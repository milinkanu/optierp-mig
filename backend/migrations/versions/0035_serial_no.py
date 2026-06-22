"""Serial No tracking: per-unit serials with a status lifecycle, plus inline
serial_nos on the stock transaction lines.

A serialised item's units are tracked individually (warranty/RMA). Serials are
created In Stock on a receipt, flip to Delivered on a delivery, and revert on a
return/cancel — valuation stays Moving Average (serials are a tracking layer, not
separate valuation). The transaction line stores the serial_nos text it touched;
the serial_nos master holds each unit's current status + warehouse.

Revision ID: 0035_serial_no
Revises: 0034_multi_uom
Create Date: 2026-06-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0035_serial_no"
down_revision: Union[str, None] = "0034_multi_uom"
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
        sa.Column("has_serial_no", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "serial_nos",
        *_doc_columns(),
        sa.Column("company_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("serial_no", sa.String(140), nullable=False),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'In Stock'")),
        sa.Column("purchase_voucher_type", sa.String(60)),
        sa.Column("purchase_voucher_id", pg.UUID(as_uuid=True)),
        sa.Column("delivery_voucher_id", pg.UUID(as_uuid=True)),
        sa.Column("warranty_expiry", sa.Date()),
        sa.UniqueConstraint("company_id", "serial_no", name="uq_serial_no"),
    )
    op.create_index("ix_serial_nos_company_item_status", "serial_nos",
                    ["company_id", "item_id", "status"])
    op.execute("ALTER TABLE serial_nos ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_isolation ON serial_nos "
        "USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    )

    for table in _ITEM_LINE_TABLES:
        op.add_column(table, sa.Column("serial_nos", sa.Text()))


def downgrade() -> None:
    for table in _ITEM_LINE_TABLES:
        op.drop_column(table, "serial_nos")
    op.execute("DROP POLICY IF EXISTS company_isolation ON serial_nos")
    op.drop_table("serial_nos")
    op.drop_column("items", "has_serial_no")
