#!/usr/bin/env python3
"""s17_leadlag_probe.py — S17 Kalshi<->Polymarket recurring-macro lead-lag first cut (Q12).

Direct S17 analog of `scripts/s9_leadlag_probe.py`. Q12 built the Fed-decision leg of
`collection/polymarket_pairs.py` (`run_fed_decision()`, 2026-07-06) and wired it into the
hourly pass, pairing Kalshi's `KXFEDDECISION` 5-bucket ladder against Polymarket's "Fed
Decision in <Month>?" events on the SAME real-ask basis (both `real_ask`, a genuine CLOB
book on the Polymarket side, a fillable Yes ask on the Kalshi side). This script is the
"once enough history exists" half of Q12's own remaining-work note: a read-only lead-lag
cross-correlation over whatever `tape/polymarket_macro_pairs/*.jsonl` has accumulated.

S17's thesis (registry): Kalshi and Polymarket price the SAME recurring-macro question
(here, "will the Fed hike/cut/hold N bps at meeting M") but sit on different rails
(USD/KYC vs USDC/Polygon) that keep arbitrage from instantly enforcing parity — so when
new information hits (an FOMC decision, a fresh dot-plot, a CPI surprise repricing the
odds), one venue should reprice first and the other should visibly lag it for at least one
capture interval. That is the decision-relevant test.

WHY THIS LEG AND NOT THE CPI LEG. This probe pools ONLY the Fed-decision family
(`polymarket_macro_pairs.v1`), whose Kalshi side is `kalshi.yes_ask` tagged `real_ask` and
Polymarket side is `polymarket.best_ask` tagged `real_ask` — apples-to-apples, exactly like
S9's WC-round comparison. The CPI leg (`tape/polymarket_cpi_pairs/`, schema
`polymarket_cpi_pairs.v1`) is DELIBERATELY OUT OF SCOPE here: its Kalshi side is
`kalshi.derived_prob`, a `synthetic` cumulative-ladder-difference, NOT a fillable price
(see `collection/polymarket_pairs.py::run_cpi` and CLAUDE.md Hard Rule #3 / prime directive
#1). Pooling a synthetic derived value into the same real-ask-vs-real-ask correlation would
silently mix a non-fillable number with a genuine fill price — the exact class of mistake
the prime directive forbids. So it is not pooled, not correlated, and not reported as a
lead-lag figure here. (The `--cpi-note` flag prints a one-line count of the CPI tape for
provenance only, clearly `synthetic`-tagged, and nothing more.)

Two things this first cut can and cannot do, stated plainly:
  - IT CAN pool every consecutive-capture price change across every stable (meeting, bucket)
    pair into a lag-0/lag+1/lag-1 cross-correlation (classic price-discovery lead-lag panel
    test) and report it honestly, whatever it shows.
  - IT CANNOT yet test the actual thesis. Kalshi's listed Fed meetings are Jul/Sep/Oct 2026;
    NONE has occurred inside the 2026-07-06 -> 2026-07-12 collection window, so no FOMC
    decision has resolved a market or rolled one off the board while continuous collection was
    running. `market_membership_changes()` — the honest proxy for "did a meeting resolve/roll
    off" — is the check for whether any such shock landed. If it is empty (the expected case),
    then every observed price tick so far is book noise (bid/ask wobble on markets whose
    underlying meeting hasn't happened yet), NOT an information shock. The pooled correlation
    below is reported for completeness but must NOT be read as a lead-lag verdict — it is a
    noise-floor characterization until a real FOMC decision lands inside the window.

No block-bootstrap, no CI, no verdict here — this is a data-adequacy first cut in the same
spirit as `s9_leadlag_probe.py`'s and `s8_basis_probe.py`'s first passes. Read-only over
`tape/polymarket_macro_pairs/*.jsonl`, no network calls.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.io import REPO_ROOT

TAPE_DIR = REPO_ROOT / "tape" / "polymarket_macro_pairs"
CPI_TAPE_DIR = REPO_ROOT / "tape" / "polymarket_cpi_pairs"

# Pairs with fewer captures than this haven't been tracked long enough to contribute a
# meaningful delta series (also drops any stray single-capture records from a smoke test).
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


def pair_key(record: Dict[str, Any]) -> Optional[str]:
    """Stable identity of one Kalshi/Polymarket pair over time. The Kalshi ticker uniquely
    identifies a (meeting, bucket) pair (e.g. KXFEDDECISION-26OCT-H26), so it is the natural
    series key — analogous to S9's per-ticker keying. Falls back to meeting+bucket if a
    record somehow lacks the ticker (never expected for this schema)."""
    kalshi = record.get("kalshi") or {}
    ticker = kalshi.get("ticker")
    if ticker is not None:
        return str(ticker)
    meeting = record.get("meeting")
    bucket = record.get("bucket")
    if meeting is not None and bucket is not None:
        return f"{meeting}|{bucket}"
    return None


def build_series(records: Sequence[Dict[str, Any]]) -> Dict[str, List[Row]]:
    """One sorted-by-capture time series per (meeting, bucket) pair (keyed by Kalshi ticker).
    De-dupes same-capture_id duplicates (VPS + cloud collectors can both fire the same hour)
    by last-write-wins — tape is append-only so a later line for the same capture_id is a
    rewrite-safe re-read, never a second real observation. Rows whose Polymarket book fetch
    failed (`book_fetch_ok` false) are dropped: no real ask was observed there."""
    by_pair: Dict[str, Dict[str, Tuple[float, float]]] = defaultdict(dict)
    for r in records:
        kalshi = r.get("kalshi") or {}
        poly = r.get("polymarket") or {}
        if not poly.get("book_fetch_ok", True):
            continue
        key = pair_key(r)
        capture_id = r.get("capture_id")
        kalshi_ask = kalshi.get("yes_ask")
        poly_ask = poly.get("best_ask")
        if key is None or capture_id is None or kalshi_ask is None or poly_ask is None:
            continue
        by_pair[key][capture_id] = (float(kalshi_ask), float(poly_ask))

    series: Dict[str, List[Row]] = {}
    for key, by_capture in by_pair.items():
        rows = sorted(by_capture.items(), key=lambda kv: kv[0])
        series[key] = [(cap, ka, pa) for cap, (ka, pa) in rows]
    return series


def deltas(rows: Sequence[Row]) -> List[Tuple[float, float]]:
    """Consecutive-step (delta_kalshi, delta_polymarket) pairs for one pair's series."""
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
    — NOT the same thing as an FOMC-decision information shock (see module docstring); with
    no meeting resolved inside the window, Kalshi's own 1c tick means these are still book
    noise, not information events."""
    events: List[Dict[str, Any]] = []
    for key, rows in series.items():
        if len(rows) < min_captures:
            continue
        for i, (dk, dp) in enumerate(deltas(rows)):
            if abs(dk) >= threshold or abs(dp) >= threshold:
                events.append({
                    "pair": key,
                    "capture_id": rows[i + 1][0],
                    "delta_kalshi": dk,
                    "delta_polymarket": dp,
                })
    return events


def market_membership_changes(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-capture added/removed pair-key sets — the actual proxy for an FOMC meeting
    resolving or rolling off the board (a real information shock). Zero changes across the
    continuously-collected window means the lead-lag thesis hasn't had a real shock to test
    yet, only book noise."""
    by_capture: Dict[str, set] = defaultdict(set)
    for r in records:
        key = pair_key(r)
        capture_id = r.get("capture_id")
        if key is not None and capture_id is not None:
            by_capture[capture_id].add(key)

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


def count_cpi_tape(cpi_tape_dir: Path = CPI_TAPE_DIR) -> Dict[str, Any]:
    """Provenance-only tally of the OUT-OF-SCOPE CPI leg (synthetic Kalshi side). Deliberately
    NOT correlated or pooled — see module docstring. Reported only so the writeup can state
    exactly how much synthetic-tagged tape exists that this probe chose not to touch."""
    n_records = 0
    for path in sorted(cpi_tape_dir.glob("*.jsonl")):
        with path.open() as fh:
            for line in fh:
                if line.strip():
                    n_records += 1
    return {"n_records": n_records, "kalshi_price_source_tag": "synthetic", "pooled": False}


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
    ap = argparse.ArgumentParser(description="S17 recurring-macro lead-lag first cut (read-only, descriptive)")
    ap.add_argument("--tape-dir", default=str(TAPE_DIR))
    ap.add_argument("--min-captures", type=int, default=MIN_CAPTURES)
    ap.add_argument("--cpi-note", action="store_true",
                    help="print a provenance-only count of the out-of-scope synthetic CPI tape")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    report = build_report(Path(args.tape_dir), min_captures=args.min_captures)

    print("=" * 78)
    print("S17 RECURRING-MACRO LEAD-LAG FIRST CUT (read-only, descriptive — NOT a verdict)")
    print("Fed-decision leg only; both sides real_ask. CPI leg (synthetic) excluded by design.")
    print("=" * 78)
    print(f"records={report['n_records']} captures={report['n_distinct_captures']} "
          f"pairs={report['n_distinct_markets']} "
          f"pairs_used(>={args.min_captures} captures)={report['n_markets_min_captures']}")
    ll = report["leadlag"]
    print(f"pooled contemporaneous rho={ll['rho_contemporaneous']} (n={ll['n_steps_contemporaneous']})")
    print(f"kalshi-leads-polymarket rho={ll['rho_kalshi_leads_polymarket']} (n={ll['n_steps_lag1']})")
    print(f"polymarket-leads-kalshi rho={ll['rho_polymarket_leads_kalshi']} (n={ll['n_steps_lag1']})")
    print(f"tick-size-or-larger moves observed: {len(report['shock_events'])}")
    print(f"FOMC meeting resolve/roll-off (shock proxy) events in window: {len(report['membership_changes'])}")
    if not report["membership_changes"]:
        print("  -> zero FOMC resolve/roll-off events inside the continuously-collected window; "
              "the actual lead-lag-around-a-shock thesis is still untested, only book noise "
              "has been observed so far. This is a noise-floor characterization, NOT a verdict.")

    if args.cpi_note:
        cpi = count_cpi_tape()
        print(f"[out-of-scope] CPI leg records={cpi['n_records']} "
              f"(kalshi side tag={cpi['kalshi_price_source_tag']}, pooled={cpi['pooled']}) "
              "— excluded from the real-ask correlation by design (Hard Rule #3).")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2))
        print(f"wrote {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
