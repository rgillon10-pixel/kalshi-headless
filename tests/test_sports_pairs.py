"""Sports moneyline capture — ticker parsing + offline (no-network) pass tests.

Mirrors tests/test_capture_bitemporal.py's discipline: collection.sports_pairs.run()
is exercised fully offline via an injected fake client writing to a tmp store. The
property under test is the same one capture_orderbooks proved: a dropped/incomplete
book lowers completeness, it is never hidden or faked as a full bracket.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from collection import sports_pairs as sp


# --------------------------------------------------------------------------- #
# ticker parsing — samples pulled from the live API across sports (2026-07-09)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ticker,event_ticker,outcome", [
    ("KXWCGAME-26JUL09FRAMAR-FRA", "KXWCGAME-26JUL09FRAMAR", "FRA"),
    ("KXWCGAME-26JUL11ARGSUI-TIE", "KXWCGAME-26JUL11ARGSUI", "TIE"),
    ("KXNFLGAME-26AUG15DALSEA-SEA", "KXNFLGAME-26AUG15DALSEA", "SEA"),
    ("KXMLBGAME-26JUL111905KCBAL-KC", "KXMLBGAME-26JUL111905KCBAL", "KC"),
])
def test_parse_moneyline_ticker(ticker, event_ticker, outcome):
    assert sp.parse_moneyline_ticker(ticker) == (event_ticker, outcome)


@pytest.mark.parametrize("bad", ["", "NODASHHERE", "TRAILING-", "-LEADING"])
def test_parse_moneyline_ticker_rejects_malformed(bad):
    with pytest.raises(ValueError):
        sp.parse_moneyline_ticker(bad)


# --------------------------------------------------------------------------- #
# offline capture pass via a fake client
# --------------------------------------------------------------------------- #
class FakeClient:
    """Minimal stand-in for validation.v3_market.Kalshi — only the read-only methods
    sports_pairs uses, served from in-memory fixtures. No network, no clock."""

    def __init__(self, series, series_detail, series_markets, detail_fail=(), markets_fail=()):
        self._series = series                    # [{"ticker":..., "title":..., "tags":[...]}]
        self._detail = series_detail              # {series_ticker: {"product_metadata": {...}}}
        self._markets = series_markets            # {series_ticker: [market dict, ...]}
        self._detail_fail = set(detail_fail)
        self._markets_fail = set(markets_fail)

    def series_by_category(self, category):
        return self._series

    def series_detail(self, ticker):
        if ticker in self._detail_fail:
            raise RuntimeError(f"simulated detail failure: {ticker}")
        return self._detail[ticker]

    def open_markets(self, series_ticker):
        if series_ticker in self._markets_fail:
            raise RuntimeError(f"simulated open_markets failure: {series_ticker}")
        return self._markets[series_ticker]


def _market(ticker, event_ticker, title, yes_bid, yes_ask, no_bid, no_ask):
    return {"ticker": ticker, "event_ticker": event_ticker, "title": title,
            "yes_bid_dollars": yes_bid, "yes_ask_dollars": yes_ask,
            "no_bid_dollars": no_bid, "no_ask_dollars": no_ask}


def _lines(out_summary):
    with open(out_summary["out_path"]) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


_WC_SERIES = [{"ticker": "KXWCGAME", "title": "World Cup Game", "tags": ["Soccer"]}]
_WC_DETAIL = {"KXWCGAME": {"product_metadata": {"scope": "Game"}}}


def test_confirmed_series_filters_on_scope_game(tmp_path):
    series = [
        {"ticker": "KXWCGAME", "title": "World Cup Game", "tags": ["Soccer"]},
        {"ticker": "KXWCTEAMSINGAME", "title": "World Cup Teams in Game", "tags": ["Soccer"]},
        {"ticker": "KXNOTMONEYLINE", "title": "Not a moneyline series", "tags": ["Soccer"]},
    ]
    detail = {
        "KXWCGAME": {"product_metadata": {"scope": "Game"}},
        "KXWCTEAMSINGAME": {"product_metadata": {"scope": "Knockout Stage Specials"}},
    }
    client = FakeClient(series, detail, {"KXWCGAME": []})
    confirmed, errors = sp.discover_moneyline_series(client)
    # KXNOTMONEYLINE never ends in "GAME" -> excluded before any detail call is even made
    assert [c["ticker"] for c in confirmed] == ["KXWCGAME"]
    assert errors == []


def test_world_cup_sorts_first(tmp_path):
    series = [
        {"ticker": "KXNFLGAME", "title": "Pro Football Game", "tags": ["Football"]},
        {"ticker": "KXWCGAME", "title": "World Cup Game", "tags": ["Soccer"]},
    ]
    detail = {"KXNFLGAME": {"product_metadata": {"scope": "Game"}},
              "KXWCGAME": {"product_metadata": {"scope": "Game"}}}
    client = FakeClient(series, detail, {"KXNFLGAME": [], "KXWCGAME": []})
    confirmed, _ = sp.discover_moneyline_series(client)
    assert [c["ticker"] for c in confirmed] == ["KXWCGAME", "KXNFLGAME"]


def test_complete_bracket_computes_bracket_sum_and_overround(tmp_path):
    markets = {"KXWCGAME": [
        _market("KXWCGAME-26JUL09FRAMAR-FRA", "KXWCGAME-26JUL09FRAMAR",
                "France vs Morocco Winner?", 0.61, 0.62, 0.39, 0.40),
        _market("KXWCGAME-26JUL09FRAMAR-MAR", "KXWCGAME-26JUL09FRAMAR",
                "France vs Morocco Winner?", 0.16, 0.17, 0.84, 0.85),
        _market("KXWCGAME-26JUL09FRAMAR-TIE", "KXWCGAME-26JUL09FRAMAR",
                "France vs Morocco Winner?", 0.22, 0.23, 0.78, 0.79),
    ]}
    client = FakeClient(_WC_SERIES, _WC_DETAIL, markets)
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_events"] == 1 and summary["n_events_complete"] == 1
    line = _lines(summary)[0]
    assert line["event_ticker"] == "KXWCGAME-26JUL09FRAMAR"
    assert line["n_outcomes"] == 3
    assert line["completeness_ok"] is True
    assert line["bracket_sum"] == pytest.approx(0.62 + 0.17 + 0.23, abs=1e-9)
    assert line["overround_absorbed"] == pytest.approx(0.02, abs=1e-9)
    assert line["price_source_tag"] == "real_ask"
    assert all(o["price_source_tag"] == "real_ask" for o in line["outcomes"])
    assert [o["outcome"] for o in line["outcomes"]] == ["FRA", "MAR", "TIE"]


def test_thin_book_missing_ask_marks_incomplete_not_hidden(tmp_path):
    markets = {"KXWCGAME": [
        _market("KXWCGAME-26JUL09FRAMAR-FRA", "KXWCGAME-26JUL09FRAMAR",
                "France vs Morocco Winner?", 0.61, 0.62, 0.39, 0.40),
        _market("KXWCGAME-26JUL09FRAMAR-MAR", "KXWCGAME-26JUL09FRAMAR",
                "France vs Morocco Winner?", None, None, None, None),
    ]}
    client = FakeClient(_WC_SERIES, _WC_DETAIL, markets)
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_events"] == 1 and summary["n_events_complete"] == 0
    line = _lines(summary)[0]
    assert line["completeness_ok"] is False
    assert "bracket_sum" not in line          # never compute a bracket over a missing ask


def test_series_open_markets_failure_is_recorded_not_hidden(tmp_path):
    client = FakeClient(_WC_SERIES, _WC_DETAIL, {"KXWCGAME": []}, markets_fail={"KXWCGAME"})
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_series_errors"] == 1
    assert summary["n_events"] == 0


def test_odds_leg_blocked_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    client = FakeClient(_WC_SERIES, _WC_DETAIL, {"KXWCGAME": []})
    summary = sp.run(client=client, store=tmp_path)
    assert summary["odds_leg"] == "BLOCKED(key)"


def test_pass_writes_only_under_given_store(tmp_path):
    client = FakeClient(_WC_SERIES, _WC_DETAIL, {"KXWCGAME": []})
    summary = sp.run(client=client, store=tmp_path)
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert all(str(p).startswith(str(tmp_path)) for p in written)
    assert Path(summary["out_path"]).exists()
