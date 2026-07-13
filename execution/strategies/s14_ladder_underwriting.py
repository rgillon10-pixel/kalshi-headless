"""execution.strategies.s14_ladder_underwriting — S14 shadow strategy (Q22).

S14 "ladder overround underwriting" (registry S14, Q13 fill-sim in
scripts/s14_ladder_fillsim.py): stand as the underwriter of a complete
mutually-exclusive Kalshi strike ladder — rest a short-YES maker offer on every
priced member at once, collect the bracket overround as premium, and pay $1 only
on the single member that settles YES.

PAPER-TIER REPRESENTATION (the load-bearing economic equivalence, worked out by
the research-lead — implemented here, not re-derived). The PaperBroker has no
short model, so a short-YES maker offer at member ask A is represented as a BUY
of NO at the real NO bid `1 - A` (a genuine fillable maker-side price, tag
real_bid), held to settlement:

  * order: side='no', action='buy', limit_price = round(1 - A, 2), qty=1, tif='rest'
  * fill (resolved later by the broker/runner, NOT here): the S14 seller rule on
    the cached YES candle (max YES high >= A and volume > 0) — identical to "the
    NO bid at 1 - A got crossed".
  * settlement (also later): the long-NO leg pays $1 if the member is NOT the
    event winner (NO wins) and $0 if it IS (NO loses).

A filled non-winner NO leg realizes A - 0.01 (== S14 member premium); a filled
winner NO leg realizes A - 1 - 0.01. Summed over filled legs this is exactly
S14's `premium_total - payout` — identical P&L.

MEMBER SELECTION (reuses s14's logic exactly): for each settled event-hour,
propose a buy-NO order for every member with yes_ask >= MIN_PRICED_ASK (0.02)
PLUS the winner member regardless of its ask (its fill drives the $1 loss leg).
Members with yes_ask < 0.02 that are not the winner net exactly $0 either way and
are omitted (fetch-budget equivalence with s14). CAVEAT: member selection uses
the broker_truth winner to include the winner leg; the omitted sub-0.02
non-winner legs have $0 P&L impact so this omission cannot change any P&L.

PURE: no network, no clock beyond context.now_ts, no persistence. It proposes
orders only — it does NOT resolve fills or settlement (the broker owns that).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List

from execution.schema import Order
# s14_ladder_fillsim is import-time network-free (its Kalshi client is lazy inside
# _client()); we reuse ONLY its pure helpers, never a fetch.
from scripts.s14_ladder_fillsim import (MIN_PRICED_ASK, build_earliest_captures,
                                       build_settlement_map)

if TYPE_CHECKING:  # annotation-only; importing at runtime would be a cycle
    from execution.strategy_api import TapeContext

FAMILY = "crypto_hourly"


class S14LadderUnderwriting:
    """S14 ladder-underwriting shadow strategy over crypto_hourly ladders."""

    name = "s14_ladder_underwriting"

    def propose_orders(self, context: "TapeContext") -> List[Order]:
        records = context.records_by_family.get(FAMILY, [])
        earliest = build_earliest_captures(records)
        settle = build_settlement_map(records)

        orders: List[Order] = []
        for event_ticker in sorted(earliest):
            settlement = settle.get(event_ticker)
            if settlement is None:
                continue  # no broker-truth winner -> cannot underwrite this ladder
            winner_ticker = settlement["winner_ticker"]
            cur = earliest[event_ticker]["current"]
            for o in cur["outcomes"]:
                member_ticker = o["ticker"]
                ask = float(o["yes_ask"])
                is_winner = member_ticker == winner_ticker
                # 1c-floor wing that is not the winner: nets $0 either way, omit it.
                if ask < MIN_PRICED_ASK and not is_winner:
                    continue
                # short-YES offer at ask A == buy NO at the real NO bid (1 - A).
                no_bid = round(1.0 - ask, 2)  # always in [0.01, 0.99] since A in [0.01, 0.99]
                orders.append(Order(
                    order_id=f"{self.name}:{event_ticker}:{member_ticker}",
                    ts=context.now_ts,
                    ticker=member_ticker,
                    side="no",
                    action="buy",
                    limit_price=no_bid,
                    qty=1,
                    tif="rest",
                    strategy=self.name,
                    event_ticker=event_ticker,
                ))
        return orders
