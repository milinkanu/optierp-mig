"""Delivery Note endpoints — Module 03/05."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.common import ListResponse
from app.schemas.stock import DeliveryNoteCreate, DeliveryNoteListItem, DeliveryNoteResponse
from app.services import delivery_note as service

router = APIRouter(prefix="/delivery-notes", tags=["stock: delivery notes"])


@router.post("", response_model=DeliveryNoteResponse, status_code=201,
             summary="Create a Delivery Note (draft)",
             description="Link rows to Sales Order items via sales_order_item_id; "
                         "rate defaults to the SO rate when linked.")
async def create(
    payload: DeliveryNoteCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Delivery Note", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> DeliveryNoteResponse:
    return DeliveryNoteResponse.model_validate(
        await service.create_delivery_note(db, payload, current_user)
    )


@router.get("", response_model=ListResponse[DeliveryNoteListItem],
            summary="List Delivery Notes",
            description="Paginated; filter by status and customer.")
async def list_notes(
    current_user: Annotated[CurrentUser, Depends(require_permission("Delivery Note", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    status: Annotated[str | None, Query(pattern="^(Draft|To Bill|Completed|Cancelled)$")] = None,
    customer_id: uuid.UUID | None = None,
) -> ListResponse[DeliveryNoteListItem]:
    notes, total = await service.list_delivery_notes(
        db, current_user.company_id, page, page_size, status, customer_id
    )
    return ListResponse(
        items=[DeliveryNoteListItem.model_validate(n) for n in notes],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{dn_id}", response_model=DeliveryNoteResponse,
            summary="Get a Delivery Note", description="Full note with item rows.")
async def get_note(
    dn_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Delivery Note", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> DeliveryNoteResponse:
    return DeliveryNoteResponse.model_validate(
        await service.get_delivery_note(db, dn_id, current_user.company_id)
    )


@router.post("/{dn_id}/submit", response_model=DeliveryNoteResponse,
             summary="Submit a Delivery Note",
             description="Stock out at valuation + GL (Dr COGS / Cr inventory); linked SO "
                         "rows accrue delivered qty and reservations release.")
async def submit(
    dn_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Delivery Note", "submit"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> DeliveryNoteResponse:
    return DeliveryNoteResponse.model_validate(
        await service.submit_delivery_note(db, dn_id, current_user)
    )


@router.post("/{dn_id}/cancel", response_model=DeliveryNoteResponse,
             summary="Cancel a Delivery Note",
             description="Reverses stock and GL. Blocked while invoices reference it.")
async def cancel(
    dn_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Delivery Note", "cancel"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> DeliveryNoteResponse:
    return DeliveryNoteResponse.model_validate(
        await service.cancel_delivery_note(db, dn_id, current_user)
    )
