"""Sports paired-odds capture (READ-ONLY) — Q1, serves S7 (sports CLV) / S11 (maker quoting).

Mirrors collection/capture_orderbooks.py's discipline for a different shape of market:
a Kalshi *event* (e.g. one soccer game) is a mutually-exclusive set of binary outcome
markets (home / away / tie), not a temperature bracket ladder — but the same bitemporal +
completeness + content-hash contract applies (core/sports_schema.py is the sibling of
core/manifest_schema.py for this shape).

One pass:
  1. Discover candidate series: every Sports-category series whose ticker ends in "GAME"
     (the empirically-observed suffix for per-event moneyline/winner markets — see the
     KXWCGAME/KXMLBGAME/KXNBAGAME family). World Cup / soccer series sort first (Q1:
     TIME-SENSITIVE, World Cup ends Jul 19) — this is a documented heuristic, not a
     Kalshi-provided classification, so it can miss a genuinely non-"GAME"-suffixed
     moneyline series; a gap here is a coverage limitation, not a silent corruption (every
     series actually scanned is scanned completely or recorded as a series_error).
  2. Group each series' OPEN markets by the API's own `event_ticker` (authoritative — not
     guessed); cross-check against a ticker-parse for defense-in-depth (a mismatch is
     recorded, never silently dropped).
  3. An event with >=2 outcome markets = a capturable bracket: snapshot each outcome's live
     yes/no BBO (tag `real_ask` — Hard Rule #3: `bracket_sum`/`overround` computed via
     core.pricing, the sole sanctioned site for yes_ask and no_ask arithmetic).
  4. If ODDS_API_KEY is present, attempt a matched sportsbook de-vig leg (tag `synthetic` —
     a de-vig is a model, not a fill) via core.odds. No key -> odds_leg_status=
     "blocked_no_key", Kalshi leg captured anyway (Q1's documented fallback).

Run one pass:
    python -m collection.sports_pairs                 # all discovered GAME series
    python -m collection.sports_pairs --limit 200      # cap markets scanned (testing)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from core.odds import american_odds_to_fair_probs
from core.pricing import bracket_sum, overround
from core.sports_schema import GamePairManifest, validate
from validation.v3_market import Kalshi, _load_venue_cfg

STORE = REPO_ROOT / "tape" / "sports_pairs"
SPORTS_CATEGORY = "Sports"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Kalshi sport-series -> the-odds-api sport key. Deliberately small and explicit: an
# unmapped series' odds leg reports "no_match" rather than guessing a sport_key.
ODDS_API_SPORT_KEYS = {
    "KXWCGAME": "soccer_fifa_world_cup",
}

# A market ticker is "<event_ticker>-<OUTCOME>"; event_ticker itself may contain hyphens
# (SERIES-DATETEAMS), so parsing must peel exactly one trailing "-<OUTCOME>" segment.
_MARKET_TICKER_RE = re.compile(r"^(?P<event>[A-Z0-9]+-[A-Z0-9.]+)-(?P<outcome>[A-Z0-9]+)$")


def _slug(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


def _match_token(text: str) -> str:
    """Slug for cross-source outcome matching, normalizing common synonyms Kalshi and
    the-odds-api disagree on (Kalshi labels a 3-way soccer draw "Tie"; the-odds-api's
    outcome name is "Draw")."""
    return _slug(text).replace("tie", "draw")


# --------------------------------------------------------------------------- #
# ticker parsing (defense-in-depth cross-check against the API's own event_ticker)
# --------------------------------------------------------------------------- #
def parse_market_ticker(ticker: str) -> Tuple[str, str]:
    """Split an outcome-market ticker into (event_ticker, outcome_code).

    Raises ValueError if the ticker doesn't match the observed grammar (e.g. a
    "GAME"-suffixed series whose markets aren't simple win/lose/tie outcomes) —
    callers must catch this and fall back to the API's own event_ticker rather
    than crash the whole pass on one unfamiliar market shape.
    """
    m = _MARKET_TICKER_RE.match(ticker.upper())
    if not m:
        raise ValueError(f"cannot parse market ticker: {ticker!r}")
    return m.group("event"), m.group("outcome")


def reconcile_event_ticker(ticker: str, api_event_ticker: str) -> Optional[str]:
    """Cross-check a ticker-derived event against the API's own `event_ticker`.

    Returns a mismatch description if they disagree, else None (either they agree,
    or the ticker shape isn't one we parse — an unparsed ticker is NOT treated as a
    mismatch, since parse_market_ticker's grammar is intentionally narrow).
    """
    try:
        derived, _outcome = parse_market_ticker(ticker)
    except ValueError:
        return None
    if derived != api_event_ticker:
        return f"{ticker}: derived event {derived!r} != api event_ticker {api_event_ticker!r}"
    return None


# --------------------------------------------------------------------------- #
# discovery — candidate series, then events grouped from their OPEN markets
# --------------------------------------------------------------------------- #
def discover_candidate_series(client) -> List[str]:
    """Every Sports-category series ticker ending in 'GAME', World Cup / soccer first."""
    series = client.series_by_category(SPORTS_CATEGORY)
    tickers = sorted({(s.get("ticker") or "") for s in series if (s.get("ticker") or "").endswith("GAME")})

    def _priority(t: str) -> Tuple[int, str]:
        return (0 if "WC" in t else 1, t)

    return sorted(tickers, key=_priority)


def discover_events(client, series_tickers: List[str], limit: Optional[int] = None
                    ) -> Tuple[Dict[str, Dict], List[Dict[str, str]], List[str]]:
    """Enumerate open markets for each candidate series, grouped by event_ticker.

    Returns (events, series_errors, ticker_mismatches). events[event_ticker] =
    {"series": ..., "markets": [raw market dicts]}. A whole-series enumeration
    failure is recorded (series_errors), never silently hidden — same discipline
    as collection/capture_orderbooks.discover_groups."""
    events: Dict[str, Dict] = {}
    series_errors: List[Dict[str, str]] = []
    ticker_mismatches: List[str] = []
    seen = 0
    for sticker in series_tickers:
        try:
            markets = client.open_markets(sticker)
        except Exception as exc:
            series_errors.append({"series": sticker, "error": str(exc)})
            continue
        for m in markets:
            ticker = m.get("ticker", "")
            event_ticker = m.get("event_ticker") or ""
            if not event_ticker:
                continue
            mismatch = reconcile_event_ticker(ticker, event_ticker)
            if mismatch:
                ticker_mismatches.append(mismatch)
            ev = events.setdefault(event_ticker, {"series": sticker, "markets": []})
            ev["markets"].append(m)
            seen += 1
            if limit and seen >= limit:
                return events, series_errors, ticker_mismatches
    return events, series_errors, ticker_mismatches


# --------------------------------------------------------------------------- #
# odds leg — matched sportsbook de-vig (synthetic; Kalshi leg is captured regardless)
# --------------------------------------------------------------------------- #
class OddsApiClient:
    """Thin throttled client for the-odds-api v4 (public sportsbook odds aggregator)."""

    def __init__(self, api_key: str, base: str = ODDS_API_BASE, min_interval: float = 0.25):
        self.api_key = api_key
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self._min_interval = min_interval
        self._last = 0.0

    def sport_odds(self, sport_key: str, regions: str = "us,eu", markets: str = "h2h",
                   odds_format: str = "american") -> List[dict]:
        gap = time.time() - self._last
        if gap < self._min_interval:
            time.sleep(self._min_interval - gap)
        r = self.s.get(f"{self.base}/sports/{sport_key}/odds",
                       params={"apiKey": self.api_key, "regions": regions,
                               "markets": markets, "oddsFormat": odds_format},
                       timeout=30)
        self._last = time.time()
        r.raise_for_status()
        return r.json()


def _team_names_from_title(title: str) -> Optional[Tuple[str, str]]:
    m = re.match(r"^(.+?)\s+vs\.?\s+(.+?)(?:\s+Winner\??)?$", title.strip(), re.I)
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def match_event_odds(odds_events: List[dict], team_a: str, team_b: str) -> Optional[dict]:
    """Find the odds-api event matching two team names (case-insensitive substring
    match on home_team/away_team). Returns the matched event dict, or None."""
    a, b = _slug(team_a), _slug(team_b)
    for ev in odds_events:
        home, away = _slug(ev.get("home_team", "")), _slug(ev.get("away_team", ""))
        names = {home, away}
        if (a in names or any(a in n or n in a for n in names)) and \
           (b in names or any(b in n or n in b for n in names)):
            return ev
    return None


def _preferred_bookmaker(matched: dict) -> Optional[dict]:
    books = matched.get("bookmakers") or []
    for b in books:              # Pinnacle preferred (Q1) — sharpest book, thinnest vig
        if (b.get("key") or "").lower() == "pinnacle":
            return b
    return books[0] if books else None


def fetch_odds_leg(odds_client: Optional[OddsApiClient], sport_series: str,
                   event_title: str, outcome_labels: Dict[str, str]
                   ) -> Tuple[Dict[str, float], str]:
    """Attempt the matched sportsbook de-vig leg for one event.

    Returns ({outcome_market_ticker: fair_probability}, status). Never raises: any
    failure degrades to an honest status code rather than poisoning the Kalshi leg,
    which is captured unconditionally by the caller."""
    if odds_client is None:
        return {}, "blocked_no_key"
    sport_key = ODDS_API_SPORT_KEYS.get(sport_series)
    if not sport_key:
        return {}, "no_match"
    teams = _team_names_from_title(event_title)
    if not teams:
        return {}, "no_match"
    try:
        odds_events = odds_client.sport_odds(sport_key)
    except Exception:
        return {}, "fetch_error"
    matched = match_event_odds(odds_events, *teams)
    if matched is None:
        return {}, "no_match"
    book = _preferred_bookmaker(matched)
    if not book:
        return {}, "no_match"
    h2h = next((m for m in (book.get("markets") or []) if m.get("key") == "h2h"), None)
    if not h2h or not h2h.get("outcomes"):
        return {}, "no_match"
    names = [o["name"] for o in h2h["outcomes"]]
    prices = [o["price"] for o in h2h["outcomes"]]
    try:
        fair = american_odds_to_fair_probs(prices)
    except (ValueError, KeyError):
        return {}, "fetch_error"
    by_name = dict(zip(names, fair))
    out: Dict[str, float] = {}
    for market_ticker, label in outcome_labels.items():
        label_tok = _match_token(label)
        for name, prob in by_name.items():
            name_tok = _match_token(name)
            if name_tok == label_tok or name_tok in label_tok or label_tok in name_tok:
                out[market_ticker] = prob
                break
    return (out, "ok") if out else ({}, "no_match")


# --------------------------------------------------------------------------- #
# capture — one signed manifest line per event
# --------------------------------------------------------------------------- #
def _group_stem(event_ticker: str) -> str:
    return _slug(event_ticker)


def run(limit: Optional[int] = None, min_interval: float = 0.2,
        client=None, store: Optional[Path] = None,
        odds_api_key: Optional[str] = None, odds_client=None) -> Dict:
    """One read-only capture pass. `client`/`store`/`odds_client` are injectable for
    offline testing; production defaults to the live Kalshi client, the real tape
    store, and ODDS_API_KEY from the environment (never printed)."""
    store = Path(store) if store is not None else STORE
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)
    source_endpoint = getattr(client, "base", "") + "/markets?series_ticker={series}&status=open"

    odds_api_key = odds_api_key if odds_api_key is not None else os.environ.get("ODDS_API_KEY")
    if odds_client is None and odds_api_key:
        odds_client = OddsApiClient(odds_api_key)

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    series_list = discover_candidate_series(client)
    events, series_errors, ticker_mismatches = discover_events(client, series_list, limit=limit)
    capture_dir = store / f"dt={day}" / f"capture-{capture_id}"

    manifests: List[Dict] = []
    degenerate: List[Dict] = []
    invalid: List[Dict] = []
    odds_status_counts: Dict[str, int] = {}

    for event_ticker, ev in sorted(events.items()):
        markets = sorted(ev["markets"], key=lambda m: m.get("ticker", ""))
        if len(markets) < 2:
            degenerate.append({"event_ticker": event_ticker, "n_outcomes": len(markets)})
            continue

        asks: List[float] = []
        outcome_tickers: List[str] = []
        outcome_labels: Dict[str, str] = {}
        raw_by_ticker: Dict[str, Any] = {}
        for m in markets:
            t = m.get("ticker", "")
            outcome_tickers.append(t)
            raw_by_ticker[t] = m
            label = m.get("yes_sub_title") or m.get("title", "")
            outcome_labels[t] = label
            ask_raw = m.get("yes_ask_dollars")
            if ask_raw is not None:
                asks.append(float(ask_raw))

        b_sum = bracket_sum(asks) if asks else 0.0
        b_overround = overround(asks) if asks else 0.0
        title = markets[0].get("title", "") or event_ticker
        event_time = markets[0].get("close_time") or captured_at

        odds_fair, odds_status = fetch_odds_leg(odds_client, ev["series"], title, outcome_labels)
        odds_status_counts[odds_status] = odds_status_counts.get(odds_status, 0) + 1

        raw_str = canonical_json(raw_by_ticker)
        manifest = GamePairManifest(
            capture_id=capture_id, venue="kalshi", sport_series=ev["series"],
            event_ticker=event_ticker, event_title=title,
            event_time=event_time, as_of=captured_at, captured_at=captured_at,
            source_endpoint=source_endpoint,
            raw_sha256=sha256_hex(raw_str),
            n_outcomes=len(outcome_tickers), expected_outcomes=len(outcome_tickers),
            bracket_sum=round(b_sum, 6), overround=round(b_overround, 6),
            price_source_tag="real_ask",
            odds_leg_status=odds_status,
            outcomes=outcome_tickers,
            completeness_ok=True,
        ).signed()

        errs = validate(manifest)
        if errs:
            print(f"[sports_pairs] WARN {event_ticker}: manifest invalid, not written: "
                  f"{errs}", file=sys.stderr)
            invalid.append({"event_ticker": event_ticker, "errors": errs})
            continue

        capture_dir.mkdir(parents=True, exist_ok=True)
        stem = _group_stem(event_ticker)
        (capture_dir / f"{stem}.raw.json").write_text(raw_str, encoding="utf-8")
        if odds_fair:
            (capture_dir / f"{stem}.odds_devig.json").write_text(
                canonical_json({"event_ticker": event_ticker, "price_source_tag": "synthetic",
                                "fair_probability": odds_fair}), encoding="utf-8")
        store.mkdir(parents=True, exist_ok=True)
        with open(store / "_manifest.jsonl", "a") as mf:
            mf.write(canonical_json(manifest) + "\n")
        manifests.append(manifest)

    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_series_scanned": len(series_list), "n_events": len(manifests),
        "n_degenerate": len(degenerate), "n_invalid": len(invalid),
        "n_series_errors": len(series_errors), "n_ticker_mismatches": len(ticker_mismatches),
        "odds_leg_status_counts": odds_status_counts,
        "total_outcomes": sum(m["n_outcomes"] for m in manifests),
        "mean_bracket_sum": (round(sum(m["bracket_sum"] for m in manifests) / len(manifests), 6)
                             if manifests else None),
    }
    print(f"[sports_pairs] {capture_id}: {summary['n_events']} events, "
          f"{summary['total_outcomes']} outcome markets, odds_leg={odds_status_counts} "
          f"-> {capture_dir}")
    if series_errors:
        print(f"[sports_pairs] WARN {len(series_errors)} series failed enumeration",
              file=sys.stderr)
    if ticker_mismatches:
        print(f"[sports_pairs] WARN {len(ticker_mismatches)} ticker/event_ticker mismatches",
              file=sys.stderr)
    return summary


def verify_against_dir(manifest: Dict, capture_dir: Path) -> List[str]:
    """Recompute the manifest's raw_sha256 from the ON-DISK provenance file and confirm
    it matches — binds the manifest to the actual written bytes (provenance, not just
    structural validity), same discipline as capture_orderbooks.verify_against_dir."""
    capture_dir = Path(capture_dir)
    errs: List[str] = []
    stem = _group_stem(manifest["event_ticker"])
    raw_file = capture_dir / f"{stem}.raw.json"
    if not raw_file.exists():
        errs.append(f"raw provenance missing: {stem}.raw.json")
    elif sha256_hex(raw_file.read_bytes()) != manifest.get("raw_sha256"):
        errs.append("raw_sha256 does not match on-disk raw bytes")
    return errs


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Sports paired-odds capture (read-only)")
    ap.add_argument("--limit", type=int, default=None, help="cap markets scanned per pass")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    run(limit=args.limit, min_interval=args.min_interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
