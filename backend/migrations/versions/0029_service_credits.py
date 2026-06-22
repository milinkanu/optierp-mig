"""Service Credits: prepaid service units (e.g. hours) with usage drawdown.

A service credit is a depleting counter (purchased − consumed = balance), not
stock — so it has its own two small tables, no Bin / SLE. The parent gets the
company_isolation RLS policy; usage rows are reached via the parent.

Revision ID: 0029_service_credits
Revises: 0028_stock_reconciliation
Create Date: 2026-06-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0029_service_credits"
down_revision: Union[str, None] = "0028_stock_reconciliation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _doc_columns() -> list[sa.Column]:
    return [
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("modified", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("docstatus", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("owner", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("modified_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    ]


def _amount(name: str, default: str = "0") -> sa.Column:
    return sa.Column(name, sa.Numeric(21, 6), nullable=False, server_default=sa.text(default))


def upgrade() -> None:
    op.create_table(
        "service_credits",
        *_doc_columns(),
        sa.Column("company_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(140), nullable=False),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("supplier_id", pg.UUID(as_uuid=True), sa.ForeignKey("suppliers.id")),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("purchased_qty", sa.Numeric(21, 6), nullable=False),
        _amount("consumed_qty"),
        _amount("rate"),
        sa.Column("uom", sa.String(140)),
        sa.Column("valid_upto", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'Active'")),
        sa.Column("remarks", sa.Text()),
        sa.UniqueConstraint("company_id", "name", name="uq_service_credit_name"),
    )
    op.create_index("ix_service_credits_company", "service_credits", ["company_id"])
    op.create_table(
        "service_credit_usages",
        *_doc_columns(),
        sa.Column("service_credit_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("service_credits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("qty", sa.Numeric(21, 6), nullable=False),
        sa.Column("remarks", sa.Text()),
    )

    op.execute("ALTER TABLE service_credits ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_isolation ON service_credits "
        "USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON service_credits")
    op.drop_table("service_credit_usages")
    op.drop_table("service_credits")
