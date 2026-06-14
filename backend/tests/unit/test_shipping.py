"""Unit tests for shipping-rule freight calculation (pure logic)."""

from decimal import Decimal
from types import SimpleNamespace

from app.services.shipping import shipping_amount_for


def _rule(**kw):
    base = dict(shipping_amount=Decimal(50), free_above=Decimal(0))
    base.update(kw)
    return SimpleNamespace(**base)


def test_flat_charge():
    assert shipping_amount_for(_rule(), Decimal(100)) == Decimal(50)


def test_free_above_threshold():
    rule = _rule(shipping_amount=Decimal(50), free_above=Decimal(1000))
    assert shipping_amount_for(rule, Decimal(999)) == Decimal(50)  # below threshold -> charged
    assert shipping_amount_for(rule, Decimal(1000)) == Decimal(0)  # at threshold -> free
    assert shipping_amount_for(rule, Decimal(2000)) == Decimal(0)  # above -> free


def test_free_above_zero_never_free():
    assert shipping_amount_for(_rule(free_above=Decimal(0)), Decimal(10_000_000)) == Decimal(50)
