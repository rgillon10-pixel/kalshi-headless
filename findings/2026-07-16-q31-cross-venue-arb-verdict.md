# Q31 — Cross-venue tradeability backtest (Kalshi↔Polymarket, two-legged real asks) — verdict: DEAD

`2026-07-16` · research loop · two-agent-confirmed (independent verifier, general-purpose agent
acting under the two-agent verdict rule) · registry: **S34 — dead ✗**

## Mechanism

Kalshi and Polymarket often quote nearly the same price for matched events (S9 first cut,
2026-07-04: mean gap +0.20¢, range −3¢/+3¢ across 48 WC-round markets). Now that Ryan can trade
both venues (the 2026-07-15 "regime change"), a genuine two-legged arb is possible: buy YES on
the cheaper venue + buy NO (same underlying event) on the dearer venue — exactly one leg pays $1
regardless of outcome, so if the combined cost net of BOTH venues' fees is < $1, that is a
locked-in profit. The queue's own honest expectation was "probably DEAD" (S9's parity prior is
tight and fees now bite both legs) — this run confirms it cleanly.

## Data-coverage limitation (stated up front, per CLAUDE.md trust defaults)

`collection/polymarket_pairs.py` / `collection/polymarket_macro_pairs.py` capture ONLY the
Polymarket "Yes" outcome token's `best_ask`/`best_bid` (`outcomes.index("Yes")`) — there is no
captured Polymarket NO-token ask anywhere in the tape. So the two-legged arb is fully computable
with real resting asks on **both** legs in exactly one direction: **buy Polymarket YES + buy
Kalshi NO**. The mirror direction (Kalshi YES + Polymarket NO) is not testable here — deriving a
Polymarket NO ask as `1 − best_bid` would be a mid/bid-derived synthetic price, forbidden by this
milestone's own gate (3). This is a genuine tape-coverage gap, not an excuse; closing it is a
future collector milestone (candidate: extend `polymarket_pairs.py` to also fetch the NO-token
book).

## Method

- Script: `scripts/q31_cross_venue_arb_probe.py` (read-only, offline, no network).
- New fee primitive: `core.pricing.polymarket_fee_per_contract` +
  `POLYMARKET_US_TAKER_RATE = 0.05` (Polymarket Fee Structure V2, US/QCX venue taker rate;
  sourced + cited in the module comment). Same `rate·p·(1−p)` shape as Kalshi's fee, but no
  round-up-to-cent (USDC settles to 6 decimals). No fee arithmetic hand-rolled elsewhere —
  `scripts/invariants.py::inv_no_handrolled_fee_rate` stays green.
- Population: `tape/polymarket_pairs/` (WC-round) + `tape/polymarket_macro_pairs/`
  (Fed-decision) — both carry `real_ask` on both legs. `tape/polymarket_cpi_pairs/` excluded
  outright (its Kalshi leg is a `synthetic` differenced probability, fails the both-legs-real_ask
  gate).
- Value per observation = `1 − (polymarket_yes_ask + kalshi_no_ask) − both fees`.
- Bootstrap unit = matched pair (family, Kalshi ticker) — L6 clustering, not raw rows — via
  `core.bootstrap.block_bootstrap`, routed through `bootstrap_verdict_admissible` +
  `clears_tick_magnitude`.
- L32 dual cut: frozen-inclusive vs movement-conditioned (a frozen consecutive snapshot pair is a
  no-fill, not free income).

## Numbers (primary: Polymarket US taker 0.05, Kalshi taker 0.07)

- Priced observations: **13,158** (19 skipped for missing/failed leg, all genuine
  `best_ask=None`/`book_fetch_ok=False`, never silently zero-filled).
- Matched pairs / bootstrap clusters: **63** (48 WC-round + 15 Fed-decision).
- Fillable-arb frequency (net cost < $1): **260/13,158 = 2.0%**.
- Gross (pre-fee) cost < $1: **1,988/13,158 = 15.1%** — parity is mostly violated even before
  fees enter.
- Pairs with a positive mean net edge: **0/63**.
- Pooled mean net edge: **−0.03398** (range [−0.3725, +0.1832]).
- **Primary block-bootstrap-by-pair: mean −0.03398, 95% CI [−0.04172, −0.02680]**, n_units=63,
  n_obs=13,158. Admissible-for-positive = **False** (`no_opposing_unit` — no pair is on the
  positive side); `clears_tick_magnitude` = **False**.
- L32 dual cut (frozen fraction 0.760): frozen-inclusive CI as above; **movement-conditioned CI
  [−0.04231, −0.03163]** (n_units=54, n_obs=3,153) — both cuts strictly negative, robust to
  either fill assumption.
- Persistence: 84.2% of visible net>0 snapshots "survive" to the next capture inclusive, but
  75.9% of consecutive pairs are frozen (no book movement); conditioned on the book actually
  moving, persistence collapses to **34.9%** — the apparent persistence is a frozen-quote
  artifact, not a re-offered fillable arb.
- Sensitivity (fee-free Polymarket, most generous): pooled mean −0.02755, 95% CI
  **[−0.03441, −0.02139]**, 0/63 positive-mean pairs — the kill does not depend on the fee
  assumption.

## Gates

1. **Resolution-equivalence** — PASSED. Only WC-round and Fed-decision families included (same
   criteria/source/timing on both venues); CPI family excluded. Residual settlement-source risk
   (Polymarket international resolves via UMA, Kalshi centrally) carried on every number as
   capital risk, not treated as non-equivalence.
2. **Provenance** — PASSED. Every number is explicitly the international CLOB (`clob.polymarket.com`),
   never claimed as a Polymarket-US fill.
3. **Both legs real resting asks** — PASSED. No `outcomePrices`/last/mid reference used.
4. **Capital/settlement friction** — noted, not modeled away (two funding pools, USDC bridging
   $5–30, no instant rebalancing) — additive on top of an already-negative edge.
5. **Positivity gate** — FAILED. CI upper bound < 0; inadmissible; fails tick-magnitude.

## Verdict

**DEAD (falsified at real two-legged asks, net of both fee models).** Across 13,158
resolution-equivalent snapshots over 63 matched pairs, the two-legged cost to lock $1 is ≥ $1 for
essentially all pairs — 95% CI strictly below zero, 0/63 pairs positive, and the 2.0% of
transiently net-positive snapshots do not survive once the book actually moves. Robust to the
Polymarket fee assumption and to the L32 movement cut. Confirms the S9 parity prior: fees now
bite both legs and the ~parity gap leaves nothing. The mirror direction remains structurally
untested (no captured Polymarket NO ask), but the parity structure makes a positive result there
implausible.

## Verification

Independent verifier (general-purpose agent, adversarial mandate) re-ran both gates
(`pytest`, `invariants --full`), independently re-derived the headline numbers from raw tape
(bypassing the probe script), re-ran the fee-free-Polymarket sensitivity, bucketed by ticker and
by price band to check for a masked positive subpopulation (none found — all 63 tickers and all
11 price bands negative-mean), confirmed the Polymarket NO-token data gap by reading the
collector source directly, confirmed the CPI exclusion is double-enforced (glob + schema filter),
and hand-checked all 19 skipped records. **Verdict: CONFIRMED.**

## New lessons (candidates for `kb/lessons/00-lessons.md`)

1. Cross-venue "same price" + fees on both legs is a structural parity kill: with a tight
   steady-state price gap and both venues charging a `p·(1−p)`-shaped taker fee, the two-legged
   lock cost sits several cents above $1 on average — the "one free leg" premise (S9) is dead
   once both legs cost money.
2. A cross-venue persistence number is a frozen-book trap (generalizes L32 beyond maker spreads
   to cross-venue snapshot pairs): always split "does the dislocation persist" by whether the
   book actually moved between captures — inclusive vs movement-conditioned persistence differed
   by 50 points here (84% vs 35%).
3. Polymarket's fee is unrounded (`rate·p·(1−p)`, no round-up-to-cent), unlike Kalshi's
   ceil-to-cent — reusing `fee_per_contract` for a Polymarket leg would overstate its fee at
   interior prices; now encoded as a distinct `polymarket_fee_per_contract`.
4. `polymarket_pairs`/`polymarket_macro_pairs` capture only the Yes-token book — any future
   cross-venue two-legged probe can only test the Polymarket-YES + Kalshi-NO direction until a
   collector milestone adds a Polymarket NO-token capture leg.

## Artifacts

- `scripts/q31_cross_venue_arb_probe.py`, `tests/test_q31_cross_venue_arb_probe.py` (17 tests)
- `core/pricing.py`: `POLYMARKET_US_TAKER_RATE`, `polymarket_fee_per_contract`
