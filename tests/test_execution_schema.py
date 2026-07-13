"""execution.schema — dataclass + JSONL round-trip tests. Offline, synthetic
fixtures only (house style: no network, no live client)."""
from __future__ import annotations

import json

import pytest

from execution.schema import (SCHEMA_VERSION, VALID_FILL_PRICE_TAGS,
                              VALID_SETTLEMENT_TAGS, Fill, Order, Position,
                              Settlement, line_to_record, record_to_line)


def _order(**kw):
    base = dict(order_id="o1", ts="2026-07-11T00:00:00Z", ticker="KX-T", side="yes",
                action="buy", limit_price=0.40, qty=10, tif="ioc", strategy="s6shadow")
    base.update(kw)
    return Order(**base)


def _fill(**kw):
    base = dict(fill_id="o1:F", order_id="o1", ts="2026-07-11T00:00:00Z", ticker="KX-T",
                side="yes", action="buy", price=0.40, qty=10, fee=0.05,
                fill_model="taker_depth", price_source_tag="real_ask", caveats=[])
    base.update(kw)
    return Fill(**base)


def _settlement(**kw):
    base = dict(settlement_id="s1", ts="2026-07-11T00:00:00Z", ticker="KX-T", side="no",
                settle_value=1.0, qty=1, event_ticker="KX-EV", price_source_tag="broker_truth")
    base.update(kw)
    return Settlement(**base)


# --------------------------------------------------------------------------- #
# Order
# --------------------------------------------------------------------------- #
def test_order_roundtrips_through_jsonl():
    o = _order()
    line = record_to_line(o)
    back = line_to_record(line)
    assert isinstance(back, Order)
    assert back == o


def test_order_line_carries_record_kind_and_schema_version():
    d = json.loads(record_to_line(_order()))
    assert d["record_kind"] == "order"
    assert d["schema_version"] == SCHEMA_VERSION


def test_order_validate_accepts_clean_order():
    assert _order().validate() == []


def test_order_validate_rejects_bad_side_action_tif():
    errs = _order(side="maybe", action="hold", tif="gtc").validate()
    assert any("side" in e for e in errs)
    assert any("action" in e for e in errs)
    assert any("tif" in e for e in errs)


def test_order_validate_rejects_price_out_of_kalshi_range():
    assert any("limit_price" in e for e in _order(limit_price=1.5).validate())
    assert any("limit_price" in e for e in _order(limit_price=0.0).validate())


def test_order_validate_rejects_nonpositive_qty():
    assert any("qty" in e for e in _order(qty=0).validate())


def test_order_roundtrips_with_event_ticker():
    o = _order(event_ticker="KX-EV")
    back = line_to_record(record_to_line(o))
    assert isinstance(back, Order)
    assert back == o
    assert back.event_ticker == "KX-EV"


def test_order_without_event_ticker_defaults_empty_and_back_compat_parses():
    # a legacy ledger line with no event_ticker field still parses (d.get default)
    d = json.loads(record_to_line(_order()))
    d.pop("event_ticker")
    back = Order.from_dict(d)
    assert back.event_ticker == ""


# --------------------------------------------------------------------------- #
# Settlement
# --------------------------------------------------------------------------- #
def test_settlement_roundtrips_through_jsonl():
    s = _settlement()
    line = record_to_line(s)
    back = line_to_record(line)
    assert isinstance(back, Settlement)
    assert back == s


def test_settlement_line_carries_record_kind():
    d = json.loads(record_to_line(_settlement()))
    assert d["record_kind"] == "settlement"


def test_settlement_validate_accepts_zero_and_one():
    assert _settlement(settle_value=1.0).validate() == []
    assert _settlement(settle_value=0.0).validate() == []


def test_settlement_validate_rejects_midband_value():
    """0.5 is a market price, NOT a binary expiry — a settlement rejects it."""
    assert any("settle_value" in e for e in _settlement(settle_value=0.5).validate())


def test_settlement_validate_rejects_tradeable_market_price():
    """Even a value inside Fill's [0.01,0.99] band is invalid for a settlement:
    a settlement must be exactly 0.0 or 1.0 (broker-truth expiry realization)."""
    assert any("settle_value" in e for e in _settlement(settle_value=0.40).validate())


def test_settlement_validate_rejects_non_broker_truth_tag():
    for bad in ("real_ask", "real_bid", "synthetic", "midpoint"):
        assert any("price_source_tag" in e
                   for e in _settlement(price_source_tag=bad).validate())


def test_settlement_validate_rejects_empty_event_ticker_and_bad_side():
    assert any("event_ticker" in e for e in _settlement(event_ticker="").validate())
    assert any("side" in e for e in _settlement(side="maybe").validate())


def test_valid_settlement_tags_is_only_broker_truth():
    assert VALID_SETTLEMENT_TAGS == frozenset({"broker_truth"})


# --------------------------------------------------------------------------- #
# Fill
# --------------------------------------------------------------------------- #
def test_fill_roundtrips_through_jsonl():
    f = _fill(caveats=["size_unverified"])
    back = line_to_record(record_to_line(f))
    assert isinstance(back, Fill)
    assert back == f


def test_fill_line_carries_record_kind():
    d = json.loads(record_to_line(_fill()))
    assert d["record_kind"] == "fill"


def test_fill_validate_accepts_real_ask_and_real_bid():
    assert _fill(price_source_tag="real_ask").validate() == []
    assert _fill(price_source_tag="real_bid").validate() == []


def test_fill_validate_rejects_synthetic_price_tag():
    """A paper fill may NEVER fill against a synthetic/modeled price."""
    errs = _fill(price_source_tag="synthetic").validate()
    assert any("synthetic" in e or "fillable real price" in e for e in errs)


def test_fill_validate_rejects_midpoint_tag():
    errs = _fill(price_source_tag="midpoint").validate()
    assert errs  # midpoint is not fillable


def test_valid_fill_price_tags_are_exactly_the_two_real_sides():
    assert VALID_FILL_PRICE_TAGS == frozenset({"real_ask", "real_bid"})


def test_fill_validate_rejects_negative_fee():
    assert any("fee" in e for e in _fill(fee=-0.01).validate())


# --------------------------------------------------------------------------- #
# Position
# --------------------------------------------------------------------------- #
def test_position_roundtrips_through_dict():
    p = Position(ticker="KX-T", side="yes", qty=10, avg_cost=0.40, realized_pnl=1.25)
    assert Position.from_dict(p.to_dict()) == p


# --------------------------------------------------------------------------- #
# line_to_record edge cases
# --------------------------------------------------------------------------- #
def test_blank_line_parses_to_none():
    assert line_to_record("   ") is None
    assert line_to_record("") is None


def test_unknown_record_kind_raises_rather_than_silently_skips():
    line = json.dumps({"record_kind": "coupon", "x": 1})
    with pytest.raises(ValueError):
        line_to_record(line)


def test_record_to_line_rejects_non_record():
    with pytest.raises(TypeError):
        record_to_line({"record_kind": "order"})
