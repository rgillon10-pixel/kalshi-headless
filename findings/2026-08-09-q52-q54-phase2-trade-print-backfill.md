# Phase-2 trade-print backfill: 34/328 games committed, plus a GitHub 100MB push rejection

*2026-08-09 · research loop · milestone = continuing
`scripts/q52_q54_trades_backfill_phase1.py`'s bounded, byte-capped pull past its phase-1
stopping point (LOOP-QUEUE.md Q52: "phase 2 is a byte decision, not a discovery") · main
context, no verdict produced (two-agent rule N/A — data-collection class, L287/L288/L290/
L291/L295/L308/L313 precedent)*

**Class: DATA-COLLECTION.** No bootstrap, no CI, no P&L, no fill rate, no edge claim, no
registry flip. S78 stays idea-stage `collect-and-revisit`. Still **0 proven edges.**

## What was pulled

Re-ran the SAME script, SAME committed-tape-only selection (328 games unchanged — no new
`orderbook_depth`/settlement tape landed in the 07-07..07-14 window since phase 1), with
`--cap-mb 50` instead of the phase-1 default of 40. The script re-plans from scratch each
run and re-visits already-covered games first (their pull is idempotent — `collection.
kalshi_trades.run`'s own `trade_id` dedupe wrote 0 new lines for all 17 phase-1 games this
pass), then continues into new games until the declared cap. **Live execution pulled 18 new
games** (119,717 new lines, 68.8 MB) — see "the push rejection" below for why only 17 of
those 18 ended up in committed tape.

| stage | phase-1 | phase-2 live execution | phase-2 committed |
|---|---|---|---|
| games planned | 328 | 328 | 328 |
| games pulled | 17 | +18 | **+17** |
| new lines written | 76,280 | 119,717 | **84,573** |
| MB written (measured) | 43.9 | 68.8 | **48.7** |
| API calls | 105 | 275 | 275 (unchanged — calls already happened) |
| stopped_reason | byte_cap | byte_cap | byte_cap, then one game post-hoc dropped |

Report: `reports/q52_q54_trades_backfill_phase1_phase2.json` (the `manifest` and summary
counts reflect the FINAL committed state, 34/328 games; `post_hoc_adjustment` documents the
one dropped game explicitly rather than silently editing history). Cumulative committed
state: **34/328 games**, all new lines `price_source_tag: broker_truth`, 0 incomplete on the
retained set.

## The push rejection — a real infra blocker, caught before it landed

The first commit (before this finding's numbers were corrected) included all 18 live-pulled
games. `git push` failed outright:

```
remote: error: File tape/kalshi_trades/dt=2026-07-07.jsonl is 104.09 MB; this exceeds
GitHub's file size limit of 100.00 MB
remote: error: GH001: Large files detected.
! [remote rejected]  ...  (pre-receive hook declined)
```

Measured precisely: 109,151,185 bytes (GitHub measures decimal MB; 100.00 MB = 100,000,000
bytes). One game, `KXWCGAME-26JUL07ARGEGY`, contributed 35,144 of that day-file's new lines
(all its own trade prints touch only `dt=2026-07-07`) — it was the last game the round-robin
plan reached before the cap fired, and dropping it exactly undoes that last step, as if the
cap had triggered one game earlier. Dropped by **ticker-prefix match** (every outcome leg —
`KXWCGAME-26JUL07ARGEGY-YES`/`-NO`/etc. — not just the bare game ticker), so no game was ever
partially committed: this preserves the script's own whole-game-atomicity contract (L315,
"a game is either fully pulled or not started, because a half-pulled game would be a
silently biased unit") even though the drop happened post-hoc rather than inside `execute()`.
Post-drop: `dt=2026-07-07.jsonl` is 88,069,420 bytes (88.1 MB), safely under the cap.

**This is a genuine, not-yet-solved scaling problem, not a one-off.** `tape/kalshi_trades/`
day-files aggregate ALL games whose trade day falls on that date; a single heavy game (MLB
and World Cup games each ran 25k-35k prints) can push a day-file arbitrarily close to
GitHub's ceiling regardless of the declared MB cap, because the cap bounds the PASS's total
growth, not any one file's absolute size. The open tape-storage-migration decision doc (PR
#166, "decision doc + verified archiver, no cutover yet") is the standing fix path; until it
lands, any future phase-N backfill into a heavy day should check the target day-file's
resulting size before committing, not just the family-wide cap. Not built here — flagged for
whoever runs phase 3.

## What this does and does not change for S78

Unchanged from phase-1's own read: the toxicity/markout question is gated on training vs.
holdout CELL POPULATION, not raw game count. 34 games is still well short of what a
pre-registered ≤4-cell design (favorite/dog × wide/tight, per the Q21 registration's
mandated tightening) needs on BOTH sides of a disjoint train/holdout split. A coarser
sampling strategy (e.g. per-cell quota rather than byte-budget-until-cap) is the more
efficient next step and is flagged for whoever picks this up next, not attempted here.
**No registry change — S78 stays `collect-and-revisit`.**

## Step-0b tape sweep — and a caught near-duplicate-work convergence

`scripts/tape_branch_sweep.py --base-ref origin/main --no-fetch` over the 235 locally-fetched
`tape/hourly-*`/`tape/burst-*` branches found 2 genuinely stranded branches carrying real,
union-appendable tape (the other 13 "missing-line" branches were all `tape/cloud-env-check.md`
conflict-marker noise, correctly refused per L247):

- `tape/hourly-202608091000Z`: 756 lines across `crypto_hourly` (2), `polymarket_macro_pairs`
  (21), `sports_pairs` (733) — all `dt=2026-08-09`.
- `tape/hourly-20260809T0057Z`: 2 lines in `hyperliquid_funding/dt=2026-08-09.jsonl`.

All 758 lines union-appended by exact-string line-set membership (verified missing via a
branch-vs-HEAD line-count diff before appending, JSON-validity-checked after). No existing
line touched or reordered. None of these files were large enough to raise the GitHub
size question above.

**This run's own step-0b appending, and the two recovered `hyperliquid_funding` lines'
side-effect on a pinned test (another instance of L319's branch-local read race, pushing
`max_multiplicity` 2->3 with 0 value conflicts), all happened LOCALLY before this run pushed.**
At `git pull --rebase origin main` — delayed by this run's own long gate waits against the
now much larger tape corpus — it turned out a concurrent research-loop run (the 12:2x-14:xxZ
IDLE RUN documented in `LOOP-QUEUE.md`'s Log of runs, L319 ratchet milestone) had independently
run the exact same sweep, recovered the exact same 758 lines, hit the exact same test break, and
already merged a fix (`max_multiplicity >= 2`, which correctly anticipates further growth —
better than this run's own `== 3`, which the file's stated "written to survive tape growth"
convention would have flagged as a regression on its next stranded-branch recovery anyway). The
tape-file hunks applied as pure rebase no-ops (byte-identical content, confirming no double
counting), and the fix was kept as the concurrent run's, not re-done. See L319 in
`kb/lessons/00-lessons.md` for the original mechanism; no new lesson from this convergence.

## Gates

Fresh after the last code change (the day-file trim + test pin update): `pytest -q -n 4` →
0 failures across the full suite (~3,655 collected); `python3 scripts/invariants.py --full`
→ exit 0, all green (only pre-existing non-gating advisories, none new from this diff).

## Files

`reports/q52_q54_trades_backfill_phase1_phase2.json`, `tests/test_hl_funding_tape_quality.py`,
`tape/kalshi_trades/dt=2026-07-07/08/10/11/12.jsonl`,
`tape/crypto_hourly/dt=2026-08-09.jsonl`, `tape/polymarket_macro_pairs/dt=2026-08-09.jsonl`,
`tape/sports_pairs/dt=2026-08-09.jsonl`, `tape/hyperliquid_funding/dt=2026-08-09.jsonl`,
`LOOP-QUEUE.md`, `kb/00-LOG.md`, `kb/strategies/00-index.md` (S78 prose only).
