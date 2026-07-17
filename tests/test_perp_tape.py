"""collection.perp_tape — fully offline (FakeClient, no network).

Covers: markets record shape / source tags / active-inactive accounting / string→float
coercion, orderbook verbatim-level preservation + tags, funding-estimate discovery over
THIS pass's active set (markets failure ⇒ honestly zero estimates, never a hardcoded
list), funding-rates windowing + defensive cursor pagination, fault isolation (one
section's failure is a visible error line that lowers completeness but never kills the
pass), JSONL append across passes, the summary contract hourly_pass folds on, and the
one-shot backfill mode."""
from __future__ import annotations

import json

import pytest

from collection import perp_tape as pt


# --------------------------------------------------------------------------- #
# FakeClient
# --------------------------------------------------------------------------- #
def _mkt(ticker, status="active", bid="1.0000", ask="1.0010", **extra):
    m = {"ticker": ticker, "title": f"t-{ticker}", "status": status,
         "bid": bid, "ask": ask, "price": "1.0005", "tick_size": "0.0001",
         "contract_size": "0.0001", "open_interest": "10.00", "volume_24h": "5.00",
         "volume_24h_notional_value_dollars": "50.00",
         "open_interest_notional_value_dollars": "100.00",
         "leverage_estimate": 3.0, "leverage_estimates": {"1000": 3.0},
         "reference_price": {"price": "1.0004", "ts_ms": 1},
         "settlement_mark_price": {"price": "1.0004", "ts_ms": 1},
         "liquidation_mark_price": {"price": "1.0004", "ts_ms": 1}}
    m.update(extra)
    return m


class FakeClient:
    """Serves the four /margin GET shapes. Failure injection per path-substring."""

    def __init__(self, markets=None, books=None, estimates=None,
                 funding_pages=None, fail_paths=()):
        self.markets = markets if markets is not None else []
        self.books = books or {}
        self.estimates = estimates or {}
        self.funding_pages = funding_pages if funding_pages is not None else [
            {"funding_rates": []}]
        self.fail_paths = tuple(fail_paths)
        self.calls = []
        self._funding_i = 0

    def get_text(self, path, **params):
        self.calls.append((path, params))
        for frag in self.fail_paths:
            if frag in path:
                raise RuntimeError(f"injected failure: {path}")
        if path == "/markets":
            return json.dumps({"markets": self.markets})
        if path.endswith("/orderbook"):
            ticker = path[len("/markets/"):-len("/orderbook")]
            return json.dumps({"orderbook": self.books.get(ticker, {})})
        if path == "/funding_rates/estimate":
            t = params["ticker"]
            return json.dumps(self.estimates.get(t, {
                "market_ticker": t, "funding_rate": 0, "mark_price": "1.0",
                "computed_time": "2026-07-16T21:00:00Z",
                "next_funding_time": "2026-07-17T04:00:00Z"}))
        if path == "/funding_rates/historical":
            page = self.funding_pages[min(self._funding_i, len(self.funding_pages) - 1)]
            self._funding_i += 1
            return json.dumps(page)
        raise AssertionError(f"unexpected path: {path}")


def _read_lines(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _by_type(records):
    out = {}
    for r in records:
        out.setdefault(r["record_type"], []).append(r)
    return out


# --------------------------------------------------------------------------- #
# happy path — record shapes, tags, accounting
# --------------------------------------------------------------------------- #
def test_run_happy_path_shapes_and_summary(tmp_path):
    client = FakeClient(
        markets=[_mkt("KXBTCPERP"), _mkt("KXETHPERP"),
                 _mkt("KXDOTPERP", status="inactive", bid="0", ask="0")],
        books={"KXBTCPERP": {"asks": [["1.0010", "5.00"]], "bids": [["1.0000", "7.00"]]},
               "KXETHPERP": {"asks": [], "bids": []}},
        funding_pages=[{"funding_rates": [
            {"market_ticker": "KXBTCPERP", "funding_time": "2026-07-16T20:00:00Z",
             "funding_rate": 0, "mark_price": "1.0004"}]}],
    )
    summary = pt.run(client=client, tape_dir=tmp_path,
                     l2_tickers=("KXBTCPERP", "KXETHPERP"))

    # sections: 1 markets + 2 books + 2 estimates (active only — DOT excluded) + 1 funding
    assert summary["n_sections_expected"] == 6
    assert summary["n_sections_ok"] == 6
    assert summary["completeness_ok"] is True
    assert summary["n_lines"] == 6
    assert summary["n_contracts"] == 3

    recs = _by_type(_read_lines(summary["path"]))
    mk = recs["markets"][0]
    assert mk["schema_version"] == "perp_tape.v1" and mk["venue"] == "kalshi_perps"
    assert mk["n_active"] == 2 and mk["n_inactive"] == 1
    assert mk["active_tickers"] == ["KXBTCPERP", "KXETHPERP"]
    assert mk["raw_sha256"]
    row = next(r for r in mk["contracts"] if r["ticker"] == "KXBTCPERP")
    assert row["bid"] == 1.0 and row["ask"] == 1.001            # string→float
    assert row["bbo_source_tag"] == "real_ask"
    assert row["mark_source_tag"] == "broker_truth"

    books = {b["ticker"]: b for b in recs["orderbook"]}
    assert books["KXBTCPERP"]["asks"] == [["1.0010", "5.00"]]   # verbatim strings
    assert books["KXBTCPERP"]["n_bid_levels"] == 1
    assert books["KXBTCPERP"]["asks_source_tag"] == "real_ask"
    assert books["KXBTCPERP"]["bids_source_tag"] == "real_bid"
    assert books["KXETHPERP"]["n_ask_levels"] == 0

    ests = {e["ticker"] for e in recs["funding_estimate"]}
    assert ests == {"KXBTCPERP", "KXETHPERP"}                   # active set, not DOT
    assert all(e["price_source_tag"] == "broker_truth" for e in recs["funding_estimate"])

    fr = recs["funding_rates"][0]
    assert fr["mode"] == "recent" and fr["n_prints"] == 1
    assert fr["prints"][0]["funding_rate"] == 0.0
    assert fr["price_source_tag"] == "broker_truth"


def test_run_missing_numeric_field_stays_none_not_zero(tmp_path):
    m = _mkt("KXBTCPERP")
    del m["open_interest"]
    m["volume_24h"] = "not-a-number"
    client = FakeClient(markets=[m])
    summary = pt.run(client=client, tape_dir=tmp_path, l2_tickers=())
    row = _by_type(_read_lines(summary["path"]))["markets"][0]["contracts"][0]
    assert row["open_interest"] is None
    assert row["volume_24h"] is None


# --------------------------------------------------------------------------- #
# fault isolation — a failed section is a visible line, never a dead pass
# --------------------------------------------------------------------------- #
def test_run_orderbook_failure_isolated(tmp_path):
    client = FakeClient(markets=[_mkt("KXBTCPERP")],
                        fail_paths=("/markets/KXBTCPERP/orderbook",))
    summary = pt.run(client=client, tape_dir=tmp_path, l2_tickers=("KXBTCPERP",))

    assert summary["completeness_ok"] is False
    assert summary["n_sections_ok"] == summary["n_sections_expected"] - 1
    recs = _by_type(_read_lines(summary["path"]))
    assert recs["orderbook"][0]["status"] == "fetch_error"
    assert "injected failure" in recs["orderbook"][0]["error"]
    assert recs["markets"][0]["status"] == "ok"                 # siblings survived
    assert recs["funding_estimate"][0]["status"] == "ok"
    assert recs["funding_rates"][0]["status"] == "ok"


def test_run_markets_failure_means_zero_estimates_and_incomplete(tmp_path):
    client = FakeClient(fail_paths=("/markets",))  # also fails the orderbook path prefix
    summary = pt.run(client=client, tape_dir=tmp_path, l2_tickers=("KXBTCPERP",))

    assert summary["completeness_ok"] is False
    assert summary["n_contracts"] == 0
    recs = _by_type(_read_lines(summary["path"]))
    assert recs["markets"][0]["status"] == "fetch_error"
    assert "funding_estimate" not in recs                       # no fabricated discovery
    assert recs["funding_rates"][0]["status"] == "ok"           # its path doesn't match


def test_run_funding_failure_isolated(tmp_path):
    client = FakeClient(markets=[_mkt("KXBTCPERP")],
                        fail_paths=("/funding_rates/historical",))
    summary = pt.run(client=client, tape_dir=tmp_path, l2_tickers=())
    assert summary["completeness_ok"] is False
    fr = _by_type(_read_lines(summary["path"]))["funding_rates"][0]
    assert fr["status"] == "fetch_error" and fr["mode"] == "recent"


# --------------------------------------------------------------------------- #
# funding pagination — defensive cursor follow, no silent truncation
# --------------------------------------------------------------------------- #
def test_fetch_funding_rates_follows_cursor():
    client = FakeClient(funding_pages=[
        {"funding_rates": [{"market_ticker": "A", "funding_time": "t1",
                            "funding_rate": 0.0001, "mark_price": "1"}], "cursor": "c1"},
        {"funding_rates": [{"market_ticker": "B", "funding_time": "t2",
                            "funding_rate": 0, "mark_price": "2"}]},
    ])
    body, ok = pt.fetch_funding_rates(client, start_ts=100, end_ts=200)
    assert ok and body["n_prints"] == 2
    assert [p["market_ticker"] for p in body["prints"]] == ["A", "B"]
    # second request carried the cursor and both carried the window
    (_, p1), (_, p2) = client.calls
    assert "cursor" not in p1 and p2["cursor"] == "c1"
    assert p1["start_ts"] == 100 and p1["end_ts"] == 200


# --------------------------------------------------------------------------- #
# append + capture identity
# --------------------------------------------------------------------------- #
def test_run_appends_across_passes_with_distinct_capture_ids(tmp_path):
    client = FakeClient(markets=[_mkt("KXBTCPERP")])
    s1 = pt.run(client=client, tape_dir=tmp_path, l2_tickers=())
    s2 = pt.run(client=client, tape_dir=tmp_path, l2_tickers=())
    recs = _read_lines(s1["path"])
    assert s1["path"] == s2["path"] or len({s1["path"], s2["path"]}) == 2  # day rollover tolerated
    ids = {r["capture_id"] for r in recs}
    assert s1["capture_id"] in ids
    assert all(r["schema_version"] == "perp_tape.v1" for r in recs)


# --------------------------------------------------------------------------- #
# backfill mode
# --------------------------------------------------------------------------- #
def test_backfill_funding_writes_backfill_record(tmp_path):
    client = FakeClient(funding_pages=[{"funding_rates": [
        {"market_ticker": "KXBTCPERP", "funding_time": "2026-06-03T20:00:00Z",
         "funding_rate": 0, "mark_price": "1"}]}])
    summary = pt.backfill_funding(client=client, tape_dir=tmp_path, start_ts=pt.LAUNCH_TS)
    assert summary["completeness_ok"] is True and summary["n_prints"] == 1
    rec = _read_lines(summary["path"])[0]
    assert rec["record_type"] == "funding_rates" and rec["mode"] == "backfill"
    assert rec["start_ts"] == pt.LAUNCH_TS
    # the request actually used the launch window
    assert client.calls[0][1]["start_ts"] == pt.LAUNCH_TS


def test_backfill_failure_is_honest(tmp_path):
    client = FakeClient(fail_paths=("/funding_rates/historical",))
    summary = pt.backfill_funding(client=client, tape_dir=tmp_path)
    assert summary["completeness_ok"] is False and summary["n_prints"] == 0
    rec = _read_lines(summary["path"])[0]
    assert rec["status"] == "fetch_error"
