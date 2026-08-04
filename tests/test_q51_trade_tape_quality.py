"""Offline tests for scripts/q51_trade_tape_quality.py (Q51 — trade-tape data-quality audit).

No network anywhere. Two classes of test:

* pure-function tests over hand-built inputs, which pin the DEFECT DETECTORS (a healthy tape
  must not be the only input a detector has ever seen — L191's shape);
* `test_acceptance_*` tests over committed tape. `tape/kalshi_trades/dt=2026-08-03.jsonl` is
  a frozen past day AND is `trade_id`-deduped, so its integrity numbers are asserted
  EXACTLY. The `orderbook_depth` side is asserted only DIRECTIONALLY (bounds, not equalities)
  because a later stranded-branch sweep may legitimately append more snapshots for the same
  day — an acceptance test that a sweep would break is a test that would be deleted.
"""
from __future__ import annotations

import json

import pytest

from scripts import q51_trade_tape_quality as Q
from scripts.q51_maker_fillsim import TAKER_BUYS, TAKER_SELLS


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _print_row(**kw):
    row = {
        "trade_id": "t1", "ticker": "KXMLBGAME-26AUG03X-A", "yes_price": 0.60,
        "no_price": 0.40, "count": 5.0, "created_time": "2026-08-03T12:00:00Z",
        "captured_at": "2026-08-04T09:00:00Z", "trade_day": "2026-08-03",
        "schema_version": "kalshi_trades.v1", "price_source_tag": "broker_truth",
        "capture_id": "C1", "raw_sha256": "abc", "event_ticker": None,
        "taker_book_side": "bid", "taker_outcome_side": "yes", "taker_side": "yes",
    }
    row.update(kw)
    return row


def _pr(ts, yes_price, side, count=1.0):
    return {"ts": ts, "yes_price": yes_price, "taker_book_side": side,
            "trade_id": f"x{ts}", "count": count}


# --------------------------------------------------------------------------- #
# percentiles
# --------------------------------------------------------------------------- #
def test_percentiles_on_empty_is_all_none_not_a_crash():
    assert Q._percentiles([]) == {k: None for k in ("p01", "p10", "p50", "p90", "p99", "max")}


def test_percentiles_are_monotone_and_end_at_the_max():
    vals = [float(i) for i in range(1, 101)]
    p = Q._percentiles(vals)
    assert p["p01"] <= p["p10"] <= p["p50"] <= p["p90"] <= p["p99"] <= p["max"]
    assert p["max"] == 100.0


# --------------------------------------------------------------------------- #
# 1. integrity detectors — each must FIRE on a planted defect
# --------------------------------------------------------------------------- #
def test_integrity_clean_rows_report_zero_defects():
    rows = [_print_row(trade_id="a"), _print_row(trade_id="b", created_time="2026-08-03T23:59:00Z")]
    r = Q.tape_integrity(rows)
    assert r["n_duplicate_trade_ids"] == 0
    assert r["n_price_identity_violations"] == 0
    assert r["n_sub_tick_prices"] == 0
    assert r["n_nonpositive_size"] == 0
    assert r["n_trade_day_mismatch"] == 0
    assert r["n_captured_before_created"] == 0
    assert r["n_parse_errors"] == 0


def test_integrity_detects_a_duplicate_trade_id():
    r = Q.tape_integrity([_print_row(trade_id="a"), _print_row(trade_id="a")])
    assert r["n_duplicate_trade_ids"] == 1
    assert r["n_distinct_trade_ids"] == 1


def test_integrity_detects_a_broken_yes_plus_no_book_identity():
    r = Q.tape_integrity([_print_row(yes_price=0.60, no_price=0.45)])
    assert r["n_price_identity_violations"] == 1


def test_integrity_detects_a_sub_tick_price():
    # Kalshi trades on a 1c grid; a 0.5c print would mean the field is not what we think.
    r = Q.tape_integrity([_print_row(yes_price=0.605, no_price=0.395)])
    assert r["n_sub_tick_prices"] == 1


def test_integrity_detects_nonpositive_and_fractional_sizes_separately():
    r = Q.tape_integrity([_print_row(trade_id="a", count=0.0),
                          _print_row(trade_id="b", count=-3),
                          _print_row(trade_id="c", count=2.5),
                          _print_row(trade_id="d", count=None),
                          _print_row(trade_id="e", count=7)])
    assert r["n_nonpositive_size"] == 3          # 0, -3 and the missing one
    assert r["n_fractional_size"] == 1           # 2.5 only; 7 is whole


def test_integrity_detects_a_trade_day_that_disagrees_with_created_time():
    r = Q.tape_integrity([_print_row(created_time="2026-08-04T00:10:00Z", trade_day="2026-08-03")])
    assert r["n_trade_day_mismatch"] == 1


def test_integrity_detects_capture_before_the_trade_existed():
    r = Q.tape_integrity([_print_row(created_time="2026-08-03T12:00:00Z",
                                     captured_at="2026-08-03T11:00:00Z")])
    assert r["n_captured_before_created"] == 1


def test_integrity_counts_parse_errors_rather_than_hiding_them():
    r = Q.tape_integrity([_print_row(), {"__parse_error__": True}])
    assert r["n_parse_errors"] == 1
    assert r["n_lines"] == 2


def test_integrity_flags_raw_sha256_that_is_not_a_per_line_hash():
    shared = [_print_row(trade_id="a", raw_sha256="same"), _print_row(trade_id="b", raw_sha256="same")]
    assert Q.tape_integrity(shared)["raw_sha256_is_per_line_hash"] is False
    distinct = [_print_row(trade_id="a", raw_sha256="h1"), _print_row(trade_id="b", raw_sha256="h2")]
    assert Q.tape_integrity(distinct)["raw_sha256_is_per_line_hash"] is True


def test_integrity_event_ticker_structural_nullity_is_not_asserted_when_one_is_present():
    rows = [_print_row(trade_id="a"), _print_row(trade_id="b", event_ticker="KXMLBGAME-26AUG03X")]
    assert Q.tape_integrity(rows)["event_ticker_is_structurally_null"] is False


# --------------------------------------------------------------------------- #
# 2. print-side join profile — the DUAL of milestone 1's interval coverage
# --------------------------------------------------------------------------- #
def _snaps(*ts):
    return [{"ts": float(t)} for t in ts]


def test_join_profile_buckets_partition_the_tape_exactly():
    prints = {"A": [_pr(50, 0.5, "bid"), _pr(150, 0.5, "bid"), _pr(5000, 0.5, "bid")],
              "B": [_pr(100, 0.5, "bid")]}
    snaps = {"A": _snaps(100, 200), "B": _snaps(100)}   # B has a single snapshot
    r = Q.print_join_profile(prints, snaps)
    assert r["n_prints"] == 4
    assert r["n_before_first_snapshot"] == 1
    assert r["n_inside_book_span"] == 1
    assert r["n_after_last_snapshot"] == 1
    assert r["n_ticker_has_under_two_snapshots"] == 1
    assert r["buckets_partition_the_tape"] is True


def test_join_profile_a_ticker_the_book_stopped_covering_is_named_not_dropped():
    prints = {"A": [_pr(10_000, 0.5, "bid"), _pr(20_000, 0.5, "bid")]}
    r = Q.print_join_profile(prints, {"A": _snaps(0, 100)})
    assert r["n_after_last_snapshot"] == 2
    assert r["worst_dropout_tickers"][0]["ticker"] == "A"
    assert r["worst_dropout_tickers"][0]["after_last"] == 2


def test_join_profile_freshness_ladder_measures_age_of_the_PRECEDING_snapshot():
    # snapshots at t=0 and t=3h; prints 10min and 2h after the first one
    prints = {"A": [_pr(600, 0.5, "bid"), _pr(7200, 0.5, "bid")]}
    r = Q.print_join_profile(prints, {"A": _snaps(0, 10_800)})
    assert r["freshness_ladder"]["within_15min"]["n"] == 1
    assert r["freshness_ladder"]["within_60min"]["n"] == 1
    assert r["freshness_ladder"]["within_180min"]["n"] == 2
    assert r["median_reference_quote_age_min"] == pytest.approx(65.0, abs=0.1)


def test_join_profile_on_empty_input_is_none_not_a_zero_division():
    r = Q.print_join_profile({}, {})
    assert r["n_prints"] == 0 and r["frac_inside_book_span"] is None


# --------------------------------------------------------------------------- #
# 3. book pass cadence
# --------------------------------------------------------------------------- #
def test_book_pass_profile_reports_the_largest_hole_and_where_it_starts(tmp_path, monkeypatch):
    day = "2026-01-01"
    p = tmp_path / f"dt={day}.jsonl"
    stamps = ["2026-01-01T00:00:00Z", "2026-01-01T03:00:00Z", "2026-01-01T06:00:00Z",
              "2026-01-01T15:00:00Z"]
    with open(p, "w", encoding="utf-8") as f:
        for s in stamps:
            for tk in ("A", "B"):        # two tickers per pass -> pass, not per-ticker, granularity
                f.write(json.dumps({"ticker": tk, "captured_at": s}) + "\n")
    monkeypatch.setattr(Q, "DEPTH_TAPE", tmp_path)
    r = Q.book_pass_profile([day])
    assert r["n_passes"] == 4                 # gaps: 180, 180, 540 minutes
    assert r["median_gap_min"] == 180.0
    assert r["max_gap_min"] == 540.0
    assert r["max_gap_starts_at"] == "2026-01-01T06:00Z"


def test_adjacent_days_brackets_the_day_and_crosses_a_month_boundary():
    assert Q.adjacent_days("2026-08-03") == ["2026-08-02", "2026-08-03", "2026-08-04"]
    assert Q.adjacent_days("2026-08-01") == ["2026-07-31", "2026-08-01", "2026-08-02"]


# --------------------------------------------------------------------------- #
# 4. capacity — orientation must match the fill predicate exactly (L279)
# --------------------------------------------------------------------------- #
def test_qualifying_size_for_a_resting_yes_bid_counts_only_SELLING_takers():
    prints = [_pr(10, 0.40, TAKER_SELLS, 3.0),    # qualifies: seller at/through 0.50
              _pr(20, 0.40, TAKER_BUYS, 99.0),    # wrong side -> ignored
              _pr(30, 0.55, TAKER_SELLS, 99.0)]   # above the rest price -> ignored
    total, first = Q.qualifying_size(prints, 0, 100, 0.50, "yes_bid")
    assert (total, first) == (3.0, 3.0)


def test_qualifying_size_for_a_resting_no_bid_counts_only_BUYING_takers():
    # a NO bid at 0.30 is a YES offer at 0.70; a BUYING taker at/above 0.70 lifts it
    prints = [_pr(10, 0.75, TAKER_BUYS, 4.0),
              _pr(20, 0.75, TAKER_SELLS, 99.0),
              _pr(30, 0.65, TAKER_BUYS, 99.0)]
    total, first = Q.qualifying_size(prints, 0, 100, 0.30, "no_bid")
    assert (total, first) == (4.0, 4.0)


def test_qualifying_size_window_is_half_open_and_sums_every_qualifying_print():
    prints = [_pr(0, 0.40, TAKER_SELLS, 100.0),    # at t0 -> excluded
              _pr(50, 0.40, TAKER_SELLS, 2.0),
              _pr(100, 0.40, TAKER_SELLS, 5.0),    # at t1 -> included
              _pr(101, 0.40, TAKER_SELLS, 100.0)]  # after t1 -> excluded
    total, first = Q.qualifying_size(prints, 0, 100, 0.50, "yes_bid")
    assert (total, first) == (7.0, 2.0)


def test_qualifying_size_unknown_side_qualifies_nothing():
    assert Q.qualifying_size([_pr(10, 0.4, TAKER_SELLS, 9.0)], 0, 100, 0.5, "yes_ask") == (0.0, None)


def test_fill_capacity_returns_none_when_the_milestone2_rows_are_absent(tmp_path):
    assert Q.fill_capacity({}, rows_path=tmp_path / "nope.jsonl") is None


def test_fill_capacity_curve_is_monotone_decreasing_in_order_size(tmp_path):
    rows = tmp_path / "rows.jsonl"
    with open(rows, "w", encoding="utf-8") as f:
        f.write(json.dumps({"filled": True, "ticker": "A", "side": "yes_bid", "rest_price": 0.5,
                            "entry_captured_at": "2026-08-03T00:00:00Z",
                            "next_captured_at": "2026-08-03T03:00:00Z"}) + "\n")
    t0 = Q.parse_ts("2026-08-03T00:00:00Z")
    prints = {"A": [_pr(t0 + 60, 0.40, TAKER_SELLS, 50.0)]}
    c = Q.fill_capacity(prints, rows_path=rows, sizes=(1.0, 10.0, 100.0))
    curve = c["capacity_curve"]
    assert c["n_traced"] == 1 and c["n_untraceable"] == 0
    vals = [curve[k]["frac_fillable_on_interval_total"] for k in ("1.0", "10.0", "100.0")]
    assert vals == [1.0, 1.0, 0.0]
    assert all(a >= b for a, b in zip(vals, vals[1:]))


# --------------------------------------------------------------------------- #
# 5/6. derived event key and the settlement gate
# --------------------------------------------------------------------------- #
def test_event_key_check_flags_a_derived_unit_that_disagrees_with_the_venue(tmp_path):
    p = tmp_path / "settlement.json"
    p.write_text(json.dumps({"markets": {
        "KXMLBGAME-26AUG03X-A": {"event_ticker": "KXMLBGAME-26AUG03X"},      # agrees
        "KXNBAGAME-26AUG03Y-B": {"event_ticker": "SOMETHING-ELSE"},          # disagrees
        "KXNHLGAME-26AUG03Z-C": {"event_ticker": None},                      # not checkable
    }}))
    r = Q.event_key_check(cache_path=p)
    assert r["checked"] == 2 and r["n_mismatches"] == 1
    assert r["mismatches"][0]["ticker"] == "KXNBAGAME-26AUG03Y-B"


def test_settlement_gate_schedule_is_cumulative_and_starts_from_the_already_settled(tmp_path):
    p = tmp_path / "settlement.json"
    p.write_text(json.dumps({"pulled_at": "2026-08-04T00:00:00Z", "markets": {
        "A": {"result": "yes", "close_time": "2026-08-01T00:00:00Z"},
        "B": {"result": "", "close_time": "2026-08-07T00:00:00Z"},
        "C": {"result": "", "close_time": "2026-08-07T12:00:00Z"},
        "D": {"result": "", "close_time": "2026-08-20T00:00:00Z"},
    }}))
    r = Q.settlement_gate(cache_path=p)
    assert r["n_already_settled"] == 1 and r["n_unsettled"] == 3
    assert r["last_close_day"] == "2026-08-20"
    assert [s["cumulative_resolvable"] for s in r["resolution_schedule"]] == [3, 4]


def test_settlement_gate_absent_cache_is_reported_not_faked(tmp_path):
    assert Q.settlement_gate(cache_path=tmp_path / "nope.json") == {"cache_present": False}


# --------------------------------------------------------------------------- #
# acceptance — committed tape
# --------------------------------------------------------------------------- #
DAY = "2026-08-03"


@pytest.fixture(scope="module")
def integrity():
    return Q.tape_integrity(Q.load_raw_prints(DAY), day=DAY)


def test_acceptance_trade_tape_is_internally_clean(integrity):
    """The frozen dt=2026-08-03 slice: exact, because the day is past and the collector
    dedupes on `trade_id`, so this file cannot legitimately change."""
    assert integrity["n_lines"] == 39698
    assert integrity["n_parse_errors"] == 0
    assert integrity["n_distinct_trade_ids"] == 39698
    assert integrity["n_duplicate_trade_ids"] == 0
    assert integrity["n_price_identity_violations"] == 0
    assert integrity["n_sub_tick_prices"] == 0
    assert integrity["n_nonpositive_size"] == 0
    assert integrity["n_trade_day_mismatch"] == 0
    assert integrity["n_captured_before_created"] == 0
    assert integrity["n_hours_covered"] == 24
    assert integrity["distinct_price_source_tags"] == ["broker_truth"]
    assert integrity["distinct_schema_versions"] == ["kalshi_trades.v1"]


def test_acceptance_event_ticker_is_structurally_null_on_this_family(integrity):
    """`/markets/trades` has no `event_ticker` field at all (verified live 2026-08-04 with one
    read-only public GET), so the column is null on every line. Any consumer needing the
    resample unit must DERIVE it from the ticker — see the next test."""
    assert integrity["n_event_ticker_null"] == integrity["n_lines"]
    assert integrity["event_ticker_is_structurally_null"] is True


def test_acceptance_raw_sha256_is_a_per_query_digest_not_a_per_line_hash(integrity):
    """42 distinct digests over 39,698 lines: it groups a ticker's pull, it does not verify a
    line. Pinned so nobody later treats it as line-level provenance."""
    assert integrity["raw_sha256_is_per_line_hash"] is False
    assert integrity["n_distinct_raw_sha256"] < integrity["n_lines"] / 100


def test_acceptance_over_half_of_executed_prints_are_fractional_size(integrity):
    """A fill-sim that assumes integer contract sizes is modelling a different venue."""
    assert integrity["frac_fractional_size"] > 0.5
    assert integrity["size_percentiles"]["p01"] < 1.0


def test_acceptance_the_derived_bootstrap_unit_matches_the_venue_event_key():
    r = Q.event_key_check()
    assert r["cache_present"] is True
    assert r["checked"] >= 60
    assert r["n_mismatches"] == 0


def test_acceptance_print_side_coverage_is_far_worse_than_book_side_coverage():
    """THE FINDING. Milestone 1 measured coverage book-side (65% of intervals hold a print)
    and it looked healthy. Print-side, most of the tape cannot be priced at all: the book
    collector stops covering a ticker long before it stops trading. Directional bounds only —
    the depth side of this join is not a frozen slice."""
    prints = Q.load_prints(DAY)
    same_day = Q.load_depth(DAY)[1]
    r = Q.print_join_profile(prints, same_day)
    assert r["buckets_partition_the_tape"] is True
    assert r["n_prints"] == 39698
    assert r["frac_inside_book_span"] < 0.35
    assert r["freshness_ladder"]["within_15min"]["frac"] < 0.05
    assert r["median_reference_quote_age_min"] > 60.0


def test_acceptance_the_depth_collector_missed_passes_on_the_audited_days():
    """The join's defect is BOOK-side. Two frozen past days, nominal 3h cadence, and a hole
    of at least 9 hours inside them."""
    r = Q.book_pass_profile(["2026-08-02", "2026-08-03"])
    assert r["median_gap_min"] == pytest.approx(180.0, abs=1.0)
    assert r["max_gap_min"] >= 540.0
