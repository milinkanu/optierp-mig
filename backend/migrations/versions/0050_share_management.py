"""Share Management: cap-table register (share types, shareholders, transfers).

Standalone bookkeeping of who owns what — NO GL effect. ``share_types`` and
``shareholders`` are engine masters; ``share_transfers`` is the bespoke submittable
ledger that holdings are derived from. Company-scoped; reads filter by company_id
explicitly (no RLS, mirrors the rest of the accounting tables).

Revision ID: 0050_share_management
Revises: 0049_subscription
Create Date: 2026-06-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0050_share_management"
down_revision: Union[str, None] = "0049_subscription"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _meta_columns() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "share_types",
        *_meta_columns(),
        sa.Column("share_type_name", sa.String(length=140), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("par_value", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.UniqueConstraint("company_id", "share_type_name", name="uq_share_type_name"),
    )
    op.create_index("ix_share_types_company_id", "share_types", ["company_id"])

    op.create_table(
        "shareholders",
        *_meta_columns(),
        sa.Column("shareholder_name", sa.String(length=140), nullable=False),
        sa.Column("contact_id", UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("folio_no", sa.String(length=140), nullable=True),
        sa.Column("disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.UniqueConstraint("company_id", "shareholder_name", name="uq_shareholder_name"),
    )
    op.create_index("ix_shareholders_company_id", "shareholders", ["company_id"])

    op.create_table(
        "share_transfers",
        *_meta_columns(),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("transfer_type", sa.String(length=10), nullable=False),
        sa.Column("from_shareholder_id", UUID(as_uuid=True), sa.ForeignKey("shareholders.id"), nullable=True),
        sa.Column("to_shareholder_id", UUID(as_uuid=True), sa.ForeignKey("shareholders.id"), nullable=True),
        sa.Column("share_type_id", UUID(as_uuid=True), sa.ForeignKey("share_types.id"), nullable=False),
        sa.Column("no_of_shares", sa.Integer(), nullable=False),
        sa.Column("rate", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("amount", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("transfer_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'Draft'"), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.UniqueConstraint("company_id", "name", name="uq_share_transfer_name"),
    )
    op.create_index("ix_share_transfers_company_id", "share_transfers", ["company_id"])
    # the cap-table/ledger reads scan submitted transfers per company by share type
    op.create_index(
        "ix_share_transfers_lookup", "share_transfers",
        ["company_id", "docstatus", "share_type_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_share_transfers_lookup", table_name="share_transfers")
    op.drop_index("ix_share_transfers_company_id", table_name="share_transfers")
    op.drop_table("share_transfers")
    op.drop_index("ix_shareholders_company_id", table_name="shareholders")
    op.drop_table("shareholders")
    op.drop_index("ix_share_types_company_id", table_name="share_types")
    op.drop_table("share_types")
