"""Terms & Conditions (Quotation/Sales Order/Sales Invoice) + Customer PO (po_no, po_date) on Sales Order/Sales Invoice.

Source: erpnext tc_name/terms + po_no/po_date on selling/accounts doctypes.

Revision ID: 0019_terms_and_customer_po
Revises: 0018_order_type
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_terms_and_customer_po"
down_revision: Union[str, None] = "0018_order_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("quotations", "sales_orders", "sales_invoices"):
        op.add_column(table, sa.Column("terms", sa.Text(), nullable=True))
    for table in ("sales_orders", "sales_invoices"):
        op.add_column(table, sa.Column("po_no", sa.String(140), nullable=True))
        op.add_column(table, sa.Column("po_date", sa.Date(), nullable=True))


def downgrade() -> None:
    for table in ("sales_orders", "sales_invoices"):
        op.drop_column(table, "po_date")
        op.drop_column(table, "po_no")
    for table in ("quotations", "sales_orders", "sales_invoices"):
        op.drop_column(table, "terms")
