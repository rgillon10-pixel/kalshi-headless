"""Sports moneyline paired-odds collector (READ-ONLY) — serves S7/S11.

Builds the forward tape S7 (Kalshi NFL/NBA/... moneyline vs Pinnacle de-vigged fair, CLV
harvest) and S11 (sharp-anchored maker quoting) need — Kalshi does not archive its own book,
so this must run forward from today. Mirrors `collection/capture_orderbooks.py` discipline:
bitemporal `fetch_ts` (frozen once per pass), content hashes on every fetched book, and honest
expected-vs-captured completeness (a dropped leg lowers completeness, it never fakes success).

Ticker grammar (empirically derived, same shape across ~40 active `*GAME`-suffix series today):
    <SERIES>-<EVENT_CODE>-<LEG>
e.g. `KXWCGAME-26JUL11ARGSUI-ARG`, `KXNFLGAME-26AUG15DALSEA-SEA`. Kalshi does not tag which
`*GAME` series are 2-outcome (no-draw sports) vs 3-outcome (soccer, draw possible) moneylines,
and some `*GAME` series are single-leg props (e.g. `KXWCTEAMSINGAME-26USAENG-Y`, "will X play
Y") rather than a mutually-exclusive outcome set. A moneyline group is discovered empirically:
group markets by (series, event_code), keep only groups with 2 or 3 legs — exactly the shape of
a head-to-head (2) or head-to-head-with-draw (3) moneyline; single-leg groups are props and are
dropped.

Kalshi books are bids-only per outcome; the tradeable ask is `1 - opposite_best_bid`
(collection/normalize.py, reused here verbatim — same primitive, same discipline).

De-vig math (`devig_probs`) is a pure function of a list of decimal odds — used only when
`ODDS_API_KEY` is present (the-odds-api). No key today, so the odds leg of every group is
recorded `odds_status="no_key"` and the Kalshi leg is captured anyway (never blocked on the
optional leg).

Run one pass:
    python -m collection.sports_pairs
    python -m collection.sports_pairs --limit 50   # cap discovered legs (smoke test)
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

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from core.pricing import bracket_sum
from collection.normalize import normalize_snapshot
from validation.v3_market import Kalshi, _load_venue_cfg

SPORTS_CATEGORY = "Sports"
ORDERBOOK_PATH = "/markets/{ticker}/orderbook"
STORE = REPO_ROOT / "tape" / "sports_pairs"
SCHEMA_VERSION = "sports_pairs.v0"

# <series>-<event_code>-<leg>, each segment alnum-only (empirically the grammar of every
# *GAME-suffix Sports series sampled 2026-07-08: soccer/WC, NFL, NBA, MLB, esports, ...).
TICKER_RE = re.compile(r"^(?P<series>[A-Z0-9]+)-(?P<event>[A-Z0-9]+)-(?P<leg>[A-Z0-9]+)$")

# A mutually-exclusive moneyline outcome set is 2-way (no draw) or 3-way (draw possible).
# Any other group size discovered under a *GAME series is a prop (single-leg "will X play Y",
# or a >3-way market Kalshi files under the same series) and is not a moneyline pair.
_MONEYLINE_SIZES = (2, 3)


def parse_market_ticker(ticker: str) -> Optional[Tuple[str, str, str]]:
    """(series, event_code, leg) or None if `ticker` doesn't match the moneyline grammar."""
    m = TICKER_RE.match(ticker.upper())
    if not m:
        return None
    return m.group("series"), m.group("event"), m.group("leg")


# --------------------------------------------------------------------------- #
# discovery — the EXPECTED set of moneyline groups
# --------------------------------------------------------------------------- #
def discover_moneyline_series(client: Kalshi) -> List[str]:
    """Sports-category series whose ticker ends `GAME` — the empirical moneyline naming
    convention (head-to-head result of one game/match), verified 2026-07-08 across soccer,
    NFL, NBA, MLB, esports, and 30+ other leagues currently listed."""
    series = client.series_by_category(SPORTS_CATEGORY)
    return sorted({s["ticker"] for s in series
                  if (s.get("ticker") or "").endswith("GAME")})


def discover_groups(client: Kalshi, series_tickers: List[str], limit: Optional[int] = None
                    ) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]], List[Dict[str, str]]]:
    """Enumerate open markets across `series_tickers`, grouped by (series, event_code) and
    filtered to moneyline-shaped groups (2 or 3 legs). Returns (groups, series_errors).

    groups[(series, event)] = {"legs": {leg_code: market_dict}, "series_title": str}
    """
    groups: Dict[Tuple[str, str], Dict[str, Any]] = {}
    series_errors: List[Dict[str, str]] = []
    seen = 0
    for sticker in series_tickers:
        try:
            markets = client.open_markets(sticker)
        except Exception as exc:
            series_errors.append({"series": sticker, "error": str(exc)})
            continue
        for m in markets:
            ticker = m.get("ticker", "")
            parsed = parse_market_ticker(ticker)
            if parsed is None:
                continue
            series, event, leg = parsed
            g = groups.setdefault((series, event), {"legs": {}})
            g["legs"][leg] = m
            seen += 1
            if limit and seen >= limit:
                return _filter_moneyline(groups), series_errors
    return _filter_moneyline(groups), series_errors


def _filter_moneyline(groups: Dict[Tuple[str, str], Dict[str, Any]]
                      ) -> Dict[Tuple[str, str], Dict[str, Any]]:
    return {k: v for k, v in groups.items() if len(v["legs"]) in _MONEYLINE_SIZES}


# --------------------------------------------------------------------------- #
# de-vig math — pure, no network/clock (used only when ODDS_API_KEY is present)
# --------------------------------------------------------------------------- #
def devig_probs(decimal_odds: List[float]) -> List[float]:
    """Multiplicative de-vig: raw implied prob = 1/odds, normalized to sum to 1.

    Standard treatment (the vig is assumed proportional across outcomes — the simplest and
    most common de-vig model; see kb/quant-finance for alternatives if this needs refining).
    Every element must be > 1.0 (a decimal odds of <=1.0 pays back <= the stake, malformed).
    """
    if not decimal_odds:
        raise ValueError("devig_probs requires at least one odds value")
    if any(o <= 1.0 for o in decimal_odds):
        raise ValueError(f"decimal odds must be > 1.0, got {decimal_odds!r}")
    raw = [1.0 / o for o in decimal_odds]
    total = sum(raw)
    return [r / total for r in raw]


def odds_api_key() -> Optional[str]:
    return os.environ.get("ODDS_API_KEY") or None


# --------------------------------------------------------------------------- #
# capture — one JSONL line per (series, event_code) moneyline group
# --------------------------------------------------------------------------- #
def run(limit: Optional[int] = None, min_interval: float = 0.15,
        client: Optional[Kalshi] = None, store: Optional[Path] = None) -> Dict[str, Any]:
    """One read-only capture pass. `client`/`store` are injectable for offline testing."""
    store = Path(store) if store is not None else STORE
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)
    source_endpoint = getattr(client, "base", "") + ORDERBOOK_PATH

    cap_ts = datetime.now(timezone.utc)
    fetch_ts = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    key_present = odds_api_key() is not None
    odds_status = "no_key" if not key_present else "not_fetched"  # fetch not implemented (no key to test against)

    series_tickers = discover_moneyline_series(client)
    groups, series_errors = discover_groups(client, series_tickers, limit=limit)

    lines: List[Dict[str, Any]] = []
    degenerate: List[Dict[str, str]] = []
    n_complete = 0

    for (series, event), g in sorted(groups.items()):
        expected_legs = sorted(g["legs"])
        leg_records: List[Dict[str, Any]] = []
        dropped: List[str] = []

        for leg in expected_legs:
            m = g["legs"][leg]
            ticker = m["ticker"]
            try:
                text = client.get_text(ORDERBOOK_PATH.format(ticker=ticker))
            except Exception:
                dropped.append(leg)
                continue
            ob = (json.loads(text) or {}).get("orderbook_fp") or {}
            snap = normalize_snapshot(ticker, ob)
            leg_records.append({
                "ticker": ticker, "leg": leg,
                "title": m.get("title"), "yes_sub_title": m.get("yes_sub_title"),
                "best_yes_bid": snap["best_yes_bid"], "best_no_bid": snap["best_no_bid"],
                "best_yes_ask": snap["best_yes_ask"], "best_no_ask": snap["best_no_ask"],
                "depth": snap["depth"], "raw_sha256": sha256_hex(text.encode("utf-8")),
                "source_tag": "real_ask",
            })

        if not leg_records:
            degenerate.append({"series": series, "event": event, "expected": len(expected_legs)})
            continue

        completeness_ok = len(leg_records) == len(expected_legs)
        n_complete += completeness_ok
        asks = [r["best_yes_ask"] for r in leg_records if r["best_yes_ask"] is not None]
        bsum = bracket_sum(asks) if completeness_ok and len(asks) == len(leg_records) else None

        line = {
            "schema_version": SCHEMA_VERSION,
            "capture_id": capture_id, "fetch_ts": fetch_ts, "venue": "kalshi",
            "series": series, "event_code": event,
            "expected_legs": len(expected_legs), "captured_legs": len(leg_records),
            "completeness_ok": completeness_ok,
            "dropped_legs": dropped,
            "legs": sorted(leg_records, key=lambda r: r["leg"]),
            "bracket_sum": bsum, "bracket_sum_source_tag": "real_ask" if bsum is not None else None,
            "odds": None, "odds_status": odds_status,
            "source_endpoint": source_endpoint,
        }
        lines.append(line)

    out_dir = store / f"dt={day}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"pairs-{capture_id}.jsonl"
    with open(out_path, "a") as f:
        for line in lines:
            f.write(canonical_json(line) + "\n")

    summary = {
        "capture_id": capture_id, "day": day, "fetch_ts": fetch_ts,
        "n_series_scanned": len(series_tickers), "n_series_errors": len(series_errors),
        "n_groups": len(lines), "n_complete": n_complete, "n_degenerate": len(degenerate),
        "n_legs_captured": sum(l["captured_legs"] for l in lines),
        "odds_status": odds_status,
    }
    print(f"[sports_pairs] {capture_id}: {summary['n_groups']} moneyline groups "
          f"({n_complete} complete), {summary['n_legs_captured']} legs, "
          f"odds={odds_status} -> {out_path}")
    if series_errors:
        print(f"[sports_pairs] WARN {len(series_errors)} series failed enumeration",
              file=sys.stderr)
    if degenerate:
        print(f"[sports_pairs] WARN {len(degenerate)} discovered group(s) captured zero legs",
              file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Sports moneyline paired-odds capture (read-only)")
    ap.add_argument("--limit", type=int, default=None, help="cap discovered legs (smoke test)")
    ap.add_argument("--min-interval", type=float, default=0.15)
    args = ap.parse_args(argv)
    run(limit=args.limit, min_interval=args.min_interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
