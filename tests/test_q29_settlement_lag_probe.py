"""Offline unit tests for the Q29/S28 post-close settlement-lag probe — synthetic fixtures,
no network, no live tape. Pins the load-bearing lookahead-firewall / fillability-vs-mirror /
winner-side / edge / exclusion logic. Does NOT re-test core.bootstrap (tests/test_bootstrap.py)
or core.pricing.fee_per_contract (tests/test_substrate_primitives.py)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.pricing import TAKER_FEE_RATE, fee_per_contract
from scripts import q29_settlement_lag_probe as q29


# --------------------------------------------------------------------------- #
# ticker-HHMM-as-UTC parser (the tz-ambiguous CONTRAST reading, L46)
# --------------------------------------------------------------------------- #
def test_parse_sports_ticker_hhmm_as_utc_basic():
    dt = q29.parse_sports_ticker_hhmm_as_utc("KXNPBGAME-26JUL110500YOMYOK-YOK")
    assert dt == datetime(2026, 7, 11, 5, 0, 0, tzinfo=timezone.utc)


def test_parse_sports_ticker_hhmm_as_utc_bad_grammar_is_none():
    assert q29.parse_sports_ticker_hhmm_as_utc("KXBTC-26JUL0621-T69300") is None
    assert q29.parse_sports_ticker_hhmm_as_utc("") is None
    assert q29.parse_sports_ticker_hhmm_as_utc("no-dashes-here") is None


def test_parse_sports_ticker_hhmm_as_utc_out_of_range_is_none():
    # 2599 is not a valid HHMM
    assert q29.parse_sports_ticker_hhmm_as_utc("KXMLBGAME-26JUL112599ABCDEF-ABC") is None


# --------------------------------------------------------------------------- #
# gate 1 — coarse / date-only close exclusion
# --------------------------------------------------------------------------- #
def test_is_coarse_close_time_2359_clamp():
    assert q29.is_coarse_close_time(datetime(2026, 7, 11, 23, 59, 0, tzinfo=timezone.utc))
    assert q29.is_coarse_close_time(datetime(2026, 7, 11, 23, 59, 59, tzinfo=timezone.utc))


def test_is_coarse_close_time_exact_midnight_clamp():
    assert q29.is_coarse_close_time(datetime(2026, 7, 11, 0, 0, 0, tzinfo=timezone.utc))


def test_is_coarse_close_time_none_is_coarse():
    assert q29.is_coarse_close_time(None)


def test_is_coarse_close_time_real_intraday_is_fine():
    # a genuine hour-resolved game-end close is NOT coarse
    assert not q29.is_coarse_close_time(datetime(2026, 7, 11, 12, 54, 32, tzinfo=timezone.utc))
    assert not q29.is_coarse_close_time(datetime(2026, 7, 11, 0, 0, 30, tzinfo=timezone.utc))


# --------------------------------------------------------------------------- #
# winner-side ask + backing depth (Kalshi bids-only complement)
# --------------------------------------------------------------------------- #
def test_winner_side_yes_uses_yes_ask_and_no_bid_depth():
    rec = {"best_yes_ask": 0.90, "best_no_ask": 0.12,
           "no_bids": [[0.10, 500.0], [0.09, 250.0]], "yes_bids": [[0.88, 30.0]]}
    side, ask, depth = q29.winner_side_ask_depth(1, rec)
    assert side == "yes"
    assert ask == 0.90
    assert depth == pytest.approx(750.0)  # backed by the NO-bid ladder


def test_winner_side_no_uses_no_ask_and_yes_bid_depth():
    rec = {"best_yes_ask": 0.90, "best_no_ask": 0.12,
           "no_bids": [[0.10, 500.0]], "yes_bids": [[0.88, 30.0], [0.87, 20.0]]}
    side, ask, depth = q29.winner_side_ask_depth(0, rec)
    assert side == "no"
    assert ask == 0.12
    assert depth == pytest.approx(50.0)  # backed by the YES-bid ladder


def test_winner_side_empty_book_zero_depth_and_none_ask():
    rec = {"best_yes_ask": None, "best_no_ask": None, "no_bids": [], "yes_bids": []}
    side, ask, depth = q29.winner_side_ask_depth(1, rec)
    assert side == "yes" and ask is None and depth == 0.0


# --------------------------------------------------------------------------- #
# gate 2 — fillability vs mirror artifact / empty book
# --------------------------------------------------------------------------- #
def test_is_fillable_true_when_sub_dollar_ask_with_backing_depth():
    assert q29.is_fillable_winner(0.90, 750.0)
    assert q29.is_fillable_winner(0.01, 1.0)


def test_is_fillable_false_for_dollar_mirror():
    # yes_ask == $1.00 mirror (no resting NO bid) — the S10/L26 non-price
    assert not q29.is_fillable_winner(1.0, 0.0)
    assert not q29.is_fillable_winner(1.0, 100.0)  # >=1.0 is not fillable regardless


def test_is_fillable_false_for_missing_ask_or_no_depth():
    assert not q29.is_fillable_winner(None, 500.0)   # emptied book, no ask
    assert not q29.is_fillable_winner(0.90, 0.0)     # ask present but no backing size
    assert not q29.is_fillable_winner(0.0, 500.0)    # non-positive ask


# --------------------------------------------------------------------------- #
# edge net of taker fee — winner settles to $1 (broker_truth)
# --------------------------------------------------------------------------- #
def test_settlement_lag_edge_matches_hand_math():
    ask = 0.90
    expected = 1.0 - ask - fee_per_contract(ask, TAKER_FEE_RATE)
    assert q29.settlement_lag_edge(ask) == pytest.approx(expected)
    # at 0.90: fee = ceil(0.07*0.90*0.10*100)/100 = ceil(0.63)/100 = 0.01 -> edge 0.09
    assert q29.settlement_lag_edge(0.90) == pytest.approx(0.09)


def test_settlement_lag_edge_thin_room_at_099():
    # ask 0.99 leaves 1c gross; fee ceil(0.07*0.99*0.01*100)/100 = ceil(0.0693)=0.01 -> edge 0.00
    assert q29.settlement_lag_edge(0.99) == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# scan + verdict integration on synthetic fixtures (no network)
# --------------------------------------------------------------------------- #
def _depth_line(**rec) -> str:
    import json
    return json.dumps(rec)


def _write_depth(tmp_path, records):
    fp = tmp_path / "dt=2026-07-11.jsonl"
    with open(fp, "w") as f:
        for r in records:
            f.write(_depth_line(**r) + "\n")
    return str(tmp_path / "dt=*.jsonl")


def test_scan_excludes_scalar_and_coarse_and_marks_fillable(tmp_path):
    settlement = {
        "KXMLBGAME-26JUL110530AAABBB-AAA": {  # yes/no, hour-resolved, retained
            "result": "yes", "close_time": "2026-07-11T12:00:00Z",
            "event_ticker": "KXMLBGAME-26JUL110530AAABBB", "retention_available": True},
        "KXMLBGAME-26JUL110530CCCDDD-CCC": {  # scalar -> excluded (L52)
            "result": "scalar", "close_time": "2026-07-11T12:00:00Z",
            "event_ticker": "KXMLBGAME-26JUL110530CCCDDD", "retention_available": True},
        "KXMLBGAME-26JUL110530EEEFFF-EEE": {  # coarse 23:59 close -> excluded (gate 1)
            "result": "no", "close_time": "2026-07-11T23:59:59Z",
            "event_ticker": "KXMLBGAME-26JUL110530EEEFFF", "retention_available": True},
    }
    glob = _write_depth(tmp_path, [
        # a fillable post-close capture for the good market (winner=YES at 0.90, NO-bid depth)
        {"ticker": "KXMLBGAME-26JUL110530AAABBB-AAA", "captured_at": "2026-07-11T12:05:00Z",
         "best_yes_ask": 0.90, "best_no_ask": 0.12,
         "no_bids": [[0.10, 500.0]], "yes_bids": [[0.88, 10.0]]},
        {"ticker": "KXMLBGAME-26JUL110530CCCDDD-CCC", "captured_at": "2026-07-11T12:05:00Z",
         "best_yes_ask": 0.90, "best_no_ask": 0.12, "no_bids": [[0.1, 5.0]], "yes_bids": []},
        {"ticker": "KXMLBGAME-26JUL110530EEEFFF-EEE", "captured_at": "2026-07-11T12:05:00Z",
         "best_yes_ask": 0.90, "best_no_ask": 0.12, "no_bids": [], "yes_bids": [[0.1, 5.0]]},
    ])
    rows, funnel = q29.scan_captures(glob, settlement)
    assert len(rows) == 1                      # scalar + coarse dropped
    assert rows[0]["fillable"] is True
    assert rows[0]["winner_side"] == "yes"
    assert len(funnel["markets_excluded_coarse_close"]) == 1


def test_scan_excludes_not_retained(tmp_path):
    settlement = {
        "KXMLBGAME-26JUL110530AAABBB-AAA": {
            "result": "yes", "close_time": "2026-07-11T12:00:00Z",
            "event_ticker": "KXMLBGAME-26JUL110530AAABBB", "retention_available": False},
    }
    glob = _write_depth(tmp_path, [
        {"ticker": "KXMLBGAME-26JUL110530AAABBB-AAA", "captured_at": "2026-07-11T12:05:00Z",
         "best_yes_ask": 0.90, "best_no_ask": 0.12, "no_bids": [[0.10, 5.0]], "yes_bids": []},
    ])
    rows, funnel = q29.scan_captures(glob, settlement)
    assert rows == []
    assert len(funnel["markets_excluded_not_retained"]) == 1


def test_run_verdict_dead_by_convergence_on_empty_books(tmp_path):
    """The real-tape shape: genuinely post-close captures exist but all have emptied books ->
    zero fillable winner asks -> DEAD-by-convergence, gate 4 N/A."""
    settlement = {
        f"KXMLBGAME-26JUL11{i:02d}30AAABB{i}-AAA": {
            "result": "yes", "close_time": "2026-07-11T12:00:00Z",
            "event_ticker": f"KXMLBGAME-26JUL11{i:02d}30AAABB{i}",
            "retention_available": True}
        for i in range(3)
    }
    recs = [
        {"ticker": f"KXMLBGAME-26JUL11{i:02d}30AAABB{i}-AAA",
         "captured_at": "2026-07-11T12:05:00Z",
         "best_yes_ask": None, "best_no_ask": None, "no_bids": [], "yes_bids": []}
        for i in range(3)
    ]
    glob = _write_depth(tmp_path, recs)
    # scan against the synthetic settlement directly (run() would load a cache from disk).
    rows, _ = q29.scan_captures(glob, settlement)
    assert all(not r["fillable"] for r in rows)
    assert len([r for r in rows if r["hours_past_settlement_close"] >= 0]) == 3


def test_run_verdict_alive_when_fillable_edge_clears(tmp_path):
    """A synthetic ALIVE world: >=10 lookahead-clean fillable games, mostly a cheap winner ask
    (big edge) PLUS one adverse-fill game (winner ask 0.995 -> strictly-negative edge) so the
    by-GAME bootstrap has an opposing-sign cluster and is L41-ADMISSIBLE -> the probe must report
    ALIVE-PROVISIONAL. Proves the gates don't always kill; the real-tape DEAD is data-driven, not
    hardcoded. (Note: on the real mechanism such an opposing cluster cannot arise — the ex-post
    winner always pays $1 — so the live settlement-lag edge is L41-degenerate by construction;
    that is moot here only because the fillable population is empty on the real tape anyway.)"""
    settlement = {}
    recs = []
    # capture 20h past a 12:00 close => lookahead-clean (>19h margin)
    for i in range(12):
        mt = f"KXMLBGAME-26JUL11{i:02d}05AAAB{i:02d}-AAA"
        ev = f"KXMLBGAME-26JUL11{i:02d}05AAAB{i:02d}"
        settlement[mt] = {"result": "yes", "close_time": "2026-07-11T12:00:00Z",
                          "event_ticker": ev, "retention_available": True}
        ask = 0.995 if i == 0 else 0.60   # one adverse-fill game -> opposing cluster
        recs.append({"ticker": mt, "captured_at": "2026-07-12T08:00:00Z",
                     "best_yes_ask": ask, "best_no_ask": round(1 - ask + 0.02, 3),
                     "no_bids": [[round(1 - ask, 3), 500.0]], "yes_bids": [[0.58, 10.0]]})
    glob = _write_depth(tmp_path, recs)
    # point run() at a written cache
    import json
    cache = tmp_path / "settlement.json"
    cache.write_text(json.dumps({"schema_version": "q29_settlement_cache.v1",
                                 "markets": settlement}))
    rep = q29.run(cache_path=cache, depth_glob=glob)
    assert rep["verdict"] == "ALIVE-PROVISIONAL"
    assert rep["gate4_bootstrap"]["clears"] is True
