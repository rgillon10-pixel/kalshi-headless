"""Offline unit tests for q32_sharp_devig_polymarket_probe.

Q32 is PROBE-PREP: both legs (the odds-api de-vig anchor and the Polymarket sports leg) are
blocked in tape, so the join/probe script is written + tested against FIXTURES so it fires the
moment real data lands. These tests pin the load-bearing logic: (1) the game+outcome JOIN, (2)
the resolution-equivalence FILTER (non-equivalent AND missing-flag pairs excluded and counted,
never assumed in), (3) the fee computation using the NEW core.pricing constant, (4) the
by-GAME bootstrap wiring routed through both verdict gates, and (5) the self-activating
graceful-exit path on empty/missing legs. No network, no tape mutation — every input is a
synthetic in-memory/tmp fixture.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.pricing import (
    POLYMARKET_SPORTS_TAKER_RATE,
    POLYMARKET_SPORTS_TAKER_RATE_OPTIMISTIC,
    polymarket_fee_per_contract,
)
from scripts.q32_sharp_devig_polymarket_probe import (
    MIN_CI_UNITS,
    bootstrap_scenario,
    join_edges,
    load_devig_fair_by_ticker,
    load_polymarket_sports_leg,
    run_probe,
)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _sports_pairs_record(event_ticker, series, outcomes, matched=True, capture_id="20260716T010000Z"):
    """A minimal sports_pairs.v2 game record. `outcomes` is a list of
    (ticker, outcome_name, fair_prob) tuples; fair_prob None => unmapped (no anchor)."""
    if matched:
        odds_leg = {
            "status": "matched",
            "price_source_tag": "synthetic",
            "outcomes": [
                {"kalshi_ticker": t, "kalshi_outcome_name": n,
                 "fair_prob": fp}
                for (t, n, fp) in outcomes
            ],
        }
    else:
        odds_leg = {"status": "blocked_key"}
    return {
        "schema_version": "sports_pairs.v2",
        "capture_id": capture_id,
        "event_ticker": event_ticker,
        "series": series,
        "outcomes": [{"ticker": t, "outcome_name": n, "price_source_tag": "real_ask"}
                     for (t, n, _fp) in outcomes],
        "odds_leg": odds_leg,
    }


def _poly_record(kalshi_event_ticker, kalshi_ticker, outcome_name, poly_yes_ask,
                 resolution_equivalent=True, include_flag=True, capture_id="20260716T020000Z"):
    rec = {
        "schema_version": "polymarket_sports_pairs.v0",
        "capture_id": capture_id,
        "captured_at": "2026-07-16T02:00:00+00:00",
        "kalshi_event_ticker": kalshi_event_ticker,
        "kalshi_ticker": kalshi_ticker,
        "outcome_name": outcome_name,
        "poly_yes_ask": poly_yes_ask,
        "price_source_tag": "real_ask",
        "polymarket_market_id": "0xfixture",
    }
    if include_flag:
        rec["resolution_equivalent"] = resolution_equivalent
    return rec


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


# --------------------------------------------------------------------------- #
# leg (a) reader
# --------------------------------------------------------------------------- #
def test_load_devig_fair_only_matched_games(tmp_path):
    recs = [
        _sports_pairs_record("G1", "KXA", [("G1-A", "Team A", 0.60), ("G1-B", "Team B", 0.40)]),
        _sports_pairs_record("G2", "KXA", [("G2-A", "Team C", None), ("G2-B", "Team D", 0.55)]),
        _sports_pairs_record("G3", "KXA", [("G3-A", "Team E", 0.5)], matched=False),
    ]
    _write_jsonl(tmp_path / "dt=2026-07-16.jsonl", recs)
    fair, meta = load_devig_fair_by_ticker(str(tmp_path / "dt=*.jsonl"))

    # G3 blocked_key contributes nothing; G2-A None fair contributes nothing.
    assert set(fair) == {"G1-A", "G1-B", "G2-B"}
    assert fair["G1-A"]["fair_prob"] == 0.60
    assert fair["G1-A"]["event_ticker"] == "G1"
    assert meta["n_games_total"] == 3
    assert meta["n_games_matched_odds"] == 2
    assert meta["n_outcomes_with_fair"] == 3


def test_load_devig_dedupes_by_latest_capture(tmp_path):
    recs = [
        _sports_pairs_record("G1", "KXA", [("G1-A", "Team A", 0.60)], capture_id="20260716T010000Z"),
        _sports_pairs_record("G1", "KXA", [("G1-A", "Team A", 0.70)], capture_id="20260716T030000Z"),
    ]
    _write_jsonl(tmp_path / "dt=2026-07-16.jsonl", recs)
    fair, meta = load_devig_fair_by_ticker(str(tmp_path / "dt=*.jsonl"))
    assert fair["G1-A"]["fair_prob"] == 0.70  # latest capture wins
    assert meta["n_games_total"] == 1


# --------------------------------------------------------------------------- #
# leg (b) reader
# --------------------------------------------------------------------------- #
def test_load_polymarket_leg_dedupes(tmp_path):
    recs = [
        _poly_record("G1", "G1-A", "Team A", 0.55, capture_id="20260716T010000Z"),
        _poly_record("G1", "G1-A", "Team A", 0.58, capture_id="20260716T040000Z"),
        _poly_record("G1", "G1-B", "Team B", 0.42),
    ]
    _write_jsonl(tmp_path / "dt=2026-07-16.jsonl", recs)
    poly, meta = load_polymarket_sports_leg(str(tmp_path))
    by_tkr = {r["kalshi_ticker"]: r for r in poly}
    assert by_tkr["G1-A"]["poly_yes_ask"] == 0.58  # latest capture wins
    assert meta["n_poly_lines"] == 3
    assert meta["n_poly_tickers"] == 2


def test_load_polymarket_missing_dir_is_empty(tmp_path):
    poly, meta = load_polymarket_sports_leg(str(tmp_path / "does_not_exist"))
    assert poly == []
    assert meta["n_poly_lines"] == 0


# --------------------------------------------------------------------------- #
# join + resolution-equivalence filter + fee computation
# --------------------------------------------------------------------------- #
def test_join_edge_and_fee_math():
    fair = {"G1-A": {"fair_prob": 0.50, "outcome_name": "Team A", "event_ticker": "G1", "series": "KXA"}}
    poly = [_poly_record("G1", "G1-A", "Team A", 0.55)]
    edges, meta = join_edges(fair, poly, sports_rate=POLYMARKET_SPORTS_TAKER_RATE)

    expected_fee = polymarket_fee_per_contract(0.55, rate=POLYMARKET_SPORTS_TAKER_RATE)
    expected_edge = 0.55 - 0.50 - expected_fee
    assert meta["n_joined_outcomes"] == 1
    assert edges["G1"] == [expected_edge]
    # fee actually uses the new sports constant (0.05), not the US-taker default:
    assert abs(expected_fee - 0.05 * 0.55 * (1 - 0.55)) < 1e-12


def test_join_fee_rate_sensitivity_changes_edge():
    fair = {"G1-A": {"fair_prob": 0.50, "outcome_name": "A", "event_ticker": "G1", "series": "KXA"}}
    poly = [_poly_record("G1", "G1-A", "A", 0.60)]
    e_hi, _ = join_edges(fair, poly, sports_rate=POLYMARKET_SPORTS_TAKER_RATE)
    e_lo, _ = join_edges(fair, poly, sports_rate=POLYMARKET_SPORTS_TAKER_RATE_OPTIMISTIC)
    # a LOWER fee rate => a LARGER (less-subtracted) edge under this sign convention.
    assert e_lo["G1"][0] > e_hi["G1"][0]


def test_join_excludes_non_equivalent_and_missing_flag():
    fair = {
        "G1-A": {"fair_prob": 0.5, "outcome_name": "A", "event_ticker": "G1", "series": "KXA"},
        "G1-B": {"fair_prob": 0.5, "outcome_name": "B", "event_ticker": "G1", "series": "KXA"},
        "G2-A": {"fair_prob": 0.5, "outcome_name": "C", "event_ticker": "G2", "series": "KXA"},
    }
    poly = [
        _poly_record("G1", "G1-A", "A", 0.55, resolution_equivalent=True),
        _poly_record("G1", "G1-B", "B", 0.55, resolution_equivalent=False),   # excluded: not equiv
        _poly_record("G2", "G2-A", "C", 0.55, include_flag=False),            # excluded: missing flag
        _poly_record("G9", "G9-X", "X", 0.55, resolution_equivalent=True),    # excluded: no fair anchor
    ]
    edges, meta = join_edges(fair, poly)
    assert set(edges) == {"G1"}                 # only the one equivalent, anchored pair
    assert meta["n_joined_outcomes"] == 1
    assert meta["n_excluded_not_resolution_equivalent"] == 1
    assert meta["n_excluded_missing_equivalence_flag"] == 1
    assert meta["n_excluded_no_fair_anchor"] == 1


def test_join_excludes_missing_ask():
    fair = {"G1-A": {"fair_prob": 0.5, "outcome_name": "A", "event_ticker": "G1", "series": "KXA"}}
    poly = [_poly_record("G1", "G1-A", "A", None)]
    edges, meta = join_edges(fair, poly)
    assert edges == {}
    assert meta["n_excluded_no_real_ask"] == 1


def test_poly_ask_nested_fallback():
    # a collector that nests its book block the polymarket_pairs way is still readable.
    fair = {"G1-A": {"fair_prob": 0.5, "outcome_name": "A", "event_ticker": "G1", "series": "KXA"}}
    rec = {
        "kalshi_ticker": "G1-A", "kalshi_event_ticker": "G1", "outcome_name": "A",
        "resolution_equivalent": True,
        "polymarket": {"best_ask": 0.55, "price_source_tag": "real_ask"},
    }
    edges, meta = join_edges(fair, [rec])
    assert meta["n_joined_outcomes"] == 1
    assert "G1" in edges


# --------------------------------------------------------------------------- #
# bootstrap wiring + both verdict gates
# --------------------------------------------------------------------------- #
def test_bootstrap_scenario_routes_through_gates():
    # 12 games, all strongly positive => admissible check needs an opposing unit; give one loser.
    edges = {f"G{i}": [0.05] for i in range(11)}
    edges["G11"] = [-0.02]  # one opposing (losing) game so the CI is admissible
    s = bootstrap_scenario(edges, n_boot=500)
    assert s["n_units"] == 12
    assert s["admissible"] is True
    assert set(s.keys()) >= {"mean", "ci95", "clears_tick_magnitude", "ci_strictly_positive", "alive"}


def test_bootstrap_scenario_all_same_sign_inadmissible():
    # every unit positive => no opposing unit => inadmissible (L41), regardless of CI sign.
    edges = {f"G{i}": [0.05] for i in range(12)}
    s = bootstrap_scenario(edges, n_boot=500)
    assert s["admissible"] is False
    assert s["alive"] is False
    assert "no_opposing_unit" in s["admissibility"]["reasons"]


# --------------------------------------------------------------------------- #
# end-to-end run_probe: self-activating guard + a joined run
# --------------------------------------------------------------------------- #
def test_run_probe_no_odds_leg_exits_clean(tmp_path):
    # sports tape present but all blocked_key; poly leg present -> insufficient (no anchor).
    sp = tmp_path / "sports"
    _write_jsonl(sp / "dt=2026-07-16.jsonl",
                 [_sports_pairs_record("G1", "KXA", [("G1-A", "A", 0.5)], matched=False)])
    pd = tmp_path / "poly"
    _write_jsonl(pd / "dt=2026-07-16.jsonl", [_poly_record("G1", "G1-A", "A", 0.55)])
    rep = run_probe(str(sp / "dt=*.jsonl"), str(pd), n_boot=200)
    assert rep["data_adequate"] is False
    assert "no de-vig-fair anchor" in rep["insufficient_reason"]
    assert "scenario_conservative" not in rep


def test_run_probe_no_poly_leg_exits_clean(tmp_path):
    sp = tmp_path / "sports"
    _write_jsonl(sp / "dt=2026-07-16.jsonl",
                 [_sports_pairs_record("G1", "KXA", [("G1-A", "A", 0.5)])])
    rep = run_probe(str(sp / "dt=*.jsonl"), str(tmp_path / "empty_poly"), n_boot=200)
    assert rep["data_adequate"] is False
    assert "no Polymarket sports leg" in rep["insufficient_reason"]


def test_run_probe_all_excluded_exits_clean(tmp_path):
    sp = tmp_path / "sports"
    _write_jsonl(sp / "dt=2026-07-16.jsonl",
                 [_sports_pairs_record("G1", "KXA", [("G1-A", "A", 0.5)])])
    pd = tmp_path / "poly"
    # the only poly outcome is non-equivalent => 0 joined => insufficient, not a fabricated CI.
    _write_jsonl(pd / "dt=2026-07-16.jsonl",
                 [_poly_record("G1", "G1-A", "A", 0.55, resolution_equivalent=False)])
    rep = run_probe(str(sp / "dt=*.jsonl"), str(pd), n_boot=200)
    assert rep["data_adequate"] is False
    assert "0 resolution-equivalent" in rep["insufficient_reason"]


def test_run_probe_joined_produces_scenarios(tmp_path):
    # 12 games each with 1 equivalent outcome -> testable; one opposing to keep it admissible.
    sports_recs = []
    poly_recs = []
    for i in range(12):
        et = f"G{i}"
        sports_recs.append(_sports_pairs_record(et, "KXA", [(f"{et}-A", f"Team{i}", 0.50)]))
        ask = 0.40 if i == 0 else 0.60  # game 0 opposing (ask below fair), rest above
        poly_recs.append(_poly_record(et, f"{et}-A", f"Team{i}", ask))
    sp = tmp_path / "sports"
    pd = tmp_path / "poly"
    _write_jsonl(sp / "dt=2026-07-16.jsonl", sports_recs)
    _write_jsonl(pd / "dt=2026-07-16.jsonl", poly_recs)

    rep = run_probe(str(sp / "dt=*.jsonl"), str(pd), n_boot=1000)
    assert rep["data_adequate"] is True
    assert rep["testable"] is True
    assert rep["scenario_conservative"]["n_units"] == 12
    assert rep["scenario_conservative"]["n_obs"] == 12
    # verdict string is one of the adequate branches (not the untestable branch)
    assert "UNTESTABLE" not in rep["verdict"]


def test_run_probe_too_few_units_untestable(tmp_path):
    # fewer than MIN_CI_UNITS joined games -> untestable, no false verdict.
    n = MIN_CI_UNITS - 1
    sports_recs, poly_recs = [], []
    for i in range(n):
        et = f"G{i}"
        sports_recs.append(_sports_pairs_record(et, "KXA", [(f"{et}-A", f"T{i}", 0.5)]))
        poly_recs.append(_poly_record(et, f"{et}-A", f"T{i}", 0.60))
    sp = tmp_path / "sports"
    pd = tmp_path / "poly"
    _write_jsonl(sp / "dt=2026-07-16.jsonl", sports_recs)
    _write_jsonl(pd / "dt=2026-07-16.jsonl", poly_recs)
    rep = run_probe(str(sp / "dt=*.jsonl"), str(pd), n_boot=200)
    assert rep["data_adequate"] is True
    assert rep["testable"] is False
    assert "UNTESTABLE" in rep["verdict"]
