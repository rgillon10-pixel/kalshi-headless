# Q54 / S79's probe, sealed before its gate — and the third gate condition nobody had counted

**Date:** 2026-08-08 · **Run:** research loop, IDLE RUN, idle-run policy (b) (write + offline-test
the probe for the next gated queue item so it fires the day its gate opens)
**Queue item:** Q54 (S79 aggressor-flow continuation taker) — DATA-GATED, `collect-and-revisit`
**Verdict class:** NONE. This is a **pre-registration + data-adequacy** finding. No P&L, no mean,
no bootstrap, no CI, no kill decision, no registry flip. S79 keeps `collect-and-revisit`; S78 and
every other row are untouched. Still 0 proven edges.
**Two-agent rule:** N/A (nothing verdict-class) **and not satisfiable** — no `Task`/subagent tool
exists in this harness (Read/Grep/Glob/Bash only), the L287/L288/L290/L291/L295 precedent. The
sanctioned redundancy fallback ran instead and is reported as such, never as a verifier.
**Prices:** every price touched here is `broker_truth` (executed prints). No quote, no midpoint,
no synthetic value appears anywhere in the instrument.

## Why this was the run's work

The queue is drained; policy (a) has no eligible row (all 5 open UNENFORCED lessons are out of
lane or self-deferred). Policy (b) says: prep the next gated item. The obvious candidate, Q51
milestone 3 (time-gated 2026-08-10), has been pre-flighted three times already — 08-05 settled its
population, 08-08 settled its fill projection (L308/L309). The *un*-prepped gated items are Q52
(S78) and Q54 (S79): both were registered by the edge-hunter with a written binding test, and
**neither has a probe script**. Between them Q54 is the one whose gate is nearest — its own Status
line puts it at 9 settled game units against the L41 floor of 10, i.e. one game away.

There is also a reason this prep cannot wait for gate day. Both items' binding tests mandate
**pre-registration** ("pre-register horizon+entry BEFORE returns", Q54; "pre-register a COLLAPSED
cell design BEFORE seeing holdout markout", Q52). A pre-registration written on the day the data
arrives is not a pre-registration. Today is the last cheap moment to write it.

## The instrument

`scripts/q54_s79_flow_continuation_probe.py` (read-only, fully offline, no network — settlement
comes from committed tape via `core.settlement_sources`, the 9-family registry from L300) +
`tests/test_q54_s79_flow_continuation_probe.py` (**41 tests**) ->
`reports/q54_s79_flow_continuation.json`.

**The pre-registered spec** (locked 2026-08-08, digest
`3f56818136b97206…`, pinned by `test_preregistration_hash_is_sealed`): unit = GAME (L6); universe =
`*GAME` sports moneylines, KXMVE* excluded (L31); decision instants on the whole UTC hour; signal =
net signed YES flow over the preceding 30 min (`+count` for a BUYING taker, `-count` for a selling
one — the L279 orientation, imported from `scripts/q51_maker_fillsim.py` rather than restated);
entry gate |flow| >= 10 contracts; entry = the first agreeing print within 5 min, at its executed
price (`broker_truth`); price band [0.02, 0.98]; exit = hold to settlement; cost = **one** taker fee
from `core.pricing` (never a literal, L5); verdict via `bootstrap_verdict_admissible(min_units=10)`
+ `clears_tick_magnitude` (L41/L27), block-bootstrapped by game.

Only the **hold-to-settlement, single-fee** variant is built. The seconds-to-minutes round trip
Q54 also names is not: `tape/orderbook_depth/` gives 4 captures/day on the one committed trade day
(the S9 cadence wall), so there is no fillable exit surface at that horizon and inventing one would
be a synthetic fill price. Note what the single-fee variant does to S79's registered KILL prior —
it removes one of the two fee legs that prior leans on, which makes the test *fairer*, not weaker.

### The seal: a probe built early must be unable to peek

The committed tape today can already produce the 8-game answer. A probe that computed it and then
printed "INSUFFICIENT DATA" would have spent the pre-registration it exists to protect: whoever
later picked the lookback, the threshold or the band would be picking them having seen the returns.
So the refusal is structural, and four things enforce it:

1. `population_report()` never receives a settlement `result`. Membership comes from
   `settled_ticker_set()`, which collapses each result through `is_binary_result(...) -> bool` —
   the label CLASS, never the direction.
2. `outcome_map()` (the only function that reads a result's value) and `score_rows()` (the only one
   that computes a return) are unreachable from `run()` while the gate is shut.
   `test_sealed_run_never_reads_an_outcome_value` monkeypatches both to raise and runs the probe.
3. `sealed_report_key_violations()` walks every key of the emitted report and requires none to
   carry an outcome-derived field. The check is KEY-level on purpose: a substring scan of the
   serialized blob flags the gate note's own prose, and a guard that over-reports gets disabled
   (L155). `test_sealed_key_violation_detector_actually_fires` pins that it is not vacuous.
4. The spec is hashed. Editing a constant breaks a test loudly, so tuning-after-seeing-data cannot
   be a quiet diff.

## The measurement (outcome-blind, on committed tape)

Running the sealed spec over `tape/kalshi_trades/dt=2026-08-03.jsonl` (the only committed trade
day; 39,698 prints, 42 tickers):

| quantity | value |
|---|---|
| sports `*GAME` tickers with prints | **38** |
| entry candidates enumerated | **82** |
| … of which land on a settled market | **67** |
| bootstrap units (games) among them | **8** (floor 10) |
| YES-side candidates / NO-side | **77 / 5** |
| **NO-side candidates on a SETTLED market** | **0** |
| settlement sources contributing | `q51_settlement_cache` 9, all other 8 families 0 |

Two facts fall out, and the second is the finding.

**(a) The gate is 2 units away, not 1.** Q54's Status line reads the distance off the settlement
census: 9 resolved binary games. But a settled game only becomes a bootstrap unit if it also yields
a pre-registered entry, and one of the nine (`KXLIGAMXGAME-26AUG02AMESLA-TIE`, 2,304 prints) has a
print span so short it produces a single decision instant and no qualifying entry. Settled-market
count over-states runnable-unit count. This is the same class as the 2026-08-03 Q37 finding ("the
gate counts the wrong unit") and the L289/L296 mixed-unit class — a gate distance quoted in the
wrong denominator.

**(b) The scoreable population has ZERO sign variation.** All 67 entries that could be scored are
on the same side. The 5 NO-side candidates the tape produces belong to two games that have not
settled. On the population a verdict would actually be computed from, S79's conditioning variable
is **constant**: the strategy degenerates to "buy YES whenever 30-minute net flow clears 10
contracts", and any CI would be evidence about buying YES sports moneylines, not about signed flow.

This is not a one-day accident. L279 measured the venue's flow asymmetry directly on this same
tape: **31,831 buy prints vs 7,867 sell prints (80/20)**, because retail overwhelmingly buys in
prediction markets. A net-flow signal aggregated over a 30-minute window is therefore positive
nearly always for structural reasons that more days of tape do not remove. Q54 names two gate
conditions (settled units < 10; no fillable seconds-to-minutes exit book). **This is a third, and
it is the one a longer tape is least likely to clear on its own.**

Because the discovery was outcome-blind, acting on it now is legitimate rather than tuning, so it
was converted into a gate rather than a note: `min_minority_side_units = 2` is part of the sealed
spec, and the probe refuses on `no_sign_variation` exactly as it refuses on `below_min_units`. Two
distinct minority units, not one, because a minority arm concentrated in a single game cannot be
block-bootstrapped at all — L41's own logic applied to the signal instead of to the outcome.

**Binding mandate for whoever fires this** (pre-registered here, before any outcome is visible; the
Q52 "mandated tightenings" precedent): if the sign gate ever opens, an ALIVE reading is **not**
admissible on the headline CI alone. The primary must be decomposed against an
always-majority-side benchmark on the identical entry instants and prices, and the **paired
per-unit difference** must itself clear a block-bootstrap-by-game CI > 0. Otherwise a majority arm
that is 90%+ of the population carries the verdict while the minority arm — the only identifying
variation S79 claims — contributes nothing. That decomposition is deliberately not built today: it
cannot be exercised against a population with zero minority-side entries, and shipping an
untestable second scoring arm adds verdict surface (L41) without adding evidence.

## Redundancy (not verification)

`test_committed_day_reproduces_on_an_independent_code_path` re-derives the whole entry population
from the raw JSONL on a separate path — integer cents instead of floats, its own window
arithmetic, orientation constants as locals rather than imports — and requires exact agreement.
It agrees on **38 tickers / 82 candidates / 5 NO-side / 67 settled / 8 units / 0 minority units,
0 disagreements**. Zero disagreement cannot catch an error the two paths share (the L279 failure
mode); it catches the transcription and off-by-one class, and that is all it is claimed to catch.

## What this does and does not change

- **Does not** change S79's status, any registry row, or any verdict. Nothing here is verdict-class.
- **Does** add a third, enforced condition to Q54's gate, and correct its stated distance from 1
  unit to 2.
- **Does** leave a probe that self-activates: it globs every committed trade day rather than
  pinning a DAY constant, so a new day flips the gate without an edit. The live-tape test asserts
  the unit count as a **floor** (`>= 8`) precisely so it does not red-line on the event it is
  waiting for.
- Q52 (S78) still has no probe and still owes its own pre-registration — the natural next unit of
  policy-(b) work, and it is strictly harder (its gate needs disjoint train/holdout windows, which
  one trade day cannot supply).

## Files

- `scripts/q54_s79_flow_continuation_probe.py`
- `tests/test_q54_s79_flow_continuation_probe.py` (41 tests)
- `reports/q54_s79_flow_continuation.json`
- `kb/lessons/00-lessons.md` (L311, L312)
- `LOOP-QUEUE.md` (Q54 Status), `kb/00-LOG.md`
