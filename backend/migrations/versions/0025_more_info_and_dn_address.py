"""Shared "More Info" link fields on Quotation/Sales Order + Address & Contact
on Delivery Note.

Source: erpnext selling More Info section (campaign / source / territory /
customer_group / sales_partner) and the delivery_note customer_address /
shipping_address / contact_person FKs (mirrors the order/invoice A&C links).

All columns are additive, nullable, ondelete SET NULL.

Revision ID: 0025_more_info_and_dn_address
Revises: 0024_line_discount
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0025_more_info_and_dn_address"
down_revision: Union[str, None] = "0024_line_discount"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# More Info link fields -> (column, target table) on the selling order docs.
_MORE_INFO = (
    ("campaign_id", "campaigns"),
    ("source_id", "utm_sources"),
    ("territory_id", "territories"),
    ("customer_group_id", "customer_groups"),
    ("sales_partner_id", "sales_partners"),
)
_ORDER_TABLES = ("quotations", "sales_orders")

# Address & Contact on the delivery note (party is the customer).
_DN_LINKS = (
    ("customer_address_id", "addresses"),
    ("shipping_address_id", "addresses"),
    ("contact_person_id", "contacts"),
)


def upgrade() -> None:
    for table in _ORDER_TABLES:
        for col, target in _MORE_INFO:
            op.add_column(table, sa.Column(col, pg.UUID(as_uuid=True), nullable=True))
            op.create_foreign_key(
                f"fk_{table}_{col}", table, target, [col], ["id"], ondelete="SET NULL",
            )
    for col, target in _DN_LINKS:
        op.add_column("delivery_notes", sa.Column(col, pg.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            f"fk_delivery_notes_{col}", "delivery_notes", target, [col], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    for col, _ in _DN_LINKS:
        op.drop_constraint(f"fk_delivery_notes_{col}", "delivery_notes", type_="foreignkey")
        op.drop_column("delivery_notes", col)
    for table in _ORDER_TABLES:
        for col, _ in _MORE_INFO:
            op.drop_constraint(f"fk_{table}_{col}", table, type_="foreignkey")
            op.drop_column(table, col)
