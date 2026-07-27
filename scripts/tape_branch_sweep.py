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

**Two guards added 2026-07-27 after a near-miss (both false-positive classes were
real, both would have corrupted committed tape if union-appended).** A step-0b sweep
over 198 remote ``tape/*`` branches reported "13 carry line(s) genuinely MISSING from
HEAD". All 13 were false positives, in two distinct classes:

*Class A — non-JSONL prose.* 8 branches, 2 "missing lines" each, all on
``tape/cloud-env-check.md`` — a MARKDOWN document, not an append-only day-file. The
flagged lines were superseded prose from the pre-reset lineage (``## UPDATE 2026-07-09
(Q0b): egress unblocked`` and a reworded provenance line). Line-set containment is only
a meaningful recovery test for APPEND-ONLY files with unique per-line capture identity;
edited prose will look "missing" forever, and union-appending it duplicates and corrupts
the doc. So only paths whose SHAPE is an append-only capture file
(``is_recoverable_capture_file``; day-file, partition-day per-pass file, or append-mode
manifest — the exact whitelist and its validation are the next section) are eligible for
the line-set check — matched on filename/parent-directory shape, not directory depth,
because ``tape/weather_books/meta/dt=*.jsonl`` is a real nested day-file. Every other
path a branch touches is reported under
``not_line_recoverable`` ("reported for human review, NEVER auto-appended") and NEVER
contributes to the genuinely-MISSING count. ``tape/ws_depth/dt=*.jsonl.gz`` (a designed
future family, Q47) is excluded with its own explicit reason: a line-set check over gzip
bytes is meaningless.

*Class B — committed git conflict markers.* 5 branches, 6 "missing lines" each, on
``tape/anomalies/dt=2026-07-18.jsonl`` and ``tape/econ_prints/dt=2026-07-18.jsonl``. The
3 unique lines per file were literally ``<<<<<<< HEAD`` / ``=======`` /
``>>>>>>> 58145d7 (tape: hourly pass 2026-07-18T09:30:28Z (vps))`` — an unresolved merge
committed into tape on those stranded branches (reproduce:
``git show c57dadf70975:tape/anomalies/dt=2026-07-18.jsonl | grep -n '^<<<<<<<'``; `main`
is clean, ``grep -c`` gives 0). Every genuine data line on those branches was already in
HEAD; the ONLY thing the sweep flagged as recoverable was the corruption. So a candidate
missing line from a ``dt=*.jsonl`` file that does not ``json.loads()`` into an OBJECT is
classified ``corrupt_lines``, never missing, and is excluded from the recoverable count.
Conflict markers are called out by name in the report because they imply a DIFFERENT
action — tell Ryan / delete the branch — than "recover these lines".

Neither guard drops information: excluded lines remain visible in their own report
section, and a branch with any excluded category is never reported as "fully contained +
verified / safe to delete" (`fully_verified` is False).

**A filename whitelist is a RECALL decision, not only a safety one (widened 2026-07-27,
same day, after the first draft's hole was caught).** The first cut of the Class-A guard
whitelisted exactly ``dt=<date>.jsonl`` — and that silently went BLIND to a shape that
genuinely exists in committed tape: the partition-directory day,
``tape/sports_pairs/dt=2026-07-02/pass-20260702T231651Z.jsonl``, where a day is a
DIRECTORY holding one JSONL file per pass. A stranded, well-formed line in such a file
came back ``contained=True``/``missing={}``, routed into ``not_line_recoverable`` — the
exact blindness the guard was written to avoid introducing. Every narrowing of this
whitelist must therefore be validated against the ACTUAL repo,
``git ls-tree -r HEAD tape``, shape by shape, and every shape it still excludes must
carry a reason that is TRUE OF THAT SHAPE — the first draft's blanket "prose docs,
manifests, raw JSON blobs" was factually wrong for a per-pass capture file, and a wrong
reason is how a recall hole hides in plain sight. Enumerate, never guess.

The whitelist validated against ``git ls-tree -r HEAD tape`` (13,656 blobs, 2026-07-27)
is `is_recoverable_capture_file`. Every distinct shape present, and its verdict:

  RECOVERABLE (append-only, unique per-line capture identity):
    * ``tape/<family>/dt=<date>.jsonl`` (199) — the canonical day-file.
    * ``tape/<family>/meta/dt=<date>.jsonl`` (10) — nested day-file, matched on filename
      so directory depth never excludes it.
    * ``tape/<family>/dt=<date>/pass-<ts>.jsonl`` (1) — partition-directory day, one
      JSONL per pass; matched as "a ``.jsonl`` whose parent directory is ``dt=<date>``".
    * ``tape/<family>/_manifest.jsonl`` (2) — despite the name this is NOT a rewritten
      index: `collection/capture_orderbooks.py` opens it in APPEND mode ("a", line 205)
      and each line is a full per-capture record (`capture_id`, `raw_sha256`,
      `signature`). Excluding it as a "manifest" would have been a second recall hole
      justified by a false reason.

  EXCLUDED, each with its own accurate reason (see the ``NOT_RECOVERABLE_*`` constants):
    * ``dt=<date>/capture-<ts>/<market>.raw.json`` (13,419) — a whole-document raw API
      blob written once per capture, not a line-oriented file.
    * ``tape/<family>/<name>.json`` (6: q2x settlement caches, sports_clv_s7/summary)
      — single JSON document, regenerated wholesale.
    * probe/analysis ``.jsonl`` caches (16: ``q42_hl_funding_cache/hl_funding_*.jsonl``
      ×13 — count them, not the 14 an earlier hand-tally claimed —
      ``seed5_funding_cache/okx_funding_20260717.jsonl``, ``sports_clv_s7/trades.jsonl``,
      ``sports_history_s7/worldcup2026.jsonl``).
    * ``tape/*.md`` (2) — edited prose (Class A above).
    * ``tape/sports_history_s7/*.xlsx`` (1) — binary workbook.
    * ``tape/ws_depth/dt=<date>.jsonl.gz`` (0 in HEAD; designed Q47 family) — gzip bytes.

**Judgment call, made explicit: the probe/analysis ``.jsonl`` caches stay EXCLUDED.**
They are honest JSONL and line-set containment would be *computable* over them, but they
are not append-only capture files, and at least one is provably regenerated wholesale:
`scripts/sports_clv_s7.py` writes ``trades.jsonl`` with ``open(out_path, "w")`` —
TRUNCATE — so a re-run with a corrected fair-value model rewrites every row, and every
rewritten row would read as "genuinely missing from HEAD" and be union-appended into a
duplicate, contradictory ledger. That is the Class-A prose failure with a ``.jsonl``
extension. Since a shape whitelist cannot tell a truncate-rewritten cache from an
appended one, the whole probe-cache shape is reported for human review instead. None of
today's 199 ``tape/*`` branches touch any of these files, so this costs no CURRENT
information — it is a documented, latent limit, not a silent one, and the honest
statement is "not verified append-only", not "not recoverable in principle".

Measured effect of the widening on the real repo (199 remote ``tape/*`` branches,
``--base-ref HEAD`` at 3c0c9ab6, 2026-07-27): headline UNCHANGED at 1 branch /
1798 recoverable line(s) — byte-identical missing-lines section before and after — so the
widening invented nothing. What changed is coverage: 17 branch-touches of
``_manifest.jsonl`` moved OUT of ``not_line_recoverable`` and were actually checked
(8 × ``crypto_hourly/_manifest.jsonl`` line-checked, fully contained; 9 ×
``sports_pairs/_manifest.jsonl`` correctly falling to the 2MB size guard at 2.6-5.0MB
rather than being mis-labelled). The one branch with genuinely missing lines,
``tape/hourly-20260727T0356Z``, is a fresh 04:03Z hourly push whose 8 files are all flat /
nested ``dt=2026-07-27.jsonl`` day-files — detected identically by the pre-widening code,
i.e. real newly-stranded tape, not a guard artefact.

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
from typing import Callable, Dict, List, Optional, Tuple

CANONICAL_NAME_RE = re.compile(r"^tape/hourly-[0-9]{8}T[0-9]{4}Z$")

# Append-only tape day-file shape, matched on the FILENAME only — `tape/weather_books/
# meta/dt=2026-07-18.jsonl` is a real nested day-file, so a fixed directory depth would
# wrongly exclude it (see module docstring, Class A).
DAY_FILE_RE = re.compile(r"^dt=[0-9]{4}-[0-9]{2}-[0-9]{2}\.jsonl$")
GZ_DAY_FILE_RE = re.compile(r"^dt=[0-9]{4}-[0-9]{2}-[0-9]{2}\.jsonl\.gz$")
# A "day" that is a DIRECTORY of per-pass JSONL files rather than a single file — real and
# committed: tape/sports_pairs/dt=2026-07-02/pass-20260702T231651Z.jsonl. Matched as
# "*.jsonl whose PARENT directory is dt=<date>", so any per-pass filename qualifies, while
# the deeper dt=<date>/capture-<ts>/ raw-blob level does not.
DT_PARTITION_DIR_RE = re.compile(r"^dt=[0-9]{4}-[0-9]{2}-[0-9]{2}$")
# Written in APPEND mode by collection/capture_orderbooks.py (line 205), one full
# per-capture record per line — an append-only capture file, not a rewritten index.
APPEND_ONLY_MANIFEST_NAME = "_manifest.jsonl"

BINARY_SUFFIXES = (".xlsx", ".xls", ".zip", ".parquet", ".db", ".sqlite", ".png", ".pdf")

NOT_RECOVERABLE_GZIP = ("gzipped day-file (tape/ws_depth/dt=*.jsonl.gz, the Q47 family): "
                        "a line-set check over gzip bytes is meaningless")
NOT_RECOVERABLE_RAW_BLOB = ("raw per-market capture blob (dt=<date>/capture-<ts>/*.raw.json): "
                            "one whole JSON document written once per capture, not a "
                            "line-oriented file — 'lines' here are pretty-printer artifacts, "
                            "not observations")
NOT_RECOVERABLE_JSON_DOC = ("single JSON document (e.g. tape/q26_settlement_cache/"
                            "settlement.json, tape/sports_clv_s7/summary.json): regenerated "
                            "wholesale, so a differing line is a re-derivation, not stranded "
                            "tape")
NOT_RECOVERABLE_PROSE = ("prose/markdown document (e.g. tape/cloud-env-check.md): edited in "
                         "place, so superseded wording looks 'missing' forever and appending "
                         "it duplicates and corrupts the doc")
NOT_RECOVERABLE_BINARY = ("binary artifact (e.g. tape/sports_history_s7/*.xlsx source "
                          "workbook): not text, so a line-set check is meaningless")
NOT_RECOVERABLE_PROBE_CACHE = ("probe/analysis .jsonl cache, NOT a verified append-only "
                               "capture file (q42_hl_funding_cache/*, seed5_funding_cache/*, "
                               "sports_clv_s7/trades.jsonl, sports_history_s7/worldcup2026."
                               "jsonl): scripts/sports_clv_s7.py rewrites trades.jsonl with "
                               "open(...,'w'), so a re-run's corrected rows would read as "
                               "'missing' — human review, never auto-append (module docstring)")
NOT_RECOVERABLE_OTHER = ("not a recognised append-only tape capture file (dt=<date>.jsonl, "
                         "dt=<date>/*.jsonl, or _manifest.jsonl): line-set containment is "
                         "only a valid recovery test for append-only files with unique "
                         "per-line capture identity")

CONFLICT_MARKER_PREFIXES = ("<<<<<<<", "=======", ">>>>>>>")

GitRunner = Callable[..., str]


def is_recoverable_capture_file(full_path: str) -> Tuple[bool, Optional[str]]:
    """`(eligible, reason_if_not)` for a path under `tape/`.

    Eligible = an APPEND-ONLY capture file with unique per-line capture identity, which is
    the only thing line-set containment is a valid recovery test for. Three shapes qualify,
    all validated against `git ls-tree -r HEAD tape` (module docstring): `dt=<date>.jsonl`
    at any depth, any `*.jsonl` inside a `dt=<date>/` partition directory, and
    `_manifest.jsonl`. Everything else is ineligible and gets a reason accurate FOR ITS OWN
    SHAPE — a blanket reason is how the partition-directory recall hole hid in the first
    draft of this guard. Ineligible paths are surfaced for human review, never counted as
    recoverable tape."""
    parts = full_path.split("/")
    name = parts[-1]
    parent = parts[-2] if len(parts) >= 2 else ""

    if name == APPEND_ONLY_MANIFEST_NAME:
        return True, None
    if DAY_FILE_RE.match(name):
        return True, None
    if GZ_DAY_FILE_RE.match(name):
        return False, NOT_RECOVERABLE_GZIP
    if name.endswith(".jsonl") and DT_PARTITION_DIR_RE.match(parent):
        return True, None
    if name.endswith(".raw.json"):
        return False, NOT_RECOVERABLE_RAW_BLOB
    if name.endswith(".json"):
        return False, NOT_RECOVERABLE_JSON_DOC
    if name.endswith(".md"):
        return False, NOT_RECOVERABLE_PROSE
    if name.endswith(BINARY_SUFFIXES):
        return False, NOT_RECOVERABLE_BINARY
    if name.endswith(".jsonl"):
        return False, NOT_RECOVERABLE_PROBE_CACHE
    return False, NOT_RECOVERABLE_OTHER


def is_conflict_marker(line: str) -> bool:
    """True for a committed git merge-conflict marker line (`<<<<<<<`/`=======`/`>>>>>>>`)."""
    return line.startswith(CONFLICT_MARKER_PREFIXES)


def is_tape_object_line(line: str) -> bool:
    """True when `line` parses as a JSON OBJECT — the only shape a tape observation takes.

    A bare scalar/array that happens to be valid JSON is NOT tape either; anything failing
    this is corruption (conflict markers, truncated writes), never a recoverable line."""
    try:
        return isinstance(json.loads(line), dict)
    except (ValueError, TypeError):
        return False


def truncate_line(line: str, limit: int = 120) -> str:
    """Short, single-line display form of a corrupt line for the report."""
    text = repr(line)
    return text if len(text) <= limit else text[: limit - 3] + "..."


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


@dataclass
class ContainmentResult:
    """Per-file outcome of a branch's line-set check. Every category is reported; a line
    is never silently dropped from all four."""

    missing: Dict[str, int] = field(default_factory=dict)  # file -> genuinely-absent lines
    skipped: Dict[str, int] = field(default_factory=dict)  # file -> byte size (size guard)
    # file -> reason: paths ineligible for line-set recovery (prose, raw blobs, probe
    # caches, gzip, ...) — each carries the reason accurate for ITS shape
    not_line_recoverable: Dict[str, str] = field(default_factory=dict)
    # file -> truncated display of each non-JSON-object candidate line
    corrupt_lines: Dict[str, List[str]] = field(default_factory=dict)
    # file -> count of corrupt lines that are git merge-conflict markers specifically
    conflict_marker_files: Dict[str, int] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        """True only when NOTHING was excluded and nothing is missing — i.e. every file
        the branch touches was fully line-checked and fully contained."""
        return not (self.missing or self.skipped or self.not_line_recoverable
                    or self.corrupt_lines)


def per_file_containment(branch_rev: str, base_ref: str, path: str,
                          run_git: GitRunner = default_git_runner,
                          cwd: Optional[str] = None,
                          head_line_cache: Optional[Dict[str, frozenset]] = None,
                          max_file_bytes: Optional[int] = DEFAULT_MAX_FILE_BYTES,
                          base_tree: Optional[str] = None,
                          branch_tree: Optional[str] = None,
                          ) -> ContainmentResult:
    """For every file that DIFFERS between `branch_rev` and `base_ref` under `path`
    (via `diff_changed_files` — never full tree enumeration, see that function's
    docstring for why), count lines NOT present (line-level set membership, matching
    LOOP-QUEUE.md step 0b's own union-append/dedupe method) in `base_ref`'s current
    version of that same file. Files IDENTICAL between the two trees are never even
    read — the diff already proves every line in them matches.

    Returns a `ContainmentResult` whose four categories are mutually exclusive per line:
      - `missing`: {file: missing_count} for files with >=1 genuinely-absent, well-formed
        JSON-object line. THIS is the only recoverable category — the only thing step 0b
        may union-append.
      - `skipped`: {file: byte_size} for files whose branch-side blob exceeds
        `max_file_bytes` — SKIPPED, not read at all, and never silently folded into
        "contained": a branch with skipped files and an empty `missing` dict means "no
        problem found in what was checked", not "proven fully contained". Pass
        `max_file_bytes=None` to disable the guard and check every file regardless of size.
      - `not_line_recoverable`: {file: reason} for paths that are not append-only
        capture files (prose docs, raw `.raw.json` blobs, probe caches, gzipped families
        — see `is_recoverable_capture_file` for the per-shape reason). Reported for human
        review, NEVER auto-appended (module docstring, Class A).
      - `corrupt_lines`: {file: [truncated line, ...]} for candidate "missing" lines that
        do not parse as a JSON object — corruption, not tape (Class B). `conflict_marker_files`
        additionally counts those that are git merge-conflict markers, which imply a
        different action (unresolved merge committed into tape) than line recovery.

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
    result = ContainmentResult()
    if branch_tree is None:
        return result  # nothing to compare — caller handles the "no tree" case
    if base_tree is None:
        # No base tree to diff against at all (rare: base_ref itself lacks `path`) — fall
        # back to full enumeration, the only case where that cost is unavoidable.
        changed_files = list_tree_files(branch_rev, path, run_git, cwd)
    else:
        changed_files = diff_changed_files(base_tree, branch_tree, run_git, cwd)
    for rel_file in changed_files:
        full_path = f"{path}/{rel_file}"
        eligible, reason = is_recoverable_capture_file(full_path)
        if not eligible:
            # Checked BEFORE the size guard: an ineligible path's size is irrelevant, and
            # a gzipped blob must never even be read as text.
            result.not_line_recoverable[full_path] = reason or NOT_RECOVERABLE_OTHER
            continue
        if max_file_bytes is not None:
            size = blob_size(branch_rev, full_path, run_git, cwd)
            if size is not None and size > max_file_bytes:
                result.skipped[full_path] = size
                continue
        if full_path not in head_line_cache:
            base_lines = read_blob_lines(base_ref, full_path, run_git, cwd)
            head_line_cache[full_path] = frozenset(base_lines) if base_lines else frozenset()
        base_set = head_line_cache[full_path]
        branch_lines = read_blob_lines(branch_rev, full_path, run_git, cwd) or []
        missing_count = 0
        for line in branch_lines:
            if line in base_set:
                continue
            if not is_tape_object_line(line):
                result.corrupt_lines.setdefault(full_path, []).append(truncate_line(line))
                if is_conflict_marker(line):
                    result.conflict_marker_files[full_path] = (
                        result.conflict_marker_files.get(full_path, 0) + 1)
                continue
            missing_count += 1
        if missing_count:
            result.missing[full_path] = missing_count
    return result


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
    # file -> reason (non-capture-file paths: prose, raw blobs, probe caches, gzip).
    # Human review only.
    not_line_recoverable: Dict[str, str] = field(default_factory=dict)
    corrupt_files: Dict[str, List[str]] = field(default_factory=dict)  # file -> truncated lines
    conflict_marker_files: Dict[str, int] = field(default_factory=dict)  # file -> marker count

    @property
    def fully_verified(self) -> bool:
        """False when ANY file went unchecked or produced an un-appendable finding: the size
        guard skipped it, it is not a line-recoverable day-file, or it contains corrupt lines.
        A `contained=True` result is then "no problem found in what WAS line-checked", not a
        proof of full containment, and the branch must not be called safe to delete on that
        basis. Always True when `contained` is None (no tape/ tree — nothing to check)."""
        return not (self.skipped_files or self.not_line_recoverable or self.corrupt_files)

    @property
    def has_conflict_markers(self) -> bool:
        """True when this branch has an UNRESOLVED GIT MERGE committed into tape — a
        different action (tell Ryan / delete the branch) than "recover these lines"."""
        return bool(self.conflict_marker_files)


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
    res = per_file_containment(sha, base_ref, path, run_git, cwd,
                                head_line_cache, max_file_bytes,
                                base_tree=base_tree, branch_tree=branch_tree)
    # `contained` reflects ONLY genuinely-recoverable lines. Excluded categories never
    # inflate it — they lower `fully_verified` and print in their own report sections.
    return BranchTriage(name=name, sha=sha, malformed=malformed, fetched=True,
                         contained=(len(res.missing) == 0), commit_date=cdate,
                         missing_files=res.missing, skipped_files=res.skipped,
                         not_line_recoverable=res.not_line_recoverable,
                         corrupt_files=res.corrupt_lines,
                         conflict_marker_files=res.conflict_marker_files)


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
    not_recoverable = [t for t in triage if t.not_line_recoverable]
    corrupt = [t for t in triage if t.corrupt_files]
    conflicted = [t for t in triage if t.has_conflict_markers]
    total_missing_lines = sum(sum(t.missing_files.values()) for t in has_missing)

    lines = [
        f"tape-branch sweep: {total} branch(es) checked against {base_ref}",
        f"  {len(malformed)} malformed name(s) (fail {CANONICAL_NAME_RE.pattern})",
        f"  {len(contained_verified)} fully contained + verified (every line checked and "
        f"present in {base_ref}; safe to delete once its PR, if any, merged)",
        f"  {len(contained_unverified)} no problem found but NOT FULLY VERIFIED (>=1 file "
        "unchecked: size guard, non-day-file path, or corrupt lines — see the lists below; "
        "do not delete on this alone)",
        f"  {len(has_missing)} carry line(s) genuinely MISSING from {base_ref} "
        f"({total_missing_lines} recoverable line(s) total; per-file line-set check over "
        "append-only capture files only (dt=<date>.jsonl, dt=<date>/*.jsonl, "
        "_manifest.jsonl), not a raw tree-hash mismatch — see module "
        "docstring)",
        f"  {len(not_recoverable)} touch non-day-file paths, NOT line-recoverable (reported "
        "for human review, NEVER auto-appended; excluded from the MISSING count)",
        f"  {len(corrupt)} carry CORRUPT (non-JSON-object) lines in day-files — corruption, "
        f"not tape; excluded from the MISSING count ({len(conflicted)} of them are "
        "unresolved git merge conflicts committed into tape)",
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
    if not_recoverable:
        # Grouped by path: on the real repo 155 branches touch the same two prose docs, and
        # a per-branch-per-path listing is 300+ near-identical lines. Grouping keeps EVERY
        # branch visible (each is named under its path) while stating the reason once.
        by_path: Dict[Tuple[str, str], List[BranchTriage]] = {}
        for t in not_recoverable:
            for f, reason in t.not_line_recoverable.items():
                by_path.setdefault((f, reason), []).append(t)
        lines.append("  non-day-file paths (NOT line-recoverable — human review only, NEVER "
                      "auto-append these into tape):")
        for (f, reason), branches_for_path in sorted(by_path.items()):
            lines.append(f"    - {f} — {reason}")
            lines.append(f"        touched by {len(branches_for_path)} branch(es): "
                          + ", ".join(f"{t.name} ({t.sha[:12]})"
                                      for t in sorted(branches_for_path, key=lambda b: b.name)))
    if corrupt:
        lines.append("  CORRUPT lines found in append-only capture files (NOT recoverable "
                      "tape, never append):")
        for t in corrupt:
            for f, samples in sorted(t.corrupt_files.items()):
                marker_count = t.conflict_marker_files.get(f, 0)
                note = (f" [{marker_count} GIT CONFLICT MARKER line(s): this branch has an "
                        "UNRESOLVED MERGE committed into tape — tell Ryan / delete the branch; "
                        "this is NOT a line-recovery job]") if marker_count else ""
                lines.append(f"    - {t.name} ({t.sha[:12]}): {f}: "
                              f"{len(samples)} corrupt line(s){note}")
                for sample in samples[:5]:
                    lines.append(f"        {sample}")
                if len(samples) > 5:
                    lines.append(f"        ... and {len(samples) - 5} more")
    if any(t.skipped_files for t in triage):
        lines.append("  branches with skipped (oversized) files — no proof of containment:")
        for t in triage:
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
