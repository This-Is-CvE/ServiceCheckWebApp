from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.database import Base, engine


def test_models_and_migrations_are_in_sync(client):
    """Schlägt fehl, wenn ein Modell geändert wurde, ohne eine Migration zu erzeugen."""
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []
