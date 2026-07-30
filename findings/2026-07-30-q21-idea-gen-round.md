# Q21 idea-gen round — 2026-07-30 (kalshi-edge-hunter → independent verifier, two-agent rule)

**3 proposed, 0 registered.** Consumes S60/S61/S62 for provenance → next free **S63**. Still **0 proven edges**.
The **17th consecutive zero-registration round** (07-29 was the 16th).

## Why the round fired

Re-eligibility trigger met: a full Q0–Q48 rescan (this session's step 0/0a/0b + the last week of
research-loop firings, all logged) finds **0 eligible TODO/IN-PROGRESS** items — every item is DONE,
credential/auth-BLOCKED, calendar-gated-not-open, or gate-open-but-density-inadequate. In particular
Q42/Q43's `_perp_days_available() >= 7` **calendar** gate is now open (13 forward `tape/perp_tape/`
day-files) but its per-day density has collapsed to **17–102 lines/day** (VPS `:23` collector dead
since 2026-07-22, cloud-only cadence) vs the ~30–48 passes/day the probe assumes — so it is
density-inadequate, not runnable, exactly as its own queue Status warned (L25 file-shape check, not
path existence). Fewer than 2 eligible → the Q21 STANDING replenishment condition is satisfied.

The producer (main context) deliberately targeted the **least-mined surface in the tape** —
`tape/universe_sweep/`, the full-universe BBO census. It is the only committed family that carries a
**depth field** (`yes_ask_size`), which is what killed S53's fillability leg; and a *within-event box*
is **self-settling** (exactly one YES bucket wins by construction), so it sidesteps the L9/L43
disjoint-window settlement-join wall that reduced S52 to single-family sports. Three candidates were
built to probe that corner from three angles. An independent `verifier` agent attacked each against
the committed tape BEFORE any registration (two-agent rule at the idea stage); producer cross-checks
agreed. **All three killed — each on a fresh tape number.**

**Honest overlap note (load-bearing).** S60 below is NOT a brand-new idea: it is the 2026-07-29 round's
**S57** ("is any MECE ladder ever *under*-round enough that buying every YES leg costs < $1 net of fees,
`core.pricing.true_arb_edge > 0`?") re-run on a **third** tape family. The 07-29 round already ran that
census on `crypto_hourly` (1 hollow-book false positive) and `weather_books` (1,097 apparent edge>0,
**0 fully-offered**) and killed it under **L168**. This round extends the same census to
`universe_sweep` and finds the same failure class — but it is still additive to the ledger, because it
establishes two things the 07-29 run did not: a **hard 20,000-line capture cap** that truncates real
MECE ladders out of the breadth tape entirely (an *adequacy* wall, not just a hollow-book artifact), and
that `universe_sweep`'s `event_ticker` grouping is a parlay-basket collection, not a partition — so the
"buy-all-YES box on the breadth tape" idea is now foreclosed across all three families that could host
it. S61/S62 are genuinely new angles.

## The three candidates and their kills (producer cross-check + independent verifier, agreeing)

### S60 — Complete-event "buy-all-YES-buckets" box on universe_sweep → KILL / `event_ticker` is not a MECE partition (extends 07-29 S57 / L168)
Mechanism: on a complete mutually-exclusive-and-exhaustive Kalshi event, buying 1 YES on every bucket
returns exactly $1.00 (exactly one bucket settles YES), so if `Σ(yes_ask) + Σ(per-leg round-up taker
fee) < $1.00` at `yes_ask_size ≥ 10` on every leg it is a belief-free within-venue lock. Self-settling
⇒ no settlement join needed. The novel angle vs 07-29 S57 was the **size field** (`yes_ask_size`, absent
on `crypto_hourly`/`weather_books`), which should let fillability actually be checked.

**Kill (both agents, fresh tape):** the `event_ticker` grouping does **not** identify a MECE partition.
Producer scan over `dt=2026-07-27/28`: **83** multi-member events have `Σyes_ask + per-leg fees < $1.00`
at `yes_ask_size ≥ 10` — and **every one** is a 2-member `KXMVESPORTSMULTIGAMEEXTENDED` /
`KXMVECROSSCATEGORY` auto-generated parlay leg with `Σyes_ask ≈ 0.004`. The verifier's independent
07-28 cut found **18/18** clearing a stricter screen, all the same parlay families, and inspected the
members: each is a giant AND-parlay over *different* team-slates, neither mutually exclusive nor
exhaustive — buying all N pays $1 only if one specific full-slate combo hits (≈2–14% probability) and
can pay **$0**. The `Σyes_ask ≈ 0.004` is the *fair price of a longshot parlay basket*, not an
underround box cost (the L31 incomplete-bracket artifact, now confirmed on a third family after 07-29's
crypto/weather instances). The genuinely-MECE `-B`/"between" ladders (KXBTC/KXETH) that DO pay exactly
$1 are **absent from `universe_sweep` entirely** (crowded out by the 20k line cap, see L-cand B); the
only real markets present — `KXSILVERH`/`KXGOLDH`/`KXWTIH` — use `-T` **threshold (nested/cumulative)**
tickers whose YES-sum-across-strikes is meaningless as a box. Secondary structural kill: `universe_sweep`
lines carry **no** `strike_type`/`expected_outcomes`/`completeness_ok`, so the gate's "provable bracket
completeness" is **unmeetable on this tape**. Kill condition met: **zero complete-MECE events sum below
par net of fees at fillable depth.**

### S61 — Yes-side depth-imbalance → same-market next-sweep (6h) BBO drift → KILL / bootstrap unit collapses to 3 correlated underlyings (L41)
Mechanism: within one market's `universe_sweep` time series (no settlement join), a large
`yes_ask_size` vs `yes_bid_size` imbalance at sweep t predicts the yes-mid drifting toward the thin
side by t+1; ride it as a taker if the drift clears 2 taker fees.

**Kill (verifier, fresh tape):** across all days, tickers with a real two-sided book
(`ya>0,yb>0,yas≥10,ybs≥10`) in ≥2 captures = **136**; excluding the 48
`KXMVE*` parlay tickers (which carry fake AMM sizes 20000/5000 — an L31/L32 frozen-quote artifact, not
a poster telegraph), the **88** real two-sided tickers are strikes of exactly **3 underlyings**
(silver, gold, WTI). All strikes of one commodity move with its spot, so a block-bootstrap-by-market
treating 88 strikes as independent is invalid; the honest independent-unit count is **3 ≪ the L41
floor of 10** — inadmissible before any edge is even measured. Compounding: the "6h drift" cadence the
proposal assumes **does not exist** — captures are irregular (40-minute gaps up to 24h), and a
commodity ladder rarely traverses the ~$0.04 (2 taker-fee) hurdle in these windows. Same S24
mean-reversion / lead-lag family; dies on unit-adequacy (S21-class), pre-killed for registration.

### S62 — Redundant-contract box: universe_sweep threshold vs crypto_hourly ladder for the same underlying → KILL / the two tapes share zero underlyings
Mechanism: a `universe_sweep` threshold market and the `crypto_hourly` ladder bucket for the same
underlying/strike/close must settle identically; cross them if their yes_asks diverge beyond 2 fees at
fillable size. Self-locking, single-venue.

**Kill (both agents, fresh tape):** the join set is **empty**. `crypto_hourly` across all days is
`{KXBTC: 725, KXETH: 722}` events — **BTC/ETH only** — while `universe_sweep`'s real (non-parlay)
underlyings are `KXWTIH/KXGOLDH/KXSILVERH/KXINXHUD/KXNDQHUD` with **no crypto series whatsoever**, so
`{universe_sweep reals} ∩ {KXBTC, KXETH} = ∅`. There is no pair of provably-equivalent contracts to
cross. Compounding (would kill it even if a pair existed): `crypto_hourly` carries **no size field** —
the exact defect that killed S53's crypto leg — so fillability on that leg is unverifiable. Kill
condition met on the first clause outright.

## Lesson candidates (deferred to kb-distiller — not appended to the ledger here, to avoid a merge conflict)

- **(S60 class — extends L168)** A low `Σ(yes_ask)` across an event's members is a lock ONLY if the
  members are a **proven MECE partition**. `universe_sweep`'s `KXMVE*` "events" are collections of
  independent AND-parlays — their YES-sum is a *probability sum*, not a box cost. Require
  `strike_type`/`expected_outcomes`/`completeness_ok` (as `crypto_hourly` carries) before any
  "sum-below-par" claim; a flat market list without a partition proof cannot source a box. L168's
  "require every leg `yes_ask>0` AND a real size" corollary now also needs a **partition proof**, and the
  `true_arb_edge>0` census is confirmed a hollow/incomplete-bracket false-positive generator on all three
  families it can run on (`crypto_hourly`, `weather_books`, `universe_sweep`).
- **(universe_sweep adequacy — new)** `universe_sweep` captures are **hard-capped at 20,000 lines** and
  ~96% saturated by auto-generated `KXMVESPORTSMULTIGAMEEXTENDED` (474,359 lines) +
  `KXMVECROSSCATEGORY` (82,607 lines) parlay series; real MECE ladders (crypto/weather) are truncated
  out entirely. Any *within-`universe_sweep`* cross-sectional strategy inherits an effective
  real-market universe of **~3 commodity underlyings + a thin sports tail** — check the post-cap series
  histogram before proposing. (Sharpens L105/L125's dead-tail census into a hard *adequacy* wall.)
- **(cross-tape join premise — new)** Before proposing a "redundant representation" cross-tape box,
  intersect the underlying sets first: `universe_sweep` (no crypto) and `crypto_hourly` (BTC/ETH only)
  are disjoint, so the pair set is empty regardless of price divergence. (The L9/L43 disjoint-window
  wall, in its cross-*family* rather than cross-*time* form.)

## Bottom line

Register-what-survives = nothing; the bar has not moved. All three kills are grounded in fresh tape
re-runs — S60 on the `event_ticker`-is-not-MECE artifact (83 phantom "locks", 18/18 parlay junk on the
verifier's cut), S61 on a 3-correlated-underlying bootstrap-unit collapse below the L41 floor, S62 on a
provably empty cross-tape join. No CI clears zero, no P&L claim, no registry table change (prose-note
precedent, matching the 07-15/16/18/19/20/22/24/25/29 rounds). Two-agent rule satisfied at the idea
stage (producer + independent verifier, all KILL). The round's compounding value is the extension of
L168's `true_arb_edge>0` census to a third tape family and the two new `universe_sweep` adequacy facts:
together they foreclose the "within-venue box on the breadth tape" class until a genuinely new
MECE-partition-proving surface (e.g. Q47's `ws_depth` streaming family, still Ryan-gated on a working
key) appears. The binding constraint remains the DATA SURFACE, not idea capacity. Consumed S60/S61/S62
→ **next free = S63.** Still **0 proven edges**.
