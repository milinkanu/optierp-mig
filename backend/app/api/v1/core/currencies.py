"""Currency & exchange-rate endpoints — Module 01."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.core import CurrencyExchangeCreate, CurrencyExchangeResponse, CurrencyResponse
from app.services import settings as settings_service

router = APIRouter(prefix="/currencies", tags=["core: currencies"])


@router.get(
    "",
    response_model=list[CurrencyResponse],
    summary="List currencies",
    description="Global currency master, seeded from ISO 4217 data.",
)
async def list_currencies(
    current_user: Annotated[CurrentUser, Depends(require_permission("Currency", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    enabled_only: bool = False,
) -> list[CurrencyResponse]:
    currencies = await settings_service.list_currencies(db, enabled_only)
    return [CurrencyResponse.model_validate(c) for c in currencies]


@router.post(
    "/exchange",
    response_model=CurrencyExchangeResponse,
    status_code=201,
    summary="Record an exchange rate",
    description="Stores a dated exchange rate. Example: `{'date': '2026-06-11', "
    "'from_currency': 'USD', 'to_currency': 'INR', 'exchange_rate': 84.2}`",
)
async def create_exchange_rate(
    payload: CurrencyExchangeCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Currency Exchange", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> CurrencyExchangeResponse:
    exchange = await settings_service.create_currency_exchange(db, payload, current_user)
    return CurrencyExchangeResponse.model_validate(exchange)


@router.get(
    "/exchange/rate",
    response_model=float,
    summary="Get the latest exchange rate",
    description="Latest stored rate for a currency pair; returns 1.0 for identical currencies.",
)
async def get_exchange_rate(
    current_user: Annotated[CurrentUser, Depends(require_permission("Currency Exchange", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    from_currency: Annotated[str, Query(min_length=3, max_length=3)],
    to_currency: Annotated[str, Query(min_length=3, max_length=3)],
    for_selling: bool = True,
) -> float:
    return await settings_service.get_exchange_rate(
        db, from_currency.upper(), to_currency.upper(), for_selling=for_selling
    )
