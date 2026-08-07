#!/usr/bin/env python3
"""Read-only settlement-coverage audit: does committed tape resolve these tickers, and from
WHICH family?

Exists because a data-gate is only as strong as the set of families the asserting run looked
at (L300). The S79 idea-stage registration (2026-08-06) recorded "no settlement coverage of
the 2026-08-03 trade day" after checking `tape/settlement_ledger/` alone; the day was in fact
covered by `tape/q51_settlement_cache/settlement.json` and the real gate was a population
one game short of the L41 floor. This script answers the same question against ALL nine
declared sources in `core.settlement_sources` and prints the per-source table, so the claim
that goes into a finding or a registry row is a measured one.

Usage::

    # tickers taken from a tape family's own records
    python3 scripts/settlement_coverage_audit.py \
        --tickers-from tape/kalshi_trades/dt=2026-08-03.jsonl

    # or explicitly
    python3 scripts/settlement_coverage_audit.py --tickers KXMLBGAME-...-LAD,KXBTC-...

Writes `reports/settlement_coverage_audit.json` (override with --out; `--no-write` to skip).
No network, no clock-dependence, no writes under `tape/`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional, Sequence, Set

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.settlement_sources import (  # noqa: E402
    DEFAULT_TAPE_ROOT,
    EMBEDDED_RESULT_FAMILIES,
    SETTLEMENT_SOURCES,
    UNDECLARED_SCAN_RECALL_NOTE,
    resolve_market_results,
    source_files_present,
    undeclared_settlement_dirs,
)

DEFAULT_OUT = os.path.join("reports", "settlement_coverage_audit.json")


def tickers_from_jsonl(path: str, field: str = "ticker") -> List[str]:
    """Distinct values of `field` over a JSONL tape file (sorted, malformed lines skipped)."""
    seen: Set[str] = set()
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                continue
            val = obj.get(field) if isinstance(obj, dict) else None
            if isinstance(val, str) and val:
                seen.add(val)
    return sorted(seen)


def build_report(tickers: Sequence[str], root: str = DEFAULT_TAPE_ROOT) -> dict:
    res = resolve_market_results(tickers, root=root)
    obj = res.to_json_obj()
    obj["sources"] = [
        {
            "name": s.name,
            "path_glob": s.path_glob,
            "kind": s.kind,
            "resolves": s.resolves,
            "declared_tag": s.declared_tag,
            "n_files_present": len(source_files_present(s, root)),
            "hits": res.per_source_hits.get(s.name, 0),
            "note": s.note,
        }
        for s in SETTLEMENT_SOURCES
    ]
    obj["embedded_result_families"] = list(EMBEDDED_RESULT_FAMILIES)
    obj["undeclared_settlement_dirs"] = list(undeclared_settlement_dirs(root))
    obj["summary_line"] = res.coverage_summary()
    return obj


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers-from", default=None,
                    help="JSONL tape file to read tickers from")
    ap.add_argument("--ticker-field", default="ticker")
    ap.add_argument("--tickers", default=None, help="comma-separated ticker list")
    ap.add_argument("--tape-root", default=DEFAULT_TAPE_ROOT)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = ap.parse_args(argv)

    tickers: List[str] = []
    if args.tickers_from:
        tickers.extend(tickers_from_jsonl(args.tickers_from, args.ticker_field))
    if args.tickers:
        tickers.extend(t.strip() for t in args.tickers.split(",") if t.strip())
    if not tickers:
        ap.error("give --tickers-from and/or --tickers")

    rep = build_report(sorted(set(tickers)), root=args.tape_root)
    if not args.no_write:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=2, sort_keys=True)
            fh.write("\n")
    if args.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
        return 0
    print(rep["summary_line"])
    for s in rep["sources"]:
        print(f"  {s['name']:<24} files={s['n_files_present']:<4} hits={s['hits']:<5} "
              f"{s['kind']}")
    if rep["undeclared_settlement_dirs"]:
        print("  UNDECLARED settlement-named dirs: "
              + ", ".join(rep["undeclared_settlement_dirs"]))
    print("  recall: " + UNDECLARED_SCAN_RECALL_NOTE)
    if not args.no_write:
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
