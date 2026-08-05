# Q51 milestone-3 pre-flight — the 08-10 firing is worth firing, and it would have broken the gate

`research loop` · 2026-08-05 · **IDLE RUN, idle-run policy (b)** (write + offline-test the
work needed by the next time-gated item so it is ready to fire on its day) · **PROJECTION and
tooling only: no P&L, no bootstrap, no CI, no registry flip, nothing verdict-class**

## Verdict (one line)

Firing Q51 milestone 3 on its gate date **2026-08-10 clears the L41 admissibility floor by
4x** — projected **44 game units / 256 legs** optimistically, **41 / 238** if you allow a
full day of settlement lag, against a floor of 10 — but the queue's recorded expectation of
"**~57 game units / ~330 legs**" is the **terminal** row of the projection (reachable only
after the last two markets close **2026-08-23**), not the 08-10 row; and the milestone-3
command as specced would have **turned `pytest -q` RED on the day it fired**, because
`--build-cache` overwrites the settlement cache that three HARD milestone-2 acceptance tests
pin. Both facts were computable offline five days early. The second is now repaired.

Reproduce: `python3 scripts/q51_m3_preflight.py` (offline, read-only, no network) →
`reports/q51_m3_preflight.json`. Pinned by `tests/test_q51_m3_preflight.py` (20 tests).

## 1. Why a pre-flight at all

Milestone 2 returned **DATA-INADEQUATE** on `n_units_games = 7` — below the L41 floor of 10 —
because 49 of the 60 sampled markets were still `active` when the settlement cache was pulled
on 2026-08-04. Settlement **recency**, not the fill leg, is the binding constraint; 145 of the
day's 165 sports intervals died on an unsettled market and **zero** died on a missing
settlement record, a non-binary result (L52), a one-sided book or a post-close entry.

That makes milestone 3 a pure waiting game — and a waiting game has exactly one decision in it:
*when to stop waiting*. The queue answered it with a word ("once the 2026-08-04..08-09 games
have been played") and a market count (44 by 08-09). Neither is the quantity the bootstrap
consumes. The bootstrap consumes **GAME units** (L6), and a market only becomes a unit if it
also carries at least one depth **interval** on the probe's frozen day. This pre-flight computes
that number, for every candidate firing date, from committed tape alone. It is the
`scripts/q37_bootstrap_unit_preflight.py` pattern applied to the next gated item.

## 2. The projection

Population is the probe's own: `q51_maker_fillsim`'s stride-13 sample of
`tape/orderbook_depth/dt=2026-08-03.jsonl`, restricted to sports `*GAME` markets. The
pre-flight imports those helpers rather than re-implementing them, so it cannot drift from
the probe it pre-flights.

* sampled sports markets: **60**
* total intervals (consecutive snapshot pairs): **165**
* markets with >= 1 interval: **57** — **3 can never contribute a unit** no matter how they
  settle, because they carry fewer than 2 snapshots on the frozen day

Cumulative by close day (an interval buys 2 legs: the `yes_bid` leg and the `no_bid` leg):

| close day | markets closed | with >=1 interval | **game units** | intervals | legs | clears L41 |
|---|---|---|---|---|---|---|
| 2026-08-03 | 7 | 4 | 4 | 11 | 22 | no |
| 2026-08-04 | 11 | 8 | 8 | 23 | 46 | no |
| 2026-08-06 | 13 | 10 | 10 | 29 | 58 | yes |
| 2026-08-07 | 26 | 23 | 23 | 68 | 136 | yes |
| 2026-08-08 | 37 | 34 | 34 | 99 | 198 | yes |
| 2026-08-09 | 44 | 41 | 41 | 119 | 238 | yes |
| **2026-08-10** | **47** | **44** | **44** | **128** | **256** | **yes** |
| 2026-08-11 | 51 | 48 | 48 | 140 | 280 | yes |
| 2026-08-12 | 57 | 54 | 54 | 158 | 316 | yes |
| 2026-08-20 | 58 | 55 | 55 | 161 | 322 | yes |
| **2026-08-23** | **60** | **57** | **57** | **165** | **330** | yes |

Candidate firing dates, optimistic (markets closing ON the date count) vs conservative (they
do not — a full day of settlement lag):

| fire date | optimistic units / legs | conservative units / legs | clears L41 conservatively |
|---|---|---|---|
| 2026-08-09 | 41 / 238 | 34 / 198 | yes |
| **2026-08-10 (the gate)** | **44 / 256** | **41 / 238** | **yes** |
| 2026-08-12 | 54 / 316 | 48 / 280 | yes |
| 2026-08-23 | 57 / 330 | 55 / 322 | yes |
| 2026-08-24 (2nd sweep) | 57 / 330 | 57 / 330 | yes |

**Every number above is an UPPER BOUND.** The projection assumes a market whose `close_time`
has passed is FINALIZED with a BINARY result at the pull instant. Settlement lag and L52
non-binary (`scalar`) results can only reduce the count, never raise it. The conservative
column is the honest planning number.

**Correction to the queue's recorded expectation:** the milestone-3 spec's "~57 game units /
~330 legs" is the 2026-08-23 row. Firing on 08-10 buys **44** (optimistic) / **41**
(conservative) — roughly three quarters of it. That is still 4x the floor, so **fire on
08-10 as gated**; the second sweep after 08-24 remains the way to reach the full 57.

**Independent cross-check of the arithmetic.** The 08-10 row predicts 128 intervals. Running
the probe itself against a synthetic post-re-pull cache dated 08-10 produces `n_intervals =
128` and `n_units_games = 44` through its own, entirely separate pipeline. The projection's
roll-up and the probe's population builder agree exactly.

## 3. The firing hazard (found, measured, repaired)

`scripts/q51_maker_fillsim.py --build-cache` — the one command milestone 3 runs —
**overwrites `tape/q51_settlement_cache/settlement.json` in place**. Three HARD acceptance
tests call `run()` on that default path and pin milestone-2 numbers that are functions of it:

* `tests/test_q51_maker_fillsim.py::test_acceptance_headline_verdict_is_data_inadequate_below_min_units`
* `tests/test_q51_maker_fillsim.py::test_acceptance_settlement_recency_is_the_binding_constraint_not_the_fill_leg`
* `tests/test_q51_maker_fillsim.py::test_acceptance_every_real_fill_traces_to_a_broker_truth_trade_id`

Measured offline against a synthetic post-re-pull cache — **population counts only; the
synthetic settlement results are invented, tagged `synthetic`, and no outcome-dependent
number is computed from them or may ever be quoted**:

| pinned quantity | committed cache (2026-08-04) | after a simulated 08-10 re-pull |
|---|---|---|
| `n_units_games` | **7** (asserted `== 7`) | **44** |
| `n_intervals` | **20** (asserted `== 20`) | **128** |
| `n_covered_intervals` | **17** (asserted `== 17`) | **62** |
| `drops["unsettled"]` | **145** (asserted `== 145`) | **37** |
| `n_fills` | **26** (asserted `== 26`) | **76** |

All five move. The three tests fail. `pytest -q` is a gate on every commit, so the milestone
would have been blocked by its own success — and it would have been blocked at the worst
possible moment, with a freshly overwritten cache and no committed copy of the input that
produced the milestone-2 numbers still on disk.

The deeper defect is that those tests cite **L191** ("pin acceptance numbers to a slice that
cannot grow") while pointing at a file that a documented future command rewrites. The tape
day files they also read genuinely cannot shrink; the settlement cache was never frozen at all.

**Repair (minimal, and the probe is untouched — milestone 3's spec says it stays UNCHANGED):**

1. `tape/q51_settlement_cache/settlement-m2-2026-08-04.json` — a byte-identical immutable
   snapshot of the milestone-2 cache (`sha256 60d381e5...eba0a`, identical to the live file).
   The live `settlement.json` is **not modified and not deleted** (append-only discipline).
2. Those three tests now pass `cache_path=M2_CACHE` explicitly. The two SHAPE tests
   (`test_module_computes_no_queue_position_or_time_to_fill_number`,
   `test_report_states_the_resolution_ceiling_explicitly`) deliberately stay on the **live**
   cache, so the post-re-pull report is still structure-checked.
3. A new `test_acceptance_frozen_m2_cache_is_the_milestone_2_input` pins the snapshot's own
   identity (pull instant, 60 tickers, 49 `active` / 10 `finalized` / 1 `closed`, 4 `yes` /
   6 `no`), so a later edit cannot swap the file and silently re-baseline the numbers.

**The repair is verified, not asserted.** The live cache was temporarily replaced with a
simulated 08-10 re-pull and the full `tests/test_q51_maker_fillsim.py` file re-run: **42/42
green**, then the live cache restored byte-identical. Before the repair the same simulation moves all five
pinned quantities, i.e. three of the then-41 cases fail by arithmetic (`n_units_games == 7`
vs 44, `n_intervals == 20` vs 128, `n_fills == 26` vs 76).

## 4. What milestone 3 should now do on 2026-08-10

1. `python3 scripts/q51_m3_preflight.py` first — re-run the projection against whatever the
   tape looks like that day and confirm the conservative unit count still clears the floor.
2. `python3 scripts/q51_maker_fillsim.py --build-cache` (one read-only unauthenticated public
   GET per ticker; overwriting `settlement.json` is now harmless).
3. `python3 scripts/q51_maker_fillsim.py` and record the result **with a fresh set of pins**
   against a NEW frozen snapshot dated that day. Do not re-baseline the milestone-2 pins.
4. Expect ~41-44 units, not 57. Plan the second sweep for after **2026-08-24**.

## 5. Honest scope

* **Nothing here is verdict-class.** No mean, no bootstrap, no CI, no P&L, no fill rate quoted
  as an edge, no registry row touched. `tests/test_q51_m3_preflight.py` asserts the report
  contains no key matching `mean`/`ci95`/`pnl`/`bootstrap`/`edge`/`profit`.
* **Two-agent rule: N/A and not satisfiable.** Nothing produced here is a verdict, a CI or a
  registry flip, so the rule does not bind. It also could not have been satisfied: no
  `Task`/subagent tool was available in this environment, the same limitation recorded on
  Q19/Q49/Q50 and on Q51 milestones 1 and 2. The projection's *arithmetic* does carry an
  independent check (section 2's cross-validation through the probe's own pipeline), which is
  a redundancy check and explicitly **not** a verifier.
* **This is an INPUT, not an edge.** Milestone 3 reopens a family that died for lack of
  measurement (S13/S23/S29 keep the status they already had). It does not predict that family
  now clears the bar. The repo still has **0 proven edges**.
* **Book-side numbers are directional.** `dt=2026-08-03` of `tape/orderbook_depth/` is a past
  day but not closed to growth — a stranded-branch sweep can legitimately union-append
  snapshots — so every book-derived acceptance assertion is a `>=` bound, per L280's
  precedent, and more tape can only raise the projected unit count.

## Files

* `scripts/q51_m3_preflight.py` (new, read-only, offline)
* `tests/test_q51_m3_preflight.py` (new, 20 tests)
* `tape/q51_settlement_cache/settlement-m2-2026-08-04.json` (new, immutable snapshot)
* `tests/test_q51_maker_fillsim.py` (3 pins repointed + 1 new identity test + docstring note)
* `reports/q51_m3_preflight.json` (new, regenerated artifact)

## 6. The lesson applied to this run's own code

`hazard_report()`'s "before" column defaults to the LIVE cache — correct for an on-demand
diagnostic, since after 2026-08-10 the hazard is genuinely gone and `hazard_confirmed` should
go False. The first draft of `test_acceptance_the_milestone_3_repull_moves_every_pinned_
milestone_2_number` used that default, which would have made the new test **an exact copy of
the bug it documents**: on 08-10 `before` becomes `after` and the assertion fails for a reason
unrelated to the property under test. The parameter `before_cache_path` was added and the test
now passes `P.FROZEN_M2_CACHE` explicitly, asserting `before_cache_is_the_frozen_m2_snapshot`
is True. Caught in review, before the gate ran.
