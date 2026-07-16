"""scripts.s14_queue_fillsim — S14 REVALIDATION: queue-aware ladder-underwriting fill-sim.

Offline: NO network, NO tape reads — every fill input (queue depth, executed volume,
settlement) is a tiny in-memory synthetic fixture. Covers the swapped fill mechanism: the
per-member queue-aware test, the winner-vs-non-winner measurability asymmetry (the
load-bearing gate #2), and the by-event-hour bootstrap grouping. Mirrors the S14/S19 offline
fixture style. The pure fill primitives (`is_filled`, `queue_ahead_at`, `member_premium`) are
IMPORTED from s19/s14 and already unit-tested there — here we test s14_queue_fillsim's own
composition of them."""
from __future__ import annotations

import pytest

from scripts import s14_queue_fillsim as q


def _member(ticker, ask, floor_s, cap_s):
    return {"strike_type": "between", "floor_strike": floor_s, "cap_strike": cap_s,
            "yes_ask": ask, "ticker": ticker}


ENTRY_TS = q._parse_ts("2026-07-11T00:00:00+00:00")


# --------------------------------------------------------------------------- #
# member_queue_fill — None == UNMEASURABLE; else filled per the queue rule
# --------------------------------------------------------------------------- #
def test_member_queue_fill_fills_when_touched_and_volume_clears_queue():
    o = _member("KX-A", 0.40, 100, 199)
    depth = {"KX-A": [(ENTRY_TS + 20.0, [[0.60, 50.0], [0.59, 999.0]])]}  # queue at >=0.60 = 50
    candle = {"KX-A": {"start_ts": ENTRY_TS, "total_volume": 100.0, "max_high_dollars": 0.42}}
    res = q.member_queue_fill(o, ENTRY_TS, depth, candle)
    assert res is not None
    assert res["queue_ahead"] == pytest.approx(50.0)
    assert res["filled"] is True  # touched (0.42>=0.40) AND vol 100 >= queue 50


def test_member_queue_fill_no_fill_when_volume_below_queue():
    o = _member("KX-A", 0.40, 100, 199)
    depth = {"KX-A": [(ENTRY_TS, [[0.60, 500.0]])]}  # queue 500 ahead
    candle = {"KX-A": {"start_ts": ENTRY_TS, "total_volume": 100.0, "max_high_dollars": 0.99}}
    res = q.member_queue_fill(o, ENTRY_TS, depth, candle)
    assert res is not None and res["filled"] is False  # vol 100 < queue 500


def test_member_queue_fill_none_when_no_depth_join():
    o = _member("KX-A", 0.40, 100, 199)
    candle = {"KX-A": {"start_ts": ENTRY_TS, "total_volume": 100.0, "max_high_dollars": 0.99}}
    assert q.member_queue_fill(o, ENTRY_TS, depth_idx={}, candle_cache=candle) is None


def test_member_queue_fill_none_when_no_candle():
    o = _member("KX-A", 0.40, 100, 199)
    depth = {"KX-A": [(ENTRY_TS, [[0.60, 50.0]])]}
    assert q.member_queue_fill(o, ENTRY_TS, depth, candle_cache={}) is None


def test_member_queue_fill_none_when_candle_window_misaligned():
    o = _member("KX-A", 0.40, 100, 199)
    depth = {"KX-A": [(ENTRY_TS, [[0.60, 50.0]])]}
    # start_ts far from entry (> CANDLE_WINDOW_TOL_SEC) -> unmeasurable
    candle = {"KX-A": {"start_ts": ENTRY_TS + 10_000.0, "total_volume": 100.0,
                       "max_high_dollars": 0.99}}
    assert q.member_queue_fill(o, ENTRY_TS, depth, candle) is None


def test_member_queue_fill_none_when_depth_outside_delta():
    o = _member("KX-A", 0.40, 100, 199)
    # depth capture 10_000s from entry (> DEPTH_JOIN_MAX_DELTA_SEC 600s) -> no join
    depth = {"KX-A": [(ENTRY_TS + 10_000.0, [[0.60, 50.0]])]}
    candle = {"KX-A": {"start_ts": ENTRY_TS, "total_volume": 100.0, "max_high_dollars": 0.99}}
    assert q.member_queue_fill(o, ENTRY_TS, depth, candle) is None


# --------------------------------------------------------------------------- #
# simulate_event_queue — the trade composition + measurability asymmetry
# --------------------------------------------------------------------------- #
def _entry(outcomes, captured_at="2026-07-11T00:00:00+00:00",
           close_time="2026-07-11T01:00:00+00:00"):
    return {"captured_at": captured_at, "series": "KXBTC",
            "current": {"event_ticker": "E1", "close_time": close_time, "outcomes": outcomes}}


def _full_depth(tickers, size=1.0):
    """Depth join for every ticker, one level at 0.99 (>= any 1-ask) with small size so any
    touched member with positive volume fills."""
    return {tk: [(ENTRY_TS, [[0.99, size]])] for tk in tickers}


def _full_candle(tickers, vol=1000.0, high=0.99):
    return {tk: {"start_ts": ENTRY_TS, "total_volume": vol, "max_high_dollars": high}
            for tk in tickers}


def test_simulate_winner_filled_pays_one_dollar():
    outs = [_member("E1-W", 0.30, 100, 199),   # winner, priced
            _member("E1-N", 0.20, 200, 299),   # near, priced
            _member("E1-F", 0.01, 900, 999)]   # 1c-floor wing, skipped (nets $0)
    entry = _entry(outs)
    settlement = {"winner_ticker": "E1-W"}
    tickers = ["E1-W", "E1-N", "E1-F"]
    row = q.simulate_event_queue("E1", entry, settlement,
                                 _full_depth(tickers), _full_candle(tickers))
    assert row["winner_measurable"] is True
    assert row["winner_filled"] is True
    assert row["payout"] == 1.0
    assert row["n_priced_relevant"] == 2   # 1c wing skipped
    # premium from W and N; pnl = premium - 1
    from scripts.s14_ladder_fillsim import member_premium
    exp_prem = member_premium(0.30) + member_premium(0.20)
    assert row["premium_collected"] == pytest.approx(exp_prem)
    assert row["pnl"] == pytest.approx(exp_prem - 1.0)


def test_simulate_non_winner_unmeasurable_is_no_fill_not_drop():
    # winner IS measurable (so the event-hour stays in the population); a non-winner member has
    # NO depth join -> it must be a NO-FILL (no premium), NOT a drop, NOT free income.
    outs = [_member("E1-W", 0.30, 100, 199), _member("E1-N", 0.20, 200, 299)]
    entry = _entry(outs)
    settlement = {"winner_ticker": "E1-W"}
    depth = _full_depth(["E1-W"])          # only the winner joins depth
    candle = _full_candle(["E1-W", "E1-N"])
    row = q.simulate_event_queue("E1", entry, settlement, depth, candle)
    assert row["winner_measurable"] is True
    assert row["n_priced_relevant"] == 2
    assert row["n_joinable"] == 1          # only the winner was measurable
    from scripts.s14_ladder_fillsim import member_premium
    # only the winner's premium is collectable; the unmeasurable near member contributes $0
    assert row["premium_collected"] == pytest.approx(member_premium(0.30))
    assert row["pnl"] == pytest.approx(member_premium(0.30) - 1.0)


def test_simulate_winner_unmeasurable_drops_event_hour():
    # winner has NO depth join -> winner leg unmeasurable -> the WHOLE event-hour is dropped
    # from the bootstrap population (winner_measurable False), NOT counted with payout=0.
    outs = [_member("E1-W", 0.30, 100, 199), _member("E1-N", 0.20, 200, 299)]
    entry = _entry(outs)
    settlement = {"winner_ticker": "E1-W"}
    depth = _full_depth(["E1-N"])           # winner does NOT join depth
    candle = _full_candle(["E1-W", "E1-N"])
    row = q.simulate_event_queue("E1", entry, settlement, depth, candle)
    assert row is not None
    assert row["winner_measurable"] is False
    # such a row is excluded by pnl_by_event -> not in the bootstrap population
    assert q.pnl_by_event([row]) == {}


def test_simulate_winner_not_in_ladder_is_structural_skip():
    outs = [_member("E1-N", 0.20, 200, 299)]
    entry = _entry(outs)
    settlement = {"winner_ticker": "E1-MISSING"}
    assert q.simulate_event_queue("E1", entry, settlement,
                                  _full_depth(["E1-N"]), _full_candle(["E1-N"])) is None


def test_simulate_skips_nonpositive_horizon():
    outs = [_member("E1-W", 0.30, 100, 199)]
    entry = _entry(outs, captured_at="2026-07-11T01:00:00+00:00")  # zero horizon
    assert q.simulate_event_queue("E1", entry, {"winner_ticker": "E1-W"},
                                  _full_depth(["E1-W"]), _full_candle(["E1-W"])) is None


def test_winner_payout_not_conditioned_away_when_measurable_and_filled_settle():
    # gate #2 discipline: a measurable + filled winner ALWAYS books the $1 payout, even though
    # dropping it would look better. Here winner fills -> payout must be exactly 1.0.
    outs = [_member("E1-W", 0.55, 100, 199)]
    entry = _entry(outs)
    row = q.simulate_event_queue("E1", entry, {"winner_ticker": "E1-W"},
                                 _full_depth(["E1-W"]), _full_candle(["E1-W"]))
    assert row["winner_measurable"] and row["winner_filled"]
    assert row["payout"] == 1.0
    from scripts.s14_ladder_fillsim import member_premium
    assert row["pnl"] == pytest.approx(member_premium(0.55) - 1.0)


# --------------------------------------------------------------------------- #
# pnl_by_event — bootstrap unit = event-hour, measurable rows only
# --------------------------------------------------------------------------- #
def test_pnl_by_event_one_value_per_measurable_event_hour():
    rows = [
        {"event_ticker": "E1", "pnl": -0.7, "winner_measurable": True},
        {"event_ticker": "E2", "pnl": 0.1, "winner_measurable": True},
        {"event_ticker": "E3", "pnl": 0.0, "winner_measurable": False},  # dropped
    ]
    blocks = q.pnl_by_event(rows)
    assert blocks == {"E1": [-0.7], "E2": [0.1]}
    from core.bootstrap import block_bootstrap
    boot = block_bootstrap(blocks, n_boot=200)
    assert boot["n_units"] == 2
