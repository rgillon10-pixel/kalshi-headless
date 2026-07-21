"""collection.hf_burst — fully offline (FakeClient, injected fake clocks, no network).

Covers: target resolution (series expansion, literal + ticker: forms, dedup, per-series
enumeration failure = resolve_error, L10 truncation cap), single-round record shape / source
tags / derived-ask math / both orderbook shapes, fault isolation (one bad ticker is a DROP that
lowers completeness but never kills the round), the window loop over an injected monotonic clock
(N rounds, JSONL append, monotonic + seq per line), overrun boundary-skip (no catch-up pile-up),
cadence-floor rejection, and the honest zero-round exits (no tickers / non-positive window)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from collection import hf_burst as hb


# --------------------------------------------------------------------------- #
# FakeClient + fake clocks
# --------------------------------------------------------------------------- #
def _ob_fp(yes_levels, no_levels):
    return {"orderbook_fp": {
        "yes_dollars": [[str(p), str(s)] for p, s in yes_levels],
        "no_dollars": [[str(p), str(s)] for p, s in no_levels]}}


def _ob_legacy(yes_cents, no_cents):
    return {"orderbook": {"yes": [[c, s] for c, s in yes_cents],
                          "no": [[c, s] for c, s in no_cents]}}


def _mkt(ticker):
    return {"ticker": ticker}


class FakeClient:
    base = "https://fake.test"

    def __init__(self, markets_by_series=None, books=None, fail_series=(), fail_tickers=()):
        self.markets_by_series = markets_by_series or {}
        self.books = books or {}
        self.fail_series = set(fail_series)
        self.fail_tickers = set(fail_tickers)
        self.get_calls = []

    def open_markets(self, series_ticker):
        if series_ticker in self.fail_series:
            raise RuntimeError(f"enumeration failure: {series_ticker}")
        return list(self.markets_by_series.get(series_ticker, []))

    def get_text(self, path, **params):
        assert path.startswith("/markets/") and path.endswith("/orderbook")
        ticker = path[len("/markets/"):-len("/orderbook")]
        self.get_calls.append(ticker)
        if ticker in self.fail_tickers:
            raise RuntimeError(f"orderbook fetch failure: {ticker}")
        return json.dumps(self.books.get(ticker, {}))


class FakeClock:
    """Monotonic-ns clock that only advances when sleep_fn is called (deterministic tests)."""
    def __init__(self):
        self.ns = 0

    def mono_ns(self):
        return self.ns

    def sleep(self, seconds):
        self.ns += int(seconds * 1e9)


def _now_fn():
    # fixed wall-clock start; resolution not load-bearing for these tests
    return datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# resolution
# --------------------------------------------------------------------------- #
def test_resolve_series_and_literals_dedup():
    client = FakeClient(markets_by_series={
        "KXTEMPNYCH": [_mkt("KXTEMPNYCH-A"), _mkt("KXTEMPNYCH-B")],
        "KXBTC": [_mkt("KXBTC-1")],
    })
    tickers, report, errs, trunc = hb.resolve_targets(
        client, ["series:KXTEMPNYCH", "ticker:KXBTC-1", "series:KXBTC", "KXLIT-9"])
    # series expands, ticker:/bare literals added, KXBTC-1 deduped (from ticker: and series:KXBTC)
    assert tickers == ["KXTEMPNYCH-A", "KXTEMPNYCH-B", "KXBTC-1", "KXLIT-9"]
    assert trunc is False and errs == []
    assert report["per_series_open_count"] == {"KXTEMPNYCH": 2, "KXBTC": 1}


def test_resolve_series_failure_is_resolve_error():
    client = FakeClient(markets_by_series={"KXBTC": [_mkt("KXBTC-1")]},
                        fail_series=["KXTEMPNYCH"])
    tickers, report, errs, trunc = hb.resolve_targets(
        client, ["series:KXTEMPNYCH", "series:KXBTC"])
    assert tickers == ["KXBTC-1"]
    assert len(errs) == 1 and errs[0]["target"] == "series:KXTEMPNYCH"
    assert report["n_resolve_errors"] == 1


def test_resolve_truncation_cap():
    client = FakeClient(markets_by_series={
        "S": [_mkt(f"S-{i}") for i in range(10)]})
    tickers, report, errs, trunc = hb.resolve_targets(client, ["series:S"], max_markets=3)
    assert trunc is True and len(tickers) == 3
    assert report["n_resolved"] == 3


# --------------------------------------------------------------------------- #
# single round: record shape, tags, derived asks, both book shapes
# --------------------------------------------------------------------------- #
def test_poll_round_record_shape_and_tags():
    client = FakeClient(books={"KX-1": _ob_fp([[0.40, 100], [0.39, 250]], [[0.58, 80]])})
    clock = FakeClock()
    recs, dropped = hb.poll_round(
        client, ["KX-1"], capture_id="CID", round_index=0, seq_start=0,
        now_fn=_now_fn, mono_fn=clock.mono_ns)
    assert dropped == []
    r = recs[0]
    assert r["schema_version"] == "hf_burst.v1"
    assert r["capture_id"] == "CID" and r["round_index"] == 0 and r["capture_seq"] == 0
    assert "capture_mono_ns" in r and "captured_at" in r
    assert r["venue"] == "kalshi" and r["ticker"] == "KX-1"
    assert r["book_shape"] == "orderbook_fp"
    assert r["yes_bids"] == [[0.40, 100], [0.39, 250]] and r["no_bids"] == [[0.58, 80]]
    assert r["best_yes_bid"] == 0.40 and r["best_no_bid"] == 0.58
    assert r["best_yes_ask"] == pytest.approx(1 - 0.58)
    assert r["best_no_ask"] == pytest.approx(1 - 0.40)
    assert r["depth"] == 3
    assert r["price_source_tag"] == "real_ask"
    assert r["price_source_tags"] == {"asks": "real_ask", "bids": "real_bid"}
    assert "raw_sha256" in r and "raw_orderbook" in r


def test_poll_round_legacy_shape():
    client = FakeClient(books={"KX-1": _ob_legacy([[40, 100]], [[58, 80]])})
    clock = FakeClock()
    recs, _ = hb.poll_round(client, ["KX-1"], capture_id="CID", round_index=0, seq_start=0,
                            now_fn=_now_fn, mono_fn=clock.mono_ns)
    r = recs[0]
    assert r["book_shape"] == "orderbook_legacy"
    assert r["yes_bids"] == [[0.40, 100]] and r["no_bids"] == [[0.58, 80]]


def test_poll_round_empty_book_captured():
    client = FakeClient(books={"KX-1": {}})
    clock = FakeClock()
    recs, dropped = hb.poll_round(client, ["KX-1"], capture_id="CID", round_index=0, seq_start=0,
                                  now_fn=_now_fn, mono_fn=clock.mono_ns)
    assert dropped == []
    assert recs[0]["book_shape"] == "empty" and recs[0]["depth"] == 0
    assert recs[0]["best_yes_ask"] is None


def test_poll_round_fault_isolation():
    client = FakeClient(books={"OK-1": _ob_fp([[0.5, 10]], [])},
                        fail_tickers=["BAD-1"])
    clock = FakeClock()
    recs, dropped = hb.poll_round(client, ["OK-1", "BAD-1"], capture_id="CID", round_index=0,
                                  seq_start=0, now_fn=_now_fn, mono_fn=clock.mono_ns)
    assert [r["ticker"] for r in recs] == ["OK-1"]     # bad ticker didn't kill the round
    assert dropped == ["BAD-1"]


# --------------------------------------------------------------------------- #
# window loop
# --------------------------------------------------------------------------- #
def test_run_window_multiple_rounds_appends_jsonl(tmp_path):
    client = FakeClient(
        markets_by_series={"S": [_mkt("S-1"), _mkt("S-2")]},
        books={"S-1": _ob_fp([[0.4, 10]], [[0.55, 5]]),
               "S-2": _ob_fp([[0.3, 20]], [[0.65, 8]])})
    clock = FakeClock()
    out = tmp_path / "out.jsonl"
    # cadence 1000ms, window 2.5s -> boundaries at 0,1,2s that are < deadline -> 3 rounds
    summary = hb.run_window(
        ["series:S"], cadence_ms=1000, window_seconds=2.5, client=client, out=out,
        now_fn=_now_fn, mono_fn=clock.mono_ns, sleep_fn=clock.sleep)
    assert summary["n_rounds"] == 3
    assert summary["n_tickers"] == 2
    assert summary["n_records"] == 6
    assert summary["completeness_ok"] is True
    assert summary["truncated"] is False
    lines = out.read_text().splitlines()
    assert len(lines) == 6
    recs = [json.loads(ln) for ln in lines]
    # seq is monotonic across the whole window; round_index increments
    assert [r["capture_seq"] for r in recs] == [0, 1, 2, 3, 4, 5]
    assert sorted({r["round_index"] for r in recs}) == [0, 1, 2]
    # all one capture_id (window), all real_ask
    assert len({r["capture_id"] for r in recs}) == 1
    assert all(r["price_source_tag"] == "real_ask" for r in recs)


def test_run_window_overrun_skips_boundaries(tmp_path):
    # each get_text advances the clock 1.2s -> a 1s-cadence round overruns; the next boundary
    # missed during the overrun is SKIPPED (no back-to-back catch-up).
    class SlowClient(FakeClient):
        def __init__(self, clock, **kw):
            super().__init__(**kw)
            self._clock = clock

        def get_text(self, path, **params):
            self._clock.ns += int(1.2 * 1e9)
            return super().get_text(path, **params)

    clock = FakeClock()
    client = SlowClient(clock, markets_by_series={"S": [_mkt("S-1")]},
                        books={"S-1": _ob_fp([[0.4, 10]], [])})
    out = tmp_path / "out.jsonl"
    summary = hb.run_window(
        ["series:S"], cadence_ms=1000, window_seconds=5.0, client=client, out=out,
        now_fn=_now_fn, mono_fn=clock.mono_ns, sleep_fn=clock.sleep)
    # 5s window, each round eats 1.2s of wall time so boundaries get skipped -> fewer than 5 rounds
    assert summary["n_rounds"] < 5
    assert summary["n_rounds"] >= 3
    assert summary["completeness_ok"] is True


def test_run_window_dropped_lowers_completeness(tmp_path):
    client = FakeClient(
        markets_by_series={"S": [_mkt("S-1"), _mkt("BAD")]},
        books={"S-1": _ob_fp([[0.4, 10]], [])},
        fail_tickers=["BAD"])
    clock = FakeClock()
    summary = hb.run_window(
        ["series:S"], cadence_ms=500, window_seconds=1.2, client=client, out=tmp_path / "o.jsonl",
        now_fn=_now_fn, mono_fn=clock.mono_ns, sleep_fn=clock.sleep)
    assert summary["n_dropped"] > 0
    assert summary["completeness_ok"] is False


def test_run_window_resolve_error_lowers_completeness(tmp_path):
    client = FakeClient(markets_by_series={"S": [_mkt("S-1")]},
                        books={"S-1": _ob_fp([[0.4, 10]], [])},
                        fail_series=["GONE"])
    clock = FakeClock()
    summary = hb.run_window(
        ["series:GONE", "series:S"], cadence_ms=500, window_seconds=1.2, client=client,
        out=tmp_path / "o.jsonl", now_fn=_now_fn, mono_fn=clock.mono_ns, sleep_fn=clock.sleep)
    assert summary["n_resolve_errors"] == 1
    assert summary["completeness_ok"] is False


def test_run_window_truncation_lowers_completeness(tmp_path):
    client = FakeClient(
        markets_by_series={"S": [_mkt(f"S-{i}") for i in range(5)]},
        books={f"S-{i}": _ob_fp([[0.4, 10]], []) for i in range(5)})
    clock = FakeClock()
    summary = hb.run_window(
        ["series:S"], cadence_ms=500, window_seconds=0.6, client=client, out=tmp_path / "o.jsonl",
        max_markets=2, now_fn=_now_fn, mono_fn=clock.mono_ns, sleep_fn=clock.sleep)
    assert summary["truncated"] is True
    assert summary["n_tickers"] == 2
    assert summary["completeness_ok"] is False


# --------------------------------------------------------------------------- #
# honest zero-round exits + guards
# --------------------------------------------------------------------------- #
def test_cadence_floor_rejected():
    client = FakeClient(markets_by_series={"S": [_mkt("S-1")]})
    clock = FakeClock()
    with pytest.raises(ValueError):
        hb.run_window(["series:S"], cadence_ms=hb.CADENCE_FLOOR_MS - 1, window_seconds=1.0,
                      client=client, now_fn=_now_fn, mono_fn=clock.mono_ns, sleep_fn=clock.sleep)


def test_no_tickers_resolved_is_honest_zero_rounds(tmp_path):
    client = FakeClient(markets_by_series={"S": []})   # series resolves to zero open markets
    clock = FakeClock()
    summary = hb.run_window(
        ["series:S"], cadence_ms=500, window_seconds=2.0, client=client, out=tmp_path / "o.jsonl",
        now_fn=_now_fn, mono_fn=clock.mono_ns, sleep_fn=clock.sleep)
    assert summary["n_rounds"] == 0 and summary["n_tickers"] == 0
    assert summary["window_ran"] is False
    assert summary["completeness_ok"] is False   # zero data captured is not success
    assert summary["path"] is None
    assert not (tmp_path / "o.jsonl").exists()   # no empty file written


def test_nonpositive_window_is_honest_zero_rounds(tmp_path):
    client = FakeClient(markets_by_series={"S": [_mkt("S-1")]},
                        books={"S-1": _ob_fp([[0.4, 10]], [])})
    clock = FakeClock()
    summary = hb.run_window(
        ["series:S"], cadence_ms=500, window_seconds=0.0, client=client, out=tmp_path / "o.jsonl",
        now_fn=_now_fn, mono_fn=clock.mono_ns, sleep_fn=clock.sleep)
    assert summary["n_rounds"] == 0 and summary["window_ran"] is False
    assert summary["completeness_ok"] is False
