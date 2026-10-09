from alembic import context
from sqlalchemy import text

from app import models  # noqa: F401  (registriert alle Tabellen)
from app.database import Base, engine

target_metadata = Base.metadata
ADVISORY_LOCK = 727274  # verhindert parallele Migrationen bei mehreren App-Instanzen (PostgreSQL)


def run() -> None:
    with engine.connect() as connection:
        postgres = connection.dialect.name == "postgresql"
        if postgres:
            connection.execute(text(f"SELECT pg_advisory_lock({ADVISORY_LOCK})"))
        try:
            context.configure(connection=connection, target_metadata=target_metadata,
                              render_as_batch=connection.dialect.name == "sqlite", compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
            connection.commit()
        finally:
            if postgres:
                connection.execute(text(f"SELECT pg_advisory_unlock({ADVISORY_LOCK})"))
                connection.commit()


run()
