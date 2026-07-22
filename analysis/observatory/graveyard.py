"""Dead-roster dedup — the Q39 lesson, mechanized.

Q39's graveyard counterfactual sweep established that our candidates died for
STRUCTURAL reasons (fees, fill reality), not detection failures. A bottom-up screen
therefore re-discovers dead patterns by default. Every screen metric+direction maps
to a factor family; families with dead cousins in kb/strategies/00-index.md are
BLOCKED: a pattern in a blocked family can never auto-promote to candidate — it
needs a human- or edge-hunter-authored ``survival_rationale`` naming why it survives
its nearest dead cousin (the Q21 registration rule).

This map is hand-maintained, append-preferred, and each entry cites the registry
row(s) that killed the family. Update it when the registry flips.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

# (metric, direction) -> (factor_family, nearest dead cousins, blocked?)
# direction is "high" / "low": which tail of the cross-section the outlier sits in.
FACTOR_MAP: Dict[Tuple[str, str], Tuple[str, str, bool]] = {
    # Rich books / overpriced tails: S14 (ladder underwriting), S21 (longshot ask),
    # S23 (favorite maker) all TESTED-DEAD — shorting the rich side dies on fees+queue.
    ("median_overround", "high"): ("short-the-overpriced-tail", "S14/S21/S23", True),
    # Cheap ladders (sum < 1): S33 intra-ladder coherence TESTED-DEAD (asynchrony
    # artifact), S34 cross-venue arb TESTED-DEAD.
    ("median_overround", "low"): ("ladder-coherence-arb", "S33/S34", True),
    # Wide spreads invite naive maker spread-capture: S6 and S13 TESTED-DEAD — the
    # flat 1c maker fee exceeds the modal capturable half-spread.
    ("median_spread", "high"): ("naive-maker-spread", "S6/S13", True),
    # Unusually TIGHT spreads for the cross-section: not a killed family — flags a
    # venue-microstructure regime worth reading (L-mech lane).
    ("median_spread", "low"): ("tight-spread-regime", "", False),
    # Liquidity-structure metrics: context for the L-rent/L-flow lanes, no dead
    # cousin, but also no direct fee interpretation (they can inform, not promote).
    ("two_sided_share", "high"): ("liquidity-structure", "", False),
    ("two_sided_share", "low"): ("liquidity-structure", "", False),
    ("median_touch_queue", "high"): ("queue-crowding", "S14 (queue gates)", False),
    ("median_touch_queue", "low"): ("queue-crowding", "", False),
    ("median_depth", "high"): ("liquidity-structure", "", False),
    ("median_depth", "low"): ("liquidity-structure", "", False),
    ("total_volume_24h", "high"): ("flow-concentration", "", False),
    ("total_volume_24h", "low"): ("flow-concentration", "", False),
    ("completeness_rate", "low"): ("collector-health", "", False),
    ("n_markets", "high"): ("universe-shift", "", False),
    ("n_markets", "low"): ("universe-shift", "", False),
}

UNKNOWN = ("unmapped", "", True)  # unmapped metric/direction: blocked by default (trust=FALSE)


def classify(metric: str, direction: str) -> Dict[str, object]:
    fam, cousins, blocked = FACTOR_MAP.get((metric, direction), UNKNOWN)
    return {
        "factor_family": fam,
        "nearest_dead_cousin": cousins or None,
        "graveyard_blocked": blocked,
    }
