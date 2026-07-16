# Q21 idea-generation round (2026-07-16, research-lead): 3 proposed, 0 survived idea-stage

`2026-07-16` · research-lead-orchestrated research loop · LOOP-QUEUE.md Q21 · two-agent rule
applied at the IDEA stage (an independent `verifier` re-ran the tape and attacked each candidate
before any registration) · **0 registry rows added**

## Why the round fired

Non-blocked, runnable-now research items in the queue = **0** (< the re-eligibility floor → Q21
STANDING re-eligibility trigger). The pipeline was drained of anything a cloud session could
actually run today:

- **Q19** — remaining per-event legs are TIME-GATED on the Jul-19 World-Cup-final and Jul-29 FOMC
  burst windows (no tape yet).
- **Q32 / Q33 / Q35-build / Q35** — all BLOCKED on Polymarket credentials (no cloud secret).
- **Q36 / Q37** — TIME-GATED on the freshly-restarted weather forecast/actuals tape (Q38 wired the
  collectors 2026-07-16; there is not yet enough committed weather tape to probe).

So Q21 re-fired to restock the hypothesis pipe, exactly the same shape as the 2026-07-15 round
(which also proposed 3 and registered 0 after its own two-agent idea-stage kills).

## The three candidates and their kills

Each was proposed by the research-lead with a named mechanism/counterparty, an
already-collected-or-free data source, a falsifiable gate + kill condition, and a "why it survives
its nearest dead cousin" argument. Each was then handed to an **independent `verifier` agent that
re-ran the relevant tape** (`tape/crypto_hourly/`, `tape/crypto_hourly_historical_spot/`) and the
nearest dead-cousin findings (S1, S10, S14, S24) before returning a verdict. **All three were
killed at the idea stage.** The three shared a common shape: single-leg or overround-neutral
HELD-TO-SETTLEMENT crypto trades on the `tape/crypto_hourly/` "between" ladders, drawn from the
net-buying-pressure / variance-risk-premium literature (Bollen & Whaley 2004; Coval & Shumway
2001) and the gambler's-fallacy literature (Rabin 2002 QJE; Terrell 1994). The diversity floor was
intended to be met by this new literature. All three died on the SAME tape reality (the per-bracket
overround is spread across the near-money region; there is no fillable directional instrument).

### S35 — near-money variance/tail miscalibration (held-to-settlement single near-money leg) → KILL-AT-IDEA

*Mechanism:* retail lottery demand overprices the tail brackets (net-buying-pressure /
variance-risk-premium), hypothesized to leave the fillable near-money brackets CHEAP relative to
their realized settlement frequency.

*Kill (decisive):* the near-money bracket is **RICH, not cheap.** The verifier re-ran
`tape/crypto_hourly/dt=2026-07-03..16`, took the last pre-close capture, and joined it to
`previous_settlement` broker_truth, taker fee via `core.pricing.fee_per_contract`:

- BTC band ask-in-[0.07,0.34], two-sided, n=181: realized win-rate 0.140 vs mean ask 0.167 → edge
  (win minus ask minus fee) **−$0.0409**.
- ETH n=80: win 0.101 vs ask 0.164 → **−$0.0771**.
- BTC near-money [0.03,0.97] n=226: win 0.258 vs ask 0.277 → **−$0.0336**.
- ETH n=126: win 0.421 vs ask 0.447 → **−$0.0395**.

The realized win-rate is below the ask **even before fees.** Near-money sum-of-yes-ask runs a
median 1.120 for BTC (+12¢, worse than the +9.84¢ overround that killed S1). This is L1/L12/S1
verbatim — the per-bracket overround share is spread across the near-money region, not concentrated
in the tails. Fillability is real but thin (median fillable-band count is 1 per BTC event, 0 per
ETH — the "5 brackets" example was event-dependent). Formulation (b), the overround-neutral pair,
is also dead: both individual legs are negative (BTC YES −$0.0409 and NO −$0.0244; there is no
cheap leg to be long), and buying NO on both rich legs is just shorting the near-money = S14 (DEAD,
L85). n is well above the ≥10 floor and not L41-degenerate (genuine 14% and 10% YES rates). This is
a quick calibration cut (last-capture, no block-bootstrap CI) but the SIGN is wrong and robust
across both symbols, both band widths, and pre-fee — decisive at the idea stage. → **lesson L87.**

### S36 — directional-skew asymmetry (overround-neutral pair, held to settlement) → KILL-AT-IDEA

*Mechanism:* bullish retail overbuys the upside brackets, hypothesized to leave the
symmetric-distance downside brackets cheap; go long the cheap downside bracket, short the rich
upside bracket, overround-neutral, hold to settlement.

*Kill (decisive):* the verifier built the pair over `tape/crypto_hourly/dt=*` (497 event-hours
captured near close, 451 with broker_truth from `previous_settlement`; block-bootstrap by
event-hour, 10k). Three compounding breaks:

1. **The "cheap downside" premise is FALSE.** Downside mid 0.104 ≈ downside realized 0.100 (fair,
   if anything a hair rich); the asymmetry is entirely UPSIDE-overpriced (up mid 0.132 vs realized
   0.104, ~2.8¢ rich at ATM±1), not downside-underpriced.
2. **That ~2.8¢ lives INSIDE the spread.** Only the ATM±1 band is two-sided (61%); at ATM±2 and
   beyond the brackets are 1¢-floor-pinned one-sided books (two-sided fraction collapses to
   3–18%), the S10/L26 mirror-wall.
3. **The 2-leg pair at real asks nets negative.** k=1 n=281 mean **−$0.0204**, 95% CI
   [−$0.0771,+$0.0369] (127 positive vs 154 negative units — non-degenerate, so a MEASURED negative
   with a zero-straddling CI = dead per L27, not untestable); k=2 n=80 mean **−$0.0879**, 95% CI
   [−$0.1552,−$0.0261], strictly negative. The ~0.7¢ genuine residual is swamped by two crossed
   spreads plus two taker fees.

No single-leg rescue (short-upside-only −0.3¢ after fee, long-downside-only −3.3¢). Same L58/S24
family: directionally real, unfillable by an order of magnitude. The residual lives inside the
spread → any skew candidate here must name a MAKER-side capture, not a taker pair. → **lesson L87**
(same near-money overround-rich reality); the maker-only corollary cross-references L26/L31.

### S37 — gambler's-fallacy serial-state conditional directional bet (held to settlement) → KILL-AT-IDEA

*Mechanism (Rabin 2002 / Terrell 1994):* after a run of consecutive same-direction hourly closes,
gambler's-fallacy retail overbets reversal, hypothesized to bias the implied P(up).

*Kill (decisive): STRUCTURAL instrument failure.* The verifier re-ran
`tape/crypto_hourly_historical_spot/` and the ladder tape. The crypto range-ladder lists 186
identical $100-wide "between" brackets plus one `less` and one `greater` tail; **there is NO
fillable ATM up/down binary.** A single near-ATM bracket is a pin/volatility bet ("closes in
[floor,cap)"), non-monotonic in direction — it does NOT express P(up). To bet direction you must
buy the STRIP of all brackets above spot: dozens of legs, each paying the 0.07 taker fee +
per-contract floor + its own half-spread, against a bracket_sum of 2.89 (~189% overround) that the
strip inherits. So the mechanism cannot be written as one fillable taker leg on this product.
Compounding walls:

- **Efficiency / fee:** hourly crypto is ~a random walk; any serial-conditional bias is sub-1% to
  low-single-digit %, an order of magnitude below the 7% taker fee (S24/L58) — worse here because
  the cost is the ladder overround.
- **Data adequacy:** `crypto_hourly_historical_spot` has only 1 committed day = 18 hourly closes
  each for BTC/ETH with holes at hours 06-09/14/20; BTC and ETH share the identical direction
  sequence UUUDUDUUUUDDUUDUU → only ~2–4 correlated qualifying post-run(≥3) event-hours vs the ≥10
  floor in `bootstrap_verdict_admissible`.

Realized closes ARE reconstructable at broker_truth from the ladder tape
(`previous_settlement.expiration_value`, 13 days), so the raw signal is collectible — but
collecting more does NOT remove the missing-directional-instrument or overround walls, which are
structural to the range-ladder product (the S10 graveyard). This is a structural KILL, not a
collect-more register. → **lesson L88.**

## Outcome

- **0 candidates registered.** No new rows in `kb/strategies/00-index.md`; still **0 proven edges**
  — the bar has not moved.
- The labels **S35 / S36 / S37 are consumed for provenance** (a killed idea stays recorded so a
  future round doesn't re-mint the number onto a different idea). The next free S-number is **S38**.
- **2 new lessons → L87 / L88** in `kb/lessons/00-lessons.md` (both ledger-only — an empirical
  venue fact and a structural product fact, neither statically assertable).
- One new kb distillation: `kb/quant-finance/net-buying-pressure-implied-distribution.md`
  (Bollen & Whaley 2004; Coval & Shumway 2001), which records the paper AND its refutation on our
  venue so the next round does not re-propose it.

This is the honest state of a well-mined surface. Three sound, novel-shaped candidates each died to
a real structural tape fact — crypto near-money is overround-RICH (not tail-concentrated), and the
range-ladder has no fillable directional instrument — not to a lazy dead-cousin match.

## Verification note (two-agent rule at idea stage)

Each candidate was attacked by an **independent `verifier` agent** that re-ran the relevant tape
(`tape/crypto_hourly/dt=2026-07-03..16`, `tape/crypto_hourly_historical_spot/`) and the nearest
dead-cousin findings (S1, S10, S14, S24) before returning a verdict. All three returned
KILL-AT-IDEA with the tape-grounded reasoning recorded above. No candidate reached registration, so
no registry status was changed and no probe was built. A killed idea costs one idea-gen round and
saves a full wasted probe run — the two-agent discipline working as designed.
