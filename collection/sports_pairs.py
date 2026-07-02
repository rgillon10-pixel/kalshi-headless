"""Sports moneyline paired-odds collector (READ-ONLY) — serves S7/S11.

One pass = for every open Kalshi sports moneyline market (soccer/World Cup first, since
the 2026 World Cup ends Jul 19 — then every other "GAME" family listed): snapshot the
yes/no BBO for every leg of the event (tag `real_ask` — these are the live top-of-book
ask/bid fields the `/markets` list endpoint already returns, no orderbook fetch needed)
and, when `ODDS_API_KEY` is present, the matched sportsbook de-vigged fair price (tag
`synthetic` — a de-vig is a model, not a fill). Append one JSONL line per event under
`tape/sports_pairs/` (tape/ is committed by design, see `tape/README.md`).

Ticker grammar (derived empirically from the live API, same discipline as
`validation/v3_market.py`): Kalshi sports moneyline tickers are
`<SERIES>-<EVENT>-<OUTCOME>` (e.g. `KXMLBGAME-26JUL051700TORSEA-TOR`,
`KXWCGAME-26JUL06USABEL-TIE`). All markets sharing one game are grouped by the API's own
`event_ticker` field; a series is classified as "moneyline" by ticker suffix `GAME`
(empirically: every real head-to-head "<Team> vs <Team> Winner?" family observed in the
Sports category ends in GAME; quarter/half/set-winner and prop series use other suffixes
and are excluded on purpose — this is Kalshi's own naming convention, not assumed).

Completeness (mirrors `collection/capture_orderbooks.py`'s discipline): a series whose
enumeration call fails is recorded as a series_error (never silently dropped); an event
whose leg count is short of what that series is known to support (2-way, or 3-way if any
event in the series has a `TIE` leg) is flagged `completeness_ok=False`, never hidden.

Odds-API leg: matching a Kalshi event to a specific the-odds-api bookmaker line requires a
team-name reconciliation table this collector does not yet build (Kalshi uses short codes
like `TOR`/`SEA`; the-odds-api uses full team names) — deliberately deferred, not guessed.
Until `ODDS_API_KEY` exists AND that mapping is built, the odds leg is recorded as
`{"status": "blocked", "reason": "ODDS_API_KEY missing"}` (or `"team matching not
implemented"` if a key exists but matching doesn't). The de-vig math itself
(`devig_proportional`) is implemented and unit-tested against a fixture odds payload so it
is ready the moment the matching gap is closed.

Run one pass:
    python -m collection.sports_pairs             # all open moneyline events
    python -m collection.sports_pairs --limit 20   # cap series scanned (smoke test)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from core.pricing import bracket_sum, normalized_ask, overround
from core.source_tag import tag_or_synthetic
from validation.v3_market import Kalshi, _load_venue_cfg

SCHEMA_VERSION = "sports_pairs.v0"
STORE = REPO_ROOT / "tape" / "sports_pairs"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_UA = {"User-Agent": "kalshi-headless/0.0 (research collection)"}

TICKER_RE = re.compile(r"^(?P<series>[A-Z0-9]+)-(?P<event>[A-Z0-9.]+)-(?P<outcome>[A-Z0-9.]+)$")

# Every series that has ever been "soccer/World Cup" priority for this time-sensitive
# window (the ticker itself contains WC — World Cup / Club World Cup) is captured first;
# everything else in the moneyline ("GAME") family follows, alphabetically.
_SOCCER_FIRST = re.compile(r"WC")


def parse_sports_ticker(ticker: str) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """Parse `<SERIES>-<EVENT>-<OUTCOME>` into its parts. Returns (parts, error)."""
    m = TICKER_RE.match(ticker)
    if not m:
        return None, "no_regex_match"
    return {"series": m.group("series"), "event": m.group("event"),
            "outcome": m.group("outcome")}, None


def _is_moneyline_series(ticker: str) -> bool:
    """Series-level classifier: the head-to-head "<Team> vs <Team> Winner?" family all
    share the ticker suffix GAME (empirically observed across every league in the Sports
    category — soccer, NFL, NBA, MLB, NHL, esports); quarter/half/set-winner and prop
    series use distinct suffixes (WINNER, ML, GWINNER, ...) and are excluded on purpose."""
    return ticker.endswith("GAME")


def _sort_key(ticker: str) -> Tuple[int, str]:
    return (0 if _SOCCER_FIRST.search(ticker) else 1, ticker)


# --------------------------------------------------------------------------- #
# de-vig math — pure functions, reuse the sanctioned bracket_sum/normalized_ask
# site (core/pricing.py, Hard Rule #3) rather than dividing by hand.
# --------------------------------------------------------------------------- #
def devig_proportional(implied_probs: List[float]) -> List[float]:
    """Proportional (multiplicative) de-vig: normalize vigged implied probabilities so
    they sum to 1. This is a MODEL of fair probability, never a fill price — callers must
    tag the result `synthetic` (CLAUDE.md trust defaults), same spirit as Hard Rule #3's
    ban on treating a raw ask as a probability."""
    total = bracket_sum(implied_probs)
    return [normalized_ask(p, total) for p in implied_probs]


def _parse_odds_h2h_response(payload: List[dict], prefer_book: str = "pinnacle"
                             ) -> List[Dict[str, Any]]:
    """Parse a the-odds-api `/v4/sports/{sport}/odds?markets=h2h&oddsFormat=decimal`
    response into per-event {home_team, away_team, commence_time, book, outcomes:
    {team: decimal_odds}}. Pure parsing logic — unit-tested against a fixture payload
    matching the documented v4 schema, independent of whether a live key is available."""
    out = []
    for ev in payload:
        books = ev.get("bookmakers") or []
        book = next((b for b in books if b.get("key") == prefer_book), None) or (
            books[0] if books else None)
        if book is None:
            continue
        market = next((m for m in (book.get("markets") or []) if m.get("key") == "h2h"), None)
        if market is None:
            continue
        outcomes = {o["name"]: float(o["price"]) for o in (market.get("outcomes") or [])
                   if "name" in o and "price" in o}
        if len(outcomes) < 2:
            continue
        out.append({
            "home_team": ev.get("home_team"), "away_team": ev.get("away_team"),
            "commence_time": ev.get("commence_time"),
            "book": book.get("key"), "outcomes": outcomes,
        })
    return out


def fetch_odds_h2h(sport_key: str, api_key: Optional[str], *, session: Optional[requests.Session] = None
                   ) -> Dict[str, Any]:
    """Best-effort the-odds-api h2h fetch for one sport. Returns a status dict — never
    raises on a missing key (that is the expected, documented BLOCKED(key) path)."""
    if not api_key:
        return {"status": "blocked", "reason": "ODDS_API_KEY missing"}
    sess = session or requests.Session()
    r = sess.get(f"{ODDS_API_BASE}/sports/{sport_key}/odds", headers=ODDS_UA, timeout=20,
                params={"apiKey": api_key, "regions": "us,uk,eu", "markets": "h2h",
                        "oddsFormat": "decimal"})
    if r.status_code != 200:
        return {"status": "blocked", "reason": f"http {r.status_code}"}
    events = _parse_odds_h2h_response(r.json())
    # Matching a parsed odds event to a specific Kalshi event_ticker needs a team-name
    # reconciliation table (Kalshi short codes vs the-odds-api full names) this collector
    # does not yet build — deferred honestly rather than guessed (see module docstring).
    return {"status": "fetched_unmatched", "reason": "team matching not implemented",
            "n_events": len(events), "raw_sha256": sha256_hex(canonical_json(events))}


# --------------------------------------------------------------------------- #
# discovery + capture
# --------------------------------------------------------------------------- #
def discover_moneyline_series(client: Kalshi) -> Tuple[List[str], List[Dict[str, str]]]:
    """All Sports-category series in the moneyline (GAME) family, soccer/World Cup first.

    Returns (series_tickers, category_errors). A failure enumerating the Sports category
    itself is a category_error (mirrors capture_orderbooks' series_errors one level up)."""
    try:
        series = client.series_by_category("Sports")
    except Exception as exc:
        return [], [{"category": "Sports", "error": str(exc)}]
    tickers = sorted({s.get("ticker", "") for s in series if _is_moneyline_series(s.get("ticker", ""))},
                     key=_sort_key)
    return tickers, []


def run(limit: Optional[int] = None, min_interval: float = 0.2,
        client: Optional[Kalshi] = None, store: Optional[Path] = None,
        odds_api_key: Optional[str] = None) -> Dict[str, Any]:
    """One read-only capture pass. `client`/`store` are injectable for offline testing;
    in production both default to the live Kalshi client and the real tape/ store."""
    store = Path(store) if store is not None else STORE
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)
    if odds_api_key is None:
        odds_api_key = os.environ.get("ODDS_API_KEY")

    # the wall-clock is read ONCE per pass and frozen into every line (bitemporal receipt instant)
    cap_ts = datetime.now(timezone.utc)
    fetch_ts = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    series_tickers, category_errors = discover_moneyline_series(client)

    lines: List[Dict[str, Any]] = []
    series_errors: List[Dict[str, str]] = list(category_errors)
    non_moneyline_series: List[str] = []
    n_scanned = 0

    for sticker in series_tickers:
        if limit is not None and n_scanned >= limit:
            break
        n_scanned += 1
        try:
            text = client.get_text("/markets", series_ticker=sticker, status="open", limit=1000)
            markets = (json.loads(text) or {}).get("markets") or []
        except Exception as exc:
            series_errors.append({"series": sticker, "error": str(exc)})
            continue
        if not markets:
            continue
        raw_sha256 = sha256_hex(text)

        by_event: Dict[str, List[dict]] = {}
        outcomes_by_ticker: Dict[str, str] = {}
        for m in markets:
            by_event.setdefault(m.get("event_ticker", ""), []).append(m)
            parts, err = parse_sports_ticker(m.get("ticker", ""))
            outcomes_by_ticker[m.get("ticker", "")] = parts["outcome"] if parts and not err else ""

        # Some GAME-suffixed series are structurally single-market props (e.g.
        # KXWCTEAMSINGAME "Will X play Y?", KXWCGOALEVERYGAME), not paired moneylines —
        # every event in them has exactly 1 market, always. A real moneyline series has
        # >=2 markets sharing an event_ticker for at least one event. Skip the whole
        # series rather than emit chronically "incomplete" 1-leg lines that misrepresent
        # a non-moneyline market as a broken moneyline one.
        if not by_event or max(len(ms) for ms in by_event.values()) < 2:
            non_moneyline_series.append(sticker)
            continue

        # NOTE on completeness: unlike capture_orderbooks.py (one HTTP call per market,
        # so a single market fetch can fail independently), every market for a series
        # arrives in ONE /markets response — there is no per-market fetch that can drop
        # silently below the whole-series level (already tracked as series_errors). An
        # "expected leg count" guessed from sibling events in the same series is NOT a
        # real completeness signal: e.g. KXLOLGAME mixes best-of matches that can draw
        # (a TIE leg) with ones that can't, so one event's TIE leg says nothing about
        # another event in the same series (caught live: guessing expected=3 series-wide
        # mislabeled 6 genuinely-complete 2-way matches as incomplete). The only
        # structurally honest completeness check at this granularity is "did we get a
        # real pair" (n_legs >= 2); has_tie_leg is descriptive, not an expectation.
        for event_ticker, ms in sorted(by_event.items()):
            legs = []
            for m in sorted(ms, key=lambda x: x.get("ticker", "")):
                legs.append({
                    "ticker": m.get("ticker"), "outcome": outcomes_by_ticker.get(m.get("ticker", ""), ""),
                    "yes_ask": m.get("yes_ask_dollars"), "yes_bid": m.get("yes_bid_dollars"),
                    "no_ask": m.get("no_ask_dollars"), "no_bid": m.get("no_bid_dollars"),
                    "price_source_tag": tag_or_synthetic("real_ask"),
                })
            asks = [lg["yes_ask"] for lg in legs if lg["yes_ask"] is not None]
            bsum = bracket_sum(asks) if asks else None
            line = {
                "schema_version": SCHEMA_VERSION,
                "capture_id": capture_id, "fetch_ts": fetch_ts, "venue": "kalshi",
                "series_ticker": sticker, "event_ticker": event_ticker,
                "title": ms[0].get("title"), "close_time": ms[0].get("close_time"),
                "legs": legs, "n_legs": len(legs),
                "has_tie_leg": any(lg["outcome"] == "TIE" for lg in legs),
                "completeness_ok": len(legs) >= 2,
                "bracket_sum": bsum, "overround": (overround(asks) if asks else None),
                "raw_sha256": raw_sha256,
                "odds": {"status": "blocked", "reason": "ODDS_API_KEY missing"}
                        if odds_api_key is None else
                        {"status": "fetched_unmatched",
                         "reason": "team matching not implemented"},
            }
            lines.append(line)

    n_complete = sum(1 for ln in lines if ln["completeness_ok"])
    summary = {
        "capture_id": capture_id, "day": day, "fetch_ts": fetch_ts,
        "n_series_scanned": n_scanned, "n_series_total": len(series_tickers),
        "n_series_errors": len(series_errors),
        "n_series_non_moneyline": len(non_moneyline_series), "n_events": len(lines),
        "n_complete": n_complete, "odds_api_key_present": odds_api_key is not None,
    }

    if lines:
        out_dir = store / f"dt={day}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"pass-{capture_id}.jsonl"
        with open(out_path, "a") as f:
            for ln in lines:
                f.write(canonical_json(ln) + "\n")
        summary["path"] = str(out_path)

    print(f"[sports_pairs] {capture_id}: {summary['n_events']} events across "
          f"{n_scanned}/{len(series_tickers)} series scanned "
          f"({len(non_moneyline_series)} excluded non-moneyline), {n_complete} complete, "
          f"odds_key_present={summary['odds_api_key_present']}")
    if series_errors:
        print(f"[sports_pairs] WARN {len(series_errors)} series/category failed enumeration",
              file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Sports moneyline paired-odds capture (read-only)")
    ap.add_argument("--limit", type=int, default=None, help="cap series scanned per pass")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    run(limit=args.limit, min_interval=args.min_interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
