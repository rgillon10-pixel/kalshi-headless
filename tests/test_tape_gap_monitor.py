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
from datetime import datetime, timezone
from pathlib import Path

import pytest

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
    now = _dt(2026, 7, 22, 12, 0)
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
    now = _dt(2026, 7, 24, 12, 0)
    r = tgm.build_report(_REAL_TAPE, now)["anomalies"]
    assert r["alert"] is True, r
    assert "stale" in r["alert_reason"], r["alert_reason"]
    assert r["age_hours"] > 48.0, r["age_hours"]
