"""Request for Quotation + Supplier Quotation services — Module 04 (lean).

RFQ: which items we want quoted, from which suppliers. Supplier Quotation:
a supplier's response (optionally linked to the RFQ; submitting one marks
that supplier's quote_status = Received). A Purchase Order can then be
created from the Supplier Quotation (the frontend prefills it).
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.core.naming import get_next_name
from app.core.security import CurrentUser
from app.models.base import DOCSTATUS_CANCELLED, DOCSTATUS_SUBMITTED
from app.models.buying import (
    RequestForQuotation,
    RequestForQuotationItem,
    RequestForQuotationSupplier,
    SupplierQuotation,
    SupplierQuotationItem,
)
from app.schemas.buying import RFQCreate, SupplierQuotationCreate
from app.services.accounts_common import get_company, get_supplier, require_draft, require_submitted
from app.services.audit import log_audit
from app.services.pagination import paginate
from app.services.stock_common import STOCK_NAMING_SERIES, get_items
from app.services.taxes_and_totals import ItemRow, calculate_taxes_and_totals

ZERO = Decimal("0")


# --- RFQ -------------------------------------------------------------------------


async def create_rfq(db: AsyncSession, payload: RFQCreate, user: CurrentUser) -> RequestForQuotation:
    company = await get_company(db, user.company_id)
    items = await get_items(db, {row.item_id for row in payload.items}, company.id)
    for supplier_id in payload.supplier_ids:
        await get_supplier(db, supplier_id, company.id)

    name = await get_next_name(db, STOCK_NAMING_SERIES["Request for Quotation"], company.id)
    rfq = RequestForQuotation(
        id=uuid.uuid4(),
        company_id=company.id,
        name=name,
        posting_date=payload.posting_date,
        schedule_date=payload.schedule_date,
        message_for_supplier=payload.message_for_supplier,
        remarks=payload.remarks,
        owner=user.id,
        modified_by=user.id,
    )
    db.add(rfq)
    await db.flush()
    for idx, row in enumerate(payload.items, start=1):
        item = items[row.item_id]
        db.add(
            RequestForQuotationItem(
                rfq_id=rfq.id,
                idx=idx,
                item_id=row.item_id,
                qty=row.qty,
                uom=row.uom or item.stock_uom,
                warehouse_id=row.warehouse_id or item.default_warehouse_id,
                schedule_date=row.schedule_date or payload.schedule_date,
            )
        )
    for idx, supplier_id in enumerate(payload.supplier_ids, start=1):
        db.add(RequestForQuotationSupplier(rfq_id=rfq.id, idx=idx, supplier_id=supplier_id))
    await db.flush()
    await log_audit(
        db, doctype="Request for Quotation", document_id=rfq.id, action="INSERT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return await get_rfq(db, rfq.id, company.id)


async def get_rfq(
    db: AsyncSession, rfq_id: uuid.UUID, company_id: uuid.UUID | None
) -> RequestForQuotation:
    rfq = await db.scalar(
        select(RequestForQuotation)
        .options(
            selectinload(RequestForQuotation.items),
            selectinload(RequestForQuotation.suppliers),
        )
        .where(RequestForQuotation.id == rfq_id, RequestForQuotation.company_id == company_id)
    )
    if rfq is None:
        raise NotFoundError("Request for Quotation not found")
    return rfq


async def list_rfqs(
    db: AsyncSession, company_id: uuid.UUID | None, page: int = 1, page_size: int = 20,
) -> tuple[list[RequestForQuotation], int]:
    stmt = (
        select(RequestForQuotation)
        .where(RequestForQuotation.company_id == company_id)
        .order_by(RequestForQuotation.posting_date.desc(), RequestForQuotation.creation.desc())
    )
    return await paginate(db, stmt, page, page_size)


async def submit_rfq(db: AsyncSession, rfq_id: uuid.UUID, user: CurrentUser) -> RequestForQuotation:
    rfq = await get_rfq(db, rfq_id, user.company_id)
    require_draft(rfq.docstatus)
    rfq.docstatus = DOCSTATUS_SUBMITTED
    rfq.status = "Submitted"
    rfq.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Request for Quotation", document_id=rfq.id, action="SUBMIT",
        user_id=user.id, company_id=rfq.company_id,
    )
    await db.commit()
    return await get_rfq(db, rfq.id, user.company_id)


async def cancel_rfq(db: AsyncSession, rfq_id: uuid.UUID, user: CurrentUser) -> RequestForQuotation:
    rfq = await get_rfq(db, rfq_id, user.company_id)
    require_submitted(rfq.docstatus)
    rfq.docstatus = DOCSTATUS_CANCELLED
    rfq.status = "Cancelled"
    rfq.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Request for Quotation", document_id=rfq.id, action="CANCEL",
        user_id=user.id, company_id=rfq.company_id,
    )
    await db.commit()
    return await get_rfq(db, rfq.id, user.company_id)


# --- Supplier Quotation ----------------------------------------------------------------


async def create_supplier_quotation(
    db: AsyncSession, payload: SupplierQuotationCreate, user: CurrentUser
) -> SupplierQuotation:
    company = await get_company(db, user.company_id)
    supplier = await get_supplier(db, payload.supplier_id, company.id)
    currency = (payload.currency or supplier.default_currency or company.default_currency).upper()
    items = await get_items(db, {row.item_id for row in payload.items}, company.id)

    linked_rfq_item_ids = {r.rfq_item_id for r in payload.items if r.rfq_item_id}
    if payload.rfq_id is not None:
        rfq = await get_rfq(db, payload.rfq_id, company.id)
        if rfq.docstatus != DOCSTATUS_SUBMITTED:
            raise ValidationError("RFQ is not submitted", field="rfq_id")
        if linked_rfq_item_ids - {i.id for i in rfq.items}:
            raise ValidationError(
                "rfq_item_id does not belong to the linked RFQ", field="items"
            )
    elif linked_rfq_item_ids:
        raise ValidationError("rfq_item_id given without rfq_id", field="items")

    engine_items = [ItemRow(qty=row.qty, rate=row.rate) for row in payload.items]
    totals = calculate_taxes_and_totals(
        engine_items, [], conversion_rate=payload.conversion_rate
    )

    name = await get_next_name(db, STOCK_NAMING_SERIES["Supplier Quotation"], company.id)
    sq = SupplierQuotation(
        id=uuid.uuid4(),
        company_id=company.id,
        name=name,
        supplier_id=supplier.id,
        rfq_id=payload.rfq_id,
        posting_date=payload.posting_date,
        valid_till=payload.valid_till,
        currency=currency,
        conversion_rate=payload.conversion_rate,
        remarks=payload.remarks,
        total_qty=totals.total_qty,
        total=totals.total,
        base_total=totals.base_total,
        net_total=totals.net_total,
        base_net_total=totals.base_net_total,
        grand_total=totals.grand_total,
        base_grand_total=totals.base_grand_total,
        rounded_total=totals.rounded_total,
        rounding_adjustment=totals.rounding_adjustment,
        owner=user.id,
        modified_by=user.id,
    )
    db.add(sq)
    await db.flush()
    for idx, (row, engine_item) in enumerate(zip(payload.items, engine_items), start=1):
        item = items[row.item_id]
        db.add(
            SupplierQuotationItem(
                quotation_id=sq.id,
                idx=idx,
                item_id=item.id,
                item_code=item.item_code,
                item_name=item.item_name,
                qty=engine_item.qty,
                uom=row.uom or item.stock_uom,
                price_list_rate=engine_item.rate,
                base_price_list_rate=engine_item.base_rate,
                discount_percentage=engine_item.discount_percentage,
                discount_amount=engine_item.discount_amount,
                rate=engine_item.rate,
                amount=engine_item.amount,
                base_rate=engine_item.base_rate,
                base_amount=engine_item.base_amount,
                net_amount=engine_item.net_amount,
                base_net_amount=engine_item.base_net_amount,
                rfq_item_id=row.rfq_item_id,
            )
        )
    await db.flush()
    await log_audit(
        db, doctype="Supplier Quotation", document_id=sq.id, action="INSERT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return await get_supplier_quotation(db, sq.id, company.id)


async def get_supplier_quotation(
    db: AsyncSession, sq_id: uuid.UUID, company_id: uuid.UUID | None
) -> SupplierQuotation:
    sq = await db.scalar(
        select(SupplierQuotation)
        .options(selectinload(SupplierQuotation.items))
        .where(SupplierQuotation.id == sq_id, SupplierQuotation.company_id == company_id)
    )
    if sq is None:
        raise NotFoundError("Supplier Quotation not found")
    return sq


async def list_supplier_quotations(
    db: AsyncSession, company_id: uuid.UUID | None, page: int = 1, page_size: int = 20,
    supplier_id: uuid.UUID | None = None,
) -> tuple[list[SupplierQuotation], int]:
    stmt = (
        select(SupplierQuotation)
        .where(SupplierQuotation.company_id == company_id)
        .order_by(SupplierQuotation.posting_date.desc(), SupplierQuotation.creation.desc())
    )
    if supplier_id is not None:
        stmt = stmt.where(SupplierQuotation.supplier_id == supplier_id)
    return await paginate(db, stmt, page, page_size)


async def submit_supplier_quotation(
    db: AsyncSession, sq_id: uuid.UUID, user: CurrentUser
) -> SupplierQuotation:
    sq = await get_supplier_quotation(db, sq_id, user.company_id)
    require_draft(sq.docstatus)
    sq.docstatus = DOCSTATUS_SUBMITTED
    sq.status = "Submitted"
    sq.modified_by = user.id
    if sq.rfq_id is not None:
        rfq_supplier = await db.scalar(
            select(RequestForQuotationSupplier).where(
                RequestForQuotationSupplier.rfq_id == sq.rfq_id,
                RequestForQuotationSupplier.supplier_id == sq.supplier_id,
            )
        )
        if rfq_supplier is not None:
            rfq_supplier.quote_status = "Received"
    await db.flush()
    await log_audit(
        db, doctype="Supplier Quotation", document_id=sq.id, action="SUBMIT",
        user_id=user.id, company_id=sq.company_id,
    )
    await db.commit()
    return await get_supplier_quotation(db, sq.id, user.company_id)


async def cancel_supplier_quotation(
    db: AsyncSession, sq_id: uuid.UUID, user: CurrentUser
) -> SupplierQuotation:
    sq = await get_supplier_quotation(db, sq_id, user.company_id)
    require_submitted(sq.docstatus)
    sq.docstatus = DOCSTATUS_CANCELLED
    sq.status = "Cancelled"
    sq.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Supplier Quotation", document_id=sq.id, action="CANCEL",
        user_id=user.id, company_id=sq.company_id,
    )
    await db.commit()
    return await get_supplier_quotation(db, sq.id, user.company_id)
