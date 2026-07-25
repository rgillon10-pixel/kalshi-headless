"""scripts.burst_chunk_plan — offline unit tests. Pure arithmetic, no network/tape/clock."""
from __future__ import annotations

import pytest

from scripts.burst_chunk_plan import (
    ChunkPlan,
    chunk_max_ticks_sequence,
    chunk_plan,
    main,
    ticks_per_chunk,
    window_minutes,
)


# --------------------------------------------------------------------------- #
# ticks_per_chunk
# --------------------------------------------------------------------------- #
def test_ticks_per_chunk_exact_division():
    assert ticks_per_chunk(chunk_minutes=20, interval_seconds=120) == 10  # 1200s/120s


def test_ticks_per_chunk_rounds_up_never_undershoots():
    # 20min=1200s at 90s interval -> 13.33 ticks; must round UP to 14 so the chunk
    # is never SHORTER than requested (an undershoot would just be a slightly-short
    # chunk with an extra chunk at the end; rounding down would silently under-cover).
    assert ticks_per_chunk(chunk_minutes=20, interval_seconds=90) == 14
    assert 14 * 90 >= 20 * 60


def test_ticks_per_chunk_floors_at_one():
    assert ticks_per_chunk(chunk_minutes=0.01, interval_seconds=90) == 1


@pytest.mark.parametrize("chunk_minutes,interval_seconds", [(0, 90), (-5, 90), (20, 0), (20, -1)])
def test_ticks_per_chunk_rejects_nonpositive(chunk_minutes, interval_seconds):
    with pytest.raises(ValueError):
        ticks_per_chunk(chunk_minutes, interval_seconds)


# --------------------------------------------------------------------------- #
# chunk_plan / chunk_max_ticks_sequence — the core invariant: the sequence must
# cover the FULL window with no gap, no chunk of a wrong size.
# --------------------------------------------------------------------------- #
def test_chunk_plan_exact_division_no_remainder():
    # 60 minutes at 120s interval = 30 ticks total; 20min chunks = 10 ticks/chunk -> 3 chunks, no remainder.
    plan = chunk_plan(total_minutes=60, chunk_minutes=20, interval_seconds=120)
    assert plan.total_ticks == 30
    assert plan.ticks_per_chunk == 10
    assert plan.n_chunks == 3
    assert plan.last_chunk_ticks == 10
    assert chunk_max_ticks_sequence(plan) == [10, 10, 10]


def test_chunk_plan_sequence_sums_to_total_ticks():
    # a battery of realistic (window, chunk, interval) triples, none evenly divisible.
    cases = [
        (125, 20, 90),   # FOMC: 17:40->19:45 = 125min @ 90s
        (155, 20, 120),  # WC final: 20:10->22:45 = 155min @ 120s
        (100, 15, 60),
        (37, 10, 45),
    ]
    for total_minutes, chunk_minutes, interval_seconds in cases:
        plan = chunk_plan(total_minutes, chunk_minutes, interval_seconds)
        seq = chunk_max_ticks_sequence(plan)
        assert sum(seq) == plan.total_ticks, (total_minutes, chunk_minutes, interval_seconds)
        assert len(seq) == plan.n_chunks
        # every chunk except the last is exactly ticks_per_chunk; the last is <= that.
        assert all(t == plan.ticks_per_chunk for t in seq[:-1])
        assert 0 < seq[-1] <= plan.ticks_per_chunk


def test_chunk_plan_last_chunk_never_zero_or_negative():
    # a case engineered to land exactly on a chunk boundary (no dangling remainder chunk).
    plan = chunk_plan(total_minutes=40, chunk_minutes=20, interval_seconds=60)
    assert plan.last_chunk_ticks > 0
    assert plan.n_chunks == 2


def test_chunk_plan_single_chunk_when_window_shorter_than_chunk_size():
    plan = chunk_plan(total_minutes=10, chunk_minutes=20, interval_seconds=90)
    assert plan.n_chunks == 1
    assert chunk_max_ticks_sequence(plan) == [plan.total_ticks]


@pytest.mark.parametrize("total_minutes", [0, -1])
def test_chunk_plan_rejects_nonpositive_window(total_minutes):
    with pytest.raises(ValueError):
        chunk_plan(total_minutes, chunk_minutes=20, interval_seconds=90)


# --------------------------------------------------------------------------- #
# window_minutes — ISO8601 parsing, mirrors collection.burst_capture._parse_until
# --------------------------------------------------------------------------- #
def test_window_minutes_basic():
    assert window_minutes("2026-07-29T17:40:00Z", "2026-07-29T19:45:00Z") == pytest.approx(125.0)


def test_window_minutes_accepts_offset_form():
    assert window_minutes("2026-07-14T20:10:00+00:00", "2026-07-14T22:30:00+00:00") == pytest.approx(140.0)


def test_window_minutes_rejects_non_positive_span():
    with pytest.raises(ValueError):
        window_minutes("2026-07-29T19:45:00Z", "2026-07-29T17:40:00Z")
    with pytest.raises(ValueError):
        window_minutes("2026-07-29T17:40:00Z", "2026-07-29T17:40:00Z")


# --------------------------------------------------------------------------- #
# the ACTUAL FOMC plan this module exists to produce (real values, not a fixture) —
# regression-pins the exact recipe the ops runbook quotes.
# --------------------------------------------------------------------------- #
def test_fomc_window_plan_matches_the_recommended_recipe():
    minutes = window_minutes("2026-07-29T17:40:00Z", "2026-07-29T19:45:00Z")
    assert minutes == pytest.approx(125.0)
    plan = chunk_plan(minutes, chunk_minutes=20, interval_seconds=90)
    assert plan.total_ticks == 84       # ceil(125*60/90)
    assert plan.ticks_per_chunk == 14   # ceil(20*60/90)
    assert plan.n_chunks == 6
    assert chunk_max_ticks_sequence(plan) == [14, 14, 14, 14, 14, 14]
    assert sum(chunk_max_ticks_sequence(plan)) == 84


# --------------------------------------------------------------------------- #
# CLI smoke test — exercises main() end-to-end (argparse + print), no mocking needed
# since the module does no I/O beyond stdout.
# --------------------------------------------------------------------------- #
def test_main_smoke(capsys):
    rc = main([
        "--start", "2026-07-29T17:40:00Z",
        "--until", "2026-07-29T19:45:00Z",
        "--interval", "90",
        "--chunk-minutes", "20",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "total_ticks=84" in out
    assert "n_chunks=6" in out
    assert "[14, 14, 14, 14, 14, 14]" in out
