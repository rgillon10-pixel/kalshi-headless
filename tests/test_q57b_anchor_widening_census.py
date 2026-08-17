"""Tests for `scripts/q57b_anchor_widening_census.py` (Q57 reopen path (b)).

Three classes of test here, and they are doing different jobs:

  * STRUCTURAL — the module is outcome-blind BY AST, not by promise, and its sealed
    pre-registration hash cannot drift silently.
  * UNIT — every rule the census adds (union precedence, cache aggregation, rewrite
    invariance, lag profile, mechanism-faithfulness) is exercised on fixtures, including
    fixtures where the check FIRES. A check that only ever returns "clean" on real tape is
    indistinguishable from a check that cannot fire at all.
  * ACCEPTANCE — the finding's headline numbers, re-derived over an explicitly FROZEN slice
    of the committed tape (L191), so an append-only tape cannot quietly rot the pin.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from scripts import q57b_anchor_widening_census as C

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "scripts" / "q57b_anchor_widening_census.py"

# The exact numbers published in
# `findings/2026-08-17-q57b-anchor-widening-census.md`. If a future tape moves one of
# these the FINDING is stale and must be re-derived — do NOT relax the pin. They are
# measured over the frozen slice built by `frozen_tape` below, so ordinary append-only
# growth cannot move them.
EXPECT = {
    "n_game_tickers": 87,
    "n_games": 72,
    "n_settled_binary": 81,
    "n_ledger_close_times": 49,
    "n_cache_close_times": 38,
    "n_anchor_overlap": 0,
    "baseline_units": 11,
    "baseline_sides": {"no": 11},
    "primary_units": 11,
    "primary_sides": {"no": 11},
    "n_close_time_rewritten": 27,
    "entry_snapshot_identical": 38,
    "ledger_within_60min": 37,
    "cache_within_60min": 5,
    "grid_n_cells": 1280,
    "grid_n_meeting_unit_floor": 976,
    "grid_n_admissible": 36,
    "grid_n_admissible_mechanism_faithful": 0,
    "grid_admissible_min_lag": 180,
    "grid_admissible_windows": [15],
}


# --------------------------------------------------------------------------- #
# STRUCTURAL
# --------------------------------------------------------------------------- #
def _imported_names(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods, names = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
            for a in node.names:
                names.add(a.name)
    return mods, names


def test_census_is_outcome_blind_by_ast():
    """It may learn WHICH tickers settled; it must never learn HOW."""
    mods, names = _imported_names(MODULE)
    forbidden = {"outcome_map", "score_rows", "binary_outcome", "unit_values",
                 "block_bootstrap", "bootstrap_verdict_admissible"}
    assert not (names & forbidden), f"outcome-value reader imported: {names & forbidden}"
    src = MODULE.read_text(encoding="utf-8")
    for token in ("outcome_map(", "score_rows(", "binary_outcome("):
        assert token not in src, f"{token} referenced in an outcome-blind module"


def test_preregistration_hash_is_sealed():
    """A spec edit after counting is tuning, not a bug fix. This failing IS the alarm."""
    assert C.PREREG_SHA256 == C.preregistration_sha256()
    assert C.PREREG_SHA256 == (
        "9ce0cf1140a26c8e8a812c9d3a2248d5c5ae0a98ad0aa655318eec2ddca964e9")


def test_seal_inherits_q57_constants_rather_than_retyping_them():
    from scripts.q57_s82_flow_fade_probe import PREREGISTRATION as Q57
    for k in ("flow_window_minutes", "max_entry_lag_minutes", "min_abs_rho",
              "min_window_count", "entry_price_band", "min_units", "direction",
              "entry_instant_rule", "entry_price_source_tag"):
        assert C.PREREGISTRATION[k] == Q57[k], k
    assert C.PREREGISTRATION["inherited_sha256"]


def test_the_two_declared_deltas_are_the_only_ones_and_D2_is_stricter():
    from scripts.q57_s82_flow_fade_probe import PREREGISTRATION as Q57
    assert C.PREREGISTRATION["close_anchor"] != Q57["close_anchor"]
    assert C.PREREGISTRATION["min_exclusive_minority_units"] == 2
    assert Q57["min_exclusive_minority_units"] == 1
    assert C.PREREGISTRATION["min_exclusive_minority_units"] > Q57["min_exclusive_minority_units"]


# --------------------------------------------------------------------------- #
# UNIT
# --------------------------------------------------------------------------- #
def test_cache_aggregation_rule_must_be_pre_registered():
    with pytest.raises(ValueError):
        C.cache_close_epochs({"T": {"f.json": "2026-07-01T00:00:00Z"}}, "median")


def test_cache_aggregation_min_and_max_pick_the_declared_ends():
    per = {"T": {"a.json": "2026-07-01T00:00:00Z", "b.json": "2026-07-01T02:00:00Z"}}
    assert C.cache_close_epochs(per, "max")["T"] - C.cache_close_epochs(per, "min")["T"] == 7200.0


def test_union_precedence_gives_the_ledger_the_overlap():
    """Never exercised on committed tape (the two sets are disjoint), so it is exercised here."""
    u, info = C.union_close_times({"A": 100.0}, {"A": 999.0, "B": 5.0})
    assert u == {"A": 100.0, "B": 5.0}
    assert info["n_both"] == 1 and info["precedence_rule_exercised"] is True
    assert info["n_ledger_only"] == 0 and info["n_cache_only"] == 1


def test_rewrite_invariance_FIRES_when_the_rewrite_moves_the_entry_snapshot():
    """Proves the real-tape `False` is a measurement, not a vacuous pass."""
    per = {"T": {"a.json": "2026-07-01T00:00:00Z", "b.json": "2026-07-01T05:00:00Z"}}
    depth = {"T": [{"ts": C.parse_iso_utc("2026-06-30T23:00:00Z").timestamp()},
                   {"ts": C.parse_iso_utc("2026-07-01T03:00:00Z").timestamp()}]}
    out = C.anchor_rewrite_invariance(per, depth)
    assert out["n_close_time_rewritten"] == 1
    assert out["entry_snapshot_differs"] == 1
    assert out["rewrite_is_binding_on_entry_instant"] is True


def test_rewrite_invariance_reports_non_binding_when_the_same_snapshot_wins():
    per = {"T": {"a.json": "2026-07-01T00:00:00Z", "b.json": "2026-07-01T05:00:00Z"}}
    depth = {"T": [{"ts": C.parse_iso_utc("2026-06-30T23:00:00Z").timestamp()}]}
    out = C.anchor_rewrite_invariance(per, depth)
    assert out["n_close_time_rewritten"] == 1
    assert out["entry_snapshot_identical_under_min_and_max_rule"] == 1
    assert out["rewrite_is_binding_on_entry_instant"] is False


def test_entry_lag_profile_separates_close_time_coverage_from_depth_coverage():
    t0 = C.parse_iso_utc("2026-07-01T12:00:00Z").timestamp()
    closes = {"A": t0, "B": t0, "C": t0}
    depth = {"A": [{"ts": t0 - 600.0}],          # 10 min  -> inside the 60-min budget
             "B": [{"ts": t0 - 7200.0}],         # 120 min -> outside
             }                                    # C has no depth at all
    out = C.entry_lag_profile(closes, depth, "fixture")
    assert out["n_tickers_with_close_time"] == 3
    assert out["n_without_pre_close_depth_snapshot"] == 1
    assert out["n_with_pre_close_depth_snapshot"] == 2
    assert out["n_within_inherited_lag_budget"] == 1


def test_mechanism_faithfulness_is_pinned_to_the_inherited_lag_budget():
    assert C.INHERITED_LAG_MINUTES == 60.0
    assert C.PREREGISTRATION["max_entry_lag_minutes"] == 60


# --------------------------------------------------------------------------- #
# ACCEPTANCE — over an explicitly FROZEN slice of committed tape (L191)
# --------------------------------------------------------------------------- #
FREEZE_DT = "dt=2026-08-16"


@pytest.fixture(scope="module")
def frozen_tape(tmp_path_factory):
    """Symlink every tape day-file that exists at or before the freeze date.

    Without this the pins below would be hostage to tomorrow's collector pass. With it they
    measure exactly the corpus the finding was written against."""
    root = tmp_path_factory.mktemp("frozen")
    spec = {
        "kalshi_trades": ("dt=*.jsonl", True),
        "orderbook_depth": ("dt=*.jsonl", True),
        "settlement_ledger": ("dt=*.jsonl", True),
        "q51_settlement_cache": ("*.json", False),
    }
    for family, (pat, dated) in spec.items():
        dst = root / family
        dst.mkdir(parents=True)
        for src in sorted((REPO / "tape" / family).glob(pat)):
            if dated and src.name[: len(FREEZE_DT)] > FREEZE_DT:
                continue
            os.symlink(src, dst / src.name)
    return root


@pytest.fixture(scope="module")
def frozen_report(frozen_tape):
    return C.run(trades_dir=frozen_tape / "kalshi_trades",
                 depth_dir=frozen_tape / "orderbook_depth",
                 ledger_dir=frozen_tape / "settlement_ledger",
                 cache_dir=frozen_tape / "q51_settlement_cache")


def test_acceptance_substrate(frozen_report):
    s = frozen_report["substrate"]
    assert s["n_game_tickers"] == EXPECT["n_game_tickers"]
    assert s["n_games"] == EXPECT["n_games"]
    assert s["n_settled_binary"] == EXPECT["n_settled_binary"]
    assert s["n_ledger_close_times"] == EXPECT["n_ledger_close_times"]
    assert s["cache"]["n_tickers_with_close_time"] == EXPECT["n_cache_close_times"]
    assert s["union"]["min"]["n_both"] == EXPECT["n_anchor_overlap"]


def test_acceptance_the_widening_adds_no_units_at_the_sealed_spec(frozen_report):
    """THE headline. Q57's reopen path (b), executed as a single change, is a no-op."""
    b, p = frozen_report["baseline_ledger_only"], frozen_report["primary"]
    assert b["n_game_units"] == EXPECT["baseline_units"]
    assert b["units_per_side"] == EXPECT["baseline_sides"]
    assert p["n_game_units"] == EXPECT["primary_units"]
    assert p["units_per_side"] == EXPECT["primary_sides"]
    assert frozen_report["widening_is_a_noop_at_the_sealed_spec"] is True
    assert p["admissible"] is False
    assert p["sign_variation_admissible"] is False


def test_acceptance_why_the_widening_is_a_noop_is_the_lag_profile(frozen_report):
    lp = frozen_report["entry_lag_profile"]
    assert lp["settlement_ledger"]["n_within_inherited_lag_budget"] == EXPECT["ledger_within_60min"]
    assert lp["q51_settlement_cache"]["n_within_inherited_lag_budget"] == EXPECT["cache_within_60min"]
    # the cache widens the close-time population but not the depth-covered one
    assert (lp["q51_settlement_cache"]["entry_lag_minutes"]["p50"]
            > lp["settlement_ledger"]["entry_lag_minutes"]["p50"])


def test_acceptance_anchor_rewrite_is_real_but_non_binding_here(frozen_report):
    a = frozen_report["anchor_rewrite_invariance"]
    assert a["n_close_time_rewritten"] == EXPECT["n_close_time_rewritten"]
    assert a["entry_snapshot_identical_under_min_and_max_rule"] == EXPECT["entry_snapshot_identical"]
    assert a["entry_snapshot_differs"] == 0
    assert a["rewrite_is_binding_on_entry_instant"] is False


def test_acceptance_grid_finds_no_mechanism_faithful_admissible_cell(frozen_report):
    g = frozen_report["grid"]
    assert g["n_cells"] == EXPECT["grid_n_cells"]
    assert g["n_meeting_unit_floor"] == EXPECT["grid_n_meeting_unit_floor"]
    assert g["n_admissible"] == EXPECT["grid_n_admissible"]
    assert g["n_admissible_and_mechanism_faithful"] == EXPECT["grid_n_admissible_mechanism_faithful"]
    assert g["admissible_min_lag_minutes"] == EXPECT["grid_admissible_min_lag"]
    assert g["admissible_windows_used"] == EXPECT["grid_admissible_windows"]
    # every admissible cell buys its sign variation with a staler book, not with data
    assert all(c["max_entry_lag_minutes"] > 60 for c in g["admissible_cells"])


def test_acceptance_path_a_is_short_on_BOTH_floors_and_the_scarce_arm_is_named(frozen_report):
    """Q57's path (a) is written as 'one more settled game'. It is short on both floors, and
    the binding shortage is the MINORITY arm — the one that arrives ~1 per 45 observations."""
    pa = frozen_report["path_a_cost"]
    led = pa["settlement_ledger_only"]
    assert led["n_game_units"] == 9
    assert led["units_per_side"] == {"no": 8, "yes": 1}
    assert led["meets_unit_floor"] is False
    assert led["n_exclusive_minority_units"] == 1
    assert led["sign_variation_admissible"] is False
    assert pa["units_short_of_L41_floor"] == 1
    assert pa["minority_units_short_of_floor"] == 1
    # F1's no-op holds at this cell too: widening the anchor changes nothing here either
    assert pa["union_cache_min"] == led


def test_acceptance_disposition(frozen_report):
    assert frozen_report["disposition"] == "PATH_B_CLOSED_DATA_ADEQUACY"
    assert frozen_report["outcome_blind"] is True
    assert "No CI" in frozen_report["verdict_class"]
