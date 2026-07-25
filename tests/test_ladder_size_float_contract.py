"""L47 — the ladder-size FLOAT contract, end to end.

`collection/orderbook_depth.py` persists `yes_bids`/`no_bids` as `[price, size]` pairs whose
size is a FLOAT and is genuinely fractional in the real tape. L47 forbids coercing one to int
"without an explicit, justified rounding rule". This module pins the whole chain:

  1. the FACT, anchored to REAL committed tape (fractional sizes genuinely exist — pinned by
     data, not only by a fixture);
  2. `collection.normalize.normalize_snapshot` preserves fractional sizes end to end;
  3. `execution.fill_models._taker_depth` (the paper-P&L path) takes the FLOOR via the one
     sanctioned helper, never reports a fractional qty, and a 0<size<1 level contributes zero
     depth WITHOUT halting the ladder walk;
  4. the ADOPTION contract: routing `_taker_depth` through
     `core.depth.whole_contracts_available` instead of its former bare `int(size)` changes NO
     fill on real tape — replayed here against a verbatim copy of the old semantics.

The census numbers quoted are DESCRIPTIVE tape statistics (level COUNTS), not prices. The
ladders themselves come from records tagged `price_source_tags={"asks":"real_ask",
"bids":"real_bid"}`. Offline: reads committed tape only, no network.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from collection.normalize import normalize_snapshot
from core.depth import whole_contracts_available
from core.pricing import TAKER_FEE_RATE, fee_per_contract
from execution.fill_models import taker_immediate
from execution.schema import Order

_TAPE = Path(__file__).resolve().parents[1] / "tape" / "orderbook_depth"
_real_tape = pytest.mark.skipif(not _TAPE.is_dir(), reason="committed tape/ not present")

# Bound the read so the test stays fast on a 315MB family: we need EXISTENCE and a
# replay sample, not a full census (the full census lives in the L47/L154 ledger rows).
_MAX_LINES_PER_FILE = 4000
_WANT_FRACTIONAL_RECORDS = 300
_WANT_PLAIN_RECORDS = 300


def _iter_records(limit_per_file: int = _MAX_LINES_PER_FILE):
    for path in sorted(_TAPE.glob("dt=*.jsonl")):
        with path.open() as fh:
            for i, line in enumerate(fh):
                if i >= limit_per_file:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    continue


def _ladder_sizes(rec: Dict[str, Any]) -> List[float]:
    out: List[float] = []
    for key in ("yes_bids", "no_bids"):
        for level in rec.get(key) or []:
            if level and len(level) >= 2 and level[1] is not None:
                out.append(float(level[1]))
    return out


def _sampled_records() -> Tuple[List[dict], List[dict]]:
    """(records carrying >=1 fractional ladder size, arbitrary records) — bounded."""
    frac: List[dict] = []
    plain: List[dict] = []
    for rec in _iter_records():
        sizes = _ladder_sizes(rec)
        if not sizes:
            continue
        if any(s != int(s) for s in sizes):
            if len(frac) < _WANT_FRACTIONAL_RECORDS:
                frac.append(rec)
        elif len(plain) < _WANT_PLAIN_RECORDS:
            plain.append(rec)
        if len(frac) >= _WANT_FRACTIONAL_RECORDS and len(plain) >= _WANT_PLAIN_RECORDS:
            break
    return frac, plain


# ─── 1. the FACT, anchored to real committed tape ────────────────────────────

@_real_tape
def test_real_tape_carries_fractional_ladder_sizes():
    """HARD acceptance test: fractional `yes_bids`/`no_bids` sizes genuinely exist in the
    committed tape. If this ever fails, L47's premise (and the floor rule built on it) must be
    re-derived — it does not silently become a fixture-only claim."""
    n_levels = 0
    n_fractional = 0
    n_sub_one = 0
    n_negative = 0
    for rec in _iter_records():
        for size in _ladder_sizes(rec):
            n_levels += 1
            if size != int(size):
                n_fractional += 1
            if 0.0 < size < 1.0:
                n_sub_one += 1
            if size < 0.0:
                n_negative += 1
    assert n_levels > 100_000, f"tape sample too thin to assert on ({n_levels} levels)"
    assert n_fractional > 0, "L47's premise: fractional ladder sizes must exist in real tape"
    assert n_sub_one > 0, "0 < size < 1 levels must exist (the floor-to-zero case is real)"
    # The floor rule's conservative direction relies on sizes being non-negative.
    assert n_negative == 0


@_real_tape
def test_real_tape_ladder_sizes_are_floats_not_ints_in_json():
    """The persisted JSON type is float, not int — a consumer type-sniffing the field sees a
    float. (A whole-valued float still round-trips as e.g. `10.0`.)"""
    seen_float = False
    for rec in _iter_records(limit_per_file=200):
        for key in ("yes_bids", "no_bids"):
            for level in rec.get(key) or []:
                if level and len(level) >= 2 and isinstance(level[1], float):
                    seen_float = True
                    break
    assert seen_float


# ─── 2. normalize_snapshot preserves fractional sizes end to end ─────────────

def test_normalize_snapshot_preserves_fractional_sizes():
    ob = {"yes_dollars": [[0.61, 91316.82], [0.60, 0.5]],
          "no_dollars": [[0.37, 12.25], [0.30, 1.75]]}
    snap = normalize_snapshot("KXWCGAME-TEST", ob)
    yes_sizes = [lvl[1] for lvl in snap["yes_bids"]]
    no_sizes = [lvl[1] for lvl in snap["no_bids"]]
    assert yes_sizes == [91316.82, 0.5]
    assert no_sizes == [12.25, 1.75]
    assert all(isinstance(s, float) for s in yes_sizes + no_sizes)
    # and none of them silently became a whole number
    assert all(s != int(s) for s in yes_sizes + no_sizes)


def test_normalize_snapshot_sub_one_size_survives_as_a_level():
    """A 0<size<1 level is NOT dropped by the normalizer — the float contract keeps it; only
    the fill model's explicit floor rule decides it is unliftable."""
    snap = normalize_snapshot("KX-T", {"yes_dollars": [[0.61, 0.25]], "no_dollars": []})
    assert snap["yes_bids"] == [[0.61, 0.25]]
    assert snap["best_yes_bid"] == 0.61


# ─── 3. _taker_depth floors, never fractional-qty, and walks past sub-1 levels ─

def _depth_record(no_bids, **kw):
    base = dict(
        price_source_tags={"asks": "real_ask", "bids": "real_bid"},
        no_bids=no_bids, yes_bids=[],
        ticker="KX-T", captured_at="2026-07-11T00:00:00Z",
    )
    base.update(kw)
    return base


def _order(**kw):
    base = dict(order_id="o1", ts="2026-07-11T00:00:00Z", ticker="KX-T", side="yes",
                action="buy", limit_price=0.90, qty=100, tif="ioc", strategy="s")
    base.update(kw)
    return Order(**base)


def test_taker_depth_floors_a_fractional_level_size():
    # NO bid 0.62 / size 10.7 -> YES ask 0.38 with 10.7 resting; only 10 are liftable.
    f = taker_immediate(_order(qty=100, limit_price=0.38),
                        _depth_record([[0.62, 10.7]]))
    assert f is not None
    assert f.qty == 10
    assert isinstance(f.qty, int) and not isinstance(f.qty, float)
    assert "partial_fill" in f.caveats


def test_taker_depth_never_reports_a_fractional_qty_across_many_fractional_levels():
    ladder = [[0.62, 3.9], [0.61, 7.25], [0.60, 100.75]]
    f = taker_immediate(_order(qty=100, limit_price=0.45), _depth_record(ladder))
    assert f is not None
    assert f.qty == 3 + 7 + 90        # floors, then the last level caps at remaining qty
    assert float(f.qty).is_integer()


def test_taker_depth_sub_one_level_contributes_zero_and_the_walk_CONTINUES():
    """PINNED BEHAVIOUR: a 0<size<1 level yields zero liftable contracts (`take <= 0`) and the
    loop `continue`s to the next, deeper level — it does NOT `break` out of the walk. A future
    refactor that turns that `continue` into a `break` would silently starve fills behind any
    dust level, so the shape is pinned explicitly here."""
    # dust at the best ask (0.38), real size one level deeper (0.39)
    f = taker_immediate(_order(qty=5, limit_price=0.40),
                        _depth_record([[0.62, 0.4], [0.61, 50.0]]))
    assert f is not None
    assert f.qty == 5
    assert f.price == pytest.approx(0.39)   # entirely from the DEEPER level


def test_taker_depth_all_dust_ladder_is_a_no_fill_not_a_fractional_fill():
    f = taker_immediate(_order(qty=5, limit_price=0.40),
                        _depth_record([[0.62, 0.4], [0.61, 0.9]]))
    assert f is None


def test_taker_depth_uses_the_sanctioned_helper_semantics():
    """The helper and the fill model must agree level-by-level (one rounding rule, one site)."""
    for size in (0.0, 0.4, 1.0, 1.9, 10.7, 91316.82):
        f = taker_immediate(_order(qty=1_000_000, limit_price=0.38),
                            _depth_record([[0.62, size]]))
        expected = whole_contracts_available(size)
        assert (f.qty if f is not None else 0) == expected


# ─── 4. ADOPTION CONTRACT: paper P&L unchanged on real tape ──────────────────

def _legacy_taker_depth_fill(order: Order, record: Dict[str, Any]):
    """VERBATIM copy of `_taker_depth`'s pre-L47-fix arithmetic (`take = min(remaining,
    int(size))`), kept here solely to prove the swap to `whole_contracts_available` changed no
    fill. Returns (qty, avg_price, fee) or None."""
    if (record.get("price_source_tags") or {}).get("asks") != "real_ask":
        return None
    opposite_bids = "no_bids" if order.side == "yes" else "yes_bids"
    ladder = []
    for level in record.get(opposite_bids) or []:
        if not level or len(level) < 2:
            continue
        ladder.append((round(1.0 - float(level[0]), 2), float(level[1])))
    remaining, taken_cost, taken_qty = order.qty, 0.0, 0
    for ask_price, size in ladder:
        if remaining <= 0:
            break
        if not (ask_price <= order.limit_price + 1e-9):
            break
        take = min(remaining, int(size))          # <- the OLD, unjustified coercion
        if take <= 0:
            continue
        taken_cost += ask_price * take
        taken_qty += take
        remaining -= take
    if taken_qty <= 0:
        return None
    avg_price = round(taken_cost / taken_qty, 2)
    fee = fee_per_contract(avg_price, rate=TAKER_FEE_RATE) * taken_qty
    return taken_qty, avg_price, round(fee, 4)


@_real_tape
def test_paper_pnl_unchanged_replaying_real_tape_ladders():
    """HARD adoption test: replay real committed ladders through `taker_immediate` and through
    a verbatim copy of the OLD `int(size)` semantics. Every fill — qty, avg price, fee — must
    be IDENTICAL, i.e. the L47 fix is pure hygiene and moves no paper P&L."""
    frac, plain = _sampled_records()
    records = frac + plain
    assert len(frac) > 0, "no fractional-size records sampled — replay would be vacuous"
    assert len(records) >= 100

    compared = 0
    fills = 0
    for rec in records:
        for side in ("yes", "no"):
            for limit, qty in ((0.20, 5), (0.50, 37), (0.99, 500)):
                order = _order(order_id=f"o{compared}", side=side, limit_price=limit, qty=qty,
                               ticker=rec.get("ticker", "KX-T"))
                new = taker_immediate(order, rec)
                old = _legacy_taker_depth_fill(order, rec)
                compared += 1
                if new is None:
                    assert old is None
                    continue
                assert old is not None
                fills += 1
                assert (new.qty, new.price, new.fee) == old
    assert compared > 1000
    assert fills > 0, "replay produced no fills at all — the comparison would be vacuous"
