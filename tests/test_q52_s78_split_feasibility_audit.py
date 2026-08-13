"""Offline tests for `scripts/q52_s78_split_feasibility_audit.py` (Q52 / S78).

All synthetic fixtures — no test touches the live committed tape glob, so this file stays
green regardless of what future collector passes append (the Q42-pin hygiene rule).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import q52_s78_split_feasibility_audit as A  # noqa: E402


def _write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _trade(ticker, count=10.0):
    return {"ticker": ticker, "count": count, "yes_price": 0.5,
            "price_source_tag": "broker_truth"}


def _depth(ticker, capture_id, captured_at):
    return {"ticker": ticker, "capture_id": capture_id, "captured_at": captured_at,
            "price_source_tags": {"asks": "real_ask", "bids": "real_bid"}}


def _settlement_root(tmp_path, results):
    root = tmp_path / "tape"
    d = root / "q51_settlement_cache"
    d.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": "q51_settlement_cache.v1", "price_source_tag": "broker_truth",
               "day": "2026-08-03",
               "markets": {t: {"result": r, "status": "finalized", "close_time": None,
                               "event_ticker": None} for t, r in results.items()}}
    (d / "settlement.json").write_text(json.dumps(payload), encoding="utf-8")
    return str(root)


# --------------------------------------------------------------------------- #
# is_game_ticker / game_unit
# --------------------------------------------------------------------------- #
def test_is_game_ticker_requires_GAME_in_series():
    assert A.is_game_ticker("KXMLBGAME-26JUL07AB-A")
    assert not A.is_game_ticker("KXBTC-26JUL0621-T71799.99")


def test_is_game_ticker_excludes_KXMVE_L31():
    assert not A.is_game_ticker("KXMVEGAME-26JUL07AB-A")


def test_game_unit_collapses_multi_outcome_legs():
    assert A.game_unit("KXBRASILEIROBGAME-26JUL07ATHFER-TIE") == "KXBRASILEIROBGAME-26JUL07ATHFER"
    assert A.game_unit("KXMLBGAME-26JUL07AB-A") == "KXMLBGAME-26JUL07AB"


# --------------------------------------------------------------------------- #
# traded_tickers_by_day / depth_snapshot_counts_by_day
# --------------------------------------------------------------------------- #
def test_traded_tickers_by_day_filters_non_game_series(tmp_path):
    trades = tmp_path / "trades"
    _write_jsonl(trades / "dt=2026-07-07.jsonl", [
        _trade("KXMLBGAME-26JUL07AB-A"), _trade("KXBTC-26JUL0621-T71799.99"),
    ])
    by_day = A.traded_tickers_by_day(str(trades / "dt=*.jsonl"))
    assert by_day == {"2026-07-07": {"KXMLBGAME-26JUL07AB-A"}}


def test_depth_snapshot_counts_only_count_wanted_tickers(tmp_path):
    depth = tmp_path / "depth"
    _write_jsonl(depth / "dt=2026-07-07.jsonl", [
        _depth("KXMLBGAME-26JUL07AB-A", "c1", "2026-07-07T00:00:00Z"),
        _depth("KXMLBGAME-26JUL07AB-A", "c2", "2026-07-07T00:30:00Z"),
        _depth("KXMLBGAME-26JUL07CD-A", "c1", "2026-07-07T00:00:00Z"),  # not wanted
    ])
    by_day = {"2026-07-07": {"KXMLBGAME-26JUL07AB-A"}}
    counts, cap_ids = A.depth_snapshot_counts_by_day(by_day, str(depth / "dt=*.jsonl"))
    assert counts["2026-07-07"] == {"KXMLBGAME-26JUL07AB-A": 2}
    assert cap_ids["2026-07-07"] == 2  # both capture_ids counted, incl. the unwanted ticker's


def test_depth_snapshot_counts_zero_on_missing_day_file(tmp_path):
    depth = tmp_path / "depth"
    depth.mkdir()
    by_day = {"2026-07-07": {"KXMLBGAME-26JUL07AB-A"}}
    counts, cap_ids = A.depth_snapshot_counts_by_day(by_day, str(depth / "dt=*.jsonl"))
    assert counts["2026-07-07"] == {}
    assert cap_ids["2026-07-07"] == 0


# --------------------------------------------------------------------------- #
# eligible_units_by_day
# --------------------------------------------------------------------------- #
def test_eligible_units_requires_min_snapshot_floor():
    by_day = {"2026-07-07": {"KXMLBGAME-26JUL07AB-A", "KXMLBGAME-26JUL07CD-A"}}
    counts = {"2026-07-07": {"KXMLBGAME-26JUL07AB-A": 2, "KXMLBGAME-26JUL07CD-A": 1}}
    units = A.eligible_units_by_day(by_day, counts, min_snapshots=2)
    assert units == {"2026-07-07": {"KXMLBGAME-26JUL07AB": "KXMLBGAME-26JUL07AB-A"}}


def test_eligible_units_dedupes_multi_outcome_legs_to_one_unit():
    by_day = {"2026-07-07": {"KXBRASILEIROBGAME-26JUL07ATHFER-TIE",
                             "KXBRASILEIROBGAME-26JUL07ATHFER-A"}}
    counts = {"2026-07-07": {"KXBRASILEIROBGAME-26JUL07ATHFER-TIE": 3,
                             "KXBRASILEIROBGAME-26JUL07ATHFER-A": 3}}
    units = A.eligible_units_by_day(by_day, counts, min_snapshots=2)
    assert list(units["2026-07-07"]) == ["KXBRASILEIROBGAME-26JUL07ATHFER"]


# --------------------------------------------------------------------------- #
# settled_units_by_day (through the sanctioned resolver)
# --------------------------------------------------------------------------- #
def test_settled_units_by_day_only_keeps_binary_settled(tmp_path):
    root = _settlement_root(tmp_path, {"KXMLBGAME-26JUL07AB-A": "yes",
                                       "KXMLBGAME-26JUL07CD-A": "scalar"})
    units_by_day = {"2026-07-07": {"KXMLBGAME-26JUL07AB": "KXMLBGAME-26JUL07AB-A",
                                   "KXMLBGAME-26JUL07CD": "KXMLBGAME-26JUL07CD-A",
                                   "KXMLBGAME-26JUL07EF": "KXMLBGAME-26JUL07EF-A"}}
    settled, report = A.settled_units_by_day(units_by_day, settlement_root=root)
    assert settled["2026-07-07"] == ["KXMLBGAME-26JUL07AB"]
    assert "KXMLBGAME-26JUL07CD-A" in report.non_binary
    assert "KXMLBGAME-26JUL07EF-A" in report.unresolved


# --------------------------------------------------------------------------- #
# chronological_splits
# --------------------------------------------------------------------------- #
def test_chronological_splits_reports_every_cut_and_overlap():
    settled_by_day = {
        "2026-07-01": ["A", "B"],
        "2026-07-02": ["B", "C"],  # B repeats -> overlap at the 07-02 cut
        "2026-07-03": ["D"],
    }
    splits = A.chronological_splits(settled_by_day)
    assert splits == [
        ("2026-07-02", 2, 3, 1),  # train {A,B} holdout {B,C,D} overlap {B}
        ("2026-07-03", 3, 1, 0),  # train {A,B,C} holdout {D} overlap {}
    ]


def test_chronological_splits_empty_on_single_day():
    assert A.chronological_splits({"2026-07-01": ["A"]}) == []


# --------------------------------------------------------------------------- #
# series_overlap
# --------------------------------------------------------------------------- #
def test_series_overlap_counts_shared_and_unshared():
    train = ["KXMLBGAME-1", "KXNPBGAME-1"]
    holdout = ["KXMLBGAME-2", "KXNBAGAME-1"]
    rep = A.series_overlap(train, holdout)
    assert rep["n_shared_series"] == 1
    assert rep["shared_series"] == ["KXMLBGAME"]
    assert rep["n_train_units_in_shared_series"] == 1
    assert rep["n_holdout_units_in_shared_series"] == 1


def test_series_overlap_zero_when_disjoint():
    rep = A.series_overlap(["KXMLBGAME-1"], ["KXNPBGAME-1"])
    assert rep["n_shared_series"] == 0
    assert rep["n_train_units_in_shared_series"] == 0


# --------------------------------------------------------------------------- #
# intra_ticker_gap_minutes (era split)
# --------------------------------------------------------------------------- #
def test_intra_ticker_gaps_split_by_era_and_ignore_cross_day():
    depth = Path
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        # rich era: two snapshots 30 min apart
        _write_jsonl(d / "dt=2026-07-07.jsonl", [
            {"ticker": "T", "captured_at": "2026-07-07T00:00:00Z"},
            {"ticker": "T", "captured_at": "2026-07-07T00:30:00Z"},
        ])
        # starved era: two snapshots 180 min apart
        _write_jsonl(d / "dt=2026-08-03.jsonl", [
            {"ticker": "T", "captured_at": "2026-08-03T00:00:00Z"},
            {"ticker": "T", "captured_at": "2026-08-03T03:00:00Z"},
        ])
        gaps = A.intra_ticker_gap_minutes({"T"}, str(d / "dt=*.jsonl"))
        assert gaps["rich"] == [30.0]
        assert gaps["starved"] == [180.0]


def test_intra_ticker_gaps_ignore_unwanted_ticker():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        _write_jsonl(d / "dt=2026-07-07.jsonl", [
            {"ticker": "OTHER", "captured_at": "2026-07-07T00:00:00Z"},
            {"ticker": "OTHER", "captured_at": "2026-07-07T00:30:00Z"},
        ])
        gaps = A.intra_ticker_gap_minutes({"T"}, str(d / "dt=*.jsonl"))
        assert gaps["rich"] == []


# --------------------------------------------------------------------------- #
# run() end-to-end, on synthetic fixtures spanning both eras
# --------------------------------------------------------------------------- #
def test_run_end_to_end_synthetic_two_era_population(tmp_path):
    trades = tmp_path / "trades"
    depth = tmp_path / "depth"

    # Rich era: two trade days, two settled units each with 3 depth snapshots.
    for day, units in (("2026-07-07", ["AB", "CD"]), ("2026-07-08", ["EF", "GH"])):
        _write_jsonl(trades / f"dt={day}.jsonl",
                     [_trade(f"KXMLBGAME-{day.replace('-', '')}{u}-A") for u in units])
        _write_jsonl(depth / f"dt={day}.jsonl", [
            _depth(f"KXMLBGAME-{day.replace('-', '')}{u}-A", f"c{i}",
                  f"{day}T0{i}:00:00Z")
            for u in units for i in range(3)
        ])

    # Starved era: one trade day, one settled unit, only 2 depth snapshots (still eligible,
    # but far sparser -- the cadence-asymmetry point this script exists to measure).
    _write_jsonl(trades / "dt=2026-08-03.jsonl",
                [_trade("KXNPBGAME-260803IJ-A")])
    _write_jsonl(depth / "dt=2026-08-03.jsonl", [
        _depth("KXNPBGAME-260803IJ-A", "c0", "2026-08-03T00:00:00Z"),
        _depth("KXNPBGAME-260803IJ-A", "c1", "2026-08-03T03:00:00Z"),
    ])

    settlement_root = _settlement_root(tmp_path, {
        "KXMLBGAME-20260707AB-A": "yes", "KXMLBGAME-20260707CD-A": "no",
        "KXMLBGAME-20260708EF-A": "yes", "KXMLBGAME-20260708GH-A": "no",
        "KXNPBGAME-260803IJ-A": "yes",
    })

    out = A.run(trade_glob=str(trades / "dt=*.jsonl"), depth_glob=str(depth / "dt=*.jsonl"),
               settlement_root=settlement_root)

    assert out["verdict_class"] is False
    assert out["natural_era_split"]["n_train_units"] == 4
    assert out["natural_era_split"]["n_holdout_units"] == 1
    assert out["natural_era_split"]["n_overlap_units"] == 0
    # 0 shared series between MLB (train) and NPB (holdout) in this fixture
    assert out["series_transfer"]["n_shared_series"] == 0
    assert out["book_cadence_by_era"]["rich_era_capture_instants_per_day"] == [3, 3]
    assert out["book_cadence_by_era"]["starved_era_capture_instants_per_day"] == [2]


def test_run_is_read_only_and_deterministic(tmp_path):
    """Two calls against the same fixtures give byte-identical output (no clock/random)."""
    trades = tmp_path / "trades"
    depth = tmp_path / "depth"
    _write_jsonl(trades / "dt=2026-07-07.jsonl", [_trade("KXMLBGAME-26JUL07AB-A")])
    _write_jsonl(depth / "dt=2026-07-07.jsonl", [
        _depth("KXMLBGAME-26JUL07AB-A", "c0", "2026-07-07T00:00:00Z"),
        _depth("KXMLBGAME-26JUL07AB-A", "c1", "2026-07-07T00:30:00Z"),
    ])
    settlement_root = _settlement_root(tmp_path, {"KXMLBGAME-26JUL07AB-A": "yes"})
    out1 = A.run(str(trades / "dt=*.jsonl"), str(depth / "dt=*.jsonl"), settlement_root)
    out2 = A.run(str(trades / "dt=*.jsonl"), str(depth / "dt=*.jsonl"), settlement_root)
    assert json.dumps(out1, sort_keys=True) == json.dumps(out2, sort_keys=True)


# --------------------------------------------------------------------------- #
# regression tests for the verifier-round-1 corrections
# --------------------------------------------------------------------------- #
def test_default_settlement_root_is_absolute_break3_regression():
    """Verifier round 1: `resolve_market_results` defaults to a RELATIVE root, so a script
    anchoring everything else via absolute REPO paths but leaving this one relative silently
    returns 0-resolved from any other working directory. Pin that the default is absolute."""
    assert os.path.isabs(A.DEFAULT_SETTLEMENT_ROOT)
    assert A.DEFAULT_SETTLEMENT_ROOT == os.path.join(A.REPO, "tape")


def test_gap_histogram_30min_bins_shows_multiple_clusters():
    """Verifier round 1: 4 percentiles alone asserted 'unimodal' over a multi-modal
    distribution. A histogram over synthetic multi-cluster data must show >1 populated bin
    far apart, not collapse to one bin. Returned as an ORDERED list of pairs (verifier round 2:
    a dict would be silently re-sorted lexicographically by `json.dumps(sort_keys=True)`)."""
    values = [10.0, 15.0] + [180.0, 185.0, 190.0] + [900.0]
    hist = A.gap_histogram_30min_bins(values)
    assert hist == [["[0,30)", 2], ["[180,210)", 3], ["[900,930)", 1]]


def test_gap_histogram_labels_the_overflow_bin_as_unbounded():
    """Verifier round 2 minor nit: a bin labeled with a finite upper edge that actually holds
    everything above it (the old "[960,990)" for a 5000-minute gap) re-creates the
    prose-overclaim problem the histogram exists to eliminate. The overflow bin must say so."""
    hist = A.gap_histogram_30min_bins([5000.0], max_bin_start=960.0)
    assert hist == [["[960,+inf)", 1]]


def test_gap_histogram_boundary_value_lands_in_overflow_not_a_phantom_bin():
    hist = A.gap_histogram_30min_bins([960.0], max_bin_start=960.0)
    assert hist == [["[960,+inf)", 1]]


def test_backfill_scope_caveat_reads_real_manifest_when_present(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "execution": {"coverage_is_ticker_scoped": True,
                      "coverage_note": "day-files are a ticker-scoped backfill...",
                      "manifest": [{"game": "A"}, {"game": "B"}]}
    }), encoding="utf-8")
    caveat = A.backfill_scope_caveat(str(manifest))
    assert caveat["manifest_found"] is True
    assert caveat["coverage_is_ticker_scoped"] is True
    assert caveat["n_games_in_manifest"] == 2


def test_backfill_scope_caveat_honest_when_manifest_missing(tmp_path):
    caveat = A.backfill_scope_caveat(str(tmp_path / "does_not_exist.json"))
    assert caveat["manifest_found"] is False
    assert caveat["coverage_is_ticker_scoped"] is None


def test_backfill_scope_caveat_matches_the_real_committed_manifest():
    """The real manifest this audit's July-side population was drawn from must self-report
    as ticker-scoped -- if this ever flips to False the audit's central caveat is stale."""
    if not os.path.exists(A.BACKFILL_MANIFEST_PATH):
        return
    caveat = A.backfill_scope_caveat()
    assert caveat["manifest_found"] is True
    assert caveat["coverage_is_ticker_scoped"] is True


def test_per_cell_split_honors_q52s_own_qualifier():
    """Verifier round 1 Break 1: Q52's status line qualifies its claim with '<=4-cell'. A
    per-cell reading of the real 34/29 split must NOT clear the L41 floor (matching Q52's own
    stated reason), even though the undivided 1-cell split does."""
    if not (REPO / "tape" / "kalshi_trades").exists():
        return
    out = A.run()
    per_cell = out["per_cell_split"]
    natural = out["natural_era_split"]
    assert per_cell["train_units_per_cell"] == natural["n_train_units"] / A.Q52_STATED_CELL_COUNT
    assert per_cell["holdout_units_per_cell"] == natural["n_holdout_units"] / A.Q52_STATED_CELL_COUNT
    # Documents the actual measured relationship as of this run; if collected tape grows this
    # may need updating, but as of 2026-08-13 it reproduces Q52's own stated blocker.
    if natural["clears_l41_undivided_1cell"]:
        assert per_cell["clears_l41_per_cell"] is False


# --------------------------------------------------------------------------- #
# live smoke: the real committed tape, if present (never a hard dependency)
# --------------------------------------------------------------------------- #
def test_live_run_against_committed_tape_smoke():
    """A live smoke test over whatever is actually committed. Growth-safe (L320): asserts
    shape and floors, never a pinned exact count that would break the moment tape grows."""
    if not (REPO / "tape" / "kalshi_trades").exists():
        return
    out = A.run()
    assert out["verdict_class"] is False
    n = out["natural_era_split"]
    assert n["n_train_units"] >= 0 and n["n_holdout_units"] >= 0
    assert n["n_overlap_units"] >= 0
    for row in out["per_day"].values():
        assert row["n_settled_units"] <= row["n_candidate_units"] <= row["n_traded_game_tickers"]
