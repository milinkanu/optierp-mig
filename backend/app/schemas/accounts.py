"""Module 02 — Accounts Pydantic schemas."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import DocumentMeta, ORMModel

# --- Customer / Supplier (stubs, extended in Modules 04/05) -----------------------


class CustomerCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=140)
    customer_type: str = "Company"
    tax_id: str | None = None
    default_currency: str | None = None
    receivable_account_id: uuid.UUID | None = None
    credit_limit: Decimal | None = None
    tax_category_id: uuid.UUID | None = None


class CustomerResponse(DocumentMeta):
    customer_name: str
    customer_type: str
    tax_id: str | None
    default_currency: str | None
    receivable_account_id: uuid.UUID | None
    credit_limit: Decimal | None
    tax_category_id: uuid.UUID | None
    disabled: bool
    company_id: uuid.UUID


class SupplierCreate(BaseModel):
    supplier_name: str = Field(min_length=1, max_length=140)
    supplier_type: str = "Company"
    tax_id: str | None = None
    default_currency: str | None = None
    payable_account_id: uuid.UUID | None = None
    tax_category_id: uuid.UUID | None = None


class SupplierResponse(DocumentMeta):
    supplier_name: str
    supplier_type: str
    tax_id: str | None
    default_currency: str | None
    payable_account_id: uuid.UUID | None
    tax_category_id: uuid.UUID | None
    disabled: bool
    company_id: uuid.UUID


# --- Account (full CRUD arrives with this module) ----------------------------------


class AccountCreate(BaseModel):
    account_name: str = Field(min_length=1, max_length=140)
    parent_account_id: uuid.UUID
    account_number: str | None = None
    account_type: str | None = None
    is_group: bool = False
    account_currency: str | None = None


class AccountResponse(DocumentMeta):
    account_name: str
    account_number: str | None
    parent_account_id: uuid.UUID | None
    root_type: str
    report_type: str
    account_type: str | None
    is_group: bool
    account_currency: str | None
    freeze_account: bool
    disabled: bool
    path: str
    company_id: uuid.UUID


# --- Tax categories ------------------------------------------------------------------


class TaxCategoryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    disabled: bool = False


class TaxCategoryResponse(DocumentMeta):
    title: str
    disabled: bool
    company_id: uuid.UUID


# --- Tax templates -------------------------------------------------------------------


class TaxRowIn(BaseModel):
    charge_type: str = "On Net Total"
    rate: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")  # input for charge_type Actual
    row_id: int | None = None
    account_head_id: uuid.UUID
    cost_center_id: uuid.UUID | None = None
    description: str | None = None
    add_deduct_tax: str = "Add"
    category: str = "Total"


class TaxTemplateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    kind: str = Field(pattern="^(sales|purchase)$")
    is_default: bool = False
    tax_category_id: uuid.UUID | None = None
    details: list[TaxRowIn] = Field(default_factory=list)


class TaxTemplateDetailResponse(DocumentMeta):
    idx: int
    charge_type: str
    rate: Decimal
    tax_amount: Decimal
    row_id: int | None
    account_head_id: uuid.UUID
    cost_center_id: uuid.UUID | None
    description: str | None
    add_deduct_tax: str
    category: str


class TaxTemplateResponse(DocumentMeta):
    title: str
    kind: str
    is_default: bool
    disabled: bool
    tax_category_id: uuid.UUID | None
    company_id: uuid.UUID
    details: list[TaxTemplateDetailResponse]


# --- Journal Entry --------------------------------------------------------------------


class JournalEntryAccountIn(BaseModel):
    account_id: uuid.UUID
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    party_type: str | None = None
    party_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    account_currency: str | None = None
    exchange_rate: Decimal = Decimal("1")
    debit_in_account_currency: Decimal | None = None
    credit_in_account_currency: Decimal | None = None
    reference_type: str | None = None
    reference_id: uuid.UUID | None = None
    user_remark: str | None = None

    @field_validator("debit", "credit")
    @classmethod
    def non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("must be >= 0")
        return v


class JournalEntryCreate(BaseModel):
    posting_date: date
    voucher_type: str = "Journal Entry"
    remarks: str | None = None
    multi_currency: bool = False
    accounts: list[JournalEntryAccountIn] = Field(min_length=2)


class JournalEntryAccountResponse(DocumentMeta):
    idx: int
    account_id: uuid.UUID
    debit: Decimal
    credit: Decimal
    party_type: str | None
    party_id: uuid.UUID | None
    cost_center_id: uuid.UUID | None
    reference_type: str | None
    reference_id: uuid.UUID | None
    user_remark: str | None


class JournalEntryResponse(DocumentMeta):
    name: str
    posting_date: date
    voucher_type: str
    total_debit: Decimal
    total_credit: Decimal
    clearance_date: date | None
    remarks: str | None
    workflow_state: str | None
    company_id: uuid.UUID
    accounts: list[JournalEntryAccountResponse]


class JournalEntryListItem(ORMModel):
    id: uuid.UUID
    name: str
    posting_date: date
    voucher_type: str
    total_debit: Decimal
    docstatus: int


# --- Invoices ---------------------------------------------------------------------------


class InvoiceItemIn(BaseModel):
    item_code: str | None = None
    item_name: str = Field(min_length=1, max_length=140)
    description: str | None = None
    qty: Decimal = Field(gt=0, default=Decimal("1"))
    uom: str | None = None
    rate: Decimal = Field(ge=0, default=Decimal("0"))
    cost_center_id: uuid.UUID | None = None
    # sales: income account; purchase: expense account (falls back to company default)
    account_id: uuid.UUID | None = None
    # Module 03-05 cycle links (all optional; free-text items still work)
    item_id: uuid.UUID | None = None
    sales_order_item_id: uuid.UUID | None = None  # sales invoices only
    delivery_note_item_id: uuid.UUID | None = None  # sales invoices only
    purchase_order_item_id: uuid.UUID | None = None  # purchase invoices only
    purchase_receipt_item_id: uuid.UUID | None = None  # purchase invoices only


class InvoiceCreateBase(BaseModel):
    posting_date: date
    due_date: date | None = None
    currency: str | None = None  # defaults to company currency
    conversion_rate: Decimal = Field(gt=0, default=Decimal("1"))
    apply_discount_on: str = "Grand Total"
    additional_discount_percentage: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    remarks: str | None = None
    items: list[InvoiceItemIn] = Field(min_length=1)
    taxes: list[TaxRowIn] = Field(default_factory=list)
    tax_template_id: uuid.UUID | None = None  # alternative to inline taxes
    is_return: bool = False
    return_against_id: uuid.UUID | None = None


class SalesInvoiceCreate(InvoiceCreateBase):
    customer_id: uuid.UUID
    debit_to_id: uuid.UUID | None = None  # defaults from customer/company
    po_no: str | None = None
    po_date: date | None = None
    terms: str | None = None
    customer_address_id: uuid.UUID | None = None
    shipping_address_id: uuid.UUID | None = None
    contact_person_id: uuid.UUID | None = None


class PurchaseInvoiceCreate(InvoiceCreateBase):
    supplier_id: uuid.UUID
    credit_to_id: uuid.UUID | None = None
    bill_no: str | None = None
    bill_date: date | None = None
    terms: str | None = None
    supplier_address_id: uuid.UUID | None = None
    shipping_address_id: uuid.UUID | None = None
    contact_person_id: uuid.UUID | None = None


class InvoiceItemResponse(DocumentMeta):
    idx: int
    item_code: str | None
    item_name: str
    qty: Decimal
    uom: str | None
    rate: Decimal
    amount: Decimal
    net_amount: Decimal
    base_net_amount: Decimal
    cost_center_id: uuid.UUID | None
    item_id: uuid.UUID | None = None
    sales_order_item_id: uuid.UUID | None = None
    delivery_note_item_id: uuid.UUID | None = None
    purchase_order_item_id: uuid.UUID | None = None
    purchase_receipt_item_id: uuid.UUID | None = None


class InvoiceTaxResponse(DocumentMeta):
    idx: int
    charge_type: str
    rate: Decimal
    row_id: int | None
    account_head_id: uuid.UUID
    description: str | None
    tax_amount: Decimal
    total: Decimal
    base_tax_amount: Decimal
    base_total: Decimal


class InvoiceResponseBase(DocumentMeta):
    name: str
    posting_date: date
    due_date: date | None
    currency: str
    conversion_rate: Decimal
    total_qty: Decimal
    total: Decimal
    net_total: Decimal
    base_net_total: Decimal
    total_taxes_and_charges: Decimal
    discount_amount: Decimal
    grand_total: Decimal
    base_grand_total: Decimal
    rounded_total: Decimal
    rounding_adjustment: Decimal
    outstanding_amount: Decimal
    advance_paid: Decimal
    is_return: bool
    status: str
    remarks: str | None
    workflow_state: str | None
    company_id: uuid.UUID
    items: list[InvoiceItemResponse]
    taxes: list[InvoiceTaxResponse]


class SalesInvoiceResponse(InvoiceResponseBase):
    customer_id: uuid.UUID
    customer_name: str | None = None
    debit_to_id: uuid.UUID
    return_against_id: uuid.UUID | None
    po_no: str | None = None
    po_date: date | None = None
    terms: str | None = None
    customer_address_id: uuid.UUID | None = None
    shipping_address_id: uuid.UUID | None = None
    contact_person_id: uuid.UUID | None = None


class PurchaseInvoiceResponse(InvoiceResponseBase):
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    credit_to_id: uuid.UUID
    return_against_id: uuid.UUID | None
    bill_no: str | None
    bill_date: date | None
    terms: str | None = None
    supplier_address_id: uuid.UUID | None = None
    shipping_address_id: uuid.UUID | None = None
    contact_person_id: uuid.UUID | None = None


class InvoiceListItem(ORMModel):
    id: uuid.UUID
    name: str
    posting_date: date
    due_date: date | None = None
    currency: str | None = None
    # one of the two is set, depending on the list (sales vs purchase)
    customer_name: str | None = None
    supplier_name: str | None = None
    grand_total: Decimal
    outstanding_amount: Decimal
    status: str
    docstatus: int


# --- Payment Entry ------------------------------------------------------------------------


class PaymentReferenceIn(BaseModel):
    reference_doctype: str = Field(pattern="^(Sales Invoice|Purchase Invoice)$")
    reference_id: uuid.UUID
    allocated_amount: Decimal = Field(gt=0)


class PaymentDeductionIn(BaseModel):
    account_id: uuid.UUID
    cost_center_id: uuid.UUID | None = None
    amount: Decimal
    description: str | None = None


class PaymentEntryCreate(BaseModel):
    posting_date: date
    payment_type: str = Field(pattern="^(Receive|Pay|Internal Transfer)$")
    party_type: str | None = None
    party_id: uuid.UUID | None = None
    paid_from_id: uuid.UUID | None = None  # defaults to party account for Receive
    paid_to_id: uuid.UUID | None = None  # defaults to party account for Pay
    paid_amount: Decimal = Field(gt=0)
    received_amount: Decimal | None = None
    source_exchange_rate: Decimal = Field(gt=0, default=Decimal("1"))
    target_exchange_rate: Decimal = Field(gt=0, default=Decimal("1"))
    mode_of_payment_id: uuid.UUID | None = None
    reference_no: str | None = None
    reference_date: date | None = None
    remarks: str | None = None
    references: list[PaymentReferenceIn] = Field(default_factory=list)
    deductions: list[PaymentDeductionIn] = Field(default_factory=list)


class PaymentReferenceResponse(DocumentMeta):
    idx: int
    reference_doctype: str
    reference_id: uuid.UUID
    reference_name: str | None
    total_amount: Decimal
    outstanding_amount: Decimal
    allocated_amount: Decimal


class PaymentEntryResponse(DocumentMeta):
    name: str
    posting_date: date
    payment_type: str
    party_type: str | None
    party_id: uuid.UUID | None
    paid_from_id: uuid.UUID
    paid_to_id: uuid.UUID
    paid_amount: Decimal
    received_amount: Decimal
    total_allocated_amount: Decimal
    unallocated_amount: Decimal
    reference_no: str | None
    reference_date: date | None
    clearance_date: date | None
    status: str
    remarks: str | None
    company_id: uuid.UUID
    references: list[PaymentReferenceResponse]


class PaymentEntryListItem(ORMModel):
    id: uuid.UUID
    name: str
    posting_date: date
    payment_type: str
    party_type: str | None = None
    party_id: uuid.UUID | None = None
    paid_amount: Decimal
    unallocated_amount: Decimal | None = None
    reference_no: str | None = None
    status: str
    docstatus: int


# --- Period Closing -------------------------------------------------------------------------


class PeriodClosingCreate(BaseModel):
    posting_date: date
    fiscal_year_id: uuid.UUID
    closing_account_id: uuid.UUID
    remarks: str | None = None


class PeriodClosingResponse(DocumentMeta):
    name: str
    posting_date: date
    fiscal_year_id: uuid.UUID
    closing_account_id: uuid.UUID
    remarks: str | None
    company_id: uuid.UUID


# --- GL / Reports ----------------------------------------------------------------------------


class GLEntryResponse(ORMModel):
    id: uuid.UUID
    posting_date: date
    account_id: uuid.UUID
    party_type: str | None
    party_id: uuid.UUID | None
    debit: Decimal
    credit: Decimal
    voucher_type: str
    voucher_no: str
    against: str | None
    is_cancellation: bool
    remarks: str | None


class TrialBalanceRow(BaseModel):
    account_id: uuid.UUID
    account_name: str
    root_type: str
    is_group: bool
    path: str
    opening_debit: Decimal
    opening_credit: Decimal
    debit: Decimal
    credit: Decimal
    closing_debit: Decimal
    closing_credit: Decimal


class FinancialStatementRow(BaseModel):
    account_id: uuid.UUID | None
    account_name: str
    root_type: str | None
    is_group: bool
    indent: int
    amount: Decimal


class AgingRow(BaseModel):
    party_id: uuid.UUID
    party_name: str
    voucher_no: str
    voucher_id: uuid.UUID
    posting_date: date
    due_date: date | None
    grand_total: Decimal
    outstanding_amount: Decimal
    age_days: int
    bucket_0_30: Decimal
    bucket_31_60: Decimal
    bucket_61_90: Decimal
    bucket_90_plus: Decimal


class CashFlowRow(BaseModel):
    section: str
    label: str
    amount: Decimal


# --- Budget ----------------------------------------------------------------------------------


class BudgetAccountIn(BaseModel):
    account_id: uuid.UUID
    budget_amount: Decimal = Field(gt=0)


class BudgetCreate(BaseModel):
    fiscal_year_id: uuid.UUID
    cost_center_id: uuid.UUID | None = None  # None = company-wide budget
    action_if_annual_budget_exceeded: str = Field(default="Warn", pattern="^(Stop|Warn|Ignore)$")
    accounts: list[BudgetAccountIn] = Field(min_length=1)


class BudgetAccountResponse(DocumentMeta):
    account_id: uuid.UUID
    budget_amount: Decimal


class BudgetResponse(DocumentMeta):
    fiscal_year_id: uuid.UUID
    cost_center_id: uuid.UUID | None
    action_if_annual_budget_exceeded: str
    company_id: uuid.UUID
    accounts: list[BudgetAccountResponse]


# --- Payment Reconciliation --------------------------------------------------------------------


class UnreconciledInvoiceRow(BaseModel):
    invoice_type: str  # Sales Invoice | Purchase Invoice
    invoice_id: uuid.UUID
    name: str
    posting_date: date
    grand_total: Decimal
    outstanding_amount: Decimal


class UnreconciledPaymentRow(BaseModel):
    payment_entry_id: uuid.UUID
    name: str
    posting_date: date
    paid_amount: Decimal
    unallocated_amount: Decimal


class UnreconciledResponse(BaseModel):
    invoices: list[UnreconciledInvoiceRow]
    payments: list[UnreconciledPaymentRow]


class ReconcileAllocationIn(BaseModel):
    payment_entry_id: uuid.UUID
    invoice_type: str = Field(pattern="^(Sales Invoice|Purchase Invoice)$")
    invoice_id: uuid.UUID
    allocated_amount: Decimal = Field(gt=0)


class PaymentReconciliationIn(BaseModel):
    party_type: str = Field(pattern="^(Customer|Supplier)$")
    party_id: uuid.UUID
    allocations: list[ReconcileAllocationIn] = Field(min_length=1)


class ReconciledInvoiceRow(BaseModel):
    invoice_id: uuid.UUID
    name: str
    outstanding_amount: Decimal
    status: str


class PaymentReconciliationResponse(BaseModel):
    allocations_applied: int
    invoices: list[ReconciledInvoiceRow]


# --- Bank Reconciliation Statement ---------------------------------------------------------------


class BankReconUnclearedRow(BaseModel):
    voucher_type: str  # Payment Entry | Journal Entry
    voucher_id: uuid.UUID
    voucher_no: str
    posting_date: date
    reference_no: str | None
    # signed against the bank account: positive = debit (inflow) not yet cleared
    amount: Decimal


class BankReconciliationReport(BaseModel):
    gl_account_id: uuid.UUID
    as_of: date
    balance_per_books: Decimal
    uncleared_amount: Decimal
    balance_per_bank: Decimal
    uncleared_entries: list[BankReconUnclearedRow]
