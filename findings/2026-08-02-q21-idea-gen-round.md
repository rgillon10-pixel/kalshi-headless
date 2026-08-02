# Q21 idea-gen round — 2026-08-02 (kalshi-edge-hunter → independent verifier, two-agent rule)

**3 proposed, 0 REGISTERED.** Round #20. Consumes S69/S70/S71 for provenance → next free **S72**.
Still **0 proven edges.** This is a valid honest outcome — a DEAD verdict at the idea stage is a
success. The one survivor of the whole month, S68, was itself killed the day before this run
(Q49 `DEAD-by-fee`, Q50 tighter-gate re-derivation, both verifier-CONFIRMED), so the registry is
back to 0 live `idea`-stage candidates and 0 proven edges.

## Why the round fired

Full Q0–Q50 file-shape rescan (L25): **0 eligible TODO/IN-PROGRESS** items — the same finding as
every rescan for two weeks. Every item is DONE, credential/auth-BLOCKED (Q14/Q15/Q32/Q33/Q35-build/
Q47), calendar-gated-closed (Q19/Q48 burst events fired; Q37 gate ~19/21 real summer contract-days,
opens ~08-04), or density-inadequate (Q36/Q42/Q43 — VPS `:23` collector dead since 2026-07-22,
11 days). The apparent-TODO items were each re-confirmed NOT eligible by file shape: Q9/Q11/Q12/Q16
sit on dead or superseded strategies (S13/S15/S17/S6 — S17 has three burst findings, S6 dead), Q23
(S19) and Q27 (S23) both carry DEAD verdict files under older TODO lines, Q24 is DONE/DEAD. Fewer
than 2 eligible → the Q21 standing replenishment condition is satisfied.

## Posture: last-corner probes, not re-skins

After 20 rounds and 20 dead strategy families, the mechanism space on the *current frozen tape* is
close to exhausted. The two structural walls are fully mapped: **taker → overround** (dead
S1/S5/S7/S52) and **maker → unmeasurable fill** (dead S6/S13/S14/S23/S68 — no trade-print field on
any committed family, so adverse selection is unmeasurable). Each of the three candidates was
constructed to route around BOTH walls and to probe a genuinely un-mined corner, using only
already-collected tape (no new data is possible — VPS dead 11d). An independent `verifier` agent
attacked all three on committed tape BEFORE any registration (two-agent rule at the idea stage) and
returned **KILL / KILL / KILL**.

## The three candidates

### S69 — Local convexity (butterfly) violation taker on MECE crypto strike ladders → KILL
Mechanism: a 3-strike butterfly (buy K−, buy K+, sell 2×K0, all taker) is riskless-bounded if local
curvature on a `crypto_hourly` ladder is violated beyond the 3-leg fee — routing around the
completeness/hollow-book wall that killed S57/S60 by needing only 3 offered legs, not the whole set.
**Kill (verifier, re-derived): two independent structural kills.** (1) `crypto_hourly` outcome
records carry **zero size/depth fields** — "every leg offered at real size" is unverifiable by
construction (the S53/S66/S67 field-availability wall). (2) The ladder is **8,029 `between` brackets
vs 62 `greater`/62 `less`** caps; a `between` price is the probability *mass* over a range, not a
"settles-above-K" CDF value, so the convexity/butterfly no-arb (2nd difference of a CDF ≥ 0) is
**ill-defined** on it (L88), and the OTM legs sit at the 1¢ yes_ask floor with `yes_bid = 0` (hollow,
S57/L168). Nearest dead cousin S33/S14 — the locality dodge is real but dies one level down on the
missing size field + the range-pin ladder type.

### S70 — Tight-spread near-certain favorite pre-close taker (orderbook_depth ∩ settlement) → KILL
Mechanism: restrict to `orderbook_depth` game books with two-sided spread ≤ 3¢ (the tight,
low-overround subset) AND best_yes_ask ≤ 0.97; buy YES at ask, hold to settlement — the explicit
test being whether any tight-overround game population exists where a small favorite-longshot
residual beats the ~1¢ taker fee. **Kill (verifier): the population EXISTS and clears L41 — 549
trades across 311 games / 18 series — so the "tight books don't exist, n≈0" escape hatch fails; but
every cut straddles zero net of taker fee.** Stated cut: mean **−$0.00426**, block-boot-by-game 95%
CI **[−0.0187, +0.0102]**, by-series **[−0.0249, +0.0177]**. Favorite steelman ask≥0.90: +$0.0273
point but CI-by-game **[−0.0063, +0.0466]** still straddles; ask≥0.80 and ask≥0.65 also straddle.
This is the **strongest kind of kill** — a genuine, adequately-powered CI falsification (311 games,
not a data-adequacy dodge): the S52/S1 overround wall reasserts even inside the tight-spread subset.
Nearest dead cousin S53 (crypto near-money, no size) / S28 (post-close) — S70 improves on both
(real game depth, pre-close, tight-spread conditioning) and still dies, which *sharpens* the wall.

### S71 — Real-funding-extreme directional taker on crypto-hourly binary → KILL
Mechanism: use RAW `hyperliquid_funding` (not the clamped `funding_rate_estimate=0.0` that killed
S49); when 1h funding is top/bottom decile, take the directional side of the nearest `crypto_hourly`
binary the funding sign predicts. **Kill (verifier): the S49 differentiator HOLDS on one axis — raw
HL funding is genuinely un-clamped (BTC 641 distinct rates, ETH 604) — but three other kills bind.**
(1) L88: `crypto_hourly` is the same `between` range-ladder; a directional bet requires buying a
multi-leg strip through a **~200% overround** (`bracket_sum` 3.02 on a live BTC ladder) — no fillable
directional binary exists. (2) Clamp degeneracy resurfaces on the *joinable* population: >55% of
funding hours sit at exactly the **+1.25e-05 cap**, and on the 285 join-eligible hours even the 10th
AND 90th percentile are both 1.25e-05 — an "extreme decile" is **inseparable**. (3) Hit-rate ≈
coin-flip and **sign-inconsistent**: fading extreme funding gives BTC **0.464** / ETH **0.571**
(the two symbols point opposite ways), the S49 0.49 signature through a different door.

## Lesson candidates (deferred to kb-distiller — prose note here to avoid a ledger merge conflict)

1. **(S70 class — the overround wall is now CI-falsified on a tight-spread, adequately-powered game
   population, not just data-adequacy-blocked.)** Prior overround kills (S52) leaned partly on a
   disjoint-window join reducing n; S70 clears L41 with 311 games and *still* straddles zero net of
   the taker fee at every ask cut. The tight-spread favorite residual is real in sign (+2.7¢ at
   ask≥0.90) but statistically indistinguishable from zero — the overround eats it. Record as a
   sharpened S1/S52 corollary: on Kalshi game books there is no taker-realizable favorite-longshot
   edge even in the lowest-overround (≤3¢-spread) subset.
2. **(S71 class — un-clamped ≠ separable.)** Raw Hyperliquid funding carries genuine variance
   (differs from the S49 clamped-estimate kill), yet is pinned at the +1.25e-05 cap for >55% of
   hours, so a funding-extreme decile cut is degenerate on the joinable `crypto_hourly` population
   even though the field is populated. The S66/S67 field-availability lesson covers "is the field
   populated"; this adds "is the signal's *extreme* separable" as a distinct pre-bootstrap gate.

## What stays true

The binding constraint that has held all month is unchanged and this round is its cleanest
confirmation yet: **idea capacity is not the limit — the data surface is.** Both walls are mapped,
and the one tape family that would break the maker-fill wall (a trade-bearing feed) is exactly the
Q47 `orderbook_delta` WebSocket daemon — BUILD DONE, activation Ryan-gated on a working API key.
Until that or a comparable trade-print surface lands, further idea-gen rounds will keep returning
KILLs on the same two walls. Consumed S69/S70/S71 → **next free = S72.** Still **0 proven edges.**

## Price source tags

All candidate re-derivations by the verifier used `real_ask`/`real_bid` (fills), `broker_truth`
(settlement), taker fee 0.07 via `core.pricing.fee_per_contract` (verified TAKER_FEE_RATE=0.07). No
synthetic price used as a fill. Tape read: `tape/crypto_hourly/`, `tape/orderbook_depth/`
(dt=2026-07-07..08-01), `tape/settlement_ledger/`, `tape/hyperliquid_funding/`, `tape/perp_tape/`.
