"""core/depth.py — ladder-depth helpers (L67 two-sided-depth-illusion lesson)."""
from __future__ import annotations

import pytest

from core.depth import (capturable_depth, lottery_tail_fraction, total_ladder_depth,
                        whole_contracts_available)


# ─── capturable_depth ───────────────────────────────────────────────────────

def test_capturable_depth_sums_only_levels_within_band():
    # best_yes_bid = 0.61; band = 5c -> [0.56, 0.66] captures the first two levels only.
    ladder = [[0.61, 200.0], [0.60, 50.0], [0.55, 999.0], [0.10, 1.0]]
    assert capturable_depth(ladder, 0.61, band_cents=5.0) == 250.0


def test_capturable_depth_none_ladder_is_zero_not_a_crash():
    assert capturable_depth(None, 0.61) == 0.0
    assert capturable_depth([], 0.61) == 0.0


def test_capturable_depth_none_best_price_is_zero():
    assert capturable_depth([[0.61, 200.0]], None) == 0.0


def test_capturable_depth_skips_malformed_levels():
    ladder = [[0.61, 200.0], None, [0.60], [None, 50.0], [0.60, None]]
    assert capturable_depth(ladder, 0.61, band_cents=5.0) == 200.0


def test_capturable_depth_tick_tolerant_boundary_inclusive():
    # band edge exactly at 0.56 with a level at 0.56 should be included (<=, tick-tolerant).
    ladder = [[0.56, 10.0]]
    assert capturable_depth(ladder, 0.61, band_cents=5.0) == 10.0


def test_capturable_depth_excludes_just_outside_band():
    ladder = [[0.55, 10.0]]  # 6c away, outside a 5c band by more than half a tick
    assert capturable_depth(ladder, 0.61, band_cents=5.0) == 0.0


# ─── total_ladder_depth ─────────────────────────────────────────────────────

def test_total_ladder_depth_sums_every_level():
    ladder = [[0.61, 200.0], [0.10, 4000.0], [0.06, 4000.0]]
    assert total_ladder_depth(ladder) == 8200.0


def test_total_ladder_depth_empty_is_zero():
    assert total_ladder_depth(None) == 0.0
    assert total_ladder_depth([]) == 0.0


# ─── lottery_tail_fraction (the L67 KBO-anatomy regression) ────────────────

def test_lottery_tail_fraction_reproduces_l67_kbo_shape():
    # L67: top-of-book 10 contracts at the 0.61 best bid, 4,000 contracts parked at 0.06
    # (deep-OTM lottery tail) -> tail should read close to the reported 98.83%-in-spirit split.
    ladder = [[0.61, 10.0], [0.06, 4000.0]]
    frac = lottery_tail_fraction(ladder, 0.61, band_cents=5.0)
    assert frac == pytest.approx(4000.0 / 4010.0)


def test_lottery_tail_fraction_all_capturable_is_zero():
    ladder = [[0.61, 200.0], [0.60, 50.0]]
    assert lottery_tail_fraction(ladder, 0.61, band_cents=5.0) == 0.0


def test_lottery_tail_fraction_empty_ladder_is_none_not_a_divide_by_zero():
    assert lottery_tail_fraction(None, 0.61) is None
    assert lottery_tail_fraction([], 0.61) is None


# ─── whole_contracts_available (L47: THE sanctioned ladder-size int coercion) ──

def test_whole_contracts_available_floors_a_fractional_size():
    # L47's real observed shape: a KXWCGAME best level of 91,316.82 contracts.
    assert whole_contracts_available(91316.82) == 91316
    assert whole_contracts_available(10.0) == 10
    assert whole_contracts_available(10.99) == 10


def test_whole_contracts_available_sub_one_level_is_zero_not_one():
    # 5,832 real-tape levels sit strictly between 0 and 1. You cannot lift a fraction of a
    # contract, so they contribute ZERO liftable depth — never a round-half-up to 1.
    assert whole_contracts_available(0.5) == 0
    assert whole_contracts_available(0.99) == 0
    assert whole_contracts_available(1e-9) == 0


def test_whole_contracts_available_is_a_floor_never_a_round_or_ceil():
    for v in (1.5, 2.5, 3.999999, 7.5):
        assert whole_contracts_available(v) == int(v)          # == floor for v >= 0
        assert whole_contracts_available(v) <= v               # never manufactures depth


def test_whole_contracts_available_matches_bare_int_for_every_nonnegative_size():
    # The adoption contract: swapping `int(size)` for this helper changes NO paper P&L,
    # because the two agree on every finite size >= 0 (which is every size the tape carries).
    for v in (0.0, 0.01, 0.5, 1.0, 1.000001, 9.99, 100.0, 91316.82, 13209380.2):
        assert whole_contracts_available(v) == int(v)


def test_whole_contracts_available_defensive_on_garbage():
    for bad in (None, "", "abc", float("nan"), float("inf"), float("-inf"), -1.0, -0.5, [],
                object()):
        assert whole_contracts_available(bad) == 0


def test_whole_contracts_available_accepts_numeric_strings_and_ints():
    assert whole_contracts_available("12.7") == 12
    assert whole_contracts_available(12) == 12
    assert whole_contracts_available(True) == 1


def test_whole_contracts_available_returns_an_int_not_a_float():
    v = whole_contracts_available(3.7)
    assert isinstance(v, int) and not isinstance(v, float)


def test_float_helpers_do_not_int_coerce_fractional_sizes():
    # The other half of L47: everything that answers "how much is resting" stays FLOAT.
    ladder = [[0.61, 0.5], [0.60, 91316.82]]
    assert total_ladder_depth(ladder) == pytest.approx(91317.32)
    assert capturable_depth(ladder, 0.61, band_cents=5.0) == pytest.approx(91317.32)
