# Q57(b) / S82 — the cache-anchored retest: the fade-to-YES arm exists only in stale books

`2026-08-17` · research loop (protocol v3) · **PROVISIONAL — no independent `verifier` agent
was dispatchable in this harness** (no `Task` tool; the L287/L288/L290/L291/L295/L308/L313/
L325/L349 precedent). **No registry flip: S82 stays `idea`.** Still 0 proven edges.

## 0. What was asked, and what class of answer came back

Q57's newest status names two reopen paths. This run executed **(b)**:

> "widens the entry anchor to `q51_settlement_cache` as its OWN pre-registered choice (not a
> post-hoc addition) at `sign_variation_admissible`'s real `min_exclusive_minority_units=2`
> floor."

**Verdict class: DATA-ADEQUACY on the verdict cell, plus one admissible NULL on a disclosed
secondary cell.** It is NOT a kill and NOT an edge. Path **(a)** (the ledger anchor at a
15-minute window, once one more settled game lands) is untouched and remains open.

## 1. The seal

`scripts/q57b_s82_cache_anchor_probe.py` carries its own pre-registration,
`PREREG_B_SHA256 = 2d243e274b31eb50…`, pinned by
`tests/test_q57b_s82_cache_anchor.py::test_preregistration_hash_is_sealed`. It was written
and sealed BEFORE the probe was run for the first time.

The sealed Q57 probe was **not edited** — its own hash (`dd80f5973c39…`) still recomputes,
so its seal is intact. This module IMPORTS it and reuses `game_id_of`, `load_prints`,
`load_depth`, `entry_candidates`, `collapse_to_games`, `outcome_map`, `score_rows`, the fee
and the price band verbatim (L36/L102). Exactly two things change, both authorised by the
reopen condition and both test-pinned:

* **DELTA 1** — the close-time anchor is `min(settlement_ledger ∪ q51_settlement_cache)`.
* **DELTA 2** — the sign-variation floor is `min_exclusive_minority_units = 2`,
  `core.bootstrap.sign_variation_admissible`'s real default. The sealed probe used 1, an
  undisclosed relaxation the Q57 verifier round caught.

`test_everything_else_matches_the_sealed_spec` asserts all sixteen remaining spec values are
equal to Q57's sealed ones, so "changed exactly two things" is enforced, not asserted.

## 2. What the wider anchor actually buys (outcome-blind)

| | ledger | cache | union |
|---|---|---|---|
| tickers carrying a `close_time` | 49 | 38 | **87** |

The cache **ADDS 38** tickers and the two families are **disjoint** (`n_tickers_in_both = 0`),
so on this population there is no ledger-vs-cache `close_time` disagreement to measure — the
L360/L361 mutation exposure is real but not observable here. The anchor now covers **87 of
87** traded `*GAME` tickers (72 distinct games); 81 settle binary.

## 3. The three cells

All entry prices are `orderbook_depth` `best_yes_ask`/`best_no_ask`,
**`price_source_tag: real_ask`**, inside the pre-registered `[0.02, 0.98]` band, net ONE
Kalshi taker fee (0.07, `core.pricing`).

| cell | window | max entry lag | units | sides | exclusive minority | mean overround (`real_ask`) | outcome |
|---|---|---|---|---|---|---|---|
| **PRIMARY** `primary_minimal_change` | 120 min | 60 min | **11** | `{no: 11, yes: 0}` | **0** | +0.0222 | **INSUFFICIENT DATA** (single-sided) |
| SECONDARY `secondary_verifier_identified` | 15 min | 240 min | 12 | `{no: 10, yes: 2}` | 2 | +0.0236 | **NOT ALIVE** (CI straddles 0) |
| DIAGNOSTIC `diagnostic_window_only` | 15 min | 60 min | 9 | `{no: 8, yes: 1}` | 1 | +0.0275 | population-only, never scored |

**PRIMARY (the verdict cell).** Widening the anchor alone raises the population past the L41
floor (11 units ≥ 10) but leaves it **single-sided** — every one of the 11 units fades to NO.
At the real floor of 2 the gate refuses, no CI was computed and **no outcome value was read**
(`test_inadmissible_scored_cell_also_never_reads_an_outcome_value` pins that the outcome
reader is unreachable on this branch).

**SECONDARY (disclosed selection exposure).** The Q57 verifier round identified this cell by
searching the population — outcome-blind (unit and side counts only), but a search. It
reproduces to the unit: **12 units, {no: 10, yes: 2}, 2 exclusive-minority**, exactly the
verifier's report. Scored:

> **mean +$0.12083 / 95% CI [−$0.01083, +$0.27833]**, n_units 12, n_obs 12, Kish 12.0,
> 10,000 resamples blocked by GAME, seed 42, entry `real_ask`, one taker fee, hold to
> `broker_truth` settlement. `admissible: true`, `clears_tick_magnitude: false`, fade wins
> 7/12.

The CI **straddles zero** → not an edge under the prime directive, and not a kill either: an
admissible NULL with a positive point estimate, the Q51-m3/S81 class.

## 4. Why the positive point estimate must not be quoted alone

The secondary cell's mean is not spread across its 12 games. Split by the pre-registered
staleness rule (**descriptive, post-hoc**, computed by the independent re-derivation):

| entry book age at fill | n | mean P&L (`real_ask`) |
|---|---|---|
| ≤ 60 min (the pre-registered rule) | 9 | **+$0.005556** |
| > 60 min (only reachable in this cell) | 3 | **+$0.466667** |

All three of the >60-min entries are wins: `KXEKSTRAKLASAGAME-…CRAPSZ` (+$0.40, lag 186.7
min), `KXNWSLGAME-26AUG02DENBOS` (+$0.76, lag 125.5 min), `KXDIMAYORGAME-26AUG02SFEOC`
(+$0.24, lag 125.5 min). Strip them and the cell is +0.6¢/contract — under one tick, i.e.
nothing.

**The load-bearing consequence:** one of the two exclusive-minority (fade-to-YES) units,
`DENBOS`, is itself a >2-hour-stale book. The other, `KXKBOGAME-…KIWKTW` (lag 4.1 min), lost.
So on committed tape the minority arm — the whole reason path (b) exists — is populated only
by relaxing the entry-book age to 2–4× the depth collector's own hourly cadence. That is the
L26/L31 stale-nominal-book signature, not a fill.

## 5. Redundancy, NOT verification

`scripts/q57b_s82_cache_anchor_rederive.py` shares no code with the probe: own JSONL readers,
own ISO→epoch parser (string slicing + `calendar.timegm`, never `core.timeutil`), own
settlement readers straight off the two tape families (never `core.settlement_sources`), own
game-id/series predicates, own flow aggregation, own entry picker, own fee formula re-stated
from Kalshi's rounding rule, own block bootstrap at a **different seed (20260817)**.

It reproduces **exactly**: 87 tickers / 72 games / 81 settled-binary; the anchor 49 + 38 = 87,
0 in both; all three cells' unit counts, per-side counts and exclusive-minority counts; the
scored mean to the last representable digit (`0.12083333333333333`); and an independent-seed
CI **[−$0.0100, +$0.2800]** — same straddle, same conclusion. Cross-implementation agreement
is pinned by four tests. **A second implementation is not a second agent**, so everything here
is PROVISIONAL and owes an independent `verifier` pass before any status moves.

## 6. Disposition

* **S82 stays `idea`.** No flip in either direction. Reopen path (b) is now EXECUTED and
  answered; path (a) is untouched.
* **The blocker moved from analysis to collection.** More `kalshi_trades` days do not fix
  this: what is missing is a **depth capture within ~15 minutes of a game close on games
  whose late taker flow is net-negative**. The hourly `orderbook_depth` cadence gives a
  median entry lag that only clears 60 minutes by luck, and the fade-to-YES arm survives
  only where it does not.
* **Do NOT re-run reopen path (b).** It is decided on committed tape.
* Recommended reopen condition, sharper than the old one: **≥2 independent settled games with
  a net-negative late taker flow AND an in-band `real_ask` YES quote captured ≤15 minutes
  before close.** That is a collector requirement (a close-anchored depth burst), not an
  analysis one.

## 7. Artifacts

* `scripts/q57b_s82_cache_anchor_probe.py` (sealed), `scripts/q57b_s82_cache_anchor_rederive.py`
* `tests/test_q57b_s82_cache_anchor.py` (35 tests)
* `reports/q57b_s82_cache_anchor.json`, `reports/q57b_s82_cache_anchor_rederive.json`
* Lessons **L368**, **L369**
