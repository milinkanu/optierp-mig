"""Opening (migration-in) invoices: is_opening on sales/purchase invoices.

An opening invoice records an outstanding receivable/payable that existed before
go-live. It posts the amount against the company's "Temporary Opening" account
(no income/expense, no tax) and is excluded from the sales/purchase registers.

Revision ID: 0039_invoice_is_opening
Revises: 0038_tax_included_in_print_rate
Create Date: 2026-06-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039_invoice_is_opening"
down_revision: Union[str, None] = "0038_tax_included_in_print_rate"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("sales_invoices", "purchase_invoices")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "is_opening", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "is_opening")
