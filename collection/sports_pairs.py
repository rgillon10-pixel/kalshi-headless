"""Sports moneyline BBO capture (READ-ONLY) — serves S7 (CLV vs sharp line) / S11.

One pass = for every open Kalshi sports moneyline event (soccer/World Cup first, per
Q1's Jul-19 deadline, then every other head-to-head "<Team> vs <Team> Winner?" market
Kalshi lists): snapshot each leg's real taker BBO (`yes_ask_dollars` / `no_ask_dollars`
etc — genuinely fillable top-of-book, tagged `real_ask` per core/source_tag.py) and
write one bitemporal JSONL line per event under `tape/sports_pairs/`.

Discovery: Kalshi's `category=Sports` series list has ~2300 entries; a head-to-head
moneyline series always has a ticker ending `GAME` (KXWCGAME, KXNFLGAME, KXMLBGAME, ...).
That is a superset (also catches novelty non-moneyline "GAME" series, e.g. all-star/
celebrity games) so the real filter is per-event: keep only markets whose title ends
in "Winner?" — Kalshi's own moneyline convention, confirmed empirically against a
2-way (MLB/NFL/NBA, no draw) and 3-way (soccer, with a Tie leg) event.

`bracket_sum`/`overround` route through `core.pricing` (the ONLY sanctioned yes_ask
arithmetic site, Hard Rule #3) rather than summing raw asks here.

Sharp-odds leg (the-odds-api, de-vigged to a `synthetic` fair prob) fetches only when
`ODDS_API_KEY` is present; absent it, the record says so honestly rather than silently
omitting the field. Kalshi's leg is captured either way — the two data problems are
independent (Q1).

Run one pass:
    python -m collection.sports_pairs
    python -m collection.sports_pairs --limit-series 5     # smoke test
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
from core.pricing import bracket_sum as _bracket_sum
from validation.v3_market import Kalshi, _load_venue_cfg

STORE = REPO_ROOT / "tape" / "sports_pairs"
SPORTS_CATEGORY = "Sports"
SCHEMA_VERSION = "sports_pairs.v0"

# event_ticker = "<SERIES>-<YYMMMDD><opaque team/time code>" (one dash); the date
# token is fixed-width and well-defined, the trailing code is NOT split further here
# (team-code width varies e.g. "AZLAD" for MLB, "ARGSUI" for soccer — ambiguous to
# split without a team dictionary, and the per-market title/sub_title already names
# the outcome, so nothing downstream needs the split).
_EVENT_RE = re.compile(r"^(?P<series>[A-Z0-9]+)-(?P<datecode>\d{2}[A-Z]{3}\d{2})(?P<rest>[A-Z0-9]*)$")


def parse_event_ticker(event_ticker: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Parse a sports event ticker into {series, date (ISO), code}. (spec, error)."""
    m = _EVENT_RE.match(event_ticker or "")
    if not m:
        return None, "no_regex_match"
    try:
        d = datetime.strptime(m.group("datecode"), "%y%b%d").date()
    except ValueError:
        return None, "bad_date_token"
    return {"series": m.group("series"), "date": d.isoformat(), "code": m.group("rest")}, None


def parse_leg_ticker(ticker: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Split a leg ticker into (event_ticker, outcome_code, error). Legs are always
    `<event_ticker>-<OUTCOME>`, so the last dash-delimited segment is the outcome."""
    if not ticker or ticker.count("-") < 2:
        return None, None, "not_a_leg_ticker"
    event_ticker, outcome = ticker.rsplit("-", 1)
    if not outcome:
        return None, None, "empty_outcome"
    return event_ticker, outcome, None


# --------------------------------------------------------------------------- #
# de-vig math (pure; unit-tested now, wired to a live odds fetch once
# ODDS_API_KEY is available — Q1 note: no key -> Kalshi leg only, honestly flagged)
# --------------------------------------------------------------------------- #
def american_to_prob(odds: float) -> float:
    """Raw (vig-included) implied probability from American odds."""
    odds = float(odds)
    if odds == 0:
        raise ValueError("American odds cannot be 0")
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def devig_multiplicative(raw_probs: List[float]) -> List[float]:
    """Proportional (multiplicative) de-vig: normalize implied probs to sum to 1.

    The simplest de-vig method (vs. Shin/power methods) — adequate for a first cut;
    persisted probs from this are `synthetic` (a de-vig is a model, never a fill,
    per CLAUDE.md trust defaults)."""
    total = sum(raw_probs)
    if total <= 0:
        raise ValueError(f"sum of implied probs must be > 0, got {total!r}")
    return [p / total for p in raw_probs]


# --------------------------------------------------------------------------- #
# discovery — moneyline series, World Cup / soccer first (Q1: Jul-19 deadline)
# --------------------------------------------------------------------------- #
def discover_moneyline_series(client: Any) -> List[Dict[str, Any]]:
    """All Sports-category series whose ticker names a head-to-head 'GAME' market.
    A superset of true moneylines (also catches all-star/novelty games); the
    per-event title filter (`_moneyline_legs`) is the real gate."""
    return [s for s in client.series_by_category(SPORTS_CATEGORY)
            if (s.get("ticker") or "").endswith("GAME")]


def _priority_key(s: Dict[str, Any]) -> Tuple[int, str]:
    ticker = s.get("ticker", "")
    tags = s.get("tags") or []
    rank = 0 if ticker == "KXWCGAME" else (1 if "Soccer" in tags else 2)
    return (rank, ticker)


def _moneyline_legs(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Keep only member markets that are genuine 2/3-way moneyline legs: Kalshi's
    own '<Team> vs <Team> Winner?' title convention on a binary market with a full
    real BBO quoted. Drops spreads/totals/props that share the same series."""
    legs = []
    for m in event.get("markets") or []:
        title = (m.get("title") or "").rstrip()
        if not title.endswith("Winner?") or m.get("market_type") != "binary":
            continue
        try:
            leg = {
                "ticker": m.get("ticker"),
                "sub_title": m.get("yes_sub_title") or title,
                "yes_ask": float(m["yes_ask_dollars"]),
                "yes_bid": float(m["yes_bid_dollars"]),
                "no_ask": float(m["no_ask_dollars"]),
                "no_bid": float(m["no_bid_dollars"]),
                "price_source_tag": "real_ask",
            }
        except (KeyError, TypeError, ValueError):
            continue   # a leg missing/malformed BBO can't be priced -> drop, don't fabricate
        legs.append(leg)
    return legs


# --------------------------------------------------------------------------- #
# capture — one JSONL line per qualifying event, one summary line per pass
# --------------------------------------------------------------------------- #
def run(client: Optional[Any] = None, store: Optional[Path] = None,
        limit_series: Optional[int] = None) -> Dict[str, Any]:
    """One read-only capture pass. `client`/`store` are injectable for offline testing;
    in production both default to the live Kalshi client and the real tape store."""
    store = Path(store) if store is not None else STORE
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=0.2)

    cap_ts = datetime.now(timezone.utc)
    fetch_ts = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    odds_key_present = bool(os.environ.get("ODDS_API_KEY"))
    odds_status = "unfetched_this_run" if odds_key_present else "BLOCKED(key)"

    series_list = sorted(discover_moneyline_series(client), key=_priority_key)
    if limit_series:
        series_list = series_list[:limit_series]

    events_out: List[Dict[str, Any]] = []
    series_failed: List[Dict[str, str]] = []

    for s in series_list:
        sticker = s.get("ticker", "")
        try:
            raw_events = client.paginate("/events", "events", series_ticker=sticker,
                                         status="open", with_nested_markets="true",
                                         limit=200)
        except Exception as exc:   # a failed series fetch -> recorded, not hidden
            series_failed.append({"series": sticker, "error": str(exc)})
            continue

        for ev in raw_events:
            legs = _moneyline_legs(ev)
            if len(legs) < 2:
                continue   # not a qualifying moneyline group (or degenerate)
            asks = [leg["yes_ask"] for leg in legs]
            bsum = _bracket_sum(asks)
            event_ticker = ev.get("event_ticker", "")
            meta, parse_err = parse_event_ticker(event_ticker)
            events_out.append({
                "schema_version": SCHEMA_VERSION,
                "fetch_ts": fetch_ts,
                "capture_id": capture_id,
                "event_ticker": event_ticker,
                "series_ticker": sticker,
                "sport_tags": s.get("tags") or [],
                "event_title": ev.get("title"),
                "game_date": meta["date"] if meta else None,
                "ticker_parse_error": parse_err,
                "legs": sorted(legs, key=lambda l: l["ticker"]),
                "n_legs": len(legs),
                "bracket_sum": round(bsum, 6),
                "overround": round(bsum - 1.0, 6),
                "raw_sha256": sha256_hex(canonical_json(ev)),
                "odds": {"status": odds_status},
            })

    out_path = None
    if events_out:
        out_dir = store / f"dt={day}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"pass-{capture_id}.jsonl"
        with open(out_path, "w") as f:
            for rec in sorted(events_out, key=lambda r: r["event_ticker"]):
                f.write(canonical_json(rec) + "\n")

    summary = {
        "capture_id": capture_id, "day": day, "fetch_ts": fetch_ts,
        "n_series_attempted": len(series_list),
        "n_series_failed": len(series_failed),
        "series_failed": series_failed,
        "n_events_captured": len(events_out),
        "completeness_ok": len(series_failed) == 0,
        "odds_key_present": odds_key_present,
        "odds_status": odds_status,
    }
    store.mkdir(parents=True, exist_ok=True)
    with open(store / "_pass_manifest.jsonl", "a") as mf:
        mf.write(canonical_json(summary) + "\n")

    n_ok = summary["n_series_attempted"] - summary["n_series_failed"]
    print(f"[sports_pairs] {capture_id}: {summary['n_events_captured']} events across "
          f"{n_ok}/{summary['n_series_attempted']} series (odds: {odds_status}) "
          f"-> {out_path or '(none written)'}")
    if series_failed:
        print(f"[sports_pairs] WARN {len(series_failed)} series failed enumeration "
              f"(completeness_ok=False)", file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Sports moneyline BBO capture (read-only)")
    ap.add_argument("--limit-series", type=int, default=None, help="cap series scanned per pass")
    args = ap.parse_args(argv)
    run(limit_series=args.limit_series)
    return 0


if __name__ == "__main__":
    sys.exit(main())
