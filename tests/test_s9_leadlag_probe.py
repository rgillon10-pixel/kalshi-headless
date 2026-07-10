"""scripts.s9_leadlag_probe — pooled lead-lag cross-correlation over polymarket_pairs tape.
Offline: synthetic in-memory records only, no filesystem tape dependency, no network."""
from __future__ import annotations

import json

import pytest

from scripts import s9_leadlag_probe as probe


def _rec(capture_id, ticker, kalshi_ask, poly_ask, book_fetch_ok=True):
    return {
        "capture_id": capture_id,
        "kalshi": {"ticker": ticker, "yes_ask": kalshi_ask},
        "polymarket": {"best_ask": poly_ask, "book_fetch_ok": book_fetch_ok},
    }


# --------------------------------------------------------------------------- #
# build_series
# --------------------------------------------------------------------------- #
def test_build_series_sorts_by_capture_and_groups_by_ticker():
    records = [
        _rec("c2", "T1", 0.20, 0.21),
        _rec("c1", "T1", 0.19, 0.20),
        _rec("c1", "T2", 0.50, 0.51),
    ]
    series = probe.build_series(records)
    assert list(series.keys()) == ["T1", "T2"]
    assert series["T1"] == [("c1", 0.19, 0.20), ("c2", 0.20, 0.21)]
    assert series["T2"] == [("c1", 0.50, 0.51)]


def test_build_series_drops_failed_book_fetch():
    records = [_rec("c1", "T1", 0.19, 0.20, book_fetch_ok=False)]
    assert probe.build_series(records) == {}


def test_build_series_drops_incomplete_records():
    records = [{"capture_id": "c1", "kalshi": {"ticker": "T1"}, "polymarket": {"book_fetch_ok": True}}]
    assert probe.build_series(records) == {}


def test_build_series_last_write_wins_on_duplicate_capture_id():
    records = [_rec("c1", "T1", 0.19, 0.20), _rec("c1", "T1", 0.22, 0.23)]
    series = probe.build_series(records)
    assert series["T1"] == [("c1", 0.22, 0.23)]


# --------------------------------------------------------------------------- #
# deltas / pearson
# --------------------------------------------------------------------------- #
def test_deltas_consecutive_steps():
    rows = [("c1", 0.10, 0.20), ("c2", 0.12, 0.19), ("c3", 0.12, 0.25)]
    dk, dp = zip(*probe.deltas(rows))
    assert list(dk) == pytest.approx([0.02, 0.0])
    assert list(dp) == pytest.approx([-0.01, 0.06])


def test_deltas_single_row_is_empty():
    assert probe.deltas([("c1", 0.10, 0.20)]) == []


def test_pearson_perfect_positive():
    assert probe.pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)


def test_pearson_perfect_negative():
    assert probe.pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)


def test_pearson_needs_at_least_two_points():
    assert probe.pearson([1.0], [2.0]) is None


def test_pearson_zero_variance_is_none():
    assert probe.pearson([1, 1, 1], [1, 2, 3]) is None


# --------------------------------------------------------------------------- #
# pooled_leadlag — synthetic controlled lead-lag relationship
# --------------------------------------------------------------------------- #
def test_pooled_leadlag_detects_kalshi_leading_polymarket():
    """Construct a market where polymarket's move at step t+1 always equals kalshi's move
    at step t (kalshi leads by exactly one capture) and confirm the pooled stat picks up
    the correct lag direction, not the reverse or contemporaneous one."""
    kalshi_prices = [0.10, 0.12, 0.12, 0.15, 0.15, 0.20]
    poly_prices = [0.10, 0.10, 0.12, 0.12, 0.15, 0.15]  # polymarket = kalshi shifted +1 step
    rows = [(f"c{i}", k, p) for i, (k, p) in enumerate(zip(kalshi_prices, poly_prices))]
    series = {"T1": rows}

    result = probe.pooled_leadlag(series, min_captures=1)
    assert result["n_markets_used"] == 1
    assert result["rho_kalshi_leads_polymarket"] == pytest.approx(1.0)
    assert result["rho_polymarket_leads_kalshi"] < 1.0


def test_pooled_leadlag_respects_min_captures_floor():
    rows = [("c0", 0.10, 0.20), ("c1", 0.11, 0.21)]
    series = {"T1": rows}
    result = probe.pooled_leadlag(series, min_captures=10)
    assert result["n_markets_used"] == 0
    assert result["rho_contemporaneous"] is None


def test_pooled_leadlag_empty_series():
    result = probe.pooled_leadlag({}, min_captures=1)
    assert result["n_markets_used"] == 0
    assert result["n_steps_contemporaneous"] == 0


# --------------------------------------------------------------------------- #
# shock_events
# --------------------------------------------------------------------------- #
def test_shock_events_flags_moves_at_or_past_threshold():
    rows = [("c0", 0.10, 0.20), ("c1", 0.11, 0.20), ("c2", 0.12, 0.30)]
    series = {"T1": rows}
    events = probe.shock_events(series, threshold=0.05, min_captures=1)
    assert len(events) == 1
    assert events[0]["capture_id"] == "c2"
    assert events[0]["delta_polymarket"] == pytest.approx(0.10)


def test_shock_events_below_threshold_is_empty():
    rows = [("c0", 0.10, 0.20), ("c1", 0.11, 0.21)]
    events = probe.shock_events({"T1": rows}, threshold=0.05, min_captures=1)
    assert events == []


def test_shock_events_respects_min_captures():
    rows = [("c0", 0.10, 0.20), ("c1", 0.50, 0.20)]
    events = probe.shock_events({"T1": rows}, threshold=0.01, min_captures=10)
    assert events == []


# --------------------------------------------------------------------------- #
# market_membership_changes
# --------------------------------------------------------------------------- #
def test_membership_changes_detects_added_and_removed():
    records = [
        _rec("c1", "T1", 0.1, 0.1),
        _rec("c1", "T2", 0.1, 0.1),
        _rec("c2", "T1", 0.1, 0.1),
        _rec("c2", "T3", 0.1, 0.1),
    ]
    changes = probe.market_membership_changes(records)
    assert changes == [{"capture_id": "c2", "added": ["T3"], "removed": ["T2"]}]


def test_membership_changes_no_change_is_empty():
    records = [_rec("c1", "T1", 0.1, 0.1), _rec("c2", "T1", 0.11, 0.11)]
    assert probe.market_membership_changes(records) == []


def test_membership_changes_single_capture_has_no_prior_to_compare():
    records = [_rec("c1", "T1", 0.1, 0.1)]
    assert probe.market_membership_changes(records) == []


# --------------------------------------------------------------------------- #
# build_report — end-to-end wiring, offline tape dir
# --------------------------------------------------------------------------- #
def test_build_report_reads_jsonl_files(tmp_path):
    tape_dir = tmp_path / "polymarket_pairs"
    tape_dir.mkdir()
    lines = [
        _rec(f"c{i}", "T1", 0.10 + 0.01 * i, 0.20 + 0.01 * i) for i in range(12)
    ]
    (tape_dir / "dt=2026-07-05.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")

    report = probe.build_report(tape_dir, min_captures=10)
    assert report["n_records"] == 12
    assert report["n_distinct_captures"] == 12
    assert report["n_distinct_markets"] == 1
    assert report["n_markets_min_captures"] == 1
    assert report["leadlag"]["n_markets_used"] == 1
    assert report["membership_changes"] == []
