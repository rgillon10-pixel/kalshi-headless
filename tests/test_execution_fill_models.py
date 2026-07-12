"""execution.fill_models — taker/maker fill tests. Offline: synthetic tape dicts
only, no network. Fees are asserted to come from core.pricing (lesson L18)."""
from __future__ import annotations

import pytest

from core.pricing import MAKER_FEE_RATE, TAKER_FEE_RATE, fee_per_contract
from execution.fill_models import last_reason, maker_resting, taker_immediate
from execution.schema import Order


def _order(**kw):
    base = dict(order_id="o1", ts="2026-07-11T00:00:00Z", ticker="KX-T", side="yes",
                action="buy", limit_price=0.40, qty=10, tif="ioc", strategy="s")
    base.update(kw)
    return Order(**base)


def _depth(**kw):
    """orderbook_depth.v1-shaped record. YES ask = 1 - best no_bid."""
    base = dict(
        price_source_tags={"asks": "real_ask", "bids": "real_bid"},
        no_bids=[[0.62, 10.0], [0.61, 100.0]],   # -> YES asks 0.38 (10), 0.39 (100)
        yes_bids=[[0.37, 5.0]],                    # -> NO asks 0.63 (5)
        best_yes_ask=0.38, best_no_ask=0.63,
        best_yes_bid=0.37, best_no_bid=0.62,
        ticker="KX-T", captured_at="2026-07-11T00:00:00Z",
    )
    base.update(kw)
    return base


def _sports(**kw):
    """sports_pairs.v1-shaped record (BBO, no size)."""
    outcome = dict(ticker="KX-T", yes_ask=0.40, no_ask=0.62, yes_bid=0.38, no_bid=0.60,
                   price_source_tag="real_ask")
    outcome.update(kw.pop("outcome", {}))
    base = dict(schema_version="sports_pairs.v1", ticker="KX-T-EVENT",
                captured_at="2026-07-11T00:00:00Z", outcomes=[outcome])
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# taker_immediate — depth walk
# --------------------------------------------------------------------------- #
def test_taker_depth_fills_full_qty_walking_the_ladder():
    o = _order(limit_price=0.40, qty=50)
    f = taker_immediate(o, _depth())
    assert f is not None
    assert f.fill_model == "taker_depth"
    assert f.qty == 50            # 10 @ 0.38 + 40 @ 0.39
    assert f.price == pytest.approx(round((10 * 0.38 + 40 * 0.39) / 50, 2))
    assert "partial_fill" not in f.caveats
    assert f.price_source_tag == "real_ask"


def test_taker_depth_partial_fill_when_limit_below_deep_levels():
    """Limit 0.38 only crosses the first (10-contract) level -> partial fill."""
    o = _order(limit_price=0.38, qty=50)
    f = taker_immediate(o, _depth())
    assert f is not None
    assert f.qty == 10
    assert "partial_fill" in f.caveats
    assert f.price == pytest.approx(0.38)


def test_taker_depth_no_fill_when_limit_below_best_ask():
    o = _order(limit_price=0.30, qty=10)
    assert taker_immediate(o, _depth()) is None
    assert "does not cross" in last_reason()


def test_taker_depth_fee_comes_from_core_pricing_taker_rate():
    o = _order(limit_price=0.40, qty=10)
    f = taker_immediate(o, _depth())
    expected = round(fee_per_contract(f.price, rate=TAKER_FEE_RATE) * f.qty, 4)
    assert f.fee == pytest.approx(expected)


def test_taker_depth_buy_no_side_walks_yes_bids():
    """Buying NO lifts the NO ask = 1 - best yes_bid = 0.63, size 5."""
    o = _order(side="no", limit_price=0.65, qty=3)
    f = taker_immediate(o, _depth())
    assert f is not None
    assert f.price == pytest.approx(0.63)
    assert f.qty == 3


# --------------------------------------------------------------------------- #
# taker_immediate — BBO no size
# --------------------------------------------------------------------------- #
def test_taker_bbo_fills_full_qty_with_size_unverified_caveat():
    o = _order(limit_price=0.40, qty=25)
    f = taker_immediate(o, _sports())
    assert f is not None
    assert f.fill_model == "taker_bbo_nosize"
    assert f.qty == 25                       # size unverified, we trust requested qty
    assert "size_unverified" in f.caveats
    assert f.price == pytest.approx(0.40)


def test_taker_bbo_fee_from_core_pricing():
    o = _order(limit_price=0.40, qty=25)
    f = taker_immediate(o, _sports())
    assert f.fee == pytest.approx(round(fee_per_contract(0.40, rate=TAKER_FEE_RATE) * 25, 4))


def test_taker_bbo_no_fill_when_limit_below_ask():
    o = _order(limit_price=0.35, qty=10)
    assert taker_immediate(o, _sports()) is None
    assert "does not cross" in last_reason()


def test_taker_bbo_ticker_not_in_record_returns_none():
    o = _order(ticker="KX-OTHER", limit_price=0.99, qty=1)
    assert taker_immediate(o, _sports()) is None
    assert "not found" in last_reason()


# --------------------------------------------------------------------------- #
# synthetic-price rejection (both families)
# --------------------------------------------------------------------------- #
def test_taker_depth_rejects_synthetic_ask_tag():
    rec = _depth(price_source_tags={"asks": "synthetic", "bids": "real_bid"})
    o = _order(limit_price=0.40, qty=10)
    assert taker_immediate(o, rec) is None
    assert "synthetic" in last_reason()


def test_taker_depth_rejects_untagged_ask_side():
    rec = _depth(price_source_tags={"bids": "real_bid"})  # no 'asks' tag -> synthetic
    o = _order(limit_price=0.40, qty=10)
    assert taker_immediate(o, rec) is None


def test_taker_bbo_rejects_synthetic_tag():
    rec = _sports(outcome={"price_source_tag": "synthetic"})
    o = _order(limit_price=0.40, qty=10)
    assert taker_immediate(o, rec) is None
    assert "synthetic" in last_reason()


def test_taker_bbo_rejects_midpoint_tag():
    rec = _sports(outcome={"price_source_tag": "midpoint"})
    o = _order(limit_price=0.40, qty=10)
    assert taker_immediate(o, rec) is None


def test_taker_immediate_refuses_sell_action_explicitly():
    o = _order(action="sell", limit_price=0.40, qty=10)
    assert taker_immediate(o, _depth()) is None
    assert "buys only" in last_reason()


# --------------------------------------------------------------------------- #
# maker_resting — candlestick through (generalized s13 rule)
# --------------------------------------------------------------------------- #
def _candles(lows=None, highs=None, tag="real_ask"):
    out = []
    for lo in (lows or []):
        out.append({"price": {"low_dollars": str(lo)}, "price_source_tag": tag})
    for hi in (highs or []):
        out.append({"price": {"high_dollars": str(hi)}, "price_source_tag": tag})
    return out


def test_maker_buy_fills_when_later_low_crosses_limit():
    o = _order(action="buy", tif="rest", limit_price=0.35, qty=10)
    f = maker_resting(o, _candles(lows=[0.50, 0.30]))
    assert f is not None
    assert f.fill_model == "maker_candle_through"
    assert f.price == pytest.approx(0.35)
    assert set(f.caveats) == {"no_queue_model", "optimistic_fill"}
    assert f.price_source_tag == "real_bid"   # a resting buy fills against the bid side


def test_maker_buy_no_fill_when_low_never_reaches_limit():
    o = _order(action="buy", tif="rest", limit_price=0.20, qty=10)
    assert maker_resting(o, _candles(lows=[0.50, 0.30])) is None
    assert "no later trade crossed" in last_reason()


def test_maker_sell_fills_when_later_high_crosses_limit():
    o = _order(action="sell", tif="rest", limit_price=0.60, qty=10)
    f = maker_resting(o, _candles(highs=[0.55, 0.65]))
    assert f is not None
    assert f.price == pytest.approx(0.60)
    assert f.price_source_tag == "real_ask"   # a resting sell fills against the ask side


def test_maker_fee_is_maker_rate_not_taker_rate():
    o = _order(action="buy", tif="rest", limit_price=0.35, qty=10)
    f = maker_resting(o, _candles(lows=[0.30]))
    assert f.fee == pytest.approx(round(fee_per_contract(0.35, rate=MAKER_FEE_RATE) * 10, 4))
    assert f.fee != pytest.approx(round(fee_per_contract(0.35, rate=TAKER_FEE_RATE) * 10, 4))


def test_maker_rejects_synthetic_candle_tag():
    o = _order(action="buy", tif="rest", limit_price=0.35, qty=10)
    assert maker_resting(o, _candles(lows=[0.30], tag="synthetic")) is None
    assert "not real" in last_reason()


def test_maker_rejects_untagged_candles():
    o = _order(action="buy", tif="rest", limit_price=0.35, qty=10)
    candles = [{"price": {"low_dollars": "0.30"}}]  # no price_source_tag
    assert maker_resting(o, candles) is None


def test_maker_no_trade_data_is_honest_no_fill():
    o = _order(action="buy", tif="rest", limit_price=0.35, qty=10)
    candles = [{"price": {}, "price_source_tag": "real_ask"}]
    assert maker_resting(o, candles) is None
    assert "no realized trade data" in last_reason()
