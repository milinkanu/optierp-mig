"""Bank Transaction: created_voucher flag.

Marks a statement line whose matched voucher was created BY the reconciliation
tool (from an unmatched line — e.g. bank charges / interest). Unreconciling such
a line cancels the voucher instead of merely un-clearing a pre-existing one.

Revision ID: 0044_bank_txn_created_voucher
Revises: 0043_bank_transaction
Create Date: 2026-06-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0044_bank_txn_created_voucher"
down_revision: Union[str, None] = "0043_bank_transaction"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bank_transactions",
        sa.Column("created_voucher", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("bank_transactions", "created_voucher")
