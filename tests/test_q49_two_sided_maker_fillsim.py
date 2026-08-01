"""Offline unit tests for the Q49/S68 two-sided BOTH-BID overround-capture maker fill-sim —
synthetic fixtures, NO network, NO live tape. Pins the load-bearing population gate, the
price-time-priority queue math, the two explicit fill models (including the adverse-selection
price-through condition), the outcome-BLINDNESS of the fill decision, the per-filled-leg maker
fee source, the four exhaustive per-attempt P&L cases (single-leg fills are directional and are
never dropped, G2/L41), and the kill-condition wiring."""
from __future__ import annotations

import inspect
import json

import pytest

from core.pricing import MAKER_FEE_RATE, fee_per_contract
from scripts import q49_two_sided_maker_fillsim as q49


# --------------------------------------------------------------------------- #
# Ticker / time / population helpers
# --------------------------------------------------------------------------- #
def test_series_and_event_ticker_split():
    mt = "KXNPBGAME-26JUL12ABCDEF-XYZ"
    assert q49.series_of(mt) == "KXNPBGAME"
    assert q49.event_ticker_of(mt) == "KXNPBGAME-26JUL12ABCDEF"


def test_event_ticker_of_no_suffix_returns_self():
    assert q49.event_ticker_of("SOLO") == "SOLO"


def test_parse_iso_handles_z_offset_and_bad_input():
    assert q49.parse_iso("2026-07-13T04:00:00Z") is not None
    assert q49.parse_iso(None) is None
    assert q49.parse_iso("") is None
    assert q49.parse_iso("not-a-date") is None


def test_parse_iso_handles_short_fraction_and_bare_z_via_the_sanctioned_helper():
    """L136/L150: a bare-`Z` / short-fractional-second Kalshi timestamp is ~38% of committed
    tape and dies on a raw `datetime.fromisoformat` under the declared Python 3.9 floor."""
    for ts in ("2026-07-20T00:55:15.650957+00:00", "2026-07-22T10:30:13.9Z",
               "2026-07-22T10:30:13Z"):
        got = q49.parse_iso(ts)
        assert got is not None and got.tzinfo is not None
        assert got.utcoffset().total_seconds() == 0


def test_is_game_series_keeps_real_moneylines_and_drops_l31_artifacts():
    assert q49.is_game_series("KXNPBGAME")
    assert q49.is_game_series("KXUECLGAME")
    # L31: the KXMVE multi-game / cross-category families are the nominal-wing artifact
    assert not q49.is_game_series("KXMVESPORTSMULTIGAMEEXTENDED")
    assert not q49.is_game_series("KXMVECROSSCATEGORY")
    # non-game families never enter S68's population
    assert not q49.is_game_series("KXBTCD")
    assert not q49.is_game_series("KXTEMPDCH")


# --------------------------------------------------------------------------- #
# Ladder helpers — sizes are FLOATS (L47), an empty ladder is VALID (L23)
# --------------------------------------------------------------------------- #
def test_bid_price_map_is_float_not_int_coerced():
    m = q49.bid_price_map([[0.66, 1500.5], [0.65, 100.25], [0.60, 9.0]], 0.65)
    assert m == {0.66: 1500.5, 0.65: 100.25}
    assert isinstance(m[0.66], float)


def test_bid_price_map_empty_and_malformed_levels_are_valid_data():
    assert q49.bid_price_map(None, 0.5) == {}
    assert q49.bid_price_map([], 0.5) == {}
    assert q49.bid_price_map([[0.6], None, [None, 5.0], [0.6, None]], 0.5) == {}


def test_queue_ahead_counts_only_levels_at_or_above_our_price():
    ladder = [[0.70, 10.0], [0.65, 20.0], [0.64, 999.0]]
    assert q49.queue_ahead_at(ladder, 0.65) == pytest.approx(30.0)
    assert q49.queue_ahead_at(ladder, 0.70) == pytest.approx(10.0)
    assert q49.queue_ahead_at(ladder, 0.64) == pytest.approx(1029.0)


def test_departures_between_is_generous_growth_and_new_levels_ignored():
    prev = [[0.65, 100.0]]
    # level shrank by 40 -> 40 departures
    assert q49.departures_between(prev, [[0.65, 60.0]], 0.65) == pytest.approx(40.0)
    # level GREW -> never a negative departure, and never charged against us
    assert q49.departures_between(prev, [[0.65, 500.0]], 0.65) == pytest.approx(0.0)
    # a brand-new level jumping ahead of us is ignored (generous, L48)
    assert q49.departures_between(prev, [[0.65, 100.0], [0.66, 900.0]], 0.65) == pytest.approx(0.0)
    # the level vanished entirely -> the whole size departed
    assert q49.departures_between(prev, [], 0.65) == pytest.approx(100.0)


def test_traded_through_requires_a_strictly_lower_touch():
    assert q49.traded_through([0.64], 0.65)
    assert not q49.traded_through([0.65, 0.66], 0.65)
    # a missing touch is not evidence either way (L23) and never manufactures a fill
    assert not q49.traded_through([None, None], 0.65)
    assert q49.traded_through([None, 0.60], 0.65)


# --------------------------------------------------------------------------- #
# Fees — ONLY from core.pricing at MAKER_FEE_RATE (L18/L30), one fee per FILLED leg (G4)
# --------------------------------------------------------------------------- #
def test_maker_fee_comes_from_core_pricing_at_maker_rate():
    for p in (0.05, 0.27, 0.5, 0.73, 0.96):
        assert q49.maker_fee(p) == fee_per_contract(p, rate=MAKER_FEE_RATE)


def test_maker_fee_is_the_flat_one_cent_interior_floor_not_the_taker_rate():
    # L5 was a 4x overcharge; this pins the maker side explicitly.
    assert q49.maker_fee(0.50) == pytest.approx(0.01)
    assert q49.maker_fee(0.50) != pytest.approx(fee_per_contract(0.50))


# --------------------------------------------------------------------------- #
# P&L — the four exhaustive per-attempt cases
# --------------------------------------------------------------------------- #
def test_both_fill_pnl_is_deterministic_and_outcome_free():
    """If BOTH legs fill you hold one YES and one NO on the same binary market, so exactly
    one settles $1 regardless of the result — the payoff cannot depend on the outcome."""
    assert "result" not in inspect.signature(q49.both_fill_pnl).parameters
    got = q49.both_fill_pnl(0.46, 0.48)
    assert got == pytest.approx(1.0 - 0.46 - 0.48 - 0.01 - 0.01)
    assert got == pytest.approx(0.04)


def test_both_fill_pnl_charges_two_fees_one_per_filled_leg():
    gross = 1.0 - 0.45 - 0.50
    assert q49.both_fill_pnl(0.45, 0.50) == pytest.approx(gross - 2 * 0.01)


def test_both_fill_pnl_goes_negative_when_the_overround_cannot_cover_two_fees():
    # bid_sum 0.99 -> 1c gross, 2c of fees: the S68 gate (spread >= 2x maker fee) exists
    # precisely to exclude this cell.
    assert q49.both_fill_pnl(0.50, 0.49) == pytest.approx(-0.01)


def test_single_fill_pnl_models_the_catastrophic_losing_leg(monkeypatch):
    # YES leg alone, market settles NO -> we lose the whole premium plus the fee (G2/L41)
    assert q49.single_fill_pnl("yes", 0.30, "no") == pytest.approx(0.0 - 0.30 - 0.01)
    assert q49.single_fill_pnl("yes", 0.30, "yes") == pytest.approx(1.0 - 0.30 - 0.01)
    assert q49.single_fill_pnl("no", 0.40, "no") == pytest.approx(1.0 - 0.40 - 0.01)
    assert q49.single_fill_pnl("no", 0.40, "yes") == pytest.approx(0.0 - 0.40 - 0.01)


def test_single_fill_pnl_is_case_insensitive_on_the_result():
    assert q49.single_fill_pnl("yes", 0.30, "YES") == q49.single_fill_pnl("yes", 0.30, "yes")


def test_attempt_pnl_covers_all_four_cases_and_never_drops_the_single_leg():
    yb, nb = 0.46, 0.48
    assert q49.attempt_pnl(True, True, yb, nb, "no") == pytest.approx(q49.both_fill_pnl(yb, nb))
    # a single-leg fill is a DIRECTIONAL position, not the capture (Q49 gate 2)
    assert q49.attempt_pnl(True, False, yb, nb, "no") == pytest.approx(-0.46 - 0.01)
    assert q49.attempt_pnl(False, True, yb, nb, "yes") == pytest.approx(-0.48 - 0.01)
    # nothing filled -> exactly zero: an unfilled resting order pays no fee
    assert q49.attempt_pnl(False, False, yb, nb, "yes") == 0.0


def test_attempt_pnl_both_fill_is_outcome_invariant():
    a = q49.attempt_pnl(True, True, 0.46, 0.48, "yes")
    b = q49.attempt_pnl(True, True, 0.46, 0.48, "no")
    assert a == pytest.approx(b)


# --------------------------------------------------------------------------- #
# Fill simulation — queue-aware (L39), outcome-BLIND, two explicit models
# --------------------------------------------------------------------------- #
def _snap(yes_bids, no_bids, best_yes_bid, best_no_bid):
    return {"yes_bids": yes_bids, "no_bids": no_bids,
            "best_yes_bid": best_yes_bid, "best_no_bid": best_no_bid}


def test_simulate_side_fill_is_outcome_blind_by_construction():
    """The fill decision must never see the settlement result — otherwise the measured
    adverse selection would be manufactured rather than discovered."""
    params = set(inspect.signature(q49.simulate_side_fill).parameters)
    assert "result" not in params and "settlement" not in params


def test_frozen_queue_never_fills_under_either_model():
    snaps = [_snap([[0.65, 100.0]], [], 0.65, 0.30),
             _snap([[0.65, 100.0]], [], 0.65, 0.30)]
    for fm in q49.FILL_MODELS:
        r = q49.simulate_side_fill(snaps, "yes", 0.65, fm)
        assert r["departures"] == pytest.approx(0.0)
        assert not r["queue_cleared"] and not r["filled"]


def test_queue_must_clear_the_size_ahead_before_a_fill():
    # 100 ahead, only 40 depart -> no fill even under the generous model
    snaps = [_snap([[0.65, 100.0]], [], 0.65, 0.30),
             _snap([[0.65, 60.0]], [], 0.60, 0.30)]
    r = q49.simulate_side_fill(snaps, "yes", 0.65, "queue_only")
    assert not r["queue_cleared"] and not r["filled"]


def test_price_through_is_the_binding_adverse_selection_condition():
    """Queue cleared but the touch never printed below our price: model A fills, model B
    does not. This is the whole difference between the optimistic and the AS-aware model."""
    snaps = [_snap([[0.65, 100.0]], [], 0.65, 0.30),
             _snap([], [], 0.65, 0.30)]
    a = q49.simulate_side_fill(snaps, "yes", 0.65, "queue_only")
    b = q49.simulate_side_fill(snaps, "yes", 0.65, "queue_price_through")
    assert a["queue_cleared"] and b["queue_cleared"]
    assert a["filled"] and not b["filled"]
    assert not b["traded_through"]


def test_queue_cleared_plus_price_through_fills_under_both_models():
    snaps = [_snap([[0.65, 100.0]], [], 0.65, 0.30),
             _snap([], [], 0.60, 0.30)]
    for fm in q49.FILL_MODELS:
        assert q49.simulate_side_fill(snaps, "yes", 0.65, fm)["filled"]


def test_simulate_side_fill_reads_the_no_ladder_for_the_no_side():
    snaps = [_snap([], [[0.30, 50.0]], 0.65, 0.30),
             _snap([], [], 0.65, 0.25)]
    r = q49.simulate_side_fill(snaps, "no", 0.30, "queue_price_through")
    assert r["queue_ahead"] == pytest.approx(50.0)
    assert r["filled"] and r["traded_through"]


def test_simulate_side_fill_tags_the_price_source_as_real_bid():
    snaps = [_snap([[0.65, 1.0]], [], 0.65, 0.30), _snap([], [], 0.60, 0.30)]
    assert q49.simulate_side_fill(snaps, "yes", 0.65)["price_source_tag"] == "real_bid"


def test_unknown_fill_model_raises_rather_than_defaulting_to_the_generous_one():
    snaps = [_snap([], [], 0.65, 0.30), _snap([], [], 0.65, 0.30)]
    with pytest.raises(ValueError):
        q49.simulate_side_fill(snaps, "yes", 0.65, "assume_it_fills")


# --------------------------------------------------------------------------- #
# Population gates
# --------------------------------------------------------------------------- #
def test_two_sided_wide_requires_both_bids_and_the_2x_fee_spread():
    ok = {"best_yes_bid": 0.46, "best_no_bid": 0.48, "best_yes_ask": 0.52}
    assert q49.two_sided_wide(ok)                       # spread 6c
    one_sided = {"best_yes_bid": 0.0, "best_no_bid": 0.48, "best_yes_ask": 0.52}
    assert not q49.two_sided_wide(one_sided)            # not genuinely two-sided
    narrow = {"best_yes_bid": 0.50, "best_no_bid": 0.49, "best_yes_ask": 0.51}
    assert not q49.two_sided_wide(narrow)               # 1c spread < 2x maker fee
    assert not q49.two_sided_wide({"best_yes_bid": None, "best_no_bid": 0.4,
                                   "best_yes_ask": 0.5})


def test_two_sided_wide_accepts_exactly_the_two_cent_boundary():
    assert q49.two_sided_wide({"best_yes_bid": 0.50, "best_no_bid": 0.48,
                               "best_yes_ask": 0.52})


def test_select_entry_first_vs_late_and_requires_a_post_entry_snapshot():
    wide = {"best_yes_bid": 0.40, "best_no_bid": 0.50, "best_yes_ask": 0.50}
    narrow = {"best_yes_bid": 0.50, "best_no_bid": 0.49, "best_yes_ask": 0.51}
    pre = [wide, narrow, wide, narrow]
    assert q49.select_entry(pre, "first") == 0
    assert q49.select_entry(pre, "late") == 2
    # the LAST snapshot can never be the entry — a fill-sim needs an observation after entry
    assert q49.select_entry([narrow, wide], "first") is None
    assert q49.select_entry([narrow, narrow], "first") is None


def test_select_entry_rejects_an_unknown_policy():
    with pytest.raises(ValueError):
        q49.select_entry([], "whenever_it_looks_good")


def test_load_settlements_drops_scalar_results_and_keeps_broker_truth(tmp_path):
    """L52: a `scalar` result is not a two-outcome settlement and must never be coerced."""
    p = tmp_path / "dt=2026-07-22.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in [
        {"ticker": "KXNPBGAME-A-X", "result": "yes", "close_time": "2026-07-20T00:00:00Z"},
        {"ticker": "KXNPBGAME-A-Y", "result": "no", "close_time": "2026-07-20T00:00:00Z"},
        {"ticker": "KXWTIH-A-Z", "result": "scalar", "close_time": "2026-07-20T00:00:00Z"},
        {"ticker": "KXNPBGAME-A-W", "result": None, "close_time": "2026-07-20T00:00:00Z"},
    ]) + "\n", encoding="utf-8")
    got = q49.load_settlements(str(tmp_path / "dt=*.jsonl"))
    assert set(got) == {"KXNPBGAME-A-X", "KXNPBGAME-A-Y"}


def test_load_settlements_uses_the_sanctioned_binary_result_guard(tmp_path):
    """L52: the scalar/binary decision comes from core.settlement, not a hand-rolled
    string comparison — so a new non-binary result label is caught at the sanctioned site."""
    from core.settlement import is_binary_result
    assert is_binary_result("yes") and is_binary_result("no")
    assert not is_binary_result("scalar") and not is_binary_result(None)
    p = tmp_path / "dt=2026-07-22.jsonl"
    p.write_text(json.dumps({"ticker": "KXNPBGAME-A-X", "result": "scalar",
                             "close_time": "2026-07-20T00:00:00Z"}) + "\n", encoding="utf-8")
    assert q49.load_settlements(str(tmp_path / "dt=*.jsonl")) == {}


def test_build_attempts_drops_non_game_series_and_uses_settlement_only_for_payout():
    settlements = {
        "KXNPBGAME-A-X": {"result": "yes", "close_time": "2026-07-20T12:00:00Z"},
        "KXMVECROSSCATEGORY-A-X": {"result": "yes", "close_time": "2026-07-20T12:00:00Z"},
    }
    window = [
        dict(_snap([[0.40, 10.0]], [[0.50, 10.0]], 0.40, 0.50),
             captured_at="2026-07-20T10:00:00Z", best_yes_ask=0.50),
        dict(_snap([], [], 0.35, 0.45),
             captured_at="2026-07-20T11:00:00Z", best_yes_ask=0.50),
    ]
    depth = {"KXNPBGAME-A-X": window, "KXMVECROSSCATEGORY-A-X": window}
    atts = q49.build_attempts(settlements, depth)
    assert [a["ticker"] for a in atts] == ["KXNPBGAME-A-X"]
    a = atts[0]
    assert a["series"] == "KXNPBGAME" and a["result"] == "yes"
    assert a["yes_bid"] == pytest.approx(0.40) and a["no_bid"] == pytest.approx(0.50)
    assert a["price_source_tag"] == "real_bid"
    assert a["settlement_price_source_tag"] == "broker_truth"


def test_build_attempts_excludes_post_close_snapshots():
    settlements = {"KXNPBGAME-A-X": {"result": "yes", "close_time": "2026-07-20T10:30:00Z"}}
    depth = {"KXNPBGAME-A-X": [
        dict(_snap([[0.40, 10.0]], [[0.50, 10.0]], 0.40, 0.50),
             captured_at="2026-07-20T10:00:00Z", best_yes_ask=0.50),
        dict(_snap([], [], 0.35, 0.45),
             captured_at="2026-07-20T11:00:00Z", best_yes_ask=0.50),   # AFTER close
    ]}
    # only one pre-close snapshot survives -> below MIN_PRE_SNAPSHOTS -> no attempt
    assert q49.build_attempts(settlements, depth) == []


# --------------------------------------------------------------------------- #
# Verdict wiring — the kill conditions must actually fire
# --------------------------------------------------------------------------- #
def _model_stub(**over):
    base = {
        "n_attempts": 100, "both_fill_rate": 0.5, "mean_net_pnl_both_fill": 0.05,
        "bootstrap_per_attempt_by_series": {
            "ci95": [0.02, 0.09], "n_units": 12, "admissible": True,
            "admissibility_reasons": [], "clears_tick_magnitude": True},
    }
    base.update(over)
    return base


def test_verdict_survives_only_when_every_gate_passes():
    assert q49.verdict_for(_model_stub())["verdict"] == "SURVIVES"


def test_verdict_empty_population_is_dead_by_adequacy():
    v = q49.verdict_for(_model_stub(n_attempts=0))
    assert v["verdict"] == "DEAD-by-adequacy" and v["reasons"] == ["empty_population"]


def test_verdict_kills_on_fill_rate_at_or_below_the_s19_floor():
    v = q49.verdict_for(_model_stub(both_fill_rate=q49.S19_FILL_FLOOR))
    assert v["verdict"] == "DEAD"
    assert any("S19_floor" in r for r in v["reasons"])


def test_verdict_kills_on_non_positive_both_fill_overround():
    v = q49.verdict_for(_model_stub(mean_net_pnl_both_fill=-0.001))
    assert any("both_fill_net_overround_non_positive" in r for r in v["reasons"])


def test_verdict_kills_on_a_ci_that_straddles_zero():
    v = q49.verdict_for(_model_stub(bootstrap_per_attempt_by_series={
        "ci95": [-0.05, 0.09], "n_units": 18, "admissible": True,
        "admissibility_reasons": [], "clears_tick_magnitude": False}))
    assert v["verdict"] == "DEAD"
    assert "per_attempt_ci_not_above_zero" in v["reasons"]
    assert "fails_clears_tick_magnitude" in v["reasons"]


def test_verdict_kills_on_an_inadmissible_l41_degenerate_bootstrap():
    v = q49.verdict_for(_model_stub(bootstrap_per_attempt_by_series={
        "ci95": [0.07, 0.31], "n_units": 18, "admissible": False,
        "admissibility_reasons": ["no_opposing_unit"], "clears_tick_magnitude": True}))
    assert v["verdict"] == "DEAD"
    assert "bootstrap_inadmissible:no_opposing_unit" in v["reasons"]


def test_verdict_kills_below_the_ten_series_bootstrap_floor():
    v = q49.verdict_for(_model_stub(bootstrap_per_attempt_by_series={
        "ci95": [0.02, 0.09], "n_units": 4, "admissible": False,
        "admissibility_reasons": ["below_min_units"], "clears_tick_magnitude": True}))
    assert any("below_series_floor" in r for r in v["reasons"])


# --------------------------------------------------------------------------- #
# End-to-end on synthetic tape (no network, no live tape)
# --------------------------------------------------------------------------- #
def test_run_model_books_the_overround_only_when_both_legs_fill():
    attempts = [{
        "ticker": "KXNPBGAME-A-X", "series": "KXNPBGAME", "event_ticker": "KXNPBGAME-A",
        "result": "no", "yes_bid": 0.40, "no_bid": 0.50, "yes_spread": 0.10,
        "entry_captured_at": "2026-07-20T10:00:00Z", "n_post_entry_snapshots": 1,
        "window": [_snap([[0.40, 5.0]], [[0.50, 5.0]], 0.40, 0.50),
                   _snap([], [], 0.35, 0.45)],
        "price_source_tag": "real_bid", "settlement_price_source_tag": "broker_truth",
    }]
    m = q49.run_model(attempts, "queue_price_through")
    assert m["counts"]["both"] == 1
    assert m["mean_pnl_per_attempt"] == pytest.approx(q49.both_fill_pnl(0.40, 0.50))
    assert m["frac_bid_sum_below_1"] == pytest.approx(1.0)


def test_run_model_charges_adverse_selection_on_a_single_leg_fill():
    """Only the YES leg trades through; the market settles NO -> the attempt must carry the
    full directional loss, not the both-fill overround."""
    attempts = [{
        "ticker": "KXNPBGAME-A-X", "series": "KXNPBGAME", "event_ticker": "KXNPBGAME-A",
        "result": "no", "yes_bid": 0.40, "no_bid": 0.50, "yes_spread": 0.10,
        "entry_captured_at": "2026-07-20T10:00:00Z", "n_post_entry_snapshots": 1,
        "window": [_snap([[0.40, 5.0]], [[0.50, 5.0]], 0.40, 0.50),
                   _snap([], [[0.50, 5.0]], 0.35, 0.50)],
        "price_source_tag": "real_bid", "settlement_price_source_tag": "broker_truth",
    }]
    m = q49.run_model(attempts, "queue_price_through")
    assert m["counts"] == {"both": 0, "yes_only": 1, "no_only": 0, "none": 0}
    assert m["mean_pnl_per_attempt"] == pytest.approx(-0.41)
    assert m["adverse_selection"]["yes_only_settle_yes_rate"] == pytest.approx(0.0)
