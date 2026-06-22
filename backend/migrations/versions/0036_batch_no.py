"""Batch tracking: lot-level batches with optional expiry, plus inline batch_no on
the stock transaction lines.

A batched item's movements are labelled with a batch_no (a lot). Unlike serials,
a batch has NO per-unit status — it is just a label on the movement; the line
stores the batch_no it moved and the batches master holds the batch's item +
optional expiry. Delivering an expired batch is blocked at submit. Valuation stays
Moving Average (batch is a tracking label, not separate valuation). The Batch
master is descriptor-backed (free CRUD at /m/batch).

Revision ID: 0036_batch_no
Revises: 0035_serial_no
Create Date: 2026-06-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0036_batch_no"
down_revision: Union[str, None] = "0035_serial_no"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ITEM_LINE_TABLES = ("purchase_receipt_items", "delivery_note_items", "stock_entry_items")


def _doc_columns() -> list[sa.Column]:
    return [
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("modified", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("docstatus", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("owner", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("modified_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    ]


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("has_batch_no", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "batches",
        *_doc_columns(),
        sa.Column("company_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_no", sa.String(140), nullable=False),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # unique per (company, item) — the line resolver keys on item too, so two SKUs
        # may legitimately reuse a supplier's lot string
        sa.UniqueConstraint("company_id", "item_id", "batch_no", name="uq_batch_no"),
    )
    op.create_index("ix_batches_company_item", "batches", ["company_id", "item_id"])
    op.execute("ALTER TABLE batches ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_isolation ON batches "
        "USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    )

    for table in _ITEM_LINE_TABLES:
        op.add_column(table, sa.Column("batch_no", sa.String(140)))


def downgrade() -> None:
    for table in _ITEM_LINE_TABLES:
        op.drop_column(table, "batch_no")
    op.execute("DROP POLICY IF EXISTS company_isolation ON batches")
    op.drop_table("batches")
    op.drop_column("items", "has_batch_no")
