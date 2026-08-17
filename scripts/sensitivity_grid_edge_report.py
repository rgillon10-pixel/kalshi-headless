#!/usr/bin/env python3
"""L362 inventory: every sensitivity grid this repo declares, where its sealed value sits,
and the one-step-past-the-edge probe each axis still owes.

Read-only, fully offline (AST over committed source; no tape, no network, no clock). This
is the re-runnable artifact behind `findings/2026-08-17-l362-sensitivity-grid-edges.md`
(CLAUDE.md: no claim enters kb/ or findings/ without a script that produced it).

    python3 scripts/sensitivity_grid_edge_report.py            # human summary
    python3 scripts/sensitivity_grid_edge_report.py --json     # machine record

The DETECTOR lives in `scripts/invariants.py` (where the non-gating `--full` advisory
already calls it) and the ARITHMETIC in `core/sensitivity.py`; this module only composes
them, so there is no third copy of either to drift (L36/L102 twin discipline).

No price is read anywhere in this module: `price_provenance = {prices_quoted: false,
price_source_tag: null}`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:      # L232: `python3 scripts/foo.py` must work
    sys.path.insert(0, str(REPO_ROOT))

from core.sensitivity import (  # noqa: E402
    POSITION_HIGH_EDGE, POSITION_LOW_EDGE, grid_edge_report, out_of_grid_probes,
    structural_claim_admissible,
)
from scripts.invariants import (  # noqa: E402
    _sensitivity_grid_declarations, _sensitivity_grid_edge_issues,
)

DEFAULT_REPORT = REPO_ROOT / "reports" / "l362_sensitivity_grid_edges.json"


def inventory(root: Path = REPO_ROOT) -> dict:
    """Per-axis inventory plus the two aggregate facts L362 asks about: how many sealed
    values sit at an edge, and how many axes have ever been probed past one."""
    decls = _sensitivity_grid_declarations(root)
    axes: List[dict] = []
    for d in decls:
        probes = out_of_grid_probes(d["values"])
        position = None
        if d["preregistered"] is not None:
            vals = sorted(d["values"])
            if d["preregistered"] <= vals[0]:
                position = POSITION_LOW_EDGE if d["preregistered"] == vals[0] else "outside_grid_low"
            elif d["preregistered"] >= vals[-1]:
                position = POSITION_HIGH_EDGE if d["preregistered"] == vals[-1] else "outside_grid_high"
            else:
                position = "interior"
        axes.append({
            "path": d["path"], "grid": d["grid"], "shape": d["shape"], "axis": d["axis"],
            "values": d["values"], "preregistered": d["preregistered"],
            "pairing": d["pairing"], "seal_position": position,
            "probe_low": probes["low"], "probe_high": probes["high"],
            "probe_low_reason": probes["low_reason"],
            "probe_high_reason": probes["high_reason"],
            "spacing": probes["spacing"],
            "declares_out_of_grid_probes": d["declares_out_of_grid_probes"],
        })
    return {
        "lesson": "L362",
        "n_axes": len(axes),
        "n_modules": len({a["path"] for a in axes}),
        "n_paired": sum(1 for a in axes if a["preregistered"] is not None),
        "n_seal_at_edge": sum(1 for a in axes
                              if a["seal_position"] in (POSITION_LOW_EDGE, POSITION_HIGH_EDGE)),
        "n_modules_declaring_out_of_grid_probes":
            len({a["path"] for a in axes if a["declares_out_of_grid_probes"]}),
        "n_axes_extendable_both_sides": sum(1 for a in axes
                                            if a["probe_low"] is not None
                                            and a["probe_high"] is not None),
        "edge_seated_issues": _sensitivity_grid_edge_issues(root),
        "axes": axes,
        "price_provenance": {"prices_quoted": False, "price_source_tag": None},
    }


def cross_module_probe_coverage(inv: dict, sealed_path_frag: str,
                                follow_path_frag: str) -> Optional[dict]:
    """Did a FOLLOW-ON module's grid actually reach past the SEALED module's edges?

    Q57b widened Q57's window axis to 15 — the only out-of-grid probing this repo has ever
    performed — but nothing records that fact, so no future run can tell which edges are
    still owed. This function computes it from the two committed grids."""
    sealed = {a["axis"]: a for a in inv["axes"] if sealed_path_frag in a["path"]}
    follow = {a["axis"]: a for a in inv["axes"] if follow_path_frag in a["path"]}
    if not sealed or not follow:
        return None
    rep = grid_edge_report({k: v["values"] for k, v in sealed.items()},
                           {k: v["preregistered"] for k, v in sealed.items()},
                           probed={k: follow[k]["values"] for k in follow if k in sealed})
    ok, blocking = structural_claim_admissible(rep)
    return {
        "sealed": sealed_path_frag, "follow_on": follow_path_frag,
        "n_axes": rep["n_axes"],
        "n_edges": 2 * rep["n_axes"],
        "n_edges_probed": sum(int(a["probed_past_low"]) + int(a["probed_past_high"])
                              for a in rep["axes"]),
        "axes_probed_past_low": [a["axis"] for a in rep["axes"] if a["probed_past_low"]],
        "axes_probed_past_high": [a["axis"] for a in rep["axes"] if a["probed_past_high"]],
        "structural_claim_admissible": ok,
        "blocking_axes": blocking,
    }


def _summary(inv: dict, cross: Optional[dict]) -> str:
    lines = [f"L362 sensitivity-grid inventory: {inv['n_axes']} readable axes / "
             f"{inv['n_modules']} modules; {inv['n_paired']} paired to a sealed value; "
             f"{inv['n_seal_at_edge']} sealed AT an edge; "
             f"{inv['n_modules_declaring_out_of_grid_probes']} modules record executed "
             f"out-of-grid cells."]
    for a in inv["axes"]:
        pre = "-" if a["preregistered"] is None else f"{a['preregistered']:g}"
        lo = f"{a['probe_low']:g}" if a["probe_low"] is not None else f"({a['probe_low_reason']})"
        hi = f"{a['probe_high']:g}" if a["probe_high"] is not None else f"({a['probe_high_reason']})"
        lines.append(f"  {a['path']}::{a['grid']}[{a['axis']}] seal={pre} "
                     f"pos={a['seal_position']} spacing={a['spacing']} "
                     f"next_below={lo} next_above={hi}")
    for issue in inv["edge_seated_issues"]:
        lines.append(f"  EDGE-SEATED: {issue}")
    if cross:
        lines.append(f"  cross-module: {cross['n_edges_probed']}/{cross['n_edges']} of "
                     f"{cross['sealed']}'s edges were ever probed by {cross['follow_on']} "
                     f"(past-low {cross['axes_probed_past_low']}, "
                     f"past-high {cross['axes_probed_past_high']}); "
                     f"structural_claim_admissible={cross['structural_claim_admissible']}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print the machine record")
    ap.add_argument("--write", action="store_true",
                    help=f"also write {DEFAULT_REPORT.relative_to(REPO_ROOT)}")
    args = ap.parse_args(argv)
    inv = inventory()
    cross = cross_module_probe_coverage(inv, "q57_s82_flow_fade_probe.py",
                                        "q57b_anchor_widening_census.py")
    payload: Dict[str, object] = dict(inv)
    payload["cross_module_probe_coverage"] = cross
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_summary(inv, cross))
    if args.write:
        DEFAULT_REPORT.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
