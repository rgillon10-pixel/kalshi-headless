"""collection.monitor_poll — public REST fallback for the 60s market snapshot (READ-ONLY).

Kalshi's public REST market data needs NO account; only the WebSocket gates on an API key.
This module keeps the monitor's 60-second price floor alive whenever the WS tape is not
flowing (dead key, outage, resubscribe gap): one cron pass per minute reads the SAME
subscription set the WS daemon uses (`config/ws_depth_tickers.txt`) and captures top-of-book
for all of it in ~2 batched `GET /markets?tickers=...` calls.

Self-gating fallback, not a second source of truth: if `tape/ws_depth/` has been written in
the last `WS_FRESH_SEC` seconds the pass is a no-op (`status: skipped_ws_fresh`, zero
network). The moment the WS key lands and delta tape flows, this collector stands down by
itself; if the WS dies again, the next minute's pass takes back over. Layer 2 reads both
families out of the same `snapshots` DB table and never has to care which one was awake.

Scope discipline: BBO + at-touch sizes only (what the listing carries inline). No per-ticker
`/orderbook` calls — top-5 L2 depth is the WS daemon's job; polling 200 books per minute
would hammer the API for depth the fallback doesn't need. The house tape contract applies:
canonical JSONL to `tape/monitor_poll/dt=YYYY-MM-DD.jsonl`, bitemporal stamps, per-page
`raw_sha256`, `price_source_tag: real_ask` (resting quotes), counted missing tickers, and a
summary line with `completeness_ok`.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from core.kalshi_fields import parse_kalshi_numeric as _to_float
from core.pricing import top_of_book_quote
from collection.ws_depth import load_tickers

SCHEMA_VERSION = "monitor_poll.snapshot60.v1"
TAPE = REPO_ROOT / "tape" / "monitor_poll"
WS_TAPE = REPO_ROOT / "tape" / "ws_depth"

BATCH_SIZE = 100          # tickers per /markets?tickers= call (2 calls for the 200 cap)
WS_FRESH_SEC = 180        # WS tape younger than this => the poller stands down


def ws_tape_age_seconds(now_ts: float, ws_tape: Path = WS_TAPE) -> Optional[float]:
    """Age of the newest ws_depth day file, or None if none exists."""
    try:
        newest = max(f.stat().st_mtime for f in ws_tape.glob("dt=*"))
    except (ValueError, OSError):
        return None
    return now_ts - newest


def _record(m: Dict[str, Any], captured_at: str, capture_id: str,
            raw_sha256: str) -> Dict[str, Any]:
    yes_bid = _to_float(m.get("yes_bid_dollars"))
    no_bid = _to_float(m.get("no_bid_dollars"))
    # Hard Rule #3 site: ask/mid/spread derivation lives ONLY in core.pricing. Derived from
    # the bid ladders exactly like the WS snapshot60, so the two families agree by identity.
    yes_ask, mid, spread = top_of_book_quote(yes_bid, no_bid)
    return {
        "schema_version": SCHEMA_VERSION,
        "capture_id": capture_id,
        "captured_at": captured_at,
        "venue": "kalshi",
        "channel": "rest_poll",
        "ticker": m.get("ticker"),
        "yes_bid": yes_bid,
        "no_bid": no_bid,
        "yes_ask": yes_ask,
        "mid": mid,
        "spread": spread,
        # at-touch sizes only (inline in the listing) — NOT L2 depth
        "yes_bid_size": _to_float(m.get("yes_bid_size_fp")),
        "yes_ask_size": _to_float(m.get("yes_ask_size_fp")),
        "last_price": _to_float(m.get("last_price_dollars")),
        "volume_24h": _to_float(m.get("volume_24h_fp")),
        "open_interest": _to_float(m.get("open_interest_fp")),
        "close_time": m.get("close_time"),
        "price_source_tag": "real_ask",
        "raw_sha256": raw_sha256,
    }


def run(client=None, store: Optional[Path] = None, tickers: Optional[List[str]] = None,
        ws_tape: Path = WS_TAPE, min_interval: float = 0.25,
        now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    captured_at, capture_id = now.isoformat(), now.strftime("%Y%m%dT%H%M%S%fZ")

    age = ws_tape_age_seconds(now.timestamp(), ws_tape)
    if age is not None and age < WS_FRESH_SEC:
        summary = {"status": "skipped_ws_fresh", "ws_tape_age_s": round(age, 1),
                   "n_lines": 0}
        print(f"[monitor_poll] {canonical_json(summary)}", flush=True)
        return summary

    if tickers is None:
        tickers, _truncated = load_tickers()
    if not tickers:
        summary = {"status": "no_tickers", "n_lines": 0}
        print(f"[monitor_poll] {canonical_json(summary)}", flush=True)
        return summary

    if client is None:
        from validation.v3_market import Kalshi, _load_venue_cfg
        client = Kalshi(_load_venue_cfg()["api_base"], min_interval=min_interval)

    store = Path(store) if store is not None else TAPE
    lines: List[str] = []
    returned = set()
    n_calls = 0
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        text = client.get_text("/markets", tickers=",".join(batch), limit=len(batch))
        n_calls += 1
        page_sha = sha256_hex(text.encode("utf-8"))
        for m in json.loads(text).get("markets") or []:
            returned.add(m.get("ticker"))
            lines.append(canonical_json(_record(m, captured_at, capture_id, page_sha)))

    # a subscribed ticker the listing no longer returns (closed/settled mid-hour) is
    # COUNTED, never silently absent — the next scope pass rotates it out
    n_missing = len([t for t in tickers if t not in returned])
    summary = {
        "schema_version": "monitor_poll.summary.v1",
        "capture_id": capture_id, "captured_at": captured_at, "status": "polled",
        "n_tickers": len(tickers), "n_lines": len(lines), "n_missing": n_missing,
        "n_calls": n_calls, "ws_tape_age_s": None if age is None else round(age, 1),
        "completeness_ok": n_missing == 0,
    }
    store.mkdir(parents=True, exist_ok=True)
    day = now.strftime("%Y-%m-%d")
    with open(store / f"dt={day}.jsonl", "a", encoding="utf-8") as fh:
        fh.write("".join(ln + "\n" for ln in lines))
        fh.write(canonical_json(summary) + "\n")
    print(f"[monitor_poll] {canonical_json(summary)}", flush=True)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Public REST fallback for the 60s monitor snapshot (read-only).")
    ap.add_argument("--min-interval", type=float, default=0.25)
    args = ap.parse_args(argv)
    summary = run(min_interval=args.min_interval)
    return 0 if summary.get("completeness_ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
