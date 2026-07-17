"""Kalshi crypto-perpetuals tape collector (READ-ONLY) — /margin market data + funding.

LOOP-QUEUE.md Q42/Q43 prerequisite (2026-07-16, Ryan interactive session — perps recon).
Kalshi launched CFTC-regulated crypto perpetual futures 2026-05-29 (BTCPERP live
2026-06-03); the market-data surface is PUBLIC and unauthenticated under the separate
`/margin` namespace at `external-api.kalshi.com` — a different host and product from the
event-contract API every other collector reads. Nobody else is archiving this venue from
month one (prime directive #2), and two of the four capture legs are NOT retrievable
later: the L2 book and the intra-window funding-rate *estimate* (a TWAP of the premium
index that is finalized — and its path destroyed — at each 8h funding time). The
finalized funding prints and the markets summary ARE retrievable, captured anyway for a
self-contained tape.

One pass, four record types into `tape/perp_tape/dt=YYYY-MM-DD.jsonl`:

  1. **markets** — the full `/markets` contract list (BBO, OI, volume, venue mark/
     reference/liquidation prices, leverage curve). BBO fields are real resting quotes
     (`real_ask`/`real_bid`); the venue-computed mark family is `broker_truth`.
  2. **orderbook** — full L2 for the configured liquid tickers (default BTC+ETH perps),
     levels preserved verbatim as delivered (dollar-string [price, size] pairs).
  3. **funding_estimate** — the live estimate for EVERY active contract discovered in
     (1); this is the leg that dies at each funding boundary. `broker_truth`.
  4. **funding_rates** — finalized prints over a trailing window (`mode=recent`,
     default 24h; dedup on (market_ticker, funding_time) at analysis time), or the
     full since-launch history via `--backfill-funding` (`mode=backfill`, run once).

Empirical (2026-07-16 recon, live API): funding prints are EXACTLY 0 in 62–99% of 8h
windows per contract (a dead band/clamp — Hyperliquid's same-window BTC funding is
never 0), which is Q42's whole thesis; 13 active + 3 inactive (`KXDOTPERP`/
`KXHBARPERP`/`KXXLMPERP` pending CFTC review — their activation is a Q43-adjacent
listing event, so status is captured every pass). Orderbook arrays arrive ordered
far-from-touch first; preserved verbatim, never re-sorted here.

A perp price is an index-tracking dollar price, NEVER a probability — no bracket_sum/
normalized_ask math applies here (Hard Rule #3 is about binary ladders; this tape is
the delta-1 side those ladders will be judged against).

Run one pass / backfill:
    python -m collection.perp_tape
    python -m collection.perp_tape --backfill-funding
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from validation.v3_market import Kalshi

TAPE = REPO_ROOT / "tape" / "perp_tape"

# Separate host AND namespace from the event-contract API (docs.kalshi.com/margin) —
# deliberately not read from config/venues.yaml, whose kalshi entry is the event API.
PERP_API_BASE = "https://external-api.kalshi.com/trade-api/v2/margin"

# Full-L2 capture set: the two deep, liquid contracts (ETH ~$89M/24h, BTC ~$82M/24h
# notional at recon). Books for the long tail are thin and the markets-record BBO
# already covers them; widen deliberately, not by default.
L2_TICKERS = ("KXBTCPERP", "KXETHPERP")

# 2026-05-29T00:00:00Z — perps launch announcement day; the API returns "earliest
# available" for anything at-or-before the first print (observed 2026-06-03T20:00:00Z).
LAUNCH_TS = 1780012800

RECENT_FUNDING_WINDOW_S = 24 * 3600


# --------------------------------------------------------------------------- #
# numeric coercion — API delivers decimals as strings; persist floats, never fail
# --------------------------------------------------------------------------- #
def _f(v: Any) -> Optional[float]:
    """Float or None — a missing/unparseable field stays None (visible), never 0.0."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _contract_row(m: Dict[str, Any]) -> Dict[str, Any]:
    """One market's persisted row. BBO = real resting quotes; the venue-computed mark
    family (mark/reference/settlement/liquidation) is Kalshi's own number, broker_truth."""
    return {
        "ticker": m.get("ticker", ""),
        "title": m.get("title", ""),
        "status": m.get("status", ""),
        "bid": _f(m.get("bid")),
        "ask": _f(m.get("ask")),
        "last_price": _f(m.get("price")),
        "tick_size": _f(m.get("tick_size")),
        "contract_size": _f(m.get("contract_size")),
        "open_interest": _f(m.get("open_interest")),
        "open_interest_notional_dollars": _f(m.get("open_interest_notional_value_dollars")),
        "volume_24h": _f(m.get("volume_24h")),
        "volume_24h_notional_dollars": _f(m.get("volume_24h_notional_value_dollars")),
        "leverage_estimate": _f(m.get("leverage_estimate")),
        "leverage_estimates": m.get("leverage_estimates"),
        "reference_price": m.get("reference_price"),
        "settlement_mark_price": m.get("settlement_mark_price"),
        "liquidation_mark_price": m.get("liquidation_mark_price"),
        "bbo_source_tag": "real_ask",       # bid field is correspondingly real_bid
        "mark_source_tag": "broker_truth",
    }


# --------------------------------------------------------------------------- #
# section fetchers — each returns (record_body, ok); a failure is a visible record
# --------------------------------------------------------------------------- #
def fetch_markets(client: Kalshi) -> Tuple[Dict[str, Any], bool]:
    try:
        text = client.get_text("/markets")
    except Exception as exc:
        return {"status": "fetch_error", "error": str(exc)}, False
    markets = (json.loads(text).get("markets")) or []
    rows = sorted((_contract_row(m) for m in markets), key=lambda r: r["ticker"])
    active = [r["ticker"] for r in rows if r["status"] == "active"]
    return {
        "status": "ok",
        "contracts": rows,
        "n_contracts": len(rows),
        "n_active": len(active),
        "n_inactive": len(rows) - len(active),
        "active_tickers": active,
        "raw_sha256": sha256_hex(text),
    }, True


def fetch_orderbook(client: Kalshi, ticker: str) -> Tuple[Dict[str, Any], bool]:
    try:
        text = client.get_text(f"/markets/{ticker}/orderbook")
    except Exception as exc:
        return {"status": "fetch_error", "error": str(exc), "ticker": ticker}, False
    ob = json.loads(text).get("orderbook") or {}
    asks, bids = ob.get("asks") or [], ob.get("bids") or []
    return {
        "status": "ok",
        "ticker": ticker,
        # verbatim [price, size] dollar-string pairs, venue ordering preserved
        "asks": asks,
        "bids": bids,
        "n_ask_levels": len(asks),
        "n_bid_levels": len(bids),
        "asks_source_tag": "real_ask",
        "bids_source_tag": "real_bid",
        "raw_sha256": sha256_hex(text),
    }, True


def fetch_funding_estimate(client: Kalshi, ticker: str) -> Tuple[Dict[str, Any], bool]:
    try:
        text = client.get_text("/funding_rates/estimate", ticker=ticker)
    except Exception as exc:
        return {"status": "fetch_error", "error": str(exc), "ticker": ticker}, False
    j = json.loads(text)
    return {
        "status": "ok",
        "ticker": j.get("market_ticker", ticker),
        "funding_rate_estimate": _f(j.get("funding_rate")),
        "mark_price": _f(j.get("mark_price")),
        "computed_time": j.get("computed_time"),
        "next_funding_time": j.get("next_funding_time"),
        "price_source_tag": "broker_truth",
        "raw_sha256": sha256_hex(text),
    }, True


def fetch_funding_rates(client: Kalshi, start_ts: int,
                        end_ts: Optional[int] = None) -> Tuple[Dict[str, Any], bool]:
    """Finalized funding prints in [start_ts, end_ts]. Cursor-paginated defensively —
    the current API returns everything-in-one-page, but a silent truncation on a future
    paginated response would be data loss, so the cursor is followed if ever present."""
    prints: List[Dict[str, Any]] = []
    raw_pages: List[str] = []
    cursor: Optional[str] = None
    try:
        while True:
            params: Dict[str, Any] = {"start_ts": start_ts}
            if end_ts is not None:
                params["end_ts"] = end_ts
            if cursor:
                params["cursor"] = cursor
            text = client.get_text("/funding_rates/historical", **params)
            raw_pages.append(text)
            j = json.loads(text)
            items = j.get("funding_rates") or []
            prints.extend({
                "market_ticker": r.get("market_ticker", ""),
                "funding_time": r.get("funding_time", ""),
                "funding_rate": _f(r.get("funding_rate")),
                "mark_price": _f(r.get("mark_price")),
            } for r in items)
            cursor = j.get("cursor")
            if not cursor or not items:
                break
    except Exception as exc:
        return {"status": "fetch_error", "error": str(exc),
                "start_ts": start_ts, "end_ts": end_ts}, False
    return {
        "status": "ok",
        "start_ts": start_ts,
        "end_ts": end_ts,
        "prints": sorted(prints, key=lambda p: (p["funding_time"], p["market_ticker"])),
        "n_prints": len(prints),
        "price_source_tag": "broker_truth",
        "raw_sha256": sha256_hex("".join(raw_pages)),
    }, True


# --------------------------------------------------------------------------- #
# capture — one JSONL line per section per pass
# --------------------------------------------------------------------------- #
def _now_ids() -> Tuple[str, str, str, datetime]:
    ts = datetime.now(timezone.utc)
    return ts.strftime("%Y%m%dT%H%M%SZ"), ts.isoformat(), ts.strftime("%Y-%m-%d"), ts


def _write(tape_dir: Path, day: str, lines: List[str]) -> str:
    tape_dir.mkdir(parents=True, exist_ok=True)
    out_path = tape_dir / f"dt={day}.jsonl"
    with open(out_path, "a", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln + "\n")
    return str(out_path)


def run(min_interval: float = 0.2, client: Optional[Kalshi] = None,
        tape_dir: Optional[Path] = None,
        l2_tickers: Tuple[str, ...] = L2_TICKERS) -> Dict[str, Any]:
    """One read-only capture pass. `client`/`tape_dir`/`l2_tickers` injectable for
    offline testing. Summary contract matches hourly_pass folding: `n_lines` /
    `n_contracts` / `completeness_ok` / `path` / `capture_id`."""
    tape_dir = Path(tape_dir) if tape_dir is not None else TAPE
    if client is None:
        client = Kalshi(PERP_API_BASE, min_interval=min_interval)

    capture_id, captured_at, day, ts = _now_ids()
    base = {"schema_version": "perp_tape.v1", "capture_id": capture_id,
            "captured_at": captured_at, "venue": "kalshi_perps"}

    lines: List[str] = []
    n_ok = 0
    n_expected = 0

    def _emit(record_type: str, body: Dict[str, Any], ok: bool) -> None:
        nonlocal n_ok, n_expected
        n_expected += 1
        n_ok += int(ok)
        lines.append(canonical_json({**base, "record_type": record_type, **body}))

    markets_body, markets_ok = fetch_markets(client)
    _emit("markets", markets_body, markets_ok)
    n_contracts = markets_body.get("n_contracts", 0)

    for ticker in l2_tickers:
        body, ok = fetch_orderbook(client, ticker)
        _emit("orderbook", body, ok)

    # estimates for every ACTIVE contract discovered THIS pass — the intra-window
    # premium path is the unretrievable leg. If markets failed, the discovery set is
    # honestly empty and the missing estimates surface via markets' own failed section
    # (never a stale/hardcoded ticker list masquerading as discovery).
    for ticker in markets_body.get("active_tickers") or []:
        body, ok = fetch_funding_estimate(client, ticker)
        _emit("funding_estimate", body, ok)

    now_ts = int(ts.timestamp())
    funding_body, funding_ok = fetch_funding_rates(client, now_ts - RECENT_FUNDING_WINDOW_S)
    _emit("funding_rates", {"mode": "recent", **funding_body}, funding_ok)

    summary: Dict[str, Any] = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_sections_expected": n_expected, "n_sections_ok": n_ok,
        "n_lines": len(lines), "n_contracts": n_contracts,
        "completeness_ok": n_ok == n_expected,
    }
    summary["path"] = _write(tape_dir, day, lines)
    print(f"[perp_tape] {capture_id}: {n_ok}/{n_expected} sections ok, "
          f"{n_contracts} contracts")
    return summary


def backfill_funding(min_interval: float = 0.2, client: Optional[Kalshi] = None,
                     tape_dir: Optional[Path] = None,
                     start_ts: int = LAUNCH_TS) -> Dict[str, Any]:
    """One-shot full funding-history capture since launch (`mode=backfill`). Finalized
    prints are venue-retrievable, so re-running just appends a fresher snapshot; dedup
    on (market_ticker, funding_time) at analysis time."""
    tape_dir = Path(tape_dir) if tape_dir is not None else TAPE
    if client is None:
        client = Kalshi(PERP_API_BASE, min_interval=min_interval)

    capture_id, captured_at, day, _ = _now_ids()
    body, ok = fetch_funding_rates(client, start_ts)
    record = {"schema_version": "perp_tape.v1", "capture_id": capture_id,
              "captured_at": captured_at, "venue": "kalshi_perps",
              "record_type": "funding_rates", "mode": "backfill", **body}
    path = _write(tape_dir, day, [canonical_json(record)])
    summary = {"capture_id": capture_id, "day": day, "n_prints": body.get("n_prints", 0),
               "completeness_ok": ok, "path": path}
    print(f"[perp_tape] backfill {capture_id}: {summary['n_prints']} funding prints, "
          f"{'ok' if ok else 'FAIL'}")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Kalshi crypto-perps tape capture (read-only)")
    ap.add_argument("--backfill-funding", action="store_true",
                    help="one-shot: capture the FULL funding-rate history since launch")
    ap.add_argument("--start-ts", type=int, default=LAUNCH_TS,
                    help="backfill window start (unix seconds; default = launch day)")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    if args.backfill_funding:
        summary = backfill_funding(min_interval=args.min_interval, start_ts=args.start_ts)
    else:
        summary = run(min_interval=args.min_interval)
    return 0 if summary["completeness_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
