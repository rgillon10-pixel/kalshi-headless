"""Forward capture emits the locked bitemporal CaptureManifest, with HONEST completeness.

These exercise collection.capture_orderbooks.run() fully offline via an injected fake
client (no network) writing to a tmp store. The point is the property the sibling tapes
lacked (audited 2026-06-07): every line is bitemporal (as_of/event_time), content-hashed,
self-signed, warmup=True, and a silently-dropped market lowers completeness rather than
masquerading as a complete capture (D3 survivorship / corrupted-actuals failure mode).
"""
from __future__ import annotations

import json

import pytest

from collection import capture_orderbooks as cap
from core.manifest_schema import MANIFEST_SCHEMA_VERSION, validate, verify_signature


class FakeClient:
    """Minimal stand-in for validation.v3_market.Kalshi — only the read-only methods
    capture uses, served from in-memory fixtures. No network, no clock, no order path."""

    base = "https://fake.test"

    def __init__(self, series_markets, books, fail_text=()):
        self.series_markets = series_markets          # {series_ticker: [market_ticker, ...]}
        self.books = books                            # {market_ticker: orderbook_fp dict}
        self.fail_text = set(fail_text)               # market_tickers whose fetch raises

    def series_by_category(self, category):
        return [{"ticker": s, "title": ("High" if "HIGH" in s else "Low") + " temp"}
                for s in self.series_markets]

    def open_markets(self, series_ticker):
        return [{"ticker": t} for t in self.series_markets[series_ticker]]

    def get_text(self, path):
        ticker = path.split("/markets/", 1)[1].rsplit("/orderbook", 1)[0]
        if ticker in self.fail_text:
            raise RuntimeError(f"simulated fetch failure: {ticker}")
        return json.dumps({"orderbook_fp": self.books[ticker]})


_BOOK = {"yes_dollars": [["0.30", "100"], ["0.29", "40"]],
         "no_dollars": [["0.68", "75"]]}


def _manifest_lines(store):
    path = store / "_manifest.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _capture_dir(store, summary):
    return store / f"dt={summary['day']}" / f"capture-{summary['capture_id']}"


# --------------------------------------------------------------------------- #
# happy path — a complete (city, contract-day) capture
# --------------------------------------------------------------------------- #
def test_complete_capture_emits_valid_bitemporal_manifest(tmp_path):
    client = FakeClient(
        {"KXHIGHAUS": ["KXHIGHAUS-26JUN06-B84.5", "KXHIGHAUS-26JUN06-B86.5"]},
        {"KXHIGHAUS-26JUN06-B84.5": _BOOK, "KXHIGHAUS-26JUN06-B86.5": _BOOK},
    )
    summary = cap.run(client=client, store=tmp_path)
    assert summary["n_groups"] == 1 and summary["n_complete"] == 1
    assert summary["total_markets"] == 2

    lines = _manifest_lines(tmp_path)
    assert len(lines) == 1
    m = lines[0]
    assert validate(m) == [], validate(m)
    assert m["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert m["city"] == "Austin" and m["target_date"] == "2026-06-06"
    # bitemporal + warm-up + self-signed (the discipline the sibling tapes lacked)
    assert m["event_time"] == "2026-06-06T00:00:00+00:00"
    assert m["as_of"] == m["captured_at"] and m["as_of"]
    assert m["warmup"] is True
    assert m["completeness_ok"] is True
    assert m["n_markets"] == m["expected_markets"] == 2
    assert verify_signature(m)
    # provenance: the manifest hashes bind to the bytes actually written
    assert cap.verify_against_dir(m, _capture_dir(tmp_path, summary)) == []


# --------------------------------------------------------------------------- #
# the core property: a silently-dropped market is NOT a complete capture
# --------------------------------------------------------------------------- #
def test_dropped_market_lowers_completeness_not_hidden(tmp_path):
    client = FakeClient(
        {"KXHIGHAUS": ["KXHIGHAUS-26JUN06-B84.5", "KXHIGHAUS-26JUN06-B86.5"]},
        {"KXHIGHAUS-26JUN06-B84.5": _BOOK, "KXHIGHAUS-26JUN06-B86.5": _BOOK},
        fail_text={"KXHIGHAUS-26JUN06-B86.5"},
    )
    summary = cap.run(client=client, store=tmp_path)
    m = _manifest_lines(tmp_path)[0]
    assert validate(m) == [], validate(m)        # an incomplete capture is still a VALID record
    assert m["completeness_ok"] is False          # ...but it is honestly flagged incomplete
    assert m["n_markets"] == 1 and m["expected_markets"] == 2
    assert summary["n_complete"] == 0


# --------------------------------------------------------------------------- #
# a discovered group we capture nothing from must NOT emit a (zero-market) line
# --------------------------------------------------------------------------- #
def test_degenerate_group_emits_no_line_but_is_recorded(tmp_path):
    client = FakeClient(
        {"KXHIGHAUS": ["KXHIGHAUS-26JUN06-B84.5"]},
        {"KXHIGHAUS-26JUN06-B84.5": _BOOK},
        fail_text={"KXHIGHAUS-26JUN06-B84.5"},
    )
    summary = cap.run(client=client, store=tmp_path)
    assert summary["n_groups"] == 0 and summary["n_degenerate"] == 1
    assert _manifest_lines(tmp_path) == []        # never write an empty "capture"


# --------------------------------------------------------------------------- #
# distinct contract-days are distinct edge units -> distinct manifest lines
# --------------------------------------------------------------------------- #
def test_multi_day_groups_split_by_contract_day(tmp_path):
    client = FakeClient(
        {"KXHIGHAUS": ["KXHIGHAUS-26JUN06-B84.5", "KXHIGHAUS-26JUN07-B84.5"]},
        {"KXHIGHAUS-26JUN06-B84.5": _BOOK, "KXHIGHAUS-26JUN07-B84.5": _BOOK},
    )
    summary = cap.run(client=client, store=tmp_path)
    assert summary["n_groups"] == 2
    dates = sorted(m["target_date"] for m in _manifest_lines(tmp_path))
    assert dates == ["2026-06-06", "2026-06-07"]


# --------------------------------------------------------------------------- #
# provenance: a re-signed forgery passes the schema but must fail the byte-binding
# --------------------------------------------------------------------------- #
def test_forged_hash_passes_schema_but_fails_provenance(tmp_path):
    from core.manifest_schema import sign
    client = FakeClient(
        {"KXHIGHAUS": ["KXHIGHAUS-26JUN06-B84.5"]},
        {"KXHIGHAUS-26JUN06-B84.5": _BOOK},
    )
    summary = cap.run(client=client, store=tmp_path)
    real = _manifest_lines(tmp_path)[0]
    cdir = _capture_dir(tmp_path, summary)
    forged = sign({**real, "raw_sha256": "0" * 64})   # internally consistent, wrong hash
    assert validate(forged) == []                      # schema alone cannot catch it
    assert cap.verify_against_dir(forged, cdir)         # provenance does
    assert cap.verify_against_dir(real, cdir) == []


# --------------------------------------------------------------------------- #
# write isolation: a pass writes only under the store it was handed
# --------------------------------------------------------------------------- #
def test_capture_writes_only_under_given_store(tmp_path):
    client = FakeClient(
        {"KXHIGHAUS": ["KXHIGHAUS-26JUN06-B84.5"]},
        {"KXHIGHAUS-26JUN06-B84.5": _BOOK},
    )
    summary = cap.run(client=client, store=tmp_path)
    written = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()}
    assert "_manifest.jsonl" in written
    assert any(name.endswith(".raw.json") for name in written)
    assert any(name.endswith(".normalized.json") for name in written)
    assert _capture_dir(tmp_path, summary).is_dir()
