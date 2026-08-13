"""Tests for the independent Q52/S78 population re-derivation (the no-verifier redundancy leg).

The point of this file is that the re-derivation is INDEPENDENT: its own date arithmetic,
its own timestamp parser, its own fee formula. Those are exactly the places a from-scratch
second implementation goes quietly wrong, so they are pinned against the shared library it
deliberately does not import.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.pricing import MAKER_FEE_RATE, fee_per_contract
from core.timeutil import parse_iso_utc
from scripts import q52_s78_population_rederive as R
from scripts import q52_s78_toxicity_filtered_maker_probe as P


@pytest.mark.parametrize("text", [
    "2026-08-03T00:55:57.567380+00:00",
    "2026-07-07T23:59:56.902633Z",
    "2026-01-01T00:00:00Z",
    "2026-12-31T23:59:59Z",
    "2026-02-28T12:34:56.7Z",
    "2026-07-07T12:00:00-04:00",
])
def test_handrolled_iso_parser_agrees_with_the_shared_one(text):
    assert R._epoch(text) == pytest.approx(parse_iso_utc(text).timestamp(), abs=1e-6)


def test_handrolled_iso_parser_is_absent_not_zero_on_junk():
    assert R._epoch("") is None
    assert R._epoch("not-a-timestamp") is None


@pytest.mark.parametrize("y,m,d", [(2026, 1, 1), (2026, 7, 7), (2026, 12, 31),
                                   (2024, 2, 29), (2000, 3, 1), (1970, 1, 1)])
def test_civil_day_arithmetic_roundtrips(y, m, d):
    epoch = R._days_from_civil(y, m, d) * 86400.0
    assert R._day_of(epoch) == "%04d-%02d-%02d" % (y, m, d)
    assert epoch == datetime(y, m, d, tzinfo=timezone.utc).timestamp()


@pytest.mark.parametrize("price", [0.01, 0.05, 0.2, 0.5, 0.77, 0.95, 0.99])
def test_handrolled_maker_fee_agrees_with_core_pricing(price):
    assert R._fee(price) == pytest.approx(fee_per_contract(price, MAKER_FEE_RATE))


def test_game_key_and_series_test_agree_with_the_probe():
    for tk in ("KXMLBGAME-26JUL07AAABBB-AAA", "KXWCGAME-26JUL07ARGEGY-TIE",
               "KXCPI-26JUL-T0.3"):
        assert R._game(tk) == P.event_ticker_of(tk)
        assert R._is_game(tk) == P.is_game_series(tk)


def test_maker_leg_orientation_agrees_with_the_probe():
    for price in (0.2, 0.5, 0.8):
        for tbs in ("bid", "ask", "", "junk"):
            assert R.maker_leg(price, tbs) == P.maker_leg_of_print(price, tbs)


def test_cell_boundary_epsilon_is_the_documented_float_trap():
    """`0.71 - 0.68` is 0.029999999999999916 in binary floating point. The epsilon-tolerant
    convention (the probe's) calls that a WIDE three-cent spread; an exact `>= 0.03` calls it
    tight. This is the sole source of the first draft's apparent disagreement."""
    spread = 0.71 - 0.68
    assert spread < 0.03
    assert R.cell(0.20, spread) == "cheap/wide"
    assert R.cell(0.20, spread, exact_boundary=True) == "cheap/tight"
    assert R.cell(0.20, spread) == P.cell_key(P.cell_of(0.20, spread))


def test_cell_agrees_with_the_probe_across_a_grid():
    for price in (0.02, 0.1, 0.4999, 0.5, 0.77, 0.98):
        for spread in (0.0, 0.01, 0.02, 0.03, 0.05, 0.71 - 0.68, 0.5 - 0.47):
            assert R.cell(price, spread) == P.cell_key(P.cell_of(price, spread))


# --------------------------------------------------------------------------- #
# REAL-TREE REDUNDANCY RECEIPT
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def both():
    return P.run(population_only=True)["population"], R.run()


def test_two_independent_implementations_agree_on_the_split(both):
    p, r = both
    assert p["split"]["train_days"] == r["train_days"]
    assert p["split"]["holdout_days"] == r["holdout_days"]
    assert p["split"]["n_train_games"] == r["n_train_games"]
    assert p["split"]["n_holdout_games"] == r["n_holdout_games"]
    assert p["split"]["n_straddling_games_dropped"] == r["n_straddling_games_dropped"]


def test_two_independent_implementations_agree_on_the_cell_admissions(both):
    p, r = both
    assert p["admitted_cells"] == r["admitted_cells"]
    for k, cell in p["train_cell_table"].items():
        assert cell["n_train_prints"] == r["train_cell_table"][k]["n"]
        if cell["mean_markout"] is not None:
            assert cell["mean_markout"] == pytest.approx(
                r["train_cell_table"][k]["mean_markout"], rel=1e-9)


def test_two_independent_implementations_agree_on_the_holdout_population(both):
    p, r = both
    assert p["n_candidates_all"] == r["n_candidates_all"]
    assert p["n_candidates_scoreable"] == r["n_candidates_scoreable"]
    assert p["n_fills_scoreable"] == r["n_fills_scoreable"]
    assert p["n_units"] == r["n_units"]
    assert (p["sign_variation"]["minority_side_units_exclusive"]
            == r["exclusive_minority_units"])


def test_the_rederivation_reads_no_settlement_value(both):
    _, r = both
    assert r["network_calls"] == 0
    assert r["price_source_tags"]["rest_price"] == "real_bid"
    assert "pnl" not in r and "ci95" not in r
