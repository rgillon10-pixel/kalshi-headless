"""Offline unit tests for scripts/q24_sports_longshot_maker_fillsim.py.

Synthetic fixtures only — NO network, NO auth, NO orders, NO real tape reads. Pins the pure
selection / queue-ahead / P&L / fill / bootstrap-admissibility logic so the machinery is
trustworthy and reusable when sports_clv and orderbook_depth eventually overlap.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location(
    "q24_probe", REPO / "scripts" / "q24_sports_longshot_maker_fillsim.py")
q24 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(q24)

from core.pricing import MAKER_FEE_RATE, fee_per_contract  # noqa: E402


# --------------------------------------------------------------------------- #
# offer_price
# --------------------------------------------------------------------------- #
def test_offer_price_observed_ask():
    assert q24.offer_price(0.15, 0.0) == pytest.approx(0.15)


def test_offer_price_ask_minus_one_cent():
    assert q24.offer_price(0.15, -0.01) == pytest.approx(0.14)


def test_offer_price_clamped_to_floor():
    # ask 0.015 - 0.01 = 0.005 < 1c floor -> clamped up to 0.01
    assert q24.offer_price(0.015, -0.01) == pytest.approx(q24.FLOOR_ASK)


# --------------------------------------------------------------------------- #
# longshot_outcomes — fair vs ask selection, floor exclusion, dedup-by-earliest
# --------------------------------------------------------------------------- #
def _clv(et, cap, outcomes):
    return {"kalshi_event_ticker": et, "captured_at": cap, "outcomes": outcomes}


def _out(tk, fair, ask):
    return {"ticker": tk, "fair_prob": fair, "pregame_ask": {"yes_ask": ask}}


def test_longshot_fair_selection_picks_low_fair():
    recs = [_clv("G1", "2026-07-03T00:00:00+00:00", [
        _out("G1-A", 0.10, 0.12),   # longshot by fair
        _out("G1-B", 0.55, 0.58),   # not a longshot
    ])]
    rows = q24.longshot_outcomes(recs, selection="fair")
    assert {r["ticker"] for r in rows} == {"G1-A"}


def test_longshot_ask_selection_picks_low_ask():
    recs = [_clv("G1", "2026-07-03T00:00:00+00:00", [
        _out("G1-A", 0.35, 0.18),   # ask-longshot (ask<=0.20) even though fair>0.20
        _out("G1-B", 0.55, 0.58),
    ])]
    rows = q24.longshot_outcomes(recs, selection="ask")
    assert {r["ticker"] for r in rows} == {"G1-A"}


def test_longshot_excludes_floor_pinned_ask():
    # a 1c-floor ask has no sellable premium and must be dropped under either selection
    recs = [_clv("G1", "2026-07-03T00:00:00+00:00", [_out("G1-A", 0.05, 0.01)])]
    assert q24.longshot_outcomes(recs, selection="fair") == []
    assert q24.longshot_outcomes(recs, selection="ask") == []


def test_longshot_dedup_keeps_earliest_capture():
    recs = [
        _clv("G1", "2026-07-04T00:00:00+00:00", [_out("G1-A", 0.10, 0.20)]),
        _clv("G1", "2026-07-03T00:00:00+00:00", [_out("G1-A", 0.10, 0.12)]),  # earlier
    ]
    rows = q24.longshot_outcomes(recs, selection="fair")
    assert len(rows) == 1
    assert rows[0]["yes_ask"] == pytest.approx(0.12)  # earliest capture retained


def test_longshot_bad_selection_raises():
    with pytest.raises(ValueError):
        q24.longshot_outcomes([], selection="midpoint")


# --------------------------------------------------------------------------- #
# queue_ahead_at — mirror-side price-time priority
# --------------------------------------------------------------------------- #
def test_queue_ahead_sums_only_at_or_above_our_no_price():
    # premium 0.20 -> our NO bid at 1-0.20 = 0.80. Only no_bids at price>=0.80 rest ahead.
    no_bids = [[0.82, 5.0], [0.80, 10.0], [0.79, 100.0], [0.10, 999.0]]
    assert q24.queue_ahead_at(no_bids, 0.20) == pytest.approx(15.0)


def test_queue_ahead_zero_when_book_all_below_our_price():
    # a typical longshot: no resting NO bids as deep as 0.80 -> front of queue
    no_bids = [[0.38, 882453.0], [0.20, 51471.0]]
    assert q24.queue_ahead_at(no_bids, 0.20) == pytest.approx(0.0)


def test_queue_ahead_ignores_malformed_levels():
    no_bids = [[0.85, 3.0], ["bad"], [0.90], None, [0.90, 2.0]]
    assert q24.queue_ahead_at(no_bids, 0.20) == pytest.approx(5.0)


# --------------------------------------------------------------------------- #
# member_fee / member_pnl — fee from sanctioned helper, both settlement legs
# --------------------------------------------------------------------------- #
def test_member_fee_matches_sanctioned_maker_fee():
    # flat 1c maker fee at every interior price (L30)
    assert q24.member_fee(0.15) == pytest.approx(
        fee_per_contract(1.0 - 0.15, rate=MAKER_FEE_RATE))
    assert q24.member_fee(0.15) == pytest.approx(0.01)


def test_pnl_longshot_loses_keeps_premium_minus_fee():
    # settle NO (longshot loses, we win) -> +premium - fee
    assert q24.member_pnl(0.15, settle_yes=False) == pytest.approx(0.15 - 0.01)


def test_pnl_longshot_wins_pays_dollar_minus_fee():
    # settle YES (longshot WINS, negative-skew leg modeled explicitly) -> premium - 1 - fee
    assert q24.member_pnl(0.15, settle_yes=True) == pytest.approx(0.15 - 1.0 - 0.01)


def test_pnl_win_leg_is_large_negative():
    # the sold-longshot-wins catastrophe must be a big loss, never conditioned away
    assert q24.member_pnl(0.15, settle_yes=True) < -0.8


# --------------------------------------------------------------------------- #
# is_filled — queue-aware, not a candle print
# --------------------------------------------------------------------------- #
def test_is_filled_true_when_touched_and_volume_clears_queue():
    assert q24.is_filled(max_touch=0.20, total_volume=100.0, premium=0.15,
                         queue_ahead=50.0) is True


def test_is_filled_false_when_never_touched():
    assert q24.is_filled(max_touch=0.10, total_volume=1e9, premium=0.15,
                         queue_ahead=0.0) is False


def test_is_filled_false_when_volume_below_queue():
    assert q24.is_filled(max_touch=0.30, total_volume=10.0, premium=0.15,
                         queue_ahead=50.0) is False


def test_is_filled_false_when_unmeasurable():
    assert q24.is_filled(None, 100.0, 0.15, 0.0) is False
    assert q24.is_filled(0.30, None, 0.15, 0.0) is False


# --------------------------------------------------------------------------- #
# nearest_no_bids — join window
# --------------------------------------------------------------------------- #
def test_nearest_no_bids_absent_ticker_is_none():
    assert q24.nearest_no_bids({}, "NOPE", 1000.0) is None


def test_nearest_no_bids_outside_window_is_none():
    idx = {"T": [(0.0, [[0.8, 1.0]])]}
    assert q24.nearest_no_bids(idx, "T", 1e9, max_delta_sec=10.0) is None


def test_nearest_no_bids_picks_closest_in_window():
    idx = {"T": [(100.0, [[0.8, 1.0]]), (200.0, [[0.8, 2.0]])]}
    got = q24.nearest_no_bids(idx, "T", 190.0, max_delta_sec=3600.0)
    assert got == [[0.8, 2.0]]


# --------------------------------------------------------------------------- #
# admissible_positive — L41 degenerate-bootstrap floor
# --------------------------------------------------------------------------- #
def test_admissible_false_when_below_min_units():
    per_unit = {f"G{i}": [0.14] for i in range(3)}  # all winning, only 3 units
    assert q24.admissible_positive(per_unit, min_units=10) is False


def test_admissible_false_when_no_losing_cluster():
    # 12 units, every one a sold-longshot-loses win -> zero losing clusters -> mechanical p=0
    per_unit = {f"G{i}": [0.14] for i in range(12)}
    assert q24.admissible_positive(per_unit, min_units=10) is False


def test_admissible_true_with_losing_cluster_and_enough_units():
    per_unit = {f"G{i}": [0.14] for i in range(11)}
    per_unit["Gloss"] = [-0.86]   # one game where the sold longshot won
    assert q24.admissible_positive(per_unit, min_units=10) is True


# --------------------------------------------------------------------------- #
# simulate + verdict — the empty-join data-adequacy path (the expected Q24 outcome)
# --------------------------------------------------------------------------- #
def test_simulate_empty_depth_join_yields_zero_fills():
    clv = [_clv("G1", "2026-07-03T00:00:00+00:00", [_out("G1-A", 0.10, 0.12)])]
    settle = {"G1-A": {"settle_yes": False, "price_source_tag": "broker_truth"}}
    candles = {"G1-A": {"total_volume": 1e6, "max_yes_ask_high": 0.5,
                        "price_source_tag": "real_ask"}}
    depth_idx = {}   # the real Q24 situation: no depth for the fair-anchored ticker
    sim = q24.simulate(clv, settle, candles, depth_idx, selection="fair")
    assert sim["n_longshot"] == 1
    assert sim["n_settle"] == 1
    assert sim["n_queue_joinable"] == 0
    assert sim["n_joinable"] == 0
    assert sim["n_fill"] == 0


def test_simulate_full_join_can_fill_and_price_both_legs():
    # a synthetic OVERLAP (what a re-collected WC window would give) exercises the fill path
    clv = [_clv("G1", "2026-07-03T00:00:00+00:00", [
        _out("G1-A", 0.10, 0.15),   # sold longshot LOSES -> +premium
        _out("G1-B", 0.12, 0.18),   # sold longshot WINS  -> -0.82 leg
    ])]
    settle = {"G1-A": {"settle_yes": False, "price_source_tag": "broker_truth"},
              "G1-B": {"settle_yes": True, "price_source_tag": "broker_truth"}}
    candles = {"G1-A": {"total_volume": 1e6, "max_yes_ask_high": 0.9},
               "G1-B": {"total_volume": 1e6, "max_yes_ask_high": 0.9}}
    cap_ts = q24._parse_ts("2026-07-03T00:00:00+00:00")   # align depth into the join window
    depth_idx = {"G1-A": [(cap_ts, [[0.85, 0.0]])], "G1-B": [(cap_ts, [[0.85, 0.0]])]}
    sim = q24.simulate(clv, settle, candles, depth_idx, selection="fair")
    assert sim["n_joinable"] == 2
    assert sim["n_fill"] == 2
    assert sim["fills_settle_no"] == 1 and sim["fills_settle_yes"] == 1
    # per-game grouping: both outcomes under the one game G1 (L6 unit = game)
    assert set(sim["per_game_pnl"].keys()) == {"G1"}
    pnls = sorted(sim["per_game_pnl"]["G1"])
    assert pnls[0] < -0.8            # the sold-longshot-wins leg present, not conditioned away
    assert pnls[1] == pytest.approx(0.15 - 0.01)


def test_verdict_empty_join_is_data_adequacy():
    sim = {"n_joinable": 0, "n_fill": 0}
    boot = {"n_units": 0, "ci95": [None, None]}
    assert q24._verdict(sim, boot, clears_mag=False, admissible=False) == "DEAD_DATA_ADEQUACY"


def test_verdict_positive_ci_but_inadmissible_is_dead():
    sim = {"n_joinable": 20, "n_fill": 20}
    boot = {"n_units": 20, "ci95": [0.05, 0.10]}
    # clears magnitude but NOT admissible (no losing cluster) -> DEAD (L41)
    assert q24._verdict(sim, boot, clears_mag=True, admissible=False) == "DEAD_CI_OR_MAGNITUDE"


def test_verdict_alive_requires_all_gates():
    sim = {"n_joinable": 20, "n_fill": 20}
    boot = {"n_units": 20, "ci95": [0.05, 0.10]}
    assert q24._verdict(sim, boot, clears_mag=True, admissible=True) == "ALIVE_UNEXPECTED"
