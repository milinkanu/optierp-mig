"""Generic metadata-engine router — one set of endpoints for every registered
DocType (``app.registry``). Adding a master needs no new router code.

Endpoints:
  GET    /meta/{doctype}              form/list metadata (the recipe card as JSON)
  GET    /registry/{doctype}          list (page, page_size, search, field filters)
  GET    /registry/{doctype}/{id}     fetch one
  POST   /registry/{doctype}          create
  PATCH  /registry/{doctype}/{id}     update
  DELETE /registry/{doctype}/{id}     delete
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PermissionDeniedError
from app.core.permissions import has_permission
from app.core.security import CurrentUser, get_current_user, get_tenant_db
from app.registry import DocTypeDescriptor, get_descriptor
from app.schemas.common import ListResponse, MessageResponse
from app.services import registry as svc

router = APIRouter(tags=["metadata engine"])


async def _require(
    db: AsyncSession, user: CurrentUser, descriptor: DocTypeDescriptor, action: str
) -> None:
    if not await has_permission(db, user, descriptor.permission_name, action):
        raise PermissionDeniedError(
            f"Insufficient permissions: requires '{action}' on {descriptor.name}"
        )


@router.get(
    "/meta/{doctype}",
    summary="Get a DocType's form/list metadata",
    description="Returns the recipe card as JSON: field configs for the form, columns for "
    "the list, and naming/tree flags. Example: GET /meta/campaign.",
)
async def get_meta(
    doctype: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> dict[str, Any]:
    descriptor = get_descriptor(doctype)
    await _require(db, current_user, descriptor, "read")
    return svc.build_meta(descriptor)


@router.get(
    "/registry/{doctype}",
    summary="List records of a DocType",
    description="Paginated list. Any query param matching a field name filters by exact "
    "value; `search` matches the title field (ILIKE).",
)
async def list_documents(
    doctype: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    search: Annotated[str | None, Query()] = None,
) -> ListResponse[dict[str, Any]]:
    descriptor = get_descriptor(doctype)
    await _require(db, current_user, descriptor, "read")
    reserved = {"page", "page_size", "search"}
    filters = {k: v for k, v in request.query_params.items() if k not in reserved}
    items, total = await svc.list_documents(
        db,
        descriptor,
        company_id=current_user.company_id,
        page=page,
        page_size=page_size,
        search=search,
        filters=filters,
    )
    return ListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/registry/{doctype}/{doc_id}",
    summary="Get one record",
    description="Full record by id (404 if not found or outside the tenant).",
)
async def get_document(
    doctype: str,
    doc_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> dict[str, Any]:
    descriptor = get_descriptor(doctype)
    await _require(db, current_user, descriptor, "read")
    return await svc.get_document(db, descriptor, doc_id, current_user.company_id)


@router.post(
    "/registry/{doctype}",
    status_code=201,
    summary="Create a record",
    description="Validates the body against the DocType's generated schema, applies naming "
    "and company scoping, runs before_insert/validate hooks, and writes an audit row.",
)
async def create_document(
    doctype: str,
    payload: Annotated[dict[str, Any], Body(...)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> dict[str, Any]:
    descriptor = get_descriptor(doctype)
    await _require(db, current_user, descriptor, "create")
    return await svc.create_document(db, descriptor, payload, current_user)


@router.patch(
    "/registry/{doctype}/{doc_id}",
    summary="Update a record",
    description="Partial update; only provided fields change. Runs before_update/validate hooks.",
)
async def update_document(
    doctype: str,
    doc_id: uuid.UUID,
    payload: Annotated[dict[str, Any], Body(...)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> dict[str, Any]:
    descriptor = get_descriptor(doctype)
    await _require(db, current_user, descriptor, "write")
    return await svc.update_document(db, descriptor, doc_id, payload, current_user)


@router.delete(
    "/registry/{doctype}/{doc_id}",
    response_model=MessageResponse,
    summary="Delete a record",
    description="Deletes the record. Returns a friendly error if it is referenced elsewhere.",
)
async def delete_document(
    doctype: str,
    doc_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> MessageResponse:
    descriptor = get_descriptor(doctype)
    await _require(db, current_user, descriptor, "delete")
    await svc.delete_document(db, descriptor, doc_id, current_user)
    return MessageResponse(message=f"{descriptor.name} deleted")
