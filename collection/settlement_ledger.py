"""collection.settlement_ledger — systematic, append-only settlement-truth harvester
(READ-ONLY, FREE/unauthenticated).

LOOP-QUEUE.md Q45 (GOAL.md Phase-1 M1b): every backtest's y-variable is the settlement
label — did a market resolve yes/no, and (its companion features) at what terminal volume /
open interest. Until now that truth was captured only as four ad-hoc one-shot per-probe
caches (`tape/q26_settlement_cache/settlement.json`, `q27_`, `q29_`, `q30_`), each written by
a single probe for itself. Kalshi purges settled `/markets` data ~60 days after close (lesson
L11), so any settlement history not migrated onto a recurring tape is lost forever the day it
ages out. This module replaces those ad-hoc caches with ONE systematic, daily-growing,
append-only tape family: `tape/settlement_ledger/dt=<capture-day>.jsonl`.

Enumeration (judgment call — see report): the queue text names "`/events?status=settled`
joined to per-market settlement fields". A live probe found the platform-wide
`/events?status=settled&with_nested_markets=true` response returns EMPTY nested `markets`
arrays (the per-market settlement fields we need — result / settlement_value / volume /
open_interest — are not carried on the event object, and would require one extra
`/markets?event_ticker=...` call per event, i.e. ~1.7k extra calls per pass: exactly the
unbounded expansion lesson L10 warns against). The public `/markets?status=settled` endpoint —
the SAME settled-markets endpoint the four probe caches already call, just without a
series filter — returns every per-market settlement field directly in one bounded, paginated
sweep. So this harvester paginates `/markets?status=settled` platform-wide, reusing the
established `get_text` + cursor-pagination + `MAX_SETTLED_MARKETS` cap pattern from
`collection/weather_actuals._fetch_settled_markets` / `collection/sports_history`.

Trust / provenance (CLAUDE.md trust-default; Hard Rule #4): a settlement `result` +
`settlement_value` is Kalshi's OWN reported settlement record — real, not modeled — so it is
tagged `price_source_tag: "broker_truth"`, never `synthetic`. Bitemporal: each line carries
`captured_at` (fetch instant) + the market's own `close_time` (when it settled); the raw bytes
of every settled page are sha256-bound in the summary.

Binary-only filter (load-bearing — lesson L52): Kalshi settlement results are NOT always
binary. Some markets settle `result: "scalar"`, not `yes`/`no`. Those are filtered OUT of the
ledger explicitly and counted (`n_scalar_dropped`) — never allowed to pass silently as a
yes/no label downstream. A market that is listed settled but carries no finalized result yet
(empty result string) is `pending` — counted, but NOT a drop and NOT written as a label.

Honest completeness (same posture as `collection/weather_actuals.py`):
  * A scalar market filtered out is a deliberate structural filter, NOT a completeness failure.
  * A `pending` (result not yet posted) market is NOT a drop and does not gate completeness.
  * A per-market parse exception DOES lower `completeness_ok` (an unexpected failure is a failure).
  * Hitting the `MAX_SETTLED_MARKETS` cap sets `markets_truncated=True` and lowers
    `completeness_ok` — we never silently claim full coverage (lesson L10).

Dedup / append-only: the tape is append-only (never rewrite/reorder existing lines). Because
Kalshi keeps listing a settled market for ~60 days, a naive daily re-pull would append the
same ~5k rows every day. So each pass first loads the set of `(ticker, close_time, result,
settlement_value)` keys already present ANYWHERE in the family and appends ONLY genuinely-new
tuples — idempotent, and it keeps existing lines untouched. `n_new` / `n_duplicate_skipped`
are reported honestly.

Migration (one-time fold, non-destructive — lesson L11): `migrate_caches()` reads the four
existing `qNN_settlement_cache/settlement.json` blobs, converts each entry to a ledger record
(their `result` / `close_time` / `event_ticker` / `series`; they predate the volume/OI/
settlement-value capture so those fields are `None`), applies the SAME scalar filter, and
appends the new keys into the ledger family deduped by the same key. The old cache files are
NEVER deleted (other scripts may still read them) — their content is folded in so nothing is
orphaned.

Run one pass:
    python -m collection.settlement_ledger
    python -m collection.settlement_ledger --limit 500        # cap the pull (dev/live-smoke)
    python -m collection.settlement_ledger --migrate          # also fold the 4 legacy caches
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT

TAPE = REPO_ROOT / "tape" / "settlement_ledger"

# Defensive cap on the platform-wide settled pull (lesson L10: Kalshi's open+settled universe
# is 10k+ and an unbounded /markets pull once blew 3GB RSS). Matches the guardrail pattern
# collection/weather_actuals.MAX_SETTLED_MARKETS already uses. A daily pass captures the most
# recently-settled slice; anything beyond the cap sets markets_truncated and lowers completeness.
MAX_SETTLED_MARKETS = 5000

BINARY_RESULTS = ("yes", "no")

# The four legacy per-probe caches to fold into the systematic family (non-destructive).
LEGACY_CACHE_PATHS = [
    REPO_ROOT / "tape" / "q26_settlement_cache" / "settlement.json",
    REPO_ROOT / "tape" / "q27_settlement_cache" / "settlement.json",
    REPO_ROOT / "tape" / "q29_settlement_cache" / "settlement.json",
    REPO_ROOT / "tape" / "q30_settlement_cache" / "settlement.json",
]

SettleKey = Tuple[Optional[str], Optional[str], Optional[str], Optional[float]]


# --------------------------------------------------------------------------- #
# field parsing — Kalshi's settled /markets object uses `_fp` / `_dollars` string suffixes
# --------------------------------------------------------------------------- #
def _to_float(val: Any) -> Optional[float]:
    """Parse a Kalshi `_fp` / `_dollars` string field to float; '', None, or unparseable -> None
    (an absent number is honestly None, never a fabricated 0)."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _series_of(ticker: str, event_ticker: str) -> Optional[str]:
    """Best-effort series prefix (the token before the first '-'); not part of the dedup key,
    just a convenience feature. Prefers the event ticker's prefix."""
    src = event_ticker or ticker or ""
    return src.split("-", 1)[0] if "-" in src else (src or None)


def _record_from_market(m: Dict[str, Any], captured_at: str, capture_id: str,
                        raw_sha256: Optional[str]) -> Dict[str, Any]:
    """One ledger record from a Kalshi settled /markets object. `result` +
    `settlement_value` are Kalshi's own reported truth -> broker_truth. Terminal `volume` /
    `open_interest` are the label's companion features most backtests join on."""
    ticker = m.get("ticker")
    event_ticker = m.get("event_ticker") or ""
    return {
        "schema_version": "settlement_ledger.v1",
        "capture_id": capture_id,
        "captured_at": captured_at,
        "venue": "kalshi",
        "ticker": ticker,
        "event_ticker": event_ticker or None,
        "series": _series_of(ticker or "", event_ticker),
        "title": m.get("title"),
        "close_time": m.get("close_time"),
        "settlement_ts": m.get("settlement_ts"),
        "result": m.get("result"),
        "settlement_value": _to_float(m.get("settlement_value_dollars")),
        "expiration_value": (m.get("expiration_value") or None),
        "volume": _to_float(m.get("volume_fp")),
        "open_interest": _to_float(m.get("open_interest_fp")),
        "is_provisional": m.get("is_provisional"),
        "price_source_tag": "broker_truth",
        "raw_sha256": raw_sha256,
        "source": "live_settled_markets",
    }


def _key(rec: Dict[str, Any]) -> SettleKey:
    """The dedup key the queue defines: (ticker, close_time, result, settlement_value)."""
    return (rec.get("ticker"), rec.get("close_time"), rec.get("result"),
            rec.get("settlement_value"))


# --------------------------------------------------------------------------- #
# bounded platform-wide settled pull (get_text so the sha256 binds to bytes on the wire)
# --------------------------------------------------------------------------- #
def fetch_settled_markets(client, max_markets: int = MAX_SETTLED_MARKETS
                          ) -> Tuple[List[Dict], List[str], bool]:
    """Paginate `/markets?status=settled` platform-wide, bounded by `max_markets`. Returns
    (markets, raw_pages, truncated). Stops at the cap with `truncated=True` (lesson L10)."""
    markets: List[Dict] = []
    raw_pages: List[str] = []
    truncated = False
    cursor: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"status": "settled", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        text = client.get_text("/markets", **params)
        raw_pages.append(text)
        j = json.loads(text)
        items = j.get("markets") or []
        markets.extend(items)
        if len(markets) >= max_markets:
            markets = markets[:max_markets]
            truncated = True
            break
        cursor = j.get("cursor")
        if not cursor or not items:
            break
    return markets, raw_pages, truncated


# --------------------------------------------------------------------------- #
# existing-key index (append-only dedup across the whole family)
# --------------------------------------------------------------------------- #
def _load_existing_keys(store: Path) -> Set[SettleKey]:
    """Every (ticker, close_time, result, settlement_value) key already present ANYWHERE in the
    ledger family. Used so a pass appends only genuinely-new tuples (idempotent, append-only —
    existing lines are never touched)."""
    keys: Set[SettleKey] = set()
    if not store.exists():
        return keys
    for fp in sorted(store.glob("dt=*.jsonl")):
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                keys.add(_key(rec))
    return keys


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
# one systematic harvest pass
# --------------------------------------------------------------------------- #
def run(min_interval: float = 0.25, client=None, store: Optional[Path] = None,
        max_markets: int = MAX_SETTLED_MARKETS, limit: Optional[int] = None,
        also_migrate: bool = False) -> Dict[str, Any]:
    """One read-only settlement-ledger harvest pass.

    `client`/`store` are injectable for fully offline testing; in production they default to the
    throttled live Kalshi client and the real tape store. `limit` caps the pull (dev/live-smoke,
    overrides `max_markets` when smaller). Returns a summary
    (`n_pulled`/`n_binary`/`n_scalar_dropped`/`n_pending`/`n_new`/`n_duplicate_skipped`/
    `markets_truncated`/`n_parse_errors`/`completeness_ok`) — hourly_pass reads `completeness_ok`.
    """
    store = Path(store) if store is not None else TAPE
    cap = min(limit, max_markets) if limit is not None else max_markets
    if client is None:
        from validation.v3_market import Kalshi, _load_venue_cfg
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    markets, raw_pages, truncated = fetch_settled_markets(client, cap)
    raw_sha256 = sha256_hex("".join(raw_pages)) if raw_pages else None

    existing = _load_existing_keys(store)
    seen_this_pass: Set[SettleKey] = set()
    lines: List[str] = []
    n_binary = n_scalar_dropped = n_pending = n_other = n_parse_errors = 0
    n_new = n_duplicate_skipped = 0

    for m in markets:
        try:
            result = m.get("result")
            if result == "scalar":
                n_scalar_dropped += 1
                continue
            if not result:                      # settled-listed but no finalized label yet
                n_pending += 1
                continue
            if result not in BINARY_RESULTS:    # unexpected non-binary label -> not a yes/no drop
                n_other += 1
                continue
            n_binary += 1
            rec = _record_from_market(m, captured_at, capture_id, raw_sha256)
            k = _key(rec)
            if k in existing or k in seen_this_pass:
                n_duplicate_skipped += 1
                continue
            seen_this_pass.add(k)
            lines.append(canonical_json(rec))
            n_new += 1
        except Exception as exc:                # a single bad market never kills the pass
            n_parse_errors += 1
            print(f"[settlement_ledger] parse error on {m.get('ticker')}: {exc}",
                  file=sys.stderr)

    path = _append_lines(store, day, lines)

    migration: Optional[Dict[str, Any]] = None
    if also_migrate:
        migration = migrate_caches(store=store, client=None, day=day,
                                   captured_at=captured_at, capture_id=capture_id)

    # honest completeness: truncation or a parse error lowers it; a scalar filter or a
    # not-yet-posted pending market does NOT.
    completeness_ok = (not truncated) and (n_parse_errors == 0)

    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_pulled": len(markets),
        "n_binary": n_binary,
        "n_scalar_dropped": n_scalar_dropped,
        "n_pending": n_pending,
        "n_other_nonbinary": n_other,
        "n_new": n_new,
        "n_duplicate_skipped": n_duplicate_skipped,
        "n_parse_errors": n_parse_errors,
        "markets_truncated": truncated,
        "completeness_ok": completeness_ok,
        "raw_sha256": raw_sha256,
        "path": path,
        "migration": migration,
    }
    print(f"[settlement_ledger] {capture_id}: pulled {len(markets)}, "
          f"binary {n_binary} (new {n_new}, dup {n_duplicate_skipped}), "
          f"scalar-dropped {n_scalar_dropped}, pending {n_pending}, "
          f"parse-errors {n_parse_errors}, "
          f"completeness {'ok' if completeness_ok else 'FAIL'}"
          + (" (TRUNCATED)" if truncated else ""))
    if truncated:
        print(f"[settlement_ledger] WARN pull hit the {cap}-market cap "
              f"-> markets_truncated=True, completeness_ok=False", file=sys.stderr)
    if n_parse_errors:
        print(f"[settlement_ledger] WARN {n_parse_errors} per-market parse error(s) "
              f"-> completeness_ok=False", file=sys.stderr)
    return summary


# --------------------------------------------------------------------------- #
# one-time migration of the four legacy per-probe caches (non-destructive)
# --------------------------------------------------------------------------- #
def _record_from_legacy(ticker: str, entry: Dict[str, Any], captured_at: str,
                        capture_id: str, cache_name: str) -> Dict[str, Any]:
    """A ledger record from a legacy qNN_settlement_cache entry. Those caches predate the
    volume/OI/settlement-value capture, so those fields are honestly `None`, not fabricated."""
    event_ticker = entry.get("event_ticker") or ""
    return {
        "schema_version": "settlement_ledger.v1",
        "capture_id": capture_id,
        "captured_at": captured_at,
        "venue": "kalshi",
        "ticker": ticker,
        "event_ticker": event_ticker or None,
        "series": entry.get("series") or _series_of(ticker, event_ticker),
        "title": None,
        "close_time": entry.get("close_time"),
        "settlement_ts": None,
        "result": entry.get("result"),
        "settlement_value": None,           # legacy caches never captured the settlement value
        "expiration_value": None,
        "volume": None,
        "open_interest": None,
        "is_provisional": None,
        "price_source_tag": "broker_truth",
        "raw_sha256": None,
        "source": f"migrated:{cache_name}",
    }


def migrate_caches(store: Optional[Path] = None,
                   cache_paths: Optional[List[Path]] = None,
                   client=None, day: Optional[str] = None,
                   captured_at: Optional[str] = None,
                   capture_id: Optional[str] = None) -> Dict[str, Any]:
    """Fold the four legacy qNN_settlement_cache blobs into the systematic family, deduped by
    the same (ticker, close_time, result, settlement_value) key. Non-destructive: the old files
    are read, never modified/deleted. Applies the same scalar filter (lesson L52). `client` is
    unused (kept for signature symmetry with run()) — migration is a pure local file fold."""
    store = Path(store) if store is not None else TAPE
    paths = cache_paths if cache_paths is not None else LEGACY_CACHE_PATHS
    cap_ts = datetime.now(timezone.utc)
    captured_at = captured_at or cap_ts.isoformat()
    capture_id = capture_id or cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = day or cap_ts.strftime("%Y-%m-%d")

    existing = _load_existing_keys(store)
    before = len(existing)
    seen_this_pass: Set[SettleKey] = set()
    lines: List[str] = []
    per_cache: Dict[str, Dict[str, int]] = {}
    n_scalar_dropped = n_pending = n_new = n_duplicate_skipped = n_missing = 0

    for cp in paths:
        cache_name = cp.parent.name if cp.name == "settlement.json" else cp.name
        stats = {"markets": 0, "new": 0, "scalar_dropped": 0, "pending": 0, "dup": 0}
        if not cp.exists():
            n_missing += 1
            per_cache[cache_name] = {**stats, "missing": 1}
            continue
        payload = json.loads(cp.read_text(encoding="utf-8"))
        markets = payload.get("markets") or {}
        for ticker, entry in markets.items():
            stats["markets"] += 1
            result = entry.get("result")
            if result == "scalar":
                n_scalar_dropped += 1
                stats["scalar_dropped"] += 1
                continue
            if not result or result not in BINARY_RESULTS:
                n_pending += 1
                stats["pending"] += 1
                continue
            rec = _record_from_legacy(ticker, entry, captured_at, capture_id, cache_name)
            k = _key(rec)
            if k in existing or k in seen_this_pass:
                n_duplicate_skipped += 1
                stats["dup"] += 1
                continue
            seen_this_pass.add(k)
            lines.append(canonical_json(rec))
            n_new += 1
            stats["new"] += 1
        per_cache[cache_name] = stats

    path = _append_lines(store, day, lines)
    after = before + n_new
    result = {
        "n_caches": len(paths), "n_missing": n_missing,
        "keys_before": before, "keys_after": after,
        "n_new": n_new, "n_duplicate_skipped": n_duplicate_skipped,
        "n_scalar_dropped": n_scalar_dropped, "n_pending_or_nonbinary": n_pending,
        "per_cache": per_cache, "path": path,
    }
    print(f"[settlement_ledger:migrate] {len(paths)} caches -> ledger: "
          f"keys {before} -> {after} (+{n_new} new, {n_duplicate_skipped} dup, "
          f"{n_scalar_dropped} scalar-dropped, {n_missing} missing)")
    return result


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Systematic settlement-ledger harvester (read-only, append-only)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap the settled-markets pull this pass (dev/live-smoke)")
    ap.add_argument("--min-interval", type=float, default=0.25,
                    help="min seconds between live fetches (politeness)")
    ap.add_argument("--migrate", action="store_true",
                    help="also fold the 4 legacy qNN_settlement_cache blobs into the ledger")
    ap.add_argument("--migrate-only", action="store_true",
                    help="ONLY run the legacy-cache migration (no live pull)")
    args = ap.parse_args(argv)
    if args.migrate_only:
        migrate_caches()
        return 0
    run(min_interval=args.min_interval, limit=args.limit, also_migrate=args.migrate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
