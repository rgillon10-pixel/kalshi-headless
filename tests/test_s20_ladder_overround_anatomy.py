"""scripts.s20_ladder_overround_anatomy — Q20 ladder overround anatomy (read-only).
Offline: no network, no tape reads — every fixture is injected/synthetic."""
from __future__ import annotations

import json
import math

import pytest

from scripts import s20_ladder_overround_anatomy as s20
from core.pricing import MAKER_FEE_RATE, fee_per_contract


# --------------------------------------------------------------------------- #
# member geometry
# --------------------------------------------------------------------------- #
def test_member_coord_between_is_midpoint():
    o = {"strike_type": "between", "floor_strike": 63700, "cap_strike": 63799.99}
    assert s20.member_coord(o) == pytest.approx((63700 + 63799.99) / 2.0)


def test_member_coord_edge_uses_available_boundary():
    assert s20.member_coord({"strike_type": "greater", "floor_strike": 73000,
                             "cap_strike": None}) == 73000.0
    assert s20.member_coord({"strike_type": "less", "floor_strike": None,
                             "cap_strike": 55000}) == 55000.0


def test_member_coord_none_when_no_strike():
    assert s20.member_coord({"strike_type": "between", "floor_strike": None,
                             "cap_strike": None}) is None


def test_ladder_spacing_from_between_floors():
    outs = [{"strike_type": "between", "floor_strike": f} for f in (100, 200, 300, 400)]
    assert s20.ladder_spacing(outs) == pytest.approx(100.0)


def test_ladder_spacing_none_below_two_strikes():
    assert s20.ladder_spacing([{"strike_type": "between", "floor_strike": 100}]) is None


# --------------------------------------------------------------------------- #
# bucket classification
# --------------------------------------------------------------------------- #
def _between(floor, cap, ask, bid=0.0):
    return {"strike_type": "between", "floor_strike": floor, "cap_strike": cap,
            "yes_ask": ask, "yes_bid": bid, "ticker": f"T{floor}"}


def test_classify_active_within_band():
    # spot 1000, spacing 100, band_steps 3 -> active if |coord-1000| <= 300
    o = _between(900, 999.99, 0.30)   # mid ~950, dist 50 -> active
    assert s20.classify_bucket(o, spot=1000.0, spacing=100.0, band_steps=3) == "active"


def test_classify_wing_floor_vs_elevated():
    floor_wing = _between(2000, 2099.99, 0.01)   # far + at 1c floor
    elevated_wing = _between(2000, 2099.99, 0.40)  # far + elevated stale ask
    assert s20.classify_bucket(floor_wing, 1000.0, 100.0, 3) == "wing_floor"
    assert s20.classify_bucket(elevated_wing, 1000.0, 100.0, 3) == "wing_elevated"


def test_classify_band_boundary_is_inclusive():
    # coord exactly band_steps*spacing away counts as active (<=)
    o = _between(1300, 1300, 0.05)  # between with equal floor/cap -> mid 1300, dist 300
    assert s20.classify_bucket(o, spot=1000.0, spacing=100.0, band_steps=3) == "active"


def test_classify_no_spacing_falls_back_to_ask_split():
    # no derivable spacing -> never dropped; split by ask alone
    floorish = _between(2000, 2099.99, 0.01)
    elevated = _between(2000, 2099.99, 0.40)
    assert s20.classify_bucket(floorish, 1000.0, None, 3) == "wing_floor"
    assert s20.classify_bucket(elevated, 1000.0, None, 3) == "wing_elevated"


# --------------------------------------------------------------------------- #
# decomposition arithmetic
# --------------------------------------------------------------------------- #
def test_decompose_partitions_bracket_sum_exactly():
    # a tiny ladder: 2 active near spot 1000, 1 floor wing, 1 elevated wing
    outs = [
        _between(950, 1049.99, 0.55, 0.50),   # active, mid 1000
        _between(1050, 1149.99, 0.45, 0.40),  # active, mid 1100 (dist 100)
        _between(3000, 3099.99, 0.01, 0.0),   # wing_floor
        _between(3100, 3199.99, 0.30, 0.0),   # wing_elevated
    ]
    d = s20.decompose_snapshot(outs, spot=1000.0, band_steps=3)
    # buckets sum back to bracket_sum
    total = d["sums"]["active"] + d["sums"]["wing_floor"] + d["sums"]["wing_elevated"]
    assert total == pytest.approx(d["bracket_sum"])
    assert d["bracket_sum"] == pytest.approx(0.55 + 0.45 + 0.01 + 0.30)
    assert d["sums"]["active"] == pytest.approx(1.00)
    assert d["sums"]["wing_floor"] == pytest.approx(0.01)
    assert d["sums"]["wing_elevated"] == pytest.approx(0.30)
    assert d["counts"] == {"active": 2, "wing_floor": 1, "wing_elevated": 1}


def test_decompose_active_over_1_after_fees_uses_maker_fee():
    outs = [
        _between(950, 1049.99, 0.55, 0.50),
        _between(1050, 1149.99, 0.45, 0.40),
    ]
    d = s20.decompose_snapshot(outs, spot=1000.0, band_steps=3)
    expected_fee = fee_per_contract(0.55, rate=MAKER_FEE_RATE) + fee_per_contract(0.45, rate=MAKER_FEE_RATE)
    assert d["active_maker_fee"] == pytest.approx(expected_fee)
    assert d["active_over_1_after_fees"] == pytest.approx(1.00 - 1.0 - expected_fee)
    # capturable half-spread = sum(ask) - sum(mid) - fees
    mid_sum = (0.55 + 0.50) / 2 + (0.45 + 0.40) / 2
    assert d["active_halfspread_after_fees"] == pytest.approx(1.00 - mid_sum - expected_fee)


def test_decompose_frac_overround_in_wings():
    # dense 100-spaced ladder so infer_strike_spacing == 100 (a sparse fixture would infer a
    # huge median gap and mis-bucket the wings as active)
    outs = [
        _between(900, 999.99, 0.05),    # active
        _between(1000, 1099.99, 0.50),  # active
        _between(1100, 1199.99, 0.05),  # active
        _between(2000, 2099.99, 0.01),  # wing_floor (dist ~1050 > 300)
        _between(2100, 2199.99, 0.60),  # wing_elevated
    ]
    d = s20.decompose_snapshot(outs, spot=1000.0, band_steps=3)
    assert d["spacing"] == pytest.approx(100.0)
    # bracket_sum 1.21, overround 0.21, wings = 0.61
    assert d["overround"] == pytest.approx(0.21)
    assert d["wing_sum"] == pytest.approx(0.61)
    assert d["counts"] == {"active": 3, "wing_floor": 1, "wing_elevated": 1}
    assert d["frac_overround_in_wings"] == pytest.approx(0.61 / 0.21)


# --------------------------------------------------------------------------- #
# depth mirror + join
# --------------------------------------------------------------------------- #
def test_ask_side_depth_is_top_no_bid_size():
    rec = {"best_yes_ask": 0.01, "best_no_bid": 0.99,
           "no_bids": [[0.99, 46967.0], [0.95, 350.0]], "yes_bids": []}
    assert s20._ask_side_depth(rec) == pytest.approx(46967.0)


def test_ask_side_depth_zero_on_empty_no_bids():
    # a genuinely one-sided wing (L23 empty != drop): no resting offer -> depth 0
    assert s20._ask_side_depth({"no_bids": []}) == 0.0
    assert s20._ask_side_depth({}) == 0.0


def _depth_index():
    # ticker T900 has two captures ~10s apart; T950 has one far in time
    base = 1_000_000.0
    return {
        "T900": [(base, 0.30, 100.0), (base + 10, 0.31, 120.0)],
        "T3000": [(base + 5, 0.01, 50000.0)],
    }


def test_nearest_depth_picks_closest_in_time():
    idx = _depth_index()
    # ts just after base -> closer to the base capture
    hit = s20.nearest_depth(idx, "T900", 1_000_002.0, max_delta_sec=600)
    assert hit == (0.30, 100.0)
    hit2 = s20.nearest_depth(idx, "T900", 1_000_009.0, max_delta_sec=600)
    assert hit2 == (0.31, 120.0)


def test_nearest_depth_none_outside_window():
    idx = _depth_index()
    assert s20.nearest_depth(idx, "T900", 1_000_000.0 + 5000, max_delta_sec=600) is None
    assert s20.nearest_depth(idx, "MISSING", 1_000_000.0, max_delta_sec=600) is None


def test_build_depth_index_from_files(tmp_path):
    d = tmp_path / "orderbook_depth"
    d.mkdir()
    recs = [
        {"ticker": "KXBTC-X-B1", "captured_at": "2026-07-12T00:00:00+00:00",
         "best_yes_ask": 0.01, "no_bids": [[0.99, 12345.0]]},
        {"ticker": "KXETH-X-B2", "captured_at": "2026-07-12T00:00:05+00:00",
         "best_yes_ask": 0.40, "no_bids": [[0.60, 10.0]]},
        {"ticker": "KXMLBGAME-X", "captured_at": "2026-07-12T00:00:00+00:00",
         "best_yes_ask": 0.50, "no_bids": [[0.50, 1.0]]},  # filtered out by prefix
    ]
    with open(d / "dt=2026-07-12.jsonl", "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    idx = s20.build_depth_index(d, ticker_prefixes=("KXBTC", "KXETH"))
    assert set(idx) == {"KXBTC-X-B1", "KXETH-X-B2"}
    assert idx["KXBTC-X-B1"][0][2] == pytest.approx(12345.0)


def test_build_depth_index_skips_stray_directory(tmp_path):
    # a dt=<date> DIRECTORY (the L25/L29 regression) must be skipped, not crash
    d = tmp_path / "orderbook_depth"
    d.mkdir()
    (d / "dt=2026-07-10").mkdir()  # stray directory
    with open(d / "dt=2026-07-12.jsonl", "w") as f:
        f.write(json.dumps({"ticker": "KXBTC-X", "captured_at": "2026-07-12T00:00:00+00:00",
                            "best_yes_ask": 0.01, "no_bids": [[0.99, 1.0]]}) + "\n")
    idx = s20.build_depth_index(d, ticker_prefixes=("KXBTC",))
    assert set(idx) == {"KXBTC-X"}


def test_join_depth_by_bucket_accumulates_into_right_bucket():
    # dense 100-spaced ladder; only A (active, mid 1000) and W (wing_floor) carry a depth entry
    snap = {
        "captured_at": "2026-07-12T00:00:02+00:00", "spot": 1000.0,
        "outcomes": [
            {**_between(900, 999.99, 0.05), "ticker": "A0"},   # active, no depth entry
            {**_between(1000, 1099.99, 0.50), "ticker": "A"},  # active, matched
            {**_between(1100, 1199.99, 0.05), "ticker": "A2"},  # active, no depth entry
            {**_between(2000, 2099.99, 0.01), "ticker": "W"},  # wing_floor, matched
        ],
    }
    ts = s20._parse_ts("2026-07-12T00:00:02+00:00")
    idx = {"A": [(ts, 0.50, 400.0)], "W": [(ts, 0.01, 50000.0)]}
    agg = s20.join_depth_by_bucket([snap], idx, band_steps=3)
    assert agg["active"]["n_members"] == 3
    assert agg["active"]["n_matched"] == 1
    assert agg["active"]["depths"] == [400.0]
    assert agg["wing_floor"]["n_matched"] == 1
    assert agg["wing_floor"]["depths"] == [50000.0]
    assert agg["wing_elevated"]["n_members"] == 0


# --------------------------------------------------------------------------- #
# per-series summary + bootstrap unit (L6 by event-hour)
# --------------------------------------------------------------------------- #
def _snap(event_ticker, spot, outs):
    return {"event_ticker": event_ticker, "series": "KXBTC", "captured_at":
            "2026-07-12T00:00:00+00:00", "spot": spot, "outcomes": outs}


def test_summarize_series_groups_bootstrap_by_event_hour():
    # two event-hours, two snapshots each -> bootstrap unit count == 2, not 4 (L6)
    outs = [_between(950, 1049.99, 0.60, 0.50), _between(1050, 1149.99, 0.50, 0.40)]
    snaps = [_snap("E1", 1000.0, outs), _snap("E1", 1000.0, outs),
             _snap("E2", 1000.0, outs), _snap("E2", 1000.0, outs)]
    summ = s20.summarize_series(snaps, band_steps=3, n_boot=200)
    assert summ["n_snapshots"] == 4
    assert summ["n_event_hours"] == 2
    assert summ["active_over_1_after_fees"]["n_units"] == 2


def test_summarize_series_empty_is_safe():
    assert s20.summarize_series([], n_boot=10)["n_snapshots"] == 0


def test_median_and_frac_positive_helpers():
    assert s20._median([3.0, 1.0, 2.0]) == 2.0
    assert s20._median([4.0, 1.0, 2.0, 3.0]) == 2.5
    assert math.isnan(s20._median([]))
    assert s20._frac_positive([0.0, 1.0, 2.0]) == pytest.approx(2 / 3)
    assert math.isnan(s20._frac_positive([]))
