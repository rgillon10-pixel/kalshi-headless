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
    assert len(lines) == 2  # 1 pair record + 1 capture_summary (L212)
    rec = json.loads(lines[0])
    assert rec["family"] == "fed_decision"
    assert rec["meeting"] == "2026-07" and rec["bucket"] == "hike_25"
    assert rec["kalshi"]["yes_ask"] == pytest.approx(0.10)
    assert rec["polymarket"]["best_ask"] == pytest.approx(0.09)
    assert rec["price_gap_yes_ask"] == pytest.approx(0.01)
    assert rec["kalshi"]["price_source_tag"] == "real_ask"
    assert rec["polymarket"]["price_source_tag"] == "real_ask"
    assert json.loads(lines[1])["family"] == "capture_summary"


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
    # L212: a zero-match pass still persists its capture_summary line — the file is no
    # longer absent, only empty of pair records.
    lines = (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["family"] == "capture_summary"
    assert rec["completeness_ok"] is True


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

    # L212: even a fully-failed discovery pass (0 lines, real error) still leaves a
    # capture_summary record behind — the exact "zero-line pass is indistinguishable from
    # a non-run" gap the lesson closes.
    lines = (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["family"] == "capture_summary"
    assert rec["polymarket_discovery_error"] == "simulated network failure"
    assert rec["completeness_ok"] is False


def test_run_fed_decision_capture_summary_line_matches_returned_summary_and_own_schema(tmp_path):
    """L212 (2026-07-28 tape audit, D1): the persisted `capture_summary` line must carry the
    same honesty fields the in-process `summary` dict returns (so it is truly recomputable
    from tape alone, not a lossy shadow of it), and must use its OWN `schema_version` — never
    `polymarket_macro_pairs.v1`, the pair-record schema — so every existing reader that
    filters on schema_version or family (`q31_cross_venue_arb_probe`,
    `q48_s55_fomc_lag_probe.load_family_records`) skips it like a foreign record rather than
    mis-parsing it as a pair."""
    client = FakeKalshiFedClient([
        _kalshi_market("KXFEDDECISION-26JUL-H25",
                       "Will the Federal Reserve Hike rates by 25bps at their July 2026 meeting?", yes_ask=0.10),
    ])
    pm_markets = [{"meeting_key": "2026-07", "bucket": "hike_25", "event_id": "E1", "market_id": "M1",
                   "yes_token_id": "TOKY"}]
    summary = pp.run_fed_decision(client=client, tape_dir=tmp_path,
                                   pm_discover=lambda: (pm_markets, ["raw"]),
                                   fetch_book=lambda t: {"best_bid": 0.08, "best_ask": 0.09})

    lines = (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
    assert len(lines) == 2  # 1 matched pair record + 1 capture_summary
    pair_rec = json.loads(lines[0])
    summary_rec = json.loads(lines[1])

    assert pair_rec["family"] == "fed_decision"
    assert summary_rec["family"] == "capture_summary"
    assert summary_rec["schema_version"] == "polymarket_macro_pairs_summary.v1"
    assert summary_rec["schema_version"] != pair_rec["schema_version"]

    for key in ("capture_id", "day", "n_kalshi_markets", "n_polymarket_markets", "n_matched",
                "unmatched_kalshi", "unmatched_polymarket", "ambiguous_kalshi",
                "n_book_errors", "polymarket_discovery_error", "completeness_ok"):
        assert summary_rec[key] == summary[key]

    # Downstream readers that key off schema_version/family must not mis-ingest it.
    from scripts.q31_cross_venue_arb_probe import RESOLUTION_EQUIVALENT_SCHEMAS
    assert summary_rec["schema_version"] not in RESOLUTION_EQUIVALENT_SCHEMAS


# --------------------------------------------------------------------------- #
# L214 — per-leg resolution-terms provenance (schema v2)
# --------------------------------------------------------------------------- #
def _km(title, ticker="KXFEDDECISION-26JUL-H26", bucket="hike_50plus"):
    return {"ticker": ticker, "meeting_key": "2026-07", "bucket": bucket, "title": title}


def _pmm(group_item_title, bucket="hike_50plus", question="q", market_id="M1"):
    return {"meeting_key": "2026-07", "bucket": bucket, "event_id": "E1",
            "market_id": market_id, "question": question,
            "group_item_title": group_item_title, "yes_token_id": "TOKY"}


def test_discover_polymarket_fed_events_carries_group_item_title(monkeypatch):
    """L214: the bucket-label text is the EVIDENCE for the normalized bucket — it used to be
    read and thrown away, which is what made the two venues' terms unauditable downstream."""
    events_payload = {"events": [
        _pm_event("Fed Decision in July?", [
            _pm_fed_market("Will the Fed increase interest rates by 50+ bps after the "
                           "July 2026 meeting?", "50+ bps increase"),
        ]),
    ]}
    monkeypatch.setattr(pp.requests, "get", lambda url, **kw: _FakeResp(events_payload))
    out, _ = pp.discover_polymarket_fed_events(queries=("Fed Decision",))
    assert len(out) == 1
    assert out[0]["group_item_title"] == "50+ bps increase"
    assert out[0]["question"].startswith("Will the Fed increase interest rates by 50+ bps")


def test_fed_bucket_terms_50plus_is_not_equivalent_and_says_why():
    """The canonical L214 asymmetry: Kalshi's title says '>25bps' (a 26-49bp move settles YES),
    Polymarket's label says '50+ bps' (the SAME move settles NO). Same `*_50plus` bucket name,
    different contracts — the verdict must be False, with a note naming it."""
    terms = pp.fed_bucket_terms(
        _km("Will the Federal Reserve Hike rates by >25bps at their July 2026 meeting?"),
        _pmm("50+ bps increase"))
    assert terms["kalshi_basis"] == "hike_gt_25bps"
    assert terms["polymarket_basis"] == "increase_gte_50bps"
    assert terms["terms_equivalent"] is False
    assert terms["note"] and "25" in terms["note"] and "50" in terms["note"]
    # the block names its own scope: a bps-region verdict under a matched meeting key, NOT
    # contract-level settlement equivalence (the adjudicators still differ).
    assert terms["compares"] == "bps_region+meeting_key"
    assert terms["meeting_key_checked"] is True


def test_fed_bucket_terms_cut_50plus_is_not_equivalent_either():
    terms = pp.fed_bucket_terms(
        _km("Will the Federal Reserve Cut rates by >25bps at their July 2026 meeting?",
            ticker="KXFEDDECISION-26JUL-C26", bucket="cut_50plus"),
        _pmm("50+ bps decrease", bucket="cut_50plus"))
    assert terms["kalshi_basis"] == "cut_gt_25bps"
    assert terms["polymarket_basis"] == "decrease_gte_50bps"
    assert terms["terms_equivalent"] is False
    assert terms["note"] is not None


def test_fed_bucket_terms_no_change_is_equivalent():
    terms = pp.fed_bucket_terms(
        _km("Will the Federal Reserve Hike rates by 0bps at their July 2026 meeting?",
            ticker="KXFEDDECISION-26JUL-H0", bucket="no_change"),
        _pmm("No change", bucket="no_change"))
    assert terms["kalshi_basis"] == "no_change_0bps"
    assert terms["polymarket_basis"] == "no_change"
    assert terms["terms_equivalent"] is True
    assert terms["note"] is None


def test_fed_bucket_terms_25bps_buckets_are_equivalent_both_directions():
    hike = pp.fed_bucket_terms(
        _km("Will the Federal Reserve Hike rates by 25bps at their July 2026 meeting?",
            ticker="KXFEDDECISION-26JUL-H25", bucket="hike_25"),
        _pmm("25 bps increase", bucket="hike_25"))
    assert hike["kalshi_basis"] == "hike_25bps" and hike["polymarket_basis"] == "increase_25bps"
    assert hike["terms_equivalent"] is True and hike["note"] is None

    cut = pp.fed_bucket_terms(
        _km("Will the Federal Reserve Cut rates by 25bps at their July 2026 meeting?",
            ticker="KXFEDDECISION-26JUL-C25", bucket="cut_25"),
        _pmm("25 bps decrease", bucket="cut_25"))
    assert cut["kalshi_basis"] == "cut_25bps" and cut["polymarket_basis"] == "decrease_25bps"
    assert cut["terms_equivalent"] is True and cut["note"] is None


def test_fed_bucket_terms_opposite_directions_are_not_equivalent():
    terms = pp.fed_bucket_terms(
        _km("Will the Federal Reserve Hike rates by 25bps at their July 2026 meeting?",
            bucket="hike_25"),
        _pmm("25 bps decrease", bucket="cut_25"))
    assert terms["terms_equivalent"] is False


def test_fed_bucket_terms_missing_text_is_none_never_a_guessed_true():
    """Absent/garbage text on either leg means the terms are UNKNOWN, not agreed. A silent
    True here would be the exact false-assurance L214 exists to prevent."""
    no_kalshi_title = pp.fed_bucket_terms({"ticker": "KXFEDDECISION-26JUL-H26"},
                                          _pmm("50+ bps increase"))
    assert no_kalshi_title["kalshi_basis"] is None
    assert no_kalshi_title["polymarket_basis"] == "increase_gte_50bps"
    assert no_kalshi_title["terms_equivalent"] is None
    assert no_kalshi_title["terms_equivalent"] is not True
    assert no_kalshi_title["note"] is None

    # A v1-shaped Polymarket dict (no `group_item_title` key at all) — same honest unknown.
    no_pm_label = pp.fed_bucket_terms(
        _km("Will the Federal Reserve Hike rates by >25bps at their July 2026 meeting?"),
        {"meeting_key": "2026-07", "bucket": "hike_50plus", "question": "q"})
    assert no_pm_label["polymarket_basis"] is None
    assert no_pm_label["terms_equivalent"] is None
    assert no_pm_label["terms_equivalent"] is not True

    garbage_both = pp.fed_bucket_terms(_km("Some unrelated title"), _pmm("mystery label"))
    assert garbage_both["kalshi_basis"] is None and garbage_both["polymarket_basis"] is None
    assert garbage_both["terms_equivalent"] is None
    assert garbage_both["terms_equivalent"] is not True


def test_fed_bucket_terms_different_meetings_are_not_equivalent():
    """D5: the function compares bps REGIONS, so two legs describing the SAME region at
    DIFFERENT meetings used to come back True. `match_fed_pairs` joins on `meeting_key` first,
    but this is a public importable — the presupposed join key is now checked explicitly."""
    km = _km("Will the Federal Reserve Hike rates by 25bps at their September 2026 meeting?",
             bucket="hike_25")
    km["meeting_key"] = "2026-09"
    pm = _pmm("25 bps increase", bucket="hike_25")
    pm["meeting_key"] = "2099-01"
    terms = pp.fed_bucket_terms(km, pm)
    assert terms["meeting_key_checked"] is True
    assert terms["terms_equivalent"] is False
    assert terms["note"] and "2026-09" in terms["note"] and "2099-01" in terms["note"]
    assert "meeting" in terms["note"]
    # the bases are still reported — the mismatch is the meeting, not the text parse
    assert terms["kalshi_basis"] == "hike_25bps"
    assert terms["polymarket_basis"] == "increase_25bps"


def test_fed_bucket_terms_absent_meeting_key_is_flagged_not_claimed():
    """D5 second half: a leg without a `meeting_key` must NOT be reported as if the join key
    had been verified. The bps verdict is unchanged; only the flag differs."""
    km = _km("Will the Federal Reserve Hike rates by 25bps at their July 2026 meeting?",
             bucket="hike_25")
    km.pop("meeting_key")
    pm = _pmm("25 bps increase", bucket="hike_25")
    terms = pp.fed_bucket_terms(km, pm)
    assert terms["meeting_key_checked"] is False
    assert terms["terms_equivalent"] is True            # bps verdict unchanged
    assert terms["note"] is None
    assert terms["compares"] == "bps_region+meeting_key"

    # ... and the same on the Polymarket side, with a False bps verdict this time
    km2 = _km("Will the Federal Reserve Hike rates by >25bps at their July 2026 meeting?")
    pm2 = _pmm("50+ bps increase")
    pm2.pop("meeting_key")
    terms2 = pp.fed_bucket_terms(km2, pm2)
    assert terms2["meeting_key_checked"] is False
    assert terms2["terms_equivalent"] is False
    assert "resolution terms differ" in terms2["note"]


def test_run_fed_decision_writes_v2_with_every_v1_field_unchanged(tmp_path):
    """L214: v2 is v1 PLUS provenance. Every pre-existing key must keep its exact name and
    value (the expected v1 record is written out explicitly here, not diffed against a golden
    file produced by the new code), and the only additions are text/basis/terms — no price,
    no size, no changed tag."""
    client = FakeKalshiFedClient([
        _kalshi_market("KXFEDDECISION-26JUL-H26",
                       "Will the Federal Reserve Hike rates by >25bps at their July 2026 meeting?",
                       yes_ask=0.03, yes_bid=0.02, no_ask=0.98, no_bid=0.97),
    ])
    pm_markets = [_pmm("50+ bps increase",
                       question="Will the Fed increase interest rates by 50+ bps after the "
                                "July 2026 meeting?")]
    summary = pp.run_fed_decision(client=client, tape_dir=tmp_path,
                                   pm_discover=lambda: (pm_markets, ["raw"]),
                                   fetch_book=lambda tok: {"best_bid": 0.01, "best_ask": 0.02})
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])

    expected_v1 = {
        "schema_version": "polymarket_macro_pairs.v1",
        "capture_id": summary["capture_id"],
        "captured_at": summary["captured_at"],
        "family": "fed_decision",
        "meeting": "2026-07",
        "bucket": "hike_50plus",
        "kalshi": {
            "ticker": "KXFEDDECISION-26JUL-H26",
            "yes_ask": 0.03, "yes_bid": 0.02, "no_ask": 0.98, "no_bid": 0.97,
            "price_source_tag": "real_ask",
        },
        "polymarket": {
            "event_id": "E1", "market_id": "M1",
            "best_bid": 0.01, "best_ask": 0.02,
            "book_fetch_ok": True, "price_source_tag": "real_ask",
        },
        "price_gap_yes_ask": 0.03 - 0.02,
    }

    # (1) every v1 field survives, name and value
    for key, value in expected_v1.items():
        if key == "schema_version":
            continue
        if key in ("kalshi", "polymarket"):
            for leg_key, leg_value in value.items():
                got = rec[key][leg_key]
                assert got == (pytest.approx(leg_value) if isinstance(leg_value, float) else leg_value)
            continue
        assert rec[key] == (pytest.approx(value) if isinstance(value, float) else value)

    # (2) the version bump, and ONLY the sanctioned additions
    assert rec["schema_version"] == "polymarket_macro_pairs.v2"
    assert set(rec) == set(expected_v1) | {"bucket_terms"}
    assert set(rec["kalshi"]) == set(expected_v1["kalshi"]) | {"title", "resolution_basis"}
    assert set(rec["polymarket"]) == set(expected_v1["polymarket"]) | {
        "question", "group_item_title", "resolution_basis"}

    # (3) the provenance itself
    assert rec["kalshi"]["title"] == ("Will the Federal Reserve Hike rates by >25bps at their "
                                      "July 2026 meeting?")
    assert rec["kalshi"]["resolution_basis"] == "kalshi_rulebook"
    assert rec["polymarket"]["group_item_title"] == "50+ bps increase"
    assert rec["polymarket"]["question"].startswith("Will the Fed increase interest rates")
    assert rec["polymarket"]["resolution_basis"] == "uma_oracle"
    assert rec["bucket_terms"] == pp.fed_bucket_terms(
        {"title": rec["kalshi"]["title"], "meeting_key": rec["meeting"]},
        {"group_item_title": rec["polymarket"]["group_item_title"],
         "meeting_key": rec["meeting"]})
    assert rec["bucket_terms"]["terms_equivalent"] is False
    assert rec["bucket_terms"]["note"]
    # the collector always joins on `meeting_key`, so the persisted block says so explicitly
    assert rec["bucket_terms"]["meeting_key_checked"] is True
    assert rec["bucket_terms"]["compares"] == "bps_region+meeting_key"


def test_run_fed_decision_v2_terms_unknown_when_polymarket_text_absent(tmp_path):
    """A Polymarket leg discovered without its label text (e.g. an injected/legacy dict) still
    writes v2 — with `terms_equivalent` None, never True. Absence of evidence is recorded as
    absence, and it does not touch prices or completeness."""
    client = FakeKalshiFedClient([
        _kalshi_market("KXFEDDECISION-26JUL-H26",
                       "Will the Federal Reserve Hike rates by >25bps at their July 2026 meeting?",
                       yes_ask=0.03),
    ])
    pm_markets = [{"meeting_key": "2026-07", "bucket": "hike_50plus", "event_id": "E1",
                   "market_id": "M1", "yes_token_id": "TOKY"}]
    summary = pp.run_fed_decision(client=client, tape_dir=tmp_path,
                                   pm_discover=lambda: (pm_markets, ["raw"]),
                                   fetch_book=lambda tok: {"best_bid": 0.01, "best_ask": 0.02})
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["schema_version"] == "polymarket_macro_pairs.v2"
    assert rec["polymarket"]["group_item_title"] is None
    assert rec["polymarket"]["question"] is None
    assert rec["bucket_terms"]["terms_equivalent"] is None
    assert rec["bucket_terms"]["terms_equivalent"] is not True
    assert rec["kalshi"]["price_source_tag"] == "real_ask"
    assert rec["polymarket"]["price_source_tag"] == "real_ask"
    assert summary["completeness_ok"] is True


def test_v2_schema_is_accepted_by_the_downstream_readers():
    """Both in-repo consumers that gate on the schema string must accept v1 AND v2 — the tape
    is append-only, so a bump that stranded old lines would silently shrink every probe's n."""
    from scripts.q31_cross_venue_arb_probe import RESOLUTION_EQUIVALENT_SCHEMAS
    from scripts.q48_s55_fomc_lag_probe import ACCEPTED_SCHEMA_VERSIONS
    for schema in ("polymarket_macro_pairs.v1", "polymarket_macro_pairs.v2"):
        assert schema in RESOLUTION_EQUIVALENT_SCHEMAS
        assert schema in ACCEPTED_SCHEMA_VERSIONS
    assert "polymarket_macro_pairs_summary.v1" not in ACCEPTED_SCHEMA_VERSIONS


# --------------------------------------------------------------------------- #
# CPI/inflation leg (Q12 follow-up) — derived-transform pairing
# --------------------------------------------------------------------------- #
def _kalshi_cpi_market(event_ticker, floor_strike, yes_ask, strike_type="greater"):
    return {"event_ticker": event_ticker, "floor_strike": floor_strike,
            "strike_type": strike_type, "yes_ask_dollars": yes_ask}


class FakeKalshiCpiClient:
    base = "https://fake.test"

    def __init__(self, markets_by_series):
        self._markets_by_series = markets_by_series

    def get_text(self, path, **params):
        assert path == "/markets"
        return json.dumps({"markets": self._markets_by_series.get(params.get("series_ticker"), [])})


def test_discover_kalshi_cpi_events_parses_series_year_month_and_builds_strike_map():
    client = FakeKalshiCpiClient({
        "KXCPICORE": [
            _kalshi_cpi_market("KXCPICORE-26JUL", 0.2, 0.87),
            _kalshi_cpi_market("KXCPICORE-26JUL", 0.3, 0.30),
        ],
    })
    events, raw = pp.discover_kalshi_cpi_events(client)
    assert len(raw) == 3  # one /markets call per series, even when empty
    entry = events[("cpi_core_mom", 2026, 7)]
    assert entry["event_ticker"] == "KXCPICORE-26JUL"
    assert entry["strikes"] == {0.2: 0.87, 0.3: 0.30}


def test_discover_kalshi_cpi_events_drops_missing_ask_and_non_greater_strikes():
    client = FakeKalshiCpiClient({
        "KXCPICORE": [
            _kalshi_cpi_market("KXCPICORE-26JUL", 0.2, None),
            _kalshi_cpi_market("KXCPICORE-26JUL", 0.3, 0.30, strike_type="less"),
            _kalshi_cpi_market("KXCPICORE-26JUL", 0.4, 0.10),
        ],
    })
    events, _ = pp.discover_kalshi_cpi_events(client)
    assert events[("cpi_core_mom", 2026, 7)]["strikes"] == {0.4: 0.10}


def test_price_cpi_bucket_from_kalshi_floor():
    r = pp.price_cpi_bucket_from_kalshi({0.0: 0.90}, "floor", 0.0)
    assert r["derived_prob"] == pytest.approx(0.10)
    assert r["price_source_tag"] == "synthetic" and r["monotonicity_violation"] is False


def test_price_cpi_bucket_from_kalshi_exact():
    r = pp.price_cpi_bucket_from_kalshi({0.2: 0.60, 0.3: 0.30}, "exact", 0.3)
    assert r["derived_prob"] == pytest.approx(0.30)
    assert r["kalshi_inputs"] == {"exceed_le": 0.2, "exceed_ge": 0.3}


def test_price_cpi_bucket_from_kalshi_ceiling():
    r = pp.price_cpi_bucket_from_kalshi({0.5: 0.08}, "ceiling", 0.6)
    assert r["derived_prob"] == pytest.approx(0.08)
    assert r["kalshi_inputs"] == {"exceed_le": 0.5, "exceed_ge": None}


def test_price_cpi_bucket_from_kalshi_missing_strike_returns_none():
    assert pp.price_cpi_bucket_from_kalshi({0.2: 0.60}, "exact", 0.3) is None
    assert pp.price_cpi_bucket_from_kalshi({}, "floor", 0.0) is None


def test_price_cpi_bucket_from_kalshi_monotonicity_violation_flagged_not_clipped():
    """A thin/stale ladder can price 'exceed 0.2' BELOW 'exceed 0.3' (should never happen
    in a coherent market) — the negative derived probability is recorded honestly, never
    clipped to zero or silently dropped."""
    r = pp.price_cpi_bucket_from_kalshi({0.2: 0.10, 0.3: 0.90}, "exact", 0.3)
    assert r["derived_prob"] == pytest.approx(-0.80)
    assert r["monotonicity_violation"] is True


def test_parse_pm_cpi_bucket_label_floor_variants():
    assert pp._parse_pm_cpi_bucket_label("≤0.0%") == ("floor", 0.0)
    assert pp._parse_pm_cpi_bucket_label("<1.0%") == ("floor", 1.0)


def test_parse_pm_cpi_bucket_label_ceiling_variants():
    assert pp._parse_pm_cpi_bucket_label("0.6%+") == ("ceiling", 0.6)
    assert pp._parse_pm_cpi_bucket_label("≥3.3%") == ("ceiling", 3.3)


def test_parse_pm_cpi_bucket_label_exact():
    assert pp._parse_pm_cpi_bucket_label("0.3%") == ("exact", 0.3)


def test_parse_pm_cpi_bucket_label_unparseable_returns_none():
    assert pp._parse_pm_cpi_bucket_label("no number here") == (None, None)


def test_infer_cpi_year_normal_case():
    # July release (month 7) for a June report (month 6) -> same year
    assert pp._infer_cpi_year(6, "2026-07-15T03:59:00Z") == 2026


def test_infer_cpi_year_december_rollover():
    # January release for a December report -> report year is the PRIOR year
    assert pp._infer_cpi_year(12, "2027-01-14T03:59:00Z") == 2026


def test_infer_cpi_year_missing_end_date_returns_none():
    assert pp._infer_cpi_year(6, None) is None


def _pm_cpi_event(title, markets, event_id="E1", end_date=None):
    ev = {"id": event_id, "title": title, "markets": markets}
    if end_date:
        ev["endDate"] = end_date
    return ev


def _pm_cpi_market(group_item_title, question, market_id=None, token_yes="TOKY", token_no="TOKN"):
    return {"id": market_id or f"m-{group_item_title}", "groupItemTitle": group_item_title,
            "question": question, "outcomes": json.dumps(["Yes", "No"]),
            "clobTokenIds": json.dumps([token_yes, token_no])}


def test_discover_polymarket_cpi_events_confirms_structurally_and_excludes_offtopic(monkeypatch):
    events_payload = {"events": [
        _pm_cpi_event("Core CPI MoM - July 2026", [
            _pm_cpi_market("≤0.0%", "Will Core CPI MoM be 0.0% or less in July?"),
            _pm_cpi_market("0.1%", "Will Core CPI MoM be 0.1% in July?"),
        ]),
        _pm_cpi_event("Japan Core-Core CPI YoY in 2026",
                      [_pm_cpi_market("≤1.9%", "irrelevant, different country/series shape")]),
        _pm_cpi_event("Price of Dozen Eggs in June?", [_pm_cpi_market("<$1.50", "irrelevant, not CPI")]),
    ]}
    monkeypatch.setattr(pp.requests, "get", lambda url, **kw: _FakeResp(events_payload))
    out, raw = pp.discover_polymarket_cpi_events(queries=("CPI",))
    assert len(out) == 1
    ev = out[0]
    assert ev["series_key"] == "cpi_core_mom" and ev["year"] == 2026 and ev["month"] == 7
    assert len(ev["buckets"]) == 2
    floor_bucket = next(b for b in ev["buckets"] if b["bucket_kind"] == "floor")
    assert floor_bucket["bucket_value"] == pytest.approx(0.0) and floor_bucket["yes_token_id"] == "TOKY"


def test_discover_polymarket_cpi_events_infers_year_from_end_date_when_title_has_none(monkeypatch):
    events_payload = {"events": [
        _pm_cpi_event("June Inflation US - Monthly",
                      [_pm_cpi_market("≤0.1%", "Will monthly inflation increase by 0.1% or less in June?")],
                      end_date="2026-07-15T03:59:00Z"),
    ]}
    monkeypatch.setattr(pp.requests, "get", lambda url, **kw: _FakeResp(events_payload))
    out, _ = pp.discover_polymarket_cpi_events(queries=("Inflation",))
    assert len(out) == 1
    assert out[0]["series_key"] == "cpi_mom" and out[0]["year"] == 2026 and out[0]["month"] == 6


def test_discover_polymarket_cpi_events_dedupes_across_queries(monkeypatch):
    events_payload = {"events": [
        _pm_cpi_event("Core CPI MoM - July 2026", [_pm_cpi_market("≤0.0%", "irrelevant")]),
    ]}
    monkeypatch.setattr(pp.requests, "get", lambda url, **kw: _FakeResp(events_payload))
    out, _ = pp.discover_polymarket_cpi_events(queries=("CPI", "Inflation"))
    assert len(out) == 1


def test_run_cpi_matches_and_computes_gap(tmp_path):
    client = FakeKalshiCpiClient({
        "KXCPICORE": [
            _kalshi_cpi_market("KXCPICORE-26JUL", 0.0, 0.90),
            _kalshi_cpi_market("KXCPICORE-26JUL", 0.1, 0.40),
        ],
    })
    pm_events = [{
        "event_id": "E1", "series_key": "cpi_core_mom", "year": 2026, "month": 7,
        "buckets": [{"market_id": "M1", "bucket_kind": "floor", "bucket_value": 0.0,
                     "question": "q", "yes_token_id": "TOKY"}],
    }]
    summary = pp.run_cpi(client=client, tape_dir=tmp_path,
                          pm_discover=lambda: (pm_events, ["raw"]),
                          fetch_book=lambda tok: {"best_bid": 0.08, "best_ask": 0.12})
    assert summary["n_matched"] == 1
    assert summary["n_buckets_total"] == 1 and summary["n_buckets_priced"] == 1
    assert summary["completeness_ok"] is True

    lines = (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["family"] == "cpi" and rec["series"] == "cpi_core_mom" and rec["period"] == "2026-07"
    assert rec["kalshi"]["derived_prob"] == pytest.approx(0.10)
    assert rec["kalshi"]["price_source_tag"] == "synthetic"
    assert rec["polymarket"]["best_ask"] == pytest.approx(0.12)
    assert rec["polymarket"]["price_source_tag"] == "real_ask"
    assert rec["prob_gap"] == pytest.approx(0.10 - 0.12)


def test_run_cpi_kalshi_forward_calendar_unmatched_does_not_fail_completeness(tmp_path):
    """A Kalshi CPI event with no Polymarket counterpart (Kalshi's series typically lists
    events several months further out than Polymarket creates them) is normal, not a
    failure — same rationale as the Fed-decision leg."""
    client = FakeKalshiCpiClient({
        "KXCPICORE": [_kalshi_cpi_market("KXCPICORE-26NOV", 0.0, 0.99)],
    })
    summary = pp.run_cpi(client=client, tape_dir=tmp_path, pm_discover=lambda: ([], ["raw"]),
                          fetch_book=lambda tok: {"best_bid": 0.1, "best_ask": 0.2})
    assert summary["n_matched"] == 0
    assert summary["completeness_ok"] is True
    assert not (tmp_path / f"dt={summary['day']}.jsonl").exists()


def test_run_cpi_unmatched_polymarket_event_fails_completeness(tmp_path):
    client = FakeKalshiCpiClient({"KXCPICORE": [_kalshi_cpi_market("KXCPICORE-26JUL", 0.0, 0.90)]})
    pm_events = [{"event_id": "E1", "series_key": "cpi_core_mom", "year": 2026, "month": 8,
                  "buckets": [{"market_id": "M1", "bucket_kind": "floor", "bucket_value": 0.0,
                               "question": "q", "yes_token_id": "TOKY"}]}]
    summary = pp.run_cpi(client=client, tape_dir=tmp_path, pm_discover=lambda: (pm_events, ["raw"]),
                          fetch_book=lambda tok: {"best_bid": 0.1, "best_ask": 0.2})
    assert summary["n_matched"] == 0
    assert summary["unmatched_polymarket"] == ["E1"]
    assert summary["completeness_ok"] is False


def test_run_cpi_ambiguous_polymarket_events_for_same_period_recorded_not_guessed(tmp_path):
    client = FakeKalshiCpiClient({"KXCPICORE": [_kalshi_cpi_market("KXCPICORE-26JUL", 0.0, 0.90)]})
    pm_events = [
        {"event_id": "E1", "series_key": "cpi_core_mom", "year": 2026, "month": 7, "buckets": []},
        {"event_id": "E2", "series_key": "cpi_core_mom", "year": 2026, "month": 7, "buckets": []},
    ]
    summary = pp.run_cpi(client=client, tape_dir=tmp_path, pm_discover=lambda: (pm_events, ["raw"]),
                          fetch_book=lambda tok: {"best_bid": 0.1, "best_ask": 0.2})
    assert summary["ambiguous_polymarket"] == ["E1"]
    assert summary["completeness_ok"] is False


def test_run_cpi_bucket_missing_kalshi_strike_recorded_and_fails_completeness(tmp_path):
    """A Polymarket bucket whose required Kalshi strike(s) aren't listed (a thin/unlisted
    threshold) is a real integrity gap for that bucket specifically — recorded via
    n_buckets_priced < n_buckets_total, never silently skipped from the count."""
    client = FakeKalshiCpiClient({
        "KXCPICORE": [_kalshi_cpi_market("KXCPICORE-26JUL", 0.0, 0.90)],
    })
    pm_events = [{"event_id": "E1", "series_key": "cpi_core_mom", "year": 2026, "month": 7,
                  "buckets": [{"market_id": "M1", "bucket_kind": "exact", "bucket_value": 0.3,
                               "question": "q", "yes_token_id": "TOKY"}]}]
    summary = pp.run_cpi(client=client, tape_dir=tmp_path, pm_discover=lambda: (pm_events, ["raw"]),
                          fetch_book=lambda tok: {"best_bid": 0.1, "best_ask": 0.2})
    assert summary["n_buckets_total"] == 1 and summary["n_buckets_priced"] == 0
    assert summary["completeness_ok"] is False
    assert not (tmp_path / f"dt={summary['day']}.jsonl").exists()


def test_run_cpi_polymarket_discovery_error_isolated_not_fatal(tmp_path):
    client = FakeKalshiCpiClient({"KXCPICORE": [_kalshi_cpi_market("KXCPICORE-26JUL", 0.0, 0.90)]})

    def raising_pm_discover():
        raise RuntimeError("simulated network failure")

    summary = pp.run_cpi(client=client, tape_dir=tmp_path, pm_discover=raising_pm_discover,
                          fetch_book=lambda tok: {"best_bid": 0.1, "best_ask": 0.2})
    assert summary["polymarket_discovery_error"] == "simulated network failure"
    assert summary["completeness_ok"] is False
    assert summary["n_matched"] == 0
