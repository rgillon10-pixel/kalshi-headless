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

SEAM PROTECTION (L164, added 2026-07-26). The default `chunk_plan()`/`chunk_max_ticks_sequence()`
path above computes a UNIFORM chunk size only — it does not protect any particular instant within
the window from landing on a chunk seam (the commit+push+verify pause between two chunk
invocations). For a one-shot event with a single decisive release moment (an FOMC statement, a
CPI print), a uniform plan can place a seam directly on top of it — see
`findings/2026-07-25-q19-fomc-burst-preflight.md`'s "third gap" section, caught by an independent
verifier review after this module's first version shipped, and fixed BY HAND for that one event
(`ops/burst_capture_chunked.md`'s `[16, 14, 14, 14, 14, 12]` recipe). L57 already established that
an entire burst's signal can live in ONE release-instant capture.

`chunk_max_ticks_sequence_protecting()` / the CLI's `--protect` flag now compute that
hand-verification instead of requiring it: they grow ONLY the first chunk so its last tick lands
more than one `--interval` (by default; `--margin-seconds` overrides) after the protected instant,
then chunk the remainder normally. Feeding the FOMC's own numbers back through this function
reproduces the hand-verified `[16, 14, 14, 14, 14, 12]` recipe exactly (regression-pinned in
`tests/test_burst_chunk_plan.py`). Scope, stated honestly (not silently overreached): ONE protected
instant, and it must fall after the window's own start by more than the margin (there is no
boundary before t=0 to move) — an event with more than one decisive moment (e.g. an FOMC
statement AND a later presser Q&A) needs a hand check for the second moment same as before, and an
instant very late in the window will simply pull most/all chunks into "chunk 1", which is correct
but not necessarily what a `--chunk-minutes`-sized cadence was chosen for.
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


def first_chunk_ticks_protecting_instant(
    protect_offset_seconds: float,
    ticks_per_chunk_: int,
    interval_seconds: int,
    total_ticks: int,
    margin_seconds: Optional[float] = None,
) -> int:
    """How many ticks the FIRST chunk needs so its LAST tick lands more than `margin_seconds`
    (default: one `interval_seconds`, the L164 rule) after `protect_offset_seconds` (elapsed
    seconds from window start) — the protected instant sits strictly inside chunk 1, not on or
    near its trailing seam. Never shrinks below the normal `ticks_per_chunk_`, never grows past
    `total_ticks` (a protected instant needing the whole window collapses to one chunk).

    Raises if the instant is too close to (or before) the window's own start (t=0) to protect —
    there is no chunk boundary before t=0 to move, so that case needs a hand fix (e.g. start the
    burst window earlier), same as the module's pre-L164 scope limit."""
    if interval_seconds <= 0:
        raise ValueError(f"interval_seconds must be > 0, got {interval_seconds}")
    if margin_seconds is None:
        margin_seconds = float(interval_seconds)
    if margin_seconds < 0:
        raise ValueError(f"margin_seconds must be >= 0, got {margin_seconds}")
    if protect_offset_seconds <= margin_seconds:
        raise ValueError(
            f"protect instant at {protect_offset_seconds}s is within {margin_seconds}s of the "
            "window start (t=0) -- no chunk boundary sits before it to move; protect it by hand "
            "(e.g. start the burst window earlier) rather than via --protect"
        )
    # smallest last-tick index whose elapsed time strictly exceeds protect+margin
    required_last_tick_index = int((protect_offset_seconds + margin_seconds) // interval_seconds) + 1
    required_ticks = required_last_tick_index + 1
    return max(ticks_per_chunk_, min(required_ticks, total_ticks))


def chunk_max_ticks_sequence_protecting(
    total_minutes: float,
    chunk_minutes: float,
    interval_seconds: int,
    protect_offset_minutes: float,
    margin_seconds: Optional[float] = None,
) -> List[int]:
    """Like `chunk_max_ticks_sequence(chunk_plan(...))`, but grows chunk 1 (only) so the instant
    `protect_offset_minutes` after window start does not land on a chunk seam (L164). Chunks 2+
    stay the normal `ticks_per_chunk` size, last one absorbing the remainder, same as the
    unprotected plan."""
    if total_minutes <= 0:
        raise ValueError(f"total_minutes must be > 0, got {total_minutes}")
    if protect_offset_minutes * 60.0 >= total_minutes * 60.0:
        raise ValueError(
            f"protect instant at {protect_offset_minutes}min is at or past the window end "
            f"({total_minutes}min) -- nothing inside the window to protect"
        )
    total_ticks = max(1, math.ceil((total_minutes * 60.0) / interval_seconds))
    tpc = ticks_per_chunk(chunk_minutes, interval_seconds)
    first = first_chunk_ticks_protecting_instant(
        protect_offset_minutes * 60.0, tpc, interval_seconds, total_ticks, margin_seconds
    )
    seq = [first]
    remaining = total_ticks - first
    while remaining > 0:
        take = min(tpc, remaining)
        seq.append(take)
        remaining -= take
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


def _format_protected(seq: List[int], interval_seconds: int, protect_offset_minutes: float) -> str:
    return "\n".join([
        f"total_ticks={sum(seq)} interval={interval_seconds}s "
        f"n_chunks={len(seq)} protect_offset={protect_offset_minutes:.2f}min",
        f"max_ticks_sequence={seq}  (chunk 1 grown to protect the instant, L164)",
    ])


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Compute a chunked --max-ticks invocation plan for collection.burst_capture")
    ap.add_argument("--start", required=True, help="ISO8601 UTC window start, e.g. 2026-07-29T17:40:00Z")
    ap.add_argument("--until", required=True, help="ISO8601 UTC window end, e.g. 2026-07-29T19:45:00Z")
    ap.add_argument("--interval", type=int, required=True, help="seconds between ticks (matches burst_capture --interval)")
    ap.add_argument("--chunk-minutes", type=float, default=20.0, help="approx minutes per chunk (default 20)")
    ap.add_argument(
        "--protect", default=None,
        help="ISO8601 UTC instant to protect from a chunk seam (L164), e.g. the FOMC statement "
             "release. Single instant, must fall after --start by more than --margin-seconds. "
             "Grows chunk 1 only -- see the module docstring's SEAM PROTECTION section.")
    ap.add_argument(
        "--margin-seconds", type=float, default=None,
        help="minimum buffer between the protected instant and its chunk's trailing boundary "
             "(default: one --interval, the L164 rule)")
    args = ap.parse_args(argv)

    minutes = window_minutes(args.start, args.until)
    if args.protect:
        protect_offset_minutes = window_minutes(args.start, args.protect)
        seq = chunk_max_ticks_sequence_protecting(
            minutes, args.chunk_minutes, args.interval, protect_offset_minutes, args.margin_seconds
        )
        print(_format_protected(seq, args.interval, protect_offset_minutes))
    else:
        plan = chunk_plan(minutes, args.chunk_minutes, args.interval)
        print(_format_plan(plan, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
