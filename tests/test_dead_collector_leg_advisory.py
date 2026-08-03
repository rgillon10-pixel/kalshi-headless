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
import re
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


# ─── L269: a DECLARED BURST pass must not stand in for a genuine leg pass ───
#
# A burst trigger deliberately re-fires the collectors every 60-120s inside its declared window
# (LOOP-QUEUE.md "Burst-capture legs"), from whatever machine ran it. One such pass landing in a
# leg's minute bucket used to reset that leg's apparent freshness for the WHOLE hourly-dual
# family set, masking a real, longer, family-specific death (L269, measured on the live tree
# 2026-08-03: the `vps` leg read 110.7h silent from a `kalshi-burst-fomc-0729` capture).
#
# RETRACTION (read this before the tests below). This block used to assert, citing
# `test_burst_exclusion_can_only_make_a_leg_look_older_L269`, that the exclusion is a strict
# tightening and therefore "the advisory can only get LOUDER, never quieter". THAT SENTENCE IS
# RETRACTED. Two independent verifier passes on 2026-08-03 each refuted a version of it:
#   * pass #1 (L272) refuted it at the DECISION level — the 6-24h `DEAD_LEG_ALIVE_HOURS` /
#     `DEAD_LEG_SILENCE_HOURS` gap let an older reading drop a leg out of `alive` without
#     putting it into `silent`, so `if not alive: return None` hid a 106.6h outage;
#   * pass #2 (L274) refuted the RESTATED version at the RENDERED-TEXT level — emptying the dead
#     leg's scheduled reading made `dead_silence_h` `None`, which used to print `>10 days` where
#     pre-L269 printed `447.6h`: monotone as data, a SHORTER outage as text.
# What survives, and all that survives, is the MEASUREMENT-level fact that
# `test_burst_exclusion_can_only_make_a_leg_look_older_L269` actually asserts: excluding
# captures can only move a leg's `last_seen` OLDER, never newer, and every failure path falls
# back to the old (non-excluding) behaviour rather than to a fabricated outage. The decision-
# level property is pinned by `test_l272_*` and the text-level property by `test_l274_*`; both
# had to be built in CODE, neither follows from the sentence above.

_BURST_FAMILY = "crypto_hourly"        # covered by kalshi-burst-fomc-0729 (`crypto` burst key)
_NON_BURST_FAMILY = "perp_tape"        # hourly-dual, covered by NO declared trigger
# A vps-bucket (minute 20-29) instant INSIDE the declared FOMC window, and a genuine vps-bucket
# pass a week earlier. Both are real shapes from the live tree.
_FOMC_BURST_TS = datetime(2026, 7, 29, 18, 29, 45, tzinfo=UTC)
_GENUINE_VPS_TS = datetime(2026, 7, 22, 17, 29, 49, tzinfo=UTC)


def _fomc_window():
    """The declared, padded window covering `_BURST_FAMILY` on 2026-07-29 — DERIVED from
    tape_gap_monitor (never re-transcribed here, same reason the production code delegates)."""
    tgm = inv._load_tape_gap_monitor()
    wins = [w for w in tgm._burst_windows_for_family(_BURST_FAMILY)
            if w[0].date() == date(2026, 7, 29)]
    assert len(wins) == 1, wins
    return wins[0]


def test_burst_window_capture_is_excluded_for_a_burst_covered_family_L269(tmp_path):
    """The defect, in miniature: a burst pass in the vps bucket used to become the leg's
    last_seen. With the fix the leg reports its last GENUINE pass instead."""
    _write_capture(tmp_path, _GENUINE_VPS_TS, _BURST_FAMILY)
    _write_capture(tmp_path, _FOMC_BURST_TS, _BURST_FAMILY)
    fixed = inv._collector_leg_last_seen(tmp_path)
    assert fixed["vps"] == _GENUINE_VPS_TS.isoformat()
    # ...and the pre-L269 reading is still reachable, so the two can be compared in one run.
    old = inv._collector_leg_last_seen(tmp_path, exclude_burst_windows=False)
    assert old["vps"] == _FOMC_BURST_TS.isoformat()
    assert fixed["vps"] < old["vps"]


def test_same_timestamp_in_a_non_burst_covered_family_is_kept_L269(tmp_path):
    """The exclusion is per FAMILY, not per instant: `perp_tape` is covered by no declared
    trigger, so the identical timestamp is real evidence the leg ran and must be KEPT."""
    _write_capture(tmp_path, _GENUINE_VPS_TS, _NON_BURST_FAMILY)
    _write_capture(tmp_path, _FOMC_BURST_TS, _NON_BURST_FAMILY)
    assert inv._collector_leg_last_seen(tmp_path)["vps"] == _FOMC_BURST_TS.isoformat()


def test_family_with_no_declared_window_is_untouched_by_the_fix_L269(tmp_path):
    """Whole-dict equality for a non-burst family: the fix changes NOTHING where no window is
    declared (it is not a blanket 'drop old captures' rule)."""
    _leg_series(tmp_path, 23, datetime(2026, 7, 20, 0, 0, tzinfo=UTC),
                datetime(2026, 7, 29, 21, 0, tzinfo=UTC))
    for p in (tmp_path / FAMILY).glob("dt=*.jsonl"):   # re-home the series to a non-burst family
        (tmp_path / _NON_BURST_FAMILY).mkdir(parents=True, exist_ok=True)
        p.rename(tmp_path / _NON_BURST_FAMILY / p.name)
    assert (inv._collector_leg_last_seen(tmp_path)
            == inv._collector_leg_last_seen(tmp_path, exclude_burst_windows=False))


def test_burst_window_pad_boundary_is_inclusive_and_one_second_outside_is_kept_L269(tmp_path):
    """The pad boundary (BURST_WINDOW_PAD_S ahead of the declared start) behaves: a capture AT
    the padded lower bound is excluded, one second earlier is kept. Both instants sit in the
    same vps minute bucket, so only the window test can distinguish them."""
    lo, _hi = _fomc_window()
    assert 20 <= lo.minute <= 29, lo          # guard: the boundary is inside the vps bucket
    _write_capture(tmp_path, lo, _BURST_FAMILY)
    assert "vps" not in inv._collector_leg_last_seen(tmp_path)
    just_before = lo - timedelta(seconds=1)
    _write_capture(tmp_path, just_before, _BURST_FAMILY)
    assert inv._collector_leg_last_seen(tmp_path)["vps"] == just_before.isoformat()


def test_burst_exclusion_can_only_make_a_leg_look_older_L269(tmp_path):
    """DIRECTION-OF-BIAS pin, SCOPED TO THE MEASUREMENT (L272): for EVERY leg, the fixed
    reading is older-or-equal to the pre-L269 reading.

    This test pins `_collector_leg_last_seen` and NOTHING ELSE. It does NOT establish that the
    advisory can never be suppressed — an independent verifier refuted that stronger reading on
    2026-08-03 by driving `_dead_collector_leg_diagnosis`'s `if not alive: return None` branch
    with exactly the monotone readings this test blesses. The decision-level property is pinned
    separately by `test_l272_*` below; do not re-broaden this docstring to cover it."""
    _write_capture(tmp_path, _GENUINE_VPS_TS, _BURST_FAMILY)
    _write_capture(tmp_path, _FOMC_BURST_TS, _BURST_FAMILY)
    _write_capture(tmp_path, datetime(2026, 7, 29, 18, 53, 2, tzinfo=UTC), _BURST_FAMILY)  # cloud
    _write_capture(tmp_path, datetime(2026, 7, 30, 9, 53, 2, tzinfo=UTC), _NON_BURST_FAMILY)
    fixed = inv._collector_leg_last_seen(tmp_path)
    old = inv._collector_leg_last_seen(tmp_path, exclude_burst_windows=False)
    assert set(fixed) <= set(old)                      # a leg can vanish, never appear
    for leg, iso in fixed.items():
        assert iso <= old[leg], (leg, iso, old[leg])


def test_burst_window_lookup_degrades_to_no_exclusion_when_unavailable_L269():
    """Fallback contract: if the monitor lacks the helper, or it raises, the lookup yields []
    (= today's pre-L269 behaviour) instead of crashing the advisory or inventing an outage."""
    class _NoHelper:
        pass

    class _Raises:
        @staticmethod
        def _burst_windows_for_family(_family):
            raise RuntimeError("boom")

    assert inv._burst_windows_for_family_safe(_NoHelper, _BURST_FAMILY) == []
    assert inv._burst_windows_for_family_safe(_Raises, _BURST_FAMILY) == []
    assert inv._burst_windows_for_family_safe(None, _BURST_FAMILY) == []


def test_fallback_path_yields_the_pre_l269_reading_not_a_crash_L269(tmp_path, monkeypatch):
    """End-to-end degraded run: with the window lookup neutered, the scan still completes and
    returns exactly the old reading — the failure direction is 'quieter', never 'broken'."""
    _write_capture(tmp_path, _GENUINE_VPS_TS, _BURST_FAMILY)
    _write_capture(tmp_path, _FOMC_BURST_TS, _BURST_FAMILY)
    monkeypatch.setattr(inv, "_burst_windows_for_family_safe", lambda *a, **k: [])
    assert (inv._collector_leg_last_seen(tmp_path)
            == {"vps": _FOMC_BURST_TS.isoformat()})


def test_burst_windows_are_delegated_not_re_transcribed_L269():
    """One home for the windows table (scripts/tape_gap_monitor.py). A second copy in
    invariants.py would desync — the exact failure class this fix exists to avoid."""
    src = (ROOT / "scripts" / "invariants.py").read_text(encoding="utf-8")
    assert "_burst_windows_for_family" in src
    assert "BURST_TRIGGER_WINDOWS: Dict" not in src
    # No transcribed table: a copy would carry QUOTED trigger ids / window bounds / a pad
    # constant. (The trigger id appears in this file only as backticked prose evidence.)
    assert '"kalshi-burst-' not in src and "'kalshi-burst-" not in src
    assert '"window_start"' not in src and "BURST_WINDOW_PAD_S: float" not in src
    assert "burst_keys" not in src


# ─── L272: the DECISION-level guard (verifier-derived regression) ───────────────
# Provenance: every test in this block descends from a counterexample built by an INDEPENDENT
# verifier agent on 2026-08-03 (`/tmp/verif/counterexample.py`, scratch — not a repo path),
# which REFUTED the original L269 claim that the burst exclusion "can never suppress a real
# alarm". It drove the UNMODIFIED production code into `if not alive: return None` and hid a
# 106.6h outage that the pre-L269 code reported. L272 is the guard that closed it: liveness
# reads burst-INCLUDED, attribution/duration reads burst-EXCLUDED. These tests exist so that
# exact scenario can never silently regress.


def _pre_l269_diagnosis(monkeypatch, *args, **kwargs):
    """Run `_dead_collector_leg_diagnosis` with the L269 exclusion forced OFF everywhere — the
    genuine pre-L269 behaviour — so post-fix and pre-fix decisions are comparable in one run."""
    orig = inv._collector_leg_last_seen
    monkeypatch.setattr(inv, "_collector_leg_last_seen",
                        lambda *a, **kw: orig(*a, **{**kw, "exclude_burst_windows": False}))
    try:
        return inv._dead_collector_leg_diagnosis(*args, **kwargs)
    finally:
        monkeypatch.undo()


def _counterexample_tape(tape_root):
    """The verifier's fixture, verbatim: a genuinely dead vps leg, a cloud leg whose last
    GENUINE pass is 10.1h old (inside the 6-24h band), and a cloud-bucket burst pass 3.1h old
    inside the declared FOMC window. Burst-covered family, so the exclusion bites."""
    _write_capture(tape_root, datetime(2026, 7, 25, 10, 23, tzinfo=UTC), _BURST_FAMILY)
    _write_capture(tape_root, datetime(2026, 7, 29, 10, 53, tzinfo=UTC), _BURST_FAMILY)
    _write_capture(tape_root, datetime(2026, 7, 29, 17, 53, tzinfo=UTC), _BURST_FAMILY)
    return datetime(2026, 7, 29, 21, 0, tzinfo=UTC)


def test_l272_verifier_counterexample_still_reports_the_outage(tmp_path, monkeypatch):
    """THE regression: the exact scenario in which the pre-L272 fix went SILENT. The advisory
    must be printed, must name `vps`, and must quote the HONEST 106.6h duration."""
    now = _counterexample_tape(tmp_path)
    diag = inv._dead_collector_leg_diagnosis(tmp_path, now=now, lookback_days=10)
    assert diag is not None, "the verifier's 106.6h outage went silent again"
    assert diag["status"] == "dead_leg"
    assert diag["dead"] == "vps"
    assert diag["alive"] == ["cloud"]          # liveness counts the burst pass (L272)
    assert 106.0 < diag["dead_silence_h"] < 107.0
    text = inv.dead_collector_leg_warning(diag)
    assert text and "the 'vps' collector leg appears DEAD" in text


def test_l272_counterexample_decision_matches_the_pre_l269_decision(tmp_path, monkeypatch):
    """Pre-L269 and post-L272 must reach the SAME decision here — the fix buys a more honest
    duration, it does not buy silence. (Pre-L272 this asserted dead_leg vs None.)"""
    now = _counterexample_tape(tmp_path)
    pre = _pre_l269_diagnosis(monkeypatch, tmp_path, now=now, lookback_days=10)
    post = inv._dead_collector_leg_diagnosis(tmp_path, now=now, lookback_days=10)
    assert pre is not None and post is not None
    assert (pre["status"], pre["dead"]) == (post["status"], post["dead"]) == ("dead_leg", "vps")
    # The vps leg has no burst pass of its own, so its duration is identical in both readings.
    assert pre["dead_silence_h"] == post["dead_silence_h"]


def test_l272_liveness_reads_burst_included_attribution_reads_burst_excluded(tmp_path):
    """The split itself, pinned at the two fields that carry it: `alive` (liveness) sees the
    burst pass; `last_seen`/`ages` (attribution) do not."""
    now = _counterexample_tape(tmp_path)
    diag = inv._dead_collector_leg_diagnosis(tmp_path, now=now, lookback_days=10)
    assert diag["last_seen"]["cloud"] == "2026-07-29T10:53:00+00:00"          # excluded
    assert diag["last_seen_incl_burst"]["cloud"] == "2026-07-29T17:53:00+00:00"  # included
    # The band that made the hole: cloud is NOT alive by the excluded reading (10.1h > 6h)...
    assert diag["ages"]["cloud"] > inv.DEAD_LEG_ALIVE_HOURS
    # ...but IS alive by the included reading (3.1h < 6h), which is what keeps the alarm up.
    assert diag["ages_incl_burst"]["cloud"] < inv.DEAD_LEG_ALIVE_HOURS
    assert "cloud" in diag["alive"] and "cloud" not in diag["silent"]


def test_l272_a_burst_only_leg_is_still_counted_silent_not_cleared(tmp_path):
    """The other half of the split: a burst pass may establish LIVENESS but must never clear a
    leg of being silent, nor shorten its outage. Both legs burst-only => AMBIGUOUS, not None,
    and the leg line says why rather than claiming nothing was written."""
    _write_capture(tmp_path, datetime(2026, 7, 29, 18, 29, 45, tzinfo=UTC), _BURST_FAMILY)
    _write_capture(tmp_path, datetime(2026, 7, 29, 18, 53, 2, tzinfo=UTC), _BURST_FAMILY)
    now = datetime(2026, 7, 29, 21, 0, tzinfo=UTC)
    diag = inv._dead_collector_leg_diagnosis(tmp_path, now=now, lookback_days=10)
    assert diag is not None and diag["status"] == "ambiguous"
    assert sorted(diag["silent"]) == sorted(inv.DEAD_LEG_MONITORED)
    assert diag["last_seen"] == {}                       # nothing survives the exclusion
    assert set(diag["alive"]) == {"vps", "cloud"}        # but the pipe is demonstrably up
    text = inv.dead_collector_leg_warning(diag)
    assert "falls inside a DECLARED burst window" in text
    assert "NO capture at all" not in text               # would be a lie: lines WERE written


def test_l272_empty_excluded_reading_does_not_crash_or_go_silent(tmp_path):
    """Guard on the `max(())` edge the split introduced: when EVERY capture in the window is a
    burst pass, `last_seen` is empty. That must report, not raise and not return None."""
    _write_capture(tmp_path, datetime(2026, 7, 29, 18, 29, 45, tzinfo=UTC), _BURST_FAMILY)
    now = datetime(2026, 7, 29, 21, 0, tzinfo=UTC)
    diag = inv._dead_collector_leg_diagnosis(tmp_path, now=now, lookback_days=10)
    assert diag is not None
    assert diag["newest_iso"] == "2026-07-29T18:29:45+00:00"   # falls back, stays honest
    assert isinstance(inv.dead_collector_leg_warning(diag), str)


def test_l272_diagnosis_is_never_quieter_than_pre_l269_on_a_sweep(tmp_path, monkeypatch):
    """The DECISION-level direction-of-bias claim, asserted where the decision is made (L272).

    Sweeps the whole 6-24h band that produced the counterexample: for every instant, if the
    pre-L269 code produced an advisory then the post-L272 code must produce one too, and the
    named leg's reported outage may only be LONGER-or-equal. This is the assert the original
    `test_burst_exclusion_can_only_make_a_leg_look_older_L269` could not make.

    SCOPE, AND A KNOWN LIMIT OF THIS FIXTURE (L276, recorded by the second verifier pass): this
    sweeps `now` over ONE tape SHAPE, in which the dead leg's own last pass is genuine. That
    shape can never produce `dead_silence_h is None`, so the one branch where the property does
    fail is UNREACHABLE from here — and the property is asserted on the diagnosis DICT, which is
    not what a human reads. Both gaps are covered by
    `test_l274_rendered_outage_is_never_shorter_than_pre_l269_on_a_sweep` below, which sweeps
    the tape SHAPE as well and asserts on the rendered string. Do not treat this test as
    covering either; that mistake is precisely what L274/L276 record."""
    _counterexample_tape(tmp_path)
    checked = 0
    for hours in range(0, 60):
        now = datetime(2026, 7, 29, 18, 0, tzinfo=UTC) + timedelta(hours=hours)
        pre = _pre_l269_diagnosis(monkeypatch, tmp_path, now=now, lookback_days=10)
        post = inv._dead_collector_leg_diagnosis(tmp_path, now=now, lookback_days=10)
        if pre is None:
            continue
        checked += 1
        assert post is not None, f"advisory went SILENT at {now.isoformat()} (pre said {pre['status']})"
        if pre.get("status") == "dead_leg" and post.get("status") == "dead_leg":
            assert post["dead"] == pre["dead"]
            assert post["dead_silence_h"] >= pre["dead_silence_h"] - 1e-9
    assert checked >= 20, f"sweep never exercised the pre-L269 advisory (checked={checked})"


# ─── L274/L276: the RENDERED-TEXT direction-of-bias claim, swept over TAPE SHAPES ───────
# Provenance: a SECOND independent verifier pass on 2026-08-03 confirmed the L272 fix closed the
# decision-level hole (8,000 differential cases: zero lost advisories, zero shortened
# `dead_silence_h`) and then refuted the RESTATED sentence one level up, at the PRODUCTION
# default `lookback_days=10`, with unmodified production code:
#
#     PRE-L269 : - last capture written by it: 2026-07-15T20:23:00+00:00
#                - silent for: 447.6h (threshold: 24h)
#     PRE-L274 : - last capture written by it: not within the last 10 day-files
#                - silent for: >10 days (threshold: 24h)      <-- 240h < 447.6h
#
# `dead_silence_h: None` is monotone-safe as DATA and monotone-UNSAFE as TEXT. The block below
# asserts the property where the human reads it, and sweeps the tape SHAPE — the previous sweep's
# fixture could not reach the `dead_silence_h is None` branch at all (L276).

_SILENT_FOR_RE = re.compile(r"- silent for: (>=|>)?\s*([0-9.]+)\s*(h|days) \(threshold:")


def _claimed_outage_h(text: str) -> float | None:
    """How many hours of silence the RENDERED dead-leg advisory claims, read as a human reads
    it: `447.6h` -> 447.6, `>=447.6h` -> 447.6 ("at least this"), `>10 days` -> 240.0. None when
    the text carries no dead-leg silence line (e.g. an AMBIGUOUS block)."""
    m = _SILENT_FOR_RE.search(text or "")
    if m is None:
        return None
    value = float(m.group(2))
    return value * 24.0 if m.group(3) == "days" else value


def _shape_dead_legs_last_pass_is_genuine(root: pathlib.Path) -> None:
    """Verifier pass #1's fixture: the DEAD leg's own last pass is genuine (in no declared
    window); only the SURVIVOR's freshness is burst-contaminated."""
    _counterexample_tape(root)


def _shape_dead_legs_only_pass_is_a_BURST_pass(root: pathlib.Path) -> None:
    """Verifier pass #2's shape — THE one the previous sweep could not reach. The dead leg's
    only capture inside the lookback is itself a declared burst pass, so the L269 exclusion
    EMPTIES its reading and `dead_silence_h` becomes None. The burst-covered family is otherwise
    frozen (one day-file), exactly like the real `polymarket_pairs`, so the excluded instant is
    OLDER than `lookback_days * 24h` — which is what makes `">10 days"` a strictly weaker claim
    than the timestamp it replaced."""
    _write_capture(root, _FOMC_BURST_TS, _BURST_FAMILY)                    # vps bucket, in-window
    t = datetime(2026, 8, 14, 0, 53, tzinfo=UTC)                           # cloud, genuine, fresh
    while t <= datetime(2026, 8, 18, 0, 53, tzinfo=UTC):
        _write_capture(root, t, _NON_BURST_FAMILY)
        t += timedelta(hours=3)


def _shape_both_legs_burst_only(root: pathlib.Path) -> None:
    """Both legs' only captures are burst passes: the exclusion empties BOTH readings."""
    _write_capture(root, _FOMC_BURST_TS, _BURST_FAMILY)
    _write_capture(root, datetime(2026, 7, 29, 18, 53, 2, tzinfo=UTC), _BURST_FAMILY)


def _shape_no_declared_window_control(root: pathlib.Path) -> None:
    """Control: a family covered by NO declared trigger. Post must equal pre, textually."""
    _write_capture(root, _GENUINE_VPS_TS, _NON_BURST_FAMILY)
    t = datetime(2026, 7, 28, 0, 53, tzinfo=UTC)
    while t <= datetime(2026, 8, 1, 0, 53, tzinfo=UTC):
        _write_capture(root, t, _NON_BURST_FAMILY)
        t += timedelta(hours=3)


_RENDER_SWEEP_SHAPES = [
    (_shape_dead_legs_last_pass_is_genuine, datetime(2026, 7, 29, 18, 0, tzinfo=UTC)),
    (_shape_dead_legs_only_pass_is_a_BURST_pass, datetime(2026, 8, 15, 0, 0, tzinfo=UTC)),
    (_shape_both_legs_burst_only, datetime(2026, 7, 29, 21, 0, tzinfo=UTC)),
    (_shape_no_declared_window_control, datetime(2026, 8, 1, 0, 0, tzinfo=UTC)),
]


def test_l274_rendered_outage_is_never_shorter_than_pre_l269_on_a_sweep(tmp_path, monkeypatch):
    """THE L274 regression: over four tape SHAPES x 60 instants each, at the PRODUCTION default
    `lookback_days=10`, the RENDERED advisory may never make a weaker claim about an outage than
    the pre-L269 code made from the same tape:

      1. pre printed a block  =>  post prints a block (the L272 property, re-asserted on text);
      2. both name the same dead leg  =>  post's CLAIMED silence >= pre's claimed silence;
      3. pre printed a concrete last-seen instant for the dead leg  =>  post must NOT fall back
         to "not within the last N day-files" (discarding the instant is itself a weaker claim).

    VERIFIED to fail on the pre-L274 tree (renderer reverted, everything else identical):
    `shape 1 at 2026-08-15T00:00:00+00:00: the RENDERED outage SHRANK, 389.5h -> 240.0h`."""
    reached_none = 0
    checked = 0
    for i, (build, t0) in enumerate(_RENDER_SWEEP_SHAPES):
        root = tmp_path / f"shape{i}"
        build(root)
        for hours in range(0, 60):
            now = t0 + timedelta(hours=hours)
            pre = _pre_l269_diagnosis(monkeypatch, root, now=now, lookback_days=10)
            post = inv._dead_collector_leg_diagnosis(root, now=now, lookback_days=10)
            pre_text = inv.dead_collector_leg_warning(pre)
            post_text = inv.dead_collector_leg_warning(post)
            if not pre_text:
                continue
            checked += 1
            assert post_text, (f"advisory text went SILENT at {now.isoformat()} on shape {i} "
                               f"(pre said: {pre_text.splitlines()[0]})")
            if post is not None and post.get("dead_silence_h") is None \
                    and post.get("status") == "dead_leg":
                reached_none += 1
            if not (pre.get("status") == post.get("status") == "dead_leg"
                    and pre.get("dead") == post.get("dead")):
                continue
            pre_h = _claimed_outage_h(pre_text)
            post_h = _claimed_outage_h(post_text)
            assert pre_h is not None and post_h is not None, (pre_text, post_text)
            # 0.05h tolerance = the rendered `.1f` rounding, nothing more (L162: the number
            # compared is the one a HUMAN reads, so it is compared at the printed precision).
            assert post_h >= pre_h - 0.05, (
                f"shape {i} at {now.isoformat()}: the RENDERED outage SHRANK, "
                f"{pre_h}h -> {post_h}h\nPRE:\n{pre_text}\nPOST:\n{post_text}")
            if pre.get("dead_last_seen") is not None:
                assert "not within the last 10 day-files" not in post_text, (
                    f"shape {i} at {now.isoformat()}: post discarded the instant pre printed "
                    f"({pre['dead_last_seen']})\nPOST:\n{post_text}")
    # EXACT, not floors. The fixture is fully synthetic and frozen on both axes (fixed shapes,
    # fixed instants, injected `now`), so these counts cannot drift with tape or wall-clock —
    # only with an edit to the sweep itself, which is precisely what should have to be noticed.
    assert (len(_RENDER_SWEEP_SHAPES), checked) == (4, 182), (len(_RENDER_SWEEP_SHAPES), checked)
    # The whole point of sweeping the SHAPE and not just `now` (L276): the failing branch must
    # actually be entered, or this test is decoration. 60 of the 182 compared pairs enter it.
    assert reached_none == 60, (
        f"the `dead_silence_h is None` dead_leg branch was reached {reached_none}x, expected 60 "
        f"— narrow this sweep's fixtures and it stops seeing the bug it exists to catch")


def test_l274_burst_only_dead_leg_renders_a_lower_bound_not_a_shorter_outage(tmp_path):
    """The minimal repro, pinned on its own: the dead leg's only capture is a declared burst
    pass in a frozen family. Pre-L269 renders `447.6h` from that instant; the corrected code
    must render a claim at LEAST that long AND keep the instant, flagged as burst-derived."""
    _shape_dead_legs_only_pass_is_a_BURST_pass(tmp_path)
    now = datetime(2026, 8, 15, 0, 0, tzinfo=UTC)
    diag = inv._dead_collector_leg_diagnosis(tmp_path, now=now, lookback_days=10)
    assert diag is not None and diag["status"] == "dead_leg" and diag["dead"] == "vps"
    assert diag["dead_silence_h"] is None          # the branch the old renderer fell through on
    text = inv.dead_collector_leg_warning(diag)
    expected_h = (now - _FOMC_BURST_TS).total_seconds() / 3600.0
    assert expected_h > 10 * 24, expected_h       # ...and it IS longer than the old ">10 days"
    assert f">={expected_h:.1f}h" in text, text
    assert _FOMC_BURST_TS.isoformat() in text     # the instant survives
    assert "DECLARED burst window" in text        # ...labelled as the lower bound it is
    assert "not within the last 10 day-files" not in text
    assert _claimed_outage_h(text) >= expected_h - 0.05 > 240.0   # 0.05h = `.1f` rounding


# ─── L273: the BLIND BAND — a KNOWN, UNFIXED limitation, pinned so it stays visible ──
# Also found by the independent verifier on 2026-08-03, and CONFIRMED PRE-EXISTING: it is NOT
# caused by L269 or L272 (both the pre-L269 and the post-L272 module return None at the live
# instant below). `_dead_collector_leg_diagnosis` reports NOTHING when no leg is fresh within
# DEAD_LEG_ALIVE_HOURS but not every leg is silent past DEAD_LEG_SILENCE_HOURS — so a FULLY
# dead pipe is silent while a HALF dead pipe alarms. These tests do NOT bless that behaviour;
# they pin its exact extent so the repair (L273's candidate) can be recognised when it lands.
# WHEN THE REPAIR IS BUILT, THESE TWO TESTS SHOULD FAIL AND BE REPLACED, NOT WEAKENED.


def test_l273_blind_band_is_silent_KNOWN_LIMITATION_not_endorsed(tmp_path):
    """The live 2026-08-03T10:36Z shape, reproduced synthetically: vps ~447h dead, cloud 6.7h
    (older than DEAD_LEG_ALIVE_HOURS=6, younger than DEAD_LEG_SILENCE_HOURS=24). A 447h outage
    is real and currently INVISIBLE. Pinned as a documented hole, not as desired behaviour."""
    now = datetime(2026, 8, 3, 10, 36, tzinfo=UTC)
    _write_capture(tmp_path, now - timedelta(hours=447), _NON_BURST_FAMILY)      # vps :29 bucket
    _write_capture(tmp_path, (now - timedelta(hours=6.7)).replace(minute=53),
                   _NON_BURST_FAMILY)                                            # cloud, in band
    diag = inv._dead_collector_leg_diagnosis(tmp_path, now=now, lookback_days=30)
    assert diag is None, "blind band repaired? then replace this test with the new contract"
    # The band is real, not a fixture artifact: the survivor sits strictly between the two
    # thresholds, which is the ONLY way this hole opens.
    ages = inv._collector_leg_last_seen(tmp_path, lookback_days=30)
    cloud_age = (now - inv._parse_capture_ts(ages["cloud"])).total_seconds() / 3600.0
    assert inv.DEAD_LEG_ALIVE_HOURS < cloud_age < inv.DEAD_LEG_SILENCE_HOURS


def test_l273_blind_band_closes_on_both_sides_so_the_gap_is_the_whole_cause(tmp_path):
    """Same tape, survivor moved to either side of the band: the advisory FIRES both times.
    That isolates the 6-24h gap itself — not the dead leg, the tape, or the exclusion — as the
    sole cause, which is what makes the repair candidate in L273 well-posed."""
    now = datetime(2026, 8, 3, 10, 36, tzinfo=UTC)
    for survivor_age_h, expected in ((2.0, "dead_leg"), (30.0, "ambiguous")):
        root = tmp_path / f"case_{survivor_age_h}"
        _write_capture(root, now - timedelta(hours=447), _NON_BURST_FAMILY)
        _write_capture(root, (now - timedelta(hours=survivor_age_h)).replace(minute=53),
                       _NON_BURST_FAMILY)
        diag = inv._dead_collector_leg_diagnosis(root, now=now, lookback_days=30)
        assert diag is not None, (survivor_age_h, "should alarm outside the band")
        assert diag["status"] == expected, (survivor_age_h, diag["status"])


# ─── HARD acceptance over the REAL committed tape (L269's own numbers) ──────

# A SECOND frozen slice, pinned separately from `_SLICE_MAX_DAY` above because L269's evidence
# lives in a later window: dt<=2026-08-01 still contains BOTH the 2026-07-29 FOMC burst pass
# (the contaminating capture) and the 2026-07-22 weather_books vps pass (the honest one). Frozen
# on both axes exactly like the slice above — `max_day` caps the files read, `now` is injected —
# so no amount of new tape or wall-clock time can flip it (L140/L191).
_L269_MAX_DAY = date(2026, 8, 1)
_L269_NOW = datetime(2026, 8, 1, 23, 0, tzinfo=UTC)
# lookback 14 (> the production default 10) so a backfilled day-file inside the slice cannot
# push the 2026-07-22 evidence out of the per-family file window; measured identical at 10/14/20
# on 2026-08-03.
_L269_LOOKBACK = 14


@_real
def test_acceptance_l269_real_tape_burst_pass_no_longer_stands_in_for_a_vps_pass():
    """L269's measured fact, re-derivable: over the frozen slice the pre-fix `vps` last_seen is
    the 2026-07-29 FOMC BURST capture; the fixed reading is the genuine 2026-07-22 pass."""
    old = inv._collector_leg_last_seen(_REAL_TAPE, lookback_days=_L269_LOOKBACK,
                                       max_day=_L269_MAX_DAY, exclude_burst_windows=False)
    fixed = inv._collector_leg_last_seen(_REAL_TAPE, lookback_days=_L269_LOOKBACK,
                                         max_day=_L269_MAX_DAY)
    assert old["vps"].startswith("2026-07-29T18:29"), old["vps"]
    # Inequality-shaped (L191): the honest pass is NO NEWER than the 2026-07-22T17:29:49Z
    # weather_books capture L269 cites, and strictly older than the contaminated reading.
    assert fixed["vps"] <= "2026-07-22T17:29:49.498224+00:00", fixed["vps"]
    assert fixed["vps"] < old["vps"]
    # ...and the reason is structural, not a coincidence of ordering: the contaminated instant
    # IS inside a declared padded burst window for a burst-covered family; the honest one is
    # inside NO declared window of ANY hourly-dual family.
    tgm = inv._load_tape_gap_monitor()
    lo, hi = _fomc_window()
    assert lo <= inv._parse_capture_ts(old["vps"]) <= hi
    honest_dt = inv._parse_capture_ts(fixed["vps"])
    families = [f for f, cfg in tgm.FAMILY_CONFIG.items() if cfg.get("kind") == "hourly-dual"]
    assert not [f for f in families
                for w_lo, w_hi in tgm._burst_windows_for_family(f)
                if w_lo <= honest_dt <= w_hi]
    # The other legs are untouched by the exclusion on this slice.
    assert fixed["cloud"] == old["cloud"]


@_real
def test_acceptance_l269_real_tape_outage_gets_longer_and_the_leg_is_still_named():
    """Second-order effect, MEASURED not assumed: on this slice the fix lengthens the reported
    vps outage by >=2.5x (L269's '2.6x understatement') while the diagnosis still NAMES the leg
    — the cloud leg is 1.1h fresh at `_L269_NOW`, so there is no dead_leg -> ambiguous flip."""
    diag = inv._dead_collector_leg_diagnosis(tape_root=_REAL_TAPE, now=_L269_NOW,
                                             lookback_days=_L269_LOOKBACK,
                                             max_day=_L269_MAX_DAY)
    assert diag is not None and diag["status"] == "dead_leg"
    assert diag["dead"] == "vps"
    assert "cloud" in diag["alive"]
    old = inv._collector_leg_last_seen(_REAL_TAPE, lookback_days=_L269_LOOKBACK,
                                       max_day=_L269_MAX_DAY, exclude_burst_windows=False)
    old_silence_h = (_L269_NOW - inv._parse_capture_ts(old["vps"])).total_seconds() / 3600.0
    assert diag["dead_silence_h"] >= 2.5 * old_silence_h, (diag["dead_silence_h"], old_silence_h)
    assert diag["dead_silence_h"] >= 240.0
    assert "2026-07-22" in inv.dead_collector_leg_warning(diag)
