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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.io import REPO_ROOT
from core.pricing import (
    POLYMARKET_US_TAKER_RATE,
    TAKER_FEE_RATE,
    fee_per_contract,
    polymarket_fee_per_contract,
)

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


# --------------------------------------------------------------------------- #
# Burst-mode (Q19) — sub-hourly WC-round event-window lead-lag + fillable
# cross-venue dislocation scan. Direct port of the s17 burst mode, adapted to the
# WC-round schema (`polymarket_pairs.v1`, keyed by `kalshi.ticker`) with the Q31
# FEE CORRECTION: BOTH crossing legs are charged their venue's REAL taker fee —
# Kalshi via `core.pricing.fee_per_contract` (taker, round-up-to-cent), Polymarket
# via `core.pricing.polymarket_fee_per_contract` (rate·p·(1−p), no round-up, default
# the Polymarket US taker rate 0.05). The stale s17 assumption (Poly fee ≈ 0) is
# WRONG post-2026-07-15 (Q31 / regime change); a `--poly-fee-rate 0.0` sensitivity
# reproduces the old fee-free view, reported alongside the primary result.
#
# HONESTY BOUNDARIES (same as the CPI leg — do not oversell):
#   - Both crossing legs lift resting size, so neither is a free maker fill (S13/L5):
#     the Kalshi leg is charged the TAKER fee, the conservative fee.
#   - A positive net_edge is a fillable-at-observed-quotes locked pair, NOT realised
#     P&L: the WC tape is SIZE-BLIND (only best_ask/best_bid, no depth), captures are
#     near-simultaneous within a pass (single `captured_at`, cannot prove venue
#     simultaneity), and the position carries cross-venue settlement + capital-rail
#     risk — the very segmentation S9 rests on. This mode SCANS dislocations; it books
#     none and makes NO CI/verdict claim (L57).
# --------------------------------------------------------------------------- #

# per-capture quote carrying BOTH sides of BOTH venues' books
BurstQuote = Dict[str, Optional[float]]


def _ticker_key(record: Dict[str, Any]) -> Optional[str]:
    """WC schema has no meeting/bucket — the Kalshi ticker IS the pair key."""
    kalshi = record.get("kalshi") or {}
    ticker = kalshi.get("ticker")
    return str(ticker) if ticker is not None else None


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_capture_time(record: Dict[str, Any]) -> Optional[datetime]:
    """Aware-UTC datetime of one record's capture instant. Prefers full-ISO
    `captured_at`; falls back to the compact `capture_id` (YYYYMMDDThhmmss[Z] or
    YYYYMMDDThhmm[Z]). Returns None if neither parses (caller drops the record)."""
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
    """Parse a CLI window bound (ISO 8601, e.g. 2026-07-15T20:10:00Z) to aware UTC."""
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
    """min/median/max inter-capture gap in seconds across DISTINCT capture instants —
    the honesty check that a window is genuinely burst-cadence (60-120s) and not sparse
    hourly tape masquerading as one. A median near 3600s means this is NOT burst tape."""
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
    """Per-ticker series carrying BOTH sides of BOTH venues' books (Kalshi yes-ask &
    yes-bid, Polymarket best-ask & best-bid) sorted by capture time. De-dupes by capture
    instant (last-write-wins, tape-append-safe). Drops Polymarket book-fetch failures.
    A row keeps whichever quotes were present; a dislocation is only scored when the two
    legs it needs are both present."""
    by_ticker: Dict[str, Dict[datetime, BurstQuote]] = defaultdict(dict)
    for r in records:
        poly = r.get("polymarket") or {}
        if not poly.get("book_fetch_ok", True):
            continue
        key = _ticker_key(r)
        t = parse_capture_time(r)
        if key is None or t is None:
            continue
        kalshi = r.get("kalshi") or {}
        by_ticker[key][t] = {
            "kalshi_yes_ask": _as_float(kalshi.get("yes_ask")),
            "kalshi_yes_bid": _as_float(kalshi.get("yes_bid")),
            "poly_best_ask": _as_float(poly.get("best_ask")),
            "poly_best_bid": _as_float(poly.get("best_bid")),
        }
    series: Dict[str, List[Tuple[datetime, BurstQuote]]] = {}
    for key, by_t in by_ticker.items():
        series[key] = [(t, by_t[t]) for t in sorted(by_t)]
    return series


def per_ticker_leadlag(burst_series: Dict[str, List[Tuple[datetime, BurstQuote]]],
                       *, min_steps: int = 3, margin: float = 0.05) -> List[Dict[str, Any]]:
    """SIGNED lead-lag per ticker at burst resolution: does Kalshi's move predict
    Polymarket's NEXT move (kalshi leads) more than the reverse? `signed_leader` is
    'kalshi'/'polymarket' when one lag's correlation beats the other by `margin`, else
    'none'. Uses the Kalshi yes-ask and Polymarket best-ask series (both real_ask)."""
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
        leader: Optional[str] = None
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


def _drop_top_crossproduct_pair(xs: Sequence[float], ys: Sequence[float]
                                ) -> Tuple[Optional[float], Optional[int]]:
    """Find the single (x_i, y_i) pair with the largest centered cross-product contribution
    to pearson(xs, ys) — the one lag-pair a single-shock correlation leans on most — drop it,
    and return (recomputed ρ, dropped index). This is the honest L57 leave-one-out for a
    DIRECTIONAL lead claim: it removes the biggest driver OF THAT DIRECTION's ρ, not merely
    the biggest raw price move (which at burst resolution is often a CONTEMPORANEOUS collapse
    that never contributed to the lead in the first place)."""
    n = len(xs)
    if n < 3:
        return (None, None)
    mx = sum(xs) / n
    my = sum(ys) / n
    contrib = [(xs[i] - mx) * (ys[i] - my) for i in range(n)]
    j = max(range(n), key=lambda i: contrib[i])
    xs2 = [v for i, v in enumerate(xs) if i != j]
    ys2 = [v for i, v in enumerate(ys) if i != j]
    return (pearson(xs2, ys2), j)


def per_ticker_leadlag_drop_largest(
        burst_series: Dict[str, List[Tuple[datetime, BurstQuote]]],
        *, min_steps: int = 3) -> List[Dict[str, Any]]:
    """Leave-one-out robustness (L57): for each ticker AND each direction, drop the single
    lag-pair that contributes most to that direction's lag±1 ρ (the shock/goal repricing the
    correlation leans on) and recompute. If the 'lead' collapses when that one pair is
    removed, it was a one-tick artifact, not a persistent relationship — report it, don't
    oversell it. Also records the largest RAW combined move step for provenance (the naive
    'drop biggest move' which, at burst resolution, may be a contemporaneous collapse)."""
    out: List[Dict[str, Any]] = []
    for key, rows in burst_series.items():
        seq = [(q["kalshi_yes_ask"], q["poly_best_ask"]) for _, q in rows
               if q["kalshi_yes_ask"] is not None and q["poly_best_ask"] is not None]
        dk = [b[0] - a[0] for a, b in zip(seq, seq[1:])]
        dp = [b[1] - a[1] for a, b in zip(seq, seq[1:])]
        if len(dk) < min_steps + 1:
            continue
        # poly-leads pairs: (dp[i], dk[i+1]); kalshi-leads pairs: (dk[i], dp[i+1]).
        rho_p_drop, p_idx = _drop_top_crossproduct_pair(dp[:-1], dk[1:])
        rho_k_drop, k_idx = _drop_top_crossproduct_pair(dk[:-1], dp[1:])
        raw_i = max(range(len(dk)), key=lambda i: abs(dk[i]) + abs(dp[i]))
        out.append({
            "pair": key,
            "n_pairs": len(dk) - 1,
            "rho_polymarket_leads_full": pearson(dp[:-1], dk[1:]),
            "rho_polymarket_leads_drop_top_pair": rho_p_drop,
            "dropped_poly_leads_pair_index": p_idx,
            "rho_kalshi_leads_full": pearson(dk[:-1], dp[1:]),
            "rho_kalshi_leads_drop_top_pair": rho_k_drop,
            "dropped_kalshi_leads_pair_index": k_idx,
            "largest_raw_move_step_index": raw_i,
            "largest_raw_move_delta_kalshi": dk[raw_i],
            "largest_raw_move_delta_poly": dp[raw_i],
        })
    return out


def _best_dislocation(quote: BurstQuote, *, kalshi_fee_rate: float,
                      poly_fee_rate: float) -> Optional[Dict[str, Any]]:
    """Best (max net-edge) fillable cross-venue Yes/Yes pair at one capture, or None if
    neither direction's two legs are both present. net_edge > 0 is a locked, outcome-neutral
    dislocation net of BOTH venues' REAL fees (Kalshi taker on the crossing leg; Polymarket
    per `poly_fee_rate` on the Polymarket leg being crossed). Directions:
      A buy_kalshi_sell_poly: poly_best_bid − kalshi_yes_ask − fee_k(kalshi_yes_ask) − fee_p(poly_best_bid)
      B buy_poly_sell_kalshi: kalshi_yes_bid − poly_best_ask − fee_k(kalshi_yes_bid) − fee_p(poly_best_ask)"""
    ka, kb = quote["kalshi_yes_ask"], quote["kalshi_yes_bid"]
    pa, pb = quote["poly_best_ask"], quote["poly_best_bid"]
    cands: List[Tuple[float, str]] = []
    if ka is not None and pb is not None:
        edge_a = (pb - ka
                  - fee_per_contract(ka, kalshi_fee_rate)
                  - polymarket_fee_per_contract(pb, poly_fee_rate))
        cands.append((edge_a, "buy_kalshi_sell_poly"))
    if pa is not None and kb is not None:
        edge_b = (kb - pa
                  - fee_per_contract(kb, kalshi_fee_rate)
                  - polymarket_fee_per_contract(pa, poly_fee_rate))
        cands.append((edge_b, "buy_poly_sell_kalshi"))
    if not cands:
        return None
    edge, direction = max(cands, key=lambda x: x[0])
    return {"net_edge": edge, "direction": direction}


def dislocation_scan(burst_series: Dict[str, List[Tuple[datetime, BurstQuote]]],
                     *, kalshi_fee_rate: float = TAKER_FEE_RATE,
                     poly_fee_rate: float = POLYMARKET_US_TAKER_RATE) -> List[Dict[str, Any]]:
    """Every capture whose best cross-venue pair clears BOTH fees (net_edge > 0)."""
    hits: List[Dict[str, Any]] = []
    for key, rows in burst_series.items():
        for t, quote in rows:
            best = _best_dislocation(quote, kalshi_fee_rate=kalshi_fee_rate,
                                     poly_fee_rate=poly_fee_rate)
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
                         poly_fee_rate: float = POLYMARKET_US_TAKER_RATE) -> List[Dict[str, Any]]:
    """Contiguous runs of positive-edge captures on the SAME ticker+direction → one
    episode each, with width (max net_edge) and duration (wall-clock seconds first→last
    capture + capture count). A dislocation surviving many captures is a very different
    animal from a single-tick blip — the width × duration distribution (L57) is the
    stale-nominal-basis vs real-shock discriminator."""
    episodes: List[Dict[str, Any]] = []
    for key, rows in burst_series.items():
        run: List[Tuple[datetime, float]] = []
        run_dir: Optional[str] = None
        for t, quote in rows:
            best = _best_dislocation(quote, kalshi_fee_rate=kalshi_fee_rate,
                                     poly_fee_rate=poly_fee_rate)
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


def _fee_model_block(kalshi_fee_rate: float, poly_fee_rate: float) -> Dict[str, Any]:
    return {
        "kalshi_rate": kalshi_fee_rate,
        "kalshi_fee_fn": "core.pricing.fee_per_contract (taker; both crossing legs)",
        "poly_rate": poly_fee_rate,
        "poly_fee_fn": "core.pricing.polymarket_fee_per_contract",
        "poly_fee_source": ("assumed_zero_polymarket_clob" if poly_fee_rate == 0.0
                            else "polymarket_us_taker_v2"),
    }


def build_burst_report(records: Sequence[Dict[str, Any]], *,
                       start: Optional[datetime] = None, end: Optional[datetime] = None,
                       kalshi_fee_rate: float = TAKER_FEE_RATE,
                       poly_fee_rate: float = POLYMARKET_US_TAKER_RATE) -> Dict[str, Any]:
    window = filter_burst_window(records, start, end) if (start and end) else list(records)
    bseries = build_burst_series(window)
    disl = dislocation_scan(bseries, kalshi_fee_rate=kalshi_fee_rate, poly_fee_rate=poly_fee_rate)
    episodes = dislocation_episodes(bseries, kalshi_fee_rate=kalshi_fee_rate, poly_fee_rate=poly_fee_rate)
    # Fee-free-Poly sensitivity (Q31 reproduces the stale-assumption view alongside primary).
    disl_ff = dislocation_scan(bseries, kalshi_fee_rate=kalshi_fee_rate, poly_fee_rate=0.0)
    episodes_ff = dislocation_episodes(bseries, kalshi_fee_rate=kalshi_fee_rate, poly_fee_rate=0.0)
    return {
        "mode": "burst",
        "window_start": start.isoformat() if start else None,
        "window_end": end.isoformat() if end else None,
        "n_records_in_window": len(window),
        "cadence": cadence_stats(window),
        "n_pairs": len(bseries),
        "per_ticker_leadlag": per_ticker_leadlag(bseries),
        "per_ticker_leadlag_drop_largest": per_ticker_leadlag_drop_largest(bseries),
        "n_dislocations": len(disl),
        "dislocations": disl,
        "dislocation_episodes": episodes,
        "fee_model": _fee_model_block(kalshi_fee_rate, poly_fee_rate),
        "poly_fee_free_sensitivity": {
            "n_dislocations": len(disl_ff),
            "dislocations": disl_ff,
            "dislocation_episodes": episodes_ff,
            "fee_model": _fee_model_block(kalshi_fee_rate, 0.0),
        },
    }


def _print_burst_report(report: Dict[str, Any]) -> None:
    print("=" * 78)
    print("S9 BURST-MODE lead-lag + fillable dislocation scan (read-only — NOT a verdict)")
    print("WC-round leg, both sides real_ask. Kalshi taker fee + Polymarket taker fee")
    print(f"({report['fee_model']['poly_fee_source']}, rate={report['fee_model']['poly_rate']}), "
          "both from core.pricing. Scans dislocations, books none.")
    print("=" * 78)
    cad = report["cadence"]
    print(f"window {report['window_start']} -> {report['window_end']}  "
          f"records={report['n_records_in_window']} pairs={report['n_pairs']}")
    print(f"cadence: distinct_captures={cad['n_distinct_captures']} "
          f"min_gap_s={cad['min_gap_s']} median_gap_s={cad['median_gap_s']} "
          f"max_gap_s={cad['max_gap_s']}")
    if cad["median_gap_s"] is not None and cad["median_gap_s"] > 300:
        print("  -> WARNING median gap > 5min: NOT burst-cadence tape; this is the hourly "
              "noise-floor characterization, not a shock-window result.")
    leaders = [t for t in report["per_ticker_leadlag"] if t["signed_leader"] not in (None, "none")]
    print(f"per-ticker signed lead-lag computed for {len(report['per_ticker_leadlag'])} pairs; "
          f"{len(leaders)} show a directional leader")
    for t in report["per_ticker_leadlag"]:
        print(f"  {t['pair']}: leader={t['signed_leader']} "
              f"rho_k_leads={t['rho_kalshi_leads']} rho_p_leads={t['rho_polymarket_leads']} "
              f"(n={t['n_steps']})")
    for t in report["per_ticker_leadlag_drop_largest"]:
        print(f"  LOO {t['pair']}: rho_p_leads {t['rho_polymarket_leads_full']} -> "
              f"{t['rho_polymarket_leads_drop_top_pair']} (drop top poly-leads pair); "
              f"rho_k_leads {t['rho_kalshi_leads_full']} -> "
              f"{t['rho_kalshi_leads_drop_top_pair']} (drop top kalshi-leads pair); "
              f"largest raw move dK={t['largest_raw_move_delta_kalshi']:.3f} "
              f"dP={t['largest_raw_move_delta_poly']:.3f}")
    print(f"fillable dislocations (net_edge>0 after BOTH real fees): {report['n_dislocations']} "
          f"captures across {len(report['dislocation_episodes'])} episodes")
    for e in sorted(report["dislocation_episodes"], key=lambda x: x["max_net_edge"], reverse=True):
        print(f"  {e['pair']} {e['direction']}: max_edge=${e['max_net_edge']:.4f} "
              f"mean=${e['mean_net_edge']:.4f} dur={e['duration_s']:.0f}s over {e['n_captures']} captures")
    ff = report["poly_fee_free_sensitivity"]
    print(f"[fee-free-Poly sensitivity, rate=0.0] dislocations={ff['n_dislocations']} "
          f"across {len(ff['dislocation_episodes'])} episodes")
    if report["n_dislocations"] == 0:
        print("  -> zero fee-clearing cross-venue dislocations in this window at the real fee model.")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S9 lead-lag first cut (read-only, descriptive)")
    ap.add_argument("--tape-dir", default=str(TAPE_DIR))
    ap.add_argument("--min-captures", type=int, default=MIN_CAPTURES)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--burst-window", nargs=2, metavar=("START", "END"), default=None,
                    help="ISO8601 start end (e.g. 2026-07-15T20:10:00Z 2026-07-15T22:30:00Z): "
                         "run burst-mode (per-ticker signed lead-lag + leave-one-out + fillable "
                         "cross-venue dislocation scan net of BOTH venues' real fees) over "
                         "sub-hourly event-window tape instead of the hourly first cut")
    ap.add_argument("--poly-fee-rate", type=float, default=POLYMARKET_US_TAKER_RATE,
                    help="Polymarket taker fee RATE for the dislocation scan "
                         f"(default {POLYMARKET_US_TAKER_RATE} = Polymarket US taker V2; "
                         "pass 0.0 for the fee-free-Poly sensitivity). Charged via "
                         "core.pricing.polymarket_fee_per_contract, never hand-rolled.")
    args = ap.parse_args(argv)

    if args.burst_window is not None:
        start = parse_window_bound(args.burst_window[0])
        end = parse_window_bound(args.burst_window[1])
        records = load_records(Path(args.tape_dir))
        report = build_burst_report(records, start=start, end=end,
                                    poly_fee_rate=args.poly_fee_rate)
        _print_burst_report(report)
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(report, indent=2))
            print(f"wrote {args.json_out}")
        return 0

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
