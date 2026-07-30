#!/usr/bin/env python3
"""Read-only census: can the RESOLUTION TERMS of each committed Kalshi<->Polymarket Fed
pair be checked from tape alone? (The L214 question.)

L214 (2026-07-28 tape audit, D2): `collection/polymarket_pairs.py::match_fed_pairs` confirms
Kalshi's `*_50plus` bucket — derived from a TITLE magnitude of ">25bps", so a 26-49bp move
settles YES — against Polymarket's `*_50plus` bucket — derived from a `groupItemTitle` of
"50+ bps", so the SAME move settles NO. Pairing them is a defensible collection-time judgment
(each is that venue's own top bucket; a non-25bp-multiple Fed move is near-zero probability),
but `polymarket_macro_pairs.v1` persisted only the winning IDs (`ticker`/`event_id`/
`market_id`), never the matched text or a resolution-basis tag. So for a v1 record the
asymmetry is not "checked and fine" — it is NOT CHECKABLE AT ALL from tape; the only way to
learn of it is to re-read collector source, which is exactly the failure L214 names.

`polymarket_macro_pairs.v2` (2026-07-30) persists per leg: the matched text (`kalshi.title`,
`polymarket.question`/`group_item_title`), a `resolution_basis` (`kalshi_rulebook` /
`uma_oracle` — different adjudicators, so even identical wording is not identical settlement),
and a derived `bucket_terms` verdict (`terms_equivalent` True/False/None, never a guessed True).

This script counts, over committed tape, how much of the record population is auditable and
how much is UNAUDITABLE-BY-CONSTRUCTION (pre-v2). It is DESCRIPTIVE ONLY: no gate, no CI wiring,
no P&L, no verdict, no network, no writes. Numbers here are meant to be quoted in a finding, so
the report is a plain deterministic function of the tape it read (plus `audited_at`).

Run:
    python3 scripts/polymarket_pair_terms_audit.py
    python3 scripts/polymarket_pair_terms_audit.py --tape-dir <dir>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Repo root on sys.path so `core` imports work when run directly as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.io import REPO_ROOT  # noqa: E402

DEFAULT_TAPE_DIR = REPO_ROOT / "tape" / "polymarket_macro_pairs"

# Pair-record schemas of this family. The `..._summary.v1` capture-summary line (L212) is NOT
# a pair record and is counted separately, never as a pair with missing terms.
PAIR_SCHEMAS = ("polymarket_macro_pairs.v1", "polymarket_macro_pairs.v2")
TERMS_BEARING_SCHEMAS = ("polymarket_macro_pairs.v2",)
SUMMARY_SCHEMA = "polymarket_macro_pairs_summary.v1"

# The buckets carrying the known >25bps-vs->=50bps asymmetry.
FIFTY_PLUS_BUCKETS = ("hike_50plus", "cut_50plus")


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def classify_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Per-record terms-auditability classification. Pure, no I/O.

    `has_terms`  -> the record carries a `bucket_terms` block AND the exact TEXT FIELDS that
                    block was derived from, non-empty, on BOTH legs. The Polymarket side of
                    `collection.polymarket_pairs.fed_bucket_terms` reads `group_item_title`
                    and NOTHING ELSE, so that — not `question` — is the evidence predicate
                    here. Keying on `question` too would report `has_terms: True` for a record
                    whose `polymarket_basis` is None: a manufactured "checked" (verifier D3).
                    `poly_question_present` is reported alongside for visibility only; it does
                    not feed `has_terms`.
    `no_terms_block` -> the record has no `bucket_terms` block at all (pre-v2 schema). This is
                    a DIFFERENT kind of ignorance from a v2 block whose verdict came back
                    undecidable, and the two are counted separately (verifier D4).
    `auditable`  -> `has_terms` AND `bucket_terms.terms_equivalent` is an actual verdict
                    (True/False). A None verdict means the collector itself could not derive a
                    basis, so the asymmetry still cannot be checked from tape.

    Tolerant of v2 blocks written before `compares`/`meeting_key_checked` existed (the first
    20 committed v2 lines): both are reported as None, and neither affects any count.
    """
    kalshi = rec.get("kalshi") if isinstance(rec.get("kalshi"), dict) else {}
    poly = rec.get("polymarket") if isinstance(rec.get("polymarket"), dict) else {}
    terms = rec.get("bucket_terms") if isinstance(rec.get("bucket_terms"), dict) else None

    kalshi_text_ok = _nonempty(kalshi.get("title"))
    poly_text_ok = _nonempty(poly.get("group_item_title"))
    has_terms = terms is not None and kalshi_text_ok and poly_text_ok
    equivalent = terms.get("terms_equivalent") if terms is not None else None
    auditable = has_terms and equivalent in (True, False)
    return {
        "schema_version": rec.get("schema_version"),
        "bucket": rec.get("bucket"),
        "kalshi_text_ok": kalshi_text_ok,
        "poly_text_ok": poly_text_ok,                        # group_item_title ONLY (D3)
        "poly_question_present": _nonempty(poly.get("question")),   # visibility only
        "no_terms_block": terms is None,
        "has_terms": has_terms,
        "terms_equivalent": equivalent if has_terms else None,
        "auditable": auditable,
        "terms_compares": terms.get("compares") if terms is not None else None,
        "meeting_key_checked": terms.get("meeting_key_checked") if terms is not None else None,
        "kalshi_resolution_basis": kalshi.get("resolution_basis"),
        "polymarket_resolution_basis": poly.get("resolution_basis"),
    }


def _blank_bucket_row() -> Dict[str, int]:
    return {"n": 0, "n_with_terms": 0, "n_auditable": 0, "n_unauditable": 0,
            "n_terms_equivalent_true": 0, "n_terms_equivalent_false": 0,
            "n_terms_verdict_null": 0, "n_no_terms_block": 0}


def audit(tape_dir: Path = DEFAULT_TAPE_DIR) -> Dict[str, Any]:
    """Scan `tape_dir/dt=*.jsonl` and report terms-auditability. `tape_dir` injectable."""
    tape_dir = Path(tape_dir)
    n_files = n_lines = n_bad_json = 0
    n_pair = n_summary = n_other = 0
    by_schema: Dict[str, int] = defaultdict(int)
    by_bucket: Dict[str, Dict[str, int]] = defaultdict(_blank_bucket_row)
    n_with_terms = n_auditable = 0
    n_eq_true = n_eq_false = n_verdict_null = n_no_block = 0
    n_pre_v2 = 0
    notes_seen: Dict[str, int] = defaultdict(int)
    example_asymmetry: Optional[Dict[str, Any]] = None

    files: List[Path] = []
    if tape_dir.is_dir():
        files = sorted(p for p in tape_dir.glob("dt=*.jsonl") if p.is_file())

    for path in files:
        n_files += 1
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                n_lines += 1
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    n_bad_json += 1
                    continue
                if not isinstance(rec, dict):
                    n_bad_json += 1
                    continue
                schema = rec.get("schema_version")
                if schema == SUMMARY_SCHEMA:
                    n_summary += 1
                    continue
                if schema not in PAIR_SCHEMAS:
                    n_other += 1
                    continue

                n_pair += 1
                by_schema[str(schema)] += 1
                if schema not in TERMS_BEARING_SCHEMAS:
                    n_pre_v2 += 1

                info = classify_record(rec)
                bucket = str(info["bucket"])
                row = by_bucket[bucket]
                row["n"] += 1
                if info["has_terms"]:
                    n_with_terms += 1
                    row["n_with_terms"] += 1
                if info["auditable"]:
                    n_auditable += 1
                    row["n_auditable"] += 1
                else:
                    row["n_unauditable"] += 1
                # D4: "no bucket_terms FIELD AT ALL" (pre-v2 schema) and "block present, verdict
                # undecidable" are opposite kinds of ignorance and are never pooled. The four
                # counters partition the pair population exactly:
                #   n_pair_records == true + false + verdict_null + no_terms_block.
                eq = info["terms_equivalent"]
                if info["no_terms_block"]:
                    n_no_block += 1
                    row["n_no_terms_block"] += 1
                elif eq is True:
                    n_eq_true += 1
                    row["n_terms_equivalent_true"] += 1
                elif eq is False:
                    n_eq_false += 1
                    row["n_terms_equivalent_false"] += 1
                    terms = rec.get("bucket_terms") or {}
                    note = terms.get("note")
                    if _nonempty(note):
                        notes_seen[note] += 1
                    if example_asymmetry is None:
                        example_asymmetry = {
                            "bucket": info["bucket"],
                            "kalshi_title": (rec.get("kalshi") or {}).get("title"),
                            "polymarket_group_item_title": (
                                rec.get("polymarket") or {}).get("group_item_title"),
                            "bucket_terms": terms,
                            "file": path.name,
                        }
                else:
                    # block present, but no usable verdict from tape: either the collector
                    # itself returned None, or the block's leg-text evidence is missing so the
                    # verdict is not independently checkable.
                    n_verdict_null += 1
                    row["n_terms_verdict_null"] += 1

    fifty_plus = {b: dict(by_bucket[b]) for b in FIFTY_PLUS_BUCKETS if b in by_bucket}
    n_fifty_plus = sum(r["n"] for r in fifty_plus.values())
    n_fifty_plus_unauditable = sum(r["n_unauditable"] for r in fifty_plus.values())
    n_fifty_plus_eq_false = sum(r["n_terms_equivalent_false"] for r in fifty_plus.values())

    return {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "tape_dir": str(tape_dir),
        "n_files": n_files,
        "n_lines": n_lines,
        "n_bad_json": n_bad_json,
        "n_pair_records": n_pair,
        "n_summary_records": n_summary,
        "n_other_records": n_other,
        "n_by_schema_version": dict(sorted(by_schema.items())),
        "n_with_terms": n_with_terms,
        "n_without_terms": n_pair - n_with_terms,
        # A record whose asymmetry cannot be checked from tape alone: no terms block / no leg
        # text / a null (undecidable) verdict. Pre-v2 records are ALL in here by construction.
        "n_terms_unauditable": n_pair - n_auditable,
        "n_terms_auditable": n_auditable,
        "n_terms_equivalent_true": n_eq_true,
        "n_terms_equivalent_false": n_eq_false,
        # D4 — two DIFFERENT ignorances, never one number:
        #   n_terms_verdict_null : a `bucket_terms` block exists but yields no verdict from tape
        #                          (collector returned None, or its leg text is missing).
        #   n_no_terms_block     : the record has no `bucket_terms` field at all (pre-v2). It was
        #                          never asked, so it cannot have answered "undecidable".
        "n_terms_verdict_null": n_verdict_null,
        "n_no_terms_block": n_no_block,
        "verdict_partition_note": ("n_pair_records == n_terms_equivalent_true + "
                                   "n_terms_equivalent_false + n_terms_verdict_null + "
                                   "n_no_terms_block (exact partition, both here and per "
                                   "bucket)"),
        "pre_v2": {
            "schema_versions": [s for s in PAIR_SCHEMAS if s not in TERMS_BEARING_SCHEMAS],
            "n_records": n_pre_v2,
            "status": "UNAUDITABLE-BY-CONSTRUCTION",
            "meaning": ("these records persist only the matched IDs, never the matched title/"
                        "groupItemTitle text or a resolution_basis tag, so their two legs' "
                        "settlement terms cannot be compared from tape at all. This is NOT a "
                        "clean bill of health — it is an absence of evidence (L214)."),
        },
        "fifty_plus_buckets": {
            "buckets": FIFTY_PLUS_BUCKETS,
            "n_records": n_fifty_plus,
            "n_unauditable": n_fifty_plus_unauditable,
            "n_terms_equivalent_false": n_fifty_plus_eq_false,
            "per_bucket": fifty_plus,
            "known_asymmetry": ("kalshi title '>25bps' covers [26, inf)bps; polymarket "
                                "'50+ bps' covers [50, inf)bps — a 26-49bp move settles YES "
                                "on one venue and NO on the other"),
        },
        "by_bucket": {b: dict(by_bucket[b]) for b in sorted(by_bucket)},
        "notes_observed": dict(sorted(notes_seen.items())),
        "example_asymmetry": example_asymmetry,
        "scope": "DESCRIPTIVE ONLY — read-only census, no gate, no verdict, no P&L (L214)",
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="L214 terms-auditability census over committed "
                                             "polymarket_macro_pairs tape (read-only)")
    ap.add_argument("--tape-dir", default=str(DEFAULT_TAPE_DIR),
                    help="dir holding polymarket_macro_pairs dt=*.jsonl (default: committed tape)")
    args = ap.parse_args(argv)
    rep = audit(Path(args.tape_dir))
    print(json.dumps(rep, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
