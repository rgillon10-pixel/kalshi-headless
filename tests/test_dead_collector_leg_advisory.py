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


def test_one_leg_silent_but_nothing_alive_is_degraded_not_attributed(tmp_path):
    """A single silent leg with NO survivor is not the staggered-death signature (it is the
    2026-07-09 systemic-outage shape), so it is still NOT attributed — but as of L273 it is no
    longer SILENT either. This test previously asserted `diag is None`; that assertion pinned
    the L273 defect (the worse the pipeline's health, the quieter the advisory) as if it were
    intended behaviour. The attribution half is unchanged and re-asserted below: no `dead` key,
    no accusation in the prose."""
    now = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
    _leg_series(tmp_path, 23, now - timedelta(hours=120), now - timedelta(hours=50))
    _leg_series(tmp_path, 53, now - timedelta(hours=120), now - timedelta(hours=12))
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=now)
    assert diag is not None
    assert diag["status"] == "degraded"
    assert "dead" not in diag
    assert diag["silent"] == ["vps"]
    assert diag["alive"] == []
    msg = inv.dead_collector_leg_warning(diag)
    assert "DEGRADED" in msg
    assert "appears DEAD" not in msg


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


# ─── L269: declared burst-window captures must not stand in for a scheduled pass ──
#
# The defect: a burst trigger deliberately re-fires the collectors every 60-120s inside its
# window, and one of those passes landed at minute :29 — inside the `vps` minute bucket — for
# `crypto_hourly` / `polymarket_macro_pairs` during `kalshi-burst-fomc-0729`. The aggregate
# MAX over families then read that burst pass as a live VPS pass and announced "silent for:
# 104.7h" while the families no trigger covers put the true last vps-bucket capture ~2.6x
# further back. Same blind spot L213 already closed for `slot_cadence_by_time_of_day`.

_FOMC_BURST_INSIDE = datetime(2026, 7, 29, 18, 29, 45, tzinfo=UTC)   # inside 17:40-19:45Z
_BURST_COVERED_FAMILY = "crypto_hourly"        # in kalshi-burst-fomc-0729's burst_keys
_NOT_BURST_COVERED_FAMILY = "orderbook_depth"  # covered by NO declared trigger


def _older_genuine_vps(tape_root: pathlib.Path, family: str) -> datetime:
    """A vps-bucket capture well before any declared burst window — the honest reading."""
    ts = datetime(2026, 7, 22, 17, 29, 49, tzinfo=UTC)
    _write_capture(tape_root, ts, family=family)
    return ts


def test_burst_window_capture_is_excluded_for_a_burst_covered_family(tmp_path):
    honest = _older_genuine_vps(tmp_path, _BURST_COVERED_FAMILY)
    _write_capture(tmp_path, _FOMC_BURST_INSIDE, family=_BURST_COVERED_FAMILY)

    on = inv._collector_leg_last_seen(tmp_path)
    assert on["vps"] == honest.isoformat(), "the burst pass must not stand in for a vps pass"

    off = inv._collector_leg_last_seen(tmp_path, exclude_burst_windows=False)
    assert off["vps"] == _FOMC_BURST_INSIDE.isoformat(), "pre-L269 reading must be reproducible"
    assert off["vps"] > on["vps"]


def test_same_instant_counts_for_a_family_no_declared_trigger_covers(tmp_path):
    """Per-FAMILY, never global wall-clock: the identical timestamp in a family outside the
    trigger's burst_keys is a genuine scheduled pass and must still count."""
    _older_genuine_vps(tmp_path, _NOT_BURST_COVERED_FAMILY)
    _write_capture(tmp_path, _FOMC_BURST_INSIDE, family=_NOT_BURST_COVERED_FAMILY)
    seen = inv._collector_leg_last_seen(tmp_path)
    assert seen["vps"] == _FOMC_BURST_INSIDE.isoformat()


def test_burst_pad_boundary_is_respected(tmp_path):
    """BURST_WINDOW_PAD_S (900s) absorbs trigger jitter: 17:26 is inside the padded window
    (17:25-20:00), 17:24 is outside it. Both are vps-bucket minutes on the same day."""
    outside = datetime(2026, 7, 29, 17, 24, 0, tzinfo=UTC)
    inside = datetime(2026, 7, 29, 17, 26, 0, tzinfo=UTC)
    _write_capture(tmp_path, outside, family=_BURST_COVERED_FAMILY)
    _write_capture(tmp_path, inside, family=_BURST_COVERED_FAMILY)
    seen = inv._collector_leg_last_seen(tmp_path)
    assert seen["vps"] == outside.isoformat()
    assert inv._collector_leg_last_seen(
        tmp_path, exclude_burst_windows=False)["vps"] == inside.isoformat()


def test_exclusion_is_reported_not_silent(tmp_path):
    """An exclusion nobody can see is indistinguishable from missing data — the stats out-dict
    names the count, the families, and the scan horizon."""
    _older_genuine_vps(tmp_path, _BURST_COVERED_FAMILY)
    _write_capture(tmp_path, _FOMC_BURST_INSIDE, family=_BURST_COVERED_FAMILY)
    stats: dict = {}
    inv._collector_leg_last_seen(tmp_path, stats=stats)
    assert stats["exclude_burst_windows"] is True
    assert stats["n_burst_excluded"] == 1
    assert stats["burst_excluded_by_family"] == {_BURST_COVERED_FAMILY: 1}
    assert stats["burst_table_unavailable"] == []
    assert stats["scan_oldest_day"] == "2026-07-22"


def test_missing_burst_table_degrades_to_old_behaviour_not_to_nothing(monkeypatch, tmp_path):
    """A missing/broken exclusion table must leave the advisory slightly OPTIMISTIC (the old
    reading), never blank it — a blanked advisory is how an outage goes unnoticed."""
    _older_genuine_vps(tmp_path, _BURST_COVERED_FAMILY)
    _write_capture(tmp_path, _FOMC_BURST_INSIDE, family=_BURST_COVERED_FAMILY)
    monkeypatch.setattr(inv, "_family_burst_windows", lambda *a, **k: None)
    stats: dict = {}
    seen = inv._collector_leg_last_seen(tmp_path, stats=stats)
    assert seen["vps"] == _FOMC_BURST_INSIDE.isoformat()   # old behaviour, not {}
    assert _BURST_COVERED_FAMILY in stats["burst_table_unavailable"]


def test_family_burst_windows_returns_none_when_the_helper_raises():
    class _Boom:
        @staticmethod
        def _burst_windows_for_family(_family):
            raise RuntimeError("table unreadable")

    assert inv._family_burst_windows(_Boom, "crypto_hourly") is None
    assert inv._family_burst_windows(object(), "crypto_hourly") is None


def test_burst_windows_table_has_exactly_one_home():
    """`BURST_TRIGGER_WINDOWS` / `BURST_WINDOW_PAD_S` live in scripts/tape_gap_monitor.py and
    are imported, never re-declared here — a second copy would desync on any trigger edit."""
    src = (ROOT / "scripts" / "invariants.py").read_text(encoding="utf-8")
    assert "BURST_TRIGGER_WINDOWS: Dict" not in src
    assert "BURST_WINDOW_PAD_S =" not in src
    assert "_burst_windows_for_family" in src


def test_warning_renders_for_a_diag_without_the_l269_keys():
    """Back-compat: a diag dict built before the L269 keys existed renders exactly as before —
    no KeyError, and no fabricated exclusion count."""
    diag = {"status": "dead_leg", "dead": "vps", "dead_last_seen": "2026-07-22T17:29:49Z",
            "dead_silence_h": 50.0, "alive": ["cloud"], "lookback_days": 10,
            "newest_iso": "2026-07-24T19:53:00Z", "newest_age_h": 0.1,
            "last_seen": {}, "ages": {}}
    msg = inv.dead_collector_leg_warning(diag)
    assert "excluded from this reading" not in msg
    assert "horizon caveat" not in msg


def test_warning_names_the_exclusion_when_present():
    diag = {"status": "dead_leg", "dead": "vps", "dead_last_seen": "2026-07-22T17:29:49Z",
            "dead_silence_h": 273.9, "alive": ["cloud"], "lookback_days": 10,
            "newest_iso": "2026-08-03T03:56:13Z", "newest_age_h": 0.1,
            "last_seen": {}, "ages": {},
            "exclude_burst_windows": True, "n_burst_excluded": 82,
            "burst_excluded_by_family": {"crypto_hourly": 24, "polymarket_macro_pairs": 23,
                                         "polymarket_pairs": 35},
            "burst_table_unavailable": [], "scan_oldest_day": "2026-07-05"}
    msg = inv.dead_collector_leg_warning(diag)
    assert "82 capture(s) written inside a DECLARED burst-trigger window" in msg
    assert "crypto_hourly" in msg and "polymarket_macro_pairs" in msg
    assert "L269" in msg
    assert "horizon caveat" in msg
    assert "2026-07-05" in msg


# ─── HARD acceptance: the L269 defect on the REAL committed tape, pinned ────
#
# Pinned exactly like the slice above so it cannot rot: `max_day=2026-08-01` caps the scan at
# CLOSED historical day-files, so neither new tape nor wall-clock time can move it. Ground
# truth (findings/2026-08-03-vps-collector-true-outage-273h-burst-contamination-blind-spot.md):
# WITHOUT the exclusion the vps reading is the kalshi-burst-fomc-0729 pass at
# 2026-07-29T18:29:45Z; WITH it, the honest last vps-bucket capture is 2026-07-22T17:29:49Z.
_L269_MAX_DAY = date(2026, 8, 1)


@_real
def test_acceptance_real_tape_burst_exclusion_moves_the_vps_reading():
    off = inv._collector_leg_last_seen(_REAL_TAPE, max_day=_L269_MAX_DAY,
                                       exclude_burst_windows=False)
    stats: dict = {}
    on = inv._collector_leg_last_seen(_REAL_TAPE, max_day=_L269_MAX_DAY, stats=stats)
    assert off["vps"].startswith("2026-07-29T18:29:45"), off["vps"]
    assert on["vps"].startswith("2026-07-22T17:29:49"), on["vps"]
    assert on["vps"] < off["vps"], "the fix must make the outage look LONGER, never shorter"
    # the cloud leg is not burst-contaminated in this slice and must be untouched
    assert on["cloud"] == off["cloud"]
    assert stats["n_burst_excluded"] > 0
    assert set(stats["burst_excluded_by_family"]) <= {
        "crypto_hourly", "polymarket_pairs", "polymarket_macro_pairs"}


# ─── L272: `alive` must be read from the burst-INCLUSIVE scan ───────────────
#
# The defect L269's own fix introduced: `_dead_collector_leg_diagnosis` passed ONE `last_seen`
# dict — already burst-excluded — into BOTH the `alive` computation and the `silent`/attribution
# computation. Excluding a burst-covered family's only recent capture could therefore empty
# `alive`, tripping the pre-existing `if not alive: return None` guard and DISCARDING an
# advisory the pre-L269 code raised. L269 was supposed to only ever make an outage look LONGER;
# on this path it made it look like NOTHING.
#
# The fix: two readings. `alive` comes from `exclude_burst_windows=False` (liveness is a
# lower-bound claim and a burst pass IS evidence something ran); `silent` / `dead` /
# `dead_silence_h` / `ages` / `last_seen` stay on the burst-EXCLUDED reading (L269's duration
# honesty, untouched). Because the liveness reading is the burst-inclusive one, `alive` is now
# byte-identical to pre-L269 `alive` — the guard fires exactly as often as it did before L269.

# now sits 30 minutes AFTER the padded fomc window closes (17:25-20:00Z), so a capture inside
# that window is ~2h old — recent enough to make its leg "alive" on the inclusive reading.
_L272_NOW = datetime(2026, 7, 29, 20, 30, tzinfo=UTC)
_L272_BURST_VPS = datetime(2026, 7, 29, 18, 29, 45, tzinfo=UTC)    # inside window, vps bucket
_L272_BURST_CLOUD = datetime(2026, 7, 29, 18, 53, 10, tzinfo=UTC)  # inside window, cloud bucket


def _l272_counterexample(tape_root: pathlib.Path) -> None:
    """The verifier's counterexample, verbatim in tape form.

    cloud: a burst-covered capture 1.6h ago (its ONLY sub-6h capture) plus a genuine capture
           14.6h ago — stale but NOT silent, so `silent` stays a strict subset and the
           `ambiguous` branch does not fire.
    vps:   a genuine capture 106h ago — unambiguously dead.

    Pre-fix, the burst-excluded reading put cloud at 14.6h, `alive` was empty, and the guard
    returned None: a 106h outage produced ZERO advisory.
    """
    _write_capture(tape_root, _L272_BURST_CLOUD)                                  # burst, 1.6h
    _write_capture(tape_root, datetime(2026, 7, 29, 5, 53, 10, tzinfo=UTC))       # genuine, 14.6h
    _write_capture(tape_root, datetime(2026, 7, 25, 10, 23, 5, tzinfo=UTC))       # genuine, 106.1h


def _pre_l272_diagnosis(tape_root, now, **kw):
    """Re-implement the SHIPPED (pre-L272) computation exactly: ONE burst-excluded reading
    feeding both halves. Keeps the defect demonstrable forever, the same way L269 kept its own
    defect reproducible via `exclude_burst_windows=False`."""
    last_seen = inv._collector_leg_last_seen(tape_root, exclude_burst_windows=True, **kw)
    if not last_seen:
        return None
    ages = {}
    for leg, iso in last_seen.items():
        dt = inv._parse_capture_ts(iso)
        ages[leg] = None if dt is None else (now - dt).total_seconds() / 3600.0
    alive = sorted(l for l, a in ages.items() if a is not None and a < inv.DEAD_LEG_ALIVE_HOURS)
    silent = [l for l in inv.DEAD_LEG_MONITORED
              if l not in last_seen
              or (ages.get(l) is not None and ages[l] >= inv.DEAD_LEG_SILENCE_HOURS)]
    if not silent:
        return None
    if len(silent) == len(inv.DEAD_LEG_MONITORED):
        return {"status": "ambiguous", "alive": alive, "silent": silent}
    if not alive:
        return None
    return {"status": "dead_leg", "dead": silent[0], "alive": alive, "silent": silent,
            "dead_silence_h": ages.get(silent[0])}


def test_l272_pre_fix_shape_suppressed_the_advisory_entirely(tmp_path):
    """The defect, pinned: the shipped one-reading computation returns None on this tape."""
    _l272_counterexample(tmp_path)
    assert _pre_l272_diagnosis(tmp_path, _L272_NOW) is None, (
        "if this stops being None the counterexample has rotted and the test below proves nothing")


def test_l272_counterexample_no_longer_suppresses_the_advisory(tmp_path):
    """Same tape, production default: the 106h outage is reported again — with the BURST-HONEST
    duration, not the burst-contaminated one."""
    _l272_counterexample(tmp_path)
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_L272_NOW)
    assert diag is not None, "L272: a real 106h outage must not be suppressed into silence"
    assert diag["status"] == "dead_leg"
    assert diag["dead"] == "vps"
    assert diag["alive"] == ["cloud"]
    assert diag["dead_silence_h"] == pytest.approx(106.115, abs=0.01)
    assert inv.dead_collector_leg_warning(diag).startswith(
        "COLLECTOR HEALTH ADVISORY (non-gating): the 'vps' collector leg appears DEAD.")


def test_l272_duration_and_attribution_stay_burst_excluded(tmp_path):
    """L269's half is untouched: only LIVENESS reads the inclusive scan. `last_seen`/`ages` for
    the cloud leg must still be the genuine 14.6h capture, never the 1.6h burst pass."""
    _l272_counterexample(tmp_path)
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_L272_NOW)
    assert diag["last_seen"]["cloud"] == "2026-07-29T05:53:10+00:00"
    assert diag["ages"]["cloud"] == pytest.approx(14.61, abs=0.01)
    # ...while the liveness reading (and only it) sees the burst pass.
    assert diag["alive_last_seen"]["cloud"] == _L272_BURST_CLOUD.isoformat()
    assert diag["alive_ages"]["cloud"] == pytest.approx(1.61, abs=0.01)
    assert diag["n_burst_excluded"] == 1


def test_l272_publishes_which_legs_are_alive_only_via_a_burst(tmp_path):
    """A difference nobody can see is indistinguishable from no difference (the L269
    `stats` discipline). The leg whose liveness rests solely on a burst pass is NAMED."""
    _l272_counterexample(tmp_path)
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_L272_NOW)
    assert diag["alive_only_via_burst"] == ["cloud"]
    assert diag["alive_from_burst_inclusive_scan"] is True
    msg = inv.dead_collector_leg_warning(diag)
    assert "liveness caveat (L272)" in msg
    assert "cloud" in msg


def test_l272_no_burst_contamination_means_no_liveness_caveat(tmp_path):
    """Negative control: on ordinary tape the two readings agree, `alive_only_via_burst` is
    empty, and the extra advisory line does NOT appear (no invented caveat)."""
    now = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
    _leg_series(tmp_path, 23, now - timedelta(hours=100), now - timedelta(hours=40))
    _leg_series(tmp_path, 53, now - timedelta(hours=100), now - timedelta(hours=1))
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=now)
    assert diag["alive_only_via_burst"] == []
    assert diag["alive_last_seen"] == diag["last_seen"]
    assert "liveness caveat" not in inv.dead_collector_leg_warning(diag)


def test_l272_second_scan_is_skipped_when_the_exclusion_is_off(tmp_path):
    """`exclude_burst_windows=False` means both readings are the same reading — pay for ONE
    scan, not two. (Doubling the I/O of the production path is the cost this fix does pay;
    doubling it for a caller who asked for the inclusive reading would be pure waste.)"""
    _l272_counterexample(tmp_path)
    calls = []
    real = inv._collector_leg_last_seen

    def counting(*a, **kw):
        calls.append(kw.get("exclude_burst_windows", True))
        return real(*a, **kw)

    inv._collector_leg_last_seen = counting
    try:
        inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_L272_NOW,
                                          exclude_burst_windows=False)
        assert calls == [False], calls
        calls.clear()
        inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_L272_NOW)
        assert calls == [True, False], calls
    finally:
        inv._collector_leg_last_seen = real


def test_l272_warning_renders_for_a_diag_without_the_l272_keys():
    """Back-compat: a diag built before the L272 keys existed renders exactly as it used to."""
    diag = {"status": "dead_leg", "dead": "vps", "dead_last_seen": "2026-07-22T17:29:49Z",
            "dead_silence_h": 50.0, "alive": ["cloud"], "lookback_days": 10,
            "newest_iso": "2026-07-24T19:53:00Z", "newest_age_h": 0.1,
            "last_seen": {}, "ages": {}}
    assert "liveness caveat" not in inv.dead_collector_leg_warning(diag)


def test_residual_all_captures_burst_excluded_still_returns_none(tmp_path):
    """KNOWN RESIDUAL, pinned rather than hidden.

    If EVERY capture in the horizon is burst-covered, the burst-excluded reading is empty and
    the `if not last_seen: return None` guard (a DIFFERENT guard from the one L272 closes)
    still suppresses an advisory the burst-inclusive reading would raise. Not closed by this
    fix: doing so requires deciding what "newest capture anywhere in committed hourly tape"
    means when the only candidate is a burst pass, which is a render-semantics decision that
    belongs with L273's `degraded`-status work. This test exists so the residual is a recorded,
    failing-loudly-if-it-changes fact and not a surprise for the next reader."""
    _write_capture(tmp_path, _L272_BURST_CLOUD)      # cloud, inside the burst window
    _write_capture(tmp_path, _L272_BURST_VPS)        # vps, inside the burst window
    assert inv._collector_leg_last_seen(tmp_path) == {}
    assert inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_L272_NOW) is None
    # the burst-inclusive reading DOES see both legs — this is the advisory being lost
    incl = inv._collector_leg_last_seen(tmp_path, exclude_burst_windows=False)
    assert set(incl) == {"vps", "cloud"}


# ─── L272 differential fuzz: never fewer advisories than pre-L269 ───────────

_FUZZ_AGES_H = (4, 5, 7, 12, 23, 25, 40, 106)   # straddles ALIVE=6h and SILENCE=24h


def _fuzz_tape(tape_root, vps_age_h, cloud_age_h, burst_leg):
    """Genuine captures for each leg at the requested age (placed at that leg's own
    minute-of-hour, so `collector_bucket` assigns them correctly), plus optionally ONE capture
    inside the declared fomc burst window in `burst_leg`'s bucket. Every genuine age in
    `_FUZZ_AGES_H` is >3.1h, which puts it strictly outside the padded window (17:25-20:00Z),
    so the fuzz never accidentally excludes a capture it meant to keep."""
    for age_h, minute in ((vps_age_h, 23), (cloud_age_h, 53)):
        if age_h is None:
            continue
        ts = (_L272_NOW - timedelta(hours=age_h)).replace(minute=minute, second=7, microsecond=0)
        _write_capture(tape_root, ts)
    if burst_leg == "vps":
        _write_capture(tape_root, _L272_BURST_VPS)
    elif burst_leg == "cloud":
        _write_capture(tape_root, _L272_BURST_CLOUD)


def test_fuzz_post_l272_never_raises_fewer_advisories_than_pre_l269(tmp_path):
    """THE binding property. Sweeping both legs across the ALIVE(6h)-to-SILENCE(24h) band with
    and without a burst-covered capture, the post-L272 production path must raise an advisory
    everywhere the pre-L269 code (`exclude_burst_windows=False`) raised one — never fewer. Also
    asserts the two things that must NOT regress while doing so: `alive` is byte-identical to
    the pre-L269 `alive`, and the reported silence is never SHORTER than pre-L269's (L269's
    "an outage may only look longer" direction)."""
    n_cases = n_pre_loud = n_pre_fix_suppressed = n_pre_degraded = 0
    n_pre_l273_suppressed = 0
    for i, vps_age in enumerate(_FUZZ_AGES_H):
        for j, cloud_age in enumerate(_FUZZ_AGES_H):
            for burst_leg in (None, "vps", "cloud"):
                root = tmp_path / f"c{i}_{j}_{burst_leg}"
                root.mkdir()
                _fuzz_tape(root, vps_age, cloud_age, burst_leg)
                pre = inv._dead_collector_leg_diagnosis(tape_root=root, now=_L272_NOW,
                                                        exclude_burst_windows=False)
                post = inv._dead_collector_leg_diagnosis(tape_root=root, now=_L272_NOW)
                pre_fix = _pre_l272_diagnosis(root, _L272_NOW)
                n_cases += 1
                case = (vps_age, cloud_age, burst_leg)

                if pre is not None:
                    n_pre_loud += 1
                    assert post is not None, f"L272 regression: advisory suppressed at {case}"
                    # L273 added a THIRD status to this same function, so `pre` (the production
                    # code with the exclusion switched off) is now loud in a band where the
                    # pre-L269 code was silent. Counted separately so the ORIGINAL pin below
                    # keeps its original meaning instead of being silently re-baselined.
                    if pre["status"] == "degraded":
                        n_pre_degraded += 1
                if pre is not None and pre_fix is None:
                    # The two suppressions are DIFFERENT bugs and are counted apart, so neither
                    # number can drift under cover of the other. L272's: `pre` is a full
                    # `dead_leg` (a live survivor existed) that the shipped one-reading code
                    # threw away. L273's: `pre` is the new `degraded` status, which the shipped
                    # code discarded because `alive` was empty.
                    if pre["status"] == "degraded":
                        n_pre_l273_suppressed += 1
                    else:
                        n_pre_fix_suppressed += 1

                if post is not None and pre is not None:
                    assert post["alive"] == pre["alive"], case
                    if (post["status"] == "dead_leg" == pre["status"]
                            and post["dead"] == pre["dead"]):
                        assert post["dead_silence_h"] >= pre["dead_silence_h"] - 1e-9, (
                            f"L269 direction violated at {case}")

    # Exact counts: the fixtures are fully synthetic and deterministic (no committed-tape
    # dependence), so these are equalities, not bounds — a change in any of them means the
    # sweep's meaning moved and should be re-read, not silently re-baselined.
    assert n_cases == len(_FUZZ_AGES_H) ** 2 * 3 == 192
    # 87 total, of which 18 are L273's new `degraded` status. The 69 is the ORIGINAL pin (the
    # pre-L269 loud count as it stood before L273 existed) and must not move; 87 - 18 == 69 is
    # the check that L273 ADDED a status and CHANGED none of the pre-existing ones.
    assert n_pre_loud == 87, n_pre_loud
    assert n_pre_degraded == 18, n_pre_degraded
    assert n_pre_loud - n_pre_degraded == 69, (n_pre_loud, n_pre_degraded)
    # The fuzz must actually EXERCISE the bug, otherwise the property above is vacuous:
    # 18 of the 69 cases the pre-L269 code reported were SUPPRESSED to None by the shipped
    # pre-L272 code. Those 18 are the regression, and all 18 are recovered by the fix.
    assert n_pre_fix_suppressed == 18, (
        f"expected 18 pre-L272 suppressions in the sweep, got {n_pre_fix_suppressed} — if this "
        f"is 0 the fuzz proves nothing")
    # L273's own band, disjoint from L272's by construction (L272's 18 all have a live survivor
    # and so are `dead_leg`; L273's 18 have none and so are `degraded`). 18 + 18 == 36 is the
    # total the single pre-L273 counter used to report as one undifferentiated number.
    assert n_pre_l273_suppressed == 18, n_pre_l273_suppressed
    assert n_pre_l273_suppressed == n_pre_degraded


def test_fuzz_exercises_the_bug_in_the_expected_band(tmp_path):
    """Locate the suppression precisely: it needs a leg alive ONLY via a burst pass whose
    genuine capture sits in the 6h-24h dead band (stale, not silent), plus the other leg
    genuinely silent. Outside that band the pre-L272 code was already correct — which is why
    the bug survived L269's own 10-test suite."""
    suppressed = []
    for i, vps_age in enumerate(_FUZZ_AGES_H):
        for j, cloud_age in enumerate(_FUZZ_AGES_H):
            for burst_leg in ("vps", "cloud"):
                root = tmp_path / f"c{i}_{j}_{burst_leg}"
                root.mkdir()
                _fuzz_tape(root, vps_age, cloud_age, burst_leg)
                pre = inv._dead_collector_leg_diagnosis(tape_root=root, now=_L272_NOW,
                                                        exclude_burst_windows=False)
                if pre is not None and _pre_l272_diagnosis(root, _L272_NOW) is None:
                    suppressed.append((vps_age, cloud_age, burst_leg))
    assert suppressed, "no suppression found — the counterexample has rotted"
    for vps_age, cloud_age, burst_leg in suppressed:
        burst_age = cloud_age if burst_leg == "cloud" else vps_age
        other_age = vps_age if burst_leg == "cloud" else cloud_age
        assert inv.DEAD_LEG_ALIVE_HOURS <= burst_age < inv.DEAD_LEG_SILENCE_HOURS, (
            vps_age, cloud_age, burst_leg)
        assert other_age >= inv.DEAD_LEG_SILENCE_HOURS, (vps_age, cloud_age, burst_leg)


# ─── HARD acceptance: the L272 defect on the REAL committed tape, pinned ────
#
# Pinned exactly like the L269 acceptance test above and for the same reason (L140): `max_day`
# caps the scan at CLOSED historical day-files and `now` is injected, so neither wall-clock time
# nor tape landing after the slice can move it. `datetime.now()` is never called.
#
# The slice: at 2026-07-29T23:59Z, capped at dt=2026-07-29, the ONLY sub-6h captures in the
# whole hourly-dual tape are inside the declared `kalshi-burst-fomc-0729` window (17:40-19:45Z,
# padded 17:25-20:00Z). So on the burst-EXCLUDED reading nothing at all is "alive" — and the
# shipped pre-L272 code therefore returned None, printing NOTHING, while the vps leg had been
# dead since 2026-07-22T17:29:49Z. This is L272's counterexample occurring on real tape, not a
# constructed one.
_L272_MAX_DAY = date(2026, 7, 29)
_L272_REAL_NOW = datetime(2026, 7, 29, 23, 59, tzinfo=UTC)


@_real
def test_acceptance_real_tape_l272_slice_was_suppressed_and_is_now_reported():
    diag = inv._dead_collector_leg_diagnosis(tape_root=_REAL_TAPE, now=_L272_REAL_NOW,
                                             max_day=_L272_MAX_DAY)
    assert diag is not None, "L272: a 174h VPS outage must not be suppressed into silence"
    assert diag["status"] == "dead_leg"
    assert diag["dead"] == "vps"
    assert str(diag["dead_last_seen"]).startswith("2026-07-22T17:29:49"), diag["dead_last_seen"]
    assert diag["dead_silence_h"] == pytest.approx(174.49, abs=0.05)
    # every leg that counts as alive here does so ONLY via the fomc burst pass — which is
    # exactly why the burst-excluded reading had nothing left to call alive
    assert diag["alive_only_via_burst"] == diag["alive"] == ["cloud", "other", "vps"]
    assert diag["n_burst_excluded"] > 0
    msg = inv.dead_collector_leg_warning(diag)
    assert "'vps' collector leg appears DEAD" in msg
    assert "liveness caveat (L272)" in msg
    # the dead leg is never listed as its own survivor, even though it is in `alive`
    assert "still alive: cloud, other (" in msg


@_real
def test_acceptance_real_tape_l272_slice_the_shipped_code_printed_nothing():
    """The other half of the acceptance pair: on this SAME real slice the pre-L272 computation
    (one burst-excluded reading feeding both halves) returns None. Without this, the test above
    could pass on tape where there was never anything to suppress."""
    assert _pre_l272_diagnosis(_REAL_TAPE, _L272_REAL_NOW, max_day=_L272_MAX_DAY) is None
    # ...and it is NOT that the pre-L269 code would have caught it either: the burst-inclusive
    # reading puts vps at ~5.5h (the burst pass), so pre-L269 called the leg healthy. The outage
    # is visible ONLY with L269's duration fix AND L272's liveness fix together.
    pre_l269 = inv._dead_collector_leg_diagnosis(tape_root=_REAL_TAPE, now=_L272_REAL_NOW,
                                                 max_day=_L272_MAX_DAY,
                                                 exclude_burst_windows=False)
    assert pre_l269 is None


# ─── L273: the blind band — silent legs, no live survivor, and NO advisory ──
#
# `_dead_collector_leg_diagnosis` used to `return None` whenever `alive` was empty, even when a
# leg had been silent well past DEAD_LEG_SILENCE_HOURS. Because `alive` empties out precisely
# when the WHOLE pipeline slows down, the guard fired more often the worse things got: a broad
# degradation printed NOTHING while a narrow one printed a full `dead_leg` block. That is
# backwards for anyone watching a pager.
#
# L273's fix keeps the attribution discipline the guard was protecting (with no live survivor
# there is no proof the pipe/repo/venue are fine, so naming ONE leg as the cause would be an
# accusation the data does not support) and drops only the silence: a THIRD status, `degraded`,
# states the measured silences as facts and names no culprit. No `dead` key is set.
#
# Scope note (what this does NOT change): `ambiguous` (ALL legs silent) still wins, `dead_leg`
# (a genuine live survivor) still wins, and "no leg silent at all" still returns None. The
# negative controls below pin each of those, because a status that fires when it should not is
# worse than the silence it replaced.


def _pre_l273_diagnosis(tape_root, now, **kw):
    """The SHIPPED pre-L273 computation, frozen: identical to production except that the empty
    -`alive` band returns None. Keeps the defect demonstrable forever, exactly the way L269 kept
    its own defect reproducible via `exclude_burst_windows=False` and L272 via
    `_pre_l272_diagnosis`."""
    diag = inv._dead_collector_leg_diagnosis(tape_root=tape_root, now=now, **kw)
    if diag is not None and diag.get("status") == "degraded":
        return None
    return diag


def _l273_band(tape_root: pathlib.Path, now: datetime) -> None:
    """The band, in tape form: vps genuinely dead (50h), cloud stale-but-not-silent (12h, i.e.
    past ALIVE=6h and short of SILENCE=24h). So `silent` is a strict subset of the monitored
    legs, and NOTHING is under 6h. No burst window is involved — this is the pre-existing gap,
    not L272's."""
    _leg_series(tape_root, 23, now - timedelta(hours=120), now - timedelta(hours=50))
    _leg_series(tape_root, 53, now - timedelta(hours=120), now - timedelta(hours=12))


_L273_NOW = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)


def test_l273_pre_fix_shape_printed_nothing_at_all(tmp_path):
    """The defect, pinned: on this tape the shipped pre-L273 computation returns None while a
    50h outage is in progress. If this stops being None the counterexample has rotted and the
    test below proves nothing."""
    _l273_band(tmp_path, _L273_NOW)
    assert _pre_l273_diagnosis(tmp_path, _L273_NOW) is None


def test_l273_band_now_reports_degraded_and_names_every_silent_leg(tmp_path):
    _l273_band(tmp_path, _L273_NOW)
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_L273_NOW)
    assert diag is not None, "L273: a 50h outage must not be suppressed into silence"
    assert diag["status"] == "degraded"
    assert diag["silent"] == ["vps"]
    assert diag["alive"] == []
    # `_leg_series` walks a 3h grid at each leg's own minute-of-hour, so the last capture lands
    # slightly before the requested age — these are the exact deterministic values, not the
    # nominal 50h/12h the fixture asks for.
    assert diag["ages"]["vps"] == pytest.approx(50.61, abs=0.01)
    assert diag["ages"]["cloud"] == pytest.approx(14.11, abs=0.01)
    # the cloud leg is the reason this band exists: neither survivor nor corpse
    assert inv.DEAD_LEG_ALIVE_HOURS <= diag["ages"]["cloud"] < inv.DEAD_LEG_SILENCE_HOURS


def test_l273_degraded_never_sets_a_dead_key(tmp_path):
    """The attribution half of the old guard, preserved. `degraded` must be unmistakable from
    `dead_leg` to any consumer reading the dict, not merely to a human reading the prose."""
    _l273_band(tmp_path, _L273_NOW)
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_L273_NOW)
    assert "dead" not in diag
    assert "dead_last_seen" not in diag
    assert "dead_silence_h" not in diag


def test_l273_warning_states_the_facts_and_refuses_the_accusation(tmp_path):
    _l273_band(tmp_path, _L273_NOW)
    msg = inv.dead_collector_leg_warning(
        inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_L273_NOW))
    assert msg is not None
    assert msg.startswith("COLLECTOR HEALTH ADVISORY (non-gating): DEGRADED — ")
    # the FACTS: the silent leg is named, with its measured silence
    assert "  - vps: last seen " in msg
    assert "(50.6h of silence)" in msg
    # the REFUSAL: no accusation, no dead-leg verdict, no AMBIGUOUS mislabel
    assert "accuses nobody" in msg
    assert "appears DEAD" not in msg
    # the prose CITES the AMBIGUOUS discipline; it must not RENDER as the AMBIGUOUS verdict
    assert "(non-gating): AMBIGUOUS" not in msg
    assert "the same discipline as the AMBIGUOUS case" in msg
    # ...and it still says it cannot change the exit code
    assert "does NOT affect the exit code" in msg


def test_l273_warning_shows_the_stale_but_not_silent_leg_too(tmp_path):
    """The cloud leg at 12h is the REASON this band exists (neither survivor nor corpse), so
    leaving it out of the render would hide the very thing that makes the case ambiguous."""
    _l273_band(tmp_path, _L273_NOW)
    msg = inv.dead_collector_leg_warning(
        inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_L273_NOW))
    assert "  - cloud: last seen " in msg
    assert "under the 24h silence threshold — not counted as silent" in msg
    assert "still producing within 6h: NOTHING" in msg


# --- negative controls: the new status must not steal any existing case ---

def test_l273_a_live_survivor_still_yields_dead_leg_not_degraded(tmp_path):
    """THE over-reach control. With a genuinely alive leg the attribution IS supported, so the
    stronger `dead_leg` verdict must still win."""
    _leg_series(tmp_path, 23, _L273_NOW - timedelta(hours=120), _L273_NOW - timedelta(hours=50))
    _leg_series(tmp_path, 53, _L273_NOW - timedelta(hours=120), _L273_NOW - timedelta(hours=1))
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_L273_NOW)
    assert diag["status"] == "dead_leg"
    assert diag["dead"] == "vps"


def test_l273_both_legs_silent_still_yields_ambiguous_not_degraded(tmp_path):
    """`ambiguous` returns BEFORE the empty-`alive` branch, so the both-dead case is untouched:
    `silent` must be a STRICT subset of DEAD_LEG_MONITORED for `degraded` to be reachable."""
    _leg_series(tmp_path, 23, _L273_NOW - timedelta(hours=120), _L273_NOW - timedelta(hours=50))
    _leg_series(tmp_path, 53, _L273_NOW - timedelta(hours=120), _L273_NOW - timedelta(hours=49))
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_L273_NOW)
    assert diag["status"] == "ambiguous"
    assert sorted(diag["silent"]) == ["cloud", "vps"]


def test_l273_no_silent_leg_still_returns_none_even_when_nothing_is_alive(tmp_path):
    """A merely SLOW pipeline (both legs stale at 12h, neither past 24h) is not an outage. The
    `if not silent: return None` guard runs first and `degraded` must not be invented here —
    otherwise the advisory becomes a permanent-on pager (the L270 alarm-fatigue shape)."""
    _leg_series(tmp_path, 23, _L273_NOW - timedelta(hours=120), _L273_NOW - timedelta(hours=12))
    _leg_series(tmp_path, 53, _L273_NOW - timedelta(hours=120), _L273_NOW - timedelta(hours=13))
    assert inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_L273_NOW) is None


def test_l273_healthy_tape_still_returns_none(tmp_path):
    """Trivial control, stated anyway: a healthy pipeline stays silent."""
    _leg_series(tmp_path, 23, _L273_NOW - timedelta(hours=72), _L273_NOW - timedelta(hours=1))
    _leg_series(tmp_path, 53, _L273_NOW - timedelta(hours=72), _L273_NOW - timedelta(hours=2))
    assert inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_L273_NOW) is None


def test_l273_warning_renders_for_a_degraded_diag_without_the_optional_keys():
    """A degraded diag built by a caller/fixture that predates the L269/L272 provenance keys
    must render without a KeyError and without inventing a number (same contract the L269 and
    L272 render branches carry)."""
    msg = inv.dead_collector_leg_warning({
        "status": "degraded", "silent": ["vps"], "alive": [], "lookback_days": 10,
        "newest_iso": "2026-07-25T05:53:00Z", "newest_age_h": 12.1,
        "last_seen": {}, "ages": {},
    })
    assert "DEGRADED" in msg
    assert "NO capture at all in the last 10 day-files" in msg
    assert "excluded from this reading" not in msg
    assert "liveness caveat" not in msg


def test_l273_degraded_advisory_is_still_non_gating(monkeypatch, capsys):
    """The whole point of this advisory class: it may never touch the exit code. Pinned for the
    NEW status specifically, not inferred from the old ones."""
    _stub_expensive_checks(monkeypatch)
    monkeypatch.setattr(inv, "_dead_collector_leg_diagnosis", lambda *a, **k: {
        "status": "degraded", "silent": ["vps"], "alive": [], "lookback_days": 10,
        "newest_iso": "2026-07-25T05:53:00Z", "newest_age_h": 12.1,
        "last_seen": {"vps": "2026-07-23T04:23:00Z"}, "ages": {"vps": 50.0},
    })
    assert _run_main(monkeypatch) == 0
    assert "DEGRADED" in capsys.readouterr().err


# ─── HARD acceptance: the L273 blind band on the REAL committed tape ────────
#
# Pinned exactly like the L269/L272 acceptance tests and for the same reason (L140): `max_day`
# caps the scan at CLOSED historical day-files and `now` is injected, so neither wall-clock time
# nor tape landing after the slice can move it. `datetime.now()` is never called.
#
# The slice: capped at dt=2026-08-01 and read at 2026-08-02T12:00Z, the vps leg's last honest
# (burst-excluded) capture is 2026-07-22T17:29:49Z — 258.5h, over TEN DAYS silent — while the
# cloud leg's last capture is 2026-08-01T21:55:26Z, i.e. 14.1h: past ALIVE=6h, short of
# SILENCE=24h. So cloud is neither a survivor nor a corpse, `alive` is empty, and the shipped
# pre-L273 code printed NOTHING about a ten-day outage. This is the L273 band occurring on real
# committed tape, not a constructed fixture.
#
# NOTE on the lesson row's own suggested pin: L273 names 2026-08-03T10:36:00Z as the qualifying
# instant. That reproduces on the LIVE (unpinned) scan as it stood when the row was written, but
# NOT at `max_day=2026-08-01`, where the cloud leg is 36.7h old and both legs are therefore
# silent — that combination lands in `ambiguous`, not this band. The pin below was re-derived
# against the tape rather than copied, and the whole of 2026-08-02T04:02Z..21:55Z qualifies.
_L273_MAX_DAY = date(2026, 8, 1)
_L273_REAL_NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


@_real
def test_acceptance_real_tape_l273_band_is_now_reported():
    diag = inv._dead_collector_leg_diagnosis(tape_root=_REAL_TAPE, now=_L273_REAL_NOW,
                                             max_day=_L273_MAX_DAY)
    assert diag is not None, "L273: a 258h VPS outage must not be suppressed into silence"
    assert diag["status"] == "degraded"
    assert diag["silent"] == ["vps"]
    assert diag["alive"] == []
    assert str(diag["last_seen"]["vps"]).startswith("2026-07-22T17:29:49"), diag["last_seen"]
    assert diag["ages"]["vps"] == pytest.approx(258.50, abs=0.05)
    # the leg that is neither survivor nor corpse — the reason this band exists at all
    assert inv.DEAD_LEG_ALIVE_HOURS <= diag["ages"]["cloud"] < inv.DEAD_LEG_SILENCE_HOURS
    msg = inv.dead_collector_leg_warning(diag)
    assert "DEGRADED" in msg and "accuses nobody" in msg
    assert "appears DEAD" not in msg


@_real
def test_acceptance_real_tape_l273_slice_the_shipped_code_printed_nothing():
    """The other half of the acceptance pair: on this SAME real slice the pre-L273 computation
    returns None. Without this, the test above could pass on tape where there was never anything
    to suppress. Both the burst-excluded (production) and burst-inclusive (pre-L269) readings
    were silent here, so this outage was invisible to EVERY shipped version of the advisory."""
    assert _pre_l273_diagnosis(_REAL_TAPE, _L273_REAL_NOW, max_day=_L273_MAX_DAY) is None
    pre_l269 = inv._dead_collector_leg_diagnosis(tape_root=_REAL_TAPE, now=_L273_REAL_NOW,
                                                 max_day=_L273_MAX_DAY,
                                                 exclude_burst_windows=False)
    # pre-L269 also saw a silent vps leg here (the fomc burst pass is 82.5h old at this
    # instant, itself past the 24h threshold), and it too had no survivor -> also None.
    assert _pre_l273_diagnosis(_REAL_TAPE, _L273_REAL_NOW, max_day=_L273_MAX_DAY,
                               exclude_burst_windows=False) is None
    assert pre_l269 is not None and pre_l269["status"] == "degraded"
