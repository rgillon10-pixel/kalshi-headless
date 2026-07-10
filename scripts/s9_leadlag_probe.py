#!/usr/bin/env python3
"""s9_leadlag_probe.py — S9 Kalshi<->Polymarket lead-lag first cut (LOOP-QUEUE.md Q8).

Q8 built `collection/polymarket_pairs.py` (2026-07-04) and wired it into the hourly pass
(2026-07-05), pairing Kalshi's `KXWCROUND` "team to reach round" markets with Polymarket's
structurally identical events on the same real-ask basis. This script is the "once enough
history exists" half of Q8's own remaining-work note: a read-only lead-lag cross-correlation
over whatever `tape/polymarket_pairs/` has accumulated so far.

S9's thesis (registry): the two venues price the SAME question, but sit on different rails
(USDC/Polygon vs USD/Kalshi, different KYC funnels) that keep arbitrage from instantly
enforcing parity — so when new information hits, one venue should reprice first and the
other should visibly lag it for at least one capture interval. That is the decision-relevant
test: does a real information SHOCK (a team advancing or being eliminated) show up on one
venue's book before the other's?

Two things this first cut can and cannot do, stated plainly:
  - IT CAN pool every consecutive-capture price change across every stable market into a
    lag-0/lag+1/lag-1 cross-correlation (classic price-discovery lead-lag panel test) and
    report it honestly, whatever it shows.
  - IT CANNOT yet test the actual thesis: as of this run's accumulation window (2026-07-05
    00:11Z to the run time), zero KXWCROUND markets have opened or closed — no team has
    advanced or been eliminated inside the window the hourly collector has continuously
    covered (the one membership change on record, at the very first capture, predates
    continuous hourly collection and is a startup artifact, not an in-window event — see
    `market_membership_changes`). Every observed price tick so far is book-noise (bid/ask
    wobble), not an information shock. The pooled correlation below is reported for
    completeness but should NOT be read as a lead-lag verdict — it is a noise-floor
    characterization until a real round-transition lands inside the window.

No block-bootstrap, no CI, no verdict here — this is a data-adequacy first cut in the same
spirit as `s8_basis_probe.py`'s first pass. Read-only over `tape/polymarket_pairs/*.jsonl`,
no network calls.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.io import REPO_ROOT

TAPE_DIR = REPO_ROOT / "tape" / "polymarket_pairs"

# Markets with fewer captures than this haven't been tracked long enough to contribute a
# meaningful delta series (also drops the handful of stray single-capture records left over
# from the pre-hourly-wiring smoke test).
MIN_CAPTURES = 10

# Kalshi's own tick size — the smallest move that isn't sub-tick book noise.
SHOCK_THRESHOLD_DOLLARS = 0.01

Row = Tuple[str, float, float]  # (capture_id, kalshi_yes_ask, polymarket_best_ask)


def load_records(tape_dir: Path = TAPE_DIR) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for path in sorted(tape_dir.glob("*.jsonl")):
        with path.open() as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def build_series(records: Sequence[Dict[str, Any]]) -> Dict[str, List[Row]]:
    """One sorted-by-capture time series per Kalshi ticker. De-dupes same-capture_id
    duplicates (VPS + cloud collectors can both fire the same hour) by last-write-wins —
    tape is append-only so a later line for the same capture_id is a rewrite-safe re-read,
    never a second real observation."""
    by_ticker: Dict[str, Dict[str, Tuple[float, float]]] = defaultdict(dict)
    for r in records:
        kalshi = r.get("kalshi") or {}
        poly = r.get("polymarket") or {}
        if not poly.get("book_fetch_ok", True):
            continue
        ticker = kalshi.get("ticker")
        capture_id = r.get("capture_id")
        kalshi_ask = kalshi.get("yes_ask")
        poly_ask = poly.get("best_ask")
        if ticker is None or capture_id is None or kalshi_ask is None or poly_ask is None:
            continue
        by_ticker[ticker][capture_id] = (float(kalshi_ask), float(poly_ask))

    series: Dict[str, List[Row]] = {}
    for ticker, by_capture in by_ticker.items():
        rows = sorted(by_capture.items(), key=lambda kv: kv[0])
        series[ticker] = [(cap, ka, pa) for cap, (ka, pa) in rows]
    return series


def deltas(rows: Sequence[Row]) -> List[Tuple[float, float]]:
    """Consecutive-step (delta_kalshi, delta_polymarket) pairs for one market's series."""
    return [(ka1 - ka0, pa1 - pa0) for (_, ka0, pa0), (_, ka1, pa1) in zip(rows, rows[1:])]


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / (vx * vy) ** 0.5


def pooled_leadlag(series: Dict[str, List[Row]], *, min_captures: int = MIN_CAPTURES) -> Dict[str, Any]:
    contemp_k: List[float] = []
    contemp_p: List[float] = []
    k_now_for_p_next: List[float] = []
    p_next: List[float] = []
    p_now_for_k_next: List[float] = []
    k_next: List[float] = []
    n_markets_used = 0

    for rows in series.values():
        if len(rows) < min_captures:
            continue
        d = deltas(rows)
        if len(d) < 2:
            continue
        n_markets_used += 1
        dk = [x[0] for x in d]
        dp = [x[1] for x in d]
        contemp_k.extend(dk)
        contemp_p.extend(dp)
        k_now_for_p_next.extend(dk[:-1])
        p_next.extend(dp[1:])
        p_now_for_k_next.extend(dp[:-1])
        k_next.extend(dk[1:])

    return {
        "n_markets_used": n_markets_used,
        "n_steps_contemporaneous": len(contemp_k),
        "rho_contemporaneous": pearson(contemp_k, contemp_p),
        "n_steps_lag1": len(k_now_for_p_next),
        "rho_kalshi_leads_polymarket": pearson(k_now_for_p_next, p_next),
        "rho_polymarket_leads_kalshi": pearson(p_now_for_k_next, k_next),
    }


def shock_events(series: Dict[str, List[Row]], *, threshold: float = SHOCK_THRESHOLD_DOLLARS,
                  min_captures: int = MIN_CAPTURES) -> List[Dict[str, Any]]:
    """Every step-to-step move at or past `threshold` on either venue, for manual eyeballing
    — NOT the same thing as a round-transition information shock (see module docstring);
    Kalshi's own 1c tick means most of these are still just book noise at this price range."""
    events: List[Dict[str, Any]] = []
    for ticker, rows in series.items():
        if len(rows) < min_captures:
            continue
        for i, (dk, dp) in enumerate(deltas(rows)):
            if abs(dk) >= threshold or abs(dp) >= threshold:
                events.append({
                    "ticker": ticker,
                    "capture_id": rows[i + 1][0],
                    "delta_kalshi": dk,
                    "delta_polymarket": dp,
                })
    return events


def market_membership_changes(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-capture added/removed ticker sets — the actual proxy for a round-transition
    (team advanced or eliminated) event. Zero changes across the continuously-collected
    window means the lead-lag thesis hasn't had a real shock to test yet."""
    by_capture: Dict[str, set] = defaultdict(set)
    for r in records:
        kalshi = r.get("kalshi") or {}
        ticker = kalshi.get("ticker")
        capture_id = r.get("capture_id")
        if ticker is not None and capture_id is not None:
            by_capture[capture_id].add(ticker)

    changes: List[Dict[str, Any]] = []
    prev: Optional[set] = None
    for capture_id in sorted(by_capture):
        cur = by_capture[capture_id]
        if prev is not None:
            added = sorted(cur - prev)
            removed = sorted(prev - cur)
            if added or removed:
                changes.append({"capture_id": capture_id, "added": added, "removed": removed})
        prev = cur
    return changes


def build_report(tape_dir: Path = TAPE_DIR, *, min_captures: int = MIN_CAPTURES) -> Dict[str, Any]:
    records = load_records(tape_dir)
    series = build_series(records)
    return {
        "n_records": len(records),
        "n_distinct_captures": len({r.get("capture_id") for r in records}),
        "n_distinct_markets": len(series),
        "n_markets_min_captures": sum(1 for rows in series.values() if len(rows) >= min_captures),
        "leadlag": pooled_leadlag(series, min_captures=min_captures),
        "shock_events": shock_events(series, min_captures=min_captures),
        "membership_changes": market_membership_changes(records),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S9 lead-lag first cut (read-only, descriptive)")
    ap.add_argument("--tape-dir", default=str(TAPE_DIR))
    ap.add_argument("--min-captures", type=int, default=MIN_CAPTURES)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    report = build_report(Path(args.tape_dir), min_captures=args.min_captures)

    print("=" * 78)
    print("S9 LEAD-LAG FIRST CUT (read-only, descriptive — NOT a verdict)")
    print("=" * 78)
    print(f"records={report['n_records']} captures={report['n_distinct_captures']} "
          f"markets={report['n_distinct_markets']} "
          f"markets_used(>={args.min_captures} captures)={report['n_markets_min_captures']}")
    ll = report["leadlag"]
    print(f"pooled contemporaneous rho={ll['rho_contemporaneous']} (n={ll['n_steps_contemporaneous']})")
    print(f"kalshi-leads-polymarket rho={ll['rho_kalshi_leads_polymarket']} (n={ll['n_steps_lag1']})")
    print(f"polymarket-leads-kalshi rho={ll['rho_polymarket_leads_kalshi']} (n={ll['n_steps_lag1']})")
    print(f"tick-size-or-larger moves observed: {len(report['shock_events'])}")
    print(f"market open/close (round-transition proxy) events in window: {len(report['membership_changes'])}")
    if not report["membership_changes"]:
        print("  -> zero round-transition events inside the continuously-collected window; "
              "the actual lead-lag-around-a-shock thesis is still untested, only book noise "
              "has been observed so far.")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2))
        print(f"wrote {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
