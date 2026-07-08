"""Sports moneyline collector: ticker grammar, group filtering, de-vig math, and a full
offline capture pass (FakeClient — no network) with honest completeness on a dropped leg."""
from __future__ import annotations

import json

import pytest

from collection import sports_pairs as sp


# --------------------------------------------------------------------------- #
# ticker parsing
# --------------------------------------------------------------------------- #
def test_parse_three_way_soccer_leg():
    assert sp.parse_market_ticker("KXWCGAME-26JUL11ARGSUI-ARG") == \
        ("KXWCGAME", "26JUL11ARGSUI", "ARG")
    assert sp.parse_market_ticker("KXWCGAME-26JUL11ARGSUI-TIE") == \
        ("KXWCGAME", "26JUL11ARGSUI", "TIE")


def test_parse_two_way_no_draw_leg():
    assert sp.parse_market_ticker("KXNFLGAME-26AUG15DALSEA-SEA") == \
        ("KXNFLGAME", "26AUG15DALSEA", "SEA")


def test_parse_lowercase_ticker_still_matches():
    # Kalshi tickers are uppercase on the wire; the parser normalizes defensively.
    assert sp.parse_market_ticker("kxnflgame-26aug15dalsea-sea") == \
        ("KXNFLGAME", "26AUG15DALSEA", "SEA")


@pytest.mark.parametrize("ticker", [
    "KXWCGAME",                    # no dashes at all
    "KXWCGAME-26JUL11ARGSUI",      # missing leg segment
    "KX-WC-GAME-26JUL11ARGSUI-ARG",  # extra dash segments
    "",
])
def test_parse_rejects_malformed_tickers(ticker):
    assert sp.parse_market_ticker(ticker) is None


# --------------------------------------------------------------------------- #
# moneyline group filtering (2-way / 3-way only; props dropped)
# --------------------------------------------------------------------------- #
def test_filter_moneyline_keeps_two_and_three_way_drops_singleton():
    groups = {
        ("KXWCGAME", "26JUL11ARGSUI"): {"legs": {"ARG": {}, "SUI": {}, "TIE": {}}},   # 3-way
        ("KXNFLGAME", "26AUG15DALSEA"): {"legs": {"DAL": {}, "SEA": {}}},              # 2-way
        ("KXWCTEAMSINGAME", "26USAENG"): {"legs": {"Y": {}}},                          # prop
    }
    kept = sp._filter_moneyline(groups)
    assert set(kept) == {("KXWCGAME", "26JUL11ARGSUI"), ("KXNFLGAME", "26AUG15DALSEA")}


# --------------------------------------------------------------------------- #
# de-vig math (pure; no network)
# --------------------------------------------------------------------------- #
def test_devig_two_way_removes_vig_to_sum_one():
    # -110/-110 American ~= 1.909 decimal each -> raw implied 1.048/1.048 = 104.8% (4.8% vig)
    probs = sp.devig_probs([1.909, 1.909])
    assert probs == pytest.approx([0.5, 0.5], abs=1e-6)
    assert sum(probs) == pytest.approx(1.0, abs=1e-9)


def test_devig_asymmetric_favorite_underdog():
    # heavy favorite (short odds) vs underdog (long odds)
    probs = sp.devig_probs([1.20, 6.0])
    assert sum(probs) == pytest.approx(1.0, abs=1e-9)
    assert probs[0] > probs[1]  # favorite (lower decimal odds) gets the higher fair prob


def test_devig_three_way_soccer_sums_to_one():
    probs = sp.devig_probs([2.5, 3.4, 3.0])
    assert sum(probs) == pytest.approx(1.0, abs=1e-9)
    assert len(probs) == 3


def test_devig_rejects_empty():
    with pytest.raises(ValueError):
        sp.devig_probs([])


def test_devig_rejects_odds_at_or_below_one():
    with pytest.raises(ValueError):
        sp.devig_probs([1.0, 5.0])
    with pytest.raises(ValueError):
        sp.devig_probs([0.5, 5.0])


# --------------------------------------------------------------------------- #
# full offline capture pass — FakeClient, no network (mirrors test_capture_bitemporal.py)
# --------------------------------------------------------------------------- #
class FakeClient:
    base = "https://fake.test"

    def __init__(self, series_markets, books, fail_text=()):
        self.series_markets = series_markets   # {series_ticker: [market_dict, ...]}
        self.books = books                     # {ticker: orderbook_fp dict}
        self.fail_text = set(fail_text)

    def series_by_category(self, category):
        return [{"ticker": s} for s in self.series_markets]

    def open_markets(self, series_ticker):
        return self.series_markets[series_ticker]

    def get_text(self, path):
        ticker = path.split("/markets/", 1)[1].rsplit("/orderbook", 1)[0]
        if ticker in self.fail_text:
            raise RuntimeError(f"simulated fetch failure: {ticker}")
        return json.dumps({"orderbook_fp": self.books[ticker]})


_BOOK = {"yes_dollars": [["0.40", "10"]], "no_dollars": [["0.55", "10"]]}


def _three_way_series():
    return {
        "KXWCGAME": [
            {"ticker": "KXWCGAME-26JUL11ARGSUI-ARG", "title": "Argentina vs Switzerland"},
            {"ticker": "KXWCGAME-26JUL11ARGSUI-SUI", "title": "Argentina vs Switzerland"},
            {"ticker": "KXWCGAME-26JUL11ARGSUI-TIE", "title": "Argentina vs Switzerland"},
        ],
        # single-leg prop under a *GAME series -> must be dropped, not captured as a "pair"
        "KXWCTEAMSINGAME": [
            {"ticker": "KXWCTEAMSINGAME-26USAENG-Y", "title": "USA vs England prop"},
        ],
    }


def test_run_captures_complete_three_way_group(tmp_path):
    markets = _three_way_series()
    books = {m["ticker"]: _BOOK for legs in markets.values() for m in legs}
    client = FakeClient(markets, books)

    summary = sp.run(client=client, store=tmp_path)

    assert summary["n_groups"] == 1          # the singleton prop group was filtered out
    assert summary["n_complete"] == 1
    assert summary["n_legs_captured"] == 3

    out_files = list((tmp_path / f"dt={summary['day']}").glob("*.jsonl"))
    assert len(out_files) == 1
    lines = [json.loads(l) for l in out_files[0].read_text().splitlines()]
    assert len(lines) == 1
    rec = lines[0]
    assert rec["series"] == "KXWCGAME" and rec["event_code"] == "26JUL11ARGSUI"
    assert rec["completeness_ok"] is True
    assert rec["expected_legs"] == 3 and rec["captured_legs"] == 3
    assert {leg["leg"] for leg in rec["legs"]} == {"ARG", "SUI", "TIE"}
    assert all(leg["source_tag"] == "real_ask" for leg in rec["legs"])
    # bracket_sum uses the sanctioned core.pricing site, not hand arithmetic here
    assert rec["bracket_sum"] == pytest.approx(0.45 * 3, abs=1e-9)
    assert rec["bracket_sum_source_tag"] == "real_ask"


def test_run_records_honest_incompleteness_on_dropped_leg(tmp_path):
    markets = _three_way_series()
    books = {m["ticker"]: _BOOK for legs in markets.values() for m in legs}
    client = FakeClient(markets, books, fail_text=["KXWCGAME-26JUL11ARGSUI-TIE"])

    summary = sp.run(client=client, store=tmp_path)

    assert summary["n_groups"] == 1
    assert summary["n_complete"] == 0  # the drop must NOT masquerade as complete

    out_files = list((tmp_path / f"dt={summary['day']}").glob("*.jsonl"))
    rec = json.loads(out_files[0].read_text().splitlines()[0])
    assert rec["completeness_ok"] is False
    assert rec["captured_legs"] == 2 and rec["expected_legs"] == 3
    assert rec["dropped_legs"] == ["TIE"]
    assert rec["bracket_sum"] is None  # never quote a bracket_sum on a partial capture


def test_run_odds_status_no_key_when_env_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    markets = _three_way_series()
    books = {m["ticker"]: _BOOK for legs in markets.values() for m in legs}
    client = FakeClient(markets, books)

    summary = sp.run(client=client, store=tmp_path)
    assert summary["odds_status"] == "no_key"

    out_files = list((tmp_path / f"dt={summary['day']}").glob("*.jsonl"))
    rec = json.loads(out_files[0].read_text().splitlines()[0])
    assert rec["odds"] is None
    assert rec["odds_status"] == "no_key"
