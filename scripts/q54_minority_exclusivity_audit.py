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

TIE-BREAK EXPOSURE (added 2026-08-14, L323's residual). This audit reaches its population
through the SEALED probe's `entry_candidates` -> `first_agreeing_print`, which selects ONE
print per decision instant. 48.5% of committed `kalshi_trades` prints sit in an exact-timestamp
`(ticker, created_time)` tie and 7,999 tie groups disagree on price (L323), and the selected
print's `yes_price` decides both the entry price and whether the row survives the probe's
price band -- so which print wins a tie can move this audit's own population, hence L321's
headline counts. The tie order today is FILE ORDER: incidental, not declared. `--sensitivity`
re-runs the whole population under three explicit orderings and reports whether the headline
moves, so the exposure is measured rather than assumed. The sealed probe is NOT edited: the
re-ordering happens in this process, on the loaded print series, after `load_all_prints`.

Run:
    python3 scripts/q54_minority_exclusivity_audit.py
    python3 scripts/q54_minority_exclusivity_audit.py --json /tmp/l321.json
    python3 scripts/q54_minority_exclusivity_audit.py --sensitivity
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

#: Explicit orderings for EXACT-TIMESTAMP print ties (L323). "file" is today's incidental
#: behaviour and is the default everywhere, so every pre-existing number is unchanged.
TIE_BREAKS: Sequence[str] = ("file", "reversed", "trade_id")


def reorder_ties(prints: Dict[str, List[dict]], mode: str = "file") -> Dict[str, List[dict]]:
    """Re-order EXACT-TIMESTAMP ties inside each ticker's print series (L323).

    `file` returns the input unchanged (today's incidental order: the probe's `load_all_prints`
    stable-sorts on `ts`, so ties keep the order the tape was written in). `reversed` is the
    adversarial ordering -- it flips ONLY the members of a tie group, never the chronology, so
    any number that moves between the two is order-dependent by construction. `trade_id` is
    the explicit key L323 proposes, applied as a string sort within each tie group (records
    lacking a `trade_id` sort last, under their own file order, rather than crashing).

    Pure: builds new lists, never mutates the caller's. Unknown mode raises -- a silent
    fallback to file order would let a typo report "no sensitivity" from an unrun comparison.
    """
    if mode not in TIE_BREAKS:
        raise ValueError(f"unknown tie-break mode {mode!r}; expected one of {TIE_BREAKS}")
    if mode == "file":
        return {tk: list(rows) for tk, rows in prints.items()}
    out: Dict[str, List[dict]] = {}
    for tk, rows in prints.items():
        new_rows: List[dict] = []
        i = 0
        n = len(rows)
        while i < n:
            j = i + 1
            while j < n and rows[j]["ts"] == rows[i]["ts"]:
                j += 1
            group = list(rows[i:j])
            if len(group) > 1:
                if mode == "reversed":
                    group.reverse()
                else:  # trade_id
                    group = [g for _, g in sorted(
                        enumerate(group),
                        key=lambda ig: (ig[1].get("trade_id") is None,
                                        str(ig[1].get("trade_id") or ""), ig[0]))]
            new_rows.extend(group)
            i = j
        out[tk] = new_rows
    return out


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
                 settlement_root: Optional[str] = None,
                 tie_break: str = "file") -> Dict[str, object]:
    """The audit. Both counts side by side, plus both gate readings.

    `tie_break` selects how exact-timestamp print ties are ordered before the sealed probe's
    `first_agreeing_print` picks one (L323); the default reproduces today's incidental file
    order exactly, so the headline this function has always reported is unchanged."""
    tape_dir = Path(tape_dir) if tape_dir is not None else P.TRADES_TAPE
    root = settlement_root if settlement_root is not None else P.DEFAULT_TAPE_ROOT

    with sealed_outcome_paths(P):
        prints = reorder_ties(P.load_all_prints(tape_dir), tie_break)
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
        "tie_break": tie_break,
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


#: The headline fields L321's row, the invariants banner and this audit's own human output
#: all quote. If any of these moves between tie-break orderings, the quoted number is
#: order-dependent and must be reported with the ordering that produced it (L323).
SENSITIVE_FIELDS: Sequence[str] = (
    "n_entry_candidates_all",
    "n_entry_candidates_settled",
    "n_units",
    "units_per_side_touching",
    "units_per_side_exclusive",
    "n_mixed_units",
    "minority_side",
    "gate_touching_ok",
    "gate_exclusive_ok",
)


def _headline(rep: Dict[str, object]) -> Dict[str, object]:
    """The comparable projection of a report (JSON-safe, order-stable)."""
    census = rep["census"]  # type: ignore[index]
    return {
        "n_entry_candidates_all": rep["n_entry_candidates_all"],
        "n_entry_candidates_settled": rep["n_entry_candidates_settled"],
        "n_units": rep["n_units"],
        "units_per_side_touching": {str(k): int(v)
                                    for k, v in census["units_per_side"].items()},
        "units_per_side_exclusive": {str(k): int(v)
                                     for k, v in census["exclusive_units_per_side"].items()},
        "n_mixed_units": int(census["n_mixed_units"]),
        "minority_side": census["minority_side"],
        "gate_touching_ok": bool(rep["gate_touching_ok"]),
        "gate_exclusive_ok": bool(rep["gate_exclusive"]["admissible"]),  # type: ignore[index]
    }


def perturbation_reach(tape_dir: Optional[Path] = None,
                       modes: Sequence[str] = TIE_BREAKS) -> Dict[str, object]:
    """How far does the tie re-ordering actually REACH into this population? (L249/L250)

    An "invariant under tie-break" headline is worthless if the re-ordering never changed
    anything -- the same vacuity trap L249 (is the ALIVE branch reachable?) and L250 (a
    saturated proxy is NO evidence) name. So this reports, beside the tie census over the
    eligible population, how many of the audit's OWN entry rows fill against a different
    `trade_id` and how many get a different `entry_price` under each non-baseline ordering.
    Settlement is not consulted here (the counts are over the full candidate list), which
    keeps it outcome-blind and cheap.
    """
    tape_dir = Path(tape_dir) if tape_dir is not None else P.TRADES_TAPE
    with sealed_outcome_paths(P):
        prints = P.load_all_prints(tape_dir)
        tickers = P.eligible_tickers(prints)
        rows_by_mode = {m: P.entry_candidates(reorder_ties(prints, m), tickers)
                        for m in modes}

    n_prints = 0
    n_tie_groups = 0
    n_prints_in_ties = 0
    n_groups_price_disagree = 0
    for tk in tickers:
        seq = prints.get(tk) or []
        n_prints += len(seq)
        i = 0
        while i < len(seq):
            j = i + 1
            while j < len(seq) and seq[j]["ts"] == seq[i]["ts"]:
                j += 1
            if j - i > 1:
                n_tie_groups += 1
                n_prints_in_ties += j - i
                if len({r["yes_price"] for r in seq[i:j]}) > 1:
                    n_groups_price_disagree += 1
            i = j

    def _key(r: dict):
        return (r["ticker"], r["decision_ts"])

    base = {_key(r): r for r in rows_by_mode[modes[0]]}
    per_mode: Dict[str, object] = {}
    for m in modes[1:]:
        other = {_key(r): r for r in rows_by_mode[m]}
        common = set(base) & set(other)
        per_mode[m] = {
            "n_entry_rows": len(other),
            "n_rows_only_in_baseline": len(set(base) - set(other)),
            "n_rows_only_in_mode": len(set(other) - set(base)),
            "n_changed_entry_trade_id": sum(
                1 for k in common
                if base[k].get("entry_trade_id") != other[k].get("entry_trade_id")),
            "n_changed_entry_price": sum(
                1 for k in common
                if abs(float(base[k]["entry_price"]) - float(other[k]["entry_price"])) > 1e-12),
        }
    return {
        "n_eligible_prints": n_prints,
        "n_tie_groups": n_tie_groups,
        "n_prints_in_ties": n_prints_in_ties,
        "frac_prints_in_ties": (n_prints_in_ties / n_prints) if n_prints else 0.0,
        "n_tie_groups_disagreeing_on_yes_price": n_groups_price_disagree,
        "n_entry_rows_baseline": len(base),
        "vs_baseline": per_mode,
    }


def tie_break_sensitivity(tape_dir: Optional[Path] = None,
                          settlement_root: Optional[str] = None,
                          modes: Sequence[str] = TIE_BREAKS) -> Dict[str, object]:
    """Is L321's headline invariant under the tie-break it never declared? (L323)

    Runs the FULL audit once per ordering and diffs the headline projection. A field that is
    identical across every ordering is order-insensitive ON TODAY'S TAPE -- which is evidence
    about this population, never a proof about the rule (the tape is append-only and still
    backfilling, so this must be re-measured, not memorised: L320's growth-safety discipline).
    """
    reports = {m: build_report(tape_dir=tape_dir, settlement_root=settlement_root,
                               tie_break=m) for m in modes}
    heads = {m: _headline(r) for m, r in reports.items()}
    reach = perturbation_reach(tape_dir=tape_dir, modes=modes)
    base = heads[modes[0]]
    moved = sorted(f for f in SENSITIVE_FIELDS
                   if any(heads[m][f] != base[f] for m in modes[1:]))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lesson": "L323",
        "audited_lesson_headline": "L321",
        "price_source_tag": "broker_truth",
        "network_calls": 0,
        "outcome_paths_sealed": True,
        "modes": list(modes),
        "baseline_mode": modes[0],
        "headline_by_mode": heads,
        "moved_fields": moved,
        "headline_invariant_under_tie_break": not moved,
        "perturbation_reach": reach,
        "n_ties_note": (
            "Tie exposure on the family as a whole is measured by "
            "scripts/trade_print_tiebreak_audit.py; this report answers only whether THIS "
            "audit's own headline moves."),
    }


def _fmt_sensitivity(rep: Dict[str, object]) -> str:
    heads = rep["headline_by_mode"]  # type: ignore[index]
    lines = [f"L323 tie-break sensitivity of the L321 headline "
             f"(modes: {', '.join(rep['modes'])})"]  # type: ignore[arg-type]
    for f in SENSITIVE_FIELDS:
        vals = [f"{m}={heads[m][f]}" for m in rep["modes"]]  # type: ignore[index]
        flag = "  <-- MOVES" if f in rep["moved_fields"] else ""  # type: ignore[operator]
        lines.append(f"  {f:28s}: {'  '.join(vals)}{flag}")
    reach = rep["perturbation_reach"]  # type: ignore[index]
    lines.append(f"  perturbation reach: {reach['n_prints_in_ties']}/{reach['n_eligible_prints']} "
                 f"({100 * float(reach['frac_prints_in_ties']):.2f}%) eligible prints sit in "
                 f"{reach['n_tie_groups']} tie group(s), "
                 f"{reach['n_tie_groups_disagreeing_on_yes_price']} disagreeing on yes_price")
    for m, d in sorted(reach["vs_baseline"].items()):  # type: ignore[union-attr]
        lines.append(f"    vs baseline [{m}]: {d['n_changed_entry_trade_id']}"
                     f"/{reach['n_entry_rows_baseline']} entry rows fill a DIFFERENT trade_id, "
                     f"{d['n_changed_entry_price']} get a different entry_price")
    lines.append(f"  headline invariant under tie-break: "
                 f"{rep['headline_invariant_under_tie_break']}")
    return "\n".join(lines)


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
    ap.add_argument("--tie-break", choices=list(TIE_BREAKS), default="file",
                    help="ordering applied to exact-timestamp print ties (L323); "
                         "'file' is today's incidental order and the default")
    ap.add_argument("--sensitivity", action="store_true",
                    help="re-run the audit under every tie-break ordering and report "
                         "whether the L321 headline moves (L323)")
    args = ap.parse_args(argv)
    if args.sensitivity:
        rep = tie_break_sensitivity(tape_dir=args.tape_dir,
                                    settlement_root=args.settlement_root)
        print(_fmt_sensitivity(rep))
    else:
        rep = build_report(tape_dir=args.tape_dir, settlement_root=args.settlement_root,
                           tie_break=args.tie_break)
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
