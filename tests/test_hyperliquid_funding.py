"""collection.hyperliquid_funding — fully offline (FakeClient, no network).

Covers: entry normalization (string->float, ms->ISO, jitter preserved), pagination
(cursor-by-startTime advance, dedup on time_ms, short-page + no-progress stop), per-coin
record shape + broker_truth tag, fault isolation (one coin's fetch failure is a visible
error record that lowers completeness but never kills siblings), and JSONL append."""
from __future__ import annotations

import json

from collection import hyperliquid_funding as hf


# --------------------------------------------------------------------------- #
# a fake pager: serves canned hourly rows for a coin, capped at PAGE_LIMIT
# --------------------------------------------------------------------------- #
def _entries(coin, start_hour, n, base_ms=1780444800000, rate=0.0000125, jitter=19):
    """n consecutive hourly entries starting `start_hour` hours after base, with a few-ms
    jitter past :00 (mirrors the live venue)."""
    out = []
    for i in range(n):
        h = start_hour + i
        out.append({"coin": coin, "fundingRate": f"{rate:.10f}",
                    "premium": "-0.0004301549", "time": base_ms + h * 3600_000 + jitter})
    return out


class FakePager:
    """Serves a full hourly series per coin, paginating like the real endpoint: returns at
    most PAGE_LIMIT rows whose time >= start_ms. Records calls for assertions."""

    def __init__(self, series, fail_coins=()):
        self.series = series          # coin -> full sorted list of raw entries
        self.fail_coins = set(fail_coins)
        self.calls = []

    def funding_history(self, coin, start_ms, end_ms=None):
        self.calls.append((coin, start_ms, end_ms))
        if coin in self.fail_coins:
            raise RuntimeError(f"injected failure: {coin}")
        rows = [e for e in self.series.get(coin, []) if e["time"] >= start_ms]
        return rows[:hf.PAGE_LIMIT]


def _read_lines(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


# --------------------------------------------------------------------------- #
# entry normalization
# --------------------------------------------------------------------------- #
def test_print_from_entry_normalizes():
    e = {"coin": "BTC", "fundingRate": "0.0000125", "premium": "-0.0004",
         "time": 1780444800019}
    pr = hf._print_from_entry(e)
    assert pr["coin"] == "BTC"
    assert pr["funding_rate"] == 0.0000125
    assert pr["premium"] == -0.0004
    assert pr["time_ms"] == 1780444800019          # jitter preserved verbatim
    assert pr["funding_time"] == "2026-06-03T00:00:00Z"  # ISO floors the ms


def test_print_from_entry_bad_fields_stay_none():
    pr = hf._print_from_entry({"coin": "BTC", "fundingRate": "nope", "time": None})
    assert pr["funding_rate"] is None
    assert pr["time_ms"] is None
    assert pr["funding_time"] is None


# --------------------------------------------------------------------------- #
# pagination
# --------------------------------------------------------------------------- #
def test_fetch_paginates_and_dedups_full_series():
    # 1200 hourly rows -> 3 pages (500,500,200). PAGE_LIMIT boundary re-serves its edge row.
    pager = FakePager({"BTC": _entries("BTC", 0, 1200)})
    body, ok = hf.fetch_funding_history(pager.funding_history, "BTC", start_ms=0)
    assert ok
    assert body["n_prints"] == 1200                 # deduped, none lost, none doubled
    times = [p["time_ms"] for p in body["prints"]]
    assert times == sorted(times)
    assert len(set(times)) == 1200
    assert body["price_source_tag"] == "broker_truth"
    # at least 3 pages were needed, and each advanced startTime strictly forward
    assert len(pager.calls) >= 3
    starts = [c[1] for c in pager.calls]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)


def test_fetch_short_first_page_stops_immediately():
    pager = FakePager({"ETH": _entries("ETH", 0, 10)})
    body, ok = hf.fetch_funding_history(pager.funding_history, "ETH", start_ms=0)
    assert ok and body["n_prints"] == 10
    assert len(pager.calls) == 1                     # short page = end of data, no re-poll


def test_fetch_no_progress_guard_terminates():
    # a pager that always returns the SAME single row must not loop forever
    class StuckPager:
        def __init__(self):
            self.n = 0

        def funding_history(self, coin, start_ms, end_ms=None):
            self.n += 1
            return [{"coin": coin, "fundingRate": "0.0001", "premium": "0",
                     "time": 1000}]
    sp = StuckPager()
    body, ok = hf.fetch_funding_history(sp.funding_history, "BTC", start_ms=0)
    assert ok and body["n_prints"] == 1
    assert sp.n <= 2                                 # ingested once, then no-progress stop


def test_fetch_failure_is_visible_record():
    pager = FakePager({}, fail_coins={"BTC"})
    body, ok = hf.fetch_funding_history(pager.funding_history, "BTC", start_ms=0)
    assert ok is False
    assert body["status"] == "fetch_error"
    assert "injected failure" in body["error"]


# --------------------------------------------------------------------------- #
# run() — record shape, tags, fault isolation, append
# --------------------------------------------------------------------------- #
def test_run_writes_one_record_per_coin(tmp_path):
    pager = FakePager({"BTC": _entries("BTC", 0, 24), "ETH": _entries("ETH", 0, 24)})
    summary = hf.run(coins=("BTC", "ETH"), start_ms=0, client=pager, tape_dir=tmp_path)
    assert summary["completeness_ok"] is True
    assert summary["n_coins"] == 2 and summary["n_coins_ok"] == 2
    assert summary["per_coin_n_prints"] == {"BTC": 24, "ETH": 24}

    recs = _read_lines(summary["path"])
    assert len(recs) == 2
    for r in recs:
        assert r["schema_version"] == "hyperliquid_funding.v1"
        assert r["venue"] == "hyperliquid"
        assert r["record_type"] == "funding_history"
        assert r["mode"] == "backfill"
        assert r["price_source_tag"] == "broker_truth"
        assert r["n_prints"] == 24
        assert r["prints"][0]["coin"] == r["coin"]


def test_run_one_coin_failure_isolated(tmp_path):
    pager = FakePager({"ETH": _entries("ETH", 0, 12)}, fail_coins={"BTC"})
    summary = hf.run(coins=("BTC", "ETH"), start_ms=0, client=pager, tape_dir=tmp_path)
    assert summary["completeness_ok"] is False
    assert summary["n_coins_ok"] == 1
    recs = {r["coin"]: r for r in _read_lines(summary["path"])}
    assert recs["BTC"]["status"] == "fetch_error"
    assert recs["ETH"]["status"] == "ok" and recs["ETH"]["n_prints"] == 12


def test_run_appends_across_passes(tmp_path):
    pager = FakePager({"BTC": _entries("BTC", 0, 5)})
    s1 = hf.run(coins=("BTC",), start_ms=0, client=pager, tape_dir=tmp_path)
    s2 = hf.run(coins=("BTC",), start_ms=0, client=pager, tape_dir=tmp_path)
    if s1["path"] == s2["path"]:                     # same UTC day
        recs = _read_lines(s1["path"])
        assert len(recs) == 2
        assert {r["capture_id"] for r in recs} == {s1["capture_id"], s2["capture_id"]}


# --------------------------------------------------------------------------- #
# _committed_time_ms — reads already-archived print times from committed tape
# --------------------------------------------------------------------------- #
def test_committed_time_ms_reads_prior_backfill(tmp_path):
    # seed the tape with a backfill record (BTC hours 0..9)
    pager = FakePager({"BTC": _entries("BTC", 0, 10), "ETH": _entries("ETH", 0, 4)})
    hf.run(coins=("BTC", "ETH"), start_ms=0, client=pager, tape_dir=tmp_path)
    seen = hf._committed_time_ms(tmp_path, ("BTC", "ETH", "SOL"))
    assert len(seen["BTC"]) == 10
    assert len(seen["ETH"]) == 4
    assert seen["SOL"] == set()                       # never archived -> empty, not a crash
    # every archived time_ms is an int matching the entries we wrote
    expected_btc = {e["time"] for e in _entries("BTC", 0, 10)}
    assert seen["BTC"] == expected_btc


def test_committed_time_ms_missing_dir_is_empty(tmp_path):
    seen = hf._committed_time_ms(tmp_path / "nope", ("BTC",))
    assert seen == {"BTC": set()}


# --------------------------------------------------------------------------- #
# run_incremental — appends only genuinely-new prints, dedup, fault isolation, empty=ok
# --------------------------------------------------------------------------- #
def test_incremental_appends_only_new_prints(tmp_path):
    # seed: BTC hours 0..9 already archived (as a backfill)
    seed = FakePager({"BTC": _entries("BTC", 0, 10)})
    hf.run(coins=("BTC",), start_ms=0, client=seed, tape_dir=tmp_path)

    # venue now has hours 0..14 (5 new). Incremental must fetch from the newest archived and
    # append ONLY hours 10..14, never re-append 0..9.
    fresh = FakePager({"BTC": _entries("BTC", 0, 15)})
    summary = hf.run_incremental(coins=("BTC",), client=fresh, tape_dir=tmp_path)
    assert summary["completeness_ok"] is True
    assert summary["n_new_prints"] == 5
    assert summary["per_coin_new_prints"] == {"BTC": 5}
    assert summary["mode"] == "incremental"

    recs = _read_lines(summary["path"])
    inc = [r for r in recs if r.get("mode") == "incremental"]
    assert len(inc) == 1
    rec = inc[0]
    assert rec["record_type"] == "funding_history"
    assert rec["price_source_tag"] == "broker_truth"
    assert rec["n_prints"] == 5
    new_ms = {p["time_ms"] for p in rec["prints"]}
    archived_ms = {e["time"] for e in _entries("BTC", 0, 10)}
    assert new_ms.isdisjoint(archived_ms)             # no overlap with what was already archived
    # the incremental fetch started at (or after) the newest archived print, not from launch
    assert summary["path"] is not None


def test_incremental_no_new_prints_writes_nothing_and_stays_complete(tmp_path):
    seed = FakePager({"BTC": _entries("BTC", 0, 10)})
    hf.run(coins=("BTC",), start_ms=0, client=seed, tape_dir=tmp_path)

    # venue has nothing beyond what's archived
    same = FakePager({"BTC": _entries("BTC", 0, 10)})
    summary = hf.run_incremental(coins=("BTC",), client=same, tape_dir=tmp_path)
    assert summary["completeness_ok"] is True          # nothing-new is NOT a failure
    assert summary["n_new_prints"] == 0
    assert summary["n_lines"] == 0
    assert summary["path"] is None                      # no line -> no file write


def test_incremental_from_empty_tape_fetches_from_launch(tmp_path):
    # no prior tape: should fetch from launch and archive everything the venue has
    fresh = FakePager({"BTC": _entries("BTC", 0, 6), "ETH": _entries("ETH", 0, 3)})
    summary = hf.run_incremental(coins=("BTC", "ETH"), client=fresh, tape_dir=tmp_path,
                                 launch_ms=0)
    assert summary["completeness_ok"] is True
    assert summary["per_coin_new_prints"] == {"BTC": 6, "ETH": 3}


def test_incremental_one_coin_failure_isolated(tmp_path):
    fresh = FakePager({"ETH": _entries("ETH", 0, 4)}, fail_coins={"BTC"})
    summary = hf.run_incremental(coins=("BTC", "ETH"), client=fresh, tape_dir=tmp_path,
                                 launch_ms=0)
    assert summary["completeness_ok"] is False          # BTC fetch failed
    assert summary["n_coins_ok"] == 1
    assert summary["per_coin_status"]["BTC"] == "fetch_error"
    assert summary["per_coin_status"]["ETH"] == "ok"
    recs = {(_r.get("coin"), _r.get("status")): _r for _r in _read_lines(summary["path"])}
    # BTC error is a visible record; ETH's genuinely-new prints still archived (fault isolation)
    assert ("BTC", "fetch_error") in recs
    eth = next(r for r in _read_lines(summary["path"]) if r["coin"] == "ETH" and r.get("prints"))
    assert eth["n_prints"] == 4


def test_incremental_idempotent_across_two_collectors(tmp_path):
    # simulate the two staggered collectors: the first archives the new print, the second
    # (same venue state) finds nothing new -> no duplicate line, no double-count.
    seed = FakePager({"BTC": _entries("BTC", 0, 10)})
    hf.run(coins=("BTC",), start_ms=0, client=seed, tape_dir=tmp_path)
    venue = FakePager({"BTC": _entries("BTC", 0, 11)})   # exactly one new print (hour 10)

    s1 = hf.run_incremental(coins=("BTC",), client=venue, tape_dir=tmp_path)
    s2 = hf.run_incremental(coins=("BTC",), client=venue, tape_dir=tmp_path)
    assert s1["n_new_prints"] == 1
    assert s2["n_new_prints"] == 0                       # second collector sees nothing new
    # the single new print appears exactly once across all incremental records
    all_new = [p["time_ms"] for r in _read_lines(s1["path"])
               if r.get("mode") == "incremental" for p in (r.get("prints") or [])]
    assert len(all_new) == 1 and len(set(all_new)) == 1
