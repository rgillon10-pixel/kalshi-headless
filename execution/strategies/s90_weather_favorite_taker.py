"""execution.strategies.s90_weather_favorite_taker — S90 (Probe C, pre-registered 2026-10-14).

THE TRADE (frozen; see reset-2026-09/50-probes/PROBE-C-weather-favorite-taker.md):
  Once a day, ~29 hours before a daily temperature market closes, BUY YES as a TAKER at the
  live ask on every KXHIGH*/KXLOW* daily market whose ask is in [ASK_MIN, ASK_MAX). Hold to
  settlement. No exits, no re-quoting, no maker leg.

WHY (prior, not data-mining): favorite-longshot bias — Bürgi, Deng & Whelan (CEPR DP20631)
find Kalshi contracts above 50c carry a small positive return; the 2026-10-14 calibration of
the repo's own weather tape (Jul 16 – Oct 13, 592 contracts at 50–80c, 587 city-days)
measured realized 0.650 vs ask 0.587 → +4.7c/contract after the taker fee, cluster-bootstrap
CI [+0.8c, +8.5c]. The caveats are in the probe doc (October-heavy, HIGH-series-driven).

PAPER-TIER REPRESENTATION: side='yes', action='buy', tif='ioc', limit_price = the observed
real ask (tag real_ask), qty = min(QTY_PER_MARKET, floor(visible ask size)). A fill at the ask
is a taker fill — the one fill model that needs no queue assumption (CLAUDE.md prime
directive: edge proven at taker prices).

This module is a PURE proposer: no network, no clock beyond context.now_ts, no persistence.
Records come from scripts/s90_daily_pass.py (public /markets listing, monitor_poll schema).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from execution.schema import Order

NAME = "s90_weather_favorite_taker"
FAMILY = "s90_weather"

# ─── Frozen rule parameters (pre-registered; changing any is a new probe, not a tweak) ───
SERIES_PREFIXES = ("KXHIGH", "KXLOW")   # daily temperature series only
ASK_MIN = 0.50                           # inclusive
ASK_MAX = 0.80                           # exclusive
HOURS_TO_CLOSE_MIN = 20.0                # the calibration horizon window (29h ± 9h)
HOURS_TO_CLOSE_MAX = 40.0
MAX_SPREAD = 0.30                        # a wider book is one-sided/stale → skip
QTY_PER_MARKET = 20                      # paper size; live size is set separately by bankroll
MAX_MARKETS_PER_PASS = 15                # diversification cap per day (one pass per day)
MIN_VISIBLE_SIZE = 1.0                   # need at least one contract showing at the ask

# Hourly / directional weather series share the KXHIGH prefix (e.g. KXHIGHNYD). They are NOT
# the calibrated population; their tickers carry an hour or direction token. We keep only
# tickers of the daily shape SERIES-YYMONDD-<strike>, i.e. exactly three dash-separated parts
# with an 8-char date token (e.g. KXHIGHTDAL-26OCT15-B72, KXHIGHNY-26OCT15-T70).
def is_daily_ticker(ticker: str) -> bool:
    parts = ticker.split("-")
    if len(parts) != 3:
        return False
    series, date_tok, strike = parts
    if not series.startswith(SERIES_PREFIXES):
        return False
    if len(date_tok) != 7 or not date_tok[:2].isdigit() or not date_tok[-2:].isdigit():
        return False
    return strike[:1] in ("B", "T") and len(strike) >= 2


def _parse_ts(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def hours_to_close(record: Dict[str, Any], now: datetime) -> Optional[float]:
    close = _parse_ts(record.get("close_time"))
    if close is None:
        return None
    return (close - now).total_seconds() / 3600.0


def select_candidates(records: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    """Apply the frozen rule to a list of monitor_poll-shaped market records. Returns the
    qualifying records sorted by ticker (deterministic), capped at MAX_MARKETS_PER_PASS by
    DESCENDING visible ask size (prefer the deeper book when the cap binds)."""
    out: List[Dict[str, Any]] = []
    for r in records:
        t = r.get("ticker") or ""
        if not is_daily_ticker(t):
            continue
        ya = r.get("yes_ask")
        yb = r.get("yes_bid")
        if ya is None or not (ASK_MIN <= float(ya) < ASK_MAX):
            continue
        if yb is not None and float(ya) - float(yb) > MAX_SPREAD:
            continue
        if r.get("price_source_tag") != "real_ask":
            continue  # never size off a modeled price
        size = r.get("yes_ask_size")
        if size is None or float(size) < MIN_VISIBLE_SIZE:
            continue
        h = hours_to_close(r, now)
        if h is None or not (HOURS_TO_CLOSE_MIN <= h <= HOURS_TO_CLOSE_MAX):
            continue
        out.append(r)
    out.sort(key=lambda r: (-float(r.get("yes_ask_size") or 0.0), r["ticker"]))
    out = out[:MAX_MARKETS_PER_PASS]
    out.sort(key=lambda r: r["ticker"])
    return out


def order_qty(record: Dict[str, Any], qty_cap: int = QTY_PER_MARKET) -> int:
    size = float(record.get("yes_ask_size") or 0.0)
    return max(0, min(int(qty_cap), int(size)))


class S90WeatherFavoriteTaker:
    name = NAME

    def __init__(self, qty_cap: int = QTY_PER_MARKET) -> None:
        self.qty_cap = int(qty_cap)

    def propose_orders(self, context: "TapeContext") -> List[Order]:  # noqa: F821
        records = context.records_by_family.get(FAMILY, [])
        now = _parse_ts(context.now_ts) or datetime.now(timezone.utc)
        orders: List[Order] = []
        for r in select_candidates(records, now):
            qty = order_qty(r, self.qty_cap)
            if qty <= 0:
                continue
            ticker = r["ticker"]
            event = "-".join(ticker.split("-")[:2])
            orders.append(Order(
                order_id=f"{self.name}:{now.strftime('%Y%m%d')}:{ticker}",
                ts=context.now_ts,
                ticker=ticker,
                side="yes",
                action="buy",
                limit_price=round(float(r["yes_ask"]), 2),
                qty=qty,
                tif="ioc",
                strategy=self.name,
                event_ticker=event,
            ))
        return orders
