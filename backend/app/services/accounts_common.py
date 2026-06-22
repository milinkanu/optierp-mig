"""Shared helpers for Module 02 document services."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.accounts import PurchaseInvoice, SalesInvoice
from app.models.buying import Supplier
from app.models.core import Company
from app.models.selling import Customer

ZERO = Decimal("0")

# ERPNext v15 default naming series per voucher
NAMING_SERIES = {
    "Journal Entry": "ACC-JV-.YYYY.-",
    "Sales Invoice": "ACC-SINV-.YYYY.-",
    "Purchase Invoice": "ACC-PINV-.YYYY.-",
    "Payment Entry": "ACC-PAY-.YYYY.-",
    "Period Closing Voucher": "ACC-PCV-.YYYY.-",
    "Bank Transaction": "ACC-BTN-.YYYY.-",
}


async def get_company(db: AsyncSession, company_id: uuid.UUID | None) -> Company:
    if company_id is None:
        raise ValidationError("An active company is required")
    company = await db.get(Company, company_id)
    if company is None:
        raise NotFoundError("Company not found")
    return company


async def get_customer(db: AsyncSession, customer_id: uuid.UUID, company_id: uuid.UUID) -> Customer:
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.company_id != company_id:
        raise NotFoundError("Customer not found")
    if customer.disabled:
        raise ValidationError("Customer is disabled", field="customer_id")
    return customer


async def get_supplier(db: AsyncSession, supplier_id: uuid.UUID, company_id: uuid.UUID) -> Supplier:
    supplier = await db.get(Supplier, supplier_id)
    if supplier is None or supplier.company_id != company_id:
        raise NotFoundError("Supplier not found")
    if supplier.disabled:
        raise ValidationError("Supplier is disabled", field="supplier_id")
    return supplier


def get_receivable_account(company: Company, customer: Customer) -> uuid.UUID:
    account_id = customer.receivable_account_id or company.default_receivable_account_id
    if account_id is None:
        raise ValidationError(
            "No receivable account configured (customer or company default)", field="debit_to_id"
        )
    return account_id


def get_payable_account(company: Company, supplier: Supplier) -> uuid.UUID:
    account_id = supplier.payable_account_id or company.default_payable_account_id
    if account_id is None:
        raise ValidationError(
            "No payable account configured (supplier or company default)", field="credit_to_id"
        )
    return account_id


from sqlalchemy import select  # noqa: E402


async def item_tax_rates(db: AsyncSession, payload_items: list) -> dict[uuid.UUID, dict]:
    """Map each invoice line's item to its Item Tax Template rates
    ({item_id: {tax_account_head_id: rate}}), so the taxes engine can apply a
    per-item GST rate. Items without a template are absent (use the row rate)."""
    from app.models.accounts import ItemTaxTemplateDetail
    from app.models.stock import Item

    item_ids = {i.item_id for i in payload_items if getattr(i, "item_id", None) is not None}
    if not item_ids:
        return {}
    tmpl_by_item = dict(
        (
            await db.execute(
                select(Item.id, Item.item_tax_template_id).where(
                    Item.id.in_(item_ids), Item.item_tax_template_id.isnot(None)
                )
            )
        ).all()
    )
    if not tmpl_by_item:
        return {}
    rates_by_tmpl: dict[uuid.UUID, dict] = {}
    rows = (
        await db.execute(
            select(
                ItemTaxTemplateDetail.template_id,
                ItemTaxTemplateDetail.account_head_id,
                ItemTaxTemplateDetail.rate,
            ).where(ItemTaxTemplateDetail.template_id.in_(set(tmpl_by_item.values())))
        )
    ).all()
    for tid, account_head_id, rate in rows:
        rates_by_tmpl.setdefault(tid, {})[account_head_id] = Decimal(rate)
    return {iid: rates_by_tmpl.get(tid, {}) for iid, tid in tmpl_by_item.items()}


def base_payable_total(invoice: SalesInvoice | PurchaseInvoice) -> Decimal:
    """The base-currency amount the party owes (grand total plus rounding)."""
    return invoice.base_grand_total + (invoice.rounding_adjustment * invoice.conversion_rate)


def set_invoice_status(invoice: SalesInvoice | PurchaseInvoice, today: date | None = None) -> None:
    """Derive status from docstatus / outstanding / due date (ERPNext set_status)."""
    today = today or date.today()
    if invoice.docstatus == 0:
        invoice.status = "Draft"
    elif invoice.docstatus == 2:
        invoice.status = "Cancelled"
    elif invoice.is_return:
        invoice.status = "Return"
    elif invoice.outstanding_amount <= ZERO:
        invoice.status = "Paid"
    elif invoice.due_date and invoice.due_date < today:
        invoice.status = "Overdue"
    elif invoice.outstanding_amount < base_payable_total(invoice):
        invoice.status = "Partly Paid"
    else:
        invoice.status = "Unpaid"


def require_draft(docstatus: int) -> None:
    if docstatus != 0:
        raise ValidationError("Only draft documents can be modified", code="ERR_DOCSTATUS")


def require_submitted(docstatus: int) -> None:
    if docstatus != 1:
        raise ValidationError("Document is not submitted", code="ERR_DOCSTATUS")
