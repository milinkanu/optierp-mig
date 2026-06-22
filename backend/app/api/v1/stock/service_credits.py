"""Service Credit endpoints — prepaid service units with usage drawdown."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.common import ListResponse
from app.schemas.stock import (
    ServiceCreditCreate,
    ServiceCreditListItem,
    ServiceCreditResponse,
    ServiceCreditUsageIn,
)
from app.services import service_credit as service

router = APIRouter(prefix="/service-credits", tags=["stock: service credits"])


@router.post("", response_model=ServiceCreditResponse, status_code=201,
             summary="Create a Service Credit",
             description="A prepaid block of a service measured in units (UOM comes from the item). "
                         "Example: 100 hours of support. Draw it down with usage entries.")
async def create(
    payload: ServiceCreditCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Service Credit", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> ServiceCreditResponse:
    return ServiceCreditResponse.model_validate(
        await service.create_service_credit(db, payload, current_user)
    )


@router.get("", response_model=ListResponse[ServiceCreditListItem],
            summary="List Service Credits", description="Newest first; filter by status.")
async def list_credits(
    current_user: Annotated[CurrentUser, Depends(require_permission("Service Credit", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    status: Annotated[str | None, Query(pattern="^(Active|Exhausted|Expired)$")] = None,
) -> ListResponse[ServiceCreditListItem]:
    credits, total = await service.list_service_credits(
        db, current_user.company_id, page, page_size, status
    )
    return ListResponse(
        items=[ServiceCreditListItem.model_validate(c) for c in credits],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{credit_id}", response_model=ServiceCreditResponse,
            summary="Get a Service Credit", description="Full credit with its usage log.")
async def get_credit(
    credit_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Service Credit", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> ServiceCreditResponse:
    return ServiceCreditResponse.model_validate(
        await service.get_service_credit(db, credit_id, current_user.company_id)
    )


@router.post("/{credit_id}/usage", response_model=ServiceCreditResponse,
             summary="Log usage against a Service Credit",
             description="Draws down the remaining balance (blocked from going negative).")
async def add_usage(
    credit_id: uuid.UUID,
    payload: ServiceCreditUsageIn,
    current_user: Annotated[CurrentUser, Depends(require_permission("Service Credit", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> ServiceCreditResponse:
    return ServiceCreditResponse.model_validate(
        await service.add_usage(db, credit_id, payload, current_user)
    )
