"""execution.paper_broker + execution.limits — broker accounting, deterministic
ledger replay, limits enforcement. Offline: synthetic tape + tmp_path ledgers,
no network."""
from __future__ import annotations

import json

import pytest

from core.pricing import TAKER_FEE_RATE, fee_per_contract
from execution import limits
from execution.limits import (MAX_CONTRACTS_PER_ORDER, MAX_DAILY_ORDERS,
                             MAX_OPEN_NOTIONAL_DOLLARS, check_order)
from execution.paper_broker import PaperBroker
from execution.schema import Fill, Order, Settlement, record_to_line


def _order(**kw):
    base = dict(order_id="o1", ts="2026-07-11T00:00:00Z", ticker="KX-T", side="yes",
                action="buy", limit_price=0.40, qty=10, tif="ioc", strategy="s")
    base.update(kw)
    return Order(**base)


def _fill(**kw):
    base = dict(fill_id="o1:F", order_id="o1", ts="2026-07-11T00:00:00Z", ticker="KX-T",
                side="yes", action="buy", price=0.40, qty=10, fee=0.03,
                fill_model="taker_depth", price_source_tag="real_ask", caveats=[])
    base.update(kw)
    return Fill(**base)


def _settlement(**kw):
    base = dict(settlement_id="s1", ts="2026-07-11T00:00:00Z", ticker="KX-T", side="no",
                settle_value=1.0, qty=1, event_ticker="KX-EV", price_source_tag="broker_truth")
    base.update(kw)
    return Settlement(**base)


def _depth(ticker="KX-T", no_bids=None, yes_bid=0.37, no_bid=0.62):
    return {
        "price_source_tags": {"asks": "real_ask", "bids": "real_bid"},
        "no_bids": no_bids if no_bids is not None else [[0.62, 100.0]],
        "yes_bids": [[0.37, 100.0]],
        "best_yes_bid": yes_bid, "best_no_bid": no_bid,
        "ticker": ticker, "captured_at": "2026-07-11T00:00:00Z",
    }


def _write_ledger(ledger_dir, records, day="2026-07-11"):
    ledger_dir.mkdir(parents=True, exist_ok=True)
    path = ledger_dir / f"dt={day}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        for r in records:
            f.write(record_to_line(r) + "\n")
    return path


# --------------------------------------------------------------------------- #
# limits.check_order
# --------------------------------------------------------------------------- #
def test_check_order_clean_order_no_violations():
    assert check_order(_order(qty=10, limit_price=0.40), open_notional=0.0, orders_today=0) == []


def test_check_order_flags_oversize_qty():
    v = check_order(_order(qty=MAX_CONTRACTS_PER_ORDER + 1), open_notional=0.0, orders_today=0)
    assert any("MAX_CONTRACTS_PER_ORDER" in s for s in v)


def test_check_order_flags_notional_breach_including_marginal():
    """An order whose own notional pushes total past the cap is rejected."""
    o = _order(qty=100, limit_price=0.50)  # marginal notional $50
    v = check_order(o, open_notional=MAX_OPEN_NOTIONAL_DOLLARS - 10.0, orders_today=0)
    assert any("MAX_OPEN_NOTIONAL_DOLLARS" in s for s in v)


def test_check_order_notional_within_cap_ok():
    o = _order(qty=10, limit_price=0.40)  # $4 marginal
    assert check_order(o, open_notional=10.0, orders_today=0) == []


def test_check_order_flags_daily_order_cap():
    v = check_order(_order(), open_notional=0.0, orders_today=MAX_DAILY_ORDERS)
    assert any("MAX_DAILY_ORDERS" in s for s in v)


def test_check_order_multiple_violations_reported_together():
    o = _order(qty=MAX_CONTRACTS_PER_ORDER + 1, limit_price=0.99)
    v = check_order(o, open_notional=MAX_OPEN_NOTIONAL_DOLLARS, orders_today=MAX_DAILY_ORDERS)
    assert len(v) == 3


def test_limits_module_is_the_caps_site():
    assert isinstance(MAX_CONTRACTS_PER_ORDER, int)
    assert isinstance(MAX_OPEN_NOTIONAL_DOLLARS, float)
    assert isinstance(MAX_DAILY_ORDERS, int)


# --------------------------------------------------------------------------- #
# deterministic replay
# --------------------------------------------------------------------------- #
def test_replay_is_deterministic_same_ledger_same_state(tmp_path):
    ledger = tmp_path / "ledger"
    _write_ledger(ledger, [
        _order(order_id="o1"), _fill(order_id="o1", fill_id="o1:F", price=0.40, qty=10),
        _order(order_id="o2"),
        _fill(order_id="o2", fill_id="o2:F", action="sell", price=0.50, qty=4),
    ])
    b1 = PaperBroker(ledger)
    b2 = PaperBroker(ledger)
    assert b1.cash == pytest.approx(b2.cash)
    assert b1.realized_pnl == pytest.approx(b2.realized_pnl)
    assert {k: v.qty for k, v in b1.positions.items()} == {
        k: v.qty for k, v in b2.positions.items()}


def test_orders_today_uses_as_of_not_wall_clock(tmp_path):
    # The class docstring promises "no clock beyond context.now_ts" / "the same
    # ledger always reproduces the same state" — orders_today must honor that too.
    # Both orders carry ts="2026-07-11..."; as_of pins "today" to that same date
    # regardless of when the test actually runs.
    ledger = tmp_path / "ledger"
    _write_ledger(ledger, [_order(order_id="o1"), _order(order_id="o2")])
    b = PaperBroker(ledger, as_of="2026-07-11T12:00:00+00:00")
    assert b.orders_today == 2


def test_orders_today_excludes_orders_from_a_different_as_of_day(tmp_path):
    ledger = tmp_path / "ledger"
    _write_ledger(ledger, [_order(order_id="o1"), _order(order_id="o2")])
    b = PaperBroker(ledger, as_of="2026-07-12T00:00:00+00:00")
    assert b.orders_today == 0


def test_replay_reproduces_position_and_realized_pnl(tmp_path):
    ledger = tmp_path / "ledger"
    # buy 10 @ 0.40 (fee 0.03), then sell 4 @ 0.50 (fee 0.02)
    _write_ledger(ledger, [
        _fill(order_id="o1", fill_id="o1:F", price=0.40, qty=10, fee=0.03),
        _fill(order_id="o2", fill_id="o2:F", action="sell", price=0.50, qty=4, fee=0.02),
    ])
    b = PaperBroker(ledger)
    pos = b.positions[("KX-T", "yes")]
    assert pos.qty == 6
    # avg_cost fee-inclusive: (0.40*10 + 0.03)/10 = 0.403
    assert pos.avg_cost == pytest.approx(0.403)
    # realized: (0.50 - 0.403)*4 - 0.02
    assert b.realized_pnl == pytest.approx((0.50 - 0.403) * 4 - 0.02)


def test_state_snapshot_is_not_source_of_truth(tmp_path):
    """A stale/garbage state.json must not affect replayed state."""
    ledger = tmp_path / "paper" / "ledger"
    _write_ledger(ledger, [_fill(order_id="o1", fill_id="o1:F", price=0.40, qty=10)])
    b = PaperBroker(ledger)
    snap = b.write_state_snapshot()
    # corrupt the cache, then rebuild: replay ignores it entirely
    snap.write_text(json.dumps({"cash": 999999.0, "realized_pnl": 999999.0}))
    b2 = PaperBroker(ledger)
    assert b2.cash == pytest.approx(b.cash)
    assert b2.cash != pytest.approx(999999.0)


# --------------------------------------------------------------------------- #
# submit — ledger append-only round trip + limits enforcement
# --------------------------------------------------------------------------- #
def test_submit_appends_order_and_fill_and_roundtrips(tmp_path):
    ledger = tmp_path / "ledger"
    b = PaperBroker(ledger)
    res = b.submit([_order(order_id="o1", limit_price=0.40, qty=10)], [_depth()])
    assert res["n_accepted"] == 1
    assert res["n_fills"] == 1
    # ledger has exactly one order line + one fill line, replayable
    b2 = PaperBroker(ledger)
    assert b2.positions[("KX-T", "yes")].qty == 10


def test_submit_is_append_only_second_submit_preserves_first(tmp_path):
    ledger = tmp_path / "ledger"
    b = PaperBroker(ledger)
    b.submit([_order(order_id="o1")], [_depth()])
    files = list(ledger.glob("dt=*.jsonl"))
    first_lines = files[0].read_text().splitlines()
    b.submit([_order(order_id="o2")], [_depth()])
    after_lines = files[0].read_text().splitlines()
    # original lines are a prefix of the new file (never rewritten/reordered)
    assert after_lines[: len(first_lines)] == first_lines
    assert len(after_lines) > len(first_lines)


def test_submit_rejects_cap_violating_order_without_writing_it(tmp_path):
    ledger = tmp_path / "ledger"
    b = PaperBroker(ledger)
    res = b.submit([_order(order_id="big", qty=MAX_CONTRACTS_PER_ORDER + 5)], [_depth()])
    assert res["n_accepted"] == 0
    assert res["n_rejected"] == 1
    assert not list(ledger.glob("dt=*.jsonl"))  # nothing written


def test_submit_rejects_schema_invalid_order(tmp_path):
    ledger = tmp_path / "ledger"
    b = PaperBroker(ledger)
    res = b.submit([_order(order_id="bad", limit_price=1.5)], [_depth()])
    assert res["n_rejected"] == 1
    assert res["n_accepted"] == 0


def test_submit_accepts_order_even_when_no_fill(tmp_path):
    """A crossable-limit miss is a valid resting order (accepted, no fill)."""
    ledger = tmp_path / "ledger"
    b = PaperBroker(ledger)
    res = b.submit([_order(order_id="o1", limit_price=0.20, qty=10)], [_depth()])
    assert res["n_accepted"] == 1
    assert res["n_fills"] == 0


# --------------------------------------------------------------------------- #
# settlement application
# --------------------------------------------------------------------------- #
def test_apply_settlement_books_realized_pnl_on_win(tmp_path):
    """Buy NO @0.60 fee0.01 (avg_cost 0.61), settle to 1.0 -> realized (1.0-0.61)*1."""
    ledger = tmp_path / "ledger"
    _write_ledger(ledger, [
        _fill(order_id="o1", fill_id="o1:F", ticker="KX-M", side="no", action="buy",
              price=0.60, qty=1, fee=0.01, fill_model="maker_candle_through",
              price_source_tag="real_bid"),
        _settlement(settlement_id="o1:S", ticker="KX-M", side="no", settle_value=1.0, qty=1),
    ])
    b = PaperBroker(ledger)
    assert b.realized_pnl == pytest.approx((1.0 - 0.61) * 1)
    assert b.positions[("KX-M", "no")].qty == 0
    assert b.settled_contracts == 1


def test_apply_settlement_books_loss_for_winner_member(tmp_path):
    """A winner NO leg settles to 0.0 -> realized (0.0 - avg_cost) = full loss."""
    ledger = tmp_path / "ledger"
    _write_ledger(ledger, [
        _fill(order_id="o1", fill_id="o1:F", ticker="KX-W", side="no", action="buy",
              price=0.70, qty=1, fee=0.01, fill_model="maker_candle_through",
              price_source_tag="real_bid"),
        _settlement(settlement_id="o1:S", ticker="KX-W", side="no", settle_value=0.0, qty=1),
    ])
    b = PaperBroker(ledger)
    assert b.realized_pnl == pytest.approx((0.0 - 0.71) * 1)


def test_replay_applies_fill_before_settle_in_file_order(tmp_path):
    """The settlement must be a LATER line than its fill; replay is order-sensitive."""
    ledger = tmp_path / "ledger"
    _write_ledger(ledger, [
        _fill(order_id="o1", fill_id="o1:F", ticker="KX-M", side="no", action="buy",
              price=0.55, qty=1, fee=0.01, fill_model="maker_candle_through",
              price_source_tag="real_bid"),
        _settlement(settlement_id="o1:S", ticker="KX-M", side="no", settle_value=1.0, qty=1),
    ])
    b1 = PaperBroker(ledger)
    b2 = PaperBroker(ledger)  # deterministic replay incl. settlement
    assert b1.realized_pnl == pytest.approx(b2.realized_pnl)
    assert b1.realized_pnl == pytest.approx((1.0 - 0.56) * 1)


def test_settle_rejects_invalid_settlement_without_writing(tmp_path):
    ledger = tmp_path / "ledger"
    _write_ledger(ledger, [
        _fill(order_id="o1", fill_id="o1:F", ticker="KX-M", side="no", action="buy",
              price=0.55, qty=1, fee=0.01, fill_model="maker_candle_through",
              price_source_tag="real_bid"),
    ])
    b = PaperBroker(ledger)
    before = ledger.glob("dt=*.jsonl")
    before_lines = sum(len(p.read_text().splitlines()) for p in before)
    res = b.settle([_settlement(settlement_id="bad", ticker="KX-M", side="no",
                                settle_value=0.5, qty=1)])
    assert res["n_settled"] == 0
    assert res["n_rejected"] == 1
    after_lines = sum(len(p.read_text().splitlines()) for p in ledger.glob("dt=*.jsonl"))
    assert after_lines == before_lines  # invalid settlement never written


def test_settle_appends_and_replays(tmp_path):
    ledger = tmp_path / "ledger"
    _write_ledger(ledger, [
        _fill(order_id="o1", fill_id="o1:F", ticker="KX-M", side="no", action="buy",
              price=0.60, qty=1, fee=0.01, fill_model="maker_candle_through",
              price_source_tag="real_bid"),
    ])
    b = PaperBroker(ledger)
    assert b.realized_pnl == pytest.approx(0.0)
    res = b.settle([_settlement(settlement_id="o1:S", ticker="KX-M", side="no",
                                settle_value=1.0, qty=1)])
    assert res["n_settled"] == 1
    assert b.realized_pnl == pytest.approx((1.0 - 0.61) * 1)
    # persisted: a fresh broker over the same ledger reproduces it
    assert PaperBroker(ledger).realized_pnl == pytest.approx(b.realized_pnl)


def test_settlement_with_no_open_position_is_surfaced_noop(tmp_path):
    ledger = tmp_path / "ledger"
    b = PaperBroker(ledger)
    res = b.settle([_settlement(settlement_id="s1", ticker="KX-NONE", side="no",
                                settle_value=1.0, qty=1)])
    assert res["n_settled"] == 1  # valid, written
    assert b.realized_pnl == pytest.approx(0.0)  # nothing to close
    assert ("KX-NONE", "no") in b.settlement_noops


# --------------------------------------------------------------------------- #
# mark_to_market
# --------------------------------------------------------------------------- #
def test_mark_to_market_marks_long_yes_at_yes_bid(tmp_path):
    ledger = tmp_path / "ledger"
    _write_ledger(ledger, [_fill(order_id="o1", fill_id="o1:F", price=0.40, qty=10)])
    b = PaperBroker(ledger)
    mtm = b.mark_to_market([_depth(yes_bid=0.45)])
    assert mtm["mtm_value"] == pytest.approx(0.45 * 10)
    mark = mtm["marks"][0]
    assert mark["mark_price"] == pytest.approx(0.45)
    assert mark["price_source_tag"] == "real_bid"


def test_mark_to_market_reports_exit_fees_separately_not_netted(tmp_path):
    ledger = tmp_path / "ledger"
    _write_ledger(ledger, [_fill(order_id="o1", fill_id="o1:F", price=0.40, qty=10)])
    b = PaperBroker(ledger)
    mtm = b.mark_to_market([_depth(yes_bid=0.45)])
    exit_fee = fee_per_contract(0.45, rate=TAKER_FEE_RATE) * 10
    assert mtm["est_exit_fees"] == pytest.approx(round(exit_fee, 4))
    # gross mark is NOT reduced by the exit fee; net_liq subtracts it explicitly
    assert mtm["mtm_value"] == pytest.approx(0.45 * 10)
    assert mtm["net_liq"] == pytest.approx(mtm["mtm_value"] + mtm["cash"] - mtm["est_exit_fees"])


def test_mark_to_market_stale_when_no_bid_available(tmp_path):
    ledger = tmp_path / "ledger"
    _write_ledger(ledger, [_fill(order_id="o1", fill_id="o1:F", price=0.40, qty=10)])
    b = PaperBroker(ledger)
    mtm = b.mark_to_market([])  # no records -> no liquidation bid
    assert mtm["marks"][0]["price_source_tag"] == "stale_no_bid"


# --------------------------------------------------------------------------- #
# daily_summary
# --------------------------------------------------------------------------- #
def test_daily_summary_is_a_single_plain_english_line(tmp_path):
    ledger = tmp_path / "ledger"
    _write_ledger(ledger, [_fill(order_id="o1", fill_id="o1:F", price=0.40, qty=10)])
    b = PaperBroker(ledger)
    line = b.daily_summary()
    assert "\n" not in line
    assert "paper:" in line
    assert "P&L" in line


def test_empty_ledger_is_flat_and_summarizes(tmp_path):
    b = PaperBroker(tmp_path / "ledger")
    assert b.cash == pytest.approx(0.0)
    assert b.open_positions() == []
    assert "0 open position" in b.daily_summary()
