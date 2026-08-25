"""collection.monitor_scope — scope resolution, per-series fetch, selection cap, tickers-file
rewrite. Offline: a fake client serves canned /series and per-series /markets pages; no
network, no repo config mutation (tmp_path everywhere)."""
from __future__ import annotations

import json

from collection import monitor_scope as ms


class FakeClient:
    """Serves /series and per-series /markets pages (cursor exhausted after one page)."""

    def __init__(self, series, markets_by_series):
        self._series = {"series": series}
        self._by_series = markets_by_series
        self.calls = []

    def get_text(self, path, **params):
        self.calls.append((path, params))
        if path == "/series":
            return json.dumps(self._series)
        sel = self._by_series.get(params.get("series_ticker"), [])
        return json.dumps({"markets": sel, "cursor": None})


def _mkt(ticker, close="2026-08-25T00:00:00Z", vol="100"):
    return {"ticker": ticker, "event_ticker": ticker.rsplit("-", 1)[0],
            "title": ticker, "status": "active", "open_time": "2026-08-01T00:00:00Z",
            "close_time": close, "volume_24h_fp": vol, "open_interest_fp": "10"}


def _cfg(max_tickers=2):
    return {
        "scope": {"series_prefixes": ["KXHIGH"], "categories": ["Mentions"],
                  "series_tickers": ["KXODDBALL"]},
        "selection": {"max_tickers": max_tickers, "sort": "volume_then_close"},
        "cadences": {}, "alerting": {}, "retention": {},
        "thresholds": {"x": {"value": 1, "range": [0, 2]}},
    }


SERIES = [{"ticker": "KXROGANMENTION", "category": "Mentions"},
          {"ticker": "KXHIGHNY", "category": "Climate and Weather"},
          {"ticker": "KXBTC", "category": "Crypto"}]

MARKETS = {"KXHIGHNY": [_mkt("KXHIGHNY-26AUG25-T86", vol="5")],
           "KXROGANMENTION": [_mkt("KXROGANMENTION-26AUG29-AI", vol="900")],
           "KXODDBALL": [_mkt("KXODDBALL-26SEP01-X", vol="50")],
           "KXBTC": [_mkt("KXBTC-26AUG25-T60000", vol="99999")]}


def test_scope_filter_prefix_category_and_explicit():
    scope = _cfg()["scope"]
    assert ms.in_scope("KXHIGHNY", "Climate and Weather", scope)      # prefix
    assert ms.in_scope("KXROGANMENTION", "Mentions", scope)           # category
    assert ms.in_scope("KXODDBALL", "Other", scope)                   # explicit
    assert not ms.in_scope("KXBTC", "Crypto", scope)
    assert not ms.in_scope(None, "Mentions", scope)


def test_scoped_series_includes_explicit_unknown_to_series_listing():
    cats = {s["ticker"]: s["category"] for s in SERIES}
    # KXODDBALL is not in the /series listing but IS explicitly scoped -> still fetched
    assert ms.scoped_series(cats, _cfg()["scope"]) == [
        "KXHIGHNY", "KXODDBALL", "KXROGANMENTION"]


def test_run_fetches_only_scoped_series_and_caps_by_volume(tmp_path):
    client = FakeClient(SERIES, MARKETS)
    tickers_path = tmp_path / "ws_depth_tickers.txt"
    summary = ms.run(client=client, store=tmp_path / "tape", tickers_path=tickers_path,
                     config=_cfg(max_tickers=2))
    # KXBTC is out of scope: its series was never even fetched
    fetched = {p.get("series_ticker") for _, p in client.calls if "series_ticker" in p}
    assert fetched == {"KXHIGHNY", "KXODDBALL", "KXROGANMENTION"}
    assert summary["n_series_scoped"] == 3 and summary["n_in_scope"] == 3
    assert summary["n_ws_selected"] == 2 and summary["n_dropped_by_cap"] == 1
    assert summary["completeness_ok"] is True
    # volume ranking: ROGAN (900) + ODDBALL (50) selected; KXHIGHNY (5) capped out
    chosen = [t for t in tickers_path.read_text().splitlines()
              if t and not t.startswith("#")]
    assert set(chosen) == {"KXROGANMENTION-26AUG29-AI", "KXODDBALL-26SEP01-X"}
    lines = [json.loads(l) for f in (tmp_path / "tape").glob("dt=*.jsonl")
             for l in f.read_text().splitlines()]
    recs = [l for l in lines if l["schema_version"] == "monitor_scope.v1"]
    by_ticker = {r["ticker"]: r for r in recs}
    assert by_ticker["KXHIGHNY-26AUG25-T86"]["ws_selected"] is False
    assert by_ticker["KXROGANMENTION-26AUG29-AI"]["ws_selected"] is True
    assert all(r["open_time"] and r["close_time"] for r in recs)      # horizon labels' inputs
    # scope lines carry no price and no price tag (prices are ws_depth's job)
    assert all("price_source_tag" not in r and "yes_ask" not in r for r in recs)
    assert len([l for l in lines
                if l["schema_version"] == "monitor_scope.summary.v1"]) == 1


def test_tickers_file_rewrite_only_on_set_change(tmp_path):
    p = tmp_path / "t.txt"
    assert ms.write_tickers_file(["B", "A"], p) is True
    assert ms.write_tickers_file(["A", "B"], p) is False       # same set, any order
    mtime = p.stat().st_mtime_ns
    assert ms.write_tickers_file(["A", "B"], p) is False
    assert p.stat().st_mtime_ns == mtime                        # untouched -> no restart
    assert ms.write_tickers_file(["A"], p) is True
    body = [l for l in p.read_text().splitlines() if l and not l.startswith("#")]
    assert body == ["A"]


def test_run_flags_truncated_series_as_incomplete(tmp_path):
    class TruncatingClient(FakeClient):
        def get_text(self, path, **params):
            self.calls.append((path, params))
            if path == "/series":
                return json.dumps(self._series)
            # always returns a live cursor -> the per-series page cap must trip
            return json.dumps({"markets": [_mkt("KXHIGHNY-26AUG25-T86")],
                               "cursor": "more"})

    client = TruncatingClient(SERIES, MARKETS)
    summary = ms.run(client=client, store=tmp_path / "tape",
                     tickers_path=tmp_path / "t.txt", config=_cfg())
    assert summary["n_series_truncated"] == 3
    assert summary["completeness_ok"] is False                  # partial scope FAILS loud
