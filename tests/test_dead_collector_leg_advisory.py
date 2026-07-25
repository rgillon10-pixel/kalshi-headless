"""scripts/invariants.py — dead collector-leg advisory (L117/L129 recurrence).

All offline: the unit tests build synthetic tape under `tmp_path` and inject a frozen `now`;
no network, no git, no wall-clock dependence. One HARD acceptance test reads the repo's ACTUAL
committed tape (read-only) and asserts the advisory fires and names the `vps` leg — pinned to a
FIXED historical slice (`max_day=` + a frozen `now`) exactly so it cannot become the kind of
time-bomb L140 documents: it never calls `datetime.now()`, and tape written after the slice
day is excluded from the scan, so neither the passage of wall-clock time nor new tape landing
can flip it.

The advisory is NON-GATING by construction; `test_advisory_is_non_gating` pins that contract.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
from datetime import date, datetime, timedelta, timezone

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UTC = timezone.utc


def _load_engine():
    spec = importlib.util.spec_from_file_location("inv_engine_collector", ROOT / "scripts" / "invariants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inv = _load_engine()

# A real hourly-dual family name, so the fixture tape is scanned by the same family list the
# advisory imports from tape_gap_monitor.FAMILY_CONFIG.
FAMILY = "crypto_hourly"


def _write_capture(tape_root: pathlib.Path, ts: datetime, family: str = FAMILY) -> None:
    """Append one canonical-shaped tape line carrying `captured_at` at `ts`."""
    fam = tape_root / family
    fam.mkdir(parents=True, exist_ok=True)
    day = ts.date().isoformat()
    with open(fam / f"dt={day}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"captured_at": ts.isoformat(), "ticker": "KXBTCD-TEST"}) + "\n")


def _leg_series(tape_root: pathlib.Path, minute: int, first: datetime, last: datetime,
                step_h: int = 3) -> None:
    """Write one capture per `step_h` hours at a fixed minute-of-hour (a collector's signature)
    from `first` through `last` inclusive."""
    t = first.replace(minute=minute, second=11, microsecond=0)
    while t <= last:
        _write_capture(tape_root, t)
        t += timedelta(hours=step_h)


# ─── unit: both legs healthy ────────────────────────────────────────────────

def test_both_legs_healthy_no_advisory(tmp_path):
    now = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
    _leg_series(tmp_path, 23, now - timedelta(hours=72), now - timedelta(hours=1))   # vps :23
    _leg_series(tmp_path, 53, now - timedelta(hours=72), now - timedelta(hours=2))   # cloud :53
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=now)
    assert diag is None
    assert inv.dead_collector_leg_warning(diag) is None


# ─── unit: one leg dead ─────────────────────────────────────────────────────

def test_vps_leg_dead_advisory_names_vps(tmp_path):
    now = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
    # vps stops 40h ago; cloud keeps producing right up to now.
    _leg_series(tmp_path, 23, now - timedelta(hours=100), now - timedelta(hours=40))
    _leg_series(tmp_path, 53, now - timedelta(hours=100), now - timedelta(hours=1))
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=now)
    assert diag is not None
    assert diag["status"] == "dead_leg"
    assert diag["dead"] == "vps"
    assert diag["dead_silence_h"] >= inv.DEAD_LEG_SILENCE_HOURS
    assert "cloud" in diag["alive"]
    msg = inv.dead_collector_leg_warning(diag)
    assert msg is not None
    assert "'vps' collector leg appears DEAD" in msg
    assert "cloud" in msg
    assert diag["dead_last_seen"] in msg          # names the exact last-seen UTC timestamp
    assert "does NOT affect the exit code" in msg


def test_cloud_leg_dead_advisory_names_cloud(tmp_path):
    """The mirror case — the naming is data-driven, not hardcoded to 'vps'."""
    now = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
    _leg_series(tmp_path, 23, now - timedelta(hours=100), now - timedelta(hours=1))
    _leg_series(tmp_path, 53, now - timedelta(hours=100), now - timedelta(hours=30))
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=now)
    assert diag["status"] == "dead_leg"
    assert diag["dead"] == "cloud"
    msg = inv.dead_collector_leg_warning(diag)
    assert "'cloud' collector leg appears DEAD" in msg


def test_leg_silent_beyond_lookback_reports_unknown_not_a_fake_timestamp(tmp_path):
    """A leg dead longer than the day-file lookback has NO last-seen in scope — the advisory
    says so honestly instead of inventing one."""
    now = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
    _leg_series(tmp_path, 23, now - timedelta(days=40), now - timedelta(days=30))  # long gone
    _leg_series(tmp_path, 53, now - timedelta(hours=48), now - timedelta(hours=1))
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=now, lookback_days=3)
    assert diag["status"] == "dead_leg"
    assert diag["dead"] == "vps"
    assert diag["dead_last_seen"] is None
    msg = inv.dead_collector_leg_warning(diag)
    assert "not within the last 3 day-files" in msg


# ─── unit: both legs silent -> AMBIGUOUS, never a guess ─────────────────────

def test_both_legs_silent_is_ambiguous_and_names_nobody(tmp_path):
    """L118/L120 attribution discipline (tape_gap_monitor.diagnose_collector's both-zero case):
    when both scheduled legs are dark, a whole-pipe outage and two independent deaths are
    indistinguishable — the advisory must NOT pick a culprit."""
    now = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
    _leg_series(tmp_path, 23, now - timedelta(hours=120), now - timedelta(hours=50))
    _leg_series(tmp_path, 53, now - timedelta(hours=120), now - timedelta(hours=48))
    # An `other`-bucket writer (ad-hoc/secondary leg) is still alive.
    _write_capture(tmp_path, now - timedelta(hours=1, minutes=0))
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=now)
    assert diag["status"] == "ambiguous"
    assert "dead" not in diag
    assert sorted(diag["silent"]) == ["cloud", "vps"]
    msg = inv.dead_collector_leg_warning(diag)
    assert "AMBIGUOUS" in msg
    assert "appears DEAD" not in msg
    assert "vps" in msg and "cloud" in msg


def test_whole_pipe_dark_stays_ambiguous_not_attributed(tmp_path):
    """Nothing alive anywhere: still ambiguous, still no name."""
    now = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
    _leg_series(tmp_path, 23, now - timedelta(hours=120), now - timedelta(hours=50))
    _leg_series(tmp_path, 53, now - timedelta(hours=120), now - timedelta(hours=49))
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=now)
    assert diag["status"] == "ambiguous"
    msg = inv.dead_collector_leg_warning(diag)
    assert "NOTHING (whole pipe looks dark)" in msg


def test_one_leg_silent_but_nothing_alive_is_not_attributed(tmp_path):
    """A single silent leg with NO survivor is not the staggered-death signature (it is the
    2026-07-09 systemic-outage shape) — stay quiet rather than mis-attribute."""
    now = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
    _leg_series(tmp_path, 23, now - timedelta(hours=120), now - timedelta(hours=50))
    _leg_series(tmp_path, 53, now - timedelta(hours=120), now - timedelta(hours=12))
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=now)
    assert diag is None


# ─── unit: empty / absent tape ──────────────────────────────────────────────

def test_absent_tape_root_no_crash_no_advisory(tmp_path):
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path / "does_not_exist",
                                             now=datetime(2026, 7, 25, 6, 0, tzinfo=UTC))
    assert diag is None
    assert inv.dead_collector_leg_warning(diag) is None


def test_empty_tape_root_no_crash_no_advisory(tmp_path):
    (tmp_path / FAMILY).mkdir(parents=True)
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path,
                                             now=datetime(2026, 7, 25, 6, 0, tzinfo=UTC))
    assert diag is None


def test_unparseable_and_empty_lines_never_crash(tmp_path):
    """Junk in the tape degrades to "no signal", never an exception (best-effort contract)."""
    now = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
    fam = tmp_path / FAMILY
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-25.jsonl").write_text('{"captured_at": "not-a-timestamp"}\n\n', encoding="utf-8")
    (fam / "dt=not-a-date.jsonl").write_text("{}\n", encoding="utf-8")
    assert inv._collector_leg_last_seen(tmp_path) == {}
    assert inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=now) is None


# ─── contract: leg signatures are imported, not re-declared ─────────────────

def test_leg_signatures_come_from_tape_gap_monitor():
    """The minute-of-hour ranges have exactly one home (scripts/tape_gap_monitor.py); the
    advisory imports them. A second hardcoded copy would drift on recalibration."""
    tgm = inv._load_tape_gap_monitor()
    assert tgm is not None
    assert set(tgm.COLLECTOR_MINUTE_BUCKETS) == {"vps", "cloud"}
    src = (ROOT / "scripts" / "invariants.py").read_text(encoding="utf-8")
    assert "COLLECTOR_MINUTE_BUCKETS: Dict" not in src   # not re-declared here
    assert "range(20, 30)" not in src and "range(50, 60)" not in src


def test_monitored_legs_are_derived_from_the_bucket_map():
    """`DEAD_LEG_MONITORED` must not be a second hardcoded copy of the leg NAMES: every
    scheduled leg in COLLECTOR_MINUTE_BUCKETS is monitored, and the catch-all `other` bucket
    (never a key of that map) is never accused. Fails loudly if a leg is added/renamed."""
    tgm = inv._load_tape_gap_monitor()
    assert set(inv.DEAD_LEG_MONITORED) == set(tgm.COLLECTOR_MINUTE_BUCKETS)
    assert "other" not in inv.DEAD_LEG_MONITORED


def test_dead_leg_prose_follows_a_modified_bucket_map(monkeypatch):
    """DEFECT-2 pin: the human sentence the run digest quotes verbatim is RENDERED from the
    imported bucket range, so recalibrating the buckets moves the prose instead of making it
    lie. Pinned against a MODIFIED map — a hardcoded ':23 UTC' string fails this."""
    class _FakeTGM:
        COLLECTOR_MINUTE_BUCKETS = {"vps": range(5, 12), "cloud": range(40, 44)}

    monkeypatch.setattr(inv, "_load_tape_gap_monitor", lambda *a, **k: _FakeTGM)
    assert inv._leg_schedule_phrase("vps") == "captures at minutes 5-11 of the hour"
    diag = {"status": "dead_leg", "dead": "vps", "dead_last_seen": "2026-07-22T17:29:49Z",
            "dead_silence_h": 50.0, "alive": ["cloud"], "lookback_days": 10,
            "newest_iso": "2026-07-24T19:53:00Z", "newest_age_h": 0.1,
            "last_seen": {}, "ages": {}}
    msg = inv.dead_collector_leg_warning(diag)
    assert "  - dead leg: vps (captures at minutes 5-11 of the hour)" in msg
    assert ":23 UTC" not in msg and ":53 UTC" not in msg


def test_leg_schedule_phrase_degrades_honestly_when_buckets_unavailable(monkeypatch):
    monkeypatch.setattr(inv, "_load_tape_gap_monitor", lambda *a, **k: None)
    assert inv._leg_schedule_phrase("vps") == "schedule unknown"


# ─── DEFECT-1: no advisory failure can ever reach the exit code ─────────────

def _stub_expensive_checks(monkeypatch):
    """Neuter every OTHER whole-tree/whole-tape scan in main()'s --full branch so these exit
    -code tests are fast. The collector-advisory path under test is left fully real."""
    monkeypatch.setattr(inv, "scan_tree", lambda *a, **k: [])
    for name in ("_git_tape_refs", "_tape_dir_shape_issues",
                 "_tape_dir_shape_orphan_classification", "_daily_family_gap_issues",
                 "_unregistered_single_hour_leg_issues", "_raw_datetime_fromisoformat_sites",
                 "_ladder_size_coercion_issues", "_duplicate_lesson_id_issues",
                 "_stale_unenforced_candidate_issues", "_tape_conflict_marker_issues",
                 "_tape_invalid_jsonl_issues"):
        monkeypatch.setattr(inv, name, lambda *a, **k: [])


def _run_main(monkeypatch) -> int:
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    return inv.main()


def test_formatter_that_raises_does_not_change_the_exit_code(monkeypatch, capsys):
    """The diagnosis self-guards, but the FORMATTER did not: a raise there used to escape into
    the exit code, silently converting a non-gating advisory into a gate."""
    _stub_expensive_checks(monkeypatch)

    def _boom(_diag):
        raise RuntimeError("formatter blew up")

    monkeypatch.setattr(inv, "dead_collector_leg_warning", _boom)
    assert _run_main(monkeypatch) == 0
    assert "collector-health advisory could not be computed" in capsys.readouterr().err


def test_formatter_returning_a_non_str_does_not_change_the_exit_code(monkeypatch, capsys):
    """`warning + "\\n"` on a non-str is a TypeError at the CALL SITE, outside the formatter's
    own guard — it must still degrade to a note."""
    _stub_expensive_checks(monkeypatch)
    monkeypatch.setattr(inv, "dead_collector_leg_warning", lambda _d: 7)
    assert _run_main(monkeypatch) == 0
    assert "collector-health advisory could not be computed" in capsys.readouterr().err


def test_base_exception_in_the_advisory_path_does_not_change_the_exit_code(monkeypatch, capsys):
    """`except Exception` does not catch BaseException, and tape_gap_monitor.py is exec'd
    dynamically — a SystemExit at its module level would have propagated straight out."""
    _stub_expensive_checks(monkeypatch)

    def _sys_exit(*a, **k):
        raise SystemExit(3)

    monkeypatch.setattr(inv, "_dead_collector_leg_diagnosis", _sys_exit)
    assert _run_main(monkeypatch) == 0
    assert "collector-health advisory could not be computed" in capsys.readouterr().err


def test_healthy_advisory_path_still_runs_unstubbed_and_exits_zero(monkeypatch):
    """Control: with the guard in place and NOTHING monkeypatched in the advisory itself, the
    real path (which currently fires on the committed tape) still exits 0."""
    _stub_expensive_checks(monkeypatch)
    assert _run_main(monkeypatch) == 0


def test_advisory_is_non_gating():
    """The advisory must never contribute to the exit code: `main()` writes it to stderr and
    never appends it to `failures` (the gating list)."""
    src = (ROOT / "scripts" / "invariants.py").read_text(encoding="utf-8")
    i = src.index("collector_warning = dead_collector_leg_warning(")
    block = src[i:i + 400]
    assert "sys.stderr.write(collector_warning" in block
    assert "failures.append(collector_warning" not in src


# ─── HARD acceptance over the REAL committed tape (time-bomb-proofed) ───────

_REAL_TAPE = ROOT / "tape"
_real = pytest.mark.skipif(not _REAL_TAPE.is_dir(), reason="committed tape/ not present")

# The pinned slice. L140: a real-tape acceptance test must not depend on wall-clock time or on
# tape that has not been written yet. Both halves are frozen here:
#   * `_SLICE_MAX_DAY` caps the scan at dt=2026-07-24.jsonl, so every day-file the assertion
#     reads is a CLOSED, append-only historical file; tape landing on 07-25 and after is
#     invisible to it (including a future VPS recovery, which would otherwise flip it red).
#   * `_SLICE_NOW` is an injected constant — `datetime.now()` is never called.
# Ground truth for the slice (`git log` 2026-07-22T17:32:20Z last VPS tape commit; L117/L129):
# the vps leg's last hourly-family capture is 2026-07-22T17:29:49Z, ~50h before `_SLICE_NOW`,
# while the cloud leg was still capturing that evening.
_SLICE_MAX_DAY = date(2026, 7, 24)
_SLICE_NOW = datetime(2026, 7, 24, 20, 0, tzinfo=UTC)


@_real
def test_acceptance_real_tape_slice_names_the_dead_vps_leg():
    diag = inv._dead_collector_leg_diagnosis(tape_root=_REAL_TAPE, now=_SLICE_NOW,
                                             max_day=_SLICE_MAX_DAY)
    assert diag is not None, "the 2026-07-22 VPS death must be visible in committed tape"
    assert diag["status"] == "dead_leg"
    assert diag["dead"] == "vps"
    assert str(diag["dead_last_seen"]).startswith("2026-07-22"), diag["dead_last_seen"]
    assert diag["dead_silence_h"] >= inv.DEAD_LEG_SILENCE_HOURS
    assert "cloud" in diag["alive"]
    msg = inv.dead_collector_leg_warning(diag)
    assert "'vps' collector leg appears DEAD" in msg
    assert "captures at minutes 20-29 of the hour" in msg   # rendered from the bucket range
    assert "2026-07-22" in msg


@_real
def test_acceptance_real_tape_slice_is_stable_under_future_tape():
    """The slice result must be identical no matter how much later tape exists — the explicit
    anti-time-bomb assertion (L140). Scanning with a far-future `now` but the SAME capped slice
    changes only the reported silence duration, never the attribution."""
    a = inv._dead_collector_leg_diagnosis(tape_root=_REAL_TAPE, now=_SLICE_NOW,
                                          max_day=_SLICE_MAX_DAY)
    b = inv._collector_leg_last_seen(_REAL_TAPE, max_day=_SLICE_MAX_DAY)
    assert b["vps"] == a["dead_last_seen"]
    assert b["cloud"] > b["vps"]
