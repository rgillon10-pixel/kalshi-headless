"""Unit tests for collection.sports_pairs: ticker parsing, de-vig math, offline capture."""
from __future__ import annotations

import json

import pytest

from collection import sports_pairs as sp


# --------------------------------------------------------------------------- #
# ticker parsing (pure string parsing, no network)
# --------------------------------------------------------------------------- #
def test_parse_ticker_three_way_soccer():
    parsed, err = sp.parse_ticker("KXWCGAME-26JUL11ARGSUI-TIE")
    assert err is None
    assert parsed == {"series": "KXWCGAME", "match_code": "26JUL11ARGSUI", "outcome": "TIE"}


def test_parse_ticker_two_way_mlb():
    parsed, err = sp.parse_ticker("KXMLBGAME-26JUL091310NYYTB-NYY")
    assert err is None
    assert parsed["series"] == "KXMLBGAME" and parsed["outcome"] == "NYY"


def test_parse_ticker_rejects_malformed():
    parsed, err = sp.parse_ticker("not-a-ticker")
    assert parsed is None and err == "no_regex_match"


def test_is_moneyline_series_filters_by_game_suffix():
    assert sp.is_moneyline_series({"ticker": "KXMLBGAME"}) is True
    assert sp.is_moneyline_series({"ticker": "KXWC1HSPREAD"}) is False
    assert sp.is_moneyline_series({"ticker": "KXWCGAMEGOALS"}) is False


# --------------------------------------------------------------------------- #
# de-vig math
# --------------------------------------------------------------------------- #
def test_devig_multiplicative_two_way_sums_to_one():
    fair = sp.devig_multiplicative([1.91, 2.05])
    assert fair == pytest.approx([0.5178, 0.4822], abs=1e-3)
    assert sum(fair) == pytest.approx(1.0)


def test_devig_multiplicative_three_way_sums_to_one():
    fair = sp.devig_multiplicative([2.60, 3.40, 2.90])
    assert sum(fair) == pytest.approx(1.0)
    assert all(0 < p < 1 for p in fair)


def test_devig_rejects_bad_odds():
    with pytest.raises(ValueError):
        sp.devig_multiplicative([0.9, 2.0])
    with pytest.raises(ValueError):
        sp.devig_multiplicative([2.0])


# --------------------------------------------------------------------------- #
# odds-event matching (name-token based, ambiguity loses to no-match)
# --------------------------------------------------------------------------- #
def test_match_odds_event_finds_unique_team_match():
    events = [
        {"home_team": "Argentina", "away_team": "Switzerland"},
        {"home_team": "Spain", "away_team": "Belgium"},
    ]
    ev = sp.match_odds_event("Argentina vs Switzerland Winner?", events)
    assert ev == events[0]


def test_match_odds_event_returns_none_on_no_match():
    events = [{"home_team": "Brazil", "away_team": "France"}]
    assert sp.match_odds_event("Argentina vs Switzerland Winner?", events) is None


# --------------------------------------------------------------------------- #
# offline capture pass -- FakeClient, no network (mirrors test_capture_bitemporal.py)
# --------------------------------------------------------------------------- #
class FakeClient:
    """Minimal stand-in for validation.v3_market.Kalshi -- only series_by_category/
    open_markets, served from in-memory fixtures. No network, no clock, no order path."""

    def __init__(self, series, markets_by_series, fail_series=()):
        self._series = series                      # [{"ticker": ..., "title": ...}, ...]
        self._markets = markets_by_series           # {series_ticker: [market_dict, ...]}
        self._fail_series = set(fail_series)

    def series_by_category(self, category):
        return self._series

    def open_markets(self, series_ticker):
        if series_ticker in self._fail_series:
            raise RuntimeError(f"simulated enumeration failure: {series_ticker}")
        return self._markets[series_ticker]


def _mkt(ticker, event_ticker, title, yes_ask, no_ask, yes_bid=None, no_bid=None,
        sub_title=""):
    return {
        "ticker": ticker, "event_ticker": event_ticker, "title": title,
        "yes_sub_title": sub_title, "close_time": "2026-07-12T04:00:00Z",
        "yes_ask_dollars": yes_ask, "no_ask_dollars": no_ask,
        "yes_bid_dollars": yes_bid, "no_bid_dollars": no_bid, "status": "active",
    }


_TWO_WAY = [
    _mkt("KXMLBGAME-26JUL091310NYYTB-NYY", "KXMLBGAME-26JUL091310NYYTB",
        "New York vs Tampa Bay Winner?", "0.5800", "0.4400", "0.5600", "0.4200", "NYY"),
    _mkt("KXMLBGAME-26JUL091310NYYTB-TB", "KXMLBGAME-26JUL091310NYYTB",
        "New York vs Tampa Bay Winner?", "0.4400", "0.5800", "0.4200", "0.5600", "TB"),
]


def test_complete_capture_emits_one_line_per_game(tmp_path):
    client = FakeClient(
        [{"ticker": "KXMLBGAME", "title": "Professional Baseball Game"}],
        {"KXMLBGAME": _TWO_WAY},
    )
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_games"] == 1 and summary["n_complete"] == 1
    lines = [json.loads(ln) for ln in (tmp_path / f"dt={summary['day']}" /
             f"pass-{summary['capture_id']}.jsonl").read_text().splitlines()]
    assert len(lines) == 1
    line = lines[0]
    assert line["event_ticker"] == "KXMLBGAME-26JUL091310NYYTB"
    assert line["n_legs"] == 2 and line["n_legs_captured"] == 2
    assert line["completeness_ok"] is True
    assert all(leg["source_tag"] == "real_ask" for leg in line["legs"])
    # bracket_sum routed through core.pricing (Hard Rule #3), never hand-summed
    assert line["bracket_sum"] == pytest.approx(0.5800 + 0.4400)
    assert line["overround_absorbed"] == pytest.approx(line["bracket_sum"] - 1.0)


def test_no_odds_key_blocks_odds_leg_but_still_captures_kalshi_leg(tmp_path):
    client = FakeClient(
        [{"ticker": "KXMLBGAME", "title": "Professional Baseball Game"}],
        {"KXMLBGAME": _TWO_WAY},
    )
    summary = sp.run(client=client, store=tmp_path, odds_api_key="")
    assert summary["odds_status"] == "BLOCKED(key)"
    assert summary["n_games"] == 1
    line = json.loads((tmp_path / f"dt={summary['day']}" /
                       f"pass-{summary['capture_id']}.jsonl").read_text().splitlines()[0])
    assert line["odds"] == {"status": "BLOCKED(key)"}
    assert line["legs"][0]["yes_ask"] is not None   # Kalshi leg unaffected by missing key


def test_series_enumeration_failure_recorded_not_hidden(tmp_path):
    client = FakeClient(
        [{"ticker": "KXMLBGAME", "title": "Professional Baseball Game"},
         {"ticker": "KXNHLGAME", "title": "Pro Hockey Game"}],
        {"KXMLBGAME": _TWO_WAY, "KXNHLGAME": []},
        fail_series={"KXNHLGAME"},
    )
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_series_errors"] == 1
    assert summary["n_games"] == 1   # MLB still captured despite NHL enumeration failing


def test_non_game_series_excluded_from_discovery(tmp_path):
    client = FakeClient(
        [{"ticker": "KXMLBGAME", "title": "Professional Baseball Game"},
         {"ticker": "KXWC1HSPREAD", "title": "World Cup 1st Half Spread"}],
        {"KXMLBGAME": _TWO_WAY, "KXWC1HSPREAD": [
            _mkt("KXWC1HSPREAD-26JUL11ARGSUI-ARG", "KXWC1HSPREAD-26JUL11ARGSUI",
                "spread market", "0.5", "0.5"),
        ]},
    )
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_games"] == 1   # the spread series never got enumerated


def test_degenerate_single_leg_group_emits_no_line(tmp_path):
    solo = [_mkt("KXMLBGAME-26JUL091310NYYTB-NYY", "KXMLBGAME-26JUL091310NYYTB",
                "New York vs Tampa Bay Winner?", "0.5800", "0.4400")]
    client = FakeClient(
        [{"ticker": "KXMLBGAME", "title": "Professional Baseball Game"}],
        {"KXMLBGAME": solo},
    )
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_games"] == 0 and summary["n_degenerate"] == 1
    assert not (tmp_path / f"dt={summary['day']}").exists()


def test_missing_ask_lowers_completeness_not_hidden(tmp_path):
    suspended = [
        _mkt("KXMLBGAME-26JUL091310NYYTB-NYY", "KXMLBGAME-26JUL091310NYYTB",
            "New York vs Tampa Bay Winner?", "0.5800", "0.4400"),
        _mkt("KXMLBGAME-26JUL091310NYYTB-TB", "KXMLBGAME-26JUL091310NYYTB",
            "New York vs Tampa Bay Winner?", None, None),
    ]
    client = FakeClient(
        [{"ticker": "KXMLBGAME", "title": "Professional Baseball Game"}],
        {"KXMLBGAME": suspended},
    )
    summary = sp.run(client=client, store=tmp_path)
    line = json.loads((tmp_path / f"dt={summary['day']}" /
                       f"pass-{summary['capture_id']}.jsonl").read_text().splitlines()[0])
    assert line["completeness_ok"] is False
    assert line["n_legs_captured"] == 1 and line["n_legs"] == 2
    assert line["bracket_sum"] is None   # < 2 captured asks -> no fabricated overround
    assert summary["n_complete"] == 0
