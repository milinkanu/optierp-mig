"""Descriptor definitions — the one place a simple master is declared.

Each ``register(...)`` call adds a DocType to the generic engine. Phase 0 ships
Campaign (the engine smoke-test pilot); Phases 1–2 add the tree masters and the
rest of the simple-master long tail here.
"""

from __future__ import annotations

from app.models.selling import (
    Campaign,
    CustomerGroup,
    MonthlyDistribution,
    SalesPartner,
    SalesPerson,
    TermsTemplate,
    Territory,
    UTMSource,
)
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


# --- Flat simple masters (Phase 2) -------------------------------------------
register(
    DocTypeDescriptor(
        name="Sales Partner",
        slug="sales-partner",
        model=SalesPartner,
        title_field="partner_name",
        naming="field:partner_name",
        group="Selling",
        permission_name="Sales Partner",
        permissions={"Sales Manager": _SALES_MANAGER, "Sales User": _SALES_USER},
        fields=(
            FieldSpec("partner_name", "Partner Name", "Data", required=True, in_list=True, span=2),
            FieldSpec("partner_type", "Partner Type", "Data"),
            FieldSpec("commission_rate", "Commission Rate (%)", "Float"),
            FieldSpec("disabled", "Disabled", "Check", in_list=True),
        ),
        list_fields=("partner_name", "partner_type", "disabled"),
    )
)

register(
    DocTypeDescriptor(
        name="Terms Template",
        slug="terms-template",
        model=TermsTemplate,
        title_field="template_name",
        naming="field:template_name",
        group="Selling",
        permission_name="Terms Template",
        permissions={"Sales Manager": _SALES_MANAGER, "Sales User": _SALES_USER},
        fields=(
            FieldSpec("template_name", "Template Name", "Data", required=True, in_list=True, span=2),
            FieldSpec("terms", "Terms and Conditions", "Text", span=2),
            FieldSpec("disabled", "Disabled", "Check", in_list=True),
        ),
        list_fields=("template_name", "disabled"),
    )
)

register(
    DocTypeDescriptor(
        name="UTM Source",
        slug="utm-source",
        model=UTMSource,
        title_field="utm_source_name",
        naming="field:utm_source_name",
        group="Selling",
        permission_name="UTM Source",
        permissions={"Sales Manager": _SALES_MANAGER, "Sales User": _SALES_USER},
        fields=(
            FieldSpec("utm_source_name", "Source Name", "Data", required=True, in_list=True, span=2),
            FieldSpec("disabled", "Disabled", "Check", in_list=True),
        ),
        list_fields=("utm_source_name", "disabled"),
    )
)

register(
    DocTypeDescriptor(
        name="Monthly Distribution",
        slug="monthly-distribution",
        model=MonthlyDistribution,
        title_field="distribution_name",
        naming="field:distribution_name",
        group="Selling",
        permission_name="Monthly Distribution",
        permissions={"Sales Manager": _SALES_MANAGER, "Sales User": _SALES_USER},
        fields=(
            FieldSpec("distribution_name", "Distribution Name", "Data", required=True, in_list=True, span=2),
            FieldSpec("month_1", "January %", "Float"),
            FieldSpec("month_2", "February %", "Float"),
            FieldSpec("month_3", "March %", "Float"),
            FieldSpec("month_4", "April %", "Float"),
            FieldSpec("month_5", "May %", "Float"),
            FieldSpec("month_6", "June %", "Float"),
            FieldSpec("month_7", "July %", "Float"),
            FieldSpec("month_8", "August %", "Float"),
            FieldSpec("month_9", "September %", "Float"),
            FieldSpec("month_10", "October %", "Float"),
            FieldSpec("month_11", "November %", "Float"),
            FieldSpec("month_12", "December %", "Float"),
        ),
        list_fields=("distribution_name",),
    )
)
