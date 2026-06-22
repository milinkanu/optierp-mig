"""Reorder automation endpoints — Module 03."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.stock import MaterialRequestResponse, ReorderMaterialRequest, ReorderRow
from app.services import stock_reorder as service

router = APIRouter(prefix="/stock-reorder", tags=["stock: reorder"])


@router.get("", response_model=list[ReorderRow],
            summary="Reorder suggestions",
            description="Items whose company-wide projected qty (on-hand + on-order − reserved) "
                        "is below their reorder level, with a suggested order quantity.")
async def suggestions(
    current_user: Annotated[CurrentUser, Depends(require_permission("Item", "report"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[ReorderRow]:
    return await service.reorder_suggestions(db, current_user.company_id)


@router.post("/material-request", response_model=MaterialRequestResponse, status_code=201,
             summary="Create a Material Request from reorder levels",
             description="Drafts a single Purchase Material Request for the below-reorder items "
                         "(optionally restricted to item_ids). Review and submit it as usual.")
async def create_material_request(
    payload: ReorderMaterialRequest,
    current_user: Annotated[CurrentUser, Depends(require_permission("Material Request", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> MaterialRequestResponse:
    return MaterialRequestResponse.model_validate(
        await service.create_reorder_material_request(db, current_user, payload.item_ids)
    )
