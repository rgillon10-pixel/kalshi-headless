"""collection.hf_burst — standing HIGH-FREQUENCY burst orderbook poller (READ-ONLY).

Why this exists (the cadence-blindness unblock)
------------------------------------------------
The project's tape is HOURLY. Every "no durable dislocation" strategy death (S9 lead-lag,
S28, the S33 ladder-coherence sub-second bursts) is really an artifact of cadence being too
coarse to MEASURE the duration of a dislocation — lesson L76 (a snapshot-count "duration"
gate is not a duration gate) and L77 (forward-filled joint state manufactures phantom arbs)
both bite precisely because we cannot observe sub-minute repricing. There is a whole untested
lane — settlement-source latency races (Kalshi's hourly weather markets settle on The Weather
Company; if TWC publishes a value before the Kalshi book reprices, a fast poller picks it off)
— that we cannot even TEST until we can capture at HF cadence. This module is that capture.

It takes a small, CONFIG-DRIVEN watchlist of markets/series most likely to have a
settlement-latency race, resolves them to a fixed ticker set ONCE at window start, then polls
each target's public orderbook at a configurable cadence for a bounded window, appending one
JSONL line per (ticker, round). Every price carries the same `real_ask`/`real_bid` source tags
and the same structural fields (`yes_bids`/`no_bids`/`best_*_ask`/`depth`, via the SHARED
collection.normalize.normalize_snapshot) the hourly collectors write, so existing analysis code
reads this tape unchanged. Each snapshot carries BOTH a wall-clock ISO `captured_at`
(microsecond) AND a monotonic `capture_mono_ns` — the monotonic clock is what actually measures
sub-minute duration (it is immune to wall-clock adjustments, unlike ISO timestamps).

HONEST ACHIEVABLE CADENCE (read this before assuming 200ms works)
-----------------------------------------------------------------
The public Kalshi REST book endpoint (`GET /markets/{ticker}/orderbook`, the SAME unauthenticated
read the other collectors use) is governed by a per-second TOKEN BUCKET: Basic tier ~200 read
tokens/s at ~10 tokens/request => ~20 read req/s total, burst up to ~2x (kb/kalshi-api/
02-rest-and-websocket.md, verified). That budget is shared across ALL requests, so a round that
polls N tickers costs N requests. The honest consequences:

  * Sub-second PER TARGET is only feasible in SHORT bursts for a TINY watchlist (a single
    ticker can be re-requested every ~50-100ms inside the burst allowance; a handful of tickers
    pushes the per-target cadence toward ~1s once you divide the budget).
  * The realistic SUSTAINED floor on public REST is ~1-2s per target for a small watchlist.
    Do NOT claim 200ms for a multi-target sustained run — the bucket will 429 you.
  * TRUE continuous sub-second (event-driven, no polling waste) needs the Kalshi WebSocket
    `orderbook_delta` push feed (snapshot + deltas with venue `ts_ms`). That feed authenticates
    with the SAME RSA key pair on the handshake (kb/kalshi-api/01-auth-and-signing.md) — i.e. it
    needs CREDENTIALS, which this read-only collector deliberately does not have and must not
    obtain. So: **the WS feed is the real unblock for genuine HF, and building it is a separate,
    credentialed, Ryan-gated task.** This module is the honest REST-only best-effort until then.

`--cadence-ms` has a hard floor of `CADENCE_FLOOR_MS` (250ms): a burst tighter than that against
public REST is not reliably serv-able and just wastes the token bucket. The per-request client
throttle (`--min-request-interval`, default 0.1s ~= 10 req/s, comfortably inside Basic) is the
second guard. If a round overruns its cadence, missed boundaries are SKIPPED (no back-to-back
catch-up pile-up) — the same scheduler discipline as collection/burst_capture.py.

Honest completeness (same discipline as every collection/ module)
-----------------------------------------------------------------
The resolved ticker set is the EXPECTED set per round. A per-ticker orderbook fetch that raises
is a DROP (recorded, never absorbed), lowering that round's captured count. A whole-series
resolution failure at window start is a `resolve_error` (its markets never enter the poll set —
an honest gap). `completeness_ok` for the window is: at least one round ran AND every round
captured its full expected set AND nothing was truncated AND no resolve errors. A partial
failure lowers it; it NEVER fakes success and one bad ticker/round never kills the others.
`--max-markets` caps the resolved target set (lesson L10: Kalshi's 10k+ universe once blew 3GB
RSS) and carries an honest `truncated` flag; only summary COUNTERS live in memory across the
window (each round's lines are flushed to disk immediately), so a long window cannot balloon RSS.

Tape layout: append-only JSONL under `tape/hf_burst/dt=YYYY-MM-DD.jsonl` (one line per
(ticker, round)), never rewritten or reordered. `--out` overrides the path.

SCOPE / wiring (Ryan's pause points — NOT crossed by this module)
-----------------------------------------------------------------
This is the module + offline tests only. It is NOT wired into collection/hourly_pass.py, NOT
deployed, NOT cronned. HOW it would be wired/deployed (left to Ryan):
  * Manual/event-triggered run (recommended first use): launch shortly before a known
    settlement instant (top of an hourly weather/crypto window, an econ print) with a bounded
    `--window-seconds`, e.g.
        python -m collection.hf_burst --targets series:KXTEMPNYCH --cadence-ms 1000 \
            --window-seconds 300
  * Standing/scheduled: a systemd timer or the burst-trigger pattern (ops/ROUTINES.md) that
    fires this at each hourly close, NOT a continuous process. Continuous sub-second belongs to
    the credentialed WS collector, not here.
  * The VPS (root@…, min_interval-throttled hourly collector) is the natural host IF Ryan
    decides the REST cadence is worth the token budget there — but that is his call, and a
    sustained HF poll must be weighed against the Basic-tier bucket the hourly pass shares.

CLI
---
    python -m collection.hf_burst --targets series:KXTEMPNYCH,series:KXBTC --cadence-ms 1000 \
        --window-seconds 120
    python -m collection.hf_burst --config config/hf_burst_targets.yaml --cadence-ms 500 \
        --window-seconds 60 --out /path/to/out.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from collection.normalize import normalize_snapshot
from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from validation.v3_market import Kalshi, _load_venue_cfg

TAPE = REPO_ROOT / "tape" / "hf_burst"
ORDERBOOK_PATH = "/markets/{ticker}/orderbook"
SCHEMA_VERSION = "hf_burst.v1"

# Hard cadence floor: a burst tighter than this against public REST is not reliably servable
# (token bucket) and just wastes budget — genuine sub-second needs the WS feed (see docstring).
CADENCE_FLOOR_MS = 250

# Defensive per-pass target cap (lesson L10: the 10k+ open-market universe once blew 3GB RSS).
MAX_MARKETS_DEFAULT = 200

# Default per-request client throttle (seconds). 0.1s ~= 10 req/s, comfortably inside Basic
# tier's ~20 read req/s ceiling, leaving headroom for the shared hourly pass.
MIN_REQUEST_INTERVAL_DEFAULT = 0.1

# Default watchlist: the three families the settlement-latency thesis flags first. `series:`
# tokens resolve to their OPEN markets at window start; econ is print-specific so it is left to
# --config / --targets rather than hardcoded here.
DEFAULT_TARGETS: Tuple[str, ...] = ("series:KXTEMPNYCH", "series:KXBTC", "series:KXETH")

_SERIES_PREFIX = "series:"
_TICKER_PREFIX = "ticker:"


# --------------------------------------------------------------------------- #
# target resolution — watchlist tokens -> a fixed, capped ticker set (ONCE, at window start)
# --------------------------------------------------------------------------- #
def resolve_targets(client: Kalshi, targets: List[str], max_markets: int = MAX_MARKETS_DEFAULT
                    ) -> Tuple[List[str], Dict[str, Any], List[Dict[str, str]], bool]:
    """Resolve watchlist tokens to a deduped, ordered, capped list of market tickers.

    Token forms:
      * "series:XXX"  -> every OPEN market ticker in series XXX (resolved once here)
      * "ticker:XXX"  -> the literal market ticker XXX
      * bare "XXX-…"  -> treated as a literal market ticker (must contain a '-')

    Returns (tickers, report, resolve_errors, truncated). A per-series enumeration failure is a
    `resolve_error` (recorded, never hidden — its markets never enter the poll set). The cap is
    applied AFTER dedup and flips `truncated` True (lesson L10)."""
    ordered: List[str] = []
    seen: set = set()
    resolve_errors: List[Dict[str, str]] = []
    per_series: Dict[str, int] = {}

    def _add(t: str) -> None:
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)

    for tok in targets:
        tok = tok.strip()
        if not tok:
            continue
        if tok.startswith(_SERIES_PREFIX):
            series = tok[len(_SERIES_PREFIX):]
            try:
                markets = client.open_markets(series)
            except Exception as exc:   # whole-series resolution failure -> honest gap
                resolve_errors.append({"target": tok, "error": str(exc)})
                continue
            per_series[series] = len(markets or [])
            for m in (markets or []):
                _add(m.get("ticker", ""))
        elif tok.startswith(_TICKER_PREFIX):
            _add(tok[len(_TICKER_PREFIX):])
        else:
            _add(tok)   # bare literal market ticker

    truncated = len(ordered) > max_markets
    if truncated:
        ordered = ordered[:max_markets]

    report = {
        "targets": list(targets),
        "n_resolved": len(ordered),
        "per_series_open_count": per_series,
        "n_resolve_errors": len(resolve_errors),
    }
    return ordered, report, resolve_errors, truncated


# --------------------------------------------------------------------------- #
# one snapshot record — reuses the shared normalize + the collectors' field/tag conventions
# --------------------------------------------------------------------------- #
def _extract_snapshot(ticker: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """Return (snapshot, raw_book, book_shape). Handles the modern `orderbook_fp` string-dollars
    shape and the legacy integer-cents `orderbook` shape (a venue rollback can't silently zero
    the capture); normalize_snapshot owns the bid->opposite-ask complement."""
    fp = payload.get("orderbook_fp")
    if fp is not None:
        return normalize_snapshot(ticker, fp or {}), (fp or {}), "orderbook_fp"
    legacy = payload.get("orderbook")
    if legacy is not None:
        conv = {
            "yes_dollars": [[str(float(p) / 100.0), str(sz)] for p, sz in (legacy.get("yes") or [])],
            "no_dollars": [[str(float(p) / 100.0), str(sz)] for p, sz in (legacy.get("no") or [])],
        }
        return normalize_snapshot(ticker, conv), (legacy or {}), "orderbook_legacy"
    return normalize_snapshot(ticker, {}), {}, "empty"


def _build_record(ticker: str, payload: Dict[str, Any], *, capture_id: str, captured_at: str,
                  capture_mono_ns: int, round_index: int, capture_seq: int, raw_sha256: str
                  ) -> Dict[str, Any]:
    snap, raw_book, book_shape = _extract_snapshot(ticker, payload)
    return {
        "schema_version": SCHEMA_VERSION,
        "capture_id": capture_id,          # window id (start instant) — groups a burst
        "round_index": round_index,        # which poll round within the window (0-based)
        "capture_seq": capture_seq,        # monotonic line index within the window
        "captured_at": captured_at,        # wall-clock ISO, microsecond
        "capture_mono_ns": capture_mono_ns,  # monotonic ns — the real duration ruler (L76)
        "venue": "kalshi",
        "ticker": ticker,
        "raw_orderbook": raw_book,
        "book_shape": book_shape,
        "yes_bids": snap["yes_bids"],
        "no_bids": snap["no_bids"],
        "best_yes_bid": snap["best_yes_bid"],
        "best_no_bid": snap["best_no_bid"],
        "best_yes_ask": snap["best_yes_ask"],
        "best_no_ask": snap["best_no_ask"],
        "depth": snap["depth"],
        # a live book read is a real fillable quote, not a model (CLAUDE.md Hard Rules #3/#4)
        "price_source_tag": "real_ask",
        "price_source_tags": {"asks": "real_ask", "bids": "real_bid"},
        "raw_sha256": raw_sha256,
    }


# --------------------------------------------------------------------------- #
# one poll round — every ticker once, fault-isolated (a bad ticker never kills the round)
# --------------------------------------------------------------------------- #
def poll_round(client: Kalshi, tickers: List[str], *, capture_id: str, round_index: int,
               seq_start: int, now_fn: Callable[[], datetime], mono_fn: Callable[[], int]
               ) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Poll each ticker's orderbook once. Returns (records, dropped). A fetch that raises is a
    DROP (recorded), never absorbed. Each record's timestamp is read PER TICKER (not once per
    round) so intra-round ordering/duration stays honest."""
    records: List[Dict[str, Any]] = []
    dropped: List[str] = []
    seq = seq_start
    for ticker in tickers:
        cap_ts = now_fn()
        mono_ns = mono_fn()
        try:
            text = client.get_text(ORDERBOOK_PATH.format(ticker=ticker))
        except Exception:
            dropped.append(ticker)
            continue
        payload = json.loads(text) if text else {}
        raw_sha256 = sha256_hex((text or "").encode("utf-8"))
        records.append(_build_record(
            ticker, payload or {}, capture_id=capture_id, captured_at=cap_ts.isoformat(),
            capture_mono_ns=mono_ns, round_index=round_index, capture_seq=seq,
            raw_sha256=raw_sha256))
        seq += 1
    return records, dropped


# --------------------------------------------------------------------------- #
# the window loop — sleep/now/mono injectable for offline tests
# --------------------------------------------------------------------------- #
def run_window(targets: List[str], cadence_ms: int, window_seconds: float, *,
               client: Optional[Kalshi] = None, out: Optional[Path] = None,
               max_markets: int = MAX_MARKETS_DEFAULT,
               min_request_interval: float = MIN_REQUEST_INTERVAL_DEFAULT,
               now_fn: Optional[Callable[[], datetime]] = None,
               mono_fn: Optional[Callable[[], int]] = None,
               sleep_fn: Optional[Callable[[float], None]] = None) -> Dict[str, Any]:
    """Poll `targets` at `cadence_ms` for `window_seconds`, appending JSONL to `out`.

    Scheduling runs off the MONOTONIC clock (`mono_fn`, nanoseconds): round boundaries sit at
    start + k*cadence; if a round overruns, missed boundaries are SKIPPED (no catch-up pile-up),
    mirroring collection/burst_capture.py. `now_fn`/`mono_fn`/`sleep_fn` are injectable for
    offline tests and default to wall-clock / time.monotonic_ns / time.sleep. Records are flushed
    to disk each round; only counters live in memory across the window (L10 RSS discipline)."""
    if cadence_ms < CADENCE_FLOOR_MS:
        raise ValueError(f"--cadence-ms {cadence_ms} below hard floor {CADENCE_FLOOR_MS}ms "
                         f"(public REST can't reliably serve tighter; use the WS feed)")

    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    mono_fn = mono_fn or _time.monotonic_ns
    sleep_fn = sleep_fn or _time.sleep

    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_request_interval)

    start_ts = now_fn()
    capture_id = start_ts.strftime("%Y%m%dT%H%M%SZ")
    day = start_ts.strftime("%Y-%m-%d")
    out_path = Path(out) if out is not None else (TAPE / f"dt={day}.jsonl")

    # resolve the fixed ticker set ONCE (a burst polls a stable set; re-resolving each round
    # would burn the token budget and let the poll set drift mid-window)
    tickers, resolve_report, resolve_errors, truncated = resolve_targets(
        client, targets, max_markets=max_markets)

    cadence_s = cadence_ms / 1000.0
    start_mono = mono_fn()
    deadline_mono = start_mono + int(window_seconds * 1e9)

    n_rounds = 0
    n_records = 0
    total_expected = 0
    total_dropped = 0
    round_summaries: List[Dict[str, Any]] = []
    seq = 0
    fh = None

    # honest zero-round exits: nothing resolved, or the window is non-positive. Either way we
    # never pretend a capture happened.
    window_ran = window_seconds > 0 and bool(tickers)

    if window_ran:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(out_path, "a", encoding="utf-8")
        try:
            k = 0
            while True:
                boundary = start_mono + int(k * cadence_s * 1e9)
                now_m = mono_fn()
                wait = (boundary - now_m) / 1e9
                if wait > 0:
                    sleep_fn(wait)
                    now_m = mono_fn()
                if now_m >= deadline_mono:
                    break

                records, dropped = poll_round(
                    client, tickers, capture_id=capture_id, round_index=n_rounds,
                    seq_start=seq, now_fn=now_fn, mono_fn=mono_fn)
                for rec in records:
                    fh.write(canonical_json(rec) + "\n")
                fh.flush()

                seq += len(records)
                n_records += len(records)
                total_expected += len(tickers)
                total_dropped += len(dropped)
                round_summaries.append({
                    "round_index": n_rounds, "n_captured": len(records),
                    "n_dropped": len(dropped), "dropped": dropped})
                n_rounds += 1

                # advance to the next boundary strictly in the future (skip any missed while this
                # round ran long) — no pile-up, no catch-up burst.
                after = mono_fn()
                k += 1
                while start_mono + int(k * cadence_s * 1e9) <= after:
                    k += 1
        finally:
            fh.close()

    completeness_ok = (
        n_rounds > 0
        and total_dropped == 0
        and not truncated
        and not resolve_errors)

    end_ts = now_fn()
    elapsed_s = (mono_fn() - start_mono) / 1e9
    summary = {
        "capture_id": capture_id, "day": day,
        "started_at": start_ts.isoformat(), "ended_at": end_ts.isoformat(),
        "elapsed_seconds": round(elapsed_s, 3),
        "targets": list(targets), "n_tickers": len(tickers),
        "cadence_ms": cadence_ms, "window_seconds": window_seconds,
        "n_rounds": n_rounds, "n_records": n_records,
        "n_expected": total_expected, "n_dropped": total_dropped,
        "truncated": truncated,
        "resolve_errors": resolve_errors, "n_resolve_errors": len(resolve_errors),
        "resolve_report": resolve_report,
        "completeness_ok": completeness_ok,
        "window_ran": window_ran,
        "round_summaries": round_summaries,
        "path": str(out_path) if window_ran else None,
    }
    return summary


def _summary_line(s: Dict[str, Any]) -> str:
    comp = "ok" if s["completeness_ok"] else "FAIL"
    tail = " (TRUNCATED)" if s["truncated"] else ""
    if not s["window_ran"]:
        why = "no tickers resolved" if s["n_tickers"] == 0 else "non-positive window"
        return (f"hf_burst {s['capture_id']}: 0 rounds ({why}), "
                f"{s['n_resolve_errors']} resolve-errors, completeness {comp}")
    return (f"hf_burst {s['capture_id']}: {s['n_rounds']} rounds over "
            f"{s['elapsed_seconds']:.1f}s, {s['n_tickers']} tickers @ {s['cadence_ms']}ms, "
            f"{s['n_records']} records, {s['n_dropped']} dropped, "
            f"{s['n_resolve_errors']} resolve-errors, completeness {comp}{tail}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load_config_targets(path: Path) -> List[str]:
    """Read a watchlist YAML with a top-level `targets:` list of tokens."""
    import yaml
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    targets = doc.get("targets") or []
    if not isinstance(targets, list) or not targets:
        raise ValueError(f"{path}: expected a non-empty top-level 'targets:' list")
    return [str(t) for t in targets]


def _targets_arg(value: str) -> List[str]:
    toks = [t.strip() for t in value.split(",") if t.strip()]
    if not toks:
        raise argparse.ArgumentTypeError("--targets must list at least one token")
    return toks


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Standing high-frequency burst orderbook poller (read-only public data)")
    ap.add_argument("--targets", type=_targets_arg, default=None,
                    help="comma list of watchlist tokens: series:XXX | ticker:XXX | bare ticker")
    ap.add_argument("--config", type=Path, default=None,
                    help="YAML watchlist with a top-level 'targets:' list (alternative to --targets)")
    ap.add_argument("--cadence-ms", type=int, default=1000,
                    help=f"ms between poll rounds (hard floor {CADENCE_FLOOR_MS})")
    ap.add_argument("--window-seconds", type=float, default=60.0,
                    help="bounded capture window length in seconds")
    ap.add_argument("--out", type=Path, default=None,
                    help="output JSONL path (default tape/hf_burst/dt=<day>.jsonl)")
    ap.add_argument("--max-markets", type=int, default=MAX_MARKETS_DEFAULT,
                    help=f"cap on resolved target tickers (L10 memory guard, default {MAX_MARKETS_DEFAULT})")
    ap.add_argument("--min-request-interval", type=float, default=MIN_REQUEST_INTERVAL_DEFAULT,
                    help="per-request client throttle in seconds (default keeps inside Basic tier)")
    args = ap.parse_args(argv)

    if args.cadence_ms < CADENCE_FLOOR_MS:
        ap.error(f"--cadence-ms {args.cadence_ms} below hard floor {CADENCE_FLOOR_MS}ms")

    if args.targets and args.config:
        ap.error("pass exactly one of --targets / --config, not both")
    if args.config:
        targets = _load_config_targets(args.config)
    elif args.targets:
        targets = args.targets
    else:
        targets = list(DEFAULT_TARGETS)
        print(f"[hf_burst] no --targets/--config given; using DEFAULT_TARGETS {targets}",
              file=sys.stderr)

    summary = run_window(
        targets=targets, cadence_ms=args.cadence_ms, window_seconds=args.window_seconds,
        out=args.out, max_markets=args.max_markets,
        min_request_interval=args.min_request_interval)
    print(_summary_line(summary))
    if summary["path"]:
        print(f"[hf_burst] -> {summary['path']}")
    return 0 if summary["completeness_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
