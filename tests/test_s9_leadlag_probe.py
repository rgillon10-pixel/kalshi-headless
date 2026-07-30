"""scripts.s9_leadlag_probe — pooled lead-lag cross-correlation over polymarket_pairs tape.
Offline: synthetic in-memory records only, no filesystem tape dependency, no network."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from core.pricing import POLYMARKET_US_TAKER_RATE, TAKER_FEE_RATE
from scripts import s9_leadlag_probe as probe


def _rec(capture_id, ticker, kalshi_ask, poly_ask, book_fetch_ok=True):
    return {
        "capture_id": capture_id,
        "kalshi": {"ticker": ticker, "yes_ask": kalshi_ask},
        "polymarket": {"best_ask": poly_ask, "book_fetch_ok": book_fetch_ok},
    }


def _burst_rec(captured_at, ticker, *, k_ask=None, k_bid=None, p_ask=None, p_bid=None,
               book_fetch_ok=True):
    return {
        "captured_at": captured_at,
        "kalshi": {"ticker": ticker, "yes_ask": k_ask, "yes_bid": k_bid},
        "polymarket": {"best_ask": p_ask, "best_bid": p_bid, "book_fetch_ok": book_fetch_ok},
    }


# --------------------------------------------------------------------------- #
# build_series
# --------------------------------------------------------------------------- #
def test_build_series_sorts_by_capture_and_groups_by_ticker():
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
    records = [{"capture_id": "c1", "kalshi": {"ticker": "T1"}, "polymarket": {"book_fetch_ok": True}}]
    assert probe.build_series(records) == {}


def test_build_series_last_write_wins_on_duplicate_capture_id():
    records = [_rec("c1", "T1", 0.19, 0.20), _rec("c1", "T1", 0.22, 0.23)]
    series = probe.build_series(records)
    assert series["T1"] == [("c1", 0.22, 0.23)]


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
    """Construct a market where polymarket's move at step t+1 always equals kalshi's move
    at step t (kalshi leads by exactly one capture) and confirm the pooled stat picks up
    the correct lag direction, not the reverse or contemporaneous one."""
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
# market_membership_changes
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
    tape_dir = tmp_path / "polymarket_pairs"
    tape_dir.mkdir()
    lines = [
        _rec(f"c{i}", "T1", 0.10 + 0.01 * i, 0.20 + 0.01 * i) for i in range(12)
    ]
    (tape_dir / "dt=2026-07-05.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")

    report = probe.build_report(tape_dir, min_captures=10)
    assert report["n_records"] == 12
    assert report["n_distinct_captures"] == 12
    assert report["n_distinct_markets"] == 1
    assert report["n_markets_min_captures"] == 1
    assert report["leadlag"]["n_markets_used"] == 1
    assert report["membership_changes"] == []


# --------------------------------------------------------------------------- #
# burst mode (Q19) — window filter, cadence honesty, series building
# --------------------------------------------------------------------------- #
def test_parse_capture_time_prefers_captured_at():
    t = probe.parse_capture_time({"captured_at": "2026-07-15T20:11:28.592737+00:00"})
    assert t == datetime(2026, 7, 15, 20, 11, 28, 592737, tzinfo=timezone.utc)


def test_parse_capture_time_falls_back_to_capture_id():
    t = probe.parse_capture_time({"capture_id": "20260715T201128Z"})
    assert t == datetime(2026, 7, 15, 20, 11, 28, tzinfo=timezone.utc)


def test_parse_capture_time_unparseable_is_none():
    assert probe.parse_capture_time({}) is None
    assert probe.parse_capture_time({"capture_id": "not-a-timestamp"}) is None


def test_filter_burst_window_inclusive_bounds():
    records = [
        _burst_rec("2026-07-15T20:09:59+00:00", "T1", k_ask=0.5, p_ask=0.5),
        _burst_rec("2026-07-15T20:10:00+00:00", "T1", k_ask=0.5, p_ask=0.5),
        _burst_rec("2026-07-15T21:00:00+00:00", "T1", k_ask=0.5, p_ask=0.5),
        _burst_rec("2026-07-15T21:00:01+00:00", "T1", k_ask=0.5, p_ask=0.5),
    ]
    start = probe.parse_window_bound("2026-07-15T20:10:00Z")
    end = probe.parse_window_bound("2026-07-15T21:00:00Z")
    out = probe.filter_burst_window(records, start, end)
    assert [r["captured_at"] for r in out] == [
        "2026-07-15T20:10:00+00:00", "2026-07-15T21:00:00+00:00",
    ]


def test_cadence_stats_burst_vs_hourly():
    burst = [_burst_rec(f"2026-07-15T20:{m:02d}:00+00:00", "T1", k_ask=0.5, p_ask=0.5)
             for m in (10, 12, 14)]
    stats = probe.cadence_stats(burst)
    assert stats["n_distinct_captures"] == 3
    assert stats["median_gap_s"] == pytest.approx(120.0)

    hourly = [_burst_rec("2026-07-15T20:00:00+00:00", "T1", k_ask=0.5, p_ask=0.5),
              _burst_rec("2026-07-15T21:00:00+00:00", "T1", k_ask=0.5, p_ask=0.5)]
    assert probe.cadence_stats(hourly)["median_gap_s"] == pytest.approx(3600.0)


def test_cadence_stats_empty_or_single():
    assert probe.cadence_stats([])["median_gap_s"] is None
    one = [_burst_rec("2026-07-15T20:00:00+00:00", "T1", k_ask=0.5, p_ask=0.5)]
    assert probe.cadence_stats(one)["median_gap_s"] is None


def test_build_burst_series_groups_and_drops_failed_fetch():
    records = [
        _burst_rec("2026-07-15T20:10:00+00:00", "T1", k_ask=0.50, k_bid=0.48, p_ask=0.51, p_bid=0.49),
        _burst_rec("2026-07-15T20:12:00+00:00", "T1", k_ask=0.52, k_bid=0.50, p_ask=0.53, p_bid=0.51),
        _burst_rec("2026-07-15T20:10:00+00:00", "T2", k_ask=0.20, p_ask=0.21, book_fetch_ok=False),
    ]
    series = probe.build_burst_series(records)
    assert list(series.keys()) == ["T1"]
    assert len(series["T1"]) == 2
    assert series["T1"][0][1]["kalshi_yes_ask"] == pytest.approx(0.50)


def test_build_burst_series_last_write_wins_same_instant():
    records = [
        _burst_rec("2026-07-15T20:10:00+00:00", "T1", k_ask=0.50, p_ask=0.51),
        _burst_rec("2026-07-15T20:10:00+00:00", "T1", k_ask=0.60, p_ask=0.61),
    ]
    series = probe.build_burst_series(records)
    assert len(series["T1"]) == 1
    assert series["T1"][0][1]["kalshi_yes_ask"] == pytest.approx(0.60)


# --------------------------------------------------------------------------- #
# burst mode — per-ticker signed lead-lag + leave-one-out robustness
# --------------------------------------------------------------------------- #
def _burst_series_from_prices(kalshi_prices, poly_prices, ticker="T1"):
    rows = []
    for i, (k, p) in enumerate(zip(kalshi_prices, poly_prices)):
        t = datetime(2026, 7, 15, 20, 0, 0, tzinfo=timezone.utc)
        rows.append((t.replace(minute=i * 2 % 60, hour=20 + i * 2 // 60),
                     {"kalshi_yes_ask": k, "kalshi_yes_bid": k - 0.02,
                      "poly_best_ask": p, "poly_best_bid": p - 0.01}))
    return {ticker: rows}


def test_per_ticker_leadlag_detects_kalshi_leading():
    # poly's delta at step i+1 equals kalshi's delta at step i (kalshi leads by one
    # capture); a less self-similar delta sequence than a simple 2-value alternation
    # keeps the REVERSE lag's correlation clearly weaker so the margin test is meaningful.
    kalshi = [0.10, 0.13, 0.11, 0.16, 0.12, 0.18, 0.17, 0.19]
    poly = [0.10, 0.10, 0.13, 0.11, 0.16, 0.12, 0.18, 0.17]
    series = _burst_series_from_prices(kalshi, poly)
    out = probe.per_ticker_leadlag(series, min_steps=3, margin=0.05)
    assert len(out) == 1
    assert out[0]["signed_leader"] == "kalshi"
    assert out[0]["rho_kalshi_leads"] == pytest.approx(1.0)
    assert out[0]["rho_kalshi_leads"] - out[0]["rho_polymarket_leads"] > 0.05


def test_per_ticker_leadlag_below_min_steps_is_dropped():
    series = _burst_series_from_prices([0.1, 0.11], [0.2, 0.21])
    assert probe.per_ticker_leadlag(series, min_steps=3) == []


# --------------------------------------------------------------------------- #
# burst mode — SIGN PRECONDITION on the signed-leader argmax (L235).
#
# `signed_leader` was a pure argmax over a SIGNED statistic subject to a `margin` DIFFERENCE,
# so when BOTH lag-rho are negative it named the LESS NEGATIVE direction the leader — which is
# not a lead in any economic reading. The real row was in the S17 sibling probe
# (`KXFEDDECISION-26SEP-H0`, leader=polymarket on rho = -0.0045 over Kalshi's -0.2536), but the
# comparison here was byte-identical, so the defect and the fix are both shared: the rule lives
# once, in `signed_leader_label`, and S17 imports it (L36/L102 — the divergent twin is the next
# variant of the bug). L229's 0.05 magnitude floor (S17-side) caught the real row only by luck;
# the verifier's counterexample -0.30 / -0.20 clears that floor 6x and is killed by SIGN alone.
# --------------------------------------------------------------------------- #
def test_signed_leader_label_refuses_a_leader_when_both_directions_are_negative():
    """POSITIVE CONTROL — the verifier's exact counterexample. Pre-fix this returned
    'polymarket' (because -0.20 > -0.30 + 0.05 as a signed comparison)."""
    assert probe.signed_leader_label(-0.30, -0.20, margin=0.05) == "none"
    assert probe.signed_leader_label(-0.20, -0.30, margin=0.05) == "none"


def test_signed_leader_label_pins_the_historical_26sep_h0_row():
    """The REAL executed values from the 2026-07-29 FOMC run (rho_k = -0.2536,
    rho_p = -0.0045), which that run labelled leader=polymarket. Both negative -> no leader."""
    assert probe.signed_leader_label(-0.25358737015281874, -0.004471504399603508,
                                     margin=0.05) == "none"


def test_signed_leader_label_sign_gate_is_independent_of_any_magnitude_gate():
    """L235's load-bearing point, checked against this module's own margin: the counterexample
    clears 0.05 on BOTH magnitudes and on the difference, and is rejected by the sign gate
    alone; conversely a sub-0.05-magnitude rho can pass the sign gate."""
    assert abs(-0.30) > 0.05 and abs(-0.20) > 0.05
    assert abs(-0.20 - -0.30) > 0.05
    assert probe.signed_leader_label(-0.30, -0.20, margin=0.05) == "none"
    assert probe.signed_leader_label(0.03, -0.30, margin=0.05) == "kalshi"   # sign ok, tiny


def test_signed_leader_label_negative_controls_unchanged():
    """MUST NOT FIRE — behaviour is unchanged wherever the winning direction's rho is positive,
    and for the within-margin and None cases."""
    assert probe.signed_leader_label(0.30, 0.20, margin=0.05) == "kalshi"
    assert probe.signed_leader_label(0.20, 0.30, margin=0.05) == "polymarket"
    assert probe.signed_leader_label(0.30, -0.20, margin=0.05) == "kalshi"     # mixed sign
    assert probe.signed_leader_label(-0.20, 0.30, margin=0.05) == "polymarket"  # mixed sign
    assert probe.signed_leader_label(0.30, 0.29, margin=0.05) == "none"        # within margin
    assert probe.signed_leader_label(None, 0.30, margin=0.05) is None
    assert probe.signed_leader_label(0.30, None, margin=0.05) is None
    assert probe.signed_leader_label(None, None, margin=0.05) is None


def test_per_ticker_leadlag_names_no_leader_when_both_lag_rho_are_negative():
    """END-TO-END through `per_ticker_leadlag` on a series that genuinely produces two NEGATIVE
    lag-rho of the counterexample's shape. The observed rho are asserted so the fixture cannot
    drift out of the both-negative regime and stop testing the sign gate."""
    kalshi = [0.50, 0.50, 0.51, 0.50, 0.48, 0.50, 0.52, 0.53]
    poly = [0.50, 0.50, 0.51, 0.52, 0.53, 0.54, 0.52, 0.54]
    series = _burst_series_from_prices(kalshi, poly)
    out = probe.per_ticker_leadlag(series, min_steps=3, margin=0.05)[0]
    assert out["rho_kalshi_leads"] == pytest.approx(-0.2988, abs=1e-3)
    assert out["rho_polymarket_leads"] == pytest.approx(-0.2010, abs=1e-3)
    assert out["rho_kalshi_leads"] < 0 and out["rho_polymarket_leads"] < 0
    # the pre-fix argmax fired here: the less-negative direction beats the other by > margin
    assert out["rho_polymarket_leads"] > out["rho_kalshi_leads"] + 0.05
    assert out["signed_leader"] == "none"
    # schema unchanged — no new keys; both rho stay on the row so 'none' is auditable
    assert set(out) == {"pair", "n_steps", "rho_contemporaneous", "rho_kalshi_leads",
                        "rho_polymarket_leads", "signed_leader"}


def test_per_ticker_leadlag_drop_largest_collapses_single_tick_artifact():
    # A "lead" driven entirely by ONE lag-pair should collapse toward noise once that pair
    # is removed — the L57 single-tick-artifact check. Here kalshi jumps one capture before
    # poly (kalshi leads); the LOO must drop the single kalshi-leads pair carrying the whole
    # correlation, collapsing rho_kalshi_leads from ~1 toward 0. It ALSO reports the largest
    # RAW combined move step for provenance — which here is the DIFFERENT step spanning the
    # kalshi crash + poly jump, exactly the case where "biggest raw move" != "lead driver".
    # Deltas engineered so the kalshi-leads lag-pairs are one big aligned driver (0.5, 0.5)
    # plus four symmetric residual pairs whose lagged correlation is exactly 0. Full
    # rho_kalshi_leads is dominated by the driver; dropping that single pair leaves the
    # zero-correlation residual.
    kalshi = [0.10, 0.60, 0.70, 0.80, 0.70, 0.60, 0.60]
    poly = [0.10, 0.10, 0.60, 0.70, 0.60, 0.70, 0.60]
    series = _burst_series_from_prices(kalshi, poly)
    out = probe.per_ticker_leadlag_drop_largest(series, min_steps=3)
    assert len(out) == 1
    row = out[0]
    assert row["rho_kalshi_leads_full"] == pytest.approx(0.8333333, rel=1e-4)
    assert row["rho_kalshi_leads_drop_top_pair"] == pytest.approx(0.0, abs=1e-9)  # collapses
    # largest RAW combined |dK|+|dP| is a DIFFERENT step (the poly-jump step 1), not the
    # lead-driving pair — the case where "biggest raw move" != "lead driver".
    assert row["largest_raw_move_step_index"] == 1


# --------------------------------------------------------------------------- #
# burst mode — fillable cross-venue dislocation scan, fee-corrected (Q31)
# --------------------------------------------------------------------------- #
def test_dislocation_scan_clears_at_zero_fee_but_not_real_fee():
    # kalshi_ask=0.55, poly_bid=0.575: raw gap = 0.025. Kalshi's taker fee alone (0.02)
    # plus Polymarket's REAL taker fee (~0.0122) exceeds the gap -> no hit at the real
    # fee model (Q31's post-2026-07-15 correction). Dropping Polymarket's fee to 0.0
    # (the stale pre-regime-change assumption) leaves only Kalshi's 0.02 fee, which the
    # 0.025 gap clears -> this is exactly the "fee correction bites" case the burst
    # dislocation scan must get right, not the old fee-free-Poly view.
    t = datetime(2026, 7, 15, 20, 10, 0, tzinfo=timezone.utc)
    quote = {"kalshi_yes_ask": 0.55, "kalshi_yes_bid": 0.53,
             "poly_best_ask": 0.60, "poly_best_bid": 0.575}
    series = {"T1": [(t, quote)]}

    real_hits = probe.dislocation_scan(series, kalshi_fee_rate=TAKER_FEE_RATE, poly_fee_rate=POLYMARKET_US_TAKER_RATE)
    zero_hits = probe.dislocation_scan(series, kalshi_fee_rate=TAKER_FEE_RATE, poly_fee_rate=0.0)
    assert real_hits == []
    assert len(zero_hits) == 1
    assert zero_hits[0]["direction"] == "buy_kalshi_sell_poly"
    assert zero_hits[0]["net_edge"] > 0.0


def test_dislocation_scan_no_hit_when_legs_missing():
    t = datetime(2026, 7, 15, 20, 10, 0, tzinfo=timezone.utc)
    quote = {"kalshi_yes_ask": None, "kalshi_yes_bid": None,
             "poly_best_ask": 0.50, "poly_best_bid": 0.49}
    assert probe.dislocation_scan({"T1": [(t, quote)]}) == []


def test_dislocation_episodes_groups_contiguous_same_direction_runs():
    # Two consecutive live captures on the same direction form one episode; a third,
    # non-live capture closes it.
    t0 = datetime(2026, 7, 15, 20, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 7, 15, 20, 12, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 7, 15, 20, 14, 0, tzinfo=timezone.utc)
    live_quote = {"kalshi_yes_ask": 0.10, "kalshi_yes_bid": 0.08,
                  "poly_best_ask": 0.50, "poly_best_bid": 0.50}
    dead_quote = {"kalshi_yes_ask": 0.50, "kalshi_yes_bid": 0.48,
                  "poly_best_ask": 0.50, "poly_best_bid": 0.49}
    series = {"T1": [(t0, live_quote), (t1, live_quote), (t2, dead_quote)]}
    episodes = probe.dislocation_episodes(series, kalshi_fee_rate=TAKER_FEE_RATE, poly_fee_rate=POLYMARKET_US_TAKER_RATE)
    assert len(episodes) == 1
    assert episodes[0]["n_captures"] == 2
    assert episodes[0]["duration_s"] == pytest.approx(120.0)


def test_build_burst_report_end_to_end():
    records = [
        _burst_rec("2026-07-15T20:10:00+00:00", "T1", k_ask=0.10, k_bid=0.08,
                   p_ask=0.50, p_bid=0.50),
        _burst_rec("2026-07-15T20:12:00+00:00", "T1", k_ask=0.12, k_bid=0.10,
                   p_ask=0.52, p_bid=0.51),
        _burst_rec("2026-07-15T20:14:00+00:00", "T1", k_ask=0.11, k_bid=0.09,
                   p_ask=0.51, p_bid=0.505),
    ]
    start = probe.parse_window_bound("2026-07-15T20:10:00Z")
    end = probe.parse_window_bound("2026-07-15T20:14:00Z")
    report = probe.build_burst_report(records, start=start, end=end)
    assert report["mode"] == "burst"
    assert report["n_records_in_window"] == 3
    assert report["n_pairs"] == 1
    assert report["fee_model"]["poly_rate"] == pytest.approx(probe.POLYMARKET_US_TAKER_RATE)
    assert "poly_fee_free_sensitivity" in report
    assert report["poly_fee_free_sensitivity"]["fee_model"]["poly_rate"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# L236 — per-OBSERVATION magnitude decomposition (shared helper lives HERE; the S17
# twin imports it rather than re-defining it, closing the L36/L102 duplicate-helper class)
# ─────────────────────────────────────────────────────────────────────────────

def test_dislocation_magnitude_is_per_observation_not_per_episode_max():
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


def test_dislocation_magnitude_empty_scan_is_honest():
    mag = probe.dislocation_magnitude([], [])
    assert mag["n"] == 0
    assert mag["sub_tick_share"] is None
    assert mag["understates_residue_by"] == 0


def test_burst_report_carries_magnitude_on_BOTH_the_primary_and_the_fee_free_bracket():
    """L236 was drawn from a fee-FREE generous bracket, so the sensitivity block needs the
    decomposition just as much as the primary one — a headline hit count from either is
    quotable, and either can be residue."""
    records = [
        _burst_rec("2026-07-15T20:10:00+00:00", "T1", k_ask=0.10, k_bid=0.08,
                   p_ask=0.50, p_bid=0.50),
        _burst_rec("2026-07-15T20:12:00+00:00", "T1", k_ask=0.12, k_bid=0.10,
                   p_ask=0.52, p_bid=0.51),
    ]
    start = probe.parse_window_bound("2026-07-15T20:10:00Z")
    end = probe.parse_window_bound("2026-07-15T20:14:00Z")
    report = probe.build_burst_report(records, start=start, end=end)
    for block in (report, report["poly_fee_free_sensitivity"]):
        mag = block["dislocation_magnitude"]
        assert mag["n"] == block["n_dislocations"]
        assert set(["n_residue", "n_sub_tick", "n_clears_tick", "episode_max_view",
                    "understates_residue_by"]).issubset(mag)


def test_s17_imports_the_shared_helper_rather_than_redefining_it():
    """L36/L102: a byte-identical twin in two probe files is how a fixed bug comes back in
    one of them. Assert identity, not equality of behaviour."""
    from scripts import s17_leadlag_probe as s17
    assert s17.dislocation_magnitude is probe.dislocation_magnitude
    assert s17._print_magnitude is probe._print_magnitude
