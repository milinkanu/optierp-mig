"""Role & permission endpoints — Module 01."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.core import (
    RoleCreate,
    RolePermissionResponse,
    RolePermissionUpsert,
    RoleResponse,
)
from app.services import settings as settings_service

router = APIRouter(prefix="/roles", tags=["core: roles"])


@router.post(
    "",
    response_model=RoleResponse,
    status_code=201,
    summary="Create a role",
    description="Creates a custom role. Example: `{'name': 'Warehouse Supervisor'}`",
)
async def create_role(
    payload: RoleCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Role", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> RoleResponse:
    return RoleResponse.model_validate(await settings_service.create_role(db, payload, current_user))


@router.get(
    "",
    response_model=list[RoleResponse],
    summary="List roles",
    description="All roles defined in the system, including seeded system roles.",
)
async def list_roles(
    current_user: Annotated[CurrentUser, Depends(require_permission("Role", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[RoleResponse]:
    return [RoleResponse.model_validate(r) for r in await settings_service.list_roles(db)]


@router.put(
    "/permissions",
    response_model=RolePermissionResponse,
    summary="Upsert a role permission",
    description="Sets the action flags for a (role, doctype) pair, mirroring ERPNext "
    "DocType permissions. Example: `{'role': 'Accounts User', 'doctype': 'Sales Invoice', "
    "'can_read': true, 'can_create': true}`",
)
async def upsert_role_permission(
    payload: RolePermissionUpsert,
    current_user: Annotated[CurrentUser, Depends(require_permission("Role", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> RolePermissionResponse:
    perm = await settings_service.upsert_role_permission(db, payload, current_user)
    return RolePermissionResponse.model_validate(perm)


@router.get(
    "/permissions",
    response_model=list[RolePermissionResponse],
    summary="List role permissions",
    description="Permission matrix rows, optionally filtered by role.",
)
async def list_role_permissions(
    current_user: Annotated[CurrentUser, Depends(require_permission("Role", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    role: Annotated[str | None, Query()] = None,
) -> list[RolePermissionResponse]:
    perms = await settings_service.list_role_permissions(db, role)
    return [RolePermissionResponse.model_validate(p) for p in perms]
