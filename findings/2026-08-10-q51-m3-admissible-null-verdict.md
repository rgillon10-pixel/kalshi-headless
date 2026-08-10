# Q51 milestone 3 — the first ADMISSIBLE run of the interval-level maker fill-sim: an honest NULL

**Date:** 2026-08-10 · **Run:** research loop (protocol v3) · **Queue item:** Q51 milestone 3
(time-gated to today; the gate opened as scheduled)
**Status:** **PROVISIONAL** — no independent `verifier` was dispatchable (see "Two-agent
status" below). **No registry row moves.** S13/S23/S29 keep the `dead ✗` they already had.
**Still 0 proven edges.**

---

## 1. What fired, and the exact recipe followed

The 2026-08-05 pre-flight run recorded a revised firing recipe; it was followed literally.

| step | command | outcome |
|---|---|---|
| (i) | `python3 scripts/q51_m3_preflight.py` | conservative **41 units / 238 legs** at an 08-10 firing (optimistic 44/256) — **4x the L41 floor of 10** → FIRE |
| (ii) | `python3 scripts/q51_maker_fillsim.py --build-cache` | re-pulled `/markets/{ticker}` for the SAME 60 tickers, read-only + unauthenticated; overwrote `tape/q51_settlement_cache/settlement.json` |
| (iii) | `python3 scripts/q51_maker_fillsim.py` | the milestone-3 result, over the rebuilt cache; reproduced byte-identically on a second run |
| (iv) | freeze + pin | `tape/q51_settlement_cache/settlement-m3-2026-08-10.json` (sha256 `26762aff…36ef5`), pinned by its own hash and used as the `cache_path=` of every milestone-3 test |

`scripts/q51_maker_fillsim.py` is **UNCHANGED**, as the milestone spec requires. The
milestone-2 pins remain on `settlement-m2-2026-08-04.json` (sha256 `60d381e5…eba0a`,
verified unchanged) — nothing was re-baselined.

The settlement cache is `broker_truth`: 60 markets, **59 finalized / 1 still active**,
results `no` 35 / `yes` 19 / **`scalar` 5** (non-binary, dropped per L52) / `''` 1.
An independent 12-ticker stride sample re-fetched with a plain `requests` GET (not the
probe's client) agrees with the frozen snapshot on `result`/`status`/`close_time`/
`event_ticker` **12/12, 0 disagreements**.

## 2. The result

**Headline `all_intervals`** — rest price `real_bid` (the touch observed at book snapshot
`t_i`), fill evidence `broker_truth` (an executed print crossing that side before `t_{i+1}`),
settlement `broker_truth`, **maker fee 0.0175** (L5 — not the 0.07 taker rate),
block-bootstrap **by GAME** (never by outcome), `n_boot=10000`, `seed=42`:

| quantity | milestone 2 (2026-08-04) | **milestone 3 (2026-08-10)** |
|---|---|---|
| units (games) | 7 — **below** the L41 floor | **51** |
| legs / fills | 40 / 26 | **294 / 64** |
| fill rate | 0.6500 | **0.21769** |
| interval coverage | 17/20 = 0.8500 | **58/147 = 0.39456** |
| opposing (losing) units | 4 | **12** |
| mean | +$0.0445 | **+$0.010068** |
| 95% CI | [−$0.0212, +$0.1202] | **[−$0.015700, +$0.036815]** |
| `admissible` | **False** (`below_min_units`) | **True** (`reasons=[]`) |
| `clears_tick_magnitude` (L27) | False | **False** |
| verdict | INADMISSIBLE / DATA-INADEQUATE | **admissible NULL — CI straddles zero at real prices** |

**Sensitivity `covered_intervals`** (the branch that first clears L41 on this firing):
116 legs / 64 fills / **fill rate 0.55172**, 25 units, mean **+$0.025517**,
CI **[−$0.041017, +$0.088559]** — same verdict.

**Sub-branches:** `all_intervals_yes_bid` fill **0.09524** (14/147), mean +$0.010544,
CI [−0.022260, +0.041479]; `all_intervals_no_bid` fill **0.34014** (50/147), mean +$0.009592,
CI [−0.057192, +0.076054]; `conditional_on_fill` 64 legs / 24 units, mean **+$0.04625**,
CI [−0.073443, +0.179091]. The YES/NO fill asymmetry milestone 2 identified as its one robust
observation (taker flow is ~80% buying) **persists and widens**: 3.6x here vs 1.9x there.

**Fill traceability: 64/64** fills trace to a `broker_truth` `trade_id`. The predicate reads a
print or returns `False`, so a synthesised fill cannot occur. Zero fills are priced at a
midpoint or a synthetic.

## 3. What this does and does not mean

**It does:** convert milestone 2's "not measured yet" into a measurement. This is the FIRST
run of this design whose `bootstrap_verdict_admissible` gate opens (≥10 units and ≥1
opposing-sign cluster, both satisfied by a wide margin). The honest verdict is a **NULL**:
at real prices, net of the maker fee, the interval-level resting-maker family on
`orderbook_depth` × `kalshi_trades` produces a mean of +1.0¢ per leg whose 95% CI spans
zero, and which fails the L27 tick-magnitude gate.

**It does not:** revive anything. S13, S23 and S29 are already `dead ✗`; a CI straddling zero
is not a revival, and this run explicitly declines to read a positive point estimate as one.
It also does not re-kill them — an admissible null is neither. The registry is untouched.

**Three qualifiers that must ride with the headline:**

1. **The headline is a fill-rate rescaling, not an independent measurement of per-fill
   economics.** 230 of 294 legs (78.2%) are unfilled and contribute an EXACT 0.0, so
   `mean_over_all_legs == fill_rate × mean_over_filled_legs` is an identity — verified
   numerically to 0.0e+00 (0.21769 × 0.04625 = 0.010068). Any per-fill edge is compressed
   ~4.6x before the tick gate is applied.
2. **51 units is nominal; only 24 are informative.** 27 of the 51 game units consist entirely
   of unfilled legs and contribute nothing but exact zeros to every resample. The
   information-bearing unit count is **24** — still above the L41 floor of 10, so the
   admissibility verdict survives, but "51 units" overstates the independent evidence by
   roughly 2x. (New lesson **L326**.) Kish effective n over legs is 49.91 (unit sizes 2–6),
   which does NOT capture this — an all-zero unit is perfectly "sized" and wholly uninformative.
3. **L309's `drops` unit-mixing defect is present and inert.** `{no_settlement: 0,
   non_binary_result: 15, unsettled: 3, not_two_sided: 0, post_close: 0, single_snapshot: 3}`
   — the first five count INTERVALS, `single_snapshot` counts TICKERS, so `sum(drops.values())`
   counts nothing. Confirmed to affect only the drops accounting, no headline number. The
   repair stays deferred (milestone 3 required the probe unchanged).

## 4. The 08-08 projection vs what actually happened (L308 re-read)

Every projected count moved, and in an instructive direction:

| | projected (08-08) | **actual (08-10)** |
|---|---|---|
| scored intervals | 128 | **147** |
| legs | 256 | **294** |
| game units | 44 | **51** |
| fills | 76 | **64** |
| `all_intervals` fill rate | 0.29688 | **0.21769** |
| `covered_intervals` fill rate | 0.61290 | **0.55172** |
| interval coverage | 0.48438 | **0.39456** |

**Both drivers are measured, not assumed:**

* **The population grew** because Kalshi's `close_time` on a FINALIZED market is the actual
  finalize instant, not the scheduled close the milestone-2 cache recorded while the game was
  still `active`. Re-pulled, **48 of 60 markets' `close_time` moved EARLIER, 12 unchanged,
  0 later** → 59 markets in scope under the actual times vs 47 under the scheduled ones. The
  `close_day <= fire_date` proxy is an upper bound on *settlement lag* but it is a LOWER bound
  in this direction, which the pre-flight did not anticipate. Test-pinned
  (`test_acceptance_the_m3_repull_moved_close_time_earlier_never_later`).
* **The fills shrank** because 5 of the 60 markets settled `scalar` (L52 non-binary) and one
  never settled — 15 intervals lost to `non_binary_result` that the synthetic projection cache
  assumed binary.

**The compression L308 predicted is real and larger than projected.** Against the committed
milestone-2 report: `all_intervals` fill rate **0.6500 → 0.21769 = 2.99x** compression
(L308 projected 2.27x), while the conditional-on-coverage rate falls only **0.7647 → 0.55172
= 1.39x** (projected 1.26x). Coverage falls **0.8500 → 0.39456 = 2.15x**. The identity
`all_rate / covered_rate == coverage` holds exactly (0.394558 = 0.394558). **L308's mechanism
is confirmed: the collapse is a COVERAGE effect, not a change in fill behaviour** — milestone
2's settled markets were the games PLAYED on 08-03, i.e. exactly the markets that TRADED on
08-03.

## 5. The gate hazard that L284 did not fully close (new lesson L325)

L284 (2026-08-05) found that `--build-cache` would turn `pytest -q` red on firing day, and
repaired it by freezing the m2 settlement cache and repointing three pins in
`tests/test_q51_maker_fillsim.py`. **The firing turned the suite red anyway** — 6 acceptance cases across
**4** sibling modules the repair never looked at:

* `tests/test_q51_m3_preflight.py` — two acceptance cases called `P.run(with_hazard=False)`,
  which defaults to the **LIVE** settlement cache. Under the re-pulled cache the close-day
  table collapses from 11 rows to 8 and the "57 units is the terminal row" pin fails.
  **Failures:** `::test_acceptance_the_queue_s_57_units_is_the_terminal_row_not_the_08_10_row`,
  `::test_acceptance_the_cumulative_table_is_monotone_on_real_tape`.
* `tests/test_q51_m3_fill_projection.py` — `calibration_vs_milestone_2()` defaulted its
  comparand to the **LIVE** `reports/q51_maker_fillsim.json`, the very file step (iii)
  rewrites. After the firing it compared the 08-04 projection against the 08-10 RESULT and
  reported `MIXED` instead of `over-inclusive`.
  **Failure:** `::test_acceptance_the_close_day_proxy_is_an_upper_bound_on_milestone_2`.
* `tests/test_q51_maker_fillsim_rederive.py` — the milestone-2 independent-redundancy
  acceptance case calls `R.rederive()`, which defaults to the live
  `reports/q51_maker_fillsim_rows.jsonl`. 40 rows became 294.
  **Failure:** `::test_acceptance_rederives_the_committed_report_rows_cleanly`.
* `tests/test_settlement_sources.py` — L300's acceptance pin ("the full settlement registry
  resolves **9** of the 42 traded tickers, all from `q51_settlement_cache`, 9 GAME units,
  below the L41 floor of 10") reads the LIVE cache. After the re-pull it resolves **32**.
  **Failures:** `::TestAcceptanceRealTapeS79DataGate::test_the_full_registry_resolves_nine_and_names_the_family`,
  `::test_nine_is_below_the_l41_ten_unit_floor`. *This one is not only a hazard — see §5b.*

**Repair (non-weakening — no assertion was relaxed, deleted or reordered):** the two preflight
cases now pass `cache_path=P.FROZEN_M2_CACHE` explicitly; `calibration_vs_milestone_2`'s
default comparand is now the newly frozen `reports/q51_maker_fillsim-m2-2026-08-04.json`
(sha256 `745c4eb7…83c24`, recovered byte-identically from the committed tree), pinned by its
own hash plus a source-text assertion that the default can never point back at the live
report; the rederive acceptance case reads the newly frozen
`reports/q51_maker_fillsim_rows-m2-2026-08-04.jsonl` (sha256 `780b1a7d…5ca50`), also
hash-pinned; and L300's pin is re-anchored by substituting the frozen m2 snapshot into the
source registry via `dataclasses.replace(path_glob=…)`, which reproduces its published
counts **exactly (9/9)**. Every repaired module keeps a live-path case (SHAPE-only, or a
directional measurement of the new state), so nothing is silently abandoned — L284's own
division of labour.

### 5b. A side-effect worth its own line: the re-pull moved a DIFFERENT data gate

L300 recorded that the whole declared settlement registry resolved **9** of the 42 tickers
that traded on 2026-08-03, all nine from `q51_settlement_cache`, **9 GAME units — below the
L41 floor of 10**. Milestone 3's re-pull resolved 49 more of the 60 sampled markets, so the
same registry now resolves **32 tickers = 32 distinct GAME units**, comfortably above the
floor. Four crypto brackets (`KXBTC-`/`KXETH-`) remain unresolved AND unlisted by every
source — L300's "third state" residue is unchanged.

**This revives nothing.** S79 already fired on 2026-08-09 (DEAD-by-CI, verifier-CONFIRMED,
24 units off the trade-print backfill), and this is a settlement-RESOLVABILITY measurement on
one surface, not a strategy result. It is recorded because a data gate that a prior run
measured as closed is now open, and the reason is a side-effect of an unrelated milestone —
the kind of thing that otherwise gets rediscovered expensively. Pinned directionally
(`>= 32`), since a settlement cache only ever gains results.

**The generalisable lesson (L325): freezing an input for ONE consumer does not freeze it for
the others — and here there were THREE others plus a downstream report.** L284 correctly identified the mutable artifact and correctly froze it, then
repaired only the module whose failure it had demonstrated. The audit that was owed — "which
OTHER tests read this same mutable artifact?" — was never run, and the hazard fired on
schedule in the two modules built AFTER the repair. A mutable-artifact repair needs a
repo-wide reader audit, not a per-file fix. **This also generalises past the cache: the
calibration's comparand was a REPORT, not a cache** — any artifact a run's own command
rewrites is equally unpinnable, and `reports/` had never been treated as such.

## 6. Two-agent status: **PROVISIONAL** (not satisfiable this run)

The run brief stated that a `Task`/subagent tool was available and that the two-agent verdict
rule was therefore active and mandatory. **It is not available in this harness** — dispatching
a `verifier` returns `No such tool available: Agent`, the same limitation every prior Q51
milestone recorded (the L287/L288/L290/L291/L295 precedent). Per LOOP-QUEUE.md step 5 this
result is committed **PROVISIONAL** and flips no registry status.

The sanctioned fallback ran instead — a second **INDEPENDENT code path** reading ONLY
`reports/q51_maker_fillsim_rows.jsonl`, never importing the probe (own reader, own `Decimal`
`ROUND_CEILING` fee arithmetic vs the probe's `math.ceil`, own grouping, own bootstrap,
own seed 20260810):

* **0 P&L mismatches / 294 rows**, 0 untraced fills, 0 bad fill tags, 0 non-`real_bid` rest tags.
* Every branch mean reproduces to 12 decimals; every CI agrees within resampling noise and
  **every sign conclusion is unchanged** (e.g. `all_intervals` [−0.016093, +0.037061] vs the
  probe's [−0.015700, +0.036815]).
* Unit construction verified from the rows, not the report: **51 distinct games**, both legs of
  a ticker and every ticker of a game share ONE unit → the bootstrap is by game, **never by
  outcome**. 12 opposing units confirmed independently.
* Fee control (L5): mean at maker 0.0175 = +$0.010068; at the taker 0.07 = +$0.008061 — the
  correct rate is applied and the verdict is not fee-rate-sensitive.
* Zero-inflation identity and the 27-of-51 all-zero unit count derived here.

**This is a redundancy check, NOT a verifier**, and its limit is stated plainly: it shares
every premise with the producer — L279's `taker_book_side` orientation, the rest-price choice,
the settlement cache itself. It could not have caught an orientation error (milestone 2's own
redundancy path did not, and only the tape did), and it is not a second agent's judgement.

## 7. What is owed next

1. **An independent `verifier`** on these numbers the first time a harness exposes one. Until
   then the result stays PROVISIONAL and the registry stays untouched.
2. **The second sweep after 2026-08-24** reaches the terminal 57 units / 330 legs. Per the
   08-08 projection this buys resample UNITS, not fill EVIDENCE (76 of the 79 fills the
   committed tape will ever supply are already in this population; the later steps add 74 legs
   and 3 fills). It will overwrite `settlement.json` again — the m3 pins are frozen against
   that, deliberately.
3. **L309's `drops` unit-mixing repair**, now unblocked: milestone 3 has fired, so the probe
   no longer has to run unchanged.
4. **The binding constraint is still `orderbook_depth`'s revisit interval** (L283): 98.01% of
   executed volume cannot be priced against a quote younger than 15 minutes. The 3-hour grid
   is a CEILING on what this design can ever claim — no queue-position, time-to-fill or
   sub-interval adverse-selection number is computed anywhere in this run, and the report's
   key set is test-asserted free of them. Only Q47's Ryan-gated WS `orderbook_delta` moves it.

## Artifacts

* `scripts/q51_maker_fillsim.py` — **unchanged** (milestone spec)
* `tape/q51_settlement_cache/settlement-m3-2026-08-10.json` — frozen milestone-3 input
* `reports/q51_maker_fillsim.json`, `reports/q51_maker_fillsim_rows.jsonl` — the result
* `reports/q51_maker_fillsim-m2-2026-08-04.json` — newly frozen milestone-2 comparand
* `reports/q51_m3_preflight.json` — step (i)
* `reports/q51_maker_fillsim_rows-m2-2026-08-04.jsonl` — newly frozen milestone-2 rows
* `tests/test_q51_maker_fillsim.py` (+6 cases, 48 total), `tests/test_q51_m3_preflight.py`
  (+2), `tests/test_q51_m3_fill_projection.py` (+2),
  `tests/test_q51_maker_fillsim_rederive.py` (+2), `tests/test_settlement_sources.py` (+1)
* `kb/lessons/00-lessons.md` — L325, L326
