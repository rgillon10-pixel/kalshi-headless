#!/usr/bin/env python3
"""l338_trend_claim_scope_audit.py — the MEASUREMENT half of lesson L338.

L338 (2026-08-11) recorded that `scripts/q51_maker_fillsim.py`'s module docstring cites a
monotone decay of the `taker_book_side` orientation-agreement rate across widening join
windows (86.8% -> 84.6% -> 70.4% at <=15min / <=60min / any-age) as corroborating evidence
that the field relationship is real rather than an artifact, and that an independent
verifier measured the OPPOSITE direction (62.99% -> 66.9% -> 69.6%, RISING) on what the
verifier described as "the FULL day tape (all 2,713 depth tickers)". L338 concluded the
corroboration argument is POPULATION-scoped.

THIS AUDIT MEASURES THE ATTRIBUTION DIRECTLY, and the attribution is different.

The two readings differ on TWO factors at once, and only one of them matters:

  * POPULATION — the probe's reconstructed 60-ticker sports universe vs. every ticker in
    the day's `orderbook_depth` file.
  * JOIN RULE — how a print is attached to a reference quote:
      `bracketed`      the probe's own rule: the print must fall strictly inside a
                       CONSECUTIVE snapshot pair (t_i, t_{i+1}], so a print after a
                       ticker's LAST snapshot, or on a ticker with a single snapshot,
                       is unmeasurable and is dropped.
      `last_preceding` nearest-preceding-quote: attach every print to the newest snapshot
                       at or before it, with no requirement that a later snapshot exist.

Run as a 2x2 factorial (population x join rule) x 3 windows x both `taker_book_side`
values. This module computes the grid and attributes the direction flip to whichever
factor actually moves it. It asserts nothing about P&L and produces no verdict, no
bootstrap and no CI: it is a MEASUREMENT over committed tape.

Provenance/tags: prints come from `tape/kalshi_trades/` (`price_source_tag`
`broker_truth`); reference quotes come from `tape/orderbook_depth/` (`best_yes_ask` is
`real_ask`, `best_yes_bid` is `real_bid`). No price here is ever treated as a fill.

READ-ONLY and FULLY OFFLINE. No network, no credentials, no order path.

Run:
    python3 scripts/l338_trend_claim_scope_audit.py
    python3 scripts/l338_trend_claim_scope_audit.py --json reports/l338_trend_claim_scope.json
"""
from __future__ import annotations

import argparse
import bisect
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.io import REPO_ROOT  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402

#: the day Q51 milestone 2/3 ran on, and the only day carrying both tapes concurrently.
DAY = "2026-08-03"
DEPTH_TAPE = REPO_ROOT / "tape" / "orderbook_depth"
TRADES_TAPE = REPO_ROOT / "tape" / "kalshi_trades"
REPORT_PATH = REPO_ROOT / "reports" / "l338_trend_claim_scope.json"

#: the three join windows the disputed claim is stated over, in seconds.
WINDOWS_S: Tuple[int, ...] = (900, 3600, 10 ** 9)
WINDOW_LABELS = {900: "<=15min", 3600: "<=60min", 10 ** 9: "any_age"}

#: `taker_book_side` values, and the direction each one is expected to AGREE with under
#: the corrected orientation (a taker carrying a BID is a buyer and lifts the ASK).
#: Named, never bare literals at the comparison site — the inverted reading is the exact
#: bug the Q51 correction caught.
TAKER_BUYS = "bid"
TAKER_SELLS = "ask"
AGREEMENT_DIRECTION = {TAKER_BUYS: "at_or_above_ask", TAKER_SELLS: "at_or_below_bid"}

JOIN_RULES: Tuple[str, ...] = ("bracketed", "last_preceding")
POPULATIONS: Tuple[str, ...] = ("probe_sports_sample", "full_depth_day")

_EPS = 1e-9


# ─────────────────────────────── tape readers (own code path) ───────────────────────────

def load_depth(day: str = DAY, tape_dir: Optional[Path] = None
               ) -> Tuple[List[str], Dict[str, List[Dict[str, Any]]]]:
    """Return (insertion-ordered ticker list, per-ticker time-sorted quote snapshots).

    Insertion order is load-bearing: it is the order the probe's stride sample is
    reconstructed from, so it must not be sorted or de-duplicated here.
    """
    path = (tape_dir or DEPTH_TAPE) / f"dt={day}.jsonl"
    order: List[str] = []
    snaps: Dict[str, List[Dict[str, Any]]] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        ticker = rec.get("ticker")
        if not ticker:
            continue
        if ticker not in snaps:
            snaps[ticker] = []
            order.append(ticker)
        snaps[ticker].append({
            "ts": parse_iso_utc(rec["captured_at"]).timestamp(),
            "best_yes_bid": rec.get("best_yes_bid"),
            "best_yes_ask": rec.get("best_yes_ask"),
        })
    for series in snaps.values():
        series.sort(key=lambda s: s["ts"])
    return order, snaps


def load_prints(day: str = DAY, tape_dir: Optional[Path] = None
                ) -> Dict[str, List[Dict[str, Any]]]:
    """Return per-ticker time-sorted executed prints (`broker_truth`).

    TIE-BREAK (L323): none is declared and none is needed. Every reduction downstream is
    a COUNT over all qualifying prints — no per-print selection happens anywhere in this
    module — so the order of equal-timestamp prints cannot change any number it reports.
    """
    path = (tape_dir or TRADES_TAPE) / f"dt={day}.jsonl"
    prints: Dict[str, List[Dict[str, Any]]] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        ticker = rec.get("ticker")
        if not ticker:
            continue
        prints.setdefault(ticker, []).append({
            "ts": parse_iso_utc(rec["created_time"]).timestamp(),
            "taker_book_side": rec.get("taker_book_side"),
            "yes_price": rec.get("yes_price"),
            "price_source_tag": rec.get("price_source_tag") or "synthetic",
        })
    for series in prints.values():
        series.sort(key=lambda p: p["ts"])
    return prints


# ─────────────────────────────────── the 2x2 measurement ────────────────────────────────

def agreement_counts(universe: Sequence[str],
                     snaps: Dict[str, List[Dict[str, Any]]],
                     prints: Dict[str, List[Dict[str, Any]]],
                     *, side: str, join_rule: str, max_age_s: int) -> Tuple[int, int]:
    """(agreeing, total) admitted prints for one cell of the grid.

    A print is ADMITTED when its ticker is in `universe`, a reference quote can be
    attached under `join_rule`, the quote is at most `max_age_s` older than the print, and
    the quote carries both a `best_yes_bid` and a `best_yes_ask`. It AGREES when its
    `yes_price` sits on the side the corrected orientation predicts.
    """
    if join_rule not in JOIN_RULES:
        raise ValueError(f"unknown join_rule {join_rule!r}")
    members = set(universe)
    agreeing = total = 0
    for ticker, series in prints.items():
        if ticker not in members:
            continue
        quotes = snaps.get(ticker) or []
        if not quotes:
            continue
        stamps = [q["ts"] for q in quotes]
        for pr in series:
            if pr["taker_book_side"] != side:
                continue
            idx = bisect.bisect_right(stamps, pr["ts"]) - 1
            if idx < 0:
                continue
            # `bracketed` additionally demands a FOLLOWING snapshot, i.e. the print must
            # sit strictly inside a consecutive pair. This single condition is the whole
            # difference between the two readings of the disputed claim.
            if join_rule == "bracketed" and idx >= len(quotes) - 1:
                continue
            if pr["ts"] - stamps[idx] > max_age_s:
                continue
            bid = quotes[idx]["best_yes_bid"]
            ask = quotes[idx]["best_yes_ask"]
            if not bid or not ask:
                continue
            price = pr["yes_price"]
            if price is None:
                continue
            total += 1
            if side == TAKER_BUYS and price >= ask - _EPS:
                agreeing += 1
            elif side == TAKER_SELLS and price <= bid + _EPS:
                agreeing += 1
    return agreeing, total


def trend_direction(rates: Sequence[Optional[float]]) -> str:
    """Label a rate series ordered by WIDENING join window.

    `decaying`/`rising` are strict; anything else (including an unmeasurable cell) is
    `non_monotonic`, so a missing measurement can never be read as corroboration.
    """
    if any(r is None for r in rates) or len(rates) < 2:
        return "non_monotonic"
    vals = [float(r) for r in rates]
    if all(a > b for a, b in zip(vals[:-1], vals[1:])):
        return "decaying"
    if all(a < b for a, b in zip(vals[:-1], vals[1:])):
        return "rising"
    return "non_monotonic"


def build_report(day: str = DAY, *, depth_dir: Optional[Path] = None,
                 trades_dir: Optional[Path] = None,
                 universes: Optional[Dict[str, Sequence[str]]] = None) -> Dict[str, Any]:
    """Compute the full population x join-rule x window x side grid and attribute the flip."""
    order, snaps = load_depth(day, depth_dir)
    prints = load_prints(day, trades_dir)

    if universes is None:
        # L36: derive the probe's population by IMPORTING the probe, never by
        # re-implementing its sampling rule. The MEASUREMENT below shares no code with it.
        import scripts.q51_maker_fillsim as probe  # noqa: WPS433 (deliberate late import)
        sample = probe.reconstruct_sample(order)
        universes = {
            "probe_sports_sample": [t for t in sample if probe.is_sports_game_market(t)],
            "full_depth_day": list(order),
        }

    grid: Dict[str, Any] = {}
    for pop_name, universe in universes.items():
        grid[pop_name] = {}
        for join_rule in JOIN_RULES:
            grid[pop_name][join_rule] = {}
            for side in (TAKER_BUYS, TAKER_SELLS):
                cells = []
                for window in WINDOWS_S:
                    agreeing, total = agreement_counts(
                        universe, snaps, prints,
                        side=side, join_rule=join_rule, max_age_s=window)
                    cells.append({
                        "window_s": window,
                        "window": WINDOW_LABELS.get(window, str(window)),
                        "n_admitted_prints": total,
                        "n_agreeing": agreeing,
                        "agreement_rate": (agreeing / total) if total else None,
                    })
                grid[pop_name][join_rule][side] = {
                    "agreement_direction": AGREEMENT_DIRECTION[side],
                    "cells": cells,
                    "trend_direction": trend_direction([c["agreement_rate"] for c in cells]),
                }

    return {
        "schema_version": "l338_trend_claim_scope.v1",
        "lesson": "L338",
        "day": day,
        "price_source_tags": {"prints": "broker_truth",
                              "reference_quotes": {"ask": "real_ask", "bid": "real_bid"}},
        "n_depth_tickers": len(order),
        "n_print_tickers": len(prints),
        "universe_sizes": {k: len(v) for k, v in universes.items()},
        "grid": grid,
        "attribution": attribute_flip(grid),
        "notes": [
            "MEASUREMENT ONLY — no P&L, no bootstrap, no CI, no verdict, no registry flip.",
            "A `non_monotonic` label is also emitted for any series with an unmeasurable "
            "cell, so an absent measurement can never be read as corroboration.",
        ],
    }


def attribute_flip(grid: Dict[str, Any], side: str = TAKER_BUYS) -> Dict[str, Any]:
    """Which factor moves the trend label: POPULATION, JOIN RULE, both, or neither?

    Reads the grid as a 2x2 factorial on one `side` and reports, for each factor, whether
    holding the other factor fixed and switching this one ever changes `trend_direction`
    (and whether it changes the measured rates AT ALL).
    """
    pops = [p for p in POPULATIONS if p in grid]
    if len(pops) < 2:
        return {"insufficient_grid": True}

    def cell(pop: str, rule: str) -> Dict[str, Any]:
        return grid[pop][rule][side]

    def rates(pop: str, rule: str) -> List[Optional[float]]:
        return [c["agreement_rate"] for c in cell(pop, rule)["cells"]]

    pop_changes_trend = any(
        cell(pops[0], r)["trend_direction"] != cell(pops[1], r)["trend_direction"]
        for r in JOIN_RULES)
    pop_changes_rates = any(rates(pops[0], r) != rates(pops[1], r) for r in JOIN_RULES)
    rule_changes_trend = any(
        cell(p, JOIN_RULES[0])["trend_direction"] != cell(p, JOIN_RULES[1])["trend_direction"]
        for p in pops)
    rule_changes_rates = any(
        rates(p, JOIN_RULES[0]) != rates(p, JOIN_RULES[1]) for p in pops)

    if rule_changes_trend and not pop_changes_trend:
        driver = "join_rule"
    elif pop_changes_trend and not rule_changes_trend:
        driver = "population"
    elif pop_changes_trend and rule_changes_trend:
        driver = "both"
    else:
        driver = "neither"
    return {
        "side": side,
        "population_changes_trend": pop_changes_trend,
        "population_changes_any_rate": pop_changes_rates,
        "join_rule_changes_trend": rule_changes_trend,
        "join_rule_changes_any_rate": rule_changes_rates,
        "driver": driver,
    }


def format_report(report: Dict[str, Any]) -> str:
    out: List[str] = []
    out.append(f"L338 trend-claim scope audit — day {report['day']} "
               f"({report['n_depth_tickers']} depth tickers, "
               f"{report['n_print_tickers']} with prints)")
    for pop, by_rule in report["grid"].items():
        size = report["universe_sizes"].get(pop)
        for rule, by_side in by_rule.items():
            for side, block in by_side.items():
                cells = " ".join(
                    f"{c['window']}={'n/a' if c['agreement_rate'] is None else format(c['agreement_rate'], '.4f')}"
                    f"(n={c['n_admitted_prints']})" for c in block["cells"])
                out.append(f"  {pop}[{size}] {rule:15s} side={side:4s} "
                           f"{cells}  -> {block['trend_direction']}")
    attr = report["attribution"]
    out.append(f"  ATTRIBUTION (side={attr.get('side')}): driver={attr.get('driver')} "
               f"(population moves trend: {attr.get('population_changes_trend')}, "
               f"any rate: {attr.get('population_changes_any_rate')}; "
               f"join rule moves trend: {attr.get('join_rule_changes_trend')}, "
               f"any rate: {attr.get('join_rule_changes_any_rate')})")
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", default=DAY)
    ap.add_argument("--json", dest="json_out", default=None,
                    help="write the full report to this path (default: reports/)")
    args = ap.parse_args(argv)

    report = build_report(args.day)
    print(format_report(report))
    out = Path(args.json_out) if args.json_out else REPORT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
