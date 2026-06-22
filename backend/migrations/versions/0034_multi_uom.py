"""Multi-UOM at item level: per-item purchase/sales UOM + conversion factors, and
conversion_factor + stock_qty on every transaction line.

A line entered in a non-stock UOM (e.g. 5 Box, factor 12) carries
``stock_qty = qty * conversion_factor`` (60); the Bin, demand counters and
cross-document caps all move in stock_qty while amounts stay in the transaction
UOM. All additive: existing rows get conversion_factor 1 and stock_qty backfilled
to qty, so behaviour is unchanged for single-UOM items.

Revision ID: 0034_multi_uom
Revises: 0033_pr_landed_cost
Create Date: 2026-06-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034_multi_uom"
down_revision: Union[str, None] = "0033_pr_landed_cost"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every transaction line table that gains conversion_factor + stock_qty.
# The first six share InvoiceItemMixin (so the model carries the columns); the
# rest are stock-module lines that get them explicitly.
_LINE_TABLES = (
    "quotation_items",
    "supplier_quotation_items",
    "purchase_order_items",
    "sales_order_items",
    "sales_invoice_items",
    "purchase_invoice_items",
    "purchase_receipt_items",
    "delivery_note_items",
    "stock_entry_items",
    "material_request_items",
)


def upgrade() -> None:
    # --- Item: flat purchase/sales UOM + conversion factors ---
    op.add_column("items", sa.Column("purchase_uom", sa.String(140), nullable=True))
    op.add_column("items", sa.Column("sales_uom", sa.String(140), nullable=True))
    op.add_column(
        "items",
        sa.Column("purchase_uom_factor", sa.Numeric(21, 9), nullable=False,
                  server_default=sa.text("1")),
    )
    op.add_column(
        "items",
        sa.Column("sales_uom_factor", sa.Numeric(21, 9), nullable=False,
                  server_default=sa.text("1")),
    )

    # --- conversion_factor + stock_qty on every transaction line ---
    for table in _LINE_TABLES:
        op.add_column(
            table,
            sa.Column("conversion_factor", sa.Numeric(21, 9), nullable=False,
                      server_default=sa.text("1")),
        )
        op.add_column(
            table,
            sa.Column("stock_qty", sa.Numeric(21, 6), nullable=False,
                      server_default=sa.text("0")),
        )
        # backfill: existing single-UOM rows have stock_qty == qty (factor 1)
        op.execute(f"UPDATE {table} SET stock_qty = qty")


def downgrade() -> None:
    for table in _LINE_TABLES:
        op.drop_column(table, "stock_qty")
        op.drop_column(table, "conversion_factor")
    op.drop_column("items", "sales_uom_factor")
    op.drop_column("items", "purchase_uom_factor")
    op.drop_column("items", "sales_uom")
    op.drop_column("items", "purchase_uom")
