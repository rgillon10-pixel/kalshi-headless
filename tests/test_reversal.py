"""core/reversal.py — jump direction precheck (L59 momentum/reversal two-number lesson)."""
from __future__ import annotations

from core.reversal import direction_precheck, reverses


# ─── reverses ────────────────────────────────────────────────────────────────

def test_reverses_true_when_opposite_sign():
    assert reverses(0.05, -0.02) is True


def test_reverses_false_when_same_sign():
    assert reverses(0.05, 0.02) is False


def test_reverses_none_when_next_step_missing():
    assert reverses(0.05, None) is None


def test_reverses_none_when_next_step_zero():
    assert reverses(0.05, 0.0) is None


def test_reverses_handles_negative_jump():
    assert reverses(-0.05, 0.02) is True
    assert reverses(-0.05, -0.02) is False


# ─── direction_precheck ──────────────────────────────────────────────────────

def test_direction_precheck_empty_is_not_momentum():
    result = direction_precheck([])
    assert result["n_with_next_step"] == 0
    assert result["reversal_fraction"] is None
    assert result["mean_next_step_after_jump_up"] is None
    assert result["mean_next_step_after_jump_down"] is None
    assert result["is_momentum"] is False


def test_direction_precheck_excludes_pairs_with_no_next_step():
    pairs = [(0.05, None), (0.05, 0.0), (0.05, 0.01)]
    result = direction_precheck(pairs)
    assert result["n_with_next_step"] == 1


def test_direction_precheck_clean_momentum_case():
    # Every jump continues in the same direction -> reversal_fraction 0.0, means agree.
    pairs = [(0.05, 0.02), (0.05, 0.03), (-0.05, -0.01), (-0.05, -0.02)]
    result = direction_precheck(pairs)
    assert result["reversal_fraction"] == 0.0
    assert result["mean_next_step_after_jump_up"] == 0.025
    assert result["mean_next_step_after_jump_down"] == -0.015
    assert result["is_momentum"] is True


def test_direction_precheck_clean_reversal_case():
    # Every jump reverses -> reversal_fraction 1.0, means point opposite the jump.
    pairs = [(0.05, -0.02), (0.05, -0.03), (-0.05, 0.01), (-0.05, 0.02)]
    result = direction_precheck(pairs)
    assert result["reversal_fraction"] == 1.0
    assert result["mean_next_step_after_jump_up"] == -0.025
    assert result["mean_next_step_after_jump_down"] == 0.015
    assert result["is_momentum"] is False


def test_direction_precheck_l59_shaped_regression_minority_reversal_dominates_mean():
    """L59's exact shape (S24, findings/2026-07-14-nearclose-fade-s24-verdict.md): a
    majority of jumps CONTINUE (reversal_fraction < 0.5, which alone reads as momentum)
    but a minority of LARGE reversals pulls the sign-conditioned mean the opposite way.
    A frequency-only classifier would wrongly call this momentum; the two-number check
    must not."""
    up_pairs = [
        (0.05, 0.01), (0.05, 0.01), (0.05, 0.01),   # 3 small continuations
        (0.05, -0.20),                              # 1 large reversal
    ]
    down_pairs = [
        (-0.05, -0.01), (-0.05, -0.01), (-0.05, -0.01),  # 3 small continuations
        (-0.05, 0.20),                                    # 1 large reversal
    ]
    pairs = up_pairs + down_pairs
    result = direction_precheck(pairs)
    # 6/8 continue -> reversal_fraction 0.25, comfortably <= 0.5 (looks like momentum by frequency alone).
    assert result["reversal_fraction"] == 0.25
    # But the single large reversal in each direction flips the conditional mean's sign.
    assert result["mean_next_step_after_jump_up"] < 0
    assert result["mean_next_step_after_jump_down"] > 0
    assert result["is_momentum"] is False


def test_direction_precheck_mixed_signal_not_momentum():
    # reversal_fraction low but only ONE side's mean agrees with the jump -> still not momentum.
    pairs = [(0.05, 0.02), (0.05, 0.03), (-0.05, 0.01), (-0.05, 0.02)]
    result = direction_precheck(pairs)
    assert result["reversal_fraction"] == 0.5
    assert result["mean_next_step_after_jump_up"] > 0
    assert result["mean_next_step_after_jump_down"] > 0
    assert result["is_momentum"] is False
