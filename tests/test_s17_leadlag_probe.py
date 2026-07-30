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


def test_build_report_pools_v1_and_v2_records(tmp_path):
    """L214 bumped the collector's pair schema to `polymarket_macro_pairs.v2` (v1 + per-leg
    resolution provenance). This probe filters STRUCTURALLY on the fields it needs, never on the
    schema string, so both versions load unchanged into one series — asserted rather than
    assumed, since a mixed-version tape is now the permanent steady state."""
    tape_dir = tmp_path / "polymarket_macro_pairs"
    tape_dir.mkdir()
    lines = []
    for i in range(12):
        rec = _rec(f"c{i:02d}", "T1", 0.10 + 0.01 * i, 0.20 + 0.01 * i)
        if i >= 6:
            rec["schema_version"] = "polymarket_macro_pairs.v2"
            rec["kalshi"]["title"] = "Will the Federal Reserve Hike rates by 25bps at their October 2026 meeting?"
            rec["kalshi"]["resolution_basis"] = "kalshi_rulebook"
            rec["polymarket"]["group_item_title"] = "25 bps increase"
            rec["polymarket"]["resolution_basis"] = "uma_oracle"
            rec["bucket_terms"] = {"kalshi_basis": "hike_25bps",
                                   "polymarket_basis": "increase_25bps",
                                   "terms_equivalent": True, "note": None}
        lines.append(rec)
    (tape_dir / "dt=2026-07-06.jsonl").write_text(
        "\n".join(json.dumps(l) for l in lines) + "\n")

    report = probe.build_report(tape_dir, min_captures=10)
    assert report["n_records"] == 12
    assert report["n_distinct_markets"] == 1
    assert report["leadlag"]["n_markets_used"] == 1


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


def test_parse_capture_time_z_suffix_with_short_fraction():
    # kb/lessons L136 live symptom shape: trailing-zero-stripped fractional seconds
    # with a 'Z' suffix — Python 3.9's fromisoformat rejects this combination outright.
    t = probe.parse_capture_time({"captured_at": "2026-07-07T00:57:04.7Z"})
    assert t == datetime(2026, 7, 7, 0, 57, 4, 700000, tzinfo=timezone.utc)


def test_parse_window_bound_z_suffix():
    assert probe.parse_window_bound("2026-07-14T12:05:00Z") == \
        datetime(2026, 7, 14, 12, 5, 0, tzinfo=timezone.utc)


def test_parse_window_bound_short_fraction():
    assert probe.parse_window_bound("2026-07-14T12:05:00.5Z") == \
        datetime(2026, 7, 14, 12, 5, 0, 500000, tzinfo=timezone.utc)


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
# A2c — SIGN PRECONDITION on the signed-leader argmax (L235).
#
# Pre-fix, leader selection was a pure argmax over a SIGNED statistic subject to a `margin`
# DIFFERENCE, so with BOTH lag-rho negative it crowned the LESS NEGATIVE direction. The real
# row: `KXFEDDECISION-26SEP-H0` got leader=polymarket on rho = -0.0045 over Kalshi's -0.2536.
# L229's magnitude floor rejected that row only INCIDENTALLY (|-0.0045| < 0.05); the verifier's
# counterexample (-0.30 / -0.20) clears the floor by 6x and would have been labelled `stable`.
# The rule now lives in `scripts/s9_leadlag_probe.py::signed_leader_label`, shared by both
# burst probes so the twin cannot drift.
# --------------------------------------------------------------------------- #
def test_signed_leader_label_refuses_a_leader_when_both_directions_are_negative():
    """POSITIVE CONTROL — the verifier's exact counterexample. Pre-fix this returned
    'polymarket' (because -0.20 > -0.30 + 0.05 as a signed comparison)."""
    assert probe.signed_leader_label(-0.30, -0.20,
                                     margin=probe.LEADLAG_SIGNED_LEADER_MARGIN) == "none"
    # symmetric: the less-negative side being Kalshi's is refused identically
    assert probe.signed_leader_label(-0.20, -0.30,
                                     margin=probe.LEADLAG_SIGNED_LEADER_MARGIN) == "none"


def test_signed_leader_label_pins_the_historical_26sep_h0_row():
    """The REAL executed values from the 2026-07-29 FOMC run (n=21 steps): rho_k = -0.2536,
    rho_p = -0.0045. The run recorded leader=polymarket; the sign gate must now say 'none',
    and it must do so on the SIGN, not on the magnitude floor (which lives one stage later, in
    `leadlag_stability`, and never sees this row again once no leader is named)."""
    assert probe.signed_leader_label(-0.25358737015281874, -0.004471504399603508,
                                     margin=probe.LEADLAG_SIGNED_LEADER_MARGIN) == "none"


def test_sign_precondition_and_magnitude_floor_are_independent_gates():
    """THE LOAD-BEARING POINT OF L235. The counterexample passes the magnitude gate outright —
    |-0.30| is six times `LEADLAG_RHO_MAGNITUDE_FLOOR` — and is killed by the sign gate ALONE.
    Neither gate implies the other: magnitude asks 'is this rho big enough to be signal?',
    sign asks 'does it point the way a lead claim requires?'."""
    rho_k, rho_p = -0.30, -0.20
    assert abs(rho_k) > probe.LEADLAG_RHO_MAGNITUDE_FLOOR
    assert abs(rho_p) > probe.LEADLAG_RHO_MAGNITUDE_FLOOR
    assert abs(rho_p - rho_k) > probe.LEADLAG_SIGNED_LEADER_MARGIN   # clears the margin too
    assert probe.signed_leader_label(rho_k, rho_p,
                                     margin=probe.LEADLAG_SIGNED_LEADER_MARGIN) == "none"
    # and the converse direction of independence: a rho can pass SIGN and fail MAGNITUDE.
    assert probe.signed_leader_label(0.03, -0.30,
                                     margin=probe.LEADLAG_SIGNED_LEADER_MARGIN) == "kalshi"
    assert abs(0.03) < probe.LEADLAG_RHO_MAGNITUDE_FLOOR


def test_signed_leader_label_negative_controls_unchanged():
    """MUST NOT FIRE — pre-existing behaviour is preserved everywhere the winning direction's
    rho is positive, and for the None / within-margin cases."""
    m = probe.LEADLAG_SIGNED_LEADER_MARGIN
    assert probe.signed_leader_label(0.30, 0.20, margin=m) == "kalshi"      # genuine lead
    assert probe.signed_leader_label(0.20, 0.30, margin=m) == "polymarket"  # genuine lead
    assert probe.signed_leader_label(0.30, -0.20, margin=m) == "kalshi"     # mixed sign
    assert probe.signed_leader_label(-0.20, 0.30, margin=m) == "polymarket"  # mixed sign
    assert probe.signed_leader_label(0.30, 0.29, margin=m) == "none"        # within margin
    assert probe.signed_leader_label(None, 0.30, margin=m) is None
    assert probe.signed_leader_label(0.30, None, margin=m) is None
    assert probe.signed_leader_label(None, None, margin=m) is None


def test_per_ticker_leadlag_names_no_leader_when_both_lag_rho_are_negative():
    """END-TO-END through `per_ticker_leadlag` on constructed tape that genuinely produces two
    NEGATIVE lag-rho of the counterexample's shape. The observed rho are asserted too, so the
    fixture cannot silently drift into a different regime and stop testing the sign gate."""
    kalshi = [0.50, 0.50, 0.51, 0.50, 0.48, 0.50, 0.52, 0.53]
    poly = [0.50, 0.50, 0.51, 0.52, 0.53, 0.54, 0.52, 0.54]
    recs = [_brec(f"2026-07-29T17:{2 * i:02d}:00Z", "A", yes_ask=k, best_ask=p)
            for i, (k, p) in enumerate(zip(kalshi, poly))]
    out = {t["pair"]: t for t in probe.per_ticker_leadlag(probe.build_burst_series(recs))}["A"]
    # the fixture really is the both-negative regime, near the -0.30 / -0.20 counterexample
    assert out["rho_kalshi_leads"] == pytest.approx(-0.2988, abs=1e-3)
    assert out["rho_polymarket_leads"] == pytest.approx(-0.2010, abs=1e-3)
    assert out["rho_kalshi_leads"] < 0 and out["rho_polymarket_leads"] < 0
    # ...and the less-negative direction beats the other by MORE than the margin, i.e. the
    # pre-fix argmax fired here and returned 'polymarket'.
    assert out["rho_polymarket_leads"] > out["rho_kalshi_leads"] + \
        probe.LEADLAG_SIGNED_LEADER_MARGIN
    assert out["signed_leader"] == "none"
    # schema unchanged: no new keys, same vocabulary, and the row still carries both rho so a
    # reader can audit WHY it is 'none'.
    assert set(out) == {"pair", "n_steps", "rho_contemporaneous", "rho_kalshi_leads",
                        "rho_polymarket_leads", "signed_leader"}


def test_leadlag_stability_maps_a_sign_gated_none_to_no_directional_claim():
    """Downstream consumer check: with no leader named, `leadlag_stability` makes no claim (and
    never reaches the magnitude/retention gates), which is the whole point of the earlier gate."""
    out = probe.leadlag_stability([{"pair": "A", "signed_leader": "none"}], [])[0]
    assert out["stability"] == "no_directional_claim"
    assert out["rho_full"] is None and out["retention"] is None


# --------------------------------------------------------------------------- #
# dislocation scan — fillable cross-venue edge net of both fees
# --------------------------------------------------------------------------- #
def test_dislocation_scan_flags_positive_edge_after_fees():
    # buy Kalshi yes_ask 0.40, sell Polymarket best_bid 0.50; kalshi taker fee ~0.02.
    q = {"kalshi_yes_ask": 0.40, "kalshi_yes_bid": 0.38,
         "poly_best_ask": 0.44, "poly_best_bid": 0.50}
    best = probe._best_dislocation(q, kalshi_fee_rate=TAKER_FEE_RATE,
                                   poly_fee_model=probe.PolyFeeModel("free"))
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
    # a large assumed flat poly fee wipes the 0.08 edge
    best = probe._best_dislocation(
        q, kalshi_fee_rate=TAKER_FEE_RATE,
        poly_fee_model=probe.PolyFeeModel("flat", flat_fee=0.20))
    assert best["net_edge"] < 0


def test_dislocation_missing_legs_returns_none():
    assert probe._best_dislocation({"kalshi_yes_ask": None, "kalshi_yes_bid": None,
                                    "poly_best_ask": None, "poly_best_bid": None},
                                   kalshi_fee_rate=TAKER_FEE_RATE,
                                   poly_fee_model=probe.PolyFeeModel("free")) is None


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
    report = probe.build_burst_report(recs, start=start, end=end,
                                      poly_fee_model=probe.PolyFeeModel("free"))
    assert report["mode"] == "burst"
    assert report["n_records_in_window"] == 3
    assert report["fee_model"]["poly_fee_source"] == "assumed_zero_polymarket_clob"
    assert report["fee_model"]["kalshi_rate"] == TAKER_FEE_RATE
    assert report["n_dislocations"] == 3


# =========================================================================== #
# Q19 FOMC leg (2026-07-29) — A1 honest Polymarket fee model, A2 L57 leave-one-out
# in burst mode, A3 release-instant coverage (L164), A4 per-capture membership +
# L32 frozen-quote fractions. All offline: synthetic in-memory records only.
# =========================================================================== #
from core.pricing import POLYMARKET_US_TAKER_RATE, polymarket_fee_per_contract


# --------------------------------------------------------------------------- #
# A1 — PolyFeeModel
# --------------------------------------------------------------------------- #
def test_poly_fee_model_schedule_charges_the_real_schedule_not_a_flat_rate():
    """REGRESSION PIN for the fee bug this leg fixed. Polymarket's Fee Structure V2 is
    rate*p*(1-p) with NO cent round-up, so at p=0.50 the US taker rate charges $0.0125 per
    contract — NOT the flat $0.05 a naive reading of the rate would charge (a ~4x
    over-charge, the L5 maker/taker mistake in mirror image)."""
    model = probe.PolyFeeModel("schedule")
    assert model.rate == POLYMARKET_US_TAKER_RATE
    assert model.fee(0.50) == pytest.approx(0.0125)
    assert model.fee(0.50) != pytest.approx(POLYMARKET_US_TAKER_RATE)
    # and it is the core helper, not a re-derivation
    assert model.fee(0.37) == pytest.approx(
        polymarket_fee_per_contract(0.37, POLYMARKET_US_TAKER_RATE))


def test_poly_fee_model_schedule_shrinks_toward_the_wings():
    """The p*(1-p) shape means a deep wing leg is charged almost nothing — the reason a flat
    constant is wrong at BOTH ends of the ladder, not just in the middle."""
    model = probe.PolyFeeModel("schedule")
    assert model.fee(0.009) < model.fee(0.25) < model.fee(0.50)


def test_poly_fee_model_flat_preserves_legacy_constant_behaviour():
    model = probe.PolyFeeModel("flat", flat_fee=0.05)
    assert model.fee(0.50) == pytest.approx(0.05)
    assert model.fee(0.01) == pytest.approx(0.05)   # flat: price-independent, i.e. wrong
    assert model.source == "explicit_cli_flat"
    assert model.as_dict()["poly_fee_per_contract_flat"] == pytest.approx(0.05)
    assert model.as_dict()["poly_fee_rate"] is None


def test_poly_fee_model_free_is_identically_zero_and_tagged_as_an_assumption():
    model = probe.PolyFeeModel("free")
    assert model.fee(0.50) == 0.0
    assert model.fee(0.01) == 0.0
    assert model.source == "assumed_zero_polymarket_clob"
    assert model.as_dict()["poly_fee_rate"] is None
    assert model.as_dict()["poly_fee_per_contract_flat"] is None


def test_poly_fee_model_flat_zero_is_tagged_as_the_zero_assumption():
    """A flat 0.0 is economically the `free` model however it was spelled, so it carries the
    honest `assumed_zero_polymarket_clob` tag rather than implying a real quoted fee."""
    assert probe.PolyFeeModel("flat", flat_fee=0.0).source == "assumed_zero_polymarket_clob"


def test_poly_fee_model_schedule_names_the_core_helper_as_its_source():
    assert probe.PolyFeeModel("schedule").source == "core.pricing.polymarket_fee_per_contract"


def test_poly_fee_model_rejects_an_unknown_model():
    with pytest.raises(ValueError):
        probe.PolyFeeModel("handrolled")


def test_default_poly_fee_model_is_the_schedule():
    assert probe.DEFAULT_POLY_FEE_MODEL == "schedule"
    assert probe.dislocation_scan({}) == []  # default construction path must not raise


def test_dislocation_row_records_the_fees_actually_charged():
    q = {"kalshi_yes_ask": 0.40, "kalshi_yes_bid": 0.38,
         "poly_best_ask": 0.44, "poly_best_bid": 0.50}
    best = probe._best_dislocation(q, kalshi_fee_rate=TAKER_FEE_RATE,
                                  poly_fee_model=probe.PolyFeeModel("schedule"))
    assert best["poly_fee_model"] == "schedule"
    assert best["kalshi_leg_price"] == pytest.approx(0.40)
    assert best["poly_leg_price"] == pytest.approx(0.50)
    assert best["kalshi_fee_charged"] == pytest.approx(fee_per_contract(0.40, TAKER_FEE_RATE))
    assert best["poly_fee_charged"] == pytest.approx(0.0125)
    assert best["net_edge"] == pytest.approx(
        0.50 - 0.40 - best["kalshi_fee_charged"] - best["poly_fee_charged"])


def test_three_fee_models_bracket_the_same_marginal_dislocation():
    """The FOMC-window shape that made this bug EV-relevant in both directions: a 3c
    Kalshi-bid-over-Polymarket-ask gap. `free` calls it a 1c edge, `schedule` shaves it below
    zero, a flat 0.05 buries it. One tape, three answers — only `schedule` is honest."""
    q = {"kalshi_yes_ask": 0.60, "kalshi_yes_bid": 0.58,
         "poly_best_ask": 0.55, "poly_best_bid": 0.54}
    kw = dict(kalshi_fee_rate=TAKER_FEE_RATE)
    free = probe._best_dislocation(q, poly_fee_model=probe.PolyFeeModel("free"), **kw)
    sched = probe._best_dislocation(q, poly_fee_model=probe.PolyFeeModel("schedule"), **kw)
    flat = probe._best_dislocation(
        q, poly_fee_model=probe.PolyFeeModel("flat", flat_fee=0.05), **kw)
    assert free["direction"] == sched["direction"] == "buy_poly_sell_kalshi"
    assert free["net_edge"] == pytest.approx(0.01)
    assert sched["net_edge"] == pytest.approx(
        0.01 - polymarket_fee_per_contract(0.55, POLYMARKET_US_TAKER_RATE))
    assert sched["net_edge"] < 0.0                 # the real schedule KILLS this one
    assert flat["net_edge"] < sched["net_edge"]    # the flat constant buries it far deeper


def test_dislocation_scan_hit_count_depends_on_the_fee_model():
    recs = [_brec(f"2026-07-29T17:{m:02d}:00Z", "A", yes_ask=0.60, yes_bid=0.58,
                  best_ask=0.55, best_bid=0.54) for m in (41, 43, 45)]
    series = probe.build_burst_series(recs)
    assert len(probe.dislocation_scan(
        series, poly_fee_model=probe.PolyFeeModel("free"))) == 3
    assert probe.dislocation_scan(
        series, poly_fee_model=probe.PolyFeeModel("schedule")) == []
    assert probe.dislocation_scan(
        series, poly_fee_model=probe.PolyFeeModel("flat", flat_fee=0.05)) == []


# --------------------------------------------------------------------------- #
# A1 — CLI wiring
# --------------------------------------------------------------------------- #
def _write_burst_tape(tmp_path, records):
    tape_dir = tmp_path / "polymarket_macro_pairs"
    tape_dir.mkdir()
    (tape_dir / "dt=2026-07-29.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records))
    return tape_dir


_FOMC_WINDOW = ["--burst-window", "2026-07-29T17:40:00Z", "2026-07-29T19:35:00Z"]


def test_cli_defaults_to_the_schedule_fee_model(tmp_path):
    recs = [_brec(f"2026-07-29T17:{m:02d}:00Z", "A", yes_ask=0.60, yes_bid=0.58,
                  best_ask=0.55, best_bid=0.54) for m in (41, 43, 45)]
    tape_dir = _write_burst_tape(tmp_path, recs)
    out = tmp_path / "r.json"
    rc = probe.main(["--tape-dir", str(tape_dir), *_FOMC_WINDOW, "--json-out", str(out)])
    assert rc == 0
    report = json.loads(out.read_text())
    assert report["fee_model"]["poly_fee_model"] == "schedule"
    assert report["fee_model"]["poly_fee_source"] == "core.pricing.polymarket_fee_per_contract"
    assert report["fee_model"]["poly_fee_rate"] == pytest.approx(POLYMARKET_US_TAKER_RATE)
    assert report["n_dislocations"] == 0


def test_cli_flat_model_preserves_the_legacy_poly_fee_flag(tmp_path):
    recs = [_brec(f"2026-07-29T17:{m:02d}:00Z", "A", yes_ask=0.60, yes_bid=0.58,
                  best_ask=0.55, best_bid=0.54) for m in (41, 43, 45)]
    tape_dir = _write_burst_tape(tmp_path, recs)
    out = tmp_path / "r.json"
    assert probe.main(["--tape-dir", str(tape_dir), *_FOMC_WINDOW,
                       "--poly-fee-model", "flat", "--poly-fee", "0.05",
                       "--json-out", str(out)]) == 0
    report = json.loads(out.read_text())
    assert report["fee_model"]["poly_fee_model"] == "flat"
    assert report["fee_model"]["poly_fee_per_contract_flat"] == pytest.approx(0.05)
    assert report["fee_model"]["poly_fee_source"] == "explicit_cli_flat"


def test_cli_refuses_a_flat_poly_fee_under_a_non_flat_model(tmp_path):
    """A silently-ignored fee flag is exactly how the flat-fee bug hid. Refuse instead."""
    tape_dir = _write_burst_tape(tmp_path, [])
    with pytest.raises(SystemExit):
        probe.main(["--tape-dir", str(tape_dir), *_FOMC_WINDOW, "--poly-fee", "0.05"])


def test_cli_free_model_is_reachable_as_the_generous_sensitivity(tmp_path):
    recs = [_brec(f"2026-07-29T17:{m:02d}:00Z", "A", yes_ask=0.60, yes_bid=0.58,
                  best_ask=0.55, best_bid=0.54) for m in (41, 43, 45)]
    tape_dir = _write_burst_tape(tmp_path, recs)
    out = tmp_path / "r.json"
    assert probe.main(["--tape-dir", str(tape_dir), *_FOMC_WINDOW,
                       "--poly-fee-model", "free", "--json-out", str(out)]) == 0
    report = json.loads(out.read_text())
    assert report["fee_model"]["poly_fee_source"] == "assumed_zero_polymarket_clob"
    assert report["n_dislocations"] == 3


# --------------------------------------------------------------------------- #
# A2 — L57 leave-one-out stability gate in burst mode
# --------------------------------------------------------------------------- #
def test_leadlag_stability_flags_a_collapsing_loo_as_unstable():
    per_ticker = [{"pair": "A", "signed_leader": "polymarket"}]
    loo = [{"pair": "A", "rho_polymarket_leads_full": 0.902,
            "rho_polymarket_leads_drop_top_pair": 0.196}]   # the literal CPI-leg collapse
    out = probe.leadlag_stability(per_ticker, loo)[0]
    assert out["stability"] == "UNSTABLE_collapsed"
    assert out["retention"] == pytest.approx(0.196 / 0.902)


def test_leadlag_stability_flags_a_sign_flip_as_unstable():
    per_ticker = [{"pair": "A", "signed_leader": "kalshi"}]
    loo = [{"pair": "A", "rho_kalshi_leads_full": 0.40,
            "rho_kalshi_leads_drop_top_pair": -0.35}]
    assert probe.leadlag_stability(per_ticker, loo)[0]["stability"] == "UNSTABLE_sign_flip"


def test_leadlag_stability_accepts_a_lead_that_survives_its_own_loo():
    per_ticker = [{"pair": "A", "signed_leader": "kalshi"}]
    loo = [{"pair": "A", "rho_kalshi_leads_full": 0.80,
            "rho_kalshi_leads_drop_top_pair": 0.74}]
    out = probe.leadlag_stability(per_ticker, loo)[0]
    assert out["stability"] == "stable"
    assert out["retention"] > probe.LEADLAG_LOO_RETENTION_FLOOR


def test_leadlag_stability_no_claim_when_there_is_no_signed_leader():
    for leader in (None, "none"):
        out = probe.leadlag_stability([{"pair": "A", "signed_leader": leader}], [])[0]
        assert out["stability"] == "no_directional_claim"
        assert out["rho_full"] is None


def test_leadlag_stability_unrecomputable_when_the_loo_row_is_missing():
    out = probe.leadlag_stability([{"pair": "A", "signed_leader": "kalshi"}], [])[0]
    assert out["stability"] == "UNSTABLE_unrecomputable"


def test_leadlag_stability_zero_rho_lead_is_not_a_claim():
    """An exactly-zero rho_full has no magnitude to retain and the retention ratio is not even
    defined, so it is caught by the magnitude floor (0.0 < floor) rather than by the retention
    gate. Both labels carry the UNSTABLE prefix, so no consumer sees a behaviour change."""
    per_ticker = [{"pair": "A", "signed_leader": "polymarket"}]
    loo = [{"pair": "A", "rho_polymarket_leads_full": 0.0,
            "rho_polymarket_leads_drop_top_pair": 0.0}]
    out = probe.leadlag_stability(per_ticker, loo)[0]
    assert out["stability"] == "UNSTABLE_below_magnitude_floor"
    assert out["stability"].startswith("UNSTABLE")
    assert out["retention"] is None


# --------------------------------------------------------------------------- #
# A2b — |rho| MAGNITUDE FLOOR (L27's magnitude gate applied to a correlation).
#
# Defect found in round-2 review of the executed 2026-07-29 FOMC run: `leadlag_stability` called
# a noise-level rho `stable` because the leave-one-out recompute moved it AWAY from zero, so the
# retention RATIO was large against a near-zero denominator. The printed summary then read
# "1 of 6 leads survives leave-one-out", which reads as a real surviving lead.
# --------------------------------------------------------------------------- #
def test_leadlag_rho_magnitude_floor_is_named_and_tied_to_the_signed_leader_margin():
    assert probe.LEADLAG_RHO_MAGNITUDE_FLOOR == pytest.approx(0.05)
    # The floor is DERIVED from the module's own directional margin, not tuned to any dataset:
    # demanding a 0.05 DIFFERENCE to name a leader while accepting a smaller ABSOLUTE magnitude
    # as a stable lead would be incoherent.
    assert probe.LEADLAG_RHO_MAGNITUDE_FLOOR == probe.LEADLAG_SIGNED_LEADER_MARGIN


def test_leadlag_stability_noise_level_rho_is_not_stable_regression_26sep_h0():
    """REGRESSION PIN with the REAL executed values from the 2026-07-29 FOMC run
    (`KXFEDDECISION-26SEP-H0`, leader=polymarket over n=21 steps): rho_full = -0.0044715...,
    i.e. |rho| = 0.0045 — pure noise — and the LOO recompute at -0.0409 moved FURTHER from zero,
    giving retention = 9.14. The pre-fix code labelled this `stable` and the summary line credited
    it as the 1 of 6 leads that survived leave-one-out. It must be UNSTABLE."""
    per_ticker = [{"pair": "KXFEDDECISION-26SEP-H0", "signed_leader": "polymarket"}]
    loo = [{"pair": "KXFEDDECISION-26SEP-H0",
            "rho_polymarket_leads_full": -0.004471504399603508,
            "rho_polymarket_leads_drop_top_pair": -0.040873388781476276}]
    out = probe.leadlag_stability(per_ticker, loo)[0]
    assert out["stability"] == "UNSTABLE_below_magnitude_floor"
    assert out["stability"].startswith("UNSTABLE")     # printer/consumers treat it as no-lead
    # the inflated ratio is RECORDED, not hidden — that is the tell a reader needs
    assert out["retention"] == pytest.approx(9.140858451375014)
    assert out["retention"] > probe.LEADLAG_LOO_RETENTION_FLOOR   # it "passed" the old gate
    assert abs(out["rho_full"]) < probe.LEADLAG_RHO_MAGNITUDE_FLOOR
    assert out["magnitude_floor"] == probe.LEADLAG_RHO_MAGNITUDE_FLOOR


def test_leadlag_stability_magnitude_floor_is_checked_before_sign_and_retention():
    """A below-floor rho is labelled by MAGNITUDE even when it would otherwise have been a sign
    flip — the magnitude gate decides whether sign/retention are measuring anything at all."""
    per_ticker = [{"pair": "A", "signed_leader": "kalshi"}]
    loo = [{"pair": "A", "rho_kalshi_leads_full": 0.004,
            "rho_kalshi_leads_drop_top_pair": -0.9}]
    assert probe.leadlag_stability(per_ticker, loo)[0]["stability"] == \
        "UNSTABLE_below_magnitude_floor"


def test_leadlag_stability_just_above_the_floor_still_reaches_the_retention_gate():
    """The floor gates, it does not swallow: a rho above it is still judged on its LOO. Uses the
    real 26SEP-H26 executed values (rho_full 0.0636, LOO 0.0157) — above the floor, killed by
    retention 0.246, exactly as the executed run reported."""
    per_ticker = [{"pair": "A", "signed_leader": "kalshi"}]
    loo = [{"pair": "A", "rho_kalshi_leads_full": 0.06362847629757783,
            "rho_kalshi_leads_drop_top_pair": 0.01568060856995576}]
    out = probe.leadlag_stability(per_ticker, loo)[0]
    assert out["stability"] == "UNSTABLE_collapsed"
    assert out["retention"] == pytest.approx(0.24644010798908098)


def test_leadlag_stability_magnitude_floor_is_overridable_for_a_sensitivity():
    """The floor is a keyword, so a verifier can re-run at a stricter bar without editing code.
    At a significance-scale floor (~1.96/sqrt(21)) even the 26SEP-C25 rho of 0.396 goes below."""
    per_ticker = [{"pair": "A", "signed_leader": "polymarket"}]
    loo = [{"pair": "A", "rho_polymarket_leads_full": 0.39640461849306996,
            "rho_polymarket_leads_drop_top_pair": 0.06390598265111037}]
    assert probe.leadlag_stability(per_ticker, loo, magnitude_floor=0.43)[0]["stability"] == \
        "UNSTABLE_below_magnitude_floor"


def _stability_only_report(stability_rows, per_ticker_rows):
    """Minimal report dict carrying only the keys `_print_burst_report` reads, so the printed
    lead-lag summary can be asserted without manufacturing tape that yields a given rho."""
    return {
        "mode": "burst",
        "window_start": "2026-07-29T17:40:00+00:00",
        "window_end": "2026-07-29T19:35:00+00:00",
        "n_records_in_window": len(per_ticker_rows),
        "n_pairs": len(per_ticker_rows),
        "cadence": probe.cadence_stats([]),
        "release_coverage": None,
        "per_capture_pair_counts": [],
        "frozen_quotes": {"per_pair": [], "n_consecutive_pairs": 0, "n_frozen_pairs": 0,
                          "frozen_fraction": None},
        "per_ticker_leadlag": per_ticker_rows,
        "per_ticker_leadlag_drop_top_pair": [],
        "leadlag_stability": stability_rows,
        "n_dislocations": 0,
        "dislocation_episodes": [],
        "fee_model": {"poly_fee_source": "core.pricing.polymarket_fee_per_contract"},
    }


def test_print_burst_report_counts_a_below_floor_rho_as_not_surviving(capsys):
    """The reader-facing half of the fix: the summary line must NOT credit the noise-level rho,
    and must say why. This is the line a future run would otherwise quote as '1 of 6 survives'."""
    pair = "KXFEDDECISION-26SEP-H0"
    per_ticker_rows = [{"pair": pair, "n_steps": 21, "rho_contemporaneous": None,
                        "rho_kalshi_leads": -0.25358737015281874,
                        "rho_polymarket_leads": -0.004471504399603508,
                        "signed_leader": "polymarket"}]
    stability_rows = probe.leadlag_stability(
        [{"pair": pair, "signed_leader": "polymarket"}],
        [{"pair": pair, "rho_polymarket_leads_full": -0.004471504399603508,
          "rho_polymarket_leads_drop_top_pair": -0.040873388781476276}])
    probe._print_burst_report(_stability_only_report(stability_rows, per_ticker_rows))
    printed = capsys.readouterr().out
    assert "1 show a directional leader, 0 survive leave-one-out" in printed
    assert "UNSTABLE_below_magnitude_floor" in printed
    assert "magnitude floor" in printed
    assert "NO signed-leader claim survives" in printed


def test_burst_report_single_shock_lead_does_not_survive_leave_one_out():
    """End-to-end L57: one big synchronised shock step manufactures a near-perfect
    'polymarket leads' rho over otherwise-uncorrelated tick noise; the leave-one-out on that
    direction's own driver pair must destroy it."""
    poly = [0.50, 0.51, 0.51, 0.52, 0.51, 0.51, 0.61, 0.61, 0.62]
    kalshi = [0.50, 0.50, 0.51, 0.51, 0.51, 0.52, 0.52, 0.62, 0.62]
    recs = [_brec(f"2026-07-29T17:{41 + 2 * i:02d}:00Z", "A", yes_ask=k, best_ask=p)
            for i, (k, p) in enumerate(zip(kalshi, poly))]
    report = probe.build_burst_report(recs)
    leadlag = {t["pair"]: t for t in report["per_ticker_leadlag"]}
    assert leadlag["A"]["signed_leader"] == "polymarket"
    assert leadlag["A"]["rho_polymarket_leads"] > 0.5
    stab = {s["pair"]: s for s in report["leadlag_stability"]}["A"]
    assert stab["stability"].startswith("UNSTABLE")
    assert abs(stab["rho_drop_top_pair"]) < abs(stab["rho_full"])


def test_burst_report_emits_the_loo_recompute_for_every_direction():
    kalshi = [0.50, 0.55, 0.55, 0.60, 0.60, 0.58, 0.58]
    poly = [0.50, 0.50, 0.55, 0.55, 0.60, 0.60, 0.58]
    recs = [_brec(f"2026-07-29T17:{41 + 2 * i:02d}:00Z", "A", yes_ask=k, best_ask=p)
            for i, (k, p) in enumerate(zip(kalshi, poly))]
    report = probe.build_burst_report(recs)
    loo = {r["pair"]: r for r in report["per_ticker_leadlag_drop_top_pair"]}["A"]
    # BOTH directions get their own drop-top-cross-product-pair recompute (per-direction, L57)
    for field in ("rho_polymarket_leads_full", "rho_polymarket_leads_drop_top_pair",
                  "rho_kalshi_leads_full", "rho_kalshi_leads_drop_top_pair"):
        assert field in loo
    stab = {s["pair"]: s for s in report["leadlag_stability"]}["A"]
    assert stab["signed_leader"] == "kalshi"
    assert stab["stability"] == "stable"


# --------------------------------------------------------------------------- #
# A3 — release-instant coverage (L164 made mechanical)
# --------------------------------------------------------------------------- #
def test_release_instant_bracketed_when_both_sides_are_within_one_cadence_step():
    recs = [_brec("2026-07-29T17:59:00Z", "A", yes_ask=0.5, best_ask=0.5),
            _brec("2026-07-29T18:00:30Z", "A", yes_ask=0.5, best_ask=0.5)]
    cov = probe.release_instant_coverage(recs, probe.parse_window_bound("2026-07-29T18:00:00Z"))
    assert cov["release_instant_bracketed"] is True
    assert cov["nearest_pre_offset_s"] == -60.0
    assert cov["nearest_post_offset_s"] == 30.0
    assert cov["containing_gap_s"] == 90.0


def test_release_instant_not_bracketed_when_a_seam_swallows_it():
    """The 2026-07-29 FOMC shape (sub-second fractions dropped for the fixture; the real tape's
    offsets are -557.18s / +162.83s): last pre-release capture 17:50:42Z, first post-release
    capture 18:02:42Z, a 720s hole straddling the 18:00:00Z statement."""
    recs = [_brec("2026-07-29T17:50:42Z", "A", yes_ask=0.5, best_ask=0.5),
            _brec("2026-07-29T18:02:42Z", "A", yes_ask=0.5, best_ask=0.5)]
    cov = probe.release_instant_coverage(recs, probe.parse_window_bound("2026-07-29T18:00:00Z"))
    assert cov["release_instant_bracketed"] is False
    assert cov["nearest_pre_offset_s"] == -558.0
    assert cov["nearest_post_offset_s"] == 162.0
    assert cov["containing_gap_s"] == 720.0
    assert cov["threshold_s"] == probe.RELEASE_BRACKET_THRESHOLD_S


def test_release_instant_not_bracketed_when_only_one_side_is_close():
    recs = [_brec("2026-07-29T17:59:30Z", "A", yes_ask=0.5, best_ask=0.5),
            _brec("2026-07-29T18:10:00Z", "A", yes_ask=0.5, best_ask=0.5)]
    cov = probe.release_instant_coverage(recs, probe.parse_window_bound("2026-07-29T18:00:00Z"))
    assert cov["release_instant_bracketed"] is False
    assert cov["nearest_pre_offset_s"] == -30.0


def test_release_instant_no_post_capture_at_all():
    recs = [_brec("2026-07-29T17:59:30Z", "A", yes_ask=0.5, best_ask=0.5)]
    cov = probe.release_instant_coverage(recs, probe.parse_window_bound("2026-07-29T18:00:00Z"))
    assert cov["release_instant_bracketed"] is False
    assert cov["nearest_post_capture"] is None
    assert cov["containing_gap_s"] is None


def test_release_instant_threshold_is_named_and_documented():
    cov = probe.release_instant_coverage([], probe.parse_window_bound("2026-07-29T18:00:00Z"))
    assert cov["threshold_s"] == probe.RELEASE_BRACKET_THRESHOLD_S == 120.0
    assert "burst cadence" in cov["threshold_source"]
    assert cov["release_instant_bracketed"] is False


def test_burst_report_carries_release_coverage_only_when_asked():
    recs = [_brec("2026-07-29T17:50:42Z", "A", yes_ask=0.5, best_ask=0.5),
            _brec("2026-07-29T18:02:42Z", "A", yes_ask=0.5, best_ask=0.5)]
    assert probe.build_burst_report(recs)["release_coverage"] is None
    report = probe.build_burst_report(
        recs, release_instant=probe.parse_window_bound("2026-07-29T18:00:00Z"))
    assert report["release_coverage"]["release_instant_bracketed"] is False


def test_cli_release_instant_flag_is_wired_through(tmp_path):
    recs = [_brec("2026-07-29T17:50:42Z", "A", yes_ask=0.5, yes_bid=0.49,
                  best_ask=0.51, best_bid=0.5),
            _brec("2026-07-29T18:02:42Z", "A", yes_ask=0.5, yes_bid=0.49,
                  best_ask=0.51, best_bid=0.5)]
    tape_dir = _write_burst_tape(tmp_path, recs)
    out = tmp_path / "r.json"
    assert probe.main(["--tape-dir", str(tape_dir), *_FOMC_WINDOW,
                       "--release-instant", "2026-07-29T18:00:00Z",
                       "--json-out", str(out)]) == 0
    cov = json.loads(out.read_text())["release_coverage"]
    assert cov["release_instant_bracketed"] is False
    assert cov["containing_gap_s"] == 720.0


def test_cadence_stats_enumerates_seams_the_median_hides():
    """A 90s median with a 720s hole in it: the seam list is what makes the hole visible."""
    stamps = ["17:41:42", "17:43:12", "17:44:42", "17:46:12", "17:50:42", "18:02:42"]
    recs = [_brec(f"2026-07-29T{s}Z", "A", yes_ask=0.5, best_ask=0.5) for s in stamps]
    cad = probe.cadence_stats(recs)
    assert cad["median_gap_s"] == 90.0
    assert cad["n_gaps_over_threshold"] == 2
    assert cad["gaps_over_threshold_s"] == [720.0, 270.0]


# --------------------------------------------------------------------------- #
# A4 — per-capture membership + L32 frozen-quote fractions
# --------------------------------------------------------------------------- #
def test_per_capture_pair_counts_names_a_market_that_disappears():
    """The FOMC fact this makes visible: Kalshi delists the DECIDED meeting's buckets at the
    decision, so the pair count drops and the removed ticker is named — meaning that market
    has ZERO post-release observations."""
    recs = [
        _brec("2026-07-29T17:50:42Z", "KXFEDDECISION-26JUL-H0", yes_ask=0.80, best_ask=0.794),
        _brec("2026-07-29T17:50:42Z", "KXFEDDECISION-26SEP-H25", yes_ask=0.59, best_ask=0.55),
        _brec("2026-07-29T18:02:42Z", "KXFEDDECISION-26SEP-H25", yes_ask=0.65, best_ask=0.64),
    ]
    counts = probe.per_capture_pair_counts(probe.build_burst_series(recs))
    assert [c["n_pairs"] for c in counts] == [2, 1]
    assert counts[0]["pairs_removed"] == [] and counts[0]["pairs_added"] == []
    assert counts[1]["pairs_removed"] == ["KXFEDDECISION-26JUL-H0"]


def test_frozen_quote_fractions_separates_a_dead_book_from_a_moving_one():
    frozen = [_brec(f"2026-07-29T17:{m:02d}:00Z", "DEAD", yes_ask=0.58, yes_bid=0.57,
                    best_ask=0.63, best_bid=0.62) for m in (41, 43, 45)]
    moving = [_brec(f"2026-07-29T17:{m:02d}:00Z", "LIVE", yes_ask=0.58 + 0.01 * i,
                    yes_bid=0.57 + 0.01 * i, best_ask=0.63, best_bid=0.62)
              for i, m in enumerate((41, 43, 45))]
    fz = probe.frozen_quote_fractions(probe.build_burst_series(frozen + moving))
    per_pair = {p["pair"]: p for p in fz["per_pair"]}
    assert per_pair["DEAD"]["frozen_fraction"] == 1.0
    assert per_pair["LIVE"]["frozen_fraction"] == 0.0
    assert fz["n_consecutive_pairs"] == 4 and fz["n_frozen_pairs"] == 2
    assert fz["frozen_fraction"] == pytest.approx(0.5)


def test_frozen_quote_fractions_single_capture_pair_has_no_consecutive_pairs():
    fz = probe.frozen_quote_fractions(probe.build_burst_series(
        [_brec("2026-07-29T17:41:00Z", "A", yes_ask=0.5, best_ask=0.5)]))
    assert fz["per_pair"][0]["frozen_fraction"] is None
    assert fz["frozen_fraction"] is None


def test_quotes_frozen_requires_all_four_quotes_unchanged():
    base = {"kalshi_yes_ask": 0.58, "kalshi_yes_bid": 0.57,
            "poly_best_ask": 0.63, "poly_best_bid": 0.62}
    assert probe._quotes_frozen(base, dict(base)) is True
    for key in probe.QUOTE_KEYS:
        moved = dict(base)
        moved[key] = base[key] + 0.01
        assert probe._quotes_frozen(base, moved) is False


def test_durable_dislocation_on_a_frozen_book_is_attributed_as_such():
    """L31/L32 attribution: the 26OCT-H0 shape — a byte-frozen far-dated book whose nominal
    cross-venue gap persists for the whole window. Durable AND small AND 100% frozen is the
    stale-nominal-quote artifact signature, not an edge."""
    recs = [_brec(f"2026-07-29T{h}:{m:02d}:42Z", "KXFEDDECISION-26OCT-H0",
                  yes_ask=0.58, yes_bid=0.57, best_ask=0.63, best_bid=0.62)
            for h, m in (("17", 41), ("17", 43), ("17", 45), ("18", 2))]
    eps = probe.dislocation_episodes(probe.build_burst_series(recs),
                                    poly_fee_model=probe.PolyFeeModel("schedule"))
    assert len(eps) == 1
    ep = eps[0]
    assert ep["direction"] == "buy_kalshi_sell_poly"
    assert ep["n_captures"] == 4
    assert ep["frozen_pairs_fraction"] == 1.0
    assert ep["n_frozen_pairs"] == ep["n_consecutive_pairs"] == 3
    # sub-tick: fails an economic-significance gate even though the sign is positive (L27)
    assert 0.0 < ep["max_net_edge"] < 0.01


def test_episode_frozen_fraction_is_zero_when_the_book_moves_every_capture():
    recs = [_brec(f"2026-07-29T17:{m:02d}:00Z", "A", yes_ask=0.40 + 0.01 * i,
                  yes_bid=0.38 + 0.01 * i, best_ask=0.44, best_bid=0.50 + 0.01 * i)
            for i, m in enumerate((41, 43, 45))]
    eps = probe.dislocation_episodes(probe.build_burst_series(recs),
                                    poly_fee_model=probe.PolyFeeModel("schedule"))
    assert len(eps) == 1
    assert eps[0]["frozen_pairs_fraction"] == 0.0


def test_burst_report_wires_membership_counts_and_frozen_fractions():
    recs = [_brec("2026-07-29T17:50:42Z", "GONE", yes_ask=0.80, yes_bid=0.79,
                  best_ask=0.794, best_bid=0.792),
            _brec("2026-07-29T17:50:42Z", "STAY", yes_ask=0.58, yes_bid=0.57,
                  best_ask=0.63, best_bid=0.62),
            _brec("2026-07-29T18:02:42Z", "STAY", yes_ask=0.58, yes_bid=0.57,
                  best_ask=0.63, best_bid=0.62)]
    report = probe.build_burst_report(recs)
    assert [c["n_pairs"] for c in report["per_capture_pair_counts"]] == [2, 1]
    assert report["frozen_quotes"]["n_frozen_pairs"] == 1
    assert report["frozen_quotes"]["frozen_fraction"] == 1.0


def test_print_burst_report_names_the_unbracketed_release_and_the_seams(capsys):
    recs = [_brec("2026-07-29T17:50:42Z", "A", yes_ask=0.58, yes_bid=0.57,
                  best_ask=0.63, best_bid=0.62),
            _brec("2026-07-29T18:02:42Z", "A", yes_ask=0.58, yes_bid=0.57,
                  best_ask=0.63, best_bid=0.62)]
    report = probe.build_burst_report(
        recs, release_instant=probe.parse_window_bound("2026-07-29T18:00:00Z"))
    probe._print_burst_report(report)
    printed = capsys.readouterr().out
    assert "release_instant_bracketed=FALSE" in printed
    assert "DATA-ADEQUACY FAILURE" in printed
    assert "SEAMS" in printed
    assert "frozen" in printed


# --------------------------------------------------------------------------- #
# CLI INVOCABILITY — both documented forms, pinned in real subprocesses.
#
# Round-2 regression: adding `from scripts.s9_leadlag_probe import ...` broke
# `python3 scripts/s17_leadlag_probe.py ...` with `ModuleNotFoundError: No module named
# 'scripts'`, while `PYTHONPATH=. python3 -m scripts.s17_leadlag_probe ...` kept working.
# `pyproject.toml` installs core/collection/validation/analysis as packages but NOT `scripts`, and
# the repo-root `conftest.py` only repairs sys.path under pytest — so nothing in the test suite
# could see the breakage. BOTH forms are load-bearing and both get a subprocess pin: LOOP-QUEUE.md
# (Q19/Q12), kb/00-LOG.md and kb/strategies/00-index.md cite this probe by SCRIPT PATH
# (`scripts/s17_leadlag_probe.py --burst-window ...`, i.e. the broken form), while the sibling CPI
# finding findings/2026-07-14-s17-burst-cpi-q19.md cites the `-m` form.
# Precedent for shelling out with sys.executable: tests/test_s14_paper_strategy.py.
# --------------------------------------------------------------------------- #
import os
import subprocess
import sys
from pathlib import Path

_INVOCATION_TAPE = [
    _brec("2026-07-29T17:50:42Z", "KXFEDDECISION-26SEP-H25", yes_ask=0.59, yes_bid=0.58,
          best_ask=0.55, best_bid=0.54),
    _brec("2026-07-29T18:02:42Z", "KXFEDDECISION-26SEP-H25", yes_ask=0.65, yes_bid=0.61,
          best_ask=0.64, best_bid=0.63),
]


def _run_probe_subprocess(argv, *, cwd, scrub_pythonpath, extra_env=None):
    env = dict(os.environ)
    if scrub_pythonpath:
        env.pop("PYTHONPATH", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run([sys.executable, *argv], cwd=str(cwd), env=env,
                          capture_output=True, text=True)


def test_direct_script_invocation_needs_no_pythonpath(tmp_path):
    """`python3 scripts/s17_leadlag_probe.py --burst-window ...` — the script-path form the queue
    and registry cite, and the one A2's cross-script import broke.
    Run with PYTHONPATH SCRUBBED and cwd OUTSIDE the repo, which is the only configuration that
    can catch the missing sys.path bootstrap (for a script invocation Python puts the SCRIPT's
    directory on sys.path, not the cwd)."""
    script = Path(probe.__file__).resolve()
    tape_dir = _write_burst_tape(tmp_path, _INVOCATION_TAPE)
    out = tmp_path / "direct.json"
    proc = _run_probe_subprocess(
        [str(script), "--tape-dir", str(tape_dir), *_FOMC_WINDOW,
         "--release-instant", "2026-07-29T18:00:00Z", "--json-out", str(out)],
        cwd=tmp_path, scrub_pythonpath=True)
    assert "No module named 'scripts'" not in proc.stderr, proc.stderr
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text())
    assert report["mode"] == "burst"
    assert report["release_coverage"]["containing_gap_s"] == 720.0
    # the imported-not-copied L57 helper (the import that broke this form) really ran: the key
    # only exists because `per_ticker_leadlag_drop_largest` resolved and returned.
    assert isinstance(report["per_ticker_leadlag_drop_top_pair"], list)
    assert isinstance(report["leadlag_stability"], list)


def test_module_form_invocation_still_works(tmp_path):
    """`PYTHONPATH=. python3 -m scripts.s17_leadlag_probe ...` — the form that kept working
    through the regression. Pinned too, so a future sys.path change cannot fix one and break the
    other silently."""
    repo_root = Path(probe.__file__).resolve().parents[1]
    tape_dir = _write_burst_tape(tmp_path, _INVOCATION_TAPE)
    out = tmp_path / "module.json"
    proc = _run_probe_subprocess(
        ["-m", "scripts.s17_leadlag_probe", "--tape-dir", str(tape_dir), *_FOMC_WINDOW,
         "--release-instant", "2026-07-29T18:00:00Z", "--json-out", str(out)],
        cwd=repo_root, scrub_pythonpath=True, extra_env={"PYTHONPATH": str(repo_root)})
    assert proc.returncode == 0, proc.stderr
    assert json.loads(out.read_text())["release_coverage"]["containing_gap_s"] == 720.0


# ─────────────────────────────────────────────────────────────────────────────
# L236 — per-OBSERVATION magnitude decomposition of the dislocation hit count
# (`core.bootstrap.hit_magnitude_decomposition` wired into `build_burst_report`)
# ─────────────────────────────────────────────────────────────────────────────

def test_dislocation_magnitude_is_per_observation_not_per_episode_max():
    """The L236 rule in the probe's own shape: an episode whose MAX is a real +$0.003 can
    still contain a residue capture, and the per-episode-max view loses it."""
    residue = 1.734723475976807e-17
    hits = [{"net_edge": residue}, {"net_edge": residue}, {"net_edge": 0.003},
            {"net_edge": 0.02}]
    episodes = [{"max_net_edge": residue, "n_captures": 1},
                {"max_net_edge": 0.003, "n_captures": 2},   # hides one residue capture
                {"max_net_edge": 0.02, "n_captures": 1}]
    mag = probe.dislocation_magnitude(hits, episodes)
    assert mag["n"] == 4
    assert mag["n_residue"] == 2
    assert mag["n_sub_tick"] == 3
    assert mag["n_clears_tick"] == 1
    assert mag["episode_max_view"]["n_residue"] == 1
    assert mag["episode_max_view"]["n_captures_in_residue_episodes"] == 1
    assert mag["understates_residue_by"] == 1


def test_dislocation_magnitude_understatement_is_zero_when_the_views_agree():
    hits = [{"net_edge": 0.02}, {"net_edge": 0.03}]
    episodes = [{"max_net_edge": 0.03, "n_captures": 2}]
    mag = probe.dislocation_magnitude(hits, episodes)
    assert mag["n_residue"] == 0
    assert mag["understates_residue_by"] == 0


def test_dislocation_magnitude_empty_scan_is_honest():
    mag = probe.dislocation_magnitude([], [])
    assert mag["n"] == 0
    assert mag["sub_tick_share"] is None
    assert mag["episode_max_view"]["n"] == 0
    assert mag["understates_residue_by"] == 0


def test_build_burst_report_carries_the_magnitude_field():
    recs = [_rec("c1", "KXFEDDECISION-26OCT-H25", 0.10, 0.50),
            _rec("c2", "KXFEDDECISION-26OCT-H25", 0.10, 0.50)]
    for i, r in enumerate(recs):
        r["captured_at"] = "2026-07-29T17:%02d:00+00:00" % (40 + i)
    report = probe.build_burst_report(
        recs, start=probe.parse_iso_utc("2026-07-29T17:00:00+00:00"),
        end=probe.parse_iso_utc("2026-07-29T18:00:00+00:00"))
    mag = report["dislocation_magnitude"]
    assert mag["n"] == report["n_dislocations"]
    assert set(["n", "n_residue", "n_sub_tick", "n_clears_tick", "episode_max_view",
                "understates_residue_by"]).issubset(mag)


# ── real-tape acceptance (FROZEN slice per L191 — never an open-ended dt=* glob) ──

_FROZEN_BURST_DAY = "2026-07-29"
_FROZEN_BURST_WINDOW = ("2026-07-29T17:40:00+00:00", "2026-07-29T19:35:00+00:00")


def _frozen_burst_records():
    """Records from the ONE committed day-file that holds the 2026-07-29 FOMC burst window.
    Named explicitly: an open-ended glob over a live family turns routine capture growth into
    a red gate with zero code change (L191)."""
    path = probe.TAPE_DIR / ("dt=%s.jsonl" % _FROZEN_BURST_DAY)
    # HARD assert, not pytest.skip: this file is a COMMITTED artifact, so its absence is a
    # tape regression, not an optional-environment condition. A skip here would turn a
    # deleted-tape regression into a green suite (verifier finding, 2026-07-30).
    assert path.exists(), "committed frozen burst day-file is missing: %s" % path
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _frozen_burst_report(fee_model):
    return probe.build_burst_report(
        _frozen_burst_records(),
        start=probe.parse_iso_utc(_FROZEN_BURST_WINDOW[0]),
        end=probe.parse_iso_utc(_FROZEN_BURST_WINDOW[1]),
        poly_fee_model=probe.PolyFeeModel(fee_model))


def test_acceptance_l236_free_bracket_per_observation_decomposition_real_tape():
    """HARD acceptance on the real committed 2026-07-29 FOMC burst tape, `free` bracket —
    the exact population L236 was drawn from. The per-observation view finds FIVE residue
    captures; the per-episode-max view finds three episodes covering four. That one-capture
    gap IS the lesson."""
    report = _frozen_burst_report("free")
    # pinned so a tape change fails loudly and diagnosably rather than shifting the counts
    assert report["n_records_in_window"] == 278
    assert report["n_dislocations"] == 49
    assert len(report["dislocation_episodes"]) == 10
    mag = report["dislocation_magnitude"]
    assert mag["n"] == 49
    assert mag["n_unmeasurable"] == 0
    assert mag["n_residue"] == 5
    assert mag["n_sub_tick"] == 19
    assert mag["n_clears_tick"] == 30
    assert mag["max"] == 0.020000000000000035
    assert mag["episode_max_view"]["n_residue"] == 3
    assert mag["episode_max_view"]["n_captures_in_residue_episodes"] == 4
    assert mag["understates_residue_by"] == 1
    # ON-TAPE pin (not just the literal expressions): every residue hit AND every residue
    # episode max on this real window is the SAME float, 5*2**-58 — the numeric correction to
    # findings/2026-07-29-s17-burst-fomc-q19.md §4d, taken from the probe's own output.
    shared = 1.734723475976807e-17
    residue_hits = [h["net_edge"] for h in report["dislocations"] if abs(h["net_edge"]) < 1e-9]
    residue_eps = [e["max_net_edge"] for e in report["dislocation_episodes"]
                   if abs(e["max_net_edge"]) < 1e-9]
    assert len(residue_hits) == 5 and set(residue_hits) == {shared}
    assert len(residue_eps) == 3 and set(residue_eps) == {shared}


def test_acceptance_l236_schedule_bracket_is_entirely_sub_tick_real_tape():
    """Same tape, the HONEST fee model (`schedule`, the default): 34 fee-clearing captures,
    every one of them sub-tick — max +$0.008220, below Kalshi's 1¢ tick. This is the number
    the S17 registry row quotes, now machine-decomposed instead of asserted in prose."""
    report = _frozen_burst_report("schedule")
    assert report["n_dislocations"] == 34
    mag = report["dislocation_magnitude"]
    assert mag["n"] == 34
    assert mag["n_residue"] == 0
    assert mag["n_sub_tick"] == 34
    assert mag["n_clears_tick"] == 0
    assert mag["sub_tick_share"] == 1.0
    assert mag["max"] == pytest.approx(0.008220, abs=5e-7)
