"""Offline tests for `scripts/hl_funding_tape_quality.py` (tape/hyperliquid_funding audit).

Two layers, per house style: synthetic-record unit tests for every pure function (no tape,
no network), plus a small pinned REAL-TAPE acceptance layer. The real-tape assertions are
deliberately written to survive tape GROWTH (>= on counts that can only grow, exact only on
facts that are frozen history) so a future collector pass does not turn a healthy tape into
a red test.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import hl_funding_tape_quality as A  # noqa: E402

HOUR = A.HOUR_MS
BASE = A.HL_BASELINE_HOURLY_RATE
T0 = 1780444800000  # 2026-06-03T00:00:00Z, the family's first archived hour


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #
def _print(coin, hour, rate=BASE, premium=1e-6, jitter=52):
    """One HL print row at `hour` hours past T0, with the venue's real ms jitter past :00."""
    return {"coin": coin, "time_ms": T0 + hour * HOUR + jitter,
            "funding_rate": rate, "premium": premium}


def _rec(coin, prints, capture_id="20260801T010000Z", captured_at="2026-08-01T01:00:00+00:00",
         mode="incremental", start_ms=None):
    rec = {"schema_version": "hyperliquid_funding.v1", "record_type": "funding_history",
           "venue": "hyperliquid", "coin": coin, "mode": mode, "capture_id": capture_id,
           "captured_at": captured_at, "prints": prints, "n_prints": len(prints),
           "price_source_tag": "broker_truth"}
    if start_ms is not None:
        rec["start_ms"] = start_ms
    return rec


def _lines(records):
    return [(f"tape/hyperliquid_funding/dt=2026-08-01.jsonl", json.dumps(r, sort_keys=True))
            for r in records]


# --------------------------------------------------------------------------- #
# parsing / flattening
# --------------------------------------------------------------------------- #
def test_hour_index_absorbs_venue_ms_jitter():
    assert A._hour_index(T0) == A._hour_index(T0 + 52) == A._hour_index(T0 + 999)
    assert A._hour_index(T0 + HOUR) == A._hour_index(T0) + 1
    assert A._hour_index(None) is None and A._hour_index("x") is None


def test_parse_records_skips_malformed_line_without_raising():
    good = json.dumps(_rec("BTC", [_print("BTC", 0)]))
    recs = A.parse_records([("p", good), ("p", "{not json"), ("p", "[1,2]")])
    assert len(recs) == 1 and recs[0]["coin"] == "BTC"


def test_flatten_prints_keeps_every_row_including_duplicates():
    """The duplicate structure is the measurement — flatten must NOT dedup."""
    a = _rec("BTC", [_print("BTC", 0), _print("BTC", 1)], capture_id="A")
    b = _rec("BTC", [_print("BTC", 1), _print("BTC", 2)], capture_id="B")
    rows = A.flatten_prints([a, b])["BTC"]
    assert len(rows) == 4
    assert sorted(r["hour_index"] for r in rows) == [
        A._hour_index(T0), A._hour_index(T0) + 1, A._hour_index(T0) + 1, A._hour_index(T0) + 2]


def test_flatten_prints_ignores_non_funding_history_records():
    other = {"record_type": "funding_rates", "coin": "BTC", "prints": [_print("BTC", 0)]}
    assert A.flatten_prints([other]) == {}


# --------------------------------------------------------------------------- #
# 1. hour coverage
# --------------------------------------------------------------------------- #
def test_hour_coverage_reports_missing_run_and_no_duplicates():
    rows = A.flatten_prints([_rec("BTC", [_print("BTC", h) for h in (0, 1, 4, 5)])])
    cov = A.hour_coverage(rows)["BTC"]
    assert cov["n_rows"] == 4 and cov["n_distinct_hours"] == 4
    assert cov["n_expected_hours"] == 6 and cov["n_missing_hours"] == 2
    assert cov["missing_runs"] == [["2026-06-03T02:00Z", "2026-06-03T03:00Z", 2]]
    assert cov["n_duplicate_hours"] == 0 and cov["n_redundant_rows"] == 0


def test_hour_coverage_counts_duplicate_hours_as_redundant_not_missing():
    a = _rec("BTC", [_print("BTC", h) for h in (0, 1, 2)], capture_id="A")
    b = _rec("BTC", [_print("BTC", h) for h in (1, 2, 3)], capture_id="B")
    cov = A.hour_coverage(A.flatten_prints([a, b]))["BTC"]
    assert cov["n_rows"] == 6 and cov["n_distinct_hours"] == 4
    assert cov["n_missing_hours"] == 0
    assert cov["n_duplicate_hours"] == 2 and cov["n_redundant_rows"] == 2
    assert cov["max_multiplicity"] == 2
    assert cov["duplicate_runs"] == [["2026-06-03T01:00Z", "2026-06-03T02:00Z", 2]]


def test_duplicate_value_conflicts_flags_disagreeing_repeat():
    a = _rec("BTC", [_print("BTC", 0, rate=BASE)], capture_id="A")
    b = _rec("BTC", [_print("BTC", 0, rate=BASE)], capture_id="B")
    assert A.duplicate_value_conflicts(A.flatten_prints([a, b]))["BTC"][
        "n_conflicting_hours"] == 0
    c = _rec("BTC", [_print("BTC", 0, rate=9.9e-5)], capture_id="C")
    assert A.duplicate_value_conflicts(A.flatten_prints([a, c]))["BTC"][
        "n_conflicting_hours"] == 1


# --------------------------------------------------------------------------- #
# 2. duplicate lines
# --------------------------------------------------------------------------- #
def test_duplicate_lines_detects_same_capture_appended_twice():
    r = _rec("BTC", [_print("BTC", 0)], capture_id="20260728T070413Z")
    rep = A.duplicate_lines(_lines([r, r, _rec("ETH", [_print("ETH", 0)])]))
    assert rep["n_lines"] == 3
    assert rep["n_duplicate_line_groups"] == 1 and rep["n_extra_lines"] == 1
    assert rep["groups"][0]["capture_id"] == "20260728T070413Z"
    assert rep["groups"][0]["n_copies"] == 2


def test_duplicate_lines_does_not_flag_two_distinct_captures_of_same_hour():
    """Overlapping (coin, time_ms) from DIFFERENT captures is a start_ms regression, not a
    duplicate append — the two defect classes must not be conflated."""
    a = _rec("BTC", [_print("BTC", 0)], capture_id="A", captured_at="2026-08-01T01:00:00+00:00")
    b = _rec("BTC", [_print("BTC", 0)], capture_id="B", captured_at="2026-08-01T04:00:00+00:00")
    assert A.duplicate_lines(_lines([a, b]))["n_duplicate_line_groups"] == 0


# --------------------------------------------------------------------------- #
# 3. start_ms regressions
# --------------------------------------------------------------------------- #
def test_start_ms_regression_detected_when_pass_misses_predecessor_write():
    a = _rec("BTC", [_print("BTC", h) for h in (1, 2, 3)], capture_id="A",
             captured_at="2026-08-01T01:00:00+00:00", start_ms=T0 + 0 * HOUR)
    b = _rec("BTC", [_print("BTC", h) for h in (1, 2, 3, 4, 5, 6)], capture_id="B",
             captured_at="2026-08-01T04:00:00+00:00", start_ms=T0 + 0 * HOUR)
    r = A.start_ms_regressions([a, b])["BTC"]
    assert r["n_incremental_records"] == 2 and r["n_start_ms_regressions"] == 1
    g = r["regressions"][0]
    assert g["capture_id"] == "B"
    assert g["start_hour"] == "2026-06-03T00:00Z"
    assert g["already_archived_through"] == "2026-06-03T03:00Z"
    assert g["n_re_emitted_hours"] == 3


def test_start_ms_tie_with_running_max_is_not_a_regression():
    """`start_ms == last archived print` is the collector working exactly as designed."""
    a = _rec("BTC", [_print("BTC", 1)], capture_id="A",
             captured_at="2026-08-01T01:00:00+00:00", start_ms=T0)
    b = _rec("BTC", [_print("BTC", 2)], capture_id="B",
             captured_at="2026-08-01T02:00:00+00:00", start_ms=T0 + 1 * HOUR + 52)
    assert A.start_ms_regressions([a, b])["BTC"]["n_start_ms_regressions"] == 0


def test_start_ms_regressions_ignore_backfill_mode_records():
    bf = _rec("BTC", [_print("BTC", h) for h in range(5)], capture_id="BF",
              captured_at="2026-07-17T00:00:00+00:00", mode="backfill", start_ms=T0)
    inc = _rec("BTC", [_print("BTC", 5)], capture_id="I",
               captured_at="2026-08-01T01:00:00+00:00", start_ms=T0)
    r = A.start_ms_regressions([bf, inc])["BTC"]
    assert r["n_incremental_records"] == 1 and r["n_start_ms_regressions"] == 0


def test_capture_cadence_dedups_capture_instants():
    a = _rec("BTC", [_print("BTC", 1)], captured_at="2026-08-01T01:00:00+00:00")
    b = _rec("ETH", [_print("ETH", 1)], captured_at="2026-08-01T01:00:00+00:00")
    c = _rec("BTC", [_print("BTC", 4)], captured_at="2026-08-01T04:00:00+00:00")
    cc = A.capture_cadence([a, b, c])
    assert cc["n_capture_instants"] == 2
    assert cc["median_gap_hours"] == pytest.approx(3.0)


# --------------------------------------------------------------------------- #
# 4. baseline pin
# --------------------------------------------------------------------------- #
def test_baseline_pin_profile_counts_distinct_hours_and_runs():
    rates = [BASE, BASE, 3e-6, BASE, BASE, BASE]
    rec = _rec("BTC", [_print("BTC", h, rate=r) for h, r in enumerate(rates)])
    b = A.baseline_pin_profile(A.flatten_prints([rec]))["BTC"]
    assert b["n_hours"] == 6 and b["n_pinned_hours"] == 5
    assert b["pinned_fraction"] == pytest.approx(5 / 6)
    assert b["n_pinned_runs"] == 2 and b["longest_pinned_run_hours"] == 3
    assert b["max_rate_equals_baseline"] is True and b["n_zero_rate_hours"] == 0


def test_baseline_pin_profile_dedups_repeated_hour_before_counting():
    """A duplicated hour must count ONCE, else the redundancy inflates the pinned fraction."""
    a = _rec("BTC", [_print("BTC", 0, rate=BASE)], capture_id="A")
    b = _rec("BTC", [_print("BTC", 0, rate=BASE), _print("BTC", 1, rate=1e-6)],
             capture_id="B")
    prof = A.baseline_pin_profile(A.flatten_prints([a, b]))["BTC"]
    assert prof["n_hours"] == 2 and prof["n_pinned_hours"] == 1


def test_baseline_pin_is_exact_not_approximate():
    """One ulp off the venue constant is a real observation, not a pin."""
    rec = _rec("BTC", [_print("BTC", 0, rate=BASE), _print("BTC", 1, rate=BASE * (1 + 1e-12))])
    assert A.baseline_pin_profile(A.flatten_prints([rec]))["BTC"]["n_pinned_hours"] == 1


# --------------------------------------------------------------------------- #
# 5. degenerate windows
# --------------------------------------------------------------------------- #
def _kalshi_print(hour_index, rate):
    return {"ticker": "KXBTCPERP", "funding_time": None, "t_ms": hour_index * HOUR,
            "hour_index": hour_index, "funding_rate": rate}


def test_degenerate_window_requires_both_legs_at_venue_constant():
    h0 = A._hour_index(T0)
    hT = h0 + 7
    pinned = {h0 + i: BASE for i in range(8)}
    mixed = dict(pinned)
    mixed[h0 + 3] = 5e-6
    # both constant -> degenerate
    r = A.degenerate_window_profile([_kalshi_print(hT, 0.0)], pinned)
    assert r["n_windows_joined"] == 1 and r["n_both_degenerate"] == 1
    assert r["n_kalshi_clamped"] == 1 and r["n_all8_hl_pinned"] == 1
    assert r["n_distinct_degenerate_differentials"] == 1
    # Kalshi off the clamp -> not degenerate
    r2 = A.degenerate_window_profile([_kalshi_print(hT, 1e-4)], pinned)
    assert r2["n_both_degenerate"] == 0 and r2["n_all8_hl_pinned"] == 1
    # one HL hour off the baseline -> not degenerate
    r3 = A.degenerate_window_profile([_kalshi_print(hT, 0.0)], mixed)
    assert r3["n_both_degenerate"] == 0 and r3["n_kalshi_clamped"] == 1


def test_degenerate_window_profile_excludes_partial_windows():
    h0 = A._hour_index(T0)
    partial = {h0 + i: BASE for i in range(7)}     # only 7 of 8 hours present
    r = A.degenerate_window_profile([_kalshi_print(h0 + 7, 0.0)], partial)
    assert r["n_windows_joined"] == 0 and r["n_both_degenerate"] == 0


def test_degenerate_differential_is_a_single_value_across_all_degenerate_windows():
    """The point-mass claim itself: every all-constant window carries the SAME number."""
    h0 = A._hour_index(T0)
    table = {h0 + i: BASE for i in range(24)}
    kps = [_kalshi_print(h0 + 7, 0.0), _kalshi_print(h0 + 15, 0.0), _kalshi_print(h0 + 23, 0.0)]
    r = A.degenerate_window_profile(kps, table)
    assert r["n_windows_joined"] == 3 and r["n_both_degenerate"] == 3
    assert r["n_distinct_degenerate_differentials"] == 1


# --------------------------------------------------------------------------- #
# real-tape acceptance (pinned 2026-08-09; written to survive tape growth)
# --------------------------------------------------------------------------- #
HL_DIR = REPO / "tape" / "hyperliquid_funding"


@pytest.mark.skipif(not HL_DIR.is_dir(), reason="hyperliquid_funding tape not present")
def test_real_tape_hour_coverage_has_no_holes_and_starts_at_launch():
    rep = A.hour_coverage(A.flatten_prints(A.parse_records(A.load_lines(A.HL_GLOB))))
    assert set(rep) >= {"BTC", "ETH"}
    for coin in ("BTC", "ETH"):
        c = rep[coin]
        # coverage is the union of embedded print hours, NOT dt= file presence: the
        # dt=2026-07-18..21 file hole (L117 VPS death) is NOT an hour hole.
        assert c["n_missing_hours"] == 0, c["missing_runs"]
        assert c["span_start"] == "2026-06-03T00:00Z"
        assert c["n_distinct_hours"] >= 1601
        # >= 2, not ==: a stranded overlapping capture recovered by a later step-0b sweep
        # can only ADD another copy of an already-duplicated hour, never remove one (tape is
        # append-only) — measured 2026-08-09 later same day, a step-0b recovery of a
        # previously-missed hyperliquid_funding residual (L301-class incomplete recovery)
        # pushed this from 2 to 3 by construction, exactly the L319 race this file audits.
        assert c["max_multiplicity"] >= 2
    assert rep["BTC"]["n_distinct_hours"] == rep["ETH"]["n_distinct_hours"]


@pytest.mark.skipif(not HL_DIR.is_dir(), reason="hyperliquid_funding tape not present")
def test_real_tape_duplicates_are_value_identical_never_conflicting():
    prints = A.flatten_prints(A.parse_records(A.load_lines(A.HL_GLOB)))
    conflicts = A.duplicate_value_conflicts(prints)
    for coin in ("BTC", "ETH"):
        assert conflicts[coin]["n_conflicting_hours"] == 0
        assert A.hour_coverage(prints)[coin]["n_duplicate_hours"] >= 79


@pytest.mark.skipif(not HL_DIR.is_dir(), reason="hyperliquid_funding tape not present")
def test_real_tape_carries_the_20260728_duplicate_append_and_start_ms_regressions():
    lines = A.load_lines(A.HL_GLOB)
    recs = A.parse_records(lines)
    dl = A.duplicate_lines(lines)
    ids = {g["capture_id"] for g in dl["groups"]}
    assert "20260728T070413Z" in ids, dl["groups"]
    reg = A.start_ms_regressions(recs)
    for coin in ("BTC", "ETH"):
        assert reg[coin]["n_start_ms_regressions"] >= 13


@pytest.mark.skipif(not HL_DIR.is_dir(), reason="hyperliquid_funding tape not present")
def test_real_tape_hl_hourly_rate_is_pinned_at_the_venue_baseline_over_half_the_time():
    prof = A.baseline_pin_profile(
        A.flatten_prints(A.parse_records(A.load_lines(A.HL_GLOB))))
    for coin in ("BTC", "ETH"):
        b = prof[coin]
        assert b["n_zero_rate_hours"] == 0          # Q42's premise: HL funding is never 0
        assert b["pinned_fraction"] > 0.5           # ... but it IS a constant most hours
        assert b["longest_pinned_run_hours"] >= 269  # pinned hours are heavily autocorrelated
    # ETH never prints ABOVE the baseline anywhere in committed tape; BTC does.
    assert prof["ETH"]["max_rate_equals_baseline"] is True
    assert prof["BTC"]["max_rate_equals_baseline"] is False


@pytest.mark.skipif(not (HL_DIR.is_dir() and (REPO / "tape" / "perp_tape").is_dir()),
                    reason="tape not present")
def test_real_tape_degenerate_window_share_is_material_and_a_point_mass():
    rep = A.build_report()
    for asset, floor in (("BTC", 56), ("ETH", 71)):
        g = rep["degenerate_windows"][asset]
        assert g["n_windows_joined"] >= 198
        assert g["n_both_degenerate"] >= floor
        assert g["both_degenerate_fraction"] > 0.25
        # the whole point: those windows carry ONE differential value, not a distribution
        assert g["n_distinct_degenerate_differentials"] == 1
        assert g["degenerate_differential"] == pytest.approx(1.0000437510937488e-04, rel=1e-9)
