"""Inclusive taxes: included_in_print_rate on every tax-and-charges row.

When set, the line rate is treated as tax-inclusive (MRP / GST-inclusive
pricing) and the net rate is back-calculated by the taxes_and_totals engine.
The flag lives on the shared TaxRowMixin, so it is added to all six tax-row
tables (templates + the five transaction tax child tables).

Revision ID: 0038_tax_included_in_print_rate
Revises: 0037_company_address_flag
Create Date: 2026-06-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038_tax_included_in_print_rate"
down_revision: Union[str, None] = "0037_company_address_flag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "tax_template_details",
    "sales_invoice_taxes",
    "purchase_invoice_taxes",
    "sales_order_taxes",
    "purchase_order_taxes",
    "quotation_taxes",
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "included_in_print_rate",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "included_in_print_rate")
