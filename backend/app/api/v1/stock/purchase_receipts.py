"""Purchase Receipt endpoints — Module 03/04."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.common import ListResponse
from app.schemas.stock import (
    PurchaseReceiptCreate,
    PurchaseReceiptListItem,
    PurchaseReceiptResponse,
)
from app.services import purchase_receipt as service

router = APIRouter(prefix="/purchase-receipts", tags=["stock: purchase receipts"])


@router.post("", response_model=PurchaseReceiptResponse, status_code=201,
             summary="Create a Purchase Receipt (draft)",
             description="Link rows to Purchase Order items via purchase_order_item_id; "
                         "rate defaults to the PO rate when linked.")
async def create(
    payload: PurchaseReceiptCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Purchase Receipt", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PurchaseReceiptResponse:
    return PurchaseReceiptResponse.model_validate(
        await service.create_purchase_receipt(db, payload, current_user)
    )


@router.get("", response_model=ListResponse[PurchaseReceiptListItem],
            summary="List Purchase Receipts",
            description="Paginated; filter by status and supplier.")
async def list_receipts(
    current_user: Annotated[CurrentUser, Depends(require_permission("Purchase Receipt", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    status: Annotated[str | None, Query(pattern="^(Draft|To Bill|Completed|Cancelled)$")] = None,
    supplier_id: uuid.UUID | None = None,
) -> ListResponse[PurchaseReceiptListItem]:
    receipts, total = await service.list_purchase_receipts(
        db, current_user.company_id, page, page_size, status, supplier_id
    )
    return ListResponse(
        items=[PurchaseReceiptListItem.model_validate(r) for r in receipts],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{pr_id}", response_model=PurchaseReceiptResponse,
            summary="Get a Purchase Receipt", description="Full receipt with item rows.")
async def get_receipt(
    pr_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Purchase Receipt", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PurchaseReceiptResponse:
    return PurchaseReceiptResponse.model_validate(
        await service.get_purchase_receipt(db, pr_id, current_user.company_id)
    )


@router.post("/{pr_id}/submit", response_model=PurchaseReceiptResponse,
             summary="Submit a Purchase Receipt",
             description="Stock in + GL (Dr inventory / Cr Stock Received But Not Billed); "
                         "linked PO rows accrue received qty.")
async def submit(
    pr_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Purchase Receipt", "submit"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PurchaseReceiptResponse:
    return PurchaseReceiptResponse.model_validate(
        await service.submit_purchase_receipt(db, pr_id, current_user)
    )


@router.post("/{pr_id}/cancel", response_model=PurchaseReceiptResponse,
             summary="Cancel a Purchase Receipt",
             description="Reverses stock and GL. Blocked while invoices reference it.")
async def cancel(
    pr_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Purchase Receipt", "cancel"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PurchaseReceiptResponse:
    return PurchaseReceiptResponse.model_validate(
        await service.cancel_purchase_receipt(db, pr_id, current_user)
    )
