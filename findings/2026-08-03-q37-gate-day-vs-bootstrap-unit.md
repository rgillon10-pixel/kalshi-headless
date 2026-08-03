# Q37 pre-flight: the gate counts tape-days, the bootstrap eats settled-and-filled days

- **Date:** 2026-08-03 (research loop, IDLE RUN, idle-run policy (b) — prep the next time-gated item)
- **Class:** DATA-ADEQUACY / PRE-FLIGHT. **No CI, no P&L, no fill price, no registry change, no
  kill decision.** Two-agent verdict rule does not apply (and no `verifier` subagent was
  dispatchable in this run's harness — stated, not glossed).
- **Re-run:** `python3 scripts/q37_bootstrap_unit_preflight.py`
- **Lessons produced:** `kb/lessons/00-lessons.md` **L271**, **L272**
- **Status of Q37 itself:** UNCHANGED — still GATED (20 of 21 summer contract-days as of today;
  earliest honest open ~2026-08-04). Nothing here opens, closes, or relaxes the gate.

## The question

Q37 fires the moment `tape/weather_books/` holds >= 21 SUMMER daily contract-days. The 2026-07-31
pre-flight audit asked whether the gate counted the wrong ROWS (it did — phantom non-temperature
series, fixed by tightening). This run asked the next question down: **does it count the wrong
UNIT?**

Falsifiable form: *on committed tape, does the number of contract-days the gate counts equal the
number of contract-days `bootstrap_cut` can actually resample?* If yes, the gate number is a fair
statement of sample size. If no, quoting "21 days" tomorrow overstates the evidence.

## Result: 20 gate-days buy 15 bootstrap units (75% yield)

Measured on committed tape at 2026-08-03 (post step-0b sweep), using the probe's own loaders and
`simulate_group` verbatim — nothing re-derived (L36):

```
contract_day  grps settled  rows  meas  prim primmeas filled  unit  reason
2026-07-15      40      40     0     0     0        0      0  no    incomplete_book
2026-07-16      40      37   158   144   133      122     57  YES
2026-07-17      40      38   154   146   134      126     50  YES
2026-07-18      40      40   159   159   138      138     65  YES
2026-07-19      40      40   156   156   131      131     41  YES
2026-07-20      40      38   158   149   137      130     46  YES
2026-07-21      40      39   154   150   127      124     43  YES
2026-07-22      40      40   160   160   131      131     57  YES
2026-07-23      40      40   154   154   126      126      5  YES
2026-07-24      40      40   160   160   127      127     30  YES
2026-07-25      40      40   154   154   141      141      0  no    zero_fill
2026-07-26      40      40    35    35    30       30      9  YES
2026-07-27      40      40   156   156   130      130     40  YES
2026-07-28      40      40   159   159   146      146     41  YES
2026-07-29      40      33   160   133   151      127     14  YES
2026-07-30      40      40    46    46    37       37      9  YES
2026-07-31      40      39   156   152   138      134     24  YES
2026-08-01      40       0   163     0   136        0      0  no    settlement_lag
2026-08-02      40       0   160     0   136        0      0  no    settlement_lag
2026-08-03      40       0   156     0   120        0      0  no    settlement_lag

GATE DAYS 20  ->  BOOTSTRAP UNITS 15  (deficit 5, yield 75.0%)
  deficit_by_reason={'incomplete_book': 1, 'zero_fill': 1, 'settlement_lag': 3}
  L41 admissibility floor min_ci_units=10  clears=True
```

The deficit is not one thing. It is three, and they behave differently:

1. **`incomplete_book` (1 day, 2026-07-15).** All 40 groups dropped: the first day of tape has no
   book at the strictly-causal decision time `T = close - 24h`. Structural; no amount of waiting
   fixes a day that is already past.
2. **`zero_fill` (1 day, 2026-07-25).** 40/40 groups booked, 40/40 settled, 154 settlement-
   measurable rows — and **0 touches**. This is a real fill-rate fact about the strategy, not a
   coverage defect, and must never be reported as one. (Fill counts across the surviving days are
   wildly dispersed — 65 on 07-18, 5 on 07-23 — so a per-day fill count is itself a thin
   statistic.)
3. **`settlement_lag` (3 days, 2026-08-01/02/03).** `n_groups_settled = 0`: the exchange has not
   settled these contract-days yet (the L262 lag), so every row is correctly DROPPED as
   unmeasurable (L86) rather than zeroed. **This is the load-bearing part.** It is always the
   *newest* gate-days, so it travels with the fire date: whenever Q37 runs, its most recent ~3
   gate-days contribute nothing. Waiting a week moves both numbers by 7 and closes none of it.

### Why it matters tomorrow

When the gate opens (~2026-08-04) the probe will report a 21-day gate while its block bootstrap
resamples **~15–16** units against `MIN_CI_UNITS = 10` (L41). It clears the admissibility floor —
by 5 units, not by 11. Any honest reading of tomorrow's CI has to quote the unit count, not the
gate count. That is now impossible to get wrong by accident: the probe prints both.

## Second finding: L32's dual cut is degenerate here, by construction

`filled_optimistic` and `filled_movement` are the same number on this tape — not approximately,
identically:

```
2,758 rows: touched=674  frozen=379  touched_AND_frozen=0  optimistic=674  movement=674
```

And it cannot be otherwise. `frozen` = the `(yes_bid, yes_ask, no_bid, no_ask)` tuple never changed
across the holding window; `touched` = some later snapshot's `best_no_ask` fell to our resting NO
bid. On a frozen book every later NO ask *equals* the entry NO ask, so a touch would require
`no_ask <= no_bid` — a crossed quote real Kalshi books do not show. The movement condition is
therefore implied by the fill condition and adds zero discriminating power.

This changes no number the probe reports (`OPTIMISTIC_FILL = True` already blocks graduation). It
changes how the report must be **read**: `_verdict()` describes the movement-conditioned cut as
"the honest fill cut", but here it is the optimistic cut wearing a second label. A genuine L32
dual cut needs a movement test independent of the fill test. Recorded as **L272**; the probe now
prints an explicit warning line whenever the degeneracy is measured (measured — a fixture with one
frozen-and-touched row flips the flag to False, and a test pins that).

## What was built (additive only — the gate, population, fill model, fee and CI are untouched)

- `scripts/q37_weather_summer_makerno_probe.py`: `bootstrap_unit_ledger()`,
  `gate_vs_units_summary()`, `dual_cut_degeneracy()`, plus two report blocks that print in the
  ANALYSIS branch only. The INSUFFICIENT-DATA branch is byte-for-byte unchanged, so the gate's
  "no analysis below 21 days" semantics still hold exactly.
- `scripts/q37_bootstrap_unit_preflight.py`: read-only, offline, force-builds the population for
  *counting only* and can never emit a CI or a verdict. It calls the probe's functions rather than
  re-deriving them (L36), so the pre-flight cannot drift away from the probe it is checking.
- `tests/test_q37_weather_summer_makerno_probe.py`: 11 new tests (33 in the file, was 22),
  including a real-tape MONOTONE acceptance pin (L191): `units >= 15`, `units < gate_days`,
  `settlement_lag >= 1`, `touched_and_frozen == 0` — bounds a new tape day cannot break.

## What was NOT done

- The gate was not opened, moved, or relaxed. Q37 stays gated at 20/21.
- No bootstrap was run and no CI computed — deliberately, so this stays outside verdict class.
- The `settlement_lag` deficit is not "fixed": the honest fix is to wait for settlement or to
  invoke `collection/weather_actuals.py --backfill-missing` closer to the fire, both of which are
  scheduling calls, not research calls.
