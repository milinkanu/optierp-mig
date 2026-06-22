"""Module 02 (Accounts) — Share Management (cap table).

Source: erpnext/accounts/doctype/{share_type, shareholder, share_transfer}, simplified.

A **Share Type** and **Shareholder** are engine masters; a **Share Transfer** is a
bespoke submittable document (Issue / Transfer / Buyback). There is **no GL posting** —
this is a standalone register of who owns what (share capital still hits the GL via a
normal Journal Entry, separately).

Key design call: a shareholder's holding is **derived** from the submitted Share
Transfers (append-only ledger), never stored on the Shareholder — exactly like AR aging
is derived from the GL rather than a second ledger (master §3.1 anti-drift). So cancel
just flips ``docstatus`` and the balance recomputes; there are no reversal rows and no
``share_balance`` child to keep in sync.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CompanyScopedMixin, DocumentMixin

# kinds of share movement
TRANSFER_TYPES = ("Issue", "Transfer", "Buyback")
SHARE_TRANSFER_STATUSES = ("Draft", "Submitted", "Cancelled")


class ShareType(Base, DocumentMixin, CompanyScopedMixin):
    """A class of share (Equity, Preference, …) — engine master."""

    __tablename__ = "share_types"
    __table_args__ = (UniqueConstraint("company_id", "share_type_name", name="uq_share_type_name"),)

    share_type_name: Mapped[str] = mapped_column(String(140), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3))
    par_value: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )  # nominal/face value per share (informational)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class Shareholder(Base, DocumentMixin, CompanyScopedMixin):
    """A shareholding party — engine master. Holdings are derived from Share Transfers,
    not stored here (so there is no balance child to drift)."""

    __tablename__ = "shareholders"
    __table_args__ = (UniqueConstraint("company_id", "shareholder_name", name="uq_shareholder_name"),)

    shareholder_name: Mapped[str] = mapped_column(String(140), nullable=False)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL")
    )
    folio_no: Mapped[str | None] = mapped_column(String(140))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class ShareTransfer(Base, DocumentMixin, CompanyScopedMixin):
    """Issue / Transfer / Buyback of shares — bespoke submittable document (no GL).

    * **Issue** — the company mints new shares: ``to`` set, ``from`` null (increases issued).
    * **Transfer** — holder → holder: both set.
    * **Buyback** — holder → company, shares retired: ``from`` set, ``to`` null (decreases issued).

    On submit the ``from`` holder's *derived* balance is validated to cover the shares.
    """

    __tablename__ = "share_transfers"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_share_transfer_name"),)

    name: Mapped[str] = mapped_column(String(140), nullable=False)  # naming-series doc number
    transfer_type: Mapped[str] = mapped_column(String(10), nullable=False)  # Issue | Transfer | Buyback
    from_shareholder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shareholders.id")
    )
    to_shareholder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shareholders.id")
    )
    share_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("share_types.id"), nullable=False
    )
    no_of_shares: Mapped[int] = mapped_column(Integer, nullable=False)  # whole shares
    rate: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    amount: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )  # = no_of_shares × rate (stored for the ledger)
    transfer_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Draft", server_default=text("'Draft'")
    )  # Draft | Submitted | Cancelled (tracks docstatus)
    remarks: Mapped[str | None] = mapped_column(Text)

    from_shareholder = relationship("Shareholder", foreign_keys=[from_shareholder_id], lazy="joined", viewonly=True)
    to_shareholder = relationship("Shareholder", foreign_keys=[to_shareholder_id], lazy="joined", viewonly=True)
    share_type = relationship("ShareType", lazy="joined", viewonly=True)

    @property
    def from_shareholder_name(self) -> str | None:
        return self.from_shareholder.shareholder_name if self.from_shareholder else None

    @property
    def to_shareholder_name(self) -> str | None:
        return self.to_shareholder.shareholder_name if self.to_shareholder else None

    @property
    def share_type_name(self) -> str | None:
        return self.share_type.share_type_name if self.share_type else None
