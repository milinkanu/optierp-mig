"""Sales Invoice service — Module 02.

Source: erpnext/accounts/doctype/sales_invoice. Totals come from the
taxes_and_totals engine; submission posts GL (Dr receivable / Cr income +
taxes + rounding); cancellation reverses GL and restores any return links.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.core.naming import get_next_name
from app.core.security import CurrentUser
from app.models.accounts import Account, SalesInvoice, SalesInvoiceItem, SalesInvoiceTax
from app.models.base import DOCSTATUS_CANCELLED, DOCSTATUS_SUBMITTED
from app.schemas.accounts import SalesInvoiceCreate
from app.services import gl
from app.services.accounts_common import (
    NAMING_SERIES,
    base_payable_total,
    get_company,
    get_customer,
    get_receivable_account,
    require_draft,
    require_submitted,
    set_invoice_status,
)
from app.services.audit import log_audit
from app.services.pagination import paginate
from app.services.taxes_and_totals import ItemRow, TaxRow, calculate_taxes_and_totals

ZERO = Decimal("0")


async def _load_tax_rows(db: AsyncSession, payload: SalesInvoiceCreate, customer) -> list:
    """Inline taxes win; then an explicit template; then the template resolved
    from the customer's tax category / company default (erpnext get_party_details)."""
    if payload.taxes:
        return payload.taxes
    from app.models.accounts import TaxTemplate

    if payload.tax_template_id:
        template = await db.scalar(
            select(TaxTemplate)
            .options(selectinload(TaxTemplate.details))
            .where(TaxTemplate.id == payload.tax_template_id)
        )
        if template is None or template.kind != "sales":
            raise NotFoundError("Sales tax template not found")
    else:
        from app.services.accounts_masters import resolve_tax_template

        template = await resolve_tax_template(
            db, customer.company_id, "sales", customer.tax_category_id
        )
        if template is None:
            return []
    from app.schemas.accounts import TaxRowIn

    return [
        TaxRowIn(
            charge_type=d.charge_type,
            rate=d.rate,
            tax_amount=d.tax_amount,
            row_id=d.row_id,
            account_head_id=d.account_head_id,
            cost_center_id=d.cost_center_id,
            description=d.description,
        )
        for d in template.details
    ]


async def create_sales_invoice(
    db: AsyncSession, payload: SalesInvoiceCreate, user: CurrentUser
) -> SalesInvoice:
    company = await get_company(db, user.company_id)
    customer = await get_customer(db, payload.customer_id, company.id)
    debit_to_id = payload.debit_to_id or get_receivable_account(company, customer)
    currency = (payload.currency or company.default_currency).upper()

    if payload.is_return and not payload.return_against_id:
        raise ValidationError("return_against_id is required for a return (credit note)",
                              field="return_against_id")

    tax_rows_in = await _load_tax_rows(db, payload, customer)

    # run the calculation engine
    engine_items = [ItemRow(qty=item.qty, rate=item.rate) for item in payload.items]
    engine_taxes = [
        TaxRow(
            charge_type=t.charge_type,
            rate=t.rate,
            tax_amount=t.tax_amount,
            row_id=t.row_id,
        )
        for t in tax_rows_in
    ]
    totals = calculate_taxes_and_totals(
        engine_items,
        engine_taxes,
        conversion_rate=payload.conversion_rate,
        apply_discount_on=payload.apply_discount_on,
        additional_discount_percentage=payload.additional_discount_percentage,
        discount_amount=payload.discount_amount,
    )

    sign = Decimal("-1") if payload.is_return else Decimal("1")
    name = await get_next_name(db, NAMING_SERIES["Sales Invoice"], company.id)
    invoice = SalesInvoice(
        id=uuid.uuid4(),
        company_id=company.id,
        name=name,
        customer_id=customer.id,
        debit_to_id=debit_to_id,
        posting_date=payload.posting_date,
        due_date=payload.due_date,
        currency=currency,
        conversion_rate=payload.conversion_rate,
        remarks=payload.remarks,
        is_return=payload.is_return,
        return_against_id=payload.return_against_id,
        apply_discount_on=payload.apply_discount_on,
        additional_discount_percentage=payload.additional_discount_percentage,
        discount_amount=totals.discount_amount,
        total_qty=totals.total_qty * sign,
        total=totals.total * sign,
        base_total=totals.base_total * sign,
        net_total=totals.net_total * sign,
        base_net_total=totals.base_net_total * sign,
        total_taxes_and_charges=totals.total_taxes_and_charges * sign,
        base_total_taxes_and_charges=totals.base_total_taxes_and_charges * sign,
        grand_total=totals.grand_total * sign,
        base_grand_total=totals.base_grand_total * sign,
        rounded_total=totals.rounded_total * sign,
        rounding_adjustment=totals.rounding_adjustment * sign,
        outstanding_amount=ZERO,
        owner=user.id,
        modified_by=user.id,
    )
    db.add(invoice)
    await db.flush()

    default_income = company.default_income_account_id
    for idx, (item_in, engine_item) in enumerate(zip(payload.items, engine_items), start=1):
        income_account_id = item_in.account_id or default_income
        if income_account_id is None:
            raise ValidationError(
                f"Item row {idx}: no income account given and the company has no default",
                field="items",
            )
        db.add(
            SalesInvoiceItem(
                invoice_id=invoice.id,
                idx=idx,
                item_code=item_in.item_code,
                item_name=item_in.item_name,
                description=item_in.description,
                qty=engine_item.qty * sign,
                uom=item_in.uom,
                rate=engine_item.rate,
                amount=engine_item.amount * sign,
                base_rate=engine_item.base_rate,
                base_amount=engine_item.base_amount * sign,
                net_amount=engine_item.net_amount * sign,
                base_net_amount=engine_item.base_net_amount * sign,
                cost_center_id=item_in.cost_center_id,
                income_account_id=income_account_id,
            )
        )
    for idx, (tax_in, engine_tax) in enumerate(zip(tax_rows_in, engine_taxes), start=1):
        db.add(
            SalesInvoiceTax(
                invoice_id=invoice.id,
                idx=idx,
                charge_type=engine_tax.charge_type,
                row_id=engine_tax.row_id,
                rate=engine_tax.rate,
                account_head_id=tax_in.account_head_id,
                cost_center_id=tax_in.cost_center_id,
                description=tax_in.description,
                tax_amount=engine_tax.tax_amount * sign,
                total=engine_tax.total * sign,
                base_tax_amount=engine_tax.base_tax_amount * sign,
                base_total=engine_tax.base_total * sign,
            )
        )
    set_invoice_status(invoice)
    await db.flush()
    await log_audit(
        db, doctype="Sales Invoice", document_id=invoice.id, action="INSERT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return await get_sales_invoice(db, invoice.id, company.id)


async def get_sales_invoice(
    db: AsyncSession, invoice_id: uuid.UUID, company_id: uuid.UUID | None
) -> SalesInvoice:
    invoice = await db.scalar(
        select(SalesInvoice)
        .options(selectinload(SalesInvoice.items), selectinload(SalesInvoice.taxes))
        .where(SalesInvoice.id == invoice_id, SalesInvoice.company_id == company_id)
    )
    if invoice is None:
        raise NotFoundError("Sales Invoice not found")
    return invoice


async def list_sales_invoices(
    db: AsyncSession, company_id: uuid.UUID | None, page: int = 1, page_size: int = 20,
    status: str | None = None,
) -> tuple[list[SalesInvoice], int]:
    stmt = (
        select(SalesInvoice)
        .where(SalesInvoice.company_id == company_id)
        .order_by(SalesInvoice.posting_date.desc(), SalesInvoice.creation.desc())
    )
    if status:
        stmt = stmt.where(SalesInvoice.status == status)
    return await paginate(db, stmt, page, page_size)


def _build_gl_rows(invoice: SalesInvoice, customer_name: str) -> list[gl.GLRow]:
    rows: list[gl.GLRow] = []
    receivable_amount = base_payable_total(invoice)
    income_names: list[str] = []

    # Dr receivable (party row); against_voucher self-links for AR tracking
    rows.append(
        gl.GLRow(
            account_id=invoice.debit_to_id,
            debit=receivable_amount if receivable_amount > ZERO else ZERO,
            credit=-receivable_amount if receivable_amount < ZERO else ZERO,
            party_type="Customer",
            party_id=invoice.customer_id,
            against_voucher_type="Sales Invoice",
            against_voucher_id=invoice.id,
        )
    )
    # Cr income per item
    for item in invoice.items:
        rows.append(
            gl.GLRow(
                account_id=item.income_account_id,
                credit=item.base_net_amount if item.base_net_amount > ZERO else ZERO,
                debit=-item.base_net_amount if item.base_net_amount < ZERO else ZERO,
                cost_center_id=item.cost_center_id,
                against=customer_name,
            )
        )
    # Cr taxes
    for tax in invoice.taxes:
        if tax.base_tax_amount == ZERO:
            continue
        rows.append(
            gl.GLRow(
                account_id=tax.account_head_id,
                credit=tax.base_tax_amount if tax.base_tax_amount > ZERO else ZERO,
                debit=-tax.base_tax_amount if tax.base_tax_amount < ZERO else ZERO,
                cost_center_id=tax.cost_center_id,
                against=customer_name,
            )
        )
    return rows


async def submit_sales_invoice(
    db: AsyncSession, invoice_id: uuid.UUID, user: CurrentUser
) -> SalesInvoice:
    invoice = await get_sales_invoice(db, invoice_id, user.company_id)
    require_draft(invoice.docstatus)
    company = await get_company(db, invoice.company_id)
    customer = await get_customer(db, invoice.customer_id, invoice.company_id)

    rows = _build_gl_rows(invoice, customer.customer_name)

    # rounding adjustment balances receivable(rounded) vs net+taxes
    base_rounding = invoice.rounding_adjustment * invoice.conversion_rate
    if base_rounding != ZERO:
        if company.round_off_account_id is None:
            raise ValidationError("Company has no Round Off account configured")
        rows.append(
            gl.GLRow(
                account_id=company.round_off_account_id,
                credit=base_rounding if base_rounding > ZERO else ZERO,
                debit=-base_rounding if base_rounding < ZERO else ZERO,
                cost_center_id=company.default_cost_center_id,
            )
        )

    await gl.make_gl_entries(
        db,
        company_id=invoice.company_id,
        voucher_type="Sales Invoice",
        voucher_id=invoice.id,
        voucher_no=invoice.name,
        posting_date=invoice.posting_date,
        rows=rows,
        user_id=user.id,
        remarks=invoice.remarks,
    )

    invoice.docstatus = DOCSTATUS_SUBMITTED
    invoice.outstanding_amount = base_payable_total(invoice)

    # a credit note (return) reduces the original invoice's outstanding
    if invoice.is_return and invoice.return_against_id:
        original = await get_sales_invoice(db, invoice.return_against_id, invoice.company_id)
        require_submitted(original.docstatus)
        original.outstanding_amount += invoice.outstanding_amount  # negative
        set_invoice_status(original)
        invoice.outstanding_amount = ZERO

    set_invoice_status(invoice)
    invoice.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Sales Invoice", document_id=invoice.id, action="SUBMIT",
        user_id=user.id, company_id=invoice.company_id,
    )
    await db.commit()
    return await get_sales_invoice(db, invoice.id, user.company_id)


async def cancel_sales_invoice(
    db: AsyncSession, invoice_id: uuid.UUID, user: CurrentUser
) -> SalesInvoice:
    invoice = await get_sales_invoice(db, invoice_id, user.company_id)
    require_submitted(invoice.docstatus)
    if invoice.outstanding_amount != base_payable_total(invoice) and not invoice.is_return:
        raise ValidationError(
            "Cannot cancel: payments are allocated against this invoice. Cancel them first."
        )

    await gl.make_reverse_gl_entries(
        db, voucher_type="Sales Invoice", voucher_id=invoice.id, user_id=user.id
    )
    if invoice.is_return and invoice.return_against_id:
        original = await get_sales_invoice(db, invoice.return_against_id, invoice.company_id)
        original.outstanding_amount -= base_payable_total(invoice)
        set_invoice_status(original)

    invoice.docstatus = DOCSTATUS_CANCELLED
    invoice.outstanding_amount = ZERO
    set_invoice_status(invoice)
    invoice.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Sales Invoice", document_id=invoice.id, action="CANCEL",
        user_id=user.id, company_id=invoice.company_id,
    )
    await db.commit()
    return await get_sales_invoice(db, invoice.id, user.company_id)
