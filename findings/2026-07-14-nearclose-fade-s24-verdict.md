# S24 — Near-close hourly-return overreaction fade (two-sided sports books) — DEAD verdict

**Date:** 2026-07-14 · **Probe:** `scripts/q28_s24_nearclose_fade_probe.py` (Q28) ·
**Status:** **DEAD-by-round-trip, verifier-CONFIRMED** (two-agent rule satisfied — independent
`verifier` bit-for-bit re-run plus a from-scratch re-implementation of jump detection, fee math,
and the by-game block bootstrap reproduced every number to the last digit; attacked fee/spread
math, cluster degeneracy, anti-overlap straddle, lookahead, and noise-floor choice — all held.
Registry flipped: `kb/strategies/00-index.md` S24 `idea` → `dead ✗`).

## Mechanism (Theme 7 behavioral, De Bondt-Thaler / Tetlock)

A near-close mid JUMP in a two-sided sports book (retail overreacting to the last salient in-game
event) is claimed to partially REVERSE over the next snapshot; fade the jump. Losing counterparty
= the overreacting retail flow. Distinct from S18 (elections/polls, idea-stage) — different
category and horizon; distinct from S9 (cross-venue lead-lag, DEAD-by-cadence) — this tests a
*different object*, within-market hour-to-hour return autocorrelation, which the hourly tape can
answer.

## Data & join (read-only; no network — a probe makes no network calls)

- Signal: `tape/orderbook_depth/` price paths (dt=2026-07-07..07-14), the 7 Q25 high-turnover,
  two-sided sports cells (KXKBOGAME, KXNPBGAME, KXWNBAGAME, KXMLBGAME, KXUCLGAME, KXUECLGAME,
  KXUELGAME). The full per-market pre-close snapshot PATH is loaded (unlike Q26/Q27 which kept
  only the last snapshot).
- Settlement + close_time: reused OFFLINE from the committed Q26 settlement cache
  (`tape/q26_settlement_cache/settlement.json`, 458 settled markets, `broker_truth`), same 7
  series. `result == "scalar"` filtered out (L52). No new live pull.
- Funnel: 599 markets in depth · 450 with a binary settlement + a pre-close path.

## Design (the binding gates, not weakened)

- **Jump detection:** mid = (best_yes_bid + best_yes_ask)/2, a `synthetic` model value (Hard
  Rule #3 — a mid is never a fill; it is only the detection signal). A jump event = a
  genuinely-consecutive pair (gap ≤ 1.5 h, L13 hole guard) with |Δmid| ≥ X whose *entry* (t+1)
  snapshot is in the near-close ttc window (≤ 4 h — a sports game's live-to-close stretch).
- **Noise floor (gate 2):** over this tape 64.1% of consecutive pairs are frozen-BBO (Q25's
  58-94% band) and 86.8% move the mid < 2¢; a jump therefore lives in the tail. Primary X = 2¢
  (>> a 0.5-1¢ one-tick flicker); reported across an X ∈ {2,3,4,5}¢ sweep. A frozen pair (Δmid=0)
  is *never* a jump event — the frozen concept is applied at detection (this is a TAKER round-trip
  where both legs fill by crossing the spread, so the S6/L32 maker "frozen = no-fill" dual-cut is
  structurally N/A; the relevant frozen guard is on the jump itself).
- **Fade entry at `real_ask`, exit at `real_bid` on the next snapshot (gate 1, load-bearing):**
  jump UP → short YES == BUY the NO contract (enter @ best_no_ask(t+1), exit @ best_no_bid(t+2));
  jump DOWN → BUY YES. `net_reversal = exit_bid − entry_ask − taker_fee(entry_ask) −
  taker_fee(exit_bid)` — charges 2× the 0.07 taker fee AND 2× the half-spread. `$1.00`-mirror /
  missing / ≤0 entry asks are excluded and counted (L26). Fees only from `core.pricing`
  (TAKER_FEE_RATE, L18).
- **Anti-overlap guard (gate 1):** the SAME entry is also held to settlement
  (`net_settle = payoff − entry_ask − ONE taker_fee`, no exit leg). If the reversal round-trip is
  DEAD but the settlement exit is alive, S24 collapses into **S22** (a directional settlement bet
  keyed on a recent jump) and is NOT registered as a new S24 edge.
- **Bootstrap by distinct GAME (event_ticker, L6), ≥10 games**, through
  `core.bootstrap.block_bootstrap` (10,000 resamples) + `bootstrap_verdict_admissible` (L41 — a
  sign question, opposing cluster NOT guaranteed) + `clears_tick_magnitude` (L27).

## Results (primary X = 2¢; `price_source_tag`s as noted)

- **Population adequacy (gate 3): PASS.** 126 distinct games carry a ≥2¢ near-close jump; 739
  round-trip trades across **123 games** (≫ the 10-game floor). Robust to X: 126/126/126/126
  games at X = 2/3/4/5¢.
- **Direction precheck (gate 2):** reversal *frequency* 0.454 (a slight majority of jumps
  CONTINUE), but the conditional next-step MEANS do point back toward the pre-jump level
  (after jump-up: **−0.0061**; after jump-down: **+0.0087**, `synthetic` mid units) — i.e. a real
  but tiny ~0.6-0.9¢ net mid-reversal exists. Not classified as pure momentum.
- **S24 fade round-trip (the binding CI), block-boot by GAME, n=123 games / 739 trades:**
  mean **−$0.02936**, **95% CI [−$0.05179, −$0.00587]** — the entire CI is **strictly below 0**
  (`real_ask` entry / `real_bid` exit, both taker fees). Admissible (50 opposing-sign clusters,
  L41 PASS); `clears_tick_magnitude` = FAIL (it's negative). **NOT a positive verdict.** The
  ~0.7¢ mid-reversal is swamped by the ~6-7¢ realized round-trip hurdle (2× taker fee + 2×
  half-spread on a ~3.7¢-overround book).
- **Anti-overlap hold-to-settlement, n=126 games / 817 trades:** mean **−$0.02611**,
  **95% CI [−$0.05884, +$0.00825]** (`real_ask` entry / `broker_truth` settle) — straddles 0,
  does **not** clear either. → **S24 does NOT collapse into S22**: neither exit is profitable, so
  there is no hidden directional-settlement edge to route away.
- **Robustness across the X sweep** (round-trip CI, by GAME): X=3¢ [−0.0540, −0.0057]; X=4¢
  [−0.0531, −0.0029]; X=5¢ [−0.0428, +0.0099]. Negative or non-clearing at every threshold; the
  hold-to-settlement CI never clears at any X. The DEAD is not an artifact of the X choice.

## Verdict

**DEAD-by-round-trip, verifier-CONFIRMED.** The behavioral reversal is genuinely present in mid
terms (~0.7¢) but is an order of magnitude below the full realized round-trip cost; the fade CI is
strictly negative at the primary threshold and non-clearing across the sweep. The anti-overlap
guard fired cleanly — the settlement exit is also unprofitable, so this is not a mislabeled S22.
This matches the honest expectation logged at idea stage ("DEAD-by-round-trip is likely; sound and
novel nonetheless"). Independent verifier: bit-for-bit re-run + from-scratch re-implementation
(own tape loader, own jump detection, own fee math, own by-game bootstrap) reproduced every number
exactly; hand-verified sample trade (`KXKBOGAME-26JUL070530KIALOT-KIA`, rt = 0.21 − 0.43 − 0.02 −
0.02 = −0.26) confirms both taker legs charged correctly; largest bootstrap cluster is 10/739
trades (1.35%) — no degeneracy; lookahead clean (entry strictly precedes exit); anti-overlap CI
genuinely straddles zero. `kb/strategies/00-index.md` S24 flipped `idea` → `dead ✗`.

## Kill-condition mapping (spec)

- jumps continue (momentum) → partial (freq 0.454 continue) but net mid-reversal exists, so not
  the operative kill; **reversal < round-trip cost** → the operative kill (0.7¢ ≪ ~7¢).
- cadence too coarse (S9-family) → NOT the kill: 126 games populate the test fine.
- CI fails either gate → yes: CI < 0 and fails `clears_tick_magnitude`.

## Lesson candidates (for the kb-distiller)

- **The behavioral reversal can be real yet un-tradeable by an order of magnitude.** S24's
  near-close mid does mean-revert (~0.7¢ net after a ≥2¢ jump) — the De Bondt-Thaler prediction is
  directionally CONFIRMED as a price observation — but a taker round-trip that must pay 2× fee +
  2× half-spread (~6-7¢ on a ~3.7¢-overround book) turns a genuine signal into a −$0.029 loss.
  Distinguish "the effect exists" (mid units, `synthetic`) from "the effect is fillable" (`real_ask`
  round-trip). Same family as L31/L57 (nominal ≠ capturable) and L39/L48 (a signal orients, the
  fill test binds).
- **The reversal *frequency* and the reversal *magnitude* can disagree in sign of implication:**
  frequency 0.454 (majority continue) yet mean next-step opposes the jump — a few large reversals
  carry the mean. A momentum/reversal precheck should report BOTH the reversal fraction and the
  sign-conditioned mean, not pick one.
- **A taker two-leg round-trip does not need the S6/L32 frozen-vs-movement maker dual-cut** — both
  legs fill by crossing the spread, so a frozen exit is a real (losing) fill, not a no-fill; the
  frozen guard belongs on the jump *detection* instead. Recording the boundary of where L32
  applies (maker resting fills) vs where it doesn't (taker round-trips).
