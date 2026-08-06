#!/usr/bin/env python3
"""Read-only data-quality audit of `tape/econ_prints/`: is a `real_ask` on an econ
threshold ladder a price a consumer could ACT on, and does the family's own tape let a
consumer tell the difference?

`collection/econ_prints.py` persists, per strike, four prices tagged `real_ask`
(`yes_ask`/`yes_bid`/`no_ask`/`no_bid`) and deliberately does NOT call
`core.pricing.bracket_sum` — each KXCPI*/KXPAYROLLS/KXGDP strike is an independent
`strike_type: "greater"` binary, not a partition member (Hard Rule #3 is satisfied by not
normalizing, which is correct). Its docstring then delegates the ONE arb shape these nested
ladders admit — buy YES(lower T) + NO(higher T) — to `scripts/anomaly_sweep.py`'s
`cross_strike_monotonicity` (Q6/S3), which prices it through
`core.pricing.monotonicity_crossing_edge` net of both legs' taker fees.

This audit asks the two questions that delegation leaves open, from the econ tape's own side:

  Q1 (fillability). A `real_ask` tag certifies PROVENANCE — the number came off Kalshi's
     book — not FILLABILITY. On Kalshi the four BBO fields are mechanically mirrored
     (`yes_ask == 1 - no_bid`, `no_ask == 1 - yes_bid`), so a strike with no resting YES bid
     reports `no_ask == 1.00` and a strike with no resting NO bid reports `yes_ask == 1.00`
     — a quote pinned by the ABSENCE of a bid, not by anyone's belief. L23 says a one-sided
     wing book is valid data, not a capture failure; L31 says its nominal spread is not
     capturable. This measures how much of the family that describes and reports whether the
     tape carries any field a consumer could use to tell one cohort from the other.

  Q2 (screen gap). The naive coherence screen a probe writer reaches for — "yes_ask must be
     non-increasing in floor_strike" — is NECESSARY but not SUFFICIENT (the collector's own
     docstring and `monotonicity_crossing_edge`'s both say so). This quantifies the gap:
     the naive screen's hit rate on ADJACENT rungs (the most conservative form) against the
     executable screen's hit rate over ALL nested pairs (the most generous form, exactly
     `anomaly_sweep.check_monotonicity`'s enumeration), plus how much of the naive screen's
     yield is explained by one-sidedness alone.

Also re-checks, from committed tape only, four claims other documents already made about this
family, because each is now decidable and one of them is wrong:
  * L224 / the 2026-07-29 audit's D4 — `expiration_value` format drift; is
    `_normalize_expiration_value` now total over every committed string?
  * the 2026-07-29 audit's D5 — `gdp`'s long `no_settled_events` run called "a silent 23-day
    regression"; the timeline now extends past it.
  * L221 — byte-redundant re-capture; re-derived here as its effect on an OPPORTUNITY count
    (distinct market-pair states vs. captures of them).
  * `collection/econ_prints.py`'s own "already covered platform-wide by anomaly_sweep"
    delegation, checked against what `tape/anomalies/` actually recorded.

DESCRIPTIVE ONLY: no gate, no bootstrap CI, no P&L, no verdict, no registry change, no
network, no writes outside `--out`. Read-only over committed tape.

Run:
    python3 scripts/econ_prints_ladder_fillability_audit.py --max-day 2026-08-04
    python3 scripts/econ_prints_ladder_fillability_audit.py --econ-dir <dir> --stdout

`--max-day` closes the window: without it tomorrow's collector pass silently moves every
number this audit's finding and acceptance tests pinned.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Repo root on sys.path so `core` / `collection` imports work when run directly (L232).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collection.econ_prints import _normalize_expiration_value  # noqa: E402
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import (  # noqa: E402
    MAKER_FEE_RATE, TAKER_FEE_RATE, monotonicity_crossing_edge,
)

DEFAULT_ECON_DIR = REPO_ROOT / "tape" / "econ_prints"
DEFAULT_ANOMALIES_DIR = REPO_ROOT / "tape" / "anomalies"
REPORT_PATH = REPO_ROOT / "reports" / "econ_prints_ladder_fillability_audit.json"

ECON_SCHEMA = "econ_prints.v1"

# Kalshi quotes on a whole-cent grid; a persisted price off that grid would mean the
# collector's dollar conversion introduced a value the venue never quoted.
CENT_TOL = 1e-6
# Float slack for the mirror identities and the monotonicity comparisons. Prices are
# cent-quantized, so anything this small is representation noise, never a real crossing.
PRICE_TOL = 1e-9
# "Actionable" = a two-sided book whose nominal spread is not itself the L31 artifact.
ACTIONABLE_SPREAD_CENTS = 5
# The econ series' own ticker prefixes, used to ask whether anomaly_sweep ever recorded a
# cross_strike_monotonicity hit on THIS family (see cross_detector_corroboration).
ECON_TICKER_PREFIXES = ("KXCPI", "KXCPICORE", "KXCPIYOY", "KXPAYROLLS", "KXGDP")


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def day_of(path: Path) -> str:
    name = path.name
    return name[len("dt="):-len(".jsonl")] if name.startswith("dt=") else name


def iter_day_files(tape_dir: Path, max_day: Optional[str] = None) -> List[Path]:
    files = sorted(Path(tape_dir).glob("dt=*.jsonl"))
    if max_day:
        files = [p for p in files if day_of(p) <= max_day]
    return files


def load_records(tape_dir: Path, max_day: Optional[str] = None
                 ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Every committed record plus a parse/duplicate census. A malformed line is COUNTED and
    skipped, never silently dropped — a parse failure lowers the reported line coverage, it
    never fakes a clean read (the honest-completeness posture the collectors themselves use).
    """
    records: List[Dict[str, Any]] = []
    n_lines = 0
    n_blank = 0
    parse_errors: List[Dict[str, Any]] = []
    line_hashes: Counter = Counter()
    key_counts: Counter = Counter()
    ordering_inversions: List[Dict[str, Any]] = []

    for path in iter_day_files(tape_dir, max_day):
        day = day_of(path)
        prev_ts: Optional[str] = None
        with open(path, "r", encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw.rstrip("\n")
                if not line.strip():
                    n_blank += 1
                    continue
                n_lines += 1
                line_hashes[line] += 1
                try:
                    rec = json.loads(line)
                except Exception as exc:  # pragma: no cover - no malformed line committed
                    parse_errors.append({"day": day, "line": lineno, "error": str(exc)})
                    continue
                rec["_day"] = day
                rec["_lineno"] = lineno
                records.append(rec)
                key_counts[(str(rec.get("capture_id")), str(rec.get("series_key")))] += 1
                ts = str(rec.get("captured_at") or "")
                if prev_ts is not None and ts < prev_ts:
                    ordering_inversions.append(
                        {"day": day, "line": lineno, "prev_captured_at": prev_ts,
                         "captured_at": ts})
                prev_ts = ts

    census = {
        "n_files": len(iter_day_files(tape_dir, max_day)),
        "n_lines": n_lines,
        "n_blank_lines": n_blank,
        "n_parse_errors": len(parse_errors),
        "parse_errors": parse_errors[:10],
        "n_exact_duplicate_lines": sum(c - 1 for c in line_hashes.values() if c > 1),
        "n_duplicate_capture_id_series_keys": sum(c - 1 for c in key_counts.values() if c > 1),
        "duplicate_capture_id_series_keys": sorted(
            [list(k) for k, c in key_counts.items() if c > 1]),
        "n_captured_at_ordering_inversions": len(ordering_inversions),
        "captured_at_ordering_inversions": ordering_inversions[:10],
    }
    return records, census


def iter_strikes(records: Iterable[Dict[str, Any]]):
    """(record, event, strike) for every persisted open-ladder strike."""
    for rec in records:
        open_events = rec.get("open_events") or {}
        for ev in open_events.get("events") or []:
            for st in ev.get("strikes") or []:
                yield rec, ev, st


def iter_ladders(records: Iterable[Dict[str, Any]]):
    """(record, event, strikes-sorted-by-floor_strike) for every ladder SNAPSHOT with >=2
    strikes carrying a numeric floor_strike. Spacing is never assumed (L7) — ordering is by
    the ladder's own `floor_strike` values, and nesting follows from `strike_type: greater`
    alone, not from any step size."""
    for rec in records:
        open_events = rec.get("open_events") or {}
        for ev in open_events.get("events") or []:
            rungs = [s for s in (ev.get("strikes") or [])
                     if s.get("floor_strike") is not None
                     and s.get("strike_type") == "greater"
                     and s.get("yes_ask") is not None and s.get("no_ask") is not None]
            if len(rungs) < 2:
                continue
            yield rec, ev, sorted(rungs, key=lambda s: float(s["floor_strike"]))


# --------------------------------------------------------------------------- #
# population / schema / tags
# --------------------------------------------------------------------------- #
def population_block(records: List[Dict[str, Any]], census: Dict[str, Any]) -> Dict[str, Any]:
    days = sorted({r["_day"] for r in records})
    n_strikes = sum(1 for _ in iter_strikes(records))
    return {
        **census,
        "n_records": len(records),
        "days": days,
        "n_days": len(days),
        "first_captured_at": min((str(r.get("captured_at")) for r in records), default=None),
        "last_captured_at": max((str(r.get("captured_at")) for r in records), default=None),
        "n_captures": len({str(r.get("capture_id")) for r in records}),
        "schema_versions": dict(sorted(Counter(str(r.get("schema_version"))
                                               for r in records).items())),
        "records_by_series_key": dict(sorted(Counter(str(r.get("series_key"))
                                                     for r in records).items())),
        "n_open_strikes": n_strikes,
        "pass_complete": dict(sorted(Counter(str(r.get("pass_complete"))
                                             for r in records).items())),
    }


def source_tag_block(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """CLAUDE.md's default-trust-FALSE rule: an untagged number IS `synthetic`, so an absent
    tag is counted explicitly rather than folded into a total."""
    strike_tags: Counter = Counter()
    for _, _, st in iter_strikes(records):
        strike_tags[str(st.get("price_source_tag") or "<untagged→synthetic>")] += 1
    settle_tags: Counter = Counter()
    nowcast_tags: Counter = Counter()
    for rec in records:
        rs = rec.get("recent_settlement") or {}
        if rs.get("status") == "settled":
            settle_tags[str(rs.get("price_source_tag") or "<untagged→synthetic>")] += 1
        nc = rec.get("nowcast") or {}
        if nc.get("status") == "ok":
            nowcast_tags[str(nc.get("price_source_tag") or "<untagged→synthetic>")] += 1
    return {
        "open_ladder_strikes": dict(sorted(strike_tags.items())),
        "settled_records": dict(sorted(settle_tags.items())),
        "nowcast_ok_records": dict(sorted(nowcast_tags.items())),
        "n_untagged": (strike_tags["<untagged→synthetic>"]
                       + settle_tags["<untagged→synthetic>"]
                       + nowcast_tags["<untagged→synthetic>"]),
        "meaning": ("provenance only — a real_ask tag says the number came off the venue's "
                    "book, NOT that a consumer could fill against it (see book_sidedness)"),
    }


def value_sanity_block(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    fields = ("yes_ask", "yes_bid", "no_ask", "no_bid")
    nulls: Counter = Counter()
    out_of_range: List[Dict[str, Any]] = []
    off_cent: List[Dict[str, Any]] = []
    crossed: List[Dict[str, Any]] = []
    strike_types: Counter = Counter()
    n = 0
    for rec, ev, st in iter_strikes(records):
        n += 1
        strike_types[str(st.get("strike_type"))] += 1
        for f in fields:
            v = st.get(f)
            if v is None:
                nulls[f] += 1
                continue
            v = float(v)
            if not (0.0 <= v <= 1.0) and len(out_of_range) < 10:
                out_of_range.append({"capture_id": rec.get("capture_id"),
                                     "ticker": st.get("ticker"), "field": f, "value": v})
            if abs(round(v * 100.0) - v * 100.0) > CENT_TOL and len(off_cent) < 10:
                off_cent.append({"capture_id": rec.get("capture_id"),
                                 "ticker": st.get("ticker"), "field": f, "value": v})
        ya, yb = st.get("yes_ask"), st.get("yes_bid")
        if ya is not None and yb is not None and float(yb) > float(ya) + PRICE_TOL \
                and len(crossed) < 10:
            crossed.append({"capture_id": rec.get("capture_id"), "ticker": st.get("ticker"),
                            "yes_bid": yb, "yes_ask": ya})
    return {
        "n_strikes": n,
        "nulls_by_field": dict(sorted(nulls.items())),
        "n_out_of_unit_interval": len(out_of_range),
        "out_of_unit_interval": out_of_range,
        "n_off_cent_grid": len(off_cent),
        "off_cent_grid": off_cent,
        "n_crossed_books_yes_bid_gt_yes_ask": len(crossed),
        "crossed_books": crossed,
        "strike_types": dict(sorted(strike_types.items())),
    }


# --------------------------------------------------------------------------- #
# Q1 — mirror identity + book sidedness
# --------------------------------------------------------------------------- #
def mirror_block(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """On Kalshi a NO order is a mirrored YES order in the SAME book, so the four BBO fields
    should carry only two degrees of freedom. Measured, not assumed — if the identity ever
    broke, `no_ask` would be independent information and the sidedness classification below
    would need both sides."""
    ok_yes = viol_yes = ok_no = viol_no = 0
    examples: List[Dict[str, Any]] = []
    for rec, _, st in iter_strikes(records):
        ya, yb = st.get("yes_ask"), st.get("yes_bid")
        na, nb = st.get("no_ask"), st.get("no_bid")
        if ya is not None and nb is not None:
            if abs(float(ya) + float(nb) - 1.0) <= PRICE_TOL:
                ok_yes += 1
            else:
                viol_yes += 1
                if len(examples) < 10:
                    examples.append({"capture_id": rec.get("capture_id"),
                                     "ticker": st.get("ticker"), "identity": "mirror_yes_side",
                                     "yes_ask": ya, "no_bid": nb})
        if na is not None and yb is not None:
            if abs(float(na) + float(yb) - 1.0) <= PRICE_TOL:
                ok_no += 1
            else:
                viol_no += 1
                if len(examples) < 10:
                    examples.append({"capture_id": rec.get("capture_id"),
                                     "ticker": st.get("ticker"), "identity": "mirror_no_side",
                                     "yes_ask": ya, "no_bid": nb})
    return {
        "yes_ask_plus_no_bid_eq_1": {"holds": ok_yes, "violations": viol_yes},
        "no_ask_plus_yes_bid_eq_1": {"holds": ok_no, "violations": viol_no},
        "violation_examples": examples,
        "degrees_of_freedom": 2 if (viol_yes == 0 and viol_no == 0) else 4,
        "meaning": ("if both identities hold everywhere, the NO-side fields carry ZERO "
                    "independent information (each is one minus its YES-side mirror, "
                    "exactly) — so an 'is there a NO book?' "
                    "check on this family is really a 'is there a YES bid?' check, and a "
                    "one-sided strike's ask is pinned by the ABSENCE of a bid, not by belief"),
    }


def classify_side(st: Dict[str, Any]) -> str:
    yb, ya = float(st["yes_bid"]), float(st["yes_ask"])
    has_yes_bid = yb > 0.0
    has_no_bid = ya < 1.0  # equivalently: a strictly positive resting NO bid
    if has_yes_bid and has_no_bid:
        return "two_sided"
    if has_no_bid:
        return "no_yes_bid"      # only a NO bid rests -> yes_ask quoted, no_ask == 1.00
    if has_yes_bid:
        return "no_no_bid"       # only a YES bid rests -> no_ask quoted, yes_ask == 1.00
    return "no_book_at_all"


def sidedness_block(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    classes: Counter = Counter()
    by_series: Dict[str, Counter] = defaultdict(Counter)
    spreads: List[float] = []
    n_actionable = 0
    n = 0
    for rec, _, st in iter_strikes(records):
        if st.get("yes_bid") is None or st.get("yes_ask") is None:
            continue
        n += 1
        cls = classify_side(st)
        classes[cls] += 1
        by_series[str(rec.get("series_key"))][cls] += 1
        spread = float(st["yes_ask"]) - float(st["yes_bid"])
        spreads.append(spread)
        if cls == "two_sided" and round(spread * 100) <= ACTIONABLE_SPREAD_CENTS:
            n_actionable += 1
    spreads.sort()

    def q(p: float) -> Optional[float]:
        return round(spreads[min(len(spreads) - 1, int(p * len(spreads)))], 4) if spreads else None

    n_one_sided = n - classes["two_sided"]
    return {
        "n_classified_strikes": n,
        "classes": dict(sorted(classes.items())),
        "frac_one_sided": round(n_one_sided / n, 6) if n else None,
        "frac_two_sided": round(classes["two_sided"] / n, 6) if n else None,
        "by_series_key": {k: dict(sorted(v.items())) for k, v in sorted(by_series.items())},
        "yes_spread": {
            "median": round(statistics.median(spreads), 4) if spreads else None,
            "mean": round(statistics.mean(spreads), 4) if spreads else None,
            "p10": q(0.10), "p90": q(0.90),
        },
        "actionable_spread_cents_bar": ACTIONABLE_SPREAD_CENTS,
        "n_two_sided_within_spread_bar": n_actionable,
        "frac_actionable": round(n_actionable / n, 6) if n else None,
        "meaning": ("L23: a one-sided wing book is VALID data, not a capture failure. L31: "
                    "its nominal spread is not capturable. Both cohorts carry the SAME "
                    "price_source_tag: real_ask, and the tape persists no field that "
                    "separates them — the consumer must derive it from yes_bid>0 & yes_ask<1"),
    }


# --------------------------------------------------------------------------- #
# Q2 — naive vs executable monotonicity screen
# --------------------------------------------------------------------------- #
def monotonicity_block(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Two screens over the SAME ladders:

    naive (adjacent rungs only, the most CONSERVATIVE form) — `yes_ask` must be non-increasing
    in `floor_strike`, since a higher threshold's YES-region is a strict subset.

    executable (ALL nested pairs, the most GENEROUS form — exactly the i<j enumeration in
    `scripts/anomaly_sweep.py::check_monotonicity`) — buy YES(outer, lower T) + NO(inner,
    higher T) pays a guaranteed >=$1, so it is an arb only when it COSTS less than $1 net of
    both legs' fees via `core.pricing.monotonicity_crossing_edge`.

    Distinct opportunities are counted by (event_ticker, outer, inner, prices) as well as by
    capture, because L221's byte-redundant re-capture inflates a per-capture opportunity count
    by however many times the same quote state was re-sampled."""
    n_ladders = n_ladders_with_naive_hit = 0
    n_adj = n_adj_hits = 0
    n_adj_hits_touching_one_sided = 0
    n_adj_two_sided_pairs = n_adj_two_sided_hits = 0
    naive_by_series: Counter = Counter()
    ladders_by_series: Counter = Counter()
    naive_examples: List[Dict[str, Any]] = []

    n_pairs = 0
    gross_rows: List[Dict[str, Any]] = []
    n_net_taker = n_net_maker = 0
    n_net_taker_bare = n_net_maker_bare = 0

    for rec, ev, rungs in iter_ladders(records):
        n_ladders += 1
        sk = str(rec.get("series_key"))
        ladders_by_series[sk] += 1
        hit_here = False
        for a, b in zip(rungs, rungs[1:]):
            n_adj += 1
            a_two = classify_side(a) == "two_sided"
            b_two = classify_side(b) == "two_sided"
            if a_two and b_two:
                n_adj_two_sided_pairs += 1
            if float(b["yes_ask"]) > float(a["yes_ask"]) + PRICE_TOL:
                n_adj_hits += 1
                hit_here = True
                if not (a_two and b_two):
                    n_adj_hits_touching_one_sided += 1
                elif a_two and b_two:
                    n_adj_two_sided_hits += 1
                if len(naive_examples) < 8:
                    naive_examples.append({
                        "capture_id": rec.get("capture_id"), "event_ticker": ev.get("event_ticker"),
                        "lower": a.get("ticker"), "lower_yes_ask": a.get("yes_ask"),
                        "higher": b.get("ticker"), "higher_yes_ask": b.get("yes_ask"),
                        "lower_side": classify_side(a), "higher_side": classify_side(b),
                    })
        if hit_here:
            n_ladders_with_naive_hit += 1
            naive_by_series[sk] += 1

        for i in range(len(rungs)):
            for j in range(i + 1, len(rungs)):
                outer, inner = rungs[i], rungs[j]
                n_pairs += 1
                outer_ask, inner_no_ask = float(outer["yes_ask"]), float(inner["no_ask"])
                cost = outer_ask + inner_no_ask
                if cost >= 1.0 - PRICE_TOL:
                    continue
                edge_t = monotonicity_crossing_edge(outer_ask, inner_no_ask, TAKER_FEE_RATE)
                edge_m = monotonicity_crossing_edge(outer_ask, inner_no_ask, MAKER_FEE_RATE)
                # PRICE_TOL guard, not a bare `> 0`: prices and fees are both cent-
                # quantized, so an exactly-$0.00 hedge is REACHABLE and lands one float
                # ULP above zero (L27) — see cross_detector_corroboration for the same
                # artifact live in the delegate.
                n_net_taker += int(edge_t > PRICE_TOL)
                n_net_maker += int(edge_m > PRICE_TOL)
                n_net_taker_bare += int(edge_t > 0)
                n_net_maker_bare += int(edge_m > 0)
                gross_rows.append({
                    "capture_id": rec.get("capture_id"), "captured_at": rec.get("captured_at"),
                    "event_ticker": ev.get("event_ticker"),
                    "outer_ticker": outer.get("ticker"), "outer_ask": outer_ask,
                    "inner_ticker": inner.get("ticker"), "inner_no_ask": inner_no_ask,
                    "gross_cost": round(cost, 6),
                    "edge_taker": round(edge_t, 6), "edge_maker": round(edge_m, 6),
                    "price_source_tag": "real_ask",
                })

    distinct_states = sorted({(r["event_ticker"], r["outer_ticker"], r["inner_ticker"],
                              r["outer_ask"], r["inner_no_ask"]) for r in gross_rows})
    return {
        "naive_screen": {
            "definition": "yes_ask(higher floor_strike) > yes_ask(lower floor_strike), ADJACENT rungs",
            "n_ladder_snapshots": n_ladders,
            "n_ladder_snapshots_with_a_hit": n_ladders_with_naive_hit,
            "frac_ladder_snapshots_with_a_hit": (round(n_ladders_with_naive_hit / n_ladders, 6)
                                                 if n_ladders else None),
            "n_adjacent_pairs": n_adj,
            "n_hits": n_adj_hits,
            "frac_adjacent_pairs_hit": round(n_adj_hits / n_adj, 6) if n_adj else None,
            "n_hits_touching_a_one_sided_rung": n_adj_hits_touching_one_sided,
            "frac_hits_touching_a_one_sided_rung": (
                round(n_adj_hits_touching_one_sided / n_adj_hits, 6) if n_adj_hits else None),
            "two_sided_only": {
                "n_pairs": n_adj_two_sided_pairs, "n_hits": n_adj_two_sided_hits,
                "frac_hit": (round(n_adj_two_sided_hits / n_adj_two_sided_pairs, 6)
                             if n_adj_two_sided_pairs else None),
            },
            "hits_by_series_key": dict(sorted(naive_by_series.items())),
            "ladder_snapshots_by_series_key": dict(sorted(ladders_by_series.items())),
            "examples": naive_examples,
        },
        "executable_screen": {
            "definition": ("buy YES(outer, lower T) + NO(inner, higher T) at both REAL asks; "
                           "arb iff core.pricing.monotonicity_crossing_edge > 0 — ALL nested "
                           "pairs, matching scripts/anomaly_sweep.py::check_monotonicity"),
            "n_nested_pairs": n_pairs,
            "n_gross_cost_under_1": len(gross_rows),
            "frac_gross_cost_under_1": round(len(gross_rows) / n_pairs, 8) if n_pairs else None,
            "n_positive_edge_taker": n_net_taker,
            "n_positive_edge_maker_counterfactual": n_net_maker,
            "n_positive_edge_taker_bare_gt_zero": n_net_taker_bare,
            "n_positive_edge_maker_bare_gt_zero": n_net_maker_bare,
            "epsilon_guard": ("counts use `> PRICE_TOL`; the *_bare_gt_zero counts use "
                              "the bare `> 0` the delegate uses — the difference is the "
                              "exactly-$0.00 hedges float representation lifts above zero"),
            "taker_fee_rate": TAKER_FEE_RATE, "maker_fee_rate": MAKER_FEE_RATE,
            "gross_rows": gross_rows,
            "n_distinct_quote_states": len(distinct_states),
            "worst_edge_taker": (max((r["edge_taker"] for r in gross_rows), default=None)),
            "price_source_tag": "real_ask",
        },
        "screen_gap": {
            "meaning": ("the naive screen is NECESSARY but not SUFFICIENT; the gap between "
                        "its hit rate and the executable screen's is the false-positive load "
                        "any consumer of this tape inherits if it screens on yes_ask ordering"),
        },
    }


# --------------------------------------------------------------------------- #
# settlement / nowcast status timelines
# --------------------------------------------------------------------------- #
def settlement_block(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    status_by_series: Dict[str, Counter] = defaultdict(Counter)
    ev_values: Counter = Counter()
    uncoercible: List[Dict[str, Any]] = []
    n_disagree = 0
    timelines: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for rec in sorted(records, key=lambda r: str(r.get("captured_at"))):
        sk = str(rec.get("series_key"))
        rs = rec.get("recent_settlement") or {}
        status = str(rs.get("status"))
        status_by_series[sk][status] += 1
        state = (status, str(rs.get("event_ticker")))
        prev = timelines[sk][-1] if timelines[sk] else None
        if prev is None or (prev["status"], str(prev["event_ticker"])) != state:
            timelines[sk].append({"captured_at": rec.get("captured_at"), "status": status,
                                  "event_ticker": rs.get("event_ticker"),
                                  "expiration_value": rs.get("expiration_value")})
        if status != "settled":
            continue
        raw = rs.get("expiration_value")
        ev_values[(sk, str(rs.get("event_ticker")), str(raw))] += 1
        if raw is not None and _normalize_expiration_value(raw) is None:
            uncoercible.append({"series_key": sk, "raw": raw})
        if rs.get("expiration_values_disagree"):
            n_disagree += 1
    return {
        "status_by_series_key": {k: dict(sorted(v.items()))
                                 for k, v in sorted(status_by_series.items())},
        "distinct_expiration_values": [
            {"series_key": k[0], "event_ticker": k[1], "raw": k[2], "n_records": c,
             "normalized": _normalize_expiration_value(k[2])}
            for k, c in sorted(ev_values.items())],
        "n_uncoercible_expiration_values": len(uncoercible),
        "uncoercible_expiration_values": uncoercible,
        "n_records_with_expiration_values_disagree": n_disagree,
        "status_timelines": {k: v for k, v in sorted(timelines.items())},
        "meaning": ("L224/D4 re-check (is _normalize_expiration_value total over every "
                    "committed string?) and the D5 re-check (does the gdp no_settled_events "
                    "run end?) — the timeline is the discriminator, and it is already in the "
                    "committed tape"),
    }


def nowcast_block(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_series: Dict[str, Counter] = defaultdict(Counter)
    gdp_values: Counter = Counter()
    not_built_gdp: List[Dict[str, Any]] = []
    for rec in records:
        sk = str(rec.get("series_key"))
        nc = rec.get("nowcast") or {}
        status = str(nc.get("status"))
        by_series[sk][status] += 1
        if sk != "gdp":
            continue
        if status == "ok":
            gdp_values[(str(nc.get("target_quarter_end")), str(nc.get("as_of")),
                        nc.get("value_pct"))] += 1
        elif status == "not_built" and len(not_built_gdp) < 10:
            not_built_gdp.append({"captured_at": rec.get("captured_at"),
                                  "day": rec.get("_day"), "line": rec.get("_lineno")})
    return {
        "status_by_series_key": {k: dict(sorted(v.items()))
                                 for k, v in sorted(by_series.items())},
        "gdp_distinct_nowcast_values": [
            {"target_quarter_end": k[0], "as_of": k[1], "value_pct": k[2], "n_records": c,
             "price_source_tag": "synthetic"}
            for k, c in sorted(gdp_values.items())],
        "n_gdp_records_status_not_built": sum(1 for r in records
                                              if str(r.get("series_key")) == "gdp"
                                              and str((r.get("nowcast") or {}).get("status"))
                                              == "not_built"),
        "gdp_not_built_examples": not_built_gdp,
        "meaning": ("fetch_nowcast() routes gdp to the GDPNow scrape unconditionally, so a "
                    "gdp record reading not_built can only come from a pre-scraper build of "
                    "the collector — a PAYLOAD-SEMANTICS change that schema_version does not "
                    "record"),
    }


# --------------------------------------------------------------------------- #
# cross-detector corroboration — what did anomaly_sweep actually record?
# --------------------------------------------------------------------------- #
def cross_detector_block(anomalies_dir: Path, max_day: Optional[str] = None) -> Dict[str, Any]:
    """`collection/econ_prints.py`'s docstring delegates this family's nested-threshold arb
    shape to `scripts/anomaly_sweep.py::check_monotonicity`. Two questions the anomaly tape
    can answer:

    (a) Is the delegation OBSERVABLE for econ? A zero econ hit count is consistent BOTH with
        "scanned and genuinely clean" and with "the capped pass never reached these markets";
        the anomaly record persists counts but no scanned-ticker list, so the tape alone
        cannot separate them. (The executable_screen block supplies the missing half from
        econ_prints' own side.)

    (b) Does the delegate apply the SAME fillability bar this audit applies to econ_prints?
        Measured, not assumed: `check_monotonicity` filters its legs on `is None` only, so a
        `yes_ask_dollars` of 0.0 — the ABSENCE of a resting offer, never a $0.00 buyable fill
        (L105) — passes through as an outer leg, and a bare `if edge > 0` admits an edge that
        is mathematically exactly $0.00 but lands one float ULP above it (L27's class).
        Both counted here over the committed anomaly tape. DESCRIPTIVE: this records what the
        tape contains; it is NOT a verdict on S3 and flips nothing."""
    if not Path(anomalies_dir).exists():
        return {"status": "anomalies_tape_absent", "dir": str(anomalies_dir)}
    kinds: Counter = Counter()
    econ_hits = 0
    prefixes: Counter = Counter()
    truncated: Counter = Counter()
    n_records = 0
    n_mono = 0
    n_zero_outer_ask = 0
    n_zero_any_leg = 0
    n_epsilon_edge = 0
    n_edge_recompute_disagreements = 0
    zero_leg_states: Counter = Counter()
    epsilon_examples: List[Dict[str, Any]] = []
    edges: List[float] = []
    for path in iter_day_files(Path(anomalies_dir), max_day):
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                if not raw.strip():
                    continue
                try:
                    rec = json.loads(raw)
                except Exception:
                    continue
                n_records += 1
                truncated[str(rec.get("markets_truncated"))] += 1
                for an in rec.get("anomalies") or []:
                    kinds[str(an.get("kind"))] += 1
                    et = str(an.get("event_ticker") or "")
                    prefixes[et.split("-")[0]] += 1
                    if an.get("kind") != "cross_strike_monotonicity":
                        continue
                    n_mono += 1
                    if et.split("-")[0] in ECON_TICKER_PREFIXES:
                        econ_hits += 1
                    oa, ina, ed = an.get("outer_ask"), an.get("inner_no_ask"), an.get("edge")
                    if oa is not None and float(oa) == 0.0:
                        n_zero_outer_ask += 1
                    if (oa is not None and float(oa) == 0.0) or \
                            (ina is not None and float(ina) == 0.0):
                        n_zero_any_leg += 1
                        zero_leg_states[(oa, ina)] += 1
                    if ed is not None:
                        edges.append(float(ed))
                        if 0.0 < float(ed) < PRICE_TOL:
                            n_epsilon_edge += 1
                            if len(epsilon_examples) < 3:
                                epsilon_examples.append({
                                    "event_ticker": et, "outer_ticker": an.get("outer_ticker"),
                                    "inner_ticker": an.get("inner_ticker"),
                                    "outer_ask": oa, "inner_no_ask": ina, "edge": ed,
                                    "exact_decimal_edge": 0.0})
                    if oa is not None and ina is not None and ed is not None:
                        if abs(monotonicity_crossing_edge(float(oa), float(ina),
                                                          TAKER_FEE_RATE) - float(ed)) > 1e-12:
                            n_edge_recompute_disagreements += 1
    edges.sort()
    return {
        "status": "ok",
        "n_anomaly_records": n_records,
        "markets_truncated": dict(sorted(truncated.items())),
        "anomalies_by_kind": dict(sorted(kinds.items())),
        "n_cross_strike_monotonicity_on_econ_series": econ_hits,
        "top_event_prefixes": dict(Counter(prefixes).most_common(10)),
        "econ_series_prefixes_checked": list(ECON_TICKER_PREFIXES),
        "delegate_fillability": {
            "n_cross_strike_monotonicity": n_mono,
            "n_edge_recompute_disagreements": n_edge_recompute_disagreements,
            "n_outer_ask_equals_zero": n_zero_outer_ask,
            "frac_outer_ask_equals_zero": (round(n_zero_outer_ask / n_mono, 6)
                                           if n_mono else None),
            "n_any_leg_equals_zero": n_zero_any_leg,
            "frac_any_leg_equals_zero": round(n_zero_any_leg / n_mono, 6) if n_mono else None,
            "zero_leg_price_states_top": [
                {"outer_ask": k[0], "inner_no_ask": k[1], "n": v}
                for k, v in zero_leg_states.most_common(5)],
            "n_edge_within_one_ulp_of_zero": n_epsilon_edge,
            "frac_edge_within_one_ulp_of_zero": (round(n_epsilon_edge / n_mono, 6)
                                                 if n_mono else None),
            "epsilon_edge_examples": epsilon_examples,
            "smallest_edges": [repr(e) for e in edges[:3]],
            "smallest_edge_above_one_ulp": next((e for e in edges if e >= PRICE_TOL), None),
            "meaning": ("L105 says a yes_ask==0.0 leg is the ABSENCE of an offer, never a "
                        "$0.00 buyable fill; L27 says a float-epsilon 'positive' is "
                        "economically zero. check_monotonicity filters legs on `is None` and "
                        "admits on a bare `edge > 0`, so both classes enter its output. "
                        "DESCRIPTIVE — recorded, not acted on; no registry status is touched "
                        "here and a verdict on S3 needs the two-agent rule"),
        },
        "meaning": ("a 0 econ hit count is NOT by itself evidence the delegation works — the "
                    "executable_screen computed above from econ_prints' OWN tape supplies the "
                    "missing half: there was nothing for it to find"),
    }


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def audit(econ_dir: Path = DEFAULT_ECON_DIR, anomalies_dir: Path = DEFAULT_ANOMALIES_DIR,
          max_day: Optional[str] = None) -> Dict[str, Any]:
    records, census = load_records(Path(econ_dir), max_day=max_day)
    return {
        "audit": "econ_prints_ladder_fillability",
        "econ_dir": str(econ_dir),
        "max_day": max_day,
        "expected_schema": ECON_SCHEMA,
        "population": population_block(records, census),
        "value_sanity": value_sanity_block(records),
        "source_tags": source_tag_block(records),
        "mirror_identity": mirror_block(records),
        "book_sidedness": sidedness_block(records),
        "monotonicity": monotonicity_block(records),
        "settlement": settlement_block(records),
        "nowcast": nowcast_block(records),
        "cross_detector_corroboration": cross_detector_block(Path(anomalies_dir), max_day),
        "scope": ("DESCRIPTIVE / DATA-QUALITY ONLY — read-only over committed tape; no gate, "
                  "no bootstrap CI, no P&L, no strategy verdict, no registry change, no "
                  "collector write-path change, no network"),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="read-only fillability/coherence audit of tape/econ_prints (DESCRIPTIVE ONLY)")
    ap.add_argument("--econ-dir", default=str(DEFAULT_ECON_DIR))
    ap.add_argument("--anomalies-dir", default=str(DEFAULT_ANOMALIES_DIR))
    ap.add_argument("--out", default=str(REPORT_PATH))
    ap.add_argument("--max-day", default=None,
                    help="cap the audited window at this tape day (inclusive, e.g. 2026-08-04)")
    ap.add_argument("--stdout", action="store_true", help="print the full report")
    args = ap.parse_args(argv)

    rep = audit(Path(args.econ_dir), Path(args.anomalies_dir), max_day=args.max_day)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.stdout:
        print(json.dumps(rep, indent=2, sort_keys=True))
        return 0

    p, s, m, mono = (rep["population"], rep["book_sidedness"], rep["mirror_identity"],
                     rep["monotonicity"])
    print(f"records={p['n_records']} lines={p['n_lines']} parse_errors={p['n_parse_errors']} "
          f"strikes={p['n_open_strikes']} days={p['n_days']} captures={p['n_captures']}")
    print(f"tags: {rep['source_tags']['open_ladder_strikes']} untagged={rep['source_tags']['n_untagged']}")
    print(f"mirror: yes-side ok={m['yes_ask_plus_no_bid_eq_1']['holds']} "
          f"viol={m['yes_ask_plus_no_bid_eq_1']['violations']} | dof={m['degrees_of_freedom']}")
    print(f"sidedness: one_sided={s['frac_one_sided']} classes={s['classes']} "
          f"actionable(<= {s['actionable_spread_cents_bar']}c two-sided)={s['frac_actionable']}")
    n = mono["naive_screen"]
    e = mono["executable_screen"]
    print(f"naive screen: {n['n_hits']}/{n['n_adjacent_pairs']} adjacent pairs "
          f"({n['frac_adjacent_pairs_hit']}), {n['n_ladder_snapshots_with_a_hit']}/"
          f"{n['n_ladder_snapshots']} ladder snapshots ({n['frac_ladder_snapshots_with_a_hit']}); "
          f"{n['frac_hits_touching_a_one_sided_rung']} touch a one-sided rung")
    print(f"executable screen: {e['n_gross_cost_under_1']}/{e['n_nested_pairs']} gross<$1 "
          f"({e['n_distinct_quote_states']} distinct quote states), "
          f"POSITIVE-EDGE taker={e['n_positive_edge_taker']} maker-cf={e['n_positive_edge_maker_counterfactual']}")
    print(f"settlement: uncoercible={rep['settlement']['n_uncoercible_expiration_values']} "
          f"disagree={rep['settlement']['n_records_with_expiration_values_disagree']}")
    cd = rep["cross_detector_corroboration"]
    print(f"anomaly_sweep econ cross_strike hits="
          f"{cd.get('n_cross_strike_monotonicity_on_econ_series')} "
          f"truncated={cd.get('markets_truncated')}")
    df = cd.get("delegate_fillability") or {}
    if df:
        print(f"  delegate: {df['n_cross_strike_monotonicity']} cross_strike anomalies, "
              f"outer_ask==0 on {df['n_outer_ask_equals_zero']} ({df['frac_outer_ask_equals_zero']}), "
              f"edge within 1 ULP of $0.00 on {df['n_edge_within_one_ulp_of_zero']} "
              f"({df['frac_edge_within_one_ulp_of_zero']}); "
              f"recompute disagreements={df['n_edge_recompute_disagreements']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
