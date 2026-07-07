"""collection.orderbook_depth — full-depth L2 snapshot capture, fully offline (FakeClient,
no network). Covers: normal full capture (completeness_ok True), a dropped-ticker case
(completeness_ok False, drop recorded), empty ticker list no-op, source-tag values, the
JSONL line shape, dedupe, and the max_tickers truncation flag."""
from __future__ import annotations

import json

import pytest

from collection import orderbook_depth as od


# --------------------------------------------------------------------------- #
# FakeClient — serves raw orderbook JSON text from in-memory fixtures, no network/clock
# --------------------------------------------------------------------------- #
class FakeClient:
    base = "https://fake.test"

    def __init__(self, books_by_ticker=None, fail_tickers=()):
        self.books_by_ticker = books_by_ticker or {}
        self.fail_tickers = set(fail_tickers)
        self.calls = []

    def get_text(self, path, **params):
        # path is the fully-formatted "/markets/<ticker>/orderbook"
        self.calls.append(path)
        assert path.startswith("/markets/") and path.endswith("/orderbook")
        ticker = path[len("/markets/"):-len("/orderbook")]
        if ticker in self.fail_tickers:
            raise RuntimeError(f"simulated orderbook fetch failure: {ticker}")
        ob = self.books_by_ticker.get(ticker, {})
        return json.dumps({"orderbook_fp": ob})


def _ob(yes_levels, no_levels):
    """Raw Kalshi orderbook_fp: yes_dollars / no_dollars are [[price, size], ...] (bids only)."""
    return {"yes_dollars": yes_levels, "no_dollars": no_levels}


# --------------------------------------------------------------------------- #
# normal full-capture pass
# --------------------------------------------------------------------------- #
def test_run_full_capture_completeness_ok(tmp_path):
    books = {
        "KXWCGAME-A-USA": _ob([[0.40, 100], [0.39, 250]], [[0.58, 80], [0.57, 120]]),
        "KXBTC-26JUL0302-T69300": _ob([[0.20, 30]], [[0.79, 10]]),
    }
    client = FakeClient(books_by_ticker=books)
    summary = od.run(list(books), client=client, store=tmp_path)

    assert summary["n_expected"] == 2
    assert summary["n_captured"] == 2
    assert summary["n_lines"] == 2
    assert summary["completeness_ok"] is True
    assert summary["truncated"] is False
    assert summary["dropped"] == []

    recs = [json.loads(ln) for ln in
            (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()]
    assert {r["ticker"] for r in recs} == set(books)


def test_run_record_shape_and_depth_derivation(tmp_path):
    books = {"KXWCGAME-A-USA": _ob([[0.40, 100], [0.39, 250]], [[0.58, 80]])}
    client = FakeClient(books_by_ticker=books)
    summary = od.run(list(books), client=client, store=tmp_path)

    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["schema_version"] == "orderbook_depth.v1"
    assert rec["venue"] == "kalshi"
    assert rec["ticker"] == "KXWCGAME-A-USA"
    assert "capture_id" in rec and "captured_at" in rec and "raw_sha256" in rec
    # full ladders, best-first
    assert rec["yes_bids"] == [[0.40, 100], [0.39, 250]]
    assert rec["no_bids"] == [[0.58, 80]]
    assert rec["best_yes_bid"] == 0.40
    assert rec["best_no_bid"] == 0.58
    # asks are the complement of the opposite side's best bid (from normalize_snapshot)
    assert rec["best_yes_ask"] == pytest.approx(1 - 0.58)
    assert rec["best_no_ask"] == pytest.approx(1 - 0.40)
    assert rec["depth"] == 3  # 2 yes levels + 1 no level


def test_price_source_tags_are_real(tmp_path):
    books = {"T": _ob([[0.5, 1]], [[0.5, 1]])}
    client = FakeClient(books_by_ticker=books)
    summary = od.run(["T"], client=client, store=tmp_path)
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["price_source_tags"] == {"asks": "real_ask", "bids": "real_bid"}


# --------------------------------------------------------------------------- #
# a dropped-ticker fetch failure -> completeness_ok False, drop recorded (never absorbed)
# --------------------------------------------------------------------------- #
def test_run_dropped_ticker_lowers_completeness(tmp_path):
    books = {"GOOD": _ob([[0.4, 10]], [[0.5, 10]])}
    client = FakeClient(books_by_ticker=books, fail_tickers=["BAD"])
    summary = od.run(["GOOD", "BAD"], client=client, store=tmp_path)

    assert summary["n_expected"] == 2
    assert summary["n_captured"] == 1
    assert summary["completeness_ok"] is False
    assert summary["dropped"] == ["BAD"]
    # only the good ticker landed on tape
    recs = [json.loads(ln) for ln in
            (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()]
    assert [r["ticker"] for r in recs] == ["GOOD"]


# --------------------------------------------------------------------------- #
# empty ticker list — valid no-op, never builds a client / touches network
# --------------------------------------------------------------------------- #
def test_run_empty_tickers_is_noop_no_client():
    # client=None; if run() tried to build a real client it would need venue cfg / network.
    summary = od.run([], client=None)
    assert summary["n_expected"] == 0
    assert summary["n_captured"] == 0
    assert summary["n_lines"] == 0
    assert summary["completeness_ok"] is True
    assert summary["path"] is None


def test_run_dedupes_tickers(tmp_path):
    books = {"T": _ob([[0.5, 1]], [[0.5, 1]])}
    client = FakeClient(books_by_ticker=books)
    summary = od.run(["T", "T", "T"], client=client, store=tmp_path)
    assert summary["n_expected"] == 1
    assert summary["n_captured"] == 1
    assert client.calls == ["/markets/T/orderbook"]  # fetched once


# --------------------------------------------------------------------------- #
# memory cap (lesson L10): max_tickers truncates and flags honestly
# --------------------------------------------------------------------------- #
def test_run_truncation_flag(tmp_path):
    books = {f"T{i}": _ob([[0.5, 1]], [[0.5, 1]]) for i in range(5)}
    client = FakeClient(books_by_ticker=books)
    summary = od.run(list(books), client=client, store=tmp_path, max_tickers=2)
    assert summary["truncated"] is True
    assert summary["n_expected"] == 2
    # truncation is an honest incompleteness — never a silent full-coverage claim
    assert summary["completeness_ok"] is False


def test_run_missing_book_still_captures_empty_ladders(tmp_path):
    # a ticker with an empty orderbook_fp is a valid (empty) book, not a drop
    client = FakeClient(books_by_ticker={"EMPTY": {}})
    summary = od.run(["EMPTY"], client=client, store=tmp_path)
    assert summary["n_captured"] == 1
    assert summary["completeness_ok"] is True
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["yes_bids"] == [] and rec["no_bids"] == []
    assert rec["depth"] == 0
    assert rec["best_yes_ask"] is None and rec["best_no_ask"] is None
