"""RBAC permission engine — mirrors ``frappe.has_permission()``.

Permissions are granted per (role, doctype) in the ``role_permission`` table
with boolean action flags (read/write/create/delete/submit/cancel/amend/
print/email/report) and an ``if_owner`` qualifier. A user holds roles via
``user_role`` (optionally scoped to a company). "System Manager" is a
superuser role, as in ERPNext.
"""

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PermissionDeniedError
from app.core.security import CurrentUser, get_current_user, get_tenant_db
from app.models.core import RolePermission, UserRole

SUPERUSER_ROLE = "System Manager"

ACTIONS = frozenset(
    {"read", "write", "create", "delete", "submit", "cancel", "amend", "print", "email", "report"}
)


async def get_user_roles(
    db: AsyncSession, user_id: uuid.UUID, company_id: uuid.UUID | None
) -> list[str]:
    """Roles assigned to the user globally or for the given company."""
    stmt = select(UserRole.role).where(UserRole.user_id == user_id)
    if company_id is not None:
        stmt = stmt.where((UserRole.company_id == company_id) | (UserRole.company_id.is_(None)))
    else:
        stmt = stmt.where(UserRole.company_id.is_(None))
    return list((await db.execute(stmt)).scalars().all())


async def has_permission(
    db: AsyncSession,
    user: CurrentUser,
    doctype: str,
    action: str,
    *,
    doc_owner: uuid.UUID | None = None,
) -> bool:
    """Check whether the user may perform ``action`` on ``doctype``.

    ``doc_owner`` enables the ``if_owner`` rule: a permission row flagged
    if_owner only matches when the user owns the specific document.
    """
    if action not in ACTIONS:
        raise ValueError(f"Unknown permission action: {action}")
    if SUPERUSER_ROLE in user.roles:
        return True

    flag = getattr(RolePermission, f"can_{action}")
    stmt = (
        select(RolePermission.if_owner)
        .where(
            RolePermission.role.in_(user.roles or [""]),
            RolePermission.doctype == doctype,
            flag.is_(True),
        )
        .where(
            (RolePermission.company_id.is_(None))
            | (RolePermission.company_id == user.company_id)
        )
    )
    rows = (await db.execute(stmt)).scalars().all()
    for if_owner in rows:
        if not if_owner:
            return True
        if doc_owner is not None and doc_owner == user.id:
            return True
    return False


def require_permission(doctype: str, action: str):
    """FastAPI dependency factory: 403 unless the user holds the permission."""

    async def _check(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_tenant_db)],
    ) -> CurrentUser:
        if not await has_permission(db, current_user, doctype, action):
            raise PermissionDeniedError(
                f"Insufficient permissions: requires '{action}' on {doctype}"
            )
        return current_user

    return _check
