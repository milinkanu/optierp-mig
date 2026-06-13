"""Material Request endpoints — Module 03."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.common import ListResponse
from app.schemas.stock import (
    MaterialRequestCreate,
    MaterialRequestListItem,
    MaterialRequestResponse,
)
from app.services import material_request as service

router = APIRouter(prefix="/material-requests", tags=["stock: material requests"])


@router.post("", response_model=MaterialRequestResponse, status_code=201,
             summary="Create a Material Request (draft)",
             description="Demand document; Purchase Orders later link rows back to it.")
async def create(
    payload: MaterialRequestCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Material Request", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> MaterialRequestResponse:
    return MaterialRequestResponse.model_validate(
        await service.create_material_request(db, payload, current_user)
    )


@router.get("", response_model=ListResponse[MaterialRequestListItem],
            summary="List Material Requests", description="Paginated; filter by status.")
async def list_requests(
    current_user: Annotated[CurrentUser, Depends(require_permission("Material Request", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    status: Annotated[
        str | None, Query(pattern="^(Draft|Pending|Partially Ordered|Ordered|Cancelled)$")
    ] = None,
) -> ListResponse[MaterialRequestListItem]:
    requests, total = await service.list_material_requests(
        db, current_user.company_id, page, page_size, status
    )
    return ListResponse(
        items=[MaterialRequestListItem.model_validate(r) for r in requests],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{mr_id}", response_model=MaterialRequestResponse,
            summary="Get a Material Request", description="Full request with item rows.")
async def get_request(
    mr_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Material Request", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> MaterialRequestResponse:
    return MaterialRequestResponse.model_validate(
        await service.get_material_request(db, mr_id, current_user.company_id)
    )


@router.post("/{mr_id}/submit", response_model=MaterialRequestResponse,
             summary="Submit a Material Request", description="Status becomes Pending.")
async def submit(
    mr_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Material Request", "submit"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> MaterialRequestResponse:
    return MaterialRequestResponse.model_validate(
        await service.submit_material_request(db, mr_id, current_user)
    )


@router.post("/{mr_id}/cancel", response_model=MaterialRequestResponse,
             summary="Cancel a Material Request", description="No stock or GL effect.")
async def cancel(
    mr_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Material Request", "cancel"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> MaterialRequestResponse:
    return MaterialRequestResponse.model_validate(
        await service.cancel_material_request(db, mr_id, current_user)
    )
