"""scripts.orderbook_depth_hollow_ladder_audit — the 2026-07-26 hollow-crypto-ladder finding's
reproducer. All offline: unit tests build fixture tape under tmp_path; the HARD acceptance
tests re-derive the exact, two-agent-confirmed numbers (tape-auditor found the phenomenon,
verifier corrected several of its causal claims) against the repo's ACTUAL committed
`tape/orderbook_depth/` (read-only, no network) so this script can never silently drift from
the finding it backs.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

# scripts/ is not a package; load the module by path (same convention as
# tests/test_tape_gap_monitor.py).
_MOD_PATH = Path(__file__).resolve().parent.parent / "scripts" / "orderbook_depth_hollow_ladder_audit.py"
_spec = importlib.util.spec_from_file_location("orderbook_depth_hollow_ladder_audit", _MOD_PATH)
odha = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(odha)

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_TAPE_DIR = REPO_ROOT / "tape" / "orderbook_depth"


def _write(tape_dir: Path, day: str, records, *, malformed_lines=()):
    tape_dir.mkdir(parents=True, exist_ok=True)
    with open(tape_dir / f"dt={day}.jsonl", "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
        for raw in malformed_lines:
            f.write(raw + "\n")


def _rec(ticker, capture_id, captured_at, *, yes_bids=None, no_bids=None,
         best_yes_bid=None, best_yes_ask=None, best_no_bid=None, best_no_ask=None):
    yb = [] if yes_bids is None else yes_bids
    nb = [] if no_bids is None else no_bids
    return {
        "ticker": ticker, "capture_id": capture_id, "captured_at": captured_at,
        "yes_bids": yb, "no_bids": nb, "depth": len(yb) + len(nb),
        "best_yes_bid": best_yes_bid, "best_yes_ask": best_yes_ask,
        "best_no_bid": best_no_bid, "best_no_ask": best_no_ask,
        "price_source_tags": {"asks": "real_ask", "bids": "real_bid"},
        "schema_version": "orderbook_depth.v1", "venue": "kalshi",
        "raw_sha256": "a" * 64,
    }


HOLLOW = dict(yes_bids=[], no_bids=[])
NONHOLLOW = dict(yes_bids=[[0.5, 10.0]], no_bids=[[0.4, 12.0]],
                  best_yes_bid=0.5, best_yes_ask=0.6, best_no_bid=0.4, best_no_ask=0.5)


# --------------------------------------------------------------------------- #
# Basic primitives
# --------------------------------------------------------------------------- #
def test_is_hollow_true_only_when_both_sides_empty():
    assert odha.is_hollow(_rec("KXBTC-26JUL2221-B70250", "c1", "2026-07-22T21:00:00+00:00",
                                **HOLLOW))
    assert not odha.is_hollow(_rec("KXBTC-26JUL2221-B70250", "c1", "2026-07-22T21:00:00+00:00",
                                    **NONHOLLOW))
    one_sided = _rec("KXBTC-26JUL2221-B70250", "c1", "2026-07-22T21:00:00+00:00",
                      yes_bids=[[0.5, 10.0]], no_bids=[])
    assert not odha.is_hollow(one_sided)


def test_is_crypto_ticker():
    assert odha.is_crypto_ticker("KXBTC-26JUL2221-B70250")
    assert odha.is_crypto_ticker("KXETH-26JUL2221-B1767")
    assert not odha.is_crypto_ticker("KXAFLGAME-26JUL230530COLADE-ADE")
    assert not odha.is_crypto_ticker("")


def test_crypto_close_time_parses_the_second_segment():
    close = odha.crypto_close_time("KXBTC-26JUL2221-B70250")
    assert close is not None
    assert close.year == 2026 and close.month == 7
    assert odha.crypto_close_time("not-a-crypto-ticker") is None
    assert odha.crypto_close_time("NOSEPARATOR") is None


def test_runway_bucket_boundaries():
    assert odha._runway_bucket(-1.0) == "post-close (runway < 0)"
    assert odha._runway_bucket(0.0) == "0-5 min"
    assert odha._runway_bucket(299.0) == "0-5 min"
    assert odha._runway_bucket(300.0) == "5-15 min"
    assert odha._runway_bucket(3599.0) == "45-60 min"
    assert odha._runway_bucket(3600.0) == "60+ min"
    assert odha._runway_bucket(None) == "unparseable-token"


# --------------------------------------------------------------------------- #
# load_records / validity
# --------------------------------------------------------------------------- #
def test_load_records_skips_malformed_and_counts_them(tmp_path):
    tape_dir = tmp_path / "orderbook_depth"
    good = _rec("KXBTC-26JUL2221-B70250", "c1", "2026-07-22T21:00:00+00:00", **NONHOLLOW)
    _write(tape_dir, "2026-07-22", [good], malformed_lines=["{not json", ""])
    records, malformed = odha.load_records(tape_dir)
    assert malformed == 1  # the blank line is skipped silently, not counted as malformed
    assert len(records) == 1
    assert records[0]["_day"] == "2026-07-22"


def test_load_records_preserves_file_order_across_days(tmp_path):
    tape_dir = tmp_path / "orderbook_depth"
    _write(tape_dir, "2026-07-21",
           [_rec("KXBTC-26JUL2118-B1", "c1", "2026-07-21T18:00:00+00:00", **NONHOLLOW),
            _rec("KXBTC-26JUL2118-B2", "c1", "2026-07-21T18:00:00+00:00", **NONHOLLOW)])
    _write(tape_dir, "2026-07-22",
           [_rec("KXBTC-26JUL2221-B1", "c2", "2026-07-22T21:00:00+00:00", **NONHOLLOW)])
    records, _ = odha.load_records(tape_dir)
    assert [r["_day"] for r in records] == ["2026-07-21", "2026-07-21", "2026-07-22"]
    assert [r["_line_no"] for r in records] == [0, 1, 0]


def test_audit_validity_flags_schema_drift_dup_and_crossed_books():
    recs = [
        {"ticker": "A", "capture_id": "c1", "best_yes_bid": 0.5, "best_yes_ask": 0.6,
         "best_no_bid": 0.3, "best_no_ask": 0.4},
        {"ticker": "A", "capture_id": "c1", "best_yes_bid": 0.5, "best_yes_ask": 0.6,
         "best_no_bid": 0.3, "best_no_ask": 0.4},  # duplicate (capture_id, ticker)
        {"ticker": "B", "capture_id": "c1", "best_yes_bid": 0.7, "best_yes_ask": 0.6,
         "best_no_bid": None, "best_no_ask": None, "extra_field": 1},  # crossed + schema drift
    ]
    v = odha.audit_validity(recs)
    assert v["total_lines"] == 3
    assert v["distinct_schema_shapes"] == 2
    assert v["duplicate_capture_ticker_pairs"] == 1
    assert v["crossed_book_count"] == 1


def test_audit_validity_clean_fixture_reports_zero_issues():
    recs = [_rec("KXBTC-26JUL2221-B1", "c1", "2026-07-22T21:00:00+00:00", **NONHOLLOW),
            _rec("KXETH-26JUL2221-B2", "c1", "2026-07-22T21:00:00+00:00", **NONHOLLOW)]
    v = odha.audit_validity(recs)
    assert v["distinct_schema_shapes"] == 1
    assert v["duplicate_capture_ticker_pairs"] == 0
    assert v["crossed_book_count"] == 0


# --------------------------------------------------------------------------- #
# Hollow rates / runway buckets / leg crosstab
# --------------------------------------------------------------------------- #
def test_hollow_rates_split_crypto_vs_noncrypto(tmp_path):
    tape_dir = tmp_path / "orderbook_depth"
    recs = [
        _rec("KXBTC-26JUL2221-B1", "c1", "2026-07-22T21:00:00+00:00", **HOLLOW),
        _rec("KXETH-26JUL2221-B2", "c1", "2026-07-22T21:00:00+00:00", **NONHOLLOW),
        _rec("KXAFLGAME-26JUL22-X", "c1", "2026-07-22T21:00:00+00:00", **HOLLOW),
    ]
    _write(tape_dir, "2026-07-22", recs)
    records, _ = odha.load_records(tape_dir)
    h = odha.audit_hollow_rates(records)
    assert h["total_hollow"] == 2
    assert h["crypto_hollow"] == 1
    assert h["non_crypto_hollow"] == 1
    assert h["per_day"]["2026-07-22"]["crypto_total"] == 2
    assert h["per_day"]["2026-07-22"]["crypto_hollow"] == 1


def test_runway_bucket_hollow_near_close_vs_far_from_close(tmp_path):
    tape_dir = tmp_path / "orderbook_depth"
    close = odha.crypto_close_time("KXBTC-26JUL2221-B1")
    # 50 minutes before close (inside the 45-60 min bucket): long runway, non-hollow.
    from datetime import timedelta
    far_ts = (close - timedelta(minutes=50)).isoformat()
    near_ts = (close - timedelta(seconds=60)).isoformat()
    past_ts = (close + timedelta(seconds=30)).isoformat()
    recs = [
        _rec("KXBTC-26JUL2221-B1", "c-far", far_ts, **NONHOLLOW),
        _rec("KXBTC-26JUL2221-B2", "c-near", near_ts, **HOLLOW),
        _rec("KXBTC-26JUL2221-B3", "c-past", past_ts, **HOLLOW),
    ]
    _write(tape_dir, "2026-07-22", recs)
    records, _ = odha.load_records(tape_dir)
    buckets = odha.audit_runway_buckets(records)
    assert buckets["45-60 min"]["total"] == 1 and buckets["45-60 min"]["hollow"] == 0
    assert buckets["0-5 min"]["total"] == 1 and buckets["0-5 min"]["hollow"] == 1
    assert buckets["post-close (runway < 0)"]["total"] == 1
    assert buckets["post-close (runway < 0)"]["hollow"] == 1


def test_leg_crosstab_uses_tape_gap_monitor_collector_bucket(tmp_path):
    tape_dir = tmp_path / "orderbook_depth"
    recs = [
        _rec("KXBTC-26JUL2221-B1", "vpsleg", "2026-07-22T20:23:00+00:00", **NONHOLLOW),
        _rec("KXETH-26JUL2221-B2", "cloudleg", "2026-07-22T20:53:00+00:00", **HOLLOW),
    ]
    _write(tape_dir, "2026-07-22", recs)
    records, _ = odha.load_records(tape_dir)
    tgm = odha._load_tape_gap_monitor()
    tab = odha.audit_leg_crosstab(records, tgm)
    assert tab["vps"] == {"total": 1, "hollow": 0}
    assert tab["cloud"] == {"total": 1, "hollow": 1}


# --------------------------------------------------------------------------- #
# Suffix contiguity
# --------------------------------------------------------------------------- #
def test_suffix_contiguity_clean_capture_no_violation(tmp_path):
    tape_dir = tmp_path / "orderbook_depth"
    recs = [
        _rec("KXBTC-26JUL2221-B1", "c1", "2026-07-22T20:56:00+00:00", **NONHOLLOW),
        _rec("KXBTC-26JUL2221-B2", "c1", "2026-07-22T20:56:00+00:00", **NONHOLLOW),
        _rec("KXBTC-26JUL2221-B3", "c1", "2026-07-22T20:56:00+00:00", **HOLLOW),
        _rec("KXBTC-26JUL2221-B4", "c1", "2026-07-22T20:56:00+00:00", **HOLLOW),
    ]
    _write(tape_dir, "2026-07-22", recs)
    records, _ = odha.load_records(tape_dir)
    result = odha.audit_suffix_contiguity(records, crypto_only=True)
    assert result["partially_empty_captures"] == 1
    assert result["suffix_violations"] == []


def test_suffix_contiguity_flags_a_non_hollow_after_first_hollow(tmp_path):
    tape_dir = tmp_path / "orderbook_depth"
    recs = [
        _rec("KXBTC-26JUL2221-B1", "c1", "2026-07-22T20:56:00+00:00", **NONHOLLOW),
        _rec("KXBTC-26JUL2221-B2", "c1", "2026-07-22T20:56:00+00:00", **HOLLOW),
        _rec("KXBTC-26JUL2221-B3", "c1", "2026-07-22T20:56:00+00:00", **NONHOLLOW),  # violation
    ]
    _write(tape_dir, "2026-07-22", recs)
    records, _ = odha.load_records(tape_dir)
    result = odha.audit_suffix_contiguity(records, crypto_only=True)
    assert result["partially_empty_captures"] == 1
    assert len(result["suffix_violations"]) == 1
    v = result["suffix_violations"][0]
    assert v["capture_id"] == "c1"
    assert v["first_hollow_index"] == 1
    assert v["non_hollow_after_first_hollow"] == 1
    assert v["example_ticker"] == "KXBTC-26JUL2221-B3"


def test_suffix_contiguity_all_hollow_or_all_nonhollow_is_not_partially_empty(tmp_path):
    tape_dir = tmp_path / "orderbook_depth"
    recs = [
        _rec("KXBTC-26JUL2221-B1", "c1", "2026-07-22T20:56:00+00:00", **HOLLOW),
        _rec("KXBTC-26JUL2221-B2", "c1", "2026-07-22T20:56:00+00:00", **HOLLOW),
    ]
    _write(tape_dir, "2026-07-22", recs)
    records, _ = odha.load_records(tape_dir)
    result = odha.audit_suffix_contiguity(records, crypto_only=True)
    assert result["partially_empty_captures"] == 0


# --------------------------------------------------------------------------- #
# CLI / report formatting smoke
# --------------------------------------------------------------------------- #
def test_format_report_and_main_smoke(tmp_path, capsys):
    tape_dir = tmp_path / "orderbook_depth"
    recs = [_rec("KXBTC-26JUL2221-B1", "c1", "2026-07-22T20:56:00+00:00", **HOLLOW)]
    _write(tape_dir, "2026-07-22", recs)
    rc = odha.main(["--tape-dir", str(tape_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ORDERBOOK_DEPTH HOLLOW-LADDER AUDIT" in out
    assert "lines=1 malformed=0" in out


def test_main_writes_json_out(tmp_path):
    tape_dir = tmp_path / "orderbook_depth"
    recs = [_rec("KXBTC-26JUL2221-B1", "c1", "2026-07-22T20:56:00+00:00", **HOLLOW)]
    _write(tape_dir, "2026-07-22", recs)
    json_out = tmp_path / "out.json"
    rc = odha.main(["--tape-dir", str(tape_dir), "--json-out", str(json_out)])
    assert rc == 0
    payload = json.loads(json_out.read_text())
    assert payload["hollow_rates"]["total_hollow"] == 1


# --------------------------------------------------------------------------- #
# HARD acceptance — reproduces the exact, verifier-confirmed numbers from the
# 2026-07-26 finding against the REAL committed tape, FROZEN at `dt<=2026-07-25` (the
# last fully-closed day at the time of the finding). This is deliberate, L140-style
# discipline: `dt=2026-07-26.jsonl` is still being appended to by every ongoing hourly
# pass, so pinning exact counts against it unfrozen would break on this test's very
# next run once new tape landed (it did, within the same run that wrote this test —
# see the finding's own note). Freezing to a day that can never grow again means these
# assertions hold forever; if new tape genuinely changes the FROZEN slice's numbers that
# is a real regression in the script, not tape drift.
#
# Module-scoped fixtures: `tape/orderbook_depth/` is ~318MB/342K lines: loading it is
# the single slowest thing in this file (~60-90s), so both HARD tests below share ONE
# `load_records` call rather than each re-reading the whole directory from scratch.
# --------------------------------------------------------------------------- #
_FROZEN_MAX_DAY = "2026-07-25"


@pytest.fixture(scope="module")
def real_records_and_malformed():
    return odha.load_records(REAL_TAPE_DIR, max_day=_FROZEN_MAX_DAY)


@pytest.fixture(scope="module")
def real_records(real_records_and_malformed):
    return real_records_and_malformed[0]


@pytest.fixture(scope="module")
def real_report(real_records_and_malformed):
    records, malformed = real_records_and_malformed
    tgm = odha._load_tape_gap_monitor()
    return {
        "malformed_lines": malformed,
        "validity": odha.audit_validity(records),
        "hollow_rates": odha.audit_hollow_rates(records),
        "runway_buckets": odha.audit_runway_buckets(records),
        "leg_crosstab_descriptive_only": odha.audit_leg_crosstab(records, tgm),
        "suffix_contiguity_crypto_only": odha.audit_suffix_contiguity(records, crypto_only=True),
    }


def test_real_tape_reproduces_the_2026_07_26_finding_exactly(real_report):
    report = real_report
    v = report["validity"]
    assert v["total_lines"] == 339_947
    assert report["malformed_lines"] == 0
    assert v["distinct_schema_shapes"] == 1
    assert v["duplicate_capture_ticker_pairs"] == 0
    assert v["crossed_book_count"] == 0

    h = report["hollow_rates"]
    assert h["total_hollow"] == 15_238
    assert h["crypto_hollow"] == 15_175
    assert h["non_crypto_hollow"] == 63

    rb = report["runway_buckets"]
    assert rb["post-close (runway < 0)"] == {"total": 789, "hollow": 789}
    assert rb["0-5 min"] == {"total": 51_501, "hollow": 14_385}
    assert rb["5-15 min"] == {"total": 1_578, "hollow": 0}
    assert rb["15-30 min"] == {"total": 488, "hollow": 0}
    assert rb["30-45 min"] == {"total": 64_274, "hollow": 1}
    assert rb["45-60 min"] == {"total": 526, "hollow": 0}

    legs = report["leg_crosstab_descriptive_only"]
    assert legs["vps"] == {"total": 64_274, "hollow": 1}
    assert legs["cloud"] == {"total": 53_079, "hollow": 14_385}
    assert legs["other"] == {"total": 1_803, "hollow": 789}

    sc = report["suffix_contiguity_crypto_only"]
    assert sc["partially_empty_captures"] == 42
    assert len(sc["suffix_violations"]) == 2
    violation_captures = {v["capture_id"] for v in sc["suffix_violations"]}
    assert violation_captures == {"20260711T052352Z", "20260714T125521Z"}


def test_real_tape_all_records_suffix_variant_matches_verifier(real_records):
    all_records = odha.audit_suffix_contiguity(real_records, crypto_only=False)
    assert all_records["partially_empty_captures"] == 77
    assert len(all_records["suffix_violations"]) == 16
