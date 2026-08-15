#!/usr/bin/env python3
"""collector_gate_reachability_rederive.py — INDEPENDENT re-derivation of the 2026-08-15
gate-hour reachability finding. Read-only, offline, no network.

WHY THIS EXISTS. The two-agent verdict rule (LOOP-QUEUE.md protocol v3 step 5) requires an
independent `verifier` before a load-bearing number is recorded. No `Task`/subagent tool
exists in this harness (the L287/L288/L290/L291/L295/L308/L313/L325 precedent), so the
sanctioned REDUNDANCY fallback runs instead: a second implementation that shares NO code with
`scripts/tape_gap_monitor.py::gate_hour_reachability`.

  * own JSONL reader (`json.loads` per line, not the primary's streaming regex scan),
  * own ISO-8601 -> datetime parser by string slicing, pinned against `core.timeutil` on real
    committed timestamps in `tests/test_collector_gate_reachability_rederive.py`,
  * own per-capture_id earliest-instant fold, own day-window selection, own histogram,
  * own gate-constant regex over `collection/hourly_pass.py`.

Redundancy is NOT verification: it cannot catch an error both implementations share, and it is
never reported as a verifier confirmation.

Run:
    python3 scripts/collector_gate_reachability_rederive.py
    python3 scripts/collector_gate_reachability_rederive.py --first dt=2026-07-26 --last dt=2026-08-14
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

FROZEN_FIRST_DEFAULT = "dt=2026-07-26"
FROZEN_LAST_DEFAULT = "dt=2026-08-14"


def iso_to_utc(s: str) -> Optional[datetime]:
    """Own tolerant ISO-8601 -> aware-UTC parser, by slicing. Returns None on anything it
    cannot read (never a guessed timestamp). Deliberately shares no code with core.timeutil;
    the test suite pins it AGAINST core.timeutil on real committed strings."""
    if not isinstance(s, str) or len(s) < 19 or s[4] != "-" or s[7] != "-" or s[10] != "T":
        return None
    try:
        y, mo, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
        hh, mi, ss = int(s[11:13]), int(s[14:16]), int(s[17:19])
    except ValueError:
        return None
    micro = 0
    rest = s[19:]
    if rest.startswith("."):
        frac = ""
        for ch in rest[1:]:
            if not ch.isdigit():
                break
            frac += ch
        if frac:
            micro = int((frac + "000000")[:6])
        rest = rest[1 + len(frac):]
    off = timedelta(0)
    if rest and rest[0] in "+-" and len(rest) >= 6:
        sign = 1 if rest[0] == "+" else -1
        try:
            off = sign * timedelta(hours=int(rest[1:3]), minutes=int(rest[4:6]))
        except ValueError:
            return None
    try:
        return datetime(y, mo, d, hh, mi, ss, micro, tzinfo=timezone.utc) - off
    except ValueError:
        return None


def day_stems(tape_root: Path, family: str) -> List[str]:
    """Ascending `dt=YYYY-MM-DD` stems of the family's regular day files."""
    fam = tape_root / family
    if not fam.is_dir():
        return []
    out = []
    for p in sorted(fam.iterdir()):
        if p.is_file() and re.fullmatch(r"dt=\d{4}-\d{2}-\d{2}\.jsonl", p.name):
            out.append(p.stem)
    return sorted(out)


def pass_start_hours(tape_root: Path, family: str, stems: List[str]) -> Tuple[int, Dict[int, int]]:
    """(n_passes, hour histogram) of pass-START instants: the EARLIEST captured_at per
    distinct capture_id, read line-by-line through json.loads."""
    earliest: Dict[str, datetime] = {}
    for stem in stems:
        path = tape_root / family / f"{stem}.jsonl"
        if not path.is_file():
            continue
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                ca = rec.get("captured_at")
                ts = iso_to_utc(ca) if isinstance(ca, str) else None
                if ts is None:
                    continue
                key = rec.get("capture_id") or ca
                if not isinstance(key, str):
                    key = ca
                prev = earliest.get(key)
                if prev is None or ts < prev:
                    earliest[key] = ts
    hist: Dict[int, int] = {}
    for ts in earliest.values():
        hist[ts.hour] = hist.get(ts.hour, 0) + 1
    return len(earliest), hist


def gate_hour_from_source(repo_root: Path, const: str) -> Optional[int]:
    """Own regex read of a `<CONST> = <int>` gate hour out of collection/hourly_pass.py."""
    src = (repo_root / "collection" / "hourly_pass.py").read_text(encoding="utf-8")
    m = re.search(rf"(?m)^{re.escape(const)}\s*=\s*(\d+)", src)
    return int(m.group(1)) if m else None


def family_day_facts(tape_root: Path, family: str) -> Dict[str, Any]:
    """Committed day coverage + line counts for a family (its own count, not tgm's)."""
    stems = day_stems(tape_root, family)
    lines = {}
    for stem in stems:
        with open(tape_root / family / f"{stem}.jsonl", "r", encoding="utf-8") as fh:
            lines[stem] = sum(1 for ln in fh if ln.strip())
    return {"n_days": len(stems), "days": stems, "lines_per_day": lines,
            "n_lines": sum(lines.values())}


def rederive(tape_root: Optional[Path] = None,
             first: str = FROZEN_FIRST_DEFAULT,
             last: str = FROZEN_LAST_DEFAULT,
             asof_day: Optional[str] = None) -> Dict[str, Any]:
    tape_root = (REPO_ROOT / "tape") if tape_root is None else tape_root
    frozen = [s for s in day_stems(tape_root, "sports_pairs") if first <= s <= last]

    witnesses: Dict[str, Any] = {}
    for fam in ("sports_pairs", "crypto_hourly", "perp_tape"):
        n, hist = pass_start_hours(tape_root, fam, frozen)
        witnesses[fam] = {"n_pass_instants": n,
                          "observed_hours": {str(k): v for k, v in sorted(hist.items())}}

    gates = {c: gate_hour_from_source(REPO_ROOT, c) for c in
             ("SETTLEMENT_LEDGER_UTC_HOUR", "ANOMALY_SWEEP_UTC_HOUR", "ECON_PRINTS_UTC_HOUR",
              "WEATHER_ACTUALS_UTC_HOUR", "FORECAST_COLLECTOR_UTC_HOUR")}

    prim = witnesses["sports_pairs"]["observed_hours"]
    per_gate = {}
    for const, h in gates.items():
        if h is None:
            continue
        at = int(prim.get(str(h), 0))
        per_gate[const] = {"gate_hour_utc": h, "n_at_gate_hour": at,
                           "reachable": at > 0}

    sl = family_day_facts(tape_root, "settlement_ledger")
    last_day = sl["days"][-1][3:] if sl["days"] else None
    asof = asof_day or (day_stems(tape_root, "sports_pairs")[-1][3:]
                        if day_stems(tape_root, "sports_pairs") else None)
    days_frozen = None
    if last_day and asof:
        d0, d1 = iso_to_utc(last_day + "T00:00:00+00:00"), iso_to_utc(asof + "T00:00:00+00:00")
        if d0 and d1:
            days_frozen = (d1 - d0).days

    return {
        "schema_version": "collector_gate_reachability_rederive.v1",
        "note": ("REDUNDANCY, not verification: an independent second implementation. It "
                 "cannot catch an error both implementations share."),
        "frozen_window": {"first": first, "last": last, "n_days": len(frozen), "days": frozen},
        "witnesses": witnesses,
        "gate_constants": gates,
        "per_gate": per_gate,
        "settlement_ledger": {**sl, "last_day": last_day, "asof_day": asof,
                              "days_since_last_capture": days_frozen},
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tape-root", default=str(REPO_ROOT / "tape"))
    ap.add_argument("--first", default=FROZEN_FIRST_DEFAULT)
    ap.add_argument("--last", default=FROZEN_LAST_DEFAULT)
    args = ap.parse_args(argv)
    out = rederive(Path(args.tape_root), args.first, args.last)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
