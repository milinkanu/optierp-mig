"""Company print/branding settings endpoints (Section 4.5)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.printing import CompanyAddressIn, CompanyAddressResponse, PrintProfile
from app.services import print_branding

router = APIRouter(prefix="/print-settings", tags=["core: print settings"])


@router.get("", response_model=PrintProfile, summary="Get the company print/branding profile")
async def get_profile(
    current_user: Annotated[CurrentUser, Depends(require_permission("System Settings", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PrintProfile:
    return await print_branding.get_print_profile(db, current_user.company_id)


@router.put("", response_model=PrintProfile, summary="Save the company print/branding profile")
async def put_profile(
    payload: PrintProfile,
    current_user: Annotated[CurrentUser, Depends(require_permission("System Settings", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PrintProfile:
    return await print_branding.save_print_profile(db, payload, current_user)


@router.get(
    "/addresses",
    response_model=list[CompanyAddressResponse],
    summary="List the company's own addresses",
)
async def list_addresses(
    current_user: Annotated[CurrentUser, Depends(require_permission("System Settings", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[CompanyAddressResponse]:
    rows = await print_branding.list_company_addresses(db, current_user.company_id)
    return [CompanyAddressResponse.model_validate(row) for row in rows]


@router.post(
    "/addresses",
    response_model=CompanyAddressResponse,
    status_code=201,
    summary="Add a company address",
)
async def create_address(
    payload: CompanyAddressIn,
    current_user: Annotated[CurrentUser, Depends(require_permission("System Settings", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> CompanyAddressResponse:
    return CompanyAddressResponse.model_validate(
        await print_branding.create_company_address(db, payload, current_user)
    )


@router.put(
    "/addresses/{address_id}",
    response_model=CompanyAddressResponse,
    summary="Update a company address",
)
async def update_address(
    address_id: uuid.UUID,
    payload: CompanyAddressIn,
    current_user: Annotated[CurrentUser, Depends(require_permission("System Settings", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> CompanyAddressResponse:
    return CompanyAddressResponse.model_validate(
        await print_branding.update_company_address(db, address_id, payload, current_user)
    )


@router.delete("/addresses/{address_id}", status_code=204, summary="Delete a company address")
async def delete_address(
    address_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("System Settings", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> Response:
    await print_branding.delete_company_address(db, address_id, current_user)
    return Response(status_code=204)
