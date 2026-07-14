"""Offline unit tests for the Q26/S22 OFI depth-imbalance probe — synthetic fixtures, no
network, no live tape. Pins the load-bearing parsing/signal/pnl/gate logic."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import q26_ofi_depth_imbalance_probe as q26


# --------------------------------------------------------------------------- #
# Ticker / time parsing
# --------------------------------------------------------------------------- #
def test_series_and_event_ticker_split():
    mt = "KXKBOGAME-26JUL09ABCDEF-ABC"
    assert q26.series_of(mt) == "KXKBOGAME"
    assert q26.event_ticker_of(mt) == "KXKBOGAME-26JUL09ABCDEF"


def test_event_ticker_of_no_outcome_suffix_returns_self():
    # Defensive: a ticker without a trailing '-<code>' returns itself, never crashes.
    assert q26.event_ticker_of("SOLO") == "SOLO"


def test_parse_iso_handles_z_and_offset_and_none():
    a = q26.parse_iso("2026-07-13T00:23:53.576703+00:00")
    b = q26.parse_iso("2026-07-13T04:00:00Z")
    assert a.tzinfo is not None and b.tzinfo is not None
    assert b == datetime(2026, 7, 13, 4, 0, 0, tzinfo=timezone.utc)
    assert q26.parse_iso(None) is None
    assert q26.parse_iso("") is None
    assert q26.parse_iso("not-a-date") is None


# --------------------------------------------------------------------------- #
# Ladder / imbalance / mid — sizes are FLOATS (L47), one-sided is VALID (L23)
# --------------------------------------------------------------------------- #
def test_ladder_size_sum_is_float_and_not_int_coerced():
    ladder = [[0.62, 1500.5], [0.61, 1500.25], [0.59, 0.25]]
    assert q26.ladder_size_sum(ladder) == pytest.approx(3001.0)  # fractional sizes kept


def test_ladder_size_sum_empty_is_zero():
    assert q26.ladder_size_sum([]) == 0.0
    assert q26.ladder_size_sum(None) == 0.0


def test_ladder_size_sum_skips_malformed_level():
    assert q26.ladder_size_sum([[0.5, 100.0], [0.4], [0.3, None]]) == 100.0


def test_imbalance_signal_range_and_sign():
    assert q26.imbalance_signal(300.0, 100.0) == pytest.approx(0.5)
    assert q26.imbalance_signal(100.0, 300.0) == pytest.approx(-0.5)
    # One-sided book is valid data at the boundary (L23), not a drop.
    assert q26.imbalance_signal(500.0, 0.0) == 1.0
    assert q26.imbalance_signal(0.0, 500.0) == -1.0


def test_imbalance_signal_both_empty_is_none():
    assert q26.imbalance_signal(0.0, 0.0) is None


def test_mid_yes_and_missing_side():
    assert q26.mid_yes(0.62, 0.66) == pytest.approx(0.64)
    assert q26.mid_yes(None, 0.66) is None
    assert q26.mid_yes(0.62, None) is None


def test_side_helpers_and_no_signal_at_boundary():
    assert q26.side_of_imbalance(0.3) == "yes"
    assert q26.side_of_imbalance(-0.3) == "no"
    assert q26.side_of_imbalance(0.0) is None
    assert q26.side_of_imbalance(None) is None
    assert q26.side_of_mid(0.64) == "yes"
    assert q26.side_of_mid(0.36) == "no"
    assert q26.side_of_mid(0.5) is None
    assert q26.side_of_mid(None) is None


# --------------------------------------------------------------------------- #
# Taker-lift P&L — fee from core.pricing, $1.00 mirror excluded (L26)
# --------------------------------------------------------------------------- #
def test_taker_lift_pnl_yes_win_and_loss():
    # buy YES at 0.60, fee = ceil(0.07*0.6*0.4*100)/100 = ceil(1.68)/100 = 0.02
    win = q26.taker_lift_pnl("yes", 1, 0.60, 0.44)
    lose = q26.taker_lift_pnl("yes", 0, 0.60, 0.44)
    assert win == pytest.approx(1.0 - 0.60 - 0.02)
    assert lose == pytest.approx(0.0 - 0.60 - 0.02)


def test_taker_lift_pnl_no_side_uses_no_ask_and_no_outcome():
    # favored NO, settled NO (settled_yes=0) -> payoff 1 at best_no_ask
    pnl = q26.taker_lift_pnl("no", 0, 0.66, 0.40)
    fee = q26.fee_per_contract(0.40, q26.TAKER_FEE_RATE)
    assert pnl == pytest.approx(1.0 - 0.40 - fee)


def test_taker_lift_pnl_excludes_dollar_mirror_and_missing_ask():
    assert q26.taker_lift_pnl("yes", 1, 1.0, 0.5) is None   # $1.00 mirror, no room (L26)
    assert q26.taker_lift_pnl("no", 0, 0.5, None) is None    # missing ask
    assert q26.taker_lift_pnl("yes", 1, 0.0, 0.5) is None    # nonsensical 0 ask


# --------------------------------------------------------------------------- #
# Snapshot join — last pre-close (ttc>0), settlement required
# --------------------------------------------------------------------------- #
def _depth_line(ticker, captured_at, yes_bids, no_bids, byb=0.6, bya=0.64, bnb=0.36, bna=0.4):
    return json.dumps({
        "ticker": ticker, "captured_at": captured_at,
        "yes_bids": yes_bids, "no_bids": no_bids,
        "best_yes_bid": byb, "best_yes_ask": bya,
        "best_no_bid": bnb, "best_no_ask": bna,
        "schema_version": "orderbook_depth.v1",
    })


def _write_depth(tmp_path: Path, lines) -> str:
    d = tmp_path / "orderbook_depth"
    d.mkdir()
    (d / "dt=2026-07-13.jsonl").write_text("\n".join(lines) + "\n")
    return str(d / "dt=*.jsonl")


def test_load_last_preclose_picks_latest_before_close_and_requires_settlement(tmp_path):
    close = "2026-07-13T10:00:00Z"
    mt = "KXKBOGAME-26JUL13AAA-AAA"
    lines = [
        _depth_line(mt, "2026-07-13T08:00:00Z", [[0.6, 100.0]], [[0.4, 50.0]]),
        _depth_line(mt, "2026-07-13T09:30:00Z", [[0.6, 200.0]], [[0.4, 50.0]]),  # latest pre-close
        _depth_line(mt, "2026-07-13T10:30:00Z", [[0.6, 999.0]], [[0.4, 50.0]]),  # post-close: excluded
        # an unsettled ticker present in depth but NOT in the settlement map
        _depth_line("KXKBOGAME-26JUL13ZZZ-ZZZ", "2026-07-13T09:00:00Z", [[0.6, 1.0]], [[0.4, 1.0]]),
    ]
    glob = _write_depth(tmp_path, lines)
    settlement = {mt: {"result": "yes", "close_time": close,
                       "event_ticker": "KXKBOGAME-26JUL13AAA", "series": "KXKBOGAME"}}
    best, funnel = q26.load_last_preclose_snapshots(glob, settlement)
    assert set(funnel["markets_in_depth"]) == {mt, "KXKBOGAME-26JUL13ZZZ-ZZZ"}
    assert set(funnel["markets_settled_joined"]) == {mt}
    assert set(best.keys()) == {mt}
    # picked the 09:30 snapshot (latest with ttc>0), ttc = 30 min
    assert best[mt]["ttc_seconds"] == pytest.approx(1800.0)
    assert q26.ladder_size_sum(best[mt]["record"]["yes_bids"]) == 200.0


def test_load_last_preclose_drops_market_with_no_preclose_snapshot(tmp_path):
    close = "2026-07-13T10:00:00Z"
    mt = "KXKBOGAME-26JUL13BBB-BBB"
    # only a post-close capture exists -> no valid pre-close snapshot
    lines = [_depth_line(mt, "2026-07-13T11:00:00Z", [[0.6, 100.0]], [[0.4, 50.0]])]
    glob = _write_depth(tmp_path, lines)
    settlement = {mt: {"result": "no", "close_time": close,
                       "event_ticker": "KXKBOGAME-26JUL13BBB", "series": "KXKBOGAME"}}
    best, funnel = q26.load_last_preclose_snapshots(glob, settlement)
    assert set(funnel["markets_settled_joined"]) == {mt}
    assert best == {}


def test_non_target_series_ignored(tmp_path):
    lines = [_depth_line("KXBTC-26JUL0621-B", "2026-07-13T09:00:00Z", [[0.6, 100.0]], [[0.4, 50.0]])]
    glob = _write_depth(tmp_path, lines)
    best, funnel = q26.load_last_preclose_snapshots(glob, {})
    assert funnel["markets_in_depth"] == set()
    assert best == {}


# --------------------------------------------------------------------------- #
# Gate 2 calibration — disagreement subset is the decisive test
# --------------------------------------------------------------------------- #
def _row(event, imb, mid, settled_yes, bya=0.64, bna=0.4):
    return {
        "market_ticker": event + "-X", "event_ticker": event, "series": "KXTEST",
        "ttc_seconds": 1800.0, "yes_bid_size": 0.0, "no_bid_size": 0.0,
        "imbalance": imb, "imb_side": q26.side_of_imbalance(imb),
        "mid_yes": mid, "mid_side": q26.side_of_mid(mid),
        "settled_yes": settled_yes, "best_yes_ask": bya, "best_no_ask": bna,
    }


def test_gate2_disagreement_subset_isolated():
    rows = [
        # agree (both YES), correct — should NOT be in disagreement subset
        _row("G1", 0.5, 0.7, 1),
        # disagree: imbalance says YES, mid says NO; settles YES -> imbalance right
        _row("G2", 0.5, 0.3, 1),
        # disagree: imbalance says NO, mid says YES; settles YES -> imbalance wrong
        _row("G3", -0.5, 0.7, 1),
    ]
    cal = q26.gate2_calibration(rows)
    assert cal["disagree_n"] == 2
    assert cal["disagree_games"] == 2
    # on the 2 disagreement rows imbalance is right once -> 0.5
    assert cal["disagree_imb_hit_rate"] == pytest.approx(0.5)
    assert cal["disagree_mid_hit_rate"] == pytest.approx(0.5)


def test_gate2_brier_prefers_confident_correct_signal():
    rows = [_row("G1", 0.8, 0.55, 1)]  # imbalance very confident YES, correct
    cal = q26.gate2_calibration(rows)
    # p_imb = 0.9, p_mid = 0.55; both against y=1 -> imbalance lower brier
    assert cal["brier_all_imb"] < cal["brier_all_mid"]


# --------------------------------------------------------------------------- #
# Gate 3 P&L grouping + exclusion
# --------------------------------------------------------------------------- #
def test_gate3_groups_by_game_and_excludes_unfillable():
    rows = [
        _row("G1", 0.5, 0.3, 1, bya=0.60, bna=0.42),   # favored YES, tradeable
        _row("G1", 0.5, 0.3, 0, bya=0.55, bna=0.47),   # same game, another market
        _row("G2", -0.5, 0.7, 0, bya=0.7, bna=1.0),    # favored NO but no_ask=1.0 -> excluded
    ]
    unit_values, funnel = q26.gate3_pnl(rows)
    assert funnel["n_excluded_no_fillable_ask"] == 1
    assert funnel["n_traded"] == 2
    assert set(unit_values.keys()) == {"G1"}
    assert len(unit_values["G1"]) == 2


# --------------------------------------------------------------------------- #
# End-to-end run — DEAD-by-join short circuit
# --------------------------------------------------------------------------- #
def test_run_dead_by_join_when_few_games(tmp_path):
    close = "2026-07-13T10:00:00Z"
    mt = "KXKBOGAME-26JUL13AAA-AAA"
    lines = [_depth_line(mt, "2026-07-13T09:30:00Z", [[0.6, 200.0]], [[0.4, 50.0]])]
    glob = _write_depth(tmp_path, lines)
    cache = tmp_path / "settlement.json"
    cache.write_text(json.dumps({
        "markets": {mt: {"result": "yes", "close_time": close,
                         "event_ticker": "KXKBOGAME-26JUL13AAA", "series": "KXKBOGAME"}}}))
    rep = q26.run(cache_path=cache, depth_glob=glob)
    assert rep["verdict"] == "DEAD-by-join"
    assert rep["funnel"]["distinct_games_joinable"] == 1


def test_load_settlement_cache_missing_file_is_empty(tmp_path):
    assert q26.load_settlement_cache(tmp_path / "nope.json") == {}
