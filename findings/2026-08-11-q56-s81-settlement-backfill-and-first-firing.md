# Q56 / S81 — the settlement backfill opened the gate, and the sealed binding test fired

**Run:** kalshi-research-loop, 2026-08-11. **Queue item:** Q56 (topmost item whose CURRENT
status carries an open sub-item: *"Owed next: (1) the settlement backfill"*).
**Milestone executed:** the owed collector milestone — a bounded, exhaustive, outcome-blind
settlement backfill for the crypto-hourly legs `crypto_hourly.previous_settlement` never
paired — and, because the sealed probe self-activates once its gate opens, its **first
firing**.

**VERDICT CLASS: CI, TWO-AGENT VERIFIER-CONFIRMED (CONFIRMED-WITH-CORRECTIONS).** The producing
sub-session's own harness had no `Task`/subagent tool, so it could not dispatch a verifier
(L287/L288/L290/L291/L295/L308/L313/L325 precedent) and recorded the result as PROVISIONAL. The
orchestrating research-loop session that supervised this run does have a `verifier` agent and
dispatched one separately: it independently reconstructed the pre-backfill selection set (proved
outcome-blindness by fault-injection, not just by grep), re-derived the headline on a THIRD
from-scratch implementation (mean and every count reproduce exactly; CI [−0.1271, +0.0082] at an
independent seed), tested the block-bootstrap's unit choice against three alternative blockings
(the preregistered (coin, regime-run) unit gives the WIDEST, most conservative upper bound of any
tested — an i.i.d. resample of the same 105 values would have manufactured a false kill,
[−0.1225, −0.0019]), and live-verified 15 cached settlements against the public endpoint. Verdict:
**CONFIRMED-WITH-CORRECTIONS** — one must-fix (the §1b cross-source citation, corrected below to
disclose it as a live, uncommitted check rather than a re-runnable artifact) and two prose-only
corrections, none of which changes a number. Consequently:

* **NO registry status was flipped** — but now because the confirmed result is an admissible NULL
  (CI straddles zero), not because verification was unavailable. S81 stays `binding-test-defined`.
* The headline CI below is now a two-agent-confirmed result, not merely provisional.
* The sanctioned no-verifier **redundancy** fallback also ran (`scripts/q56_s81_rederive.py`,
  below) — reported as redundancy, distinct from the independent verifier pass above.

---

## 1. What was built (the collector milestone)

`scripts/q56_s81_settlement_backfill.py` (+23 offline tests in
`tests/test_q56_s81_settlement_backfill.py`). Read-only, GET-only, unauthenticated public
`/markets/{ticker}` through the existing throttled `validation.v3_market.Kalshi` client. No
credentials, no order path of any tier, no `execution/` import (pinned on the AST, not on prose).

**The selection rule, declared in the module docstring before any result was read, and
EXHAUSTIVE:** pull *every* unjoinable `leg_ticker` the sealed probe's own outcome-blind
candidate path produces — every cell (`informative`, `control`, `excluded`), fillable and
non-fillable alike, in sorted order, with no early stop that depends on what came back. This
is load-bearing rather than bookkeeping: a backfill that chose *which* missing settlements to
fetch could bias a sealed probe's population without touching one byte of the probe. An
exhaustive, pre-declared, outcome-independent rule cannot — the only thing this module decides
is *whether a ticker's outcome is known at all*, never *which outcome makes the cut*.

The selection set is derived by importing the sealed probe's own functions (L36 — never
re-deriving its candidate logic): `load_crypto_records` → `funding_hours` → `regime_runs` →
`candidate_rows` → `settled_ticker_set` (a MEMBERSHIP set; the direction is dropped inside the
probe). `outcome_map()` / `score_rows()` are never reached from the backfill; a test pins that
no `PROBE.outcome_map` / `PROBE.score_rows` / `PROBE.verdict_block` / `PROBE.binary_outcome`
reference exists in the module.

**Artifact:** `tape/q56_settlement_cache/settlement-s81-2026-08-11.json`, in the same
`CACHE_MARKETS_MAP` shape `core/settlement_sources.py` already reads for the five
`q*_settlement_cache` families, **declared** there as a new source `q56_settlement_cache`
(price_source_tag `broker_truth`) so it is visible to every future coverage scan — an
undeclared settlement family is exactly the L165/L300 failure that module exists to end. The
repo now has **TEN** declared settlement surfaces, not nine; the module docstring says so and
tells the reader to quote `declared_source_names()` rather than a remembered count.

**Live pull (2026-08-11):** 282 requested / **282 fetched** / 0 failed / completeness
**1.0000** / errors `{}`; classified **282 binary / 0 non-binary / 0 listed-unsettled**. All
results cached VERBATIM (L52 — `scalar` and unsettled rows would have been kept as-is;
none arrived). Idempotent and additive by construction: a re-run merges, and a stored binary
result can never be downgraded by a later weaker read (both pinned by tests).

*Disclosure:* before writing the collector I ran a two-ticker endpoint smoke test
(`KXBTC-26AUG0100-B63050`, `KXBTC-26JUL0512-B63050`) to confirm the public endpoint still
serves months-old crypto-hourly results; both returned `finalized`. Those two tickers are
inside the exhaustive selection set, and the probe's spec is hash-sealed, so no selection or
tuning could have been influenced by having seen them — recorded here rather than omitted.

### 1b. Cross-source validation of the new family (12/12, live check — not a committed artifact)

The backfill's results are read from a DIFFERENT surface (public `/markets/{ticker}`) than the
family that already answered for the other 574 legs (`crypto_hourly.previous_settlement`). Because
the backfill's own selection rule is exhaustive over exactly the UNJOINABLE tickers (§1a), the
282 cached rows and the 574 embedded-family rows are disjoint by construction — **the overlap
between `tape/q56_settlement_cache/` and `crypto_hourly.previous_settlement` is 0 tickers**, so
this check can never be reproduced by reading the committed cache file against itself, and no
script or artifact for it lives in this repo. It was a live tool call made while writing this
finding, in the same spirit as §1a's two-ticker smoke-test disclosure: on 12 randomly sampled
(seed 11) legs the EMBEDDED family already resolves (drawn live from `crypto_hourly`, fetched
live from the public endpoint), the two surfaces returned the identical result — **12/12 agree, 0
disagree**, including the one `yes` in the sample (`KXBTC-26JUL1418-B64650`). An independent
verifier re-ran the same live check on a fresh seed-11 draw and got **25/25** agreement, including
two `yes` outcomes. The two surfaces mean the same thing by the same convention, so the 282
backfilled rows are not a semantically different kind of settlement quietly mixed into the same
population — but treat this paragraph as a disclosed live observation, not a re-runnable proof.

## 2. The gate opened, and L327's counterfactual was realized to the digit

Re-measured through the sealed probe's OWN outcome-blind adequacy path
(`candidate_rows` → `settled_ticker_set` → `population_report`; `outcome_map()`/`score_rows()`
not called, so the L311 seal was intact at this point):

| quantity | 2026-08-10 (gate shut) | 2026-08-11 (after the backfill) | floor |
|---|---|---|---|
| entry snapshots | 854 | 856 | — |
| settlement-joinable | 574 | **856** | — |
| unjoinable | 280 | **0** | — |
| informative entries | 19 | **137** | — |
| informative fillable entries | 15 | **105** | 10 |
| informative fillable RUNS (the unit) | 8 | **77** | 10 (L41) |
| Kish effective n | 4.79 | **58.33** | 10 (L322/L326) |
| `gate_reasons` | `[below_min_units, below_min_kish_effective_n]` | `[]` | — |
| `admissible` | false | **true** | — |

The 2026-08-10 finding computed a counterfactual — *"had every captured snapshot been
settlement-paired, the informative cell would hold 105 FILLABLE entries over 77 FILLABLE runs,
Kish 58.3"*. The realized post-backfill numbers are **105 / 77 / 58.333…**. That counterfactual
was a falsifiable forecast and it was confirmed exactly (new lesson **L331**), which is also the
strongest available evidence that L327's diagnosis — *the wall is the JOIN, not the funding
tape* — was the right one.

Stated precisely, because the match is exact only where it should be: the counterfactual's
FILLABLE figures (105 entries / 77 runs / Kish 58.3) reproduce to the digit, while the
counterfactual's total informative figures (136 entries / 94 runs) realize as **137 / 95** —
tape grew by 2 entry snapshots between the two runs (854 → 856), one of which lands in the
informative cell and is not fillable. The forecast is confirmed on exactly the quantities the
gate is defined over; the one-unit drift on the total is capture growth, not a modelling miss,
and is recorded rather than rounded away.

Settlement coverage after the pull: `856 requested / 856 resolved / 0 non-binary / 0
unresolved; hits: crypto_hourly=574, q56_settlement_cache=282`.

## 3. The firing — two-agent verifier-confirmed

`scripts/q56_s81_funding_regime_settlement_probe.py` is **byte-identical to HEAD** (verified by
`git diff --quiet` before the firing) and its `PREREG_SHA256` recomputes to the sealed
`edde1f66efc059d3628128ad2bbf0e49d60526c274664ca8e8bb5978dec34581`. Nothing about the design was
touched; only the population it was waiting for arrived.

Headline (`reports/q56_s81_funding_regime_settlement.json`, `status: SCORED`), entry at the
resting `yes_ask` (**`real_ask`**) of the adjacent-above `between` bracket, ONE
`core.pricing` taker fee at entry, settlement **`broker_truth`**, blocked by REGIME RUN
(L318/L324), n_boot 10,000, seed 42:

* **n_units 77 · n_obs 105 · mean −$0.06362 · 95% CI [−$0.12729, +$0.00660]**
* `admissible: true`, `reasons: []`, **n_opposing_units 13** (not a degenerate S20/L41 resample)
* `clears_tick_magnitude: false` — this gate tests whether the CI's LOWER bound clears +1 tick;
  with a negative mean it is arithmetically false regardless of this run's other numbers, so it
  carries no independent information here (it would matter for a positive-mean result close to
  the tick floor, not this one)
* Kish effective n **58.33** (design effect 1.32 — the informative cell is a genuine panel, not
  one long autocorrelated block; contrast the CONTROL cell's Kish 4.61 on 485 observations)
* 90 of the 105 scored legs (86%) come from tickers the backfill newly resolved; the sign is
  stable across the split (pre-backfill-only: mean −$0.0953, n=15; backfill-only: mean −$0.0583,
  n=90) — the result is not an artifact of the 14 legs that predate this run's collector

### 3b. Where the loss comes from (descriptive, post-hoc — not a second verdict)

The mean decomposes exactly, the way Q37's did: over the 105 scored legs the mean entry
`real_ask` is **$0.20181** and the mean taker fee **$0.01419**, so the break-even hit rate is
**21.600%**; the realized settle-YES rate on those legs is **15.238%**. The difference is
`0.15238 − 0.21600 = −0.063619` — the headline mean to the digit. So the leg is simply an
out-of-the-money bracket bought at a price the realized frequency does not support, and the
funding-regime conditioning does not move that: the CONTROL (`pin`) cell's fillable legs settle
YES at **15.052%** on 485 observations against a mean ask of **$0.21907** — i.e. the informative
cell's hit rate is 0.19 points HIGHER than the control's while its ask is 1.7¢ cheaper, a
difference far too small (and far too noisy at 77 units) to clear the fee. The signal is not
inverted; it is absent at this magnitude.

**Reading it honestly: this is NOT an edge.** The bar is a bootstrapped 95% CI strictly > 0 at
real fillable asks; this CI straddles zero with a NEGATIVE point estimate and fails the L27 tick
gate. It is an admissible NULL on an adequate population (the Q51-milestone-3 class), not a
strictly-negative falsification — the upper bound is +0.66¢, so "S81 is worthless" and "S81 is
mildly bad" are both inside the interval. **What it is not:** a kill — the CI does not clear
strictly below zero either, and a kill is verdict-class regardless: it would need this same
two-agent confirmation, which this NULL result now has, and still isn't one.

## 4. Redundancy (the sanctioned no-verifier fallback — NOT verification)

`scripts/q56_s81_rederive.py` (+13 offline tests) is a from-scratch second implementation
sharing **no code** with the probe: own JSONL readers (no `core.io`), own ISO-8601→epoch parser
by string slicing + days-from-civil (no `core.timeutil`, pinned against `parse_iso_utc` on real
committed timestamps so the "independence" is not two parsers sharing one bug), the funding
baseline re-derived from L318's TEXT (0.01% per 8h) rather than imported, own hour indexing,
own regime labelling and run blocker, own entry-snapshot selection, own adjacent-above leg
picker, own fillability band, own settlement reader straight off `crypto_hourly`'s embedded
`previous_settlement` and the new cache file (never `core.settlement_sources`), own
round-up-to-cent fee formula, own block bootstrap on its own RNG at seed **20260811** (not 42).
`TAKER_FEE_RATE` is the single shared symbol, because `invariants.py::no_handrolled_fee_rate`
forbids any module but `core/pricing.py` from spelling a schedule rate.

| quantity | probe | re-derivation |
|---|---|---|
| entry rows / joinable / unjoinable | 856 / 856 / 0 | 856 / 856 / 0 |
| informative entries / fillable / runs / fillable runs | 137 / 105 / 95 / 77 | 137 / 105 / 95 / 77 |
| control entries | 719 | 719 |
| scored rows | 105 | 105 |
| opposing units | 13 | 13 |
| pooled mean | −0.06361904761904763 | −0.0636190476190476**2** (last-bit float) |
| 95% CI | [−0.12729, +0.00660] (seed 42) | [−0.12752, +0.00692] (seed 20260811) |

Every count exact; the mean agrees to the last representable bit; the CI is an independent draw
and agrees to bootstrap noise with an unchanged sign conclusion. **This is redundancy, not
verification** — both implementations read the same tape and both believe the same
pre-registered design (that the adjacent-above bracket is the right directional instrument, and
that the capture-hour funding print is the right label). It cannot catch an error they share.

## 5. A test that went red, and why the repair is non-weakening (L325 again)

Declaring a TENTH settlement family is a global change, and it turned
`tests/test_q56_s81_funding_regime_settlement_probe.py::
test_acceptance_the_join_loses_most_of_the_informative_cell_to_settlement_pairing` red
(`assert 0 >= 1`) — a fixed-slice pin that asserts part of the informative cell is
settlement-unjoinable. Nothing about the property under test changed; the backfill simply
resolved the tickers.

The repair keeps the original assertion **byte-for-byte** and scopes its INPUT to the source
whose property it encodes: L327's claim is about the EMBEDDED `crypto_hourly.previous_settlement`
pairing, so the measurement now reads membership through that one source
(`resolve_market_results(..., sources=[crypto_hourly])`) — this is the same `dataclasses.replace`/
source-filter device `tests/test_settlement_sources.py::_frozen_m2_sources` already uses for the
Q51 cache. The post-backfill state of the FULL registry is measured in a NEW case
(`test_acceptance_the_q56_backfill_closes_the_embedded_pairing_gap_on_this_slice`) rather than
absorbed into the old one. No assertion was deleted, relaxed or reordered; the module goes 36 → 37
tests. The sibling `test_acceptance_gate_is_shut_on_the_fixed_slice` still passes untouched (the
two-day fixed slice is still below the 10-unit floor even fully joined).

## 6. Independent verifier pass — CONFIRMED-WITH-CORRECTIONS

Dispatched by the orchestrating research-loop session (which has a `verifier` agent the
producing sub-session's harness lacked), read-only, no changes to any producer file. It:

* proved outcome-blindness of the backfill selection **at runtime** (monkeypatched every
  outcome-reading function to raise, re-ran selection, zero trips — stronger than the source-grep
  the producer relied on), and independently reconstructed the pre-backfill unjoinable set to
  confirm it is set-equal to the 282 cached tickers (no cherry-pick possible);
* confirmed the seal: `git diff`/`git log` since the sealing commit `ce19b3e` show the probe
  untouched, and the pinned `PREREG_SHA256` was committed to `tests/` *before* this run, ruling
  out post-hoc re-specification;
* re-derived the headline on a **third**, independently-written implementation (a script separate
  from both the probe and `q56_s81_rederive.py`): every count matches exactly, the mean matches to
  the reported digits, and a fresh-seed CI draw lands at [−0.1271, +0.0082] — same sign, same
  shape;
* stress-tested the block-bootstrap's unit choice against three alternative blockings (by hour, by
  day, i.i.d. over observations); the preregistered (coin, regime-run) unit produces the WIDEST,
  most conservative upper bound of all of them — an i.i.d. resample of the identical 105 values
  would have manufactured a false kill ([−0.1225, −0.0019], excludes zero) — so the blocking is
  real and, if anything, working against this result reading as a kill;
* ran the L249 sign-boundedness check on the fill gate and confirmed it is verdict-bearing (both
  positive and negative outcomes are reachable under the gate's own constraints), and checked the
  funding-regime label for look-ahead (funding prints stamp at the top of the hour; entries land
  ~55 minutes before that print is knowable at capture time — no look-ahead found);
* live-reproduced the §1b cross-source check on a fresh sample (25/25 agreement, 2 `yes` outcomes)
  and flagged that the original 12/12 claim, as first written, cited no committed artifact and
  cannot be checked against the committed cache file (the exhaustive selection rule guarantees
  zero ticker overlap between the new cache and the embedded family by construction) — fixed above
  in §1b by relabeling it a disclosed live check rather than a reproducible artifact.

Two prose-only corrections were also folded in above: `clears_tick_magnitude: false` is now
annotated as carrying no independent information for a negative-mean result (§3), and the
finding now states that 86% of the scored sample (90/105 legs) comes from tickers the backfill
newly resolved, with the sign stable across the pre-/post-backfill split (§3).

**New lesson (folds into L330/L331/L332's family): an exhaustive backfill's cross-source
validation can never be checked against the backfill artifact itself** — the same exhaustiveness
that makes the selection rule outcome-blind (§1a) also guarantees zero overlap with the incumbent
source, so any agreement check necessarily lives outside the committed tape and must be labeled a
disclosed live observation, not implied to be a re-runnable proof.

## 7. What this does NOT claim

No edge. No kill. No graduation of any kind. The S81 row stays `binding-test-defined` — the
verifier-confirmed result is an admissible NULL (CI straddles zero), which is not a registry-flip
event in either direction — and the repo still has **0 proven edges**.

## Owed next

Nothing outstanding from Q56/S81: the backfill landed, the gate opened, the sealed probe fired,
and the two-agent rule is now satisfied (CONFIRMED-WITH-CORRECTIONS, §6). Both Q56 sub-milestones
have run to a stable, confirmed, non-edge conclusion.

## Reproduce

```
python3 scripts/q56_s81_settlement_backfill.py --dry-run     # selection count, no network
python3 scripts/q56_s81_settlement_backfill.py               # the pull (idempotent)
python3 scripts/q56_s81_funding_regime_settlement_probe.py   # unmodified, self-activating
python3 scripts/q56_s81_rederive.py                          # independent re-derivation
```
