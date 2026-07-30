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

# Repo root on sys.path BEFORE the first-party imports below, so BOTH documented invocation
# forms work: `python3 scripts/s17_leadlag_probe.py ...` (what LOOP-QUEUE.md Q19/Q12,
# kb/00-LOG.md and kb/strategies/00-index.md all cite) and
# `PYTHONPATH=. python3 -m scripts.s17_leadlag_probe ...`. Without this line the direct form dies
# with `ModuleNotFoundError: No module named 'scripts'` at the `from scripts.s9_leadlag_probe`
# import below, while `from core...` still resolves — `pyproject.toml` installs
# core/collection/validation/analysis as packages but NOT `scripts`, and the repo-root
# `conftest.py` only repairs sys.path under pytest, never for the CLI. Same two lines, same
# reason, as `scripts/q48_s55_fomc_lag_probe.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.io import REPO_ROOT  # noqa: E402
from core.pricing import (  # noqa: E402
    POLYMARKET_US_TAKER_RATE,
    TAKER_FEE_RATE,
    fee_per_contract,
    polymarket_fee_per_contract,
)
from core.timeutil import parse_iso_utc  # noqa: E402
# Reused, never re-copied (L36/L102 — two byte-identical copies of a helper across scripts is
# a lesson this repo has already paid for): the L57 leave-one-out is implemented ONCE, in
# `scripts/s9_leadlag_probe.py`, and works unchanged here because both burst modes build the
# SAME `BurstQuote` key contract (`kalshi_yes_ask` / `kalshi_yes_bid` / `poly_best_ask` /
# `poly_best_bid`). Cross-script import precedent: `scripts/q48_s55_fomc_lag_probe.py` imports
# `parse_capture_time` from THIS module for the same reason.
from scripts.s9_leadlag_probe import (  # noqa: E402
    dislocation_magnitude,
    _print_magnitude,
    per_ticker_leadlag_drop_largest,
    signed_leader_label,
)

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
# macro shock — exactly the data class this mode is built to read. It does things the hourly
# cut cannot: (a) per-ticker SIGNED lead-lag (which venue reprices first) at burst resolution,
# WITH its L57 leave-one-out stability gate, (b) a fillable cross-venue DISLOCATION scan —
# moments where buying the cheap venue's real ask and selling the rich venue's real bid clears
# BOTH venues' fees, (c) the width x duration x frozen-fraction distribution of those
# dislocations, (d) a release-instant coverage check (L164), and (e) per-capture pair counts,
# so a market disappearing mid-window is visible in the report rather than hand-derived.
#
# HONESTY BOUNDARIES (do not oversell):
#   - Both legs on the Kalshi side are charged the TAKER fee (`core.pricing.fee_per_contract`,
#     never a hand-rolled literal): crossing to buy at the ask OR to sell at the bid both lift
#     resting size, so neither is a free maker fill (the S13 lesson — an assumed maker fill
#     must cite a fill model). This is the conservative fee; a real resting maker fill would be
#     cheaper but cannot be assumed here.
#   - Polymarket's taker fee is charged from its REAL published schedule
#     (`core.pricing.polymarket_fee_per_contract`, Fee Structure V2: rate·p·(1−p), no cent
#     round-up), selected by `--poly-fee-model` (default `schedule`). See the FEE-MODEL
#     CORRECTION note below — the earlier FLAT `--poly-fee` constant was wrong in BOTH
#     directions and is retained only as an explicit `flat` sensitivity.
#   - A positive net_edge is a fillable-at-observed-quotes locked pair (long Yes one venue +
#     short Yes the other = outcome-neutral), NOT a realised P&L: it ignores size/depth at the
#     quote, the cross-venue settlement + capital-rail risk that is the very segmentation S17
#     rests on, and any queue position. This mode SCANS for dislocations; it does not book them
#     and makes no CI/verdict claim. That is the per-event run's job, under the two-agent rule.
#
# FEE-MODEL CORRECTION (2026-07-29, Q19 FOMC leg). Until this run the burst dislocation scan
# charged the Polymarket leg a FLAT per-contract `--poly-fee` (default 0.0). That is wrong in
# both directions and it can flip the answer on real tape:
#   - the 0.0 default UNDER-charges (a genuinely fee-bearing leg booked free), which can
#     manufacture a phantom dislocation — the prime-directive failure mode; and
#   - a naive flat 0.05 OVER-charges ~4x at mid prices (the real schedule is 0.05·p·(1−p) =
#     $0.0125/contract at p=0.50, NOT $0.05), which can erase a real one — the L5 maker/taker
#     mistake in mirror image.
#   On the 2026-07-29 FOMC window the two mis-specified views disagree completely (flat-0.05
#   clears nothing at all; 0.0 clears dozens of captures), and NEITHER is the honest number.
#   The sibling WC-schema probe (`scripts/s9_leadlag_probe.py`) was corrected to the real
#   rate-based schedule on 2026-07-15 (Q31); this module was not, and the fix is applied here.
#   Three models are available and the report always names the one it used:
#     `schedule` (DEFAULT, the honest one) — `core.pricing.polymarket_fee_per_contract(price,
#         rate)` on the crossed Polymarket leg's OWN price, rate default POLYMARKET_US_TAKER_RATE.
#     `flat`     — the legacy constant `--poly-fee F` per contract, kept ONLY so an old
#         invocation reproduces bit-for-bit and so a flat OVER-charge can be shown as a
#         deliberately-too-harsh sensitivity.
#     `free`     — identically zero, the maximally GENEROUS sensitivity (Polymarket's
#         international geopolitics/econ category is fee-free today).
#   The L32 discipline is to BRACKET a verdict with the generous and the harsh cut and only
#   believe a result that survives both; `schedule` is the headline, `free`/`flat` the brackets.
# --------------------------------------------------------------------------- #

# (capture_dt, kalshi_yes_ask, kalshi_yes_bid, poly_best_ask, poly_best_bid)
BurstQuote = Dict[str, Optional[float]]

# The four quotes a BurstQuote carries. Used by the L32 frozen-pair check: "frozen" for THIS
# probe means all four — both venues, both sides — identical between two consecutive captures,
# i.e. neither book moved at all, so no fill can have occurred against either.
QUOTE_KEYS = ("kalshi_yes_ask", "kalshi_yes_bid", "poly_best_ask", "poly_best_bid")

POLY_FEE_MODELS = ("schedule", "flat", "free")

DEFAULT_POLY_FEE_MODEL = "schedule"


class PolyFeeModel:
    """How the crossed POLYMARKET leg is charged. Never hand-rolls the formula (L5/L18): the
    `schedule` model delegates to `core.pricing.polymarket_fee_per_contract`, the single
    sanctioned Polymarket fee site.

      schedule — rate·p·(1−p) on that leg's own price (Fee Structure V2, no cent round-up).
                 THE DEFAULT and the headline model.
      flat     — a constant per-contract fee (the legacy `--poly-fee F`), kept as an explicit
                 sensitivity only. At mid prices a flat 0.05 over-charges ~4x.
      free     — identically zero: the maximally generous sensitivity.

    `source` is the provenance string that lands in the report's `fee_model` block. A model
    that charges identically zero is tagged `assumed_zero_polymarket_clob` whichever way it
    was spelled, because that is the honest description of what was assumed."""

    def __init__(self, model: str = DEFAULT_POLY_FEE_MODEL, *, flat_fee: float = 0.0,
                 rate: float = POLYMARKET_US_TAKER_RATE) -> None:
        if model not in POLY_FEE_MODELS:
            raise ValueError(f"poly fee model must be one of {POLY_FEE_MODELS}, got {model!r}")
        self.model = model
        # A flat amount is meaningless under the other two models; keep it at 0.0 so
        # `as_dict()` can never advertise a fee that was not charged.
        self.flat_fee = float(flat_fee) if model == "flat" else 0.0
        self.rate = float(rate)

    def fee(self, price: float) -> float:
        if self.model == "schedule":
            return polymarket_fee_per_contract(price, self.rate)
        if self.model == "flat":
            return self.flat_fee
        return 0.0

    @property
    def source(self) -> str:
        if self.model == "schedule":
            return "core.pricing.polymarket_fee_per_contract"
        if self.model == "flat" and self.flat_fee != 0.0:
            return "explicit_cli_flat"
        return "assumed_zero_polymarket_clob"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "poly_fee_model": self.model,
            "poly_fee_source": self.source,
            # Only meaningful under `schedule`; reported as None otherwise so a reader cannot
            # mistake a carried-over default for the rate that was actually applied.
            "poly_fee_rate": self.rate if self.model == "schedule" else None,
            "poly_fee_per_contract_flat": self.flat_fee if self.model == "flat" else None,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"PolyFeeModel({self.model!r}, flat_fee={self.flat_fee!r}, rate={self.rate!r})"


def _quotes_frozen(a: BurstQuote, b: BurstQuote) -> bool:
    """L32: a consecutive pair with BOTH venues' books entirely unchanged is a no-fill, not
    free income. Missing-on-both-sides counts as unchanged (nothing was observed to move)."""
    return all(a.get(k) == b.get(k) for k in QUOTE_KEYS)


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
            return parse_iso_utc(captured_at)
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
    return parse_iso_utc(text)


def filter_burst_window(records: Sequence[Dict[str, Any]], start: datetime,
                        end: datetime) -> List[Dict[str, Any]]:
    """Records whose capture instant falls in [start, end] (inclusive)."""
    out: List[Dict[str, Any]] = []
    for r in records:
        t = parse_capture_time(r)
        if t is not None and start <= t <= end:
            out.append(r)
    return out


def cadence_stats(records: Sequence[Dict[str, Any]], *,
                  seam_threshold_s: float = 120.0) -> Dict[str, Any]:
    """min/median/max inter-capture gap in seconds across DISTINCT capture instants — the
    honesty check that a window is genuinely burst-cadence (60-120s) and not sparse hourly
    tape masquerading as one. A median gap near 3600s means this is NOT burst tape.

    ALSO enumerates every gap above `seam_threshold_s` (the SEAMS). A chunked burst capture
    (ops/burst_capture_chunked.md) pauses to commit between chunks, so a window can be at a
    perfect 90s median and still contain multi-minute holes — the median HIDES them, which is
    exactly how L164's risk materialises. The seam list makes them visible; `--release-instant`
    then answers the decision-relevant question of whether one landed on the release."""
    times = sorted({t for t in (parse_capture_time(r) for r in records) if t is not None})
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
    if not gaps:
        return {"n_distinct_captures": len(times), "min_gap_s": None,
                "median_gap_s": None, "max_gap_s": None,
                "seam_threshold_s": seam_threshold_s,
                "n_gaps_over_threshold": 0, "gaps_over_threshold_s": []}
    gaps_sorted = sorted(gaps)
    median = gaps_sorted[len(gaps_sorted) // 2]
    seams = sorted((g for g in gaps if g > seam_threshold_s), reverse=True)
    return {"n_distinct_captures": len(times), "min_gap_s": min(gaps),
            "median_gap_s": median, "max_gap_s": max(gaps),
            "seam_threshold_s": seam_threshold_s,
            "n_gaps_over_threshold": len(seams), "gaps_over_threshold_s": seams}


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


# How much one lag-direction's ρ must beat the other's before a pair is called directional at
# all. Named (was an inline 0.05 default) because `LEADLAG_RHO_MAGNITUDE_FLOOR` below is tied to
# it by construction: it would be incoherent to demand a 0.05 DIFFERENCE to name a leader and
# then accept an absolute ρ magnitude smaller than that as a stable lead.
LEADLAG_SIGNED_LEADER_MARGIN = 0.05

# SIGN PRECONDITION — the second, INDEPENDENT gate on the same decision (L235).
#
# The margin above is a DIFFERENCE test, and a difference test over a SIGNED statistic is an
# argmax that can crown a negative winner: with both lag-ρ negative it names the LESS NEGATIVE
# direction the leader. `KXFEDDECISION-26SEP-H0` in this module's own 2026-07-29 FOMC run got
# `leader = polymarket` on ρ = -0.0045 over Kalshi's -0.2536, because -0.0045 > -0.2536.
# "Less negative" is not a lead; two negative lag-ρ mean each venue's move ANTI-predicts the
# other's next move, which supports NO directional claim in either direction.
#
# `LEADLAG_RHO_MAGNITUDE_FLOOR` below does NOT subsume this. It killed that row only by luck —
# |−0.0045| happens to be below 0.05. The verifier's counterexample separates the two gates
# cleanly: `rho_k = -0.30` / `rho_p = -0.20` clears the 0.05 magnitude floor by 6x and, pre-fix,
# was labelled `polymarket` and then `stable`. Magnitude asks "is this ρ large enough to be
# signal?"; sign asks "does it point the way a lead claim requires?" — neither implies the
# other, so both are asked, and the sign gate is the earlier one (it runs here, at leader
# selection, before `leadlag_stability` ever sees the row).
#
# The rule itself lives in ONE place, `scripts/s9_leadlag_probe.py::signed_leader_label`,
# imported above and shared with the S9 burst probe, whose `per_ticker_leadlag` had the
# byte-identical defect (L36/L102: the divergent twin is the next variant of the bug).


def per_ticker_leadlag(burst_series: Dict[str, List[Tuple[datetime, BurstQuote]]],
                       *, min_steps: int = 3,
                       margin: float = LEADLAG_SIGNED_LEADER_MARGIN) -> List[Dict[str, Any]]:
    """SIGNED lead-lag per pair at burst resolution: does Kalshi's move predict Polymarket's
    NEXT move (kalshi leads) more than the reverse? `signed_leader` is 'kalshi'/'polymarket'
    when one lag's correlation beats the other by `margin` AND that direction's ρ is strictly
    positive (L235 sign precondition, `signed_leader_label`), else 'none'. Uses the Kalshi
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
        leader = signed_leader_label(rho_k_leads, rho_p_leads, margin=margin)
        out.append({
            "pair": key,
            "n_steps": len(dk),
            "rho_contemporaneous": pearson(dk, dp),
            "rho_kalshi_leads": rho_k_leads,
            "rho_polymarket_leads": rho_p_leads,
            "signed_leader": leader,
        })
    return out


# --------------------------------------------------------------------------- #
# L57 leave-one-out stability gate for a burst-mode signed-leader claim.
#
# L57 (June-CPI leg) and the WC-semifinal-2 leg both found the SAME thing: a burst-window
# lead-lag ρ can be almost entirely the work of ONE release/goal lag-pair. CPI collapsed
# 0.902/0.777 → 0.196/0.037 (retaining 22%/5% of magnitude); WC collapsed 0.269/0.290 →
# 0.054/0.053 (retaining 20%/18%). The rule L57 states — "any burst-window lead-lag figure
# MUST be reported WITH the release-tick-removed recompute before any directional claim" —
# was applied BY HAND on those legs. This makes it mechanical for the Fed schema.
#
# Threshold rationale: a claim is UNSTABLE if the leave-one-out recompute retains less than
# half the full ρ's magnitude. 0.5 is deliberately LENIENT — both historical collapses (22%,
# 20%) clear it by a wide margin, so a figure that fails this gate is not a marginal call.
# A sign flip is UNSTABLE regardless of magnitude.
LEADLAG_LOO_RETENTION_FLOOR = 0.5

# MAGNITUDE FLOOR — L27's lesson applied to a correlation instead of a P&L.
#
# The retention test above is a RATIO, and a ratio is meaningless when its denominator is noise.
# The 2026-07-29 FOMC window produced the exact pathology: `KXFEDDECISION-26SEP-H0` was labelled
# `stable` on rho_full = -0.004471504399603508 — |ρ| = 0.0045, pure noise — purely because the
# leave-one-out recompute moved it FURTHER from zero (-0.0409), giving retention = 9.14 against a
# near-zero denominator. The printed summary then read "1 of 6 leads survives leave-one-out",
# which a reader (or a later run quoting the row) would take for a real surviving lead. It is not
# one, and no retention ratio can make it one. L27 is the same rule for P&L: a positive bootstrap
# lower bound that sits orders of magnitude below a fillable tick is a rounding residue, not an
# edge — so a stability verdict needs a magnitude gate beside it.
#
# WHY 0.05, honestly. Three anchors, none of them tuned to this window's numbers:
#   1. It is this module's OWN `LEADLAG_SIGNED_LEADER_MARGIN`. `per_ticker_leadlag` already
#      refuses to name a leader unless the two lag-ρ differ by 0.05; accepting an ABSOLUTE
#      magnitude below that same 0.05 as a stable lead is internally incoherent. This is the
#      load-bearing reason — the constant is derived from the code, not from the data.
#   2. ρ² is the share of next-step variance explained: |ρ| = 0.05 -> R² = 0.0025, i.e. a quarter
#      of one percent. Nothing below that is a price-discovery claim in any reading.
#   3. It is deliberately LENIENT, not convenient. A real significance bar at this n would be far
#      stricter (~1.96/sqrt(21) ≈ 0.43 for the 21-step pairs) and would kill every ρ this window
#      produced; 0.05 kills only the one that is indistinguishable from zero. It excludes 0.0045
#      by a factor of ~11 — nowhere near the boundary — while the WC-leg's collapsed LOO remnants
#      (0.054/0.053) sit just ABOVE it, i.e. the floor is not set where it would flatter a past
#      verdict (those were killed by the retention gate, on their own merits).
#
# A below-floor verdict is labelled `UNSTABLE_below_magnitude_floor` — deliberately sharing the
# `UNSTABLE` prefix, so every existing consumer that gates on `.startswith("UNSTABLE")` (the
# printer's refusal line included) treats it as NOT a lead without further change.
LEADLAG_RHO_MAGNITUDE_FLOOR = LEADLAG_SIGNED_LEADER_MARGIN

_LOO_DIRECTION_FIELDS = {
    "kalshi": ("rho_kalshi_leads_full", "rho_kalshi_leads_drop_top_pair"),
    "polymarket": ("rho_polymarket_leads_full", "rho_polymarket_leads_drop_top_pair"),
}


def leadlag_stability(per_ticker: Sequence[Dict[str, Any]],
                      loo: Sequence[Dict[str, Any]],
                      *, retention_floor: float = LEADLAG_LOO_RETENTION_FLOOR,
                      magnitude_floor: float = LEADLAG_RHO_MAGNITUDE_FLOOR
                      ) -> List[Dict[str, Any]]:
    """Join each pair's SIGNED leader (`per_ticker_leadlag`) to its per-direction leave-one-out
    recompute (`per_ticker_leadlag_drop_largest`, imported from the S9 probe) and label the
    claim. Verdicts:
      no_directional_claim           — signed_leader is None/'none'; nothing to destabilise.
      UNSTABLE_unrecomputable        — the LOO could not be computed (too few lag-pairs).
      UNSTABLE_below_magnitude_floor — |rho_full| < `magnitude_floor`: a noise-level ρ, so the
                                       retention RATIO is a near-zero-denominator artifact and
                                       cannot certify anything (L27's magnitude gate; includes
                                       rho_full == 0.0, where the ratio is undefined outright).
      UNSTABLE_sign_flip             — the LOO ρ points the other way.
      UNSTABLE_collapsed             — the LOO ρ keeps < `retention_floor` of the full magnitude.
      stable                         — clears the magnitude floor AND survives its own LOO.
    A pair whose verdict starts with UNSTABLE must NOT be reported as a lead (L57). The magnitude
    check runs FIRST, before sign and retention, because it decides whether those two are even
    measuring anything."""
    loo_by_pair = {row["pair"]: row for row in loo}
    out: List[Dict[str, Any]] = []
    for row in per_ticker:
        pair = row["pair"]
        leader = row.get("signed_leader")
        entry: Dict[str, Any] = {
            "pair": pair,
            "signed_leader": leader,
            "rho_full": None,
            "rho_drop_top_pair": None,
            "retention": None,
            # Reported on every row so a reader never has to guess which gate a verdict cleared.
            "magnitude_floor": magnitude_floor,
            "stability": "no_directional_claim",
        }
        if leader in _LOO_DIRECTION_FIELDS:
            full_field, drop_field = _LOO_DIRECTION_FIELDS[leader]
            loo_row = loo_by_pair.get(pair)
            rho_full = loo_row.get(full_field) if loo_row else None
            rho_drop = loo_row.get(drop_field) if loo_row else None
            entry["rho_full"] = rho_full
            entry["rho_drop_top_pair"] = rho_drop
            if rho_full is None or rho_drop is None:
                entry["stability"] = "UNSTABLE_unrecomputable"
            elif abs(rho_full) < magnitude_floor:
                # L27 magnitude gate, checked BEFORE sign/retention. Nothing a ratio does to a
                # noise-level ρ makes it a lead — and when rho_full is exactly 0.0 the ratio is
                # not even defined. The retention is still recorded (when computable) so the
                # near-zero-denominator inflation is visible rather than hidden.
                entry["stability"] = "UNSTABLE_below_magnitude_floor"
                if rho_full != 0.0:
                    entry["retention"] = abs(rho_drop) / abs(rho_full)
            else:
                entry["retention"] = abs(rho_drop) / abs(rho_full)
                if (rho_drop > 0) != (rho_full > 0):
                    entry["stability"] = "UNSTABLE_sign_flip"
                elif entry["retention"] < retention_floor:
                    entry["stability"] = "UNSTABLE_collapsed"
                else:
                    entry["stability"] = "stable"
        out.append(entry)
    return out


# --------------------------------------------------------------------------- #
# Release-instant coverage (L164 made mechanical).
#
# L164: chunking a one-shot burst window to bound sandbox-death data loss introduces a new
# failure mode — a chunk seam (the commit/push/verify pause between two invocations) can land
# on top of the single most decisive instant in the window. L57 already showed an entire
# burst's signal can live in ONE release-instant capture. `cadence_stats` reports only
# min/median/max gap, so a median of 90s HIDES a 720s hole sitting exactly on the release.
# This makes the question a first-class, printed, boolean data-adequacy input.
#
# Threshold: the nominal burst cadence the one-shot triggers are configured for is 60–120s
# (LOOP-QUEUE.md "Burst-capture legs"; ops/burst_capture_chunked.md). The release instant is
# "bracketed" only if BOTH the nearest capture before it and the nearest capture after it sit
# within ONE nominal interval — i.e. the release genuinely falls inside a normal cadence step,
# not inside a seam. Named here, never inlined, so a future run can only change it deliberately.
RELEASE_BRACKET_THRESHOLD_S = 120.0
RELEASE_BRACKET_THRESHOLD_SOURCE = (
    "nominal burst cadence upper bound, 120s (LOOP-QUEUE.md 'Burst-capture legs' 60-120s; "
    "ops/burst_capture_chunked.md)"
)


def release_instant_coverage(records: Sequence[Dict[str, Any]], release_instant: datetime,
                             *, threshold_s: float = RELEASE_BRACKET_THRESHOLD_S
                             ) -> Dict[str, Any]:
    """Is the decisive instant actually bracketed at burst cadence? Reports the nearest
    capture on each side with its SIGNED offset in seconds (negative = before the release),
    the length of the inter-capture gap that contains the instant, and a boolean
    `release_instant_bracketed` true only if BOTH offsets are within `threshold_s`.

    `release_instant_bracketed=False` is a DATA-ADEQUACY verdict input, not a nicety: it means
    the repricing at the instant that matters happened inside an unobserved hole, so no
    consecutive-capture step in the window spans the release and no lead-lag measured over it
    can speak to that repricing at all."""
    times = sorted({t for t in (parse_capture_time(r) for r in records) if t is not None})
    pre = [t for t in times if t <= release_instant]
    post = [t for t in times if t > release_instant]
    nearest_pre = max(pre) if pre else None
    nearest_post = min(post) if post else None
    pre_offset = (nearest_pre - release_instant).total_seconds() if nearest_pre else None
    post_offset = (nearest_post - release_instant).total_seconds() if nearest_post else None
    containing_gap = (post_offset - pre_offset) if (
        pre_offset is not None and post_offset is not None) else None
    bracketed = bool(pre_offset is not None and post_offset is not None
                     and abs(pre_offset) <= threshold_s and abs(post_offset) <= threshold_s)
    return {
        "release_instant": release_instant.isoformat(),
        "n_captures_considered": len(times),
        "nearest_pre_capture": nearest_pre.isoformat() if nearest_pre else None,
        "nearest_pre_offset_s": pre_offset,
        "nearest_post_capture": nearest_post.isoformat() if nearest_post else None,
        "nearest_post_offset_s": post_offset,
        "containing_gap_s": containing_gap,
        "threshold_s": threshold_s,
        "threshold_source": RELEASE_BRACKET_THRESHOLD_SOURCE,
        "release_instant_bracketed": bracketed,
    }


# --------------------------------------------------------------------------- #
# Per-capture membership + L32 frozen-quote fractions.
# --------------------------------------------------------------------------- #

def per_capture_pair_counts(burst_series: Dict[str, List[Tuple[datetime, BurstQuote]]]
                            ) -> List[Dict[str, Any]]:
    """Per-capture pair count with the pairs added/removed since the previous capture. This is
    how a market DISAPPEARING mid-window becomes visible in the report instead of hand-derived:
    Kalshi delists a decided meeting's buckets at the decision, so the count drops and the
    removed tickers are named. A pair that vanishes at the release has ZERO post-release
    observations — whatever the rest of the report says, it cannot speak to that market."""
    by_time: Dict[datetime, set] = defaultdict(set)
    for key, rows in burst_series.items():
        for t, _ in rows:
            by_time[t].add(key)
    out: List[Dict[str, Any]] = []
    prev: Optional[set] = None
    for t in sorted(by_time):
        cur = by_time[t]
        out.append({
            "capture_time": t.isoformat(),
            "n_pairs": len(cur),
            "pairs_added": sorted(cur - prev) if prev is not None else [],
            "pairs_removed": sorted(prev - cur) if prev is not None else [],
        })
        prev = cur
    return out


def frozen_quote_fractions(burst_series: Dict[str, List[Tuple[datetime, BurstQuote]]]
                           ) -> Dict[str, Any]:
    """L32 observability precheck, per pair and pooled: what fraction of consecutive-capture
    pairs had BOTH venues' books entirely unchanged (see `_quotes_frozen`)? A high fraction
    means most "durable" dislocations on that pair are stale nominal quotes nobody traded
    against, not standing income."""
    per_pair: List[Dict[str, Any]] = []
    for key in sorted(burst_series):
        quotes = [q for _, q in burst_series[key]]
        n = len(quotes) - 1
        frozen = sum(1 for a, b in zip(quotes, quotes[1:]) if _quotes_frozen(a, b))
        per_pair.append({
            "pair": key,
            "n_consecutive_pairs": max(n, 0),
            "n_frozen_pairs": frozen,
            "frozen_fraction": (frozen / n) if n > 0 else None,
        })
    total_n = sum(p["n_consecutive_pairs"] for p in per_pair)
    total_f = sum(p["n_frozen_pairs"] for p in per_pair)
    return {
        "per_pair": per_pair,
        "n_consecutive_pairs": total_n,
        "n_frozen_pairs": total_f,
        "frozen_fraction": (total_f / total_n) if total_n > 0 else None,
    }


def _best_dislocation(quote: BurstQuote, *, kalshi_fee_rate: float = TAKER_FEE_RATE,
                      poly_fee_model: Optional[PolyFeeModel] = None) -> Optional[Dict[str, Any]]:
    """Best (max net-edge) fillable cross-venue Yes/Yes pair at one capture, or None if
    neither direction's two legs are both present. net_edge > 0 is a locked, outcome-neutral
    dislocation net of both venues' fees (Kalshi taker on the crossing leg via
    `core.pricing.fee_per_contract`; Polymarket on the crossed Polymarket leg's OWN price via
    `poly_fee_model`, whose `schedule` default is `core.pricing.polymarket_fee_per_contract`).
    Directions:
      A buy_kalshi_sell_poly:  poly_best_bid  − kalshi_yes_ask − fee_k(kalshi_yes_ask) − fee_p(poly_best_bid)
      B buy_poly_sell_kalshi:  kalshi_yes_bid − poly_best_ask  − fee_k(kalshi_yes_bid) − fee_p(poly_best_ask)
    Every returned row records the fees ACTUALLY charged, so a report can be re-audited
    without re-deriving the schedule."""
    model = poly_fee_model or PolyFeeModel(DEFAULT_POLY_FEE_MODEL)
    ka, kb = quote["kalshi_yes_ask"], quote["kalshi_yes_bid"]
    pa, pb = quote["poly_best_ask"], quote["poly_best_bid"]
    cands: List[Dict[str, Any]] = []
    if ka is not None and pb is not None:
        fee_k = fee_per_contract(ka, kalshi_fee_rate)
        fee_p = model.fee(pb)
        cands.append({"net_edge": pb - ka - fee_k - fee_p,
                      "direction": "buy_kalshi_sell_poly",
                      "kalshi_leg_price": ka, "poly_leg_price": pb,
                      "kalshi_fee_charged": fee_k, "poly_fee_charged": fee_p})
    if pa is not None and kb is not None:
        fee_k = fee_per_contract(kb, kalshi_fee_rate)
        fee_p = model.fee(pa)
        cands.append({"net_edge": kb - pa - fee_k - fee_p,
                      "direction": "buy_poly_sell_kalshi",
                      "kalshi_leg_price": kb, "poly_leg_price": pa,
                      "kalshi_fee_charged": fee_k, "poly_fee_charged": fee_p})
    if not cands:
        return None
    best = max(cands, key=lambda c: c["net_edge"])
    best["poly_fee_model"] = model.model
    return best


def dislocation_scan(burst_series: Dict[str, List[Tuple[datetime, BurstQuote]]],
                     *, kalshi_fee_rate: float = TAKER_FEE_RATE,
                     poly_fee_model: Optional[PolyFeeModel] = None) -> List[Dict[str, Any]]:
    """Every capture whose best cross-venue pair clears both fees (net_edge > 0)."""
    model = poly_fee_model or PolyFeeModel(DEFAULT_POLY_FEE_MODEL)
    hits: List[Dict[str, Any]] = []
    for key, rows in burst_series.items():
        for t, quote in rows:
            best = _best_dislocation(quote, kalshi_fee_rate=kalshi_fee_rate,
                                     poly_fee_model=model)
            if best is not None and best["net_edge"] > 0.0:
                hit: Dict[str, Any] = {"pair": key, "capture_time": t.isoformat(),
                                       "quote": quote}
                hit.update(best)
                hits.append(hit)
    return hits


def dislocation_episodes(burst_series: Dict[str, List[Tuple[datetime, BurstQuote]]],
                         *, kalshi_fee_rate: float = TAKER_FEE_RATE,
                         poly_fee_model: Optional[PolyFeeModel] = None) -> List[Dict[str, Any]]:
    """Contiguous runs of positive-edge captures on the SAME pair+direction → one episode
    each, with width (max net_edge over the run), duration (wall-clock seconds first→last
    capture, plus capture count) and the L32 FROZEN fraction of the run's own consecutive
    capture-pairs. A dislocation that survives many captures is a very different animal from
    a single-tick blip — and a durable one whose book never moved is a stale-nominal-quote
    artifact (L31/L32), not an edge. The width x duration x frozen cross is what the
    per-event finding reports."""
    model = poly_fee_model or PolyFeeModel(DEFAULT_POLY_FEE_MODEL)
    episodes: List[Dict[str, Any]] = []
    for key, rows in burst_series.items():
        run: List[Tuple[datetime, float, BurstQuote]] = []
        run_dir: Optional[str] = None
        for t, quote in rows:
            best = _best_dislocation(quote, kalshi_fee_rate=kalshi_fee_rate,
                                     poly_fee_model=model)
            live = best is not None and best["net_edge"] > 0.0
            direction = best["direction"] if best is not None else None
            if live and (run_dir is None or run_dir == direction):
                run.append((t, best["net_edge"], quote))
                run_dir = direction
            else:
                if run:
                    episodes.append(_episode(key, run_dir, run))
                run = [(t, best["net_edge"], quote)] if live else []
                run_dir = direction if live else None
        if run:
            episodes.append(_episode(key, run_dir, run))
    return episodes


def _episode(pair: str, direction: Optional[str],
             run: Sequence[Tuple[datetime, float, BurstQuote]]) -> Dict[str, Any]:
    times = [t for t, _, _ in run]
    edges = [e for _, e, _ in run]
    quotes = [q for _, _, q in run]
    duration_s = (max(times) - min(times)).total_seconds()
    n_consec = len(quotes) - 1
    n_frozen = sum(1 for a, b in zip(quotes, quotes[1:]) if _quotes_frozen(a, b))
    return {
        "pair": pair,
        "direction": direction,
        "n_captures": len(run),
        "start": min(times).isoformat(),
        "end": max(times).isoformat(),
        "duration_s": duration_s,
        "max_net_edge": max(edges),
        "mean_net_edge": sum(edges) / len(edges),
        # L32 attribution: 1.0 means the "dislocation" persisted purely because NEITHER book
        # moved — a no-fill, not durable income.
        "n_consecutive_pairs": n_consec,
        "n_frozen_pairs": n_frozen,
        "frozen_pairs_fraction": (n_frozen / n_consec) if n_consec else None,
    }


def build_burst_report(records: Sequence[Dict[str, Any]], *,
                       start: Optional[datetime] = None, end: Optional[datetime] = None,
                       kalshi_fee_rate: float = TAKER_FEE_RATE,
                       poly_fee_model: Optional[PolyFeeModel] = None,
                       release_instant: Optional[datetime] = None) -> Dict[str, Any]:
    model = poly_fee_model or PolyFeeModel(DEFAULT_POLY_FEE_MODEL)
    window = filter_burst_window(records, start, end) if (start and end) else list(records)
    bseries = build_burst_series(window)
    disl = dislocation_scan(bseries, kalshi_fee_rate=kalshi_fee_rate, poly_fee_model=model)
    episodes = dislocation_episodes(bseries, kalshi_fee_rate=kalshi_fee_rate,
                                    poly_fee_model=model)
    per_ticker = per_ticker_leadlag(bseries)
    loo = per_ticker_leadlag_drop_largest(bseries)
    fee_model: Dict[str, Any] = {
        "kalshi_rate": kalshi_fee_rate,
        "kalshi_fee_fn": "core.pricing.fee_per_contract (taker; both crossing legs)",
    }
    fee_model.update(model.as_dict())
    return {
        "mode": "burst",
        "window_start": start.isoformat() if start else None,
        "window_end": end.isoformat() if end else None,
        "n_records_in_window": len(window),
        "cadence": cadence_stats(window),
        "release_coverage": (release_instant_coverage(window, release_instant)
                             if release_instant is not None else None),
        "n_pairs": len(bseries),
        "per_capture_pair_counts": per_capture_pair_counts(bseries),
        "frozen_quotes": frozen_quote_fractions(bseries),
        "per_ticker_leadlag": per_ticker,
        "per_ticker_leadlag_drop_top_pair": loo,
        "leadlag_stability": leadlag_stability(per_ticker, loo),
        "n_dislocations": len(disl),
        "dislocations": disl,
        "dislocation_episodes": episodes,
        "dislocation_magnitude": dislocation_magnitude(disl, episodes),
        "fee_model": fee_model,
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
    if cad.get("n_gaps_over_threshold"):
        print(f"  SEAMS: {cad['n_gaps_over_threshold']} gap(s) > "
              f"{cad['seam_threshold_s']}s: {[round(g, 1) for g in cad['gaps_over_threshold_s']]} "
              "— the median above HIDES these (chunked-capture commit pauses, L164).")
    if cad["median_gap_s"] is not None and cad["median_gap_s"] > 300:
        print("  -> WARNING median gap > 5min: this is NOT burst-cadence tape; lead-lag at this "
              "resolution is the same noise-floor characterization the hourly first cut already "
              "gave, not a shock-window result.")

    cov = report.get("release_coverage")
    if cov is not None:
        print("-" * 78)
        print(f"RELEASE-INSTANT COVERAGE (L164) — instant {cov['release_instant']}")
        print(f"  nearest PRE  capture: {cov['nearest_pre_capture']} "
              f"(offset {cov['nearest_pre_offset_s']}s)")
        print(f"  nearest POST capture: {cov['nearest_post_capture']} "
              f"(offset {cov['nearest_post_offset_s']}s)")
        print(f"  gap containing the instant: {cov['containing_gap_s']}s   "
              f"threshold={cov['threshold_s']}s ({cov['threshold_source']})")
        if cov["release_instant_bracketed"]:
            print("  -> release_instant_bracketed=TRUE: the decisive instant sits inside a "
                  "normal cadence step; a lead-lag step spanning the release EXISTS.")
        else:
            print("  -> release_instant_bracketed=FALSE: **DATA-ADEQUACY FAILURE** — the "
                  "decisive instant falls inside an unobserved hole, so NO consecutive-capture "
                  "step in this window spans the release. Every lead-lag figure below is "
                  "measured over non-release steps and cannot speak to the release repricing "
                  "(L57/L164).")
        print("-" * 78)

    counts = report.get("per_capture_pair_counts") or []
    if counts:
        ns = [c["n_pairs"] for c in counts]
        print(f"per-capture pair count: first={ns[0]} last={ns[-1]} min={min(ns)} max={max(ns)}")
        for c in counts:
            if c["pairs_added"] or c["pairs_removed"]:
                print(f"  {c['capture_time']}: n_pairs={c['n_pairs']} "
                      f"removed={c['pairs_removed']} added={c['pairs_added']}")

    fz = report.get("frozen_quotes") or {}
    if fz.get("n_consecutive_pairs"):
        print(f"L32 frozen consecutive pairs (both venues, both sides unchanged): "
              f"{fz['n_frozen_pairs']}/{fz['n_consecutive_pairs']} = "
              f"{fz['frozen_fraction']:.3f} pooled")

    leaders = [t for t in report["per_ticker_leadlag"] if t["signed_leader"] not in (None, "none")]
    stab = {s["pair"]: s for s in report.get("leadlag_stability", [])}
    n_stable = sum(1 for s in stab.values() if s["stability"] == "stable")
    n_below_floor = sum(1 for s in stab.values()
                        if s["stability"] == "UNSTABLE_below_magnitude_floor")
    print(f"per-ticker signed lead-lag computed for {len(report['per_ticker_leadlag'])} pairs; "
          f"{len(leaders)} show a directional leader, {n_stable} survive leave-one-out (L57)")
    if n_below_floor:
        print(f"  NOTE: {n_below_floor} of those directional leaders is/are BELOW the |rho| "
              f"magnitude floor {LEADLAG_RHO_MAGNITUDE_FLOOR} — a noise-level rho whose "
              "leave-one-out 'retention' ratio is a near-zero-denominator artifact, NOT a "
              "surviving lead. Counted as NOT surviving above (L27's magnitude gate applied to "
              "a correlation).")
    for t in leaders[:10]:
        s = stab.get(t["pair"], {})
        print(f"  {t['pair']}: leader={t['signed_leader']} "
              f"rho_k_leads={t['rho_kalshi_leads']} rho_p_leads={t['rho_polymarket_leads']} "
              f"(n={t['n_steps']})")
        print(f"      LOO: rho_full={s.get('rho_full')} "
              f"rho_drop_top_pair={s.get('rho_drop_top_pair')} "
              f"retention={s.get('retention')} -> {s.get('stability')}")
    if leaders and n_stable == 0:
        print("  -> NO signed-leader claim survives its own leave-one-out: every directional "
              "figure here is a single-lag-pair artifact (L57), NOT a persistent lead. Do not "
              "report it as a lead.")

    print(f"fillable dislocations (net_edge>0 after both fees): {report['n_dislocations']} "
          f"captures across {len(report['dislocation_episodes'])} episodes")
    _print_magnitude(report.get("dislocation_magnitude"))
    for e in sorted(report["dislocation_episodes"], key=lambda x: x["max_net_edge"], reverse=True)[:10]:
        frz = e["frozen_pairs_fraction"]
        frz_txt = "n/a" if frz is None else f"{frz:.2f}"
        print(f"  {e['pair']} {e['direction']}: max_edge=${e['max_net_edge']:.4f} "
              f"dur={e['duration_s']:.0f}s over {e['n_captures']} captures "
              f"frozen_frac={frz_txt}")
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
    ap.add_argument("--poly-fee-model", choices=POLY_FEE_MODELS, default=DEFAULT_POLY_FEE_MODEL,
                    help="how to charge the crossed Polymarket leg in the dislocation scan. "
                         "'schedule' (DEFAULT, honest): core.pricing.polymarket_fee_per_contract "
                         "on that leg's own price. 'flat': the legacy constant --poly-fee F "
                         "(over-charges ~4x at mid prices — a deliberately harsh sensitivity). "
                         "'free': identically zero (maximally generous sensitivity).")
    ap.add_argument("--poly-fee-rate", type=float, default=POLYMARKET_US_TAKER_RATE,
                    help="rate for --poly-fee-model schedule (default "
                         "core.pricing.POLYMARKET_US_TAKER_RATE; pass 0.0 to model the "
                         "international geopolitics/econ fee-free category)")
    ap.add_argument("--poly-fee", type=float, default=None,
                    help="LEGACY flat per-contract Polymarket fee; valid ONLY with "
                         "--poly-fee-model flat. A flat fee is not Polymarket's real schedule "
                         "(which is rate*p*(1-p)); it is retained as an explicit sensitivity.")
    ap.add_argument("--release-instant", default=None,
                    help="ISO8601 instant of the event's decisive release (e.g. "
                         "2026-07-29T18:00:00Z for the FOMC statement). Reports whether the "
                         "instant is actually BRACKETED at burst cadence — a data-adequacy "
                         "verdict input (L164), not a nicety.")
    args = ap.parse_args(argv)

    if args.burst_window is not None:
        # A silently-ignored fee flag is exactly how the flat-fee bug hid: refuse rather than
        # accept a fee amount under a model that will never charge it.
        if args.poly_fee is not None and args.poly_fee_model != "flat":
            ap.error("--poly-fee is the flat-model amount and is only valid with "
                     f"--poly-fee-model flat (got --poly-fee-model {args.poly_fee_model}). "
                     "Use --poly-fee-rate for the schedule model, or --poly-fee-model free.")
        poly_fee_model = PolyFeeModel(args.poly_fee_model,
                                      flat_fee=(args.poly_fee or 0.0),
                                      rate=args.poly_fee_rate)
        start = parse_window_bound(args.burst_window[0])
        end = parse_window_bound(args.burst_window[1])
        release_instant = (parse_window_bound(args.release_instant)
                           if args.release_instant else None)
        records = load_records(Path(args.tape_dir))
        report = build_burst_report(records, start=start, end=end,
                                    poly_fee_model=poly_fee_model,
                                    release_instant=release_instant)
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
