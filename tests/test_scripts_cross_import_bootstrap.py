"""L232 enforcement: a file under `scripts/` that imports the `scripts.` package must carry a
repo-root `sys.path` bootstrap ahead of that import.

Two layers, deliberately:

1. FIXTURE tests of `scripts/invariants.py::_scripts_cross_import_bootstrap_issues` over a
   synthetic tree. Per L189 a detector that reports 0 issues must PUBLISH its recall, and per
   L192/L207 the "it CAN fire" assertion belongs on a FROZEN FIXTURE, never on the live tree
   (whose cleanliness is the thing the advisory exists to change).
2. REAL-SUBPROCESS acceptance tests. L232's own text: an in-process import test proves nothing
   here, because the repo-root `conftest.py` repairs `sys.path` under pytest and masks exactly
   the breakage. So the two scripts this run repaired are invoked as real subprocesses with
   `PYTHONPATH` scrubbed and the working directory OUTSIDE the repo.

Also pins the 2026-08-02 exclusion defect (`_excluded_relative_to`): EXCLUDE_DIRS must be
matched on the path RELATIVE to the repo root. Every autonomous run of this repo executes from
`.claude/worktrees/agent-*`, whose absolute parts contain `.claude` AND `worktrees` -- the old
absolute-parts test excluded the whole repository, so `scan_tree()` (the Hard-Rule static gate)
and every source-scanning advisory silently scanned 0 files and reported 0 issues.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_engine():
    spec = importlib.util.spec_from_file_location(
        "inv_engine_l232", ROOT / "scripts" / "invariants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inv = _load_engine()

BOOTSTRAP = 'sys.path.insert(0, str(Path(__file__).resolve().parents[1]))'

# Scripts this run repaired; each is cited BY SCRIPT PATH (the direct form) in kb/ or findings/.
REPAIRED_SCRIPTS = ("s9_shock_eventstudy.py", "sports_clv_s7.py")


def _tree(tmp_path: pathlib.Path, name: str, body: str) -> pathlib.Path:
    """A minimal fake repo root with one file under scripts/."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / name).write_text(body)
    return root


# --- Layer 1: fixture tests of the detector (recall proof) -------------------

def test_fires_on_module_level_from_scripts_import_without_bootstrap(tmp_path):
    root = _tree(tmp_path, "broken.py", "import sys\nfrom scripts.other import thing\n")
    assert inv._scripts_cross_import_bootstrap_issues(root) == ["scripts/broken.py:2"]


def test_fires_on_plain_import_scripts_dot_x_without_bootstrap(tmp_path):
    root = _tree(tmp_path, "broken2.py", "import os\nimport scripts.other\n")
    assert inv._scripts_cross_import_bootstrap_issues(root) == ["scripts/broken2.py:2"]


def test_fires_on_from_scripts_import_name_form(tmp_path):
    root = _tree(tmp_path, "broken3.py", "from scripts import other\n")
    assert inv._scripts_cross_import_bootstrap_issues(root) == ["scripts/broken3.py:1"]


def test_fires_when_the_bootstrap_comes_after_the_import(tmp_path):
    body = (
        "import sys\n"
        "from pathlib import Path\n"
        "from scripts.other import thing\n"
        f"{BOOTSTRAP}\n"
    )
    root = _tree(tmp_path, "late.py", body)
    assert inv._scripts_cross_import_bootstrap_issues(root) == ["scripts/late.py:3"]


def test_fires_when_the_only_bootstrap_inserts_the_scripts_directory(tmp_path):
    """The `scripts/gen_problems_dashboard.py` shape: inserting the scripts DIRECTORY makes
    `import other` work but NOT `import scripts.other`, so it is not a bootstrap for this
    rule."""
    body = (
        "import sys\n"
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        'sys.path.insert(0, str(ROOT / "scripts"))\n'
        "from scripts.other import thing\n"
    )
    root = _tree(tmp_path, "dirboot.py", body)
    assert inv._scripts_cross_import_bootstrap_issues(root) == ["scripts/dirboot.py:5"]


def test_silent_when_the_bootstrap_precedes_the_import(tmp_path):
    body = (
        "import sys\n"
        "from pathlib import Path\n"
        f"{BOOTSTRAP}\n"
        "from scripts.other import thing\n"
    )
    root = _tree(tmp_path, "ok.py", body)
    assert inv._scripts_cross_import_bootstrap_issues(root) == []


def test_silent_for_a_function_local_import_under_a_module_level_bootstrap(tmp_path):
    """`scripts/q35_maker_rebate_reframe.py` / `q39_graveyard_counterfactual_sweep.py` shape."""
    body = (
        "import sys\n"
        "from pathlib import Path\n"
        f"{BOOTSTRAP}\n"
        "\n"
        "def go():\n"
        "    from scripts import other\n"
        "    return other\n"
    )
    root = _tree(tmp_path, "local.py", body)
    assert inv._scripts_cross_import_bootstrap_issues(root) == []


def test_a_function_local_import_with_no_bootstrap_at_all_still_fires(tmp_path):
    body = "def go():\n    from scripts import other\n    return other\n"
    root = _tree(tmp_path, "localbad.py", body)
    assert inv._scripts_cross_import_bootstrap_issues(root) == ["scripts/localbad.py:2"]


def test_a_from_scripts_inside_a_docstring_is_not_a_hit(tmp_path):
    """The reason this detector is AST-based: `scripts/q48_s55_fomc_lag_probe.py` carries
    `from scripts.q48_s55_fomc_lag_probe import ...` inside its module docstring as a usage
    example. A line-level regex flags it; the AST does not."""
    body = '"""Usage:\n\n    from scripts.q48 import load\n"""\nimport os\n'
    root = _tree(tmp_path, "docstr.py", body)
    assert inv._scripts_cross_import_bootstrap_issues(root) == []


def test_a_from_scripts_inside_a_comment_is_not_a_hit(tmp_path):
    root = _tree(tmp_path, "comment.py", "# from scripts.other import thing\nimport os\n")
    assert inv._scripts_cross_import_bootstrap_issues(root) == []


def test_relative_import_is_not_flagged(tmp_path):
    root = _tree(tmp_path, "rel.py", "from . import other\nfrom .scripts import thing\n")
    assert inv._scripts_cross_import_bootstrap_issues(root) == []


def test_core_only_import_is_not_a_hit(tmp_path):
    root = _tree(tmp_path, "coreonly.py", "from core.pricing import fee_per_contract\n")
    assert inv._scripts_cross_import_bootstrap_issues(root) == []


def test_a_syntax_error_file_is_skipped_and_never_raises(tmp_path):
    root = _tree(tmp_path, "bad.py", "def (:\n")
    (root / "scripts" / "alsobroken.py").write_text("from scripts.other import thing\n")
    assert inv._scripts_cross_import_bootstrap_issues(root) == ["scripts/alsobroken.py:1"]


def test_missing_scripts_dir_returns_empty(tmp_path):
    root = tmp_path / "norepo"
    root.mkdir()
    assert inv._scripts_cross_import_bootstrap_issues(root) == []


def test_multiple_offenders_are_sorted_and_report_the_first_import_only(tmp_path):
    root = _tree(tmp_path, "b_two.py",
                 "import os\nfrom scripts.x import a\nfrom scripts.y import b\n")
    (root / "scripts" / "a_one.py").write_text("from scripts.z import c\n")
    assert inv._scripts_cross_import_bootstrap_issues(root) == [
        "scripts/a_one.py:1",
        "scripts/b_two.py:2",
    ]


def test_warning_is_none_on_no_sites():
    assert inv.scripts_cross_import_bootstrap_warning([]) is None


def test_warning_names_l232_the_count_and_the_advisory_posture():
    msg = inv.scripts_cross_import_bootstrap_warning(["scripts/a.py:1", "scripts/b.py:2"])
    assert msg is not None
    assert "L232" in msg
    assert "2 file(s)" in msg
    assert "non-gating" in msg
    assert "does NOT affect the exit code" in msg
    # The message must publish its blind spots, not just its hits (L155).
    assert "BLIND SPOTS" in msg


def test_warning_truncates_the_example_list():
    msg = inv.scripts_cross_import_bootstrap_warning([f"scripts/f{i}.py:1" for i in range(5)])
    assert "..." in msg and "5 file(s)" in msg


# --- Documented blind spots: regression-tested as MISSES, not as hits --------

def test_blind_spot_sys_path_extend_is_not_recognised_as_a_bootstrap(tmp_path):
    """`sys.path.extend([...])` genuinely works at runtime but this proxy does not see it, so
    it FIRES (a false alarm, documented in the warning text). Pinned so the behaviour is a
    known state, not a surprise."""
    body = (
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.extend([str(Path(__file__).resolve().parents[1])])\n"
        "from scripts.other import thing\n"
    )
    root = _tree(tmp_path, "extend.py", body)
    assert inv._scripts_cross_import_bootstrap_issues(root) == ["scripts/extend.py:4"]


def test_blind_spot_dynamic_import_is_missed(tmp_path):
    body = "import importlib\nmod = importlib.import_module('scripts.other')\n"
    root = _tree(tmp_path, "dyn.py", body)
    assert inv._scripts_cross_import_bootstrap_issues(root) == []


def test_blind_spot_unresolvable_variable_path_is_accepted_permissively(tmp_path):
    body = (
        "import sys\n"
        "sys.path.insert(0, SOMEWHERE)\n"
        "from scripts.other import thing\n"
    )
    root = _tree(tmp_path, "varboot.py", body)
    assert inv._scripts_cross_import_bootstrap_issues(root) == []


# --- Layer 2: real-subprocess acceptance (L232's own mandate) ---------------
#
# An in-process import test proves nothing here: the repo-root conftest.py repairs sys.path
# under pytest and masks exactly the breakage. So these invoke real subprocesses, with
# PYTHONPATH deleted and the working directory moved OUTSIDE the repo.

@pytest.mark.parametrize("script", REPAIRED_SCRIPTS)
def test_direct_cli_invocation_needs_no_pythonpath(script, tmp_path, monkeypatch):
    """The direct-CLI form -- the one kb/00-LOG.md, kb/strategies/00-index.md, LOOP-QUEUE.md
    and findings/ cite for both of these scripts. Before this run both died with
    ModuleNotFoundError: No module named 'scripts'."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), "--help"],
        capture_output=True, text=True, timeout=300,
    )
    assert "No module named 'scripts'" not in proc.stderr, proc.stderr[-2000:]
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "usage:" in proc.stdout


@pytest.mark.parametrize("script", REPAIRED_SCRIPTS)
def test_module_form_invocation_still_works(script, monkeypatch):
    """The bootstrap must not break the module form, run from the repo root."""
    monkeypatch.chdir(ROOT)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    proc = subprocess.run(
        [sys.executable, "-m", "scripts." + script[:-3], "--help"],
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "usage:" in proc.stdout


# --- Layer 3: the live tree, after this run's repair ------------------------

def test_real_tree_has_no_unbootstrapped_scripts_cross_import():
    sites = inv._scripts_cross_import_bootstrap_issues()
    assert sites == [], (
        "L232 violation: these files under scripts/ import the `scripts.` package with no "
        "repo-root sys.path bootstrap ahead of the import, so the direct-CLI form dies with "
        "ModuleNotFoundError while pytest stays green. Add "
        f"`{BOOTSTRAP}` above the import (the scripts/q48_s55_fomc_lag_probe.py pattern) and "
        f"pin it with a real-subprocess test. Sites: {sites}"
    )


def test_real_tree_scan_is_not_vacuous():
    """Non-vacuity first (the L188/L192 discipline): the clean result above is only meaningful
    if the detector actually reached files that DO import the `scripts.` package."""
    import ast as _ast
    reached = 0
    for p in (ROOT / "scripts").rglob("*.py"):
        if inv._excluded_relative_to(ROOT, p):
            continue
        try:
            tree = _ast.parse(p.read_text())
        except Exception:
            continue
        if any(inv._imports_scripts_package(n) for n in _ast.walk(tree)):
            reached += 1
    assert reached >= 10, f"only {reached} scripts/ files import the scripts package"


# --- The EXCLUDE_DIRS scoping defect this run also repaired -----------------

def test_exclude_dirs_are_matched_relative_to_the_repo_root(tmp_path):
    """A repo checked out UNDER an excluded directory name must still be scanned. Before the
    fix, `_iter_source_files` matched EXCLUDE_DIRS on ABSOLUTE parts, so a checkout at
    `.claude/worktrees/agent-*` (where every autonomous run of this repo executes) returned 0
    files for the whole repository -- a vacuous scan that reports exactly what a clean one
    does."""
    root = tmp_path / ".claude" / "worktrees" / "agent-x"
    (root / "core").mkdir(parents=True)
    (root / "core" / "mod.py").write_text("x = 1\n")
    found = inv._iter_source_files(root, exts=(".py",))
    assert [p.name for p in found] == ["mod.py"]


def test_exclude_dirs_inside_the_repo_are_still_excluded(tmp_path):
    root = tmp_path / "repo"
    (root / "core").mkdir(parents=True)
    (root / "core" / "keep.py").write_text("x = 1\n")
    for skipped in ("data", ".venv", "__pycache__"):
        (root / skipped).mkdir(parents=True)
        (root / skipped / "drop.py").write_text("x = 1\n")
    found = inv._iter_source_files(root, exts=(".py",))
    assert [p.name for p in found] == ["keep.py"]


def test_real_tree_source_scan_is_not_vacuous():
    """The regression that motivated the fix: this assertion FAILED (0 files) in every agent
    checkout under `.claude/worktrees/` before 2026-08-02, silently making the Hard-Rule static
    gate (`scan_tree`) and three source-scanning advisories no-ops."""
    files = inv._iter_source_files()
    assert len(files) >= 100, f"static scan reached only {len(files)} source files"
    assert "invariants.py" in {p.name for p in files}


def test_static_gate_scan_tree_reaches_the_tree():
    """`scan_tree()` is the Hard-Rule #1/#2/#3 gate. It must be clean AND non-vacuous."""
    assert inv.scan_tree() == []
    assert len(inv._iter_source_files()) >= 100
