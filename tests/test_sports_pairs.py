"""Sports moneyline BBO capture — ticker parsing, de-vig math, and the same honest-
completeness discipline as test_capture_bitemporal.py, adapted to head-to-head events.
"""
from __future__ import annotations

import json
import os

import pytest

from collection import sports_pairs as sp
from core.manifest_schema import verify_signature


# --------------------------------------------------------------------------- #
# ticker parsing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ticker,series,date,matchup", [
    ("KXWCGAME-26JUL09FRAMAR", "KXWCGAME", "2026-07-09", "FRAMAR"),
    ("KXMLBGAME-26JUL112110AZLAD", "KXMLBGAME", "2026-07-11", "AZLAD"),
    ("KXNFLGAME-26AUG15DALSEA", "KXNFLGAME", "2026-08-15", "DALSEA"),
    ("KXMLSGAME-26JUL16MTLTOR", "KXMLSGAME", "2026-07-16", "MTLTOR"),
])
def test_parse_event_ticker(ticker, series, date, matchup):
    parsed = sp.parse_event_ticker(ticker)
    assert parsed == {"series": series, "target_date": date, "matchup_code": matchup}


@pytest.mark.parametrize("ticker", ["not-a-ticker", "KXWCGAME", "KXWCGAME-26XYZ09FRAMAR"])
def test_parse_event_ticker_rejects_garbage(ticker):
    assert sp.parse_event_ticker(ticker) is None


# --------------------------------------------------------------------------- #
# de-vig (pure function, independent of any live odds fetch)
# --------------------------------------------------------------------------- #
def test_devig_multiplicative_normalizes_to_one():
    # -110/-110 American ~ 1.909/1.909 decimal -> raw implied sums > 1 (the vig)
    fair = sp.devig_multiplicative([1.909, 1.909])
    assert fair == pytest.approx([0.5, 0.5], abs=1e-6)
    assert sum(fair) == pytest.approx(1.0)


def test_devig_multiplicative_three_way():
    fair = sp.devig_multiplicative([2.5, 3.4, 3.9])
    assert sum(fair) == pytest.approx(1.0)
    assert all(0 < p < 1 for p in fair)


def test_devig_multiplicative_rejects_bad_input():
    with pytest.raises(ValueError):
        sp.devig_multiplicative([1.9])          # needs >=2 outcomes
    with pytest.raises(ValueError):
        sp.devig_multiplicative([0.9, 1.9])     # decimal odds must be > 1.0


# --------------------------------------------------------------------------- #
# discovery — allowlist suffix + denylist + World Cup priority
# --------------------------------------------------------------------------- #
class _SeriesOnlyClient:
    def __init__(self, tickers):
        self._tickers = tickers

    def series_by_category(self, category):
        return [{"ticker": t} for t in self._tickers]


def test_discover_series_filters_suffix_and_denylist_worldcup_first():
    cfg = {
        "category": "Sports",
        "series_ticker_suffixes": ["GAME", "GAMES"],
        "series_ticker_denylist": ["KXNBAPTSALLGAMES"],
    }
    client = _SeriesOnlyClient(
        ["KXWCGAME", "KXMLBGAME", "KXNBAPTSALLGAMES", "KXATPGAMETOTAL", "KXNFLGAME"])
    out = sp.discover_series(client, cfg)
    assert out[0] == "KXWCGAME"                       # priority first
    assert set(out) == {"KXWCGAME", "KXMLBGAME", "KXNFLGAME"}   # denylist + non-suffix excluded


# --------------------------------------------------------------------------- #
# capture — offline via a FakeClient (no network), mirroring test_capture_bitemporal.py
# --------------------------------------------------------------------------- #
def _market(ticker, side, yes_bid, yes_ask, no_bid, no_ask, title="A vs B Winner?"):
    return {"ticker": ticker, "yes_sub_title": side, "title": title,
            "yes_bid_dollars": str(yes_bid), "yes_ask_dollars": str(yes_ask),
            "no_bid_dollars": str(no_bid), "no_ask_dollars": str(no_ask)}


class FakeClient:
    base = "https://fake.test/trade-api/v2"

    def __init__(self, series_events, fail_series=()):
        self._series_events = series_events   # {series_ticker: [event, ...]}
        self._fail = set(fail_series)

    def series_by_category(self, category):
        return [{"ticker": t} for t in self._series_events]

    def paginate(self, path, key, *, max_items=20000, **params):
        assert path == "/events"
        series = params["series_ticker"]
        if series in self._fail:
            raise RuntimeError(f"simulated /events failure: {series}")
        return self._series_events[series]


_CFG = {
    "category": "Sports",
    "series_ticker_suffixes": ["GAME", "GAMES"],
    "series_ticker_denylist": [],
}


def _manifest_lines(store):
    path = store / "_manifest.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def test_complete_two_way_event_captured_and_signed(tmp_path, monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    event = {
        "event_ticker": "KXNFLGAME-26AUG15DALSEA", "mutually_exclusive": True,
        "markets": [
            _market("KXNFLGAME-26AUG15DALSEA-DAL", "Dallas", 0.44, 0.46, 0.53, 0.56),
            _market("KXNFLGAME-26AUG15DALSEA-SEA", "Seattle", 0.53, 0.56, 0.44, 0.46),
        ],
    }
    client = FakeClient({"KXNFLGAME": [event]})
    summary = sp.run(client=client, cfg=_CFG, store=tmp_path)

    assert summary["n_events"] == 1 and summary["n_complete"] == 1
    assert summary["odds_leg"] == "BLOCKED(key)"
    lines = _manifest_lines(tmp_path)
    assert len(lines) == 1
    rec = lines[0]
    assert verify_signature(rec)
    assert rec["completeness_ok"] is True
    assert rec["n_legs"] == rec["expected_legs"] == 2
    assert rec["warmup"] is True
    assert rec["as_of"] == rec["captured_at"]
    assert all(l["price_source_tag"] == "real_ask" for l in rec["legs"])
    # bracket_sum computed via the sanctioned site (core.pricing), not by hand
    assert rec["bracket_sum"] == pytest.approx(0.46 + 0.56)


def test_three_way_soccer_event_includes_tie_leg(tmp_path):
    event = {
        "event_ticker": "KXWCGAME-26JUL09FRAMAR", "mutually_exclusive": True,
        "markets": [
            _market("KXWCGAME-26JUL09FRAMAR-FRA", "France", 0.61, 0.62, 0.38, 0.39),
            _market("KXWCGAME-26JUL09FRAMAR-MAR", "Morocco", 0.10, 0.11, 0.89, 0.90),
            _market("KXWCGAME-26JUL09FRAMAR-TIE", "Tie", 0.24, 0.26, 0.74, 0.76),
        ],
    }
    client = FakeClient({"KXWCGAME": [event]})
    summary = sp.run(client=client, cfg=_CFG, store=tmp_path)
    assert summary["n_events"] == 1
    rec = _manifest_lines(tmp_path)[0]
    assert rec["n_legs"] == 3
    assert {l["side_name"] for l in rec["legs"]} == {"France", "Morocco", "Tie"}


def test_dropped_leg_lowers_completeness_not_hidden(tmp_path):
    good = _market("KXNFLGAME-26AUG15DALSEA-DAL", "Dallas", 0.44, 0.46, 0.53, 0.56)
    bad = {"ticker": "KXNFLGAME-26AUG15DALSEA-SEA", "yes_sub_title": "Seattle",
           "title": "Dallas vs Seattle Pro Football game?"}   # missing price fields -> DROP
    event = {"event_ticker": "KXNFLGAME-26AUG15DALSEA", "mutually_exclusive": True,
             "markets": [good, bad]}
    client = FakeClient({"KXNFLGAME": [event]})
    summary = sp.run(client=client, cfg=_CFG, store=tmp_path)
    rec = _manifest_lines(tmp_path)[0]
    assert rec["completeness_ok"] is False
    assert rec["n_legs"] == 1 and rec["expected_legs"] == 2
    assert summary["n_complete"] == 0


def test_non_mutually_exclusive_event_skipped(tmp_path):
    event = {"event_ticker": "KXWEIRD-26JUL09XX", "mutually_exclusive": False,
             "markets": [_market("A", "a", 0.4, 0.5, 0.5, 0.6),
                        _market("B", "b", 0.4, 0.5, 0.5, 0.6)]}
    client = FakeClient({"KXWCGAME": [event]})
    summary = sp.run(client=client, cfg=_CFG, store=tmp_path)
    assert summary["n_events"] == 0 and summary["n_events_skipped"] == 1
    assert _manifest_lines(tmp_path) == []


def test_single_leg_event_skipped_not_force_fit(tmp_path):
    event = {"event_ticker": "KXWCGAME-26JUL09FRAMAR", "mutually_exclusive": True,
             "markets": [_market("KXWCGAME-26JUL09FRAMAR-FRA", "France", 0.6, 0.62, 0.38, 0.4)]}
    client = FakeClient({"KXWCGAME": [event]})
    summary = sp.run(client=client, cfg=_CFG, store=tmp_path)
    assert summary["n_events"] == 0 and summary["n_events_skipped"] == 1


def test_series_fetch_failure_recorded_not_hidden(tmp_path):
    event = {"event_ticker": "KXWCGAME-26JUL09FRAMAR", "mutually_exclusive": True,
             "markets": [_market("KXWCGAME-26JUL09FRAMAR-FRA", "France", 0.6, 0.62, 0.38, 0.4),
                        _market("KXWCGAME-26JUL09FRAMAR-MAR", "Morocco", 0.1, 0.12, 0.88, 0.9)]}
    client = FakeClient({"KXWCGAME": [event], "KXNFLGAME": []}, fail_series={"KXNFLGAME"})
    summary = sp.run(client=client, cfg=_CFG, store=tmp_path)
    assert summary["n_series_errors"] == 1
    assert summary["n_events"] == 1   # the surviving series still captured


def test_odds_leg_key_present_flagged_not_wired(tmp_path, monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "fake-key-not-printed")
    event = {"event_ticker": "KXWCGAME-26JUL09FRAMAR", "mutually_exclusive": True,
             "markets": [_market("KXWCGAME-26JUL09FRAMAR-FRA", "France", 0.6, 0.62, 0.38, 0.4),
                        _market("KXWCGAME-26JUL09FRAMAR-MAR", "Morocco", 0.1, 0.12, 0.88, 0.9)]}
    client = FakeClient({"KXWCGAME": [event]})
    summary = sp.run(client=client, cfg=_CFG, store=tmp_path)
    assert summary["odds_leg"] == "present_not_wired"


def test_capture_writes_only_under_given_store(tmp_path):
    event = {"event_ticker": "KXWCGAME-26JUL09FRAMAR", "mutually_exclusive": True,
             "markets": [_market("KXWCGAME-26JUL09FRAMAR-FRA", "France", 0.6, 0.62, 0.38, 0.4),
                        _market("KXWCGAME-26JUL09FRAMAR-MAR", "Morocco", 0.1, 0.12, 0.88, 0.9)]}
    client = FakeClient({"KXWCGAME": [event]})
    summary = sp.run(client=client, cfg=_CFG, store=tmp_path)
    written = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()}
    assert "_manifest.jsonl" in written
    assert any(name.endswith(".raw.json") for name in written)
