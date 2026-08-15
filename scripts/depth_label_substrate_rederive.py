#!/usr/bin/env python3
"""Independent re-derivation of `scripts/depth_label_substrate_census.py`'s load-bearing
numbers — REDUNDANCY, NOT VERIFICATION.

This harness carries no `Task`/`verifier` subagent (the L287/L288/L290/L291/L295/L308/L313/
L325/L338 precedent), so the two-agent rule could not be satisfied for the 2026-08-15 census.
The sanctioned fallback is a second implementation that shares NO code with the first and
does not import it, so a bug has to occur twice, identically, to survive. Anything this
script confirms is still PROVISIONAL until an independent agent re-runs it.

Deliberate implementation differences (a copy would prove nothing):
  * does NOT import `core.settlement_sources` — it reads the three source shapes directly
    from their own record grammars (JSONL `result` field / cache `markets` map / the
    `previous_settlement.results` map embedded in `crypto_hourly`);
  * counts snapshots with a single streaming pass keyed by `(ticker)` built from `str.split`
    on the raw line's `"ticker":"..."` field rather than a full `json.loads` per record;
  * derives the unit by splitting on the LAST '-' with `rsplit`, not `rpartition`;
  * computes medians by index into a sorted list built with `list.sort()`, not a helper.

Run:  python3 scripts/depth_label_substrate_rederive.py [--json]
Exit 0 = every compared field agrees with `reports/depth_label_substrate_census.json`;
exit 1 = a disagreement, printed field by field.
"""
from __future__ import annotations

import argparse
import json
import os
from glob import glob
from typing import Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRYPTO = ("KXBTC", "KXETH")


def _ticker_of_raw(line: str) -> str:
    """Pull `ticker` out of the raw JSONL line without a full parse (a different failure mode
    from the census's `json.loads`)."""
    i = line.find('"ticker"')
    if i < 0:
        return ""
    k = line.find(":", i + 8)
    if k < 0:
        return ""
    k += 1
    while k < len(line) and line[k] in " \t":
        k += 1
    if k >= len(line) or line[k] != '"':
        return ""          # a null/numeric ticker is not a ticker
    j = line.find('"', k + 1)
    return line[k + 1:j] if j > 0 else ""


def depth_snapshots(tape: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for path in sorted(glob(os.path.join(tape, "orderbook_depth", "dt=*.jsonl"))):
        with open(path) as fh:
            for line in fh:
                t = _ticker_of_raw(line)
                if t:
                    counts[t] = counts.get(t, 0) + 1
    return counts


def depth_days(tape: str) -> Dict[str, set]:
    days: Dict[str, set] = {}
    for path in sorted(glob(os.path.join(tape, "orderbook_depth", "dt=*.jsonl"))):
        day = os.path.basename(path)[3:13]
        with open(path) as fh:
            for line in fh:
                t = _ticker_of_raw(line)
                if t:
                    days.setdefault(t, set()).add(day)
    return days


def labels(tape: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """(all_labels, naive_union_labels) — read straight from each source's own grammar."""
    allv: Dict[str, str] = {}
    naive: Dict[str, str] = {}
    for path in sorted(glob(os.path.join(tape, "settlement_ledger", "dt=*.jsonl"))):
        for line in open(path):
            if '"result":"yes"' in line or '"result":"no"' in line:
                rec = json.loads(line)
                if rec.get("result") in ("yes", "no") and rec.get("ticker"):
                    allv.setdefault(rec["ticker"], "settlement_ledger")
                    naive.setdefault(rec["ticker"], "settlement_ledger")
    for path in sorted(glob(os.path.join(tape, "q*_settlement_cache", "*.json"))):
        fam = os.path.basename(os.path.dirname(path))
        for t, v in (json.load(open(path)).get("markets") or {}).items():
            if v.get("result") in ("yes", "no"):
                allv.setdefault(t, fam)
                naive.setdefault(t, fam)
    for path in sorted(glob(os.path.join(tape, "crypto_hourly", "dt=*.jsonl"))):
        for line in open(path):
            if '"previous_settlement"' not in line:
                continue
            ps = json.loads(line).get("previous_settlement") or {}
            if ps.get("status") != "settled":
                continue
            for t, res in (ps.get("results") or {}).items():
                if res in ("yes", "no"):
                    allv.setdefault(t, "crypto_hourly")
    return allv, naive


def klass(t: str) -> str:
    s = t.split("-")[0]
    return "crypto" if s in CRYPTO else ("sports" if "GAME" in s else "other")


def median(xs: List[int]):
    if not xs:
        return None
    xs = list(xs)
    xs.sort()
    n = len(xs)
    return float(xs[n // 2]) if n % 2 == 1 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def rederive(tape: str) -> Dict[str, object]:
    snaps = depth_snapshots(tape)
    days = depth_days(tape)
    allv, naive = labels(tape)
    out: Dict[str, object] = {"n_tickers": len(snaps),
                              "n_snapshots": sum(snaps.values()),
                              "n_resolved_total": sum(1 for t in snaps if t in allv),
                              "n_resolved_naive_union": sum(
                                  1 for t in snaps if t in allv and t in naive)}
    per_class: Dict[str, Dict[str, object]] = {}
    for cls in ("crypto", "sports", "other"):
        ts = [t for t in snaps if klass(t) == cls]
        legs = [snaps[t] for t in ts]
        units: Dict[str, List[str]] = {}
        for t in ts:
            head = t.rsplit("-", 1)
            if len(head) == 2 and head[0] and head[1]:
                units.setdefault(head[0], []).append(t)
        ready = [e for e, ls in units.items()
                 if all(x in allv for x in ls) and sum(snaps[x] for x in ls) >= 2]
        rdays = set()
        for e in ready:
            for x in units[e]:
                rdays |= days.get(x, set())
        per_class[cls] = {
            "n_tickers": len(ts),
            "n_resolved": sum(1 for t in ts if t in allv),
            "n_units": len(units),
            "n_probe_ready": len(ready),
            "n_distinct_ready_days": len(rdays),
            "median_snapshots_per_leg": median(legs),
            "frac_legs_with_ge_2_snapshots": (
                round(sum(1 for x in legs if x >= 2) / len(legs), 4) if legs else None),
        }
    out["by_class"] = per_class
    return out


def compare(mine: Dict[str, object], census_report: Dict[str, object]) -> List[str]:
    diffs: List[str] = []

    def chk(name, a, b):
        if a != b:
            diffs.append(f"{name}: rederive={a!r} census={b!r}")

    chk("n_tickers", mine["n_tickers"], census_report["population"]["n_tickers"])
    chk("n_snapshots", mine["n_snapshots"], census_report["population"]["n_snapshots"])
    lc = census_report["label_coverage"]
    chk("n_resolved_total", mine["n_resolved_total"], lc["n_resolved_total"])
    chk("n_resolved_naive_union", mine["n_resolved_naive_union"],
        lc["n_resolved_naive_union_only"])
    for cls, m in mine["by_class"].items():
        chk(f"{cls}.n_tickers", m["n_tickers"], lc["by_class"][cls]["n_tickers"])
        chk(f"{cls}.n_resolved", m["n_resolved"], lc["by_class"][cls]["n_resolved"])
        ur = census_report["unit_readiness"][cls]
        chk(f"{cls}.n_units", m["n_units"], ur["n_units"])
        chk(f"{cls}.n_probe_ready", m["n_probe_ready"], ur["n_probe_ready"])
        chk(f"{cls}.n_distinct_ready_days", m["n_distinct_ready_days"],
            ur["n_distinct_ready_days"])
        fo = census_report["fill_observability"][cls]
        chk(f"{cls}.median_snapshots_per_leg", m["median_snapshots_per_leg"],
            fo["median_snapshots_per_leg"])
        chk(f"{cls}.frac_legs_with_ge_2_snapshots", m["frac_legs_with_ge_2_snapshots"],
            fo["frac_legs_with_ge_2_snapshots"])
    return diffs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tape-root", default=os.path.join(ROOT, "tape"))
    ap.add_argument("--census-json", default=os.path.join(
        ROOT, "reports", "depth_label_substrate_census.json"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    mine = rederive(args.tape_root)
    if args.json:
        print(json.dumps(mine, indent=1, sort_keys=True))
    with open(args.census_json) as fh:
        rep = json.load(fh)
    diffs = compare(mine, rep)
    if diffs:
        print("DISAGREEMENT:")
        for d in diffs:
            print("  " + d)
        return 1
    print("redundancy check: every compared field agrees (NOT a verifier confirmation)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
