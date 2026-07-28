# Stranded-tape recovery (`tape/hourly-20260727T1303Z`, 21,303 lines) + `tape_branch_sweep.py` bulk-family blind spot (2026-07-28)

Step 0b milestone: three consecutive prior runs (PRs #217, #218/#219, #220) recorded
"`tape/hourly-20260727T1303Z` already recovered by PR #217 — nothing new to sweep," each
trusting `scripts/tape_branch_sweep.py`'s report at face value. This run re-verified that
branch directly, by hand, against `HEAD` rather than re-trusting the prior claim — and found
it was wrong.

## The blind spot

`tape_branch_sweep.py`'s per-file line-set containment check applies a `--max-file-bytes`
size guard (default 2,000,000 bytes) that **skips** any file above that size, reporting the
branch as "no problem found but NOT FULLY VERIFIED" rather than flagging a gap. The module's
own docstring says this "excludes this repo's bulk families by construction" —
`orderbook_depth`, `universe_sweep`, `sports_pairs`. That line is accurate on its face, but its
practical effect is a standing coverage hole: any stranded line in exactly those three families
is **structurally invisible** to the sweep tool, every run, forever, unless someone checks by
hand. Three runs in a row (07-27T21:1x, 07-28T00:1x, 07-28T03:2x) read "no branch newer than
`tape/hourly-20260727T1303Z`" and "13 missing-lines hits, all previously-triaged false
positives" as a clean bill of health for that branch — none of them noticed the size-guard
skip meant `orderbook_depth`/`universe_sweep` were never actually checked on it.

## What was actually stranded

Direct capture_id-level comparison of `tape/hourly-20260727T1303Z` (commit `0e9870b`,
2026-07-27T13:11:49Z, an `hourly_pass` run that fell back off `main`) against `HEAD`'s current
per-day tape files found three genuinely missing captures, none present anywhere in `HEAD`'s
tape tree:

| family | capture_id | lines | evidence |
|---|---|---|---|
| `weather_books` | `20260727T130038Z` | 302 | `HEAD`'s `dt=2026-07-27.jsonl` had captures at 04:00/07:00/16:00/22:00 only — 13:00 absent |
| `orderbook_depth` | `20260727T125540Z` | 1,001 | `HEAD` had 03:55/06:55/15:55/21:55 captures only — 12:55 absent |
| `universe_sweep` | `20260727T130302Z` | 20,000 | `HEAD` had exactly ONE capture (07:03) for the whole day — 13:03 absent entirely |

Total: **21,303 lines**, all valid JSON (verified via `json.loads` on every extracted line),
all `dt=2026-07-27`. The branch's other five touched files
(`crypto_hourly`, `hyperliquid_funding`, `perp_tape`, `polymarket_macro_pairs`,
`sports_pairs`, `weather_actuals`) were independently verified fully contained in `HEAD`
(raw line-set diff, 0 missing) — those are correctly not part of this recovery.

Union-appended to each family's `dt=2026-07-27.jsonl` (pure append — pre-recovery content is
an exact prefix of post-recovery content; post-append dedup check confirms 0 duplicate lines
in any of the three files). The branch is not deleted here — step 0b defers deletion until
the PR carrying these lines merges, per protocol.

## Why this matters beyond one branch

The same three families (`orderbook_depth`, `universe_sweep`, `sports_pairs`) are exactly the
ones large enough to trip the 2MB size guard on almost every `tape/hourly-*` branch, which
means **every prior sweep's "fully contained + verified" and "nothing new to sweep" claims for
these three families were never actually checked** — the tool's own report format
distinguishes "fully contained + verified" from "no problem found but NOT FULLY VERIFIED," but
prior runs' prose (including this run's own predecessors) collapsed that distinction when
summarizing the sweep result. New lesson **L216** (below) records this; the honest fix is
either a cheaper per-family check that doesn't require reading the whole file (e.g. capture_id
set comparison via a lighter parse, or raising the size guard for a bounded per-branch budget)
or an explicit standing exception: bulk-family branches always get the manual capture_id
check this run just did, never trusted to the tool's default guard alone.

## Gates

`python3 -m pytest -q`: **2,162 collected, 0 failed** (fresh `--collect-only -q` count, taken
after this diff's last edit — pure tape append, no source touched).
`python3 scripts/invariants.py --full`: exit 0, `invariants: all green` — same pre-existing
non-gating advisory classes as PR #220 (dir-shaped days, GC-dispatch, daily-cadence gaps,
hollow crypto ladders, capped-pagination coverage ceiling, raw-`fromisoformat` backlog,
recovery-dwell, unguarded-settlement; VPS collector-dead advisory duration increased as
expected). No new advisory class introduced by this diff.

No strategy claim, no registry change, no bootstrap CI/P&L — pure data recovery plus a
tooling-blind-spot finding, same posture as the 07-23/07-25/07-26/07-27 stranded-tape
recoveries. Two-agent verdict rule N/A (not a verdict-class change).
