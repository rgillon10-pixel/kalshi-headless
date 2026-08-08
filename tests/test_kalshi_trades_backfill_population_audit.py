"""Offline tests for scripts/kalshi_trades_backfill_population_audit.py.

No network in any path. Two tiers:

  * UNIT tests over hand-built fixture tape — the writer census (including its
    can't-look-vs-looked-and-found-nothing distinction), the trade-tape inventory, the
    streaming book scan and its two-sided predicate, the eligibility threshold, the
    funnel's per-day/aggregate roll-up, the projection's PROJECTION labelling, and the
    gate classifier's four branches (each pinned by its own case, so "backfill" cannot be
    reached by accident).
  * HARD `test_acceptance_*` cases over the real committed tape.

WHICH ACCEPTANCE ASSERTIONS ARE EXACT AND WHY (the L280 rule, as applied by
tests/test_q51_m3_fill_projection.py): anything sourced from a `tape/*/dt=*.jsonl` day-file
is a DIRECTIONAL BOUND (`>=`), because a legitimate LOOP-QUEUE step-0b stranded-branch sweep
may union-append lines to a past day and that can only ADD tickers, snapshots and eligible
units. What is asserted exactly is the sign of each conclusion — no scheduled writer exists,
the settled-unit population clears the L41 floor by a wide multiple, and the gate classifies
as `backfill` — because more tape strengthens all three.

This module asserts NO mean, NO CI, NO P&L, NO fill rate and NO strategy verdict: the audit
computes none, and `test_report_is_data_adequacy_only` pins that it never will.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import kalshi_trades_backfill_population_audit as A


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _depth_line(ticker: str, cap: str, yb=0.5, nb=0.5) -> str:
    return json.dumps({"ticker": ticker, "capture_id": cap, "captured_at": cap,
                       "best_yes_bid": yb, "best_no_bid": nb,
                       "schema_version": "orderbook_depth.v1"})


def _write_depth(root: Path, day: str, lines) -> None:
    d = root / "orderbook_depth"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"dt={day}.jsonl").write_text("\n".join(lines) + "\n")


def _write_trades(root: Path, day: str, recs) -> None:
    d = root / "kalshi_trades"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"dt={day}.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")


# --------------------------------------------------------------------------- #
# writer census
# --------------------------------------------------------------------------- #
def test_writer_census_reports_no_scheduled_writer_when_no_caller_mentions_the_family(tmp_path):
    (tmp_path / "collection").mkdir()
    (tmp_path / "collection" / "hourly_pass.py").write_text("from collection import crypto_hourly\n")
    out = A.writer_census(tmp_path, ("collection/hourly_pass.py",), "kalshi_trades")
    assert out["has_scheduled_writer"] is False
    assert out["callers_scanned"] == ("collection/hourly_pass.py",)
    assert out["callers_referencing"] == ()


def test_writer_census_finds_a_caller_that_does_reference_the_family(tmp_path):
    (tmp_path / "collection").mkdir()
    (tmp_path / "collection" / "hourly_pass.py").write_text("from collection import kalshi_trades\n")
    out = A.writer_census(tmp_path, ("collection/hourly_pass.py",), "kalshi_trades")
    assert out["has_scheduled_writer"] is True
    assert out["callers_referencing"] == ("collection/hourly_pass.py",)


def test_writer_census_distinguishes_absent_caller_from_a_caller_with_no_reference(tmp_path):
    """An absent file must not be silently counted as evidence of absence."""
    out = A.writer_census(tmp_path, ("collection/nope.py",), "kalshi_trades")
    assert out["callers_absent"] == ("collection/nope.py",)
    assert out["callers_scanned"] == ()
    assert out["has_scheduled_writer"] is False


# --------------------------------------------------------------------------- #
# trade-tape inventory
# --------------------------------------------------------------------------- #
def test_trade_tape_inventory_counts_lines_tickers_tags_and_duplicate_trade_ids(tmp_path):
    _write_trades(tmp_path, "2026-08-03", [
        {"ticker": "A-X", "trade_id": "t1", "price_source_tag": "broker_truth"},
        {"ticker": "A-X", "trade_id": "t2", "price_source_tag": "broker_truth"},
        {"ticker": "B-Y", "trade_id": "t2", "price_source_tag": "broker_truth"},  # duplicate id
        {"ticker": "B-Y", "trade_id": "t3"},                                      # untagged
    ])
    inv = A.trade_tape_inventory(tmp_path)
    assert inv["n_days"] == 1 and inv["days"] == ("2026-08-03",)
    assert inv["n_lines"] == 4
    assert inv["n_distinct_tickers"] == 2
    assert inv["n_distinct_trade_ids"] == 3
    assert inv["n_duplicate_trade_ids"] == 1
    # CLAUDE.md trust default: an untagged number is synthetic, never upgraded.
    assert inv["price_source_tag_census"] == {"broker_truth": 3, "synthetic": 1}


def test_trade_tape_inventory_counts_malformed_lines_instead_of_dropping_them(tmp_path):
    d = tmp_path / "kalshi_trades"
    d.mkdir(parents=True)
    (d / "dt=2026-08-03.jsonl").write_text('{"ticker":"A-X","trade_id":"t1"}\nnot json\n\n')
    inv = A.trade_tape_inventory(tmp_path)
    assert inv["n_lines"] == 2 and inv["n_malformed_lines"] == 1


def test_trade_tape_inventory_on_absent_family_is_empty_not_an_error(tmp_path):
    inv = A.trade_tape_inventory(tmp_path)
    assert inv["n_days"] == 0 and inv["n_lines"] == 0


# --------------------------------------------------------------------------- #
# book scan / eligibility
# --------------------------------------------------------------------------- #
def test_scan_depth_day_counts_snapshots_and_two_sided_snapshots_separately(tmp_path):
    _write_depth(tmp_path, "2026-08-03", [
        _depth_line("KXNFLGAME-26AUG03AAABBB-AAA", "c1"),
        _depth_line("KXNFLGAME-26AUG03AAABBB-AAA", "c2", yb=0.0, nb=0.9),  # one-sided
        _depth_line("KXNFLGAME-26AUG03AAABBB-BBB", "c1"),
    ])
    snaps, two = A.scan_depth_day(tmp_path / "orderbook_depth" / "dt=2026-08-03.jsonl")
    assert snaps["KXNFLGAME-26AUG03AAABBB-AAA"] == 2
    assert two["KXNFLGAME-26AUG03AAABBB-AAA"] == 1
    assert snaps["KXNFLGAME-26AUG03AAABBB-BBB"] == 1


def test_eligible_tickers_applies_the_fillsims_own_two_snapshot_interval_predicate():
    assert A.MIN_SNAPSHOTS == 2
    assert A.eligible_tickers({"a": 1, "b": 2, "c": 5}) == ["b", "c"]


def test_depth_day_files_accepts_both_dt_prefixed_and_bare_day_selectors(tmp_path):
    _write_depth(tmp_path, "2026-08-03", [_depth_line("A-X", "c1")])
    _write_depth(tmp_path, "2026-08-04", [_depth_line("A-X", "c1")])
    assert [d for d, _ in A.depth_day_files(tmp_path)] == ["2026-08-03", "2026-08-04"]
    assert [d for d, _ in A.depth_day_files(tmp_path, ["dt=2026-08-04"])] == ["2026-08-04"]
    assert [d for d, _ in A.depth_day_files(tmp_path, ["2026-08-03"])] == ["2026-08-03"]


# --------------------------------------------------------------------------- #
# funnel
# --------------------------------------------------------------------------- #
def test_funnel_rolls_eligible_sports_tickers_up_to_distinct_games(tmp_path):
    """Two outcome tickers of ONE game are ONE resample unit (L6 — never the outcome)."""
    _write_depth(tmp_path, "2026-08-03", [
        _depth_line("KXNFLGAME-26AUG03AAABBB-AAA", "c1"),
        _depth_line("KXNFLGAME-26AUG03AAABBB-AAA", "c2"),
        _depth_line("KXNFLGAME-26AUG03AAABBB-BBB", "c1"),
        _depth_line("KXNFLGAME-26AUG03AAABBB-BBB", "c2"),
        _depth_line("KXBTCD-26AUG0312-T50", "c1"),   # not a sports GAME series
        _depth_line("KXBTCD-26AUG0312-T50", "c2"),
    ])
    f = A.funnel(tmp_path)
    row = f["per_day"][0]
    assert row["n_eligible"] == 3
    assert row["n_sports_eligible"] == 2
    assert row["n_sports_games_eligible"] == 1
    assert f["aggregate"]["n_sports_games_eligible_union"] == 1


def test_funnel_marks_a_day_with_no_settlement_coverage_instead_of_averaging_it_away(tmp_path):
    _write_depth(tmp_path, "2026-08-03", [
        _depth_line("KXNFLGAME-26AUG03AAABBB-AAA", "c1"),
        _depth_line("KXNFLGAME-26AUG03AAABBB-AAA", "c2"),
    ])
    f = A.funnel(tmp_path)
    assert f["aggregate"]["n_sports_games_settled_union"] == 0
    assert f["settlement"]["days_with_zero_settled_sports_games"] == ("2026-08-03",)
    assert f["settlement"]["price_source_tag"] == "broker_truth"


def test_funnel_counts_a_ticker_settled_by_a_committed_cache_family(tmp_path):
    _write_depth(tmp_path, "2026-08-03", [
        _depth_line("KXNFLGAME-26AUG03AAABBB-AAA", "c1"),
        _depth_line("KXNFLGAME-26AUG03AAABBB-AAA", "c2"),
    ])
    cache = tmp_path / "q51_settlement_cache"
    cache.mkdir(parents=True)
    (cache / "settlement.json").write_text(json.dumps({
        "markets": {"KXNFLGAME-26AUG03AAABBB-AAA": {"result": "yes", "status": "finalized"}}}))
    f = A.funnel(tmp_path)
    assert f["aggregate"]["n_sports_games_settled_union"] == 1
    assert f["per_day"][0]["n_sports_games_settled"] == 1


def test_funnel_does_not_count_a_listed_but_unsettled_market_as_settled(tmp_path):
    """Listed is not settled — conflating them is how a coverage claim lies the other way."""
    _write_depth(tmp_path, "2026-08-03", [
        _depth_line("KXNFLGAME-26AUG03AAABBB-AAA", "c1"),
        _depth_line("KXNFLGAME-26AUG03AAABBB-AAA", "c2"),
    ])
    cache = tmp_path / "q51_settlement_cache"
    cache.mkdir(parents=True)
    (cache / "settlement.json").write_text(json.dumps({
        "markets": {"KXNFLGAME-26AUG03AAABBB-AAA": {"result": "", "status": "active"}}}))
    f = A.funnel(tmp_path)
    assert f["aggregate"]["n_sports_games_settled_union"] == 0
    assert f["settlement"]["n_listed_unsettled"] >= 1


# --------------------------------------------------------------------------- #
# projection + gate classifier
# --------------------------------------------------------------------------- #
def test_unit_projection_is_labelled_a_projection_and_carries_its_basis():
    p = A.unit_projection(100, ticker_print_rate=0.21)
    assert p["is_projection"] is True
    assert p["price_source_tag"] == "synthetic"
    assert p["projected_units"] == pytest.approx(21.0)
    assert "42/200" in p["basis"]
    assert p["caveat"]


def test_gate_classifier_names_backfill_only_when_no_writer_and_the_floor_clears():
    assert A.gate_class(338, False)["gate_class"] == "backfill"
    assert A.gate_class(3, False)["gate_class"] == "backfill_insufficient"
    assert A.gate_class(3, True)["gate_class"] == "calendar"
    assert A.gate_class(338, True)["gate_class"] == "open"


def test_gate_classifier_reports_the_multiple_of_the_l41_floor():
    g = A.gate_class(338, False)
    assert g["l41_floor"] == 10
    assert g["multiple_of_floor"] == pytest.approx(33.8)
    assert g["waiting_adds_days"] is False


# --------------------------------------------------------------------------- #
# report shape
# --------------------------------------------------------------------------- #
def test_report_is_data_adequacy_only(tmp_path):
    """No verdict-class quantity may ever appear in the emitted report."""
    _write_depth(tmp_path, "2026-08-03", [_depth_line("KXNFLGAME-26AUG03AAABBB-AAA", "c1")])
    rep = A.run(tmp_path, repo_root=tmp_path)
    assert rep["verdict_class"] == "data_adequacy_only"
    # `not_computed` is the DECLARATION of the ban; scan everything else for a violation.
    scanned = {k: v for k, v in rep.items() if k != "not_computed"}
    blob = json.dumps(scanned).lower()
    for banned in ('"mean"', '"ci95"', '"pnl"', '"fill_rate"', '"edge"', '"won"'):
        assert banned not in blob
    assert rep["not_computed"] == ["mean", "ci95", "pnl", "fill_rate", "edge", "won"]


def test_cli_writes_json_and_exits_zero(tmp_path, capsys):
    _write_depth(tmp_path, "2026-08-03", [
        _depth_line("KXNFLGAME-26AUG03AAABBB-AAA", "c1"),
        _depth_line("KXNFLGAME-26AUG03AAABBB-AAA", "c2"),
    ])
    out = tmp_path / "report.json"
    rc = A.main(["--tape-root", str(tmp_path), "--json", str(out)])
    assert rc == 0
    blob = json.loads(out.read_text())
    assert blob["schema_version"] == "kalshi_trades_backfill_population_audit.v1"
    assert blob["offline"] is True
    assert "backfill-population audit" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# HARD acceptance tests over the real committed tape
# --------------------------------------------------------------------------- #
REAL_TAPE = A.DEFAULT_TAPE_ROOT
_HAS_TAPE = (REAL_TAPE / "orderbook_depth").exists() and (REAL_TAPE / "kalshi_trades").exists()
pytestmark_real = pytest.mark.skipif(not _HAS_TAPE, reason="committed tape not present")


@pytestmark_real
def test_acceptance_kalshi_trades_has_no_scheduled_writer_in_this_repo():
    """The load-bearing half of the finding: waiting adds zero trade days.

    Exact (not a bound): this reads source files, not tape, so a step-0b sweep cannot move
    it. If someone wires the collector into hourly_pass.py, this test SHOULD fail and the
    Q52/Q54 gate framing must be revisited — that is the intended alarm.
    """
    c = A.writer_census()
    assert c["callers_absent"] == ()
    assert c["has_scheduled_writer"] is False, c["callers_referencing"]


@pytestmark_real
def test_acceptance_committed_trade_tape_is_one_day_and_matches_q51_m1s_published_figures():
    inv = A.trade_tape_inventory()
    assert inv["n_days"] >= 1
    assert "2026-08-03" in inv["days"]
    # Q51-m1 published 39,698 prints across 42 tickers with >=1 print. Bounds, per L280.
    assert inv["n_lines"] >= 39698
    assert inv["n_distinct_tickers"] >= 42
    assert inv["n_duplicate_trade_ids"] == 0
    assert inv["price_source_tag_census"].get("broker_truth", 0) >= 39698


@pytestmark_real
def test_acceptance_one_real_day_clears_the_eligibility_and_sports_rollup():
    """dt=2026-08-03 — the only day with a trade capture, so the natural control day."""
    f = A.funnel(days=["dt=2026-08-03"])
    row = f["per_day"][0]
    assert row["n_tickers"] >= 2713          # Q51-m1's own universe figure for that day
    assert row["n_eligible"] >= 729
    assert row["n_sports_games_eligible"] >= 271
    # 7 game units settled from committed sources on that day == Q51 milestone 2's own n.
    assert row["n_sports_games_settled"] >= 7


@pytestmark_real
def test_acceptance_committed_tape_already_holds_far_more_settled_units_than_the_l41_floor():
    """The headline. 338 distinct settled sports games sit in committed book tape with a
    binary broker_truth outcome; only the trade-print leg is missing. Bound, per L280."""
    f = A.funnel()
    agg = f["aggregate"]
    assert agg["n_days"] >= 31
    assert agg["n_sports_games_eligible_union"] >= 2575
    assert agg["n_sports_games_settled_union"] >= 338
    assert agg["n_sports_games_settled_union"] >= 10 * A.L41_UNIT_FLOOR


@pytestmark_real
def test_acceptance_gate_classifies_as_backfill_not_calendar():
    rep = A.run()
    assert rep["gate"]["gate_class"] == "backfill"
    assert rep["gate"]["waiting_adds_days"] is False
    assert rep["gate"]["multiple_of_floor"] >= 33.0
    # Even after the measured ticker-level print haircut the population clears the floor.
    assert rep["projection"]["projected_multiple_of_floor"] >= 7.0
    assert rep["projection"]["is_projection"] is True
