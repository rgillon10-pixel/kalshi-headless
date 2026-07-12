"""execution.schema — the paper-trading ledger record types (stdlib only).

Dataclasses for the paper execution spine, matching the repo's schema style
(core/sports_schema.py, core/crypto_schema.py): plain @dataclass, explicit
JSONL (de)serialization, a schema_version stamp on every persisted line.

Ledger discipline (same as tape/): append-only JSONL under
`paper/ledger/dt=<date>.jsonl`, one JSON object per line, never rewritten and
never reordered. `paper/` is committed like `tape/` (it is provenance, not a
scratch cache). A ledger line is one of two kinds — an Order or a Fill — each
carrying a `record_kind` discriminator so a single-file replay can tell them
apart and rebuild state deterministically.

Conventions honored here:
  * Prices are dollars floats (repo convention: 0.01..0.99), NOT integer cents.
  * `Fill.fee` comes from `core.pricing` at the call site (lesson L18); this
    schema only stores the resulting number, it never derives a fee.
  * `Fill.price_source_tag` is restricted to the two REAL fillable tags a paper
    fill is allowed to fill against: `real_ask` (a buy lifting a live ask) and
    `real_bid` (a sell / maker fill against a live bid ladder). `real_bid` is a
    tape-only tag namespace (lesson L24) — deliberately NOT in
    core.source_tag.VALID_SOURCE_TAGS — and these records live in JSONL, never a
    DB column, so the enum invariant is not tripped. A synthetic/modeled price is
    never a valid fill tag; validation rejects it.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "paper_ledger.v1"

VALID_SIDES = frozenset({"yes", "no"})
VALID_ACTIONS = frozenset({"buy", "sell"})
VALID_TIF = frozenset({"rest", "ioc"})

# The ONLY tags a paper fill may fill against — both are real, fillable prices.
# `real_bid` is the tape-only maker-side tag (lesson L24). A modeled price
# (`synthetic`/`midpoint`) can never be a fill price (CLAUDE.md prime directive).
VALID_FILL_PRICE_TAGS = frozenset({"real_ask", "real_bid"})


@dataclass
class Order:
    """One paper order the strategy asked to place. Persisted as a ledger line
    (record_kind='order') before any fill is attempted, so the ledger records
    intent as well as outcome."""

    order_id: str
    ts: str                 # ISO-8601 — when the strategy proposed the order
    ticker: str
    side: str               # 'yes' | 'no'
    action: str             # 'buy' | 'sell'
    limit_price: float      # dollars (0.01..0.99)
    qty: int                # contracts
    tif: str                # 'rest' | 'ioc'
    strategy: str           # strategy name that proposed it
    schema_version: str = SCHEMA_VERSION
    record_kind: str = "order"

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Order":
        return cls(
            order_id=d["order_id"], ts=d["ts"], ticker=d["ticker"], side=d["side"],
            action=d["action"], limit_price=float(d["limit_price"]), qty=int(d["qty"]),
            tif=d["tif"], strategy=d["strategy"],
            schema_version=d.get("schema_version", SCHEMA_VERSION),
        )

    def validate(self) -> List[str]:
        errs: List[str] = []
        if self.side not in VALID_SIDES:
            errs.append(f"side {self.side!r} not in {sorted(VALID_SIDES)}")
        if self.action not in VALID_ACTIONS:
            errs.append(f"action {self.action!r} not in {sorted(VALID_ACTIONS)}")
        if self.tif not in VALID_TIF:
            errs.append(f"tif {self.tif!r} not in {sorted(VALID_TIF)}")
        if not (0.01 <= self.limit_price <= 0.99):
            errs.append(f"limit_price {self.limit_price!r} outside Kalshi [0.01, 0.99]")
        if self.qty <= 0:
            errs.append(f"qty {self.qty!r} must be > 0")
        if not self.ticker.strip():
            errs.append("ticker must be non-empty")
        return errs


@dataclass
class Fill:
    """One simulated fill against already-collected tape. `fill_model` names the
    assumption used (so downstream can filter), `price_source_tag` is the REAL
    price it filled against, and `caveats` records every honesty flag (e.g.
    'size_unverified', 'no_queue_model')."""

    fill_id: str
    order_id: str
    ts: str                 # ISO-8601 — the tape observation timestamp the fill is drawn from
    ticker: str
    side: str               # 'yes' | 'no'
    action: str             # 'buy' | 'sell'
    price: float            # dollars, the fill price off the tape
    qty: int                # contracts filled (<= order qty; partials allowed)
    fee: float              # dollars, from core.pricing at the call site (lesson L18)
    fill_model: str         # 'taker_depth' | 'taker_bbo_nosize' | 'maker_candle_through'
    price_source_tag: str   # 'real_ask' | 'real_bid' — never a synthetic price
    caveats: List[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    record_kind: str = "fill"

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Fill":
        return cls(
            fill_id=d["fill_id"], order_id=d["order_id"], ts=d["ts"], ticker=d["ticker"],
            side=d["side"], action=d["action"], price=float(d["price"]), qty=int(d["qty"]),
            fee=float(d["fee"]), fill_model=d["fill_model"],
            price_source_tag=d["price_source_tag"], caveats=list(d.get("caveats", [])),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
        )

    def validate(self) -> List[str]:
        errs: List[str] = []
        if self.side not in VALID_SIDES:
            errs.append(f"side {self.side!r} not in {sorted(VALID_SIDES)}")
        if self.action not in VALID_ACTIONS:
            errs.append(f"action {self.action!r} not in {sorted(VALID_ACTIONS)}")
        if self.price_source_tag not in VALID_FILL_PRICE_TAGS:
            errs.append(
                f"price_source_tag {self.price_source_tag!r} is not a fillable real price "
                f"(must be one of {sorted(VALID_FILL_PRICE_TAGS)}) — a paper fill may never "
                f"fill against a synthetic/modeled price (CLAUDE.md prime directive)")
        if not (0.01 <= self.price <= 0.99):
            errs.append(f"price {self.price!r} outside Kalshi [0.01, 0.99]")
        if self.qty <= 0:
            errs.append(f"qty {self.qty!r} must be > 0")
        if self.fee < 0:
            errs.append(f"fee {self.fee!r} must be >= 0")
        return errs


@dataclass
class Position:
    """Net position in one (ticker, side). `avg_cost` is dollars/contract of the
    open lots; `realized_pnl` accumulates closed-lot P&L (dollars, fees included
    at the call site that books them)."""

    ticker: str
    side: str
    qty: int = 0
    avg_cost: float = 0.0
    realized_pnl: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Position":
        return cls(ticker=d["ticker"], side=d["side"], qty=int(d.get("qty", 0)),
                   avg_cost=float(d.get("avg_cost", 0.0)),
                   realized_pnl=float(d.get("realized_pnl", 0.0)))


# --------------------------------------------------------------------------- #
# JSONL (de)serialization helpers — append-only ledger lines
# --------------------------------------------------------------------------- #
def record_to_line(rec: Any) -> str:
    """Serialize an Order or Fill to a single canonical JSONL line (no newline)."""
    if isinstance(rec, (Order, Fill)):
        return rec.to_json()
    raise TypeError(f"record_to_line expects Order|Fill, got {type(rec).__name__}")


def line_to_record(line: str) -> Optional[Any]:
    """Parse one ledger line back into an Order or Fill by its `record_kind`
    discriminator. A blank line yields None (tolerated at read time); an unknown
    record_kind raises (a ledger we cannot fully replay is a hard error, never
    silently skipped)."""
    line = line.strip()
    if not line:
        return None
    d = json.loads(line)
    kind = d.get("record_kind")
    if kind == "order":
        return Order.from_dict(d)
    if kind == "fill":
        return Fill.from_dict(d)
    raise ValueError(f"unknown ledger record_kind {kind!r}: cannot replay this line")
