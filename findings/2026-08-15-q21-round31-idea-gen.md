# Q21 idea-gen round #31 — 0 of 3 survived; the "print-only escape" from the settlement wall runs straight into the fill-model wall

**Run:** kalshi-edge-hunter nightly, 2026-08-15 ~04:15Z UTC. **Trigger:** eligible queue count < 2.
Full Q0–Q56 file-shape rescan (L25, each item's LATEST dated status) = **0 eligible
TODO/unclaimed/unblocked** (9th consecutive idle-adjacent run; Q56 done — S81's independent-verifier
pass CONFIRMED an admissible NULL 2026-08-11; Q52/S78 + Q54/S79 both closed `dead ✗`; everything else
DONE / cred- or burst-gated / on a dead strategy) → Q21 round required per the edge-hunter spec.

**Two-agent pre-registration discipline ran for real this round.** Unlike the recent research-loop
runs that recorded "no `Task`/subagent tool in this harness," this session had the `verifier`
subagent available, so each candidate was attacked by an independent agent that re-derived every
load-bearing number off committed tape BEFORE any registration.

## Outcome
Three NEW falsifiable candidates (proposed A/B/C), each deliberately chosen to attack a mechanism the
prior 30 rounds had NOT tested in this exact form, and each aimed at a *fresh-flowing or richest*
tape family rather than a graveyard re-skin. An independent `verifier` attacked all three against
committed tape. **0 of 3 survived — all KILL on directly re-derived tape facts, before fees or CI
enter the picture.** A 0-registration round with honest verifier refutations is a valid outcome; **no
S-numbers are burned** (round #27 precedent): next free stays **S82**. Still **0 proven edges.**

| cand | name | verdict | load-bearing tape fact (verifier-rederived) |
|---|---|---|---|
| **A** | Temporary-impact reversion **maker** on Kalshi executed prints (claimed settlement-free escape) | **KILL (S13 fill-model wall + S80 dead-cousin)** | `tape/kalshi_trades/` = **213,488 prints / 91 tickers**, and **0 records carry any resting-book field** (`bid/ask/yes_ask/yes_bid`) — it is an executed-*print* stream (`broker_truth`), never a book. A maker fill on the reverting side is unconstructible without queue position / resting depth. The only committed sports fill artifact is `tape/sports_maker_fillsim/dt=2026-07-04.jsonl` — **one day**, not a validated model. And "rest on the swept side, capture reversion" **is S80** (print-VWAP overshoot maker fade, already DEAD/NULL) re-labeled; the "opposite sign to S79" claim escapes the continuation-*taker* cousin, not the reversion-*maker* cousin that actually killed it. |
| **B** | Toxicity-filtered selective maker on `crypto_hourly` ladders (S78 mechanism, different family) | **KILL (adverse selection unmeasurable + S10 floor-pin re-skin)** | `crypto_hourly` outcome schema has **no size/depth field** and is a quote-snapshot ladder, not a trade stream. Executed crypto prints in *all* committed tape = **57 total, all on the single day 2026-08-03** (47 KXBTC + 10 KXETH); `kalshi_trades` is otherwise 100% sports. S78's realized-adverse-selection filter needs a per-fill subsequent adverse move → needs an executed-print stream on crypto, which does not exist at adequacy. The sampled ladder is 1¢-floor-pinned (`yes_ask=0.01, no_ask=1.0`) — the S10 far-bracket failure mode. This is S6/S10/S19 re-skinned onto a tape that structurally cannot measure the one quantity the twist depends on. |
| **C** | Cross-venue fee-band static capture, Kalshi↔Polymarket same-question pairs | **KILL (frozen WC population + L6 + S17/S31 re-skin)** | `tape/polymarket_pairs/` = **6,369 rows, 48 distinct kalshi tickers, 100% `KXWCROUND`** (World Cup), last day-file **`dt=2026-07-15`** — one month stale. No non-frozen, non-WC population exists in the candidate's declared tape scope (non-WC pairs live in `polymarket_macro_pairs`/`polymarket_cpi_pairs`, outside scope). The 48 "questions" are round/team outcomes on one tournament bracket → mechanically correlated, NOT ≥10 independent fillable units (L6). "Static, no timing" escapes the S9 cadence cousin but not S17 (`frozen_pairs_fraction=0.654`, delisting-at-decision) nor S31 (cross-venue tradeability): a simultaneous quote on a delisted WC market is not a fillable instant. |

## The durable product of this round: the "print-only escape" is a mirage
Round #31's candidate A was the most novel angle available — a *settlement-free* mechanism (no join to
the frozen `settlement_ledger` that has capped every recent surface, per round #30). It escaped the
settlement wall and ran straight into the **fill-model wall**. The generalizable fact, re-derived from
the actual schema:

> **A "settlement-free / print-only" escape does not escape the S13 fill-model wall.** Print tape
> (`broker_truth` executed trades) carries no resting book — only what taker aggressors executed — so
> any MAKER-capture claim on it (reversion, fade, toxicity-filter) is unconstructible without a
> separately-cited, adequacy-passing fill model. Grep for a `bid/ask` field before accepting any
> maker mechanism on a trade tape.

This is the same wall that reduced S78/S80 to DEAD/NULL, restated one level up: it is a property of
the *tape family class* (executed-print streams), not of any one candidate. Deferred to `kb-distiller`
for enshrinement — NOT enshrined here (this run produced no verdict-class output).

## The saturation signal, now at nine rounds
Rounds #27–#31 (five consecutive, plus round #26's two survivors S80/S81 that reached registration and
then died DEAD/NULL) confirm the binding constraint is the **DATA SURFACE, not idea capacity**. The two
concrete, already-named unblocks stand unchanged:
1. **Multi-day `kalshi_trades` on book-covered tickers** — the collector is Ryan-key-gated (Q47/Q51);
   the tape is byte-frozen at 6 days (last `dt=2026-08-03`). This alone would let a real fill model be
   built for candidate-A-class print mechanisms.
2. **A forward `settlement_ledger` past `dt=2026-07-22`** (Q45) — round #30's measured cap on the whole
   `universe_sweep` surface.

Neither is a cloud-runnable code change; both are Ryan-side. This is a standing note, not a new ask.

## Provenance / discipline
- All counts re-derived by an independent `verifier` from committed tape (`tape/kalshi_trades/` 6 days,
  `tape/crypto_hourly/`, `tape/polymarket_pairs/` 11 days, `tape/sports_maker_fillsim/`), nothing
  trusted from proposal prose. Fees only via `core.pricing` (`TAKER_FEE_RATE=0.07`,
  `MAKER_FEE_RATE=0.0175`, `polymarket_fee_per_contract`). Bootstrap unit = independent game/event
  (L6); floor = 10 units (L41).
- A pre-registration verifier attack is the mandated step for idea-stage candidates; it ran and
  returned 0 survivors. No candidate was registered, so nothing here is verdict-class; no registry
  flip, no new queue item, no S-number consumed (next free stays **S82**).
- Still **0 proven edges.** Binding constraint stays the DATA SURFACE.
