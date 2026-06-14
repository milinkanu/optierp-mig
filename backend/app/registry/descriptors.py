"""Descriptor definitions — the one place a simple master is declared.

Each ``register(...)`` call adds a DocType to the generic engine. Phase 0 ships
Campaign (the engine smoke-test pilot); Phases 1–2 add the tree masters and the
rest of the simple-master long tail here.
"""

from __future__ import annotations

from app.models.selling import Campaign
from app.registry.base import DocTypeDescriptor, FieldSpec, register

# Common permission bundles for selling masters.
_SALES_MANAGER = ("read", "write", "create", "delete", "report")
_SALES_USER = ("read", "report")


# --- Selling: Campaign (Phase 0 pilot) ---------------------------------------
register(
    DocTypeDescriptor(
        name="Campaign",
        slug="campaign",
        model=Campaign,
        title_field="campaign_name",
        naming="field:campaign_name",
        group="Selling",
        permission_name="Campaign",
        permissions={"Sales Manager": _SALES_MANAGER, "Sales User": _SALES_USER},
        fields=(
            FieldSpec(
                "campaign_name", "Campaign Name", "Data",
                required=True, in_list=True, span=2, unique=True,
            ),
            FieldSpec("status", "Status", "Select", options="Active\nInactive", in_list=True),
            FieldSpec("campaign_desc", "Description", "Text", span=2),
            FieldSpec("disabled", "Disabled", "Check", in_list=True),
        ),
        list_fields=("campaign_name", "status", "disabled"),
    )
)
