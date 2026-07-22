"""Screen battery — pilot: cross-sectional outlier + fee-floor interpretation.

Pre-registered parameters (OBS-1, 2026-07-21 — change requires a logged decision,
not a quiet edit; a tuned threshold is a multiple-comparisons leak):

  * Z_MIN = 4.0          robust z (median/MAD, consistency const 1.4826) to flag
  * MIN_CROSS_SECTION = 8  series in the day's cross-section, else the metric is
                           skipped that day (an outlier among 3 peers is noise)
  * TOP_K = 10           max flags per family-metric-day, strongest first — a hard
                           emission cap so a weird tape day cannot flood the ledger
  * MIN_N = 5            per-series row must aggregate >= 5 markets/events to be
                           screened (spread median over 2 markets is not a signal)

This is deliberately a FISHING pass — the discipline lives downstream: persistence
across held-out later days (ledger.py) is the out-of-sample confirmation, and the
graveyard/fee gates keep known-dead shapes from promoting. In-sample flags are
"observed", never more.

Fee-floor interpretation (where one exists):
  * median_spread outliers -> maker half-spread-capture context: cleared iff
    half the median spread exceeds the flat maker fee at the median mid
    (core.pricing.fee_per_contract, MAKER_FEE_RATE). This is the S6/S13 death
    arithmetic run in reverse — most cells will NOT clear, which is the point.
  * median_overround (low tail) -> ladder-buy context: cleared iff -overround
    exceeds per-leg taker fees at uniform member prices (true_arb_edge shape).
  * everything else -> fee_floor_cleared = None (no direct fill interpretation;
    such patterns can inform a lane but can never auto-promote).

Only rows whose price_source_tags are all fillable (real_ask/real_bid — the tape's
bid-side twin of real_ask) may claim a cleared fee floor; anything else is
context-only, per core.source_tag discipline.
"""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional

from core.pricing import MAKER_FEE_RATE, TAKER_FEE_RATE, fee_per_contract

from .graveyard import classify

Z_MIN = 4.0
MIN_CROSS_SECTION = 8
TOP_K = 10
MIN_N = 5
_MAD_CONSISTENCY = 1.4826
# Scale floor when the cross-section is degenerate (MAD == 0, e.g. every series'
# two_sided_share identical): a deviation from a zero-dispersion cross-section IS
# an outlier, but dividing by ~0 turns z into meaningless 1e8-scale noise that then
# dominates TOP_K ordering. 1e-3 (0.1 cent / 0.1 pp) keeps such z values large but
# comparable. Pre-registered with the other OBS-1 params.
_MAD_FLOOR = 1e-3

SCREEN_METRICS = {
    "universe_sweep": ["median_spread", "two_sided_share", "total_volume_24h", "n_markets"],
    "orderbook_depth": ["median_spread", "two_sided_share", "median_touch_queue", "median_depth"],
    "sports_pairs": ["median_overround", "completeness_rate"],
}

# The tape's bid-side provenance twin of real_ask (see orderbook_depth price_source_tags).
_FILLABLE_ROW_TAGS = frozenset({"real_ask", "real_bid", "broker_truth"})


def _row_n(row: Dict[str, Any]) -> int:
    return int(row.get("n_markets") or row.get("n_events") or 0)


def _row_fillable(row: Dict[str, Any]) -> bool:
    tags = row.get("price_source_tags") or []
    return bool(tags) and all(t in _FILLABLE_ROW_TAGS for t in tags)


def robust_z(value: float, cross_section: List[float]) -> Optional[float]:
    med = statistics.median(cross_section)
    mad = statistics.median([abs(v - med) for v in cross_section])
    denom = max(mad * _MAD_CONSISTENCY, _MAD_FLOOR)
    return (value - med) / denom


def _fee_check(metric: str, direction: str, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Returns {cleared, margin, basis} or None when no fill interpretation exists."""
    if not _row_fillable(row):
        return None
    if metric == "median_spread" and direction == "high":
        spread, mid = row.get("median_spread"), row.get("median_mid")
        if spread is None or mid is None:
            return None
        margin = spread / 2.0 - fee_per_contract(mid, MAKER_FEE_RATE)
        return {"cleared": margin > 0, "margin": round(margin, 6),
                "basis": "half_spread_minus_maker_fee_at_median_mid"}
    if metric == "median_overround" and direction == "low":
        over = row.get("median_overround")
        n = _row_n(row)
        if over is None or over >= 0 or n == 0:
            return None
        # Buy-every-leg cost: per-leg taker fee at uniform member price 1/n_legs.
        # More legs = MORE total fees (3 legs at 1/3 cost ~$0.06 vs 2 at 1/2 ~$0.04),
        # so the conservative (hardest) bar is the MAX plausible leg count for these
        # books: sports_pairs events are 2-3 outcome books -> 3.
        legs = 3
        fees = legs * fee_per_contract(1.0 / legs, TAKER_FEE_RATE)
        margin = -over - fees
        return {"cleared": margin > 0, "margin": round(margin, 6),
                "basis": "neg_overround_minus_{}leg_taker_fees".format(legs)}
    return None


def outlier_screen(family: str, dt: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One family-day of committed aggregates -> {"flags": [...], "screened": [...]}.

    ``screened`` lists the (family, metric) pairs that actually cleared
    MIN_CROSS_SECTION — the ledger needs it to record honest misses (a metric with
    zero flags was still LOOKED AT; a metric with too thin a cross-section was not).
    Flags are sorted and deterministic; each is ledger-ready."""
    flags: List[Dict[str, Any]] = []
    screened: List[List[str]] = []
    eligible = [r for r in rows if _row_n(r) >= MIN_N]
    for metric in SCREEN_METRICS.get(family, []):
        cells = [(r["series"], r[metric], r) for r in eligible
                 if isinstance(r.get(metric), (int, float))]
        if len(cells) < MIN_CROSS_SECTION:
            continue
        screened.append([family, metric])
        xs = [v for _, v, _ in cells]
        scored = []
        for series, v, row in cells:
            z = robust_z(v, xs)
            if z is None or abs(z) < Z_MIN:
                continue
            direction = "high" if z > 0 else "low"
            obs = {
                "family": family,
                "series": series,
                "metric": metric,
                "direction": direction,
                "dt": dt,
                "value": round(float(v), 6),
                "robust_z": round(z, 3),
                "cross_section_n": len(cells),
                "row_n": _row_n(row),
                "price_source_tags": row.get("price_source_tags") or [],
            }
            obs.update(classify(metric, direction))
            fee = _fee_check(metric, direction, row)
            obs["fee_floor"] = fee
            obs["fee_floor_cleared"] = (fee or {}).get("cleared")
            scored.append(obs)
        scored.sort(key=lambda o: (-abs(o["robust_z"]), o["series"]))
        flags.extend(scored[:TOP_K])
    flags.sort(key=lambda o: (o["metric"], -abs(o["robust_z"]), o["series"]))
    return {"flags": flags, "screened": screened}
