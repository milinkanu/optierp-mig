"""Unit tests for promotional-scheme matching and tier selection (pure logic)."""

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.promotion import best_tier_discount, scheme_matches

ITEM = uuid.uuid4()
GROUP = uuid.uuid4()
CUST = uuid.uuid4()
TODAY = date(2026, 6, 1)


def _scheme(**kw):
    base = dict(
        apply_on="Item", item_id=ITEM, item_group_id=None, customer_id=None,
        valid_from=None, valid_upto=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _tier(min_qty, disc):
    return SimpleNamespace(min_qty=Decimal(min_qty), discount_percentage=Decimal(disc))


def _match(scheme, *, item_id=ITEM, item_group_id=GROUP, customer_id=CUST, on_date=TODAY):
    return scheme_matches(
        scheme, item_id=item_id, item_group_id=item_group_id, customer_id=customer_id, on_date=on_date
    )


# --- best_tier_discount ------------------------------------------------------


def test_no_tier_applies_below_min():
    assert best_tier_discount([_tier(10, 5)], Decimal(3)) == Decimal(0)


def test_best_applicable_tier_wins():
    tiers = [_tier(1, 2), _tier(10, 5), _tier(50, 10)]
    assert best_tier_discount(tiers, Decimal(20)) == Decimal(5)  # 1 and 10 apply -> max 5
    assert best_tier_discount(tiers, Decimal(100)) == Decimal(10)  # all apply -> max 10


def test_empty_tiers():
    assert best_tier_discount([], Decimal(100)) == Decimal(0)


# --- scheme_matches ----------------------------------------------------------


def test_match_by_item():
    assert _match(_scheme(item_id=ITEM))
    assert not _match(_scheme(item_id=uuid.uuid4()))


def test_match_by_item_group():
    assert _match(_scheme(apply_on="Item Group", item_group_id=GROUP, item_id=None))


def test_customer_filter():
    assert _match(_scheme(customer_id=None))
    assert _match(_scheme(customer_id=CUST))
    assert not _match(_scheme(customer_id=uuid.uuid4()))


def test_date_window():
    assert not _match(_scheme(valid_from=date(2026, 7, 1)))
    assert not _match(_scheme(valid_upto=date(2026, 5, 1)))
