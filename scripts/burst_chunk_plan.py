#!/usr/bin/env python3
"""burst_chunk_plan.py — Q19 FOMC pre-flight: compute a chunked-commit invocation plan for
`collection.burst_capture`, so a one-shot cloud burst survives its own sandbox dying partway
through the window.

WHY (see `findings/2026-07-25-q19-fomc-burst-preflight.md`). Every burst trigger today runs ONE
continuous `python -m collection.burst_capture --until <end> --interval I --families F` for the
whole event window (up to ~155 minutes) and commits tape to git exactly ONCE, after the script
exits on its own. Two of the three fired one-shots so far (`kalshi-burst-wcsemi1-0714`,
`kalshi-burst-wcfinal-0719`) produced ZERO committed tape despite `last_fired_at` confirming they
ran — `kb/00-LOG.md` 2026-07-14/07-15 pins the semi-1 loss to a dead sandbox mid-run, and a
2026-07-15 fix (Ryan-applied) added mandatory push-verification to the surviving one-shots, yet
`wcfinal` still lost its data on 07-19. Each underlying collector `run()` call
(`collection.polymarket_pairs`, `collection.crypto_hourly`, etc.) writes its own tape line to
local disk on every tick — the loss is NOT in the writing, it is that a single commit gates the
ENTIRE window on the process surviving to its very last line. Splitting one continuous run into
several shorter chunks, each followed by its own commit+push+verify, bounds worst-case loss to
one chunk instead of the whole window, at the one thing that changes: no code here, since
`collection.burst_capture` already supports `--max-ticks` per invocation.

This module does the one part of that recipe worth computing rather than doing by hand: how many
`--max-ticks` per chunk, and how many chunks, cover a given window without an off-by-one leaving a
gap at the end. It runs no network calls and touches no tape; it is pure arithmetic over the same
`--until`/`--interval` values the trigger prompt already carries.

WHAT THIS MODULE DOES NOT DO. It computes a UNIFORM chunk size only — it does not protect any
particular instant within the window from landing on a chunk seam (the commit+push+verify pause
between two chunk invocations). For a one-shot event with a single decisive release moment (an
FOMC statement, a CPI print), a uniform plan can place a seam directly on top of it — see
`findings/2026-07-25-q19-fomc-burst-preflight.md`'s "third gap" section, caught by an independent
verifier review after this module's first version shipped. L57 already established that an
entire burst's signal can live in ONE release-instant capture. Anyone using this tool for an
event with such a moment MUST manually check that no chunk boundary (the running sum of the
`chunk_max_ticks_sequence()` output, converted to elapsed time) falls within one `--interval` of
that moment, and hand-adjust the first chunk's size if it does — this module will not catch that
for you.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import List, Optional

from core.timeutil import parse_iso_utc


@dataclass(frozen=True)
class ChunkPlan:
    total_ticks: int
    ticks_per_chunk: int
    n_chunks: int
    chunk_seconds: float
    last_chunk_ticks: int


def ticks_per_chunk(chunk_minutes: float, interval_seconds: int) -> int:
    """How many ticks fit in one chunk's NOMINAL window (`chunk_minutes` converted to a tick
    count via `ceil`, so `ticks_per_chunk * interval_seconds >= chunk_minutes * 60`). This is a
    sizing target, not the actual elapsed span between a chunk's first and last tick — see
    `chunk_plan`'s `chunk_seconds` field for that (one interval shorter, since the first tick of
    a fresh `collection.burst_capture` invocation fires immediately, with no wait)."""
    if interval_seconds <= 0:
        raise ValueError(f"interval_seconds must be > 0, got {interval_seconds}")
    if chunk_minutes <= 0:
        raise ValueError(f"chunk_minutes must be > 0, got {chunk_minutes}")
    return max(1, math.ceil((chunk_minutes * 60.0) / interval_seconds))


def chunk_plan(total_minutes: float, chunk_minutes: float, interval_seconds: int) -> ChunkPlan:
    """Plan N chunks of `--max-ticks` covering a `total_minutes` window at `interval_seconds`
    cadence, each chunk approximately `chunk_minutes` long. The LAST chunk's tick count is
    whatever remains (never padded past the window — `collection.burst_capture` already stops
    itself at `--until` regardless of `--max-ticks`, so overshoot is harmless, but the plan
    should report the honest remainder for the runbook's own bookkeeping).

    `chunk_seconds` is the ACTUAL elapsed span from a chunk's first tick to its last —
    `(ticks_per_chunk - 1) * interval_seconds`, one interval shorter than the nominal
    `ticks_per_chunk * interval_seconds` window, because a fresh `collection.burst_capture`
    invocation's first tick fires immediately (no wait before boundary k=0). This is the
    quantity that matters for seam-timing decisions (see the module docstring's warning about
    protecting a decisive release instant)."""
    if total_minutes <= 0:
        raise ValueError(f"total_minutes must be > 0, got {total_minutes}")
    total_ticks = max(1, math.ceil((total_minutes * 60.0) / interval_seconds))
    tpc = ticks_per_chunk(chunk_minutes, interval_seconds)
    n_chunks = math.ceil(total_ticks / tpc)
    last = total_ticks - tpc * (n_chunks - 1)
    return ChunkPlan(
        total_ticks=total_ticks,
        ticks_per_chunk=tpc,
        n_chunks=n_chunks,
        chunk_seconds=float(max(0, tpc - 1) * interval_seconds),
        last_chunk_ticks=last,
    )


def chunk_max_ticks_sequence(plan: ChunkPlan) -> List[int]:
    """The literal `--max-ticks` value for each successive chunk invocation, in order."""
    seq = [plan.ticks_per_chunk] * (plan.n_chunks - 1)
    seq.append(plan.last_chunk_ticks)
    return seq


def window_minutes(start_iso: str, until_iso: str) -> float:
    """Minutes between two ISO8601 UTC timestamps (accepts a trailing 'Z')."""
    start, until = parse_iso_utc(start_iso), parse_iso_utc(until_iso)
    delta = (until - start).total_seconds() / 60.0
    if delta <= 0:
        raise ValueError(f"until ({until_iso}) must be after start ({start_iso})")
    return delta


def _format_plan(plan: ChunkPlan, interval_seconds: int) -> str:
    seq = chunk_max_ticks_sequence(plan)
    lines = [
        f"total_ticks={plan.total_ticks} interval={interval_seconds}s "
        f"chunk~{plan.chunk_seconds/60.0:.1f}min n_chunks={plan.n_chunks}",
        f"max_ticks_sequence={seq}",
    ]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Compute a chunked --max-ticks invocation plan for collection.burst_capture")
    ap.add_argument("--start", required=True, help="ISO8601 UTC window start, e.g. 2026-07-29T17:40:00Z")
    ap.add_argument("--until", required=True, help="ISO8601 UTC window end, e.g. 2026-07-29T19:45:00Z")
    ap.add_argument("--interval", type=int, required=True, help="seconds between ticks (matches burst_capture --interval)")
    ap.add_argument("--chunk-minutes", type=float, default=20.0, help="approx minutes per chunk (default 20)")
    args = ap.parse_args(argv)

    minutes = window_minutes(args.start, args.until)
    plan = chunk_plan(minutes, args.chunk_minutes, args.interval)
    print(_format_plan(plan, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
