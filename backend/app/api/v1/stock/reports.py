"""Stock report endpoints — Module 03."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.stock import StockBalanceRow, StockLedgerRow
from app.services import stock_reports as service

router = APIRouter(prefix="/reports", tags=["stock: reports"])


@router.get("/stock-balance", response_model=list[StockBalanceRow],
            summary="Stock Balance",
            description="Per item/warehouse: actual, reserved, ordered, projected qty, "
                        "valuation rate and stock value (from Bin).")
async def stock_balance(
    current_user: Annotated[CurrentUser, Depends(require_permission("Stock Ledger Entry", "report"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    warehouse_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
) -> list[StockBalanceRow]:
    return await service.stock_balance(db, current_user.company_id, warehouse_id, item_id)


@router.get("/stock-ledger", response_model=list[StockLedgerRow],
            summary="Stock Ledger",
            description="Chronological stock movements with running qty and valuation.")
async def stock_ledger(
    current_user: Annotated[CurrentUser, Depends(require_permission("Stock Ledger Entry", "report"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    item_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[StockLedgerRow]:
    return await service.stock_ledger(
        db, current_user.company_id, item_id, warehouse_id, from_date, to_date
    )
