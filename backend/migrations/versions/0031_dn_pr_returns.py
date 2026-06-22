"""DN/PR returns: is_return + return_against_id (self-FK) on Delivery Note and
Purchase Receipt, plus supplier_delivery_note on Purchase Receipt.

A return Delivery Note takes goods back into stock (SLE in / reverse COGS); a
return Purchase Receipt sends goods back to the supplier (SLE out / reverse
SRBNB). All additive nullable columns — no behaviour change for existing rows.
Mirrors the is_return/return_against_id shape already on sales/purchase invoices
(migration 0002).

Revision ID: 0031_dn_pr_returns
Revises: 0030_service_credit_accounting
Create Date: 2026-06-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0031_dn_pr_returns"
down_revision: Union[str, None] = "0030_service_credit_accounting"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Delivery Note ---
    op.add_column(
        "delivery_notes",
        sa.Column("is_return", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("delivery_notes", sa.Column("return_against_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_dn_return_against", "delivery_notes", "delivery_notes",
        ["return_against_id"], ["id"],
    )

    # --- Purchase Receipt ---
    op.add_column(
        "purchase_receipts",
        sa.Column("is_return", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("purchase_receipts", sa.Column("return_against_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_pr_return_against", "purchase_receipts", "purchase_receipts",
        ["return_against_id"], ["id"],
    )
    op.add_column(
        "purchase_receipts", sa.Column("supplier_delivery_note", sa.String(140), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("purchase_receipts", "supplier_delivery_note")
    op.drop_constraint("fk_pr_return_against", "purchase_receipts", type_="foreignkey")
    op.drop_column("purchase_receipts", "return_against_id")
    op.drop_column("purchase_receipts", "is_return")

    op.drop_constraint("fk_dn_return_against", "delivery_notes", type_="foreignkey")
    op.drop_column("delivery_notes", "return_against_id")
    op.drop_column("delivery_notes", "is_return")
