"""core.oddsmath — American/decimal conversion + de-vig math (pure functions)."""
from __future__ import annotations

import pytest

from core import oddsmath as om


@pytest.mark.parametrize("american,decimal", [
    (100, 2.0), (150, 2.5), (-150, 1.0 + 100.0 / 150.0), (-110, 1.0 + 100.0 / 110.0),
])
def test_american_to_decimal(american, decimal):
    assert om.american_to_decimal(american) == pytest.approx(decimal, abs=1e-9)


def test_american_to_decimal_rejects_zero():
    with pytest.raises(ValueError):
        om.american_to_decimal(0)


def test_decimal_to_implied_prob():
    assert om.decimal_to_implied_prob(2.0) == pytest.approx(0.5, abs=1e-9)
    assert om.decimal_to_implied_prob(4.0) == pytest.approx(0.25, abs=1e-9)


def test_decimal_to_implied_prob_rejects_non_positive_edge():
    with pytest.raises(ValueError):
        om.decimal_to_implied_prob(1.0)


def test_american_to_implied_prob_matched_pair_favorite_underdog():
    # -150 favorite / +130 underdog is a typical two-way vigged quote.
    fav = om.american_to_implied_prob(-150)
    dog = om.american_to_implied_prob(130)
    assert fav > 0.5 > dog
    assert fav + dog > 1.0          # the vig: raw implied probs sum above 1


def test_devig_multiplicative_two_way():
    # -150/+130 -> raw implied probs, scaled to sum to exactly 1.
    fav = om.american_to_implied_prob(-150)
    dog = om.american_to_implied_prob(130)
    fair = om.devig_multiplicative([fav, dog])
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)
    assert fair[0] > fair[1]                       # favorite stays favorite
    assert fair[0] < fav                            # de-vig always shrinks the favorite's edge


def test_devig_multiplicative_three_way_preserves_ratios():
    raw = [0.50, 0.30, 0.20]      # already sums to 1 -> de-vig is a no-op
    fair = om.devig_multiplicative(raw)
    for r, f in zip(raw, fair):
        assert f == pytest.approx(r, abs=1e-9)


def test_devig_multiplicative_rejects_empty():
    with pytest.raises(ValueError):
        om.devig_multiplicative([])


def test_devig_multiplicative_rejects_non_positive():
    with pytest.raises(ValueError):
        om.devig_multiplicative([0.5, 0.0])


def test_overround_matches_devig_normalization_factor():
    raw = [0.55, 0.50]   # sums to 1.05 -> 5% overround
    assert om.overround(raw) == pytest.approx(0.05, abs=1e-9)
    fair = om.devig_multiplicative(raw)
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)


def test_overround_rejects_empty():
    with pytest.raises(ValueError):
        om.overround([])
