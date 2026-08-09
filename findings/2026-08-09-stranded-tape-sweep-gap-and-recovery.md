# 2026-08-09 — the standing tape-sweep only matched two of the three fallback branch shapes; recovery + VPS-leg outage found underneath it

## Summary

LOOP-QUEUE.md step 0b's stranded-tape sweep, and `scripts/invariants.py::_git_tape_refs`,
both probe only `refs/*/tape/hourly-*` and (since 2026-07-10) `refs/*/tape/burst-*`. The
kalshi-collector Routine's trigger config sets `outcomes.git_repository.git_info.branches:
["claude/determined-goodall"]` — a CCR session-outcome branch (auto-suffixed per session,
e.g. `claude/determined-goodall-5llz9l`) that the collector's own git fallback lands on
whenever BOTH its push to `main` and its manual `tape/hourly-<ts>Z` fallback fail. Neither the
protocol prose nor the invariants probe ever looked at that branch family, so tape stranded
there accumulated invisibly — every prior run's "sweep found zero new lines" was true of the
branches it checked and silent about the ones it didn't.

## What this run did

1. Enumerated every remote branch (`git for-each-ref --sort=-committerdate refs/remotes/origin/`)
   instead of trusting the name-pattern probe, to find the single most recent commit on the
   entire remote. It was `claude/determined-goodall-5llz9l`, `tape: hourly pass
   2026-08-08T16:05:00Z` — newer than anything reachable from `main` (whose newest direct tape
   landing was `2026-08-08T01:02:45Z`) or from any `tape/hourly-*`/`tape/burst-*` branch (newest:
   `2026-08-07T21:55:56Z`).
2. Restricted to branches matching the three known collector-fallback shapes
   (`tape/hourly-*`, `tape/burst-*`, `claude/determined-goodall-*`) with a SMALL number of
   commits ahead of `main` (<=3) — the large-count branches (600+ commits ahead) are old
   research/idle-run PR branches never deleted post-squash-merge; raw commit-ancestry counts
   overstate their "stranded" status because a squash merge does not make the pre-squash
   commits ancestors of the squash commit. Content is the correct test, not ancestry — see below.
3. For each of the 20 candidate commits found this way, diffed its own added lines (via
   `git diff-tree`/`git show`) against `main`'s CURRENT content for the same file (not against
   the commit's own parent) and kept only lines genuinely absent from `main`. 16 of 20 were
   already fully subsumed (duplicate pushes that also landed via `main` directly, or
   previously recovered by earlier sweep PRs, e.g. PR #317's `hourly-20260807T1257Z` recovery).
4. **4 commits carried genuinely missing data — 7,114 lines never committed anywhere reachable
   from `main` before this run:**

   | commit | when | families | lines |
   |---|---|---|---|
   | `8aff5571` | 2026-08-06 04:12 | weather_books (+meta) | 591 |
   | `1b766e2a` | 2026-08-07 18:56 | crypto_hourly, polymarket_macro_pairs, sports_pairs | 627 |
   | `50fcb786` | 2026-08-07 22:11 | hyperliquid_funding, orderbook_depth, perp_tape, weather_books | 2,561 |
   | `02ff07ed` | 2026-08-08 16:05 | crypto_hourly, hyperliquid_funding, orderbook_depth, perp_tape, polymarket_macro_pairs, sports_pairs, weather_books | 3,335 |

   Union-appended into the corresponding `tape/<family>/dt=*.jsonl` files, dedup by exact
   line content (append-only, unique capture identity per line, per CLAUDE.md's Trust
   defaults). Every line re-validated as parseable JSON before being written; no existing
   line touched, reordered, or removed.
5. **Root-caused and closed the detection gap**: `scripts/invariants.py::_git_tape_refs` now
   also probes `refs/*/tape/burst-*` (previously undocumented in that function though already
   swept by protocol prose) and `refs/*/claude/determined-goodall-*`. `stranded_tape_warning`'s
   message text updated to stop implying `tape/hourly-*` is the only shape and to point at a
   CONTENT-level diff rather than a name-pattern match (this run's own recovery would have been
   invisible to a second name-pattern-only sweep, since 3 of the 4 real commits are `tape/
   hourly-*`-named — the gap was never in that pattern, it was in never checking
   `claude/determined-goodall-*` at all). New tests:
   `tests/test_invariants.py::test_git_tape_refs_probes_determined_goodall_pattern`,
   `::test_stranded_tape_warning_message_content_determined_goodall`.

## What the recovered data revealed: a real collector-health finding, not just bookkeeping

`scripts/invariants.py --full`'s existing (pre-built, L117/L129/L269-273) COLLECTOR HEALTH
ADVISORY reads committed tape only, so it was blind to the same stranded data. Re-run AFTER
the recovery above, it separates the two scheduled legs cleanly for the first time in days:

- **`vps` leg: last seen 2026-08-06T07:23:15Z — 65.1 hours of silence** as of this run. This is
  the VPS/local-hosted collector leg CLAUDE.md's execution lane distinguishes from cloud; per
  the tool's own text, "a dead VPS cron cannot be fixed from a cloud run — fix = restart the
  cron on the machine that owns it." This is the run's headline: **Ryan needs to restart the
  VPS collector.**
- **`cloud` leg: last seen 2026-08-08T15:56:05Z — 8.5 hours of silence**, under the 24h
  threshold so not counted as a dead leg, but still stale relative to the 6h "alive" bar.
  Before this run's recovery, the `cloud` leg's newest visible capture (in `main` alone) was
  `2026-08-08T01:02:45Z` — 23.3h old at run time, one bad sample away from tripping the same
  `>=24h silent` bucket the `vps` leg is already in. The two firings after the recovered
  16:05 pass (the kalshi-collector Routine's own `last_fired_at` shows firings at 18:53 and
  21:53 UTC on 2026-08-08) left no discoverable commit anywhere — not on `main`, not on any
  `tape/hourly-*`/`tape/burst-*`/`claude/determined-goodall-*` branch. Two explanations are
  consistent with that and this run could not distinguish them from tape alone: the passes
  captured zero new lines (nothing to commit), or they failed before ever reaching the commit
  step. Not resolved here — flagged for the next run/retro to watch the 00:53 UTC firing.

## Residual (not fully swept, honestly scoped)

The 600+-commits-ahead branches (mostly `research-loop-*`/`idle-run-*`/`edge-hunter/*`
PR-source branches, squash-merged but never deleted) were NOT content-diffed this run — there
are ~350 of them and a full pairwise diff against `main`'s current tape files is a
multi-hour job at this repo's tape size (the `orderbook_depth` family alone is 378MB). Spot
risk is low (these are PR branches whose content was reviewed and squash-merged, not raw
collector fallbacks), but it is unverified, not disproven. A future idle run could scope a
proper batch content-diff (the `find_missing.py`-style approach this run used, generalized)
if branch cleanup ever becomes cheap enough to also delete what it clears.

## Verdict class

DATA-COLLECTION + tooling (non-verdict-class): no registry status flip, no bootstrap CI, no
kill decision. The two-agent verdict rule does not bind. Every appended line carries its
original `price_source_tag` from its source commit (real_ask/broker_truth per family
convention; unchanged from the original capture).
