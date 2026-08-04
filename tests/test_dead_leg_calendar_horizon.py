"""scripts/invariants.py — L271: the leg-scan horizon must be UNIFORM, and what it cannot see
must be a LOWER BOUND rather than a borrowed date.

The defect (kb/lessons/00-lessons.md L271, measured live 2026-08-04): `_collector_leg_last_seen`
bounded its scan to "the newest N day-FILES per family". Tape is one `dt=<day>.jsonl` per family
per day, so that window is RAGGED across families — a family writing a file most days reaches
back ~N days, a sparse or DEAD one reaches back much further. The aggregate MAX over that window
could therefore land on a stale family's older capture and report a leg's last-seen as OLDER
than the truth: the `vps` leg read 2026-07-15T19:23:54Z (464.0h of silence) off `polymarket_pairs`,
whose own writes stopped on 07-15, while the leg's true last capture was 2026-07-22T17:29:49Z
(~298h) — a ~166h OVER-statement wearing a precise date. Note the inverted monotonicity that made
it easy to miss: a DEEPER lookback returned a NEWER reading (10 -> 07-15, 20 -> 07-22).

The repair, pinned here: ONE uniform calendar window for every family; ONE bounded deeper scan
when (and only when) a monitored leg has no capture inside it; and an explicit lower bound on the
silence when even that sees nothing. Every unit test is offline (`tmp_path` + injected `now`);
the real-tape acceptance tests are pinned to a FIXED `max_day` slice and assert BOUNDS, never
equalities a new tape day could rot (L191/L140).
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
    spec = importlib.util.spec_from_file_location("inv_engine_l271", ROOT / "scripts" / "invariants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inv = _load_engine()

DENSE = "crypto_hourly"        # a real hourly-dual family that writes most days
SPARSE = "polymarket_pairs"    # a real hourly-dual family whose writes stopped (the contaminator)
VPS_MINUTE = 23                # tape_gap_monitor bucket: vps = minutes 20-29
CLOUD_MINUTE = 53              # cloud = minutes 50-59


def _write(tape_root: pathlib.Path, family: str, ts: datetime) -> None:
    fam = tape_root / family
    fam.mkdir(parents=True, exist_ok=True)
    with open(fam / f"dt={ts.date().isoformat()}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"captured_at": ts.isoformat(), "ticker": "KXTEST"}) + "\n")


# ── the L271 fixture: a sparse family reaching further back than a dense one ──
#
# anchor day = 2026-07-31.
#   DENSE  writes a file every day 07-20..07-31 (12 files); its only vps capture is on 07-20,
#          i.e. 11 days before the anchor -> OUTSIDE the newest-10-FILES window (07-22..07-31).
#   SPARSE writes only 07-10 and 07-11 (2 files); its vps capture is on 07-10 -> INSIDE its own
#          newest-10-files window, because it has fewer than 10 files at all.
# So the file-count MAX picks 07-10 over 07-20: ten days OLDER than the truth.
_ANCHOR = date(2026, 7, 31)
_TRUE_VPS = datetime(2026, 7, 20, 17, VPS_MINUTE, 49, tzinfo=UTC)
_STALE_VPS = datetime(2026, 7, 10, 9, VPS_MINUTE, 11, tzinfo=UTC)
_NOW = datetime(2026, 8, 1, 0, 30, tzinfo=UTC)


def _l271_tape(tape_root: pathlib.Path) -> None:
    day = date(2026, 7, 20)
    while day <= _ANCHOR:
        _write(tape_root, DENSE, datetime(day.year, day.month, day.day, 21, CLOUD_MINUTE, 5, tzinfo=UTC))
        day += timedelta(days=1)
    _write(tape_root, DENSE, _TRUE_VPS)
    _write(tape_root, SPARSE, _STALE_VPS)
    _write(tape_root, SPARSE, datetime(2026, 7, 11, 9, CLOUD_MINUTE, 11, tzinfo=UTC))


def test_a_sparse_family_can_no_longer_dominate_the_leg_maximum(tmp_path):
    """The whole L271 defect in one assertion: the reported vps capture must be the NEWEST one
    that exists, not the newest one visible through a ragged per-family window."""
    _l271_tape(tmp_path)
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_NOW)
    assert diag is not None
    assert diag["last_seen"]["vps"] == _TRUE_VPS.isoformat()
    assert diag["last_seen"]["vps"] > _STALE_VPS.isoformat()
    # and the silence it reports is the true one, not the ~10-days-longer fiction
    assert diag["ages"]["vps"] == pytest.approx(
        (_NOW - _TRUE_VPS).total_seconds() / 3600.0, abs=0.01)


def test_the_pre_l271_ragged_reading_is_still_reproducible(tmp_path):
    """The defect itself stays pinned — a fix nobody can reproduce the bug against is a fix
    nobody can re-verify (the `exclude_burst_windows=False` precedent)."""
    _l271_tape(tmp_path)
    ragged = inv._collector_leg_last_seen(tmp_path, calendar_horizon=False)
    assert ragged["vps"] == _STALE_VPS.isoformat()
    uniform = inv._collector_leg_last_seen(tmp_path)
    assert "vps" not in uniform, "the true capture predates the routine window; absence is honest"
    assert inv._collector_leg_last_seen(
        tmp_path, lookback_days=inv.DEAD_LEG_DEEP_LOOKBACK_DAYS)["vps"] == _TRUE_VPS.isoformat()


def test_the_ragged_reading_over_states_the_silence(tmp_path):
    """Direction matters: the old bound could only make an outage look LONGER than it was, which
    is why it survived — an over-statement of silence still 'looks like' a correct alarm."""
    _l271_tape(tmp_path)
    ragged = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_NOW, calendar_horizon=False)
    fixed = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_NOW)
    assert ragged["ages"]["vps"] > fixed["ages"]["vps"]
    assert ragged["ages"]["vps"] - fixed["ages"]["vps"] == pytest.approx(
        (_TRUE_VPS - _STALE_VPS).total_seconds() / 3600.0, abs=0.01)


def test_the_horizon_is_one_window_for_every_family(tmp_path):
    """Uniformity is the property being bought: one cutoff, one anchor, no per-family raggedness.
    Nothing older than the cutoff may be read at all."""
    _l271_tape(tmp_path)
    stats: dict = {}
    inv._collector_leg_last_seen(tmp_path, stats=stats)
    assert stats["calendar_horizon"] is True
    assert stats["scan_anchor_day"] == _ANCHOR.isoformat()
    assert stats["scan_cutoff_day"] == (_ANCHOR - timedelta(days=9)).isoformat()
    assert stats["scan_oldest_day"] >= stats["scan_cutoff_day"]
    ragged: dict = {}
    inv._collector_leg_last_seen(tmp_path, calendar_horizon=False, stats=ragged)
    assert ragged["scan_cutoff_day"] is None, "the old bound has no single cutoff — its defect"
    assert ragged["scan_oldest_day"] < stats["scan_cutoff_day"], "it read outside the window"


def test_the_deeper_scan_is_the_thing_that_recovers_the_date(tmp_path):
    """The escalation is what keeps a uniform window from going date-blind exactly when the
    outage is longest (the L273 'quieter the worse it gets' shape)."""
    _l271_tape(tmp_path)
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_NOW)
    assert diag["recovered_by_deep_scan"] == ["vps"]
    assert diag["deep_scan_days"] == inv.DEAD_LEG_DEEP_LOOKBACK_DAYS
    msg = inv.dead_collector_leg_warning(diag)
    assert "recovered by the deeper 30-day scan" in msg
    assert _TRUE_VPS.isoformat() in msg


def test_no_deeper_scan_when_nothing_is_missing(tmp_path):
    """Cost is paid only in the abnormal case: with every monitored leg inside the routine
    window, the deep scan must not run at all."""
    for h in range(0, 72, 3):
        t = datetime(2026, 7, 31, 23, 0, tzinfo=UTC) - timedelta(hours=h)
        _write(tmp_path, DENSE, t.replace(minute=VPS_MINUTE))
        _write(tmp_path, DENSE, t.replace(minute=CLOUD_MINUTE))
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_NOW, lookback_days=2)
    assert diag is None or diag["recovered_by_deep_scan"] == []
    seen = inv._collector_leg_last_seen(tmp_path, lookback_days=2)
    assert "vps" in seen and "cloud" in seen


def test_the_deep_scan_never_runs_on_the_pre_fix_path(tmp_path):
    """`calendar_horizon=False` must reproduce the OLD reading exactly — including the absence of
    an escalation the old code never had."""
    _l271_tape(tmp_path)
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_NOW, calendar_horizon=False)
    assert diag["recovered_by_deep_scan"] == []
    assert diag["deep_scan_days"] is None


# ── the floor: what the scan cannot see is a bound, never a date ─────────────

_ANCIENT_VPS = datetime(2026, 6, 1, 12, VPS_MINUTE, 30, tzinfo=UTC)


def _ancient_tape(tape_root: pathlib.Path) -> None:
    _write(tape_root, DENSE, _ANCIENT_VPS)
    day = date(2026, 7, 25)
    while day <= _ANCHOR:
        _write(tape_root, DENSE, datetime(day.year, day.month, day.day, 23, CLOUD_MINUTE, 5, tzinfo=UTC))
        day += timedelta(days=1)


def test_a_leg_older_than_every_window_reports_a_floor_not_a_date(tmp_path):
    """Beyond even the deep scan there is no date to report. The advisory must say so as a
    LOWER BOUND and must never reach for the nearest older timestamp it happens to hold."""
    _ancient_tape(tmp_path)
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_NOW)
    assert diag["status"] == "dead_leg" and diag["dead"] == "vps"
    assert diag["dead_last_seen"] is None
    assert diag["recovered_by_deep_scan"] == []
    floor = diag["silence_floor_h"]
    true_silence = (_NOW - _ANCIENT_VPS).total_seconds() / 3600.0
    assert 0 < floor <= true_silence, "a floor that exceeds the truth is not a floor"
    msg = inv.dead_collector_leg_warning(diag)
    assert "lower bound" in msg.lower()
    assert f"{floor:.1f}h" in msg
    assert _ANCIENT_VPS.isoformat() not in msg, "no timestamp may be invented or borrowed"


def test_the_floor_is_stated_in_the_ambiguous_block_too(tmp_path):
    """Both legs silent: the same honesty applies to the block that names nobody.

    Note the shape needed to reach this state at all — a consequence of the anchor being
    DATA-derived: recent day-files must exist (here written by the ad-hoc `other` bucket, which
    is a survivor signal but is never accused of dying) while both SCHEDULED legs are older than
    every window. A tape whose newest file is itself ancient anchors the window on that file and
    so still reports real dates; absence is always relative to newer data existing."""
    _write(tmp_path, DENSE, _ANCIENT_VPS)
    _write(tmp_path, DENSE, _ANCIENT_VPS.replace(minute=CLOUD_MINUTE))
    day = date(2026, 7, 25)
    while day <= _ANCHOR:
        _write(tmp_path, DENSE, datetime(day.year, day.month, day.day, 23, 5, 5, tzinfo=UTC))
        day += timedelta(days=1)
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_NOW)
    assert diag["status"] == "ambiguous"
    assert diag["last_seen"].get("vps") is None and diag["last_seen"].get("cloud") is None
    msg = inv.dead_collector_leg_warning(diag)
    assert msg.count("AT LEAST") == 2, "both legs get a bound, neither gets a borrowed date"
    assert _ANCIENT_VPS.isoformat() not in msg


# ── bounded I/O: the reason L271 declined to build this ─────────────────────

def test_files_read_is_bounded_by_days_times_families(tmp_path):
    """L271's stated cost objection was 'unbounded I/O on a family that writes many files per
    day'. Tape is one day-file per family per day, so the uniform window reads at most
    `lookback_days` files per family — a hard bound, asserted here rather than assumed."""
    day = date(2026, 7, 1)
    while day <= _ANCHOR:
        for fam in (DENSE, SPARSE):
            _write(tmp_path, fam, datetime(day.year, day.month, day.day, 12, CLOUD_MINUTE, 1, tzinfo=UTC))
        day += timedelta(days=1)
    stats: dict = {}
    inv._collector_leg_last_seen(tmp_path, lookback_days=10, stats=stats)
    assert stats["n_files_read"] <= 10 * 2
    ragged: dict = {}
    inv._collector_leg_last_seen(tmp_path, lookback_days=10, calendar_horizon=False, stats=ragged)
    assert stats["n_files_read"] <= ragged["n_files_read"], "the fix must not cost more I/O"


def test_a_dead_family_stops_costing_io_entirely(tmp_path):
    """The sparse/dead family is the one the old bound spent I/O on to fetch a WRONG answer;
    under the uniform window it contributes no files at all."""
    _l271_tape(tmp_path)
    uniform: dict = {}
    inv._collector_leg_last_seen(tmp_path, stats=uniform)
    ragged: dict = {}
    inv._collector_leg_last_seen(tmp_path, calendar_horizon=False, stats=ragged)
    assert uniform["n_files_read"] == ragged["n_files_read"] - 2  # SPARSE's two files


# ── robustness ──────────────────────────────────────────────────────────────

def test_empty_and_absent_tape_never_crash(tmp_path):
    assert inv._collector_leg_last_seen(tmp_path / "nope") == {}
    assert inv._newest_committed_day(tmp_path / "nope", [DENSE]) is None
    (tmp_path / DENSE).mkdir(parents=True)
    assert inv._newest_committed_day(tmp_path, [DENSE]) is None
    assert inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_NOW) is None


def test_unparseable_day_filenames_are_skipped_not_fatal(tmp_path):
    _l271_tape(tmp_path)
    (tmp_path / DENSE / "dt=not-a-date.jsonl").write_text("{}\n", encoding="utf-8")
    assert inv._newest_committed_day(tmp_path, [DENSE, SPARSE]) == _ANCHOR
    assert inv._collector_leg_last_seen(tmp_path, lookback_days=inv.DEAD_LEG_DEEP_LOOKBACK_DAYS)["vps"] \
        == _TRUE_VPS.isoformat()


def test_max_day_still_caps_the_anchor(tmp_path):
    """`max_day` is what makes the real-tape acceptance tests un-rottable; the anchor must obey
    it, or a pinned slice would silently follow the newest tape."""
    _l271_tape(tmp_path)
    stats: dict = {}
    inv._collector_leg_last_seen(tmp_path, max_day=date(2026, 7, 25), stats=stats)
    assert stats["scan_anchor_day"] == "2026-07-25"
    assert stats["scan_cutoff_day"] == "2026-07-16"


def test_the_advisory_is_still_non_gating(tmp_path, monkeypatch, capsys):
    """The L156 posture is unchanged by this fix: nothing here may touch the exit code."""
    _l271_tape(tmp_path)
    diag = inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_NOW)
    assert isinstance(inv.dead_collector_leg_warning(diag), str)
    monkeypatch.setattr(inv, "_collector_leg_last_seen",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert inv._dead_collector_leg_diagnosis(tape_root=tmp_path, now=_NOW) is None


# ── HARD acceptance on the REAL committed tape, pinned (L140/L191) ──────────
#
# `max_day=2026-08-01` caps the scan at CLOSED historical day-files, so neither wall-clock time
# nor tape landing later can move these. Assertions are BOUNDS and DIRECTIONS, never equalities
# on numbers a new tape day could change.
_REAL_TAPE = ROOT / "tape"
_real = pytest.mark.skipif(not _REAL_TAPE.is_dir(), reason="committed tape/ not present")
_L271_MAX_DAY = date(2026, 8, 1)
_L271_NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


@_real
def test_acceptance_real_tape_uniform_window_never_reports_an_older_date():
    """The core L271 direction on real tape: the uniform reading is never OLDER than the ragged
    one. (Absence is not 'older' — it is reported as a bound and escalated, see below.)"""
    ragged: dict = {}
    uniform: dict = {}
    old = inv._collector_leg_last_seen(_REAL_TAPE, max_day=_L271_MAX_DAY,
                                       calendar_horizon=False, stats=ragged)
    new = inv._collector_leg_last_seen(_REAL_TAPE, max_day=_L271_MAX_DAY, stats=uniform)
    for leg, iso in new.items():
        assert iso >= old.get(leg, ""), f"{leg} went backwards under the uniform window"
    assert uniform["scan_cutoff_day"] is not None
    assert ragged["scan_oldest_day"] <= uniform["scan_oldest_day"], \
        "the ragged window really does reach further back on this tape"
    assert uniform["n_files_read"] <= ragged["n_files_read"], "the fix must not cost more I/O"


@_real
def test_acceptance_real_tape_the_escalation_recovers_the_known_vps_outage():
    """Ground truth for this slice (findings/2026-08-03-...; L269/L272/L273 acceptance tests pin
    the same instant): the vps leg's last honest capture is 2026-07-22T17:29:49Z. It sits OUTSIDE
    the routine 10-day window at this anchor, so this is exactly the case the escalation exists
    for — the advisory must still name the true date, not a bound and not a borrowed one."""
    diag = inv._dead_collector_leg_diagnosis(tape_root=_REAL_TAPE, now=_L271_NOW,
                                             max_day=_L271_MAX_DAY)
    assert diag is not None
    assert str(diag["last_seen"]["vps"]).startswith("2026-07-22T17:29:49")
    assert diag["recovered_by_deep_scan"] == ["vps"], "this slice must exercise the escalation"
    assert diag["ages"]["vps"] > inv.DEAD_LEG_SILENCE_HOURS
    msg = inv.dead_collector_leg_warning(diag)
    assert "2026-07-22" in msg and "horizon caveat" in msg


@_real
def test_acceptance_real_tape_escalation_cost_is_bounded():
    """The escalation reads more, but a BOUNDED more: at most `deep days` files per family."""
    stats: dict = {}
    inv._collector_leg_last_seen(_REAL_TAPE, max_day=_L271_MAX_DAY,
                                 lookback_days=inv.DEAD_LEG_DEEP_LOOKBACK_DAYS, stats=stats)
    tgm = inv._load_tape_gap_monitor()
    n_families = len([f for f, c in tgm.FAMILY_CONFIG.items() if c.get("kind") == "hourly-dual"])
    assert stats["n_files_read"] <= inv.DEAD_LEG_DEEP_LOOKBACK_DAYS * n_families
