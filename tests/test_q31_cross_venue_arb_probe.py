"""Offline tests for Q31 cross-venue arb probe: the new Polymarket fee piece + the
two-legged pricing/join/frozen/persistence logic. No network, no tape dependency."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from core.pricing import (
    POLYMARKET_US_TAKER_RATE,
    TAKER_FEE_RATE,
    fee_per_contract,
    polymarket_fee_per_contract,
)
from scripts.q31_cross_venue_arb_probe import (
    frozen_flags_and_values,
    load_observations,
    net_edges_by_pair,
    persistence_stats,
    run,
    two_legged_arb_edge,
)


# --------------------------------------------------------------------------- #
# Polymarket fee constant/function (new core.pricing piece)
# --------------------------------------------------------------------------- #
def test_polymarket_rate_constant_value():
    assert POLYMARKET_US_TAKER_RATE == 0.05


def test_polymarket_fee_matches_published_cap_at_50c():
    # Published cap ~$1.25 / 100 contracts @ 50c == 0.0125/contract, un-rounded.
    assert polymarket_fee_per_contract(0.50) == pytest.approx(0.0125)


def test_polymarket_fee_is_p_times_1_minus_p_shape():
    for p in (0.1, 0.267, 0.5, 0.73, 0.9):
        assert polymarket_fee_per_contract(p) == pytest.approx(POLYMARKET_US_TAKER_RATE * p * (1 - p))


def test_polymarket_fee_zero_rate_is_zero():
    # intl geopolitics/econ fee-free sensitivity
    assert polymarket_fee_per_contract(0.42, rate=0.0) == 0.0


def test_polymarket_fee_no_cent_roundup_unlike_kalshi():
    # Kalshi ceils to a whole cent; Polymarket does not -- they must differ at 50c.
    assert fee_per_contract(0.50, TAKER_FEE_RATE) == pytest.approx(0.02)
    assert polymarket_fee_per_contract(0.50) == pytest.approx(0.0125)
    assert polymarket_fee_per_contract(0.50) != fee_per_contract(0.50, TAKER_FEE_RATE)


# --------------------------------------------------------------------------- #
# two_legged_arb_edge
# --------------------------------------------------------------------------- #
def test_two_legged_edge_parity_is_negative_after_fees():
    # near-parity: pm YES 0.26 + kalshi NO 0.75 = 1.01 gross > 1 -> already dead pre-fee
    e = two_legged_arb_edge(0.26, 0.75)
    assert e["gross_cost"] == pytest.approx(1.01)
    assert e["gross_edge"] < 0
    assert e["net_edge"] < e["gross_edge"]  # fees only make it worse


def test_two_legged_edge_transient_dislocation_can_be_positive():
    # a genuine cheap-YES/dear-NO dislocation: pm 0.267 + kalshi NO 0.52 = 0.787
    e = two_legged_arb_edge(0.267, 0.52)
    assert e["gross_edge"] == pytest.approx(1.0 - 0.787)
    expect_net = 1.0 - 0.787 - polymarket_fee_per_contract(0.267) - fee_per_contract(0.52)
    assert e["net_edge"] == pytest.approx(expect_net)
    assert e["net_edge"] > 0  # this specific dislocation clears even after both fees


def test_two_legged_edge_uses_both_fee_models():
    e = two_legged_arb_edge(0.3, 0.6, pm_rate=0.05)
    assert e["pm_fee"] == pytest.approx(polymarket_fee_per_contract(0.3, 0.05))
    assert e["kalshi_fee"] == pytest.approx(fee_per_contract(0.6, TAKER_FEE_RATE))
    assert e["net_cost"] == pytest.approx(0.3 + 0.6 + e["pm_fee"] + e["kalshi_fee"])


def test_two_legged_edge_fee_free_pm_rate():
    e = two_legged_arb_edge(0.3, 0.6, pm_rate=0.0)
    assert e["pm_fee"] == 0.0


# --------------------------------------------------------------------------- #
# load / join over synthetic tape
# --------------------------------------------------------------------------- #
def _rec(schema, ticker, no_ask, best_ask, captured_at, book_ok=True):
    return {
        "schema_version": schema,
        "captured_at": captured_at,
        # yes_ask intentionally omitted -- the probe reads only kalshi NO + polymarket YES;
        # computing it here would be Hard-Rule-#3 ask arithmetic the invariant (rightly) blocks.
        "kalshi": {"ticker": ticker, "no_ask": no_ask, "price_source_tag": "real_ask"},
        "polymarket": {"best_ask": best_ask, "best_bid": (best_ask - 0.002 if best_ask else None),
                       "book_fetch_ok": book_ok, "price_source_tag": "real_ask"},
        "price_gap_yes_ask": None,
    }


def _write_tape(tmp_path: Path, name: str, recs) -> str:
    import json
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    f = d / "dt=2026-07-11.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return str(d / "dt=*.jsonl")


def test_load_skips_missing_and_failed_legs(tmp_path):
    recs = [
        _rec("polymarket_pairs.v1", "KXWCROUND-26SEMI-SUI", 0.75, 0.26, "2026-07-11T00:00:00Z"),
        _rec("polymarket_pairs.v1", "KXWCROUND-26SEMI-USA", 0.60, None, "2026-07-11T00:00:00Z"),
        _rec("polymarket_pairs.v1", "KXWCROUND-26SEMI-ARG", 0.50, 0.40, "2026-07-11T00:00:00Z",
             book_ok=False),
    ]
    g = _write_tape(tmp_path, "polymarket_pairs", recs)
    obs = load_observations(wc_glob=g, fed_glob=str(tmp_path / "none" / "dt=*.jsonl"))
    assert len(obs) == 1
    assert getattr(load_observations, "_n_skipped") == 2
    assert obs[0]["ticker"] == "KXWCROUND-26SEMI-SUI"


def test_load_excludes_non_equivalent_schema(tmp_path):
    # a stray synthetic-leg CPI-shaped record must never enter the population
    recs = [_rec("polymarket_cpi_pairs.v1", "KXCPI-26JUL", 0.5, 0.4, "2026-07-11T00:00:00Z")]
    g = _write_tape(tmp_path, "polymarket_cpi_pairs", recs)
    obs = load_observations(wc_glob=g, fed_glob=str(tmp_path / "none" / "dt=*.jsonl"))
    assert obs == []


def test_net_edges_by_pair_clusters_by_ticker(tmp_path):
    recs = [
        _rec("polymarket_pairs.v1", "KXWCROUND-26SEMI-SUI", 0.75, 0.26, "2026-07-11T00:00:00Z"),
        _rec("polymarket_pairs.v1", "KXWCROUND-26SEMI-SUI", 0.74, 0.27, "2026-07-11T01:00:00Z"),
        _rec("polymarket_pairs.v1", "KXWCROUND-26SEMI-USA", 0.60, 0.35, "2026-07-11T00:00:00Z"),
    ]
    g = _write_tape(tmp_path, "polymarket_pairs", recs)
    obs = load_observations(wc_glob=g, fed_glob=str(tmp_path / "none" / "dt=*.jsonl"))
    by_pair = net_edges_by_pair(obs)
    assert len(by_pair) == 2
    assert len(by_pair["wc_round:KXWCROUND-26SEMI-SUI"]) == 2
    assert len(by_pair["wc_round:KXWCROUND-26SEMI-USA"]) == 1


# --------------------------------------------------------------------------- #
# frozen / movement logic (L32)
# --------------------------------------------------------------------------- #
def test_frozen_flags_first_obs_frozen_then_move_detection():
    obs = [
        {"pair_key": "p", "captured_at": "t1", "k_no_ask": 0.75, "pm_yes_ask": 0.26, "net_edge": -0.01},
        {"pair_key": "p", "captured_at": "t2", "k_no_ask": 0.75, "pm_yes_ask": 0.26, "net_edge": -0.01},
        {"pair_key": "p", "captured_at": "t3", "k_no_ask": 0.74, "pm_yes_ask": 0.26, "net_edge": 0.00},
    ]
    flags, values, moved_by_pair = frozen_flags_and_values(obs)
    assert flags == [True, True, False]  # first frozen, second unchanged, third moved
    assert values == [-0.01, -0.01, 0.00]
    assert moved_by_pair["p"] == [0.00]


def test_frozen_flags_sorts_within_pair_by_time():
    # out-of-order input must be sorted by captured_at before movement diffing
    obs = [
        {"pair_key": "p", "captured_at": "t2", "k_no_ask": 0.70, "pm_yes_ask": 0.30, "net_edge": 0.0},
        {"pair_key": "p", "captured_at": "t1", "k_no_ask": 0.75, "pm_yes_ask": 0.26, "net_edge": -0.01},
    ]
    flags, values, _ = frozen_flags_and_values(obs)
    assert flags[0] is True and values[0] == -0.01   # t1 came first after sort


# --------------------------------------------------------------------------- #
# persistence
# --------------------------------------------------------------------------- #
def test_persistence_distinguishes_frozen_from_moved():
    obs = [
        # pair A: net>0 then frozen (unchanged) still net>0  -> a NO-FILL persistence
        {"pair_key": "A", "captured_at": "t1", "k_no_ask": 0.50, "pm_yes_ask": 0.40, "net_edge": 0.05},
        {"pair_key": "A", "captured_at": "t2", "k_no_ask": 0.50, "pm_yes_ask": 0.40, "net_edge": 0.05},
        # pair B: net>0 then MOVED to net<0 -> did NOT survive under movement
        {"pair_key": "B", "captured_at": "t1", "k_no_ask": 0.50, "pm_yes_ask": 0.40, "net_edge": 0.05},
        {"pair_key": "B", "captured_at": "t2", "k_no_ask": 0.55, "pm_yes_ask": 0.44, "net_edge": -0.02},
    ]
    p = persistence_stats(obs)
    assert p["n_consecutive_pairs"] == 2
    assert p["n_frozen_pairs"] == 1
    assert p["n_pos_with_next"] == 2
    assert p["frac_pos_persist_inclusive"] == pytest.approx(0.5)  # A survives, B does not
    assert p["n_pos_moved_with_next"] == 1  # only B moved
    assert p["frac_pos_persist_moved"] == pytest.approx(0.0)  # and B did not survive


# --------------------------------------------------------------------------- #
# end-to-end run over synthetic tape: DEAD when parity holds
# --------------------------------------------------------------------------- #
def test_run_parity_population_is_dead(tmp_path):
    # 12 pairs all near-parity (sum slightly > 1) across two captures each -> mean net < 0
    recs = []
    for i in range(12):
        t = f"KXWCROUND-26SEMI-T{i:02d}"
        recs.append(_rec("polymarket_pairs.v1", t, 0.75, 0.26, "2026-07-11T00:00:00Z"))
        recs.append(_rec("polymarket_pairs.v1", t, 0.74, 0.27, "2026-07-11T01:00:00Z"))
    g = _write_tape(tmp_path, "polymarket_pairs", recs)
    s = run(wc_glob=g, fed_glob=str(tmp_path / "none" / "dt=*.jsonl"), n_boot=500)
    assert s["n_pairs"] == 12
    assert s["pooled_mean_net_edge"] < 0
    assert s["n_pairs_positive_mean"] == 0
    assert s["verdict_positive"] is False
    assert s["boot_primary"]["ci95"][1] < 0  # even the upper CI bound is below zero


def test_run_reports_provenance_tag(tmp_path):
    recs = [_rec("polymarket_pairs.v1", "KXWCROUND-26SEMI-SUI", 0.75, 0.26, "2026-07-11T00:00:00Z")]
    g = _write_tape(tmp_path, "polymarket_pairs", recs)
    s = run(wc_glob=g, fed_glob=str(tmp_path / "none" / "dt=*.jsonl"), n_boot=100)
    assert s["price_source_tag"] == "real_ask"
    assert s["pm_rate"] == POLYMARKET_US_TAKER_RATE
