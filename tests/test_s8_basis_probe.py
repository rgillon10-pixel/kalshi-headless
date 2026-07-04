"""scripts.s8_basis_probe — historical-spot fetch (fixes the ~29min live-spot lag confound),
its cache, and the corrected basis report. Offline: HTTP monkeypatched, no network."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from scripts import s8_basis_probe as probe


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


# --------------------------------------------------------------------------- #
# fetch_historical_spot_coinbase
# --------------------------------------------------------------------------- #
def test_fetch_historical_spot_exact_bucket_match(monkeypatch):
    at = datetime(2026, 7, 4, 2, 0, 0, tzinfo=timezone.utc)
    target_epoch = int(at.timestamp())
    monkeypatch.setattr(probe.requests, "get", lambda url, **kw: _FakeResp(
        [[target_epoch + 60, 62421.98, 62450, 62421.98, 62429.35, 0.9],
         [target_epoch, 62403.49, 62429.99, 62403.5, 62421.98, 2.4]]))
    rec = probe.fetch_historical_spot_coinbase("BTC", at)
    assert rec["status"] == "ok"
    assert rec["price"] == pytest.approx(62403.5)  # open of the exact-matching bucket
    assert rec["lag_seconds"] == 0
    assert rec["price_source_tag"] == "synthetic"


def test_fetch_historical_spot_no_bucket_is_honest_not_fabricated(monkeypatch):
    at = datetime(2026, 7, 4, 2, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(probe.requests, "get", lambda url, **kw: _FakeResp([]))
    rec = probe.fetch_historical_spot_coinbase("BTC", at)
    assert rec["status"] == "no_candle"
    assert "price" not in rec


def test_fetch_historical_spot_network_error_recorded_not_raised(monkeypatch):
    at = datetime(2026, 7, 4, 2, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(probe.requests, "get", lambda url, **kw: (_ for _ in ()).throw(
        RuntimeError("network down")))
    rec = probe.fetch_historical_spot_coinbase("BTC", at)
    assert rec["status"] == "fetch_error"
    assert "price" not in rec


# --------------------------------------------------------------------------- #
# load_or_fetch_historical_spot — cache
# --------------------------------------------------------------------------- #
def _mk_pair(symbol="BTC", event_ticker="KXBTC-26JUL0402", settle_value=62450.0,
             settle_close_iso="2026-07-04T02:00:00Z"):
    return probe.HourPair(
        symbol=symbol, event_ticker=event_ticker, settle_value=settle_value,
        spot_price=62400.0, lag_seconds=1740.0, captured_at="2026-07-04T02:29:00Z",
        settle_close_iso=settle_close_iso,
    )


def test_load_or_fetch_historical_spot_caches_and_skips_refetch(tmp_path):
    calls = []

    def fake_fetcher(symbol, at):
        calls.append((symbol, at))
        return {"status": "ok", "source": "fake", "price": 62403.5, "lag_seconds": 0,
                "price_source_tag": "synthetic"}

    pair = _mk_pair()
    tape_dir = tmp_path / "hist"
    cached1 = probe.load_or_fetch_historical_spot([pair], tape_dir, fetcher=fake_fetcher)
    assert len(calls) == 1
    assert cached1[("BTC", "KXBTC-26JUL0402")]["price"] == pytest.approx(62403.5)
    assert (tape_dir / f"dt={datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl").exists()

    # second call against the same tape_dir must reuse the cache, not refetch
    cached2 = probe.load_or_fetch_historical_spot([pair], tape_dir, fetcher=fake_fetcher)
    assert len(calls) == 1
    assert cached2[("BTC", "KXBTC-26JUL0402")]["price"] == pytest.approx(62403.5)


# --------------------------------------------------------------------------- #
# corrected_basis_report
# --------------------------------------------------------------------------- #
def test_corrected_basis_report_uses_historical_gap_and_lag():
    pairs = [
        _mk_pair(event_ticker="KXBTC-26JUL0400", settle_value=62450.0),
        _mk_pair(event_ticker="KXBTC-26JUL0401", settle_value=62500.0),
    ]
    historical = {
        ("BTC", "KXBTC-26JUL0400"): {"status": "ok", "price": 62448.0, "lag_seconds": 0},
        ("BTC", "KXBTC-26JUL0401"): {"status": "ok", "price": 62490.0, "lag_seconds": 30},
    }
    report = probe.corrected_basis_report(pairs, historical)
    entry = report["BTC"]
    assert entry["n_hours"] == 2
    assert entry["n_dropped_no_historical_spot"] == 0
    assert entry["mean_gap_dollars"] == pytest.approx(((62450 - 62448) + (62500 - 62490)) / 2)
    assert entry["mean_lag_seconds"] == pytest.approx(15.0)
    assert entry["max_lag_seconds"] == 30


def test_corrected_basis_report_drops_failed_fetches_honestly():
    pairs = [
        _mk_pair(event_ticker="KXBTC-26JUL0400", settle_value=62450.0),
        _mk_pair(event_ticker="KXBTC-26JUL0401", settle_value=62500.0),
    ]
    historical = {
        ("BTC", "KXBTC-26JUL0400"): {"status": "ok", "price": 62448.0, "lag_seconds": 0},
        ("BTC", "KXBTC-26JUL0401"): {"status": "no_candle"},
    }
    report = probe.corrected_basis_report(pairs, historical)
    entry = report["BTC"]
    assert entry["n_hours"] == 1
    assert entry["n_dropped_no_historical_spot"] == 1


def test_corrected_basis_report_all_dropped_reports_zero_not_crash():
    pairs = [_mk_pair(event_ticker="KXBTC-26JUL0400")]
    historical = {("BTC", "KXBTC-26JUL0400"): {"status": "fetch_error"}}
    report = probe.corrected_basis_report(pairs, historical)
    assert report["BTC"]["n_hours"] == 0
    assert report["BTC"]["n_dropped_no_historical_spot"] == 1
