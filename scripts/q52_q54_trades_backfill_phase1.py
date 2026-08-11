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
from core.push_limits import PUSH_SIZE_GATE_BYTES  # noqa: E402
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

# PER-DAY-FILE byte ceiling (L315 follow-up, the gap this item's own 2026-08-09 status flagged
# for "the next run"). The `cap_bytes` above is a FAMILY-TOTAL budget; GitHub's push block is
# PER FILE. On 2026-08-09 the family total sat comfortably inside its 50MB cap while
# `tape/kalshi_trades/dt=2026-07-07.jsonl` reached 109,151,185 bytes, GitHub rejected the push
# at pre-receive, and a whole 35,144-line game had to be dropped BY HAND after it had already
# been fetched. A family-total cap cannot see that: the heaviest day absorbs a
# disproportionate share of every league-diverse prefix. The ceiling itself is imported from
# `core/push_limits.py`, the single sanctioned site — never hand-rolled here.
DEFAULT_DAY_FILE_CAP_BYTES = PUSH_SIZE_GATE_BYTES

# Conservative bootstrap for "how many bytes will this game add to that day-file?" before any
# game in THIS pass has landed and supplied a measurement. Deliberately larger than any
# ticker-day measured so far (the heaviest single game observed, `KXWCGAME-26JUL07ARGEGY`, was
# 35,144 lines ~= 21MB across 3 outcome legs), so the FIRST game aimed at a near-limit day is
# skipped rather than risked. Once a game lands, the estimator switches to the MAX realized
# bytes-per-ticker-day of this pass — still the pessimistic order statistic, not the mean,
# because one heavy game is exactly the case the guard exists to stop.
BOOTSTRAP_BYTES_PER_TICKER_DAY = 25_000_000


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
def guard_preview(plan: Sequence[Mapping[str, object]],
                  store: Optional[Path] = None,
                  day_file_cap_bytes: int = DEFAULT_DAY_FILE_CAP_BYTES,
                  bytes_per_ticker_day: int = BOOTSTRAP_BYTES_PER_TICKER_DAY,
                  ) -> Dict[str, object]:
    """OFFLINE preview of the per-day-file guard against the CURRENT tape, no network.

    Answers "which games would the guard refuse to start today, and which days are the
    blocked ones?" using the pessimistic bootstrap estimate — i.e. the state the guard is in
    at the top of a fresh pass, before any measurement exists. Reported in `--dry-run` so the
    guard's effect on the selection is inspectable before anything is fetched.
    """
    store = Path(store) if store is not None else kt.TAPE
    sizes = day_file_sizes(store)
    blocked_days: Dict[str, int] = {}
    skipped: List[str] = []
    for unit in plan:
        projected = project_day_file_bytes(unit, sizes, bytes_per_ticker_day)
        breach = sorted(d for d, b in projected.items() if b >= day_file_cap_bytes)
        if breach:
            skipped.append(str(unit["game"]))
            for d in breach:
                blocked_days[d] = blocked_days.get(d, 0) + 1
    return {
        "day_file_cap_bytes": int(day_file_cap_bytes),
        "bytes_per_ticker_day_estimate": int(bytes_per_ticker_day),
        "estimate_source": "bootstrap_no_measurement_yet",
        "current_day_bytes": dict(sorted(sizes.items())),
        "n_games_planned": len(plan),
        "n_games_would_skip": len(skipped),
        "games_would_skip": sorted(skipped),
        "blocked_days": dict(sorted(blocked_days.items())),
    }



def family_bytes(store: Path) -> int:
    store = Path(store)
    if not store.exists():
        return 0
    return sum(p.stat().st_size for p in store.glob("dt=*.jsonl"))


def day_file_sizes(store: Path) -> Dict[str, int]:
    """`{day: bytes}` for every `dt=<day>.jsonl` in the store. Missing store -> {}."""
    store = Path(store)
    if not store.exists():
        return {}
    out: Dict[str, int] = {}
    for p in store.glob("dt=*.jsonl"):
        out[p.name[len("dt="):-len(".jsonl")]] = p.stat().st_size
    return out


def days_of(unit: Mapping[str, object]) -> Dict[str, int]:
    """`{day: n_ticker_days}` a planned game unit will write into."""
    out: Dict[str, int] = {}
    for q in unit["queries"]:                     # type: ignore[index]
        out[str(q["day"])] = out.get(str(q["day"]), 0) + len(q["tickers"])
    return out


def project_day_file_bytes(unit: Mapping[str, object],
                           sizes: Mapping[str, int],
                           bytes_per_ticker_day: int) -> Dict[str, int]:
    """Projected size of each day-file this game targets, if the game were pulled.

    Projection, not measurement — and the guard treats it as an upper bound on purpose. An
    under-projection is the only failure mode that matters here (it lets a wedging game start),
    so the estimator is the pessimistic order statistic, never the mean.
    """
    return {day: int(sizes.get(day, 0)) + n * int(bytes_per_ticker_day)
            for day, n in days_of(unit).items()}


def execute(plan: Sequence[Mapping[str, object]],
            store: Optional[Path] = None,
            cap_bytes: int = int(DEFAULT_CAP_MB * 1024 * 1024),
            max_games: Optional[int] = None,
            client=None,
            max_calls: int = DEFAULT_MAX_CALLS,
            min_interval: float = 0.25,
            runner: Callable = kt.run,
            day_file_cap_bytes: int = DEFAULT_DAY_FILE_CAP_BYTES,
            bootstrap_bytes_per_ticker_day: int = BOOTSTRAP_BYTES_PER_TICKER_DAY,
            verbose: bool = True) -> Dict[str, object]:
    """Pull whole games until the DECLARED byte cap is reached. Measured, never extrapolated.

    The family-total cap is checked BEFORE starting a game and again after it lands, so a game
    is either fully pulled or not started — a half-pulled game would be a silently biased unit.

    TWO caps, because they answer different questions (the 2026-08-09 lesson):
      * `cap_bytes` bounds how much tape this pass adds in TOTAL — a budget.
      * `day_file_cap_bytes` bounds any SINGLE `dt=<day>.jsonl` — a push-wedge guard. GitHub
        rejects a whole push over a per-FILE limit, and the rejection survives in the commit,
        so the family total staying inside budget says nothing about whether the push will
        land. The guard is PREVENTIVE (project each target day-file before starting a game and
        skip the game if the projection breaches) and, because a projection can be wrong, also
        POST-CHECKED against measured bytes after each game lands.

    A skip does NOT stop the pass: the ordering is league round-robin, so a game aimed at the
    one overweight day should not veto the games aimed at empty days behind it. Skips are
    counted and named in `skipped_day_file_cap`, never silent.

    This function NEVER deletes or truncates tape. If the post-check finds a day-file over the
    ceiling anyway, it stops and reports exactly which whole game to drop (L315 whole-game
    atomicity) — the manual repair the 2026-08-09 run had to improvise, now named for the
    operator instead of discovered at `git push`.
    """
    store = Path(store) if store is not None else kt.TAPE
    if client is None and runner is kt.run:
        # ONE client for the whole pass: `kt.run` would otherwise build a fresh one per
        # query and each would carry its own politeness timer, so the min-interval would
        # never actually bind across a 300-query backfill.
        from validation.v3_market import Kalshi, _load_venue_cfg
        client = Kalshi(_load_venue_cfg()["api_base"], min_interval=min_interval)
    start_bytes = family_bytes(store)
    start_day_bytes = day_file_sizes(store)
    manifest: List[Dict[str, object]] = []
    skipped: List[Dict[str, object]] = []
    overflow: Optional[Dict[str, object]] = None
    n_written = 0
    n_pulled = 0
    n_calls = 0
    n_incomplete = 0
    n_ticker_days_pulled = 0
    max_bytes_per_ticker_day = 0
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
        # PREVENTIVE per-day-file guard. `max_bytes_per_ticker_day` is 0 until a game lands,
        # so the first decision uses the deliberately pessimistic bootstrap.
        est = max_bytes_per_ticker_day or bootstrap_bytes_per_ticker_day
        sizes_now = day_file_sizes(store)
        projected = project_day_file_bytes(unit, sizes_now, est)
        breach = {d: b for d, b in projected.items() if b >= day_file_cap_bytes}
        if breach:
            skipped.append({
                "game": unit["game"], "series": unit["series"],
                "reason": "day_file_cap",
                "bytes_per_ticker_day_estimate": int(est),
                "estimate_source": ("measured_max_this_pass" if max_bytes_per_ticker_day
                                    else "bootstrap_no_measurement_yet"),
                "projected_day_bytes": {d: int(b) for d, b in sorted(projected.items())},
                "current_day_bytes": {d: int(sizes_now.get(d, 0))
                                      for d in sorted(projected)},
                "breaching_days": sorted(breach),
            })
            if verbose:
                print(f"[phase1] SKIP {unit['game']}: would take "
                      f"{sorted(breach)} past the {day_file_cap_bytes:,}B day-file cap",
                      flush=True)
            continue
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

        # Re-measure and refresh the estimator from what this game ACTUALLY cost per
        # ticker-day. `max`, not mean: one heavy game is the case the guard exists to stop.
        sizes_after = day_file_sizes(store)
        game_days = days_of(unit)
        for day, n_td in game_days.items():
            delta = int(sizes_after.get(day, 0)) - int(sizes_now.get(day, 0))
            if n_td > 0 and delta > 0:
                max_bytes_per_ticker_day = max(max_bytes_per_ticker_day, delta // n_td)
        n_ticker_days_pulled += sum(game_days.values())

        if verbose:
            mb = (family_bytes(store) - start_bytes) / (1024 * 1024)
            print(f"[phase1] {i+1}/{len(plan)} {unit['game']}: "
                  f"+{entry['n_written']} line(s), {mb:.1f} MB used", flush=True)

        # POST-CHECK against MEASURED bytes: the projection above can be wrong, and being
        # wrong in the unsafe direction is precisely the 2026-08-09 failure. Stop rather than
        # keep appending, and name the whole game to drop instead of leaving it to `git push`.
        # Scoped to the days THIS game wrote to. A whole-store scan would also flag a
        # day-file that was already over the ceiling before the pass began and that this game
        # never touched — stopping the pass and blaming the wrong game for it.
        over = {d: int(sizes_after.get(d, 0)) for d in game_days
                if int(sizes_after.get(d, 0)) >= day_file_cap_bytes}
        if over:
            overflow = {
                "game": unit["game"],
                "day_bytes": dict(sorted(over.items())),
                "cap_bytes": int(day_file_cap_bytes),
                "remediation": (
                    f"day-file cap breached on {sorted(over)} AFTER `{unit['game']}` "
                    f"landed — those are days this game itself wrote to. The append-only-safe "
                    f"repair is to drop that WHOLE game's lines from the working tree before "
                    f"committing (every outcome leg, ticker-prefix match — whole-game "
                    f"atomicity, L315), or to shard the family's next writes into a new file. "
                    f"Never truncate or reorder already-committed lines."
                ),
            }
            stopped_reason = "day_file_cap_exceeded"
            if verbose:
                print(f"[phase1] STOP: {sorted(over)} at/over the "
                      f"{day_file_cap_bytes:,}B day-file cap after {unit['game']}", flush=True)
            break

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
        "day_file_cap_bytes": int(day_file_cap_bytes),
        "day_file_bytes_start": dict(sorted(start_day_bytes.items())),
        "day_file_bytes_end": dict(sorted(day_file_sizes(store).items())),
        "n_games_skipped_day_file_cap": len(skipped),
        "skipped_day_file_cap": skipped,
        "day_file_overflow": overflow,
        "max_bytes_per_ticker_day_measured": int(max_bytes_per_ticker_day),
        "n_ticker_days_pulled": n_ticker_days_pulled,
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
        day_file_cap_bytes: int = DEFAULT_DAY_FILE_CAP_BYTES,
        bootstrap_bytes_per_ticker_day: int = BOOTSTRAP_BYTES_PER_TICKER_DAY,
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
        report["day_file_guard_preview"] = guard_preview(
            plan, store=store, day_file_cap_bytes=day_file_cap_bytes,
            bytes_per_ticker_day=bootstrap_bytes_per_ticker_day)
        return report
    report["dry_run"] = False
    report["execution"] = execute(
        plan, store=store, cap_bytes=int(cap_mb * 1024 * 1024), max_games=max_games,
        client=client, max_calls=max_calls, min_interval=min_interval, runner=runner,
        day_file_cap_bytes=day_file_cap_bytes,
        bootstrap_bytes_per_ticker_day=bootstrap_bytes_per_ticker_day, verbose=verbose)
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cap-mb", type=float, default=DEFAULT_CAP_MB,
                    help="FAMILY-TOTAL byte budget for this pass (a budget)")
    ap.add_argument("--day-file-cap-bytes", type=int, default=DEFAULT_DAY_FILE_CAP_BYTES,
                    help="PER-DAY-FILE ceiling (a push-wedge guard, not a budget): a game "
                         "whose projected write would take any target dt=<day>.jsonl to or "
                         "past this is skipped, not started. Default is "
                         "core.push_limits.PUSH_SIZE_GATE_BYTES.")
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
              min_interval=args.min_interval,
              day_file_cap_bytes=args.day_file_cap_bytes)
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
              f"{ex['n_games_incomplete']} game(s) with an incomplete query, "
              f"{ex['n_games_skipped_day_file_cap']} skipped on the day-file cap")
        if ex["day_file_overflow"]:
            print(f"[phase1] DAY-FILE CAP BREACHED: "
                  f"{ex['day_file_overflow']['remediation']}")
            return 1
        return 0 if ex["n_games_incomplete"] == 0 else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
