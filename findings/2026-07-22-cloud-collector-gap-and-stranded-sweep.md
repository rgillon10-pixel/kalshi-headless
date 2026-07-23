# 2026-07-22 — cloud `kalshi-collector` leg goes quiet for ~5h; stranded-tape sweep (2,056 lines)

**Run:** scheduled cloud research-loop, protocol v3. Idle run — Q0-Q47 all DONE/DEAD/BLOCKED/GATED
(matching #156/#158/#159/#160's same-day assessment); `main`'s own `invariants --full` gate is still
RED (issue #157, independently re-reproduced this run, byte-identical to the 06:47Z diagnosis). Idle
policy (a)/(b)/(d) all recently exhausted today (L-backlog empty since L128 except Ryan-gated L131 and
already-converted L136→L138; Q36/Q37/Q43 probes already self-activating; Q21 at 7 zero rounds) → took
**(c)**, paired with the mandatory step-0b sweep.

## Step 0b — stranded-tape sweep

Newest stranded branch `tape/hourly-20260722T1256Z` (commit `fae7446`, message `tape: hourly pass
2026-07-22T12:56:32Z (partial; universe_sweep too large)` — a `kalshi-collector` (cloud, no `(vps)`
tag) attempt that failed to push to `main` and fell back per the L17 mechanism). Union-appended via
sorted-line-set diff (`comm -13`, dedup-safe, 0 invalid JSON) — **2,056 genuinely-missing lines**
across 8 families: 1,383 `orderbook_depth`, 327 `sports_pairs`, 290 `weather_books`, 20
`weather_actuals`, 17 `perp_tape`, 15 `polymarket_macro_pairs`, 2 `crypto_hourly`, 2
`hyperliquid_funding`. Notable: the `weather_actuals` append **doubles** today's committed count
(20 → 40 lines) — that family is one of the single-UTC-hour daily-cadence legs L74/L75/L126 flagged
as exposed to full-day blackouts, so recovering a same-day duplicate-hour capture is a real gap-closer,
not just volume.

## Finding — cloud `kalshi-collector` (hourly, non-VPS) landed 0 successful commits to `main` for ~5h

`git log origin/main --since=2026-07-22T09:00:00Z` filtered to commits WITHOUT the `(vps)` tag (i.e.
the separate cloud `kalshi-collector` leg, not the VPS `:23` cron) shows:

```
6909fff tape: hourly pass 2026-07-22T10:06:30Z
af9181f tape: hourly pass 2026-07-22T10:05:41Z
825083b tape: hourly pass 2026-07-22T10:03:42Z
77028b8 tape: hourly pass 2026-07-22T09:56:33Z
```

Nothing since **10:06:30Z**. The run's own current wall-clock is 2026-07-22T15:1xZ — over 5 hours of
silence from the cloud leg's direct-to-`main` pushes. The ONE cloud-collector attempt in that window
(12:56:32Z) did fire, but failed to push and stranded onto `tape/hourly-20260722T1256Z` (now swept in
by this run) with an honest `(partial; universe_sweep too large)` self-report — consistent with L10's
known `universe_sweep` fetch-budget/RSS pattern, not a new failure mode. No cloud-collector attempt
(successful or stranded) is visible after 12:56Z, so as of this run the leg has been silent (not even
attempting) for ~2h20m on top of the ~2h50m it took to strand once.

Meanwhile the VPS `:23` leg is healthy and current (`855a54a`, `tape: hourly pass
2026-07-22T14:32:26Z (vps)`, 43 min old at run time) — this is a cloud-side gap specifically, the
mirror image of the VPS outage L117-L129 already tracked at length. `tape_gap_monitor.py`'s live
under-capture alerts on the hourly-dual families (`sports_pairs`/`crypto_hourly`/`orderbook_depth`/
`polymarket_macro_pairs`/`perp_tape`/`weather_books`, all ~0.46-0.48 capture ratio vs the 0.8 floor)
are consistent with this — VPS alone can't cover the expected 48/day two-collector baseline.

**Not fixed, on purpose.** The cloud collector's trigger/cron configuration lives in Ryan's account
(per `ops/ROUTINES.md` and the burst-capture section's own note: "they live in Ryan's account, not
this file"), outside this repo's reach — a cloud research-loop run cannot restart or diagnose it
further than reading the committed-tape trail. Flagged here and in the run digest/phone note for
Ryan; same posture as every VPS-outage finding to date (L117/L118/L126/L127/L129).

## Gates

`pytest` (excluding the two files broken by issue #157's pre-existing `cryptography`/pyo3 ABI panic):
1433 collected, 5 failed (identical to base `main`, all `test_invariants.py`, traced to #157) → 1428
passing, byte-identical failure set to `main` before this diff (stash-compared). `python
scripts/invariants.py --full`: exit 2, same 2 `order_endpoints_confined` violations as `main`'s
pre-existing state (issue #157) — this diff touches neither `tests/test_polymarket_us_live.py` nor
`tests/test_ws_depth.py`. Per LOOP-QUEUE.md step 6, **not merging** while `main`'s own gate is red —
same posture as #158/#159/#160, now a 4th PR stacked behind #157.

## Two-agent rule

N/A — no verdict-class change (no registry flip, no bootstrap CI, no kill decision; pure tape sweep +
ops/data-quality observation).

## Step 9 (paper sub-pass)

`SHADOW_REGISTRY={s14_ladder_underwriting}` (DEAD-at-real-fills per Q34 — paper-infra validation
only, not edge evidence). `paper_pass.py` processed 0 newly-eligible events from this run's sweep
(the swept `crypto_hourly` lines were only 2, both dated/duplicate); ledger unchanged **+$15.05**
(`broker_truth`). Still **0 proven edges**.
