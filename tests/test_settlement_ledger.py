"""collection.settlement_ledger — the systematic settlement-truth harvester.

Fully offline: an injected FakeKalshi serves settled `/markets` pages from in-memory fixtures
(the exact `_fp`/`_dollars` string-suffix shape Kalshi returns) and the migration reads a
temp-dir copy of the legacy cache schema — no live network, no clock injection beyond the
tape store path. Covers: the binary/scalar/pending filter (lesson L52), broker_truth tagging,
terminal volume/OI capture, the MAX_SETTLED_MARKETS cap + truncation completeness gate
(lesson L10), append-only cross-family dedup, and the non-destructive legacy-cache migration.
"""
from __future__ import annotations

import json

from collection import settlement_ledger as sl


# --------------------------------------------------------------------------- #
# fakes / fixtures
# --------------------------------------------------------------------------- #
class FakeKalshi:
    """Stand-in for validation.v3_market.Kalshi. Serves `/markets?status=settled` as cursor-
    paginated pages of raw market objects; `fail_after` pages in to simulate a transport error."""

    base = "https://fake.test"

    def __init__(self, pages):
        # pages: list of (markets_list, next_cursor|None)
        self.pages = pages
        self.calls = 0

    def get_text(self, path, **params):
        assert path == "/markets"
        assert params["status"] == "settled"
        cursor = params.get("cursor")
        idx = 0 if cursor is None else int(cursor)
        markets, nxt = self.pages[idx]
        self.calls += 1
        return json.dumps({"markets": markets, "cursor": nxt})


def _mkt(ticker, result, *, event_ticker=None, close_time="2026-07-16T04:00:00Z",
         settlement_value="1.0000", volume="12.00", open_interest="5.00", title="T"):
    return {
        "ticker": ticker,
        "event_ticker": event_ticker or ticker.rsplit("-", 1)[0],
        "result": result,
        "close_time": close_time,
        "settlement_ts": "2026-07-16T04:00:05Z",
        "settlement_value_dollars": settlement_value,
        "expiration_value": "",
        "volume_fp": volume,
        "open_interest_fp": open_interest,
        "title": title,
        "is_provisional": False,
    }


def _one_page(markets):
    return FakeKalshi([(markets, None)])


# --------------------------------------------------------------------------- #
# field parsing
# --------------------------------------------------------------------------- #
def test_to_float_handles_strings_blanks_and_numbers():
    assert sl._to_float("1.0000") == 1.0
    assert sl._to_float("12.50") == 12.5
    assert sl._to_float("") is None            # blank -> honest None, never fabricated 0
    assert sl._to_float(None) is None
    assert sl._to_float("garbage") is None
    assert sl._to_float(3) == 3.0


def test_record_from_market_tags_broker_truth_and_captures_companion_features():
    rec = sl._record_from_market(
        _mkt("KXNBA-26JUL15-LAL", "yes", settlement_value="1.0000",
             volume="34.00", open_interest="8.00"),
        captured_at="2026-07-17T10:00:00+00:00", capture_id="X", raw_sha256="abc")
    assert rec["price_source_tag"] == "broker_truth"      # Kalshi's own truth, not synthetic
    assert rec["result"] == "yes"
    assert rec["settlement_value"] == 1.0
    assert rec["volume"] == 34.0                          # terminal companion features
    assert rec["open_interest"] == 8.0
    assert rec["schema_version"] == "settlement_ledger.v1"
    assert rec["series"] == "KXNBA"


# --------------------------------------------------------------------------- #
# binary / scalar / pending filter — lesson L52
# --------------------------------------------------------------------------- #
def test_run_filters_scalar_and_pending_keeps_only_binary(tmp_path):
    client = _one_page([
        _mkt("KXA-26JUL15-1", "yes"),
        _mkt("KXA-26JUL15-2", "no"),
        _mkt("KXA-26JUL15-3", "scalar"),     # non-binary -> dropped + counted (L52)
        _mkt("KXA-26JUL15-4", ""),           # settled but no finalized label -> pending
    ])
    s = sl.run(client=client, store=tmp_path)
    assert s["n_pulled"] == 4
    assert s["n_binary"] == 2
    assert s["n_scalar_dropped"] == 1
    assert s["n_pending"] == 1
    assert s["n_new"] == 2
    # scalar/pending do NOT gate completeness — they are structural, not failures
    assert s["completeness_ok"] is True

    recs = [json.loads(ln) for ln in (tmp_path / f"dt={s['day']}.jsonl").read_text().splitlines()]
    assert len(recs) == 2
    assert {r["result"] for r in recs} == {"yes", "no"}
    assert all(r["price_source_tag"] == "broker_truth" for r in recs)
    # a scalar market never reaches the tape as a yes/no label
    assert "KXA-26JUL15-3" not in {r["ticker"] for r in recs}


# --------------------------------------------------------------------------- #
# cap + truncation -> honest completeness (lesson L10)
# --------------------------------------------------------------------------- #
def test_run_cap_truncates_and_lowers_completeness(tmp_path):
    many = [_mkt(f"KXB-26JUL15-{i}", "yes") for i in range(10)]
    client = _one_page(many)
    s = sl.run(client=client, store=tmp_path, max_markets=3)
    assert s["markets_truncated"] is True
    assert s["n_pulled"] == 3
    assert s["completeness_ok"] is False     # truncation is never silently claimed as full


def test_run_limit_caps_pull_below_max(tmp_path):
    many = [_mkt(f"KXC-26JUL15-{i}", "yes") for i in range(10)]
    s = sl.run(client=_one_page(many), store=tmp_path, limit=4)
    assert s["n_pulled"] == 4
    assert s["markets_truncated"] is True


def test_run_pagination_follows_cursor(tmp_path):
    client = FakeKalshi([
        ([_mkt("KXD-26JUL15-1", "yes")], "1"),      # page 0 -> cursor "1"
        ([_mkt("KXD-26JUL15-2", "no")], None),      # page 1 -> end
    ])
    s = sl.run(client=client, store=tmp_path)
    assert client.calls == 2
    assert s["n_binary"] == 2
    assert s["markets_truncated"] is False
    assert s["completeness_ok"] is True


# --------------------------------------------------------------------------- #
# append-only cross-family dedup
# --------------------------------------------------------------------------- #
def test_run_dedups_against_existing_family_keys(tmp_path):
    markets = [_mkt("KXE-26JUL15-1", "yes"), _mkt("KXE-26JUL15-2", "no")]
    first = sl.run(client=_one_page(markets), store=tmp_path)
    assert first["n_new"] == 2

    # a second identical pull appends nothing new (idempotent, append-only)
    second = sl.run(client=_one_page(markets), store=tmp_path)
    assert second["n_binary"] == 2
    assert second["n_new"] == 0
    assert second["n_duplicate_skipped"] == 2

    # a changed settlement_value is a genuinely different key -> a new line
    changed = [_mkt("KXE-26JUL15-1", "yes", settlement_value="0.5000")]
    third = sl.run(client=_one_page(changed), store=tmp_path)
    assert third["n_new"] == 1

    all_lines = (tmp_path / f"dt={first['day']}.jsonl").read_text().splitlines()
    assert len(all_lines) == 3        # 2 + 0 + 1, nothing rewritten


def test_run_dedups_within_a_single_pass(tmp_path):
    dup = [_mkt("KXF-26JUL15-1", "yes"), _mkt("KXF-26JUL15-1", "yes")]
    s = sl.run(client=_one_page(dup), store=tmp_path)
    assert s["n_binary"] == 2
    assert s["n_new"] == 1
    assert s["n_duplicate_skipped"] == 1


# --------------------------------------------------------------------------- #
# migration of the four legacy per-probe caches (non-destructive)
# --------------------------------------------------------------------------- #
def _legacy_cache(tmp_path, name, markets):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    p = d / "settlement.json"
    p.write_text(json.dumps({"schema_version": f"{name}.v1", "markets": markets}))
    return p


def test_migrate_folds_legacy_caches_deduped_and_filters_scalar(tmp_path):
    store = tmp_path / "ledger"
    c1 = _legacy_cache(tmp_path, "q26_settlement_cache", {
        "KXKBO-26JUL07-A": {"result": "yes", "close_time": "2026-07-07T12:00:00Z",
                            "event_ticker": "KXKBO-26JUL07", "series": "KXKBO"},
        "KXKBO-26JUL07-B": {"result": "no", "close_time": "2026-07-07T12:00:00Z",
                            "event_ticker": "KXKBO-26JUL07", "series": "KXKBO"},
        "KXKBO-26JUL05-S": {"result": "scalar", "close_time": "2026-07-05T09:00:00Z",
                            "event_ticker": "KXKBO-26JUL05", "series": "KXKBO"},
    })
    # second cache overlaps A (same key) and adds one new market
    c2 = _legacy_cache(tmp_path, "q27_settlement_cache", {
        "KXKBO-26JUL07-A": {"result": "yes", "close_time": "2026-07-07T12:00:00Z",
                            "event_ticker": "KXKBO-26JUL07", "series": "KXKBO"},
        "KXKBO-26JUL08-C": {"result": "no", "close_time": "2026-07-08T12:00:00Z",
                            "event_ticker": "KXKBO-26JUL08", "series": "KXKBO"},
    })
    missing = tmp_path / "q99_settlement_cache" / "settlement.json"

    r = sl.migrate_caches(store=store, cache_paths=[c1, c2, missing])
    assert r["keys_before"] == 0
    assert r["n_new"] == 3                    # A, B (from c1) + C (from c2); A in c2 dedup'd
    assert r["n_duplicate_skipped"] == 1      # c2's repeat of A
    assert r["n_scalar_dropped"] == 1         # the scalar market never migrated (L52)
    assert r["n_missing"] == 1
    assert r["keys_after"] == 3

    recs = [json.loads(ln) for ln in
            list(store.glob("dt=*.jsonl"))[0].read_text().splitlines()]
    assert len(recs) == 3
    assert all(r["price_source_tag"] == "broker_truth" for r in recs)
    assert all(r["settlement_value"] is None for r in recs)     # legacy caches lack it
    assert all(r["source"].startswith("migrated:") for r in recs)
    # scalar never reaches the ledger
    assert "KXKBO-26JUL05-S" not in {r["ticker"] for r in recs}


def test_migrate_is_idempotent(tmp_path):
    store = tmp_path / "ledger"
    c1 = _legacy_cache(tmp_path, "q30_settlement_cache", {
        "KXA-26JUL11-1": {"result": "no", "close_time": "2026-07-11T15:00:00Z",
                          "event_ticker": "KXA-26JUL11", "series": "KXA"},
    })
    first = sl.migrate_caches(store=store, cache_paths=[c1])
    assert first["n_new"] == 1
    second = sl.migrate_caches(store=store, cache_paths=[c1])
    assert second["n_new"] == 0
    assert second["n_duplicate_skipped"] == 1


def test_run_with_also_migrate_folds_both(tmp_path):
    store = tmp_path / "ledger"
    c1 = _legacy_cache(tmp_path, "q26_settlement_cache", {
        "KXLEG-26JUL07-A": {"result": "yes", "close_time": "2026-07-07T12:00:00Z",
                            "event_ticker": "KXLEG-26JUL07", "series": "KXLEG"},
    })
    # monkeypatch the legacy paths the run() migration reads
    orig = sl.LEGACY_CACHE_PATHS
    sl.LEGACY_CACHE_PATHS = [c1]
    try:
        s = sl.run(client=_one_page([_mkt("KXLIVE-26JUL15-1", "yes")]),
                   store=store, also_migrate=True)
    finally:
        sl.LEGACY_CACHE_PATHS = orig
    assert s["n_new"] == 1                     # the live binary market
    assert s["migration"]["n_new"] == 1        # the migrated legacy market
    tickers = {json.loads(ln)["ticker"]
               for ln in list(store.glob("dt=*.jsonl"))[0].read_text().splitlines()}
    assert tickers == {"KXLIVE-26JUL15-1", "KXLEG-26JUL07-A"}
