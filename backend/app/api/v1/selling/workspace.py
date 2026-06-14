"""Selling workspace endpoint — stats for the Selling module workspace page."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.services import module_workspace as svc

router = APIRouter(prefix="/selling", tags=["selling: workspace"])


@router.get(
    "/workspace",
    summary="Selling workspace stats",
    description="Number cards (Sales Orders count, total & average value) and a "
    "12-month Sales Order trend for the Selling workspace page.",
)
async def workspace_stats(
    current_user: Annotated[CurrentUser, Depends(require_permission("Sales Order", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> dict[str, Any]:
    if current_user.company_id is None:
        raise ValidationError("An active company is required")
    return await svc.get_selling_workspace(db, current_user.company_id)
