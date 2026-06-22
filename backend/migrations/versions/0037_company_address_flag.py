"""Company-owned addresses for print letterheads.

A company prints its own registered-office / billing / dispatch address on its
documents. Rather than a new table, we flag ``Address`` rows that belong to the
company itself (``is_company_address=true``, with ``customer_id``/``supplier_id``
NULL). The existing per-tenant RLS policy on ``addresses`` already isolates them,
and the ``address_type`` column already carries the label.

Revision ID: 0037_company_address_flag
Revises: 0036_batch_no
Create Date: 2026-06-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0037_company_address_flag"
down_revision: Union[str, None] = "0036_batch_no"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "addresses",
        sa.Column(
            "is_company_address",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("addresses", "is_company_address")
