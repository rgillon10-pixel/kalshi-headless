"""Offline tests for scripts/tape_branch_sweep.py (kb lessons L160/L161).

Builds a real temporary git repository per test (not a mocked subprocess) so the
tree-hash containment logic and the malformed-name commit-date triage are exercised
against actual git behavior, not an assumption about it.
"""
import ast
from pathlib import Path

import pytest

from scripts.tape_branch_sweep import (
    ASSERT_CONTAINED_EXIT_CODE,
    BULK_CAPTURE_ID_FAMILIES,
    CANONICAL_NAME_RE,
    BranchTriage,
    capture_ids_in_blob,
    commit_known_locally,
    default_git_runner,
    fetch_branches,
    format_report,
    is_malformed_branch_name,
    list_remote_tape_branches,
    list_tree_files,
    main,
    assert_contained_report,
    missing_line_is_appendable,
    resolve_branch_sha,
    parse_ls_remote,
    per_file_containment,
    read_blob_lines,
    sweep,
    tree_hash,
    triage_branch,
)


def _git(cwd, *args):
    return default_git_runner(list(args), cwd=str(cwd))


def _init_repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    return path


def _commit(path: Path, rel_file: str, content: str, message: str) -> str:
    f = path / rel_file
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content)
    _git(path, "add", rel_file)
    _git(path, "commit", "-q", "-m", message)
    return _git(path, "rev-parse", "HEAD")


@pytest.fixture()
def main_repo(tmp_path):
    """A 'remote' repo with one committed tape file, cloned into 'clone' (a normal `git
    clone` fetches every object reachable from every branch — so branches created BEFORE
    cloning would already be locally known, defeating an "unfetched" test). The three test
    branches are therefore created on `remote` AFTER `clone` exists, so `clone` genuinely
    has not fetched them until a test explicitly calls `fetch_branches`:
    - `tape/hourly-20260725T0406Z` — tape tree byte-identical to main (contained).
    - `tape/hourly-20260725T0500Z` — tape tree with one extra line (NOT contained).
    - `tape/hourly-202607251200Z` — malformed name (missing the `T` separator), contained.
    """
    remote = _init_repo(tmp_path / "remote.git")
    _git(remote, "config", "receive.denyCurrentBranch", "ignore")
    _commit(remote, "tape/sports_pairs/dt=2026-07-25.jsonl", '{"a": 1}\n', "seed")
    _git(remote, "branch", "-M", "main")

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(remote), str(clone))
    _git(clone, "config", "user.email", "test@example.com")
    _git(clone, "config", "user.name", "Test")
    _git(clone, "checkout", "-q", "main")

    # Branch A: a NEW commit (distinct sha from the seed, so it is genuinely unfetched
    # by `clone` until swept) whose tape/ tree is untouched — byte-identical to main
    # (fully contained). The new commit only touches a file outside tape/.
    _git(remote, "checkout", "-q", "-b", "tape/hourly-20260725T0406Z")
    (remote / "branch-marker-a.txt").write_text("branch A marker, tape/ untouched\n")
    _git(remote, "add", "branch-marker-a.txt")
    _git(remote, "commit", "-q", "-m", "branch A: no tape change")
    _git(remote, "checkout", "-q", "main")

    # Branch B: tape tree with one extra line (NOT contained).
    _git(remote, "checkout", "-q", "-b", "tape/hourly-20260725T0500Z")
    (remote / "tape/sports_pairs/dt=2026-07-25.jsonl").write_text('{"a": 1}\n{"b": 2}\n')
    _git(remote, "add", "tape/sports_pairs/dt=2026-07-25.jsonl")
    _git(remote, "commit", "-q", "-m", "extra line")
    _git(remote, "checkout", "-q", "main")

    # Branch C: malformed name (missing the T separator); new commit, tape/ untouched
    # (fully contained).
    _git(remote, "checkout", "-q", "-b", "tape/hourly-202607251200Z")
    (remote / "branch-marker-c.txt").write_text("branch C marker, tape/ untouched\n")
    _git(remote, "add", "branch-marker-c.txt")
    _git(remote, "commit", "-q", "-m", "branch C: no tape change")
    _git(remote, "checkout", "-q", "main")

    # Branch D: an OLD one-line snapshot of the tape file, branched before `main` grows
    # a second line below. Its tree hash will therefore NOT match HEAD's tree (HEAD has
    # an extra line D never saw) even though D's one line remains fully present in
    # HEAD's now-larger file — this is the exact "hash mismatch but still contained"
    # case an append-only tape needs, and the case a naive tree-hash-only read gets wrong.
    _git(remote, "checkout", "-q", "-b", "tape/hourly-20260724T1200Z")
    (remote / "branch-marker-d.txt").write_text("branch D marker, tape/ untouched\n")
    _git(remote, "add", "branch-marker-d.txt")
    _git(remote, "commit", "-q", "-m", "branch D: no tape change, old snapshot")
    _git(remote, "checkout", "-q", "main")

    # Now `main` grows a second, genuinely new line in the same file — after D diverged.
    (remote / "tape/sports_pairs/dt=2026-07-25.jsonl").write_text('{"a": 1}\n{"c": 3}\n')
    _git(remote, "add", "tape/sports_pairs/dt=2026-07-25.jsonl")
    _git(remote, "commit", "-q", "-m", "main grows: append a second, unrelated line")
    _git(clone, "pull", "-q", "origin", "main")

    return clone, remote


class TestNameValidation:
    def test_canonical_name_passes(self):
        assert not is_malformed_branch_name("tape/hourly-20260725T0406Z")

    def test_missing_t_separator_is_malformed(self):
        assert is_malformed_branch_name("tape/hourly-202607251200Z")

    def test_bare_z_is_malformed(self):
        assert is_malformed_branch_name("tape/hourly-Z")

    def test_empty_suffix_is_malformed(self):
        assert is_malformed_branch_name("tape/hourly-")

    def test_amended_suffix_is_malformed(self):
        assert is_malformed_branch_name("tape/hourly-amended-20260704T1455Z")

    def test_regex_matches_expected_shape(self):
        assert CANONICAL_NAME_RE.match("tape/hourly-20260725T0406Z")
        assert not CANONICAL_NAME_RE.match("tape/hourly-202607251200Z")


class TestParseLsRemote:
    def test_parses_heads(self):
        out = (
            "abc123\trefs/heads/tape/hourly-20260725T0406Z\n"
            "def456\trefs/heads/tape/hourly-20260725T0500Z\n"
            "789fed\trefs/heads/main\n"
        )
        parsed = parse_ls_remote(out, prefix="refs/heads/tape/")
        assert parsed == [
            ("abc123", "hourly-20260725T0406Z"),
            ("def456", "hourly-20260725T0500Z"),
        ]

    def test_empty_output(self):
        assert parse_ls_remote("") == []

    def test_ignores_blank_lines(self):
        out = "\nabc123\trefs/heads/tape/hourly-20260725T0406Z\n\n"
        assert parse_ls_remote(out, prefix="refs/heads/tape/") == [
            ("abc123", "hourly-20260725T0406Z")
        ]


class TestCommitKnownLocally:
    def test_head_is_known(self, main_repo):
        clone, _remote = main_repo
        head = _git(clone, "rev-parse", "HEAD")
        assert commit_known_locally(head, cwd=str(clone)) is True

    def test_unfetched_sha_is_unknown(self, main_repo):
        clone, _remote = main_repo
        assert commit_known_locally("0" * 40, cwd=str(clone)) is False


class TestTreeHash:
    def test_matches_for_identical_path(self, main_repo):
        clone, _remote = main_repo
        head = _git(clone, "rev-parse", "HEAD")
        h1 = tree_hash(head, "tape", cwd=str(clone))
        h2 = tree_hash("HEAD", "tape", cwd=str(clone))
        assert h1 == h2
        assert h1 is not None

    def test_missing_path_returns_none(self, main_repo):
        clone, _remote = main_repo
        assert tree_hash("HEAD", "nonexistent_dir", cwd=str(clone)) is None


class TestFetchAndTriage:
    def test_fetch_then_triage_contained_branch(self, main_repo):
        clone, remote = main_repo
        branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
        names = {n for _sha, n in branches}
        assert names == {
            "tape/hourly-20260725T0406Z",
            "tape/hourly-20260725T0500Z",
            "tape/hourly-202607251200Z",
            "tape/hourly-20260724T1200Z",
        }

        fetch_branches(branches, remote="origin", cwd=str(clone))
        triage = sweep(branches, base_ref="HEAD", cwd=str(clone))
        by_name = {t.name: t for t in triage}

        contained = by_name["tape/hourly-20260725T0406Z"]
        assert contained.fetched is True
        assert contained.contained is True
        assert contained.malformed is False
        assert contained.commit_date is None  # only populated for malformed rows
        assert contained.missing_files == {}

        not_contained = by_name["tape/hourly-20260725T0500Z"]
        assert not_contained.fetched is True
        assert not_contained.contained is False
        assert not_contained.malformed is False
        # The extra line ('{"b": 2}') this branch carries is genuinely absent from HEAD's
        # (now-grown) version of the same file — exactly one file, exactly one missing line.
        assert not_contained.missing_files == {"tape/sports_pairs/dt=2026-07-25.jsonl": 1}

        malformed = by_name["tape/hourly-202607251200Z"]
        assert malformed.malformed is True
        assert malformed.contained is True
        assert malformed.commit_date is not None  # triage-by-date field populated

        # Branch D: tree hash MISMATCHES HEAD (HEAD grew a line after D diverged), but
        # D's one line is still fully present in HEAD's larger file — the core L160 fix.
        old_snapshot = by_name["tape/hourly-20260724T1200Z"]
        assert old_snapshot.fetched is True
        assert old_snapshot.contained is True
        assert old_snapshot.missing_files == {}
        head_tree = tree_hash("HEAD", "tape", cwd=str(clone))
        branch_tree = tree_hash(old_snapshot.sha, "tape", cwd=str(clone))
        assert branch_tree != head_tree  # the mismatch this fixture exists to exercise

    def test_unfetched_branch_reports_fetched_false_not_contained_none(self, main_repo):
        clone, remote = main_repo
        branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
        # Deliberately skip fetch_branches().
        triage = sweep(branches, base_ref="HEAD", cwd=str(clone))
        for t in triage:
            assert t.fetched is False
            # fetched=False must never be conflated with contained=None (the "no tape/
            # tree" signal) — they are different facts.
            assert t.contained is None
            assert t.commit_date is None

    def test_branch_with_no_tape_tree_is_distinct_from_unfetched(self, tmp_path):
        remote = _init_repo(tmp_path / "remote.git")
        _git(remote, "config", "receive.denyCurrentBranch", "ignore")
        _commit(remote, "tape/sports_pairs/dt=2026-07-25.jsonl", '{"a": 1}\n', "seed")
        _git(remote, "branch", "-M", "main")
        # A branch with a file OUTSIDE tape/ only — no tape/ tree exists on it.
        _git(remote, "checkout", "-q", "-b", "tape/hourly-20260725T0700Z")
        _git(remote, "rm", "-q", "-r", "tape")
        (remote / "LOOP-QUEUE.md").write_text("stray non-tape branch\n")
        _git(remote, "add", "LOOP-QUEUE.md")
        _git(remote, "commit", "-q", "-m", "no tape tree here")
        _git(remote, "checkout", "-q", "main")

        clone = tmp_path / "clone"
        _git(tmp_path, "clone", "-q", str(remote), str(clone))

        branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
        fetch_branches(branches, remote="origin", cwd=str(clone))
        triage = sweep(branches, base_ref="HEAD", cwd=str(clone))
        assert len(triage) == 1
        t = triage[0]
        assert t.fetched is True
        assert t.contained is None  # fetched, but genuinely no tape/ tree — a real anomaly


class TestPerFileContainmentPrimitives:
    def test_list_tree_files_lists_recursively(self, main_repo):
        clone, _remote = main_repo
        files = list_tree_files("HEAD", "tape", cwd=str(clone))
        assert files == ["sports_pairs/dt=2026-07-25.jsonl"]

    def test_list_tree_files_missing_path_returns_empty(self, main_repo):
        clone, _remote = main_repo
        assert list_tree_files("HEAD", "nonexistent", cwd=str(clone)) == []

    def test_read_blob_lines_missing_returns_none(self, main_repo):
        clone, _remote = main_repo
        assert read_blob_lines("HEAD", "tape/does_not_exist.jsonl", cwd=str(clone)) is None

    def test_read_blob_lines_reads_content(self, main_repo):
        clone, _remote = main_repo
        lines = read_blob_lines("HEAD", "tape/sports_pairs/dt=2026-07-25.jsonl", cwd=str(clone))
        assert lines == ['{"a": 1}', '{"c": 3}']  # post-growth HEAD content

    def test_per_file_containment_empty_for_subset_branch(self, main_repo):
        clone, _remote = main_repo
        branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
        fetch_branches(branches, remote="origin", cwd=str(clone))
        d_sha = next(sha for sha, name in branches if name == "tape/hourly-20260724T1200Z")
        missing, skipped, capture_id_checked = per_file_containment(d_sha, "HEAD", "tape", cwd=str(clone))
        assert missing == {}
        assert skipped == {}
        assert capture_id_checked == {}

    def test_per_file_containment_reports_genuinely_missing_line(self, main_repo):
        clone, _remote = main_repo
        branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
        fetch_branches(branches, remote="origin", cwd=str(clone))
        b_sha = next(sha for sha, name in branches if name == "tape/hourly-20260725T0500Z")
        missing, skipped, capture_id_checked = per_file_containment(b_sha, "HEAD", "tape", cwd=str(clone))
        assert missing == {"tape/sports_pairs/dt=2026-07-25.jsonl": 1}
        assert skipped == {}
        assert capture_id_checked == {}

    def test_size_guard_skips_oversized_files(self, main_repo):
        clone, _remote = main_repo
        branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
        fetch_branches(branches, remote="origin", cwd=str(clone))
        b_sha = next(sha for sha, name in branches if name == "tape/hourly-20260725T0500Z")
        # The seeded file is a few bytes — any positive-but-tiny max_file_bytes skips it.
        # It has no `capture_id` field, so even though its family (sports_pairs) is one of
        # the L216 bulk families, the cheaper check finds no signal and falls back to a
        # plain skip (see TestBulkCaptureIdCheck for the case where capture_id IS present).
        missing, skipped, capture_id_checked = per_file_containment(b_sha, "HEAD", "tape", cwd=str(clone),
                                                  max_file_bytes=1)
        assert missing == {}  # never checked, so never reported as missing either
        # 18 bytes = len('{"a": 1}\n{"b": 2}\n') — the file this branch wrote, trailing newline
        # included (git blob size counts the exact bytes stored).
        assert skipped == {"tape/sports_pairs/dt=2026-07-25.jsonl": 18}
        assert capture_id_checked == {}

    def test_size_guard_disabled_with_none(self, main_repo):
        clone, _remote = main_repo
        branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
        fetch_branches(branches, remote="origin", cwd=str(clone))
        b_sha = next(sha for sha, name in branches if name == "tape/hourly-20260725T0500Z")
        missing, skipped, capture_id_checked = per_file_containment(b_sha, "HEAD", "tape", cwd=str(clone),
                                                  max_file_bytes=None)
        assert missing == {"tape/sports_pairs/dt=2026-07-25.jsonl": 1}
        assert skipped == {}
        assert capture_id_checked == {}

    def test_triage_branch_marks_contained_unverified_when_skipped(self, main_repo):
        clone, _remote = main_repo
        branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
        fetch_branches(branches, remote="origin", cwd=str(clone))
        b_sha, b_name = next((sha, name) for sha, name in branches
                              if name == "tape/hourly-20260725T0500Z")
        t = triage_branch(b_sha, b_name, base_ref="HEAD", cwd=str(clone), max_file_bytes=1)
        assert t.contained is True  # no missing line PROVEN, because nothing was checked
        assert t.fully_verified is False  # but it must not be trusted as a real proof
        assert t.skipped_files

    def test_head_line_cache_is_reused_across_calls(self, main_repo):
        clone, _remote = main_repo
        branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
        fetch_branches(branches, remote="origin", cwd=str(clone))
        b_sha = next(sha for sha, name in branches if name == "tape/hourly-20260725T0500Z")
        cache = {}
        per_file_containment(b_sha, "HEAD", "tape", cwd=str(clone), head_line_cache=cache)
        assert "tape/sports_pairs/dt=2026-07-25.jsonl" in cache
        # A second call with the same cache must not need to re-read HEAD's blob — verified
        # indirectly by passing a run_git stub that fails on any "show HEAD:..." call.
        def strict_run_git(args, cwd=None):
            if args and args[0] == "show" and len(args) > 1 and args[1].startswith("HEAD:"):
                raise AssertionError("HEAD-side blob re-read despite a warm cache")
            return default_git_runner(args, cwd=cwd)
        per_file_containment(b_sha, "HEAD", "tape", run_git=strict_run_git, cwd=str(clone),
                              head_line_cache=cache)


class TestCaptureIdsInBlob:
    """`capture_ids_in_blob` (L216) — the cheaper per-family check's raw extraction step."""

    def test_extracts_distinct_capture_ids(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit(repo, "tape/orderbook_depth/dt=2026-07-27.jsonl",
                '{"capture_id": "cap-A", "ticker": "X"}\n'
                '{"capture_id": "cap-A", "ticker": "Y"}\n'
                '{"capture_id": "cap-B", "ticker": "Z"}\n',
                "seed")
        ids = capture_ids_in_blob("HEAD", "tape/orderbook_depth/dt=2026-07-27.jsonl", cwd=str(repo))
        assert ids == frozenset({"cap-A", "cap-B"})

    def test_missing_path_returns_none(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit(repo, "tape/orderbook_depth/dt=2026-07-27.jsonl", '{"capture_id": "cap-A"}\n', "seed")
        assert capture_ids_in_blob("HEAD", "tape/orderbook_depth/dt=2026-07-28.jsonl", cwd=str(repo)) is None

    def test_malformed_and_fieldless_lines_are_skipped_not_crashed(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit(repo, "tape/orderbook_depth/dt=2026-07-27.jsonl",
                '{"capture_id": "cap-A"}\n'
                "not json at all\n"
                '{"ticker": "no capture_id field"}\n'
                '["capture_id", "not-a-dict-so-no-.get"]\n',
                "seed")
        ids = capture_ids_in_blob("HEAD", "tape/orderbook_depth/dt=2026-07-27.jsonl", cwd=str(repo))
        assert ids == frozenset({"cap-A"})


class TestBulkCaptureIdCheck:
    """L216: an oversized file under one of `BULK_CAPTURE_ID_FAMILIES` gets a capture_id-set
    check instead of an unverified skip, PROVIDED the branch side yields >=1 real capture_id.
    (The no-signal case — an oversized bulk file with no capture_id at all — is already
    covered by `TestPerFileContainment.test_size_guard_skips_oversized_files`, which
    deliberately uses `sports_pairs` content with no `capture_id` field and asserts it still
    falls back to a plain skip.)
    """

    @pytest.fixture()
    def bulk_family_repo(self, tmp_path):
        """One repo, three commits, no remote/clone/fetch needed (this exercises
        `per_file_containment`/`triage_branch` directly against local shas):
        - `contained-branch`: `tape/orderbook_depth/dt=2026-07-27.jsonl` carries only cap-A.
        - `missing-branch`: same file carries cap-A + cap-C (cap-C never reaches HEAD).
        - `main` (HEAD): advances past both to carry cap-A + cap-B — a subset check against
          cap-C (missing) and a superset check against cap-A alone (contained) in one fixture.
        """
        repo = _init_repo(tmp_path / "repo")
        _commit(repo, "tape/orderbook_depth/dt=2026-07-27.jsonl",
                '{"capture_id": "cap-A", "ticker": "X"}\n', "seed cap-A")
        _git(repo, "branch", "-M", "main")
        _git(repo, "branch", "contained-branch")
        _git(repo, "checkout", "-q", "-b", "missing-branch")
        (repo / "tape/orderbook_depth/dt=2026-07-27.jsonl").write_text(
            '{"capture_id": "cap-A", "ticker": "X"}\n{"capture_id": "cap-C", "ticker": "Z"}\n')
        _git(repo, "add", "tape/orderbook_depth/dt=2026-07-27.jsonl")
        _git(repo, "commit", "-q", "-m", "adds cap-C")
        _git(repo, "checkout", "-q", "main")
        (repo / "tape/orderbook_depth/dt=2026-07-27.jsonl").write_text(
            '{"capture_id": "cap-A", "ticker": "X"}\n{"capture_id": "cap-B", "ticker": "Y"}\n')
        _git(repo, "add", "tape/orderbook_depth/dt=2026-07-27.jsonl")
        _git(repo, "commit", "-q", "-m", "HEAD adds cap-B")
        return repo

    def test_bulk_family_constant_is_observational_not_a_gate(self):
        """L235: the constant is a MEASUREMENT RECORD of families observed above the size
        guard, not the gate that decides whether the capture_id check fires. It must stay
        importable (cited by name in `kb/lessons/00-lessons.md` L217 and the 2026-07-28
        bulk-family-blindspot finding) and factually current, but nothing may read it to
        decide behaviour — see `test_capture_id_check_fires_for_family_absent_from_constant`.
        """
        assert BULK_CAPTURE_ID_FAMILIES >= frozenset(
            {"orderbook_depth", "universe_sweep", "sports_pairs", "weather_books"})
        # the three families L217's enumeration missed, each measured oversized on 2026-07-31
        assert BULK_CAPTURE_ID_FAMILIES >= frozenset(
            {"crypto_hourly", "econ_prints", "anomalies"})

    def test_constant_is_not_consulted_by_the_containment_gate(self):
        """The enumeration must not be re-introduced as a gate: no function in the module
        may branch on `BULK_CAPTURE_ID_FAMILIES`. Pinning the ABSENCE of a read is the only
        way to stop L217's defect (enumerate-where-you-should-derive) recurring a third time.
        """
        src = Path("scripts/tape_branch_sweep.py").read_text(encoding="utf-8")
        module = ast.parse(src)
        reads = [n for n in ast.walk(module)
                 if isinstance(n, ast.Name)
                 and n.id == "BULK_CAPTURE_ID_FAMILIES"
                 and isinstance(n.ctx, ast.Load)]
        assert reads == [], (
            "BULK_CAPTURE_ID_FAMILIES is read at line(s) "
            f"{[n.lineno for n in reads]} — it is an observational record, not a gate")

    def test_capture_id_check_fires_for_family_absent_from_constant(self, tmp_path):
        """L235 regression: an oversized day-file in a family that is NOT in
        `BULK_CAPTURE_ID_FAMILIES` at all still gets the capture_id-set check, because the
        blob's own content (it carries `capture_id`) is what qualifies it. Before this fix
        such a file was reported as an unverified skip — the state 126 of 218 real branches
        were in on 2026-07-31 solely because `crypto_hourly` was not on the list.
        """
        assert "brand_new_family" not in BULK_CAPTURE_ID_FAMILIES
        repo = _init_repo(tmp_path / "repo")
        _commit(repo, "tape/brand_new_family/dt=2026-07-31.jsonl",
                '{"capture_id": "cap-A", "ticker": "X"}\n', "seed cap-A")
        _git(repo, "branch", "-M", "main")
        _git(repo, "checkout", "-q", "-b", "stranded")
        (repo / "tape/brand_new_family/dt=2026-07-31.jsonl").write_text(
            '{"capture_id": "cap-A", "ticker": "X"}\n{"capture_id": "cap-C", "ticker": "Z"}\n')
        _git(repo, "add", "tape/brand_new_family/dt=2026-07-31.jsonl")
        _git(repo, "commit", "-q", "-m", "adds cap-C")
        _git(repo, "checkout", "-q", "main")
        sha = _git(repo, "rev-parse", "stranded")
        missing, skipped, capture_id_checked = per_file_containment(
            sha, "HEAD", "tape", cwd=str(repo), max_file_bytes=1)
        assert skipped == {}, "must not fall back to an unverified skip"
        assert capture_id_checked == {"tape/brand_new_family/dt=2026-07-31.jsonl": 1}

    def test_oversized_file_without_capture_id_still_skips_honestly(self, tmp_path):
        """The no-signal fallback survives the L235 widening: attempting the check on every
        oversized file must NOT turn "yielded zero capture_ids" into a clean bill of health.
        """
        repo = _init_repo(tmp_path / "repo")
        _commit(repo, "tape/no_id_family/dt=2026-07-31.jsonl",
                '{"ticker": "X"}\n', "seed")
        _git(repo, "branch", "-M", "main")
        _git(repo, "checkout", "-q", "-b", "stranded")
        (repo / "tape/no_id_family/dt=2026-07-31.jsonl").write_text(
            '{"ticker": "X"}\n{"ticker": "Z"}\n')
        _git(repo, "add", "tape/no_id_family/dt=2026-07-31.jsonl")
        _git(repo, "commit", "-q", "-m", "adds a line")
        _git(repo, "checkout", "-q", "main")
        sha = _git(repo, "rev-parse", "stranded")
        missing, skipped, capture_id_checked = per_file_containment(
            sha, "HEAD", "tape", cwd=str(repo), max_file_bytes=1)
        assert capture_id_checked == {}
        assert list(skipped) == ["tape/no_id_family/dt=2026-07-31.jsonl"]

    def test_contained_branch_verified_via_capture_id_zero_missing(self, bulk_family_repo):
        repo = bulk_family_repo
        sha = _git(repo, "rev-parse", "contained-branch")
        missing, skipped, capture_id_checked = per_file_containment(
            sha, "HEAD", "tape", cwd=str(repo), max_file_bytes=1)
        assert missing == {}
        assert skipped == {}
        assert capture_id_checked == {"tape/orderbook_depth/dt=2026-07-27.jsonl": 0}

    def test_missing_branch_reports_missing_capture_id_count(self, bulk_family_repo):
        repo = bulk_family_repo
        sha = _git(repo, "rev-parse", "missing-branch")
        missing, skipped, capture_id_checked = per_file_containment(
            sha, "HEAD", "tape", cwd=str(repo), max_file_bytes=1)
        assert missing == {}
        assert skipped == {}
        assert capture_id_checked == {"tape/orderbook_depth/dt=2026-07-27.jsonl": 1}

    def test_triage_branch_contained_true_but_capture_id_only(self, bulk_family_repo):
        repo = bulk_family_repo
        sha = _git(repo, "rev-parse", "contained-branch")
        t = triage_branch(sha, "tape/hourly-20260727T1200Z", base_ref="HEAD", cwd=str(repo),
                           max_file_bytes=1)
        assert t.contained is True
        assert t.fully_verified is True  # genuinely checked, not size-guard-skipped
        assert t.capture_id_only is True  # ...but only at capture_id, not line, granularity
        assert t.capture_id_checked_files == {"tape/orderbook_depth/dt=2026-07-27.jsonl": 0}

    def test_triage_branch_not_contained_when_capture_id_missing(self, bulk_family_repo):
        repo = bulk_family_repo
        sha = _git(repo, "rev-parse", "missing-branch")
        t = triage_branch(sha, "tape/hourly-20260727T1300Z", base_ref="HEAD", cwd=str(repo),
                           max_file_bytes=1)
        assert t.contained is False
        assert t.capture_id_checked_files == {"tape/orderbook_depth/dt=2026-07-27.jsonl": 1}

    def test_head_capture_id_cache_is_reused_across_calls(self, bulk_family_repo):
        repo = bulk_family_repo
        sha = _git(repo, "rev-parse", "contained-branch")
        cache = {}
        per_file_containment(sha, "HEAD", "tape", cwd=str(repo), max_file_bytes=1,
                              head_capture_id_cache=cache)
        assert "tape/orderbook_depth/dt=2026-07-27.jsonl" in cache

        def strict_run_git(args, cwd=None):
            if args and args[0] == "show" and len(args) > 1 and args[1].startswith("HEAD:"):
                raise AssertionError("HEAD-side blob re-read despite a warm capture_id cache")
            return default_git_runner(args, cwd=cwd)
        per_file_containment(sha, "HEAD", "tape", run_git=strict_run_git, cwd=str(repo),
                              max_file_bytes=1, head_capture_id_cache=cache)


class TestFormatReport:
    def test_report_counts_and_sections(self):
        triage = [
            BranchTriage("tape/hourly-20260725T0406Z", "aaa111", False, True, True, None, {}),
            BranchTriage("tape/hourly-20260725T0500Z", "bbb222", False, True, False, None,
                         {"tape/sports_pairs/dt=2026-07-25.jsonl": 3}),
            BranchTriage("tape/hourly-202607251200Z", "ccc333", True, True, True,
                          "2026-07-25T12:00:00+00:00", {}),
            BranchTriage("tape/hourly-Z", "ddd444", True, False, None, None, {}),
        ]
        report = format_report(triage, base_ref="HEAD")
        assert "4 branch(es) checked" in report
        assert "2 malformed name(s)" in report
        assert "2 fully contained" in report  # aaa111 (well-formed) + ccc333 (malformed)
        assert "1 carry line(s) or capture_id(s) genuinely MISSING" in report
        assert "1 not yet fetched locally" in report
        assert "tape/hourly-20260725T0500Z" in report  # missing-lines section names it
        assert "3 line(s) across 1 file(s)" in report
        # Malformed branches are ordered by commit date, not printed in input/name order.
        malformed_section = report.split("malformed-name branches")[1]
        assert "tape/hourly-202607251200Z" in malformed_section

    def test_empty_input(self):
        report = format_report([], base_ref="HEAD")
        assert "0 branch(es) checked" in report

    def test_capture_id_only_containment_reported_distinctly(self):
        """L216: a branch contained ONLY via the capture_id-level check must land in its
        own bucket, never counted as full line-level "fully contained + verified", and a
        branch with a genuinely missing capture_id must be named in the missing section
        with capture_id units, not line units."""
        contained_via_capture_id = BranchTriage(
            "tape/hourly-20260727T1200Z", "eee555", False, True, True, None, {}, {},
            {"tape/orderbook_depth/dt=2026-07-27.jsonl": 0})
        missing_via_capture_id = BranchTriage(
            "tape/hourly-20260727T1300Z", "fff666", False, True, False, None, {}, {},
            {"tape/orderbook_depth/dt=2026-07-27.jsonl": 1})
        report = format_report([contained_via_capture_id, missing_via_capture_id], base_ref="HEAD")
        assert "0 fully contained + verified" in report  # neither is a line-level proof
        assert "1 contained via capture_id-level check only" in report
        assert "1 carry line(s) or capture_id(s) genuinely MISSING" in report
        assert "1 missing capture_id(s) across 1 bulk-family file(s)" in report
        assert "tape/orderbook_depth/dt=2026-07-27.jsonl: 1 missing capture_id(s)" in report
        assert "tape/hourly-20260727T1200Z" in report  # named in the capture_id-only section
        assert "0 missing capture_id(s)" in report


class TestMainCli:
    def test_limit_bounds_work_and_reports_the_skip_count(self, main_repo, monkeypatch,
                                                            capsys):
        clone, _remote = main_repo
        monkeypatch.chdir(clone)
        rc = main(["--remote", "origin", "--limit", "1"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "3 of 4 listed branch(es) were NOT triaged" in out
        assert "1 branch(es) checked against HEAD" in out

    def test_no_limit_covers_every_branch(self, main_repo, monkeypatch, capsys):
        clone, _remote = main_repo
        monkeypatch.chdir(clone)
        rc = main(["--remote", "origin"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "NOT triaged" not in out
        assert "4 branch(es) checked against HEAD" in out


class TestNeverUsesMergeBaseIsAncestor:
    def test_source_code_has_no_merge_base_call(self):
        """L160: `git merge-base --is-ancestor` reports every fully-contained tape branch
        as 'stranded' on this squash-merge repo, so this module must never call it. The
        module docstring explains why in prose (mentions the string 'merge-base' as
        narrative) — strip that docstring and assert the CODE that remains never does."""
        source = Path("scripts/tape_branch_sweep.py").read_text()
        module = ast.parse(source)
        docstring = ast.get_docstring(module)
        assert docstring and "merge-base" in docstring  # the prose warning exists
        code_without_docstring = source.replace(docstring, "", 1)
        assert "merge-base" not in code_without_docstring
        assert "is-ancestor" not in code_without_docstring


class TestUnionAppendabilityTriage:
    """L247 (2026-08-01): a line missing from HEAD is a CONTAINMENT answer, not a
    permission to union-append. The 2026-08-01 step-0b sweep found 13 not-contained
    branches and ZERO carried recoverable tape: 5 carried the three unresolved git
    conflict markers of the 2026-07-23 incident (L142) inside `anomalies`/`econ_prints`
    day-files, 8 carried superseded prose from `tape/cloud-env-check.md`, a markdown doc
    that lives under `tape/` but is not append-only JSONL. Appending either would have
    handed `main` a red `invariants.py` gate."""

    @pytest.mark.parametrize("line", [
        "<<<<<<< HEAD",
        "=======",
        ">>>>>>> 58145d7 (tape: hourly pass 2026-07-18T09:30:28Z (vps))",
    ])
    def test_conflict_markers_are_never_appendable(self, line):
        assert not missing_line_is_appendable("tape/econ_prints/dt=2026-07-18.jsonl", line)

    @pytest.mark.parametrize("path", [
        "tape/cloud-env-check.md",          # the real 2026-08-01 case: a hand-written doc
        "tape/README.md",
        "tape/ws_depth/dt=2026-07-22.jsonl.gz",   # gzipped: not line-unionable as text
    ])
    def test_non_jsonl_files_under_tape_are_never_appendable(self, path):
        assert not missing_line_is_appendable(path, '{"capture_id": "20260718T091512Z"}')

    def test_a_real_jsonl_tape_line_is_appendable(self):
        assert missing_line_is_appendable(
            "tape/econ_prints/dt=2026-07-18.jsonl",
            '{"capture_id": "20260718T091512Z", "captured_at": "2026-07-18T09:15:12+00:00"}')

    @pytest.mark.parametrize("line", ["123", "null", '"a bare string"', "[1, 2]"])
    def test_a_bare_json_scalar_or_array_is_not_a_tape_record(self, line):
        # parses, but is not a record — propagating it spreads corruption, not tape
        assert not missing_line_is_appendable("tape/econ_prints/dt=2026-07-18.jsonl", line)

    def test_a_non_json_line_in_a_jsonl_file_is_not_appendable(self):
        # e.g. a truncated write or a stray log line — never blind-append it
        assert not missing_line_is_appendable("tape/econ_prints/dt=2026-07-18.jsonl",
                                              "Traceback (most recent call last):")

    def test_per_file_containment_populates_the_unappendable_breakdown(self, main_repo):
        clone, _remote = main_repo
        branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
        fetch_branches(branches, remote="origin", cwd=str(clone))
        b_sha = next(sha for sha, name in branches if name == "tape/hourly-20260725T0500Z")
        out = {}
        missing, _skipped, _cid = per_file_containment(b_sha, "HEAD", "tape", cwd=str(clone),
                                                       unappendable_out=out)
        # the fixture's missing line IS valid JSONL tape, so nothing is withheld
        assert missing == {"tape/sports_pairs/dt=2026-07-25.jsonl": 1}
        assert out == {}

    def test_triage_flags_a_branch_whose_only_missing_line_is_a_conflict_marker(self, tmp_path):
        remote = _init_repo(tmp_path / "remote")
        day = remote / "tape" / "econ_prints"
        day.mkdir(parents=True)
        f = day / "dt=2026-07-18.jsonl"
        f.write_text('{"capture_id": "A"}\n{"capture_id": "B"}\n')
        _git(remote, "add", "-A"); _git(remote, "commit", "-qm", "base")
        _git(remote, "checkout", "-qb", "tape/hourly-20260718T0930Z")
        f.write_text('{"capture_id": "A"}\n=======\n'
                     '>>>>>>> 58145d7 (tape: hourly pass)\n{"capture_id": "B"}\n<<<<<<< HEAD\n')
        _git(remote, "add", "-A"); _git(remote, "commit", "-qm", "conflicted")
        sha = _git(remote, "rev-parse", "HEAD").strip()
        # base_ref = the branch's own parent, i.e. the pre-conflict "main" tree
        t = triage_branch(sha, "tape/hourly-20260718T0930Z",
                          base_ref=sha + "^", cwd=str(remote))
        assert t.contained is False
        assert t.missing_files == {"tape/econ_prints/dt=2026-07-18.jsonl": 3}
        assert t.unappendable_files == {"tape/econ_prints/dt=2026-07-18.jsonl": 3}
        assert t.all_missing_unappendable is True
        report = format_report([t], base_ref=sha[:7])
        assert "NOT union-appendable" in report
        assert "carries NO strandable tape" in report

    def test_all_missing_unappendable_is_false_when_real_tape_is_stranded(self, tmp_path):
        remote = _init_repo(tmp_path / "remote2")
        day = remote / "tape" / "econ_prints"
        day.mkdir(parents=True)
        f = day / "dt=2026-07-18.jsonl"
        f.write_text('{"capture_id": "A"}\n')
        _git(remote, "add", "-A"); _git(remote, "commit", "-qm", "base")
        _git(remote, "checkout", "-qb", "tape/hourly-20260718T1030Z")
        f.write_text('{"capture_id": "A"}\n=======\n{"capture_id": "REAL"}\n')
        _git(remote, "add", "-A"); _git(remote, "commit", "-qm", "mixed")
        sha = _git(remote, "rev-parse", "HEAD").strip()
        t = triage_branch(sha, "tape/hourly-20260718T1030Z", base_ref=sha + "^", cwd=str(remote))
        assert t.missing_files == {"tape/econ_prints/dt=2026-07-18.jsonl": 2}
        assert t.unappendable_files == {"tape/econ_prints/dt=2026-07-18.jsonl": 1}
        assert t.all_missing_unappendable is False   # one genuine line IS worth sweeping



class TestAssertContainedPostRecoveryCheck:
    """L301 (2026-08-07): a commit that says it recovered a branch's stranded tape must
    prove it against its OWN post-append tree.

    The real recurrence this pins: PR #305 (2026-08-06) was titled "recover
    hourly-20260806T0726Z stranded lines", union-appended that branch's two bulk families
    (orderbook_depth 1,748 + universe_sweep 20,000) and stopped — six other capture_ids the
    same branch carried (crypto_hourly 065616Z, polymarket_macro_pairs 065625Z, sports_pairs
    065433Z, hyperliquid_funding 072313Z, perp_tape 072308Z, weather_books 072315Z, 1,081
    lines) stayed stranded for a day, under a merged PR whose title said otherwise. Nothing
    re-triaged the branch after the append, so nothing could notice.
    """

    def test_branch_with_missing_lines_exits_nonzero_and_names_the_files(
            self, main_repo, monkeypatch, capsys):
        clone, _remote = main_repo
        monkeypatch.chdir(clone)
        rc = main(["--remote", "origin", "--assert-contained",
                   "tape/hourly-20260725T0500Z"])
        assert rc == ASSERT_CONTAINED_EXIT_CODE
        out = capsys.readouterr().out
        assert "STILL MISSING tape/hourly-20260725T0500Z" in out
        assert "tape/sports_pairs/dt=2026-07-25.jsonl: 1 line(s)" in out
        assert "NOT recovered" in out

    def test_contained_branch_exits_zero(self, main_repo, monkeypatch, capsys):
        clone, _remote = main_repo
        monkeypatch.chdir(clone)
        rc = main(["--remote", "origin", "--assert-contained",
                   "tape/hourly-20260725T0406Z"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "CONTAINED    tape/hourly-20260725T0406Z" in out
        assert "all named branches contained" in out

    def test_the_check_flips_to_green_only_after_the_lines_are_actually_appended(
            self, main_repo, monkeypatch, capsys):
        """The whole workflow in one test: red before the union-append, green after."""
        clone, _remote = main_repo
        monkeypatch.chdir(clone)
        assert main(["--remote", "origin", "--assert-contained",
                     "tape/hourly-20260725T0500Z"]) == ASSERT_CONTAINED_EXIT_CODE
        capsys.readouterr()

        target = clone / "tape/sports_pairs/dt=2026-07-25.jsonl"
        target.write_text(target.read_text() + '{"b": 2}\n')
        _git(clone, "add", "tape/sports_pairs/dt=2026-07-25.jsonl")
        _git(clone, "commit", "-q", "-m", "tape: recover stranded line")

        rc = main(["--remote", "origin", "--assert-contained",
                   "tape/hourly-20260725T0500Z"])
        assert rc == 0
        assert "CONTAINED" in capsys.readouterr().out

    def test_partial_recovery_still_fails_the_check(self, main_repo, monkeypatch, capsys):
        """PR #305's exact shape: recover SOME of a branch's stranded lines, claim the
        branch. A second stranded file is appended to the branch, only the first is
        recovered locally — the check must stay red on the remainder."""
        clone, remote = main_repo
        _git(remote, "checkout", "-q", "tape/hourly-20260725T0500Z")
        (remote / "tape/weather_books/dt=2026-07-25.jsonl").parent.mkdir(
            parents=True, exist_ok=True)
        (remote / "tape/weather_books/dt=2026-07-25.jsonl").write_text('{"w": 9}\n')
        _git(remote, "add", "tape/weather_books/dt=2026-07-25.jsonl")
        _git(remote, "commit", "-q", "-m", "second stranded family")
        _git(remote, "checkout", "-q", "main")

        monkeypatch.chdir(clone)
        target = clone / "tape/sports_pairs/dt=2026-07-25.jsonl"
        target.write_text(target.read_text() + '{"b": 2}\n')
        _git(clone, "add", "tape/sports_pairs/dt=2026-07-25.jsonl")
        _git(clone, "commit", "-q", "-m", "tape: recover ONE family only")

        rc = main(["--remote", "origin", "--assert-contained",
                   "tape/hourly-20260725T0500Z"])
        assert rc == ASSERT_CONTAINED_EXIT_CODE
        out = capsys.readouterr().out
        assert "tape/weather_books/dt=2026-07-25.jsonl: 1 line(s)" in out
        assert "tape/sports_pairs" not in out.split("STILL MISSING", 1)[1].split(
            "VERDICT", 1)[0]

    def test_name_may_omit_the_tape_prefix(self, main_repo, monkeypatch, capsys):
        clone, _remote = main_repo
        monkeypatch.chdir(clone)
        rc = main(["--remote", "origin", "--assert-contained", "hourly-20260725T0406Z"])
        assert rc == 0
        assert "tape/hourly-20260725T0406Z" in capsys.readouterr().out

    def test_several_branches_one_bad_fails_the_whole_check(self, main_repo, monkeypatch,
                                                             capsys):
        clone, _remote = main_repo
        monkeypatch.chdir(clone)
        rc = main(["--remote", "origin", "--assert-contained",
                   "tape/hourly-20260725T0406Z,tape/hourly-20260725T0500Z"])
        assert rc == ASSERT_CONTAINED_EXIT_CODE
        out = capsys.readouterr().out
        assert "CONTAINED    tape/hourly-20260725T0406Z" in out
        assert "STILL MISSING tape/hourly-20260725T0500Z" in out

    def test_a_branch_the_remote_does_not_have_is_a_failure_not_a_pass(
            self, main_repo, monkeypatch, capsys):
        """An unverifiable claim is not a verified one — a typo must never read green."""
        clone, _remote = main_repo
        monkeypatch.chdir(clone)
        rc = main(["--remote", "origin", "--assert-contained", "hourly-20260725T9999Z"])
        assert rc == ASSERT_CONTAINED_EXIT_CODE
        out = capsys.readouterr().out
        assert "NOT ON REMOTE tape/hourly-20260725T9999Z" in out
        assert "NOT recovered" in out

    def test_resolve_branch_sha_returns_none_for_an_unknown_name(self, main_repo,
                                                                  monkeypatch):
        clone, _remote = main_repo
        monkeypatch.chdir(clone)
        assert resolve_branch_sha("hourly-20260725T9999Z", "origin") is None
        assert resolve_branch_sha("hourly-20260725T0406Z", "origin") is not None

    def test_report_treats_an_unfetched_branch_as_unverifiable(self):
        t = BranchTriage(name="tape/hourly-20260725T0406Z", sha="deadbeefcafe",
                         malformed=False, fetched=False, contained=None, commit_date=None)
        text, ok = assert_contained_report([t])
        assert ok is False
        assert "UNVERIFIABLE" in text

    def test_report_treats_a_size_guard_skip_as_unverified(self):
        """A file the size guard never read is 'not checked', never 'checked and clean'
        (L216) — so it cannot certify a recovery either."""
        t = BranchTriage(name="tape/hourly-20260725T0406Z", sha="deadbeefcafe",
                         malformed=False, fetched=True, contained=True, commit_date=None,
                         skipped_files={"tape/universe_sweep/dt=2026-07-25.jsonl": 9_000_000})
        text, ok = assert_contained_report([t])
        assert ok is False
        assert "size-guard-skipped" in text

    def test_report_counts_a_missing_capture_id_as_not_recovered(self):
        t = BranchTriage(name="tape/hourly-20260725T0406Z", sha="deadbeefcafe",
                         malformed=False, fetched=True, contained=False, commit_date=None,
                         capture_id_checked_files={"tape/universe_sweep/dt=2026-07-25.jsonl": 3})
        text, ok = assert_contained_report([t])
        assert ok is False
        assert "3 capture_id(s)" in text

    def test_capture_id_only_containment_is_labelled_not_hidden(self):
        t = BranchTriage(name="tape/hourly-20260725T0406Z", sha="deadbeefcafe",
                         malformed=False, fetched=True, contained=True, commit_date=None,
                         capture_id_checked_files={"tape/universe_sweep/dt=2026-07-25.jsonl": 0})
        text, ok = assert_contained_report([t])
        assert ok is True
        assert "capture_id-level only" in text
