# Q19 PREP: S17 burst-mode lead-lag + fillable dislocation scanner (built, offline-tested)

**Date:** 2026-07-13 · **Run:** kalshi-edge-hunter (nightly, cloud) · **Unit:** probe-prep
· **Verdict class:** NONE — this is a build + offline-test milestone, no CI, no registry flip.

## Why now

The June-CPI burst trigger (`kalshi-burst-cpi-0714`) fires **Jul 14 12:05→13:45Z** — inside
72h. It delivers 60s-cadence cross-venue tape bracketing the CPI print, the exact data class
whose absence left S17's first cut (`findings/2026-07-12-polymarket-macro-leadlag-s17-firstcut.md`)
descriptive-only. Per protocol, the analysis script is built and tested NOW so the per-event
run (fires the run after the burst tape lands) only has to execute it.

## What was built

`scripts/s17_leadlag_probe.py` gained a burst-mode entry point
(`--burst-window START END [--poly-fee F]`), additive and read-only — the hourly first cut is
untouched. New capabilities (Q19 spec (a)-(c)):

1. **Window isolation + cadence honesty.** `filter_burst_window` slices records by capture
   instant; `cadence_stats` reports min/median/max inter-capture gap so a window that is NOT
   actually burst-cadence is flagged loudly (median gap > 5min prints a WARNING and says the
   result is the same noise-floor characterization the hourly cut already gave).
2. **Per-ticker SIGNED lead-lag** (`per_ticker_leadlag`): which venue reprices first, per
   (meeting,bucket) pair, from the lag±1 cross-correlation of consecutive-capture Δ on the
   Kalshi yes-ask vs Polymarket best-ask series (both `real_ask`, same basis as the pooled cut).
3. **Fillable cross-venue dislocation scan** (`dislocation_scan` / `_best_dislocation`):
   every capture where buying the cheap venue's real ask and selling the rich venue's real
   bid clears BOTH venues' fees (`net_edge > 0`). Both Kalshi legs are charged the **taker**
   fee via `core.pricing.fee_per_contract` (never a hand-rolled literal) — crossing to buy at
   the ask OR sell at the bid both lift resting size, so neither is a free maker fill (the S13
   lesson). Polymarket's ~0 CLOB fee is a `--poly-fee` model **assumption** (default 0.0),
   tagged `assumed_zero_polymarket_clob` in the report's `fee_model` block, not a fill.
4. **Dislocation width × duration distribution** (`dislocation_episodes`): contiguous
   positive-edge runs per pair+direction → max edge (width) and wall-clock duration.

17 new offline unit tests (43 total in `tests/test_s17_leadlag_probe.py`), synthetic
in-memory records only. Gates green: **621 pytest passed**, `invariants.py --full` green.

## Honest scope (do NOT oversell — this SCANS, it does not book)

A positive `net_edge` is a fillable-at-observed-quotes locked pair (long Yes one venue +
short Yes the other = outcome-neutral), **not** a realised P&L. It ignores size/depth behind
the quote, the cross-venue settlement + capital-rail risk that is the very segmentation S17
rests on, and queue position. The per-event run makes the CI/verdict call under the two-agent
rule; this tool only produces candidates.

## Smoke observation over the HOURLY tape (a caveat the burst run must resolve)

Run against the accumulated hourly `tape/polymarket_macro_pairs/` (2026-07-06→07-13, correctly
flagged NOT burst-cadence, median gap ~31min), the scanner flags **616 candidate dislocations
across 29 episodes**, max edge ~$0.04 — but with episode **durations of hours to 3.5 days**.
A $0.04 cross-venue gap that persists for days across dozens of hourly captures is the
signature of a **stale / nominal Polymarket quote nobody is resting real size behind**, not a
repeatedly-fillable arb — the same wing/thin-book artifact family that produced S6's spurious
+$0.069 "edge" (lesson L31). This is exactly why burst tape matters: the **width × duration**
distribution is the discriminator. A real information-shock dislocation should be **short-lived**
(seconds-to-minutes of repricing lag around the print); a persistent multi-hour gap is a
nominal-quote artifact. The CPI/FOMC burst run's first job is to check which of the two the
event-window dislocations look like — the scanner now measures that directly.

## What fires next

- Jul 14: CPI burst tape lands → PER-EVENT run executes `--burst-window` over it →
  `findings/2026-07-14-s17-burst-cpi.md` (two-agent rule if any tradeable claim).
- No registry change here. S17 stays `data-collecting`.
