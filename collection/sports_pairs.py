"""Forward capture (READ-ONLY): Kalshi sports moneyline BBO + de-vigged sharp odds.

Serves S7 (sports CLV vs de-vigged sharp line, try-first) and S11 (sharp-anchored maker
quoting). Mirrors `collection/capture_orderbooks.py`'s discipline -- bitemporal
`fetch_ts`, raw-bytes sha256, honest expected-vs-captured completeness -- but is NOT
schema-locked to `core.manifest_schema.CaptureManifest`: that schema keys on
(city, target_date), a weather-specific edge unit. A sports game's edge unit is one
`event_ticker` (a two-or-three-way mutually-exclusive outcome set: e.g. NYY vs TB, or
Argentina/Switzerland/Tie), so this module defines its own line schema.

Kalshi's `/markets` listing already returns top-of-book `yes_ask_dollars` /
`no_ask_dollars` per market (empirically verified 2026-07-09) -- unlike the weather
orderbook capture, no per-market `/orderbook` GET is needed for BBO. That ask is a real,
fillable taker price: tag `real_ask` (CLAUDE.md trust defaults; Hard Rule #3 forces the
bracket_sum divisor via `core.pricing`, never bare ask arithmetic elsewhere).

One pass = for every open Kalshi sports moneyline market (series ticker ending in
`GAME` -- empirically the moneyline/game-winner suffix; SPREAD/TOTAL/prop variants use a
distinct suffix and are excluded), grouped by `event_ticker`:
  - capture the Kalshi leg (real_ask) unconditionally;
  - if `ODDS_API_KEY` is present, fetch matched sportsbook odds and de-vig
    (tag `synthetic` -- a de-vig is a model, not a fill) -- currently only the World Cup
    (`KXWCGAME` -> the-odds-api `soccer_fifa_world_cup`) is mapped, per Q1's
    "soccer/World Cup first" priority; other sports record `no_sport_mapping`;
  - no key -> the odds leg is recorded `BLOCKED(key)` for the whole pass, Kalshi leg
    captured anyway (never block the free half on the paid half).

One JSONL file per pass (not a single append file): tape/ is git-committed, and cloud
runs are stateless/concurrent, so a shared append file would just be a merge-conflict
generator. `tape/sports_pairs/dt=<day>/pass-<capture_id>.jsonl`, one line per game.

Run one pass:
    python -m collection.sports_pairs
    python -m collection.sports_pairs --limit 40
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from core.pricing import bracket_sum
from validation.v3_market import Kalshi, _load_venue_cfg

TAPE = REPO_ROOT / "tape" / "sports_pairs"
SPORTS_CATEGORY = "Sports"
SCHEMA_VERSION = "sp.v0"

# The odds-api base + per-series sport-key mapping. Only World Cup is mapped today
# (Q1 priority: "soccer/World Cup first, then anything listed" -- for the KALSHI leg;
# the odds leg is best-effort and grows as more sports are validated end-to-end).
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SERIES_TO_ODDS_SPORT = {
    "KXWCGAME": "soccer_fifa_world_cup",
}

# ticker = <series>-<match_code>-<outcome>, e.g. KXWCGAME-26JUL11ARGSUI-TIE,
# KXMLBGAME-26JUL091310NYYTB-NYY. Derived empirically from the live API (2026-07-09).
# Kept strict so drift FAILS loudly rather than silently mis-grouping games.
TICKER_RE = re.compile(r'^(?P<series>[A-Z0-9]+)-(?P<match_code>[A-Za-z0-9]+)-(?P<outcome>[A-Z0-9.]+)$')


def parse_ticker(ticker: str) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """Parse a sports-moneyline ticker into (series, match_code, outcome). error is None
    on success. Pure string parsing -- no network, matches v3_market.parse_ticker's shape."""
    m = TICKER_RE.match(ticker)
    if not m:
        return None, "no_regex_match"
    return {"series": m.group("series"), "match_code": m.group("match_code"),
            "outcome": m.group("outcome")}, None


def is_moneyline_series(series: dict) -> bool:
    """Game-winner moneyline series end in GAME (empirically -- SPREAD/TOTAL/prop
    variants use a distinct suffix, never bare GAME; see module docstring)."""
    return (series.get("ticker") or "").endswith("GAME")


def devig_multiplicative(decimal_odds: List[float]) -> List[float]:
    """Standard multiplicative de-vig: implied probs (1/odds) normalized to sum to 1.

    This is a MODEL of fair value, not a fill price -- callers must tag the result
    `synthetic` (core.source_tag), never `real_ask` (CLAUDE.md trust defaults)."""
    if len(decimal_odds) < 2:
        raise ValueError(f"devig needs >=2 outcomes, got {decimal_odds!r}")
    if any(o <= 1.0 for o in decimal_odds):
        raise ValueError(f"decimal odds must all be > 1.0, got {decimal_odds!r}")
    implied = [1.0 / o for o in decimal_odds]
    total = sum(implied)
    return [p / total for p in implied]


def _normalize_name(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (s or "").lower()).strip()


def match_odds_event(kalshi_title: str, odds_events: List[dict]) -> Optional[dict]:
    """Find the odds-api event whose home_team/away_team both appear as tokens in the
    Kalshi market title ('X vs Y Winner?'). Returns None on no/ambiguous match -- a
    silent wrong match would poison S7's CLV number, so ambiguity loses to no match."""
    title_tokens = set(_normalize_name(kalshi_title).split())
    hits = []
    for ev in odds_events:
        home = set(_normalize_name(ev.get("home_team", "")).split())
        away = set(_normalize_name(ev.get("away_team", "")).split())
        if not home or not away:
            continue
        if home <= title_tokens and away <= title_tokens:
            hits.append(ev)
    return hits[0] if len(hits) == 1 else None


def _leg_from_market(m: dict) -> Dict[str, Any]:
    parsed, _err = parse_ticker(m.get("ticker", ""))
    yes_ask = m.get("yes_ask_dollars")
    no_ask = m.get("no_ask_dollars")
    yes_bid = m.get("yes_bid_dollars")
    no_bid = m.get("no_bid_dollars")
    has_ask = yes_ask not in (None, "") and no_ask not in (None, "")
    return {
        "ticker": m.get("ticker", ""),
        "outcome": (parsed or {}).get("outcome") or "",
        "name": m.get("yes_sub_title") or m.get("title") or "",
        "yes_ask": float(yes_ask) if yes_ask not in (None, "") else None,
        "no_ask": float(no_ask) if no_ask not in (None, "") else None,
        "yes_bid": float(yes_bid) if yes_bid not in (None, "") else None,
        "no_bid": float(no_bid) if no_bid not in (None, "") else None,
        "source_tag": "real_ask" if has_ask else None,
        "status": m.get("status", ""),
    }


# --------------------------------------------------------------------------- #
# discovery -- the EXPECTED set, grouped by event_ticker (one game = one group)
# --------------------------------------------------------------------------- #
def discover_moneyline_markets(client: Kalshi, limit: Optional[int] = None
                               ) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, str]]]:
    """Enumerate open sports moneyline markets grouped by event_ticker.

    Returns (groups, series_errors). groups[event_ticker] = {"series": str, "markets": [..]}.
    series_errors records series whose market enumeration failed (a completeness gap
    surfaced, never silently swallowed) -- same discipline as capture_orderbooks."""
    groups: Dict[str, Dict[str, Any]] = {}
    series_errors: List[Dict[str, str]] = []
    seen = 0
    for s in client.series_by_category(SPORTS_CATEGORY):
        if not is_moneyline_series(s):
            continue
        sticker = s.get("ticker", "")
        try:
            markets = client.open_markets(sticker)
        except Exception as exc:  # whole-series enumeration failure -> recorded, not hidden
            series_errors.append({"series": sticker, "error": str(exc)})
            continue
        for m in markets:
            ev = m.get("event_ticker") or ""
            if not ev:
                continue
            g = groups.setdefault(ev, {"series": sticker, "markets": []})
            g["markets"].append(m)
            seen += 1
            if limit and seen >= limit:
                return groups, series_errors
    return groups, series_errors


def build_line(event_ticker: str, series_ticker: str, markets: List[dict],
               fetch_ts: str, odds_leg: Dict[str, Any]) -> Dict[str, Any]:
    """One JSONL line for one game: every leg's real_ask BBO + the bracket overround
    (Hard Rule #3: routed through core.pricing.bracket_sum, never hand-summed) + the
    matched odds leg (synthetic, may be BLOCKED(key)/no_match/no_sport_mapping)."""
    legs = [_leg_from_market(m) for m in sorted(markets, key=lambda m: m.get("ticker", ""))]
    captured_asks = [leg["yes_ask"] for leg in legs if leg["yes_ask"] is not None]
    n_captured = len(captured_asks)

    bs = bracket_sum(captured_asks) if n_captured >= 2 else None
    line: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "venue": "kalshi",
        "fetch_ts": fetch_ts,
        "captured_at": fetch_ts,
        "series": series_ticker,
        "event_ticker": event_ticker,
        "title": markets[0].get("title", "") if markets else "",
        "close_time": markets[0].get("close_time") if markets else None,
        "legs": legs,
        "n_legs": len(legs),
        "n_legs_captured": n_captured,
        "completeness_ok": n_captured == len(legs) and len(legs) > 0,
        "bracket_sum": round(bs, 6) if bs is not None else None,
        "overround_absorbed": round(bs - 1.0, 6) if bs is not None else None,
        "odds": odds_leg,
        "raw_sha256": sha256_hex(canonical_json(
            sorted([[m.get("ticker", ""), sha256_hex(canonical_json(m))] for m in markets]))),
    }
    return line


# --------------------------------------------------------------------------- #
# odds leg -- best-effort, gated entirely on ODDS_API_KEY presence
# --------------------------------------------------------------------------- #
def fetch_odds_leg(odds_client: Kalshi, series_ticker: str, title: str, api_key: str
                   ) -> Dict[str, Any]:
    """Fetch + de-vig the matched sportsbook line for one game. Never called when
    ODDS_API_KEY is absent (see run()) -- that gate lives one level up so a keyless
    pass makes zero odds-api calls."""
    sport_key = SERIES_TO_ODDS_SPORT.get(series_ticker)
    if not sport_key:
        return {"status": "no_sport_mapping"}
    try:
        events = odds_client.get(f"/sports/{sport_key}/odds", apiKey=api_key,
                                 regions="us,uk,eu", markets="h2h", oddsFormat="decimal")
    except Exception as exc:
        return {"status": f"error:{exc}"}
    if not isinstance(events, list):
        return {"status": "no_match"}
    ev = match_odds_event(title, events)
    if ev is None:
        return {"status": "no_match"}
    book = next((b for b in ev.get("bookmakers", []) if b.get("key") == "pinnacle"),
               ev.get("bookmakers", [None])[0])
    if not book:
        return {"status": "no_match"}
    h2h = next((mk for mk in book.get("markets", []) if mk.get("key") == "h2h"), None)
    outcomes = (h2h or {}).get("outcomes") or []
    if len(outcomes) < 2:
        return {"status": "no_match"}
    fair = devig_multiplicative([float(o["price"]) for o in outcomes])
    return {
        "status": "ok",
        "book": book.get("key"),
        "commence_time": ev.get("commence_time"),
        "outcomes": [{"name": o["name"], "decimal_odds": float(o["price"]),
                      "fair_prob": round(p, 6), "source_tag": "synthetic"}
                     for o, p in zip(outcomes, fair)],
    }


# --------------------------------------------------------------------------- #
# capture -- one pass, one JSONL file, honest completeness
# --------------------------------------------------------------------------- #
def run(limit: Optional[int] = None, min_interval: float = 0.2,
        client: Optional[Kalshi] = None, odds_client: Optional[Kalshi] = None,
        store: Optional[Path] = None, odds_api_key: Optional[str] = None) -> Dict:
    """One read-only capture pass. `client`/`odds_client`/`store`/`odds_api_key` are
    injectable for offline testing; in production all default to live clients, the
    real tape store, and the ODDS_API_KEY env var."""
    store = Path(store) if store is not None else TAPE
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)
    if odds_api_key is None:
        odds_api_key = os.environ.get("ODDS_API_KEY")
    if odds_client is None and odds_api_key:
        odds_client = Kalshi(ODDS_API_BASE, min_interval=min_interval)

    cap_ts = datetime.now(timezone.utc)
    fetch_ts = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    groups, series_errors = discover_moneyline_markets(client, limit=limit)

    lines: List[Dict[str, Any]] = []
    degenerate: List[Dict[str, Any]] = []
    for ev, g in sorted(groups.items()):
        markets = g["markets"]
        if len(markets) < 2:
            # a "game" with < 2 mutually-exclusive outcomes isn't a scoreable edge unit
            degenerate.append({"event_ticker": ev, "n_markets": len(markets)})
            continue
        if not odds_api_key:
            odds_leg = {"status": "BLOCKED(key)"}
        else:
            odds_leg = fetch_odds_leg(odds_client, g["series"], markets[0].get("title", ""),
                                      odds_api_key)
        lines.append(build_line(ev, g["series"], markets, fetch_ts, odds_leg))

    out_dir = store / f"dt={day}"
    out_path = out_dir / f"pass-{capture_id}.jsonl"
    if lines:
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            for line in lines:
                f.write(canonical_json(line) + "\n")

    n_complete = sum(1 for l in lines if l["completeness_ok"])
    summary = {
        "capture_id": capture_id, "day": day, "fetch_ts": fetch_ts,
        "n_games": len(lines), "n_complete": n_complete,
        "n_degenerate": len(degenerate), "n_series_errors": len(series_errors),
        "odds_status": "ok" if odds_api_key else "BLOCKED(key)",
        "out_path": str(out_path) if lines else None,
    }
    print(f"[sports_pairs] {capture_id}: {summary['n_games']} games, {n_complete} complete, "
         f"odds={summary['odds_status']} -> {summary['out_path']}")
    if series_errors:
        print(f"[sports_pairs] WARN {len(series_errors)} series failed enumeration "
             f"(games may be missing this pass)", file=sys.stderr)
    if degenerate:
        print(f"[sports_pairs] WARN {len(degenerate)} discovered event(s) had < 2 outcomes "
             f"(gap recorded, no line emitted)", file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Sports moneyline BBO capture (read-only)")
    ap.add_argument("--limit", type=int, default=None, help="cap markets discovered per pass")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    run(limit=args.limit, min_interval=args.min_interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
