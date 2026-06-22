"""Generic document print/preview endpoint (Section 4.5).

One route renders any registered doctype. ``?format=html`` returns themed HTML for
the in-app preview iframe; ``?format=pdf`` returns the PDF. Permission is checked
dynamically as ``print`` on the doctype, so adding a doctype needs no endpoint code.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.permissions import has_permission
from app.core.security import CurrentUser, get_current_user, get_tenant_db
from app.schemas.printing import EmailDocumentRequest, EmailSendResult
from app.services import print_service

router = APIRouter(prefix="/print", tags=["core: print"])


@router.get(
    "/{doctype}/{doc_id}",
    summary="Render a document as PDF or HTML preview",
    description="`doctype` must be registered (e.g. `Sales Invoice`). `?format=html` "
    "returns the themed HTML preview; `?format=pdf` (default) returns the PDF. "
    "Returns 501 if the PDF engine is not installed.",
)
async def print_document(
    doctype: str,
    doc_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    format: Annotated[Literal["pdf", "html"], Query()] = "pdf",
) -> Response:
    if doctype not in print_service.PRINT_REGISTRY:
        raise NotFoundError(f"No print format registered for '{doctype}'")
    if not await has_permission(db, current_user, doctype, "print"):
        raise PermissionDeniedError(f"Insufficient permissions: requires 'print' on {doctype}")
    content, filename, media_type = await print_service.render_document(
        db, doctype, doc_id, current_user.company_id, format
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post(
    "/{doctype}/{doc_id}/email",
    summary="Email a document to the party as a PDF attachment",
    description="Renders `doctype`/`doc_id` to PDF and emails it. Recipient defaults to "
    "the party's email; `to`/`subject`/`body` may override. Requires `email` permission. "
    "Never raises on a delivery failure — returns status `Failed` with the error.",
)
async def email_document(
    doctype: str,
    doc_id: uuid.UUID,
    payload: EmailDocumentRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> EmailSendResult:
    if doctype not in print_service.PRINT_REGISTRY:
        raise NotFoundError(f"No print format registered for '{doctype}'")
    if not await has_permission(db, current_user, doctype, "email"):
        raise PermissionDeniedError(f"Insufficient permissions: requires 'email' on {doctype}")
    log = await print_service.email_document(
        db,
        doctype,
        doc_id,
        current_user.company_id,
        current_user.id,
        to=[str(x) for x in payload.to] if payload.to else None,
        subject=payload.subject,
        body=payload.body,
    )
    return EmailSendResult(
        status=log.status,
        to=log.to_addresses,
        email_log_id=log.id,
        error=log.error_message,
    )
