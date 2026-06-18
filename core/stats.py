"""Ensemble statistics — THE sanctioned home for `pstdev` (Hard Rule #2).

Hard Rule #2: never take `pstdev(member_values)` without a `member_count >= 4` guard. pt1
mixed ensemble arrays of wildly different member counts (3 / 5 / 150 / 255 members); a
population stdev over 3 members is noise masquerading as a spread signal, and feeding it
into sizing is how a non-edge gets amplified.

The invariant engine (scripts/invariants.py) BLOCKS bare `pstdev(` and `from statistics
import pstdev` everywhere except this file. Route ensemble spread through `safe_pstdev`,
which refuses fewer than `MIN_MEMBERS` members rather than returning a confident-looking
number from too little data.
"""
from __future__ import annotations

import statistics
from typing import Sequence

MIN_MEMBERS = 4


def safe_pstdev(values: Sequence[float], *, min_members: int = MIN_MEMBERS) -> float:
    """Population stdev with a hard member-count floor (Hard Rule #2).

    Raises ValueError if fewer than `min_members` values are supplied — the n>=4 guard
    that the invariant engine cannot express but the rule requires.
    """
    n = len(values)
    if n < min_members:
        raise ValueError(
            f"safe_pstdev: {n} members < min_members={min_members} (Hard Rule #2). "
            f"A population stdev over <4 ensemble members is noise, not a spread signal."
        )
    return statistics.pstdev(values)
