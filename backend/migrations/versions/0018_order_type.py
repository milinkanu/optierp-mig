"""Order Type on Quotation and Sales Order (Sales | Maintenance | Shopping Cart).

Source: erpnext order_type on selling/doctype/quotation + sales_order.

Revision ID: 0018_order_type
Revises: 0017_promotional_scheme
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_order_type"
down_revision: Union[str, None] = "0017_promotional_scheme"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("quotations", "sales_orders"):
        op.add_column(
            table,
            sa.Column(
                "order_type",
                sa.String(30),
                nullable=False,
                server_default=sa.text("'Sales'"),
            ),
        )


def downgrade() -> None:
    for table in ("sales_orders", "quotations"):
        op.drop_column(table, "order_type")
