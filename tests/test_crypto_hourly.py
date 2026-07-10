"""Crypto-hourly settlement-basis capture (Q2) — bitemporal, honest-completeness,
content-hashed, spot/settle legs paired for S8's ρ-guard.

Mirrors tests/test_sports_pairs.py's discipline: run() is exercised fully offline via
injected fake Kalshi + spot clients (no network), writing to a tmp store.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from collection import crypto_hourly as ch
from core.crypto_schema import CRYPTO_SCHEMA_VERSION, sign, validate, verify_signature

NOW = datetime(2026, 7, 10, 0, 16, 0, tzinfo=timezone.utc)


class FakeClient:
    """Minimal stand-in for validation.v3_market.Kalshi — open_markets + markets(status),
    served from in-memory fixtures."""

    base = "https://fake.test"

    def __init__(self, open_by_series, settled_by_series=None, fail_series=()):
        self.open_by_series = open_by_series
        self.settled_by_series = settled_by_series or {}
        self.fail_series = set(fail_series)

    def open_markets(self, series_ticker):
        if series_ticker in self.fail_series:
            raise RuntimeError(f"simulated series failure: {series_ticker}")
        return self.open_by_series.get(series_ticker, [])

    def markets(self, series_ticker, status, limit=1000):
        if status == "settled":
            return self.settled_by_series.get(series_ticker, [])
        return self.open_by_series.get(series_ticker, [])


class FakeSpotClient:
    def __init__(self, price=None, exchange=""):
        self.price = price
        self.exchange = exchange

    def spot(self, coinbase_product, kraken_pair):
        return self.price, self.exchange


def _market(ticker, event_ticker, open_time, close_time, yes_ask, expiration_value=None):
    m = {"ticker": ticker, "event_ticker": event_ticker,
         "open_time": open_time, "close_time": close_time, "yes_ask_dollars": yes_ask}
    if expiration_value is not None:
        m["expiration_value"] = expiration_value
    return m


# Current hourly ladder: 3 outcome markets, straddles NOW, duration exactly 1h.
_HOURLY = [
    _market("KXBTC-26JUL0921-T70799.99", "KXBTC-26JUL0921",
           "2026-07-10T00:00:00Z", "2026-07-10T01:00:00Z", "0.05"),
    _market("KXBTC-26JUL0921-B70750", "KXBTC-26JUL0921",
           "2026-07-10T00:00:00Z", "2026-07-10T01:00:00Z", "0.60"),
    _market("KXBTC-26JUL0921-T52200", "KXBTC-26JUL0921",
           "2026-07-10T00:00:00Z", "2026-07-10T01:00:00Z", "0.38"),
]
# Standing ~7-day "range" event under the SAME series_ticker (the real Kalshi shape).
_WEEKLY = [
    _market("KXBTC-26JUL1017-T70000", "KXBTC-26JUL1017",
           "2026-07-03T20:00:00Z", "2026-07-10T21:00:00Z", "0.40"),
]
# The PREVIOUS hour's settled event: close_time == the hourly ladder's open_time.
_PREV_SETTLED = [
    _market("KXBTC-26JUL0920-T70799.99", "KXBTC-26JUL0920",
           "2026-07-09T23:00:00Z", "2026-07-10T00:00:00Z", "0.00",
           expiration_value="63193.52"),
    _market("KXBTC-26JUL0920-B70750", "KXBTC-26JUL0920",
           "2026-07-09T23:00:00Z", "2026-07-10T00:00:00Z", "1.00",
           expiration_value="63193.52"),
]


def _manifest_lines(store):
    path = store / "_manifest.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _capture_dir(store, summary):
    return store / f"dt={summary['day']}" / f"capture-{summary['capture_id']}"


# --------------------------------------------------------------------------- #
# find_current_hourly_event — duration-based selection, not ticker parsing
# --------------------------------------------------------------------------- #
def test_prefers_the_straddling_hourly_event_over_the_weekly_one():
    events = ch.group_by_event(_HOURLY + _WEEKLY)
    picked = ch.find_current_hourly_event(events, NOW)
    assert picked == "KXBTC-26JUL0921"


def test_falls_back_to_closest_duration_when_nothing_straddles_now():
    # NOW is well outside every candidate's [open, close) window.
    far_now = datetime(2027, 1, 1, tzinfo=timezone.utc)
    events = ch.group_by_event(_HOURLY + _WEEKLY)
    picked = ch.find_current_hourly_event(events, far_now)
    assert picked == "KXBTC-26JUL0921"   # duration 3600s beats the weekly one's ~7d


def test_no_events_returns_none():
    assert ch.find_current_hourly_event({}, NOW) is None


# --------------------------------------------------------------------------- #
# happy path — one symbol, complete hourly ladder + spot + prior settlement
# --------------------------------------------------------------------------- #
def test_complete_pass_emits_valid_paired_manifest(tmp_path):
    client = FakeClient(
        open_by_series={"KXBTC": _HOURLY + _WEEKLY, "KXETH": []},
        settled_by_series={"KXBTC": _PREV_SETTLED},
    )
    spot_client = FakeSpotClient(price=63190.12, exchange="coinbase")
    summary = ch.run(client=client, store=tmp_path, spot_client=spot_client, now=NOW)

    assert summary["n_captured"] == 1   # KXETH has no open markets -> degenerate
    assert summary["n_degenerate"] == 1

    lines = _manifest_lines(tmp_path)
    assert len(lines) == 1
    m = lines[0]
    assert validate(m) == [], validate(m)
    assert m["schema_version"] == CRYPTO_SCHEMA_VERSION
    assert m["symbol"] == "BTC"
    assert m["series_ticker"] == "KXBTC"
    assert m["event_ticker"] == "KXBTC-26JUL0921"
    assert m["n_outcomes"] == m["expected_outcomes"] == 3
    assert m["completeness_ok"] is True
    assert m["price_source_tag"] == "real_ask"
    # Hard Rule #3: bracket_sum/overround via core.pricing, 0.05+0.60+0.38 = 1.03
    assert m["bracket_sum"] == pytest.approx(1.03, abs=1e-9)
    assert m["overround"] == pytest.approx(0.03, abs=1e-9)
    # spot leg
    assert m["spot_status"] == "ok"
    assert m["spot_price"] == pytest.approx(63190.12)
    assert m["spot_exchange"] == "coinbase"
    assert m["spot_source_tag"] == "synthetic"
    # settle leg — the previous hour's Kalshi-reported settlement value
    assert m["settle_status"] == "ok"
    assert m["prev_event_ticker"] == "KXBTC-26JUL0920"
    assert m["settle_value"] == pytest.approx(63193.52)
    assert m["settle_source_tag"] == "broker_truth"
    assert verify_signature(m)
    assert ch.verify_against_dir(m, _capture_dir(tmp_path, summary)) == []


# --------------------------------------------------------------------------- #
# degradation: missing hourly event, single-outcome, series failure
# --------------------------------------------------------------------------- #
def test_no_open_markets_recorded_degenerate(tmp_path):
    client = FakeClient(open_by_series={"KXBTC": [], "KXETH": []})
    summary = ch.run(client=client, store=tmp_path, spot_client=FakeSpotClient(1.0, "coinbase"),
                     now=NOW)
    assert summary["n_captured"] == 0
    assert summary["n_degenerate"] == 2
    assert _manifest_lines(tmp_path) == []


def test_single_outcome_hourly_event_recorded_degenerate(tmp_path):
    lone = [_market("KXBTC-26JUL0921-ONLY", "KXBTC-26JUL0921",
                    "2026-07-10T00:00:00Z", "2026-07-10T01:00:00Z", "0.50")]
    client = FakeClient(open_by_series={"KXBTC": lone, "KXETH": []})
    summary = ch.run(client=client, store=tmp_path, spot_client=FakeSpotClient(1.0, "coinbase"),
                     now=NOW)
    assert summary["n_captured"] == 0
    assert summary["n_degenerate"] == 2   # KXBTC single-outcome + KXETH empty
    assert _manifest_lines(tmp_path) == []


def test_series_error_recorded_others_still_captured(tmp_path):
    client = FakeClient(
        open_by_series={"KXBTC": _HOURLY, "KXETH": []},
        settled_by_series={"KXBTC": _PREV_SETTLED},
        fail_series={"KXETH"},
    )
    summary = ch.run(client=client, store=tmp_path, spot_client=FakeSpotClient(1.0, "coinbase"),
                     now=NOW)
    assert summary["n_series_errors"] == 1
    assert summary["n_captured"] == 1


# --------------------------------------------------------------------------- #
# spot / settle leg degradation: honest status, never poisons the Kalshi leg
# --------------------------------------------------------------------------- #
def test_spot_fetch_failure_recorded_kalshi_leg_still_captured(tmp_path):
    client = FakeClient(
        open_by_series={"KXBTC": _HOURLY, "KXETH": []},
        settled_by_series={"KXBTC": _PREV_SETTLED},
    )
    summary = ch.run(client=client, store=tmp_path, spot_client=FakeSpotClient(None, ""), now=NOW)
    m = _manifest_lines(tmp_path)[0]
    assert m["spot_status"] == "fetch_error"
    assert m["spot_price"] == 0.0
    assert m["price_source_tag"] == "real_ask"   # Kalshi leg unaffected
    assert validate(m) == []


def test_settle_not_found_when_no_matching_previous_hour(tmp_path):
    client = FakeClient(
        open_by_series={"KXBTC": _HOURLY, "KXETH": []},
        settled_by_series={"KXBTC": []},   # no settled markets at all this pass
    )
    summary = ch.run(client=client, store=tmp_path, spot_client=FakeSpotClient(1.0, "coinbase"),
                     now=NOW)
    m = _manifest_lines(tmp_path)[0]
    assert m["settle_status"] == "not_found"
    assert m["prev_event_ticker"] == ""
    assert m["settle_value"] == 0.0
    assert validate(m) == []


def test_settle_fetch_error_when_settled_query_raises(tmp_path):
    class RaisingSettledClient(FakeClient):
        def markets(self, series_ticker, status, limit=1000):
            if status == "settled":
                raise RuntimeError("simulated settled-query failure")
            return super().markets(series_ticker, status, limit)

    client = RaisingSettledClient(open_by_series={"KXBTC": _HOURLY, "KXETH": []})
    summary = ch.run(client=client, store=tmp_path, spot_client=FakeSpotClient(1.0, "coinbase"),
                     now=NOW)
    m = _manifest_lines(tmp_path)[0]
    assert m["settle_status"] == "fetch_error"


# --------------------------------------------------------------------------- #
# provenance: a forged hash passes schema but fails the byte-binding check
# --------------------------------------------------------------------------- #
def test_forged_hash_passes_schema_but_fails_provenance(tmp_path):
    client = FakeClient(
        open_by_series={"KXBTC": _HOURLY, "KXETH": []},
        settled_by_series={"KXBTC": _PREV_SETTLED},
    )
    summary = ch.run(client=client, store=tmp_path, spot_client=FakeSpotClient(1.0, "coinbase"),
                     now=NOW)
    real = _manifest_lines(tmp_path)[0]
    cdir = _capture_dir(tmp_path, summary)
    forged = sign({**real, "raw_sha256": "0" * 64})
    assert validate(forged) == []
    assert ch.verify_against_dir(forged, cdir)
    assert ch.verify_against_dir(real, cdir) == []


# --------------------------------------------------------------------------- #
# schema adversarial checks — the "ok" -> tag consistency rules
# --------------------------------------------------------------------------- #
def _valid_record(**overrides):
    base = {
        "schema_version": CRYPTO_SCHEMA_VERSION, "capture_id": "20260710T001600Z",
        "venue": "kalshi", "symbol": "BTC", "series_ticker": "KXBTC",
        "event_ticker": "KXBTC-26JUL0921", "event_time": "2026-07-10T00:00:00Z",
        "close_time": "2026-07-10T01:00:00Z", "as_of": "2026-07-10T00:16:00Z",
        "captured_at": "2026-07-10T00:16:00Z",
        "source_endpoint": "https://fake.test/markets",
        "raw_sha256": "a" * 64, "n_outcomes": 3, "expected_outcomes": 3,
        "bracket_sum": 1.03, "overround": 0.03, "price_source_tag": "real_ask",
        "spot_price": 63190.12, "spot_exchange": "coinbase", "spot_status": "ok",
        "spot_source_tag": "synthetic", "prev_event_ticker": "KXBTC-26JUL0920",
        "prev_close_time": "2026-07-10T00:00:00Z", "settle_value": 63193.52,
        "settle_status": "ok", "settle_source_tag": "broker_truth",
        "outcomes": ["a", "b", "c"], "completeness_ok": True, "warmup": True,
        "signature": "",
    }
    base.update(overrides)
    return sign(base)


def test_schema_rejects_synthetic_tag_mislabeled_as_ok_spot():
    rec = _valid_record(spot_source_tag="real_ask")
    errs = validate(rec)
    assert any("spot_source_tag" in e for e in errs)


def test_schema_rejects_settle_ok_without_broker_truth_tag():
    rec = _valid_record(settle_source_tag="synthetic")
    errs = validate(rec)
    assert any("settle_source_tag" in e for e in errs)


def test_schema_valid_record_passes():
    assert validate(_valid_record()) == []
