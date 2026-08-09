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
    disagreement_subset_calibration,
    entry_instant_concentration,
    floor_pinned_fraction,
    headline_fill_rate,
    hit_magnitude_decomposition,
    kish_effective_n,
    sign_bounded_objective,
    turnover_rule_saturation,
    TURNOVER_SATURATION_RATIO,
    TURNOVER_SATURATION_FILL_RATE,
    MIN_SNAPSHOTS_FOR_SATURATION,
    PRIMARY_FILL_RULE,
    DIAGNOSTIC_FILL_RULE,
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


# ─── kish_effective_n (L322) ────────────────────────────────────────────────

def test_kish_effective_n_empty_is_honest_undefined_not_zero():
    r = kish_effective_n([])
    assert r["n_units"] == 0
    assert r["n_obs"] == 0
    assert r["kish_n"] is None
    assert r["design_effect"] is None


def test_kish_effective_n_all_zero_size_units_is_also_undefined():
    r = kish_effective_n([0, 0, 0])
    assert r["n_units"] == 3
    assert r["n_obs"] == 0
    assert r["kish_n"] is None
    assert r["design_effect"] is None


def test_kish_effective_n_equal_sized_units_equals_the_raw_count():
    """`design_effect == 1.0` exactly when every block is the same size — Kish's formula
    degenerates to the naive unit count with no raggedness to discount."""
    r = kish_effective_n([5, 5, 5, 5])
    assert r["n_units"] == 4
    assert r["n_obs"] == 20
    assert r["kish_n"] == pytest.approx(4.0)
    assert r["design_effect"] == pytest.approx(1.0)


def test_kish_effective_n_single_unit_is_itself():
    r = kish_effective_n([7])
    assert r["kish_n"] == pytest.approx(1.0)
    assert r["design_effect"] == pytest.approx(1.0)


def test_kish_effective_n_ragged_sizes_fall_strictly_below_raw_count():
    """A single dominant block plus many singletons is the shape L322 flags: the raw
    `n_units` overstates independence, so `kish_n` must land strictly below it."""
    r = kish_effective_n([50, 1, 1, 1, 1, 1, 1, 1, 1, 1])
    assert r["n_units"] == 10
    assert r["kish_n"] < 10
    assert r["design_effect"] > 1.0


def test_kish_effective_n_never_exceeds_raw_unit_count():
    for sizes in ([1], [1, 1], [3, 1, 1], [23, 17, 12, 12, 11, 11, 8, 5, 4, 4, 3, 2, 2, 2,
                                            2, 1, 1, 1, 1, 1, 1, 1, 1, 1]):
        r = kish_effective_n(sizes)
        assert r["kish_n"] <= r["n_units"] + 1e-9


def test_kish_effective_n_negative_size_raises():
    with pytest.raises(ValueError):
        kish_effective_n([3, -1, 2])


def test_kish_effective_n_does_not_mutate_its_input():
    sizes = [4, 2, 1]
    kish_effective_n(sizes)
    assert sizes == [4, 2, 1]


def test_acceptance_q54_s79_real_report_reproduces_l322s_effective_n():
    """Real-tape acceptance test (L322): Q54/S79's own committed bootstrap pooled 133
    entries into 24 game-units (`n_units=24` in `reports/q54_s79_flow_continuation.json`'s
    `bootstrap` block) — the exact ragged-block population that motivated this lesson.
    Reproducing it from the report's own `population.entries_per_unit` sizes pins the
    ~11.6 Kish n (1.16x the L41 floor of 10, not the 2.4x the raw `n_units` implies)
    against the real committed numbers rather than a synthetic fixture alone."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "reports" / "q54_s79_flow_continuation.json"
    if not p.is_file():
        pytest.skip("reports/q54_s79_flow_continuation.json not present in this checkout")
    report = json.loads(p.read_text(encoding="utf-8"))
    entries_per_unit = report["population"]["entries_per_unit"]
    bootstrap = report["bootstrap"]

    r = kish_effective_n(list(entries_per_unit.values()))

    assert r["n_units"] == bootstrap["n_units"] == 24
    assert r["n_obs"] == bootstrap["n_obs"] == 133
    assert r["kish_n"] == pytest.approx(11.629848783694937)
    # the headroom over the L41 floor the raw n_units implies (2.4x) vs. what the
    # ragged block sizes actually deliver (~1.16x) — the gap L322 exists to surface.
    assert (bootstrap["n_units"] / 10) == pytest.approx(2.4)
    assert (r["kish_n"] / 10) == pytest.approx(1.1629848783694937)


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


# ─── disagreement_subset_calibration (L51) ──────────────────────────────────

def test_disagreement_complementarity_identity_holds_on_strict_subset():
    # L51 headline: on a strict two-way disagreement subset the two accuracies are
    # mechanically complementary — signal_accuracy == 1 - mid_accuracy, exactly.
    hit_mid = [True, True, True, False, False]
    hit_signal = [not m for m in hit_mid]
    report = disagreement_subset_calibration(hit_signal, hit_mid)
    assert report["is_strict_two_way"] is True
    assert report["signal_accuracy"] == pytest.approx(1 - report["mid_accuracy"])
    assert report["mid_accuracy"] + report["signal_accuracy"] == pytest.approx(1.0)


def test_disagreement_rows_are_pointwise_negations_on_strict_subset():
    # (b) the per-row invariant hit_signal[i] == (not hit_mid[i]) that makes the
    # complementarity mechanical, not statistical.
    hit_mid = [True, False, True, False, True, True]
    hit_signal = [not m for m in hit_mid]
    report = disagreement_subset_calibration(hit_signal, hit_mid)
    assert report["violating_indices"] == []
    for s, m in zip(hit_signal, hit_mid):
        assert bool(s) == (not bool(m))


def test_disagreement_regression_reproduces_q26_s22_numbers():
    # (c) Q26/S22's cited disagreement-subset numbers: mid 72.1% vs signal 27.9%.
    # Construct a strict two-way subset with 721 mid-wins and 279 signal-wins.
    hit_mid = [True] * 721 + [False] * 279
    hit_signal = [not m for m in hit_mid]
    report = disagreement_subset_calibration(hit_signal, hit_mid)
    assert report["mid_accuracy"] == pytest.approx(0.721)
    assert report["signal_accuracy"] == pytest.approx(0.279)
    # The illusion L51 warns against: treating 0.721 and 0.279 as two independent
    # measurements. They are one number — they sum to exactly 1.0 by construction.
    assert report["mid_accuracy"] + report["signal_accuracy"] == pytest.approx(1.0)
    assert report["is_strict_two_way"] is True


def test_disagreement_violating_indices_catches_non_strict_row():
    # (d) a row where BOTH are True cannot come from a strict directional two-way
    # partition — it proves the "disagreement subset" leaked a non-two-way / non-
    # directional observation. Report it, do not raise.
    hit_mid = [True, False, True]
    hit_signal = [False, True, True]  # index 2 violates (both True)
    report = disagreement_subset_calibration(hit_signal, hit_mid)
    assert report["is_strict_two_way"] is False
    assert report["violating_indices"] == [2]
    # accuracies are still reported honestly over all rows
    assert report["n"] == 3


def test_disagreement_empty_input_is_honest_not_crashing():
    # (e) empty input → honest empty report, matching the sibling helpers' discipline.
    report = disagreement_subset_calibration([], [])
    assert report == {"n": 0, "mid_accuracy": None, "signal_accuracy": None,
                      "is_strict_two_way": True, "violating_indices": []}


def test_disagreement_length_mismatch_raises():
    # (f) a length mismatch is a caller bug, not silent misalignment.
    with pytest.raises(ValueError):
        disagreement_subset_calibration([True, False], [True])


# ─── hit_magnitude_decomposition (L236 granularity rule) ────────────────────

def test_hit_magnitude_empty_input_is_honest_not_crashing():
    rep = hit_magnitude_decomposition([])
    assert rep["n"] == 0 and rep["n_unmeasurable"] == 0
    assert rep["n_residue"] == 0 and rep["n_sub_tick"] == 0 and rep["n_clears_tick"] == 0
    # shares are None, never 0.0 — a 0.0 share would read as a MEASURED absence of artifacts
    assert rep["residue_share"] is None and rep["sub_tick_share"] is None
    assert rep["max"] is None


def test_hit_magnitude_none_input_is_honest():
    assert hit_magnitude_decomposition(None)["n"] == 0


def test_hit_magnitude_all_none_entries_are_unmeasurable_not_zero():
    # L86: an unmeasurable observation is DROPPED and reported, never booked as a zero
    # (booking None as 0.0 would silently inflate the residue count).
    rep = hit_magnitude_decomposition([None, None, None])
    assert rep["n"] == 0 and rep["n_unmeasurable"] == 3
    assert rep["n_residue"] == 0
    assert rep["residue_share"] is None


def test_hit_magnitude_nan_and_inf_are_unmeasurable():
    rep = hit_magnitude_decomposition([float("nan"), float("inf"), float("-inf"), 0.02])
    assert rep["n"] == 1 and rep["n_unmeasurable"] == 3
    assert rep["n_clears_tick"] == 1
    assert rep["max"] == 0.02


def test_hit_magnitude_shares_exclude_unmeasurable_from_the_denominator():
    rep = hit_magnitude_decomposition([1e-17, 0.005, None])
    assert rep["n"] == 2 and rep["n_unmeasurable"] == 1
    assert rep["residue_share"] == pytest.approx(0.5)   # 1/2, NOT 1/3
    assert rep["sub_tick_share"] == pytest.approx(1.0)


def test_hit_magnitude_tick_boundary_is_inclusive_at_exactly_one_tick():
    rep = hit_magnitude_decomposition([0.01, 0.00999])
    assert rep["n_clears_tick"] == 1
    assert rep["n_sub_tick"] == 1


def test_hit_magnitude_residue_boundary():
    rep = hit_magnitude_decomposition([1e-10, 1e-9, 1e-8], residue_floor=1e-9)
    # strict `< residue_floor`: only 1e-10 is residue
    assert rep["n_residue"] == 1
    assert rep["n_sub_tick"] == 3  # residue is trivially sub-tick, and is INCLUDED


def test_hit_magnitude_residue_is_included_in_sub_tick_and_the_difference_is_the_real_tail():
    rep = hit_magnitude_decomposition([1e-17, 1e-17, 0.003, 0.02])
    assert rep["n_residue"] == 2
    assert rep["n_sub_tick"] == 3
    # the genuinely-nonzero-but-unfillable population is the difference
    assert rep["n_sub_tick"] - rep["n_residue"] == 1
    assert rep["n_clears_tick"] == 1


def test_hit_magnitude_negative_residue_counts_by_absolute_value():
    # a residue has a SIGN and no economic content in either direction (L236)
    rep = hit_magnitude_decomposition([-1e-17, 1e-17])
    assert rep["n_residue"] == 2


def test_hit_magnitude_echoes_its_own_thresholds_for_provenance():
    rep = hit_magnitude_decomposition([0.5], tick=0.02, residue_floor=1e-6)
    assert rep["tick"] == 0.02 and rep["residue_floor"] == 1e-6


def test_hit_magnitude_bool_entries_are_unmeasurable_not_silently_ones():
    # a bool sneaking into a price list must not become 1.0/0.0
    rep = hit_magnitude_decomposition([True, False, 0.02])
    assert rep["n"] == 1 and rep["n_unmeasurable"] == 2


def test_l236_per_observation_and_per_group_max_views_disagree():
    """THE L236 COUNTEREXAMPLE, with the real floats from S17's 2026-07-29 FOMC `free`
    bracket. Two groups (episodes): one is all-residue; the other has a real +$0.003 max but
    ALSO contains a residue capture. The per-group-max view sees ONE residue group / ONE
    residue capture; the honest per-observation view sees TWO. A group is scored by its best
    member, so the max view always understates the artifact share."""
    residue = 1.734723475976807e-17
    groups = [[residue], [0.003, residue]]
    per_observation = hit_magnitude_decomposition([v for g in groups for v in g])
    per_group_max = hit_magnitude_decomposition([max(g) for g in groups])
    assert per_observation["n_residue"] == 2
    assert per_group_max["n_residue"] == 1
    assert per_observation["n_residue"] > per_group_max["n_residue"]


def test_l236_the_three_fomc_residue_subtractions_are_the_SAME_float():
    """NUMERIC CORRECTION (2026-07-30) pinned so it cannot drift back.
    `findings/2026-07-29-s17-burst-fomc-q19.md` §4d and L236's own text asserted the three
    residue episodes carried DIFFERENT floats (~3.955e-17 and ~2.776e-17 for the 26SEP-H25
    pair). In IEEE-754 double all three subtractions evaluate to EXACTLY the same value,
    5·2⁻⁵⁸ — so the round-2 claim the verifier "corrected" was right about the shared float.
    The residue-per-subtraction PRINCIPLE (L236) stands; this specific trio just happens to
    coincide, and the only way to know is to evaluate it."""
    shared = 1.734723475976807e-17
    assert shared == 5 * 2.0 ** -58
    assert (0.26 - 0.24 - 0.02) == shared      # 26JUL-H25
    assert (0.61 - 0.59 - 0.02) == shared      # 26SEP-H25
    assert (0.62 - 0.60 - 0.02) == shared      # 26SEP-H25
    rep = hit_magnitude_decomposition([0.26 - 0.24 - 0.02, 0.61 - 0.59 - 0.02,
                                       0.62 - 0.60 - 0.02])
    assert rep["n_residue"] == 3 and rep["n_clears_tick"] == 0


# ─── entry_instant_concentration (L251) ─────────────────────────────────────

def _fixture_cuts():
    import json
    from pathlib import Path
    p = Path(__file__).parent / "fixtures" / "q49_entry_instants_2026-08-01.json"
    return json.loads(p.read_text(encoding="utf-8"))["cuts"]


def test_entry_instant_concentration_empty_is_no_signal_not_clean():
    """L155/L185 discipline: "nothing measured" must never read as "nothing wrong"."""
    r = entry_instant_concentration([])
    assert r["no_signal"] is True
    assert r["n_entries"] == 0 and r["n_distinct_instants"] == 0
    assert r["concentrated"] is False and r["single_instant"] is False
    assert r["top_instant"] is None


def test_entry_instant_concentration_empty_with_unit_labels_keeps_unit_keys_numeric():
    r = entry_instant_concentration([], unit_labels=[])
    assert r["no_signal"] is True
    assert r["n_units"] == 0 and r["n_units_on_top_instant"] == 0
    assert r["unit_share_on_top_instant"] == 0.0 and r["n_unit_instant_pairs"] == 0


def test_entry_instant_concentration_unit_keys_are_none_when_no_labels_given():
    r = entry_instant_concentration(["a", "b"])
    assert r["n_units"] is None and r["n_units_on_top_instant"] is None
    assert r["unit_share_on_top_instant"] is None and r["n_unit_instant_pairs"] is None


def test_entry_instant_concentration_single_instant_is_the_q49_shape():
    r = entry_instant_concentration(["t0"] * 20, unit_labels=list("aabbccddee") * 2)
    assert r["single_instant"] is True
    assert r["n_distinct_instants"] == 1
    assert r["max_instant_share"] == 1.0
    assert r["concentrated"] is True
    # the sharp part: every bootstrap unit lives on that one instant, so the unit
    # count carries no temporal independence whatsoever.
    assert r["n_units"] == r["n_units_on_top_instant"] == 5
    assert r["unit_share_on_top_instant"] == 1.0
    assert r["n_unit_instant_pairs"] == 5


def test_entry_instant_concentration_perfectly_spread_population_is_not_flagged():
    r = entry_instant_concentration([f"t{i}" for i in range(10)])
    assert r["n_distinct_instants"] == 10
    assert r["max_instant_share"] == 0.1
    assert r["entries_per_distinct_instant"] == 1.0
    assert r["concentrated"] is False and r["single_instant"] is False


def test_entry_instant_concentration_flag_is_inclusive_at_the_threshold():
    """Exactly `flag_share` of the population on one instant DOES flag (>=, not >)."""
    r = entry_instant_concentration(["a", "a", "b", "c"])
    assert r["max_instant_share"] == 0.5
    assert r["concentrated"] is True
    assert entry_instant_concentration(["a", "a", "b", "c", "d"])["concentrated"] is False


def test_entry_instant_concentration_threshold_is_overridable_and_echoed_back():
    """The threshold used is always reported, so a downstream write-up cannot quietly
    reinterpret a flag under a different bar than the one that produced it."""
    inst = ["a", "a", "b", "c"]
    assert entry_instant_concentration(inst)["flag_share"] == 0.5
    strict = entry_instant_concentration(inst, flag_share=0.9)
    assert strict["flag_share"] == 0.9 and strict["concentrated"] is False
    loose = entry_instant_concentration(inst, flag_share=0.25)
    assert loose["flag_share"] == 0.25 and loose["concentrated"] is True


def test_entry_instant_concentration_top_instant_tie_break_is_deterministic():
    """Two instants tied on count: `str()` order decides, every run, so a report that
    quotes `top_instant` reproduces byte-identically."""
    for _ in range(5):
        r = entry_instant_concentration(["zzz", "aaa", "zzz", "aaa"])
        assert r["top_instant"] == "aaa"
        assert r["top_instant_count"] == 2


def test_entry_instant_concentration_accepts_datetimes_without_mixed_type_compare():
    from datetime import datetime, timezone
    d0 = datetime(2026, 7, 7, 1, 23, 57, tzinfo=timezone.utc)
    d1 = datetime(2026, 7, 8, 1, 23, 57, tzinfo=timezone.utc)
    r = entry_instant_concentration([d0, d0, d1], unit_labels=["u", "v", "u"])
    assert r["top_instant"] == d0 and r["top_instant_count"] == 2
    assert r["n_units"] == 2 and r["n_units_on_top_instant"] == 2
    assert r["n_unit_instant_pairs"] == 3


def test_entry_instant_concentration_length_mismatch_raises_not_misaligns():
    with pytest.raises(ValueError):
        entry_instant_concentration(["a", "b"], unit_labels=["u"])


def test_entry_instant_concentration_unit_pairs_count_distinct_support():
    """`n_unit_instant_pairs` is the population's real (unit x instant) support — the
    number a resampled block actually draws from — not the raw row count."""
    r = entry_instant_concentration(["t0", "t0", "t1"], unit_labels=["u", "u", "u"])
    assert r["n_entries"] == 3
    assert r["n_units"] == 1
    assert r["n_unit_instant_pairs"] == 2


def test_entry_instant_concentration_arithmetic_identities_hold():
    inst = ["a"] * 7 + ["b"] * 2 + ["c"]
    r = entry_instant_concentration(inst, unit_labels=list("uuuuuuuvvw"))
    assert r["max_instant_share"] == r["top_instant_count"] / r["n_entries"]
    assert r["entries_per_distinct_instant"] == r["n_entries"] / r["n_distinct_instants"]
    assert 0.0 < r["max_instant_share"] <= 1.0
    assert r["n_units_on_top_instant"] <= r["n_units"]
    assert r["n_unit_instant_pairs"] >= r["n_units"]
    assert r["n_unit_instant_pairs"] <= r["n_entries"]


def test_entry_instant_concentration_does_not_mutate_its_inputs():
    inst = ["a", "b", "a"]
    units = ["u", "v", "u"]
    entry_instant_concentration(inst, unit_labels=units)
    assert inst == ["a", "b", "a"] and units == ["u", "v", "u"]


# --- acceptance: the real Q49/S68 populations, frozen (L191/L192 discipline) ---
# Exact counts are pinned against tests/fixtures/q49_entry_instants_2026-08-01.json,
# NOT against the live tape: `tape/orderbook_depth/` grows every hour, and pinning a
# statistic to a live-GROWING population is exactly the failure L191/L192 record.

def test_acceptance_q49_primary_population_is_one_single_instant():
    """L251's motivating case, reproduced from frozen real tape. Q49/S68's PRIMARY
    `fillable_entry` population read as "20 candidates, 5 game-series, 14 games" — and
    all 20 entries share ONE capture instant, the depth tape's first full pass."""
    cuts = _fixture_cuts()
    d = cuts["fillable_entry"]
    r = entry_instant_concentration(d["entry_instants"], unit_labels=d["series_units"])
    assert r["n_entries"] == 20
    assert r["n_distinct_instants"] == 1
    assert r["max_instant_share"] == 1.0
    assert r["single_instant"] is True and r["concentrated"] is True
    assert r["top_instant"] == "2026-07-07T01:23:57.700581+00:00"
    assert r["n_units"] == 5 and r["n_units_on_top_instant"] == 5
    assert r["unit_share_on_top_instant"] == 1.0


def test_acceptance_q49_contamination_is_not_confined_to_the_primary_cut():
    """The number Q49's own finding did NOT report: the SAME tape-start instant is the
    top instant of ALL FOUR labeled cuts, and carries 54.9% of the 284-candidate
    `spread_le_10c` population. The verifier's caveat named only the primary cut."""
    cuts = _fixture_cuts()
    tape_start = "2026-07-07T01:23:57.700581+00:00"
    tops = {}
    for name, d in cuts.items():
        r = entry_instant_concentration(d["entry_instants"], unit_labels=d["series_units"])
        tops[name] = (r["top_instant"], round(r["max_instant_share"], 4), r["concentrated"])
    assert all(t[0] == tape_start for t in tops.values())
    assert tops["spread_le_10c"][1] == 0.5493 and tops["spread_le_10c"][2] is True
    assert tops["nearclose_le_24h"][1] == 1.0 and tops["nearclose_le_24h"][2] is True


def test_acceptance_the_flag_is_not_a_rubber_stamp_on_real_data():
    """Honest counterweight to the test above: Q49's widest cut (445 candidates, 18
    series) sits at 47.19% on the tape-start instant and does NOT trip the 0.5 flag.
    The descriptor reports a number; it does not label everything an artifact."""
    cuts = _fixture_cuts()
    d = cuts["unrestricted"]
    r = entry_instant_concentration(d["entry_instants"], unit_labels=d["series_units"])
    assert r["n_entries"] == 445 and r["n_distinct_instants"] == 23
    assert round(r["max_instant_share"], 4) == 0.4719
    assert r["concentrated"] is False
    assert r["n_units"] == 18 and r["n_units_on_top_instant"] == 12


def test_acceptance_live_tape_first_depth_instant_is_monotone_not_pinned():
    """The one LIVE-tree assertion, deliberately monotone (L191): a stranded-tape sweep
    may still union-append older lines into `dt=2026-07-07.jsonl`, so the day-file's
    earliest `captured_at` can only move EARLIER, never later. Asserting `<=` keeps the
    gate honest without binding it to a file that append-only collection can still touch."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "tape" / "orderbook_depth" / "dt=2026-07-07.jsonl"
    if not p.is_file():
        pytest.skip("tape/orderbook_depth/dt=2026-07-07.jsonl not present in this checkout")
    earliest = None
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ca = json.loads(line).get("captured_at")
            if ca and (earliest is None or ca < earliest):
                earliest = ca
    assert earliest is not None
    assert earliest <= "2026-07-07T01:23:57.700581+00:00"


# --------------------------------------------------------------------------- #
# L249 — sign_bounded_objective: is the bootstrap's opposing branch reachable?
# --------------------------------------------------------------------------- #

def _l249_fixture():
    import json
    from pathlib import Path
    p = (Path(__file__).resolve().parent / "fixtures"
         / "q49_pnl_units_2026-08-02.json")
    return json.loads(p.read_text(encoding="utf-8"))


def test_sign_bounded_objective_empty_is_no_signal_not_a_clean_bill():
    """Nothing measured is never reported as nothing wrong (the repo's no_signal
    discipline) — and with no admissibility dict the definitional verdict is None,
    not False."""
    r = sign_bounded_objective({})
    assert r["no_signal"] is True
    assert r["reasons"] == ["empty"]
    assert r["verdict_bearing"] is False
    assert r["one_sided_support"] is False
    assert r["support_sign"] is None
    assert r["inadmissibility_is_definitional"] is None
    assert r["n_obs"] == 0 and r["min_value"] is None and r["max_value"] is None


def test_sign_bounded_objective_all_positive_support_is_not_verdict_bearing():
    r = sign_bounded_objective({"a": [0.1, 0.2], "b": [0.3, 0.4, 0.5]})
    assert r["one_sided_support"] is True
    assert r["support_sign"] == 1
    assert r["all_zero_support"] is False
    assert r["verdict_bearing"] is False
    assert "one_sided_support" in r["reasons"]


def test_sign_bounded_objective_all_negative_support_is_symmetric():
    """The check is direction-agnostic: a gate that guarantees a LOSS is just as
    unfalsifiable as one that guarantees a win."""
    r = sign_bounded_objective({"a": [-0.1, -0.2], "b": [-0.3, -0.4, -0.5]})
    assert r["one_sided_support"] is True
    assert r["support_sign"] == -1
    assert r["verdict_bearing"] is False


def test_sign_bounded_objective_all_zero_support_is_flagged_distinctly():
    """Q49's exact shape: an object pinned to exactly 0.0 is one-sided AND degenerate,
    and `support_sign == 0` says so without pretending it is a directional claim."""
    r = sign_bounded_objective({"a": [0.0, 0.0], "b": [0.0, 0.0, 0.0, 0.0]})
    assert r["all_zero_support"] is True
    assert r["support_sign"] == 0
    assert r["one_sided_support"] is True
    assert r["verdict_bearing"] is False
    assert r["reasons"][:2] == ["one_sided_support", "all_zero_support"]


def test_sign_bounded_objective_straddling_support_is_verdict_bearing():
    r = sign_bounded_objective({"a": [0.1, -0.2], "b": [0.3, -0.4, 0.0]})
    assert r["one_sided_support"] is False
    assert r["support_sign"] is None
    assert r["verdict_bearing"] is True
    assert "one_sided_support" not in r["reasons"]


def test_sign_bounded_objective_counts_partition_the_observations():
    r = sign_bounded_objective({"a": [1.0, -1.0, 0.0], "b": [2.0]})
    assert r["n_positive"] + r["n_negative"] + r["n_zero"] == r["n_obs"] == 4
    assert (r["n_positive"], r["n_negative"], r["n_zero"]) == (2, 1, 1)
    assert r["min_value"] == -1.0 and r["max_value"] == 2.0


def test_sign_bounded_objective_tolerance_absorbs_float_noise_not_real_pnl():
    """A value that is algebraically zero but arrives as 1e-15 must not manufacture a
    two-sided support; a real sub-cent P&L of 1e-6 must still count as a sign."""
    noise = sign_bounded_objective({"a": [1e-15, -1e-15, 0.0, 0.0, 0.0]})
    assert noise["all_zero_support"] is True
    assert noise["verdict_bearing"] is False
    real = sign_bounded_objective({"a": [1e-6, -1e-6, 0.0, 0.0, 0.0]})
    assert real["n_positive"] == 1 and real["n_negative"] == 1
    assert real["verdict_bearing"] is True


def test_sign_bounded_objective_tolerance_is_overridable_and_echoed():
    vals = {"a": [1e-6, -1e-6, 0.0, 0.0, 0.0]}
    assert sign_bounded_objective(vals)["tol"] == 1e-12
    blunt = sign_bounded_objective(vals, tol=1e-3)
    assert blunt["tol"] == 1e-3
    assert blunt["all_zero_support"] is True


def test_sign_bounded_objective_small_one_sided_sample_is_flagged_weak():
    """One-sidedness on four observations is an unremarkable accident, not evidence of
    a bound — the flag says so rather than letting the reader over-read it."""
    weak = sign_bounded_objective({"a": [0.1, 0.2], "b": [0.3, 0.4]})
    assert weak["n_obs"] == 4
    assert weak["weak_sample"] is True
    assert "weak_sample" in weak["reasons"]
    strong = sign_bounded_objective({"a": [0.1, 0.2], "b": [0.3, 0.4, 0.5]})
    assert strong["weak_sample"] is False
    assert "weak_sample" not in strong["reasons"]


def test_sign_bounded_objective_min_obs_is_overridable_and_echoed():
    vals = {"a": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]}
    assert sign_bounded_objective(vals)["min_obs"] == 5
    strict = sign_bounded_objective(vals, min_obs=50)
    assert strict["min_obs"] == 50 and strict["weak_sample"] is True


def test_sign_bounded_objective_separates_adequacy_from_definitional_inadmissibility():
    """The whole point of L249. Two objects, IDENTICAL `admissible=False` headline:
    one can never disagree (definitional), the other merely lacks units (adequacy)."""
    bounded = {f"u{i}": [0.05] for i in range(5)}
    adm_b = bootstrap_verdict_admissible(bounded, min_units=10)
    r_b = sign_bounded_objective(bounded, admissibility=adm_b)
    assert adm_b["admissible"] is False
    assert "no_opposing_unit" in adm_b["reasons"]
    assert r_b["inadmissibility_is_definitional"] is True

    adequate = {"u0": [0.05, 0.05], "u1": [-0.05, -0.05], "u2": [0.02, -0.01]}
    adm_a = bootstrap_verdict_admissible(adequate, min_units=10)
    r_a = sign_bounded_objective(adequate, admissibility=adm_a)
    assert adm_a["admissible"] is False
    assert adm_a["reasons"] == ["below_min_units"]
    assert r_a["inadmissibility_is_definitional"] is False
    assert r_a["verdict_bearing"] is True


def test_sign_bounded_objective_definitional_is_false_when_the_gate_passed():
    vals = {f"u{i}": [0.05 if i % 2 else -0.05] for i in range(12)}
    adm = bootstrap_verdict_admissible(vals, min_units=10)
    assert adm["admissible"] is True
    assert sign_bounded_objective(vals, admissibility=adm)[
        "inadmissibility_is_definitional"] is False


def test_sign_bounded_objective_observation_level_straddle_only_is_distinguished():
    """Every unit MEAN positive while raw observations cross zero is the case the L41
    gate calls `no_opposing_unit` but which is NOT structurally unfalsifiable — more
    units genuinely could flip it, so it must not be tagged definitional."""
    vals = {"a": [0.10, -0.02], "b": [0.20, -0.01], "c": [0.30, -0.05]}
    r = sign_bounded_objective(vals)
    assert r["unit_means_one_sided"] is True
    assert r["one_sided_support"] is False
    assert r["observation_level_straddle_only"] is True
    assert r["verdict_bearing"] is True


def test_sign_bounded_objective_is_not_a_substitute_for_admissibility():
    """Documented limit, pinned: `verdict_bearing=True` says only that the object COULD
    have disagreed — a 2-unit population is verdict-BEARING and still inadmissible."""
    vals = {"a": [0.5], "b": [-0.5]}
    r = sign_bounded_objective(vals)
    assert r["verdict_bearing"] is True
    assert bootstrap_verdict_admissible(vals, min_units=10)["admissible"] is False


def test_sign_bounded_objective_ignores_empty_units_without_crashing():
    r = sign_bounded_objective({"a": [0.1, 0.2, 0.3, 0.4, 0.5], "empty": []})
    assert r["n_units"] == 1
    assert r["n_obs"] == 5
    assert r["no_signal"] is False


def test_sign_bounded_objective_does_not_mutate_its_input():
    vals = {"a": [0.1, -0.2], "b": [0.3]}
    before = {k: list(v) for k, v in vals.items()}
    sign_bounded_objective(vals)
    assert vals == before


# --- acceptance: the real Q49/S68 bootstrap objects, frozen (L191/L192 discipline) ---
# Both objects come from ONE run of scripts/q49_s68_bothside_maker_fillsim.py over the
# committed tape on 2026-08-02, frozen to a fixture rather than recomputed against
# `tape/orderbook_depth/`, which grows every hour.

def test_acceptance_l249_q49_both_fill_object_is_structurally_unfalsifiable():
    """L249's exhibit, reproduced. Q49/S68's PRIMARY `fillable_entry` double-fill P&L —
    the object whose `admissible=False` was reported as DEAD-by-CI — has all 11
    observations pinned to exactly $0.0000, because the entry gate (yes-spread >= two
    maker fees) plus `best_yes_ask == 1 - best_no_bid` bounds the sign by arithmetic."""
    d = _l249_fixture()["both_fill_pnl_by_series"]
    adm = bootstrap_verdict_admissible(d, min_units=10)
    r = sign_bounded_objective(d, admissibility=adm)
    assert r["n_units"] == 5 and r["n_obs"] == 11
    assert (r["n_positive"], r["n_negative"], r["n_zero"]) == (0, 0, 11)
    assert r["min_value"] == 0.0 and r["max_value"] == 0.0
    assert r["all_zero_support"] is True
    assert r["one_sided_support"] is True
    assert r["verdict_bearing"] is False
    assert r["weak_sample"] is False
    assert adm["reasons"] == ["below_min_units", "no_opposing_unit"]
    assert r["inadmissibility_is_definitional"] is True


def test_acceptance_l249_q49_strategy_level_object_is_the_verdict_bearing_one():
    """The NEGATIVE control, from the SAME probe, SAME cut, SAME tape: the
    strategy-level P&L that keeps the unhedged single-side legs straddles zero, so its
    inadmissibility is pure adequacy — this is the object a verdict may rest on."""
    d = _l249_fixture()["strategy_level_pnl_by_series"]
    adm = bootstrap_verdict_admissible(d, min_units=10)
    r = sign_bounded_objective(d, admissibility=adm)
    assert r["n_units"] == 5 and r["n_obs"] == 20
    assert r["n_positive"] == 4 and r["n_negative"] == 5
    assert r["min_value"] == -0.58 and r["max_value"] == 0.73
    assert r["one_sided_support"] is False
    assert r["verdict_bearing"] is True
    assert r["reasons"] == []
    assert adm["reasons"] == ["below_min_units"]
    assert r["inadmissibility_is_definitional"] is False


def test_acceptance_l249_the_l41_gate_alone_cannot_separate_the_two_objects():
    """Why this function had to exist. On the real Q49 populations
    `bootstrap_verdict_admissible` returns admissible=False for BOTH — an identical
    headline for a definitional artifact and a genuine data-adequacy shortfall. Only
    the observation-level sign support tells them apart."""
    f = _l249_fixture()
    both, strat = f["both_fill_pnl_by_series"], f["strategy_level_pnl_by_series"]
    adm_both = bootstrap_verdict_admissible(both, min_units=10)
    adm_strat = bootstrap_verdict_admissible(strat, min_units=10)
    assert adm_both["admissible"] is adm_strat["admissible"] is False
    assert adm_both["n_units"] == adm_strat["n_units"] == 5
    assert (sign_bounded_objective(both, admissibility=adm_both)["verdict_bearing"]
            is not sign_bounded_objective(strat, admissibility=adm_strat)["verdict_bearing"])


def test_acceptance_l249_fixture_carries_its_own_provenance_and_price_tag():
    """Trust default FALSE: the frozen numbers above are only usable because the fixture
    names the producer and the price_source_tag they were computed from."""
    prov = _l249_fixture()["_provenance"]
    assert prov["lesson"] == "L249"
    assert "q49_s68_bothside_maker_fillsim.py" in prov["producer"]
    assert prov["fill_model"] == "touch"
    assert "broker_truth(settlement)" in prov["price_source_tag"]


# --------------------------------------------------------------------------- #
# L250 — turnover_rule_saturation / headline_fill_rate
# --------------------------------------------------------------------------- #

def _l250_fixture(cut: str):
    """The FROZEN 2026-08-02 per-candidate L250 inputs from Q49/S68 (L191/L192: the live
    depth tape grows hourly, so the acceptance tests bind to a committed snapshot, never to
    the moving tree)."""
    import json
    from pathlib import Path
    p = (Path(__file__).resolve().parent / "fixtures"
         / "q49_turnover_saturation_2026-08-02.json")
    return json.loads(p.read_text(encoding="utf-8"))[cut]


def _sat(cut: str):
    u = _l250_fixture(cut)
    return turnover_rule_saturation(
        u["loose_filled"], u["strict_filled"],
        departures=u["departures"], queue_ahead=u["queue_ahead"],
        snapshots_held=u["snapshots_held"])


def test_turnover_saturation_empty_is_no_signal_not_a_clean_bill():
    r = turnover_rule_saturation([], [], departures=[], queue_ahead=[])
    assert r["no_signal"] is True
    assert r["reasons"] == ["empty"]
    assert r["saturated"] is False
    assert r["loose_fill_rate"] is None and r["strict_fill_rate"] is None
    assert r["loose_rule_direction"] == "none"


def test_turnover_saturation_misaligned_inputs_raise_rather_than_silently_zip():
    with pytest.raises(ValueError):
        turnover_rule_saturation([True, False], [True], departures=[1.0, 1.0],
                                 queue_ahead=[1.0, 1.0])
    with pytest.raises(ValueError):
        turnover_rule_saturation([True], [True], departures=[1.0, 2.0], queue_ahead=[1.0])
    with pytest.raises(ValueError):
        turnover_rule_saturation([True], [True], departures=[1.0], queue_ahead=[1.0],
                                 snapshots_held=[10, 10])


def test_turnover_saturation_flags_the_l250_shape():
    """Loose rule fills everything, departures swamp the queue, hold is long → saturated,
    and the loose rule then points NOWHERE (not even the L48 'OUT' reading)."""
    n = 20
    r = turnover_rule_saturation(
        [True] * n, [True] * 8 + [False] * 12,
        departures=[50000.0] * n, queue_ahead=[50.0] * n,
        snapshots_held=[60] * n)
    assert r["saturated"] is True
    assert r["loose_fill_rate"] == 1.0
    assert r["strict_fill_rate"] == 0.4
    assert r["fill_rate_gap"] == pytest.approx(0.6)
    assert r["median_departure_queue_ratio"] == pytest.approx(1000.0)
    assert r["long_hold"] is True
    assert r["loose_rule_discriminates"] is False
    assert r["loose_rule_direction"] == "none"
    assert "loose_fill_rate_at_or_above_floor" in r["reasons"]
    assert "median_departures_swamp_queue" in r["reasons"]
    assert "loose_rule_has_no_variation" in r["reasons"]


def test_turnover_saturation_short_hold_withholds_the_call():
    """A short window genuinely cannot accumulate book migration — the call is WITHHELD
    (long_hold False → not saturated), not asserted, and the L48 OUT reading survives."""
    n = 12
    r = turnover_rule_saturation(
        [True] * n, [False] * n,
        departures=[50000.0] * n, queue_ahead=[50.0] * n,
        snapshots_held=[2] * n)
    assert r["long_hold"] is False
    assert r["saturated"] is False
    assert r["loose_rule_direction"] == "OUT_only"


def test_turnover_saturation_thin_population_is_not_saturated():
    """A dead-thin population (loose rule barely fills, departures never clear the queue) is
    exactly the case L48 says the proxy CAN speak to — it must not be labelled saturated."""
    n = 10
    r = turnover_rule_saturation(
        [False] * 9 + [True], [False] * 10,
        departures=[1.0] * n, queue_ahead=[500.0] * n,
        snapshots_held=[60] * n)
    assert r["saturated"] is False
    assert r["median_departure_queue_ratio"] == pytest.approx(0.002)
    assert r["frac_units_above_ratio_floor"] == 0.0
    assert r["loose_rule_direction"] == "OUT_only"
    assert r["loose_rule_discriminates"] is True


def test_turnover_saturation_zero_queue_units_are_excluded_not_infinite():
    """A front-of-queue rest has an UNDEFINED departures/queue ratio; it is excluded from the
    median and counted, never silently treated as infinite (saturating) or as zero."""
    r = turnover_rule_saturation(
        [True, True, True], [False, False, False],
        departures=[100.0, 200.0, 300.0], queue_ahead=[0.0, 10.0, 20.0],
        snapshots_held=[60, 60, 60])
    assert r["n_units_zero_queue"] == 1
    assert r["n_units_with_ratio"] == 2
    assert r["median_departure_queue_ratio"] == pytest.approx(17.5)


def test_turnover_saturation_no_snapshots_supplied_rests_on_two_halves():
    r = turnover_rule_saturation(
        [True] * 10, [False] * 10,
        departures=[10000.0] * 10, queue_ahead=[10.0] * 10)
    assert r["long_hold"] is None
    assert r["median_snapshots_held"] is None
    assert r["saturated"] is True
    assert "no_snapshot_counts_supplied" in r["reasons"]


def test_turnover_saturation_echoes_its_own_thresholds():
    r = turnover_rule_saturation([True], [False], departures=[1.0], queue_ahead=[1.0],
                                 snapshots_held=[1])
    assert r["ratio_floor"] == TURNOVER_SATURATION_RATIO
    assert r["fill_rate_floor"] == TURNOVER_SATURATION_FILL_RATE
    assert r["min_snapshots"] == MIN_SNAPSHOTS_FOR_SATURATION
    assert r["loose_rule"] == DIAGNOSTIC_FILL_RULE
    assert r["strict_rule"] == PRIMARY_FILL_RULE


def test_headline_fill_rate_refuses_the_loose_rule_even_when_unsaturated():
    """The operative half. L48's direction is unconditional: the loose proxy may never carry
    an affirmative fill-rate headline, saturated or not."""
    unsat = turnover_rule_saturation(
        [False] * 9 + [True], [False] * 10,
        departures=[1.0] * 10, queue_ahead=[500.0] * 10, snapshots_held=[60] * 10)
    assert unsat["saturated"] is False
    with pytest.raises(ValueError, match="may not carry a fill-rate headline"):
        headline_fill_rate(unsat, DIAGNOSTIC_FILL_RULE)
    assert headline_fill_rate(unsat, PRIMARY_FILL_RULE) == 0.0


def test_headline_fill_rate_rejects_unknown_rule_and_no_signal():
    r = turnover_rule_saturation([True], [True], departures=[1.0], queue_ahead=[1.0])
    with pytest.raises(ValueError, match="unknown fill rule"):
        headline_fill_rate(r, "candlestick")
    empty = turnover_rule_saturation([], [], departures=[], queue_ahead=[])
    with pytest.raises(ValueError, match="no_signal"):
        headline_fill_rate(empty, PRIMARY_FILL_RULE)
    with pytest.raises(TypeError):
        headline_fill_rate("not a report", PRIMARY_FILL_RULE)


# --- HARD acceptance tests over the FROZEN Q49/S68 tape slice (L191) ---------

def test_l250_acceptance_unrestricted_cut_reproduces_the_lesson_numbers():
    """L250's own stated measurement, machine-checked: on the SAME 445 candidates the loose
    turnover rule read ~98% both-fill while the strict touch rule read ~42%."""
    r = _sat("unrestricted")
    assert r["n_units"] == 445
    assert r["loose_fill_rate"] == pytest.approx(0.9798, abs=5e-4)
    assert r["strict_fill_rate"] == pytest.approx(0.4247, abs=5e-4)
    assert r["fill_rate_gap"] > 0.55
    assert r["median_departure_queue_ratio"] == pytest.approx(306.2, abs=0.1)
    assert r["median_snapshots_held"] == 66.0
    assert r["saturated"] is True
    assert r["loose_rule_direction"] == "none"


def test_l250_acceptance_primary_cut_loose_rule_has_zero_variation():
    """On Q49's PRIMARY (fillable_entry) population the loose rule fills 20/20 — a statistic
    with no variation left cannot discriminate anything, which is exactly why the verdict
    rested on the strict rule's 55%."""
    r = _sat("fillable_entry")
    assert r["n_units"] == 20
    assert r["loose_fill_rate"] == 1.0
    assert r["strict_fill_rate"] == pytest.approx(0.55)
    assert r["loose_rule_discriminates"] is False
    assert r["saturated"] is True
    assert headline_fill_rate(r, PRIMARY_FILL_RULE) == pytest.approx(0.55)
    with pytest.raises(ValueError):
        headline_fill_rate(r, DIAGNOSTIC_FILL_RULE)


def test_l250_fixture_carries_its_own_provenance():
    import json
    from pathlib import Path
    p = (Path(__file__).resolve().parent / "fixtures"
         / "q49_turnover_saturation_2026-08-02.json")
    prov = json.loads(p.read_text(encoding="utf-8"))["_provenance"]
    assert prov["lesson"] == "L250"
    assert "q49_s68_bothside_maker_fillsim.py" in prov["producer"]
    assert "real_bid" in prov["price_source_tag"]
    assert "broker_truth(settlement)" in prov["price_source_tag"]
