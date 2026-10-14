#!/usr/bin/env python3
"""s90_daily_pass.py — Probe C / S90 weather-favorite-taker daily pass (paper tier + gated live).

Modes (one per cron fire; every mode is idempotent and append-only):

  propose   00:35 UTC daily. Lists every OPEN daily temperature market from the public
            /markets listing (no credentials), writes the raw snapshot to
            tape/s90_weather/dt=<day>.jsonl (monitor_poll schema, tag real_ask), runs the frozen
            S90 rule, and books the orders + taker fills into the paper ledger
            paper/ledger_s90/. A fill is the observed ask for min(qty, visible ask size) — the
            taker model, no queue assumption. With --live (gated, see below) it ALSO sends the
            same orders to Kalshi as IOC limit buys and books the REAL fills instead.
  settle    daily after expiry (14:10 UTC). For every open paper position whose market has a
            venue result, books a Settlement (broker_truth) at $1/$0.
  report    prints the running track record (fills, settled, P&L, hit rate vs entry) so the
            paper record can be compared with the pre-registered expectation.

LIVE GATE (CLAUDE.md execution lane, all required, checked at runtime, no exceptions):
  --live flag  AND  reset-2026-09/50-probes/LIVE-AUTH-S90.md present with Ryan's signature line
  AND  KALSHI_API_KEY_ID + KALSHI_PRIVATE_KEY_PATH in the environment (VPS/local only)
  AND  bankroll caps from execution.limits honoured by the PaperBroker-style pre-check.
Nothing in this file imports the order client unless --live passes the gate.

Run:  python scripts/s90_daily_pass.py propose|settle|report [--live] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.canonical import canonical_json, sha256_hex  # noqa: E402
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import fee_per_contract  # noqa: E402
from execution.paper_broker import PaperBroker  # noqa: E402
from execution.schema import Fill, Order, Settlement  # noqa: E402
from execution.strategy_api import TapeContext  # noqa: E402
from execution.strategies.s90_weather_favorite_taker import (  # noqa: E402
    FAMILY, NAME, S90WeatherFavoriteTaker, is_daily_ticker)

TAPE_DIR = REPO_ROOT / "tape" / "s90_weather"
LEDGER_DIR = REPO_ROOT / "paper" / "ledger_s90"
LIVE_LEDGER_DIR = REPO_ROOT / "paper" / "ledger_s90_live"   # real fills, same schema
LIVE_AUTH = REPO_ROOT.parent / "reset-2026-09" / "50-probes" / "LIVE-AUTH-S90.md"
SNAPSHOT_SCHEMA = "s90_weather.snapshot.v1"


# ───────────────────────────────────────────── market listing (public, read-only)
def _client():
    from validation.v3_market import Kalshi, _load_venue_cfg
    return Kalshi(_load_venue_cfg()["api_base"], min_interval=0.25)


def list_daily_weather_markets(client=None) -> List[Dict[str, Any]]:
    """Every OPEN daily temperature market, as raw /markets dicts. Discovery reuses
    collection.weather_books.discover (config/cities.yaml series ∪ category sweep)."""
    from collection.weather_books import discover
    client = client or _client()
    by_group, _report, _errs = discover(client)
    out = []
    for _series, m in by_group.get("daily", []):
        if is_daily_ticker(m.get("ticker") or ""):
            out.append(m)
    return out


def snapshot_records(markets: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    """monitor_poll-shaped records (the shape the strategy and the calibration both read)."""
    from collection.monitor_poll import _record
    captured_at, capture_id = now.isoformat(), now.strftime("%Y%m%dT%H%M%S%fZ")
    recs = []
    for m in markets:
        page_sha = sha256_hex(canonical_json(m).encode("utf-8"))
        r = _record(m, captured_at, capture_id, page_sha)
        r["schema_version"] = SNAPSHOT_SCHEMA
        r["event_ticker"] = m.get("event_ticker")
        r["series"] = (m.get("ticker") or "").split("-")[0]
        recs.append(r)
    return recs


def write_tape(recs: List[Dict[str, Any]], now: datetime, tape_dir: Path = TAPE_DIR) -> Path:
    tape_dir.mkdir(parents=True, exist_ok=True)
    p = tape_dir / f"dt={now.strftime('%Y-%m-%d')}.jsonl"
    with open(p, "a", encoding="utf-8") as fh:
        for r in recs:
            fh.write(canonical_json(r) + "\n")
    return p


# ───────────────────────────────────────────── paper fill model (taker at the observed ask)
def taker_at_ask_fill(order: Order, tape_records: List[Dict[str, Any]]) -> Optional[Fill]:
    rec = next((r for r in tape_records if r.get("ticker") == order.ticker), None)
    if rec is None or rec.get("price_source_tag") != "real_ask":
        return None
    ask = rec.get("yes_ask")
    size = float(rec.get("yes_ask_size") or 0.0)
    if ask is None or float(ask) > order.limit_price or size < 1:
        return None
    qty = min(order.qty, int(size))
    price = round(float(ask), 2)
    return Fill(
        fill_id=f"{order.order_id}:fill",
        order_id=order.order_id,
        ts=rec.get("captured_at") or order.ts,
        ticker=order.ticker, side="yes", action="buy",
        price=price, qty=qty,
        fee=round(fee_per_contract(price) * qty, 2),
        fill_model="taker_bbo_size",
        price_source_tag="real_ask",
        caveats=["size_from_listing_at_touch", "no_latency_model"],
    )


# ───────────────────────────────────────────── live gate + client (imported only when needed)
def live_gate_errors() -> List[str]:
    errs = []
    if not LIVE_AUTH.exists():
        errs.append(f"missing {LIVE_AUTH}")
    else:
        txt = LIVE_AUTH.read_text(encoding="utf-8")
        if "SIGNED: Ryan Gillon" not in txt:
            errs.append("LIVE-AUTH-S90.md present but not signed ('SIGNED: Ryan Gillon' line absent)")
    if not os.environ.get("KALSHI_API_KEY_ID"):
        errs.append("KALSHI_API_KEY_ID not in environment")
    pem = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
    if not pem or not Path(pem).exists():
        errs.append("KALSHI_PRIVATE_KEY_PATH missing or file absent")
    return errs


# ───────────────────────────────────────────── modes
def run_propose(now: Optional[datetime] = None, live: bool = False, dry_run: bool = False,
                client=None, markets: Optional[List[Dict[str, Any]]] = None,
                ledger_dir: Optional[Path] = None, tape_dir: Path = TAPE_DIR) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    markets = markets if markets is not None else list_daily_weather_markets(client)
    recs = snapshot_records(markets, now)
    if not dry_run:
        write_tape(recs, now, tape_dir)
    strat = S90WeatherFavoriteTaker()
    orders = strat.propose_orders(TapeContext(records_by_family={FAMILY: recs}, now_ts=now.isoformat()))

    summary: Dict[str, Any] = {
        "mode": "propose", "live": live, "dry_run": dry_run, "captured_at": now.isoformat(),
        "n_markets": len(recs), "n_orders": len(orders),
        "orders": [{"ticker": o.ticker, "price": o.limit_price, "qty": o.qty} for o in orders],
    }
    if dry_run or not orders:
        print(f"[s90] {canonical_json(summary)}", flush=True)
        return summary

    if live:
        errs = live_gate_errors()
        if errs:
            summary["live_blocked"] = errs
            print(f"[s90] {canonical_json(summary)}", flush=True)
            return summary
        from execution.kalshi_client import KalshiOrderClient, live_fill_fn
        kc = KalshiOrderClient.from_env()
        broker = PaperBroker(ledger_dir or LIVE_LEDGER_DIR, as_of=now.isoformat())
        res = broker.submit(orders, recs, fill_fn=live_fill_fn(kc))
    else:
        broker = PaperBroker(ledger_dir or LEDGER_DIR, as_of=now.isoformat())
        # idempotency from ledger content: never re-order a ticker already ordered today
        already = {o.ticker for o in _orders_in_ledger(broker.ledger_dir) if o.ts[:10] == now.isoformat()[:10]}
        orders = [o for o in orders if o.ticker not in already]
        res = broker.submit(orders, recs, fill_fn=taker_at_ask_fill)
    summary.update({"n_accepted": res["n_accepted"], "n_fills": res["n_fills"],
                    "n_rejected": res["n_rejected"], "rejected": res["rejected"],
                    "open_notional": round(broker.open_notional(), 2)})
    print(f"[s90] {canonical_json(summary)}", flush=True)
    return summary


def _orders_in_ledger(ledger_dir: Path) -> List[Order]:
    out = []
    for p in sorted(Path(ledger_dir).glob("dt=*.jsonl")):
        for line in open(p, encoding="utf-8"):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("record_kind") == "order":
                out.append(Order.from_dict(d))
    return out


def fetch_results(tickers: List[str], client=None) -> Dict[str, str]:
    """{ticker: 'yes'|'no'} for settled markets, from the public listing (broker_truth)."""
    client = client or _client()
    out: Dict[str, str] = {}
    for i in range(0, len(tickers), 100):
        batch = tickers[i:i + 100]
        d = client.get("/markets", tickers=",".join(batch), limit=len(batch))
        for m in d.get("markets") or []:
            if m.get("result") in ("yes", "no"):
                out[m["ticker"]] = m["result"]
    return out


def run_settle(now: Optional[datetime] = None, client=None, ledger_dir: Optional[Path] = None,
               results: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    broker = PaperBroker(ledger_dir or LEDGER_DIR, as_of=now.isoformat())
    open_pos = [p for p in broker.open_positions() if p.qty > 0]
    tickers = sorted({p.ticker for p in open_pos})
    results = results if results is not None else (fetch_results(tickers, client) if tickers else {})
    settlements = []
    for p in open_pos:
        res = results.get(p.ticker)
        if res not in ("yes", "no"):
            continue
        settlements.append(Settlement(
            settlement_id=f"{NAME}:{p.ticker}:{p.side}:settle",
            ts=now.isoformat(), ticker=p.ticker, side=p.side,
            settle_value=1.0 if res == p.side else 0.0, qty=p.qty,
            event_ticker="-".join(p.ticker.split("-")[:2]),
        ))
    res = broker.settle(settlements) if settlements else {"n_settled": 0, "rejected": []}
    summary = {"mode": "settle", "ts": now.isoformat(), "n_open_before": len(open_pos),
               "n_settled": res["n_settled"], "n_rejected": len(res["rejected"]),
               "realized_pnl": round(broker.realized_pnl, 2), "cash": round(broker.cash, 2)}
    print(f"[s90] {canonical_json(summary)}", flush=True)
    return summary


def run_report(ledger_dir: Optional[Path] = None) -> Dict[str, Any]:
    ledger_dir = ledger_dir or LEDGER_DIR
    fills: List[Fill] = []
    settles: Dict[str, Settlement] = {}
    for p in sorted(Path(ledger_dir).glob("dt=*.jsonl")):
        for line in open(p, encoding="utf-8"):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("record_kind") == "fill":
                fills.append(Fill.from_dict(d))
            elif d.get("record_kind") == "settlement":
                settles[d["ticker"]] = Settlement.from_dict(d)
    n_contracts = sum(f.qty for f in fills)
    cost = sum(f.price * f.qty + f.fee for f in fills)
    settled = [f for f in fills if f.ticker in settles]
    wins = sum(f.qty for f in settled if settles[f.ticker].settle_value == 1.0)
    settled_contracts = sum(f.qty for f in settled)
    pnl = sum((settles[f.ticker].settle_value - f.price) * f.qty - f.fee for f in settled)
    avg_entry = (sum(f.price * f.qty for f in settled) / settled_contracts) if settled_contracts else None
    rep = {"mode": "report", "ledger": str(ledger_dir), "days": len(list(Path(ledger_dir).glob("dt=*.jsonl"))),
           "fills": len(fills), "contracts": n_contracts, "cost_incl_fees": round(cost, 2),
           "settled_contracts": settled_contracts, "hit_rate": (round(wins / settled_contracts, 3) if settled_contracts else None),
           "avg_entry": (round(avg_entry, 3) if avg_entry else None),
           "realized_pnl": round(pnl, 2),
           "pnl_per_contract": (round(pnl / settled_contracts, 4) if settled_contracts else None),
           "preregistered_expectation_per_contract": "+0.01 to +0.05 (kill if 14-day CI upper bound < 0)"}
    print(f"[s90] {canonical_json(rep)}", flush=True)
    return rep


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["propose", "settle", "report"])
    ap.add_argument("--live", action="store_true", help="send REAL orders (gated; see module doc)")
    ap.add_argument("--dry-run", action="store_true", help="propose only; write nothing")
    a = ap.parse_args(argv)
    if a.mode == "propose":
        run_propose(live=a.live, dry_run=a.dry_run)
    elif a.mode == "settle":
        run_settle()
    else:
        run_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
