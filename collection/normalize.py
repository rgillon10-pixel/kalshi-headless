"""Shared orderbook normalization — the bid->opposite-ask complement.

Single source for turning a raw Kalshi `orderbook_fp` dict into a depth snapshot, used
by both the forward capture tool (collection/capture_orderbooks.py) and the Milestone-1
dry-run (collection/m1_capture.py). Kalshi posts only bids per outcome; the tradeable
ask on one side is the complement of the other side's best bid (the price H1 trades on).

Pure function: deterministic given its input, no clock, no network.
"""
from __future__ import annotations

from typing import Any, Dict


def normalize_snapshot(ticker: str, ob: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw Kalshi orderbook_fp dict into a depth snapshot.

    Kalshi posts only bids per outcome (yes_dollars / no_dollars). The tradeable ask
    on one side is the complement of the other side's best bid.
    """
    yb = sorted(([float(p), float(sz)] for p, sz in (ob.get("yes_dollars") or [])),
                key=lambda x: -x[0])
    nb = sorted(([float(p), float(sz)] for p, sz in (ob.get("no_dollars") or [])),
                key=lambda x: -x[0])
    byb = yb[0][0] if yb else None
    nbb = nb[0][0] if nb else None
    return {
        "ticker": ticker, "yes_bids": yb, "no_bids": nb,
        "best_yes_bid": byb, "best_no_bid": nbb,
        "best_yes_ask": round(1 - nbb, 4) if nbb is not None else None,
        "best_no_ask": round(1 - byb, 4) if byb is not None else None,
        "depth": len(yb) + len(nb),
    }
