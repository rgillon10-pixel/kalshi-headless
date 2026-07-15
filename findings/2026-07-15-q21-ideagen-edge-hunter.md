# Q21 idea-gen round (kalshi-edge-hunter nightly, 2026-07-15 04:15 UTC) — 0 survivors

Second Q21 round in 24h (yesterday's edge-hunter round #75 also produced 0; the research
loop's own #76 registered S28/S29). Eligible queue items = **1** (Q30/S29 only) < 2 →
replenishment triggered. Three candidates generated (research-lead), each attacked at the
idea stage before any registration (two-agent rule). **0 registered.** Still **0 proven edges.**

## S30 — Deep-two-sided wide-spread selective maker on illiquid foreign-sports books → KILLED (verifier)

**Thesis.** Foreign-sports books (KBO/NPB/BSN/foreign-soccer) carry abnormally wide *two-sided*
spreads (KBO median yes-spread 0.27, ~5–27× the flat 1¢ maker fee). Rest a maker quote inside
the spread; the width (claimed) comes from *absence of maker competition*, not adverse-selection
compensation, so the half-spread is nearly free money — the structural inverse of S6 (which died
because the 1¢ fee exceeded the modal 1–2¢ spread, and whose only CI>0 population was the >30¢
**one-sided** wing artifact, L31).

**The one surprising, real tape fact** (reproduced to the digit by both the edge-hunter and the
independent verifier, over `tape/orderbook_depth/dt=2026-07-14.jsonl`, 28,697 real_bid/real_ask
records): the wide foreign spreads ARE two-sided by record count — KXKBOGAME 840/840 two-sided,
median yes-spread 0.27; the inverse relation also holds (deep-size books have tight spreads: AFL
0.02 spr / ~2000-size, MLS 0.01, ECULP 0.03 / ~1650; thin-size books have wide spreads).

**Why it dies anyway (two independent kills):**

1. **The load-bearing "deep two-sided size at the wide spread" is a total-ladder lottery-ticket
   artifact — an L31 wing in a two-sided costume.** The "4,601 yes / 10,556 no contracts" backing
   the KBO spread is the *total ladder summed across all price levels*; the **top-of-book at the
   27¢ spread is 10 yes / 26 no contracts**, and **98.83% of the resting yes-ladder size sits at
   price ≤ 0.10** (verifier, per-record median). The thousands of contracts are deep-OTM lottery
   tickets (a 4,000-contract bid at 6¢) that will never be crossed at a spread-capturing price.
   The steelman doesn't escape: NPB 87.85% ≤0.10, BSN 75.90%. So "backed by real two-sided size"
   is **false at the top of book where capture must occur** — the two-sidedness is real only in
   the nominal-not-capturable tail (exactly what L31 covers).

2. **The discriminating claim is structurally unobservable on committed tape → can never reach
   the registration bar (L41).** S30's whole thesis rests on "width = absent competition, NOT
   adverse selection." Telling those apart requires observing fills and their correlation with
   subsequent price/settlement. `tape/orderbook_depth/` has **zero** trade/volume/last fields
   (schema is resting-depth snapshots only); the only sports executed-volume tape is
   `tape/sports_history_s7/worldcup2026.jsonl` (WC-only, L44) — **no KBO/NPB/BSN trade print
   exists anywhere in the tape.** A wide spread on a thin foreign book is equally consistent with
   both hypotheses and the tape cannot adjudicate; no adverse-selection-modeled block-bootstrap
   CI (L41 needs opposing-sign clusters, not toxicity assumed away) is constructible. Any
   "buy-at-resting-bid / hold-to-settlement" workaround is a directional longshot hold at
   queue-blind prices — the L39/L41 trap, not spread capture.

   Not the S6/L30 fee kill (KBO's ~13.5¢ half-spread genuinely dwarfs the 1¢ fee); it dies on
   *missing capturable size + unobservable toxicity*. Also: KXKBOGAME settles partly `scalar`
   (8/34 settled markets in the q26/q27 caches, L52) — the widest-spread family isn't even a
   clean binary P&L construction.

**Verdict: KILL-at-idea-stage** (verifier-decisive). Registering it would spend a research-loop
probe on a mechanism the committed tape cannot test.

## S31 — Crypto near-money last-capture reachability taker (hold-to-settlement) → idea-kill

Buy the near-money crypto-hourly bracket at the last pre-close capture and hold to settlement
(one taker fee, no exit round-trip). **Presumptively dead per the standing taker-into-overround
rule (S1/S5/S7):** you pay the ask, which is rich by construction; the near-money bracket would
have to be *under*-priced despite the overround, requiring a reachability lag larger than the vig
share — and at 2-captures/hour cadence with a data-starved settlement-instant spot conditioner
(`tape/crypto_hourly_historical_spot/` = 36 rows, 07-04 only; per-capture spot lags ~29 min, L8),
that lag is both unlikely and unobservable (S9/L57 cadence family). Distinct from S10 (which
covered only the 1¢-floor-pinned FAR/tail brackets, L26) but dies to the same overround wall.
Not registered.

## S32 — Crypto near-money two-sided maker-short (queue-aware) → folded into S14, not a new S-number

Rest a maker short-YES inside the two-sided spread on the liquid near-money crypto brackets.
This **is** S14's own explicit remaining binding gate (a queue-aware `orderbook_depth` short-YES
fill-sim over the crypto ladder), scoped to the two-sided legs — not a new candidate. Registering
it would duplicate an S-number and split S14's factor slot (Hard Rule #6 ρ). Confirmed near-money
crypto two-sided spreads are only ~3¢ (KXBTC median 0.03, 07-14), so the near-money-only slice
lands squarely in the L30 fee-floor regime — S14's ~9¢ proxy edge lives in the thin wings the
queue-aware sim is expected to strip. Routed to S14's open gate (Q29 in the unmerged #77);
recorded here so the round shows the crypto-overround-maker corner was re-examined and correctly
assigned, not re-registered.

## Round outcome

0 registered. Two consecutive 0-survivor idea-gen rounds (this + #75) with the research loop's
own #76 registering the only two current live ideas (S28 already tested DEAD, S29 still queued
Q30) is itself signal: **the free-data / already-collected-tape edge space is deeply mined.** The
remaining live levers are not new hypotheses — they are (a) executing Q30/S29, and (b) S14's
binding-gate queue-aware depth fill-sim, which needs ~30 event-days of `orderbook_depth` (currently
8) and whose queue item is stuck in the unmerged #77. Pipeline stays at 1 eligible item (Q30).

New lessons: **L67** (two-sided-depth illusion — decompose ladder depth by price band before
believing a wide two-sided spread is capturable) and **L68** (a maker-spread-capture idea over
`orderbook_depth` alone is toxicity-untestable by construction — no trade prints — and should be
killed at idea stage, not registered as "untestable").
