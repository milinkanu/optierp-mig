"""Tax Category: is_inter_state flag.

Marks the out-of-state (IGST) category so GST can auto-resolve place of supply
from the party's GSTIN state vs the company's, instead of a manual category.

Revision ID: 0045_tax_category_inter_state
Revises: 0044_bank_txn_created_voucher
Create Date: 2026-06-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0045_tax_category_inter_state"
down_revision: Union[str, None] = "0044_bank_txn_created_voucher"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tax_categories",
        sa.Column("is_inter_state", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tax_categories", "is_inter_state")
