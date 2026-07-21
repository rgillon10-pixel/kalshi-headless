"""Offline unit tests for scripts/seed5_funding_prior_probe.py pure logic.

No network, no tape — synthetic fixtures only. Covers the parsing/matching/selection logic
that must be right before any verdict: funding-in-force lookup, sign-convention mapping,
nearest-fillable-bracket selection (raw-ask pin exclusion + side geometry), and net P&L
(taker fee via the sanctioned core.pricing).
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from core import pricing  # noqa: E402
from scripts import seed5_funding_prior_probe as probe  # noqa: E402


def _dt(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


# ── funding_at_time ─────────────────────────────────────────────────────────────

def test_funding_at_time_picks_most_recent_at_or_before():
    # prints at 00:00 and 08:00 UTC
    t0 = int(_dt("2026-07-14T00:00:00").timestamp() * 1000)
    t1 = int(_dt("2026-07-14T08:00:00").timestamp() * 1000)
    series = [(t0, 0.0001), (t1, -0.0002)]
    # 05:00 -> in force is the 00:00 print
    assert probe.funding_at_time(series, _dt("2026-07-14T05:00:00")) == 0.0001
    # 08:00 exactly -> the 08:00 print (<= boundary)
    assert probe.funding_at_time(series, _dt("2026-07-14T08:00:00")) == -0.0002
    # 12:00 -> still the 08:00 print
    assert probe.funding_at_time(series, _dt("2026-07-14T12:00:00")) == -0.0002


def test_funding_at_time_before_first_print_is_none():
    t0 = int(_dt("2026-07-14T08:00:00").timestamp() * 1000)
    series = [(t0, 0.0001)]
    assert probe.funding_at_time(series, _dt("2026-07-14T00:00:00")) is None


def test_funding_at_time_empty_series_is_none():
    assert probe.funding_at_time([], _dt("2026-07-14T00:00:00")) is None


# ── implied_side ────────────────────────────────────────────────────────────────

def test_implied_side_momentum():
    assert probe.implied_side(0.0001, "momentum") == "up"
    assert probe.implied_side(-0.0001, "momentum") == "down"


def test_implied_side_contrarian_is_the_mirror():
    assert probe.implied_side(0.0001, "contrarian") == "down"
    assert probe.implied_side(-0.0001, "contrarian") == "up"


def test_implied_side_unknown_convention_raises():
    with pytest.raises(ValueError):
        probe.implied_side(0.0001, "nonsense")


# ── nearest_fillable_bracket ────────────────────────────────────────────────────

def _bracket(floor, cap, yes_ask, ticker):
    return {"floor_strike": floor, "cap_strike": cap, "yes_ask": yes_ask, "ticker": ticker}


def test_nearest_fillable_up_side_picks_closest_above_spot():
    outs = [
        _bracket(100, 200, 0.30, "A"),   # above spot 150? floor 100 < 150 -> not up-side
        _bracket(200, 300, 0.20, "B"),   # floor 200 >= 150 -> up, dist 50
        _bracket(300, 400, 0.10, "C"),   # floor 300 >= 150 -> up, dist 150
    ]
    o = probe.nearest_fillable_bracket(outs, 150.0, "up", 0.05, 0.95)
    assert o["ticker"] == "B"


def test_nearest_fillable_down_side_picks_closest_below_spot():
    outs = [
        _bracket(100, 200, 0.30, "A"),   # cap 200 > 150 -> not down-side
        _bracket(0, 100, 0.20, "B"),     # cap 100 <= 150 -> down, dist 50
        _bracket(-100, 0, 0.10, "C"),    # cap 0 <= 150 -> down, dist 150
    ]
    o = probe.nearest_fillable_bracket(outs, 150.0, "down", 0.05, 0.95)
    assert o["ticker"] == "B"


def test_nearest_fillable_excludes_floor_pinned_wings():
    # only a 1c-floor-pinned bracket exists above spot -> no fillable trade (S10)
    outs = [_bracket(200, 300, 0.01, "PIN")]
    assert probe.nearest_fillable_bracket(outs, 150.0, "up", 0.05, 0.95) is None


def test_nearest_fillable_excludes_ceiling_pinned():
    outs = [_bracket(200, 300, 0.99, "HOT")]
    assert probe.nearest_fillable_bracket(outs, 150.0, "up", 0.05, 0.95) is None


def test_nearest_fillable_none_when_side_empty():
    outs = [_bracket(0, 100, 0.30, "B")]  # only a down-side bracket
    assert probe.nearest_fillable_bracket(outs, 150.0, "up", 0.05, 0.95) is None


def test_nearest_fillable_band_bounds_inclusive():
    outs = [_bracket(200, 300, 0.05, "LO"), _bracket(300, 400, 0.95, "HI")]
    # both inside inclusive band; nearest above spot is LO
    assert probe.nearest_fillable_bracket(outs, 150.0, "up", 0.05, 0.95)["ticker"] == "LO"


# ── trade_net_pnl (fee via core.pricing) ────────────────────────────────────────

def test_trade_net_pnl_win_matches_core_fee():
    entry = 0.20
    fee = pricing.fee_per_contract(entry, pricing.TAKER_FEE_RATE)
    assert probe.trade_net_pnl(entry, True) == pytest.approx(1.0 - entry - fee)


def test_trade_net_pnl_loss_matches_core_fee():
    entry = 0.20
    fee = pricing.fee_per_contract(entry, pricing.TAKER_FEE_RATE)
    assert probe.trade_net_pnl(entry, False) == pytest.approx(0.0 - entry - fee)


def test_trade_net_pnl_uses_taker_not_maker_rate():
    # L5: must be taker (0.07), not maker (0.0175). At 0.20 the fees differ.
    entry = 0.20
    taker = probe.trade_net_pnl(entry, False)
    maker_fee = pricing.fee_per_contract(entry, pricing.MAKER_FEE_RATE)
    assert taker != pytest.approx(0.0 - entry - maker_fee)


# ── side-degeneracy flag (L41) ──────────────────────────────────────────────────

def test_side_degeneracy_flags_one_sided():
    assert probe._side_degeneracy(95, 5) is not None
    assert probe._side_degeneracy(50, 50) is None
    assert probe._side_degeneracy(0, 0) == "no_trades"


# ── parse_iso_utc ───────────────────────────────────────────────────────────────

def test_parse_iso_utc_handles_z_suffix():
    d = probe.parse_iso_utc("2026-07-14T02:00:00Z")
    assert d.tzinfo is not None
    assert d.hour == 2
