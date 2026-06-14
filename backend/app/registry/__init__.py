"""Metadata engine package.

Importing this package registers every descriptor (see ``.descriptors``) so the
``REGISTRY`` is populated wherever the engine is used (router, services, seed,
tests).
"""

from app.registry.base import (
    FIELDTYPE_TO_UI,
    LAYOUT_FIELDTYPES,
    REGISTRY,
    ChildSpec,
    DocTypeDescriptor,
    FieldSpec,
    get_descriptor,
    register,
)
# Importing names from descriptors also populates REGISTRY on first import.
from app.registry.descriptors import LINK_SOURCES, resolve_link_source  # noqa: F401

__all__ = [
    "FIELDTYPE_TO_UI",
    "LAYOUT_FIELDTYPES",
    "LINK_SOURCES",
    "REGISTRY",
    "ChildSpec",
    "DocTypeDescriptor",
    "FieldSpec",
    "get_descriptor",
    "register",
    "resolve_link_source",
]
