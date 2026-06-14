"""Phase 3 — Shipping Rule. Company-scoped, engine-served master; adds a freight
charge row to orders via app.services.shipping.

Revision ID: 0014_shipping_rule
Revises: 0013_coupon_code
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0014_shipping_rule"
down_revision: Union[str, None] = "0013_coupon_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shipping_rules",
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
        sa.Column("shipping_rule_name", sa.String(140), nullable=False),
        sa.Column("shipping_amount", sa.Numeric(21, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("free_above", sa.Numeric(21, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "shipping_rule_name", name="uq_shipping_rule"),
    )
    op.create_index("ix_shipping_rules_company_id", "shipping_rules", ["company_id"])
    op.execute("ALTER TABLE shipping_rules ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_isolation ON shipping_rules "
        "USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON shipping_rules")
    op.drop_index("ix_shipping_rules_company_id", table_name="shipping_rules")
    op.drop_table("shipping_rules")
