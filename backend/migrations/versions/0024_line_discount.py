"""Per-line discount columns on every transaction line table.

Source: erpnext sales/purchase item `price_list_rate` / `discount_percentage` /
`discount_amount`. Added to the shared ``InvoiceItemMixin`` (app.models.accounts),
so all six line tables that inherit it must gain the columns or the ORM mapping
and the DB schema diverge.

The engine (``app.services.taxes_and_totals``) already derives the discounted
``rate`` from ``price_list_rate`` + ``discount_percentage``; these columns just
persist the inputs and let the response echo them.

Revision ID: 0024_line_discount
Revises: 0023_buying_address_contact
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024_line_discount"
down_revision: Union[str, None] = "0023_buying_address_contact"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every table whose model inherits InvoiceItemMixin.
_TABLES = (
    "quotation_items",
    "sales_order_items",
    "purchase_order_items",
    "supplier_quotation_items",
    "sales_invoice_items",
    "purchase_invoice_items",
)

_MONEY = sa.Numeric(21, 6)
_PCT = sa.Numeric(8, 4)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("price_list_rate", _MONEY, nullable=False, server_default=sa.text("0")),
        )
        op.add_column(
            table,
            sa.Column("base_price_list_rate", _MONEY, nullable=False, server_default=sa.text("0")),
        )
        op.add_column(
            table,
            sa.Column("discount_percentage", _PCT, nullable=False, server_default=sa.text("0")),
        )
        op.add_column(
            table,
            sa.Column("discount_amount", _MONEY, nullable=False, server_default=sa.text("0")),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "discount_amount")
        op.drop_column(table, "discount_percentage")
        op.drop_column(table, "base_price_list_rate")
        op.drop_column(table, "price_list_rate")
