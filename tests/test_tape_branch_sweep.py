"""Offline tests for scripts/tape_branch_sweep.py (kb lessons L160/L161).

Builds a real temporary git repository per test (not a mocked subprocess) so the
tree-hash containment logic and the malformed-name commit-date triage are exercised
against actual git behavior, not an assumption about it.
"""
import ast
from pathlib import Path

import pytest

from scripts.tape_branch_sweep import (
    CANONICAL_NAME_RE,
    NOT_RECOVERABLE_BINARY,
    NOT_RECOVERABLE_GZIP,
    NOT_RECOVERABLE_JSON_DOC,
    NOT_RECOVERABLE_OTHER,
    NOT_RECOVERABLE_PROBE_CACHE,
    NOT_RECOVERABLE_PROSE,
    NOT_RECOVERABLE_RAW_BLOB,
    BranchTriage,
    is_conflict_marker,
    is_recoverable_capture_file,
    is_tape_object_line,
    commit_known_locally,
    default_git_runner,
    fetch_branches,
    format_report,
    is_malformed_branch_name,
    list_remote_tape_branches,
    list_tree_files,
    main,
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
        res = per_file_containment(d_sha, "HEAD", "tape", cwd=str(clone))
        assert res.missing == {}
        assert res.skipped == {}
        assert res.clean is True

    def test_per_file_containment_reports_genuinely_missing_line(self, main_repo):
        clone, _remote = main_repo
        branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
        fetch_branches(branches, remote="origin", cwd=str(clone))
        b_sha = next(sha for sha, name in branches if name == "tape/hourly-20260725T0500Z")
        res = per_file_containment(b_sha, "HEAD", "tape", cwd=str(clone))
        assert res.missing == {"tape/sports_pairs/dt=2026-07-25.jsonl": 1}
        assert res.skipped == {}

    def test_size_guard_skips_oversized_files(self, main_repo):
        clone, _remote = main_repo
        branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
        fetch_branches(branches, remote="origin", cwd=str(clone))
        b_sha = next(sha for sha, name in branches if name == "tape/hourly-20260725T0500Z")
        # The seeded file is a few bytes — any positive-but-tiny max_file_bytes skips it.
        res = per_file_containment(b_sha, "HEAD", "tape", cwd=str(clone),
                                     max_file_bytes=1)
        assert res.missing == {}  # never checked, so never reported as missing either
        # 18 bytes = len('{"a": 1}\n{"b": 2}\n') — the file this branch wrote, trailing newline
        # included (git blob size counts the exact bytes stored).
        assert res.skipped == {"tape/sports_pairs/dt=2026-07-25.jsonl": 18}

    def test_size_guard_disabled_with_none(self, main_repo):
        clone, _remote = main_repo
        branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
        fetch_branches(branches, remote="origin", cwd=str(clone))
        b_sha = next(sha for sha, name in branches if name == "tape/hourly-20260725T0500Z")
        res = per_file_containment(b_sha, "HEAD", "tape", cwd=str(clone),
                                     max_file_bytes=None)
        assert res.missing == {"tape/sports_pairs/dt=2026-07-25.jsonl": 1}
        assert res.skipped == {}

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
        assert "1 carry line(s) genuinely MISSING" in report
        assert "1 not yet fetched locally" in report
        assert "tape/hourly-20260725T0500Z" in report  # missing-lines section names it
        assert "3 line(s) across 1 file(s)" in report
        # Malformed branches are ordered by commit date, not printed in input/name order.
        malformed_section = report.split("malformed-name branches")[1]
        assert "tape/hourly-202607251200Z" in malformed_section

    def test_empty_input(self):
        report = format_report([], base_ref="HEAD")
        assert "0 branch(es) checked" in report


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


CONFLICTED_DAY_FILE = (
    '{"a": 1}\n'
    "<<<<<<< HEAD\n"
    '{"b": 2}\n'
    "=======\n"
    '{"b": 2}\n'
    ">>>>>>> 58145d7 (tape: hourly pass 2026-07-18T09:30:28Z (vps))\n"
)


@pytest.fixture()
def guard_repo(tmp_path):
    """Reproduces the 2026-07-27 step-0b near-miss in miniature (module docstring).

    `main` carries one prose doc, one day-file, one gzipped future-family file. Four
    branches, one per class the sweep must now distinguish:
    - `tape/hourly-20260727T0100Z` — reworded line in `tape/cloud-env-check.md` (Class A:
      prose, NOT line-recoverable).
    - `tape/hourly-20260727T0200Z` — git conflict markers committed into
      `tape/anomalies/dt=2026-07-18.jsonl` (Class B: corrupt, NOT missing).
    - `tape/hourly-20260727T0300Z` — differing `tape/ws_depth/dt=2026-07-18.jsonl.gz`
      bytes (gzip: excluded with its own reason).
    - `tape/hourly-20260727T0400Z` — one genuinely stranded, well-formed JSONL line
      (the regression that matters: the tool must NOT go blind).
    """
    remote = _init_repo(tmp_path / "remote.git")
    _git(remote, "config", "receive.denyCurrentBranch", "ignore")
    (remote / "tape").mkdir()
    (remote / "tape/cloud-env-check.md").write_text(
        "# cloud env check\n`run` · 2026-07-02 · cloud sandbox\n")
    (remote / "tape/anomalies").mkdir()
    (remote / "tape/anomalies/dt=2026-07-18.jsonl").write_text('{"a": 1}\n{"b": 2}\n')
    (remote / "tape/ws_depth").mkdir()
    (remote / "tape/ws_depth/dt=2026-07-18.jsonl.gz").write_bytes(b"\x1f\x8b\x08\x00seed")
    _git(remote, "add", "tape")
    _git(remote, "commit", "-q", "-m", "seed")
    _git(remote, "branch", "-M", "main")

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(remote), str(clone))

    def _branch(name, write):
        _git(remote, "checkout", "-q", "-b", name)
        write()
        _git(remote, "add", "tape")
        _git(remote, "commit", "-q", "-m", name)
        _git(remote, "checkout", "-q", "main")

    _branch("tape/hourly-20260727T0100Z", lambda: (remote / "tape/cloud-env-check.md")
            .write_text("# cloud env check\n## UPDATE 2026-07-09 (Q0b): egress unblocked\n"))
    _branch("tape/hourly-20260727T0200Z", lambda: (remote / "tape/anomalies/dt=2026-07-18.jsonl")
            .write_text(CONFLICTED_DAY_FILE))
    _branch("tape/hourly-20260727T0300Z", lambda: (remote / "tape/ws_depth/dt=2026-07-18.jsonl.gz")
            .write_bytes(b"\x1f\x8b\x08\x00branch-side-different-bytes"))
    _branch("tape/hourly-20260727T0400Z", lambda: (remote / "tape/anomalies/dt=2026-07-18.jsonl")
            .write_text('{"a": 1}\n{"b": 2}\n{"stranded": true}\n'))

    branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
    fetch_branches(branches, remote="origin", cwd=str(clone))
    return clone, branches


def _triage_by_name(clone, branches):
    return {t.name: t for t in sweep(branches, base_ref="HEAD", cwd=str(clone))}


class TestRecoverablePathClassification:
    """Whitelist = append-only capture files, validated shape-by-shape against the real
    `git ls-tree -r HEAD tape` (module docstring). Every excluded shape must carry a reason
    that is TRUE OF THAT SHAPE — a blanket reason is how the partition-day recall hole hid."""

    def test_flat_day_file_is_recoverable(self):
        assert is_recoverable_capture_file("tape/anomalies/dt=2026-07-18.jsonl") == (True, None)

    def test_nested_meta_day_file_is_recoverable(self):
        # tape/weather_books/meta/dt=*.jsonl is real — match on filename, not directory depth.
        assert is_recoverable_capture_file(
            "tape/weather_books/meta/dt=2026-07-18.jsonl") == (True, None)

    def test_partition_directory_pass_file_is_recoverable(self):
        # THE recall hole: tape/sports_pairs/dt=2026-07-02/pass-20260702T231651Z.jsonl is a
        # real committed file — a day that is a DIRECTORY of per-pass JSONL files.
        assert is_recoverable_capture_file(
            "tape/sports_pairs/dt=2026-07-02/pass-20260702T231651Z.jsonl") == (True, None)

    def test_any_jsonl_inside_a_dt_partition_dir_is_recoverable(self):
        # Matched on "parent dir is dt=<date>", so a differently-named per-pass file still
        # qualifies rather than being silently dropped by an over-specific filename regex.
        assert is_recoverable_capture_file(
            "tape/sports_pairs/dt=2026-07-02/capture-20260702T231651Z.jsonl") == (True, None)

    def test_append_mode_manifest_is_recoverable(self):
        # collection/capture_orderbooks.py opens _manifest.jsonl in APPEND mode ("a") and
        # writes one full per-capture record per line — calling it a "manifest" and excluding
        # it would be a recall hole justified by a false reason.
        assert is_recoverable_capture_file("tape/crypto_hourly/_manifest.jsonl") == (True, None)

    def test_markdown_prose_is_not_recoverable(self):
        eligible, reason = is_recoverable_capture_file("tape/cloud-env-check.md")
        assert eligible is False
        assert reason == NOT_RECOVERABLE_PROSE
        assert "edited in place" in reason

    def test_gzipped_day_file_has_its_own_reason(self):
        eligible, reason = is_recoverable_capture_file("tape/ws_depth/dt=2026-07-18.jsonl.gz")
        assert eligible is False
        assert reason == NOT_RECOVERABLE_GZIP
        assert reason != NOT_RECOVERABLE_PROSE  # a distinct, documented reason

    def test_raw_json_blob_has_its_own_reason(self):
        eligible, reason = is_recoverable_capture_file(
            "tape/sports_pairs/dt=2026-07-09/capture-20260709T201837Z/"
            "kxlmbgame26jul102030bletdq.raw.json")
        assert eligible is False
        # NOT "prose docs, manifests" — this is a per-capture raw API blob, and the reason
        # printed to a human must say so.
        assert reason == NOT_RECOVERABLE_RAW_BLOB
        assert "raw per-market capture blob" in reason

    def test_single_json_document_has_its_own_reason(self):
        eligible, reason = is_recoverable_capture_file(
            "tape/q26_settlement_cache/settlement.json")
        assert (eligible, reason) == (False, NOT_RECOVERABLE_JSON_DOC)

    def test_binary_workbook_has_its_own_reason(self):
        eligible, reason = is_recoverable_capture_file(
            "tape/sports_history_s7/worldcup2026-odds-source-20260710T102817Z.xlsx")
        assert (eligible, reason) == (False, NOT_RECOVERABLE_BINARY)

    @pytest.mark.parametrize("path", [
        "tape/q42_hl_funding_cache/hl_funding_BTC.jsonl",
        "tape/seed5_funding_cache/okx_funding_20260717.jsonl",
        "tape/sports_clv_s7/trades.jsonl",
        "tape/sports_history_s7/worldcup2026.jsonl",
    ])
    def test_probe_caches_excluded_with_the_probe_cache_reason(self, path):
        """Judgment call, documented in the module docstring: these ARE JSONL, but they are
        not verified append-only (scripts/sports_clv_s7.py rewrites trades.jsonl with
        open(...,'w')), so they stay excluded — with a reason that says exactly that rather
        than mis-describing them as prose or manifests."""
        eligible, reason = is_recoverable_capture_file(path)
        assert eligible is False
        assert reason == NOT_RECOVERABLE_PROBE_CACHE
        assert "never auto-append" in reason

    def test_unknown_shape_falls_back_to_the_generic_reason(self):
        eligible, reason = is_recoverable_capture_file("tape/some_family/notes.txt")
        assert (eligible, reason) == (False, NOT_RECOVERABLE_OTHER)

    def test_every_reason_string_is_distinct(self):
        """Distinct reasons are the whole point — if two shapes share a string, one of them
        is being mis-described (the defect this class exists to prevent)."""
        reasons = [NOT_RECOVERABLE_GZIP, NOT_RECOVERABLE_RAW_BLOB, NOT_RECOVERABLE_JSON_DOC,
                   NOT_RECOVERABLE_PROSE, NOT_RECOVERABLE_BINARY, NOT_RECOVERABLE_PROBE_CACHE,
                   NOT_RECOVERABLE_OTHER]
        assert len(set(reasons)) == len(reasons)

    def test_conflict_markers_detected(self):
        assert is_conflict_marker("<<<<<<< HEAD")
        assert is_conflict_marker("=======")
        assert is_conflict_marker(">>>>>>> 58145d7 (tape: hourly pass)")
        assert not is_conflict_marker('{"a": 1}')

    def test_only_json_objects_are_tape_lines(self):
        assert is_tape_object_line('{"a": 1}')
        assert not is_tape_object_line("<<<<<<< HEAD")
        assert not is_tape_object_line("=======")  # valid nothing; corruption
        assert not is_tape_object_line("[1, 2]")  # valid JSON, but not a tape observation
        assert not is_tape_object_line("## UPDATE 2026-07-09 (Q0b): egress unblocked")


class TestNearMissGuards:
    """The 2026-07-27 near-miss: 13 "genuinely MISSING" lines, all false positives."""

    def test_prose_path_is_not_line_recoverable_not_missing(self, guard_repo):
        clone, branches = guard_repo
        t = _triage_by_name(clone, branches)["tape/hourly-20260727T0100Z"]
        assert t.missing_files == {}  # NEVER counted as recoverable tape
        assert t.contained is True
        assert t.not_line_recoverable == {
            "tape/cloud-env-check.md": NOT_RECOVERABLE_PROSE}
        # but it must not read as "verified, safe to delete" either — nothing was checked.
        assert t.fully_verified is False

    def test_conflict_markers_are_corrupt_not_missing(self, guard_repo):
        clone, branches = guard_repo
        t = _triage_by_name(clone, branches)["tape/hourly-20260727T0200Z"]
        assert t.missing_files == {}  # zero genuinely-recoverable lines
        assert t.contained is True
        path = "tape/anomalies/dt=2026-07-18.jsonl"
        assert set(t.corrupt_files) == {path}
        assert len(t.corrupt_files[path]) == 3  # <<<<<<< / ======= / >>>>>>>
        assert t.conflict_marker_files == {path: 3}
        assert t.has_conflict_markers is True
        assert t.fully_verified is False

    def test_gzipped_day_file_excluded_with_its_own_reason(self, guard_repo):
        clone, branches = guard_repo
        t = _triage_by_name(clone, branches)["tape/hourly-20260727T0300Z"]
        assert t.missing_files == {}
        assert t.corrupt_files == {}
        assert t.not_line_recoverable == {
            "tape/ws_depth/dt=2026-07-18.jsonl.gz": NOT_RECOVERABLE_GZIP}

    def test_genuinely_stranded_jsonl_line_is_still_missing(self, guard_repo):
        """The regression that matters most: the tool must not become blind."""
        clone, branches = guard_repo
        t = _triage_by_name(clone, branches)["tape/hourly-20260727T0400Z"]
        assert t.contained is False
        assert t.missing_files == {"tape/anomalies/dt=2026-07-18.jsonl": 1}
        assert t.corrupt_files == {}
        assert t.not_line_recoverable == {}

    def test_report_headline_reports_zero_recoverable_for_the_false_positives(self,
                                                                              guard_repo):
        clone, branches = guard_repo
        false_positive_only = [(sha, name) for sha, name in branches
                                if not name.endswith("T0400Z")]
        report = format_report(sweep(false_positive_only, base_ref="HEAD", cwd=str(clone)),
                                base_ref="HEAD")
        assert "0 carry line(s) genuinely MISSING" in report
        assert "0 recoverable line(s) total" in report
        # ...and every excluded line is still visible somewhere in the report.
        assert "NOT line-recoverable" in report
        assert "tape/cloud-env-check.md" in report
        assert "CORRUPT" in report
        assert "UNRESOLVED MERGE committed into tape" in report
        assert "<<<<<<< HEAD" in report
        assert NOT_RECOVERABLE_GZIP in report

    def test_full_sweep_still_surfaces_the_one_real_stranded_line(self, guard_repo):
        clone, branches = guard_repo
        report = format_report(sweep(branches, base_ref="HEAD", cwd=str(clone)),
                                base_ref="HEAD")
        assert "1 carry line(s) genuinely MISSING" in report
        assert "1 recoverable line(s) total" in report


@pytest.fixture()
def shape_repo(tmp_path):
    """One stranded, well-formed JSONL line per committed day-file SHAPE.

    Reproduces the recall hole a verifier found in the first draft of the Class-A guard:
    the flat and nested-`meta/` shapes reported `missing: 1`, but the partition-directory
    shape (`dt=<date>/pass-<ts>.jsonl`, a REAL committed file — see
    `tape/sports_pairs/dt=2026-07-02/pass-20260702T231651Z.jsonl`) came back
    `contained=True`, `missing={}`, silently routed to `not_line_recoverable`.
    """
    remote = _init_repo(tmp_path / "remote.git")
    _git(remote, "config", "receive.denyCurrentBranch", "ignore")
    seeded = {
        "flat": "tape/anomalies/dt=2026-07-20.jsonl",
        "meta": "tape/weather_books/meta/dt=2026-07-20.jsonl",
        "partition": "tape/sports_pairs/dt=2026-07-20/pass-20260720T000000Z.jsonl",
        "manifest": "tape/crypto_hourly/_manifest.jsonl",
    }
    for rel in seeded.values():
        f = remote / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('{"a": 1}\n')
    _git(remote, "add", "tape")
    _git(remote, "commit", "-q", "-m", "seed one file per shape")
    _git(remote, "branch", "-M", "main")

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(remote), str(clone))

    names = {}
    for i, (label, rel) in enumerate(sorted(seeded.items())):
        branch = f"tape/hourly-20260720T0{i}00Z"
        names[label] = branch
        _git(remote, "checkout", "-q", "-b", branch)
        (remote / rel).write_text('{"a": 1}\n{"stranded": "%s"}\n' % label)
        _git(remote, "add", "tape")
        _git(remote, "commit", "-q", "-m", branch)
        _git(remote, "checkout", "-q", "main")

    branches = list_remote_tape_branches(remote="origin", cwd=str(clone))
    fetch_branches(branches, remote="origin", cwd=str(clone))
    return clone, branches, names, seeded


class TestEveryCommittedDayFileShapeIsChecked:
    """A whitelist is a RECALL decision: a shape it forgets goes silently unchecked."""

    @pytest.mark.parametrize("label", ["flat", "meta", "partition", "manifest"])
    def test_stranded_line_is_reported_missing_for_every_shape(self, shape_repo, label):
        clone, branches, names, seeded = shape_repo
        t = _triage_by_name(clone, branches)[names[label]]
        assert t.contained is False, f"{label}: stranded line went UNDETECTED"
        assert t.missing_files == {seeded[label]: 1}
        assert t.not_line_recoverable == {}
        assert t.corrupt_files == {}

    def test_report_counts_every_shape_as_recoverable(self, shape_repo):
        clone, branches, _names, _seeded = shape_repo
        report = format_report(sweep(branches, base_ref="HEAD", cwd=str(clone)),
                                base_ref="HEAD")
        assert "4 carry line(s) genuinely MISSING" in report
        assert "4 recoverable line(s) total" in report


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
