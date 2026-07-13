"""execution.paper_broker — the paper-trading broker (PAPER TIER, no network).

`PaperBroker` simulates order submission, filling, position/cash accounting, and
mark-to-market entirely over already-committed tape. It NEVER opens a socket,
authenticates, or emits an order anywhere. It is deterministic: constructed from
a ledger directory, its state is derived by REPLAYING the append-only ledger, so
the same ledger always reproduces the same positions, cash, and realized P&L.

SOURCE OF TRUTH: the ledger JSONL is authoritative. `paper/state.json` may be
written as a convenience cache (fast startup, phone-note snapshot) but is NEVER
read back as truth — `_replay()` always rebuilds from the ledger lines. If the
cache and a ledger replay ever disagree, the ledger wins by construction (we
simply never trust the cache). This mirrors tape/ discipline: the append-only log
is the record; any derived snapshot is disposable.

ACCOUNTING (dollars, per-contract prices):
  * A BUY fill of q contracts at price p with fee f: cash -= p*q + f; the open lot
    grows and avg_cost is the fee-inclusive weighted average entry.
  * A SELL fill of q contracts at price p with fee f against an open long: cash +=
    p*q - f; realized_pnl += (p - avg_cost)*q - f (avg_cost already carries the
    entry-side fee). Selling more than the open qty is clamped to the open qty and
    flagged (paper has no short model this milestone — an over-sell is a strategy
    bug, surfaced, not silently shorted).

MARK-TO-MARKET marks a long at its LIQUIDATION side (the price we could exit at):
long YES at yes_bid, long NO at no_bid — never the ask (marking a long at the ask
we bought at would book unrealized profit we cannot actually capture). Exit fees
are reported SEPARATELY (est_exit_fees) and NOT subtracted from the gross mark, so
mtm_value stays a clean gross-liquidation number and net_liq = mtm_value + cash -
est_exit_fees is the honest cash-out figure. Every mark records the
price_source_tag it used (real_bid for a bid-based liquidation mark).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.pricing import TAKER_FEE_RATE, fee_per_contract
from execution.limits import check_order
from execution.schema import (Fill, Order, Position, Settlement,
                              line_to_record, record_to_line)

STARTING_CASH = 0.0  # paper starts flat; P&L is measured relative to zero.


class PaperBroker:
    """Deterministic paper broker. Construct from a ledger dir; state is a pure
    function of the ledger lines under it."""

    def __init__(self, ledger_dir: Path, starting_cash: float = STARTING_CASH) -> None:
        self.ledger_dir = Path(ledger_dir)
        self.starting_cash = float(starting_cash)
        # derived state (rebuilt by _replay)
        self.positions: Dict[Tuple[str, str], Position] = {}
        self.cash: float = self.starting_cash
        self.realized_pnl: float = 0.0
        self.orders_today: int = 0
        self.settled_contracts: int = 0
        # (ticker, side) settlements that arrived with no open position to close —
        # surfaced honestly (never crashed) though normal operation never hits it.
        self.settlement_noops: List[Tuple[str, str]] = []
        self._replay()

    # ----------------------------------------------------------------- replay
    def _ledger_files(self) -> List[Path]:
        if not self.ledger_dir.exists():
            return []
        return sorted(self.ledger_dir.glob("dt=*.jsonl"))

    def _read_records(self) -> List[Any]:
        recs: List[Any] = []
        for path in self._ledger_files():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    rec = line_to_record(line)
                    if rec is not None:
                        recs.append(rec)
        return recs

    def _replay(self) -> None:
        """Rebuild ALL derived state from the append-only ledger. Deterministic:
        same ledger lines -> same state. Orders are counted per current UTC day
        for the daily-order cap; fills mutate positions/cash/realized P&L."""
        self.positions = {}
        self.cash = self.starting_cash
        self.realized_pnl = 0.0
        self.settled_contracts = 0
        self.settlement_noops = []
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        orders_today = 0
        for rec in self._read_records():
            if isinstance(rec, Order):
                if rec.ts[:10] == today:
                    orders_today += 1
            elif isinstance(rec, Fill):
                self._apply_fill(rec)
            elif isinstance(rec, Settlement):
                self._apply_settlement(rec)
        self.orders_today = orders_today

    def _apply_fill(self, fill: Fill) -> None:
        key = (fill.ticker, fill.side)
        pos = self.positions.get(key) or Position(ticker=fill.ticker, side=fill.side)
        if fill.action == "buy":
            gross = fill.price * fill.qty + fill.fee
            self.cash -= gross
            new_qty = pos.qty + fill.qty
            # fee-inclusive weighted average entry cost
            pos.avg_cost = ((pos.avg_cost * pos.qty) + gross) / new_qty if new_qty else 0.0
            pos.qty = new_qty
        else:  # sell — close against the open long (no shorting this milestone)
            close_qty = min(fill.qty, pos.qty)
            proceeds = fill.price * close_qty - fill.fee
            self.cash += proceeds
            realized = (fill.price - pos.avg_cost) * close_qty - fill.fee
            pos.realized_pnl += realized
            self.realized_pnl += realized
            pos.qty -= close_qty
            if pos.qty == 0:
                pos.avg_cost = 0.0
        self.positions[key] = pos

    def _apply_settlement(self, s: Settlement) -> None:
        """Forced close of an open long at the venue's expiry value (0.0 or 1.0),
        ZERO fee (a settlement charges no trading fee). This mirrors the SELL
        accounting in _apply_fill — realized = (settle_value - avg_cost) * qty —
        but deliberately does NOT route through _apply_fill, because Fill forbids a
        0.0/1.0 price (it is a market print, not an expiry). A settlement is the
        one place that boundary value is legitimate (broker_truth).

        No open position for (ticker, side) -> a no-op, surfaced via
        settlement_noops rather than crashed (fault isolation). In normal
        operation a settlement only ever follows its own fill in the same ledger."""
        key = (s.ticker, s.side)
        pos = self.positions.get(key)
        if pos is None or pos.qty <= 0:
            self.settlement_noops.append(key)
            return
        close_qty = min(s.qty, pos.qty)
        self.cash += s.settle_value * close_qty
        realized = (s.settle_value - pos.avg_cost) * close_qty
        pos.realized_pnl += realized
        self.realized_pnl += realized
        pos.qty -= close_qty
        self.settled_contracts += close_qty
        if pos.qty == 0:
            pos.avg_cost = 0.0
        self.positions[key] = pos

    # ------------------------------------------------------------------ submit
    def submit(self, orders: List[Order],
               tape_records: List[Dict[str, Any]],
               fill_fn=None) -> Dict[str, Any]:
        """Validate `orders` against limits, attempt fills via `fill_fn`, and
        append accepted orders + resulting fills to today's ledger file.

        `fill_fn(order, tape_records) -> Fill|None` is injected (default: the
        taker-depth/BBO model). Rejected orders (schema-invalid or cap-violating)
        are NOT written to the ledger and are returned under 'rejected' with their
        reasons — an honest accounting, never a silent drop.

        Returns a summary dict: accepted order_ids, fills, rejections. Appends to
        the ledger in place, then re-derives state via _replay (so post-submit
        state is always a ledger replay, never an in-memory shortcut)."""
        if fill_fn is None:
            fill_fn = _default_fill_fn

        accepted: List[Order] = []
        fills: List[Fill] = []
        rejected: List[Dict[str, Any]] = []

        # start from the already-open notional / order count so caps compose
        open_notional = self.open_notional()
        orders_today = self.orders_today

        for order in orders:
            schema_errs = order.validate()
            if schema_errs:
                rejected.append({"order_id": order.order_id, "reasons": schema_errs})
                continue
            violations = check_order(order, open_notional, orders_today)
            if violations:
                rejected.append({"order_id": order.order_id, "reasons": violations})
                continue
            accepted.append(order)
            orders_today += 1
            open_notional += order.limit_price * order.qty
            fill = fill_fn(order, tape_records)
            if fill is not None:
                errs = fill.validate()
                if errs:  # a fill model must never emit an invalid/synthetic fill
                    rejected.append({"order_id": order.order_id,
                                     "reasons": [f"fill invalid: {e}" for e in errs]})
                    accepted.pop()
                    orders_today -= 1
                    open_notional -= order.limit_price * order.qty
                    continue
                fills.append(fill)

        self._append(accepted, fills)
        self._replay()
        return {
            "accepted": [o.order_id for o in accepted],
            "fills": [f.fill_id for f in fills],
            # the actual Fill objects booked this call, so a caller can build the
            # matching Settlement legs authoritatively (which legs really filled)
            # without recomputing the fill model.
            "fill_records": fills,
            "rejected": rejected,
            "n_accepted": len(accepted), "n_fills": len(fills), "n_rejected": len(rejected),
        }

    def _append(self, orders: List[Order], fills: List[Fill]) -> Optional[Path]:
        """Append accepted orders then their fills to today's ledger file. Never
        rewrites or reorders existing lines (tape/ discipline)."""
        if not orders and not fills:
            return None
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        path = self.ledger_dir / f"dt={day}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            for o in orders:
                f.write(record_to_line(o) + "\n")
            for fl in fills:
                f.write(record_to_line(fl) + "\n")
        return path

    def _append_settlements(self, settlements: List[Settlement]) -> Optional[Path]:
        """Append settlement lines to today's ledger file. Called AFTER any fills
        in the same run so a settlement always lands as a LATER line than the fill
        it closes — replay then applies fill-then-settle in file order. Append-only:
        never rewrites or reorders existing lines (tape/ discipline)."""
        if not settlements:
            return None
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        path = self.ledger_dir / f"dt={day}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            for s in settlements:
                f.write(record_to_line(s) + "\n")
        return path

    # ---------------------------------------------------------------- settle
    def settle(self, settlements: List[Settlement]) -> Dict[str, Any]:
        """Book a batch of venue-truth settlements against open positions. Each is
        validated; an INVALID settlement is never written and is returned under
        'rejected' with its reasons (honest accounting, never a silent drop). Valid
        settlements are appended AFTER any fills already written this run, then
        state is re-derived by _replay (so post-settle state is a ledger replay,
        never an in-memory shortcut). Returns a summary dict."""
        valid: List[Settlement] = []
        rejected: List[Dict[str, Any]] = []
        for s in settlements:
            errs = s.validate()
            if errs:
                rejected.append({"settlement_id": s.settlement_id, "reasons": errs})
                continue
            valid.append(s)

        self._append_settlements(valid)
        self._replay()
        return {
            "settled": [s.settlement_id for s in valid],
            "rejected": rejected,
            "n_settled": len(valid), "n_rejected": len(rejected),
        }

    # ---------------------------------------------------------- state readers
    def open_notional(self) -> float:
        """Total open exposure in dollars, valued at entry cost (avg_cost * qty)."""
        return sum(p.avg_cost * p.qty for p in self.positions.values() if p.qty > 0)

    def open_positions(self) -> List[Position]:
        return [p for p in self.positions.values() if p.qty != 0]

    # ------------------------------------------------------- mark to market
    def mark_to_market(self, latest_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Mark every open long at its liquidation (bid) side. Returns explicit
        fields: mtm_value (gross liquidation value of open longs), est_exit_fees
        (taker fee to exit at the mark, reported separately — NOT netted into
        mtm_value), cash, net_liq (= mtm_value + cash - est_exit_fees), and a
        per-position breakdown recording the price_source_tag used for each mark.

        A position with no available liquidation bid in `latest_records` is marked
        at avg_cost with tag 'stale_no_bid' and flagged — never dropped, never
        marked at a fabricated price."""
        bids = _bids_by_ticker(latest_records)
        mtm_value = 0.0
        est_exit_fees = 0.0
        marks: List[Dict[str, Any]] = []
        for pos in self.open_positions():
            if pos.qty <= 0:
                continue  # no short model this milestone
            bid = bids.get((pos.ticker, pos.side))
            if bid is None or bid[0] is None:
                mark_price = round(pos.avg_cost, 2)
                tag = "stale_no_bid"
                fee = 0.0
            else:
                mark_price = round(float(bid[0]), 2)
                tag = bid[1]
                fee = fee_per_contract(mark_price, rate=TAKER_FEE_RATE) * pos.qty
            gross = mark_price * pos.qty
            mtm_value += gross
            est_exit_fees += fee
            marks.append({
                "ticker": pos.ticker, "side": pos.side, "qty": pos.qty,
                "avg_cost": round(pos.avg_cost, 4), "mark_price": mark_price,
                "gross_mark": round(gross, 4), "est_exit_fee": round(fee, 4),
                "price_source_tag": tag,
            })
        net_liq = mtm_value + self.cash - est_exit_fees
        return {
            "mtm_value": round(mtm_value, 4),
            "cash": round(self.cash, 4),
            "est_exit_fees": round(est_exit_fees, 4),
            "net_liq": round(net_liq, 4),
            "realized_pnl": round(self.realized_pnl, 4),
            "marks": marks,
        }

    # ---------------------------------------------------------- state cache
    def write_state_snapshot(self, path: Optional[Path] = None) -> Path:
        """Write the disposable `paper/state.json` cache. Documented as NEVER a
        source of truth — _replay always rebuilds from the ledger. Provided for a
        fast phone-note snapshot only."""
        path = Path(path) if path is not None else self.ledger_dir.parent / "state.json"
        snapshot = {
            "cash": round(self.cash, 4),
            "realized_pnl": round(self.realized_pnl, 4),
            "open_notional": round(self.open_notional(), 4),
            "positions": [p.to_dict() for p in self.open_positions()],
            "written_at": datetime.now(timezone.utc).isoformat(),
            "note": "disposable cache — ledger JSONL is the source of truth, not this file",
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
        return path

    # ---------------------------------------------------------- phone summary
    def daily_summary(self) -> str:
        """One plain-English line for a phone note: open positions, realized P&L."""
        n_open = len(self.open_positions())
        return (f"paper: {n_open} open position(s), {self.settled_contracts} settled "
                f"contract(s), realized P&L ${self.realized_pnl:+.2f}, "
                f"cash ${self.cash:+.2f}, open notional ${self.open_notional():.2f}")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _default_fill_fn(order: Order, tape_records: List[Dict[str, Any]]):
    """Default submit fill model: try taker_immediate against the first tape
    record that matches the order's ticker (or the first depth record). Injected
    in tests to isolate broker accounting from fill-model behavior."""
    from execution.fill_models import taker_immediate
    for rec in tape_records:
        if rec.get("ticker") == order.ticker or _record_mentions(rec, order.ticker):
            fill = taker_immediate(order, rec)
            if fill is not None:
                return fill
    return None


def _record_mentions(record: Dict[str, Any], ticker: str) -> bool:
    return any(o.get("ticker") == ticker for o in record.get("outcomes") or [])


def _bids_by_ticker(records: List[Dict[str, Any]]
                    ) -> Dict[Tuple[str, str], Tuple[Optional[float], str]]:
    """Map (ticker, side) -> (liquidation_bid_price, price_source_tag) from a mix
    of orderbook_depth and sports_pairs records. Long YES liquidates at yes_bid,
    long NO at no_bid. A live bid is tagged real_bid (lesson L24)."""
    out: Dict[Tuple[str, str], Tuple[Optional[float], str]] = {}

    def _put(ticker: str, yes_bid, no_bid, tag: str) -> None:
        if yes_bid is not None:
            out[(ticker, "yes")] = (float(yes_bid), tag)
        if no_bid is not None:
            out[(ticker, "no")] = (float(no_bid), tag)

    for rec in records:
        if "best_yes_bid" in rec or "best_no_bid" in rec:  # orderbook_depth.v1
            tag = (rec.get("price_source_tags") or {}).get("bids", "real_bid")
            _put(rec.get("ticker", ""), rec.get("best_yes_bid"), rec.get("best_no_bid"), tag)
        for o in rec.get("outcomes") or []:  # sports_pairs.v1
            # a live BBO bid is a real fillable maker-side price (lesson L24)
            _put(o.get("ticker", ""), o.get("yes_bid"), o.get("no_bid"), "real_bid")
    return out
