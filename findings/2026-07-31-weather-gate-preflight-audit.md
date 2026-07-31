# Weather-revival gate pre-flight — Q37's summer-day counter was contaminated, and its EMOS half cannot run in a cloud checkout

`2026-07-31` · research loop IDLE RUN (protocol v3), idle-run policy (c) · **verdict class:
DATA-ADEQUACY / PRE-FLIGHT — no bootstrap, no CI, no P&L, no registry change, no kill.**

Re-runnable: `python3 scripts/weather_revival_gate_preflight_audit.py --as-of 2026-07-31`
(read-only, offline, no network). Offline tests: `tests/test_weather_revival_gate_preflight_audit.py`.

---

## The question

Q37 (weather revival, summer maker-side S1/S5 re-test) was the **next queue gate due to open**:
its probe self-activates when `_summer_contract_days_available() >= 21`. Every prior weather-revival
gate in this project taught the same lesson — Q36's settlement-basis leg opened onto a feed frozen
since its build day; Q43's calendar gate opened onto density-inadequate tape. *A calendar gate
opening is not the same event as the data being adequate.* So, with the gate days away rather than
weeks: **will Q37's inputs actually be adequate on the day it fires?**

Falsifiable form: for each of Q37's three inputs (the day-count gate, the settlement/EMOS-target
leg `tape/weather_actuals/`, the EMOS signal leg `data/forecast_tape/`), state an explicit
data-adequacy verdict with counted evidence. `tape/weather_actuals/` had never been audited.

## Answer: NO on two of three, and the day-count gate was measurably wrong

### (A) The gate counter was contaminated — it would have opened 2 days early

`_summer_contract_days_available()` reported **19** summer daily contract-days where only **17**
real ones existed. Two compounding defects in `scripts/q37_weather_summer_makerno_probe.py`:

1. `is_summer(d)` was `d >= SUMMER_START` with **no upper bound**, so any future-dated contract
   day satisfied "summer 2026".
2. `load_daily_snapshots()` applied **no series whitelist**. `tape/weather_books/` is captured by
   weather *family*, not by ladder *shape*, so it legitimately carries non-temperature weather
   series — which then flowed in as if they were daily temperature ladders.

Measured contaminants on committed tape (56,096 parsed daily rows):

| series | contract day | snapshots | what it actually is |
|---|---|---|---|
| `KXARCTICICEMIN` | 2026-10-01 | 162 | Arctic sea-ice minimum extent |
| `KXTXURI` | 2028-12-31 | 69 | named-storm market, settles end-2028 |

Each bought the gate exactly one phantom day (231 snapshots total, 0.41% of the population).
Neither can settle inside Q37's study window at all, so no amount of waiting would have made them
legitimate. Consequence, at the deliberately optimistic one-new-day-per-calendar-day rate:

| counter | days now | projected gate open |
|---|---|---|
| contaminated (pre-fix) | 19 | **2026-08-02** |
| real (post-fix) | 17 | **2026-08-04** |

i.e. the gate would have fired **two calendar days early, on 19 real days of tape instead of the
21 the gate exists to require** — a 10% shortfall against its own design, silently.

Downstream population effect, measured by force-opening the gate (`days_required=1`) with and
without the contaminants: 682 → 680 groups, 2,289 → 2,279 longshot trades (10 trades, 0.44%).
**Nothing in that forced-open diagnostic is a Q37 verdict** — the real gate is closed, the day
requirement was overridden, `optimistic_fill=True`, and the EMOS half was absent.

**Fixed this run, tightening only.** `SUMMER_END = 2026-09-22` bounds the window at both ends;
`is_temperature_series()` pins the `KXHIGH*`/`KXLOW*` grammar that all 41 real daily temperature
series share. Both guards can only ever *remove* rows — neither can admit anything the old code
rejected, so the gate is strictly tightened, never relaxed. The probe now reports 17.

### (B) `tape/weather_actuals/` — joinability is perfect, coverage is one third

First audit of this family. It is **alive but sparse**, not frozen:

- 7 day-files / 162 lines; capture days `07-16, 07-17, 07-18, 07-21, 07-22, 07-27, 07-30` —
  7 of a possible 16, so **9 daily passes never happened**.
- 1,374 `broker_truth` settled result tickers; 229 `(series, contract_day)` realized-high actuals
  spanning only **7 distinct settled contract-days**.

The join itself is sound — this is a coverage problem, not a schema or key problem:

| measurement | value | reading |
|---|---|---|
| join precision, `(series, contract_day)` | **1.0** (0 orphans) | every actual maps to a real book group |
| join precision, exact market ticker | **1.0** (0 orphans) | all 1,374 settled tickers ⊆ book tickers |
| book groups carrying settlement truth | **229 / 680 = 33.7%** | two thirds of the population has no outcome |

**The holes do not self-heal.** `collection/weather_actuals.py` targets
`cap_ts.date() - timedelta(days=1)` — yesterday only, no backfill. A missed daily pass is a
permanently missing settlement contract-day unless someone explicitly invokes the collector's
`--target-day` for that date, which nothing schedules. The data is still recoverable at source
(Kalshi still serves those settled markets, subject to the L10 purge bound), but recovery is a
deliberate act, not a matter of waiting.

### (C) `data/forecast_tape/` — EMOS is structurally unavailable to any cloud run

Q37's stated milestone is *maker-NO fill-sim **× S5 EMOS entry filter***. The EMOS half reads
`FORECAST_DIR = data/forecast_tape`. `data/` is gitignored by project contract (CLAUDE.md lane
discipline), so it is a property of the *checkout*, not of the repo: **`dir_present=False`,
`emos_input_available=False`** here, and in every cloud checkout, permanently. Forced-open
diagnostic confirms `emos_available: false` / `primary_emos_filtered: "EMOS_UNAVAILABLE"`.

This is not a collector failure — Q38 is legitimately DONE and the forecast leg is wired into
`hourly_pass.py`. It is a **lane mismatch**: the collector writes to a lane that cannot travel to
the analysis surface. Left alone, Q37 fires on its gate day and produces a baseline-only cut with
half its designed signal layer silently missing.

## What this means

- Q37 stays **GATED**. Its gate now reads honestly (17, not 19) and opens ~2026-08-04 at the
  earliest, later if capture dies again.
- When it opens, it will fire **baseline-only** unless the forecast leg is made reachable, and its
  EMOS training target will cover ~1/3 of contract-days even then. That is worth knowing before
  the run rather than after.
- No registry row moved. S1/S5 keep their existing status; no strategy was proven or killed here.

## Ryan-side / out-of-lane items (recorded, not acted on)

1. **Forecast lane.** EMOS needs `data/forecast_tape/` reachable from an analysis checkout —
   either a committed tape family or a VPS-local run. Both are lane decisions above a research run.
2. **Actuals backfill.** `collection/weather_actuals.py --target-day <date>` can recover the 9
   missed days while Kalshi still serves them. A write-path/collector-schedule change, not a
   research run's lane.

## Provenance

Every number above comes from `scripts/weather_revival_gate_preflight_audit.py` over committed
tape at `tape/weather_books/` (through `dt=2026-07-31`, incl. this run's step-0b sweep) and
`tape/weather_actuals/` (through `dt=2026-07-30`). No price is quoted anywhere in this finding —
it makes no fill claim, so no `price_source_tag` applies to any figure. Settlement values counted
are `broker_truth` only; the audit explicitly refuses events carrying any other tag
(`test_non_broker_truth_settlement_is_refused`).
