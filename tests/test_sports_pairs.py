"""Sports paired-odds capture (Q1) — bitemporal, honest-completeness, content-hashed.

Mirrors tests/test_capture_bitemporal.py's discipline for the event/outcome shape:
run() is exercised fully offline via injected fake Kalshi + odds clients (no network),
writing to a tmp store.
"""
from __future__ import annotations

import json

import pytest

from collection import sports_pairs as sp
from core.sports_schema import SPORTS_SCHEMA_VERSION, validate, verify_signature


class FakeClient:
    """Minimal stand-in for validation.v3_market.Kalshi — series_by_category +
    open_markets only, served from in-memory fixtures."""

    base = "https://fake.test"

    def __init__(self, series_markets, fail_series=()):
        self.series_markets = series_markets   # {series_ticker: [market_dict, ...]}
        self.fail_series = set(fail_series)

    def series_by_category(self, category):
        return [{"ticker": s} for s in self.series_markets]

    def open_markets(self, series_ticker):
        if series_ticker in self.fail_series:
            raise RuntimeError(f"simulated series failure: {series_ticker}")
        return self.series_markets[series_ticker]


def _market(ticker, event_ticker, title, sub_title, yes_ask, no_ask, close_time="2026-07-12T04:00:00Z"):
    return {
        "ticker": ticker, "event_ticker": event_ticker, "title": title,
        "yes_sub_title": sub_title, "yes_ask_dollars": yes_ask, "no_ask_dollars": no_ask,
        "close_time": close_time,
    }


_ARGSUI = [
    _market("KXWCGAME-26JUL11ARGSUI-TIE", "KXWCGAME-26JUL11ARGSUI",
           "Argentina vs Switzerland Winner?", "Reg Time: Tie", "0.27", "0.74"),
    _market("KXWCGAME-26JUL11ARGSUI-SUI", "KXWCGAME-26JUL11ARGSUI",
           "Argentina vs Switzerland Winner?", "Reg Time: Switzerland", "0.16", "0.85"),
    _market("KXWCGAME-26JUL11ARGSUI-ARG", "KXWCGAME-26JUL11ARGSUI",
           "Argentina vs Switzerland Winner?", "Reg Time: Argentina", "0.58", "0.43"),
]


def _manifest_lines(store):
    path = store / "_manifest.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _capture_dir(store, summary):
    return store / f"dt={summary['day']}" / f"capture-{summary['capture_id']}"


# --------------------------------------------------------------------------- #
# ticker parsing
# --------------------------------------------------------------------------- #
def test_parse_market_ticker_three_way():
    event, outcome = sp.parse_market_ticker("KXWCGAME-26JUL11ARGSUI-TIE")
    assert event == "KXWCGAME-26JUL11ARGSUI"
    assert outcome == "TIE"


def test_parse_market_ticker_rejects_unfamiliar_shape():
    with pytest.raises(ValueError):
        sp.parse_market_ticker("SINGLEWORDNOHYPHENS")


def test_reconcile_event_ticker_matches():
    assert sp.reconcile_event_ticker("KXWCGAME-26JUL11ARGSUI-TIE",
                                     "KXWCGAME-26JUL11ARGSUI") is None


def test_reconcile_event_ticker_mismatch_recorded():
    msg = sp.reconcile_event_ticker("KXWCGAME-26JUL11ARGSUI-TIE", "KXWCGAME-WRONGEVENT")
    assert msg is not None and "!=" in msg   # descriptive, not a crash


def test_priority_ordering_world_cup_first():
    client = FakeClient({"KXNBAGAME": [], "KXWCGAME": [], "KXMLBGAME": []})
    ordered = sp.discover_candidate_series(client)
    assert ordered[0] == "KXWCGAME"
    assert ordered[1:] == sorted(["KXNBAGAME", "KXMLBGAME"])


# --------------------------------------------------------------------------- #
# happy path — a complete 3-way event capture
# --------------------------------------------------------------------------- #
def test_complete_event_emits_valid_bitemporal_manifest(tmp_path):
    client = FakeClient({"KXWCGAME": _ARGSUI})
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_events"] == 1
    assert summary["total_outcomes"] == 3

    lines = _manifest_lines(tmp_path)
    assert len(lines) == 1
    m = lines[0]
    assert validate(m) == [], validate(m)
    assert m["schema_version"] == SPORTS_SCHEMA_VERSION
    assert m["event_ticker"] == "KXWCGAME-26JUL11ARGSUI"
    assert m["sport_series"] == "KXWCGAME"
    assert m["n_outcomes"] == m["expected_outcomes"] == 3
    assert m["completeness_ok"] is True
    assert m["price_source_tag"] == "real_ask"
    assert m["odds_leg_status"] == "blocked_no_key"    # no ODDS_API_KEY injected
    # Hard Rule #3: bracket_sum/overround via core.pricing, real asks 0.27+0.16+0.58=1.01
    assert m["bracket_sum"] == pytest.approx(1.01, abs=1e-9)
    assert m["overround"] == pytest.approx(0.01, abs=1e-9)
    assert verify_signature(m)
    assert sp.verify_against_dir(m, _capture_dir(tmp_path, summary)) == []


# --------------------------------------------------------------------------- #
# a single-outcome group cannot price a bracket — recorded, no line emitted
# --------------------------------------------------------------------------- #
def test_degenerate_single_outcome_emits_no_line(tmp_path):
    lone = [_market("KXFOO-26JUL01-ONLY", "KXFOO-26JUL01", "Solo Market", "Only", "0.50", "0.51")]
    client = FakeClient({"KXFOOGAME": lone})
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_events"] == 0 and summary["n_degenerate"] == 1
    assert _manifest_lines(tmp_path) == []


# --------------------------------------------------------------------------- #
# a whole-series enumeration failure is recorded, not hidden; others still run
# --------------------------------------------------------------------------- #
def test_series_error_recorded_others_still_captured(tmp_path):
    client = FakeClient({"KXWCGAME": _ARGSUI, "KXBROKENGAME": []},
                        fail_series={"KXBROKENGAME"})
    summary = sp.run(client=client, store=tmp_path)
    assert summary["n_series_errors"] == 1
    assert summary["n_events"] == 1


# --------------------------------------------------------------------------- #
# odds leg: key present, matched odds -> synthetic de-vig persisted alongside real_ask
# --------------------------------------------------------------------------- #
class FakeOddsClient:
    def __init__(self, payload):
        self.payload = payload

    def sport_odds(self, sport_key, **kw):
        return self.payload


_ODDS_PAYLOAD = [{
    "home_team": "Argentina", "away_team": "Switzerland",
    "bookmakers": [{"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
        {"name": "Argentina", "price": -180},
        {"name": "Switzerland", "price": 425},
        {"name": "Draw", "price": 310},
    ]}]}],
}]


def test_odds_leg_ok_when_matched(tmp_path):
    client = FakeClient({"KXWCGAME": _ARGSUI})
    odds_client = FakeOddsClient(_ODDS_PAYLOAD)
    summary = sp.run(client=client, store=tmp_path, odds_api_key="fake-key",
                     odds_client=odds_client)
    m = _manifest_lines(tmp_path)[0]
    assert m["odds_leg_status"] == "ok"
    devig_file = _capture_dir(tmp_path, summary) / f"{sp._slug(m['event_ticker'])}.odds_devig.json"
    assert devig_file.exists()
    payload = json.loads(devig_file.read_text())
    assert payload["price_source_tag"] == "synthetic"
    assert sum(payload["fair_probability"].values()) == pytest.approx(1.0, abs=1e-6)


def test_odds_leg_no_match_when_unmapped_series(tmp_path):
    client = FakeClient({"KXWCGAME": _ARGSUI})
    odds_client = FakeOddsClient([])   # no matching event
    summary = sp.run(client=client, store=tmp_path, odds_api_key="fake-key",
                     odds_client=odds_client)
    m = _manifest_lines(tmp_path)[0]
    assert m["odds_leg_status"] == "no_match"


# --------------------------------------------------------------------------- #
# provenance: a forged hash passes schema but fails the byte-binding check
# --------------------------------------------------------------------------- #
def test_forged_hash_passes_schema_but_fails_provenance(tmp_path):
    from core.sports_schema import sign
    client = FakeClient({"KXWCGAME": _ARGSUI})
    summary = sp.run(client=client, store=tmp_path)
    real = _manifest_lines(tmp_path)[0]
    cdir = _capture_dir(tmp_path, summary)
    forged = sign({**real, "raw_sha256": "0" * 64})
    assert validate(forged) == []
    assert sp.verify_against_dir(forged, cdir)
    assert sp.verify_against_dir(real, cdir) == []
