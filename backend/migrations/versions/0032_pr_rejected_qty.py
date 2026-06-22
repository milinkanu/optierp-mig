"""Purchase Receipt accepted/rejected split: rejected_qty + rejected_warehouse_id
on purchase_receipt_items.

`qty` stays the ACCEPTED quantity (received into the line warehouse); rejected_qty
is received into a separate rejected warehouse and valued, but is not billed. The
PO received_qty accrues qty+rejected_qty so a partly-rejected receipt still closes
the order. Additive nullable columns — no behaviour change for existing rows.

Revision ID: 0032_pr_rejected_qty
Revises: 0031_dn_pr_returns
Create Date: 2026-06-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0032_pr_rejected_qty"
down_revision: Union[str, None] = "0031_dn_pr_returns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "purchase_receipt_items",
        sa.Column(
            "rejected_qty", sa.Numeric(21, 6), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "purchase_receipt_items", sa.Column("rejected_warehouse_id", pg.UUID(as_uuid=True))
    )
    op.create_foreign_key(
        "fk_pri_rejected_warehouse", "purchase_receipt_items", "warehouses",
        ["rejected_warehouse_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_pri_rejected_warehouse", "purchase_receipt_items", type_="foreignkey")
    op.drop_column("purchase_receipt_items", "rejected_warehouse_id")
    op.drop_column("purchase_receipt_items", "rejected_qty")
