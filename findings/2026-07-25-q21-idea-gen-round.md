# Q21 idea-gen round — 2026-07-25 (kalshi-edge-hunter → independent verifier, two-agent rule)

**3 proposed, 0 registered.** Consumes S51/S52/S53 for provenance → next free **S54**. Still **0 proven edges**.
The **13th consecutive zero-registration round.**

## Why the round fired

Re-eligibility trigger met: a full Q0–Q47 rescan (this session's step 0/0a/0b + the last several
research-loop firings, all logged) finds **0 eligible TODO/IN-PROGRESS** items — every item is DONE,
credential/auth-BLOCKED (Q32 / Q33 / Q35-build / Q42-part3 / Q47), calendar-gated-not-open
(Q19 FOMC 07-29, Q37 ~08-05), or gate-open-but-density-inadequate (Q36 both legs, Q43). Fewer than
2 eligible → Q21 STANDING replenishment condition satisfied.

The producer (main context) proposed three falsifiable candidates chosen to probe **under-explored
corners** rather than re-tread the S48/S49/S50 dead slots from the 07-24 round; an independent
`verifier` agent attacked each against the committed tape BEFORE any registration (two-agent rule at
the idea stage). **All three killed** — but each kill is *informative* (fresh numbers, two reopen
conditions), not a re-run of a known kill. The binding constraint remains the DATA SURFACE, not idea
capacity (L130 mid-efficiency wall / L131 fill wall / L9/L43 disjoint-window).

## The three candidates and their kills (verifier re-run numbers)

### S51 — Cross-venue single-leg Fed-decision taker (Polymarket signal, Kalshi the only fee leg) → KILL / data-adequacy (n=0 settled)
Mechanism: use Polymarket's Fed-decision implied prob as a **free exogenous signal** (not a traded
leg — pay only ONE fee, on Kalshi); when it diverges from Kalshi's implied by > Kalshi overround
share + taker fee before an FOMC settlement, taker the Kalshi side toward Polymarket and hold to
settlement. Explicitly routes around **S34** (dead two-legged double-fee arb) by being single-legged
and around **S9** (dead sub-hourly lead-lag) by targeting settlement convergence, not minute lead-lag.

**Kill (re-run):** dies on **n = 0 settled FOMC events**, NOT on price provenance. A useful
correction to the S43 prior: the Kalshi Fed leg is **`real_ask`** — `tape/polymarket_macro_pairs/`
(`family="fed_decision"`) carries `kalshi.price_source_tag="real_ask"` on all 8,850 rows (unlike the
`polymarket_cpi_pairs` Kalshi leg, which the verifier re-confirmed is 100% `synthetic`/`derived_prob`).
But only **3 distinct FOMC meetings** are tracked (2026-07/09/10 × 5 buckets = 15 tickers); Sep/Oct
settle in the future, and `tape/settlement_ledger/` has **zero** `KXFEDDECISION` rows (every "FED"
grep hit is a hex substring inside `KXMVE…` sports tickers). 3 tracked, 0 settled ⇒ a
settlement-convergence bootstrap (needs ≥10) has 0 — the divergence→settlement link cannot be
measured even once. **Reopen condition (concrete):** ≥10 FOMC decisions settled with both real_ask
Kalshi + real Polymarket legs — many months out at ~8 FOMC/year, but the tape leg is real and
already collecting, so this is a genuine "collect and revisit," not a dead factor.

### S52 — Settlement-ledger pooled reliability-curve taker (all families) → KILL / collapses into S1/S5/S7 overround
Mechanism: pool EVERY settled market in `tape/settlement_ledger/` (`broker_truth`) with a pre-close
`real_ask`, bin by implied prob, find any band where realized win-rate − price > overround share +
taker fee, out-of-sample. Claimed to beat S1's single-family thinness by pooling ALL families over
the large realized settled set.

**Kill (re-run):** the join is real (`result∈{yes,no}` recovers win/loss, joins by ticker to
`orderbook_depth` `best_yes_ask`) but it **guts the premise**. Of **10,605** settled markets only
**605 (5.7%)** have a non-degenerate `0<ask<1` pre-close real ask (the **L9/L43 disjoint-window
wall**), and those 605 are **100% sports** (`KXMLBGAME`/`KXUECLGAME`/`KXNPBGAME`/`KXUCLGAME`/
`KXWNBAGAME`/…) — every econ/crypto/weather settled market fails to join a pre-close real ask, so
"pool ALL families" silently reduces to single-family sports. The `universe_sweep` join variant is
worse: 27 non-degenerate rows on a **single** settlement day (07-22), 17 of them one
`KXSILVERH-26JUL2205` strike ladder → the specified block-bootstrap-by-day has **n_blocks=1**. Priced
honestly (520 markets / 322 games, game-level bootstrap): pooled yes-side calibration EV
**−0.033/contract, 95% CI [−0.044, −0.021]** (strictly negative); the two small positive bins (0.6,
0.8) are thin-n cherry-picks. It IS single-family sports calibration reached by a different tape
join, swamped by the real-ask overround exactly as **S1/S5/S7** documented.

### S53 — Near-money [0.90,0.99] "winner-certain" pre-settlement taker → KILL / CI straddles zero
Mechanism: distinct from **S10** (far-tail floor-pinned to a $1.00 NO ask) and **S28** (sports books
empty AT close) — buy a NEAR-money almost-certain winner (implied ∈ [0.90,0.99]) at a fillable ask
< $1 on a family whose book does NOT empty (crypto range-pin), hold to settlement, clear the fee.

**Kill (re-run):** genuinely occupies **new mechanism space** and is joinable — `tape/crypto_hourly`
self-joins `previous_settlement.results` (`broker_truth`, per-bracket) to `current.outcomes[].yes_ask`
(`real_ask`) on books that don't empty, so it clears the joinability and non-emptiness attacks. It
dies on the **gate**: near-money population = **106 bracket-rows / 106 distinct events**, realized
win-rate **0.962** vs avg paid ask **0.945**, fee 0.01 → point EV **+0.76¢/contract**, but the
calibration edge is 1.7pp ± ~1.9pp SE (noise); event-level bootstrap 95% CI **[−0.033, +0.039]**
straddles zero (~5× the point estimate). Concentrated in one 3-week window, 75% one symbol (ETH 79 /
BTC 27, autocorrelated). And `crypto_hourly` outcomes carry **no `yes_ask_size`** — the 0.945 ask is
BBO with unverifiable depth, so even the positive-looking point is not confirmed fillable at size.
Killed by the **CI-straddles-zero rule** (a straddling CI is dead, not promising — L27/S23 family).

## Lesson candidates (deferred to kb-distiller, not appended here to avoid a ledger merge conflict)

- **(S52 pattern)** A "pool ALL families" calibration claim must be checked against the *realized*
  `settlement ∩ pre-close-real-ask` join, not the settlement set alone: non-sports settled markets do
  not join a pre-close real ask (disjoint collector windows, L9/L43), so any pooled-calibration idea
  silently reduces to single-family **sports** and re-collapses into the S1/S5/S7 overround wall.
- **(S53 pattern)** A favorite-band near-money edge on crypto hourlies with a positive *point* EV is
  presumptively dead until event-bootstrapped: the [0.90,0.99] band's net-of-fee CI straddles zero
  (n≈100, one 3-week window), and `crypto_hourly` carries no `yes_ask_size` so depth is unverifiable
  regardless of the point estimate.
- **(S51 note, not a kill lesson)** The Kalshi **Fed-decision** leg in `tape/polymarket_macro_pairs/`
  is `real_ask` (contrast the `synthetic` CPI leg) — a cross-venue single-leg Fed taker is
  **collect-and-revisit**, reopenable once ≥10 FOMC decisions settle, not a dead factor.

## Bottom line

Register-what-survives = nothing; the bar has not moved. All three kills are grounded in fresh
tape re-runs: S51 on a hard n=0 (with a real, reopenable tape leg), S52 on the L9/L43 disjoint-window
+ S1/S5/S7 overround wall (CI strictly negative), S53 on a CI straddling zero in genuinely new
mechanism space. No CI clears zero, no P&L claim, no registry table change (prose-note precedent,
matching the 07-15/16/18/19/20/22/24 rounds). Two-agent rule satisfied at the idea stage (producer +
independent verifier, all KILL). Consumed S51/S52/S53 → **next free = S54**. Still **0 proven edges**.
