# `tape/hyperliquid_funding/` second-pass data-quality audit — the venue baseline pin

2026-08-09 · research loop, idle-run policy (c) · `edge-prober` subagent (read-only, offline),
main context reviewed and wrote this doc. No strategy claim, no P&L, no fee model, no
bootstrap CI, no registry change — two-agent rule N/A (data-quality characterization, not a
verdict).

## Why this family, why now

`kb/lessons/00-lessons.md`'s UNENFORCED backlog is genuinely empty (verified via the repo's
own canonical query, `invariants._lesson_disposed_ids` — every nominally-`UNENFORCED` row is
already disposed by an `L188`-class supersession), and the standing queue (Q0-Q55) is fully
drained (all DONE / BLOCKED / RESERVED / time-gated / data-gated, most recently confirmed by
`kalshi-edge-hunter` round #25, 2026-08-07). Q51 milestone 3 (the next time-gated item, fires
2026-08-10) is already maximally prepped across five prior idle runs — nothing further to add
there. So this run took idle-run policy (c): a data-quality deep-dive on one tape family.

`findings/2026-07-26-hyperliquid-funding-tape-audit.md` audited this family's SHAPE (schema,
key-sets, null-freeness, append-only history, day-file-vs-print coverage, source tags) and
found one 2-row duplicate. It never audited the family's VALUES, and it predates 13 days of
new tape (`dt=2026-07-27` … `dt=2026-08-08`). This pass looks at what the numbers themselves
say, using the family's actual consumer — `scripts/q42_crossvenue_funding_join.py` (Q42) — as
the join reference rather than re-implementing it.

## Headline: a large minority of the Q42 join's windows carry zero information

Kalshi's finalized perp funding clamps to exactly `0.0` inside its own ±1bp dead band (Q42
part 1, `findings/2026-07-17-q42-funding-clamp-characterization.md`). This pass finds
Hyperliquid's hourly rate has an analogous constant: **its 0.01%-per-8h interest-rate
baseline, `1.25e-05`/hour**. A print sitting at that value to the exact bit is the venue's
floor, not an independent observation, and it happens **more than half the time**:

| coin | hours | pinned at baseline | pinned fraction | longest pinned run | median run |
|---|---|---|---|---|---|
| BTC | 1601 | 845 | 52.78% | 269h | 3h |
| ETH | 1601 | 894 | 55.84% | 270h | 2h |

Zero HL prints are exactly `0.0` in either coin (Q42's "never zero" premise holds), but "never
zero" and "an independent observation" are different claims — a pinned hour tells you nothing
a neighboring pinned hour didn't already say. ETH's rate never exceeds the baseline anywhere
in 1601 committed hours (`max_rate == baseline` exactly); BTC does (`max 1.8918e-05`).

**Joined 8h windows where BOTH legs sit at their venue's constant simultaneously** (re-using
Q42's own `WINDOW_HOURS`/`_compound` window join, imported not re-implemented, so this cannot
drift from what Q42 actually runs):

| asset | windows joined | Kalshi clamped | HL all-8-pinned | BOTH degenerate | fraction |
|---|---|---|---|---|---|
| BTC | 198 | 143 (72.2%) | 66 (33.3%) | 56 | 28.3% |
| ETH | 198 | 168 (84.8%) | 74 (37.4%) | 71 | 35.9% |

Across all 127 of those degenerate windows, the differential (`HL 8h-equivalent − Kalshi`)
takes **exactly one distinct value**: `1.0000437510937488e-04`. Zero variance — a window where
both legs are pinned cannot carry any information about a real basis, it can only reproduce
`baseline*8 − 0`.

**Implication for a future Q42 part 3 (data-quality, not a verdict):** the previously-reported
n=198 windows/asset overstates independent information materially — roughly a third of it is
one repeated constant, not 198 draws. A future CI on the differential must resample by
autocorrelated REGIME RUN (the way `n_pinned_runs`/`longest_pinned_run_hours` are reported
above), not by window, and should report the degenerate fraction as a mixture weight rather
than silently averaging it into the mean.

## Secondary findings (mostly extends already-known history, one new mechanism confirmation)

- **Coverage is still perfect at the hour level.** 1601/1601 hours, 0 missing, both coins,
  `2026-06-03T00:00Z → 2026-08-08T16:00Z`. The `dt=2026-07-18..21` file gap (L117 VPS-death
  window) remains a day-file hole, not an hour hole — the 07-26 finding's point still holds.
- **Duplicate `(coin, time_ms)` prints grew from 2 (07-26 reading) to 158 rows** (79/coin,
  4.93% of hours, max multiplicity 2, **0 value conflicts** — every duplicate agrees with
  itself on `(funding_rate, premium)`, so this is count-inflation, not a correctness defect).
  **Root cause is now diagnosable purely from committed tape:** 13 of 79 `mode=incremental`
  records per coin persist a `start_ms` that sits BEHIND the newest hour an earlier-captured
  record had already archived (e.g. capture `20260805T190647Z` computed `start_ms` from
  `2026-08-05T02:00Z` when the tape already held through `2026-08-05T16:00Z`) — a
  branch-local read race in `collection/hyperliquid_funding.py::_committed_time_ms`. The
  2026-07-26 audit reached this same mechanism only via `git log -S` archaeology; the
  persisted `start_ms` field makes it a pure-tape check going forward.
- **The one byte-identical duplicate LINE this family carries** (capture `20260728T070413Z`,
  BTC+ETH) is already-documented history: 2 of the 1,358 lines lesson `L285` censused across
  six families on `dt=2026-07-28`. Reproduced here, not new — measured separately from the
  158 `(coin, time_ms)` overlaps above so the two duplicate classes (one append written twice,
  vs. two distinct captures both re-covering an hour) are never conflated.
- **The Q42 join is not frozen** (unlike the 2026-07-21 finding, which is now stale in this
  respect — the family clearly got a working collector re-wired at some point after that
  note): 198 windows/asset join cleanly, 0 partial. One consequence of honest population
  growth: `q42_crossvenue_funding_join.py`'s hardcoded historical cross-check constant
  (`PART1_BTC_ZERO_FRACTION = 0.669`, tolerance 0.05) now reads `False` against the larger
  joined population (current BTC zero-fraction **0.7222**, `|Δ|=0.0532 > 0.05`) — a stale
  pin false-alarming, not a defect; the underlying full-population sanity check still passes.
  Left unmodified deliberately (see "not fixed" below).
- Capture cadence (79 distinct instants, median gap 3.04h, max gap 116.4h) reflects the
  already-documented global scheduler degradation (L117), not a family-specific defect.

## What was NOT changed

`collection/hyperliquid_funding.py` and `scripts/q42_crossvenue_funding_join.py` are
UNCHANGED. The `start_ms` race and the stale cross-check constant are both real and
cheaply fixable, but this run's charter was diagnosis (idle-run policy (c)), not a build
milestone, and Q42's own scripts are frozen against pinned real-tape gate tests (`L191`) that
a future dedicated Q42 milestone should update deliberately, not as a side effect of an
idle-run audit.

## Reproduce

```
python3 scripts/hl_funding_tape_quality.py
python3 scripts/hl_funding_tape_quality.py --json-out reports/hl_funding_tape_quality.json
```

Offline, read-only, no network. `tests/test_hl_funding_tape_quality.py` (24 tests: unit tests
for every pure function on synthetic records, plus a pinned real-tape acceptance layer written
to survive tape growth — `>=` on counts that can only grow, exact only on frozen history).

## Gates

`pytest -q` → **3637 collected** (24 new); full-suite pass/fail count taken fresh after the
last code change — see the Log-of-runs line in `LOOP-QUEUE.md` for the exact number timestamped
at commit. `python scripts/invariants.py --full` → exit **0**, all green (same non-gating
advisories as the prior run, none newly introduced by this change).

## Lesson candidates (for kb-distiller)

1. A venue's rate baseline/floor is a THIRD state beside "clamped to zero" and "free-floating"
   — a cross-venue join must count both legs' constant-valued windows before quoting a window
   count as independent information (this run's headline).
2. An incremental collector that persists the `start_ms`/watermark it computed FROM its own
   committed-tape read makes a branch-local dedup race detectable from tape alone, no
   `git log -S` archaeology needed — worth generalizing to other incremental collectors that
   don't yet persist their computed watermark.
3. A hardcoded historical cross-check constant embedded in a live, still-growing-population
   script (`q42_crossvenue_funding_join.py`'s `PART1_BTC_ZERO_FRACTION`) silently converts
   honest population growth into a false alarm; such constants should be labelled historical
   notes, with the live check re-derived against the current full population.

## Files

`scripts/hl_funding_tape_quality.py` (new), `tests/test_hl_funding_tape_quality.py` (new, 24
tests), `reports/hl_funding_tape_quality.json` (new), this finding, `kb/lessons/00-lessons.md`,
`LOOP-QUEUE.md`, `kb/00-LOG.md`.
