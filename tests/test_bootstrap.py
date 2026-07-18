"""core/bootstrap.py — shared block-bootstrap + verdict-gate helpers (L6/L27/L28/L32)."""
from __future__ import annotations

import pytest

from core.bootstrap import (
    block_bootstrap,
    bootstrap_verdict_admissible,
    bracket_by_movement,
    catastrophic_leg_drop_stress_check,
    clears_tick_magnitude,
    collapse_duration_gated_runs,
    decompose_edge_by_leg_volume,
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


# ─── collapse_duration_gated_runs (L76) ─────────────────────────────────────

def test_collapse_duration_gated_runs_burst_fails_duration_gate_despite_count():
    # W-D's own shape: 2 consecutive hits but 0s wall-clock (a repricing burst) — a
    # naive MIN_SNAPS>=2 count gate would call this executable; the duration gate must not.
    is_hit = [True, True, False]
    seconds = [0.0, 0.0, 5.0]
    runs = collapse_duration_gated_runs(is_hit, seconds, min_duration_seconds=1.0)
    assert len(runs) == 1
    assert runs[0]["n_snaps"] == 2
    assert runs[0]["seconds"] == 0.0
    assert runs[0]["executable"] is False


def test_collapse_duration_gated_runs_sustained_run_clears_duration_gate():
    is_hit = [True, True, True, False]
    seconds = [30.0, 30.0, 30.0, 0.0]
    runs = collapse_duration_gated_runs(is_hit, seconds, min_duration_seconds=60.0)
    assert runs[0]["seconds"] == 90.0
    assert runs[0]["executable"] is True


def test_collapse_duration_gated_runs_depth_gate_applies_alongside_duration():
    is_hit = [True, True]
    seconds = [60.0, 60.0]
    depths = [500.0, 50.0]
    runs = collapse_duration_gated_runs(
        is_hit, seconds, depths, min_duration_seconds=60.0, min_depth=100.0
    )
    assert runs[0]["min_depth"] == 50.0
    assert runs[0]["executable"] is False  # duration clears, depth does not


def test_collapse_duration_gated_runs_no_depths_arg_skips_depth_gate():
    is_hit = [True, True]
    seconds = [60.0, 60.0]
    runs = collapse_duration_gated_runs(is_hit, seconds, min_duration_seconds=60.0)
    assert runs[0]["min_depth"] is None
    assert runs[0]["executable"] is True


def test_collapse_duration_gated_runs_multiple_maximal_runs():
    is_hit = [True, False, True, True, False]
    seconds = [10.0, 0.0, 10.0, 10.0, 0.0]
    runs = collapse_duration_gated_runs(is_hit, seconds, min_duration_seconds=15.0)
    assert len(runs) == 2
    assert (runs[0]["start_index"], runs[0]["end_index"]) == (0, 0)
    assert (runs[1]["start_index"], runs[1]["end_index"]) == (2, 3)
    assert runs[0]["executable"] is False
    assert runs[1]["executable"] is True


def test_collapse_duration_gated_runs_trailing_run_included():
    is_hit = [False, True, True]
    seconds = [0.0, 10.0, 10.0]
    runs = collapse_duration_gated_runs(is_hit, seconds, min_duration_seconds=15.0)
    assert len(runs) == 1
    assert runs[0]["seconds"] == 20.0


def test_collapse_duration_gated_runs_no_hits_is_empty_not_a_crash():
    runs = collapse_duration_gated_runs([False, False], [1.0, 1.0], min_duration_seconds=1.0)
    assert runs == []


def test_collapse_duration_gated_runs_length_mismatch_raises():
    with pytest.raises(ValueError):
        collapse_duration_gated_runs([True, False], [1.0], min_duration_seconds=1.0)


def test_collapse_duration_gated_runs_depths_length_mismatch_raises():
    with pytest.raises(ValueError):
        collapse_duration_gated_runs(
            [True, True], [1.0, 1.0], [5.0], min_duration_seconds=1.0
        )


# ─── decompose_edge_by_leg_volume (L39) ─────────────────────────────────────

def test_decompose_edge_by_leg_volume_the_s14_shape_thin_legs_dominate():
    # S14's own headline: +$0.0925 mean, 78% (+$0.072 of +$0.093) from sub-100-volume
    # legs. Approximate that shape: a few thick legs carry a small slice of the edge, many
    # thin legs (volume < 100) carry most of it.
    leg_pnls = [0.010, 0.011, 0.072]
    leg_volumes = [40, 60, 500]  # first two thin, third thick
    report = decompose_edge_by_leg_volume(leg_pnls, leg_volumes)
    assert report["total"] == pytest.approx(0.093)
    assert report["thin_total"] == pytest.approx(0.021)
    assert report["thin_fraction"] == pytest.approx(0.021 / 0.093)
    assert report["n_legs"] == 3
    assert report["n_thin_legs"] == 2


def test_decompose_edge_by_leg_volume_all_thick_legs_zero_thin_fraction():
    report = decompose_edge_by_leg_volume([0.05, 0.05], [500, 600])
    assert report["thin_total"] == 0.0
    assert report["thin_fraction"] == 0.0
    assert report["n_thin_legs"] == 0


def test_decompose_edge_by_leg_volume_all_thin_legs_full_thin_fraction():
    report = decompose_edge_by_leg_volume([0.02, 0.03], [10, 20])
    assert report["thin_fraction"] == pytest.approx(1.0)
    assert report["n_thin_legs"] == 2


def test_decompose_edge_by_leg_volume_threshold_is_tunable():
    report = decompose_edge_by_leg_volume([0.02, 0.03], [10, 20], thin_volume_threshold=15)
    assert report["n_thin_legs"] == 1
    assert report["thin_total"] == pytest.approx(0.02)


def test_decompose_edge_by_leg_volume_zero_total_is_honest_none_not_a_crash():
    report = decompose_edge_by_leg_volume([0.05, -0.05], [10, 500])
    assert report["total"] == 0.0
    assert report["thin_fraction"] is None


def test_decompose_edge_by_leg_volume_empty_input_is_honest_not_a_crash():
    report = decompose_edge_by_leg_volume([], [])
    assert report["total"] == 0
    assert report["thin_fraction"] is None
    assert report["n_legs"] == 0
    assert report["n_thin_legs"] == 0


def test_decompose_edge_by_leg_volume_length_mismatch_raises():
    with pytest.raises(ValueError):
        decompose_edge_by_leg_volume([0.01, 0.02], [10])


# ─── catastrophic_leg_drop_stress_check (L86) ───────────────────────────────

def test_catastrophic_leg_drop_stress_check_the_s14_shape_sign_preserved():
    # S14's Q34 verdict: 146 measurable event-hours mean -0.0453; crediting the 290
    # winner-leg-unmeasurable event-hours with payout=0 (the most generous counterfactual)
    # still moved the mean to -0.0152 — same sign. Approximate the shape at small n.
    retained = [-0.0453] * 146
    report = catastrophic_leg_drop_stress_check(retained, 290, generous_replacement_value=0.0)
    assert report["reported_mean"] == pytest.approx(-0.0453)
    assert report["stress_mean"] == pytest.approx(-0.0152, abs=1e-4)
    assert report["n_retained"] == 146
    assert report["n_dropped"] == 290
    assert report["sign_preserved"] is True


def test_catastrophic_leg_drop_stress_check_sign_flip_is_a_red_flag():
    # A reported negative mean that flips positive once the dropped units are credited
    # generously means the "drop" was doing the work, not the edge — sign_preserved must
    # come back False, not silently pass.
    retained = [-0.01, -0.01]
    report = catastrophic_leg_drop_stress_check(retained, 8, generous_replacement_value=1.0)
    assert report["reported_mean"] < 0
    assert report["stress_mean"] > 0
    assert report["sign_preserved"] is False


def test_catastrophic_leg_drop_stress_check_zero_dropped_is_a_noop():
    retained = [0.02, -0.01, 0.03]
    report = catastrophic_leg_drop_stress_check(retained, 0)
    assert report["stress_mean"] == pytest.approx(report["reported_mean"])
    assert report["sign_preserved"] is True


def test_catastrophic_leg_drop_stress_check_both_exact_zero_preserves():
    report = catastrophic_leg_drop_stress_check([0.0, 0.0], 3, generous_replacement_value=0.0)
    assert report["reported_mean"] == 0.0
    assert report["stress_mean"] == 0.0
    assert report["sign_preserved"] is True


def test_catastrophic_leg_drop_stress_check_zero_vs_nonzero_does_not_preserve():
    # reported_mean is exactly 0 (retained legs cancel) but crediting the dropped units at
    # a nonzero value moves the stress mean off zero — signs differ, must not silently pass.
    report = catastrophic_leg_drop_stress_check([0.05, -0.05], 2, generous_replacement_value=0.02)
    assert report["reported_mean"] == 0.0
    assert report["stress_mean"] != 0.0
    assert report["sign_preserved"] is False


def test_catastrophic_leg_drop_stress_check_empty_input_is_honest_none_not_a_crash():
    report = catastrophic_leg_drop_stress_check([], 0)
    assert report["reported_mean"] is None
    assert report["stress_mean"] is None
    assert report["sign_preserved"] is None
    assert report["n_retained"] == 0
    assert report["n_dropped"] == 0


def test_catastrophic_leg_drop_stress_check_all_retained_dropped_none_still_defined():
    # n_dropped=0 with a nonempty retained list must not return an undefined stress_mean.
    report = catastrophic_leg_drop_stress_check([0.01], 0)
    assert report["stress_mean"] == pytest.approx(0.01)


def test_catastrophic_leg_drop_stress_check_negative_n_dropped_raises():
    with pytest.raises(ValueError):
        catastrophic_leg_drop_stress_check([0.01], -1)


# ─── bootstrap_verdict_admissible (L41) ─────────────────────────────────────

def test_admissible_rejects_all_winning_clusters_the_s20_survivor_shape():
    # S20's sole FDR "survivor": 8 clusters, every one resolved positive -> the
    # bootstrap can never straddle zero, p is mechanically 0. Inadmissible on BOTH gates.
    units = {f"m{i}": [0.05, 0.10] for i in range(8)}
    report = bootstrap_verdict_admissible(units)
    assert report["admissible"] is False
    assert set(report["reasons"]) == {"below_min_units", "no_opposing_unit"}
    assert report["n_opposing_units"] == 0


def test_admissible_rejects_no_opposing_unit_even_above_min_units():
    units = {f"m{i}": [0.02] for i in range(15)}
    report = bootstrap_verdict_admissible(units)
    assert report["admissible"] is False
    assert report["reasons"] == ["no_opposing_unit"]


def test_admissible_rejects_below_min_units_even_with_losing_cluster():
    # S19's shape: a losing observation exists but the filled population is 2 units.
    units = {"h1": [0.35, 0.40], "h2": [-0.10]}
    report = bootstrap_verdict_admissible(units)
    assert report["admissible"] is False
    assert report["reasons"] == ["below_min_units"]
    assert report["n_opposing_units"] == 1


def test_admissible_accepts_healthy_mixed_population():
    units = {f"g{i}": [0.03, -0.01, 0.02] for i in range(9)}
    units["g_loser"] = [-0.05, -0.02]
    report = bootstrap_verdict_admissible(units)
    assert report["admissible"] is True
    assert report["reasons"] == []
    assert report["n_units"] == 10
    assert report["n_opposing_units"] == 1


def test_admissible_negative_claim_requires_a_winning_cluster():
    # Mirror direction: a strictly-negative population is just as degenerate.
    units = {f"m{i}": [-0.04] for i in range(12)}
    assert bootstrap_verdict_admissible(units)["admissible"] is False
    units["winner"] = [0.06]
    report = bootstrap_verdict_admissible(units)
    assert report["admissible"] is True
    assert report["n_opposing_units"] == 1


def test_admissible_zero_pooled_mean_requires_both_sides():
    all_zero = {f"m{i}": [0.0] for i in range(12)}
    assert bootstrap_verdict_admissible(all_zero)["reasons"] == ["no_opposing_unit"]
    mixed = {f"p{i}": [0.01] for i in range(6)}
    mixed.update({f"n{i}": [-0.01] for i in range(6)})
    assert bootstrap_verdict_admissible(mixed)["admissible"] is True


def test_admissible_empty_and_empty_valued_inputs_are_honest_not_crashing():
    assert bootstrap_verdict_admissible({})["reasons"] == ["empty"]
    assert bootstrap_verdict_admissible({"a": [], "b": []})["reasons"] == ["empty"]


def test_admissible_min_units_is_tunable_but_defaults_to_ten():
    units = {"a": [0.02], "b": [-0.01]}
    assert bootstrap_verdict_admissible(units)["admissible"] is False
    assert bootstrap_verdict_admissible(units, min_units=2)["admissible"] is True


def test_admissible_zero_mean_unit_is_not_a_losing_cluster():
    # Docstring promise: "strictly opposite" — a unit at exactly 0.0 must not count as
    # opposing under a positive pooled mean (a refactor to `m <= 0` must fail here).
    units = {f"m{i}": [0.02] for i in range(11)}
    units["flat"] = [0.0]
    report = bootstrap_verdict_admissible(units)
    assert report["admissible"] is False
    assert report["reasons"] == ["no_opposing_unit"]
    assert report["n_opposing_units"] == 0
