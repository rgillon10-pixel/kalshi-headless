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
import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

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

# L216 (2026-07-28): a plain size-guard skip on these families is a "not checked" signal,
# not a "checked and clean" one — and three consecutive runs (PRs #217/#219/#220) misread
# it as the latter on `orderbook_depth`/`universe_sweep`/`sports_pairs`, missing 21,303
# genuinely-stranded lines. Every line in one of these families' captures is minted
# atomically by a single collector pass and shares one `capture_id` (a 20,000-line
# `universe_sweep` capture is ONE `capture_id`, not 20,000 independent facts) — so
# comparing the small set of DISTINCT `capture_id` values between branch and HEAD is a
# structurally-sound, cheap proxy for "is every capture this branch carries already
# present in HEAD", without materializing a 20MB file into a frozenset of full line
# strings. Coarser than the line-level check (a capture_id match does not prove every byte
# of that capture is byte-identical), so it is surfaced separately in
# `BranchTriage.capture_id_checked` and the report — never silently folded into
# "fully line-verified". `weather_books` added the same day this fix was built: verifying
# this exact fix against the live `tape/hourly-20260727T1303Z` recovery branch found its
# `weather_books` day-file ALSO exceeds `DEFAULT_MAX_FILE_BYTES` (2,303,754 bytes on that
# branch; HEAD's `dt=2026-07-24/26/27` day-files measured 07-28 at 2.75MB/2.23MB/4.48MB) —
# L216's own text named only the three families true as of its 2026-07-25 measurement, but
# this family has since crossed the same line and carries the same `capture_id` field, so
# it gets the same treatment rather than leaving a freshly-discovered instance of the exact
# gap this fix closes.
#
# L235 (2026-07-31): the L216/L217 fix above closed the gap for the four families it could
# NAME, and thereby reproduced, one layer up, the exact defect it was written to fix — an
# ENUMERATION where a DERIVATION was called for. Measured on this run's 218-branch sweep:
# 126 branches (57.8%) still came back "no problem found but NOT FULLY VERIFIED" because
# their only oversized files were `crypto_hourly` (121 branches), `econ_prints` (5) and
# `anomalies` (1) day-files — every one of which carries `capture_id` and answers the
# capture_id-set check perfectly well (verified live: `crypto_hourly/dt=2026-07-14.jsonl`
# 116 branch ids vs 143 HEAD ids; `econ_prints/dt=2026-07-14.jsonl` 137 vs 137;
# `anomalies/dt=2026-07-21.jsonl` 20 vs 21), but were excluded solely for not appearing in
# the frozenset below. The gate is therefore no longer a family allowlist: the check is
# ATTEMPTED on every oversized file and the blob's own content decides whether it applies
# (`capture_ids_in_blob` returning empty == "no signal" == honest size-guard skip, the
# behaviour L217 already relied on). A tape family that starts carrying `capture_id`, or
# newly crosses the 2MB line, is covered the day it does so, with no constant to update.
#
# The frozenset survives ONLY as an observational record of which families have been
# MEASURED above `DEFAULT_MAX_FILE_BYTES` (it is cited by name in `kb/lessons/00-lessons.md`
# L217 and `findings/2026-07-28-...-bulk-family-blindspot.md`). It is NOT read by
# `per_file_containment` and must never again become a gate — if you find yourself adding a
# name here to make a check fire, the check is wrong, not the list.
BULK_CAPTURE_ID_FAMILIES = frozenset(
    {"orderbook_depth", "universe_sweep", "sports_pairs", "weather_books",
     "crypto_hourly", "econ_prints", "anomalies"})


def capture_ids_in_blob(rev: str, path: str, run_git: GitRunner = default_git_runner,
                         cwd: Optional[str] = None) -> Optional[frozenset]:
    """Distinct `capture_id` values found in the JSONL blob at `path` for `rev`, or None
    if the blob doesn't exist there. A line that isn't valid JSON, or that parses but
    carries no `capture_id` key, is silently skipped for THIS extraction (never crashes
    the sweep on one bad line, matching `default_git_runner`'s lenient-decode discipline)
    — but note that skipping means an empty/partial result here is a "no signal" outcome,
    not proof the file has no capture_id lines; the caller (`per_file_containment`) treats
    an empty result as "no signal" and falls back to the honest size-guard skip rather than
    reading zero missing capture_ids as zero missing content."""
    lines = read_blob_lines(rev, path, run_git, cwd)
    if lines is None:
        return None
    ids = set()
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        cid = obj.get("capture_id") if isinstance(obj, dict) else None
        if cid is not None:
            ids.add(cid)
    return frozenset(ids)


# ─── Union-appendability triage of a "genuinely missing" line (L247, 2026-08-01) ──
#
# A line absent from HEAD is a containment answer; it is NOT automatically a line step 0b
# should union-append. The 2026-08-01 sweep found 13 branches carrying "genuinely missing"
# lines and ZERO of them were tape: 5 branches carried the three unresolved git conflict
# markers of the 2026-07-23 incident (`<<<<<<< HEAD` / `=======` / `>>>>>>> <sha> (...)`,
# lesson L142) sitting inside `anomalies`/`econ_prints` day-files, and 8 carried two
# superseded prose headers of `tape/cloud-env-check.md`, a hand-written MARKDOWN doc that
# happens to live under `tape/` and is not append-only JSONL at all. Union-appending the
# first class would re-inject the exact corruption `scripts/invariants.py`'s
# `_tape_conflict_marker_issues` gate exists to catch — the sweep would hand a future run a
# red gate — and the second would splice a stale document header into a living doc.
#
# So the report distinguishes them. Deliberately CONSERVATIVE about what counts as
# appendable: a line is appendable only if its file is a `.jsonl` day-file AND the line
# parses as JSON. Anything else is reported as unappendable and left for a human, which is
# the right error direction — a wrongly-withheld tape line is visible in the next sweep,
# a wrongly-appended conflict marker breaks `main`'s gate.
_CONFLICT_MARKER_RE = re.compile(r"^(?:<{7}|={7}|>{7})(?:\s|$)")


def missing_line_is_appendable(full_path: str, line: str) -> bool:
    """True only for a line that step 0b may safely union-append into `main`'s tape.

    A tape line is a JSON OBJECT, so a bare JSON scalar (`123`, `null`, a quoted string)
    or array is refused too — it parses, but it is not a record, and propagating it would
    spread corruption rather than rescue tape."""
    if not full_path.endswith(".jsonl"):
        return False
    if _CONFLICT_MARKER_RE.match(line):
        return False
    try:
        return isinstance(json.loads(line), dict)
    except Exception:
        return False


def per_file_containment(branch_rev: str, base_ref: str, path: str,
                          run_git: GitRunner = default_git_runner,
                          cwd: Optional[str] = None,
                          head_line_cache: Optional[Dict[str, frozenset]] = None,
                          max_file_bytes: Optional[int] = DEFAULT_MAX_FILE_BYTES,
                          base_tree: Optional[str] = None,
                          branch_tree: Optional[str] = None,
                          head_capture_id_cache: Optional[Dict[str, frozenset]] = None,
                          unappendable_out: Optional[Dict[str, int]] = None,
                          ) -> Tuple[Dict[str, int], Dict[str, int], Dict[str, int]]:
    """For every file that DIFFERS between `branch_rev` and `base_ref` under `path`
    (via `diff_changed_files` — never full tree enumeration, see that function's
    docstring for why), count lines NOT present (line-level set membership, matching
    LOOP-QUEUE.md step 0b's own union-append/dedupe method) in `base_ref`'s current
    version of that same file. Files IDENTICAL between the two trees are never even
    read — the diff already proves every line in them matches.

    Returns `(missing, skipped, capture_id_checked)`:
      - `missing`: {file: missing_count} for files with >=1 genuinely-absent line
        (line-level check).
      - `skipped`: {file: byte_size} for files whose branch-side blob exceeds
        `max_file_bytes` AND got no other signal — SKIPPED, not read at all, and never
        silently folded into "contained": a branch with skipped files and an empty
        `missing` dict means "no problem found in what was checked", not "proven fully
        contained". Pass `max_file_bytes=None` to disable the guard and check every file
        regardless of size.
      - `capture_id_checked`: {file: missing_capture_id_count} for oversized files whose
        branch side yielded >=1 real `capture_id` (L216, widened to every family by L235 —
        the blob's content qualifies it, never a family allowlist), checked at
        capture_id granularity instead of skipped
        outright. 0 means every capture_id the branch carries is already in HEAD's
        version of that file (coarser than, but a genuine alternative to, a full
        line-level proof); >0 means the branch carries at least one capture_id absent
        from HEAD (a real signal of missing content). An oversized bulk-family file that
        yields ZERO capture_ids (e.g. malformed content, or a family whose schema simply
        has no such field) still falls back to `skipped` — no signal is never read as a
        clean bill of health.

    `head_line_cache` (keyed by the full `path/file` string) lets a caller sweeping many
    branches read each `base_ref`-side file only once, since many branches share day-files.
    `head_capture_id_cache` is the same idea, keyed the same way, for the coarser
    capture_id-set path. `base_tree`/`branch_tree`: pass already-computed tree hashes to
    skip re-deriving them (the caller in `triage_branch` already has both).
    """
    if head_line_cache is None:
        head_line_cache = {}
    if head_capture_id_cache is None:
        head_capture_id_cache = {}
    if base_tree is None:
        base_tree = tree_hash(base_ref, path, run_git, cwd)
    if branch_tree is None:
        branch_tree = tree_hash(branch_rev, path, run_git, cwd)
    missing: Dict[str, int] = {}
    skipped: Dict[str, int] = {}
    capture_id_checked: Dict[str, int] = {}
    if branch_tree is None:
        return missing, skipped, capture_id_checked  # nothing to compare — caller handles "no tree"
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
                # L235: capability is DERIVED from the blob, never from a family name.
                # Try the capture_id-set check on EVERY oversized file; the extraction
                # itself decides whether this family can support the check.
                branch_ids = capture_ids_in_blob(branch_rev, full_path, run_git, cwd)
                if branch_ids:  # non-empty: a real signal, not just "no capture_id found"
                    if full_path not in head_capture_id_cache:
                        head_ids = capture_ids_in_blob(base_ref, full_path, run_git, cwd)
                        head_capture_id_cache[full_path] = head_ids or frozenset()
                    head_ids = head_capture_id_cache[full_path]
                    capture_id_checked[full_path] = len(branch_ids - head_ids)
                    continue
                skipped[full_path] = size
                continue
        if full_path not in head_line_cache:
            base_lines = read_blob_lines(base_ref, full_path, run_git, cwd)
            head_line_cache[full_path] = frozenset(base_lines) if base_lines else frozenset()
        base_set = head_line_cache[full_path]
        branch_lines = read_blob_lines(branch_rev, full_path, run_git, cwd) or []
        absent = [line for line in branch_lines if line not in base_set]
        if absent:
            missing[full_path] = len(absent)
            if unappendable_out is not None:
                n_bad = sum(1 for line in absent
                            if not missing_line_is_appendable(full_path, line))
                if n_bad:
                    unappendable_out[full_path] = n_bad
    return missing, skipped, capture_id_checked


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
    capture_id_checked_files: Dict[str, int] = field(default_factory=dict)  # file -> missing capture_id count (L216)
    unappendable_files: Dict[str, int] = field(default_factory=dict)  # file -> NOT-union-appendable missing lines (L247)

    @property
    def all_missing_unappendable(self) -> bool:
        """True when EVERY genuinely-missing line this branch carries is one step 0b must
        NOT union-append (a git conflict marker, or a line in a non-`.jsonl` file under
        `tape/`) — i.e. the branch is 'not contained' but there is no tape to rescue. The
        2026-08-01 sweep found all 13 not-contained branches were in exactly this state."""
        return (bool(self.missing_files)
                and sum(self.unappendable_files.values()) == sum(self.missing_files.values()))

    @property
    def fully_verified(self) -> bool:
        """False when the size guard skipped >=1 file with NO check of any kind — a
        `contained=True` result is then "no problem found in what WAS checked", not a
        proof of full containment. Always True when `contained` is False (a genuine
        problem was already found) or None (no tape/ tree — nothing to skip). A file
        resolved via the coarser `capture_id_checked_files` path (L216) does NOT count
        against this — it was genuinely checked, just at capture-id rather than
        line-level granularity; see `capture_id_only` to distinguish the two."""
        return not self.skipped_files

    @property
    def capture_id_only(self) -> bool:
        """True when at least one file's containment rests solely on the coarser
        capture_id-set check (L216) rather than a full line-level proof — surfaced so a
        reader never mistakes "no missing capture_id" for "every line verified"."""
        return bool(self.capture_id_checked_files)


def triage_branch(sha: str, name: str, base_ref: str = "HEAD", path: str = "tape",
                   run_git: GitRunner = default_git_runner,
                   cwd: Optional[str] = None,
                   head_line_cache: Optional[Dict[str, frozenset]] = None,
                   max_file_bytes: Optional[int] = DEFAULT_MAX_FILE_BYTES,
                   head_capture_id_cache: Optional[Dict[str, frozenset]] = None) -> BranchTriage:
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
    unappendable: Dict[str, int] = {}
    missing, skipped, capture_id_checked = per_file_containment(
        sha, base_ref, path, run_git, cwd, head_line_cache, max_file_bytes,
        base_tree=base_tree, branch_tree=branch_tree,
        head_capture_id_cache=head_capture_id_cache,
        unappendable_out=unappendable)
    contained = len(missing) == 0 and all(v == 0 for v in capture_id_checked.values())
    return BranchTriage(name=name, sha=sha, malformed=malformed, fetched=True,
                         contained=contained, commit_date=cdate,
                         missing_files=missing, skipped_files=skipped,
                         capture_id_checked_files=capture_id_checked,
                         unappendable_files=unappendable)


def sweep(branches: List[Tuple[str, str]], base_ref: str = "HEAD", path: str = "tape",
          run_git: GitRunner = default_git_runner,
          cwd: Optional[str] = None,
          max_file_bytes: Optional[int] = DEFAULT_MAX_FILE_BYTES) -> List[BranchTriage]:
    """`branches`: (sha, name) pairs, e.g. from `parse_ls_remote`. Malformed-name branches
    come back with `commit_date` populated so the CALLER never has to fall back to name order
    (L161) — this function itself does no branch-to-branch ordering. A single
    `head_line_cache` (and `head_capture_id_cache`, L216) is shared across all branches so
    `base_ref`-side files are read once even when many branches touch the same day-file."""
    head_line_cache: Dict[str, frozenset] = {}
    head_capture_id_cache: Dict[str, frozenset] = {}
    return [triage_branch(sha, name, base_ref, path, run_git, cwd, head_line_cache,
                           max_file_bytes, head_capture_id_cache)
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
    contained_verified = [t for t in triage
                           if t.contained is True and t.fully_verified and not t.capture_id_only]
    contained_capture_id_only = [t for t in triage
                                  if t.contained is True and t.fully_verified and t.capture_id_only]
    contained_unverified = [t for t in triage if t.contained is True and not t.fully_verified]
    has_missing = [t for t in triage if t.fetched and t.contained is False]
    no_tape = [t for t in triage if t.fetched and t.contained is None]

    lines = [
        f"tape-branch sweep: {total} branch(es) checked against {base_ref}",
        f"  {len(malformed)} malformed name(s) (fail {CANONICAL_NAME_RE.pattern})",
        f"  {len(contained_verified)} fully contained + verified (every line checked and "
        f"present in {base_ref}; safe to delete once its PR, if any, merged)",
        f"  {len(contained_capture_id_only)} contained via capture_id-level check only "
        f"(L216 — one or more bulk-family files were too large for a full line-set diff; "
        "every distinct capture_id the branch carries is present in "
        f"{base_ref}, but individual bytes were not compared — coarser than the line-level "
        "proof above, still a real check, not a size-guard skip)",
        f"  {len(contained_unverified)} no problem found but NOT FULLY VERIFIED (>=1 file "
        "skipped by the size guard with no signal at all — see skipped-file list; do not "
        "delete on this alone)",
        f"  {len(has_missing)} carry line(s) or capture_id(s) genuinely MISSING from "
        f"{base_ref} (per-file line-set check, or capture_id-set check for oversized bulk "
        "families — not a raw tree-hash mismatch; see module docstring)",
        f"  {sum(1 for t in has_missing if t.all_missing_unappendable)} of those carry "
        "NO union-appendable tape at all — every missing line is a git conflict marker or "
        "sits in a non-`.jsonl` file under tape/ (L247; sweeping them would re-inject the "
        "L142 corruption `invariants.py` gates against)",
        f"  {len(no_tape)} fetched but carry no tape/ tree at all (anomaly for a tape/* branch)",
        f"  {len(not_fetched)} not yet fetched locally (run with fetch enabled, or "
        "`git fetch` them first)",
    ]
    if has_missing:
        lines.append("  branches with genuinely missing lines/capture_ids:")
        for t in has_missing:
            total_missing = sum(t.missing_files.values())
            if total_missing:
                lines.append(f"    - {t.name} ({t.sha[:12]}): {total_missing} line(s) across "
                              f"{len(t.missing_files)} file(s)")
                for f, count in sorted(t.missing_files.items()):
                    bad = t.unappendable_files.get(f, 0)
                    suffix = ""
                    if bad:
                        suffix = (f" — {bad} NOT union-appendable (conflict marker / "
                                  "non-JSONL file); do NOT sweep those, L247")
                    lines.append(f"        {f}: {count} missing line(s){suffix}")
                if t.all_missing_unappendable:
                    lines.append("        ^ EVERY missing line here is unappendable — "
                                 "this branch carries NO strandable tape (L247)")
            missing_capture_files = {f: n for f, n in t.capture_id_checked_files.items() if n}
            if missing_capture_files:
                total_missing_captures = sum(missing_capture_files.values())
                lines.append(f"    - {t.name} ({t.sha[:12]}): {total_missing_captures} "
                              f"missing capture_id(s) across {len(missing_capture_files)} "
                              "bulk-family file(s) (capture_id-level check, L216)")
                for f, count in sorted(missing_capture_files.items()):
                    lines.append(f"        {f}: {count} missing capture_id(s)")
    if contained_capture_id_only:
        lines.append("  branches contained via capture_id-level check only (bulk families):")
        for t in contained_capture_id_only:
            for f in sorted(t.capture_id_checked_files):
                lines.append(f"    - {t.name} ({t.sha[:12]}): {f} (0 missing capture_id(s))")
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


ASSERT_CONTAINED_EXIT_CODE = 2


def resolve_branch_sha(name: str, remote: str = "origin",
                        run_git: GitRunner = default_git_runner,
                        cwd: Optional[str] = None) -> Optional[str]:
    """SHA of a remote tape branch by name, or None if the remote does not have it."""
    full = name if name.startswith("tape/") else f"tape/{name}"
    out = run_git(["ls-remote", "--heads", remote, f"refs/heads/{full}"], cwd)
    for sha, listed in parse_ls_remote(out):
        if listed == full:
            return sha
    return None


def assert_contained_report(triages: List[BranchTriage],
                             not_on_remote: Sequence[str] = ()) -> Tuple[str, bool]:
    """Render the post-recovery self-check (L301). Returns (text, ok).

    `ok` is True only when EVERY named branch triages contained with zero missing lines and
    zero missing capture_ids — the exact claim a "stranded lines recovered" commit message
    makes. A branch the remote does not have, or one whose commit is not fetched, is a
    FAILURE of the check, never a silent pass: an unverifiable claim is not a verified one.
    """
    lines = ["post-recovery containment check (L301):"]
    ok = True
    for t in triages:
        n_missing = sum(t.missing_files.values())
        n_cids = sum(t.capture_id_checked_files.values())
        if not t.fetched:
            lines.append(f"  UNVERIFIABLE {t.name}: commit {t.sha[:12]} not fetched locally")
            ok = False
        elif t.contained and not n_missing and not n_cids:
            note = " (capture_id-level only)" if t.capture_id_only else ""
            skipped = "" if t.fully_verified else " (WARNING: >=1 file size-guard-skipped)"
            if not t.fully_verified:
                ok = False
            lines.append(f"  CONTAINED    {t.name}{note}{skipped}")
        else:
            lines.append(f"  STILL MISSING {t.name}: {n_missing} line(s), "
                         f"{n_cids} capture_id(s)")
            for f, n in sorted(t.missing_files.items()):
                lines.append(f"      - {f}: {n} line(s)")
            for f, n in sorted(t.capture_id_checked_files.items()):
                if n:
                    lines.append(f"      - {f}: {n} capture_id(s)")
            ok = False
    for full in not_on_remote:
        lines.append(f"  NOT ON REMOTE {full} (nothing to verify - name typo?)")
        ok = False
    lines.append("  VERDICT: " + ("all named branches contained"
                                  if ok else "NOT recovered - do not claim recovery"))
    return "\n".join(lines), ok


def _run_assert_contained(args) -> int:
    names = [n.strip() for n in args.assert_contained.split(",") if n.strip()]
    pairs: List[Tuple[str, str]] = []
    missing_names: List[str] = []
    for n in names:
        sha = resolve_branch_sha(n, args.remote)
        full = n if n.startswith("tape/") else f"tape/{n}"
        if sha is None:
            missing_names.append(full)
        else:
            pairs.append((sha, full))
    if not args.no_fetch and pairs:
        fetch_branches(pairs, args.remote)
    max_bytes = None if args.no_size_guard else args.max_file_bytes
    triage = sweep(pairs, base_ref=args.base_ref, path=args.path, max_file_bytes=max_bytes)
    text, ok = assert_contained_report(triage, missing_names)
    print(text)
    return 0 if ok else ASSERT_CONTAINED_EXIT_CODE


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
    parser.add_argument("--assert-contained", default=None, metavar="BRANCH[,BRANCH...]",
                         help="POST-RECOVERY SELF-CHECK (L301). Re-triage only the named "
                              "branch(es) against --base-ref and exit 2 if ANY of them still "
                              "carries a genuinely-missing line or capture_id. A run that "
                              "union-appends a branch's stranded tape must call this against "
                              "its own post-append commit before claiming the branch is "
                              "recovered: PR #305 was titled 'recover hourly-20260806T0726Z "
                              "stranded lines', recovered that branch's two bulk families "
                              "only, and left six other capture_ids on the branch for a day. "
                              "Names may be given with or without the 'tape/' prefix.")
    parser.add_argument("--limit", type=int, default=None,
                         help="only triage the first N listed branches (per-file checks are "
                              "one-or-more git subprocesses per file, so a full historical "
                              "sweep over hundreds of branches can take minutes; --limit lets "
                              "a single run make bounded, incremental progress). Skipped "
                              "branches are counted and reported, never silently dropped.")
    args = parser.parse_args(argv)

    if args.assert_contained:
        return _run_assert_contained(args)

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
