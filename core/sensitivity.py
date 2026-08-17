"""Sensitivity-grid edge arithmetic — compounding **L362** into code.

L362 (2026-08-16, Q57/S82 verifier round): *a sensitivity grid that only BRACKETS the
pre-registered value cannot distinguish "structural" from "an artifact of this constant."*
Q57's `flow_window_minutes` axis ran `(30, 60, 120, 240, 480)` around a pre-registered 120
— the pre-registered value sits comfortably INTERIOR, so an "is the seal at an edge?" check
would have passed — yet the claimed sign-variation degeneracy dissolved at **15 minutes**,
one geometric step PAST the grid's own low edge, where nobody had looked. The lesson is
therefore not "keep the seal interior"; it is **"probe past the edge, one axis at a time,
before calling anything structural."**

This module supplies the two things that rule needs to stop being a memory:

1. `out_of_grid_probes(values)` — the concrete values one step beyond each edge, derived
   from the axis's OWN spacing (geometric axes extend by their ratio, arithmetic axes by
   their step), so "probe past the edge" names a number instead of a wish. On Q57's own
   committed axis it returns **15.0** on the low side: the exact value the verifier had to
   discover by hand is mechanically derivable from the grid as sealed.
2. `grid_edge_report(...)` / `structural_claim_admissible(...)` — a per-axis record of
   whether each edge was actually probed (or is at a declared natural bound), and a single
   boolean a probe may cite before writing the word "structural".

Deliberately NOT decided here (per-probe judgment, the `core.bootstrap` precedent):
- WHICH axes belong in a grid at all, and what the pre-registered value should be.
- Whether an axis has a natural bound. `min_window_count` cannot go below 0 and
  `min_abs_rho` cannot go below 0, but only the caller knows that; pass `bounds=`.
- Whether an out-of-grid cell is MECHANISM-FAITHFUL (Q57b's 180-minute entry-lag cells
  cleared every population floor while abandoning the mechanism). Probing past the edge is
  necessary for a structural claim, never sufficient for an alive one.

Pure: no I/O, no clock, no tape.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Mapping, Optional, Sequence, Tuple

# Spacing kinds.
SPACING_ARITHMETIC = "arithmetic"
SPACING_GEOMETRIC = "geometric"
SPACING_IRREGULAR = "irregular"
SPACING_SINGLETON = "singleton"
SPACING_EMPTY = "empty"

# Axis positions of a pre-registered value relative to its own grid.
POSITION_INTERIOR = "interior"
POSITION_LOW_EDGE = "low_edge"
POSITION_HIGH_EDGE = "high_edge"
POSITION_OUTSIDE_LOW = "outside_grid_low"
POSITION_OUTSIDE_HIGH = "outside_grid_high"
POSITION_SINGLETON = "singleton_axis"
POSITION_ABSENT = "not_pre_registered"

# Relative tolerance for "the same step" / "the same ratio". Grids are hand-written
# decimal literals (0.05, 0.10, 0.20), so binary float noise is ~1e-16; 1e-9 is loose
# enough to absorb it and tight enough that 0.02/0.03/0.04 is NOT read as geometric.
_REL_TOL = 1e-9


def _clean(values: Sequence[float]) -> Tuple[float, ...]:
    """Sorted, de-duplicated, float-cast axis values. Order in the source literal is
    incidental (a grid is a set of cells); duplicates are a typo, not a second cell."""
    out = sorted({float(v) for v in values})
    return tuple(out)


def _all_close(xs: Sequence[float]) -> bool:
    if not xs:
        return False
    first = xs[0]
    scale = max(abs(first), 1.0)
    return all(abs(x - first) <= _REL_TOL * scale for x in xs)


def axis_spacing(values: Sequence[float]) -> dict:
    """Classify an axis's spacing and report the parameter needed to extend it.

    Returns `{"kind", "step", "ratio", "values", "ambiguous_two_point"}`. A two-point axis
    is BOTH arithmetic and geometric; it is reported as `arithmetic` (the conservative,
    smaller extension) with `ambiguous_two_point=True` and the geometric `ratio` also
    filled, so a caller that knows better can choose — the tool never hides the ambiguity.
    A geometric reading requires all values strictly positive (a 0 in the axis makes ratios
    meaningless, e.g. `(0.0, 100.0, 1000.0)` -> irregular, correctly)."""
    vals = _clean(values)
    if not vals:
        return {"kind": SPACING_EMPTY, "step": None, "ratio": None,
                "values": vals, "ambiguous_two_point": False}
    if len(vals) == 1:
        return {"kind": SPACING_SINGLETON, "step": None, "ratio": None,
                "values": vals, "ambiguous_two_point": False}

    diffs = [b - a for a, b in zip(vals, vals[1:])]
    arithmetic = _all_close(diffs)
    ratios: Optional[list] = None
    geometric = False
    if all(v > 0.0 for v in vals):
        ratios = [b / a for a, b in zip(vals, vals[1:])]
        geometric = _all_close(ratios)

    two_point = len(vals) == 2
    if arithmetic:
        return {"kind": SPACING_ARITHMETIC, "step": diffs[0],
                "ratio": (ratios[0] if (geometric and ratios) else None),
                "values": vals, "ambiguous_two_point": bool(two_point and geometric)}
    if geometric and ratios:
        return {"kind": SPACING_GEOMETRIC, "step": None, "ratio": ratios[0],
                "values": vals, "ambiguous_two_point": False}
    return {"kind": SPACING_IRREGULAR, "step": None, "ratio": None,
            "values": vals, "ambiguous_two_point": False}


def out_of_grid_probes(values: Sequence[float],
                       bounds: Tuple[Optional[float], Optional[float]] = (None, None)
                       ) -> dict:
    """The value one step BEYOND each edge, in the axis's own spacing, plus a reason when a
    side cannot be extended.

    `bounds` are NATURAL limits the caller declares (e.g. a count axis cannot go below 0).
    A side whose extension would cross its bound returns `None` with reason
    `at_natural_bound` — that is an ANSWER (the edge is the end of the physical axis), not
    a refusal, and `structural_claim_admissible` treats it as satisfied.

    An irregular axis returns `None` on both sides with reason `irregular_spacing`: this
    module will not invent a step for `(30, 60, 240, 4320)`. Naming the extension is then a
    human judgment, and saying so beats guessing (the `core.bootstrap` unit-choice
    precedent).
    """
    sp = axis_spacing(values)
    vals = sp["values"]
    lo_bound, hi_bound = bounds
    out = {"low": None, "high": None, "low_reason": None, "high_reason": None,
           "spacing": sp["kind"], "ambiguous_two_point": sp["ambiguous_two_point"]}
    # A side whose EDGE already sits at its declared natural limit is settled no matter how
    # the axis is spaced — there is nothing beyond it to probe. This must be decided BEFORE
    # the spacing refusal below, else an irregular axis that starts at its own floor (the
    # `min_window_count = (0, 100, 250)` shape) reports `irregular_spacing` and looks like
    # an unmet obligation forever. Caught by
    # tests/test_sensitivity_grid_edges.py::test_natural_bound_plus_one_probe_settles_the_axis.
    at_lo = bool(vals) and lo_bound is not None and \
        vals[0] <= lo_bound + _REL_TOL * max(abs(lo_bound), 1.0)
    at_hi = bool(vals) and hi_bound is not None and \
        vals[-1] >= hi_bound - _REL_TOL * max(abs(hi_bound), 1.0)
    if at_lo:
        out["low_reason"] = "at_natural_bound"
    if at_hi:
        out["high_reason"] = "at_natural_bound"
    if sp["kind"] in (SPACING_EMPTY, SPACING_SINGLETON):
        if not at_lo:
            out["low_reason"] = f"{sp['kind']}_axis"
        if not at_hi:
            out["high_reason"] = f"{sp['kind']}_axis"
        return out
    if sp["kind"] == SPACING_IRREGULAR:
        if not at_lo:
            out["low_reason"] = "irregular_spacing"
        if not at_hi:
            out["high_reason"] = "irregular_spacing"
        return out

    if sp["kind"] == SPACING_ARITHMETIC:
        low = vals[0] - float(sp["step"])
        high = vals[-1] + float(sp["step"])
    else:
        ratio = float(sp["ratio"])
        low = vals[0] / ratio
        high = vals[-1] * ratio

    if at_lo or (lo_bound is not None
                 and low < lo_bound - _REL_TOL * max(abs(lo_bound), 1.0)):
        out["low_reason"] = "at_natural_bound"
    else:
        out["low"] = low
    if at_hi or (hi_bound is not None
                 and high > hi_bound + _REL_TOL * max(abs(hi_bound), 1.0)):
        out["high_reason"] = "at_natural_bound"
    else:
        out["high"] = high
    return out


@dataclass(frozen=True)
class AxisEdgeStatus:
    """One axis of one grid: where the seal sits, and whether the edges were probed."""
    axis: str
    values: Tuple[float, ...]
    preregistered: Optional[float]
    position: str
    spacing: str
    probe_low: Optional[float]
    probe_high: Optional[float]
    probe_low_reason: Optional[str]
    probe_high_reason: Optional[str]
    probed_past_low: bool
    probed_past_high: bool

    @property
    def edges_settled(self) -> bool:
        """True when BOTH sides are either probed past or terminated at a natural bound —
        the L362 precondition for calling a result structural on this axis."""
        low_ok = self.probed_past_low or self.probe_low_reason == "at_natural_bound"
        high_ok = self.probed_past_high or self.probe_high_reason == "at_natural_bound"
        return bool(low_ok and high_ok)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["values"] = list(self.values)
        d["edges_settled"] = self.edges_settled
        return d


def axis_edge_status(axis: str, values: Sequence[float],
                     preregistered: Optional[float] = None,
                     probed: Sequence[float] = (),
                     bounds: Tuple[Optional[float], Optional[float]] = (None, None)
                     ) -> AxisEdgeStatus:
    """Position of `preregistered` within `values`, plus whether `probed` reaches past each
    edge. `probed` is the set of axis values ACTUALLY evaluated outside the declared grid
    (an empty default is the honest state of every grid in this repo as of L362)."""
    vals = _clean(values)
    probes = out_of_grid_probes(vals, bounds=bounds)
    if not vals:
        position = POSITION_ABSENT if preregistered is None else POSITION_OUTSIDE_LOW
    elif preregistered is None:
        position = POSITION_ABSENT
    elif len(vals) == 1:
        position = POSITION_SINGLETON
    elif preregistered < vals[0]:
        position = POSITION_OUTSIDE_LOW
    elif preregistered > vals[-1]:
        position = POSITION_OUTSIDE_HIGH
    elif abs(preregistered - vals[0]) <= _REL_TOL * max(abs(vals[0]), 1.0):
        position = POSITION_LOW_EDGE
    elif abs(preregistered - vals[-1]) <= _REL_TOL * max(abs(vals[-1]), 1.0):
        position = POSITION_HIGH_EDGE
    else:
        position = POSITION_INTERIOR

    lo = vals[0] if vals else None
    hi = vals[-1] if vals else None
    probed_low = any(float(p) < lo for p in probed) if lo is not None else False
    probed_high = any(float(p) > hi for p in probed) if hi is not None else False
    return AxisEdgeStatus(
        axis=axis, values=vals,
        preregistered=(None if preregistered is None else float(preregistered)),
        position=position, spacing=probes["spacing"],
        probe_low=probes["low"], probe_high=probes["high"],
        probe_low_reason=probes["low_reason"], probe_high_reason=probes["high_reason"],
        probed_past_low=probed_low, probed_past_high=probed_high)


def grid_edge_report(grid: Mapping[str, Sequence[float]],
                     preregistration: Optional[Mapping[str, object]] = None,
                     probed: Optional[Mapping[str, Sequence[float]]] = None,
                     bounds: Optional[Mapping[str, Tuple[Optional[float],
                                                         Optional[float]]]] = None) -> dict:
    """Per-axis L362 record for a whole grid.

    `preregistration` may be the probe's full sealed spec dict — only keys matching an axis
    name and carrying a numeric value are read, so a spec full of prose fields is fine and
    an axis with no matching key is honestly `not_pre_registered` rather than assumed."""
    prereg = preregistration or {}
    probed = probed or {}
    bounds = bounds or {}
    axes = []
    for axis in sorted(grid):
        raw = prereg.get(axis)
        pre = float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None
        axes.append(axis_edge_status(axis, grid[axis], preregistered=pre,
                                     probed=probed.get(axis, ()),
                                     bounds=bounds.get(axis, (None, None))))
    at_edge = [a.axis for a in axes if a.position in (POSITION_LOW_EDGE, POSITION_HIGH_EDGE)]
    unsettled = [a.axis for a in axes if not a.edges_settled]
    return {
        "n_axes": len(axes),
        "axes": [a.to_dict() for a in axes],
        "axes_with_seal_at_an_edge": at_edge,
        "axes_with_unprobed_edges": unsettled,
        "structural_claim_admissible": not unsettled and bool(axes),
    }


def structural_claim_admissible(report: Mapping[str, object]) -> Tuple[bool, list]:
    """`(admissible, blocking_axes)` for a `grid_edge_report`. A "structural / no more tape
    helps" claim is admissible only when EVERY axis has been probed past both edges or is
    terminated at a declared natural bound (L362). An empty grid is never admissible: a
    claim of structure with no sensitivity evidence at all is the weakest case, not the
    strongest."""
    blocking = list(report.get("axes_with_unprobed_edges") or [])
    admissible = bool(report.get("structural_claim_admissible"))
    return admissible, blocking
