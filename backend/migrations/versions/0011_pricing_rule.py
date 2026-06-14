"""Phase 3 — Pricing Rule (pricing engine). Company-scoped, engine-served master;
applied to selling line rates by app.services.pricing.

Revision ID: 0011_pricing_rule
Revises: 0010_address_contact
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0011_pricing_rule"
down_revision: Union[str, None] = "0010_address_contact"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pricing_rules",
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
        sa.Column("selling", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("buying", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("apply_on", sa.String(20), nullable=False, server_default=sa.text("'Item'")),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id")),
        sa.Column("item_group_id", pg.UUID(as_uuid=True), sa.ForeignKey("item_groups.id")),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id")),
        sa.Column("min_qty", sa.Numeric(21, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("max_qty", sa.Numeric(21, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_upto", sa.Date()),
        sa.Column("rate_or_discount", sa.String(20), nullable=False,
                  server_default=sa.text("'Discount Percentage'")),
        sa.Column("discount_percentage", sa.Numeric(8, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("discount_amount", sa.Numeric(21, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("rate", sa.Numeric(21, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "title", name="uq_pricing_rule_title"),
    )
    op.create_index("ix_pricing_rules_company_id", "pricing_rules", ["company_id"])
    op.execute("ALTER TABLE pricing_rules ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_isolation ON pricing_rules "
        "USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON pricing_rules")
    op.drop_index("ix_pricing_rules_company_id", table_name="pricing_rules")
    op.drop_table("pricing_rules")
