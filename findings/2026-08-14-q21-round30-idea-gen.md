# Q21 idea-gen round #30 — 0 of 3 survived; and the un-mined surface has a measured 1-day settleability ceiling

**Run:** kalshi-edge-hunter nightly, 2026-08-14 ~04:15Z UTC. **Trigger:** eligible queue count < 2.
Full Q0–Q56 file-shape rescan (L25, each item's LATEST status) = **0 eligible TODO/unclaimed/unblocked**
(8th consecutive idle-adjacent run; Q52/S78 flipped `dead ✗` and Q54/S79 already `dead ✗` — both
closed collect-and-revisit; everything else DONE / cred- or burst-gated / on a dead strategy) →
Q21 round required per the edge-hunter spec.

## The new signal this round: four independent saturation checks now agree
Rounds #27/#28/#29 (three consecutive nights) each proposed 3 candidates and the pre-registration
`verifier` killed all 9. Tonight a **fourth, mechanical** check agrees: the `kalshi-observatory`
leg's `findings/observatory/patterns.jsonl` scan of the freshest tape (`dt=2026-08-13`, 73 patterns)
finds **0 patterns that clear the fee floor AND are not already graveyard-blocked**. All 10
fee-clearing patterns are `naive-maker-spread`, every one blocked by the dead cousin **S6/S13**
(the flat-maker-fee > spread wall; the high z≈+31 is the >30¢ wing-spread artifact S6 already
diagnosed). Human reasoning and the mechanical scanner independently converge: **the binding
constraint is the data surface, not idea capacity.**

## Outcome
Three NEW falsifiable S-candidates (proposed S82/S83/S84) deliberately targeting the ONE fresh
surface never used for a directional-settlement backtest: `tape/universe_sweep/` (full-universe
top-of-book BBO, `price_source_tag=real_ask`, 4×/day, 07-17→08-13, ~20k lines/pass). An independent
`verifier` subagent attacked each against committed tape BEFORE registration (two-agent
pre-registration discipline). **0 of 3 survived — all KILL on directly re-derived tape facts,
before fees or CI even enter the picture.** A 0-registration round with honest verifier refutations
is a valid outcome; **no S-numbers are burned** (round #27 precedent): next free stays **S82**.
Still **0 proven edges.**

| cand | name | verdict | load-bearing tape fact (verifier-rederived) |
|---|---|---|---|
| **S82** | Full-universe favorite-longshot fade at real asks (the S1 mechanism on the whole platform) | **KILL (adequacy + fabricated field + hollow book)** | The gate cited a `no_ask_size` field that **does not exist** in `universe_sweep.v1` (a producer-spec error — the schema was never grepped). Using the real book identity `no_ask = 1 − yes_bid` (holds 667/667), the corrected fillable-NO gate (`yes_ask≤0.10`, `no_ask<1.00`, `yes_bid_size>0`) over the joinable-to-settlement set yields **13 rows → 2 distinct events ≪ the L41 10-event floor**. The S10 hollow-book death it claimed to escape is exactly what kills it: **623/667** joinable rows quote `no_ask=$1.00`. |
| **S83** | Cross-snapshot stale-quote settlement fade (≥3 byte-identical BBO snapshots) | **KILL (structurally unmeasurable on settleable tape)** | The mechanism needs ≥3 consecutive identical snapshots per ticker. On the joinable set, snapshots-per-ticker is **median 2, max 2 — 0 tickers reach 3** (the entire settleable surface is a single day). **0 measurable events.** |
| **S84** | Near-close decided-side underpricing taker (last snapshot before close) | **KILL (adequacy)** | Cadence is fine (median last-snapshot→close gap **0.81h**, so the S9 cadence-kill is NOT the decider). The gate (`last_price≥0.90 or ≤0.10`, decided-side ask `<1.00`, fill size `>0`) passes **2 distinct events < 10**. Hollow book (623/667 `no_ask=$1`) does the killing again. |

## The measured data-gap (the durable product of this round)
Resolving all **1,003,235** unique `universe_sweep` tickers (24 snapshot-days) through
`core.settlement_sources.resolve_market_results` across all 10 declared settlement families:

- **373 tickers resolve to a `broker_truth` settlement — all 373 via `settlement_ledger`, 0 from
  any q-cache family** (the q-caches are sports/crypto-probe-specific and don't overlap the broad
  universe).
- Those 373 collapse to **209 distinct events across only 3 series** —
  `KXMVESPORTSMULTIGAMEEXTENDED` + `KXMVECROSSCATEGORY` (multi-game / cross-category parlays) and
  `KXSILVERH` (silver hourly) — **not** the diversified sports/econ/politics/crypto population the
  proposals leaned on.
- **Every joinable row is captured on a single day, `dt=2026-07-22`** — the `settlement_ledger`
  freeze date (`tape/settlement_ledger/` holds only `dt=2026-07-17` and `dt=2026-07-22`). So the
  "24 days × 20k markets" surface has a **broker_truth-settleable footprint of one snapshot-day /
  3 series**, and it stays that way until a settlement collector is extended past 07-22.
- Even that footprint fails L6 independence: the 3 series are combinatorial parlays / sequential
  hourly strikes on shared underlyings → correlated draws, not independent units (adequacy kills
  first, so this is secondary).

**Actionable read for Ryan (a concrete unblock, distinct from the standing kalshi_trades key ask):**
`universe_sweep` — the largest, freshest, most-diversified free tape we hold — is currently
**un-backtestable for any settlement-direction edge** not because of the sweep but because the
broad settlement family (`settlement_ledger`, Q45) stopped producing after 07-22. A settlement
collector fixed to run forward would unlock this whole surface.

## Verifier lesson candidates (flagged for kb-distiller, NOT enshrined here)
1. **A gate field that does not exist on the target tape is an automatic idea-stage KILL.** S82
   gated on `no_ask_size`, absent from `universe_sweep.v1`. A mechanism's fields must be grepped in
   the actual schema before registration (extends the L165-class citation discipline).
2. **Settleability of a full-universe BBO tape is bounded by the settlement-family freeze, not by
   the sweep's own date range.** `universe_sweep` advertises 24 days × ~20k markets; its
   broker_truth-joinable footprint is 373 tickers / 209 events / 3 series on the single day
   2026-07-22.

## Provenance / discipline
- All counts re-derived by the `verifier` from committed tape (`tape/universe_sweep/` 24 days,
  `tape/settlement_ledger/`), nothing trusted from proposal prose. Settlement via
  `core.settlement_sources.resolve_market_results` across all 10 families. Fees only via
  `core.pricing` (`fee_per_contract`, `TAKER_FEE_RATE=0.07`, `MAKER_FEE_RATE=0.0175`). Bootstrap
  unit = event (L6); floor = 10 units (L41).
- A pre-registration verifier attack is the mandated step for idea-stage candidates; it ran and
  returned 0 survivors. No candidate was registered, so nothing here is verdict-class; no registry
  flip, no new queue item, no S-number consumed (next free stays **S82**).
- Still **0 proven edges.** Binding constraint stays the DATA SURFACE — the standing multi-day
  `kalshi_trades` need (Q47/Q51, Ryan-key-gated) plus, newly measured tonight, the frozen broad
  `settlement_ledger` (Q45) that caps the `universe_sweep` surface at one settleable day.
