"""Full-depth L2 order-book snapshot collector (READ-ONLY) — the forward tape S6 needs.

Strategy candidate S6 (inventory-aware market-making) can't even estimate order-arrival
intensity without a forward record of the *full* bid ladder over time — not just the BBO the
sports/crypto collectors already persist, but every price level and its resting size. Kalshi
does NOT archive L2 depth history, so (lesson L11) an un-collected snapshot is lost forever;
this collector starts accumulating that history now.

Scope — deliberately NARROW to stay off the 3GB-RSS rake (lesson L10: Kalshi's open-market
universe is 10,000+ and an unbounded `/markets` pull once blew past 3GB). We do NOT re-sweep
the platform. We snapshot depth ONLY for the tickers the sibling collectors
(`collection/sports_pairs.py`, `collection/crypto_hourly.py`) already discovered THIS pass —
the caller (hourly_pass, tests) passes that exact list in as `tickers`. `max_tickers` caps the
per-pass fetch budget regardless, carrying an honest `truncated` flag when the cap bites.

Reuse — this module reinvents nothing:
  * `collection.normalize.normalize_snapshot(ticker, ob)` (PURE, already generic — NOT
    weather-specific) turns a raw Kalshi `orderbook_fp` dict into
    {yes_bids, no_bids, best_yes_bid, best_no_bid, best_yes_ask, best_no_ask, depth}. Kalshi
    posts bids-only per outcome, so the tradeable ask on one side is the complement of the
    other side's best bid — that arithmetic lives once, in normalize.py.
  * The fetch pattern is copied verbatim from `collection/capture_orderbooks.py`:
    `client.get_text(ORDERBOOK_PATH.format(ticker=ticker))` -> `orderbook_fp` -> normalize.

Source tags (CLAUDE.md trust-default + Hard Rules #3/#4): a LIVE order-book read is a genuine
fillable quote, not a model, so each record tags its ask fields `real_ask` and its bid fields
`real_bid` (an explicit tag — untagged defaults to `synthetic` per project convention). Note:
`real_bid` is not in the canonical DB enum (real_ask/broker_truth/midpoint/synthetic) because
that enum gates synthetic-vs-real P&L columns; a resting bid is a distinct, equally-real
fillable side and is tagged as such so a downstream consumer never conflates the two ladders.

Honest completeness (same discipline as every other `collection/` module): the passed-in
`tickers` set is the EXPECTED set; a per-ticker orderbook fetch that raises is recorded as a
DROP (added to `dropped`, never silently absorbed), lowering `n_captured` below `n_expected`
so `completeness_ok` goes False. A throttled/truncated response can therefore never masquerade
as a complete capture.

HONEST CADENCE CAVEAT: the recurring collector cron in this project is hard-capped at an
HOURLY minimum interval (a real S9 lead-lag finding). Order-arrival-intensity estimation
ideally wants continuous order-flow; hourly depth SNAPSHOTS are coarse for that. This collector
gives S6 a repeated-snapshot depth time-series (resting-liquidity shape and its hour-over-hour
drift), NOT a continuous message-level order-flow tape. Treat any intensity estimate built on
this tape as snapshot-sampled, and say so.

Run one pass (standalone / dev):
    python -m collection.orderbook_depth --tickers KXWCGAME-...-USA KXBTC-...-T69300
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from collection.normalize import normalize_snapshot
from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from validation.v3_market import Kalshi, _load_venue_cfg

TAPE = REPO_ROOT / "tape" / "orderbook_depth"
ORDERBOOK_PATH = "/markets/{ticker}/orderbook"

# Per-pass fetch-budget cap (lesson L10). The caller already hands us a bounded, pre-discovered
# ticker list, but we cap defensively regardless and flag when the cap actually bites.
MAX_TICKERS_DEFAULT = 2000


def _snapshot_record(ticker: str, ob: Dict[str, Any], capture_id: str, captured_at: str,
                     raw_sha256: str) -> Dict[str, Any]:
    """Build one tape record from a normalized depth snapshot. `normalize_snapshot` owns the
    bid->opposite-ask complement; we only tag the fields and stamp bitemporal provenance."""
    snap = normalize_snapshot(ticker, ob)
    return {
        "schema_version": "orderbook_depth.v1",
        "capture_id": capture_id,
        "captured_at": captured_at,
        "venue": "kalshi",
        "ticker": ticker,
        # full L2 ladders, best-first (normalize_snapshot's ordering) — [[price, size], ...]
        "yes_bids": snap["yes_bids"],
        "no_bids": snap["no_bids"],
        "best_yes_bid": snap["best_yes_bid"],
        "best_no_bid": snap["best_no_bid"],
        "best_yes_ask": snap["best_yes_ask"],
        "best_no_ask": snap["best_no_ask"],
        "depth": snap["depth"],
        # a live book read is a real fillable quote, not a model (CLAUDE.md Hard Rules #3/#4):
        # ask fields are real_ask, bid fields real_bid.
        "price_source_tags": {"asks": "real_ask", "bids": "real_bid"},
        "raw_sha256": raw_sha256,
    }


def run(tickers: List[str], min_interval: float = 0.2,
        client: Optional[Kalshi] = None, store: Optional[Path] = None,
        max_tickers: int = MAX_TICKERS_DEFAULT) -> Dict[str, Any]:
    """One read-only full-depth capture pass over the pre-discovered `tickers`.

    `client`/`store` are injectable for offline testing. Returns a summary dict
    (capture_id, day, n_expected, n_captured, n_lines, completeness_ok, truncated, dropped,
    path). An empty ticker list is a valid no-op (no client is built, no network touched) —
    it returns completeness_ok True with zero lines.
    """
    store = Path(store) if store is not None else TAPE

    # dedupe while preserving order; the caller may hand overlapping sports+crypto lists
    seen: set = set()
    expected: List[str] = []
    for t in tickers:
        if t and t not in seen:
            seen.add(t)
            expected.append(t)

    truncated = len(expected) > max_tickers
    if truncated:
        expected = expected[:max_tickers]

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    # no tickers -> genuine no-op, never build a client (keeps offline callers off the network)
    if not expected:
        return {
            "capture_id": capture_id, "day": day, "captured_at": captured_at,
            "n_expected": 0, "n_captured": 0, "n_lines": 0,
            "completeness_ok": True, "truncated": truncated, "dropped": [], "path": None,
        }

    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)

    lines: List[str] = []
    captured: List[str] = []
    dropped: List[str] = []
    for ticker in expected:
        try:
            text = client.get_text(ORDERBOOK_PATH.format(ticker=ticker))
        except Exception:            # a failed fetch is a DROP -> lowers completeness, never hidden
            dropped.append(ticker)
            continue
        ob = (json.loads(text) or {}).get("orderbook_fp") or {}
        raw_sha256 = sha256_hex(text.encode("utf-8"))
        record = _snapshot_record(ticker, ob, capture_id, captured_at, raw_sha256)
        captured.append(ticker)
        lines.append(canonical_json(record))

    completeness_ok = (len(captured) == len(expected)) and not truncated

    path: Optional[str] = None
    if lines:
        store.mkdir(parents=True, exist_ok=True)
        out_path = store / f"dt={day}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
        path = str(out_path)

    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_expected": len(expected), "n_captured": len(captured), "n_lines": len(lines),
        "completeness_ok": completeness_ok, "truncated": truncated,
        "dropped": dropped, "path": path,
    }
    print(f"[orderbook_depth] {capture_id}: {len(captured)}/{len(expected)} books captured, "
          f"{len(dropped)} dropped, completeness {'ok' if completeness_ok else 'FAIL'}"
          + (" (TRUNCATED)" if truncated else ""))
    if dropped:
        print(f"[orderbook_depth] WARN dropped {len(dropped)} ticker(s) -> completeness_ok=False",
              file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Full-depth L2 orderbook snapshot capture (read-only)")
    ap.add_argument("--tickers", nargs="*", default=[],
                    help="explicit ticker list to snapshot depth for (pre-discovered by a "
                         "sibling collector; this module never sweeps the platform)")
    ap.add_argument("--min-interval", type=float, default=0.2)
    ap.add_argument("--max-tickers", type=int, default=MAX_TICKERS_DEFAULT)
    args = ap.parse_args(argv)
    run(tickers=args.tickers, min_interval=args.min_interval, max_tickers=args.max_tickers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
