"""Sportsbook odds arithmetic — American odds -> de-vigged fair probability.

A de-vig is a MODEL, not a fill (CLAUDE.md: "a de-vig is a model, not a fill" — Q1).
Every probability produced here is persisted with `price_source_tag="synthetic"` by the
caller; nothing in this file is a fillable price.

The de-vig method is the same overround-removal arithmetic as core.pricing's Kalshi
bracket normalization (divide each implied probability by the sum across the mutually
exclusive outcome set) — reusing core.pricing.bracket_sum/normalized_ask here keeps that
"divide by the group sum to remove the overround" logic defined in exactly one place,
even though core.pricing's own Hard-Rule #3 gate is scoped to Kalshi yes_ask and no_ask.

Pure functions: deterministic, no clock, no network.
"""
from __future__ import annotations

from typing import Iterable, List

from core.pricing import bracket_sum, normalized_ask


def american_to_decimal(odds: float) -> float:
    """American odds -> decimal odds. +150 -> 2.5; -150 -> 1.6667."""
    odds = float(odds)
    if odds == 0:
        raise ValueError("American odds cannot be 0")
    return 1.0 + (odds / 100.0 if odds > 0 else 100.0 / -odds)


def decimal_to_implied_prob(decimal_odds: float) -> float:
    """Decimal odds -> raw (vig-inclusive) implied probability: 1 / decimal_odds."""
    if decimal_odds <= 0:
        raise ValueError(f"decimal_odds must be > 0, got {decimal_odds!r}")
    return 1.0 / decimal_odds


def devig_multiplicative(implied_probs: Iterable[float]) -> List[float]:
    """Multiplicative de-vig: normalize a mutually-exclusive outcome set's raw implied
    probabilities so they sum to 1.0 (removes the sportsbook's overround). Same operation
    as core.pricing.normalized_ask, applied to odds-implied probabilities instead of
    Kalshi asks."""
    probs = [float(p) for p in implied_probs]
    total = bracket_sum(probs)
    return [normalized_ask(p, total) for p in probs]


def american_odds_to_fair_probs(american_odds: Iterable[float]) -> List[float]:
    """End-to-end: American odds for a mutually-exclusive outcome set -> de-vigged fair
    probabilities (sum to 1.0). The composition Q1's odds leg calls."""
    implied = [decimal_to_implied_prob(american_to_decimal(o)) for o in american_odds]
    return devig_multiplicative(implied)
