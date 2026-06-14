"""Generic nested-master tree service (ltree materialised path).

Maintains ``TreeMixin.path`` for any ``is_tree`` descriptor on create and on
move (reparent / rename), blocks deleting a non-leaf, and builds the nested
structure for the tree view. Mirrors the Chart of Accounts path convention
(``parent.path`` + "." + slugified title). Reparent/rename go through these
functions (called from the generic registry service), never a raw column write.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.registry import DocTypeDescriptor
from app.services.audit import serialize_document


def slugify(label: str) -> str:
    """ltree-safe label (matches app.services.accounts_masters._slugify)."""
    slug = re.sub(r"[^a-z0-9_]+", "_", (label or "").lower()).strip("_")
    return slug or "node"


async def _get_parent(
    db: AsyncSession, descriptor: DocTypeDescriptor, parent_id: uuid.UUID, company_id: uuid.UUID | None
) -> Any:
    model = descriptor.model
    stmt = select(model).where(model.id == parent_id)
    if descriptor.scoped and company_id is not None:
        stmt = stmt.where(model.company_id == company_id)
    parent = (await db.execute(stmt)).scalar_one_or_none()
    if parent is None:
        raise ValidationError("Parent not found", field=descriptor.parent_field)
    if not parent.is_group:
        raise ValidationError("Parent must be a group node", field=descriptor.parent_field)
    return parent


async def on_create(db: AsyncSession, descriptor: DocTypeDescriptor, obj: Any) -> None:
    """Set ``path`` for a new node from its parent and title."""
    title = getattr(obj, descriptor.title_field)
    parent_id = getattr(obj, descriptor.parent_field)
    if parent_id is None:
        obj.path = slugify(title)
    else:
        parent = await _get_parent(db, descriptor, parent_id, getattr(obj, "company_id", None))
        obj.path = f"{parent.path}.{slugify(title)}"


async def on_update(db: AsyncSession, descriptor: DocTypeDescriptor, obj: Any, old_path: str) -> None:
    """Recompute ``path`` after a rename/reparent and cascade to descendants."""
    title = getattr(obj, descriptor.title_field)
    parent_id = getattr(obj, descriptor.parent_field)
    if parent_id is None:
        new_path = slugify(title)
    else:
        if parent_id == obj.id:
            raise ValidationError("A node cannot be its own parent", field=descriptor.parent_field)
        parent = await _get_parent(db, descriptor, parent_id, getattr(obj, "company_id", None))
        if parent.path == old_path or parent.path.startswith(old_path + "."):
            raise ValidationError(
                "Cannot move a node under its own descendant", field=descriptor.parent_field
            )
        new_path = f"{parent.path}.{slugify(title)}"

    if new_path == old_path:
        return

    # Cascade the prefix change to every descendant (small master trees — fetch
    # the company's nodes and rewrite in Python rather than relying on ltree ops).
    model = descriptor.model
    stmt = select(model)
    if descriptor.scoped:
        stmt = stmt.where(model.company_id == getattr(obj, "company_id", None))
    rows = (await db.execute(stmt.with_for_update())).scalars().all()
    obj.path = new_path
    prefix = old_path + "."
    for row in rows:
        if row.id != obj.id and row.path.startswith(prefix):
            row.path = new_path + row.path[len(old_path):]


async def block_if_has_children(
    db: AsyncSession, descriptor: DocTypeDescriptor, obj: Any
) -> None:
    """Reject deleting a node that still has children."""
    model = descriptor.model
    count = (
        await db.execute(
            select(func.count())
            .select_from(model)
            .where(getattr(model, descriptor.parent_field) == obj.id)
        )
    ).scalar_one()
    if count:
        raise ValidationError(
            "Cannot delete: this node has child records.", code="ERR_HAS_CHILDREN"
        )


async def get_tree(
    db: AsyncSession, descriptor: DocTypeDescriptor, company_id: uuid.UUID | None
) -> list[dict[str, Any]]:
    """Return the nested tree (root nodes each with a ``children`` list)."""
    model = descriptor.model
    stmt = select(model)
    if descriptor.scoped and company_id is not None:
        stmt = stmt.where(model.company_id == company_id)
    rows = (await db.execute(stmt.order_by(model.path))).scalars().all()

    nodes: dict[uuid.UUID, dict[str, Any]] = {
        row.id: {**serialize_document(row), "children": []} for row in rows
    }
    roots: list[dict[str, Any]] = []
    for row in rows:
        parent_id = getattr(row, descriptor.parent_field)
        if parent_id is not None and parent_id in nodes:
            nodes[parent_id]["children"].append(nodes[row.id])
        else:
            roots.append(nodes[row.id])
    return roots
