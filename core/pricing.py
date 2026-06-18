"""Kalshi price arithmetic — THE sanctioned site for yes_ask/no_ask math (Hard Rule #3).

Hard Rule #3: a raw `yes_ask` is NOT a probability. Kalshi temperature ladders carry a
bracket overround (the bracket asks sum to > $1.00 — the ~3-5c structural cost that killed
pt1 at real asks). The implied probability of an outcome is its ask divided by the sum of
all bracket asks, never the ask alone.

The invariant engine (scripts/invariants.py, inv_no_yes_ask_arithmetic) BLOCKS `yes_ask` /
`no_ask` arithmetic everywhere except this file. If you need to turn an ask into a
probability, call `normalized_ask` / `yes_implied_prob` here — do not divide by hand
elsewhere. That is what makes the overround impossible to silently ignore.

Pure functions: deterministic, no clock, no network.
"""
from __future__ import annotations

from typing import Iterable


def bracket_sum(asks: Iterable[float]) -> float:
    """Sum of the per-outcome asks across a mutually-exclusive bracket set.

    For a coherent, frictionless ladder this would be 1.0; the excess over 1.0 is the
    overround the taker pays. Callers persist it as `bracket_sum` so a backtest can
    report `overround_absorbed = bracket_sum - 1.0` per trade (CLAUDE.md trust defaults).
    """
    total = 0.0
    for a in asks:
        total += float(a)
    return total


def normalized_ask(yes_ask: float, bracket_sum: float) -> float:
    """The overround-normalized implied probability of one outcome: yes_ask / bracket_sum.

    This is the ONLY correct way to read a probability off an ask (Hard Rule #3). Dividing
    by the bracket sum (not by 1.0) removes the overround so brackets sum to 1.0.
    """
    if bracket_sum <= 0:
        raise ValueError(f"bracket_sum must be > 0, got {bracket_sum!r}")
    return float(yes_ask) / float(bracket_sum)


def yes_implied_prob(yes_ask: float, bracket_sum: float) -> float:
    """Alias for `normalized_ask` — the implied P(YES) at the real ask. See Hard Rule #3."""
    return normalized_ask(yes_ask, bracket_sum)


def overround(asks: Iterable[float]) -> float:
    """The bracket overround: bracket_sum - 1.0. The structural taker cost (~3-5c on
    KXHIGH) that ate pt1. Persist it per trade as `overround_absorbed`."""
    return bracket_sum(asks) - 1.0
