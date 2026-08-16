#!/usr/bin/env python3
"""Idle-run policy (c) — data-quality deep-dive: is the SETTLEMENT-SOURCE REGISTRY complete?

LOOP-QUEUE.md protocol v3, 2026-08-15. READ-ONLY and FULLY OFFLINE: opens committed tape
files and nothing else — no network, no credentials, no orders, no writes outside `reports/`.
It emits a DATA-ADEQUACY description: no P&L, no CI, no bootstrap, no registry flip
(test-pinned — see `tests/test_settlement_source_recall_audit.py`).

THE QUESTION, falsifiably. `core/settlement_sources.py` is the ONE sanctioned answer to "is
this market's outcome known?", and every kill-by-data-adequacy of the last month leaned on
it (Q21 rounds #30/#31, Q24's 0/81 join, Q54's data gate, and the 2026-08-15 depth-label
substrate census that named the sports family label-poor and routed the fix to a Ryan-side
collector). That module publishes its own recall limit: its `undeclared_settlement_dirs()`
guard is DIRECTORY-NAME based and structurally cannot see a family that hides settled state
inside another family's record schema — which is how 3 of its 10 declared sources arrived.

So: **does any committed tape family carry populated, market-attributable outcome state that
the sanctioned resolver cannot see, and if so what would declaring it be WORTH?** "Worth" is
not the raw label count — it is the count that lands on a population a probe could actually
score. A label on a market we never captured a book for buys nothing.

FOUR MEASUREMENTS, each falsifiable from committed bytes:

1. `family_scan` — every family directory under `tape/`, every committed `.json`/`.jsonl`
   file in it, streamed. Evidence extracted by `core.result_evidence.scan_record` (field
   level, NOT directory name). Lines are byte-prefiltered before decode for speed; the
   prefilter's completeness is separately test-pinned, and `n_lines` is a true line count so
   the prefilter can never silently shrink the denominator.
2. `registry_gap` — each family classified into exactly one of:
     `declared`              — named by `declared_source_names()`
     `undeclared_populated`  — NOT declared, and carries >=1 ATTRIBUTED binary label
     `undeclared_schema_only`— NOT declared, carries the `result` field but never populated
     `no_outcome_field`      — NOT declared, no `result`/`status` evidence at all
   The third class is the interesting negative: it proves a family is structurally incapable
   of labeling, which is a stronger statement than "we have no labels from it yet".
3. `yield` — for each `undeclared_populated` family: distinct binary-labeled tickers, how many
   the sanctioned resolver ALSO resolves (overlap), the AGREEMENT rate on that overlap (a
   source that disagrees with broker truth is a defect, not a discovery), and the NET-NEW count.
4. `depth_incremental` — the load-bearing one. Of the net-new tickers, how many appear in
   `tape/orderbook_depth/` (the only family carrying both sides of a resting book, i.e. the
   only substrate a maker fill-sim can score on), and how many depth EVENT units (L6's
   bootstrap unit: ticker minus its final `-LEAF` segment) would become fully labeled that
   are not fully labeled today. A net-new label that touches zero depth units is recorded as
   worth zero to the fill question, however large its raw count.

WHAT THIS CANNOT SHOW. `core.result_evidence`'s recall limit (published in that module) is
inherited whole: a family encoding outcomes under a name other than `result`/`status` is
invisible here. A clean run therefore means "no `result`/`status`-shaped undeclared source",
never "the registry is complete". Stating it the other way round would recreate exactly the
L165/L300 failure this audit exists to close.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Set, Tuple

from core.result_evidence import line_may_carry_evidence, scan_record
from core.settlement_sources import (DEFAULT_TAPE_ROOT, declared_source_names,
                                     resolve_market_results)

#: Re-exported from the sanctioned resolver rather than re-declared as the relative string
#: "tape" — L345/L348: a relative default silently scores one tree's labels against another's,
#: and `scripts/invariants.py::_settlement_root_anchoring_issues` gates on exactly that.
DEPTH_FAMILY = "orderbook_depth"

#: Families that are ANALYSIS ARTEFACTS this repo wrote itself, not exchange captures. They
#: may legitimately echo a result they read from a declared source; declaring them as
#: settlement sources would launder a derived number back in as broker truth (the L9/L300
#: double-count shape). They are still SCANNED and still REPORTED — the exemption only means
#: "do not advise declaring this one", and each carries the probe that produced it.
DERIVED_ARTEFACT_FAMILIES: Dict[str, str] = {
    "sports_clv": "scripts/sports_clv.py output (de-vig study), derived",
    "sports_clv_s7": "scripts/sports_clv_s7.py output (S7c bootstrap input), derived",
    "sports_maker_fillsim": "scripts/s13_maker_fillsim.py candle summaries, derived",
    "s14_ladder_fillsim": "scripts/s14_ladder_fillsim.py output, derived",
    "anomalies": "scripts/anomaly_sweep.py output, derived",
}

_LEAF_RE = re.compile(r"^(?P<event>.+)-(?P<leaf>[^-]+)$")


def _collect_market_legs(node: Any, out: Set[str], depth: int = 0) -> None:
    """Every market ticker reachable in a `sports_pairs` record, by BOTH shapes it uses: an
    `outcomes[].ticker` field (day-file records) and a ticker-keyed MAP (raw captures, which
    also nest one level deep inside some day-file records). The nested walk was added after an
    independent regex reader found 231 legs (2.0%) this enumeration was missing — a bigger
    denominator only makes the 'what does a new label buy' fraction more conservative."""
    if depth > 6:
        return
    if isinstance(node, Mapping):
        for k, v in node.items():
            if k in ("ticker", "market_ticker") and isinstance(v, str) and v:
                out.add(v)
            if isinstance(v, dict) and _looks_like_market_key(k):
                out.add(k)
            if isinstance(v, (dict, list)):
                _collect_market_legs(v, out, depth + 1)
    elif isinstance(node, list):
        for v in node:
            if isinstance(v, (dict, list)):
                _collect_market_legs(v, out, depth + 1)


def _looks_like_market_key(key: Any) -> bool:
    """A `sports_pairs` raw-capture file is a MAP from market ticker -> market object; this
    recognises that key shape so those legs are counted. Same narrowness as
    `core.result_evidence._looks_like_ticker`, restated locally rather than imported private."""
    return (isinstance(key, str) and len(key) >= 8 and "-" in key
            and not any(ch.isspace() for ch in key) and key == key.upper())


def event_unit(ticker: str) -> str:
    """L6's bootstrap unit for a book-scored probe: the ticker minus its final `-LEAF`
    segment. Returns the ticker unchanged when it has no leaf segment."""
    m = _LEAF_RE.match(ticker)
    return m.group("event") if m else ticker


def iter_family_files(fam_dir: str) -> List[str]:
    out: List[str] = []
    for root, _dirs, files in os.walk(fam_dir):
        for fn in sorted(files):
            if fn.endswith(".jsonl") or fn.endswith(".json"):
                out.append(os.path.join(root, fn))
    return sorted(out)


def _iter_records(path: str) -> Iterator[Tuple[Any, bool]]:
    """(record, prefilter_hit) for each record in a committed file.

    `.jsonl` -> one record per line, byte-prefiltered before decode.
    `.json`   -> the whole document is ONE record, always decoded (no prefilter: a single
                 document is cheap and skipping it on a byte test would be the only place a
                 prefilter miss could hide a whole family).
    """
    if path.endswith(".json"):
        try:
            with open(path, "rb") as fh:
                yield json.loads(fh.read().decode("utf-8", "replace")), True
        except Exception:
            return
        return
    with open(path, "rb") as fh:
        for raw in fh:
            if not raw.strip():
                continue
            if not line_may_carry_evidence(raw):
                yield None, False
                continue
            try:
                yield json.loads(raw.decode("utf-8", "replace")), True
            except Exception:
                yield None, True


def scan_family(fam: str, fam_dir: str) -> Dict[str, Any]:
    files = iter_family_files(fam_dir)
    n_lines = 0
    n_decoded = 0
    n_malformed = 0
    labels: Dict[str, Set[str]] = {}
    non_binary: Set[str] = set()
    unattributed = 0
    terminal_status = 0
    closed_not_settled = 0
    schema_only = 0
    for path in files:
        for rec, hit in _iter_records(path):
            n_lines += 1
            if not hit:
                continue
            if rec is None:
                n_malformed += 1
                continue
            n_decoded += 1
            ev = scan_record(rec)
            unattributed += len(ev["unattributed_results"])
            terminal_status += len(ev["terminal_status"])
            closed_not_settled += ev["closed_not_settled"]
            schema_only += ev["schema_only_result"]
            for lab in ev["labels"]:
                if lab["binary"]:
                    labels.setdefault(lab["ticker"], set()).add(lab["result"])
                else:
                    non_binary.add(lab["ticker"])
    conflicts = sorted(t for t, v in labels.items() if len(v) > 1)
    return {
        "family": fam,
        "n_files": len(files),
        "n_lines": n_lines,
        "n_decoded": n_decoded,
        "n_malformed": n_malformed,
        "n_binary_labeled_tickers": len(labels),
        "n_non_binary_tickers": len(non_binary),
        "n_conflicting_tickers": len(conflicts),
        "conflicting_tickers_sample": conflicts[:5],
        "n_unattributed_results": unattributed,
        "n_terminal_status_nodes": terminal_status,
        "n_closed_not_settled_nodes": closed_not_settled,
        "n_schema_only_result_nodes": schema_only,
        "_labels": {t: sorted(v)[0] for t, v in labels.items() if len(v) == 1},
    }


def classify(fam: str, scan: Dict[str, Any], declared: Iterable[str]) -> str:
    if fam in set(declared):
        return "declared"
    if scan["n_binary_labeled_tickers"] > 0:
        return "undeclared_populated"
    if scan["n_schema_only_result_nodes"] > 0 or scan["n_terminal_status_nodes"] > 0:
        return "undeclared_schema_only"
    return "no_outcome_field"


def depth_population(tape_root: str) -> Dict[str, Set[str]]:
    """{event_unit: {leg tickers}} over the whole committed depth family."""
    units: Dict[str, Set[str]] = {}
    fam_dir = os.path.join(tape_root, DEPTH_FAMILY)
    if not os.path.isdir(fam_dir):
        return units
    for path in iter_family_files(fam_dir):
        with open(path, "rb") as fh:
            for raw in fh:
                if b'"ticker"' not in raw:
                    continue
                try:
                    rec = json.loads(raw.decode("utf-8", "replace"))
                except Exception:
                    continue
                tk = rec.get("ticker")
                if isinstance(tk, str) and tk:
                    units.setdefault(event_unit(tk), set()).add(tk)
    return units


def audit(tape_root: str = DEFAULT_TAPE_ROOT) -> Dict[str, Any]:
    declared = list(declared_source_names())
    fams = sorted(
        d for d in os.listdir(tape_root)
        if os.path.isdir(os.path.join(tape_root, d))
    )
    scans: Dict[str, Dict[str, Any]] = {}
    for fam in fams:
        scans[fam] = scan_family(fam, os.path.join(tape_root, fam))

    registry_gap: Dict[str, List[str]] = {
        "declared": [], "undeclared_populated": [],
        "undeclared_schema_only": [], "no_outcome_field": [],
    }
    for fam, sc in scans.items():
        registry_gap[classify(fam, sc, declared)].append(fam)

    # --- measurement 3: what would declaring each undeclared_populated family be worth?
    # `root=tape_root` is load-bearing, not decoration (L345): `resolve_market_results`
    # defaults to the RELATIVE string "tape", so an audit run against any other tree would
    # otherwise score its labels against the repo's committed tape and silently invent a
    # 100% overlap. Pinned by the synthetic-tree tests, which run under a tmp_path root.
    yields: Dict[str, Any] = {}
    net_new: Dict[str, str] = {}
    for fam in registry_gap["undeclared_populated"]:
        fam_labels: Dict[str, str] = scans[fam]["_labels"]
        rep = resolve_market_results(list(fam_labels), root=tape_root)
        overlap = {t: mr for t, mr in rep.resolved.items() if t in fam_labels}
        agree = sum(1 for t, mr in overlap.items() if mr.result == fam_labels[t])
        fresh = {t: r for t, r in fam_labels.items() if t not in rep.resolved}
        yields[fam] = {
            "n_labeled_tickers": len(fam_labels),
            "n_resolver_overlap": len(overlap),
            "n_agree_on_overlap": agree,
            "n_disagree_on_overlap": len(overlap) - agree,
            "agreement_rate": (agree / len(overlap)) if overlap else None,
            "n_net_new": len(fresh),
            "derived_artefact": fam in DERIVED_ARTEFACT_FAMILIES,
            "derived_artefact_note": DERIVED_ARTEFACT_FAMILIES.get(fam),
            "sample_net_new": sorted(fresh)[:5],
        }
        if fam not in DERIVED_ARTEFACT_FAMILIES:
            net_new.update(fresh)

    # --- measurement 4: what does it buy the fill substrate?
    units = depth_population(tape_root)
    depth_legs = {leg for legs in units.values() for leg in legs}
    hit_legs = sorted(set(net_new) & depth_legs)
    already = resolve_market_results(sorted(depth_legs), root=tape_root) if depth_legs else None
    n_units_newly_full = 0
    if already is not None and hit_legs:
        resolved_now = set(already.resolved)
        touched = {event_unit(t) for t in hit_legs}
        for u in touched:
            legs = units.get(u, set())
            if legs and not legs <= resolved_now and legs <= (resolved_now | set(net_new)):
                n_units_newly_full += 1
    # --- measurement 4b: the same question for the SPORTS PRICE substrate. The depth family
    # is the maker-fill substrate; `sports_pairs` is the substrate every sports TAKER study
    # (S7/S7c/S11/S13/S24/Q24) has ever run on, and its own kills were data-adequacy kills.
    # A label that lands there is worth something different from one that lands on depth.
    price_legs: Set[str] = set()
    sp_dir = os.path.join(tape_root, "sports_pairs")
    if os.path.isdir(sp_dir):
        for path in iter_family_files(sp_dir):
            with open(path, "rb") as fh:
                for raw in fh:
                    if b'"ticker"' not in raw:
                        continue
                    try:
                        rec = json.loads(raw.decode("utf-8", "replace"))
                    except Exception:
                        continue
                    _collect_market_legs(rec, price_legs)
    sp_already = resolve_market_results(sorted(price_legs), root=tape_root) if price_legs else None
    sp_hits = sorted(set(net_new) & price_legs)
    sports_pairs_incremental = {
        "n_price_legs": len(price_legs),
        "n_price_legs_resolvable_today": len(sp_already.resolved) if sp_already else 0,
        "n_net_new_landing_on_price_legs": len(sp_hits),
        "n_price_legs_after": (len(sp_already.resolved) if sp_already else 0) + len(sp_hits),
        "sample_hits": sp_hits[:5],
    }

    depth_incremental = {
        "n_depth_units": len(units),
        "n_depth_legs": len(depth_legs),
        "n_net_new_labels_offered": len(net_new),
        "n_net_new_landing_on_depth_legs": len(hit_legs),
        "n_depth_units_newly_fully_labeled": n_units_newly_full,
        "sample_hits": hit_legs[:5],
    }

    verdict = (
        "REGISTRY-RECALL-GAP" if registry_gap["undeclared_populated"] else "REGISTRY-COMPLETE-ON-THIS-DETECTOR"
    )
    return {
        "schema_version": "settlement_source_recall_audit.v1",
        "tape_root": tape_root,
        "declared_sources": declared,
        "family_scan": {f: {k: v for k, v in s.items() if not k.startswith("_")}
                        for f, s in scans.items()},
        "registry_gap": registry_gap,
        "yield": yields,
        "depth_incremental": depth_incremental,
        "sports_pairs_incremental": sports_pairs_incremental,
        "verdict": verdict,
        "verdict_caveat": (
            "Detection is key-name based on `result`/`status` only (core.result_evidence's "
            "published recall limit). A clean verdict means 'no result/status-shaped "
            "undeclared source', NEVER 'the registry is complete'. `n_net_new` is a LABEL "
            "count, not an edge: quote `depth_incremental` beside it or the number overstates "
            "what any probe could score."
        ),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tape-root", default=DEFAULT_TAPE_ROOT)
    ap.add_argument("--json-out", default="reports/settlement_source_recall_audit.json")
    ap.add_argument("--json", action="store_true", help="print the report to stdout")
    args = ap.parse_args(argv)
    rep = audit(args.tape_root)
    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
        with open(args.json_out, "w") as fh:
            json.dump(rep, fh, indent=1, sort_keys=True)
            fh.write("\n")
    if args.json:
        print(json.dumps(rep, indent=1, sort_keys=True))
    else:
        print(f"verdict: {rep['verdict']}")
        for cls, fams in rep["registry_gap"].items():
            print(f"  {cls:24s} {len(fams):3d}  {', '.join(fams) if fams else '-'}")
        for fam, y in rep["yield"].items():
            print(f"  yield[{fam}]: labeled={y['n_labeled_tickers']} overlap={y['n_resolver_overlap']} "
                  f"agree={y['n_agree_on_overlap']} net_new={y['n_net_new']} "
                  f"derived={y['derived_artefact']}")
        d = rep["depth_incremental"]
        print(f"  depth: units={d['n_depth_units']} legs={d['n_depth_legs']} "
              f"offered={d['n_net_new_labels_offered']} landing={d['n_net_new_landing_on_depth_legs']} "
              f"units_newly_full={d['n_depth_units_newly_fully_labeled']}")
        sp = rep["sports_pairs_incremental"]
        print(f"  sports_pairs: legs={sp['n_price_legs']} resolvable_today={sp['n_price_legs_resolvable_today']} "
              f"landing={sp['n_net_new_landing_on_price_legs']} after={sp['n_price_legs_after']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
