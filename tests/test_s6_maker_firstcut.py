"""Offline unit tests for scripts/s6_maker_firstcut.py — the S6 maker first-cut probe.

Covers the core logic with tiny synthetic snapshot fixtures (no network, no tape, no clock):
consecutive-pair construction (dedup, gap filter, one-sided/crossed skips per lesson L23), the
half-spread / adverse-selection / maker-fee net arithmetic, the flat-1c maker fee fact the
verdict rests on, the L28 frozen-fraction precheck, and the by-ticker block bootstrap."""
from __future__ import annotations

import pytest

from core.pricing import MAKER_FEE_RATE, fee_per_contract
from scripts import s6_maker_firstcut as s6


def _rec(ticker, cid, captured_at, yes_ask, yes_bid):
    """A minimal orderbook_depth.v1-shaped record (only the fields the probe reads)."""
    return {
        "ticker": ticker,
        "capture_id": cid,
        "captured_at": captured_at,
        "best_yes_ask": yes_ask,
        "best_yes_bid": yes_bid,
    }


# --------------------------------------------------------------------------- #
# maker_net arithmetic + the flat maker fee
# --------------------------------------------------------------------------- #
def test_maker_fee_is_flat_one_cent_at_every_interior_price():
    # ceil(0.0175 * P * (1-P) * 100)/100 == 0.01 for all 0<P<1 (max P(1-P)=0.25 -> 0.4375 -> 1)
    for p in (0.01, 0.1, 0.25, 0.5, 0.63, 0.9, 0.99):
        assert fee_per_contract(p, MAKER_FEE_RATE) == pytest.approx(0.01)


def test_maker_net_frozen_book_is_half_spread_minus_fee():
    # spread 4c -> half 2c; no mid move -> net = 0.02 - 0 - 0.01 = 0.01
    net = s6.maker_net(half_spread=0.02, dmid=0.0, fill_price=0.50)
    assert net == pytest.approx(0.01)


def test_maker_net_adverse_move_eats_the_spread():
    # half-spread 2c but mid moved 3c against -> net = 0.02 - 0.03 - 0.01 = -0.02
    net = s6.maker_net(half_spread=0.02, dmid=0.03, fill_price=0.50)
    assert net == pytest.approx(-0.02)
    # sign of dmid must not matter (adverse on either side)
    assert s6.maker_net(0.02, -0.03, 0.50) == pytest.approx(-0.02)


# --------------------------------------------------------------------------- #
# build_pairs: consecutive pairing, dedup, gap filter, one-sided/crossed skips
# --------------------------------------------------------------------------- #
def test_build_pairs_basic_consecutive_two_sided():
    recs = [
        _rec("T", "c1", "2026-07-07T00:00:00+00:00", 0.55, 0.51),
        _rec("T", "c2", "2026-07-07T00:31:00+00:00", 0.57, 0.53),
    ]
    pairs = s6.build_pairs(recs)
    assert len(pairs) == 1
    p = pairs[0]
    assert p.spread_cents == 4
    assert p.half_spread == pytest.approx(0.02)
    # mid1=0.53, mid2=0.55 -> dmid=+0.02, filled on ask side, moved True
    assert p.dmid == pytest.approx(0.02)
    assert p.moved is True
    assert p.fill_price == pytest.approx(0.55)
    assert p.net == pytest.approx(0.02 - 0.02 - 0.01)


def test_build_pairs_dedups_repeat_capture_id():
    # a duplicated pass line (same capture_id) must not fake a zero-gap pair
    recs = [
        _rec("T", "c1", "2026-07-07T00:00:00+00:00", 0.55, 0.51),
        _rec("T", "c1", "2026-07-07T00:00:00+00:00", 0.55, 0.51),
        _rec("T", "c2", "2026-07-07T00:31:00+00:00", 0.55, 0.51),
    ]
    pairs = s6.build_pairs(recs)
    assert len(pairs) == 1


def test_build_pairs_gap_filter_excludes_stale_overnight_pair():
    recs = [
        _rec("T", "c1", "2026-07-07T23:00:00+00:00", 0.55, 0.51),
        _rec("T", "c2", "2026-07-08T12:00:00+00:00", 0.55, 0.51),  # 13h later
    ]
    assert s6.build_pairs(recs, max_gap_min=90.0) == []
    assert len(s6.build_pairs(recs, max_gap_min=24 * 60)) == 1


def test_build_pairs_skips_one_sided_book_L23():
    # capture-1 has an empty ask side (None) -> valid one-sided book, not a quotable spread
    recs = [
        _rec("T", "c1", "2026-07-07T00:00:00+00:00", None, 0.51),
        _rec("T", "c2", "2026-07-07T00:31:00+00:00", 0.55, 0.51),
    ]
    assert s6.build_pairs(recs) == []


def test_build_pairs_skips_crossed_or_zero_spread():
    recs = [
        _rec("T", "c1", "2026-07-07T00:00:00+00:00", 0.51, 0.51),  # zero spread
        _rec("T", "c2", "2026-07-07T00:31:00+00:00", 0.55, 0.51),
    ]
    assert s6.build_pairs(recs) == []


def test_build_pairs_separates_by_ticker():
    recs = [
        _rec("A", "c1", "2026-07-07T00:00:00+00:00", 0.55, 0.51),
        _rec("A", "c2", "2026-07-07T00:31:00+00:00", 0.55, 0.51),
        _rec("B", "c1", "2026-07-07T00:00:00+00:00", 0.30, 0.26),
        _rec("B", "c2", "2026-07-07T00:31:00+00:00", 0.30, 0.26),
    ]
    pairs = s6.build_pairs(recs)
    assert {p.ticker for p in pairs} == {"A", "B"}
    assert len(pairs) == 2


# --------------------------------------------------------------------------- #
# L28 precheck: frozen fraction
# --------------------------------------------------------------------------- #
def test_precheck_frozen_fraction():
    recs = [
        # frozen pair (BBO identical)
        _rec("A", "c1", "2026-07-07T00:00:00+00:00", 0.55, 0.51),
        _rec("A", "c2", "2026-07-07T00:31:00+00:00", 0.55, 0.51),
        # moved pair
        _rec("B", "c1", "2026-07-07T00:00:00+00:00", 0.30, 0.26),
        _rec("B", "c2", "2026-07-07T00:31:00+00:00", 0.34, 0.30),
    ]
    pc = s6.precheck(s6.build_pairs(recs))
    assert pc["n_pairs"] == 2
    assert pc["n_frozen_bbo"] == 1
    assert pc["frac_frozen_bbo"] == pytest.approx(0.5)
    assert pc["n_mid_moved"] == 1


def test_precheck_empty_is_safe():
    assert s6.precheck([]) == {"n_pairs": 0}


# --------------------------------------------------------------------------- #
# block bootstrap by ticker: deterministic, correct shape, CI brackets the mean
# --------------------------------------------------------------------------- #
def _pair(ticker, net):
    return s6.MakerPair(
        ticker=ticker, cap1_id="c1", cap2_id="c2", gap_min=30.0,
        yes_ask1=0.55, yes_bid1=0.51, yes_ask2=0.55, yes_bid2=0.51,
        spread_cents=4, half_spread=0.02, mid1=0.53, mid2=0.53, dmid=0.0,
        moved=False, fill_price=0.51, maker_fee=0.01, net=net,
    )


def test_bootstrap_by_ticker_deterministic_and_bracketing():
    pairs = [_pair("A", 0.01), _pair("A", 0.03), _pair("B", -0.05), _pair("C", 0.00)]
    out = s6.block_bootstrap_by_ticker(pairs, n_boot=2000, seed=42)
    assert out["n_tickers"] == 3
    assert out["n_pairs"] == 4
    # grand mean = (0.01+0.03-0.05+0.00)/4 = -0.0025
    assert out["mean"] == pytest.approx(-0.0025)
    lo, hi = out["ci95"]
    assert lo <= out["mean"] <= hi
    # deterministic under fixed seed
    again = s6.block_bootstrap_by_ticker(pairs, n_boot=2000, seed=42)
    assert again["ci95"] == out["ci95"]


def test_bootstrap_respects_predicate():
    pairs = [_pair("A", 0.01), _pair("B", -0.05)]
    out = s6.block_bootstrap_by_ticker(pairs, predicate=lambda p: p.net > 0, n_boot=500)
    assert out["n_tickers"] == 1
    assert out["mean"] == pytest.approx(0.01)


def test_bootstrap_empty_population_is_safe():
    out = s6.block_bootstrap_by_ticker([], n_boot=100)
    assert out["n_tickers"] == 0
    assert out["mean"] is None


def test_population_report_wing_positive_tight_negative_on_synthetic():
    # a wing pair (huge nominal spread, frozen) books its whole half-spread; a tight frozen 1c
    # pair nets negative (0.005 - 0.01). Confirms the artifact/verdict directions structurally.
    wing = s6.build_pairs([
        _rec("W", "c1", "2026-07-07T00:00:00+00:00", 0.89, 0.03),
        _rec("W", "c2", "2026-07-07T00:31:00+00:00", 0.89, 0.03),
    ])
    tight = s6.build_pairs([
        _rec("T", "c1", "2026-07-07T00:00:00+00:00", 0.51, 0.50),
        _rec("T", "c2", "2026-07-07T00:31:00+00:00", 0.51, 0.50),
    ])
    assert wing[0].net > 0        # unfillable-wing artifact
    assert tight[0].net < 0       # flat 1c fee eats the 0.5c half-spread
