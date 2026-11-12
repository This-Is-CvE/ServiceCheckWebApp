"""Freitextfeld "Beschreibung" (details) an Katalogparametern und deren Check-Snapshots

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

EMPTY = sa.text("''")


def upgrade() -> None:
    for table in ("parameters", "check_items"):
        with op.batch_alter_table(table) as b:
            b.add_column(sa.Column("details", sa.Text(), nullable=False, server_default=EMPTY))


def downgrade() -> None:
    for table in ("parameters", "check_items"):
        with op.batch_alter_table(table) as b:
            b.drop_column("details")
