"""Tests for scripts/l338_trend_claim_scope_audit.py — the MEASUREMENT half of L338.

Two layers:
  * synthetic-fixture unit tests over every branch of the join rules, the trend labeller
    and the factorial attribution;
  * REAL-TAPE acceptance tests pinning the load-bearing structural facts. Per L320 these
    pin FLOORS and DIRECTIONS, never equalities — `tape/kalshi_trades/dt=2026-08-03.jsonl`
    is an append-only backfill family that may still grow. The one thing pinned exactly is
    an IDENTITY between two populations, which is a structural property, not a magnitude.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.l338_trend_claim_scope_audit as A  # noqa: E402


# ───────────────────────────────── synthetic fixtures ───────────────────────────────────

def _write(tmp_path: Path, depth_rows, trade_rows, day="2026-01-01"):
    d = tmp_path / "depth"
    t = tmp_path / "trades"
    d.mkdir()
    t.mkdir()
    (d / f"dt={day}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in depth_rows))
    (t / f"dt={day}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in trade_rows))
    return d, t


def _snap(ticker, ts, bid, ask):
    return {"ticker": ticker, "captured_at": ts,
            "best_yes_bid": bid, "best_yes_ask": ask}


def _print(ticker, ts, side, price):
    return {"ticker": ticker, "created_time": ts, "taker_book_side": side,
            "yes_price": price, "price_source_tag": "broker_truth"}


# ───────────────────────────────────── unit tests ───────────────────────────────────────

def test_load_depth_preserves_insertion_order_and_sorts_snapshots(tmp_path):
    d, t = _write(tmp_path, [
        _snap("B", "2026-01-01T01:00:00Z", 0.4, 0.6),
        _snap("A", "2026-01-01T02:00:00Z", 0.4, 0.6),
        _snap("A", "2026-01-01T00:30:00Z", 0.3, 0.5),
    ], [])
    order, snaps = A.load_depth("2026-01-01", d)
    assert order == ["B", "A"], "insertion order is the probe's sampling key — do not sort"
    assert [s["best_yes_bid"] for s in snaps["A"]] == [0.3, 0.4]


def test_load_prints_defaults_an_untagged_price_to_synthetic(tmp_path):
    d, t = _write(tmp_path, [], [
        {"ticker": "A", "created_time": "2026-01-01T00:00:00Z",
         "taker_book_side": "bid", "yes_price": 0.5},
    ])
    prints = A.load_prints("2026-01-01", t)
    assert prints["A"][0]["price_source_tag"] == "synthetic"


def test_bracketed_drops_a_print_after_the_last_snapshot_and_last_preceding_keeps_it(tmp_path):
    """The single condition that separates the two readings of the disputed claim."""
    d, t = _write(tmp_path, [
        _snap("A", "2026-01-01T00:00:00Z", 0.40, 0.60),
        _snap("A", "2026-01-01T00:10:00Z", 0.40, 0.60),
    ], [
        _print("A", "2026-01-01T00:05:00Z", "bid", 0.70),   # inside the pair
        _print("A", "2026-01-01T00:15:00Z", "bid", 0.70),   # after the LAST snapshot
    ])
    order, snaps = A.load_depth("2026-01-01", d)
    prints = A.load_prints("2026-01-01", t)
    assert A.agreement_counts(order, snaps, prints, side="bid",
                              join_rule="bracketed", max_age_s=10 ** 9) == (1, 1)
    assert A.agreement_counts(order, snaps, prints, side="bid",
                              join_rule="last_preceding", max_age_s=10 ** 9) == (2, 2)


def test_a_single_snapshot_ticker_is_unmeasurable_under_bracketed(tmp_path):
    d, t = _write(tmp_path, [_snap("A", "2026-01-01T00:00:00Z", 0.40, 0.60)],
                  [_print("A", "2026-01-01T00:05:00Z", "bid", 0.70)])
    order, snaps = A.load_depth("2026-01-01", d)
    prints = A.load_prints("2026-01-01", t)
    assert A.agreement_counts(order, snaps, prints, side="bid",
                              join_rule="bracketed", max_age_s=10 ** 9) == (0, 0)


def test_max_age_excludes_a_stale_reference_quote(tmp_path):
    d, t = _write(tmp_path, [
        _snap("A", "2026-01-01T00:00:00Z", 0.40, 0.60),
        _snap("A", "2026-01-01T02:00:00Z", 0.40, 0.60),
    ], [_print("A", "2026-01-01T01:00:00Z", "bid", 0.70)])
    order, snaps = A.load_depth("2026-01-01", d)
    prints = A.load_prints("2026-01-01", t)
    assert A.agreement_counts(order, snaps, prints, side="bid",
                              join_rule="bracketed", max_age_s=900) == (0, 0)
    assert A.agreement_counts(order, snaps, prints, side="bid",
                              join_rule="bracketed", max_age_s=10 ** 9) == (1, 1)


def test_orientation_sides_agree_in_opposite_directions(tmp_path):
    d, t = _write(tmp_path, [
        _snap("A", "2026-01-01T00:00:00Z", 0.40, 0.60),
        _snap("A", "2026-01-01T00:10:00Z", 0.40, 0.60),
    ], [
        _print("A", "2026-01-01T00:01:00Z", "bid", 0.60),   # at the ask -> agrees
        _print("A", "2026-01-01T00:02:00Z", "bid", 0.50),   # mid        -> disagrees
        _print("A", "2026-01-01T00:03:00Z", "ask", 0.40),   # at the bid -> agrees
        _print("A", "2026-01-01T00:04:00Z", "ask", 0.50),   # mid        -> disagrees
    ])
    order, snaps = A.load_depth("2026-01-01", d)
    prints = A.load_prints("2026-01-01", t)
    assert A.agreement_counts(order, snaps, prints, side=A.TAKER_BUYS,
                              join_rule="bracketed", max_age_s=10 ** 9) == (1, 2)
    assert A.agreement_counts(order, snaps, prints, side=A.TAKER_SELLS,
                              join_rule="bracketed", max_age_s=10 ** 9) == (1, 2)


def test_a_quote_missing_a_side_is_unmeasurable_never_a_disagreement(tmp_path):
    d, t = _write(tmp_path, [
        _snap("A", "2026-01-01T00:00:00Z", None, 0.60),
        _snap("A", "2026-01-01T00:10:00Z", 0.40, 0.60),
    ], [_print("A", "2026-01-01T00:01:00Z", "bid", 0.70)])
    order, snaps = A.load_depth("2026-01-01", d)
    prints = A.load_prints("2026-01-01", t)
    assert A.agreement_counts(order, snaps, prints, side="bid",
                              join_rule="bracketed", max_age_s=10 ** 9) == (0, 0)


def test_a_ticker_outside_the_universe_contributes_nothing(tmp_path):
    d, t = _write(tmp_path, [
        _snap("A", "2026-01-01T00:00:00Z", 0.40, 0.60),
        _snap("A", "2026-01-01T00:10:00Z", 0.40, 0.60),
    ], [_print("A", "2026-01-01T00:01:00Z", "bid", 0.70)])
    order, snaps = A.load_depth("2026-01-01", d)
    prints = A.load_prints("2026-01-01", t)
    assert A.agreement_counts(["Z"], snaps, prints, side="bid",
                              join_rule="bracketed", max_age_s=10 ** 9) == (0, 0)


def test_unknown_join_rule_raises(tmp_path):
    with pytest.raises(ValueError):
        A.agreement_counts([], {}, {}, side="bid", join_rule="nearest", max_age_s=1)


@pytest.mark.parametrize("rates,label", [
    ([0.9, 0.8, 0.7], "decaying"),
    ([0.6, 0.7, 0.8], "rising"),
    ([0.6, 0.8, 0.7], "non_monotonic"),
    ([0.7, 0.7, 0.7], "non_monotonic"),
    ([0.9, None, 0.7], "non_monotonic"),
    ([0.9], "non_monotonic"),
])
def test_trend_direction_labels(rates, label):
    assert A.trend_direction(rates) == label


def test_an_unmeasurable_cell_can_never_be_read_as_corroboration():
    """A missing measurement must not be labelled `decaying` by omission."""
    assert A.trend_direction([0.9, None, 0.1]) == "non_monotonic"


def _grid(pop_trends, rule_key="bracketed"):
    """Build a minimal grid shell with explicit trend labels per (population, rule)."""
    grid = {}
    for pop, per_rule in pop_trends.items():
        grid[pop] = {}
        for rule, (trend, rates) in per_rule.items():
            grid[pop][rule] = {A.TAKER_BUYS: {
                "trend_direction": trend,
                "agreement_direction": "at_or_above_ask",
                "cells": [{"window_s": w, "window": str(w), "n_admitted_prints": 10,
                           "n_agreeing": 5, "agreement_rate": r}
                          for w, r in zip(A.WINDOWS_S, rates)],
            }}
    return grid


def test_attribution_names_the_join_rule_when_only_it_moves_the_trend():
    grid = _grid({
        "probe_sports_sample": {"bracketed": ("decaying", [0.9, 0.8, 0.7]),
                                "last_preceding": ("rising", [0.6, 0.7, 0.8])},
        "full_depth_day": {"bracketed": ("decaying", [0.9, 0.8, 0.7]),
                           "last_preceding": ("rising", [0.6, 0.7, 0.8])},
    })
    attr = A.attribute_flip(grid)
    assert attr["driver"] == "join_rule"
    assert attr["population_changes_trend"] is False
    assert attr["population_changes_any_rate"] is False
    assert attr["join_rule_changes_trend"] is True


def test_attribution_names_the_population_when_only_it_moves_the_trend():
    grid = _grid({
        "probe_sports_sample": {"bracketed": ("decaying", [0.9, 0.8, 0.7]),
                                "last_preceding": ("decaying", [0.9, 0.8, 0.7])},
        "full_depth_day": {"bracketed": ("rising", [0.6, 0.7, 0.8]),
                           "last_preceding": ("rising", [0.6, 0.7, 0.8])},
    })
    attr = A.attribute_flip(grid)
    assert attr["driver"] == "population"


def test_attribution_reports_both_and_neither():
    both = _grid({
        "probe_sports_sample": {"bracketed": ("decaying", [0.9, 0.8, 0.7]),
                                "last_preceding": ("rising", [0.6, 0.7, 0.8])},
        "full_depth_day": {"bracketed": ("rising", [0.6, 0.7, 0.8]),
                           "last_preceding": ("rising", [0.6, 0.7, 0.8])},
    })
    assert A.attribute_flip(both)["driver"] == "both"
    neither = _grid({
        "probe_sports_sample": {"bracketed": ("decaying", [0.9, 0.8, 0.7]),
                                "last_preceding": ("decaying", [0.9, 0.8, 0.7])},
        "full_depth_day": {"bracketed": ("decaying", [0.9, 0.8, 0.7]),
                           "last_preceding": ("decaying", [0.9, 0.8, 0.7])},
    })
    assert A.attribute_flip(neither)["driver"] == "neither"


def test_attribution_refuses_an_incomplete_grid():
    grid = _grid({"probe_sports_sample": {"bracketed": ("decaying", [0.9, 0.8, 0.7]),
                                          "last_preceding": ("rising", [0.6, 0.7, 0.8])}})
    assert A.attribute_flip(grid)["insufficient_grid"] is True


def test_build_report_runs_end_to_end_on_synthetic_tape(tmp_path):
    d, t = _write(tmp_path, [
        _snap("A", "2026-01-01T00:00:00Z", 0.40, 0.60),
        _snap("A", "2026-01-01T00:10:00Z", 0.40, 0.60),
    ], [_print("A", "2026-01-01T00:01:00Z", "bid", 0.70)])
    rep = A.build_report("2026-01-01", depth_dir=d, trades_dir=t,
                         universes={"probe_sports_sample": ["A"], "full_depth_day": ["A"]})
    assert rep["schema_version"] == "l338_trend_claim_scope.v1"
    assert rep["lesson"] == "L338"
    assert rep["n_depth_tickers"] == 1 and rep["n_print_tickers"] == 1
    assert set(rep["grid"]) == {"probe_sports_sample", "full_depth_day"}
    assert A.format_report(rep)


def test_the_report_carries_no_pnl_or_verdict_keys(tmp_path):
    d, t = _write(tmp_path, [
        _snap("A", "2026-01-01T00:00:00Z", 0.40, 0.60),
        _snap("A", "2026-01-01T00:10:00Z", 0.40, 0.60),
    ], [_print("A", "2026-01-01T00:01:00Z", "bid", 0.70)])
    rep = A.build_report("2026-01-01", depth_dir=d, trades_dir=t,
                         universes={"probe_sports_sample": ["A"], "full_depth_day": ["A"]})
    def keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield str(k).lower()
                yield from keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys(v)

    present = set(keys(rep))
    for forbidden in ("pnl", "p_and_l", "edge_after_fee", "ci_low", "ci_high",
                      "bootstrap", "verdict", "admissible", "ci"):
        assert forbidden not in present, f"a MEASUREMENT must not emit key {forbidden!r}"


def test_main_writes_json(tmp_path, monkeypatch):
    d, t = _write(tmp_path, [
        _snap("A", "2026-01-01T00:00:00Z", 0.40, 0.60),
        _snap("A", "2026-01-01T00:10:00Z", 0.40, 0.60),
    ], [_print("A", "2026-01-01T00:01:00Z", "bid", 0.70)])
    real_build = A.build_report
    monkeypatch.setattr(A, "build_report", lambda day: real_build(
        day, depth_dir=d, trades_dir=t,
        universes={"probe_sports_sample": ["A"], "full_depth_day": ["A"]}))
    out = tmp_path / "r.json"
    assert A.main(["--day", "2026-01-01", "--json", str(out)]) == 0
    assert json.loads(out.read_text())["lesson"] == "L338"


# ──────────────────────────── real-tape acceptance (L320: floors) ───────────────────────

REAL_DEPTH = A.DEPTH_TAPE / f"dt={A.DAY}.jsonl"
REAL_TRADES = A.TRADES_TAPE / f"dt={A.DAY}.jsonl"
_HAVE_TAPE = REAL_DEPTH.exists() and REAL_TRADES.exists()
_real = pytest.mark.skipif(not _HAVE_TAPE, reason="committed 2026-08-03 tape not present")


@pytest.fixture(scope="module")
def real_report():
    if not _HAVE_TAPE:
        pytest.skip("committed 2026-08-03 tape not present")
    return A.build_report()


@_real
def test_acceptance_l338_the_population_factor_moves_nothing(real_report):
    """THE load-bearing correction to L338's stated mechanism.

    L338 attributes the contrary reading to POPULATION scope. Held at a fixed join rule,
    switching the 60-ticker sports sample for all 2,713 depth tickers does not move a
    single admitted-print count or agreement rate on either side. This is an identity, not
    a magnitude, so pinning it exactly is growth-safe: the 4 print-carrying tickers outside
    the probe universe are crypto markets with ONE depth snapshot each and zero prints
    after it, so they are structurally unmeasurable under either rule.
    """
    grid = real_report["grid"]
    assert real_report["universe_sizes"]["probe_sports_sample"] < \
        real_report["universe_sizes"]["full_depth_day"], "the two universes must differ"
    for rule in A.JOIN_RULES:
        for side in (A.TAKER_BUYS, A.TAKER_SELLS):
            a = grid["probe_sports_sample"][rule][side]["cells"]
            b = grid["full_depth_day"][rule][side]["cells"]
            assert a == b, f"population moved a rate at {rule}/{side} — re-derive L338"
    assert real_report["attribution"]["population_changes_any_rate"] is False


@_real
def test_acceptance_l338_the_join_rule_is_the_sole_driver_of_the_direction_flip(real_report):
    """Bid-side: the probe's bracketed join DECAYS; nearest-preceding RISES — on the SAME
    population. This is the fact the disputed corroboration argument actually turns on."""
    grid = real_report["grid"]
    for pop in ("probe_sports_sample", "full_depth_day"):
        assert grid[pop]["bracketed"][A.TAKER_BUYS]["trend_direction"] == "decaying"
        assert grid[pop]["last_preceding"][A.TAKER_BUYS]["trend_direction"] == "rising"
    assert real_report["attribution"]["driver"] == "join_rule"
    assert real_report["attribution"]["join_rule_changes_trend"] is True


@_real
def test_acceptance_both_disputed_rate_series_still_reproduce_within_tolerance(real_report):
    """Floors and tolerances, never equalities (L320): `kalshi_trades` is an append-only
    backfill family and this day-file may still grow."""
    cells = real_report["grid"]["probe_sports_sample"]["bracketed"][A.TAKER_BUYS]["cells"]
    for cell, expect, floor in zip(cells, (0.868, 0.846, 0.704), (100, 400, 2500)):
        assert cell["n_admitted_prints"] >= floor
        assert abs(cell["agreement_rate"] - expect) <= 0.02
    cells = real_report["grid"]["full_depth_day"]["last_preceding"][A.TAKER_BUYS]["cells"]
    for cell, expect, floor in zip(cells, (0.630, 0.669, 0.696), (500, 2000, 25000)):
        assert cell["n_admitted_prints"] >= floor
        assert abs(cell["agreement_rate"] - expect) <= 0.02


@_real
def test_acceptance_the_directional_conclusion_survives_on_every_cell(real_report):
    """What L338 did NOT overturn, pinned so a future run cannot over-read this audit: a
    `bid` taker still prints at/above the ask far more often than not under BOTH joins."""
    grid = real_report["grid"]
    for rule in A.JOIN_RULES:
        for cell in grid["full_depth_day"][rule][A.TAKER_BUYS]["cells"]:
            assert cell["agreement_rate"] > 0.55


@_real
def test_acceptance_the_bracketed_join_discards_most_of_the_print_tape(real_report):
    """WHY the two joins disagree: the probe's bracketing requirement is not a detail —
    it drops the large majority of admissible prints at the any-age window."""
    grid = real_report["grid"]["full_depth_day"]
    bracketed = grid["bracketed"][A.TAKER_BUYS]["cells"][-1]["n_admitted_prints"]
    preceding = grid["last_preceding"][A.TAKER_BUYS]["cells"][-1]["n_admitted_prints"]
    assert preceding >= 4 * bracketed
