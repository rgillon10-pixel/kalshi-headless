"""Offline unit tests for q39_graveyard_counterfactual_sweep.

Per the Q39 spec (mirrors tests/test_q35_maker_rebate_reframe.py): pin the NEW logic this
milestone adds — the general fee-swap (`apply_fee_config`), the by-config grouping, and the
classify verdict — not the whole pipeline. Each source strategy's simulate/aggregate functions
are already covered by its own suite; the end-to-end reproduction of the committed finding
numbers is the correctness check the script's `as_is` column provides at run time. Pure/offline.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.pricing import (
    MAKER_FEE_RATE,
    TAKER_FEE_RATE,
    fee_per_contract,
    polymarket_fee_per_contract,
)
from scripts.q39_graveyard_counterfactual_sweep import (
    AS_IS,
    MAKER_CONFIGS,
    PM_MAKER_REBATE_CONSERVATIVE,
    PM_MAKER_REBATE_US,
    PM_TAKER,
    REBATE_HI,
    REBATE_LO,
    TAKER_CONFIGS,
    ZERO_FEE,
    Unit,
    analyze,
    apply_fee_config,
    group_by_config,
)


# --------------------------------------------------------------------------- #
# apply_fee_config — the general fee-swap
# --------------------------------------------------------------------------- #
def test_as_is_is_identity():
    assert apply_fee_config(-0.0037, [(0.5, 0.01)], AS_IS) == -0.0037
    assert apply_fee_config(0.19, [(0.4, 0.02), (0.6, 0.02)], AS_IS) == 0.19


def test_zero_fee_adds_back_all_original_fees():
    # single leg
    assert abs(apply_fee_config(-0.0037, [(0.5, 0.01)], ZERO_FEE) - (-0.0037 + 0.01)) < 1e-12
    # two legs: both original fees returned
    got = apply_fee_config(-0.05, [(0.4, 0.02), (0.6, 0.02)], ZERO_FEE)
    assert abs(got - (-0.05 + 0.04)) < 1e-12


def test_rebate_adds_fee_back_plus_rebate_per_leg():
    # one maker leg: as_is + fee + rebate (matches q35's rebate_swap exactly)
    assert abs(apply_fee_config(0.0, [(None, 0.01)], REBATE_LO) - 0.015) < 1e-12
    assert abs(apply_fee_config(0.0, [(None, 0.01)], REBATE_HI) - 0.0225) < 1e-12


def test_rebate_scales_with_leg_count():
    # a (hypothetical) two-leg maker earns the rebate on BOTH legs
    got = apply_fee_config(0.0, [(None, 0.01), (None, 0.01)], REBATE_HI)
    assert abs(got - (0.0 + 0.02 + 2 * PM_MAKER_REBATE_US)) < 1e-12


def test_pm_taker_removes_kalshi_fee_and_adds_polymarket_fee_per_leg():
    ea, xb = 0.5, 0.5
    fee_in = fee_per_contract(ea, TAKER_FEE_RATE)   # $0.02 at 50c
    fee_out = fee_per_contract(xb, TAKER_FEE_RATE)
    as_is = 0.03 - fee_in - fee_out                 # some gross minus both taker fees
    got = apply_fee_config(as_is, [(ea, fee_in), (xb, fee_out)], PM_TAKER)
    expected = as_is + fee_in + fee_out - polymarket_fee_per_contract(ea) - polymarket_fee_per_contract(xb)
    assert abs(got - expected) < 1e-12
    # sanity: PM taker (0.05) is cheaper than Kalshi taker (0.07 + round-up) at 50c, so the swap
    # must IMPROVE the P&L.
    assert got > as_is


def test_pm_taker_raises_on_none_price():
    # a maker unit (price None) must never silently take the taker branch
    import pytest
    with pytest.raises(ValueError):
        apply_fee_config(0.0, [(None, 0.01)], PM_TAKER)


def test_unknown_config_raises():
    import pytest
    with pytest.raises(ValueError):
        apply_fee_config(0.0, [(0.5, 0.01)], "not_a_config")


def test_swing_is_exactly_fee_line_delta():
    # the whole point: every config shifts a unit by exactly (Σ original_fee − Σ new_fee).
    legs = [(0.4, fee_per_contract(0.4, TAKER_FEE_RATE)),
            (0.6, fee_per_contract(0.6, TAKER_FEE_RATE))]
    orig = sum(f for _, f in legs)
    for as_is in (-0.5, -0.03, 0.0, 0.12):
        assert abs(apply_fee_config(as_is, legs, ZERO_FEE) - as_is - orig) < 1e-12
        pm_new = sum(polymarket_fee_per_contract(p) for p, _ in legs)
        assert abs(apply_fee_config(as_is, legs, PM_TAKER) - as_is - (orig - pm_new)) < 1e-12


# --------------------------------------------------------------------------- #
# group_by_config — the by-unit block grouping
# --------------------------------------------------------------------------- #
def test_group_preserves_block_membership_and_reprices():
    units = [Unit("gA", 0.19, [(None, 0.01)]),
             Unit("gA", -0.34, [(None, 0.01)]),
             Unit("gB", 0.66, [(None, 0.01)])]
    as_is = group_by_config(units, AS_IS)
    assert as_is == {"gA": [0.19, -0.34], "gB": [0.66]}
    reb = group_by_config(units, REBATE_HI)
    # every value shifted by exactly fee + rebate = 0.01 + 0.0125
    for key in as_is:
        for a, r in zip(as_is[key], reb[key]):
            assert abs((r - a) - (0.01 + PM_MAKER_REBATE_US)) < 1e-12


# --------------------------------------------------------------------------- #
# analyze / classify — verdict logic + flip detection (synthetic collectors, no tape)
# --------------------------------------------------------------------------- #
def _maker_collector(units):
    return lambda: (units, {"block_unit": "unit", "family": "maker"})


def test_classify_flip_detection_regression():
    # 12 units all at exactly break-even on the Kalshi maker fee (as_is straddles 0), so a
    # +1.25c rebate lifts EVERY unit to +$0.0225 -> a degenerate all-positive CI that clears the
    # 1c tick gate: the canonical S13/S29-style FLIP.
    units = [Unit(f"g{i}", 0.0, [(None, 0.01)]) for i in range(12)]
    rep = analyze("flipper", _maker_collector(units), MAKER_CONFIGS, n_boot=500)
    assert rep["verdict_class"] == "flips"
    assert REBATE_HI in rep["flips"]
    assert rep["scenarios"][REBATE_HI]["alive"] is True
    assert rep["scenarios"][AS_IS]["alive"] is False


def test_classify_lost_by_more_than_fee_swing():
    # a $0.20/unit loss cannot be recovered by a +2.25c max swing: strictly negative even at the
    # best config -> NOT fee-revivable.
    units = [Unit(f"g{i}", -0.20, [(None, 0.01)]) for i in range(15)]
    rep = analyze("hopeless", _maker_collector(units), MAKER_CONFIGS, n_boot=500)
    assert rep["verdict_class"] == "lost_by_more"
    assert rep["flips"] == []
    assert rep["best_mean"] < 0


def test_classify_fee_marginal_below_tick_gate():
    # a small loss that the max rebate lifts to a POSITIVE mean with a strictly-positive CI, but
    # whose lower bound sits below the 1c tick gate -> fee-line marginal, NOT a flip. Tiny
    # per-unit spread so the CI is tight and positive but sub-tick.
    # as_is ~ -0.019; +2.25c max rebate lifts it to ~+0.0035 (in (0, 1c)) -> sub-tick positive.
    units = [Unit(f"g{i}", -0.019 + 0.00001 * (i % 3), [(None, 0.01)]) for i in range(20)]
    rep = analyze("marginal", _maker_collector(units), MAKER_CONFIGS, n_boot=800)
    best = rep["scenarios"][REBATE_HI]
    assert best["mean"] > 0                       # rebate lifted the mean positive
    assert best["clears_tick_magnitude"] is False  # but below the 1c tick gate
    assert rep["flips"] == []
    assert rep["verdict_class"] == "fee_marginal"


def test_classify_data_adequacy_dead_below_min_units():
    # < 10 distinct block units -> untestable regardless of the fee line.
    units = [Unit("only_one", 0.0, [(None, 0.01)]) for _ in range(50)]
    rep = analyze("thin", _maker_collector(units), MAKER_CONFIGS, n_boot=300)
    assert rep["verdict_class"] == "data_adequacy"
    assert rep["flips"] == []


def test_taker_zero_fee_cross_check_against_gross():
    # for a taker round-trip, zero_fee must equal the gross (pre-fee) P&L unit-for-unit.
    ea, xb = 0.55, 0.52
    fee_in = fee_per_contract(ea, TAKER_FEE_RATE)
    fee_out = fee_per_contract(xb, TAKER_FEE_RATE)
    rt = xb - ea - fee_in - fee_out
    units = [Unit(f"g{i}", rt, [(ea, fee_in), (xb, fee_out)]) for i in range(11)]
    rep = analyze("taker", lambda: (units, {"block_unit": "game", "family": "taker"}),
                  TAKER_CONFIGS, n_boot=300)
    # zero_fee mean == gross == xb - ea, exactly
    assert abs(rep["scenarios"][ZERO_FEE]["mean"] - (xb - ea)) < 1e-9
