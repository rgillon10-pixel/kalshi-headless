"""Crypto-hourly settlement-basis capture (READ-ONLY) — Q2, serves S8 (crypto-hourly
settlement basis) / S10 (reachability decay).

Kalshi's KXBTC/KXETH "range" series post a fresh hourly bracket ladder (a mutually
exclusive/exhaustive set of threshold + band outcome markets over the full price range,
the same overround-bearing shape as the weather temperature ladder — see
collection/capture_orderbooks.py) alongside a much-longer-dated "range" event under the
SAME series_ticker (empirically ~7 days). Duration, not the ticker string, is what
distinguishes the true hourly ladder from the standing longer one — see
`find_current_hourly_event`.

One pass, per symbol (BTC via KXBTC, ETH via KXETH):
  1. Discover the CURRENT hourly event (open markets grouped by event_ticker; pick the
     one whose (close_time - open_time) is closest to 3600s, preferring one that
     genuinely straddles `now`).
  2. Snapshot every outcome market's real yes_ask BBO (tag `real_ask`; `bracket_sum`/
     `overround` via core.pricing, the sole sanctioned site — Hard Rule #3).
  3. Fetch the live public spot price for the same symbol (Coinbase primary, Kraken
     fallback — Q2: ">=1 public exchange endpoint"; tag `synthetic` — never a fill).
  4. Locate the PREVIOUS hour's settlement: the settled event whose close_time equals
     the current event's open_time, and read off Kalshi's own `expiration_value` (tag
     `broker_truth` — the exchange's own reported settlement fact). Stored alongside the
     spot leg so S8's ρ-guard (spot-vs-settle correlation) is computable from tape alone,
     with no second pass needed.

A failure at any leg (spot fetch, settlement lookup) degrades to an honest status code
(`spot_status`/`settle_status`) rather than poisoning the Kalshi ladder leg, which is
captured unconditionally — same discipline as collection/sports_pairs.py's odds leg.

Run one pass:
    python -m collection.crypto_hourly
    python -m collection.crypto_hourly --limit 400   # cap markets scanned per series (testing)
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from core.canonical import canonical_json, sha256_hex
from core.crypto_schema import CryptoHourlyManifest, validate
from core.io import REPO_ROOT
from core.pricing import bracket_sum, overround
from core.timeutil import _parse_iso
from validation.v3_market import Kalshi, _load_venue_cfg

STORE = REPO_ROOT / "tape" / "crypto_hourly"
COINBASE_BASE = "https://api.exchange.coinbase.com"
KRAKEN_BASE = "https://api.kraken.com/0/public"

# Kalshi series -> {display symbol, per-exchange product/pair codes for the spot leg}.
SYMBOLS: Dict[str, Dict[str, str]] = {
    "KXBTC": {"symbol": "BTC", "coinbase_product": "BTC-USD", "kraken_pair": "XBTUSD"},
    "KXETH": {"symbol": "ETH", "coinbase_product": "ETH-USD", "kraken_pair": "ETHUSD"},
}


def _slug(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


# --------------------------------------------------------------------------- #
# spot leg — public reference price, Coinbase primary / Kraken fallback (synthetic)
# --------------------------------------------------------------------------- #
class SpotClient:
    """Thin throttled client for public spot tickers. Never raises: a total failure
    across both exchanges degrades to (None, "") rather than poisoning the pass."""

    def __init__(self, session: Optional[requests.Session] = None, min_interval: float = 0.2):
        self.s = session or requests.Session()
        self._min_interval = min_interval
        self._last = 0.0

    def _throttle(self) -> None:
        gap = time.time() - self._last
        if gap < self._min_interval:
            time.sleep(self._min_interval - gap)
        self._last = time.time()

    def spot(self, coinbase_product: str, kraken_pair: str) -> Tuple[Optional[float], str]:
        """Returns (price, exchange_name); (None, "") if both exchanges fail."""
        self._throttle()
        try:
            r = self.s.get(f"{COINBASE_BASE}/products/{coinbase_product}/ticker", timeout=15)
            r.raise_for_status()
            return float(r.json()["price"]), "coinbase"
        except Exception:
            pass
        self._throttle()
        try:
            r = self.s.get(f"{KRAKEN_BASE}/Ticker", params={"pair": kraken_pair}, timeout=15)
            r.raise_for_status()
            result = (r.json() or {}).get("result") or {}
            row = next(iter(result.values()), None)
            if row is None:
                return None, ""
            return float(row["c"][0]), "kraken"
        except Exception:
            return None, ""


# --------------------------------------------------------------------------- #
# discovery — group open markets by event_ticker, pick the true hourly ladder
# --------------------------------------------------------------------------- #
def group_by_event(markets: List[dict]) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for m in markets:
        et = m.get("event_ticker") or ""
        if not et:
            continue
        out.setdefault(et, []).append(m)
    return out


def find_current_hourly_event(events: Dict[str, List[dict]], now: datetime) -> Optional[str]:
    """Pick the event whose (close_time - open_time) is closest to exactly one hour.

    Kalshi keeps a much-longer-dated standing 'range' event alongside the true hourly
    ladder under the SAME series_ticker (observed ~7 days); duration is what actually
    distinguishes them, not the ticker string. Prefers a candidate that genuinely
    straddles `now` (open_time <= now < close_time); falls back to closest-by-duration
    if none currently straddle (e.g. a brief gap between hours)."""
    candidates: List[Tuple[str, datetime, datetime, float]] = []
    for event_ticker, mk in events.items():
        m = mk[0]
        try:
            open_dt = _parse_iso(m["open_time"])
            close_dt = _parse_iso(m["close_time"])
        except (KeyError, ValueError, TypeError):
            continue
        duration = (close_dt - open_dt).total_seconds()
        candidates.append((event_ticker, open_dt, close_dt, duration))
    if not candidates:
        return None
    active = [c for c in candidates if c[1] <= now < c[2]]
    pool = active if active else candidates
    return min(pool, key=lambda c: abs(c[3] - 3600.0))[0]


# --------------------------------------------------------------------------- #
# settlement leg — the previous hour's Kalshi-reported settle value (broker_truth)
# --------------------------------------------------------------------------- #
def find_previous_settlement(client, series_ticker: str, current_open_time: str,
                             limit: int = 500) -> Tuple[str, str, Dict[str, Any]]:
    """Locate the settled event whose close_time == the current hourly event's
    open_time (the hour immediately prior) and read off its `expiration_value` (shared
    across every outcome market in that event — same underlying settle price).

    Returns (prev_event_ticker, status, info) where status is one of
    core.crypto_schema.VALID_SETTLE_STATUS and info holds {"prev_close_time",
    "settle_value"} on "ok". Never raises: a fetch failure degrades to "fetch_error"."""
    try:
        settled = client.markets(series_ticker, status="settled", limit=limit)
    except Exception:
        return "", "fetch_error", {}
    try:
        target = _parse_iso(current_open_time)
    except (ValueError, TypeError):
        return "", "not_found", {}
    for m in settled:
        close_time = m.get("close_time")
        if not close_time:
            continue
        try:
            if _parse_iso(close_time) != target:
                continue
        except (ValueError, TypeError):
            continue
        exp = m.get("expiration_value")
        if exp is None:
            continue
        try:
            settle_value = float(exp)
        except (TypeError, ValueError):
            continue
        return (m.get("event_ticker") or ""), "ok", {
            "prev_close_time": close_time, "settle_value": settle_value,
        }
    return "", "not_found", {}


# --------------------------------------------------------------------------- #
# capture — one signed manifest line per symbol
# --------------------------------------------------------------------------- #
def run(limit: Optional[int] = None, min_interval: float = 0.2,
        client=None, store: Optional[Path] = None,
        spot_client=None, settled_limit: int = 500,
        now: Optional[datetime] = None) -> Dict:
    """One read-only capture pass. `client`/`store`/`spot_client`/`now` are injectable
    for offline testing; production defaults to the live Kalshi client, the real tape
    store, a live Coinbase/Kraken SpotClient, and the real wall-clock."""
    store = Path(store) if store is not None else STORE
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)
    if spot_client is None:
        spot_client = SpotClient()
    source_endpoint = getattr(client, "base", "") + "/markets?series_ticker={series}&status={status}"

    cap_ts = now if now is not None else datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")
    capture_dir = store / f"dt={day}" / f"capture-{capture_id}"

    manifests: List[Dict] = []
    degenerate: List[Dict] = []
    invalid: List[Dict] = []
    series_errors: List[Dict] = []
    spot_status_counts: Dict[str, int] = {}
    settle_status_counts: Dict[str, int] = {}

    for series_ticker, sym_cfg in SYMBOLS.items():
        symbol = sym_cfg["symbol"]
        try:
            open_mk = client.open_markets(series_ticker)
        except Exception as exc:
            series_errors.append({"series": series_ticker, "error": str(exc)})
            continue
        if limit:
            open_mk = open_mk[:limit]

        events = group_by_event(open_mk)
        event_ticker = find_current_hourly_event(events, cap_ts)
        if event_ticker is None:
            degenerate.append({"series": series_ticker, "reason": "no_hourly_event_found"})
            continue

        markets = sorted(events[event_ticker], key=lambda m: m.get("ticker", ""))
        if len(markets) < 2:
            degenerate.append({"series": series_ticker, "event_ticker": event_ticker,
                               "n_outcomes": len(markets)})
            continue

        asks: List[float] = []
        outcome_tickers: List[str] = []
        raw_by_ticker: Dict[str, Any] = {}
        for m in markets:
            t = m.get("ticker", "")
            outcome_tickers.append(t)
            raw_by_ticker[t] = m
            ask_raw = m.get("yes_ask_dollars")
            if ask_raw is not None:
                asks.append(float(ask_raw))

        b_sum = bracket_sum(asks) if asks else 0.0
        b_overround = overround(asks) if asks else 0.0
        event_time = markets[0].get("open_time") or captured_at
        close_time = markets[0].get("close_time") or captured_at

        spot_price, spot_exchange = spot_client.spot(sym_cfg["coinbase_product"],
                                                      sym_cfg["kraken_pair"])
        spot_status = "ok" if spot_price is not None else "fetch_error"
        spot_status_counts[spot_status] = spot_status_counts.get(spot_status, 0) + 1

        prev_event_ticker, settle_status, settle_info = find_previous_settlement(
            client, series_ticker, event_time, limit=settled_limit)
        settle_status_counts[settle_status] = settle_status_counts.get(settle_status, 0) + 1

        raw_str = canonical_json(raw_by_ticker)
        manifest = CryptoHourlyManifest(
            capture_id=capture_id, venue="kalshi", symbol=symbol, series_ticker=series_ticker,
            event_ticker=event_ticker, event_time=event_time, close_time=close_time,
            as_of=captured_at, captured_at=captured_at,
            source_endpoint=source_endpoint,
            raw_sha256=sha256_hex(raw_str),
            n_outcomes=len(outcome_tickers), expected_outcomes=len(outcome_tickers),
            bracket_sum=round(b_sum, 6), overround=round(b_overround, 6),
            price_source_tag="real_ask",
            spot_price=round(spot_price, 6) if spot_price is not None else 0.0,
            spot_exchange=spot_exchange, spot_status=spot_status,
            prev_event_ticker=prev_event_ticker,
            prev_close_time=settle_info.get("prev_close_time", ""),
            settle_value=round(settle_info.get("settle_value", 0.0), 6),
            settle_status=settle_status,
            outcomes=outcome_tickers,
            completeness_ok=True,
        ).signed()

        errs = validate(manifest)
        if errs:
            print(f"[crypto_hourly] WARN {series_ticker} {event_ticker}: manifest invalid, "
                  f"not written: {errs}", file=sys.stderr)
            invalid.append({"series": series_ticker, "event_ticker": event_ticker, "errors": errs})
            continue

        capture_dir.mkdir(parents=True, exist_ok=True)
        stem = _slug(f"{series_ticker}_{event_ticker}")
        (capture_dir / f"{stem}.raw.json").write_text(raw_str, encoding="utf-8")
        store.mkdir(parents=True, exist_ok=True)
        with open(store / "_manifest.jsonl", "a") as mf:
            mf.write(canonical_json(manifest) + "\n")
        manifests.append(manifest)

    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_symbols": len(SYMBOLS), "n_captured": len(manifests),
        "n_degenerate": len(degenerate), "n_invalid": len(invalid),
        "n_series_errors": len(series_errors),
        "spot_status_counts": spot_status_counts,
        "settle_status_counts": settle_status_counts,
        "total_outcomes": sum(m["n_outcomes"] for m in manifests),
    }
    print(f"[crypto_hourly] {capture_id}: {summary['n_captured']}/{summary['n_symbols']} "
          f"symbols captured, spot={spot_status_counts}, settle={settle_status_counts} "
          f"-> {capture_dir}")
    if degenerate:
        print(f"[crypto_hourly] WARN {len(degenerate)} symbol(s) with no capturable "
              f"hourly bracket this pass", file=sys.stderr)
    if series_errors:
        print(f"[crypto_hourly] WARN {len(series_errors)} series failed enumeration",
              file=sys.stderr)
    return summary


def verify_against_dir(manifest: Dict, capture_dir: Path) -> List[str]:
    """Recompute the manifest's raw_sha256 from the ON-DISK provenance file and confirm
    it matches — same provenance discipline as sports_pairs/capture_orderbooks."""
    capture_dir = Path(capture_dir)
    errs: List[str] = []
    stem = _slug(f"{manifest['series_ticker']}_{manifest['event_ticker']}")
    raw_file = capture_dir / f"{stem}.raw.json"
    if not raw_file.exists():
        errs.append(f"raw provenance missing: {stem}.raw.json")
    elif sha256_hex(raw_file.read_bytes()) != manifest.get("raw_sha256"):
        errs.append("raw_sha256 does not match on-disk raw bytes")
    return errs


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Crypto-hourly settlement-basis capture (read-only)")
    ap.add_argument("--limit", type=int, default=None, help="cap markets scanned per series")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    run(limit=args.limit, min_interval=args.min_interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
