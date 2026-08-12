"""Offline tests for scripts/q51_queue_aware_fillsim.py (L337 queue-aware discount).

No network. The `test_acceptance_*` cases read the COMMITTED, FROZEN dt=2026-08-03 slice of
`tape/orderbook_depth/` + `tape/kalshi_trades/` and the FROZEN settlement snapshot
`tape/q51_settlement_cache/settlement-m3-2026-08-10.json` (L191/L284/L325 — never the mutable
`settlement.json`, which a later sweep overwrites) and hard-assert rather than skip.

The deterministic counts (294 / 116 legs, 64 -> 25 fills, 51 / 25 units, 24 -> 14 informative
units) are asserted EXACTLY: they are set arithmetic over a frozen tape, not bootstrap draws.
The means/CIs are asserted with a small absolute tolerance, since a resample sequence can
wobble in the last digits across numpy/platform versions.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

from core.pricing import MAKER_FEE_RATE, TAKER_FEE_RATE
from scripts import q51_maker_fillsim as M
from scripts import q51_queue_aware_fillsim as Q

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: the milestone-3 numbers are pinned at the module's own defaults
N_BOOT = 10000
SEED = 42
TOL = 5e-5


@pytest.fixture(scope="module")
def report_rows():
    """One full-fat run (n_boot=10000, seed=42) shared by every acceptance case."""
    return Q.run(n_boot=N_BOOT, seed=SEED)


# --------------------------------------------------------------------------- #
# ladders: own-side, float sizes (L47)
# --------------------------------------------------------------------------- #
def test_levels_keep_fractional_sizes_as_floats_never_int_coerced_l47():
    lv = Q._levels([[0.31, 91316.82], [0.29, 3144.0]])
    assert lv == [(0.31, 91316.82), (0.29, 3144.0)]
    assert isinstance(lv[0][1], float)


def test_levels_skips_malformed_entries():
    assert Q._levels(None) == []
    assert Q._levels([[0.5], ["x", 1.0], [0.5, "y"], [0.4, 12.5]]) == [(0.4, 12.5)]


def test_resting_size_at_returns_the_level_size_or_none():
    lv = [(0.67, 2320.0), (0.65, 1500.5)]
    assert Q.resting_size_at(lv, 0.65) == 1500.5
    assert Q.resting_size_at(lv, 0.66) is None
    assert Q.resting_size_at([], 0.65) is None


def test_own_side_ladder_reads_the_no_ladder_for_a_no_bid_never_the_mirrored_yes_level():
    ladder = {"yes_bids": [(0.65, 11.0)], "no_bids": [(0.35, 22.0)]}
    assert Q.own_side_ladder(ladder, "yes_bid") == [(0.65, 11.0)]
    assert Q.own_side_ladder(ladder, "no_bid") == [(0.35, 22.0)]
    # a NO bid at 0.35 mirrors to a YES quote at 0.65 — its SIZE must NOT be read there
    assert Q.resting_size_at(Q.own_side_ladder(ladder, "no_bid"), 0.35) == 22.0
    assert Q.resting_size_at(Q.own_side_ladder(ladder, "no_bid"), 0.65) is None


# --------------------------------------------------------------------------- #
# qualifying volume: the HEADLINE predicate, applied to every print
# --------------------------------------------------------------------------- #
def _pr(ts, price, side, count, tid="tid"):
    return {"ts": ts, "yes_price": price, "taker_book_side": side, "trade_id": tid,
            "count": count}


def test_qualifying_volume_sums_every_qualifying_print_not_only_the_crediting_one():
    prints = [_pr(1, 0.55, M.TAKER_SELLS, 10.0, "a"), _pr(2, 0.58, M.TAKER_SELLS, 4.5, "b")]
    vq = Q.qualifying_volume(prints, 0, 10, "yes_bid", 0.60)
    assert vq["volume"] == pytest.approx(14.5)
    assert vq["n_prints"] == 2
    assert vq["crediting"] == 10.0     # the earliest — what the headline credits the fill to
    assert vq["largest"] == 10.0


def test_qualifying_volume_excludes_wrong_side_out_of_window_and_through_price_misses():
    prints = [
        _pr(5, 0.55, M.TAKER_BUYS, 100.0, "wrong-side"),   # a BUYER cannot hit a resting bid
        _pr(0, 0.55, M.TAKER_SELLS, 100.0, "at t0"),       # window is left-OPEN
        _pr(11, 0.55, M.TAKER_SELLS, 100.0, "after t1"),
        _pr(6, 0.61, M.TAKER_SELLS, 100.0, "above price"),
        _pr(7, 0.60, M.TAKER_SELLS, 3.0, "at price"),
    ]
    vq = Q.qualifying_volume(prints, 0, 10, "yes_bid", 0.60)
    assert vq["volume"] == pytest.approx(3.0) and vq["n_prints"] == 1


def test_qualifying_volume_for_a_no_bid_uses_the_no_side_orientation():
    # a NO bid at 0.35 is a YES offer at 0.65, lifted by a BUYING taker
    prints = [_pr(5, 0.70, M.TAKER_BUYS, 2.0), _pr(6, 0.64, M.TAKER_BUYS, 9.0),
              _pr(7, 0.70, M.TAKER_SELLS, 9.0)]
    vq = Q.qualifying_volume(prints, 0, 10, "no_bid", 0.35)
    assert vq["volume"] == pytest.approx(2.0) and vq["n_prints"] == 1


def test_qualifying_volume_is_empty_without_prints():
    vq = Q.qualifying_volume([], 0, 10, "yes_bid", 0.60)
    assert vq == {"volume": 0.0, "n_prints": 0.0, "largest": 0.0, "crediting": 0.0}


def test_qualifying_prints_agree_with_the_headline_predicate_by_construction():
    """The rule reuses `M.yes_bid_fill`; the crediting print must BE the headline's fill."""
    prints = [_pr(3, 0.50, M.TAKER_SELLS, 1.0, "early"),
              _pr(7, 0.50, M.TAKER_SELLS, 1.0, "late")]
    qs = Q.qualifying_prints(prints, 0, 10, "yes_bid", 0.60)
    assert [p["trade_id"] for p in qs] == ["early", "late"]
    assert qs[0]["trade_id"] == M.yes_bid_fill(prints, 0, 10, 0.60)["trade_id"]


# --------------------------------------------------------------------------- #
# the size gate
# --------------------------------------------------------------------------- #
def test_clears_queue_boundary_is_inclusive():
    """The >= / > boundary is load-bearing: on the committed slice strict `>` gives 24 fills
    (8.163%, mean +0.002449), not the 25 (8.503%, +0.000714) L337 records."""
    assert Q.clears_queue(500.0, 500.0) is True
    assert Q.clears_queue(500.0 - 1e-6, 500.0) is False
    assert Q.clears_queue(501.0, 500.0) is True


def test_clears_queue_treats_a_missing_price_level_as_not_filled():
    assert Q.clears_queue(10.0 ** 9, None) is False


# --------------------------------------------------------------------------- #
# discounting rows
# --------------------------------------------------------------------------- #
def _row(**kw):
    base = {"ticker": "KXTESTGAME-26AUG03AB-A", "game": "KXTESTGAME-26AUG03AB",
            "series": "KXTESTGAME", "side": "yes_bid", "entry_captured_at": "t0",
            "next_captured_at": "t1", "rest_price": 0.60, "price_source_tag": "real_bid",
            "interval_covered": True, "filled": True, "fill_trade_id": "x",
            "fill_price_source_tag": "broker_truth", "settle_result": "yes", "won": True,
            "pnl": 0.39}
    base.update(kw)
    return base


_T0 = "2026-08-03T00:00:00+00:00"
_T1 = "2026-08-03T01:00:00+00:00"


def _ctx(resting, prints):
    ladders = {("KXTESTGAME-26AUG03AB-A", _T0): {"yes_bids": [(0.60, resting)],
                                                 "no_bids": [(0.38, resting)]}}
    return ladders, {"KXTESTGAME-26AUG03AB-A": prints}


def test_a_headline_fill_smaller_than_the_queue_is_discounted_to_no_fill_and_zero_pnl():
    ts = M.parse_ts(_T0) + 60
    ladders, prints = _ctx(500.0, [_pr(ts, 0.55, M.TAKER_SELLS, 8.0)])
    rows, prof = Q.apply_queue_discount(
        [_row(entry_captured_at=_T0, next_captured_at=_T1)], ladders, prints)
    r = rows[0]
    assert r["headline_filled"] is True and r["queue_aware_filled"] is False
    assert r["filled"] is False and r["pnl"] == 0.0
    assert r["fill_trade_id"] is None and r["headline_fill_trade_id"] == "x"
    assert r["resting_size_ahead"] == 500.0 and r["qualifying_volume"] == 8.0
    assert prof["n_headline_fills"] == 1 and prof["n_queue_aware_fills"] == 0


def test_cumulative_volume_across_several_prints_can_clear_the_queue():
    t = M.parse_ts(_T0)
    ladders, prints = _ctx(10.0, [_pr(t + 60, 0.55, M.TAKER_SELLS, 4.0),
                                  _pr(t + 90, 0.55, M.TAKER_SELLS, 6.0)])
    rows, prof = Q.apply_queue_discount(
        [_row(entry_captured_at=_T0, next_captured_at=_T1)], ladders, prints)
    assert rows[0]["queue_aware_filled"] is True and rows[0]["pnl"] == pytest.approx(0.39)
    assert rows[0]["fill_trade_id"] == "x" and rows[0]["n_qualifying_prints"] == 2
    # neither single print would have cleared it
    assert prof["n_headline_fills_cleared_by_the_crediting_print"] == 0
    assert prof["n_headline_fills_cleared_by_the_largest_single_print"] == 0


def test_an_unfilled_headline_leg_is_never_promoted_even_at_zero_resting_size():
    """0 >= 0 must not fabricate a fill: the size gate only ever removes one (rule 4)."""
    ladders, prints = _ctx(0.0, [])
    rows, prof = Q.apply_queue_discount(
        [_row(entry_captured_at=_T0, next_captured_at=_T1, filled=False, pnl=0.0,
              fill_trade_id=None, fill_price_source_tag=None, won=None)], ladders, prints)
    assert rows[0]["queue_aware_filled"] is False and rows[0]["filled"] is False
    assert prof["n_headline_fills"] == 0 and prof["n_queue_aware_fills"] == 0


def test_a_missing_entry_price_level_is_counted_and_scored_unfilled():
    ts = M.parse_ts(_T0) + 60
    ladders = {("KXTESTGAME-26AUG03AB-A", _T0): {"yes_bids": [(0.59, 1.0)], "no_bids": []}}
    prints = {"KXTESTGAME-26AUG03AB-A": [_pr(ts, 0.55, M.TAKER_SELLS, 10.0 ** 6)]}
    rows, prof = Q.apply_queue_discount(
        [_row(entry_captured_at=_T0, next_captured_at=_T1)], ladders, prints)
    assert rows[0]["queue_aware_filled"] is False
    assert rows[0]["resting_size_ahead"] is None
    assert prof["n_entry_price_level_missing"] == 1


def test_apply_queue_discount_copies_rows_and_never_mutates_the_headline_rows():
    ts = M.parse_ts(_T0) + 60
    ladders, prints = _ctx(500.0, [_pr(ts, 0.55, M.TAKER_SELLS, 8.0)])
    src = [_row(entry_captured_at=_T0, next_captured_at=_T1)]
    before = dict(src[0])
    out, _ = Q.apply_queue_discount(src, ladders, prints)
    assert src[0] == before and out[0] is not src[0]


def test_informative_units_counts_only_games_with_a_nonzero_leg():
    rows = [{"game": "G1", "pnl": 0.0}, {"game": "G1", "pnl": 0.0},
            {"game": "G2", "pnl": 0.0}, {"game": "G2", "pnl": -0.4}]
    assert Q.informative_units(rows) == 1


def test_discount_factor_reports_before_after_and_the_retained_fractions():
    head = {"n_legs": 100, "n_filled_legs": 40, "fill_rate": 0.40, "mean": 0.010,
            "ci95": [-0.1, 0.2], "n_informative_units": 20, "n_units_games": 30}
    qa = {"n_legs": 100, "n_filled_legs": 10, "fill_rate": 0.10, "mean": 0.001,
          "ci95": [-0.05, 0.06], "n_informative_units": 8, "n_units_games": 30}
    d = Q.discount_factor(head, qa)
    assert d["fills_headline"] == 40 and d["fills_queue_aware"] == 10
    assert d["fills_removed"] == 30
    assert d["fill_rate_retained_fraction"] == pytest.approx(0.25)
    assert d["mean_retained_fraction"] == pytest.approx(0.1)
    assert d["informative_units_headline"] == 20
    assert d["informative_units_queue_aware"] == 8


def test_discount_factor_is_none_safe_on_a_zero_headline():
    d = Q.discount_factor(
        {"n_legs": 0, "n_filled_legs": 0, "fill_rate": None, "mean": 0.0, "ci95": [None, None],
         "n_informative_units": 0, "n_units_games": 0},
        {"n_legs": 0, "n_filled_legs": 0, "fill_rate": None, "mean": 0.0, "ci95": [None, None],
         "n_informative_units": 0, "n_units_games": 0})
    assert d["fill_rate_retained_fraction"] is None
    assert d["mean_retained_fraction"] is None


def test_fee_rate_is_the_maker_rate_sourced_from_core_pricing_l5():
    assert Q.FEE_RATE == M.FEE_RATE == MAKER_FEE_RATE == 0.0175
    assert Q.FEE_RATE != TAKER_FEE_RATE


# --------------------------------------------------------------------------- #
# ACCEPTANCE over the committed frozen slice — the L337 target numbers
# --------------------------------------------------------------------------- #
def test_acceptance_frozen_m3_cache_is_this_scripts_default_input():
    assert Q.M3_CACHE_PATH.exists()
    assert Q.M3_CACHE_PATH.name == "settlement-m3-2026-08-10.json"
    assert Q.M3_CACHE_PATH != M.CACHE_PATH   # never the mutable live cache (L284/L325)


def test_acceptance_headline_branch_reproduces_milestone_3(report_rows):
    """HEADLINE all_intervals: legs=294 fills=64 rate=0.21769 units=51 inf=24
    mean=+0.010068 ci=[-0.0157, +0.036815]."""
    report, _rows = report_rows
    v = report["verdicts"]["headline"]["all_intervals"]
    assert v["n_legs"] == 294
    assert v["n_filled_legs"] == 64
    assert v["fill_rate"] == pytest.approx(64 / 294)
    assert v["n_units_games"] == 51
    assert v["n_informative_units"] == 24
    assert v["mean"] == pytest.approx(0.010068, abs=TOL)
    assert v["ci95"][0] == pytest.approx(-0.015700, abs=TOL)
    assert v["ci95"][1] == pytest.approx(0.036815, abs=TOL)


def test_acceptance_queue_aware_all_intervals_is_the_l337_discount(report_rows):
    """QUEUE-AWARE all_intervals: legs=294 fills=25 rate=0.08503 units=51 inf=14
    mean=+0.000714 ci=[-0.010387, +0.012823]."""
    report, _rows = report_rows
    v = report["verdicts"]["queue_aware"]["all_intervals"]
    assert v["n_legs"] == 294
    assert v["n_filled_legs"] == 25
    assert v["fill_rate"] == pytest.approx(25 / 294)
    assert v["n_units_games"] == 51
    assert v["n_informative_units"] == 14        # still above the L41 floor of 10
    assert v["mean"] == pytest.approx(0.000714, abs=TOL)
    assert v["ci95"][0] == pytest.approx(-0.010387, abs=TOL)
    assert v["ci95"][1] == pytest.approx(0.012823, abs=TOL)


def test_acceptance_queue_aware_covered_intervals(report_rows):
    """QUEUE-AWARE covered_intervals: legs=116 fills=25 rate=0.21552 units=25 inf=14
    mean=+0.001810 ci=[-0.02675, +0.03161]."""
    report, _rows = report_rows
    v = report["verdicts"]["queue_aware"]["covered_intervals"]
    assert v["n_legs"] == 116
    assert v["n_filled_legs"] == 25
    assert v["fill_rate"] == pytest.approx(25 / 116)
    assert v["n_units_games"] == 25
    assert v["n_informative_units"] == 14
    assert v["mean"] == pytest.approx(0.001810, abs=TOL)
    assert v["ci95"][0] == pytest.approx(-0.026750, abs=TOL)
    assert v["ci95"][1] == pytest.approx(0.031610, abs=TOL)


def test_acceptance_both_branches_are_bootstrapped_independently_not_rescaled(report_rows):
    """The two branches are each run through `verdict_for` over their OWN unit population.

    Honest qualifier, pinned rather than hidden: every uncovered leg contributes an exact
    0.0, so the two POINT ESTIMATES are related by the leg-count ratio as an arithmetic
    identity (`block_bootstrap`'s `mean` is the pooled grand mean) — exactly the zero-
    inflation identity the headline module pins. The CIs are NOT: they come from resampling
    51 units vs 25 units, so they cannot be obtained by rescaling one another.
    """
    report, rows = report_rows
    allv = report["verdicts"]["queue_aware"]["all_intervals"]
    cov = report["verdicts"]["queue_aware"]["covered_intervals"]
    assert cov["n_units_games"] == 25 and allv["n_units_games"] == 51
    assert sum(r["pnl"] for r in rows) == pytest.approx(
        sum(r["pnl"] for r in rows if r["interval_covered"]))
    # point estimates: the identity holds (both are the same P&L sum over a different n_legs)
    assert cov["mean"] == pytest.approx(allv["mean"] * allv["n_legs"] / cov["n_legs"],
                                        abs=1e-12)
    # CIs: independently resampled, so the same rescaling does NOT reproduce them
    scale = allv["n_legs"] / cov["n_legs"]
    assert cov["ci95"][0] != pytest.approx(allv["ci95"][0] * scale, abs=1e-4)
    assert cov["ci95"][1] != pytest.approx(allv["ci95"][1] * scale, abs=1e-4)


def test_acceptance_verdict_is_still_dead_on_every_branch(report_rows):
    """The discount runs TOWARD the null. No branch may come back alive: every CI straddles
    zero and every one fails the L27 tick gate. A change here is a registry-class event."""
    report, _rows = report_rows
    for rule in ("headline", "queue_aware"):
        for br in ("all_intervals", "covered_intervals"):
            v = report["verdicts"][rule][br]
            lo, hi = v["ci95"]
            assert lo < 0.0 < hi, f"{rule}/{br} CI no longer straddles zero: {v['ci95']}"
            assert v["clears_tick_magnitude"] is False
            assert v["admissible"] is True
            assert v["verdict"].startswith("DEAD")
            assert v["fee_rate"] == MAKER_FEE_RATE
            assert v["price_source_tag"] == "real_bid"
            assert v["fill_evidence_tag"] == "broker_truth"
    assert report["verdict_class_change"] is False


def test_acceptance_discount_factor_block_states_the_upper_bound_explicitly(report_rows):
    report, _rows = report_rows
    d = report["discount_factor"]["all_intervals"]
    assert d["fills_headline"] == 64 and d["fills_queue_aware"] == 25
    assert d["fills_removed"] == 39
    assert d["fill_rate_headline"] == pytest.approx(64 / 294)
    assert d["fill_rate_queue_aware"] == pytest.approx(25 / 294)
    assert d["fill_rate_retained_fraction"] == pytest.approx(25 / 64)
    assert d["mean_retained_fraction"] == pytest.approx(0.0709, abs=1e-3)
    assert d["informative_units_headline"] == 24
    assert d["informative_units_queue_aware"] == 14


def test_acceptance_queue_depth_profile_reconciles_l337s_cited_numbers(report_rows):
    """L337 cites median resting size 500.74 vs a median filling print of 8.9, and 6.2% of
    the 64 credited fills cleared by a single print. All three reproduce here — the 6.2% is
    specifically the CREDITING (earliest qualifying) print, 4/64."""
    report, _rows = report_rows
    pf = report["queue_depth_profile"]
    assert pf["n_headline_fills"] == 64 and pf["n_queue_aware_fills"] == 25
    assert pf["n_entry_price_level_missing"] == 0
    assert pf["median_resting_size_ahead"] == pytest.approx(500.74)
    assert pf["median_crediting_print_size"] == pytest.approx(8.905)
    assert pf["median_qualifying_volume"] == pytest.approx(131.75)
    assert pf["n_headline_fills_cleared_by_the_crediting_print"] == 4
    assert pf["share_of_headline_fills_cleared_by_the_crediting_print"] == pytest.approx(
        4 / 64)
    assert pf["n_headline_fills_cleared_by_the_largest_single_print"] == 13
    assert pf["share_of_headline_fills_surviving_queue_gate"] == pytest.approx(25 / 64)


def test_acceptance_queue_aware_fills_are_a_strict_subset_of_headline_fills(report_rows):
    _report, rows = report_rows
    head = {(r["ticker"], r["side"], r["entry_captured_at"])
            for r in rows if r["headline_filled"]}
    qa = {(r["ticker"], r["side"], r["entry_captured_at"])
          for r in rows if r["queue_aware_filled"]}
    assert len(head) == 64 and len(qa) == 25
    assert qa < head


def test_acceptance_every_queue_aware_fill_still_traces_to_a_broker_truth_print(report_rows):
    report, rows = report_rows
    assert report["fill_traceability"]["all_fills_traced"] is True
    assert report["fill_traceability"]["n_fills"] == 25
    for r in rows:
        if r["queue_aware_filled"]:
            assert r["fill_trade_id"] and r["fill_price_source_tag"] == "broker_truth"
            assert r["resting_size_source_tag"] == "real_bid"
        else:
            assert r["pnl"] == 0.0 and r["fill_trade_id"] is None


def test_acceptance_strict_greater_than_would_give_a_different_answer(report_rows):
    """Pins the inclusive `>=` boundary on real tape: a strict `>` drops one more fill
    (25 -> 24). Recorded so the boundary can never be flipped as a cosmetic edit."""
    _report, rows = report_rows
    strict = [r for r in rows if r["headline_filled"]
              and r["resting_size_ahead"] is not None
              and r["qualifying_volume"] > r["resting_size_ahead"]]
    inclusive = [r for r in rows if r["queue_aware_filled"]]
    assert len(inclusive) == 25 and len(strict) == 24


def test_acceptance_report_restates_the_resolution_ceiling_and_names_the_lesson(report_rows):
    report, _rows = report_rows
    assert report["lesson"] == "L337"
    assert report["schema_version"] == "q51_queue_aware_fillsim.v1"
    assert report["settlement_cache"] == "settlement-m3-2026-08-10.json"
    ceiling = report["resolution_ceiling"].lower()
    assert "size gate" in ceiling and "no queue position" in ceiling
    assert "time-to-fill" in ceiling


# --------------------------------------------------------------------------- #
# REGRESSION: the headline module is untouched
# --------------------------------------------------------------------------- #
def test_regression_companion_never_assigns_to_the_headline_module():
    """Import-only reuse: no monkeypatching, no attribute rebinding, no setattr."""
    src = (ROOT / "scripts" / "q51_queue_aware_fillsim.py").read_text(encoding="utf-8")
    assert "setattr(" not in src
    assert not re.search(r"\bmonkeypatch\s*\.", src)   # prose mentions are fine, calls are not
    assert not re.search(r"^\s*M\.[A-Za-z_][A-Za-z_0-9]*\s*(?:\[[^\]]*\])?\s*=(?!=)",
                         src, re.M), "companion rebinds an attribute of the headline module"


def test_regression_headline_module_report_is_unchanged_in_shape_after_import():
    report, rows = M.run(n_boot=100, cache_path=Q.M3_CACHE_PATH)
    assert report["schema_version"] == "q51_maker_fillsim.v1"
    assert set(report["verdicts"]) == {"all_intervals", "covered_intervals",
                                       "all_intervals_yes_bid", "all_intervals_no_bid",
                                       "conditional_on_fill"}
    assert set(rows[0]) == {
        "ticker", "game", "series", "side", "entry_captured_at", "next_captured_at",
        "rest_price", "price_source_tag", "interval_covered", "filled", "fill_trade_id",
        "fill_price_source_tag", "settle_result", "won", "pnl"}


def test_regression_headline_modules_forbidden_token_invariant_still_passes():
    """L337's fix must not have weakened
    `test_q51_maker_fillsim.py::test_module_computes_no_queue_position_or_time_to_fill_number`.
    The original test function is loaded from disk and executed here, so a future edit that
    quietly relaxes it fails this file too."""
    spec = importlib.util.spec_from_file_location(
        "q51_maker_fillsim_tests_l337", ROOT / "tests" / "test_q51_maker_fillsim.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(M.FORBIDDEN_REPORT_TOKENS) >= {"queue", "queue_ahead", "queue_position",
                                              "time_to_fill"}
    mod.test_module_computes_no_queue_position_or_time_to_fill_number()


def test_regression_the_queue_aware_report_is_a_separate_artifact():
    """The queue-aware numbers live in their OWN report/rows files; the headline module's
    outputs are not rewritten by this script."""
    assert Q.REPORT_PATH.name == "q51_queue_aware_fillsim.json"
    assert Q.REPORT_PATH != M.REPORT_PATH and Q.ROWS_PATH != M.ROWS_PATH
