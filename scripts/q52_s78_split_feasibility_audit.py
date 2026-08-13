#!/usr/bin/env python3
"""q52_s78_split_feasibility_audit.py — is a chronological train/holdout split of the S78
toxicity-filtered-maker population actually feasible on committed tape, and if not, why?

Why this script exists (2026-08-13 idle-run policy (c)).
----------------------------------------------------------------------------------------
Q52's own status line (LOOP-QUEUE.md) gives the S78 blocker as a unit-count problem: "34
games is still short of what a pre-registered <=4-cell train/holdout design needs on both
sides of the split." Nobody had actually attempted the split and measured what it looks
like. This script does that.

**Verifier round 1 REFUTED the first version of this script's interpretation** (not its
arithmetic — every count reproduced independently to the digit). Three corrections are baked
into this version, and the finding this script now supports is narrower and more honest than
the original draft:

  1. **The "1-cell" framing was a straw man.** Q52's claim is about a <=4-CELL design; testing
     a single undivided split against the L41 n>=10 floor and calling it a contradiction drops
     Q52's own qualifier. At 4 cells, 34/4≈8.5 train and 29/4≈7.25 holdout per cell are BOTH
     below the L41 floor — Q52's stated reason holds once its qualifier is honored. This
     script now reports both the 1-cell split (34/29/0, clears L41) and the per-stated-cell-
     count arithmetic side by side, and does not claim to falsify Q52.
  2. **"Cleanly unimodal within each era" was unsupported.** Four percentiles are not a
     modality test. A 30-minute-bin histogram of the starved-era gaps (below) shows clusters
     near multiples of ~180 minutes (~180/360/540/900) — consistent with the VPS collector
     making sporadic, irregular passes (L117/L127/L177/L213/L304), not a single clean
     regime shift. The rich era genuinely is tight (1469/1498 gaps in [0,60) minutes); the
     starved era is not asserted to be unimodal, only reported by bin.
  3. **The July `kalshi_trades` day-files are NOT complete venue days.** They are a
     ticker-scoped BACKFILL of a specific 34-game list (`reports/
     q52_q54_trades_backfill_phase1_phase2.json::execution.coverage_is_ticker_scoped =
     true`, with its own coverage note: "day-files are a ticker-scoped backfill of the
     listed games only, NOT complete venue days; join against `manifest`, never against a
     whole dt= file assumed complete"). The 2026-08-03 file is a DIFFERENT process — one
     live, complete `public_markets_trades` sweep. So the July-side unit/series counts in
     this script reflect the BACKFILL's round-robin selection and its 50MB byte cap, not the
     true population of games that traded those days — any claim built on "which games/series
     appear in the July window" (the unit counts, the series-transfer numbers) inherits that
     selection bias and should be read as a property of the backfill, not of the market.
     This is now surfaced explicitly in the output (`backfill_scope_caveat`), read from the
     manifest file itself rather than asserted in prose.

**What is NOT confounded by (3):** `orderbook_depth` is a separate, independently-running
collector never touched by the trade backfill. `book_cadence_by_era`'s `capture_id` counts
are taken over EVERY row in each day's whole depth file (not filtered to backfilled tickers),
so it is unconfounded by the backfill — but that block is keyed by TRADE day, which has a
3-week hole straddling the era boundary itself (07-12 -> 08-03), so it cannot show a
boundary step on its own. `era_boundary_evidence` fixes that: it scans EVERY `orderbook_depth`
day file within a window of the boundary regardless of whether a trade happened that day. As
of this run it shows a real, sharp step — 2026-07-22: 25 distinct capture instants ->
2026-07-23: 3 — consistent with the already-documented VPS-collector-death lesson chain
(L117/L127/L177/L213/L304), not a new discovery. It is NOT a claim that every pre-boundary day
is uniformly dense (2026-07-19 in the same window is 6, 2026-07-20 is 7 — both single digits,
both pre-boundary): the collector was already somewhat irregular before the step, and the
step itself is what's load-bearing for the "different fill regime" argument, not a uniform
"tens vs ones" contrast.

This is a data-quality / feasibility characterization: NO fill is simulated, NO P&L or CI is
computed, NO registry status changes. The two-agent verdict rule (LOOP-QUEUE.md step 5) does
not strictly apply to this class of output (same posture as the Q44/Q54 status-update
precedent), but a `verifier` pass was run anyway: round 1 REFUTED the first interpretation
(this docstring's corrected version); round 2 re-checked the correction and returned
CONFIRMED-WITH-CORRECTIONS (two further prose-accuracy defects — an evidence citation that
pointed at a field which couldn't show what was claimed, and this same "tens vs single
digits" overstatement — fixed in this version, plus the histogram/overflow-bin/dead-code nits
below). The redundancy earned its keep twice.

Settlement is read exclusively through `core.settlement_sources.resolve_market_results` (the
one sanctioned resolver, L300) — never a single family, and never re-derived locally.
Settlement is used ONLY as a binary/non-binary LABEL CLASS here (does this game have a
result at all), never by direction: this script is deliberately outcome-blind, the same
discipline the S78/S79 sealed probes hold, because any markout or fill number belongs to
S78's own pre-registered probe, not to a feasibility audit that runs before it.

Read-only, fully offline, no network. Run (from any working directory — see the settlement
root fix below):
    python3 scripts/q52_s78_split_feasibility_audit.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
from typing import Dict, List, Sequence, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from core.settlement_sources import ResolutionReport, resolve_market_results  # noqa: E402

TRADE_TAPE_GLOB = os.path.join(REPO, "tape", "kalshi_trades", "dt=*.jsonl")
DEPTH_TAPE_GLOB = os.path.join(REPO, "tape", "orderbook_depth", "dt=*.jsonl")
# core.settlement_sources.resolve_market_results defaults root="tape" (RELATIVE). A caller
# that anchors every other path via absolute REPO but leaves this one relative gets a SILENT
# 0-resolved report from any other working directory (rc=0, no error) — verifier round 1
# caught this live (`cd /tmp && python3 .../this_script.py` -> "0 resolved", n_train=0,
# n_holdout=0, no warning). Always pass an absolute root explicitly (new lesson candidate).
DEFAULT_SETTLEMENT_ROOT = os.path.join(REPO, "tape")
BACKFILL_MANIFEST_PATH = os.path.join(REPO, "reports", "q52_q54_trades_backfill_phase1_phase2.json")

MIN_DEPTH_SNAPSHOTS = 2  # a unit needs >=2 same-day book instants to carry ANY fill signal
L41_MIN_UNITS = 10  # the repo's standing minimum-bootstrap-units floor
Q52_STATED_CELL_COUNT = 4  # the "<=4-cell" design Q52's own status line qualifies its claim with
EXCLUDE_SERIES_PREFIXES = ("KXMVE",)  # L31: fake AMM-sized series, never a real game unit

# Era boundary used for the book-cadence comparison. Cross-checked against the pre-existing
# L117/L127/L177/L213/L304 VPS-collector-death lesson chain, which already dates the collapse
# to ~2026-07-23. Verifier round 2's NEW-1: the ONLY per-day capture_id counts this script
# emitted (`book_cadence_by_era`) are keyed by TRADE day, which has a 3-week hole straddling
# this exact boundary (07-12 -> 08-03) — so the boundary was not actually checkable against
# anything the output showed, despite the docstring saying "see the output". Fixed below by
# `depth_capture_id_counts_around_boundary()`, which scans the FULL `orderbook_depth` day
# range (independent of which days had a trade) and is included in the output as
# `era_boundary_evidence` — the claim is now checkable against what the script actually
# emits, not just against this comment.
RICH_ERA_LAST_DAY = "2026-07-22"
STARVED_ERA_FIRST_DAY = "2026-07-23"
ERA_BOUNDARY_EVIDENCE_WINDOW_DAYS = 5  # days shown on each side of the boundary


def _day_of(path: str) -> str:
    base = os.path.basename(path)
    return base[len("dt="):-len(".jsonl")]


def _iter_jsonl(path: str):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except (ValueError, TypeError):
                continue


def depth_capture_id_counts_around_boundary(depth_glob: str = DEPTH_TAPE_GLOB,
                                            window_days: int = ERA_BOUNDARY_EVIDENCE_WINDOW_DAYS
                                            ) -> Dict[str, int]:
    """Distinct `capture_id` count per day for EVERY `orderbook_depth` day file within
    `window_days` of the era boundary — independent of which days had a trade. Unlike
    `book_cadence_by_era` (keyed by trade day, which has no row between 07-12 and 08-03), this
    scans the depth tape's own day range directly, so the era-boundary claim in the module
    docstring is checkable against a field the output actually emits (verifier round 2, NEW-1:
    the prior version's docstring pointed at `book_cadence_by_era` for this evidence, but that
    block cannot show a boundary it has no days near)."""
    from datetime import date, timedelta

    boundary = date.fromisoformat(STARVED_ERA_FIRST_DAY)
    lo = (boundary - timedelta(days=window_days)).isoformat()
    hi = (boundary + timedelta(days=window_days - 1)).isoformat()
    counts: Dict[str, int] = {}
    for path in sorted(glob.glob(depth_glob)):
        day = _day_of(path)
        if not (lo <= day <= hi):
            continue
        cap_ids = set()
        for r in _iter_jsonl(path):
            cid = r.get("capture_id")
            if cid:
                cap_ids.add(cid)
        counts[day] = len(cap_ids)
    return counts


def is_game_ticker(ticker: str) -> bool:
    series = ticker.split("-")[0]
    if "GAME" not in series:
        return False
    return not any(series.startswith(p) for p in EXCLUDE_SERIES_PREFIXES)


def game_unit(ticker: str) -> str:
    """Collapse an outcome-leg ticker to its game unit. Multi-outcome games (3-way soccer,
    -TIE legs) share this prefix; single-outcome games ARE this prefix. Matches the
    convention already used by `scripts/q56_s80_rederive.py::game` (rsplit on the last '-')."""
    return ticker.rsplit("-", 1)[0]


def traded_tickers_by_day(trade_glob: str = TRADE_TAPE_GLOB) -> Dict[str, set]:
    """day -> set of distinct GAME-series tickers that printed a trade that day."""
    out: Dict[str, set] = {}
    for path in sorted(glob.glob(trade_glob)):
        day = _day_of(path)
        tickers = out.setdefault(day, set())
        for r in _iter_jsonl(path):
            tk = r.get("ticker")
            if isinstance(tk, str) and is_game_ticker(tk):
                tickers.add(tk)
    return out


def depth_snapshot_counts_by_day(tickers_by_day: Dict[str, set],
                                  depth_glob: str = DEPTH_TAPE_GLOB
                                  ) -> Tuple[Dict[str, Dict[str, int]], Dict[str, int]]:
    """For each day with traded tickers, count same-day `orderbook_depth` snapshots per
    ticker, and separately the day's total distinct `capture_id` cardinality (a day-level
    cadence measure, independent of which tickers traded)."""
    per_ticker: Dict[str, Dict[str, int]] = {}
    capture_ids_by_day: Dict[str, int] = {}
    depth_days = {_day_of(p): p for p in glob.glob(depth_glob)}
    for day, wanted in tickers_by_day.items():
        path = depth_days.get(day)
        counts: Dict[str, int] = {}
        cap_ids = set()
        if path:
            for r in _iter_jsonl(path):
                cid = r.get("capture_id")
                if cid:
                    cap_ids.add(cid)
                tk = r.get("ticker")
                if tk in wanted:
                    counts[tk] = counts.get(tk, 0) + 1
        per_ticker[day] = counts
        capture_ids_by_day[day] = len(cap_ids)
    return per_ticker, capture_ids_by_day


def eligible_units_by_day(tickers_by_day: Dict[str, set],
                          depth_counts_by_day: Dict[str, Dict[str, int]],
                          min_snapshots: int = MIN_DEPTH_SNAPSHOTS
                          ) -> Dict[str, Dict[str, str]]:
    """day -> {game_unit: representative_ticker} for units clearing the depth-snapshot floor.
    Settlement is resolved in one batch call afterwards (never per-ticker, never re-derived)."""
    result: Dict[str, Dict[str, str]] = {}
    for day, tickers in tickers_by_day.items():
        counts = depth_counts_by_day.get(day, {})
        qualifying = [t for t in tickers if counts.get(t, 0) >= min_snapshots]
        units: Dict[str, str] = {}
        for t in sorted(qualifying):
            units.setdefault(game_unit(t), t)
        result[day] = units
    return result


def settled_units_by_day(units_by_day: Dict[str, Dict[str, str]],
                         settlement_root: str = DEFAULT_SETTLEMENT_ROOT
                         ) -> Tuple[Dict[str, List[str]], ResolutionReport]:
    """Filter each day's candidate units to those with a resolved BINARY settlement on any
    representative-outcome ticker for that game (multi-outcome games settle all legs
    together, so any one leg resolving is sufficient to know the game unit is decided)."""
    all_reps = {t for units in units_by_day.values() for t in units.values()}
    report = resolve_market_results(all_reps, root=settlement_root)
    resolved_tickers = set(report.resolved)
    out: Dict[str, List[str]] = {}
    for day, units in units_by_day.items():
        out[day] = sorted(u for u, rep in units.items() if rep in resolved_tickers)
    return out, report


def chronological_splits(settled_by_day: Dict[str, List[str]]
                         ) -> List[Tuple[str, int, int, int]]:
    """Every possible chronological cut point over the observed days: (cut_day,
    n_train_units_strictly_before, n_holdout_units_on_or_after, n_overlapping_units).
    A unit id (game prefix) could in principle repeat across days only if the same two teams
    played twice; overlap is reported, not assumed to be zero."""
    days = sorted(settled_by_day)
    out = []
    for i in range(1, len(days)):
        cut = days[i]
        train_units: set = set()
        for d in days[:i]:
            train_units |= set(settled_by_day[d])
        holdout_units: set = set()
        for d in days[i:]:
            holdout_units |= set(settled_by_day[d])
        overlap = train_units & holdout_units
        out.append((cut, len(train_units), len(holdout_units), len(overlap)))
    return out


def series_of(unit: str) -> str:
    return unit.split("-")[0]


def series_overlap(train_units: Sequence[str], holdout_units: Sequence[str]) -> Dict[str, object]:
    train_series = {series_of(u) for u in train_units}
    holdout_series = {series_of(u) for u in holdout_units}
    shared = train_series & holdout_series
    return {
        "n_train_series": len(train_series),
        "n_holdout_series": len(holdout_series),
        "n_shared_series": len(shared),
        "shared_series": sorted(shared),
        "n_train_units_in_shared_series": sum(1 for u in train_units if series_of(u) in shared),
        "n_holdout_units_in_shared_series": sum(1 for u in holdout_units if series_of(u) in shared),
    }


def intra_ticker_gap_minutes(tickers: set, depth_glob: str = DEPTH_TAPE_GLOB
                             ) -> Dict[str, List[float]]:
    """Consecutive same-day `captured_at` gaps (minutes) per ticker, split by trade era —
    re-derives L328's own metric (not assumed) to test whether its bimodality is an
    era-mixture artifact. Cross-day gaps are excluded by construction (one file per day)."""
    from core.timeutil import parse_iso_utc  # L136/L150: never bare datetime.fromisoformat

    by_era: Dict[str, List[float]] = {"rich": [], "starved": []}
    for path in sorted(glob.glob(depth_glob)):
        day = _day_of(path)
        era = "rich" if day <= RICH_ERA_LAST_DAY else "starved"
        per_ticker: Dict[str, List[float]] = {}
        for r in _iter_jsonl(path):
            tk = r.get("ticker")
            if tk not in tickers:
                continue
            ts = r.get("captured_at")
            if not isinstance(ts, str):
                continue
            per_ticker.setdefault(tk, []).append(parse_iso_utc(ts).timestamp())
        for tk, stamps in per_ticker.items():
            stamps.sort()
            for a, b in zip(stamps, stamps[1:]):
                by_era[era].append((b - a) / 60.0)
    return by_era


def _percentile(values: List[float], p: float):
    if not values:
        return None
    s = sorted(values)
    k = min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))
    return s[k]


def gap_histogram_30min_bins(values: List[float], max_bin_start: float = 960.0
                             ) -> List[List[object]]:
    """Coarse 30-minute-bin histogram, returned as an ORDERED list of `[bin_label, count]`
    pairs (not a dict) — verifier round 2's NEW finding: `main()` prints with
    `json.dumps(sort_keys=True)`, which would re-sort a dict's keys LEXICOGRAPHICALLY
    ("[0,30)" < "[270,300)" < "[30,60)"), silently discarding the numeric order this function
    builds. A list survives `sort_keys` untouched. The last bin is an explicit unbounded
    overflow ("[max_bin_start,+inf)"), not a finite-looking upper edge that would mislabel a
    5000-minute gap as if it were between 960 and 990 (verifier round 2 minor nit).

    Verifier round 1's finding this exists for: a 4-number percentile summary asserted
    "unimodal" over a distribution that is actually multi-modal (clusters near
    ~180/360/540/900 minutes) — a histogram makes multi-modality visible instead of requiring
    a prose claim the reader has to trust."""
    hist: Dict[float, int] = {}
    overflow = 0
    for v in values:
        if v >= max_bin_start:
            overflow += 1
            continue
        lo = 30.0 * int(v // 30.0)
        hist[lo] = hist.get(lo, 0) + 1
    pairs = [[f"[{lo:.0f},{lo + 30:.0f})", n] for lo, n in sorted(hist.items())]
    if overflow:
        pairs.append([f"[{max_bin_start:.0f},+inf)", overflow])
    return pairs


def backfill_scope_caveat(manifest_path: str = BACKFILL_MANIFEST_PATH) -> Dict[str, object]:
    """Read (never assert) whether the trade tape this audit reads is a complete-day capture
    or a ticker-scoped backfill, straight from the backfill script's own manifest. Verifier
    round 1: the July `kalshi_trades` day-files ARE a ticker-scoped backfill of one 34-game
    list, not complete venue days — any July-side unit/series count in this audit inherits
    that selection, and a reader must not treat it as a random day-sample. Missing manifest
    (e.g. an offline test fixture) is reported honestly, not silently assumed either way."""
    if not os.path.exists(manifest_path):
        return {"manifest_found": False, "coverage_is_ticker_scoped": None, "coverage_note": None}
    try:
        blob = json.load(open(manifest_path, "r", encoding="utf-8"))
    except (ValueError, OSError):
        return {"manifest_found": True, "parse_error": True,
                "coverage_is_ticker_scoped": None, "coverage_note": None}
    execu = blob.get("execution") if isinstance(blob, dict) else None
    execu = execu if isinstance(execu, dict) else {}
    return {
        "manifest_found": True,
        "manifest_path": manifest_path,
        "coverage_is_ticker_scoped": execu.get("coverage_is_ticker_scoped"),
        "coverage_note": execu.get("coverage_note"),
        "n_games_in_manifest": len(execu.get("manifest") or []),
    }


def run(trade_glob: str = TRADE_TAPE_GLOB, depth_glob: str = DEPTH_TAPE_GLOB,
        settlement_root: str = DEFAULT_SETTLEMENT_ROOT) -> Dict[str, object]:
    """The full audit, parametrized so tests can point it at synthetic fixtures instead of
    the live committed tape. `main()` calls this with the real repo paths."""
    tickers_by_day = traded_tickers_by_day(trade_glob)
    depth_counts_by_day, capture_ids_by_day = depth_snapshot_counts_by_day(tickers_by_day, depth_glob)
    candidate_units_by_day = eligible_units_by_day(tickers_by_day, depth_counts_by_day)
    settled_by_day, resolution = settled_units_by_day(candidate_units_by_day, settlement_root)

    splits = chronological_splits(settled_by_day)

    # Natural gap split used in the write-up: everything <= RICH_ERA_LAST_DAY vs after.
    days = sorted(settled_by_day)
    train_days = [d for d in days if d <= RICH_ERA_LAST_DAY]
    holdout_days = [d for d in days if d > RICH_ERA_LAST_DAY]
    train_units = sorted({u for d in train_days for u in settled_by_day[d]})
    holdout_units = sorted({u for d in holdout_days for u in settled_by_day[d]})
    overlap_units = sorted(set(train_units) & set(holdout_units))
    series_report = series_overlap(train_units, holdout_units)

    gap_report = intra_ticker_gap_minutes(
        {t for units in candidate_units_by_day.values() for t in units.values()}, depth_glob)
    gap_summary = {
        era: {
            "n_gaps": len(vals),
            "p25_min": _percentile(vals, 0.25),
            "median_min": _percentile(vals, 0.50),
            "p75_min": _percentile(vals, 0.75),
            "p90_min": _percentile(vals, 0.90),
            "share_le_60min": (sum(1 for v in vals if v <= 60) / len(vals)) if vals else None,
            "histogram_30min_bins": gap_histogram_30min_bins(vals),
        }
        for era, vals in gap_report.items()
    }

    n_train, n_holdout = len(train_units), len(holdout_units)
    per_cell_split = {
        "stated_cell_count": Q52_STATED_CELL_COUNT,
        "train_units_per_cell": n_train / Q52_STATED_CELL_COUNT,
        "holdout_units_per_cell": n_holdout / Q52_STATED_CELL_COUNT,
        # NOTE (verifier round 2 nit): this is the MEAN units/cell, an even-split assumption —
        # not the guaranteed minimum cell if the real <=4-cell design is unbalanced. A False
        # here is still a sound "infeasible" (a failed necessary condition), but a True would
        # not by itself prove every cell clears the floor.
        "clears_l41_per_cell": (n_train / Q52_STATED_CELL_COUNT >= L41_MIN_UNITS and
                                n_holdout / Q52_STATED_CELL_COUNT >= L41_MIN_UNITS),
    }
    era_boundary_evidence = depth_capture_id_counts_around_boundary(depth_glob)

    out = {
        "script": "q52_s78_split_feasibility_audit",
        "purpose": "measure whether a chronological train/holdout split of the S78 population "
                   "is feasible, and characterize why/why not — NOT a claim that Q52's stated "
                   "reason is wrong (see per_cell_split, which honors Q52's own <=4-cell "
                   "qualifier, alongside the undivided 1-cell split)",
        "verdict_class": False,
        "backfill_scope_caveat": backfill_scope_caveat(),
        "settlement_resolution_summary": resolution.coverage_summary(),
        "settlement_sources_scanned": list(resolution.sources_scanned),
        "settlement_sources_absent_on_disk": list(resolution.sources_absent_on_disk),
        "per_day": {
            day: {
                "n_traded_game_tickers": len(tickers_by_day.get(day, ())),
                "n_depth_capture_instants": capture_ids_by_day.get(day, 0),
                "n_candidate_units": len(candidate_units_by_day.get(day, {})),
                "n_settled_units": len(settled_by_day.get(day, [])),
            }
            for day in sorted(tickers_by_day)
        },
        "chronological_splits": [
            {"cut_day": c, "n_train_units": tr, "n_holdout_units": h, "n_overlap_units": ov,
             "clears_l41_undivided_1cell": tr >= L41_MIN_UNITS and h >= L41_MIN_UNITS and ov == 0}
            for c, tr, h, ov in splits
        ],
        "natural_era_split": {
            "train_days": train_days,
            "holdout_days": holdout_days,
            "n_train_units": n_train,
            "n_holdout_units": n_holdout,
            "n_overlap_units": len(overlap_units),
            "clears_l41_undivided_1cell": n_train >= L41_MIN_UNITS and n_holdout >= L41_MIN_UNITS,
        },
        "per_cell_split": per_cell_split,
        "series_transfer": series_report,
        "book_cadence_by_era": {
            "rich_era_days": train_days,
            "starved_era_days": holdout_days,
            "rich_era_capture_instants_per_day": [capture_ids_by_day.get(d) for d in train_days],
            "starved_era_capture_instants_per_day": [capture_ids_by_day.get(d) for d in holdout_days],
            "note": "capture_id counted over the WHOLE day file, not filtered to backfilled "
                    "tickers — unaffected by backfill_scope_caveat. Only covers TRADE days "
                    "(a 3-week hole around the era boundary itself) — see "
                    "era_boundary_evidence for the boundary step-down.",
        },
        "era_boundary_evidence": {
            "window_days_each_side": ERA_BOUNDARY_EVIDENCE_WINDOW_DAYS,
            "capture_instants_by_day": era_boundary_evidence,
            "note": "EVERY orderbook_depth day file in the window, independent of whether it "
                    "had a trade — this is the field the module docstring's era-boundary claim "
                    "is checkable against (verifier round 2, NEW-1).",
        },
        "intra_ticker_snapshot_gap_minutes_by_era": gap_summary,
        "price_source_tags": {"settlement": "broker_truth", "trades": "broker_truth",
                              "depth": "real_ask/real_bid (unused here — no price read)"},
    }
    return out


def main() -> int:
    print(json.dumps(run(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
