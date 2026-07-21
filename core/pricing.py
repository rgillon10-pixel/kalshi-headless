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
import warnings
from typing import Iterable, Optional


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


def infer_strike_spacing(strikes: Iterable[float]) -> Optional[float]:
    """Derive a bracket ladder's own strike spacing from its strikes — never hardcode a
    per-symbol width (lesson L7: a fixed $100 half-band check silently mis-scored every ETH
    hour, whose real ladder steps $10/$20, not BTC's $100; the fix that shipped only swapped
    in a per-symbol dict, still a hardcoded guess rather than a value read off the ladder
    itself). Dedupes and sorts the given strikes, then returns the MEDIAN consecutive gap —
    median rather than mean/min so one missing or doubled member (a thin/stale far strike,
    a duplicate capture) doesn't skew the estimate. Returns None if fewer than 2 distinct
    strikes are given (spacing is undefined on a singleton or empty ladder)."""
    uniq = sorted(set(float(s) for s in strikes))
    if len(uniq) < 2:
        return None
    gaps = sorted(b - a for a, b in zip(uniq, uniq[1:]))
    mid = len(gaps) // 2
    if len(gaps) % 2 == 1:
        return gaps[mid]
    return (gaps[mid - 1] + gaps[mid]) / 2.0


def member_coord(o: dict) -> Optional[float]:
    """A single strike coordinate for distance-from-spot binning: the midpoint of a
    `between` band, else whichever boundary strike exists for an edge `less`/`greater`
    member. None if neither strike is present. (lesson L7/L102 — was independently
    duplicated byte-for-byte in `scripts/s19_wing_fade_fillsim.py` and
    `scripts/s20_ladder_overround_anatomy.py`; shared here so a third bracket-ladder probe
    doesn't re-derive it.)"""
    st = o.get("strike_type")
    fs = o.get("floor_strike")
    cs = o.get("cap_strike")
    if st == "between" and fs is not None and cs is not None:
        return (float(fs) + float(cs)) / 2.0
    if fs is not None:
        return float(fs)
    if cs is not None:
        return float(cs)
    return None


def ladder_spacing(outcomes: Iterable[dict]) -> Optional[float]:
    """Strike spacing read off the ladder's own `between` floor strikes via
    `infer_strike_spacing` (lesson L7/L102 — never a hardcoded per-symbol width). Median
    consecutive gap, robust to one missing/duplicated member."""
    return infer_strike_spacing(
        [o["floor_strike"] for o in outcomes
         if o.get("strike_type") == "between" and o.get("floor_strike") is not None])


# ─── Kalshi fee-schedule rates — THE single source of truth (Hard Rule / lesson L5) ──
# From the published Kalshi fee schedule (https://kalshi.com/docs/kalshi-fee-schedule.pdf,
# docs.kalshi.com/getting_started/fee_rounding; distilled in kb/kalshi-api/03-fees-and-
# breakeven.md). A first S13 draft charged maker fills the taker rate — a 4x overcharge that
# alone ate a 1c edge (finding 2026-07-04-sports-maker-s13-verdict). These constants exist so
# no module hand-rolls a fee coefficient; scripts/invariants.py::no_handrolled_fee_rate
# statically forbids the banned literals anywhere but this file.
TAKER_FEE_RATE = 0.07       # standard taker fills — the conservative default fee rate
MAKER_FEE_RATE = 0.0175     # maker fills (resting order that gets lifted): a quarter of taker
SP500_NDX_FEE_RATE = 0.035  # S&P 500 / Nasdaq-100 products


def fee_per_contract(price: float, rate: float = TAKER_FEE_RATE) -> float:
    """Kalshi taker fee per contract, dollars, round-up-to-cent on the whole order
    (docs.kalshi.com/getting_started/fee_rounding): fee = roundup_cent(rate * P * (1-P)).
    The default is the conservative TAKER rate; pass MAKER_FEE_RATE for resting-order fills.
    Mirrors scripts/fee_breakeven.py's formula; lives here too because Q6's anomaly sweep
    (LOOP-QUEUE.md) needs it alongside bracket_sum to gate a mispricing on REAL fillable
    edge, not just a raw ask/bid gap."""
    return math.ceil(rate * float(price) * (1.0 - float(price)) * 100.0) / 100.0


# ─── Polymarket fee-schedule rate — the cross-venue leg (Q31 / regime change 2026-07-15) ──
# Polymarket "Fee Structure V2" (eff. ~2026-03-30) is TAKER-only (makers get a rebate) with the
# SAME functional shape as Kalshi's: fee = C · rate · p · (1−p) per contract. Rates by venue/
# category (researched 2026-07-15, cited in LOOP-QUEUE.md "Regime change" note): Polymarket US
# (QCX/QCEX, the CFTC-regulated venue Ryan can actually fill on) ≈ 0.05 taker, cap ~$1.25/100
# contracts @ 50¢; international CLOB: crypto 0.07, sports 0.03–0.05, geopolitics/econ fee-free.
# Sources: Polymarket help "Trading Fees" (help.polymarket.com/en/articles/13364478); Sacra &
# Galaxy fee breakdowns (V2 eff. 2026-03-30; US venue eff. 2026-04-03). We default the cross-venue
# probe to the US taker rate — the venue Ryan realizes — but our captured book is the INTERNATIONAL
# CLOB, so this is a modeled fee on an international price, never a claimed Polymarket-US fill.
POLYMARKET_US_TAKER_RATE = 0.05   # Polymarket US (QCX/QCEX) taker — Ryan's realizable venue

# Polymarket INTERNATIONAL sports taker rate (Q32 — sharp-devig vs Polymarket sports price).
# The regime-change note gives the international sports category as a RANGE, 0.03–0.05 (crypto is
# 0.07, geopolitics/econ fee-free). We default the Q32 probe to the CONSERVATIVE end of that
# range — the HIGHER 0.05 — because the fee is a COST the edge must clear: an edge that survives a
# 0.05 taker fee survives at any lower rate, so 0.05 is the harder, safer bar to set the verdict
# against (never flatter the edge by picking the cheap end of an uncertain schedule). It also
# coincides with the Polymarket-US taker figure, so it is the single most-likely realized rate.
# POLYMARKET_SPORTS_TAKER_RATE_OPTIMISTIC (0.03, the low end) exists ONLY as a sensitivity floor —
# the most-generous rate the schedule allows — mirroring q35_maker_rebate_reframe's two-scenario
# pattern, but kept HERE (not script-local) because core/pricing.py is the one sanctioned
# fee-coefficient site. Neither literal is a banned schedule rate (0.07/0.0175/0.035), so a probe
# that imports these names never hand-rolls a rate. Same p·(1−p) shape / no-round posture as
# `polymarket_fee_per_contract` (Fee Structure V2) — pass either rate into that function.
POLYMARKET_SPORTS_TAKER_RATE = 0.05             # conservative (harder bar): high end of 0.03–0.05
POLYMARKET_SPORTS_TAKER_RATE_OPTIMISTIC = 0.03  # sensitivity floor: most-generous end of the range


def polymarket_fee_per_contract(price: float, rate: float = POLYMARKET_US_TAKER_RATE) -> float:
    """Polymarket taker fee per contract, in dollars: fee = rate · P · (1−P) (Fee Structure V2,
    the same p·(1−p) shape as Kalshi's `fee_per_contract` — see the constant block above for the
    schedule/citations). UNLIKE Kalshi's fee there is NO round-up-to-cent step: Polymarket settles
    in USDC to 6 decimals, not whole cents, and its published cap (~$1.25/100 contracts at 50¢)
    matches the un-rounded formula exactly (0.05·0.5·0.5 = 0.0125/contract). Pass rate=0.0 to model
    the international geopolitics/econ fee-free category (the most-generous sensitivity)."""
    p = float(price)
    return float(rate) * p * (1.0 - p)


# ─── Resting-book notional at touch (lesson L119 — the units-bug guardrail) ──────────────
# A "book notional at touch" descriptor is the dollar depth resting at the best quote:
# price × size. The trap L119 caught: Kalshi's price fields arrive as `_dollars`-suffixed
# STRINGS and must be read via core.kalshi_fields.parse_kalshi_numeric (L90), which returns
# an ALREADY-dollars float ('0.98' -> 0.98). A `price * size / 100` formula — the reflex for
# a cents price — therefore understates real book depth ~100x. During the 2026-07-20 Q36
# weather_books audit a draft metric read medians of $2.3-$19.7/market-hour when the true
# medians were $215-$1,968 (findings/2026-07-20-q36-weather-books-data-adequacy.md). This is
# THE shared helper that lesson said did not yet exist, so the next script that computes the
# metric imports it instead of re-deriving the /100 mistake.

# A genuinely liquid hourly-market touch rarely notionals below this; a result under it is the
# fingerprint of a units (cents-vs-dollars) bug — but a legitimately thin market CAN sit here,
# so the sanity check WARNS (non-gating advisory, the repo's default for anything short of a
# hard data-integrity violation — cf. scripts/invariants.py's advisories, L100/L109/L110), it
# does not raise. The returned notional is never altered by the check.
LOW_TOUCH_NOTIONAL_WARN_DOLLARS = 50.0


def book_notional_at_touch(price_dollars: float, size: float,
                           *, warn_if_implausibly_low: bool = True) -> float:
    """Dollar notional resting at the touch: `price_dollars * size` — NEVER `/100`.

    `price_dollars` is already in dollars once parsed via `core.kalshi_fields.parse_kalshi_numeric`
    (L90's `_dollars` convention). Dividing by 100 silently understates book depth ~100x
    (lesson L119). Emits a non-gating `UserWarning` when the result is implausibly low for a
    liquid market (0 < notional < LOW_TOUCH_NOTIONAL_WARN_DOLLARS) — a cheap units sanity
    check, not a gate; the notional is returned regardless. Pass `warn_if_implausibly_low=False`
    to silence it for a market known to be genuinely thin. A zero notional (empty/zero-size
    touch) is honest, not suspicious, so it never warns."""
    notional = float(price_dollars) * float(size)
    if warn_if_implausibly_low and 0.0 < notional < LOW_TOUCH_NOTIONAL_WARN_DOLLARS:
        warnings.warn(
            f"book_notional_at_touch={notional:.4f} is below ${LOW_TOUCH_NOTIONAL_WARN_DOLLARS:.0f} "
            f"for a supposedly liquid touch (price_dollars={price_dollars!r}, size={size!r}); "
            f"a units bug (cents-vs-dollars, e.g. a stray /100 on an already-dollars price) "
            f"produces exactly this fingerprint — lesson L119. Non-gating advisory.",
            UserWarning,
            stacklevel=2,
        )
    return notional


def true_arb_edge(bracket_sum_value: float, total_fees: float) -> float:
    """Dollar edge of buying every YES in a COMPLETE, mutually-exclusive bracket ladder:
    guaranteed $1 payout costs `bracket_sum_value + total_fees`. Positive means a true arb
    (Q6's "bracket sums vs $1 + fees") — the ladder is underpriced net of fees, not just
    the raw bracket_sum dipping below 1.0."""
    return 1.0 - (bracket_sum_value + total_fees)


def monotonicity_crossing_edge(outer_ask: float, inner_no_ask: float,
                               rate: float = TAKER_FEE_RATE) -> float:
    """Dollar edge of the cross-strike hedge for two NESTED threshold markets (Q6 /
    S3): `inner`'s YES-region is a subset of `outer`'s (e.g. temp>=80 subset of
    temp>=70). Buying YES(outer) + NO(inner) — both REAL taker asks, never a
    bid-derived synthetic price — pays a guaranteed >=$1 regardless of outcome, so it is
    a genuine arb whenever its total cost clears below $1 net of both legs' fees. A
    monotonicity violation alone (inner priced above outer) is necessary but not
    sufficient; this is the fillable-arb bar CLAUDE.md's prime directive demands."""
    fees = fee_per_contract(outer_ask, rate) + fee_per_contract(inner_no_ask, rate)
    return 1.0 - (outer_ask + inner_no_ask) - fees
