# Stranded-tape recovery (`tape/hourly-20260726T2204Z`, 134 lines) + VPS collector still dead at 102.9h (2026-07-27)

Idle-run milestone: step 0b's sweep found a genuine recovery (elevated beyond "sweep only" per
the 2026-07-12 protocol amendment), and a fresh live re-check of the already-known VPS-death
data-quality issue (idle-run policy (c)) updates its duration and confirms no self-healing has
occurred.

## Part 1 — Stranded-tape recovery (step 0b)

A fresh, unfiltered `scripts/tape_branch_sweep.py` run (198 branches, full fetch) found **14
branches carrying lines reported missing from `HEAD`**. Each was hand-verified before touching
anything (per the tool's own docstring warning and the 07-25/07-26 precedent of high
false-positive rates on this exact check):

**13 false positives, correctly left untouched** — the same two recurring artifact classes as
the last two sweeps:
- 8 branches report `tape/cloud-env-check.md` missing 2 lines — a **prose doc**, not append-only
  JSONL; `HEAD`'s current text is a deliberately condensed rewrite, not an accidental drop.
- 5 branches (07-22/07-23-dated) report `tape/anomalies/dt=2026-07-18.jsonl` /
  `tape/econ_prints/dt=2026-07-18.jsonl` missing 3 lines each — the "missing" lines are literal
  **git conflict markers** (`<<<<<<< HEAD` / `=======` / `>>>>>>> ...`), the exact corruption
  L142 already found and repaired. `HEAD` correctly excludes them.

**1 genuine recovery, applied:**
- `tape/hourly-20260726T2204Z` (commit `ad9e7a36a8ec`, 2026-07-26T22:04:10Z, an `hourly_pass`
  run that fell back off `main` per the known push-permission-boundary pattern) carries **134
  lines genuinely absent from `HEAD`**, all valid JSON, all `dt=2026-07-26`, none touching a
  file `HEAD` doesn't already have:
  - `tape/crypto_hourly/dt=2026-07-26.jsonl`: +2 lines
  - `tape/hyperliquid_funding/dt=2026-07-26.jsonl`: +2 lines
  - `tape/perp_tape/dt=2026-07-26.jsonl`: +17 lines
  - `tape/polymarket_macro_pairs/dt=2026-07-26.jsonl`: +15 lines
  - `tape/sports_pairs/dt=2026-07-26.jsonl`: +98 lines

Union-appended (pure append: each file's pre-recovery content is an exact prefix of its
post-recovery content — no line touched, reordered, or deduped away). Every appended line
parses as valid JSON (0 malformed across all 134). The branch is not deleted here — step 0b
defers deletion until the PR carrying these lines merges.

## Part 2 — VPS `:23` collector leg: still dead, now 102.9h silent (idle-run policy (c))

The 2026-07-25 finding (`findings/2026-07-25-vps-collector-second-death-and-cloud-slot-attrition.md`)
documented the VPS `:23` leg dying a second time, last committed capture
`2026-07-22T17:29:49.498223+00:00`, silent 61.7h as of that run. This run independently
re-derived the same measurement live against current committed tape (not trusting the prior
finding as still-current, per the same discipline as the 07-21/07-22/07-25 re-checks):

- Newest VPS-signature (`captured_at` minute-of-hour 20-29) capture across
  `crypto_hourly`/`orderbook_depth`/`sports_pairs`/`polymarket_macro_pairs` is still
  `2026-07-22T17:24:00.000505+00:00` (`orderbook_depth`) — **unchanged** since the 07-25
  finding. Zero new VPS-signature lines have landed in the intervening ~41h.
- `python3 scripts/invariants.py --full`'s non-gating collector-health advisory independently
  confirms: `dead leg: vps`, `silent for: 103.1h (threshold: 24h)`, `still alive: cloud, other`.
- `python3 scripts/tape_gap_monitor.py --no-notify` shows the same pattern across all four
  `hourly-dual` families: `vps_dead: 0 passes in window, cloud collector still producing`,
  `capture_ratio` 0.06-0.17 (well under the 0.8 threshold) — matching a cloud-only cadence
  (~8 passes/day at the live `53 */3 * * *` cron) with zero VPS contribution, not a *new*
  cloud degradation.
- `weather_actuals` (107.1h stale) and `settlement_ledger` (109.7h stale) remain frozen for the
  same already-diagnosed reason (VPS is their sole writer at the relevant UTC hour).

**Conclusion: no self-healing.** The outage that was 61.7h on 2026-07-25T07:12Z is now 102.9h
(orderbook_depth-measured) / 103.1h (invariants-measured) as of this run
(2026-07-27T00:15Z) — an unbroken continuation, not a new event. This is Ryan/VPS-side only (a
cloud sandbox cannot restart the VPS cron); flagged again per L156/L157/L159's non-gating
advisory discipline. No code change this run — the existing advisory infrastructure (L156/L159)
already surfaces this correctly; the value here is a fresh, independently-reproduced duration
figure and confirmation that the affected gates (Q36 settlement-basis, weather microstructure)
remain frozen for the same reason as last reported.

## Gates

`pytest -q`: **2065 collected** (`--collect-only -q` summed across 88 files, taken after this
diff's last edit — pure tape/paper-ledger append, no source touched), **2 pre-existing
failures** (`tests/test_q42_funding_estimate_path_inference.py::test_tape_leave_one_out_67_drops_decomposes_as_7_18_42`,
`::test_tape_random_same_size_subsets_reproduce_the_dense_cuts_hard_gap`) — both `@_real_tape`
acceptance tests pinned to a `perp_tape` window count that has since grown as more forward tape
committed; a real-tape-drift flake. Verified **byte-identical on base `main`** via `git stash`
(same 2 tests fail identically with this run's tape-recovery diff reverted, same `p11` drift
pattern) — unrelated to this change.
`python scripts/invariants.py --full`: exit 0, only pre-existing non-gating advisory classes
(dir-shaped days, GC-dispatch, daily-cadence gaps, VPS collector dead [now 103.1h], hollow
crypto ladders, raw-fromisoformat backlog, recovery-dwell, settlement-binary). No new advisory
class introduced by this diff.

No strategy claim, no registry change, no P&L/bootstrap CI — pure data-recovery + a
data-quality status re-check, same posture as the 07-23/07-25/07-26 stranded-tape recoveries and
the 07-21/07-22/07-25 VPS re-checks. Two-agent verdict rule N/A.
