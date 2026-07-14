#!/usr/bin/env python3
"""paper_pass.py — the PAPER-TIER paper-trading pass (NO network anywhere).

Drives every strategy in execution.strategy_api.SHADOW_REGISTRY over
already-committed tape and books the results into the append-only paper ledger
(paper/ledger/dt=<today>.jsonl). Pure simulation: it reads committed crypto_hourly
tape and the committed S14 candle-summary cache (reading a committed tape file is
NOT a network call), proposes orders, resolves fills by the deterministic S14
seller rule, settles the filled legs at broker-truth expiry values, and records
everything through the PaperBroker. No socket is ever opened; no order leaves the
process (CLAUDE.md execution lane, paper tier).

PER-EVENT ATOMICITY & HONEST ACCOUNTING
  * The event universe = event-hours that have an earliest capture AND a
    broker-truth settlement AND FULL candle coverage (every member the strategy
    would order is present in the committed cache). An event missing coverage is
    DEFERRED('coverage') and counted — never fetched (this pass has no network).
  * Idempotency is derived from ledger CONTENT: an event whose event_ticker
    already appears on an Order line for this strategy is skipped. Re-running the
    pass never double-books.
  * Each event is processed all-or-nothing. Before submitting an event's batch we
    pre-check the WHOLE batch against the remaining daily-order and open-notional
    caps (execution.limits, read-only). A batch that does not fit is
    DEFERRED('caps') and counted; a later, smaller event may still fit
    (deterministic, sorted order). The daily-order cap is EXPECTED to bite on the
    first run and defer most of the backlog — that is the honest outcome (the
    backlog drains ~MAX_DAILY_ORDERS orders/day over subsequent runs). We do NOT
    back-date orders to evade the cap.
  * Order.ts = now, so the whole backlog counts against TODAY's daily cap.

Run:
    python scripts/paper_pass.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.io import REPO_ROOT  # noqa: E402
from execution.fill_models import resting_short_yes_as_no_fill  # noqa: E402
from execution.limits import (MAX_DAILY_ORDERS,  # noqa: E402  (read-only import)
                             MAX_OPEN_NOTIONAL_DOLLARS)
from execution.paper_broker import PaperBroker  # noqa: E402
from execution.schema import Order, Settlement  # noqa: E402
from execution.strategy_api import SHADOW_REGISTRY, TapeContext  # noqa: E402
from scripts.s14_ladder_fillsim import (build_settlement_map,  # noqa: E402
                                       load_candle_summary_cache, load_records)

TAPE_DIR = REPO_ROOT / "tape" / "crypto_hourly"
CACHE_DIR = REPO_ROOT / "tape" / "s14_ladder_fillsim"
LEDGER_DIR = REPO_ROOT / "paper" / "ledger"
FAMILY = "crypto_hourly"


def _fill_fn_factory(cache: Dict[str, Dict[str, Any]]) -> Callable[[Order, List], Optional[Any]]:
    """Build the injected fill_fn for broker.submit. Resolves each buy-NO order's
    fill via the S14 seller rule on the committed candle summary keyed by ticker.
    Ignores tape_records (the S14 fill lives in the candle cache, not a BBO book)."""
    def fill_fn(order: Order, _tape_records: List) -> Optional[Any]:
        return resting_short_yes_as_no_fill(order, cache.get(order.ticker))
    return fill_fn


def _already_processed_events(broker: PaperBroker, strategy_name: str) -> set:
    """The set of event_tickers this strategy has already written Order lines for
    (idempotency derived from ledger content, not a separate state file)."""
    done = set()
    for rec in broker._read_records():
        if isinstance(rec, Order) and rec.strategy == strategy_name:
            done.add(rec.event_ticker)
    return done


def run_strategy(strategy, context: TapeContext, records: List[Dict[str, Any]],
                 cache: Dict[str, Dict[str, Any]], broker: PaperBroker) -> Dict[str, Any]:
    """Process one strategy's proposed orders event-by-event into the broker's
    ledger. Returns a per-strategy accounting dict."""
    settle = build_settlement_map(records)
    proposed = strategy.propose_orders(context)

    # group proposed orders by their event ladder (all-or-nothing per event)
    by_event: Dict[str, List[Order]] = defaultdict(list)
    for o in proposed:
        by_event[o.event_ticker].append(o)

    already = _already_processed_events(broker, strategy.name)
    fill_fn = _fill_fn_factory(cache)

    n_processed = n_defer_caps = n_defer_cov = n_already = 0
    for event_ticker in sorted(by_event):
        batch = by_event[event_ticker]
        if event_ticker in already:
            n_already += 1
            continue
        # coverage: every ordered member must have a committed candle summary
        if not all(o.ticker in cache for o in batch):
            n_defer_cov += 1
            continue
        # caps pre-check on the WHOLE batch (read-only caps from execution.limits)
        batch_notional = sum(o.limit_price * o.qty for o in batch)
        fits_daily = broker.orders_today + len(batch) <= MAX_DAILY_ORDERS
        fits_notional = broker.open_notional() + batch_notional <= MAX_OPEN_NOTIONAL_DOLLARS
        if not (fits_daily and fits_notional):
            n_defer_caps += 1
            continue

        res = broker.submit(batch, tape_records=[], fill_fn=fill_fn)
        winner_ticker = settle[event_ticker]["winner_ticker"]
        settlements: List[Settlement] = []
        for f in res["fill_records"]:
            member = f.ticker
            is_winner = member == winner_ticker
            settlements.append(Settlement(
                settlement_id=f"{strategy.name}:{event_ticker}:{member}:S",
                ts=context.now_ts, ticker=member, side="no",
                settle_value=0.0 if is_winner else 1.0, qty=1,
                event_ticker=event_ticker, price_source_tag="broker_truth"))
        if settlements:
            broker.settle(settlements)
        n_processed += 1

    return {
        "strategy": strategy.name,
        "n_processed": n_processed,
        "n_deferred_caps": n_defer_caps,
        "n_deferred_coverage": n_defer_cov,
        "n_already": n_already,
    }


def run_pass(tape_dir: Path = TAPE_DIR, cache_dir: Path = CACHE_DIR,
             ledger_dir: Path = LEDGER_DIR, now_ts: Optional[str] = None) -> Dict[str, Any]:
    """One paper pass over committed tape. Returns a summary dict; safe to re-run
    (idempotent per event)."""
    now_ts = now_ts or datetime.now(timezone.utc).isoformat()
    records = load_records(tape_dir)
    cache = load_candle_summary_cache(cache_dir)
    broker = PaperBroker(ledger_dir, as_of=now_ts)
    context = TapeContext(records_by_family={FAMILY: records}, now_ts=now_ts)

    per_strategy: List[Dict[str, Any]] = []
    for name in sorted(SHADOW_REGISTRY):
        per_strategy.append(run_strategy(SHADOW_REGISTRY[name], context, records,
                                        cache, broker))

    return {
        "now_ts": now_ts,
        "n_records": len(records),
        "per_strategy": per_strategy,
        "daily_summary": broker.daily_summary(),
        "realized_pnl": broker.realized_pnl,
        "broker": broker,
    }


def main(argv: Optional[List[str]] = None) -> int:
    result = run_pass()
    print("=" * 78)
    print("PAPER PASS (paper tier, no network) — SHADOW_REGISTRY over committed tape")
    print("=" * 78)
    print(f"records loaded: {result['n_records']}  now_ts={result['now_ts']}")
    for s in result["per_strategy"]:
        print(f"[{s['strategy']}] {s['n_processed']} processed, "
              f"{s['n_deferred_caps']} deferred(caps), "
              f"{s['n_deferred_coverage']} deferred(coverage), "
              f"{s['n_already']} already-in-ledger, "
              f"realized P&L ${result['realized_pnl']:+.2f}")
    print("-" * 78)
    print(result["daily_summary"])
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
