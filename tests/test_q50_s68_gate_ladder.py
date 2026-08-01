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
  * **L256** — every cell is scored under BOTH exit treatments and the verdict is the WORSE of
    the two; an orphan single-side leg flattened at the cross costs the two fees on an unmoved
    mirrored book, the exit leg is charged at the TAKER rate, an unquotable flatten is dropped
    rather than zeroed (L86), and `cell_verdict` RAISES when the flatten branch is absent so the
    generous branch can never become the headline by omission,
  * **L255** — every cell also carries a ZERO-INFORMATION mid-as-truth control (an unhedged
    leg's broker_truth payout replaced by the book's own contemporaneous mid), the control is
    the immediate markout minus the entry maker fee, it is settlement-INDEPENDENT, an unquotable
    mid is dropped rather than zeroed (L86), and `cell_verdict` may use it in ONE direction only
    — it removes an otherwise-ALIVE cell whose positive CI a zero-information control
    reproduces, and can never award one,
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
    LONGSHOT_MAX_PRICE, MIN_DISTINCT_ENTRY_TS, PLACEBO_OFFSET, VERDICT_SEVERITY,
    adverse_selection_breakeven, book_mid, build_trades_at, cell_verdict,
    distinct_entry_timestamps, drop_longshot_single_side, flatten_analysis,
    flatten_at_cross_pnl, gate_with_ticks, leave_one_series_out, leg_markout,
    control_reproduces, mid_as_truth_analysis, mid_as_truth_payout, mid_as_truth_pnl,
    opposite_side_ask, price_offset_placebo, run_robustness, select_entry_index,
    single_side_fill_price, strategy_units_by_series, taker_fee, touch_fill_index)

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
def _depth_rec(ticker, yes_bid, no_bid, yes_offer, yes_sizes, no_sizes, no_offer=None):
    # `best_no_ask` mirrors the YES bid the way collection/normalize.py builds it (1 - yes_bid)
    # unless a fixture overrides it; the L256 flatten reads it to close an orphan YES leg.
    return {"ticker": ticker, "best_yes_bid": yes_bid, "best_no_bid": no_bid,
            "best_yes_ask": yes_offer,
            "best_no_ask": (round(1.0 - yes_bid, 10) if no_offer is None else no_offer),
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


def _cell(n_candidates, n_units, ci, clears_tick, admissible=True, reasons=(),
          flat_ci=None, flat_clears=None, flat_units=None, flat_admissible=None,
          control_ci=(-0.02, 0.05)):
    """A synthetic cell. The L256 flatten branch DEFAULTS to a copy of the hold-to-settlement
    branch, so a test that says nothing about the exit treatment still exercises the ladder it
    means to; the worse-of-two tests below override it explicitly.

    The L255 control DEFAULTS to a NON-reproducing one (a CI straddling zero): a test that says
    nothing about the control is asserting the ladder's behaviour when the zero-information
    control did NOT reproduce the cell, which is the only case in which an ALIVE verdict may
    stand. `control_ci=None` removes the branch entirely (the missing-control test)."""
    return {"clears_tick_magnitude_strategy": clears_tick,
            "flatten_at_cross": {
                "n_units_series": (n_units if flat_units is None else flat_units),
                "ci95": (ci if flat_ci is None else flat_ci),
                "clears_tick_magnitude": (clears_tick if flat_clears is None else flat_clears),
                "admissible": {"admissible": (admissible if flat_admissible is None
                                              else flat_admissible),
                               "reasons": list(reasons)}},
            **({} if control_ci is None else {
                "mid_as_truth": {"control_treatment": "mid_as_truth",
                                 "n_units_series": n_units, "ci95": list(control_ci),
                                 "n_single_side_legs": 1, "n_unmeasurable_single_side": 0,
                                 "admissible": {"admissible": True, "reasons": []}}}),
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


# --------------------------------------------------------------------------- #
# L256 — BOTH EXIT TREATMENTS, WORSE OF THE TWO (built 2026-08-01)
#
# The lesson: a fill-sim that can leave an UNHEDGED single-side leg must report both
# hold-to-settlement AND flatten-at-cross, and a verdict that survives only the generous
# hold-to-settlement branch is not a verdict. The Q50 verifier applied the flatten treatment
# BY HAND — no committed artifact carried the number, which is exactly the L165 provenance
# hole the rest of this module was already fixing. These tests pin the treatment as code.
# --------------------------------------------------------------------------- #
def test_flatten_on_a_mirrored_unmoved_book_costs_exactly_the_two_fees():
    """L256's arithmetic prediction, COMPUTED not hardcoded: on a mirrored binary book
    (`best_no_ask == 1 - best_yes_bid`) that has not moved since our fill at the touch, the
    gross of the flatten is exactly zero, so the exit costs precisely the two fees — a small
    CERTAIN loss where hold-to-settlement booked a $0/$1 lottery."""
    entry = 0.30
    mirrored_ask = round(1.0 - entry, 10)
    got = flatten_at_cross_pnl(entry, "yes", mirrored_ask)
    assert got == pytest.approx(-(maker_fee(entry) + taker_fee(mirrored_ask)))
    # and the NO side is symmetric
    entry_no = 0.60
    got_no = flatten_at_cross_pnl(entry_no, "no", round(1.0 - entry_no, 10))
    assert got_no == pytest.approx(-(maker_fee(entry_no) + taker_fee(1.0 - entry_no)))


def test_flatten_charges_the_taker_rate_on_the_exit_leg_not_the_maker_rate():
    """L5 with its sign flipped: the flatten CROSSES the spread, so the exit leg is a TAKER
    fill (0.07), not a maker one (0.0175). Charging maker on both legs would make the honest
    branch look BETTER than it is — the opposite direction of L5's original 4x overcharge, and
    just as wrong. Pinned as an inequality on real fee values, not on the rate constants."""
    entry, exit_px = 0.30, 0.70
    honest = flatten_at_cross_pnl(entry, "yes", exit_px)
    both_maker = -(maker_fee(entry) + maker_fee(exit_px))
    assert taker_fee(exit_px) > maker_fee(exit_px), "fixture must sit where the rates differ"
    assert honest == pytest.approx(-(maker_fee(entry) + taker_fee(exit_px)))
    assert honest < both_maker, "the taker exit must be strictly more expensive"


@pytest.mark.parametrize("opposite_ask,expect_sign", [
    (0.60, 1),    # book moved TOWARD us after the fill -> flatten out at a profit
    (0.70, -1),   # unmoved mirrored book -> the two fees, a certain small loss
    (0.80, -1),   # book moved AGAINST us -> flatten out at a loss
])
def test_flatten_sign_tracks_which_way_the_book_moved(opposite_ask, expect_sign):
    """Sign convention pinned on BOTH sides (the same discipline as the markout test): the
    flatten gross is `1 - entry - opposite_ask`, so it is positive iff the book moved in our
    favour between resting and flattening."""
    got = flatten_at_cross_pnl(0.30, "yes", opposite_ask)
    assert (got > 0) == (expect_sign > 0)
    # strictly monotone: a worse exit quote is a worse P&L
    assert flatten_at_cross_pnl(0.30, "yes", 0.60) > flatten_at_cross_pnl(0.30, "yes", 0.80)


def test_flatten_is_unmeasurable_not_zero_when_the_opposite_ask_is_missing():
    """L86 — never book an unmeasured leg as a free zero. An absent or 0.00 opposite ask is the
    ABSENCE of an offer (L1/L105), so the flatten is UNMEASURABLE and must return None."""
    assert flatten_at_cross_pnl(0.30, "yes", None) is None
    assert opposite_side_ask({"best_no_ask": None}, "yes") is None
    assert opposite_side_ask({}, "yes") is None
    assert opposite_side_ask(None, "yes") is None
    assert opposite_side_ask({"best_no_ask": 0.0}, "yes") is None, "a $0 ask is not free money"
    assert opposite_side_ask({"best_no_ask": 1.4}, "yes") is None, "off-scale quote"
    assert opposite_side_ask({"best_no_ask": 1.0}, "yes") == 1.0, "a $1 ask is a real quote"
    assert opposite_side_ask({"best_yes_ask": 0.42}, "no") == 0.42
    with pytest.raises(ValueError):
        opposite_side_ask({"best_no_ask": 0.5}, "sideways")
    with pytest.raises(ValueError):
        flatten_at_cross_pnl(0.30, "sideways", 0.70)


def _one_ticker(tk, seq, close, no_offer=None):
    """seq = list of (ttc_hours, yes_size, no_size); prices constant, `no_offer` overridable."""
    return {tk: [{"record": _depth_rec(tk, 0.30, 0.60, 0.40, [ys], [ns], no_offer=no_offer),
                  "captured_at": close - timedelta(hours=ttc),
                  "close_time": close, "ttc_hours": ttc}
                 for (ttc, ys, ns) in seq]}


def _settle(tk, close, result):
    return {tk: {"result": result, "close_time": close.isoformat(),
                 "event_ticker": "KXTESTGAME-26JUL10AAABBB", "series": "KXTESTGAME",
                 "price_source_tag": "broker_truth"}}


@pytest.mark.parametrize("result", ["yes", "no"])
def test_orphan_leg_flatten_is_settlement_independent_unlike_the_hold_branch(result):
    """THE POINT OF L256, end to end. The same YES-only orphan is a +$0.69 jackpot or a -$0.31
    write-off under hold-to-settlement depending purely on the coin flip; flattened at the
    cross it is the SAME small certain loss either way. Reporting only the first treatment
    converts 'we were left holding an unwanted position' into income."""
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    per = _one_ticker(tk, [(20.0, 10.0, 10.0), (10.0, 0.0, 10.0), (1.0, 0.0, 10.0)], close)
    trades, funnel = build_trades_at(per, _settle(tk, close, result), 24.0, 0)
    m = trades[0]["models"]["touch"]
    assert m["fill_category"] == "yes_only"
    assert funnel["flatten_unquotable_single_side"] == 0
    # mirrored, unmoved book -> the two fees, whichever way it settled
    assert m["pnl_strategy_flatten"] == pytest.approx(-(maker_fee(0.30) + taker_fee(0.70)))
    assert m["flatten_price"] == pytest.approx(0.70)
    assert m["flatten_price_source_tag"] == "real_ask"
    assert "real_ask(flatten_exit)" in trades[0]["price_source_tag"]
    assert m["pnl_strategy_flatten"] < m["pnl_strategy_level"] if result == "yes" else True
    # the generous branch still swings with the settlement; the honest one does not
    assert m["pnl_strategy_level"] == pytest.approx(
        (1.0 if result == "yes" else 0.0) - 0.30 - maker_fee(0.30))


@pytest.mark.parametrize("seq,expect", [
    ([(20.0, 10.0, 10.0), (10.0, 0.0, 0.0), (1.0, 0.0, 0.0)], "both"),
    ([(20.0, 10.0, 10.0), (10.0, 10.0, 10.0)], "neither"),
])
def test_hedged_and_unfilled_rows_are_identical_under_the_two_treatments(seq, expect):
    """A double fill is already hedged and a no-fill has nothing to close, so the exit
    treatment is a NO-OP on those categories — only the orphan legs may move. If this drifts,
    the two branches stop being comparable and the worse-of-two is meaningless."""
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    trades, _ = build_trades_at(_one_ticker(tk, seq, close), _settle(tk, close, "yes"), 24.0, 0)
    m = trades[0]["models"]["touch"]
    assert m["fill_category"] == expect
    assert m["pnl_strategy_flatten"] == m["pnl_strategy_level"]
    assert m["flatten_price"] is None and m["flatten_price_source_tag"] is None


def test_unquotable_orphan_is_dropped_from_the_flatten_bootstrap_not_zeroed():
    """An orphan whose opposite ask is unquotable at the fill instant leaves the flatten branch
    speaking for a SMALLER population than the hold branch. That is a coverage limit — counted
    and published (`n_unmeasurable_single_side`), never a $0.00 exit (L86)."""
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    per = _one_ticker(tk, [(20.0, 10.0, 10.0), (10.0, 0.0, 10.0), (1.0, 0.0, 10.0)], close,
                      no_offer=0.0)      # a $0 ask == absence of an offer
    trades, funnel = build_trades_at(per, _settle(tk, close, "yes"), 24.0, 0)
    m = trades[0]["models"]["touch"]
    assert m["fill_category"] == "yes_only"
    assert m["pnl_strategy_flatten"] is None and m["pnl_strategy_level"] is not None
    assert funnel["flatten_unquotable_single_side"] == 1
    fa = flatten_analysis(trades, "touch", n_boot=200)
    assert fa["n_single_side_legs"] == 1 and fa["n_unmeasurable_single_side"] == 1
    assert fa["n_obs"] == 0, "the row must be DROPPED, not booked at 0.0"
    assert fa["exit_treatment"] == "flatten_at_cross" and fa["n_boot"] == 200
    assert "real_ask" in fa["price_source_tag"]


def test_turnover_model_reports_no_flatten_because_it_localises_no_fill_instant():
    """The `turnover` rule accumulates departures over the whole hold and never says WHEN a leg
    filled, so there is no snapshot at which to read a flatten quote. Honest answer: None +
    counted (L86). It is a labeled diagnostic anyway (L250) — the verdict rests on `touch`."""
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    per = _one_ticker(tk, [(20.0, 10.0, 10.0), (10.0, 0.0, 10.0), (1.0, 0.0, 10.0)], close)
    trades, funnel = build_trades_at(per, _settle(tk, close, "yes"), 24.0, 0)
    turn = trades[0]["models"]["turnover"]
    if turn["fill_category"] in ("yes_only", "no_only"):
        assert turn["pnl_strategy_flatten"] is None
        assert funnel["flatten_no_fill_instant"] >= 1


def test_cell_verdict_takes_the_worse_of_the_two_exit_treatments():
    """The operative half of L256, in code: a cell that is ALIVE only under the generous
    hold-to-settlement branch must NOT be reported ALIVE. This is the exact shape of Q50's ten
    real cells — hold-to-settlement CI > 0, flatten CI straddling zero."""
    hold_alive_flat_dead = _cell(100, 13, [0.024, 0.152], True,
                                 flat_ci=[-0.015, 0.070], flat_clears=False)
    v, why = cell_verdict(hold_alive_flat_dead)
    assert v == "DEAD-by-CI"
    assert "flatten_at_cross" in why and "L256" in why and "hold=ALIVE-CANDIDATE" in why

    # symmetric: the WORSE branch wins whichever one it is
    hold_dead_flat_alive = _cell(100, 13, [-0.01, 0.10], True,
                                 flat_ci=[0.02, 0.12], flat_clears=True)
    assert cell_verdict(hold_dead_flat_alive)[0] == "DEAD-by-CI"

    # a thin flatten population is an ADEQUACY answer and outranks a CI answer
    thin_flat = _cell(100, 13, [0.02, 0.12], True, flat_units=4)
    assert cell_verdict(thin_flat)[0] == "DEAD-by-adequacy"

    # only when BOTH branches clear does the cell stay alive
    both_alive = _cell(100, 13, [0.02, 0.12], True)
    v2, why2 = cell_verdict(both_alive)
    assert v2 == "ALIVE-CANDIDATE" and "BOTH exit treatments" in why2


def test_cell_verdict_refuses_to_score_a_cell_with_no_flatten_branch():
    """Pinning the ABSENCE of a generous-branch fallback. If a future refactor drops the
    flatten branch, this must go RED rather than silently reverting to the treatment L256 was
    filed to stop being the headline."""
    cell = _cell(100, 13, [0.02, 0.12], True)
    del cell["flatten_at_cross"]
    with pytest.raises(KeyError, match="L256"):
        cell_verdict(cell)


def test_verdict_severity_ranks_alive_as_the_least_severe_answer():
    """`max` over the two branches is only 'the worse of the two' if ALIVE ranks lowest."""
    assert VERDICT_SEVERITY["ALIVE-CANDIDATE"] == min(VERDICT_SEVERITY.values())
    assert (VERDICT_SEVERITY["DEAD-by-adequacy"] > VERDICT_SEVERITY["DEAD-by-CI"]
            > VERDICT_SEVERITY["DEAD-by-magnitude"] > VERDICT_SEVERITY["ALIVE-CANDIDATE"])


# --------------------------------------------------------------------------- #
# HARD real-tape acceptance (L256). Anchored to COMMITTED tape, no network, no clock.
# --------------------------------------------------------------------------- #
def test_acceptance_l256_flatten_at_cross_kills_the_alive_hold_to_settlement_cell():
    """THE claim L256 makes, re-derived from code over the committed tape instead of quoted
    from a verifier's hand-run session (the L165 hole in the lesson row itself).

    The L254 headline cell (H=24h, gate = fees + 1 tick) is the one whose ALIVE status was the
    whole question. Under hold-to-settlement its strategy-level CI is > 0 and clears the tick
    gate; under flatten-at-cross the CI straddles zero, so the cell is DEAD and the entire
    apparent edge lived in the unhedged legs' settlement lottery.

    NON-VACUITY IS ASSERTED FIRST: if the hold branch ever stops being ALIVE on this tape, this
    test FAILS loudly rather than passing for the wrong reason — the premise would have moved
    and the claim needs re-deriving, not silently re-blessing."""
    from scripts.q49_s68_bothside_maker_fillsim import (
        DEPTH_GLOB, SETTLEMENT_GLOB, load_preclose_snapshots, load_settlements)
    from scripts.q50_s68_gate_ladder import branch_verdict

    settlement, _ = load_settlements(SETTLEMENT_GLOB)
    per_ticker, _ = load_preclose_snapshots(DEPTH_GLOB, settlement)
    trades, funnel = build_trades_at(per_ticker, settlement, 24.0, 1)
    assert funnel["candidates"] > 0, "committed depth tape no longer yields the L254 headline cell"

    from core.bootstrap import block_bootstrap, bootstrap_verdict_admissible, clears_tick_magnitude
    from scripts.q49_s68_bothside_maker_fillsim import PRICE_TICK, per_series_pnl

    hold_units = per_series_pnl(trades, "pnl_strategy_level", "touch")
    hold_boot = block_bootstrap(hold_units, n_boot=2000)
    hold = {"n_units_series": len(hold_units), "ci95": hold_boot["ci95"],
            "admissible": bootstrap_verdict_admissible(hold_units, min_units=10)}
    hold_v, _ = branch_verdict(len(trades), hold,
                               clears_tick_magnitude(hold_boot["ci95"], tick=PRICE_TICK,
                                                     min_ticks=1.0), "hold_to_settlement")
    assert hold_v == "ALIVE-CANDIDATE", (
        f"PREMISE MOVED: the H=24/N=1 cell is {hold_v} under hold-to-settlement on this tape, "
        f"so L256's kill has nothing to kill. Re-derive the lesson, do not relax this test.")

    fa = flatten_analysis(trades, "touch", n_boot=2000)
    assert fa["n_single_side_legs"] > 0, "no orphan legs -> the treatment would be vacuous"
    flat_v, _ = branch_verdict(len(trades), fa, fa["clears_tick_magnitude"], "flatten_at_cross")
    assert flat_v != "ALIVE-CANDIDATE", (
        f"L256 CONTRADICTED on committed tape: flatten-at-cross CI {fa['ci95']} survives. "
        f"That is a FINDING, not a test to bend.")
    assert fa["ci95"][0] is not None and fa["ci95"][0] <= 0.0

    # and the whole cell therefore reports the worse branch
    cell = {"analysis": {"n_candidates": len(trades),
                         "bootstrap_strategy_level_diagnostic": dict(hold)},
            "clears_tick_magnitude_strategy": clears_tick_magnitude(
                hold_boot["ci95"], tick=PRICE_TICK, min_ticks=1.0),
            "flatten_at_cross": fa}
    assert cell_verdict(cell)[0] != "ALIVE-CANDIDATE"


def test_acceptance_l256_every_hold_alive_cell_dies_under_flatten_in_the_committed_ladder():
    """The FULL 10-cell claim, pinned against this probe's own COMMITTED artifact so it costs
    a file read rather than a 54-second ladder re-run. `reports/q50_s68_gate_ladder_summary.json`
    is regenerated by `python3 scripts/q50_s68_gate_ladder.py`, so a drift between the code and
    this assertion shows up the next time the probe is run and committed.

    L256's row claimed the verifier's hand-run flatten killed all ten ALIVE cells "CI straddling
    zero". Re-derived from code, the KILL is confirmed 10/10 — but the stated MECHANISM holds for
    only three of them. The other seven keep a flatten CI lower bound that is still positive and
    still SUB-TICK (+0.0006 to +0.0060, i.e. a fraction of one cent), so they die on L27's
    tick-magnitude gate, not on a straddle. Flatten alone would not have killed those seven;
    flatten AND L27 together do. That refinement is why the treatment had to become code."""
    import json
    from pathlib import Path

    from core.bootstrap import clears_tick_magnitude
    from scripts.q49_s68_bothside_maker_fillsim import MIN_CI_UNITS, PRICE_TICK
    from scripts.q50_s68_gate_ladder import SUMMARY_OUT

    summary = json.loads(Path(SUMMARY_OUT).read_text(encoding="utf-8"))

    def _branch_alive(units, ci, admissible):
        return (units is not None and units >= MIN_CI_UNITS and admissible
                and ci[0] is not None and ci[0] > 0.0
                and clears_tick_magnitude(ci, tick=PRICE_TICK, min_ticks=1.0))

    hold_alive, flat_alive, straddle, subtick = [], [], [], []
    for c in summary["cells"]:
        st = c["analysis"]["bootstrap_strategy_level_diagnostic"]
        fl = c["flatten_at_cross"]
        if not _branch_alive(st["n_units_series"], st["ci95"],
                             st["admissible"]["admissible"]):
            continue
        key = (c["horizon_hours"], c["gate_extra_ticks"])
        hold_alive.append(key)
        assert c["verdict"] != "ALIVE-CANDIDATE", (
            f"cell {key} is ALIVE under hold-to-settlement and the cell verdict did NOT take "
            f"the worse branch — L256's worse-of-two is not being applied")
        if _branch_alive(fl["n_units_series"], fl["ci95"], fl["admissible"]["admissible"]):
            flat_alive.append(key)
        elif fl["ci95"][0] is None or fl["ci95"][0] <= 0.0:
            straddle.append(key)
        else:
            subtick.append((key, fl["ci95"][0]))

    assert len(hold_alive) == 10, (
        f"PREMISE MOVED: {len(hold_alive)} hold-to-settlement ALIVE cells in the committed "
        f"ladder, not the 10 L256 was written about — re-derive, do not relax")
    assert flat_alive == [], (
        f"L256 CONTRADICTED on the committed ladder: {flat_alive} survive flatten-at-cross. "
        f"That is a FINDING, not a test to bend.")
    assert len(straddle) == 3 and len(subtick) == 7, (
        f"mechanism split moved: {len(straddle)} straddle / {len(subtick)} sub-tick "
        f"(L256's row records 3 and 7)")
    assert all(0.0 < lo < PRICE_TICK for _, lo in subtick), (
        "the seven sub-tick kills must have a POSITIVE but sub-one-cent lower bound — that is "
        "exactly the L27 gate doing the work L256's prose credited to a straddle")
    # the treatment must also be reported for every cell, alive or not
    assert all("flatten_at_cross" in c for c in summary["cells"])
    assert summary["overall_verdict"].startswith("DEAD")


# --------------------------------------------------------------------------- #
# L255 — THE ZERO-INFORMATION MID-AS-TRUTH CONTROL (built 2026-08-01)
#
# The lesson: a maker fill-sim that books an unhedged leg to settlement must publish a control
# in which that leg carries NO outcome information (its payout is the book's own contemporaneous
# mid), and must not call a cell ALIVE when the control reproduces its positive CI. The Q50
# verifier ran this control BY HAND over `reports/q50_s68_gate_ladder_rows.jsonl`; L255's own row
# records that "the control's own output is NOT persisted in any committed artifact" — the L165
# provenance hole these tests and `mid_as_truth_*` close.
# --------------------------------------------------------------------------- #
def test_mid_as_truth_payout_is_the_mid_for_yes_and_its_complement_for_no():
    assert mid_as_truth_payout("yes", 0.35) == pytest.approx(0.35)
    assert mid_as_truth_payout("no", 0.35) == pytest.approx(0.65)
    # the two sides of the same book must exhaust the $1 payout exactly once
    assert (mid_as_truth_payout("yes", 0.42) + mid_as_truth_payout("no", 0.42)
            == pytest.approx(1.0))


def test_mid_as_truth_payout_is_unmeasurable_not_zero_on_a_one_sided_book():
    """L86/L23: an absent mid means we cannot measure the control for that leg. None, never 0.0
    — a zero payout is a LOSS of the whole stake, which is a claim, not a missing value."""
    assert mid_as_truth_payout("yes", None) is None
    assert mid_as_truth_pnl(0.30, "yes", None) is None


@pytest.mark.parametrize("bad", [-0.01, 1.01, 5.0])
def test_mid_as_truth_payout_rejects_a_non_probability(bad):
    with pytest.raises(ValueError):
        mid_as_truth_payout("yes", bad)


def test_mid_as_truth_payout_rejects_an_unknown_side():
    with pytest.raises(ValueError):
        mid_as_truth_payout("sideways", 0.5)
    with pytest.raises(ValueError):
        mid_as_truth_pnl(0.30, "sideways", 0.5)


def test_mid_as_truth_pnl_is_the_immediate_markout_minus_the_entry_maker_fee():
    """The identity that keeps the control and the L253 markout from drifting apart: the control
    IS the k=0 markout charged its entry fee. Checked on both sides at several prices, COMPUTED
    on both sides of the equation rather than hardcoded."""
    mids = [0.20, 0.35, 0.55]
    for side, price in (("yes", 0.30), ("yes", 0.05), ("no", 0.60), ("no", 0.90)):
        for idx in range(len(mids)):
            got = mid_as_truth_pnl(price, side, mids[idx])
            want = leg_markout(mids, idx, side, price, 0) - maker_fee(price)
            assert got == pytest.approx(want)


def test_mid_as_truth_pnl_charges_the_maker_rate_not_the_taker_rate():
    """The control isolates the PAYOUT term. Charging the exit/taker rate here would make the
    control artificially worse than the branch it is compared against (the mirror image of the
    L5 fee error) and would break the attribution the control exists to make."""
    assert mid_as_truth_pnl(0.30, "yes", 0.35) == pytest.approx(0.35 - 0.30 - maker_fee(0.30))
    assert maker_fee(0.30) != taker_fee(0.30), "fixture assumes the two rates differ"


@pytest.mark.parametrize("result", ["yes", "no"])
def test_orphan_control_is_settlement_independent_unlike_the_hold_branch(result):
    """THE POINT OF L255, end to end, on the same fixture the L256 test uses. The identical
    YES-only orphan is +$0.69 or -$0.31 under hold-to-settlement depending purely on the coin
    flip; under the zero-information control it is the SAME small number either way, because the
    control contains no outcome information at all. The book mids to 0.35 ((0.30 + (1-0.60))/2),
    so the control books 0.35 - 0.30 - one maker fee."""
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    per = _one_ticker(tk, [(20.0, 10.0, 10.0), (10.0, 0.0, 10.0), (1.0, 0.0, 10.0)], close)
    trades, funnel = build_trades_at(per, _settle(tk, close, result), 24.0, 0)
    m = trades[0]["models"]["touch"]
    assert m["fill_category"] == "yes_only"
    assert funnel["control_unquotable_single_side"] == 0
    assert m["mid_at_fill"] == pytest.approx(0.35)
    assert m["mid_price_source_tag"] == "midpoint"
    assert m["pnl_strategy_mid_as_truth"] == pytest.approx(0.35 - 0.30 - maker_fee(0.30))
    # the generous branch still swings with the settlement; the control does not
    assert m["pnl_strategy_level"] == pytest.approx(
        (1.0 if result == "yes" else 0.0) - 0.30 - maker_fee(0.30))
    assert "midpoint(l255_control)" in trades[0]["price_source_tag"]


def test_the_control_is_not_the_flatten_treatment():
    """Two DIFFERENT counterfactuals on the same orphan — if they ever coincide numerically by
    construction, one of them has stopped saying anything. Flatten = pay the crossing ask and be
    rid of the position (maker in, TAKER out); control = keep it but assume the book is right."""
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    per = _one_ticker(tk, [(20.0, 10.0, 10.0), (10.0, 0.0, 10.0), (1.0, 0.0, 10.0)], close)
    trades, _ = build_trades_at(per, _settle(tk, close, "yes"), 24.0, 0)
    m = trades[0]["models"]["touch"]
    assert m["pnl_strategy_flatten"] == pytest.approx(-(maker_fee(0.30) + taker_fee(0.70)))
    assert m["pnl_strategy_mid_as_truth"] != pytest.approx(m["pnl_strategy_flatten"])


@pytest.mark.parametrize("seq,expect", [
    ([(20.0, 10.0, 10.0), (10.0, 0.0, 0.0), (1.0, 0.0, 0.0)], "both"),
    ([(20.0, 10.0, 10.0), (10.0, 10.0, 10.0)], "neither"),
])
def test_hedged_and_unfilled_rows_are_identical_under_the_control(seq, expect):
    """A double fill carries no settlement term and a no-fill carries no position, so replacing
    the payout with a mid cannot move them. If this drifts, the control stops being comparable
    with the branch it is a control FOR."""
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    trades, _ = build_trades_at(_one_ticker(tk, seq, close), _settle(tk, close, "yes"), 24.0, 0)
    m = trades[0]["models"]["touch"]
    assert m["fill_category"] == expect
    assert m["pnl_strategy_mid_as_truth"] == m["pnl_strategy_level"]
    assert m["mid_at_fill"] is None and m["mid_price_source_tag"] is None


def test_turnover_model_reports_no_control_because_it_localises_no_fill_instant():
    """Same reason the flatten branch is None under `turnover` (L250/L86): with no fill instant
    there is no snapshot whose mid to read. Honest None + counted, never a zero."""
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    per = _one_ticker(tk, [(20.0, 10.0, 10.0), (10.0, 0.0, 10.0), (1.0, 0.0, 10.0)], close)
    trades, funnel = build_trades_at(per, _settle(tk, close, "yes"), 24.0, 0)
    turn = trades[0]["models"]["turnover"]
    if turn["fill_category"] in ("yes_only", "no_only"):
        assert turn["pnl_strategy_mid_as_truth"] is None
        assert funnel["control_no_fill_instant"] >= 1


def test_unquotable_mid_is_dropped_from_the_control_bootstrap_not_zeroed():
    """A one-sided book AT THE FILL INSTANT makes the control unmeasurable for that orphan. The
    row is DROPPED and counted (`n_unmeasurable_single_side`), never booked at 0.0 (L86), so the
    control's population size is always visible next to the branch it is compared with."""
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    per = _one_ticker(tk, [(20.0, 10.0, 10.0), (10.0, 0.0, 10.0), (1.0, 0.0, 10.0)], close)
    per[tk][1]["record"]["best_no_bid"] = None          # one-sided at the fill snapshot
    trades, funnel = build_trades_at(per, _settle(tk, close, "yes"), 24.0, 0)
    m = trades[0]["models"]["touch"]
    assert m["fill_category"] == "yes_only"
    assert m["pnl_strategy_mid_as_truth"] is None and m["pnl_strategy_level"] is not None
    assert funnel["control_unquotable_single_side"] == 1
    ca = mid_as_truth_analysis(trades, "touch", n_boot=200)
    assert ca["n_single_side_legs"] == 1 and ca["n_unmeasurable_single_side"] == 1
    assert ca["n_obs"] == 0, "the row must be DROPPED, not booked at 0.0"
    assert ca["control_treatment"] == "mid_as_truth" and ca["n_boot"] == 200
    assert "midpoint" in ca["price_source_tag"] and "real_bid" in ca["price_source_tag"]


def test_control_reproduces_only_when_both_lower_bounds_are_positive():
    """The decision rule, in isolation. `reproduces` is TRUE only when a strategy that provably
    cannot pick winners returns the same POSITIVE answer."""
    pos = {"ci95": [0.02, 0.15]}
    assert control_reproduces(pos, {"ci95": [0.003, 0.10]})["reproduces"] is True
    assert control_reproduces(pos, {"ci95": [-0.01, 0.10]})["reproduces"] is False
    assert control_reproduces(pos, {"ci95": [0.0, 0.10]})["reproduces"] is False
    assert control_reproduces(pos, {"ci95": [None, None]})["reproduces"] is False
    # nothing to reproduce when the branch under test is not positive
    for hold_ci in ([-0.05, 0.05], [0.0, 0.05], [None, None]):
        r = control_reproduces({"ci95": hold_ci}, {"ci95": [0.02, 0.15]})
        assert r["reproduces"] is False and "nothing for a control" in r["reason"]


def test_cell_verdict_downgrades_an_alive_cell_whose_control_reproduces_it():
    """L255 operative: both exit treatments clear, and a ZERO-INFORMATION control returns the
    same positive CI -> the positive part is gate arithmetic, so the cell is NOT alive."""
    cell = _cell(100, 13, [0.02, 0.12], True, control_ci=(0.015, 0.11))
    v, why = cell_verdict(cell)
    assert v == "DEAD-by-zero-information-control"
    assert "L255" in why and "NO outcome information" in why


def test_cell_verdict_keeps_alive_when_the_control_does_not_reproduce():
    """The control is not a blanket kill: a cell whose control comes back straddling zero keeps
    its ALIVE verdict, and the report says so explicitly rather than silently."""
    v, why = cell_verdict(_cell(100, 13, [0.02, 0.12], True, control_ci=(-0.03, 0.04)))
    assert v == "ALIVE-CANDIDATE"
    assert "BOTH exit treatments" in why and "L255 control did NOT reproduce" in why


def test_control_can_only_remove_an_alive_never_award_one():
    """One-way by construction: a cell already dead on its CI stays DEAD-by-CI even when the
    zero-information control is wildly positive. A control is never evidence FOR an edge."""
    dead = _cell(100, 13, [-0.01, 0.10], True, control_ci=(0.30, 0.60))
    assert cell_verdict(dead)[0] == "DEAD-by-CI"
    thin = _cell(100, 4, [0.05, 0.10], True, control_ci=(0.30, 0.60))
    assert cell_verdict(thin)[0] == "DEAD-by-adequacy"


def test_cell_verdict_refuses_to_report_alive_without_the_control():
    """Pinning the ABSENCE of a no-control fallback (the L256 pattern applied to L255): a cell
    that would be reported ALIVE without its zero-information control must go RED, not through.
    A cell that is already DEAD needs no control — nothing can be taken away twice."""
    alive_no_control = _cell(100, 13, [0.02, 0.12], True, control_ci=None)
    with pytest.raises(KeyError, match="L255"):
        cell_verdict(alive_no_control)
    dead_no_control = _cell(100, 13, [-0.01, 0.10], True, control_ci=None)
    assert cell_verdict(dead_no_control)[0] == "DEAD-by-CI"


def test_control_kill_is_registered_in_the_severity_map():
    assert "DEAD-by-zero-information-control" in VERDICT_SEVERITY
    assert (VERDICT_SEVERITY["DEAD-by-zero-information-control"]
            > VERDICT_SEVERITY["ALIVE-CANDIDATE"])


def test_run_robustness_publishes_the_control_beside_the_headline():
    """The artifact half of L255: `--robustness-only` must carry the control, at the SAME n_boot
    as everything else in the object (the defect-2 discipline applies to it too)."""
    close = T0 + timedelta(days=2)
    tk = "KXTESTGAME-26JUL10AAABBB-AAA"
    rob = run_robustness(_placebo_per_ticker(tk, close), _placebo_settlement(tk, close),
                         24.0, 0, "touch", n_boot=150)
    ct = rob["mid_as_truth_control"]
    assert ct["control_treatment"] == "mid_as_truth" and ct["n_boot"] == 150
    assert "midpoint" in ct["price_source_tag"]


# --------------------------------------------------------------------------- #
# HARD real-tape acceptance (L255). Anchored to COMMITTED tape/artifacts, no network, no clock.
# --------------------------------------------------------------------------- #
def test_acceptance_l255_zero_information_control_reproduces_the_headline_cell():
    """L255's claim, re-derived from code over the committed tape instead of quoted from a
    verifier's hand-run session (the L165 hole the lesson row itself records).

    NON-VACUITY IS ASSERTED FIRST: the hold branch of the H=24/N=1 cell must still be positive on
    this tape, otherwise there is no positive verdict for a control to reproduce and the premise
    has moved."""
    from core.bootstrap import block_bootstrap
    from scripts.q49_s68_bothside_maker_fillsim import (
        DEPTH_GLOB, SETTLEMENT_GLOB, load_preclose_snapshots, load_settlements, per_series_pnl)

    settlement, _ = load_settlements(SETTLEMENT_GLOB)
    per_ticker, _ = load_preclose_snapshots(DEPTH_GLOB, settlement)
    trades, funnel = build_trades_at(per_ticker, settlement, 24.0, 1)
    assert funnel["candidates"] > 0, "committed depth tape no longer yields the L254 headline cell"

    hold_boot = block_bootstrap(per_series_pnl(trades, "pnl_strategy_level", "touch"),
                                n_boot=2000)
    assert hold_boot["ci95"][0] is not None and hold_boot["ci95"][0] > 0.0, (
        f"PREMISE MOVED: hold-to-settlement CI {hold_boot['ci95']} is no longer positive on "
        f"this tape, so L255 has no positive verdict to reproduce. Re-derive, do not relax.")

    ca = mid_as_truth_analysis(trades, "touch", n_boot=2000)
    assert ca["n_single_side_legs"] > 0, "no orphan legs -> the control would be vacuous"
    assert ca["n_unmeasurable_single_side"] == 0, (
        "coverage moved: some orphan leg now has no quotable mid at its fill instant; the "
        "control would be speaking for a smaller population than the branch it is compared with")
    assert control_reproduces({"ci95": hold_boot["ci95"]}, ca)["reproduces"] is True, (
        f"L255 CONTRADICTED on committed tape: the zero-information control CI {ca['ci95']} "
        f"does NOT reproduce the hold branch {hold_boot['ci95']}. That is a FINDING, not a "
        f"test to bend.")


def test_acceptance_l255_control_reproduces_every_hold_alive_cell_in_the_committed_ladder():
    """The FULL ladder claim, pinned against this probe's own COMMITTED artifact so it costs a
    file read rather than a re-run. Measured 2026-08-01 over
    `reports/q50_s68_gate_ladder_summary.json`: all TEN hold-to-settlement ALIVE cells have a
    zero-information control whose CI is also strictly positive — 10/10, with ZERO unmeasurable
    orphan legs anywhere in the ladder. L255 is therefore confirmed AS STATED (unlike L256, whose
    stated straddle mechanism held for only 3 of the same 10 cells).

    Note what this does and does not say: no cell's printed verdict is
    DEAD-by-zero-information-control, because the L256 flatten treatment already kills all ten
    before the control is consulted (the control is a one-way override on a cell that would
    otherwise be ALIVE). The control's value here is evidentiary — it shows the positive part of
    those CIs is gate arithmetic — plus prospective, for any future cell that survives flatten."""
    import json
    from pathlib import Path

    from core.bootstrap import clears_tick_magnitude
    from scripts.q49_s68_bothside_maker_fillsim import MIN_CI_UNITS, PRICE_TICK
    from scripts.q50_s68_gate_ladder import SUMMARY_OUT

    summary = json.loads(Path(SUMMARY_OUT).read_text(encoding="utf-8"))
    assert all("mid_as_truth" in c for c in summary["cells"]), (
        "the control must be published for EVERY cell, alive or not — a control reported only "
        "where it is convenient is not a control")

    hold_alive, reproduced, not_reproduced = [], [], []
    for c in summary["cells"]:
        st = c["analysis"]["bootstrap_strategy_level_diagnostic"]
        ct = c["mid_as_truth"]
        alive = (st["n_units_series"] is not None and st["n_units_series"] >= MIN_CI_UNITS
                 and st["admissible"]["admissible"] and st["ci95"][0] is not None
                 and st["ci95"][0] > 0.0
                 and clears_tick_magnitude(st["ci95"], tick=PRICE_TICK, min_ticks=1.0))
        if not alive:
            continue
        key = (c["horizon_hours"], c["gate_extra_ticks"])
        hold_alive.append(key)
        assert ct["n_unmeasurable_single_side"] == 0, f"cell {key} lost control coverage"
        (reproduced if control_reproduces(st, ct)["reproduces"]
         else not_reproduced).append(key)

    assert len(hold_alive) == 10, (
        f"PREMISE MOVED: {len(hold_alive)} hold-to-settlement ALIVE cells in the committed "
        f"ladder, not the 10 L255/L256 were written about — re-derive, do not relax")
    assert not_reproduced == [], (
        f"L255 CONTRADICTED on the committed ladder: the zero-information control fails to "
        f"reproduce {not_reproduced}. That is a FINDING, not a test to bend.")
    assert len(reproduced) == 10
    assert summary["overall_verdict"].startswith("DEAD")
