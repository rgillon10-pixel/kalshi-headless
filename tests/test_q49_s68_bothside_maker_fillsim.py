"""Offline unit tests for the Q49/S68 two-sided both-bid overround-capture maker fill-sim —
synthetic fixtures, NO network, NO live tape. Pins the load-bearing selection gate (genuinely
two-sided + spread >= the two maker fees), the fee source (core.pricing only), the both-fill
P&L symmetry, both queue-aware fill models (including the regression that separates the
GENEROUS turnover rule from the STRICT touch rule), the single-side directional legs, the
bootstrap unit being the GAME-SERIES (not the game), the settlement-ledger conflict/scalar
handling, and every verdict branch of the Q49 kill ladder."""
from __future__ import annotations

import json

import pytest

from core.pricing import MAKER_FEE_RATE, fee_per_contract
from scripts import q49_s68_bothside_maker_fillsim as q49


# --------------------------------------------------------------------------- #
# Ticker / series / time parsing
# --------------------------------------------------------------------------- #
def test_series_and_event_ticker_split():
    mt = "KXKBOGAME-26JUL070530KIALOT-KIA"
    assert q49.series_of(mt) == "KXKBOGAME"
    assert q49.event_ticker_of(mt) == "KXKBOGAME-26JUL070530KIALOT"


def test_event_ticker_of_no_suffix_returns_self():
    assert q49.event_ticker_of("SOLO") == "SOLO"


def test_is_excluded_series_only_kxmve():
    # the S68 note excludes the KXMVE* nominal-wing AMM families (L31), nothing else
    assert q49.is_excluded_series("KXMVESPORTSMULTIGAMEEXTENDED-26JUL07X-A") is True
    assert q49.is_excluded_series("KXMVECROSSCATEGORY-26JUL07X-A") is True
    assert q49.is_excluded_series("KXKBOGAME-26JUL070530KIALOT-KIA") is False
    assert q49.is_excluded_series("KXUECLGAME-26JUL07X-BAR") is False


def test_parse_ts_handles_z_offset_none_and_garbage():
    assert q49.parse_ts("2026-07-13T04:00:00Z") is not None
    assert q49.parse_ts("2026-07-13T04:00:00+00:00") is not None
    assert q49.parse_ts(None) is None
    assert q49.parse_ts("") is None
    assert q49.parse_ts("not-a-date") is None


def test_parse_ts_returns_utc_aware():
    dt = q49.parse_ts("2026-07-13T04:00:00+02:00")
    assert dt.utcoffset().total_seconds() == 0.0
    assert dt.hour == 2


# --------------------------------------------------------------------------- #
# GATE 1 — genuinely two-sided, spread >= the two maker fees
# --------------------------------------------------------------------------- #
def test_gate_rejects_missing_quote():
    assert q49.two_sided_wide_entry(None, 0.6, 0.4)["reason"] == "missing_quote"
    assert q49.two_sided_wide_entry(0.35, None, 0.4)["reason"] == "missing_quote"
    assert q49.two_sided_wide_entry(0.35, 0.6, None)["reason"] == "missing_quote"


def test_gate_rejects_zero_bid_as_absent_order_not_a_zero_price():
    # a 0.0 bid is the ABSENCE of a resting order, never a $0.00 fillable price
    g = q49.two_sided_wide_entry(0.0, 0.6, 0.4)
    assert g["eligible"] is False and g["reason"] == "not_two_sided"
    g = q49.two_sided_wide_entry(0.35, 0.0, 0.4)
    assert g["eligible"] is False and g["reason"] == "not_two_sided"


def test_gate_rejects_spread_below_the_two_maker_fees():
    # a 0.35 bid against a 0.36 offer is a 1c spread, against 2c of maker fees
    g = q49.two_sided_wide_entry(0.35, 0.64, 0.36)
    assert g["eligible"] is False
    assert g["reason"] == "spread_below_two_maker_fees"
    assert g["fee_total"] == pytest.approx(0.02)


def test_gate_accepts_exactly_two_fee_spread_and_reports_capture():
    g = q49.two_sided_wide_entry(0.35, 0.63, 0.37)
    assert g["eligible"] is True
    assert g["spread"] == pytest.approx(0.02)
    assert g["fee_yes"] == pytest.approx(0.01)
    assert g["fee_no"] == pytest.approx(0.01)
    # gross capture is computed from the two REAL bids, not assumed equal to the spread
    assert g["gross_capture"] == pytest.approx(1.0 - 0.35 - 0.63)


def test_gate_capture_measured_not_assumed_when_mirror_identity_breaks():
    # an incoherent snapshot (yes_ask != 1 - no_bid) must NOT silently reuse the spread
    g = q49.two_sided_wide_entry(0.35, 0.70, 0.45)
    assert g["spread"] == pytest.approx(0.10)
    assert g["gross_capture"] == pytest.approx(-0.05)


# --------------------------------------------------------------------------- #
# Fees come from core.pricing ONLY (L18/L30) — flat $0.01 maker fee interior
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("p", [0.05, 0.2, 0.35, 0.5, 0.63, 0.9, 0.99])
def test_maker_fee_matches_core_pricing_at_maker_rate(p):
    assert q49.maker_fee(p) == fee_per_contract(p, rate=MAKER_FEE_RATE)


def test_maker_fee_is_flat_penny_in_the_interior():
    assert q49.maker_fee(0.35) == pytest.approx(0.01)
    assert q49.maker_fee(0.5) == pytest.approx(0.01)


# --------------------------------------------------------------------------- #
# P&L — both-fill symmetry (gate 4) and the single-side directional legs
# --------------------------------------------------------------------------- #
def test_both_fill_pnl_is_identical_under_either_settlement():
    a = q49.both_fill_pnl_by_result(0.35, 0.60, "yes")
    b = q49.both_fill_pnl_by_result(0.35, 0.60, "no")
    assert a == pytest.approx(b)


def test_both_fill_pnl_formula_net_of_both_maker_fees():
    p_yes, p_no = 0.35, 0.60
    expected = 1.0 - p_yes - p_no - fee_per_contract(p_yes, rate=MAKER_FEE_RATE) \
        - fee_per_contract(p_no, rate=MAKER_FEE_RATE)
    assert q49.both_fill_pnl(p_yes, p_no) == pytest.approx(expected)
    assert q49.both_fill_pnl(p_yes, p_no) == pytest.approx(0.03)


def test_both_fill_pnl_is_exactly_zero_at_the_two_fee_gate_boundary():
    # a book whose gross capture is exactly the two fees nets exactly $0.00 — the fee wall
    assert q49.both_fill_pnl(0.35, 0.63) == pytest.approx(0.0, abs=1e-12)


def test_both_fill_pnl_rejects_non_binary_result_L52():
    with pytest.raises(ValueError):
        q49.both_fill_pnl_by_result(0.35, 0.60, "scalar")


def test_single_side_pnl_win_and_lose_branches():
    # long YES @0.35, settles YES -> +1 - 0.35 - 0.01
    assert q49.single_side_pnl(0.35, "yes", "yes") == pytest.approx(1.0 - 0.35 - 0.01)
    # long YES @0.35, settles NO -> catastrophic leg, no payout
    assert q49.single_side_pnl(0.35, "yes", "no") == pytest.approx(-0.35 - 0.01)
    # long NO @0.60, settles NO -> +1
    assert q49.single_side_pnl(0.60, "no", "no") == pytest.approx(1.0 - 0.60 - 0.01)
    assert q49.single_side_pnl(0.60, "no", "yes") == pytest.approx(-0.60 - 0.01)


def test_single_side_pnl_rejects_bad_side_and_non_binary_result():
    with pytest.raises(ValueError):
        q49.single_side_pnl(0.35, "maybe", "yes")
    with pytest.raises(ValueError):
        q49.single_side_pnl(0.35, "yes", "scalar")


# --------------------------------------------------------------------------- #
# Ladder helpers — sizes are FLOATS (L47), an empty ladder is VALID (L23)
# --------------------------------------------------------------------------- #
def test_queue_ahead_sums_levels_at_or_above_our_price_as_floats():
    bids = [[0.66, 1500.5], [0.65, 100.25], [0.60, 9.0]]
    assert q49.queue_ahead_at(bids, 0.65) == pytest.approx(1600.75)


def test_queue_ahead_never_int_coerces_a_fractional_size_L47():
    # a real observed KXWCGAME best-level size was 91,316.82 contracts
    assert q49.queue_ahead_at([[0.35, 91316.82]], 0.35) == pytest.approx(91316.82)


def test_queue_ahead_empty_and_malformed_levels():
    assert q49.queue_ahead_at([], 0.6) == 0.0
    assert q49.queue_ahead_at(None, 0.6) == 0.0
    assert q49.queue_ahead_at([[0.6, 100.0], [0.6], [None, 5.0], [0.6, None]], 0.6) == 100.0


def test_departures_between_counts_reductions_at_or_above_our_price():
    prev = [[0.66, 1000.0], [0.65, 500.0], [0.60, 200.0]]
    now = [[0.66, 700.0], [0.65, 500.0], [0.60, 50.0]]
    # 0.66 lost 300; 0.65 flat; 0.60 sits below our bid -> ignored
    assert q49.departures_between(prev, now, 0.65) == pytest.approx(300.0)


def test_departures_between_ignores_new_size_jumping_ahead_generous():
    prev = [[0.65, 100.0]]
    now = [[0.66, 5000.0], [0.65, 100.0]]
    assert q49.departures_between(prev, now, 0.65) == 0.0


def test_size_at_price_is_only_our_own_level():
    bids = [[0.66, 1000.0], [0.65, 250.5], [0.64, 10.0]]
    assert q49.size_at_price(bids, 0.65) == pytest.approx(250.5)
    assert q49.size_at_price([], 0.65) == 0.0


def test_best_bid_of_prefers_the_quoted_field_then_the_ladder():
    bids = [[0.60, 10.0], [0.58, 5.0]]
    assert q49.best_bid_of(bids, 0.61) == pytest.approx(0.61)
    assert q49.best_bid_of(bids, None) == pytest.approx(0.60)
    assert q49.best_bid_of([], None) is None


def test_touch_departures_zero_when_best_bid_moved_above_us():
    prev = [[0.70, 900.0], [0.65, 400.0]]
    now = [[0.70, 100.0], [0.65, 0.0]]
    # best bid 0.70 > our 0.65 -> under price priority we cannot be hit at all
    assert q49.touch_departures_between(prev, now, 0.65, 0.70) == 0.0
    # at the touch, the loss at OUR level counts
    assert q49.touch_departures_between(prev, now, 0.65, 0.65) == pytest.approx(400.0)


# --------------------------------------------------------------------------- #
# The two fill models
# --------------------------------------------------------------------------- #
def _ladders(*levels):
    return list(levels)


def test_turnover_fill_requires_departures_to_clear_the_queue():
    ladders = _ladders([[0.65, 100.0]], [[0.65, 40.0]], [[0.65, 10.0]])
    assert q49.simulate_leg_fill(ladders, 0.65, 90.0)["filled"] is True   # 60+30 = 90
    assert q49.simulate_leg_fill(ladders, 0.65, 200.0)["filled"] is False


def test_frozen_ladder_is_a_no_fill_not_free_income_L32():
    ladders = _ladders([[0.65, 100.0]], [[0.65, 100.0]], [[0.65, 100.0]])
    out = q49.simulate_leg_fill(ladders, 0.65, 0.0)
    assert out["frozen"] is True and out["filled"] is False


def test_touch_model_is_strictly_tighter_than_turnover_regression():
    """The saturation artifact this probe measures: the book migrates AWAY from our stale
    price, so the generous turnover rule books a fill off levels we could never be hit at,
    while the touch rule (our own level, only while at the touch) correctly says no-fill."""
    ladders = _ladders(
        [[0.65, 100.0]],                 # entry: we join behind 100 at 0.65
        [[0.80, 50000.0], [0.65, 100.0]],  # market runs away; a huge level appears above us
        [[0.80, 100.0], [0.65, 100.0]],    # that level churns 49,900 contracts
    )
    best = [0.65, 0.80, 0.80]
    assert q49.simulate_leg_fill(ladders, 0.65, 100.0)["filled"] is True
    strict = q49.simulate_leg_fill_touch(ladders, best, 0.65, 100.0)
    assert strict["filled"] is False
    assert strict["cumulative_departures"] == 0.0


def test_touch_model_fills_when_our_own_level_is_eaten_at_the_touch():
    ladders = _ladders([[0.65, 100.0]], [[0.65, 20.0]], [[0.65, 0.0]])
    best = [0.65, 0.65, 0.65]
    out = q49.simulate_leg_fill_touch(ladders, best, 0.65, 100.0)
    assert out["filled"] is True
    assert out["cumulative_departures"] == pytest.approx(100.0)


def test_touch_model_raises_on_misaligned_best_bid_sequence():
    with pytest.raises(ValueError):
        q49.simulate_leg_fill_touch([[[0.65, 1.0]]], [0.65, 0.65], 0.65, 0.0)


# --------------------------------------------------------------------------- #
# Settlement ledger loading — conflicts dropped, scalars dropped (L52)
# --------------------------------------------------------------------------- #
def _write_settlement(tmp_path, rows):
    fp = tmp_path / "dt=2026-07-17.jsonl"
    with open(fp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return str(tmp_path / "dt=*.jsonl")


def _srow(ticker, result, close="2026-07-08T00:00:00Z"):
    return {"ticker": ticker, "result": result, "close_time": close,
            "event_ticker": q49.event_ticker_of(ticker), "series": q49.series_of(ticker),
            "price_source_tag": "broker_truth"}


def test_load_settlements_keeps_binary_drops_scalar_and_conflicts(tmp_path):
    g = _write_settlement(tmp_path, [
        _srow("KXKBOGAME-26JUL07A-KIA", "yes"),
        _srow("KXKBOGAME-26JUL07A-LOT", "no"),
        _srow("KXKBOGAME-26JUL07A-LOT", "no"),        # duplicate, agreeing -> kept once
        _srow("KXNPBGAME-26JUL07B-YOM", "scalar"),    # L52 non-binary -> dropped
        _srow("KXNPBGAME-26JUL07C-HAN", "yes"),
        _srow("KXNPBGAME-26JUL07C-HAN", "no"),        # conflicting re-capture -> dropped
    ])
    sett, stats = q49.load_settlements(g)
    assert set(sett) == {"KXKBOGAME-26JUL07A-KIA", "KXKBOGAME-26JUL07A-LOT"}
    assert sett["KXKBOGAME-26JUL07A-KIA"]["result"] == "yes"
    assert sett["KXKBOGAME-26JUL07A-KIA"]["price_source_tag"] == "broker_truth"
    assert stats["dropped_non_binary"] == 1
    assert stats["dropped_conflicting"] == 1
    assert stats["multi_line_tickers"] == 2


# --------------------------------------------------------------------------- #
# End-to-end over a synthetic in-memory tape (no files, no network)
# --------------------------------------------------------------------------- #
def _snap(ts, yes_bid, no_bid, yes_offer, yes_bids, no_bids, close="2026-07-10T00:00:00Z"):
    return {"record": {"ticker": "T", "captured_at": ts, "best_yes_bid": yes_bid,
                       "best_no_bid": no_bid, "best_yes_ask": yes_offer,
                       "yes_bids": yes_bids, "no_bids": no_bids},
            "captured_at": q49.parse_ts(ts), "close_time": q49.parse_ts(close),
            "ttc_hours": 5.0}


def _double_fill_ticker(ticker, result, series=None, ttc=5.0):
    """A two-snapshot ticker whose BOTH ladders are fully eaten at the touch -> double fill."""
    snaps = [
        _snap("2026-07-09T19:00:00Z", 0.35, 0.60, 0.40, [[0.35, 10.0]], [[0.60, 10.0]]),
        _snap("2026-07-09T20:00:00Z", 0.35, 0.60, 0.40, [[0.35, 0.0]], [[0.60, 0.0]]),
    ]
    for s in snaps:
        s["record"]["ticker"] = ticker
        s["ttc_hours"] = ttc
    sett = {"result": result, "close_time": "2026-07-10T00:00:00Z",
            "event_ticker": q49.event_ticker_of(ticker),
            "series": series or q49.series_of(ticker), "price_source_tag": "broker_truth"}
    return snaps, sett


def test_build_trades_double_fill_row_carries_tags_and_pnl():
    snaps, s = _double_fill_ticker("KXKBOGAME-26JUL07A-KIA", "no")
    trades, funnel = q49.build_trades({"KXKBOGAME-26JUL07A-KIA": snaps},
                                      {"KXKBOGAME-26JUL07A-KIA": s})
    assert funnel["candidates"] == 1
    t = trades[0]
    assert t["series"] == "KXKBOGAME"
    assert t["price_source_tag"].startswith("real_bid")
    assert "broker_truth" in t["price_source_tag"]
    for model in q49.FILL_MODELS:
        m = t["models"][model]
        assert m["fill_category"] == "both"
        assert m["pnl_both_fill"] == pytest.approx(1.0 - 0.35 - 0.60 - 0.02)


def test_build_trades_skips_narrow_and_one_sided_and_single_snapshot():
    narrow, s_narrow = _double_fill_ticker("KXKBOGAME-26JUL07B-AAA", "yes")
    for sn in narrow:                        # 1c spread -> below the two maker fees
        sn["record"]["best_yes_ask"] = 0.36
    one_sided, s_one = _double_fill_ticker("KXKBOGAME-26JUL07C-BBB", "yes")
    for sn in one_sided:                     # no resting NO bid -> not genuinely two-sided
        sn["record"]["best_no_bid"] = 0.0
    single, s_single = _double_fill_ticker("KXKBOGAME-26JUL07D-CCC", "yes")
    single = single[:1]                      # only one snapshot -> unmeasurable, not a fill
    per_ticker = {"KXKBOGAME-26JUL07B-AAA": narrow, "KXKBOGAME-26JUL07C-BBB": one_sided,
                  "KXKBOGAME-26JUL07D-CCC": single}
    sett = {"KXKBOGAME-26JUL07B-AAA": s_narrow, "KXKBOGAME-26JUL07C-BBB": s_one,
            "KXKBOGAME-26JUL07D-CCC": s_single}
    trades, funnel = q49.build_trades(per_ticker, sett)
    assert trades == []
    assert funnel["entry_spread_below_two_fees"] == 1
    assert funnel["entry_not_two_sided"] == 1
    assert funnel["entry_single_snapshot"] == 1


def test_single_side_fill_never_enters_the_both_fill_pnl():
    snaps, s = _double_fill_ticker("KXKBOGAME-26JUL07E-DDD", "no")
    snaps[1]["record"]["no_bids"] = [[0.60, 10.0]]   # NO ladder frozen -> only YES fills
    trades, _ = q49.build_trades({"KXKBOGAME-26JUL07E-DDD": snaps},
                                 {"KXKBOGAME-26JUL07E-DDD": s})
    m = trades[0]["models"]["touch"]
    assert m["fill_category"] == "yes_only"
    assert m["pnl_both_fill"] is None                 # excluded from the capture population
    # it IS the directional position we are left holding (settles NO -> the YES leg loses)
    assert m["pnl_strategy_level"] == pytest.approx(-0.35 - 0.01)


# --------------------------------------------------------------------------- #
# Bootstrap unit = GAME-SERIES (L6/L41), not the game
# --------------------------------------------------------------------------- #
def _trade(series, event, pnl_both, pnl_strategy=None, model="touch"):
    return {"series": series, "event_ticker": event,
            "models": {model: {"pnl_both_fill": pnl_both,
                               "pnl_strategy_level": pnl_strategy
                               if pnl_strategy is not None else (pnl_both or 0.0)}}}


def test_per_series_pnl_groups_by_series_not_by_game():
    trades = [_trade("KXKBOGAME", "KXKBOGAME-G1", 0.03),
              _trade("KXKBOGAME", "KXKBOGAME-G2", 0.05),
              _trade("KXNPBGAME", "KXNPBGAME-G1", 0.01)]
    units = q49.per_series_pnl(trades, "pnl_both_fill")
    assert set(units) == {"KXKBOGAME", "KXNPBGAME"}     # 2 units, NOT 3 games
    assert units["KXKBOGAME"] == [0.03, 0.05]


def test_per_series_pnl_drops_none_rather_than_zeroing_it_L86():
    trades = [_trade("KXKBOGAME", "G1", None), _trade("KXKBOGAME", "G2", 0.02)]
    units = q49.per_series_pnl(trades, "pnl_both_fill")
    assert units == {"KXKBOGAME": [0.02]}


def test_cut_trades_populations_and_unknown_cut():
    t_near_tight = {"fillable_entry_spread": True, "fillable_entry_nearclose": True}
    t_wide_early = {"fillable_entry_spread": False, "fillable_entry_nearclose": False}
    trades = [t_near_tight, t_wide_early]
    assert q49.cut_trades(trades, "unrestricted") == trades
    assert q49.cut_trades(trades, "fillable_entry") == [t_near_tight]
    assert q49.cut_trades(trades, "spread_le_10c") == [t_near_tight]
    assert q49.cut_trades(trades, "nearclose_le_24h") == [t_near_tight]
    with pytest.raises(ValueError):
        q49.cut_trades(trades, "nope")


# --------------------------------------------------------------------------- #
# The verdict ladder (pure function over an analyzed-cut dict)
# --------------------------------------------------------------------------- #
def _cut(n=100, both=50, mean=0.03, ci=(0.02, 0.04), n_units=12, opposing=1,
         clears=True, n_sub_tick=0, n_clears_tick=50):
    return {
        "n_candidates": n,
        "fills": {"both": both, "both_fill_rate": (both / n) if n else None},
        "net_pnl_magnitude": {"n": both, "n_sub_tick": n_sub_tick,
                              "n_clears_tick": n_clears_tick},
        "bootstrap_both_fill_by_series": {
            "mean": mean, "ci95": list(ci), "n_units_series": n_units,
            "admissible": {"admissible": opposing >= 1 and n_units >= q49.MIN_CI_UNITS,
                           "reasons": ([] if (opposing >= 1 and n_units >= q49.MIN_CI_UNITS)
                                       else ["no_opposing_unit"]),
                           "n_units": n_units, "n_opposing_units": opposing},
            "clears_tick_magnitude": clears,
            "ci_lower_positive": ci[0] > 0,
        },
    }


def test_verdict_dead_by_fill_rate_below_the_s19_floor():
    v, why = q49.verdict_for(_cut(n=10000, both=1))
    assert v == "DEAD-by-fill-rate" and "S19" in why


def test_verdict_dead_by_fee_when_realized_overround_is_zero_or_negative():
    v, why = q49.verdict_for(_cut(mean=0.0, ci=(0.0, 0.0), n_sub_tick=50, n_clears_tick=0))
    assert v == "DEAD-by-fee"
    v, _ = q49.verdict_for(_cut(mean=-0.01, ci=(-0.02, -0.001)))
    assert v == "DEAD-by-fee"


def test_verdict_dead_by_adequacy_below_the_ten_series_floor():
    v, why = q49.verdict_for(_cut(n_units=5))
    assert v == "DEAD-by-adequacy" and "GAME-SERIES" in why


def test_verdict_dead_by_ci_on_a_degenerate_all_positive_population_L41():
    v, why = q49.verdict_for(_cut(opposing=0))
    assert v == "DEAD-by-CI" and "inadmissible" in why


def test_verdict_dead_by_ci_when_lower_bound_not_positive():
    v, _ = q49.verdict_for(_cut(mean=0.005, ci=(-0.001, 0.02)))
    assert v == "DEAD-by-CI"


def test_verdict_dead_by_ci_when_it_fails_the_tick_magnitude_gate_L27():
    v, why = q49.verdict_for(_cut(mean=0.0005, ci=(0.0001, 0.001), clears=False))
    assert v == "DEAD-by-CI" and "economic-significance" in why


def test_verdict_alive_only_when_every_gate_passes():
    v, _ = q49.verdict_for(_cut())
    assert v == "ALIVE-PROVISIONAL"


def test_verdict_empty_population_is_adequacy_not_a_ci():
    v, _ = q49.verdict_for(_cut(n=0, both=0))
    assert v == "DEAD-by-adequacy"


# --------------------------------------------------------------------------- #
# analyze_cut wiring (both models, adverse-selection split, L32 dual cut)
# --------------------------------------------------------------------------- #
def test_analyze_cut_reports_both_models_and_adverse_selection_split():
    per_ticker, sett = {}, {}
    for i, (series, result) in enumerate([("KXKBOGAME", "no"), ("KXNPBGAME", "yes")]):
        tk = f"{series}-26JUL0{i}A-XXX"
        snaps, s = _double_fill_ticker(tk, result)
        per_ticker[tk], sett[tk] = snaps, s
    trades, _ = q49.build_trades(per_ticker, sett)
    for model in q49.FILL_MODELS:
        c = q49.analyze_cut(trades, model, n_boot=200)
        assert c["fill_model"] == model
        assert c["n_candidates"] == 2 and c["n_series"] == 2
        assert c["fills"]["both"] == 2
        assert c["adverse_selection"]["settle_yes_rate_double_fills"] == pytest.approx(0.5)
        assert c["bootstrap_both_fill_by_series"]["n_units_series"] == 2
        # all-positive population -> L41 inadmissible (no opposing cluster possible)
        assert c["bootstrap_both_fill_by_series"]["admissible"]["admissible"] is False
        assert c["bootstrap_strategy_level_diagnostic"]["frac_frozen"] == 0.0
