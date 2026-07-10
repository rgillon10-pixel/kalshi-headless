# 2026-07-10 — Tape-format regression: `crypto_hourly`/`sports_pairs` wrote unreadable raw blobs for ~19h

**Status: bug found, self-corrected, historical data not yet recovered — decision needed.**

## What happened

Checking Q7's eligibility (needs ≥7 distinct days of `tape/crypto_hourly/`) this run, the day
count looked like it had just crossed the bar: `tape/crypto_hourly/` had entries for
`dt=2026-07-03` through `dt=2026-07-08` (6 canonical `.jsonl` files) plus what looked like a
7th day, `dt=2026-07-10`. On inspection, `tape/crypto_hourly/dt=2026-07-10` is not a file —
it's a **directory** containing 23 `capture-<timestamp>/` subdirectories, each holding raw,
per-market Kalshi API response blobs (`kxbtckxbtc26jul0921.raw.json` etc.), not the canonical
`dt=2026-07-10.jsonl` line-per-record format every other day uses. `tape/sports_pairs/` has
the identical problem (22 capture directories, ~9,655 raw files).

**Root cause.** This repo's `main` was rewound to a 6-day-old checkpoint on 2026-07-08T10:56Z
(see the 2026-07-10 RECONCILIATION entry at the top of `kb/00-LOG.md`). Unaware, the cloud/VPS
collectors rebuilt `collection/crypto_hourly.py` and `collection/sports_pairs.py` from scratch
on 2026-07-09/10 — and that rebuild wrote a *different* storage format (raw-blob capture
directories) than the pre-reset lineage's collectors (canonical `dt=<date>.jsonl`). PR #35
(merged today, 19:37:23Z) reconciled the **code** in this repo back to the pre-reset lineage
(which is what `collection/crypto_hourly.py` on `main` does today — writes
`dt={day}.jsonl`), but the **already-committed tape** from every hourly pass between
2026-07-10T00:26Z and 2026-07-10T19:24Z (23 passes, both the cloud loop and the VPS cron) is
stuck in the old raw-blob format, because those passes ran the pre-reconciliation code.

**Bigger gap than the format mismatch alone.** The post-reset `hourly_pass.py` only ran 2
sub-passes (sports + crypto) — the pre-reset lineage's `hourly_pass.py` runs 5 (sports,
crypto, Polymarket pairs, Polymarket macro pairs, orderbook depth). So for the same ~19h
window, `tape/orderbook_depth/`, `tape/polymarket_pairs/`, and `tape/polymarket_macro_pairs/`
have **no entries at all** for 2026-07-10 (not even in the wrong format) — those sub-passes
simply didn't run.

**Confirmed self-corrected.** The stranded branch `tape/hourly-20260710T1955Z` (commit
`cf33e5f`, timestamped 2026-07-10T20:01:49Z — the first hourly pass to run *after* PR #35
merged) writes proper `tape/crypto_hourly/dt=2026-07-10.jsonl`,
`tape/sports_pairs/dt=2026-07-10.jsonl`, **and** populates `orderbook_depth`,
`polymarket_pairs`, `polymarket_macro_pairs` for the first time today — confirming the
collectors pick up fresh code each run and the fix is already live going forward. That
branch's push to `main` hit the known intermittent-push-failure issue (L17) and is under 30
minutes old as of this run, so it's left for the next run's step-0b sweep rather than merged
now.

## Impact

- **Q7 (S10 reachability decay)** is NOT newly eligible — the apparent "7th day" was this
  unreadable directory, not usable tape. Still 6 valid canonical days (03–08). Corrected the
  day-count method in `LOOP-QUEUE.md`'s Q7 entry so a future run doesn't get fooled by a
  directory that merely shares the `dt=<date>` name prefix.
- **~19 hours of `crypto_hourly`/`sports_pairs` snapshots (23 passes)** are sitting in raw form
  and are not readable by any existing analysis script.
- **~19 hours of `orderbook_depth`/`polymarket_pairs`/`polymarket_macro_pairs` coverage** simply
  don't exist for 2026-07-10 (those sub-passes weren't running under the post-reset code).

## What this run did NOT do

Did not attempt to reprocess the raw blobs into canonical `.jsonl` records. The raw blobs are
complete per-market Kalshi API responses (see sample below), so a reconstruction is *possible*
in principle, but `collection/crypto_hourly.py`'s canonical record also pairs each snapshot with
a previous-hour settlement fetch and a spot-price fetch that were not necessarily captured
alongside these blobs in a recoverable form — building that converter correctly, without
introducing synthetic-looking-real data, is a real milestone of its own, not a same-run
tack-on. Left as an open decision for Ryan / a future `collector-engineer` milestone.

Sample raw blob (`tape/crypto_hourly/dt=2026-07-10/capture-20260710T002212Z/kxbtckxbtc26jul0921.raw.json`,
truncated):

```json
{"KXBTC-26JUL0921-B52250": {"floor_strike": 52200, "cap_strike": 52299.99, "yes_ask_dollars": "0.0100", "yes_bid_dollars": "0.0000", ...}}
```

## Recommendation

1. Ryan: decide whether the ~19h of raw crypto/sports blobs are worth reprocessing (a
   `collector-engineer` milestone) or an acceptable gap (Q7/S10 loses one day of history but
   the day-boundary already resets tomorrow).
2. No code fix needed — the collectors are already producing the correct format as of the
   first pass after PR #35's merge.
3. Added `kb/lessons/00-lessons.md` L25 (UNENFORCED): after any code-reconciliation event,
   verify a tape family's `dt=<date>` entry is the expected **file** shape, not just that a
   same-named path exists — a directory masquerading as a day is an easy miss for a
   line/day-count check.
