"""Material Request service — Module 03.

Lightweight demand document: no stock or GL effect. Purchase Orders link
their rows back via material_request_item_id, driving per_ordered / status
(Pending -> Partially Ordered -> Ordered).
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.core.naming import get_next_name
from app.core.security import CurrentUser
from app.models.base import DOCSTATUS_CANCELLED, DOCSTATUS_SUBMITTED
from app.models.stock import MaterialRequest, MaterialRequestItem
from app.schemas.stock import MaterialRequestCreate
from app.services.accounts_common import get_company, require_draft, require_submitted
from app.services.audit import log_audit
from app.services.pagination import paginate
from app.services.stock_common import STOCK_NAMING_SERIES, get_items

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def set_material_request_status(mr: MaterialRequest) -> None:
    if mr.docstatus == 0:
        mr.status = "Draft"
        return
    if mr.docstatus == 2:
        mr.status = "Cancelled"
        return
    total = sum((row.qty for row in mr.items), ZERO)
    ordered = sum((min(row.ordered_qty, row.qty) for row in mr.items), ZERO)
    mr.per_ordered = (ordered / total * HUNDRED) if total else ZERO
    if mr.per_ordered >= HUNDRED:
        mr.status = "Ordered"
    elif mr.per_ordered > ZERO:
        mr.status = "Partially Ordered"
    else:
        mr.status = "Pending"


async def create_material_request(
    db: AsyncSession, payload: MaterialRequestCreate, user: CurrentUser
) -> MaterialRequest:
    company = await get_company(db, user.company_id)
    items = await get_items(db, {row.item_id for row in payload.items}, company.id)

    name = await get_next_name(db, STOCK_NAMING_SERIES["Material Request"], company.id)
    mr = MaterialRequest(
        id=uuid.uuid4(),
        company_id=company.id,
        name=name,
        posting_date=payload.posting_date,
        material_request_type=payload.material_request_type,
        schedule_date=payload.schedule_date,
        remarks=payload.remarks,
        owner=user.id,
        modified_by=user.id,
    )
    db.add(mr)
    await db.flush()
    for idx, row in enumerate(payload.items, start=1):
        item = items[row.item_id]
        db.add(
            MaterialRequestItem(
                material_request_id=mr.id,
                idx=idx,
                item_id=row.item_id,
                warehouse_id=row.warehouse_id or item.default_warehouse_id,
                qty=row.qty,
                uom=row.uom or item.stock_uom,
                schedule_date=row.schedule_date or payload.schedule_date,
            )
        )
    await db.flush()
    await log_audit(
        db, doctype="Material Request", document_id=mr.id, action="INSERT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return await get_material_request(db, mr.id, company.id)


async def get_material_request(
    db: AsyncSession, mr_id: uuid.UUID, company_id: uuid.UUID | None
) -> MaterialRequest:
    mr = await db.scalar(
        select(MaterialRequest)
        .options(selectinload(MaterialRequest.items))
        .where(MaterialRequest.id == mr_id, MaterialRequest.company_id == company_id)
    )
    if mr is None:
        raise NotFoundError("Material Request not found")
    return mr


async def list_material_requests(
    db: AsyncSession, company_id: uuid.UUID | None, page: int = 1, page_size: int = 20,
    status: str | None = None,
) -> tuple[list[MaterialRequest], int]:
    stmt = (
        select(MaterialRequest)
        .where(MaterialRequest.company_id == company_id)
        .order_by(MaterialRequest.posting_date.desc(), MaterialRequest.creation.desc())
    )
    if status:
        stmt = stmt.where(MaterialRequest.status == status)
    return await paginate(db, stmt, page, page_size)


async def submit_material_request(
    db: AsyncSession, mr_id: uuid.UUID, user: CurrentUser
) -> MaterialRequest:
    mr = await get_material_request(db, mr_id, user.company_id)
    require_draft(mr.docstatus)
    mr.docstatus = DOCSTATUS_SUBMITTED
    set_material_request_status(mr)
    mr.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Material Request", document_id=mr.id, action="SUBMIT",
        user_id=user.id, company_id=mr.company_id,
    )
    await db.commit()
    return await get_material_request(db, mr.id, user.company_id)


async def cancel_material_request(
    db: AsyncSession, mr_id: uuid.UUID, user: CurrentUser
) -> MaterialRequest:
    mr = await get_material_request(db, mr_id, user.company_id)
    require_submitted(mr.docstatus)
    mr.docstatus = DOCSTATUS_CANCELLED
    set_material_request_status(mr)
    mr.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Material Request", document_id=mr.id, action="CANCEL",
        user_id=user.id, company_id=mr.company_id,
    )
    await db.commit()
    return await get_material_request(db, mr.id, user.company_id)
