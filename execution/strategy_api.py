"""execution.strategy_api — the Strategy contract the paper broker drives.

A Strategy is a pure proposer: given a small read-only view of the current tape
(`TapeContext`), it returns a list of `Order`s it would place. It does NOT fill,
book, or persist anything — the PaperBroker owns that (separation of concerns, so
a strategy can be unit-tested with zero I/O and the fill/ledger machinery is
shared across all strategies).

SHADOW_REGISTRY is POPULATED as of Q22 with the S14 "ladder overround
underwriting" shadow strategy (execution.strategies.s14_ladder_underwriting),
whose Q13 fill-sim (scripts/s14_ladder_fillsim.py) defined its universe and
member selection. It is a REAL proposer over already-committed tape — its fills
are resolved by the deterministic S14 seller rule on cached (committed) candle
summaries, never fabricated. We still do NOT ship a placeholder: every registered
strategy must be a genuine, tape-grounded proposer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Protocol, runtime_checkable

from execution.schema import Order


@dataclass
class TapeContext:
    """The read-only view a strategy sees for one decision. `records_by_family`
    maps a tape family name (e.g. 'orderbook_depth', 'sports_pairs') to the list
    of records available to the strategy at `now_ts`. A strategy must treat these
    as immutable inputs."""

    records_by_family: Dict[str, List[dict]] = field(default_factory=dict)
    now_ts: str = ""


@runtime_checkable
class Strategy(Protocol):
    """A paper strategy. `name` identifies it in the ledger (Order.strategy);
    `propose_orders` returns the orders it would place given the tape context.
    Implementations must be pure (no network, no clock beyond context.now_ts, no
    persistence)."""

    name: str

    def propose_orders(self, context: TapeContext) -> List[Order]:
        ...


# Q22: registered with the S14 ladder-underwriting shadow strategy. The import is
# kept module-light on purpose — the strategy module pulls in only pure helpers
# (no network client) so importing strategy_api never touches the network.
from execution.strategies.s14_ladder_underwriting import S14LadderUnderwriting

SHADOW_REGISTRY: Dict[str, Strategy] = {
    "s14_ladder_underwriting": S14LadderUnderwriting(),
}
