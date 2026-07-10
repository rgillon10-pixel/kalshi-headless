"""scripts.s9_shock_eventstudy — event-study around real KXWCROUND round-transition shocks.
Offline: synthetic in-memory records only, no filesystem tape dependency, no network."""
from __future__ import annotations

import json

import pytest

from scripts import s9_shock_eventstudy as study


def _rec(capture_id, ticker, kalshi_ask, poly_ask, book_fetch_ok=True):
    return {
        "capture_id": capture_id,
        "kalshi": {"ticker": ticker, "yes_ask": kalshi_ask},
        "polymarket": {"best_ask": poly_ask, "book_fetch_ok": book_fetch_ok},
    }


# --------------------------------------------------------------------------- #
# parse_capture_id
# --------------------------------------------------------------------------- #
def test_parse_capture_id_valid():
    dt = study.parse_capture_id("20260705T222356Z")
    assert dt is not None
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second) == (2026, 7, 5, 22, 23, 56)


def test_parse_capture_id_invalid_is_none():
    assert study.parse_capture_id("not-a-capture-id") is None


# --------------------------------------------------------------------------- #
# real_transition_events — startup-artifact exclusion
# --------------------------------------------------------------------------- #
def test_real_transition_events_excludes_startup_capture():
    """The diff INTO the documented continuous-collection-start capture is a startup
    artifact (smoke-test capture vs first real hourly capture), not an in-window shock."""
    start = study.CONTINUOUS_COLLECTION_START_CAPTURE
    records = [
        _rec("20260704T151554Z", "T_STARTUP_ONLY", 0.1, 0.1),
        _rec(start, "T_CONTINUING", 0.1, 0.1),
        _rec("20260705T012348Z", "T_CONTINUING", 0.1, 0.1),
    ]
    assert study.real_transition_events(records) == []


def test_real_transition_events_keeps_later_transitions():
    start = study.CONTINUOUS_COLLECTION_START_CAPTURE
    records = [
        _rec(start, "T1", 0.1, 0.1),
        _rec(start, "T2", 0.1, 0.1),
        _rec("20260705T012348Z", "T1", 0.1, 0.1),  # T2 vanished here
    ]
    events = study.real_transition_events(records)
    assert events == [{"capture_id": "20260705T012348Z", "added": [], "removed": ["T2"]}]


# --------------------------------------------------------------------------- #
# event_study_for_ticker
# --------------------------------------------------------------------------- #
def test_event_study_uses_last_two_rows_not_the_vanish_capture():
    """The capture where a ticker vanishes is never itself a price row for that ticker —
    the real repricing is the LAST observed step before it drops out."""
    rows = [
        ("c0", 0.50, 0.51),
        ("c1", 0.68, 0.68),
        ("c2", 0.01, 0.02),
    ]
    result = study.event_study_for_ticker(rows)
    assert result["pre_capture"] == "c1"
    assert result["post_capture"] == "c2"
    assert result["delta_kalshi"] == pytest.approx(-0.67)
    assert result["delta_polymarket"] == pytest.approx(-0.66)


def test_event_study_computes_wall_clock_gap_minutes():
    rows = [("20260705T212422Z", 0.68, 0.68), ("20260705T215437Z", 0.01, 0.021)]
    result = study.event_study_for_ticker(rows)
    assert result["gap_minutes"] == pytest.approx(30.25, abs=0.01)


def test_event_study_needs_at_least_two_rows():
    assert study.event_study_for_ticker([("c0", 0.5, 0.5)]) is None
    assert study.event_study_for_ticker([]) is None


# --------------------------------------------------------------------------- #
# build_report — end-to-end wiring, offline tape dir
# --------------------------------------------------------------------------- #
def test_build_report_reports_real_transition_only(tmp_path):
    tape_dir = tmp_path / "polymarket_pairs"
    tape_dir.mkdir()
    start = study.CONTINUOUS_COLLECTION_START_CAPTURE
    lines = [
        _rec("20260704T151554Z", "T_STARTUP_ONLY", 0.1, 0.1),
        _rec(start, "T1", 0.50, 0.51),
        _rec(start, "T2", 0.34, 0.33),
        _rec("20260705T005445Z", "T1", 0.50, 0.51),
        _rec("20260705T005445Z", "T2", 0.68, 0.68),
        _rec("20260705T012348Z", "T1", 0.51, 0.50),
        # T2 vanishes at 012348Z (its last row is at 005445Z)
    ]
    (tape_dir / "dt=2026-07-05.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")

    report = study.build_report(tape_dir)
    assert report["n_real_transition_events"] == 1
    event = report["events"][0]
    assert event["vanish_capture_id"] == "20260705T012348Z"
    assert event["removed"] == ["T2"]
    assert len(event["ticker_studies"]) == 1
    assert event["ticker_studies"][0]["ticker"] == "T2"
    assert event["ticker_studies"][0]["pre_capture"] == start
    assert event["ticker_studies"][0]["post_capture"] == "20260705T005445Z"


def test_build_report_no_transitions_is_empty(tmp_path):
    tape_dir = tmp_path / "polymarket_pairs"
    tape_dir.mkdir()
    lines = [_rec("c0", "T1", 0.1, 0.1), _rec("c1", "T1", 0.11, 0.11)]
    (tape_dir / "dt=2026-07-05.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")

    report = study.build_report(tape_dir)
    assert report["n_real_transition_events"] == 0
    assert report["events"] == []


def test_main_runs_end_to_end_against_real_tape(capsys):
    """Smoke test against whatever the repo's actual tape/polymarket_pairs/ currently holds —
    must not raise regardless of how many real transitions have accumulated."""
    rc = study.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "S9 SHOCK EVENT-STUDY" in out
