"""Bank Transaction: imported bank-statement lines for reconciliation.

A Bank Transaction is one line from a bank statement (deposit/withdrawal). It
posts no GL; reconciling it sets the matched voucher's clearance_date (the
existing bank-rec mechanism). MVP matches one line to one existing voucher.

Revision ID: 0043_bank_transaction
Revises: 0042_item_tax_template
Create Date: 2026-06-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0043_bank_transaction"
down_revision: Union[str, None] = "0042_item_tax_template"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bank_transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("creation", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("owner", UUID(as_uuid=True), nullable=True),
        sa.Column("modified_by", UUID(as_uuid=True), nullable=True),
        sa.Column("docstatus", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column(
            "bank_account_id", UUID(as_uuid=True),
            sa.ForeignKey("bank_accounts.id"), nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("reference_number", sa.String(length=140), nullable=True),
        sa.Column("deposit", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("withdrawal", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'Unreconciled'"), nullable=False),
        sa.Column("matched_voucher_type", sa.String(length=40), nullable=True),
        sa.Column("matched_voucher_id", UUID(as_uuid=True), nullable=True),
        sa.Column("matched_voucher_no", sa.String(length=140), nullable=True),
        sa.UniqueConstraint("company_id", "name", name="uq_bank_transaction_name"),
    )
    op.create_index(
        "ix_bank_transactions_account_status", "bank_transactions",
        ["bank_account_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_bank_transactions_account_status", table_name="bank_transactions")
    op.drop_table("bank_transactions")
