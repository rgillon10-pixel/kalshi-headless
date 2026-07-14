"""Offline unit tests for the Q27/S23 favorite-underpricing maker fill-sim — synthetic
fixtures, NO network, NO live tape. Pins the load-bearing parsing / favorite-identification /
queue-ahead / fill / catastrophic-leg / scalar-filter / fee-source / bootstrap-by-game logic
and the empty-join <10-games DEAD-by-adequacy path (the tests the milestone spec mandates)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.pricing import MAKER_FEE_RATE, fee_per_contract
from scripts import q27_favorite_underpricing_fillsim as q27


# --------------------------------------------------------------------------- #
# Ticker / time parsing
# --------------------------------------------------------------------------- #
def test_series_and_event_ticker_split():
    mt = "KXKBOGAME-26JUL09ABCDEF-ABC"
    assert q27.series_of(mt) == "KXKBOGAME"
    assert q27.event_ticker_of(mt) == "KXKBOGAME-26JUL09ABCDEF"


def test_event_ticker_of_no_suffix_returns_self():
    assert q27.event_ticker_of("SOLO") == "SOLO"


def test_parse_iso_handles_z_offset_and_none():
    assert q27.parse_iso("2026-07-13T04:00:00Z") is not None
    assert q27.parse_iso(None) is None
    assert q27.parse_iso("") is None
    assert q27.parse_iso("not-a-date") is None


# --------------------------------------------------------------------------- #
# Ladder helpers — sizes are FLOATS (L47), empty is VALID (L23)
# --------------------------------------------------------------------------- #
def test_bid_size_at_or_above_is_float_not_int_coerced():
    yes_bids = [[0.66, 1500.5], [0.65, 100.25], [0.60, 9.0]]
    # at bid 0.65: 1500.5 + 100.25 (0.60 is below) — fractional sizes kept (L47)
    assert q27.bid_size_at_or_above(yes_bids, 0.65) == pytest.approx(1600.75)


def test_bid_size_at_or_above_empty_is_zero():
    assert q27.bid_size_at_or_above([], 0.6) == 0.0
    assert q27.bid_size_at_or_above(None, 0.6) == 0.0


def test_bid_size_skips_malformed_level():
    assert q27.bid_size_at_or_above([[0.6, 100.0], [0.6], [None, 5.0], [0.6, None]], 0.6) == 100.0


def test_departures_between_counts_reductions_at_or_above_bid():
    prev = [[0.66, 1000.0], [0.65, 500.0], [0.60, 200.0]]
    now = [[0.66, 700.0], [0.65, 500.0], [0.60, 50.0]]
    # at bid 0.65: 0.66 dropped 300, 0.65 unchanged, 0.60 below the bid -> ignored. dep=300.
    assert q27.departures_between(prev, now, 0.65) == pytest.approx(300.0)


def test_departures_ignores_new_bids_jumping_ahead_generous():
    # a NEW level appears / a level grows: ignored (generous fill model, L48).
    prev = [[0.65, 500.0]]
    now = [[0.67, 999.0], [0.65, 500.0]]
    assert q27.departures_between(prev, now, 0.65) == 0.0


# --------------------------------------------------------------------------- #
# Favorite identification — normalized fair ≥ 0.65 via core.pricing (Hard Rule #3)
# --------------------------------------------------------------------------- #
def test_favorite_normalized_fair_uses_bracket_sum_not_raw_ask():
    # two-team game: favorite ask 0.68, dog ask 0.36 -> bracket 1.04, normalized 0.6538 ≥ 0.65
    fav = q27.favorite_normalized_fair(0.68, [0.68, 0.36])
    assert fav == pytest.approx(0.68 / 1.04)
    assert fav >= q27.FAVORITE_MIN_FAIR
    # the raw ask 0.68 differs from the normalized 0.6538 — proves it is NOT the raw ask
    assert fav < 0.68


def test_favorite_normalized_fair_dog_is_below_threshold():
    dog = q27.favorite_normalized_fair(0.36, [0.68, 0.36])
    assert dog == pytest.approx(0.36 / 1.04)
    assert dog < q27.FAVORITE_MIN_FAIR


def test_favorite_normalized_fair_missing_or_degenerate_is_none():
    assert q27.favorite_normalized_fair(None, [0.5, 0.5]) is None
    assert q27.favorite_normalized_fair(0.6, [None, None]) is None


# --------------------------------------------------------------------------- #
# Fee sourced from core.pricing (never hand-rolled, L18/L30) — flat $0.01 interior
# --------------------------------------------------------------------------- #
def test_maker_fee_is_core_pricing_flat_one_cent():
    for p in (0.55, 0.66, 0.72, 0.80):
        assert q27.maker_fee(p) == fee_per_contract(p, MAKER_FEE_RATE)
        assert q27.maker_fee(p) == 0.01  # flat interior (L30)


# --------------------------------------------------------------------------- #
# P&L — the favorite-LOSES catastrophic leg is included, never dropped (G2/L41)
# --------------------------------------------------------------------------- #
def test_favorite_pnl_win_leg():
    # buy favorite YES at 0.66, favorite WINS -> 1 - 0.66 - 0.01 = +0.33
    assert q27.favorite_pnl(0.66, True) == pytest.approx(1.0 - 0.66 - 0.01)


def test_favorite_pnl_lose_leg_is_catastrophic_and_present():
    # favorite LOSES -> 0 - 0.66 - 0.01 = -0.67 (the catastrophic leg fully modeled, G2)
    assert q27.favorite_pnl(0.66, False) == pytest.approx(-0.66 - 0.01)
    assert q27.favorite_pnl(0.66, False) < -0.6


# --------------------------------------------------------------------------- #
# Queue-aware fill (L39) — cleared queue fills; frozen queue is a NO-FILL (L32/L48)
# --------------------------------------------------------------------------- #
def _snap(captured_at, yes_bids):
    return {"record": {"yes_bids": yes_bids}, "captured_at": captured_at}


def test_simulate_fill_cleared_queue_fills():
    # queue_ahead 500; departures 300 + 300 = 600 ≥ 500 -> filled
    snaps = [
        _snap(1, [[0.65, 500.0]]),
        _snap(2, [[0.65, 200.0]]),
        _snap(3, [[0.65, 0.0]]),  # last of the 200 leaves -> cumulative 500 exactly...
    ]
    # departures: 500->200 = 300, 200->0 = 200 => cumulative 500 ≥ 500 -> filled
    assert q27.simulate_fill(snaps, 0.65, 500.0) is True


def test_simulate_fill_frozen_queue_never_fills():
    # queue never moves (frozen, L32/L48) -> 0 departures -> NO fill even if queue_ahead tiny
    snaps = [_snap(1, [[0.65, 500.0]]), _snap(2, [[0.65, 500.0]]), _snap(3, [[0.65, 500.0]])]
    assert q27.simulate_fill(snaps, 0.65, 500.0) is False
    assert q27.simulate_fill(snaps, 0.65, 0.0) is False  # frozen: no departure -> no fill


def test_simulate_fill_partial_departure_below_queue_no_fill():
    # queue_ahead 1000; only 100 departs -> not cleared -> no fill
    snaps = [_snap(1, [[0.65, 1000.0]]), _snap(2, [[0.65, 900.0]])]
    assert q27.simulate_fill(snaps, 0.65, 1000.0) is False


# --------------------------------------------------------------------------- #
# Scalar-result filtering (L52) — scalar rows never enter the trade population
# --------------------------------------------------------------------------- #
def _depth_line(ticker, captured_at, yes_bids, best_yes_ask, best_yes_bid):
    return json.dumps({
        "ticker": ticker, "captured_at": captured_at,
        "yes_bids": yes_bids, "no_bids": [],
        "best_yes_bid": best_yes_bid, "best_yes_ask": best_yes_ask,
        "schema_version": "orderbook_depth.v1",
    })


def _write_depth(tmp_path: Path, lines) -> str:
    d = tmp_path / "orderbook_depth"
    d.mkdir()
    (d / "dt=2026-07-13.jsonl").write_text("\n".join(lines) + "\n")
    return str(d / "dt=*.jsonl")


def test_scalar_result_is_dropped_L52(tmp_path):
    close = "2026-07-13T12:00:00Z"
    mt = "KXKBOGAME-26JUL13SCA-SCA"
    lines = [_depth_line(mt, "2026-07-13T09:00:00Z", [[0.66, 100.0]], 0.68, 0.66)]
    glob = _write_depth(tmp_path, lines)
    settlement = {mt: {"result": "scalar", "close_time": close,
                       "event_ticker": "KXKBOGAME-26JUL13SCA", "series": "KXKBOGAME"}}
    per_market, funnel = q27.load_preclose_snapshots(glob, settlement)
    assert per_market == {}
    assert mt in funnel["markets_settled_scalar"]
    assert mt not in funnel["markets_settled_binary"]


def test_binary_result_is_kept_preclose_only(tmp_path):
    close = "2026-07-13T12:00:00Z"
    mt = "KXKBOGAME-26JUL13BIN-BIN"
    lines = [
        _depth_line(mt, "2026-07-13T09:00:00Z", [[0.66, 100.0]], 0.68, 0.66),   # pre-close
        _depth_line(mt, "2026-07-13T13:00:00Z", [[0.66, 100.0]], 0.68, 0.66),   # post-close: excluded
    ]
    glob = _write_depth(tmp_path, lines)
    settlement = {mt: {"result": "yes", "close_time": close,
                       "event_ticker": "KXKBOGAME-26JUL13BIN", "series": "KXKBOGAME"}}
    per_market, funnel = q27.load_preclose_snapshots(glob, settlement)
    assert list(per_market.keys()) == [mt]
    assert len(per_market[mt]) == 1  # only the pre-close snapshot


# --------------------------------------------------------------------------- #
# build_favorite_trades — favorite rested, dog ignored, per-game grouping (L6)
# --------------------------------------------------------------------------- #
def _mk_snap(mt, et, captured_at, ttc, yes_ask, yes_bid, yes_bids, result):
    from datetime import datetime, timezone
    return {
        "record": {"best_yes_ask": yes_ask, "best_yes_bid": yes_bid, "yes_bids": yes_bids},
        "captured_at": datetime.fromisoformat(captured_at).replace(tzinfo=timezone.utc),
        "close_time": None, "ttc_seconds": ttc,
        "event_ticker": et, "series": "KXKBOGAME", "result": result,
    }


def test_build_favorite_trades_identifies_and_rests_only_favorite():
    et = "KXKBOGAME-26JUL13GM"
    fav, dog = et + "-FAV", et + "-DOG"
    # favorite ask 0.68 (normalized 0.6538 ≥ 0.65), dog 0.36; favorite settles YES.
    per_market = {
        fav: [
            _mk_snap(fav, et, "2026-07-13T08:00:00", 7200, 0.68, 0.66, [[0.66, 500.0]], "yes"),
            _mk_snap(fav, et, "2026-07-13T09:00:00", 3600, 0.68, 0.66, [[0.66, 0.0]], "yes"),
        ],
        dog: [
            _mk_snap(dog, et, "2026-07-13T08:00:00", 7200, 0.36, 0.34, [[0.34, 500.0]], "no"),
        ],
    }
    trades, funnel = q27.build_favorite_trades(per_market)
    assert funnel["n_favorite_markets"] == 1
    assert [t["market_ticker"] for t in trades] == [fav]
    t = trades[0]
    assert t["fill_price"] == 0.66
    assert t["queue_ahead"] == pytest.approx(500.0)
    assert t["filled"] is True          # 500 departed (500->0) clears queue_ahead 500
    assert t["favorite_settles_yes"] is True
    assert t["pnl"] == pytest.approx(1.0 - 0.66 - 0.01)
    assert t["normalized_fair"] == pytest.approx(0.68 / 1.04)


def test_favorite_loses_fill_included_in_per_game_pnl_G2():
    et = "KXKBOGAME-26JUL13LOS"
    fav = et + "-FAV"
    per_market = {
        fav: [
            _mk_snap(fav, et, "2026-07-13T08:00:00", 7200, 0.70, 0.68, [[0.68, 300.0]], "no"),
            _mk_snap(fav, et, "2026-07-13T09:00:00", 3600, 0.70, 0.68, [[0.68, 0.0]], "no"),
        ],
        et + "-DOG": [
            _mk_snap(et + "-DOG", et, "2026-07-13T08:00:00", 7200, 0.34, 0.32,
                     [[0.32, 10.0]], "yes"),
        ],
    }
    trades, _ = q27.build_favorite_trades(per_market)
    pg = q27.per_game_pnl(trades)
    # the favorite LOST -> its filled leg is a catastrophic negative, present in the game unit
    assert et in pg
    assert pg[et][0] == pytest.approx(-0.68 - 0.01)
    assert pg[et][0] < 0


def test_favorite_with_no_restable_bid_is_counted_not_traded():
    et = "KXKBOGAME-26JUL13NOB"
    fav = et + "-FAV"
    per_market = {
        fav: [_mk_snap(fav, et, "2026-07-13T08:00:00", 7200, 0.70, None, [], "yes")],
        et + "-DOG": [_mk_snap(et + "-DOG", et, "2026-07-13T08:00:00", 7200, 0.32, 0.30,
                               [[0.30, 5.0]], "no")],
    }
    trades, funnel = q27.build_favorite_trades(per_market)
    assert funnel["n_favorite_markets"] == 1
    assert funnel["n_favorite_no_restable_bid"] == 1
    assert trades == []


# --------------------------------------------------------------------------- #
# End-to-end run — the empty-join <10-games DEAD-by-adequacy path (G4 / spec-mandated)
# --------------------------------------------------------------------------- #
def test_run_dead_by_adequacy_when_few_games(tmp_path):
    close = "2026-07-13T12:00:00Z"
    mt = "KXKBOGAME-26JUL13AAA-AAA"
    lines = [_depth_line(mt, "2026-07-13T09:00:00Z", [[0.66, 100.0]], 0.68, 0.66)]
    glob = _write_depth(tmp_path, lines)
    cache = tmp_path / "settlement.json"
    cache.write_text(json.dumps({"markets": {
        mt: {"result": "yes", "close_time": close,
             "event_ticker": "KXKBOGAME-26JUL13AAA", "series": "KXKBOGAME"}}}))
    rep = q27.run(cache_path=cache, depth_glob=glob, n_boot=200)
    assert rep["verdict"] == "DEAD-by-adequacy"
    assert rep["distinct_joinable_games"] == 1


def test_load_settlement_cache_missing_file_is_empty(tmp_path):
    assert q27.load_settlement_cache(tmp_path / "nope.json") == {}
