"""scripts/invariants.py — hand-rolled binary settlement-result advisory (L52 enforcement).

L52 (2026-07-14): "Kalshi sports settlement results are not always binary: Q26's live pull of
`fetch_kalshi_settled` over 458 settled markets in 7 sports series returned 8 with
`result:"scalar"`, not `result in {"yes","no"}`. A binary-outcome probe must filter explicitly
on the result field's actual value, never assume 'settled' implies 'yes/no'."

The advisory is a LEXICAL, LINE-SCOPED proxy, so this file is built the way L155 demands:

  * a CONSTRUCTED-POSITIVE corpus of realistic hand-rolled shapes that MUST fire — the recall
    evidence that a small real-tree count can never supply on its own;
  * a CONSTRUCTED-NEGATIVE corpus (guarded-by-"scalar", guarded-by-membership, guarded-by-
    helper-import, order-SIDE comparisons, comments, docstrings, tests/) that must NOT fire;
  * a KNOWN-BLIND-SPOT corpus asserted as MISSES, so widening the rule has to delete a test on
    purpose rather than by accident;
  * HARD acceptance tests over the REAL tree: `execution/fill_models.py`'s order-SIDE
    comparisons must not be reported (precision), the guarded probes must not be reported, and
    every reported site must exist on disk with a real "yes"/"no" comparison on that line
    (asserted as a PROPERTY, so a future cleanup of any one script cannot break this file);
  * exit-code pins: the advisory can never change `invariants.py`'s exit code.

All offline: `tmp_path` corpora plus read-only reads of committed source. No network, no git,
no subprocess, no wall-clock dependence. `core/settlement.py` is referenced only by NAME (the
detector never imports it), so these tests pass whether or not that module exists yet.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_engine():
    spec = importlib.util.spec_from_file_location(
        "inv_engine_settlement", ROOT / "scripts" / "invariants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inv = _load_engine()


def _tree(tmp_path: pathlib.Path, name: str, body: str) -> pathlib.Path:
    """Write one .py file into a fresh root and return that root."""
    root = tmp_path / name.replace("/", "_").replace(".py", "")
    (root / pathlib.Path(name).parent).mkdir(parents=True, exist_ok=True)
    (root / name).write_text(body, encoding="utf-8")
    return root


def _sites(tmp_path: pathlib.Path, name: str, body: str):
    return inv._handrolled_binary_result_sites(_tree(tmp_path, name, body))


# ─── constructed POSITIVES: hand-rolled shapes that must FIRE ───────────────
_POSITIVE_SHAPES = [
    pytest.param(
        'if result == "yes":\n    wins += 1\n',
        id="bare-result-eq-yes"),
    pytest.param(
        'if entry["result"] == "no":\n    losses += 1\n',
        id="subscripted-result-eq-no"),
    pytest.param(
        'won = [k for k, v in results.items() if v == "yes"]\n',
        id="comprehension-over-results-map"),
    pytest.param(
        'if "yes" == result:\n    pass\n',
        id="mirrored-yes-eq-result"),
    pytest.param(
        'if row.result != "yes":\n    continue\n',
        id="attribute-result-neq-yes"),
    pytest.param(
        'hit = settlement["result"] == "yes"\n',
        id="settle-token-and-result-token"),
    pytest.param(
        'gross = (1.0 if outcome == "no" else 0.0) - entry\n',
        id="outcome-token-inline-conditional"),
    pytest.param(
        'if m.get("settled_result") == "yes":\n    pass\n',
        id="settle-prefixed-field"),
]


@pytest.mark.parametrize("body", _POSITIVE_SHAPES)
def test_handrolled_shape_is_reported(tmp_path, body):
    sites = _sites(tmp_path, "probe.py", body)
    assert sites, f"expected a hit for:\n{body}"
    assert all(s.startswith("probe.py:") for s in sites)


def test_reported_label_is_relpath_and_1_based_line():
    """The label shape other tooling reads: `relpath:line`, line 1-based."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "pkg").mkdir()
        (root / "pkg" / "probe.py").write_text(
            "x = 1\ny = 2\nif result == \"yes\":\n    pass\n", encoding="utf-8")
        assert inv._handrolled_binary_result_sites(root) == ["pkg/probe.py:3"]


# ─── constructed NEGATIVES: shapes that must NOT fire ──────────────────────
_NEGATIVE_SHAPES = [
    pytest.param(
        'if result == "scalar":\n    skip += 1\nif result == "yes":\n    wins += 1\n',
        id="guarded-by-scalar-literal"),
    pytest.param(
        'if result not in ("yes", "no"):\n    continue\nif result == "yes":\n    w += 1\n',
        id="guarded-by-not-in-tuple"),
    pytest.param(
        'if res in {"no", "yes"}:\n    pass\nif res == "yes" and result:\n    pass\n',
        id="guarded-by-in-set-reversed-order"),
    pytest.param(
        'if r in ["yes", "no"]:\n    pass\nif result == "no":\n    pass\n',
        id="guarded-by-in-list"),
    pytest.param(
        'from core.settlement import binary_outcome\nif result == "yes":\n    pass\n',
        id="guarded-by-helper-import"),
    pytest.param(
        'from core import settlement\nif result == "yes":\n    pass\n',
        id="guarded-by-module-import"),
    pytest.param(
        'ok = is_binary_result(r)\nif result == "yes":\n    pass\n',
        id="guarded-by-is_binary_result"),
    pytest.param(
        'rows = filter_binary_settlements(rows)\nif result == "yes":\n    pass\n',
        id="guarded-by-filter_binary_settlements"),
    pytest.param(
        'rows = filter_binary_results_map(rows)\nif result == "yes":\n    pass\n',
        id="guarded-by-filter_binary_results_map"),
    pytest.param(
        'require_binary_result(r)\nif result == "yes":\n    pass\n',
        id="guarded-by-require_binary_result"),
    pytest.param(
        'if side == "yes":\n    pass\nif order.side != "no":\n    pass\n',
        id="order-side-comparison-no-settlement-token"),
    pytest.param(
        '# if result == "yes": legacy read, replaced\nx = 1\n',
        id="comment-only-hit"),
    pytest.param(
        '"""Settlement: YES pays $1 if result == "yes"."""\nx = 1\n',
        id="module-docstring-only-hit"),
    pytest.param(
        'def f():\n    """gross = 1 if result == "no" else 0."""\n    return 0\n',
        id="function-docstring-only-hit"),
    pytest.param(
        'class C:\n    """Pays out when result == "yes"."""\n    x = 1\n',
        id="class-docstring-only-hit"),
    pytest.param(
        'if result == "maybe":\n    pass\n',
        id="non-binary-literal"),
    pytest.param(
        'if result >= "yes":\n    pass\n',
        id="non-equality-operator"),
]


@pytest.mark.parametrize("body", _NEGATIVE_SHAPES)
def test_clean_shape_is_not_reported(tmp_path, body):
    assert _sites(tmp_path, "probe.py", body) == [], f"unexpected hit for:\n{body}"


def test_tests_directory_is_skipped(tmp_path):
    """tests/ fixtures deliberately construct the bad shape."""
    assert _sites(tmp_path, "tests/test_x.py", 'if result == "yes":\n    pass\n') == []


def test_sanctioned_helper_module_is_exempt(tmp_path):
    """core/settlement.py must define the literals it filters on; exempt by path, so this holds
    even for a hypothetical future version carrying no 'scalar' literal."""
    assert inv.HANDROLLED_BINARY_RESULT_EXEMPT == ("core/settlement.py",)
    root = tmp_path / "r"
    (root / "core").mkdir(parents=True)
    (root / "core" / "settlement.py").write_text(
        'def binary(r):\n    return r == "yes"  # result\n', encoding="utf-8")
    assert inv._handrolled_binary_result_sites(root) == []


def test_multiple_hits_in_one_file_are_all_reported(tmp_path):
    body = 'if result == "yes":\n    pass\nif result == "no":\n    pass\n'
    assert _sites(tmp_path, "probe.py", body) == ["probe.py:1", "probe.py:3"]


def test_docstring_exclusion_does_not_hide_real_code_in_the_same_file(tmp_path):
    """The weather_rehab_s5.py shape exactly: prose in the module docstring, real read below."""
    body = (
        '"""Backtest.\n\nSettlement: YES pays $1 if result == "yes".\n'
        'NO pays $1 if result == "no".\n"""\n'
        'x = 1\n'
        'won = [tk for tk in tickers if members[tk]["result"] == "yes"]\n'
    )
    assert _sites(tmp_path, "probe.py", body) == ["probe.py:7"]


# ─── KNOWN BLIND SPOTS: genuine violations the rule deliberately MISSES ────
_BLIND_SPOT_SHAPES = [
    pytest.param(
        'res = rec["result"]\nif res == "yes":\n    pass\n',
        id="settlement-token-on-an-earlier-line"),
    pytest.param(
        'if result.startswith("y"):\n    pass\n',
        id="non-comparison-form"),
    pytest.param(
        'if result == VALUES[0]:\n    pass\n',
        id="literal-behind-a-constant"),
    pytest.param(
        'if (result ==\n        "yes"):\n    pass\n',
        id="comparison-split-across-lines"),
]


@pytest.mark.parametrize("body", _BLIND_SPOT_SHAPES)
def test_known_blind_spot_is_a_miss(tmp_path, body):
    """Asserted as MISSES so that widening the rule must delete a case on purpose. Each of
    these IS a real hand-rolled binary read; closing them needs dataflow, not a wider regex."""
    assert _sites(tmp_path, "probe.py", body) == []


def test_blind_spots_are_named_in_the_warning_text():
    msg = inv.handrolled_binary_result_warning(["a.py:1"])
    assert "KNOWN BLIND SPOTS" in msg
    assert "probe_ladder_coherence.py:140" in msg
    assert "file-level guard granularity" in msg


# ─── robustness: a broken file can never poison the scan ──────────────────
def test_unparseable_file_does_not_raise_and_still_scans(tmp_path):
    """AST docstring exclusion falls back to 'no exclusion'; the line scan still runs, and the
    rest of the tree is unaffected."""
    root = tmp_path / "r"
    root.mkdir()
    (root / "broken.py").write_text(
        'def f(:\n    pass\nif result == "yes":\n    pass\n', encoding="utf-8")
    (root / "good.py").write_text('if result == "no":\n    pass\n', encoding="utf-8")
    sites = inv._handrolled_binary_result_sites(root)
    assert "good.py:1" in sites
    assert "broken.py:3" in sites


def test_unreadable_file_is_skipped_not_fatal(tmp_path, monkeypatch):
    root = tmp_path / "r"
    root.mkdir()
    (root / "boom.py").write_text('if result == "yes":\n    pass\n', encoding="utf-8")
    real_read = pathlib.Path.read_text

    def _read(self, *a, **k):
        if self.name == "boom.py":
            raise OSError("nope")
        return real_read(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_text", _read)
    assert inv._handrolled_binary_result_sites(root) == []


def test_missing_root_returns_empty(tmp_path):
    assert inv._handrolled_binary_result_sites(tmp_path / "does-not-exist") == []


# ─── the warning formatter ─────────────────────────────────────────────────
def test_warning_is_none_when_clean():
    assert inv.handrolled_binary_result_warning([]) is None


def test_warning_states_count_examples_and_lesson():
    sites = [f"scripts/p{i}.py:{i}" for i in range(1, 6)]
    msg = inv.handrolled_binary_result_warning(sites)
    assert isinstance(msg, str)
    assert "non-gating" in msg
    assert "5 production site(s)" in msg
    assert "L52" in msg and "L155" in msg
    assert "scripts/p1.py:1" in msg and "scripts/p3.py:3" in msg
    assert "scripts/p4.py:4" not in msg      # capped at 3 examples
    assert ", ..." in msg
    assert "does NOT affect the exit code" in msg


def test_warning_cites_the_real_l52_numbers_and_the_sanctioned_fix():
    msg = inv.handrolled_binary_result_warning(["a.py:1"])
    assert "458" in msg and "8 with" in msg and 'result:"scalar"' in msg
    assert "core.settlement.filter_binary_settlements" in msg
    assert "core.settlement.binary_outcome" in msg
    assert "COVERAGE (lexical proxy, line-scoped, tested shapes only)" in msg
    assert "PRECISION evidence, not RECALL" in msg


# ─── HARD acceptance tests against the REAL tree ──────────────────────────
_REAL_SITES = inv._handrolled_binary_result_sites()

# Files independently known to carry an explicit binary-result guard (2026-07-25 tree).
_GUARDED_REAL_FILES = (
    "scripts/longshot_fade_probe.py",
    "scripts/q24_sports_longshot_maker_fillsim.py",
    "scripts/q26_ofi_depth_imbalance_probe.py",
    "scripts/q27_favorite_underpricing_fillsim.py",
    "scripts/q28_s24_nearclose_fade_probe.py",
    "scripts/q29_settlement_lag_probe.py",
    "scripts/q30_draw_aversion_maker_probe.py",
    "scripts/q37_weather_summer_makerno_probe.py",
    "scripts/s10_reachability_probe.py",
    "scripts/sports_clv_s7.py",
)


def test_acceptance_order_side_comparisons_are_not_reported():
    """PRECISION anchor. execution/fill_models.py compares an ORDER SIDE (`side == "yes"`,
    `order.side != "no"`), never a settlement result — the same-line settlement-token
    requirement is what excludes it. If this ever fails, the rule got too wide."""
    assert not [s for s in _REAL_SITES if s.startswith("execution/fill_models.py:")]


@pytest.mark.parametrize("rel", _GUARDED_REAL_FILES)
def test_acceptance_guarded_real_file_is_not_reported(rel):
    assert (ROOT / rel).is_file(), f"{rel} vanished — update this list deliberately"
    assert not [s for s in _REAL_SITES if s.startswith(rel + ":")]


def test_acceptance_at_least_one_real_unguarded_site_is_found():
    """Recall anchor on the real tree. Deliberately a COUNT, not a frozen file list, so a
    future cleanup of any one script cannot break this file."""
    assert _REAL_SITES, "expected >=1 unguarded hand-rolled binary-result site on the tree"


def test_acceptance_every_reported_site_is_real():
    """Each label points at a file on disk whose reported line really carries a "yes"/"no"
    comparison AND a settlement token — the property, not a frozen list."""
    for site in _REAL_SITES:
        rel, _, lineno = site.rpartition(":")
        p = ROOT / rel
        assert p.is_file(), f"{site} does not exist on disk"
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        n = int(lineno)
        assert 1 <= n <= len(lines), f"{site} is out of range"
        line = lines[n - 1]
        assert inv._BINARY_RESULT_CMP_RE.search(line), f"{site}: {line!r}"
        assert inv._SETTLEMENT_TOKEN_RE.search(line), f"{site}: {line!r}"
        assert not line.lstrip().startswith("#"), f"{site} is a comment"


def test_acceptance_known_real_blind_spot_stays_a_miss():
    """`scripts/probe_ladder_coherence.py:140` (`if res == "yes":`) IS a genuine unguarded
    settlement read, but its settlement token is on an earlier line. Pinned as a MISS so the
    warning text's honesty claim stays true; if a future rule catches it, update BOTH."""
    p = ROOT / "scripts" / "probe_ladder_coherence.py"
    if not p.is_file():
        pytest.skip("probe_ladder_coherence.py no longer present")
    assert not [s for s in _REAL_SITES if s.startswith("scripts/probe_ladder_coherence.py:")]


def test_acceptance_no_site_lives_under_tests():
    assert not [s for s in _REAL_SITES if s.startswith("tests/")]


# ─── exit-code pins: the advisory can NEVER gate ──────────────────────────
def _stub_expensive_checks(monkeypatch):
    """Neuter every OTHER whole-tree/whole-tape scan in main()'s --full branch so these
    exit-code tests are fast. The L52 path under test is left fully real."""
    monkeypatch.setattr(inv, "scan_tree", lambda *a, **k: [])
    for name in ("_git_tape_refs", "_tape_dir_shape_issues",
                 "_tape_dir_shape_orphan_classification", "_daily_family_gap_issues",
                 "_unregistered_single_hour_leg_issues", "_raw_datetime_fromisoformat_sites",
                 "_ladder_size_coercion_issues", "_duplicate_lesson_id_issues",
                 "_stale_unenforced_candidate_issues", "_recovery_dwell_issues",
                 "_tape_conflict_marker_issues", "_tape_invalid_jsonl_issues"):
        monkeypatch.setattr(inv, name, lambda *a, **k: [])
    monkeypatch.setattr(inv, "_dead_collector_leg_diagnosis", lambda *a, **k: None)


def _run_main(monkeypatch) -> int:
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    return inv.main()


def test_real_firing_advisory_still_exits_zero(monkeypatch, capsys):
    """Control + the load-bearing property: the advisory DOES fire on the real tree today, and
    the run still exits 0."""
    _stub_expensive_checks(monkeypatch)
    assert _run_main(monkeypatch) == 0
    assert "bare \"yes\"/\"no\" literal" in capsys.readouterr().err


def test_detector_that_raises_does_not_change_the_exit_code(monkeypatch, capsys):
    _stub_expensive_checks(monkeypatch)

    def _boom(*a, **k):
        raise RuntimeError("detector blew up")

    monkeypatch.setattr(inv, "_handrolled_binary_result_sites", _boom)
    assert _run_main(monkeypatch) == 0
    assert "binary-settlement-result advisory could not be computed" in capsys.readouterr().err


def test_formatter_returning_a_non_str_does_not_change_the_exit_code(monkeypatch, capsys):
    """`warning + "\\n"` on a non-str is a TypeError at the CALL SITE, outside any guard the
    formatter itself could carry."""
    _stub_expensive_checks(monkeypatch)
    monkeypatch.setattr(inv, "handrolled_binary_result_warning", lambda _s: 7)
    assert _run_main(monkeypatch) == 0
    assert "binary-settlement-result advisory could not be computed" in capsys.readouterr().err


def test_base_exception_in_the_advisory_path_does_not_change_the_exit_code(monkeypatch, capsys):
    def _sys_exit(*a, **k):
        raise SystemExit(3)

    _stub_expensive_checks(monkeypatch)
    monkeypatch.setattr(inv, "handrolled_binary_result_warning", _sys_exit)
    assert _run_main(monkeypatch) == 0
    assert "binary-settlement-result advisory could not be computed" in capsys.readouterr().err


def test_advisory_is_non_gating_by_construction():
    """`main()` writes it to stderr and never appends it to `failures` (the gating list)."""
    src = (ROOT / "scripts" / "invariants.py").read_text(encoding="utf-8")
    i = src.index("binres_warning = handrolled_binary_result_warning(")
    block = src[i:i + 400]
    assert "sys.stderr.write(binres_warning" in block
    assert "failures.append(binres_warning" not in src
    assert "failures.append(handrolled_binary_result_warning" not in src


def test_advisory_is_not_wired_into_the_pre_edit_hook_or_db_paths():
    """--pre-edit-hook is a single-file fast path and --db is a SQLite path; a whole-tree
    lexical scan belongs to neither."""
    import inspect
    hook_src = inspect.getsource(inv.handle_pre_edit_hook)
    assert "handrolled_binary_result" not in hook_src
    assert "handrolled_binary_result" not in inspect.getsource(inv.scan_tree)
    assert "handrolled_binary_result" not in inspect.getsource(inv.scan_db)


def test_advisory_path_touches_no_network_or_subprocess():
    """Offline contract: the detector reads files only."""
    import inspect
    src = (inspect.getsource(inv._handrolled_binary_result_sites)
           + inspect.getsource(inv._docstring_line_numbers)
           + inspect.getsource(inv.handrolled_binary_result_warning))
    for banned in ("subprocess.", "requests.", "urllib.", "socket.", "os.popen", "os.system"):
        assert banned not in src


def test_detector_does_not_import_the_sanctioned_helper():
    """It references core.settlement by NAME only, so the advisory works whether or not that
    module exists yet."""
    import inspect
    src = inspect.getsource(inv._handrolled_binary_result_sites)
    assert "import core.settlement" not in src
    assert "importlib" not in src
