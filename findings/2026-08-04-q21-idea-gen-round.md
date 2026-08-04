# Q21 idea-generation round #22 (kalshi-edge-hunter nightly, 2026-08-04) — 0 registered

- **Class:** IDEA-GENERATION / REPLENISHMENT. No CI, no P&L, no fill price, no registry change, no
  kill-of-a-live-strategy. Two-agent rule satisfied AT IDEA STAGE (producer = edge-hunter main
  context; independent `verifier` subagent attacked all three on committed tape before any
  registration).
- **Outcome:** 3 proposed (S75/S76/S77), **verifier KILLED all three** → **0 registered.** Consumed
  S75/S76/S77 → next free = **S78.** Still **0 proven edges.**

## Why the round fired

Full Q0–Q50 file-shape rescan (L25, each item's LATEST status line). As of this run **Q37's gate has
OPENED** — `tape/weather_books/` now holds **21/21** summer daily contract-days — so Q37 is the one
newly-eligible item and the next research-loop firing executes it (its probe is built + 33 offline
tests green; this run re-ran `scripts/q37_bootstrap_unit_preflight.py` and re-confirmed **15 usable
bootstrap units**, clearing the L41 floor of 10 by 5, not 11). Everything else remains
DONE / cred-BLOCKED [Q14/Q15/Q32/Q33/Q35-build/Q47] / density-inadequate [Q36/Q42/Q43, VPS dead 12.5d]
/ on a dead-or-superseded strategy [Q9/Q11/Q12/Q16/Q23/Q24/Q27]. **1 eligible (Q37) < 2 → round fired.**

## The three candidates and why each died

Each was built to route around BOTH mapped walls — **WALL-A** (taker → bracket overround) and **WALL-B**
(maker → adverse selection unmeasurable on `orderbook_depth`, which has no trade/volume field) — on
already-collected tape. The verifier re-derived one load-bearing number per candidate directly from
committed tape.

- **S75 — Delisting-gap survivor taker.** Buy the surviving YES leg of a multi-outcome Kalshi event
  in the window after a rival is eliminated but before the survivor's ask is re-normalized upward.
  **KILL.** Across all `tape/sports_pairs/`, of **442** three-outcome captures containing a dead leg
  (a sibling `yes_ask ≤ 0.02`), the median sum of the surviving legs' `real_ask` = **1.00**, and only
  **4/442** show sum < 0.98; the single apparent "gap" is a live in-play soccer market with genuine
  draw/comeback risk, not a reprice lag. The survivor is already repriced the instant a rival hits ~0
  → no observable window, and the taker leg still eats the overround (WALL-A). Forecloses on S28/S17.

- **S76 — Funding-extreme crypto-hourly fade.** When `hyperliquid_funding` is in its top/bottom decile,
  fade the `crypto_hourly` bracket the funding-implied drift over-favors (crowded-perp mean reversion).
  **KILL.** Over all `tape/hyperliquid_funding/` (1,512 BTC prints), max `|funding_rate|` = **1.89e-5/hr**
  ⇒ a 1-hour drift of ~**$1.25 on a $66k BTC** against Kalshi's **$100-wide** brackets (~80× too small
  to move which bracket settles); and only **5 of 188** brackets are non-1¢-pinned/fillable, the ATM one
  carrying a 6¢ spread on a `bracket_sum` 3.21 (~200% overround, WALL-A). Complements the S8/S10 ρ≈1
  crypto death from an orthogonal (funding, not spot-basis) angle.

- **S77 — Weather realized-obs late NO-taker.** Late in the local day, once the high temp is effectively
  locked, fade brackets far from the realized high using `weather_actuals` as near-truth (a
  settlement-anchored taker, not a forecast bet). **KILL.** `weather_actuals` `captured_at` UTC-hour
  histogram across all committed tape = **{09:218, 12:40, 13:160, 15:2}** — every capture is early-UTC,
  *after* the climate day closed; `high.value` is a finalized daily CLI/METAR `broker_truth` value, not
  a running intraday obs. **Zero** captures fall in the local-afternoon window when the high forms, so
  the "near-truth intraday obs" input the strategy needs **does not exist on tape**; and the far NO leg
  is already 1¢-floor pinned (`best_no_ask` 0.01, the S10 no-fillable-residual death).

## Lesson candidate (deferred to kb-distiller)

**Funding-rate drift is dimensionally negligible against Kalshi crypto bracket width.** Max observed BTC
hourly funding (1.89e-5/hr) implies ~$1.25 drift vs $100-wide brackets (~80×), so no perp-funding signal
can route around the crypto-ladder overround (WALL-A). Records the dimensional argument so the
funding-as-crypto-signal family is not re-proposed a fourth time (cf. S49/S71).

## The standing constraint (unchanged, restated honestly)

This is the ~fourth consecutive zero-registration round with **no new tape surface** since the last
registration. The binding constraint is not idea capacity — it is the **data surface**. Every maker
candidate dies on WALL-B because `tape/orderbook_depth/` carries no trade/volume field, so adverse
selection is structurally unmeasurable (L253/L255/L256, the Q50/S68 close-out). The single highest-value
unlock is the **Q47 `orderbook_delta` trade-bearing feed** (Ryan-gated) — it would let the
adverse-selection term be measured and re-open the entire dead maker family (S6/S13/S14/S19/S21/S23/S68),
none of which was proven negative, only unmeasurable. Until that feed exists, 0-registered rounds are the
honest and expected outcome, not a failure.
