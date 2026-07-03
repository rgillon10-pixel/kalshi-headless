"""Historical settled-game sourcing (READ-ONLY) — LOOP-QUEUE.md Q4/S7a.

Two independent legs, captured separately with NO game-matching/join yet — that join
(team-name normalization across the two venues' conventions) is the next stage (S7b),
mirroring Q1's odds-api leg precedent: capture what's reachable now, honestly flag what
isn't, leave matching for when it's tested against real paired data.

**Load-bearing discovery (2026-07-03), documented here and in the S7a finding:** Kalshi's
public `/markets` (and therefore `/candlesticks`, which needs a live market object to
resolve) only serves a settled market for roughly the ~60 days after it closes — NOT a
full season. `/events?status=settled` keeps listing the event indefinitely, but its
markets 404 once purged. Empirically: an NBA game settled 2026-04-30 still had markets;
one settled 2026-04-24 (six days older) did not. Every 2025-season NFL game (last settled
~2026-02) is fully purged; NBA only the playoff tail (~2026-04-30 onward) survives; World
Cup 2026 (started ~2026-06-11) is the one series where the whole tournament-to-date is
still live. `fetch_kalshi_settled` below flags every event `retention_available: true/false`
— it never silently drops a purged event, and it never fabricates a price for one.

**Second trap, also load-bearing:** a sports market's `occurrence_datetime` /
`expected_expiration_time` is NOT kickoff — it is the expected *resolution* time, within
seconds-to-minutes of `close_time` (empirically confirmed on both an NBA and a World Cup
game: `close_time` sits 20s-18min *before* `occurrence_datetime`, i.e. both cluster at
game END, not game start). A first draft of this collector used `occurrence_datetime` as
"decision time" and silently pulled a candlestick from minutes before final settlement —
already at/near $1.00 or $0.00, not a pregame price. Caught before commit by inspecting a
live sample (a Switzerland-vs-Algeria game showing `yes_ask=1.0` on *every* outcome, which
is impossible pregame). Kalshi's market object has no kickoff field; the fix (this
version) does NOT fabricate a decision timestamp — it captures the raw timing fields
(`open_time`, `close_time`, `occurrence_datetime`) plus one honestly-labeled
`sample_ask_near_close` candlestick (proves the candlestick pipeline resolves a real ask;
explicitly NOT a pregame/CLV price). True decision-time (pregame) pricing needs the game's
actual kickoff, which only the ESPN leg's `date` field carries — that join is S7b's job,
not this stage's.

ESPN leg (`fetch_espn_closing_odds`): ESPN's public event-summary API relays one
sportsbook's (DraftKings, provider id 100) `pickcenter[].moneyline`, which carries
distinct `open`/`close` legs — a free, reachable closing-line proxy. Tagged `synthetic`
per CLAUDE.md (an external reference price, never a Kalshi fill) — and it is DraftKings
(retail), not Pinnacle (sharp) as S7's spec preferred; Pinnacle publishes no free API.
That is a real limitation of this data source, documented rather than glossed over.

Run:
    python -m collection.sports_history kalshi --series KXWCGAME --limit 20
    python -m collection.sports_history espn --sport soccer --league fifa.world --dates 20260615-20260620
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from validation.v3_market import Kalshi, _load_venue_cfg

TAPE = REPO_ROOT / "tape" / "sports_history"
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
DRAFTKINGS_PROVIDER_ID = "100"


# --------------------------------------------------------------------------- #
# Kalshi leg — settled events, decision-time real_ask off candlesticks
# --------------------------------------------------------------------------- #
def fetch_settled_events(client: Kalshi, series: str, limit: Optional[int] = None
                         ) -> tuple[List[Dict], List[str]]:
    """Paginate /events?series_ticker=...&status=settled. Kalshi keeps listing these
    even once the underlying markets have been purged (see module docstring)."""
    events: List[Dict] = []
    raw_pages: List[str] = []
    cursor: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"series_ticker": series, "status": "settled", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        text = client.get_text("/events", **params)
        raw_pages.append(text)
        j = json.loads(text)
        events.extend(j.get("events") or [])
        cursor = j.get("cursor")
        if not cursor or (limit and len(events) >= limit):
            break
    return (events[:limit] if limit else events), raw_pages


def candlestick_ask_before(client: Kalshi, series: str, ticker: str, before_ts: datetime,
                           lookback_hours: int = 6) -> Optional[Dict]:
    """Last hourly candlestick with `end_period_ts <= before_ts`: its
    `yes_ask.close_dollars` as a real, fillable taker price at that moment. Deliberately
    generic — callers decide what `before_ts` means (this module does NOT claim it is
    kickoff; see module docstring's second trap). None if the window has no candlesticks
    (market purged, or no trading occurred in the window)."""
    end_ts = int(before_ts.timestamp())
    start_ts = end_ts - lookback_hours * 3600
    j = client.get(f"/series/{series}/markets/{ticker}/candlesticks",
                   start_ts=start_ts, end_ts=end_ts, period_interval=60)
    candles = [c for c in (j.get("candlesticks") or []) if c.get("end_period_ts", 0) <= end_ts]
    if not candles:
        return None
    last = max(candles, key=lambda c: c["end_period_ts"])
    ya = (last.get("yes_ask") or {}).get("close_dollars")
    if ya is None:
        return None
    return {"yes_ask": float(ya), "end_period_ts": last["end_period_ts"],
            "price_source_tag": "real_ask"}


def fetch_kalshi_settled(client: Kalshi, series: str, limit: int,
                         tape_dir: Optional[Path] = None) -> Dict:
    """One pass: settled events for `series`, raw timing fields + a `sample_ask_near_close`
    real_ask per outcome market where the market is still retrievable
    (`retention_available`); honestly flagged (never dropped) where it has aged out of
    Kalshi's public retention window. NOT a pregame/decision price — see module docstring's
    second trap; true decision-time pricing needs S7b's ESPN-kickoff join."""
    tape_dir = Path(tape_dir) if tape_dir is not None else TAPE
    cap_ts = datetime.now(timezone.utc)
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    events, raw_pages = fetch_settled_events(client, series, limit=limit)
    lines: List[str] = []
    n_retained = 0
    for e in events:
        event_ticker = e.get("event_ticker", "")
        markets_text = client.get_text("/markets", event_ticker=event_ticker)
        markets = json.loads(markets_text).get("markets") or []
        retention_available = bool(markets)
        outcomes: List[Dict] = []
        if retention_available:
            n_retained += 1
            for m in markets:
                close_time_raw = m.get("close_time")
                sample_ask = None
                if close_time_raw:
                    close_ts = datetime.fromisoformat(close_time_raw.replace("Z", "+00:00"))
                    sample_ask = candlestick_ask_before(client, series, m["ticker"], close_ts,
                                                        lookback_hours=2)
                outcomes.append({
                    "ticker": m.get("ticker"), "title": m.get("title"), "result": m.get("result"),
                    "open_time": m.get("open_time"), "close_time": close_time_raw,
                    "occurrence_datetime": m.get("occurrence_datetime"),
                    "sample_ask_near_close": sample_ask,
                })
        record = {
            "schema_version": "sports_history_kalshi.v1",
            "capture_id": capture_id, "captured_at": cap_ts.isoformat(),
            "series": series, "event_ticker": event_ticker,
            "title": e.get("title"), "sub_title": e.get("sub_title"),
            "retention_available": retention_available,
            "outcomes": outcomes,
        }
        lines.append(canonical_json(record))

    summary = {
        "capture_id": capture_id, "day": day, "series": series,
        "n_events": len(events), "n_retention_available": n_retained,
        "raw_sha256": sha256_hex("".join(raw_pages)),
    }
    if lines:
        tape_dir.mkdir(parents=True, exist_ok=True)
        out_path = tape_dir / f"dt={day}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
        summary["path"] = str(out_path)
    print(f"[sports_history:kalshi] {series}: {len(events)} settled events, "
          f"{n_retained} retention_available")
    return summary


# --------------------------------------------------------------------------- #
# ESPN leg — free closing-line odds (DraftKings via ESPN, open+close both present)
# --------------------------------------------------------------------------- #
def fetch_espn_scoreboard(sport: str, league: str, dates: str) -> Dict:
    r = requests.get(f"{ESPN_BASE}/{sport}/{league}/scoreboard",
                     params={"dates": dates}, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_espn_summary(sport: str, league: str, event_id: str) -> Dict:
    r = requests.get(f"{ESPN_BASE}/{sport}/{league}/summary",
                     params={"event": event_id}, timeout=30)
    r.raise_for_status()
    return r.json()


def extract_closing_moneyline(summary: Dict) -> Optional[Dict]:
    """DraftKings (provider 100, ESPN's `pickcenter[0]`) open+close moneyline. None if
    ESPN carries no odds for this event (common for lower-profile games/leagues)."""
    pc = summary.get("pickcenter") or []
    if not pc:
        return None
    entry = pc[0]
    ml = entry.get("moneyline") or {}
    if not ml:
        return None
    out = {
        "provider": (entry.get("provider") or {}).get("name"),
        "provider_id": (entry.get("provider") or {}).get("id"),
        "home_open": ((ml.get("home") or {}).get("open") or {}).get("odds"),
        "home_close": ((ml.get("home") or {}).get("close") or {}).get("odds"),
        "away_open": ((ml.get("away") or {}).get("open") or {}).get("odds"),
        "away_close": ((ml.get("away") or {}).get("close") or {}).get("odds"),
        "price_source_tag": "synthetic",
    }
    if "draw" in ml:
        out["draw_open"] = ((ml.get("draw") or {}).get("open") or {}).get("odds")
        out["draw_close"] = ((ml.get("draw") or {}).get("close") or {}).get("odds")
    return out


def fetch_espn_closing_odds(sport: str, league: str, dates: str,
                            tape_dir: Optional[Path] = None) -> Dict:
    """One pass: ESPN scoreboard for `dates` (`YYYYMMDD` or `YYYYMMDD-YYYYMMDD`), each
    event's DraftKings open/close moneyline via the per-event summary endpoint."""
    tape_dir = Path(tape_dir) if tape_dir is not None else TAPE
    cap_ts = datetime.now(timezone.utc)
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    sb = fetch_espn_scoreboard(sport, league, dates)
    events = sb.get("events") or []
    lines: List[str] = []
    n_with_odds = 0
    n_fetch_errors = 0
    for e in events:
        eid = e.get("id")
        try:
            summ = fetch_espn_summary(sport, league, eid)
        except Exception:
            n_fetch_errors += 1
            summ = {}
        ml = extract_closing_moneyline(summ)
        if ml:
            n_with_odds += 1
        record = {
            "schema_version": "sports_history_espn.v1",
            "capture_id": capture_id, "captured_at": cap_ts.isoformat(),
            "sport": sport, "league": league, "espn_event_id": eid,
            "name": e.get("name"), "date": e.get("date"),
            "status": ((e.get("status") or {}).get("type") or {}).get("name"),
            "moneyline": ml,
        }
        lines.append(canonical_json(record))

    summary = {
        "capture_id": capture_id, "day": day, "sport": sport, "league": league, "dates": dates,
        "n_events": len(events), "n_with_odds": n_with_odds, "n_fetch_errors": n_fetch_errors,
    }
    if lines:
        tape_dir.mkdir(parents=True, exist_ok=True)
        out_path = tape_dir / f"dt={day}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
        summary["path"] = str(out_path)
    print(f"[sports_history:espn] {sport}/{league} {dates}: {len(events)} events, "
          f"{n_with_odds} with DraftKings odds, {n_fetch_errors} fetch errors")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S7a historical sourcing (read-only)")
    sub = ap.add_subparsers(dest="leg", required=True)

    pk = sub.add_parser("kalshi")
    pk.add_argument("--series", required=True)
    pk.add_argument("--limit", type=int, default=20)
    pk.add_argument("--min-interval", type=float, default=0.2)

    pe = sub.add_parser("espn")
    pe.add_argument("--sport", required=True)
    pe.add_argument("--league", required=True)
    pe.add_argument("--dates", required=True)

    args = ap.parse_args(argv)
    if args.leg == "kalshi":
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=args.min_interval)
        fetch_kalshi_settled(client, args.series, args.limit)
    else:
        fetch_espn_closing_odds(args.sport, args.league, args.dates)
    return 0


if __name__ == "__main__":
    sys.exit(main())
