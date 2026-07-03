"""collection.crypto_hourly — hour-token arithmetic, current-group discovery (excluding a
stray long-lived group under the same series), settlement fetch, spot fallback, and a fully
offline capture pass (FakeClient, no network) with honest completeness."""
from __future__ import annotations

import json

import pytest

from collection import crypto_hourly as ch

# --------------------------------------------------------------------------- #
# hour-token arithmetic
# --------------------------------------------------------------------------- #
def test_parse_hour_token_known_shape():
    dt = ch.parse_hour_token("26JUL0302")
    assert dt is not None
    assert (dt.year, dt.month, dt.day, dt.hour) == (2026, 7, 3, 2)


def test_parse_hour_token_bad_shape():
    assert ch.parse_hour_token("NOT-A-TOKEN") is None


def test_previous_hour_event_ticker_simple():
    assert ch.previous_hour_event_ticker("KXBTC-26JUL0302") == "KXBTC-26JUL0301"


def test_previous_hour_event_ticker_day_rollover():
    assert ch.previous_hour_event_ticker("KXBTC-26JUL0300") == "KXBTC-26JUL0223"


def test_previous_hour_event_ticker_month_rollover():
    assert ch.previous_hour_event_ticker("KXBTC-26AUG0100") == "KXBTC-26JUL3123"


def test_previous_hour_event_ticker_bad_ticker():
    assert ch.previous_hour_event_ticker("garbage") is None


# --------------------------------------------------------------------------- #
# current-hour group discovery
# --------------------------------------------------------------------------- #
def _mk_market(ticker, event_ticker, close_time, open_time, yes_ask=0.10,
               yes_bid=None, no_ask=None, no_bid=None, floor_strike=None, cap_strike=None):
    return {
        "ticker": ticker, "event_ticker": event_ticker,
        "title": "Bitcoin price range", "close_time": close_time, "open_time": open_time,
        "floor_strike": floor_strike, "cap_strike": cap_strike, "strike_type": "greater",
        "yes_ask_dollars": f"{yes_ask:.4f}" if yes_ask is not None else None,
        "yes_bid_dollars": f"{yes_bid:.4f}" if yes_bid is not None else None,
        "no_ask_dollars": f"{no_ask:.4f}" if no_ask is not None else None,
        "no_bid_dollars": f"{no_bid:.4f}" if no_bid is not None else None,
    }


class FakeClient:
    """Minimal stand-in for validation.v3_market.Kalshi — only the read-only methods
    crypto_hourly uses, served from in-memory fixtures. No network, no clock."""

    base = "https://fake.test"

    def __init__(self, markets_by_series=None, markets_by_event=None,
                fail_series=(), fail_events=()):
        self.markets_by_series = markets_by_series or {}
        self.markets_by_event = markets_by_event or {}
        self.fail_series = set(fail_series)
        self.fail_events = set(fail_events)

    def get_text(self, path, **params):
        assert path == "/markets"
        if "series_ticker" in params:
            sticker = params["series_ticker"]
            if sticker in self.fail_series:
                raise RuntimeError(f"simulated enumeration failure: {sticker}")
            return json.dumps({"markets": self.markets_by_series.get(sticker, [])})
        et = params["event_ticker"]
        if et in self.fail_events:
            raise RuntimeError(f"simulated settlement fetch failure: {et}")
        return json.dumps({"markets": self.markets_by_event.get(et, [])})


def test_discover_current_hour_group_excludes_stray_long_lived_group():
    # genuine hourly group: 1h duration, closes soonest
    hourly = [_mk_market("KXBTC-26JUL0302-T69300", "KXBTC-26JUL0302",
                         "2026-07-03T06:00:00Z", "2026-07-03T05:00:00Z", yes_ask=0.20)]
    # stray group under the same series: same ticker grammar, but open ~1 week
    stray = [_mk_market("KXBTC-26JUL0317-T69300", "KXBTC-26JUL0317",
                        "2026-07-03T21:00:00Z", "2026-06-26T20:00:00Z", yes_ask=0.30)]
    client = FakeClient(markets_by_series={"KXBTC": hourly + stray})
    et, markets, raw_pages, err = ch.discover_current_hour_group(client, "KXBTC")
    assert err is None
    assert et == "KXBTC-26JUL0302"
    assert len(markets) == 1
    assert raw_pages


def test_discover_current_hour_group_no_hourly_group_found():
    stray = [_mk_market("KXBTC-26JUL0317-T69300", "KXBTC-26JUL0317",
                        "2026-07-03T21:00:00Z", "2026-06-26T20:00:00Z")]
    client = FakeClient(markets_by_series={"KXBTC": stray})
    et, markets, raw_pages, err = ch.discover_current_hour_group(client, "KXBTC")
    assert et is None and markets == [] and err == "no_hourly_group_found"


def test_discover_current_hour_group_series_error():
    client = FakeClient(markets_by_series={}, fail_series=["KXBTC"])
    et, markets, raw_pages, err = ch.discover_current_hour_group(client, "KXBTC")
    assert et is None and err and "simulated" in err


# --------------------------------------------------------------------------- #
# outcome capture — honest completeness
# --------------------------------------------------------------------------- #
def test_capture_outcomes_drops_missing_ask():
    markets = [
        _mk_market("KXBTC-26JUL0302-T69300", "KXBTC-26JUL0302",
                  "2026-07-03T06:00:00Z", "2026-07-03T05:00:00Z", yes_ask=0.20),
        _mk_market("KXBTC-26JUL0302-B69200", "KXBTC-26JUL0302",
                  "2026-07-03T06:00:00Z", "2026-07-03T05:00:00Z", yes_ask=None),
    ]
    outcomes, yes_asks = ch._capture_outcomes(markets)
    assert len(outcomes) == 1 and yes_asks == [0.20]
    assert all(o["price_source_tag"] == "real_ask" for o in outcomes)


# --------------------------------------------------------------------------- #
# previous-hour settlement
# --------------------------------------------------------------------------- #
def test_fetch_settlement_settled():
    markets = [
        {"ticker": "KXBTC-26JUL0301-B59450", "result": "no", "expiration_value": "61387.31"},
        {"ticker": "KXBTC-26JUL0301-B65450", "result": "no", "expiration_value": "61387.31"},
    ]
    client = FakeClient(markets_by_event={"KXBTC-26JUL0301": markets})
    rec = ch.fetch_settlement(client, "KXBTC-26JUL0301")
    assert rec["status"] == "settled"
    assert rec["expiration_value"] == "61387.31"
    assert rec["price_source_tag"] == "broker_truth"
    assert rec["results"] == {"KXBTC-26JUL0301-B59450": "no", "KXBTC-26JUL0301-B65450": "no"}


def test_fetch_settlement_pending():
    markets = [
        {"ticker": "A", "result": "no", "expiration_value": "1"},
        {"ticker": "B", "result": "", "expiration_value": None},
    ]
    client = FakeClient(markets_by_event={"EVT": markets})
    rec = ch.fetch_settlement(client, "EVT")
    assert rec["status"] == "pending"


def test_fetch_settlement_not_found():
    client = FakeClient(markets_by_event={})
    rec = ch.fetch_settlement(client, "MISSING")
    assert rec["status"] == "not_found"


def test_fetch_settlement_fetch_error():
    client = FakeClient(fail_events=["EVT"])
    rec = ch.fetch_settlement(client, "EVT")
    assert rec["status"] == "fetch_error"


def test_fetch_settlement_disagreeing_expiration_values_surfaced_not_hidden():
    markets = [
        {"ticker": "A", "result": "no", "expiration_value": "1"},
        {"ticker": "B", "result": "yes", "expiration_value": "2"},
    ]
    client = FakeClient(markets_by_event={"EVT": markets})
    rec = ch.fetch_settlement(client, "EVT")
    assert rec["expiration_value"] is None
    assert rec["expiration_values_disagree"] == ["1", "2"]


# --------------------------------------------------------------------------- #
# spot fallback (Coinbase primary, Kraken fallback) — monkeypatched HTTP
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


def test_fetch_spot_coinbase_success(monkeypatch):
    monkeypatch.setattr(ch.requests, "get", lambda url, **kw: _FakeResp(
        {"price": "61451.02", "bid": "61451.01", "ask": "61451.03", "time": "t"}))
    rec = ch.fetch_spot_coinbase("BTC")
    assert rec["source"] == "coinbase" and rec["price"] == pytest.approx(61451.02)
    assert rec["price_source_tag"] == "synthetic"


def test_fetch_spot_falls_back_to_kraken_on_coinbase_failure(monkeypatch):
    def fake_get(url, **kw):
        if "coinbase" in url:
            raise RuntimeError("coinbase down")
        return _FakeResp({"error": [], "result": {"XXBTZUSD": {
            "c": ["61453.20000", "0.001"], "b": ["61453.10000", "1", "1"],
            "a": ["61453.20000", "1", "1"]}}})
    monkeypatch.setattr(ch.requests, "get", fake_get)
    rec = ch.fetch_spot("BTC")
    assert rec["source"] == "kraken" and rec["price"] == pytest.approx(61453.20)


def test_fetch_spot_both_fail_records_error_not_stale_price(monkeypatch):
    monkeypatch.setattr(ch.requests, "get", lambda url, **kw: (_ for _ in ()).throw(
        RuntimeError("network down")))
    rec = ch.fetch_spot("BTC")
    assert rec.get("status") == "fetch_error"
    assert "price" not in rec


# --------------------------------------------------------------------------- #
# fully offline capture pass
# --------------------------------------------------------------------------- #
def _fake_spot_ok(symbol):
    return {"source": "fake", "price": 61000.0, "bid": 60999.0, "ask": 61001.0,
            "exchange_time": "t", "price_source_tag": "synthetic"}


def test_run_captures_current_and_settlement_end_to_end(tmp_path):
    current = [
        _mk_market("KXBTC-26JUL0302-T69300", "KXBTC-26JUL0302",
                  "2026-07-03T06:00:00Z", "2026-07-03T05:00:00Z", yes_ask=0.20, yes_bid=0.19),
        _mk_market("KXBTC-26JUL0302-B69200", "KXBTC-26JUL0302",
                  "2026-07-03T06:00:00Z", "2026-07-03T05:00:00Z", yes_ask=0.35, yes_bid=0.34),
    ]
    settlement = [
        {"ticker": "KXBTC-26JUL0301-A", "result": "no", "expiration_value": "61387.31"},
    ]
    client = FakeClient(
        markets_by_series={"KXBTC": current},
        markets_by_event={"KXBTC-26JUL0301": settlement},
    )
    summary = ch.run(client=client, tape_dir=tmp_path, symbols={"BTC": "KXBTC"},
                     spot_fetcher=_fake_spot_ok)
    assert summary["n_symbols"] == 1 and summary["n_complete"] == 1

    out_path = tmp_path / f"dt={summary['day']}.jsonl"
    rec = json.loads(out_path.read_text().splitlines()[0])
    assert rec["symbol"] == "BTC"
    assert rec["current"]["completeness_ok"] is True
    assert rec["current"]["member_count"] == 2
    assert rec["current"]["bracket_sum"] == pytest.approx(0.20 + 0.35, abs=1e-9)
    assert rec["current"]["overround_absorbed"] == pytest.approx(rec["current"]["bracket_sum"] - 1.0)
    assert rec["previous_settlement"]["status"] == "settled"
    assert rec["previous_settlement"]["expiration_value"] == "61387.31"
    assert rec["spot"]["price"] == 61000.0
    assert rec["pass_complete"] is True


def test_run_marks_incomplete_when_no_hourly_group_found(tmp_path):
    stray = [_mk_market("KXBTC-26JUL0317-T69300", "KXBTC-26JUL0317",
                        "2026-07-03T21:00:00Z", "2026-06-26T20:00:00Z")]
    client = FakeClient(markets_by_series={"KXBTC": stray})
    summary = ch.run(client=client, tape_dir=tmp_path, symbols={"BTC": "KXBTC"},
                     spot_fetcher=_fake_spot_ok)
    assert summary["n_complete"] == 0
    out_path = tmp_path / f"dt={summary['day']}.jsonl"
    rec = json.loads(out_path.read_text().splitlines()[0])
    assert rec["current"]["status"] == "no_hourly_group_found"
    assert rec["previous_settlement"]["status"] == "no_current_group"
    assert rec["pass_complete"] is False


def test_run_two_symbols_independent(tmp_path):
    current_btc = [_mk_market("KXBTC-26JUL0302-T1", "KXBTC-26JUL0302",
                              "2026-07-03T06:00:00Z", "2026-07-03T05:00:00Z", yes_ask=0.5)]
    current_eth = [_mk_market("KXETH-26JUL0302-T1", "KXETH-26JUL0302",
                              "2026-07-03T06:00:00Z", "2026-07-03T05:00:00Z", yes_ask=0.4)]
    client = FakeClient(markets_by_series={"KXBTC": current_btc, "KXETH": current_eth})
    summary = ch.run(client=client, tape_dir=tmp_path,
                     symbols={"BTC": "KXBTC", "ETH": "KXETH"}, spot_fetcher=_fake_spot_ok)
    assert summary["n_symbols"] == 2
    out_path = tmp_path / f"dt={summary['day']}.jsonl"
    recs = [json.loads(ln) for ln in out_path.read_text().splitlines()]
    assert {r["symbol"] for r in recs} == {"BTC", "ETH"}
