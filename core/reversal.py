"""Jump direction precheck — THE sanctioned site for "does a price jump continue or
reverse" (L59: reversal FREQUENCY and reversal MAGNITUDE can disagree in sign of
implication, so a momentum/reversal precheck must report BOTH, never classify on one
alone).

S24's raw continuation frequency was 0.454 (a slight majority of jumps kept going, which
alone would read as momentum), yet the sign-conditioned mean next-step pointed the
opposite way (post-jump-up mean -$0.0061, post-jump-down mean +$0.0087) — a minority of
large reversals carried the mean. Classifying on frequency alone would have mislabeled
this DEAD-by-momentum and skipped the real (round-trip-cost) kill entirely
(`findings/2026-07-14-nearclose-fade-s24-verdict.md`). This module gives the two-number
check one home so a future momentum/reversal precheck reaches for it by default instead
of re-deriving (and re-mis-deriving) a frequency-only classification per script.

Pure functions: deterministic, no clock, no network.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple


def reverses(jump: float, next_step: Optional[float]) -> Optional[bool]:
    """Did `next_step` move OPPOSITE in sign to `jump`? None if `next_step` is missing or
    exactly zero (no direction to compare against — not a reversal, not a continuation)."""
    if next_step is None or next_step == 0:
        return None
    return (jump > 0) != (next_step > 0)


def direction_precheck(jumps_and_next: Sequence[Tuple[float, Optional[float]]]) -> dict:
    """Reversal-vs-momentum precheck (L59) over a sequence of `(jump, next_step)` pairs.

    Reports reversal FREQUENCY (fraction of directional pairs that reversed) and the
    sign-conditioned MEAN next-step move after an up-jump and after a down-jump, as two
    independent numbers — never collapses them into a single frequency-only verdict.
    `is_momentum` is True only when BOTH agree: fewer than half of jumps reverse AND the
    conditional means point the SAME way as the jump (up-jump mean > 0, down-jump mean <
    0). A reversal-direction mean survives even when the reversal fraction is <= 0.5 (a
    minority of large reversals can outweigh a majority of small continuations).

    Pairs whose `next_step` is None or exactly zero are excluded from every count (no
    direction to classify). Returns `is_momentum=False` (not None/error) on an empty or
    fully-excluded input — the conservative default, since "no evidence of momentum" is
    the safe read when there's nothing to measure."""
    up_next = []
    dn_next = []
    n_rev = 0
    n_dir = 0
    for jump, next_step in jumps_and_next:
        r = reverses(jump, next_step)
        if r is None:
            continue
        n_dir += 1
        if r:
            n_rev += 1
        (up_next if jump > 0 else dn_next).append(next_step)
    up_mean = sum(up_next) / len(up_next) if up_next else None
    dn_mean = sum(dn_next) / len(dn_next) if dn_next else None
    reversal_fraction = (n_rev / n_dir) if n_dir else None
    momentum = (
        n_dir > 0
        and reversal_fraction is not None and reversal_fraction <= 0.5
        and up_mean is not None and up_mean > 0
        and dn_mean is not None and dn_mean < 0
    )
    return {
        "n_with_next_step": n_dir,
        "reversal_fraction": reversal_fraction,
        "mean_next_step_after_jump_up": up_mean,
        "mean_next_step_after_jump_down": dn_mean,
        "is_momentum": momentum,
    }
