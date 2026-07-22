"""Hyperliquid perpetual funding-history collector (READ-ONLY) — public /info REST.

LOOP-QUEUE.md Q42 part (2) prerequisite (2026-07-17). Q42 part (1) proved Kalshi's
finalized crypto-perp funding prints are a GENUINE ±1bp dead-band/clamp — exactly 0 in
~76% of 8h windows pooled (67% for BTC). The cross-venue thesis needs the OTHER leg: an
off-venue perp whose same-underlying funding is essentially never 0. Hyperliquid is the
natural comparator — its public `/info` endpoint is unauthenticated and reachable from
this sandbox (no API key, no geo-block, unlike Binance from US IPs).

    POST https://api.hyperliquid.xyz/info
    body: {"type":"fundingHistory","coin":"BTC","startTime":<ms epoch>[,"endTime":<ms>]}
    -> JSON array of {"coin","fundingRate":"0.0000125","premium":"...","time":<ms epoch>}

Two things that MUST be respected downstream (documented here so the join can't get them
wrong): (1) Hyperliquid funding is HOURLY (entries ~3600s apart, each rate is per-hour),
whereas Kalshi's perp funding is finalized every 8 HOURS — the join compounds 8 matching
hourly HL rates into an 8h-equivalent, this collector just archives the raw hourly prints.
(2) The endpoint returns at most ~500 entries per call, so a full backfill since the Kalshi
perps launch (2026-06-03) is paginated by advancing `startTime` past the newest returned
`time` until the venue stops returning new rows.

Each finalized hourly print is a venue-computed number, not a fill — tagged `broker_truth`,
exactly the same tagging logic `collection/perp_tape.py` uses for Kalshi's `funding_rates`.

One pass writes ONE JSONL record per coin (a `funding_history` record carrying the full
`prints` list) into `tape/hyperliquid_funding/dt=YYYY-MM-DD.jsonl`. Default scope BTC+ETH
(the two deep Kalshi perps, and part 1's BTC focus); `--coins` widens it. The coin symbol
maps to a Kalshi perp ticker as `KX<COIN>PERP` (BTC->KXBTCPERP); the mapping for the long
tail is left to the join, which is where an ambiguous symbol (kSHIB, HYPE) would surface.

Two run modes (L127/L128 close-out, 2026-07-21):
  * `run` (`--mode backfill`) — the original one-shot paginated backfill since launch. One
    `funding_history`/`mode=backfill` record per coin carrying the FULL prints list.
  * `run_incremental` (`--mode incremental`, the default hourly-pass leg) — a tiny forward
    refresh. Per coin it reads the newest funding-print `time_ms` already on committed tape,
    fetches only from there, and union-appends a record carrying ONLY the genuinely-new
    prints (deduped per-print by `(coin, time_ms)` against everything already archived — an
    append-only add, never a rewrite/reorder of existing lines). A pass with nothing new for
    a coin writes NO line for it (empty-is-data, not a drop, and not an incompleteness); only
    a genuine fetch/parse exception lowers completeness. This is what tracks `perp_tape`'s
    forward cadence so `scripts/q42_crossvenue_funding_join.py` stops silently truncating at
    the 2026-07-17 backfill date. Steady-state cost is 1 short page (~1 new hourly print) per
    coin => 1-2 POSTs per pass; the first post-freeze pass catches the whole gap in one page
    (< PAGE_LIMIT for any gap under ~20 days). Idempotent across the two staggered collectors
    (VPS + cloud) and across re-runs: whichever pass runs first after a new hourly print
    archives it, the next finds nothing new — the per-print dedup makes double-collection a
    no-op, never a duplicate line.

Run one pass / backfill since launch:
    python -m collection.hyperliquid_funding                       # incremental forward refresh (default)
    python -m collection.hyperliquid_funding --mode backfill       # full paginated backfill since launch
    python -m collection.hyperliquid_funding --coins BTC ETH SOL
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import requests

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT

TAPE = REPO_ROOT / "tape" / "hyperliquid_funding"

HL_API_BASE = "https://api.hyperliquid.xyz"

# 2026-06-03T00:00:00Z — the Kalshi perps launch day (BTCPERP live 2026-06-03); HL returns
# "earliest available" for anything at-or-before its own first print, so this is a safe
# lower bound that lines up with the Kalshi funding tape's start.
LAUNCH_MS = int(datetime(2026, 6, 3, tzinfo=timezone.utc).timestamp() * 1000)

# The venue caps a fundingHistory response; we page by advancing startTime. A page shorter
# than this is the natural end-of-data signal (belt-and-suspenders with a no-progress guard).
PAGE_LIMIT = 500

# default deep-liquid scope (matches perp_tape.L2_TICKERS + part-1's BTC focus)
DEFAULT_COINS = ("BTC", "ETH")

# guard against an unexpected non-terminating pager (each page is ~500 hourly rows ~= 20d;
# a full year is < 20 pages/coin — 200 is an absurd ceiling that only trips on a venue bug).
MAX_PAGES = 200


def _f(v: Any) -> Optional[float]:
    """Float or None — a missing/unparseable field stays None (visible), never 0.0."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _iso_from_ms(ms: Any) -> Optional[str]:
    """UTC ISO8601 (…Z) from an epoch-ms int, or None on a bad value."""
    try:
        return (datetime.fromtimestamp(int(ms) / 1000, timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError, OSError):
        return None


def _print_from_entry(e: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one HL funding entry into a persisted print. `funding_time` is the ISO
    render of the venue's ms `time`; `time_ms` is kept verbatim so the join can bucket by
    hour without re-parsing (and so timestamp jitter — HL stamps ~a few ms past :00 — is
    preserved, not silently rounded away here)."""
    ms = e.get("time")
    return {
        "coin": e.get("coin", ""),
        "funding_time": _iso_from_ms(ms),
        "time_ms": int(ms) if isinstance(ms, (int, float)) else None,
        "funding_rate": _f(e.get("fundingRate")),
        "premium": _f(e.get("premium")),
    }


# --------------------------------------------------------------------------- #
# HTTP client — throttled + retrying, mirrors validation.v3_market.Kalshi.get
# --------------------------------------------------------------------------- #
class Hyperliquid:
    """Minimal read-only POST client for Hyperliquid's public /info endpoint."""

    def __init__(self, base: str = HL_API_BASE, min_interval: float = 0.2,
                 max_retries: int = 5, timeout: float = 30.0):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"Content-Type": "application/json",
                               "User-Agent": "kalshi-headless/0.0 (research-collection)"})
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._timeout = timeout
        self._last = 0.0

    def post_info(self, body: Dict[str, Any]) -> Any:
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            gap = time.time() - self._last
            if gap < self._min_interval:
                time.sleep(self._min_interval - gap)
            r = self.s.post(self.base + "/info", json=body, timeout=self._timeout)
            self._last = time.time()
            if r.status_code == 429 or r.status_code >= 500:
                wait = max(float(r.headers.get("Retry-After") or 0), min(2 ** attempt, 16))
                last_exc = requests.HTTPError(f"{r.status_code} on /info {body.get('type')}")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        raise last_exc or requests.HTTPError("exhausted retries on /info")

    def funding_history(self, coin: str, start_ms: int,
                        end_ms: Optional[int] = None) -> List[Dict[str, Any]]:
        body: Dict[str, Any] = {"type": "fundingHistory", "coin": coin, "startTime": int(start_ms)}
        if end_ms is not None:
            body["endTime"] = int(end_ms)
        out = self.post_info(body)
        return out if isinstance(out, list) else []


# --------------------------------------------------------------------------- #
# pagination — pure over an injected fetch callable (offline-testable)
# --------------------------------------------------------------------------- #
def fetch_funding_history(fetch: Callable[[str, int, Optional[int]], List[Dict[str, Any]]],
                          coin: str, start_ms: int = LAUNCH_MS,
                          end_ms: Optional[int] = None) -> Tuple[Dict[str, Any], bool]:
    """Page the full HL hourly funding history for `coin` in [start_ms, end_ms].

    `fetch(coin, start, end) -> list[raw_entry]` is injected so tests never touch the
    network. Pages advance `startTime` past the newest `time` seen; dedup on `time_ms`
    (a page boundary re-serves its edge row). Stops on: empty page, a short page
    (< PAGE_LIMIT = end of data), or no time progress (defensive anti-loop)."""
    seen_ms: set = set()
    prints: List[Dict[str, Any]] = []
    cur = int(start_ms)
    try:
        for _ in range(MAX_PAGES):
            page = fetch(coin, cur, end_ms) or []
            new_max = cur
            added = 0
            for e in page:
                pr = _print_from_entry(e)
                ms = pr["time_ms"]
                if ms is None or ms in seen_ms:
                    continue
                seen_ms.add(ms)
                prints.append(pr)
                added += 1
                if ms > new_max:
                    new_max = ms
            if not page or added == 0 or new_max <= cur:
                break
            if len(page) < PAGE_LIMIT:
                break
            cur = new_max + 1  # advance strictly past the newest row we ingested
    except Exception as exc:  # noqa: BLE001 — a fetch failure is a visible record, not a crash
        return {"status": "fetch_error", "error": str(exc), "coin": coin,
                "start_ms": int(start_ms), "end_ms": end_ms}, False
    prints.sort(key=lambda p: (p["time_ms"] if p["time_ms"] is not None else 0))
    return {
        "status": "ok",
        "coin": coin,
        "start_ms": int(start_ms),
        "end_ms": end_ms,
        "prints": prints,
        "n_prints": len(prints),
        "price_source_tag": "broker_truth",
        "raw_sha256": sha256_hex(canonical_json(prints)),
    }, True


# --------------------------------------------------------------------------- #
# capture
# --------------------------------------------------------------------------- #
def _now_ids() -> Tuple[str, str, str]:
    ts = datetime.now(timezone.utc)
    return ts.strftime("%Y%m%dT%H%M%SZ"), ts.isoformat(), ts.strftime("%Y-%m-%d")


def _write(tape_dir: Path, day: str, lines: List[str]) -> str:
    tape_dir.mkdir(parents=True, exist_ok=True)
    out_path = tape_dir / f"dt={day}.jsonl"
    with open(out_path, "a", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln + "\n")
    return str(out_path)


def run(coins: Sequence[str] = DEFAULT_COINS, start_ms: int = LAUNCH_MS,
        end_ms: Optional[int] = None, client: Optional[Hyperliquid] = None,
        tape_dir: Optional[Path] = None, min_interval: float = 0.2) -> Dict[str, Any]:
    """One read-only backfill pass: one `funding_history` record per coin. `client`/
    `tape_dir` injectable for offline testing. A per-coin fetch failure is a visible
    error record that lowers `completeness_ok` but never kills the sibling coins."""
    tape_dir = Path(tape_dir) if tape_dir is not None else TAPE
    if client is None:
        client = Hyperliquid(min_interval=min_interval)

    capture_id, captured_at, day = _now_ids()
    base = {"schema_version": "hyperliquid_funding.v1", "capture_id": capture_id,
            "captured_at": captured_at, "venue": "hyperliquid",
            "record_type": "funding_history", "mode": "backfill"}

    lines: List[str] = []
    per_coin: Dict[str, int] = {}
    n_ok = 0
    for coin in coins:
        body, ok = fetch_funding_history(client.funding_history, coin, start_ms, end_ms)
        n_ok += int(ok)
        per_coin[coin] = body.get("n_prints", 0)
        lines.append(canonical_json({**base, "coin": coin, **body}))

    path = _write(tape_dir, day, lines)
    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_coins": len(list(coins)), "n_coins_ok": n_ok,
        "per_coin_n_prints": per_coin, "n_lines": len(lines),
        "completeness_ok": n_ok == len(list(coins)), "path": path,
    }
    print(f"[hyperliquid_funding] {capture_id}: {n_ok}/{summary['n_coins']} coins ok, "
          f"prints={per_coin}")
    return summary


# --------------------------------------------------------------------------- #
# incremental forward refresh — reads what's already archived, appends only the new
# --------------------------------------------------------------------------- #
def _committed_time_ms(tape_dir: Path, coins: Sequence[str]) -> Dict[str, set]:
    """Per-coin set of funding-print `time_ms` already on committed family tape.

    Streaming over `dt=*.jsonl`: holds ONLY the int set per coin (hourly prints — a few
    thousand ints even after a year, trivially bounded), never the full records, so this
    stays within the memory discipline (L10) regardless of how much tape has accrued. A
    malformed line / missing field is skipped, never fatal. Both `backfill` and `incremental`
    records are read (both are `record_type=funding_history`), so the newest archived print
    is found no matter which mode wrote it."""
    seen: Dict[str, set] = {c: set() for c in coins}
    d = Path(tape_dir)
    if not d.is_dir():
        return seen
    for path in sorted(d.glob("dt=*.jsonl")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if rec.get("record_type") != "funding_history":
                        continue
                    s = seen.get(rec.get("coin"))
                    if s is None:
                        continue
                    for pr in rec.get("prints") or []:
                        ms = pr.get("time_ms")
                        if isinstance(ms, int):
                            s.add(ms)
        except OSError:
            continue
    return seen


def run_incremental(coins: Sequence[str] = DEFAULT_COINS, client: Optional[Hyperliquid] = None,
                    tape_dir: Optional[Path] = None, min_interval: float = 0.2,
                    launch_ms: int = LAUNCH_MS) -> Dict[str, Any]:
    """One incremental forward-refresh pass: per coin, fetch funding prints since the newest
    already archived and union-append ONLY the genuinely-new ones (deduped per-print by
    `(coin, time_ms)`; append-only, existing lines never touched).

    `client`/`tape_dir` injectable for offline testing. Honest completeness: a per-coin fetch
    failure is a visible `fetch_error` record that lowers `completeness_ok` but never kills the
    sibling coins; a successful fetch that simply has no new prints yet is NORMAL (empty-is-data)
    — it writes no line for that coin and does NOT lower completeness. A pass where nothing is
    new for any coin writes no file at all (mirrors polymarket_pairs' `if lines:` guard)."""
    tape_dir = Path(tape_dir) if tape_dir is not None else TAPE
    if client is None:
        client = Hyperliquid(min_interval=min_interval)

    committed = _committed_time_ms(tape_dir, coins)
    capture_id, captured_at, day = _now_ids()
    base = {"schema_version": "hyperliquid_funding.v1", "capture_id": capture_id,
            "captured_at": captured_at, "venue": "hyperliquid",
            "record_type": "funding_history", "mode": "incremental"}

    lines: List[str] = []
    per_coin_new: Dict[str, int] = {}
    per_coin_status: Dict[str, str] = {}
    n_ok = 0
    for coin in coins:
        seen = committed.get(coin, set())
        start_ms = max(seen) if seen else int(launch_ms)
        body, ok = fetch_funding_history(client.funding_history, coin, start_ms)
        n_ok += int(ok)
        if not ok:
            per_coin_new[coin] = 0
            per_coin_status[coin] = "fetch_error"
            lines.append(canonical_json({**base, "coin": coin, **body}))  # visible error record
            continue
        new_prints = [p for p in body["prints"]
                      if p["time_ms"] is not None and p["time_ms"] not in seen]
        per_coin_new[coin] = len(new_prints)
        per_coin_status[coin] = "ok"
        if new_prints:
            lines.append(canonical_json({
                **base, "coin": coin, "status": "ok", "start_ms": int(start_ms),
                "prints": new_prints, "n_prints": len(new_prints),
                "price_source_tag": "broker_truth",
                "raw_sha256": sha256_hex(canonical_json(new_prints)),
            }))

    path = _write(tape_dir, day, lines) if lines else None
    summary = {
        "mode": "incremental", "capture_id": capture_id, "day": day,
        "captured_at": captured_at, "n_coins": len(list(coins)), "n_coins_ok": n_ok,
        "per_coin_new_prints": per_coin_new, "per_coin_status": per_coin_status,
        "n_new_prints": sum(per_coin_new.values()), "n_lines": len(lines),
        "completeness_ok": n_ok == len(list(coins)), "path": path,
    }
    print(f"[hyperliquid_funding] {capture_id} incremental: {n_ok}/{summary['n_coins']} coins ok, "
          f"new_prints={per_coin_new}")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Hyperliquid perp funding-history collector (read-only, public /info)")
    ap.add_argument("--mode", choices=["incremental", "backfill"], default="incremental",
                    help="incremental forward refresh (default) or full paginated backfill")
    ap.add_argument("--coins", nargs="+", default=list(DEFAULT_COINS),
                    help="coin symbols to fetch (default: %(default)s)")
    ap.add_argument("--start-ms", type=int, default=LAUNCH_MS,
                    help="backfill window start (unix ms; default = Kalshi perps launch)")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    if args.mode == "backfill":
        summary = run(coins=args.coins, start_ms=args.start_ms, min_interval=args.min_interval)
    else:
        summary = run_incremental(coins=args.coins, min_interval=args.min_interval)
    return 0 if summary["completeness_ok"] else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
