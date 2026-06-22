"""Company print/branding profile + company-owned addresses (Section 4.5).

The profile is stored under the ``print_settings`` key of ``SystemSetting`` via the
existing settings service — no new persistence. Company addresses are ``Address``
rows flagged ``is_company_address`` (no new table; the address RLS policy applies).
"""

import uuid

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateError, NotFoundError
from app.core.security import CurrentUser
from app.models.selling import Address
from app.schemas.core import SystemSettingUpsert
from app.schemas.printing import CompanyAddressIn, PrintProfile
from app.services import settings as settings_service

PRINT_SETTINGS_KEY = "print_settings"


async def get_print_profile(db: AsyncSession, company_id: uuid.UUID | None) -> PrintProfile:
    """Load the company profile, defaulting cleanly when unset or malformed."""
    try:
        setting = await settings_service.get_setting(db, PRINT_SETTINGS_KEY, company_id)
    except NotFoundError:
        return PrintProfile()
    if not isinstance(setting.value, dict):
        return PrintProfile()
    try:
        return PrintProfile.model_validate(setting.value)
    except ValidationError:
        return PrintProfile()


async def save_print_profile(
    db: AsyncSession, profile: PrintProfile, user: CurrentUser
) -> PrintProfile:
    payload = SystemSettingUpsert(
        key=PRINT_SETTINGS_KEY,
        value=profile.model_dump(mode="json"),
        company_id=user.company_id,
    )
    await settings_service.upsert_setting(db, payload, user)
    return profile


# --- Company addresses -------------------------------------------------------------


async def list_company_addresses(db: AsyncSession, company_id: uuid.UUID | None) -> list[Address]:
    rows = await db.execute(
        select(Address)
        .where(
            Address.company_id == company_id,
            Address.is_company_address.is_(True),
            Address.disabled.is_(False),
        )
        .order_by(Address.address_title)
    )
    return list(rows.scalars().all())


async def get_company_address(
    db: AsyncSession, address_id: uuid.UUID, company_id: uuid.UUID | None
) -> Address:
    address = await db.get(Address, address_id)
    if address is None or address.company_id != company_id or not address.is_company_address:
        raise NotFoundError("Company address not found")
    return address


async def create_company_address(
    db: AsyncSession, payload: CompanyAddressIn, user: CurrentUser
) -> Address:
    existing = await db.scalar(
        select(Address).where(
            Address.company_id == user.company_id,
            Address.address_title == payload.address_title,
        )
    )
    if existing is not None:
        raise DuplicateError("An address with this title already exists", field="address_title")
    address = Address(
        **payload.model_dump(),
        company_id=user.company_id,
        is_company_address=True,
        owner=user.id,
    )
    db.add(address)
    await db.commit()
    await db.refresh(address)
    return address


async def update_company_address(
    db: AsyncSession, address_id: uuid.UUID, payload: CompanyAddressIn, user: CurrentUser
) -> Address:
    address = await get_company_address(db, address_id, user.company_id)
    for field, value in payload.model_dump().items():
        setattr(address, field, value)
    address.modified_by = user.id
    await db.commit()
    await db.refresh(address)
    return address


async def delete_company_address(db: AsyncSession, address_id: uuid.UUID, user: CurrentUser) -> None:
    address = await get_company_address(db, address_id, user.company_id)
    await db.delete(address)
    await db.commit()


async def resolve_company_address(
    db: AsyncSession, profile: PrintProfile, doctype: str, company_id: uuid.UUID | None
) -> Address | None:
    """Which company address prints for a doctype: explicit mapping, else the first."""
    addresses = await list_company_addresses(db, company_id)
    if not addresses:
        return None
    chosen_id = profile.doctype_address.get(doctype)
    if chosen_id:
        for address in addresses:
            if str(address.id) == str(chosen_id):
                return address
    return addresses[0]
