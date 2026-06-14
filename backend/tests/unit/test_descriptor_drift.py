"""Descriptor-drift guard — the single most important safeguard for the engine.

Every registered descriptor must agree with its bound SQLAlchemy model:
its title field, every persisted FieldSpec, every list column and (when
declared) the company_id / name / parent columns must be real columns. If this
fails, the recipe card and the table have drifted apart — fix one of them.

Runs without a database (introspection only).
"""

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import configure_mappers

from app.registry import REGISTRY
from app.registry.base import LAYOUT_FIELDTYPES


def test_registry_is_populated():
    assert REGISTRY, "No descriptors registered — app.registry.descriptors did not load."


def test_descriptors_match_their_models():
    configure_mappers()
    for slug, d in REGISTRY.items():
        columns = {c.key for c in sa_inspect(d.model).columns}

        assert d.title_field in columns, f"{slug}: title_field '{d.title_field}' is not a column"

        for spec in d.fields:
            if spec.fieldtype in LAYOUT_FIELDTYPES:
                continue
            assert spec.name in columns, (
                f"{slug}: field '{spec.name}' has no column on {d.model.__name__}"
            )

        for name in d.list_fields:
            assert name in columns, f"{slug}: list_field '{name}' is not a column"

        if d.scoped:
            assert "company_id" in columns, f"{slug}: scoped=True but model has no company_id"

        if d.naming.startswith("series:"):
            assert "name" in columns, f"{slug}: series naming but model has no 'name' column"

        if d.is_tree:
            assert d.parent_field, f"{slug}: is_tree=True but no parent_field declared"
            assert d.parent_field in columns, f"{slug}: parent_field '{d.parent_field}' is not a column"
