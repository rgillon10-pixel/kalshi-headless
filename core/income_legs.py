"""Income-leg volume decomposition — THE sanctioned site for "how much of a small-net-of-
two-legs edge is thin-print optimism" (L39).

A bracket-ladder P&L that nets a small edge against a large loss leg (S14: mean +$0.0925
overround sits on top of a ~$0.51-$0.97 winner-$1 loss) is vulnerable to a queue-blind
`high >= ask AND volume > 0` fill proxy crediting the INCOME leg too easily: a candlestick
bar only proves the price printed, not that a resting offer ahead of the whole queue would
have filled. The loss leg is not so biased (heavy volume genuinely sweeps the offer). S14
found **78% of its $0.093 edge came from sub-100-contract-volume income legs** — this module
gives that decomposition one home so a future small-net-of-two-legs probe reaches for it by
default instead of re-deriving (and re-mis-deriving) a volume-gate filter per script.

Pure functions: deterministic, no clock, no network. Callers pass an already-computed
`Sequence[(income, volume)]` per filled income leg — this module never inspects raw book or
candlestick fields itself (same "caller has already decided" discipline as
`core.bootstrap.bracket_by_movement`, L32).
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple


def income_leg_thin_fraction(legs: Sequence[Tuple[float, float]], *,
                              volume_threshold: float) -> Optional[float]:
    """Fraction of TOTAL leg income coming from legs whose volume is STRICTLY BELOW
    `volume_threshold` (the S14-shaped number: "78% of the edge came from sub-100-contract
    legs"). `legs` is a sequence of `(income, volume)` pairs, one per filled income leg.

    None on zero (or negative) total income — an undefined ratio, never a divide-by-zero."""
    total = sum(income for income, _ in legs)
    if total <= 0.0:
        return None
    thin = sum(income for income, volume in legs if volume < volume_threshold)
    return thin / total


def income_leg_edge_at_gate(legs: Sequence[Tuple[float, float]], *,
                             volume_threshold: float) -> float:
    """Sum of leg income restricted to legs with volume >= `volume_threshold` — the
    volume-gated income total (L39's "vol50"/"vol100" haircut columns), so a caller can add
    it to the (unbiased) loss leg and get a haircut P&L without re-deriving the filter."""
    return sum(income for income, volume in legs if volume >= volume_threshold)
