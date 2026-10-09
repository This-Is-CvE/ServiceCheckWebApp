from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, oidc
from ..database import get_db
from ..models import User
from ..schemas import UserCreate, UserOut, UserUpdate
from ..security import admin_user, create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/auth/config")
def auth_config():
    return {"local": config.AUTH_LOCAL_ENABLED, "oidc": config.oidc_enabled()}


@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    if not config.AUTH_LOCAL_ENABLED:
        raise HTTPException(403, "Die lokale Anmeldung ist deaktiviert. Bitte mit Microsoft anmelden.")
    user = db.scalar(select(User).where(User.username == form.username))
    if not user or not user.active or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Benutzername oder Passwort falsch")
    return {"access_token": create_token(user), "token_type": "bearer", "user": UserOut.model_validate(user)}


def _login_error(code: str) -> RedirectResponse:
    resp = RedirectResponse("/login?" + urlencode({"error": code}), status_code=303)
    resp.delete_cookie(oidc.COOKIE, path=oidc.COOKIE_PATH)
    return resp


@router.get("/auth/oidc/login")
def oidc_login():
    if not config.oidc_enabled():
        raise HTTPException(404, "Anmeldung über Entra ID ist nicht konfiguriert")
    url, cookie = oidc.new_transaction()
    resp = RedirectResponse(url, status_code=303)
    resp.set_cookie(oidc.COOKIE, cookie, max_age=600, httponly=True, samesite="lax", path=oidc.COOKIE_PATH,
                    secure=config.OIDC_REDIRECT_URI.startswith("https://"))
    return resp


@router.get("/auth/oidc/callback")
def oidc_callback(request: Request, code: str | None = None, state: str | None = None,
                  error: str | None = None, db: Session = Depends(get_db)):
    if not config.oidc_enabled():
        raise HTTPException(404, "Anmeldung über Entra ID ist nicht konfiguriert")
    try:
        if error or not code:
            raise oidc.OidcError("login_cancelled")
        tx = oidc.read_transaction(request.cookies.get(oidc.COOKIE), state)
        tokens = oidc.exchange_code(code, tx["verifier"])
        claims = oidc.validate_id_token(tokens.get("id_token", ""), tx["nonce"])
        role = oidc.role_from_claims(claims)
        if role is None:
            raise oidc.OidcError("no_role")
        external_id = claims.get("oid") or claims.get("sub")
        username = (claims.get("preferred_username") or claims.get("email") or external_id).lower()
        user = db.scalar(select(User).where(User.external_id == external_id))
        if user is None:
            if db.scalar(select(User).where(User.username == username)):
                raise oidc.OidcError("username_taken")
            user = User(username=username, external_id=external_id, password_hash=None, active=True)
            db.add(user)
        if not user.active:
            raise oidc.OidcError("account_disabled")
        user.role, user.full_name = role, claims.get("name") or user.full_name or username
        db.commit()
    except oidc.OidcError as exc:
        return _login_error(exc.code)
    resp = RedirectResponse("/auth/callback#" + urlencode({"token": create_token(user)}), status_code=303)
    resp.delete_cookie(oidc.COOKIE, path=oidc.COOKIE_PATH)
    return resp


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_user)):
    return db.scalars(select(User).order_by(User.username)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    if not config.AUTH_LOCAL_ENABLED:
        raise HTTPException(400, "Lokale Benutzer sind deaktiviert; Benutzer werden über Entra ID verwaltet")
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(409, "Benutzername existiert bereits")
    user = User(username=body.username, full_name=body.full_name, role=body.role,
                password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Benutzer nicht gefunden")
    data = body.model_dump(exclude_unset=True)
    if user.external_id and (data.get("role") or data.get("password") or "full_name" in data):
        raise HTTPException(400, "Rolle, Name und Passwort dieses Benutzers werden in Entra ID verwaltet")
    if user.id == admin.id and (data.get("active") is False or data.get("role") == "consultant"):
        raise HTTPException(400, "Das eigene Konto kann nicht deaktiviert oder herabgestuft werden")
    if "password" in data:
        pw = data.pop("password")
        if pw:
            user.password_hash = hash_password(pw)
    for k, v in data.items():
        if v is not None:
            setattr(user, k, v)
    db.commit()
    return user
