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
import math
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from collection.sports_pairs import devig_multiplicative
from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from core.pricing import bracket_sum
from validation.v3_market import Kalshi, _load_venue_cfg

TAPE = REPO_ROOT / "tape" / "sports_history"
CLV_TAPE = REPO_ROOT / "tape" / "sports_clv"
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


# --------------------------------------------------------------------------- #
# S7b — event matching: Kalshi settled event <-> ESPN closing-odds event
# --------------------------------------------------------------------------- #
# A Kalshi game title is one of (all observed live, S7a tape 2026-07-03):
#   "Switzerland vs Algeria: Regulation Time Moneyline SUI vs DZA (Jul 2)"   (WC, full form)
#   "Cape Verde vs Saudi Arabia"                                            (WC, bare form)
#   "Game 5: New York at San Antonio NYK at SAS (Jun 13)"                   (NBA)
# Strip the trailing "(Mon DD)", the redundant "<CODE> vs/at <CODE>" ticker-code repeat,
# the ": Regulation Time Moneyline" suffix, and a leading "Game N:" — whichever are
# present — leaving "<team A> vs/at <team B>" in ticker team-code order.
_TRAILING_DATE_RE = re.compile(r"\s*\([A-Za-z]+\s+\d{1,2}\)\s*$")
_TRAILING_CODE_PAIR_RE = re.compile(r"\s+[A-Z]{2,4}\s+(?:vs\.?|at)\s+[A-Z]{2,4}\s*$")
_TRAILING_MONEYLINE_RE = re.compile(r":\s*Regulation Time Moneyline\s*$", re.I)
_GAME_PREFIX_RE = re.compile(r"^Game\s+\d+:\s*", re.I)
_TEAM_SPLIT_RE = re.compile(r"\s+(?:vs\.?|at)\s+", re.I)
_ESPN_SPLIT_RE = re.compile(r"\s+at\s+", re.I)
# Event ticker's trailing team-code segment, e.g. "KXWCGAME-26JUL02SUIDZA" -> teams="SUIDZA".
_EVENT_TICKER_RE = re.compile(r"-(?P<yy>\d{2})(?P<mon>[A-Z]{3})(?P<dd>\d{2})(?P<teams>[A-Z0-9]+)$")


def extract_kalshi_teams(title: str) -> Optional[Tuple[str, str]]:
    """Pull the two full team names out of a Kalshi sports-game title (see forms above).
    Order is preserved (team A, team B) — assumed (and unit-tested against live samples)
    to match the event ticker's team-code order, which `_event_team_codes` reads
    independently. None if the title doesn't parse into an "A vs/at B" shape."""
    s = title.strip()
    s = _TRAILING_DATE_RE.sub("", s)
    s = _TRAILING_CODE_PAIR_RE.sub("", s)
    s = _TRAILING_MONEYLINE_RE.sub("", s)
    s = _GAME_PREFIX_RE.sub("", s)
    parts = _TEAM_SPLIT_RE.split(s, maxsplit=1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        return None
    return parts[0].strip(), parts[1].strip()


def _espn_teams(name: str) -> Optional[Tuple[str, str]]:
    """ESPN scoreboard `name` is always "<away> at <home>"."""
    parts = _ESPN_SPLIT_RE.split((name or "").strip(), maxsplit=1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        return None
    return parts[0].strip(), parts[1].strip()


def _event_team_codes(event_ticker: str) -> Optional[Tuple[str, str]]:
    """Split an event ticker's team-code segment into (code_a, code_b) — a 3+3 letter
    split (every sampled series, KXWCGAME/KXNBAGAME/KXNFLGAME, uses 3-letter codes;
    verified against S7a's live tape). None if the segment isn't exactly 6 chars, so a
    non-conforming series is honestly unmapped rather than mis-split."""
    m = _EVENT_TICKER_RE.search(event_ticker or "")
    if not m:
        return None
    teams = m["teams"]
    if len(teams) != 6:
        return None
    return teams[:3], teams[3:]


def _kalshi_event_date(event_ticker: str):
    m = _EVENT_TICKER_RE.search(event_ticker or "")
    if not m:
        return None
    try:
        return datetime.strptime(f"{m['yy']}{m['mon']}{m['dd']}", "%y%b%d").date()
    except ValueError:
        return None


def _espn_event_date(espn_record: Dict):
    d = espn_record.get("date")
    if not d:
        return None
    try:
        return datetime.fromisoformat(d.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def normalize_team_name(name: str) -> str:
    """Lowercase, strip accents/punctuation/whitespace — a comparable form for Kalshi vs
    ESPN team names (e.g. "Türkiye" vs "Turkiye", "Congo DR" vs "Congo DR")."""
    nfkd = unicodedata.normalize("NFKD", name or "")
    ascii_form = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", ascii_form.lower())


def _names_match(a: str, b: str) -> bool:
    """One normalized name contains the other — handles the NBA city-name-vs-full-team-
    name case ("sanantonio" in "sanantoniospurs")."""
    if not a or not b:
        return False
    return a in b or b in a


def _base_match_row(ke: Dict) -> Dict:
    return {"kalshi_event_ticker": ke.get("event_ticker"), "series": ke.get("series"),
            "kalshi_title": ke.get("title")}


def match_kalshi_espn(kalshi_events: List[Dict], espn_events: List[Dict],
                      max_date_delta_days: int = 1) -> List[Dict]:
    """For each Kalshi settled-event record, find its ESPN closing-odds counterpart by
    team-name containment (BOTH teams must match one ESPN event) with kickoff-date
    proximity as a safety check (Kalshi's own date token vs ESPN's real kickoff can differ
    by a day across timezones — S7a's second trap). `match_status` is one of "matched"
    (exactly one candidate), "ambiguous" (>1 candidate — never silently picks one),
    "no_match" (0 candidates), or "unparseable_title" — every input row gets an output
    row, nothing is silently dropped."""
    out = []
    for ke in kalshi_events:
        teams = extract_kalshi_teams(ke.get("title") or "")
        if teams is None:
            out.append({**_base_match_row(ke), "match_status": "unparseable_title"})
            continue
        team_a, team_b = teams
        na, nb = normalize_team_name(team_a), normalize_team_name(team_b)
        kalshi_date = _kalshi_event_date(ke.get("event_ticker") or "")
        candidates = []
        for ee in espn_events:
            e_teams = _espn_teams(ee.get("name") or "")
            if e_teams is None:
                continue
            away, home = e_teams
            n_away, n_home = normalize_team_name(away), normalize_team_name(home)
            a_to_away, a_to_home = _names_match(na, n_away), _names_match(na, n_home)
            b_to_away, b_to_home = _names_match(nb, n_away), _names_match(nb, n_home)
            if not ((a_to_away and b_to_home) or (a_to_home and b_to_away)):
                continue
            if kalshi_date is not None:
                e_date = _espn_event_date(ee)
                if e_date is not None and abs((e_date - kalshi_date).days) > max_date_delta_days:
                    continue
            candidates.append((ee, "a_away" if a_to_away else "a_home"))
        if not candidates:
            out.append({**_base_match_row(ke), "match_status": "no_match"})
        elif len(candidates) > 1:
            out.append({**_base_match_row(ke), "match_status": "ambiguous",
                        "candidate_espn_ids": [c[0].get("espn_event_id") for c in candidates]})
        else:
            ee, orientation = candidates[0]
            out.append({**_base_match_row(ke), "match_status": "matched",
                        "espn_event_id": ee.get("espn_event_id"), "espn_record": ee,
                        "team_a": team_a, "team_b": team_b, "orientation": orientation})
    return out


# --------------------------------------------------------------------------- #
# S7b — DraftKings-close de-vig + real pregame ask join
# --------------------------------------------------------------------------- #
def american_to_decimal(odds) -> float:
    v = float(odds)
    if v > 0:
        return 1.0 + v / 100.0
    if v < 0:
        return 1.0 + 100.0 / abs(v)
    raise ValueError(f"american odds cannot be 0, got {odds!r}")


def devig_closing_fair_probs(moneyline: Optional[Dict]) -> Optional[Dict[str, float]]:
    """De-vig DraftKings' CLOSING line (home/away[/draw]) into fair probabilities via
    `sports_pairs.devig_multiplicative`. Tagged `synthetic` by the caller (CLAUDE.md: a
    de-vig is a model, never a fill). None if any required closing price is missing."""
    if not moneyline:
        return None
    keys = ["home", "away"] + (["draw"] if "draw_close" in moneyline else [])
    raw = [moneyline.get(f"{k}_close") for k in keys]
    if any(r is None for r in raw):
        return None
    fair = devig_multiplicative([american_to_decimal(r) for r in raw])
    return dict(zip(keys, fair))


def _taker_fee_per_contract(price: float, rate: float = 0.07) -> float:
    """Round-up-to-cent taker fee per contract. Mirrors `scripts/fee_breakeven.py`'s
    `fee_per_contract` (the documented source of this formula, from Kalshi's published fee
    schedule) — duplicated as a tiny pure function rather than importing across the
    scripts/collection boundary, since `scripts/` is not an installed package."""
    raw = rate * price * (1.0 - price)
    return math.ceil(raw * 100.0) / 100.0


def load_tape_records(path: Path, schema_version: str) -> List[Dict]:
    """Read back only the rows of one schema from a JSONL tape day-file."""
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("schema_version") == schema_version:
                out.append(rec)
    return out


def run_clv_join(client: Kalshi, kalshi_events: List[Dict], espn_events: List[Dict],
                 tape_dir: Optional[Path] = None) -> Dict:
    """One join pass (S7b): match already-captured Kalshi settled-event records to
    already-captured ESPN closing-odds records, pull each matched game's real PREGAME ask
    per outcome (candlestick anchored at ESPN's actual kickoff — not Kalshi's own timing
    fields, per S7a's second trap), de-vig DraftKings' close, and persist the paired
    per-game record with independent per-field `price_source_tag`s. Live network: one
    `candlestick_ask_before` call per outcome market of every matched game."""
    tape_dir = Path(tape_dir) if tape_dir is not None else CLV_TAPE
    cap_ts = datetime.now(timezone.utc)
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    matches = match_kalshi_espn(kalshi_events, espn_events)
    by_ticker = {ke.get("event_ticker"): ke for ke in kalshi_events}
    lines: List[str] = []
    n_matched = n_priced = 0
    status_counts: Dict[str, int] = {}
    for row in matches:
        status_counts[row["match_status"]] = status_counts.get(row["match_status"], 0) + 1
        if row["match_status"] != "matched":
            continue
        n_matched += 1
        ke = by_ticker.get(row["kalshi_event_ticker"])
        ee = row["espn_record"]
        kickoff_raw = ee.get("date")
        fair = devig_closing_fair_probs(ee.get("moneyline"))
        codes = _event_team_codes(ke.get("event_ticker") or "")
        a_is_away = row["orientation"] == "a_away"
        code_to_fair_key: Dict[str, str] = {}
        if codes:
            code_a, code_b = codes
            code_to_fair_key[code_a] = "away" if a_is_away else "home"
            code_to_fair_key[code_b] = "home" if a_is_away else "away"

        kickoff_ts = None
        if kickoff_raw:
            kickoff_ts = datetime.fromisoformat(kickoff_raw.replace("Z", "+00:00"))

        outcomes_out = []
        yes_asks = []
        for o in ke.get("outcomes", []):
            ticker = o.get("ticker", "")
            outcome_code = ticker.rsplit("-", 1)[-1] if ticker else ""
            ask = None
            if kickoff_ts is not None:
                ask = candlestick_ask_before(client, ke["series"], ticker, kickoff_ts,
                                             lookback_hours=6)
            if ask is not None:
                yes_asks.append(ask["yes_ask"])
            fair_key = "draw" if outcome_code == "TIE" else code_to_fair_key.get(outcome_code)
            fair_prob = fair.get(fair_key) if (fair and fair_key) else None
            outcomes_out.append({
                "ticker": ticker, "outcome_code": outcome_code, "fair_key": fair_key,
                "pregame_ask": ask,
                "fair_prob": fair_prob,
                "fair_prob_source_tag": "synthetic" if fair_prob is not None else None,
            })

        bsum = bracket_sum(yes_asks) if yes_asks else None
        priced_any = False
        for oc in outcomes_out:
            ask, fp = oc["pregame_ask"], oc["fair_prob"]
            if ask is None or fp is None:
                continue
            priced_any = True
            oc["edge_raw"] = fp - ask["yes_ask"]
            oc["fee_per_contract"] = _taker_fee_per_contract(ask["yes_ask"])
            oc["edge_after_fee"] = oc["edge_raw"] - oc["fee_per_contract"]
        if priced_any:
            n_priced += 1

        record = {
            "schema_version": "sports_clv_join.v1",
            "capture_id": capture_id, "captured_at": cap_ts.isoformat(),
            "kalshi_event_ticker": ke.get("event_ticker"), "series": ke.get("series"),
            "espn_event_id": ee.get("espn_event_id"), "kickoff_ts": kickoff_raw,
            "team_a": row["team_a"], "team_b": row["team_b"],
            "bracket_sum": bsum, "overround_absorbed": (bsum - 1.0) if bsum else None,
            "outcomes": outcomes_out,
            "priced": priced_any,
            "price_source_tag": "mixed",  # composite record — per-field tags are load-bearing
        }
        lines.append(canonical_json(record))

    summary = {
        "capture_id": capture_id, "day": day,
        "n_kalshi_events": len(kalshi_events), "n_espn_events": len(espn_events),
        "match_status_counts": status_counts,
        "n_matched": n_matched, "n_priced": n_priced,
    }
    if lines:
        tape_dir.mkdir(parents=True, exist_ok=True)
        out_path = tape_dir / f"dt={day}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
        summary["path"] = str(out_path)
    print(f"[sports_history:join] {len(kalshi_events)} kalshi events, "
          f"{len(espn_events)} espn events -> {status_counts}, {n_priced}/{n_matched} priced")
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

    pj = sub.add_parser("join")
    pj.add_argument("--history-tape", default=None,
                    help="path to a sports_history dt=YYYY-MM-DD.jsonl (default: today's)")
    pj.add_argument("--espn-fetch", nargs="*", default=[],
                    help="sport:league:dates triples to freshly pull ESPN odds for before "
                         "joining, e.g. soccer:fifa.world:20260626-20260702")
    pj.add_argument("--min-interval", type=float, default=0.2)

    args = ap.parse_args(argv)
    if args.leg == "kalshi":
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=args.min_interval)
        fetch_kalshi_settled(client, args.series, args.limit)
    elif args.leg == "espn":
        fetch_espn_closing_odds(args.sport, args.league, args.dates)
    else:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tape_path = Path(args.history_tape) if args.history_tape else TAPE / f"dt={day}.jsonl"
        for target in args.espn_fetch:
            sport, league, dates = target.split(":")
            fetch_espn_closing_odds(sport, league, dates, tape_dir=tape_path.parent)
        kalshi_events = load_tape_records(tape_path, "sports_history_kalshi.v1")
        espn_events = load_tape_records(tape_path, "sports_history_espn.v1")
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=args.min_interval)
        run_clv_join(client, kalshi_events, espn_events)
    return 0


if __name__ == "__main__":
    sys.exit(main())
