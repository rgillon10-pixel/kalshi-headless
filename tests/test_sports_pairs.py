"""Sports moneyline paired-odds capture: ticker parsing, moneyline-title filter,
de-vig math, and the same bitemporal/completeness discipline test_capture_bitemporal.py
exercises for weather — offline via an injected fake client, no network.
"""
from __future__ import annotations

import json

import pytest

from collection import sports_pairs as sp


# --------------------------------------------------------------------------- #
# ticker parsing
# --------------------------------------------------------------------------- #
def test_parses_soccer_3way_ticker():
    parsed = sp.parse_event_ticker("KXWCGAME-26JUL09FRAMAR-FRA")
    assert parsed == ("KXWCGAME", "26JUL09FRAMAR", "FRA")


def test_parses_baseball_2way_ticker():
    parsed = sp.parse_event_ticker("KXMLBGAME-26JUL111410ATHCWS-CWS")
    assert parsed == ("KXMLBGAME", "26JUL111410ATHCWS", "CWS")


def test_rejects_malformed_ticker():
    assert sp.parse_event_ticker("KXWCGAME26JUL09FRAMARFRA") is None
    assert sp.parse_event_ticker("KXWCGAME-26JUL09-FRA-MAR") is None


# --------------------------------------------------------------------------- #
# moneyline title filter — must admit real moneyline titles, reject props
# --------------------------------------------------------------------------- #
def test_moneyline_title_filter_admits_vs_winner_shape():
    assert sp.is_moneyline_market("Argentina vs Switzerland Winner?")
    assert sp.is_moneyline_market("A's vs Chicago WS Winner?")
    assert sp.is_moneyline_market("Los Angeles A vs Minnesota Winner?")


def test_moneyline_title_filter_rejects_prop_titles():
    assert not sp.is_moneyline_market("World Cup Teams in Game")
    assert not sp.is_moneyline_market("Will Norway play Switzerland in the Semifinal?")
    assert not sp.is_moneyline_market("First Home Game Opponent")


# --------------------------------------------------------------------------- #
# de-vig math — pure functions, no odds API needed to test
# --------------------------------------------------------------------------- #
def test_devig_two_way_sums_to_one():
    fair_a, fair_b = sp.devig_two_way(0.55, 0.55)  # 10% overround, symmetric
    assert fair_a == pytest.approx(0.5)
    assert fair_b == pytest.approx(0.5)
    assert fair_a + fair_b == pytest.approx(1.0)


def test_devig_two_way_preserves_relative_odds():
    fair_a, fair_b = sp.devig_two_way(0.60, 0.50)
    assert fair_a + fair_b == pytest.approx(1.0)
    assert fair_a > fair_b  # favorite stays the favorite after de-vig


def test_devig_two_way_rejects_nonpositive_sum():
    with pytest.raises(ValueError):
        sp.devig_two_way(0.0, 0.0)


def test_devig_n_way_sums_to_one():
    fair = sp.devig_n_way([0.45, 0.35, 0.25])  # 3-way soccer, 5% overround
    assert sum(fair) == pytest.approx(1.0)
    assert fair[0] > fair[1] > fair[2]  # ordering preserved


# --------------------------------------------------------------------------- #
# odds_status — honest BLOCKED(key) reporting, never invents a line
# --------------------------------------------------------------------------- #
def test_odds_status_no_key(monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    assert sp.odds_status() == "no_key"


def test_odds_status_with_key(monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "fake-test-key")
    assert sp.odds_status() == "fetched"


# --------------------------------------------------------------------------- #
# end-to-end capture (offline fake client) — bitemporal + completeness discipline
# --------------------------------------------------------------------------- #
class FakeClient:
    """Minimal stand-in for validation.v3_market.Kalshi — only the read-only methods
    sports_pairs uses, served from in-memory fixtures. No network, no clock."""

    base = "https://fake.test"

    def __init__(self, series, series_markets, books, fail_text=()):
        self.series = series                       # [{"ticker":..,"tags":[..]}]
        self.series_markets = series_markets        # {series_ticker: [{"ticker","title"},...]}
        self.books = books                          # {market_ticker: orderbook_fp dict}
        self.fail_text = set(fail_text)

    def series_by_category(self, category):
        return self.series

    def open_markets(self, series_ticker):
        return self.series_markets.get(series_ticker, [])

    def get_text(self, path):
        ticker = path.split("/markets/", 1)[1].rsplit("/orderbook", 1)[0]
        if ticker in self.fail_text:
            raise RuntimeError(f"simulated fetch failure: {ticker}")
        return json.dumps({"orderbook_fp": self.books[ticker]})


_BOOK_FRA = {"yes_dollars": [["0.61", "100"]], "no_dollars": [["0.38", "75"]]}
_BOOK_MAR = {"yes_dollars": [["0.14", "50"]], "no_dollars": [["0.85", "60"]]}
_BOOK_TIE = {"yes_dollars": [["0.23", "40"]], "no_dollars": [["0.75", "45"]]}

_SOCCER_SERIES = [{"ticker": "KXWCGAME", "tags": ["Soccer"]}]
_SOCCER_MARKETS = {
    "KXWCGAME": [
        {"ticker": "KXWCGAME-26JUL09FRAMAR-FRA", "title": "France vs Morocco Winner?"},
        {"ticker": "KXWCGAME-26JUL09FRAMAR-MAR", "title": "France vs Morocco Winner?"},
        {"ticker": "KXWCGAME-26JUL09FRAMAR-TIE", "title": "France vs Morocco Winner?"},
    ]
}
_SOCCER_BOOKS = {
    "KXWCGAME-26JUL09FRAMAR-FRA": _BOOK_FRA,
    "KXWCGAME-26JUL09FRAMAR-MAR": _BOOK_MAR,
    "KXWCGAME-26JUL09FRAMAR-TIE": _BOOK_TIE,
}


def _lines(store, day):
    path = store / f"dt={day}.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def test_complete_capture_emits_valid_signed_manifest(tmp_path, monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    client = FakeClient(_SOCCER_SERIES, _SOCCER_MARKETS, _SOCCER_BOOKS)
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_events"] == 1 and summary["n_complete"] == 1
    assert summary["total_outcomes"] == 3
    assert summary["odds_status"] == "no_key"

    lines = _lines(tmp_path, summary["day"])
    assert len(lines) == 1
    m = lines[0]
    assert sp.validate_manifest(m) == [], sp.validate_manifest(m)
    assert m["series"] == "KXWCGAME" and m["event"] == "26JUL09FRAMAR"
    assert m["sport"] == "Soccer"
    assert m["as_of"] == m["captured_at"] and m["as_of"]
    assert m["warmup"] is True
    assert m["completeness_ok"] is True
    assert m["n_outcomes"] == m["expected_outcomes"] == 3
    assert m["odds_status"] == "no_key"
    assert sp.verify_signature(m)
    assert sorted(m["outcomes"]) == sorted(o["ticker"] for o in m["snapshots"])
    for o in m["snapshots"]:
        assert o["source_tag"] == "real_ask"


def test_dropped_outcome_lowers_completeness_not_hidden(tmp_path):
    client = FakeClient(_SOCCER_SERIES, _SOCCER_MARKETS, _SOCCER_BOOKS,
                        fail_text={"KXWCGAME-26JUL09FRAMAR-TIE"})
    summary = sp.run(client=client, store=tmp_path)
    m = _lines(tmp_path, summary["day"])[0]
    assert sp.validate_manifest(m) == [], sp.validate_manifest(m)
    assert m["completeness_ok"] is False
    assert m["n_outcomes"] == 2 and m["expected_outcomes"] == 3
    assert summary["n_complete"] == 0


def test_degenerate_event_emits_no_line_but_is_recorded(tmp_path):
    client = FakeClient(
        _SOCCER_SERIES,
        {"KXWCGAME": [{"ticker": "KXWCGAME-26JUL09FRAMAR-FRA", "title": "France vs Morocco Winner?"}]},
        _SOCCER_BOOKS,
        fail_text={"KXWCGAME-26JUL09FRAMAR-FRA"},
    )
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_events"] == 0 and summary["n_degenerate"] == 1
    assert _lines(tmp_path, summary["day"]) == []


def test_non_moneyline_markets_are_excluded_even_in_a_game_series():
    client = FakeClient(
        _SOCCER_SERIES,
        {"KXWCGAME": _SOCCER_MARKETS["KXWCGAME"] +
         [{"ticker": "KXWCGAME-26JUL09FRAMAR-PROP", "title": "World Cup Teams in Game"}]},
        _SOCCER_BOOKS,
    )
    events, _errs = sp.discover_events(client)
    assert len(events) == 1
    ((_series, _event), ev), = events.items()
    assert len(ev["outcomes"]) == 3  # the PROP market never enters the group


def test_2way_baseball_event_grouping(tmp_path):
    series = [{"ticker": "KXMLBGAME", "tags": ["Baseball"]}]
    markets = {"KXMLBGAME": [
        {"ticker": "KXMLBGAME-26JUL111410ATHCWS-ATH", "title": "A's vs Chicago WS Winner?"},
        {"ticker": "KXMLBGAME-26JUL111410ATHCWS-CWS", "title": "A's vs Chicago WS Winner?"},
    ]}
    books = {
        "KXMLBGAME-26JUL111410ATHCWS-ATH": {"yes_dollars": [["0.45", "10"]], "no_dollars": [["0.58", "10"]]},
        "KXMLBGAME-26JUL111410ATHCWS-CWS": {"yes_dollars": [["0.55", "10"]], "no_dollars": [["0.48", "10"]]},
    }
    client = FakeClient(series, markets, books)
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_events"] == 1
    assert summary["total_outcomes"] == 2


# --------------------------------------------------------------------------- #
# discovery ordering — soccer first (World Cup time-sensitivity)
# --------------------------------------------------------------------------- #
def test_discover_moneyline_series_ranks_world_cup_first():
    series = [
        {"ticker": "KXNHLGAME", "tags": ["Hockey"]},
        {"ticker": "KXAFCONGAME", "tags": ["Soccer"]},   # soccer, but NOT World Cup
        {"ticker": "KXWCGAME", "tags": ["Soccer"]},      # World Cup — must rank first
        {"ticker": "KXNBAGAME", "tags": ["Basketball"]},
    ]
    client = FakeClient(series, {}, {})
    ranked = [s["ticker"] for s in sp.discover_moneyline_series(client)]
    assert ranked[0] == "KXWCGAME"
    assert ranked.index("KXAFCONGAME") < ranked.index("KXNHLGAME")
    assert ranked.index("KXAFCONGAME") < ranked.index("KXNBAGAME")


def test_discover_moneyline_series_excludes_non_game_series():
    series = [{"ticker": "KXWCGAME", "tags": ["Soccer"]}, {"ticker": "KXWCADVANCE", "tags": ["Soccer"]}]
    client = FakeClient(series, {}, {})
    ranked = [s["ticker"] for s in sp.discover_moneyline_series(client)]
    assert ranked == ["KXWCGAME"]
