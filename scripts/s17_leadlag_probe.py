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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.io import REPO_ROOT
from core.pricing import TAKER_FEE_RATE, fee_per_contract

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


# --------------------------------------------------------------------------- #
# Burst-mode (Q19) — sub-hourly event-window lead-lag + fillable dislocation scan.
#
# The first-cut above pools HOURLY captures, whose cadence is coarser than an FOMC/CPI
# repricing (S9/S17's own data-adequacy finding). The five one-shot burst triggers
# (LOOP-QUEUE.md "Burst-capture legs") deliver 60-120s-cadence tape bracketing a real
# macro shock — exactly the data class this mode is built to read. It does three things the
# hourly cut cannot: (a) per-ticker SIGNED lead-lag (which venue reprices first) at burst
# resolution, (b) a fillable cross-venue DISLOCATION scan — moments where buying the cheap
# venue's real ask and selling the rich venue's real bid clears BOTH venues' fees, and
# (c) the width x duration distribution of those dislocations.
#
# HONESTY BOUNDARIES (do not oversell):
#   - Both legs on the Kalshi side are charged the TAKER fee (`core.pricing.fee_per_contract`,
#     never a hand-rolled literal): crossing to buy at the ask OR to sell at the bid both lift
#     resting size, so neither is a free maker fill (the S13 lesson — an assumed maker fill
#     must cite a fill model). This is the conservative fee; a real resting maker fill would be
#     cheaper but cannot be assumed here.
#   - Polymarket's CLOB taker fee is ~0 today; it is a MODEL ASSUMPTION, not a fill, so it is a
#     parameter (`--poly-fee`, default 0.0) tagged in the report's `fee_model` block. Set it to
#     the real number the day Polymarket charges one.
#   - A positive net_edge is a fillable-at-observed-quotes locked pair (long Yes one venue +
#     short Yes the other = outcome-neutral), NOT a realised P&L: it ignores size/depth at the
#     quote, the cross-venue settlement + capital-rail risk that is the very segmentation S17
#     rests on, and any queue position. This mode SCANS for dislocations; it does not book them
#     and makes no CI/verdict claim. That is the per-event run's job, under the two-agent rule.
# --------------------------------------------------------------------------- #

# (capture_dt, kalshi_yes_ask, kalshi_yes_bid, poly_best_ask, poly_best_bid)
BurstQuote = Dict[str, Optional[float]]


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_capture_time(record: Dict[str, Any]) -> Optional[datetime]:
    """Aware-UTC datetime of one record's capture instant. Prefers the full-ISO
    `captured_at`; falls back to parsing the compact `capture_id` (YYYYMMDDThhmmss[Z] or
    YYYYMMDDThhmm[Z]). Returns None if neither parses — the caller drops such a record."""
    captured_at = record.get("captured_at")
    if isinstance(captured_at, str):
        try:
            dt = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    cid = record.get("capture_id")
    if isinstance(cid, str):
        s = cid.strip().rstrip("Zz")
        for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%dT%H%M%S%f"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def parse_window_bound(text: str) -> datetime:
    """Parse a CLI window bound (ISO 8601, e.g. 2026-07-14T12:05:00Z) to aware UTC."""
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def filter_burst_window(records: Sequence[Dict[str, Any]], start: datetime,
                        end: datetime) -> List[Dict[str, Any]]:
    """Records whose capture instant falls in [start, end] (inclusive)."""
    out: List[Dict[str, Any]] = []
    for r in records:
        t = parse_capture_time(r)
        if t is not None and start <= t <= end:
            out.append(r)
    return out


def cadence_stats(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """min/median/max inter-capture gap in seconds across DISTINCT capture instants — the
    honesty check that a window is genuinely burst-cadence (60-120s) and not sparse hourly
    tape masquerading as one. A median gap near 3600s means this is NOT burst tape."""
    times = sorted({t for t in (parse_capture_time(r) for r in records) if t is not None})
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
    if not gaps:
        return {"n_distinct_captures": len(times), "min_gap_s": None,
                "median_gap_s": None, "max_gap_s": None}
    gaps_sorted = sorted(gaps)
    median = gaps_sorted[len(gaps_sorted) // 2]
    return {"n_distinct_captures": len(times), "min_gap_s": min(gaps),
            "median_gap_s": median, "max_gap_s": max(gaps)}


def build_burst_series(records: Sequence[Dict[str, Any]]) -> Dict[str, List[Tuple[datetime, BurstQuote]]]:
    """Per-pair series carrying BOTH sides of BOTH venues' books (Kalshi yes-ask & yes-bid,
    Polymarket best-ask & best-bid) sorted by capture time — the dislocation scan needs all
    four quotes. De-dupes by capture instant (last-write-wins, tape-append-safe). Drops
    Polymarket book-fetch failures (no real ask/bid observed there). A row keeps whichever
    of the four quotes were present; a dislocation is only scored when the two legs it needs
    are both present."""
    by_pair: Dict[str, Dict[datetime, BurstQuote]] = defaultdict(dict)
    for r in records:
        poly = r.get("polymarket") or {}
        if not poly.get("book_fetch_ok", True):
            continue
        key = pair_key(r)
        t = parse_capture_time(r)
        if key is None or t is None:
            continue
        kalshi = r.get("kalshi") or {}
        by_pair[key][t] = {
            "kalshi_yes_ask": _as_float(kalshi.get("yes_ask")),
            "kalshi_yes_bid": _as_float(kalshi.get("yes_bid")),
            "poly_best_ask": _as_float(poly.get("best_ask")),
            "poly_best_bid": _as_float(poly.get("best_bid")),
        }
    series: Dict[str, List[Tuple[datetime, BurstQuote]]] = {}
    for key, by_t in by_pair.items():
        series[key] = [(t, by_t[t]) for t in sorted(by_t)]
    return series


def per_ticker_leadlag(burst_series: Dict[str, List[Tuple[datetime, BurstQuote]]],
                       *, min_steps: int = 3, margin: float = 0.05) -> List[Dict[str, Any]]:
    """SIGNED lead-lag per pair at burst resolution: does Kalshi's move predict Polymarket's
    NEXT move (kalshi leads) more than the reverse? `signed_leader` is 'kalshi'/'polymarket'
    when one lag's correlation beats the other by `margin`, else 'none'. Uses the Kalshi
    yes-ask and Polymarket best-ask series (both real_ask), same basis as the pooled cut."""
    out: List[Dict[str, Any]] = []
    for key, rows in burst_series.items():
        seq = [(q["kalshi_yes_ask"], q["poly_best_ask"]) for _, q in rows
               if q["kalshi_yes_ask"] is not None and q["poly_best_ask"] is not None]
        dk = [b[0] - a[0] for a, b in zip(seq, seq[1:])]
        dp = [b[1] - a[1] for a, b in zip(seq, seq[1:])]
        if len(dk) < min_steps:
            continue
        rho_k_leads = pearson(dk[:-1], dp[1:])
        rho_p_leads = pearson(dp[:-1], dk[1:])
        leader = None
        if rho_k_leads is not None and rho_p_leads is not None:
            if rho_k_leads > rho_p_leads + margin:
                leader = "kalshi"
            elif rho_p_leads > rho_k_leads + margin:
                leader = "polymarket"
            else:
                leader = "none"
        out.append({
            "pair": key,
            "n_steps": len(dk),
            "rho_contemporaneous": pearson(dk, dp),
            "rho_kalshi_leads": rho_k_leads,
            "rho_polymarket_leads": rho_p_leads,
            "signed_leader": leader,
        })
    return out


def _best_dislocation(quote: BurstQuote, *, kalshi_fee_rate: float,
                      poly_fee: float) -> Optional[Dict[str, Any]]:
    """Best (max net-edge) fillable cross-venue Yes/Yes pair at one capture, or None if
    neither direction's two legs are both present. net_edge > 0 is a locked, outcome-neutral
    dislocation net of both venues' fees (Kalshi taker on the crossing leg; Polymarket per
    `poly_fee`). Directions:
      A buy_kalshi_sell_poly:  proceeds poly_best_bid  - cost kalshi_yes_ask - fees
      B buy_poly_sell_kalshi:  proceeds kalshi_yes_bid - cost poly_best_ask  - fees"""
    ka, kb = quote["kalshi_yes_ask"], quote["kalshi_yes_bid"]
    pa, pb = quote["poly_best_ask"], quote["poly_best_bid"]
    cands: List[Tuple[float, str]] = []
    if ka is not None and pb is not None:
        edge_a = pb - ka - fee_per_contract(ka, kalshi_fee_rate) - poly_fee
        cands.append((edge_a, "buy_kalshi_sell_poly"))
    if pa is not None and kb is not None:
        edge_b = kb - pa - fee_per_contract(kb, kalshi_fee_rate) - poly_fee
        cands.append((edge_b, "buy_poly_sell_kalshi"))
    if not cands:
        return None
    edge, direction = max(cands, key=lambda x: x[0])
    return {"net_edge": edge, "direction": direction}


def dislocation_scan(burst_series: Dict[str, List[Tuple[datetime, BurstQuote]]],
                     *, kalshi_fee_rate: float = TAKER_FEE_RATE,
                     poly_fee: float = 0.0) -> List[Dict[str, Any]]:
    """Every capture whose best cross-venue pair clears both fees (net_edge > 0)."""
    hits: List[Dict[str, Any]] = []
    for key, rows in burst_series.items():
        for t, quote in rows:
            best = _best_dislocation(quote, kalshi_fee_rate=kalshi_fee_rate, poly_fee=poly_fee)
            if best is not None and best["net_edge"] > 0.0:
                hits.append({
                    "pair": key,
                    "capture_time": t.isoformat(),
                    "direction": best["direction"],
                    "net_edge": best["net_edge"],
                    "quote": quote,
                })
    return hits


def dislocation_episodes(burst_series: Dict[str, List[Tuple[datetime, BurstQuote]]],
                         *, kalshi_fee_rate: float = TAKER_FEE_RATE,
                         poly_fee: float = 0.0) -> List[Dict[str, Any]]:
    """Contiguous runs of positive-edge captures on the SAME pair+direction → one episode
    each, with width (max net_edge over the run) and duration (wall-clock seconds first→last
    capture, plus capture count). A dislocation that survives many captures is a very
    different animal from a single-tick blip — the width x duration distribution is what the
    per-event finding will report."""
    episodes: List[Dict[str, Any]] = []
    for key, rows in burst_series.items():
        run: List[Tuple[datetime, float]] = []
        run_dir: Optional[str] = None
        for t, quote in rows:
            best = _best_dislocation(quote, kalshi_fee_rate=kalshi_fee_rate, poly_fee=poly_fee)
            live = best is not None and best["net_edge"] > 0.0
            direction = best["direction"] if best is not None else None
            if live and (run_dir is None or run_dir == direction):
                run.append((t, best["net_edge"]))
                run_dir = direction
            else:
                if run:
                    episodes.append(_episode(key, run_dir, run))
                run = [(t, best["net_edge"])] if live else []
                run_dir = direction if live else None
        if run:
            episodes.append(_episode(key, run_dir, run))
    return episodes


def _episode(pair: str, direction: Optional[str],
             run: Sequence[Tuple[datetime, float]]) -> Dict[str, Any]:
    times = [t for t, _ in run]
    edges = [e for _, e in run]
    duration_s = (max(times) - min(times)).total_seconds()
    return {
        "pair": pair,
        "direction": direction,
        "n_captures": len(run),
        "start": min(times).isoformat(),
        "end": max(times).isoformat(),
        "duration_s": duration_s,
        "max_net_edge": max(edges),
        "mean_net_edge": sum(edges) / len(edges),
    }


def build_burst_report(records: Sequence[Dict[str, Any]], *,
                       start: Optional[datetime] = None, end: Optional[datetime] = None,
                       kalshi_fee_rate: float = TAKER_FEE_RATE,
                       poly_fee: float = 0.0) -> Dict[str, Any]:
    window = filter_burst_window(records, start, end) if (start and end) else list(records)
    bseries = build_burst_series(window)
    disl = dislocation_scan(bseries, kalshi_fee_rate=kalshi_fee_rate, poly_fee=poly_fee)
    episodes = dislocation_episodes(bseries, kalshi_fee_rate=kalshi_fee_rate, poly_fee=poly_fee)
    return {
        "mode": "burst",
        "window_start": start.isoformat() if start else None,
        "window_end": end.isoformat() if end else None,
        "n_records_in_window": len(window),
        "cadence": cadence_stats(window),
        "n_pairs": len(bseries),
        "per_ticker_leadlag": per_ticker_leadlag(bseries),
        "n_dislocations": len(disl),
        "dislocations": disl,
        "dislocation_episodes": episodes,
        "fee_model": {
            "kalshi_rate": kalshi_fee_rate,
            "kalshi_fee_fn": "core.pricing.fee_per_contract (taker; both crossing legs)",
            "poly_fee_per_contract": poly_fee,
            "poly_fee_source": "assumed_zero_polymarket_clob" if poly_fee == 0.0 else "explicit_cli",
        },
    }


def _print_burst_report(report: Dict[str, Any]) -> None:
    print("=" * 78)
    print("S17 BURST-MODE lead-lag + fillable dislocation scan (read-only — NOT a verdict)")
    print("Fed-decision leg, both sides real_ask. Kalshi taker fee both legs; Polymarket fee")
    print(f"per model ({report['fee_model']['poly_fee_source']}). Scans dislocations, books none.")
    print("=" * 78)
    cad = report["cadence"]
    print(f"window {report['window_start']} -> {report['window_end']}  "
          f"records={report['n_records_in_window']} pairs={report['n_pairs']}")
    print(f"cadence: distinct_captures={cad['n_distinct_captures']} "
          f"min_gap_s={cad['min_gap_s']} median_gap_s={cad['median_gap_s']} "
          f"max_gap_s={cad['max_gap_s']}")
    if cad["median_gap_s"] is not None and cad["median_gap_s"] > 300:
        print("  -> WARNING median gap > 5min: this is NOT burst-cadence tape; lead-lag at this "
              "resolution is the same noise-floor characterization the hourly first cut already "
              "gave, not a shock-window result.")
    leaders = [t for t in report["per_ticker_leadlag"] if t["signed_leader"] not in (None, "none")]
    print(f"per-ticker signed lead-lag computed for {len(report['per_ticker_leadlag'])} pairs; "
          f"{len(leaders)} show a directional leader")
    for t in leaders[:10]:
        print(f"  {t['pair']}: leader={t['signed_leader']} "
              f"rho_k_leads={t['rho_kalshi_leads']} rho_p_leads={t['rho_polymarket_leads']} "
              f"(n={t['n_steps']})")
    print(f"fillable dislocations (net_edge>0 after both fees): {report['n_dislocations']} "
          f"captures across {len(report['dislocation_episodes'])} episodes")
    for e in sorted(report["dislocation_episodes"], key=lambda x: x["max_net_edge"], reverse=True)[:10]:
        print(f"  {e['pair']} {e['direction']}: max_edge=${e['max_net_edge']:.4f} "
              f"dur={e['duration_s']:.0f}s over {e['n_captures']} captures")
    if report["n_dislocations"] == 0:
        print("  -> zero fee-clearing cross-venue dislocations in this window (expected on "
              "thin/aligned books; a real one is what S17's live/kill decision hunts for).")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S17 recurring-macro lead-lag first cut (read-only, descriptive)")
    ap.add_argument("--tape-dir", default=str(TAPE_DIR))
    ap.add_argument("--min-captures", type=int, default=MIN_CAPTURES)
    ap.add_argument("--cpi-note", action="store_true",
                    help="print a provenance-only count of the out-of-scope synthetic CPI tape")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--burst-window", nargs=2, metavar=("START", "END"), default=None,
                    help="ISO8601 start end (e.g. 2026-07-14T12:05:00Z 2026-07-14T13:45:00Z): "
                         "run burst-mode (per-ticker signed lead-lag + fillable dislocation "
                         "scan) over sub-hourly event-window tape instead of the hourly first cut")
    ap.add_argument("--poly-fee", type=float, default=0.0,
                    help="Polymarket per-contract taker fee assumption for the dislocation "
                         "scan (default 0.0 — CLOB is ~free today; a model assumption, tagged "
                         "in the report, NOT a fill)")
    args = ap.parse_args(argv)

    if args.burst_window is not None:
        start = parse_window_bound(args.burst_window[0])
        end = parse_window_bound(args.burst_window[1])
        records = load_records(Path(args.tape_dir))
        report = build_burst_report(records, start=start, end=end, poly_fee=args.poly_fee)
        _print_burst_report(report)
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(report, indent=2))
            print(f"wrote {args.json_out}")
        return 0

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
