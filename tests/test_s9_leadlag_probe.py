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
# signed_leader_from_rhos — the SHARED leader-selection gate, L235's sign precondition.
#
# The helper lives in THIS module (imported by scripts/s17_leadlag_probe.py, which must not
# hold a second copy — L36/L102), so it is pinned here, once. L235: the margin test compares
# SIGNED ρ, so without a positivity precondition it crowns the LESS NEGATIVE of two negative
# correlations as the "leader" — and the |ρ| magnitude floor covers that case only by luck.
# --------------------------------------------------------------------------- #
_SIGN_GATE_MARGIN = 0.05  # this module's own per_ticker_leadlag margin default


def test_l235_signed_leader_rejects_less_negative_of_two_negative_rhos():
    # THE L235-NAMED PIN (the verifier's counterexample). rho_p = -0.20 beats rho_k = -0.30 by
    # 0.10 > margin, so the margin test alone would name polymarket. It must not: -0.20 is not
    # a lead, it is merely less negative. Note |−0.20| is FAR above any 0.05 magnitude floor,
    # which is precisely why the floor does not cover this case.
    assert probe.signed_leader_from_rhos(-0.30, -0.20, margin=_SIGN_GATE_MARGIN) == "none"
    # ...and symmetrically with the venues swapped.
    assert probe.signed_leader_from_rhos(-0.20, -0.30, margin=_SIGN_GATE_MARGIN) == "none"


def test_l235_signed_leader_regression_kxfeddecision_26sep_h0_is_not_polymarket():
    # The real row from findings/2026-07-29-s17-burst-fomc-q19.md §5: KXFEDDECISION-26SEP-H0
    # was published as `leader = polymarket` on these two exact floats, purely because
    # -0.00447 > -0.25359 as a signed comparison. Sign-gated, it is no claim at all.
    # (Same full-precision pair as tests/test_s17_leadlag_probe.py's L229/D2 pin.)
    rho_kalshi_leads = -0.25358737015281874
    rho_polymarket_leads = -0.004471504399603508
    assert rho_polymarket_leads > rho_kalshi_leads + _SIGN_GATE_MARGIN  # the old argmax path
    assert probe.signed_leader_from_rhos(
        rho_kalshi_leads, rho_polymarket_leads, margin=_SIGN_GATE_MARGIN) == "none"


def test_signed_leader_still_names_a_genuine_positive_lead_both_directions():
    # No behaviour regression: a POSITIVE winning ρ beating the other by more than margin
    # still names its venue, in either direction (including when the loser is negative).
    assert probe.signed_leader_from_rhos(0.40, 0.10, margin=_SIGN_GATE_MARGIN) == "kalshi"
    assert probe.signed_leader_from_rhos(0.10, 0.40, margin=_SIGN_GATE_MARGIN) == "polymarket"
    assert probe.signed_leader_from_rhos(0.30, -0.20, margin=_SIGN_GATE_MARGIN) == "kalshi"
    assert probe.signed_leader_from_rhos(-0.20, 0.30, margin=_SIGN_GATE_MARGIN) == "polymarket"


def test_signed_leader_positive_winner_inside_the_margin_is_none():
    # Pre-existing behaviour, pinned: winning ρ > 0 but NOT by `margin` -> no claim.
    assert probe.signed_leader_from_rhos(0.40, 0.36, margin=_SIGN_GATE_MARGIN) == "none"
    assert probe.signed_leader_from_rhos(0.36, 0.40, margin=_SIGN_GATE_MARGIN) == "none"
    # Exactly AT the margin is not "by more than" the margin, either. Values chosen to be
    # EXACTLY representable in binary (0.5 / 0.25) so this pins the `>` and not a float
    # rounding accident: 0.35 + 0.05 == 0.39999999999999997 < 0.40 in IEEE754, so the
    # "obvious" (0.40, 0.35, margin=0.05) triple would silently test the wrong thing.
    assert probe.signed_leader_from_rhos(0.5, 0.25, margin=0.25) == "none"
    assert probe.signed_leader_from_rhos(0.25, 0.5, margin=0.25) == "none"


def test_signed_leader_exactly_zero_winning_rho_is_none():
    # The sign gate is strictly `> 0`: ρ = 0.0 carries no direction, so it is not a lead even
    # when it beats a negative counterpart by more than the margin.
    assert probe.signed_leader_from_rhos(-0.20, 0.0, margin=_SIGN_GATE_MARGIN) == "none"
    assert probe.signed_leader_from_rhos(0.0, -0.20, margin=_SIGN_GATE_MARGIN) == "none"


def test_signed_leader_is_none_object_only_when_a_rho_is_uncomputable():
    # `None` (the object) stays RESERVED for "no number", never for "no claim" — so a consumer
    # can distinguish an uncomputable ρ from a computed refusal.
    assert probe.signed_leader_from_rhos(None, -0.20, margin=_SIGN_GATE_MARGIN) is None
    assert probe.signed_leader_from_rhos(0.40, None, margin=_SIGN_GATE_MARGIN) is None
    assert probe.signed_leader_from_rhos(None, None, margin=_SIGN_GATE_MARGIN) is None
    # and the refusal is the STRING "none", not the object
    assert probe.signed_leader_from_rhos(-0.30, -0.20, margin=_SIGN_GATE_MARGIN) is not None


def test_signed_leader_negative_margin_raises_value_error():
    """A negative `margin` is a caller error, not a looser gate — it INVERTS the predicate.

    Un-guarded, `rho_a > rho_b + margin` with margin < 0 is satisfiable by the SMALLER ρ, so
    the function named the wrong venue: measured on the un-guarded implementation,
    `signed_leader_from_rhos(0.30, 0.35, margin=-0.10)` returned `"kalshi"` — the venue whose
    ρ (0.30) is the smaller of the two. Both ρ are positive there, so the L235 sign gate does
    not catch it; only an explicit guard does. ValueError (not `assert`) so it survives `-O`.
    """
    with pytest.raises(ValueError, match="margin"):
        probe.signed_leader_from_rhos(0.30, 0.35, margin=-0.10)
    with pytest.raises(ValueError, match="margin"):
        probe.signed_leader_from_rhos(-0.30, -0.20, margin=-0.01)
    # ...and it is rejected BEFORE the None check, so even the uncomputable path cannot mask it
    with pytest.raises(ValueError, match="margin"):
        probe.signed_leader_from_rhos(None, None, margin=-0.10)


def test_signed_leader_zero_margin_is_allowed_and_is_a_strict_comparison():
    """`margin = 0.0` is IN contract (>= 0) and degenerates to a strict `>` on the two ρ.

    Derivation, straight off the implementation: with margin = 0.0 the first branch is
    `rho_k > rho_p + 0.0`, and adding 0.0 to a float is exact, so the test is exactly
    `rho_k > rho_p` — strict, hence EQUAL ρ still yield no claim. The sign gate is unchanged
    and still applies, so two negative ρ remain `"none"` even at zero margin.
    """
    assert probe.signed_leader_from_rhos(0.40, 0.10, margin=0.0) == "kalshi"
    assert probe.signed_leader_from_rhos(0.25, 0.5, margin=0.0) == "polymarket"
    # equal ρ: `>` is strict, so no venue is named (0.20 is not exactly representable, but both
    # sides are the SAME float here, so the comparison is exact regardless)
    assert probe.signed_leader_from_rhos(0.20, 0.20, margin=0.0) == "none"
    # a one-tick-wide win IS enough at margin 0.0 — this is what "no margin" means
    assert probe.signed_leader_from_rhos(0.20, 0.19, margin=0.0) == "kalshi"
    # the L235 sign gate is independent of the margin and still bites at margin 0.0
    assert probe.signed_leader_from_rhos(-0.10, -0.20, margin=0.0) == "none"
    assert probe.signed_leader_from_rhos(0.0, -0.20, margin=0.0) == "none"


def test_signed_leader_nan_rho_falls_through_to_the_string_none_not_the_object():
    """A NaN ρ yields the FAIL-SAFE `"none"` (no leader claimed), never the `None` object.

    Every comparison against NaN is False, so both margin tests fail and control reaches the
    `else`. Pinning the DIRECTION of that fall-through: a NaN must not be able to name a
    venue, and it must not impersonate an uncomputable ρ either (`None` stays reserved for a
    literal `None` argument). Unreachable from real tape: `pearson` (s9:108-118, mirrored at
    s17:166-176) returns `None` on zero variance instead of dividing to NaN, and tape prices
    are bounded in [0, 1] so its sums cannot overflow — hence NO NaN branch in the helper,
    which would be dead code. This test pins the incidental-but-safe behaviour, not a
    contract the callers rely on.
    """
    nan = float("nan")
    assert probe.signed_leader_from_rhos(nan, -0.20, margin=_SIGN_GATE_MARGIN) == "none"
    assert probe.signed_leader_from_rhos(-0.20, nan, margin=_SIGN_GATE_MARGIN) == "none"
    assert probe.signed_leader_from_rhos(nan, nan, margin=_SIGN_GATE_MARGIN) == "none"
    assert probe.signed_leader_from_rhos(nan, 0.40, margin=_SIGN_GATE_MARGIN) is not None


def test_per_ticker_leadlag_two_negative_rhos_yield_no_leader_end_to_end_l235():
    # End-to-end through per_ticker_leadlag on a synthetic ANTI-lead series: poly's delta at
    # step i+1 is the NEGATION of kalshi's delta at step i, so rho_kalshi_leads == -1.0 while
    # rho_polymarket_leads is a less-negative ~-0.766. The margin test alone would therefore
    # crown polymarket on a ρ of -0.766; the L235 sign gate refuses.
    kalshi = [0.10, 0.13, 0.11, 0.16, 0.12, 0.18, 0.17, 0.19]
    poly = [0.50, 0.50, 0.47, 0.49, 0.44, 0.48, 0.42, 0.43]
    series = _burst_series_from_prices(kalshi, poly)
    out = probe.per_ticker_leadlag(series, min_steps=3, margin=0.05)
    assert len(out) == 1
    row = out[0]
    assert row["rho_kalshi_leads"] == pytest.approx(-1.0)
    assert row["rho_polymarket_leads"] == pytest.approx(-0.7657, abs=1e-3)
    # the OLD signed-argmax would have named polymarket here (it wins the margin test)
    assert row["rho_polymarket_leads"] > row["rho_kalshi_leads"] + 0.05
    assert row["signed_leader"] == "none"


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
