"""collection.polymarket_pairs — Kalshi ticker parsing, Polymarket discovery parsing,
(round, team) matching, and a fully offline capture pass (FakeClient + stub pm_discover/
fetch_book, no network) with honest completeness."""
from __future__ import annotations

import json

import pytest

from collection import polymarket_pairs as pp


# --------------------------------------------------------------------------- #
# Kalshi ticker/title parsing
# --------------------------------------------------------------------------- #
def test_parse_kalshi_round_ticker_quarterfinals():
    fields, err = pp.parse_kalshi_round_ticker("KXWCROUND-26QUAR-USA")
    assert err is None
    assert fields == {"series": "KXWCROUND", "round": "quarterfinals", "team_code": "USA"}


def test_parse_kalshi_round_ticker_semifinals_and_final():
    fields, err = pp.parse_kalshi_round_ticker("KXWCROUND-26SEMI-SUI")
    assert err is None and fields["round"] == "semifinals"
    fields, err = pp.parse_kalshi_round_ticker("KXWCROUND-26FINAL-FRA")
    assert err is None and fields["round"] == "final"


def test_parse_kalshi_round_ticker_bad_shape():
    fields, err = pp.parse_kalshi_round_ticker("NOT-A-TICKER")
    assert fields is None and err == "no_regex_match"


def test_parse_kalshi_round_ticker_unknown_round_token():
    fields, err = pp.parse_kalshi_round_ticker("KXWCROUND-26THIRD-USA")
    assert fields is None and err == "unknown_round_token:THIRD"


def test_normalize_team_folds_case_and_punctuation():
    assert pp._normalize_team("USA") == pp._normalize_team(" usa ")
    assert pp._normalize_team("Bosnia and Herzegovina") == "bosniaandherzegovina"


# --------------------------------------------------------------------------- #
# discover_kalshi_round_markets — offline FakeClient
# --------------------------------------------------------------------------- #
class FakeKalshiClient:
    base = "https://fake.test"

    def __init__(self, markets):
        self._markets = markets

    def get_text(self, path, **params):
        assert path == "/markets"
        assert params.get("series_ticker") == pp.KALSHI_ROUND_SERIES
        return json.dumps({"markets": self._markets})


def _kalshi_market(ticker, title, yes_ask=0.20, yes_bid=0.19, no_ask=0.81, no_bid=0.80):
    return {
        "ticker": ticker, "title": title,
        "yes_ask_dollars": yes_ask, "yes_bid_dollars": yes_bid,
        "no_ask_dollars": no_ask, "no_bid_dollars": no_bid,
    }


def test_discover_kalshi_round_markets_parses_team_and_round():
    client = FakeKalshiClient([
        _kalshi_market("KXWCROUND-26QUAR-USA", "Will USA qualify for FIFA World Cup Quarterfinals?"),
        _kalshi_market("KXWCROUND-26SEMI-FRA", "Will France qualify for FIFA World Cup Semifinals?"),
    ])
    out, raw = pp.discover_kalshi_round_markets(client)
    assert len(out) == 2 and len(raw) == 1
    usa = next(m for m in out if m["ticker"] == "KXWCROUND-26QUAR-USA")
    assert usa["round"] == "quarterfinals" and usa["team_name"] == "USA"
    assert usa["yes_ask"] == pytest.approx(0.20) and usa["price_source_tag"] == "real_ask"


def test_discover_kalshi_round_markets_missing_ask_records_none():
    client = FakeKalshiClient([_kalshi_market("KXWCROUND-26QUAR-USA", "Will USA qualify for FIFA World Cup Quarterfinals?",
                                              yes_ask=None)])
    out, _ = pp.discover_kalshi_round_markets(client)
    assert out[0]["yes_ask"] is None


# --------------------------------------------------------------------------- #
# match_pairs — exact (round, team) only; ambiguous/no-match never guessed
# --------------------------------------------------------------------------- #
def _pm(round_, team, event_id="E1", market_id="M1", token="TOK1"):
    return {"event_id": event_id, "market_id": market_id, "round": round_,
            "team_name": team, "question": f"Will {team} reach the {round_}?",
            "yes_token_id": token}


def test_match_pairs_exact_match():
    km = [{"ticker": "KXWCROUND-26QUAR-USA", "round": "quarterfinals", "team_name": "USA"}]
    pm = [_pm("quarterfinals", "USA")]
    matched, unmatched, ambiguous = pp.match_pairs(km, pm)
    assert len(matched) == 1 and not unmatched and not ambiguous
    assert matched[0][1]["team_name"] == "USA"


def test_match_pairs_no_match_recorded_not_dropped():
    km = [{"ticker": "KXWCROUND-26QUAR-USA", "round": "quarterfinals", "team_name": "USA"}]
    matched, unmatched, ambiguous = pp.match_pairs(km, [])
    assert not matched and unmatched == ["KXWCROUND-26QUAR-USA"] and not ambiguous


def test_match_pairs_ambiguous_when_multiple_pm_candidates():
    km = [{"ticker": "KXWCROUND-26QUAR-USA", "round": "quarterfinals", "team_name": "USA"}]
    pm = [_pm("quarterfinals", "USA", market_id="M1"), _pm("quarterfinals", "USA", market_id="M2")]
    matched, unmatched, ambiguous = pp.match_pairs(km, pm)
    assert not matched and not unmatched and ambiguous == ["KXWCROUND-26QUAR-USA"]


def test_match_pairs_unparsed_kalshi_ticker_is_unmatched():
    km = [{"ticker": "KXWCROUND-BAD", "round": None, "team_name": None}]
    matched, unmatched, ambiguous = pp.match_pairs(km, [_pm("quarterfinals", "USA")])
    assert not matched and unmatched == ["KXWCROUND-BAD"] and not ambiguous


# --------------------------------------------------------------------------- #
# discover_polymarket_round_events — offline via monkeypatched requests.get
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _pm_event(title, markets):
    return {"id": "E1", "title": title, "markets": markets}


def _pm_market(team, question, token_yes="TOKY", token_no="TOKN"):
    return {
        "id": f"m-{team}", "groupItemTitle": team, "question": question,
        "outcomes": json.dumps(["Yes", "No"]),
        "clobTokenIds": json.dumps([token_yes, token_no]),
    }


def test_discover_polymarket_round_events_confirms_structurally(monkeypatch):
    events_payload = {"events": [
        _pm_event("World Cup: Nation To Reach Quarterfinals",
                 [_pm_market("USA", "Will USA reach the Quarterfinals at the 2026 FIFA World Cup?")]),
        _pm_event("Some Unrelated Event", [_pm_market("Nobody", "irrelevant")]),
    ]}
    monkeypatch.setattr(pp.requests, "get", lambda url, **kw: _FakeResp(events_payload))
    out, raw = pp.discover_polymarket_round_events(queries=("World Cup Nation to Reach Quarterfinals",))
    assert len(out) == 1
    assert out[0]["round"] == "quarterfinals" and out[0]["team_name"] == "USA"
    assert out[0]["yes_token_id"] == "TOKY"


def test_discover_polymarket_round_events_dedupes_across_queries(monkeypatch):
    events_payload = {"events": [
        _pm_event("World Cup: Nation To Reach Final",
                 [_pm_market("France", "Will France reach the 2026 FIFA World Cup final?")]),
    ]}
    monkeypatch.setattr(pp.requests, "get", lambda url, **kw: _FakeResp(events_payload))
    out, _ = pp.discover_polymarket_round_events(queries=("q1", "q2"))
    assert len(out) == 1


# --------------------------------------------------------------------------- #
# fetch_clob_book
# --------------------------------------------------------------------------- #
def test_fetch_clob_book_best_bid_ask(monkeypatch):
    payload = {"bids": [{"price": "0.10", "size": "5"}, {"price": "0.15", "size": "5"}],
               "asks": [{"price": "0.20", "size": "5"}, {"price": "0.25", "size": "5"}]}
    monkeypatch.setattr(pp.requests, "get", lambda url, **kw: _FakeResp(payload))
    book = pp.fetch_clob_book("TOK1")
    assert book == {"best_bid": pytest.approx(0.15), "best_ask": pytest.approx(0.20)}


def test_fetch_clob_book_empty_sides_return_none(monkeypatch):
    monkeypatch.setattr(pp.requests, "get", lambda url, **kw: _FakeResp({"bids": [], "asks": []}))
    book = pp.fetch_clob_book("TOK1")
    assert book == {"best_bid": None, "best_ask": None}


# --------------------------------------------------------------------------- #
# run() — fully offline, injected client + pm_discover + fetch_book
# --------------------------------------------------------------------------- #
def test_run_full_pass_matches_and_computes_gap(tmp_path):
    client = FakeKalshiClient([
        _kalshi_market("KXWCROUND-26QUAR-USA", "Will USA qualify for FIFA World Cup Quarterfinals?", yes_ask=0.25),
    ])
    pm_markets = [_pm("quarterfinals", "USA", token="TOKY")]

    def fake_pm_discover():
        return pm_markets, ["raw"]

    def fake_fetch_book(token_id):
        assert token_id == "TOKY"
        return {"best_bid": 0.18, "best_ask": 0.20}

    summary = pp.run(client=client, tape_dir=tmp_path,
                     pm_discover=fake_pm_discover, fetch_book=fake_fetch_book)
    assert summary["n_kalshi_markets"] == 1 and summary["n_matched"] == 1
    assert summary["completeness_ok"] is True
    assert not summary["unmatched_kalshi"] and not summary["ambiguous_kalshi"]

    lines = (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["kalshi"]["yes_ask"] == pytest.approx(0.25)
    assert rec["polymarket"]["best_ask"] == pytest.approx(0.20)
    assert rec["price_gap_yes_ask"] == pytest.approx(0.05)
    assert rec["kalshi"]["price_source_tag"] == "real_ask"
    assert rec["polymarket"]["price_source_tag"] == "real_ask"


def test_run_no_match_lowers_completeness_but_never_raises(tmp_path):
    client = FakeKalshiClient([
        _kalshi_market("KXWCROUND-26QUAR-USA", "Will USA qualify for FIFA World Cup Quarterfinals?"),
    ])
    summary = pp.run(client=client, tape_dir=tmp_path,
                     pm_discover=lambda: ([], ["raw"]), fetch_book=lambda t: {"best_bid": 0.1, "best_ask": 0.2})
    assert summary["n_matched"] == 0
    assert summary["unmatched_kalshi"] == ["KXWCROUND-26QUAR-USA"]
    assert summary["completeness_ok"] is False
    assert not (tmp_path / f"dt={summary['day']}.jsonl").exists()


def test_run_polymarket_discovery_error_isolated_not_fatal(tmp_path):
    client = FakeKalshiClient([
        _kalshi_market("KXWCROUND-26QUAR-USA", "Will USA qualify for FIFA World Cup Quarterfinals?"),
    ])

    def raising_pm_discover():
        raise RuntimeError("simulated network failure")

    summary = pp.run(client=client, tape_dir=tmp_path, pm_discover=raising_pm_discover,
                     fetch_book=lambda t: {"best_bid": 0.1, "best_ask": 0.2})
    assert summary["polymarket_discovery_error"] == "simulated network failure"
    assert summary["completeness_ok"] is False
    assert summary["n_matched"] == 0


def test_run_book_fetch_error_recorded_not_fatal(tmp_path):
    client = FakeKalshiClient([
        _kalshi_market("KXWCROUND-26QUAR-USA", "Will USA qualify for FIFA World Cup Quarterfinals?", yes_ask=0.25),
    ])
    pm_markets = [_pm("quarterfinals", "USA", token="TOKY")]

    def raising_fetch_book(token_id):
        raise RuntimeError("simulated CLOB timeout")

    summary = pp.run(client=client, tape_dir=tmp_path, pm_discover=lambda: (pm_markets, ["raw"]),
                     fetch_book=raising_fetch_book)
    assert summary["n_book_errors"] == 1
    assert summary["completeness_ok"] is False
    lines = (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
    rec = json.loads(lines[0])
    assert rec["polymarket"]["book_fetch_ok"] is False
    assert rec["polymarket"]["best_ask"] is None
    assert rec["price_gap_yes_ask"] is None


# --------------------------------------------------------------------------- #
# Fed-decision leg (Q12/S17) — Kalshi ticker+title parsing
# --------------------------------------------------------------------------- #
def test_parse_kalshi_fed_ticker_hike_25bps():
    fields, err = pp.parse_kalshi_fed_ticker(
        "KXFEDDECISION-26JUL-H25", "Will the Federal Reserve Hike rates by 25bps at their July 2026 meeting?")
    assert err is None
    assert fields == {"meeting_key": "2026-07", "bucket": "hike_25"}


def test_parse_kalshi_fed_ticker_hike_over_25bps():
    fields, err = pp.parse_kalshi_fed_ticker(
        "KXFEDDECISION-26JUL-H26", "Will the Federal Reserve Hike rates by >25bps at their July 2026 meeting?")
    assert err is None
    assert fields == {"meeting_key": "2026-07", "bucket": "hike_50plus"}


def test_parse_kalshi_fed_ticker_cut_25bps():
    fields, err = pp.parse_kalshi_fed_ticker(
        "KXFEDDECISION-26JUL-C25", "Will the Federal Reserve Cut rates by 25bps at their July 2026 meeting?")
    assert err is None
    assert fields == {"meeting_key": "2026-07", "bucket": "cut_25"}


def test_parse_kalshi_fed_ticker_no_change_is_zero_bps_hike():
    fields, err = pp.parse_kalshi_fed_ticker(
        "KXFEDDECISION-26JUL-H0", "Will the Federal Reserve Hike rates by 0bps at their July 2026 meeting?")
    assert err is None
    assert fields == {"meeting_key": "2026-07", "bucket": "no_change"}


def test_parse_kalshi_fed_ticker_bad_shape():
    fields, err = pp.parse_kalshi_fed_ticker("NOT-A-TICKER", "irrelevant")
    assert fields is None and err == "no_regex_match"


def test_parse_kalshi_fed_ticker_title_mismatch_never_guessed():
    fields, err = pp.parse_kalshi_fed_ticker("KXFEDDECISION-26JUL-H25", "Some unrelated title")
    assert fields is None and err == "title_no_regex_match"


def test_month_num_accepts_full_name_and_abbreviation():
    assert pp._month_num("July") == 7
    assert pp._month_num("jul") == 7
    assert pp._month_num("nonsense") is None


# --------------------------------------------------------------------------- #
# Fed-decision leg — discover_kalshi_fed_markets (offline FakeClient)
# --------------------------------------------------------------------------- #
class FakeKalshiFedClient:
    base = "https://fake.test"

    def __init__(self, markets):
        self._markets = markets

    def get_text(self, path, **params):
        assert path == "/markets"
        assert params.get("series_ticker") == pp.KALSHI_FED_SERIES
        return json.dumps({"markets": self._markets})


def test_discover_kalshi_fed_markets_parses_meeting_and_bucket():
    client = FakeKalshiFedClient([
        _kalshi_market("KXFEDDECISION-26JUL-H25",
                       "Will the Federal Reserve Hike rates by 25bps at their July 2026 meeting?", yes_ask=0.10),
    ])
    out, raw = pp.discover_kalshi_fed_markets(client)
    assert len(out) == 1 and len(raw) == 1
    m = out[0]
    assert m["meeting_key"] == "2026-07" and m["bucket"] == "hike_25"
    assert m["yes_ask"] == pytest.approx(0.10) and m["price_source_tag"] == "real_ask"


# --------------------------------------------------------------------------- #
# Fed-decision leg — bucket normalization + matching
# --------------------------------------------------------------------------- #
def test_normalize_fed_bucket_no_change():
    assert pp._normalize_fed_bucket("No change") == "no_change"


def test_normalize_fed_bucket_25bps_each_direction():
    assert pp._normalize_fed_bucket("25 bps increase") == "hike_25"
    assert pp._normalize_fed_bucket("25 bps decrease") == "cut_25"


def test_normalize_fed_bucket_50plus_bps_each_direction():
    assert pp._normalize_fed_bucket("50+ bps increase") == "hike_50plus"
    assert pp._normalize_fed_bucket("50+ bps decrease") == "cut_50plus"


def test_normalize_fed_bucket_unrecognized_returns_none():
    assert pp._normalize_fed_bucket("some other label") is None


def test_match_fed_pairs_exact_match():
    km = [{"ticker": "KXFEDDECISION-26JUL-H25", "meeting_key": "2026-07", "bucket": "hike_25"}]
    pmm = [{"meeting_key": "2026-07", "bucket": "hike_25", "event_id": "E1", "market_id": "M1", "yes_token_id": "TOK1"}]
    matched, unmatched, ambiguous = pp.match_fed_pairs(km, pmm)
    assert len(matched) == 1 and not unmatched and not ambiguous


def test_match_fed_pairs_no_match_recorded_not_dropped():
    km = [{"ticker": "KXFEDDECISION-26JUL-H25", "meeting_key": "2026-07", "bucket": "hike_25"}]
    matched, unmatched, ambiguous = pp.match_fed_pairs(km, [])
    assert not matched and unmatched == ["KXFEDDECISION-26JUL-H25"] and not ambiguous


def test_match_fed_pairs_ambiguous_when_multiple_candidates():
    km = [{"ticker": "KXFEDDECISION-26JUL-H25", "meeting_key": "2026-07", "bucket": "hike_25"}]
    pmm = [
        {"meeting_key": "2026-07", "bucket": "hike_25", "event_id": "E1", "market_id": "M1", "yes_token_id": "T1"},
        {"meeting_key": "2026-07", "bucket": "hike_25", "event_id": "E1", "market_id": "M2", "yes_token_id": "T2"},
    ]
    matched, unmatched, ambiguous = pp.match_fed_pairs(km, pmm)
    assert not matched and not unmatched and ambiguous == ["KXFEDDECISION-26JUL-H25"]


def test_match_fed_pairs_unparsed_kalshi_ticker_is_unmatched():
    km = [{"ticker": "KXFEDDECISION-BAD", "meeting_key": None, "bucket": None}]
    pmm = [{"meeting_key": "2026-07", "bucket": "hike_25", "event_id": "E1", "market_id": "M1", "yes_token_id": "T1"}]
    matched, unmatched, ambiguous = pp.match_fed_pairs(km, pmm)
    assert not matched and unmatched == ["KXFEDDECISION-BAD"] and not ambiguous


# --------------------------------------------------------------------------- #
# Fed-decision leg — discover_polymarket_fed_events (offline via monkeypatched requests.get)
# --------------------------------------------------------------------------- #
def _pm_fed_market(question, group_item_title, token_yes="TOKY", token_no="TOKN"):
    return {
        "id": f"m-{group_item_title}", "question": question, "groupItemTitle": group_item_title,
        "outcomes": json.dumps(["Yes", "No"]),
        "clobTokenIds": json.dumps([token_yes, token_no]),
    }


def test_discover_polymarket_fed_events_confirms_structurally(monkeypatch):
    events_payload = {"events": [
        _pm_event("Fed Decision in July?", [
            _pm_fed_market("Will the Fed increase interest rates by 25 bps after the July 2026 meeting?",
                            "25 bps increase"),
        ]),
        _pm_event("Fed decisions (Jul-Oct)", [_pm_fed_market("irrelevant bundle question", "25 bps increase")]),
        _pm_event("How many dissent at the July Fed meeting?", [_pm_fed_market("irrelevant", "1")]),
    ]}
    monkeypatch.setattr(pp.requests, "get", lambda url, **kw: _FakeResp(events_payload))
    out, raw = pp.discover_polymarket_fed_events(queries=("Fed Decision",))
    assert len(out) == 1
    assert out[0]["meeting_key"] == "2026-07" and out[0]["bucket"] == "hike_25"
    assert out[0]["yes_token_id"] == "TOKY"


def test_discover_polymarket_fed_events_dedupes_across_queries(monkeypatch):
    events_payload = {"events": [
        _pm_event("Fed Decision in July?", [
            _pm_fed_market("Will there be no change in Fed interest rates after the July 2026 meeting?",
                            "No change"),
        ]),
    ]}
    monkeypatch.setattr(pp.requests, "get", lambda url, **kw: _FakeResp(events_payload))
    out, _ = pp.discover_polymarket_fed_events(queries=("q1", "q2"))
    assert len(out) == 1


# --------------------------------------------------------------------------- #
# Fed-decision leg — run_fed_decision() fully offline
# --------------------------------------------------------------------------- #
def test_run_fed_decision_matches_and_computes_gap(tmp_path):
    client = FakeKalshiFedClient([
        _kalshi_market("KXFEDDECISION-26JUL-H25",
                       "Will the Federal Reserve Hike rates by 25bps at their July 2026 meeting?", yes_ask=0.10),
    ])
    pm_markets = [{"meeting_key": "2026-07", "bucket": "hike_25", "event_id": "E1", "market_id": "M1",
                   "yes_token_id": "TOKY"}]

    def fake_pm_discover():
        return pm_markets, ["raw"]

    def fake_fetch_book(token_id):
        assert token_id == "TOKY"
        return {"best_bid": 0.08, "best_ask": 0.09}

    summary = pp.run_fed_decision(client=client, tape_dir=tmp_path,
                                   pm_discover=fake_pm_discover, fetch_book=fake_fetch_book)
    assert summary["n_kalshi_markets"] == 1 and summary["n_matched"] == 1
    assert summary["completeness_ok"] is True

    lines = (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["family"] == "fed_decision"
    assert rec["meeting"] == "2026-07" and rec["bucket"] == "hike_25"
    assert rec["kalshi"]["yes_ask"] == pytest.approx(0.10)
    assert rec["polymarket"]["best_ask"] == pytest.approx(0.09)
    assert rec["price_gap_yes_ask"] == pytest.approx(0.01)
    assert rec["kalshi"]["price_source_tag"] == "real_ask"
    assert rec["polymarket"]["price_source_tag"] == "real_ask"


def test_run_fed_decision_kalshi_forward_calendar_unmatched_does_not_fail_completeness(tmp_path):
    """Kalshi lists KXFEDDECISION meetings ~18 months out; Polymarket only creates a
    meeting's event closer to it. A Kalshi market with no Polymarket counterpart yet is
    recorded (`unmatched_kalshi`) but must NOT fail completeness — that's the normal,
    expected state for most of Kalshi's forward calendar, not a data-quality problem."""
    client = FakeKalshiFedClient([
        _kalshi_market("KXFEDDECISION-28JAN-H25",
                       "Will the Federal Reserve Hike rates by 25bps at their January 2028 meeting?"),
    ])
    summary = pp.run_fed_decision(client=client, tape_dir=tmp_path,
                                   pm_discover=lambda: ([], ["raw"]),
                                   fetch_book=lambda t: {"best_bid": 0.1, "best_ask": 0.2})
    assert summary["n_matched"] == 0
    assert summary["unmatched_kalshi"] == ["KXFEDDECISION-28JAN-H25"]
    assert summary["completeness_ok"] is True
    assert not (tmp_path / f"dt={summary['day']}.jsonl").exists()


def test_run_fed_decision_unmatched_polymarket_market_fails_completeness(tmp_path):
    """The other direction DOES fail completeness: a market Polymarket is actively
    quoting right now that this pass failed to pair with any Kalshi ticker (e.g. a
    bucket/meeting mismatch) is a real integrity problem, not forward-calendar noise."""
    client = FakeKalshiFedClient([
        _kalshi_market("KXFEDDECISION-26JUL-H25",
                       "Will the Federal Reserve Hike rates by 25bps at their July 2026 meeting?"),
    ])
    pm_markets = [{"meeting_key": "2026-08", "bucket": "hike_25", "event_id": "E1", "market_id": "M1",
                   "yes_token_id": "TOKY"}]
    summary = pp.run_fed_decision(client=client, tape_dir=tmp_path,
                                   pm_discover=lambda: (pm_markets, ["raw"]),
                                   fetch_book=lambda t: {"best_bid": 0.1, "best_ask": 0.2})
    assert summary["n_matched"] == 0
    assert summary["unmatched_polymarket"] == ["M1"]
    assert summary["completeness_ok"] is False


def test_run_fed_decision_polymarket_discovery_error_isolated_not_fatal(tmp_path):
    client = FakeKalshiFedClient([
        _kalshi_market("KXFEDDECISION-26JUL-H25",
                       "Will the Federal Reserve Hike rates by 25bps at their July 2026 meeting?"),
    ])

    def raising_pm_discover():
        raise RuntimeError("simulated network failure")

    summary = pp.run_fed_decision(client=client, tape_dir=tmp_path, pm_discover=raising_pm_discover,
                                   fetch_book=lambda t: {"best_bid": 0.1, "best_ask": 0.2})
    assert summary["polymarket_discovery_error"] == "simulated network failure"
    assert summary["completeness_ok"] is False
    assert summary["n_matched"] == 0
