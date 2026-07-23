#!/usr/bin/env python3
"""tape_archive.py — move COLD bulk-family dt files out of the git working tree, keeping
their provenance (sha256, line count, size) in a committed per-family manifest.

Context: ops/storage-migration.md (Ryan-approved 2026-07-22). tape/ is 1.1 GB and three
families (universe_sweep, orderbook_depth, sports_pairs) are 83% of it; git-as-persistence
stops scaling months before the planned end of the collection campaign. The hot window
(newest --age-days of every family) STAYS in git so collectors and every scheduled probe
see no change; only cold dt files of the named bulk families migrate to --archive-root
(VPS disk, mirrored nightly to object storage per the runbook).

Safety posture — nothing here can lose a byte:
  * manifest line (sha256 + line count + size) is appended and flushed BEFORE the copy;
  * the copy is re-hashed and must match before the source is deleted;
  * any mismatch aborts that file, leaving source + partial copy for inspection;
  * DRY-RUN by default — --apply to act; idempotent across reruns (manifested files skip,
    identical pre-existing copies verify-and-continue).
  * never calls git — the runbook reviews and commits the working-tree deletions.

Usage (VPS):
    python scripts/tape_archive.py                       # dry-run report
    python scripts/tape_archive.py --apply               # archive cold files
    python scripts/tape_archive.py --verify              # re-hash every archived file vs manifest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TAPE_ROOT = REPO_ROOT / "tape"
DEFAULT_ARCHIVE_ROOT = Path("/root/tape-archive")
DEFAULT_AGE_DAYS = 14

# Only these families ever migrate — everything else stays fully in git. Growing this set
# is a Ryan decision (same bar as the original >50MB trigger in tape/README.md).
BULK_FAMILIES = ("universe_sweep", "orderbook_depth", "sports_pairs")

MANIFEST_NAME = "ARCHIVE-MANIFEST.jsonl"


def _sha256_and_lines(path: Path) -> tuple:
    h = hashlib.sha256()
    lines = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            lines += chunk.count(b"\n")
    return h.hexdigest(), lines


def _dt_of(path: Path) -> Optional[date]:
    name = path.name
    if not (name.startswith("dt=") and name.endswith(".jsonl")):
        return None
    try:
        return date.fromisoformat(name[3:-6])
    except ValueError:
        return None


def _load_manifested(manifest: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if manifest.exists():
        with manifest.open() as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    out[rec["file"]] = rec
                except (json.JSONDecodeError, KeyError):
                    continue
    return out


def archive_pass(tape_root: Path, archive_root: Path, age_days: int,
                 apply: bool, now: Optional[datetime] = None) -> Dict[str, Any]:
    ts = now if now is not None else datetime.now(timezone.utc)
    cutoff = ts.date() - timedelta(days=age_days)
    summary: Dict[str, Any] = {"apply": apply, "cutoff": cutoff.isoformat(),
                               "archived": [], "skipped_manifested": 0,
                               "kept_hot": 0, "errors": []}
    for family in BULK_FAMILIES:
        fam_dir = tape_root / family
        if not fam_dir.is_dir():
            continue
        manifest = fam_dir / MANIFEST_NAME
        manifested = _load_manifested(manifest)
        summary["skipped_manifested"] += sum(
            1 for rel in manifested if not (tape_root / rel).exists())
        for f in sorted(fam_dir.glob("dt=*.jsonl")):
            d = _dt_of(f)
            if d is None or d >= cutoff:
                summary["kept_hot"] += 1
                continue
            rel = f"{family}/{f.name}"
            digest, lines = _sha256_and_lines(f)
            size = f.stat().st_size
            if not apply:
                summary["archived"].append({"file": rel, "sha256": digest,
                                            "n_lines": lines, "bytes": size,
                                            "dry_run": True})
                continue
            dest_dir = archive_root / family
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f.name
            rec = {"file": rel, "sha256": digest, "n_lines": lines, "bytes": size,
                   "archived_at": ts.isoformat(), "archive_root": str(archive_root)}
            if rel not in manifested:
                with manifest.open("a") as mh:
                    mh.write(json.dumps(rec, sort_keys=True) + "\n")
                    mh.flush()
            if dest.exists():
                dest_digest, _ = _sha256_and_lines(dest)
            else:
                shutil.copy2(f, dest)
                dest_digest, _ = _sha256_and_lines(dest)
            if dest_digest != digest:
                summary["errors"].append(
                    {"file": rel, "error": f"copy hash mismatch ({dest_digest[:12]} != {digest[:12]}) — source kept"})
                continue
            f.unlink()
            summary["archived"].append(rec)
    return summary


def verify(tape_root: Path, archive_root: Path) -> Dict[str, Any]:
    """Re-hash every archived file against its committed manifest line."""
    out: Dict[str, Any] = {"ok": 0, "missing": [], "mismatched": []}
    for family in BULK_FAMILIES:
        manifest = tape_root / family / MANIFEST_NAME
        for rel, rec in _load_manifested(manifest).items():
            archived = archive_root / rel
            in_git = tape_root / rel
            target = archived if archived.exists() else (in_git if in_git.exists() else None)
            if target is None:
                out["missing"].append(rel)
                continue
            digest, _ = _sha256_and_lines(target)
            if digest == rec["sha256"]:
                out["ok"] += 1
            else:
                out["mismatched"].append(rel)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Archive cold bulk-family tape out of git (manifest stays).")
    ap.add_argument("--tape-root", default=str(DEFAULT_TAPE_ROOT))
    ap.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    ap.add_argument("--age-days", type=int, default=DEFAULT_AGE_DAYS)
    ap.add_argument("--apply", action="store_true", help="actually move files (default: dry-run).")
    ap.add_argument("--verify", action="store_true", help="re-hash archived files vs manifests and exit.")
    args = ap.parse_args(argv)
    tape_root, archive_root = Path(args.tape_root), Path(args.archive_root)
    if args.verify:
        rep = verify(tape_root, archive_root)
        print(json.dumps(rep, indent=2, sort_keys=True))
        return 0 if not rep["missing"] and not rep["mismatched"] else 1
    rep = archive_pass(tape_root, archive_root, args.age_days, apply=args.apply)
    print(json.dumps(rep, indent=2, sort_keys=True))
    if not args.apply and rep["archived"]:
        print(f"\n[tape_archive] DRY-RUN: {len(rep['archived'])} cold files would migrate. "
              f"Re-run with --apply on the VPS (see ops/storage-migration.md).", file=sys.stderr)
    return 0 if not rep["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
