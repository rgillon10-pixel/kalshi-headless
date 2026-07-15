# Data-quality deep-dive: the 09-UTC daily-cadence tape families carried a 2-day blackout, not 1

**Date:** 2026-07-15 · **Type:** discovery-class data-quality note (read-only, no bootstrap, no
strategy registration, no registry flip — idle-run policy order (c)) · **Scope:**
`tape/econ_prints/`, `tape/polymarket_cpi_pairs/`, `tape/anomalies/`, contrasted with
`tape/polymarket_macro_pairs/` and the hourly families (`sports_pairs`, `crypto_hourly`).

## Why this family

`econ_prints`/`polymarket_cpi_pairs`/`anomalies` feed S12/S17/S18 and are the only
non-burst-window source of Kalshi's CPI/GDP/payrolls ladders and the anomaly sweep. With
FOMC (Jul 29) the next scheduled macro shock and its `--burst-window` probe already built
(per the 2026-07-15 edge-hunter run), a coverage check on the ordinary (non-burst) collection
path for this family was worth doing now, before that window — not after.

## What was checked

Read every `tape/<family>/dt=*.jsonl` file directly (no derived script — plain JSON parse +
aggregation, cross-checked against `ls` directory listings to rule out the L25-style
"directory instead of file" artifact masking a day as present-but-wrong-shape). Checked:
(a) per-day capture-day coverage across 7 tape families since 2026-07-03/04, (b) nested
`completeness_ok` on every `open_events.events[]` entry in `econ_prints`, (c) settlement-value
consistency for every distinct settled `event_ticker` across all repeated captures (drift
check), (d) which UTC-hour gate each family's sub-pass fires on, read from
`collection/hourly_pass.py` directly (`ANOMALY_SWEEP_UTC_HOUR`/`ECON_PRINTS_UTC_HOUR` = 9;
`polymarket_pairs.run_cpi` shares the same `ts.hour == 9` gate; `polymarket_macro_pairs`
(Fed-decision leg) fires every hour, no gate).

## Findings

**1. Completeness and drift are clean.** 4,774/4,774 nested `open_events.events[]` entries in
`econ_prints` have `completeness_ok: true` (100%, no partial-ladder captures). Across 8
distinct settled `event_ticker`s with repeated captures (e.g. `KXCPICORE-26MAY`,
`KXPAYROLLS-26JUN`), every capture agrees on `expiration_value`/`n_markets` — 0 inconsistent
records. This family's per-pass data quality, when it runs, is solid.

**2. Coverage has a real 2-day gap the incident writeup didn't call out by family.** Per-day
coverage (`.jsonl` files present, confirmed via `ls`, no stray directories for these three):

| family | missing days | gate |
|---|---|---|
| `econ_prints` | **2026-07-09, 2026-07-10** | `ts.hour == 9` only |
| `polymarket_cpi_pairs` | **2026-07-09, 2026-07-10** | `ts.hour == 9` only (same slot as `econ_prints`) |
| `anomalies` | **2026-07-09, 2026-07-10** | `ts.hour == 9` only |
| `polymarket_macro_pairs` | 2026-07-09 only | every hour, no gate |
| `sports_pairs` / `crypto_hourly` | 2026-07-09 only (07-10 present, but with the already-ledgered L25 stray-directory artifact for part of the day) | every hour, no gate |

The known 2026-07-08 main-branch reset (`kb/00-LOG.md` "2026-07-10 — RECONCILIATION" entry:
`origin/main` pushed back to the 2026-07-02 checkpoint at 07-08T10:56Z, orphaning 07-03→07-08,
reconciled 07-10 by merging the pre-reset lineage back in) already explains *why* collection
was disrupted in this window. What it doesn't say explicitly: the disruption cost the
once-a-day families a **full extra day** relative to the always-hourly families. The
post-reset lineage that ran through 07-09/07-10 rebuilt `sports_pairs`/`crypto_hourly` (core
primitives) and `polymarket_macro_pairs` far enough to fire again by 07-10, but never produced
a 09-UTC econ/CPI/anomaly pass on either day — so those three families went dark for 48
consecutive hours, not 24.

**3. Structural point, independent of this one incident.** `ECON_PRINTS_UTC_HOUR` /
`ANOMALY_SWEEP_UTC_HOUR` / the CPI leg's gate are all the *same single hourly window*
(`ts.hour == 9`) with no retry or backfill if that specific pass fails for any reason (a
collector crash, a transient host outage, another rewind-class incident) — one bad hour costs
a full calendar day of CPI/GDP/payrolls/Fed-nowcast/anomaly-sweep tape with nothing else to
catch it, unlike every hourly-cadence family which has 23 other chances the same day.
`scripts/invariants.py` has no check for a missing calendar day in a daily-cadence family (it
checks tape *shape*, per L25, not tape *presence over time*). No fix proposed this run —
flagging the exposure, consistent with the idle-run policy's "read-only ... report the coverage
fact honestly" instruction (Q25 precedent) rather than building an invariant nobody has asked
for. If a `dt=<date>` day-gap check is later wanted, `polymarket_macro_pairs`' hourly cadence
already provides a natural cross-family witness other daily families can compare against without
new tape.

## Verdict

Not a strategy finding — no CI, no registry flip. Descriptive coverage fact only, so the
two-agent verdict rule (which binds registry flips, bootstrap CIs, and kill decisions) does not
apply; numbers were independently cross-checked here via two methods (JSON aggregation +
directory listing) rather than routed through a separate verifier agent. Any future S12/S17/S18
probe that assumes continuous daily econ/CPI tape since collection began should account for this
2026-07-09/10 gap explicitly.
