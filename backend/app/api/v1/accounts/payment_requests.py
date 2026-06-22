"""Payment Request endpoints — Module 02 (collections).

CRUD + status. Printing/emailing reuses the generic /print/{doctype}/{id} endpoints
(Payment Request is registered in print_service.PRINT_REGISTRY).
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.accounts import (
    PaymentRequestCreate,
    PaymentRequestListItem,
    PaymentRequestResponse,
)
from app.schemas.common import ListResponse
from app.services import payment_request as service

router = APIRouter(prefix="/payment-requests", tags=["accounts: payment requests"])


@router.post(
    "",
    response_model=PaymentRequestResponse,
    status_code=201,
    summary="Create a payment request",
    description="Ask a customer to pay an amount, optionally against a Sales Invoice. "
    "Email/print it via the generic /print endpoints.",
)
async def create_payment_request(
    payload: PaymentRequestCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Payment Request", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PaymentRequestResponse:
    return PaymentRequestResponse.model_validate(
        await service.create_payment_request(db, payload, current_user)
    )


@router.get(
    "",
    response_model=ListResponse[PaymentRequestListItem],
    summary="List payment requests",
)
async def list_payment_requests(
    current_user: Annotated[CurrentUser, Depends(require_permission("Payment Request", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    status: str | None = None,
) -> ListResponse[PaymentRequestListItem]:
    items, total = await service.list_payment_requests(
        db, current_user.company_id, page, page_size, status=status
    )
    return ListResponse(
        items=[PaymentRequestListItem.model_validate(p) for p in items],
        total=total, page=page, page_size=page_size,
    )


@router.get(
    "/{request_id}",
    response_model=PaymentRequestResponse,
    summary="Get a payment request",
)
async def get_payment_request(
    request_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Payment Request", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PaymentRequestResponse:
    return PaymentRequestResponse.model_validate(
        await service.get_payment_request(db, request_id, current_user.company_id)
    )


@router.post(
    "/{request_id}/status",
    response_model=PaymentRequestResponse,
    summary="Set status (Requested / Paid / Cancelled)",
)
async def set_status(
    request_id: uuid.UUID,
    status: Annotated[Literal["Requested", "Paid", "Cancelled"], Query()],
    current_user: Annotated[CurrentUser, Depends(require_permission("Payment Request", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PaymentRequestResponse:
    return PaymentRequestResponse.model_validate(
        await service.set_status(db, request_id, status, current_user)
    )
