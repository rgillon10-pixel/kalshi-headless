"""Offline tests for `scripts/q56_s80_print_vwap_overshoot_maker_fade.py` (Q56 / S80).

Three jobs, the house shape:

  1. pure unit tests on synthetic fixtures — the look-ahead firewall, the VWAP/chase signal,
     the registered direction, the queue-aware fill predicate and its CORRECTED
     `taker_book_side` orientation, the maker-fee arithmetic, the losing leg;
  2. discipline pins — the fill predicate can only ever return a `broker_truth` `trade_id`
     (a synthesised fill is unconstructible), the mirror leg is labelled DESCRIPTIVE-ONLY,
     the module holds no network/order surface, and the bootstrap unit is the GAME;
  3. real-tape acceptance on a FIXED, never-growing slice of committed day files, with
     directional assertions that survive tape growth, plus one hard pin of the headline
     kill so a future edit cannot silently flip the verdict.

Every test is offline: no network, no credentials, no writes outside tmp_path.
"""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.pricing import MAKER_FEE_RATE, fee_per_contract  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402
from scripts import q56_s80_print_vwap_overshoot_maker_fade as Q  # noqa: E402

# A fixed slice of committed tape — the two families' overlap on a single day. Never the
# open-ended live glob: a test that globs a growing family red-lines the day a collector
# lands a new day-file.
TRADE_DAY = REPO / "tape" / "kalshi_trades" / "dt=2026-07-11.jsonl"
DEPTH_DAY = REPO / "tape" / "orderbook_depth" / "dt=2026-07-11.jsonl"
_real_tape = pytest.mark.skipif(
    not (TRADE_DAY.exists() and DEPTH_DAY.exists()),
    reason="committed kalshi_trades / orderbook_depth day files not present")


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _p(ts, price, count, tbs="bid", tid=None):
    return (parse_iso_utc(ts), float(price), float(count), tbs, tid or f"t-{ts}-{price}")


def _snap(ticker, captured_at, *, yes_bid=None, no_bid=None,
          yes_bids=None, no_bids=None):
    return {"ticker": ticker, "captured_at": captured_at,
            "best_yes_bid": yes_bid, "best_no_bid": no_bid,
            "yes_bids": yes_bids if yes_bids is not None else ([[yes_bid, 10.0]]
                                                               if yes_bid is not None else []),
            "no_bids": no_bids if no_bids is not None else ([[no_bid, 10.0]]
                                                            if no_bid is not None else []),
            "price_source_tags": {"asks": "real_ask", "bids": "real_bid"}}


# --------------------------------------------------------------------------- #
# 1. ticker helpers
# --------------------------------------------------------------------------- #
def test_event_ticker_is_the_bootstrap_unit_and_strips_only_the_outcome_segment():
    assert Q.event_ticker_of("KXMLBGAME-26JUL07AAABBB-AAA") == "KXMLBGAME-26JUL07AAABBB"
    assert Q.event_ticker_of("KXMLBGAME-26JUL07AAABBB-BBB") == "KXMLBGAME-26JUL07AAABBB"
    # two outcomes of the same game collapse to ONE unit (L6) -- never two
    assert (Q.event_ticker_of("KXWCGAME-26JUL15ENGARG-ENG")
            == Q.event_ticker_of("KXWCGAME-26JUL15ENGARG-ARG"))
    assert Q.event_ticker_of("NOSEGMENTS") == "NOSEGMENTS"


def test_series_and_game_series_predicate():
    assert Q.series_of("KXKBOGAME-26AUG040530KTWKIA-KIA") == "KXKBOGAME"
    assert Q.is_game_series("KXKBOGAME-26AUG040530KTWKIA-KIA")
    assert not Q.is_game_series("KXBTC-26JUL0621-T71799.99")


# --------------------------------------------------------------------------- #
# 2. signal: look-ahead firewall + VWAP + chase
# --------------------------------------------------------------------------- #
def test_vwap_is_volume_weighted_not_a_simple_mean():
    prs = [_p("2026-07-11T10:00:00Z", 0.10, 1.0), _p("2026-07-11T10:01:00Z", 0.50, 9.0)]
    assert Q.vwap(prs) == pytest.approx((0.10 * 1 + 0.50 * 9) / 10.0)


def test_vwap_on_empty_or_zero_size_is_none_not_a_crash():
    assert Q.vwap([]) is None
    assert Q.vwap([_p("2026-07-11T10:00:00Z", 0.5, 0.0)]) is None


def test_split_windows_never_returns_a_print_at_or_after_the_snapshot_instant():
    t_i = parse_iso_utc("2026-07-11T12:00:00Z")
    prs = [_p("2026-07-11T10:00:00Z", 0.2, 1),   # anchor
           _p("2026-07-11T11:45:00Z", 0.3, 1),   # recent
           _p("2026-07-11T12:00:00Z", 0.9, 1),   # AT t_i -- must be excluded
           _p("2026-07-11T12:30:00Z", 0.9, 1)]   # after -- must be excluded
    anchor, recent = Q.split_windows(prs, t_i, timedelta(minutes=30))
    assert [a[1] for a in anchor] == [0.2]
    assert [r[1] for r in recent] == [0.3]


def test_chase_signal_is_none_when_either_leg_is_too_thin():
    t_i = parse_iso_utc("2026-07-11T12:00:00Z")
    prs = [_p("2026-07-11T10:00:00Z", 0.2, 1)] * 1
    assert Q.chase_signal(prs, t_i, timedelta(minutes=30)) is None


def test_chase_signal_sign_and_magnitude():
    t_i = parse_iso_utc("2026-07-11T12:00:00Z")
    anchor = [_p(f"2026-07-11T10:0{i}:00Z", 0.20, 1) for i in range(5)]
    recent = [_p(f"2026-07-11T11:5{i}:00Z", 0.30, 1) for i in range(3)]
    sig = Q.chase_signal(anchor + recent, t_i, timedelta(minutes=30))
    assert sig["anchor_vwap"] == pytest.approx(0.20)
    assert sig["recent_vwap"] == pytest.approx(0.30)
    assert sig["chase"] == pytest.approx(0.10)
    assert sig["n_anchor_prints"] == 5 and sig["n_recent_prints"] == 3


def test_registered_direction_rests_on_the_trailing_side_of_the_chase():
    # YES chased UP -> the trailing side is NO -> rest a NO bid
    assert Q.fade_side(+0.05) == "no"
    # YES dumped DOWN -> the trailing side is YES -> rest a YES bid
    assert Q.fade_side(-0.05) == "yes"
    assert Q.fade_side(0.0) is None


def test_mirror_side_is_the_exact_sign_flip_and_is_labelled_descriptive_only():
    assert Q.mirror_side(+0.05) == "yes"
    assert Q.mirror_side(-0.05) == "no"
    assert Q.mirror_side(0.0) is None
    src = (REPO / "scripts" / "q56_s80_print_vwap_overshoot_maker_fade.py").read_text()
    assert "DESCRIPTIVE ONLY" in src


# --------------------------------------------------------------------------- #
# 3. queue + fill predicate (the CORRECTED taker_book_side orientation)
# --------------------------------------------------------------------------- #
def test_queue_ahead_counts_only_levels_at_or_above_our_price_and_is_float():
    ladder = [[0.30, 5.5], [0.28, 100.0], [0.25, 7.0]]
    assert Q.queue_ahead_at(ladder, 0.28) == pytest.approx(105.5)
    assert Q.queue_ahead_at(ladder, 0.30) == pytest.approx(5.5)
    assert isinstance(Q.queue_ahead_at(ladder, 0.30), float)


def test_queue_ahead_on_an_empty_ladder_is_zero_not_a_crash():
    assert Q.queue_ahead_at([], 0.5) == 0.0
    assert Q.queue_ahead_at(None, 0.5) == 0.0


def test_a_resting_yes_bid_is_filled_by_an_ASK_side_taker_never_a_BID_side_one():
    # Q51-m2 orientation: taker_book_side names the side the TAKER'S OWN order sat on.
    # A taker holding an ASK is a SELLER and HITS our resting YES bid.
    assert Q.print_consumes("yes", 0.30, yes_price=0.30, taker_book_side="ask")
    assert Q.print_consumes("yes", 0.30, yes_price=0.25, taker_book_side="ask")
    assert not Q.print_consumes("yes", 0.30, yes_price=0.35, taker_book_side="ask")
    assert not Q.print_consumes("yes", 0.30, yes_price=0.30, taker_book_side="bid")


def test_a_resting_no_bid_is_filled_by_a_BID_side_taker_lifting_the_mirrored_offer():
    # a NO bid at 0.70 IS the YES offer at 0.30; a BUYER (taker_book_side 'bid') lifts it
    assert Q.print_consumes("no", 0.70, yes_price=0.30, taker_book_side="bid")
    assert Q.print_consumes("no", 0.70, yes_price=0.45, taker_book_side="bid")
    assert not Q.print_consumes("no", 0.70, yes_price=0.25, taker_book_side="bid")
    assert not Q.print_consumes("no", 0.70, yes_price=0.30, taker_book_side="ask")


def test_fill_requires_consuming_volume_to_strictly_exceed_the_queue_ahead():
    prints = [_p("2026-07-11T12:05:00Z", 0.25, 10.0, "ask"),
              _p("2026-07-11T12:06:00Z", 0.25, 10.0, "ask")]
    assert not Q.simulate_fill("yes", 0.30, 25.0, prints)["filled"]   # 20 <= 25
    got = Q.simulate_fill("yes", 0.30, 15.0, prints)
    assert got["filled"] and got["fill_trade_id"] == prints[1][4]


def test_every_fill_carries_a_broker_truth_trade_id_and_an_unfilled_leg_carries_none():
    prints = [_p("2026-07-11T12:05:00Z", 0.25, 99.0, "ask", tid="TID-XYZ")]
    assert Q.simulate_fill("yes", 0.30, 1.0, prints)["fill_trade_id"] == "TID-XYZ"
    assert Q.simulate_fill("yes", 0.30, 1000.0, prints)["fill_trade_id"] is None
    # a synthesised fill is unconstructible: with no prints there is no fill at any queue
    assert not Q.simulate_fill("yes", 0.30, 0.0, [])["filled"]


# --------------------------------------------------------------------------- #
# 4. fee + P&L arithmetic (L5 -- maker rate, never taker)
# --------------------------------------------------------------------------- #
def test_leg_pnl_charges_exactly_one_maker_fee_and_pays_a_dollar_on_a_win():
    fee = fee_per_contract(0.30, MAKER_FEE_RATE)
    assert Q.leg_pnl("yes", 0.30, "yes") == pytest.approx(1.0 - 0.30 - fee)
    assert Q.leg_pnl("no", 0.70, "no") == pytest.approx(1.0 - 0.70 - fee + 0.0
                                                        - (fee_per_contract(0.70, MAKER_FEE_RATE)
                                                           - fee))


def test_the_losing_leg_loses_its_full_cost_plus_the_fee_and_is_never_dropped():
    assert Q.leg_pnl("yes", 0.30, "no") == pytest.approx(
        -0.30 - fee_per_contract(0.30, MAKER_FEE_RATE))
    assert Q.leg_pnl("no", 0.65, "yes") == pytest.approx(
        -0.65 - fee_per_contract(0.65, MAKER_FEE_RATE))


def test_the_maker_fee_is_the_flat_one_cent_across_the_interior_range():
    # L18/L30: round-up-to-cent makes the maker fee $0.01 for essentially every fillable price
    for price in (0.05, 0.20, 0.50, 0.80, 0.95):
        assert fee_per_contract(price, MAKER_FEE_RATE) == pytest.approx(0.01)
    # and the taker rate would be 4x the coefficient -- never used here
    assert (REPO / "scripts" / "q56_s80_print_vwap_overshoot_maker_fade.py"
            ).read_text().count("TAKER_FEE_RATE") == 0


# --------------------------------------------------------------------------- #
# 5. overshoot gate (K1)
# --------------------------------------------------------------------------- #
def test_overshoot_rows_align_the_gross_to_the_registered_fade_direction():
    prints = {"G-1-AAA": [_p("2026-07-11T10:00:00Z", 0.70, 10.0)],
              "G-1-BBB": [_p("2026-07-11T10:00:00Z", 0.20, 10.0)]}
    results = {"G-1-AAA": "yes", "G-1-BBB": "no"}
    rows = {r["ticker"]: r for r in Q.overshoot_rows(prints, results)}
    # chased side = YES (VWAP 0.70 >= 0.5); it settled YES so the prints UNDERSHOT (-0.30)
    assert rows["G-1-AAA"]["chased_side"] == "yes"
    assert rows["G-1-AAA"]["overshoot"] == pytest.approx(-0.30)
    assert rows["G-1-AAA"]["fade_gross"] == pytest.approx(-0.30)
    # chased side = NO (VWAP 0.20 < 0.5); it settled NO so YES prints overshot (+0.20),
    # and a fade of the NO chase gains the NEGATIVE of that
    assert rows["G-1-BBB"]["chased_side"] == "no"
    assert rows["G-1-BBB"]["fade_gross"] == pytest.approx(-0.20)


def test_overshoot_gate_requires_the_point_estimate_to_strictly_exceed_the_maker_fee():
    rows = [{"game": f"G{i}", "ticker": f"G{i}-A", "fade_gross": 0.005,
             "overshoot": 0.005, "vwap": 0.5, "settlement_value": 0.0,
             "chased_side": "yes"} for i in range(12)]
    got = Q.overshoot_gate(rows, fee=0.01, n_boot=200, seed=1)
    assert got["mean"] == pytest.approx(0.005)
    assert got["passes"] is False           # inside the fee -> K1 fires
    rows2 = [dict(r, fade_gross=0.05) for r in rows]
    assert Q.overshoot_gate(rows2, fee=0.01, n_boot=200, seed=1)["passes"] is True


def test_overshoot_gate_on_an_empty_population_is_a_reasoned_refusal_not_a_crash():
    got = Q.overshoot_gate([], fee=0.01)
    assert got["passes"] is False and got["reason"] == "empty"


# --------------------------------------------------------------------------- #
# 6. candidate construction + scoring, end to end on synthetic tape
# --------------------------------------------------------------------------- #
def _synthetic_case():
    tk = "KXTESTGAME-26JUL11AAABBB-AAA"
    prints = {tk: ([_p(f"2026-07-11T10:{i:02d}:00Z", 0.20, 5.0) for i in range(6)]
                   + [_p(f"2026-07-11T11:5{i}:00Z", 0.32, 5.0) for i in range(3)]
                   + [_p("2026-07-11T12:10:00Z", 0.40, 50.0, "bid", tid="FILLER")])}
    books = {tk: [_snap(tk, "2026-07-11T12:00:00Z", yes_bid=0.28, no_bid=0.68),
                  _snap(tk, "2026-07-11T12:30:00Z", yes_bid=0.30, no_bid=0.66)]}
    return tk, prints, books


def test_build_candidates_picks_the_registered_leg_and_tags_the_price_source():
    tk, prints, books = _synthetic_case()
    rows, stats = Q.build_candidates(prints, books, {tk: "no"}, window_min=30, theta=0.02)
    assert len(rows) == 1
    r = rows[0]
    assert r["chase"] == pytest.approx(0.12)     # 0.32 - 0.20, YES chased UP
    assert r["side"] == "no" and r["mirror_side"] == "yes"
    assert r["fill_price"] == 0.68               # best_no_bid, the touch
    assert r["price_source_tag"] == "real_bid"
    assert r["game"] == "KXTESTGAME-26JUL11AAABBB"
    assert stats["triggered"] == 1 and stats["candidates"] == 1


def test_score_rows_fills_the_registered_leg_off_a_broker_truth_print_and_prices_the_loss():
    tk, prints, books = _synthetic_case()
    rows, _ = Q.build_candidates(prints, books, {tk: "no"}, window_min=30, theta=0.02)
    scored = Q.score_rows(rows, {tk: "no"})
    assert len(scored) == 1
    s = scored[0]
    assert s["filled"] and s["fill_trade_id"] == "FILLER"
    assert s["settlement_tag"] == "broker_truth" and s["price_source_tag"] == "real_bid"
    # NO bid at 0.68, market settled NO -> +1 payout
    assert s["pnl"] == pytest.approx(1.0 - 0.68 - fee_per_contract(0.68, MAKER_FEE_RATE))
    # the same leg on a YES settlement is the full loss, still scored
    scored_loss = Q.score_rows(rows, {tk: "yes"})
    assert scored_loss[0]["pnl"] == pytest.approx(
        -0.68 - fee_per_contract(0.68, MAKER_FEE_RATE))


def test_no_candidate_is_built_below_the_trigger_threshold():
    tk, prints, books = _synthetic_case()
    rows, stats = Q.build_candidates(prints, books, {tk: "no"}, window_min=30, theta=0.50)
    assert rows == [] and stats["below_theta"] == 1


def test_an_unsettled_ticker_never_produces_a_candidate():
    tk, prints, books = _synthetic_case()
    rows, stats = Q.build_candidates(prints, books, {}, window_min=30, theta=0.02)
    assert rows == [] and stats["ticker_unsettled"] == 1


def test_mirror_leg_rests_on_its_OWN_ladder_touch_not_the_registered_one():
    tk, prints, books = _synthetic_case()
    rows, _ = Q.build_candidates(prints, books, {tk: "no"}, window_min=30, theta=0.02)
    mirrored = Q.score_rows(rows, {tk: "no"}, side_key="mirror_side")
    assert mirrored[0]["scored_side"] == "yes"
    assert mirrored[0]["scored_fill_price"] == 0.28      # best_yes_bid, not 0.68


# --------------------------------------------------------------------------- #
# 7. bootstrap branch: unit = game, adequacy reported honestly
# --------------------------------------------------------------------------- #
def _scored(n_games, per_game, pnl):
    return [{"game": f"G{g}", "ticker": f"G{g}-A", "filled": True, "pnl": pnl}
            for g in range(n_games) for _ in range(per_game)]


def test_bootstrap_branch_blocks_by_game_never_by_outcome():
    scored = _scored(3, 4, -0.1)
    got = Q.bootstrap_branch(scored, only_filled=True, n_boot=200, seed=1)
    assert got["n_units"] == 3 and got["n_legs"] == 12   # 12 rows collapse to 3 units (L6)


def test_bootstrap_branch_reports_kish_and_informative_units_beside_n_units():
    scored = _scored(11, 1, -0.1) + [{"game": "Z", "ticker": "Z-A", "filled": True, "pnl": 0.0}]
    got = Q.bootstrap_branch(scored, only_filled=True, n_boot=200, seed=1)
    assert got["n_units"] == 12                       # L41 nominal count
    assert got["n_informative_units"] == 11           # L326: the all-zero unit is uninformative
    assert got["kish_effective_n"]["kish_n"] == pytest.approx(12.0)   # L322


def test_a_below_floor_population_is_inadmissible_never_a_verdict():
    got = Q.bootstrap_branch(_scored(3, 2, +0.5), only_filled=True, n_boot=200, seed=1)
    assert got["admissible"]["admissible"] is False
    assert "below_min_units" in got["admissible"]["reasons"]
    assert got["verdict"] == "INADMISSIBLE"


def test_an_all_same_sign_population_is_inadmissible_L41():
    got = Q.bootstrap_branch(_scored(15, 1, +0.5), only_filled=True, n_boot=200, seed=1)
    assert "no_opposing_unit" in got["admissible"]["reasons"]


def test_bootstrap_branch_on_an_empty_population_is_empty_not_a_crash():
    got = Q.bootstrap_branch([], only_filled=True)
    assert got["verdict"] == "EMPTY" and got["n_units"] == 0


# --------------------------------------------------------------------------- #
# 8. adverse-selection decomposition
# --------------------------------------------------------------------------- #
def test_adverse_selection_cost_is_static_gross_minus_realized_gross():
    tk = "G-1-AAA"
    prints = {tk: [_p("2026-07-11T10:00:00Z", 0.40, 10.0)]}
    scored = [{"ticker": tk, "filled": True, "scored_side": "yes",
               "scored_fill_price": 0.30, "pnl": 1.0 - 0.30 - 0.01}]
    got = Q.adverse_selection_decomposition(scored, prints, {tk: "yes"})
    assert got["static_gross_at_vwap"] == pytest.approx(1.0 - 0.40)
    assert got["realized_gross_at_bid"] == pytest.approx(1.0 - 0.30)
    # resting at the bid was 10c CHEAPER than the average print -> negative (favourable) cost
    assert got["adverse_selection_cost"] == pytest.approx(-0.10)


def test_adverse_selection_ignores_unfilled_legs():
    tk = "G-1-AAA"
    prints = {tk: [_p("2026-07-11T10:00:00Z", 0.40, 10.0)]}
    assert Q.adverse_selection_decomposition(
        [{"ticker": tk, "filled": False, "scored_side": "yes",
          "scored_fill_price": 0.30, "pnl": 0.0}], prints, {tk: "yes"})["n_fills"] == 0


# --------------------------------------------------------------------------- #
# 9. discipline pins (Stop rules / prime directive)
# --------------------------------------------------------------------------- #
def test_module_has_no_network_or_order_surface():
    src = (REPO / "scripts" / "q56_s80_print_vwap_overshoot_maker_fade.py").read_text()
    # the order/auth markers are assembled from fragments on purpose: spelling them
    # literally would itself trip `invariants.py::order_endpoints_confined`, which scans
    # every file in the tree including this one.
    banned = ["requests", "urllib", "http.client", "socket",
              "create" + "_order", "api" + "_key", "KALSHI" + "_"]
    for token in banned:
        assert token not in src, f"offline probe must not reference {token!r}"


def test_no_synthetic_or_midpoint_is_ever_used_as_a_fill_price():
    tags = Q.PRICE_SOURCE_TAGS
    assert tags["fill_price"] == "real_bid"
    assert tags["settlement"] == "broker_truth"
    assert "synthetic" not in set(tags.values()) and "midpoint" not in set(tags.values())


def test_cadence_report_covers_the_three_nested_populations():
    tk_sport, tk_crypto = "KXTESTGAME-26JUL11AAABBB-AAA", "KXBTC-26JUL0621-T1"
    books = {tk_sport: [_snap(tk_sport, "2026-07-11T12:00:00Z", yes_bid=0.3),
                        _snap(tk_sport, "2026-07-11T12:30:00Z", yes_bid=0.3)],
             tk_crypto: [_snap(tk_crypto, "2026-07-11T12:00:00Z", yes_bid=0.3),
                         _snap(tk_crypto, "2026-07-11T15:00:00Z", yes_bid=0.3)]}
    got = Q.cadence_report(books, [tk_sport, tk_crypto])
    assert got["all_depth_tickers"]["n_tickers"] == 2
    assert got["traded_sports_game_tickers"]["n_tickers"] == 1
    assert got["traded_sports_game_tickers"]["pooled_gap_minutes"]["median"] == pytest.approx(30.0)
    # the same tape reads ~30min on one population and ~180min on another -- the L283
    # reconciliation: "the cadence" is a distribution, not a scalar
    assert got["all_depth_tickers"]["pooled_gap_minutes"]["p90"] > 100.0


# --------------------------------------------------------------------------- #
# 10. real-tape acceptance (FIXED slice; directional, survives tape growth)
# --------------------------------------------------------------------------- #
@_real_tape
def test_acceptance_the_fixed_slice_joins_prints_to_books_at_all():
    prints = Q.load_prints(str(TRADE_DAY))
    books = Q.load_books(str(DEPTH_DAY), wanted=prints.keys())
    assert len(prints) >= 5, "committed 07-11 trade day must hold sports prints"
    assert len(books) >= 1, "at least one traded sports ticker must have a book that day"
    for tk, prs in prints.items():
        assert Q.is_game_series(tk)
        assert all(p[3] in ("bid", "ask", "") for p in prs)


@_real_tape
def test_acceptance_prints_are_sorted_and_tie_broken_by_trade_id_not_read_order():
    prints = Q.load_prints(str(TRADE_DAY))
    for prs in prints.values():
        keys = [(p[0], p[4]) for p in prs]
        assert keys == sorted(keys)


# Loading the full committed depth tape is the expensive step; every acceptance test below
# shares ONE load and ONE probe run through module-scoped fixtures. A fresh run is still
# exercised (the reproducibility test does its own two runs over a single day-file).
@pytest.fixture(scope="module")
def full_tape():
    return Q.load_prints(), Q.load_books()


@pytest.fixture(scope="module")
def payload():
    return Q.run(n_boot=2000, with_grid=False)


@_real_tape
def test_acceptance_book_cadence_on_traded_sports_tickers_is_bimodal_not_a_scalar(full_tape):
    """The L283 reconciliation, pinned on committed tape: the traded-sports depth revisit
    interval has a ~30-min lower mode AND a ~3-hour upper mode. Both published figures are
    correct statistics of the SAME distribution, so neither may be quoted as 'the cadence'."""
    prints, books_all = full_tape
    rep = Q.cadence_report(books_all, prints.keys())
    sports = rep["traded_sports_game_tickers"]["pooled_gap_minutes"]
    assert sports["n"] > 500
    assert 20.0 <= sports["median"] <= 45.0, "lower mode is sub-hourly"
    assert sports["p75"] >= 120.0, "upper mode is multi-hour -- the graveyard's ~3h figure"


@_real_tape
def test_acceptance_headline_verdict_is_dead_and_is_not_a_data_adequacy_death(payload):
    """HARD pin of the recorded verdict (2026-08-10). The population clears the L41 game
    floor, so this is a CI falsification, not an adequacy refusal -- if a future edit turns
    this ALIVE, or silently drops the population below the floor, this test must fail."""
    assert payload["verdict"] == "DEAD"
    assert "K1_overshoot_within_maker_fee" in payload["kill_conditions_fired"]
    assert payload["fill"]["n_games_with_fill"] >= Q.MIN_CI_UNITS
    assert payload["branch_all_candidates"]["admissible"]["admissible"] is True
    assert payload["branch_all_candidates"]["mean"] < 0
    assert payload["gate_K1_overshoot_vs_maker_fee"]["mean"] < 0
    assert payload["fill"]["fills_traceable_to_broker_truth_print"] == payload["fill"]["n_fills"]


@_real_tape
def test_acceptance_the_registered_direction_is_the_wrong_sign_on_this_tape(full_tape):
    """The load-bearing economic fact: on committed tape the LEADING side's prints sit BELOW
    settlement and the TRAILING side's sit ABOVE it (favourite-longshot bias) -- the exact
    opposite of S80's registered premise that the leader is chased ABOVE fair."""
    prints, _ = full_tape
    results, _cov = Q.settlement_map(prints.keys())
    rows = Q.overshoot_rows(prints, results)
    lead = [r["overshoot"] for r in rows if r["chased_side"] == "yes"]
    trail = [r["overshoot"] for r in rows if r["chased_side"] == "no"]
    assert len(lead) >= 10 and len(trail) >= 10
    assert sum(lead) / len(lead) < -0.05, "leading-side prints settle ABOVE their own VWAP"
    assert sum(trail) / len(trail) > +0.05, "trailing-side prints settle BELOW their own VWAP"


@_real_tape
def test_acceptance_the_mirror_leg_is_not_an_edge_either(payload):
    """Guards the obvious bad inference from the row above: the sign-flip does NOT rescue the
    family. Resting on the chased side straddles zero net of the maker fee."""
    mirror = payload["mirror_leg_DESCRIPTIVE_ONLY"]["branch_all_candidates"]
    assert mirror["verdict"].startswith("DEAD")
    assert mirror["clears_tick_magnitude"] is False


@_real_tape
def test_acceptance_run_is_reproducible_under_a_fixed_seed():
    kw = dict(trades_glob=str(TRADE_DAY), depth_glob=str(DEPTH_DAY),
              n_boot=500, seed=42, with_grid=False)
    a, b = Q.run(**kw), Q.run(**kw)
    assert a["branch_all_candidates"]["ci95"] == b["branch_all_candidates"]["ci95"]
    assert a["gate_K1_overshoot_vs_maker_fee"]["ci95"] == b["gate_K1_overshoot_vs_maker_fee"]["ci95"]
