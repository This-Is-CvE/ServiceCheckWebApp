"""Anmeldung über Microsoft Entra ID (OpenID Connect, Authorization-Code-Flow mit PKCE).

Rollen kommen aus den App-Rollen der Entra-App-Registrierung (Claim "roles"):
  OIDC_ADMIN_ROLE -> Administrator, OIDC_USER_ROLE -> Consultant. Ohne eine der beiden Rollen kein Zugang.
Die Rolle wird bei jeder Anmeldung neu aus dem Token übernommen.
"""
import base64
import hashlib
import secrets
import time
from functools import lru_cache
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from . import config

COOKIE = "oidc_tx"
COOKIE_PATH = "/api/auth/oidc"


class OidcError(Exception):
    """Fehler mit kurzem Code, der der Login-Seite übergeben wird."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _base() -> str:
    return f"https://login.microsoftonline.com/{config.OIDC_TENANT_ID}"


def issuer() -> str:
    return f"{_base()}/v2.0"


def new_transaction() -> tuple[str, str]:
    """Liefert (Authorize-URL, signierter Cookie-Wert mit state/nonce/PKCE-Verifier)."""
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    cookie = jwt.encode({"state": state, "nonce": nonce, "verifier": verifier, "exp": int(time.time()) + 600},
                        config.SECRET_KEY, algorithm="HS256")
    url = f"{_base()}/oauth2/v2.0/authorize?" + urlencode({
        "client_id": config.OIDC_CLIENT_ID, "response_type": "code", "redirect_uri": config.OIDC_REDIRECT_URI,
        "response_mode": "query", "scope": "openid profile email", "state": state, "nonce": nonce,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    return url, cookie


def read_transaction(cookie: str | None, state: str | None) -> dict:
    try:
        tx = jwt.decode(cookie or "", config.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise OidcError("session_expired")
    if not state or not secrets.compare_digest(tx["state"], state):
        raise OidcError("state_mismatch")
    return tx


def exchange_code(code: str, verifier: str) -> dict:
    resp = httpx.post(f"{_base()}/oauth2/v2.0/token", timeout=15, data={
        "client_id": config.OIDC_CLIENT_ID, "client_secret": config.OIDC_CLIENT_SECRET, "grant_type": "authorization_code",
        "code": code, "redirect_uri": config.OIDC_REDIRECT_URI, "code_verifier": verifier,
    })
    if resp.status_code != 200:
        raise OidcError("token_exchange_failed")
    return resp.json()


@lru_cache
def _jwks(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True)


def signing_key(id_token: str):
    return _jwks(f"{_base()}/discovery/v2.0/keys").get_signing_key_from_jwt(id_token).key


def validate_id_token(id_token: str, nonce: str) -> dict:
    try:
        claims = jwt.decode(id_token, signing_key(id_token), algorithms=["RS256"],
                            audience=config.OIDC_CLIENT_ID, issuer=issuer())
    except jwt.PyJWTError:
        raise OidcError("invalid_token")
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise OidcError("invalid_token")
    return claims


def role_from_claims(claims: dict) -> str | None:
    roles = claims.get("roles") or []
    if config.OIDC_ADMIN_ROLE in roles:
        return "admin"
    if config.OIDC_USER_ROLE in roles:
        return "consultant"
    return None
