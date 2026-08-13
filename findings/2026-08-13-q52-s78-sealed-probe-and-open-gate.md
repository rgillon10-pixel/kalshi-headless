# Q52 / S78 — the binding test is now WRITTEN AND SEALED, and its data gate is OPEN

*2026-08-13 · research loop, IDLE RUN, idle-run policy (b) ("write + offline-test the probe
script for the NEXT gated queue item so it fires the day its gate opens") · producer: main
context · **no independent `verifier` was dispatchable in this harness** (tools available:
Read/Grep/Glob/Bash — no `Task`/subagent tool; the L287/L288/L290/L291/L295/L308/L313/L325
precedent chain), so the sanctioned redundancy fallback ran instead and is reported as
redundancy, never as verification.*

**Nothing here is a verdict.** No settlement result's VALUE was read, no return was computed,
no CI exists, no registry status changed. S78 stays `collect-and-revisit`, S11 stays
`data-collecting`, the project still has 0 proven edges.

---

## 1. Why this, and why now

Q52 has sat DATA-GATED since 2026-08-05 with **no probe script at all**. Its registration
carries three mandated tightenings from the round-#23 verifier, and the FIRST of them is a
statement about *when* the design may be chosen, not about what it is:

> (1) pre-register a COLLAPSED cell design (continuous toxicity score, or ≤4 pre-declared
> cells e.g. favorite/dog × wide/tight) **BEFORE seeing holdout markout** — else L41's
> luckiest-cell failure (600 naive cells ≫ the units that exist).

A design chosen *after* the tape is adequate cannot satisfy that mandate by assertion, only
by trust. Choosing it while the answer is still unknowable, and sealing it behind a hash, is
the only way the mandate can be **met** rather than merely claimed. This is the same
discipline `scripts/q54_s79_flow_continuation_probe.py` was built under on 2026-08-08.

## 2. What was built

**`scripts/q52_s78_toxicity_filtered_maker_probe.py`** (+36 offline tests in
`tests/test_q52_s78_toxicity_filtered_maker_probe.py`) — the sealed pre-registered probe.

`PREREG_SHA256 = 1c2e422876ce44f5f8217dc98b4a7d8a43c9fcca04b1d8ddd1e8d3ff5bb218c2`, pinned by
`tests/test_q52_s78_toxicity_filtered_maker_probe.py::test_preregistration_digest_is_pinned_to_the_sealed_spec`.
Any later edit to a spec constant breaks that test loudly, so tuning-after-seeing-an-answer
cannot be a quiet diff.

The seal is structural, not cosmetic:

* `population_report()` never receives, reads or returns a settlement `result`. Settlement
  membership comes from `settled_ticker_set()`, which collapses each result through
  `is_binary_result(...) -> bool` — the LABEL CLASS, never the direction.
* `outcome_map()` (the only function that reads a result's VALUE) and `score_rows()` (the
  only one that computes a return) are unreachable from `run()` unless
  `population_report()["admissible"]` is True.
* `sealed_report_key_violations()` asserts, key by key, that no settlement-derived field
  reached a sealed report. On the real tree it returns `[]`.
* The fill model, ticker grammar and loaders are **imported** from the S80 probe rather than
  re-declared (L100) — `P.print_consumes is S80.print_consumes` is test-pinned, because a
  second copy of the orientation predicate is exactly how L279's bug survived its first
  repair.

### The pre-registered spec, in one paragraph

Unit = GAME (L6). Universe = sports `*GAME` markets with ≥1 `broker_truth` print, ≥2
`orderbook_depth` snapshots and a binary settlement from any declared
`core.settlement_sources` family (L300). The **toxicity anchor** is the maker's realized
30-minute markout: `taker_book_side` names the side the TAKER'S order sat on (L279), so a
taker on the bid is a BUYER and the maker holds NO at `1-p`; the mark is the LAST print in
`(t, t+30min]`, and a print with no later print inside the horizon is UNSCORED, never zero.
**Four collapsed cells**, both axes observable EX ANTE at rest time (a cell a maker cannot
see before resting is not a filter, it is hindsight): maker's own price `rich`/`cheap` at
$0.50, quoted spread `wide`/`tight` at $0.03 (mechanism, not a fit — the maker fee at
mid-price rounds up to $0.01, so two ticks is bare break-even and three is the first spread
leaving a full tick of gross capture). Train/holdout split is a RULE, not dates: the
committed trade days sorted ascending, TRAIN = first `floor(N/2)`, HOLDOUT = the rest, with a
game assigned by its earliest print day and any **straddling game dropped from both** —
mandate (2) is disjointness of populations, not of calendars. A cell is admitted iff it
carries ≥30 train prints AND its mean train markout **strictly** exceeds
`fee_per_contract(mean train maker price, MAKER_FEE_RATE)`. Holdout candidates rest at the
snapshot's own touch bid (`real_bid`) inside `[0.02, 0.98]`, in admitted cells only, over
snapshot intervals ≤240 min; fills are **queue-aware** (cumulative consuming `broker_truth`
print volume must strictly exceed the displayed queue at or better than our price) and every
fill returns the crossing print's `trade_id`. Exit = hold to venue settlement. Cost = ONE
maker fee at fill via `core.pricing` (`TAKER_FEE_RATE` appears nowhere in the module, and
that absence is test-pinned). Headline branch = `all_candidates` (an unfilled candidate
scores an honest $0.00), with `conditional_on_fill` beside it. Verdict = block bootstrap by
GAME, n_boot 10,000, seed 42, on the HOLDOUT only; ALIVE only if the CI is strictly > 0 AND
clears one tick (L27), admissible via `bootstrap_verdict_admissible(min_units=10)` (L41) and
`sign_variation_admissible(min_exclusive_minority_units=2)` (**L321's EXCLUSIVE count**, the
first probe in this repo built against that rule from the start rather than retrofitted).

## 3. The measurement — Q52's data gate is OPEN for the first time

All of the following is **outcome-blind**: it was produced by the sealed probe's own
`population_report()` path, with `outcome_map()` and `score_rows()` never called.

**Split** (6 committed trade days): TRAIN `2026-07-07 / 07-08 / 07-10`, HOLDOUT
`2026-07-11 / 07-12 / 08-03`. 72 games total → **21 train / 40 holdout / 11 straddling games
dropped**. 87 sports `*GAME` tickers carry prints; 87/87 carry a book.

**TRAIN cell table** (markout is print-vs-print, `price_source_tag: broker_truth`; fee is the
MAKER rate 0.0175 via `core.pricing`):

| cell | n train prints | mean markout | mean maker price | maker fee | net of fee | admitted |
|---|---|---|---|---|---|---|
| `cheap/tight` | 52,738 | **+$0.06861** | $0.2264 | $0.01 | **+$0.05861** | **YES** |
| `cheap/wide`  | 2,717  | −$0.04419 | $0.1658 | $0.01 | −$0.05419 | no |
| `rich/tight`  | 62,560 | −$0.06159 | $0.7741 | $0.01 | −$0.07159 | no |
| `rich/wide`   | 2,422  | **+$0.06714** | $0.7660 | $0.01 | **+$0.05714** | **YES** |

Read the direction carefully, because the sign is the whole L279 wall. A `cheap` maker
position at a mean price of $0.226 is, for the taker-buy prints that dominate this tape
(80/20, L279), a maker who **sold YES at a high price** — i.e. sold the FAVOURITE — and the
positive markout says the YES price then fell. `rich/tight` is its mirror: a maker who sold
YES cheaply (sold the LONGSHOT) and watched it rise. That is directionally consistent with
S80's own K1 leg, which measured the LEADING side's prints as $0.169 ABOVE settlement-fair
and the trailing side's $0.153 BELOW — retail overpays what it is buying. It is NOT
independent evidence of anything: it is the same venue, the same family, the same tape.

**HOLDOUT population**: **434 candidates → 362 scoreable** (on a settled ticker) → **21
fills (5.80%)** across **34 bootstrap units (games)**, against the L41 floor of 10.
Sign variation (L321, EXCLUSIVE count): minority side `yes`, **5 exclusively-minority units**
against a floor of 2; touching counts 29 `no` / 28 `yes`, exclusive 6 `no` / 5 `yes`.
Settlement coverage: 40 candidate tickers requested → **34 binary** (`q51_settlement_cache`
32, `settlement_ledger` 2), 5 non-binary, 1 listed-unsettled, 6 unresolved.

**`gate_reasons: []`, `admissible: true`.** Every gate the sealed spec declares — an admitted
cell, a scoreable population, the 10-unit floor, a non-zero fill count, the exclusive
minority floor, and a real train/holdout split — is open at once, for the first time since
S78 was registered on 2026-08-05.

## 4. What was deliberately NOT run

**The scoring half.** It is verdict-class: it produces a bootstrapped CI destined for `kb/`,
and LOOP-QUEUE's two-agent rule requires the producer AND an independent `verifier` re-run
before such a number may be committed as anything but PROVISIONAL. No `Task`/subagent tool
exists in this harness, so the rule is **unsatisfiable this run**, and the honest response is
to leave the sealed probe unfired rather than to bank an unverifiable number. This is exactly
what the 2026-08-08 Q54 status did in the same situation, and firing it costs nothing later:
`python scripts/q52_s78_toxicity_filtered_maker_probe.py` with no flags scores automatically
now that the gate reads admissible.

**One honest expectation, stated in advance so it cannot be claimed as a prediction
afterwards.** The fill rate is **5.80%** — an order of magnitude above S19's 0.45%
dead-thin floor, but an order of magnitude below S80's 69.4% on a signal-triggered
population. The headline `all_candidates` branch is therefore ~94% exact zeros, which shrinks
a bootstrap toward the origin; and the nearest cousins in this factor family (S13, S23, S79,
S80's mirror leg) are all dead or straddling zero. The registered presumptive outcome here is
a **kill**, and the probe was built to make that kill honest rather than to avoid it.

## 5. Redundancy leg (NOT verification) — and the defect it caught

**`scripts/q52_s78_population_rederive.py`** (+28 tests) re-derives every number in §3 from
scratch, sharing no code with the probe: its own JSONL readers, its own hand-rolled ISO-8601
parser and Hinnant civil-date arithmetic (no `datetime` module at all), its own game key, its
own orientation statement, a linear-scan book join instead of a bisect, its own queue-aware
fill loop, its own round-up-to-cent fee FORMULA, and a settlement read that goes straight at
the committed cache/ledger files instead of through `core.settlement_sources`. Its
independence stops at exactly one line, and the gate is what stopped it: the first draft
restated the maker RATE as a `0.0175` literal and tripped the GATING `no_handrolled_fee_rate`
invariant (L5 — the 4x maker/taker overcharge that sank an S13 draft). The invariant was
obeyed, not relaxed: the rate is now imported from `core.pricing`, which is correct — a
schedule rate is a venue FACT with one sanctioned site, while the rounding formula is the
part an independent implementation can actually get wrong. **Every load-bearing number
agrees**: the split (21/40/11), all four cell counts and means to 1e-9, the admitted set, 434
/ 362 candidates, 21 fills, 34 units, 5 exclusive-minority units.

It did not agree on the first attempt, and the disagreement was worth more than the
agreement. The first draft disagreed on 163 `cheap` and 96 `rich` train prints — **exactly**
compensating, so both totals still read 120,437 — and on the holdout's per-side unit census
(6 vs 5 exclusive-minority units, which flipped which side was the minority). Cause:
`0.71 - 0.68` is `0.029999999999999916` in binary floating point. The probe's
epsilon-tolerant `>= 0.03 - 1e-9` calls that a genuine three-cent spread WIDE; the
re-derivation's exact `>= 0.03` called it TIGHT. Since the two admitted cells are DIAGONAL
(`cheap/tight`, `rich/wide`) and the two price buckets inside one snapshot are complementary
(a cheap YES touch implies a rich NO touch), every flipped interval swapped one candidate out
and its opposite-side twin in — which is why the totals matched while the side census did
not. The probe's convention is the correct one on a venue quoted in whole cents; the
re-derivation now uses it, with `--exact-boundary` retained so the discovery stays
reproducible, and `tests/test_q52_s78_population_rederive.py::test_cell_boundary_epsilon_is_the_documented_float_trap`
pins it. New lesson **L347** (renumbered from L345 during merge — a concurrent research-loop
firing, PR #364, independently claimed L345/L346 for an unrelated Q52/S78 split-feasibility
finding the same day; see `kb/00-LOG.md`'s 09:3x-11:xx entry and `kb/lessons/00-lessons.md`).

## 6. Scope, limits, and what this does not license

* **No verdict, no CI, no P&L, no registry flip.** S78 stays `collect-and-revisit` at
  confidence `low`. What changed is Q52's runnability, not S78's standing.
* Prices: rest = `real_bid` (read off the committed ladder), fill evidence and toxicity
  signal and settlement = `broker_truth`. No synthetic price appears anywhere, and a fill
  against one is unconstructible — the fill predicate reads a print or returns False.
* The book cadence ceiling is real: 240-minute intervals are admitted, and L328 measured p75
  at 179.5 min, so a meaningful share of holdout intervals are hours wide. Queue position
  inside such an interval is unmeasurable; the queue-aware rule is conservative about that
  (it requires the whole displayed queue to clear) but it is not a substitute for a
  trade-cadence book (Q47).
* Same factor family as S13 / S23 / S79 / S80 (short the chased/favoured side, negative
  skew). If this ever graduated alongside one of them they would share one factor
  allocation — recorded here so a future graduation memo cannot miss it.
* 11 of 72 games were dropped as straddlers. That is a real 15% cost of enforcing population
  disjointness, paid deliberately.

## 7. Reproduce

```
python scripts/q52_s78_toxicity_filtered_maker_probe.py --population-only --no-write --json
python scripts/q52_s78_population_rederive.py --json
python scripts/q52_s78_population_rederive.py --exact-boundary   # reproduces §5's mismatch
```

Both are read-only and offline (`network_calls: 0` on both reports).
