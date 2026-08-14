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

MULTI-INSTANT SEAM PROTECTION + MECHANICAL CHECK (L164's remaining half, added 2026-08-14).
L164's own text named two things the 2026-07-26 build deliberately left out: (1) events with MORE
than one decisive instant (an FOMC statement AND its ~30-minutes-later presser Q&A), and (2) the
fact that a plan can only be GENERATED here, never CHECKED — `ops/burst_capture_chunked.md` still
instructed every future one-shot to "MANUALLY check whether any chunk boundary falls within one
`--interval` of any of them ... the tool will not do it for you". Both are now built:

  * `seam_offsets_seconds()` reports each INTERNAL seam as the `(last tick of chunk k, first tick
    of chunk k+1)` elapsed-second pair — the actual at-risk gap, not a nominal boundary.
  * `seam_violations()` is the mechanical form of L164's rule: an instant is safe iff its distance
    to EVERY seam interval exceeds the margin (default one `--interval`), checked on BOTH sides, so
    an instant sitting just after a seam is caught as well as one sitting just before it. This
    turns an arbitrary already-written sequence (e.g. the one pasted into a live trigger prompt)
    into something verifiable — `--verify-sequence` exits non-zero on any violation.
  * `chunk_max_ticks_sequence_protecting_multi()` accepts N protected instants and grows ONLY the
    chunk whose own trailing seam is violated, leaving every other chunk at the requested
    `--chunk-minutes` size.

Measured consequence, honestly stated: the single-instant
`chunk_max_ticks_sequence_protecting()` above grows CHUNK 1 no matter where the instant falls, so
whenever the instant lives in a LATER chunk it inflates chunk 1 to reach it and thereby inflates
the worst-case data loss the chunking exists to bound. On this module's own committed test cases
that is 43 ticks vs 15 (`100min/15min/60s`, protect at 40min) and 15 vs 10
(`155min/20min/120s`, protect at 25min). The single-instant function is NOT changed (the
FOMC `[16, 14, 14, 14, 14, 12]` recipe is regression-pinned to it and the two agree whenever the
instant falls inside chunk 1); new callers should prefer the multi form. See
`findings/2026-08-14-l164-multi-instant-seam-check.md`.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

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


@dataclass(frozen=True)
class SeamViolation:
    """One protected instant that lands too close to one chunk seam.

    `chunk_index` is 1-based and names the chunk the seam FOLLOWS (seam k sits between chunk k
    and chunk k+1). `gap_seconds` is the distance from the instant to the nearer edge of the seam
    interval, and is 0.0 when the instant falls INSIDE the seam itself (the worst case: no capture
    covers it at all)."""
    chunk_index: int
    seam_start_seconds: float
    seam_end_seconds: float
    protect_offset_seconds: float
    gap_seconds: float
    margin_seconds: float


def seam_offsets_seconds(seq: Sequence[int], interval_seconds: int) -> List[Tuple[float, float]]:
    """Each INTERNAL seam of a `--max-ticks` sequence, as `(last-tick-of-chunk-k elapsed seconds,
    first-tick-of-chunk-(k+1) elapsed seconds)` from window start.

    The pair — not a single instant — is the honest object: the seam is the commit+push+verify
    PAUSE, so the whole span between the two adjacent ticks is at risk, and it is at least one
    `interval_seconds` wide even in the idealized zero-overhead model used here (real overhead only
    widens it, never narrows it, so every check below is a lower bound on the true risk window).
    A sequence of one chunk has no internal seam and yields `[]`; the window's own end is not a
    seam (nothing follows it)."""
    if interval_seconds <= 0:
        raise ValueError(f"interval_seconds must be > 0, got {interval_seconds}")
    if any(t <= 0 for t in seq):
        raise ValueError(f"every chunk must carry >= 1 tick, got {list(seq)}")
    seams: List[Tuple[float, float]] = []
    cumulative = 0
    for ticks in list(seq)[:-1]:
        cumulative += ticks
        seams.append((float((cumulative - 1) * interval_seconds), float(cumulative * interval_seconds)))
    return seams


def _seam_is_safe(
    protect_offset_seconds: float,
    seam_start_seconds: float,
    seam_end_seconds: float,
    margin_seconds: float,
) -> bool:
    """L164's rule, two-sided: the instant must clear the seam interval by more than `margin`
    on whichever side it falls. Checking only the "instant before the seam" side (the single-
    instant grower's implicit assumption, which is sound only because it always moves the seam
    LATER) would silently pass an instant sitting just AFTER a seam."""
    return (
        protect_offset_seconds < seam_start_seconds - margin_seconds
        or protect_offset_seconds > seam_end_seconds + margin_seconds
    )


def seam_violations(
    seq: Sequence[int],
    interval_seconds: int,
    protect_offsets_seconds: Iterable[float],
    margin_seconds: Optional[float] = None,
) -> List[SeamViolation]:
    """Every (instant, seam) pair violating L164 in an ALREADY-WRITTEN `--max-ticks` sequence.

    This is the check `ops/burst_capture_chunked.md` previously mandated be done by hand for every
    future one-shot. Empty list == the sequence is seam-safe for all the given instants at this
    margin. Pure arithmetic: no clock, no network, no tape."""
    if margin_seconds is None:
        margin_seconds = float(interval_seconds)
    if margin_seconds < 0:
        raise ValueError(f"margin_seconds must be >= 0, got {margin_seconds}")
    seams = seam_offsets_seconds(seq, interval_seconds)
    out: List[SeamViolation] = []
    for offset in protect_offsets_seconds:
        for k, (start, end) in enumerate(seams, start=1):
            if _seam_is_safe(offset, start, end, margin_seconds):
                continue
            if start <= offset <= end:
                gap = 0.0
            else:
                gap = min(abs(offset - start), abs(offset - end))
            out.append(SeamViolation(
                chunk_index=k,
                seam_start_seconds=start,
                seam_end_seconds=end,
                protect_offset_seconds=float(offset),
                gap_seconds=float(gap),
                margin_seconds=float(margin_seconds),
            ))
    return out


def chunk_max_ticks_sequence_protecting_multi(
    total_minutes: float,
    chunk_minutes: float,
    interval_seconds: int,
    protect_offsets_minutes: Sequence[float],
    margin_seconds: Optional[float] = None,
) -> List[int]:
    """A `--max-ticks` sequence covering the window in which NO internal seam falls within
    `margin_seconds` (default one `interval_seconds`) of ANY of `protect_offsets_minutes`.

    Unlike `chunk_max_ticks_sequence_protecting()`, which grows chunk 1 regardless of where the
    instant sits, this grows ONLY the chunk whose own trailing seam is violated — so an instant
    late in the window no longer inflates the first chunk (and with it the worst-case loss the
    whole chunking recipe exists to bound). With a single instant that falls inside chunk 1 the two
    functions agree exactly (regression-pinned on the FOMC recipe).

    Degenerate-but-correct case, stated rather than hidden: instants packed so densely that every
    candidate seam is blocked collapse the plan toward ONE chunk covering the window — which IS the
    only seam-safe plan then, and is exactly the loss exposure the caller should see and react to
    (e.g. by widening the window or accepting a hand-chosen seam), not something to silently
    approximate away."""
    if total_minutes <= 0:
        raise ValueError(f"total_minutes must be > 0, got {total_minutes}")
    if interval_seconds <= 0:
        raise ValueError(f"interval_seconds must be > 0, got {interval_seconds}")
    if margin_seconds is None:
        margin_seconds = float(interval_seconds)
    if margin_seconds < 0:
        raise ValueError(f"margin_seconds must be >= 0, got {margin_seconds}")
    total_seconds = total_minutes * 60.0
    offsets = sorted({float(p) * 60.0 for p in protect_offsets_minutes})
    for offset in offsets:
        if offset >= total_seconds:
            raise ValueError(
                f"protect instant at {offset / 60.0}min is at or past the window end "
                f"({total_minutes}min) -- nothing inside the window to protect"
            )
        if offset <= margin_seconds:
            raise ValueError(
                f"protect instant at {offset}s is within {margin_seconds}s of the window start "
                "(t=0) -- no chunk boundary sits before it to move; protect it by hand (e.g. "
                "start the burst window earlier) rather than via --protect"
            )
    total_ticks = max(1, math.ceil(total_seconds / interval_seconds))
    tpc = ticks_per_chunk(chunk_minutes, interval_seconds)
    seq: List[int] = []
    placed = 0
    while placed < total_ticks:
        take = min(tpc, total_ticks - placed)
        while placed + take < total_ticks:
            start = float((placed + take - 1) * interval_seconds)
            end = float((placed + take) * interval_seconds)
            if all(_seam_is_safe(o, start, end, margin_seconds) for o in offsets):
                break
            take += 1
        seq.append(take)
        placed += take
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


def _format_protected_multi(
    seq: List[int], interval_seconds: int, protect_offsets_minutes: List[float]
) -> str:
    offsets = ", ".join(f"{m:.2f}min" for m in protect_offsets_minutes)
    return "\n".join([
        f"total_ticks={sum(seq)} interval={interval_seconds}s "
        f"n_chunks={len(seq)} protect_offsets=[{offsets}]",
        f"max_ticks_sequence={seq}  (only the chunks whose own seam was violated grew, L164)",
    ])


def _format_seam_check(violations: List[SeamViolation], margin_seconds: float) -> str:
    if not violations:
        return f"seam_check=PASS (margin={margin_seconds:.0f}s, 0 violations)"
    lines = [f"seam_check=FAIL (margin={margin_seconds:.0f}s, {len(violations)} violations)"]
    for v in violations:
        lines.append(
            f"  instant t+{v.protect_offset_seconds:.0f}s vs seam after chunk {v.chunk_index} "
            f"[{v.seam_start_seconds:.0f}s, {v.seam_end_seconds:.0f}s] -- gap {v.gap_seconds:.0f}s "
            f"<= margin {v.margin_seconds:.0f}s"
        )
    return "\n".join(lines)


def _parse_sequence(raw: str) -> List[int]:
    try:
        seq = [int(tok) for tok in raw.replace("[", "").replace("]", "").split(",") if tok.strip()]
    except ValueError as exc:
        raise ValueError(f"--verify-sequence must be comma-separated integers, got {raw!r}") from exc
    if not seq:
        raise ValueError("--verify-sequence must name at least one chunk")
    return seq


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Compute a chunked --max-ticks invocation plan for collection.burst_capture")
    ap.add_argument("--start", required=True, help="ISO8601 UTC window start, e.g. 2026-07-29T17:40:00Z")
    ap.add_argument("--until", required=True, help="ISO8601 UTC window end, e.g. 2026-07-29T19:45:00Z")
    ap.add_argument("--interval", type=int, required=True, help="seconds between ticks (matches burst_capture --interval)")
    ap.add_argument("--chunk-minutes", type=float, default=20.0, help="approx minutes per chunk (default 20)")
    ap.add_argument(
        "--protect", default=None, action="append",
        help="ISO8601 UTC instant to protect from a chunk seam (L164), e.g. the FOMC statement "
             "release. REPEATABLE (added 2026-08-14): pass it once per decisive instant, e.g. the "
             "statement AND its presser. Each must fall after --start by more than "
             "--margin-seconds. One instant keeps the original grow-chunk-1 behavior; two or more "
             "grow only the chunks whose own seam is violated -- see the module docstring.")
    ap.add_argument(
        "--margin-seconds", type=float, default=None,
        help="minimum buffer between the protected instant and its chunk's trailing boundary "
             "(default: one --interval, the L164 rule)")
    ap.add_argument(
        "--verify-sequence", default=None,
        help="check an ALREADY-WRITTEN --max-ticks sequence (comma-separated, e.g. "
             "'16,14,14,14,14,12') against every --protect instant instead of computing a new "
             "one; exits 2 if any seam violates L164. This is the check "
             "ops/burst_capture_chunked.md used to mandate be done by hand.")
    args = ap.parse_args(argv)

    minutes = window_minutes(args.start, args.until)
    protect_offsets = [window_minutes(args.start, p) for p in (args.protect or [])]
    margin = float(args.interval) if args.margin_seconds is None else float(args.margin_seconds)

    if args.verify_sequence:
        if not protect_offsets:
            ap.error("--verify-sequence requires at least one --protect instant to check against")
        seq = _parse_sequence(args.verify_sequence)
        violations = seam_violations(
            seq, args.interval, [m * 60.0 for m in protect_offsets], args.margin_seconds
        )
        print(_format_protected_multi(seq, args.interval, protect_offsets))
        print(_format_seam_check(violations, margin))
        return 2 if violations else 0

    if len(protect_offsets) == 1:
        seq = chunk_max_ticks_sequence_protecting(
            minutes, args.chunk_minutes, args.interval, protect_offsets[0], args.margin_seconds
        )
        print(_format_protected(seq, args.interval, protect_offsets[0]))
    elif protect_offsets:
        seq = chunk_max_ticks_sequence_protecting_multi(
            minutes, args.chunk_minutes, args.interval, protect_offsets, args.margin_seconds
        )
        print(_format_protected_multi(seq, args.interval, protect_offsets))
    else:
        plan = chunk_plan(minutes, args.chunk_minutes, args.interval)
        print(_format_plan(plan, args.interval))
        return 0

    # self-check: never emit a plan this module's own rule would reject (defence in depth --
    # the generator and the checker are separate code paths, so agreement is information).
    violations = seam_violations(
        seq, args.interval, [m * 60.0 for m in protect_offsets], args.margin_seconds
    )
    print(_format_seam_check(violations, margin))
    return 2 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
