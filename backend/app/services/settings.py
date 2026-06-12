"""System settings + masters (currency, country, UOM, roles) — Module 01."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateError, NotFoundError
from app.core.security import CurrentUser
from app.models.core import (
    Currency,
    CurrencyExchange,
    Role,
    RolePermission,
    SystemSetting,
    UOM,
    UOMConversion,
)
from app.schemas.core import (
    CurrencyExchangeCreate,
    RoleCreate,
    RolePermissionUpsert,
    SystemSettingUpsert,
    UOMConversionCreate,
    UOMCreate,
)


# --- System settings -------------------------------------------------------------


async def upsert_setting(db: AsyncSession, payload: SystemSettingUpsert, user: CurrentUser) -> SystemSetting:
    setting = await db.scalar(
        select(SystemSetting).where(
            SystemSetting.key == payload.key, SystemSetting.company_id == payload.company_id
        )
    )
    if setting is None:
        setting = SystemSetting(key=payload.key, company_id=payload.company_id, owner=user.id)
        db.add(setting)
    setting.value = payload.value
    setting.modified_by = user.id
    await db.commit()
    await db.refresh(setting)
    return setting


async def get_setting(db: AsyncSession, key: str, company_id: uuid.UUID | None) -> SystemSetting:
    """Company-scoped value wins over the instance-wide default."""
    if company_id is not None:
        scoped = await db.scalar(
            select(SystemSetting).where(SystemSetting.key == key, SystemSetting.company_id == company_id)
        )
        if scoped is not None:
            return scoped
    setting = await db.scalar(
        select(SystemSetting).where(SystemSetting.key == key, SystemSetting.company_id.is_(None))
    )
    if setting is None:
        raise NotFoundError(f"Setting '{key}' not found")
    return setting


# --- Roles & permissions -----------------------------------------------------------


async def create_role(db: AsyncSession, payload: RoleCreate, user: CurrentUser) -> Role:
    if await db.scalar(select(Role).where(Role.name == payload.name)):
        raise DuplicateError("Role already exists", field="name")
    role = Role(name=payload.name, description=payload.description, owner=user.id)
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


async def list_roles(db: AsyncSession) -> list[Role]:
    return list((await db.execute(select(Role).order_by(Role.name))).scalars().all())


async def upsert_role_permission(
    db: AsyncSession, payload: RolePermissionUpsert, user: CurrentUser
) -> RolePermission:
    perm = await db.scalar(
        select(RolePermission).where(
            RolePermission.role == payload.role,
            RolePermission.doctype == payload.doctype,
            RolePermission.company_id == payload.company_id,
        )
    )
    if perm is None:
        perm = RolePermission(role=payload.role, doctype=payload.doctype, company_id=payload.company_id)
        db.add(perm)
    for field, value in payload.model_dump(exclude={"role", "doctype", "company_id"}).items():
        setattr(perm, field, value)
    perm.modified_by = user.id
    await db.commit()
    await db.refresh(perm)
    return perm


async def list_role_permissions(db: AsyncSession, role: str | None = None) -> list[RolePermission]:
    stmt = select(RolePermission).order_by(RolePermission.role, RolePermission.doctype)
    if role:
        stmt = stmt.where(RolePermission.role == role)
    return list((await db.execute(stmt)).scalars().all())


# --- Currencies ---------------------------------------------------------------------


async def list_currencies(db: AsyncSession, enabled_only: bool = False) -> list[Currency]:
    stmt = select(Currency).order_by(Currency.code)
    if enabled_only:
        stmt = stmt.where(Currency.enabled.is_(True))
    return list((await db.execute(stmt)).scalars().all())


async def create_currency_exchange(
    db: AsyncSession, payload: CurrencyExchangeCreate, user: CurrentUser
) -> CurrencyExchange:
    exchange = CurrencyExchange(**payload.model_dump(), owner=user.id)
    db.add(exchange)
    await db.commit()
    await db.refresh(exchange)
    return exchange


async def get_exchange_rate(
    db: AsyncSession, from_currency: str, to_currency: str, *, for_selling: bool = True
) -> float:
    """Latest stored rate; 1.0 for same-currency (mirrors erpnext get_exchange_rate
    minus the external rate-provider fallback)."""
    if from_currency == to_currency:
        return 1.0
    stmt = (
        select(CurrencyExchange.exchange_rate)
        .where(
            CurrencyExchange.from_currency == from_currency,
            CurrencyExchange.to_currency == to_currency,
        )
        .order_by(CurrencyExchange.date.desc())
        .limit(1)
    )
    if for_selling:
        stmt = stmt.where(CurrencyExchange.for_selling.is_(True))
    else:
        stmt = stmt.where(CurrencyExchange.for_buying.is_(True))
    rate = (await db.execute(stmt)).scalar_one_or_none()
    if rate is None:
        raise NotFoundError(f"No exchange rate found for {from_currency} -> {to_currency}")
    return float(rate)


# --- UOM -----------------------------------------------------------------------------


async def create_uom(db: AsyncSession, payload: UOMCreate, user: CurrentUser) -> UOM:
    if await db.scalar(select(UOM).where(UOM.uom_name == payload.uom_name)):
        raise DuplicateError("UOM already exists", field="uom_name")
    uom = UOM(**payload.model_dump(), owner=user.id)
    db.add(uom)
    await db.commit()
    await db.refresh(uom)
    return uom


async def list_uoms(db: AsyncSession) -> list[UOM]:
    return list((await db.execute(select(UOM).order_by(UOM.uom_name))).scalars().all())


async def create_uom_conversion(
    db: AsyncSession, payload: UOMConversionCreate, user: CurrentUser
) -> UOMConversion:
    conversion = UOMConversion(**payload.model_dump(), owner=user.id)
    db.add(conversion)
    await db.commit()
    await db.refresh(conversion)
    return conversion
