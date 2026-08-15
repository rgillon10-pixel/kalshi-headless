# The depth tape's two halves never overlap: labels live on crypto, book evolution lives on sports

**2026-08-15 · research loop, IDLE RUN, idle-run policy (c) — data-quality deep-dive on one
tape family (`tape/orderbook_depth/`).** Read-only, fully offline. **No P&L, no CI, no
bootstrap, no registry flip** (test-pinned). Verdict class: **data-adequacy, PROVISIONAL** —
this harness has no `Task`/`verifier` subagent, so the two-agent rule could not be satisfied;
the sanctioned redundancy fallback ran instead (see §5).

Scripts: `scripts/depth_label_substrate_census.py` (+22 tests),
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

Whole committed family, no sampling: **110,613 distinct tickers · 463,776 snapshots · 39
day-files · 0 malformed lines**. Outcomes resolved through
`core.settlement_sources.resolve_market_results` (the single sanctioned resolver, all 10
declared sources, none absent on disk). Bootstrap unit = the EVENT (L6), i.e. the crypto
hour-ladder or the sports game, never the individual bracket.

Floors were **pre-registered before the first run** and were not tuned to the result:
`MIN_SNAPSHOTS_PER_UNIT=2` · `MIN_READY_UNITS=30` · `MIN_DISTINCT_DAYS=5`. A unit is
`probe_ready` only when **every** depth-covered leg is labeled — partial labeling never
counts, because a fill-sim that scores only a ladder's labeled legs conditions away the
catastrophic wing (L41/L86).

## 3. Findings

**F1 — the naive census under-counts the outcome corpus by 73.73×.** Scanning only the
settlement-NAMED directories (`tape/settlement_ledger/` + the six `tape/qNN_settlement_cache/`
dirs) — the census shape a person would write — reaches **837** labeled depth tickers (0.76%).
The sanctioned resolver reaches **61,711 (55.79%)**, because three declared sources are
EMBEDDED in another family's schema; here the whole gap is
`crypto_hourly.previous_settlement.results` (**60,874** hits, `broker_truth` by its own record
tag). Nothing is broken, and this is **not** a new hazard: **L300** already recorded that
three of the settlement-bearing surfaces are invisible to a directory listing, and the recent
Q21 rounds did route through the sanctioned resolver. What is new is the MAGNITUDE on the
family that hosts the fill question — **73.73×** — which is the number to quote the next time
someone reaches for a hand-rolled label map.

**F2 (new, and the reason this census distrusts itself) — the pre-registered unit-level floor
is VACUOUS on a multi-leg ladder** (found by this
census, in its own design — recorded as **L353**). A 188-bracket crypto hour trivially clears
"the unit has ≥2 snapshots" while **every individual bracket carries exactly one**. Measured
per LEG, POST-HOC and reported separately from the pre-registered verdict:

| class | legs | median snapshots/leg | max | legs with ≥2 |
|---|---|---|---|---|
| crypto | 101,060 | **1.0** | 3 | **38.25%** |
| sports | 9,553 | **20.0** | 375 | **96.22%** |

A resting order lives on ONE leg, so a leg seen once has **no forward interval** and its fill
is unobservable no matter how rich its siblings are.

**F3 — the two halves of a runnable maker fill-sim exist on this tape but never in the same
class.** Pre-registered (label-adequacy) verdict vs the observability half:

| class | probe-ready units | distinct days | day span | label verdict | observability |
|---|---|---|---|---|---|
| crypto | **418** | 17 | 2026-07-07 → 08-12 | SUBSTRATE-ADEQUATE | **fails** (median 1 snapshot/leg) |
| sports | **224** | 8 | 2026-07-07 → **07-15** | SUBSTRATE-ADEQUATE | **passes** (median 20, 96.2% ≥2) |
| other | 0 | 0 | — | SUBSTRATE-INADEQUATE | n/a |

Crypto is **label-rich, observation-poor**: 418 fully-labeled event-hours (2.9× the n=146
event-hours Q34's S14 queue fill-sim ran on) but you cannot watch a resting order's fate.
Sports is **observation-rich, label-poor**: 3,158 of 3,542 units carry no outcome at all, and
**every labeled sports unit predates 2026-07-16** — the `settlement_ledger` freeze window
(that family holds only `dt=2026-07-17` and `dt=2026-07-22`). The sports depth tape has kept
growing (321,992 snapshots) into a labeling void for a month.

**F4 — no cross-source agreement rate is computable.** The embedded crypto labels (60,874
tickers) and the naive-union labels (10,941) overlap in **0** tickers on this population —
the L9 non-overlap shape again, at the source level. The one validation that IS available is
reported instead: **872/872** settled bracket ladders settle exactly one `B` bracket `yes`,
**0 violations** — a corrupted or misaligned label map would not produce that.

## 4. What it means (the actionable read)

The binding constraint on offline maker research is **not** idea capacity and **not** the
absence of outcomes. It is that the one family with two-sided book evolution (sports) stopped
being labeled on 2026-07-15, while the family that is still labeled (crypto ladders) is
captured about once per bracket. Two consequences:

1. **The named unblock is the same one Q21 round #30 surfaced for `universe_sweep`, and it is
   worth more than that round could show:** a forward-running settlement collector (Q45 /
   `settlement_ledger`, dead since 07-22 per Q36's VPS diagnosis) would convert ~3,158 already
   captured, snapshot-rich sports units into scoreable units. That is Ryan-side (VPS restart),
   and it unlocks the substrate for the entire maker family at once.
2. **A cheaper, cloud-side alternative exists and is NOT proposed here as a probe:** raising
   the depth collector's per-leg cadence on crypto ladders would fix observability at the
   source. Both are collection changes, out of an idle run's lane; recorded, not built.

Nothing here says an edge exists in either class. The real-ask CI bar is untouched, and the
repo still has **0 proven edges**.

## 5. Provenance and discipline

- Every number above is emitted by `scripts/depth_label_substrate_census.py` into
  `reports/depth_label_substrate_census.json`; re-run it to reproduce.
- No price is persisted by this census, so **no `price_source_tag` applies to its outputs**;
  the labels it counts are `broker_truth` by their own source records' tags.
- **Two-agent rule NOT SATISFIABLE** (no `Task`/subagent tool in this harness — the
  L287/L288/L290/L291/L295/L308/L313/L325/L338 precedent). Redundancy fallback, reported as
  redundancy and never as verification: `scripts/depth_label_substrate_rederive.py` shares no
  code with the census and does not import it or `core.settlement_sources` (AST-pinned) — it
  reads each source's own record grammar directly, extracts tickers by string slicing instead
  of `json.loads`, splits units with `rsplit`, and medians by index. It reproduces **every**
  compared field exactly (population, snapshots, per-source resolution, per-class units,
  probe-ready counts, ready-day counts, per-leg medians and ≥2 fractions). The verdicts in §3
  are therefore **PROVISIONAL** until an independent agent re-runs them; no registry status
  was flipped and none may be flipped on this file alone.
- Acceptance tests over real tape are floors and directions only (L320 growth-safety), on a
  frozen two-day slice (L191).
