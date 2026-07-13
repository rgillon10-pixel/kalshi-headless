"""execution.fill_models — deterministic paper fills over already-collected tape.

Two pure functions, no clock, no network, no randomness. Each takes an `Order`
plus a tape record (a dict exactly as it appears in the committed JSONL) and
returns a `Fill` or None. Same tape families the collectors already write:

  * orderbook_depth.v1 — full L2 ladders (`yes_bids`/`no_bids` = [[price,size]..],
    `best_yes_ask`/`best_no_ask`, tags in `price_source_tags`). Kalshi posts
    bids-only per outcome, so the tradeable YES ask is the complement of the NO
    bid ladder and vice-versa (this arithmetic already lives in
    collection/normalize.py; we walk the ladder the same way). Because this
    family carries resting SIZE at each level, `taker_immediate` walks the ladder
    and can PARTIALLY fill — honest about available depth.

  * sports_pairs.v1 — per-outcome BBO (`yes_ask`/`no_ask`/`yes_bid`/`no_bid`,
    `price_source_tag`) with NO size. `taker_immediate` fills the whole requested
    qty at the BBO but tags fill_model='taker_bbo_nosize' and caveats
    ['size_unverified'] — honesty over optimism: downstream can filter these out
    when size actually matters.

SYNTHETIC-PRICE REJECTION (CLAUDE.md prime directive #1): a paper fill may NEVER
fill against a modeled price. Both functions return None (with the reason printed
to a returned Fill's absence, documented per-function) when the record's relevant
price field is NOT tagged real. We chose return-None-with-reason over raising so a
strategy loop that hands a mixed batch of records to the broker does not die on
the first synthetic one (fault isolation, house discipline) — the reason is
surfaced via the module-level `last_reason()` accessor for tests/debugging.

FEES (lesson L18): every fee comes from core.pricing — `fee_per_contract` with
`TAKER_FEE_RATE` for taker fills and `MAKER_FEE_RATE` for the resting maker fill.
No fee coefficient is ever written literally in this module.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.pricing import MAKER_FEE_RATE, TAKER_FEE_RATE, fee_per_contract
from execution.schema import Fill, Order

# The tape tags that mark a genuinely fillable price. A record whose relevant
# price field carries anything else (or nothing -> synthetic by default) is rejected.
_REAL_ASK = "real_ask"
_REAL_BID = "real_bid"

# Last rejection/no-fill reason, for tests and debugging (never load-bearing state).
_LAST_REASON: List[str] = [""]


def last_reason() -> str:
    """The reason the most recent fill-model call returned None (or '' if it filled)."""
    return _LAST_REASON[0]


def _set_reason(reason: str) -> None:
    _LAST_REASON[0] = reason


# --------------------------------------------------------------------------- #
# tag extraction — a record fills only if its relevant price field is tagged real
# --------------------------------------------------------------------------- #
def _depth_ask_tag(record: Dict[str, Any]) -> Optional[str]:
    """The tag guarding the ASK side of an orderbook_depth record."""
    return (record.get("price_source_tags") or {}).get("asks")


def _depth_bid_tag(record: Dict[str, Any]) -> Optional[str]:
    """The tag guarding the BID side of an orderbook_depth record."""
    return (record.get("price_source_tags") or {}).get("bids")


def _is_depth_record(record: Dict[str, Any]) -> bool:
    return "price_source_tags" in record and (
        "yes_bids" in record or "no_bids" in record)


# --------------------------------------------------------------------------- #
# taker_immediate
# --------------------------------------------------------------------------- #
def _ask_ladder_from_depth(record: Dict[str, Any], side: str) -> List[Tuple[float, float]]:
    """The (price, size) ladder a TAKER buys into for `side`, best-first.

    Kalshi posts bids-only. Buying YES lifts the YES ask, whose ladder is the
    complement of the opposite (NO) bid ladder: a NO bid at price p / size s is a
    YES ask at (1 - p) for s contracts. Symmetric for buying NO off the YES bids.
    """
    opposite_bids = "no_bids" if side == "yes" else "yes_bids"
    ladder: List[Tuple[float, float]] = []
    for level in record.get(opposite_bids) or []:
        if not level or len(level) < 2:
            continue
        bid_price, size = float(level[0]), float(level[1])
        ask_price = round(1.0 - bid_price, 2)
        ladder.append((ask_price, size))
    # complement of a best-first bid ladder is already best (lowest-ask) first
    return ladder


def _crosses_buy(limit_price: float, ask_price: float) -> bool:
    """A resting/marketable buy at `limit_price` crosses an ask at `ask_price`
    iff the limit is at or above the ask (we would pay no worse than our limit)."""
    return ask_price <= limit_price + 1e-9


def taker_immediate(order: Order, book_record: Dict[str, Any]) -> Optional[Fill]:
    """Fill a crossable taker order against a live book's real ask.

    Depth path (orderbook_depth.v1): walk the ask ladder best-first, taking size
    at each level whose price crosses the order's limit, until the order qty is
    met or the crossable depth runs out. Partial fills are honest and expected.
    fill_model='taker_depth'. The reported fill `price` is the size-weighted
    average of the levels taken (rounded to the cent), and the fee is
    core.pricing.fee_per_contract at that average price, TAKER rate, times qty.

    BBO-no-size path (sports_pairs.v1): fill the whole requested qty at the BBO
    ask; fill_model='taker_bbo_nosize', caveats=['size_unverified'].

    Returns None (reason via last_reason()) if: the record is synthetic-tagged on
    the ask side; the book does not cross the order's limit; or the order action
    is not a buy (this function models marketable BUYS lifting an ask — a taker
    SELL hitting a bid is symmetric and out of this milestone's spec scope, so it
    is refused explicitly rather than mis-modeled)."""
    _set_reason("")
    if order.action != "buy":
        _set_reason("taker_immediate models marketable buys only (action != 'buy')")
        return None

    if _is_depth_record(book_record):
        return _taker_depth(order, book_record)
    return _taker_bbo_nosize(order, book_record)


def _taker_depth(order: Order, record: Dict[str, Any]) -> Optional[Fill]:
    tag = _depth_ask_tag(record)
    if tag != _REAL_ASK:
        _set_reason(f"depth ask side tagged {tag!r}, not real_ask — refusing synthetic fill")
        return None

    ladder = _ask_ladder_from_depth(record, order.side)
    remaining = order.qty
    taken_cost = 0.0
    taken_qty = 0
    for ask_price, size in ladder:
        if remaining <= 0:
            break
        if not _crosses_buy(order.limit_price, ask_price):
            break  # ladder is best-first; once a level is above our limit, so is the rest
        take = min(remaining, int(size))
        if take <= 0:
            continue
        taken_cost += ask_price * take
        taken_qty += take
        remaining -= take

    if taken_qty <= 0:
        _set_reason("book does not cross the order limit (no fillable depth)")
        return None

    avg_price = round(taken_cost / taken_qty, 2)
    fee = fee_per_contract(avg_price, rate=TAKER_FEE_RATE) * taken_qty
    caveats: List[str] = []
    if taken_qty < order.qty:
        caveats.append("partial_fill")
    return Fill(
        fill_id=f"{order.order_id}:F", order_id=order.order_id,
        ts=record.get("captured_at", order.ts), ticker=order.ticker, side=order.side,
        action=order.action, price=avg_price, qty=taken_qty, fee=round(fee, 4),
        fill_model="taker_depth", price_source_tag=_REAL_ASK, caveats=caveats,
    )


def _bbo_ask_for(order: Order, outcome: Dict[str, Any]) -> Optional[float]:
    """The BBO ask price for the order's side off a sports_pairs outcome dict."""
    field = "yes_ask" if order.side == "yes" else "no_ask"
    val = outcome.get(field)
    return None if val is None else float(val)


def _find_outcome(record: Dict[str, Any], ticker: str) -> Optional[Dict[str, Any]]:
    """Locate the outcome dict for `ticker` in a sports_pairs record (which nests
    a list of outcomes) or treat the record itself as the outcome if it carries
    the price fields directly."""
    for o in record.get("outcomes") or []:
        if o.get("ticker") == ticker:
            return o
    if record.get("ticker") == ticker and ("yes_ask" in record or "no_ask" in record):
        return record
    return None


def _taker_bbo_nosize(order: Order, record: Dict[str, Any]) -> Optional[Fill]:
    outcome = _find_outcome(record, order.ticker)
    if outcome is None:
        _set_reason(f"ticker {order.ticker!r} not found in BBO record")
        return None

    tag = outcome.get("price_source_tag", record.get("price_source_tag"))
    if tag != _REAL_ASK:
        _set_reason(f"BBO price_source_tag {tag!r}, not real_ask — refusing synthetic fill")
        return None

    ask = _bbo_ask_for(order, outcome)
    if ask is None:
        _set_reason("no BBO ask for the order side")
        return None
    if not _crosses_buy(order.limit_price, ask):
        _set_reason("BBO ask does not cross the order limit")
        return None

    fee = fee_per_contract(ask, rate=TAKER_FEE_RATE) * order.qty
    return Fill(
        fill_id=f"{order.order_id}:F", order_id=order.order_id,
        ts=record.get("captured_at", order.ts), ticker=order.ticker, side=order.side,
        action=order.action, price=round(ask, 2), qty=order.qty, fee=round(fee, 4),
        fill_model="taker_bbo_nosize", price_source_tag=_REAL_ASK,
        caveats=["size_unverified"],
    )


# --------------------------------------------------------------------------- #
# maker_resting — generalize s13's candlestick-through rule
# --------------------------------------------------------------------------- #
def _min_low_dollars(records: List[Dict[str, Any]]) -> Optional[float]:
    """Lowest realized trade price across a list of later candlestick records
    (each `{'price': {'low_dollars': ...}}`, s13's shape). None if no trade data."""
    best: Optional[float] = None
    for c in records:
        low = (c.get("price") or {}).get("low_dollars")
        if low is None:
            continue
        low = float(low)
        if best is None or low < best:
            best = low
    return best


def _max_high_dollars(records: List[Dict[str, Any]]) -> Optional[float]:
    best: Optional[float] = None
    for c in records:
        high = (c.get("price") or {}).get("high_dollars")
        if high is None:
            continue
        high = float(high)
        if best is None or high > best:
            best = high
    return best


def _candle_tag(records: List[Dict[str, Any]]) -> Optional[str]:
    """The price_source_tag guarding a candlestick series. A realized trade print
    is a real fill event; s13 tags its candle summaries real_ask. We require every
    candle carrying a tag to be tagged real (a synthetic candle is refused)."""
    tags = {c.get("price_source_tag") for c in records if "price_source_tag" in c}
    if not tags:
        return None  # untagged -> caller treats as synthetic and refuses
    if tags == {_REAL_ASK} or tags == {_REAL_BID} or tags == {_REAL_ASK, _REAL_BID}:
        return "real"
    return "synthetic"


def maker_resting(order: Order,
                  candle_or_later_records: List[Dict[str, Any]]) -> Optional[Fill]:
    """A resting maker order fills iff a later observed trade crosses its limit
    (s13's candlestick-through rule, generalized to both sides):

      * a resting BUY at `limit` fills iff some later candle's low <= limit
        (a trade printed at/below our bid means someone crossed into it);
      * a resting SELL at `limit` fills iff some later candle's high >= limit.

    fill_model='maker_candle_through', caveats=['no_queue_model','optimistic_fill']
    (we have no queue position and assume any through-print fills us fully — the
    same optimism s13 documents). Fee is core.pricing.fee_per_contract at the
    MAKER rate (lesson L18/L30: a resting fill is a maker fill; using the taker
    rate would 4x-overcharge it).

    Returns None (reason via last_reason()) if the candle series is synthetic-
    tagged/untagged, carries no trade data, or never crosses the limit."""
    _set_reason("")
    if order.action not in ("buy", "sell"):
        _set_reason(f"unsupported action {order.action!r}")
        return None

    tag = _candle_tag(candle_or_later_records)
    if tag != "real":
        _set_reason(f"candle series tag {tag!r} is not real — refusing synthetic fill")
        return None

    if order.action == "buy":
        low = _min_low_dollars(candle_or_later_records)
        if low is None:
            _set_reason("no realized trade data in candle series")
            return None
        if low > order.limit_price + 1e-9:
            _set_reason("no later trade crossed the resting buy limit")
            return None
        fill_price = round(order.limit_price, 2)
        source_tag = _REAL_BID  # a resting buy fills against the bid ladder side
    else:  # sell
        high = _max_high_dollars(candle_or_later_records)
        if high is None:
            _set_reason("no realized trade data in candle series")
            return None
        if high < order.limit_price - 1e-9:
            _set_reason("no later trade crossed the resting sell limit")
            return None
        fill_price = round(order.limit_price, 2)
        source_tag = _REAL_ASK  # a resting sell fills against the ask ladder side

    fee = fee_per_contract(fill_price, rate=MAKER_FEE_RATE) * order.qty
    return Fill(
        fill_id=f"{order.order_id}:F", order_id=order.order_id,
        ts=order.ts, ticker=order.ticker, side=order.side, action=order.action,
        price=fill_price, qty=order.qty, fee=round(fee, 4),
        fill_model="maker_candle_through", price_source_tag=source_tag,
        caveats=["no_queue_model", "optimistic_fill"],
    )


# --------------------------------------------------------------------------- #
# resting_short_yes_as_no_fill — S14 ladder underwriting's fill (buy-NO mirror)
# --------------------------------------------------------------------------- #
def resting_short_yes_as_no_fill(order: Order,
                                candle_summary: Optional[Dict[str, Any]]) -> Optional[Fill]:
    """The S14 "ladder overround underwriting" fill, represented in the paper
    broker's long-only model.

    S14 rests a SHORT-YES maker offer at each member's `yes_ask` A. The broker has
    no short model, so the same economic position is a BUY of NO at the real NO bid
    `1 - A` (a genuine fillable maker-side price, tag `real_bid`), held to
    settlement. `order` is that buy-NO order: side='no', action='buy',
    limit_price = round(1 - A, 2). We RECONSTRUCT A = round(1 - limit_price, 2)
    (a clean cent round-trip) and apply S14's SELLER fill rule on the cached YES
    candle summary: a fill iff the realized YES trade HIGH reached the posted ask A
    and volume > 0 (`detect_seller_fill`). That is arithmetically identical to "the
    NO bid at 1 - A got crossed" — we key the candle by A, NOT by 1 - A, because
    the cache stores the YES `max_high_dollars`.

    Fee is the MAKER rate via core.pricing (lesson L18/L30). Because Kalshi's maker
    fee is a flat $0.01/contract at every interior price, fee(1 - A) == fee(A), so
    this buy-NO fee equals S14's short-YES member fee cent-for-cent. Returns None
    (reason via last_reason()) for a non-(buy-NO) order, a missing/synthetic candle
    summary, or a window whose seller rule never crossed."""
    _set_reason("")
    if order.action != "buy" or order.side != "no":
        _set_reason("resting_short_yes_as_no_fill models the S14 buy-NO mirror only "
                    "(needs action='buy', side='no')")
        return None
    if candle_summary is None:
        _set_reason("no candle summary for ticker — cannot resolve fill")
        return None
    # The candle summary is a realized trade print (s14 tags it real_ask); a
    # synthetic/untagged summary can never fill (CLAUDE.md prime directive).
    tag = candle_summary.get("price_source_tag")
    if tag not in (_REAL_ASK, _REAL_BID):
        _set_reason(f"candle summary tag {tag!r} is not real — refusing synthetic fill")
        return None

    limit = float(order.limit_price)
    posted_ask = round(1.0 - limit, 2)  # reconstruct S14's short-YES ask A from the NO bid

    from scripts.s14_ladder_fillsim import detect_seller_fill  # pure, network-free
    if not detect_seller_fill(candle_summary, posted_ask):
        _set_reason("S14 seller rule not crossed (YES high < posted ask or zero volume)")
        return None

    fill_price = round(limit, 2)  # the NO bid 1 - A we actually filled at
    fee = fee_per_contract(fill_price, rate=MAKER_FEE_RATE) * order.qty
    return Fill(
        fill_id=f"{order.order_id}:F", order_id=order.order_id,
        ts=order.ts, ticker=order.ticker, side=order.side, action=order.action,
        price=fill_price, qty=order.qty, fee=round(fee, 4),
        fill_model="maker_candle_through", price_source_tag=_REAL_BID,
        caveats=["no_queue_model", "optimistic_fill", "s14_seller_mirror"],
    )
