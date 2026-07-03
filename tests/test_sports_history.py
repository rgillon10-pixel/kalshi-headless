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


# --------------------------------------------------------------------------- #
# S7b — team-name extraction / normalization
# --------------------------------------------------------------------------- #
def test_extract_kalshi_teams_wc_full_form():
    title = "Switzerland vs Algeria: Regulation Time Moneyline SUI vs DZA (Jul 2)"
    assert sh.extract_kalshi_teams(title) == ("Switzerland", "Algeria")


def test_extract_kalshi_teams_wc_bare_form():
    assert sh.extract_kalshi_teams("Cape Verde vs Saudi Arabia") == ("Cape Verde", "Saudi Arabia")


def test_extract_kalshi_teams_nba_game_prefix_and_at_separator():
    title = "Game 5: New York at San Antonio NYK at SAS (Jun 13)"
    assert sh.extract_kalshi_teams(title) == ("New York", "San Antonio")


def test_extract_kalshi_teams_unparseable_returns_none():
    assert sh.extract_kalshi_teams("Total Corners Over 9.5?") is None


def test_espn_teams_splits_away_at_home():
    assert sh._espn_teams("New York Knicks at San Antonio Spurs") == \
        ("New York Knicks", "San Antonio Spurs")


def test_event_team_codes_six_char_split():
    assert sh._event_team_codes("KXWCGAME-26JUL02SUIDZA") == ("SUI", "DZA")
    assert sh._event_team_codes("KXNBAGAME-26JUN13NYKSAS") == ("NYK", "SAS")


def test_event_team_codes_none_when_not_six_chars():
    assert sh._event_team_codes("KXODDGAME-26JUL02ABCDEFG") is None


def test_normalize_team_name_strips_accents_and_case():
    assert sh.normalize_team_name("Türkiye") == sh.normalize_team_name("Turkiye") == "turkiye"


def test_normalize_team_name_strips_punctuation():
    assert sh.normalize_team_name("Bosnia-Herzegovina") == "bosniaherzegovina"


# --------------------------------------------------------------------------- #
# S7b — american odds -> decimal -> de-vig
# --------------------------------------------------------------------------- #
def test_american_to_decimal_favorite_and_underdog():
    assert sh.american_to_decimal("-1000") == pytest.approx(1.1)
    assert sh.american_to_decimal("+2000") == pytest.approx(21.0)


def test_american_to_decimal_zero_raises():
    with pytest.raises(ValueError):
        sh.american_to_decimal("0")


def test_devig_closing_fair_probs_three_way_sums_to_one():
    fair = sh.devig_closing_fair_probs(
        {"home_close": "-1000", "away_close": "+2000", "draw_close": "+1000"})
    assert set(fair) == {"home", "away", "draw"}
    assert fair["home"] == pytest.approx(sum(fair.values()) * fair["home"] / sum(fair.values()))
    assert sum(fair.values()) == pytest.approx(1.0)


def test_devig_closing_fair_probs_two_way_no_draw_key():
    fair = sh.devig_closing_fair_probs({"home_close": "-625", "away_close": "+455"})
    assert set(fair) == {"home", "away"}


def test_devig_closing_fair_probs_none_when_missing_close():
    assert sh.devig_closing_fair_probs({"home_close": "-625", "away_close": None}) is None
    assert sh.devig_closing_fair_probs(None) is None
    assert sh.devig_closing_fair_probs({}) is None


# --------------------------------------------------------------------------- #
# S7b — match_kalshi_espn: matched / ambiguous / no_match / date-window reject
# --------------------------------------------------------------------------- #
def _mk_kalshi_event(event_ticker, title, outcomes=None):
    return {"schema_version": "sports_history_kalshi.v1", "series": event_ticker.split("-")[0],
            "event_ticker": event_ticker, "title": title,
            "outcomes": outcomes if outcomes is not None else []}


def _mk_espn_event(espn_id, name, date, moneyline=None):
    return {"schema_version": "sports_history_espn.v1", "espn_event_id": espn_id,
            "name": name, "date": date, "moneyline": moneyline}


def test_match_kalshi_espn_unique_match():
    ke = [_mk_kalshi_event("KXWCGAME-26JUL02SUIDZA",
                           "Switzerland vs Algeria: Regulation Time Moneyline SUI vs DZA (Jul 2)")]
    ee = [_mk_espn_event("1", "Algeria at Switzerland", "2026-07-02T18:00Z")]
    out = sh.match_kalshi_espn(ke, ee)
    assert len(out) == 1 and out[0]["match_status"] == "matched"
    assert out[0]["espn_event_id"] == "1"
    assert out[0]["orientation"] == "a_home"   # team_a=Switzerland is ESPN's home side


def test_match_kalshi_espn_no_match_different_teams():
    ke = [_mk_kalshi_event("KXWCGAME-26JUL02SUIDZA", "Switzerland vs Algeria")]
    ee = [_mk_espn_event("1", "Brazil at France", "2026-07-02T18:00Z")]
    out = sh.match_kalshi_espn(ke, ee)
    assert out[0]["match_status"] == "no_match"


def test_match_kalshi_espn_ambiguous_when_multiple_candidates():
    ke = [_mk_kalshi_event("KXNBAGAME-26JUN08SASNYK", "San Antonio at New York")]
    ee = [_mk_espn_event("1", "San Antonio Spurs at New York Knicks", "2026-06-08T00:30Z"),
          _mk_espn_event("2", "San Antonio Spurs at New York Knicks", "2026-06-09T00:30Z")]
    out = sh.match_kalshi_espn(ke, ee)
    assert out[0]["match_status"] == "ambiguous"
    assert set(out[0]["candidate_espn_ids"]) == {"1", "2"}


def test_match_kalshi_espn_date_window_rejects_far_kickoff():
    ke = [_mk_kalshi_event("KXWCGAME-26JUL02SUIDZA", "Switzerland vs Algeria")]
    ee = [_mk_espn_event("1", "Algeria at Switzerland", "2026-06-20T18:00Z")]  # 12 days off
    out = sh.match_kalshi_espn(ke, ee)
    assert out[0]["match_status"] == "no_match"


def test_match_kalshi_espn_unparseable_title_flagged_not_dropped():
    ke = [_mk_kalshi_event("KXWCGAME-26JUL02SUIDZA", "Total Corners Over 9.5?")]
    out = sh.match_kalshi_espn(ke, [])
    assert out[0]["match_status"] == "unparseable_title"


# --------------------------------------------------------------------------- #
# S7b — run_clv_join: full offline pass (FakeClient candlesticks, no network)
# --------------------------------------------------------------------------- #
def test_run_clv_join_offline_prices_matched_game(tmp_path):
    import datetime as dt
    kickoff = "2026-07-02T18:00Z"
    kickoff_ts = dt.datetime(2026, 7, 2, 18, 0, tzinfo=dt.timezone.utc)
    end_before = int(kickoff_ts.timestamp()) - 600
    ke = [_mk_kalshi_event("KXWCGAME-26JUL02SUIDZA",
                           "Switzerland vs Algeria: Regulation Time Moneyline SUI vs DZA (Jul 2)",
                           outcomes=[
                               {"ticker": "KXWCGAME-26JUL02SUIDZA-SUI"},
                               {"ticker": "KXWCGAME-26JUL02SUIDZA-DZA"},
                               {"ticker": "KXWCGAME-26JUL02SUIDZA-TIE"},
                           ])]
    ee = [_mk_espn_event("1", "Algeria at Switzerland", kickoff,
                         moneyline={"home_close": "-200", "away_close": "+550",
                                    "draw_close": "+340"})]
    client = FakeClient(
        events_pages=[], markets_by_event={},
        candles_by_ticker={
            "KXWCGAME-26JUL02SUIDZA-SUI": [_mk_candle(end_before, 0.60)],
            "KXWCGAME-26JUL02SUIDZA-DZA": [_mk_candle(end_before, 0.20)],
            "KXWCGAME-26JUL02SUIDZA-TIE": [_mk_candle(end_before, 0.28)],
        },
    )
    summary = sh.run_clv_join(client, ke, ee, tape_dir=tmp_path)
    assert summary["n_matched"] == 1 and summary["n_priced"] == 1
    lines = (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
    rec = json.loads(lines[0])
    assert rec["bracket_sum"] == pytest.approx(1.08)
    sui = next(o for o in rec["outcomes"] if o["outcome_code"] == "SUI")
    assert sui["fair_key"] == "home"   # team_a=Switzerland matched ESPN home
    assert sui["pregame_ask"]["yes_ask"] == pytest.approx(0.60)
    assert sui["fair_prob_source_tag"] == "synthetic"
    assert sui["pregame_ask"]["price_source_tag"] == "real_ask"
    assert "edge_raw" in sui and "edge_after_fee" in sui


def test_run_clv_join_unmatched_games_not_priced(tmp_path):
    ke = [_mk_kalshi_event("KXWCGAME-26JUL02SUIDZA", "Switzerland vs Algeria")]
    ee = [_mk_espn_event("1", "Brazil at France", "2026-07-02T18:00Z")]
    client = FakeClient(events_pages=[], markets_by_event={})
    summary = sh.run_clv_join(client, ke, ee, tape_dir=tmp_path)
    assert summary["n_matched"] == 0 and summary["n_priced"] == 0
    assert summary["match_status_counts"] == {"no_match": 1}
    assert "path" not in summary   # nothing written — no matched games to persist


def test_load_tape_records_filters_by_schema_version(tmp_path):
    p = tmp_path / "dt=2026-07-03.jsonl"
    p.write_text(
        json.dumps({"schema_version": "sports_history_kalshi.v1", "x": 1}) + "\n" +
        json.dumps({"schema_version": "sports_history_espn.v1", "x": 2}) + "\n"
    )
    kalshi = sh.load_tape_records(p, "sports_history_kalshi.v1")
    assert len(kalshi) == 1 and kalshi[0]["x"] == 1


def test_load_tape_records_missing_file_returns_empty(tmp_path):
    assert sh.load_tape_records(tmp_path / "nope.jsonl", "sports_history_kalshi.v1") == []
