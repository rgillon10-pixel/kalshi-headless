"""collection.sports_pairs — ticker parsing, moneyline confirmation, de-vig math, and a
fully offline capture pass (FakeClient, no network) with honest completeness."""
from __future__ import annotations

import json

import pytest

from collection import sports_pairs as sp

# --------------------------------------------------------------------------- #
# ticker parsing
# --------------------------------------------------------------------------- #
def test_parse_sports_ticker_known_shape():
    fields, err = sp.parse_sports_ticker("KXWCGAME-26JUL06USABEL-USA")
    assert err is None
    assert fields == {
        "series": "KXWCGAME", "event": "26JUL06USABEL", "game_date": "2026-07-06",
        "teams_code": "USABEL", "outcome": "USA",
    }


def test_parse_sports_ticker_tie_outcome():
    fields, err = sp.parse_sports_ticker("KXWCGAME-26JUL06USABEL-TIE")
    assert err is None and fields["outcome"] == "TIE"


def test_parse_sports_ticker_bad_shape_fails_loudly():
    spec, err = sp.parse_sports_ticker("NOT-A-VALID-TICKER-SHAPE")
    assert spec is None and err == "no_regex_match"


def test_parse_sports_ticker_bad_date_token():
    spec, err = sp.parse_sports_ticker("KXWCGAME-26XYZ06USABEL-USA")
    assert spec is None and err and err.startswith("bad_date_token")


# --------------------------------------------------------------------------- #
# moneyline group confirmation (structural, not just the series-title heuristic)
# --------------------------------------------------------------------------- #
def test_is_moneyline_group_confirms_3way_soccer():
    markets = [
        {"title": "USA vs Belgium Winner?"},
        {"title": "USA vs Belgium Winner?"},
        {"title": "USA vs Belgium Winner?"},
    ]
    assert sp.is_moneyline_group(markets) is True


def test_is_moneyline_group_rejects_non_winner_titles():
    markets = [{"title": "USA vs Belgium Total Goals"}, {"title": "USA vs Belgium Total Goals"}]
    assert sp.is_moneyline_group(markets) is False


def test_is_moneyline_group_rejects_wrong_outcome_count():
    assert sp.is_moneyline_group([{"title": "USA vs Belgium Winner?"}]) is False
    five = [{"title": "A vs B Winner?"}] * 5
    assert sp.is_moneyline_group(five) is False


# --------------------------------------------------------------------------- #
# de-vig math
# --------------------------------------------------------------------------- #
def test_devig_multiplicative_no_vig_case():
    # decimal odds 1.5 / 3.0 -> implied 0.667/0.333, already sums to 1.0
    out = sp.devig_multiplicative([1.5, 3.0])
    assert out[0] == pytest.approx(2 / 3, abs=1e-9)
    assert out[1] == pytest.approx(1 / 3, abs=1e-9)
    assert sum(out) == pytest.approx(1.0, abs=1e-9)


def test_devig_multiplicative_removes_vig():
    # both sides quoted 1.9 -> implied 0.5263+0.5263=1.0526 overround; devig -> 0.5/0.5
    out = sp.devig_multiplicative([1.9, 1.9])
    assert out[0] == pytest.approx(0.5, abs=1e-9)
    assert out[1] == pytest.approx(0.5, abs=1e-9)


def test_devig_multiplicative_rejects_bad_odds():
    with pytest.raises(ValueError):
        sp.devig_multiplicative([1.0, 2.0])
    with pytest.raises(ValueError):
        sp.devig_multiplicative([])


# --------------------------------------------------------------------------- #
# fully offline capture pass
# --------------------------------------------------------------------------- #
class FakeClient:
    """Minimal stand-in for validation.v3_market.Kalshi — only the read-only methods
    sports_pairs uses, served from in-memory fixtures. No network, no clock."""

    base = "https://fake.test"

    def __init__(self, series_titles, markets_by_series, fail_series=()):
        self.series_titles = series_titles           # {series_ticker: title}
        self.markets_by_series = markets_by_series    # {series_ticker: [market dict, ...]}
        self.fail_series = set(fail_series)

    def series_by_category(self, category):
        return [{"ticker": t, "title": title} for t, title in self.series_titles.items()]

    def get_text(self, path, **params):
        assert path == "/markets"
        sticker = params["series_ticker"]
        if sticker in self.fail_series:
            raise RuntimeError(f"simulated enumeration failure: {sticker}")
        return json.dumps({"markets": self.markets_by_series.get(sticker, [])})


def _mk_market(ticker, title, event_ticker, yes_ask, yes_bid=None, no_ask=None, no_bid=None):
    return {
        "ticker": ticker, "title": title, "event_ticker": event_ticker,
        "yes_ask_dollars": f"{yes_ask:.4f}",
        "yes_bid_dollars": f"{yes_bid:.4f}" if yes_bid is not None else None,
        "no_ask_dollars": f"{no_ask:.4f}" if no_ask is not None else None,
        "no_bid_dollars": f"{no_bid:.4f}" if no_bid is not None else None,
    }


def _three_way_group():
    event = "KXWCGAME-26JUL06USABEL"
    return [
        _mk_market(f"{event}-USA", "USA vs Belgium Winner?", event, 0.37, 0.36, 0.64, 0.63),
        _mk_market(f"{event}-TIE", "USA vs Belgium Winner?", event, 0.28, 0.27, 0.73, 0.72),
        _mk_market(f"{event}-BEL", "USA vs Belgium Winner?", event, 0.39, 0.38, 0.62, 0.61),
    ]


def test_discover_moneyline_series_filters_by_title():
    client = FakeClient(
        series_titles={
            "KXWCGAME": "World Cup Game",
            "KXWCGOAL": "World Cup Goal",       # excluded: prop-bet keyword "goal"
            "KXNBAALLSTARGAME": "NBA All-Star Game Winner",  # excluded: all-star
            "KXNFLGAME": "Professional Football Game",
        },
        markets_by_series={},
    )
    out = sp.discover_moneyline_series(client)
    assert out == ["KXNFLGAME", "KXWCGAME"]


def test_run_captures_confirmed_group_with_honest_bracket_sum(tmp_path):
    client = FakeClient(
        series_titles={"KXWCGAME": "World Cup Game"},
        markets_by_series={"KXWCGAME": _three_way_group()},
    )
    summary = sp.run(client=client, tape_dir=tmp_path)
    assert summary["n_games"] == 1
    assert summary["n_complete"] == 1

    out_path = tmp_path / f"dt={summary['day']}.jsonl"
    lines = [json.loads(ln) for ln in out_path.read_text().splitlines()]
    assert len(lines) == 1
    rec = lines[0]
    assert rec["completeness_ok"] is True
    assert rec["member_count"] == 3
    assert rec["bracket_sum"] == pytest.approx(0.37 + 0.28 + 0.39, abs=1e-9)
    assert rec["overround_absorbed"] == pytest.approx(rec["bracket_sum"] - 1.0, abs=1e-9)
    assert all(o["price_source_tag"] == "real_ask" for o in rec["outcomes"])
    assert rec["odds_leg"] == {"status": "blocked_key"}


def test_run_drops_missing_ask_and_marks_incomplete(tmp_path):
    markets = _three_way_group()
    markets[1]["yes_ask_dollars"] = None    # TIE has no live ask -> dropped, not fabricated
    client = FakeClient(
        series_titles={"KXWCGAME": "World Cup Game"},
        markets_by_series={"KXWCGAME": markets},
    )
    summary = sp.run(client=client, tape_dir=tmp_path)
    out_path = tmp_path / f"dt={summary['day']}.jsonl"
    rec = json.loads(out_path.read_text().splitlines()[0])
    assert rec["captured_outcomes"] == 2
    assert rec["expected_outcomes"] == 3
    assert rec["completeness_ok"] is False


def test_run_ignores_non_moneyline_and_series_errors(tmp_path):
    client = FakeClient(
        series_titles={"KXWCGAME": "World Cup Game", "KXWCGOALX": "World Cup Games Broken"},
        markets_by_series={
            "KXWCGAME": [_mk_market("KXWCGAME-X-A", "A vs B Total Goals",
                                    "KXWCGAME-X", 0.5)],   # not a "Winner?" title -> rejected
        },
        fail_series=["KXWCGOALX"],
    )
    summary = sp.run(client=client, tape_dir=tmp_path)
    assert summary["n_games"] == 0
    assert summary["n_series_errors"] == 1
    assert not (tmp_path / f"dt={summary['day']}.jsonl").exists()


def test_run_reports_odds_key_presence(tmp_path):
    client = FakeClient(
        series_titles={"KXWCGAME": "World Cup Game"},
        markets_by_series={"KXWCGAME": _three_way_group()},
    )
    summary = sp.run(client=client, tape_dir=tmp_path, odds_api_key="fake-key")
    assert summary["odds_api_key_present"] is True
    out_path = tmp_path / f"dt={summary['day']}.jsonl"
    rec = json.loads(out_path.read_text().splitlines()[0])
    assert rec["odds_leg"] == {"status": "unmatched"}
