"""Payment Terms Template link on trade + invoice documents.

Lets a Quotation / Sales Order / Purchase Order / Sales Invoice / Purchase
Invoice reference a Payment Terms Template. The installment breakdown (due
dates + amounts) is derived from the template + grand total + posting date for
display; it is not snapshotted into a child table (kept deliberately simple).

Revision ID: 0027_doc_payment_terms
Revises: 0026_payment_term_label
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0027_doc_payment_terms"
down_revision: Union[str, None] = "0026_payment_term_label"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("quotations", "sales_orders", "purchase_orders", "sales_invoices", "purchase_invoices")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("payment_terms_template_id", pg.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_payment_terms", table, "payment_terms_templates",
            ["payment_terms_template_id"], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f"fk_{table}_payment_terms", table, type_="foreignkey")
        op.drop_column(table, "payment_terms_template_id")
