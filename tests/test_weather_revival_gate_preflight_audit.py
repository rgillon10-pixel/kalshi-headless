"""Offline unit tests for scripts/weather_revival_gate_preflight_audit.py.

No network anywhere: every fixture is a synthetic tmp_path JSONL day-file. The tests pin the
three things the 2026-07-31 pre-flight finding actually claims — that phantom gate days are
detected and attributed, that settlement COVERAGE and settlement JOINABILITY are measured
separately (they fail for different reasons), and that a missing gitignored signal lane is
reported as an availability fact rather than swallowed.

L191 / Q42 test-hygiene discipline: the one test that reads the REAL committed tape asserts a
MONOTONE property (post-fix count never exceeds pre-fix count; phantom days are never in-window),
never an exact count over an open-ended, still-growing glob.
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.q37_weather_summer_makerno_probe import SUMMER_END, SUMMER_START
from scripts.weather_revival_gate_preflight_audit import (
    DEFAULT_BOOKS_DIR,
    audit_gate_integrity,
    audit_settlement_leg,
    audit_signal_leg,
    projected_gate_open,
    run,
)


def _book_row(ticker, group="daily"):
    return {"group": group, "ticker": ticker, "captured_at": "2026-07-14T12:00:00Z",
            "close_time": "2026-07-16T05:59:00Z", "best_yes_ask": 0.10, "best_yes_bid": 0.05,
            "best_no_ask": 0.95, "best_no_bid": 0.90, "no_bids": [[0.90, 100.0]]}


def _write(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# (A) gate integrity
# --------------------------------------------------------------------------- #
def test_phantom_gate_days_detected_and_attributed(tmp_path):
    books = tmp_path / "books"
    _write(books / "dt=2026-07-14.jsonl", [
        _book_row("KXHIGHNY-26JUL15-B90.5"),
        _book_row("KXHIGHNY-26JUL16-B90.5"),
        _book_row("KXARCTICICEMIN-26OCT01-T4.5"),     # non-temperature AND out of window
        _book_row("KXARCTICICEMIN-26OCT01-T4.6"),
        _book_row("KXTXURI-28DEC31-27JAN01"),         # non-temperature AND far future
    ])
    g = audit_gate_integrity(str(books))
    assert g["summer_days_prefix_rule"] == 4        # 07-15, 07-16, 10-01, 28-12-31
    assert g["summer_days_postfix_rule"] == 2       # only the two real temperature days
    assert g["phantom_gate_days"] == ["2026-10-01", "2028-12-31"]
    assert g["n_phantom_snapshots"] == 3
    assert g["phantom_snapshots_by_series"] == {
        "KXARCTICICEMIN|2026-10-01": 2, "KXTXURI|2028-12-31": 1}
    assert g["real_contract_days"] == ["2026-07-15", "2026-07-16"]


def test_non_daily_rows_never_counted(tmp_path):
    books = tmp_path / "books"
    _write(books / "dt=2026-07-14.jsonl", [
        _book_row("KXHIGHNY-26JUL15-B90.5"),
        _book_row("KXTEMPNYCH-26JUL15-B90.5", group="hourly"),
    ])
    g = audit_gate_integrity(str(books))
    assert g["n_daily_rows_parsed"] == 1
    assert g["summer_days_postfix_rule"] == 1


def test_projection_is_optimistic_and_none_when_open():
    # 17 real days on 07-31 -> 4 more calendar days at the optimistic 1/day rate
    assert projected_gate_open(17, date(2026, 7, 31), required=21) == "2026-08-04"
    # the contaminated counter buys exactly the phantom count in days
    assert projected_gate_open(19, date(2026, 7, 31), required=21) == "2026-08-02"
    assert projected_gate_open(21, date(2026, 7, 31), required=21) is None
    assert projected_gate_open(25, date(2026, 7, 31), required=21) is None


# --------------------------------------------------------------------------- #
# (B) settlement leg — coverage and joinability are separate measurements
# --------------------------------------------------------------------------- #
def _actual_rec(event_ticker, results, tag="broker_truth", exp="90.00"):
    return {"schema_version": "weather_actuals.v1",
            "settled_markets": {"errors": [], "events": [
                {"event_ticker": event_ticker, "expiration_value": exp,
                 "price_source_tag": tag, "results": results}]}}


def test_settlement_coverage_vs_join_precision_are_distinct(tmp_path):
    books, actuals = tmp_path / "books", tmp_path / "actuals"
    _write(books / "dt=2026-07-14.jsonl", [
        _book_row("KXHIGHNY-26JUL15-B90.5"),
        _book_row("KXHIGHNY-26JUL16-B90.5"),
        _book_row("KXHIGHAUS-26JUL15-B99.5"),
    ])
    # settlement exists for ONE of the three book groups, and it joins perfectly
    _write(actuals / "dt=2026-07-16.jsonl",
           [_actual_rec("KXHIGHNY-26JUL15", {"KXHIGHNY-26JUL15-B90.5": "yes"})])
    s = audit_settlement_leg(str(actuals), str(books))
    assert s["n_book_groups"] == 3
    assert s["n_book_groups_with_actual"] == 1
    assert s["book_group_settlement_coverage"] == round(1 / 3, 4)   # COVERAGE is poor
    assert s["join_precision_groups"] == 1.0                        # JOINABILITY is perfect
    assert s["join_precision_tickers"] == 1.0
    assert s["n_orphan_actual_groups"] == 0
    assert s["n_settled_contract_days"] == 1


def test_non_broker_truth_settlement_is_refused(tmp_path):
    """Trust default: a settlement event not tagged broker_truth is NOT settlement truth."""
    books, actuals = tmp_path / "books", tmp_path / "actuals"
    _write(books / "dt=2026-07-14.jsonl", [_book_row("KXHIGHNY-26JUL15-B90.5")])
    _write(actuals / "dt=2026-07-16.jsonl", [
        _actual_rec("KXHIGHNY-26JUL15", {"KXHIGHNY-26JUL15-B90.5": "yes"}, tag="synthetic")])
    s = audit_settlement_leg(str(actuals), str(books))
    assert s["n_events_not_broker_truth"] == 1
    assert s["n_settled_result_tickers"] == 0
    assert s["n_book_groups_with_actual"] == 0


def test_orphan_actuals_are_surfaced(tmp_path):
    """An actual whose group has no book coverage is an orphan, not silently dropped."""
    books, actuals = tmp_path / "books", tmp_path / "actuals"
    _write(books / "dt=2026-07-14.jsonl", [_book_row("KXHIGHNY-26JUL15-B90.5")])
    _write(actuals / "dt=2026-07-16.jsonl", [
        _actual_rec("KXHIGHNY-26JUL15", {"KXHIGHNY-26JUL15-B90.5": "yes"}),
        _actual_rec("KXHIGHMIA-26JUL15", {"KXHIGHMIA-26JUL15-B95.5": "no"}),
    ])
    s = audit_settlement_leg(str(actuals), str(books))
    assert s["n_orphan_actual_groups"] == 1
    assert s["n_orphan_result_tickers"] == 1
    assert s["join_precision_groups"] == 0.5


def test_missing_actuals_dir_is_zeroes_not_a_crash(tmp_path):
    books = tmp_path / "books"
    _write(books / "dt=2026-07-14.jsonl", [_book_row("KXHIGHNY-26JUL15-B90.5")])
    s = audit_settlement_leg(str(tmp_path / "nope"), str(books))
    assert s["n_day_files"] == 0 and s["n_lines"] == 0
    assert s["book_group_settlement_coverage"] == 0.0
    assert s["join_precision_groups"] is None       # undefined, NOT 0.0 — nothing to divide


# --------------------------------------------------------------------------- #
# (C) signal leg
# --------------------------------------------------------------------------- #
def test_signal_leg_absent_and_present(tmp_path):
    absent = audit_signal_leg(str(tmp_path / "nope"))
    assert absent["dir_present"] is False and absent["emos_input_available"] is False
    fc = tmp_path / "fc"
    fc.mkdir()
    (fc / "2026-07-30.jsonl").write_text('{"city":"NYC"}\n', encoding="utf-8")
    present = audit_signal_leg(str(fc))
    assert present["dir_present"] is True and present["emos_input_available"] is True
    assert present["n_files"] == 1


# --------------------------------------------------------------------------- #
# orchestration + the one real-tape (monotone) pin
# --------------------------------------------------------------------------- #
def test_run_shape_declares_verdict_class(tmp_path):
    books = tmp_path / "books"
    _write(books / "dt=2026-07-14.jsonl", [_book_row("KXHIGHNY-26JUL15-B90.5")])
    rep = run(str(books), str(tmp_path / "a"), str(tmp_path / "f"), as_of=date(2026, 7, 31))
    assert "no CI" in rep["verdict_class"] and "no registry change" in rep["verdict_class"]
    assert set(rep) >= {"gate_integrity", "settlement_leg", "signal_leg", "as_of"}


def test_real_tape_monotone_pin():
    """Over the COMMITTED tape: the tightened rule can only ever admit FEWER days, and no phantom
    day is ever inside the summer window. Monotone by construction — safe as tape grows."""
    g = audit_gate_integrity(str(DEFAULT_BOOKS_DIR))
    if g["n_daily_rows_parsed"] == 0:
        return                                    # tape absent in this checkout
    assert g["summer_days_postfix_rule"] <= g["summer_days_prefix_rule"]
    # a phantom day is by definition one the tightened rule refuses — it must never also appear
    # as a real admitted day (that would mean the two rules disagree about the same day twice)
    real = set(g["real_contract_days"])
    for d in g["phantom_gate_days"]:
        assert d not in real, d
    for d in g["real_contract_days"]:
        assert SUMMER_START <= date.fromisoformat(d) <= SUMMER_END
    assert (g["n_phantom_gate_days"]
            == g["summer_days_prefix_rule"] - g["summer_days_postfix_rule"])
