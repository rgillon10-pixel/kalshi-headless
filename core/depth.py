"""Ladder-depth helpers — THE sanctioned site for "how much is really resting near the
top of book" (L67: the two-sided-depth-illusion lesson).

A maker-spread candidate (S30, `findings/2026-07-15-q21-ideagen-edge-hunter.md`) rested its
whole case on "the wide KBO spread is backed by thousands of two-sided contracts (4,601 yes /
10,556 no)" — that figure was the total ladder summed across every price level, dominated by
deep-OTM lottery bids (98.83% of the yes-ladder size sat at price <= 0.10, six cents off the
27c spread it was claimed to back). Capture happens at the top of book: the fillable number is
the size resting WITHIN a few cents of the best price, never the ladder total. This module
gives that number one home so a future maker-spread claim reaches for it by default instead of
re-deriving (and re-mis-deriving) a ladder sum per script.

Ladders are `[price, size]` pairs, sizes are FLOATS (L47) and summed as floats, never int-
coerced; an empty/None ladder is a valid one-sided book (L23) and sums to 0.0. Pure functions:
deterministic, no clock, no network.
"""
from __future__ import annotations

from typing import Optional, Sequence

PRICE_TICK = 0.01


def capturable_depth(ladder: Optional[Sequence[Sequence[float]]], best_price: Optional[float],
                      *, band_cents: float = 5.0, tick: float = PRICE_TICK) -> float:
    """Sum of `ladder` resting size within `band_cents` of `best_price` (L67) — the
    fillable-near-top-of-book number, as opposed to the whole-ladder total.

    None/empty ladder, or `best_price` of None, sums to 0.0 (valid one-sided book, L23) rather
    than raising. A level is included when `|price - best_price| <= band_cents/100 + tick/2`
    (tick-tolerant, mirrors `bid_size_at_or_above`'s comparison style)."""
    if not ladder or best_price is None:
        return 0.0
    band = band_cents / 100.0
    total = 0.0
    for level in ladder:
        if level is None or len(level) < 2 or level[0] is None or level[1] is None:
            continue
        price, size = float(level[0]), float(level[1])
        if abs(price - best_price) <= band + tick / 2.0:
            total += size
    return total


def total_ladder_depth(ladder: Optional[Sequence[Sequence[float]]]) -> float:
    """Sum of ALL `ladder` resting size, every price level — the whole-ladder total that
    L67 warns is NOT evidence of a capturable spread by itself. Exists so a caller can report
    `total_ladder_depth` alongside `capturable_depth` and show the gap explicitly, rather than
    quoting the total alone as if it were fillable."""
    if not ladder:
        return 0.0
    total = 0.0
    for level in ladder:
        if level is None or len(level) < 2 or level[1] is None:
            continue
        total += float(level[1])
    return total


def lottery_tail_fraction(ladder: Optional[Sequence[Sequence[float]]], best_price: Optional[float],
                           *, band_cents: float = 5.0, tick: float = PRICE_TICK) -> Optional[float]:
    """Fraction of `total_ladder_depth` that sits OUTSIDE the `band_cents` capturable band
    around `best_price` (the L67 "lottery tail" — e.g. KBO's 98.83% of yes-size at price
    <= 0.10 while the spread it was claimed to back sat at 27c). None on an empty ladder or a
    zero total (undefined ratio), never a divide-by-zero."""
    total = total_ladder_depth(ladder)
    if total <= 0.0:
        return None
    capturable = capturable_depth(ladder, best_price, band_cents=band_cents, tick=tick)
    return (total - capturable) / total
