"""Q4/S7a historical sourcing — bitemporal-free, purely offline (no network). The
fake Kalshi client and an in-memory football-data.co.uk workbook stand in for the
two live sources; run() is exercised end-to-end against a tmp store."""
from __future__ import annotations

import io
import json

import openpyxl
import pytest

from core.odds import decimal_to_implied_prob
from scripts import sports_history_s7a as s7a


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class FakeClient:
    """Stand-in for validation.v3_market.Kalshi's events/candlesticks/markets."""

    def __init__(self, events, candles_by_ticker=None, markets_by_series=None,
                fail_candles_for=()):
        self._events = events
        self._candles = candles_by_ticker or {}
        self._markets = markets_by_series or {}
        self._fail_candles_for = set(fail_candles_for)

    def events(self, series_ticker, status, limit=200):
        return self._events

    def candlesticks(self, series_ticker, ticker, period_interval, start_ts, end_ts):
        if ticker in self._fail_candles_for:
            raise RuntimeError("simulated candlestick fetch failure")
        return self._candles.get(ticker, [])

    def markets(self, series_ticker, status, limit=1000):
        return self._markets.get(series_ticker, [])


def _wc_market(ticker, title, sub_title, result="", settlement="",
              open_time="2026-07-11T00:00:00Z", close_time="2026-07-11T23:00:00Z"):
    return {
        "ticker": ticker, "title": title, "yes_sub_title": sub_title,
        "result": result, "settlement_value_dollars": settlement,
        "open_time": open_time, "close_time": close_time,
    }


_ARGSUI_EVENT = {
    "event_ticker": "KXWCGAME-26JUL11ARGSUI",
    "markets": [
        _wc_market("KXWCGAME-26JUL11ARGSUI-TIE", "Argentina vs Switzerland Winner?",
                  "Reg Time: Tie", result="no", settlement="0.0000"),
        _wc_market("KXWCGAME-26JUL11ARGSUI-SUI", "Argentina vs Switzerland Winner?",
                  "Reg Time: Switzerland", result="no", settlement="0.0000"),
        _wc_market("KXWCGAME-26JUL11ARGSUI-ARG", "Argentina vs Switzerland Winner?",
                  "Reg Time: Argentina", result="yes", settlement="1.0000"),
    ],
}

# an event whose nested markets never carry a "<A> vs <B> Winner?" title — must be
# skipped as a warning, not crash the pass.
_UNPARSEABLE_EVENT = {
    "event_ticker": "KXWCGAME-26JULWEIRD",
    "markets": [{"ticker": "KXWCGAME-26JULWEIRD-X", "title": "Something else entirely",
                "yes_sub_title": "X", "result": "", "settlement_value_dollars": "",
                "open_time": "2026-07-01T00:00:00Z", "close_time": "2026-07-01T02:00:00Z"}],
}


def _xlsx_bytes(rows, sheet_name=s7a.FOOTBALL_DATA_SHEET):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    header = ["Home", "Away", "Date", "H-Avg", "D-Avg", "A-Avg"]
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


import datetime as _dt

_ODDS_ROWS = [
    ["Argentina", "Switzerland", _dt.datetime(2026, 7, 11), 1.45, 4.6, 9.6],
]


# --------------------------------------------------------------------------- #
# team-name parsing / aliasing
# --------------------------------------------------------------------------- #
def test_parse_event_teams_finds_the_winner_titled_market():
    teams = s7a.parse_event_teams(_ARGSUI_EVENT["markets"])
    assert teams == ("Argentina", "Switzerland")


def test_parse_event_teams_returns_none_when_unparseable():
    assert s7a.parse_event_teams(_UNPARSEABLE_EVENT["markets"]) is None


def test_slug_applies_known_aliases():
    assert s7a._slug("IR Iran") == s7a._slug("Iran")
    assert s7a._slug("Korea Republic") == s7a._slug("South Korea")
    assert s7a._slug("Czechia") == s7a._slug("Czech Republic")
    assert s7a._slug("Bosnia and Herzegovina") == s7a._slug("Bosnia & Herzegovina")


def test_slug_distinguishes_unrelated_teams():
    assert s7a._slug("France") != s7a._slug("Morocco")


# --------------------------------------------------------------------------- #
# football-data.co.uk xlsx parsing + matching + de-vig
# --------------------------------------------------------------------------- #
def test_load_worldcup_odds_rows_parses_expected_columns():
    rows = s7a.load_worldcup_odds_rows(_xlsx_bytes(_ODDS_ROWS))
    assert len(rows) == 1
    row = rows[0]
    assert row["home"] == "Argentina" and row["away"] == "Switzerland"
    assert row["date"] == "2026-07-11"
    assert row["h_avg"] == pytest.approx(1.45)


def test_load_worldcup_odds_rows_rejects_missing_columns():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = s7a.FOOTBALL_DATA_SHEET
    ws.append(["Home", "Away"])  # missing Date/H-Avg/D-Avg/A-Avg
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ValueError):
        s7a.load_worldcup_odds_rows(buf.getvalue())


def test_match_odds_row_is_order_agnostic():
    rows = s7a.load_worldcup_odds_rows(_xlsx_bytes(_ODDS_ROWS))
    # Kalshi's "home"/"away" need not agree with football-data's home/away designation.
    assert s7a.match_odds_row(rows, "Switzerland", "Argentina") is not None
    assert s7a.match_odds_row(rows, "Argentina", "Switzerland") is not None


def test_match_odds_row_uses_team_aliases():
    rows = s7a.load_worldcup_odds_rows(_xlsx_bytes(
        [["Iran", "New Zealand", _dt.datetime(2026, 6, 15), 2.1, 3.3, 3.5]]))
    assert s7a.match_odds_row(rows, "IR Iran", "New Zealand") is not None


def test_match_odds_row_none_when_no_pairing_exists():
    rows = s7a.load_worldcup_odds_rows(_xlsx_bytes(_ODDS_ROWS))
    assert s7a.match_odds_row(rows, "Brazil", "Japan") is None


def test_devig_odds_row_sums_to_one_and_matches_implied_ranking():
    rows = s7a.load_worldcup_odds_rows(_xlsx_bytes(_ODDS_ROWS))
    devig = s7a.devig_odds_row(rows[0])
    assert devig["price_source_tag"] == "synthetic"
    total = devig["fair_home"] + devig["fair_draw"] + devig["fair_away"]
    assert total == pytest.approx(1.0, abs=1e-9)
    # shortest decimal odds (favorite) must have the highest fair probability
    assert devig["fair_home"] > devig["fair_draw"] > devig["fair_away"]


def test_devig_odds_row_none_on_missing_leg():
    row = {"home": "A", "away": "B", "date": "2026-01-01", "h_avg": 1.5, "d_avg": None, "a_avg": 5.0}
    assert s7a.devig_odds_row(row) is None


# --------------------------------------------------------------------------- #
# end-to-end run() — offline, tmp store
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# candlestick window truncation
# --------------------------------------------------------------------------- #
def test_candle_window_untruncated_when_short():
    start_ts, end_ts, truncated = s7a.candle_window(
        "2026-07-08T00:00:00Z", "2026-07-09T22:04:24Z")
    assert not truncated
    assert start_ts == int(s7a._parse_iso("2026-07-08T00:00:00Z").timestamp())
    assert end_ts == int(s7a._parse_iso("2026-07-09T22:04:24Z").timestamp()) + 3600


def test_candle_window_truncated_when_market_opened_long_before_close():
    start_ts, end_ts, truncated = s7a.candle_window(
        "2026-01-01T00:00:00Z", "2026-07-09T22:04:24Z")
    assert truncated
    close_ts = int(s7a._parse_iso("2026-07-09T22:04:24Z").timestamp())
    assert start_ts == close_ts - s7a.CANDLE_LOOKBACK_HOURS * 3600


def test_run_end_to_end_offline(tmp_path):
    candles = {"KXWCGAME-26JUL11ARGSUI-ARG": [{"end_period_ts": 1, "yes_ask": {"close_dollars": "0.58"}}]}
    client = FakeClient(events=[_ARGSUI_EVENT, _UNPARSEABLE_EVENT], candles_by_ticker=candles,
                       markets_by_series={"KXNFLGAME": [], "KXNBAGAME": []})
    summary = s7a.run(client=client, store=tmp_path,
                      odds_bytes_fetcher=lambda: _xlsx_bytes(_ODDS_ROWS))

    assert summary["n_games"] == 1  # the unparseable event is skipped
    assert summary["n_odds_matched"] == 1
    assert summary["n_parse_warnings"] == 1
    assert summary["last_season_nfl_nba_availability"] == {
        "KXNFLGAME": {"n_settled": 0, "n_closed": 0},
        "KXNBAGAME": {"n_settled": 0, "n_closed": 0},
    }

    lines = (tmp_path / "worldcup2026.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["kalshi_event_ticker"] == "KXWCGAME-26JUL11ARGSUI"
    assert rec["home_team"] == "Argentina" and rec["away_team"] == "Switzerland"
    assert rec["price_source_tag_kalshi"] == "real_ask"
    assert rec["odds_match"]["matched"] is True
    assert rec["odds_match"]["price_source_tag"] == "synthetic"
    assert rec["n_candle_fetch_failures"] == 0
    assert len(rec["kalshi_raw_sha256"]) == 64


def test_run_records_candle_fetch_failure_without_dropping_the_game(tmp_path):
    client = FakeClient(events=[_ARGSUI_EVENT],
                       fail_candles_for={"KXWCGAME-26JUL11ARGSUI-ARG"},
                       markets_by_series={"KXNFLGAME": [], "KXNBAGAME": []})
    summary = s7a.run(client=client, store=tmp_path,
                      odds_bytes_fetcher=lambda: _xlsx_bytes(_ODDS_ROWS))
    assert summary["n_games"] == 1
    assert summary["n_candle_fetch_failures"] == 1
    rec = json.loads((tmp_path / "worldcup2026.jsonl").read_text().splitlines()[0])
    arg_outcome = next(o for o in rec["outcomes"] if o["market_ticker"].endswith("-ARG"))
    assert arg_outcome["candle_fetch_ok"] is False
    assert arg_outcome["candles"] == []


def test_run_writes_odds_source_provenance_file(tmp_path):
    client = FakeClient(events=[_ARGSUI_EVENT], markets_by_series={"KXNFLGAME": [], "KXNBAGAME": []})
    xlsx_bytes = _xlsx_bytes(_ODDS_ROWS)
    s7a.run(client=client, store=tmp_path, odds_bytes_fetcher=lambda: xlsx_bytes)
    saved = list(tmp_path.glob("worldcup2026-odds-source-*.xlsx"))
    assert len(saved) == 1
    assert saved[0].read_bytes() == xlsx_bytes
