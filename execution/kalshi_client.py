"""execution.kalshi_client — THE only module allowed to hold authenticated / order-capable
Kalshi endpoints (CLAUDE.md execution lane, live tier).

Structural gate: credentials come ONLY from the environment (`KALSHI_API_KEY_ID`,
`KALSHI_PRIVATE_KEY_PATH`), which exist on the VPS/local box and never in a cloud sandbox.
`from_env()` raises if either is absent, so an unauthenticated run cannot construct a client.

Scope (deliberately minimal — S90 is a once-a-day IOC taker): balance, create an IOC limit
order, read an order (to learn the real fill), and a `live_fill_fn` adapter that turns a real
fill into the same `execution.schema.Fill` record the paper tier books, tagged `real_ask`
with fill_model='live_ioc'. Fees are what Kalshi reports on the order when present, else
`core.pricing.fee_per_contract` at the fill price (taker rate), flagged in caveats.

Signing: Kalshi API v2 — RSA-PSS/SHA-256 over `<ts_ms><METHOD><path>` (path without query),
headers KALSHI-ACCESS-KEY / KALSHI-ACCESS-SIGNATURE (base64) / KALSHI-ACCESS-TIMESTAMP.
"""
from __future__ import annotations

import base64
import json
import os
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from core.pricing import fee_per_contract
from execution.schema import Fill, Order

DEFAULT_BASE = "https://api.elections.kalshi.com"
API_PREFIX = "/trade-api/v2"


def _load_private_key(pem_path: str):
    from cryptography.hazmat.primitives import serialization
    with open(pem_path, "rb") as fh:
        return serialization.load_pem_private_key(fh.read(), password=None)


def sign(private_key, ts_ms: str, method: str, path: str) -> str:
    """base64 RSA-PSS signature over ts+METHOD+path. `path` is the full request path
    (e.g. /trade-api/v2/portfolio/balance) with no query string."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    msg = f"{ts_ms}{method.upper()}{path}".encode("utf-8")
    sig = private_key.sign(
        msg,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(sig).decode("ascii")


class KalshiOrderClient:
    def __init__(self, key_id: str, private_key, base: str = DEFAULT_BASE, session=None,
                 timeout: float = 20.0) -> None:
        if not key_id or private_key is None:
            raise ValueError("KalshiOrderClient needs a key id and a private key")
        self.key_id = key_id
        self.pk = private_key
        self.base = base.rstrip("/")
        self.timeout = timeout
        if session is None:
            import requests
            session = requests.Session()
        self.s = session

    @classmethod
    def from_env(cls, base: Optional[str] = None) -> "KalshiOrderClient":
        key_id = os.environ.get("KALSHI_API_KEY_ID")
        pem = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
        if not key_id or not pem or not os.path.exists(pem):
            raise RuntimeError("live credentials absent (KALSHI_API_KEY_ID / KALSHI_PRIVATE_KEY_PATH)")
        return cls(key_id, _load_private_key(pem), base=base or os.environ.get("KALSHI_API_BASE", DEFAULT_BASE))

    # ------------------------------------------------------------------ transport
    def _headers(self, method: str, path: str) -> Dict[str, str]:
        ts = str(int(time.time() * 1000))
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": sign(self.pk, ts, method, path),
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "Content-Type": "application/json",
            "User-Agent": "kalshi-headless-s90/1",
        }

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None,
                 params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        full = API_PREFIX + path
        r = self.s.request(method, self.base + full, headers=self._headers(method, full),
                           data=json.dumps(body) if body is not None else None,
                           params=params, timeout=self.timeout)
        if r.status_code >= 400:
            raise RuntimeError(f"kalshi {method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else {}

    # ------------------------------------------------------------------ endpoints
    def balance_dollars(self) -> float:
        d = self._request("GET", "/portfolio/balance")
        # v2 reports cents in `balance`; some versions add `balance_dollars`
        if "balance_dollars" in d:
            return float(d["balance_dollars"])
        return float(d.get("balance", 0)) / 100.0

    def create_ioc_limit_buy(self, order: Order) -> Dict[str, Any]:
        """Place an immediate-or-cancel limit BUY for `order` (side yes/no, price in dollars).
        Returns the venue's order object. Never retries (a retry could double-fill)."""
        if order.action != "buy":
            raise ValueError("S90 live path places buys only")
        body = {
            "ticker": order.ticker,
            "client_order_id": str(uuid.uuid5(uuid.NAMESPACE_URL, order.order_id)),
            "side": order.side,
            "action": "buy",
            "type": "limit",
            "count": int(order.qty),
            "time_in_force": "immediate_or_cancel",
            f"{order.side}_price_dollars": f"{order.limit_price:.2f}",
        }
        d = self._request("POST", "/portfolio/orders", body=body)
        return d.get("order", d)

    def get_order(self, order_id: str) -> Dict[str, Any]:
        d = self._request("GET", f"/portfolio/orders/{order_id}")
        return d.get("order", d)

    def get_fills(self, order_id: str) -> List[Dict[str, Any]]:
        d = self._request("GET", "/portfolio/fills", params={"order_id": order_id, "limit": 200})
        return list(d.get("fills") or [])


def _num(x: Any) -> Optional[float]:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def fill_from_venue(order: Order, venue_order: Dict[str, Any], fills: List[Dict[str, Any]],
                    ts: str) -> Optional[Fill]:
    """Turn a venue order + its fills into one ledger Fill (qty = total filled, price =
    size-weighted average). None when nothing filled (IOC cancelled)."""
    qty = 0
    cost = 0.0
    fee_total = 0.0
    fee_known = True
    for f in fills:
        c = int(_num(f.get("count")) or 0)
        p = _num(f.get(f"{order.side}_price_dollars"))
        if p is None:
            p = (_num(f.get(f"{order.side}_price")) or 0.0) / 100.0
        if c <= 0 or p <= 0:
            continue
        qty += c
        cost += c * p
        fee = _num(f.get("fee_dollars"))
        if fee is None:
            fee_known = False
        else:
            fee_total += fee
    if qty <= 0:
        filled = int(_num(venue_order.get("filled_count") or venue_order.get("fill_count")) or 0)
        if filled <= 0:
            return None
        qty = filled
        cost = qty * order.limit_price
        fee_known = False
    price = round(cost / qty, 2)
    caveats = ["live_ioc"]
    if not fee_known:
        fee_total = round(fee_per_contract(price) * qty, 2)
        caveats.append("fee_modeled_not_reported")
    return Fill(
        fill_id=f"{order.order_id}:livefill:{venue_order.get('order_id', '')}",
        order_id=order.order_id, ts=ts, ticker=order.ticker, side=order.side, action="buy",
        price=price, qty=qty, fee=round(fee_total, 2), fill_model="live_ioc",
        price_source_tag="real_ask", caveats=caveats,
    )


def live_fill_fn(client: KalshiOrderClient) -> Callable[[Order, List[Dict[str, Any]]], Optional[Fill]]:
    """PaperBroker-compatible fill_fn that places the REAL order and reports the REAL fill."""
    def _fn(order: Order, _tape_records: List[Dict[str, Any]]) -> Optional[Fill]:
        venue = client.create_ioc_limit_buy(order)
        oid = venue.get("order_id") or ""
        fills = client.get_fills(oid) if oid else []
        if oid and not fills:
            venue = client.get_order(oid)
        ts = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
        return fill_from_venue(order, venue, fills, ts)
    return _fn
