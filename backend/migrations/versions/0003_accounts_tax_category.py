"""Module 02 — Accounts (continued): Tax Category master.

Adds the tax_categories table and tax_category_id links on tax_templates,
customers and suppliers, so invoices can resolve their tax template from
the party's category (erpnext tax_category / get_party_details).

Revision ID: 0003_accounts_tax_category
Revises: 0002_accounts
Create Date: 2026-06-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0003_accounts_tax_category"
down_revision: Union[str, None] = "0002_accounts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tax_categories",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("modified", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("docstatus", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("owner", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("modified_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "company_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("title", sa.String(140), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "title", name="uq_tax_category"),
    )

    op.add_column(
        "tax_templates",
        sa.Column("tax_category_id", pg.UUID(as_uuid=True), sa.ForeignKey("tax_categories.id")),
    )
    op.add_column(
        "customers",
        sa.Column("tax_category_id", pg.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        "fk_customer_tax_category", "customers", "tax_categories", ["tax_category_id"], ["id"]
    )
    op.add_column(
        "suppliers",
        sa.Column("tax_category_id", pg.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        "fk_supplier_tax_category", "suppliers", "tax_categories", ["tax_category_id"], ["id"]
    )

    op.execute("ALTER TABLE tax_categories ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_isolation ON tax_categories "
        "USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON tax_categories")
    op.drop_constraint("fk_supplier_tax_category", "suppliers", type_="foreignkey")
    op.drop_column("suppliers", "tax_category_id")
    op.drop_constraint("fk_customer_tax_category", "customers", type_="foreignkey")
    op.drop_column("customers", "tax_category_id")
    op.drop_column("tax_templates", "tax_category_id")
    op.drop_table("tax_categories")
