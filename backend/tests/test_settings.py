"""Absicherung gegen leere oder schwache Einstellungen im Produktivbetrieb (PostgreSQL)."""
import asyncio
import os
import subprocess
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(__file__))
PG = "postgresql+psycopg://u:p@localhost:1/db"  # wird nie erreicht, der Start bricht vorher ab


def run(code: str, **env):
    full = {**os.environ, **env}
    return subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=full, capture_output=True, text=True)


START = ("import asyncio\nfrom app.main import app, lifespan\n"
         "async def go():\n    async with lifespan(app): pass\nasyncio.run(go())")


@pytest.mark.parametrize("url", ["", "kein url", "postgresql+psycopg//kaputt"])
def test_empty_or_invalid_database_url_gives_clear_message(url):
    r = run("import app.database", DATABASE_URL=url)
    assert r.returncode != 0
    assert "DATABASE_URL ist leer oder ungültig" in r.stderr
    assert "Could not parse" not in r.stderr.split("RuntimeError")[-1]  # keine kryptische Folgemeldung
    assert url not in r.stderr or url == ""  # die URL (mit Passwort) wird nie ausgegeben


@pytest.mark.parametrize("secret", ["", "short", "dev-only-change-me", "x" * 31])
def test_weak_secret_key_blocks_start_with_postgres(secret):
    r = run(START, DATABASE_URL=PG, SECRET_KEY=secret, ADMIN_PASSWORD="a-long-enough-password")
    assert r.returncode != 0 and "SECRET_KEY muss gesetzt sein" in r.stderr


def test_secret_key_of_32_chars_passes_the_guard():
    r = run(START, DATABASE_URL=PG, SECRET_KEY="x" * 32, ADMIN_PASSWORD="a-long-enough-password")
    assert "SECRET_KEY muss gesetzt sein" not in r.stderr  # scheitert erst an der (absichtlich) fehlenden Datenbank


class _Bind:
    class dialect:
        name = "postgresql"


class _FakeDB:
    def scalar(self, *_):
        return None  # noch kein Benutzer vorhanden

    def get_bind(self):
        return _Bind()


@pytest.mark.parametrize("pw", ["", "admin", "kurz", "123456789"])
def test_weak_admin_password_blocks_first_admin_with_postgres(pw, monkeypatch):
    from app import config
    from app.seed import seed_admin
    monkeypatch.setattr(config, "AUTH_LOCAL_ENABLED", True)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", pw)
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        seed_admin(_FakeDB())


def test_admin_password_not_needed_when_local_login_is_disabled(monkeypatch):
    from app import config
    from app.seed import seed_admin
    monkeypatch.setattr(config, "AUTH_LOCAL_ENABLED", False)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    seed_admin(_FakeDB())  # darf nichts auslösen
