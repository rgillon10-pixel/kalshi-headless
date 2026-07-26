#!/usr/bin/env python3
"""orderbook_depth_hollow_ladder_audit.py — idle-run (policy c) data-quality deep-dive.

Question: `tape/orderbook_depth/` is the largest tape family by volume (Q46) and the one
most exposed to the VPS `:23` collector-leg death (Q44/L117/L118/L127/L129/L156/L157). Those
existing detectors all measure ABSENCE (staleness, under-capture). This script measures a
different failure that survives even when a pass runs and returns HTTP 200: a record that is
present, well-formed, tagged `real_ask`/`real_bid`, and completely HOLLOW — `yes_bids=[]`,
`no_bids=[]`, both sides' best price/size null, `depth=0` — because the ticker it asked about
had already closed by the time the fetch reached it. `completeness_ok` (computed in
`collection/orderbook_depth.py`, never persisted onto the tape line itself) cannot see this:
a 200-OK empty-book response is not a fetch failure.

Two-agent provenance (2026-07-26): a `tape-auditor` subagent found the phenomenon and an
independent `verifier` subagent re-derived every number from the raw tape, REFUTING several
of the auditor's causal claims (a "cloud-leg" attribution was collinear with runway-to-close,
not causal — a :41-minute cloud capture with long runway is 0% hollow; a "constant fetch
throughput" claim understated its own variance) while confirming the core mechanism (runway-
to-close, not collector identity, predicts hollow rate) and finding TWO further failure modes
the auditor missed: (1) a captures's `captured_at` is a pass-START stamp replicated onto every
record, so a late-pass fetch's real fetch time can trail its recorded timestamp by the whole
pass duration (kb/lessons L168); (2) some hollow crypto captures are fetched from a STALE
post-close ticker universe (the pass's ticker discovery step ran before the hour rolled, so it
targets an already-closed contract) rather than an in-flight fetch that ran out of runway
mid-pass — a second, distinct mechanism from pass-duration overrun (kb/lessons L169's sibling
finding; see the finding doc). This script is the reproducer both agents were missing.

What it computes (read-only, no network, offline-testable):
  1. Basic validity over every committed line: malformed-JSON count, schema key-set
     uniformity, duplicate (capture_id, ticker) pairs, crossed two-sided books.
  2. Hollow-record rate, overall and split crypto (KXBTC/KXETH) vs non-crypto, per day.
  3. Per-record runway-to-close for crypto tickers (via
     core.timeutil.parse_crypto_hour_token_close_utc on the ticker's date+hour token),
     bucketed, to show hollow rate rising as runway shrinks and staying high past close —
     the mechanism, not a collector-identity story.
  4. A collector-leg cross-check via `scripts/tape_gap_monitor.py::collector_bucket` (the
     REAL leg-attribution function, not a hand-rolled minute rule) — reported only as a
     descriptive cross-tab, explicitly NOT causal (see L169: leg and runway are collinear
     under today's cron schedule, so this table cannot distinguish "cloud is worse" from
     "the cloud slot has less runway").
  5. Fetch-order contiguity: whether hollow crypto records within one capture form a
     contiguous suffix (the truncation signature) — reporting exceptions by name rather than
     asserting universally, because a deep-OTM wing can legitimately be empty on its own
     (kb/lessons L23) independent of any truncation.

No strategy claim, no P&L, no registry change. Every price on the tape is already tagged by
its own collector; this script adds no new price_source_tag and performs no yes_ask or no_ask
arithmetic (Hard Rule #3 N/A — it counts and buckets, it does not price anything).

Run:
    python scripts/orderbook_depth_hollow_ladder_audit.py
    python scripts/orderbook_depth_hollow_ladder_audit.py --tape-dir tape/orderbook_depth \
        --json-out /tmp/depth_audit.json
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.io import REPO_ROOT  # noqa: E402
from core.timeutil import parse_crypto_hour_token_close_utc, parse_iso_utc  # noqa: E402

DEFAULT_TAPE_DIR = REPO_ROOT / "tape" / "orderbook_depth"
_TAPE_GAP_MONITOR_PATH = REPO_ROOT / "scripts" / "tape_gap_monitor.py"

CRYPTO_PREFIXES = ("KXBTC", "KXETH")

# Runway-to-close buckets, seconds. A negative runway means the record was fetched AT OR
# AFTER the ticker's own recorded close time (the stale-post-close-universe mechanism);
# everything else is "still open when fetched" (the in-flight-overrun mechanism, when hollow).
RUNWAY_BUCKETS: List[Tuple[str, Optional[float], Optional[float]]] = [
    ("post-close (runway < 0)", None, 0.0),
    ("0-5 min", 0.0, 300.0),
    ("5-15 min", 300.0, 900.0),
    ("15-30 min", 900.0, 1800.0),
    ("30-45 min", 1800.0, 2700.0),
    ("45-60 min", 2700.0, 3600.0),
    ("60+ min", 3600.0, None),
]


def _load_tape_gap_monitor(path: Path = _TAPE_GAP_MONITOR_PATH):
    """Import scripts/tape_gap_monitor.py by path (scripts/ is not a package) — mirrors
    scripts/invariants.py::_load_tape_gap_monitor so leg-bucket logic is never duplicated."""
    spec = importlib.util.spec_from_file_location("_odha_tape_gap_monitor", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def is_hollow(rec: Dict[str, Any]) -> bool:
    return rec.get("yes_bids") == [] and rec.get("no_bids") == []


def is_crypto_ticker(ticker: str) -> bool:
    return ticker.startswith(CRYPTO_PREFIXES)


def crypto_close_time(ticker: str) -> Optional[datetime]:
    """Parse the ticker's embedded date+hour token (2nd '-'-delimited segment,
    e.g. '26JUL2221' in 'KXBTC-26JUL2221-B70250') into its UTC close instant."""
    parts = ticker.split("-")
    if len(parts) < 2:
        return None
    return parse_crypto_hour_token_close_utc(parts[1])


def _runway_bucket(seconds: Optional[float]) -> str:
    if seconds is None:
        return "unparseable-token"
    for label, lo, hi in RUNWAY_BUCKETS:
        if (lo is None or seconds >= lo) and (hi is None or seconds < hi):
            return label
    return "unparseable-token"  # pragma: no cover - RUNWAY_BUCKETS is exhaustive


def load_records(tape_dir: Path, max_day: Optional[str] = None
                  ) -> Tuple[List[Dict[str, Any]], int]:
    """Returns (records with day/line_no attached, malformed_line_count). File order is
    preserved within each day (list order == append order == fetch order within a pass).

    `max_day` (optional, 'YYYY-MM-DD') restricts the scan to `dt=<date>.jsonl` files on or
    before that day. A test pinning exact counts against the real, live-growing tape MUST use
    this — the CURRENT day's file is still being appended to by ongoing hourly passes, so an
    unpinned scan is an L140-style time bomb; freeze to the last FULLY CLOSED day instead."""
    records: List[Dict[str, Any]] = []
    malformed = 0
    for path in sorted(glob.glob(str(tape_dir / "dt=*.jsonl"))):
        day = Path(path).stem.split("=", 1)[1]
        if max_day is not None and day > max_day:
            continue
        with open(path, "r") as f:
            for line_no, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                rec["_day"] = day
                rec["_line_no"] = line_no
                records.append(rec)
    return records, malformed


def audit_validity(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    schema_keysets = Counter()
    dup_keys: Counter = Counter()
    crossed = 0
    for rec in records:
        keys = frozenset(k for k in rec.keys() if not k.startswith("_"))
        schema_keysets[keys] += 1
        dup_keys[(rec.get("capture_id"), rec.get("ticker"))] += 1
        by, ba = rec.get("best_yes_bid"), rec.get("best_yes_ask")
        bny, bna = rec.get("best_no_bid"), rec.get("best_no_ask")
        if by is not None and ba is not None and by > ba:
            crossed += 1
        if bny is not None and bna is not None and bny > bna:
            crossed += 1
    duplicate_pairs = sum(1 for count in dup_keys.values() if count > 1)
    return {
        "total_lines": len(records),
        "distinct_schema_shapes": len(schema_keysets),
        "duplicate_capture_ticker_pairs": duplicate_pairs,
        "crossed_book_count": crossed,
    }


def audit_hollow_rates(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    per_day: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"crypto_total": 0, "crypto_hollow": 0, "other_total": 0, "other_hollow": 0}
    )
    total_hollow = 0
    crypto_hollow = 0
    for rec in records:
        day = rec["_day"]
        hollow = is_hollow(rec)
        total_hollow += hollow
        if is_crypto_ticker(rec.get("ticker", "")):
            per_day[day]["crypto_total"] += 1
            per_day[day]["crypto_hollow"] += hollow
            crypto_hollow += hollow
        else:
            per_day[day]["other_total"] += 1
            per_day[day]["other_hollow"] += hollow
    return {
        "total_records": len(records),
        "total_hollow": total_hollow,
        "crypto_hollow": crypto_hollow,
        "non_crypto_hollow": total_hollow - crypto_hollow,
        "per_day": dict(sorted(per_day.items())),
    }


def audit_runway_buckets(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """Crypto-only: hollow rate by runway-to-close bucket. This is the mechanism table —
    it should show hollow rate near-zero at long runway and near-100% past close/short
    runway, regardless of which collector leg produced the capture (see L169)."""
    buckets: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "hollow": 0})
    for rec in records:
        ticker = rec.get("ticker", "")
        if not is_crypto_ticker(ticker):
            continue
        close = crypto_close_time(ticker)
        if close is None:
            continue
        captured_at = parse_iso_utc(rec["captured_at"])
        runway = (close - captured_at).total_seconds()
        label = _runway_bucket(runway)
        buckets[label]["total"] += 1
        buckets[label]["hollow"] += is_hollow(rec)
    return dict(buckets)


def audit_leg_crosstab(records: List[Dict[str, Any]], tgm) -> Dict[str, Dict[str, int]]:
    """Descriptive only (see L169): collector leg is inferred purely from captured_at's
    minute-of-hour via the project's OWN tape_gap_monitor.collector_bucket, never a
    hand-rolled rule. Do not read a 'worse leg' conclusion off this table alone — cross-check
    against audit_runway_buckets, since leg and runway are collinear under the current cron
    schedule."""
    buckets: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "hollow": 0})
    for rec in records:
        if not is_crypto_ticker(rec.get("ticker", "")):
            continue
        captured_at = parse_iso_utc(rec["captured_at"])
        leg = tgm.collector_bucket(captured_at)
        buckets[leg]["total"] += 1
        buckets[leg]["hollow"] += is_hollow(rec)
    return dict(buckets)


def audit_suffix_contiguity(records: List[Dict[str, Any]],
                             crypto_only: bool = True) -> Dict[str, Any]:
    """Within each capture_id, are hollow records a contiguous suffix of fetch order? A
    genuine truncation-in-flight produces exactly that shape. A named exception (a legitimate
    deep-OTM/settled wing per L23) breaks it without meaning the capture was truncated."""
    by_capture: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for rec in records:
        ticker = rec.get("ticker", "")
        if crypto_only and not is_crypto_ticker(ticker):
            continue
        by_capture[rec["capture_id"]].append(rec)

    violations: List[Dict[str, Any]] = []
    partially_empty = 0
    for capture_id, recs in by_capture.items():
        hollow_flags = [is_hollow(r) for r in recs]
        if not any(hollow_flags) or all(hollow_flags):
            continue
        partially_empty += 1
        first_hollow = hollow_flags.index(True)
        tail_non_hollow = [i for i, h in enumerate(hollow_flags) if i > first_hollow and not h]
        if tail_non_hollow:
            violations.append({
                "capture_id": capture_id,
                "first_hollow_index": first_hollow,
                "non_hollow_after_first_hollow": len(tail_non_hollow),
                "example_ticker": recs[tail_non_hollow[0]].get("ticker"),
            })
    return {
        "partially_empty_captures": partially_empty,
        "suffix_violations": violations,
    }


def run_audit(tape_dir: Path, max_day: Optional[str] = None) -> Dict[str, Any]:
    records, malformed = load_records(tape_dir, max_day=max_day)
    tgm = _load_tape_gap_monitor()
    return {
        "malformed_lines": malformed,
        "validity": audit_validity(records),
        "hollow_rates": audit_hollow_rates(records),
        "runway_buckets": audit_runway_buckets(records),
        "leg_crosstab_descriptive_only": audit_leg_crosstab(records, tgm),
        "suffix_contiguity_crypto_only": audit_suffix_contiguity(records, crypto_only=True),
    }


def format_report(report: Dict[str, Any]) -> str:
    lines = ["ORDERBOOK_DEPTH HOLLOW-LADDER AUDIT", "=" * 60]
    v = report["validity"]
    lines.append(f"lines={v['total_lines']} malformed={report['malformed_lines']} "
                 f"schema_shapes={v['distinct_schema_shapes']} "
                 f"dup_capture_ticker_pairs={v['duplicate_capture_ticker_pairs']} "
                 f"crossed_books={v['crossed_book_count']}")
    h = report["hollow_rates"]
    lines.append(f"total_hollow={h['total_hollow']}/{h['total_records']} "
                 f"crypto_hollow={h['crypto_hollow']} non_crypto_hollow={h['non_crypto_hollow']}")
    lines.append("-- runway-to-close buckets (crypto only, descriptive of MECHANISM) --")
    for label, _, _ in RUNWAY_BUCKETS:
        b = report["runway_buckets"].get(label, {"total": 0, "hollow": 0})
        if b["total"]:
            lines.append(f"  {label:24s} total={b['total']:6d} hollow={b['hollow']:6d} "
                         f"({100.0 * b['hollow'] / b['total']:.1f}%)")
    lines.append("-- collector-leg crosstab (DESCRIPTIVE ONLY, see L169 collinearity note) --")
    for leg, b in sorted(report["leg_crosstab_descriptive_only"].items()):
        if b["total"]:
            lines.append(f"  {leg:8s} total={b['total']:6d} hollow={b['hollow']:6d} "
                         f"({100.0 * b['hollow'] / b['total']:.1f}%)")
    sc = report["suffix_contiguity_crypto_only"]
    lines.append(f"partially-empty captures={sc['partially_empty_captures']} "
                 f"suffix-violations={len(sc['suffix_violations'])}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tape-dir", default=str(DEFAULT_TAPE_DIR))
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--max-day", default=None,
                        help="Restrict to dt=<date>.jsonl files on or before this day "
                             "('YYYY-MM-DD'). Use to freeze a reproducible historical slice.")
    args = parser.parse_args(argv)

    report = run_audit(Path(args.tape_dir), max_day=args.max_day)
    print(format_report(report))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
