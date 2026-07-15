"""core/income_legs.py — income-leg volume decomposition (L39 small-net-of-two-legs lesson)."""
from __future__ import annotations

import pytest

from core.income_legs import income_leg_edge_at_gate, income_leg_thin_fraction


# ─── income_leg_thin_fraction ───────────────────────────────────────────────

def test_income_leg_thin_fraction_reproduces_s14_shape():
    # S14-shaped: total income $0.093, of which $0.072 (78%) sits on legs < 100-contract
    # volume (thin prints) and $0.021 on a heavy-volume leg.
    legs = [(0.072, 47.0), (0.021, 1047.0)]
    frac = income_leg_thin_fraction(legs, volume_threshold=100.0)
    assert frac == pytest.approx(0.072 / 0.093)


def test_income_leg_thin_fraction_all_thin_is_one():
    legs = [(0.05, 1.0), (0.03, 10.0)]
    assert income_leg_thin_fraction(legs, volume_threshold=100.0) == 1.0


def test_income_leg_thin_fraction_all_heavy_is_zero():
    legs = [(0.05, 500.0), (0.03, 10183.0)]
    assert income_leg_thin_fraction(legs, volume_threshold=100.0) == 0.0


def test_income_leg_thin_fraction_boundary_is_not_thin():
    # volume == threshold is NOT strictly below -> counts as heavy (matches
    # income_leg_edge_at_gate's ">=" gate convention, so the two functions partition cleanly).
    legs = [(0.05, 100.0)]
    assert income_leg_thin_fraction(legs, volume_threshold=100.0) == 0.0


def test_income_leg_thin_fraction_empty_legs_is_none_not_a_divide_by_zero():
    assert income_leg_thin_fraction([], volume_threshold=100.0) is None


def test_income_leg_thin_fraction_zero_total_income_is_none():
    legs = [(0.03, 5.0), (-0.03, 500.0)]
    assert income_leg_thin_fraction(legs, volume_threshold=100.0) is None


def test_income_leg_thin_fraction_negative_total_income_is_none():
    legs = [(-0.05, 5.0), (-0.02, 500.0)]
    assert income_leg_thin_fraction(legs, volume_threshold=100.0) is None


# ─── income_leg_edge_at_gate ────────────────────────────────────────────────

def test_income_leg_edge_at_gate_sums_only_legs_at_or_above_threshold():
    legs = [(0.072, 47.0), (0.021, 1047.0), (0.004, 10183.0)]
    assert income_leg_edge_at_gate(legs, volume_threshold=100.0) == pytest.approx(0.025)


def test_income_leg_edge_at_gate_boundary_is_included():
    legs = [(0.05, 100.0)]
    assert income_leg_edge_at_gate(legs, volume_threshold=100.0) == pytest.approx(0.05)


def test_income_leg_edge_at_gate_no_legs_clear_gate_is_zero():
    legs = [(0.05, 1.0), (0.03, 10.0)]
    assert income_leg_edge_at_gate(legs, volume_threshold=100.0) == 0.0


def test_income_leg_edge_at_gate_empty_legs_is_zero():
    assert income_leg_edge_at_gate([], volume_threshold=100.0) == 0.0


# ─── partition consistency ──────────────────────────────────────────────────

def test_thin_fraction_and_gate_edge_partition_total_income():
    legs = [(0.072, 47.0), (0.021, 1047.0)]
    total = sum(income for income, _ in legs)
    thin_income = income_leg_thin_fraction(legs, volume_threshold=100.0) * total
    heavy_income = income_leg_edge_at_gate(legs, volume_threshold=100.0)
    assert thin_income + heavy_income == pytest.approx(total)
