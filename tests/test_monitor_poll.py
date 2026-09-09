"""collection.monitor_poll — the public-REST 60s snapshot fallback, fully offline: the
self-gating stand-down when WS tape is fresh, batched capture with the sanctioned quote
derivation, and honest accounting of tickers the listing stopped returning."""
from __future__ import annotations

import json
import os
import time

from collection import monitor_poll as mp


class FakeClient:
    def __init__(self, markets):
        self._markets = {m["ticker"]: m for m in markets}
        self.calls = []

    def get_text(self, path, **params):
        self.calls.append((path, params))
        want = params["tickers"].split(",")
        return json.dumps({"markets": [self._markets[t] for t in want
                                       if t in self._markets]})


def _mkt(ticker, yes_bid="0.41", no_bid="0.57"):
    return {"ticker": ticker, "yes_bid_dollars": yes_bid, "no_bid_dollars": no_bid,
            "yes_bid_size_fp": "105.0", "yes_ask_size_fp": "80.0",
            "last_price_dollars": "0.42", "volume_24h_fp": "900",
            "open_interest_fp": "10", "close_time": "2026-08-27T00:00:00Z"}


def test_stands_down_when_ws_tape_fresh(tmp_path):
    ws = tmp_path / "ws_depth"
    ws.mkdir()
    (ws / "dt=2026-08-26.jsonl.gz").write_bytes(b"x")   # just written -> fresh
    summary = mp.run(client=None, store=tmp_path / "poll", ws_tape=ws)
    assert summary["status"] == "skipped_ws_fresh" and summary["n_lines"] == 0
    assert not (tmp_path / "poll").exists()             # zero network, zero files


def test_polls_when_ws_tape_stale_and_derives_quote(tmp_path):
    ws = tmp_path / "ws_depth"
    ws.mkdir()
    stale = ws / "dt=2026-08-20.jsonl.gz"
    stale.write_bytes(b"x")
    old = time.time() - 3600
    os.utime(stale, (old, old))
    client = FakeClient([_mkt("A"), _mkt("B")])
    summary = mp.run(client=client, store=tmp_path / "poll", tickers=["A", "B"],
                     ws_tape=ws)
    assert summary["status"] == "polled" and summary["completeness_ok"] is True
    lines = [json.loads(l) for f in (tmp_path / "poll").glob("dt=*.jsonl")
             for l in f.read_text().splitlines()]
    recs = [l for l in lines if l["schema_version"] == "monitor_poll.snapshot60.v1"]
    assert len(recs) == 2
    r = recs[0]
    # quote derived by core.pricing.top_of_book_quote from the two bid sides
    assert r["yes_ask"] == 0.43 and r["mid"] == 0.42 and r["spread"] == 0.02
    assert r["price_source_tag"] == "real_ask" and len(r["raw_sha256"]) == 64


def test_missing_subscribed_ticker_is_counted_not_silent(tmp_path):
    client = FakeClient([_mkt("A")])                    # "GONE" not in the listing
    summary = mp.run(client=client, store=tmp_path / "poll", tickers=["A", "GONE"],
                     ws_tape=tmp_path / "no_ws")
    assert summary["n_missing"] == 1
    assert summary["completeness_ok"] is False


def test_batches_by_100(tmp_path):
    tickers = [f"T{i}" for i in range(150)]
    client = FakeClient([_mkt(t) for t in tickers])
    summary = mp.run(client=client, store=tmp_path / "poll", tickers=tickers,
                     ws_tape=tmp_path / "no_ws")
    assert summary["n_calls"] == 2 and summary["n_lines"] == 150
