"""Offline unit tests for q35_maker_rebate_reframe's fee-swap arithmetic.

Per the Q35 Milestone A spec: test the NEW helper this milestone adds (the fee-swap), not the
whole pipeline — the per-strategy simulate/aggregate functions are already tested by each
source script's own suite (test_s13_maker_fillsim, test_s19_wing_fade_fillsim, ...), and the
end-to-end reproduction of the committed finding numbers is the correctness check the script's
`as_is` column already provides. These tests pin the one piece of new logic: `rebate_swap`
(fee removed + rebate added) and the `_group` scenario builder, both pure and offline.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.pricing import MAKER_FEE_RATE, fee_per_contract
from scripts.q35_maker_rebate_reframe import (
    POLYMARKET_REBATE_CONSERVATIVE,
    POLYMARKET_REBATE_US,
    _group,
    filter_two_sided_fills,
    rebate_swap,
)


def test_rebate_swap_adds_fee_back_and_rebate():
    # as-is P&L had a $0.01 fee subtracted; on a rebate venue add the fee back + rebate income.
    assert rebate_swap(0.0, 0.01, 0.005) == 0.015
    assert rebate_swap(0.0, 0.01, 0.0125) == 0.0225


def test_rebate_swap_zero_rebate_recovers_gross():
    # rebate=0 is the pure fee-removal case: it must recover the gross (pre-fee) P&L exactly.
    as_is = -0.0037
    fee = 0.01
    assert abs(rebate_swap(as_is, fee, 0.0) - (as_is + fee)) < 1e-12


def test_rebate_swap_swing_is_fee_plus_rebate():
    # the whole point of Q35: the fee-line swing per contract is exactly kalshi_fee + rebate.
    for as_is in (-0.5, -0.01, 0.0, 0.19, 0.66):
        for fee in (0.0, 0.01):
            for reb in (POLYMARKET_REBATE_CONSERVATIVE, POLYMARKET_REBATE_US):
                assert abs((rebate_swap(as_is, fee, reb) - as_is) - (fee + reb)) < 1e-12


def test_rebate_swap_reproduces_s13_construction():
    # S13: bid = fair - 1c, so gross edge = fair - bid = 0.01; fee 0.01 -> as-is edge = 0.00.
    fair, bid = 0.42, 0.41
    fee = fee_per_contract(bid, rate=MAKER_FEE_RATE)   # flat $0.01 interior (L30)
    as_is = fair - bid - fee
    assert abs(as_is) < 1e-9
    assert abs(rebate_swap(as_is, fee, POLYMARKET_REBATE_CONSERVATIVE) - 0.015) < 1e-9
    assert abs(rebate_swap(as_is, fee, POLYMARKET_REBATE_US) - 0.0225) < 1e-9


def test_rebate_swap_uses_actual_fee_per_contract_value():
    # recomputing the fee from the price (not hand-rolling 0.01) must give the same swap.
    price = 0.73
    fee = fee_per_contract(price, rate=MAKER_FEE_RATE)
    as_is = 1.0 - price - fee   # a favorite-wins leg, say
    swapped = rebate_swap(as_is, fee, POLYMARKET_REBATE_US)
    assert abs(swapped - (1.0 - price + POLYMARKET_REBATE_US)) < 1e-12


def test_group_as_is_vs_rebate_shift_is_constant_per_obs():
    # _group(None) is the as-is series; _group(rebate) shifts every obs by exactly fee+rebate.
    units = [("gameA", 0.19, 0.01), ("gameA", 0.66, 0.01), ("gameB", -0.34, 0.01)]
    as_is = _group(units, None)
    reb = _group(units, POLYMARKET_REBATE_US)
    assert set(as_is) == set(reb) == {"gameA", "gameB"}
    for key in as_is:
        for a, r in zip(as_is[key], reb[key]):
            assert abs((r - a) - (0.01 + POLYMARKET_REBATE_US)) < 1e-12


def test_group_preserves_block_membership():
    # grouping must key by the block unit (game/event-hour), never collapse the units.
    units = [("g1", 0.1, 0.01), ("g1", 0.2, 0.01), ("g2", 0.3, 0.01)]
    grouped = _group(units, None)
    assert grouped["g1"] == [0.1, 0.2]
    assert grouped["g2"] == [0.3]


# --------------------------------------------------------------------------- #
# S29 two-sided-book population fix (two-agent-rule catch, 2026-07-16): collect_s29 must
# use the fillable two-sided-book cut, NOT build_draw_trades()'s raw earliest-entry output
# (an entry-timing artifact the S29 finding itself disowns as its DEAD-verdict basis).
# --------------------------------------------------------------------------- #
def _trade(spread, filled=True, pnl=0.1):
    return {"filled": filled, "pnl": pnl, "entry_yes_spread": spread}


def test_filter_two_sided_fills_keeps_within_band():
    trades = [_trade(0.05), _trade(0.10), _trade(0.10 + 1e-9)]
    kept = filter_two_sided_fills(trades, spread_max=0.10)
    assert len(kept) == 3


def test_filter_two_sided_fills_drops_wide_one_sided_spread():
    trades = [_trade(0.05), _trade(0.11), _trade(0.86)]
    kept = filter_two_sided_fills(trades, spread_max=0.10)
    assert kept == [trades[0]]


def test_filter_two_sided_fills_drops_unfilled_and_unpriced():
    trades = [
        _trade(0.05, filled=False),
        _trade(0.05, pnl=None),
        {"filled": True, "pnl": 0.2, "entry_yes_spread": None},
        _trade(0.05),
    ]
    kept = filter_two_sided_fills(trades, spread_max=0.10)
    assert kept == [trades[-1]]
