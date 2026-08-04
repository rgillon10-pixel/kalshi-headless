"""collection.kalshi_trades — public EXECUTED-TRADE print tape (READ-ONLY, unauthenticated).

Why this module exists (the WALL-B unblocker). Every maker-side candidate this project has
tested died on the same sentence, repeated verbatim across `kb/00-LOG.md`, six `findings/`
Q21 rounds and lessons L68/L131: *"`orderbook_depth` has no trade-print field, so a rested
maker fill is unmeasurable"* — S6, S13, S19, S21, S23, S29, S68 and the S73 idea-stage kill
all bottom out there. The repo's own idea-gen rounds concluded (2026-08-02, 2026-08-03)
that "until a comparable trade-print surface lands, further idea-gen rounds will keep
returning zero". `kb/kalshi-api/02-rest-and-websocket.md` has listed `GET /markets/trades`
as PUBLIC market data since 2026-06-18 under a `~` (inferred) marker, and nothing was ever
built against it. This module is that surface.

What a trade print buys that a book snapshot cannot. Each record carries
`taker_book_side` ∈ {bid, ask}, plus `price` and `count`: the direct observable for "would
my resting order have been hit?", the question every fill-sim in this repo has so far had
to SYNTHESIZE (prime-directive-forbidden as a fill price) or assume away
(`OPTIMISTIC_FILL=True`).

*** ORIENTATION — CORRECTED 2026-08-04 (Q51 milestone 2). *** This docstring originally
read `taker_book_side` as "the side of the BOOK the taker crossed INTO". **That is
backwards**, and the committed tape says so. `taker_book_side` names the side of the book
the TAKER'S OWN order sat on: a taker carrying a BID is a BUYER and LIFTS a resting offer;
a taker carrying an ASK is a SELLER and HITS a resting bid. Measured on
`tape/kalshi_trades/dt=2026-08-03.jsonl` x `tape/orderbook_depth/dt=2026-08-03.jsonl`,
restricted to prints landing within 15 minutes of their reference snapshot so the quote is
not up to 3h stale: `bid` prints execute at or ABOVE the best ask 86.8% of the time
(n=151), `ask` prints at or BELOW the best bid 83.3% (n=30), and the effect decays
monotonically as the join window widens (86.8% -> 84.6% -> 70.4% at <=15min / <=60min /
any age) exactly as a real relationship does and an artifact does not. The three side
fields are perfectly collinear on this tape (`bid`/`yes`/`yes` 31,831; `ask`/`no`/`no`
7,867), so the same reading is available from `taker_side` and the redundancy is not extra
evidence. Under the corrected orientation the 80/20 split says retail overwhelmingly BUYS
— the standard prediction-market pattern; under the original reading it would have claimed
80% of taker flow SELLS. The RECORDS ARE UNAFFECTED (the field is stored verbatim from the
API and was never derived here); only the interpretation moves. Consumers: a resting YES
bid is filled by a `taker_book_side == "ask"` print, NOT a `"bid"` one. Pinned by
`tests/test_q51_maker_fillsim.py::test_acceptance_taker_book_side_orientation_*`.

Trust / provenance (CLAUDE.md trust-default). An executed trade is a venue-reported fact
about a completed transaction, not a quote we hope to hit and not a model output — the same
epistemic class as Kalshi's own settlement `result`. Every line is therefore tagged
`price_source_tag: "broker_truth"` (a member of `core.source_tag.SOURCE_TAGS`; this module
does NOT widen that enum). Prices are stored verbatim in dollars with NO normalization and
NO derived probability (Hard Rule #3 — that transform lives only in `core.pricing`).

Backfill, not just forward capture (verified live 2026-08-04). `/markets/trades` accepts
`min_ts`/`max_ts` UNIX-second bounds and `ticker`, so this collector can reconstruct history
for markets whose book tape we already hold: probed live, a 2026-06-20 window still returns
prints, which predates this repo's OLDEST book tape (`tape/sports_pairs/dt=2026-07-03`).
That makes the fill question retro-testable on already-committed tape rather than only
after N more forward days — the single reason this is worth building now rather than as a
forward-only leg.

Day partitioning differs from the snapshot families ON PURPOSE. `universe_sweep`/
`orderbook_depth` partition `dt=` by CAPTURE day because a snapshot has no other time. A
trade print carries its own immutable event time, and every downstream join is
book-snapshot-day × trade-day — so lines are partitioned by the UTC day of the trade's
`created_time`, with `captured_at`/`capture_id` recording when we pulled it. One backfill
pass therefore legitimately writes into several past day-files.

Idempotent by construction (lesson L221/L222 shape). A trade is immutable and uniquely keyed
by `trade_id`, so this collector DEDUPES against the trade_ids already present in each target
day-file before appending — re-running the same window is a no-op that appends zero bytes,
rather than the "unbounded passes inside the gate hour produce byte-redundant re-capture"
failure L221 measured on `econ_prints`. Files are still append-only; existing lines are never
rewritten or reordered.

Honest completeness (lesson L10, and L270's cap-saturation shape). `completeness_ok` is True
only if pagination EXHAUSTED the cursor within `max_calls` AND no record failed to parse.
Hitting the call cap with an active cursor sets `truncated=True` / `completeness_ok=False`
and is reported, never silently upgraded. `at_cap` is reported as its OWN field so a
consumer can distinguish "bounded by our cap" from "parse failure" without re-deriving it —
L270's lesson being that a permanently-false completeness folded into a pass-level signal is
indistinguishable from a new outage.

NOT wired into `collection/hourly_pass.py`. This module is standalone (`python -m
collection.kalshi_trades`). Adding a leg mutates a LIVE collector's write path, which
lessons L221/L222 place outside a research run's lane; wiring is a separate, deliberate
decision with its own cadence/quota analysis.

Read-only and unauthenticated: no credential is read, no header is signed, no order verb
exists here. This is public market data, the same class as every other module in this
package (see L145 for the authenticated-vs-order-capable distinction).

Run:
    python -m collection.kalshi_trades --day 2026-08-03 --tickers-from tape/orderbook_depth
    python -m collection.kalshi_trades --ticker KXBTC15M-26AUG040530-30 --day 2026-08-04
    python -m collection.kalshi_trades --min-ts 1785000000 --max-ts 1785003600
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from core.kalshi_fields import parse_kalshi_numeric as _to_float
from core.timeutil import parse_iso_utc

TAPE = REPO_ROOT / "tape" / "kalshi_trades"

TRADES_PATH = "/markets/trades"

# A ticker-scoped window is small (one market's prints over one day); a venue-wide window is
# NOT — a live probe measured >6,000 prints in a single 10-minute platform-wide window
# (2026-07-28T18:00Z), i.e. ~1e6/day. The cap is therefore a real bound, and `truncated`
# reporting is load-bearing rather than theoretical. Callers doing venue-wide pulls must
# treat a truncated pass as partial coverage of that window, never as the window.
MAX_CALLS = 40
PAGE_LIMIT = 1000

SCHEMA_VERSION = "kalshi_trades.v1"


def _trade_day(created_time: str) -> Optional[str]:
    """UTC day (YYYY-MM-DD) of a trade's own `created_time`, or None if unparseable.

    Partitioning key — see the module docstring on why this is the TRADE's day and not the
    capture day. Kalshi returns RFC3339 with a 'Z' suffix and VARIABLE fractional-second
    precision, so parsing goes through `core.timeutil.parse_iso_utc` and never the stdlib
    `datetime.fromisoformat` directly (L136/L150: the 3.9 floor rejects the trailing-zero-
    stripped fractions that are ~38% of committed tape, and CI on 3.11 is blind to it).
    """
    if not isinstance(created_time, str) or not created_time:
        return None
    try:
        return parse_iso_utc(created_time).astimezone(timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _record_from_trade(t: Dict[str, Any], captured_at: str, capture_id: str,
                       raw_sha256: Optional[str]) -> Dict[str, Any]:
    """One executed-print record from a Kalshi `/markets/trades` object.

    `taker_book_side` is the load-bearing field: the side of the book the TAKER'S OWN
    order sat on — a `bid` taker BUYS (lifting a resting offer), an `ask` taker SELLS
    (hitting a resting bid). See the module docstring's ORIENTATION note: the original
    reading of this field was inverted and was corrected on 2026-08-04 against the tape.
    Stored verbatim from the API and never derived here, so no record changed.
    Prices are stored verbatim in dollars — no normalization, no derived probability.
    """
    ticker = t.get("ticker")
    created_time = t.get("created_time")
    return {
        "schema_version": SCHEMA_VERSION,
        "capture_id": capture_id,
        "captured_at": captured_at,
        "venue": "kalshi",
        "trade_id": t.get("trade_id"),
        "ticker": ticker,
        "event_ticker": t.get("event_ticker"),
        "created_time": created_time,
        "trade_day": _trade_day(created_time or ""),
        # executed prices, verbatim dollars (Hard Rule #3: no normalization here)
        "yes_price": _to_float(t.get("yes_price_dollars")),
        "no_price": _to_float(t.get("no_price_dollars")),
        "count": _to_float(t.get("count_fp")),
        # the fill observable: which side of the BOOK the taker crossed into
        "taker_book_side": t.get("taker_book_side"),
        "taker_side": t.get("taker_side"),
        "taker_outcome_side": t.get("taker_outcome_side"),
        "is_block_trade": t.get("is_block_trade"),
        # an executed trade is a venue-reported completed transaction -> broker_truth
        "price_source_tag": "broker_truth",
        "raw_sha256": raw_sha256,
        "source": "public_markets_trades",
    }


# --------------------------------------------------------------------------- #
# bounded paginated pull
# --------------------------------------------------------------------------- #
def fetch_trades(client, ticker: Optional[str] = None, min_ts: Optional[int] = None,
                 max_ts: Optional[int] = None, max_calls: int = MAX_CALLS,
                 page_limit: int = PAGE_LIMIT
                 ) -> Tuple[List[Dict], List[str], bool, int]:
    """Paginate `/markets/trades`, bounded by `max_calls`.

    Returns (trades, raw_pages, truncated, n_calls). `truncated=True` iff we stopped because
    the call cap was reached while the cursor was STILL active — honest partial coverage of
    the requested window (L10), never silently upgraded to full.
    """
    trades: List[Dict] = []
    raw_pages: List[str] = []
    truncated = False
    n_calls = 0
    cursor: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"limit": page_limit}
        if ticker:
            params["ticker"] = ticker
        if min_ts is not None:
            params["min_ts"] = int(min_ts)
        if max_ts is not None:
            params["max_ts"] = int(max_ts)
        if cursor:
            params["cursor"] = cursor
        text = client.get_text(TRADES_PATH, **params)
        n_calls += 1
        raw_pages.append(text)
        j = json.loads(text)
        items = j.get("trades") or []
        trades.extend(items)
        cursor = j.get("cursor")
        if not cursor or not items:
            break
        if n_calls >= max_calls:
            truncated = True
            break
    return trades, raw_pages, truncated, n_calls


# --------------------------------------------------------------------------- #
# append-only, trade_id-deduped write
# --------------------------------------------------------------------------- #
def existing_trade_ids(store: Path, day: str) -> Set[str]:
    """trade_ids already committed in `dt=<day>.jsonl` (empty set if the file is absent).

    A malformed/legacy line without a parseable trade_id is skipped rather than raising —
    it simply cannot suppress an append, which is the safe direction (a duplicate is
    detectable and removable; a silently-dropped print is not).
    """
    path = store / f"dt={day}.jsonl"
    ids: Set[str] = set()
    if not path.exists():
        return ids
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                tid = json.loads(line).get("trade_id")
            except (ValueError, AttributeError):
                continue
            if isinstance(tid, str) and tid:
                ids.add(tid)
    return ids


def append_records(store: Path, records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Append records to their own trade-day files, deduped by `trade_id`.

    Dedupe is against BOTH what is already on disk and what this same call has queued, so a
    window that returns the same print twice (overlapping pages) writes it once. Returns
    {paths, n_written, n_duplicate, n_undated}.
    """
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    n_undated = 0
    for rec in records:
        day = rec.get("trade_day")
        if not day:
            n_undated += 1
            continue
        by_day.setdefault(day, []).append(rec)

    paths: List[str] = []
    n_written = 0
    n_duplicate = 0
    for day, recs in sorted(by_day.items()):
        seen = existing_trade_ids(store, day)
        fresh: List[str] = []
        for rec in recs:
            tid = rec.get("trade_id")
            if not isinstance(tid, str) or not tid or tid in seen:
                n_duplicate += 1
                continue
            seen.add(tid)
            fresh.append(canonical_json(rec))
        if not fresh:
            continue
        store.mkdir(parents=True, exist_ok=True)
        out_path = store / f"dt={day}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for ln in fresh:
                f.write(ln + "\n")
        paths.append(str(out_path))
        n_written += len(fresh)
    return {"paths": paths, "n_written": n_written, "n_duplicate": n_duplicate,
            "n_undated": n_undated}


# --------------------------------------------------------------------------- #
# ticker discovery from an existing book-tape family (the join target)
# --------------------------------------------------------------------------- #
def tickers_from_tape(family_dir: Path, day: Optional[str] = None,
                      limit: Optional[int] = None) -> List[str]:
    """Distinct `ticker`s appearing in a committed tape family (optionally one `dt=` day).

    This is how a backfill is aimed at exactly the markets whose BOOK we already hold —
    the population the fill question is asked about — instead of pulling the whole venue.
    Returned in first-seen order so a `--limit` slice is deterministic and re-runnable.
    """
    family_dir = Path(family_dir)
    if not family_dir.exists():
        return []
    files = sorted(family_dir.glob(f"dt={day}.jsonl")) if day else sorted(
        family_dir.glob("dt=*.jsonl"))
    out: List[str] = []
    seen: Set[str] = set()
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    tk = json.loads(line).get("ticker")
                except (ValueError, AttributeError):
                    continue
                if isinstance(tk, str) and tk and tk not in seen:
                    seen.add(tk)
                    out.append(tk)
                    if limit is not None and len(out) >= limit:
                        return out
    return out


def day_bounds(day: str) -> Tuple[int, int]:
    """UNIX-second [start, end) bounds of a UTC day string 'YYYY-MM-DD'."""
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


# --------------------------------------------------------------------------- #
# one pass
# --------------------------------------------------------------------------- #
def run(tickers: Optional[Iterable[str]] = None, min_ts: Optional[int] = None,
        max_ts: Optional[int] = None, min_interval: float = 0.25, client=None,
        store: Optional[Path] = None, max_calls: int = MAX_CALLS,
        page_limit: int = PAGE_LIMIT) -> Dict[str, Any]:
    """One read-only trade-print pull.

    With `tickers`, issues one bounded paginated query PER ticker (the targeted backfill
    shape); without, one venue-wide query over the window. `client`/`store` are injectable
    for fully offline testing. Returns a summary whose `completeness_ok` is True only on a
    clean cursor exhaustion for EVERY query with zero parse errors.
    """
    store = Path(store) if store is not None else TAPE
    if client is None:
        from validation.v3_market import Kalshi, _load_venue_cfg
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")

    queries: List[Optional[str]] = list(tickers) if tickers else [None]
    all_records: List[Dict[str, Any]] = []
    raw_pages_all: List[str] = []
    n_calls = 0
    n_pulled = 0
    n_parse_errors = 0
    truncated_queries: List[str] = []

    for tk in queries:
        trades, raw_pages, truncated, calls = fetch_trades(
            client, ticker=tk, min_ts=min_ts, max_ts=max_ts,
            max_calls=max_calls, page_limit=page_limit)
        n_calls += calls
        n_pulled += len(trades)
        raw_pages_all.extend(raw_pages)
        if truncated:
            truncated_queries.append(tk or "__venue_wide__")
        page_sha = sha256_hex("".join(raw_pages)) if raw_pages else None
        for t in trades:
            try:
                all_records.append(
                    _record_from_trade(t, captured_at, capture_id, page_sha))
            except Exception as exc:     # one bad print never kills the pass
                n_parse_errors += 1
                print(f"[kalshi_trades] parse error on {t.get('trade_id')}: {exc}",
                      file=sys.stderr)

    written = append_records(store, all_records)
    cursor_exhausted = not truncated_queries
    completeness_ok = cursor_exhausted and n_parse_errors == 0

    summary = {
        "capture_id": capture_id,
        "captured_at": captured_at,
        "n_queries": len(queries),
        "n_pulled": n_pulled,
        "n_lines": written["n_written"],
        "n_duplicate": written["n_duplicate"],
        "n_undated": written["n_undated"],
        "call_count": n_calls,
        "cursor_exhausted": cursor_exhausted,
        "truncated": bool(truncated_queries),
        "at_cap": bool(truncated_queries),
        "n_truncated_queries": len(truncated_queries),
        "truncated_queries": truncated_queries[:20],
        "n_parse_errors": n_parse_errors,
        "completeness_ok": completeness_ok,
        "min_ts": min_ts,
        "max_ts": max_ts,
        "raw_sha256": sha256_hex("".join(raw_pages_all)) if raw_pages_all else None,
        "paths": written["paths"],
    }
    print(f"[kalshi_trades] {capture_id}: {len(queries)} query/queries, "
          f"pulled {n_pulled} print(s) in {n_calls} call(s), wrote {written['n_written']} "
          f"new line(s) ({written['n_duplicate']} already held), "
          f"completeness {'ok' if completeness_ok else 'FAIL'}"
          + (f" (TRUNCATED on {len(truncated_queries)} query/queries)"
             if truncated_queries else ""))
    if truncated_queries:
        print(f"[kalshi_trades] WARN hit the {max_calls}-call cap with an active cursor on "
              f"{len(truncated_queries)} query/queries -> truncated=True, "
              f"completeness_ok=False (partial coverage of the window)", file=sys.stderr)
    if n_parse_errors:
        print(f"[kalshi_trades] WARN {n_parse_errors} parse error(s) -> completeness_ok=False",
              file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Public executed-trade print tape (read-only, append-only, deduped)")
    ap.add_argument("--ticker", action="append", default=None,
                    help="market ticker to pull (repeatable); omit for a venue-wide window")
    ap.add_argument("--tickers-from", default=None,
                    help="tape family directory (e.g. tape/orderbook_depth) whose distinct "
                         "tickers define the pull population")
    ap.add_argument("--tickers-from-day", default=None,
                    help="restrict --tickers-from to one dt= day (default: all days)")
    ap.add_argument("--max-tickers", type=int, default=None,
                    help="cap the ticker population (bounded, deterministic first-seen slice)")
    ap.add_argument("--day", default=None,
                    help="UTC day YYYY-MM-DD; sets min_ts/max_ts to that day's bounds")
    ap.add_argument("--min-ts", type=int, default=None, help="window start (unix seconds)")
    ap.add_argument("--max-ts", type=int, default=None, help="window end (unix seconds)")
    ap.add_argument("--max-calls", type=int, default=MAX_CALLS,
                    help="hard cap on paginated calls PER query")
    ap.add_argument("--page-limit", type=int, default=PAGE_LIMIT,
                    help="prints per page (Kalshi max 1000)")
    ap.add_argument("--min-interval", type=float, default=0.25,
                    help="min seconds between live fetches (politeness)")
    args = ap.parse_args(argv)

    min_ts, max_ts = args.min_ts, args.max_ts
    if args.day:
        d_start, d_end = day_bounds(args.day)
        min_ts = d_start if min_ts is None else min_ts
        max_ts = d_end if max_ts is None else max_ts

    tickers: List[str] = list(args.ticker or [])
    if args.tickers_from:
        tickers.extend(t for t in tickers_from_tape(
            Path(args.tickers_from), day=args.tickers_from_day, limit=args.max_tickers)
            if t not in tickers)
    if args.max_tickers is not None:
        tickers = tickers[:args.max_tickers]

    s = run(tickers=tickers or None, min_ts=min_ts, max_ts=max_ts,
            min_interval=args.min_interval, max_calls=args.max_calls,
            page_limit=args.page_limit)
    return 0 if s["completeness_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
