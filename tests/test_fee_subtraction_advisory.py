"""scripts/invariants.py — hand-rolled fee-subtraction advisory (L228 enforcement).

L228 (2026-07-29): `scripts/s17_leadlag_probe.py`'s burst dislocation scan charged the
Polymarket leg a flat `--poly-fee` CLI parameter (defaulting to 0.0) for 16 days after the
sibling `s9_leadlag_probe.py` was corrected to route through
`core.pricing.polymarket_fee_per_contract` — wrong in BOTH directions (0.0 under-charges and
manufactures phantom dislocations; a naive flat 0.05 over-charges ~4x at mid prices) and
load-bearing on the verdict (0 / 34 / 49 fee-clearing captures under three fee views on one
identical tape). That file is fixed; this is the general rule L228 itself named as still open:
a `*_fee`-named scalar (dollar amount, not a rate) must never be added/subtracted into an
expression without tracing back to a `core.pricing` fee-schedule call.

Unlike its L52 sibling, this check is AST-based, not lexical — a first line-regex draft flagged
45 real-tree sites, and every one was a hyphen inside a STRING (argparse help text, printed
prose like `"(pre-fee)"`/`"--poly-fee-model"`/`"- fee floor: {}"`), never real arithmetic. This
file is built the way L155 demands regardless of proxy shape:

  * a CONSTRUCTED-POSITIVE corpus of realistic hand-rolled shapes that MUST fire;
  * a CONSTRUCTED-NEGATIVE corpus (direct schedule call, one-hop local helper, aliased module
    prefix, augmented-assign accumulator, rate-suffixed names, string/docstring/comment
    look-alikes, `tests/`, `core/pricing.py`) that must NOT fire;
  * a KNOWN-BLIND-SPOT corpus asserted as MISSES, so widening the rule has to delete a test on
    purpose rather than by accident;
  * HARD acceptance tests over the REAL tree;
  * exit-code pins: the advisory can never change `invariants.py`'s exit code.

All offline: `tmp_path` corpora plus read-only reads of committed source. No network, no git,
no subprocess, no wall-clock dependence.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_engine():
    spec = importlib.util.spec_from_file_location(
        "inv_engine_fee_subtraction", ROOT / "scripts" / "invariants.py")
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
    return inv._handrolled_fee_subtraction_sites(_tree(tmp_path, name, body))


# ─── constructed POSITIVES: hand-rolled shapes that must FIRE ───────────────
_POSITIVE_SHAPES = [
    pytest.param(
        'def f(edge, poly_fee):\n    return edge - poly_fee\n',
        id="unbound-fee-subtracted"),
    pytest.param(
        'def f(edge, kalshi_fee):\n    return kalshi_fee + edge\n',
        id="unbound-fee-added-left-operand"),
    pytest.param(
        'def f(xs, poly_fee):\n    total = 0.0\n    for x in xs:\n        total -= poly_fee\n'
        '    return total\n',
        id="unbound-fee-in-augassign-value"),
    pytest.param(
        'poly_fee = float(input())\n\n\ndef f(edge):\n    return edge - poly_fee\n',
        id="module-level-unbound-fee"),
    pytest.param(
        'def f(edge):\n    fee = 0.05\n    return edge - fee\n',
        id="bare-fee-hardcoded-literal"),
]


@pytest.mark.parametrize("body", _POSITIVE_SHAPES)
def test_handrolled_shape_is_reported(tmp_path, body):
    sites = _sites(tmp_path, "probe.py", body)
    assert sites, f"expected a hit for:\n{body}"
    assert all(s.startswith("probe.py:") for s in sites)


def test_reported_label_is_relpath_and_1_based_line(tmp_path):
    root = tmp_path / "r"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "probe.py").write_text(
        "x = 1\ny = 2\ndef f(edge, poly_fee):\n    return edge - poly_fee\n", encoding="utf-8")
    assert inv._handrolled_fee_subtraction_sites(root) == ["pkg/probe.py:4"]


# ─── constructed NEGATIVES: shapes that must NOT fire ──────────────────────
_NEGATIVE_SHAPES = [
    pytest.param(
        'from core.pricing import fee_per_contract\n\n\n'
        'def f(edge, price, rate):\n    poly_fee = fee_per_contract(price, rate)\n'
        '    return edge - poly_fee\n',
        id="bound-direct-bare-call"),
    pytest.param(
        'import core.pricing\n\n\n'
        'def f(edge, price, rate):\n'
        '    poly_fee = core.pricing.polymarket_fee_per_contract(price, rate)\n'
        '    return edge - poly_fee\n',
        id="bound-direct-fully-qualified-call"),
    pytest.param(
        'from core import pricing\n\n\n'
        'def f(edge, price, rate):\n    fee = pricing.fee_per_contract(price, rate)\n'
        '    return edge - fee\n',
        id="bound-direct-aliased-module-prefix"),
    pytest.param(
        'from core.pricing import fee_per_contract, MAKER_FEE_RATE\n\n\n'
        'def member_fee(p):\n    return fee_per_contract(1.0 - p, rate=MAKER_FEE_RATE)\n\n\n'
        'def f(premium, edge):\n    fee = member_fee(premium)\n    return edge - fee\n',
        id="bound-via-one-hop-local-helper"),
    pytest.param(
        'from core.pricing import TAKER_FEE_RATE\n\nFEE_COEFF = TAKER_FEE_RATE\n\n\n'
        'def taker_fee(p):\n    return FEE_COEFF * p * (1.0 - p)\n\n\n'
        'def f(p, edge):\n    fee = taker_fee(p)\n    return edge - fee\n',
        id="bound-via-local-helper-referencing-aliased-rate-constant"),
    pytest.param(
        'from core.pricing import fee_per_contract\n\n\n'
        'def f(prices, edge):\n    total_fee = 0.0\n    for p in prices:\n'
        '        total_fee += fee_per_contract(p, rate=0.03)\n'
        '    return edge - total_fee\n',
        id="bound-via-augassign-accumulator"),
    pytest.param(
        'def f(edge, poly_fee_rate):\n    return edge - poly_fee_rate\n',
        id="rate-suffixed-name-is-not-a-fee-amount"),
    pytest.param(
        'def f(edge, fee_per_contract):\n    return edge - fee_per_contract\n',
        id="the-schedule-function-name-itself-is-not-a-fee-amount"),
    pytest.param(
        'def f(mu, sigma):\n    return "(pre-fee) bracket price"\n',
        id="hyphenated-word-inside-a-string-literal"),
    pytest.param(
        'import argparse\n\n\n'
        'def build():\n    ap = argparse.ArgumentParser()\n'
        '    ap.add_argument("--poly-fee-model", default="schedule")\n    return ap\n',
        id="hyphenated-cli-flag-inside-a-help-string"),
    pytest.param(
        'def report(fee):\n    return "- fee floor: {}".format(fee)\n',
        id="bullet-dash-inside-a-printed-string"),
    pytest.param(
        '# def f(edge, poly_fee):\n#     return edge - poly_fee\nx = 1\n',
        id="comment-only-hit"),
    pytest.param(
        '"""net = edge - poly_fee, unbound on purpose in this docstring example."""\nx = 1\n',
        id="module-docstring-only-hit"),
]


@pytest.mark.parametrize("body", _NEGATIVE_SHAPES)
def test_clean_shape_is_not_reported(tmp_path, body):
    assert _sites(tmp_path, "probe.py", body) == [], f"unexpected hit for:\n{body}"


def test_tests_directory_is_skipped(tmp_path):
    body = 'def f(edge, poly_fee):\n    return edge - poly_fee\n'
    assert _sites(tmp_path, "tests/test_x.py", body) == []


def test_sanctioned_pricing_module_itself_is_exempt(tmp_path):
    assert inv.HANDROLLED_FEE_SUBTRACTION_EXEMPT == ("core/pricing.py",)
    root = tmp_path / "r"
    (root / "core").mkdir(parents=True)
    (root / "core" / "pricing.py").write_text(
        'def fee_per_contract(price, rate=0.03):\n'
        '    def helper(edge, poly_fee):\n        return edge - poly_fee\n'
        '    return price * rate\n', encoding="utf-8")
    assert inv._handrolled_fee_subtraction_sites(root) == []


def test_multiple_hits_in_one_file_are_all_reported(tmp_path):
    body = (
        'def f(edge, poly_fee):\n    return edge - poly_fee\n\n\n'
        'def g(edge, kalshi_fee):\n    return edge - kalshi_fee\n'
    )
    assert _sites(tmp_path, "probe.py", body) == ["probe.py:2", "probe.py:6"]


def test_nested_function_uses_its_own_innermost_scope(tmp_path):
    """A nested function's OWN local binding must be found before falling back to the outer
    scope, and vice versa: the outer scope's fee var is invisible if a nested fn shadows it
    with an unbound one of the same name."""
    body = (
        'from core.pricing import fee_per_contract\n\n\n'
        'def outer(edge, price, rate):\n'
        '    poly_fee = fee_per_contract(price, rate)\n'
        '    def inner(x, poly_fee):\n'
        '        return x - poly_fee\n'
        '    return edge - poly_fee, inner\n'
    )
    sites = _sites(tmp_path, "probe.py", body)
    assert "probe.py:6" in sites          # inner()'s own unbound parameter
    assert "probe.py:7" not in sites      # outer's poly_fee IS bound in outer's own scope


# ─── KNOWN BLIND SPOTS: genuine violations the rule deliberately MISSES ────
_BLIND_SPOT_SHAPES = [
    pytest.param(
        'from other_module import maker_fee\n\n\n'
        'def f(price, edge):\n    fee = maker_fee(price)\n    return edge - fee\n',
        id="helper-imported-from-another-file"),
    pytest.param(
        'from core.pricing import fee_per_contract\n\n\n'
        'def inner_fee(p):\n    return fee_per_contract(p, rate=0.03)\n\n\n'
        'def outer_fee(p):\n    return inner_fee(p) * 1.0\n\n\n'
        'def f(p, edge):\n    fee = outer_fee(p)\n    return edge - fee\n',
        id="two-hop-local-helper-chain"),
]


@pytest.mark.parametrize("body", _BLIND_SPOT_SHAPES)
def test_known_blind_spot_is_a_miss(tmp_path, body):
    """Asserted as MISSES so widening the rule must delete a case on purpose. Each of these IS
    a genuinely clean fee, wrongly reported as a hit by the current one-hop rule."""
    assert _sites(tmp_path, "probe.py", body) != []


def test_blind_spots_are_named_in_the_warning_text():
    msg = inv.handrolled_fee_subtraction_warning(["a.py:1"])
    assert "KNOWN BLIND SPOTS" in msg
    assert "imported from ANOTHER file" in msg
    assert "chain of local helpers" in msg


# ─── robustness: a broken file can never poison the scan ──────────────────
def test_unparseable_file_does_not_raise_and_still_scans(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    (root / "broken.py").write_text('def f(:\n    pass\n', encoding="utf-8")
    (root / "good.py").write_text(
        'def f(edge, poly_fee):\n    return edge - poly_fee\n', encoding="utf-8")
    sites = inv._handrolled_fee_subtraction_sites(root)
    assert "good.py:2" in sites
    assert not [s for s in sites if s.startswith("broken.py:")]


def test_unreadable_file_is_skipped_not_fatal(tmp_path, monkeypatch):
    root = tmp_path / "r"
    root.mkdir()
    (root / "boom.py").write_text(
        'def f(edge, poly_fee):\n    return edge - poly_fee\n', encoding="utf-8")
    real_read = pathlib.Path.read_text

    def _read(self, *a, **k):
        if self.name == "boom.py":
            raise OSError("nope")
        return real_read(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_text", _read)
    assert inv._handrolled_fee_subtraction_sites(root) == []


def test_missing_root_returns_empty(tmp_path):
    assert inv._handrolled_fee_subtraction_sites(tmp_path / "does-not-exist") == []


def test_file_with_no_fee_substring_is_skipped_cheaply(tmp_path):
    """The `"fee" not in text.lower()` prefilter must never cause a false negative — only skip
    parsing files that could not possibly contain a hit."""
    root = tmp_path / "r"
    root.mkdir()
    (root / "clean.py").write_text('def f(edge, cost):\n    return edge - cost\n',
                                    encoding="utf-8")
    assert inv._handrolled_fee_subtraction_sites(root) == []


# ─── the warning formatter ─────────────────────────────────────────────────
def test_warning_is_none_when_clean():
    assert inv.handrolled_fee_subtraction_warning([]) is None


def test_warning_states_count_examples_and_lesson():
    sites = [f"scripts/p{i}.py:{i}" for i in range(1, 6)]
    msg = inv.handrolled_fee_subtraction_warning(sites)
    assert isinstance(msg, str)
    assert "non-gating" in msg
    assert "5 production site(s)" in msg
    assert "L228" in msg and "L155" in msg
    assert "scripts/p1.py:1" in msg and "scripts/p3.py:3" in msg
    assert "scripts/p4.py:4" not in msg      # capped at 3 examples
    assert ", ..." in msg
    assert "does NOT affect the exit code" in msg


def test_warning_cites_the_real_l228_numbers_and_the_sanctioned_fix():
    msg = inv.handrolled_fee_subtraction_warning(["a.py:1"])
    assert "s17_leadlag_probe.py" in msg
    assert "0 / 34 / 49" in msg
    assert "core.pricing.fee_per_contract" in msg or "fee_per_contract" in msg
    assert "COVERAGE (AST-based, per-function-scoped proxy, tested shapes only)" in msg
    assert "PRECISION evidence, not RECALL" in msg


# ─── HARD acceptance tests against the REAL tree ──────────────────────────
_REAL_SITES = inv._handrolled_fee_subtraction_sites()

# Files independently known to route every fee through core.pricing, either directly, via a
# same-module helper, or via an augmented-assign accumulator (2026-08-07 tree).
_CLEAN_REAL_FILES = (
    "scripts/q31_cross_venue_arb_probe.py",
    "scripts/s9_leadlag_probe.py",
    "scripts/s17_leadlag_probe.py",
    "scripts/q24_sports_longshot_maker_fillsim.py",
    "scripts/s19_wing_fade_fillsim.py",
    "scripts/seed5_funding_prior_probe.py",
)


@pytest.mark.parametrize("rel", _CLEAN_REAL_FILES)
def test_acceptance_clean_real_file_is_not_reported(rel):
    assert (ROOT / rel).is_file(), f"{rel} vanished — update this list deliberately"
    assert not [s for s in _REAL_SITES if s.startswith(rel + ":")]


def test_acceptance_known_real_blind_spot_stays_a_miss():
    """`scripts/q30_draw_aversion_maker_probe.py`'s `maker_fee` is imported from
    `scripts/q27_favorite_underpricing_fillsim.py` (a genuinely clean helper); pinned as a MISS
    so the warning text's honesty claim stays true. If a future cross-file resolution pass
    catches it, update BOTH this test and the warning text."""
    p = ROOT / "scripts" / "q30_draw_aversion_maker_probe.py"
    if not p.is_file():
        pytest.skip("q30_draw_aversion_maker_probe.py no longer present")
    assert [s for s in _REAL_SITES if s.startswith("scripts/q30_draw_aversion_maker_probe.py:")]


def test_acceptance_every_reported_site_is_real():
    """Each label points at a file on disk whose reported line really carries an `ast.Name`
    fee-token operand of a `+`/`-` — the property, not a frozen list."""
    import ast as _ast
    for site in _REAL_SITES:
        rel, _, lineno = site.rpartition(":")
        p = ROOT / rel
        assert p.is_file(), f"{site} does not exist on disk"
        text = p.read_text(encoding="utf-8", errors="replace")
        tree = _ast.parse(text)
        hits = inv._fee_arith_name_hits(tree)
        assert int(lineno) in {ln for ln, _ in hits}, f"{site}: no AST fee-arith hit found"


def test_acceptance_no_site_lives_under_tests():
    assert not [s for s in _REAL_SITES if s.startswith("tests/")]


def test_acceptance_no_site_in_core_pricing_itself():
    assert not [s for s in _REAL_SITES if s.startswith("core/pricing.py:")]


# ─── exit-code pins: the advisory can NEVER gate ──────────────────────────
def _stub_expensive_checks(monkeypatch):
    """Neuter every OTHER whole-tree/whole-tape scan in main()'s --full branch so these
    exit-code tests are fast. The L228 path under test is left fully real."""
    monkeypatch.setattr(inv, "scan_tree", lambda *a, **k: [])
    for name in ("_git_tape_refs", "_tape_dir_shape_issues",
                 "_tape_dir_shape_orphan_classification", "_daily_family_gap_issues",
                 "_unregistered_single_hour_leg_issues", "_raw_datetime_fromisoformat_sites",
                 "_ladder_size_coercion_issues", "_duplicate_lesson_id_issues",
                 "_stale_unenforced_candidate_issues", "_recovery_dwell_issues",
                 "_handrolled_binary_result_sites", "_tape_conflict_marker_issues",
                 "_tape_invalid_jsonl_issues"):
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
    assert "*_fee`-named scalar" in capsys.readouterr().err


def test_detector_that_raises_does_not_change_the_exit_code(monkeypatch, capsys):
    _stub_expensive_checks(monkeypatch)

    def _boom(*a, **k):
        raise RuntimeError("detector blew up")

    monkeypatch.setattr(inv, "_handrolled_fee_subtraction_sites", _boom)
    assert _run_main(monkeypatch) == 0
    assert "fee-subtraction advisory could not be computed" in capsys.readouterr().err


def test_formatter_returning_a_non_str_does_not_change_the_exit_code(monkeypatch, capsys):
    """`warning + "\\n"` on a non-str is a TypeError at the CALL SITE, outside any guard the
    formatter itself could carry."""
    _stub_expensive_checks(monkeypatch)
    monkeypatch.setattr(inv, "handrolled_fee_subtraction_warning", lambda _s: 7)
    assert _run_main(monkeypatch) == 0
    assert "fee-subtraction advisory could not be computed" in capsys.readouterr().err


def test_base_exception_in_the_advisory_path_does_not_change_the_exit_code(monkeypatch, capsys):
    def _sys_exit(*a, **k):
        raise SystemExit(3)

    _stub_expensive_checks(monkeypatch)
    monkeypatch.setattr(inv, "handrolled_fee_subtraction_warning", _sys_exit)
    assert _run_main(monkeypatch) == 0
    assert "fee-subtraction advisory could not be computed" in capsys.readouterr().err


def test_advisory_is_non_gating_by_construction():
    """`main()` writes it to stderr and never appends it to `failures` (the gating list)."""
    src = (ROOT / "scripts" / "invariants.py").read_text(encoding="utf-8")
    i = src.index("fee_sub_warning = handrolled_fee_subtraction_warning(")
    block = src[i:i + 400]
    assert "sys.stderr.write(fee_sub_warning" in block
    assert "failures.append(fee_sub_warning" not in src
    assert "failures.append(handrolled_fee_subtraction_warning" not in src


def test_advisory_is_not_wired_into_the_pre_edit_hook_or_db_paths():
    import inspect
    hook_src = inspect.getsource(inv.handle_pre_edit_hook)
    assert "handrolled_fee_subtraction" not in hook_src
    assert "handrolled_fee_subtraction" not in inspect.getsource(inv.scan_tree)
    assert "handrolled_fee_subtraction" not in inspect.getsource(inv.scan_db)


def test_advisory_path_touches_no_network_or_subprocess():
    import inspect
    src = (inspect.getsource(inv._handrolled_fee_subtraction_sites)
           + inspect.getsource(inv._fee_arith_name_hits)
           + inspect.getsource(inv._fee_identifier_is_sanctioned)
           + inspect.getsource(inv._locally_sanctioned_fee_helpers)
           + inspect.getsource(inv._module_rate_aliases)
           + inspect.getsource(inv.handrolled_fee_subtraction_warning))
    for banned in ("subprocess.", "requests.", "urllib.", "socket.", "os.popen", "os.system"):
        assert banned not in src


def test_detector_does_not_import_core_pricing():
    """It references core.pricing by NAME only, so the advisory works whether or not that
    module's API shape changes."""
    import inspect
    src = inspect.getsource(inv._handrolled_fee_subtraction_sites)
    assert "import core.pricing" not in src
    assert "importlib" not in src
