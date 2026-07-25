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

import math
from typing import Any, Optional, Sequence

PRICE_TICK = 0.01


def whole_contracts_available(size: Any) -> int:
    """THE sanctioned integer coercion of an order-book ladder level's size (L47).

    L47 forbids coercing a ladder size to int "without an explicit, justified rounding
    rule", because persisted `yes_bids`/`no_bids` sizes are FLOATS and genuinely fractional
    (real-tape census over `tape/orderbook_depth/dt=*.jsonl`, 2026-07-25: 747,412 of
    14,756,132 levels = 5.07% fractional; 5,832 levels with 0 < size < 1; none zero, none
    negative — descriptive level counts, not prices). This function IS that explicit rule,
    stated once and cited by every caller that needs a contract count:

        A fill can only lift WHOLE contracts, so the liftable quantity at a level is the
        FLOOR of its resting size, never a round-half-up and never a ceil. Flooring is the
        conservative direction: it can only under-state available depth (fewer/cheaper-to-
        model fills), never manufacture depth that isn't resting. A level with
        0 < size < 1 therefore contributes ZERO liftable contracts — correct, since you
        cannot lift a fraction of a contract — and the caller walks on to the next level.

    Numerically identical to a bare `int(size)` for every finite size >= 0 (which is every
    size the real tape has ever carried), so adopting it changes no existing paper P&L.

    Defensiveness, stated precisely rather than as a blanket claim (it was oversold in an
    earlier draft of this docstring; L155):

      * `None` / non-numeric (`""`, `[]`, a dict) -> 0. On the ONLY production caller today,
        `execution/fill_models.py::_taker_depth`, this branch is DEAD CODE: the ladder is
        built by `_ask_ladder_from_bids`, which already does `float(level[1])` and would have
        raised TypeError/ValueError one step earlier. The branch is live only for a future
        caller that hands this function a RAW, un-floated field straight off a tape record.
      * NaN / +/-inf -> 0. This is the only genuinely NEW behaviour on the fill path, and it
        is a CRASH-to-SILENCE conversion, not added protection: a bare `int(float("nan"))`
        raises ValueError (and `int(inf)` OverflowError), whereas here the level silently
        contributes zero liftable contracts and the walk continues to the next level. The
        trade is deliberate and is in the conservative UNDER-fill direction (never invents
        depth), but it means a malformed-size bug shows up as a quietly thin book instead of
        a loud failure. Nothing in the committed tape carries a non-finite size (real-tape
        census 2026-07-25 over 14,756,132 levels: 0 non-finite, 0 negative), so this path is
        untriggered today; if that ever changes, prefer surfacing it at the collector.
      * negative -> 0 rather than a negative "available depth" (also untriggered by real
        tape; a bare `int(-3.5)` would return -3, which is nonsense as a liftable quantity).

    Anything that needs a ladder size as a FLOAT (queue-ahead totals, capturable depth,
    turnover) must NOT call this — it must keep the float, per L47. This exists only for
    the "how many whole contracts can I lift here" question.
    """
    try:
        val = float(size)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(val) or val <= 0.0:
        return 0
    return int(math.floor(val))


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
