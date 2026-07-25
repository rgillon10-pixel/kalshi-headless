"""Offline tests for the GATING dead-strategy/shadow-registry invariant.

Stage 0 of the 2026-07-24 graph-engineering audit: a strategy marked `dead ✗` in
kb/strategies/00-index.md must not remain in execution/strategy_api.py::SHADOW_REGISTRY,
so a falsified strategy can never keep accruing paper P&L that reads as a live result.

Fixture-driven both directions (must fire / must not fire), plus a HARD pin that the
REAL tree is currently clean, plus the stale-exemption checks that stop
DEAD_SHADOW_PAPER_INFRA_EXEMPT from outliving its reason.
"""
import importlib.util
import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location(
    "invariants_mod", os.path.join(_ROOT, "scripts", "invariants.py")
)
inv = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(inv)


_REGISTRY_HEADER = (
    "| id | name | source | status | conf | gate |\n"
    "|---|---|---|---|---|---|\n"
)


def _write_registry(tmp_path, rows):
    """rows: list of (sid, status_cell)."""
    body = _REGISTRY_HEADER + "".join(
        f"| **{sid}** | n | src | {status} | low | g |\n" for sid, status in rows
    )
    p = tmp_path / "00-index.md"
    p.write_text(body, encoding="utf-8")
    return p


def _write_api(tmp_path, keys, extra=""):
    body = (
        "from __future__ import annotations\n"
        "from typing import Dict\n\n"
        "SHADOW_REGISTRY: Dict[str, Strategy] = {\n"
        + extra
        + "".join(f'    "{k}": Obj(),\n' for k in keys)
        + "}\n"
    )
    p = tmp_path / "strategy_api.py"
    p.write_text(body, encoding="utf-8")
    return p


# --- parsers --------------------------------------------------------------

def test_registry_dead_ids_reads_the_status_column(tmp_path):
    idx = _write_registry(tmp_path, [
        ("S1", "**dead ✗**"),
        ("S3", "**data-collecting**"),
        ("S0", "**built ✅**"),
        ("S16", "idea"),
        ("S14", "**dead ✗**"),
    ])
    assert inv._registry_dead_ids(idx) == {"S1", "S14"}


def test_registry_dead_ids_missing_file_is_offline_safe(tmp_path):
    assert inv._registry_dead_ids(tmp_path / "nope.md") == set()


def test_shadow_registry_keys_are_read_statically(tmp_path):
    api = _write_api(tmp_path, ["s14_ladder_underwriting", "s29_draw_maker"])
    assert inv._shadow_registry_keys(api) == ["s14_ladder_underwriting", "s29_draw_maker"]


def test_shadow_registry_keys_skips_comments_and_stops_at_close(tmp_path):
    api = _write_api(tmp_path, ["s14_ladder_underwriting"],
                     extra='    # "s99_commented_out": Obj(),\n')
    api.write_text(api.read_text(encoding="utf-8") + '\nOTHER = {"s77_not_shadow": 1}\n',
                   encoding="utf-8")
    assert inv._shadow_registry_keys(api) == ["s14_ladder_underwriting"]


def test_shadow_registry_keys_missing_file_is_offline_safe(tmp_path):
    assert inv._shadow_registry_keys(tmp_path / "nope.py") == []


# --- the invariant fires when it should -----------------------------------

def test_dead_strategy_still_registered_is_an_issue(tmp_path):
    idx = _write_registry(tmp_path, [("S14", "**dead ✗**")])
    api = _write_api(tmp_path, ["s14_ladder_underwriting"])
    issues = inv._dead_shadow_issues(idx, api, exempt={})
    assert len(issues) == 1
    assert "s14_ladder_underwriting" in issues[0] and "S14" in issues[0]


def test_registered_key_with_no_registry_row_is_an_issue(tmp_path):
    """The hole that would otherwise let a rename evade the dead check."""
    idx = _write_registry(tmp_path, [("S14", "**dead ✗**")])
    api = _write_api(tmp_path, ["s99_ghost_strategy"])
    issues = inv._dead_shadow_issues(idx, api, exempt={})
    assert len(issues) == 1
    assert "no row in the strategy registry" in issues[0]


def test_registered_key_without_an_s_id_is_an_issue(tmp_path):
    idx = _write_registry(tmp_path, [("S14", "**dead ✗**")])
    api = _write_api(tmp_path, ["totally_unnumbered"])
    issues = inv._dead_shadow_issues(idx, api, exempt={})
    assert len(issues) == 1
    assert "no `s<N>_` strategy id resolvable" in issues[0]


# --- and stays quiet when it should ---------------------------------------

def test_live_strategy_registered_is_clean(tmp_path):
    idx = _write_registry(tmp_path, [("S11", "**data-collecting**")])
    api = _write_api(tmp_path, ["s11_sharp_anchored_maker"])
    assert inv._dead_shadow_issues(idx, api, exempt={}) == []


def test_dead_strategy_with_a_documented_exemption_is_clean(tmp_path):
    idx = _write_registry(tmp_path, [("S14", "**dead ✗**")])
    api = _write_api(tmp_path, ["s14_ladder_underwriting"])
    exempt = {"s14_ladder_underwriting": "paper-infra validation only, not edge evidence"}
    assert inv._dead_shadow_issues(idx, api, exempt=exempt) == []


def test_empty_shadow_registry_is_clean(tmp_path):
    idx = _write_registry(tmp_path, [("S14", "**dead ✗**")])
    api = _write_api(tmp_path, [])
    assert inv._dead_shadow_issues(idx, api, exempt={}) == []


# --- exemptions cannot outlive their reason -------------------------------

def test_exemption_for_an_unregistered_key_is_stale(tmp_path):
    idx = _write_registry(tmp_path, [("S14", "**dead ✗**")])
    api = _write_api(tmp_path, [])
    exempt = {"s14_ladder_underwriting": "paper-infra validation only"}
    issues = inv._dead_shadow_issues(idx, api, exempt=exempt)
    assert len(issues) == 1
    assert "STALE EXEMPTION" in issues[0] and "no longer in SHADOW_REGISTRY" in issues[0]


def test_exemption_for_a_revived_strategy_is_stale(tmp_path):
    idx = _write_registry(tmp_path, [("S14", "**data-collecting**")])
    api = _write_api(tmp_path, ["s14_ladder_underwriting"])
    exempt = {"s14_ladder_underwriting": "paper-infra validation only"}
    issues = inv._dead_shadow_issues(idx, api, exempt=exempt)
    assert len(issues) == 1
    assert "STALE EXEMPTION" in issues[0] and "no longer `dead ✗`" in issues[0]


# --- message shape --------------------------------------------------------

def test_failure_message_is_none_when_clean():
    assert inv.dead_shadow_registered_failure([]) is None


def test_failure_message_names_the_rule_and_the_escape_hatch():
    msg = inv.dead_shadow_registered_failure(["s14_ladder_underwriting: strategy S14 is dead"])
    assert msg is not None
    assert "[dead_shadow_registered]" in msg
    assert "SHADOW_REGISTRY" in msg
    assert "DEAD_SHADOW_PAPER_INFRA_EXEMPT" in msg
    assert "may only shrink" in msg


def test_failure_message_truncates_long_issue_lists():
    msg = inv.dead_shadow_registered_failure([f"issue{i}" for i in range(9)])
    assert msg.startswith("[dead_shadow_registered] 9 ")
    assert "..." in msg


# --- HARD pins on the real tree -------------------------------------------

def test_real_tree_is_currently_clean():
    """If this fails, a dead strategy is shadowing (or an exemption went stale) — fix the
    registry/SHADOW_REGISTRY disagreement, do not weaken this test."""
    assert inv._dead_shadow_issues() == []


def test_the_only_exemption_is_s14_and_it_documents_why():
    """Ratchet pin: DEAD_SHADOW_PAPER_INFRA_EXEMPT may only SHRINK. Adding an entry must be a
    deliberate act that fails this test first."""
    assert set(inv.DEAD_SHADOW_PAPER_INFRA_EXEMPT) == {"s14_ladder_underwriting"}
    reason = inv.DEAD_SHADOW_PAPER_INFRA_EXEMPT["s14_ladder_underwriting"]
    assert "Q34" in reason
    assert "NOT edge evidence" in reason


def test_s14_is_actually_dead_in_the_real_registry():
    """The exemption's premise. If S14 ever revives, the stale-exemption check fires."""
    assert "S14" in inv._registry_dead_ids()


# --- wiring: this GATES, it does not warn ---------------------------------

def test_main_flips_the_exit_code_on_a_dead_shadow(monkeypatch, capsys):
    monkeypatch.setattr(inv, "scan_tree", lambda: [])
    for name in ("_git_tape_refs", "_tape_dir_shape_issues",
                 "_tape_dir_shape_orphan_classification", "_daily_family_gap_issues",
                 "_unregistered_single_hour_leg_issues", "_raw_datetime_fromisoformat_sites",
                 "_duplicate_lesson_id_issues", "_tape_conflict_marker_issues",
                 "_tape_invalid_jsonl_issues"):
        monkeypatch.setattr(inv, name, lambda *a, **k: [])
    monkeypatch.setattr(inv, "_dead_shadow_issues",
                        lambda *a, **k: ["s14_ladder_underwriting: strategy S14 is dead"])
    monkeypatch.setattr("sys.argv", ["invariants.py", "--full"])
    assert inv.main() == 2
    assert "[dead_shadow_registered]" in capsys.readouterr().err


def test_main_is_green_when_the_shadow_registry_agrees(monkeypatch):
    monkeypatch.setattr(inv, "scan_tree", lambda: [])
    for name in ("_git_tape_refs", "_tape_dir_shape_issues",
                 "_tape_dir_shape_orphan_classification", "_daily_family_gap_issues",
                 "_unregistered_single_hour_leg_issues", "_raw_datetime_fromisoformat_sites",
                 "_duplicate_lesson_id_issues", "_tape_conflict_marker_issues",
                 "_tape_invalid_jsonl_issues"):
        monkeypatch.setattr(inv, name, lambda *a, **k: [])
    monkeypatch.setattr(inv, "_dead_shadow_issues", lambda *a, **k: [])
    monkeypatch.setattr("sys.argv", ["invariants.py", "--full"])
    assert inv.main() == 0
