#!/usr/bin/env python3
"""INDEPENDENT re-derivation of `scripts/close_time_mutation_audit.py`'s headline numbers.

Why this file exists
--------------------
The two-agent verdict rule (LOOP-QUEUE protocol v3) wants a second agent to re-run and attack
any number before it is recorded. No `Task`/`verifier` subagent exists in this harness
(L287/L288/L290/L291/L295/L308/L313/L325/L338 precedent), so the sanctioned fallback is
REDUNDANCY: a second implementation that shares no code with the first, reaches the same
question by a different route, and is reported AS redundancy -- never as verification.

Independence is structural and TEST-PINNED (`tests/test_close_time_mutation_rederive.py`
asserts by AST that this module imports none of them):

  * it does NOT import `core.close_time_mutation`  -- no shared regime/settled definition
  * it does NOT import `core.settlement_sources`   -- no shared source registry or root
  * it does NOT import the audit script            -- no shared loader, pairing or summary

The single permitted import is `core.timeutil.parse_iso_utc` (see the note beside it): L136/L150
gate every raw `datetime.fromisoformat` site in the repo, so a private parser here would be a
deliberate known-defect. That shared parser is the one published limit of this redundancy.

Different route, not a different spelling of the same route
-----------------------------------------------------------
  * The audit decodes JSON and walks structure. This scans RAW TEXT with regexes and
    attributes each field to the NEAREST PRECEDING ticker-shaped key -- positional, not
    structural. If the audit's structural walk mis-associates a row, positional attribution
    fails differently, so agreement is informative.
  * The audit answers the live-stability question by ordering each ticker's observations and
    comparing first to last. This answers it BACKWARDS and without any ordering at all:
    close_time is stable for every ticker if and only if the number of distinct
    (ticker, close_time) pairs equals the number of distinct tickers. No `captured_at` is
    read, so a clock defect cannot produce the same answer twice.
  * The audit enumerates cache files from the declared source registry. This globs the tape
    root for `*/settlement*.json`, so a registry omission cannot hide a file from both.

Read-only. No network, no writes, no verdict, no CI, no P&L.

Run:
    python3 scripts/close_time_mutation_rederive.py
    python3 scripts/close_time_mutation_rederive.py --tape-root <dir> --no-live
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Exactly ONE project import, and it is mandated rather than chosen: L136/L150 GATE against
# any new raw `datetime.fromisoformat` call site, because Kalshi's bare-`Z` / short-fraction
# timestamps (38.27% of committed tape) parse on CI's 3.11 and crash on the declared 3.9
# floor. A hand-rolled parser here would be independence bought with a known bug.
# HONEST LIMIT this creates, stated rather than hidden: the audit and this re-derivation now
# share their ISO parser, so a defect INSIDE `parse_iso_utc` is the one class of error this
# redundancy cannot catch. Everything else -- source enumeration, attribution, pairing,
# regime rules, the live-stability question -- remains independent and is AST-pinned as such.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.timeutil import parse_iso_utc  # noqa: E402

# The root is derived here independently, and is ABSOLUTE (L345/L348): a relative "tape"
# would score whatever tree the process started in, returning 0 findings at exit code 0.
TAPE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tape")

#: A ticker-shaped JSON map key: uppercase/dash/digit, at least two dash-separated segments.
_TICKER_KEY_RE = re.compile(rb'"([A-Z0-9]+(?:-[A-Z0-9.]+)+)"\s*:\s*\{')
_CLOSE_RE = re.compile(rb'"close_time"\s*:\s*"([^"]*)"')
_RESULT_RE = re.compile(rb'"result"\s*:\s*"([^"]*)"')
_STATUS_RE = re.compile(rb'"status"\s*:\s*"([^"]*)"')

_TERMINAL = {"settled", "finalized", "determined"}


def _nearest_preceding(keys: List[Tuple[int, str]], pos: int) -> Optional[str]:
    """The ticker key whose `{` opened most recently at or before `pos`. Positional.

    `keys` holds each ticker match's END offset, i.e. the index one past its `{`. In COMPACT
    JSON (`json.dumps` default) the very next character is the first field's opening quote, so
    the owner's key offset EQUALS the field match's start and a strict `<` silently attributed
    that field to the PREVIOUS ticker. Found by `tests/test_close_time_mutation_rederive.py::
    TestPositionalAttribution` on a compact fixture; the committed caches are pretty-printed,
    so real tape never hit it and the reconciliation was correct both before and after -- which
    is precisely why the fixture, not the tape, had to be the thing that asked."""
    lo, hi, found = 0, len(keys) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if keys[mid][0] <= pos:
            found = keys[mid][1]
            lo = mid + 1
        else:
            hi = mid - 1
    return found


def scan_cache_file(path: str) -> Dict[str, Dict[str, Optional[str]]]:
    """ticker -> {close_time, result, status} by raw-text scan with positional attribution."""
    with open(path, "rb") as fh:
        raw = fh.read()
    keys = [(m.end(), m.group(1).decode("ascii")) for m in _TICKER_KEY_RE.finditer(raw)]
    keys.sort()
    out: Dict[str, Dict[str, Optional[str]]] = {}
    for rx, field in ((_CLOSE_RE, "close_time"), (_RESULT_RE, "result"), (_STATUS_RE, "status")):
        for m in rx.finditer(raw):
            owner = _nearest_preceding(keys, m.start())
            if owner is None:
                continue
            out.setdefault(owner, {})[field] = m.group(1).decode("utf-8", "replace")
    return out


def _settled(row: Dict[str, Optional[str]]) -> bool:
    """Settled = non-empty result, or a terminal status. `closed` is not terminal."""
    r = (row.get("result") or "").strip()
    if r:
        return True
    return (row.get("status") or "").strip().lower() in _TERMINAL


def _instant(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        dt = parse_iso_utc(text.strip())
    except (ValueError, TypeError):
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _pulled_at(path: str) -> str:
    """Read only the `pulled_at` scalar via regex -- still no structural decode of the blob."""
    with open(path, "rb") as fh:
        m = re.search(rb'"pulled_at"\s*:\s*"([^"]*)"', fh.read())
    return m.group(1).decode() if m else ""


def cache_files(root: str = TAPE_ROOT) -> List[str]:
    """Every `*/settlement*.json` under the tape root -- registry-independent by design."""
    return sorted(glob.glob(os.path.join(root, "*", "settlement*.json")))


def rederive_caches(root: str = TAPE_ROOT) -> Dict[str, Any]:
    files = cache_files(root)
    scans = {p: scan_cache_file(p) for p in files}
    order = sorted(files, key=lambda p: (_pulled_at(p), p))
    per_ticker_changed: Dict[str, bool] = {}
    per_ticker_date_changed: Dict[str, bool] = {}
    per_ticker_open_to_settled: Dict[str, bool] = {}
    regime_obs = {"open_to_open": 0, "open_to_settled": 0, "settled_to_settled": 0,
                  "settled_to_open": 0}
    moved_earlier = moved_later = 0
    conflicts: List[Tuple[str, str, str]] = []
    n_obs = 0
    for i, a in enumerate(order):
        for b in order[i + 1:]:
            sa, sb = scans[a], scans[b]
            for t in sorted(set(sa) & set(sb)):
                ra, rb = sa[t], sb[t]
                n_obs += 1
                ea, eb = _settled(ra), _settled(rb)
                key = ("settled_to_settled" if ea and eb else
                       "settled_to_open" if ea else
                       "open_to_settled" if eb else "open_to_open")
                regime_obs[key] += 1
                if key == "open_to_settled":
                    per_ticker_open_to_settled[t] = True
                ia, ib = _instant(ra.get("close_time")), _instant(rb.get("close_time"))
                if ia is not None and ib is not None and ia != ib:
                    per_ticker_changed[t] = True
                    if ib < ia:
                        moved_earlier += 1
                    else:
                        moved_later += 1
                    if ia.date() != ib.date():
                        per_ticker_date_changed[t] = True
                if ea and eb:
                    va = (ra.get("result") or "").strip().lower()
                    vb = (rb.get("result") or "").strip().lower()
                    if va and vb and va != vb:
                        conflicts.append((t, va, vb))
    tickers = set()
    for s in scans.values():
        tickers |= set(s)
    return {
        "n_cache_files": len(files),
        "cache_files": [os.path.relpath(p, root) for p in files],
        "n_paired_observations": n_obs,
        "regime_observation_counts": regime_obs,
        "n_distinct_tickers_across_pairs": len(
            set().union(*[set(scans[a]) & set(scans[b])
                          for i, a in enumerate(order) for b in order[i + 1:]] or [set()])),
        "n_distinct_close_time_changed": len(per_ticker_changed),
        "n_distinct_close_date_changed": len(per_ticker_date_changed),
        "n_distinct_open_to_settled": len(per_ticker_open_to_settled),
        "n_observations_moved_earlier": moved_earlier,
        "n_observations_moved_later": moved_later,
        "n_settled_result_conflicts": len(conflicts),
        "settled_result_conflicts": conflicts[:20],
        "n_tickers_any_cache": len(tickers),
    }


def rederive_live(root: str = TAPE_ROOT) -> Dict[str, Any]:
    """Stability WITHOUT ordering: #distinct (ticker, close_time) vs #distinct ticker."""
    pairs = set()
    tickers = set()
    n_lines = 0
    for path in sorted(glob.glob(os.path.join(root, "universe_sweep", "dt=*.jsonl"))):
        with open(path, "rb") as fh:
            for raw in fh:
                if not raw.strip():
                    continue
                n_lines += 1
                mt = re.search(rb'"ticker"\s*:\s*"([^"]*)"', raw)
                mc = _CLOSE_RE.search(raw)
                if not mt:
                    continue
                t = mt.group(1).decode("utf-8", "replace")
                tickers.add(t)
                pairs.add((t, mc.group(1).decode("utf-8", "replace") if mc else None))
    return {
        "n_lines": n_lines,
        "n_distinct_tickers": len(tickers),
        "n_distinct_ticker_close_time_pairs": len(pairs),
        "n_tickers_with_more_than_one_close_time": len(pairs) - len(tickers),
        "every_ticker_has_exactly_one_close_time": len(pairs) == len(tickers),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tape-root", default=TAPE_ROOT)
    ap.add_argument("--no-live", action="store_true")
    ap.add_argument("--report-path",
                    default=os.path.join(os.path.dirname(TAPE_ROOT), "reports",
                                         "close_time_mutation_rederive.json"))
    args = ap.parse_args(argv)
    out: Dict[str, Any] = {"rederived_at": datetime.now(timezone.utc).isoformat(),
                           "tape_root": args.tape_root,
                           "caches": rederive_caches(args.tape_root)}
    out["live"] = None if args.no_live else rederive_live(args.tape_root)
    os.makedirs(os.path.dirname(args.report_path), exist_ok=True)
    with open(args.report_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps(out, indent=2, sort_keys=True))
    print(f"report -> {args.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
