#!/usr/bin/env python3
"""Kalshi fee + breakeven math — runnable proof for kb/kalshi-api/03-fees-and-breakeven.md

Source of formula: Kalshi fee schedule (https://kalshi.com/docs/kalshi-fee-schedule.pdf,
docs.kalshi.com/getting_started/fee_rounding). General trading fee per *trade*:

    fee = roundup_to_cent( rate * C * P * (1 - P) )

where C = number of contracts, P = price in DOLLARS (50c -> 0.50).
TAKER fills use TAKER_FEE_RATE (0.07); MAKER fills use MAKER_FEE_RATE (0.0175, where the
maker rebate/lower fee applies); S&P 500 / Nasdaq-100 products use SP500_NDX_FEE_RATE (0.035).
These rates are imported from core.pricing, the single fee-schedule source of truth (lesson L5).

The fee is charged on entry. roundup is to the next whole cent on the *whole order*.

The point of this script: show exactly how big the fee tax is at each price, and how
much the market price must move in your favor just to break even. This is the single
biggest reason a "model edge" can be real while the "dollar edge" is not.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.pricing import (  # noqa: E402
    MAKER_FEE_RATE,
    SP500_NDX_FEE_RATE,
    TAKER_FEE_RATE,
)


def fee_per_contract(price: float, rate: float = TAKER_FEE_RATE, contracts: int = 1) -> float:
    """Round-up-to-cent fee for an order, returned per-contract in dollars."""
    raw = rate * contracts * price * (1.0 - price)
    fee_cents = math.ceil(raw * 100.0)          # round UP to next whole cent (whole order)
    return (fee_cents / 100.0) / contracts


def breakeven_prob(price: float, rate: float = TAKER_FEE_RATE) -> float:
    """True P(YES) needed for a YES buy at `price` to be EV-neutral after entry fee.

    EV per contract = p*(1 - price) - (1-p)*price - fee  (payoff 1 if YES, 0 if NO)
                    = p - price - fee
    EV = 0  ->  p = price + fee
    """
    f = fee_per_contract(price, rate)
    return price + f


def roundtrip_drag(price: float, rate: float = TAKER_FEE_RATE) -> float:
    """Approx fee drag if you pay the fee on entry only (settlement has no fee).
    For a flipped/closed position you'd pay entry fee twice; we report entry-only."""
    return fee_per_contract(price, rate)


if __name__ == "__main__":
    print(f"Kalshi taker fee (rate={TAKER_FEE_RATE}), per single contract, round-up-to-cent:\n")
    print(f"{'price':>6} {'fee/ct':>7} {'fee(bps of $1)':>15} {'breakeven_p':>12} "
          f"{'edge_needed_cents':>18}")
    for p in [0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95]:
        f = fee_per_contract(p, TAKER_FEE_RATE)
        be = breakeven_prob(p, TAKER_FEE_RATE)
        print(f"{p:>6.2f} {f:>7.4f} {f*10000:>15.0f} {be:>12.4f} "
              f"{(be - p)*100:>18.2f}")

    print(f"\nMaker fee (rate={MAKER_FEE_RATE}) vs taker ({TAKER_FEE_RATE}) at p=0.50, per contract:")
    print(f"  taker fee = {fee_per_contract(0.50, TAKER_FEE_RATE):.4f}  "
          f"maker fee = {fee_per_contract(0.50, MAKER_FEE_RATE):.4f}")

    print("\nKey takeaway: at p=0.50 the taker fee is ~2c/contract, so a YES buy at 50c")
    print("only breaks even if true P(YES) >= ~0.52. A model that is 'right' by 1c of")
    print("probability is a guaranteed loser after fees. The bracket overround (3-5c)")
    print("stacks on top of this. THIS is why arb-bot's dollar edge broke at real asks.")
