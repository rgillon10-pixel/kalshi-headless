# Q56 / S81 — the binding test is built and SEALED: the join keeps 14% of the informative cell

**Run:** kalshi-research-loop, 2026-08-10 (later firing). **Queue item:** Q56 (topmost TODO).
**Milestone executed:** S81's binding test (the S80 milestone is untouched and stays TODO).
**Verdict class:** DATA-ADEQUACY. **No CI, no P&L, no kill, no registry flip.** S81 stays
idea-stage `binding-test-defined`. **CONFIRMED-WITH-CORRECTIONS** by an independent `verifier`
agent dispatched later in this same run (see "Independent verifier pass" below) — supersedes the
PROVISIONAL status this note originally carried when no verifier was yet dispatchable (no
`Task`/subagent tool in the producing sub-context; the L287/L288/L290/L291/L295/L308/L313/L325
precedent). A same-commit redundancy check also ran regardless: an independently-written second
code path sharing no code with the probe (below).

## What was built

`scripts/q56_s81_funding_regime_settlement_probe.py` (+36 offline tests in
`tests/test_q56_s81_funding_regime_settlement_probe.py`) — the pre-registered, gate-sealed
binding test Q56 specifies for S81, hash-locked at `PREREG_SHA256 =
edde1f66efc059d3628128ad2bbf0e49d60526c274664ca8e8bb5978dec34581`.

Spec, in one paragraph (the full pre-registration is the module docstring): label every
(coin, UTC hour) from `tape/hyperliquid_funding/` as `pin` (rate exactly at the 0.01%-per-8h
interest baseline — L318's dead band), `sub_baseline`, `negative`, or `above_baseline`; block
by REGIME RUN, never by hour or window (L318/L324's house rule, encoded in
`.claude/agents/edge-prober.md`); take one entry snapshot per (coin, `event_ticker`) — the
latest `crypto_hourly` capture with `current.status == "ok"` strictly BEFORE that event's own
`close_time`; the directional leg is the single `between` bracket immediately ABOVE the bracket
holding spot; fill at its resting `yes_ask` (`real_ask`) net ONE `core.pricing` taker fee;
settlement is `broker_truth` through `core.settlement_sources` (nine declared families, L300);
score P&L = payoff − ask − fee; bootstrap by regime run, n_boot 10,000, seed 42, through
`bootstrap_verdict_admissible` + `clears_tick_magnitude`. Spot (`coinbase`, tag `synthetic`) is
used ONLY to decide which bracket is adjacent — never as a price, never as an edge input.

**The seal.** `population_report()` is outcome-blind by construction: it receives a MEMBERSHIP
set from `settled_ticker_set()`, which collapses every settlement to `is_binary_result(...) ->
bool` and drops the direction. `outcome_map()` (the only function that reads a result's value)
and `score_rows()` (the only one that computes a return) are unreachable from `run()` unless the
gate opens. Tests pin that the sealed report contains none of
`pnl/mean/ci95/edge_after_fee/payoff/verdict_ci/n_wins`.

## What it measured (outcome-blind; nothing below required reading a single settlement direction)

`python scripts/q56_s81_funding_regime_settlement_probe.py` → `reports/q56_s81_funding_regime_settlement.json`

| quantity | value |
|---|---|
| entry snapshots (one per coin×event, strictly pre-close, `status: ok`) | **854** |
| settlement-joinable | **574** (`crypto_hourly` = 574 hits; the other 8 declared families = **0**) |
| unjoinable | **280** |
| **informative cell** (`sub_baseline` + `negative`) | **19 entries** (17 + 2), **15 fillable**, **11 runs**, **8 fillable runs**, **Kish effective n 4.79** |
| control cell (`pin` — L318's dead band, benchmark only) | 555 entries, 368 fillable, 13 runs, 12 fillable runs, Kish **3.49** |
| gate | `admissible: false`, reasons `["below_min_units", "below_min_kish_effective_n"]` |

Pre-registered gates: ≥10 informative regime runs (L41) · Kish effective n ≥ 10 (L322/L326) ·
≥10 fillable informative entries. Only the third opened (15 ≥ 10). Note the first gate fails on
the **plain L41 floor** (8 fillable runs < 10), so the verdict does not rest on the stricter
Kish condition — that condition was adopted from the existing ledger (L322/L326), not invented
here, and every number above was computed without reading an outcome, so the gate choice
cannot have been result-motivated.

Entry legs are genuinely fillable near-money instruments, not 1¢ wings: the 15 informative
fillable asks are `[0.02, 0.06, 0.10, 0.11, 0.16, 0.16, 0.17, 0.18, 0.20, 0.26, 0.29, 0.35,
0.36, 0.37, 0.41]` (`real_ask`, resting, two-sided). S10's no-fillable-price kill genuinely does
not apply — the verifier's registration claim survives.

## The load-bearing finding: the wall is the JOIN, not the funding tape

Marginally, both legs look abundant. Funding: BTC pin 848 / sub_baseline 606 / negative 179 /
above_baseline **1**; ETH pin 926 / sub_baseline 435 / negative 273 — 1,493 short-crowded
coin-hours. Kalshi: 854 pre-close entry snapshots. S81 was registered on exactly that kind of
marginal count ("215 BTC settlement events / ~338 regime runs ≫ 10-unit floor").

Joined, the informative cell is **19 entries / 8 fillable runs / Kish 4.79** — 19 of the **136**
total `sub_baseline`+`negative` snapshots in the full funding census (the join keeps 14% of that
captured-informative population, the "14%" in this note's title), and just 3.3% of the full
574-entry joinable universe — two different denominators, do not conflate them.

The loss is almost entirely one mechanism. `crypto_hourly`'s settlement is EMBEDDED in the
capture: each record's `previous_settlement` reports ONLY the event that closed immediately
before that capture. So an entry snapshot is settlement-joinable **only if another capture lands
in the hour after its event closes**. Starting ~2026-07-15 the collector's capture-pass cadence
(distinct `capture_id`s/day) fell from ~46–50/day to ~2–8/day, reaching that floor around
07-23 (one relapse day, 07-29, at 27) — an ~8× collapse measured in one consistent unit — and the
joinable count collapses with it:

```
joinable entries/day   07-11..07-17: 44,44,44,44,44,34,44   07-18: 18   07-21: 6   07-22: 34
                       07-26: 2   07-28: 2   07-29: 4   08-05: 2   (nothing since)
```

**Counterfactual, measured on the same tape:** if every captured entry snapshot had its
settlement recorded, the informative cell would hold 136 entries over 94 regime runs, of which
**105 fillable entries over 77 fillable regime runs, Kish effective n 58.3** — 5.8× the floor and
comfortably adequate. The design is not structurally starved; it is starved by one collector's
settlement-pairing.

**Therefore the unblock is a bounded PULL, not a calendar wait.** 280 unjoinable entry snapshots
(117 of them in the informative cell, 90 fillable, 69 runs) name concrete, long-settled
`KXBTC-*`/`KXETH-*` bracket tickers whose results the public `/markets` endpoint still serves.
A settlement backfill for those tickers is a collector milestone of exactly the Q52/Q54 phase-1
shape, and it would open the gate far sooner than waiting: at the current accrual rate (3
fillable informative runs since 07-23, ~1.17/week) the plain L41 floor (10 fillable runs) is an
estimated ~2 weeks out, but the stricter Kish-effective-n ≥ 10 condition needs roughly a dozen
more singleton runs — an estimated ~10+ weeks. The two gate conditions have very different
waits; a backfill opens both immediately.

## Second measured fact worth carrying forward

The CONTROL cell has 555 joinable entries and a Kish effective n of **3.49** — because pinned
hours arrive in enormous autocorrelated runs (largest run block: 167 entries, then 85, 48, 28,
24). Any future probe that blocks crypto-hourly work by funding regime should expect nominal
sample sizes in the hundreds to buy single-digit independent blocks. This is L318's
"a pinned hour tells you nothing a neighbouring pinned hour didn't already say", now measured on
the Kalshi side of the join.

## Independent re-derivation (the sanctioned no-verifier fallback)

A second implementation sharing NO code with the probe — own JSON reader, own baseline constant
re-derived from L318's text (0.01% / 8h) rather than imported, own calendar-arithmetic hour
index, own run builder, own leg picker, own settlement read straight from
`crypto_hourly.previous_settlement` (never `core.settlement_sources`), own Kish formula —
reproduces every headline exactly: 854 entry candidates, 574 joinable, informative 19 entries /
15 fillable / 11 runs / 8 fillable runs / Kish 4.787234042553192 (12 decimals), by-regime
{negative 2, sub_baseline 17}; control 555 / 368 / 13 / 12 / Kish 3.4863556791267634; and the
all-settled counterfactual 105 fillable entries / 77 fillable runs. This is a redundancy check,
NOT a verifier: it shares the probe's design premises (that the adjacent-above bracket is the
right directional instrument, and that the capture-hour funding print is the right label) and
could not have caught an error in either.

## Independent verifier pass (2026-08-10, same run)

A dispatchable `verifier` agent became available later in this same run and re-derived every
headline number above from a third, from-scratch implementation (own reader, own baseline, own
Kish formula), reproducing all of them exactly, confirmed the pre-registration hash is genuinely
load-bearing (test-pinned, not decorative), and confirmed outcome-blindness at runtime by
booby-trapping `outcome_map`/`score_rows`/`binary_outcome`/`verdict_block` and observing `run()`
complete via `SEALED_INSUFFICIENT_DATA` without calling any of them. **Verdict:
CONFIRMED-WITH-CORRECTIONS** — the DATA-ADEQUACY/gate-SHUT verdict itself stands unchanged; four
wording/unit corrections were required and are folded into this note (the capture-cadence unit
mix and onset date above; "fillable" qualifiers on the counterfactual 105/77; the two-denominator
14%-vs-3.3% clarification above; and the split L41-floor-vs-Kish-floor wait estimate above). This
satisfies LOOP-QUEUE.md's two-agent verdict rule for this milestone's supporting numbers — no
registry flip occurred or was warranted.

## What this does NOT claim

No edge, no CI, no P&L, no kill. S81 is neither alive nor dead — its binding test is built,
sealed and waiting on a population. The registry row is unchanged at `binding-test-defined`.
The S80 milestone of Q56 is untouched.

## Owed next

1. A settlement backfill for the 280 unjoinable crypto-hourly event tickers (collector
   milestone, public endpoint, bounded byte budget — the Q52 phase-1 pattern). This is the
   single action that opens the gate.
2. Q56's S80 milestone, which is independent of all of the above.
