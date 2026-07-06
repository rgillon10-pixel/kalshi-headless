"""scripts.s13_maker_fillsim — S13 maker-side fill-sim (LOOP-QUEUE.md Q9). Offline: no
network, candlestick fetch is always injected."""
from __future__ import annotations

import json

import pytest

from scripts import s13_maker_fillsim as sim


# --------------------------------------------------------------------------- #
# bid_price_for
# --------------------------------------------------------------------------- #
def test_bid_price_for_subtracts_one_cent():
    assert sim.bid_price_for(0.50) == pytest.approx(0.49)


def test_bid_price_for_clamps_to_tradeable_range():
    assert sim.bid_price_for(0.005) == pytest.approx(0.01)
    assert sim.bid_price_for(0.999) == pytest.approx(0.99)


# --------------------------------------------------------------------------- #
# devig_fair_probs (open vs close leg, shared logic)
# --------------------------------------------------------------------------- #
def test_devig_fair_probs_open_and_close_legs_independent():
    ml = {"home_open": -150, "away_open": 130, "home_close": -200, "away_close": 170}
    fair_open = sim.devig_fair_probs(ml, "open")
    fair_close = sim.devig_fair_probs(ml, "close")
    assert set(fair_open) == {"home", "away"}
    assert fair_open != fair_close
    assert fair_open["home"] + fair_open["away"] == pytest.approx(1.0)
    assert fair_close["home"] + fair_close["away"] == pytest.approx(1.0)


def test_devig_fair_probs_handles_draw_leg():
    ml = {"home_close": -120, "away_close": 300, "draw_close": 250}
    fair = sim.devig_fair_probs(ml, "close")
    assert set(fair) == {"home", "away", "draw"}
    assert sum(fair.values()) == pytest.approx(1.0)


def test_devig_fair_probs_missing_leg_is_none_not_fabricated():
    ml = {"home_close": -120, "away_close": 300}  # no *_open at all
    assert sim.devig_fair_probs(ml, "open") is None
    assert sim.devig_fair_probs({}, "close") is None
    assert sim.devig_fair_probs(None, "close") is None


# --------------------------------------------------------------------------- #
# summarize_min_low / detect_fill
# --------------------------------------------------------------------------- #
def test_summarize_min_low_picks_the_lowest_trade_and_its_timestamp():
    candles = [
        {"end_period_ts": 100, "price": {"low_dollars": "0.20"}},
        {"end_period_ts": 200, "price": {"low_dollars": "0.05"}},
        {"end_period_ts": 300, "price": {"low_dollars": "0.30"}},
    ]
    summary = sim.summarize_min_low(candles)
    assert summary["min_low_dollars"] == pytest.approx(0.05)
    assert summary["min_low_end_period_ts"] == 200
    assert summary["n_candles"] == 3


def test_summarize_min_low_skips_candles_with_no_trade_data():
    candles = [{"end_period_ts": 100, "price": {}}, {"end_period_ts": 200, "price": None}]
    summary = sim.summarize_min_low(candles)
    assert summary["min_low_dollars"] is None
    assert summary["min_low_end_period_ts"] is None
    assert summary["n_candles"] == 2


def test_detect_fill_true_when_min_low_trades_through():
    summary = {"min_low_dollars": 0.05, "min_low_end_period_ts": 200}
    filled, fill_ts = sim.detect_fill(summary, bid_price=0.10)
    assert filled is True
    assert fill_ts == 200


def test_detect_fill_false_when_min_low_never_reaches_bid():
    summary = {"min_low_dollars": 0.50, "min_low_end_period_ts": 100}
    filled, fill_ts = sim.detect_fill(summary, bid_price=0.10)
    assert filled is False
    assert fill_ts is None


def test_detect_fill_no_trade_data_is_honest_not_filled():
    filled, fill_ts = sim.detect_fill({"min_low_dollars": None}, bid_price=0.99)
    assert filled is False
    assert fill_ts is None


def test_detect_fill_boundary_exact_match_fills():
    summary = {"min_low_dollars": 0.10, "min_low_end_period_ts": 100}
    filled, _ = sim.detect_fill(summary, bid_price=0.10)
    assert filled is True


# --------------------------------------------------------------------------- #
# kalshi_outcome_windows / espn_moneylines — dedupe-by-latest-capture over tape
# --------------------------------------------------------------------------- #
def test_kalshi_outcome_windows_keeps_latest_capture():
    records = [
        {"schema_version": "sports_history_kalshi.v1", "capture_id": "20260703T000000Z",
         "series": "KXWCGAME",
         "outcomes": [{"ticker": "T-A", "open_time": "2026-07-01T00:00:00Z",
                      "close_time": "2026-07-03T00:00:00Z"}]},
        {"schema_version": "sports_history_kalshi.v1", "capture_id": "20260704T000000Z",
         "series": "KXWCGAME",
         "outcomes": [{"ticker": "T-A", "open_time": "2026-07-01T00:00:01Z",
                      "close_time": "2026-07-04T00:00:00Z"}]},
    ]
    windows = sim.kalshi_outcome_windows(records)
    assert windows["T-A"]["open_time"] == "2026-07-01T00:00:01Z"  # from the newer capture


def test_kalshi_outcome_windows_skips_outcomes_without_open_time():
    records = [{"schema_version": "sports_history_kalshi.v1", "capture_id": "c1",
                "series": "KXWCGAME", "outcomes": [{"ticker": "T-B"}]}]
    assert sim.kalshi_outcome_windows(records) == {}


def test_espn_moneylines_keeps_latest_capture_by_event_id():
    records = [
        {"schema_version": "sports_history_espn.v1", "capture_id": "c1",
         "espn_event_id": "111", "moneyline": {"home_close": -110, "away_close": -110}},
        {"schema_version": "sports_history_espn.v1", "capture_id": "c2",
         "espn_event_id": "111", "moneyline": {"home_close": -120, "away_close": 100}},
    ]
    out = sim.espn_moneylines(records)
    assert out["111"]["home_close"] == -120


# --------------------------------------------------------------------------- #
# get_or_fetch_candle_summary — cache (loaded once per run, not re-read per ticker)
# --------------------------------------------------------------------------- #
def test_get_or_fetch_candle_summary_caches_in_memory_and_skips_refetch(tmp_path):
    calls = []

    def fake_fetcher(series, ticker, start_ts, end_ts):
        calls.append((series, ticker, start_ts, end_ts))
        return {"candles": [{"end_period_ts": 1, "price": {"low_dollars": "0.10"}}],
                "raw_sha256": "abc"}

    cache_dir = tmp_path / "cache"
    cache = sim.load_candle_summary_cache(cache_dir)  # empty dir -> empty cache
    r1 = sim.get_or_fetch_candle_summary("TICK-A", "KXWCGAME", 100, 200,
                                         cache=cache, cache_dir=cache_dir, fetcher=fake_fetcher)
    assert len(calls) == 1
    assert r1["min_low_dollars"] == pytest.approx(0.10)

    r2 = sim.get_or_fetch_candle_summary("TICK-A", "KXWCGAME", 100, 200,
                                         cache=cache, cache_dir=cache_dir, fetcher=fake_fetcher)
    assert len(calls) == 1  # in-memory cache hit, no second fetch
    assert r2 == r1

    # exactly one cache file was written, with the expected tag, no full candle list persisted
    cache_files = list(cache_dir.glob("dt=*.jsonl"))
    assert len(cache_files) == 1
    lines = cache_files[0].read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["ticker"] == "TICK-A"
    assert rec["price_source_tag"] == "real_ask"
    assert "candles" not in rec  # trimmed — only the summary is persisted


def test_load_candle_summary_cache_reads_back_a_prior_run(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    rec = {"schema_version": "sports_maker_fillsim_candle_summary.v1", "ticker": "TICK-B",
           "min_low_dollars": 0.20, "min_low_end_period_ts": 500, "n_candles": 10}
    (cache_dir / "dt=2026-07-04.jsonl").write_text(json.dumps(rec) + "\n")

    cache = sim.load_candle_summary_cache(cache_dir)
    called = []
    result = sim.get_or_fetch_candle_summary(
        "TICK-B", "KXWCGAME", 100, 200, cache=cache, cache_dir=cache_dir,
        fetcher=lambda *a: called.append(a) or {"candles": [], "raw_sha256": "x"})
    assert not called  # cache hit from disk, fetcher never called
    assert result["min_low_dollars"] == pytest.approx(0.20)


# --------------------------------------------------------------------------- #
# simulate_outcomes — end to end over small fake tape
# --------------------------------------------------------------------------- #
def _clv_game(edge_key="ARG", fair_prob=0.83125, fair_key="home"):
    return {
        "schema_version": "sports_clv_join.v1",
        "kalshi_event_ticker": "KXWCGAME-26JUL03ARGCPV", "series": "KXWCGAME",
        "espn_event_id": "760500", "kickoff_ts": "2026-07-03T22:00:00Z",
        "outcomes": [{"ticker": f"KXWCGAME-26JUL03ARGCPV-{edge_key}",
                     "fair_key": fair_key, "fair_prob": fair_prob}],
    }


def test_simulate_outcomes_fill_and_edge_math():
    games = [_clv_game()]
    windows = {"KXWCGAME-26JUL03ARGCPV-ARG": {"open_time": "2026-06-30T12:00:00Z",
                                              "close_time": "2026-07-03T22:05:00Z",
                                              "series": "KXWCGAME"}}
    moneylines = {"760500": {"home_open": -140, "away_open": 120,
                             "home_close": -160, "away_close": 140}}

    def fetcher(series, ticker, start_ts, end_ts):
        return {"min_low_dollars": 0.80, "min_low_end_period_ts": start_ts + 3600, "n_candles": 1}

    rows = sim.simulate_outcomes(games, windows, moneylines, fetcher)
    assert len(rows) == 1
    row = rows[0]
    assert row["bid_price"] == pytest.approx(0.82)  # 0.83125 - 0.01, rounded
    assert row["filled"] is True  # candle low 0.80 <= bid 0.82
    assert row["edge_after_fee_fill_anchor"] == pytest.approx(
        0.83125 - 0.82 - sim.fee_per_contract(0.82, rate=sim.MAKER_FEE_RATE))
    assert "fair_entry" in row and row["fair_entry"] is not None
    assert row["fair_move_entry_to_fill_anchor"] == pytest.approx(
        row["fair_close"] - row["fair_entry"])


def test_simulate_outcomes_uses_maker_not_taker_fee_rate():
    """A resting bid that fills is a MAKER fill (0.0175 rate) — using the taker default
    (0.07, 4x higher) would silently overcharge every simulated fill."""
    games = [_clv_game()]
    windows = {"KXWCGAME-26JUL03ARGCPV-ARG": {"open_time": "2026-06-30T12:00:00Z",
                                              "close_time": "2026-07-03T22:05:00Z",
                                              "series": "KXWCGAME"}}
    moneylines = {}

    def fetcher(series, ticker, start_ts, end_ts):
        return {"min_low_dollars": 0.80, "min_low_end_period_ts": start_ts + 3600, "n_candles": 1}

    rows = sim.simulate_outcomes(games, windows, moneylines, fetcher)
    bid = rows[0]["bid_price"]
    assert rows[0]["fee_per_contract"] == pytest.approx(
        sim.fee_per_contract(bid, rate=sim.MAKER_FEE_RATE))
    assert rows[0]["fee_per_contract"] != pytest.approx(
        sim.fee_per_contract(bid, rate=sim.TAKER_FEE_RATE))


def test_simulate_outcomes_no_fill_skips_edge_fields():
    games = [_clv_game()]
    windows = {"KXWCGAME-26JUL03ARGCPV-ARG": {"open_time": "2026-06-30T12:00:00Z",
                                              "close_time": "2026-07-03T22:05:00Z",
                                              "series": "KXWCGAME"}}
    moneylines = {}

    def fetcher(series, ticker, start_ts, end_ts):
        return {"min_low_dollars": 0.95, "min_low_end_period_ts": start_ts + 3600, "n_candles": 1}

    rows = sim.simulate_outcomes(games, windows, moneylines, fetcher)
    assert rows[0]["filled"] is False
    assert "edge_after_fee_fill_anchor" not in rows[0]
    assert "fair_entry" not in rows[0]


def test_simulate_outcomes_skips_outcomes_missing_window():
    games = [_clv_game()]
    rows = sim.simulate_outcomes(games, windows={}, moneylines={}, candle_fetcher=lambda *a: {})
    assert rows == []


def test_simulate_outcomes_skips_unpriced_outcomes():
    game = _clv_game()
    game["outcomes"][0]["fair_prob"] = None
    rows = sim.simulate_outcomes([game], windows={"x": {}}, moneylines={},
                                 candle_fetcher=lambda *a: {})
    assert rows == []


# --------------------------------------------------------------------------- #
# aggregation helpers
# --------------------------------------------------------------------------- #
def test_fill_rate_and_edge_aggregation_by_game():
    rows = [
        {"kalshi_event_ticker": "G1", "filled": True, "edge_after_fee_fill_anchor": 0.02},
        {"kalshi_event_ticker": "G1", "filled": False},
        {"kalshi_event_ticker": "G2", "filled": True, "edge_after_fee_fill_anchor": -0.01},
    ]
    fills = sim.fill_rate_by_game(rows)
    assert fills["G1"] == [1.0, 0.0]
    assert fills["G2"] == [1.0]
    edges = sim.filled_edges_by_game(rows)
    assert edges["G1"] == [0.02]
    assert edges["G2"] == [-0.01]
