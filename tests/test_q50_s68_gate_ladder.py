"""Offline tests for `scripts/q50_s68_gate_ladder.py` (Q50 — the L252 fees-plus-N-ticks
re-derivation of S68 under the L251 first-snapshot-with-ttc<=H entry rule).

No tape, no network, no clock. Every fixture is hand-built so the arithmetic is checkable by
eye. The load-bearing properties pinned here:

  * N=0 reproduces Q49's gate EXACTLY (so the ladder has a valid anchor),
  * the entry rule is genuinely "first snapshot with ttc<=H", not "earliest, then filter"
    (L251 — the defect that collapsed Q49's primary cut to one capture instant),
  * `touch_fill_index` stays in lockstep with Q49's boolean `simulate_leg_fill_touch`,
  * the strategy-level P&L includes the unhedged single-side legs on BOTH settlement branches
    (L249 — the only non-degenerate object under a sign-bounding gate),
  * the markout sign convention (NEGATIVE = adverse selection),
  * the verdict ladder answers data-adequacy BEFORE it answers CI (L53/L43).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.q49_s68_bothside_maker_fillsim import (
    maker_fee, simulate_leg_fill_touch, two_sided_wide_entry)
from scripts.q50_s68_gate_ladder import (
    MIN_DISTINCT_ENTRY_TS, adverse_selection_breakeven, book_mid, build_trades_at,
    cell_verdict, distinct_entry_timestamps, gate_with_ticks, leg_markout,
    select_entry_index, touch_fill_index)

T0 = datetime(2026, 7, 10, 0, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# The L252 gate: fees + N ticks
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("yes_bid,no_bid,yes_offer", [
    (0.40, 0.53, 0.47),      # 7c spread, comfortably two-sided
    (0.30, 0.68, 0.32),      # 2c spread, right at two maker fees
    (0.10, 0.85, 0.15),      # wide/thin
    (None, 0.50, 0.55),      # missing quote
    (0.0, 0.50, 0.55),       # zero bid = absence of an order, not a $0 price
])
def test_n0_reproduces_the_q49_gate_exactly(yes_bid, no_bid, yes_offer):
    """N=0 must be Q49's gate, key for key — otherwise the ladder has no anchor."""
    q49 = two_sided_wide_entry(yes_bid, no_bid, yes_offer)
    q50 = gate_with_ticks(yes_bid, no_bid, yes_offer, 0)
    assert q50["eligible"] == q49["eligible"]
    assert q50["reason"] == q49["reason"]
    for k in ("spread", "fee_yes", "fee_no", "fee_total", "gross_capture"):
        assert q50[k] == q49[k]


def test_gate_is_strictly_tighter_as_ticks_rise():
    """A book admitted at N must still be admitted at every smaller N (nested populations)."""
    yes_bid, no_bid, yes_offer = 0.30, 0.60, 0.40   # 10c spread
    admitted = [n for n in range(0, 12)
                if gate_with_ticks(yes_bid, no_bid, yes_offer, n)["eligible"]]
    assert admitted == list(range(0, max(admitted) + 1)), "admission must be a prefix in N"


def test_boundary_book_admitted_at_n0_and_rejected_at_n1():
    """The exact defect L252 names: at N=0 the gate admits books sitting ON the zero-profit
    boundary. One extra tick must exclude precisely those."""
    yes_bid, no_bid = 0.49, 0.49
    fee_total = maker_fee(yes_bid) + maker_fee(no_bid)
    yes_offer = yes_bid + fee_total                 # spread == fees exactly
    assert gate_with_ticks(yes_bid, no_bid, yes_offer, 0)["eligible"] is True
    g1 = gate_with_ticks(yes_bid, no_bid, yes_offer, 1)
    assert g1["eligible"] is False
    assert g1["reason"] == "spread_below_fees_plus_ticks"
    # one more cent of spread and it is admitted again
    assert gate_with_ticks(yes_bid, no_bid, yes_offer + 0.01, 1)["eligible"] is True


def test_required_spread_is_fees_plus_n_ticks():
    g = gate_with_ticks(0.30, 0.60, 0.45, 3)
    assert g["required_spread"] == pytest.approx(g["fee_total"] + 0.03)


def test_negative_ticks_rejected():
    with pytest.raises(ValueError):
        gate_with_ticks(0.30, 0.60, 0.45, -1)


def test_non_two_sided_reason_survives_the_tick_margin():
    g = gate_with_ticks(0.0, 0.60, 0.45, 2)
    assert g["eligible"] is False and g["reason"] == "not_two_sided"


# --------------------------------------------------------------------------- #
# The L251 entry rule
# --------------------------------------------------------------------------- #
def _snaps(ttcs):
    return [{"ttc_hours": t, "captured_at": T0 + timedelta(hours=i), "record": {}}
            for i, t in enumerate(ttcs)]


def test_entry_is_first_snapshot_within_horizon_not_the_earliest():
    """THE L251 REGRESSION. Earliest-then-filter would keep index 0 (ttc=100h) and then
    discard the ticker for being outside 24h; the honest rule enters at index 2."""
    snaps = _snaps([100.0, 50.0, 20.0, 5.0, 1.0])
    assert select_entry_index(snaps, 24.0) == 2
    assert snaps[2]["ttc_hours"] == 20.0
    # earliest-then-filter on the same ticker yields NO usable entry at all
    assert snaps[0]["ttc_hours"] > 24.0


def test_entry_none_when_no_snapshot_inside_horizon():
    assert select_entry_index(_snaps([100.0, 80.0]), 24.0) is None


def test_entry_horizon_none_is_the_earliest_snapshot():
    assert select_entry_index(_snaps([100.0, 20.0]), None) == 0
    assert select_entry_index([], None) is None


def test_entry_horizon_boundary_is_inclusive():
    assert select_entry_index(_snaps([24.0, 1.0]), 24.0) == 0


def test_distinct_entry_timestamp_count_flags_the_tape_start_artifact():
    same = [{"entry_captured_at": "2026-07-07T01:23:57Z"} for _ in range(20)]
    assert distinct_entry_timestamps(same) == 1
    assert distinct_entry_timestamps(same) < MIN_DISTINCT_ENTRY_TS
    spread = [{"entry_captured_at": f"2026-07-07T0{i}:00:00Z"} for i in range(5)]
    assert distinct_entry_timestamps(spread) == 5


# --------------------------------------------------------------------------- #
# Fill-index instrumentation must not drift from Q49's boolean rule
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ladders,best_bids,price,queue", [
    ([[[0.30, 100.0]], [[0.30, 40.0]], [[0.30, 10.0]]], [0.30, 0.30, 0.30], 0.30, 100.0),
    ([[[0.30, 50.0]], [[0.30, 50.0]], [[0.30, 50.0]]], [0.30, 0.30, 0.30], 0.30, 50.0),
    ([[[0.30, 20.0]], [[0.30, 0.0]]], [0.30, 0.30], 0.30, 20.0),
    ([[[0.30, 20.0]], [[0.30, 5.0]]], [0.40, 0.40], 0.30, 20.0),   # never at the touch
])
def test_touch_fill_index_agrees_with_the_boolean_rule(ladders, best_bids, price, queue):
    idx = touch_fill_index(ladders, best_bids, price, queue)
    filled = simulate_leg_fill_touch(ladders, best_bids, price, queue)["filled"]
    assert (idx is not None) == filled
    if idx is not None:
        assert 1 <= idx <= len(ladders) - 1


# --------------------------------------------------------------------------- #
# Markout sign convention (L253)
# --------------------------------------------------------------------------- #
def test_book_mid_uses_both_real_bids_and_is_none_on_a_one_sided_book():
    assert book_mid({"best_yes_bid": 0.40, "best_no_bid": 0.55}) == pytest.approx(0.425)
    assert book_mid({"best_yes_bid": 0.40}) is None
    assert book_mid({}) is None


def test_markout_is_negative_when_the_book_moves_against_us():
    mids = [0.50, 0.40, 0.30]
    # long YES at 0.45; the mid FALLS -> adverse
    assert leg_markout(mids, 1, "yes", 0.45, 0) == pytest.approx(-0.05)
    assert leg_markout(mids, 1, "yes", 0.45, 1) == pytest.approx(-0.15)
    # long NO at 0.45; the same fall is FAVOURABLE for the NO side
    assert leg_markout(mids, 1, "no", 0.45, 0) == pytest.approx(0.15)


def test_markout_clamps_past_the_last_snapshot_and_handles_missing():
    mids = [0.50, 0.40]
    assert leg_markout(mids, 1, "yes", 0.40, 99) == pytest.approx(0.0)
    assert leg_markout(mids, None, "yes", 0.40, 0) is None
    assert leg_markout([None, None], 1, "yes", 0.40, 0) is None


# --------------------------------------------------------------------------- #
# Strategy-level P&L must carry the unhedged single-side legs (L249)
# --------------------------------------------------------------------------- #
def _depth_rec(ticker, yes_bid, no_bid, yes_offer, yes_sizes, no_sizes):
    return {"ticker": ticker, "best_yes_bid": yes_bid, "best_no_bid": no_bid,
            "best_yes_ask": yes_offer,
            "yes_bids": [[yes_bid, s] for s in ([yes_sizes] if isinstance(yes_sizes, float)
                                                else yes_sizes)],
            "no_bids": [[no_bid, s] for s in ([no_sizes] if isinstance(no_sizes, float)
                                              else no_sizes)]}


def _per_ticker_one(ticker, seq, close):
    """seq = list of (ttc_hours, yes_size, no_size); prices held constant."""
    out = []
    for i, (ttc, ys, ns) in enumerate(seq):
        out.append({"record": _depth_rec(ticker, 0.30, 0.60, 0.40, [ys], [ns]),
                    "captured_at": close - timedelta(hours=ttc),
                    "close_time": close, "ttc_hours": ttc})
    return {ticker: out}


@pytest.mark.parametrize("result,expected_sign", [("yes", 1), ("no", -1)])
def test_single_side_fill_is_marked_to_settlement_on_both_branches(result, expected_sign):
    """A YES-only fill is an UNHEDGED directional position: it must pay $1 when the market
    settles YES and $0 when it settles NO. Booking it as zero (or as the hedged capture)
    is the L249 error this probe exists to avoid."""
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    # YES ladder drains (fills); NO ladder frozen (never fills)
    per = _per_ticker_one(tk, [(20.0, 10.0, 10.0), (10.0, 0.0, 10.0), (1.0, 0.0, 10.0)], close)
    settlement = {tk: {"result": result, "close_time": close.isoformat(),
                       "event_ticker": "KXTESTGAME-26JUL10AAABBB", "series": "KXTESTGAME",
                       "price_source_tag": "broker_truth"}}
    trades, funnel = build_trades_at(per, settlement, 24.0, 0)
    assert funnel["candidates"] == 1 and len(trades) == 1
    m = trades[0]["models"]["touch"]
    assert m["fill_category"] == "yes_only"
    # long YES at 0.30 net of one maker fee
    expected = (1.0 if result == "yes" else 0.0) - 0.30 - maker_fee(0.30)
    assert m["pnl_strategy_level"] == pytest.approx(expected)
    assert (m["pnl_strategy_level"] > 0) == (expected_sign > 0)
    assert m["pnl_both_fill"] is None, "a single-side fill is NOT a hedged capture"


def test_no_fill_books_exactly_zero_and_carries_source_tags():
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    per = _per_ticker_one(tk, [(20.0, 10.0, 10.0), (10.0, 10.0, 10.0)], close)
    settlement = {tk: {"result": "yes", "close_time": close.isoformat(),
                       "event_ticker": "KXTESTGAME-26JUL10AAABBB", "series": "KXTESTGAME",
                       "price_source_tag": "broker_truth"}}
    trades, _ = build_trades_at(per, settlement, 24.0, 0)
    m = trades[0]["models"]["touch"]
    assert m["fill_category"] == "neither"
    assert m["pnl_strategy_level"] == 0.0
    assert "real_bid" in trades[0]["price_source_tag"]
    assert "broker_truth" in trades[0]["price_source_tag"]


def test_entry_window_shifts_the_simulated_ladders():
    """Entering later must simulate over FEWER snapshots — the queue cannot observe
    departures that happened before we rested the order."""
    close = T0 + timedelta(days=3)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    per = _per_ticker_one(
        tk, [(60.0, 10.0, 10.0), (30.0, 10.0, 10.0), (20.0, 10.0, 10.0), (2.0, 0.0, 10.0)],
        close)
    settlement = {tk: {"result": "yes", "close_time": close.isoformat(),
                       "event_ticker": "KXTESTGAME-26JUL10AAABBB", "series": "KXTESTGAME",
                       "price_source_tag": "broker_truth"}}
    far, _ = build_trades_at(per, settlement, 72.0, 0)
    near, _ = build_trades_at(per, settlement, 24.0, 0)
    assert far[0]["n_snapshots"] == 4 and far[0]["entry_index"] == 0
    assert near[0]["n_snapshots"] == 2 and near[0]["entry_index"] == 2


# --------------------------------------------------------------------------- #
# Break-even haircut + the verdict ladder
# --------------------------------------------------------------------------- #
def _trade(series, pnl, category):
    return {"series": series, "models": {"touch": {"pnl_strategy_level": pnl,
                                                   "fill_category": category}}}


def test_breakeven_haircut_is_found_and_charges_two_legs_on_a_double_fill():
    trades = [_trade(f"S{i}", 0.05, "both") for i in range(12)]
    res = adverse_selection_breakeven(trades, "touch", n_boot=400)
    # 0.05 net over two filled legs dies once the charge exceeds 2.5c/leg
    assert res["breakeven_haircut_per_filled_leg"] is not None
    assert res["breakeven_haircut_per_filled_leg"] <= 0.03
    assert [row["haircut_per_filled_leg"] for row in res["ladder"]][0] == 0.0


def test_breakeven_ladder_is_monotone_non_increasing_in_mean():
    trades = [_trade(f"S{i}", 0.05, "both") for i in range(12)]
    means = [row["mean"] for row in
             adverse_selection_breakeven(trades, "touch", n_boot=300)["ladder"]]
    assert all(a >= b - 1e-9 for a, b in zip(means, means[1:]))


def _cell(n_candidates, n_units, ci, clears_tick, admissible=True, reasons=()):
    return {"clears_tick_magnitude_strategy": clears_tick,
            "analysis": {"n_candidates": n_candidates,
                         "bootstrap_strategy_level_diagnostic": {
                             "n_units_series": n_units, "ci95": ci,
                             "admissible": {"admissible": admissible,
                                            "reasons": list(reasons)}}}}


def test_verdict_ladder_answers_adequacy_before_ci():
    assert cell_verdict(_cell(0, 0, [None, None], False))[0] == "DEAD-by-adequacy"
    assert cell_verdict(_cell(50, 4, [0.05, 0.10], True))[0] == "DEAD-by-adequacy"
    assert cell_verdict(_cell(50, 12, [0.05, 0.10], True, admissible=False,
                              reasons=["no_opposing_unit"]))[0] == "DEAD-by-adequacy"


def test_verdict_ladder_ci_and_magnitude_branches():
    assert cell_verdict(_cell(50, 12, [-0.01, 0.10], True))[0] == "DEAD-by-CI"
    assert cell_verdict(_cell(50, 12, [0.0, 0.10], True))[0] == "DEAD-by-CI"
    assert cell_verdict(_cell(50, 12, [0.002, 0.10], False))[0] == "DEAD-by-magnitude"
    assert cell_verdict(_cell(50, 12, [0.02, 0.10], True))[0] == "ALIVE-CANDIDATE"
