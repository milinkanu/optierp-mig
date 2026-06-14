"""Generic metadata-engine CRUD service.

Drives create / read / update / delete / list for any ``DocTypeDescriptor``:
request-validation models are generated from the descriptor, and the existing
naming, pagination and audit engines are reused. Per-doctype rules attach via
descriptor hooks; transactional documents keep their own bespoke services.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, create_model
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.core.naming import get_next_name
from app.core.security import CurrentUser
from app.registry import FIELDTYPE_TO_UI, DocTypeDescriptor, FieldSpec
from app.services import tree as tree_service
from app.services.audit import log_audit, serialize_document
from app.services.pagination import paginate

# fieldtype -> Python type for the generated Pydantic request models.
_PY_TYPES: dict[str, type] = {
    "Data": str,
    "Text": str,
    "Select": str,
    "Email": str,
    "Int": int,
    "Float": Decimal,
    "Currency": Decimal,
    "Check": bool,
    "Date": date,
    "Link": uuid.UUID,
}

_create_models: dict[str, type[BaseModel]] = {}
_update_models: dict[str, type[BaseModel]] = {}


# --- generated request models ------------------------------------------------


def _build_model(descriptor: DocTypeDescriptor, *, all_optional: bool) -> type[BaseModel]:
    fields_def: dict[str, Any] = {}
    for spec in descriptor.fields:
        if not spec.is_persisted:
            continue
        py = _PY_TYPES.get(spec.fieldtype, str)
        if spec.required and not all_optional:
            fields_def[spec.name] = (py, ...)
        else:
            fields_def[spec.name] = (py | None, None)
    suffix = "Update" if all_optional else "Create"
    return create_model(
        f"{descriptor.name.replace(' ', '')}{suffix}",
        __config__=ConfigDict(extra="ignore"),
        **fields_def,
    )


def get_create_model(descriptor: DocTypeDescriptor) -> type[BaseModel]:
    if descriptor.slug not in _create_models:
        _create_models[descriptor.slug] = _build_model(descriptor, all_optional=False)
    return _create_models[descriptor.slug]


def get_update_model(descriptor: DocTypeDescriptor) -> type[BaseModel]:
    if descriptor.slug not in _update_models:
        _update_models[descriptor.slug] = _build_model(descriptor, all_optional=True)
    return _update_models[descriptor.slug]


def _validate(model: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
    try:
        return model(**payload)
    except PydanticValidationError as exc:
        err = exc.errors()[0] if exc.errors() else {}
        loc = [str(x) for x in err.get("loc", ())]
        raise ValidationError(
            err.get("msg", "Validation error"), field=".".join(loc) or None
        ) from exc


# --- meta (consumed by the frontend FormBuilder / DataTable) -----------------


def _field_config(spec: FieldSpec) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "name": spec.name,
        "label": spec.label,
        "type": FIELDTYPE_TO_UI.get(spec.fieldtype, "text"),
        "required": spec.required,
        "span": spec.span,
    }
    if spec.help:
        cfg["help"] = spec.help
    if spec.read_only:
        cfg["readOnly"] = True
    if spec.depends_on:
        cfg["dependsOn"] = spec.depends_on
    if spec.fieldtype == "Select" and spec.options:
        cfg["options"] = [{"value": o, "label": o} for o in spec.options.split("\n") if o]
    if spec.fieldtype == "Link" and spec.options:
        cfg["link"] = spec.options  # target slug; the form fetches its options
    return cfg


def build_meta(descriptor: DocTypeDescriptor) -> dict[str, Any]:
    fmap = descriptor.field_map()
    return {
        "name": descriptor.name,
        "slug": descriptor.slug,
        "title_field": descriptor.title_field,
        "naming": descriptor.naming,
        "scoped": descriptor.scoped,
        "is_tree": descriptor.is_tree,
        "parent_field": descriptor.parent_field,
        "group": descriptor.group,
        "fields": [_field_config(f) for f in descriptor.fields],
        "list_fields": [
            {"key": n, "label": fmap[n].label if n in fmap else n} for n in descriptor.list_fields
        ],
    }


# --- helpers -----------------------------------------------------------------


async def _get_obj(
    db: AsyncSession, descriptor: DocTypeDescriptor, doc_id: uuid.UUID, company_id: uuid.UUID | None
) -> Any:
    stmt = select(descriptor.model).where(descriptor.model.id == doc_id)
    if descriptor.scoped and company_id is not None:
        stmt = stmt.where(descriptor.model.company_id == company_id)
    obj = (await db.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise NotFoundError(f"{descriptor.name} not found")
    return obj


async def _run_hook(
    descriptor: DocTypeDescriptor, event: str, db: AsyncSession, obj: Any, user: CurrentUser
) -> None:
    hook = descriptor.hooks.get(event)
    if hook is None:
        return
    result = hook(db, descriptor, obj, user)
    if inspect.isawaitable(result):
        await result


async def _flush_unique(db: AsyncSession) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateError("A record with these values already exists.") from exc


# --- CRUD --------------------------------------------------------------------


async def list_documents(
    db: AsyncSession,
    descriptor: DocTypeDescriptor,
    *,
    company_id: uuid.UUID | None,
    page: int,
    page_size: int,
    search: str | None,
    filters: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(descriptor.model)
    if descriptor.scoped and company_id is not None:
        stmt = stmt.where(descriptor.model.company_id == company_id)
    if search and hasattr(descriptor.model, descriptor.title_field):
        stmt = stmt.where(getattr(descriptor.model, descriptor.title_field).ilike(f"%{search}%"))
    fmap = descriptor.field_map()
    for key, value in filters.items():
        if key in fmap and value not in (None, ""):
            stmt = stmt.where(getattr(descriptor.model, key) == value)
    stmt = stmt.order_by(descriptor.model.modified.desc())
    rows, total = await paginate(db, stmt, page, page_size)
    return [serialize_document(r) for r in rows], total


async def get_document(
    db: AsyncSession, descriptor: DocTypeDescriptor, doc_id: uuid.UUID, company_id: uuid.UUID | None
) -> dict[str, Any]:
    return serialize_document(await _get_obj(db, descriptor, doc_id, company_id))


async def create_document(
    db: AsyncSession, descriptor: DocTypeDescriptor, payload: dict[str, Any], user: CurrentUser
) -> dict[str, Any]:
    data = _validate(get_create_model(descriptor), payload).model_dump(exclude_unset=True)
    obj = descriptor.model()
    for key, value in data.items():
        setattr(obj, key, value)
    if descriptor.scoped:
        obj.company_id = user.company_id
    obj.owner = user.id
    obj.modified_by = user.id
    if descriptor.naming.startswith("series:"):
        obj.name = await get_next_name(db, descriptor.naming.split(":", 1)[1], user.company_id)
    if descriptor.is_tree:
        await tree_service.on_create(db, descriptor, obj)
    await _run_hook(descriptor, "before_insert", db, obj, user)
    await _run_hook(descriptor, "validate", db, obj, user)
    db.add(obj)
    await _flush_unique(db)
    await log_audit(
        db,
        doctype=descriptor.name,
        document_id=obj.id,
        action="INSERT",
        user_id=user.id,
        company_id=getattr(obj, "company_id", None),
        data_after=serialize_document(obj),
    )
    await db.commit()
    await db.refresh(obj)
    return serialize_document(obj)


async def update_document(
    db: AsyncSession,
    descriptor: DocTypeDescriptor,
    doc_id: uuid.UUID,
    payload: dict[str, Any],
    user: CurrentUser,
) -> dict[str, Any]:
    obj = await _get_obj(db, descriptor, doc_id, user.company_id)
    before = serialize_document(obj)
    old_path = getattr(obj, "path", None) if descriptor.is_tree else None
    data = _validate(get_update_model(descriptor), payload).model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(obj, key, value)
    obj.modified_by = user.id
    if descriptor.is_tree and old_path is not None:
        await tree_service.on_update(db, descriptor, obj, old_path)
    await _run_hook(descriptor, "before_update", db, obj, user)
    await _run_hook(descriptor, "validate", db, obj, user)
    await _flush_unique(db)
    await log_audit(
        db,
        doctype=descriptor.name,
        document_id=obj.id,
        action="UPDATE",
        user_id=user.id,
        company_id=getattr(obj, "company_id", None),
        data_before=before,
        data_after=serialize_document(obj),
    )
    await db.commit()
    await db.refresh(obj)
    return serialize_document(obj)


async def delete_document(
    db: AsyncSession, descriptor: DocTypeDescriptor, doc_id: uuid.UUID, user: CurrentUser
) -> None:
    obj = await _get_obj(db, descriptor, doc_id, user.company_id)
    before = serialize_document(obj)
    company_id = getattr(obj, "company_id", None)
    if descriptor.is_tree:
        await tree_service.block_if_has_children(db, descriptor, obj)
    await _run_hook(descriptor, "before_delete", db, obj, user)
    await db.delete(obj)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ValidationError(
            "Cannot delete: this record is referenced by other documents.", code="ERR_LINKED"
        ) from exc
    await log_audit(
        db,
        doctype=descriptor.name,
        document_id=doc_id,
        action="DELETE",
        user_id=user.id,
        company_id=company_id,
        data_before=before,
    )
    await db.commit()


# --- Link options & tree -----------------------------------------------------


async def list_link_options(
    db: AsyncSession,
    *,
    model: type,
    title_field: str,
    scoped: bool,
    company_id: uuid.UUID | None,
    q: str | None,
    limit: int = 20,
) -> list[dict[str, str]]:
    """Typeahead options for a Link field: [{value: id, label: title_field}].

    Works for any model (engine descriptor or core doctype) resolved via the
    link-source registry.
    """
    stmt = select(model)
    if scoped and company_id is not None:
        stmt = stmt.where(model.company_id == company_id)
    if q:
        stmt = stmt.where(getattr(model, title_field).ilike(f"%{q}%"))
    stmt = stmt.order_by(getattr(model, title_field)).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [{"value": str(r.id), "label": getattr(r, title_field)} for r in rows]


async def get_tree(
    db: AsyncSession, descriptor: DocTypeDescriptor, company_id: uuid.UUID | None
) -> list[dict[str, Any]]:
    """Nested tree for an is_tree descriptor (delegates to the tree service)."""
    return await tree_service.get_tree(db, descriptor, company_id)
