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


def test_no_diagnosis_when_both_collectors_zero_family_ambiguous(tmp_path):
    # An "other"-only leg (e.g. weather_books' real cloud offset, see module docstring)
    # is honestly left unattributed rather than forced into vps or cloud.
    now = _dt(2026, 7, 20, 0, 30)
    _hourly_day(tmp_path, "weather_books", "2026-07-19", range(0, 24), minute=3, complete=None)
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "weather_books", now), now)
    assert rec["collectors"]["vps"]["passes"] == 0
    assert rec["collectors"]["cloud"]["passes"] == 0
    assert rec["collectors"]["other"]["passes"] > 0
    assert rec["collector_diagnosis"] is None


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
    # perp_tape is one-shot/backfill: no cadence expectation, never pages even when old.
    _write_lines(tmp_path, "perp_tape", "2026-07-10",
                 [_pass("c1", "2026-07-10T01:00:00+00:00", record_type="funding_rates")])
    now = _dt(2026, 8, 1, 0, 0)  # weeks later
    rec = tgm.evaluate_family(tgm.aggregate_family(tmp_path, "perp_tape", now), now)
    assert rec["alert"] is False
    assert rec["completeness_ok"] is None  # no signal -> not fabricated True


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
