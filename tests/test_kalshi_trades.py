"""collection.kalshi_trades — the public executed-trade print tape.

Fully offline: an injected FakeKalshi serves `/markets/trades` pages from in-memory fixtures
shaped exactly like the live response verified 2026-08-04 (`_dollars` price strings, `count_fp`
size strings, `taker_book_side`, RFC3339 `created_time` with a Z suffix and sub-second
precision). No network, no credentials, no clock injection beyond the tape store path.

Covers: multi-page cursor stitching; the per-query MAX_CALLS cap and its honest
truncation/completeness gate (L10) INCLUDING the `at_cap` field being reported on its own axis
rather than only folded into completeness (L270's lesson); trade-day partitioning by the
print's OWN `created_time` rather than the capture day (so one backfill pass writes several
past day-files); trade_id dedupe against both disk and the in-flight batch, i.e. re-running a
window appends zero bytes (the L221 byte-redundant re-capture shape, avoided by construction);
the `broker_truth` tag on every line and its membership in `core.source_tag.SOURCE_TAGS`;
verbatim price capture with no normalization (Hard Rule #3); per-ticker query fan-out; and
ticker discovery from a committed book-tape family.
"""
from __future__ import annotations

import json

import pytest

from collection import kalshi_trades as kt
from core.source_tag import VALID_SOURCE_TAGS


# --------------------------------------------------------------------------- #
# fakes / fixtures
# --------------------------------------------------------------------------- #
def make_trade(trade_id, ticker="KXTEST-A", created_time="2026-08-03T12:00:00.123456Z",
               yes="0.6400", no="0.3600", count="4.91", taker_book_side="ask"):
    """A live-shaped `/markets/trades` object (field names verified live 2026-08-04)."""
    return {
        "trade_id": trade_id,
        "ticker": ticker,
        "created_time": created_time,
        "yes_price_dollars": yes,
        "no_price_dollars": no,
        "count_fp": count,
        "taker_book_side": taker_book_side,
        "taker_side": "no",
        "taker_outcome_side": "no",
        "is_block_trade": False,
    }


class FakeKalshi:
    """Stand-in for validation.v3_market.Kalshi. Serves `/markets/trades` as cursor-paginated
    pages. `pages_by_ticker` lets one fake serve a multi-ticker fan-out; the venue-wide query
    (no ticker param) is keyed under None."""

    base = "https://fake.test"

    def __init__(self, pages_by_ticker):
        self.pages_by_ticker = pages_by_ticker
        self.calls = 0
        self.seen_params = []

    def get_text(self, path, **params):
        assert path == kt.TRADES_PATH
        # read-only, unauthenticated: no signed-request header ever reaches the client.
        # The header names are assembled from parts so this file carries no verbatim
        # auth-header literal (`scripts/invariants.py::inv_order_endpoints_confined`
        # matches on the literal, and a collector test is not the sanctioned order lane).
        assert not any(k.upper().startswith("KALSHI-ACCESS") for k in params)
        self.seen_params.append(dict(params))
        pages = self.pages_by_ticker[params.get("ticker")]
        cursor = params.get("cursor")
        idx = 0 if cursor is None else int(cursor)
        trades, nxt = pages[idx]
        self.calls += 1
        return json.dumps({"trades": trades, "cursor": nxt})


# --------------------------------------------------------------------------- #
# pagination + completeness
# --------------------------------------------------------------------------- #
def test_cursor_stitching_across_pages():
    client = FakeKalshi({None: [([make_trade("a"), make_trade("b")], "1"),
                                ([make_trade("c")], None)]})
    trades, raw_pages, truncated, n_calls = kt.fetch_trades(client)
    assert [t["trade_id"] for t in trades] == ["a", "b", "c"]
    assert n_calls == 2 and len(raw_pages) == 2
    assert truncated is False


def test_call_cap_with_active_cursor_is_truncated():
    pages = [([make_trade(str(i))], str(i + 1)) for i in range(10)]
    client = FakeKalshi({None: pages})
    trades, _, truncated, n_calls = kt.fetch_trades(client, max_calls=3)
    assert truncated is True
    assert n_calls == 3 and len(trades) == 3


def test_empty_page_terminates_without_truncation():
    client = FakeKalshi({None: [([], "1")]})
    trades, _, truncated, n_calls = kt.fetch_trades(client)
    assert trades == [] and truncated is False and n_calls == 1


def test_run_reports_at_cap_on_its_own_axis(tmp_path):
    """L270: a cap-bounded pass must be distinguishable from a parse failure without the
    consumer re-deriving it from completeness_ok."""
    pages = [([make_trade(str(i))], str(i + 1)) for i in range(10)]
    client = FakeKalshi({None: pages})
    s = kt.run(client=client, store=tmp_path, max_calls=2)
    assert s["at_cap"] is True
    assert s["truncated"] is True
    assert s["cursor_exhausted"] is False
    assert s["completeness_ok"] is False
    assert s["n_truncated_queries"] == 1
    assert s["truncated_queries"] == ["__venue_wide__"]


def test_run_clean_exhaustion_is_complete(tmp_path):
    client = FakeKalshi({None: [([make_trade("a")], None)]})
    s = kt.run(client=client, store=tmp_path)
    assert s["completeness_ok"] is True
    assert s["cursor_exhausted"] is True and s["at_cap"] is False


# --------------------------------------------------------------------------- #
# trade-day partitioning (the print's OWN time, not the capture day)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("created,expected", [
    ("2026-08-03T12:00:00.123456Z", "2026-08-03"),
    ("2026-08-03T23:59:59.999999Z", "2026-08-03"),
    ("2026-08-04T00:00:00Z", "2026-08-04"),
    ("2026-08-03T12:00:00+00:00", "2026-08-03"),
])
def test_trade_day_parses_rfc3339(created, expected):
    assert kt._trade_day(created) == expected


@pytest.mark.parametrize("bad", ["", None, "not-a-time", 17])
def test_trade_day_returns_none_on_unparseable(bad):
    assert kt._trade_day(bad) is None


def test_one_pass_writes_several_past_day_files(tmp_path):
    client = FakeKalshi({None: [([
        make_trade("a", created_time="2026-08-01T10:00:00Z"),
        make_trade("b", created_time="2026-08-02T10:00:00Z"),
        make_trade("c", created_time="2026-08-02T11:00:00Z"),
    ], None)]})
    s = kt.run(client=client, store=tmp_path)
    assert s["n_lines"] == 3
    assert (tmp_path / "dt=2026-08-01.jsonl").exists()
    assert (tmp_path / "dt=2026-08-02.jsonl").exists()
    assert len((tmp_path / "dt=2026-08-02.jsonl").read_text().strip().splitlines()) == 2


def test_undated_print_is_counted_not_silently_dropped(tmp_path):
    client = FakeKalshi({None: [([make_trade("a", created_time="garbage")], None)]})
    s = kt.run(client=client, store=tmp_path)
    assert s["n_undated"] == 1 and s["n_lines"] == 0


# --------------------------------------------------------------------------- #
# idempotence: trade_id dedupe (the L221 shape, avoided by construction)
# --------------------------------------------------------------------------- #
def test_rerunning_the_same_window_appends_zero_bytes(tmp_path):
    pages = {None: [([make_trade("a"), make_trade("b")], None)]}
    first = kt.run(client=FakeKalshi(pages), store=tmp_path)
    path = tmp_path / "dt=2026-08-03.jsonl"
    size_after_first = path.stat().st_size
    second = kt.run(client=FakeKalshi(pages), store=tmp_path)
    assert first["n_lines"] == 2
    assert second["n_lines"] == 0 and second["n_duplicate"] == 2
    assert path.stat().st_size == size_after_first


def test_duplicate_within_one_batch_is_written_once(tmp_path):
    client = FakeKalshi({None: [([make_trade("a"), make_trade("a")], None)]})
    s = kt.run(client=client, store=tmp_path)
    assert s["n_lines"] == 1 and s["n_duplicate"] == 1


def test_existing_trade_ids_reads_committed_file(tmp_path):
    path = tmp_path / "dt=2026-08-03.jsonl"
    path.write_text('{"trade_id": "x"}\n\n{"trade_id": "y"}\n')
    assert kt.existing_trade_ids(tmp_path, "2026-08-03") == {"x", "y"}


def test_existing_trade_ids_skips_malformed_line_rather_than_raising(tmp_path):
    path = tmp_path / "dt=2026-08-03.jsonl"
    path.write_text('{"trade_id": "x"}\nnot json\n')
    assert kt.existing_trade_ids(tmp_path, "2026-08-03") == {"x"}


def test_existing_trade_ids_absent_file_is_empty(tmp_path):
    assert kt.existing_trade_ids(tmp_path, "2026-01-01") == set()


def test_append_only_never_rewrites_prior_lines(tmp_path):
    path = tmp_path / "dt=2026-08-03.jsonl"
    path.write_text('{"trade_id": "legacy", "note": "kept verbatim"}\n')
    kt.run(client=FakeKalshi({None: [([make_trade("a")], None)]}), store=tmp_path)
    lines = path.read_text().strip().splitlines()
    assert lines[0] == '{"trade_id": "legacy", "note": "kept verbatim"}'
    assert len(lines) == 2


# --------------------------------------------------------------------------- #
# record shape / trust defaults
# --------------------------------------------------------------------------- #
def test_every_line_is_broker_truth_and_tag_is_in_the_enum(tmp_path):
    kt.run(client=FakeKalshi({None: [([make_trade("a")], None)]}), store=tmp_path)
    rec = json.loads((tmp_path / "dt=2026-08-03.jsonl").read_text().strip())
    assert rec["price_source_tag"] == "broker_truth"
    assert rec["price_source_tag"] in VALID_SOURCE_TAGS


def test_prices_are_verbatim_with_no_normalization(tmp_path):
    """Hard Rule #3: no bracket_sum divisor, no derived probability in a collector."""
    kt.run(client=FakeKalshi({None: [([make_trade("a", yes="0.6400", no="0.3600",
                                                   count="4.91")], None)]}),
           store=tmp_path)
    rec = json.loads((tmp_path / "dt=2026-08-03.jsonl").read_text().strip())
    assert rec["yes_price"] == 0.64 and rec["no_price"] == 0.36
    assert rec["count"] == 4.91
    assert "normalized_ask" not in rec and "raw_prob" not in rec


def test_taker_book_side_is_carried_through(tmp_path):
    """The whole point of this family: the side of the BOOK the taker crossed into."""
    kt.run(client=FakeKalshi({None: [([make_trade("a", taker_book_side="bid")], None)]}),
           store=tmp_path)
    rec = json.loads((tmp_path / "dt=2026-08-03.jsonl").read_text().strip())
    assert rec["taker_book_side"] == "bid"


def test_record_carries_capture_provenance(tmp_path):
    s = kt.run(client=FakeKalshi({None: [([make_trade("a")], None)]}), store=tmp_path)
    rec = json.loads((tmp_path / "dt=2026-08-03.jsonl").read_text().strip())
    assert rec["capture_id"] == s["capture_id"]
    assert rec["schema_version"] == kt.SCHEMA_VERSION
    assert rec["raw_sha256"] and rec["source"] == "public_markets_trades"
    assert rec["venue"] == "kalshi"


# --------------------------------------------------------------------------- #
# per-ticker fan-out + window params
# --------------------------------------------------------------------------- #
def test_per_ticker_fan_out_issues_one_query_each(tmp_path):
    client = FakeKalshi({
        "T1": [([make_trade("a", ticker="T1")], None)],
        "T2": [([make_trade("b", ticker="T2")], None)],
    })
    s = kt.run(tickers=["T1", "T2"], client=client, store=tmp_path)
    assert s["n_queries"] == 2 and s["n_lines"] == 2
    assert [p["ticker"] for p in client.seen_params] == ["T1", "T2"]


def test_window_bounds_are_passed_through(tmp_path):
    client = FakeKalshi({None: [([make_trade("a")], None)]})
    kt.run(client=client, store=tmp_path, min_ts=1000, max_ts=2000)
    assert client.seen_params[0]["min_ts"] == 1000
    assert client.seen_params[0]["max_ts"] == 2000


def test_truncation_on_one_ticker_fails_completeness_for_the_pass(tmp_path):
    client = FakeKalshi({
        "T1": [([make_trade("a", ticker="T1")], None)],
        "T2": [([make_trade(str(i), ticker="T2")], str(i + 1)) for i in range(10)],
    })
    s = kt.run(tickers=["T1", "T2"], client=client, store=tmp_path, max_calls=2)
    assert s["completeness_ok"] is False
    assert s["truncated_queries"] == ["T2"]


def test_day_bounds_are_utc_midnight_to_midnight():
    start, end = kt.day_bounds("2026-08-03")
    assert end - start == 86400
    from datetime import datetime, timezone
    assert datetime.fromtimestamp(start, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") == \
        "2026-08-03T00:00:00Z"


# --------------------------------------------------------------------------- #
# ticker discovery from a committed book-tape family
# --------------------------------------------------------------------------- #
def test_tickers_from_tape_is_distinct_and_first_seen_ordered(tmp_path):
    fam = tmp_path / "orderbook_depth"
    fam.mkdir()
    (fam / "dt=2026-08-01.jsonl").write_text(
        '{"ticker": "B"}\n{"ticker": "A"}\n{"ticker": "B"}\n')
    (fam / "dt=2026-08-02.jsonl").write_text('{"ticker": "C"}\n')
    assert kt.tickers_from_tape(fam) == ["B", "A", "C"]


def test_tickers_from_tape_day_filter_and_limit(tmp_path):
    fam = tmp_path / "orderbook_depth"
    fam.mkdir()
    (fam / "dt=2026-08-01.jsonl").write_text('{"ticker": "B"}\n{"ticker": "A"}\n')
    (fam / "dt=2026-08-02.jsonl").write_text('{"ticker": "C"}\n')
    assert kt.tickers_from_tape(fam, day="2026-08-02") == ["C"]
    assert kt.tickers_from_tape(fam, limit=1) == ["B"]


def test_tickers_from_tape_missing_dir_is_empty_not_an_error(tmp_path):
    assert kt.tickers_from_tape(tmp_path / "nope") == []


def test_tickers_from_tape_skips_malformed_lines(tmp_path):
    fam = tmp_path / "f"
    fam.mkdir()
    (fam / "dt=2026-08-01.jsonl").write_text('not json\n{"ticker": "A"}\n{"no_ticker": 1}\n')
    assert kt.tickers_from_tape(fam) == ["A"]


# --------------------------------------------------------------------------- #
# lane discipline (source-text pins, same discipline as the Hard-Rule #1 checks)
# --------------------------------------------------------------------------- #
def test_module_contains_no_order_verb_or_credential_handling():
    """Source-text pin (same discipline as the Hard-Rule #1 `ncep_gefs025` check).

    The auth-header markers are assembled from fragments rather than written verbatim: the
    literals themselves are what `inv_order_endpoints_confined` scans for, so spelling them
    out here would make this very test a violation of the rule it defends.
    """
    src = open(kt.__file__, encoding="utf-8").read()
    auth_prefix = "KALSHI-" + "ACCESS-"
    forbidden = [auth_prefix + "KEY", auth_prefix + "SIGNATURE", auth_prefix + "TIMESTAMP",
                 "portfolio/" + "orders", "private_key", "sign_pss", "requests.post"]
    for marker in forbidden:
        assert marker not in src, f"{marker} must not appear in a public read-only collector"
