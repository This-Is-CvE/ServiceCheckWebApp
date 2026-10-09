import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import config, oidc

TENANT, CLIENT = "11111111-1111-1111-1111-111111111111", "client-id"


@pytest.fixture
def sso(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for name, value in [("OIDC_TENANT_ID", TENANT), ("OIDC_CLIENT_ID", CLIENT), ("OIDC_CLIENT_SECRET", "s"),
                        ("OIDC_REDIRECT_URI", "http://testserver/api/auth/oidc/callback")]:
        monkeypatch.setattr(config, name, value)
    monkeypatch.setattr(oidc, "signing_key", lambda token: key.public_key())
    state = {"claims": {}}

    def fake_exchange(code, verifier):
        return {"id_token": jwt.encode(state["claims"], key, algorithm="RS256")}

    monkeypatch.setattr(oidc, "exchange_code", fake_exchange)

    def run(client, roles=("ServiceCheck.Consultant",), oid="oid-1", name="Erika Muster", nonce=None, state_override=None,
            audience=CLIENT):
        r = client.get("/api/auth/oidc/login", follow_redirects=False)
        q = parse_qs(urlparse(r.headers["location"]).query)
        assert r.status_code == 303 and q["code_challenge_method"] == ["S256"]
        state["claims"] = {"iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "aud": audience,
                           "exp": int(time.time()) + 300, "nonce": nonce or q["nonce"][0], "oid": oid,
                           "preferred_username": f"{oid}@pco.example", "name": name, "roles": list(roles)}
        return client.get("/api/auth/oidc/callback",
                          params={"code": "c", "state": state_override or q["state"][0]}, follow_redirects=False)

    return run


def _token(resp):
    loc = resp.headers["location"]
    assert loc.startswith("/auth/callback#token="), loc
    return loc.split("token=")[1]


def test_config_reports_available_methods(client, sso):
    assert client.get("/api/auth/config").json() == {"local": True, "oidc": True}


def test_login_creates_user_with_role_from_entra(client, sso):
    token = _token(sso(client, roles=["ServiceCheck.Admin"], oid="admin-oid"))
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["role"] == "admin" and me["full_name"] == "Erika Muster" and me["sso"] is True


def test_role_is_refreshed_on_next_login(client, sso):
    _token(sso(client, roles=["ServiceCheck.Admin"], oid="same"))
    token = _token(sso(client, roles=["ServiceCheck.Consultant"], oid="same"))
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["role"] == "consultant"


def test_user_without_app_role_is_rejected(client, sso):
    r = sso(client, roles=[], oid="norole")
    assert r.headers["location"] == "/login?error=no_role"


def test_wrong_state_nonce_and_audience_are_rejected(client, sso):
    assert sso(client, state_override="evil").headers["location"] == "/login?error=state_mismatch"
    assert sso(client, nonce="other").headers["location"] == "/login?error=invalid_token"
    assert sso(client, audience="someone-else").headers["location"] == "/login?error=invalid_token"


def test_callback_without_login_cookie_is_rejected(client, sso):
    client.cookies.clear()
    r = client.get("/api/auth/oidc/callback", params={"code": "c", "state": "x"}, follow_redirects=False)
    assert r.headers["location"] == "/login?error=session_expired"


def test_sso_user_cannot_be_edited_locally(client, auth, sso):
    token = _token(sso(client, oid="managed"))
    uid = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["id"]
    assert client.patch(f"/api/users/{uid}", json={"role": "admin"}, headers=auth).status_code == 400
    assert client.patch(f"/api/users/{uid}", json={"active": False}, headers=auth).status_code == 200
    assert sso(client, oid="managed").headers["location"] == "/login?error=account_disabled"


def test_local_login_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "AUTH_LOCAL_ENABLED", False)
    r = client.post("/api/auth/login", data={"username": "admin", "password": "adminpass"})
    assert r.status_code == 403
