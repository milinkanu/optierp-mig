"""Descriptor definitions — the one place a simple master is declared.

Each ``register(...)`` call adds a DocType to the generic engine. Phase 0 ships
Campaign (the engine smoke-test pilot); Phases 1–2 add the tree masters and the
rest of the simple-master long tail here.
"""

from __future__ import annotations

from app.models.selling import Campaign, CustomerGroup, SalesPerson, Territory
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


# --- Selling: tree masters (Phase 1) -----------------------------------------
register(
    DocTypeDescriptor(
        name="Territory",
        slug="territory",
        model=Territory,
        title_field="territory_name",
        naming="field:territory_name",
        group="Selling",
        permission_name="Territory",
        permissions={"Sales Manager": _SALES_MANAGER, "Sales User": _SALES_USER},
        is_tree=True,
        parent_field="parent_territory_id",
        fields=(
            FieldSpec("territory_name", "Territory Name", "Data", required=True, in_list=True, span=2),
            FieldSpec("parent_territory_id", "Parent Territory", "Link", options="territory"),
            FieldSpec("is_group", "Is Group", "Check", in_list=True),
            FieldSpec("disabled", "Disabled", "Check", in_list=True),
        ),
        list_fields=("territory_name", "is_group", "disabled"),
    )
)

register(
    DocTypeDescriptor(
        name="Customer Group",
        slug="customer-group",
        model=CustomerGroup,
        title_field="customer_group_name",
        naming="field:customer_group_name",
        group="Selling",
        permission_name="Customer Group",
        permissions={"Sales Manager": _SALES_MANAGER, "Sales User": _SALES_USER},
        is_tree=True,
        parent_field="parent_customer_group_id",
        fields=(
            FieldSpec(
                "customer_group_name", "Customer Group Name", "Data",
                required=True, in_list=True, span=2,
            ),
            FieldSpec("parent_customer_group_id", "Parent Customer Group", "Link", options="customer-group"),
            FieldSpec("is_group", "Is Group", "Check", in_list=True),
            FieldSpec("disabled", "Disabled", "Check", in_list=True),
        ),
        list_fields=("customer_group_name", "is_group", "disabled"),
    )
)

register(
    DocTypeDescriptor(
        name="Sales Person",
        slug="sales-person",
        model=SalesPerson,
        title_field="sales_person_name",
        naming="field:sales_person_name",
        group="Selling",
        permission_name="Sales Person",
        permissions={"Sales Manager": _SALES_MANAGER, "Sales User": _SALES_USER},
        is_tree=True,
        parent_field="parent_sales_person_id",
        fields=(
            FieldSpec(
                "sales_person_name", "Sales Person Name", "Data",
                required=True, in_list=True, span=2,
            ),
            FieldSpec("parent_sales_person_id", "Parent Sales Person", "Link", options="sales-person"),
            FieldSpec("commission_rate", "Commission Rate (%)", "Float"),
            FieldSpec("is_group", "Is Group", "Check", in_list=True),
            FieldSpec("disabled", "Disabled", "Check", in_list=True),
        ),
        list_fields=("sales_person_name", "is_group", "disabled"),
    )
)
