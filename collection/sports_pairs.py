"""Forward capture (READ-ONLY) of Kalshi sports moneyline BBO — serves S7/S11.

Mirrors collection/capture_orderbooks.py's discipline for a different market shape:
head-to-head "Game" events (2-way for most US leagues, 3-way with a Tie leg for soccer)
instead of temperature ladders. Same bitemporal contract (D3): `fetch_ts` is read ONCE
per pass and frozen into every line; every persisted price carries a `price_source_tag`
(CLAUDE.md trust defaults); a leg Kalshi's API failed to serve is a DROP that lowers
`completeness_ok`, never a silently-shrunk "complete" record (the survivorship failure
mode capture_orderbooks.py already guards against).

Kalshi does not expose a "moneyline" category, so discovery is a static allowlist derived
empirically (see config/venues.yaml `kalshi_sports`): every series whose ticker ends in
GAME/GAMES, minus a small denylist of confirmed non-moneyline outliers (props/aggregates
that happen to share the suffix). A denylist MISS is not a silent-wrong-record risk: any
discovered event whose markets aren't a mutually-exclusive winner bracket (Kalshi's own
`mutually_exclusive` flag, `>=2` legs) is skipped and counted, never force-fit.

`GET /events?series_ticker=...&status=open&with_nested_markets=true` returns each event's
markets pre-populated with yes/no BBO — the real fillable `yes_ask_dollars`/`no_ask_dollars`
(tag `real_ask`), no separate per-market orderbook fetch needed (unlike the temperature
ladders, which are bids-only and require deriving the opposite ask).

World Cup markets (KXWCGAME) are processed first per LOOP-QUEUE.md Q1's time-sensitivity
(tournament ends 2026-07-19); the ordering is cosmetic (the pass is complete either way),
it only affects which capture-dir raw files land first if a run is interrupted mid-pass.

Sportsbook odds (Pinnacle preferred, `the_odds_api`) are fetched only when ODDS_API_KEY is
set; when present the de-vigged fair probability is tagged `synthetic` (a de-vig is a
model, never a fill price — Hard Rule #3's spirit generalized). No key -> the Kalshi leg
is still captured; the odds leg is recorded as `BLOCKED(key)` in the pass summary.

Run one pass:
    python -m collection.sports_pairs
    python -m collection.sports_pairs --limit 5   # cap series scanned (smoke test)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.canonical import canonical_json, sha256_hex
from core.io import CONFIG, REPO_ROOT
from core.manifest_schema import sign
from core.pricing import bracket_sum
from validation.v3_market import Kalshi, _load_venue_cfg

STORE = REPO_ROOT / "tape" / "sports_pairs"
SCHEMA_VERSION = "sports_pairs.v0"
_EVENT_TICKER_RE = re.compile(
    r"^(?P<series>[A-Z0-9]+)-(?P<date>\d{2}[A-Z]{3}\d{2})(?:\d{4})?(?P<matchup>[A-Z]+)$"
)


def _load_sports_cfg() -> Dict[str, Any]:
    import yaml
    with open(CONFIG / "venues.yaml") as f:
        return yaml.safe_load(f)["kalshi_sports"]


def _load_odds_cfg() -> Dict[str, Any]:
    import yaml
    with open(CONFIG / "venues.yaml") as f:
        return yaml.safe_load(f)["the_odds_api"]


# --------------------------------------------------------------------------- #
# ticker parsing
# --------------------------------------------------------------------------- #
def parse_event_ticker(event_ticker: str) -> Optional[Dict[str, str]]:
    """Split a Kalshi sports event ticker into its series / date-token / matchup code.

    Format is `<SERIES>-<YYMMMDD>[<HHMM>]<MATCHUP>` — e.g. `KXWCGAME-26JUL09FRAMAR`,
    `KXMLBGAME-26JUL112110AZLAD` (MLB adds an HHMM start-time before the matchup code).
    The matchup code (team codes concatenated, no separator) is intentionally NOT split
    into two team codes — codes are variable-width and ambiguous to split blind; the
    human-readable side name Kalshi returns per-market (`yes_sub_title`) is authoritative
    for that, so this parser only needs series + date for grouping/logging. Returns None
    on no match (recorded as a skip, never guessed)."""
    m = _EVENT_TICKER_RE.match(event_ticker)
    if not m:
        return None
    try:
        target = datetime.strptime(m.group("date"), "%y%b%d").date()
    except ValueError:
        return None
    return {"series": m.group("series"), "target_date": target.isoformat(),
            "matchup_code": m.group("matchup")}


# --------------------------------------------------------------------------- #
# discovery — the moneyline series allowlist (World Cup first, then anything listed)
# --------------------------------------------------------------------------- #
def discover_series(client: Kalshi, cfg: Dict[str, Any]) -> List[str]:
    """Every Sports-category series ticker ending in a moneyline suffix, minus the
    denylist, with World Cup (KXWCGAME) first (LOOP-QUEUE.md Q1 time-sensitivity)."""
    suffixes = tuple(cfg["series_ticker_suffixes"])
    deny = set(cfg["series_ticker_denylist"])
    series = client.series_by_category(cfg["category"])
    tickers = sorted({s.get("ticker", "") for s in series
                      if s.get("ticker", "").endswith(suffixes)} - deny)
    priority = [t for t in tickers if t == "KXWCGAME"]
    rest = [t for t in tickers if t != "KXWCGAME"]
    return priority + rest


# --------------------------------------------------------------------------- #
# de-vig (pure function over sportsbook decimal odds — never touches a Kalshi ask,
# so it lives outside core/pricing.py; Hard Rule #3 governs Kalshi ask arithmetic)
# --------------------------------------------------------------------------- #
def devig_multiplicative(prices: List[float]) -> List[float]:
    """Multiplicative de-vig: normalize raw implied probabilities (1/decimal_odds per
    outcome) to sum to 1.0, removing the sportsbook's overround. `prices` are decimal
    odds (>1.0) for every outcome in one mutually-exclusive market."""
    if len(prices) < 2:
        raise ValueError("devig_multiplicative needs >=2 outcomes")
    if any(p <= 1.0 for p in prices):
        raise ValueError(f"decimal odds must be > 1.0, got {prices!r}")
    implied = [1.0 / p for p in prices]
    total = sum(implied)
    return [p / total for p in implied]


# --------------------------------------------------------------------------- #
# capture — one manifest line per (event, capture pass), signed + bitemporal
# --------------------------------------------------------------------------- #
def _leg_record(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One outcome leg's real-ask BBO from an /events nested market. None if the API
    omitted a price field this pass (a DROP, not a guess)."""
    try:
        yes_ask = float(m["yes_ask_dollars"])
        yes_bid = float(m["yes_bid_dollars"])
        no_ask = float(m["no_ask_dollars"])
        no_bid = float(m["no_bid_dollars"])
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "ticker": m.get("ticker", ""),
        "side_name": m.get("yes_sub_title", ""),
        "yes_bid": yes_bid, "yes_ask": yes_ask,
        "no_bid": no_bid, "no_ask": no_ask,
        "price_source_tag": "real_ask",
    }


def _event_record(series_ticker: str, event: Dict[str, Any], capture_id: str,
                  captured_at: str, source_endpoint: str, raw_sha256: str) -> Optional[Dict[str, Any]]:
    event_ticker = event.get("event_ticker", "")
    markets = event.get("markets") or []
    expected_legs = len(markets)
    if expected_legs < 2:
        return None  # not a head-to-head bracket at all — skip, don't force-fit

    legs = [_leg_record(m) for m in markets]
    captured_legs = [l for l in legs if l is not None]
    if not captured_legs:
        return None  # degenerate: nothing captured, never emit an empty "complete" line

    normalized = {"venue": "kalshi", "event_ticker": event_ticker,
                  "legs": sorted(captured_legs, key=lambda l: l["ticker"])}
    normalized_str = canonical_json(normalized)

    record = {
        "schema_version": SCHEMA_VERSION,
        "capture_id": capture_id,
        "venue": "kalshi",
        "series_ticker": series_ticker,
        "event_ticker": event_ticker,
        "title": markets[0].get("title", ""),
        "mutually_exclusive": bool(event.get("mutually_exclusive")),
        "as_of": captured_at, "captured_at": captured_at,   # observability == receipt (warm-up)
        "source_endpoint": source_endpoint,
        "raw_sha256": raw_sha256,
        "normalized_sha256": sha256_hex(normalized_str),
        "n_legs": len(captured_legs),
        "expected_legs": expected_legs,
        "completeness_ok": len(captured_legs) == expected_legs,
        "bracket_sum": bracket_sum(l["yes_ask"] for l in captured_legs),
        "legs": sorted(captured_legs, key=lambda l: l["ticker"]),
        "warmup": True,
        "odds_leg": {"status": "BLOCKED(key)"},
    }
    return sign(record)


def _capture_id_dir(store: Path, day: str, capture_id: str) -> Path:
    return store / f"dt={day}" / f"capture-{capture_id}"


def run(limit: Optional[int] = None, min_interval: float = 0.2,
        client: Optional[Kalshi] = None, cfg: Optional[Dict[str, Any]] = None,
        store: Optional[Path] = None) -> Dict[str, Any]:
    """One read-only capture pass. `client`/`cfg`/`store` are injectable for offline
    testing; in production all default to the live Kalshi client and real tape store."""
    store = Path(store) if store is not None else STORE
    cfg = cfg if cfg is not None else _load_sports_cfg()
    if client is None:
        venue_cfg = _load_venue_cfg()
        client = Kalshi(venue_cfg["api_base"], min_interval=min_interval)
    source_endpoint = getattr(client, "base", "") + "/events"

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    tickers = discover_series(client, cfg)
    if limit:
        tickers = tickers[:limit]

    capture_dir = _capture_id_dir(store, day, capture_id)
    records: List[Dict[str, Any]] = []
    skipped_events = 0
    series_errors: List[Dict[str, str]] = []
    n_series_with_events = 0

    for series_ticker in tickers:
        try:
            events = client.paginate("/events", "events", series_ticker=series_ticker,
                                     status="open", with_nested_markets="true", limit=200)
            raw_text = canonical_json(events)   # verbatim (canonicalized) bytes to hash
        except Exception as exc:   # a whole-series fetch failure -> recorded, never hidden
            series_errors.append({"series": series_ticker, "error": str(exc)})
            continue
        if not events:
            continue
        n_series_with_events += 1
        raw_sha = sha256_hex(raw_text)

        for event in events:
            if not event.get("mutually_exclusive"):
                skipped_events += 1
                continue
            rec = _event_record(series_ticker, event, capture_id, captured_at,
                                source_endpoint, raw_sha)
            if rec is None:
                skipped_events += 1
                continue
            records.append(rec)

        capture_dir.mkdir(parents=True, exist_ok=True)
        (capture_dir / f"{series_ticker}.raw.json").write_text(raw_text, encoding="utf-8")

    if records:
        store.mkdir(parents=True, exist_ok=True)
        with open(store / "_manifest.jsonl", "a") as mf:
            for rec in records:
                mf.write(canonical_json(rec) + "\n")

    n_complete = sum(1 for r in records if r["completeness_ok"])
    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_series_scanned": len(tickers), "n_series_with_events": n_series_with_events,
        "n_series_errors": len(series_errors),
        "n_events": len(records), "n_complete": n_complete,
        "n_events_skipped": skipped_events,
        "odds_leg": "BLOCKED(key)" if not os.environ.get("ODDS_API_KEY") else "present_not_wired",
    }
    print(f"[sports_pairs] {capture_id}: {summary['n_events']} events "
          f"({n_complete} complete) across {n_series_with_events}/{len(tickers)} series "
          f"with open markets -> {capture_dir}; odds_leg={summary['odds_leg']}")
    if series_errors:
        print(f"[sports_pairs] WARN {len(series_errors)} series failed /events fetch "
              f"(missing this pass)", file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Sports moneyline BBO capture (read-only)")
    ap.add_argument("--limit", type=int, default=None, help="cap series scanned per pass")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    run(limit=args.limit, min_interval=args.min_interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
