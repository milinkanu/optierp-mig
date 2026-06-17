"""Metadata engine — descriptor types and the DocType registry.

A ``DocTypeDescriptor`` ("recipe card") declares everything the generic engine
needs to serve a master DocType: its bound SQLAlchemy model, fields, list
columns, naming, permissions and (optionally) tree / child / hook behaviour.
Registering one descriptor is all that is needed to add a simple master — the
generic router (``app.api.v1.registry``) and the generic Vue views then render
its list, form, permissions and naming with no per-doctype code.

Design note: descriptors are typed Python objects (version-controlled,
IDE-checked) rather than DB rows (cf. Frappe's ``tabDocType``/``tabDocField``).
See ``docs/metadata_engine_plan.md`` §3, Decision 1.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from app.core.exceptions import NotFoundError

# fieldtype -> FormBuilder control type (frontend FieldConfig.type union).
FIELDTYPE_TO_UI: dict[str, str] = {
    "Data": "text",
    "Text": "textarea",
    "Email": "email",
    "Int": "number",
    "Float": "number",
    "Currency": "number",
    "Check": "checkbox",
    "Date": "date",
    "Select": "select",
    "Link": "link",
}

# Layout-only fieldtypes hold no DB column (cf. Frappe Section/Column Break).
LAYOUT_FIELDTYPES: frozenset[str] = frozenset({"Section Break", "Column Break", "HTML"})


@dataclass(frozen=True)
class FieldSpec:
    """One field on a DocType — the OptiReach analogue of a Frappe DocField."""

    name: str
    label: str
    fieldtype: str
    options: str | None = None  # Link -> target slug; Select -> newline-separated choices
    required: bool = False
    in_list: bool = False
    span: int = 1
    depends_on: str | None = None
    unique: bool = False
    read_only: bool = False
    help: str | None = None

    @property
    def is_persisted(self) -> bool:
        """False for layout-only fields (no DB column / no payload value)."""
        return self.fieldtype not in LAYOUT_FIELDTYPES


@dataclass(frozen=True)
class ChildSpec:
    """A child grid (line items) owned by a parent DocType.

    The child has its own table/model but no standalone CRUD/permissions — it is
    created/edited with the parent. ``field`` is the attribute on the parent
    payload holding the row list; ``fk_column`` is the child FK to the parent id.
    """

    field: str
    label: str
    model: type
    fk_column: str
    fields: Sequence[FieldSpec]


@dataclass(frozen=True)
class LinkSpec:
    """A related DocType that points back to this one via a FK field.

    Unlike a ChildSpec (rows owned by, and saved with, the parent), a link target
    is a *standalone* DocType with its own CRUD/permissions — e.g. a Customer's
    Addresses and Contacts. The generic form renders each link as an inline
    managed list (add/edit/delete) filtered to the parent, mirroring ERPNext's
    Address & Contact section. ``link_field`` is the FK on the target pointing at
    this parent's id; the inline editor sets it automatically.
    """

    doctype: str  # slug of the (registered) linked DocType
    link_field: str  # FK field on the linked DocType -> this parent's id
    label: str


@dataclass(frozen=True)
class DocTypeDescriptor:
    """The recipe card for one DocType served by the generic engine."""

    name: str
    slug: str
    model: type
    title_field: str
    fields: Sequence[FieldSpec]
    list_fields: Sequence[str]
    permission_name: str
    naming: str = "field:name"  # "field:<fieldname>" | "series:<PATTERN>"
    scoped: bool = True  # company-scoped? False for global masters (UOM, Currency, ...)
    is_tree: bool = False
    parent_field: str | None = None
    children: Sequence[ChildSpec] = ()
    links: Sequence[LinkSpec] = ()  # related standalone DocTypes (Address, Contact, …)
    hooks: Mapping[str, Callable] = field(default_factory=dict)
    # role -> actions; seeded as RolePermission rows by scripts.seed
    permissions: Mapping[str, Sequence[str]] = field(default_factory=dict)
    group: str = "Setup"  # sidebar group label

    def field_map(self) -> dict[str, FieldSpec]:
        return {f.name: f for f in self.fields}


REGISTRY: dict[str, DocTypeDescriptor] = {}


def register(descriptor: DocTypeDescriptor) -> DocTypeDescriptor:
    """Add a descriptor to the registry (raises on duplicate slug)."""
    if descriptor.slug in REGISTRY:
        raise ValueError(f"Duplicate descriptor slug: {descriptor.slug}")
    REGISTRY[descriptor.slug] = descriptor
    return descriptor


def get_descriptor(slug: str) -> DocTypeDescriptor:
    """Resolve a descriptor by slug, or raise a 404."""
    try:
        return REGISTRY[slug]
    except KeyError as exc:
        raise NotFoundError(f"Unknown doctype: {slug}", code="ERR_UNKNOWN_DOCTYPE") from exc
