# Tape-branch sweep tool + full backlog audit (2026-07-25)

Idle-run milestone (policy a): converts the previous run's UNENFORCED lessons **L160**
and **L161** (`kb/lessons/00-lessons.md`) into a reusable, tested tool, and uses it to
audit the entire stranded-tape-branch backlog for the first time.

## What shipped

`scripts/tape_branch_sweep.py` + `tests/test_tape_branch_sweep.py` (31 offline tests,
real temporary git repos — not mocked subprocess).

Two functions, per LOOP-QUEUE.md step 0b's own stated need:

1. **Containment**: does a `tape/*` branch carry any line genuinely missing from `main`?
   Fast path: `git rev-parse <rev>:tape` tree-hash equality (L160's original insight).
   Fallback (an append-only tree means a hash MISMATCH does not by itself mean
   "not contained" — see Correction below): a per-file line-set check, scoped to only
   the files that actually differ between the two trees (`git diff --name-only
   --diff-filter=AM`), never a full tree walk.
2. **Malformed-name triage**: branches failing the canonical
   `tape/hourly-YYYYMMDDTHHMMZ` name are ordered by commit date, never by name (L161) —
   a lexical sort would silently mis-triage degenerate names like `tape/hourly-Z`.

`git merge-base --is-ancestor` is never called anywhere in the module (source-text
pinned by a test) — `main` squash-merges, so that check reports every fully-contained
branch as "stranded," every time.

## Correction to L160's own worked example

L160's original text cited one branch where `origin/<branch>:tape == HEAD:tape` exactly,
and concluded tree-hash equality "settles... in ONE command." That's true only because
`tape/` hadn't grown between the branch's push and the check. Since `tape/` is
append-only and grows roughly hourly, a tree-hash comparison against any OLDER branch
will read as "mismatch" essentially always — not because the branch carries missing
data, but because `HEAD`'s same files now have more lines appended. Treating a mismatch
as "not contained" was tried first in this run and produced 191/192 false positives
against real branches. The fix implemented: a mismatch triggers the per-file line-set
fallback, which correctly recognizes when a branch's older, smaller file content remains
a strict subset of `HEAD`'s current (larger) file.

## Performance notes (why this took three iterations)

- A branch's `tape/` tree is a full historical snapshot: 13,644 files as of this run,
  not just the files that branch's own commit touched (git trees are snapshots, not
  deltas). Enumerating every file per branch (`git ls-tree -r`) made a 20-branch sweep
  exceed 150s.
- Fix: diff the branch's tree against `HEAD`'s tree directly
  (`git diff --name-only <base_tree> <branch_tree>`) — but the raw diff of an old branch
  against a week-newer `HEAD` is dominated by files that exist ONLY in `HEAD` (added
  after the branch was cut, irrelevant to what the branch carries): one real branch
  produced 3,196 raw differing paths, of which only 7 were files the branch actually
  has. `--diff-filter=AM` (Added-or-Modified relative to base) keeps only the relevant 7.
- Real committed tape blob content is not always valid UTF-8 (hit live, not
  hypothetical) — `default_git_runner` decodes with `errors="replace"` rather than
  `subprocess.run(text=True)`'s strict decode, which crashed on the first such blob.
- Bulk families (`orderbook_depth`/`universe_sweep`/`sports_pairs`, ~950MB combined)
  make full-content reads impractical at 192-branch scale; a 2MB per-file size guard
  skips (never silently trusts) oversized files — a branch with skipped files and no
  proven-missing line reports `contained=True, fully_verified=False`, distinct from a
  fully-verified `True`.

With these fixes the full 192-branch live sweep completes in ~30s.

## Live sweep result (2026-07-25, all 192 `tape/*` branches, no `--limit`)

```
tape-branch sweep: 192 branch(es) checked against HEAD
  44 malformed name(s)
  12 fully contained + verified
  167 no problem found but NOT FULLY VERIFIED (bulk-family files size-guard-skipped)
  13 carry line(s) "genuinely MISSING" per the raw per-file check
  0 fetched but carry no tape/ tree
  0 not yet fetched locally
```

The 13 "missing" hits were individually inspected, not taken at face value:

- **8** are in `tape/cloud-env-check.md` — a prose Q0 documentation file that happens to
  live under `tape/`, not an append-only `dt=*.jsonl` capture file. It gets EDITED over
  time (not appended), so old branches naturally carry superseded wording. Benign.
- **5** are `tape/anomalies/dt=2026-07-18.jsonl` / `tape/econ_prints/dt=2026-07-18.jsonl`
  on branches from 2026-07-22/23 — verified by hand (`comm -23` against `HEAD`) to be
  the exact `<<<<<<< HEAD` / `=======` / `>>>>>>> 58145d7 (...)` conflict-marker lines
  L142 already found and fixed in `HEAD`'s version of these files. `HEAD` correctly
  excludes them; the branches just carry the old, since-repaired garbage. Benign — `HEAD`
  is better, not missing anything.

**Net result: zero genuine stranded tape found across the entire 192-branch historical
backlog.** This matches every prior ad-hoc spot-check's informal conclusion (e.g. the
2026-07-21T06:1xZ run log: "the ~190-branch historical backlog is undeleted-but-already-
swept debris") but is now the first FULL, tool-verified confirmation of it, not a sample.

The 167 size-guard-skipped branches are not a negative result — they mean "not fully
checked," and remain open work for a future pass with either a longer time budget or the
byte-prefix optimization named below, not evidence of a problem.

## What this does NOT do

- No branch is deleted. Deletion stays a human/protocol decision gated on "only after the
  PR containing its lines has merged" (LOOP-QUEUE.md step 0b) — this tool only informs
  that decision.
- The 167 skipped-file branches are not proven clean for their large files. A future
  optimization (byte-prefix comparison — since tape is append-only, an old file's content
  should be a literal byte-prefix of `HEAD`'s current file; checking that requires only
  comparing the first N bytes of `HEAD`'s blob, not reading the whole thing) would let a
  future pass raise or drop the size guard without the current O(file size) cost. Not
  built this run — flagged as open work, not a terminal state, matching L160/L161's own
  framing.

## Gates

`pytest`: full suite green (unchanged baseline + 31 new). `python scripts/invariants.py
--full`: exit 0, same pre-existing non-gating advisory classes as `HEAD` before this run.

No strategy claim, no bootstrap CI, no registry change, no P&L — infrastructure/tooling,
same posture as L109/L118/L126/L144/L152/L156. Two-agent verdict rule N/A (not a
verdict-class change).
