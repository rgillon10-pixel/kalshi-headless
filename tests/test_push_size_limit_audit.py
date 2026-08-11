"""Offline tests for the push-wedge size gate: `core/push_limits.py`,
`scripts/push_size_limit_audit.py`, and `scripts/invariants.py`'s GATING
`push_size_gate_failure` plus its non-gating warn-band advisory.

NO NETWORK anywhere. The gate's detector shells out to `git ls-files`, so the adversarial
fixtures build a throwaway git repo in `tmp_path` rather than mutating the real tree.

Both branches of the gate are exercised deliberately (L249's sign-boundedness posture applied
to a boolean gate): a planted oversized file MUST fail, and a clean tree MUST pass. A test
that can only ever see one branch is not evidence the gate works.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess

import pytest

from core import push_limits as PL
from scripts import push_size_limit_audit as A

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_engine():
    spec = importlib.util.spec_from_file_location("inv_engine_push",
                                                  ROOT / "scripts" / "invariants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inv = _load_engine()


def _git_repo(tmp_path: pathlib.Path, files: dict) -> pathlib.Path:
    """A throwaway git repo with `files` (relpath -> byte length) tracked."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for rel, nbytes in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("wb") as fh:
            fh.truncate(nbytes)          # sparse: a 96MB fixture costs no real disk
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    return tmp_path


# --------------------------------------------------------------------------- #
# the constants themselves
# --------------------------------------------------------------------------- #
def test_thresholds_are_ordered_and_leave_repair_room():
    assert 0 < PL.PUSH_SIZE_WARN_BYTES < PL.PUSH_SIZE_GATE_BYTES < PL.GITHUB_MAX_FILE_BYTES
    # The gate must sit strictly below the host block, or a run that trips it has no room to
    # land the repair commit — the whole reason the gate is not simply the host limit.
    assert PL.GITHUB_MAX_FILE_BYTES - PL.PUSH_SIZE_GATE_BYTES >= 5_000_000


def test_github_hard_block_is_the_documented_decimal_100mb():
    """100,000,000 bytes, NOT 100 MiB. Using MiB (104,857,600) would silently allow a blob
    GitHub still rejects."""
    assert PL.GITHUB_MAX_FILE_BYTES == 100_000_000
    assert PL.GITHUB_MAX_FILE_BYTES != 100 * 1024 * 1024


def test_invariants_mirror_matches_core_push_limits():
    """scripts/invariants.py mirrors the thresholds so it keeps zero import-time dependency on
    the package (same rationale as VALID_SOURCE_TAGS). This test IS the anti-drift mechanism
    that makes the mirror safe."""
    assert inv.GITHUB_MAX_FILE_BYTES == PL.GITHUB_MAX_FILE_BYTES
    assert inv.PUSH_SIZE_GATE_BYTES == PL.PUSH_SIZE_GATE_BYTES
    assert inv.PUSH_SIZE_WARN_BYTES == PL.PUSH_SIZE_WARN_BYTES


def test_headroom_and_predicates():
    assert PL.headroom_bytes(1_000) == PL.GITHUB_MAX_FILE_BYTES - 1_000
    assert PL.headroom_bytes(PL.GITHUB_MAX_FILE_BYTES + 5) == -5
    assert PL.is_gating(PL.PUSH_SIZE_GATE_BYTES) and not PL.is_gating(PL.PUSH_SIZE_GATE_BYTES - 1)
    assert PL.is_warning(PL.PUSH_SIZE_WARN_BYTES) and not PL.is_warning(PL.PUSH_SIZE_WARN_BYTES - 1)


# --------------------------------------------------------------------------- #
# the GATING invariant — both branches
# --------------------------------------------------------------------------- #
def test_gate_fires_on_a_planted_oversized_tracked_file(tmp_path):
    repo = _git_repo(tmp_path, {"tape/x/dt=2026-01-01.jsonl": PL.PUSH_SIZE_GATE_BYTES + 1,
                                "tape/x/dt=2026-01-02.jsonl": 10})
    issues = inv._push_size_gate_issues(repo)
    assert len(issues) == 1 and issues[0].startswith("tape/x/dt=2026-01-01.jsonl:")
    msg = inv.push_size_gate_failure(issues)
    assert msg is not None and "push_size_gate" in msg
    assert "STOP APPENDING" in msg and "never truncate" in msg.lower()


def test_gate_is_silent_one_byte_under_the_threshold(tmp_path):
    repo = _git_repo(tmp_path, {"tape/x/dt=2026-01-01.jsonl": PL.PUSH_SIZE_GATE_BYTES - 1})
    assert inv._push_size_gate_issues(repo) == []
    assert inv.push_size_gate_failure([]) is None


def test_gate_ignores_an_untracked_oversized_file(tmp_path):
    """An untracked, mid-write collector file cannot wedge a push, and gating on it would
    stop a run for something no commit contains."""
    repo = _git_repo(tmp_path, {"tape/x/dt=2026-01-01.jsonl": 10})
    with (repo / "tape" / "x" / "untracked.jsonl").open("wb") as fh:
        fh.truncate(PL.GITHUB_MAX_FILE_BYTES + 1)
    assert inv._push_size_gate_issues(repo) == []


def test_gate_degrades_to_a_no_op_where_git_is_unavailable(tmp_path):
    """A GATING check may never INVENT a violation for an environment reason."""
    assert inv._push_size_gate_issues(tmp_path / "not-a-repo") == []


def test_warn_band_excludes_files_already_owned_by_the_gate(tmp_path):
    repo = _git_repo(tmp_path, {
        "a.bin": PL.PUSH_SIZE_GATE_BYTES + 1,        # gate's report
        "b.bin": PL.PUSH_SIZE_WARN_BYTES + 1,        # warn band
        "c.bin": PL.PUSH_SIZE_WARN_BYTES - 1,        # neither
    })
    warn = inv._push_size_warn_issues(repo)
    assert [w.split(":")[0] for w in warn] == ["b.bin"]
    assert [g.split(":")[0] for g in inv._push_size_gate_issues(repo)] == ["a.bin"]


def test_warn_advisory_is_non_gating_prose():
    msg = inv.push_size_warn_warning(["tape/x/dt=2026-01-01.jsonl:60000000"])
    assert msg is not None and msg.startswith("note:")
    assert "exit code is unaffected" in msg
    assert inv.push_size_warn_warning([]) is None


# --------------------------------------------------------------------------- #
# the audit tool
# --------------------------------------------------------------------------- #
def test_family_day_profile_separates_the_historical_max_from_the_recent_max():
    sizes = [(90, "tape/f/dt=2026-01-01.jsonl"), (10, "tape/f/dt=2026-01-09.jsonl"),
             (20, "tape/f/dt=2026-01-10.jsonl")]
    prof = A.family_day_profile(sizes, recent_days=2)
    f = prof["f"]
    assert f["n_days"] == 3 and f["max_bytes"] == 90 and f["max_day"] == "2026-01-01"
    assert f["max_recent_bytes"] == 20 and f["max_recent_day"] == "2026-01-10"


def test_family_profile_ignores_non_canonical_paths():
    sizes = [(5, "tape/f/meta/dt=2026-01-01.jsonl"), (7, "tape/f/notes.md"),
             (9, "reports/x.json"), (11, "tape/f/dt=2026-01-01.jsonl")]
    assert set(A.family_day_profile(sizes)) == {"f"}
    assert A.family_day_profile(sizes)["f"]["n_days"] == 1


def test_active_families_are_measured_from_day_strings_not_mtimes():
    prof = {"live": {"last_day": "2026-08-11"}, "stale": {"last_day": "2026-07-01"},
            "edge": {"last_day": "2026-08-09"}}
    assert A._active_families(prof, lag_days=2) == {"live", "edge"}
    assert A._active_families(prof, lag_days=0) == {"live"}


def test_append_exposure_names_the_backfill_only_for_the_family_it_targets():
    prof = {"kalshi_trades": {"last_day": "2026-07-07"},
            "universe_sweep": {"last_day": "2026-08-11"}}
    active = A._active_families(prof)
    kt = A.append_exposure("tape/kalshi_trades/dt=2026-07-07.jsonl", prof, active)
    us = A.append_exposure("tape/universe_sweep/dt=2026-07-22.jsonl", prof, active)
    assert "q52_backfill" in kt and "step0b_sweep" in kt
    assert "collector" not in kt            # no scheduled writer for this family (L313)
    assert "collector" in us and "q52_backfill" not in us
    assert A.append_exposure("README.md", prof, active) == []


def test_file_sizes_skips_a_tracked_but_deleted_path_rather_than_scoring_it_zero(tmp_path):
    (tmp_path / "real.bin").write_bytes(b"1234")
    out = A.file_sizes(["real.bin", "vanished.bin"], root=tmp_path)
    assert out == [(4, "real.bin")]


def test_report_is_repository_health_only():
    """This is a health measurement, not a probe. No strategy vocabulary may leak into it."""
    rep = dict(A.build_report())
    # `report_class` is the DECLARATION that this is not a probe ("no P&L, no CI, no registry
    # flip"); it necessarily names the words it disclaims, so it is excluded from the scan for
    # them — the same shape as tests/test_q52_q54_trades_backfill_phase1.py's sibling check.
    assert "no p&l" in str(rep.pop("report_class")).lower()
    text = json.dumps(rep).lower()
    for banned in ("p&l", "pnl", "edge_after_fee", "bootstrap", "verdict\":", "fill_rate",
                   "ci95", "\"mean\""):
        assert banned not in text, banned


def test_summary_names_the_largest_file_and_its_headroom():
    rep = A.build_report()
    out = A.summarize(rep)
    assert str(rep["largest_path"]) in out and "headroom" in out


# --------------------------------------------------------------------------- #
# acceptance over the REAL tree
# --------------------------------------------------------------------------- #
def test_acceptance_real_tree_is_under_the_hard_block_and_the_gate():
    """Directional, not a pinned count: tape only grows, so this asserts the property that
    matters (nothing is over the line) rather than a number that drifts every collector pass."""
    rep = A.build_report()
    assert rep["n_measured_files"] > 0
    assert rep["n_over_hard_block"] == 0
    assert rep["n_at_or_over_gate"] == 0
    assert rep["min_headroom_bytes"] > 0


def test_acceptance_real_tree_has_at_least_one_file_in_the_warn_band():
    """Recorded 2026-08-11 at 7 files >= 50,000,000 bytes, the largest
    `tape/universe_sweep/dt=2026-07-22.jsonl` at 90,470,557. Asserted as a FLOOR: if this ever
    reads 0 the audit has stopped seeing the tape, which is the failure worth catching (a
    silently-empty scan reporting a clean bill — the L152/L155 recall trap)."""
    rep = A.build_report()
    assert rep["n_at_or_over_warn"] >= 1
    assert rep["largest_bytes"] >= 80_000_000


def test_acceptance_the_engine_and_the_audit_agree_on_the_real_tree():
    """Two independent implementations (the gate shells out itself; the audit builds a full
    report) must not disagree about whether the tree is over the gate."""
    rep = A.build_report()
    assert bool(inv._push_size_gate_issues()) == bool(rep["n_at_or_over_gate"])
