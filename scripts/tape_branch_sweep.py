#!/usr/bin/env python3
"""Stranded tape-branch sweep helper (LOOP-QUEUE.md step-0b; kb lessons L160/L161).

Builds the two things both lessons named as open work, so no future run has to
re-derive them by hand:

1. **Tree-hash fast path, per-file line-set containment as the real answer.**
   ``git rev-parse <rev>:<path>`` gives the tree object hash for a path at a
   revision in ONE command with no per-file work — if a branch's ``tape`` tree
   hash equals ``HEAD``'s, containment is proven outright with zero further work.
   But ``tape/`` is APPEND-ONLY and grows every hour, so this equality can only
   ever hold for the single most-recently-diverged branch checked before the next
   commit lands — for any older branch the whole-tree hash will differ from
   ``HEAD`` even when every line the branch carries is fully present in `HEAD`'s
   now-larger files. A tree-hash MISMATCH is therefore not "stranded tape" by
   itself; per this file's own docstring in an earlier draft it was mis-read as
   the terminal answer (191 of 192 real branches came back "NOT contained" on
   that reading, which was wrong — see below). The correct reading, and the one
   this module implements: a mismatch means "fall back to a per-file LINE-SET
   check" (`git ls-tree`/`git show` per file the branch touches, each branch line
   tested for membership in `HEAD`'s current version of that same path) — exactly
   the union-append/line-level-dedupe method LOOP-QUEUE.md step 0b already
   specifies. Only lines that fail that membership test are genuinely missing.
   HEAD-side file contents are cached across branches (many branches touch the
   same day-file) so the same blob is never re-read twice in one sweep.

   ``git merge-base --is-ancestor`` must NEVER be used for any of this (L160):
   `main` squash-merges every PR, so a tape branch is never an ancestor of `HEAD`
   even when every line it carries is already merged — `--is-ancestor` reports
   "stranded" on branches that are fully contained, every single time, sending
   step-0b sweeps chasing tape that needs no chasing. (This module contains no
   call to ``--is-ancestor`` — see ``tests/test_tape_branch_sweep.py`` for a
   source-text pin on that absence, the same discipline as the Hard-Rule #1
   ``ncep_gefs025`` check.)

2. **Malformed-name triage by commit date, never name order.** 44+ of ~192
   ``tape/*`` branches (2026-07-25 measurement) fail the canonical name shape
   ``tape/hourly-YYYYMMDDTHHMMZ`` — missing the ``T`` separator, or degenerate
   names like ``tape/hourly-Z`` / ``tape/hourly-`` with no timestamp at all.
   Because ``Z`` and the empty suffix sort AFTER every dated branch name
   lexically, a sweep that orders branches by NAME picks a degenerate one last,
   concludes it has swept past everything, and silently leaves real unswept tape
   behind. Malformed names are therefore never name-sorted here; they are ordered
   by their actual commit date (``git log -1 --format=%cI``), and the malformed
   count is always reported rather than skipped quietly (L161).

Read-only over git: this script only inspects refs and objects. It never pushes,
deletes a branch, or writes to the working tree. Deleting a swept branch remains a
human/run decision gated on "only after the PR containing its lines has merged"
(LOOP-QUEUE.md step 0b) — that action is deliberately NOT automated here.

``fetched=False`` on a `BranchTriage` is a distinct, honest signal from
``contained=None``: the former means this repo hasn't pulled that branch's commit
object down yet (call `fetch_branches` first, or run without `--no-fetch`); the
latter means the commit IS present locally but carries no `tape/` tree at all — a
genuine anomaly for a `tape/*`-named branch worth flagging, never silently
conflated with "not fetched" (this repo's `no_signal`-vs-`False` discipline, see
`scripts/tape_gap_monitor.py`).
"""
from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

CANONICAL_NAME_RE = re.compile(r"^tape/hourly-[0-9]{8}T[0-9]{4}Z$")

GitRunner = Callable[..., str]


def default_git_runner(args: List[str], cwd: Optional[str] = None) -> str:
    """Run a git command, returning stripped stdout. Raises RuntimeError on failure.

    Decodes stdout as UTF-8 with `errors="replace"` rather than `text=True`'s strict
    decoding: `git show <rev>:<path>` on real committed tape can hit non-UTF-8 byte
    sequences (observed live on this repo's tape — a strict decode crashes the whole
    sweep on the first such blob). Every OTHER caller in this module only ever reads
    ASCII hex shas / ISO dates / newline-separated paths from git plumbing commands, so
    lenient decoding changes nothing for them; only blob content (`git show`) can
    contain non-UTF-8 bytes, and there `errors="replace"` degrades a byte-exact
    containment check to a best-effort one on that one line rather than crashing the
    whole run — a deliberate, narrow trade documented here, not a silent one."""
    result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True)
    stdout = result.stdout.decode("utf-8", errors="replace")
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr.strip()}")
    return stdout.strip()


def is_malformed_branch_name(name: str) -> bool:
    """True when `name` (e.g. 'tape/hourly-20260725T0406Z', WITH the leading 'tape/' —
    the same shape `list_remote_tape_branches`/`parse_ls_remote` return) fails the
    canonical `tape/hourly-YYYYMMDDTHHMMZ` shape."""
    return not bool(CANONICAL_NAME_RE.match(name))


def commit_known_locally(sha: str, run_git: GitRunner = default_git_runner,
                          cwd: Optional[str] = None) -> bool:
    """Whether `sha`'s commit object is already present in this local repo (i.e. fetched)."""
    try:
        run_git(["cat-file", "-e", f"{sha}^{{commit}}"], cwd=cwd)
        return True
    except RuntimeError:
        return False


def tree_hash(rev: str, path: str, run_git: GitRunner = default_git_runner,
              cwd: Optional[str] = None) -> Optional[str]:
    """Tree object hash for `path` at `rev`, or None if `path` doesn't exist there.
    Caller must ensure `rev` is already fetched locally (see `commit_known_locally`)."""
    try:
        return run_git(["rev-parse", f"{rev}:{path}"], cwd=cwd)
    except RuntimeError:
        return None


def commit_date(rev: str, run_git: GitRunner = default_git_runner,
                 cwd: Optional[str] = None) -> Optional[str]:
    """ISO-8601 committer date for `rev`, or None if unresolvable."""
    try:
        return run_git(["log", "-1", "--format=%cI", rev], cwd=cwd)
    except RuntimeError:
        return None


def list_tree_files(rev: str, path: str, run_git: GitRunner = default_git_runner,
                     cwd: Optional[str] = None) -> List[str]:
    """Blob paths (relative to `path`) under `path` at `rev`, recursively. [] if `path`
    doesn't exist at `rev`. Expensive on this repo's `tape/` (13,000+ files in a single
    snapshot as of 2026-07-25) — prefer `diff_changed_files` when a comparison base is
    available; this is the full-enumeration fallback for when it isn't."""
    try:
        out = run_git(["ls-tree", "-r", "--name-only", f"{rev}:{path}"], cwd=cwd)
    except RuntimeError:
        return []
    return [p for p in out.splitlines() if p]


def diff_changed_files(base_tree: str, branch_tree: str, run_git: GitRunner = default_git_runner,
                        cwd: Optional[str] = None) -> List[str]:
    """Paths in `branch_tree` (e.g. an OLDER branch's tape/ snapshot) that are new or
    differ relative to `base_tree` (e.g. HEAD's), scoped to whatever root both tree
    hashes already represent. A git tree is a full snapshot, not a delta — a branch's
    `tape/` tree contains every historical day-file across every family, not just the
    ones that commit touched, so enumerating an entire tree (`list_tree_files`) to find
    what changed is enormously wasteful (13,000+ files per snapshot on this repo).

    Plain `git diff --name-only base_tree branch_tree` is NOT enough by itself: on an
    append-only tree where `base_tree` (HEAD) is chronologically newer than an old
    `branch_tree`, the union of differing paths is dominated by files that exist ONLY in
    `base_tree` — day-files added to HEAD after the old branch was created, which the
    branch never claimed to carry and are irrelevant to a containment question (measured
    live 2026-07-25: 3,196 raw differing paths for one branch, of which only 7 were
    actually files the branch carries). `--diff-filter=AM` keeps only paths that EXIST in
    `branch_tree` and are either new relative to `base_tree` (A) or present in both with
    different content (M) — exactly the files worth reading."""
    try:
        out = run_git(["diff", "--name-only", "--diff-filter=AM", base_tree, branch_tree],
                       cwd=cwd)
    except RuntimeError:
        return []
    return [p for p in out.splitlines() if p]


def read_blob_lines(rev: str, path: str, run_git: GitRunner = default_git_runner,
                     cwd: Optional[str] = None) -> Optional[List[str]]:
    """Non-empty lines of the blob at `path` for `rev`, or None if it doesn't exist there."""
    try:
        content = run_git(["show", f"{rev}:{path}"], cwd=cwd)
    except RuntimeError:
        return None
    return [line for line in content.splitlines() if line.strip()]


def blob_size(rev: str, path: str, run_git: GitRunner = default_git_runner,
              cwd: Optional[str] = None) -> Optional[int]:
    """Byte size of the blob at `path` for `rev`, or None if it doesn't exist there."""
    try:
        out = run_git(["cat-file", "-s", f"{rev}:{path}"], cwd=cwd)
        return int(out)
    except (RuntimeError, ValueError):
        return None


# tape/orderbook_depth, tape/universe_sweep, tape/sports_pairs alone total ~950MB (measured
# 2026-07-25) — reading full blob content for every branch that touches a bulk-family
# day-file would make a 192-branch sweep impractically slow. 2MB comfortably covers a
# healthy hourly-family day-file (observed 07-25: sports_pairs/dt=2026-07-25.jsonl is
# 684KB for one day) while excluding the bulk families by construction.
DEFAULT_MAX_FILE_BYTES = 2_000_000


def per_file_containment(branch_rev: str, base_ref: str, path: str,
                          run_git: GitRunner = default_git_runner,
                          cwd: Optional[str] = None,
                          head_line_cache: Optional[Dict[str, frozenset]] = None,
                          max_file_bytes: Optional[int] = DEFAULT_MAX_FILE_BYTES,
                          base_tree: Optional[str] = None,
                          branch_tree: Optional[str] = None,
                          ) -> Tuple[Dict[str, int], Dict[str, int]]:
    """For every file that DIFFERS between `branch_rev` and `base_ref` under `path`
    (via `diff_changed_files` — never full tree enumeration, see that function's
    docstring for why), count lines NOT present (line-level set membership, matching
    LOOP-QUEUE.md step 0b's own union-append/dedupe method) in `base_ref`'s current
    version of that same file. Files IDENTICAL between the two trees are never even
    read — the diff already proves every line in them matches.

    Returns `(missing, skipped)`:
      - `missing`: {file: missing_count} for files with >=1 genuinely-absent line.
      - `skipped`: {file: byte_size} for files whose branch-side blob exceeds
        `max_file_bytes` — SKIPPED, not read at all, and never silently folded into
        "contained": a branch with skipped files and an empty `missing` dict means "no
        problem found in what was checked", not "proven fully contained". Pass
        `max_file_bytes=None` to disable the guard and check every file regardless of size.

    `head_line_cache` (keyed by the full `path/file` string) lets a caller sweeping many
    branches read each `base_ref`-side file only once, since many branches share day-files.
    `base_tree`/`branch_tree`: pass already-computed tree hashes to skip re-deriving them
    (the caller in `triage_branch` already has both).
    """
    if head_line_cache is None:
        head_line_cache = {}
    if base_tree is None:
        base_tree = tree_hash(base_ref, path, run_git, cwd)
    if branch_tree is None:
        branch_tree = tree_hash(branch_rev, path, run_git, cwd)
    missing: Dict[str, int] = {}
    skipped: Dict[str, int] = {}
    if branch_tree is None:
        return missing, skipped  # nothing to compare — caller handles the "no tree" case
    if base_tree is None:
        # No base tree to diff against at all (rare: base_ref itself lacks `path`) — fall
        # back to full enumeration, the only case where that cost is unavoidable.
        changed_files = list_tree_files(branch_rev, path, run_git, cwd)
    else:
        changed_files = diff_changed_files(base_tree, branch_tree, run_git, cwd)
    for rel_file in changed_files:
        full_path = f"{path}/{rel_file}"
        if max_file_bytes is not None:
            size = blob_size(branch_rev, full_path, run_git, cwd)
            if size is not None and size > max_file_bytes:
                skipped[full_path] = size
                continue
        if full_path not in head_line_cache:
            base_lines = read_blob_lines(base_ref, full_path, run_git, cwd)
            head_line_cache[full_path] = frozenset(base_lines) if base_lines else frozenset()
        base_set = head_line_cache[full_path]
        branch_lines = read_blob_lines(branch_rev, full_path, run_git, cwd) or []
        missing_count = sum(1 for line in branch_lines if line not in base_set)
        if missing_count:
            missing[full_path] = missing_count
    return missing, skipped


@dataclass
class BranchTriage:
    name: str
    sha: str
    malformed: bool
    fetched: bool
    contained: Optional[bool]  # None only when fetched but the branch has no `tape/` tree
    commit_date: Optional[str]  # populated only for malformed branches (ordering fallback)
    missing_files: Dict[str, int] = field(default_factory=dict)  # file -> missing-line count
    skipped_files: Dict[str, int] = field(default_factory=dict)  # file -> byte size, size-guard

    @property
    def fully_verified(self) -> bool:
        """False when the size guard skipped >=1 file — a `contained=True` result is then
        "no problem found in what WAS checked", not a proof of full containment. Always True
        when `contained` is False (a genuine problem was already found) or None (no tape/
        tree — nothing to skip)."""
        return not self.skipped_files


def triage_branch(sha: str, name: str, base_ref: str = "HEAD", path: str = "tape",
                   run_git: GitRunner = default_git_runner,
                   cwd: Optional[str] = None,
                   head_line_cache: Optional[Dict[str, frozenset]] = None,
                   max_file_bytes: Optional[int] = DEFAULT_MAX_FILE_BYTES) -> BranchTriage:
    malformed = is_malformed_branch_name(name)
    if not commit_known_locally(sha, run_git, cwd):
        return BranchTriage(name=name, sha=sha, malformed=malformed, fetched=False,
                             contained=None, commit_date=None)
    base_tree = tree_hash(base_ref, path, run_git, cwd)
    branch_tree = tree_hash(sha, path, run_git, cwd)
    cdate = commit_date(sha, run_git, cwd) if malformed else None

    if branch_tree is None:
        return BranchTriage(name=name, sha=sha, malformed=malformed, fetched=True,
                             contained=None, commit_date=cdate)
    if branch_tree == base_tree:
        # Fast path (L160): identical trees mean containment with zero per-file work.
        return BranchTriage(name=name, sha=sha, malformed=malformed, fetched=True,
                             contained=True, commit_date=cdate)

    # Mismatch does NOT mean "not contained" on an append-only tree — fall back to the
    # per-file line-set check (diff-scoped, not a full tree walk) to find out what, if
    # anything, is genuinely missing. Reuse the tree hashes already computed above.
    missing, skipped = per_file_containment(sha, base_ref, path, run_git, cwd,
                                             head_line_cache, max_file_bytes,
                                             base_tree=base_tree, branch_tree=branch_tree)
    return BranchTriage(name=name, sha=sha, malformed=malformed, fetched=True,
                         contained=(len(missing) == 0), commit_date=cdate,
                         missing_files=missing, skipped_files=skipped)


def sweep(branches: List[Tuple[str, str]], base_ref: str = "HEAD", path: str = "tape",
          run_git: GitRunner = default_git_runner,
          cwd: Optional[str] = None,
          max_file_bytes: Optional[int] = DEFAULT_MAX_FILE_BYTES) -> List[BranchTriage]:
    """`branches`: (sha, name) pairs, e.g. from `parse_ls_remote`. Malformed-name branches
    come back with `commit_date` populated so the CALLER never has to fall back to name order
    (L161) — this function itself does no branch-to-branch ordering. A single
    `head_line_cache` is shared across all branches so `base_ref`-side files are read once
    even when many branches touch the same day-file."""
    head_line_cache: Dict[str, frozenset] = {}
    return [triage_branch(sha, name, base_ref, path, run_git, cwd, head_line_cache,
                           max_file_bytes)
            for sha, name in branches]


def parse_ls_remote(output: str, prefix: str = "refs/heads/") -> List[Tuple[str, str]]:
    """Parse `git ls-remote --heads ...` output into (sha, short-name) pairs."""
    branches = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        sha, ref = line.split(None, 1)
        if ref.startswith(prefix):
            branches.append((sha, ref[len(prefix):]))
    return branches


def list_remote_tape_branches(remote: str = "origin", run_git: GitRunner = default_git_runner,
                               cwd: Optional[str] = None) -> List[Tuple[str, str]]:
    out = run_git(["ls-remote", "--heads", remote, "refs/heads/tape/*"], cwd=cwd)
    return parse_ls_remote(out)


def fetch_branches(branches: List[Tuple[str, str]], remote: str = "origin",
                    run_git: GitRunner = default_git_runner,
                    cwd: Optional[str] = None) -> None:
    """Fetch every listed branch's commit object into local remote-tracking refs, one `git
    fetch` call, so `triage_branch` finds them via `commit_known_locally`. By ref name (not
    bare sha) — servers commonly reject fetching an arbitrary sha unless
    `uploadpack.allowReachableSHA1InWant` is set, but fetching a known branch head always
    works."""
    if not branches:
        return
    refspecs = [f"+refs/heads/{name}:refs/remotes/{remote}/tape-sweep/{name}"
                for _sha, name in branches]
    run_git(["fetch", remote, "--no-tags"] + refspecs, cwd=cwd)


def format_report(triage: List[BranchTriage], base_ref: str = "HEAD") -> str:
    total = len(triage)
    not_fetched = [t for t in triage if not t.fetched]
    malformed = [t for t in triage if t.malformed]
    contained_verified = [t for t in triage if t.contained is True and t.fully_verified]
    contained_unverified = [t for t in triage if t.contained is True and not t.fully_verified]
    has_missing = [t for t in triage if t.fetched and t.contained is False]
    no_tape = [t for t in triage if t.fetched and t.contained is None]

    lines = [
        f"tape-branch sweep: {total} branch(es) checked against {base_ref}",
        f"  {len(malformed)} malformed name(s) (fail {CANONICAL_NAME_RE.pattern})",
        f"  {len(contained_verified)} fully contained + verified (every line checked and "
        f"present in {base_ref}; safe to delete once its PR, if any, merged)",
        f"  {len(contained_unverified)} no problem found but NOT FULLY VERIFIED (>=1 file "
        "skipped by the size guard — see skipped-file list; do not delete on this alone)",
        f"  {len(has_missing)} carry line(s) genuinely MISSING from {base_ref} (per-file "
        "line-set check, not a raw tree-hash mismatch — see module docstring)",
        f"  {len(no_tape)} fetched but carry no tape/ tree at all (anomaly for a tape/* branch)",
        f"  {len(not_fetched)} not yet fetched locally (run with fetch enabled, or "
        "`git fetch` them first)",
    ]
    if has_missing:
        lines.append("  branches with genuinely missing lines:")
        for t in has_missing:
            total_missing = sum(t.missing_files.values())
            lines.append(f"    - {t.name} ({t.sha[:12]}): {total_missing} line(s) across "
                          f"{len(t.missing_files)} file(s)")
            for f, count in sorted(t.missing_files.items()):
                lines.append(f"        {f}: {count} missing line(s)")
    if contained_unverified:
        lines.append("  branches with skipped (oversized) files — no proof of containment:")
        for t in contained_unverified:
            for f, size in sorted(t.skipped_files.items()):
                lines.append(f"    - {t.name} ({t.sha[:12]}): {f} ({size:,} bytes, skipped)")
    if no_tape:
        lines.append("  branches with no tape/ tree (anomaly):")
        for t in no_tape:
            lines.append(f"    - {t.name} ({t.sha[:12]})")
    if malformed:
        lines.append("  malformed-name branches, ordered by commit date (never name order):")
        for t in sorted(malformed, key=lambda t: t.commit_date or ""):
            lines.append(f"    - {t.name} ({t.sha[:12]}) committed {t.commit_date or 'unknown'}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--base-ref", default="HEAD")
    parser.add_argument("--path", default="tape")
    parser.add_argument("--no-fetch", action="store_true",
                         help="skip the fetch step (assumes branches are already fetched)")
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES,
                         help="skip per-file containment check for files larger than this "
                              "(default %(default)s bytes; excludes this repo's bulk "
                              "families by construction — see module docstring)")
    parser.add_argument("--no-size-guard", action="store_true",
                         help="disable the size guard entirely (checks every file "
                              "regardless of size — can be very slow on bulk families)")
    parser.add_argument("--limit", type=int, default=None,
                         help="only triage the first N listed branches (per-file checks are "
                              "one-or-more git subprocesses per file, so a full historical "
                              "sweep over hundreds of branches can take minutes; --limit lets "
                              "a single run make bounded, incremental progress). Skipped "
                              "branches are counted and reported, never silently dropped.")
    args = parser.parse_args(argv)

    branches = list_remote_tape_branches(args.remote)
    total_listed = len(branches)
    if args.limit is not None:
        branches = branches[:args.limit]
    if not args.no_fetch:
        fetch_branches(branches, args.remote)
    max_bytes = None if args.no_size_guard else args.max_file_bytes
    triage = sweep(branches, base_ref=args.base_ref, path=args.path, max_file_bytes=max_bytes)
    if args.limit is not None and total_listed > len(branches):
        print(f"NOTE: --limit {args.limit} applied; {total_listed - len(branches)} of "
              f"{total_listed} listed branch(es) were NOT triaged this run.")
    print(format_report(triage, base_ref=args.base_ref))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
