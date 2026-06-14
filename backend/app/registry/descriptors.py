"""Descriptor definitions — the one place a simple master is declared.

Each ``register(...)`` call adds a DocType to the generic engine. Phase 0 ships
Campaign (the engine smoke-test pilot); Phases 1–2 add the tree masters and the
rest of the simple-master long tail here.
"""

from __future__ import annotations

from app.models.accounts import Account
from app.models.buying import Supplier
from app.models.selling import (
    Address,
    Campaign,
    Contact,
    CouponCode,
    Customer,
    CustomerGroup,
    MonthlyDistribution,
    PricingRule,
    SalesPartner,
    SalesPerson,
    ShippingRule,
    TermsTemplate,
    Territory,
    UTMSource,
)
from app.models.stock import Item, ItemGroup
from app.registry.base import REGISTRY, DocTypeDescriptor, FieldSpec, register

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

_SALES_USER_RW = ("read", "write", "create", "report")

register(
    DocTypeDescriptor(
        name="Address",
        slug="address",
        model=Address,
        title_field="address_title",
        naming="field:address_title",
        group="Selling",
        permission_name="Address",
        permissions={"Sales Manager": _SALES_MANAGER, "Sales User": _SALES_USER_RW},
        fields=(
            FieldSpec("address_title", "Address Title", "Data", required=True, in_list=True, span=2),
            FieldSpec("address_type", "Type", "Select",
                      options="Billing\nShipping\nOffice\nWarehouse", in_list=True),
            FieldSpec("address_line1", "Address Line 1", "Data", required=True, span=2),
            FieldSpec("address_line2", "Address Line 2", "Data", span=2),
            FieldSpec("city", "City", "Data"),
            FieldSpec("state", "State / Province", "Data"),
            FieldSpec("pincode", "Postal Code", "Data"),
            FieldSpec("country", "Country", "Data"),
            FieldSpec("customer_id", "Customer", "Link", options="customer"),
            FieldSpec("supplier_id", "Supplier", "Link", options="supplier"),
            FieldSpec("disabled", "Disabled", "Check"),
        ),
        list_fields=("address_title", "address_type", "city"),
    )
)

register(
    DocTypeDescriptor(
        name="Contact",
        slug="contact",
        model=Contact,
        title_field="first_name",
        naming="field:first_name",
        group="Selling",
        permission_name="Contact",
        permissions={"Sales Manager": _SALES_MANAGER, "Sales User": _SALES_USER_RW},
        fields=(
            FieldSpec("first_name", "First Name", "Data", required=True, in_list=True),
            FieldSpec("last_name", "Last Name", "Data", in_list=True),
            FieldSpec("email_id", "Email", "Email", in_list=True),
            FieldSpec("mobile_no", "Mobile", "Data"),
            FieldSpec("phone", "Phone", "Data"),
            FieldSpec("designation", "Designation", "Data"),
            FieldSpec("customer_id", "Customer", "Link", options="customer"),
            FieldSpec("supplier_id", "Supplier", "Link", options="supplier"),
            FieldSpec("disabled", "Disabled", "Check"),
        ),
        list_fields=("first_name", "last_name", "email_id"),
    )
)


# --- Selling: Customer (engine-served CRUD UI) -------------------------------
register(
    DocTypeDescriptor(
        name="Customer",
        slug="customer",
        model=Customer,
        title_field="customer_name",
        naming="field:customer_name",
        group="Selling",
        permission_name="Customer",
        permissions={"Sales Manager": _SALES_MANAGER, "Sales User": _SALES_USER_RW},
        fields=(
            FieldSpec("customer_name", "Customer Name", "Data", required=True, in_list=True, span=2),
            FieldSpec("customer_type", "Type", "Select", options="Company\nIndividual", in_list=True),
            FieldSpec("customer_group_id", "Customer Group", "Link", options="customer-group", in_list=True),
            FieldSpec("territory_id", "Territory", "Link", options="territory"),
            FieldSpec("tax_id", "Tax ID", "Data"),
            FieldSpec("default_currency", "Default Currency", "Data"),
            FieldSpec("credit_limit", "Credit Limit", "Float"),
            FieldSpec("disabled", "Disabled", "Check", in_list=True),
            FieldSpec("notes", "Notes", "Text", span=2),
        ),
        list_fields=("customer_name", "customer_type", "disabled"),
    )
)


# --- Items & Pricing: Pricing Rule (Phase 3) ---------------------------------
register(
    DocTypeDescriptor(
        name="Pricing Rule",
        slug="pricing-rule",
        model=PricingRule,
        title_field="title",
        naming="field:title",
        group="Selling",
        permission_name="Pricing Rule",
        permissions={"Sales Manager": _SALES_MANAGER, "Sales User": _SALES_USER},
        fields=(
            FieldSpec("title", "Title", "Data", required=True, in_list=True, span=2),
            FieldSpec("selling", "Applies to Selling", "Check"),
            FieldSpec("buying", "Applies to Buying", "Check"),
            FieldSpec("apply_on", "Apply On", "Select", options="Item\nItem Group", in_list=True),
            FieldSpec("item_id", "Item", "Link", options="item", help="When Apply On = Item"),
            FieldSpec("item_group_id", "Item Group", "Link", options="item-group",
                      help="When Apply On = Item Group"),
            FieldSpec("customer_id", "Customer", "Link", options="customer",
                      help="Leave blank to apply to all customers"),
            FieldSpec("customer_group_id", "Customer Group", "Link", options="customer-group",
                      help="Apply to a whole customer group"),
            FieldSpec("territory_id", "Territory", "Link", options="territory",
                      help="Apply to a whole territory"),
            FieldSpec("min_qty", "Min Qty", "Float"),
            FieldSpec("max_qty", "Max Qty", "Float", help="0 = no upper limit"),
            FieldSpec("valid_from", "Valid From", "Date"),
            FieldSpec("valid_upto", "Valid Upto", "Date"),
            FieldSpec("rate_or_discount", "Rate or Discount", "Select",
                      options="Discount Percentage\nDiscount Amount\nRate", in_list=True),
            FieldSpec("discount_percentage", "Discount %", "Float"),
            FieldSpec("discount_amount", "Discount Amount", "Float"),
            FieldSpec("rate", "Rate", "Float"),
            FieldSpec("priority", "Priority", "Int", help="Higher wins when several rules match"),
            FieldSpec("disabled", "Disabled", "Check", in_list=True),
        ),
        list_fields=("title", "apply_on", "rate_or_discount", "disabled"),
    )
)

register(
    DocTypeDescriptor(
        name="Coupon Code",
        slug="coupon-code",
        model=CouponCode,
        title_field="coupon_code",
        naming="field:coupon_code",
        group="Selling",
        permission_name="Coupon Code",
        permissions={"Sales Manager": _SALES_MANAGER, "Sales User": _SALES_USER},
        fields=(
            FieldSpec("coupon_code", "Coupon Code", "Data", required=True, in_list=True, span=2),
            FieldSpec("coupon_name", "Coupon Name", "Data"),
            FieldSpec("discount_percentage", "Discount %", "Float", in_list=True),
            FieldSpec("valid_from", "Valid From", "Date"),
            FieldSpec("valid_upto", "Valid Upto", "Date"),
            FieldSpec("maximum_use", "Maximum Use", "Int", help="0 = unlimited"),
            FieldSpec("disabled", "Disabled", "Check", in_list=True),
        ),
        # "used" is maintained by the engine on redemption — shown in the list, not editable.
        list_fields=("coupon_code", "discount_percentage", "used", "disabled"),
    )
)

register(
    DocTypeDescriptor(
        name="Shipping Rule",
        slug="shipping-rule",
        model=ShippingRule,
        title_field="shipping_rule_name",
        naming="field:shipping_rule_name",
        group="Selling",
        permission_name="Shipping Rule",
        permissions={"Sales Manager": _SALES_MANAGER, "Sales User": _SALES_USER},
        fields=(
            FieldSpec("shipping_rule_name", "Shipping Rule Name", "Data", required=True, in_list=True, span=2),
            FieldSpec("shipping_amount", "Shipping Amount", "Currency", in_list=True),
            FieldSpec("free_above", "Free Above Subtotal", "Currency", help="0 = never free"),
            FieldSpec("account_id", "Freight Account", "Link", options="account"),
            FieldSpec("disabled", "Disabled", "Check", in_list=True),
        ),
        list_fields=("shipping_rule_name", "shipping_amount", "disabled"),
    )
)


# --- Link sources ------------------------------------------------------------
# Lets engine Link fields target core/bespoke doctypes (not just engine masters),
# e.g. an Address's "customer" Link resolves Customers. Maps slug -> (model,
# title_field, permission_name). Engine descriptors are resolved first.
LINK_SOURCES: dict[str, tuple[type, str, str]] = {
    "customer": (Customer, "customer_name", "Customer"),
    "supplier": (Supplier, "supplier_name", "Supplier"),
    "item": (Item, "item_code", "Item"),
    "item-group": (ItemGroup, "item_group_name", "Item Group"),
    "account": (Account, "account_name", "Account"),
}


def resolve_link_source(slug: str) -> tuple[type, str, str, bool] | None:
    """Resolve a Link target slug to (model, title_field, permission_name, scoped).

    Checks registered descriptors first, then the LINK_SOURCES table for core
    doctypes. Returns None if the slug is unknown.
    """
    descriptor = REGISTRY.get(slug)
    if descriptor is not None:
        return (descriptor.model, descriptor.title_field, descriptor.permission_name, descriptor.scoped)
    src = LINK_SOURCES.get(slug)
    if src is not None:
        model, title_field, permission_name = src
        return (model, title_field, permission_name, True)
    return None
