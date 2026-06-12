"""Module 02 (Accounts) models — partial.

Only the masters that Module 01 needs are defined here (Account tree,
Cost Center, Fiscal Year), because company creation must seed the Chart of
Accounts and a default cost center. Transactions (GL Entry, Journal Entry,
invoices, ...) arrive with Module 02.

The account tree uses the PostgreSQL ``ltree`` extension (Section 3,
Module 02) — ``path`` is the materialised path of slugified account names.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from app.models.base import Base, CompanyScopedMixin, DocumentMixin
from app.models.types import Ltree

ROOT_TYPES = ("Asset", "Liability", "Equity", "Income", "Expense")
REPORT_TYPES = ("Balance Sheet", "Profit and Loss")

# Normal balance side per root type (Section 3, Module 02, rule 4)
ROOT_TYPE_BALANCE = {
    "Asset": "Debit",
    "Expense": "Debit",
    "Liability": "Credit",
    "Equity": "Credit",
    "Income": "Credit",
}

ROOT_TYPE_REPORT = {
    "Asset": "Balance Sheet",
    "Liability": "Balance Sheet",
    "Equity": "Balance Sheet",
    "Income": "Profit and Loss",
    "Expense": "Profit and Loss",
}

root_type_enum = Enum(*ROOT_TYPES, name="account_root_type")
report_type_enum = Enum(*REPORT_TYPES, name="account_report_type")


class Account(Base, DocumentMixin, CompanyScopedMixin):
    """Chart of Accounts node. Source: erpnext/accounts/doctype/account."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("company_id", "account_name", "parent_account_id", name="uq_account_name"),
        Index("ix_accounts_path", "path", postgresql_using="gist"),
        Index("ix_accounts_company_root", "company_id", "root_type"),
    )

    account_name: Mapped[str] = mapped_column(String(140), nullable=False)
    account_number: Mapped[str | None] = mapped_column(String(40))
    parent_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT")
    )
    root_type: Mapped[str] = mapped_column(root_type_enum, nullable=False)
    report_type: Mapped[str] = mapped_column(report_type_enum, nullable=False)
    account_type: Mapped[str | None] = mapped_column(String(60))  # Bank, Cash, Receivable, ...
    account_category: Mapped[str | None] = mapped_column(String(80))
    is_group: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    account_currency: Mapped[str | None] = mapped_column(String(3))
    freeze_account: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    path: Mapped[str] = mapped_column(Ltree, nullable=False)

    @property
    def balance_must_be(self) -> str:
        return ROOT_TYPE_BALANCE[self.root_type]


class CostCenter(Base, DocumentMixin, CompanyScopedMixin):
    """Source: erpnext/accounts/doctype/cost_center (tree)."""

    __tablename__ = "cost_centers"
    __table_args__ = (
        UniqueConstraint("company_id", "cost_center_name", "parent_cost_center_id", name="uq_cost_center"),
    )

    cost_center_name: Mapped[str] = mapped_column(String(140), nullable=False)
    parent_cost_center_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cost_centers.id", ondelete="RESTRICT")
    )
    is_group: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class FiscalYear(Base, DocumentMixin, CompanyScopedMixin):
    """Source: erpnext/accounts/doctype/fiscal_year.

    Assumption: scoped per company (ERPNext keeps fiscal years global with a
    company child table; per-company is simpler under shared-DB multi-tenancy).
    """

    __tablename__ = "fiscal_years"
    __table_args__ = (UniqueConstraint("company_id", "year", name="uq_fiscal_year"),)

    year: Mapped[str] = mapped_column(String(40), nullable=False)
    year_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    year_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    auto_created: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


# ============================================================================
# Module 02 — Accounts: masters
# ============================================================================

CHARGE_TYPES = ("Actual", "On Net Total", "On Previous Row Amount", "On Previous Row Total", "On Item Quantity")
charge_type_enum = Enum(*CHARGE_TYPES, name="tax_charge_type")

PARTY_TYPES = ("Customer", "Supplier")
party_type_enum = Enum(*PARTY_TYPES, name="party_type")

INVOICE_STATUSES = ("Draft", "Unpaid", "Partly Paid", "Paid", "Overdue", "Cancelled", "Return")
invoice_status_enum = Enum(*INVOICE_STATUSES, name="invoice_status")


class TaxRowMixin:
    """Shared columns for Sales/Purchase Taxes and Charges rows
    (source: erpnext Sales Taxes and Charges child doctype)."""

    idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    charge_type: Mapped[str] = mapped_column(charge_type_enum, nullable=False)
    row_id: Mapped[int | None] = mapped_column(Integer)  # 1-based ref for On Previous Row *
    description: Mapped[str | None] = mapped_column(String(300))
    rate: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    base_tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    base_total: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))

    @declared_attr
    def account_head_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)

    @declared_attr
    def cost_center_id(cls) -> Mapped[uuid.UUID | None]:  # noqa: N805
        return mapped_column(UUID(as_uuid=True), ForeignKey("cost_centers.id"))


class TaxTemplate(Base, DocumentMixin, CompanyScopedMixin):
    """Sales/Purchase Taxes and Charges Template (kind discriminator)."""

    __tablename__ = "tax_templates"
    __table_args__ = (UniqueConstraint("company_id", "title", "kind", name="uq_tax_template"),)

    title: Mapped[str] = mapped_column(String(140), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # sales | purchase
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))

    details: Mapped[list["TaxTemplateDetail"]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="TaxTemplateDetail.idx"
    )


class TaxTemplateDetail(Base, DocumentMixin, TaxRowMixin):
    __tablename__ = "tax_template_details"

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tax_templates.id", ondelete="CASCADE"), nullable=False
    )
    add_deduct_tax: Mapped[str] = mapped_column(
        String(10), nullable=False, default="Add", server_default=text("'Add'")
    )
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Total", server_default=text("'Total'")
    )

    template: Mapped[TaxTemplate] = relationship(back_populates="details")


class PaymentTerm(Base, DocumentMixin, CompanyScopedMixin):
    """Source: erpnext/accounts/doctype/payment_term."""

    __tablename__ = "payment_terms"
    __table_args__ = (UniqueConstraint("company_id", "term_name", name="uq_payment_term"),)

    term_name: Mapped[str] = mapped_column(String(140), nullable=False)
    invoice_portion: Mapped[Decimal] = mapped_column(
        Numeric(8, 3), nullable=False, default=100, server_default=text("100")
    )
    due_date_based_on: Mapped[str] = mapped_column(
        String(40), nullable=False, default="Day(s) after invoice date",
        server_default=text("'Day(s) after invoice date'"),
    )
    credit_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))


class PaymentTermsTemplate(Base, DocumentMixin, CompanyScopedMixin):
    __tablename__ = "payment_terms_templates"
    __table_args__ = (UniqueConstraint("company_id", "template_name", name="uq_ptt_name"),)

    template_name: Mapped[str] = mapped_column(String(140), nullable=False)

    terms: Mapped[list["PaymentTermsTemplateDetail"]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="PaymentTermsTemplateDetail.idx"
    )


class PaymentTermsTemplateDetail(Base, DocumentMixin):
    __tablename__ = "payment_terms_template_details"

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_terms_templates.id", ondelete="CASCADE"), nullable=False
    )
    payment_term_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("payment_terms.id"))
    invoice_portion: Mapped[Decimal] = mapped_column(
        Numeric(8, 3), nullable=False, default=100, server_default=text("100")
    )
    due_date_based_on: Mapped[str] = mapped_column(
        String(40), nullable=False, default="Day(s) after invoice date",
        server_default=text("'Day(s) after invoice date'"),
    )
    credit_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))

    template: Mapped[PaymentTermsTemplate] = relationship(back_populates="terms")


class ModeOfPayment(Base, DocumentMixin, CompanyScopedMixin):
    """Source: erpnext/accounts/doctype/mode_of_payment. Per-company here, so
    the default account child table collapses to a single column."""

    __tablename__ = "modes_of_payment"
    __table_args__ = (UniqueConstraint("company_id", "mode_name", name="uq_mode_of_payment"),)

    mode_name: Mapped[str] = mapped_column(String(140), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="Cash", server_default=text("'Cash'"))
    default_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Bank(Base, DocumentMixin, CompanyScopedMixin):
    __tablename__ = "banks"
    __table_args__ = (UniqueConstraint("company_id", "bank_name", name="uq_bank_name"),)

    bank_name: Mapped[str] = mapped_column(String(140), nullable=False)
    swift_number: Mapped[str | None] = mapped_column(String(40))


class BankAccount(Base, DocumentMixin, CompanyScopedMixin):
    __tablename__ = "bank_accounts"
    __table_args__ = (UniqueConstraint("company_id", "account_name", name="uq_bank_account_name"),)

    account_name: Mapped[str] = mapped_column(String(140), nullable=False)
    bank_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("banks.id"))
    gl_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"))
    account_number: Mapped[str | None] = mapped_column(String(40))
    iban: Mapped[str | None] = mapped_column(String(40))
    is_company_account: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


# ============================================================================
# Module 02 — Accounts: transactions
# ============================================================================


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


class VoucherMixin:
    """Common columns for submittable financial documents."""

    name: Mapped[str] = mapped_column(String(140), nullable=False)  # naming-series doc number
    posting_date: Mapped[date] = mapped_column(Date, nullable=False)
    workflow_state: Mapped[str | None] = mapped_column(String(100))
    remarks: Mapped[str | None] = mapped_column(Text)
    amended_from_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


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


class InvoiceMixin(VoucherMixin):
    """Shared invoice header fields (taxes_and_totals outputs)."""

    due_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    conversion_rate: Mapped[Decimal] = mapped_column(
        Numeric(21, 9), nullable=False, default=1, server_default=text("1")
    )
    total_qty: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    base_total: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    net_total: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    base_net_total: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    total_taxes_and_charges: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    base_total_taxes_and_charges: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    apply_discount_on: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Grand Total", server_default=text("'Grand Total'")
    )
    additional_discount_percentage: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, default=0, server_default=text("0")
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    grand_total: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    base_grand_total: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    rounded_total: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    rounding_adjustment: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    outstanding_amount: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    advance_paid: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    is_return: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(
        invoice_status_enum, nullable=False, default="Draft", server_default=text("'Draft'")
    )


class InvoiceItemMixin:
    """Shared invoice line fields. item_code is free-text until Module 03
    introduces the Item master (then it gains an FK)."""

    idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    item_code: Mapped[str | None] = mapped_column(String(140))
    item_name: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    qty: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=1, server_default=text("1"))
    uom: Mapped[str | None] = mapped_column(String(140))
    rate: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    amount: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    base_rate: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    base_amount: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    base_net_amount: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )

    @declared_attr
    def cost_center_id(cls) -> Mapped[uuid.UUID | None]:  # noqa: N805
        return mapped_column(UUID(as_uuid=True), ForeignKey("cost_centers.id"))


class SalesInvoice(Base, DocumentMixin, CompanyScopedMixin, InvoiceMixin):
    """Source: erpnext/accounts/doctype/sales_invoice."""

    __tablename__ = "sales_invoices"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_sales_invoice_name"),
        Index("ix_sales_invoices_company_docstatus", "company_id", "docstatus"),
        Index("ix_sales_invoices_customer", "customer_id"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    debit_to_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    return_against_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sales_invoices.id"))
    update_stock: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))

    items: Mapped[list["SalesInvoiceItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="SalesInvoiceItem.idx"
    )
    taxes: Mapped[list["SalesInvoiceTax"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="SalesInvoiceTax.idx"
    )


class SalesInvoiceItem(Base, DocumentMixin, InvoiceItemMixin):
    __tablename__ = "sales_invoice_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_invoices.id", ondelete="CASCADE"), nullable=False
    )
    income_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )

    invoice: Mapped[SalesInvoice] = relationship(back_populates="items")


class SalesInvoiceTax(Base, DocumentMixin, TaxRowMixin):
    __tablename__ = "sales_invoice_taxes"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_invoices.id", ondelete="CASCADE"), nullable=False
    )

    invoice: Mapped[SalesInvoice] = relationship(back_populates="taxes")


class PurchaseInvoice(Base, DocumentMixin, CompanyScopedMixin, InvoiceMixin):
    """Source: erpnext/accounts/doctype/purchase_invoice."""

    __tablename__ = "purchase_invoices"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_purchase_invoice_name"),
        Index("ix_purchase_invoices_company_docstatus", "company_id", "docstatus"),
        Index("ix_purchase_invoices_supplier", "supplier_id"),
    )

    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False)
    credit_to_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    return_against_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_invoices.id")
    )
    bill_no: Mapped[str | None] = mapped_column(String(140))  # supplier's invoice number
    bill_date: Mapped[date | None] = mapped_column(Date)

    items: Mapped[list["PurchaseInvoiceItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="PurchaseInvoiceItem.idx"
    )
    taxes: Mapped[list["PurchaseInvoiceTax"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="PurchaseInvoiceTax.idx"
    )


class PurchaseInvoiceItem(Base, DocumentMixin, InvoiceItemMixin):
    __tablename__ = "purchase_invoice_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_invoices.id", ondelete="CASCADE"), nullable=False
    )
    expense_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )

    invoice: Mapped[PurchaseInvoice] = relationship(back_populates="items")


class PurchaseInvoiceTax(Base, DocumentMixin, TaxRowMixin):
    __tablename__ = "purchase_invoice_taxes"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_invoices.id", ondelete="CASCADE"), nullable=False
    )
    add_deduct_tax: Mapped[str] = mapped_column(
        String(10), nullable=False, default="Add", server_default=text("'Add'")
    )
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Total", server_default=text("'Total'")
    )

    invoice: Mapped[PurchaseInvoice] = relationship(back_populates="taxes")


class PaymentEntry(Base, DocumentMixin, CompanyScopedMixin, VoucherMixin):
    """Source: erpnext/accounts/doctype/payment_entry."""

    __tablename__ = "payment_entries"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_payment_entry_name"),
        Index("ix_payment_entries_company_docstatus", "company_id", "docstatus"),
    )

    payment_type: Mapped[str] = mapped_column(String(20), nullable=False)  # Receive | Pay | Internal Transfer
    party_type: Mapped[str | None] = mapped_column(party_type_enum)
    party_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    paid_from_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    paid_to_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    paid_from_account_currency: Mapped[str | None] = mapped_column(String(3))
    paid_to_account_currency: Mapped[str | None] = mapped_column(String(3))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    received_amount: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    source_exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(21, 9), nullable=False, default=1, server_default=text("1")
    )
    target_exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(21, 9), nullable=False, default=1, server_default=text("1")
    )
    total_allocated_amount: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    unallocated_amount: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    mode_of_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modes_of_payment.id")
    )
    reference_no: Mapped[str | None] = mapped_column(String(140))  # cheque / txn ref
    reference_date: Mapped[date | None] = mapped_column(Date)
    clearance_date: Mapped[date | None] = mapped_column(Date)  # bank reconciliation
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Draft", server_default=text("'Draft'"))

    references: Mapped[list["PaymentEntryReference"]] = relationship(
        back_populates="payment_entry", cascade="all, delete-orphan", order_by="PaymentEntryReference.idx"
    )
    deductions: Mapped[list["PaymentEntryDeduction"]] = relationship(
        back_populates="payment_entry", cascade="all, delete-orphan", order_by="PaymentEntryDeduction.idx"
    )


class PaymentEntryReference(Base, DocumentMixin):
    __tablename__ = "payment_entry_references"

    payment_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_entries.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    reference_doctype: Mapped[str] = mapped_column(String(60), nullable=False)  # Sales Invoice / Purchase Invoice
    reference_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reference_name: Mapped[str | None] = mapped_column(String(140))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    outstanding_amount: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    allocated_amount: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )

    payment_entry: Mapped[PaymentEntry] = relationship(back_populates="references")


class PaymentEntryDeduction(Base, DocumentMixin):
    __tablename__ = "payment_entry_deductions"

    payment_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_entries.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cost_centers.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    description: Mapped[str | None] = mapped_column(String(300))

    payment_entry: Mapped[PaymentEntry] = relationship(back_populates="deductions")


class Budget(Base, DocumentMixin, CompanyScopedMixin):
    """Source: erpnext/accounts/doctype/budget (annual, against cost center)."""

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("company_id", "fiscal_year_id", "cost_center_id", name="uq_budget"),
    )

    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fiscal_years.id"), nullable=False
    )
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cost_centers.id"))
    action_if_annual_budget_exceeded: Mapped[str] = mapped_column(
        String(10), nullable=False, default="Warn", server_default=text("'Warn'")
    )  # Stop | Warn | Ignore

    accounts: Mapped[list["BudgetAccount"]] = relationship(
        back_populates="budget", cascade="all, delete-orphan"
    )


class BudgetAccount(Base, DocumentMixin):
    __tablename__ = "budget_accounts"

    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    budget_amount: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False)

    budget: Mapped[Budget] = relationship(back_populates="accounts")


class PeriodClosingVoucher(Base, DocumentMixin, CompanyScopedMixin, VoucherMixin):
    """Source: erpnext/accounts/doctype/period_closing_voucher.

    On submit: transfers P&L balances up to posting_date into the closing
    (retained earnings) account and freezes GL postings on or before that date.
    """

    __tablename__ = "period_closing_vouchers"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_pcv_name"),)

    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fiscal_years.id"), nullable=False
    )
    closing_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
