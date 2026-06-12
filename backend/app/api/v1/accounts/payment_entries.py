"""Payment Entry endpoints — Module 02."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.accounts import PaymentEntryCreate, PaymentEntryListItem, PaymentEntryResponse
from app.schemas.common import ListResponse
from app.services import payment_entry as service

router = APIRouter(prefix="/payment-entries", tags=["accounts: payment entries"])


class ClearanceUpdate(BaseModel):
    clearance_date: date


@router.post(
    "",
    response_model=PaymentEntryResponse,
    status_code=201,
    summary="Create a Payment Entry (draft)",
    description="Receive (customer) or Pay (supplier) with invoice allocations. "
    "Example: `{'payment_type': 'Receive', 'party_type': 'Customer', 'party_id': '...', "
    "'paid_to_id': '<bank account>', 'paid_amount': 1180, 'posting_date': '2026-06-12', "
    "'references': [{'reference_doctype': 'Sales Invoice', 'reference_id': '...', "
    "'allocated_amount': 1180}]}`",
)
async def create(
    payload: PaymentEntryCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Payment Entry", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PaymentEntryResponse:
    return PaymentEntryResponse.model_validate(
        await service.create_payment_entry(db, payload, current_user)
    )


@router.get(
    "",
    response_model=ListResponse[PaymentEntryListItem],
    summary="List Payment Entries",
    description="Paginated, newest first.",
)
async def list_entries(
    current_user: Annotated[CurrentUser, Depends(require_permission("Payment Entry", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
) -> ListResponse[PaymentEntryListItem]:
    entries, total = await service.list_payment_entries(db, current_user.company_id, page, page_size)
    return ListResponse(
        items=[PaymentEntryListItem.model_validate(e) for e in entries],
        total=total, page=page, page_size=page_size,
    )


@router.get(
    "/{entry_id}",
    response_model=PaymentEntryResponse,
    summary="Get a Payment Entry",
    description="Full payment with references and deductions.",
)
async def get_entry(
    entry_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Payment Entry", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PaymentEntryResponse:
    return PaymentEntryResponse.model_validate(
        await service.get_payment_entry(db, entry_id, current_user.company_id)
    )


@router.post(
    "/{entry_id}/submit",
    response_model=PaymentEntryResponse,
    summary="Submit a Payment Entry",
    description="Posts GL and applies the spec's outstanding recalculation to every "
    "referenced invoice (outstanding -= allocated).",
)
async def submit(
    entry_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Payment Entry", "submit"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PaymentEntryResponse:
    return PaymentEntryResponse.model_validate(
        await service.submit_payment_entry(db, entry_id, current_user)
    )


@router.post(
    "/{entry_id}/cancel",
    response_model=PaymentEntryResponse,
    summary="Cancel a Payment Entry",
    description="Reverses GL and restores invoice outstanding amounts.",
)
async def cancel(
    entry_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Payment Entry", "cancel"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PaymentEntryResponse:
    return PaymentEntryResponse.model_validate(
        await service.cancel_payment_entry(db, entry_id, current_user)
    )


@router.patch(
    "/{entry_id}/clearance",
    response_model=PaymentEntryResponse,
    summary="Set bank clearance date",
    description="Marks the date the bank cleared this payment (bank reconciliation).",
)
async def set_clearance(
    entry_id: uuid.UUID,
    payload: ClearanceUpdate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Payment Entry", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PaymentEntryResponse:
    return PaymentEntryResponse.model_validate(
        await service.set_clearance_date(db, entry_id, payload.clearance_date, current_user)
    )
