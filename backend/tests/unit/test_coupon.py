"""Unit tests for coupon validity (pure logic)."""

from datetime import date
from types import SimpleNamespace

from app.services.coupon import coupon_invalid_reason

TODAY = date(2026, 6, 1)


def _coupon(**kw):
    base = dict(disabled=False, valid_from=None, valid_upto=None, maximum_use=0, used=0)
    base.update(kw)
    return SimpleNamespace(**base)


def test_valid_coupon():
    assert coupon_invalid_reason(_coupon(), TODAY) is None


def test_disabled():
    assert coupon_invalid_reason(_coupon(disabled=True), TODAY) == "Coupon is disabled"


def test_not_yet_valid():
    assert coupon_invalid_reason(_coupon(valid_from=date(2026, 7, 1)), TODAY) == "Coupon is not yet valid"


def test_expired():
    assert coupon_invalid_reason(_coupon(valid_upto=date(2026, 5, 1)), TODAY) == "Coupon has expired"


def test_usage_limit_reached():
    assert coupon_invalid_reason(_coupon(maximum_use=3, used=3), TODAY) == "Coupon usage limit reached"


def test_under_usage_limit():
    assert coupon_invalid_reason(_coupon(maximum_use=3, used=2), TODAY) is None


def test_unlimited_use():
    assert coupon_invalid_reason(_coupon(maximum_use=0, used=999), TODAY) is None
