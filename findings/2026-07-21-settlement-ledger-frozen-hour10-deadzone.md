# settlement_ledger frozen since its build day — single-hour label-legs land in the degraded pipe's dead-zone

**2026-07-21 · kalshi-edge-hunter nightly run · data-quality deep-dive (idle-policy (c)) · non-verdict ops finding**

## One-line

`tape/settlement_ledger/` has produced **exactly one day of data** (`dt=2026-07-17`, 5605 rows, its Q45 build day) and **nothing since** — because the leg is gated to fire only at UTC hour 10 (`ts.hour == SETTLEMENT_LEDGER_UTC_HOUR`), but the live `kalshi-collector` routine runs **every 3 hours** (`cron: 53 */3 * * *` → passes at UTC {0,3,6,9,12,15,18,21}), so it **never runs at hour 10** — and the VPS collector that could is dead since 07-19 (L117). The single-hour label-legs were designed assuming an *hourly* collector (which `ops/ROUTINES.md` still lists as the desired state); the live cadence is every-3h, a routine drift that leaves hours 10 (settlement_ledger) and 11 (forecast) permanently unreachable from the cloud. This — not "under-powered density" (the 2026-07-20 framing) — is the hard root cause of Q36's settlement gate stuck at `n_settled_events=1`; it cannot advance on calendar time.

## Evidence (all re-runnable over committed tape)

**1. settlement_ledger never written past its build day.**
```
git log --all --oneline --name-only | grep -oE "tape/settlement_ledger/dt=2026-[0-9-]+" | sort -u
# → tape/settlement_ledger/dt=2026-07-17   (the ONLY one, across --all)
```
Working tree: `tape/settlement_ledger/` = 1 file, `dt=2026-07-17.jsonl`, 5605 lines. KXTEMPNYCH settled events in it: **1** (`KXTEMPNYCH-26JUL1707`, 10 strike-lines → 1 distinct `event_ticker`). Not stranded either: `settlement_ledger/dt>=07-18` appears on **none** of the `tape/hourly-*` fallback branches checked — the leg genuinely produced no output, it is not a sweep gap.

**2. UTC hour 10 lands no collector pass on any recent day.** `crypto_hourly` is captured by every `hourly_pass` invocation, so its set of landed UTC hours = the set of hours where a pass reached `main`:

| day | UTC hours that landed a pass | hour 10? | hour 11 (forecast)? | hour 12 (actuals)? |
|---|---|---|---|---|
| 2026-07-18 | 0,1,2,3,4,5,6,7,8,12,18,21 | ✗ | ✗ | ✓ |
| 2026-07-19 | 0,3,6,9,15,18,21 | ✗ | ✗ | ✗ |
| 2026-07-20 | 0,3,6,9,12,15,18,21 | ✗ | ✗ | ✓ |
| 2026-07-21 (to 04:15Z) | 0,3 | ✗ | ✗ | — |

Hour 10 is absent **4/4 days**. Hour 11 absent 4/4. Hour 12 lands only intermittently (2/3 completed days). The healthy cadence would be ~24–48 passes/day (VPS `:23` + cloud `:53`); the pipe is landing ~8/day at ~3-hour spacing, all in the cloud `:5x` minute-bucket (VPS `:23` bucket = **0 lines since 07-19**, confirming L117's dead-VPS-cron diagnosis persists).

**3. The three single-hour label-legs are all exposed to this.** `collection/hourly_pass.py`: `SETTLEMENT_LEDGER_UTC_HOUR=10`, `FORECAST_COLLECTOR_UTC_HOUR=11`, `WEATHER_ACTUALS_UTC_HOUR=12`, each fired on exact-hour equality (`if ts.hour == …`). Observed consequences match exactly: `settlement_ledger` frozen at 07-17 (hour 10 never lands), `weather_actuals` dark since 07-18 (hour 12 landed 07-18 & 07-20 but the actuals leg found no newly-posted CLI those runs / hour 12 missed on 07-19 & 07-21), forecast tape gitignored so not directly observable here. By contrast `universe_sweep` (gated on the **set** `{0,6,12,18}`, not a single hour) has captured cleanly every day 07-17 → 07-21 (20,000 lines/day) — the multi-hour gate is what makes it robust to the sparse landing pattern.

## Why it matters (the Ryan-relevant consequence)

Q36 (weather revival — KXTEMPNYCH hourly-market settlement-basis, a Ryan-prioritized directive) needs ≥10 settled KXTEMPNYCH event-hours in `tape/settlement_ledger/` for its `MIN_EVENTS=10` gate. The 2026-07-20 audit correctly reported `n_settled_events=1` but attributed it to under-powered density. The sharper truth: **the settlement_ledger collector has not run since 07-17**, so that count is frozen at 1 and cannot advance one event per calendar day as assumed — Q36's settlement leg is structurally un-testable until the pipe is fixed. The calendar gate opening ~07-22 is therefore moot for this leg.

## Fix (documented, NOT applied this run — deliberately left for Ryan / a supervised run)

Two parts, in priority order:

1. **Restore the collector cadence (Ryan / VPS-side, primary).** The VPS `:23` cron has been dead since 07-19 (L117) and the cloud `kalshi-collector` is landing only ~1/3 of its hourly passes to `main`. With the pipe landing ~8 passes/day at unpredictable hours, *no* single-hour gate is reliable. This is the root fix and it is outside cloud-run scope.

2. **Make the single-hour label-legs robust to hour-misses (code, secondary).** Change the exact-hour gate to *"fire on the first landed pass at-or-after the target hour, at most once per UTC day"* (idempotency keyed on today's family tape file already existing). settlement_ledger is global-dedup append-only (a re-fire is harmless); weather_actuals/forecast would need their per-day idempotency checked. This is a genuine reliability improvement but it modifies the firing behavior of three **live** collection legs, so — unlike the additive self-activating collectors idle runs have self-merged (Q33/Q44/Q45/Q46) — it is left here as a proposal rather than merged unattended at 04:15Z with no human watching. It is also secondary: a gate that fires "at/after hour 10" still needs the pipe to land *some* pass that day, which part 1 addresses.

## Scope / provenance

Read-only over committed tape + git history. No strategy claim, no bootstrap CI, no `kb/strategies/00-index.md` registry flip — this is a collector-health characterization, so the two-agent verdict rule does not formally bind (same tier as the 2026-07-20 Q36 data-adequacy audit and the collector-build precedents). An independent `verifier` pass **CONFIRMED** both counts (settlement_ledger never written past 07-17; hour 10 lands no pass 07-18→21), closed the stranding hypothesis (no post-07-17 `tape/hourly-*` branch carries a `T10xx` timestamp), and confirmed Q36's probe globs `settlement_ledger` as its sole feed with no alternate KXTEMPNYCH settlement source. Lesson candidate registered as **L123** (UNENFORCED) in `kb/lessons/00-lessons.md`. Every number above is a plain tape/git count with its command shown.
