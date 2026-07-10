#!/usr/bin/env python3
"""s9_shock_eventstudy.py — S9 event-study around REAL round-transition shocks (LOOP-QUEUE.md Q8).

`s9_leadlag_probe.py` pooled every consecutive-capture price change into a lag cross-
correlation, but flagged (2026-07-05) that zero KXWCROUND markets had opened/closed inside
the continuously-collected window — every observed tick was book noise, not the information
shock S9's thesis actually needs (does one venue reprice before the other around a team
advancing/being eliminated?).

By 2026-07-06 three such transitions have landed in `tape/polymarket_pairs/`. The very first
one (diffed between the one-off 2026-07-04T15:15Z smoke-test capture and 2026-07-05T00:11:30Z,
where continuous hourly collection actually began) is a startup artifact, not an in-window
shock — excluded here by that documented cutoff, same reasoning `s9_leadlag_probe`'s own
docstring already gives.

For each real transition, a removed ticker's last TWO captured rows straddle the actual
repricing (the ticker keeps being captured with its near-settled price for a bit before it
drops out of Kalshi's open-markets listing entirely — the capture where it vanishes is not
itself a price observation). This reports both venues' values across that final step plus
the wall-clock gap between the two captures, i.e. the real event-study, not a pooled
noise-floor number.

Still descriptive only, n=3 events / ~15 affected tickers — nowhere near bootstrap-worthy.
Read-only over `tape/polymarket_pairs/*.jsonl`, no network calls.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from core.io import REPO_ROOT
from scripts.s9_leadlag_probe import (
    TAPE_DIR,
    Row,
    build_series,
    load_records,
    market_membership_changes,
)

CAPTURE_ID_FMT = "%Y%m%dT%H%M%SZ"

# The capture at which continuous hourly collection actually began (Q8, 2026-07-05). The
# membership-change diffed INTO this capture (from the prior one-off 2026-07-04T15:15:54Z
# smoke-test capture, ~9h earlier) reflects collector startup, not a real in-window shock.
CONTINUOUS_COLLECTION_START_CAPTURE = "20260705T001130Z"


def parse_capture_id(capture_id: str) -> Optional[datetime]:
    try:
        return datetime.strptime(capture_id, CAPTURE_ID_FMT)
    except ValueError:
        return None


def real_transition_events(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Membership changes minus the documented startup-artifact one (see module docstring)."""
    changes = market_membership_changes(records)
    return [c for c in changes if c["capture_id"] != CONTINUOUS_COLLECTION_START_CAPTURE]


def event_study_for_ticker(rows: Sequence[Row]) -> Optional[Dict[str, Any]]:
    """A removed ticker's last two captured rows straddle its actual repricing (it keeps
    being captured with its near-settled price for a bit before Kalshi stops listing it as
    open — the capture where it vanishes is not itself a price observation)."""
    if len(rows) < 2:
        return None
    pre_capture, kalshi_pre, poly_pre = rows[-2]
    post_capture, kalshi_post, poly_post = rows[-1]
    pre_dt = parse_capture_id(pre_capture)
    post_dt = parse_capture_id(post_capture)
    gap_minutes = (post_dt - pre_dt).total_seconds() / 60.0 if pre_dt and post_dt else None
    return {
        "pre_capture": pre_capture,
        "post_capture": post_capture,
        "gap_minutes": gap_minutes,
        "kalshi_pre": kalshi_pre,
        "kalshi_post": kalshi_post,
        "delta_kalshi": kalshi_post - kalshi_pre,
        "polymarket_pre": poly_pre,
        "polymarket_post": poly_post,
        "delta_polymarket": poly_post - poly_pre,
    }


def build_report(tape_dir: Path = TAPE_DIR) -> Dict[str, Any]:
    records = load_records(tape_dir)
    series = build_series(records)
    events = real_transition_events(records)

    event_reports = []
    for event in events:
        ticker_studies = []
        for ticker in sorted(event["removed"]):
            rows = series.get(ticker)
            if not rows:
                continue
            study = event_study_for_ticker(rows)
            if study is not None:
                ticker_studies.append({"ticker": ticker, **study})
        event_reports.append({
            "vanish_capture_id": event["capture_id"],
            "added": event["added"],
            "removed": event["removed"],
            "ticker_studies": ticker_studies,
        })

    return {
        "n_records": len(records),
        "n_real_transition_events": len(event_reports),
        "events": event_reports,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S9 event-study around real round-transition shocks")
    ap.add_argument("--tape-dir", default=str(TAPE_DIR))
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    report = build_report(Path(args.tape_dir))

    print("=" * 78)
    print("S9 SHOCK EVENT-STUDY (read-only, descriptive — NOT a verdict)")
    print("=" * 78)
    print(f"records={report['n_records']} real_transition_events={report['n_real_transition_events']}")
    if not report["events"]:
        print("  -> still zero real in-window transitions; re-run once one lands.")
    for event in report["events"]:
        print(f"\nvanished as of capture {event['vanish_capture_id']} "
              f"(removed={event['removed']}):")
        for s in event["ticker_studies"]:
            print(f"  {s['ticker']}: gap={s['gap_minutes']}min "
                  f"kalshi {s['kalshi_pre']}->{s['kalshi_post']} (d={s['delta_kalshi']:+.3f})  "
                  f"poly {s['polymarket_pre']}->{s['polymarket_post']} (d={s['delta_polymarket']:+.3f})")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2))
        print(f"\nwrote {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
