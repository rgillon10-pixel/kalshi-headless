"""collection.universe_sweep — the full-universe top-of-book sweep.

Fully offline: an injected FakeKalshi serves platform-wide `/markets?status=open` pages from
in-memory fixtures (the inline BBO + volume/OI/last_price shape the listing returns) — no live
network, no clock injection beyond the tape store path. Covers: multi-page cursor stitching,
the MAX_CALLS cap + truncation completeness gate (lesson L10), clean-exhaustion completeness,
the real_ask tag on every line, verbatim inline-field capture (no arithmetic — Hard Rule #3),
raw-page provenance, and append-only writes to the dt= partition.

Field shape (lesson L90 — verified live for OPEN markets 2026-07-17): Kalshi's open /markets
object carries prices as `_dollars` STRING fields and sizes/volumes as `_fp` STRING fields; the
bare `yes_ask`/`volume`/... keys come back null. The fixtures emit that realistic suffixed shape
so the offline tests exercise the SAME parsing the live sweep uses.
"""
from __future__ import annotations

import json

from collection import universe_sweep as us


# --------------------------------------------------------------------------- #
# fakes / fixtures
# --------------------------------------------------------------------------- #
class FakeKalshi:
    """Stand-in for validation.v3_market.Kalshi. Serves `/markets?status=open` as cursor-
    paginated pages of raw market objects (no series_ticker — a full-universe sweep)."""

    base = "https://fake.test"

    def __init__(self, pages, extra_top=None):
        # pages: list of (markets_list, next_cursor|None); extra_top: dict folded into every page
        self.pages = pages
        self.extra_top = extra_top or {}
        self.calls = 0

    def get_text(self, path, **params):
        assert path == "/markets"
        assert params["status"] == "open"
        assert "series_ticker" not in params            # genuine full-universe sweep
        cursor = params.get("cursor")
        idx = 0 if cursor is None else int(cursor)
        markets, nxt = self.pages[idx]
        self.calls += 1
        return json.dumps({"markets": markets, "cursor": nxt, **self.extra_top})


def _mkt(ticker, *, event_ticker=None, yes_bid=40, yes_ask=42, no_bid=58, no_ask=60,
         volume=100, open_interest=50, last_price=41):
    # Kalshi's OPEN /markets object carries prices as `_dollars` STRINGs and sizes/volumes as
    # `_fp` STRINGs; the bare keys come back null (lesson L90). Emit that realistic suffixed shape.
    return {
        "ticker": ticker,
        "event_ticker": event_ticker or ticker.rsplit("-", 1)[0],
        "status": "active",
        "market_type": "binary",
        "yes_bid_dollars": str(yes_bid), "yes_ask_dollars": str(yes_ask),
        "no_bid_dollars": str(no_bid), "no_ask_dollars": str(no_ask),
        "volume_fp": str(volume), "open_interest_fp": str(open_interest),
        "last_price_dollars": str(last_price),
    }


def _one_page(markets):
    return FakeKalshi([(markets, None)])


# --------------------------------------------------------------------------- #
# record building — verbatim inline capture, real_ask tag, no arithmetic
# --------------------------------------------------------------------------- #
def test_record_tags_real_ask_and_captures_inline_fields_verbatim():
    rec = us._record_from_market(
        _mkt("KXTEST-26JUL17-A", yes_bid=33, yes_ask=35, no_bid=64, no_ask=66,
             volume=777, open_interest=88, last_price=34),
        captured_at="2026-07-17T12:00:00+00:00", capture_id="X", raw_sha256="abc")
    assert rec["price_source_tag"] == "real_ask"     # a resting book ask is a fillable price
    # inline top-of-book parsed from the _dollars/_fp fields, verbatim (no normalization)
    assert rec["yes_bid"] == 33.0 and rec["yes_ask"] == 35.0
    assert rec["no_bid"] == 64.0 and rec["no_ask"] == 66.0
    assert rec["volume"] == 777.0
    assert rec["open_interest"] == 88.0
    assert rec["last_price"] == 34.0
    assert rec["ticker"] == "KXTEST-26JUL17-A"
    assert rec["event_ticker"] == "KXTEST-26JUL17"
    assert rec["schema_version"] == "universe_sweep.v1"
    assert rec["raw_sha256"] == "abc"


def test_record_parses_real_dollar_strings_to_floats():
    # a realistic Kalshi open-market object (prices are sub-dollar strings, not integer cents)
    rec = us._record_from_market(
        {"ticker": "KXHIGHNY-26JUL17-B", "event_ticker": "KXHIGHNY-26JUL17",
         "status": "active", "yes_bid_dollars": "0.4200", "yes_ask_dollars": "0.4400",
         "no_bid_dollars": "0.5600", "no_ask_dollars": "0.5800",
         "last_price_dollars": "0.4300", "volume_fp": "1234.00",
         "open_interest_fp": "567.00", "liquidity_dollars": "89.0000"},
        captured_at="t", capture_id="Y", raw_sha256=None)
    assert rec["yes_ask"] == 0.44 and rec["no_ask"] == 0.58
    assert rec["last_price"] == 0.43
    assert rec["volume"] == 1234.0 and rec["open_interest"] == 567.0
    assert rec["liquidity"] == 89.0
    # bare/absent fields are honestly None, never fabricated 0
    assert rec["previous_price"] is None


# --------------------------------------------------------------------------- #
# multi-page pagination + cursor stitching
# --------------------------------------------------------------------------- #
def test_run_pagination_follows_cursor_and_writes_every_market(tmp_path):
    client = FakeKalshi([
        ([_mkt("KXA-26JUL17-1"), _mkt("KXA-26JUL17-2")], "1"),   # page 0 -> cursor "1"
        ([_mkt("KXB-26JUL17-1")], "2"),                          # page 1 -> cursor "2"
        ([_mkt("KXC-26JUL17-1")], None),                         # page 2 -> end
    ])
    s = us.run(client=client, store=tmp_path)
    assert client.calls == 3
    assert s["call_count"] == 3
    assert s["n_pulled"] == 4
    assert s["n_markets"] == 4
    assert s["n_lines"] == 4
    assert s["cursor_exhausted"] is True
    assert s["truncated"] is False
    assert s["completeness_ok"] is True

    recs = [json.loads(ln) for ln in (tmp_path / f"dt={s['day']}.jsonl").read_text().splitlines()]
    assert len(recs) == 4
    assert {r["ticker"] for r in recs} == {
        "KXA-26JUL17-1", "KXA-26JUL17-2", "KXB-26JUL17-1", "KXC-26JUL17-1"}
    # real_ask on EVERY line
    assert all(r["price_source_tag"] == "real_ask" for r in recs)
    # inline BBO/volume/OI/last_price present AND populated (not null) on every line
    for r in recs:
        for f in ("yes_bid", "yes_ask", "no_bid", "no_ask", "volume", "open_interest",
                  "last_price"):
            assert f in r and r[f] is not None


# --------------------------------------------------------------------------- #
# clean cursor exhaustion -> completeness ok
# --------------------------------------------------------------------------- #
def test_run_clean_exhaustion_completeness_ok(tmp_path):
    s = us.run(client=_one_page([_mkt("KXD-26JUL17-1"), _mkt("KXD-26JUL17-2")]),
               store=tmp_path)
    assert s["cursor_exhausted"] is True
    assert s["truncated"] is False
    assert s["completeness_ok"] is True
    assert s["coverage"] == 1.0
    assert s["coverage_basis"] == "cursor_exhausted"


# --------------------------------------------------------------------------- #
# call cap truncates a still-active cursor -> honest completeness (lesson L10)
# --------------------------------------------------------------------------- #
def test_run_call_cap_truncates_and_lowers_completeness(tmp_path):
    # every page hands back a next cursor -> the cursor is NEVER exhausted; only the cap stops it
    pages = [([_mkt(f"KXE-26JUL17-{i}")], str(i + 1)) for i in range(10)]
    client = FakeKalshi(pages)
    s = us.run(client=client, store=tmp_path, max_calls=3)
    assert client.calls == 3                 # stopped exactly at the cap
    assert s["call_count"] == 3
    assert s["cursor_exhausted"] is False
    assert s["truncated"] is True
    assert s["completeness_ok"] is False     # truncation is never silently claimed as full
    assert s["coverage"] is None
    assert s["coverage_basis"] == "truncated"
    # only the 3 captured markets were written
    assert s["n_markets"] == 3


def test_run_respects_default_max_calls_cap(tmp_path):
    # more pages than the module-level MAX_CALLS, all with a live cursor
    pages = [([_mkt(f"KXF-26JUL17-{i}")], str(i + 1)) for i in range(us.MAX_CALLS + 5)]
    client = FakeKalshi(pages)
    s = us.run(client=client, store=tmp_path)
    assert client.calls == us.MAX_CALLS
    assert s["truncated"] is True
    assert s["completeness_ok"] is False


# --------------------------------------------------------------------------- #
# coverage from a platform total, if the listing ever exposes one (future-proof)
# --------------------------------------------------------------------------- #
def test_run_uses_total_count_when_exposed(tmp_path):
    client = FakeKalshi([([_mkt("KXG-26JUL17-1"), _mkt("KXG-26JUL17-2")], None)],
                        extra_top={"total": 4})
    s = us.run(client=client, store=tmp_path)
    assert s["total_hint"] == 4
    assert s["coverage"] == 0.5              # 2 captured / 4 reported total
    assert s["coverage_basis"] == "total_count"


# --------------------------------------------------------------------------- #
# raw-page provenance preserved (sha256 binds to the bytes on the wire)
# --------------------------------------------------------------------------- #
def test_run_binds_raw_sha256_to_page_bytes(tmp_path):
    from core.canonical import sha256_hex
    p0 = [_mkt("KXH-26JUL17-1")]
    p1 = [_mkt("KXH-26JUL17-2")]
    client = FakeKalshi([(p0, "1"), (p1, None)])
    s = us.run(client=client, store=tmp_path)
    expected = sha256_hex(
        json.dumps({"markets": p0, "cursor": "1"})
        + json.dumps({"markets": p1, "cursor": None}))
    assert s["raw_sha256"] == expected
    # every record carries the same page-bound hash
    recs = [json.loads(ln) for ln in (tmp_path / f"dt={s['day']}.jsonl").read_text().splitlines()]
    assert all(r["raw_sha256"] == expected for r in recs)


# --------------------------------------------------------------------------- #
# append-only write to the dt= partition
# --------------------------------------------------------------------------- #
def test_run_appends_never_rewrites(tmp_path):
    first = us.run(client=_one_page([_mkt("KXI-26JUL17-1")]), store=tmp_path)
    second = us.run(client=_one_page([_mkt("KXI-26JUL17-2")]), store=tmp_path)
    # both passes land in the same dt= file, appended (2 lines, nothing rewritten)
    lines = (tmp_path / f"dt={first['day']}.jsonl").read_text().splitlines()
    assert len(lines) == 2
    tickers = {json.loads(ln)["ticker"] for ln in lines}
    assert tickers == {"KXI-26JUL17-1", "KXI-26JUL17-2"}
    assert first["path"] == second["path"]


def test_run_empty_universe_writes_nothing_but_is_complete(tmp_path):
    s = us.run(client=_one_page([]), store=tmp_path)
    assert s["n_markets"] == 0
    assert s["path"] is None                 # nothing to append -> no file created
    assert s["cursor_exhausted"] is True     # an empty first page is still clean exhaustion
    assert s["completeness_ok"] is True
