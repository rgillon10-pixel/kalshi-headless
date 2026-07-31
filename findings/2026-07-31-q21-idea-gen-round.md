# Q21 idea-gen round — 2026-07-31 (kalshi-edge-hunter → independent verifier, two-agent rule)

**3 proposed, 0 registered.** Consumes S63/S64/S65 for provenance → next free **S66**. Still **0 proven edges**.
The **18th consecutive zero-registration round** (07-30 was the 17th; 07-29 the 16th).

## Why the round fired

Re-eligibility trigger met: a full Q0–Q48 file-shape rescan (L25) this session finds **0 eligible
TODO/IN-PROGRESS** items — every item is DONE, credential/auth-BLOCKED, calendar-gated-not-open, or
gate-open-but-density-inadequate (Q42/Q43's perp calendar gate is open but the VPS `:23` collector has
been dead since 2026-07-22, so `crypto_hourly`/`perp_tape` are cloud-only and density-inadequate). The
nightly **observatory** pass (07-30) also surfaced **0 candidates** this run — every persistent pattern is
graveyard-blocked (naive-maker-spread) or descriptive (liquidity-structure / queue-crowding / the parlay
universe-shift). Fewer than 2 eligible → the Q21 standing replenishment condition is satisfied.

The producer targeted the two least-mined structural corners left on committed tape: the
**hyperliquid_funding × crypto_hourly** join (a signal not yet used as a Kalshi settlement predictor) and
the **universe_sweep** commodity ladders (`-T` thresholds, the only real non-parlay markets in the breadth
tape). An independent `verifier` agent attacked each against the committed tape BEFORE any registration
(two-agent rule at the idea stage) and **CONFIRMED all three kills, correcting two producer numbers** — the
corrected numbers are what stand below (trust default = FALSE; the producer's first-pass counts were a
citation defect the verifier caught).

## The three candidates and their kills (producer + independent verifier, agreeing on KILL)

### S63 — Perp-funding-flip settlement predictor on Kalshi crypto-hourly brackets → KILL / signal-firing population below the L41 floor
Mechanism: a hyperliquid BTC/ETH funding sign-flip within the hour signals a positioning unwind that could
front-run a spot move; take the Kalshi hourly bracket in the funding-implied direction as a taker if the
move clears 2 taker fees. Counterparty: retail pricing the hourly off stale visible spot. Data:
`tape/hyperliquid_funding/` (a genuinely un-mined signal leg) + `tape/crypto_hourly/`.

**Kill (verifier, fresh tape — CORRECTS the producer's stated count).** The producer's stated check
("real-book event-hours with a joinable funding record < 10") was **factually wrong**: `crypto_hourly`
carries **748** real-`bracket_sum` event-hours with `broker_truth` settlement, and `hyperliquid_funding`
backfills **1391 hourly buckets (2026-06-03 → 07-30)**, so **748/748 are joinable** — the deep funding
history defeats the naive density kill. But the *tradeable unit is a flip-firing event-hour*, and funding
pins at the +1.25e-06 cap for long runs, so sign-flips are rare: only **~12** real-book event-hours carry a
flip in/around the event hour, of which only **3** have a captured `broker_truth` settlement to score, and
those cluster within days (KXETH-26JUL28-06/09/10 consecutive; KXBTC-26JUL29-15/16) — **not independent**.
3 scoreable, clustered ≪ the L41 floor of 10 independent units → `bootstrap_verdict_admissible` fails
before any real_ask CI can be built. Dead on adequacy, on the corrected count. (The producer's secondary
"settle≈spot ρ=0.9997 ⇒ can't beat spot" leg is a non-sequitur the verifier flagged — settle≈spot does not
refute a *within-hour directional* predictor; the real kill is the signal-firing unit count.)

### S64 — universe_sweep commodity-ladder threshold-monotonicity taker (KXWTIH/KXGOLDH/KXSILVERH) → KILL / 0 fee-clearing boxes over 25,866 pairs
Mechanism: nested `-T` threshold strikes must satisfy P(≥X) ≥ P(≥X+Δ); buy YES(lower)+NO(higher) when the
guaranteed-$1 pair costs < $1 + 2 taker fees at `yes_ask_size ≥ 10`. Counterparty: a stale-quote laggard on
one strike. Data: `tape/universe_sweep/` (the only committed family carrying a depth field).

**Kill (verifier, fresh tape — matches prediction).** Box scan over all 12 days, fees from
`core.pricing.fee_per_contract(TAKER_FEE_RATE)`: 42 snapshots, 1340 commodity rows with fillable YES,
**25,866** both-legs-fillable lower-YES/higher-NO pairs → **0 fee-clearing boxes** at `size ≥ 10`, and still
**0** with the size gate removed. The same 8¢-taker-round-trip floor that gave S3/S15 zero hits in 60 days;
the commodity ladders are the *tightly-priced liquid* markets, so no monotonicity violation ever clears the
fee. Confirmed dead.

### S65 — universe_sweep cross-sectional stale-BBO reversion on the commodity underlyings → KILL / independent-unit count below L41 (07-30 S61 re-skin)
Mechanism: a large `yes_ask_size` vs `yes_bid_size` imbalance predicts the mid drifting to the thin side by
the next sweep; ride it as a taker if the drift clears 2 taker fees.

**Kill (verifier, fresh tape — CORRECTS the producer's "3").** The real two-sided `universe_sweep` series
(`yes_bid>0 & yes_ask>0`, `real_ask`) are **four**, not three: KXWTIH (519 two-sided rows), KXSILVERH
(365), KXGOLDH (365), **and KXAAAGASD (14)** — an average-gas-price series the producer omitted. Four
*cross-correlated commodity* underlyings is still ≪ the L41 floor of 10 independent units (effective
independent count lower still), so it is inadmissible before any edge is even measured — the identical
bootstrap-unit collapse that killed 07-30's S61.

## Lesson candidate (deferred to kb-distiller — not appended to the ledger here, to avoid a merge conflict)

- **(S63 class — signal-conditioned density, sibling to L41)** A density/independence kill for a
  *signal-conditioned* strategy must count the event-hours where the **signal fires AND settlement is
  scoreable**, not event-hours where the book and the raw signal-source data merely co-exist. The producer's
  first-pass S63 check over-counted the tradeable population by ~60× (748 book+funding vs 3
  flip-firing-and-settleable). The kill survives only under the signal-firing count — and it is exactly this
  over-count that makes a naive "we have lots of joinable rows" reading look testable when it is not.

## Bottom line

Register-what-survives = nothing; the bar has not moved. All three kills are grounded in fresh committed-tape
re-runs and the two-agent rule is satisfied at the idea stage (producer + independent verifier, all KILL,
verifier CORRECTING two producer counts before they shipped). The round's compounding value: three fresh dead
angles (a funding-flow settlement predictor, a commodity-threshold box, a commodity cross-sectional reversion)
and one new signal-conditioned-density lesson candidate. Every angle collapsed to either a graveyard fee-floor
(S64) or the L41 independent-unit floor (S63/S65) — and the L41 failures are *properties of the frozen data
surface*: with the VPS collector dead 9 days, the signal-firing and cross-sectional populations are too thin
to bootstrap. The binding constraint remains the **DATA SURFACE, not idea capacity** — the same conclusion the
07-29 and 07-30 rounds reached. The one thing that would open genuinely new testable ground is a new MECE /
higher-cadence surface, i.e. Q47's `ws_depth` streaming family (still Ryan-gated on a working Kalshi key).
Consumed S63/S64/S65 → **next free = S66.** Still **0 proven edges**.
