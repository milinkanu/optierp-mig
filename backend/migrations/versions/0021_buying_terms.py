"""Terms & Conditions on Purchase Order / Purchase Invoice (symmetry with selling).

Revision ID: 0021_buying_terms
Revises: 0020_party_address_contact
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_buying_terms"
down_revision: Union[str, None] = "0020_party_address_contact"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("purchase_orders", "purchase_invoices"):
        op.add_column(table, sa.Column("terms", sa.Text(), nullable=True))


def downgrade() -> None:
    for table in ("purchase_orders", "purchase_invoices"):
        op.drop_column(table, "terms")
