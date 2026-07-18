"""collection.universe_sweep — full-universe top-of-book snapshot (READ-ONLY, FREE/unauthenticated).

LOOP-QUEUE.md Q46 (GOAL.md Phase-1 M2): the breadth spine. Every other collector in this
package captures a NARROW, curated slice (a sport, a crypto ladder, the weather cities, the
settled labels). Nobody systematically enumerates the ~10k OPEN Kalshi markets that exist at
any instant. This module is that enumeration: one bounded, paginated sweep of the ENTIRE open
universe, writing one top-of-book snapshot line per market.

Enumeration: `GET /markets` accepts `status`/`limit`/`cursor` WITHOUT a `series_ticker`
(kb/kalshi-api/02-rest-and-websocket.md:12), so a single paginated pass over
`/markets?status=open&limit=1000` walks the whole platform — ~10-15 pages, i.e. WELL under the
`MAX_CALLS=20` cap. This is NOT a per-series loop and NOT per-market orderbook calls: every
field we keep is returned INLINE per market by the listing itself (confirmed live 2026-07-17).

Top-of-book ONLY (scope discipline): we capture the inline best-bid/best-offer + last price +
volume + open interest the listing already carries. We DO NOT fetch `/markets/{ticker}/
orderbook` — L2 depth stays the focused `orderbook_depth` / Phase-2 lane. No scope-creep.

Field names (lesson L90 — verified live for OPEN markets 2026-07-17): Kalshi's open `/markets`
object carries prices as `_dollars`-suffixed STRING fields (`yes_ask_dollars`, `no_bid_dollars`,
`last_price_dollars`, ...) and sizes/volumes as `_fp`-suffixed strings (`volume_fp`,
`open_interest_fp`, `yes_ask_size_fp`, ...); the bare `yes_ask`/`volume`/... keys come back
null. We parse the suffixed fields to floats and store them under their natural short names.

Trust / provenance (CLAUDE.md trust-default; Hard Rule #3): a resting `yes_ask` on the book is a
FILLABLE ask price, not a synthetic probability — so every line is tagged
`price_source_tag: "real_ask"`. We store the raw top-of-book verbatim and do NO arithmetic on it
here: no normalization, no `bracket_sum` divisor, no derived probability (that transform lives
only in core.pricing, per Hard Rule #3). This is a raw snapshot; downstream consumers normalize.
The raw bytes of every page are sha256-bound per line for provenance (same discipline as
sports_pairs / settlement_ledger / capture_orderbooks).

Snapshot tape (NOT deduped): unlike settlement_ledger (a growing set of immutable labels, deduped
by key), this is a time-series of BBO SNAPSHOTS — the same ticker legitimately reappears every
pass with different prices. So each pass appends a fresh capture_id-stamped snapshot for every
open market; we never dedup across passes. Append-only, one file per UTC day
(`tape/universe_sweep/dt=<day>.jsonl`), multiple snapshots per day at the 0/6/12/18 cadence.

Honest completeness (lesson L10): `completeness_ok` is True only if pagination EXHAUSTED the
cursor within the `MAX_CALLS` cap. If we hit the call cap with the cursor still active
(partial pagination), `truncated=True` and `completeness_ok=False` — we never silently claim
full coverage. A per-market parse exception also lowers `completeness_ok`. Nothing else does.

Coverage cross-check: if the listing ever exposes a platform-wide `total` count we report
`coverage = captured / total` (`coverage_basis="total_count"`); today it does not (top-level
keys are just `cursor`/`markets`), so a clean cursor-exhaustion asserts full coverage
(`coverage=1.0`, `coverage_basis="cursor_exhausted"`); a truncated sweep reports
`coverage=None` (`coverage_basis="truncated"`). The caller can additionally cross-check
union-count stability across immediate re-calls (done in the live-validation smoke, not baked
into every pass so we don't double the API cost).

Run one pass:
    python -m collection.universe_sweep
    python -m collection.universe_sweep --max-calls 5     # dev/live-smoke: cap the sweep
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
from core.kalshi_fields import parse_kalshi_numeric as _to_float

TAPE = REPO_ROOT / "tape" / "universe_sweep"

# The whole open universe is ~10k markets -> ~10-15 pages at limit=1000. The <=20-call cap is the
# queue's hard bound (a bounded breadth sweep, never the unbounded 10k per-market pull L10 warns
# against). Hitting the cap with an active cursor is honest partial coverage, not full.
MAX_CALLS = 20
PAGE_LIMIT = 1000


# field parsing (`_to_float`) — Kalshi's open /markets object uses `_dollars` / `_fp` string
# suffixes (L90); the shared parser lives in `core/kalshi_fields.py` (L100), imported above
# under this module's existing internal name so callers/tests are unaffected.


def _series_of(ticker: str, event_ticker: str) -> Optional[str]:
    """Best-effort series prefix (token before the first '-'); prefers the event ticker."""
    src = event_ticker or ticker or ""
    return src.split("-", 1)[0] if "-" in src else (src or None)


def _record_from_market(m: Dict[str, Any], captured_at: str, capture_id: str,
                        raw_sha256: Optional[str]) -> Dict[str, Any]:
    """One top-of-book snapshot record from a Kalshi open /markets object. The best bid/offer
    are REAL resting prices on the book (fillable) -> price_source_tag 'real_ask'. Stored raw:
    NO normalization / NO derived probability here (Hard Rule #3 — that transform lives only in
    core.pricing). Companion features (volume / open interest / last price / at-touch sizes /
    liquidity) are the inline fields most downstream joins need."""
    ticker = m.get("ticker")
    event_ticker = m.get("event_ticker") or ""
    return {
        "schema_version": "universe_sweep.v1",
        "capture_id": capture_id,
        "captured_at": captured_at,
        "venue": "kalshi",
        "ticker": ticker,
        "event_ticker": event_ticker or None,
        "series": _series_of(ticker or "", event_ticker),
        "title": m.get("title"),
        "market_type": m.get("market_type"),
        "status": m.get("status"),
        "close_time": m.get("close_time"),
        # top-of-book best bid/offer (raw, verbatim, un-normalized) -> real_ask
        "yes_bid": _to_float(m.get("yes_bid_dollars")),
        "yes_ask": _to_float(m.get("yes_ask_dollars")),
        "no_bid": _to_float(m.get("no_bid_dollars")),
        "no_ask": _to_float(m.get("no_ask_dollars")),
        # size resting AT the touch (inline top-of-book size — not L2 depth)
        "yes_bid_size": _to_float(m.get("yes_bid_size_fp")),
        "yes_ask_size": _to_float(m.get("yes_ask_size_fp")),
        # companion features carried inline by the listing
        "last_price": _to_float(m.get("last_price_dollars")),
        "previous_price": _to_float(m.get("previous_price_dollars")),
        "volume": _to_float(m.get("volume_fp")),
        "volume_24h": _to_float(m.get("volume_24h_fp")),
        "open_interest": _to_float(m.get("open_interest_fp")),
        "liquidity": _to_float(m.get("liquidity_dollars")),
        "price_source_tag": "real_ask",
        "raw_sha256": raw_sha256,
        "source": "live_open_markets",
    }


# --------------------------------------------------------------------------- #
# bounded platform-wide open pull (get_text so the sha256 binds to bytes on the wire)
# --------------------------------------------------------------------------- #
def fetch_open_markets(client, max_calls: int = MAX_CALLS, page_limit: int = PAGE_LIMIT
                       ) -> Tuple[List[Dict], List[str], bool, int, Optional[int]]:
    """Paginate `/markets?status=open` platform-wide (no series filter), bounded by `max_calls`.
    Returns (markets, raw_pages, truncated, n_calls, total_hint). `truncated=True` iff we stop
    because the call cap is reached while the cursor is STILL active (honest partial coverage,
    L10). `total_hint` is a platform-wide count if the listing ever exposes one, else None."""
    markets: List[Dict] = []
    raw_pages: List[str] = []
    truncated = False
    n_calls = 0
    total_hint: Optional[int] = None
    cursor: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"status": "open", "limit": page_limit}
        if cursor:
            params["cursor"] = cursor
        text = client.get_text("/markets", **params)
        n_calls += 1
        raw_pages.append(text)
        j = json.loads(text)
        items = j.get("markets") or []
        markets.extend(items)
        if total_hint is None:
            t = j.get("total")
            if isinstance(t, int):
                total_hint = t
        cursor = j.get("cursor")
        if not cursor or not items:      # cursor exhausted -> full coverage of the open universe
            break
        if n_calls >= max_calls:         # cap hit with cursor still active -> honest partial
            truncated = True
            break
    return markets, raw_pages, truncated, n_calls, total_hint


def _append_lines(store: Path, day: str, lines: List[str]) -> Optional[str]:
    if not lines:
        return None
    store.mkdir(parents=True, exist_ok=True)
    out_path = store / f"dt={day}.jsonl"
    with open(out_path, "a", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln + "\n")
    return str(out_path)


# --------------------------------------------------------------------------- #
# one full-universe top-of-book sweep pass
# --------------------------------------------------------------------------- #
def run(min_interval: float = 0.25, client=None, store: Optional[Path] = None,
        max_calls: int = MAX_CALLS, page_limit: int = PAGE_LIMIT) -> Dict[str, Any]:
    """One read-only full-universe top-of-book sweep pass.

    `client`/`store` are injectable for fully offline testing; in production they default to the
    throttled live Kalshi client and the real tape store. Returns a summary
    (`n_markets`/`n_lines`/`n_pulled`/`call_count`/`cursor_exhausted`/`truncated`/`coverage`/
    `coverage_basis`/`total_hint`/`n_parse_errors`/`completeness_ok`) — hourly_pass folds
    `n_markets`/`n_lines` and reads `completeness_ok`.
    """
    store = Path(store) if store is not None else TAPE
    if client is None:
        from validation.v3_market import Kalshi, _load_venue_cfg
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    markets, raw_pages, truncated, n_calls, total_hint = fetch_open_markets(
        client, max_calls, page_limit)
    raw_sha256 = sha256_hex("".join(raw_pages)) if raw_pages else None

    lines: List[str] = []
    n_parse_errors = 0
    for m in markets:
        try:
            rec = _record_from_market(m, captured_at, capture_id, raw_sha256)
            lines.append(canonical_json(rec))
        except Exception as exc:            # a single bad market never kills the sweep
            n_parse_errors += 1
            print(f"[universe_sweep] parse error on {m.get('ticker')}: {exc}", file=sys.stderr)

    path = _append_lines(store, day, lines)
    n_markets = len(lines)
    cursor_exhausted = not truncated

    # honest completeness: partial pagination (cap hit with active cursor) or a parse error
    # lowers it; nothing else does.
    completeness_ok = cursor_exhausted and (n_parse_errors == 0)

    # coverage: prefer the platform total if the listing exposes one; else a clean cursor
    # exhaustion asserts full coverage; a truncated sweep is honestly unknown-but-partial.
    if truncated:
        coverage: Optional[float] = None
        coverage_basis = "truncated"
    elif total_hint:
        coverage = round(n_markets / total_hint, 6)
        coverage_basis = "total_count"
    else:
        coverage = 1.0
        coverage_basis = "cursor_exhausted"

    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_markets": n_markets,
        "n_lines": n_markets,
        "n_pulled": len(markets),
        "call_count": n_calls,
        "cursor_exhausted": cursor_exhausted,
        "truncated": truncated,
        "coverage": coverage,
        "coverage_basis": coverage_basis,
        "total_hint": total_hint,
        "n_parse_errors": n_parse_errors,
        "completeness_ok": completeness_ok,
        "raw_sha256": raw_sha256,
        "path": path,
    }
    print(f"[universe_sweep] {capture_id}: pulled {len(markets)} open markets in {n_calls} call(s), "
          f"wrote {n_markets} snapshot line(s), coverage {coverage} ({coverage_basis}), "
          f"parse-errors {n_parse_errors}, "
          f"completeness {'ok' if completeness_ok else 'FAIL'}"
          + (" (TRUNCATED)" if truncated else ""))
    if truncated:
        print(f"[universe_sweep] WARN hit the {max_calls}-call cap with an active cursor "
              f"-> truncated=True, completeness_ok=False", file=sys.stderr)
    if n_parse_errors:
        print(f"[universe_sweep] WARN {n_parse_errors} per-market parse error(s) "
              f"-> completeness_ok=False", file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Full-universe top-of-book sweep (read-only, append-only)")
    ap.add_argument("--max-calls", type=int, default=MAX_CALLS,
                    help="hard cap on paginated /markets calls this pass (queue bound: <=20)")
    ap.add_argument("--page-limit", type=int, default=PAGE_LIMIT,
                    help="markets per page (Kalshi max 1000)")
    ap.add_argument("--min-interval", type=float, default=0.25,
                    help="min seconds between live fetches (politeness)")
    args = ap.parse_args(argv)
    s = run(min_interval=args.min_interval, max_calls=args.max_calls, page_limit=args.page_limit)
    return 0 if s["completeness_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
