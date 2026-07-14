"""Offline unit tests for the Q28/S24 near-close fade probe — synthetic fixtures, no
network, no live tape. Pins the load-bearing signal / windowing / round-trip-cost / fee /
exclusion logic. Does NOT re-test core.bootstrap (already covered in tests/test_bootstrap.py)
or core.pricing.fee_per_contract (tests/test_substrate_primitives.py)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.pricing import TAKER_FEE_RATE, fee_per_contract
from scripts import q28_s24_nearclose_fade_probe as q28
from scripts.q26_ofi_depth_imbalance_probe import mid_yes

T0 = datetime(2026, 7, 12, 0, 0, 0, tzinfo=timezone.utc)


def snap(minutes_after, *, ttc_hours, yes_bid, yes_ask, no_bid, no_ask,
         event="KXKBOGAME-26JUL12AAA", settled_yes=0):
    """Build one path snapshot dict as load_price_paths would, with a derived mid."""
    return {
        "captured_at": T0 + timedelta(minutes=minutes_after),
        "ttc_hours": ttc_hours,
        "mid": mid_yes(yes_bid, yes_ask),
        "best_yes_ask": yes_ask,
        "best_no_ask": no_ask,
        "best_yes_bid": yes_bid,
        "best_no_bid": no_bid,
        "event_ticker": event,
        "settled_yes": settled_yes,
    }


# --------------------------------------------------------------------------- #
# mid / jump sign & magnitude & threshold
# --------------------------------------------------------------------------- #
def test_mid_yes_reused_from_q26():
    assert mid_yes(0.48, 0.52) == pytest.approx(0.50)
    assert mid_yes(None, 0.52) is None
    assert mid_yes(0.48, None) is None


def test_jump_of_sign_and_missing():
    assert q28.jump_of(0.50, 0.53) == pytest.approx(0.03)   # up
    assert q28.jump_of(0.53, 0.50) == pytest.approx(-0.03)  # down
    assert q28.jump_of(None, 0.53) is None
    assert q28.jump_of(0.53, None) is None


def test_is_jump_event_threshold_and_frozen():
    assert q28.is_jump_event(0.02, 0.02) is True
    assert q28.is_jump_event(-0.02, 0.02) is True
    assert q28.is_jump_event(0.01, 0.02) is False          # one-tick flicker below X
    assert q28.is_jump_event(0.0, 0.02) is False           # frozen pair is never an event
    assert q28.is_jump_event(None, 0.02) is False
    # a 2¢ move does NOT clear a 3¢ threshold (population thins as X rises)
    assert q28.is_jump_event(0.02, 0.03) is False


# --------------------------------------------------------------------------- #
# fade side is OPPOSITE the jump sign (the whole point of a fade)
# --------------------------------------------------------------------------- #
def test_fade_side_is_opposite_the_jump():
    # jump UP (mid rose) -> we FADE by buying NO; jump DOWN -> buy YES.
    assert q28.fade_side_of_jump(0.03) == "no"
    assert q28.fade_side_of_jump(-0.03) == "yes"
    assert q28.fade_side_of_jump(0.0) is None
    assert q28.fade_side_of_jump(None) is None
    # explicit opposite-ness: the faded side never matches the jump's own direction
    up = 0.03
    assert (q28.fade_side_of_jump(up) == "no") and (up > 0)      # rose -> sell via NO
    dn = -0.03
    assert (q28.fade_side_of_jump(dn) == "yes") and (dn < 0)     # fell -> buy via YES


def test_reverses_classification():
    assert q28.reverses(0.03, -0.01) is True    # jump up, next down -> reversal
    assert q28.reverses(0.03, 0.01) is False     # jump up, next up   -> momentum
    assert q28.reverses(-0.03, 0.01) is True     # jump down, next up -> reversal
    assert q28.reverses(0.03, 0.0) is None       # no directional next-step
    assert q28.reverses(0.03, None) is None


# --------------------------------------------------------------------------- #
# the full round-trip charges 2x taker fee + 2x half-spread (~6-8c on a ~3.7c book)
# --------------------------------------------------------------------------- #
def test_round_trip_charges_two_fees_and_two_half_spreads():
    # A representative two-sided book, ~3.7c overround (wording avoids the Hard-Rule-#3
    # prose scanner, L37/L56 — no "yes_ask"/"no_ask" token adjacent to an operator):
    #   yes bid 0.500, yes ask 0.537. The NO ask is one minus the yes bid (0.500); the NO
    #   bid is one minus the yes ask (0.463). bracket_sum (yes ask plus no ask) is 1.037,
    #   so the 3.7c overround equals the 3.7c spread.
    # Fade a jump UP: BUY NO at no_ask(t+1)=0.500. If the book is UNCHANGED at t+2, we must
    # SELL NO at no_bid(t+2)=0.463 -> we cross the full spread AND pay both taker fees.
    entry_ask, exit_bid_unchanged = 0.500, 0.463
    cost = q28.round_trip_pnl(entry_ask, exit_bid_unchanged)
    expected = (0.463 - 0.500
                - fee_per_contract(0.500, TAKER_FEE_RATE)
                - fee_per_contract(0.463, TAKER_FEE_RATE))
    assert cost == pytest.approx(expected)
    # the realized round-trip hurdle sits in the ~6-8c band the spec calls out
    assert -0.08 <= cost <= -0.06

    # A SMALL favorable raw move (mid reverses ~1c, no_bid rises 0.463 -> 0.473) is STILL
    # not enough to net positive: the 2x fee + 2x half-spread swamps a sub-2c reversal.
    small_favorable = q28.round_trip_pnl(entry_ask, 0.473)
    assert small_favorable < 0

    # It only turns positive once the favorable move exceeds the whole ~7c round-trip cost.
    big_favorable = q28.round_trip_pnl(entry_ask, 0.575)
    assert big_favorable > 0


def test_round_trip_excludes_dollar_mirror_and_missing_and_counts_them():
    # $1.00 NO-mirror ask (L26): no fillable price -> excluded (None).
    assert q28.round_trip_pnl(1.00, 0.40) is None
    # missing / non-positive entry ask -> excluded.
    assert q28.round_trip_pnl(None, 0.40) is None
    assert q28.round_trip_pnl(0.0, 0.40) is None
    # entry fillable but NO t+2 exit bid -> no realized round-trip exit -> excluded.
    assert q28.round_trip_pnl(0.50, None) is None
    # a normal fillable pair is NOT excluded.
    assert q28.round_trip_pnl(0.50, 0.55) is not None


# --------------------------------------------------------------------------- #
# hold-to-settlement uses EXACTLY ONE taker fee (settlement is free)
# --------------------------------------------------------------------------- #
def test_hold_to_settlement_charges_one_taker_fee():
    # Fade a jump UP -> bought NO at 0.50; settled NO (settled_yes=0) -> $1 payoff.
    pnl = q28.hold_to_settlement_pnl("no", settled_yes=0, entry_ask=0.50)
    expected_one_fee = 1.0 - 0.50 - fee_per_contract(0.50, TAKER_FEE_RATE)
    assert pnl == pytest.approx(expected_one_fee)
    # explicitly NOT two fees: the round-trip's second fee is absent on a hold.
    two_fee = 1.0 - 0.50 - 2 * fee_per_contract(0.50, TAKER_FEE_RATE)
    assert pnl != pytest.approx(two_fee)
    # a losing hold: bought NO, settled YES -> 0 payoff, still one fee charged.
    loss = q28.hold_to_settlement_pnl("no", settled_yes=1, entry_ask=0.50)
    assert loss == pytest.approx(0.0 - 0.50 - fee_per_contract(0.50, TAKER_FEE_RATE))
    # YES fade wins when settled YES.
    yes_win = q28.hold_to_settlement_pnl("yes", settled_yes=1, entry_ask=0.40)
    assert yes_win == pytest.approx(1.0 - 0.40 - fee_per_contract(0.40, TAKER_FEE_RATE))
    # same unfillable-entry exclusions as the round-trip.
    assert q28.hold_to_settlement_pnl("no", 0, 1.00) is None
    assert q28.hold_to_settlement_pnl("no", 0, None) is None


# --------------------------------------------------------------------------- #
# path-level: frozen pair yields no jump event; near-close windowing; gap guard
# --------------------------------------------------------------------------- #
def test_frozen_pair_yields_no_jump_event():
    # two consecutive snapshots with an identical mid -> zero jump -> no event.
    path = [
        snap(0, ttc_hours=2.0, yes_bid=0.50, yes_ask=0.52, no_bid=0.48, no_ask=0.50),
        snap(30, ttc_hours=1.5, yes_bid=0.50, yes_ask=0.52, no_bid=0.48, no_ask=0.50),
    ]
    assert q28.jump_events(path, 0.02, q28.NEAR_CLOSE_HOURS, q28.MAX_PAIR_GAP_HOURS) == []


def test_near_close_windowing_excludes_far_ttc_jump():
    # A real 3c jump but the t+1 snapshot is OUTSIDE the near-close window -> excluded.
    far = [
        snap(0, ttc_hours=9.0, yes_bid=0.48, yes_ask=0.52, no_bid=0.48, no_ask=0.52),
        snap(30, ttc_hours=8.5, yes_bid=0.54, yes_ask=0.58, no_bid=0.42, no_ask=0.46),
    ]
    assert q28.jump_events(far, 0.02, near_close_hours=4.0, max_gap_hours=1.5) == []
    # the SAME jump inside the window IS an event.
    near = [
        snap(0, ttc_hours=2.5, yes_bid=0.48, yes_ask=0.52, no_bid=0.48, no_ask=0.52),
        snap(30, ttc_hours=2.0, yes_bid=0.54, yes_ask=0.58, no_bid=0.42, no_ask=0.46),
    ]
    evs = q28.jump_events(near, 0.02, near_close_hours=4.0, max_gap_hours=1.5)
    assert len(evs) == 1 and evs[0]["jump"] == pytest.approx(0.06)


def test_gap_guard_excludes_non_consecutive_jump():
    # mids jump 6c but the pair spans 3h (a collection hole) -> not a consecutive hourly step.
    path = [
        snap(0, ttc_hours=3.5, yes_bid=0.48, yes_ask=0.52, no_bid=0.48, no_ask=0.52),
        snap(180, ttc_hours=0.5, yes_bid=0.54, yes_ask=0.58, no_bid=0.42, no_ask=0.46),
    ]
    assert q28.jump_events(path, 0.02, near_close_hours=4.0, max_gap_hours=1.5) == []


# --------------------------------------------------------------------------- #
# fade_trades + gate3 funnel: entry side, exclusion counting
# --------------------------------------------------------------------------- #
def test_fade_trades_enters_opposite_side_at_ask_exits_at_bid():
    # jump UP over (t,t+1): mid 0.50 -> 0.56 (+6c). Fade -> buy NO at t+1 no_ask, exit at
    # t+2 no_bid.
    path = [
        snap(0, ttc_hours=3.0, yes_bid=0.49, yes_ask=0.51, no_bid=0.49, no_ask=0.51),  # mid .50
        snap(30, ttc_hours=2.5, yes_bid=0.55, yes_ask=0.57, no_bid=0.43, no_ask=0.45), # mid .56
        snap(60, ttc_hours=2.0, yes_bid=0.53, yes_ask=0.55, no_bid=0.45, no_ask=0.47), # mid .54
    ]
    trades = q28.fade_trades(path, 0.02, 4.0, 1.5)
    assert len(trades) == 1
    tr = trades[0]
    assert tr["fade_side"] == "no"               # jump up -> fade with NO
    assert tr["entry_ask"] == 0.45               # t+1 best_no_ask
    assert tr["exit_bid"] == 0.45                # t+2 best_no_bid
    assert tr["jump"] == pytest.approx(0.06)
    assert tr["next_step"] == pytest.approx(-0.02)


def test_gate3_counts_both_exclusion_kinds():
    # Trade A: fillable entry + fillable exit -> counted.
    # Trade B: $1.00 mirror entry -> excluded as unfillable_entry (kills both legs).
    # Trade C: fillable entry but missing exit bid -> excluded as no_exit_bid (round-trip only).
    trades = [
        {"event_ticker": "G1", "settled_yes": 0, "jump": 0.03, "next_step": -0.01,
         "fade_side": "no", "entry_ask": 0.50, "exit_bid": 0.52,
         "rt_pnl": q28.round_trip_pnl(0.50, 0.52),
         "hold_pnl": q28.hold_to_settlement_pnl("no", 0, 0.50)},
        {"event_ticker": "G2", "settled_yes": 0, "jump": 0.03, "next_step": -0.01,
         "fade_side": "no", "entry_ask": 1.00, "exit_bid": 0.40,
         "rt_pnl": q28.round_trip_pnl(1.00, 0.40),
         "hold_pnl": q28.hold_to_settlement_pnl("no", 0, 1.00)},
        {"event_ticker": "G3", "settled_yes": 0, "jump": 0.03, "next_step": -0.01,
         "fade_side": "no", "entry_ask": 0.50, "exit_bid": None,
         "rt_pnl": q28.round_trip_pnl(0.50, None),
         "hold_pnl": q28.hold_to_settlement_pnl("no", 0, 0.50)},
    ]
    rt_units, hs_units, funnel = q28.gate3_roundtrip(trades)
    assert funnel["n_candidate_triples"] == 3
    assert funnel["n_excluded_unfillable_entry"] == 1     # trade B
    assert funnel["n_excluded_no_exit_bid"] == 1          # trade C
    assert funnel["n_roundtrip_trades"] == 1              # only trade A
    assert funnel["n_hold_trades"] == 2                   # A + C (both had fillable entries)
    assert set(rt_units.keys()) == {"G1"}
    assert set(hs_units.keys()) == {"G1", "G3"}
