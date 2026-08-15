#!/usr/bin/env python3
"""Independent re-derivation of `settlement_source_recall_audit.py`'s headline numbers.

REDUNDANCY, NOT VERIFICATION. This harness carries no `Task`/`verifier` subagent (the
L287/L288/L290/L291/L295/L308/L313/L325/L338 precedent), so the sanctioned fallback is a
second implementation that shares no code path with the first. It is reported as redundancy
and never as the two-agent rule being satisfied.

Deliberately different at every level, so a shared bug cannot survive both:
  * imports NEITHER `core.result_evidence` NOR `core.settlement_sources` NOR the audit module
    (AST-pinned by `tests/test_settlement_source_recall_rederive.py`);
  * finds results with a REGEX over raw bytes instead of decoding JSON and walking the tree;
  * attributes a result to a ticker by PROXIMITY in the raw line (nearest preceding `"ticker"`
    / map key) instead of by dict structure;
  * answers the resolver-overlap question the opposite way round — instead of resolving each
    candidate ticker, it asks whether any DECLARED source file mentions the candidate's series
    at all, which bounds the overlap from above without re-implementing the resolver.

A field-by-field match is evidence the numbers are not an artefact of one parser. A mismatch
is the interesting outcome and must be reported, not reconciled away.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any, Dict, List, Optional, Set

DECLARED_DIRS = (
    "settlement_ledger", "q26_settlement_cache", "q27_settlement_cache", "q29_settlement_cache",
    "q30_settlement_cache", "q51_settlement_cache", "q56_settlement_cache", "crypto_hourly",
    "weather_actuals", "econ_prints",
)

_RESULT_RE = re.compile(rb'"result"\s*:\s*"([^"]*)"')
_TICKER_RE = re.compile(rb'"(?:market_)?ticker"\s*:\s*"([^"]+)"')
_MAPKEY_RE = re.compile(rb'"([A-Z0-9][A-Z0-9\-\.]{7,})"\s*:\s*\{')
_STATUS_RE = re.compile(rb'"status"\s*:\s*"([^"]*)"')
_BINARY = (b"yes", b"no")


def _files(d: str) -> List[str]:
    out: List[str] = []
    for root, _dirs, files in os.walk(d):
        for fn in sorted(files):
            if fn.endswith((".json", ".jsonl")):
                out.append(os.path.join(root, fn))
    return sorted(out)


def _labels_in_blob(blob: bytes) -> Dict[str, str]:
    """Attribute each populated `result` to a ticker by POSITION in the raw bytes — no JSON
    decode, no dict walk. Structurally different from the audit; agrees only if both are
    reading the same thing.

    Rule: nearest ticker anchor in EITHER direction, where an anchor is a ticker FIELD
    (`"ticker"` / `"market_ticker"`) or a ticker-shaped MAP KEY. It is one-directional-free on
    purpose — these files are written with `sort_keys=True`, so a ticker field lands AFTER
    `result` when it is called `ticker` and BEFORE when it is called `market_ticker`, while a
    map key always precedes. A nearest-PRECEDING rule under-counted `tape/sports_history/`
    341 -> 214 and scored `tape/sports_history_s7/` at 0; both bugs were in THIS file, which
    is what a redundancy pass is for.

    PUBLISHED LIMIT, measured rather than assumed: on a ticker-KEYED MAP whose objects are
    small (the `tape/qNN_settlement_cache/` shape), the NEXT map key can be nearer to a result
    than its own, so attribution shifts by one. `known_disagreement_families()` reports exactly
    which families this affects and by how much, and the reconciliation test excludes them BY
    NAME rather than by loosening the assertion. It affects no family the audit's headline
    rests on: every undeclared/candidate family, `sports_pairs`, `universe_sweep` and the depth
    leg population agree exactly. The correct fix is a brace-matching parse of each object,
    which would have to walk ~300 MB of bytes in Python per run — the cost is not worth it for
    a cross-check of DECLARED sources that the audit reads through the sanctioned resolver.
    """
    anchors = [(m.start(), m.group(1).decode()) for m in _TICKER_RE.finditer(blob)]
    anchors += [(m.start(), m.group(1).decode()) for m in _MAPKEY_RE.finditer(blob)]
    anchors.sort()
    out: Dict[str, str] = {}
    conflict: Set[str] = set()
    for m in _RESULT_RE.finditer(blob):
        val = m.group(1).strip().lower().decode()
        if val not in ("yes", "no"):
            continue
        pos = m.start()
        if not anchors:
            continue
        lo, hi = 0, len(anchors)
        while lo < hi:
            mid = (lo + hi) // 2
            if anchors[mid][0] < pos:
                lo = mid + 1
            else:
                hi = mid
        cands = []
        if lo:
            cands.append(anchors[lo - 1])
        if lo < len(anchors):
            cands.append(anchors[lo])
        tk = min(cands, key=lambda c: abs(c[0] - pos))[1]
        if tk in out and out[tk] != val:
            conflict.add(tk)
        out[tk] = val
    for tk in conflict:
        out.pop(tk, None)
    return out


def known_disagreement_families() -> tuple:
    """Families where the positional reader's published limit bites — ticker-KEYED MAPS with
    small objects. Named, not hand-waved, so the reconciliation test can exclude them BY NAME."""
    return ("q26_settlement_cache", "q27_settlement_cache", "q29_settlement_cache",
            "q30_settlement_cache", "q51_settlement_cache", "q56_settlement_cache")


def rederive(tape_root: str = "tape") -> Dict[str, Any]:
    fams = sorted(d for d in os.listdir(tape_root) if os.path.isdir(os.path.join(tape_root, d)))
    per_family: Dict[str, Any] = {}
    for fam in fams:
        labels: Dict[str, str] = {}
        empty_results = 0
        closed = 0
        terminal = 0
        n_lines = 0
        for path in _files(os.path.join(tape_root, fam)):
            with open(path, "rb") as fh:
                data = fh.read()
            if path.endswith(".jsonl"):
                chunks = [ln for ln in data.split(b"\n") if ln.strip()]
            else:
                chunks = [data]
            n_lines += len(chunks)
            for ch in chunks:
                if b'"result"' in ch:
                    for m in _RESULT_RE.finditer(ch):
                        if not m.group(1).strip():
                            empty_results += 1
                    labels.update(_labels_in_blob(ch))
                for m in _STATUS_RE.finditer(ch):
                    v = m.group(1).strip().lower()
                    if v == b"closed":
                        closed += 1
                    elif v in (b"settled", b"finalized", b"determined"):
                        terminal += 1
        per_family[fam] = {
            "n_lines": n_lines,
            "n_binary_labeled_tickers": len(labels),
            "n_empty_result_nodes": empty_results,
            "n_closed_status_nodes": closed,
            "n_terminal_status_nodes": terminal,
        }
        if fam in ("sports_history", "sports_history_s7"):
            per_family[fam]["_tickers"] = sorted(labels)

    # Overlap bound, answered backwards: does ANY declared source even mention the series?
    cand: Set[str] = set()
    for fam in ("sports_history", "sports_history_s7"):
        cand |= set(per_family.get(fam, {}).get("_tickers", []))
    series = sorted({t.split("-", 1)[0] for t in cand})
    mentions: Dict[str, int] = {s: 0 for s in series}
    for d in DECLARED_DIRS:
        p = os.path.join(tape_root, d)
        if not os.path.isdir(p):
            continue
        for path in _files(p):
            with open(path, "rb") as fh:
                blob = fh.read()
            for s in series:
                if s.encode() in blob:
                    mentions[s] += 1

    # Where do the candidate labels land?
    depth_legs: Set[str] = set()
    for path in _files(os.path.join(tape_root, "orderbook_depth")):
        with open(path, "rb") as fh:
            for raw in fh:
                m = _TICKER_RE.search(raw)
                if m:
                    depth_legs.add(m.group(1).decode())
    price_legs: Set[str] = set()
    for path in _files(os.path.join(tape_root, "sports_pairs")):
        with open(path, "rb") as fh:
            blob = fh.read()
        for m in _TICKER_RE.finditer(blob):
            price_legs.add(m.group(1).decode())
        for m in _MAPKEY_RE.finditer(blob):
            price_legs.add(m.group(1).decode())

    return {
        "schema_version": "settlement_source_recall_rederive.v1",
        "per_family": {f: {k: v for k, v in d.items() if not k.startswith("_")}
                       for f, d in per_family.items()},
        "candidate_labels": len(cand),
        "candidate_series": series,
        "declared_source_files_mentioning_candidate_series": mentions,
        "candidates_landing_on_depth_legs": len(cand & depth_legs),
        "candidates_landing_on_price_legs": len(cand & price_legs),
        "n_depth_legs": len(depth_legs),
        "n_price_legs": len(price_legs),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tape-root", default="tape")
    ap.add_argument("--json-out", default="reports/settlement_source_recall_rederive.json")
    args = ap.parse_args(argv)
    rep = rederive(args.tape_root)
    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
        with open(args.json_out, "w") as fh:
            json.dump(rep, fh, indent=1, sort_keys=True)
            fh.write("\n")
    print(json.dumps({k: v for k, v in rep.items() if k != "per_family"}, indent=1, sort_keys=True))
    for f in ("sports_history", "sports_history_s7", "sports_pairs", "universe_sweep"):
        if f in rep["per_family"]:
            print(f, json.dumps(rep["per_family"][f], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
