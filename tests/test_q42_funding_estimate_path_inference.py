"""Offline unit tests for scripts/q42_funding_estimate_path_inference.py.

Offline throughout — no network. Synthetic fixtures except for the TAPE-PINNED tests in
the `=== correction round 2 ===` block at the bottom, which read the COMMITTED
`tape/perp_tape/` read-only over an EXPLICIT FROZEN DAY-SLICE (see
`_FROZEN_TAPE_SLICE_DAYS`; they skip, rather than silently pass, if the family is
absent): a claim the writeup quotes as a number must be re-runnable from the shipped
artifact, and round 1 published a leave-one-out result that lived only in a throwaway
session. The load-bearing cases:
  * the NESTED `prints[]` flatten (a `funding_rates` record is an ENVELOPE, not a row),
  * the BOTH-modes dedupe (L137: reading only `mode=="backfill"` is the documented bug),
  * the `record_type` filter (L96-class family conflation),
  * a REGRESSION pinning that the naive TOP-LEVEL `(ticker, funding_time)` join returns
    ZERO entries, so that trap cannot silently return,
  * the theta/separation + hard-gap logic on both a separable and an overlapping fixture,
  * that this module makes no raw `datetime.fromisoformat` call (L136/L138).

2026-07-24 CORRECTION BLOCK (post-verifier) — the tests below `# === correction ===` pin
the two pieces of logic the refutation turned on, so the correction cannot silently
regress:
  * DENSITY STRATIFICATION — a pooled class overlap that DISAPPEARS on the dense subsets
    is a capture-staleness artifact, not nondeterminism. The fixture builds exactly that
    shape (dense windows separable, sparse/stale windows overlapping) and pins that the
    stratified table recovers the hidden gap while the pooled test does not.
  * CLUSTER-ROBUST PERMUTATION (L6) — the naive Fisher p treats 286 windows as 286
    independent observations; they are 13 tickers x 22 funding_times. The fixture pins
    that an association living entirely inside ONE cluster gives a tiny naive p and a
    LARGE cluster-robust p, and that the fast hypergeometric sampler agrees with a
    brute-force within-stratum shuffle.

2026-07-24 CORRECTION ROUND 2 (a SECOND independent verifier; the UNDECIDABLE verdict
SURVIVED, four supporting pieces did not) — see the `=== correction round 2 ===` block:
  * LEAVE-ONE-OUT is now shipped code (67 drops = 7 discriminating tickers + 18
    discriminating funding_times + 42 windows) and tape-pinned, instead of a number
    quoted in the writeup with nothing behind it.
  * GAP MONOTONICITY is pinned as a TAUTOLOGY on nested chains (round 1's docstring
    claimed the opposite), and the matched-size RANDOM-SUBSET baseline is pinned as the
    statistic that actually discriminates.
  * The failures-vs-successes contrast is pinned as TWO SEPARATE axes (lead vs sample
    count) because on the real tape only the lead axis is supported.
  * The 9-cut post-hoc search family and its Bonferroni correction are pinned.
"""
from __future__ import annotations

import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import q42_funding_estimate_path_inference as Q  # noqa: E402

UTC = timezone.utc


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def est_row(ticker: str, nft: str, value, computed: str, **kw):
    r = {
        "record_type": "funding_estimate",
        "ticker": ticker,
        "next_funding_time": nft,
        "funding_rate_estimate": value,
        "computed_time": computed,
        "captured_at": computed,
        "capture_id": kw.pop("capture_id", computed),
        "price_source_tag": "broker_truth",
    }
    r.update(kw)
    return r


def fr_envelope(mode: str, prints):
    return {
        "record_type": "funding_rates",
        "mode": mode,
        "n_prints": len(prints),
        "prints": prints,
        "price_source_tag": "broker_truth",
    }


def pr(ticker: str, ft: str, rate):
    return {"market_ticker": ticker, "funding_time": ft, "funding_rate": rate,
            "mark_price": 1.0}


FT = "2026-07-20T12:00:00Z"


def win(values_and_leads, finalized, ticker="KXTESTPERP", ft=FT):
    """Build a Window from [(value, lead_hours_before_close), ...]."""
    ft_dt = Q.parse_iso_utc(ft)
    path = sorted(((ft_dt - timedelta(hours=lh), float(v)) for v, lh in values_and_leads),
                  key=lambda t: t[0])
    return Q.Window(ticker=ticker, funding_time=ft, funding_time_dt=ft_dt,
                    path=path, finalized=float(finalized))


# --------------------------------------------------------------------------- #
# loader: record_type filter + field name
# --------------------------------------------------------------------------- #
def test_collect_estimates_filters_record_type():
    recs = [
        est_row("KXAPERP", FT, 1.5e-4, "2026-07-20T08:00:00Z"),
        {"record_type": "markets", "ticker": "KXAPERP"},
        {"record_type": "orderbook", "ticker": "KXAPERP"},
        fr_envelope("backfill", [pr("KXAPERP", FT, 0.0)]),
    ]
    out = Q.collect_funding_estimates(recs)
    assert len(out) == 1
    assert out[0]["ticker"] == "KXAPERP"
    assert out[0]["funding_rate_estimate"] == pytest.approx(1.5e-4)


def test_collect_estimates_reads_funding_rate_estimate_not_funding_rate():
    """The field is `funding_rate_estimate`. A row carrying only `funding_rate` /
    `funding_estimate` is NOT an estimate row and must be dropped, never coerced."""
    recs = [
        {"record_type": "funding_estimate", "ticker": "KXAPERP", "next_funding_time": FT,
         "funding_rate": 9.9e-4, "computed_time": "2026-07-20T08:00:00Z"},
        {"record_type": "funding_estimate", "ticker": "KXAPERP", "next_funding_time": FT,
         "funding_estimate": 9.9e-4, "computed_time": "2026-07-20T08:00:00Z"},
    ]
    assert Q.collect_funding_estimates(recs) == []


def test_collect_estimates_missing_estimate_is_dropped_not_zeroed():
    recs = [est_row("KXAPERP", FT, None, "2026-07-20T08:00:00Z"),
            est_row("KXAPERP", FT, 0.0, "2026-07-20T09:00:00Z")]
    out = Q.collect_funding_estimates(recs)
    assert len(out) == 1
    assert out[0]["funding_rate_estimate"] == 0.0


def test_collect_estimates_accepts_explicit_zero():
    """0.0 is a REAL clamped observation, not a missing value — it must survive."""
    out = Q.collect_funding_estimates([est_row("KXAPERP", FT, 0.0, "2026-07-20T08:00:00Z")])
    assert len(out) == 1 and out[0]["funding_rate_estimate"] == 0.0


# --------------------------------------------------------------------------- #
# loader: the nested prints[] flatten + both-modes dedupe (L137)
# --------------------------------------------------------------------------- #
def test_finalized_prints_flatten_nested_envelope():
    recs = [fr_envelope("backfill", [pr("KXAPERP", FT, 1e-4), pr("KXBPERP", FT, 0.0)])]
    idx, meta = Q.collect_finalized_prints(recs)
    assert set(idx) == {("KXAPERP", FT), ("KXBPERP", FT)}
    assert meta["n_prints_read"] == 2 and meta["n_prints_dedup"] == 2
    assert idx[("KXAPERP", FT)]["funding_rate"] == pytest.approx(1e-4)


def test_finalized_prints_reads_both_modes_L137():
    """Reading only mode=='backfill' is the exact L137 bug: the recent-mode print here
    exists ONLY in the recent envelope and must still be joined."""
    later = "2026-07-24T12:00:00Z"
    recs = [fr_envelope("backfill", [pr("KXAPERP", FT, 0.0)]),
            fr_envelope("recent", [pr("KXAPERP", later, -2e-4)])]
    idx, meta = Q.collect_finalized_prints(recs)
    assert set(idx) == {("KXAPERP", FT), ("KXAPERP", later)}
    assert meta["modes_seen"] == {"backfill": 1, "recent": 1}
    backfill_only = {k: v for k, v in idx.items() if v["mode"] == "backfill"}
    assert len(backfill_only) == 1, "fixture must actually exercise the recent mode"


def test_finalized_prints_dedupe_first_wins():
    recs = [fr_envelope("backfill", [pr("KXAPERP", FT, 1e-4)]),
            fr_envelope("recent", [pr("KXAPERP", FT, 5e-4)]),
            fr_envelope("recent", [pr("KXAPERP", FT, 7e-4)])]
    idx, meta = Q.collect_finalized_prints(recs)
    assert len(idx) == 1
    assert idx[("KXAPERP", FT)]["funding_rate"] == pytest.approx(1e-4)
    assert meta["n_prints_read"] == 3 and meta["n_dupes_dropped"] == 2


def test_finalized_prints_ignores_other_record_types():
    recs = [{"record_type": "markets", "prints": [pr("KXAPERP", FT, 1e-4)]},
            {"record_type": "funding_estimate", "ticker": "KXAPERP"}]
    idx, meta = Q.collect_finalized_prints(recs)
    assert idx == {} and meta["n_envelopes"] == 0


# --------------------------------------------------------------------------- #
# THE TRAP — regression pin
# --------------------------------------------------------------------------- #
def test_naive_toplevel_join_returns_zero_regression():
    """Keying funding_rates records at TOP LEVEL yields an EMPTY index — the silent-zero
    trap. Pinned so it can never quietly come back as a 'working' join."""
    recs = [fr_envelope("backfill", [pr("KXAPERP", FT, 1e-4), pr("KXBPERP", FT, 0.0)]),
            fr_envelope("recent", [pr("KXAPERP", FT, 1e-4)])]
    assert Q.naive_toplevel_print_index(recs) == {}
    # ...while the correct flatten finds them.
    good, _ = Q.collect_finalized_prints(recs)
    assert len(good) == 2


def test_naive_toplevel_join_would_produce_zero_windows():
    recs = [est_row("KXAPERP", FT, 1.5e-4, "2026-07-20T08:00:00Z"),
            fr_envelope("backfill", [pr("KXAPERP", FT, 1.5e-4)])]
    groups = Q.group_estimates(Q.collect_funding_estimates(recs))
    trap_windows, _ = Q.build_windows(groups, Q.naive_toplevel_print_index(recs))
    assert trap_windows == []
    good_idx, _ = Q.collect_finalized_prints(recs)
    good_windows, _ = Q.build_windows(groups, good_idx)
    assert len(good_windows) == 1


# --------------------------------------------------------------------------- #
# window construction
# --------------------------------------------------------------------------- #
def test_build_windows_inner_join_and_ordering():
    recs = [
        est_row("KXAPERP", FT, 0.0, "2026-07-20T10:00:00Z"),
        est_row("KXAPERP", FT, -1.5e-4, "2026-07-20T04:00:00Z"),
        est_row("KXBPERP", FT, 1e-4, "2026-07-20T04:00:00Z"),   # no finalized print
        fr_envelope("backfill", [pr("KXAPERP", FT, -2e-4)]),
    ]
    groups = Q.group_estimates(Q.collect_funding_estimates(recs))
    idx, _ = Q.collect_finalized_prints(recs)
    ws, meta = Q.build_windows(groups, idx)
    assert len(ws) == 1 and meta["n_groups_without_print"] == 1
    w = ws[0]
    assert w.values == [pytest.approx(-1.5e-4), 0.0]  # sorted ascending by computed_time
    assert w.finalized == pytest.approx(-2e-4)
    assert w.last_lead_hours == pytest.approx(2.0)
    assert w.first_lead_hours == pytest.approx(8.0)


def test_build_windows_drops_none_rate_never_zeroes_it():
    recs = [est_row("KXAPERP", FT, 1e-4, "2026-07-20T04:00:00Z"),
            fr_envelope("backfill", [pr("KXAPERP", FT, None)])]
    groups = Q.group_estimates(Q.collect_funding_estimates(recs))
    idx, _ = Q.collect_finalized_prints(recs)
    ws, meta = Q.build_windows(groups, idx)
    assert ws == [] and meta["n_groups_print_rate_none"] == 1


def test_build_windows_drops_samples_at_or_after_close():
    recs = [est_row("KXAPERP", FT, 1e-4, "2026-07-20T04:00:00Z"),
            est_row("KXAPERP", FT, 9e-4, FT),                       # exactly at close
            est_row("KXAPERP", FT, 9e-4, "2026-07-20T13:00:00Z"),   # after close
            fr_envelope("backfill", [pr("KXAPERP", FT, 1e-4)])]
    groups = Q.group_estimates(Q.collect_funding_estimates(recs))
    idx, _ = Q.collect_finalized_prints(recs)
    ws, meta = Q.build_windows(groups, idx)
    assert len(ws) == 1 and ws[0].n_samples == 1
    assert meta["n_samples_dropped_not_pre_close"] == 2


# --------------------------------------------------------------------------- #
# candidate g's
# --------------------------------------------------------------------------- #
def test_g_last_and_maxabs_and_last_nonzero():
    w = win([(-1.0e-4, 8), (3.0e-4, 5), (0.0, 1)], finalized=0.0)
    assert Q.g_last(w) == 0.0
    assert Q.g_maxabs(w) == pytest.approx(3.0e-4)
    assert Q.g_last_nonzero(w) == pytest.approx(3.0e-4)
    assert Q.g_mean(w) == pytest.approx((-1.0e-4 + 3.0e-4 + 0.0) / 3)


def test_g_last_nonzero_all_zero_path_is_zero():
    w = win([(0.0, 8), (0.0, 2)], finalized=0.0)
    assert Q.g_last_nonzero(w) == 0.0
    assert Q.g_maxabs(w) == 0.0
    assert Q.g_mean(w) == 0.0
    assert Q.g_last(w) == 0.0


def test_g_twap_weights_by_held_duration():
    """Sample at close-8h holds 6h at 0.0; sample at close-2h holds 2h at 1.0.
    TWAP = (0*6 + 1*2)/8 = 0.25 — distinct from the simple mean 0.5."""
    w = win([(0.0, 8), (1.0, 2)], finalized=0.0)
    assert Q.g_twap(w) == pytest.approx(0.25)
    assert Q.g_mean(w) == pytest.approx(0.5)


def test_g_twap_single_sample_equals_that_sample():
    w = win([(2.5e-4, 3)], finalized=0.0)
    assert Q.g_twap(w) == pytest.approx(2.5e-4)


def test_g_twap_degenerate_zero_weight_falls_back_to_mean():
    ft_dt = Q.parse_iso_utc(FT)
    w = Q.Window(ticker="X", funding_time=FT, funding_time_dt=ft_dt,
                 path=[(ft_dt, 1.0), (ft_dt, 3.0)], finalized=0.0)
    assert Q.g_twap(w) == pytest.approx(2.0)


def test_every_candidate_g_is_zero_on_an_all_zero_path():
    """The premise of the class-wide falsifier: no candidate can distinguish all-zero
    paths from each other, so an all-zero path with a nonzero print breaks the class."""
    w = win([(0.0, 8), (0.0, 4), (0.0, 1)], finalized=0.0)
    for name, fn in Q.CANDIDATE_GS.items():
        assert fn(w) == 0.0, name


# --------------------------------------------------------------------------- #
# theta / separation logic
# --------------------------------------------------------------------------- #
def test_best_threshold_perfect_separation_has_hard_gap():
    abs_g = [1e-5, 2e-5, 3e-5, 5e-4, 6e-4]
    is_zero = [True, True, True, False, False]
    s = Q.best_threshold(abs_g, is_zero)
    assert s["n_misclassified"] == 0
    assert s["hard_gap"] is True
    assert s["gap_width"] == pytest.approx(5e-4 - 3e-5)
    assert 3e-5 < s["theta"] <= 5e-4


def test_best_threshold_overlap_has_no_hard_gap():
    abs_g = [1e-4, 3e-4, 2e-4, 1.5e-4]
    is_zero = [True, True, False, False]  # a zero-print sits ABOVE a nonzero-print
    s = Q.best_threshold(abs_g, is_zero)
    assert s["hard_gap"] is False
    assert s["gap_width"] < 0
    assert s["n_misclassified"] >= 1


def test_best_threshold_reports_untuned_dead_band_separately():
    abs_g = [5e-5, 5e-5, 9e-4, 9e-4]
    is_zero = [True, True, False, False]
    s = Q.best_threshold(abs_g, is_zero, untuned_theta=1e-4)
    assert s["n_misclassified"] == 0
    assert s["n_misclassified_untuned"] == 0
    s2 = Q.best_threshold(abs_g, is_zero, untuned_theta=1e-3)
    assert s2["n_misclassified"] == 0          # tuned theta still separates
    assert s2["n_misclassified_untuned"] == 2  # the untuned band calls everything zero


def test_best_threshold_misclassification_breakdown():
    abs_g = [4e-4, 1e-5]
    is_zero = [True, False]  # exactly inverted
    s = Q.best_threshold(abs_g, is_zero)
    assert s["n_false_zero"] + s["n_false_nonzero"] == s["n_misclassified"]
    assert s["n_misclassified"] == 1  # a degenerate all-one-side theta still gets one right


def test_best_threshold_empty_input_is_none_not_crash():
    s = Q.best_threshold([], [])
    assert s["theta"] is None and s["n_misclassified"] is None


def test_best_threshold_single_class_leaves_hard_gap_undecidable():
    s = Q.best_threshold([1e-4, 2e-4], [True, True])
    assert s["hard_gap"] is None and s["n_misclassified"] == 0


# --------------------------------------------------------------------------- #
# identity fit
# --------------------------------------------------------------------------- #
def test_identity_fit_exact_identity():
    g = [1e-4, -2e-4, 3e-4, -1.5e-4]
    fit = Q.identity_fit(g, list(g))
    assert fit["pearson_r"] == pytest.approx(1.0)
    assert fit["mean_abs_residual"] == pytest.approx(0.0)
    assert fit["sign_agreement_fraction"] == pytest.approx(1.0)


def test_identity_fit_scaled_but_correlated_is_not_identity():
    """r == 1 with a 2x scale error: correlation alone must not read as identity."""
    g = [1e-4, 2e-4, 3e-4, 4e-4]
    fin = [2 * x for x in g]
    fit = Q.identity_fit(g, fin)
    assert fit["pearson_r"] == pytest.approx(1.0)
    assert fit["mean_abs_residual"] > 0
    assert fit["mean_abs_residual_over_median_abs_finalized"] > 0.3


def test_identity_fit_residual_lead_structure():
    """|residual| rising with the last sample's lead time is STRUCTURE (staleness)."""
    g = [1e-4, 1e-4, 1e-4, 1e-4]
    fin = [1.0e-4, 1.2e-4, 1.4e-4, 1.6e-4]
    fit = Q.identity_fit(g, fin, [1.0, 2.0, 3.0, 4.0])
    assert fit["r_absresidual_vs_last_sample_lead_hours"] == pytest.approx(1.0, abs=1e-9)
    assert fit["n_with_lead"] == 4


def test_identity_fit_lead_none_tolerated():
    fit = Q.identity_fit([1e-4, 2e-4, 3e-4], [1e-4, 2e-4, 3e-4], [None, None, None])
    assert fit["r_absresidual_vs_last_sample_lead_hours"] is None
    assert fit["n_with_lead"] == 0


def test_identity_fit_small_n_leaves_r_none():
    """Hard Rule #2's n>=4 floor (via core.stats.safe_pstdev): below it r is None, not a
    confident-looking number off 2-3 points."""
    assert Q.identity_fit([1e-4, 2e-4], [1e-4, 2e-4])["pearson_r"] is None
    assert Q.identity_fit([1e-4, 2e-4, 3e-4], [1e-4, 2e-4, 3e-4])["pearson_r"] is None
    assert Q.identity_fit([1e-4, 2e-4, 3e-4, 4e-4],
                          [1e-4, 2e-4, 3e-4, 4e-4])["pearson_r"] == pytest.approx(1.0)


def test_identity_fit_constant_series_leaves_r_none_not_zero():
    fit = Q.identity_fit([1e-4] * 5, [1e-4, 2e-4, 3e-4, 4e-4, 5e-4])
    assert fit["pearson_r"] is None


# --------------------------------------------------------------------------- #
# exact Fisher + class-wide falsifier + clamp summary
# --------------------------------------------------------------------------- #
def test_fisher_exact_known_value_tea_tasting():
    # Fisher's tea-tasting 2x2 [[3,1],[1,3]]: two-sided p = 0.4857142857...
    assert Q.fisher_exact_2x2(3, 1, 1, 3) == pytest.approx(0.4857142857, abs=1e-9)


def test_fisher_exact_independent_table_is_p1():
    assert Q.fisher_exact_2x2(5, 5, 5, 5) == pytest.approx(1.0)


def test_fisher_exact_strong_association_is_tiny():
    assert Q.fisher_exact_2x2(20, 0, 0, 20) < 1e-8


def test_class_wide_falsifier_flags_the_counterexample():
    ws = [win([(0.0, 8), (0.0, 2)], finalized=0.0),
          win([(0.0, 8)], finalized=1.4e-4, ticker="KXBPERP"),
          win([(1.5e-4, 4)], finalized=1.5e-4, ticker="KXCPERP")]
    cf = Q.class_wide_falsifier(ws)
    assert cf["n_allzero_path_windows"] == 2
    assert cf["n_allzero_path_finalized_nonzero"] == 1
    assert cf["class_falsified"] is True
    assert cf["counterexamples"][0]["ticker"] == "KXBPERP"


def test_class_wide_falsifier_not_triggered_when_consistent():
    ws = [win([(0.0, 8)], finalized=0.0), win([(1.5e-4, 4)], finalized=1.5e-4)]
    assert Q.class_wide_falsifier(ws)["class_falsified"] is False


def test_estimate_clamp_summary_detects_dead_band():
    ests = [{"funding_rate_estimate": v} for v in
            [0.0, 0.0, 0.0, 1.2e-4, -1.05e-4, 3e-4]]
    s = Q.estimate_clamp_summary(ests, dead_band=1e-4)
    assert s["n"] == 6 and s["n_zero"] == 3
    assert s["n_nonzero_inside_band"] == 0
    assert s["min_abs_nonzero"] == pytest.approx(1.05e-4)


def test_estimate_clamp_summary_detects_band_violation():
    ests = [{"funding_rate_estimate": v} for v in [0.0, 4e-5, 2e-4]]
    s = Q.estimate_clamp_summary(ests, dead_band=1e-4)
    assert s["n_nonzero_inside_band"] == 1


# --------------------------------------------------------------------------- #
# end-to-end over a synthetic tape + hygiene
# --------------------------------------------------------------------------- #
def test_analyze_end_to_end_synthetic_reports_integrity_mismatch_honestly():
    recs = [
        est_row("KXAPERP", FT, 0.0, "2026-07-20T04:00:00Z"),
        est_row("KXAPERP", FT, -1.4e-4, "2026-07-20T10:00:00Z"),
        {"record_type": "markets", "ticker": "KXAPERP"},
        fr_envelope("recent", [pr("KXAPERP", FT, -1.6e-4)]),
    ]
    rep = Q.analyze(recs)
    assert rep["price_source_tag"] == "broker_truth"
    assert rep["is_pnl_claim"] is False
    assert rep["integrity"]["observed"]["n_joined_windows"] == 1
    # a synthetic fixture must NOT claim to reproduce the real pre-measured population
    assert rep["integrity"]["reproduced"] is False
    assert rep["per_g"]["g_last"]["discriminating"]["separation"]["n"] == 1


def test_load_records_passthrough_list():
    recs = [{"record_type": "funding_estimate"}]
    assert Q.load_records(recs) == recs


def test_load_records_missing_path_is_empty_not_crash():
    assert Q.load_records(str(ROOT / "tape" / "no_such_dir" / "dt=*.jsonl")) == []


def test_module_makes_no_raw_fromisoformat_call_L136():
    """L136/L138: Python 3.9's datetime.fromisoformat rejects bare-'Z' and short-fraction
    timestamps. Every ISO string here must go through core.timeutil.parse_iso_utc."""
    src = (ROOT / "scripts" / "q42_funding_estimate_path_inference.py").read_text()
    # CALL SITES only (`fromisoformat(`), so the docstring that NAMES the hazard is fine.
    assert re.findall(r"fromisoformat\s*\(", src) == []
    assert "parse_iso_utc" in src


def test_expected_integrity_constants_are_the_lead_premeasured_population():
    assert Q.EXPECTED_INTEGRITY == {
        "n_estimate_groups": 299,
        "n_finalized_prints_dedup": 1746,
        "n_joined_windows": 286,
        "n_joined_tickers": 13,
        "n_joined_funding_times": 22,
        "n_joined_ge3_samples": 130,
        "n_discriminating": 42,
        "n_discriminating_finalized_zero": 28,
    }


# =========================================================================== #
# === correction === (2026-07-24, post-verifier)
# density stratification: is a pooled overlap just capture staleness?
# =========================================================================== #
def _staleness_fixture():
    """Dense windows separate PERFECTLY; two sparse/stale 1-sample windows sit on the
    wrong side and destroy the pooled gap. This is the exact shape the verifier found on
    the real tape (gap monotone in density, inverting to a hard gap when sparse windows
    are dropped)."""
    dense_zero = [win([(3e-5, 8), (4e-5, 6), (5e-5, 4), (5e-5, 0.5)], finalized=0.0,
                      ticker=f"KXD{i}PERP") for i in range(2)]
    dense_nonzero = [win([(2e-4, 8), (2e-4, 6), (2e-4, 4), (2.2e-4, 0.5)], finalized=2.2e-4,
                         ticker=f"KXE{i}PERP") for i in range(2)]
    # sparse + stale, and on the WRONG side: |g|=3e-4 but the print clamped to zero
    sparse_zero = [win([(3e-4, 5.0)], finalized=0.0, ticker="KXSPARSE1PERP")]
    sparse_nonzero = [win([(1e-5, 5.0)], finalized=1.5e-4, ticker="KXSPARSE2PERP")]
    return dense_zero + dense_nonzero + sparse_zero + sparse_nonzero


def test_density_stratification_recovers_a_gap_the_pooled_test_hides():
    ws = _staleness_fixture()
    pooled = Q.best_threshold([abs(Q.g_last(w)) for w in ws],
                              [w.finalized_is_zero for w in ws])
    assert pooled["hard_gap"] is False, "fixture must have NO pooled gap"

    rows = Q.density_stratified_separation(ws, Q.g_last)
    by = {r["filter"]: r for r in rows}
    assert by["n>=1"]["n"] == 6 and by["n>=1"]["hard_gap"] is False
    dense = by["n>=4"]
    assert dense["n"] == 4 and dense["n_finalized_zero"] == 2
    assert dense["hard_gap"] is True, "dropping the sparse windows must restore the gap"
    assert dense["gap_width"] > 0


def test_density_stratification_strata_are_nested_and_shrink():
    ws = _staleness_fixture()
    rows = [r for r in Q.density_stratified_separation(ws, Q.g_last)
            if r["stratifier"] == "min_samples"]
    ns = [r["n"] for r in sorted(rows, key=lambda r: r["value"])]
    assert ns == sorted(ns, reverse=True)


def test_density_stratification_empty_stratum_does_not_keyerror():
    """No window here has >=8 samples: the stratum is EMPTY and must still carry the full
    key set (the report iterates every row)."""
    rows = Q.density_stratified_separation(_staleness_fixture(), Q.g_last)
    empty = [r for r in rows if r["filter"] == "n>=8"][0]
    assert empty["n"] == 0
    for k in ("n_finalized_zero", "n_finalized_nonzero", "gap_width", "hard_gap",
              "n_misclassified_untuned", "median_samples"):
        assert k in empty


def test_density_stratification_lead_filter_uses_last_sample_lead():
    """The lead cut keeps the windows we looked at LATE, independent of path length."""
    ws = [win([(1e-4, 0.5)], finalized=0.0, ticker="KXFRESHPERP"),
          win([(1e-4, 6), (1e-4, 5), (1e-4, 4)], finalized=0.0, ticker="KXSTALEPERP")]
    rows = {r["filter"]: r for r in Q.density_stratified_separation(ws, Q.g_last)}
    assert rows["lead<=0.75h"]["n"] == 1      # the 1-sample FRESH window, not the 3-sample stale one
    assert rows["n>=3"]["n"] == 1             # and the sample cut selects the opposite window


def test_gap_monotonicity_flags_the_density_confound():
    rows = Q.density_stratified_separation(_staleness_fixture(), Q.g_last)
    mono = Q.gap_is_monotone_in_density(rows)
    assert mono["monotone_nondecreasing_in_density"] is True
    assert "n>=4" in mono["strata_with_hard_gap"]
    assert mono["pooled_overlap_is_density_confounded"] is True


def test_gap_monotonicity_not_flagged_when_density_is_irrelevant():
    """Genuine nondeterminism: two windows with IDENTICAL dense paths and different
    prints. No stratum can ever separate them, so nothing is flagged as confounded."""
    ws = [win([(1.2e-4, 8), (1.2e-4, 4), (1.2e-4, 2), (1.2e-4, 0.4)], finalized=0.0,
              ticker="KXAPERP"),
          win([(1.2e-4, 8), (1.2e-4, 4), (1.2e-4, 2), (1.2e-4, 0.4)], finalized=1.3e-4,
              ticker="KXBPERP")]
    mono = Q.gap_is_monotone_in_density(Q.density_stratified_separation(ws, Q.g_last))
    assert mono["strata_with_hard_gap"] == []
    assert mono["pooled_overlap_is_density_confounded"] is False


def test_misclassification_density_contrast_exposes_sparse_failures():
    ws = _staleness_fixture()
    mc = Q.misclassification_density_contrast(ws, Q.g_last, theta=1e-4)
    assert mc["misclassified"]["n"] == 2                     # exactly the two sparse windows
    assert mc["misclassified"]["median_samples"] == 1
    assert mc["correct"]["median_samples"] == 4
    assert mc["misclassified"]["median_last_lead_hours"] == pytest.approx(5.0)
    assert {d["ticker"] for d in mc["misclassified_detail"]} == {"KXSPARSE1PERP",
                                                                 "KXSPARSE2PERP"}


def test_hard_gap_exact_permutation_p_is_one_over_n_choose_k():
    """The verifier's counter-note, pinned: a hard gap on n=11 with ONE nonzero-finalized
    window has exact p = 1/11 = 0.0909 — VACUOUS. n=14 with 2 gives 1/91 = 0.0110."""
    assert Q.hard_gap_exact_permutation_p(11, 1) == pytest.approx(1 / 11)
    assert Q.hard_gap_exact_permutation_p(14, 2) == pytest.approx(1 / 91)
    assert Q.hard_gap_exact_permutation_p(42, 14) < 1e-10


def test_hard_gap_exact_permutation_p_degenerate_is_none():
    assert Q.hard_gap_exact_permutation_p(10, 0) is None
    assert Q.hard_gap_exact_permutation_p(10, 10) is None
    assert Q.hard_gap_exact_permutation_p(0, 0) is None


def test_exact_p_reported_only_where_a_hard_gap_exists():
    rows = Q.density_stratified_separation(_staleness_fixture(), Q.g_last)
    for r in rows:
        if r["hard_gap"] is True:
            assert r["exact_p_if_hard_gap"] is not None
        else:
            assert r["exact_p_if_hard_gap"] is None


# =========================================================================== #
# === correction === cluster-robust permutation (L6)
# =========================================================================== #
def _bruteforce_cluster_p(strata, x, y, n_perm, seed):
    """Reference implementation: literally shuffle the labels within each stratum. The
    shipped version samples the equivalent hypergeometric overlap instead (much faster);
    the two must agree up to Monte-Carlo noise."""
    rng = random.Random(seed)
    groups = {}
    for i, s in enumerate(strata):
        groups.setdefault(s, []).append(i)
    obs = sum(1 for xi, yi in zip(x, y) if xi and yi)
    perm_y = list(y)
    ge = 0
    for _ in range(n_perm):
        for ids in groups.values():
            vals = [y[i] for i in ids]
            rng.shuffle(vals)
            for i, v in zip(ids, vals):
                perm_y[i] = v
        if sum(1 for i in range(len(x)) if x[i] and perm_y[i]) >= obs:
            ge += 1
    return (ge + 1) / (n_perm + 1)


def _three_cluster_fixture():
    strata, x, y = [], [], []
    for c in ("A", "B", "C"):
        strata += [c] * 6
        x += [True, True, True, False, False, False]
        y += [True, True, False, False, False, False]
    return strata, x, y


def test_cluster_permutation_matches_bruteforce_shuffle():
    strata, x, y = _three_cluster_fixture()
    fast = Q.cluster_permutation_p(strata, x, y, n_perm=20000, seed=11)["p_one_sided"]
    slow = _bruteforce_cluster_p(strata, x, y, n_perm=20000, seed=99)
    assert fast == pytest.approx(slow, abs=0.02)


def test_cluster_permutation_is_deterministic_given_seed():
    strata, x, y = _three_cluster_fixture()
    a = Q.cluster_permutation_p(strata, x, y, n_perm=2000, seed=7)
    b = Q.cluster_permutation_p(strata, x, y, n_perm=2000, seed=7)
    assert a == b
    c = Q.cluster_permutation_p(strata, x, y, n_perm=2000, seed=8)
    assert c["seed"] == 8 and c["n_perm"] == 2000


def test_cluster_permutation_kills_a_single_cluster_association_L6():
    """THE REFUTATION, pinned. All the association lives in ONE cluster: the naive Fisher
    p is tiny (it pretends 24 independent rows) while the cluster-robust p is large,
    because within-cluster permutation cannot manufacture it."""
    strata = ["HOT"] * 12 + ["COLD"] * 12
    x = [True] * 6 + [False] * 6 + [False] * 12
    y = [True] * 6 + [False] * 6 + [False] * 12
    a = sum(1 for xi, yi in zip(x, y) if xi and yi)
    b = sum(1 for xi, yi in zip(x, y) if xi and not yi)
    c = sum(1 for xi, yi in zip(x, y) if not xi and yi)
    d = sum(1 for xi, yi in zip(x, y) if not xi and not yi)
    naive = Q.fisher_exact_2x2(a, b, c, d)
    clustered = Q.cluster_permutation_p(strata, x, y, n_perm=5000, seed=3)["p_one_sided"]
    assert naive < 1e-4
    assert clustered > 0.001
    assert clustered > naive * 10, "clustering must be strictly more conservative here"


def test_cluster_permutation_no_association_gives_large_p():
    strata = ["A"] * 8 + ["B"] * 8
    x = ([True] * 4 + [False] * 4) * 2
    y = ([True, False] * 4) * 2
    p = Q.cluster_permutation_p(strata, x, y, n_perm=5000, seed=5)["p_one_sided"]
    assert p > 0.2


def test_cluster_permutation_p_is_add_one_and_never_zero():
    """An add-one estimator: p can never be 0, and its floor is the MC resolution."""
    strata = ["A"] * 10
    x = [True] * 5 + [False] * 5
    y = [True] * 5 + [False] * 5
    out = Q.cluster_permutation_p(strata, x, y, n_perm=1000, seed=1)
    assert out["p_one_sided"] > 0
    assert out["p_one_sided"] >= out["mc_resolution"]
    assert out["mc_resolution"] == pytest.approx(1 / 1001)


def test_cluster_permutation_constant_cluster_contributes_no_variation():
    """A stratum where every row is x-true (or every label is set) is DETERMINISTIC under
    permutation — it must be folded into the fixed term, not resampled."""
    strata = ["A"] * 4
    x = [True] * 4
    y = [True, True, False, False]
    out = Q.cluster_permutation_p(strata, x, y, n_perm=500, seed=2)
    assert out["n_variable_clusters"] == 0
    assert out["p_one_sided"] == pytest.approx(1.0)


def test_cluster_permutation_mismatched_input_is_none_not_crash():
    out = Q.cluster_permutation_p(["A", "B"], [True], [True, False], n_perm=10)
    assert out["p_one_sided"] is None


def test_per_cluster_tables_partition_the_pooled_table():
    ws = [win([(1.5e-4, 4)], finalized=1.5e-4, ticker="KXAPERP"),
          win([(0.0, 4)], finalized=0.0, ticker="KXAPERP", ft="2026-07-21T12:00:00Z"),
          win([(1.5e-4, 4)], finalized=0.0, ticker="KXBPERP")]
    rows = Q.per_cluster_tables(ws, lambda w: w.ticker)
    assert [r["cluster"] for r in rows] == ["KXAPERP", "KXBPERP"]
    assert sum(r["a"] for r in rows) == 1
    assert sum(r["b"] for r in rows) == 1
    assert sum(r["n"] for r in rows) == 3
    assert all(0.0 <= r["p_fisher_two_sided"] <= 1.0 for r in rows)


# =========================================================================== #
# === correction === framing guards
# =========================================================================== #
def test_class_wide_falsifier_marks_sparse_counterexamples_as_density_confounded():
    """An 'all-zero path' seen ONCE is not evidence the path was all-zero."""
    ws = [win([(0.0, 8), (0.0, 2)], finalized=0.0),
          win([(0.0, 5)], finalized=1.4e-4, ticker="KXSPARSEPERP")]
    cf = Q.class_wide_falsifier(ws)
    assert cf["class_falsified"] is True          # the raw flag still fires...
    assert cf["counterexamples_all_sparse"] is True   # ...but is flagged as confounded
    assert cf["n_counterexamples_dense_ge3_samples"] == 0
    assert cf["max_counterexample_samples"] == 1


def test_class_wide_falsifier_dense_counterexample_is_not_sparse_flagged():
    ws = [win([(0.0, 8), (0.0, 2)], finalized=0.0),
          win([(0.0, 8), (0.0, 4), (0.0, 1)], finalized=1.4e-4, ticker="KXDENSEPERP")]
    cf = Q.class_wide_falsifier(ws)
    assert cf["counterexamples_all_sparse"] is False
    assert cf["n_counterexamples_dense_ge3_samples"] == 1


def test_analyze_reports_both_naive_and_cluster_robust_p_never_naive_alone():
    """The naive key is RENAMED so it cannot be quoted as if it were the honest p."""
    recs = [
        est_row("KXAPERP", FT, 0.0, "2026-07-20T04:00:00Z"),
        est_row("KXAPERP", FT, -1.4e-4, "2026-07-20T10:00:00Z"),
        est_row("KXBPERP", FT, 0.0, "2026-07-20T04:00:00Z"),
        fr_envelope("recent", [pr("KXAPERP", FT, -1.6e-4), pr("KXBPERP", FT, 0.0)]),
    ]
    ind = Q.analyze(recs, n_perm=200, seed=1)["independence"]
    assert "p_fisher_two_sided" not in ind, "the bare naive key must not come back"
    assert ind["p_fisher_two_sided_NAIVE_pseudoreplicated"] is not None
    assert ind["cluster_permutation_by_ticker"]["p_one_sided"] is not None
    assert ind["cluster_permutation_by_funding_time"]["p_one_sided"] is not None
    assert len(ind["per_ticker_tables"]) == 2


def test_analyze_emits_density_stratification_for_every_candidate_g():
    recs = [
        est_row("KXAPERP", FT, 0.0, "2026-07-20T04:00:00Z"),
        est_row("KXAPERP", FT, -1.4e-4, "2026-07-20T10:00:00Z"),
        fr_envelope("recent", [pr("KXAPERP", FT, -1.6e-4)]),
    ]
    rep = Q.analyze(recs, n_perm=100, seed=1)
    for gname in Q.CANDIDATE_GS:
        blk = rep["per_g"][gname]
        assert blk["density_stratified_discriminating"], gname
        assert "density_monotonicity" in blk
        assert "misclassification_density_contrast" in blk


def test_correction_constants_are_pinned():
    assert Q.MIN_SAMPLE_STRATA == (1, 2, 3, 4, 5, 8)
    assert Q.MAX_LEAD_STRATA_HOURS == (0.75, 1.0, 2.0)
    assert Q.N_PERMUTATIONS == 200_000
    assert Q.PERMUTATION_SEED == 20260724


def test_module_carries_the_undecidable_verdict_not_falsified():
    """The corrected headline must live in the SCRIPT, not only in the writeup."""
    src = (ROOT / "scripts" / "q42_funding_estimate_path_inference.py").read_text()
    assert "UNDECIDABLE" in src
    assert "H1 is FALSIFIED" not in src


def test_parse_iso_utc_handles_the_tape_grammars():
    """Both grammars this family emits: bare-'Z' funding_time and an offset captured_at."""
    a = Q.parse_iso_utc("2026-07-20T12:00:00Z")
    b = Q.parse_iso_utc("2026-07-17T01:00:32.634200+00:00")
    assert a == datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    assert b.tzinfo is not None and b.year == 2026


# =========================================================================== #
# === correction round 2 === (2026-07-24, SECOND independent verifier)
#
# The verdict (H1 UNDECIDABLE) survived, but four things in round 1 did not:
#   * the leave-one-out claim was in the WRITEUP with no shipped code behind it
#     (CLAUDE.md trust default) -> Q.leave_one_out_gap_scan
#   * `gap_is_monotone_in_density` is a TAUTOLOGY for nested subsets, and round 1's
#     docstring claimed the opposite -> pinned as a tautology here, with
#     Q.random_subset_hard_gap_rate as the statistic that actually discriminates
#   * the failures-vs-successes contrast holds on LEAD but NOT on sample count
#     -> Q.failure_density_permutation reports the two axes separately
#   * the strata are a searched family of 9 -> Q.bonferroni
# =========================================================================== #
def _loo_fixture():
    """4 windows: gap is destroyed by exactly ONE window (the 'outlier' whose |g| sits on
    the wrong side). Dropping it restores a hard gap; dropping anything else does not."""
    return [
        win([(3e-5, 1.0)], finalized=0.0, ticker="KXAPERP", ft="2026-07-20T12:00:00Z"),
        win([(4e-5, 1.0)], finalized=0.0, ticker="KXBPERP", ft="2026-07-20T12:00:00Z"),
        win([(3e-4, 1.0)], finalized=0.0, ticker="KXCPERP", ft="2026-07-20T20:00:00Z"),  # outlier
        win([(2e-4, 1.0)], finalized=2e-4, ticker="KXDPERP", ft="2026-07-20T20:00:00Z"),
    ]


def test_leave_one_out_drop_count_is_tickers_plus_funding_times_plus_windows():
    """The decomposition round 1's finding got wrong (it wrote '13 tickers + 22
    funding_times + 42 windows', which sums to 77, not 67). The drops are over the
    DISCRIMINATING population's OWN distinct keys, never the full join's."""
    loo = Q.leave_one_out_gap_scan(_loo_fixture(), Q.g_last)
    assert loo["n_tickers_dropped"] == 4          # 4 distinct tickers
    assert loo["n_funding_times_dropped"] == 2    # only 2 distinct funding_times
    assert loo["n_windows_dropped"] == 4
    assert loo["n_drops"] == 4 + 2 + 4 == loo["n_tickers_dropped"] \
        + loo["n_funding_times_dropped"] + loo["n_windows_dropped"]


def test_leave_one_out_finds_the_single_row_that_restores_a_hard_gap():
    ws = _loo_fixture()
    assert Q.best_threshold([abs(Q.g_last(w)) for w in ws],
                            [w.finalized_is_zero for w in ws])["hard_gap"] is False
    loo = Q.leave_one_out_gap_scan(ws, Q.g_last)
    assert loo["pooled_gap_width"] < 0
    assert loo["n_drops_restoring_hard_gap"] >= 1
    assert any(d["dropped"].startswith("KXCPERP") or d["dropped"] == "KXCPERP"
               for d in loo["restoring_drops"])
    assert loo["max_gap_width_over_drops"] > 0


def test_leave_one_out_single_class_drop_is_undefined_not_a_restoration():
    """Dropping the only finalized-nonzero window leaves one class: the gap is UNDEFINED
    (None) and must be counted as such, never scored as a hard gap."""
    ws = [win([(3e-5, 1.0)], finalized=0.0, ticker="KXAPERP"),
          win([(2e-4, 1.0)], finalized=2e-4, ticker="KXBPERP")]
    loo = Q.leave_one_out_gap_scan(ws, Q.g_last)
    assert loo["n_drops_gap_undefined"] >= 1
    undefined = [d for d in loo["restoring_drops"] if d["gap_width"] is None]
    assert undefined == []


def test_gap_monotonicity_is_a_tautology_on_any_nested_chain():
    """ROUND-2: `gap(S) = min{|g| | fin!=0} - max{|g| | fin==0}`. For nested S' subset S the
    min can only RISE and the max can only FALL, so gap(S') >= gap(S) for ANY data. The
    `min_samples` strata are exactly such a chain, so the flag is guaranteed True and
    carries ZERO information. Pinned over random nested chains so nobody re-reads it as
    evidence."""
    rng = random.Random(20260724)
    for _ in range(200):
        n = rng.randint(8, 40)
        pop = [(rng.random(), rng.random() < 0.6) for _ in range(n)]
        chain = list(pop)
        prev = None
        while len(chain) >= 4:
            sep = Q.best_threshold([a for a, _ in chain], [z for _, z in chain])
            gap = sep["gap_width"]
            if gap is not None and prev is not None:
                assert gap >= prev - 1e-15, "nested subset gap must be non-decreasing"
            if gap is not None:
                prev = gap
            chain = rng.sample(chain, len(chain) - 2)   # strictly nested-by-cardinality


def test_gap_monotonicity_flag_is_labelled_tautological_and_conjunct_is_inert():
    mono = Q.gap_is_monotone_in_density(
        Q.density_stratified_separation(_staleness_fixture(), Q.g_last))
    assert mono["monotone_is_tautological_for_nested_chains"] is True
    assert mono["density_confound_flag_is_effectively_bool_hard"] is True
    # the `and mono` conjunct never binds: the flag equals bool(strata_with_hard_gap)
    assert mono["pooled_overlap_is_density_confounded"] == bool(mono["strata_with_hard_gap"])


def test_random_subset_baseline_is_one_on_a_perfectly_separable_population():
    ws = [win([(1e-5 * i, 1.0)], finalized=0.0, ticker=f"KXZ{i}PERP") for i in range(1, 6)]
    ws += [win([(1e-3 * i, 1.0)], finalized=1e-3 * i, ticker=f"KXN{i}PERP") for i in range(1, 6)]
    base = Q.random_subset_hard_gap_rate(ws, Q.g_last, size=4, n_draws=500, seed=1)
    assert base["p_hard_gap"] + base["n_single_class_draws"] / 500 == pytest.approx(1.0)


def test_random_subset_baseline_is_seeded_and_reproducible():
    ws = _staleness_fixture()
    a = Q.random_subset_hard_gap_rate(ws, Q.g_last, size=4, n_draws=300, seed=7)
    b = Q.random_subset_hard_gap_rate(ws, Q.g_last, size=4, n_draws=300, seed=7)
    c = Q.random_subset_hard_gap_rate(ws, Q.g_last, size=4, n_draws=300, seed=8)
    assert a == b
    assert c["size"] == 4 and 0.0 <= c["p_hard_gap"] <= 1.0


def test_random_subset_baseline_size_out_of_range_is_none_not_crash():
    ws = _staleness_fixture()
    out = Q.random_subset_hard_gap_rate(ws, Q.g_last, size=999, n_draws=10, seed=1)
    assert out["p_hard_gap"] is None and "note" in out


def test_permutation_mean_diff_detects_a_real_shift_and_a_null():
    shifted = Q.permutation_mean_diff_p([10.0] * 8, [1.0] * 8, n_perm=2000, seed=1)
    assert shifted["observed_diff"] == pytest.approx(9.0)
    assert shifted["p_one_sided"] < 0.01
    null = Q.permutation_mean_diff_p([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0],
                                     n_perm=2000, seed=1)
    assert null["observed_diff"] == pytest.approx(0.0)
    assert null["p_one_sided"] > 0.5


def test_permutation_mean_diff_p_is_add_one_and_never_zero():
    out = Q.permutation_mean_diff_p([100.0] * 5, [0.0] * 5, n_perm=200, seed=3)
    assert out["p_one_sided"] == pytest.approx(1 / 201)
    assert out["p_one_sided"] > 0


def test_permutation_mean_diff_empty_group_is_none_not_crash():
    out = Q.permutation_mean_diff_p([], [1.0, 2.0], n_perm=10, seed=1)
    assert out["p_one_sided"] is None and out["observed_diff"] is None


def test_failure_density_permutation_reports_lead_and_samples_separately():
    """ROUND-2: the two axes are DIFFERENT measurements and must not be headlined as one.
    Fixture: failures are much staler but have the SAME sample count as successes, so the
    lead axis moves and the sample-count axis cannot."""
    fails = [win([(3e-4, 5.0), (3e-4, 4.9)], finalized=0.0, ticker=f"KXF{i}PERP")
             for i in range(4)]
    oks = [win([(3e-5, 0.4), (3e-5, 0.3)], finalized=0.0, ticker=f"KXO{i}PERP")
           for i in range(8)]
    out = Q.failure_density_permutation(fails + oks, Q.g_last, n_perm=2000, seed=1)
    assert out["n_failures"] == 4 and out["n_successes"] == 8
    assert out["last_lead_hours"]["observed_diff"] > 4.0
    assert out["last_lead_hours"]["p_one_sided"] < 0.05
    assert out["n_samples"]["observed_diff"] == pytest.approx(0.0)
    assert out["n_samples"]["p_one_sided"] > 0.5


def test_bonferroni_over_the_searched_cut_family():
    """ROUND-2: 9 cuts were searched (6 min_samples + 3 max_lead). Neither dense cut's p
    survives the correction — which STRENGTHENS the UNDECIDABLE verdict."""
    assert Q.N_POSTHOC_CUTS_SEARCHED == 9
    assert Q.bonferroni(1 / 91) == pytest.approx(0.0989, abs=5e-4)     # lead<=0.75h
    assert Q.bonferroni(1 / 11) == pytest.approx(0.818, abs=5e-3)      # n>=8
    assert Q.bonferroni(1 / 11) > 0.05 and Q.bonferroni(1 / 91) > 0.05
    assert Q.bonferroni(0.5) == 1.0                                    # clamped at 1
    assert Q.bonferroni(None) is None


def test_strata_rows_carry_the_multiplicity_corrected_p():
    rows = Q.density_stratified_separation(_staleness_fixture(), Q.g_last)
    key = "exact_p_bonferroni_%d_cuts" % Q.N_POSTHOC_CUTS_SEARCHED
    for r in rows:
        assert key in r and r["n_posthoc_cuts_searched"] == 9
        if r["exact_p_if_hard_gap"] is None:
            assert r[key] is None
        else:
            assert r[key] == pytest.approx(min(1.0, r["exact_p_if_hard_gap"] * 9))


def test_analyze_emits_the_round2_outputs():
    recs = [
        est_row("KXAPERP", FT, 0.0, "2026-07-20T04:00:00Z"),
        est_row("KXAPERP", FT, -1.4e-4, "2026-07-20T10:00:00Z"),
        fr_envelope("recent", [pr("KXAPERP", FT, -1.6e-4)]),
    ]
    rep = Q.analyze(recs, n_perm=100, seed=1, n_subset_draws=50)
    assert rep["n_posthoc_cuts_searched"] == 9
    assert "failure_density_permutation_g_last" in rep
    for gname in Q.CANDIDATE_GS:
        blk = rep["per_g"][gname]
        assert "leave_one_out" in blk, gname
        assert "matched_size_random_subset_baseline" in blk, gname


# --------------------------------------------------------------------------- #
# TAPE-PINNED (read-only, offline, committed tape) — the two round-2 MANDATORY
# numbers. Skipped, never silently passed, if the committed tape is absent.
#
# 2026-07-27 GATE REPAIR — THE FROZEN TAPE SLICE (L140-class time bomb).
# ----------------------------------------------------------------------------
# These tests originally globbed `tape/perp_tape/dt=*.jsonl` — OPEN-ENDED over a LIVE,
# STILL-GROWING collected family. `perp_tape` gained dt=2026-07-25/26/27 after the
# 2026-07-24 finding was written, which changed the POPULATION the pinned statistics
# describe, so the pins went red on `main` with no code change anywhere:
#
#   statistic                     2026-07-24 (dt=17..24)   2026-07-27 (dt=*, 17..27)
#   n_joined_windows                     286                       364
#   n_discriminating (LOO n_windows)      42                        58
#   LOO n_tickers_dropped                  7                         8
#   LOO n_funding_times_dropped           18                        23
#   LOO n_drops                           67                        89
#   p_hard_gap(size=11, 20k draws)     0.2057                    0.3655
#   p_hard_gap(size=14, 20k draws)     0.1042                    0.2390
#
# DIAGNOSIS (2026-07-27, this repair): the day-files that existed at the finding commit
# cebe691 — dt=2026-07-17 .. dt=2026-07-24 — are BYTE-IDENTICAL between cebe691 and HEAD
# (verified blob-by-blob with `git rev-parse <rev>:<path>`), and
# `scripts/q42_funding_estimate_path_inference.py` is likewise byte-identical. The
# stranded-tape recovery in ac8a758 union-appended only into `dt=2026-07-27.jsonl` within
# this family, i.e. it added a NEW day, it did not mutate an old one. So the drift is
# PURELY TAPE GROWTH: restricted to the frozen slice below, all four tape pins reproduce
# EXACTLY (67 / 7 / 18 / 42, p11=0.20565, p14=0.10420). NOTHING WAS RE-PINNED — no
# number in this file moved; the population was made explicit instead.
#
# The slice is the exact `dt=` day set committed at cebe691 (2026-07-24), which is what
# `findings/2026-07-24-q42-funding-estimate-path-inference.md` was computed over. Every
# member is a CLOSED, append-only historical day-file. Do NOT extend it to keep pace with
# the collector: a statistic pinned to a growing population is not a reproducible claim.
# Re-measuring Q42 on more tape is a NEW milestone with its OWN dated numbers, not an
# edit to these constants.
# --------------------------------------------------------------------------- #
_TAPE_DIR = ROOT / "tape" / "perp_tape"
_real_tape = pytest.mark.skipif(not _TAPE_DIR.is_dir(),
                                reason="committed tape/perp_tape/ not present")

#: The `dt=` days committed at cebe691 (the 2026-07-24 Q42 part-1-residual finding).
_FROZEN_TAPE_SLICE_DAYS = (
    "2026-07-17", "2026-07-18", "2026-07-19", "2026-07-20",
    "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24",
)


def _frozen_tape_paths():
    """The frozen slice's day-file paths, in order. Never a glob."""
    return [_TAPE_DIR / ("dt=%s.jsonl" % d) for d in _FROZEN_TAPE_SLICE_DAYS]


def _load_frozen_tape():
    """All records in the frozen slice. Read-only; a missing member is NOT silently
    skipped-over as an empty file — `test_frozen_tape_slice_is_intact` names it."""
    recs = []
    for p in _frozen_tape_paths():
        recs.extend(Q.load_records(str(p)))
    return recs


def _tape_discriminating():
    recs = _load_frozen_tape()
    ests = Q.collect_funding_estimates(recs)
    idx, _ = Q.collect_finalized_prints(recs)
    wins, _ = Q.build_windows(Q.group_estimates(ests), idx)
    return [w for w in wins if w.has_nonzero_estimate]


@_real_tape
def test_frozen_tape_slice_is_intact_and_its_population_is_unchanged():
    """The RATCHET behind the frozen slice: if a future stranded-line recovery ever
    union-appends into one of these eight CLOSED day-files (the failure mode this repair
    checked for and did NOT find), the pinned statistics below would move silently. This
    test fires first, with the population cell that moved, instead.

    The eight cells are `Q.EXPECTED_INTEGRITY`, which the writeup and the probe's own
    integrity gate both quote — so drift here is drift in the published claim."""
    missing = [p.name for p in _frozen_tape_paths() if not p.is_file()]
    assert missing == [], "frozen tape slice is incomplete: %s" % missing

    recs = _load_frozen_tape()
    assert len(recs) == 1667, "frozen-slice record count moved (old day-file mutated?)"

    ests = Q.collect_funding_estimates(recs)
    idx, _ = Q.collect_finalized_prints(recs)
    wins, _ = Q.build_windows(Q.group_estimates(ests), idx)
    disc = [w for w in wins if w.has_nonzero_estimate]
    observed = {
        "n_estimate_groups": len(Q.group_estimates(ests)),
        "n_finalized_prints_dedup": len(idx),
        "n_joined_windows": len(wins),
        "n_joined_tickers": len({w.ticker for w in wins}),
        "n_joined_funding_times": len({w.funding_time for w in wins}),
        "n_joined_ge3_samples": sum(1 for w in wins if w.n_samples >= 3),
        "n_discriminating": len(disc),
        "n_discriminating_finalized_zero": sum(1 for w in disc if w.finalized_is_zero),
    }
    assert observed == Q.EXPECTED_INTEGRITY


@_real_tape
def test_tape_leave_one_out_67_drops_decomposes_as_7_18_42():
    """MANDATORY round-2 fix: 67 = 7 DISCRIMINATING tickers + 18 DISCRIMINATING
    funding_times + 42 windows. Round 1's finding wrote '13 + 22 + 42' = 77.

    Over the FROZEN SLICE (dt=2026-07-17..24). On today's full dt=* glob the same code
    gives 89 = 8 + 23 + 58 — a POPULATION change from three more collected days, not a
    code change; see the frozen-slice block above."""
    loo = Q.leave_one_out_gap_scan(_tape_discriminating(), Q.g_last)
    assert loo["n_windows"] == 42
    assert loo["n_tickers_dropped"] == 7
    assert loo["n_funding_times_dropped"] == 18
    assert loo["n_windows_dropped"] == 42
    assert loo["n_drops"] == 67


@_real_tape
def test_tape_no_leave_one_out_drop_restores_a_hard_gap():
    loo = Q.leave_one_out_gap_scan(_tape_discriminating(), Q.g_last)
    assert loo["n_drops_restoring_hard_gap"] == 0
    assert loo["restoring_drops"] == []
    assert loo["n_drops_gap_undefined"] == 0


@_real_tape
def test_tape_leave_one_out_max_gap_is_still_negative():
    """The most favourable single drop still leaves the gap at -2.8216e-05 — i.e. the
    pooled overlap is not an outlier artifact (it is a DENSITY artifact)."""
    loo = Q.leave_one_out_gap_scan(_tape_discriminating(), Q.g_last)
    assert loo["max_gap_width_over_drops"] == pytest.approx(-2.8216e-05, rel=1e-3)
    assert loo["max_gap_width_over_drops"] < 0
    assert loo["pooled_gap_width"] == pytest.approx(-1.3016e-04, rel=1e-3)


@_real_tape
def test_tape_random_same_size_subsets_reproduce_the_dense_cuts_hard_gap():
    """ROUND-2: the statistic that replaces the tautological monotonicity flag. A hard gap
    on 11 of 42 happens ~20% of the time at RANDOM, and on 14 of 42 ~10% — so neither
    post-hoc dense cut beats an arbitrary same-size cut.

    Over the FROZEN SLICE (dt=2026-07-17..24): p11 = 0.20565, p14 = 0.10420 at 20,000
    draws, seed PERMUTATION_SEED. The `abs=0.02` tolerance is the Monte-Carlo band for a
    20k-draw binomial (se = sqrt(p(1-p)/20000) ~= 0.0029 at p=0.2, so 0.02 is ~7 se) —
    it is NOT slack for population drift. On today's full dt=* glob (58 discriminating
    windows, not 42) the same code gives p11 = 0.3655 / p14 = 0.2390; those are ~55 se
    and ~47 se away, i.e. a POPULATION change, and widening the tolerance to absorb them
    would have been papering over it."""
    disc = _tape_discriminating()
    p11 = Q.random_subset_hard_gap_rate(disc, Q.g_last, size=11, n_draws=20_000,
                                        seed=Q.PERMUTATION_SEED)["p_hard_gap"]
    p14 = Q.random_subset_hard_gap_rate(disc, Q.g_last, size=14, n_draws=20_000,
                                        seed=Q.PERMUTATION_SEED)["p_hard_gap"]
    assert p11 == pytest.approx(0.205, abs=0.02)
    assert p14 == pytest.approx(0.104, abs=0.02)
    assert p11 > 0.05 and p14 > 0.05    # neither dense cut is rare among same-size cuts
