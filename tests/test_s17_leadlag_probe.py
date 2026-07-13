"""scripts.s17_leadlag_probe — pooled lead-lag cross-correlation over polymarket_macro_pairs.
Offline: synthetic in-memory records only, no filesystem tape dependency, no network.
Mirrors tests/test_s9_leadlag_probe.py coverage shape, adapted to the Fed-decision schema
(record keyed by kalshi.ticker; kalshi.yes_ask and polymarket.best_ask both real_ask)."""
from __future__ import annotations

import json

import pytest

from scripts import s17_leadlag_probe as probe


def _rec(capture_id, ticker, kalshi_ask, poly_ask, book_fetch_ok=True,
         meeting="2026-10", bucket="hike_25"):
    return {
        "schema_version": "polymarket_macro_pairs.v1",
        "capture_id": capture_id,
        "family": "fed_decision",
        "meeting": meeting,
        "bucket": bucket,
        "kalshi": {"ticker": ticker, "yes_ask": kalshi_ask, "price_source_tag": "real_ask"},
        "polymarket": {"best_ask": poly_ask, "book_fetch_ok": book_fetch_ok,
                       "price_source_tag": "real_ask"},
    }


# --------------------------------------------------------------------------- #
# pair_key
# --------------------------------------------------------------------------- #
def test_pair_key_prefers_ticker():
    assert probe.pair_key(_rec("c1", "KXFED-26OCT-H25", 0.1, 0.1)) == "KXFED-26OCT-H25"


def test_pair_key_falls_back_to_meeting_bucket_when_no_ticker():
    rec = {"capture_id": "c1", "meeting": "2026-10", "bucket": "cut_25",
           "kalshi": {"yes_ask": 0.1}, "polymarket": {"best_ask": 0.1}}
    assert probe.pair_key(rec) == "2026-10|cut_25"


def test_pair_key_none_when_unidentifiable():
    assert probe.pair_key({"capture_id": "c1", "kalshi": {}, "polymarket": {}}) is None


# --------------------------------------------------------------------------- #
# build_series
# --------------------------------------------------------------------------- #
def test_build_series_sorts_by_capture_and_groups_by_pair():
    records = [
        _rec("c2", "T1", 0.20, 0.21),
        _rec("c1", "T1", 0.19, 0.20),
        _rec("c1", "T2", 0.50, 0.51),
    ]
    series = probe.build_series(records)
    assert list(series.keys()) == ["T1", "T2"]
    assert series["T1"] == [("c1", 0.19, 0.20), ("c2", 0.20, 0.21)]
    assert series["T2"] == [("c1", 0.50, 0.51)]


def test_build_series_drops_failed_book_fetch():
    records = [_rec("c1", "T1", 0.19, 0.20, book_fetch_ok=False)]
    assert probe.build_series(records) == {}


def test_build_series_drops_incomplete_records():
    records = [{"capture_id": "c1", "kalshi": {"ticker": "T1"},
                "polymarket": {"book_fetch_ok": True}}]
    assert probe.build_series(records) == {}


def test_build_series_last_write_wins_on_duplicate_capture_id():
    records = [_rec("c1", "T1", 0.19, 0.20), _rec("c1", "T1", 0.22, 0.23)]
    series = probe.build_series(records)
    assert series["T1"] == [("c1", 0.22, 0.23)]


def test_build_series_all_book_fetch_false_is_empty():
    records = [_rec(f"c{i}", "T1", 0.1, 0.1, book_fetch_ok=False) for i in range(5)]
    assert probe.build_series(records) == {}


# --------------------------------------------------------------------------- #
# deltas / pearson
# --------------------------------------------------------------------------- #
def test_deltas_consecutive_steps():
    rows = [("c1", 0.10, 0.20), ("c2", 0.12, 0.19), ("c3", 0.12, 0.25)]
    dk, dp = zip(*probe.deltas(rows))
    assert list(dk) == pytest.approx([0.02, 0.0])
    assert list(dp) == pytest.approx([-0.01, 0.06])


def test_deltas_single_row_is_empty():
    assert probe.deltas([("c1", 0.10, 0.20)]) == []


def test_pearson_perfect_positive():
    assert probe.pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)


def test_pearson_perfect_negative():
    assert probe.pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)


def test_pearson_needs_at_least_two_points():
    assert probe.pearson([1.0], [2.0]) is None


def test_pearson_zero_variance_is_none():
    assert probe.pearson([1, 1, 1], [1, 2, 3]) is None


# --------------------------------------------------------------------------- #
# pooled_leadlag — synthetic controlled lead-lag relationship
# --------------------------------------------------------------------------- #
def test_pooled_leadlag_detects_kalshi_leading_polymarket():
    """polymarket's move at step t+1 always equals kalshi's move at step t (kalshi leads by
    exactly one capture); the pooled stat should pick up the correct lag direction."""
    kalshi_prices = [0.10, 0.12, 0.12, 0.15, 0.15, 0.20]
    poly_prices = [0.10, 0.10, 0.12, 0.12, 0.15, 0.15]  # polymarket = kalshi shifted +1 step
    rows = [(f"c{i}", k, p) for i, (k, p) in enumerate(zip(kalshi_prices, poly_prices))]
    series = {"T1": rows}

    result = probe.pooled_leadlag(series, min_captures=1)
    assert result["n_markets_used"] == 1
    assert result["rho_kalshi_leads_polymarket"] == pytest.approx(1.0)
    assert result["rho_polymarket_leads_kalshi"] < 1.0


def test_pooled_leadlag_respects_min_captures_floor():
    rows = [("c0", 0.10, 0.20), ("c1", 0.11, 0.21)]
    series = {"T1": rows}
    result = probe.pooled_leadlag(series, min_captures=10)
    assert result["n_markets_used"] == 0
    assert result["rho_contemporaneous"] is None


def test_pooled_leadlag_empty_series():
    result = probe.pooled_leadlag({}, min_captures=1)
    assert result["n_markets_used"] == 0
    assert result["n_steps_contemporaneous"] == 0


# --------------------------------------------------------------------------- #
# shock_events
# --------------------------------------------------------------------------- #
def test_shock_events_flags_moves_at_or_past_threshold():
    rows = [("c0", 0.10, 0.20), ("c1", 0.11, 0.20), ("c2", 0.12, 0.30)]
    series = {"T1": rows}
    events = probe.shock_events(series, threshold=0.05, min_captures=1)
    assert len(events) == 1
    assert events[0]["capture_id"] == "c2"
    assert events[0]["pair"] == "T1"
    assert events[0]["delta_polymarket"] == pytest.approx(0.10)


def test_shock_events_below_threshold_is_empty():
    rows = [("c0", 0.10, 0.20), ("c1", 0.11, 0.21)]
    events = probe.shock_events({"T1": rows}, threshold=0.05, min_captures=1)
    assert events == []


def test_shock_events_respects_min_captures():
    rows = [("c0", 0.10, 0.20), ("c1", 0.50, 0.20)]
    events = probe.shock_events({"T1": rows}, threshold=0.01, min_captures=10)
    assert events == []


# --------------------------------------------------------------------------- #
# market_membership_changes — the FOMC resolve/roll-off proxy
# --------------------------------------------------------------------------- #
def test_membership_changes_detects_added_and_removed():
    records = [
        _rec("c1", "T1", 0.1, 0.1),
        _rec("c1", "T2", 0.1, 0.1),
        _rec("c2", "T1", 0.1, 0.1),
        _rec("c2", "T3", 0.1, 0.1),
    ]
    changes = probe.market_membership_changes(records)
    assert changes == [{"capture_id": "c2", "added": ["T3"], "removed": ["T2"]}]


def test_membership_changes_no_change_is_empty():
    records = [_rec("c1", "T1", 0.1, 0.1), _rec("c2", "T1", 0.11, 0.11)]
    assert probe.market_membership_changes(records) == []


def test_membership_changes_single_capture_has_no_prior_to_compare():
    records = [_rec("c1", "T1", 0.1, 0.1)]
    assert probe.market_membership_changes(records) == []


# --------------------------------------------------------------------------- #
# build_report — end-to-end wiring, offline tape dir
# --------------------------------------------------------------------------- #
def test_build_report_reads_jsonl_files(tmp_path):
    tape_dir = tmp_path / "polymarket_macro_pairs"
    tape_dir.mkdir()
    lines = [_rec(f"c{i:02d}", "T1", 0.10 + 0.01 * i, 0.20 + 0.01 * i) for i in range(12)]
    (tape_dir / "dt=2026-07-06.jsonl").write_text(
        "\n".join(json.dumps(l) for l in lines) + "\n")

    report = probe.build_report(tape_dir, min_captures=10)
    assert report["n_records"] == 12
    assert report["n_distinct_captures"] == 12
    assert report["n_distinct_markets"] == 1
    assert report["n_markets_min_captures"] == 1
    assert report["leadlag"]["n_markets_used"] == 1
    assert report["membership_changes"] == []


def test_build_report_empty_tape_dir(tmp_path):
    tape_dir = tmp_path / "polymarket_macro_pairs"
    tape_dir.mkdir()
    report = probe.build_report(tape_dir, min_captures=10)
    assert report["n_records"] == 0
    assert report["n_distinct_captures"] == 0
    assert report["n_distinct_markets"] == 0
    assert report["leadlag"]["n_markets_used"] == 0
    assert report["shock_events"] == []
    assert report["membership_changes"] == []


# --------------------------------------------------------------------------- #
# count_cpi_tape — provenance-only, out-of-scope synthetic leg
# --------------------------------------------------------------------------- #
def test_count_cpi_tape_counts_records_and_tags_synthetic(tmp_path):
    cpi_dir = tmp_path / "polymarket_cpi_pairs"
    cpi_dir.mkdir()
    (cpi_dir / "dt=2026-07-06.jsonl").write_text('{"a":1}\n{"a":2}\n\n{"a":3}\n')
    out = probe.count_cpi_tape(cpi_dir)
    assert out["n_records"] == 3
    assert out["kalshi_price_source_tag"] == "synthetic"
    assert out["pooled"] is False


# --------------------------------------------------------------------------- #
# Burst-mode (Q19): parse_capture_time / window filter / cadence
# --------------------------------------------------------------------------- #
from datetime import datetime, timezone

from core.pricing import TAKER_FEE_RATE, fee_per_contract


def _brec(captured_at, ticker, *, yes_ask=None, yes_bid=None, best_ask=None, best_bid=None,
          book_fetch_ok=True, meeting="2026-07", bucket="hold"):
    return {
        "schema_version": "polymarket_macro_pairs.v1",
        "captured_at": captured_at,
        "capture_id": captured_at.replace("-", "").replace(":", "").split(".")[0],
        "family": "fed_decision",
        "meeting": meeting,
        "bucket": bucket,
        "kalshi": {"ticker": ticker, "yes_ask": yes_ask, "yes_bid": yes_bid,
                   "price_source_tag": "real_ask"},
        "polymarket": {"best_ask": best_ask, "best_bid": best_bid,
                       "book_fetch_ok": book_fetch_ok, "price_source_tag": "real_ask"},
    }


def test_parse_capture_time_prefers_captured_at():
    t = probe.parse_capture_time({"captured_at": "2026-07-14T12:05:03.5+00:00"})
    assert t == datetime(2026, 7, 14, 12, 5, 3, 500000, tzinfo=timezone.utc)


def test_parse_capture_time_falls_back_to_capture_id():
    t = probe.parse_capture_time({"capture_id": "20260714T120503Z"})
    assert t == datetime(2026, 7, 14, 12, 5, 3, tzinfo=timezone.utc)


def test_parse_capture_time_none_when_unparseable():
    assert probe.parse_capture_time({"capture_id": "not-a-time"}) is None
    assert probe.parse_capture_time({}) is None


def test_parse_window_bound_z_suffix():
    assert probe.parse_window_bound("2026-07-14T12:05:00Z") == \
        datetime(2026, 7, 14, 12, 5, 0, tzinfo=timezone.utc)


def test_filter_burst_window_inclusive():
    recs = [_brec("2026-07-14T12:00:00Z", "A"),
            _brec("2026-07-14T12:30:00Z", "A"),
            _brec("2026-07-14T14:00:00Z", "A")]
    start = probe.parse_window_bound("2026-07-14T12:00:00Z")
    end = probe.parse_window_bound("2026-07-14T13:00:00Z")
    out = probe.filter_burst_window(recs, start, end)
    assert len(out) == 2


def test_cadence_stats_flags_burst_vs_hourly():
    burst = [_brec(f"2026-07-14T12:{m:02d}:00Z", "A") for m in (0, 1, 2, 4)]
    stats = probe.cadence_stats(burst)
    assert stats["n_distinct_captures"] == 4
    assert stats["min_gap_s"] == 60.0
    assert stats["median_gap_s"] <= 120.0
    hourly = [_brec("2026-07-14T12:00:00Z", "A"), _brec("2026-07-14T13:00:00Z", "A")]
    assert probe.cadence_stats(hourly)["median_gap_s"] == 3600.0


def test_cadence_stats_empty():
    assert probe.cadence_stats([])["median_gap_s"] is None


# --------------------------------------------------------------------------- #
# build_burst_series
# --------------------------------------------------------------------------- #
def test_build_burst_series_keeps_four_quotes_and_dedupes():
    recs = [_brec("2026-07-14T12:00:00Z", "A", yes_ask=0.4, yes_bid=0.38,
                  best_ask=0.42, best_bid=0.40),
            # same capture instant, later line = last-write-wins
            _brec("2026-07-14T12:00:00Z", "A", yes_ask=0.41, yes_bid=0.39,
                  best_ask=0.43, best_bid=0.41)]
    series = probe.build_burst_series(recs)
    assert len(series["A"]) == 1
    _, q = series["A"][0]
    assert q["kalshi_yes_ask"] == 0.41 and q["poly_best_bid"] == 0.41


def test_build_burst_series_drops_book_fetch_failures():
    recs = [_brec("2026-07-14T12:00:00Z", "A", yes_ask=0.4, best_bid=0.5,
                  book_fetch_ok=False)]
    assert probe.build_burst_series(recs) == {}


# --------------------------------------------------------------------------- #
# per_ticker_leadlag — signed leader detection
# --------------------------------------------------------------------------- #
def test_per_ticker_leadlag_detects_kalshi_leader():
    # Polymarket's ask follows Kalshi's by exactly one capture step.
    kalshi = [0.50, 0.55, 0.55, 0.60, 0.60, 0.58, 0.58]
    poly = [0.50, 0.50, 0.55, 0.55, 0.60, 0.60, 0.58]
    recs = [_brec(f"2026-07-14T12:{m:02d}:00Z", "A", yes_ask=k, best_ask=p)
            for m, (k, p) in enumerate(zip(kalshi, poly))]
    series = probe.build_burst_series(recs)
    out = {t["pair"]: t for t in probe.per_ticker_leadlag(series)}
    assert out["A"]["signed_leader"] == "kalshi"
    assert out["A"]["rho_kalshi_leads"] > out["A"]["rho_polymarket_leads"]


def test_per_ticker_leadlag_skips_too_short():
    recs = [_brec(f"2026-07-14T12:{m:02d}:00Z", "A", yes_ask=0.5, best_ask=0.5)
            for m in range(3)]
    assert probe.per_ticker_leadlag(recs and probe.build_burst_series(recs)) == []


# --------------------------------------------------------------------------- #
# dislocation scan — fillable cross-venue edge net of both fees
# --------------------------------------------------------------------------- #
def test_dislocation_scan_flags_positive_edge_after_fees():
    # buy Kalshi yes_ask 0.40, sell Polymarket best_bid 0.50; kalshi taker fee ~0.02.
    q = {"kalshi_yes_ask": 0.40, "kalshi_yes_bid": 0.38,
         "poly_best_ask": 0.44, "poly_best_bid": 0.50}
    best = probe._best_dislocation(q, kalshi_fee_rate=TAKER_FEE_RATE, poly_fee=0.0)
    expected = 0.50 - 0.40 - fee_per_contract(0.40, TAKER_FEE_RATE)
    assert best["direction"] == "buy_kalshi_sell_poly"
    assert abs(best["net_edge"] - expected) < 1e-12
    assert best["net_edge"] > 0


def test_dislocation_scan_no_edge_on_aligned_books():
    recs = [_brec("2026-07-14T12:00:00Z", "A", yes_ask=0.50, yes_bid=0.48,
                  best_ask=0.52, best_bid=0.50)]
    series = probe.build_burst_series(recs)
    assert probe.dislocation_scan(series) == []


def test_dislocation_scan_poly_fee_can_kill_edge():
    q = {"kalshi_yes_ask": 0.40, "kalshi_yes_bid": 0.38,
         "poly_best_ask": 0.44, "poly_best_bid": 0.50}
    # a large assumed poly fee wipes the 0.08 edge
    best = probe._best_dislocation(q, kalshi_fee_rate=TAKER_FEE_RATE, poly_fee=0.20)
    assert best["net_edge"] < 0


def test_dislocation_missing_legs_returns_none():
    assert probe._best_dislocation({"kalshi_yes_ask": None, "kalshi_yes_bid": None,
                                    "poly_best_ask": None, "poly_best_bid": None},
                                   kalshi_fee_rate=TAKER_FEE_RATE, poly_fee=0.0) is None


# --------------------------------------------------------------------------- #
# dislocation episodes — width x duration of contiguous runs
# --------------------------------------------------------------------------- #
def test_dislocation_episodes_groups_contiguous_runs():
    # two consecutive positive captures then one aligned (no edge) closes the episode
    recs = [
        _brec("2026-07-14T12:00:00Z", "A", yes_ask=0.40, best_bid=0.50, best_ask=0.44, yes_bid=0.38),
        _brec("2026-07-14T12:01:00Z", "A", yes_ask=0.41, best_bid=0.51, best_ask=0.45, yes_bid=0.39),
        _brec("2026-07-14T12:02:00Z", "A", yes_ask=0.50, best_bid=0.50, best_ask=0.52, yes_bid=0.48),
    ]
    series = probe.build_burst_series(recs)
    eps = probe.dislocation_episodes(series)
    assert len(eps) == 1
    ep = eps[0]
    assert ep["n_captures"] == 2
    assert ep["duration_s"] == 60.0
    assert ep["direction"] == "buy_kalshi_sell_poly"
    assert ep["max_net_edge"] >= ep["mean_net_edge"]


# --------------------------------------------------------------------------- #
# build_burst_report smoke — fee model tagging + shape
# --------------------------------------------------------------------------- #
def test_build_burst_report_shape_and_fee_tag():
    recs = [_brec(f"2026-07-14T12:{m:02d}:00Z", "A", yes_ask=0.40, best_bid=0.50,
                  best_ask=0.44, yes_bid=0.38) for m in range(3)]
    start = probe.parse_window_bound("2026-07-14T12:00:00Z")
    end = probe.parse_window_bound("2026-07-14T13:00:00Z")
    report = probe.build_burst_report(recs, start=start, end=end, poly_fee=0.0)
    assert report["mode"] == "burst"
    assert report["n_records_in_window"] == 3
    assert report["fee_model"]["poly_fee_source"] == "assumed_zero_polymarket_clob"
    assert report["fee_model"]["kalshi_rate"] == TAKER_FEE_RATE
    assert report["n_dislocations"] == 3
