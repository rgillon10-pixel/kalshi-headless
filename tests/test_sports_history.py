"""collection.sports_history — settled-event pagination, decision-time candlestick ask
selection, honest retention-window flagging, and ESPN closing-moneyline extraction (fully
offline: FakeClient / monkeypatched requests, no network)."""
from __future__ import annotations

import json

import pytest

from collection import sports_history as sh

# --------------------------------------------------------------------------- #
# fake Kalshi client
# --------------------------------------------------------------------------- #
class FakeClient:
    """Minimal stand-in for validation.v3_market.Kalshi — only the read-only calls
    sports_history uses, served from in-memory fixtures. No network, no clock."""

    def __init__(self, events_pages, markets_by_event, candles_by_ticker=None):
        self.events_pages = events_pages              # list of {"events": [...], "cursor": ...}
        self.markets_by_event = markets_by_event       # {event_ticker: [market dict, ...]}
        self.candles_by_ticker = candles_by_ticker or {}  # {ticker: [candle dict, ...]}
        self._events_call = 0

    def get_text(self, path, **params):
        if path == "/events":
            page = self.events_pages[self._events_call]
            self._events_call += 1
            return json.dumps(page)
        if path == "/markets":
            et = params["event_ticker"]
            return json.dumps({"markets": self.markets_by_event.get(et, [])})
        raise AssertionError(f"unexpected get_text path {path!r}")

    def get(self, path, **params):
        assert path.endswith("/candlesticks")
        ticker = path.split("/markets/")[1].split("/candlesticks")[0]
        return {"candlesticks": self.candles_by_ticker.get(ticker, [])}


def _mk_market(ticker, close_time, title="Team A vs Team B Winner?", result="yes"):
    return {"ticker": ticker, "title": title, "result": result,
            "close_time": close_time, "open_time": "2026-06-01T00:00:00Z",
            "occurrence_datetime": close_time}


def _mk_candle(end_ts, yes_ask_close):
    return {"end_period_ts": end_ts,
            "yes_ask": {"close_dollars": f"{yes_ask_close:.4f}"} if yes_ask_close is not None else {}}


# --------------------------------------------------------------------------- #
# fetch_settled_events — pagination
# --------------------------------------------------------------------------- #
def test_fetch_settled_events_paginates_until_no_cursor():
    client = FakeClient(
        events_pages=[
            {"events": [{"event_ticker": "E1"}], "cursor": "c1"},
            {"events": [{"event_ticker": "E2"}], "cursor": ""},
        ],
        markets_by_event={},
    )
    events, raw_pages = sh.fetch_settled_events(client, "KXNFLGAME")
    assert [e["event_ticker"] for e in events] == ["E1", "E2"]
    assert len(raw_pages) == 2


def test_fetch_settled_events_respects_limit_and_stops_early():
    client = FakeClient(
        events_pages=[{"events": [{"event_ticker": "E1"}, {"event_ticker": "E2"}], "cursor": "c1"}],
        markets_by_event={},
    )
    events, _ = sh.fetch_settled_events(client, "KXNFLGAME", limit=1)
    assert [e["event_ticker"] for e in events] == ["E1"]


# --------------------------------------------------------------------------- #
# candlestick_ask_before — candlestick selection (generic, no kickoff/decision claim)
# --------------------------------------------------------------------------- #
def test_candlestick_ask_before_picks_last_candle_at_or_before_before_ts():
    import datetime as dt
    before_ts = dt.datetime(2026, 6, 14, 3, 30, 0, tzinfo=dt.timezone.utc)
    end_before = int(before_ts.timestamp()) - 3600
    end_after = int(before_ts.timestamp()) + 3600   # must be excluded (after before_ts)
    client = FakeClient(
        events_pages=[], markets_by_event={},
        candles_by_ticker={"TKR": [_mk_candle(end_before - 3600, 0.30),
                                    _mk_candle(end_before, 0.36),
                                    _mk_candle(end_after, 0.99)]},
    )
    out = sh.candlestick_ask_before(client, "KXNBAGAME", "TKR", before_ts)
    assert out == {"yes_ask": 0.36, "end_period_ts": end_before, "price_source_tag": "real_ask"}


def test_candlestick_ask_before_none_when_no_candles_in_window():
    import datetime as dt
    before_ts = dt.datetime(2026, 6, 14, 3, 30, 0, tzinfo=dt.timezone.utc)
    client = FakeClient(events_pages=[], markets_by_event={}, candles_by_ticker={"TKR": []})
    assert sh.candlestick_ask_before(client, "KXNBAGAME", "TKR", before_ts) is None


def test_candlestick_ask_before_none_when_candle_missing_yes_ask():
    import datetime as dt
    before_ts = dt.datetime(2026, 6, 14, 3, 30, 0, tzinfo=dt.timezone.utc)
    end_before = int(before_ts.timestamp()) - 60
    client = FakeClient(events_pages=[], markets_by_event={},
                        candles_by_ticker={"TKR": [_mk_candle(end_before, None)]})
    assert sh.candlestick_ask_before(client, "KXNBAGAME", "TKR", before_ts) is None


# --------------------------------------------------------------------------- #
# fetch_kalshi_settled — honest retention flagging, never silently dropped
# --------------------------------------------------------------------------- #
def test_fetch_kalshi_settled_flags_retention_available_true(tmp_path):
    import datetime as dt
    close_time = "2026-06-14T03:30:00Z"
    close_ts = dt.datetime(2026, 6, 14, 3, 30, 0, tzinfo=dt.timezone.utc)
    end_before = int(close_ts.timestamp()) - 60   # just before close, within lookback window
    client = FakeClient(
        events_pages=[{"events": [{"event_ticker": "KXNBAGAME-26JUN13NYKSAS",
                                    "title": "New York at San Antonio"}], "cursor": ""}],
        markets_by_event={"KXNBAGAME-26JUN13NYKSAS": [_mk_market("TKR-NYK", close_time)]},
        candles_by_ticker={"TKR-NYK": [_mk_candle(end_before, 0.42)]},
    )
    summary = sh.fetch_kalshi_settled(client, "KXNBAGAME", limit=5, tape_dir=tmp_path)
    assert summary["n_events"] == 1 and summary["n_retention_available"] == 1
    lines = (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
    rec = json.loads(lines[0])
    assert rec["retention_available"] is True
    assert rec["outcomes"][0]["sample_ask_near_close"]["price_source_tag"] == "real_ask"


def test_fetch_kalshi_settled_flags_purged_event_never_drops_it(tmp_path):
    client = FakeClient(
        events_pages=[{"events": [{"event_ticker": "KXNFLGAME-26JAN25LASEA",
                                    "title": "Los Angeles R at Seattle"}], "cursor": ""}],
        markets_by_event={},   # purged: /markets?event_ticker=... returns []
    )
    summary = sh.fetch_kalshi_settled(client, "KXNFLGAME", limit=5, tape_dir=tmp_path)
    assert summary["n_events"] == 1 and summary["n_retention_available"] == 0
    lines = (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
    rec = json.loads(lines[0])
    assert rec["retention_available"] is False
    assert rec["outcomes"] == []
    assert rec["event_ticker"] == "KXNFLGAME-26JAN25LASEA"   # present, not dropped


# --------------------------------------------------------------------------- #
# ESPN closing-moneyline extraction
# --------------------------------------------------------------------------- #
def test_extract_closing_moneyline_two_way():
    summary = {"pickcenter": [{
        "provider": {"name": "DraftKings", "id": "100"},
        "moneyline": {"home": {"close": {"odds": "-625"}, "open": {"odds": "-750"}},
                      "away": {"close": {"odds": "+455"}, "open": {"odds": "+525"}}},
    }]}
    ml = sh.extract_closing_moneyline(summary)
    assert ml["home_close"] == "-625" and ml["away_open"] == "+525"
    assert ml["price_source_tag"] == "synthetic"
    assert "draw_close" not in ml


def test_extract_closing_moneyline_three_way_soccer_has_draw():
    summary = {"pickcenter": [{
        "provider": {"name": "DraftKings", "id": "100"},
        "moneyline": {"home": {"close": {"odds": "-1000"}, "open": {"odds": "-1400"}},
                      "away": {"close": {"odds": "+2000"}, "open": {"odds": "+1900"}},
                      "draw": {"close": {"odds": "+1000"}, "open": {"odds": "+750"}}},
    }]}
    ml = sh.extract_closing_moneyline(summary)
    assert ml["draw_close"] == "+1000" and ml["draw_open"] == "+750"


def test_extract_closing_moneyline_none_when_no_pickcenter():
    assert sh.extract_closing_moneyline({"pickcenter": []}) is None
    assert sh.extract_closing_moneyline({}) is None


# --------------------------------------------------------------------------- #
# fetch_espn_closing_odds — monkeypatched HTTP, fully offline
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_fetch_espn_closing_odds_offline_pass(monkeypatch, tmp_path):
    def fake_get(url, **kw):
        if url.endswith("/scoreboard"):
            return _FakeResp({"events": [{"id": "1", "name": "USA at Belgium",
                                          "date": "2026-07-06T18:00Z",
                                          "status": {"type": {"name": "STATUS_FINAL"}}}]})
        assert url.endswith("/summary")
        return _FakeResp({"pickcenter": [{
            "provider": {"name": "DraftKings", "id": "100"},
            "moneyline": {"home": {"close": {"odds": "-1000"}, "open": {"odds": "-1400"}},
                          "away": {"close": {"odds": "+2000"}, "open": {"odds": "+1900"}},
                          "draw": {"close": {"odds": "+1000"}, "open": {"odds": "+750"}}},
        }]})
    monkeypatch.setattr(sh.requests, "get", fake_get)
    summary = sh.fetch_espn_closing_odds("soccer", "fifa.world", "20260706", tape_dir=tmp_path)
    assert summary["n_events"] == 1 and summary["n_with_odds"] == 1
    lines = (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
    rec = json.loads(lines[0])
    assert rec["moneyline"]["draw_close"] == "+1000"


def test_fetch_espn_closing_odds_records_event_with_no_odds_not_dropped(monkeypatch, tmp_path):
    def fake_get(url, **kw):
        if url.endswith("/scoreboard"):
            return _FakeResp({"events": [{"id": "1", "name": "No Odds Game",
                                          "date": "t", "status": {"type": {"name": "STATUS_FINAL"}}}]})
        return _FakeResp({"pickcenter": []})
    monkeypatch.setattr(sh.requests, "get", fake_get)
    summary = sh.fetch_espn_closing_odds("basketball", "nba", "20260101", tape_dir=tmp_path)
    assert summary["n_events"] == 1 and summary["n_with_odds"] == 0
    lines = (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
    assert json.loads(lines[0])["moneyline"] is None


def test_fetch_espn_closing_odds_summary_fetch_error_recorded_not_raised(monkeypatch, tmp_path):
    def fake_get(url, **kw):
        if url.endswith("/scoreboard"):
            return _FakeResp({"events": [{"id": "1", "name": "Flaky Game",
                                          "date": "t", "status": {"type": {"name": "STATUS_FINAL"}}}]})
        raise RuntimeError("espn summary down")
    monkeypatch.setattr(sh.requests, "get", fake_get)
    summary = sh.fetch_espn_closing_odds("football", "nfl", "20260101", tape_dir=tmp_path)
    assert summary["n_fetch_errors"] == 1 and summary["n_with_odds"] == 0
