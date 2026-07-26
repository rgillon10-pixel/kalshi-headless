# Stranded-tape recovery: `tape/hourly-20260725T2157Z` + false-positive triage (2026-07-26)

Idle-run milestone (step 0b, elevated beyond "sweep only" by a genuine recovery — the
2026-07-12 protocol amendment explicitly forbids ending an idle run on a sweep alone, and
this run's sweep surfaced real missing data, unlike the immediately preceding several runs'
clean sweeps).

## What happened

A fresh, unfiltered `scripts/tape_branch_sweep.py` run (195 branches, full fetch, no
`--limit` truncation) found **14 branches carrying lines reported missing from `HEAD`**,
one more than the previous run's clean 0-result sweep 3 hours earlier
(`kb/00-LOG.md` 2026-07-26 ~00:2x entry). Each candidate was hand-verified before touching
anything — the tool's own docstring warns a raw "missing lines" count is not proof of
genuine stranded data (see the 07-25 sweep's own false-positive rate: 13/13 "missing" hits
that run were benign). This run's 14 decomposed the same way:

**13 false positives, correctly left untouched:**
- 8 branches (07-10, 07-16) report `tape/cloud-env-check.md` missing 2 lines. This is a
  **prose doc**, not append-only JSONL — `git diff` against the oldest branch shows `HEAD`'s
  current version is a *deliberately condensed* rewrite (verbose per-check history folded
  into a shorter summary), not an accidental drop. Re-appending the old branch's fuller
  text would undo an intentional edit. Left alone.
- 5 branches (07-22, 07-23) report `tape/anomalies/dt=2026-07-18.jsonl` and
  `tape/econ_prints/dt=2026-07-18.jsonl` missing 3 lines each. Those "missing" lines are
  literal **git conflict markers** (`<<<<<<< HEAD` / `=======` / `>>>>>>> 58145d7 ...`) —
  the exact corruption `kb/00-LOG.md`'s 2026-07-23 entry already found and repaired (L142,
  now a GATING invariant). The stranded branches still carry the pre-repair corrupted
  lines; `HEAD` correctly excludes them. Re-appending would reintroduce already-fixed
  corruption. Left alone.

**1 genuine recovery, applied:**
- `tape/hourly-20260725T2157Z` (commit `13186532111a`, 2026-07-25T21:57Z, a `hourly_pass`
  run that fell back off `main` per the known push-permission-boundary pattern) carries
  **235 lines genuinely absent from `HEAD`**, all valid JSON, none touching a file `HEAD`
  doesn't already have — a pure gap-fill, not a new family:
  - `tape/crypto_hourly/dt=2026-07-25.jsonl`: +2 lines (one BTC + one ETH ladder snapshot,
    `capture_id=20260725T215522Z`, `real_ask`)
  - `tape/polymarket_macro_pairs/dt=2026-07-25.jsonl`: +15 lines
  - `tape/sports_pairs/dt=2026-07-25.jsonl`: +218 lines

Union-appended (pure append, verified byte-for-byte: each file's pre-recovery content is
an exact prefix of its post-recovery content — no line touched, reordered, or deduped
away) into this run's commit. Every appended line parses as valid JSON (0 malformed across
all 235). The branch is old enough (>30min, per step 0b's own guard) to be safely swept;
it is not deleted here — step 0b defers deletion until the PR carrying these lines merges.

## Why this run's sweep found something the prior run's didn't

Not investigated in depth (out of scope for a data-recovery milestone) — most likely
explanation: `tape/hourly-20260725T2157Z` postdates the *branch listing* the 00:2x run's
own sweep operated over (that run reported "487-branch remote backlog"; this run's
`git ls-remote` + fetch saw 195 `tape/hourly-*`/`tape/burst-*` refs specifically, a
different count that includes this branch). No evidence of a sweep-tool regression —
`scripts/tape_branch_sweep.py`'s own logic is unchanged since 07-25's audit.

## Gates

`pytest -q`: 1990 collected, **2 pre-existing failures**
(`tests/test_q42_funding_estimate_path_inference.py::test_tape_leave_one_out_67_drops_decomposes_as_7_18_42`,
`::test_tape_random_same_size_subsets_reproduce_the_dense_cuts_hard_gap`) — both
`@_real_tape` acceptance tests pinned to a `perp_tape` window count (`n_windows == 42`)
that has since grown to 44 as more forward tape has committed since Q42's 2026-07-24
snapshot; a real-tape-drift flake, not a regression. Verified **byte-identical on base
`main`** via `git stash` (same 2 tests fail identically with this run's tape-recovery diff
reverted) — unrelated to this change. 1988/1990 pass otherwise.
`python scripts/invariants.py --full`: exit 0, only the same pre-existing non-gating
advisory classes as every recent run (dir-shaped days, GC-dispatch, daily-cadence gaps,
VPS collector dead [now 81.9h, worsening, Ryan-side], raw-fromisoformat backlog,
recovery-dwell, settlement-binary). No new advisory introduced by this diff.

No strategy claim, no registry change, no P&L/bootstrap CI — pure data-recovery +
false-positive triage, same posture as the 07-23/07-25 stranded-tape recoveries
(L109/L118/L142 precedent). Two-agent verdict rule N/A.
