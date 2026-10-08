from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import UserCreate, UserOut, UserUpdate
from ..security import admin_user, create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == form.username))
    if not user or not user.active or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Benutzername oder Passwort falsch")
    return {"access_token": create_token(user), "token_type": "bearer", "user": UserOut.model_validate(user)}


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_user)):
    return db.scalars(select(User).order_by(User.username)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), _: User = Depends(admin_user)):
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
