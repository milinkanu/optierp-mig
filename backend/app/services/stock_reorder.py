"""Reorder automation — Module 03.

Surfaces items whose company-wide *projected* quantity (on-hand + on-order −
reserved) has fallen below their reorder level, and turns that shortfall into a
DRAFT Material Request the user can review and submit. This finally makes the
dormant ``Item.reorder_level`` / ``reorder_qty`` fields do something.

Reorder is item-level (not per-warehouse): we aggregate projected qty across
all of an item's bins and compare to the single reorder level. The suggested
Material Request line uses the item's default warehouse.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.security import CurrentUser
from app.models.stock import Bin, Item, MaterialRequest, Warehouse
from app.schemas.stock import MaterialRequestCreate, MaterialRequestItemIn, ReorderRow
from app.services import material_request as mr_service
from app.services.accounts_common import get_company

ZERO = Decimal("0")


async def reorder_suggestions(db: AsyncSession, company_id: uuid.UUID) -> list[ReorderRow]:
    # select explicit Item columns (not the entity) so the eager item_group
    # join isn't added — that would force its columns into GROUP BY
    projected = func.coalesce(func.sum(Bin.actual_qty + Bin.ordered_qty - Bin.reserved_qty), 0)
    stmt = (
        select(
            Item.id,
            Item.item_code,
            Item.item_name,
            Item.default_warehouse_id,
            Item.reorder_level,
            Item.reorder_qty,
            projected.label("projected"),
        )
        .outerjoin(Bin, Bin.item_id == Item.id)
        .where(
            Item.company_id == company_id,
            Item.is_stock_item.is_(True),
            Item.disabled.is_(False),
            Item.reorder_level > ZERO,
        )
        .group_by(Item.id)  # PK group: other items.* columns are functionally dependent
        .order_by(Item.item_code)
    )
    results = (await db.execute(stmt)).all()

    wh_ids = {r.default_warehouse_id for r in results if r.default_warehouse_id}
    wh_names = {
        w.id: w.warehouse_name
        for w in (
            await db.execute(select(Warehouse).where(Warehouse.id.in_(wh_ids)))
        ).scalars()
    } if wh_ids else {}

    rows: list[ReorderRow] = []
    for r in results:
        projected_qty = Decimal(r.projected)
        if projected_qty >= r.reorder_level:
            continue
        shortfall = r.reorder_level - projected_qty
        suggested = r.reorder_qty if r.reorder_qty > ZERO else shortfall
        rows.append(
            ReorderRow(
                item_id=r.id,
                item_code=r.item_code,
                item_name=r.item_name,
                default_warehouse_id=r.default_warehouse_id,
                default_warehouse_name=wh_names.get(r.default_warehouse_id),
                projected_qty=projected_qty,
                reorder_level=r.reorder_level,
                reorder_qty=r.reorder_qty,
                shortfall=shortfall,
                suggested_qty=suggested,
            )
        )
    return rows


async def create_reorder_material_request(
    db: AsyncSession, user: CurrentUser, item_ids: list[uuid.UUID] | None = None
) -> MaterialRequest:
    """Draft a single Purchase Material Request for the items below reorder
    level (optionally restricted to ``item_ids``)."""
    company = await get_company(db, user.company_id)
    suggestions = await reorder_suggestions(db, company.id)
    if item_ids:
        wanted = set(item_ids)
        suggestions = [s for s in suggestions if s.item_id in wanted]
    if not suggestions:
        raise ValidationError("No items are below their reorder level")
    missing_wh = [s.item_code for s in suggestions if s.default_warehouse_id is None]
    if missing_wh:
        raise ValidationError(
            "Set a default warehouse on these items before drafting a reorder request: "
            + ", ".join(missing_wh),
            field="default_warehouse_id",
        )
    payload = MaterialRequestCreate(
        material_request_type="Purchase",
        posting_date=date.today(),
        remarks="Auto-generated from reorder levels",
        items=[
            MaterialRequestItemIn(
                item_id=s.item_id,
                qty=s.suggested_qty,
                warehouse_id=s.default_warehouse_id,
            )
            for s in suggestions
        ],
    )
    return await mr_service.create_material_request(db, payload, user)
