"""Friendly label on payment terms template installments.

Adds ``description`` to ``payment_terms_template_details`` so each installment
can carry a plain-language label (e.g. "Advance", "Balance on delivery"),
replacing the need to reference a separate Payment Term master.

Revision ID: 0026_payment_term_label
Revises: 0025_more_info_and_dn_address
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026_payment_term_label"
down_revision: Union[str, None] = "0025_more_info_and_dn_address"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payment_terms_template_details", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("payment_terms_template_details", "description")
