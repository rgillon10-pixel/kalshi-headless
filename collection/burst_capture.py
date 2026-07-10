"""collection.burst_capture — one-shot cloud "burst" runner for sub-hourly cross-venue capture.

Purpose
-------
Poll the EXISTING cross-venue one-pass collectors at sub-hourly cadence for a bounded window
around a scheduled market event (a CPI print, an FOMC rate decision, a World Cup semi/final).
It is a thin orchestrator: it calls the same `run()` functions the hourly pass calls, once per
requested family per tick, and stops at a wall-clock deadline. It writes NO tape of its own and
introduces NO schema change — every observation lands in the same tape family (and same JSONL
schema) the hourly pass would have written. Burst lines are distinguishable downstream PURELY by
`fetch_ts` density (many observations packed into a few minutes), never by a new family or flag.

Why (S9 / S17 data-adequacy rationale)
--------------------------------------
S9's Kalshi<->Polymarket lead-lag thesis died on data adequacy, not on the hypothesis: an hourly
cadence is far too coarse to resolve which venue moves first around a discrete news shock. See
`findings/2026-07-06-polymarket-leadlag-s9-resolution.md`. S17 (macro cross-venue pairs) needs the
same thing the hourly pass cannot provide: dense snapshots in the minutes bracketing a scheduled
release. This module is the collector that fills exactly that gap — a bounded, one-shot burst that
a cloud job launches shortly before an event and lets run until just after it.

Discipline mirrored from `collection/hourly_pass.py`
----------------------------------------------------
- Fault isolation (`_safe_call`): one family's exception is caught and recorded, never taking down
  the other families in that tick, and never aborting the burst.
- Honest completeness: overall completeness is the AND over every family-call of every tick. Any
  caught exception OR any family-level completeness failure flips it to FAIL — a partial failure
  lowers completeness, it never fakes success and it never stops the remaining ticks.
- No new tape family, no schema change: the pass functions write their own tape; burst adds none.

Ryan-approved 2026-07-10 (interactive session).

CLI
---
    python -m collection.burst_capture --until 2026-07-14T13:45:00Z \
        --interval 120 --families cpi,fed
    python -m collection.burst_capture --until <ISO8601-UTC> [--interval SECONDS]
        [--families a,b,c] [--max-ticks N]

Timing: tick boundaries sit at start + k*interval. If a tick overruns its interval, the missed
boundaries are skipped and the burst resumes at the next FUTURE boundary — no pile-up, no
back-to-back catch-up ticks. `--interval` has a hard floor of 30s (values below the floor are a
CLI error). The burst stops when now >= --until (or --max-ticks is reached). If --until is already
past at startup, it exits 0 having run 0 ticks and says so honestly — it never pretends a capture
happened.
"""
from __future__ import annotations

import argparse
import os
import sys
import time as _time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from collection import crypto_hourly, econ_prints, polymarket_pairs, sports_pairs

INTERVAL_FLOOR_SECONDS = 30


# --------------------------------------------------------------------------- #
# family registry — each family maps to an EXISTING one-pass run() function.
# `complete` extracts that family's own honest completeness signal from its return dict:
#   - polymarket_* families expose a top-level `completeness_ok`
#   - crypto/sports/econ expose n_total + n_complete; family completeness = n_total == n_complete
# This module does not modify any of those modules; it only reads their return shapes.
# --------------------------------------------------------------------------- #
def _complete_polymarket(r: Dict[str, Any]) -> bool:
    return bool(r.get("completeness_ok", False))


def _complete_crypto(r: Dict[str, Any]) -> bool:
    return r.get("n_symbols", 0) == r.get("n_complete", 0)


def _complete_sports(r: Dict[str, Any]) -> bool:
    return r.get("n_games", 0) == r.get("n_complete", 0)


def _complete_econ(r: Dict[str, Any]) -> bool:
    return r.get("n_series", 0) == r.get("n_complete", 0)


FAMILY_REGISTRY: Dict[str, Dict[str, Callable]] = {
    "wc": {
        "run": lambda: polymarket_pairs.run(),
        "complete": _complete_polymarket,
    },
    "fed": {
        "run": lambda: polymarket_pairs.run_fed_decision(),
        "complete": _complete_polymarket,
    },
    "cpi": {
        "run": lambda: polymarket_pairs.run_cpi(),
        "complete": _complete_polymarket,
    },
    "econ": {
        "run": lambda: econ_prints.run(),
        "complete": _complete_econ,
    },
    "crypto": {
        "run": lambda: crypto_hourly.run(),
        "complete": _complete_crypto,
    },
    "sports": {
        "run": lambda: sports_pairs.run(odds_api_key=os.environ.get("ODDS_API_KEY")),
        "complete": _complete_sports,
    },
}

VALID_FAMILIES = tuple(FAMILY_REGISTRY.keys())


def _safe_call(fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    """Never let one family's exception take the others (or the burst) down with it."""
    try:
        return {"status": "ok", "result": fn()}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _parse_until(value: str) -> datetime:
    """Parse an ISO8601 UTC deadline (accepts a trailing 'Z'). Result is tz-aware UTC."""
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# --------------------------------------------------------------------------- #
# one tick = run every requested family once, each fault-isolated
# --------------------------------------------------------------------------- #
def run_tick(families: List[str]) -> Dict[str, Any]:
    """Run each requested family once, fault-isolated. Returns per-family outcomes plus this
    tick's own `completeness_ok` (AND over every family-call) and `errors` count."""
    calls: Dict[str, Any] = {}
    tick_complete = True
    errors = 0
    for fam in families:
        entry = FAMILY_REGISTRY[fam]
        outcome = _safe_call(entry["run"])
        if outcome["status"] == "ok":
            fam_complete = bool(entry["complete"](outcome["result"]))
            outcome["completeness_ok"] = fam_complete
            tick_complete = tick_complete and fam_complete
        else:
            errors += 1
            tick_complete = False
        calls[fam] = outcome
    return {"calls": calls, "completeness_ok": tick_complete, "errors": errors}


# --------------------------------------------------------------------------- #
# the burst loop — sleep/now injectable for offline tests
# --------------------------------------------------------------------------- #
def run_burst(
    until: datetime,
    families: List[str],
    interval: int = 120,
    max_ticks: Optional[int] = None,
    *,
    now_fn: Callable[[], datetime] = None,
    sleep_fn: Callable[[float], None] = None,
    tick_fn: Callable[[List[str]], Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run ticks on boundaries at start + k*interval until now >= `until` (or `max_ticks`).

    Overrun handling: after a tick finishes, the next boundary is the first start+k*interval that
    is strictly in the future; any boundaries missed while a tick overran are skipped (no
    back-to-back catch-up). `now_fn`/`sleep_fn`/`tick_fn` are injectable for offline tests and
    default to wall-clock / real sleep / `run_tick`.
    """
    if interval < INTERVAL_FLOOR_SECONDS:
        raise ValueError(
            f"--interval {interval}s below hard floor {INTERVAL_FLOOR_SECONDS}s")

    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    sleep_fn = sleep_fn or _time.sleep
    tick_fn = tick_fn or run_tick

    start = now_fn()
    ticks: List[Dict[str, Any]] = []
    completeness_ok = True
    errors = 0

    # window already past at startup: honest zero-tick exit, never a faked capture.
    if start >= until:
        return {
            "ticks": 0, "families": families, "errors": 0,
            "completeness_ok": True, "window_already_past": True,
            "start": start.isoformat(), "until": until.isoformat(),
            "elapsed_minutes": 0.0, "tick_details": ticks,
        }

    k = 0  # index of the NEXT boundary to fire (boundary_k = start + k*interval)
    while True:
        boundary = start.timestamp() + k * interval
        now = now_fn()
        wait = boundary - now.timestamp()
        if wait > 0:
            sleep_fn(wait)
            now = now_fn()

        # deadline check happens at the boundary we actually reached.
        if now >= until:
            break
        if max_ticks is not None and len(ticks) >= max_ticks:
            break

        result = tick_fn(families)
        ticks.append(result)
        completeness_ok = completeness_ok and bool(result["completeness_ok"])
        errors += int(result.get("errors", 0))

        if max_ticks is not None and len(ticks) >= max_ticks:
            break

        # advance to the next boundary strictly in the future (skip any missed while this tick
        # ran long) — no pile-up, no catch-up burst.
        after = now_fn()
        k += 1
        while start.timestamp() + k * interval <= after.timestamp():
            k += 1

    end = now_fn()
    elapsed_minutes = (end.timestamp() - start.timestamp()) / 60.0
    return {
        "ticks": len(ticks), "families": families, "errors": errors,
        "completeness_ok": completeness_ok if ticks else True,
        "window_already_past": False,
        "start": start.isoformat(), "until": until.isoformat(),
        "elapsed_minutes": elapsed_minutes, "tick_details": ticks,
    }


def _summary_line(summary: Dict[str, Any]) -> str:
    fams = ",".join(summary["families"])
    if summary.get("window_already_past"):
        return (f"burst: 0 ticks (window already past), families {fams}, "
                f"errors 0, completeness ok")
    n = summary["ticks"]
    mins = summary["elapsed_minutes"]
    comp = "ok" if summary["completeness_ok"] else "FAIL"
    return (f"burst: {n} ticks over {mins:.1f} min, families {fams}, "
            f"errors {summary['errors']}, completeness {comp}")


def _families_arg(value: str) -> List[str]:
    fams = [f.strip() for f in value.split(",") if f.strip()]
    if not fams:
        raise argparse.ArgumentTypeError("--families must list at least one family")
    unknown = [f for f in fams if f not in FAMILY_REGISTRY]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown families {unknown}; valid: {list(VALID_FAMILIES)}")
    return fams


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="One-shot sub-hourly cross-venue burst capture (read-only collectors)")
    ap.add_argument("--until", required=True, type=_parse_until,
                    help="ISO8601 UTC deadline, e.g. 2026-07-14T13:45:00Z")
    ap.add_argument("--interval", type=int, default=120,
                    help=f"seconds between ticks (hard floor {INTERVAL_FLOOR_SECONDS})")
    ap.add_argument("--families", required=True, type=_families_arg,
                    help=f"comma list; valid: {','.join(VALID_FAMILIES)}")
    ap.add_argument("--max-ticks", type=int, default=None,
                    help="safety cap on number of ticks")
    args = ap.parse_args(argv)

    if args.interval < INTERVAL_FLOOR_SECONDS:
        ap.error(f"--interval {args.interval}s below hard floor {INTERVAL_FLOOR_SECONDS}s")

    summary = run_burst(
        until=args.until, families=args.families,
        interval=args.interval, max_ticks=args.max_ticks)
    print(_summary_line(summary))
    return 0 if summary["completeness_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
