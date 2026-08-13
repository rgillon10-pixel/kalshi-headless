"""Offline tests for the SEALED Q52/S78 toxicity-filtered maker probe.

Everything here runs against synthetic fixtures or committed tape; nothing touches a
network, a credential or an order path. The real-tree tests deliberately pin STRUCTURE
(shape, disjointness, source tags, seal emptiness) and never a live population COUNT — L341
is the lesson that a pin against a population which grows with every collector pass turns
red on correct data.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core.pricing import MAKER_FEE_RATE, TAKER_FEE_RATE, fee_per_contract
from scripts import q52_s78_toxicity_filtered_maker_probe as P
from scripts import q56_s80_print_vwap_overshoot_maker_fade as S80

UTC = timezone.utc


# --------------------------------------------------------------------------- #
# THE SEAL
# --------------------------------------------------------------------------- #
# The digest of the spec as pre-registered on 2026-08-13, BEFORE any settlement value was
# read. If this test fails, a spec constant moved: that is a re-pre-registration and must be
# declared in LOOP-QUEUE.md / kb/00-LOG.md, never repaired by re-pinning the number quietly.
PREREG_SHA256_AS_SEALED = (
    "1c2e422876ce44f5f8217dc98b4a7d8a43c9fcca04b1d8ddd1e8d3ff5bb218c2")


def test_preregistration_digest_is_pinned_to_the_sealed_spec():
    assert P.PREREG_SHA256 == PREREG_SHA256_AS_SEALED
    assert P.preregistration_sha256() == PREREG_SHA256_AS_SEALED


def test_preregistration_digest_tracks_values_not_key_order():
    spec = dict(P.PREREGISTRATION)
    reordered = {k: spec[k] for k in reversed(list(spec))}
    assert P.preregistration_sha256(reordered) == P.PREREG_SHA256
    changed = dict(spec)
    changed["wide_spread_min"] = 0.04
    assert P.preregistration_sha256(changed) != P.PREREG_SHA256


def test_sealed_report_key_scan_catches_a_settlement_derived_field():
    assert P.sealed_report_key_violations({"population": {"n_units": 3}}) == []
    assert P.sealed_report_key_violations({"population": {"mean_pnl": 1.0}}) == ["mean_pnl"]
    assert P.sealed_report_key_violations({"a": [{"ci95": [0, 1]}]}) == ["ci95"]


def test_sealed_report_key_scan_ignores_the_frozen_spec_subtree():
    # `verdict_rule` is the pre-registration's OWN field name, not a computed value; a guard
    # that fires on every run is a guard that gets switched off (L155).
    rep = {"preregistration": dict(P.PREREGISTRATION), "population": {"n_units": 1}}
    assert P.sealed_report_key_violations(rep) == []
    rep["verdict_leak"] = "ALIVE"
    assert P.sealed_report_key_violations(rep) == ["verdict_leak"]


# --------------------------------------------------------------------------- #
# ORIENTATION — the L279 wall
# --------------------------------------------------------------------------- #
def test_maker_leg_of_print_orientation():
    assert P.maker_leg_of_print(0.30, P.TAKER_BUYS) == ("no", pytest.approx(0.70))
    assert P.maker_leg_of_print(0.30, P.TAKER_SELLS) == ("yes", pytest.approx(0.30))
    assert P.maker_leg_of_print(0.30, "") is None
    assert P.maker_leg_of_print(0.30, "buy") is None


def test_maker_leg_agrees_with_the_shared_fill_predicate():
    """Structural cross-check against the imported fill model: whichever side a print is
    said to CONSUME is the side the maker was resting on, so the two must never disagree."""
    yes_price = 0.70
    # A taker on the BID lifts an offer -> consumes a resting NO bid at 1-0.70 = 0.30.
    assert S80.print_consumes("no", 0.30, yes_price, P.TAKER_BUYS) is True
    assert P.maker_leg_of_print(yes_price, P.TAKER_BUYS)[0] == "no"
    # A taker on the ASK hits a bid -> consumes a resting YES bid at 0.70.
    assert S80.print_consumes("yes", 0.70, yes_price, P.TAKER_SELLS) is True
    assert P.maker_leg_of_print(yes_price, P.TAKER_SELLS)[0] == "yes"


def test_maker_markout_signs():
    # Maker holds NO bought at 1-0.30: gains when the YES price FALLS.
    assert P.maker_markout("no", 0.30, 0.20) == pytest.approx(+0.10)
    assert P.maker_markout("no", 0.30, 0.45) == pytest.approx(-0.15)
    # Maker holds YES bought at 0.30: gains when the YES price RISES.
    assert P.maker_markout("yes", 0.30, 0.45) == pytest.approx(+0.15)
    assert P.maker_markout("yes", 0.30, 0.20) == pytest.approx(-0.10)


# --------------------------------------------------------------------------- #
# CELLS
# --------------------------------------------------------------------------- #
def test_cell_boundaries_are_the_pre_registered_ones():
    assert P.cell_of(0.50, 0.03) == ("rich", "wide")
    assert P.cell_of(0.4999, 0.0299) == ("cheap", "tight")
    assert P.cell_of(0.9, 0.01) == ("rich", "tight")
    assert P.cell_of(0.1, 0.25) == ("cheap", "wide")


def test_all_four_cells_are_enumerated_even_when_empty():
    table = P.train_cell_table({}, {}, [])
    assert sorted(table) == sorted(P.ALL_CELL_KEYS) == [
        "cheap/tight", "cheap/wide", "rich/tight", "rich/wide"]
    assert all(v["admitted"] is False and v["reasons"] == ["no_train_prints"]
               for v in table.values())


def test_quoted_spread_and_touch_reads_are_absent_not_zero():
    assert P.quoted_spread({"best_yes_ask": 0.71, "best_yes_bid": 0.67}) == pytest.approx(0.04)
    assert P.quoted_spread({"best_yes_bid": 0.67}) is None
    assert P.quoted_spread({}) is None
    snap = {"best_yes_bid": 0.67, "best_no_bid": 0.31,
            "yes_bids": [[0.67, 5.0]], "no_bids": [[0.31, 9.0]]}
    assert P.touch_bid(snap, "yes") == 0.67
    assert P.touch_bid(snap, "no") == 0.31
    assert P.touch_bid({}, "yes") is None
    assert P.ladder_of(snap, "yes") == [[0.67, 5.0]]
    assert P.ladder_of(snap, "no") == [[0.31, 9.0]]


# --------------------------------------------------------------------------- #
# MARKOUT MARK SELECTION
# --------------------------------------------------------------------------- #
def _p(minute, price, tbs="bid", tid="t"):
    return (datetime(2026, 7, 7, 12, 0, tzinfo=UTC) + timedelta(minutes=minute),
            price, 1.0, tbs, tid)


def test_mark_price_takes_the_last_print_inside_the_horizon():
    prints = [_p(0, 0.30), _p(5, 0.35), _p(29, 0.40), _p(31, 0.99)]
    assert P.mark_price_after(prints, 0) == pytest.approx(0.40)


def test_mark_price_is_none_when_nothing_lands_inside_the_horizon():
    prints = [_p(0, 0.30), _p(45, 0.90)]
    assert P.mark_price_after(prints, 0) is None
    assert P.mark_price_after(prints, 1) is None      # last print has no successor
    assert P.mark_price_after(prints, 99) is None     # out of range, no raise


def test_mark_price_ignores_an_exact_timestamp_tie():
    """Prints sharing the entry's own instant are not a later mark (L323: 48.5% of committed
    prints sit in an exact-timestamp tie, and pricing a markout off one of them measures
    nothing)."""
    prints = [_p(0, 0.30, tid="a"), _p(0, 0.80, tid="b")]
    assert P.mark_price_after(prints, 0) is None


# --------------------------------------------------------------------------- #
# BOOK JOIN
# --------------------------------------------------------------------------- #
def _snaps(minutes):
    base = datetime(2026, 7, 7, 12, 0, tzinfo=UTC)
    snaps = [{"captured_at": (base + timedelta(minutes=m)).isoformat()} for m in minutes]
    ts = [base + timedelta(minutes=m) for m in minutes]
    return snaps, ts


def test_snapshot_join_takes_the_last_at_or_before_and_refuses_a_stale_one():
    snaps, ts = _snaps([0, 60, 120])
    base = ts[0]
    assert P.snapshot_at_or_before(snaps, ts, base + timedelta(minutes=90)) is snaps[1]
    assert P.snapshot_at_or_before(snaps, ts, base + timedelta(minutes=120)) is snaps[2]
    assert P.snapshot_at_or_before(snaps, ts, base - timedelta(minutes=1)) is None
    # 241 minutes after the last snapshot -> past the declared 240-minute ceiling.
    assert P.snapshot_at_or_before(snaps, ts, ts[2] + timedelta(minutes=241)) is None
    assert P.snapshot_at_or_before([], [], base) is None


# --------------------------------------------------------------------------- #
# SPLIT + STRADDLE
# --------------------------------------------------------------------------- #
def test_split_rule_is_first_floor_half():
    assert P.split_days(["d1", "d2", "d3", "d4"]) == (["d1", "d2"], ["d3", "d4"])
    assert P.split_days(["d1", "d2", "d3"]) == (["d1"], ["d2", "d3"])
    assert P.split_days(["d1"]) == ([], ["d1"])
    assert P.split_days([]) == ([], [])
    assert P.split_days(["d2", "d1", "d2"]) == (["d1"], ["d2"])


def test_a_game_straddling_the_boundary_is_dropped_from_both_sides():
    gd = {"G_TRAIN": {"d1"}, "G_HOLD": {"d3"}, "G_BOTH": {"d1", "d3"}}
    out = P.assign_games(gd, ["d1", "d2"], ["d3", "d4"])
    assert out["train_games"] == {"G_TRAIN"}
    assert out["holdout_games"] == {"G_HOLD"}
    assert out["straddling_games"] == {"G_BOTH"}
    # disjointness is the mandate, so the three sets never intersect
    assert not (out["train_games"] & out["holdout_games"])


# --------------------------------------------------------------------------- #
# ADMISSION ARITHMETIC — the L5 fee wall
# --------------------------------------------------------------------------- #
def test_admission_requires_both_a_population_and_a_net_positive_markout():
    assert P.admit_cell(0, None, None)["reasons"] == ["no_train_prints"]
    thin = P.admit_cell(P.MIN_TRAIN_PRINTS_PER_CELL - 1, 0.50, 0.50)
    assert thin["admitted"] is False and "below_min_train_prints" in thin["reasons"]
    inside = P.admit_cell(1000, 0.005, 0.50)
    assert inside["admitted"] is False
    assert inside["reasons"] == ["markout_within_maker_fee"]
    good = P.admit_cell(1000, 0.05, 0.50)
    assert good["admitted"] is True and good["reasons"] == []
    assert good["net_of_fee"] == pytest.approx(0.05 - fee_per_contract(0.50, MAKER_FEE_RATE))


def test_admission_is_strictly_greater_than_the_fee_never_equal():
    fee = fee_per_contract(0.50, MAKER_FEE_RATE)
    assert P.admit_cell(1000, fee, 0.50)["admitted"] is False


def test_admission_charges_the_maker_rate_not_the_taker_rate():
    """A markout that clears the maker fee but not the taker fee must still be admitted —
    charging the taker rate to a resting order is L5's 4x overcharge."""
    price = 0.50
    maker_fee = fee_per_contract(price, MAKER_FEE_RATE)
    taker_fee = fee_per_contract(price, TAKER_FEE_RATE)
    assert maker_fee < taker_fee
    between = (maker_fee + taker_fee) / 2.0
    cell = P.admit_cell(1000, between, price)
    assert cell["fee"] == pytest.approx(maker_fee)
    assert cell["admitted"] is True


def test_module_never_names_the_taker_fee_rate():
    src = open(P.__file__).read()
    assert "TAKER_FEE_RATE" not in src


def test_module_imports_the_shared_fill_model_rather_than_copying_it():
    assert P.print_consumes is S80.print_consumes
    assert P.simulate_fill is S80.simulate_fill
    assert P.queue_ahead_at is S80.queue_ahead_at
    assert P.leg_pnl is S80.leg_pnl
    assert P.event_ticker_of is S80.event_ticker_of


# --------------------------------------------------------------------------- #
# FIXTURE TAPE — end-to-end over synthetic files
# --------------------------------------------------------------------------- #
GAME_TRAIN = "KXTESTGAME-26JUL07AAABBB"
GAME_HOLD = "KXTESTGAME-26JUL12CCCDDD"


def _write_tape(tmp_path, print_rows, book_rows):
    tdir, bdir = tmp_path / "trades", tmp_path / "depth"
    tdir.mkdir(), bdir.mkdir()
    by_day = {}
    for r in print_rows:
        by_day.setdefault(r["created_time"][:10], []).append(r)
    for day, rows in by_day.items():
        (tdir / f"dt={day}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows))
    by_day = {}
    for r in book_rows:
        by_day.setdefault(r["captured_at"][:10], []).append(r)
    for day, rows in by_day.items():
        (bdir / f"dt={day}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows))
    return str(tdir / "dt=*.jsonl"), str(bdir / "dt=*.jsonl")


def _print(ticker, ts, yes_price, tbs, tid, count=1.0):
    return {"ticker": ticker, "created_time": ts, "yes_price": yes_price,
            "count": count, "taker_book_side": tbs, "trade_id": tid,
            "price_source_tag": "broker_truth"}


def _book(ticker, ts, yes_bid, yes_ask, no_bid, yes_size=1.0, no_size=1.0):
    return {"ticker": ticker, "captured_at": ts, "best_yes_bid": yes_bid,
            "best_yes_ask": yes_ask, "best_no_bid": no_bid,
            "yes_bids": [[yes_bid, yes_size]], "no_bids": [[no_bid, no_size]],
            "price_source_tags": {"bids": "real_bid", "asks": "real_ask"}}


def _tiny_tape(tmp_path):
    """Two trade days, one train game, one holdout game, one fillable holdout interval."""
    prints, books = [], []
    tk_tr = GAME_TRAIN + "-AAA"
    # TRAIN: enough prints in cheap/tight to clear the 30-print floor, each with a later
    # mark 5 minutes on that shows the maker profiting.
    for i in range(40):
        base = f"2026-07-07T12:{i:02d}:00Z"
        mark = f"2026-07-07T12:{i:02d}:30Z"
        prints.append(_print(tk_tr, base, 0.80, P.TAKER_BUYS, f"tr{i}a"))
        prints.append(_print(tk_tr, mark, 0.60, P.TAKER_BUYS, f"tr{i}b"))
    books.append(_book(tk_tr, "2026-07-07T11:59:00Z", 0.79, 0.81, 0.19))
    # HOLDOUT: a cheap/tight book with a taker who hits our YES bid hard enough to clear it.
    tk_ho = GAME_HOLD + "-CCC"
    books.append(_book(tk_ho, "2026-07-12T12:00:00Z", 0.20, 0.22, 0.78, yes_size=1.0))
    books.append(_book(tk_ho, "2026-07-12T13:00:00Z", 0.20, 0.22, 0.78))
    prints.append(_print(tk_ho, "2026-07-12T12:30:00Z", 0.20, P.TAKER_SELLS, "ho1", count=50.0))
    return _write_tape(tmp_path, prints, books)


def _stub_resolution(results):
    class _M:
        def __init__(self, r): self.result = r

    def _fake(tickers, root="tape"):
        tickers = sorted(set(tickers))
        return SimpleNamespace(
            resolved={t: _M(results[t]) for t in tickers if t in results},
            requested=len(tickers), non_binary=[], listed_unsettled=[],
            unresolved=[t for t in tickers if t not in results],
            per_source_hits={"stub": len(results)}, sources_scanned=["stub"],
            sources_absent_on_disk=[])
    return _fake


def test_fixture_tape_admits_the_trained_cell_and_fills_the_holdout(tmp_path, monkeypatch):
    tg, bg = _tiny_tape(tmp_path)
    monkeypatch.setattr(P, "resolve_market_results",
                        _stub_resolution({GAME_HOLD + "-CCC": "yes"}))
    rep = P.run(trades_glob=tg, depth_glob=bg, population_only=True)
    pop = rep["population"]
    assert pop["split"]["train_days"] == ["2026-07-07"]
    assert pop["split"]["holdout_days"] == ["2026-07-12"]
    assert "cheap/tight" in pop["admitted_cells"]
    assert pop["n_candidates_scoreable"] >= 1
    assert pop["n_fills_scoreable"] >= 1
    assert rep["sealed"] is True and rep["sealed_key_violations"] == []
    assert "scoring" not in rep


def test_a_shut_gate_seals_and_computes_no_return(tmp_path, monkeypatch):
    tg, bg = _tiny_tape(tmp_path)
    monkeypatch.setattr(P, "resolve_market_results",
                        _stub_resolution({GAME_HOLD + "-CCC": "yes"}))

    def _boom(*a, **k):
        raise AssertionError("outcome value read while the gate was shut")
    monkeypatch.setattr(P, "outcome_map", _boom)
    monkeypatch.setattr(P, "score_rows", _boom)
    rep = P.run(trades_glob=tg, depth_glob=bg)     # one holdout game << the 10-unit floor
    assert rep["sealed"] is True
    assert "below_min_units" in rep["population"]["gate_reasons"]
    assert "scoring" not in rep
    assert rep["sealed_key_violations"] == []


def test_population_only_withholds_scoring_even_when_the_gate_is_open(tmp_path, monkeypatch):
    tg, bg = _tiny_tape(tmp_path)
    monkeypatch.setattr(P, "resolve_market_results",
                        _stub_resolution({GAME_HOLD + "-CCC": "yes"}))
    monkeypatch.setattr(P, "MIN_UNITS", 1)
    monkeypatch.setattr(P, "MIN_EXCLUSIVE_MINORITY_UNITS", 0)

    def _boom(*a, **k):
        raise AssertionError("scored under --population-only")
    monkeypatch.setattr(P, "outcome_map", _boom)
    rep = P.run(trades_glob=tg, depth_glob=bg, population_only=True)
    assert rep["sealed"] is True and "scoring" not in rep


# --------------------------------------------------------------------------- #
# SCORING
# --------------------------------------------------------------------------- #
def _row(**kw):
    base = {"ticker": "T", "unit": "U", "series": "S", "side": "yes", "cell": "cheap/tight",
            "rest_price": 0.20, "rest_price_source_tag": "real_bid", "quoted_spread": 0.02,
            "queue_ahead": 0.0, "consuming_volume": 0.0, "filled": False,
            "fill_trade_id": None, "t_rest": "x", "t_interval_end": "y"}
    base.update(kw)
    return base


def test_an_unfilled_candidate_scores_exactly_zero_and_claims_no_win():
    out = P.score_rows([_row(filled=False)], {"T": "yes"})
    assert out[0]["pnl"] == 0.0 and out[0]["won"] is None


def test_a_filled_candidate_is_priced_by_the_shared_maker_leg():
    out = P.score_rows([_row(filled=True, fill_trade_id="x")], {"T": "yes"})
    assert out[0]["pnl"] == pytest.approx(S80.leg_pnl("yes", 0.20, "yes"))
    assert out[0]["won"] is True
    loser = P.score_rows([_row(filled=True, fill_trade_id="x")], {"T": "no"})
    assert loser[0]["won"] is False
    assert loser[0]["pnl"] < 0     # the losing leg is fully priced, never dropped


def test_a_non_binary_result_is_dropped_not_scored_as_a_loss():
    assert P.score_rows([_row(filled=True)], {"T": "scalar"}) == []
    assert P.score_rows([_row(filled=True)], {}) == []


def test_every_scored_row_carries_a_real_bid_price_source_tag():
    out = P.score_rows([_row(filled=True), _row(filled=False)], {"T": "yes"})
    assert {r["rest_price_source_tag"] for r in out} == {"real_bid"}


def test_verdict_label_requires_both_a_positive_ci_and_the_tick_gate():
    alive = {"ci95": [0.02, 0.05], "clears_tick_magnitude": True,
             "admissibility": {"admissible": True}}
    assert P.verdict_label(alive) == "ALIVE"
    thin = dict(alive, ci95=[0.001, 0.05], clears_tick_magnitude=False)
    assert P.verdict_label(thin) == "DEAD"
    straddles = dict(alive, ci95=[-0.01, 0.05])
    assert P.verdict_label(straddles) == "DEAD"
    inadmissible = dict(alive, admissibility={"admissible": False})
    assert P.verdict_label(inadmissible) == "INADMISSIBLE"


# --------------------------------------------------------------------------- #
# CANDIDATE ENUMERATION GUARDS
# --------------------------------------------------------------------------- #
def test_candidates_are_refused_outside_the_admitted_cells_and_the_price_band(tmp_path):
    tk = GAME_HOLD + "-CCC"
    books = {tk: [_book(tk, "2026-07-12T12:00:00Z", 0.20, 0.22, 0.78),
                  _book(tk, "2026-07-12T13:00:00Z", 0.20, 0.22, 0.78)]}
    prints = {tk: []}
    assert P.holdout_candidates(prints, books, [GAME_HOLD], frozenset()) == []
    rows = P.holdout_candidates(prints, books, [GAME_HOLD], frozenset({"cheap/tight"}))
    assert {r["side"] for r in rows} == {"yes"}          # the NO touch (0.78) is rich/tight
    assert all(r["rest_price_source_tag"] == "real_bid" for r in rows)
    # price band: a 0.99 touch is outside [0.02, 0.98] and must not become a candidate
    books_edge = {tk: [_book(tk, "2026-07-12T12:00:00Z", 0.99, 1.00, 0.01),
                       _book(tk, "2026-07-12T13:00:00Z", 0.99, 1.00, 0.01)]}
    assert P.holdout_candidates(prints, books_edge, [GAME_HOLD],
                                frozenset(P.ALL_CELL_KEYS)) == []


def test_an_interval_wider_than_the_declared_ceiling_is_not_a_candidate():
    tk = GAME_HOLD + "-CCC"
    books = {tk: [_book(tk, "2026-07-12T00:00:00Z", 0.20, 0.22, 0.78),
                  _book(tk, "2026-07-12T05:00:00Z", 0.20, 0.22, 0.78)]}
    assert P.holdout_candidates({tk: []}, books, [GAME_HOLD],
                                frozenset({"cheap/tight"})) == []


def test_a_single_snapshot_ticker_yields_no_candidate():
    tk = GAME_HOLD + "-CCC"
    books = {tk: [_book(tk, "2026-07-12T12:00:00Z", 0.20, 0.22, 0.78)]}
    assert P.holdout_candidates({tk: []}, books, [GAME_HOLD],
                                frozenset({"cheap/tight"})) == []


def test_a_fill_always_traces_to_a_broker_truth_trade_id():
    tk = GAME_HOLD + "-CCC"
    books = {tk: [_book(tk, "2026-07-12T12:00:00Z", 0.20, 0.22, 0.78, yes_size=1.0),
                  _book(tk, "2026-07-12T13:00:00Z", 0.20, 0.22, 0.78)]}
    prints = {tk: [(datetime(2026, 7, 12, 12, 30, tzinfo=UTC), 0.20, 50.0,
                    P.TAKER_SELLS, "tid-42")]}
    rows = P.holdout_candidates(prints, books, [GAME_HOLD], frozenset({"cheap/tight"}))
    filled = [r for r in rows if r["filled"]]
    assert filled and all(r["fill_trade_id"] for r in filled)
    # a synthesised fill is unconstructible: no crossing print -> no fill
    rows_none = P.holdout_candidates({tk: []}, books, [GAME_HOLD],
                                     frozenset({"cheap/tight"}))
    assert all(r["filled"] is False and r["fill_trade_id"] is None for r in rows_none)


# --------------------------------------------------------------------------- #
# REAL-TREE ACCEPTANCE — structure only, never a live count (L341)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def real_tree_report():
    return P.run(population_only=True)


def test_real_tree_sealed_report_leaks_no_settlement_derived_key(real_tree_report):
    assert real_tree_report["sealed"] is True
    assert real_tree_report["sealed_key_violations"] == []
    assert "scoring" not in real_tree_report
    assert real_tree_report["network_calls"] == 0
    assert real_tree_report["fee_side"] == "maker"
    assert real_tree_report["price_source_tags"]["rest_price"] == "real_bid"


def test_real_tree_train_and_holdout_windows_are_disjoint(real_tree_report):
    split = real_tree_report["population"]["split"]
    assert set(split["train_days"]).isdisjoint(split["holdout_days"])
    assert split["n_train_games"] + split["n_holdout_games"] \
        + split["n_straddling_games_dropped"] == split["n_games_total"]


def test_real_tree_cell_table_is_complete_and_bounded(real_tree_report):
    pop = real_tree_report["population"]
    assert sorted(pop["train_cell_table"]) == sorted(P.ALL_CELL_KEYS)
    assert 0 <= pop["n_admitted_cells"] <= len(P.ALL_CELL_KEYS)
    assert set(pop["admitted_cells"]) <= set(P.ALL_CELL_KEYS)
    assert isinstance(pop["admissible"], bool)
