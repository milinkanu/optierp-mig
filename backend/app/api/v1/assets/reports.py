"""Asset report endpoints (Phase 4) — read-only."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.assets import DepreciationLedgerRow, FixedAssetRegisterRow
from app.services import asset_reports as svc

router = APIRouter(prefix="/asset-reports", tags=["assets: reports"])


@router.get(
    "/fixed-asset-register",
    response_model=list[FixedAssetRegisterRow],
    summary="Fixed Asset Register / Net Block",
    description="Each asset's gross, accumulated depreciation and book value as of a date. "
    "Disposed assets are excluded unless include_disposed=true.",
)
async def fixed_asset_register(
    current_user: Annotated[CurrentUser, Depends(require_permission("Asset", "report"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    as_of: date | None = None,
    category_id: uuid.UUID | None = None,
    include_disposed: bool = False,
) -> list[FixedAssetRegisterRow]:
    if current_user.company_id is None:
        raise ValidationError("An active company is required")
    return await svc.fixed_asset_register(
        db, current_user.company_id, as_of=as_of, category_id=category_id,
        include_disposed=include_disposed,
    )


@router.get(
    "/depreciation-ledger",
    response_model=list[DepreciationLedgerRow],
    summary="Asset Depreciation Ledger",
    description="Every posted depreciation entry (date, asset, amount, Journal Entry).",
)
async def depreciation_ledger(
    current_user: Annotated[CurrentUser, Depends(require_permission("Asset", "report"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    asset_id: uuid.UUID | None = None,
) -> list[DepreciationLedgerRow]:
    if current_user.company_id is None:
        raise ValidationError("An active company is required")
    return await svc.depreciation_ledger(
        db, current_user.company_id, from_date=from_date, to_date=to_date, asset_id=asset_id,
    )
