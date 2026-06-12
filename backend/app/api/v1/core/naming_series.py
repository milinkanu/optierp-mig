"""Naming series endpoints — Module 01."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.naming import peek_next_name
from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.core import NamingSeriesPreviewRequest, NamingSeriesPreviewResponse

router = APIRouter(prefix="/naming-series", tags=["core: naming series"])


@router.post(
    "/preview",
    response_model=NamingSeriesPreviewResponse,
    summary="Preview the next name in a series",
    description="Expands a pattern like `SINV-.YYYY.-` for the active company without "
    "consuming a number. Example response: `{'pattern': 'SINV-.YYYY.-', "
    "'next_name': 'SINV-2026-00001'}`",
)
async def preview_series(
    payload: NamingSeriesPreviewRequest,
    current_user: Annotated[CurrentUser, Depends(require_permission("Naming Series", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> NamingSeriesPreviewResponse:
    if current_user.company_id is None:
        raise ValidationError("An active company is required to preview naming series")
    next_name = await peek_next_name(db, payload.pattern, current_user.company_id)
    return NamingSeriesPreviewResponse(pattern=payload.pattern, next_name=next_name)
