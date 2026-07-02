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


from sqlalchemy import func, select  # noqa: E402


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


def _gstin_state(value: str | None) -> str | None:
    """Two-digit state code of a 15-char GSTIN, else None."""
    s = (value or "").strip()
    return s[:2] if len(s) == 15 and s[:2].isdigit() else None


async def _hsn_rates(db: AsyncSession, codes: set[str]) -> dict[str, Decimal]:
    """Map each HSN code to its GST rate from the reference master. A code with
    several rows (e.g. fresh 0% vs frozen 12%) picks the most common rate,
    breaking ties toward the higher rate."""
    from app.models.core import HsnCode

    if not codes:
        return {}
    rows = (
        await db.execute(
            select(HsnCode.hsn_code, HsnCode.gst_rate, func.count())
            .where(HsnCode.hsn_code.in_(codes))
            .group_by(HsnCode.hsn_code, HsnCode.gst_rate)
        )
    ).all()
    best: dict[str, tuple[int, Decimal]] = {}  # code -> (count, rate)
    for code, rate, count in rows:
        rate = Decimal(rate)
        current = best.get(code)
        if current is None or (count, rate) > current:
            best[code] = (count, rate)
    return {code: rate for code, (count, rate) in best.items()}


async def auto_gst_from_items(
    db: AsyncSession, *, company: Company, party_gstin: str | None,
    place_of_supply: str | None, payload_items: list,
    item_rates: dict[uuid.UUID, dict] | None = None,
) -> tuple[list, dict[uuid.UUID, dict]]:
    """Derive GST tax rows + per-item rate overrides from the line items when no
    invoice-level tax template resolved — the "the item's HSN carries the rate,
    so GST just applies" path.

    Each line's total GST rate comes from its Item Tax Template if set, else the
    HSN master (by ``hsn_sac_code``); a non-Taxable ``gst_treatment`` is 0%. The
    split is CGST+SGST (intra-state) or IGST (inter-state), decided from the
    party's GSTIN state (or place of supply) vs the company's. Returns
    ``([], {})`` when GST can't be derived (no Output GST accounts, or no taxable
    line), leaving the caller's zero-tax behaviour unchanged.

    Called ONLY when the invoice would otherwise carry no tax, so it never alters
    invoices that already resolve a template.
    """
    from app.models.accounts import Account
    from app.models.stock import Item
    from app.schemas.accounts import TaxRowIn

    item_ids = {i.item_id for i in payload_items if getattr(i, "item_id", None) is not None}
    if not item_ids:
        return [], {}

    # line item GST context (HSN + treatment + whether it has its own template)
    meta = {
        r.id: r
        for r in (
            await db.execute(
                select(
                    Item.id, Item.hsn_sac_code, Item.gst_treatment, Item.item_tax_template_id
                ).where(Item.id.in_(item_ids))
            )
        ).all()
    }
    hsn_rate = await _hsn_rates(
        db, {m.hsn_sac_code for m in meta.values() if m.hsn_sac_code and m.gst_treatment == "Taxable"}
    )

    # intra vs inter: party state vs company state (GSTIN first, then place of supply)
    company_state = _gstin_state(company.tax_id)
    party_state = _gstin_state(party_gstin)
    if party_state is None and place_of_supply and place_of_supply[:2].isdigit():
        party_state = place_of_supply[:2]
    inter = bool(company_state and party_state and company_state != party_state)

    # Each non-template line's total GST rate: HSN rate if Taxable, else 0.
    # Every such line gets an EXPLICIT override (incl. 0), so a Nil/Exempt line
    # never falls back to a non-zero row rate. Template lines keep their own
    # item_tax_rate (computed by the caller) and are left untouched here.
    totals: dict[uuid.UUID, Decimal] = {}
    has_template = False
    for item in payload_items:
        m = meta.get(getattr(item, "item_id", None))
        if m is None:
            continue
        if m.item_tax_template_id is not None:
            has_template = True
            continue
        rate = hsn_rate.get(m.hsn_sac_code or "") if m.gst_treatment == "Taxable" else None
        totals[m.id] = rate if rate and rate > 0 else Decimal(0)

    if not any(v > 0 for v in totals.values()) and not has_template:
        return [], {}  # nothing taxable — leave the invoice tax-free

    # resolve the Output GST accounts for this company (Tax accounts named *GST*)
    async def _account(*needles: str) -> uuid.UUID | None:
        stmt = select(Account.id).where(
            Account.company_id == company.id, Account.account_type == "Tax"
        )
        for n in needles:
            stmt = stmt.where(Account.account_name.ilike(f"%{n}%"))
        return await db.scalar(stmt.order_by(Account.account_name).limit(1))

    if inter:
        igst = await _account("IGST")
        if igst is None:
            return [], {}
        heads = [("IGST", igst, Decimal(1))]
    else:
        cgst, sgst = await _account("CGST"), await _account("SGST")
        if cgst is None or sgst is None:
            return [], {}
        heads = [("CGST", cgst, Decimal("0.5")), ("SGST", sgst, Decimal("0.5"))]

    # split each HSN-derived line total across the heads (per-line overrides drive
    # the amounts; every taxable line has one).
    item_rate_override = {
        iid: {acc: total * share for _, acc, share in heads} for iid, total in totals.items()
    }
    # Row rate per head = the common per-head rate when every taxable line agrees
    # (template lines contribute via ``item_rates``), else 0 for a mixed-slab bill.
    existing = item_rates or {}

    def _row_rate(acc: uuid.UUID) -> Decimal:
        vals = set()
        for item in payload_items:
            iid = getattr(item, "item_id", None)
            r = item_rate_override.get(iid, {}).get(acc)
            if r is None:
                r = existing.get(iid, {}).get(acc)
            if r and r > 0:
                vals.add(Decimal(r))
        return next(iter(vals)) if len(vals) == 1 else Decimal(0)

    tax_rows = [
        TaxRowIn(charge_type="On Net Total", rate=_row_rate(acc), account_head_id=acc, description=label)
        for label, acc, _ in heads
    ]
    return tax_rows, item_rate_override


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
