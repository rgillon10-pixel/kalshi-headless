"""Offline unit tests for the Q30/S29 soccer draw-aversion maker fill-sim — synthetic
fixtures, NO network, NO live tape. Pins the load-bearing -TIE draw-leg detection, series
discovery, queue-aware fill-sim (imported from Q27), draw P&L, the catastrophic no-draw leg,
the fill-conditional NO-draw rate (binding gate 2), the gate-4 power-floor calc, the L52
scalar-filter, per-game grouping (L6), and the <10-games DEAD-by-adequacy verdict branch."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from core.pricing import MAKER_FEE_RATE, fee_per_contract
from scripts import q30_draw_aversion_maker_probe as q30


# --------------------------------------------------------------------------- #
# -TIE draw-leg identification (the self-disambiguating discriminator)
# --------------------------------------------------------------------------- #
def test_is_tie_ticker_true_only_for_trailing_TIE():
    assert q30.is_tie_ticker("KXMLSGAME-26JUL12ABCDEF-TIE") is True
    assert q30.is_tie_ticker("KXUCLGAME-26JUL12X-TIE") is True


def test_is_tie_ticker_false_for_team_legs_and_baseball():
    # team-outcome legs and draw-less sports carry no -TIE
    assert q30.is_tie_ticker("KXMLSGAME-26JUL12ABCDEF-LAG") is False
    assert q30.is_tie_ticker("KXKBOGAME-26JUL12ABCDEF-ABC") is False
    assert q30.is_tie_ticker("") is False
    assert q30.is_tie_ticker(None) is False


def test_is_tie_ticker_not_substring_false_positive():
    # a team code merely CONTAINING the letters TIE must not false-positive (last-segment check)
    assert q30.is_tie_ticker("KXMLSGAME-26JUL12ABC-TIEBREAKER") is False
    assert q30.is_tie_ticker("KXMLSGAME-26JUL12TIE-LAG") is False


def test_series_of_and_event_ticker_of_imported():
    mt = "KXMLSGAME-26JUL12ABCDEF-TIE"
    assert q30.series_of(mt) == "KXMLSGAME"
    assert q30.event_ticker_of(mt) == "KXMLSGAME-26JUL12ABCDEF"


# --------------------------------------------------------------------------- #
# Series discovery — read off the tape, not hardcoded (L7 spirit)
# --------------------------------------------------------------------------- #
def _depth_line(ticker, captured_at, yes_bids, best_yes_bid, best_yes_ask=None):
    return json.dumps({
        "ticker": ticker, "captured_at": captured_at,
        "yes_bids": yes_bids, "no_bids": [],
        "best_yes_bid": best_yes_bid,
        "best_yes_ask": best_yes_ask if best_yes_ask is not None else best_yes_bid,
        "schema_version": "orderbook_depth.v1",
    })


def _write_depth(tmp_path: Path, lines) -> str:
    d = tmp_path / "orderbook_depth"
    d.mkdir()
    (d / "dt=2026-07-12.jsonl").write_text("\n".join(lines) + "\n")
    return str(d / "dt=*.jsonl")


def test_discover_tie_series_reads_only_tie_families(tmp_path):
    lines = [
        _depth_line("KXMLSGAME-26JUL12AAA-TIE", "2026-07-12T09:00:00Z", [[0.25, 100.0]], 0.25),
        _depth_line("KXMLSGAME-26JUL12AAA-LAG", "2026-07-12T09:00:00Z", [[0.40, 100.0]], 0.40),
        _depth_line("KXUCLGAME-26JUL12BBB-TIE", "2026-07-12T09:00:00Z", [[0.30, 100.0]], 0.30),
        _depth_line("KXKBOGAME-26JUL12CCC-ABC", "2026-07-12T09:00:00Z", [[0.55, 100.0]], 0.55),
    ]
    glob = _write_depth(tmp_path, lines)
    assert q30.discover_tie_series(glob) == ("KXMLSGAME", "KXUCLGAME")


# --------------------------------------------------------------------------- #
# Fee sourced from core.pricing (never hand-rolled, L18/L30) — flat $0.01 interior
# --------------------------------------------------------------------------- #
def test_maker_fee_is_core_pricing_flat_one_cent():
    for p in (0.18, 0.22, 0.25, 0.33):
        assert q30.maker_fee(p) == fee_per_contract(p, MAKER_FEE_RATE)
        assert q30.maker_fee(p) == 0.01  # flat interior (L30)


# --------------------------------------------------------------------------- #
# Draw P&L — the no-draw catastrophic leg is included, never dropped (gate 2/G2/L41)
# --------------------------------------------------------------------------- #
def test_draw_pnl_draw_leg():
    # buy draw-YES at 0.22, match DRAWS -> 1 - 0.22 - 0.01 = +0.77
    assert q30.draw_pnl(0.22, True) == pytest.approx(1.0 - 0.22 - 0.01)


def test_draw_pnl_no_draw_leg_is_catastrophic_and_present():
    # match DECIDES -> 0 - 0.22 - 0.01 = -0.23 (the catastrophic no-draw leg fully modeled)
    assert q30.draw_pnl(0.22, False) == pytest.approx(-0.22 - 0.01)
    assert q30.draw_pnl(0.22, False) < 0


# --------------------------------------------------------------------------- #
# Power-floor calc (gate 4) — sqrt(p(1-p)/n), the ±$1 settlement-leg floor
# --------------------------------------------------------------------------- #
def test_power_floor_matches_stated_values():
    # milestone's stated floors: ~$0.09 at n≈24, ~$0.044 at n≈100 (p=0.25)
    assert q30.power_floor_halfwidth(24, 0.25) == pytest.approx(0.0884, abs=5e-4)
    assert q30.power_floor_halfwidth(100, 0.25) == pytest.approx(0.0433, abs=5e-4)


def test_power_floor_formula_and_edge_cases():
    assert q30.power_floor_halfwidth(16, 0.25) == pytest.approx(math.sqrt(0.1875 / 16))
    assert q30.power_floor_halfwidth(0) is None
    assert q30.power_floor_halfwidth(-3) is None


# --------------------------------------------------------------------------- #
# Queue-aware fill (L39, imported from Q27) — cleared fills; frozen is a NO-FILL (L32/L48)
# --------------------------------------------------------------------------- #
def _snap(captured_at, yes_bids):
    return {"record": {"yes_bids": yes_bids}, "captured_at": captured_at}


def test_simulate_fill_cleared_queue_fills():
    snaps = [_snap(1, [[0.22, 500.0]]), _snap(2, [[0.22, 200.0]]), _snap(3, [[0.22, 0.0]])]
    assert q30.simulate_fill(snaps, 0.22, 500.0) is True


def test_simulate_fill_frozen_queue_never_fills():
    snaps = [_snap(1, [[0.22, 500.0]]), _snap(2, [[0.22, 500.0]]), _snap(3, [[0.22, 500.0]])]
    assert q30.simulate_fill(snaps, 0.22, 500.0) is False
    assert q30.simulate_fill(snaps, 0.22, 0.0) is False


def test_bid_size_at_or_above_is_float_not_int_coerced():
    yes_bids = [[0.23, 1500.5], [0.22, 100.25], [0.19, 9.0]]
    assert q30.bid_size_at_or_above(yes_bids, 0.22) == pytest.approx(1600.75)


# --------------------------------------------------------------------------- #
# Scalar-result filtering (L52) — scalar/void rows never enter the trade population
# --------------------------------------------------------------------------- #
def test_scalar_result_is_dropped_L52(tmp_path):
    close = "2026-07-12T12:00:00Z"
    mt = "KXMLSGAME-26JUL12SCA-TIE"
    lines = [_depth_line(mt, "2026-07-12T09:00:00Z", [[0.22, 100.0]], 0.22)]
    glob = _write_depth(tmp_path, lines)
    settlement = {mt: {"result": "scalar", "close_time": close,
                       "event_ticker": "KXMLSGAME-26JUL12SCA", "series": "KXMLSGAME"}}
    per_market, funnel = q30.load_preclose_snapshots(glob, settlement)
    assert per_market == {}
    assert mt in funnel["markets_settled_scalar_dropped_L52"]
    assert mt not in funnel["markets_settled_binary"]


def test_binary_result_kept_preclose_only(tmp_path):
    close = "2026-07-12T12:00:00Z"
    mt = "KXMLSGAME-26JUL12BIN-TIE"
    lines = [
        _depth_line(mt, "2026-07-12T09:00:00Z", [[0.22, 100.0]], 0.22),   # pre-close
        _depth_line(mt, "2026-07-12T13:00:00Z", [[0.22, 100.0]], 0.22),   # post-close excluded
    ]
    glob = _write_depth(tmp_path, lines)
    settlement = {mt: {"result": "yes", "close_time": close,
                       "event_ticker": "KXMLSGAME-26JUL12BIN", "series": "KXMLSGAME"}}
    per_market, _ = q30.load_preclose_snapshots(glob, settlement)
    assert list(per_market.keys()) == [mt]
    assert len(per_market[mt]) == 1


# --------------------------------------------------------------------------- #
# build_draw_trades — every -TIE market rests a bid (NO favorite filter), per-game (L6)
# --------------------------------------------------------------------------- #
def _mk_snap(mt, et, captured_at, ttc, yes_bid, yes_bids, result):
    from datetime import datetime, timezone
    return {
        "record": {"best_yes_ask": (yes_bid + 0.02) if yes_bid is not None else None,
                   "best_yes_bid": yes_bid, "yes_bids": yes_bids},
        "captured_at": datetime.fromisoformat(captured_at).replace(tzinfo=timezone.utc),
        "close_time": None, "ttc_seconds": ttc,
        "event_ticker": et, "series": q30.series_of(mt), "result": result,
    }


def test_build_draw_trades_rests_every_tie_market_no_favorite_filter():
    et = "KXMLSGAME-26JUL12GM"
    tie = et + "-TIE"
    # draw-YES at bid 0.22, match DRAWS -> settles yes; queue 500 clears (500->0) -> filled
    per_market = {
        tie: [
            _mk_snap(tie, et, "2026-07-12T08:00:00", 7200, 0.22, [[0.22, 500.0]], "yes"),
            _mk_snap(tie, et, "2026-07-12T09:00:00", 3600, 0.22, [[0.22, 0.0]], "yes"),
        ],
    }
    trades, funnel = q30.build_draw_trades(per_market)
    assert funnel["n_rested"] == 1
    t = trades[0]
    assert t["market_ticker"] == tie
    assert t["fill_price"] == 0.22
    assert t["queue_ahead"] == pytest.approx(500.0)
    assert t["filled"] is True
    assert t["draw_settles_yes"] is True
    assert t["pnl"] == pytest.approx(1.0 - 0.22 - 0.01)


def test_no_draw_fill_included_in_per_game_pnl_gate2():
    et = "KXMLSGAME-26JUL12LOS"
    tie = et + "-TIE"
    per_market = {
        tie: [
            _mk_snap(tie, et, "2026-07-12T08:00:00", 7200, 0.24, [[0.24, 300.0]], "no"),
            _mk_snap(tie, et, "2026-07-12T09:00:00", 3600, 0.24, [[0.24, 0.0]], "no"),
        ],
    }
    trades, _ = q30.build_draw_trades(per_market)
    pg = q30.per_game_pnl(trades)
    assert et in pg
    assert pg[et][0] == pytest.approx(-0.24 - 0.01)  # catastrophic no-draw leg present
    assert pg[et][0] < 0


def test_no_restable_bid_is_counted_not_traded():
    et = "KXMLSGAME-26JUL12NOB"
    tie = et + "-TIE"
    per_market = {tie: [_mk_snap(tie, et, "2026-07-12T08:00:00", 7200, None, [], "yes")]}
    trades, funnel = q30.build_draw_trades(per_market)
    assert funnel["n_no_restable_bid"] == 1
    assert trades == []


# --------------------------------------------------------------------------- #
# End-to-end run — the <10-games DEAD-by-adequacy branch (verdict-branching coverage)
# --------------------------------------------------------------------------- #
def test_run_dead_by_adequacy_when_few_games(tmp_path):
    close = "2026-07-12T12:00:00Z"
    mt = "KXMLSGAME-26JUL12AAA-TIE"
    lines = [_depth_line(mt, "2026-07-12T09:00:00Z", [[0.22, 100.0]], 0.22)]
    glob = _write_depth(tmp_path, lines)
    cache = tmp_path / "settlement.json"
    cache.write_text(json.dumps({"markets": {
        mt: {"result": "yes", "close_time": close,
             "event_ticker": "KXMLSGAME-26JUL12AAA", "series": "KXMLSGAME"}}}))
    rep = q30.run(cache_path=cache, depth_glob=glob, n_boot=200)
    assert rep["verdict"] == "DEAD-by-adequacy"
    assert rep["distinct_joinable_games"] == 1


def test_fill_conditional_no_draw_rate_reported(tmp_path):
    # two games, both draw bids fill; one draws (yes), one decides (no) -> no-draw rate 0.5.
    # <10 games so verdict is adequacy, but the fill block still reports the gate-2 number.
    lines = []
    settlement = {}
    for i, res in enumerate(("yes", "no")):
        et = f"KXMLSGAME-26JUL12G{i}"
        mt = et + "-TIE"
        lines.append(_depth_line(mt, "2026-07-12T08:00:00Z", [[0.22, 100.0]], 0.22))
        lines.append(_depth_line(mt, "2026-07-12T09:00:00Z", [[0.22, 0.0]], 0.22))
        settlement[mt] = {"result": res, "close_time": "2026-07-12T12:00:00Z",
                          "event_ticker": et, "series": "KXMLSGAME"}
    glob = _write_depth(tmp_path, lines)
    per_market, _ = q30.load_preclose_snapshots(glob, settlement)
    trades, _ = q30.build_draw_trades(per_market)
    fills = [t for t in trades if t["filled"]]
    assert len(fills) == 2
    n_no_draw = sum(1 for t in fills if not t["draw_settles_yes"])
    assert n_no_draw / len(fills) == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# Robustness cut (_bootstrap_cut) — same gate outputs on a subset (L31/L48/L53)
# --------------------------------------------------------------------------- #
def test_bootstrap_cut_empty_is_zero_games():
    out = q30._bootstrap_cut([], n_boot=100)
    assert out["n_fills"] == 0 and out["n_games"] == 0


def test_bootstrap_cut_reports_gate_fields_and_no_draw_rate():
    # 3 fills across 3 games: 1 draw, 2 no-draw -> no-draw rate 2/3; edge fields present.
    fills = [
        {"event_ticker": "G1", "fill_price": 0.20, "draw_settles_yes": True,
         "pnl": q30.draw_pnl(0.20, True)},
        {"event_ticker": "G2", "fill_price": 0.20, "draw_settles_yes": False,
         "pnl": q30.draw_pnl(0.20, False)},
        {"event_ticker": "G3", "fill_price": 0.20, "draw_settles_yes": False,
         "pnl": q30.draw_pnl(0.20, False)},
    ]
    out = q30._bootstrap_cut(fills, n_boot=500)
    assert out["n_fills"] == 3 and out["n_games"] == 3
    assert out["fill_conditional_no_draw_rate"] == pytest.approx(2 / 3)
    assert out["net_underpricing_edge"] == pytest.approx(1 / 3 - (0.20 + 0.01))
    assert out["passes_all_gates"] is False  # only 3 games (< MIN_CI_UNITS)


def test_build_draw_trades_records_entry_spread():
    et = "KXMLSGAME-26JUL12SPR"
    tie = et + "-TIE"
    snap = _mk_snap(tie, et, "2026-07-12T08:00:00", 7200, 0.22, [[0.22, 500.0]], "yes")
    snap["record"]["best_yes_ask"] = 0.30  # explicit 8¢ spread
    per_market = {tie: [snap,
                        _mk_snap(tie, et, "2026-07-12T09:00:00", 3600, 0.22, [[0.22, 0.0]], "yes")]}
    trades, _ = q30.build_draw_trades(per_market)
    assert trades[0]["entry_yes_spread"] == pytest.approx(0.08)


def test_load_settlement_for_run_missing_falls_back(tmp_path):
    # a nonexistent q30 cache falls back to the committed q27 cache (Q29-style), TIE-filtered.
    missing = tmp_path / "nope.json"
    settlement, src = q30.load_settlement_for_run(missing)
    # the fallback is the committed q27 cache; every returned market is a -TIE draw leg.
    assert src in ("q27_fallback_cache", "q30_cache")
    assert all(q30.is_tie_ticker(mt) for mt in settlement)
