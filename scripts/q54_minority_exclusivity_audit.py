#!/usr/bin/env python3
"""L321 — how many of Q54/S79's minority-side units are EXCLUSIVELY minority-side?

THE QUESTION. L312 added a sign-variation floor to the sealed Q54 probe: the minority arm
must span >= 2 bootstrap units (games) before a CI may be quoted. L321 (found by an
independent `verifier` under the two-agent rule, 2026-08-09) showed the floor as coded counts
units TOUCHED by at least one minority-sign entry — and a block bootstrap resamples whole
blocks (L6), so a minority arm living entirely inside otherwise-majority blocks can never
appear alone in ANY resample. The gate can therefore open on exactly the population it exists
to refuse. This script measures the gap on today's committed tape.

WHAT IT DOES NOT DO. It does not repair the probe. `scripts/q54_s79_flow_continuation_probe.py`
is SEALED mid-verdict (L311) and its pre-registration digest is pinned by a test; a research
run may not edit its gate logic. This is the measurement half only — the same posture L221's
`single_hour_leg_idempotence`, L222's `caller_explicability` and L323's tie-break audit take
toward repairs that live in a lane a cloud run may not touch.

OUTCOME-BLIND BY CONSTRUCTION. It reaches the population through the sealed probe's own
outcome-blind path (`load_all_prints` -> `eligible_tickers` -> `settled_ticker_set` ->
`entry_candidates` -> `population_report`), and before doing so it REPLACES the probe's two
outcome-reading functions (`outcome_map`, `score_rows`) with stubs that raise. So a P&L or a
settlement direction cannot enter this process even by accident — the same structural refusal
`tests/test_q54_s79_flow_continuation_probe.py::test_sealed_run_never_reads_an_outcome_value`
asserts for the probe itself. No CI, no P&L, no verdict: S79's status is unchanged and this
script cannot change it.

Read-only. No network (settlement membership comes from committed tape via
`core.settlement_sources`). Writes nothing unless `--json PATH` is given explicitly.

Run:
    python3 scripts/q54_minority_exclusivity_audit.py
    python3 scripts/q54_minority_exclusivity_audit.py --json /tmp/l321.json
"""
from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.bootstrap import (  # noqa: E402
    minority_side_unit_census,
    sign_variation_admissible,
)
from scripts import q54_s79_flow_continuation_probe as P  # noqa: E402

SCHEMA_VERSION = "q54_minority_exclusivity_audit.v1"


class OutcomeReadForbidden(RuntimeError):
    """Raised if anything in this process tries to read a settlement outcome value."""


@contextmanager
def sealed_outcome_paths(module=P):
    """Replace the probe's ONLY outcome-reading functions with raising stubs, for the
    duration of the block.

    Structural, not cosmetic (L311): while this context is open the module object cannot
    return an outcome value or a P&L, so every number computed inside it is provably
    outcome-blind. The originals are restored on exit — a permanently monkeypatched module
    would silently break the probe's own suite if it ran later in the same process, which
    is a worse failure than the one this guard prevents."""
    def _forbidden(*_a, **_k):
        raise OutcomeReadForbidden(
            "L321 audit is outcome-blind: outcome_map/score_rows are sealed here")

    saved = (module.outcome_map, module.score_rows)
    module.outcome_map = _forbidden
    module.score_rows = _forbidden
    try:
        yield module
    finally:
        module.outcome_map, module.score_rows = saved


def unit_sides(rows: Sequence[dict], settled) -> Dict[str, List[str]]:
    """unit (game, L6's blocking key) -> the side label of each SCOREABLE entry in it.

    Scoreable means "on a market with a binary settlement", exactly the population the
    probe's own `population_report` gates on — not the wider candidate list. The labels come
    straight from the probe's rows; this function invents nothing."""
    out: Dict[str, List[str]] = {}
    for r in rows:
        if r["ticker"] not in settled:
            continue
        out.setdefault(r["unit"], []).append(r["side"])
    return out


def build_report(tape_dir: Optional[Path] = None,
                 settlement_root: Optional[str] = None) -> Dict[str, object]:
    """The audit. Both counts side by side, plus both gate readings."""
    tape_dir = Path(tape_dir) if tape_dir is not None else P.TRADES_TAPE
    root = settlement_root if settlement_root is not None else P.DEFAULT_TAPE_ROOT

    with sealed_outcome_paths(P):
        prints = P.load_all_prints(tape_dir)
        tickers = P.eligible_tickers(prints)
        settled, coverage = P.settled_ticker_set(tickers, root=root)
        rows = P.entry_candidates(prints, tickers)
        pop = P.population_report(rows, settled, coverage)

    by_unit = unit_sides(rows, settled)
    census = minority_side_unit_census(by_unit, sides=(P.SIDE_NO, P.SIDE_YES))
    floor = int(P.MIN_MINORITY_SIDE_UNITS)
    gate_exclusive = sign_variation_admissible(
        by_unit, min_exclusive_minority_units=floor, sides=(P.SIDE_NO, P.SIDE_YES))

    probe_sv = dict(pop["sign_variation"])
    # The probe's own touching counts must reproduce EXACTLY, or this audit is measuring a
    # different population than the gate it is auditing (L280: measure the join from both
    # sides). Reported as a field rather than asserted, so a future divergence is visible in
    # the artifact instead of crashing the run.
    reproduces_probe = (
        {str(k): int(v) for k, v in probe_sv["units_per_side"].items()}
        == {str(k): int(v) for k, v in census["units_per_side"].items()})

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lesson": "L321",
        "queue_item": "Q54",
        "strategy": "S79",
        "probe": "scripts/q54_s79_flow_continuation_probe.py",
        "probe_preregistration_sha256": P.PREREG_SHA256,
        "outcome_paths_sealed": True,
        "network_calls": 0,
        "price_source_tag": "broker_truth",
        "trade_days": [p.name for p in P.trade_day_paths(tape_dir)],
        "n_entry_candidates_all": pop["n_entry_candidates_all"],
        "n_entry_candidates_settled": pop["n_entry_candidates_settled"],
        "n_units": pop["n_units"],
        "min_minority_side_units": floor,
        "probe_sign_variation": probe_sv,
        "census": census,
        "gate_touching_ok": bool(probe_sv["ok"]),
        "gate_exclusive": gate_exclusive,
        "reproduces_probe_units_per_side": reproduces_probe,
        "note": (
            "Measurement only (L321). The probe is sealed (L311) and unmodified; S79's "
            "verdict is unchanged and no CI, P&L or registry status is computed here. A "
            "TOUCHING count above the floor with an EXCLUSIVE count below it means the "
            "block bootstrap cannot draw a minority-only resample."),
    }


def _fmt_human(rep: Dict[str, object]) -> str:
    c = rep["census"]  # type: ignore[index]
    g = rep["gate_exclusive"]  # type: ignore[index]
    return "\n".join([
        f"L321 minority-side exclusivity — Q54/S79 population "
        f"({len(rep['trade_days'])} trade days)",  # type: ignore[arg-type]
        f"  entry candidates        : {rep['n_entry_candidates_all']} "
        f"({rep['n_entry_candidates_settled']} scoreable)",
        f"  bootstrap units (games) : {rep['n_units']}",
        f"  units per side TOUCHING : {c['units_per_side']}   "
        f"(the sealed probe's own count: {rep['probe_sign_variation']['units_per_side']}, "
        f"reproduced={rep['reproduces_probe_units_per_side']})",
        f"  units per side EXCLUSIVE: {c['exclusive_units_per_side']}   "
        f"(mixed units: {c['n_mixed_units']})",
        f"  minority side           : {c['minority_side']} — "
        f"touching {c['minority_side_units_touching']}, "
        f"exclusive {c['minority_side_units_exclusive']}, "
        f"floor {rep['min_minority_side_units']}",
        f"  gate as coded (touching): {'OPEN' if rep['gate_touching_ok'] else 'SHUT'}"
        f"   gate on L321's rule    : "
        f"{'OPEN' if g['admissible'] else 'SHUT'} {g['reasons']}",
    ])


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", metavar="PATH",
                    help="write the raw report JSON to PATH (nothing is written otherwise)")
    ap.add_argument("--tape-dir", help="override the kalshi_trades tape directory")
    ap.add_argument("--settlement-root", help="override the settlement tape root")
    args = ap.parse_args(argv)
    rep = build_report(tape_dir=args.tape_dir, settlement_root=args.settlement_root)
    print(_fmt_human(rep))
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=2, sort_keys=True)
            f.write("\n")
        print(f"[l321] report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
