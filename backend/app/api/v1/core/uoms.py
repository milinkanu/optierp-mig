"""Unit of Measure endpoints — Module 01."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.core import (
    UOMConversionCreate,
    UOMConversionResponse,
    UOMCreate,
    UOMResponse,
)
from app.services import settings as settings_service

router = APIRouter(prefix="/uoms", tags=["core: uoms"])


@router.get(
    "",
    response_model=list[UOMResponse],
    summary="List units of measure",
    description="Global UOM master (Nos, Kg, Litre, ...).",
)
async def list_uoms(
    current_user: Annotated[CurrentUser, Depends(require_permission("UOM", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[UOMResponse]:
    return [UOMResponse.model_validate(u) for u in await settings_service.list_uoms(db)]


@router.post(
    "",
    response_model=UOMResponse,
    status_code=201,
    summary="Create a unit of measure",
    description="Example: `{'uom_name': 'Box', 'must_be_whole_number': true}`",
)
async def create_uom(
    payload: UOMCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("UOM", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> UOMResponse:
    return UOMResponse.model_validate(await settings_service.create_uom(db, payload, current_user))


@router.post(
    "/conversions",
    response_model=UOMConversionResponse,
    status_code=201,
    summary="Create a UOM conversion factor",
    description="Example: `{'from_uom': 'Kg', 'to_uom': 'Gram', 'value': 1000}`",
)
async def create_uom_conversion(
    payload: UOMConversionCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("UOM", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> UOMConversionResponse:
    conversion = await settings_service.create_uom_conversion(db, payload, current_user)
    return UOMConversionResponse.model_validate(conversion)
