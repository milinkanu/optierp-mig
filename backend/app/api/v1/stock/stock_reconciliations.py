"""Stock Reconciliation endpoints — Module 03."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.common import ListResponse
from app.schemas.stock import (
    StockReconciliationCreate,
    StockReconciliationListItem,
    StockReconciliationResponse,
)
from app.services import stock_reconciliation as service

router = APIRouter(prefix="/stock-reconciliations", tags=["stock: stock reconciliations"])


@router.post("", response_model=StockReconciliationResponse, status_code=201,
             summary="Create a Stock Reconciliation (draft)",
             description="Sets each (item, warehouse) row to an absolute target qty and rate. "
                         "Leave valuation_rate empty to keep the current/item rate. "
                         "Example: `{'purpose': 'Opening Stock', 'posting_date': '2026-06-18', "
                         "'items': [{'item_id': '...', 'warehouse_id': '...', 'qty': 100, "
                         "'valuation_rate': 500}]}`")
async def create(
    payload: StockReconciliationCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Stock Reconciliation", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> StockReconciliationResponse:
    return StockReconciliationResponse.model_validate(
        await service.create_stock_reconciliation(db, payload, current_user)
    )


@router.get("", response_model=ListResponse[StockReconciliationListItem],
            summary="List Stock Reconciliations",
            description="Paginated, newest first; filter by purpose.")
async def list_recons(
    current_user: Annotated[CurrentUser, Depends(require_permission("Stock Reconciliation", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    purpose: Annotated[str | None, Query(pattern="^(Opening Stock|Stock Reconciliation)$")] = None,
) -> ListResponse[StockReconciliationListItem]:
    recons, total = await service.list_stock_reconciliations(
        db, current_user.company_id, page, page_size, purpose
    )
    return ListResponse(
        items=[StockReconciliationListItem.model_validate(r) for r in recons],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{recon_id}", response_model=StockReconciliationResponse,
            summary="Get a Stock Reconciliation", description="Full document with item rows.")
async def get_recon(
    recon_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Stock Reconciliation", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> StockReconciliationResponse:
    return StockReconciliationResponse.model_validate(
        await service.get_stock_reconciliation(db, recon_id, current_user.company_id)
    )


@router.post("/{recon_id}/submit", response_model=StockReconciliationResponse,
             summary="Submit a Stock Reconciliation",
             description="Posts the qty/value difference vs the current Bin to the stock ledger "
                         "and (perpetual inventory) the Stock Adjustment GL.")
async def submit(
    recon_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Stock Reconciliation", "submit"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> StockReconciliationResponse:
    return StockReconciliationResponse.model_validate(
        await service.submit_stock_reconciliation(db, recon_id, current_user)
    )


@router.post("/{recon_id}/cancel", response_model=StockReconciliationResponse,
             summary="Cancel a Stock Reconciliation",
             description="Reverses stock and GL via mirror entries (blocked if stock has since "
                         "moved at a different valuation).")
async def cancel(
    recon_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Stock Reconciliation", "cancel"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> StockReconciliationResponse:
    return StockReconciliationResponse.model_validate(
        await service.cancel_stock_reconciliation(db, recon_id, current_user)
    )
