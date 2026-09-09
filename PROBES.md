# PROBES — the coordination surface since 2026-09-09

`LOOP-QUEUE.md` is **retired** as the coordination surface (kept read-only as history; do not
append to it). The autonomous research loop, edge-hunter, and cloud collector routines no
longer exist; the observatory and weekly retro are disabled. There is no autonomous idea
generation. Work is human-picked, Claude-assisted, and recorded in the reset folder:

    ~/Active/01-projects/kalshi-26/reset-2026-09/

Read `00-plan.md` there first. The decision gate is **2026-12-01**; the default outcome is
mothball unless a probe produces broker-truth evidence.

## Why (one paragraph)

Seven attempts, ~40 candidates tested at real asks, 0 proven. Every death is the
fee-plus-overround wall, not data (Q39: taker and cross-venue strategies stay negative even
fee-free). The only sign-flip in the graveyard is maker strategies under a rebate (Q35), and
Kalshi now runs a public Liquidity Incentive Program that pays for resting orders. That lane
and the one never-falsified thesis (S2, FOMC ladder vs futures) are the two probes.

## Active probes

| Probe | What | Window | Protocol + ledger |
|---|---|---|---|
| A | Hand-quote both sides in thin Kalshi markets with an active liquidity reward pool; ledger paid rewards (`broker_truth`), fill P&L, adverse selection | 2026-09-15 → 11-20 | `reset-2026-09/50-probes/PROBE-A-kalshi-liquidity-program.md`, `ledger-A.csv` |
| B | `KXFEDDECISION` ladder vs CME FedWatch / ZQ, daily on free data; burst capture on Sep 16 / Oct 28 / Dec 9 | 2026-09-10 → 12-09 | `reset-2026-09/50-probes/PROBE-B-fomc-ladder-vs-futures.md`, `ledger-B.csv` |

Both probes: no new modules beyond a ledger script; source-tag discipline (`real_ask` /
`broker_truth` / `synthetic`) stays; capital ≤ $200 total; live orders only by hand until a
probe graduates through the execution lane in `CLAUDE.md`.

## What still runs (collection only)

VPS hourly pass (`:23`) → `tape/` on main; monitor scope (`:08`) + ingest (`*/15`) +
healthcheck (`*/5`) + gap monitor (6h); `kalshi-headless-wsdepth.service` (needs a live key);
REST poll fallback (`* * * * *`). Retired legs are listed in `collection/hourly_pass.py`
`RETIRED_LEGS` (weather books / forecasts / actuals, sharp-odds de-vig).

## Kill / keep

See `reset-2026-09/00-plan.md` §6. Do not re-open: weather (dead ×4), sports CLV, crypto
ladders, cross-venue taker arb, unpaid Kalshi making, earnings iron condors.
