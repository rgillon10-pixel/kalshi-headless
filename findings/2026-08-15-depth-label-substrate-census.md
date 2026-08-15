# The depth tape's binding limit is RESOLUTION, not absence: a crypto fill-sim is runnable today at ~31-minute cadence; the sports lane is blocked on labels

**2026-08-15 · research loop, IDLE RUN, idle-run policy (c) — data-quality deep-dive on one
tape family (`tape/orderbook_depth/`).** Read-only, fully offline. **No P&L, no CI, no
bootstrap, no registry flip** (test-pinned).

**Status: CONFIRMED-WITH-CORRECTIONS (two-agent rule SATISFIED).** An independent `verifier`
re-implemented this census a third time and **confirmed F1, F2, F4 and the §4 collector-restart
claim exactly**, while **refuting the first cut's F3 and the title built on it**. This document
is the corrected version; §6 records exactly what changed and why, because a correction that
hides its own history is how a refuted number survives.

Scripts: `scripts/depth_label_substrate_census.py` (+31 tests),
`scripts/depth_label_substrate_rederive.py` (+8 tests).
Artifact: `reports/depth_label_substrate_census.json`.

## 1. Why this family, why now

`tape/orderbook_depth/` is the only committed family that carries **both sides of a real
resting book**, so every maker-side candidate this repo has tested (S6, S13, S19, S21, S23,
S29, S68, S78, S80) had to score its simulated fills against it. Scoring a fill needs a
y-label — a settled outcome. The recurring idea-stage kill of the last month has been some
form of *"we have no settled outcomes to join to"*: Q21 round #30 measured 373 of 1,003,235
`universe_sweep` tickers broker_truth-resolvable (all on one day); round #31 killed three more
candidates; Q24 died 0/81 on the join; S21 died on the L9/L43 disjoint-window trap. **Nobody
had ever asked that question of the depth family itself** — the one that actually hosts the
fill question. Prior depth work (Q25's 2026-07-13 anatomy, L168/L169/L282) measured book
shape and duplicates, never label joinability.

## 2. What was measured

Whole committed family, no sampling: **110,632 distinct tickers · 465,776 snapshots · 39
day-files · 0 malformed lines** — **as of this branch's merge with `origin/main` at `e897c61`**.
The tape is append-only, so the DESCRIPTIVE counts here drift with every collector pass (the two
hourly passes merged from `main` while this file was being written moved the population from
110,613/463,776 and the sports class from 9,553 to 9,572 legs). Every VERIFIER-CONFIRMED
headline figure was re-derived after that merge and is UNCHANGED: 418 probe-ready crypto units,
258 every-leg-observable across 12 days, 160 all-single, ready-only median 2.0 / 57.58%, median
forward gap 31.5 min, the 73.73x naive-census undercount, 488 duplicate rows / 0.48pp, and
418/418 depth-scoped ladder coherence. Outcomes resolved through
`core.settlement_sources.resolve_market_results` (the single sanctioned resolver, all 10
declared sources, none absent on disk). Bootstrap unit = the EVENT (L6), i.e. the crypto
hour-ladder or the sports game, never the individual bracket.

Floors were **pre-registered before the first run** and were not tuned to the result:
`MIN_SNAPSHOTS_PER_UNIT=2` · `MIN_READY_UNITS=30` · `MIN_DISTINCT_DAYS=5`. A unit is
`probe_ready` only when **every** depth-covered leg is labeled — partial labeling never
counts, because a fill-sim that scores only a ladder's labeled legs conditions away the
catastrophic wing (L41/L86).

## 3. Findings

**F1 (verifier-CONFIRMED) — the naive census under-counts the outcome corpus by 73.73×.**
Scanning only the settlement-NAMED directories (`tape/settlement_ledger/` + the six
`tape/qNN_settlement_cache/` dirs) — the census shape a person would write — reaches **837**
labeled depth tickers (0.76%). The sanctioned resolver reaches **61,711 (55.79%)**, because
three declared sources are EMBEDDED in another family's schema; here the whole gap is
`crypto_hourly.previous_settlement.results` (**60,874** hits, `broker_truth` by its own record
tag). Not a new hazard — **L300** already recorded that three settlement surfaces are invisible
to a directory listing, and the recent Q21 rounds did route through the sanctioned resolver.
What is new is the MAGNITUDE on the family that hosts the fill question.

**F2 (verifier-CONFIRMED as a mechanism; its first-cut magnitude was NOT — see §6) — the
pre-registered unit-level floor is VACUOUS on a multi-leg ladder** (recorded as **L355**). A
188-bracket crypto hour trivially clears "the unit has ≥2 snapshots" while an individual
bracket can carry exactly one. A resting order lives on ONE leg, so a leg seen once has **no
forward interval**. On real tape this bites **160 of the 418** probe-ready crypto units (every
leg single), not all 418. The sealed floor was left untouched and a separately-labelled
POST-HOC observability block added beside it.

**F3 (CORRECTED — the first cut was refuted) — the binding limit is CADENCE, and a crypto
fill-sim IS runnable on committed tape today.** Observability must be read **conditioned on
the probe-ready units**, never class-wide (the class-wide crypto figure is diluted by 40,186
legs that no probe would ever score — 40,008 unresolved plus 178 sitting in partially-labeled
units — and it points the opposite way):

| population | median snapshots/leg | legs with ≥2 |
|---|---|---|
| crypto, class-wide (101,060 legs) — **do not quote beside a ready-unit count** | 1.0 | 38.25% |
| **crypto, conditioned on the 418 ready units (60,874 legs)** | **2.0** | **57.58%** |
| **sports, conditioned on the 224 ready units (499 legs)** | **66.0** | **99.2%** |

Of the 418 ready crypto units, **258 have EVERY leg observed ≥2 times, across 12 distinct
days** — which clears this census's own pre-registered `MIN_READY_UNITS=30` /
`MIN_DISTINCT_DAYS=5`. Their **median forward gap is 31.5 min** (p25 31.3 / p75 31.9), and the
sports ready units run at essentially the same cadence (**median 31.1 min**). So the depth
collector's ~31-minute cadence, not a missing population, is what limits a queue-aware maker
fill-sim on crypto: **at most ~2 forward intervals per ready leg, spaced ~31 minutes** — a
resolution problem for a queue model whose events are second-scale.

The sports lane is limited by something else entirely: only **224 of 3,551** sports units carry
outcomes and **every labeled sports unit predates 2026-07-16** (the `settlement_ledger` freeze;
that family holds only `dt=2026-07-17` and `dt=2026-07-22`). Since the freeze the sports depth
tape has added **198,086 snapshots across 3,152 units** that nothing can score.

**F4 (verifier-CONFIRMED, scope corrected) — no cross-source agreement rate is computable.**
The embedded crypto labels (60,874 tickers) and the naive-union labels (10,941) overlap in
**0** tickers on this population — the L9 non-overlap shape again, at the source level. The one
validation that IS available is reported instead: over **the whole `crypto_hourly` corpus**,
**874/874** settled bracket ladders settle exactly one `B` bracket `yes`, 0 violations;
restricted to **the depth-covered crypto units only**, **418/418**, 0 violations. (Both are now
emitted separately — `ladder_coherence` and `ladder_coherence_depth_scoped` — because the two
scopes are different claims.)

**F5 (raised by the verifier) — 488 exact `(ticker, captured_at)` duplicate rows inflate the
crypto class-wide `frac_legs_with_ge_2_snapshots` by 0.48pp** (0.3825 raw → 0.3777 deduped;
sports: 605 duplicate rows, **0.00pp** effect). A duplicated row is not a second observation.
The forward-gap profile collapses exact-timestamp repeats before measuring, and
`duplicate_row_accounting` reports raw vs deduped side by side (ties to **L282**).

## 4. What it means (the actionable read — verifier-CONFIRMED)

Two independent lanes, two different blockers:

1. **Sports — blocked on LABELS, and the unblock is the same one Q21 round #30 surfaced for
   `universe_sweep`, worth more than that round could show.** A forward-running settlement
   collector (Q45 / `settlement_ledger`, dead since 07-22 per Q36's VPS diagnosis) would
   convert **3,152 already-captured, snapshot-rich sports units (198,086 snapshots)** into
   scoreable ones — the largest single substrate unlock available, and Ryan-side (VPS restart).
2. **Crypto — runnable NOW, at coarse resolution.** 258 ready units across 12 days already
   clear the pre-registered floors with every leg observed ≥2 times. Any probe built on them
   must state ~31-minute quote resolution as a modelling assumption, not assume continuous
   observation; raising the depth collector's per-leg cadence on crypto ladders is the
   collection-side fix. Both are collection changes, out of an idle run's lane — recorded, not
   built.

Nothing here says an edge exists in either lane. The real-ask CI bar is untouched, and the repo
still has **0 proven edges**.

## 5. Provenance and discipline

- Every number above is emitted by `scripts/depth_label_substrate_census.py` into
  `reports/depth_label_substrate_census.json`; re-run it to reproduce.
- No price is persisted by this census, so **no `price_source_tag` applies to its outputs**;
  the labels it counts are `broker_truth` by their own source records' tags.
- **Two-agent rule SATISFIED.** Producer: this run. Independent `verifier`: a third
  re-implementation of the census, dispatched by the orchestrating session, which confirmed
  F1/F2/F4/§4 exactly and refuted the first cut's F3 (§6). In addition, the producer-side
  redundancy script `scripts/depth_label_substrate_rederive.py` shares no code with the census
  and does not import it or `core.settlement_sources` (AST-pinned) — it reads each source's own
  record grammar, extracts tickers by string slicing instead of `json.loads`, splits units with
  `rsplit`, medians by index — and reproduces **every** compared field, including the corrected
  conditioned block (ready-only median/fraction, the 258/160/12 counts).
- Acceptance tests over real tape are floors and directions only (L320 growth-safety), on a
  frozen two-day slice (L191).

## 6. Correction history (what the verifier refuted, and what replaced it)

The first cut of this file (commit `b04efe7`) was titled *"the depth tape's two halves never
overlap"* and reported, beside the 418 probe-ready crypto units, a **class-wide** observability
cell (median 1.0 snapshots/leg, 38.25% with a forward interval) — a statistic over 101,060
legs, 40,186 of which are outside the ready set. Conditioned on the units it was printed next
to, the true figures are **median 2.0 and 57.58%**, and **258 units clear the census's own
floors with every leg observable**. The claim that 418 crypto event-hours were individually
unobservable was therefore wrong (the correct count is **160**), and "never overlap" was the
wrong frame: the overlap exists, it is **coarse (~31.5-min cadence)**.

Three narrower corrections landed with it: the "323,992 snapshots into a labeling void" figure
was an all-days class total (post-freeze: **198,086 on 3,152 units**); "874/874 ladders" is the
whole `crypto_hourly` corpus, not the depth-covered units (**418/418** there); and 488 exact
duplicate rows inflate the crypto class-wide ≥2 fraction by 0.48pp.

The census now emits `fill_observability_ready_only` (conditioned), `duplicate_row_accounting`
and `ladder_coherence_depth_scoped`, its `verdict_caveat` states in the artifact itself that the
class-wide block **must never be quoted beside a probe-ready count**, and both the conflation
and the scoping are pinned by tests — so this specific error cannot recur silently. The lesson
rows were reframed to the verifier-confirmed claim before publication (see L355/L356).
