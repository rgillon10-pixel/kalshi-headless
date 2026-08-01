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
  * the verdict ladder answers data-adequacy BEFORE it answers CI (L53/L43),
  * the THREE ROBUSTNESS ATTACKS are real code with pinned semantics (leave-one-series-out
    drops a whole series, the longshot drop removes only UNHEDGED single-side legs and drops
    units whole rather than zeroing them (L86), the placebo re-rests at a worse price without
    changing the admission gate), and every reported number carries the n_boot it used — the
    two provenance defects a verifier found in the first cut of this probe.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.q49_s68_bothside_maker_fillsim import (
    maker_fee, simulate_leg_fill_touch, two_sided_wide_entry)
from scripts.q50_s68_gate_ladder import (
    LONGSHOT_MAX_PRICE, MIN_DISTINCT_ENTRY_TS, PLACEBO_OFFSET, adverse_selection_breakeven,
    book_mid, build_trades_at, cell_verdict, distinct_entry_timestamps, drop_longshot_single_side,
    gate_with_ticks, leave_one_series_out, leg_markout, price_offset_placebo, run_robustness,
    select_entry_index, single_side_fill_price, strategy_units_by_series, touch_fill_index)

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
    # n_boot disclosure (defect-2 regression): this helper once defaulted to 4000 while the
    # headline used 10000, silently.
    assert res["n_boot"] == 400 and all(row["n_boot"] == 400 for row in res["ladder"])


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


# --------------------------------------------------------------------------- #
# THE THREE ROBUSTNESS ATTACKS (added 2026-08-01 — the provenance fix).
#
# These were prose-only in the first cut of this probe; a verifier had to re-derive them by
# hand and found the longshot CI had been quoted at an undisclosed n_boot=4000 while the
# headline used 10,000. The tests below pin BOTH the semantics and the n_boot disclosure.
# --------------------------------------------------------------------------- #
def _rt(series, pnl, category, yes_price=0.40, no_price=0.55):
    """A trade row carrying only what the robustness attacks read."""
    return {"series": series, "ticker": f"{series}-X", "event_ticker": f"{series}-E",
            "yes_fill_price": yes_price, "no_fill_price": no_price,
            "models": {"touch": {"pnl_strategy_level": pnl, "fill_category": category}}}


def test_strategy_units_group_by_series_and_keep_every_trade():
    trades = [_rt("A", 0.1, "both"), _rt("A", -0.2, "neither"), _rt("B", 0.3, "yes_only")]
    units = strategy_units_by_series(trades)
    assert units == {"A": [0.1, -0.2], "B": [0.3]}


def test_leave_one_series_out_drops_one_whole_series_per_row():
    trades = ([_rt(f"S{i}", 0.05, "both") for i in range(12)]
              + [_rt("S0", 0.04, "both"), _rt("S3", -0.02, "neither")])
    loo = leave_one_series_out(trades, "touch", n_boot=300)
    assert loo["n_series_dropped_one_at_a_time"] == 12
    assert [d["dropped_series"] for d in loo["drops"]] == sorted({t["series"] for t in trades})
    by_series = {d["dropped_series"]: d for d in loo["drops"]}
    assert by_series["S0"]["n_obs_dropped"] == 2 and by_series["S1"]["n_obs_dropped"] == 1
    # every drop leaves exactly (n_units - 1) units and (n_obs - dropped) observations
    for d in loo["drops"]:
        assert d["n_units_series"] == 11
        assert d["n_obs"] == len(trades) - d["n_obs_dropped"]


def test_leave_one_series_out_detects_a_ci_carried_by_a_single_series():
    """THE POINT OF THE ATTACK. 12 series are flat-negative and one carries the whole mean;
    dropping that one must flip the drop's CI, and the summary flag must say so."""
    trades = [_rt(f"S{i}", -0.01, "both") for i in range(12)] + [_rt("BIG", 5.0, "both")]
    loo = leave_one_series_out(trades, "touch", n_boot=300)
    assert loo["full_population"]["mean"] > 0
    assert loo["all_drops_keep_ci_positive"] is False
    assert loo["n_drops_ci_lower_positive"] < loo["n_series_dropped_one_at_a_time"]
    dropped_big = next(d for d in loo["drops"] if d["dropped_series"] == "BIG")
    assert dropped_big["ci_lower_positive"] is False
    # and the honest all-positive case still reports all-clear
    good = leave_one_series_out([_rt(f"S{i}", 0.05, "both") for i in range(12)]
                                + [_rt("S0", -0.02, "neither")], "touch", n_boot=300)
    assert good["all_drops_keep_ci_positive"] is True


def test_every_robustness_number_discloses_its_n_boot():
    """DEFECT-2 REGRESSION: the longshot CI was once computed at an undisclosed n_boot=4000
    while the headline used 10,000. Every bootstrap dict this module emits must echo the
    n_boot it actually used, and it must be the one the caller asked for."""
    trades = [_rt(f"S{i}", 0.05, "both") for i in range(12)] + [_rt("S0", -0.02, "neither")]
    loo = leave_one_series_out(trades, "touch", n_boot=250)
    assert loo["n_boot"] == 250 and loo["full_population"]["n_boot"] == 250
    assert all(d["n_boot"] == 250 for d in loo["drops"])
    ls = drop_longshot_single_side(trades, "touch", n_boot=250)
    assert ls["n_boot"] == 250 and ls["bootstrap_after_drop"]["n_boot"] == 250


def test_longshot_drop_removes_only_cheap_unhedged_single_side_legs():
    trades = [
        _rt("A", 0.7, "yes_only", yes_price=0.20),    # cheap unhedged -> dropped
        _rt("B", -0.6, "no_only", no_price=0.25),     # cheap unhedged -> dropped
        _rt("C", 0.1, "yes_only", yes_price=0.55),    # not a longshot -> kept
        _rt("D", 0.02, "both", yes_price=0.20, no_price=0.20),  # hedged -> kept
        _rt("E", 0.0, "neither", yes_price=0.10, no_price=0.10),  # no fill -> kept
    ]
    res = drop_longshot_single_side(trades, "touch", n_boot=200, max_price=0.30)
    assert res["n_dropped"] == 2 and res["n_kept"] == 3
    assert res["n_trades_in"] == len(trades)
    # units are dropped WHOLE, never zeroed (L86): the retained bootstrap sees 3 obs, not 5
    assert res["bootstrap_after_drop"]["n_obs"] == 3


def test_longshot_drop_boundary_is_inclusive_at_the_threshold():
    at = drop_longshot_single_side([_rt("A", 0.5, "yes_only", yes_price=LONGSHOT_MAX_PRICE)],
                                   "touch", n_boot=100)
    above = drop_longshot_single_side(
        [_rt("A", 0.5, "yes_only", yes_price=LONGSHOT_MAX_PRICE + 0.01)], "touch", n_boot=100)
    assert at["n_dropped"] == 1 and above["n_dropped"] == 0


def test_single_side_fill_price_is_none_for_hedged_and_unfilled_rows():
    assert single_side_fill_price(_rt("A", 0.1, "yes_only", yes_price=0.22)) == 0.22
    assert single_side_fill_price(_rt("A", 0.1, "no_only", no_price=0.33)) == 0.33
    assert single_side_fill_price(_rt("A", 0.1, "both")) is None
    assert single_side_fill_price(_rt("A", 0.0, "neither")) is None


# --- the price-offset placebo ---------------------------------------------- #
def _placebo_per_ticker(ticker, close):
    """Depth sits at the touch AND two ticks below it. The touch level drains (a baseline
    fill); the deeper level never moves and, being below the best bid, could not be hit
    anyway under price priority."""
    def rec(touch_size):
        return {"ticker": ticker, "best_yes_bid": 0.30, "best_no_bid": 0.60,
                "best_yes_ask": 0.40,
                "yes_bids": [[0.30, touch_size], [0.28, 500.0]],
                "no_bids": [[0.60, touch_size], [0.58, 500.0]]}
    seq = [(20.0, 10.0), (10.0, 0.0), (2.0, 0.0)]
    return {ticker: [{"record": rec(sz), "captured_at": close - timedelta(hours=ttc),
                      "close_time": close, "ttc_hours": ttc} for ttc, sz in seq]}


def _placebo_settlement(ticker, close):
    return {ticker: {"result": "yes", "close_time": close.isoformat(),
                     "event_ticker": "KXTESTGAME-26JUL10AAABBB", "series": "KXTESTGAME",
                     "price_source_tag": "broker_truth"}}


def test_price_offset_placebo_collapses_fill_rates_without_changing_the_gate():
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    per = _placebo_per_ticker(tk, close)
    res = price_offset_placebo(per, _placebo_settlement(tk, close), 24.0, 0,
                               "touch", n_boot=200, offset=PLACEBO_OFFSET)
    # SAME admitted population — the placebo re-prices, it does not re-gate
    assert res["baseline"]["n_candidates"] == res["placebo"]["n_candidates"] == 1
    assert res["baseline"]["yes_leg_fill_rate"] == 1.0
    assert res["baseline"]["no_leg_fill_rate"] == 1.0
    assert res["placebo"]["yes_leg_fill_rate"] == 0.0
    assert res["placebo"]["no_leg_fill_rate"] == 0.0
    assert res["fill_rate_collapsed"] is True
    assert res["offset"] == PLACEBO_OFFSET and res["n_boot"] == 200


def test_price_offset_placebo_with_zero_offset_reproduces_the_baseline():
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    res = price_offset_placebo(_placebo_per_ticker(tk, close), _placebo_settlement(tk, close),
                               24.0, 0, "touch", n_boot=200, offset=0.0)
    assert res["placebo"] == res["baseline"]
    assert res["fill_rate_collapsed"] is False, "no collapse when nothing was offset"


def test_build_trades_at_offset_shifts_the_resting_price_and_drops_non_positive_ones():
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    per = _placebo_per_ticker(tk, close)
    settle = _placebo_settlement(tk, close)
    base, _ = build_trades_at(per, settle, 24.0, 0, 0.0)
    off, _ = build_trades_at(per, settle, 24.0, 0, PLACEBO_OFFSET)
    assert base[0]["yes_fill_price"] == pytest.approx(0.30)
    assert off[0]["yes_fill_price"] == pytest.approx(0.28)
    assert off[0]["no_fill_price"] == pytest.approx(0.58)
    assert base[0]["price_offset"] == 0.0 and off[0]["price_offset"] == PLACEBO_OFFSET
    # an offset that takes a bid to zero or below is the ABSENCE of an order (L1/L105) —
    # dropped, never booked as a $0.00 fill
    deep, funnel = build_trades_at(per, settle, 24.0, 0, -0.30)
    assert deep == [] and funnel["offset_price_non_positive"] == 1 and funnel["candidates"] == 0


def test_repo_relative_never_writes_an_absolute_path_into_a_committed_report():
    """A committed artifact must not record one machine's filesystem layout."""
    from scripts.q50_s68_gate_ladder import ROBUSTNESS_OUT, _repo_relative
    rel = _repo_relative(str(ROBUSTNESS_OUT))
    assert rel == "reports/q50_s68_gate_ladder_robustness.json"
    assert not rel.startswith("/")
    # a path outside the repo is returned unchanged rather than raising
    assert _repo_relative("/somewhere/else/x.json") == "/somewhere/else/x.json"


def test_run_robustness_runs_all_three_attacks_at_one_disclosed_n_boot():
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    rob = run_robustness(_placebo_per_ticker(tk, close), _placebo_settlement(tk, close),
                         24.0, 0, "touch", n_boot=150)
    assert set(rob) >= {"cell", "headline", "leave_one_series_out",
                        "drop_longshot_single_side", "price_offset_placebo"}
    assert rob["n_boot"] == 150
    assert rob["cell"]["median_entry_spread"] == pytest.approx(0.10)
    assert rob["cell"]["median_ttc_hours_entry"] == pytest.approx(20.0)

    # EVERY nested bootstrap result must disclose the same n_boot (defect-2 regression,
    # applied to the whole returned object rather than one function at a time).
    seen = []

    def walk(obj):
        if isinstance(obj, dict):
            if "ci95" in obj:
                seen.append(obj["n_boot"])
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(rob)
    assert seen and set(seen) == {150}
