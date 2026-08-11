#!/usr/bin/env python3
"""PUSH-WEDGE AUDIT: how close is any committed file to GitHub's 100,000,000-byte per-file
hard block, and which append path would push it over?

Read-only, fully offline, no network. Computes no P&L, no fill rate, no CI, no edge and no
verdict — this is a repository-health measurement, not a probe (a test asserts those words
never appear in the report).

WHY
---
See `core/push_limits.py` for the mechanism in full. Short version: GitHub rejects a whole
push if any blob in it exceeds 100,000,000 bytes; this repo commits append-only tape, so its
day-files grow monotonically toward that ceiling; and once an oversized blob is in a commit
the branch is permanently unpushable short of a history rewrite (LOOP-QUEUE step 0a's
max-priority incident). It already bit once: the 2026-08-09 Q52 phase-2 backfill measured
`tape/kalshi_trades/dt=2026-07-07.jsonl` at 109,151,185 bytes, was rejected at pre-receive,
and had to drop a whole game by hand before it could commit.

WHAT IT REPORTS
---------------
1. `files` — every TRACKED file at or above the advisory band, with headroom to the hard
   block. Tracked-scoped on purpose: an untracked, mid-write collector file is not something
   a push can trip over, and scanning the filesystem instead would flag it.
2. `families` — per tape family: how many day-files, the largest, and the largest of the last
   7 committed days. A family whose ROUTINE day already runs at a large fraction of the block
   is one busy day away from wedging, and that is a different exposure from one historical
   outlier.
3. `append_exposure` — for each near-limit file, which committed append path targets it: an
   actively-written collector family (a future day could be as large), the LOOP-QUEUE step-0b
   stranded-branch sweep (union-appends into EXISTING day-files, so it can grow a historical
   file), and the Q52/Q54 trade-print backfill (targets specific historical days by name).

Run:
    python3 scripts/push_size_limit_audit.py                # human summary + JSON report
    python3 scripts/push_size_limit_audit.py --json -       # report to stdout
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.push_limits import (  # noqa: E402
    GITHUB_MAX_FILE_BYTES, PUSH_SIZE_GATE_BYTES, PUSH_SIZE_WARN_BYTES, headroom_bytes,
)

SCHEMA_VERSION = "push_size_limit_audit.v1"

# Append paths that can grow an EXISTING committed file (not just create a new one). Each is a
# real, committed writer in this repo; the audit names them rather than implying a generic risk.
APPEND_PATHS: Tuple[Tuple[str, str], ...] = (
    ("collector", "an hourly/daily collector leg appending to the CURRENT day's file "
                  "(`collection/hourly_pass.py`)"),
    ("step0b_sweep", "LOOP-QUEUE step 0b's stranded-branch recovery union-appending missing "
                     "lines into an EXISTING day-file (`scripts/tape_branch_sweep.py`)"),
    ("q52_backfill", "the Q52/Q54 trade-print backfill pulling more games into named "
                     "historical days (`scripts/q52_q54_trades_backfill_phase1.py`)"),
)

# Families whose writer targets named HISTORICAL days rather than only today.
_HISTORICAL_APPEND_FAMILIES = {"kalshi_trades"}


def tracked_files(root: Path = REPO_ROOT) -> List[str]:
    """git-tracked paths, relative POSIX. Empty list if git is unavailable (never raises)."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                             capture_output=True, text=True, check=True).stdout
    except Exception:
        return []
    return [p for p in out.split("\0") if p]


def file_sizes(paths: Sequence[str], root: Path = REPO_ROOT) -> List[Tuple[int, str]]:
    """(size_bytes, relpath) for every path that still exists on disk, largest first.

    A tracked-but-absent path (deleted in the working tree) is skipped, never counted as 0 —
    a fabricated zero would understate the exposure this audit exists to measure.
    """
    out: List[Tuple[int, str]] = []
    for rel in paths:
        try:
            out.append((os.path.getsize(root / rel), rel))
        except OSError:
            continue
    out.sort(reverse=True)
    return out


def _family_of(rel: str) -> Optional[Tuple[str, str]]:
    """(family, day) for a canonical `tape/<family>/dt=<day>.jsonl` path, else None."""
    parts = rel.split("/")
    if len(parts) != 3 or parts[0] != "tape":
        return None
    name = parts[2]
    if not (name.startswith("dt=") and name.endswith(".jsonl")):
        return None
    return parts[1], name[3:-len(".jsonl")]


def family_day_profile(sizes: Sequence[Tuple[int, str]],
                       recent_days: int = 7) -> Dict[str, Dict[str, object]]:
    """Per-family day-file size profile: n_days, largest day, and largest of the last N days.

    `max_recent_bytes` is the forward-looking number: a family whose ROUTINE recent day
    already runs at a large fraction of the block is one busy day from a wedge, which is a
    different (and worse) exposure than a single historical outlier.
    """
    by_family: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
    for size, rel in sizes:
        fd = _family_of(rel)
        if fd is None:
            continue
        by_family[fd[0]].append((fd[1], size))
    out: Dict[str, Dict[str, object]] = {}
    for fam, rows in by_family.items():
        rows.sort()
        recent = rows[-recent_days:]
        mx_day, mx_bytes = max(rows, key=lambda r: r[1])
        rmx_day, rmx_bytes = max(recent, key=lambda r: r[1])
        out[fam] = {
            "n_days": len(rows),
            "first_day": rows[0][0],
            "last_day": rows[-1][0],
            "max_bytes": mx_bytes,
            "max_day": mx_day,
            "max_headroom_bytes": headroom_bytes(mx_bytes),
            "max_recent_bytes": rmx_bytes,
            "max_recent_day": rmx_day,
            "recent_window_days": len(recent),
            "max_fraction_of_block": round(mx_bytes / GITHUB_MAX_FILE_BYTES, 4),
            "max_recent_fraction_of_block": round(rmx_bytes / GITHUB_MAX_FILE_BYTES, 4),
        }
    return out


# A family counts as actively-written when its newest committed day is within this many days
# of the newest day anywhere in tape/. MEASURED from the tape itself rather than read from a
# declared registry on purpose: `tape/universe_sweep/` — the family holding the three largest
# files in the repo — is absent from `scripts/tape_gap_monitor.py::FAMILY_CONFIG`, so a
# registry-driven check would have reported the biggest exposure in the repo as having no
# collector append path at all.
ACTIVE_FAMILY_LAG_DAYS = 2


def _newest_day(families: Mapping[str, Dict[str, object]]) -> Optional[str]:
    days = [str(v["last_day"]) for v in families.values() if v.get("last_day")]
    return max(days) if days else None


def _active_families(families: Mapping[str, Dict[str, object]],
                     lag_days: int = ACTIVE_FAMILY_LAG_DAYS) -> set:
    """Families whose newest committed day is within `lag_days` of the newest day anywhere.

    Date arithmetic on the ISO day strings, not on file mtimes: a fresh clone rewrites every
    mtime, so an mtime-based liveness read would call every family active.
    """
    newest = _newest_day(families)
    if newest is None:
        return set()
    from datetime import date
    def _d(s: str):
        y, m, d = (int(x) for x in s.split("-"))
        return date(y, m, d)
    try:
        cutoff = _d(newest).toordinal() - int(lag_days)
    except Exception:
        return set()
    out = set()
    for fam, v in families.items():
        try:
            if _d(str(v["last_day"])).toordinal() >= cutoff:
                out.add(fam)
        except Exception:
            continue
    return out


def append_exposure(rel: str, families: Mapping[str, Dict[str, object]],
                    active: Optional[set] = None) -> List[str]:
    """Which named append paths can grow THIS file. Honest about not knowing: a non-tape file
    gets an empty list rather than a guessed one."""
    fd = _family_of(rel)
    if fd is None:
        return []
    fam, _day = fd
    if active is None:
        active = _active_families(families)
    out = ["step0b_sweep"]                       # union-appends into any existing day-file
    if fam in active:
        out.append("collector")                  # a future day of this family can be as large
    if fam in _HISTORICAL_APPEND_FAMILIES:
        out.append("q52_backfill")               # targets named historical days
    return sorted(set(out))


def build_report(root: Path = REPO_ROOT, recent_days: int = 7) -> Dict[str, object]:
    tracked = tracked_files(root)
    sizes = file_sizes(tracked, root)
    families = family_day_profile(sizes, recent_days=recent_days)
    active = _active_families(families)
    flagged = [
        {
            "path": rel,
            "bytes": size,
            "headroom_bytes": headroom_bytes(size),
            "fraction_of_block": round(size / GITHUB_MAX_FILE_BYTES, 4),
            "at_or_over_gate": size >= PUSH_SIZE_GATE_BYTES,
            "over_hard_block": size >= GITHUB_MAX_FILE_BYTES,
            "append_paths": append_exposure(rel, families, active),
        }
        for size, rel in sizes if size >= PUSH_SIZE_WARN_BYTES
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "scripts/push_size_limit_audit.py",
        "report_class": "REPOSITORY HEALTH (no P&L, no CI, no registry flip)",
        "hard_block_bytes": GITHUB_MAX_FILE_BYTES,
        "gate_bytes": PUSH_SIZE_GATE_BYTES,
        "warn_bytes": PUSH_SIZE_WARN_BYTES,
        "n_tracked_files": len(tracked),
        "n_measured_files": len(sizes),
        "total_tracked_bytes": sum(s for s, _ in sizes),
        "largest_bytes": sizes[0][0] if sizes else 0,
        "largest_path": sizes[0][1] if sizes else None,
        "min_headroom_bytes": headroom_bytes(sizes[0][0]) if sizes else GITHUB_MAX_FILE_BYTES,
        "n_at_or_over_warn": len(flagged),
        "n_at_or_over_gate": sum(1 for f in flagged if f["at_or_over_gate"]),
        "n_over_hard_block": sum(1 for f in flagged if f["over_hard_block"]),
        "files": flagged,
        "families": families,
        "active_families": sorted(active),
        "newest_tape_day": _newest_day(families),
        "append_path_glossary": {k: v for k, v in APPEND_PATHS},
        "repair_note": ("append-only-safe repair: STOP APPENDING to the offending path and "
                        "shard the family's next writes into a new file; never truncate, "
                        "rewrite or reorder committed tape lines to get under the limit"),
    }


def summarize(rep: Mapping[str, object]) -> str:
    lines = [
        f"push-size audit: {rep['n_measured_files']} tracked file(s), "
        f"{rep['total_tracked_bytes'] / 1e9:.3f} GB",
        f"  hard block {rep['hard_block_bytes']:,} B · gate {rep['gate_bytes']:,} B · "
        f"warn {rep['warn_bytes']:,} B",
        f"  largest: {rep['largest_path']} = {rep['largest_bytes']:,} B "
        f"(headroom {rep['min_headroom_bytes']:,} B)",
        f"  at/over warn: {rep['n_at_or_over_warn']} · at/over gate: "
        f"{rep['n_at_or_over_gate']} · over hard block: {rep['n_over_hard_block']}",
    ]
    for f in list(rep.get("files") or [])[:10]:
        lines.append(f"    {f['bytes']:>12,} B  headroom {f['headroom_bytes']:>12,} B  "
                     f"{f['path']}  [{','.join(f['append_paths']) or 'no-named-append-path'}]")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--recent-days", type=int, default=7)
    ap.add_argument("--json", default=str(REPO_ROOT / "reports" / "push_size_limit_audit.json"),
                    help="report path, or '-' for stdout")
    args = ap.parse_args(argv)

    rep = build_report(recent_days=args.recent_days)
    text = json.dumps(rep, indent=2, sort_keys=True)
    if args.json == "-":
        print(text)
    else:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"[push-size] report -> {out}")
    print(summarize(rep))
    # Exit 1 when something is already AT or OVER this repo's own gate — the gating decision
    # itself lives in scripts/invariants.py; this is the standalone measurement tool's echo.
    return 1 if rep["n_at_or_over_gate"] else 0


if __name__ == "__main__":
    sys.exit(main())
