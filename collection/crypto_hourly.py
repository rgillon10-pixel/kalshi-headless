"""Crypto-hourly settlement collector (READ-ONLY) — BTC/ETH bracket books + spot + settle.

LOOP-QUEUE.md Q2: serves S8 (crypto-hourly settlement basis) and S10 (reachability decay).
Mirrors `collection/sports_pairs.py` / `collection/capture_orderbooks.py` discipline:
bitemporal `captured_at`, raw-bytes sha256 provenance, honest expected-vs-captured
completeness (a fetch failure lowers `completeness_ok`, it never silently drops a market).

Kalshi's KXBTC/KXETH ("Bitcoin/Ethereum range") series price a fresh hourly bracket ladder
every hour — ticker grammar `SERIES-YYMONDDHH-[T|B]<strike>`, `HH` in ET so `close_time` =
`HH+4:00Z` during EDT (empirically confirmed 2026-07-03 against the live API, not assumed).
One pass, per symbol:

  1. **current** — discover the CURRENT hourly bracket group: the open group whose
     `close_time - open_time` marks it as the hourly ladder, not a stray long-lived group
     under the same series (observed live: a ~1-week-open `KXBTC-...17` group that is a
     different market shape reusing the hourly ticker grammar — excluded by duration, not
     assumed away). Per-outcome BBO tagged `real_ask`; `bracket_sum`/`overround_absorbed`
     via `core.pricing` (Hard Rule #3).
  2. **previous_settlement** — the PREVIOUS hour's event_ticker is derived by pure ticker
     arithmetic (subtract 1 hour from the current group's token — no clock read) and queried
     directly via `?event_ticker=`. Kalshi's own `result` + `expiration_value` (the CF
     Benchmarks index average actually used to settle) are `broker_truth` — this is exactly
     the paired (settle, spot) data S8's ρ-guard needs.
  3. **spot** — Coinbase `products/{PAIR}/ticker`, Kraken fallback if Coinbase fails;
     `synthetic` (CLAUDE.md: an external reference price, not itself a Kalshi fill).

Run one pass:
    python -m collection.crypto_hourly
    python -m collection.crypto_hourly --symbols BTC   # cap symbols (offline/dev use)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from core.pricing import bracket_sum, overround
from validation.v3_market import Kalshi, _load_venue_cfg

TAPE = REPO_ROOT / "tape" / "crypto_hourly"

SYMBOLS = {"BTC": "KXBTC", "ETH": "KXETH"}
COINBASE_BASE = "https://api.exchange.coinbase.com"
COINBASE_PRODUCT = {"BTC": "BTC-USD", "ETH": "ETH-USD"}
KRAKEN_BASE = "https://api.kraken.com/0/public"
KRAKEN_PAIR = {"BTC": "XBTUSD", "ETH": "ETHUSD"}
_UA = {"User-Agent": "kalshi-headless/0.0 (research)"}

# A genuine hourly bracket ladder has close_time - open_time ~= 1h. A stray same-series
# group observed to stay open ~1 week (KXBTC-26JUL0317 empirically) is not the hourly
# ladder and must not be picked up as "current" just because it's open.
_HOURLY_GROUP_MAX_SECONDS = 65 * 60

_EVENT_TOKEN_RE = re.compile(r"^(?P<yy>\d{2})(?P<mon>[A-Z]{3})(?P<dd>\d{2})(?P<hh>\d{2})$")


# --------------------------------------------------------------------------- #
# hour-token arithmetic (pure — no clock, no network)
# --------------------------------------------------------------------------- #
def parse_hour_token(token: str) -> Optional[datetime]:
    """Parse an event-ticker date+hour token (e.g. '26JUL0302') to a naive datetime."""
    if not _EVENT_TOKEN_RE.match(token.upper()):
        return None
    try:
        return datetime.strptime(token.upper(), "%y%b%d%H")
    except ValueError:
        return None


def previous_hour_event_ticker(event_ticker: str) -> Optional[str]:
    """Derive the previous hour's event_ticker by pure arithmetic on the current one's
    date+hour token (e.g. 'KXBTC-26JUL0300' -> 'KXBTC-26JUL0223', handling day/month/year
    rollover). Returns None if the ticker doesn't match the expected grammar."""
    series_part, sep, token = event_ticker.partition("-")
    if not sep:
        return None
    dt = parse_hour_token(token)
    if dt is None:
        return None
    prev = dt - timedelta(hours=1)
    return f"{series_part}-{prev.strftime('%y%b%d%H').upper()}"


# --------------------------------------------------------------------------- #
# discovery — the CURRENT hourly bracket group
# --------------------------------------------------------------------------- #
def _fetch_markets_raw(client: Kalshi, **params: Any) -> Tuple[List[Dict], List[str]]:
    """Manually paginate /markets, keeping verbatim raw page bytes (provenance), the same
    discipline as sports_pairs._fetch_open_markets_raw."""
    markets: List[Dict] = []
    raw_pages: List[str] = []
    cursor: Optional[str] = None
    while True:
        p = dict(params)
        if cursor:
            p["cursor"] = cursor
        text = client.get_text("/markets", **p)
        raw_pages.append(text)
        j = json.loads(text)
        items = j.get("markets") or []
        markets.extend(items)
        cursor = j.get("cursor")
        if not cursor or not items:
            break
    return markets, raw_pages


def discover_current_hour_group(client: Kalshi, series_ticker: str
                                ) -> Tuple[Optional[str], List[Dict], List[str], Optional[str]]:
    """Return (event_ticker, markets, raw_pages, error) for the CURRENT hourly bracket
    group: among open groups whose duration marks them as the hourly ladder, the one
    closing soonest. error is None on success (a non-error empty result is
    'no_hourly_group_found', not a fetch failure)."""
    try:
        markets, raw_pages = _fetch_markets_raw(
            client, series_ticker=series_ticker, status="open", limit=1000)
    except Exception as exc:
        return None, [], [], str(exc)

    by_event: Dict[str, List[Dict]] = {}
    for m in markets:
        by_event.setdefault(m.get("event_ticker", ""), []).append(m)

    candidates: List[Tuple[datetime, str, List[Dict]]] = []
    for et, ms in by_event.items():
        close, open_ = ms[0].get("close_time"), ms[0].get("open_time")
        if not et or not close or not open_:
            continue
        try:
            c = datetime.fromisoformat(close.replace("Z", "+00:00"))
            o = datetime.fromisoformat(open_.replace("Z", "+00:00"))
        except ValueError:
            continue
        if (c - o).total_seconds() <= _HOURLY_GROUP_MAX_SECONDS:
            candidates.append((c, et, ms))

    if not candidates:
        return None, [], raw_pages, "no_hourly_group_found"
    candidates.sort(key=lambda t: t[0])
    _, et, ms = candidates[0]
    return et, ms, raw_pages, None


def _capture_outcomes(markets: List[Dict]) -> Tuple[List[Dict], List[float]]:
    """Per-outcome real_ask BBO, dropping any market with no live ask (never fabricated) —
    the drop shows up as captured < expected, lowering completeness_ok."""
    outcomes: List[Dict] = []
    yes_asks: List[float] = []
    for m in sorted(markets, key=lambda m: m.get("ticker", "")):
        yes_ask_dollars = m.get("yes_ask_dollars")
        if yes_ask_dollars is None:
            continue
        ya = float(yes_ask_dollars)
        yes_asks.append(ya)
        outcomes.append({
            "ticker": m.get("ticker", ""),
            "title": m.get("title", ""),
            "floor_strike": m.get("floor_strike"),
            "cap_strike": m.get("cap_strike"),
            "strike_type": m.get("strike_type"),
            "yes_ask": ya,
            "yes_bid": float(m["yes_bid_dollars"]) if m.get("yes_bid_dollars") is not None else None,
            "no_ask": float(m["no_ask_dollars"]) if m.get("no_ask_dollars") is not None else None,
            "no_bid": float(m["no_bid_dollars"]) if m.get("no_bid_dollars") is not None else None,
            "price_source_tag": "real_ask",
        })
    return outcomes, yes_asks


# --------------------------------------------------------------------------- #
# previous-hour settlement — Kalshi's own result + settle index value
# --------------------------------------------------------------------------- #
def fetch_settlement(client: Kalshi, event_ticker: str) -> Dict[str, Any]:
    """The previous hour's settlement, queried directly by event_ticker (no status filter
    needed — a closed event returns its markets regardless of finalized/settled status).
    `broker_truth`: Kalshi's own reported result and settle index value, not a model."""
    try:
        text = client.get_text("/markets", event_ticker=event_ticker)
    except Exception as exc:
        return {"status": "fetch_error", "error": str(exc), "event_ticker": event_ticker}
    raw_sha256 = sha256_hex(text.encode("utf-8"))
    markets = (json.loads(text).get("markets")) or []
    if not markets:
        return {"status": "not_found", "event_ticker": event_ticker, "raw_sha256": raw_sha256}

    settled = [m for m in markets if m.get("result")]
    if len(settled) < len(markets):
        return {"status": "pending", "event_ticker": event_ticker, "raw_sha256": raw_sha256,
                "n_markets": len(markets), "n_settled": len(settled)}

    values = sorted({m.get("expiration_value") for m in markets if m.get("expiration_value")})
    return {
        "status": "settled",
        "event_ticker": event_ticker,
        "raw_sha256": raw_sha256,
        "n_markets": len(markets),
        "expiration_value": values[0] if len(values) == 1 else None,
        "expiration_values_disagree": values if len(values) > 1 else None,
        "results": {m["ticker"]: m.get("result") for m in markets},
        "price_source_tag": "broker_truth",
    }


# --------------------------------------------------------------------------- #
# spot — external reference price, never a Kalshi fill (synthetic)
# --------------------------------------------------------------------------- #
def fetch_spot_coinbase(symbol: str) -> Dict[str, Any]:
    product = COINBASE_PRODUCT[symbol]
    r = requests.get(f"{COINBASE_BASE}/products/{product}/ticker", timeout=15, headers=_UA)
    r.raise_for_status()
    j = r.json()
    return {"source": "coinbase", "product": product, "price": float(j["price"]),
            "bid": float(j["bid"]), "ask": float(j["ask"]), "exchange_time": j.get("time"),
            "price_source_tag": "synthetic"}


def fetch_spot_kraken(symbol: str) -> Dict[str, Any]:
    pair = KRAKEN_PAIR[symbol]
    r = requests.get(f"{KRAKEN_BASE}/Ticker", params={"pair": pair}, timeout=15, headers=_UA)
    r.raise_for_status()
    j = r.json()
    if j.get("error"):
        raise RuntimeError(f"kraken error: {j['error']}")
    result = j.get("result") or {}
    if not result:
        raise RuntimeError("kraken: empty result")
    _, v = next(iter(result.items()))
    return {"source": "kraken", "pair": pair, "price": float(v["c"][0]),
            "bid": float(v["b"][0]), "ask": float(v["a"][0]), "exchange_time": None,
            "price_source_tag": "synthetic"}


def fetch_spot(symbol: str) -> Dict[str, Any]:
    """Coinbase primary, Kraken fallback. A total failure is recorded honestly (never a
    stale/fabricated substitute) so it lowers pass_complete instead of masquerading as data."""
    last_err = None
    for fetcher in (fetch_spot_coinbase, fetch_spot_kraken):
        try:
            return fetcher(symbol)
        except Exception as exc:
            last_err = str(exc)
    return {"status": "fetch_error", "error": last_err, "price_source_tag": "synthetic"}


# --------------------------------------------------------------------------- #
# capture — one JSONL line per symbol per pass
# --------------------------------------------------------------------------- #
def run(min_interval: float = 0.2, client: Optional[Kalshi] = None,
        tape_dir: Optional[Path] = None, symbols: Optional[Dict[str, str]] = None,
        spot_fetcher: Callable[[str], Dict[str, Any]] = fetch_spot) -> Dict:
    """One read-only capture pass. `client`/`tape_dir`/`spot_fetcher` injectable for
    offline testing."""
    tape_dir = Path(tape_dir) if tape_dir is not None else TAPE
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)
    symbols = symbols if symbols is not None else SYMBOLS

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    lines: List[str] = []
    n_complete = 0
    for symbol, series_ticker in sorted(symbols.items()):
        record: Dict[str, Any] = {
            "schema_version": "crypto_hourly.v1",
            "capture_id": capture_id, "captured_at": captured_at,
            "venue": "kalshi", "symbol": symbol, "series": series_ticker,
        }

        event_ticker, markets, raw_pages, disc_err = discover_current_hour_group(
            client, series_ticker)
        if disc_err:
            record["current"] = {"status": disc_err}
            record["previous_settlement"] = {"status": "no_current_group"}
        else:
            outcomes, yes_asks = _capture_outcomes(markets)
            expected, captured = len(markets), len(outcomes)
            bsum = bracket_sum(yes_asks) if yes_asks else None
            record["current"] = {
                "status": "ok",
                "event_ticker": event_ticker,
                "close_time": markets[0].get("close_time"),
                "open_time": markets[0].get("open_time"),
                "outcomes": outcomes,
                "expected_outcomes": expected,
                "captured_outcomes": captured,
                "member_count": captured,
                "completeness_ok": captured == expected,
                "bracket_sum": bsum,
                "overround_absorbed": overround(yes_asks) if yes_asks else None,
                "raw_sha256": sha256_hex("".join(raw_pages).encode("utf-8")) if raw_pages else None,
                "price_source_tag": "real_ask",
            }
            prev_et = previous_hour_event_ticker(event_ticker)
            record["previous_settlement"] = (
                fetch_settlement(client, prev_et) if prev_et
                else {"status": "no_previous_ticker"})

        record["spot"] = spot_fetcher(symbol)

        record["pass_complete"] = (
            record["current"].get("completeness_ok") is True
            and record["previous_settlement"].get("status") == "settled"
            and "price" in record["spot"]
        )
        n_complete += int(record["pass_complete"])
        lines.append(canonical_json(record))

    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_symbols": len(symbols), "n_complete": n_complete,
    }
    if lines:
        tape_dir.mkdir(parents=True, exist_ok=True)
        out_path = tape_dir / f"dt={day}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
        summary["path"] = str(out_path)

    print(f"[crypto_hourly] {capture_id}: {summary['n_symbols']} symbols, "
          f"{n_complete} pass-complete")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Crypto-hourly settlement capture (read-only)")
    ap.add_argument("--symbols", nargs="*", default=None,
                    help="cap symbols per pass, e.g. --symbols BTC (offline/dev use)")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    symbols = {s: SYMBOLS[s] for s in args.symbols} if args.symbols else None
    run(min_interval=args.min_interval, symbols=symbols)
    return 0


if __name__ == "__main__":
    sys.exit(main())
