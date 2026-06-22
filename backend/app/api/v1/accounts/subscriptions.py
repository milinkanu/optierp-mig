"""Subscription endpoints — Module 02 (recurring billing).

CRUD + cancel + a manual ``generate-invoice`` trigger (so the feature is testable
without waiting for the daily cron, and a user can bill early). The Subscription Plan
master is served by the generic metadata engine (/m/subscription-plan).
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.accounts import (
    GenerateInvoiceResult,
    SubscriptionCreate,
    SubscriptionListItem,
    SubscriptionResponse,
)
from app.schemas.common import ListResponse
from app.services import subscription as service

router = APIRouter(prefix="/subscriptions", tags=["accounts: subscriptions"])


@router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=201,
    summary="Create a subscription",
    description="Attach one or more Subscription Plans to a customer. A daily job (or the "
    "manual generate-invoice trigger) bills each cycle as a real Sales Invoice.",
)
async def create_subscription(
    payload: SubscriptionCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Subscription", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> SubscriptionResponse:
    return SubscriptionResponse.model_validate(
        await service.create_subscription(db, payload, current_user)
    )


@router.get(
    "",
    response_model=ListResponse[SubscriptionListItem],
    summary="List subscriptions",
)
async def list_subscriptions(
    current_user: Annotated[CurrentUser, Depends(require_permission("Subscription", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    status: str | None = None,
) -> ListResponse[SubscriptionListItem]:
    items, total = await service.list_subscriptions(
        db, current_user.company_id, page, page_size, status=status
    )
    return ListResponse(
        items=[SubscriptionListItem.model_validate(s) for s in items],
        total=total, page=page, page_size=page_size,
    )


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionResponse,
    summary="Get a subscription",
)
async def get_subscription(
    subscription_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Subscription", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> SubscriptionResponse:
    return SubscriptionResponse.model_validate(
        await service.get_subscription(db, subscription_id, current_user.company_id)
    )


@router.post(
    "/{subscription_id}/cancel",
    response_model=SubscriptionResponse,
    summary="Cancel a subscription",
)
async def cancel_subscription(
    subscription_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Subscription", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> SubscriptionResponse:
    return SubscriptionResponse.model_validate(
        await service.cancel_subscription(db, subscription_id, current_user)
    )


@router.post(
    "/{subscription_id}/generate-invoice",
    response_model=GenerateInvoiceResult,
    summary="Generate the due invoice now",
    description="Bill the current period on demand (same logic as the daily job). Idempotent: "
    "returns generated=false when the subscription's cursor is not yet due.",
)
async def generate_invoice(
    subscription_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Subscription", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    on_date: Annotated[date | None, Query(description="Bill as if today were this date")] = None,
) -> GenerateInvoiceResult:
    return await service.generate_for_subscription(
        db, subscription_id, current_user, on_date=on_date
    )
