# Q21 idea-gen round — 2026-07-24 (kalshi-edge-hunter → independent verifier, two-agent rule)

**3 proposed, 0 registered.** Consumes S48/S49/S50 for provenance → next free **S51**. Still **0 proven edges**.

## Why the round fired

Re-eligibility trigger met: a full Q0–Q47 rescan (this session's step 0/0a/0b + the last several
research-loop firings, all logged) finds **0 eligible TODO/IN-PROGRESS** items — every item is DONE,
credential/auth-BLOCKED (Q1-odds / Q32 / Q33 / Q42-part3 / Q47), calendar-gated-not-open (Q19 FOMC
07-29, Q37 ~08-05), or gate-open-but-density-inadequate (Q36 both legs, Q43). Fewer than 2 eligible
→ Q21 STANDING replenishment condition satisfied.

The producer (main context) proposed three falsifiable candidates; an independent `verifier` agent
attacked each against the committed tape BEFORE any registration (two-agent rule at the idea stage).
**All three killed** — the 11th consecutive zero-registration round. The binding constraint remains
the DATA SURFACE, not idea capacity (L130 mid-efficiency wall / L131 fill wall).

Diversity-floor (spec rule 3) satisfied: **S48** is a NEW market family (commodities) the registry
has never touched — neither a dead-verdict inversion nor an existing QF theme.

## The three candidates and their kills (verifier re-run numbers)

### S48 — Commodity daily-close settlement-basis ρ-guard (KXWTIH oil / KXGOLDH gold / KXSILVERH silver) → KILL / UNVERIFIABLE
Mechanism: Kalshi settles these daily-close ladders on an exchange settlement reference while retail
prices off continuously-visible spot; a basis divergence would misprice the bracket holding the true
settle (S8 shape, but on a settlement PRICE with hard market closures rather than a 24/7 index).

**Kill (re-run):** the strategy's own core gate — an S8-shape ρ-guard vs **public spot-at-settle** —
is **UNVERIFIABLE**: there is no committed commodity spot/settlement-reference series anywhere in
`tape/` (only `crypto_hourly_historical_spot/` exists). Fails CLAUDE.md's re-runnable-script bar.
And the empirical panel does not exist: commodity events with a pre-close book in
`tape/universe_sweep/` = **24**; with a settled outcome in `tape/settlement_ledger/` = **4**;
intersection (both) = **exactly 1** (`KXSILVERH-26JUL2205`, partial) — the textbook L9/L43
disjoint-collector-window join. Liquidity is a quoted-but-**untraded** census: of 440 `KXWTIH`
sweep rows, `open_interest>0` on 23, `volume_24h>0` on **2**; `KXSILVERH` `volume_24h>0` on 2/320
— effectively no counterparty. Also `settlement_ledger.settlement_value` is the binary payout
(yes=1.0/no=0.0), not the underlying settle price, so even the outcome leg needs ladder-crossover
reconstruction. Collapses into **L9/L43** (disjoint window), **L96** (universe_sweep census can't
feed a settlement-joined per-market panel), and the **S1/weather overround** death. Also needs a
dedicated commodity settlement collector (Ryan-gated collector lane) before any probe is runnable.

### S49 — Perp-funding-sign directional predictor for the crypto hourly binary → KILL
Mechanism: extreme perp funding = crowded leverage → mean-revert the hourly binary in the opposite
direction; funding as an exogenous signal for a bounded real_ask instrument (distinct from S42's
funding-CARRY hold).

**Kill (calibration precheck, re-run):** over the perp∩hourly window (07-17→07-23), 100 BTC/ETH
directional hourly events joined a pre-close funding read; funding-sign-reversion hit-rate =
**49/100 = 0.490 — below a coin flip** → the mandated calibration gate fires. Mechanistic cause:
`funding_rate_estimate = 0.0` on **95/95 BTC and 95/95 ETH** reads (nonzero: 0) — the Kalshi perp
funding is clamped/degenerate exactly per the **S42/L105** kill, no variance, so the signal is
undefined on 96/100 events (1/4 on the nonzero handful). Secondary independent wall: `tape/crypto_hourly/`
is a 188-member **"between" range-pin ladder** (`bracket_sum=3.53`), **not** a directional up/down
binary (**L88**) — even a real signal couldn't be expressed without buying into ~3.5 aggregate
overround at the 0.07 taker rate (L12 / mid-efficiency wall). Collapses into **S42 + L88**.

### S50 — Weekend/holiday-gap stale-ask maker fade on commodity ladders (S48's maker/closure angle) → KILL
Mechanism: over a weekend the underlying doesn't trade but the Kalshi ladder stays quotable; rest a
maker offer on the stale-rich bracket.

**Kill (re-run):** the **FILL WALL (L131)** — `tape/universe_sweep/` is hourly BBO snapshots with
**no trade-print field**, so a rested maker fill is unmeasurable (the idea's own kill clause concedes
this). Compounded: the target weekend has **zero** `KXWTIH/KXGOLDH/KXSILVERH` rows in
`dt=2026-07-18` (Sat) or `dt=2026-07-19` (Sun) — the exact stale window it trades is empty tape;
OI≈0 (no counterparty to lift the stale quote); near-money books are 1–3¢ wide so the flat ~1¢ maker
fee eats the spread (**S6/S13, L18/L30**). Collapses into **L131 + S6/S13 + an L15-style weekend
data hole**.

## Lesson candidate (deferred to kb-distiller, not appended here to avoid a ledger merge conflict)

*The commodity daily-close ladders in `tape/universe_sweep/` are a quoted-but-untraded census
(OI≈0, no committed spot reference, settlement join n=1) — they inherit L96 and cannot support any
settlement-basis or maker-fade panel without a dedicated dense/settlement collector.* Recorded so a
future round does not re-spend a milestone on a fourth commodity-surface idea.

## Bottom line

Register-what-survives = nothing; the bar has not moved. All three kills map onto existing ledger
rows (L9/L43/L88/L96/L131 + S1/S6/S8/S13/S42) — no CI, no P&L, no registry table change (prose-note
precedent, matching the 07-15/07-16/07-18/07-19/07-20/07-22 rounds). Two-agent rule satisfied at the
idea stage (producer + independent verifier, all KILL). Still **0 proven edges**.
