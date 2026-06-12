"""User endpoints — Module 01."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.common import ListResponse
from app.schemas.core import UserCreate, UserListItem, UserResponse, UserUpdate
from app.services import user as user_service

router = APIRouter(prefix="/users", tags=["core: users"])


def _to_response(user) -> UserResponse:
    resp = UserResponse.model_validate(user)
    resp.role_names = sorted({r.role for r in user.roles})
    return resp


@router.post(
    "",
    response_model=UserResponse,
    status_code=201,
    summary="Create a user",
    description="Creates a user with hashed password and optional role assignments. "
    "Example: `{'email': 'jane@acme.com', 'first_name': 'Jane', 'password': 'S3cret!pass', "
    "'roles': ['Accounts User']}`",
)
async def create_user(
    payload: UserCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("User", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> UserResponse:
    user = await user_service.create_user(db, payload, current_user)
    return _to_response(await user_service.get_user(db, user.id))


@router.get(
    "",
    response_model=ListResponse[UserListItem],
    summary="List users",
    description="Paginated user list with optional name/email search.",
)
async def list_users(
    current_user: Annotated[CurrentUser, Depends(require_permission("User", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    search: str | None = None,
) -> ListResponse[UserListItem]:
    users, total = await user_service.list_users(db, page, page_size, search)
    return ListResponse(
        items=[UserListItem.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get a user",
    description="Full user profile including role assignments.",
)
async def get_user(
    user_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("User", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> UserResponse:
    return _to_response(await user_service.get_user(db, user_id))


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update a user",
    description="Partial update; pass `roles` to replace role assignments for the user's "
    "default company.",
)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    current_user: Annotated[CurrentUser, Depends(require_permission("User", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> UserResponse:
    return _to_response(await user_service.update_user(db, user_id, payload, current_user))
