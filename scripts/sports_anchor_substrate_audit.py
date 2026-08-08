#!/usr/bin/env python3
"""Idle-run policy (c) — data-quality deep-dive on the SPORTS FAIR-ANCHOR substrate.

LOOP-QUEUE.md protocol v3, 2026-08-08. READ-ONLY and FULLY OFFLINE: this module opens
committed tape files and nothing else — no network, no credentials, no orders, no writes
outside `reports/`. It produces a DATA-QUALITY description, never a P&L, never a CI, never
a registry flip.

WHAT "the fair-anchor substrate" IS. Four strategy candidates in `kb/strategies/00-index.md`
are scored against an EXTERNAL bookmaker's de-vigged fair probability rather than against
Kalshi's own price: S7 (dead), S13 (dead), S21 (DEAD-by-data-adequacy) and S11 — the only
sports-maker lane still `data-collecting`. That anchor has been written by two different
mechanisms in this repo's history, and nothing had ever audited them side by side:

  BACKFILL LANE (frozen)  `tape/sports_clv/`, `tape/sports_history/`, `tape/sports_clv_s7/`,
                          `tape/sports_history_s7/`, `tape/sports_maker_fillsim/`
                          — written by hand-invoked CLIs (`python -m collection.sports_history`,
                          `python -m scripts.sports_history_s7a`, …), never by a scheduled pass.
  LIVE LANE               `tape/sports_pairs/`'s per-record `odds_leg` sub-object — written by
                          `collection/sports_pairs.py` -> `collection/odds_api.py` on EVERY
                          hourly pass, i.e. the lane S11's "anchor confirmed live 2026-07-13"
                          registry note refers to.

S21's registry row records the backfill lane's death cause (L43/L9): its fair anchors cover
kickoffs <= 2026-07-03 while `tape/orderbook_depth/` began >= 2026-07-07, so the join is
empty by construction, and S21 is "re-testable only on concurrently-collected fair-anchor +
depth tape". This module asks the obvious follow-up nobody had asked: does the LIVE lane
supply that concurrent tape, and if not, exactly which mechanism is starving it?

Six measurements, each falsifiable from committed bytes:

1. `backfill_lane`      — per-file schema, record counts, capture/kickoff spans, staleness in
                          days, and the source tags actually persisted (including tags that
                          are NOT in `core.source_tag.SOURCE_TAGS` and therefore degrade to
                          `synthetic` by CLAUDE.md's trust default).
2. `write_path_liveness`— which module writes each directory, and whether that module is
                          imported by `collection/hourly_pass.py` at all. A directory whose
                          writer has no scheduled caller is a one-shot artifact, not a family
                          that "went stale".
3. `monitor_coverage`   — which of these families are registered in
                          `scripts/tape_gap_monitor.py`'s `FAMILY_CONFIG` /
                          `REGISTERED_CALLER_FAMILIES`. An unregistered family can never
                          alert; that is a monitoring blind spot, not a clean bill of health.
4. `live_lane`          — the full `odds_leg.status` census over every committed
                          `tape/sports_pairs/` day: how many records/events ever reached
                          `matched` (a usable anchor), and the exact day the lane last
                          produced one.
5. `starvation_diagnosis` — WHY the live lane stopped, split into its independent causes and
                          measured separately so a reader cannot conflate them: a missing API
                          key (`blocked_key`), a series absent from `SPORT_KEY_BY_SERIES`
                          (`unmapped_series`), and a series that IS mapped but excluded by the
                          `DEFAULT_SPORTS` quota selector (`not_selected`). The third is the
                          durable one and is measured on the single fully-keyed day that
                          exists after the World Cup ended.
6. `retest_population`  — the honest denominator for a future S21/S13-class re-test: of the
                          anchors that DO exist, how many join `tape/orderbook_depth/`
                          concurrently (the L43 blocker), and how many carry an ex-post
                          settlement on any committed settlement surface (L300's nine).

Every count is a distinct-entity count with its denominator stated. No price is quoted
without its `price_source_tag`. The `--max-day` cutoff exists so tomorrow's collector pass
cannot silently move a number this run's finding pins (L286).

Usage:
    python -m scripts.sports_anchor_substrate_audit
    python -m scripts.sports_anchor_substrate_audit --max-day 2026-08-07 --json-out reports/x.json
"""
from __future__ import annotations

import argparse
import ast
import collections
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from core.io import REPO_ROOT  # noqa: E402
from core.source_tag import VALID_SOURCE_TAGS, tag_or_synthetic  # noqa: E402

# The closed window this audit's committed headline numbers were derived over. Tape is
# append-only, so a LATER day can only ADD rows; pinning the cutoff keeps the finding's
# numbers re-derivable after the next collector pass (L286's closed-window rule).
DEFAULT_MAX_DAY = "2026-08-07"

# The five backfill-lane directories, with the module that writes each (read off the writer's
# own module-level path constant — see `write_path_liveness`).
BACKFILL_FAMILIES: Dict[str, str] = {
    "sports_clv": "collection/sports_history.py",
    "sports_history": "collection/sports_history.py",
    "sports_clv_s7": "scripts/sports_clv_s7.py",
    "sports_history_s7": "scripts/sports_history_s7a.py",
    "sports_maker_fillsim": "scripts/s13_maker_fillsim.py",
}

LIVE_FAMILY = "sports_pairs"

# An `odds_leg.status` of exactly this value means the record carries a usable external fair
# anchor. Every other status is a refusal, and the refusals are NOT interchangeable — see
# `starvation_diagnosis`.
ANCHOR_STATUS = "matched"


# ───────────────────────────── small readers ─────────────────────────────

def _day_of(path: Path) -> Optional[str]:
    name = path.name
    if not name.startswith("dt=") or not name.endswith(".jsonl"):
        return None
    return name[3:-6]


def _iter_jsonl(path: Path):
    """Yield parsed objects; silently skip blank lines, count unparseable ones."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except (ValueError, TypeError):
                yield None


def _day_files(family: str, max_day: Optional[str], root: Path) -> List[Path]:
    d = root / "tape" / family
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("dt=*.jsonl")):
        day = _day_of(p)
        if day is None:
            continue
        if max_day is not None and day > max_day:
            continue
        out.append(p)
    return out


def _event_prefix(ticker: str) -> str:
    """`KXWCGAME-26JUL14FRAESP-ESP` -> `KXWCGAME-26JUL14FRAESP`. The repo's standing
    event/bootstrap unit for sports (L6): the market ticker minus its outcome token."""
    t = str(ticker or "")
    return t.rsplit("-", 1)[0] if "-" in t else t


# ───────────────────────────── 1. backfill lane ─────────────────────────────

def backfill_lane(root: Path = REPO_ROOT, max_day: Optional[str] = DEFAULT_MAX_DAY) -> Dict[str, Any]:
    """Per-directory shape, span, staleness and persisted source tags.

    A tag that is not in `core.source_tag.SOURCE_TAGS` is reported as
    `out_of_vocabulary`, because `tag_or_synthetic` degrades it to `synthetic` —
    a record can therefore LOOK tagged and still be untrusted (CLAUDE.md trust default).
    """
    out: Dict[str, Any] = {}
    for fam in BACKFILL_FAMILIES:
        d = root / "tape" / fam
        entry: Dict[str, Any] = {
            "exists": d.is_dir(),
            "files": [],
            "n_records": 0,
            "schema_versions": {},
            "record_source_tags": {},
            "out_of_vocabulary_tags": {},
            "captured_at_min": None,
            "captured_at_max": None,
        }
        if not d.is_dir():
            out[fam] = entry
            continue
        for p in sorted(d.iterdir()):
            if not p.is_file():
                continue
            day = _day_of(p)
            if day is not None and max_day is not None and day > max_day:
                continue
            entry["files"].append(p.name)
            if p.suffix != ".jsonl":
                continue
            for rec in _iter_jsonl(p):
                if rec is None or not isinstance(rec, dict):
                    continue
                entry["n_records"] += 1
                sv = rec.get("schema_version")
                entry["schema_versions"][sv] = entry["schema_versions"].get(sv, 0) + 1
                for key in ("price_source_tag", "price_source_tag_kalshi", "price_source_tag_odds"):
                    tag = rec.get(key)
                    if tag is None:
                        continue
                    k = f"{key}={tag}"
                    entry["record_source_tags"][k] = entry["record_source_tags"].get(k, 0) + 1
                    if tag not in VALID_SOURCE_TAGS:
                        entry["out_of_vocabulary_tags"][k] = {
                            "n": entry["out_of_vocabulary_tags"].get(k, {}).get("n", 0) + 1,
                            "degrades_to": tag_or_synthetic(tag),
                        }
                ts = rec.get("captured_at") or rec.get("fetch_ts") or rec.get("fetched_at")
                if isinstance(ts, str):
                    if entry["captured_at_min"] is None or ts < entry["captured_at_min"]:
                        entry["captured_at_min"] = ts
                    if entry["captured_at_max"] is None or ts > entry["captured_at_max"]:
                        entry["captured_at_max"] = ts
        out[fam] = entry
    return out


def clv_anchor_span(root: Path = REPO_ROOT, max_day: Optional[str] = DEFAULT_MAX_DAY) -> Dict[str, Any]:
    """`tape/sports_clv/`'s own kickoff span + the S21 longshot denominators.

    Reproduces (or fails to reproduce) the two population sizes the S21 registry row quotes:
    `fair_prob <= 0.20` (row says 81) and the `yes_ask <= 0.20` proxy (row says 83).
    """
    recs: List[Dict[str, Any]] = []
    for p in _day_files("sports_clv", max_day, root):
        for r in _iter_jsonl(p):
            if isinstance(r, dict):
                recs.append(r)
    kickoffs = [r["kickoff_ts"] for r in recs if r.get("kickoff_ts")]
    outcomes = [o for r in recs for o in (r.get("outcomes") or []) if isinstance(o, dict)]
    fair_lo = {o.get("ticker") for o in outcomes
               if isinstance(o.get("fair_prob"), (int, float)) and o["fair_prob"] <= 0.20}
    ask_lo = {o.get("ticker") for o in outcomes
              if isinstance((o.get("pregame_ask") or {}).get("yes_ask"), (int, float))
              and o["pregame_ask"]["yes_ask"] <= 0.20}
    return {
        "n_records": len(recs),
        "n_distinct_events": len({r.get("kalshi_event_ticker") for r in recs}),
        "n_outcome_rows": len(outcomes),
        "kickoff_min": min(kickoffs) if kickoffs else None,
        "kickoff_max": max(kickoffs) if kickoffs else None,
        "n_markets_fair_prob_le_020": len(fair_lo),
        "n_markets_yes_ask_le_020": len(ask_lo),
    }


# ───────────────────────────── 2. write-path liveness ─────────────────────────────

def write_path_liveness(root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Is any backfill-lane writer imported by `collection/hourly_pass.py`?

    AST-based, not lexical: a module name appearing in a docstring or a comment is not a
    call site (the L228 precedent — a line-regex draft of a similar check flagged only
    string literals). We resolve the set of `collection.*` modules `hourly_pass` actually
    imports, then ask whether each writer is in it.
    """
    hp = root / "collection" / "hourly_pass.py"
    imported: Set[str] = set()
    if hp.is_file():
        tree = ast.parse(hp.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("collection"):
                for a in node.names:
                    imported.add(a.name)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("collection."):
                        imported.add(a.name.split(".", 1)[1])
    out: Dict[str, Any] = {"hourly_pass_imports": sorted(imported), "families": {}}
    for fam, writer in BACKFILL_FAMILIES.items():
        mod = Path(writer).stem
        in_collection = writer.startswith("collection/")
        out["families"][fam] = {
            "writer": writer,
            "importable_by_hourly_pass": in_collection,
            "imported_by_hourly_pass": bool(in_collection and mod in imported),
            "verdict": ("scheduled" if (in_collection and mod in imported)
                        else "one_shot_no_scheduled_caller"),
        }
    out["families"][LIVE_FAMILY] = {
        "writer": "collection/sports_pairs.py",
        "importable_by_hourly_pass": True,
        "imported_by_hourly_pass": "sports_pairs" in imported,
        "verdict": "scheduled" if "sports_pairs" in imported else "one_shot_no_scheduled_caller",
    }
    return out


# ───────────────────────────── 3. monitor coverage ─────────────────────────────

def monitor_coverage(root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Which of these families can `scripts/tape_gap_monitor.py` alert on at all?

    A family absent from `FAMILY_CONFIG` is never iterated by the default report, so it
    can never produce a STALE/UNDER-CAPTURE reason — the monitor makes NO claim about it.
    That is a coverage limit of the monitor, not evidence the family is healthy (L155).
    """
    if str(_HERE) not in sys.path:
        sys.path.insert(0, str(_HERE))
    import tape_gap_monitor as tgm  # noqa: E402  (script-dir import, offline)
    fams = list(BACKFILL_FAMILIES) + [LIVE_FAMILY]
    registered_callers = set()
    for names in tgm.REGISTERED_CALLER_FAMILIES.values():
        registered_callers.update(names)
    return {
        "family_config_keys": sorted(tgm.FAMILY_CONFIG),
        "families": {
            f: {
                "in_family_config": f in tgm.FAMILY_CONFIG,
                "in_registered_caller_families": f in registered_callers,
                "can_alert_on_staleness": f in tgm.FAMILY_CONFIG,
            }
            for f in fams
        },
        "n_unmonitored_backfill_families": sum(
            1 for f in BACKFILL_FAMILIES if f not in tgm.FAMILY_CONFIG
        ),
        "monitors_the_odds_leg_subfield": False,  # no reader of `odds_leg` exists in the monitor
    }


# ───────────────────────────── 4. live lane ─────────────────────────────

def live_lane(root: Path = REPO_ROOT, max_day: Optional[str] = DEFAULT_MAX_DAY) -> Dict[str, Any]:
    """Full `odds_leg.status` census over every committed `tape/sports_pairs/` day."""
    per_day: Dict[str, Dict[str, int]] = {}
    totals: collections.Counter = collections.Counter()
    all_events: Set[str] = set()
    anchor_events: Set[str] = set()
    anchor_days: Set[str] = set()
    anchor_bookmakers: collections.Counter = collections.Counter()
    anchor_tags: collections.Counter = collections.Counter()
    n_records = 0
    for p in _day_files(LIVE_FAMILY, max_day, root):
        day = _day_of(p)
        c: collections.Counter = collections.Counter()
        for rec in _iter_jsonl(p):
            if not isinstance(rec, dict):
                continue
            n_records += 1
            leg = rec.get("odds_leg") or {}
            status = leg.get("status", "<missing>")
            c[status] += 1
            totals[status] += 1
            ev = rec.get("event_ticker")
            if ev:
                all_events.add(ev)
            if status == ANCHOR_STATUS:
                anchor_days.add(day)
                if ev:
                    anchor_events.add(ev)
                anchor_bookmakers[leg.get("bookmaker")] += 1
                anchor_tags[leg.get("price_source_tag")] += 1
        per_day[day] = dict(c)
    days_all_blocked = sorted(d for d, c in per_day.items()
                              if c and set(c) == {"blocked_key"})
    trailing_blocked: List[str] = []
    for d in sorted(per_day, reverse=True):
        if d in days_all_blocked:
            trailing_blocked.append(d)
        else:
            break
    return {
        "n_days": len(per_day),
        "n_records": n_records,
        "status_totals": dict(totals),
        "per_day": per_day,
        "n_distinct_events": len(all_events),
        "n_anchor_events": len(anchor_events),
        "anchor_events": sorted(anchor_events),
        "anchor_days": sorted(anchor_days),
        "last_anchor_day": max(anchor_days) if anchor_days else None,
        "anchor_bookmakers": dict(anchor_bookmakers),
        "anchor_price_source_tags": dict(anchor_tags),
        "n_consecutive_trailing_all_blocked_days": len(trailing_blocked),
        "trailing_all_blocked_days": sorted(trailing_blocked),
    }


def odds_api_constants(root: Path = REPO_ROOT) -> Tuple[Tuple[str, ...], Dict[str, str]]:
    """Read `DEFAULT_SPORTS` and `SPORT_KEY_BY_SERIES` out of `collection/odds_api.py` by AST.

    Deliberately NOT an import. `collection.odds_api` pulls in `requests` at module scope,
    and this audit's contract is that it opens committed bytes and nothing else — an offline
    module that cannot run without a network client's package installed is not offline in any
    useful sense. Reading the two literals structurally also means a future refactor that
    renames or deletes them fails loudly here instead of silently changing a headline.
    """
    src = (root / "collection" / "odds_api.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    found: Dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id in ("DEFAULT_SPORTS", "SPORT_KEY_BY_SERIES"):
                found[tgt.id] = ast.literal_eval(node.value)
    missing = {"DEFAULT_SPORTS", "SPORT_KEY_BY_SERIES"} - set(found)
    if missing:
        raise RuntimeError(
            f"collection/odds_api.py no longer defines {sorted(missing)} as a module-level "
            "literal — this audit's selector numbers would be silently wrong; fix the reader."
        )
    return tuple(found["DEFAULT_SPORTS"]), dict(found["SPORT_KEY_BY_SERIES"])


# ───────────────────────────── 5. starvation diagnosis ─────────────────────────────

def starvation_diagnosis(root: Path = REPO_ROOT,
                         max_day: Optional[str] = DEFAULT_MAX_DAY,
                         code_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Split the live lane's refusals into their INDEPENDENT causes.

    `blocked_key` (no API key) and `not_selected` (key fine, sport excluded by the
    `DEFAULT_SPORTS` quota selector) are different failures with different fixes, and
    conflating them would misattribute the outage. The selector cause is measured on the
    fully-keyed days that exist AFTER the World Cup ended — the only window where the
    selector is the binding constraint rather than a moot one.
    """
    # `root` is the TAPE root (tests point it at a fixture dir); the selector
    # constants always come from the real checkout unless overridden.
    default_sports, sport_key_by_series = odds_api_constants(code_root)

    keyed_days: List[str] = []
    per_day_rows: Dict[str, List[Dict[str, Any]]] = {}
    for p in _day_files(LIVE_FAMILY, max_day, root):
        day = _day_of(p)
        rows = [r for r in _iter_jsonl(p) if isinstance(r, dict)]
        per_day_rows[day] = rows
        if any((r.get("odds_leg") or {}).get("status") != "blocked_key" for r in rows):
            keyed_days.append(day)

    anchor_days = {d for d, rows in per_day_rows.items()
                   if any((r.get("odds_leg") or {}).get("status") == ANCHOR_STATUS for r in rows)}
    last_anchor = max(anchor_days) if anchor_days else None
    post_anchor_keyed = sorted(d for d in keyed_days if last_anchor and d > last_anchor)

    selector: Dict[str, Any] = {}
    for day in post_anchor_keyed:
        rows = per_day_rows[day]
        ns_rows = [r for r in rows
                   if (r.get("odds_leg") or {}).get("status") == "not_selected"]
        ns_series = collections.Counter(r.get("series") for r in ns_rows)
        ns_events = {r.get("event_ticker") for r in ns_rows if r.get("event_ticker")}
        selected_series_present = sum(
            1 for r in rows
            if sport_key_by_series.get(str(r.get("series") or "")) in set(default_sports)
        )
        selector[day] = {
            "n_rows": len(rows),
            "n_distinct_series": len({r.get("series") for r in rows}),
            "n_rows_not_selected": len(ns_rows),
            "n_events_not_selected": len(ns_events),
            "not_selected_by_series": {
                s: {"n_rows": n, "sport_key": sport_key_by_series.get(str(s))}
                for s, n in ns_series.most_common()
            },
            # If this is 0, NO selected sport had a single Kalshi game that day: the
            # selector conserved a quota it never had the chance to spend.
            "n_rows_whose_series_is_in_default_sports": selected_series_present,
        }
    return {
        "keyed_days": sorted(keyed_days),
        "last_anchor_day": last_anchor,
        "post_anchor_keyed_days": post_anchor_keyed,
        "default_sports": list(default_sports),
        "n_mapped_series": len(sport_key_by_series),
        "n_mapped_series_reachable_by_default": sum(
            1 for v in sport_key_by_series.values() if v in set(default_sports)
        ),
        "selector_forfeiture": selector,
    }


# ───────────────────────────── 6. re-test population ─────────────────────────────

def retest_population(root: Path = REPO_ROOT,
                      max_day: Optional[str] = DEFAULT_MAX_DAY) -> Dict[str, Any]:
    """The honest denominator for a future S21/S13-class re-test.

    Two gates, measured separately: (a) does an anchored event have CONCURRENT
    `orderbook_depth` tape (the L43/L9 blocker that killed S21), and (b) does it carry an
    ex-post settlement anywhere on committed tape (the scoring leg). A candidate must pass
    BOTH; reporting only one would overstate the population.
    """
    lane = live_lane(root=root, max_day=max_day)
    anchors = set(lane["anchor_events"])

    depth_days_by_event: Dict[str, Set[str]] = collections.defaultdict(set)
    for p in _day_files("orderbook_depth", max_day, root):
        day = _day_of(p)
        for rec in _iter_jsonl(p):
            if not isinstance(rec, dict):
                continue
            ev = _event_prefix(rec.get("ticker") or "")
            if ev in anchors:
                depth_days_by_event[ev].add(day)

    # Settlement: scan every committed settlement surface (L300's nine live under tape/,
    # each with its own schema, so membership is tested on raw bytes — a deliberately
    # coarse test that OVER-counts if anything, never under-counts).
    settle_by_event: Dict[str, List[str]] = collections.defaultdict(list)
    tape_root = root / "tape"
    if tape_root.is_dir():
        for dirpath, _dirnames, filenames in os.walk(tape_root):
            if "settlement" not in dirpath and not any("settlement" in f for f in filenames):
                continue
            for fn in filenames:
                p = Path(dirpath) / fn
                if "settlement" not in str(p):
                    continue
                day = _day_of(p)
                if day is not None and max_day is not None and day > max_day:
                    continue
                try:
                    blob = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for ev in anchors:
                    if ev in blob:
                        settle_by_event[ev].append(str(p.relative_to(root)))

    per_event = {
        ev: {
            "n_depth_days": len(depth_days_by_event.get(ev, ())),
            "depth_days": sorted(depth_days_by_event.get(ev, ())),
            "settlement_surfaces": sorted(settle_by_event.get(ev, ())),
            "joinable_to_depth": bool(depth_days_by_event.get(ev)),
            "has_settlement": bool(settle_by_event.get(ev)),
        }
        for ev in sorted(anchors)
    }
    both = [ev for ev, d in per_event.items() if d["joinable_to_depth"] and d["has_settlement"]]
    return {
        "n_anchor_events": len(anchors),
        "n_joinable_to_depth": sum(1 for d in per_event.values() if d["joinable_to_depth"]),
        "n_with_settlement": sum(1 for d in per_event.values() if d["has_settlement"]),
        "n_passing_both_gates": len(both),
        "events_passing_both_gates": sorted(both),
        "per_event": per_event,
        # L41's floor for a block-bootstrap unit count. Stated, never silently applied.
        "l41_min_units": 10,
        "clears_l41_floor": len(both) >= 10,
    }


def clv_depth_overlap(root: Path = REPO_ROOT,
                      max_day: Optional[str] = DEFAULT_MAX_DAY) -> Dict[str, Any]:
    """Independent re-derivation of S21's zero-overlap claim from the BACKFILL lane."""
    clv_events: Set[str] = set()
    for p in _day_files("sports_clv", max_day, root):
        for r in _iter_jsonl(p):
            if isinstance(r, dict) and r.get("kalshi_event_ticker"):
                clv_events.add(r["kalshi_event_ticker"])
    depth_events: Set[str] = set()
    for p in _day_files("orderbook_depth", max_day, root):
        for rec in _iter_jsonl(p):
            if isinstance(rec, dict):
                depth_events.add(_event_prefix(rec.get("ticker") or ""))
    return {
        "n_clv_events": len(clv_events),
        "n_depth_events": len(depth_events),
        "n_overlap": len(clv_events & depth_events),
        "overlap": sorted(clv_events & depth_events),
    }


# ───────────────────────────── report ─────────────────────────────

def build_report(root: Path = REPO_ROOT,
                 max_day: Optional[str] = DEFAULT_MAX_DAY) -> Dict[str, Any]:
    return {
        "schema_version": "sports_anchor_substrate_audit.v0",
        "max_day": max_day,
        "backfill_lane": backfill_lane(root, max_day),
        "clv_anchor_span": clv_anchor_span(root, max_day),
        "write_path_liveness": write_path_liveness(root),
        "monitor_coverage": monitor_coverage(root),
        "live_lane": live_lane(root, max_day),
        "starvation_diagnosis": starvation_diagnosis(root, max_day),
        "retest_population": retest_population(root, max_day),
        "clv_depth_overlap": clv_depth_overlap(root, max_day),
    }


def format_report(rep: Dict[str, Any]) -> str:
    L: List[str] = []
    L.append(f"sports fair-anchor substrate audit  (closed window <= {rep['max_day']})")
    L.append("")
    L.append("1. BACKFILL LANE")
    for fam, e in rep["backfill_lane"].items():
        L.append(f"   {fam:22s} files={len(e['files']):2d} records={e['n_records']:6d} "
                 f"captured {e['captured_at_min']} -> {e['captured_at_max']}")
        for k, v in e["out_of_vocabulary_tags"].items():
            L.append(f"       OUT-OF-VOCAB TAG {k} (n={v['n']}) -> degrades to {v['degrades_to']}")
    s = rep["clv_anchor_span"]
    L.append(f"   sports_clv kickoffs {s['kickoff_min']} -> {s['kickoff_max']}  "
             f"({s['n_distinct_events']} events / {s['n_outcome_rows']} outcome rows)")
    L.append(f"   S21 denominators: fair_prob<=0.20 -> {s['n_markets_fair_prob_le_020']} markets; "
             f"yes_ask<=0.20 proxy -> {s['n_markets_yes_ask_le_020']} markets")
    L.append("")
    L.append("2. WRITE-PATH LIVENESS")
    for fam, e in rep["write_path_liveness"]["families"].items():
        L.append(f"   {fam:22s} {e['writer']:32s} {e['verdict']}")
    L.append("")
    L.append("3. MONITOR COVERAGE")
    for fam, e in rep["monitor_coverage"]["families"].items():
        L.append(f"   {fam:22s} in FAMILY_CONFIG={str(e['in_family_config']):5s} "
                 f"can_alert_on_staleness={e['can_alert_on_staleness']}")
    L.append(f"   monitors the odds_leg sub-field: "
             f"{rep['monitor_coverage']['monitors_the_odds_leg_subfield']}")
    L.append("")
    ll = rep["live_lane"]
    L.append("4. LIVE LANE (tape/sports_pairs/ odds_leg)")
    L.append(f"   {ll['n_records']} records over {ll['n_days']} days; "
             f"{ll['n_distinct_events']} distinct events")
    for k, v in sorted(ll["status_totals"].items(), key=lambda x: -x[1]):
        L.append(f"       {k:18s} {v:7d}")
    L.append(f"   anchors: {ll['status_totals'].get(ANCHOR_STATUS, 0)} rows / "
             f"{ll['n_anchor_events']} events; last anchor day {ll['last_anchor_day']}")
    L.append(f"   trailing all-blocked_key days: {ll['n_consecutive_trailing_all_blocked_days']}")
    L.append("")
    sd = rep["starvation_diagnosis"]
    L.append("5. STARVATION DIAGNOSIS")
    L.append(f"   DEFAULT_SPORTS={sd['default_sports']}  "
             f"({sd['n_mapped_series_reachable_by_default']}/{sd['n_mapped_series']} "
             f"mapped series reachable)")
    for day, e in sd["selector_forfeiture"].items():
        L.append(f"   {day}: {e['n_events_not_selected']} events / {e['n_rows_not_selected']} rows "
                 f"refused by the selector; "
                 f"{e['n_rows_whose_series_is_in_default_sports']} rows in a selected sport")
    L.append("")
    rp = rep["retest_population"]
    L.append("6. RE-TEST POPULATION")
    L.append(f"   anchors={rp['n_anchor_events']}  joinable_to_depth={rp['n_joinable_to_depth']}  "
             f"with_settlement={rp['n_with_settlement']}  both={rp['n_passing_both_gates']}  "
             f"clears L41 floor({rp['l41_min_units']})={rp['clears_l41_floor']}")
    co = rep["clv_depth_overlap"]
    L.append(f"   backfill-lane control: {co['n_clv_events']} sports_clv events x "
             f"{co['n_depth_events']} depth events -> overlap {co['n_overlap']}")
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-day", default=DEFAULT_MAX_DAY,
                    help="inclusive dt= cutoff; keeps a pinned headline re-derivable (L286)")
    ap.add_argument("--json-out", default=None, help="write the full report JSON here")
    args = ap.parse_args(argv)
    rep = build_report(max_day=args.max_day)
    print(format_report(rep))
    if args.json_out:
        p = Path(args.json_out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rep, indent=1, sort_keys=True), encoding="utf-8")
        print(f"\nwrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
