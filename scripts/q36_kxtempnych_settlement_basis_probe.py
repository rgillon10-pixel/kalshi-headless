"""scripts.q36_kxtempnych_settlement_basis_probe — LOOP-QUEUE Q36 part (1): settlement-basis
study, read-only, descriptive only (NOT a strategy verdict, NOT a registry change).

Q36's main milestone is GATED on >=7 days of `tape/weather_books/` hourly-family coverage
(collector landed 2026-07-15; day 7 lands ~2026-07-22). This script is the idle-run-policy-(b)
prep: build + offline-test the probe now so it can fire the day the gate opens, per
LOOP-QUEUE.md's v3 idle-run policy. It does NOT wait on `tape/weather_books/` at all — the
settled KXTEMPNYCH events it joins already live in `tape/settlement_ledger/` (Q45), a
different, already-flowing tape family — so running it live is a legitimate descriptive smoke
test (same posture as Q10/Q12/Q32's "live pass, explicitly not a verdict"), never a substitute
for the full milestone's binding gates (block-bootstrap by market-hour, two-agent rule,
depth x duration joint distribution) once the weather_books gate actually opens.

What it measures: Kalshi's KXTEMPNYCH-* markets settle on The Weather Company's value for
KNYC, carried verbatim as each event's `expiration_value` in `tape/settlement_ledger/`
(broker_truth — Kalshi's own reported settlement, see collection/settlement_ledger.py). This
script joins that TWC settlement value to an INDEPENDENT KNYC ASOS observation nearest the
event's `close_time` (IEM's `obhistory.json`, station NYC / network NY_ASOS, same station
config/station_candidates.yaml already uses for the daily-city validators) and quantifies the
mapping: bias, rounding pattern, disagreement rate at 1/2 degF tolerances, and the lag between
`close_time` and the matched observation's own timestamp. This mirrors validation/v1_actuals.py
's CLI-vs-METAR reconciliation, adapted to hourly directional markets instead of daily
high/low ladders.

Honest completeness: an event with no settlement_ledger `expiration_value`, or a settlement
day with zero ASOS observations returned, is a DROP — reported, never silently skipped in
count only. `min_events` gates whether a summary is even attempted (INSUFFICIENT DATA,
same self-activating pattern as scripts/q32_sharp_devig_polymarket_probe.py) — this script
is NEVER allowed to fabricate a mapping from too few points.

No bootstrap, no CI, no kill condition — this is a data-quality/mapping characterization,
not the milestone's own binding-gate verdict. `kb/strategies/00-index.md` is untouched by
running this script; the two-agent verdict rule does not apply (no verdict is produced).

Run:
    python -m scripts.q36_kxtempnych_settlement_basis_probe                  # live IEM fetch
    python -m scripts.q36_kxtempnych_settlement_basis_probe --tape-dir tape/settlement_ledger
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from validation._http import Http

IEM_OBHISTORY = "https://mesonet.agron.iastate.edu/api/1/obhistory.json"
STATION = "NYC"
NETWORK = "NY_ASOS"
SERIES = "KXTEMPNYCH"

TOLERANCES_F = (1.0, 2.0)


def _parse_iso(v: Any) -> Optional[datetime]:
    if not v:
        return None
    s = str(v).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _f(v: Any) -> Optional[float]:
    if v in (None, "", "M"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_settled_events(tape_dir: str = "tape/settlement_ledger") -> List[Dict[str, Any]]:
    """Read-only over committed tape. One row per unique KXTEMPNYCH event_ticker (Kalshi
    settles every strike in an event with the same expiration_value/close_time — dedupe on
    event_ticker, never double-count a market's shared settlement instant)."""
    seen: Dict[str, Dict[str, Any]] = {}
    for path in sorted(glob.glob(str(Path(tape_dir) / "dt=*.jsonl"))):
        try:
            lines = Path(path).read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("series") != SERIES:
                continue
            event_ticker = rec.get("event_ticker")
            if not event_ticker or event_ticker in seen:
                continue
            close_dt = _parse_iso(rec.get("close_time"))
            twc_value = _f(rec.get("expiration_value"))
            if close_dt is None or twc_value is None:
                continue
            seen[event_ticker] = {
                "event_ticker": event_ticker,
                "close_time": close_dt,
                "twc_value": twc_value,
                "settlement_ts": rec.get("settlement_ts"),
                "result": rec.get("result"),
            }
    return sorted(seen.values(), key=lambda r: r["close_time"])


def fetch_asos_day(http: Http, day_iso: str) -> List[Dict[str, Any]]:
    """One IEM obhistory.json call for KNYC on a single UTC date. Returns [] (never raises)
    on a network/parse failure — the caller records that as a drop, per this project's
    honest-completeness discipline; a transient IEM outage must not crash the whole pass."""
    try:
        payload = http.json(IEM_OBHISTORY, station=STATION, network=NETWORK, date=day_iso)
    except Exception:
        return []
    rows = (payload or {}).get("data") or []
    out = []
    for row in rows:
        valid = _parse_iso(row.get("utc_valid"))
        tmpf = _f(row.get("tmpf"))
        if valid is None or tmpf is None:
            continue
        out.append({"utc_valid": valid, "tmpf": tmpf})
    return out


def nearest_ob(obs: List[Dict[str, Any]], target: datetime) -> Optional[Tuple[Dict[str, Any], float]]:
    """Nearest-in-time observation to `target`; returns (ob, lag_seconds) where lag_seconds =
    ob_time - target (signed: positive = ob posted after close_time). None on an empty list —
    never guesses a nearest ob that doesn't exist."""
    if not obs:
        return None
    best = min(obs, key=lambda o: abs((o["utc_valid"] - target).total_seconds()))
    lag = (best["utc_valid"] - target).total_seconds()
    return best, lag


def build_basis_rows(events: List[Dict[str, Any]], http: Http) -> Tuple[List[Dict[str, Any]], int]:
    """Joins each settled event to its nearest KNYC ASOS ob. Returns (rows, n_dropped) — a
    drop is an event whose settlement day returned zero ASOS observations (IEM gap or fetch
    failure), counted honestly rather than silently shrinking the sample."""
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    rows: List[Dict[str, Any]] = []
    n_dropped = 0
    for ev in events:
        day_iso = ev["close_time"].date().isoformat()
        if day_iso not in by_day:
            by_day[day_iso] = fetch_asos_day(http, day_iso)
        obs = by_day[day_iso]
        match = nearest_ob(obs, ev["close_time"])
        if match is None:
            n_dropped += 1
            continue
        ob, lag_seconds = match
        diff = ev["twc_value"] - ob["tmpf"]
        rows.append({
            "event_ticker": ev["event_ticker"],
            "close_time": ev["close_time"].isoformat(),
            "twc_value": ev["twc_value"],
            "asos_tmpf": ob["tmpf"],
            "asos_utc_valid": ob["utc_valid"].isoformat(),
            "diff_degf": diff,
            "abs_diff_degf": abs(diff),
            "lag_seconds": lag_seconds,
        })
    return rows, n_dropped


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    abs_diffs = sorted(r["abs_diff_degf"] for r in rows)
    diffs = [r["diff_degf"] for r in rows]
    lags = [abs(r["lag_seconds"]) for r in rows]
    mean_diff = sum(diffs) / n
    mean_abs_diff = sum(abs_diffs) / n
    median_abs_diff = abs_diffs[n // 2] if n % 2 else (abs_diffs[n // 2 - 1] + abs_diffs[n // 2]) / 2
    return {
        "n": n,
        "mean_diff_degf": mean_diff,
        "mean_abs_diff_degf": mean_abs_diff,
        "median_abs_diff_degf": median_abs_diff,
        "max_abs_diff_degf": abs_diffs[-1],
        "mean_abs_lag_seconds": sum(lags) / n,
        "max_abs_lag_seconds": max(lags),
        **{
            f"disagreement_rate_gte_{tol}degf".replace(".", "_"): sum(
                1 for d in abs_diffs if d >= tol
            ) / n
            for tol in TOLERANCES_F
        },
    }


MIN_EVENTS = 10


def run(tape_dir: str = "tape/settlement_ledger", http: Optional[Http] = None,
        min_events: int = MIN_EVENTS) -> Dict[str, Any]:
    events = load_settled_events(tape_dir)
    if len(events) < min_events:
        return {
            "status": "INSUFFICIENT DATA",
            "n_settled_events": len(events),
            "min_events": min_events,
        }
    http = http or Http()
    rows, n_dropped = build_basis_rows(events, http)
    return {
        "status": "descriptive",
        "note": "NOT a strategy verdict — mapping characterization only, per LOOP-QUEUE Q36",
        "n_settled_events": len(events),
        "n_joined": len(rows),
        "n_dropped_no_asos_ob": n_dropped,
        "summary": summarize(rows),
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tape-dir", default="tape/settlement_ledger")
    p.add_argument("--min-events", type=int, default=MIN_EVENTS)
    args = p.parse_args(argv)
    result = run(tape_dir=args.tape_dir, min_events=args.min_events)
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
