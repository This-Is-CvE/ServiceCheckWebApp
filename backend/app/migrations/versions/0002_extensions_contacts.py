"""Erweiterungskataloge, Onboarding-Vorlage pro Produkt, Ansprechpartner, KT-Nummer, Modell/Seriennummer

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

EMPTY = sa.text("''")
EMPTY_LIST = sa.text("'[]'")


def upgrade() -> None:
    op.create_table(
        "product_extensions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=EMPTY),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "onboarding_contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("onboarding_id", sa.Integer(), sa.ForeignKey("onboardings.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(200), nullable=False, server_default=EMPTY),
        sa.Column("phone", sa.String(100), nullable=False, server_default=EMPTY),
        sa.Column("mobile", sa.String(100), nullable=False, server_default=EMPTY),
        sa.Column("email", sa.String(200), nullable=False, server_default=EMPTY),
        sa.Column("notes", sa.Text(), nullable=False, server_default=EMPTY),
    )

    with op.batch_alter_table("customers") as b:
        b.add_column(sa.Column("kt_number", sa.String(50), nullable=False, server_default=EMPTY))
    with op.batch_alter_table("onboarding_assets") as b:
        b.add_column(sa.Column("model", sa.String(200), nullable=False, server_default=EMPTY))
        b.add_column(sa.Column("serial_number", sa.String(200), nullable=False, server_default=EMPTY))
    with op.batch_alter_table("parameters") as b:
        b.add_column(sa.Column("extension_id", sa.Integer(), nullable=True))
        b.create_foreign_key("fk_parameters_extension", "product_extensions", ["extension_id"], ["id"])
    with op.batch_alter_table("check_items") as b:
        b.add_column(sa.Column("extension_name", sa.String(200), nullable=True))
    with op.batch_alter_table("service_checks") as b:
        b.add_column(sa.Column("extensions", sa.JSON(), nullable=False, server_default=EMPTY_LIST))
    with op.batch_alter_table("onboarding_items") as b:
        b.add_column(sa.Column("extension_name", sa.String(200), nullable=True))
    with op.batch_alter_table("onboardings") as b:
        b.add_column(sa.Column("product_id", sa.Integer(), nullable=True))
        b.create_foreign_key("fk_onboardings_product", "products", ["product_id"], ["id"])
        b.add_column(sa.Column("product_name", sa.String(200), nullable=False, server_default=EMPTY))
        b.add_column(sa.Column("extensions", sa.JSON(), nullable=False, server_default=EMPTY_LIST))

    # Onboarding-Vorlage: vom Managed Service auf jedes seiner Produkte kopieren
    with op.batch_alter_table("onboarding_template_items") as b:
        b.add_column(sa.Column("product_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("extension_id", sa.Integer(), nullable=True))
        b.create_foreign_key("fk_template_product", "products", ["product_id"], ["id"])
        b.create_foreign_key("fk_template_extension", "product_extensions", ["extension_id"], ["id"])
    op.execute(
        "INSERT INTO onboarding_template_items "
        "(offer_id, product_id, section, label, help, field_type, required, position) "
        "SELECT t.offer_id, p.id, t.section, t.label, t.help, t.field_type, t.required, t.position "
        "FROM onboarding_template_items t JOIN products p ON p.offer_id = t.offer_id WHERE t.product_id IS NULL")
    op.execute("DELETE FROM onboarding_template_items WHERE product_id IS NULL")
    with op.batch_alter_table("onboarding_template_items") as b:
        b.drop_column("offer_id")
        b.alter_column("product_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    raise NotImplementedError("Ein Downgrade von 0002 ist nicht vorgesehen (Datenverlust). Bitte aus der Sicherung wiederherstellen.")
