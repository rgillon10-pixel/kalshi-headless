"""Tests for `scripts/q57b_rederive.py` — the redundancy leg.

The value of this module is ENTIRELY in its independence, so that is what is tested hardest.
A re-derivation that quietly imports the thing it is checking proves nothing, and the failure
mode is invisible at runtime (the numbers would agree perfectly).
"""
from __future__ import annotations

import ast
from pathlib import Path

from scripts import q57b_rederive as R

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "scripts" / "q57b_rederive.py"

FORBIDDEN_MODULES = {
    "scripts.q57b_anchor_widening_census",
    "scripts.q57_s82_flow_fade_probe",
    "scripts.q57_s82_rederive",
    "core.bootstrap",
    "core.settlement_sources",
    "core.settlement",
    "core.timeutil",
    "core.pricing",
    "core.markets",
    "core.io",
}


def test_rederivation_shares_no_code_with_what_it_checks():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
    leaked = {m for m in mods if any(m == f or m.startswith(f + ".") for f in FORBIDDEN_MODULES)}
    assert not leaked, f"redundancy leg imports what it is checking: {leaked}"


def test_it_parses_iso_without_the_shared_parser():
    assert R.epoch("2026-07-01T00:00:00Z") == 1782864000.0
    assert R.epoch("2026-07-01T00:00:30.5Z") - R.epoch("2026-07-01T00:00:00Z") == 30.5
    # agrees with the repo parser it deliberately does not import
    from core.timeutil import parse_iso_utc
    for s in ("2026-07-01T00:00:00Z", "2026-08-16T23:59:59Z", "2026-07-13T04:20:11.123Z"):
        assert abs(R.epoch(s) - parse_iso_utc(s).timestamp()) < 1e-6


def test_its_own_game_key_strips_only_the_outcome_suffix():
    assert R.game_of("KXKBOGAME-26JUL070530KIWKTW-KIW") == "KXKBOGAME-26JUL070530KIWKTW"
    assert R.looks_like_sports_game("KXNPBGAME-26JUL070500HANYOM-YOM") is True
    assert R.looks_like_sports_game("KXBTCD-26JUL0317-T100000") is False


def test_its_own_minority_counter_matches_the_library_contract():
    from core.bootstrap import sign_variation_admissible
    for units, expect_adm in (
        ({"g1": ("x", "no", "t1"), "g2": ("x", "no", "t2")}, False),
        ({"g1": ("x", "no", "t1"), "g2": ("x", "yes", "t2")}, False),
        ({"g1": ("x", "no", "t1"), "g2": ("x", "yes", "t2"), "g3": ("x", "yes", "t3")}, False),
        ({"g1": ("x", "no", "t1"), "g2": ("x", "no", "t2"), "g3": ("x", "no", "t3"),
          "g4": ("x", "yes", "t4"), "g5": ("x", "yes", "t5")}, True),
    ):
        counts, n_min, adm = R.minority(units)
        assert adm is expect_adm
        lib = sign_variation_admissible({g: [v[1]] for g, v in units.items()},
                                        min_exclusive_minority_units=2, sides=("yes", "no"))
        assert adm is bool(lib["admissible"])
        assert n_min == lib["minority_side_units_exclusive"]


def test_compare_flags_a_disagreement_rather_than_swallowing_it():
    """A comparison harness that cannot report DISAGREE is a rubber stamp."""
    report = {
        "substrate": {"n_game_tickers": 87, "n_games": 72, "n_settled_binary": 81,
                      "n_ledger_close_times": 49,
                      "cache": {"n_tickers_with_close_time": 38},
                      "union": {"min": {"n_both": 0}}},
        "baseline_ledger_only": {"n_game_units": 11, "units_per_side": {"no": 11}},
        "primary": {"n_game_units": 999, "units_per_side": {"no": 11}, "admissible": False},
        "widening_is_a_noop_at_the_sealed_spec": True,
        "anchor_rewrite_invariance": {"n_close_time_rewritten": 27,
                                      "entry_snapshot_identical_under_min_and_max_rule": 38},
        "entry_lag_profile": {
            "settlement_ledger": {"n_within_inherited_lag_budget": 37},
            "q51_settlement_cache": {"n_within_inherited_lag_budget": 5}},
        "grid": {"n_cells": 1280, "n_meeting_unit_floor": 976, "n_admissible": 36,
                 "n_admissible_and_mechanism_faithful": 0,
                 "admissible_min_lag_minutes": 180, "admissible_windows_used": [15]},
    }
    mine = {k: g(report) for k, g in R.COMPARE}
    mine["primary_units"] = 11              # the honest value; the report carries 999
    rows = R.compare(mine, report)
    bad = [r for r in rows if not r[3]]
    assert [r[0] for r in bad] == ["primary_units"]


# The FROZEN, dated snapshot of the census report — never the live path. L325/L341: a probe
# that self-activates over committed tape rewrites its own report whenever the tape grows, so
# an exact pin against `reports/<name>.json` turns RED on correct data (the 2026-08-12 Q54
# incident). The live artifact is free to move; this file is the published evidence.
FROZEN_REPORT = REPO / "reports" / "q57b_anchor_widening_census-2026-08-17.json"
FROZEN_SHA256 = "89b9f3922a2cc35b5bed28889715921201ab831c524d3a8b6042547a8b1b37ca"


def test_the_frozen_snapshot_is_the_one_the_finding_published():
    import hashlib
    assert hashlib.sha256(FROZEN_REPORT.read_bytes()).hexdigest() == FROZEN_SHA256


def test_the_redundancy_leg_reproduces_the_frozen_census_report():
    """The 22/22 agreement claim quoted in the finding, re-derived from raw tape."""
    import json
    report = json.loads(FROZEN_REPORT.read_text(encoding="utf-8"))
    rows = R.compare(R.derive(), report)
    disagree = [(k, a, b) for k, a, b, ok in rows if not ok]
    assert not disagree, f"redundancy leg disagrees: {disagree}"
    assert len(rows) == 22
