"""Supplier Address & Contact links on Purchase Order + Purchase Invoice.

Source: erpnext supplier_address / shipping_address / contact_person on the
buying/accounts purchase doctypes (direct FK links, mirroring the selling A&C).

Revision ID: 0023_buying_address_contact
Revises: 0022_buying_masters
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0023_buying_address_contact"
down_revision: Union[str, None] = "0022_buying_masters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("purchase_orders", "purchase_invoices")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("supplier_address_id", pg.UUID(as_uuid=True), nullable=True))
        op.add_column(table, sa.Column("shipping_address_id", pg.UUID(as_uuid=True), nullable=True))
        op.add_column(table, sa.Column("contact_person_id", pg.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_supplier_address", table, "addresses",
            ["supplier_address_id"], ["id"], ondelete="SET NULL",
        )
        op.create_foreign_key(
            f"fk_{table}_shipping_address", table, "addresses",
            ["shipping_address_id"], ["id"], ondelete="SET NULL",
        )
        op.create_foreign_key(
            f"fk_{table}_contact_person", table, "contacts",
            ["contact_person_id"], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f"fk_{table}_contact_person", table, type_="foreignkey")
        op.drop_constraint(f"fk_{table}_shipping_address", table, type_="foreignkey")
        op.drop_constraint(f"fk_{table}_supplier_address", table, type_="foreignkey")
        op.drop_column(table, "contact_person_id")
        op.drop_column(table, "shipping_address_id")
        op.drop_column(table, "supplier_address_id")
