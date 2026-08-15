#!/usr/bin/env python3
"""Idle-run policy (c) — data-quality deep-dive: is the DEPTH tape's outcome-label
substrate adequate to score a queue-aware fill-sim OFFLINE, and for which market class?

LOOP-QUEUE.md protocol v3, 2026-08-15. READ-ONLY and FULLY OFFLINE: this module opens
committed tape files and nothing else — no network, no credentials, no orders, no writes
outside `reports/`. It emits a DATA-ADEQUACY description: no P&L, no CI, no bootstrap, no
registry flip (test-pinned — see `tests/test_depth_label_substrate_census.py`).

WHY THIS QUESTION. `tape/orderbook_depth/` is the ONLY family that carries both sides of a
real resting book, so every maker-side candidate this repo has ever tested (S6/S13/S19/S21/
S23/S29/S68/S78/S80) had to score its simulated fills against it. Scoring a fill needs a
y-label — a settled outcome — and the recurring idea-stage kill of the last month has been
some form of "we have no settled outcomes to join to" (Q21 round #30's universe_sweep kills:
373/1,003,235 tickers broker_truth-resolvable, all on one day; round #31's three kills;
Q24's 0/81 join; S21's L9/L43 disjoint-window death). Nobody had ever asked the same
question of the DEPTH family itself — the one that actually hosts the fill question.

The answer is NOT obvious a priori, because the outcome corpus is fragmented across ten
declared sources (`core/settlement_sources.py`), three of which are EMBEDDED inside another
family's schema rather than living in a settlement-named directory. A census that scans only
`tape/settlement_ledger/` + the `tape/qNN_settlement_cache/` dirs — the naive union, and the
shape most people would write — reaches a materially different number than the sanctioned
resolver does. This module therefore resolves through `core.settlement_sources.
resolve_market_results` (the single sanctioned resolver) and reports the naive-union subset
alongside it, so the gap between the two is a measured number rather than an assumption.

THREE MEASUREMENTS, each falsifiable from committed bytes:

1. `population` — every distinct `ticker` in `tape/orderbook_depth/`, its snapshot count, its
   first/last `captured_at`, and the day-files it appears in, bucketed into a `class`
   (`crypto` = KXBTC/KXETH hourly bracket ladders · `sports` = a `*GAME*` series ·
   `other` = everything else). No sampling: the whole committed family.
2. `label_coverage` — each ticker resolved through `resolve_market_results`. Reported per
   class AND per source, splitting `resolved` (binary broker_truth outcome) from
   `non_binary` (L52 `scalar`) from `listed_unsettled` (listed is NOT settled) from
   `unresolved`. An unresolved ticker is COUNTED, never dropped.
3. `unit_readiness` — the load-bearing one. The bootstrap unit for a fill-sim on this tape is
   the EVENT (L6: crypto hour-ladder / sports game), never the individual bracket, so
   readiness is computed per `event_ticker` (the ticker minus its final `-LEAF` segment):
   a unit is `probe_ready` iff EVERY one of its depth-covered legs resolves to a binary
   outcome AND the unit carries >= `MIN_SNAPSHOTS_PER_UNIT` depth snapshots. Partially
   labeled units are reported separately and never counted as ready — a fill-sim that scores
   only the labeled legs of a ladder silently conditions away the catastrophic wing (L41/L86).

4. `fill_observability` — added POST-HOC, AFTER the first run of measurement 3, and kept
   strictly separate from the pre-registered verdict for that reason (the floor below was NOT
   re-tuned to this result — see L355). Measurement 3's unit-level snapshot floor turned out
   to be VACUOUS for a multi-leg ladder: a 188-bracket crypto hour trivially carries >= 2
   snapshots across the unit while every individual bracket carries exactly one. A fill-sim
   observes a RESTING ORDER on ONE leg, so the observability question is per-LEG:
   `median_snapshots_per_leg` and `frac_legs_with_ge_2_snapshots` (the fraction of legs that
   have any forward interval at all). Reported per class, never merged into the verdict above.

5. `fill_observability_ready_only` — added 2026-08-15 AFTER an independent `verifier` refuted
   the first cut's headline. Measurement 4 is a CLASS-WIDE statistic: on crypto it is computed
   over all 101,060 legs, 40,186 of which sit outside the probe-ready set entirely (unlabeled,
   or in a partially-labeled unit), and those dilute it. Quoting a class-wide observability
   number NEXT TO a probe-ready unit count is a conflation — the two describe different
   populations and here they point in OPPOSITE directions (class-wide crypto median 1.0
   snapshots/leg and 38.25% with a forward interval; conditioned on the 418 probe-ready units,
   median 2.0 and 57.58%). This block therefore recomputes observability CONDITIONED ON the
   probe-ready units, and adds the two counts that actually decide runnability:
   `n_units_every_leg_ge_2` (units where EVERY leg has a forward interval) and
   `n_units_all_legs_single` (units where no leg does), plus the forward-gap CADENCE for the
   former — because "how often is a resting order re-observed" is the real fill-sim constraint.
   `duplicate_row_accounting` reports how much of `frac_legs_with_ge_2_snapshots` rests on
   exact `(ticker, captured_at)` duplicate rows (L282), since a duplicated row is not a second
   observation.

PRE-REGISTERED FLOORS (fixed BEFORE the first run of this module, never tuned to the
result — the L311/L321 pre-registration discipline applied to an adequacy verdict):

  MIN_SNAPSHOTS_PER_UNIT = 2   a fill question needs at least one forward INTERVAL between
                               two book observations (the `q51_trade_print_joinability`
                               interval-coverage argument); one snapshot answers nothing.
  MIN_READY_UNITS        = 30  bootstrap-unit floor. Strictly above the L41 10-event floor
                               prior probes used, because a block bootstrap over <30 units
                               produces a CI whose width is dominated by the unit count.
  MIN_DISTINCT_DAYS      = 5   L6 independence: 30 units inside one session are one
                               correlated draw. Five distinct capture days is the same
                               spread the G4 sports gate used.

VERDICT GRAMMAR (per class, and only per class — this module issues no strategy verdict):
  `SUBSTRATE-ADEQUATE`   n_probe_ready_units >= MIN_READY_UNITS AND
                         n_distinct_ready_days >= MIN_DISTINCT_DAYS
  `SUBSTRATE-INADEQUATE` otherwise, with `binding_shortfall` naming WHICH floor failed.
An ADEQUATE verdict says a probe on that class is RUNNABLE offline. It says NOTHING about
whether an edge exists there — the real-ask CI bar is untouched by this file.

HONEST LIMITS, stated here so they travel with any quoted number:
  * A ticker present in the depth tape whose event never settled inside the capture window is
    genuinely unlabelable from committed bytes; it is `unresolved`, not a defect.
  * `crypto_hourly.previous_settlement` is a broker_truth source per its own record tag, but
    its outcomes and the `settlement_ledger`/q-cache outcomes cover DISJOINT ticker sets on
    this tape (measured, `cross_source_overlap`), so no cross-source agreement rate can be
    computed. The internal consistency check that IS available — exactly one `yes` per MECE
    bracket ladder — is reported as `ladder_coherence`.
  * The pre-registered verdict answers LABEL adequacy at the bootstrap-unit level. It does
    NOT answer whether a resting order's fate is observable; `fill_observability_ready_only`
    does, and it is the ONLY observability block that may be quoted beside a probe-ready unit
    count (see measurement 5 — the class-wide block is a different population).
  * Depth records carry no `close_time`, so "snapshots before close" is NOT computed here;
    `MIN_SNAPSHOTS_PER_UNIT` is a raw snapshot count. A probe still owes its own
    entry-before-close discipline (L69).

Run:
    python3 scripts/depth_label_substrate_census.py
    python3 scripts/depth_label_substrate_census.py --json-out reports/x.json --tape-root tape
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from glob import glob
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from core.timeutil import parse_iso_utc
from core.settlement_sources import (
    DEFAULT_TAPE_ROOT,
    SETTLEMENT_SOURCES,
    declared_source_names,
    resolve_market_results,
)

SCHEMA_VERSION = "depth_label_substrate_census.v1"

# ── pre-registered floors (see the module docstring; do not tune to a result) ──────────
MIN_SNAPSHOTS_PER_UNIT = 2
MIN_READY_UNITS = 30
MIN_DISTINCT_DAYS = 5

# the naive union a hand-written census would scan, kept ONLY so the gap to the sanctioned
# resolver is a measured number rather than an assumption
NAIVE_UNION_SOURCE_NAMES: Tuple[str, ...] = ("settlement_ledger",)
NAIVE_UNION_CACHE_GLOB = "q*_settlement_cache"

CRYPTO_SERIES = ("KXBTC", "KXETH")


def series_of(ticker: str) -> str:
    """Leading series token of a Kalshi ticker (`KXBTC-26AUG1421-B54250` -> `KXBTC`)."""
    return ticker.split("-", 1)[0]


def event_of(ticker: str) -> Optional[str]:
    """The ticker minus its final `-LEAF` segment — the bootstrap unit (L6).

    Returns None for a ticker with no leaf segment: a unit cannot be inferred, and guessing
    one would silently merge unrelated markets."""
    if "-" not in ticker:
        return None
    head, _, leaf = ticker.rpartition("-")
    if not head or not leaf:
        return None
    return head


def class_of(ticker: str) -> str:
    """`crypto` / `sports` / `other` — the three populations whose adequacy differs."""
    s = series_of(ticker)
    if s in CRYPTO_SERIES:
        return "crypto"
    if "GAME" in s:
        return "sports"
    return "other"


def _day_of_path(path: str) -> str:
    base = os.path.basename(path)
    return base[3:13] if base.startswith("dt=") else base


def scan_depth_population(tape_root: str = DEFAULT_TAPE_ROOT) -> Dict[str, Dict[str, Any]]:
    """{ticker: {n_snapshots, days:[...], first_captured_at, last_captured_at}} over the whole
    committed `orderbook_depth` family. A malformed line is COUNTED (`_n_bad_lines`), never
    silently skipped."""
    out: Dict[str, Dict[str, Any]] = {}
    bad = 0
    for path in sorted(glob(os.path.join(tape_root, "orderbook_depth", "dt=*.jsonl"))):
        day = _day_of_path(path)
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    bad += 1
                    continue
                t = rec.get("ticker")
                if not isinstance(t, str) or not t:
                    bad += 1
                    continue
                ts = rec.get("captured_at")
                e = out.get(t)
                if e is None:
                    out[t] = {"n_snapshots": 1, "days": {day},
                              "first_captured_at": ts, "last_captured_at": ts}
                else:
                    e["n_snapshots"] += 1
                    e["days"].add(day)
                    if isinstance(ts, str):
                        if not isinstance(e["first_captured_at"], str) or ts < e["first_captured_at"]:
                            e["first_captured_at"] = ts
                        if not isinstance(e["last_captured_at"], str) or ts > e["last_captured_at"]:
                            e["last_captured_at"] = ts
    out["_n_bad_lines"] = {"n_snapshots": bad, "days": set(),
                           "first_captured_at": None, "last_captured_at": None}
    return out


def naive_union_labels(tape_root: str = DEFAULT_TAPE_ROOT) -> Dict[str, str]:
    """The label map a hand-written census reaches: `settlement_ledger` + the `qNN` caches.

    Deliberately NOT the sanctioned path — its only purpose is to measure the gap to
    `resolve_market_results`, which also reads the three EMBEDDED sources."""
    labels: Dict[str, str] = {}
    for path in sorted(glob(os.path.join(tape_root, "settlement_ledger", "dt=*.jsonl"))):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                t, res = rec.get("ticker"), rec.get("result")
                if isinstance(t, str) and res in ("yes", "no"):
                    labels.setdefault(t, "settlement_ledger")
    for path in sorted(glob(os.path.join(tape_root, NAIVE_UNION_CACHE_GLOB, "*.json"))):
        try:
            blob = json.load(open(path))
        except Exception:
            continue
        fam = os.path.basename(os.path.dirname(path))
        for t, v in (blob.get("markets") or {}).items():
            if isinstance(v, Mapping) and v.get("result") in ("yes", "no"):
                labels.setdefault(t, fam)
    return labels


def ladder_coherence(tape_root: str = DEFAULT_TAPE_ROOT,
                     restrict_to: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Internal consistency of the embedded crypto label source: a MECE bracket ladder must
    settle EXACTLY ONE `B`-bracket `yes`.

    This is the only validation available for that source on this tape (its ticker set is
    disjoint from every other source's — see `cross_source_overlap`), so it is reported, not
    assumed. Reads `crypto_hourly.previous_settlement` through the same declared source the
    resolver uses."""
    per_event: Dict[str, Dict[str, str]] = defaultdict(dict)
    for path in sorted(glob(os.path.join(tape_root, "crypto_hourly", "dt=*.jsonl"))):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                ps = rec.get("previous_settlement") or {}
                if ps.get("status") != "settled":
                    continue
                for t, res in (ps.get("results") or {}).items():
                    if res in ("yes", "no"):
                        e = event_of(t)
                        if e and (restrict_to is None or e in restrict_to):
                            per_event[e][t] = res
    n_ok = n_bad = 0
    violations: List[str] = []
    for e, legs in per_event.items():
        brackets = {t: r for t, r in legs.items() if t.rpartition("-")[2].startswith("B")}
        if not brackets:
            continue
        n_yes = sum(1 for r in brackets.values() if r == "yes")
        if n_yes == 1:
            n_ok += 1
        else:
            n_bad += 1
            if len(violations) < 20:
                violations.append(f"{e}:{n_yes}")
    return {"n_ladders_checked": n_ok + n_bad, "n_exactly_one_yes": n_ok,
            "n_violations": n_bad, "violation_examples": violations,
            "scope": ("the depth-covered crypto units only" if restrict_to is not None
                      else "the whole crypto_hourly corpus, NOT only its depth-covered units")}


def fill_observability(pop: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Per-LEG snapshot counts by class — the observability half, POST-HOC (see docstring 4).

    A resting maker order lives on ONE leg, so a leg with a single snapshot has NO forward
    interval: its fill is unobservable no matter how many snapshots its sibling brackets
    carry. Deliberately NOT folded into `verdict`, whose floors were pre-registered."""
    out: Dict[str, Dict[str, Any]] = {}
    for cls in ("crypto", "sports", "other"):
        xs = sorted(v["n_snapshots"] for t, v in pop.items() if class_of(t) == cls)
        if not xs:
            out[cls] = {"n_legs": 0, "median_snapshots_per_leg": None,
                        "mean_snapshots_per_leg": None, "max_snapshots_per_leg": None,
                        "n_legs_with_ge_2_snapshots": 0, "frac_legs_with_ge_2_snapshots": None}
            continue
        ge2 = sum(1 for x in xs if x >= MIN_SNAPSHOTS_PER_UNIT)
        out[cls] = {
            "n_legs": len(xs),
            "median_snapshots_per_leg": _median(xs),
            "mean_snapshots_per_leg": round(sum(xs) / len(xs), 4),
            "max_snapshots_per_leg": max(xs),
            "n_legs_with_ge_2_snapshots": ge2,
            "frac_legs_with_ge_2_snapshots": round(ge2 / len(xs), 4),
        }
    return out


def ready_unit_observability(pop: Mapping[str, Any],
                             units: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Observability CONDITIONED ON the probe-ready units of one class (measurement 5).

    This is the block that may be quoted beside a probe-ready unit count; the class-wide
    `fill_observability` may not, because it is computed over a population that includes legs
    no probe would ever score."""
    ready = [e for e, u in units.items() if u["probe_ready"]]
    legs = sorted(n for e in ready for n in _leg_counts(pop, e, units))
    every2, single, days2 = [], [], set()
    for e in ready:
        counts = _leg_counts(pop, e, units)
        if counts and all(c >= MIN_SNAPSHOTS_PER_UNIT for c in counts):
            every2.append(e)
            days2 |= set(units[e]["days"])
        elif counts and all(c < MIN_SNAPSHOTS_PER_UNIT for c in counts):
            single.append(e)
    ge2 = sum(1 for x in legs if x >= MIN_SNAPSHOTS_PER_UNIT)
    return {
        "n_ready_units": len(ready),
        "n_ready_legs": len(legs),
        "median_snapshots_per_leg": _median(legs),
        "frac_legs_with_ge_2_snapshots": round(ge2 / len(legs), 4) if legs else None,
        "n_units_every_leg_ge_2": len(every2),
        "n_distinct_days_every_leg_ge_2": len(days2),
        "n_units_all_legs_single": len(single),
        "units_every_leg_ge_2": sorted(every2),
    }


def _leg_counts(pop: Mapping[str, Any], event: str,
                units: Mapping[str, Mapping[str, Any]]) -> List[int]:
    return [v["n_snapshots"] for t, v in pop.items() if event_of(t) == event]


def forward_gap_profile(tape_root: str, events: Iterable[str]) -> Dict[str, Any]:
    """Minutes between CONSECUTIVE DISTINCT observations of the same leg, over `events`.

    Exact `(ticker, captured_at)` repeats are collapsed first — a duplicated row is not a
    second observation (L282). Answers the question the snapshot COUNT cannot: at what cadence
    would a resting order be re-observed?"""
    want = set(events)
    seen: Dict[str, set] = defaultdict(set)
    for path in sorted(glob(os.path.join(tape_root, "orderbook_depth", "dt=*.jsonl"))):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                t, ts = rec.get("ticker"), rec.get("captured_at")
                if isinstance(t, str) and isinstance(ts, str) and event_of(t) in want:
                    seen[t].add(ts)
    gaps: List[float] = []
    for t, stamps in seen.items():
        eps = sorted(parse_iso_utc(x).timestamp() for x in stamps)
        gaps.extend((b - a) / 60.0 for a, b in zip(eps, eps[1:]))
    gaps.sort()
    return {"n_legs": len(seen), "n_gaps": len(gaps),
            "median_forward_gap_minutes": round(_median(gaps), 2) if gaps else None,
            "p25_forward_gap_minutes": round(gaps[len(gaps) // 4], 2) if gaps else None,
            "p75_forward_gap_minutes": round(gaps[(3 * len(gaps)) // 4], 2) if gaps else None}


def duplicate_row_accounting(tape_root: str) -> Dict[str, Any]:
    """How much of `frac_legs_with_ge_2_snapshots` rests on exact `(ticker, captured_at)`
    repeats (L282's duplicate class). A duplicated row is not a second observation, so the
    dedup-adjusted fraction is the honest one."""
    rows: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for path in sorted(glob(os.path.join(tape_root, "orderbook_depth", "dt=*.jsonl"))):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                t = rec.get("ticker")
                if isinstance(t, str):
                    rows[t][rec.get("captured_at")] += 1
    out: Dict[str, Any] = {}
    for cls in ("crypto", "sports", "other"):
        ts = [t for t in rows if class_of(t) == cls]
        if not ts:
            out[cls] = {"n_legs": 0, "n_duplicate_rows": 0, "frac_ge_2_raw": None,
                        "frac_ge_2_deduped": None, "inflation_pp": None}
            continue
        dup = sum(sum(n - 1 for n in rows[t].values() if n > 1) for t in ts)
        raw = sum(1 for t in ts if sum(rows[t].values()) >= MIN_SNAPSHOTS_PER_UNIT)
        ded = sum(1 for t in ts if len(rows[t]) >= MIN_SNAPSHOTS_PER_UNIT)
        out[cls] = {"n_legs": len(ts), "n_duplicate_rows": dup,
                    "frac_ge_2_raw": round(raw / len(ts), 4),
                    "frac_ge_2_deduped": round(ded / len(ts), 4),
                    "inflation_pp": round(100.0 * (raw - ded) / len(ts), 2)}
    return out


def census(tape_root: str = DEFAULT_TAPE_ROOT) -> Dict[str, Any]:
    """The whole census. Pure over committed bytes; no network, no writes."""
    pop = scan_depth_population(tape_root)
    n_bad_lines = pop.pop("_n_bad_lines")["n_snapshots"]
    tickers = sorted(pop)
    report = resolve_market_results(tickers, root=tape_root)
    naive = naive_union_labels(tape_root)

    by_class: Dict[str, Dict[str, Any]] = {}
    for cls in ("crypto", "sports", "other"):
        ts = [t for t in tickers if class_of(t) == cls]
        res = [t for t in ts if t in report.resolved]
        by_class[cls] = {
            "n_tickers": len(ts),
            "n_snapshots": sum(pop[t]["n_snapshots"] for t in ts),
            "n_resolved": len(res),
            "n_non_binary": sum(1 for t in ts if t in report.non_binary),
            "n_listed_unsettled": sum(1 for t in ts if t in report.listed_unsettled),
            "n_unresolved": len(ts) - len(res) - sum(1 for t in ts if t in report.non_binary)
                            - sum(1 for t in ts if t in report.listed_unsettled),
            "n_resolved_by_naive_union": sum(1 for t in res if t in naive),
            "resolved_by_source": _count_by(report, res),
        }

    units = _unit_readiness(pop, report, tape_root)
    verdicts = {cls: _verdict(u) for cls, u in units.items()}
    return {
        "schema_version": SCHEMA_VERSION,
        "tape_root": tape_root,
        "floors": {"MIN_SNAPSHOTS_PER_UNIT": MIN_SNAPSHOTS_PER_UNIT,
                   "MIN_READY_UNITS": MIN_READY_UNITS,
                   "MIN_DISTINCT_DAYS": MIN_DISTINCT_DAYS},
        "population": {
            "n_tickers": len(tickers),
            "n_snapshots": sum(pop[t]["n_snapshots"] for t in tickers),
            "n_day_files": len(glob(os.path.join(tape_root, "orderbook_depth", "dt=*.jsonl"))),
            "n_malformed_lines": n_bad_lines,
        },
        "label_coverage": {
            "sources_declared": list(declared_source_names()),
            "sources_absent_on_disk": list(report.sources_absent_on_disk),
            "per_source_hits": dict(report.per_source_hits),
            "n_resolved_total": len(report.resolved),
            "n_resolved_naive_union_only": len(
                [t for t in report.resolved if t in naive]),
            "naive_union_undercount_factor": round(
                len(report.resolved) / max(1, len([t for t in report.resolved if t in naive])), 2),
            "by_class": by_class,
        },
        "cross_source_overlap": _cross_source_overlap(report, naive),
        "ladder_coherence": ladder_coherence(tape_root),
        "ladder_coherence_depth_scoped": ladder_coherence(tape_root, restrict_to=set(units["crypto"])),
        "unit_readiness": {c: _summarize_units(u) for c, u in units.items()},
        "fill_observability": fill_observability(pop),
        "fill_observability_ready_only": _ready_only_block(pop, units, tape_root),
        "duplicate_row_accounting": duplicate_row_accounting(tape_root),
        "verdict": verdicts,
        "verdict_caveat": (
            "LABEL adequacy only, at the pre-registered floors. Observability is a SEPARATE, "
            "POST-HOC measurement and must be read from `fill_observability_ready_only`, which "
            "is conditioned on the same probe-ready units this verdict counts. The class-wide "
            "`fill_observability` block describes a DIFFERENT population (it includes legs no "
            "probe would score) and must never be quoted beside a probe-ready count — doing so "
            "is the conflation an independent verifier caught on 2026-08-15 (L355)."),
    }


def _ready_only_block(pop, units, tape_root: str) -> Dict[str, Any]:
    """Per-class measurement 5, plus the forward-gap cadence for the every-leg-observable
    subset (the population a fill-sim could actually run on)."""
    out: Dict[str, Any] = {}
    for cls, u in units.items():
        block = ready_unit_observability(pop, u)
        events = block.pop("units_every_leg_ge_2")
        block["forward_gap_profile"] = (forward_gap_profile(tape_root, events)
                                        if events else None)
        out[cls] = block
    return out


def _count_by(report, tickers: Iterable[str]) -> Dict[str, int]:
    out: Dict[str, int] = defaultdict(int)
    for t in tickers:
        out[report.resolved[t].source] += 1
    return dict(sorted(out.items()))


def _cross_source_overlap(report, naive: Mapping[str, str]) -> Dict[str, Any]:
    """How many resolved depth tickers carry a label from BOTH the embedded crypto source and
    the naive-union sources. Zero means no agreement rate is computable — an honest limit,
    not a clean bill."""
    emb = {t for t, m in report.resolved.items() if m.source == "crypto_hourly"}
    return {"n_embedded_crypto": len(emb), "n_naive_union": len(naive),
            "n_overlap": len(emb & set(naive)),
            "agreement_rate_computable": bool(emb & set(naive))}


def _unit_readiness(pop: Mapping[str, Any], report, tape_root: str) -> Dict[str, Dict[str, Any]]:
    """Per-class {event_ticker: {...}} readiness. A unit is ready only when EVERY depth-covered
    leg is labeled (partial labeling is reported, never counted ready — L41/L86)."""
    units: Dict[str, Dict[str, Any]] = {"crypto": {}, "sports": {}, "other": {}}
    grouped: Dict[str, List[str]] = defaultdict(list)
    for t in pop:
        e = event_of(t)
        if e:
            grouped[e].append(t)
    for e, legs in grouped.items():
        cls = class_of(legs[0])
        n_lab = sum(1 for t in legs if t in report.resolved)
        n_snap = sum(pop[t]["n_snapshots"] for t in legs)
        days = set()
        for t in legs:
            days |= pop[t]["days"]
        units[cls][e] = {
            "n_legs": len(legs), "n_labeled_legs": n_lab, "n_snapshots": n_snap,
            "days": sorted(days),
            "fully_labeled": n_lab == len(legs),
            "probe_ready": n_lab == len(legs) and n_snap >= MIN_SNAPSHOTS_PER_UNIT,
        }
    return units


def _summarize_units(units: Mapping[str, Any]) -> Dict[str, Any]:
    ready = [u for u in units.values() if u["probe_ready"]]
    ready_days = set()
    for u in ready:
        ready_days |= set(u["days"])
    partial = [u for u in units.values() if 0 < u["n_labeled_legs"] < u["n_legs"]]
    return {
        "n_units": len(units),
        "n_fully_labeled": sum(1 for u in units.values() if u["fully_labeled"]),
        "n_partially_labeled": len(partial),
        "n_unlabeled": sum(1 for u in units.values() if u["n_labeled_legs"] == 0),
        "n_probe_ready": len(ready),
        "n_distinct_ready_days": len(ready_days),
        "ready_day_span": [min(ready_days), max(ready_days)] if ready_days else [],
        "median_snapshots_per_ready_unit": _median([u["n_snapshots"] for u in ready]),
    }


def _median(xs: List[int]) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _verdict(units: Mapping[str, Any]) -> Dict[str, Any]:
    s = _summarize_units(units)
    shortfall: List[str] = []
    if s["n_probe_ready"] < MIN_READY_UNITS:
        shortfall.append(f"n_probe_ready={s['n_probe_ready']} < MIN_READY_UNITS={MIN_READY_UNITS}")
    if s["n_distinct_ready_days"] < MIN_DISTINCT_DAYS:
        shortfall.append(
            f"n_distinct_ready_days={s['n_distinct_ready_days']} < MIN_DISTINCT_DAYS={MIN_DISTINCT_DAYS}")
    return {
        "verdict": "SUBSTRATE-ADEQUATE" if not shortfall else "SUBSTRATE-INADEQUATE",
        "binding_shortfall": shortfall,
        "n_probe_ready": s["n_probe_ready"],
        "n_distinct_ready_days": s["n_distinct_ready_days"],
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tape-root", default=DEFAULT_TAPE_ROOT)
    ap.add_argument("--json-out", default="reports/depth_label_substrate_census.json")
    ap.add_argument("--json", action="store_true", help="print the report to stdout")
    args = ap.parse_args(argv)
    rep = census(args.tape_root)
    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
        with open(args.json_out, "w") as fh:
            json.dump(rep, fh, indent=1, sort_keys=True)
            fh.write("\n")
    if args.json:
        print(json.dumps(rep, indent=1, sort_keys=True))
    else:
        for cls, v in rep["verdict"].items():
            print(f"{cls:7s} {v['verdict']:22s} ready_units={v['n_probe_ready']:5d} "
                  f"ready_days={v['n_distinct_ready_days']:3d} {';'.join(v['binding_shortfall'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
