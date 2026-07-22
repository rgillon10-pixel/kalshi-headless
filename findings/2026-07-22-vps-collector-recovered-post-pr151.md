# VPS collector recovered — confirms PR #151's self-heal fix, closes the L117/L118 outage

**Date:** 2026-07-22 (research loop, idle-run policy (c) — data-quality deep-dive)
**Status:** descriptive/ops confirmation, no strategy claim, no registry change. Two-agent
verdict rule N/A (not a verdict-class change — same posture as L117/L118/L127/L128's
diagnosis-only entries).

## Headline

The VPS `:23` cron that died 2026-07-19 (root-caused 2026-07-20 as L117, tracked through
L118/L126/L127) **is producing fresh tape again**, starting **2026-07-21T22:41Z**, immediately
after `PR #151` (the self-healing hourly-runner wrapper) merged at `22:37:40Z`. This closes a
3-day outage that had degraded or fully blocked five tape families and gated Q36/Q42/Q43's
`vps_dead` conditions.

## Evidence (independently re-derived against real committed tape, not just commit messages)

1. **Recovery commits exist and are VPS-authored.** `git log` shows two `vps-collector`-authored
   commits after PR #151 merged: `069df6b` (`2026-07-21T22:48:18Z`) and `261133e`
   (`2026-07-21T23:31:05Z`), both `tape: hourly pass ... (vps)`.
2. **The captured content is genuinely fresh, not a backfill relabel.** Per-line `captured_at`
   timestamps inside `261133e`'s `tape/orderbook_depth/` and `tape/weather_books/` diffs are
   `2026-07-21T23:23:5{4,8}Z` and `T23:28:34Z` — i.e. captured within the same pass that produced
   the commit, not older recovered lines.
3. **Minute-of-hour signature matches the VPS bucket.** L118's calibrated buckets are
   `vps: :20-29`, `cloud: :50-59`, else `other`. The `23:23-23:28` captures land squarely in the
   VPS `:20-29` bucket — this is the collector's normal cron phase resuming, not a one-off stray
   pass.
4. **`scripts/tape_gap_monitor.py --now 2026-07-22T00:10Z` corroborates independently:**
   `crypto_hourly`'s `collectors.vps.newest_captured_at` = `2026-07-21T23:23:54Z`, `passes: 1` —
   the monitor (which reads only committed tape, no knowledge of commit messages) sees exactly
   one fresh VPS-bucketed pass in its 24h window, consistent with a collector that just came
   back up ~40 minutes before this run started.
5. **One earlier, off-cadence pass at `22:41-22:48Z` (minute 41-48, neither bucket)** is the
   catch-up pass the self-heal script fired immediately on deploy, before settling back into its
   normal `:23` cron phase by the next firing (`23:23Z`). Consistent with PR #151's described
   fix: abort stale `rebase-merge` state (age > 2h) before pulling, so a wedged rebase can no
   longer wedge every subsequent hourly firing.

## What is NOT yet true

- **Under-capture alerts have not cleared.** `tape_gap_monitor` still reads `sports_pairs`,
  `crypto_hourly`, `orderbook_depth`, `weather_books`, `polymarket_macro_pairs`, and `perp_tape`
  as `ALERT` (ratios 0.19-0.21) — expected: the 24h window denominator (48 expected passes)
  still includes ~3 days of the outage. This will self-clear over the next ~24-36h of VPS passes
  without further action, and should NOT be re-diagnosed as a fresh VPS-death in the meantime.
- **`settlement_ledger` and `hyperliquid_funding` are still stale** (107.8h / 113.8h). The
  `settlement_ledger` leg is gated at `SETTLEMENT_LEDGER_UTC_HOUR=10`; the VPS has not yet fired
  an hour-10 pass since recovering (next opportunity ~2026-07-22T10:23Z). `hyperliquid_funding`
  has no scheduled refresh at all (L127 candidate (a), still open/unbuilt) — VPS recovery alone
  does not fix it.
- **Q36's calendar gate:** `tape/weather_books/` has 6 distinct committed days
  (`dt=2026-07-16`..`2026-07-21`) as of this run, still short of the `>=7` floor. With VPS back,
  the gate should open on schedule (~2026-07-22/23) rather than staying starved.

## Why this matters for the queue

Q36 (weather revival), Q42 part 3, and Q43 (perp/binary consistency) all carry `STILL GATED`
notes whose root cause was the same dead VPS collector (L117). None of their verdicts change
here — this is purely a collector-health confirmation — but the next run that finds Q36 or Q43's
calendar gate open should NOT assume thin per-day density (the 2026-07-20/21 runs' caveat); it
should re-check `tape_gap_monitor` fresh, since the VPS side of the pipe is producing again.

## Reproduce

```
python scripts/tape_gap_monitor.py --now 2026-07-22T00:10:00Z --no-notify
git log --oneline --since="2026-07-21T22:00:00Z" -- tape/
git show 261133e -- tape/orderbook_depth/ | grep -o '"captured_at":"[^"]*"' | sort -u
```
