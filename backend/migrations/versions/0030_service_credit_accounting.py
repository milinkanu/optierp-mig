"""Service Credit accounting: prepaid/expense accounts + cost center + PI link.

Lets a Service Credit post the amortization GL on each usage
(Dr Expense / Cr Prepaid) and link to the Purchase Invoice that booked the
prepaid asset. All additive nullable FKs — no behaviour change for existing rows.

Revision ID: 0030_service_credit_accounting
Revises: 0029_service_credits
Create Date: 2026-06-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0030_service_credit_accounting"
down_revision: Union[str, None] = "0029_service_credits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("service_credits", sa.Column("purchase_invoice_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_service_credit_pi", "service_credits", "purchase_invoices",
        ["purchase_invoice_id"], ["id"], ondelete="SET NULL",
    )
    op.add_column("service_credits", sa.Column("prepaid_account_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_service_credit_prepaid_acct", "service_credits", "accounts",
        ["prepaid_account_id"], ["id"],
    )
    op.add_column("service_credits", sa.Column("expense_account_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_service_credit_expense_acct", "service_credits", "accounts",
        ["expense_account_id"], ["id"],
    )
    op.add_column("service_credits", sa.Column("cost_center_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_service_credit_cc", "service_credits", "cost_centers",
        ["cost_center_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_service_credit_cc", "service_credits", type_="foreignkey")
    op.drop_column("service_credits", "cost_center_id")
    op.drop_constraint("fk_service_credit_expense_acct", "service_credits", type_="foreignkey")
    op.drop_column("service_credits", "expense_account_id")
    op.drop_constraint("fk_service_credit_prepaid_acct", "service_credits", type_="foreignkey")
    op.drop_column("service_credits", "prepaid_account_id")
    op.drop_constraint("fk_service_credit_pi", "service_credits", type_="foreignkey")
    op.drop_column("service_credits", "purchase_invoice_id")
