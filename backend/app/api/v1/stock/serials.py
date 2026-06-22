"""Serial No endpoints — Module 03 (Phase 5).

Read-only: serial numbers are created and moved by stock transactions (receipts,
deliveries, stock entries), not by free-form CRUD. This surfaces the master for
lookup (status, warehouse, warranty) — e.g. warranty/RMA checks.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.common import ListResponse
from app.schemas.stock import SerialNoListItem, SerialNoResponse
from app.services import stock_serials as service

router = APIRouter(prefix="/serial-nos", tags=["stock: serial nos"])


@router.get("", response_model=ListResponse[SerialNoListItem],
            summary="List serial numbers",
            description="Paginated; filter by item, status (In Stock / Delivered / Returned), "
                        "warehouse, or serial-number search.")
async def list_serials(
    current_user: Annotated[CurrentUser, Depends(require_permission("Serial No", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    item_id: uuid.UUID | None = None,
    status: Annotated[str | None, Query(pattern="^(In Stock|Delivered|Returned)$")] = None,
    warehouse_id: uuid.UUID | None = None,
    search: str | None = None,
) -> ListResponse[SerialNoListItem]:
    rows, total = await service.list_serial_nos(
        db, current_user.company_id, page, page_size, item_id, status, warehouse_id, search
    )
    return ListResponse(
        items=[SerialNoListItem.model_validate(r) for r in rows],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{serial_id}", response_model=SerialNoResponse, summary="Get a serial number")
async def get_serial(
    serial_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Serial No", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> SerialNoResponse:
    return SerialNoResponse.model_validate(
        await service.get_serial_no(db, serial_id, current_user.company_id)
    )
