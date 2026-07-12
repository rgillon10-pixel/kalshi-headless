"""core/bootstrap.py — shared block-bootstrap + verdict-gate helpers (L6/L27/L28/L32)."""
from __future__ import annotations

import pytest

from core.bootstrap import (
    block_bootstrap,
    bracket_by_movement,
    clears_tick_magnitude,
    floor_pinned_fraction,
)


# ─── block_bootstrap ────────────────────────────────────────────────────────

def test_block_bootstrap_empty_input_is_honest_not_crashing():
    report = block_bootstrap({})
    assert report["n_units"] == 0
    assert report["mean"] is None
    assert report["ci95"] == [None, None]


def test_block_bootstrap_all_units_empty_values_is_honest():
    report = block_bootstrap({"h1": [], "h2": []})
    assert report["n_units"] == 2
    assert report["n_obs"] == 0
    assert report["mean"] is None
    assert report["ci95"] == [None, None]


def test_block_bootstrap_grand_mean_matches_pooled_mean():
    units = {"h1": [1.0, 2.0], "h2": [3.0], "h3": [4.0, 4.0, 4.0]}
    report = block_bootstrap(units, n_boot=500, seed=1)
    all_vals = [v for vs in units.values() for v in vs]
    assert report["mean"] == sum(all_vals) / len(all_vals)
    assert report["n_units"] == 3
    assert report["n_obs"] == 6


def test_block_bootstrap_deterministic_given_seed():
    units = {"a": [0.01, 0.02, -0.01], "b": [0.03], "c": [-0.02, 0.05]}
    r1 = block_bootstrap(units, n_boot=2000, seed=42)
    r2 = block_bootstrap(units, n_boot=2000, seed=42)
    assert r1["ci95"] == r2["ci95"]


def test_block_bootstrap_ci_widens_with_fewer_units():
    # A single-unit "population" can only ever resample itself -> zero-width CI.
    one_unit = block_bootstrap({"only": [1.0, -1.0, 2.0]}, n_boot=1000, seed=7)
    lo, hi = one_unit["ci95"]
    assert lo == hi == one_unit["mean"]


def test_block_bootstrap_strictly_positive_population_has_positive_ci():
    units = {f"u{i}": [0.05, 0.06, 0.04] for i in range(20)}
    report = block_bootstrap(units, n_boot=2000, seed=3)
    lo, hi = report["ci95"]
    assert lo > 0
    assert hi > 0


def test_block_bootstrap_reports_n_boot_and_seed():
    report = block_bootstrap({"a": [1.0]}, n_boot=123, seed=9)
    assert report["n_boot"] == 123
    assert report["seed"] == 9


# ─── clears_tick_magnitude (L27) ────────────────────────────────────────────

def test_clears_tick_magnitude_true_for_a_real_edge():
    # S6's proven-alive shape: mean/CI comfortably above a cent.
    assert clears_tick_magnitude([0.05, 0.09], tick=0.01, min_ticks=1.0) is True


def test_clears_tick_magnitude_false_for_sign_only_positive_ci():
    # S10's exact near-miss: CI lower bound +0.000000, three orders below the tick.
    assert clears_tick_magnitude([0.000000, 0.000024], tick=0.01, min_ticks=1.0) is False


def test_clears_tick_magnitude_false_for_negative_lower_bound():
    assert clears_tick_magnitude([-0.001, 0.02], tick=0.01) is False


def test_clears_tick_magnitude_false_for_empty_ci():
    assert clears_tick_magnitude([None, None]) is False
    assert clears_tick_magnitude([]) is False


def test_clears_tick_magnitude_respects_custom_min_ticks():
    ci = [0.015, 0.02]  # 1.5 ticks -- clears a 1-tick bar, not a 2-tick bar
    assert clears_tick_magnitude(ci, tick=0.01, min_ticks=1.0) is True
    assert clears_tick_magnitude(ci, tick=0.01, min_ticks=2.0) is False


# ─── floor_pinned_fraction (L28) ────────────────────────────────────────────

def test_floor_pinned_fraction_all_pinned():
    assert floor_pinned_fraction([0.01, 0.01, 0.01], floor=0.01) == 1.0


def test_floor_pinned_fraction_none_pinned():
    assert floor_pinned_fraction([0.5, 0.6, 0.7], floor=0.01) == 0.0


def test_floor_pinned_fraction_partial():
    # S10's own shape: the overwhelming majority already at the floor.
    values = [0.01] * 999 + [0.5]
    assert floor_pinned_fraction(values, floor=0.01) == 999 / 1000


def test_floor_pinned_fraction_empty_is_zero_not_a_crash():
    assert floor_pinned_fraction([], floor=0.01) == 0.0


def test_floor_pinned_fraction_respects_tolerance():
    # Floating-point-close-but-not-exact should still count as pinned.
    assert floor_pinned_fraction([0.010000001], floor=0.01, tol=1e-6) == 1.0
    assert floor_pinned_fraction([0.0101], floor=0.01, tol=1e-6) == 0.0


# ─── bracket_by_movement (L32) ──────────────────────────────────────────────

def test_bracket_by_movement_all_frozen():
    report = bracket_by_movement([True, True, True], [0.05, 0.05, 0.05])
    assert report["frac_frozen"] == 1.0
    assert report["frozen_inclusive"] == [0.05, 0.05, 0.05]
    assert report["movement_conditioned"] == []


def test_bracket_by_movement_none_frozen():
    report = bracket_by_movement([False, False], [0.01, -0.02])
    assert report["frac_frozen"] == 0.0
    assert report["movement_conditioned"] == [0.01, -0.02]


def test_bracket_by_movement_partial_matches_s6_shape():
    # S6's own precheck shape: the large majority of consecutive pairs frozen.
    flags = [True] * 697 + [False] * 303
    values = [0.01] * 697 + [-0.02] * 303
    report = bracket_by_movement(flags, values)
    assert report["frac_frozen"] == pytest.approx(0.697)
    assert report["frozen_inclusive"] == values
    assert report["movement_conditioned"] == [-0.02] * 303


def test_bracket_by_movement_movement_conditioned_excludes_only_frozen_entries():
    flags = [True, False, True, False]
    values = [1.0, 2.0, 3.0, 4.0]
    report = bracket_by_movement(flags, values)
    assert report["movement_conditioned"] == [2.0, 4.0]


def test_bracket_by_movement_empty_is_honest_not_a_crash():
    report = bracket_by_movement([], [])
    assert report["n"] == 0
    assert report["frac_frozen"] == 0.0
    assert report["frozen_inclusive"] == []
    assert report["movement_conditioned"] == []


def test_bracket_by_movement_length_mismatch_raises():
    with pytest.raises(ValueError):
        bracket_by_movement([True, False], [1.0])
