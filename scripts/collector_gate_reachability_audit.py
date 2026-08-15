#!/usr/bin/env python3
"""collector_gate_reachability_audit.py — is every once-per-UTC-day collector leg's gate
hour REACHABLE by the scheduler we can actually observe? (L123's third half)

READ-ONLY over committed tape. No network, no credentials, no `execution/` import, and it
NEVER edits `collection/hourly_pass.py` — widening a live collector gate is L123's candidate
(b), explicitly Ryan/VPS-side, and the `daily_leg_due()` repair already exists in open
PR #165 (L221/L246). This script measures and reports; it does not repair.

What it answers, per single-hour leg registered in `scripts/invariants.py`:

    the leg fires when `ts.hour == N` (ts = the pass START instant)
    -> over the trailing committed window, did ANY observed pass actually START in hour N?

`REACHABLE` = at least one did. `UNREACHABLE` = none did on adequate evidence (a
rule-of-three bound travels with it). `INSUFFICIENT_EVIDENCE` / `WITNESS_DISAGREEMENT` /
`NO_WITNESS_TAPE` are distinct abstentions, never collapsed into a `False`.

Gate hours are read out of `collection/hourly_pass.py` itself (never re-declared here), and
the measurement is `scripts/tape_gap_monitor.py::gate_hour_reachability` (never re-implemented
here) — one shared site each, L36.

Run:
    python3 scripts/collector_gate_reachability_audit.py
    python3 scripts/collector_gate_reachability_audit.py --out reports/x.json --trailing-days 14
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_OUT = REPO_ROOT / "reports" / "collector_gate_reachability.json"


def _load(name: str, rel: str):
    """Load a `scripts/` module by path — they are not a package, and importing one as
    `scripts.x` breaks the direct-CLI form the docstring cites (L232)."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    if spec is None or spec.loader is None:                     # pragma: no cover - defensive
        raise ImportError(rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_report(tape_root: Optional[Path] = None,
                 trailing_days: Optional[int] = None,
                 days: Optional[List[str]] = None) -> Dict[str, Any]:
    """The full per-leg reachability table. Pure given the tree; no network."""
    inv = _load("invariants_mod", "scripts/invariants.py")
    tgm = _load("tape_gap_monitor_mod", "scripts/tape_gap_monitor.py")
    tape_root = (REPO_ROOT / "tape") if tape_root is None else tape_root
    if trailing_days is None:
        trailing_days = tgm.GATE_REACHABILITY_TRAILING_DAYS

    gate_hours: Dict[str, int] = inv._single_hour_leg_gate_hours()
    legs: Dict[str, Any] = {}
    for fam in sorted(gate_hours):
        legs[fam] = tgm.gate_hour_reachability(
            tape_root, gate_hours[fam], days=days, trailing_days=trailing_days, family=fam)

    src = (REPO_ROOT / "collection" / "hourly_pass.py").read_text(encoding="utf-8")
    all_consts = {m.group(1): int(m.group(2)) for m in inv._UTC_HOUR_CONST_RE.finditer(src)}
    exempt: Dict[str, Any] = {}
    for const, reason in sorted(inv.SINGLE_HOUR_LEG_EXEMPT.items()):
        h = all_consts.get(const)
        if h is None:
            continue
        rep = tgm.gate_hour_reachability(tape_root, h, days=days,
                                         trailing_days=trailing_days, family=const)
        rep["exempt_reason"] = reason
        exempt[const] = rep

    unreachable = sorted(f for f, r in legs.items() if r.get("verdict") == "UNREACHABLE")
    return {
        "schema_version": "collector_gate_reachability.v1",
        "trailing_days": trailing_days,
        "frozen_days": list(days) if days else None,
        "gate_hours": gate_hours,
        "legs": legs,
        "exempt_legs": exempt,
        "n_legs": len(legs),
        "n_unreachable": len(unreachable),
        "unreachable_families": unreachable,
        "repair_disposition": (
            "DETECTION ONLY. Widening a live `if ts.hour == N` gate is L123 candidate (b), "
            "Ryan/VPS-side; the once-per-day `daily_leg_due()` key already exists in open "
            "PR #165 (L221/L246 — a second implementation was written and reverted). This "
            "run did not touch collection/hourly_pass.py."),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tape-root", default=str(REPO_ROOT / "tape"))
    ap.add_argument("--trailing-days", type=int, default=None)
    ap.add_argument("--days", default=None, metavar="dt=YYYY-MM-DD,...",
                    help="frozen dt= slice (overrides --trailing-days)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)

    days = [d.strip() for d in args.days.split(",") if d.strip()] if args.days else None
    rep = build_report(Path(args.tape_root), args.trailing_days, days)

    for fam in sorted(rep["legs"]):
        r = rep["legs"][fam]
        print(f"{fam:24s} gate {r['gate_hour_utc']:02d}Z  {r['verdict']:22s} "
              f"{r['n_at_gate_hour']}/{r['n_pass_instants']} observed pass-starts "
              f"(witness {r['primary_witness']})")
    for const in sorted(rep["exempt_legs"]):
        r = rep["exempt_legs"][const]
        print(f"{const:24s} gate {r['gate_hour_utc']:02d}Z  {r['verdict']:22s} "
              f"{r['n_at_gate_hour']}/{r['n_pass_instants']}  [EXEMPT: no committed family]")
    print(f"\n{rep['n_unreachable']}/{rep['n_legs']} registered leg(s) UNREACHABLE: "
          f"{rep['unreachable_families'] or 'none'}")

    if not args.no_write:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rep, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
