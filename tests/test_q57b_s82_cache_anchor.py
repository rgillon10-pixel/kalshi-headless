"""Tests for Q57(b): the cache-anchored S82 retest and its independent re-derivation.

Three tiers, in the house style:
  1. SEAL     - the pre-registration hash is pinned, so a post-hoc spec edit fails CI.
  2. OFFLINE  - synthetic fixtures for the two deltas (union anchor, floor-2 gate) and for
                the re-derivation's own primitives, each checked against the incumbent
                implementation it deliberately does not import.
  3. REAL TAPE - acceptance assertions over the COMMITTED tape, stated as directions and
                floors (L320/L191), plus the cross-implementation agreement that stands in
                for the verifier this harness cannot dispatch.
"""
from __future__ import annotations

import json

import pytest

from core.bootstrap import sign_variation_admissible
from core.pricing import fee_per_contract
from core.timeutil import parse_iso_utc
from scripts import q57b_s82_cache_anchor_probe as B
from scripts import q57b_s82_cache_anchor_rederive as R
from scripts import q57_s82_flow_fade_probe as P

# The seal. Recomputed from PREREGISTRATION_B; changing any spec value changes this and
# this test is the intended alarm.
SEALED_PREREG_B_SHA256 = (
    "2d243e274b31eb50daf6fb7d112a98cf10734526b386719c9bb356c769c1813c")


# --------------------------------------------------------------------------- #
# 1. seal
# --------------------------------------------------------------------------- #
def test_preregistration_hash_is_sealed():
    assert B.PREREG_B_SHA256 == SEALED_PREREG_B_SHA256
    assert B.preregistration_b_sha256() == SEALED_PREREG_B_SHA256


def test_seal_breaks_when_any_spec_value_changes():
    tweaked = dict(B.PREREGISTRATION_B)
    tweaked["min_abs_rho"] = 0.19
    assert B.preregistration_b_sha256(tweaked) != SEALED_PREREG_B_SHA256


def test_delta_2_is_the_real_default_floor_not_a_relaxation():
    """The sealed Q57 probe used 1; the reopen condition mandates the real default 2."""
    assert B.MIN_MINORITY_UNITS_B == 2
    census = {"g1": ["no"], "g2": ["yes"]}
    at_floor_2 = sign_variation_admissible(census, min_exclusive_minority_units=2)
    assert at_floor_2["min_exclusive_minority_units"] == 2
    assert B.MIN_MINORITY_UNITS_B > int(P.PREREGISTRATION["min_exclusive_minority_units"])


def test_delta_1_anchor_names_both_families():
    anchor = str(B.PREREGISTRATION_B["close_anchor"])
    assert "settlement_ledger" in anchor and "q51_settlement_cache" in anchor


def test_everything_else_matches_the_sealed_spec():
    """Only the two authorised deltas may differ from Q57's sealed pre-registration."""
    for key in ("unit", "entry_instant_rule", "flow_weight", "min_abs_rho",
                "min_window_count", "direction", "entry_price_source_tag",
                "entry_price_band", "exit", "fee_legs", "fee_side", "min_units",
                "n_boot", "seed", "tick", "min_ticks"):
        assert B.PREREGISTRATION_B[key] == P.PREREGISTRATION[key], key


# --------------------------------------------------------------------------- #
# 2. offline fixtures - DELTA 1
# --------------------------------------------------------------------------- #
def _write_ledger(tmp_path, rows):
    d = tmp_path / "settlement_ledger"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "dt=2026-07-07.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return d


def _write_cache(tmp_path, markets):
    d = tmp_path / "tape" / "q51_settlement_cache"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "settlement-test.json", "w", encoding="utf-8") as fh:
        json.dump({"markets": markets, "price_source_tag": "broker_truth"}, fh)
    return tmp_path


def test_union_anchor_adds_cache_only_tickers(tmp_path):
    ledger = _write_ledger(tmp_path, [
        {"ticker": "KXNPBGAME-A-X", "close_time": "2026-07-07T05:00:00Z"}])
    root = _write_cache(tmp_path, {
        "KXMLBGAME-B-Y": {"close_time": "2026-07-06T19:15:00Z", "result": "yes"}})
    closes, audit = B.load_close_times_union(
        frozenset({"KXNPBGAME-A-X", "KXMLBGAME-B-Y"}), ledger, root)
    assert set(closes) == {"KXNPBGAME-A-X", "KXMLBGAME-B-Y"}
    assert audit["n_tickers_ledger"] == 1
    assert audit["n_tickers_cache"] == 1
    assert audit["n_tickers_added_by_cache"] == 1
    assert audit["n_tickers_union"] == 2


def test_union_anchor_takes_the_min_and_reports_the_disagreement(tmp_path):
    ledger = _write_ledger(tmp_path, [
        {"ticker": "KXT-A", "close_time": "2026-07-07T06:00:00Z"}])
    root = _write_cache(tmp_path, {
        "KXT-A": {"close_time": "2026-07-07T05:00:00Z", "result": "no"}})
    closes, audit = B.load_close_times_union(frozenset({"KXT-A"}), ledger, root)
    assert closes["KXT-A"] == parse_iso_utc("2026-07-07T05:00:00Z").timestamp()
    assert audit["n_tickers_in_both"] == 1
    assert audit["n_tickers_disagreeing"] == 1
    assert audit["disagreement_minutes_examples"][0][1] == -60.0
    assert audit["close_time_distinct_values_max"] == 2


def test_union_anchor_ignores_tickers_outside_the_population(tmp_path):
    ledger = _write_ledger(tmp_path, [
        {"ticker": "KXOTHER-Z", "close_time": "2026-07-07T06:00:00Z"}])
    root = _write_cache(tmp_path, {"KXALSO-Q": {"close_time": "2026-07-07T05:00:00Z"}})
    closes, audit = B.load_close_times_union(frozenset({"KXT-A"}), ledger, root)
    assert closes == {}
    assert audit["n_tickers_union"] == 0


# --------------------------------------------------------------------------- #
# 2b. offline fixtures - DELTA 2 and the outcome-blind branch
# --------------------------------------------------------------------------- #
def _row(game, ticker, side, ask=0.40, cap="2026-07-07T00:00:00Z"):
    return {"game": game, "ticker": ticker, "fade_side": side, "entry_ask": ask,
            "entry_captured_at": cap, "overround": 0.02}


def test_population_gate_refuses_a_single_sided_population_at_floor_two():
    rows = [_row(f"G{i}", f"G{i}-T", "no") for i in range(12)]
    pop = B.population_gate(rows, frozenset(r["ticker"] for r in rows))
    assert pop["meets_unit_floor"] is True
    assert pop["admissible"] is False
    assert "single_sided" in pop["sign_variation"]["reasons"]


def test_population_gate_refuses_one_minority_unit_but_admits_two():
    one = [_row(f"G{i}", f"G{i}-T", "no") for i in range(11)] + [
        _row("GY", "GY-T", "yes")]
    pop_one = B.population_gate(one, frozenset(r["ticker"] for r in one))
    assert pop_one["admissible"] is False
    two = one + [_row("GY2", "GY2-T", "yes")]
    pop_two = B.population_gate(two, frozenset(r["ticker"] for r in two))
    assert pop_two["sign_variation"]["census"]["minority_side_units_exclusive"] == 2
    assert pop_two["admissible"] is True


def test_population_only_cell_never_reads_an_outcome_value(monkeypatch):
    """`score=False` must not touch `outcome_map`; a trip here is a seal breach."""
    def _boom(*a, **k):
        raise AssertionError("outcome_map called on a population-only cell")

    monkeypatch.setattr(P, "outcome_map", _boom)
    cell = B.run_cell({}, {}, {}, frozenset(), name="diag", window_minutes=15.0,
                      max_lag_minutes=60.0, score=False, settlement_root="tape")
    assert cell["scored_cell"] is False
    assert "POPULATION-ONLY" in cell["verdict"]


def test_inadmissible_scored_cell_also_never_reads_an_outcome_value(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("outcome_map called before the adequacy gate passed")

    monkeypatch.setattr(P, "outcome_map", _boom)
    cell = B.run_cell({}, {}, {}, frozenset(), name="primary", window_minutes=120.0,
                      max_lag_minutes=60.0, score=True, settlement_root="tape")
    assert cell["verdict"] == "INSUFFICIENT DATA"
    assert "no outcome value read" in cell["note"]


# --------------------------------------------------------------------------- #
# 2c. the re-derivation primitives, checked against what it refuses to import
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("iso", [
    "2026-07-07T05:00:00Z",
    "2026-08-03T23:59:59Z",
    "2026-07-11T15:55:10.058238+00:00",
    "2026-07-07T11:55:53.296454+00:00",
])
def test_rederive_epoch_parser_agrees_with_core_timeutil(iso):
    assert R.epoch(iso) == pytest.approx(parse_iso_utc(iso).timestamp(), abs=1e-6)


@pytest.mark.parametrize("price", [0.01, 0.02, 0.05, 0.2, 0.5, 0.73, 0.9, 0.93, 0.98])
def test_rederive_fee_agrees_with_core_pricing(price):
    assert R.fee(price) == pytest.approx(fee_per_contract(price), abs=1e-12)


def test_rederive_game_predicates_match_the_incumbent():
    for tk in ("KXMLBGAME-26JUL061915NYMATL-NYM", "KXNWSLGAME-26AUG02DENBOS-DEN",
               "KXMVEGAME-26JUL01A-B", "KXBTC-26JUL0317-T71799.99"):
        assert R.is_game(tk) == P.M.is_sports_game_market(tk), tk
        assert R.game_of(tk) == P.game_id_of(tk), tk


def test_rederive_side_census_matches_core_bootstrap_on_a_fixture():
    rows = [{"game": "A", "fade_side": "no"}, {"game": "B", "fade_side": "no"},
            {"game": "C", "fade_side": "yes"}, {"game": "D", "fade_side": "yes"}]
    mine = R.side_census(rows)
    theirs = sign_variation_admissible(
        {"A": ["no"], "B": ["no"], "C": ["yes"], "D": ["yes"]},
        min_exclusive_minority_units=2, sides=("yes", "no"))["census"]
    assert mine["units_per_side"] == theirs["units_per_side"]
    assert mine["minority_units_exclusive"] == theirs["minority_side_units_exclusive"]


# --------------------------------------------------------------------------- #
# 3. real committed tape - acceptance, stated as directions and floors (L320/L191)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def probe_report():
    return B.run()


@pytest.fixture(scope="module")
def rederive_report():
    return R.run()


def _cell(rep, name):
    for c in rep["cells"]:
        if c["name"] == name:
            return c
    raise AssertionError(name)


def test_real_tape_primary_cell_is_single_sided_and_refuses_to_score(probe_report):
    c = _cell(probe_report, "primary_minimal_change")
    cen = c["population"]["sign_variation"]["census"]
    assert c["population"]["n_game_units"] >= 10
    assert cen["units_per_side"]["yes"] == 0
    assert c["verdict"] == "INSUFFICIENT DATA"
    assert "bootstrap" not in c


def test_real_tape_secondary_cell_is_admissible_and_does_not_clear_the_bar(probe_report):
    c = _cell(probe_report, "secondary_verifier_identified")
    cen = c["population"]["sign_variation"]["census"]
    assert cen["minority_side_units_exclusive"] >= 2
    assert c["population"]["n_game_units"] >= 10
    lo, hi = c["bootstrap"]["ci95"]
    assert lo < 0.0 < hi, "the CI straddles zero: not an edge, not a kill"
    assert c["verdict"] == "NOT ALIVE"


def test_real_tape_every_scored_entry_is_a_real_ask_inside_the_band(probe_report):
    c = _cell(probe_report, "secondary_verifier_identified")
    for s in c["scored"]:
        assert s["price_source_tag"] == "real_ask"
        assert 0.02 <= s["entry_ask"] <= 0.98


def test_real_tape_widening_the_anchor_is_what_the_cache_actually_does(probe_report):
    a = probe_report["anchor_audit"]
    assert a["n_tickers_added_by_cache"] >= 1
    assert a["n_tickers_union"] == a["n_tickers_ledger"] + a["n_tickers_added_by_cache"]


def test_the_two_implementations_agree_on_every_cell_population(probe_report,
                                                                rederive_report):
    """The redundancy that stands in for the verifier this harness cannot dispatch."""
    for name in ("primary_minimal_change", "secondary_verifier_identified",
                 "diagnostic_window_only"):
        p = _cell(probe_report, name)
        r = _cell(rederive_report, name)
        cen = p["population"]["sign_variation"]["census"]
        assert p["population"]["n_game_units"] == r["n_units"], name
        assert cen["units_per_side"] == r["units_per_side"], name
        assert (cen["minority_side_units_exclusive"]
                == r["minority_units_exclusive"]), name


def test_the_two_implementations_agree_on_the_scored_mean(probe_report,
                                                          rederive_report):
    p = _cell(probe_report, "secondary_verifier_identified")["bootstrap"]
    r = _cell(rederive_report, "secondary_verifier_identified")["bootstrap"]
    assert p["n_units"] == r["n_units"] and p["n_obs"] == r["n_obs"]
    assert p["mean"] == pytest.approx(r["mean"], abs=1e-12)
    assert r["seed"] != p["seed"], "the CI agreement must be across seeds, not one draw"
    assert r["ci95"][0] < 0.0 < r["ci95"][1]


def test_the_two_implementations_agree_on_the_union_anchor(probe_report,
                                                           rederive_report):
    for k in ("n_tickers_ledger", "n_tickers_cache", "n_tickers_union",
              "n_tickers_added_by_cache", "n_tickers_in_both"):
        assert probe_report["anchor_audit"][k] == rederive_report["anchor_audit"][k], k


def test_real_tape_the_positive_point_estimate_lives_in_the_stale_book_entries(
        rederive_report):
    """DESCRIPTIVE, and the reason the secondary cell must never be quoted alone: its
    entire positive mean comes from entries whose book is staler than the pre-registered
    60-minute rule allows."""
    split = _cell(rederive_report, "secondary_verifier_identified")["staleness_split"]
    assert split["n_entries_lag_gt_60min"] >= 1
    assert split["mean_pnl_lag_gt_60min"] > split["mean_pnl_lag_le_60min"]
