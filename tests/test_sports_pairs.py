"""Sports moneyline BBO capture — ticker parsing, de-vig math, and an offline run()
against a fake Kalshi client (no network), mirroring test_capture_bitemporal.py's
discipline: a failed series fetch lowers completeness rather than being hidden.
"""
from __future__ import annotations

import json
import math

import pytest

from collection import sports_pairs as sp


# --------------------------------------------------------------------------- #
# ticker parsing
# --------------------------------------------------------------------------- #
def test_parse_event_ticker_soccer_world_cup():
    meta, err = sp.parse_event_ticker("KXWCGAME-26JUL11ARGSUI")
    assert err is None
    assert meta == {"series": "KXWCGAME", "date": "2026-07-11", "code": "ARGSUI"}


def test_parse_event_ticker_mlb_with_time_prefix():
    meta, err = sp.parse_event_ticker("KXMLBGAME-26JUL112110AZLAD")
    assert err is None
    assert meta["series"] == "KXMLBGAME"
    assert meta["date"] == "2026-07-11"
    assert meta["code"] == "2110AZLAD"


def test_parse_event_ticker_bad_shape_fails_loudly():
    meta, err = sp.parse_event_ticker("not-a-ticker")
    assert meta is None and err == "no_regex_match"


def test_parse_event_ticker_bad_date_token():
    meta, err = sp.parse_event_ticker("KXWCGAME-26XXX11ARGSUI")
    assert meta is None and err == "bad_date_token"


def test_parse_leg_ticker_splits_outcome_suffix():
    event_ticker, outcome, err = sp.parse_leg_ticker("KXWCGAME-26JUL11ARGSUI-ARG")
    assert err is None
    assert event_ticker == "KXWCGAME-26JUL11ARGSUI"
    assert outcome == "ARG"


def test_parse_leg_ticker_two_way_no_draw():
    event_ticker, outcome, err = sp.parse_leg_ticker("KXMLBGAME-26JUL112110AZLAD-LAD")
    assert err is None
    assert event_ticker == "KXMLBGAME-26JUL112110AZLAD"
    assert outcome == "LAD"


def test_parse_leg_ticker_rejects_non_leg_shape():
    event_ticker, outcome, err = sp.parse_leg_ticker("KXWCGAME-26JUL11ARGSUI")  # no outcome
    assert event_ticker is None and outcome is None and err == "not_a_leg_ticker"


# --------------------------------------------------------------------------- #
# de-vig math (pure — no live odds fetch without ODDS_API_KEY)
# --------------------------------------------------------------------------- #
def test_american_to_prob_known_values():
    assert math.isclose(sp.american_to_prob(-110), 110 / 210, rel_tol=1e-9)
    assert math.isclose(sp.american_to_prob(100), 0.5, rel_tol=1e-9)
    assert math.isclose(sp.american_to_prob(150), 100 / 250, rel_tol=1e-9)


def test_american_to_prob_rejects_zero():
    with pytest.raises(ValueError):
        sp.american_to_prob(0)


def test_devig_multiplicative_normalizes_to_one():
    raw = [sp.american_to_prob(-110), sp.american_to_prob(-110)]  # a vigged 50/50 line
    assert sum(raw) > 1.0   # the vig
    fair = sp.devig_multiplicative(raw)
    assert math.isclose(sum(fair), 1.0, rel_tol=1e-9)
    assert math.isclose(fair[0], fair[1], rel_tol=1e-9)


def test_devig_multiplicative_preserves_relative_odds():
    raw = [0.60, 0.30, 0.20]   # a 3-way overround line (soccer-shaped)
    fair = sp.devig_multiplicative(raw)
    assert math.isclose(sum(fair), 1.0, rel_tol=1e-9)
    assert fair[0] > fair[1] > fair[2]


def test_devig_multiplicative_rejects_zero_sum():
    with pytest.raises(ValueError):
        sp.devig_multiplicative([0.0, 0.0])


# --------------------------------------------------------------------------- #
# offline run() against a fake client — no network
# --------------------------------------------------------------------------- #
class FakeClient:
    """Minimal stand-in for validation.v3_market.Kalshi: only series_by_category
    (discovery) and paginate (events w/ nested markets) — served from fixtures."""

    def __init__(self, series, events_by_series, fail_series=()):
        self._series = series                       # [{"ticker":.., "tags":[..]}, ...]
        self._events_by_series = events_by_series    # {series_ticker: [event, ...]}
        self._fail_series = set(fail_series)

    def series_by_category(self, category):
        return self._series

    def paginate(self, path, key, **params):
        assert path == "/events" and key == "events"
        sticker = params["series_ticker"]
        if sticker in self._fail_series:
            raise RuntimeError(f"simulated series fetch failure: {sticker}")
        return self._events_by_series.get(sticker, [])


def _leg(ticker, title, sub, ya, yb, na, nb, market_type="binary"):
    return {"ticker": ticker, "title": title, "yes_sub_title": sub,
            "market_type": market_type,
            "yes_ask_dollars": ya, "yes_bid_dollars": yb,
            "no_ask_dollars": na, "no_bid_dollars": nb}


_SOCCER_EVENT = {
    "event_ticker": "KXWCGAME-26JUL11ARGSUI",
    "title": "Argentina vs Switzerland",
    "markets": [
        _leg("KXWCGAME-26JUL11ARGSUI-ARG", "Argentina vs Switzerland Winner?",
             "Reg Time: Argentina", "0.5800", "0.5700", "0.4300", "0.4200"),
        _leg("KXWCGAME-26JUL11ARGSUI-SUI", "Argentina vs Switzerland Winner?",
             "Reg Time: Switzerland", "0.1700", "0.1600", "0.8400", "0.8300"),
        _leg("KXWCGAME-26JUL11ARGSUI-TIE", "Argentina vs Switzerland Winner?",
             "Reg Time: Tie", "0.2700", "0.2600", "0.7400", "0.7300"),
    ],
}

_MLB_EVENT = {
    "event_ticker": "KXMLBGAME-26JUL112110AZLAD",
    "title": "Arizona vs Los Angeles D",
    "markets": [
        _leg("KXMLBGAME-26JUL112110AZLAD-AZ", "Arizona vs Los Angeles D Winner?",
             "Arizona", "0.3500", "0.3000", "0.7000", "0.6500"),
        _leg("KXMLBGAME-26JUL112110AZLAD-LAD", "Arizona vs Los Angeles D Winner?",
             "Los Angeles D", "0.7000", "0.6800", "0.3200", "0.3000"),
        # a non-moneyline market riding the same series -> must be filtered out
        _leg("KXMLBGAME-26JUL112110AZLAD-SPREAD", "Arizona vs Los Angeles D Spread",
             "Arizona -1.5", "0.4500", "0.4000", "0.6000", "0.5500"),
    ],
}


def _lines(store):
    files = sorted((store / "dt=2026-07-09").glob("pass-*.jsonl")) if (store / "dt=2026-07-09").exists() else []
    out = []
    for p in files:
        out.extend(json.loads(ln) for ln in p.read_text().splitlines() if ln.strip())
    return out


def test_soccer_and_mlb_events_captured_with_real_ask_tags(tmp_path, monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    client = FakeClient(
        series=[{"ticker": "KXWCGAME", "tags": ["Soccer"]},
                {"ticker": "KXMLBGAME", "tags": ["Baseball"]}],
        events_by_series={"KXWCGAME": [_SOCCER_EVENT], "KXMLBGAME": [_MLB_EVENT]},
    )
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_events_captured"] == 2
    assert summary["completeness_ok"] is True
    assert summary["odds_key_present"] is False
    assert summary["odds_status"] == "BLOCKED(key)"

    recs = {r["event_ticker"]: r for r in _lines(tmp_path)}
    soccer = recs["KXWCGAME-26JUL11ARGSUI"]
    assert soccer["n_legs"] == 3   # win/lose/tie, not the (absent) spread market
    assert all(leg["price_source_tag"] == "real_ask" for leg in soccer["legs"])
    assert soccer["game_date"] == "2026-07-11"
    # 0.58 + 0.17 + 0.27 = 1.02 -> a 2c overround, computed via core.pricing only
    assert math.isclose(soccer["bracket_sum"], 1.02, rel_tol=1e-9)
    assert math.isclose(soccer["overround"], 0.02, rel_tol=1e-9)
    assert soccer["odds"] == {"status": "BLOCKED(key)"}

    mlb = recs["KXMLBGAME-26JUL112110AZLAD"]
    assert mlb["n_legs"] == 2   # the spread leg was filtered out (title doesn't end "Winner?")
    assert {leg["ticker"] for leg in mlb["legs"]} == {
        "KXMLBGAME-26JUL112110AZLAD-AZ", "KXMLBGAME-26JUL112110AZLAD-LAD"}


def test_odds_key_present_flips_status_but_kalshi_leg_still_captured(tmp_path, monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "fake-key-for-test")
    client = FakeClient(
        series=[{"ticker": "KXWCGAME", "tags": ["Soccer"]}],
        events_by_series={"KXWCGAME": [_SOCCER_EVENT]},
    )
    summary = sp.run(client=client, store=tmp_path)
    assert summary["odds_key_present"] is True
    assert summary["odds_status"] == "unfetched_this_run"
    recs = _lines(tmp_path)
    assert len(recs) == 1 and recs[0]["n_legs"] == 3


def test_failed_series_lowers_completeness_not_hidden(tmp_path, monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    client = FakeClient(
        series=[{"ticker": "KXWCGAME", "tags": ["Soccer"]},
                {"ticker": "KXNFLGAME", "tags": ["Football"]}],
        events_by_series={"KXWCGAME": [_SOCCER_EVENT]},
        fail_series={"KXNFLGAME"},
    )
    summary = sp.run(client=client, store=tmp_path)
    assert summary["completeness_ok"] is False
    assert summary["n_series_failed"] == 1
    assert summary["series_failed"][0]["series"] == "KXNFLGAME"
    assert summary["n_events_captured"] == 1   # the series that DID work still gets written


def test_single_leg_event_is_degenerate_and_dropped(tmp_path, monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    lone = {"event_ticker": "KXNBAGAME-26JUL09ABCXYZ", "title": "solo",
            "markets": [_leg("KXNBAGAME-26JUL09ABCXYZ-ABC", "X vs Y Winner?",
                              "X", "0.5000", "0.4900", "0.5100", "0.5000")]}
    client = FakeClient(series=[{"ticker": "KXNBAGAME", "tags": ["Basketball"]}],
                        events_by_series={"KXNBAGAME": [lone]})
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_events_captured"] == 0


def test_priority_sort_puts_world_cup_first():
    series = [{"ticker": "KXNFLGAME", "tags": ["Football"]},
              {"ticker": "KXMLSGAME", "tags": ["Soccer"]},
              {"ticker": "KXWCGAME", "tags": ["Soccer"]}]
    ordered = sorted(series, key=sp._priority_key)
    assert [s["ticker"] for s in ordered] == ["KXWCGAME", "KXMLSGAME", "KXNFLGAME"]


def test_discover_moneyline_series_filters_by_game_suffix():
    client = FakeClient(
        series=[{"ticker": "KXWCGAME", "tags": ["Soccer"]},
                {"ticker": "KXWCTOTAL", "tags": ["Soccer"]},   # not a head-to-head market
                {"ticker": "KXNBAGAME", "tags": ["Basketball"]}],
        events_by_series={},
    )
    tickers = {s["ticker"] for s in sp.discover_moneyline_series(client)}
    assert tickers == {"KXWCGAME", "KXNBAGAME"}
