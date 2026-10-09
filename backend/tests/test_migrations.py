import os
import subprocess
import sys

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from app.database import Base, engine

BACKEND = os.path.dirname(os.path.dirname(__file__))


def test_models_and_migrations_are_in_sync(client):
    """Schlägt fehl, wenn ein Modell geändert wurde, ohne eine Migration zu erzeugen."""
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []


def test_upgrade_keeps_existing_data(tmp_path):
    """Migration 0001 -> 0002 mit vorhandenen Daten: Vorlage wird auf jedes Produkt des Managed Service kopiert."""
    url = f"sqlite:///{tmp_path}/old.db"
    env = {**os.environ, "DATABASE_URL": url}

    def alembic(rev):
        code = f"from alembic import command; from app.db_migrate import alembic_config; command.upgrade(alembic_config(), '{rev}')"
        subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, check=True)

    alembic("0001")
    e = create_engine(url)
    with e.begin() as c:
        c.execute(text("INSERT INTO offers (id, name, description) VALUES (1, 'MVI', '')"))
        c.execute(text("INSERT INTO products (id, offer_id, name, description, green_min, yellow_min) "
                       "VALUES (1, 1, 'A', '', 80, 50), (2, 1, 'B', '', 80, 50)"))
        c.execute(text("INSERT INTO onboarding_template_items (offer_id, section, label, help, field_type, required, position) "
                       "VALUES (1, 'general', 'Firma', '', 'text', 1, 10), (1, 'checklist', 'Kick-off', '', 'text', 1, 20)"))
        c.execute(text("INSERT INTO customers (id, name, contact_name, contact_email, notes) VALUES (1, 'K', '', '', '')"))
    alembic("head")
    with e.connect() as c:
        rows = c.execute(text("SELECT product_id, label FROM onboarding_template_items ORDER BY product_id, position")).all()
        assert rows == [(1, "Firma"), (1, "Kick-off"), (2, "Firma"), (2, "Kick-off")]
        assert c.execute(text("SELECT kt_number FROM customers")).scalar() == ""
