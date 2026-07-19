"""Offline unit tests for q36_kxtempnych_settlement_basis_probe.

Q36's main milestone is GATED on >=7 days of tape/weather_books/ coverage; this script
(the settlement-basis sub-study) joins tape/settlement_ledger/ (a different, already-flowing
family) to an independent KNYC ASOS ob and is written + offline-tested now per the idle-run
policy so it fires the day the full gate opens. No network in these tests: a FakeHttp stands
in for validation._http.Http, and settlement_ledger rows are synthetic tmp fixtures.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.q36_kxtempnych_settlement_basis_probe import (
    MIN_EVENTS,
    build_basis_rows,
    fetch_asos_day,
    load_settled_events,
    nearest_ob,
    run,
    summarize,
)


class FakeHttp:
    """Injectable stand-in for validation._http.Http — no network. `pages` maps the ISO date
    string requested to a canned IEM obhistory.json-shaped payload (or an exception class to
    simulate a fetch failure for that day)."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def json(self, url, **params):
        self.calls.append(params)
        day = params["date"]
        page = self.pages.get(day)
        if page is None:
            return {"data": []}
        if isinstance(page, Exception):
            raise page
        return page


def _obhistory_payload(rows):
    return {"data": [{"utc_valid": utc, "tmpf": tmpf} for utc, tmpf in rows]}


def _settlement_rec(event_ticker, ticker, close_time, expiration_value, series="KXTEMPNYCH",
                     result="no", settlement_ts="2026-07-17T12:20:52Z"):
    return {
        "series": series,
        "event_ticker": event_ticker,
        "ticker": ticker,
        "close_time": close_time,
        "expiration_value": expiration_value,
        "result": result,
        "settlement_ts": settlement_ts,
        "price_source_tag": "broker_truth",
    }


def _write_ledger_day(tmp_path, day, records):
    d = tmp_path / f"dt={day}.jsonl"
    d.write_text("\n".join(json.dumps(r) for r in records) + "\n")


# --------------------------------------------------------------------------- #
# load_settled_events
# --------------------------------------------------------------------------- #
def test_load_settled_events_dedupes_by_event_ticker(tmp_path):
    _write_ledger_day(tmp_path, "2026-07-17", [
        _settlement_rec("KXTEMPNYCH-26JUL1707", "KXTEMPNYCH-26JUL1707-T76.99",
                         "2026-07-17T11:00:00Z", "72.00"),
        _settlement_rec("KXTEMPNYCH-26JUL1707", "KXTEMPNYCH-26JUL1707-T74.99",
                         "2026-07-17T11:00:00Z", "72.00"),
    ])
    events = load_settled_events(str(tmp_path))
    assert len(events) == 1
    assert events[0]["event_ticker"] == "KXTEMPNYCH-26JUL1707"
    assert events[0]["twc_value"] == 72.00


def test_load_settled_events_filters_other_series(tmp_path):
    _write_ledger_day(tmp_path, "2026-07-17", [
        _settlement_rec("KXHIGHNY-26JUL17", "KXHIGHNY-26JUL17-T80", "2026-07-17T23:00:00Z",
                         "78.00", series="KXHIGHNY"),
        _settlement_rec("KXTEMPNYCH-26JUL1707", "KXTEMPNYCH-26JUL1707-T74.99",
                         "2026-07-17T11:00:00Z", "72.00"),
    ])
    events = load_settled_events(str(tmp_path))
    assert len(events) == 1
    assert events[0]["event_ticker"] == "KXTEMPNYCH-26JUL1707"


def test_load_settled_events_drops_missing_close_time_or_value(tmp_path):
    _write_ledger_day(tmp_path, "2026-07-17", [
        _settlement_rec("KXTEMPNYCH-A", "KXTEMPNYCH-A-T1", None, "72.00"),
        _settlement_rec("KXTEMPNYCH-B", "KXTEMPNYCH-B-T1", "2026-07-17T11:00:00Z", None),
        _settlement_rec("KXTEMPNYCH-C", "KXTEMPNYCH-C-T1", "2026-07-17T11:00:00Z", "72.00"),
    ])
    events = load_settled_events(str(tmp_path))
    assert [e["event_ticker"] for e in events] == ["KXTEMPNYCH-C"]


def test_load_settled_events_sorted_by_close_time_across_days(tmp_path):
    _write_ledger_day(tmp_path, "2026-07-17", [
        _settlement_rec("KXTEMPNYCH-LATER", "KXTEMPNYCH-LATER-T1",
                         "2026-07-17T15:00:00Z", "80.00"),
    ])
    _write_ledger_day(tmp_path, "2026-07-16", [
        _settlement_rec("KXTEMPNYCH-EARLIER", "KXTEMPNYCH-EARLIER-T1",
                         "2026-07-16T11:00:00Z", "70.00"),
    ])
    events = load_settled_events(str(tmp_path))
    assert [e["event_ticker"] for e in events] == ["KXTEMPNYCH-EARLIER", "KXTEMPNYCH-LATER"]


def test_load_settled_events_skips_malformed_json_line(tmp_path):
    d = tmp_path / "dt=2026-07-17.jsonl"
    d.write_text("not json\n" + json.dumps(
        _settlement_rec("KXTEMPNYCH-A", "KXTEMPNYCH-A-T1", "2026-07-17T11:00:00Z", "72.00")
    ) + "\n")
    events = load_settled_events(str(tmp_path))
    assert len(events) == 1


# --------------------------------------------------------------------------- #
# fetch_asos_day / nearest_ob
# --------------------------------------------------------------------------- #
def test_fetch_asos_day_parses_rows():
    http = FakeHttp({"2026-07-17": _obhistory_payload([
        ("2026-07-17T10:51Z", 71.0),
        ("2026-07-17T11:51Z", 73.0),
    ])})
    obs = fetch_asos_day(http, "2026-07-17")
    assert len(obs) == 2
    assert obs[0]["tmpf"] == 71.0


def test_fetch_asos_day_never_raises_on_http_failure():
    http = FakeHttp({"2026-07-17": RuntimeError("boom")})
    assert fetch_asos_day(http, "2026-07-17") == []


def test_fetch_asos_day_drops_missing_field_rows():
    http = FakeHttp({"2026-07-17": {"data": [
        {"utc_valid": "2026-07-17T10:51Z", "tmpf": None},
        {"utc_valid": None, "tmpf": 71.0},
        {"utc_valid": "2026-07-17T11:51Z", "tmpf": 73.0},
    ]}})
    obs = fetch_asos_day(http, "2026-07-17")
    assert len(obs) == 1
    assert obs[0]["tmpf"] == 73.0


def test_nearest_ob_picks_closest_and_signed_lag():
    obs = [
        {"utc_valid": datetime(2026, 7, 17, 10, 51, tzinfo=timezone.utc), "tmpf": 71.0},
        {"utc_valid": datetime(2026, 7, 17, 11, 51, tzinfo=timezone.utc), "tmpf": 73.0},
    ]
    target = datetime(2026, 7, 17, 11, 0, tzinfo=timezone.utc)
    ob, lag = nearest_ob(obs, target)
    assert ob["tmpf"] == 71.0
    assert lag == -9 * 60  # ob is 9 minutes BEFORE close_time


def test_nearest_ob_empty_list_returns_none():
    assert nearest_ob([], datetime.now(timezone.utc)) is None


# --------------------------------------------------------------------------- #
# build_basis_rows / summarize
# --------------------------------------------------------------------------- #
def test_build_basis_rows_computes_diff_and_drops_missing_day():
    events = [
        {"event_ticker": "KXTEMPNYCH-A", "close_time": datetime(2026, 7, 17, 11, 0, tzinfo=timezone.utc),
         "twc_value": 72.0, "settlement_ts": "x", "result": "no"},
        {"event_ticker": "KXTEMPNYCH-B", "close_time": datetime(2026, 7, 18, 11, 0, tzinfo=timezone.utc),
         "twc_value": 80.0, "settlement_ts": "x", "result": "yes"},
    ]
    http = FakeHttp({
        "2026-07-17": _obhistory_payload([("2026-07-17T10:51Z", 70.0)]),
        # 2026-07-18 has no page => empty obs => drop
    })
    rows, n_dropped = build_basis_rows(events, http)
    assert n_dropped == 1
    assert len(rows) == 1
    assert rows[0]["diff_degf"] == 2.0  # 72.0 (TWC) - 70.0 (ASOS)
    assert rows[0]["abs_diff_degf"] == 2.0


def test_build_basis_rows_caches_per_day_fetch():
    events = [
        {"event_ticker": "KXTEMPNYCH-A", "close_time": datetime(2026, 7, 17, 11, 0, tzinfo=timezone.utc),
         "twc_value": 72.0, "settlement_ts": "x", "result": "no"},
        {"event_ticker": "KXTEMPNYCH-B", "close_time": datetime(2026, 7, 17, 15, 0, tzinfo=timezone.utc),
         "twc_value": 80.0, "settlement_ts": "x", "result": "yes"},
    ]
    http = FakeHttp({"2026-07-17": _obhistory_payload([("2026-07-17T10:51Z", 70.0)])})
    build_basis_rows(events, http)
    assert len(http.calls) == 1  # same day fetched once, not twice


def test_summarize_empty_rows():
    assert summarize([]) == {"n": 0}


def test_summarize_aggregates_and_disagreement_rate():
    rows = [
        {"diff_degf": 0.5, "abs_diff_degf": 0.5, "lag_seconds": 60},
        {"diff_degf": -3.0, "abs_diff_degf": 3.0, "lag_seconds": -120},
        {"diff_degf": 1.5, "abs_diff_degf": 1.5, "lag_seconds": 0},
    ]
    s = summarize(rows)
    assert s["n"] == 3
    assert abs(s["mean_diff_degf"] - (-1.0 / 3)) < 1e-9
    assert s["max_abs_diff_degf"] == 3.0
    assert s["disagreement_rate_gte_1_0degf"] == 2 / 3  # 3.0 and 1.5 both >= 1.0
    assert s["disagreement_rate_gte_2_0degf"] == 1 / 3  # only 3.0 >= 2.0
    assert s["mean_abs_lag_seconds"] == (60 + 120 + 0) / 3


# --------------------------------------------------------------------------- #
# run() — self-activating INSUFFICIENT DATA path (L-precedent: Q32)
# --------------------------------------------------------------------------- #
def test_run_insufficient_data_below_min_events(tmp_path):
    _write_ledger_day(tmp_path, "2026-07-17", [
        _settlement_rec("KXTEMPNYCH-A", "KXTEMPNYCH-A-T1", "2026-07-17T11:00:00Z", "72.00"),
    ])
    result = run(tape_dir=str(tmp_path), min_events=MIN_EVENTS)
    assert result["status"] == "INSUFFICIENT DATA"
    assert result["n_settled_events"] == 1


def test_run_produces_descriptive_summary_when_enough_events(tmp_path, monkeypatch):
    records = []
    for hour in range(12):
        records.append(_settlement_rec(
            f"KXTEMPNYCH-{hour}", f"KXTEMPNYCH-{hour}-T1",
            f"2026-07-17T{hour:02d}:00:00Z", f"{70 + hour}.00",
        ))
    _write_ledger_day(tmp_path, "2026-07-17", records)

    obs_rows = [(f"2026-07-17T{hour:02d}:00Z", float(70 + hour)) for hour in range(12)]
    http = FakeHttp({"2026-07-17": _obhistory_payload(obs_rows)})

    result = run(tape_dir=str(tmp_path), http=http, min_events=10)
    assert result["status"] == "descriptive"
    assert result["n_settled_events"] == 12
    assert result["n_joined"] == 12
    assert result["summary"]["n"] == 12
    assert result["summary"]["mean_abs_diff_degf"] == 0.0  # exact ob match constructed
    assert "verdict" not in result and "ci" not in result  # never fabricates a strategy verdict
