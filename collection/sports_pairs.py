"""Forward Kalshi sports moneyline capture (READ-ONLY) — bitemporal, real-ask BBO.

Serves S7 (Kalshi NFL/NBA moneyline vs Pinnacle de-vig CLV harvest) and S11 (sharp-
anchored maker quoting). Mirrors `collection/capture_orderbooks.py`'s discipline:
bitemporal `fetch_ts` (wall clock read once per pass, frozen into every line),
raw-bytes sha256 provenance, and honest expected-vs-captured completeness — a fetch
failure lowers completeness, it never fakes a full pass.

Discovery is two-stage and rate-limit-friendly: Kalshi's own `/series?category=Sports`
listing does not carry a moneyline flag, so we (1) cheaply filter to `ticker.endswith
("GAME")` — true of every sport's game-winner family observed (KXWCGAME, KXNFLGAME,
KXMLBGAME, ...) but also a handful of non-moneyline props (KXWCTEAMSINGAME,
KXWCGOALEVERYGAME) — then (2) confirm each candidate with one `/series/{ticker}`
detail call and keep only `product_metadata.scope == "Game"`, the field Kalshi itself
uses to mark a game-winner market (empirically confirmed against known moneyline vs.
known prop series, 2026-07-09 live API).

One capture pass = for every confirmed moneyline series' open markets, grouped by
`event_ticker` (one mutually-exclusive bracket per game: 2 outcomes for most sports, 3
for soccer's win/draw/loss): snapshot yes/no BBO (tag `real_ask`) straight off the
market listing (Kalshi's own best-bid/best-ask — no extra per-market orderbook fetch
needed) → one JSONL line per event under `tape/sports_pairs/`. World Cup (KXWCGAME)
sorts first per the queue's World-Cup-first priority (World Cup ends Jul 19, 2026).

The paired-odds leg (Pinnacle-preferred de-vig fair prob via the-odds-api) is gated on
`ODDS_API_KEY`: absent -> the Kalshi leg is still captured, the odds leg is recorded as
`odds_leg: "BLOCKED(key)"` in the pass summary (never silently skipped). The
matching/pairing implementation is intentionally NOT built yet — this repo builds from
live API shapes, never assumed ones (CLAUDE.md), and there is no key in this
environment to verify the-odds-api's actual response shape against. Build it
empirically once a key exists; see `core/oddsmath.py` for the (already-tested)
de-vig math it will consume.

Run one pass:
    python -m collection.sports_pairs
    python -m collection.sports_pairs --limit 5     # cap confirmed series (fast smoke test)
Then schedule it hourly (LOOP-QUEUE Q3) to accumulate CLV history ahead of S7.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from core.pricing import bracket_sum as _bracket_sum, overround as _overround
from validation.v3_market import Kalshi, _load_venue_cfg

SPORTS_CATEGORY = "Sports"
STORE = REPO_ROOT / "tape" / "sports_pairs"
WORLD_CUP_SERIES = "KXWCGAME"


# --------------------------------------------------------------------------- #
# ticker parsing
# --------------------------------------------------------------------------- #
def parse_moneyline_ticker(ticker: str) -> Tuple[str, str]:
    """Split a moneyline market ticker into (event_ticker, outcome_code).

    Grammar (empirically observed across every sport sampled): `<EVENT_TICKER>-
    <OUTCOME>`, e.g. `KXWCGAME-26JUL09FRAMAR-FRA` -> ("KXWCGAME-26JUL09FRAMAR", "FRA").
    The event/date/team token in the middle varies by sport (MLB embeds a start time;
    soccer does not) so we don't try to decompose it further — only the always-present
    event/outcome split, which the API's own `event_ticker` field lets us cross-check
    (see `_group_by_event`) rather than trust blindly.
    """
    if "-" not in ticker:
        raise ValueError(f"not a moneyline ticker (no '-'): {ticker!r}")
    event_ticker, _, outcome = ticker.rpartition("-")
    if not event_ticker or not outcome:
        raise ValueError(f"not a moneyline ticker (empty segment): {ticker!r}")
    return event_ticker, outcome


# --------------------------------------------------------------------------- #
# discovery — confirmed moneyline ("Game") series, World Cup first
# --------------------------------------------------------------------------- #
def discover_moneyline_series(client: Kalshi, limit: Optional[int] = None
                              ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Enumerate Kalshi 'Game' (moneyline/game-winner) series.

    Returns (confirmed, detail_errors). `confirmed` is sorted with KXWCGAME (World Cup)
    first, then alphabetically. `detail_errors` records series whose detail call failed
    (a completeness gap, surfaced rather than silently dropped).
    """
    all_series = client.series_by_category(SPORTS_CATEGORY)
    candidates = [s for s in all_series if (s.get("ticker") or "").endswith("GAME")]

    confirmed: List[Dict[str, str]] = []
    detail_errors: List[Dict[str, str]] = []
    for s in candidates:
        ticker = s["ticker"]
        try:
            detail = client.series_detail(ticker)
        except Exception as exc:
            detail_errors.append({"series": ticker, "error": str(exc)})
            continue
        if (detail.get("product_metadata") or {}).get("scope") == "Game":
            confirmed.append({"ticker": ticker, "title": s.get("title", ""),
                              "sport": ",".join(s.get("tags") or [])})
        if limit and len(confirmed) >= limit:
            break

    confirmed.sort(key=lambda s: (s["ticker"] != WORLD_CUP_SERIES, s["ticker"]))
    return confirmed, detail_errors


# --------------------------------------------------------------------------- #
# capture — one JSONL line per event (mutually-exclusive outcome bracket)
# --------------------------------------------------------------------------- #
def _outcome_row(m: Dict[str, Any]) -> Dict[str, Any]:
    def _f(key: str) -> Optional[float]:
        v = m.get(key)
        return float(v) if v is not None else None

    _, outcome = parse_moneyline_ticker(m["ticker"])
    return {
        "ticker": m["ticker"], "outcome": outcome,
        "yes_bid_dollars": _f("yes_bid_dollars"), "yes_ask_dollars": _f("yes_ask_dollars"),
        "no_bid_dollars": _f("no_bid_dollars"), "no_ask_dollars": _f("no_ask_dollars"),
        "price_source_tag": "real_ask",
    }


def _group_by_event(markets: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for m in markets:
        event_ticker = m.get("event_ticker") or parse_moneyline_ticker(m["ticker"])[0]
        groups.setdefault(event_ticker, []).append(m)
    return groups


def _event_line(series_ticker: str, sport: str, event_ticker: str,
                title: str, markets: List[Dict[str, Any]], fetch_ts: str) -> Dict[str, Any]:
    outcomes = sorted((_outcome_row(m) for m in markets), key=lambda o: o["outcome"])
    asks = [o["yes_ask_dollars"] for o in outcomes]
    has_full_book = all(a is not None for a in asks)
    line: Dict[str, Any] = {
        "fetch_ts": fetch_ts, "venue": "kalshi", "series_ticker": series_ticker,
        "sport": sport, "event_ticker": event_ticker, "title": title,
        "n_outcomes": len(outcomes), "outcomes": outcomes,
        "completeness_ok": has_full_book,
    }
    if has_full_book:
        bsum = _bracket_sum(asks)
        line["bracket_sum"] = round(bsum, 6)
        line["overround_absorbed"] = round(_overround(asks), 6)
        line["price_source_tag"] = "real_ask"
    raw_bytes = canonical_json(sorted(markets, key=lambda m: m["ticker"]))
    line["raw_sha256"] = sha256_hex(raw_bytes)
    return line


def run(limit: Optional[int] = None, min_interval: float = 0.2,
        client: Optional[Kalshi] = None, store: Optional[Path] = None) -> Dict[str, Any]:
    """One read-only capture pass. `client`/`store` are injectable for offline testing;
    in production both default to the live Kalshi client and the real tape store."""
    store = Path(store) if store is not None else STORE
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)

    cap_ts = datetime.now(timezone.utc)
    fetch_ts = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    confirmed, detail_errors = discover_moneyline_series(client, limit=limit)

    lines: List[Dict[str, Any]] = []
    series_errors: List[Dict[str, str]] = []
    n_events_incomplete = 0
    for s in confirmed:
        sticker = s["ticker"]
        try:
            markets = client.open_markets(sticker)
        except Exception as exc:
            series_errors.append({"series": sticker, "error": str(exc)})
            continue
        if not markets:
            continue
        for event_ticker, ms in sorted(_group_by_event(markets).items()):
            title = ms[0].get("title", "")
            line = _event_line(sticker, s["sport"], event_ticker, title, ms, fetch_ts)
            lines.append(line)
            if not line["completeness_ok"]:
                n_events_incomplete += 1

    odds_key = os.environ.get("ODDS_API_KEY")
    odds_leg = "not_attempted(no matching impl yet)" if odds_key else "BLOCKED(key)"

    store.mkdir(parents=True, exist_ok=True)
    out_path = store / f"dt={day}" / f"pass-{capture_id}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for line in lines:
            f.write(canonical_json(line) + "\n")

    summary = {
        "capture_id": capture_id, "day": day, "fetch_ts": fetch_ts,
        "n_series_confirmed": len(confirmed), "n_series_errors": len(series_errors),
        "n_series_detail_errors": len(detail_errors),
        "n_events": len(lines), "n_events_complete": len(lines) - n_events_incomplete,
        "n_events_incomplete": n_events_incomplete,
        "odds_leg": odds_leg, "out_path": str(out_path),
    }
    print(f"[sports_pairs] {capture_id}: {summary['n_series_confirmed']} series, "
          f"{summary['n_events']} events ({summary['n_events_complete']} complete) "
          f"-> {out_path}; odds_leg={odds_leg}")
    if series_errors:
        print(f"[sports_pairs] WARN {len(series_errors)} series failed open_markets "
              f"(city/day may be missing this pass)", file=sys.stderr)
    if detail_errors:
        print(f"[sports_pairs] WARN {len(detail_errors)} series failed detail lookup "
              f"(excluded from confirmed set)", file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Forward Kalshi sports moneyline capture (read-only)")
    ap.add_argument("--limit", type=int, default=None, help="cap confirmed series per pass")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    run(limit=args.limit, min_interval=args.min_interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
