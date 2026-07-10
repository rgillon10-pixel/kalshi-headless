"""collection.burst_capture — offline unit tests. Every family run() is monkeypatched to a
stub and the clock/sleep are injected, so no network and no real time pass. House style mirrors
tests/test_hourly_pass.py (injected stubs, honest completeness assertions)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from collection import burst_capture as bc


UNTIL = datetime(2026, 7, 14, 13, 45, 0, tzinfo=timezone.utc)


def _ok_tick(families):
    """A tick_fn stub: every family complete, no errors."""
    return {
        "calls": {f: {"status": "ok", "completeness_ok": True} for f in families},
        "completeness_ok": True, "errors": 0,
    }


class FakeClock:
    """Injectable now_fn/sleep_fn pair. sleep advances the fake clock; now returns it."""

    def __init__(self, start: datetime):
        self.t = start

    def now(self) -> datetime:
        return self.t

    def sleep(self, seconds: float) -> None:
        # advance the fake clock; never actually sleep.
        self.t = self.t + timedelta(seconds=max(0.0, seconds))


# --------------------------------------------------------------------------- #
# family-name -> function mapping; unknown family is an argparse error
# --------------------------------------------------------------------------- #
def test_family_registry_covers_spec():
    assert set(bc.FAMILY_REGISTRY) == {"wc", "fed", "cpi", "econ", "crypto", "sports"}


def test_families_arg_parses_known():
    assert bc._families_arg("cpi,fed") == ["cpi", "fed"]


def test_families_arg_unknown_is_error():
    with pytest.raises(Exception):
        bc._families_arg("cpi,bogus")


def test_main_unknown_family_exits_nonzero():
    with pytest.raises(SystemExit) as e:
        bc.main(["--until", "2026-07-14T13:45:00Z", "--families", "nope"])
    assert e.value.code != 0


# --------------------------------------------------------------------------- #
# stops at --until
# --------------------------------------------------------------------------- #
def test_stops_at_until():
    start = UNTIL - timedelta(minutes=10)  # 300s window
    clock = FakeClock(start)
    summary = bc.run_burst(
        until=UNTIL, families=["cpi"], interval=60,
        now_fn=clock.now, sleep_fn=clock.sleep, tick_fn=_ok_tick)
    # boundaries at 0,60,...,540 that are < until fire; 600 (==until) does not.
    assert summary["ticks"] == 10
    assert summary["completeness_ok"] is True
    assert summary["window_already_past"] is False


def test_window_already_past():
    clock = FakeClock(UNTIL + timedelta(seconds=1))
    summary = bc.run_burst(
        until=UNTIL, families=["cpi"], interval=60,
        now_fn=clock.now, sleep_fn=clock.sleep, tick_fn=_ok_tick)
    assert summary["ticks"] == 0
    assert summary["window_already_past"] is True
    assert summary["completeness_ok"] is True
    line = bc._summary_line(summary)
    assert "0 ticks (window already past)" in line


# --------------------------------------------------------------------------- #
# overrun skips missed boundaries (no pile-up / no catch-up)
# --------------------------------------------------------------------------- #
def test_overrun_skips_missed_boundaries():
    start = UNTIL - timedelta(minutes=10)
    clock = FakeClock(start)

    # each tick burns 150s of fake time — longer than one 60s interval, so it overruns and the
    # boundary it would otherwise land on next is already in the past. Must NOT fire back-to-back.
    fire_times = []

    def slow_tick(families):
        fire_times.append(clock.now())
        clock.sleep(150)  # overrun past the next boundary
        return _ok_tick(families)

    summary = bc.run_burst(
        until=UNTIL, families=["cpi"], interval=60,
        now_fn=clock.now, sleep_fn=clock.sleep, tick_fn=slow_tick)

    # boundaries fire at t=0, then next future boundary after 0+150=150 -> 180, then 180+150=330
    # -> 360, then 360+150=510 -> 540, then 540+150=690 >= until(600) stop.
    offsets = [(t - start).total_seconds() for t in fire_times]
    assert offsets == [0, 180, 360, 540]
    # no two ticks fired within the same interval window
    for a, b in zip(offsets, offsets[1:]):
        assert (b - a) >= 60
    assert summary["ticks"] == 4


# --------------------------------------------------------------------------- #
# fault isolation: one family raises every tick, others still run
# --------------------------------------------------------------------------- #
def test_fault_isolation_via_run_tick(monkeypatch):
    calls = {"good": 0, "bad": 0}

    def good_run():
        calls["good"] += 1
        return {"completeness_ok": True, "n_matched": 3}

    def bad_run():
        calls["bad"] += 1
        raise RuntimeError("venue 500")

    # inject a two-family registry: one healthy polymarket-style, one always-raising.
    monkeypatch.setitem(bc.FAMILY_REGISTRY, "good",
                        {"run": good_run, "complete": bc._complete_polymarket})
    monkeypatch.setitem(bc.FAMILY_REGISTRY, "bad",
                        {"run": bad_run, "complete": bc._complete_polymarket})

    result = bc.run_tick(["good", "bad"])
    # both families were attempted despite bad raising
    assert calls == {"good": 1, "bad": 1}
    assert result["calls"]["good"]["status"] == "ok"
    assert result["calls"]["bad"]["status"] == "error"
    assert result["errors"] == 1
    assert result["completeness_ok"] is False


def test_fault_isolation_over_full_burst(monkeypatch):
    def bad_run():
        raise RuntimeError("boom")

    def good_run():
        return {"completeness_ok": True}

    monkeypatch.setitem(bc.FAMILY_REGISTRY, "good",
                        {"run": good_run, "complete": bc._complete_polymarket})
    monkeypatch.setitem(bc.FAMILY_REGISTRY, "bad",
                        {"run": bad_run, "complete": bc._complete_polymarket})

    start = UNTIL - timedelta(minutes=3)  # 3 ticks at 60s
    clock = FakeClock(start)
    summary = bc.run_burst(
        until=UNTIL, families=["good", "bad"], interval=60,
        now_fn=clock.now, sleep_fn=clock.sleep)  # real run_tick

    assert summary["ticks"] == 3
    assert summary["errors"] == 3           # bad raised once per tick
    assert summary["completeness_ok"] is False
    line = bc._summary_line(summary)
    assert "completeness FAIL" in line
    assert "errors 3" in line


def test_family_completeness_failure_flips_summary():
    # a family that runs fine but reports its own completeness FALSE must lower the burst's.
    def incomplete_run():
        return {"completeness_ok": False}

    import collection.burst_capture as m
    m.FAMILY_REGISTRY["_incomplete"] = {
        "run": incomplete_run, "complete": bc._complete_polymarket}
    try:
        start = UNTIL - timedelta(minutes=1)
        clock = FakeClock(start)
        summary = bc.run_burst(
            until=UNTIL, families=["_incomplete"], interval=60,
            now_fn=clock.now, sleep_fn=clock.sleep)
        assert summary["ticks"] == 1
        assert summary["errors"] == 0                # no exception
        assert summary["completeness_ok"] is False   # family-level failure still fails
    finally:
        del m.FAMILY_REGISTRY["_incomplete"]


# --------------------------------------------------------------------------- #
# interval floor enforced (clamp choice: reject below 30 -> ValueError / CLI error)
# --------------------------------------------------------------------------- #
def test_interval_floor_run_burst_raises():
    clock = FakeClock(UNTIL - timedelta(minutes=1))
    with pytest.raises(ValueError):
        bc.run_burst(
            until=UNTIL, families=["cpi"], interval=29,
            now_fn=clock.now, sleep_fn=clock.sleep, tick_fn=_ok_tick)


def test_interval_floor_cli_error():
    with pytest.raises(SystemExit) as e:
        bc.main(["--until", "2026-07-14T13:45:00Z", "--families", "cpi", "--interval", "29"])
    assert e.value.code != 0


# --------------------------------------------------------------------------- #
# --max-ticks honored
# --------------------------------------------------------------------------- #
def test_max_ticks_honored():
    start = UNTIL - timedelta(minutes=30)  # window would allow many ticks
    clock = FakeClock(start)
    summary = bc.run_burst(
        until=UNTIL, families=["cpi"], interval=60, max_ticks=3,
        now_fn=clock.now, sleep_fn=clock.sleep, tick_fn=_ok_tick)
    assert summary["ticks"] == 3


# --------------------------------------------------------------------------- #
# --until parsing
# --------------------------------------------------------------------------- #
def test_parse_until_z_suffix():
    dt = bc._parse_until("2026-07-14T13:45:00Z")
    assert dt == UNTIL
    assert dt.tzinfo is not None


def test_summary_line_ok():
    summary = {
        "ticks": 5, "families": ["cpi", "fed"], "errors": 0,
        "completeness_ok": True, "elapsed_minutes": 8.0, "window_already_past": False,
    }
    line = bc._summary_line(summary)
    assert line == "burst: 5 ticks over 8.0 min, families cpi,fed, errors 0, completeness ok"
