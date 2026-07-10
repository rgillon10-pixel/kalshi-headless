"""De-vig math (Q1) — American odds -> decimal -> implied prob -> overround-normalized
fair probability. Pure, offline; no network."""
from __future__ import annotations

import math

import pytest

from core.odds import (american_odds_to_fair_probs, american_to_decimal,
                       decimal_to_implied_prob, devig_multiplicative)


def test_american_to_decimal_favorite_and_underdog():
    assert american_to_decimal(-150) == pytest.approx(1.6667, abs=1e-3)
    assert american_to_decimal(150) == pytest.approx(2.5, abs=1e-9)
    assert american_to_decimal(100) == pytest.approx(2.0, abs=1e-9)
    assert american_to_decimal(-100) == pytest.approx(2.0, abs=1e-9)


def test_american_to_decimal_rejects_zero():
    with pytest.raises(ValueError):
        american_to_decimal(0)


def test_decimal_to_implied_prob():
    assert decimal_to_implied_prob(2.0) == pytest.approx(0.5)
    assert decimal_to_implied_prob(4.0) == pytest.approx(0.25)
    with pytest.raises(ValueError):
        decimal_to_implied_prob(0.0)


def test_devig_multiplicative_removes_overround():
    # two-way, vig-inclusive implied probs summing to 1.05 (a typical -110/-110 line)
    raw = [0.5238, 0.5238]
    fair = devig_multiplicative(raw)
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)
    assert fair[0] == pytest.approx(fair[1])


def test_devig_multiplicative_preserves_relative_shape():
    raw = [0.6, 0.3, 0.15]   # overround 1.05, favorite/dog/dog
    fair = devig_multiplicative(raw)
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)
    assert fair[0] > fair[1] > fair[2]


def test_american_odds_to_fair_probs_end_to_end_two_way():
    # -150 / +130 book line -> de-vigged fair probs sum to 1.0
    fair = american_odds_to_fair_probs([-150, 130])
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)
    assert fair[0] > 0.5 > fair[1]   # favorite (-150) still favored after de-vig


def test_american_odds_to_fair_probs_three_way_soccer():
    # home/away/tie moneyline — mutually exclusive 3-way bracket
    fair = american_odds_to_fair_probs([120, 250, 210])
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)
    assert all(0.0 < p < 1.0 for p in fair)
