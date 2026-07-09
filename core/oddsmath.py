"""Sportsbook odds math — American/decimal conversion + de-vig.

A de-vig turns quoted odds (which embed the book's overround) into a fair probability
estimate. Per CLAUDE.md trust defaults: **a de-vig is a model, not a fill** — its output
must always be persisted with `price_source_tag="synthetic"`, never treated as a price
anyone could transact at. The only fillable prices in this repo are real asks (see
`core/pricing.py` for the Kalshi-side equivalent, `normalized_ask`).

Pure functions: deterministic, no clock, no network.
"""
from __future__ import annotations

from typing import Iterable, List


def american_to_decimal(odds: float) -> float:
    """American odds (e.g. -150, +130) -> decimal odds (e.g. 1.667, 2.30)."""
    odds = float(odds)
    if odds == 0:
        raise ValueError("american odds cannot be 0")
    return 1.0 + (odds / 100.0 if odds > 0 else 100.0 / -odds)


def decimal_to_implied_prob(decimal_odds: float) -> float:
    """Decimal odds -> the book's raw (vig-inclusive) implied probability."""
    decimal_odds = float(decimal_odds)
    if decimal_odds <= 1.0:
        raise ValueError(f"decimal odds must be > 1.0, got {decimal_odds!r}")
    return 1.0 / decimal_odds


def american_to_implied_prob(odds: float) -> float:
    """American odds -> raw (vig-inclusive) implied probability. Convenience composition."""
    return decimal_to_implied_prob(american_to_decimal(odds))


def devig_multiplicative(implied_probs: Iterable[float]) -> List[float]:
    """Multiplicative (proportional) de-vig: scale raw implied probs so they sum to 1.

    The standard, simplest de-vig — divide each outcome's raw implied probability by the
    sum across the mutually-exclusive set. (Shin's method is a documented, more careful
    refinement for favorite-longshot bias; not implemented here — do not silently swap
    one in without updating every caller's expectations.) Output is always `synthetic`:
    a model of the book's fair line, never a fillable price.
    """
    probs = [float(p) for p in implied_probs]
    if not probs:
        raise ValueError("implied_probs must be non-empty")
    if any(p <= 0 for p in probs):
        raise ValueError(f"implied probs must be > 0, got {probs!r}")
    total = sum(probs)
    return [p / total for p in probs]


def overround(implied_probs: Iterable[float]) -> float:
    """The book's overround: sum(raw implied probs) - 1.0 (the vig, in probability terms)."""
    probs = [float(p) for p in implied_probs]
    if not probs:
        raise ValueError("implied_probs must be non-empty")
    return sum(probs) - 1.0
