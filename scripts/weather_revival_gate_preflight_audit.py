#!/usr/bin/env python3
"""Weather-revival gate PRE-FLIGHT audit — will Q37's inputs be adequate the day its gate opens?

Read-only, offline, no network. Produced by the 2026-07-31 research-loop IDLE RUN under
LOOP-QUEUE.md's idle-run policy (c) (data-quality deep-dive on one tape family). Backs
`findings/2026-07-31-weather-gate-preflight-audit.md`; every number in that finding is
re-derivable by running this file.

WHY THIS EXISTS
---------------
Q37 ("Weather revival: summer maker-side re-test of the S1/S5 family") self-activates when
`scripts/q37_weather_summer_makerno_probe.py::_summer_contract_days_available()` reaches 21.
That was the next queue gate due to open (~early August 2026). The loop's repeated experience
with weather-revival gates (Q36's settlement-basis leg opened onto a feed that had been frozen
since its build day; Q43's gate opened onto density-inadequate tape) says the same thing every
time: **a calendar gate opening is not the same event as the data being adequate.** So this
audit asks the pre-flight question BEFORE the gate opens, when there is still time to act.

VERDICT CLASS: DATA-ADEQUACY / PRE-FLIGHT. This file computes NO P&L, NO bootstrap, NO CI, and
touches NO strategy registry row. Nothing it prints is a verdict on Q37's edge.

THREE LEGS
----------
(A) GATE INTEGRITY — recompute the summer-day counter from raw tape under BOTH the pre-fix and
    the post-fix admission rules, so the measured contamination stays reproducible after the fix
    landed. Pre-fix rule = the historical one: `contract_day >= SUMMER_START`, no series
    whitelist. Post-fix = the probe's current `is_temperature_series` + bounded `is_summer`.
    A day counted only under the pre-fix rule is a PHANTOM gate day.

(B) SETTLEMENT LEG (`tape/weather_actuals/`) — the family that supplies Q37's EMOS training
    target and Q36's settlement truth, and the one tape family that had never been audited.
    Coverage (day-files, capture days, distinct settled contract-days), and JOINABILITY onto
    `tape/weather_books/` at both keys the probe actually uses: `(series, contract_day)` for the
    realized high, and the exact market ticker for the settled yes/no result. Coverage and
    joinability are reported separately on purpose — they fail for different reasons and a
    single "join rate" would hide which one is broken.

(C) SIGNAL LEG (`data/forecast_tape/`) — Q37's EMOS half needs as-issued forecasts. `data/` is
    gitignored by project contract (CLAUDE.md lane discipline), so this leg's presence is a
    property of the CHECKOUT, not of the repo. Reported as an availability fact, never as a
    failure of the collector that writes it.

USAGE
    python3 scripts/weather_revival_gate_preflight_audit.py
    python3 scripts/weather_revival_gate_preflight_audit.py --json-out /tmp/preflight.json
    # injectable dirs so the offline tests never read the real tape:
    python3 scripts/weather_revival_gate_preflight_audit.py \
        --books-dir /tmp/books --actuals-dir /tmp/actuals --forecast-dir /tmp/fc
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.q37_weather_summer_makerno_probe import (  # noqa: E402
    SUMMER_DAYS_REQUIRED,
    SUMMER_END,
    SUMMER_START,
    is_summer,
    is_temperature_series,
    parse_daily_ticker,
)

DEFAULT_BOOKS_DIR = REPO_ROOT / "tape" / "weather_books"
DEFAULT_ACTUALS_DIR = REPO_ROOT / "tape" / "weather_actuals"
DEFAULT_FORECAST_DIR = REPO_ROOT / "data" / "forecast_tape"


# --------------------------------------------------------------------------- #
# tiny readers (mirroring the probe's own tolerant style — a bad line is skipped,
# never fatal, and never silently counted as good)
# --------------------------------------------------------------------------- #
def _iter_records(day_glob: str):
    for path in sorted(glob.glob(day_glob)):
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue


def _day_files(directory: str) -> List[str]:
    return sorted(glob.glob(os.path.join(directory, "dt=*.jsonl")))


def _dt_of(path: str) -> str:
    return os.path.basename(path).replace("dt=", "").replace(".jsonl", "")


# --------------------------------------------------------------------------- #
# (A) gate integrity
# --------------------------------------------------------------------------- #
def _prefix_admits(series: str, cday: date) -> bool:
    """The HISTORICAL (pre-2026-07-31) admission rule: unbounded summer, no series whitelist."""
    return cday >= SUMMER_START


def audit_gate_integrity(books_dir: str = str(DEFAULT_BOOKS_DIR)) -> Dict[str, Any]:
    """Summer-day counter under the pre-fix vs post-fix admission rules, and the phantom delta."""
    day_glob = os.path.join(books_dir, "dt=*.jsonl")
    prefix_days: set = set()
    postfix_days: set = set()
    phantom_snaps: Counter = Counter()
    n_daily_rows = 0
    for rec in _iter_records(day_glob):
        if rec.get("group") != "daily":
            continue
        parsed = parse_daily_ticker(rec.get("ticker"))
        if parsed is None:
            continue
        series, cday, _bracket = parsed
        n_daily_rows += 1
        admitted_pre = _prefix_admits(series, cday)
        admitted_post = is_temperature_series(series) and is_summer(cday)
        if admitted_pre:
            prefix_days.add(cday)
        if admitted_post:
            postfix_days.add(cday)
        if admitted_pre and not admitted_post:
            phantom_snaps[(series, cday.isoformat())] += 1

    phantom_days = sorted(d.isoformat() for d in (prefix_days - postfix_days))
    return {
        "books_dir": books_dir,
        "n_daily_rows_parsed": n_daily_rows,
        "summer_days_prefix_rule": len(prefix_days),
        "summer_days_postfix_rule": len(postfix_days),
        "phantom_gate_days": phantom_days,
        "n_phantom_gate_days": len(phantom_days),
        "phantom_snapshots_by_series": {f"{s}|{d}": n for (s, d), n in
                                        sorted(phantom_snaps.items())},
        "n_phantom_snapshots": int(sum(phantom_snaps.values())),
        "real_contract_days": sorted(d.isoformat() for d in postfix_days),
        "gate_required": SUMMER_DAYS_REQUIRED,
        "summer_window": [SUMMER_START.isoformat(), SUMMER_END.isoformat()],
    }


def projected_gate_open(n_days_now: int, as_of: date,
                        required: int = SUMMER_DAYS_REQUIRED) -> Optional[str]:
    """Naive projection at ONE new contract-day per calendar day — deliberately optimistic.

    Stated as a projection, never as a fact: capture has died for multi-day stretches twice in
    this project's history, so the true open date can only be later than this, never earlier.
    Returns None when the gate is already open."""
    if n_days_now >= required:
        return None
    return (as_of + timedelta(days=required - n_days_now)).isoformat()


# --------------------------------------------------------------------------- #
# (B) settlement leg
# --------------------------------------------------------------------------- #
def audit_settlement_leg(actuals_dir: str = str(DEFAULT_ACTUALS_DIR),
                         books_dir: str = str(DEFAULT_BOOKS_DIR)) -> Dict[str, Any]:
    """`tape/weather_actuals/` coverage, plus its join onto `tape/weather_books/` at BOTH keys."""
    files = _day_files(actuals_dir)
    capture_days = [_dt_of(p) for p in files]
    n_lines = 0
    result_tickers: set = set()
    actual_groups: set = set()          # (series, contract_day) with a broker_truth expiration
    untagged_events = 0
    for rec in _iter_records(os.path.join(actuals_dir, "dt=*.jsonl")):
        n_lines += 1
        sm = rec.get("settled_markets") or {}
        for ev in (sm.get("events") or []):
            if ev.get("price_source_tag") != "broker_truth":
                # trust default: an untagged/otherwise-tagged settlement is NOT broker truth
                untagged_events += 1
                continue
            for tk, res in (ev.get("results") or {}).items():
                if isinstance(res, str):
                    result_tickers.add(tk)
            parsed = parse_daily_ticker(str(ev.get("event_ticker") or "") + "-x")
            if parsed is None or ev.get("expiration_value") is None:
                continue
            series, cday, _ = parsed
            actual_groups.add((series, cday))

    # book side, admitted under the CURRENT (post-fix) rule
    book_groups: set = set()
    book_tickers: set = set()
    for rec in _iter_records(os.path.join(books_dir, "dt=*.jsonl")):
        if rec.get("group") != "daily":
            continue
        parsed = parse_daily_ticker(rec.get("ticker"))
        if parsed is None:
            continue
        series, cday, _b = parsed
        if not (is_temperature_series(series) and is_summer(cday)):
            continue
        book_groups.add((series, cday))
        book_tickers.add(rec.get("ticker"))

    covered = book_groups & actual_groups
    orphan_actuals = actual_groups - book_groups
    orphan_tickers = result_tickers - book_tickers
    settled_days = sorted({c.isoformat() for _s, c in actual_groups})

    return {
        "actuals_dir": actuals_dir,
        "n_day_files": len(files),
        "capture_days": capture_days,
        "n_lines": n_lines,
        "n_events_not_broker_truth": untagged_events,
        "n_settled_result_tickers": len(result_tickers),
        "n_actual_groups": len(actual_groups),
        "settled_contract_days": settled_days,
        "n_settled_contract_days": len(settled_days),
        "n_book_groups": len(book_groups),
        "n_book_groups_with_actual": len(covered),
        "book_group_settlement_coverage": (round(len(covered) / len(book_groups), 4)
                                           if book_groups else None),
        "n_orphan_actual_groups": len(orphan_actuals),
        "n_orphan_result_tickers": len(orphan_tickers),
        # joinability is the ratio among rows that EXIST; coverage is how many rows exist at all
        "join_precision_groups": (round(len(covered) / len(actual_groups), 4)
                                  if actual_groups else None),
        "join_precision_tickers": (round(len(result_tickers & book_tickers) / len(result_tickers), 4)
                                   if result_tickers else None),
    }


# --------------------------------------------------------------------------- #
# (C) signal leg
# --------------------------------------------------------------------------- #
def audit_signal_leg(forecast_dir: str = str(DEFAULT_FORECAST_DIR)) -> Dict[str, Any]:
    """Is Q37's EMOS forecast input present IN THIS CHECKOUT? `data/` is gitignored, so a cloud
    run's answer is structurally 'no' regardless of whether the collector is healthy."""
    present = os.path.isdir(forecast_dir)
    files = sorted(glob.glob(os.path.join(forecast_dir, "*.jsonl"))) if present else []
    return {
        "forecast_dir": forecast_dir,
        "dir_present": present,
        "n_files": len(files),
        "emos_input_available": bool(files),
        "gitignored_lane": "data/",
    }


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def run(books_dir: str = str(DEFAULT_BOOKS_DIR),
        actuals_dir: str = str(DEFAULT_ACTUALS_DIR),
        forecast_dir: str = str(DEFAULT_FORECAST_DIR),
        as_of: Optional[date] = None) -> Dict[str, Any]:
    gate = audit_gate_integrity(books_dir)
    settle = audit_settlement_leg(actuals_dir, books_dir)
    signal = audit_signal_leg(forecast_dir)
    ref = as_of or date.today()
    gate["projected_open_prefix_rule"] = projected_gate_open(
        gate["summer_days_prefix_rule"], ref)
    gate["projected_open_postfix_rule"] = projected_gate_open(
        gate["summer_days_postfix_rule"], ref)
    return {
        "verdict_class": "DATA-ADEQUACY / PRE-FLIGHT — no CI, no P&L, no registry change",
        "as_of": ref.isoformat(),
        "gate_integrity": gate,
        "settlement_leg": settle,
        "signal_leg": signal,
    }


def format_report(rep: Dict[str, Any]) -> str:
    g, s, sig = rep["gate_integrity"], rep["settlement_leg"], rep["signal_leg"]
    out = [
        "=" * 92,
        "WEATHER-REVIVAL GATE PRE-FLIGHT AUDIT (read-only, offline) — " + rep["verdict_class"],
        "=" * 92,
        f"as_of={rep['as_of']}   summer window {g['summer_window'][0]}..{g['summer_window'][1]}"
        f"   gate opens at {g['gate_required']} contract-days",
        "",
        "(A) GATE INTEGRITY",
        f"    daily rows parsed          : {g['n_daily_rows_parsed']}",
        f"    summer days, PRE-FIX rule  : {g['summer_days_prefix_rule']}",
        f"    summer days, POST-FIX rule : {g['summer_days_postfix_rule']}",
        f"    PHANTOM gate days          : {g['n_phantom_gate_days']} {g['phantom_gate_days']}",
        f"    phantom snapshots          : {g['n_phantom_snapshots']} "
        f"{g['phantom_snapshots_by_series']}",
        f"    projected open (pre-fix)   : {g['projected_open_prefix_rule']}",
        f"    projected open (post-fix)  : {g['projected_open_postfix_rule']}",
        "",
        "(B) SETTLEMENT LEG  tape/weather_actuals/",
        f"    day-files / lines          : {s['n_day_files']} / {s['n_lines']}",
        f"    capture days               : {s['capture_days']}",
        f"    settled contract-days      : {s['n_settled_contract_days']} "
        f"{s['settled_contract_days']}",
        f"    broker_truth result tickers: {s['n_settled_result_tickers']}",
        f"    book groups w/ settlement  : {s['n_book_groups_with_actual']}/{s['n_book_groups']} "
        f"(coverage {s['book_group_settlement_coverage']})",
        f"    JOIN precision grp/ticker  : {s['join_precision_groups']} / "
        f"{s['join_precision_tickers']}   orphans {s['n_orphan_actual_groups']} / "
        f"{s['n_orphan_result_tickers']}",
        "",
        "(C) SIGNAL LEG  data/forecast_tape/  (gitignored lane — checkout property, not repo)",
        f"    dir present / files        : {sig['dir_present']} / {sig['n_files']}",
        f"    EMOS input available       : {sig['emos_input_available']}",
        "=" * 92,
    ]
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Weather-revival gate pre-flight audit (read-only)")
    ap.add_argument("--books-dir", default=str(DEFAULT_BOOKS_DIR))
    ap.add_argument("--actuals-dir", default=str(DEFAULT_ACTUALS_DIR))
    ap.add_argument("--forecast-dir", default=str(DEFAULT_FORECAST_DIR))
    ap.add_argument("--as-of", default=None, help="YYYY-MM-DD reference date for the projection")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    rep = run(args.books_dir, args.actuals_dir, args.forecast_dir, as_of=as_of)
    print(format_report(rep))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rep, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
