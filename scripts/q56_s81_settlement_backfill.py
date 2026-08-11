#!/usr/bin/env python3
"""Q56 / S81 — settlement backfill for the crypto-hourly legs `crypto_hourly` never paired.

Why this exists (LOOP-QUEUE.md Q56, "Owed next (1)")
---------------------------------------------------
S81's binding test (`scripts/q56_s81_funding_regime_settlement_probe.py`, pre-registered and
hash-sealed at `PREREG_SHA256 = edde1f66...`) is gate-SHUT on data adequacy, and the
2026-08-10 measurement (L327, `findings/2026-08-10-q56-s81-join-cell-adequacy.md`) located the
wall precisely: it is the JOIN, not the funding tape.  `crypto_hourly`'s settlement is
EMBEDDED — each capture's `previous_settlement` reports ONLY the event that closed immediately
before that capture — so an entry snapshot is settlement-joinable only if another capture
happens to land in the hour after its event closes.  When the capture cadence fell ~8x in
mid-July, the joinable population fell with it.

The unjoinable snapshots are not lost data: they name concrete, long-settled `KXBTC-*` /
`KXETH-*` bracket tickers whose results Kalshi's PUBLIC, UNAUTHENTICATED `/markets/{ticker}`
endpoint still serves.  This module pulls them into a declared settlement family so the
existing `core.settlement_sources` registry can resolve them like any other.

Selection rule (declared here, before any result is read — and it is EXHAUSTIVE)
-------------------------------------------------------------------------------
Pull **every** unjoinable `leg_ticker` the sealed probe's own outcome-blind candidate path
produces: every cell (`informative`, `control`, `excluded`), fillable and non-fillable alike,
in sorted order, with no early stop that depends on what came back.

This is load-bearing, not bookkeeping.  A backfill that chose WHICH missing settlements to
fetch could bias a sealed probe's population without touching one byte of the probe.  An
exhaustive, pre-declared, outcome-independent rule cannot: the only thing this module decides
is *whether a ticker's outcome is known at all*, never *which outcome makes the cut*.  The
`--max-tickers` cap exists only as a byte/rate guard; it truncates the SORTED list (a
deterministic, outcome-blind prefix) and is reported in the artifact when it binds.

Discipline
----------
* Read-only, GET-only, unauthenticated public endpoint.  No credentials, no order path, no
  writes outside `tape/q56_settlement_cache/`.  Never imports anything under `execution/`.
* Results are cached **VERBATIM** (L52): `scalar`, empty and `active` rows are kept exactly as
  they arrived; binary classification is delegated to `core.settlement.is_binary_result`
  downstream and is never re-derived here as a local `== "scalar"` test.
* Honest completeness: a per-ticker fetch failure LOWERS `completeness` and leaves the ticker
  ABSENT from `markets`.  A failed fetch is never written as a null result, and a partial pull
  never reports as a whole one.
* Idempotent and additive (append-only tape discipline): re-running merges into an existing
  same-day artifact.  A ticker already carrying a binary result is never downgraded by a later
  weaker read (`finalized`/`yes` cannot become `active`/``).
* The sealed probe is IMPORTED, never modified and never re-derived (L36).  Only its
  outcome-blind path is touched: `load_crypto_records` -> `funding_hours` -> `regime_runs` ->
  `candidate_rows` -> `settled_ticker_set` (a MEMBERSHIP set; the direction is dropped inside
  the probe).  `outcome_map()` / `score_rows()` are never called from this module.

Artifact
--------
`tape/q56_settlement_cache/settlement-s81-<UTCDATE>.json`, in the same `CACHE_MARKETS_MAP`
shape `core/settlement_sources.py` already reads for the five `q*_settlement_cache` families,
declared there as source `q56_settlement_cache` (so it is visible to every future coverage
scan, per L300 — a family that exists but is undeclared is exactly the L165 failure that
module was built to end).

Reproduce::

    python3 scripts/q56_s81_settlement_backfill.py --dry-run      # count only, no network
    python3 scripts/q56_s81_settlement_backfill.py                # the pull
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.settlement import is_binary_result, normalize_result  # noqa: E402
from scripts import q56_s81_funding_regime_settlement_probe as PROBE  # noqa: E402

SCHEMA_VERSION = "q56_settlement_cache.v1"
PRICE_SOURCE_TAG = "broker_truth"
CACHE_DIR = REPO_ROOT / "tape" / "q56_settlement_cache"
QUEUE_ITEM = "Q56"
SELECTION_RULE = (
    "EXHAUSTIVE and outcome-blind: every unjoinable leg_ticker produced by the sealed S81 "
    "probe's own candidate path (all cells, fillable and non-fillable), sorted, no early "
    "stop dependent on any fetched result."
)
KEPT_FIELDS: Tuple[str, ...] = ("result", "status", "close_time", "event_ticker")


# --------------------------------------------------------------------------- #
# selection (outcome-blind, via the sealed probe's own functions)
# --------------------------------------------------------------------------- #
def unjoinable_leg_tickers(crypto_source: object = PROBE.CRYPTO_GLOB,
                           funding_source: object = PROBE.FUNDING_GLOB
                           ) -> Tuple[List[str], Dict[str, object]]:
    """The selection set: leg tickers with no binary result in ANY declared family today.

    Outcome-blind by construction — `settled_ticker_set` returns MEMBERSHIP only.
    """
    hours = PROBE.funding_hours(funding_source)
    runs = PROBE.regime_runs(hours)
    rows = PROBE.candidate_rows(PROBE.load_crypto_records(crypto_source), runs)
    tickers = sorted({r["leg_ticker"] for r in rows if r.get("leg_ticker")})
    settled, coverage = PROBE.settled_ticker_set(tickers)
    unjoinable = sorted(t for t in tickers if t not in settled)
    by_cell: Dict[str, int] = {}
    by_cell_fillable: Dict[str, int] = {}
    unjoinable_set = set(unjoinable)
    for row in rows:
        if row.get("leg_ticker") in unjoinable_set:
            cell = str(row.get("cell"))
            by_cell[cell] = by_cell.get(cell, 0) + 1
            if row.get("leg_fillable"):
                by_cell_fillable[cell] = by_cell_fillable.get(cell, 0) + 1
    stats = {
        "n_entry_rows": len(rows),
        "n_distinct_leg_tickers": len(tickers),
        "n_already_settled": len(settled),
        "n_unjoinable": len(unjoinable),
        "unjoinable_entry_rows_by_cell": dict(sorted(by_cell.items())),
        "unjoinable_fillable_entry_rows_by_cell": dict(sorted(by_cell_fillable.items())),
        "settlement_coverage_before": coverage,
    }
    return unjoinable, stats


# --------------------------------------------------------------------------- #
# fetch (the only network path)
# --------------------------------------------------------------------------- #
def make_public_fetcher(min_interval: float = 0.25) -> Callable[[str], Mapping]:
    """Read-only, UNAUTHENTICATED public `GET /markets/{ticker}` through the shared client.

    No new HTTP stack, no credentials: `validation.v3_market.Kalshi` already throttles and
    retries 429/5xx; the extra loop here is the L40 self-wrapped ConnectionError retry the
    Q51 cache builder uses.
    """
    import requests  # local import so the offline test path never needs it

    from validation.v3_market import Kalshi, _load_venue_cfg

    client = Kalshi(_load_venue_cfg()["api_base"], min_interval=min_interval)

    def fetch(ticker: str) -> Mapping:
        last: Optional[BaseException] = None
        for attempt in range(4):
            try:
                blob = client.get(f"/markets/{ticker}") or {}
                return blob.get("market") or {}
            except (requests.ConnectionError, ConnectionError) as exc:  # pragma: no cover
                last = exc
                time.sleep(min(2 ** attempt, 8))
        raise last if last is not None else RuntimeError("unreachable")

    return fetch


def _keep(market: Mapping) -> Dict[str, Optional[str]]:
    """VERBATIM (L52): whatever the venue said, unclassified, unedited."""
    return {k: market.get(k) for k in KEPT_FIELDS}


def _is_stronger(new: Mapping, old: Optional[Mapping]) -> bool:
    """Never downgrade: a stored binary result beats any later weaker read."""
    if old is None:
        return True
    if is_binary_result(old.get("result")):
        return False
    return True


# --------------------------------------------------------------------------- #
# the backfill
# --------------------------------------------------------------------------- #
def load_existing(cache_path: Path) -> Dict[str, object]:
    if not cache_path.exists():
        return {}
    try:
        blob = json.loads(cache_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return blob if isinstance(blob, dict) else {}


def classify(markets: Mapping[str, Mapping]) -> Dict[str, int]:
    binary = non_binary = listed = 0
    for rec in markets.values():
        result = rec.get("result") if isinstance(rec, Mapping) else None
        if is_binary_result(result):
            binary += 1
        elif normalize_result(result):
            non_binary += 1
        else:
            listed += 1
    return {"n_binary": binary, "n_non_binary": non_binary, "n_listed_unsettled": listed}


def backfill(tickers: Sequence[str],
             fetcher: Callable[[str], Mapping],
             cache_path: Path,
             *,
             max_tickers: Optional[int] = None,
             selection_stats: Optional[Mapping[str, object]] = None,
             now_iso: Optional[str] = None,
             progress_every: int = 25) -> Dict[str, object]:
    """Fetch every requested ticker, merge into `cache_path`, return the written payload."""
    requested = sorted(set(t for t in tickers if isinstance(t, str) and t))
    capped = requested if max_tickers is None else requested[:max_tickers]

    existing = load_existing(cache_path)
    markets: Dict[str, Dict[str, Optional[str]]] = {}
    prior = existing.get("markets")
    if isinstance(prior, Mapping):
        for ticker, rec in prior.items():
            if isinstance(ticker, str) and isinstance(rec, Mapping):
                markets[ticker] = dict(rec)
    n_prior = len(markets)

    fetched = 0
    errors: Dict[str, int] = {}
    for i, ticker in enumerate(capped):
        try:
            market = fetcher(ticker)
        except Exception as exc:  # noqa: BLE001 - a failure LOWERS completeness, never fakes
            name = type(exc).__name__
            errors[name] = errors.get(name, 0) + 1
            continue
        if not isinstance(market, Mapping):
            errors["NonMappingResponse"] = errors.get("NonMappingResponse", 0) + 1
            continue
        fetched += 1
        record = _keep(market)
        if _is_stronger(record, markets.get(ticker)):
            markets[ticker] = record
        if progress_every and (i + 1) % progress_every == 0:
            print(f"[q56:backfill] {i + 1}/{len(capped)}", file=sys.stderr)

    payload: Dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "price_source_tag": PRICE_SOURCE_TAG,
        "source": "public_markets_by_ticker",
        "queue_item": QUEUE_ITEM,
        "pulled_at": now_iso or datetime.now(timezone.utc).isoformat(),
        "selection_rule": SELECTION_RULE,
        "completeness": {
            "n_requested": len(requested),
            "n_attempted": len(capped),
            "n_fetched": fetched,
            "n_failed": len(capped) - fetched,
            "completeness": (fetched / len(capped)) if capped else 0.0,
            "cap_bound": max_tickers is not None and len(capped) < len(requested),
            "errors": dict(sorted(errors.items())),
            "n_markets_before": n_prior,
            "n_markets_after": len(markets),
            **classify(markets),
        },
        "selection": dict(selection_stats or {}),
        "markets": dict(sorted(markets.items())),
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                          encoding="utf-8")
    return payload


def default_cache_path(day: Optional[str] = None) -> Path:
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return CACHE_DIR / f"settlement-s81-{day}.json"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--max-tickers", type=int, default=None,
                    help="byte/rate guard only; truncates the SORTED (outcome-blind) list")
    ap.add_argument("--min-interval", type=float, default=0.25)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the selection set size and exit; makes NO network call")
    args = ap.parse_args(argv)

    tickers, stats = unjoinable_leg_tickers()
    print(f"Q56/S81 settlement backfill — selection {len(tickers)} unjoinable leg tickers "
          f"of {stats['n_distinct_leg_tickers']} ({stats['n_already_settled']} already settled)")
    print(f"  unjoinable entry rows by cell: {stats['unjoinable_entry_rows_by_cell']}")
    if args.dry_run:
        print("  --dry-run: no network call made")
        return 0

    out = args.out or default_cache_path()
    payload = backfill(tickers, make_public_fetcher(args.min_interval), out,
                       max_tickers=args.max_tickers, selection_stats=stats)
    comp = payload["completeness"]
    print(f"  fetched {comp['n_fetched']}/{comp['n_attempted']} "
          f"(completeness {comp['completeness']:.4f}, failed {comp['n_failed']}, "
          f"errors {comp['errors']})")
    print(f"  markets {comp['n_markets_before']} -> {comp['n_markets_after']}: "
          f"binary {comp['n_binary']} / non-binary {comp['n_non_binary']} / "
          f"listed-unsettled {comp['n_listed_unsettled']}")
    print(f"  wrote {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
