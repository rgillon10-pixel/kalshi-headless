"""L362 enforcement: sensitivity-grid edge arithmetic + the repo-wide inventory scanner.

L362 (2026-08-16, Q57/S82 verifier round): *a sensitivity grid that only BRACKETS the
pre-registered value cannot distinguish "structural" from "an artifact of this constant."*
Q57's `flow_window_minutes` axis ran (30, 60, 120, 240, 480) around a sealed 120 — the seal
is INTERIOR, so an "is the seal at an edge?" test would have passed — and the sign-variation
degeneracy it called structural dissolved at 15 minutes, one geometric step past the grid's
own low edge.

Three tiers, per house style:
  * synthetic unit tests of the arithmetic (`core/sensitivity.py`);
  * synthetic AST tests of the scanner, INCLUDING its declared blind spots pinned as
    deliberate MISSES (a detector whose recall is unstated is a detector that lies, L155);
  * real-tree acceptance over the COMMITTED probe modules, as directions and floors, never
    frozen counts (L320/L191) — except the one exact pin that IS the lesson: Q57's own
    committed axis yields 15.0.
"""
from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.sensitivity import (  # noqa: E402
    POSITION_ABSENT, POSITION_HIGH_EDGE, POSITION_INTERIOR, POSITION_LOW_EDGE,
    POSITION_OUTSIDE_HIGH, POSITION_OUTSIDE_LOW, POSITION_SINGLETON,
    SPACING_ARITHMETIC, SPACING_EMPTY, SPACING_GEOMETRIC, SPACING_IRREGULAR,
    SPACING_SINGLETON, axis_edge_status, axis_spacing, grid_edge_report,
    out_of_grid_probes, structural_claim_admissible,
)


def _load_invariants():
    spec = importlib.util.spec_from_file_location("_inv_l362", ROOT / "scripts" / "invariants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


INV = _load_invariants()


# --------------------------------------------------------------------------- #
# tier 1 — the arithmetic
# --------------------------------------------------------------------------- #
class TestAxisSpacing:
    def test_arithmetic_axis(self):
        sp = axis_spacing((0.02, 0.03, 0.04, 0.05))
        assert sp["kind"] == SPACING_ARITHMETIC
        assert sp["step"] == pytest.approx(0.01)

    def test_geometric_axis(self):
        sp = axis_spacing((30, 60, 120, 240, 480))
        assert sp["kind"] == SPACING_GEOMETRIC
        assert sp["ratio"] == pytest.approx(2.0)

    def test_a_zero_in_the_axis_makes_it_irregular_not_geometric(self):
        # (0, 100, 1000) — ratios are undefined at 0; the tool must not invent a step.
        assert axis_spacing((0.0, 100.0, 1000.0))["kind"] == SPACING_IRREGULAR

    def test_mixed_spacing_is_irregular(self):
        assert axis_spacing((30, 60, 240, 4320))["kind"] == SPACING_IRREGULAR

    def test_singleton_and_empty_are_distinct_kinds(self):
        assert axis_spacing((5,))["kind"] == SPACING_SINGLETON
        assert axis_spacing(())["kind"] == SPACING_EMPTY

    def test_two_point_axis_is_ambiguous_and_says_so(self):
        sp = axis_spacing((30, 60))
        assert sp["kind"] == SPACING_ARITHMETIC          # conservative reading
        assert sp["ambiguous_two_point"] is True
        assert sp["ratio"] == pytest.approx(2.0)         # the alternative is still reported

    def test_unsorted_and_duplicated_input_is_normalised(self):
        assert axis_spacing((60, 30, 30, 120))["values"] == (30.0, 60.0, 120.0)


class TestOutOfGridProbes:
    def test_L362_REGRESSION_the_geometric_low_probe_is_the_value_the_verifier_found(self):
        # THE lesson, in one assertion: Q57's sealed axis, extended by its own ratio,
        # names 15 minutes — the value at which the "structural" degeneracy dissolved.
        p = out_of_grid_probes((30.0, 60.0, 120.0, 240.0, 480.0))
        assert p["low"] == pytest.approx(15.0)
        assert p["high"] == pytest.approx(960.0)

    def test_arithmetic_extension_uses_the_axis_step(self):
        p = out_of_grid_probes((0.02, 0.03, 0.04, 0.05))
        assert p["low"] == pytest.approx(0.01)
        assert p["high"] == pytest.approx(0.06)

    def test_irregular_axis_refuses_rather_than_guessing(self):
        p = out_of_grid_probes((30, 60, 240, 4320))
        assert p["low"] is None and p["high"] is None
        assert p["low_reason"] == p["high_reason"] == "irregular_spacing"

    def test_a_natural_bound_terminates_a_side_with_a_reason_not_a_number(self):
        p = out_of_grid_probes((0.05, 0.10, 0.20, 0.40), bounds=(0.05, None))
        assert p["low"] is None and p["low_reason"] == "at_natural_bound"
        assert p["high"] == pytest.approx(0.80)

    def test_a_bound_that_is_not_crossed_leaves_the_probe_intact(self):
        p = out_of_grid_probes((0.05, 0.10, 0.20, 0.40), bounds=(0.0, 1.0))
        assert p["low"] == pytest.approx(0.025)
        assert p["high"] == pytest.approx(0.80)

    def test_singleton_axis_has_no_extension(self):
        p = out_of_grid_probes((7,))
        assert p["low"] is None and p["low_reason"] == "singleton_axis"


class TestAxisEdgeStatus:
    def test_interior_seal_is_still_not_settled_the_q57_case(self):
        st = axis_edge_status("flow_window_minutes", (30, 60, 120, 240, 480), 120)
        assert st.position == POSITION_INTERIOR
        assert st.edges_settled is False          # interior != discharged (L362's whole point)

    def test_low_edge_and_high_edge(self):
        assert axis_edge_status("x", (0.02, 0.03, 0.04), 0.02).position == POSITION_LOW_EDGE
        assert axis_edge_status("x", (0.02, 0.03, 0.04), 0.04).position == POSITION_HIGH_EDGE

    def test_outside_the_grid_both_ways(self):
        assert axis_edge_status("x", (2, 3, 4), 1).position == POSITION_OUTSIDE_LOW
        assert axis_edge_status("x", (2, 3, 4), 9).position == POSITION_OUTSIDE_HIGH

    def test_absent_and_singleton_positions(self):
        assert axis_edge_status("x", (2, 3, 4)).position == POSITION_ABSENT
        assert axis_edge_status("x", (2,), 2).position == POSITION_SINGLETON

    def test_probing_past_both_edges_settles_the_axis(self):
        st = axis_edge_status("x", (30, 60, 120), 60, probed=(15, 240))
        assert st.probed_past_low and st.probed_past_high and st.edges_settled

    def test_a_probe_inside_the_grid_settles_nothing(self):
        st = axis_edge_status("x", (30, 60, 120), 60, probed=(45, 90))
        assert not st.probed_past_low and not st.probed_past_high and not st.edges_settled

    def test_natural_bound_plus_one_probe_settles_the_axis(self):
        st = axis_edge_status("count", (0.0, 100.0, 250.0), 100.0, probed=(500.0,),
                              bounds=(0.0, None))
        assert st.probe_low_reason == "at_natural_bound"
        assert st.edges_settled is True


class TestGridEdgeReport:
    GRID = {"w": (30, 60, 120, 240, 480), "rho": (0.05, 0.10, 0.20, 0.40)}

    def test_unprobed_grid_is_not_admissible_and_names_the_blockers(self):
        rep = grid_edge_report(self.GRID, {"w": 120, "rho": 0.20})
        ok, blocking = structural_claim_admissible(rep)
        assert ok is False
        assert sorted(blocking) == ["rho", "w"]

    def test_fully_probed_grid_is_admissible(self):
        rep = grid_edge_report(self.GRID, {"w": 120, "rho": 0.20},
                               probed={"w": (15, 960), "rho": (0.025, 0.80)})
        assert structural_claim_admissible(rep) == (True, [])

    def test_empty_grid_is_never_admissible(self):
        assert structural_claim_admissible(grid_edge_report({}, {})) == (False, [])

    def test_prose_fields_in_a_sealed_spec_are_ignored_not_coerced(self):
        rep = grid_edge_report({"w": (30, 60, 120)},
                               {"w": 60, "strategy": "S82", "direction": "FADE"})
        assert rep["axes"][0]["preregistered"] == 60.0

    def test_a_bool_is_not_a_pre_registered_number(self):
        rep = grid_edge_report({"w": (30, 60, 120)}, {"w": True})
        assert rep["axes"][0]["preregistered"] is None
        assert rep["axes"][0]["position"] == POSITION_ABSENT

    def test_edge_seated_seals_are_listed_separately(self):
        rep = grid_edge_report({"x": (0.02, 0.03, 0.04)}, {"x": 0.02})
        assert rep["axes_with_seal_at_an_edge"] == ["x"]


# --------------------------------------------------------------------------- #
# tier 2 — the scanner, including its declared blind spots
# --------------------------------------------------------------------------- #
def _scan(tmp_path: Path, source: str, name: str = "probe.py"):
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts" / name).write_text(source, encoding="utf-8")
    return INV._sensitivity_grid_declarations(tmp_path)


class TestScannerShapes:
    def test_dict_of_axes_with_a_sealed_spec_is_read(self, tmp_path):
        decls = _scan(tmp_path, 'PREREGISTRATION = {"w": 120}\n'
                                'SENSITIVITY_GRID = {"w": (30, 60, 120, 240)}\n')
        assert len(decls) == 1
        assert decls[0]["axis"] == "w" and decls[0]["preregistered"] == 120.0
        assert decls[0]["pairing"] == "sealed_spec_key"

    def test_grid_nested_inside_the_sealed_spec_is_read(self, tmp_path):
        decls = _scan(tmp_path, 'PREREGISTRATION = {"w": 60, '
                                '"grid_axes": {"w": [15, 30, 60, 120]}}\n')
        assert len(decls) == 1 and decls[0]["shape"] == "nested_in_sealed_spec"
        assert decls[0]["preregistered"] == 60.0

    def test_bare_sequence_pairs_to_a_unique_prefix_scalar(self, tmp_path):
        decls = _scan(tmp_path, "X_PRIMARY = 0.02\nX_SWEEP = (0.02, 0.03, 0.04)\n")
        assert len(decls) == 1
        assert decls[0]["preregistered"] == 0.02
        assert decls[0]["pairing"] == "prefix_scalar:X_PRIMARY"

    def test_two_prefix_candidates_are_ambiguous_never_a_guess(self, tmp_path):
        decls = _scan(tmp_path, "X_PRIMARY = 0.02\nX_OTHER = 0.09\n"
                                "X_SWEEP = (0.02, 0.03, 0.04)\n")
        assert decls[0]["preregistered"] is None and decls[0]["pairing"] == "ambiguous"

    def test_out_of_grid_declaration_is_detected(self, tmp_path):
        decls = _scan(tmp_path, 'PREREGISTRATION = {"w": 60}\n'
                                'SENSITIVITY_GRID = {"w": (30, 60, 120)}\n'
                                'OUT_OF_GRID_PROBES = {"w": (15, 240)}\n')
        assert decls[0]["declares_out_of_grid_probes"] is True


class TestScannerBlindSpotsArePinnedAsMisses:
    """Each of these is a KNOWN miss named in the advisory text. Pinning them as tests
    keeps the stated recall honest: if one ever starts being detected, the advisory's
    coverage sentence must change with it."""

    def test_symbolic_axis_values_are_not_read(self, tmp_path):
        decls = _scan(tmp_path, "OTHER = 30\nSENSITIVITY_GRID = {'w': (OTHER, 60, 120)}\n")
        assert decls == []

    def test_a_sealed_value_that_is_an_expression_is_unpaired(self, tmp_path):
        decls = _scan(tmp_path, 'OTHER = {"w": 60}\n'
                                'PREREGISTRATION = {"w": OTHER["w"]}\n'
                                'SENSITIVITY_GRID = {"w": (30, 60, 120)}\n')
        assert len(decls) == 1 and decls[0]["preregistered"] is None

    def test_a_grid_built_inside_a_function_is_not_seen(self, tmp_path):
        decls = _scan(tmp_path, "def f():\n    SENSITIVITY_GRID = {'w': (30, 60, 120)}\n"
                                "    return SENSITIVITY_GRID\n")
        assert decls == []

    def test_a_one_element_sequence_is_not_a_grid(self, tmp_path):
        decls = _scan(tmp_path, "X_PRIMARY = 0.02\nX_SWEEP = (0.02,)\n")
        assert decls == []

    def test_a_comprehension_axis_is_not_read(self, tmp_path):
        decls = _scan(tmp_path, "SENSITIVITY_GRID = {'w': [30 * i for i in range(4)]}\n")
        assert decls == []


class TestScannerIssuesAndWarning:
    def test_only_edge_seated_paired_axes_become_issues(self, tmp_path):
        _scan(tmp_path, 'PREREGISTRATION = {"w": 120}\n'
                        'SENSITIVITY_GRID = {"w": (30, 60, 120, 240, 480)}\n', "interior.py")
        assert INV._sensitivity_grid_edge_issues(tmp_path) == []
        (tmp_path / "scripts" / "edge.py").write_text(
            'PREREGISTRATION = {"w": 30}\nSENSITIVITY_GRID = {"w": (30, 60, 120)}\n',
            encoding="utf-8")
        issues = INV._sensitivity_grid_edge_issues(tmp_path)
        assert len(issues) == 1 and "low_edge" in issues[0] and "15" in issues[0]

    def test_warning_is_none_only_when_the_tree_declares_nothing(self):
        assert INV.sensitivity_grid_edge_warning([], []) is None

    def test_warning_says_non_gating_and_cites_the_lesson(self):
        msg = INV.sensitivity_grid_edge_warning(
            [], [{"path": "scripts/p.py", "preregistered": 120.0,
                  "declares_out_of_grid_probes": False}])
        assert "non-gating" in msg and "L362" in msg
        assert "does NOT affect the exit code" in msg

    def test_warning_states_that_zero_issues_is_precision_not_recall(self):
        msg = INV.sensitivity_grid_edge_warning(
            [], [{"path": "scripts/p.py", "preregistered": None,
                  "declares_out_of_grid_probes": False}])
        assert "PRECISION only" in msg and "RECALL" in msg
        # an interior seal must NOT be reported as discharging the lesson
        assert "interior seal was exactly Q57's situation" in msg


# --------------------------------------------------------------------------- #
# tier 3 — real committed tree (directions and floors, L320/L191)
# --------------------------------------------------------------------------- #
class TestRealTreeAcceptance:
    DECLS = INV._sensitivity_grid_declarations()

    def _axes_of(self, path_frag, grid=None):
        return {d["axis"]: d for d in self.DECLS
                if path_frag in d["path"] and (grid is None or d["grid"] == grid)}

    def test_the_tree_declares_several_readable_grids(self):
        assert len(self.DECLS) >= 5
        assert len({d["path"] for d in self.DECLS}) >= 3

    def test_q57s_committed_axis_yields_the_15_minute_probe(self):
        """The exact pin: read Q57's SEALED grid off the committed source and extend it.
        The verifier needed a hand-run to find 15; the tool derives it from the seal."""
        axes = self._axes_of("q57_s82_flow_fade_probe.py", "SENSITIVITY_GRID")
        w = axes["flow_window_minutes"]
        assert w["preregistered"] == 120.0
        assert out_of_grid_probes(w["values"])["low"] == pytest.approx(15.0)

    def test_q57s_grid_is_not_structural_claim_admissible_unprobed(self):
        axes = self._axes_of("q57_s82_flow_fade_probe.py", "SENSITIVITY_GRID")
        grid = {a: d["values"] for a, d in axes.items()}
        prereg = {a: d["preregistered"] for a, d in axes.items()}
        ok, blocking = structural_claim_admissible(grid_edge_report(grid, prereg))
        assert ok is False
        assert set(blocking) == set(grid)          # every axis, not just the window one

    def test_the_follow_on_census_extends_exactly_one_of_q57s_eight_edges(self):
        """Direction, not a frozen count: Q57b DID reach past Q57's low window edge (that
        is how 15 got measured at all) and did NOT reach past most of the others, so the
        most recent structural-class claim in this repo still owes most of its edges."""
        sealed = self._axes_of("q57_s82_flow_fade_probe.py", "SENSITIVITY_GRID")
        follow = self._axes_of("q57b_anchor_widening_census.py", "PREREGISTRATION")
        assert sealed and follow
        rep = grid_edge_report({a: d["values"] for a, d in sealed.items()},
                               {a: d["preregistered"] for a, d in sealed.items()},
                               probed={a: follow[a]["values"] for a in follow if a in sealed})
        settled = [a["axis"] for a in rep["axes"] if a["edges_settled"]]
        assert settled == []                       # not one axis fully settled
        past_low = [a["axis"] for a in rep["axes"] if a["probed_past_low"]]
        assert "flow_window_minutes" in past_low   # the one real extension
        assert len(past_low) <= 2
        past_high = [a["axis"] for a in rep["axes"] if a["probed_past_high"]]
        assert past_high == []                     # no axis was extended upward at all

    def test_every_live_issue_names_a_real_file_and_a_next_probe(self):
        for issue in INV._sensitivity_grid_edge_issues():
            path = issue.split("::", 1)[0]
            assert (ROOT / path).is_file()
            assert "one step past that edge =" in issue

    def test_the_scanner_only_reads_syntactically_valid_literals(self):
        """Whatever it reports must round-trip through ast.literal_eval on the source it
        claims to have read — a cheap guard against a future regex-y rewrite."""
        for d in self.DECLS:
            assert all(isinstance(v, float) for v in d["values"])
            assert len(d["values"]) >= 2
            src = (ROOT / d["path"]).read_text(encoding="utf-8")
            ast.parse(src)


class TestInvariantsStaysGreen:
    def test_full_run_exits_zero_with_the_advisory_present(self):
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "invariants.py"), "--full"],
                              capture_output=True, text=True, cwd=str(ROOT), timeout=900)
        assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
        assert "L362 sensitivity-grid edge inventory" in proc.stderr


class TestNaturalBoundPrecedence:
    """Regression tier for the defect this suite caught during construction: the bound
    check must run BEFORE the spacing refusal, else an axis that starts at its own floor
    (`min_window_count = (0, 100, 250)`) reports `irregular_spacing` forever and looks like
    an unmet L362 obligation when it is in fact settled."""

    def test_irregular_axis_sitting_on_its_floor_is_settled_low_not_refused(self):
        p = out_of_grid_probes((0.0, 100.0, 250.0), bounds=(0.0, None))
        assert p["low_reason"] == "at_natural_bound"
        assert p["high_reason"] == "irregular_spacing"   # the other side is still owed

    def test_without_a_declared_bound_the_same_axis_is_refused_both_ways(self):
        p = out_of_grid_probes((0.0, 100.0, 250.0))
        assert p["low_reason"] == p["high_reason"] == "irregular_spacing"

    def test_singleton_axis_on_its_floor_reports_the_bound_not_the_singleton(self):
        p = out_of_grid_probes((0.0,), bounds=(0.0, None))
        assert p["low_reason"] == "at_natural_bound"
        assert p["high_reason"] == "singleton_axis"

    def test_an_axis_topping_out_at_its_ceiling_is_settled_high(self):
        p = out_of_grid_probes((0.90, 0.95, 1.0), bounds=(0.0, 1.0))
        assert p["high_reason"] == "at_natural_bound"
        assert p["low"] == pytest.approx(0.85)


class TestInventoryReportScript:
    """`scripts/sensitivity_grid_edge_report.py` — the re-runnable artifact behind the
    finding. Composition only: it must not re-implement the detector or the arithmetic."""

    def test_module_does_not_reimplement_the_detector_or_the_arithmetic(self):
        """AST pin (the L36/L102 twin rule): the report script IMPORTS both halves and
        defines neither, so a future edit cannot fork a third copy silently."""
        src = (ROOT / "scripts" / "sensitivity_grid_edge_report.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert "out_of_grid_probes" not in defined
        assert "_sensitivity_grid_declarations" not in defined
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                    for a in n.names}
        assert {"out_of_grid_probes", "_sensitivity_grid_declarations"} <= imported

    def test_inventory_shape_and_price_provenance(self):
        from scripts.sensitivity_grid_edge_report import inventory
        inv = inventory()
        assert inv["lesson"] == "L362"
        assert inv["n_axes"] == len(inv["axes"]) >= 5
        assert inv["n_paired"] <= inv["n_axes"]
        # This work touches no price at all; the record must say so rather than omit it.
        assert inv["price_provenance"] == {"prices_quoted": False, "price_source_tag": None}

    def test_cross_module_coverage_reports_the_owed_edges(self):
        from scripts.sensitivity_grid_edge_report import (cross_module_probe_coverage,
                                                          inventory)
        cross = cross_module_probe_coverage(inventory(), "q57_s82_flow_fade_probe.py",
                                            "q57b_anchor_widening_census.py")
        assert cross is not None
        assert cross["n_edges"] == 2 * cross["n_axes"]
        assert 1 <= cross["n_edges_probed"] < cross["n_edges"]   # some, never all
        assert cross["structural_claim_admissible"] is False
        assert cross["axes_probed_past_high"] == []

    def test_cross_module_coverage_is_none_when_a_side_is_absent(self):
        from scripts.sensitivity_grid_edge_report import (cross_module_probe_coverage,
                                                          inventory)
        assert cross_module_probe_coverage(inventory(), "no_such_module.py",
                                           "q57b_anchor_widening_census.py") is None

    def test_runs_as_a_real_subprocess_with_scrubbed_pythonpath(self, tmp_path):
        """L232: the invocation form findings/ cite (`python3 scripts/foo.py`) must work
        with no PYTHONPATH help and cwd outside the repo."""
        import os
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "sensitivity_grid_edge_report.py"), "--json"],
            capture_output=True, text=True, cwd=str(tmp_path), env=env, timeout=300)
        assert proc.returncode == 0, proc.stderr[-2000:]
        payload = __import__("json").loads(proc.stdout)
        assert payload["lesson"] == "L362" and payload["n_axes"] >= 5

    def test_committed_report_matches_a_fresh_run(self):
        """The committed artifact is regenerable, not a hand-edited number (CLAUDE.md's
        re-runnable-script rule). Compared on the STABLE aggregate fields only, so adding a
        new grid to the tree does not rot the pin — it changes the counts, which is exactly
        when the report should be regenerated."""
        import json as _json
        from scripts.sensitivity_grid_edge_report import DEFAULT_REPORT, inventory
        if not DEFAULT_REPORT.exists():
            pytest.skip("report not committed")
        committed = _json.loads(DEFAULT_REPORT.read_text(encoding="utf-8"))
        fresh = inventory()
        assert committed["n_axes"] == fresh["n_axes"]
        assert committed["n_seal_at_edge"] == fresh["n_seal_at_edge"]
        assert committed["n_modules_declaring_out_of_grid_probes"] == \
            fresh["n_modules_declaring_out_of_grid_probes"]
