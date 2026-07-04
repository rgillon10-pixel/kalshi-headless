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

import math
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


def fee_per_contract(price: float, rate: float = 0.07) -> float:
    """Kalshi taker fee per contract, dollars, round-up-to-cent on the whole order
    (docs.kalshi.com/getting_started/fee_rounding): fee = roundup_cent(rate * P * (1-P)).
    Mirrors scripts/fee_breakeven.py's formula; lives here too because Q6's anomaly sweep
    (LOOP-QUEUE.md) needs it alongside bracket_sum to gate a mispricing on REAL fillable
    edge, not just a raw ask/bid gap."""
    return math.ceil(rate * float(price) * (1.0 - float(price)) * 100.0) / 100.0


def true_arb_edge(bracket_sum_value: float, total_fees: float) -> float:
    """Dollar edge of buying every YES in a COMPLETE, mutually-exclusive bracket ladder:
    guaranteed $1 payout costs `bracket_sum_value + total_fees`. Positive means a true arb
    (Q6's "bracket sums vs $1 + fees") — the ladder is underpriced net of fees, not just
    the raw bracket_sum dipping below 1.0."""
    return 1.0 - (bracket_sum_value + total_fees)


def monotonicity_crossing_edge(outer_ask: float, inner_no_ask: float,
                               rate: float = 0.07) -> float:
    """Dollar edge of the cross-strike hedge for two NESTED threshold markets (Q6 /
    S3): `inner`'s YES-region is a subset of `outer`'s (e.g. temp>=80 subset of
    temp>=70). Buying YES(outer) + NO(inner) — both REAL taker asks, never a
    bid-derived synthetic price — pays a guaranteed >=$1 regardless of outcome, so it is
    a genuine arb whenever its total cost clears below $1 net of both legs' fees. A
    monotonicity violation alone (inner priced above outer) is necessary but not
    sufficient; this is the fillable-arb bar CLAUDE.md's prime directive demands."""
    fees = fee_per_contract(outer_ask, rate) + fee_per_contract(inner_no_ask, rate)
    return 1.0 - (outer_ask + inner_no_ask) - fees
