"""Journal Entry endpoints — Module 02."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.accounts import JournalEntryCreate, JournalEntryListItem, JournalEntryResponse
from app.schemas.common import ListResponse
from app.services import journal_entry as service

router = APIRouter(prefix="/journal-entries", tags=["accounts: journal entries"])


@router.post(
    "",
    response_model=JournalEntryResponse,
    status_code=201,
    summary="Create a Journal Entry (draft)",
    description="Balanced multi-row voucher; party is mandatory on receivable/payable "
    "rows. Example: Dr Rent Expense 5000 / Cr Cash 5000.",
)
async def create(
    payload: JournalEntryCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Journal Entry", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> JournalEntryResponse:
    return JournalEntryResponse.model_validate(
        await service.create_journal_entry(db, payload, current_user)
    )


@router.get(
    "",
    response_model=ListResponse[JournalEntryListItem],
    summary="List Journal Entries",
    description="Paginated, newest first; filter by docstatus (0/1/2).",
)
async def list_entries(
    current_user: Annotated[CurrentUser, Depends(require_permission("Journal Entry", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    docstatus: Annotated[int | None, Query(ge=0, le=2)] = None,
) -> ListResponse[JournalEntryListItem]:
    entries, total = await service.list_journal_entries(
        db, current_user.company_id, page, page_size, docstatus
    )
    return ListResponse(
        items=[JournalEntryListItem.model_validate(e) for e in entries],
        total=total, page=page, page_size=page_size,
    )


@router.get(
    "/{entry_id}",
    response_model=JournalEntryResponse,
    summary="Get a Journal Entry",
    description="Full voucher with account rows.",
)
async def get_entry(
    entry_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Journal Entry", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> JournalEntryResponse:
    return JournalEntryResponse.model_validate(
        await service.get_journal_entry(db, entry_id, current_user.company_id)
    )


@router.post(
    "/{entry_id}/submit",
    response_model=JournalEntryResponse,
    summary="Submit a Journal Entry",
    description="Posts the GL entries (docstatus 0 -> 1). The voucher must balance.",
)
async def submit(
    entry_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Journal Entry", "submit"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> JournalEntryResponse:
    return JournalEntryResponse.model_validate(
        await service.submit_journal_entry(db, entry_id, current_user)
    )


@router.post(
    "/{entry_id}/cancel",
    response_model=JournalEntryResponse,
    summary="Cancel a Journal Entry",
    description="Writes reversing GL entries (docstatus 1 -> 2); the ledger stays append-only.",
)
async def cancel(
    entry_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Journal Entry", "cancel"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> JournalEntryResponse:
    return JournalEntryResponse.model_validate(
        await service.cancel_journal_entry(db, entry_id, current_user)
    )
