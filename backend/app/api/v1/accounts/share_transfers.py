"""Share Transfer endpoints — Module 02 (Share Management, no GL).

CRUD + submit/cancel for the cap-table register. Share Type and Shareholder masters
are served by the generic metadata engine (/m/share-type, /m/shareholder); the cap
table and ledger are read-only reports under /reports.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.accounts import (
    ShareTransferCreate,
    ShareTransferListItem,
    ShareTransferResponse,
)
from app.schemas.common import ListResponse
from app.services import share_transfer as service

router = APIRouter(prefix="/share-transfers", tags=["accounts: share transfers"])


@router.post(
    "",
    response_model=ShareTransferResponse,
    status_code=201,
    summary="Create a share transfer (draft)",
    description="Issue (mint), Transfer (holder→holder) or Buyback (retire) shares. "
    "Holdings are validated and become effective on submit; no GL is posted.",
)
async def create_share_transfer(
    payload: ShareTransferCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Share Transfer", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> ShareTransferResponse:
    return ShareTransferResponse.model_validate(
        await service.create_share_transfer(db, payload, current_user)
    )


@router.get(
    "",
    response_model=ListResponse[ShareTransferListItem],
    summary="List share transfers",
)
async def list_share_transfers(
    current_user: Annotated[CurrentUser, Depends(require_permission("Share Transfer", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    status: str | None = None,
) -> ListResponse[ShareTransferListItem]:
    rows, total = await service.list_share_transfers(
        db, current_user.company_id, page, page_size, status=status
    )
    return ListResponse(
        items=[ShareTransferListItem.model_validate(r) for r in rows],
        total=total, page=page, page_size=page_size,
    )


@router.get(
    "/{doc_id}",
    response_model=ShareTransferResponse,
    summary="Get a share transfer",
)
async def get_share_transfer(
    doc_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Share Transfer", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> ShareTransferResponse:
    return ShareTransferResponse.model_validate(
        await service.get_share_transfer(db, doc_id, current_user.company_id)
    )


@router.post(
    "/{doc_id}/submit",
    response_model=ShareTransferResponse,
    summary="Submit a share transfer",
)
async def submit_share_transfer(
    doc_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Share Transfer", "submit"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> ShareTransferResponse:
    return ShareTransferResponse.model_validate(
        await service.submit_share_transfer(db, doc_id, current_user)
    )


@router.post(
    "/{doc_id}/cancel",
    response_model=ShareTransferResponse,
    summary="Cancel a share transfer",
)
async def cancel_share_transfer(
    doc_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Share Transfer", "cancel"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> ShareTransferResponse:
    return ShareTransferResponse.model_validate(
        await service.cancel_share_transfer(db, doc_id, current_user)
    )
