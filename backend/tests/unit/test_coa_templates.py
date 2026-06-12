"""Unit tests — Chart of Accounts template loading (app.services.coa)."""

import pytest

from app.models.accounts import ROOT_TYPES
from app.services import coa


def test_bundled_templates_present():
    templates = coa.available_templates()
    assert "standard" in templates
    assert "in_standard" in templates
    assert "ae_uae_standard" in templates


@pytest.mark.parametrize("key", ["standard", "in_standard", "ae_uae_standard"])
def test_templates_parse_with_valid_roots(key: str):
    template = coa.load_template(key)
    tree = template["tree"]
    assert isinstance(tree, dict) and tree
    for root_name, root_node in tree.items():
        if not isinstance(root_node, dict):
            continue
        root_type = coa._node_root_type(root_name, root_node)
        assert root_type in ROOT_TYPES


def test_country_template_mapping():
    assert coa.template_for_country("IN") == "in_standard"
    assert coa.template_for_country("AE") == "ae_uae_standard"
    assert coa.template_for_country("US") == "standard"
    assert coa.template_for_country("GB") == "standard"
    assert coa.template_for_country(None) == "standard"
    assert coa.template_for_country("ZZ") == "standard"  # unknown -> fallback


def test_unknown_template_raises():
    from app.core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        coa.load_template("does_not_exist")


def test_slugify_ltree_safe():
    assert coa._slugify("Application of Funds (Assets)") == "application_of_funds_assets"
    assert coa._slugify("Cash In Hand") == "cash_in_hand"
    assert coa._slugify("---") == "node"
