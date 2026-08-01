"""scripts.tape_gap_monitor — collector gap-detector / missing-day monitor.

All offline. Unit tests build fixture tape under tmp_path; the three HARD
acceptance tests run the library functions over the repo's ACTUAL committed
tape (read-only, no network) per the Q44 falsifiable acceptance contract:
(1) flag the 2026-07-09 systemic full-day outage, (2) flag the 2026-07-15
interior under-capture, (3) do NOT hard-alert polymarket_pairs's benign
post-07-15 silence. The ntfy POST is always injected/monkeypatched — no test
ever touches the network.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from collection import burst_capture as _burst_capture
from core.timeutil import parse_iso_utc as _parse_iso_utc

# scripts/ is not a package; load the module by path.
_MOD_PATH = Path(__file__).resolve().parent.parent / "scripts" / "tape_gap_monitor.py"
_spec = importlib.util.spec_from_file_location("tape_gap_monitor", _MOD_PATH)
tgm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tgm)


UTC = timezone.utc


def _dt(y, mo, d, h=0, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def _write_lines(tape_root: Path, family: str, day: str, records):
    fam = tape_root / family
    fam.mkdir(parents=True, exist_ok=True)
    with open(fam / f"dt={day}.jsonl", "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def _pass(cid, captured_at, **extra):
    r = {"capture_id": cid, "captured_at": captured_at}
    r.update(extra)
    return r


def _hourly_day(tape_root, family, day, hours, minute=23, complete=None):
    """Write one pass per listed hour on `day` (a single line each)."""
    for h in hours:
        cid = f"{day}T{h:02d}{minute:02d}"
        ca = f"{day}T{h:02d}:{minute:02d}:00+00:00"
        extra = {} if complete is None else {"completeness_ok": complete}
        _write_lines(tape_root, family, day, [_pass(cid, ca, **extra)])


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def test_parse_iso_valid_naive_and_bad():
    assert tgm._parse_iso("2026-07-15T00:23:01+00:00") == _dt(2026, 7, 15, 0, 23, 1)
    assert tgm._parse_iso("2026-07-15T00:23:01.690374+00:00") == \
        datetime(2026, 7, 15, 0, 23, 1, 690374, tzinfo=UTC)
    naive = tgm._parse_iso("2026-07-15T00:23:01")
    assert naive is not None and naive.tzinfo is not None  # naive assumed UTC
    assert tgm._parse_iso("not-a-date") is None
    assert tgm._parse_iso(None) is None


def test_parse_day_from_filename():
    assert tgm._parse_day_from_filename(Path("dt=2026-07-15.jsonl")) == datetime(2026, 7, 15).date()
    # A regression-era DIRECTORY name (no .jsonl) is not a canonical day file.
    assert tgm._parse_day_from_filename(Path("dt=2026-07-09")) is None
    assert tgm._parse_day_from_filename(Path("_manifest.jsonl")) is None


# --------------------------------------------------------------------------- #
# Completeness extraction (honest, no fabricated True)
# --------------------------------------------------------------------------- #
def test_extract_completeness_top_level():
    assert tgm.extract_completeness({"completeness_ok": True}) is True
    assert tgm.extract_completeness({"completeness_ok": False}) is False


def test_extract_completeness_pass_complete():
    assert tgm.extract_completeness({"pass_complete": True}) is True


def test_extract_completeness_nested():
    # crypto_hourly nests completeness under `current`.
    assert tgm.extract_completeness({"current": {"completeness_ok": True}}) is True


def test_extract_completeness_ands_signals():
    # A False anywhere makes the line incomplete (never AND'd away to True).
    rec = {"pass_complete": True, "current": {"completeness_ok": False}}
    assert tgm.extract_completeness(rec) is False


def test_extract_completeness_no_signal_is_none_not_true():
    assert tgm.extract_completeness({"ticker": "X", "best_yes_ask": 0.4}) is None


# --------------------------------------------------------------------------- #
# Aggregate + evaluate over synthetic fixtures
# --------------------------------------------------------------------------- #
def test_healthy_hourly_no_alert(tmp_path):
    # Dual-collector ~48 passes/day; here 2 passes/hour across the window.
    now = _dt(2026, 7, 15, 12, 0)
    for day, hrs in (("2026-07-14", range(12, 24)), ("2026-07-15", range(0, 12))):
        _hourly_day(tmp_path, "sports_pairs", day, hrs, minute=23, complete=True)
        _hourly_day(tmp_path, "sports_pairs", day, hrs, minute=53, complete=True)
    agg = tgm.aggregate_family(tmp_path, "sports_pairs", now)
    rec = tgm.evaluate_family(agg, now)
    assert rec["alert"] is False
    assert rec["completeness_ok"] is True
    assert rec["capture_ratio"] is not None and rec["capture_ratio"] >= 0.9


# --------------------------------------------------------------------------- #
# Collector attribution (L117): minute-of-hour VPS(:2x)/cloud(:5x)/other split
# --------------------------------------------------------------------------- #
def test_collector_bucket_classification():
    assert tgm.collector_bucket(_dt(2026, 7, 19, 3, 23)) == "vps"
    assert tgm.collector_bucket(_dt(2026, 7, 19, 3, 20)) == "vps"
    assert tgm.collector_bucket(_dt(2026, 7, 19, 3, 29)) == "vps"
    assert tgm.collector_bucket(_dt(2026, 7, 19, 3, 53)) == "cloud"
    assert tgm.collector_bucket(_dt(2026, 7, 19, 3, 50)) == "cloud"
    assert tgm.collector_bucket(_dt(2026, 7, 19, 3, 59)) == "cloud"
    assert tgm.collector_bucket(_dt(2026, 7, 19, 3, 0)) == "other"
    assert tgm.collector_bucket(_dt(2026, 7, 19, 3, 45)) == "other"


def test_collectors_present_for_hourly_dual_kind(tmp_path):
    now = _dt(2026, 7, 15, 12, 0)
    for day, hrs in (("2026-07-14", range(12, 24)), ("2026-07-15", range(0, 12))):
        _hourly_day(tmp_path, "sports_pairs", day, hrs, minute=23, complete=True)
        _hourly_day(tmp_path, "sports_pairs", day, hrs, minute=53, complete=True)
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "sports_pairs", now), now)
    assert rec["collectors"] is not None
    assert rec["collectors"]["vps"]["passes"] == 24
    assert rec["collectors"]["cloud"]["passes"] == 24
    assert rec["collectors"]["other"]["passes"] == 0
    assert rec["collector_diagnosis"] is None  # healthy -> nothing to diagnose


def test_collectors_none_for_non_hourly_dual_kind(tmp_path):
    # econ_prints is a daily-econ-slot family, not a two-collector split.
    _write_lines(tmp_path, "econ_prints", "2026-07-13",
                 [_pass("c1", "2026-07-13T09:30:00+00:00", pass_complete=True)])
    now = _dt(2026, 7, 13, 10, 0)
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "econ_prints", now), now)
    assert rec["collectors"] is None
    assert rec["collector_diagnosis"] is None


def test_diagnoses_vps_dead_when_cloud_still_producing(tmp_path):
    # Only the cloud (:53) leg lands across the whole window -> clean under-capture
    # + an unambiguous vps_dead attribution, mirroring the real 2026-07-19/20 outage.
    now = _dt(2026, 7, 20, 0, 30)
    _hourly_day(tmp_path, "crypto_hourly", "2026-07-19", range(0, 24), minute=54, complete=True)
    _hourly_day(tmp_path, "crypto_hourly", "2026-07-20", [0], minute=54, complete=True)
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "crypto_hourly", now), now)
    assert rec["alert"] is True
    assert "under_capture" in rec["alert_reason"]
    assert rec["collectors"]["vps"]["passes"] == 0
    assert rec["collectors"]["cloud"]["passes"] > 0
    assert rec["collector_diagnosis"] == \
        "vps_dead: 0 passes in window, cloud collector still producing"
    assert "vps_dead" in rec["alert_reason"]


def test_diagnoses_cloud_dead_when_vps_still_producing(tmp_path):
    now = _dt(2026, 7, 20, 0, 30)
    _hourly_day(tmp_path, "crypto_hourly", "2026-07-19", range(0, 24), minute=23, complete=True)
    _hourly_day(tmp_path, "crypto_hourly", "2026-07-20", [0], minute=23, complete=True)
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "crypto_hourly", now), now)
    assert rec["alert"] is True
    assert rec["collectors"]["cloud"]["passes"] == 0
    assert rec["collectors"]["vps"]["passes"] > 0
    assert rec["collector_diagnosis"] == \
        "cloud_dead: 0 passes in window, vps collector still producing"


def test_no_diagnosis_when_both_collectors_still_present(tmp_path):
    # Both sides thinned (e.g. every other hour) -> under-capture alert fires but
    # neither collector is at zero, so no attribution is guessed.
    now = _dt(2026, 7, 16, 0, 30)
    _hourly_day(tmp_path, "orderbook_depth", "2026-07-15", range(0, 24, 4), minute=23, complete=None)
    _hourly_day(tmp_path, "orderbook_depth", "2026-07-15", range(0, 24, 4), minute=53, complete=None)
    _hourly_day(tmp_path, "orderbook_depth", "2026-07-16", [0], minute=23, complete=None)
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "orderbook_depth", now), now)
    assert rec["alert"] is True
    assert "under_capture" in rec["alert_reason"]
    assert rec["collectors"]["vps"]["passes"] > 0
    assert rec["collectors"]["cloud"]["passes"] > 0
    assert rec["collector_diagnosis"] is None
    assert "vps_dead" not in rec["alert_reason"]
    assert "cloud_dead" not in rec["alert_reason"]


def test_unmapped_family_other_only_leg_stays_unattributed(tmp_path):
    # An UNMAPPED hourly-dual family (crypto_hourly is not in EXPECTED_COLLECTOR_BUCKETS)
    # whose only leg lands in "other" is honestly left unattributed rather than forced
    # into vps or cloud — L118's exact both-named-buckets-zero behavior, preserved.
    now = _dt(2026, 7, 20, 0, 30)
    _hourly_day(tmp_path, "crypto_hourly", "2026-07-19", range(0, 24), minute=3, complete=None)
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "crypto_hourly", now), now)
    assert rec["alert"] is True  # a full window of drops still alerts
    assert rec["collectors"]["vps"]["passes"] == 0
    assert rec["collectors"]["cloud"]["passes"] == 0
    assert rec["collectors"]["other"]["passes"] > 0
    assert rec["collector_diagnosis"] is None  # unmapped => no attribution guessed


# --------------------------------------------------------------------------- #
# Per-family expected-bucket map (L120): name a dead PRIMARY leg even when the
# surviving leg is bucketed "other".
# --------------------------------------------------------------------------- #
def test_mapped_weather_books_names_vps_dead_when_only_other_survives(tmp_path):
    # weather_books IS in EXPECTED_COLLECTOR_BUCKETS ({primary: vps, secondary: other}).
    # Its VPS(:2x) primary leg died; only the "other"(:00-03) secondary survives.
    # L118 would read vps=0 & cloud=0 as ambiguous; the L120 map names vps_dead.
    now = _dt(2026, 7, 20, 0, 30)
    _hourly_day(tmp_path, "weather_books", "2026-07-19", range(0, 24), minute=3, complete=None)
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "weather_books", now), now)
    assert rec["alert"] is True
    assert rec["collectors"]["vps"]["passes"] == 0
    assert rec["collectors"]["cloud"]["passes"] == 0
    assert rec["collectors"]["other"]["passes"] > 0
    assert rec["collector_diagnosis"] == \
        "vps_dead: 0 passes in window, other collector still producing"
    assert "vps_dead" in rec["alert_reason"]


def test_mapped_weather_books_names_secondary_dead_when_only_primary_survives(tmp_path):
    # The symmetric case: the "other" secondary died, the VPS primary survives.
    # A thinned vps-only book so the under-capture ratio still fires the alert.
    now = _dt(2026, 7, 16, 0, 30)
    _hourly_day(tmp_path, "weather_books", "2026-07-15", range(0, 24), minute=27, complete=None)
    _hourly_day(tmp_path, "weather_books", "2026-07-16", [0], minute=27, complete=None)
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "weather_books", now), now)
    assert rec["alert"] is True
    assert rec["collectors"]["vps"]["passes"] > 0
    assert rec["collectors"]["other"]["passes"] == 0
    assert rec["collector_diagnosis"] == \
        "other_dead: 0 passes in window, vps collector still producing"


def test_mapped_family_both_expected_buckets_healthy_unattributed(tmp_path):
    # Both the vps primary and the "other" secondary produce passes but the book is
    # thinned enough to trip under-capture: no single leg to blame => unattributed.
    now = _dt(2026, 7, 16, 0, 30)
    _hourly_day(tmp_path, "weather_books", "2026-07-15", range(0, 24, 4), minute=27, complete=None)
    _hourly_day(tmp_path, "weather_books", "2026-07-15", range(0, 24, 4), minute=2, complete=None)
    _hourly_day(tmp_path, "weather_books", "2026-07-16", [0], minute=27, complete=None)
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "weather_books", now), now)
    assert rec["alert"] is True
    assert "under_capture" in rec["alert_reason"]
    assert rec["collectors"]["vps"]["passes"] > 0
    assert rec["collectors"]["other"]["passes"] > 0
    assert rec["collector_diagnosis"] is None


def test_mapped_family_both_expected_buckets_zero_unattributed(tmp_path):
    # A mapped family whose passes land ENTIRELY outside its expected buckets
    # (here only the :5x cloud window, which is neither weather_books' primary
    # `vps` nor its secondary `other`) => both expected buckets zero => the L118
    # "never guess when ambiguous" discipline holds and nothing is attributed.
    now = _dt(2026, 7, 20, 0, 30)
    _hourly_day(tmp_path, "weather_books", "2026-07-19", range(0, 24), minute=55, complete=None)
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "weather_books", now), now)
    assert rec["alert"] is True
    assert rec["collectors"]["vps"]["passes"] == 0     # primary
    assert rec["collectors"]["other"]["passes"] == 0   # secondary
    assert rec["collectors"]["cloud"]["passes"] > 0    # neither expected bucket
    assert rec["collector_diagnosis"] is None


def test_diagnose_collector_helper_mapped_and_unmapped():
    # Direct unit coverage of the attribution helper for both paths.
    def cols(vps, cloud, other):
        return {"vps": {"passes": vps}, "cloud": {"passes": cloud}, "other": {"passes": other}}
    # Mapped (weather_books: primary vps, secondary other).
    assert tgm.diagnose_collector("weather_books", cols(0, 0, 5)) == \
        "vps_dead: 0 passes in window, other collector still producing"
    assert tgm.diagnose_collector("weather_books", cols(5, 0, 0)) == \
        "other_dead: 0 passes in window, vps collector still producing"
    assert tgm.diagnose_collector("weather_books", cols(0, 9, 0)) is None  # both expected zero
    assert tgm.diagnose_collector("weather_books", cols(5, 0, 5)) is None  # both expected non-zero
    # Unmapped keeps L118 vps/cloud logic exactly.
    assert tgm.diagnose_collector("crypto_hourly", cols(0, 5, 0)) == \
        "vps_dead: 0 passes in window, cloud collector still producing"
    assert tgm.diagnose_collector("crypto_hourly", cols(5, 0, 0)) == \
        "cloud_dead: 0 passes in window, vps collector still producing"
    assert tgm.diagnose_collector("crypto_hourly", cols(0, 0, 5)) is None  # other-only, unmapped


def test_collector_summary_tracks_newest_per_bucket(tmp_path):
    _hourly_day(tmp_path, "sports_pairs", "2026-07-15", [0, 1, 2], minute=23, complete=True)
    _hourly_day(tmp_path, "sports_pairs", "2026-07-15", [0, 1], minute=53, complete=True)
    now = _dt(2026, 7, 15, 4, 0)
    agg = tgm.aggregate_family(tmp_path, "sports_pairs", now)
    summary = agg.collector_summary()
    assert summary["vps"]["passes"] == 3
    assert summary["vps"]["newest_captured_at"] == "2026-07-15T02:23:00+00:00"
    assert summary["cloud"]["passes"] == 2
    assert summary["cloud"]["newest_captured_at"] == "2026-07-15T01:53:00+00:00"
    assert summary["other"]["passes"] == 0
    assert summary["other"]["newest_captured_at"] is None


def test_format_collector_diagnoses_lists_only_diagnosed_alerts(tmp_path):
    now = _dt(2026, 7, 20, 0, 30)
    _hourly_day(tmp_path, "crypto_hourly", "2026-07-19", range(0, 24), minute=54, complete=True)
    report = tgm.build_report(tmp_path, now, families=["crypto_hourly"])
    out = tgm.format_collector_diagnoses(report)
    assert "crypto_hourly: vps_dead" in out


def test_format_collector_diagnoses_empty_when_nothing_to_diagnose(tmp_path):
    now = _dt(2026, 7, 15, 12, 0)
    for day, hrs in (("2026-07-14", range(12, 24)), ("2026-07-15", range(0, 12))):
        _hourly_day(tmp_path, "sports_pairs", day, hrs, minute=23, complete=True)
        _hourly_day(tmp_path, "sports_pairs", day, hrs, minute=53, complete=True)
    report = tgm.build_report(tmp_path, now, families=["sports_pairs"])
    assert tgm.format_collector_diagnoses(report) == ""


def test_stale_hourly_alerts(tmp_path):
    now = _dt(2026, 7, 15, 12, 0)
    # last pass 5h before now, nothing since -> stale (> 2h threshold).
    _hourly_day(tmp_path, "crypto_hourly", "2026-07-15", [7], minute=0, complete=True)
    agg = tgm.aggregate_family(tmp_path, "crypto_hourly", now)
    rec = tgm.evaluate_family(agg, now)
    assert rec["alert"] is True
    assert "stale" in rec["alert_reason"]
    assert rec["age_hours"] == pytest.approx(5.0, abs=0.01)


def test_under_capture_alerts_without_contiguous_gap(tmp_path):
    # Full-day span but only ~half the expected passes (one collector dropped):
    # distributed drops, max consecutive gap stays ~1h so only the ratio detector fires.
    now = _dt(2026, 7, 16, 0, 30)
    _hourly_day(tmp_path, "orderbook_depth", "2026-07-15", range(0, 24), minute=23, complete=None)
    # add a couple more so newest is fresh (no stale), still ~24-26 passes in window
    _hourly_day(tmp_path, "orderbook_depth", "2026-07-16", [0], minute=23, complete=None)
    agg = tgm.aggregate_family(tmp_path, "orderbook_depth", now)
    rec = tgm.evaluate_family(agg, now)
    assert rec["alert"] is True
    assert "under_capture" in rec["alert_reason"]
    assert "stale" not in rec["alert_reason"]  # fresh, so not the stale path
    assert rec["missed_passes_estimate"] > 2


def test_daily_family_stale_threshold_two_days(tmp_path):
    # econ_prints is daily (interval 24h) -> alert only past ~2 days silent.
    _write_lines(tmp_path, "econ_prints", "2026-07-13",
                 [_pass("c1", "2026-07-13T09:30:00+00:00", pass_complete=True)])
    # 1.5 days later: no alert.
    rec_ok = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "econ_prints", _dt(2026, 7, 14, 21, 0)),
                                 _dt(2026, 7, 14, 21, 0))
    assert rec_ok["alert"] is False
    # 3 days later: alert.
    rec_bad = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "econ_prints", _dt(2026, 7, 16, 12, 0)),
                                  _dt(2026, 7, 16, 12, 0))
    assert rec_bad["alert"] is True
    assert "stale" in rec_bad["alert_reason"]


def test_one_shot_family_never_alerts(tmp_path):
    # Repointed (L127): this test covers the "a family with no cadence config never
    # pages on age" property. It USED to use hyperliquid_funding, but that family is
    # now join-critical (JOIN_CRITICAL_ONE_SHOT) and DOES alert on join-staleness —
    # covered by test_acceptance_8_l127_hyperliquid_funding_join_stale below. So we
    # repoint to a genuinely non-join-critical, unconfigured family name (not in
    # FAMILY_CONFIG and not in JOIN_CRITICAL_ONE_SHOT), which falls through to the
    # default {"interval_h": None, ...} — the pure "uncadenced, never pages" case.
    fam = "some_backfill_family"  # unconfigured -> default interval_h=None, not join-critical
    assert fam not in tgm.FAMILY_CONFIG
    assert fam not in tgm.JOIN_CRITICAL_ONE_SHOT
    _write_lines(tmp_path, fam, "2026-07-10",
                 [_pass("c1", "2026-07-10T01:00:00+00:00", record_type="funding_rates")])
    now = _dt(2026, 8, 1, 0, 0)  # weeks later
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, fam, now), now)
    assert rec["alert"] is False
    assert rec["completeness_ok"] is None  # no signal -> not fabricated True


def test_hyperliquid_funding_forward_refreshed_not_join_critical(tmp_path):
    # L127/L128 close-out (candidate (a), this run supersedes L128's config choice):
    # hyperliquid_funding.run_incremental is now wired into collection/hourly_pass.py and runs
    # every pass, so the family GRADUATED from a frozen join-critical one-shot to a
    # forward-refreshed hourly family. Its freeze is now caught by the STALE detector at 2h,
    # which strictly subsumes the old 48h join-staleness stopgap — so it is no longer a member
    # of JOIN_CRITICAL_ONE_SHOT (which is now empty; the mechanism stays dormant for future use).
    assert "hyperliquid_funding" not in tgm.JOIN_CRITICAL_ONE_SHOT
    cfg = tgm.FAMILY_CONFIG["hyperliquid_funding"]
    assert cfg["interval_h"] == 1.0
    assert cfg["kind"] == "hourly"
    # STALE-only: single-WRITE-per-new-print, not per pass, so no fixed passes_per_day / ratio.
    assert cfg["passes_per_day"] is None
    # kind != "hourly-dual" -> no vps/cloud attribution invented for a single-writer family.
    _write_lines(tmp_path, "hyperliquid_funding", "2026-07-21",
                 [_pass("c1", "2026-07-21T00:23:00+00:00")])
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "hyperliquid_funding",
                                                   _dt(2026, 7, 21, 0, 40)), _dt(2026, 7, 21, 0, 40))
    assert rec["collectors"] is None


def test_hyperliquid_funding_stale_alerts_within_cadence(tmp_path):
    # Now a proper hourly family: a fresh print keeps it healthy; a >2h silence pages via STALE
    # (the "join is going stale" signal now caught in ~2h, not the old 48h).
    _write_lines(tmp_path, "hyperliquid_funding", "2026-07-21",
                 [_pass("c1", "2026-07-21T05:23:00+00:00")])
    near = _dt(2026, 7, 21, 6, 30)  # ~1h since last print -> healthy
    rec_ok = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "hyperliquid_funding", near), near)
    assert rec_ok["alert"] is False
    far = _dt(2026, 7, 21, 9, 0)    # ~3.6h silent -> stale (> 2h threshold)
    rec_bad = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "hyperliquid_funding", far), far)
    assert rec_bad["alert"] is True
    assert "stale" in rec_bad["alert_reason"]
    assert rec_bad["age_hours"] > 2.0


def test_join_critical_one_shot_alerts_on_join_staleness(tmp_path, monkeypatch):
    # The JOIN-STALENESS mechanism (L128) is retained (dormant) for any FUTURE genuinely-one-shot
    # leg a live join depends on. Register a synthetic such family to prove the detector still
    # fires: an UNCONFIGURED family (interval_h=None -> STALE/UNDER-CAPTURE are no-ops, `dark`
    # cannot fire) that IS in JOIN_CRITICAL_ONE_SHOT pages purely on join-age.
    fam = "synthetic_join_partner"
    assert fam not in tgm.FAMILY_CONFIG  # unconfigured -> default interval_h=None
    monkeypatch.setitem(tgm.JOIN_CRITICAL_ONE_SHOT, fam,
                        {"max_age_h": 48.0, "consumer": "scripts/some_live_join.py"})
    _write_lines(tmp_path, fam, "2026-07-17",
                 [_pass("c1", "2026-07-17T06:20:03+00:00", record_type="funding_rates")])
    # Well within threshold -> no alert.
    near = _dt(2026, 7, 18, 6, 0)  # ~24h
    rec_ok = tgm.evaluate_family(tgm.aggregate_family(tmp_path, fam, near), near)
    assert rec_ok["alert"] is False
    assert rec_ok["alert_reason"] == "ok"
    # Past the 48h threshold -> join-staleness alert.
    far = _dt(2026, 7, 20, 6, 0)  # ~72h
    rec_bad = tgm.evaluate_family(tgm.aggregate_family(tmp_path, fam, far), far)
    assert rec_bad["alert"] is True
    assert "join_stale" in rec_bad["alert_reason"]
    assert "scripts/some_live_join.py" in rec_bad["alert_reason"]
    assert rec_bad["age_hours"] > 48.0
    # interval_h is None -> this family is never treated as "dark" and never gets a
    # fabricated cadence expectation.
    assert not rec_bad["alert_reason"].startswith("dark")


def test_dark_family_shown_not_paged(tmp_path):
    # Family whose only tape is dated AFTER now (not yet active at this reference).
    _hourly_day(tmp_path, "weather_books", "2026-07-16", range(0, 5), minute=23)
    now = _dt(2026, 7, 10, 0, 0)
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "weather_books", now), now)
    assert rec["alert"] is False
    assert rec["alert_reason"].startswith("dark")
    assert rec["last_captured_at"] is None


def test_partial_completeness_is_false(tmp_path):
    now = _dt(2026, 7, 15, 1, 0)
    _write_lines(tmp_path, "sports_pairs", "2026-07-15", [
        _pass("c1", "2026-07-15T00:23:00+00:00", completeness_ok=True),
        _pass("c1", "2026-07-15T00:23:00+00:00", completeness_ok=False),  # one game incomplete
    ])
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "sports_pairs", now), now)
    assert rec["completeness_ok"] is False
    assert rec["completeness_detail"]["incomplete_lines"] == 1


def test_regression_directory_excluded_reads_as_gap(tmp_path):
    # dt=2026-07-09 as a DIRECTORY (L25/L29 regression) must be ignored, so the
    # day reads as a genuine gap.
    _write_lines(tmp_path, "sports_pairs", "2026-07-08",
                 [_pass("c1", "2026-07-08T23:00:00+00:00", completeness_ok=True)])
    (tmp_path / "sports_pairs" / "dt=2026-07-09").mkdir(parents=True)
    (tmp_path / "sports_pairs" / "dt=2026-07-09" / "raw.json").write_text("{}")
    now = _dt(2026, 7, 9, 23, 0)  # 24h after last real capture
    agg = tgm.aggregate_family(tmp_path, "sports_pairs", now)
    assert agg.newest_captured_at == _dt(2026, 7, 8, 23, 0)
    rec = tgm.evaluate_family(agg, now)
    assert rec["alert"] is True  # the 07-09 directory contributed no capture


# --------------------------------------------------------------------------- #
# Benign-silence discriminator
# --------------------------------------------------------------------------- #
def test_benign_silence_suppresses_alert_on_onset_day(tmp_path):
    # polymarket_pairs last captured on the documented silent_since day -> benign.
    _hourly_day(tmp_path, "polymarket_pairs", "2026-07-15", range(0, 21), minute=23)
    now = _dt(2026, 7, 17, 0, 0)  # ~1.5 days of silence -> would be stale
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "polymarket_pairs", now), now)
    assert rec["alert"] is False
    assert rec["alert_reason"].startswith("known_benign_silence")


def test_benign_silence_does_not_mask_different_onset(tmp_path):
    # Same family, but its last capture is a DIFFERENT day (not the documented
    # onset) -> the benign entry must NOT suppress; a real stall pages.
    _hourly_day(tmp_path, "polymarket_pairs", "2026-07-12", range(0, 21), minute=23)
    now = _dt(2026, 7, 14, 0, 0)
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "polymarket_pairs", now), now)
    assert rec["alert"] is True
    assert "stale" in rec["alert_reason"]


# --------------------------------------------------------------------------- #
# ntfy (injected POST -> no network)
# --------------------------------------------------------------------------- #
class _RecPost:
    def __init__(self):
        self.calls = []

    def __call__(self, url, data, headers):
        self.calls.append((url, data, headers))


def _report(alert_family=None):
    rep = {}
    for fam in ("sports_pairs", "crypto_hourly"):
        rep[fam] = {"alert": fam == alert_family, "alert_reason": "under_capture: x" if fam == alert_family else "ok"}
    return rep


def test_notify_no_alerts_is_noop():
    post = _RecPost()
    out = tgm.maybe_notify(_report(alert_family=None), url="https://ntfy.example/t", post_fn=post, env={})
    assert out["sent"] is False and out["reason"] == "no_alerts"
    assert post.calls == []


def test_notify_posts_priority_high_with_url_arg():
    post = _RecPost()
    out = tgm.maybe_notify(_report(alert_family="sports_pairs"),
                           url="https://ntfy.example/t", post_fn=post, env={})
    assert out["sent"] is True
    assert len(post.calls) == 1
    url, data, headers = post.calls[0]
    assert url == "https://ntfy.example/t"
    assert headers.get("Priority") == "high"
    assert b"sports_pairs" in data


def test_notify_url_from_env():
    post = _RecPost()
    out = tgm.maybe_notify(_report(alert_family="sports_pairs"),
                           url=None, post_fn=post, env={"NTFY_TOPIC_URL": "https://ntfy.example/env"})
    assert out["sent"] is True
    assert post.calls[0][0] == "https://ntfy.example/env"


def test_notify_absent_url_is_noop_not_crash():
    post = _RecPost()
    out = tgm.maybe_notify(_report(alert_family="sports_pairs"), url=None, post_fn=post, env={})
    assert out["sent"] is False and out["reason"] == "no_url"
    assert post.calls == []  # never posts, never raises


def test_notify_post_error_is_swallowed():
    def boom(url, data, headers):
        raise RuntimeError("network down")
    out = tgm.maybe_notify(_report(alert_family="sports_pairs"),
                           url="https://ntfy.example/t", post_fn=boom, env={})
    assert out["sent"] is False and out["reason"].startswith("post_error")


# --------------------------------------------------------------------------- #
# Presentation + CLI smoke
# --------------------------------------------------------------------------- #
def test_format_table_smoke(tmp_path):
    now = _dt(2026, 7, 15, 12, 0)
    _hourly_day(tmp_path, "sports_pairs", "2026-07-15", [7], minute=0, complete=True)
    report = tgm.build_report(tmp_path, now)
    table = tgm.format_table(report, now)
    assert "sports_pairs" in table
    assert "tape gap monitor" in table


def test_main_json_over_fixture(tmp_path, capsys):
    _hourly_day(tmp_path, "sports_pairs", "2026-07-15", [7], minute=0, complete=True)
    rc = tgm.main(["--tape-root", str(tmp_path), "--now", "2026-07-15T12:00:00+00:00",
                   "--json", "--no-notify"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "sports_pairs" in parsed


# --------------------------------------------------------------------------- #
# HARD ACCEPTANCE — over the REAL committed tape (read-only, no network)
# --------------------------------------------------------------------------- #
_REAL_TAPE = tgm._default_tape_root()
_real = pytest.mark.skipif(not _REAL_TAPE.is_dir(), reason="committed tape/ not present")


@_real
def test_acceptance_1_systemic_0709_outage():
    """All hourly families silent across 2026-07-09 -> every one alerts."""
    now = _dt(2026, 7, 10, 0, 5)
    report = tgm.build_report(_REAL_TAPE, now)
    for fam in ("sports_pairs", "crypto_hourly", "orderbook_depth",
                "polymarket_pairs", "polymarket_macro_pairs"):
        assert report[fam]["alert"] is True, f"{fam} should alert on the 07-09 outage: {report[fam]}"
        assert "stale" in report[fam]["alert_reason"]
    # The benign entry must NOT mask polymarket_pairs here: its last capture then
    # was 07-08 (not the documented 07-15 onset), so it is a real outage, not benign.
    assert not report["polymarket_pairs"]["alert_reason"].startswith("known_benign_silence")


@_real
def test_acceptance_2_interior_undercapture_0715():
    """2026-07-15 dropped ~16 of the two-collector passes (full-day span, ~32/48)."""
    now = _dt(2026, 7, 16, 0, 30)
    report = tgm.build_report(_REAL_TAPE, now)
    for fam in ("sports_pairs", "crypto_hourly", "orderbook_depth", "polymarket_macro_pairs"):
        r = report[fam]
        assert r["alert"] is True, f"{fam} should alert on the 07-15 under-capture: {r}"
        assert "under_capture" in r["alert_reason"]
        assert r["capture_ratio"] is not None and r["capture_ratio"] < tgm.UNDER_CAPTURE_FLOOR
        assert r["missed_passes_estimate"] >= 10  # ~16 dropped in reality


@_real
def test_acceptance_3_polymarket_benign_not_hard_alerted():
    """polymarket_pairs's post-07-15 silence is the documented benign WC-resolution
    zero-match, NOT a hard alert."""
    now = _dt(2026, 7, 16, 0, 30)
    report = tgm.build_report(_REAL_TAPE, now)
    r = report["polymarket_pairs"]
    assert r["alert"] is False
    assert r["alert_reason"].startswith("known_benign_silence")
    # And later, when the silence is unambiguously stale, still benign (not paged).
    later = _dt(2026, 7, 17, 12, 0)
    r2 = tgm.build_report(_REAL_TAPE, later)["polymarket_pairs"]
    assert r2["alert"] is False


@_real
def test_acceptance_4_l117_vps_dead_0719_attributed():
    """The real 2026-07-19 VPS-cron death (findings/2026-07-20-tape-cadence-decline-
    vps-collector-down.md, lesson L117): over the 24h window ending 2026-07-20T00:30,
    the VPS(:2x) bucket is genuinely empty for the affected hourly-dual families while
    cloud(:5x) keeps producing -> an unambiguous vps_dead attribution, not just an
    aggregate under-capture ratio."""
    now = _dt(2026, 7, 20, 0, 30)
    report = tgm.build_report(_REAL_TAPE, now)
    for fam in ("crypto_hourly", "orderbook_depth", "sports_pairs", "polymarket_macro_pairs"):
        r = report[fam]
        assert r["alert"] is True, f"{fam} should alert in this window: {r}"
        assert r["collectors"]["vps"]["passes"] == 0, f"{fam}: {r['collectors']}"
        assert r["collectors"]["cloud"]["passes"] > 0, f"{fam}: {r['collectors']}"
        assert r["collector_diagnosis"] == \
            "vps_dead: 0 passes in window, cloud collector still producing", \
            f"{fam}: {r['collector_diagnosis']}"


@_real
def test_acceptance_5_l120_weather_books_vps_dead_via_other_survivor():
    """The real 2026-07-19 VPS-cron death as seen by weather_books, whose SECOND
    collector fires at minutes ~00-03 ("other", not the :5x cloud window). Over the
    24h window ending 2026-07-20T00:30 the committed tape shows the VPS(:2x) bucket
    genuinely empty while the "other" leg keeps producing (~6 passes) — L118 would
    read vps=0 & cloud=0 as ambiguous, but the L120 EXPECTED_COLLECTOR_BUCKETS map
    ({primary: vps, secondary: other}) names the dead primary. This is anchored to
    the real committed tape, not a fixture (mirrors acceptance test 4)."""
    now = _dt(2026, 7, 20, 0, 30)
    r = tgm.build_report(_REAL_TAPE, now)["weather_books"]
    assert r["alert"] is True, r
    assert r["collectors"]["vps"]["passes"] == 0, r["collectors"]
    assert r["collectors"]["cloud"]["passes"] == 0, r["collectors"]
    assert r["collectors"]["other"]["passes"] > 0, r["collectors"]
    assert r["collector_diagnosis"] == \
        "vps_dead: 0 passes in window, other collector still producing", \
        r["collector_diagnosis"]
    # Sanity: L118's four dual-cron families are unmapped and unchanged — they still
    # read the standard "cloud collector still producing" attribution, not "other".
    crypto = tgm.build_report(_REAL_TAPE, now)["crypto_hourly"]
    assert crypto["collector_diagnosis"] == \
        "vps_dead: 0 passes in window, cloud collector still producing"


@_real
def test_acceptance_6_l123_settlement_ledger_frozen_since_build_day():
    """L123 (findings/2026-07-21-settlement-ledger-frozen-hour10-deadzone.md,
    verifier-CONFIRMED): `settlement_ledger` fires on its own single exact UTC hour
    (10) that the live every-3h `kalshi-collector` cron never lands on, so it has
    been silently frozen at its 2026-07-17 build day (last real captured_at
    2026-07-17T12:23:02Z) ever since — invisibly, because this family was never
    registered in FAMILY_CONFIG (an unconfigured family's STALE detector is a
    no-op). This is the enforcement half of L123: registering the family here
    means the monitor now actually catches the real, currently-ongoing freeze,
    anchored to the real committed tape (mirrors acceptance tests 4/5), not a
    fixture."""
    now = _dt(2026, 7, 21, 6, 0)
    r = tgm.build_report(_REAL_TAPE, now)["settlement_ledger"]
    assert r["kind"] == "daily"
    assert r["alert"] is True, r
    assert "stale" in r["alert_reason"], r["alert_reason"]
    assert r["age_hours"] > 48.0, r["age_hours"]


@_real
def test_acceptance_7_l127_perp_tape_reclassified_hourly_dual():
    """L127: perp_tape was misfiled as "one-shot-backfill" since its 2026-07-16 build,
    even though `collection/hourly_pass.py` runs it every hourly_pass() call same as
    the other hourly-dual families — so its real post-L117-VPS-death degradation
    (same root cause as crypto_hourly/sports_pairs/orderbook_depth) was structurally
    invisible: an interval_h=None family never runs the UNDER-CAPTURE check. Anchored
    to the real committed tape (mirrors acceptance tests 4/5/6), not a fixture."""
    now = _dt(2026, 7, 21, 18, 0)
    r = tgm.build_report(_REAL_TAPE, now)["perp_tape"]
    assert r["kind"] == "hourly-dual"
    assert r["alert"] is True, r
    assert "under_capture" in r["alert_reason"], r["alert_reason"]
    assert r["capture_ratio"] < 0.8, r["capture_ratio"]
    # perp_tape's surviving collector lands in the "other" minute-bucket (~00-04),
    # same signature as weather_books' L120 secondary leg — the L127 mapping in
    # EXPECTED_COLLECTOR_BUCKETS should name vps_dead rather than leaving it
    # ambiguous (vps=0 & cloud=0, the fate an unmapped family would suffer here).
    assert r["collectors"]["vps"]["passes"] == 0, r["collectors"]
    assert r["collectors"]["other"]["passes"] > 0, r["collectors"]
    assert r["collector_diagnosis"] == \
        "vps_dead: 0 passes in window, other collector still producing", \
        r["collector_diagnosis"]


@_real
def test_acceptance_8_l127_hyperliquid_funding_forward_refreshed_catches_freeze_via_stale():
    """L127/L128 close-out (candidate (a), this run): hyperliquid_funding.run_incremental is
    now wired into collection/hourly_pass.py, so the family is a forward-refreshed hourly family
    (interval_h=1.0, kind="hourly"), NOT the old frozen one-shot. Its freeze is now caught by
    the STALE detector at 2h instead of the 48h join-staleness stopgap it graduated out of.

    Anchored to the real committed tape at a HISTORICAL reference time (2026-07-19T06:00Z),
    where the only capture at-or-before `now` is the original 2026-07-17T06:20:03Z manual
    backfill (~47.7h old) — this is immune to any fresh forward-refresh lines the newly-wired
    leg appends (dated after this `now`, they are filtered out), so it deterministically proves
    the reclassified detector fires on exactly the freeze L127 flagged."""
    now = _dt(2026, 7, 19, 6, 0)
    r = tgm.build_report(_REAL_TAPE, now)["hyperliquid_funding"]
    assert r["kind"] == "hourly", r
    assert r["alert"] is True, r
    assert "stale" in r["alert_reason"], r["alert_reason"]
    assert r["age_hours"] > 2.0, r["age_hours"]
    # graduated out of the join-staleness stopgap: no longer a JOIN_CRITICAL_ONE_SHOT member.
    assert "hyperliquid_funding" not in tgm.JOIN_CRITICAL_ONE_SHOT


@_real
def test_acceptance_9_l139_anomalies_was_a_monitoring_blind_spot():
    """L139: `anomalies` (collection/hourly_pass.py runs `scripts/anomaly_sweep.py` only
    when `ts.hour == ANOMALY_SWEEP_UTC_HOUR`, the same single-exact-UTC-hour gate shape
    as `settlement_ledger` (L123) and `weather_actuals` (L126)) was never registered in
    FAMILY_CONFIG. Since `build_report`'s default family list is
    `list(FAMILY_CONFIG.keys())`, an unregistered family isn't just unscored — it never
    appears in the report at all. Unlike L123/L126, `anomalies` is NOT currently frozen
    (real committed tape shows a healthy daily cadence through 2026-07-22); this test
    proves the registration both (a) makes the family visible in the report and (b) does
    not false-alarm on its current healthy state, anchored just after its real last
    capture."""
    # L140: anchor `now` to the tape's OWN newest anomalies capture, not a hardcoded
    # calendar date. `anomalies` is a healthy daily-growing family; the original
    # hardcoded now=2026-07-22T12:00 assumed the newest committed capture stays frozen,
    # which silently flips red the instant a routine fresh capture lands (it did, on
    # 2026-07-23) — the real-tape-anchored-`now` time-bomb L140 records. Probing with a
    # far-future `now` reads the true newest capture regardless of when it is.
    newest = tgm._parse_iso(
        tgm.build_report(_REAL_TAPE, _dt(2999, 1, 1))["anomalies"]["last_captured_at"])
    now = newest + timedelta(hours=2)
    report = tgm.build_report(_REAL_TAPE, now)
    assert "anomalies" in report
    r = report["anomalies"]
    assert r["kind"] == "daily-econ-slot", r
    assert r["alert"] is False, r
    assert r["age_hours"] < 24.0, r["age_hours"]


@_real
def test_acceptance_10_l139_anomalies_would_be_caught_if_it_ever_froze():
    """L139 continued: proves the registration is load-bearing, not cosmetic — evaluated
    far enough past the real last committed `anomalies` capture (2026-07-22T10:05:33Z) to
    cross the STALE threshold (2 x 24h = 48h), the monitor now actually pages, closing the
    exact blind spot that let `settlement_ledger` (L123) and `weather_actuals` (L126) each
    freeze silently for days before anyone noticed by hand."""
    # L140: derive `now` from the real tape's own newest anomalies capture + just past
    # the 2x24h STALE threshold, so this proves the registration is load-bearing whatever
    # the newest committed capture happens to be. A hardcoded now=2026-07-24T12:00 broke
    # on 2026-07-23 when a fresh healthy capture pushed age below 48h (alert flipped off).
    newest = tgm._parse_iso(
        tgm.build_report(_REAL_TAPE, _dt(2999, 1, 1))["anomalies"]["last_captured_at"])
    now = newest + timedelta(hours=49)
    r = tgm.build_report(_REAL_TAPE, now)["anomalies"]
    assert r["alert"] is True, r
    assert "stale" in r["alert_reason"], r["alert_reason"]
    assert r["age_hours"] > 48.0, r["age_hours"]


# --------------------------------------------------------------------------- #
# Retrospective-list family coverage (L171, 2026-07-26)
# --------------------------------------------------------------------------- #
def test_retrospective_coverage_unregistered_family_returns_none(tmp_path):
    _hourly_day(tmp_path, "crypto_hourly", "2026-07-15", [10])
    assert tgm.retrospective_coverage(tmp_path, "crypto_hourly") is None


def test_retrospective_coverage_no_tape_at_all(tmp_path):
    assert tgm.retrospective_coverage(tmp_path, "hyperliquid_funding") == {
        "family": "hyperliquid_funding",
        "n_observations": 0,
        "span_start": None,
        "span_end": None,
        "step_seconds": 3600,
        "n_missing_steps": None,
    }


def _hl_record(cid, captured_at, coin, hours_ms):
    return {
        "capture_id": cid,
        "captured_at": captured_at,
        "coin": coin,
        "prints": [{"coin": coin, "time_ms": t} for t in hours_ms],
    }


def test_retrospective_coverage_manufactures_no_false_gap_across_day_file_hole(tmp_path):
    """The exact L171 shape: dt=18..21 have NO committed file (a naive day-file
    coverage read sees a 4-day hole) but the embedded prints[].time_ms union,
    written entirely by a catch-up pass on dt=22, is a complete hourly grid with
    zero missing steps."""
    hour_ms = 3600 * 1000
    base = 1784448000000  # 2026-07-19T00:00:00Z, arbitrary anchor
    pre_gap = [base - 2 * hour_ms, base - hour_ms]  # dt=07-17-ish
    catch_up = [base + i * hour_ms for i in range(0, 5)]  # backfills 07-18..22 in one record
    _write_lines(tmp_path, "hyperliquid_funding", "2026-07-17",
                 [_hl_record("a", "2026-07-17T06:20:03+00:00", "BTC", pre_gap)])
    # dt=18, dt=19, dt=20, dt=21: deliberately NO files written (the freeze window).
    _write_lines(tmp_path, "hyperliquid_funding", "2026-07-22",
                 [_hl_record("b", "2026-07-22T02:43:22+00:00", "BTC", catch_up)])

    cov = tgm.retrospective_coverage(tmp_path, "hyperliquid_funding")
    assert cov["n_observations"] == len(set(pre_gap + catch_up)) == 7
    assert cov["n_missing_steps"] == 0, cov
    assert cov["span_start"] == datetime.fromtimestamp(
        min(pre_gap) / 1000.0, tz=UTC).isoformat()
    assert cov["span_end"] == datetime.fromtimestamp(
        max(catch_up) / 1000.0, tz=UTC).isoformat()

    # And the naive "day-file presence" read a human/future tool might reach for
    # WOULD have seen a gap — proving this function is not a no-op relative to it.
    present_days = {p.name for p in (tmp_path / "hyperliquid_funding").iterdir()}
    assert "dt=2026-07-18.jsonl" not in present_days
    assert "dt=2026-07-21.jsonl" not in present_days


def test_retrospective_coverage_detects_a_real_gap(tmp_path):
    hour_ms = 3600 * 1000
    base = 1784448000000
    # A genuine hole: hours 0,1,2 then a jump to hour 5 (3,4 missing for real).
    hours = [base, base + hour_ms, base + 2 * hour_ms, base + 5 * hour_ms]
    _write_lines(tmp_path, "hyperliquid_funding", "2026-07-17",
                 [_hl_record("a", "2026-07-17T06:20:03+00:00", "BTC", hours)])
    cov = tgm.retrospective_coverage(tmp_path, "hyperliquid_funding")
    assert cov["n_observations"] == 4
    assert cov["n_missing_steps"] == 2, cov


def test_retrospective_coverage_skips_malformed_items_never_fabricates(tmp_path):
    rec = {
        "capture_id": "a", "captured_at": "2026-07-17T06:20:03+00:00", "coin": "BTC",
        "prints": [{"coin": "BTC", "time_ms": 1784448000000},
                   {"coin": "BTC"},                      # missing time_ms
                   {"coin": "BTC", "time_ms": "bad"},     # wrong type
                   {"coin": "BTC", "time_ms": True},      # bool must not count as int
                   "not-a-dict"],
    }
    _write_lines(tmp_path, "hyperliquid_funding", "2026-07-17", [rec])
    cov = tgm.retrospective_coverage(tmp_path, "hyperliquid_funding")
    assert cov["n_observations"] == 1, cov


def test_evaluate_family_attaches_retrospective_coverage_when_tape_root_given(tmp_path):
    hour_ms = 3600 * 1000
    base = 1784448000000
    hours = [base, base + hour_ms]
    _write_lines(tmp_path, "hyperliquid_funding", "2026-07-17",
                 [_hl_record("a", "2026-07-17T06:20:03+00:00", "BTC", hours)])
    now = _dt(2026, 7, 17, 7, 0)
    agg = tgm.aggregate_family(tmp_path, "hyperliquid_funding", now)
    r = tgm.evaluate_family(agg, now, tape_root=tmp_path)
    assert r["retrospective_coverage"]["n_observations"] == 2
    assert r["retrospective_coverage"]["n_missing_steps"] == 0

    # Without tape_root, the field is present but None — never fabricated.
    r_no_root = tgm.evaluate_family(agg, now)
    assert r_no_root["retrospective_coverage"] is None

    # A family NOT in RETROSPECTIVE_LIST_FAMILIES stays None even WITH tape_root.
    _hourly_day(tmp_path, "crypto_hourly", "2026-07-17", [6])
    agg2 = tgm.aggregate_family(tmp_path, "crypto_hourly", now)
    r2 = tgm.evaluate_family(agg2, now, tape_root=tmp_path)
    assert r2["retrospective_coverage"] is None


@_real
def test_acceptance_11_l171_hyperliquid_funding_real_tape_zero_missing_steps():
    """HARD acceptance, real committed tape: hyperliquid_funding's dt=2026-07-18
    .. dt=2026-07-21 files are genuinely absent (the L127 VPS-freeze window) —
    a naive day-file coverage read sees a 4-day hole — but retrospective_coverage's
    embedded-time_ms union has zero missing hourly steps, matching
    findings/2026-07-26-hyperliquid-funding-tape-audit.md's finding exactly."""
    fam_dir = _REAL_TAPE / "hyperliquid_funding"
    present = {p.name for p in fam_dir.iterdir() if p.is_file()}
    for gap_day in ("dt=2026-07-18.jsonl", "dt=2026-07-19.jsonl",
                    "dt=2026-07-20.jsonl", "dt=2026-07-21.jsonl"):
        assert gap_day not in present, \
            f"{gap_day} now exists — L171's worked example day-file hole has closed; " \
            "this test's premise (file presence looks like a gap) needs re-verifying, " \
            "not just re-pinning the missing-steps assertion below."
    cov = tgm.retrospective_coverage(_REAL_TAPE, "hyperliquid_funding")
    assert cov["n_observations"] > 1000, cov
    assert cov["n_missing_steps"] == 0, cov


# --------------------------------------------------------------------------- #
# Capped-pagination span-vs-cadence coverage (L185, 2026-07-27)
# --------------------------------------------------------------------------- #
def _sl_record(cid, close_time, ticker="KX-A", source="live_settled_markets"):
    """A minimal settlement_ledger.v1-shaped row (only the fields the check reads)."""
    return {
        "capture_id": cid,
        "captured_at": "2026-07-22T10:31:41.942809+00:00",
        "close_time": close_time,
        "ticker": ticker,
        "source": source,
        "price_source_tag": "broker_truth",
        "schema_version": "settlement_ledger.v1",
    }


def _sl_capture(cid, start: datetime, span_hours: float, n_rows: int, **kw):
    """n_rows rows whose close_time is spread evenly over span_hours, bare-Z formatted
    exactly like committed tape (`2026-07-22T10:30:00Z`)."""
    out = []
    for i in range(n_rows):
        frac = 0.0 if n_rows == 1 else i / (n_rows - 1)
        ts = start + timedelta(hours=span_hours * frac)
        out.append(_sl_record(cid, ts.strftime("%Y-%m-%dT%H:%M:%SZ"), **kw))
    return out


def test_capped_pagination_unregistered_family_returns_none_L185(tmp_path):
    _hourly_day(tmp_path, "crypto_hourly", "2026-07-15", [10])
    assert tgm.capped_pagination_span_coverage(tmp_path, "crypto_hourly") is None


def test_capped_pagination_no_tape_at_all_makes_no_claim_L185(tmp_path):
    cov = tgm.capped_pagination_span_coverage(tmp_path, "settlement_ledger")
    assert cov["n_captures"] == 0
    assert cov["n_captures_judged"] == 0
    assert cov["n_captures_narrow"] == 0
    assert cov["captures"] == []


def test_capped_pagination_narrow_span_vs_cadence_is_flagged_L185(tmp_path):
    """The exact L185 shape: a 5000-row daily pass whose close_time span is ~3.25h
    against a 24h firing interval — every cadence detector reads green, but only
    ~13.5% of the day's settlements can possibly be in it."""
    _write_lines(tmp_path, "settlement_ledger", "2026-07-22",
                 _sl_capture("c_narrow", _dt(2026, 7, 22, 7, 15), 3.25, 500))
    cov = tgm.capped_pagination_span_coverage(tmp_path, "settlement_ledger")
    assert cov["n_captures"] == 1
    assert cov["n_captures_judged"] == 1
    assert cov["n_captures_not_judged"] == 0
    assert cov["n_captures_narrow"] == 1
    rec = cov["narrow_captures"][0]
    assert rec["capture_id"] == "c_narrow"
    assert rec["n_rows_with_time"] == 500
    assert abs(rec["span_hours"] - 3.25) < 1e-6
    assert abs(rec["span_ratio"] - 3.25 / 24.0) < 1e-6
    assert rec["coverage_ceiling_fraction"] == rec["span_ratio"]
    assert abs(rec["rows_per_hour"] - 500 / 3.25) < 0.05
    assert rec["not_judged_reason"] is None


def test_capped_pagination_wide_span_is_not_flagged_L185(tmp_path):
    """A capture whose span EXCEEDS the firing interval (the migrated legacy-backfill
    shape) is judged and explicitly NOT narrow — the asymmetry that proves the check
    measures span, not merely row count."""
    _write_lines(tmp_path, "settlement_ledger", "2026-07-17",
                 _sl_capture("c_wide", _dt(2026, 7, 7, 1, 39), 24 * 8, 300,
                             source="migrated:q26_settlement_cache"))
    # And one sitting just above the threshold (0.5 * 24h = 12h) — boundary, still ok.
    _write_lines(tmp_path, "settlement_ledger", "2026-07-18",
                 _sl_capture("c_boundary", _dt(2026, 7, 18, 0, 0), 13.0, 300))
    cov = tgm.capped_pagination_span_coverage(tmp_path, "settlement_ledger")
    assert cov["n_captures_judged"] == 2
    assert cov["n_captures_narrow"] == 0, cov["narrow_captures"]
    wide = [c for c in cov["captures"] if c["capture_id"] == "c_wide"][0]
    assert wide["judged"] is True and wide["narrow"] is False
    assert wide["span_ratio"] > 1.0


def test_capped_pagination_thin_capture_is_not_judged_never_flagged_L185(tmp_path):
    """A capture below `min_rows_for_span` has a narrow span for legitimate reasons.
    It must be reported as NOT-JUDGED — never flagged, never folded into 'ok'."""
    _write_lines(tmp_path, "settlement_ledger", "2026-07-23",
                 _sl_capture("c_thin", _dt(2026, 7, 23, 9, 0), 0.05, 3))
    cov = tgm.capped_pagination_span_coverage(tmp_path, "settlement_ledger")
    assert cov["n_captures"] == 1
    assert cov["n_captures_judged"] == 0
    assert cov["n_captures_not_judged"] == 1
    assert cov["n_captures_narrow"] == 0
    rec = cov["captures"][0]
    assert rec["judged"] is False and rec["narrow"] is False
    assert rec["not_judged_reason"] == "below_min_rows_for_span"
    # The span is still reported (informational), but no ratio/ceiling claim is made.
    assert rec["span_ratio"] is None and rec["coverage_ceiling_fraction"] is None


def test_capped_pagination_malformed_times_are_skipped_not_fabricated_L185(tmp_path):
    """Missing/malformed close_time rows are skipped rather than invented, and the
    resulting under-count is visible in n_rows vs n_rows_with_time. A capture with NO
    parseable time at all is NOT-JUDGED, never silently 'ok'."""
    rows = _sl_capture("c_mixed", _dt(2026, 7, 24, 8, 0), 2.0, 60)
    rows.append(_sl_record("c_mixed", None))
    rows.append(_sl_record("c_mixed", "not-a-timestamp"))
    rows.append({"capture_id": "c_mixed", "ticker": "KX-Z"})  # close_time absent entirely
    rows.append({"close_time": "2026-07-24T08:00:00Z"})       # no capture_id -> unattributable
    rows.extend([_sl_record("c_blind", "garbage") for _ in range(80)])
    _write_lines(tmp_path, "settlement_ledger", "2026-07-24", rows)
    # A non-JSON line in the file must not kill the scan either.
    with open(tmp_path / "settlement_ledger" / "dt=2026-07-24.jsonl", "a",
              encoding="utf-8") as f:
        f.write("{not json\n")

    cov = tgm.capped_pagination_span_coverage(tmp_path, "settlement_ledger")
    by_id = {c["capture_id"]: c for c in cov["captures"]}
    assert set(by_id) == {"c_mixed", "c_blind"}
    assert by_id["c_mixed"]["n_rows"] == 63
    assert by_id["c_mixed"]["n_rows_with_time"] == 60
    assert by_id["c_mixed"]["judged"] is True
    assert by_id["c_blind"]["n_rows"] == 80
    assert by_id["c_blind"]["n_rows_with_time"] == 0
    assert by_id["c_blind"]["judged"] is False
    assert by_id["c_blind"]["not_judged_reason"] == "no_parseable_event_times"
    assert by_id["c_blind"]["span_hours"] is None
    assert cov["n_captures_not_judged"] == 1
    assert cov["n_captures_narrow"] == 1  # c_mixed only


def test_capped_pagination_zero_span_rows_per_hour_is_none_not_infinity_L185(tmp_path):
    """All rows sharing one instant: genuinely maximally narrow, but the observed
    event rate is UNDEFINED — reported as None, never an invented infinity."""
    _write_lines(tmp_path, "settlement_ledger", "2026-07-25",
                 [_sl_record("c_zero", "2026-07-25T10:00:00Z") for _ in range(100)])
    cov = tgm.capped_pagination_span_coverage(tmp_path, "settlement_ledger")
    rec = cov["captures"][0]
    assert rec["judged"] is True and rec["narrow"] is True
    assert rec["span_hours"] == 0.0
    assert rec["rows_per_hour"] is None


def test_evaluate_family_attaches_capped_pagination_span_when_tape_root_given_L185(tmp_path):
    _write_lines(tmp_path, "settlement_ledger", "2026-07-22",
                 _sl_capture("c_narrow", _dt(2026, 7, 22, 7, 15), 3.25, 200))
    now = _dt(2026, 7, 22, 11, 0)
    agg = tgm.aggregate_family(tmp_path, "settlement_ledger", now)
    r = tgm.evaluate_family(agg, now, tape_root=tmp_path)
    assert r["capped_pagination_span"]["n_captures_narrow"] == 1

    # Without tape_root the field is present but None — never fabricated.
    assert tgm.evaluate_family(agg, now)["capped_pagination_span"] is None

    # A family NOT in CAPPED_PAGINATION_FAMILIES stays None even WITH tape_root.
    _hourly_day(tmp_path, "crypto_hourly", "2026-07-22", [6])
    agg2 = tgm.aggregate_family(tmp_path, "crypto_hourly", now)
    assert tgm.evaluate_family(agg2, now, tape_root=tmp_path)["capped_pagination_span"] is None


def test_capped_pagination_span_never_touches_the_alert_path_L185(tmp_path):
    """The check is INFORMATIONAL: a family with 100% narrow captures whose collector
    is otherwise healthy must still report alert=False / alert_reason='ok'."""
    _write_lines(tmp_path, "settlement_ledger", "2026-07-22",
                 _sl_capture("c_narrow", _dt(2026, 7, 22, 7, 15), 3.25, 200))
    now = _dt(2026, 7, 22, 11, 0)
    agg = tgm.aggregate_family(tmp_path, "settlement_ledger", now)
    with_root = tgm.evaluate_family(agg, now, tape_root=tmp_path)
    without_root = tgm.evaluate_family(agg, now)
    assert with_root["capped_pagination_span"]["n_captures_narrow"] == 1
    assert with_root["alert"] is False
    assert with_root["alert_reason"] == "ok"
    # Byte-for-byte identical alert path with and without the new computation.
    for key in ("alert", "alert_reason", "age_hours", "missed_passes_estimate",
                "capture_ratio", "passes_in_window"):
        assert with_root[key] == without_root[key]


@_real
def test_acceptance_12_l185_settlement_ledger_real_tape_span_vs_cadence():
    """HARD acceptance, real committed tape: settlement_ledger's 4 committed captures.
    The 3 live `live_settled_markets` harvests each span 1-4h of close_time against a
    24h firing interval (ratio < 0.2) and are flagged narrow; the 605-row
    `migrated:q26_settlement_cache` legacy backfill spans ~8 DAYS and is NOT flagged.
    That asymmetry is the self-check that the span, not the row count, is what is
    being measured."""
    cov = tgm.capped_pagination_span_coverage(_REAL_TAPE, "settlement_ledger")
    assert cov is not None
    by_id = {c["capture_id"]: c for c in cov["captures"]}
    expected = {"20260717T122238Z", "20260717T122243Z",
                "20260717T122302Z", "20260722T103141Z"}
    assert set(by_id) == expected, sorted(by_id)
    assert cov["n_captures"] == 4
    assert cov["n_captures_judged"] == 4
    assert cov["n_captures_not_judged"] == 0
    assert cov["n_captures_narrow"] == 3, cov["narrow_captures"]

    legacy = by_id["20260717T122238Z"]
    assert legacy["n_rows"] == 605
    assert legacy["narrow"] is False, legacy
    assert legacy["span_hours"] > 24.0 * 7, legacy  # ~8.07 days
    assert legacy["span_ratio"] > 1.0, legacy

    for cid, n_rows in (("20260717T122243Z", 800),
                        ("20260717T122302Z", 4200),
                        ("20260722T103141Z", 5000)):
        rec = by_id[cid]
        assert rec["n_rows"] == n_rows, rec
        assert rec["narrow"] is True, rec
        assert 1.0 <= rec["span_hours"] <= 4.0, rec
        assert rec["span_ratio"] < 0.2, rec
        # L185's arithmetic: the observed event rate the 5000-row cap is spent against.
        assert rec["rows_per_hour"] > 500, rec
        assert rec["coverage_ceiling_fraction"] == rec["span_ratio"]


# ─── L210: `capture_id` is a pass LABEL, not a unique join key ──────────────────
#
# Hard assertions live over FIXTURES (the L201/L207 move); the one real-tree test below
# is deliberately STRUCTURAL/conditional so it cannot be broken by ordinary tape growth.


def _cap_row(cid, captured_at, **extra):
    r = {"capture_id": cid, "captured_at": captured_at}
    r.update(extra)
    return r


def test_l210_no_tape_at_all_makes_no_claim(tmp_path):
    assert tgm._collision_candidate_families(tmp_path) == {}
    assert tgm.duplicate_capture_id_collisions(tmp_path, "perp_tape") is None


def test_l210_clean_single_pass_is_not_a_candidate(tmp_path):
    """One invocation, one captured_at, several distinct items — nothing to flag."""
    _write_lines(tmp_path, "perp_tape", "2026-07-17", [
        _cap_row("c1", "2026-07-17T01:00:32.6+00:00", record_type="orderbook", ticker="KXBTCPERP"),
        _cap_row("c1", "2026-07-17T01:00:32.6+00:00", record_type="orderbook", ticker="KXETHPERP"),
    ])
    assert tgm._collision_candidate_families(tmp_path) == {}
    assert tgm.duplicate_capture_id_collisions(tmp_path, "perp_tape") is None


def test_l210_two_invocations_in_one_second_are_flagged(tmp_path):
    """L210's exact shape: a `--backfill-funding` one-shot landing in the same wall-clock
    second as a scheduled pass. Same capture_id, same logical item (funding_rates), two
    genuinely different payloads — distinguishable only by `mode`."""
    _write_lines(tmp_path, "perp_tape", "2026-07-17", [
        _cap_row("20260717T010032Z", "2026-07-17T01:00:32.634200+00:00",
                 record_type="funding_rates", venue="kalshi_perps", mode="backfill",
                 n_prints=1447, start_ts=1780012800),
        _cap_row("20260717T010032Z", "2026-07-17T01:00:32.886118+00:00",
                 record_type="funding_rates", venue="kalshi_perps", mode="recent",
                 n_prints=39, start_ts=1784163632),
    ])
    res = tgm.duplicate_capture_id_collisions(tmp_path, "perp_tape")
    assert res["n_collisions"] == 1
    assert res["exempt_reason"] is None
    col = res["collisions"][0]
    assert col["capture_id"] == "20260717T010032Z"
    assert col["n_distinct_captured_at"] == 2
    # `mode` is the evidence that these were two invocations, not one retried write.
    assert "mode" in col["differing_fields"]
    assert sorted(col["differing_fields"]["mode"]) == ["backfill", "recent"]


def test_l210_ladder_walk_within_one_pass_is_not_flagged(tmp_path):
    """THE false-positive guard. One pass walking a 5-strike ladder stamps 5 different
    `captured_at` under ONE capture_id. That is a single round, not a collision, and a
    naive "one capture_id must have one captured_at" rule would wrongly flag it. No item
    repeats, so the item-identity rule reads it clean WITHOUT needing the exemption."""
    _write_lines(tmp_path, "weather_books", "2026-07-16", [
        _cap_row("20260716T202839Z", f"2026-07-16T20:28:39.{i}00000+00:00",
                 ticker=f"KXTEMPNYCH-26JUL1617-T8{i}.99")
        for i in range(1, 6)
    ])
    # It IS a prefilter candidate (5 distinct captured_at)...
    assert "weather_books" in tgm._collision_candidate_families(tmp_path)
    # ...and the authoritative pass correctly clears it.
    res = tgm.duplicate_capture_id_collisions(tmp_path, "weather_books")
    assert res["n_collisions"] == 0
    assert res["collisions"] == []


def test_l210_within_pass_sequence_field_structurally_exempts(tmp_path):
    """A family that stamps its own within-pass ordering declares that several captured_at
    per capture_id are BY DESIGN. The exemption is keyed on the SCHEMA FIELD, not on a
    family name-list, so a new burst collector inherits it with no edit to the detector."""
    for field in tgm.WITHIN_PASS_SEQUENCE_FIELDS:
        root = tmp_path / field
        _write_lines(root, "hf_burst", "2026-07-16", [
            _cap_row("b1", "2026-07-16T20:28:39.3+00:00", ticker="KX-A", **{field: 0}),
            # Same ticker twice — would collide but for the declared sequence.
            _cap_row("b1", "2026-07-16T20:28:39.5+00:00", ticker="KX-A", **{field: 1}),
        ])
        res = tgm.duplicate_capture_id_collisions(root, "hf_burst")
        assert res["exempt_reason"] == "declares_within_pass_sequence", field
        assert res["n_collisions"] == 0, field


def test_l210_pass_summary_row_with_no_item_fields_still_collides(tmp_path):
    """The `anomalies` shape: one summary row per pass carrying no item-identity field at
    all. Two such rows under one capture_id are two passes — the empty item key is the
    correct identity here, not a reason to abstain."""
    payload = dict(n_anomalies=324, n_markets_scanned=20000, completeness_ok=True)
    _write_lines(tmp_path, "anomalies", "2026-07-14", [
        _cap_row("20260714T091958Z", "2026-07-14T09:19:58.634583+00:00", **payload),
        _cap_row("20260714T091958Z", "2026-07-14T09:19:58.718011+00:00", **payload),
    ])
    res = tgm.duplicate_capture_id_collisions(tmp_path, "anomalies")
    assert res["n_collisions"] == 1
    col = res["collisions"][0]
    assert col["item_key"] == []
    # Byte-identical payloads: nothing differs, which is itself the honest report.
    assert col["differing_fields"] == {}


def test_l210_malformed_and_keyless_lines_are_skipped_never_fabricated(tmp_path):
    fam = tmp_path / "perp_tape"
    fam.mkdir(parents=True)
    with open(fam / "dt=2026-07-17.jsonl", "w", encoding="utf-8") as f:
        f.write("{not json\n")
        f.write("\n")
        f.write(json.dumps([1, 2, 3]) + "\n")                      # not a dict
        f.write(json.dumps({"captured_at": "2026-07-17T01:00:00+00:00"}) + "\n")  # no cid
        f.write(json.dumps({"capture_id": "c1"}) + "\n")           # no captured_at
    assert tgm._collision_candidate_families(tmp_path) == {}
    assert tgm.duplicate_capture_id_collisions(tmp_path, "perp_tape") is None


def test_l210_prefilter_never_under_nominates_relative_to_json_parse(tmp_path):
    """Soundness of the cheap regex prefilter: it may over-nominate (harmless — the
    authoritative pass re-checks) but must NEVER miss a family that an honest top-level
    `json.loads` read would nominate. Includes a NESTED captured_at, the one shape where a
    regex could in principle disagree with a top-level read."""
    _write_lines(tmp_path, "perp_tape", "2026-07-17", [
        _cap_row("c1", "2026-07-17T01:00:32.6+00:00", record_type="funding_rates"),
        _cap_row("c1", "2026-07-17T01:00:32.8+00:00", record_type="funding_rates"),
    ])
    _write_lines(tmp_path, "crypto_hourly", "2026-07-17", [
        _cap_row("c2", "2026-07-17T02:00:00.1+00:00", ticker="KXBTC",
                 current={"captured_at": "2026-07-17T02:00:00.9+00:00"}),
    ])
    regex_cands = tgm._collision_candidate_families(tmp_path)

    json_cands = {}
    for fam_dir in sorted(p for p in tmp_path.iterdir() if p.is_dir()):
        seen = {}
        for _d, path in tgm._family_files(tmp_path, fam_dir.name):
            for line in open(path, encoding="utf-8"):
                if not line.strip():
                    continue
                rec = json.loads(line)
                cid, cap = rec.get("capture_id"), rec.get("captured_at")
                if isinstance(cid, str) and isinstance(cap, str):
                    seen.setdefault(cid, set()).add(cap)
        hits = sorted(c for c, v in seen.items() if len(v) > 1)
        if hits:
            json_cands[fam_dir.name] = hits

    for fam, ids in json_cands.items():
        assert fam in regex_cands, f"prefilter under-nominated {fam}"
        assert set(ids) <= set(regex_cands[fam]), f"prefilter under-nominated ids in {fam}"


def test_acceptance_13_l210_real_tape_capture_id_collisions_are_reported():
    """Real committed tape, read-only. STRUCTURAL/conditional by design (L192/L207): it
    asserts the detector's CONTRACT holds over the live tree, never a pinned count that
    ordinary tape growth would break."""
    root = _MOD_PATH.resolve().parent.parent / "tape"
    if not root.is_dir():
        pytest.skip("no committed tape in this checkout")
    cands = tgm._collision_candidate_families(root)
    for family, ids in cands.items():
        res = tgm.duplicate_capture_id_collisions(root, family, ids)
        assert res is not None
        assert set(res) >= {"family", "n_collisions", "collisions", "exempt_reason"}
        assert res["n_collisions"] == len(res["collisions"])
        for col in res["collisions"]:
            # A reported collision always carries its evidence: >=2 real timestamps.
            assert col["n_distinct_captured_at"] >= 2
            assert len(col["captured_at_values"]) == col["n_distinct_captured_at"]
        # A family that declares its own within-pass sequence must never be flagged.
        if res["exempt_reason"] == "declares_within_pass_sequence":
            assert res["n_collisions"] == 0


# --------------------------------------------------------------------------- #
# L208 — expected-window-grid coverage (survivorship vs coverage denominator)
# --------------------------------------------------------------------------- #
# The unit tests below build fixture tape under tmp_path. The one REAL-TAPE
# acceptance test pins a FROZEN day slice (L191): `tape/perp_tape/` is a live,
# still-growing family, so an open-ended `dt=*` read would red-line main's gate on
# ordinary capture with zero code change.

def _fe(cid, captured_at, next_funding_time, ticker="KXBTCPERP", **extra):
    """One `funding_estimate` row shaped exactly like committed perp_tape."""
    rec = {
        "capture_id": cid,
        "captured_at": captured_at,
        "record_type": "funding_estimate",
        "next_funding_time": next_funding_time,
        "ticker": ticker,
        "funding_rate_estimate": 0.0,
        "price_source_tag": "broker_truth",
        "schema_version": "perp_tape.v1",
        "venue": "kalshi_perps",
    }
    rec.update(extra)
    return rec


def test_window_grid_unregistered_family_returns_none_L208(tmp_path):
    """Same refusal as capped_pagination/retrospective_coverage: no claim about a
    shape the function wasn't told the family has."""
    _hourly_day(tmp_path, "crypto_hourly", "2026-07-15", [10])
    assert tgm.expected_window_grid_coverage(tmp_path, "crypto_hourly") is None


def test_window_grid_no_tape_makes_no_claim_L208(tmp_path):
    cov = tgm.expected_window_grid_coverage(tmp_path, "perp_tape")
    assert cov["reason"] == "no_on_grid_window_keys"
    assert cov["n_windows_expected"] == 0
    assert cov["coverage_fraction"] is None
    assert cov["grid_start"] is None and cov["grid_end"] is None


def test_window_grid_zero_capture_window_is_found_L208(tmp_path):
    """The L208 shape: three consecutive 8h funding windows, the MIDDLE one never
    captured. An observed-windows-only statistic sees 2 windows and reads healthy;
    the grid denominator sees 3 and names the hole."""
    _write_lines(tmp_path, "perp_tape", "2026-07-20", [
        _fe("c1", "2026-07-20T01:00:00+00:00", "2026-07-20T04:00:00Z"),
        _fe("c2", "2026-07-20T02:00:00+00:00", "2026-07-20T04:00:00Z"),
        # nothing at all for the 12:00Z window
        _fe("c3", "2026-07-20T17:00:00+00:00", "2026-07-20T20:00:00Z"),
    ])
    cov = tgm.expected_window_grid_coverage(tmp_path, "perp_tape")
    assert cov["n_windows_expected"] == 3
    assert cov["n_windows_observed"] == 2
    assert cov["n_windows_zero_capture"] == 1
    assert cov["zero_capture_windows"] == ["2026-07-20T12:00:00+00:00"]
    assert cov["coverage_fraction"] == round(2 / 3, 6)


def test_window_grid_reports_both_survivorship_and_honest_denominator_L208(tmp_path):
    """Both statistics are reported side by side — the whole point of L208 is that
    the observed-only number is not WRONG, it answers a different question."""
    _write_lines(tmp_path, "perp_tape", "2026-07-20", [
        _fe("c1", "2026-07-20T01:00:00+00:00", "2026-07-20T04:00:00Z"),
        _fe("c2", "2026-07-20T02:00:00+00:00", "2026-07-20T04:00:00Z"),
        _fe("c3", "2026-07-20T03:00:00+00:00", "2026-07-20T04:00:00Z"),
        _fe("c4", "2026-07-20T17:00:00+00:00", "2026-07-20T20:00:00Z"),
    ])
    cov = tgm.expected_window_grid_coverage(tmp_path, "perp_tape")
    # observed-only never sees the empty 12:00Z window; grid-filled does.
    assert cov["observed_only"]["min_passes"] == 1
    assert cov["grid_filled"]["min_passes"] == 0
    assert cov["observed_only"]["median_passes"] == 2.0     # median(3, 1)
    assert cov["grid_filled"]["median_passes"] == 1         # median(3, 0, 1)
    assert cov["survivorship_gap_median"] == 1.0


def test_window_grid_thin_includes_zero_windows_L208(tmp_path):
    """A zero-pass window is the EXTREME thin window; `n_windows_thin` must include
    it, or the path-inadequacy fraction under-reports exactly where it matters."""
    _write_lines(tmp_path, "perp_tape", "2026-07-20", [
        _fe("c1", "2026-07-20T01:00:00+00:00", "2026-07-20T04:00:00Z"),
        _fe("c3", "2026-07-20T17:00:00+00:00", "2026-07-20T20:00:00Z"),
        _fe("c4", "2026-07-20T18:00:00+00:00", "2026-07-20T20:00:00Z"),
    ])
    cov = tgm.expected_window_grid_coverage(tmp_path, "perp_tape")
    # windows: 04Z=1 pass (thin), 12Z=0 (thin, zero), 20Z=2 passes (ok)
    assert cov["n_windows_thin"] == 2
    assert cov["n_windows_zero_capture"] == 1
    assert cov["path_inadequate_fraction"] == round(2 / 3, 6)


def test_window_grid_offgrid_key_is_reported_never_snapped_L208(tmp_path):
    """The load-bearing rule. A boundary off the configured (width, anchor) grid means
    the venue's cadence changed — report it, never round it into a neighbouring slot."""
    _write_lines(tmp_path, "perp_tape", "2026-07-20", [
        _fe("c1", "2026-07-20T01:00:00+00:00", "2026-07-20T04:00:00Z"),
        _fe("c_bad", "2026-07-20T07:00:00+00:00", "2026-07-20T08:00:00Z"),   # 00Z-anchored
        _fe("c2", "2026-07-20T17:00:00+00:00", "2026-07-20T20:00:00Z"),
    ])
    cov = tgm.expected_window_grid_coverage(tmp_path, "perp_tape")
    assert cov["n_offgrid_window_keys"] == 1
    assert cov["offgrid_examples"] == ["2026-07-20T08:00:00+00:00"]
    # The off-grid row did NOT get snapped into 04Z or 12Z: 12Z is still empty.
    assert cov["zero_capture_windows"] == ["2026-07-20T12:00:00+00:00"]
    assert cov["n_windows_expected"] == 3


def test_window_grid_unparseable_key_is_skipped_and_counted_L208(tmp_path):
    _write_lines(tmp_path, "perp_tape", "2026-07-20", [
        _fe("c1", "2026-07-20T01:00:00+00:00", "2026-07-20T04:00:00Z"),
        _fe("c_none", "2026-07-20T05:00:00+00:00", None),
        _fe("c_junk", "2026-07-20T06:00:00+00:00", "not-a-timestamp"),
    ])
    cov = tgm.expected_window_grid_coverage(tmp_path, "perp_tape")
    assert cov["n_rows_considered"] == 3
    assert cov["n_rows_skipped_no_window_key"] == 2
    assert cov["n_windows_expected"] == 1


def test_window_grid_ignores_other_record_types_L208(tmp_path):
    """`perp_tape` multiplexes record_types on one family; only the configured one
    carries a funding boundary."""
    _write_lines(tmp_path, "perp_tape", "2026-07-20", [
        _fe("c1", "2026-07-20T01:00:00+00:00", "2026-07-20T04:00:00Z"),
        _pass("c1", "2026-07-20T01:00:00+00:00", record_type="orderbook",
              next_funding_time="2026-07-20T12:00:00Z"),
    ])
    cov = tgm.expected_window_grid_coverage(tmp_path, "perp_tape")
    assert cov["n_rows_considered"] == 1
    assert cov["n_windows_expected"] == 1


def test_window_grid_density_unit_is_the_distinct_pass_L208(tmp_path):
    """13 tickers in ONE pass is one pass, not 13 samples — otherwise a single
    fat pass masquerades as a dense path."""
    rows = [_fe("c1", "2026-07-20T01:00:00+00:00", "2026-07-20T04:00:00Z",
                ticker=f"KX{i}PERP") for i in range(13)]
    _write_lines(tmp_path, "perp_tape", "2026-07-20", rows)
    cov = tgm.expected_window_grid_coverage(tmp_path, "perp_tape")
    assert cov["observed_only"]["max_passes"] == 1


def test_window_grid_missing_capture_id_never_reads_as_empty_L208(tmp_path):
    """A row with no capture_id cannot be attributed to a pass, but it PROVES the
    window was observed — it must never make the window read as a zero-pass hole."""
    _write_lines(tmp_path, "perp_tape", "2026-07-20", [
        {"record_type": "funding_estimate", "next_funding_time": "2026-07-20T04:00:00Z",
         "captured_at": "2026-07-20T01:00:00+00:00"},
    ])
    cov = tgm.expected_window_grid_coverage(tmp_path, "perp_tape")
    assert cov["n_windows_zero_capture"] == 0
    assert cov["n_windows_observed"] == 1


def test_window_grid_days_slice_restricts_the_scan_L208(tmp_path):
    """The L191 pin: `days=` freezes the population so a live family's ordinary
    growth cannot move a pinned number."""
    _write_lines(tmp_path, "perp_tape", "2026-07-20",
                 [_fe("c1", "2026-07-20T01:00:00+00:00", "2026-07-20T04:00:00Z")])
    _write_lines(tmp_path, "perp_tape", "2026-07-21",
                 [_fe("c2", "2026-07-21T01:00:00+00:00", "2026-07-21T04:00:00Z")])
    full = tgm.expected_window_grid_coverage(tmp_path, "perp_tape")
    pinned = tgm.expected_window_grid_coverage(tmp_path, "perp_tape",
                                              days=["dt=2026-07-20"])
    assert full["n_windows_expected"] == 4      # 07-20T04 .. 07-21T04, 8h apart
    assert pinned["n_windows_expected"] == 1
    assert pinned["days_scanned"] == ["dt=2026-07-20"]


def test_window_grid_on_grid_helper_is_exact_L208():
    assert tgm._on_grid(_dt(2026, 7, 20, 4), 8.0, 4) is True
    assert tgm._on_grid(_dt(2026, 7, 20, 12), 8.0, 4) is True
    assert tgm._on_grid(_dt(2026, 7, 20, 20), 8.0, 4) is True
    assert tgm._on_grid(_dt(2026, 7, 20, 8), 8.0, 4) is False
    assert tgm._on_grid(_dt(2026, 7, 20, 4, 1), 8.0, 4) is False
    assert tgm._on_grid(_dt(2026, 7, 20, 4), 0.0, 4) is False


@_real
def test_acceptance_9_l208_perp_tape_funding_grid_frozen_slice():
    """HARD real-tape acceptance, FROZEN to dt=2026-07-17..2026-07-27 (L191).

    This is the exact tape `findings/2026-07-27-perp-tape-audit.md` PERP-F1 audited.
    Read on the collector's OWN funding boundary (`next_funding_time`, a 04/12/20Z
    grid), it has THREE zero-pass windows — a different set from the FOUR the audit
    reported off 00Z-anchored `captured_at` calendar bins. Both facts are pinned so a
    future re-anchoring cannot silently change the answer."""
    days = [f"dt=2026-07-{d:02d}" for d in range(17, 28)]
    cov = tgm.expected_window_grid_coverage(_REAL_TAPE, "perp_tape", days=days)
    assert cov is not None
    assert cov["window_key"] == "next_funding_time"
    assert cov["window_hours"] == 8.0 and cov["anchor_hour_utc"] == 4
    # Every committed boundary in the slice is on the 04/12/20Z grid — none on 00/08/16.
    assert cov["n_offgrid_window_keys"] == 0
    assert cov["n_rows_skipped_no_window_key"] == 0
    assert cov["n_windows_expected"] == 34
    assert cov["n_windows_observed"] == 31
    assert cov["n_windows_zero_capture"] == 3
    assert cov["zero_capture_windows"] == [
        "2026-07-24T04:00:00+00:00",
        "2026-07-25T04:00:00+00:00",
        "2026-07-25T20:00:00+00:00",
    ]
    # The audit's four 00Z-anchored bins (07-23T08Z/07-24T08Z/07-25T08Z/07-25T16Z) are
    # not funding boundaries at all: not one of them appears on this grid.
    audit_bins = {"2026-07-23T08:00:00+00:00", "2026-07-24T08:00:00+00:00",
                  "2026-07-25T08:00:00+00:00", "2026-07-25T16:00:00+00:00"}
    assert audit_bins.isdisjoint(set(cov["zero_capture_windows"]))
    # And the survivorship point itself: observed-only never sees a 0.
    assert cov["observed_only"]["min_passes"] >= 1
    assert cov["grid_filled"]["min_passes"] == 0


# --------------------------------------------------------------------------- #
# Wall-clock-slot cadence (L213)
# --------------------------------------------------------------------------- #
def test_slot_cadence_counts_only_passes_inside_the_window(tmp_path):
    _write_lines(tmp_path, "polymarket_macro_pairs", "2026-07-20", [
        _pass("c1", "2026-07-20T05:00:00+00:00"),   # outside
        _pass("c2", "2026-07-20T17:45:00+00:00"),   # inside
        _pass("c3", "2026-07-20T18:29:59+00:00"),   # inside (upper edge)
        _pass("c4", "2026-07-20T18:31:00+00:00"),   # outside (just past)
    ])
    out = tgm.slot_cadence_by_time_of_day(tmp_path, "polymarket_macro_pairs", "17:40", "18:30")
    assert out["per_day_pass_count"] == {"dt=2026-07-20": 2}
    assert out["n_days_zero"] == 0
    assert out["all_days_zero"] is False


def test_slot_cadence_bounds_are_inclusive(tmp_path):
    _write_lines(tmp_path, "polymarket_macro_pairs", "2026-07-20", [
        _pass("c1", "2026-07-20T17:40:00+00:00"),   # exact start
        _pass("c2", "2026-07-20T18:30:00+00:00"),   # exact end
    ])
    out = tgm.slot_cadence_by_time_of_day(tmp_path, "polymarket_macro_pairs", "17:40", "18:30")
    assert out["per_day_pass_count"] == {"dt=2026-07-20": 2}


def test_slot_cadence_all_days_zero_is_the_l213_shape(tmp_path):
    """The exact L213 finding shape: dense captures every day, none of them ever
    inside the slot that mattered."""
    for day in ("2026-07-18", "2026-07-19", "2026-07-20"):
        _write_lines(tmp_path, "polymarket_macro_pairs", day, [
            _pass(f"{day}-a", f"{day}T05:00:00+00:00"),
            _pass(f"{day}-b", f"{day}T12:00:00+00:00"),
        ])
    out = tgm.slot_cadence_by_time_of_day(tmp_path, "polymarket_macro_pairs", "17:40", "18:30",
                                          days=["dt=2026-07-18", "dt=2026-07-19", "dt=2026-07-20"])
    assert out["n_days_scanned"] == 3
    assert out["n_days_zero"] == 3
    assert out["all_days_zero"] is True
    assert out["zero_days"] == ["dt=2026-07-18", "dt=2026-07-19", "dt=2026-07-20"]


def test_slot_cadence_missing_day_file_reports_as_zero_not_skipped(tmp_path):
    """A `days=` entry with NO committed file at all is a genuine zero-pass day —
    a burst-fallback risk read must see it, not have it silently vanish."""
    _write_lines(tmp_path, "polymarket_macro_pairs", "2026-07-20", [
        _pass("c1", "2026-07-20T18:00:00+00:00"),
    ])
    out = tgm.slot_cadence_by_time_of_day(tmp_path, "polymarket_macro_pairs", "17:40", "18:30",
                                          days=["dt=2026-07-20", "dt=2026-07-21"])
    assert out["n_days_scanned"] == 2
    assert out["per_day_pass_count"]["dt=2026-07-21"] == 0
    assert out["n_days_zero"] == 1
    assert out["all_days_zero"] is False


def test_slot_cadence_density_unit_is_the_distinct_pass(tmp_path):
    """Two rows sharing one `capture_id` inside the window are ONE pass, not two —
    same density-unit convention as `expected_window_grid_coverage` (L208/L210)."""
    _write_lines(tmp_path, "polymarket_macro_pairs", "2026-07-20", [
        _pass("c1", "2026-07-20T18:00:00+00:00", ticker="A"),
        _pass("c1", "2026-07-20T18:00:00+00:00", ticker="B"),
    ])
    out = tgm.slot_cadence_by_time_of_day(tmp_path, "polymarket_macro_pairs", "17:40", "18:30")
    assert out["per_day_pass_count"] == {"dt=2026-07-20": 1}


def test_slot_cadence_missing_capture_id_never_merges_distinct_rows(tmp_path):
    out_dir_lines = [
        {"captured_at": "2026-07-20T18:00:00.100000+00:00"},
        {"captured_at": "2026-07-20T18:00:00.200000+00:00"},
    ]
    _write_lines(tmp_path, "polymarket_macro_pairs", "2026-07-20", out_dir_lines)
    out = tgm.slot_cadence_by_time_of_day(tmp_path, "polymarket_macro_pairs", "17:40", "18:30")
    assert out["per_day_pass_count"] == {"dt=2026-07-20": 2}


def test_slot_cadence_no_tape_at_all_makes_no_claim(tmp_path):
    out = tgm.slot_cadence_by_time_of_day(tmp_path, "polymarket_macro_pairs", "17:40", "18:30")
    assert out["n_days_scanned"] == 0
    assert out["all_days_zero"] is False   # empty is NOT "all zero" — no days to be zero


def test_slot_cadence_wrapped_window_raises():
    with pytest.raises(ValueError):
        tgm.slot_cadence_by_time_of_day(Path("."), "polymarket_macro_pairs", "23:50", "00:10")


def test_slot_cadence_days_slice_restricts_the_scan(tmp_path):
    _write_lines(tmp_path, "polymarket_macro_pairs", "2026-07-20",
                 [_pass("c1", "2026-07-20T18:00:00+00:00")])
    _write_lines(tmp_path, "polymarket_macro_pairs", "2026-07-21",
                 [_pass("c2", "2026-07-21T18:00:00+00:00")])
    full = tgm.slot_cadence_by_time_of_day(tmp_path, "polymarket_macro_pairs", "17:40", "18:30")
    pinned = tgm.slot_cadence_by_time_of_day(tmp_path, "polymarket_macro_pairs", "17:40", "18:30",
                                             days=["dt=2026-07-20"])
    assert full["n_days_scanned"] == 2
    assert pinned["n_days_scanned"] == 1
    assert pinned["days_scanned"] == ["dt=2026-07-20"]


@_real
def test_acceptance_10_l213_polymarket_macro_pairs_fomc_slot_frozen_slice():
    """HARD real-tape acceptance, FROZEN to dt=2026-07-18..2026-07-27 (L191).

    Reproduces `findings/2026-07-28-polymarket-macro-pairs-tape-audit.md` D3's exact
    claim: the recurring collector landed dozens of passes/day on `polymarket_macro_pairs`
    over these 10 days yet exactly ZERO of them fall inside the 17:40-18:30Z window the
    2026-07-29T18:00Z FOMC statement needed."""
    days = [f"dt=2026-07-{d:02d}" for d in range(18, 28)]
    out = tgm.slot_cadence_by_time_of_day(_REAL_TAPE, "polymarket_macro_pairs",
                                          "17:40", "18:30", days=days)
    assert out["n_days_scanned"] == 10
    assert out["n_days_zero"] == 10
    assert out["all_days_zero"] is True
    assert out["zero_days"] == days
    # And a sanity check that this isn't a family with no tape at all in the slice —
    # the family DOES capture, just never inside this slot.
    assert sum(
        len(list(open(_REAL_TAPE / "polymarket_macro_pairs" / f"{d}.jsonl")))
        for d in days
    ) > 0


# ─── L222 caller-explicability audit ───────────────────────────────────────────
#
# The read-only half of L222: "a tape-quality check asserts each family's realized pass
# count is explicable by its registered callers". The discriminator is CO-OCCURRENCE with
# the caller's OTHER (ungated) legs, so the check flags the dt=2026-07-23 econ_prints
# incident (18 passes, no sibling within 2.3h) while correctly ABSTAINING on the
# dt=2026-07-14 CPI burst (137 passes, all with real concurrent sibling writes).

def _ep(cid, captured_at, **extra):
    """One econ_prints-shaped pass row."""
    return _pass(cid, captured_at, **extra)


def test_pass_instants_groups_a_ladder_walk_into_one_pass_at_its_earliest_stamp(tmp_path):
    # One capture_id stamped across a ladder walk is ONE pass (L210 case (a)), located at
    # its START — not three passes, and not its last row.
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [
        _ep("c1", "2026-07-23T09:00:05+00:00"),
        _ep("c1", "2026-07-23T09:00:01+00:00"),
        _ep("c1", "2026-07-23T09:00:09+00:00"),
    ])
    out = tgm.pass_instants(tmp_path, "econ_prints")
    assert len(out) == 1
    assert out[0] == _dt(2026, 7, 23, 9, 0, 1)


def test_pass_instants_falls_back_to_captured_at_when_no_capture_id(tmp_path):
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [
        {"captured_at": "2026-07-23T09:00:01+00:00"},
        {"captured_at": "2026-07-23T09:30:01+00:00"},
    ])
    assert len(tgm.pass_instants(tmp_path, "econ_prints")) == 2


def test_pass_instants_skips_malformed_and_undated_rows_never_guesses(tmp_path):
    fam = tmp_path / "econ_prints"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-23.jsonl").write_text(
        '{"capture_id": "c1", "captured_at": "2026-07-23T09:00:01+00:00"}\n'
        'not json at all\n'
        '{"capture_id": "c2"}\n'                                   # no timestamp
        '{"capture_id": "c3", "captured_at": "not-a-time"}\n'      # unparseable
        '\n',
        encoding="utf-8",
    )
    assert tgm.pass_instants(tmp_path, "econ_prints") == [_dt(2026, 7, 23, 9, 0, 1)]


def test_pass_instants_days_slice_restricts_the_scan(tmp_path):
    _write_lines(tmp_path, "econ_prints", "2026-07-22", [_ep("a", "2026-07-22T09:00:00+00:00")])
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [_ep("b", "2026-07-23T09:00:00+00:00")])
    assert len(tgm.pass_instants(tmp_path, "econ_prints")) == 2
    assert tgm.pass_instants(tmp_path, "econ_prints", days=["dt=2026-07-23"]) == [
        _dt(2026, 7, 23, 9, 0, 0)]


def test_nearest_gap_s_is_pure_and_none_on_empty():
    others = [_dt(2026, 7, 23, 9, 0, 0), _dt(2026, 7, 23, 12, 0, 0)]
    assert tgm._nearest_gap_s(_dt(2026, 7, 23, 9, 0, 30), others) == 30.0
    assert tgm._nearest_gap_s(_dt(2026, 7, 23, 8, 59, 0), others) == 60.0   # before the first
    assert tgm._nearest_gap_s(_dt(2026, 7, 23, 13, 0, 0), others) == 3600.0  # after the last
    assert tgm._nearest_gap_s(_dt(2026, 7, 23, 9, 0, 0), []) is None


def test_caller_explicability_witnessed_pass_is_explicable(tmp_path):
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [_ep("e1", "2026-07-23T09:00:00+00:00")])
    _write_lines(tmp_path, "sports_pairs", "2026-07-23", [_pass("s1", "2026-07-23T08:55:00+00:00")])
    out = tgm.caller_explicability(tmp_path, "econ_prints")
    assert out["verdict"] == "ALL_EXPLICABLE"
    assert (out["n_passes"], out["n_explained"], out["n_unexplained"]) == (1, 1, 0)
    assert out["explained_by_caller"]["hourly_pass"] == 1
    assert out["unexplained_fraction"] == 0.0


def test_caller_explicability_unwitnessed_pass_is_the_l222_shape(tmp_path):
    # The witness exists, but ~2h away — far outside any real invocation's leg spread.
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [_ep("e1", "2026-07-23T09:00:00+00:00")])
    _write_lines(tmp_path, "sports_pairs", "2026-07-23", [_pass("s1", "2026-07-23T11:00:00+00:00")])
    out = tgm.caller_explicability(tmp_path, "econ_prints")
    assert out["verdict"] == "UNEXPLAINED_PASSES"
    assert (out["n_explained"], out["n_unexplained"]) == (0, 1)
    assert out["unexplained_fraction"] == 1.0
    assert out["per_day_unexplained"] == {"dt=2026-07-23": 1}
    assert out["unexplained_examples"] == ["2026-07-23T09:00:00+00:00"]
    assert out["nearest_witness_gap_s"]["min"] == 7200.0


def test_caller_explicability_tolerance_boundary_is_inclusive(tmp_path):
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [_ep("e1", "2026-07-23T09:15:00+00:00")])
    _write_lines(tmp_path, "sports_pairs", "2026-07-23", [_pass("s1", "2026-07-23T09:00:00+00:00")])
    exact = tgm.caller_explicability(tmp_path, "econ_prints", tolerance_s=900.0)
    tight = tgm.caller_explicability(tmp_path, "econ_prints", tolerance_s=899.0)
    assert exact["verdict"] == "ALL_EXPLICABLE"       # 900s gap, tolerance 900 -> explained
    assert tight["verdict"] == "UNEXPLAINED_PASSES"


def test_caller_explicability_unregistered_family_makes_no_claim(tmp_path):
    _write_lines(tmp_path, "sports_clv", "2026-07-23", [_pass("x1", "2026-07-23T09:00:00+00:00")])
    out = tgm.caller_explicability(tmp_path, "sports_clv")
    assert out["verdict"] == "FAMILY_NOT_REGISTERED"
    assert out["registered_callers"] == []
    # It counted the passes but refuses to call any of them unexplained.
    assert out["n_passes"] == 1
    assert out["n_unexplained"] == 0
    assert out["unexplained_fraction"] is None


def test_caller_explicability_no_passes_is_not_a_clean_bill(tmp_path):
    out = tgm.caller_explicability(tmp_path, "econ_prints")
    assert out["verdict"] == "NO_PASSES"
    assert out["n_passes"] == 0
    assert out["unexplained_fraction"] is None


def test_caller_explicability_absent_witness_tape_is_reported_not_read_as_unexplained(tmp_path):
    # The family fired, but NOT ONE witness family has committed tape in scope. Calling
    # these "unexplained" would be measuring the absence of witness tape, not a defect.
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [
        _ep("e1", "2026-07-23T09:00:00+00:00"),
        _ep("e2", "2026-07-23T09:30:00+00:00"),
    ])
    out = tgm.caller_explicability(tmp_path, "econ_prints")
    assert out["verdict"] == "NO_WITNESS_TAPE"
    assert out["n_witness_passes"] == 0
    assert out["n_unexplained"] == 0
    assert out["unexplained_fraction"] is None


def test_caller_explicability_a_gated_leg_never_witnesses_another_gated_leg(tmp_path):
    # `anomalies` and `econ_prints` are BOTH hour-09-gated legs of hourly_pass. They fire
    # together, so co-occurrence between them is uninformative — a caller that skips the
    # ungated legs skips them for both. Neither may explain the other.
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [_ep("e1", "2026-07-23T09:00:00+00:00")])
    _write_lines(tmp_path, "anomalies", "2026-07-23", [_pass("a1", "2026-07-23T09:00:10+00:00")])
    # An UNGATED leg exists but fires 2h away, so nothing legitimately explains e1. If the
    # 10s-away `anomalies` row were allowed to witness, this would flip to ALL_EXPLICABLE.
    _write_lines(tmp_path, "sports_pairs", "2026-07-23", [_pass("s1", "2026-07-23T11:00:00+00:00")])
    assert "anomalies" not in tgm.HOURLY_PASS_CO_WRITTEN_FAMILIES
    assert "anomalies" in tgm.REGISTERED_CALLER_FAMILIES["hourly_pass"]
    out = tgm.caller_explicability(tmp_path, "econ_prints")
    assert out["verdict"] == "UNEXPLAINED_PASSES"
    assert out["n_unexplained"] == 1
    assert "anomalies" not in out["witness_families"]["hourly_pass"]
    assert out["nearest_witness_gap_s"]["min"] == 7200.0   # sports_pairs, not anomalies@10s


def test_caller_explicability_gated_pair_with_no_ungated_tape_abstains(tmp_path):
    # Same fixture MINUS the ungated leg: with no admissible witness at all the honest
    # answer is NO_WITNESS_TAPE, not "1 unexplained".
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [_ep("e1", "2026-07-23T09:00:00+00:00")])
    _write_lines(tmp_path, "anomalies", "2026-07-23", [_pass("a1", "2026-07-23T09:00:10+00:00")])
    out = tgm.caller_explicability(tmp_path, "econ_prints")
    assert out["verdict"] == "NO_WITNESS_TAPE"
    assert out["n_unexplained"] == 0


def test_caller_explicability_never_witnesses_itself(tmp_path):
    # crypto_hourly is in BOTH caller rosters; auditing it must not let its own rows
    # explain its own passes.
    _write_lines(tmp_path, "crypto_hourly", "2026-07-23", [_pass("c1", "2026-07-23T09:00:00+00:00")])
    out = tgm.caller_explicability(tmp_path, "crypto_hourly")
    for fams in out["witness_families"].values():
        assert "crypto_hourly" not in fams
    assert out["verdict"] == "NO_WITNESS_TAPE"


def test_caller_explicability_concurrent_invocations_proven_below_the_rate_limit_floor(tmp_path):
    # Two pass starts 0.153s apart cannot be one sequential caller (v3_market's ~1.8s floor).
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [
        _ep("e1", "2026-07-23T09:00:00.000000+00:00"),
        _ep("e2", "2026-07-23T09:00:00.153000+00:00"),
    ])
    out = tgm.caller_explicability(tmp_path, "econ_prints")
    assert out["min_consecutive_pass_gap_s"] == 0.153
    assert out["concurrent_invocations_proven"] is True
    assert out["rate_limit_floor_s"] == tgm.PASS_RATE_LIMIT_FLOOR_S


def test_caller_explicability_sequential_passes_do_not_prove_concurrency(tmp_path):
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [
        _ep("e1", "2026-07-23T09:00:00+00:00"),
        _ep("e2", "2026-07-23T09:00:11+00:00"),
    ])
    out = tgm.caller_explicability(tmp_path, "econ_prints")
    assert out["min_consecutive_pass_gap_s"] == 11.0
    assert out["concurrent_invocations_proven"] is False


def test_caller_explicability_reports_passes_near_the_slice_edge(tmp_path):
    # A pass 60s after midnight may look unexplained only because its witness sits in the
    # PREVIOUS day-file, outside the frozen slice. Reported, never silently dropped.
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [
        _ep("e1", "2026-07-23T00:01:00+00:00"),
        _ep("e2", "2026-07-23T12:00:00+00:00"),
    ])
    _write_lines(tmp_path, "sports_pairs", "2026-07-23", [_pass("s1", "2026-07-23T12:00:30+00:00")])
    out = tgm.caller_explicability(tmp_path, "econ_prints", days=["dt=2026-07-23"])
    assert out["n_passes_near_slice_edge"] == 1
    assert out["n_unexplained"] == 1


def test_caller_explicability_slice_edge_is_none_when_every_day_is_scanned(tmp_path):
    # days=None scans everything, so no witness can be out of scope: the caveat field is
    # None, not a bare 0 that reads like a measured "no edge cases".
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [_ep("e1", "2026-07-23T00:01:00+00:00")])
    _write_lines(tmp_path, "sports_pairs", "2026-07-23", [_pass("s1", "2026-07-23T11:00:00+00:00")])
    assert tgm.caller_explicability(tmp_path, "econ_prints")["n_passes_near_slice_edge"] is None
    pinned = tgm.caller_explicability(tmp_path, "econ_prints", days=["dt=2026-07-23"])
    assert pinned["n_passes_near_slice_edge"] == 1


def test_caller_explicability_explained_by_caller_values_overlap_and_do_not_sum(tmp_path):
    # crypto_hourly witnesses BOTH callers, so one pass is counted under each. A consumer
    # that sums these would double-count; the docstring says so and this pins it.
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [_ep("e1", "2026-07-23T09:00:00+00:00")])
    _write_lines(tmp_path, "crypto_hourly", "2026-07-23", [_pass("c1", "2026-07-23T09:00:30+00:00")])
    out = tgm.caller_explicability(tmp_path, "econ_prints")
    assert out["n_passes"] == 1 and out["n_explained"] == 1
    assert out["explained_by_caller"] == {"burst_capture": 1, "hourly_pass": 1}
    assert sum(out["explained_by_caller"].values()) == 2 > out["n_explained"]


def test_caller_explicability_coverage_note_states_the_proxy_limit(tmp_path):
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [_ep("e1", "2026-07-23T09:00:00+00:00")])
    _write_lines(tmp_path, "sports_pairs", "2026-07-23", [_pass("s1", "2026-07-23T09:00:10+00:00")])
    out = tgm.caller_explicability(tmp_path, "econ_prints")
    assert out["verdict"] == "ALL_EXPLICABLE"
    note = out["coverage_note"].lower()
    assert "proxy" in note and "never proof" in note and "capture_source" in note


def test_caller_explicability_cli_prints_json(tmp_path, capsys):
    _write_lines(tmp_path, "econ_prints", "2026-07-23", [_ep("e1", "2026-07-23T09:00:00+00:00")])
    _write_lines(tmp_path, "sports_pairs", "2026-07-23", [_pass("s1", "2026-07-23T11:00:00+00:00")])
    rc = tgm.main(["--tape-root", str(tmp_path), "--caller-explicability", "econ_prints",
                   "--explicability-days", "dt=2026-07-23", "--no-notify"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["family"] == "econ_prints"
    assert out["verdict"] == "UNEXPLAINED_PASSES"
    assert out["days_scanned"] == ["dt=2026-07-23"]


@_real
def test_acceptance_11_l222_econ_prints_0723_is_wholly_inexplicable():
    """HARD real-tape acceptance, FROZEN to dt=2026-07-23 (L191).

    Reproduces `findings/2026-07-29-econ-prints-tape-audit.md` D1 exactly: 18 distinct
    econ_prints passes land that day and NOT ONE has a sibling leg of any registered
    caller anywhere near it — the nearest witness is >2 hours away, versus the ~60-540s
    spread a real hourly_pass invocation shows. This is the incident that had to be
    hand-derived to be seen; it is now machine-reported."""
    out = tgm.caller_explicability(_REAL_TAPE, "econ_prints", days=["dt=2026-07-23"])
    assert out["verdict"] == "UNEXPLAINED_PASSES"
    assert out["n_passes"] == 18
    assert out["n_unexplained"] == 18
    assert out["unexplained_fraction"] == 1.0
    assert out["explained_by_caller"] == {"burst_capture": 0, "hourly_pass": 0}
    # Not an absence-of-witness artifact: witnesses DID capture that day, just hours away.
    assert out["n_witness_passes"] > 0
    assert out["nearest_witness_gap_s"]["min"] > 7200.0
    # Not a slice-edge artifact either.
    assert out["n_passes_near_slice_edge"] == 0


@_real
def test_acceptance_12_l222_econ_prints_0714_cpi_burst_is_fully_explicable():
    """HARD real-tape acceptance, FROZEN to dt=2026-07-14 (L191) — the ABSTENTION case.

    137 econ_prints passes in one day is the loudest anomaly in the whole family, and a
    firing-window rule would flag every one of them. But `burst_capture` co-wrote
    crypto_hourly and polymarket_macro_pairs throughout the CPI burst, so all 137 are
    explicable and this check reports ZERO. A detector that cannot abstain here would be
    useless. Also pins L222's OTHER measured fact: consecutive pass starts 0.153s apart,
    far below v3_market's ~1.8s rate-limit floor, proving concurrent invocations."""
    out = tgm.caller_explicability(_REAL_TAPE, "econ_prints", days=["dt=2026-07-14"])
    assert out["verdict"] == "ALL_EXPLICABLE"
    assert out["n_passes"] == 137
    assert out["n_unexplained"] == 0
    assert out["explained_by_caller"]["burst_capture"] == 137
    assert out["min_consecutive_pass_gap_s"] == 0.153
    assert out["concurrent_invocations_proven"] is True


@_real
def test_acceptance_13_l222_an_ungated_leg_is_clean_on_the_same_tape():
    """HARD real-tape acceptance, FROZEN to dt=2026-07-20 (L191) — the NEGATIVE control.

    The check must not simply flag everything. `sports_pairs` is an UNGATED leg of the same
    invocations, on a day econ_prints shows 14/23 unexplained: all 8 of its passes are
    explicable, with the nearest witness ~57s away (the real intra-invocation leg spread)."""
    clean = tgm.caller_explicability(_REAL_TAPE, "sports_pairs", days=["dt=2026-07-20"])
    assert clean["verdict"] == "ALL_EXPLICABLE"
    assert clean["n_passes"] == 8
    assert clean["n_unexplained"] == 0
    assert clean["nearest_witness_gap_s"]["max"] < tgm.CO_OCCURRENCE_TOLERANCE_S
    dirty = tgm.caller_explicability(_REAL_TAPE, "econ_prints", days=["dt=2026-07-20"])
    assert dirty["n_passes"] == 23
    assert dirty["n_unexplained"] == 14


def test_burst_capture_key_to_tape_family_matches_registry():
    """`BURST_CAPTURE_KEY_TO_TAPE_FAMILY` must cover exactly the `--families` values
    `collection.burst_capture` actually accepts (2026-07-31 polymarket_pairs tape audit: the
    prior hand-maintained 3-family tuple silently omitted "wc"/"cpi"/"sports", so
    `polymarket_pairs` and `sports_pairs` were never registered as burst_capture-written at
    all). This is the drift detector: it fails loudly the moment burst_capture's own family
    registry changes without this map being updated."""
    assert set(tgm.BURST_CAPTURE_KEY_TO_TAPE_FAMILY.keys()) == set(
        _burst_capture.VALID_FAMILIES
    )


def test_burst_capture_co_written_families_now_includes_polymarket_pairs_and_sports_pairs():
    assert "polymarket_pairs" in tgm.BURST_CAPTURE_CO_WRITTEN_FAMILIES
    assert "polymarket_cpi_pairs" in tgm.BURST_CAPTURE_CO_WRITTEN_FAMILIES
    assert "sports_pairs" in tgm.BURST_CAPTURE_CO_WRITTEN_FAMILIES
    assert "polymarket_pairs" in tgm.REGISTERED_CALLER_FAMILIES["burst_capture"]
    assert "sports_pairs" in tgm.REGISTERED_CALLER_FAMILIES["burst_capture"]


@_real
def test_acceptance_14_l222_polymarket_pairs_wcsemi2_burst_is_registered_but_still_arity_blind():
    """HARD real-tape acceptance, FROZEN to dt=2026-07-15 (L191).

    Reproduces `findings/2026-07-31-polymarket-pairs-tape-audit.md`: 14 of 57 `polymarket_pairs`
    passes that day are the `kalshi-burst-wcsemi2-0715` one-shot (--families wc alone, 120s
    cadence, 20:39:28Z-21:05:28Z). Before this fix `burst_capture` was not even a registered
    caller of `polymarket_pairs`; after it, `burst_capture` IS registered and explains the other
    43 passes (a multi-family CPI-style window earlier that day) — but these 14 remain
    UNEXPLAINED, because a single-family round has no sibling leg to witness by. That is the
    documented arity blind spot, not a registry bug: pin both facts so a future "fix" doesn't
    silently paper over the blind spot by faking a witness."""
    out = tgm.caller_explicability(_REAL_TAPE, "polymarket_pairs", days=["dt=2026-07-15"])
    assert "burst_capture" in out["registered_callers"]
    assert out["n_passes"] == 57
    assert out["verdict"] == "UNEXPLAINED_PASSES"
    assert out["n_unexplained"] == 14
    assert out["explained_by_caller"]["burst_capture"] == 43
    unexplained_minutes = sorted(
        _parse_iso_utc(t) for t in out["unexplained_examples"]
    )
    assert len(unexplained_minutes) == 14
    gaps = {round((b - a).total_seconds()) for a, b in zip(unexplained_minutes, unexplained_minutes[1:])}
    assert gaps == {120}, "the unexplained passes form a regular 120s burst cadence, not noise"


# --------------------------------------------------------------------------- #
# burst_window_liveness / burst_trigger_liveness — L227's PREVENTION half
# --------------------------------------------------------------------------- #
def _burst_pass(tape_root, family, day, ts, cid=None):
    _write_lines(tape_root, family, day, [_pass(cid or ts, ts)])


def test_burst_window_liveness_no_passes_in_window_is_total_loss(tmp_path):
    _burst_pass(tmp_path, "crypto_hourly", "2026-07-14", "2026-07-14T10:00:00+00:00")
    out = tgm.burst_window_liveness(
        tmp_path, "crypto_hourly",
        _dt(2026, 7, 14, 17, 40), _dt(2026, 7, 14, 19, 45),
        expected_interval_s=90.0,
    )
    assert out["verdict"] == "NO_PASSES_IN_WINDOW"
    assert out["n_passes_in_window"] == 0
    assert out["gaps"] == []
    assert out["max_gap_s"] is None


def test_burst_window_liveness_steady_cadence_is_live(tmp_path):
    start = _dt(2026, 7, 14, 17, 40)
    for i in range(20):
        ts = (start + timedelta(seconds=90 * i)).isoformat()
        _burst_pass(tmp_path, "crypto_hourly", "2026-07-14", ts, cid=f"p{i}")
    out = tgm.burst_window_liveness(
        tmp_path, "crypto_hourly", start, start + timedelta(seconds=90 * 19),
        expected_interval_s=90.0,
    )
    assert out["verdict"] == "LIVE"
    assert out["n_passes_in_window"] == 20
    assert out["gaps"] == []


def test_burst_window_liveness_interior_gap_is_reported_with_bounds(tmp_path):
    start = _dt(2026, 7, 14, 17, 40)
    times = [start, start + timedelta(seconds=90), start + timedelta(seconds=1200)]
    for i, t in enumerate(times):
        _burst_pass(tmp_path, "crypto_hourly", "2026-07-14", t.isoformat(), cid=f"p{i}")
    out = tgm.burst_window_liveness(
        tmp_path, "crypto_hourly", start, times[-1] + timedelta(seconds=90),
        expected_interval_s=90.0, gap_multiplier=3.0,
    )
    assert out["verdict"] == "OUTAGE_DETECTED"
    assert out["threshold_s"] == 270.0
    interior = [g for g in out["gaps"] if g["kind"] == "interior"]
    assert len(interior) == 1
    assert interior[0]["start"] == times[1].isoformat()
    assert interior[0]["end"] == times[2].isoformat()
    assert interior[0]["duration_s"] == pytest.approx(1110.0)
    assert out["max_gap_s"] == pytest.approx(1110.0)


def test_burst_window_liveness_lead_in_and_trail_gaps_are_flagged(tmp_path):
    window_start = _dt(2026, 7, 14, 17, 40)
    window_end = _dt(2026, 7, 14, 19, 45)
    # First pass 20 minutes late; last pass 20 minutes before window close.
    first = window_start + timedelta(seconds=1200)
    last = window_end - timedelta(seconds=1200)
    _burst_pass(tmp_path, "crypto_hourly", "2026-07-14", first.isoformat(), cid="a")
    _burst_pass(tmp_path, "crypto_hourly", "2026-07-14", last.isoformat(), cid="b")
    out = tgm.burst_window_liveness(
        tmp_path, "crypto_hourly", window_start, window_end, expected_interval_s=90.0,
    )
    kinds = {g["kind"] for g in out["gaps"]}
    assert "lead_in" in kinds
    assert "trail" in kinds
    assert out["verdict"] == "OUTAGE_DETECTED"


def test_burst_window_liveness_gap_multiplier_controls_the_threshold(tmp_path):
    start = _dt(2026, 7, 14, 17, 40)
    mid = start + timedelta(seconds=200)
    _burst_pass(tmp_path, "crypto_hourly", "2026-07-14", start.isoformat(), cid="a")
    _burst_pass(tmp_path, "crypto_hourly", "2026-07-14", mid.isoformat(), cid="b")
    # 200s gap: LIVE at the default 3x90s=270s threshold, OUTAGE at a tight 1x=90s threshold.
    live = tgm.burst_window_liveness(
        tmp_path, "crypto_hourly", start, mid, expected_interval_s=90.0, gap_multiplier=3.0,
    )
    assert live["verdict"] == "LIVE"
    strict = tgm.burst_window_liveness(
        tmp_path, "crypto_hourly", start, mid, expected_interval_s=90.0, gap_multiplier=1.0,
    )
    assert strict["verdict"] == "OUTAGE_DETECTED"


def test_burst_trigger_liveness_unknown_trigger_is_honest_not_a_guess(tmp_path):
    out = tgm.burst_trigger_liveness(tmp_path, "kalshi-burst-does-not-exist")
    assert out["verdict"] == "UNKNOWN_TRIGGER"
    assert out["families"] == {}


def test_burst_trigger_liveness_dispatches_every_configured_family(tmp_path):
    cfg = tgm.BURST_TRIGGER_WINDOWS["kalshi-burst-fomc-0729"]
    start = _dt(2026, 7, 29, 17, 40)
    end = _dt(2026, 7, 29, 19, 45)
    n_passes = int((end - start).total_seconds() // 90.0) + 1
    for i in range(n_passes):
        ts = (start + timedelta(seconds=90 * i)).isoformat()
        for key in cfg["burst_keys"]:
            fam = tgm.BURST_CAPTURE_KEY_TO_TAPE_FAMILY[key]
            _burst_pass(tmp_path, fam, "2026-07-29", ts, cid=f"{fam}-{i}")
    out = tgm.burst_trigger_liveness(tmp_path, "kalshi-burst-fomc-0729")
    assert out["verdict"] == "LIVE"
    expected_families = {tgm.BURST_CAPTURE_KEY_TO_TAPE_FAMILY[k] for k in cfg["burst_keys"]}
    assert set(out["families"].keys()) == expected_families
    for fam_result in out["families"].values():
        assert fam_result["verdict"] == "LIVE"


def test_burst_trigger_windows_keys_are_all_known_burst_capture_keys():
    """Every `burst_keys` entry in the declared-window table must be a real
    `collection.burst_capture` family key — the same drift guard as
    `test_burst_capture_key_to_tape_family_matches_registry`, applied to this table."""
    for trigger, cfg in tgm.BURST_TRIGGER_WINDOWS.items():
        for key in cfg["burst_keys"]:
            assert key in tgm.BURST_CAPTURE_KEY_TO_TAPE_FAMILY, (trigger, key)


@_real
def test_acceptance_15_l227_fomc_burst_had_a_real_outage_in_its_declared_window():
    """HARD real-tape acceptance, FROZEN to the kalshi-burst-fomc-0729 trigger's declared
    window (17:40-19:45Z, 2026-07-29). This is L227's own originating incident, now
    machine-detected from the DECLARED window instead of the narrower 17:40-18:30Z slice a
    human happened to inspect by hand: crypto_hourly/econ_prints/polymarket_macro_pairs all
    show a >=700s interior gap bracketing the 18:00:00Z FOMC statement, AND (a fact the
    narrower hand audit didn't see) further multi-hundred-second gaps recur through the rest
    of the declared window — the burst leg was live for barely the first ten minutes, not
    merely blipping once at the release instant."""
    out = tgm.burst_trigger_liveness(_REAL_TAPE, "kalshi-burst-fomc-0729")
    assert out["verdict"] == "OUTAGE_DETECTED"
    for fam in ("crypto_hourly", "econ_prints", "polymarket_macro_pairs"):
        r = out["families"][fam]
        assert r["verdict"] == "OUTAGE_DETECTED"
        assert r["n_passes_in_window"] > 0
        release_bracketing = [
            g for g in r["gaps"]
            if g["start"] < "2026-07-29T18:00:00" < g["end"]
        ]
        assert release_bracketing, f"{fam}: no gap brackets the 18:00:00Z release"
        assert release_bracketing[0]["duration_s"] > 700.0


@_real
def test_acceptance_16_l227_cpi_burst_is_the_negative_control_stayed_live():
    """HARD real-tape acceptance, FROZEN to kalshi-burst-cpi-0714's declared window
    (12:05-13:45Z, 2026-07-14). The negative control every L213/L222 precedent already
    established by hand: this burst's own tape shows dense, unbroken cadence throughout —
    the detector must not flag a healthy burst just because it CAN flag one."""
    out = tgm.burst_trigger_liveness(_REAL_TAPE, "kalshi-burst-cpi-0714")
    assert out["verdict"] == "LIVE"
    for fam, r in out["families"].items():
        assert r["verdict"] == "LIVE", fam
        assert r["n_passes_in_window"] > 50, fam


@_real
def test_acceptance_17_l227_wcfinal_burst_was_a_total_loss():
    """HARD real-tape acceptance, FROZEN to kalshi-burst-wcfinal-0719's declared window
    (20:10-22:45Z, 2026-07-19). L213's own text names this trigger (alongside WC-semi1) as
    having "lost ... entirely" — the total-loss case NO_PASSES_IN_WINDOW exists for, distinct
    from a mid-window OUTAGE_DETECTED gap."""
    out = tgm.burst_trigger_liveness(_REAL_TAPE, "kalshi-burst-wcfinal-0719")
    assert out["verdict"] == "OUTAGE_DETECTED"
    assert out["families"]["polymarket_pairs"]["verdict"] == "NO_PASSES_IN_WINDOW"
    assert out["families"]["polymarket_pairs"]["n_passes_in_window"] == 0


# ─── L221: single-hour gate idempotence (rate gate vs idempotence gate) ────────────────

def _write_leg_tape(root: Path, family: str, day: str, rows):
    """rows = [(capture_id, captured_at_iso, payload_dict), ...] -> one dt= day-file."""
    d = root / family
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"dt={day}.jsonl", "w", encoding="utf-8") as fh:
        for cid, ca, payload in rows:
            rec = dict(payload)
            rec["capture_id"] = cid
            rec["captured_at"] = ca
            fh.write(json.dumps(rec) + "\n")


def test_l221_payload_identity_ignores_only_the_volatile_fields():
    """Two captures of the SAME payload differ only in the pass stamps, so they must share an
    identity — and a genuine payload change must NOT."""
    a = {"capture_id": "A", "captured_at": "2026-07-13T09:00:00+00:00", "series": "cpi", "v": 1}
    b = {"capture_id": "B", "captured_at": "2026-07-13T09:40:00+00:00", "series": "cpi", "v": 1}
    c = {"capture_id": "C", "captured_at": "2026-07-13T09:41:00+00:00", "series": "cpi", "v": 2}
    assert tgm.payload_identity(a) == tgm.payload_identity(b)
    assert tgm.payload_identity(a) != tgm.payload_identity(c)


def test_l221_payload_volatile_fields_reuse_the_l210_sequence_constant():
    """The within-pass sequence fields must come FROM the L210 constant, never be re-listed —
    a second copy is exactly the desync this repo's twin discipline forbids."""
    for f in tgm.WITHIN_PASS_SEQUENCE_FIELDS:
        assert f in tgm.PAYLOAD_VOLATILE_FIELDS
    assert "capture_id" in tgm.PAYLOAD_VOLATILE_FIELDS
    assert "captured_at" in tgm.PAYLOAD_VOLATILE_FIELDS


def test_l221_missing_family_is_none_not_a_clean_result(tmp_path):
    """`no_signal` discipline: a family with no committed day-files returns None, which must
    never be conflated with 'checked and clean'."""
    (tmp_path / "tape").mkdir()
    assert tgm.single_hour_leg_idempotence(tmp_path / "tape", "nope", 9) is None


def test_l221_rejects_an_impossible_gate_hour(tmp_path):
    """A gate hour outside 0..23 raises rather than silently auditing a window that cannot
    occur (the same posture as the wrapped-slot-window guard)."""
    _write_leg_tape(tmp_path, "fam", "2026-07-13",
                    [("A", "2026-07-13T09:00:00+00:00", {"v": 1})])
    for bad in (-1, 24, 99, True):
        with pytest.raises(ValueError):
            tgm.single_hour_leg_idempotence(tmp_path, "fam", bad)


def test_l221_one_pass_per_day_is_clean(tmp_path):
    """The negative control: a genuinely idempotent leg (one pass/day, changing payload)
    reports ONE_PASS_PER_DAY with zero redundancy."""
    _write_leg_tape(tmp_path, "fam", "2026-07-13",
                    [("A", "2026-07-13T09:10:00+00:00", {"v": 1})])
    _write_leg_tape(tmp_path, "fam", "2026-07-14",
                    [("B", "2026-07-14T09:10:00+00:00", {"v": 2})])
    r = tgm.single_hour_leg_idempotence(tmp_path, "fam", 9)
    assert r["verdict"] == "ONE_PASS_PER_DAY"
    assert r["max_passes_per_day"] == 1
    assert r["max_passes_per_day_excl_burst"] == 1
    assert r["n_days_over_capture"] == 0
    assert r["redundant_line_fraction"] == 0.0
    assert r["gate_attributable_redundant_line_fraction"] == 0.0


def test_l221_repeat_passes_same_day_are_over_capture(tmp_path):
    """Two passes inside the gated hour re-capturing an unchanged payload: the exact L221
    failure. Both measures must fire."""
    _write_leg_tape(tmp_path, "fam", "2026-07-13", [
        ("A", "2026-07-13T09:10:00+00:00", {"v": 1}),
        ("B", "2026-07-13T09:40:00+00:00", {"v": 1}),
    ])
    r = tgm.single_hour_leg_idempotence(tmp_path, "fam", 9)
    assert r["verdict"] == "OVER_CAPTURE"
    assert r["max_passes_per_day"] == 2
    assert r["max_passes_in_gate_hour"] == 2
    assert r["n_lines"] == 2 and r["n_distinct_payloads"] == 1
    assert r["redundant_line_fraction"] == 0.5
    assert r["gate_attributable_redundant_line_fraction"] == 0.5
    assert r["over_capture_examples"][0]["day"] == "dt=2026-07-13"


def test_l221_fast_moving_payload_reads_zero_redundant_but_still_over_capture(tmp_path):
    """Limit (b), pinned: a payload that changes every pass makes redundancy read 0.0. Only
    the pass-count measure can see the gate leak — this is why BOTH are reported."""
    _write_leg_tape(tmp_path, "fam", "2026-07-13", [
        ("A", "2026-07-13T09:10:00+00:00", {"v": 1}),
        ("B", "2026-07-13T09:40:00+00:00", {"v": 2}),
    ])
    r = tgm.single_hour_leg_idempotence(tmp_path, "fam", 9)
    assert r["redundant_line_fraction"] == 0.0
    assert r["verdict"] == "OVER_CAPTURE"
    assert r["max_passes_per_day"] == 2


def test_l221_redundancy_decomposition_partitions_exactly(tmp_path):
    """The three shares must sum to the whole-slice fraction with no remainder, and each must
    land on the right mechanism: intra-pass (collector wrote it twice in ONE pass), across-pass
    within day (the gate), cross-day (legitimate re-report)."""
    _write_leg_tape(tmp_path, "fam", "2026-07-13", [
        ("A", "2026-07-13T09:10:00+00:00", {"v": 1}),   # pass A
        ("A", "2026-07-13T09:10:01+00:00", {"v": 1}),   # same pass, duplicate -> intra_pass
        ("B", "2026-07-13T09:40:00+00:00", {"v": 1}),   # 2nd pass, same payload -> gate
    ])
    _write_leg_tape(tmp_path, "fam", "2026-07-14", [
        ("C", "2026-07-14T09:10:00+00:00", {"v": 1}),   # next day, same payload -> cross_day
    ])
    r = tgm.single_hour_leg_idempotence(tmp_path, "fam", 9)
    d = r["redundancy_decomposition"]
    assert r["n_lines"] == 4 and r["n_distinct_payloads"] == 1
    assert d["intra_pass"] == pytest.approx(0.25)
    assert d["across_pass_within_day"] == pytest.approx(0.25)
    assert d["cross_day"] == pytest.approx(0.25)
    assert (d["intra_pass"] + d["across_pass_within_day"] + d["cross_day"]
            == pytest.approx(r["redundant_line_fraction"]))
    assert r["gate_attributable_redundant_line_fraction"] == pytest.approx(0.25)


def test_l221_off_gate_hour_pass_still_counts_toward_the_verdict(tmp_path):
    """Limit (e), pinned: a leg landing after its pass-start hour stamps `captured_at` in the
    NEXT hour. The verdict measure is passes-per-DAY, so such a pass is still counted — while
    `max_passes_in_gate_hour` (the drift-sensitive one) stays a lower bound."""
    _write_leg_tape(tmp_path, "fam", "2026-07-13", [
        ("A", "2026-07-13T09:55:00+00:00", {"v": 1}),
        ("B", "2026-07-13T10:05:00+00:00", {"v": 1}),
    ])
    r = tgm.single_hour_leg_idempotence(tmp_path, "fam", 9)
    assert r["max_passes_in_gate_hour"] == 1          # drift hides one
    assert r["max_passes_per_day"] == 2               # the verdict measure does not
    assert r["verdict"] == "OVER_CAPTURE"
    assert r["per_day"]["dt=2026-07-13"]["n_passes_off_gate_hour"] == 1


def test_l221_declared_burst_window_passes_are_excused(tmp_path):
    """A declared burst trigger re-fires these collectors on purpose. Those passes must not be
    counted as gate leakage — otherwise the check manufactures an incident out of sanctioned
    collection."""
    rows = [(f"P{i}", f"2026-07-14T12:{10 + i:02d}:00+00:00", {"v": 1}) for i in range(6)]
    _write_leg_tape(tmp_path, "econ_prints", "2026-07-14", rows)
    r = tgm.single_hour_leg_idempotence(tmp_path, "econ_prints", 9)
    assert r["max_passes_per_day"] == 6
    assert r["max_passes_per_day_excl_burst"] == 0
    assert r["n_burst_expected_passes"] == 6
    assert r["verdict"] == "ONE_PASS_PER_DAY"
    # a family NOT driven by any declared trigger gets no exclusion at all
    _write_leg_tape(tmp_path, "weather_actuals", "2026-07-14", rows)
    r2 = tgm.single_hour_leg_idempotence(tmp_path, "weather_actuals", 12)
    assert r2["n_burst_expected_passes"] == 0
    assert r2["verdict"] == "OVER_CAPTURE"


def test_l221_days_pins_a_frozen_slice_and_max_days_trims(tmp_path):
    """L191 frozen-slice discipline: `days` selects exact stems; `max_days` keeps the N most
    recent AFTER that filter, so a cheap routine run cannot silently redefine a pinned slice."""
    for day in ("2026-07-13", "2026-07-14", "2026-07-15"):
        _write_leg_tape(tmp_path, "fam", day,
                        [("A" + day, f"{day}T09:10:00+00:00", {"v": day})])
    assert tgm.single_hour_leg_idempotence(tmp_path, "fam", 9)["n_days"] == 3
    pinned = tgm.single_hour_leg_idempotence(
        tmp_path, "fam", 9, days=["dt=2026-07-13", "dt=2026-07-14"])
    assert pinned["days_scanned"] == ["dt=2026-07-13", "dt=2026-07-14"]
    assert pinned["slice_pinned"] is True
    trimmed = tgm.single_hour_leg_idempotence(tmp_path, "fam", 9, max_days=1)
    assert trimmed["days_scanned"] == ["dt=2026-07-15"]
    both = tgm.single_hour_leg_idempotence(
        tmp_path, "fam", 9, days=["dt=2026-07-13", "dt=2026-07-14"], max_days=1)
    assert both["days_scanned"] == ["dt=2026-07-14"]


def test_l221_malformed_lines_are_counted_never_guessed(tmp_path):
    """A malformed line is reported, not silently dropped into the denominator."""
    d = tmp_path / "fam"
    d.mkdir(parents=True)
    (d / "dt=2026-07-13.jsonl").write_text(
        '{"capture_id":"A","captured_at":"2026-07-13T09:10:00+00:00","v":1}\n'
        "not json\n"
        "[]\n"
        "\n", encoding="utf-8")
    r = tgm.single_hour_leg_idempotence(tmp_path, "fam", 9)
    assert r["n_lines"] == 1
    assert r["n_malformed_lines"] == 2


def test_l221_files_present_but_nothing_parseable_is_a_distinct_verdict(tmp_path):
    """Files exist but yield no record: NO_PARSEABLE_LINES, distinct from None (no files)."""
    d = tmp_path / "fam"
    d.mkdir(parents=True)
    (d / "dt=2026-07-13.jsonl").write_text("garbage\n", encoding="utf-8")
    r = tgm.single_hour_leg_idempotence(tmp_path, "fam", 9)
    assert r is not None
    assert r["verdict"] == "NO_PARSEABLE_LINES"
    assert r["n_lines"] == 0


def test_l221_coverage_note_names_every_limit_it_must_travel_with():
    """The honest limits have to ride along with any quoted number (L155/L165 discipline)."""
    note = None
    root = _REAL_TAPE if _REAL_TAPE.is_dir() else None
    if root is not None:
        rep = tgm.single_hour_leg_idempotence(root, "econ_prints", 9, max_days=1)
        note = rep and rep.get("coverage_note")
    if note is None:
        pytest.skip("committed tape/ not present")
    for token in ("PROXY", "capture_source", "max_passes_per_day", "LOWER bound",
                  "burst", "write path"):
        assert token in note, token


@_real
def test_acceptance_18_l221_econ_prints_frozen_slice_reproduces_the_recorded_54pct():
    """HARD real-tape acceptance on the FROZEN dt=2026-07-05..28 slice (L191) that produced
    L221's own recorded numbers: 1,720 committed lines collapsing to 785 distinct payloads =
    54.4% byte-redundant re-capture (findings/2026-07-29-econ-prints-tape-audit.md D2). The
    row's per-series figures are reproduced by the same identity rule. This is the row's own
    finding, now machine-reported instead of hand-derived."""
    days = [f"dt=2026-07-{d}" for d in
            ("05", "06", "07", "08", "11", "12", "13", "14", "15", "16",
             "17", "18", "19", "20", "21", "22", "23", "26", "28")]
    r = tgm.single_hour_leg_idempotence(_REAL_TAPE, "econ_prints", 9, days=days)
    assert r["n_lines"] == 1720
    assert r["n_distinct_payloads"] == 785
    assert r["redundant_line_fraction"] == pytest.approx(0.5436, abs=5e-4)
    assert r["verdict"] == "OVER_CAPTURE"
    # the gate admitted 58 passes inside ONE gated hour — a fact the hand audit did not state
    assert r["max_passes_in_gate_hour"] == 58
    assert r["per_day"]["dt=2026-07-13"]["n_passes_in_gate_hour"] == 58
    # and the 07-14 CPI burst is the busiest DAY, but its passes are excused as declared
    assert r["over_capture_examples"][0]["day"] == "dt=2026-07-14"
    assert r["per_day"]["dt=2026-07-14"]["n_passes"] > r["per_day"]["dt=2026-07-14"]["n_passes_excl_burst"]


@_real
def test_acceptance_19_l221_settlement_ledger_is_the_zero_redundancy_control():
    """HARD real-tape negative control for limit (b): `settlement_ledger`'s payload is a page
    of unique market rows, so byte-redundancy reads EXACTLY 0.0 across its whole committed
    history — yet its gate still admitted 3 passes in one day. A one-measure check would call
    this family clean; the pass-count measure is what catches it."""
    r = tgm.single_hour_leg_idempotence(_REAL_TAPE, "settlement_ledger", 10)
    assert r["redundant_line_fraction"] == 0.0
    assert r["gate_attributable_redundant_line_fraction"] == 0.0
    assert r["max_passes_per_day_excl_burst"] >= 2
    assert r["verdict"] == "OVER_CAPTURE"
