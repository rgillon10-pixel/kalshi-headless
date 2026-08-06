"""scripts.anomaly_detector_evidence_audit — the L296 replay over committed anomaly tape.

Two halves, the repo's usual shape: fixture tests that prove the classification FIRES on a
planted defect (L191), and acceptance tests that pin the real committed numbers over a CLOSED
window (`--max-day 2026-08-04`; without it the next collector pass moves every count — L286).
"""
from __future__ import annotations

import json

import pytest

import scripts.anomaly_detector_evidence_audit as A
from core.detector_evidence import (EVIDENCE_COUNTER_ABSENT, EVIDENCE_EMPTY_DENOMINATOR,
                                    EVIDENCE_HITS, EVIDENCE_INCOHERENT,
                                    EVIDENCE_INFORMATIVE_ZERO)

MAX_DAY = "2026-08-04"


def _rec(bracket=0, mono=0, pairs=0, anomalies=(), omit_pairs=False,
         completeness_ok=True, fetch_error=None, n_markets=100, capture_id="c1"):
    r = {
        "schema_version": "anomaly_sweep.v1", "capture_id": capture_id,
        "n_markets_scanned": n_markets, "n_event_groups": 3,
        "n_bracket_groups_checked": bracket, "n_monotonicity_groups_checked": mono,
        "n_implication_pairs_checked": pairs,
        "anomalies": [{"kind": k} for k in anomalies],
        "n_anomalies": len(anomalies), "fetch_error": fetch_error,
        "markets_truncated": True, "completeness_ok": completeness_ok,
    }
    if omit_pairs:
        del r["n_implication_pairs_checked"]
    return r


def _write(tmp_path, by_day):
    for day, records in by_day.items():
        with open(tmp_path / f"dt={day}.jsonl", "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
    return tmp_path


# --------------------------------------------------------------------------- #
# fixture — the classification fires
# --------------------------------------------------------------------------- #
def test_a_pass_that_checked_nothing_is_an_empty_denominator(tmp_path):
    """The planted defect: a pass that scanned 20,000 markets, reported completeness_ok and
    zero anomalies, and evaluated ZERO candidates. Before this audit it read as clean."""
    _write(tmp_path, {"2026-07-01": [_rec(bracket=0, mono=0, pairs=0, n_markets=20000)]})
    out = A.audit(tmp_path)
    for name in ("bracket_arb", "cross_strike_monotonicity", "cross_event_implication"):
        cc = out["per_check"][name]["class_counts"]
        assert cc[EVIDENCE_EMPTY_DENOMINATOR] == 1
        assert out["per_check"][name]["n_passes_whose_zero_is_readable"] == 0
        assert out["per_check"][name]["n_clean_looking_empty_denominator_passes"] == 1


def test_a_pass_that_checked_candidates_and_found_none_is_an_informative_zero(tmp_path):
    _write(tmp_path, {"2026-07-01": [_rec(bracket=7, mono=9, pairs=38)]})
    out = A.audit(tmp_path)
    for name in ("bracket_arb", "cross_strike_monotonicity", "cross_event_implication"):
        cc = out["per_check"][name]["class_counts"]
        assert cc[EVIDENCE_INFORMATIVE_ZERO] == 1
        assert cc[EVIDENCE_EMPTY_DENOMINATOR] == 0
        assert out["per_check"][name]["n_passes_whose_zero_is_readable"] == 1
        assert out["per_check"][name]["n_clean_looking_empty_denominator_passes"] == 0


def test_hits_are_attributed_to_the_emitting_check_only(tmp_path):
    _write(tmp_path, {"2026-07-01": [_rec(bracket=2, mono=3, pairs=4,
                                          anomalies=("cross_strike_monotonicity",) * 5)]})
    out = A.audit(tmp_path)
    assert out["per_check"]["cross_strike_monotonicity"]["class_counts"][EVIDENCE_HITS] == 1
    assert out["per_check"]["cross_strike_monotonicity"]["sum_hits"] == 5
    assert out["per_check"]["bracket_arb"]["class_counts"][EVIDENCE_INFORMATIVE_ZERO] == 1
    assert out["per_check"]["bracket_arb"]["sum_hits"] == 0
    assert out["per_check"]["cross_event_implication"]["sum_hits"] == 0


def test_an_absent_counter_is_not_folded_into_zero(tmp_path):
    """L289's shape: a record predating the counter is `counter_absent`, never an empty
    denominator — and it contributes nothing to the summed denominator either."""
    _write(tmp_path, {"2026-07-01": [_rec(bracket=1, mono=1, pairs=0, omit_pairs=True)]})
    out = A.audit(tmp_path)
    cc = out["per_check"]["cross_event_implication"]["class_counts"]
    assert cc[EVIDENCE_COUNTER_ABSENT] == 1
    assert cc[EVIDENCE_EMPTY_DENOMINATOR] == 0
    assert out["per_check"]["cross_event_implication"]["sum_candidates_checked"] == 0


def test_a_self_contradictory_record_is_counted_not_swallowed(tmp_path):
    """Hits over an empty denominator: the audit must be able to COUNT these, which it could
    not do if the predicate raised on them."""
    _write(tmp_path, {"2026-07-01": [_rec(bracket=0, mono=0, pairs=0,
                                          anomalies=("bracket_arb",))]})
    out = A.audit(tmp_path)
    assert out["per_check"]["bracket_arb"]["class_counts"][EVIDENCE_INCOHERENT] == 1
    assert out["n_incoherent_records"] == 1
    assert out["incoherent_records"][0]["check"] == "bracket_arb"


def test_a_failed_fetch_is_not_reported_as_a_clean_looking_empty_pass(tmp_path):
    """An honest fetch failure already says so; only a pass that LOOKS healthy is the trap."""
    _write(tmp_path, {"2026-07-01": [_rec(completeness_ok=False, fetch_error="boom",
                                          n_markets=0)]})
    out = A.audit(tmp_path)
    assert out["per_check"]["bracket_arb"]["class_counts"][EVIDENCE_EMPTY_DENOMINATOR] == 1
    assert out["per_check"]["bracket_arb"]["n_clean_looking_empty_denominator_passes"] == 0


def test_max_day_closes_the_window(tmp_path):
    _write(tmp_path, {"2026-07-01": [_rec(bracket=1)], "2026-07-09": [_rec(bracket=1)]})
    assert A.audit(tmp_path)["n_records"] == 2
    assert A.audit(tmp_path, max_day="2026-07-01")["n_records"] == 1
    assert A.audit(tmp_path, max_day="2026-07-01")["n_capture_days"] == 1


def test_a_malformed_line_is_counted_never_silently_dropped(tmp_path):
    p = tmp_path / "dt=2026-07-01.jsonl"
    p.write_text(json.dumps(_rec(bracket=1)) + "\n{not json}\n", encoding="utf-8")
    out = A.audit(tmp_path)
    assert out["n_records"] == 1
    assert out["n_malformed_lines"] == 1


def test_main_writes_the_report(tmp_path):
    _write(tmp_path, {"2026-07-01": [_rec(bracket=1)]})
    out = tmp_path / "r.json"
    assert A.main(["--tape-dir", str(tmp_path), "--max-day", "2026-07-01",
                   "--out", str(out)]) == 0
    assert json.loads(out.read_text())["n_records"] == 1


# --------------------------------------------------------------------------- #
# acceptance — committed tape, CLOSED window
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def real():
    from core.io import REPO_ROOT
    d = REPO_ROOT / "tape" / "anomalies"
    if not d.is_dir():
        pytest.skip("committed anomalies tape not present")
    return A.audit(d, max_day=MAX_DAY)


def test_acceptance_population_is_the_closed_window(real):
    assert real["n_records"] == 248
    assert real["n_capture_days"] == 26
    assert real["n_malformed_lines"] == 0


def test_acceptance_s15s_implication_check_has_never_evaluated_a_candidate(real):
    """L296's headline, re-derived independently through the shared predicate: 243 passes
    carrying the counter, ALL empty-denominator, plus 5 that predate the counter entirely.
    Zero passes anywhere in committed history whose zero is readable."""
    blk = real["per_check"]["cross_event_implication"]
    cc = blk["class_counts"]
    assert cc[EVIDENCE_EMPTY_DENOMINATOR] == 243
    assert cc[EVIDENCE_COUNTER_ABSENT] == 5
    assert cc[EVIDENCE_HITS] == 0 and cc[EVIDENCE_INFORMATIVE_ZERO] == 0
    assert blk["n_passes_whose_zero_is_readable"] == 0
    assert blk["sum_candidates_checked"] == 0


def test_acceptance_s3s_own_checks_have_23_empty_denominator_passes(real):
    """New beside L296: S3's two checks are not immune either. 23 of 248 passes evaluated ZERO
    candidate groups while reporting completeness_ok, no fetch error, and thousands of markets
    scanned — a pass that looks clean and says nothing."""
    for name in ("bracket_arb", "cross_strike_monotonicity"):
        blk = real["per_check"][name]
        assert blk["class_counts"][EVIDENCE_EMPTY_DENOMINATOR] == 23
        assert blk["n_clean_looking_empty_denominator_passes"] == 23
        assert blk["sum_candidates_checked"] == 2210


def test_acceptance_the_bracket_check_has_never_fired_over_2210_real_checks(real):
    blk = real["per_check"]["bracket_arb"]
    assert blk["class_counts"][EVIDENCE_HITS] == 0
    assert blk["n_passes_whose_zero_is_readable"] == 225
    assert blk["sum_hits"] == 0


def test_acceptance_the_monotonicity_check_fired_on_137_passes(real):
    blk = real["per_check"]["cross_strike_monotonicity"]
    assert blk["class_counts"][EVIDENCE_HITS] == 137
    assert blk["n_passes_whose_zero_is_readable"] == 88
    assert blk["sum_hits"] == 43038


def test_acceptance_no_committed_record_is_self_contradictory(real):
    assert real["n_incoherent_records"] == 0


def test_acceptance_the_two_s3_counters_agree_on_every_committed_pass(real):
    """Descriptive, and NOT an identity the code guarantees — an event of three `between`
    rungs increments the bracket counter without incrementing the monotonicity one. Pinned so
    that if the population ever stops having this shape, someone has to look at why."""
    assert real["n_records_bracket_counter_equals_monotonicity_counter"] == 248
