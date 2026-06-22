"""Email send log + party email.

Adds ``email_logs`` (one row per outbound email, for the send audit trail) and an
optional ``email_id`` on customers + suppliers (so documents/statements can be
emailed to the party). Company-scoped reads filter by company_id explicitly
(mirrors bank_transactions — no RLS policy).

Revision ID: 0046_email_log_and_party_email
Revises: 0045_tax_category_inter_state
Create Date: 2026-06-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0046_email_log_and_party_email"
down_revision: Union[str, None] = "0045_tax_category_inter_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("modified", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("docstatus", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("owner", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("modified_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "company_id", UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("to_addresses", JSONB(), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("reference_doctype", sa.String(length=100), nullable=True),
        sa.Column("reference_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),  # Sent | Failed
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_email_logs_company_id", "email_logs", ["company_id"])
    op.create_index("ix_email_logs_reference", "email_logs", ["reference_doctype", "reference_id"])

    op.add_column("customers", sa.Column("email_id", sa.String(length=140), nullable=True))
    op.add_column("suppliers", sa.Column("email_id", sa.String(length=140), nullable=True))


def downgrade() -> None:
    op.drop_column("suppliers", "email_id")
    op.drop_column("customers", "email_id")
    op.drop_index("ix_email_logs_reference", table_name="email_logs")
    op.drop_index("ix_email_logs_company_id", table_name="email_logs")
    op.drop_table("email_logs")
