"""Billing/Shipping Address + Contact Person links on Quotation / Sales Order / Sales Invoice.

Source: erpnext customer_address / shipping_address_name / contact_person on the
selling + accounts transaction doctypes (direct FK links, mirroring our Address/
Contact masters).

Revision ID: 0020_party_address_contact
Revises: 0019_terms_and_customer_po
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0020_party_address_contact"
down_revision: Union[str, None] = "0019_terms_and_customer_po"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("quotations", "sales_orders", "sales_invoices")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("customer_address_id", pg.UUID(as_uuid=True), nullable=True))
        op.add_column(table, sa.Column("shipping_address_id", pg.UUID(as_uuid=True), nullable=True))
        op.add_column(table, sa.Column("contact_person_id", pg.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_customer_address", table, "addresses",
            ["customer_address_id"], ["id"], ondelete="SET NULL",
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
        op.drop_constraint(f"fk_{table}_customer_address", table, type_="foreignkey")
        op.drop_column(table, "contact_person_id")
        op.drop_column(table, "shipping_address_id")
        op.drop_column(table, "customer_address_id")
