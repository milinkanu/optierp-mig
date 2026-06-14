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
from app.registry import descriptors as descriptors  # noqa: F401 — populate REGISTRY on import

__all__ = [
    "FIELDTYPE_TO_UI",
    "LAYOUT_FIELDTYPES",
    "REGISTRY",
    "ChildSpec",
    "DocTypeDescriptor",
    "FieldSpec",
    "get_descriptor",
    "register",
]
