"""Asset endpoints — fixed-asset register + depreciation.

CRUD + submit/cancel + a manual ``depreciate`` trigger (so depreciation is testable
without waiting for the daily job, and for catch-up runs). Asset Category and Location
masters are served by the metadata engine (/m/asset-category, /m/location).
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.assets import (
    AssetCreate,
    AssetDisposeIn,
    AssetListItem,
    AssetMoveIn,
    AssetResponse,
    AssetValueAdjustIn,
    DepreciateResult,
)
from app.schemas.common import ListResponse
from app.services import asset as service

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post(
    "",
    response_model=AssetResponse,
    status_code=201,
    summary="Create an asset",
    description="Registers a fixed asset (Draft) and generates its depreciation schedule "
    "(Straight Line, or Manual rows) so it can be previewed before submitting.",
)
async def create_asset(
    payload: AssetCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Asset", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> AssetResponse:
    return AssetResponse.model_validate(await service.create_asset(db, payload, current_user))


@router.get("", response_model=ListResponse[AssetListItem], summary="List assets")
async def list_assets(
    current_user: Annotated[CurrentUser, Depends(require_permission("Asset", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    status: str | None = None,
) -> ListResponse[AssetListItem]:
    items, total = await service.list_assets(db, current_user.company_id, page, page_size, status=status)
    return ListResponse(
        items=[AssetListItem.model_validate(a) for a in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{asset_id}", response_model=AssetResponse, summary="Get an asset")
async def get_asset(
    asset_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Asset", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> AssetResponse:
    return AssetResponse.model_validate(await service.get_asset(db, asset_id, current_user.company_id))


@router.post("/{asset_id}/submit", response_model=AssetResponse, summary="Submit an asset")
async def submit_asset(
    asset_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Asset", "submit"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> AssetResponse:
    return AssetResponse.model_validate(await service.submit_asset(db, asset_id, current_user))


@router.post("/{asset_id}/cancel", response_model=AssetResponse, summary="Cancel an asset")
async def cancel_asset(
    asset_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Asset", "cancel"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> AssetResponse:
    return AssetResponse.model_validate(await service.cancel_asset(db, asset_id, current_user))


@router.post(
    "/{asset_id}/depreciate",
    response_model=DepreciateResult,
    summary="Post due depreciation now",
    description="Books every due, unposted schedule row (schedule_date <= on_date) as a "
    "Journal Entry. Idempotent — already-posted rows are skipped.",
)
async def depreciate_asset(
    asset_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Asset", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    on_date: Annotated[date | None, Query(description="Post as if today were this date")] = None,
) -> DepreciateResult:
    return await service.depreciate_asset(db, asset_id, current_user, on_date=on_date)


@router.post(
    "/{asset_id}/cancel-depreciation",
    response_model=AssetResponse,
    summary="Cancel posted depreciation",
    description="Reverses all posted depreciation (reversing Journal Entries) and reopens the "
    "asset so its schedule can be re-posted. The ledger stays append-only.",
)
async def cancel_depreciation(
    asset_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Asset", "cancel"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> AssetResponse:
    return AssetResponse.model_validate(await service.cancel_depreciation(db, asset_id, current_user))


@router.post(
    "/{asset_id}/dispose",
    response_model=AssetResponse,
    summary="Sell or scrap an asset",
    description="Removes the asset's cost + accumulated depreciation and books the gain/loss "
    "vs book value as a Journal Entry. Depreciation halts after disposal.",
)
async def dispose_asset(
    asset_id: uuid.UUID,
    payload: AssetDisposeIn,
    current_user: Annotated[CurrentUser, Depends(require_permission("Asset", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> AssetResponse:
    return AssetResponse.model_validate(await service.dispose_asset(db, asset_id, payload, current_user))


@router.post(
    "/{asset_id}/move",
    response_model=AssetResponse,
    summary="Move an asset (location / custodian)",
    description="Records a transfer of the asset's location and/or custodian (no GL).",
)
async def move_asset(
    asset_id: uuid.UUID,
    payload: AssetMoveIn,
    current_user: Annotated[CurrentUser, Depends(require_permission("Asset", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> AssetResponse:
    return AssetResponse.model_validate(await service.move_asset(db, asset_id, payload, current_user))


@router.post(
    "/{asset_id}/adjust-value",
    response_model=AssetResponse,
    summary="Revalue an asset",
    description="Adjusts the asset to a new book value, posting the difference (impairment "
    "or write-up) to a Journal Entry and rescheduling the remaining depreciation.",
)
async def adjust_value(
    asset_id: uuid.UUID,
    payload: AssetValueAdjustIn,
    current_user: Annotated[CurrentUser, Depends(require_permission("Asset", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> AssetResponse:
    return AssetResponse.model_validate(
        await service.adjust_asset_value(db, asset_id, payload, current_user)
    )
