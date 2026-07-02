"""Sports paired-odds collector (Q1) — ticker parsing, de-vig math, and the bitemporal
capture discipline (raw-bytes sha256, honest expected-vs-captured completeness), fully
offline via an injected fake client (no network), mirroring test_capture_bitemporal.py."""
from __future__ import annotations

import json

import pytest

from collection import sports_pairs as sp
from core.pricing import bracket_sum


# --------------------------------------------------------------------------- #
# ticker parsing
# --------------------------------------------------------------------------- #
def test_parses_known_moneyline_ticker_shapes():
    parts, err = sp.parse_sports_ticker("KXWCGAME-26JUL06USABEL-USA")
    assert err is None
    assert parts == {"series": "KXWCGAME", "event": "26JUL06USABEL", "outcome": "USA"}

    parts, err = sp.parse_sports_ticker("KXMLBGAME-26JUL051700TORSEA-TOR")
    assert err is None
    assert parts["series"] == "KXMLBGAME" and parts["outcome"] == "TOR"

    parts, err = sp.parse_sports_ticker("KXWCGAME-26JUL06USABEL-TIE")
    assert err is None and parts["outcome"] == "TIE"


def test_malformed_ticker_is_rejected():
    parts, err = sp.parse_sports_ticker("not-a-real-ticker")
    assert parts is None and err == "no_regex_match"

    parts, err = sp.parse_sports_ticker("ONLYONEHYPHEN-NOOUTCOME")
    assert parts is None and err == "no_regex_match"


def test_moneyline_series_classifier():
    assert sp._is_moneyline_series("KXWCGAME")
    assert sp._is_moneyline_series("KXMLBGAME")
    assert not sp._is_moneyline_series("KXNFL2QWINNER")   # quarter winner, not moneyline
    assert not sp._is_moneyline_series("KXNCAAMB2ML")     # exotic combo, not moneyline


def test_soccer_world_cup_sorts_first():
    tickers = ["KXMLBGAME", "KXWCGAME", "KXNBAGAME", "KXCLUBWCGAME"]
    ordered = sorted(tickers, key=sp._sort_key)
    assert ordered[0] in ("KXWCGAME", "KXCLUBWCGAME")
    assert ordered[1] in ("KXWCGAME", "KXCLUBWCGAME")
    assert ordered[2:] == ["KXMLBGAME", "KXNBAGAME"]       # non-soccer stays alphabetical


# --------------------------------------------------------------------------- #
# de-vig math — a model, always tag synthetic (never a fill price)
# --------------------------------------------------------------------------- #
def test_devig_proportional_removes_the_vig():
    # -150/+130 American ~ implied 0.60/0.4643 -> vigged sum 1.0643 (6.43% overround)
    implied = [0.60, 0.4643]
    fair = sp.devig_proportional(implied)
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)
    # proportional de-vig preserves the RATIO between outcomes
    assert fair[0] / fair[1] == pytest.approx(implied[0] / implied[1])


def test_devig_proportional_three_way():
    implied = [0.45, 0.30, 0.30]     # win / tie / lose, 5% overround
    fair = sp.devig_proportional(implied)
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)
    assert fair[1] == pytest.approx(fair[2])   # equal inputs stay equal after de-vig


def test_devig_reuses_sanctioned_bracket_sum():
    implied = [0.5, 0.5, 0.1]
    assert bracket_sum(implied) == pytest.approx(sum(implied))


# --------------------------------------------------------------------------- #
# the-odds-api response parsing — pure function, fixture-driven (no live key needed)
# --------------------------------------------------------------------------- #
_ODDS_FIXTURE = [
    {
        "home_team": "Seattle Mariners", "away_team": "Toronto Blue Jays",
        "commence_time": "2026-07-05T17:00:00Z",
        "bookmakers": [
            {"key": "draftkings", "markets": [{"key": "h2h", "outcomes": [
                {"name": "Seattle Mariners", "price": 1.83},
                {"name": "Toronto Blue Jays", "price": 2.05}]}]},
            {"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
                {"name": "Seattle Mariners", "price": 1.87},
                {"name": "Toronto Blue Jays", "price": 2.10}]}]},
        ],
    },
    {
        "home_team": "No Market Event", "away_team": "Nobody",
        "commence_time": "2026-07-05T18:00:00Z",
        "bookmakers": [],
    },
]


def test_parse_odds_h2h_prefers_pinnacle():
    events = sp._parse_odds_h2h_response(_ODDS_FIXTURE)
    assert len(events) == 1        # the bookmaker-less event is skipped, not fabricated
    ev = events[0]
    assert ev["book"] == "pinnacle"
    assert ev["outcomes"]["Seattle Mariners"] == 1.87


def test_fetch_odds_h2h_blocked_without_key_makes_no_network_call():
    result = sp.fetch_odds_h2h("baseball_mlb", api_key=None)
    assert result == {"status": "blocked", "reason": "ODDS_API_KEY missing"}


# --------------------------------------------------------------------------- #
# full pass — offline via a fake client, bitemporal + completeness discipline
# --------------------------------------------------------------------------- #
class FakeClient:
    """Minimal stand-in for validation.v3_market.Kalshi — only the read-only methods
    sports_pairs uses, served from in-memory fixtures. No network, no clock."""

    def __init__(self, series, markets_by_series, fail_series=()):
        self.series = series                      # [{"ticker": ...}, ...]
        self.markets_by_series = markets_by_series  # {series_ticker: [market_dict, ...]}
        self.fail_series = set(fail_series)

    def series_by_category(self, category):
        return self.series

    def get_text(self, path, **params):
        sticker = params["series_ticker"]
        if sticker in self.fail_series:
            raise RuntimeError(f"simulated enumeration failure: {sticker}")
        return json.dumps({"markets": self.markets_by_series.get(sticker, [])})


def _mkt(ticker, event_ticker, title, yes_ask, yes_bid, no_ask, no_bid):
    return {"ticker": ticker, "event_ticker": event_ticker, "title": title,
            "close_time": "2026-07-05T17:00:00Z",
            "yes_ask_dollars": yes_ask, "yes_bid_dollars": yes_bid,
            "no_ask_dollars": no_ask, "no_bid_dollars": no_bid}


def _lines(store, day, capture_id):
    path = store / f"dt={day}" / f"pass-{capture_id}.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def test_two_way_event_captured_complete_real_ask(tmp_path):
    client = FakeClient(
        [{"ticker": "KXMLBGAME"}],
        {"KXMLBGAME": [
            _mkt("KXMLBGAME-26JUL051700TORSEA-TOR", "KXMLBGAME-26JUL051700TORSEA",
                 "Toronto vs Seattle Winner?", 0.51, 0.50, 0.56, 0.49),
            _mkt("KXMLBGAME-26JUL051700TORSEA-SEA", "KXMLBGAME-26JUL051700TORSEA",
                 "Toronto vs Seattle Winner?", 0.56, 0.44, 0.50, 0.44),
        ]},
    )
    summary = sp.run(client=client, store=tmp_path, odds_api_key=None)
    assert summary["n_events"] == 1 and summary["n_complete"] == 1
    assert summary["odds_api_key_present"] is False

    lines = _lines(tmp_path, summary["day"], summary["capture_id"])
    assert len(lines) == 1
    ln = lines[0]
    assert ln["n_legs"] == 2 and ln["has_tie_leg"] is False and ln["completeness_ok"] is True
    assert all(leg["price_source_tag"] == "real_ask" for leg in ln["legs"])
    assert ln["bracket_sum"] == pytest.approx(1.07)
    assert ln["overround"] == pytest.approx(0.07)
    assert ln["odds"] == {"status": "blocked", "reason": "ODDS_API_KEY missing"}
    assert ln["fetch_ts"] and ln["raw_sha256"]


def test_three_way_soccer_event_captured_complete(tmp_path):
    client = FakeClient(
        [{"ticker": "KXWCGAME"}],
        {"KXWCGAME": [
            _mkt("KXWCGAME-26JUL06USABEL-USA", "KXWCGAME-26JUL06USABEL",
                 "USA vs Belgium Winner?", 0.37, 0.36, 0.64, 0.63),
            _mkt("KXWCGAME-26JUL06USABEL-BEL", "KXWCGAME-26JUL06USABEL",
                 "USA vs Belgium Winner?", 0.33, 0.32, 0.68, 0.67),
            _mkt("KXWCGAME-26JUL06USABEL-TIE", "KXWCGAME-26JUL06USABEL",
                 "USA vs Belgium Winner?", 0.30, 0.29, 0.71, 0.70),
        ]},
    )
    summary = sp.run(client=client, store=tmp_path, odds_api_key=None)
    ln = _lines(tmp_path, summary["day"], summary["capture_id"])[0]
    assert ln["n_legs"] == 3 and ln["has_tie_leg"] is True and ln["completeness_ok"] is True
    assert {leg["outcome"] for leg in ln["legs"]} == {"USA", "BEL", "TIE"}


def test_mixed_tie_and_non_tie_events_in_one_series_both_complete(tmp_path):
    # Regression: a series can mix drawable matches (TIE leg) with non-drawable ones (2
    # legs only) — e.g. live KXLOLGAME mixes best-of formats. Guessing a series-wide
    # "expected leg count" from one event previously mislabeled the other as incomplete;
    # both must be honestly complete since each got every market the API returned for it.
    client = FakeClient(
        [{"ticker": "KXWCGAME"}],
        {"KXWCGAME": [
            _mkt("KXWCGAME-26JUL06USABEL-USA", "KXWCGAME-26JUL06USABEL",
                 "USA vs Belgium Winner?", 0.37, 0.36, 0.64, 0.63),
            _mkt("KXWCGAME-26JUL06USABEL-BEL", "KXWCGAME-26JUL06USABEL",
                 "USA vs Belgium Winner?", 0.33, 0.32, 0.68, 0.67),
            _mkt("KXWCGAME-26JUL06USABEL-TIE", "KXWCGAME-26JUL06USABEL",
                 "USA vs Belgium Winner?", 0.30, 0.29, 0.71, 0.70),
            _mkt("KXWCGAME-26JUL07FRAMEX-FRA", "KXWCGAME-26JUL07FRAMEX",
                 "France vs Mexico Winner?", 0.55, 0.54, 0.46, 0.45),
            _mkt("KXWCGAME-26JUL07FRAMEX-MEX", "KXWCGAME-26JUL07FRAMEX",
                 "France vs Mexico Winner?", 0.46, 0.45, 0.55, 0.54),
        ]},
    )
    summary = sp.run(client=client, store=tmp_path, odds_api_key=None)
    lines = _lines(tmp_path, summary["day"], summary["capture_id"])
    usabel = next(ln for ln in lines if ln["event_ticker"] == "KXWCGAME-26JUL06USABEL")
    framex = next(ln for ln in lines if ln["event_ticker"] == "KXWCGAME-26JUL07FRAMEX")
    assert usabel["n_legs"] == 3 and usabel["has_tie_leg"] is True and usabel["completeness_ok"] is True
    assert framex["n_legs"] == 2 and framex["has_tie_leg"] is False and framex["completeness_ok"] is True
    assert summary["n_complete"] == 2


def test_orphaned_single_leg_event_is_incomplete_not_hidden(tmp_path):
    # a genuine single-market orphan (n_legs < 2) inside an otherwise-paired series is
    # the one structurally-decidable incompleteness signal at this granularity.
    client = FakeClient(
        [{"ticker": "KXWCGAME"}],
        {"KXWCGAME": [
            _mkt("KXWCGAME-26JUL06USABEL-USA", "KXWCGAME-26JUL06USABEL",
                 "USA vs Belgium Winner?", 0.37, 0.36, 0.64, 0.63),
            _mkt("KXWCGAME-26JUL06USABEL-BEL", "KXWCGAME-26JUL06USABEL",
                 "USA vs Belgium Winner?", 0.33, 0.32, 0.68, 0.67),
            _mkt("KXWCGAME-26JUL07FRAMEX-TIE", "KXWCGAME-26JUL07FRAMEX",
                 "France vs Mexico Winner?", 0.30, 0.29, 0.71, 0.70),
        ]},
    )
    summary = sp.run(client=client, store=tmp_path, odds_api_key=None)
    lines = _lines(tmp_path, summary["day"], summary["capture_id"])
    framex = next(ln for ln in lines if ln["event_ticker"] == "KXWCGAME-26JUL07FRAMEX")
    assert framex["n_legs"] == 1 and framex["completeness_ok"] is False
    assert summary["n_complete"] == 1     # only USABEL (2 real legs)


def test_series_enumeration_failure_is_recorded_not_silently_dropped(tmp_path):
    client = FakeClient(
        [{"ticker": "KXMLBGAME"}, {"ticker": "KXNBAGAME"}],
        {"KXNBAGAME": [
            _mkt("KXNBAGAME-26JUL05LALBOS-LAL", "KXNBAGAME-26JUL05LALBOS",
                 "LA Lakers vs Boston Winner?", 0.55, 0.54, 0.47, 0.46),
            _mkt("KXNBAGAME-26JUL05LALBOS-BOS", "KXNBAGAME-26JUL05LALBOS",
                 "LA Lakers vs Boston Winner?", 0.47, 0.46, 0.55, 0.54),
        ]},
        fail_series={"KXMLBGAME"},
    )
    summary = sp.run(client=client, store=tmp_path, odds_api_key=None)
    assert summary["n_series_errors"] == 1
    assert summary["n_events"] == 1        # KXNBAGAME still captured despite KXMLBGAME failing


def test_structurally_single_market_series_excluded_not_marked_incomplete(tmp_path):
    # KXWCTEAMSINGAME-style series: every event has exactly ONE market ("Will X play Y?"),
    # never a paired second leg. Must be excluded as non-moneyline, not emitted as a
    # chronically-incomplete moneyline event (the real bug this test guards against).
    client = FakeClient(
        [{"ticker": "KXWCTEAMSINGAME"}, {"ticker": "KXMLBGAME"}],
        {
            "KXWCTEAMSINGAME": [
                _mkt("KXWCTEAMSINGAME-26ARGPOR-Y", "KXWCTEAMSINGAME-26ARGPOR",
                     "Will Argentina play Portugal in the 2026 World Cup?", 0.10, 0.09, 0.91, 0.90),
            ],
            "KXMLBGAME": [
                _mkt("KXMLBGAME-26JUL051700TORSEA-TOR", "KXMLBGAME-26JUL051700TORSEA",
                     "Toronto vs Seattle Winner?", 0.51, 0.50, 0.56, 0.49),
                _mkt("KXMLBGAME-26JUL051700TORSEA-SEA", "KXMLBGAME-26JUL051700TORSEA",
                     "Toronto vs Seattle Winner?", 0.56, 0.44, 0.50, 0.44),
            ],
        },
    )
    summary = sp.run(client=client, store=tmp_path, odds_api_key=None)
    assert summary["n_series_non_moneyline"] == 1
    lines = _lines(tmp_path, summary["day"], summary["capture_id"])
    assert len(lines) == 1                                   # only the real MLB pair
    assert lines[0]["series_ticker"] == "KXMLBGAME"
    assert all(ln["series_ticker"] != "KXWCTEAMSINGAME" for ln in lines)


def test_no_open_markets_writes_no_file(tmp_path):
    client = FakeClient([{"ticker": "KXMLBGAME"}], {"KXMLBGAME": []})
    summary = sp.run(client=client, store=tmp_path, odds_api_key=None)
    assert summary["n_events"] == 0
    assert not (tmp_path / f"dt={summary['day']}").exists()


def test_odds_key_present_marks_unmatched_not_fabricated(tmp_path):
    client = FakeClient(
        [{"ticker": "KXMLBGAME"}],
        {"KXMLBGAME": [
            _mkt("KXMLBGAME-26JUL051700TORSEA-TOR", "KXMLBGAME-26JUL051700TORSEA",
                 "Toronto vs Seattle Winner?", 0.51, 0.50, 0.56, 0.49),
            _mkt("KXMLBGAME-26JUL051700TORSEA-SEA", "KXMLBGAME-26JUL051700TORSEA",
                 "Toronto vs Seattle Winner?", 0.56, 0.44, 0.50, 0.44),
        ]},
    )
    summary = sp.run(client=client, store=tmp_path, odds_api_key="fake-key-not-used-offline")
    assert summary["odds_api_key_present"] is True
    ln = _lines(tmp_path, summary["day"], summary["capture_id"])[0]
    assert ln["odds"] == {"status": "fetched_unmatched", "reason": "team matching not implemented"}
