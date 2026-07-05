"""Econ-print collector (READ-ONLY) — CPI/Core-CPI/Payrolls/GDP bracket ladders.

LOOP-QUEUE.md Q10: serves S12 (econ-print nowcast overlay). Mirrors
`collection/crypto_hourly.py` discipline: raw-bytes sha256 provenance, honest
expected-vs-captured completeness (a fetch failure lowers `completeness_ok`, it never
silently drops a market).

Kalshi's KXCPI/KXCPIYOY/KXCPICORE/KXPAYROLLS/KXGDP series (confirmed live 2026-07-05 via
`/series?category=Economics` + a structural check against `/markets`) each price a "will
the print exceed threshold T" ladder: several strikes share one `event_ticker`, each an
independent `strike_type: "greater"` binary, NOT a complete mutually-exclusive partition
like `crypto_hourly`'s KXBTC/KXETH brackets. `core.pricing.bracket_sum` is the sanctioned
site for partition ladders (Hard Rule #3) and is deliberately NOT called here — each
strike's yes_ask is persisted as its own `real_ask`, nothing summed or normalized.
(The nested-threshold arb shape these ladders DO admit — buying YES(higher T) + NO(lower
T) — is already covered platform-wide by `scripts/anomaly_sweep.py`'s
`cross_strike_monotonicity`, Q6; this module is a data feed, not a second arb scanner.)

One pass, per series:
  1. **open_events** — every currently-open event_ticker under the series; full
     per-strike real_ask BBO (dropping any market with no live ask, never fabricated).
  2. **recent_settlement** — the single most-recently-settled event_ticker for the
     series. Kalshi purges settled markets ~60 days after close (S7a finding) — every
     uncollected release is data lost forever, so this leg runs every pass regardless of
     the open ladder. Kalshi's own `result` + `expiration_value` (the actual BLS/BEA
     print) are `broker_truth`.
  3. **nowcast** — BLOCKED(nowcast-scrape), status always `not_built` this run: the
     Cleveland Fed inflation-nowcasting page renders its number client-side with no
     static data or discoverable API in the served HTML (checked live 2026-07-05); the
     Atlanta Fed GDPNow page DOES embed its full history as raw JS arrays
     (`gdpForecast`/`forecastDates`/`forecastQuarters`) but reliably slicing the current
     quarter's window is nontrivial and left for a follow-up pass. Never fabricated as a
     placeholder number.

Run one pass:
    python -m collection.econ_prints
    python -m collection.econ_prints --series cpi_mom gdp   # cap series (offline/dev use)
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
from validation.v3_market import Kalshi, _load_venue_cfg

TAPE = REPO_ROOT / "tape" / "econ_prints"

# Confirmed live 2026-07-05 via `/series?category=Economics` + a structural check (each
# has >=1 open event whose markets carry a numeric `floor_strike` / `strike_type ==
# "greater"` — a real threshold ladder, not a one-off annual yes/no).
SERIES = {
    "cpi_mom": "KXCPI",
    "cpi_yoy": "KXCPIYOY",
    "cpi_core_mom": "KXCPICORE",
    "payrolls": "KXPAYROLLS",
    "gdp": "KXGDP",
}

# Settled events are rare (monthly/quarterly) — one page comfortably covers years of
# history, so the "most recent" pick never has to worry about a second page.
_SETTLEMENT_SCAN_LIMIT = 200


# --------------------------------------------------------------------------- #
# pagination (mirrors crypto_hourly._fetch_markets_raw / sports_pairs' own copy —
# each collector owns its copy rather than sharing an abstraction over one call site)
# --------------------------------------------------------------------------- #
def _fetch_markets_raw(client: Kalshi, **params: Any) -> Tuple[List[Dict], List[str]]:
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


def _group_by_event(markets: List[Dict]) -> Dict[str, List[Dict]]:
    by_event: Dict[str, List[Dict]] = {}
    for m in markets:
        by_event.setdefault(m.get("event_ticker", ""), []).append(m)
    return by_event


# --------------------------------------------------------------------------- #
# open ladders
# --------------------------------------------------------------------------- #
def _capture_strikes(markets: List[Dict]) -> List[Dict]:
    """Per-strike real_ask BBO, dropping any market with no live ask (never fabricated —
    the drop shows up as captured < expected, lowering completeness_ok)."""
    strikes: List[Dict] = []
    for m in sorted(markets, key=lambda m: m.get("ticker", "")):
        yes_ask_dollars = m.get("yes_ask_dollars")
        if yes_ask_dollars is None:
            continue
        strikes.append({
            "ticker": m.get("ticker", ""),
            "title": m.get("title", ""),
            "floor_strike": m.get("floor_strike"),
            "strike_type": m.get("strike_type"),
            "yes_ask": float(yes_ask_dollars),
            "yes_bid": float(m["yes_bid_dollars"]) if m.get("yes_bid_dollars") is not None else None,
            "no_ask": float(m["no_ask_dollars"]) if m.get("no_ask_dollars") is not None else None,
            "no_bid": float(m["no_bid_dollars"]) if m.get("no_bid_dollars") is not None else None,
            "price_source_tag": "real_ask",
        })
    return strikes


def discover_open_events(client: Kalshi, series_ticker: str) -> Dict[str, Any]:
    """Every currently-open event_ticker under the series, each with its full per-strike
    ladder. Returns {"status": "ok"|"fetch_error", "events": [...], "error": ...}."""
    try:
        markets, raw_pages = _fetch_markets_raw(
            client, series_ticker=series_ticker, status="open", limit=1000)
    except Exception as exc:
        return {"status": "fetch_error", "error": str(exc), "events": []}

    raw_sha256 = sha256_hex("".join(raw_pages).encode("utf-8")) if raw_pages else None
    events: List[Dict[str, Any]] = []
    for et, ms in sorted(_group_by_event(markets).items()):
        if not et:
            continue
        strikes = _capture_strikes(ms)
        events.append({
            "event_ticker": et,
            "close_time": ms[0].get("close_time"),
            "strikes": strikes,
            "expected_strikes": len(ms),
            "captured_strikes": len(strikes),
            "completeness_ok": len(strikes) == len(ms),
        })
    return {"status": "ok", "events": events, "raw_sha256": raw_sha256}


# --------------------------------------------------------------------------- #
# most-recent settlement — Kalshi's own result + the actual published print value
# --------------------------------------------------------------------------- #
def fetch_recent_settlement(client: Kalshi, series_ticker: str) -> Dict[str, Any]:
    """The single most-recently-settled event_ticker for this series. `broker_truth`:
    Kalshi's own reported result and `expiration_value` (the actual BLS/BEA print), not
    a model. A series with no settled history yet is `no_settled_events`, not an error."""
    try:
        markets, raw_pages = _fetch_markets_raw(
            client, series_ticker=series_ticker, status="settled",
            limit=_SETTLEMENT_SCAN_LIMIT)
    except Exception as exc:
        return {"status": "fetch_error", "error": str(exc)}

    raw_sha256 = sha256_hex("".join(raw_pages).encode("utf-8")) if raw_pages else None
    by_event = _group_by_event(markets)
    if not by_event:
        return {"status": "no_settled_events", "raw_sha256": raw_sha256}

    et, ms = max(
        by_event.items(),
        key=lambda kv: kv[1][0].get("close_time") or "")

    settled = [m for m in ms if m.get("result")]
    if len(settled) < len(ms):
        return {"status": "pending", "event_ticker": et, "raw_sha256": raw_sha256,
                "n_markets": len(ms), "n_settled": len(settled)}

    values = sorted({m.get("expiration_value") for m in ms if m.get("expiration_value")})
    return {
        "status": "settled",
        "event_ticker": et,
        "raw_sha256": raw_sha256,
        "close_time": ms[0].get("close_time"),
        "n_markets": len(ms),
        "expiration_value": values[0] if len(values) == 1 else None,
        "expiration_values_disagree": values if len(values) > 1 else None,
        "results": {m["ticker"]: m.get("result") for m in ms},
        "price_source_tag": "broker_truth",
    }


# --------------------------------------------------------------------------- #
# nowcast leg — not built this run (BLOCKED, honestly recorded, never faked)
# --------------------------------------------------------------------------- #
def fetch_nowcast(series_key: str) -> Dict[str, Any]:
    """Cleveland Fed (CPI legs) / GDPNow (gdp leg) forward model comparator. Not built
    this run — see module docstring for why. Always an honest `not_built`, never a
    fabricated placeholder number."""
    return {"status": "not_built"}


# --------------------------------------------------------------------------- #
# capture — one JSONL line per series per pass
# --------------------------------------------------------------------------- #
def run(min_interval: float = 0.2, client: Optional[Kalshi] = None,
        tape_dir: Optional[Path] = None, series: Optional[Dict[str, str]] = None
        ) -> Dict[str, Any]:
    """One read-only capture pass. `client`/`tape_dir` injectable for offline testing."""
    tape_dir = Path(tape_dir) if tape_dir is not None else TAPE
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)
    series = series if series is not None else SERIES

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    lines: List[str] = []
    n_complete = 0
    for series_key, series_ticker in sorted(series.items()):
        record: Dict[str, Any] = {
            "schema_version": "econ_prints.v1",
            "capture_id": capture_id, "captured_at": captured_at,
            "venue": "kalshi", "series_key": series_key, "series": series_ticker,
        }

        open_result = discover_open_events(client, series_ticker)
        record["open_events"] = open_result
        record["recent_settlement"] = fetch_recent_settlement(client, series_ticker)
        record["nowcast"] = fetch_nowcast(series_key)

        open_ok = (
            open_result["status"] == "ok"
            and bool(open_result["events"])
            and all(e["completeness_ok"] for e in open_result["events"]))
        settlement_ok = record["recent_settlement"]["status"] in (
            "settled", "no_settled_events", "pending")
        record["pass_complete"] = open_ok and settlement_ok
        n_complete += int(record["pass_complete"])
        lines.append(canonical_json(record))

    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_series": len(series), "n_complete": n_complete,
    }
    if lines:
        tape_dir.mkdir(parents=True, exist_ok=True)
        out_path = tape_dir / f"dt={day}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
        summary["path"] = str(out_path)

    print(f"[econ_prints] {capture_id}: {summary['n_series']} series, "
          f"{n_complete} pass-complete")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Econ-print capture (read-only)")
    ap.add_argument("--series", nargs="*", default=None,
                    help="cap series keys per pass, e.g. --series cpi_mom gdp (offline/dev use)")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    series = {k: SERIES[k] for k in args.series} if args.series else None
    run(min_interval=args.min_interval, series=series)
    return 0


if __name__ == "__main__":
    sys.exit(main())
