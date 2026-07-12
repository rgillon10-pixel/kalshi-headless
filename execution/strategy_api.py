"""execution.strategy_api — the Strategy contract the paper broker drives.

A Strategy is a pure proposer: given a small read-only view of the current tape
(`TapeContext`), it returns a list of `Order`s it would place. It does NOT fill,
book, or persist anything — the PaperBroker owns that (separation of concerns, so
a strategy can be unit-tested with zero I/O and the fill/ledger machinery is
shared across all strategies).

SHADOW_REGISTRY is deliberately EMPTY this milestone. Real shadow strategies get
registered here by queue item Q22, once the Q13/Q19 analyses have defined their
parameters (bid offsets, universe, sizing). Until then the paper sub-pass has
nothing to run and is a no-op — an empty registry means "no strategies proposed,
nothing filled, ledger untouched", which is the honest state before any edge is
proven. We do NOT ship a placeholder strategy: a made-up strategy proposing
orders would put fabricated fills into the committed ledger.
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


# Q22 registers real shadow strategies here once Q13/Q19 define their parameters.
# EMPTY == the paper sub-pass is a no-op (see module docstring). Do not add a
# placeholder strategy — a fabricated proposer would write fabricated fills to the
# committed ledger.
SHADOW_REGISTRY: Dict[str, Strategy] = {}
