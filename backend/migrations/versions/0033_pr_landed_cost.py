"""Purchase Receipt landed cost: a purchase_receipt_charges child table.

Additional costs (freight / customs / insurance) entered directly on the receipt
are apportioned by item value into the incoming stock valuation at submit, so
COGS later reflects the true landed cost — without a separate Landed Cost Voucher.
GL on submit: Dr inventory (base + apportioned charge) / Cr SRBNB (item base) /
Cr each charge account (its amount). Child-scoped (parent receipt is RLS'd), so no
own RLS — mirrors purchase_receipt_items.

Revision ID: 0033_pr_landed_cost
Revises: 0032_pr_rejected_qty
Create Date: 2026-06-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0033_pr_landed_cost"
down_revision: Union[str, None] = "0032_pr_rejected_qty"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "purchase_receipt_charges",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", pg.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("modified", pg.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("docstatus", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("owner", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("modified_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("receipt_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("purchase_receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("description", sa.String(180), nullable=False),
        sa.Column("account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("amount", sa.Numeric(21, 6), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_pr_charges_receipt", "purchase_receipt_charges", ["receipt_id"])


def downgrade() -> None:
    op.drop_index("ix_pr_charges_receipt", table_name="purchase_receipt_charges")
    op.drop_table("purchase_receipt_charges")
