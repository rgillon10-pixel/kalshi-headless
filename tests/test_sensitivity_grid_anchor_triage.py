"""L362 ratchet: a sensitivity grid must declare where its pre-registered anchor sits and what
happens ONE STEP PAST its own edge.

Q57/S82 swept `flow_window_minutes` over (30, 60, 120, 240, 480) around a sealed 120 and called
the resulting sign-variation degeneracy STRUCTURAL; an independent verifier measured 15 min —
below the grid's own low edge — and the degeneracy dissolved. The gate this file pins does NOT
try to judge that reasoning. It forces the question to be ASKED at the site, in a form a later
reader can attack: per axis, the anchor constant, the anchor's position (RE-DERIVED from source,
so the declaration cannot rot), and an explicit OUT-OF-GRID disposition.

Everything here is offline and source-only: no tape, no network, no clock. The one real-tree
acceptance test reads committed SOURCE (not tape), so it cannot become an L140-style time bomb.
"""
from __future__ import annotations

import ast
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_engine():
    spec = importlib.util.spec_from_file_location(
        "inv_engine_sensitivity_grid", ROOT / "scripts" / "invariants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inv = _load_engine()

FIXTURE = ROOT / "scripts" / "q99_fixture_probe.py"        # never written to disk
FIXTURE_REL = "scripts/q99_fixture_probe.py"

GOOD_SENTENCE = ("NO STRUCTURAL CLAIM: the verdict is a CI at the pre-registered cell and no "
                 "generality claim rests on this grid.")


def _triage(monkeypatch, entries):
    monkeypatch.setitem(inv.SENSITIVITY_GRID_ANCHOR_TRIAGE, FIXTURE_REL, entries)


# ─── detector: what counts as a sensitivity grid ────────────────────────────────────

def _axes(src):
    return inv._sensitivity_grid_axes(ast.parse(src))


def test_detector_finds_a_tuple_and_a_list_grid():
    assert [a for a, _, _ in _axes("X_SWEEP = (0.02, 0.03)\n")] == ["X_SWEEP"]
    assert [a for a, _, _ in _axes("THETA_GRID = [1, 2, 3]\n")] == ["THETA_GRID"]


def test_detector_splits_a_dict_grid_into_one_axis_per_key():
    src = ('SENSITIVITY_GRID = {"w": (30.0, 60.0), "rho": (0.05, 0.10, 0.20)}\n')
    assert sorted(a for a, _, _ in _axes(src)) == ["SENSITIVITY_GRID[rho]", "SENSITIVITY_GRID[w]"]


def test_detector_drops_a_none_member_but_keeps_the_axis():
    """`None` is the idiom for an UNBOUNDED cell (tape_gap_monitor's full-history window). It is
    not a numeric member, but its presence must not hide the whole axis from the ratchet."""
    axes = _axes("GATE_SENSITIVITY_WINDOWS = (14, 21, 28, None)\n")
    assert [v for _, _, v in axes] == [[14.0, 21.0, 28.0]]


def test_detector_rejects_a_non_numeric_member():
    assert _axes('MODE_SWEEP = ("a", "b")\n') == []
    assert _axes("FLAG_SWEEP = (True, False)\n") == []


def test_detector_rejects_a_one_point_sweep():
    """One point is not a sweep, and neither is a repeated point — both would make the
    edge/interior question vacuous rather than answered."""
    assert _axes("X_SWEEP = (0.02,)\n") == []
    assert _axes("X_SWEEP = (5, 5)\n") == []


def test_detector_ignores_a_name_without_a_grid_segment():
    assert _axes("THRESHOLDS = (0.01, 0.02)\n") == []
    assert _axes("GRIDDED_FAMILIES = (1, 2)\n") == []     # 'GRIDDED' is not 'GRID'


def test_detector_ignores_a_grid_built_inside_a_function():
    """HONEST LIMIT, pinned as a limit rather than left implicit (L155): the rule is
    module-level-literal shaped, so a runtime-built grid is invisible to it."""
    assert _axes("def f():\n    X_SWEEP = (0.01, 0.02)\n    return X_SWEEP\n") == []


# ─── anchor resolution + position classification ────────────────────────────────────

def test_anchor_resolves_from_a_bare_module_constant_and_from_a_dict_lookup():
    tree = ast.parse('X_PRIMARY = 0.02\nPREREG = {"w": 120, "rho": 0.2}\n')
    assert inv._resolve_grid_anchor(tree, "X_PRIMARY") == 0.02
    assert inv._resolve_grid_anchor(tree, 'PREREG["w"]') == 120.0
    assert inv._resolve_grid_anchor(tree, "PREREG['rho']") == 0.2
    assert inv._resolve_grid_anchor(tree, "NOT_THERE") is None
    assert inv._resolve_grid_anchor(tree, 'PREREG["missing"]') is None


def test_classify_covers_every_position_including_off_grid_and_unresolved():
    g = [0.02, 0.03, 0.04]
    assert inv.classify_grid_anchor(0.02, g) == "EDGE_MIN"
    assert inv.classify_grid_anchor(0.04, g) == "EDGE_MAX"
    assert inv.classify_grid_anchor(0.03, g) == "INTERIOR"
    assert inv.classify_grid_anchor(0.99, g) == "OFF_GRID"
    assert inv.classify_grid_anchor(None, g) == "UNRESOLVED"
    assert inv.classify_grid_anchor(0.02, []) == "UNRESOLVED"


def test_classify_tolerates_float_representation_noise():
    assert inv.classify_grid_anchor(0.1 + 0.2, [0.1, 0.3]) == "EDGE_MAX"


# ─── the ratchet fires ──────────────────────────────────────────────────────────────

def test_fires_on_a_new_untriaged_grid():
    msg = inv.inv_sensitivity_grid_anchor_triage(
        FIXTURE, "X_PRIMARY = 0.02\nX_SWEEP = (0.02, 0.03, 0.04)\n")
    assert msg is not None
    assert "UNTRIAGED axis 'X_SWEEP'" in msg
    assert "L362" in msg and "SENSITIVITY_GRID_ANCHOR_TRIAGE" in msg


def test_fires_when_the_declared_position_disagrees_with_the_source():
    """The registry cannot rot: move the anchor to an edge and the INTERIOR declaration is a
    gate failure, not a stale comment nobody re-reads."""
    src = "X_PRIMARY = 0.02\nX_SWEEP = (0.02, 0.03, 0.04)\n"
    monkey = pytest.MonkeyPatch()
    try:
        _triage(monkey, {"X_SWEEP": ("X_PRIMARY", "INTERIOR", GOOD_SENTENCE)})
        msg = inv.inv_sensitivity_grid_anchor_triage(FIXTURE, src)
    finally:
        monkey.undo()
    assert msg is not None
    assert "declares INTERIOR" in msg and "source says EDGE_MIN" in msg


def test_fires_on_an_unknown_position_token(monkeypatch):
    _triage(monkeypatch, {"X_SWEEP": ("X_PRIMARY", "PROBABLY_FINE", GOOD_SENTENCE)})
    msg = inv.inv_sensitivity_grid_anchor_triage(
        FIXTURE, "X_PRIMARY = 0.03\nX_SWEEP = (0.02, 0.03, 0.04)\n")
    assert msg is not None and "not one of" in msg


def test_fires_when_the_disposition_token_is_missing(monkeypatch):
    _triage(monkeypatch, {"X_SWEEP": ("X_PRIMARY", "INTERIOR",
                                      "we looked at it and it seemed robust enough")})
    msg = inv.inv_sensitivity_grid_anchor_triage(
        FIXTURE, "X_PRIMARY = 0.03\nX_SWEEP = (0.02, 0.03, 0.04)\n")
    assert msg is not None
    assert "must open with one of" in msg


def test_fires_on_a_bare_disposition_token_with_no_reason(monkeypatch):
    _triage(monkeypatch, {"X_SWEEP": ("X_PRIMARY", "INTERIOR", "NO STRUCTURAL CLAIM:")})
    msg = inv.inv_sensitivity_grid_anchor_triage(
        FIXTURE, "X_PRIMARY = 0.03\nX_SWEEP = (0.02, 0.03, 0.04)\n")
    assert msg is not None and "bare token" in msg


def test_fires_on_a_stale_registry_entry_whose_axis_is_gone(monkeypatch):
    """Deleting a sweep must not leave a triage sentence behind claiming a question was
    answered about code that no longer exists."""
    _triage(monkeypatch, {"OLD_SWEEP": ("X_PRIMARY", "INTERIOR", GOOD_SENTENCE)})
    msg = inv.inv_sensitivity_grid_anchor_triage(FIXTURE, "X_PRIMARY = 0.03\n")
    assert msg is not None and "STALE entry" in msg


def test_fires_when_the_anchor_cannot_be_resolved_but_is_declared_concrete(monkeypatch):
    _triage(monkeypatch, {"X_SWEEP": ("MISSING_CONST", "INTERIOR", GOOD_SENTENCE)})
    msg = inv.inv_sensitivity_grid_anchor_triage(FIXTURE, "X_SWEEP = (0.02, 0.03, 0.04)\n")
    assert msg is not None and "source says UNRESOLVED" in msg


# ─── the ratchet stays silent where it should ───────────────────────────────────────

def test_silent_on_a_correctly_triaged_axis(monkeypatch):
    _triage(monkeypatch, {"X_SWEEP": ("X_PRIMARY", "EDGE_MIN",
                                      "OUT-OF-GRID IMPOSSIBLE: 0.01 is the venue's minimum "
                                      "tick, so no cell exists below this edge.")})
    assert inv.inv_sensitivity_grid_anchor_triage(
        FIXTURE, "X_PRIMARY = 0.02\nX_SWEEP = (0.02, 0.03, 0.04)\n") is None


def test_silent_when_the_anchor_is_declared_UNRESOLVED_and_really_is(monkeypatch):
    _triage(monkeypatch, {"X_SWEEP": ("RUNTIME_ANCHOR", "UNRESOLVED",
                                      "NO STRUCTURAL CLAIM: the anchor is a CLI argument, so "
                                      "the source does not decide its value.")})
    assert inv.inv_sensitivity_grid_anchor_triage(FIXTURE, "X_SWEEP = (0.02, 0.03)\n") is None


def test_out_of_scope_directories_and_files_are_not_scanned():
    src = "X_PRIMARY = 0.02\nX_SWEEP = (0.02, 0.03, 0.04)\n"
    assert inv.inv_sensitivity_grid_anchor_triage(ROOT / "tests" / "t_fixture.py", src) is None
    assert inv.inv_sensitivity_grid_anchor_triage(ROOT / "notebooks_x.py", src) is None
    assert inv.inv_sensitivity_grid_anchor_triage(
        ROOT / "scripts" / "invariants.py", src) is None      # self-exclusion


def test_syntax_error_is_not_a_finding():
    assert inv.inv_sensitivity_grid_anchor_triage(FIXTURE, "def (\n") is None


# ─── wiring: this is a GATING static invariant, reached through scan_text ───────────

def test_registered_as_a_gating_static_invariant():
    names = [n for n, _ in inv.STATIC_INVARIANTS]
    assert "sensitivity_grid_anchor_triage" in names


def test_scan_text_surfaces_the_finding():
    issues = inv.scan_text(FIXTURE, "X_PRIMARY = 0.02\nX_SWEEP = (0.02, 0.03, 0.04)\n")
    assert any("L362" in i for i in issues)


# ─── real-tree acceptance (source, not tape) ────────────────────────────────────────

def _real_tree_failures():
    out = []
    for p in inv._iter_source_files():
        if p.suffix != ".py":
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        msg = inv.inv_sensitivity_grid_anchor_triage(p, text)
        if msg:
            out.append(msg)
    return out


def test_acceptance_real_tree_is_clean():
    assert _real_tree_failures() == []


def test_acceptance_the_registry_is_not_vacuous():
    """A ratchet that matches nothing reports the same 0 as a clean one (L155). Floors, not
    frozen counts (L320/L191): the census on 2026-08-17 was 11 axes across 6 files."""
    axes = 0
    for p in inv._iter_source_files():
        if p.suffix != ".py" or not inv._rel(p).startswith(inv._SENSITIVITY_GRID_DIRS):
            continue
        if inv._file_excluded(p):
            continue
        try:
            axes += len(inv._sensitivity_grid_axes(ast.parse(p.read_text(encoding="utf-8"))))
        except SyntaxError:
            continue
    assert axes >= 8
    assert len(inv.SENSITIVITY_GRID_ANCHOR_TRIAGE) >= 5


def test_acceptance_q57s_four_axes_are_all_INTERIOR():
    """THE L362 EXHIBIT. The other enforcement candidate the lesson named — 'the anchor must not
    be the min or max of any swept axis' — would have passed Q57, the probe the lesson came
    from: every one of its axes brackets its sealed value. Interiority is not sufficient, which
    is why the mandatory field is the out-of-grid DISPOSITION, not the position."""
    rel = "scripts/q57_s82_flow_fade_probe.py"
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    axes = inv._sensitivity_grid_axes(tree)
    assert len(axes) == 4
    for axis_id, _, values in axes:
        spec, declared, _sentence = inv.SENSITIVITY_GRID_ANCHOR_TRIAGE[rel][axis_id]
        assert inv.classify_grid_anchor(inv._resolve_grid_anchor(tree, spec), values) == "INTERIOR"
        assert declared == "INTERIOR"


def test_acceptance_the_edge_anchored_sites_are_named_and_carry_a_disposition():
    """The three EDGE-anchored axes on the tree as of 2026-08-17, all in probes whose verdicts
    are closed. Only ONE of them backs a claim the lesson binds on (S10 is a 'STRUCTURAL DEAD'),
    and its disposition is OUT-OF-GRID IMPOSSIBLE — 0.01 is Kalshi's minimum tick."""
    expected = {
        "scripts/q28_s24_nearclose_fade_probe.py": ("X_SWEEP", "EDGE_MIN"),
        "scripts/s10_reachability_probe.py": ("THRESHOLD_SWEEP", "EDGE_MIN"),
        "scripts/s6_maker_firstcut.py": ("SPREAD_CAP_SWEEP_CENTS", "EDGE_MAX"),
    }
    for rel, (axis_id, position) in expected.items():
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        values = {a: v for a, _, v in inv._sensitivity_grid_axes(tree)}[axis_id]
        spec, declared, sentence = inv.SENSITIVITY_GRID_ANCHOR_TRIAGE[rel][axis_id]
        assert inv.classify_grid_anchor(inv._resolve_grid_anchor(tree, spec), values) == position
        assert declared == position
        assert any(sentence.startswith(t) for t in inv._GRID_DISPOSITIONS)
    s10 = inv.SENSITIVITY_GRID_ANCHOR_TRIAGE["scripts/s10_reachability_probe.py"]
    assert s10["THRESHOLD_SWEEP"][2].startswith("OUT-OF-GRID IMPOSSIBLE:")
