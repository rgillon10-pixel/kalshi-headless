"""core/depth.py — ladder-depth helpers (L67 two-sided-depth-illusion lesson)."""
from __future__ import annotations

import pytest

from core.depth import capturable_depth, lottery_tail_fraction, total_ladder_depth


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
