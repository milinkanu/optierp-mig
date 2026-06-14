"""Unit tests for the pricing-rule engine (pure matching/application logic)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.services.pricing import apply_rule, pick_rule, rule_matches

ITEM = uuid.uuid4()
OTHER_ITEM = uuid.uuid4()
GROUP = uuid.uuid4()
CUST = uuid.uuid4()
OTHER_CUST = uuid.uuid4()
TODAY = date(2026, 6, 1)


def _rule(**kw):
    base = dict(
        apply_on="Item",
        item_id=ITEM,
        item_group_id=None,
        customer_id=None,
        valid_from=None,
        valid_upto=None,
        min_qty=Decimal(0),
        max_qty=Decimal(0),
        rate_or_discount="Discount Percentage",
        discount_percentage=Decimal(0),
        discount_amount=Decimal(0),
        rate=Decimal(0),
        priority=0,
        creation=datetime(2026, 1, 1),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _match(rule, *, item_id=ITEM, item_group_id=GROUP, customer_id=CUST, qty=Decimal(1), on_date=TODAY):
    return rule_matches(
        rule, item_id=item_id, item_group_id=item_group_id, customer_id=customer_id,
        qty=qty, on_date=on_date,
    )


# --- apply_rule --------------------------------------------------------------


def test_apply_percentage():
    assert apply_rule(_rule(discount_percentage=Decimal(10)), Decimal(100)) == Decimal(90)


def test_apply_amount():
    assert apply_rule(_rule(rate_or_discount="Discount Amount", discount_amount=Decimal(20)), Decimal(100)) == Decimal(80)


def test_apply_amount_floored_at_zero():
    assert apply_rule(_rule(rate_or_discount="Discount Amount", discount_amount=Decimal(150)), Decimal(100)) == Decimal(0)


def test_apply_rate_override():
    assert apply_rule(_rule(rate_or_discount="Rate", rate=Decimal(55)), Decimal(100)) == Decimal(55)


# --- rule_matches ------------------------------------------------------------


def test_match_by_item():
    assert _match(_rule(item_id=ITEM))
    assert not _match(_rule(item_id=OTHER_ITEM))


def test_match_by_item_group():
    assert _match(_rule(apply_on="Item Group", item_group_id=GROUP, item_id=None))
    assert not _match(_rule(apply_on="Item Group", item_group_id=uuid.uuid4(), item_id=None))


def test_customer_filter():
    assert _match(_rule(customer_id=None))  # applies to all
    assert _match(_rule(customer_id=CUST))
    assert not _match(_rule(customer_id=OTHER_CUST))


def test_qty_window():
    assert not _match(_rule(min_qty=Decimal(5)), qty=Decimal(3))
    assert _match(_rule(min_qty=Decimal(5)), qty=Decimal(10))
    assert not _match(_rule(max_qty=Decimal(8)), qty=Decimal(10))
    assert _match(_rule(max_qty=Decimal(0)), qty=Decimal(9999))  # 0 = no upper bound


def test_date_window():
    assert not _match(_rule(valid_from=date(2026, 7, 1)))  # not started
    assert not _match(_rule(valid_upto=date(2026, 5, 1)))  # expired
    assert _match(_rule(valid_from=date(2026, 1, 1), valid_upto=date(2026, 12, 31)))


# --- pick_rule ---------------------------------------------------------------


def test_pick_highest_priority():
    low = _rule(priority=1)
    high = _rule(priority=5)
    assert pick_rule([low, high]) is high


def test_pick_newest_on_tie():
    older = _rule(priority=3, creation=datetime(2026, 1, 1))
    newer = _rule(priority=3, creation=datetime(2026, 5, 1))
    assert pick_rule([older, newer]) is newer


def test_pick_none_when_empty():
    assert pick_rule([]) is None
