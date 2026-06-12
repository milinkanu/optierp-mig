"""Purchase Invoice service — Module 02 (mirror of sales_invoice).

GL on submit: Cr payable (party) / Dr expense per item / Dr-Cr taxes by
Add/Deduct; Valuation-only rows post nothing (they affect stock cost,
arriving with Module 03).
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.core.naming import get_next_name
from app.core.security import CurrentUser
from app.models.accounts import PurchaseInvoice, PurchaseInvoiceItem, PurchaseInvoiceTax, TaxTemplate
from app.models.base import DOCSTATUS_CANCELLED, DOCSTATUS_SUBMITTED
from app.schemas.accounts import PurchaseInvoiceCreate, TaxRowIn
from app.services import gl
from app.services.accounts_common import (
    NAMING_SERIES,
    base_payable_total,
    get_company,
    get_payable_account,
    get_supplier,
    require_draft,
    require_submitted,
    set_invoice_status,
)
from app.services.audit import log_audit
from app.services.pagination import paginate
from app.services.taxes_and_totals import ItemRow, TaxRow, calculate_taxes_and_totals

ZERO = Decimal("0")


async def _load_tax_rows(db: AsyncSession, payload: PurchaseInvoiceCreate) -> list[TaxRowIn]:
    if payload.taxes or not payload.tax_template_id:
        return payload.taxes
    template = await db.scalar(
        select(TaxTemplate)
        .options(selectinload(TaxTemplate.details))
        .where(TaxTemplate.id == payload.tax_template_id)
    )
    if template is None or template.kind != "purchase":
        raise NotFoundError("Purchase tax template not found")
    return [
        TaxRowIn(
            charge_type=d.charge_type,
            rate=d.rate,
            tax_amount=d.tax_amount,
            row_id=d.row_id,
            account_head_id=d.account_head_id,
            cost_center_id=d.cost_center_id,
            description=d.description,
            add_deduct_tax=d.add_deduct_tax,
            category=d.category,
        )
        for d in template.details
    ]


async def create_purchase_invoice(
    db: AsyncSession, payload: PurchaseInvoiceCreate, user: CurrentUser
) -> PurchaseInvoice:
    company = await get_company(db, user.company_id)
    supplier = await get_supplier(db, payload.supplier_id, company.id)
    credit_to_id = payload.credit_to_id or get_payable_account(company, supplier)
    currency = (payload.currency or company.default_currency).upper()

    if payload.is_return and not payload.return_against_id:
        raise ValidationError("return_against_id is required for a return (debit note)",
                              field="return_against_id")

    tax_rows_in = await _load_tax_rows(db, payload)
    engine_items = [ItemRow(qty=item.qty, rate=item.rate) for item in payload.items]
    engine_taxes = [
        TaxRow(
            charge_type=t.charge_type,
            rate=t.rate,
            tax_amount=t.tax_amount,
            row_id=t.row_id,
            add_deduct_tax=t.add_deduct_tax,
            category=t.category,
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
        is_purchase=True,
    )

    sign = Decimal("-1") if payload.is_return else Decimal("1")
    name = await get_next_name(db, NAMING_SERIES["Purchase Invoice"], company.id)
    invoice = PurchaseInvoice(
        id=uuid.uuid4(),
        company_id=company.id,
        name=name,
        supplier_id=supplier.id,
        credit_to_id=credit_to_id,
        posting_date=payload.posting_date,
        due_date=payload.due_date,
        bill_no=payload.bill_no,
        bill_date=payload.bill_date,
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

    default_expense = company.default_expense_account_id
    for idx, (item_in, engine_item) in enumerate(zip(payload.items, engine_items), start=1):
        expense_account_id = item_in.account_id or default_expense
        if expense_account_id is None:
            raise ValidationError(
                f"Item row {idx}: no expense account given and the company has no default",
                field="items",
            )
        db.add(
            PurchaseInvoiceItem(
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
                expense_account_id=expense_account_id,
            )
        )
    for idx, (tax_in, engine_tax) in enumerate(zip(tax_rows_in, engine_taxes), start=1):
        db.add(
            PurchaseInvoiceTax(
                invoice_id=invoice.id,
                idx=idx,
                charge_type=engine_tax.charge_type,
                row_id=engine_tax.row_id,
                rate=engine_tax.rate,
                account_head_id=tax_in.account_head_id,
                cost_center_id=tax_in.cost_center_id,
                description=tax_in.description,
                add_deduct_tax=engine_tax.add_deduct_tax,
                category=engine_tax.category,
                tax_amount=engine_tax.tax_amount * sign,
                total=engine_tax.total * sign,
                base_tax_amount=engine_tax.base_tax_amount * sign,
                base_total=engine_tax.base_total * sign,
            )
        )
    set_invoice_status(invoice)
    await db.flush()
    await log_audit(
        db, doctype="Purchase Invoice", document_id=invoice.id, action="INSERT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return await get_purchase_invoice(db, invoice.id, company.id)


async def get_purchase_invoice(
    db: AsyncSession, invoice_id: uuid.UUID, company_id: uuid.UUID | None
) -> PurchaseInvoice:
    invoice = await db.scalar(
        select(PurchaseInvoice)
        .options(selectinload(PurchaseInvoice.items), selectinload(PurchaseInvoice.taxes))
        .where(PurchaseInvoice.id == invoice_id, PurchaseInvoice.company_id == company_id)
    )
    if invoice is None:
        raise NotFoundError("Purchase Invoice not found")
    return invoice


async def list_purchase_invoices(
    db: AsyncSession, company_id: uuid.UUID | None, page: int = 1, page_size: int = 20,
    status: str | None = None,
) -> tuple[list[PurchaseInvoice], int]:
    stmt = (
        select(PurchaseInvoice)
        .where(PurchaseInvoice.company_id == company_id)
        .order_by(PurchaseInvoice.posting_date.desc(), PurchaseInvoice.creation.desc())
    )
    if status:
        stmt = stmt.where(PurchaseInvoice.status == status)
    return await paginate(db, stmt, page, page_size)


def _build_gl_rows(invoice: PurchaseInvoice, supplier_name: str) -> list[gl.GLRow]:
    rows: list[gl.GLRow] = []
    payable_amount = base_payable_total(invoice)

    # Cr payable (party row)
    rows.append(
        gl.GLRow(
            account_id=invoice.credit_to_id,
            credit=payable_amount if payable_amount > ZERO else ZERO,
            debit=-payable_amount if payable_amount < ZERO else ZERO,
            party_type="Supplier",
            party_id=invoice.supplier_id,
            against_voucher_type="Purchase Invoice",
            against_voucher_id=invoice.id,
        )
    )
    # Dr expense per item
    for item in invoice.items:
        rows.append(
            gl.GLRow(
                account_id=item.expense_account_id,
                debit=item.base_net_amount if item.base_net_amount > ZERO else ZERO,
                credit=-item.base_net_amount if item.base_net_amount < ZERO else ZERO,
                cost_center_id=item.cost_center_id,
                against=supplier_name,
            )
        )
    # taxes: Add -> Dr; Deduct -> Cr; pure Valuation rows post nothing here
    for tax in invoice.taxes:
        if tax.base_tax_amount == ZERO or tax.category == "Valuation":
            continue
        amount = tax.base_tax_amount
        if tax.add_deduct_tax == "Deduct":
            amount = -amount
        rows.append(
            gl.GLRow(
                account_id=tax.account_head_id,
                debit=amount if amount > ZERO else ZERO,
                credit=-amount if amount < ZERO else ZERO,
                cost_center_id=tax.cost_center_id,
                against=supplier_name,
            )
        )
    return rows


async def submit_purchase_invoice(
    db: AsyncSession, invoice_id: uuid.UUID, user: CurrentUser
) -> PurchaseInvoice:
    invoice = await get_purchase_invoice(db, invoice_id, user.company_id)
    require_draft(invoice.docstatus)
    company = await get_company(db, invoice.company_id)
    supplier = await get_supplier(db, invoice.supplier_id, invoice.company_id)

    rows = _build_gl_rows(invoice, supplier.supplier_name)

    base_rounding = invoice.rounding_adjustment * invoice.conversion_rate
    if base_rounding != ZERO:
        if company.round_off_account_id is None:
            raise ValidationError("Company has no Round Off account configured")
        rows.append(
            gl.GLRow(
                account_id=company.round_off_account_id,
                debit=base_rounding if base_rounding > ZERO else ZERO,
                credit=-base_rounding if base_rounding < ZERO else ZERO,
                cost_center_id=company.default_cost_center_id,
            )
        )

    await gl.make_gl_entries(
        db,
        company_id=invoice.company_id,
        voucher_type="Purchase Invoice",
        voucher_id=invoice.id,
        voucher_no=invoice.name,
        posting_date=invoice.posting_date,
        rows=rows,
        user_id=user.id,
        remarks=invoice.remarks,
    )

    invoice.docstatus = DOCSTATUS_SUBMITTED
    invoice.outstanding_amount = base_payable_total(invoice)

    if invoice.is_return and invoice.return_against_id:
        original = await get_purchase_invoice(db, invoice.return_against_id, invoice.company_id)
        require_submitted(original.docstatus)
        original.outstanding_amount += invoice.outstanding_amount
        set_invoice_status(original)
        invoice.outstanding_amount = ZERO

    set_invoice_status(invoice)
    invoice.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Purchase Invoice", document_id=invoice.id, action="SUBMIT",
        user_id=user.id, company_id=invoice.company_id,
    )
    await db.commit()
    return await get_purchase_invoice(db, invoice.id, user.company_id)


async def cancel_purchase_invoice(
    db: AsyncSession, invoice_id: uuid.UUID, user: CurrentUser
) -> PurchaseInvoice:
    invoice = await get_purchase_invoice(db, invoice_id, user.company_id)
    require_submitted(invoice.docstatus)
    if invoice.outstanding_amount != base_payable_total(invoice) and not invoice.is_return:
        raise ValidationError(
            "Cannot cancel: payments are allocated against this invoice. Cancel them first."
        )

    await gl.make_reverse_gl_entries(
        db, voucher_type="Purchase Invoice", voucher_id=invoice.id, user_id=user.id
    )
    if invoice.is_return and invoice.return_against_id:
        original = await get_purchase_invoice(db, invoice.return_against_id, invoice.company_id)
        original.outstanding_amount -= base_payable_total(invoice)
        set_invoice_status(original)

    invoice.docstatus = DOCSTATUS_CANCELLED
    invoice.outstanding_amount = ZERO
    set_invoice_status(invoice)
    invoice.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Purchase Invoice", document_id=invoice.id, action="CANCEL",
        user_id=user.id, company_id=invoice.company_id,
    )
    await db.commit()
    return await get_purchase_invoice(db, invoice.id, user.company_id)
