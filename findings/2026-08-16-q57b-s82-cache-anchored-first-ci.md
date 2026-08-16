# Q57(b) / S82 — the cache-anchored re-test: the first CI ever scored on S82, and it straddles zero

*2026-08-16 · research loop (`research-lead` orchestrator) · reopen path (b) of LOOP-QUEUE.md Q57*

**Verdict: DEAD by the pre-registered kill clause — PROVISIONAL, no registry flip.**
Block-bootstrapped 95% CI at `real_ask` net one taker fee: **[−0.0108, +0.2783]**, mean **+0.1208**,
`n_units = 12`, `n_obs = 12`, Kish effective n **12.0**, seed 42, 10,000 resamples, blocked by GAME.
The CI straddles zero, so Q57's own kill clause fires ("real-ask CI ≤ 0 / straddles zero → joins
S79/S22"). `clears_tick_magnitude` = **False**. Recommended disposition on independent confirmation:
S82 `idea` → `dead ✗`. **`kb/strategies/00-index.md` is NOT flipped by this run** — see §7.

---

## 1. What this run was, and why it is not tuning

Q57's newest-dated Status line (the independent verifier's correction round) left the item OPEN with
two precise reopen paths. This run executed **path (b)** verbatim:

> "reopen via a properly PRE-REGISTERED retest that … (b) widens the entry anchor to
> `q51_settlement_cache` as its OWN pre-registered choice (not a post-hoc addition) at
> `sign_variation_admissible`'s real `min_exclusive_minority_units=2` floor."

Every constant that differs from the first probe's sealed spec — the union anchor,
`flow_window_minutes = 15`, `max_entry_lag_minutes = 240`, `min_exclusive_minority_units = 2` — is
quoted out of that Status text, which was **committed to `main` at `d78c528` before this probe
existed**. `PREREG_SOURCE_COMMIT` pins it; `PREREG_SHA256 = eaab11238127ebed…` seals the spec dict and
`test_preregistration_hash_is_sealed` is the alarm if anyone edits a constant after scoring.

**The honest weakness, stated first rather than buried.** Those constants were fixed by a prior
round's *population-composition* observation ("12 GAME units, {no:10, yes:2}, 2 exclusive-minority").
No settlement result VALUE was read and no CI was computed in either prior round, so the choice is
**outcome-blind** — it cannot manufacture a positive mean. But outcome-blind is not the same as
information-free: choosing the cell with the most usable minority arm also chooses a variance
structure. That is exactly why §5 exists and why the disposition here is a kill and not a claim.

## 2. The population — admissible for the first time in S82's history

| | first probe (ledger anchor, 120 min) | **this run (union anchor, 15 min)** |
|---|---|---|
| GAME units | 11 | **12** (L41 floor 10 ✓) |
| `units_per_side` | {no: 11, yes: 0} | **{no: 10, yes: 2}** |
| exclusive-minority units | 0 (floor used: 1, an undisclosed relaxation) | **2** (floor: the real default 2 ✓) |
| CI scored | none — refused at the population gate | **yes, the first ever on S82** |

Anchor provenance: 49 tickers from `tape/settlement_ledger/` + **38 added by
`tape/q51_settlement_cache/`** = 87 anchored tickers (ledger takes precedence where both carry a
ticker, so the widening is strictly additive — pinned by
`test_union_anchor_is_a_superset_of_the_ledger_only_anchor`). Entry drops:
`no_prints_in_flow_window` 24 · `entry_snapshot_too_stale` 17 · `entry_ask_outside_price_band` 11 ·
`flow_not_extreme` 9 · `fade_side_ask_absent` 8 · `window_count_below_floor` 5.

**The pre-committed claim reproduced EXACTLY** — 12 / {no:10, yes:2} / 2, asserted in the report as
`precommitted_claim_check.reproduced = true`. The verifier's post-hoc observation was correct, and
this run converts it from a peek into a pre-registered, scored population.

Mean overround absorbed **+0.023636** (`real_ask`). Entry-instant concentration clean.

## 3. The result

```
block bootstrap   mean $+0.1208   95% CI [-0.0108, +0.2783]   n_units=12 n_obs=12
                  price_source_tag = real_ask, net ONE taker fee (0.07, core.pricing)
kish effective n  12.0
admissible=True   clears_tick_magnitude=False   fade wins 7/12
```

The lower bound is **1.1 cents below zero**. This is a near-miss, and a near-miss is a kill: the bar
is a bootstrapped CI *strictly* > 0 at real asks net of fees, and it is not met.

## 4. Anchor sensitivity — the undetermined choice is not load-bearing

The queue text did not say which `close_time` to take when a cache ticker carries several (48/60 do;
L360/L361 — Kalshi rewrites `close_time` at settlement, always EARLIER). This probe pre-registered
the **earliest** (most-rewritten, most conservative on the look-ahead axis) and reports the
alternative:

| anchor | units | sides | minority excl. | 95% CI (`real_ask`) |
|---|---|---|---|---|
| **prereg union / earliest** | 12 | {no:10, yes:2} | 2 | **[−0.0108, +0.2783]** |
| union / latest | 12 | {no:10, yes:2} | 2 | [−0.0108, +0.2783] — *identical* |
| cache only | 3 | {no:2, yes:1} | 1 | not scored (below floors) |
| ledger only | 9 | {no:8, yes:1} | 1 | not scored (below floors) |

The earliest/latest choice moves **nothing**. And the two single-source anchors both fail the floors —
the union is not a convenience, it is the only anchor that reaches an admissible population at all.

## 5. Why the +12¢ point estimate is not an edge (the checks this result needed most)

**(a) Jackknife — one unit carries more than half the mean.** Dropping the single best GAME unit
(`KXNWSLGAME-26AUG02DENBOS`, entered at `real_ask` 0.22, settled a win, +$0.76) takes the mean from
**+0.1208 to +0.0627**. Of the 12 leave-one-out refits, only **2/12** would have produced a CI lower
bound above zero — i.e. **10 of 12** single-unit deletions leave a CI that still straddles zero.

**(b) Calibration null — the whole "edge" is 1.62 binary events.** A `real_ask` of 0.93 is the venue's
own 93% claim, so under perfect calibration the expected number of fade wins is the SUM of the entry
asks = **5.38**. Observed: **7**. The entire result is **+1.62 excess wins on n = 12**. Quoting that
as "+12¢ per contract" dresses a small integer count of coin flips as a rate.

**(c) The outcome split is a restatement of the entry price.** `perfectly_price_ordered = True`:
**every** winning unit was entered at a `real_ask` ≥ **0.22** and **every** losing unit at ≤ **0.20**.
There is no interleaving at all. Rank correlations: entry ask vs P&L **+0.4685**, and the strategy's
own statistic |ρ| vs P&L **+0.4196** — the signal ranks P&L *no better than the price does*. On this
population S82's flow statistic is inert; what is being measured is "the expensive side won".

Any one of these would warrant caution. Together they say the sign of the point estimate is not
information, and they are the reason this finding does not hedge the kill.

## 6. What is honestly new, beyond the kill

The first probe's escalation — that the fade-to-YES arm is *structurally unfillable* — is now
**falsified on committed tape, under a pre-registered spec rather than a post-hoc one**. Two
independent settled games supply an in-band, `real_ask`-fillable fade-to-YES entry
(`KXNWSLGAME-26AUG02DENBOS` ρ = −0.850 at 0.22; `KXKBOGAME-26JUL070530KIWKTW` ρ = −0.231 at 0.06).
The correct historical reading of the first probe is the verifier's: **`below_min_units` under a
too-narrow anchor**, not a definitional impossibility. S82 dies of *measured indistinguishability from
price level on 12 units*, which is a much better-supported death than "unmeasurable".

## 7. Provenance, gates, and what this run does NOT claim

- **PROVISIONAL, no registry flip.** No `Task`/subagent tool exists in this harness, so no independent
  `verifier` was dispatchable (L287/L288/L290/L291/L295/L308/L313/L325 precedent; Q57's own text
  sanctions a PROVISIONAL run in exactly this case). Under the two-agent verdict rule a CI destined
  for `findings/` may be recorded as PROVISIONAL but **must not flip the registry** — S82 therefore
  stays `idea` with a dated note. The owed work is one independent re-derivation.
- **Reuse over reimplementation, deliberately.** The loaders, window arithmetic, entry rule, game
  collapse and scoring are IMPORTED from `scripts/q57_s82_flow_fade_probe.py`, which has already been
  re-derived to the digit twice (by `scripts/q57_s82_rederive.py`, which caught a real
  def-time-default-argument defect, and by an independent verifier working from a from-scratch
  reader). A third fresh implementation would have traded audited code for unaudited code. This module
  owns only what changes: the union anchor, the minority floor of 2, the L51 restatement, and §5.
  **This means the redundancy argument does NOT extend to the new code** — §5's checks and the union
  anchor have one implementation and one author.
- **L51 differentiation, with an axis that inverted.** The first probe partly justified separation
  from the dead S79 on "120 min is 4× S79's 30-min lookback". At 15 minutes that argument runs the
  other way (15 is *half* of 30) and is **not relied on**. Differentiation rests on the three axes
  that survive: disjoint entry-price families (`orderbook_depth`/`real_ask` vs
  `kalshi_trades`/`broker_truth` — no entry price can coincide), one close-anchored instant per game
  vs S79's hourly UTC grid, and a scale-free ρ vs an absolute contract threshold. `voided = False`,
  evaluated before any outcome value was read.
- **Look-ahead, unchanged and unresolved.** The entry anchor is a post-settlement `close_time`, and
  27/38 cache tickers in this population carry more than one distinct value. Ex-ante knowability is
  **UNVERIFIED**. It can only flatter the strategy, so it does not soften a negative result — but it
  would have to be closed before any positive one.
- **Prices.** Every entry price is `best_yes_ask`/`best_no_ask` read from `tape/orderbook_depth/`
  where the tape's own `price_source_tags.asks == "real_ask"`. Nothing is derived, averaged,
  complemented from a bid, or synthetic. Fee = one taker leg at `core.pricing.TAKER_FEE_RATE`
  (0.07), imported, never spelled (L5).

**Files:** `scripts/q57b_s82_cache_anchored_probe.py` ·
`tests/test_q57b_s82_cache_anchored_probe.py` (31 tests) · `reports/q57b_s82_cache_anchored.json`.
Gates AFTER the last code change: see the LOOP-QUEUE.md "Log of runs" line for this run.

## 8. Reopen condition (precise, so this is not re-run by accident)

S82 should be considered again **only** if a future tape supplies a population where the outcome split
is **not** perfectly ordered by entry price — concretely: ≥ 20 independent GAME units with ≥ 5
exclusive-minority (fade-to-YES) units, in which |ρ| ranks per-unit P&L materially better than the
entry ask does. More days of the current hourly `orderbook_depth` cadence at the current settled-game
rate will grow the unit count slowly but will not by itself break the price-ordering degeneracy. Absent
that, the honest close is: the signed-flow taker family (S79 continuation, S82 fade) is dead in both
directions.
