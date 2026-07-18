"""The sanctioned rule-homes: pricing (Rule #3), source_tag (trust default + Rule #4),
stats (Rule #2). Plus the dossier's #1 binding assertion: the real taker ask is the
complement of the opposite best bid, and it is stamped real_ask."""
from __future__ import annotations

import pytest

from collection.normalize import normalize_snapshot
from core.pricing import (bracket_sum, fee_per_contract, infer_strike_spacing,
                          ladder_spacing, member_coord, monotonicity_crossing_edge,
                          normalized_ask, overround, true_arb_edge, yes_implied_prob)
from core.source_tag import (DEFAULT_TAG, FILLABLE_TAGS, VALID_SOURCE_TAGS,
                             is_fillable, require_fillable, tag_or_synthetic)
from core.stats import MIN_MEMBERS, safe_pstdev


# ─── pricing (Hard Rule #3): a raw ask is not a probability ────────────────────

def test_normalized_ask_divides_by_bracket_sum():
    # Three KXHIGH brackets whose asks sum to 1.05 (a 5c overround, the pt1 killer).
    asks = [0.40, 0.35, 0.30]
    bs = bracket_sum(asks)
    assert bs == pytest.approx(1.05)
    assert overround(asks) == pytest.approx(0.05)
    # normalizing removes the overround: the implied probs sum back to 1.0
    probs = [normalized_ask(a, bs) for a in asks]
    assert sum(probs) == pytest.approx(1.0)
    # the raw ask OVERstates probability (this is exactly the trap Rule #3 forbids)
    assert asks[0] > normalized_ask(asks[0], bs)


def test_yes_implied_prob_is_normalized_ask():
    assert yes_implied_prob(0.40, 1.05) == normalized_ask(0.40, 1.05)


def test_bracket_sum_zero_rejected():
    with pytest.raises(ValueError):
        normalized_ask(0.4, 0.0)


# ─── Q6 anomaly-sweep helpers: fee floor + real-fillable arb edges (Hard Rule #3) ──

def test_fee_per_contract_matches_kalshi_roundup_to_cent():
    # rate*p*(1-p) = 0.07*0.5*0.5 = 0.0175 -> rounds UP to 2 cents, not down to 1
    assert fee_per_contract(0.50) == pytest.approx(0.02)
    # a near-zero price still rounds up to a whole cent, never to $0.00
    assert fee_per_contract(0.01) == pytest.approx(0.01)


def test_true_arb_edge_positive_when_ladder_underpriced():
    asks = [0.05, 0.30, 0.30, 0.05]  # sums to 0.70, a badly underpriced complete ladder
    bs = bracket_sum(asks)
    fees = sum(fee_per_contract(a) for a in asks)
    edge = true_arb_edge(bs, fees)
    assert edge == pytest.approx(1.0 - (bs + fees))
    assert edge > 0


def test_true_arb_edge_negative_under_ordinary_overround():
    asks = [0.30, 0.30, 0.30, 0.20]  # sums to 1.10, an ordinary bracket overround
    bs = bracket_sum(asks)
    fees = sum(fee_per_contract(a) for a in asks)
    assert true_arb_edge(bs, fees) < 0


def test_monotonicity_crossing_edge_positive_on_a_real_cross():
    # outer cheap (0.40) + inner's no_ask cheap (0.45, i.e. inner overpriced) -> real arb
    edge = monotonicity_crossing_edge(0.40, 0.45)
    assert edge > 0
    fees = fee_per_contract(0.40) + fee_per_contract(0.45)
    assert edge == pytest.approx(1.0 - (0.40 + 0.45) - fees)


def test_monotonicity_crossing_edge_negative_when_ordinarily_priced():
    assert monotonicity_crossing_edge(0.60, 0.71) < 0


# ─── infer_strike_spacing (lesson L7): derive width from the ladder, never hardcode ──

def test_infer_strike_spacing_btc_like_ladder():
    strikes = [100000.0, 100100.0, 100200.0, 100300.0]  # $100-spaced, like BTC
    assert infer_strike_spacing(strikes) == pytest.approx(100.0)


def test_infer_strike_spacing_eth_like_ladder():
    strikes = [3000.0, 3020.0, 3040.0, 3060.0]  # $20-spaced, like ETH
    assert infer_strike_spacing(strikes) == pytest.approx(20.0)


def test_infer_strike_spacing_uses_median_robust_to_one_missing_member():
    # a clean $50 ladder with one gap doubled (a missing intermediate strike) — the median
    # gap still reads $50, not skewed by the single $100 outlier gap
    strikes = [100.0, 150.0, 200.0, 300.0, 350.0, 400.0]
    assert infer_strike_spacing(strikes) == pytest.approx(50.0)


def test_infer_strike_spacing_ignores_order_and_duplicates():
    strikes = [300.0, 100.0, 200.0, 200.0, 100.0]
    assert infer_strike_spacing(strikes) == pytest.approx(100.0)


def test_infer_strike_spacing_none_below_two_distinct_strikes():
    assert infer_strike_spacing([]) is None
    assert infer_strike_spacing([100.0]) is None
    assert infer_strike_spacing([100.0, 100.0]) is None


# ─── member_coord / ladder_spacing (lesson L7/L102): shared bracket-ladder geometry,
# was independently duplicated byte-for-byte in s19 and s20 before this extraction ────

def test_member_coord_between_is_midpoint():
    o = {"strike_type": "between", "floor_strike": 63700, "cap_strike": 63799.99}
    assert member_coord(o) == pytest.approx((63700 + 63799.99) / 2.0)


def test_member_coord_edge_uses_available_boundary():
    assert member_coord({"strike_type": "greater", "floor_strike": 73000,
                         "cap_strike": None}) == pytest.approx(73000.0)
    assert member_coord({"strike_type": "less", "floor_strike": None,
                         "cap_strike": 50000}) == pytest.approx(50000.0)


def test_member_coord_none_when_no_strike():
    assert member_coord({"strike_type": "between", "floor_strike": None,
                         "cap_strike": None}) is None


def test_ladder_spacing_from_between_floors():
    outs = [{"strike_type": "between", "floor_strike": 100 + 100 * i} for i in range(4)]
    assert ladder_spacing(outs) == pytest.approx(100.0)


def test_ladder_spacing_none_below_two_strikes():
    assert ladder_spacing([{"strike_type": "between", "floor_strike": 100}]) is None


def test_ladder_spacing_ignores_non_between_members():
    outs = [{"strike_type": "between", "floor_strike": 100},
            {"strike_type": "between", "floor_strike": 200},
            {"strike_type": "greater", "floor_strike": 9999}]
    assert ladder_spacing(outs) == pytest.approx(100.0)


# ─── source_tag (trust=FALSE default + Rule #4) ────────────────────────────────

def test_untagged_number_defaults_to_synthetic():
    assert tag_or_synthetic(None) == "synthetic"
    assert tag_or_synthetic("") == "synthetic"
    assert tag_or_synthetic("not_a_real_tag") == "synthetic"
    assert DEFAULT_TAG == "synthetic"


def test_valid_tags_pass_through():
    for t in VALID_SOURCE_TAGS:
        assert tag_or_synthetic(t) == t


def test_only_real_ask_and_broker_truth_are_fillable():
    assert is_fillable("real_ask") and is_fillable("broker_truth")
    assert not is_fillable("midpoint")
    assert not is_fillable("synthetic")
    assert not is_fillable(None)
    assert FILLABLE_TAGS == frozenset({"real_ask", "broker_truth"})


def test_require_fillable_blocks_synthetic_and_midpoint():
    assert require_fillable("real_ask") == "real_ask"
    for bad in ("synthetic", "midpoint", None):
        with pytest.raises(ValueError):
            require_fillable(bad, context="fill decision")


# ─── stats (Hard Rule #2): no pstdev under 4 members ───────────────────────────

def test_safe_pstdev_requires_min_members():
    assert MIN_MEMBERS == 4
    with pytest.raises(ValueError):
        safe_pstdev([1.0, 2.0, 3.0])           # 3 < 4 -> refused


def test_safe_pstdev_computes_for_enough_members():
    import statistics
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert safe_pstdev(vals) == pytest.approx(statistics.pstdev(vals))  # inv-pattern-def


# ─── #1 binding assertion: real ask = complement of opposite best bid ──────────

@pytest.mark.parametrize("yes_bid,no_bid", [
    (0.30, 0.68), (0.05, 0.94), (0.49, 0.49), (0.01, 0.98),
])
def test_real_ask_is_complement_of_opposite_best_bid(yes_bid, no_bid):
    ob = {"yes_dollars": [[str(yes_bid), "100"]], "no_dollars": [[str(no_bid), "100"]]}
    s = normalize_snapshot("KXHIGHAUS-26JUN06-B84.5", ob)
    # the dossier's #1 binding test, asserted exactly:
    assert s["best_yes_ask"] == round(1 - no_bid, 4)
    assert s["best_no_ask"] == round(1 - yes_bid, 4)


def test_derived_ask_is_tagged_real_ask():
    """A derived taker ask off a live book is a real, fillable price -> real_ask, and a
    fill decision may consume it (prime directive #1)."""
    ob = {"yes_dollars": [["0.30", "100"]], "no_dollars": [["0.68", "100"]]}
    s = normalize_snapshot("KXHIGHAUS-26JUN06-B84.5", ob)
    tag = "real_ask"   # capture stamps every derived ask real_ask
    assert is_fillable(tag)
    assert require_fillable(tag) == "real_ask"
    assert s["best_yes_ask"] is not None
