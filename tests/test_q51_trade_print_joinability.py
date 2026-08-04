"""Q51 join-ability probe — data-adequacy measurement over committed tape.

Fully offline: every test builds its own tiny two-family fixture on tmp_path, so the pure
`joinability()` arithmetic is pinned independently of the real tape. This probe produces no
P&L and no CI — these tests guard the ADEQUACY arithmetic (coverage denominators, honest
abstention, interval boundary handling), which is what a wrong number here would corrupt.
"""
from __future__ import annotations

import json

from scripts import q51_trade_print_joinability as q51


def snap(ts, bid=0.40, ask=0.60):
    return {"ts": ts, "best_yes_bid": bid, "best_yes_ask": ask}


def prt(ts, price=0.50, side="bid"):
    return {"ts": ts, "yes_price": price, "count": 1.0, "taker_book_side": side}


# --------------------------------------------------------------------------- #
# timestamp parsing
# --------------------------------------------------------------------------- #
def test_parse_ts_accepts_both_rfc3339_spellings():
    assert q51.parse_ts("2026-08-03T00:00:00Z") == q51.parse_ts("2026-08-03T00:00:00+00:00")


def test_parse_ts_returns_none_on_garbage():
    for bad in ("", None, "nope", 12):
        assert q51.parse_ts(bad) is None


# --------------------------------------------------------------------------- #
# interval coverage — the load-bearing measurement
# --------------------------------------------------------------------------- #
def test_interval_coverage_counts_pairs_not_snapshots():
    snaps = {"A": [snap(0), snap(10), snap(20)]}
    prints = {"A": [prt(5)]}
    r = q51.joinability(snaps, prints, ["A"])
    assert r["n_intervals"] == 2               # 3 snapshots -> 2 intervals
    assert r["n_intervals_with_print"] == 1
    assert r["interval_coverage"] == 0.5


def test_single_snapshot_ticker_contributes_zero_intervals_not_a_guess():
    snaps = {"A": [snap(0)]}
    prints = {"A": [prt(5)]}
    r = q51.joinability(snaps, prints, ["A"])
    assert r["n_intervals"] == 0
    assert r["interval_coverage"] is None      # honest abstention, never 0.0
    assert r["n_tickers_with_prints"] == 1     # the print is still counted


def test_interval_is_half_open_lower_exclusive_upper_inclusive():
    snaps = {"A": [snap(0), snap(10)]}
    assert q51.joinability(snaps, {"A": [prt(0)]}, ["A"])["n_intervals_with_print"] == 0
    assert q51.joinability(snaps, {"A": [prt(10)]}, ["A"])["n_intervals_with_print"] == 1


def test_print_outside_every_interval_is_counted_but_covers_nothing():
    snaps = {"A": [snap(10), snap(20)]}
    r = q51.joinability(snaps, {"A": [prt(50)]}, ["A"])
    assert r["n_prints"] == 1 and r["n_intervals_with_print"] == 0


# --------------------------------------------------------------------------- #
# ticker coverage / missing-side accounting
# --------------------------------------------------------------------------- #
def test_ticker_with_book_but_no_prints_lowers_coverage():
    snaps = {"A": [snap(0), snap(10)], "B": [snap(0), snap(10)]}
    r = q51.joinability(snaps, {"A": [prt(5)]}, ["A", "B"])
    assert r["n_tickers"] == 2 and r["n_tickers_with_book"] == 2
    assert r["n_tickers_with_prints"] == 1 and r["ticker_coverage"] == 0.5


def test_ticker_absent_from_book_is_reported_not_dropped():
    r = q51.joinability({}, {"A": [prt(5)]}, ["A"])
    assert r["n_tickers"] == 1 and r["n_tickers_with_book"] == 0
    assert r["n_tickers_with_prints"] == 1


def test_empty_population_abstains_everywhere():
    r = q51.joinability({}, {}, [])
    assert r["ticker_coverage"] is None and r["interval_coverage"] is None
    assert r["price_consistency"] is None


# --------------------------------------------------------------------------- #
# side split + price-consistency cross-check
# --------------------------------------------------------------------------- #
def test_taker_book_side_counts_split_bid_and_ask():
    snaps = {"A": [snap(0), snap(10)]}
    prints = {"A": [prt(1, side="bid"), prt(2, side="ask"), prt(3, side="bid")]}
    r = q51.joinability(snaps, prints, ["A"])
    assert r["taker_book_side_counts"] == {"ask": 1, "bid": 2}


def test_missing_side_is_labelled_not_silently_bucketed():
    snaps = {"A": [snap(0), snap(10)]}
    r = q51.joinability(snaps, {"A": [{"ts": 1, "yes_price": 0.5, "taker_book_side": None}]},
                        ["A"])
    assert r["taker_book_side_counts"] == {"__missing__": 1}


def test_price_consistency_uses_the_preceding_snapshot_quote():
    snaps = {"A": [snap(0, bid=0.40, ask=0.60), snap(10)]}
    prints = {"A": [prt(1, price=0.50), prt(2, price=0.95)]}
    r = q51.joinability(snaps, prints, ["A"])
    assert r["n_price_checked"] == 2
    assert r["n_price_inside_prior_quote"] == 1
    assert r["price_consistency"] == 0.5


def test_price_check_skips_snapshot_with_no_quote_rather_than_scoring_it():
    snaps = {"A": [snap(0, bid=None, ask=None), snap(10)]}
    r = q51.joinability(snaps, {"A": [prt(1)]}, ["A"])
    assert r["n_price_checked"] == 0 and r["price_consistency"] is None
    assert r["n_intervals_with_print"] == 1     # coverage still counts the print


# --------------------------------------------------------------------------- #
# loaders
# --------------------------------------------------------------------------- #
def test_load_prints_filters_sorts_and_skips_malformed(tmp_path):
    p = tmp_path / "dt=2026-08-03.jsonl"
    p.write_text("\n".join([
        json.dumps({"ticker": "A", "created_time": "2026-08-03T02:00:00Z", "yes_price": 0.5,
                    "taker_book_side": "bid"}),
        json.dumps({"ticker": "A", "created_time": "2026-08-03T01:00:00Z", "yes_price": 0.4,
                    "taker_book_side": "ask"}),
        json.dumps({"ticker": "B", "created_time": "2026-08-03T01:00:00Z"}),
        "not json",
        json.dumps({"ticker": "A", "created_time": "bad"}),
    ]) + "\n")
    got = q51.load_prints(p, {"A"})
    assert list(got) == ["A"]
    assert [r["yes_price"] for r in got["A"]] == [0.4, 0.5]     # sorted by event time


def test_load_snapshots_sorts_by_capture_time(tmp_path):
    p = tmp_path / "dt=2026-08-03.jsonl"
    p.write_text("\n".join([
        json.dumps({"ticker": "A", "captured_at": "2026-08-03T09:00:00+00:00",
                    "best_yes_bid": 0.4, "best_yes_ask": 0.6}),
        json.dumps({"ticker": "A", "captured_at": "2026-08-03T06:00:00+00:00",
                    "best_yes_bid": 0.3, "best_yes_ask": 0.5}),
    ]) + "\n")
    got = q51.load_snapshots(p, {"A"})
    assert [r["best_yes_bid"] for r in got["A"]] == [0.3, 0.4]


def test_loaders_on_absent_file_return_empty(tmp_path):
    assert q51.load_prints(tmp_path / "nope.jsonl") == {}
    assert q51.load_snapshots(tmp_path / "nope.jsonl") == {}
