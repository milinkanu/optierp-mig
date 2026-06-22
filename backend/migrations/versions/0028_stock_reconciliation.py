"""Stock Reconciliation: opening-balance / physical-count document.

Two new tables (stock_reconciliations + items). On submit the service posts
the qty/value difference vs the current Bin to the (existing) stock ledger and
Stock Adjustment GL — no schema change to the ledger is needed. The parent gets
the company_isolation RLS policy and a partial (company_id, docstatus) index,
matching the other Module-03 vouchers.

Revision ID: 0028_stock_reconciliation
Revises: 0027_doc_payment_terms
Create Date: 2026-06-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0028_stock_reconciliation"
down_revision: Union[str, None] = "0027_doc_payment_terms"
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
        "stock_reconciliations",
        *_doc_columns(),
        sa.Column("company_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(140), nullable=False),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("workflow_state", sa.String(100)),
        sa.Column("remarks", sa.Text()),
        sa.Column("amended_from_id", pg.UUID(as_uuid=True)),
        sa.Column("purpose", sa.String(40), nullable=False,
                  server_default=sa.text("'Stock Reconciliation'")),
        sa.Column("set_warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id")),
        _amount("difference_amount"),
        sa.UniqueConstraint("company_id", "name", name="uq_stock_reconciliation_name"),
    )
    op.create_table(
        "stock_reconciliation_items",
        *_doc_columns(),
        sa.Column("reconciliation_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("stock_reconciliations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("qty", sa.Numeric(21, 6), nullable=False),
        sa.Column("uom", sa.String(140)),
        _amount("valuation_rate"),
        _amount("current_qty"),
        _amount("current_valuation_rate"),
        _amount("amount_difference"),
    )

    op.execute(
        "CREATE INDEX ix_stock_reconciliations_company_docstatus "
        "ON stock_reconciliations (company_id, docstatus) WHERE docstatus < 2"
    )

    op.execute("ALTER TABLE stock_reconciliations ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_isolation ON stock_reconciliations "
        "USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON stock_reconciliations")
    op.drop_table("stock_reconciliation_items")
    op.drop_table("stock_reconciliations")
