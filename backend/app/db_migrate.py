import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .database import engine

MIGRATIONS = os.path.join(os.path.dirname(__file__), "migrations")


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", MIGRATIONS)
    return cfg


def upgrade_db() -> None:
    """Bringt das Datenbankschema auf den aktuellen Stand (alembic upgrade head)."""
    tables = inspect(engine).get_table_names()
    if tables and "alembic_version" not in tables:
        raise RuntimeError(
            "Die Datenbank enthält Tabellen, wurde aber nicht mit Migrationen angelegt (Stand vor Einführung "
            "von Alembic). Bitte eine leere Datenbank verwenden, z. B. 'docker compose down -v'.")
    command.upgrade(alembic_config(), "head")
