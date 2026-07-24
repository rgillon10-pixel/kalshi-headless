#!/usr/bin/env python3
"""Read-only census: which committed-tape timestamp values would crash a strict
Python-3.9 ``datetime.fromisoformat`` consumer (the L136/L138/L141 hazard)?

Standalone diagnostic (like ``scripts/tape_gap_monitor.py`` /
``scripts/universe_sweep_liquidity_census.py``) — NOT wired into
``scripts/invariants.py``'s gate (a full-tape scan of ~1M lines is too slow for
the pre-commit path) and NOT a collector. Reads only ``tape/*/dt=*.jsonl``,
writes nothing, makes no network call.

Background. Python 3.9's ``datetime.fromisoformat`` rejects (a) a bare trailing
``Z`` and (b) a fractional-seconds component whose digit-count is not exactly 3
or 6 (short 1-2 digit fractions AND over-length >6-digit nanosecond fractions).
``core.timeutil.parse_iso_utc`` normalizes all of these before parsing, so it is
the sanctioned wrapper (L138); L141 already flags the raw call sites in code.
This script answers the complementary, never-before-measured question: does the
committed TAPE actually carry the hazardous shape, i.e. is the migration backlog
an urgent live landmine or a theoretical one? (Answer as of 2026-07-24: 37.87%
of 1,725,070 timestamp values are hazardous -> URGENT. See
findings/2026-07-24-tape-timestamp-parseability-audit.md.)

Emulation note: this sandbox runs Python 3.11 (where raw ``fromisoformat``
already tolerates Z/short/long fractions), so the 3.9 hazard is emulated by the
regex/digit-count rule below, NEVER by calling ``fromisoformat`` and catching.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict
from typing import Dict, Iterator, Optional, Tuple

# Repo root on sys.path so `core` imports work when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.timeutil import parse_iso_utc  # noqa: E402  (sanctioned wrapper)

# A value that looks like an ISO-8601 datetime string. Seconds optional so a
# seconds-less bare-Z shape ("2026-06-28T02:00Z", which 3.9 also rejects) is
# not silently skipped. Groups: 1=fraction-with-dot, 2=fraction-digits, 3=tz.
_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$"
)


def classify(value: str) -> Optional[Tuple[bool, str]]:
    """Return (is_3_9_hazardous, reason) for an ISO timestamp string, or None
    if ``value`` is not an ISO-8601 datetime string at all.

    Hazardous == would raise on strict Python-3.9 ``datetime.fromisoformat``:
    a bare trailing ``Z`` OR a fractional-seconds digit-count not in {3, 6}.
    """
    m = _ISO_RE.match(value)
    if not m:
        return None
    frac = m.group(2) or ""
    tz = m.group(3) or ""
    nd = len(frac)
    bare_z = tz == "Z"
    reasons = []
    if bare_z:
        reasons.append("bare_z")
    if 0 < nd < 3:
        reasons.append("short_frac")
    elif 3 < nd < 6:
        reasons.append("short_frac")
    elif nd > 6:
        reasons.append("overlen_frac")
    hazard = bare_z or (nd not in (0, 3, 6))
    return hazard, "+".join(reasons) if reasons else "clean"


def _iter_strings(obj) -> Iterator[str]:
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_strings(v)
    elif isinstance(obj, str):
        yield obj


def audit(tape_dir: str = "tape") -> Dict:
    fam_tot: Dict[str, int] = defaultdict(int)
    fam_haz: Dict[str, int] = defaultdict(int)
    reasons: Dict[str, int] = defaultdict(int)
    examples: Dict[str, Tuple[str, str]] = {}
    total = haz = unparseable = wrapper_fail = 0
    files = lines = 0
    for f in sorted(glob.glob(os.path.join(tape_dir, "*", "dt=*.jsonl"))):
        fam = os.path.basename(os.path.dirname(f))
        files += 1
        with open(f, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                lines += 1
                try:
                    obj = json.loads(ln)
                except Exception:
                    continue  # JSON-validity is L148's gate, not this census
                for s in _iter_strings(obj):
                    c = classify(s)
                    if c is None:
                        continue
                    is_haz, reason = c
                    total += 1
                    fam_tot[fam] += 1
                    if is_haz:
                        haz += 1
                        fam_haz[fam] += 1
                        for r in reason.split("+"):
                            reasons[r] += 1
                        examples.setdefault(reason, (s, f))
                    # Independent cross-check: the sanctioned wrapper must parse
                    # every value (including the hazardous ones) to a tz-aware
                    # UTC datetime. A failure here would break the "wrapper is
                    # the complete fix" claim.
                    try:
                        r = parse_iso_utc(s)
                        if r is None or r.tzinfo is None:
                            wrapper_fail += 1
                    except Exception:
                        wrapper_fail += 1
                        unparseable += 1
    verdict = "URGENT" if haz > 0 else "BENIGN"
    return {
        "tape_dir": tape_dir,
        "files_scanned": files,
        "lines_scanned": lines,
        "total_ts_values": total,
        "hazardous": haz,
        "hazardous_pct": round(100.0 * haz / total, 2) if total else 0.0,
        "clean": total - haz,
        "unparseable": unparseable,
        "parse_iso_utc_failures": wrapper_fail,
        "reason_breakdown": dict(reasons),
        "families_with_hazards": sum(1 for k in fam_haz if fam_haz[k] > 0),
        "per_family": {
            k: {"total": fam_tot[k], "hazardous": fam_haz.get(k, 0)}
            for k in sorted(fam_tot)
        },
        "examples": {k: {"value": v[0], "file": v[1]} for k, v in examples.items()},
        "verdict": verdict,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tape-dir", default="tape")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args(argv)
    rep = audit(args.tape_dir)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0
    print(f"files={rep['files_scanned']} lines={rep['lines_scanned']} "
          f"families_with_ts_hazards={rep['families_with_hazards']}")
    print(f"TOTAL ts values={rep['total_ts_values']}  "
          f"HAZARDOUS={rep['hazardous']} ({rep['hazardous_pct']}%)  "
          f"clean={rep['clean']}  unparseable={rep['unparseable']}  "
          f"parse_iso_utc_failures={rep['parse_iso_utc_failures']}")
    print("reason breakdown:", rep["reason_breakdown"])
    print("examples:")
    for reason, ex in rep["examples"].items():
        print(f"  [{reason}] {ex['value']}  <- {ex['file']}")
    print(f"VERDICT: {rep['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
