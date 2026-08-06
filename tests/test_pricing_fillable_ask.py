"""core.pricing.is_fillable_ask / is_material_arb_edge — the L105/L288 guards.

A $0.00 Kalshi ask is the ABSENCE of a resting offer (the venue's minimum quotable price is
1 cent), never a free contract; and a bare `edge > 0` admission test on a cent-grid edge lets
binary-float residue through as profit. These are the two shared predicates every arb scanner
in the repo now routes through, so the tests here pin the boundary behaviour rather than
re-deriving it per scanner (L36/L102 twin discipline).

Mirrors tests/test_pricing_book_notional.py's style: pure functions, no clock, no network.
"""
from __future__ import annotations

import math

import pytest

from core.pricing import (ARB_EDGE_RESIDUE_FLOOR_DOLLARS, MIN_FILLABLE_ASK_DOLLARS,
                          fee_per_contract, is_fillable_ask, is_material_arb_edge,
                          monotonicity_crossing_edge, true_arb_edge)


# ─── is_fillable_ask ────────────────────────────────────────────────────────────────────
def test_the_floor_is_kalshis_one_cent_minimum_tick():
    assert MIN_FILLABLE_ASK_DOLLARS == 0.01


def test_a_zero_ask_is_not_fillable_it_is_the_absence_of_an_offer():
    """THE lesson (L105/L288): the pt1-class error is reading $0.00 as a buyable price."""
    assert is_fillable_ask(0.0) is False
    assert is_fillable_ask(0) is False
    assert is_fillable_ask("0.0000") is False


def test_a_price_below_the_minimum_tick_is_not_fillable():
    assert is_fillable_ask(0.001) is False
    assert is_fillable_ask(0.009) is False
    assert is_fillable_ask(-0.5) is False


def test_the_minimum_tick_itself_is_fillable_despite_binary_float():
    # 0.01 has no exact binary representation; the epsilon exists only to protect this case.
    assert is_fillable_ask(0.01) is True
    assert is_fillable_ask(1e-2) is True
    assert is_fillable_ask(0.01 - 1e-12) is True


def test_ordinary_and_dollar_pinned_asks_are_fillable():
    assert is_fillable_ask(0.03) is True
    assert is_fillable_ask(0.5) is True
    assert is_fillable_ask(1.0) is True


def test_a_kalshi_dollars_string_is_coerced_not_refused():
    """Kalshi's `_dollars` fields arrive as strings (L90); a caller that forgot to parse
    must not be silently told 'unfillable'."""
    assert is_fillable_ask("0.0300") is True
    assert is_fillable_ask("0.0000") is False


def test_missing_and_unparseable_inputs_are_refused_not_crashed():
    assert is_fillable_ask(None) is False
    assert is_fillable_ask("") is False
    assert is_fillable_ask("n/a") is False
    assert is_fillable_ask(float("nan")) is False


def test_it_is_deliberately_not_capped_above_one_dollar():
    """Documented choice: an ask over $1.00 cannot exist on Kalshi and could never produce a
    positive edge (every consumer subtracts it from $1.00), so the predicate does not add a
    second, untested refusal path for it."""
    assert is_fillable_ask(1.5) is True


def test_fillability_is_a_price_grid_test_not_a_size_test():
    """NECESSARY, NOT SUFFICIENT. `/markets` carries no `*_ask_size`; where size IS visible
    (L96/L105) ~96% of nonzero asks still have zero size. A 1-cent ask therefore passes here
    and may still be unfillable in the book — any finding must say which it checked."""
    assert is_fillable_ask(0.01) is True  # price grid only — says nothing about resting size


# ─── is_material_arb_edge ───────────────────────────────────────────────────────────────
def test_the_residue_floor_is_sub_tick():
    assert 0 < ARB_EDGE_RESIDUE_FLOOR_DOLLARS < 0.01


def test_zero_and_negative_edges_are_not_material():
    assert is_material_arb_edge(0.0) is False
    assert is_material_arb_edge(-0.01) is False


def test_the_exact_l288_float_artifact_is_refused_but_the_bare_test_would_admit_it():
    """L288's second defect, pinned against the arithmetic that produces it: 1,480 committed
    anomalies carry this exact value. The bare `> 0` reading is asserted BESIDE the guard so
    the difference stays visible instead of being silently absorbed."""
    artifact = monotonicity_crossing_edge(0.0, 0.99)
    assert artifact == 8.673617379884035e-18
    assert artifact > 0                       # what the old admission test saw
    assert is_material_arb_edge(artifact) is False   # what it actually is: exactly $0.00


def test_the_residue_defect_survives_the_fillability_guard_on_the_cent_grid():
    """The two guards are independent, not redundant: this pair is fully QUOTED (both legs
    >= 1c) and still nets exactly $0.00, showing up as 1.73e-17. Without the residue floor the
    fillability guard alone would still admit it as an arb."""
    outer, inner = 0.01, 0.97
    assert is_fillable_ask(outer) and is_fillable_ask(inner)
    residue = monotonicity_crossing_edge(outer, inner)
    assert 0 < residue < 1e-9
    assert is_material_arb_edge(residue) is False


def test_every_genuine_cent_edge_is_material():
    assert is_material_arb_edge(0.01) is True
    assert is_material_arb_edge(0.06) is True
    assert is_material_arb_edge(1e-8) is True   # above the floor: admitted, never rounded away


def test_a_real_ladder_edge_stays_material_after_the_guard():
    asks = [0.05, 0.30, 0.30, 0.05]
    edge = true_arb_edge(sum(asks), sum(fee_per_contract(a) for a in asks))
    assert edge > 0.01
    assert is_material_arb_edge(edge) is True


def test_unparseable_edges_are_refused_not_crashed():
    assert is_material_arb_edge(float("nan")) is False
    assert is_material_arb_edge(None) is False
    assert is_material_arb_edge("lots") is False


def test_the_floor_is_below_the_smallest_survivor_seen_in_committed_tape():
    """The 13 anomalies that survive both guards over all committed tape have edges >= $0.01;
    the floor sits ~7 orders of magnitude below that, so it can only remove residue."""
    assert ARB_EDGE_RESIDUE_FLOOR_DOLLARS < 0.01 / 1e6
    assert not math.isnan(ARB_EDGE_RESIDUE_FLOOR_DOLLARS)
