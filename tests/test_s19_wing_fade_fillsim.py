"""scripts.s19_wing_fade_fillsim — S19/Q23 elevated-wing stale-ask MAKER fade fill-sim
(LOOP-QUEUE.md Q23). Offline: NO network — every fill input (queue depth, executed volume,
settlement) is a synthetic fixture. Covers the fill-sim logic itself: the queue-clearing
rule, the flat 1c maker fee, and the settlement join. Mirrors the S14/S20 offline test style."""
from __future__ import annotations

import pytest

from scripts import s19_wing_fade_fillsim as sim
from core.pricing import MAKER_FEE_RATE, TAKER_FEE_RATE, fee_per_contract


# --------------------------------------------------------------------------- #
# wing selection — Q20 wing_elevated definition EXACTLY
# --------------------------------------------------------------------------- #
def _wing(ask, bid, floor_strike, cap_strike):
    return {"strike_type": "between", "floor_strike": floor_strike, "cap_strike": cap_strike,
            "yes_ask": ask, "yes_bid": bid, "ticker": "KXBTC-T"}


def test_wing_elevated_qualifies_far_stale_in_band_ask():
    # spot 60000, spacing 100, band +/-3 -> active within +/-300. A strike at 61000 is 10
    # spacings out (outside band); ask 0.40 in [0.20,0.67]; yes_bid 0 -> qualifies.
    o = _wing(0.40, 0.0, 60950, 61050)  # coord 61000
    assert sim.is_wing_elevated(o, spot=60000.0, spacing=100.0) is True


def test_wing_rejected_inside_active_band():
    # coord 60100 is within +/-3*100 of spot 60000 -> active, not a wing
    o = _wing(0.40, 0.0, 60050, 60150)
    assert sim.is_wing_elevated(o, spot=60000.0, spacing=100.0) is False


def test_wing_rejected_ask_below_band():
    o = _wing(0.10, 0.0, 60950, 61050)  # far + one-sided but ask 0.10 < 0.20
    assert sim.is_wing_elevated(o, spot=60000.0, spacing=100.0) is False


def test_wing_rejected_ask_above_band():
    o = _wing(0.80, 0.0, 60950, 61050)  # ask 0.80 > 0.67
    assert sim.is_wing_elevated(o, spot=60000.0, spacing=100.0) is False


def test_wing_rejected_two_sided_nonzero_bid():
    o = _wing(0.40, 0.05, 60950, 61050)  # yes_bid != 0 -> not the stale one-sided case
    assert sim.is_wing_elevated(o, spot=60000.0, spacing=100.0) is False


def test_wing_rejected_when_spacing_undefined():
    o = _wing(0.40, 0.0, 60950, 61050)
    assert sim.is_wing_elevated(o, spot=60000.0, spacing=None) is False


# --------------------------------------------------------------------------- #
# queue_ahead — sum of no_bids resting at price >= (1 minus yes_ask)
# --------------------------------------------------------------------------- #
def test_queue_ahead_sums_at_and_above_our_price():
    # yes_ask 0.40 -> our NO bid at 0.60. Levels at 0.60/0.61/0.62 are ahead; 0.59 is behind.
    no_bids = [[0.62, 100.0], [0.61, 50.0], [0.60, 30.0], [0.59, 999.0]]
    assert sim.queue_ahead_at(no_bids, yes_ask=0.40) == pytest.approx(180.0)


def test_queue_ahead_empty_book_is_zero():
    assert sim.queue_ahead_at([], yes_ask=0.40) == pytest.approx(0.0)


def test_queue_ahead_ignores_malformed_levels():
    no_bids = [[0.60, 30.0], ["bad"], [0.61], [0.62, "x"]]
    assert sim.queue_ahead_at(no_bids, yes_ask=0.40) == pytest.approx(30.0)


# --------------------------------------------------------------------------- #
# queue-clearing fill rule — the binding L39 gate (NOT a candle print)
# --------------------------------------------------------------------------- #
def test_fill_true_when_volume_clears_queue_and_touched():
    # touched (max_high 0.45 >= ask 0.40) AND executed vol 200 >= queue 180 -> FILL
    assert sim.is_filled(max_high=0.45, total_volume=200.0, yes_ask=0.40,
                         queue_ahead=180.0) is True


def test_fill_false_when_volume_below_queue():
    # touched, but executed vol 100 < queue 180 -> our offer at the BACK never reached -> NO FILL
    assert sim.is_filled(max_high=0.45, total_volume=100.0, yes_ask=0.40,
                         queue_ahead=180.0) is False


def test_fill_false_when_ask_never_touched():
    # even with huge volume, if the max trade high never reached our ask, no lift -> NO FILL
    assert sim.is_filled(max_high=0.05, total_volume=100000.0, yes_ask=0.40,
                         queue_ahead=0.0) is False


def test_fill_false_when_volume_unmeasurable():
    # no offline executed-volume -> no-fill, not a free assumption
    assert sim.is_filled(max_high=0.45, total_volume=None, yes_ask=0.40,
                         queue_ahead=0.0) is False


def test_fill_false_when_high_unmeasurable():
    assert sim.is_filled(max_high=None, total_volume=100000.0, yes_ask=0.40,
                         queue_ahead=0.0) is False


def test_fill_boundary_volume_equals_queue():
    # exactly clearing the queue counts as a fill (>= boundary)
    assert sim.is_filled(max_high=0.40, total_volume=180.0, yes_ask=0.40,
                         queue_ahead=180.0) is True


# --------------------------------------------------------------------------- #
# flat 1c maker fee (L30) — via the sanctioned helper, maker not taker rate
# --------------------------------------------------------------------------- #
def test_member_fee_is_flat_one_cent_across_interior_prices():
    # L30: fee_per_contract(P, MAKER_FEE_RATE) == 0.01 for every interior fill price
    for ask in (0.20, 0.33, 0.40, 0.55, 0.67):
        assert sim.member_fee(ask) == pytest.approx(0.01)


def test_member_fee_uses_maker_rate_on_no_bid_price():
    # the fill price is the NO bid (1 minus yes_ask); fee must use MAKER, not TAKER, rate
    ask = 0.40
    assert sim.member_fee(ask) == pytest.approx(fee_per_contract(1 - ask, rate=MAKER_FEE_RATE))
    # taker fee at 0.60 is 0.02 (0.07*0.6*0.4 -> ceil to 0.02) != the maker 0.01
    assert sim.member_fee(ask) != pytest.approx(fee_per_contract(1 - ask, rate=TAKER_FEE_RATE))


# --------------------------------------------------------------------------- #
# settlement join — settle-YES pays $1 (loss), settle-NO keeps premium (win)
# --------------------------------------------------------------------------- #
def test_pnl_settle_no_keeps_premium_minus_fee():
    # win leg: keep the yes_ask premium, minus the flat 1c fee
    assert sim.member_pnl(0.40, settle_yes=False) == pytest.approx(0.40 - 0.01)


def test_pnl_settle_yes_pays_the_dollar_minus_fee():
    # loss leg: the short pays $1 against the collected premium, minus the flat 1c fee
    assert sim.member_pnl(0.40, settle_yes=True) == pytest.approx(0.40 - 1.0 - 0.01)


def test_pnl_settle_yes_is_toxic_relative_to_settle_no():
    # the mechanism: a fill that settles YES is ~$1 worse than one that settles NO
    win = sim.member_pnl(0.40, settle_yes=False)
    lose = sim.member_pnl(0.40, settle_yes=True)
    assert win - lose == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# end-to-end simulate() on a tiny synthetic corpus (no network, no tape)
# --------------------------------------------------------------------------- #
def _record(event, ticker, ask, bid, floor_s, cap_s, spot, winner_ticker, captured_at):
    """A minimal crypto_hourly-shaped record with one settled event + one outcome."""
    return {
        "series": "KXBTC", "captured_at": captured_at,
        "spot": {"price": spot, "price_source_tag": "synthetic"},
        "current": {"event_ticker": event, "close_time": "2026-07-11T01:00:00+00:00",
                    "outcomes": [{"strike_type": "between", "floor_strike": floor_s,
                                  "cap_strike": cap_s, "yes_ask": ask, "yes_bid": bid,
                                  "ticker": ticker}]},
        "previous_settlement": {"event_ticker": event,
                                "results": {ticker: ("yes" if ticker == winner_ticker else "no")},
                                "price_source_tag": "broker_truth"},
    }


def _ladder_record():
    """A 4-member between-ladder spaced $100 (so infer_strike_spacing -> 100, band +/-300)
    with three near-money two-sided members and one far, stale, one-sided wing at coord
    61000 (1000 out, well outside the +/-300 band). Winner = a NEAR member -> the WING
    settles NO (the win leg)."""
    return {
        "series": "KXBTC", "captured_at": "2026-07-11T00:00:00+00:00",
        "spot": {"price": 60000.0, "price_source_tag": "synthetic"},
        "current": {"event_ticker": "KXBTC-E1", "close_time": "2026-07-11T01:00:00+00:00",
                    "outcomes": [
                        {"strike_type": "between", "floor_strike": 59900, "cap_strike": 60000,
                         "yes_ask": 0.34, "yes_bid": 0.32, "ticker": "KXBTC-E1-N1"},
                        {"strike_type": "between", "floor_strike": 60000, "cap_strike": 60100,
                         "yes_ask": 0.35, "yes_bid": 0.33, "ticker": "KXBTC-E1-N2"},
                        {"strike_type": "between", "floor_strike": 60100, "cap_strike": 60200,
                         "yes_ask": 0.34, "yes_bid": 0.32, "ticker": "KXBTC-E1-N3"},
                        {"strike_type": "between", "floor_strike": 60950, "cap_strike": 61050,
                         "yes_ask": 0.40, "yes_bid": 0.0, "ticker": "KXBTC-E1-WING"},
                    ]},
        "previous_settlement": {"event_ticker": "KXBTC-E1",
                                "results": {"KXBTC-E1-N1": "no", "KXBTC-E1-N2": "yes",
                                            "KXBTC-E1-N3": "no", "KXBTC-E1-WING": "no"},
                                "price_source_tag": "broker_truth"},
    }


def test_simulate_counts_wing_and_fill_offline():
    rec = _ladder_record()
    ts = sim._parse_ts("2026-07-11T00:00:00+00:00")
    depth_idx = {"KXBTC-E1-WING": [(ts + 20.0, [[0.60, 50.0], [0.59, 999.0]])]}
    # executed vol 100 >= queue 50 (only the 0.60 level is >= our 0.60), touched at 0.42
    candle = {"KXBTC-E1-WING": {"start_ts": ts, "end_ts": ts + 3600,
                                "total_volume": 100.0, "max_high_dollars": 0.42}}
    out = sim.simulate([rec], depth_idx, candle)
    assert out["n_wing"] == 1
    assert out["n_joinable"] == 1
    assert out["n_fill"] == 1
    assert out["fills_settle_no"] == 1  # WING settled NO -> win leg
    assert out["fills_settle_yes"] == 0
    # P&L booked by event-hour: +0.40 - 0.01 = 0.39
    assert out["per_event_pnl"]["KXBTC-E1"] == [pytest.approx(0.39)]


def test_simulate_no_fill_when_queue_not_measurable():
    # same wing but NO depth entry -> queue unmeasurable -> no-fill, not counted joinable
    rec = _ladder_record()
    ts = sim._parse_ts("2026-07-11T00:00:00+00:00")
    candle = {"KXBTC-E1-WING": {"start_ts": ts, "total_volume": 100000.0,
                                "max_high_dollars": 0.99}}
    out = sim.simulate([rec], depth_idx={}, candle_cache=candle)
    assert out["n_wing"] == 1
    assert out["n_joinable"] == 0
    assert out["n_fill"] == 0
