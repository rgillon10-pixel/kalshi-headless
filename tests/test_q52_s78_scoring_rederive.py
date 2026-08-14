"""Tests for the independent Q52/S78 SCORING re-derivation (the no-verifier redundancy leg).

This file's job is to pin the three places a from-scratch second implementation of a scored
verdict goes quietly wrong: the settlement-direction precedence walk (a first-hit bug flips
a P&L sign), the payout/fee arithmetic, and the hand-rolled bootstrap RNG (a degenerate
stream would collapse the CI and manufacture agreement). Everything here is offline and
synthetic; no committed tape is read.
"""
from __future__ import annotations

import json
import os

import pytest

from core.pricing import MAKER_FEE_RATE, fee_per_contract
from scripts import q52_s78_scoring_rederive as S
from scripts import q56_s80_print_vwap_overshoot_maker_fade as S80


# --------------------------------------------------------------------------- #
# Settlement direction
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw,expected", [
    ("yes", "yes"), ("NO", "no"), (" Yes ", "yes"), ("scalar", None), ("", None),
    (None, None), ("void", None), (1, None),
])
def test_norm_is_absent_not_a_loss_on_anything_non_binary(raw, expected):
    got = S._norm(raw)
    assert got == expected
    if expected is None:
        assert got is None


def _write_cache(root: str, family: str, markets: dict) -> None:
    d = os.path.join(root, family)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "settlement.json"), "w") as fh:
        json.dump({"markets": markets}, fh)


def _write_ledger(root: str, day: str, rows: list) -> None:
    d = os.path.join(root, "settlement_ledger")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "dt=%s.jsonl" % day), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_settlement_direction_first_hit_follows_the_declared_source_order(tmp_path):
    root = str(tmp_path)
    _write_ledger(root, "2026-08-03", [{"ticker": "A", "result": "yes"}])
    _write_cache(root, "q51_settlement_cache", {"A": {"result": "no"},
                                                "B": {"result": "no"}})
    direction, conflicts = S.settled_direction(root=root)
    # the ledger is declared FIRST, so it wins for A; B is only in the later cache
    assert direction == {"A": "yes", "B": "no"}
    # ...and the disagreement is surfaced, not swallowed by the first-hit walk
    assert set(conflicts) == {"A"}
    assert conflicts["A"] == {"settlement_ledger": "yes", "q51_settlement_cache": "no"}


def test_settlement_direction_reports_no_conflict_when_sources_agree(tmp_path):
    root = str(tmp_path)
    _write_ledger(root, "2026-08-03", [{"ticker": "A", "result": "yes"}])
    _write_cache(root, "q56_settlement_cache", {"A": {"result": "yes"}})
    direction, conflicts = S.settled_direction(root=root)
    assert direction == {"A": "yes"}
    assert conflicts == {}


def test_settlement_direction_skips_non_binary_results(tmp_path):
    root = str(tmp_path)
    _write_cache(root, "q51_settlement_cache",
                 {"A": {"result": "scalar"}, "B": {"result": ""}, "C": {"result": "no"}})
    direction, conflicts = S.settled_direction(root=root)
    assert direction == {"C": "no"}
    assert conflicts == {}


def test_settlement_direction_on_an_empty_root_is_empty_not_an_error(tmp_path):
    direction, conflicts = S.settled_direction(root=str(tmp_path))
    assert direction == {} and conflicts == {}


def test_declared_source_order_matches_the_shared_registry_order():
    """The order is RESTATED in this file on purpose (importing it would make agreement on
    precedence circular) — but a restatement that drifts from the registry is a silent bug."""
    from core.settlement_sources import SETTLEMENT_SOURCES
    declared = [s.name for s in SETTLEMENT_SOURCES]
    restated = [name for name, _, _ in S.SOURCE_ORDER]
    assert restated == [n for n in declared if n in set(restated)]
    assert restated[0] == "settlement_ledger"


# --------------------------------------------------------------------------- #
# P&L arithmetic
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("side,price,result", [
    ("yes", 0.30, "yes"), ("yes", 0.30, "no"), ("no", 0.30, "no"), ("no", 0.30, "yes"),
    ("yes", 0.02, "yes"), ("no", 0.98, "no"), ("yes", 0.50, "no"),
])
def test_rederived_leg_pnl_agrees_with_the_probes_imported_one(side, price, result):
    assert S.leg_pnl_rederived(side, price, result) == pytest.approx(
        S80.leg_pnl(side, price, result), abs=1e-12)


def test_a_losing_leg_is_fully_priced_never_dropped():
    lost = S.leg_pnl_rederived("yes", 0.40, "no")
    assert lost == pytest.approx(-0.40 - fee_per_contract(0.40, MAKER_FEE_RATE), abs=1e-12)
    assert lost < 0


def test_the_fee_is_charged_once_on_the_winning_side_too():
    won = S.leg_pnl_rederived("no", 0.40, "no")
    assert won == pytest.approx(1.0 - 0.40 - fee_per_contract(0.40, MAKER_FEE_RATE), abs=1e-12)


# --------------------------------------------------------------------------- #
# Hand-rolled RNG + bootstrap
# --------------------------------------------------------------------------- #
def test_lcg_is_deterministic_for_a_seed():
    s1, s2 = S.LCG(42), S.LCG(42)
    assert [s1.next_below(97) for _ in range(50)] == [s2.next_below(97) for _ in range(50)]


def test_lcg_stream_is_not_degenerate():
    """A stuck or short-period stream would collapse every resample onto one unit and
    manufacture a spuriously tight CI — the failure this bootstrap must not have."""
    rng = S.LCG(42)
    draws = [rng.next_below(34) for _ in range(5000)]
    assert all(0 <= d < 34 for d in draws)
    assert len(set(draws)) == 34            # every unit index is reachable
    counts = [draws.count(i) for i in range(34)]
    assert min(counts) > 5000 / 34 * 0.5    # roughly uniform, not a hot-spot stream


def test_lcg_differs_across_seeds():
    assert [S.LCG(1).next_below(1000) for _ in range(20)] != \
           [S.LCG(2).next_below(1000) for _ in range(20)]


def test_bootstrap_mean_is_the_exact_pooled_mean_not_a_mean_of_unit_means():
    uv = {"g1": [1.0, 1.0, 1.0], "g2": [0.0]}
    boot = S.block_bootstrap_rederived(uv, n_boot=200, seed=7)
    assert boot["mean"] == pytest.approx(3.0 / 4.0)   # pooled, not (1.0 + 0.0)/2
    assert boot["n_units"] == 2 and boot["n_obs"] == 4


def test_bootstrap_ci_brackets_the_mean_on_a_dispersed_population():
    uv = {"g%d" % i: [float(i % 5) - 2.0] for i in range(40)}
    boot = S.block_bootstrap_rederived(uv, n_boot=1000, seed=42)
    lo, hi = boot["ci95"]
    assert lo <= boot["mean"] <= hi
    assert lo < hi


def test_bootstrap_on_a_constant_population_has_a_degenerate_ci():
    uv = {"g%d" % i: [0.25] for i in range(20)}
    boot = S.block_bootstrap_rederived(uv, n_boot=500, seed=42)
    assert boot["ci95"] == [pytest.approx(0.25), pytest.approx(0.25)]


def test_bootstrap_on_empty_input_is_honest_none_not_zero():
    boot = S.block_bootstrap_rederived({}, n_boot=10, seed=1)
    assert boot["mean"] is None and boot["ci95"] == [None, None]
    boot2 = S.block_bootstrap_rederived({"g1": []}, n_boot=10, seed=1)
    assert boot2["mean"] is None and boot2["n_obs"] == 0


def test_two_independent_rngs_agree_on_a_wide_ci_within_monte_carlo_error():
    """The claim this file's redundancy rests on: the MEAN is exact, the CI agrees only up
    to Monte-Carlo error. Pinned against `core.bootstrap` on a synthetic population."""
    from core.bootstrap import block_bootstrap
    uv = {"g%d" % i: [float((i * 37) % 11) / 10.0 - 0.5] for i in range(50)}
    mine = S.block_bootstrap_rederived(uv, n_boot=4000, seed=42)
    theirs = block_bootstrap(uv, n_boot=4000, seed=42)
    assert mine["mean"] == pytest.approx(theirs["mean"], abs=1e-12)
    assert mine["ci95"][0] == pytest.approx(theirs["ci95"][0], abs=0.02)
    assert mine["ci95"][1] == pytest.approx(theirs["ci95"][1], abs=0.02)


# --------------------------------------------------------------------------- #
# Verdict rule
# --------------------------------------------------------------------------- #
def test_verdict_is_dead_when_the_ci_straddles_zero():
    assert S.verdict_of({"n_units": 34, "ci95": [-0.0087, 0.0146]}) == "DEAD"


def test_verdict_is_dead_when_positive_but_inside_one_tick():
    assert S.verdict_of({"n_units": 34, "ci95": [0.004, 0.02]}) == "DEAD"


def test_verdict_is_alive_only_above_one_tick():
    assert S.verdict_of({"n_units": 34, "ci95": [0.011, 0.05]}) == "ALIVE"


def test_verdict_is_inadmissible_below_the_unit_floor():
    assert S.verdict_of({"n_units": 9, "ci95": [0.5, 0.9]}) == "INADMISSIBLE"
    assert S.MIN_UNITS == 10 and S.MIN_EXCLUSIVE_MINORITY == 2


# --------------------------------------------------------------------------- #
# Candidate scoring
# --------------------------------------------------------------------------- #
def _snap(ts_rec):
    return ts_rec


def _book(t, yes_bid, yes_ask, no_bid, yes_ladder, no_ladder):
    return (t, {"best_yes_bid": yes_bid, "best_yes_ask": yes_ask, "best_no_bid": no_bid,
                "yes_bids": yes_ladder, "no_bids": no_ladder})


def test_score_candidates_fills_only_when_consuming_volume_exceeds_the_queue():
    tk = "KXTESTGAME-26AUG01AAABBB-AAA"
    books = {tk: [_book(0.0, 0.30, 0.31, 0.69, [[0.30, 5]], [[0.69, 5]]),
                  _book(600.0, 0.30, 0.31, 0.69, [[0.30, 5]], [[0.69, 5]])]}
    # one ask-side print of 10 contracts at 0.30 consumes the yes queue of 5 -> fill
    prints = {tk: [(300.0, 0.30, 10.0, "ask", "t1")]}
    rows = S.score_candidates(prints, books, [S._game(tk)], ["cheap/tight"], {tk: "yes"})
    yes_rows = [r for r in rows if r["side"] == "yes"]
    assert len(yes_rows) == 1 and yes_rows[0]["filled"] is True
    assert yes_rows[0]["pnl"] == pytest.approx(S.leg_pnl_rederived("yes", 0.30, "yes"))


def test_an_unfilled_candidate_scores_an_honest_zero():
    tk = "KXTESTGAME-26AUG01AAABBB-AAA"
    books = {tk: [_book(0.0, 0.30, 0.31, 0.69, [[0.30, 500]], [[0.69, 500]]),
                  _book(600.0, 0.30, 0.31, 0.69, [[0.30, 500]], [[0.69, 500]])]}
    prints = {tk: [(300.0, 0.30, 1.0, "ask", "t1")]}
    rows = S.score_candidates(prints, books, [S._game(tk)], ["cheap/tight"], {tk: "yes"})
    assert rows and all(r["filled"] is False and r["pnl"] == 0.0 for r in rows)


def test_a_ticker_with_no_binary_direction_is_dropped_not_scored_as_zero():
    tk = "KXTESTGAME-26AUG01AAABBB-AAA"
    books = {tk: [_book(0.0, 0.30, 0.31, 0.69, [[0.30, 5]], [[0.69, 5]]),
                  _book(600.0, 0.30, 0.31, 0.69, [[0.30, 5]], [[0.69, 5]])]}
    prints = {tk: [(300.0, 0.30, 10.0, "ask", "t1")]}
    assert S.score_candidates(prints, books, [S._game(tk)], ["cheap/tight"], {}) == []


def test_a_candidate_outside_an_admitted_cell_is_never_generated():
    tk = "KXTESTGAME-26AUG01AAABBB-AAA"
    books = {tk: [_book(0.0, 0.30, 0.31, 0.69, [[0.30, 5]], [[0.69, 5]]),
                  _book(600.0, 0.30, 0.31, 0.69, [[0.30, 5]], [[0.69, 5]])]}
    prints = {tk: [(300.0, 0.30, 10.0, "ask", "t1")]}
    assert S.score_candidates(prints, books, [S._game(tk)], ["rich/wide"], {tk: "yes"}) == []


def test_a_snapshot_pair_wider_than_the_interval_cap_is_skipped():
    tk = "KXTESTGAME-26AUG01AAABBB-AAA"
    far = S.MAX_INTERVAL_S + 1.0
    books = {tk: [_book(0.0, 0.30, 0.31, 0.69, [[0.30, 5]], [[0.69, 5]]),
                  _book(far, 0.30, 0.31, 0.69, [[0.30, 5]], [[0.69, 5]])]}
    prints = {tk: [(300.0, 0.30, 10.0, "ask", "t1")]}
    assert S.score_candidates(prints, books, [S._game(tk)], ["cheap/tight"], {tk: "yes"}) == []


def test_a_resting_price_outside_the_band_is_refused():
    tk = "KXTESTGAME-26AUG01AAABBB-AAA"
    books = {tk: [_book(0.0, 0.005, 0.01, 0.99, [[0.005, 5]], [[0.99, 5]]),
                  _book(600.0, 0.005, 0.01, 0.99, [[0.005, 5]], [[0.99, 5]])]}
    prints = {tk: [(300.0, 0.005, 10.0, "ask", "t1")]}
    rows = S.score_candidates(prints, books, [S._game(tk)], ["cheap/tight", "rich/wide"],
                              {tk: "yes"})
    assert all(S.BAND_LO <= r["rest_price"] <= S.BAND_HI for r in rows)
    assert not any(r["side"] == "yes" for r in rows)


def test_score_candidates_on_an_empty_holdout_is_empty_not_vacuously_green():
    """A guard whose denominator is zero cannot be evidence (L191/L296): pin that the
    non-empty case above really did produce rows, so this emptiness is meaningful."""
    tk = "KXTESTGAME-26AUG01AAABBB-AAA"
    books = {tk: [_book(0.0, 0.30, 0.31, 0.69, [[0.30, 5]], [[0.69, 5]]),
                  _book(600.0, 0.30, 0.31, 0.69, [[0.30, 5]], [[0.69, 5]])]}
    prints = {tk: [(300.0, 0.30, 10.0, "ask", "t1")]}
    assert S.score_candidates(prints, books, [], ["cheap/tight"], {tk: "yes"}) == []
    assert S.score_candidates(prints, books, [S._game(tk)], ["cheap/tight"], {tk: "yes"})


# --------------------------------------------------------------------------- #
# Independence / hygiene
# --------------------------------------------------------------------------- #
def test_this_module_does_not_import_the_sealed_probe():
    """The whole value of the redundancy leg is that it shares no code with the probe."""
    import ast
    src = open(S.__file__).read()
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("toxicity_filtered_maker_probe" in m for m in imported)
    assert not any("q56_s80" in m for m in imported)


def test_no_handrolled_fee_rate_literal():
    src = open(S.__file__).read()
    assert "0.0175" not in src and "0.07" not in src
    assert "MAKER_FEE_RATE" in open(
        os.path.join(os.path.dirname(S.__file__), "q52_s78_population_rederive.py")).read()


def test_no_network_or_execution_import():
    src = open(S.__file__).read()
    for banned in ("requests", "urllib", "http.client", "execution.", "socket"):
        assert banned not in src
