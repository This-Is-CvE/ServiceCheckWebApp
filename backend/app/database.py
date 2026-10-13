from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

try:
    make_url(config.DATABASE_URL)
except ArgumentError:
    # Der Wert wird bewusst nicht ausgegeben, er enthält das Datenbank-Passwort.
    raise RuntimeError(
        "DATABASE_URL ist leer oder ungültig. Erwartet wird z. B. "
        "postgresql+psycopg://BENUTZER:PASSWORT@HOST:5432/DATENBANK?sslmode=require "
        "(Sonderzeichen im Passwort müssen URL-kodiert sein). Bitte die App-Einstellung prüfen.") from None

_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, connect_args=_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
