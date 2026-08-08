# Q51 milestone 3, two days before its gate: 70% of the legs it will score can never fill

**Date:** 2026-08-08 · **Run:** research loop, IDLE RUN, idle-run policy (b) (build + offline-test
what the NEXT time-gated queue item needs so it fires correctly on its day)
**Queue item:** Q51 milestone 3 (time-gated to **2026-08-10**, two days out)
**Verdict class:** NONE. This is a **data-adequacy / instrument** finding. No P&L, no mean, no
bootstrap, no CI, no fill rate quoted as an edge, no registry flip, no kill decision. S13/S23/S29
keep the status they already had. Still 0 proven edges.
**Two-agent rule:** N/A (nothing verdict-class) **and not satisfiable** — no `Task`/subagent tool
exists in this harness (Read/Grep/Glob/Bash only), the L287/L288/L290/L291/L295 precedent. The
sanctioned redundancy fallback ran instead and is reported as such, never as a verifier.

## Why this was the run's work

`scripts/q51_m3_preflight.py` (2026-08-05) settled milestone 3's **population** question — an
08-10 firing buys **44 game units / 128 intervals / 256 legs**, 4x the L41 floor of 10, so FIRE ON
08-10 AS GATED. It did not ask, and nothing else has asked, the question that decides how the
result must be *read*:

> of those 256 legs, how many can ever **fill**?

That question is answerable **today and outcome-independently**, because a fill in
`scripts/q51_maker_fillsim.py` is decided by BOOK + PRINTS alone: `yes_bid_fill` / `no_bid_fill`
read `tape/orderbook_depth/` and `tape/kalshi_trades/` and never touch the settlement cache.
Settlement decides only *which* legs are scored and whether a filled leg *won* — and `won` is
exactly what this instrument refuses to compute. Every count below is therefore fixed by
already-committed tape and cannot move on 08-10.

## Instrument

`scripts/q51_m3_fill_projection.py` (read-only, fully offline, no network) +
`tests/test_q51_m3_fill_projection.py` (**29 tests**) -> `reports/q51_m3_fill_projection.json`.

It **imports** `scripts/q51_maker_fillsim.py` rather than reimplementing it, so the projection
cannot drift from what will actually run on 08-10 (milestone 3's spec requires that file to run
UNCHANGED, and nothing here changes it). Settlement is read for **`close_time` only** — a schedule
field, never a result. `test_acceptance_report_is_outcome_independent` pins that the emitted report
contains no `pnl` / `ci95` / `won` / `settle_result` token, and
`test_acceptance_no_leg_record_carries_an_outcome_or_a_pnl` pins the same on every leg record.

## The measurement (source tags: rest price `real_bid`, fill evidence `broker_truth`, `close_time` `broker_truth`)

Cumulative by close day over the committed `dt=2026-08-03` slice and the FROZEN
`tape/q51_settlement_cache/settlement-m2-2026-08-04.json`:

| fire date | markets | units | intervals | covered | coverage | ALL legs | ALL fills | **ALL fill rate** | COVERED legs | COVERED units | **COVERED fill rate** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-04 | 8 | 8 | 23 | 20 | 0.870 | 46 | 31 | **0.6739** | 40 | 7 | **0.7750** |
| 2026-08-09 | 41 | 41 | 119 | 62 | 0.521 | 238 | 76 | **0.3193** | 124 | 26 | **0.6129** |
| **2026-08-10** | **44** | **44** | **128** | **62** | **0.484** | **256** | **76** | **0.2969** | **124** | **26** | **0.6129** |
| 2026-08-12 | 54 | 54 | 158 | 65 | 0.411 | 316 | 78 | **0.2468** | 130 | 28 | **0.6000** |
| 2026-08-23 | 57 | 57 | 165 | 67 | 0.406 | 330 | 79 | **0.2394** | 134 | 29 | **0.5896** |

Cross-checks that had to hold and did: the 08-10 row reproduces the pre-flight's population
exactly (44 units / 128 intervals / 256 legs), and its `n_covered_intervals = 62` /
`n_fills = 76` reproduce **exactly** the two quantities L284 measured against a synthetic 08-10
cache from a different direction. Independent redundancy path (own integer-cent comparison, own
window convention, orientation passed as arguments rather than module constants): **330/330 legs
cross-checked, 0 disagreements**. That is a redundancy check, NOT a verifier — both paths read the
same tape and share L279's orientation premise, so an error in that premise is invisible to it.
Stated plainly because the milestone-2 run's own redundancy check made exactly this mistake.

## Finding 1 — milestone 2's 65.0% fill rate is a property of the SETTLED SUBSET, not of the mechanism

On 2026-08-04 the only markets that had settled were the games **played on 2026-08-03** — which
are precisely the markets that **traded on 2026-08-03**. The headline `all_intervals` branch
therefore measured its fill rate on the most active slice the tape has. As settlement extends to
games played 08-04..08-09, whose 08-03 snapshots are pre-game and whose 08-03 prints are sparse:

* headline (`all_intervals`) fill rate **0.6739 -> 0.2969**, a **2.27x compression**;
* conditional-on-coverage fill rate **0.7750 -> 0.6129**, only **1.26x** — it barely moves.

The entire collapse is a **coverage** effect, not a change in fill behaviour. Interval coverage
falls 0.870 -> 0.484 over the same population. Only the covered-branch number is comparable across
populations; the headline number is not, and comparing milestone 2's 65.0% with milestone 3's
~29.7% as if they measured the same thing would be a category error.

## Finding 2 — how the 08-10 headline must be read

On the `all_intervals` branch an unfilled leg contributes an **exact 0.0**, so the reported mean
obeys the arithmetic identity

```
mean_over_all_legs == (n_fills / n_legs) * mean_over_FILLED_legs
```

At 76/256 that multiplier is **0.297**, so **180 of 256 legs (70.3%) contribute exactly zero by
construction**, and any per-fill edge is compressed **2.27x** *before* the L27 one-tick magnitude
gate is applied to it. This report deliberately **does not** multiply that multiplier by any
per-fill edge: that product would be a P&L forecast — outcome-dependent, verdict-class, and not
this instrument's lane.

The operational consequence, stated as a reading rule and not as a prediction: an 08-10 headline
that lands at or below the tick gate is **not** by itself evidence about the mechanism, because the
same arithmetic would produce it from an unchanged per-fill edge. The **`covered_intervals`
sensitivity branch clears the L41 floor for the first time at the 08-10 firing (26 units, up from
milestone 2's 6)**, so for the first time BOTH branches are admissible by unit count and the
conditioning that made the sensitivity branch untrustworthy at n=6 is no longer the binding
objection. Both should be read; neither alone.

Side split at 08-10 (diagnostic, `real_bid` / `broker_truth`): YES-bid 22/128 = **17.2%**, NO-bid
54/128 = **42.2%** — the same ~2.5x asymmetry milestone 2 saw (45.0% / 85.0%), scaled down by the
common coverage factor, and consistent with L279's ~80%-buying flow.

## Finding 3 — the second sweep after 2026-08-24 buys units, not evidence

Marginal counts between consecutive fire dates:

| from -> to | Δ legs | Δ fills | Δ units | marginal fill rate |
|---|---|---|---|---|
| 08-04 -> 08-09 | 192 | 45 | 33 | 0.234 |
| 08-09 -> 08-10 | 18 | **0** | 3 | **0.000** |
| 08-10 -> 08-12 | 60 | **2** | 10 | **0.033** |
| 08-12 -> 08-23 | 14 | **1** | 3 | **0.071** |

**76 of the 79 fills the committed tape will ever supply are already in the 08-10 population.**
Waiting past 08-10 adds 74 legs and **3** fills. The queue's planned "second sweep after
2026-08-24" therefore buys 13 more resample units made almost entirely of legs that cannot fill —
which on the headline branch *lowers* the multiplier further (0.297 -> 0.239). Its real value is
the covered branch (26 -> 29 units) and settlement variety, not fill evidence. Re-scoping only; it
refutes nothing and changes no gate.

## Finding 4 (secondary) — `build_rows`'s `drops` dict mixes units

`scripts/q51_maker_fillsim.py::build_rows` (lines 364-398) increments five keys in **intervals**
(`no_settlement` / `non_binary_result` / `unsettled` `+= len(ss) - 1`; `post_close` /
`not_two_sided` `+= 1` inside the per-interval loop) and one key, `single_snapshot`, in **tickers**
(`+= 1` in the per-ticker loop, for a ticker that contributes **zero** intervals). The dict is
emitted under `report["intervals"]` next to `n_intervals`, which invites reading every value as an
interval count and summing them; `sum(drops.values())` is a count of nothing. Milestone 2's
published `{single_snapshot: 3, unsettled: 145}` is 3 tickers plus 145 intervals. Same defect class
as L289/L296 (a counter whose denominator means two different things). **Reported, not repaired** —
milestone 3's spec requires the probe to run UNCHANGED. `drops_unit_audit()` states it in the
report so the 08-10 reader is not misled, and a test pins the audit.

## Calibration — the upper-bound claim is measured, not asserted

This module buckets a market by `close_day <= fire_date`; milestone 2's probe bucketed it by
whether the venue had published a binary `result` at the 08-04 pull. Those are different
predicates, and the gap between them IS the settlement lag the projection calls an upper bound.
Measured against the committed milestone-2 report, every delta is non-negative — intervals +3,
covered +3, legs +6, fills +5, units +1 — so the direction is **over-inclusive**, exactly what an
upper bound must look like. A negative delta would have falsified the bound; the code reports that
case as `MIXED` and a test pins it.

## What this does NOT claim

* No P&L, no mean, no CI, no verdict about S13/S23/S29, and no revival of any strategy.
* No queue-position, time-to-fill or sub-interval adverse-selection number (L283's ceiling).
* No recommendation to modify `scripts/q51_maker_fillsim.py`. The 08-10 recipe from the 08-05
  pre-flight stands unchanged; this adds one step to it — read `covered_intervals` beside the
  headline, and read the headline through its known 0.297 multiplier.

## Reproduce

```
python3 scripts/q51_m3_fill_projection.py     # -> reports/q51_m3_fill_projection.json
python3 -m pytest tests/test_q51_m3_fill_projection.py -q
```
