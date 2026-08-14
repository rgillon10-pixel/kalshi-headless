#!/usr/bin/env python3
"""l164_seam_rederive.py — independent re-derivation of the L164 seam-safety claims.

WHY THIS EXISTS. The two-agent verdict rule (LOOP-QUEUE.md step 5) requires an independent
`verifier` before any verdict-class number is recorded. Nothing here is verdict-class — this is
pure scheduling arithmetic, no price, no P&L, no CI, no registry flip — but the harness that built
`scripts/burst_chunk_plan.py`'s multi-instant half had no `Task`/subagent tool (the
L287/L288/L290/L291/L295/L308/L313/L325/L349 precedent), so the sanctioned REDUNDANCY fallback runs
instead. This is redundancy, never verification: it is a second implementation by the same author,
which catches representation and off-by-one errors but cannot catch a shared misconception.

WHAT MAKES IT INDEPENDENT. It imports NOTHING from `scripts.burst_chunk_plan` (pinned on the AST in
`tests/test_l164_seam_rederive.py`, not on prose) and re-derives the same facts on a deliberately
different representation:

  * `burst_chunk_plan` works in ELAPSED SECONDS from window start (integer tick indices x interval).
    This module materializes ABSOLUTE `datetime` objects for every tick of every chunk invocation,
    the way the actual `collection.burst_capture` runs would.
  * `burst_chunk_plan` derives a seam from a running cumulative tick count; this module derives it
    by walking the materialized per-chunk tick LISTS and taking `(last of chunk k, first of chunk
    k+1)` — i.e. from the data, not from an index formula.
  * Its ISO parser is its own (string slicing + `datetime`), not `core.timeutil.parse_iso_utc`.

The zero-overhead idealization is shared and stated: a real chunk seam also carries the
commit+push+verify wall-clock pause, which only WIDENS the gap. Every margin reported here is
therefore an upper bound on safety / a lower bound on risk.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple


def parse_instant(text: str) -> datetime:
    """Own ISO8601-UTC parser (string slicing), deliberately not `core.timeutil.parse_iso_utc`."""
    raw = text.strip()
    if raw.endswith("Z"):
        raw = raw[:-1]
    date_part, _, time_part = raw.partition("T")
    year, month, day = int(date_part[0:4]), int(date_part[5:7]), int(date_part[8:10])
    hour = int(time_part[0:2]) if len(time_part) >= 2 else 0
    minute = int(time_part[3:5]) if len(time_part) >= 5 else 0
    second = int(time_part[6:8]) if len(time_part) >= 8 else 0
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def materialize_chunk_ticks(
    start: datetime, sequence: Sequence[int], interval_seconds: int
) -> List[List[datetime]]:
    """Absolute timestamp of every tick, grouped by chunk invocation.

    Models what `collection.burst_capture --max-ticks N` actually does: a fresh invocation's first
    tick fires immediately, then one every `interval_seconds`. Chunk k+1 resumes on the cadence
    grid (the zero-overhead idealization above)."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be > 0")
    if not sequence or any(n <= 0 for n in sequence):
        raise ValueError(f"every chunk needs >= 1 tick, got {list(sequence)}")
    chunks: List[List[datetime]] = []
    cursor = start
    for n in sequence:
        ticks = [cursor + timedelta(seconds=interval_seconds * i) for i in range(n)]
        chunks.append(ticks)
        cursor = ticks[-1] + timedelta(seconds=interval_seconds)
    return chunks


def seam_windows(chunks: Sequence[Sequence[datetime]]) -> List[Tuple[datetime, datetime]]:
    """Every inter-chunk pause, read off the materialized tick lists rather than an index formula."""
    return [(chunks[k][-1], chunks[k + 1][0]) for k in range(len(chunks) - 1)]


def instant_margin_seconds(
    instant: datetime, seam: Tuple[datetime, datetime]
) -> float:
    """Distance in seconds from `instant` to the nearer edge of the seam pause; 0.0 if inside."""
    open_at, close_at = seam
    if open_at <= instant <= close_at:
        return 0.0
    return min(abs((instant - open_at).total_seconds()), abs((instant - close_at).total_seconds()))


def audit(
    start_iso: str,
    sequence: Sequence[int],
    interval_seconds: int,
    protect_isos: Sequence[str],
    margin_seconds: Optional[float] = None,
) -> Dict[str, object]:
    """Per-instant nearest-seam margin + a pass/fail against the L164 rule."""
    if margin_seconds is None:
        margin_seconds = float(interval_seconds)
    start = parse_instant(start_iso)
    chunks = materialize_chunk_ticks(start, sequence, interval_seconds)
    seams = seam_windows(chunks)
    rows = []
    for iso in protect_isos:
        instant = parse_instant(iso)
        margins = [instant_margin_seconds(instant, seam) for seam in seams]
        nearest = min(range(len(margins)), key=lambda i: margins[i]) if margins else None
        rows.append({
            "instant": iso,
            "offset_seconds": (instant - start).total_seconds(),
            "nearest_seam_after_chunk": None if nearest is None else nearest + 1,
            "nearest_seam_margin_seconds": None if nearest is None else margins[nearest],
            "containing_chunk": next(
                (k + 1 for k, ticks in enumerate(chunks) if ticks[0] <= instant <= ticks[-1]), None
            ),
            "safe": True if nearest is None else margins[nearest] > margin_seconds,
        })
    return {
        "start": start_iso,
        "sequence": list(sequence),
        "interval_seconds": interval_seconds,
        "margin_seconds": margin_seconds,
        "n_ticks": sum(sequence),
        "n_seams": len(seams),
        "seams_utc": [(a.isoformat().replace("+00:00", "Z"), b.isoformat().replace("+00:00", "Z"))
                      for a, b in seams],
        "instants": rows,
        "all_safe": all(r["safe"] for r in rows),
        "note": "redundancy re-derivation, not verification; zero-overhead seam idealization",
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Independent re-derivation of L164 seam safety")
    ap.add_argument("--start", required=True)
    ap.add_argument("--interval", type=int, required=True)
    ap.add_argument("--sequence", required=True, help="comma-separated --max-ticks values")
    ap.add_argument("--protect", action="append", default=[], help="ISO8601 UTC instant (repeatable)")
    ap.add_argument("--margin-seconds", type=float, default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    sequence = [int(tok) for tok in args.sequence.replace("[", "").replace("]", "").split(",") if tok.strip()]
    report = audit(args.start, sequence, args.interval, args.protect, args.margin_seconds)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_out:
        with open(args.json_out, "w") as fh:
            fh.write(text + "\n")
    print(text)
    return 0 if report["all_safe"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
