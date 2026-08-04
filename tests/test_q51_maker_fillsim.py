"""Offline tests for scripts/q51_maker_fillsim.py (Q51 milestone 2).

No network. The `test_acceptance_*` cases read the COMMITTED, FROZEN day slice
`dt=2026-08-03` of `tape/orderbook_depth/`, `tape/kalshi_trades/` and
`tape/q51_settlement_cache/` (L191: pin acceptance numbers to a slice that cannot grow —
both day files are for a PAST day, and the trade collector is `trade_id`-deduped) and
hard-assert rather than skip.
"""
from __future__ import annotations

import json

import pytest

from core.pricing import MAKER_FEE_RATE, TAKER_FEE_RATE, fee_per_contract
from scripts import q51_maker_fillsim as M


# --------------------------------------------------------------------------- #
# keys / population helpers
# --------------------------------------------------------------------------- #
def test_game_of_strips_the_outcome_leg_not_the_event():
    assert M.game_of("KXMLBGAME-26AUG032005LADCHC-CHC") == "KXMLBGAME-26AUG032005LADCHC"
    assert M.game_of("NOHYPHEN") == "NOHYPHEN"


def test_series_of():
    assert M.series_of("KXMLBGAME-26AUG032005LADCHC-CHC") == "KXMLBGAME"


def test_is_sports_game_market_selects_game_series_and_excludes_kxmve_l31():
    assert M.is_sports_game_market("KXMLBGAME-26AUG03-CHC")
    assert not M.is_sports_game_market("KXBTC-26AUG0312-T50")
    assert not M.is_sports_game_market("KXETH-26AUG0300-T2")
    # L31: the nominal-wing AMM multi-outcome families are out even though they end GAME
    assert not M.is_sports_game_market("KXMVESPORTSMULTIGAME-S2026-X")


def test_parse_ts_handles_variable_fractional_precision_and_bad_input():
    assert M.parse_ts("2026-08-03T13:25:19.649422Z") is not None
    assert M.parse_ts("2026-08-03T13:25:19Z") is not None
    assert M.parse_ts("2026-08-03T13:25:19.649422+00:00") is not None
    assert M.parse_ts("") is None
    assert M.parse_ts(None) is None
    assert M.parse_ts("not-a-time") is None


def test_reconstruct_sample_is_insertion_order_stride_13_first_200():
    order = [f"T{i}" for i in range(3000)]
    s = M.reconstruct_sample(order)
    assert len(s) == 200
    assert s[0] == "T0" and s[1] == "T13" and s[-1] == "T2587"


# --------------------------------------------------------------------------- #
# the fill predicate — orientation is the load-bearing part
# --------------------------------------------------------------------------- #
def _pr(ts, price, side, tid="tid"):
    return {"ts": ts, "yes_price": price, "taker_book_side": side, "trade_id": tid}


def test_orientation_constants_are_the_takers_own_order_side():
    # a taker carrying a BID is a BUYER; one carrying an ASK is a SELLER
    assert M.TAKER_BUYS == "bid"
    assert M.TAKER_SELLS == "ask"


def test_yes_bid_is_filled_by_a_selling_taker_not_a_buying_one():
    sells = [_pr(10, 0.60, M.TAKER_SELLS)]
    buys = [_pr(10, 0.60, M.TAKER_BUYS)]
    assert M.yes_bid_fill(sells, 0, 20, 0.60) is not None
    # REGRESSION (milestone 1's inverted reading): a BUYING taker must NOT fill a resting bid
    assert M.yes_bid_fill(buys, 0, 20, 0.60) is None


def test_no_bid_is_filled_by_a_buying_taker_not_a_selling_one():
    # a NO bid at 0.35 is a YES offer at 0.65
    buys = [_pr(10, 0.65, M.TAKER_BUYS)]
    sells = [_pr(10, 0.65, M.TAKER_SELLS)]
    assert M.no_bid_fill(buys, 0, 20, 0.35) is not None
    assert M.no_bid_fill(sells, 0, 20, 0.35) is None


def test_regression_inverting_the_orientation_changes_the_answer():
    """Pins that orientation is NOT a cosmetic naming choice: the same tape read the
    milestone-1 way produces a different fill on both legs."""
    prints = [_pr(10, 0.60, M.TAKER_SELLS), _pr(11, 0.72, M.TAKER_BUYS)]
    correct_yes = M.yes_bid_fill(prints, 0, 20, 0.60) is not None
    inverted_yes = any(p["ts"] > 0 and p["ts"] <= 20 and p["taker_book_side"] == "bid"
                       and p["yes_price"] <= 0.60 for p in prints)
    assert correct_yes is True and inverted_yes is False


def test_yes_bid_fills_through_the_price_but_not_above_it():
    assert M.yes_bid_fill([_pr(5, 0.55, M.TAKER_SELLS)], 0, 10, 0.60) is not None  # through
    assert M.yes_bid_fill([_pr(5, 0.60, M.TAKER_SELLS)], 0, 10, 0.60) is not None  # at
    assert M.yes_bid_fill([_pr(5, 0.61, M.TAKER_SELLS)], 0, 10, 0.60) is None      # above


def test_no_bid_fills_through_the_price_but_not_below_it():
    assert M.no_bid_fill([_pr(5, 0.70, M.TAKER_BUYS)], 0, 10, 0.35) is not None
    assert M.no_bid_fill([_pr(5, 0.65, M.TAKER_BUYS)], 0, 10, 0.35) is not None
    assert M.no_bid_fill([_pr(5, 0.64, M.TAKER_BUYS)], 0, 10, 0.35) is None


def test_fill_window_is_left_open_right_closed():
    at_t0 = [_pr(0, 0.50, M.TAKER_SELLS)]
    at_t1 = [_pr(10, 0.50, M.TAKER_SELLS)]
    after = [_pr(11, 0.50, M.TAKER_SELLS)]
    assert M.yes_bid_fill(at_t0, 0, 10, 0.60) is None
    assert M.yes_bid_fill(at_t1, 0, 10, 0.60) is not None
    assert M.yes_bid_fill(after, 0, 10, 0.60) is None


def test_fill_returns_the_earliest_qualifying_print_and_it_carries_a_trade_id():
    prints = [_pr(3, 0.50, M.TAKER_SELLS, "early"), _pr(7, 0.50, M.TAKER_SELLS, "late")]
    assert M.yes_bid_fill(prints, 0, 10, 0.60)["trade_id"] == "early"


def test_no_print_means_no_fill_never_a_synthesised_one():
    assert M.yes_bid_fill([], 0, 10, 0.60) is None
    assert M.no_bid_fill([], 0, 10, 0.35) is None


# --------------------------------------------------------------------------- #
# fees (L5) and P&L
# --------------------------------------------------------------------------- #
def test_leg_pnl_uses_the_maker_rate_not_the_taker_rate_l5():
    assert M.FEE_RATE == MAKER_FEE_RATE
    assert M.FEE_RATE != TAKER_FEE_RATE
    p = 0.40
    assert M.leg_pnl(p, True) == pytest.approx(
        1.0 - p - fee_per_contract(p, rate=MAKER_FEE_RATE))
    # charging the taker rate would be a materially different (worse) number — L5's 4x bug
    taker = 1.0 - p - fee_per_contract(p, rate=TAKER_FEE_RATE)
    assert M.leg_pnl(p, True) != pytest.approx(taker)


def test_leg_pnl_loss_side_is_modelled_not_conditioned_away():
    p = 0.40
    assert M.leg_pnl(p, False) == pytest.approx(-p - fee_per_contract(p, rate=MAKER_FEE_RATE))
    assert M.leg_pnl(p, False) < 0


# --------------------------------------------------------------------------- #
# row construction / abstention discipline
# --------------------------------------------------------------------------- #
def _snap(ts, ybid=0.60, nbid=0.38, captured_at=None):
    return {"ts": ts, "captured_at": captured_at or f"t{ts}", "best_yes_bid": ybid,
            "best_no_bid": nbid,
            "best_yes_ask": (1 - nbid) if isinstance(nbid, (int, float)) else None}


def _settle(result="yes", close_time=None):
    return {"result": result, "close_time": close_time, "event_ticker": None}


def test_build_rows_scores_both_sides_of_every_interval():
    tk = "KXTESTGAME-26AUG03AB-A"
    snaps = {tk: [_snap(0), _snap(100)]}
    rows, stats = M.build_rows(snaps, {}, {tk: _settle()}, [tk])
    assert {r["side"] for r in rows} == {"yes_bid", "no_bid"}
    assert len(rows) == 2
    assert stats["n_intervals"] == 1


def test_unfilled_leg_is_zero_pnl_not_dropped():
    tk = "KXTESTGAME-26AUG03AB-A"
    rows, _ = M.build_rows({tk: [_snap(0), _snap(100)]}, {}, {tk: _settle()}, [tk])
    assert all(r["filled"] is False and r["pnl"] == 0.0 for r in rows)
    assert all(r["fill_trade_id"] is None for r in rows)


def test_unsettled_market_is_dropped_and_counted_never_imputed():
    tk = "KXTESTGAME-26AUG03AB-A"
    rows, stats = M.build_rows({tk: [_snap(0), _snap(100)]}, {},
                               {tk: _settle(result="")}, [tk])
    assert rows == []
    assert stats["drops"]["unsettled"] == 1


def test_non_binary_scalar_result_is_dropped_and_counted_l52():
    tk = "KXTESTGAME-26AUG03AB-A"
    rows, stats = M.build_rows({tk: [_snap(0), _snap(100)]}, {},
                               {tk: _settle(result="scalar")}, [tk])
    assert rows == []
    assert stats["drops"]["non_binary_result"] == 1


def test_single_snapshot_ticker_contributes_no_interval():
    tk = "KXTESTGAME-26AUG03AB-A"
    rows, stats = M.build_rows({tk: [_snap(0)]}, {}, {tk: _settle()}, [tk])
    assert rows == [] and stats["n_intervals"] == 0
    assert stats["drops"]["single_snapshot"] == 1


def test_one_sided_book_is_dropped_never_mirrored_into_a_synthetic_quote():
    tk = "KXTESTGAME-26AUG03AB-A"
    snaps = {tk: [_snap(0, nbid=None), _snap(100)]}
    rows, stats = M.build_rows(snaps, {}, {tk: _settle()}, [tk])
    assert rows == [] and stats["drops"]["not_two_sided"] == 1


def test_entry_after_close_time_is_dropped():
    tk = "KXTESTGAME-26AUG03AB-A"
    snaps = {tk: [_snap(1000), _snap(2000)]}
    sett = {tk: _settle(close_time="1970-01-01T00:00:10Z")}
    rows, stats = M.build_rows(snaps, {}, sett, [tk])
    assert rows == [] and stats["drops"]["post_close"] == 1


def test_interval_coverage_is_reported_and_an_uncovered_interval_is_flagged():
    tk = "KXTESTGAME-26AUG03AB-A"
    snaps = {tk: [_snap(0), _snap(100), _snap(200)]}
    prints = {tk: [_pr(50, 0.50, M.TAKER_SELLS)]}
    rows, stats = M.build_rows(snaps, prints, {tk: _settle()}, [tk])
    assert stats["n_intervals"] == 2 and stats["n_covered_intervals"] == 1
    assert stats["interval_coverage"] == 0.5
    assert {r["interval_covered"] for r in rows} == {True, False}


def test_every_filled_row_traces_to_a_broker_truth_print():
    tk = "KXTESTGAME-26AUG03AB-A"
    prints = {tk: [_pr(50, 0.55, M.TAKER_SELLS, "abc")]}
    rows, _ = M.build_rows({tk: [_snap(0), _snap(100)]}, prints, {tk: _settle()}, [tk])
    filled = [r for r in rows if r["filled"]]
    assert filled and all(r["fill_trade_id"] and
                          r["fill_price_source_tag"] == "broker_truth" for r in filled)


def test_rest_price_is_tagged_real_bid_never_synthetic():
    tk = "KXTESTGAME-26AUG03AB-A"
    rows, _ = M.build_rows({tk: [_snap(0), _snap(100)]}, {}, {tk: _settle()}, [tk])
    assert all(r["price_source_tag"] == "real_bid" for r in rows)


def test_load_prints_rejects_a_line_that_is_not_broker_truth(tmp_path):
    p = tmp_path / "dt=2026-08-03.jsonl"
    good = {"ticker": "T-A", "created_time": "2026-08-03T00:00:01Z", "yes_price": 0.5,
            "taker_book_side": "bid", "trade_id": "g", "price_source_tag": "broker_truth"}
    bad = dict(good, trade_id="b", price_source_tag="synthetic")
    p.write_text(json.dumps(good) + "\n" + json.dumps(bad) + "\n")
    out = M.load_prints(path=p)
    assert [r["trade_id"] for r in out["T-A"]] == ["g"]


# --------------------------------------------------------------------------- #
# bootstrap grouping and gates
# --------------------------------------------------------------------------- #
def test_unit_values_group_by_game_never_by_outcome_l6():
    rows = [{"game": "G1", "pnl": 1.0}, {"game": "G1", "pnl": -1.0}, {"game": "G2", "pnl": 0.5}]
    uv = M.unit_values(rows)
    assert set(uv) == {"G1", "G2"} and sorted(uv["G1"]) == [-1.0, 1.0]


def test_verdict_reports_losing_clusters_and_flags_below_min_units():
    rows = [{"game": f"G{i}", "pnl": (0.5 if i % 2 else -0.4), "filled": True}
            for i in range(4)]
    v = M.verdict_for(rows, "x", n_boot=200)
    assert v["n_units_games"] == 4
    assert v["n_losing_units"] >= 1
    assert v["admissible"] is False
    assert "below_min_units" in v["admissibility"]["reasons"]
    assert v["verdict"] == "INADMISSIBLE"


def test_verdict_label_kills_a_positive_but_sub_tick_ci_l27():
    boot = {"ci95": [0.001, 0.02], "mean": 0.01}
    adm = {"admissible": True, "reasons": []}
    assert "sub-tick" in M._verdict_label(boot, adm, tick_ok=False)
    assert M._verdict_label(boot, adm, tick_ok=True).startswith("ALIVE-CANDIDATE")


def test_verdict_label_kills_a_ci_straddling_zero():
    boot = {"ci95": [-0.02, 0.05], "mean": 0.01}
    assert M._verdict_label(boot, {"admissible": True, "reasons": []},
                            tick_ok=False).startswith("DEAD")


def test_verdict_carries_the_maker_fee_rate_and_both_source_tags():
    v = M.verdict_for([{"game": "G1", "pnl": 0.1, "filled": True}], "x", n_boot=50)
    assert v["fee_rate"] == MAKER_FEE_RATE
    assert v["price_source_tag"] == "real_bid"
    assert v["fill_evidence_tag"] == "broker_truth"


# --------------------------------------------------------------------------- #
# the 3-hour resolution CEILING
# --------------------------------------------------------------------------- #
def test_module_computes_no_queue_position_or_time_to_fill_number():
    """The book cadence is ~3h; a queue-position or time-to-fill number is not claimable
    from this tape and must not appear in the report."""
    report, rows = M.run(n_boot=100)

    def keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield str(k).lower()
                yield from keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys(v)

    all_keys = set(keys(report)) | {k.lower() for r in rows for k in r}
    for tok in M.FORBIDDEN_REPORT_TOKENS:
        leaked = [k for k in all_keys if tok in k]
        assert not leaked, f"report leaked a forbidden resolution claim: {leaked}"


def test_report_states_the_resolution_ceiling_explicitly():
    report, _rows = M.run(n_boot=100)
    assert "queue" in report["resolution_ceiling"].lower()
    assert "existence" in report["resolution_ceiling"].lower()


# --------------------------------------------------------------------------- #
# HARD acceptance tests over the committed, frozen dt=2026-08-03 slice (L191)
# --------------------------------------------------------------------------- #
def test_acceptance_sample_reconstruction_covers_every_traded_ticker():
    order, _snaps = M.load_depth()
    prints = M.load_prints()
    assert order, "committed orderbook_depth dt=2026-08-03 missing"
    assert prints, "committed kalshi_trades dt=2026-08-03 missing"
    sample = set(M.reconstruct_sample(order))
    assert len(sample) == 200
    assert set(prints).issubset(sample), (
        "milestone 1's stride sample was not reproduced — the fill-rate denominator "
        "would be wrong")


def test_acceptance_taker_book_side_orientation_bid_is_a_buyer():
    """The ORIENTATION CORRECTION, pinned on real tape: restricted to prints landing
    within 15 minutes of their reference snapshot, a `bid` taker's print sits at or ABOVE
    the best ask — i.e. it LIFTED the offer, so it cannot fill a resting bid."""
    at_or_above_ask, total = _orientation_counts(M.TAKER_BUYS, max_age_s=900)
    assert total >= 100, f"too few fresh bid-side prints to pin orientation ({total})"
    assert at_or_above_ask / total >= 0.80


def test_acceptance_taker_book_side_orientation_ask_is_a_seller():
    at_or_below_bid, total = _orientation_counts(M.TAKER_SELLS, max_age_s=900,
                                                 direction="bid")
    assert total >= 20, f"too few fresh ask-side prints to pin orientation ({total})"
    assert at_or_below_bid / total >= 0.75


def test_acceptance_orientation_signal_decays_as_the_reference_quote_goes_stale():
    """A real relationship degrades as the join window widens; an artifact would not."""
    fresh = _rate(M.TAKER_BUYS, 900)
    hour = _rate(M.TAKER_BUYS, 3600)
    anyage = _rate(M.TAKER_BUYS, 10 ** 9)
    assert fresh > hour > anyage


def _orientation_counts(side, *, max_age_s, direction="ask"):
    order, snaps = M.load_depth()
    prints = M.load_prints()
    universe = [t for t in M.reconstruct_sample(order) if M.is_sports_game_market(t)]
    hit = tot = 0
    for tk in universe:
        ss = snaps.get(tk) or []
        for a, b in zip(ss[:-1], ss[1:]):
            yb, ya = a.get("best_yes_bid"), a.get("best_yes_ask")
            if not yb or not ya:
                continue
            for pr in prints.get(tk, []):
                if not (a["ts"] < pr["ts"] <= b["ts"]) or pr["ts"] - a["ts"] > max_age_s:
                    continue
                if pr["taker_book_side"] != side:
                    continue
                tot += 1
                if direction == "ask" and pr["yes_price"] >= ya - 1e-9:
                    hit += 1
                elif direction == "bid" and pr["yes_price"] <= yb + 1e-9:
                    hit += 1
    return hit, tot


def _rate(side, max_age_s):
    hit, tot = _orientation_counts(side, max_age_s=max_age_s)
    return hit / tot if tot else 0.0


def test_acceptance_headline_verdict_is_data_inadequate_below_min_units():
    """Pins the RECORDED milestone-2 verdict. If this ever changes, the finding and the
    LOOP-QUEUE status line are stale and must be re-derived, not quietly overwritten."""
    report, rows = M.run(n_boot=2000)
    v = report["verdicts"]["all_intervals"]
    assert v["n_units_games"] == 7
    assert v["n_legs"] == 40 and v["n_filled_legs"] == 26
    assert v["admissible"] is False
    assert v["admissibility"]["reasons"] == ["below_min_units"]
    # the failure is NOT definitional (L249): the object COULD have disagreed
    assert v["sign_bounded_objective"]["verdict_bearing"] is True
    assert v["sign_bounded_objective"]["inadmissibility_is_definitional"] is False
    assert v["n_losing_units"] >= 1          # the S20 >=1-losing-cluster requirement
    assert v["clears_tick_magnitude"] is False
    assert v["verdict"] == "INADMISSIBLE"
    assert len(rows) == 40


def test_acceptance_settlement_recency_is_the_binding_constraint_not_the_fill_leg():
    report, _rows = M.run(n_boot=100)
    iv = report["intervals"]
    assert iv["n_intervals"] == 20 and iv["n_covered_intervals"] == 17
    assert iv["interval_coverage"] == pytest.approx(0.85)
    # 145 of the day's 165 sports intervals die on an UNSETTLED market, not on coverage
    assert iv["drops"]["unsettled"] == 145
    assert iv["drops"]["no_settlement"] == 0


def test_acceptance_every_real_fill_traces_to_a_broker_truth_trade_id():
    report, rows = M.run(n_boot=100)
    assert report["fill_traceability"]["all_fills_traced"] is True
    assert report["fill_traceability"]["n_fills"] == 26
    for r in rows:
        if r["filled"]:
            assert r["fill_trade_id"] and r["fill_price_source_tag"] == "broker_truth"
