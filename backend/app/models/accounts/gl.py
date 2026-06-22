"""Module 02 (Accounts) — General Ledger + Journal Entry."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CompanyScopedMixin, DocumentMixin

from app.models.accounts.common import (
    VoucherMixin,
    party_type_enum,
)

class GLEntry(Base, CompanyScopedMixin):
    """Immutable double-entry ledger (Section 3, Module 02 rule 1).

    INSERT-only: a DB trigger blocks UPDATE/DELETE, and a deferred constraint
    trigger validates debit == credit per voucher at commit. Cancellation
    writes reversing entries (assumption: ERPNext flips an is_cancelled flag;
    reversal entries keep the ledger strictly append-only).

    Written exclusively through app.services.gl.make_gl_entries.
    """

    __tablename__ = "gl_entries"
    __table_args__ = (
        Index("ix_gl_entries_voucher", "voucher_type", "voucher_id"),
        Index("ix_gl_entries_account_date", "account_id", "posting_date"),
        Index("ix_gl_entries_party", "party_type", "party_id"),
        Index("ix_gl_entries_company_date", "company_id", "posting_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    creation: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    owner: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    posting_date: Mapped[date] = mapped_column(Date, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    party_type: Mapped[str | None] = mapped_column(party_type_enum)
    party_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cost_centers.id"))

    # Base (company currency) amounts — the ledger always posts in company currency
    debit: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    credit: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    # Transaction-currency amounts (multi-currency, Module 02 rule 5)
    account_currency: Mapped[str | None] = mapped_column(String(3))
    debit_in_account_currency: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    credit_in_account_currency: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )

    voucher_type: Mapped[str] = mapped_column(String(60), nullable=False)
    voucher_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    voucher_no: Mapped[str] = mapped_column(String(140), nullable=False)
    against: Mapped[str | None] = mapped_column(String(300))  # counterpart account names
    against_voucher_type: Mapped[str | None] = mapped_column(String(60))
    against_voucher_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    fiscal_year_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fiscal_years.id"))
    is_opening: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    is_cancellation: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    remarks: Mapped[str | None] = mapped_column(Text)


class JournalEntry(Base, DocumentMixin, CompanyScopedMixin, VoucherMixin):
    """Source: erpnext/accounts/doctype/journal_entry."""

    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_journal_entry_name"),
        Index("ix_journal_entries_company_docstatus", "company_id", "docstatus"),
    )

    voucher_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="Journal Entry", server_default=text("'Journal Entry'")
    )
    total_debit: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    total_credit: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    multi_currency: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    clearance_date: Mapped[date | None] = mapped_column(Date)  # bank reconciliation

    accounts: Mapped[list["JournalEntryAccount"]] = relationship(
        back_populates="journal_entry", cascade="all, delete-orphan", order_by="JournalEntryAccount.idx"
    )


class JournalEntryAccount(Base, DocumentMixin):
    __tablename__ = "journal_entry_accounts"

    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    party_type: Mapped[str | None] = mapped_column(party_type_enum)
    party_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cost_centers.id"))
    account_currency: Mapped[str | None] = mapped_column(String(3))
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(21, 9), nullable=False, default=1, server_default=text("1"))
    debit_in_account_currency: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    credit_in_account_currency: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    debit: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    credit: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    reference_type: Mapped[str | None] = mapped_column(String(60))  # e.g. Sales Invoice
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_remark: Mapped[str | None] = mapped_column(Text)

    journal_entry: Mapped[JournalEntry] = relationship(back_populates="accounts")


