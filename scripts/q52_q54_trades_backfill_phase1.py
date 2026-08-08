#!/usr/bin/env python3
"""Q52/Q54 PHASE-1 TRADE-PRINT BACKFILL: turn the S78/S79 "collect-and-revisit" gate from an
un-run pull into committed tape, under a DECLARED byte cap.

WHY THIS EXISTS
---------------
`findings/2026-08-08-kalshi-trades-backfill-gate-not-calendar-gate.md` (L313) measured that
the S78/Q52 and S79/Q54 data gates are NOT calendar gates: `collection/kalshi_trades.py` has
no scheduled writer, so waiting adds exactly zero trade days forever, while 338 distinct
settled sports games already sit in committed book+settlement tape. That finding ended with a
proposal it deliberately did NOT execute:

    "a bounded phase 1 instead: target only the settled sports tickers, min_ts/max_ts scoped
     to each ticker's own eligible day, start with the 07-07..07-14 window, measure realized
     bytes and stop if the extrapolation exceeds a declared cap (suggest 25-50MB)."

This module IS that phase 1. It is a COLLECTOR milestone, not a probe: it pulls public
executed prints and writes tape. It computes no P&L, no fill rate, no CI, no edge and no
verdict, and a test asserts those words never appear in its report.

WHAT IT DOES
------------
1. Rebuilds the population funnel from COMMITTED tape only (no network): per
   `tape/orderbook_depth/` day in the window, tickers with >= 2 snapshots (the fill-sim's own
   interval predicate, imported from `scripts/q51_maker_fillsim`, never re-guessed) that are
   sports-game markets and whose outcome one of the NINE declared settlement families already
   resolves to a binary result (`core.settlement_sources`, L300 — one-family reads are how
   this gate was mis-stated before).
2. Rolls those (day, ticker) pairs up to GAMES — S79's resample unit (L6) — and orders the
   games deterministically by ROUND-ROBIN over series (league), so a byte-capped prefix is
   league-diverse rather than one league's alphabet. Re-running with the same tape and the
   same cap selects the same games.
3. Pulls each selected game's tickers WHOLE-GAME AT A TIME through
   `collection.kalshi_trades.run` (its own trade_id dedupe, its own append-only writer, its
   own honest `completeness_ok`), full committed-day windows, and re-measures
   `tape/kalshi_trades/` on disk after every game.
4. STOPS at the declared byte cap. The cap is enforced against MEASURED bytes on disk, not an
   extrapolation, and the stop is recorded (`stopped_reason`) rather than inferred.

HONEST COVERAGE (read this before joining against the tape)
-----------------------------------------------------------
The resulting `tape/kalshi_trades/dt=*.jsonl` day-files are NOT complete venue days and must
never be read as such. They are a TICKER-SCOPED backfill: only the tickers of the selected
games, only on the days those tickers had >= 2 book snapshots. `dt=2026-08-03` (the one
pre-existing day) is likewise a 42-ticker slice. The emitted report carries the full coverage
manifest — every (game, day, ticker, min_ts, max_ts) attempted and its outcome — so a
consumer can state exactly what it is joining against instead of assuming a day is whole.

Run:
    python3 scripts/q52_q54_trades_backfill_phase1.py --dry-run      # offline plan only
    python3 scripts/q52_q54_trades_backfill_phase1.py --cap-mb 40    # live pull, capped
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from collection import kalshi_trades as kt  # noqa: E402
from core.settlement_sources import resolve_market_results  # noqa: E402
from scripts.kalshi_trades_backfill_population_audit import (  # noqa: E402
    depth_day_files, eligible_tickers, scan_depth_day,
)
from scripts.q51_maker_fillsim import game_of, is_sports_game_market, series_of  # noqa: E402

DEFAULT_TAPE_ROOT = REPO_ROOT / "tape"
TRADES_FAMILY = "kalshi_trades"
SCHEMA_VERSION = "q52_q54_trades_backfill_phase1.v1"

# The 2026-08-08 finding's own phase-1 window: the stretch holding the bulk of the 338 settled
# sports games. Not a claim that later days are worthless — a bounded starting point.
DEFAULT_DAYS: Tuple[str, ...] = (
    "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10",
    "2026-07-11", "2026-07-12", "2026-07-13", "2026-07-14",
)

# Declared cap. The finding proposed 25-50MB for phase 1 against a tape/ that is already
# ~1.7GB; 40MB sits inside that band. Enforced on MEASURED on-disk bytes.
DEFAULT_CAP_MB = 40.0

# Per-query pagination cap. RAISED 20 -> 60 after the first live pass: a ticker-scoped sports
# day window is usually 1-3 pages, but the heaviest one measured (`KXMLBGAME-26JUL061915NYMATL`,
# a US-market MLB game) needed 26 and 28 calls at limit=1000 (25,405 / 27,532 prints), so a
# cap of 20 TRUNCATED it. A truncated print stream is worse than a missing one for a flow
# strategy — the tape line carries no partial-coverage marker, so a downstream signed-flow
# signal would silently read a prefix of the day as the day. 60 is ~2x the measured worst
# case; anything that still hits it is reported as `truncated` and never silently upgraded
# (L10), and whole games with a truncated query are counted in `n_games_incomplete`.
DEFAULT_MAX_CALLS = 60


# --------------------------------------------------------------------------- #
# population (committed tape only — no network in this half)
# --------------------------------------------------------------------------- #
def eligible_ticker_days(tape_root: Path = DEFAULT_TAPE_ROOT,
                         days: Sequence[str] = DEFAULT_DAYS,
                         resolver: Callable = resolve_market_results,
                         ) -> Tuple[Dict[str, List[Tuple[str, str]]], Dict[str, object]]:
    """(game -> sorted [(day, ticker)], funnel_stats) over committed tape.

    A (day, ticker) pair qualifies iff the ticker has >= 2 `orderbook_depth` snapshots that
    day, is a sports-game market, and a declared settlement family already resolves it to a
    binary result. Settlement is resolved ONCE over the union, not per day.
    """
    day_sports: Dict[str, List[str]] = {}
    union: set = set()
    for day, path in depth_day_files(tape_root, days):
        snaps, _ = scan_depth_day(path)
        sports = [t for t in eligible_tickers(snaps) if is_sports_game_market(t)]
        day_sports[day] = sports
        union |= set(sports)

    rep = resolver(sorted(union), root=str(tape_root))
    settled = set(rep.resolved)

    games: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    n_pairs = 0
    for day in sorted(day_sports):
        for t in sorted(day_sports[day]):
            if t in settled:
                games[game_of(t)].append((day, t))
                n_pairs += 1
    stats = {
        "days_scanned": [d for d, _ in depth_day_files(tape_root, days)],
        "n_sports_eligible_union": len(union),
        "n_sports_settled_union": len(union & settled),
        "n_ticker_days": n_pairs,
        "n_games": len(games),
        "settlement_price_source_tag": "broker_truth",
        "settlement_sources_scanned": list(rep.sources_scanned),
    }
    return {g: sorted(v) for g, v in games.items()}, stats


def order_games(games: Mapping[str, Sequence[Tuple[str, str]]]) -> List[str]:
    """Deterministic league-diverse order: round-robin over series, sorted within each.

    A plain `sorted()` prefix would be one league's alphabet; a byte-capped prefix of THAT is
    a single-competition sample masquerading as a cross-sport one.
    """
    by_series: Dict[str, List[str]] = defaultdict(list)
    for g in sorted(games):
        by_series[series_of(g)].append(g)
    out: List[str] = []
    i = 0
    while True:
        added = False
        for s in sorted(by_series):
            if i < len(by_series[s]):
                out.append(by_series[s][i])
                added = True
        if not added:
            return out
        i += 1


def plan_pulls(games: Mapping[str, Sequence[Tuple[str, str]]],
               order: Sequence[str]) -> List[Dict[str, object]]:
    """One planned unit per game: its ticker-days grouped by day, with that day's UTC bounds."""
    plan: List[Dict[str, object]] = []
    for g in order:
        by_day: Dict[str, List[str]] = defaultdict(list)
        for day, tk in games[g]:
            by_day[day].append(tk)
        queries = []
        for day in sorted(by_day):
            mn, mx = kt.day_bounds(day)
            queries.append({"day": day, "tickers": sorted(by_day[day]),
                            "min_ts": mn, "max_ts": mx})
        plan.append({"game": g, "series": series_of(g), "queries": queries,
                     "n_ticker_days": sum(len(q["tickers"]) for q in queries)})
    return plan


# --------------------------------------------------------------------------- #
# bounded execution
# --------------------------------------------------------------------------- #
def family_bytes(store: Path) -> int:
    store = Path(store)
    if not store.exists():
        return 0
    return sum(p.stat().st_size for p in store.glob("dt=*.jsonl"))


def execute(plan: Sequence[Mapping[str, object]],
            store: Optional[Path] = None,
            cap_bytes: int = int(DEFAULT_CAP_MB * 1024 * 1024),
            max_games: Optional[int] = None,
            client=None,
            max_calls: int = DEFAULT_MAX_CALLS,
            min_interval: float = 0.25,
            runner: Callable = kt.run,
            verbose: bool = True) -> Dict[str, object]:
    """Pull whole games until the DECLARED byte cap is reached. Measured, never extrapolated.

    The cap is checked BEFORE starting a game and again after it lands, so a game is either
    fully pulled or not started — a half-pulled game would be a silently biased unit.
    """
    store = Path(store) if store is not None else kt.TAPE
    if client is None and runner is kt.run:
        # ONE client for the whole pass: `kt.run` would otherwise build a fresh one per
        # query and each would carry its own politeness timer, so the min-interval would
        # never actually bind across a 300-query backfill.
        from validation.v3_market import Kalshi, _load_venue_cfg
        client = Kalshi(_load_venue_cfg()["api_base"], min_interval=min_interval)
    start_bytes = family_bytes(store)
    manifest: List[Dict[str, object]] = []
    n_written = 0
    n_pulled = 0
    n_calls = 0
    n_incomplete = 0
    stopped_reason = "plan_exhausted"
    t0 = time.time()

    for i, unit in enumerate(plan):
        if max_games is not None and i >= max_games:
            stopped_reason = "max_games"
            break
        grown = family_bytes(store) - start_bytes
        if grown >= cap_bytes:
            stopped_reason = "byte_cap"
            break
        entry: Dict[str, object] = {"game": unit["game"], "series": unit["series"],
                                    "queries": [], "n_written": 0, "completeness_ok": True}
        for q in unit["queries"]:
            s = runner(tickers=list(q["tickers"]), min_ts=q["min_ts"], max_ts=q["max_ts"],
                       store=store, client=client, max_calls=max_calls,
                       min_interval=min_interval)
            entry["queries"].append({
                "day": q["day"], "n_tickers": len(q["tickers"]),
                "min_ts": q["min_ts"], "max_ts": q["max_ts"],
                "n_pulled": s["n_pulled"], "n_lines": s["n_lines"],
                "n_duplicate": s["n_duplicate"], "call_count": s["call_count"],
                "completeness_ok": s["completeness_ok"], "truncated": s["truncated"],
                "n_truncated_queries": s["n_truncated_queries"],
                "tickers": list(q["tickers"]),
            })
            entry["n_written"] = int(entry["n_written"]) + s["n_lines"]
            n_written += s["n_lines"]
            n_pulled += s["n_pulled"]
            n_calls += s["call_count"]
            if not s["completeness_ok"]:
                entry["completeness_ok"] = False
        if not entry["completeness_ok"]:
            n_incomplete += 1
        manifest.append(entry)
        if verbose:
            mb = (family_bytes(store) - start_bytes) / (1024 * 1024)
            print(f"[phase1] {i+1}/{len(plan)} {unit['game']}: "
                  f"+{entry['n_written']} line(s), {mb:.1f} MB used", flush=True)

    end_bytes = family_bytes(store)
    return {
        "schema_version": SCHEMA_VERSION,
        "verdict_class": "DATA-COLLECTION (no P&L, no CI, no registry flip)",
        "price_source_tag": "broker_truth",
        "cap_bytes": cap_bytes,
        "cap_mb": round(cap_bytes / (1024 * 1024), 3),
        "start_bytes": start_bytes,
        "end_bytes": end_bytes,
        "bytes_written": end_bytes - start_bytes,
        "mb_written": round((end_bytes - start_bytes) / (1024 * 1024), 3),
        "stopped_reason": stopped_reason,
        "n_games_planned": len(plan),
        "n_games_pulled": len(manifest),
        "n_games_incomplete": n_incomplete,
        "n_prints_pulled": n_pulled,
        "n_lines_written": n_written,
        "n_api_calls": n_calls,
        "elapsed_s": round(time.time() - t0, 1),
        "coverage_is_ticker_scoped": True,
        "coverage_note": ("day-files are a ticker-scoped backfill of the listed games only, "
                          "NOT complete venue days; join against `manifest`, never against "
                          "a whole dt= file assumed complete"),
        "manifest": manifest,
    }


def run(tape_root: Path = DEFAULT_TAPE_ROOT,
        days: Sequence[str] = DEFAULT_DAYS,
        cap_mb: float = DEFAULT_CAP_MB,
        max_games: Optional[int] = None,
        dry_run: bool = False,
        store: Optional[Path] = None,
        client=None,
        resolver: Callable = resolve_market_results,
        runner: Callable = kt.run,
        max_calls: int = DEFAULT_MAX_CALLS,
        min_interval: float = 0.25,
        verbose: bool = True) -> Dict[str, object]:
    games, stats = eligible_ticker_days(tape_root, days, resolver=resolver)
    order = order_games(games)
    plan = plan_pulls(games, order)
    report: Dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "scripts/q52_q54_trades_backfill_phase1.py",
        "window_days": list(days),
        "population": stats,
        "plan_preview": [{"game": p["game"], "n_ticker_days": p["n_ticker_days"]}
                         for p in plan[:20]],
    }
    if dry_run:
        report["dry_run"] = True
        report["execution"] = None
        return report
    report["dry_run"] = False
    report["execution"] = execute(
        plan, store=store, cap_bytes=int(cap_mb * 1024 * 1024), max_games=max_games,
        client=client, max_calls=max_calls, min_interval=min_interval, runner=runner,
        verbose=verbose)
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cap-mb", type=float, default=DEFAULT_CAP_MB)
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--days", nargs="*", default=list(DEFAULT_DAYS))
    ap.add_argument("--dry-run", action="store_true",
                    help="plan from committed tape only; no network, no writes")
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    ap.add_argument("--min-interval", type=float, default=0.25)
    ap.add_argument("--json", default=str(REPO_ROOT / "reports" /
                                          "q52_q54_trades_backfill_phase1_selection.json"),
                    help="report path, or '-' for stdout. The committed reports are "
                         "`..._selection.json` (the 40MB-cap-bound selection pass that chose "
                         "the 17 games) and `..._repair.json` (the L314 truncation repair); "
                         "both are kept because the selection rule is provenance (L315).")
    args = ap.parse_args(argv)

    rep = run(days=args.days, cap_mb=args.cap_mb, max_games=args.max_games,
              dry_run=args.dry_run, max_calls=args.max_calls,
              min_interval=args.min_interval)
    text = json.dumps(rep, indent=2, sort_keys=True)
    if args.json == "-":
        print(text)
    else:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"[phase1] report -> {out}")
    ex = rep.get("execution")
    if ex:
        print(f"[phase1] {ex['n_games_pulled']}/{ex['n_games_planned']} game(s), "
              f"{ex['n_lines_written']} new line(s), {ex['mb_written']} MB, "
              f"stopped: {ex['stopped_reason']}, "
              f"{ex['n_games_incomplete']} game(s) with an incomplete query")
        return 0 if ex["n_games_incomplete"] == 0 else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
