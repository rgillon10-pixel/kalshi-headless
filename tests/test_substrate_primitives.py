"""The sanctioned rule-homes: pricing (Rule #3), source_tag (trust default + Rule #4),
stats (Rule #2). Plus the dossier's #1 binding assertion: the real taker ask is the
complement of the opposite best bid, and it is stamped real_ask."""
from __future__ import annotations

import pytest

from collection.normalize import normalize_snapshot
from core.pricing import bracket_sum, normalized_ask, overround, yes_implied_prob
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
