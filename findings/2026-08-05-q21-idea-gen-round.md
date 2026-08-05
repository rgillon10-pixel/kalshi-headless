# Q21 idea-generation round #23 (2026-08-05, kalshi-edge-hunter) — 1 registered (S78, collect-and-revisit)

**Date:** 2026-08-05 (kalshi-edge-hunter nightly, Opus). **Two-agent rule at idea stage:**
producer (this run) + independent `verifier` agent. **Result: 1 registered (S78, as
`collect-and-revisit`), 2 surveyed and not registered (S79/S80).** Still **0 proven edges** — a
registration is not a proof, and S78 has no CI.

## Why a round fired, and why it is NOT the treadmill

Full Q0–Q51 file-shape rescan (L25, each item's LATEST status): **0 eligible TODO/IN-PROGRESS.**
Everything is DONE / cred-BLOCKED [Q14/Q15/Q32/Q33/Q35-build/Q47] / density-inadequate
[Q36/Q42/Q43, VPS dead ~13d] / on a dead-or-superseded strategy [Q9/Q11/Q12/Q16/Q23/Q24/Q27];
**Q51 is MILESTONE-3 TIME-GATED (re-pull 2026-08-10, ~44 settled markets)**; Q37 opened AND was
executed to a DEAD verdict on 2026-08-04. `<2 eligible → round fired.`

The four rounds before this one (#20–#22) each recorded "no new tape surface since the last
registration." **That is no longer true.** `tape/kalshi_trades/` — the public executed-trade
print tape (`broker_truth`, `taker_book_side`) — landed 2026-08-04 06:00Z (Q51 milestone 1).
This is the FIRST Q21 round with that surface available, so it is genuinely non-treadmill: the
trade tape makes realized post-fill **adverse selection (markout) directly measurable** for the
first time — the exact term that was unmeasurable and killed eight maker candidates
(S6/S13/S19/S21/S23/S29/S68 + the S73 idea-kill).

## S78 — Toxicity-filtered selective maker (the measurable-adverse-selection S11 lane) — REGISTERED `collect-and-revisit`

**Mechanism / counterparty.** Rest a maker quote ONLY on (series × price-bucket × regime) cells
whose realized post-fill markout — measured from `tape/kalshi_trades/` — is positive net of the
maker fee. Counterparty: uninformed retail takers crossing the spread in cells where informed
flow is demonstrably absent. The maker earns the spread minus a MEASURED (not assumed) adverse-
selection charge. This operationalizes the S11 lane (registry `data-collecting` since 2026-06-18,
explicitly blocked on "the forward L2 tape for fill-intensity"), but the toxicity anchor is the
trade tape's OWN realized markout — no external Pinnacle de-vig, so it does not inherit Q18's
thin-odds dependency.

**Data (already-collected / free).** `tape/kalshi_trades/` (broker_truth prints + taker_book_side)
∩ `tape/orderbook_depth/` (real_bid/real_ask touch) ∩ Kalshi public settlement (broker_truth, the
same unauthenticated `GET /markets/{ticker}` path Q51 already caches).

**Falsifiable gate + kill.** Split the trade tape into a toxicity-TRAINING window and a disjoint
HOLDOUT (out-of-sample, to defeat the S20/L41 luckiest-cell trap); select cells on training
markout; on the holdout, block-bootstrap by GAME (L6) of net maker markout on selected cells;
**register-as-edge only if the holdout 95% CI > 0 at real prices net of the maker fee
(`core.pricing`, 0.0175 per L5), n_units ≥ 10 (L41), clearing the L27 tick gate.** KILL if the
holdout CI ≤ 0, or the selected population is below the 10-unit floor, or a train/holdout split is
not achievable.

**Why it survives its dead cousins (verifier-confirmed on committed tape).**
- vs S6/S13/S23/S68 (WALL-B, "adverse selection unmeasurable"): those *assumed* worst-case or
  were structurally blind (Q50/L253/L255: `touch` over `orderbook_depth` "has no channel through
  which adverse selection could appear"). The load-bearing claim that the trade tape fixes this
  **HOLDS**: on `dt=2026-08-03`, **39,327 / 39,698 prints (99.1%) have a later same-ticker print
  within 30 min (97.6% within 5 min)** — a subsequent-print path IS a post-fill markout, and
  `taker_book_side` gives the aggressor direction. S78's toxicity leg is the *trade* tape, so it
  escapes the L68/L106 kill, which is scoped to `orderbook_depth`-only candidates.
- vs Q51 milestone 2/3 (the UNCONDITIONAL sports maker, n=7, gated 08-10): S78 is CONDITIONAL and
  out-of-sample — a distinct object with a distinct failure mode, not a strict duplicate.
- vs S21 (died on L43 join-emptiness — no fills observable): `kalshi_trades` now supplies the
  fills S21 lacked (42/42 trade tickers join the depth tape).

**Why `collect-and-revisit`, not a probe now (verifier's mandated tightenings, adopted).** On the
one committed day (1 capture, 42 tickers, ~7 scoreable settled sports games) everything S78 could
*do* collapses onto Q51's exact population; a disjoint train/holdout with the same cells populated
on both sides is impossible, and the naive cell space (20 series × 10 buckets × 3 regimes = 600
cells) against ~7 units is the L41 luckiest-cell trap at full strength. So the registry line
carries three binding conditions: **(1)** pre-register a COLLAPSED cell design (a continuous
toxicity score, or ≤4 pre-declared cells e.g. favorite/dog × wide/tight) BEFORE seeing holdout
markout; **(2)** the gating tape is multi-day `kalshi_trades` aimed at book-covered tickers, which
depends on the Ryan-gated collector write-path (L221/L222) or Q47 `orderbook_delta` — the same
external gate as Q51; **(3)** the register-as-edge P&L still inherits Q51-m3's ≥10-game floor + L27
+ block-boot by GAME + maker fee via `core.pricing`. This is the S55 collect-and-revisit precedent,
not an edge and not a probe to run today.

## Surveyed, NOT registered (space searched, not padded — 07-29 precedent)

- **S79** (retail-buy-pressure NO-maker): genuine DUPLICATE of Q51 milestone-2's already-measured
  NO-bid-only leg (20 legs, 85% fill, mean +$0.0905, CI [−$0.1528, +$0.3252], n=7 inadmissible).
  A live item already covers it → not registered.
- **S80** (taker-flow-imbalance short-horizon continuation): foreclosed — directional taker eats
  WALL-A overround; S22 (OFI, dead-tested Q26) and S24 (near-close fade, dead-tested Q28) own the
  factor slot → not registered.

## Lesson candidate (deferred to kb-distiller)

The arrival of a NEW data surface can lift a standing idea-stage kill for the specific candidate
class the surface addresses — here `kalshi_trades` lifts L68/L106 (the "no trade/volume field, so
adverse selection is unconstructible" wall) for maker-spread candidates — **but only by moving the
blocker from "untestable-by-construction" to "not-collected-yet."** The correct disposition is
`collect-and-revisit` with the gating tape named, not a probe and not a revival of the dead
cousins. Also worth a one-line scoping note: L68/L106's kill is scoped to `orderbook_depth`-only,
not to any maker-spread idea once a trade/print tape exists.

## Consumed / next

Consumed S78/S79/S80 → **next free = S81.** Queue item **Q52** appended (S78 collect-and-revisit,
gated on multi-day trade tape). Two-agent rule at idea stage satisfied (producer + independent
`verifier` REGISTER-as-collect-and-revisit). No registry status flips to `live`; no CI; still
**0 proven edges.**
