"""scripts.s14_ladder_fillsim — S14 ladder overround underwriting fill-sim (LOOP-QUEUE.md
Q13). Offline: no network — every candlestick fill is injected. Synthetic fixtures only."""
from __future__ import annotations

import json

import pytest

from scripts import s14_ladder_fillsim as sim
from core.pricing import MAKER_FEE_RATE, TAKER_FEE_RATE, fee_per_contract


# --------------------------------------------------------------------------- #
# L30 fee annihilation — a 1c-floor member nets exactly $0
# --------------------------------------------------------------------------- #
def test_member_premium_at_1c_floor_nets_zero():
    # ask 0.01 minus the flat 0.01 maker fee == 0.00
    assert sim.member_premium(0.01) == pytest.approx(0.0)


def test_member_premium_uses_maker_not_taker_fee():
    # at 0.50 the maker fee is 0.01 (flat), taker fee is 0.02 — must use maker
    assert sim.member_premium(0.50) == pytest.approx(0.50 - fee_per_contract(0.50, rate=MAKER_FEE_RATE))
    assert sim.member_premium(0.50) != pytest.approx(0.50 - fee_per_contract(0.50, rate=TAKER_FEE_RATE))


def test_member_premium_flat_fee_across_interior_prices():
    # L30: the maker fee is a flat 1c at every interior price -> premium == ask - 0.01
    for ask in (0.02, 0.10, 0.37, 0.63, 0.90, 0.99):
        assert sim.member_premium(ask) == pytest.approx(ask - 0.01)


def test_frac_overround_on_1c_floor():
    outs = [
        {"yes_ask": 0.01}, {"yes_ask": 0.01}, {"yes_ask": 0.01},  # 0.03 on floor
        {"yes_ask": 0.50}, {"yes_ask": 0.47},                     # 0.97 near money
    ]
    # bracket_sum 1.00; floor sum 0.03
    assert sim.frac_overround_on_1c_floor(outs) == pytest.approx(0.03)


# --------------------------------------------------------------------------- #
# fill detection — seller mirror (max high >= ask AND volume > 0)
# --------------------------------------------------------------------------- #
def test_summarize_candles_max_high_and_volume():
    candles = [
        {"volume_fp": "10", "price": {"high_dollars": "0.20"}},
        {"volume_fp": "5", "price": {"high_dollars": "0.55"}},
        {"volume_fp": "0", "price": {}},
    ]
    s = sim.summarize_candles(candles)
    assert s["max_high_dollars"] == pytest.approx(0.55)
    assert s["total_volume"] == pytest.approx(15.0)
    assert s["n_candles"] == 3


def test_detect_seller_fill_true_when_trade_crosses_up():
    s = {"max_high_dollars": 0.55, "total_volume": 5.0}
    assert sim.detect_seller_fill(s, ask=0.40) is True


def test_detect_seller_fill_false_when_high_never_reaches_ask():
    s = {"max_high_dollars": 0.30, "total_volume": 5.0}
    assert sim.detect_seller_fill(s, ask=0.40) is False


def test_detect_seller_fill_false_with_zero_volume_even_if_high_ge_ask():
    # a printed high with no volume is not a real trade into the resting offer
    s = {"max_high_dollars": 0.90, "total_volume": 0.0}
    assert sim.detect_seller_fill(s, ask=0.40) is False


def test_detect_seller_fill_boundary_exact_match_fills():
    s = {"max_high_dollars": 0.40, "total_volume": 1.0}
    assert sim.detect_seller_fill(s, ask=0.40) is True


def test_detect_seller_fill_no_trade_data_is_not_filled():
    assert sim.detect_seller_fill({"max_high_dollars": None, "total_volume": 0.0}, ask=0.01) is False


# --------------------------------------------------------------------------- #
# settlement + earliest-capture joins
# --------------------------------------------------------------------------- #
def test_build_settlement_map_joins_by_prior_event_ticker_one_yes():
    records = [
        {"previous_settlement": {
            "event_ticker": "KXBTC-26JUL1220",
            "results": {"KXBTC-26JUL1220-A": "no", "KXBTC-26JUL1220-B": "yes",
                        "KXBTC-26JUL1220-C": "no"},
            "expiration_value": 55123.0, "price_source_tag": "broker_truth"}},
    ]
    m = sim.build_settlement_map(records)
    assert m["KXBTC-26JUL1220"]["winner_ticker"] == "KXBTC-26JUL1220-B"
    assert m["KXBTC-26JUL1220"]["expiration_value"] == 55123.0


def test_build_settlement_map_rejects_non_mece_settlement():
    records = [{"previous_settlement": {"event_ticker": "E", "results": {"a": "yes", "b": "yes"}}}]
    assert sim.build_settlement_map(records) == {}


def test_build_earliest_captures_keeps_earliest_and_skips_null_current():
    records = [
        {"captured_at": "2026-07-13T00:40:00+00:00", "series": "KXBTC",
         "current": {"event_ticker": "E1", "close_time": "2026-07-13T01:00:00Z",
                     "outcomes": [{"ticker": "E1-A", "yes_ask": 0.5}]}},
        {"captured_at": "2026-07-13T00:20:00+00:00", "series": "KXBTC",
         "current": {"event_ticker": "E1", "close_time": "2026-07-13T01:00:00Z",
                     "outcomes": [{"ticker": "E1-A", "yes_ask": 0.4}]}},
        {"captured_at": "2026-07-13T00:22:00+00:00", "current": None},  # L15 null hour
    ]
    e = sim.build_earliest_captures(records)
    assert set(e) == {"E1"}
    assert e["E1"]["captured_at"] == "2026-07-13T00:20:00+00:00"  # earliest wins


# --------------------------------------------------------------------------- #
# simulate_event — winner payout, floor skipping, premium math
# --------------------------------------------------------------------------- #
def _entry(outcomes, captured_at="2026-07-13T00:00:00+00:00",
           close_time="2026-07-13T01:00:00Z"):
    return {"captured_at": captured_at, "series": "KXBTC",
            "current": {"event_ticker": "E1", "close_time": close_time,
                        "outcomes": outcomes}}


def test_simulate_event_winner_filled_pays_one_dollar():
    outs = [
        {"ticker": "E1-W", "yes_ask": 0.30, "strike_type": "between",
         "floor_strike": 100, "cap_strike": 199},   # winner, priced
        {"ticker": "E1-N", "yes_ask": 0.20, "strike_type": "between",
         "floor_strike": 200, "cap_strike": 299},   # near, priced
        {"ticker": "E1-F", "yes_ask": 0.01, "strike_type": "between",
         "floor_strike": 900, "cap_strike": 999},   # 1c wing, skipped
    ]
    entry = _entry(outs)
    settlement = {"winner_ticker": "E1-W"}

    def fill_all(series, ticker, ask, s, e):
        return True  # everyone fills

    row = sim.simulate_event("E1", entry, settlement, fill_all)
    # premium from W and N (wing skipped, contributes $0); minus $1 payout for filled winner
    expected_prem = sim.member_premium(0.30) + sim.member_premium(0.20)
    assert row["premium_collected"] == pytest.approx(expected_prem)
    assert row["winner_filled"] is True
    assert row["payout"] == 1.0
    assert row["pnl"] == pytest.approx(expected_prem - 1.0)
    assert row["n_priced_relevant"] == 2  # the 1c wing was not fetched


def test_simulate_event_winner_unfilled_no_payout():
    outs = [
        {"ticker": "E1-W", "yes_ask": 0.05, "strike_type": "between",
         "floor_strike": 100, "cap_strike": 199},
        {"ticker": "E1-N", "yes_ask": 0.20, "strike_type": "between",
         "floor_strike": 200, "cap_strike": 299},
    ]
    entry = _entry(outs)
    settlement = {"winner_ticker": "E1-W"}

    def fill_only_near(series, ticker, ask, s, e):
        return ticker == "E1-N"

    row = sim.simulate_event("E1", entry, settlement, fill_only_near)
    assert row["winner_filled"] is False
    assert row["payout"] == 0.0
    assert row["pnl"] == pytest.approx(sim.member_premium(0.20))


def test_simulate_event_complete_fill_equals_overround_minus_fees():
    # every member priced >= 0.02 and all fill -> pnl == bracket_sum - n*fee - 1
    outs = [
        {"ticker": "E1-W", "yes_ask": 0.40, "strike_type": "between",
         "floor_strike": 100, "cap_strike": 199},
        {"ticker": "E1-B", "yes_ask": 0.35, "strike_type": "between",
         "floor_strike": 200, "cap_strike": 299},
        {"ticker": "E1-C", "yes_ask": 0.30, "strike_type": "between",
         "floor_strike": 300, "cap_strike": 399},
    ]
    entry = _entry(outs)
    settlement = {"winner_ticker": "E1-W"}
    row = sim.simulate_event("E1", entry, settlement, lambda *a: True)
    bsum = 0.40 + 0.35 + 0.30
    fees = 3 * fee_per_contract(0.40, rate=MAKER_FEE_RATE)  # flat 0.01 each
    assert row["pnl"] == pytest.approx(bsum - fees - 1.0)
    assert row["overround"] == pytest.approx(bsum - 1.0)


def test_simulate_event_skips_when_horizon_nonpositive():
    outs = [{"ticker": "E1-W", "yes_ask": 0.40}]
    entry = _entry(outs, captured_at="2026-07-13T01:00:00+00:00",
                   close_time="2026-07-13T01:00:00Z")  # zero horizon
    assert sim.simulate_event("E1", entry, {"winner_ticker": "E1-W"}, lambda *a: True) is None


# --------------------------------------------------------------------------- #
# bootstrap unit = event-hour
# --------------------------------------------------------------------------- #
def test_pnl_by_event_one_value_per_event_hour():
    rows = [{"event_ticker": "E1", "pnl": -0.9}, {"event_ticker": "E2", "pnl": 0.1}]
    blocks = sim.pnl_by_event(rows)
    assert blocks == {"E1": [-0.9], "E2": [0.1]}
    # block_bootstrap over this maps units 1:1 to event-hours
    from core.bootstrap import block_bootstrap
    boot = block_bootstrap(blocks, n_boot=200)
    assert boot["n_units"] == 2


# --------------------------------------------------------------------------- #
# adverse-selection classification — wing vs near-money vs winner
# --------------------------------------------------------------------------- #
def test_classify_members_uses_ladder_spacing_not_hardcoded_width():
    # uniform $100-spaced between ladder -> infer_strike_spacing == 100; winner at 500-599
    # (coord 549.5), near band = within 3*100 = 300 of the winner coord.
    outs = [{"ticker": f"T-{f}", "strike_type": "between", "floor_strike": f,
             "cap_strike": f + 99} for f in range(100, 1001, 100)]
    bins = sim.classify_members(outs, "T-500", nearmoney_steps=3)
    assert bins["T-500"] == "winner"
    assert bins["T-600"] == "near_money"   # coord 100 away, within 300
    assert bins["T-800"] == "near_money"   # coord 300 away, on the band edge
    assert bins["T-900"] == "wing"          # coord 400 away, beyond 300
    assert bins["T-100"] == "wing"          # coord 400 away


def test_full_ladder_fill_rates_winner_fills_wings_do_not():
    outs = [
        {"ticker": "T-W", "yes_ask": 0.60, "strike_type": "between",
         "floor_strike": 500, "cap_strike": 599},
        {"ticker": "T-N", "yes_ask": 0.20, "strike_type": "between",
         "floor_strike": 600, "cap_strike": 699},
        {"ticker": "T-WING1", "yes_ask": 0.01, "strike_type": "between",
         "floor_strike": 1000, "cap_strike": 1099},
        {"ticker": "T-WING2", "yes_ask": 0.01, "strike_type": "between",
         "floor_strike": 1100, "cap_strike": 1199},
    ]
    entry = {"captured_at": "2026-07-13T00:00:00+00:00", "series": "KXBTC",
             "current": {"event_ticker": "E1", "close_time": "2026-07-13T01:00:00Z",
                         "outcomes": outs}}
    settlement = {"winner_ticker": "T-W"}

    def fill_winner_and_near(series, ticker, ask, s, e):
        return ticker in ("T-W", "T-N")  # winner + near fill, wings never

    ladder = sim.full_ladder_fill_rates([("E1", entry, settlement)], fill_winner_and_near,
                                        nearmoney_steps=3)
    assert ladder["fill_rates"]["winner"] == pytest.approx(1.0)
    assert ladder["fill_rates"]["near_money"] == pytest.approx(1.0)
    assert ladder["fill_rates"]["wing"] == pytest.approx(0.0)
    assert ladder["complete_fill_rate"] == pytest.approx(0.0)  # wings unfilled -> not complete


# --------------------------------------------------------------------------- #
# cache — loaded once, resumable, tagged real_ask, no raw candles persisted
# --------------------------------------------------------------------------- #
def test_get_or_fetch_candle_summary_caches_and_tags(tmp_path):
    calls = []

    def fake_fetcher(series, ticker, start_ts, end_ts):
        calls.append(ticker)
        return {"candles": [{"volume_fp": "3", "price": {"high_dollars": "0.30"}}],
                "raw_sha256": "deadbeef"}

    cache_dir = tmp_path / "cache"
    cache = sim.load_candle_summary_cache(cache_dir)
    r1 = sim.get_or_fetch_candle_summary("TK-A", "KXBTC", 100, 200, cache=cache,
                                         cache_dir=cache_dir, fetcher=fake_fetcher)
    assert len(calls) == 1
    assert r1["max_high_dollars"] == pytest.approx(0.30)
    assert r1["price_source_tag"] == "real_ask"

    r2 = sim.get_or_fetch_candle_summary("TK-A", "KXBTC", 100, 200, cache=cache,
                                         cache_dir=cache_dir, fetcher=fake_fetcher)
    assert len(calls) == 1  # in-memory hit, no refetch
    assert r2 == r1

    files = list(cache_dir.glob("dt=*.jsonl"))
    assert len(files) == 1
    rec = json.loads(files[0].read_text().splitlines()[0])
    assert rec["ticker"] == "TK-A"
    assert "candles" not in rec  # trimmed to the summary only
