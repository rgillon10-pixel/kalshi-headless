"""anomaly_detector_evidence_audit — classify every committed anomaly pass's THREE checks by
whether their zero is readable (L296), using the same shared predicate the write path now uses.

Read-only. NO network. Replays `tape/anomalies/dt=*.jsonl` and answers one question per check
per pass: *was this detector's zero evidence of absence, or evidence of nothing?*

Why a replay as well as a write-path guard: the guard only labels passes captured from now on,
and every claim S3 and S15 currently rest on was captured BEFORE it existed. The historical
denominators are recoverable from the counters already persisted, so the same classification
can be applied retroactively — which is what turns "0 arbs in 26 days" into a statement with a
known denominator instead of an assumed one.

Windowing: pass `--max-day` to close the window. `tape/anomalies/` is an actively collected
family, so any number quoted from an OPEN window moves the next time the collector runs
(L286/L287); the numbers pinned in tests and quoted in findings use `--max-day 2026-08-04`.

An ABSENT counter is reported as its own class, never folded into zero: a key the collector
never wrote and a key it wrote as 0 are different claims, and only the collector's source says
which one you are looking at (L289).

Usage:
    python3 scripts/anomaly_detector_evidence_audit.py --max-day 2026-08-04
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.canonical import canonical_json  # noqa: E402
from core.detector_evidence import (ALL_EVIDENCE_CLASSES, EVIDENCE_COUNTER_ABSENT,  # noqa: E402
                                    EVIDENCE_EMPTY_DENOMINATOR, EVIDENCE_INCOHERENT,
                                    classify_record_evidence, zero_is_informative)
from core.io import REPO_ROOT  # noqa: E402

# (check name, the record's candidate-counter field, the anomaly `kind` that check emits).
# The counter field names are the ones `scripts/anomaly_sweep.py` has persisted since well
# before this audit existed — nothing here depends on the new `check_evidence` block, so the
# replay covers the whole committed history rather than only post-guard passes.
CHECKS = (
    ("bracket_arb", "n_bracket_groups_checked", "bracket_arb"),
    ("cross_strike_monotonicity", "n_monotonicity_groups_checked", "cross_strike_monotonicity"),
    ("cross_event_implication", "n_implication_pairs_checked", "cross_event_implication"),
)

_DAY_RE = re.compile(r"dt=(\d{4}-\d{2}-\d{2})")


def iter_records(tape_dir: Path, max_day: Optional[str] = None):
    """Yield (day, record) for every committed anomaly pass, oldest day first.

    A malformed line is COUNTED by the caller, never silently skipped — see `audit`.
    """
    for path in sorted(tape_dir.glob("dt=*.jsonl")):
        m = _DAY_RE.search(path.name)
        if not m:
            continue
        day = m.group(1)
        if max_day is not None and day > max_day:
            continue
        with open(path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield day, json.loads(line)
                except json.JSONDecodeError:
                    yield day, {"__malformed__": True, "__path__": str(path), "__line__": lineno}


def hits_for_kind(record: Dict[str, Any], kind: str) -> int:
    return sum(1 for a in record.get("anomalies", []) if a.get("kind") == kind)


def audit(tape_dir: Path, max_day: Optional[str] = None) -> Dict[str, Any]:
    per_check: Dict[str, collections.Counter] = {name: collections.Counter() for name, _, _ in CHECKS}
    per_check_totals: Dict[str, Dict[str, int]] = {
        name: {"sum_candidates_checked": 0, "sum_hits": 0} for name, _, _ in CHECKS
    }
    n_records = 0
    n_malformed = 0
    days: set = set()
    # A pass that LOOKS healthy (no fetch error, completeness_ok, markets actually scanned) and
    # still evaluated zero candidates is the exact shape L296 warns about: nothing in the record
    # says "this zero is empty" unless you go looking for the denominator.
    clean_looking_empty: Dict[str, List[Dict[str, Any]]] = {name: [] for name, _, _ in CHECKS}
    incoherent_records: List[Dict[str, Any]] = []
    # Descriptive cross-check: the two S3-side counters are not equal by construction (an event
    # of three `between` rungs increments the bracket counter and not the monotonicity one), so
    # whether they agree on real tape is a fact worth measuring rather than assuming.
    n_bracket_eq_monotonicity = 0

    for day, record in iter_records(tape_dir, max_day=max_day):
        if record.get("__malformed__"):
            n_malformed += 1
            continue
        n_records += 1
        days.add(day)
        if record.get("n_bracket_groups_checked") == record.get("n_monotonicity_groups_checked"):
            n_bracket_eq_monotonicity += 1
        for name, counter_field, kind in CHECKS:
            hits = hits_for_kind(record, kind)
            klass = classify_record_evidence(record, counter_field, n_hits=hits)
            per_check[name][klass] += 1
            if klass != EVIDENCE_COUNTER_ABSENT:
                per_check_totals[name]["sum_candidates_checked"] += int(record[counter_field])
                per_check_totals[name]["sum_hits"] += hits
            ident = {"day": day, "capture_id": record.get("capture_id"),
                     "n_markets_scanned": record.get("n_markets_scanned"),
                     "markets_truncated": record.get("markets_truncated"),
                     "completeness_ok": record.get("completeness_ok")}
            if klass == EVIDENCE_INCOHERENT:
                incoherent_records.append({**ident, "check": name, "n_hits": hits})
            if (klass == EVIDENCE_EMPTY_DENOMINATOR
                    and record.get("completeness_ok") is True
                    and record.get("fetch_error") is None
                    and (record.get("n_markets_scanned") or 0) > 0):
                clean_looking_empty[name].append(ident)

    out: Dict[str, Any] = {
        "schema_version": "anomaly_detector_evidence_audit.v1",
        "tape_dir": str(tape_dir),
        "max_day": max_day,
        "n_records": n_records,
        "n_malformed_lines": n_malformed,
        "n_capture_days": len(days),
        "evidence_classes": list(ALL_EVIDENCE_CLASSES),
        "per_check": {},
        "n_records_bracket_counter_equals_monotonicity_counter": n_bracket_eq_monotonicity,
        "n_incoherent_records": len(incoherent_records),
        "incoherent_records": incoherent_records[:50],
    }
    for name, _, _ in CHECKS:
        counts = {k: per_check[name].get(k, 0) for k in ALL_EVIDENCE_CLASSES}
        readable = sum(v for k, v in counts.items() if zero_is_informative(k))
        out["per_check"][name] = {
            "class_counts": counts,
            **per_check_totals[name],
            "n_passes_whose_zero_is_readable": readable,
            "n_clean_looking_empty_denominator_passes": len(clean_looking_empty[name]),
            "clean_looking_empty_denominator_examples": clean_looking_empty[name][:5],
        }
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tape-dir", default=str(REPO_ROOT / "tape" / "anomalies"))
    ap.add_argument("--max-day", default=None,
                    help="inclusive upper bound dt (e.g. 2026-08-04) — REQUIRED for any number "
                         "you intend to pin or publish; without it the window is open and every "
                         "count moves on the next collector pass")
    ap.add_argument("--out", default=str(REPO_ROOT / "reports" / "anomaly_detector_evidence_audit.json"))
    args = ap.parse_args(argv)

    result = audit(Path(args.tape_dir), max_day=args.max_day)
    if args.max_day is None:
        print("[evidence_audit] WARN open window (--max-day not given): these counts will move "
              "on the next collector pass and must not be pinned", file=sys.stderr)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(canonical_json(result) + "\n", encoding="utf-8")

    print(f"[evidence_audit] {result['n_records']} passes over {result['n_capture_days']} "
          f"capture-days (max_day={args.max_day})")
    for name, _, _ in CHECKS:
        blk = result["per_check"][name]
        cc = blk["class_counts"]
        print(f"  {name:28s} readable_zero={blk['n_passes_whose_zero_is_readable']:4d} "
              f"empty_denominator={cc[EVIDENCE_EMPTY_DENOMINATOR]:4d} "
              f"counter_absent={cc[EVIDENCE_COUNTER_ABSENT]:3d} "
              f"hits={cc['hits']:4d} incoherent={cc[EVIDENCE_INCOHERENT]:3d} "
              f"| sum_checked={blk['sum_candidates_checked']} sum_hits={blk['sum_hits']}")
    print(f"  wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
