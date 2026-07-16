# Net buying pressure & the implied distribution — primary sources for the tail-overprice / variance-premium angle, and its REFUTATION on Kalshi crypto ladders

`cited` · 2026-07-16 · QF behavioral/variance-premium theme · new-literature half of the 2026-07-16 Q21 round (S35/S36/S37, all killed at idea) · trust=FALSE

**The thesis, stated for a near-money buyer.** The options literature documents that
**net buying pressure** distorts the *shape* of the implied distribution: demand for lottery-like
tail payoffs (retail buying cheap far-OTM options) bids up the tails relative to their objective
probability, which — if the risk-neutral density must integrate to one — is hypothesized to leave
the **near-money region relatively CHEAP** versus realized settlement frequency. The companion
result is the **variance risk premium**: options are, on average, expensive versus realized
variance (writers earn a premium for bearing variance risk). Put together, the tempting Kalshi
translation is: on a crypto "between"-ladder, the fillable near-money brackets should realize ABOVE
their ask because the retail-loved tail brackets soaked up the overpricing. This note distills the
primary sources, then records the **load-bearing empirical result — that on Kalshi crypto-hourly
ladders the thesis is REVERSED and/or unfillable** — so a future idea-gen round does not
re-propose it.

Every empirical claim below is tagged with its source. Literature magnitudes are the paper's; every
project number carries its `real_ask` / `broker_truth` / `synthetic` provenance.

---

## 1. Bollen & Whaley (2004) — net buying pressure shapes the implied-volatility function

**(1) Citation.** Nicolas P. B. Bollen & Robert E. Whaley, "Does Net Buying Pressure Affect the
Shape of Implied Volatility Functions?", *Journal of Finance* 59(2), 2004, pp. 711–753. `[classic]`

**(2) Market / sample.** U.S. index and individual equity options (S&P 500 index options and a
cross-section of stock options), intraday, matching signed option order flow to changes in the
implied-volatility function across strikes.

**(3) Headline magnitude.** Direction (exact coefficients `approx`): **changes in implied
volatility at a given strike are driven by the net buying pressure at that strike** — demand for a
particular part of the strike ladder moves that part's implied vol, and the effect persists rather
than being instantly arbitraged. For index options the demand concentrates in out-of-the-money
puts (crash insurance), steepening the skew; the shape of the smile is a demand artifact, not only
a belief artifact.

**(4) Mechanism it argues.** Market makers face limits to arbitrage (hedging is costly and
imperfect), so they cannot flatten the smile back to a single fair vol. Persistent one-sided demand
at a strike therefore leaves a **price footprint** at that strike — the implied distribution's
shape encodes where the buying pressure went.

**(5) Relevance to the Kalshi crypto ladders.** Supplies the *why* for the S35/S36 premise:
IF retail net buying pressure piles into the tail brackets of a crypto range-ladder, the
near-money brackets could be left cheap. It establishes the effect is demand-side and can persist —
but it says NOTHING about which *direction* the residual lands on a given venue, nor about whether
the near-money residual is fillable net of frictions. Those are the two things the venue test below
decides against the thesis.

---

## 2. Coval & Shumway (2001) — expected option returns and the variance risk premium

**(1) Citation.** Joshua D. Coval & Tyler Shumway, "Expected Option Returns," *Journal of Finance*
56(3), 2001, pp. 983–1009. `[classic]`

**(2) Market / sample.** U.S. index options (S&P 100/500), studying the average returns to holding
option positions (zero-beta straddles, delta-hedged positions) to expiry.

**(3) Headline magnitude.** Direction (magnitude `approx`): **option buyers earn systematically
negative average returns** even after hedging market-directional exposure — zero-beta straddles
lose money on average — which is the return-space signature of a **variance risk premium**: options
are priced above their actuarially fair (realized-variance) value, and the seller of variance earns
that premium.

**(4) Mechanism it argues.** Investors pay a premium to hedge/priced-in variance and jump risk, so
the risk-neutral distribution is fatter-tailed and options are, on net, expensive versus realized
outcomes. The counterparty who is short variance (and can bear it) is compensated.

**(5) Relevance to the Kalshi crypto ladders.** This is the theoretical warrant for expecting
SOME leg of a Kalshi crypto ladder to be systematically rich versus realized settlement — options
are, on average, overpriced. The naive S35 read hoped this overpricing was confined to the tails
(leaving near-money cheap). The venue test below finds the overpricing is instead spread across the
near-money region itself — the variance premium shows up as near-money RICHNESS, not near-money
cheapness.

---

## Synthesis — the LOAD-BEARING venue result: on Kalshi crypto-hourly ladders the thesis is REVERSED and unfillable

The 2026-07-16 Q21 round proposed three candidates (S35/S36/S37) built on sources 1–2 (plus, for
S37, the gambler's-fallacy strand, Rabin 2002 QJE / Terrell 1994 J. Risk & Uncertainty). An
independent `verifier` re-ran `tape/crypto_hourly/` and `tape/crypto_hourly_historical_spot/` for
each and killed all three at the idea stage. The refutation, tagged by provenance:

**(a) The near-money region is overround-RICH, not cheap.** Last pre-close capture (`real_ask`)
joined to `previous_settlement` broker_truth, taker fee via `core.pricing.fee_per_contract`:
BTC band ask-in-[0.07,0.34] n=181 realized win-rate **0.140** below mean ask **0.167**; ETH n=80
win **0.101** below ask **0.164**; BTC near-money [0.03,0.97] n=226 win 0.258 below ask 0.277; ETH
n=126 win 0.421 below ask 0.447. The realized win-rate is below the ask **before fees**, both
symbols, both band widths. Near-money sum-of-yes-ask runs a median **1.120** for BTC (+12¢, worse
than the +9.84¢ overround that killed S1). The variance premium (source 2) is real on this venue —
but it manifests as the near-money legs being expensive, exactly INVERTING source 1's hoped-for
"tails soak up the overpricing, near-money left cheap" translation. The overround is spread across
the near-money region, not concentrated in the wings.

**(b) The directional skew is one-sided and lives INSIDE the spread (maker-only).** The asymmetry
is entirely upside-overpriced (up mid 0.132 vs realized 0.104, ~2.8¢ rich at ATM±1); the downside
is fair (mid 0.104 ≈ realized 0.100). Only the ATM±1 band is two-sided (~61%); beyond it the
brackets are 1¢-floor-pinned one-sided books (two-sided fraction 3–18%, the S10/L26 mirror-wall).
The overround-neutral taker pair nets negative (k=1 n=281 mean −$0.0204, CI straddling zero; k=2
n=80 mean −$0.0879, CI strictly negative) because the ~0.7¢ genuine residual is swamped by two
crossed spreads + two taker fees. Any capture of this skew must be a MAKER-side quote, not a taker
pair (cross-references L26/L31).

**(c) There is no fillable ATM directional instrument.** The `crypto_hourly` "between" range-ladder
lists ~186 identical $100-wide brackets plus two tail caps (`less`/`greater`). A single near-ATM
bracket is a pin/volatility bet (non-monotonic in direction — it does NOT express P(up)). To trade
direction you must buy the STRIP of brackets above spot (`synthetic` spot from
`tape/crypto_hourly_historical_spot/`), which inherits a **bracket_sum of 2.89 (~189% overround)**
plus a per-leg 0.07 taker fee floor plus each leg's own half-spread. So a directional
gambler's-fallacy mechanism cannot be written as one fillable leg on this product — structural,
not a data-thinness problem.

**What the literature cannot tell you and the venue test can.** Sources 1–2 establish that
demand/variance premia distort the implied distribution and make options net-expensive — a genuine,
real effect. They do NOT tell you (i) which leg of a *particular* venue's ladder carries the
residual, (ii) whether that residual is fillable net of a 7% taker fee + per-bracket floor +
half-spread, or (iii) whether the product even offers a directional instrument. On Kalshi
crypto-hourly ladders the answers are: near-money (not tails), no, and no. This is the
new-literature diversity-floor distillation for the 2026-07-16 round — recorded with its refutation
so the thesis is not re-proposed.

## Citation hygiene (trust=FALSE)

Bollen & Whaley (2004) and Coval & Shumway (2001) are real, peer-reviewed *Journal of Finance*
papers verified from first-principles knowledge; the gambler's-fallacy strand (Rabin 2002 QJE
"Inference by Believers in the Law of Small Numbers"; Terrell 1994 J. Risk & Uncertainty) is
cited for S37 and likewise real. Where an exact coefficient or figure was uncertain it is marked
`approx` or stated as direction only, never fabricated — consult the primary source before any
magnitude sizes capital. The project's own numbers (near-money win-rates, sum-of-yes-ask median,
189% strip overround) carry their `real_ask` / `broker_truth` / `synthetic` tags and are
re-runnable from `tape/crypto_hourly/` and `tape/crypto_hourly_historical_spot/`.

## See also

- `findings/2026-07-16-q21-idea-gen-round.md` — the round this note is the new-literature half of
  (S35/S36/S37 verifier kills, the numbers above).
- `kb/lessons/00-lessons.md` **L87** (crypto near-money is overround-RICH, variance-premium thesis
  reversed) and **L88** (no fillable ATM directional instrument on the crypto range-ladder).
- `kb/strategies/00-index.md` S1 / S10 / S14 — the dead-cousin crypto-ladder verdicts this
  refutation lands squarely inside.
