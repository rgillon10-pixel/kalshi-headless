"""Offline tests for scripts/crypto_hourly_settlement_audit.py (idle-run policy (c)
data-quality deep-dive on `tape/crypto_hourly/`).

No network anywhere. Two classes of test:

* pure-function tests over hand-built records, which pin the DEFECT DETECTOR (a healthy
  settlement history must not be the only input the exactly-one-winner check has ever seen
  — L191's shape: a synthetic violation is fed in to prove the detector actually detects);
* `test_acceptance_*` tests over committed tape. `tape/crypto_hourly/` is actively collected
  every hourly pass, so acceptance assertions are DIRECTIONAL (bounds, not equalities) per
  the `q51_trade_tape_quality` precedent — an acceptance test that a future hourly pass or
  stranded-branch sweep would break is a test that would be deleted.
"""
from __future__ import annotations

import json

import pytest

from scripts import crypto_hourly_settlement_audit as A


# --------------------------------------------------------------------------- #
# settlement_integrity
# --------------------------------------------------------------------------- #
def _settled_rec(event_ticker, results, day="2026-08-01", symbol="BTC",
                  capture_id="C1", expiration_value="100.00"):
    return {
        "_day": day, "symbol": symbol, "capture_id": capture_id,
        "previous_settlement": {
            "status": "settled", "event_ticker": event_ticker,
            "expiration_value": expiration_value, "results": results,
        },
    }


def _pending_rec(day="2026-08-01", symbol="BTC"):
    return {"_day": day, "symbol": symbol, "capture_id": "C2",
            "previous_settlement": {"status": "pending", "event_ticker": "X",
                                     "n_markets": 5, "n_settled": 2}}


def _no_current_group_rec(day="2026-08-01", symbol="BTC"):
    return {"_day": day, "symbol": symbol, "capture_id": "C3",
            "current": {"status": "no_hourly_group_found"},
            "previous_settlement": {"status": "no_current_group"}}


def test_settlement_integrity_clean_mece_ladder_holds():
    records = [
        _settled_rec("EV1", {"EV1-A": "no", "EV1-B": "yes", "EV1-C": "no"}),
        _settled_rec("EV2", {"EV2-A": "yes", "EV2-B": "no"}, capture_id="C4"),
        _pending_rec(),
    ]
    r = A.settlement_integrity(records)
    assert r["n_settled"] == 2
    assert r["n_mece_exactly_one_winner_violations"] == 0
    assert r["mece_invariant_holds"] is True
    assert r["status_distribution"] == {"settled": 2, "pending": 1}


def test_settlement_integrity_pending_and_no_current_group_are_not_violations():
    """A record whose settlement hasn't posted yet correctly carries no `results` key at
    all (per `collection/crypto_hourly.py::fetch_settlement`/`run`) — it must never be
    read as a zero-winner (i.e. corrupted) settlement. This is the exact false-positive
    class this module exists to avoid (see module docstring measurement 1)."""
    records = [_pending_rec(), _no_current_group_rec(),
               {"_day": "2026-08-01", "symbol": "ETH", "capture_id": "C5",
                "previous_settlement": {"status": "not_found", "event_ticker": "Y"}}]
    r = A.settlement_integrity(records)
    assert r["n_settled"] == 0
    assert r["n_mece_exactly_one_winner_violations"] == 0
    assert r["mece_invariant_holds"] is True
    assert r["status_distribution"] == {"pending": 1, "no_current_group": 1, "not_found": 1}


def test_settlement_integrity_detects_zero_winner_violation():
    """The detector must actually fire on a genuine defect, not just report clean on
    everything it's ever seen (L191/L216 discipline)."""
    records = [_settled_rec("EV1", {"EV1-A": "no", "EV1-B": "no", "EV1-C": "no"})]
    r = A.settlement_integrity(records)
    assert r["n_settled"] == 1
    assert r["n_mece_exactly_one_winner_violations"] == 1
    assert r["mece_invariant_holds"] is False
    assert r["violation_examples"][0]["n_yes"] == 0
    assert r["violation_examples"][0]["event_ticker"] == "EV1"


def test_settlement_integrity_detects_multi_winner_violation():
    records = [_settled_rec("EV1", {"EV1-A": "yes", "EV1-B": "yes", "EV1-C": "no"})]
    r = A.settlement_integrity(records)
    assert r["n_mece_exactly_one_winner_violations"] == 1
    assert r["violation_examples"][0]["n_yes"] == 2


def test_settlement_integrity_missing_expiration_value_counted_but_not_a_violation():
    rec = _settled_rec("EV1", {"EV1-A": "yes", "EV1-B": "no"}, expiration_value=None)
    r = A.settlement_integrity([rec])
    assert r["n_settled_missing_expiration_value"] == 1
    assert r["mece_invariant_holds"] is True


def test_settlement_integrity_empty_input():
    r = A.settlement_integrity([])
    assert r["n_settled"] == 0
    assert r["mece_invariant_holds"] is True
    assert r["status_distribution"] == {}


# --------------------------------------------------------------------------- #
# capture_cadence
# --------------------------------------------------------------------------- #
def test_capture_cadence_counts_passes_as_paired_capture_ids():
    records = [
        {"_day": "2026-07-01", "capture_id": "A"},
        {"_day": "2026-07-01", "capture_id": "A"},  # same pass, second symbol (ETH)
        {"_day": "2026-07-01", "capture_id": "B"},
        {"_day": "2026-07-02", "capture_id": "C"},
    ]
    r = A.capture_cadence(records)
    assert r["n_days"] == 2
    by_day = {d["day"]: d for d in r["per_day"]}
    assert by_day["2026-07-01"]["n_lines"] == 3
    assert by_day["2026-07-01"]["n_passes"] == 2  # A, B — one capture_id each pass
    assert by_day["2026-07-02"]["n_passes"] == 1
    assert r["peak_day"] == "2026-07-01"
    assert r["peak_passes"] == 2


def test_capture_cadence_empty_input():
    assert A.capture_cadence([]) == {"n_days": 0}


def test_capture_cadence_recent_window_is_last_seven_day_files():
    records = [{"_day": f"2026-07-{d:02d}", "capture_id": f"C{d}"} for d in range(1, 11)]
    r = A.capture_cadence(records)
    recent_days = [p["day"] for p in r["per_day"][-7:]]
    assert recent_days == [f"2026-07-{d:02d}" for d in range(4, 11)]
    assert r["recent_7day_mean_passes"] == 1.0


# --------------------------------------------------------------------------- #
# discovery_gap_profile
# --------------------------------------------------------------------------- #
def test_discovery_gap_profile_all_ok():
    records = [{"_day": "2026-07-01", "symbol": "BTC", "current": {"status": "ok"}}] * 3
    r = A.discovery_gap_profile(records)
    assert r["n_gap"] == 0
    assert r["frac_gap"] == 0.0
    assert r["reason_counts"] == {}


def test_discovery_gap_profile_classifies_genuine_vs_transient():
    records = [
        {"_day": "2026-07-01", "symbol": "BTC", "current": {"status": "ok"}},
        {"_day": "2026-07-02", "symbol": "BTC", "current": {"status": "no_hourly_group_found"}},
        {"_day": "2026-07-03", "symbol": "ETH",
         "current": {"status": "HTTPSConnectionPool(...): Max retries exceeded with url: ..."}},
    ]
    r = A.discovery_gap_profile(records)
    assert r["n_total"] == 3
    assert r["n_ok"] == 1
    assert r["n_gap"] == 2
    assert r["reason_counts"]["no_hourly_group_found"] == 1
    assert r["reason_counts"]["transient_error"] == 1
    assert r["by_symbol"] == {"BTC": 1, "ETH": 1}
    assert r["last_gap_day"] == "2026-07-03"


def test_discovery_gap_profile_empty_input():
    r = A.discovery_gap_profile([])
    assert r["n_total"] == 0
    assert r["frac_gap"] is None


# --------------------------------------------------------------------------- #
# acceptance — real committed tape (directional bounds, tape grows every hourly pass)
# --------------------------------------------------------------------------- #
def test_acceptance_real_tape_mece_invariant_holds():
    records = A._iter_records(A.TAPE_DIR)
    assert len(records) > 1000
    r = A.settlement_integrity(records)
    assert r["n_settled"] >= 1481
    assert r["n_mece_exactly_one_winner_violations"] == 0
    assert r["mece_invariant_holds"] is True


def test_acceptance_real_tape_cadence_report_shape():
    records = A._iter_records(A.TAPE_DIR)
    r = A.capture_cadence(records)
    assert r["n_days"] >= 30
    assert r["first_day"] == "2026-07-03"
    assert r["peak_passes"] >= 100  # 07-14 CPI burst
    assert r["recent_7day_mean_passes"] is not None
    assert r["recent_7day_mean_passes"] < r["peak_passes"]


def test_acceptance_real_tape_discovery_gaps_recurred_in_august_L302():
    """AMENDED 2026-08-07 (L302). This pin used to assert `last_gap_day < "2026-08-01"` —
    "a closed July episode, no August recurrence" — and that was an AVAILABILITY artifact,
    not a fact about the collector. The 2026-08-06 06:56Z pass DID hit
    `no_hourly_group_found` on both BTC and ETH, but its push to `main` failed and it sat on
    `tape/hourly-20260806T0657Z` until this run's step-0b sweep recovered it. A conclusion
    computed over committed tape is conditioned on the pass having successfully pushed, and a
    pass that fails is not independent of a pass that fails to push. The pin now asserts the
    recurrence so it can never silently un-recur."""
    records = A._iter_records(A.TAPE_DIR)
    r = A.discovery_gap_profile(records)
    assert r["n_gap"] >= 78
    assert r["reason_counts"].get("no_hourly_group_found", 0) >= 74
    assert r["last_gap_day"] == "2026-08-06"
    assert r["by_day"]["2026-08-06"] == 2   # BTC + ETH, capture 20260806T065616Z


def test_acceptance_build_report_end_to_end():
    rep = A.build_report(A.TAPE_DIR)
    assert rep["schema_version"] == A.SCHEMA_VERSION
    assert rep["offline"] is True
    assert rep["n_records"] > 1000
    assert rep["settlement_integrity"]["mece_invariant_holds"] is True
