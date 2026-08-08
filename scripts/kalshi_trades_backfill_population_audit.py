#!/usr/bin/env python3
"""KALSHI_TRADES BACKFILL-POPULATION AUDIT: is the S78/S79 data gate a CALENDAR gate or an
UN-RUN BACKFILL gate?

Read-only over committed tape. Fully offline by default (NO network in any code path this
module owns). Computes NO settlement-conditioned P&L, NO mean, NO bootstrap, NO CI, NO
fill rate and NO verdict about any strategy. It is a DATA-ADEQUACY instrument in the
`scripts/q51_m3_preflight.py` / `scripts/q51_m3_fill_projection.py` lane, not a probe, so
nothing it prints is verdict-class.

WHY THIS EXISTS
---------------
Two registered idea-stage strategies are parked as `collect-and-revisit`:

  * S78 / Q52 (toxicity-filtered selective maker) — gate stated as "needs more
    `tape/kalshi_trades/` days".
  * S79 / Q54 (aggressor-flow continuation taker) — gate stated 2026-08-07 as
    `below_min_units`: 9 distinct settled games joinable, below the L41 floor of 10.

Both gates read as CALENDAR gates: wait, and the data will accrue. Two facts already on the
record say otherwise, and nothing had put them together:

  1. `collection/kalshi_trades.py` reads the PUBLIC, unauthenticated, ticker- and
     window-scoped `GET /markets/trades`. Q51 milestone 1 (2026-08-04) measured that its
     history reaches back to at least 2026-06-20 — i.e. it PREDATES the oldest committed
     book tape. Trade prints for a past day are a pull, not a wait.
  2. The collector is deliberately NOT wired into `collection/hourly_pass.py` (Q51-m1 made
     that call on the L221/L222 write-path lane). So no scheduled writer exists: waiting
     produces exactly zero additional trade days, forever.

Put together, "collect and revisit" describes work nobody has run, not time nobody has
waited. This module measures HOW MUCH of that work is available from tape that is already
committed, so the size of the un-run backfill is a number instead of an intuition.

WHAT IT MEASURES
----------------
The joinable-unit funnel, per committed `tape/orderbook_depth/` day and in aggregate:

    distinct tickers in book tape
      -> tickers with >= 2 snapshots that day        (the fill-sim's own interval predicate,
                                                      imported from scripts/q51_maker_fillsim,
                                                      never re-guessed)
      -> of those, sports-game markets               (S79's population; is_sports_game_market)
      -> of those, tickers a COMMITTED settlement source already resolves to a BINARY result
         (`core.settlement_sources.resolve_market_results` — all NINE declared families, the
          L300/Q54 correction; `broker_truth`)
      -> rolled up to DISTINCT GAMES (`game_of`), which is S79's resample unit (L6).

The last number is the honest count of resample units that a trade-print backfill — and
nothing else — would unlock.

WHAT IT DOES NOT CLAIM
----------------------
  * It does NOT claim those units will produce prints. Ticker-level print incidence was
    measured once, at 42/200 = 21.0% of sampled tickers on 2026-08-03 (Q51-m1). This module
    reports the units-after-haircut arithmetic as an explicitly-labelled PROJECTION with its
    `basis` attached, never as a measurement, and refuses to publish a single point estimate
    without the rate it used.
  * It does NOT claim an edge, a fill rate, or a direction. `mean`, `ci`, `pnl`, `edge` and
    `won` appear nowhere in the emitted report and a test asserts that.
  * It does NOT flip any registry status. S78 and S79 stay exactly where they are; only the
    DESCRIPTION of what their gate is made of changes.
  * Settlement coverage from committed tape is itself partial and lumpy (whole book days
    resolve to zero settled games because no probe ever cached those markets). That is
    reported per-day, never averaged away — and it is the second half of the same finding:
    settlement is fetched by an unauthenticated public `GET /markets/{ticker}` too
    (`scripts/q51_maker_fillsim.build_settlement_cache`), so it is equally a pull.

Run:
    python3 scripts/kalshi_trades_backfill_population_audit.py
    python3 scripts/kalshi_trades_backfill_population_audit.py --days dt=2026-08-03 --json -
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.settlement_sources import declared_source_names, resolve_market_results  # noqa: E402
from scripts.q51_maker_fillsim import game_of, is_sports_game_market  # noqa: E402

DEFAULT_TAPE_ROOT = REPO_ROOT / "tape"
DEPTH_FAMILY = "orderbook_depth"
TRADES_FAMILY = "kalshi_trades"
MIN_SNAPSHOTS = 2           # scripts/q51_maker_fillsim.build_rows: len(ss) < 2 -> dropped
L41_UNIT_FLOOR = 10         # the project's minimum resample-unit count

# Ticker-level print incidence MEASURED once, on the only committed trade day (Q51-m1,
# findings/2026-08-04-q51-trade-print-surface-wall-b-half-broken.md): 42 of 200 sampled
# book tickers carried >= 1 print. Used ONLY to label a projection, never as a measurement.
MEASURED_TICKER_PRINT_RATE = 42.0 / 200.0
MEASURED_TICKER_PRINT_RATE_BASIS = (
    "42/200 sampled tickers with >=1 print on dt=2026-08-03 (Q51 milestone 1, "
    "findings/2026-08-04-q51-trade-print-surface-wall-b-half-broken.md); a whole-universe "
    "stride-13 sample, NOT a sports-only rate"
)

# The callers that could schedule a collector. `kalshi_trades` appearing in NONE of them is
# the writer-census result this module exists partly to pin.
SCHEDULED_CALLER_FILES: Tuple[str, ...] = (
    "collection/hourly_pass.py",
    "collection/burst_capture.py",
)


# --------------------------------------------------------------------------- #
# writer census
# --------------------------------------------------------------------------- #
def writer_census(repo_root: Path = REPO_ROOT,
                  caller_files: Sequence[str] = SCHEDULED_CALLER_FILES,
                  family: str = TRADES_FAMILY) -> Dict[str, object]:
    """Which scheduled callers, if any, can write `tape/<family>/`?

    Text scan of each caller file for the module name. A file that does not exist is
    reported as `absent`, never silently counted as "no reference" (the difference matters:
    absent means the census could not look, not that it looked and found nothing).
    """
    referencing: List[str] = []
    absent: List[str] = []
    scanned: List[str] = []
    pat = re.compile(re.escape(family))
    for rel in caller_files:
        p = repo_root / rel
        if not p.exists():
            absent.append(rel)
            continue
        scanned.append(rel)
        try:
            if pat.search(p.read_text(errors="replace")):
                referencing.append(rel)
        except OSError:
            absent.append(rel)
    return {
        "family": family,
        "callers_scanned": tuple(scanned),
        "callers_absent": tuple(absent),
        "callers_referencing": tuple(referencing),
        "has_scheduled_writer": bool(referencing),
        "note": ("A False here means waiting adds zero days: the only writer is a manual "
                 "`python -m collection.kalshi_trades` invocation."),
    }


# --------------------------------------------------------------------------- #
# committed trade-tape inventory
# --------------------------------------------------------------------------- #
def trade_tape_inventory(tape_root: Path = DEFAULT_TAPE_ROOT) -> Dict[str, object]:
    """Days, lines, distinct tickers, duplicate trade_ids and the source-tag census of
    `tape/kalshi_trades/`. Malformed lines are counted, never dropped silently (L10)."""
    d = Path(tape_root) / TRADES_FAMILY
    files = sorted(d.glob("dt=*.jsonl")) if d.exists() else []
    tickers: set = set()
    trade_ids: set = set()
    tags: Counter = Counter()
    n_lines = 0
    n_bad = 0
    n_dup = 0
    for path in files:
        with path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                n_lines += 1
                try:
                    rec = json.loads(line)
                except (ValueError, TypeError):
                    n_bad += 1
                    continue
                tk = rec.get("ticker")
                if isinstance(tk, str):
                    tickers.add(tk)
                tid = rec.get("trade_id")
                if isinstance(tid, str):
                    if tid in trade_ids:
                        n_dup += 1
                    trade_ids.add(tid)
                tags[str(rec.get("price_source_tag") or "synthetic")] += 1
    return {
        "days": tuple(p.name[3:-6] for p in files),
        "n_days": len(files),
        "n_lines": n_lines,
        "n_malformed_lines": n_bad,
        "n_distinct_tickers": len(tickers),
        "n_distinct_trade_ids": len(trade_ids),
        "n_duplicate_trade_ids": n_dup,
        "price_source_tag_census": dict(tags),
    }


# --------------------------------------------------------------------------- #
# book-tape scan
# --------------------------------------------------------------------------- #
def depth_day_files(tape_root: Path = DEFAULT_TAPE_ROOT,
                    days: Optional[Iterable[str]] = None) -> List[Tuple[str, Path]]:
    """[(day, path)] for `tape/orderbook_depth/dt=*.jsonl`, ascending. `days` accepts either
    `dt=YYYY-MM-DD` or bare `YYYY-MM-DD`."""
    d = Path(tape_root) / DEPTH_FAMILY
    if not d.exists():
        return []
    wanted = None
    if days is not None:
        wanted = {s[3:] if s.startswith("dt=") else s for s in days}
    out = []
    for p in sorted(d.glob("dt=*.jsonl")):
        day = p.name[3:-6]
        if wanted is None or day in wanted:
            out.append((day, p))
    return out


def scan_depth_day(path: Path) -> Tuple[Counter, Counter]:
    """(snapshots per ticker, two-sided snapshots per ticker) for one committed day-file.

    Two-sided means BOTH `best_yes_bid` and `best_no_bid` are numeric and > 0 — the same
    condition `q51_maker_fillsim.build_rows` uses to reject an interval as `not_two_sided`.
    Streaming: one pass, no whole-file load (`orderbook_depth` day-files reach 30MB).
    """
    snaps: Counter = Counter()
    two_sided: Counter = Counter()
    with Path(path).open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            tk = rec.get("ticker")
            if not isinstance(tk, str):
                continue
            snaps[tk] += 1
            yb, nb = rec.get("best_yes_bid"), rec.get("best_no_bid")
            if isinstance(yb, (int, float)) and isinstance(nb, (int, float)) \
                    and yb > 0 and nb > 0:
                two_sided[tk] += 1
    return snaps, two_sided


def eligible_tickers(snaps: Mapping[str, int], min_snapshots: int = MIN_SNAPSHOTS) -> List[str]:
    """Tickers with enough snapshots to form at least one interval."""
    return sorted(t for t, c in snaps.items() if c >= min_snapshots)


# --------------------------------------------------------------------------- #
# the funnel
# --------------------------------------------------------------------------- #
def funnel(tape_root: Path = DEFAULT_TAPE_ROOT,
           days: Optional[Iterable[str]] = None,
           min_snapshots: int = MIN_SNAPSHOTS) -> Dict[str, object]:
    """Per-day and aggregate joinable-unit funnel. One settlement resolution over the UNION
    of eligible tickers (not per-day), so a ticker quoted on many days is resolved once."""
    per_day: List[Dict[str, object]] = []
    day_eligible: Dict[str, List[str]] = {}
    union_all: set = set()
    union_eligible: set = set()
    for day, path in depth_day_files(tape_root, days):
        snaps, two_sided = scan_depth_day(path)
        elig = eligible_tickers(snaps, min_snapshots)
        day_eligible[day] = elig
        union_all |= set(snaps)
        union_eligible |= set(elig)
        sports = [t for t in elig if is_sports_game_market(t)]
        per_day.append({
            "day": day,
            "n_tickers": len(snaps),
            "n_eligible": len(elig),
            "n_eligible_two_sided": sum(1 for t in elig if two_sided.get(t, 0) >= min_snapshots),
            "n_sports_eligible": len(sports),
            "n_sports_games_eligible": len({game_of(t) for t in sports}),
        })

    rep = resolve_market_results(sorted(union_eligible), root=str(tape_root))
    settled = set(rep.resolved)
    for row in per_day:
        sports_settled = [t for t in day_eligible[row["day"]]
                          if is_sports_game_market(t) and t in settled]
        row["n_sports_eligible_settled"] = len(sports_settled)
        row["n_sports_games_settled"] = len({game_of(t) for t in sports_settled})

    sports_elig = {t for t in union_eligible if is_sports_game_market(t)}
    sports_settled_tickers = sports_elig & settled
    settled_games = {game_of(t) for t in sports_settled_tickers}
    zero_settlement_days = tuple(r["day"] for r in per_day if r["n_sports_games_settled"] == 0)

    return {
        "per_day": per_day,
        "aggregate": {
            "n_days": len(per_day),
            "n_tickers_union": len(union_all),
            "n_eligible_union": len(union_eligible),
            "n_sports_eligible_union": len(sports_elig),
            "n_sports_games_eligible_union": len({game_of(t) for t in sports_elig}),
            "n_sports_eligible_settled_union": len(sports_settled_tickers),
            "n_sports_games_settled_union": len(settled_games),
        },
        "settlement": {
            "sources_scanned": list(rep.sources_scanned),
            "sources_absent_on_disk": list(rep.sources_absent_on_disk),
            "per_source_hits": dict(rep.per_source_hits),
            "requested": rep.requested,
            "n_resolved_any_family": len(rep.resolved),
            "n_non_binary": len(rep.non_binary),
            "n_listed_unsettled": len(rep.listed_unsettled),
            "n_unresolved": len(rep.unresolved),
            "price_source_tag": "broker_truth",
            "days_with_zero_settled_sports_games": zero_settlement_days,
            "note": ("Settlement coverage is lumpy because it was harvested per-probe, not "
                     "systematically; a zero day means nobody cached those markets, not "
                     "that they did not settle. It is fetched by an unauthenticated public "
                     "GET /markets/{ticker} (q51_maker_fillsim.build_settlement_cache), so "
                     "it is a pull too."),
        },
    }


def unit_projection(n_units: int,
                    ticker_print_rate: float = MEASURED_TICKER_PRINT_RATE) -> Dict[str, object]:
    """PROJECTION, not a measurement: units surviving a ticker-level print-incidence haircut.

    Always carries its `basis` and its own `is_projection` flag, so the number can never be
    quoted as a measured population (CLAUDE.md trust-default rule).
    """
    projected = n_units * float(ticker_print_rate)
    return {
        "is_projection": True,
        "price_source_tag": "synthetic",
        "input_units": n_units,
        "ticker_print_rate": float(ticker_print_rate),
        "basis": MEASURED_TICKER_PRINT_RATE_BASIS,
        "projected_units": projected,
        "l41_floor": L41_UNIT_FLOOR,
        "projected_multiple_of_floor": projected / L41_UNIT_FLOOR if L41_UNIT_FLOOR else None,
        "caveat": ("A game unit survives if ANY of its tickers printed, so a ticker-level "
                   "rate applied to game units is a LOWER-bound-flavoured heuristic, not an "
                   "unbiased estimate. Reported to bound the order of magnitude only."),
    }


def gate_class(n_units: int, has_scheduled_writer: bool,
               floor: int = L41_UNIT_FLOOR) -> Dict[str, object]:
    """Name the gate: does waiting help, and is the population already there?"""
    clears = n_units >= floor
    if has_scheduled_writer:
        cls = "calendar" if not clears else "open"
    else:
        cls = "backfill" if clears else "backfill_insufficient"
    return {
        "gate_class": cls,
        "n_units_available_from_committed_tape": n_units,
        "l41_floor": floor,
        "multiple_of_floor": (n_units / floor) if floor else None,
        "waiting_adds_days": bool(has_scheduled_writer),
        "reading": {
            "backfill": "population already exists in committed tape; only an un-run pull "
                        "stands between it and a testable join. Waiting adds nothing.",
            "backfill_insufficient": "no scheduled writer AND the committed population is "
                                     "below the floor: neither waiting nor a pull of the "
                                     "current tape suffices.",
            "calendar": "a scheduled writer exists and the population is below the floor: "
                        "waiting genuinely accrues units.",
            "open": "population clears the floor and collection is live: not gated.",
        }[cls],
    }


def run(tape_root: Path = DEFAULT_TAPE_ROOT,
        days: Optional[Iterable[str]] = None,
        repo_root: Path = REPO_ROOT) -> Dict[str, object]:
    census = writer_census(repo_root)
    inv = trade_tape_inventory(tape_root)
    fun = funnel(tape_root, days)
    units = int(fun["aggregate"]["n_sports_games_settled_union"])
    return {
        "schema_version": "kalshi_trades_backfill_population_audit.v1",
        "generated_by": "scripts/kalshi_trades_backfill_population_audit.py",
        "offline": True,
        "writer_census": census,
        "trade_tape": inv,
        "funnel": fun,
        "projection": unit_projection(units),
        "gate": gate_class(units, bool(census["has_scheduled_writer"])),
        "verdict_class": "data_adequacy_only",
        "not_computed": ["mean", "ci95", "pnl", "fill_rate", "edge", "won"],
    }


def _format(report: Mapping) -> str:
    a = report["funnel"]["aggregate"]
    g = report["gate"]
    c = report["writer_census"]
    inv = report["trade_tape"]
    pj = report["projection"]
    lines = [
        "kalshi_trades backfill-population audit (data-adequacy only; no CI, no P&L)",
        f"  scheduled writer for tape/kalshi_trades/: {c['has_scheduled_writer']} "
        f"(scanned {', '.join(c['callers_scanned']) or 'nothing'})",
        f"  committed trade tape: {inv['n_days']} day(s), {inv['n_lines']} lines, "
        f"{inv['n_distinct_tickers']} tickers, dup trade_ids={inv['n_duplicate_trade_ids']}",
        f"  book tape: {a['n_days']} days, {a['n_tickers_union']} distinct tickers, "
        f"{a['n_eligible_union']} with >={MIN_SNAPSHOTS} snapshots",
        f"  sports-game eligible: {a['n_sports_eligible_union']} tickers / "
        f"{a['n_sports_games_eligible_union']} games",
        f"  ALREADY SETTLED (broker_truth, committed sources): "
        f"{a['n_sports_eligible_settled_union']} tickers / "
        f"{a['n_sports_games_settled_union']} games",
        f"  gate class: {g['gate_class']} "
        f"({g['n_units_available_from_committed_tape']} units = "
        f"{g['multiple_of_floor']:.1f}x the L41 floor of {g['l41_floor']})",
        f"  projection (synthetic, print-incidence haircut {pj['ticker_print_rate']:.3f}): "
        f"~{pj['projected_units']:.0f} units = {pj['projected_multiple_of_floor']:.1f}x floor",
        f"  {g['reading']}",
    ]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tape-root", default=str(DEFAULT_TAPE_ROOT))
    ap.add_argument("--days", nargs="*", default=None,
                    help="restrict to these days (dt=YYYY-MM-DD or YYYY-MM-DD)")
    ap.add_argument("--json", default=str(REPO_ROOT / "reports" /
                                          "kalshi_trades_backfill_population.json"),
                    help="path for the JSON report, or '-' for stdout")
    args = ap.parse_args(list(argv) if argv is not None else None)

    report = run(Path(args.tape_root), args.days)
    print(_format(report))
    if args.json == "-":
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
        print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
