#!/usr/bin/env python3
"""Q51 — is the maker-fill question MEASURABLE once a trade-print tape exists?

Read-only, offline over committed tape. This probe answers a DATA-ADEQUACY question, not a
strategy question: it produces no P&L, no CI, and flips no registry status.

Background. Every maker-side candidate this repo has tested (S6, S13, S19, S21, S23, S29,
S68, and the S73 idea-stage kill) died on one sentence — "`orderbook_depth` has no
trade-print field, so a rested maker fill is unmeasurable" (lessons L68/L131; the 2026-08-02
and 2026-08-03 Q21 rounds both concluded idea-gen stays stuck until such a surface lands).
`collection/kalshi_trades.py` now supplies that surface from Kalshi's PUBLIC
`/markets/trades`. The open question this probe answers: does the new family actually JOIN
to the book tape densely enough to make the fill question answerable, or does it land in the
same L9/L43 disjoint-window trap that reduced S52 to a single family?

Three measurements, each deliberately falsifiable:

1. **Ticker coverage** — of the book tickers queried, what share carry >=1 executed print in
   the window. A low share means the population is quoted-but-untraded (the S48 shape).
2. **Interval coverage** — the load-bearing one. For each consecutive pair of book snapshots
   of the same ticker, did >=1 print land inside the interval? This is exactly "between two
   things I can see, can I observe whether a resting order would have been hit?" A book
   snapshot with no print in its forward interval is a fill question that stays unanswerable
   even WITH this tape.
3. **Book-side split + price consistency** — the share of prints by `taker_book_side`
   (a taker crossing into the bid is what fills a resting YES bid; into the ask, a resting
   YES ask), and the share of prints whose executed `yes_price` falls inside the
   [best_yes_bid, best_yes_ask] of the immediately preceding snapshot. The latter is a
   JOIN-VALIDITY cross-check, not a strategy metric: if the two families were misaligned in
   time or instrument, prints would systematically sit outside the quoted book.

Honest-abstention discipline: a ticker present in one family and absent from the other is
counted and reported, never silently dropped; a ticker with fewer than two book snapshots
contributes zero intervals rather than a guessed one.

Run:
    python3 scripts/q51_trade_print_joinability.py --day 2026-08-03
    python3 scripts/q51_trade_print_joinability.py --day 2026-08-03 --tickers-json path.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.io import REPO_ROOT
from core.timeutil import parse_iso_utc

DEPTH_TAPE = REPO_ROOT / "tape" / "orderbook_depth"
TRADES_TAPE = REPO_ROOT / "tape" / "kalshi_trades"


def parse_ts(text: str) -> Optional[float]:
    """UNIX seconds from an RFC3339 string ('Z' or '+00:00'), or None if unparseable.

    Goes through `core.timeutil.parse_iso_utc`, never the stdlib `datetime.fromisoformat`
    directly (L136/L150): both families carry variable fractional-second precision, which
    the declared Python 3.9 floor rejects while CI on 3.11 accepts.
    """
    if not isinstance(text, str) or not text:
        return None
    try:
        return parse_iso_utc(text).astimezone(timezone.utc).timestamp()
    except (ValueError, TypeError):
        return None


def load_prints(path: Path, tickers: Optional[set] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Executed prints keyed by ticker, each sorted by event time."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    if not path.exists():
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            tk = rec.get("ticker")
            if not tk or (tickers is not None and tk not in tickers):
                continue
            ts = parse_ts(rec.get("created_time") or "")
            if ts is None:
                continue
            out.setdefault(tk, []).append({
                "ts": ts,
                "yes_price": rec.get("yes_price"),
                "count": rec.get("count"),
                "taker_book_side": rec.get("taker_book_side"),
            })
    for v in out.values():
        v.sort(key=lambda r: r["ts"])
    return out


def load_snapshots(path: Path, tickers: Optional[set] = None
                   ) -> Dict[str, List[Dict[str, Any]]]:
    """Book snapshots keyed by ticker, each sorted by capture time."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    if not path.exists():
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            tk = rec.get("ticker")
            if not tk or (tickers is not None and tk not in tickers):
                continue
            ts = parse_ts(rec.get("captured_at") or "")
            if ts is None:
                continue
            out.setdefault(tk, []).append({
                "ts": ts,
                "best_yes_bid": rec.get("best_yes_bid"),
                "best_yes_ask": rec.get("best_yes_ask"),
            })
    for v in out.values():
        v.sort(key=lambda r: r["ts"])
    return out


def joinability(snapshots: Dict[str, List[Dict[str, Any]]],
                prints: Dict[str, List[Dict[str, Any]]],
                tickers: Sequence[str]) -> Dict[str, Any]:
    """The three measurements. Pure — no I/O, so the numbers are unit-testable."""
    n_tickers = len(tickers)
    n_with_prints = 0
    n_with_book = 0
    n_intervals = 0
    n_intervals_with_print = 0
    n_prints = 0
    side_counts: Dict[str, int] = {}
    n_price_checked = 0
    n_price_inside = 0

    for tk in tickers:
        snaps = snapshots.get(tk, [])
        pr = prints.get(tk, [])
        if snaps:
            n_with_book += 1
        if pr:
            n_with_prints += 1
        n_prints += len(pr)
        for p in pr:
            side_counts[p.get("taker_book_side") or "__missing__"] = \
                side_counts.get(p.get("taker_book_side") or "__missing__", 0) + 1
        for i in range(len(snaps) - 1):
            lo, hi = snaps[i]["ts"], snaps[i + 1]["ts"]
            n_intervals += 1
            hits = [p for p in pr if lo < p["ts"] <= hi]
            if hits:
                n_intervals_with_print += 1
            bid, ask = snaps[i]["best_yes_bid"], snaps[i]["best_yes_ask"]
            if bid is None or ask is None:
                continue
            for p in hits:
                px = p.get("yes_price")
                if px is None:
                    continue
                n_price_checked += 1
                if bid <= px <= ask:
                    n_price_inside += 1

    def frac(a: int, b: int) -> Optional[float]:
        return round(a / b, 6) if b else None

    return {
        "n_tickers": n_tickers,
        "n_tickers_with_book": n_with_book,
        "n_tickers_with_prints": n_with_prints,
        "ticker_coverage": frac(n_with_prints, n_tickers),
        "n_prints": n_prints,
        "n_intervals": n_intervals,
        "n_intervals_with_print": n_intervals_with_print,
        "interval_coverage": frac(n_intervals_with_print, n_intervals),
        "taker_book_side_counts": dict(sorted(side_counts.items())),
        "n_price_checked": n_price_checked,
        "n_price_inside_prior_quote": n_price_inside,
        "price_consistency": frac(n_price_inside, n_price_checked),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", required=True, help="UTC day YYYY-MM-DD present in both families")
    ap.add_argument("--tickers-json", default=None,
                    help="JSON list of tickers to score (default: every ticker with prints "
                         "on that day)")
    ap.add_argument("--depth-tape", default=str(DEPTH_TAPE))
    ap.add_argument("--trades-tape", default=str(TRADES_TAPE))
    args = ap.parse_args(argv)

    trades_path = Path(args.trades_tape) / f"dt={args.day}.jsonl"
    depth_path = Path(args.depth_tape) / f"dt={args.day}.jsonl"
    if args.tickers_json:
        tickers = json.loads(Path(args.tickers_json).read_text())
    else:
        tickers = sorted(load_prints(trades_path).keys())
    tset = set(tickers)
    prints = load_prints(trades_path, tset)
    snapshots = load_snapshots(depth_path, tset)
    report = joinability(snapshots, prints, tickers)
    report["day"] = args.day
    report["trades_path"] = str(trades_path)
    report["depth_path"] = str(depth_path)
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
