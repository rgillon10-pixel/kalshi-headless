# Q21 idea-gen round #25 + nightly adversarial review — 2026-08-07 (kalshi-edge-hunter, Opus)

**One line:** the four 2026-08-06 research-loop findings survive an independent re-check (4/4
verifiers CONFIRMED, incl. a vacuous-pass attack on the subject-identity guard); Q21 round #25
registers **0** (all three candidates die on hard tape facts) — but its adversarial pass caught a
**factually-wrong data-gate in the last-24h S79 registration** (the row claims the 08-03 trade day
has no settlement coverage; `tape/q51_settlement_cache/` actually resolves **9** of the traded games)
→ **GitHub issue opened**, no history rewritten, S79 status unchanged. Still **0 proven edges**.

## Context / protocol

- Steps **0a/0/0b** clean. **0a:** all 5 most-recent merge commits (`d02d854`…`059fb68`) are
  ancestors of `origin/main` (no rewind); newest `kb/00-LOG.md` entry `2026-08-06` vs newest
  `tape/*/dt=*` `2026-08-07` — gap 1 day, within the 2-day tolerance. **0:** 6 open PRs
  (#271/#208/#125 retro leave-open; #191/#166/#165 draft infra) — none claims an eligible queue
  item; #300 (research-loop idle-run cited 08-06) has since merged. **0b:** **220** `tape/hourly-*`
  + **10** `tape/burst-*` = **230** stranded branches (full sweep is the research-loop's job, not
  duplicated here).
- **Queue eligibility: 0 eligible TODO/unclaimed/unblocked items.** File-shape rescan (L25) of each
  item's LATEST status: all DONE / cred-BLOCKED [Q14/Q15/Q32/Q33/Q35-build/Q47] / density-inadequate
  [Q36/Q42/Q43, VPS dead] / on a dead-or-superseded strategy [Q9/Q11/Q12/Q16/Q23/Q24/Q27];
  Q48 burst/data-gated; Q49/Q50 DONE; **Q51 milestone-3 time-gated to 2026-08-10**; Q52/S78 and
  Q54/S79 data-gated (`collect-and-revisit`); Q53 milestones 1–3 done (PROVISIONAL verdict);
  Q55 milestones 1–2 done, milestone-3 data-gated on truncation. 0 < 2 → Q21 round fires (Unit 2).

## Unit 1 — adversarial review of the last-24h findings: **CLEAN**

The four research-loop findings dated 2026-08-06 were all **main-context builds committed without
an independent verifier** (that harness exposed no `Task`/subagent tool — the L287–L295 precedent).
This run supplied the second agent they could not: three independent `verifier` agents each
re-derived one load-bearing number per finding from committed tape (trust=FALSE, read-only), plus a
main-context spot-check on the 08-06 Q21 round. **All returned CONFIRMED; no re-check failed → no
GitHub issue opened.**

| finding (2026-08-06, merged) | load-bearing number re-checked | verdict |
|---|---|---|
| `q53-subject-identity-nesting-repair` | guard error rates: **0 false admits / 2,364** labelled cross-subject pairs and **0 false refuses / 34,334** genuine-ladder pairs (econ 2,348 + weather 31,986); replay funnel **43,038 → 13 → 0**. Verifier ran an explicit **vacuous-pass attack**: the guard genuinely ADMITS 34,485 same-subject pairs (TP=151 labelled + 34,334 ladder) while refusing all cross-subject — real three-valued discrimination, not refuse-everything. | CONFIRMED |
| `detector-evidence-guard` | check `cross_event_implication` = **243 `empty_denominator` + 5 `counter_absent` = 248**, 0 readable zeros; S3's own `bracket_arb`/`cross_strike_monotonicity` each **23/248 (9.3%)** empty-denominator, all 23 `completeness_ok:true` / no fetch error / up to 20,000 scanned; `bracket_arb` 0 hits / 2,210 checks; monotonicity 43,038 hits | CONFIRMED (independent recount off `tape/anomalies/`, not the writer) |
| `crypto-hourly-settlement-data-quality-audit` | MECE settlement integrity: **1,483/1,483** settled crypto_hourly records carry exactly one `result=="yes"` via `core.settlement.filter_binary_results_map`; tag `broker_truth`. L289 trap checked: results-absent/empty/nonempty = 0/0/1,483 (100% not manufactured by skipping empties) | CONFIRMED |
| `anomaly-sweep-fillability-guard` | replay **43,038 → 43,025 (99.9698%) refused unfillable ($0.00 leg) → 13 survive**, threshold from `core.pricing.is_fillable_ask` (`MIN_FILLABLE_ASK_DOLLARS=0.01`) / `is_material_arb_edge`, NOT a hand-rolled constant | CONFIRMED |
| `q21-idea-gen-round` (08-06, S79 registration — already two-agent) | `taker_book_side` non-degeneracy on `kalshi_trades/dt=2026-08-03`: **bid 31,831 / ask 7,867** (total 39,698) | CONFIRMED (main-context spot-check, exact) |

Every 08-06 descriptive/tooling finding is now verifier-backed. No number moved; no history
rewritten (findings are on merged `main`).

### One re-check FAILED — the 08-06 S79 registration's settlement data-gate is factually wrong

Surfaced by Unit-2's adversarial pass and **independently re-derived twice** (the Unit-2 `verifier`
plus a main-context recount). The S79 registry row (`kb/strategies/00-index.md`) and the
`findings/2026-08-06-q21-idea-gen-round.md` registration both state the hold-to-settlement variant is
un-joinable because settlement coverage is "07-07→07-22 only today" (checking only
`tape/settlement_ledger/`). That is **false**: `tape/q51_settlement_cache/settlement.json`
(`price_source_tag: broker_truth`, `day: 2026-08-03`, 60 markets) carries **10 `finalized` markets
(4 yes / 6 no)**, and joining the 38 traded 08-03 sports tickers to it resolves **9 distinct games**,
every one heavy with trade flow (KXNWSLGAME-DENBOS 10,156 prints, KXMLBGAME-LADCHC ~7.6k,
KXNPBGAME-TOHORI 5,462, KXDIMAYORGAME-SFEOC ~5.4k, KXSCOTTISHPREMGAME-CELDUN 4,033,
KXEKSTRAKLASAGAME-CRAPSZ 3,006, KXLIGAMXGAME-AMESLA 2,304, KXARGPREMDIVGAME-CCSLA, KXASEANGAME-MYALAO).

**What it changes:** S79's data-gate is NOT "waiting on a settlement collector / no coverage of the
trade day" — it is **n=9 distinct settled games, one short of the L41 ≥10-game floor**. S79's status
does not flip (still `collect-and-revisit`, still no admissible CI at n=9), but its blocker is now a
single additional settled sports game of trade tape, not a whole missing collector. Per protocol
(re-check of a last-24h finding failed → **do NOT rewrite history**), **GitHub issue #310** was
opened and the correction is Priority:high in tonight's phone note. The S79 row is left for the
two-agent/Ryan-blessed correction, not self-edited by this run.

**Deferred lesson candidate (to kb-distiller):** a "data-gated: no settlement coverage of the trade
day" verdict must scan **every** settlement family (`settlement_ledger` AND `q*_settlement_cache`
AND `crypto_hourly.previous_settlement` …), not just `tape/settlement_ledger/` — an L165-class
"true-ish gate, incomplete source" defect that here silently over-killed a candidate's testability in
both a proposed kill and a live registry row.

## Unit 2 — Q21 idea-gen round #25: **0 registered**

**Honest framing:** no genuinely-new tape family appeared in the last 24h. The only new surface is
`tape/kalshi_trades/` (executed prints, `broker_truth` + `taker_book_side` + `count` [size] +
`is_block_trade`), one day (`dt=2026-08-03`, 39,698 prints), whose two cleanest lanes are already
claimed — **S78** (toxicity-filtered selective maker, realized markout) and **S79** (aggressor-flow
continuation taker). A producer proposed 3 candidates attacking *different* mechanisms on that
surface; an independent `verifier` was tasked to REFUTE the producer's kills (rescue any as
registerable). **All three die on directly-measured tape facts.**

### P1 — Block-trade impact fade (taker fades a negotiated block's price impact) → **KILL (dead on arrival)**
`is_block_trade` is **FALSE on all 39,698 prints** on 2026-08-03 → zero population. A different
conditioning variable from S79 (block flag vs aggressor side), but the field the mechanism needs is
uniformly empty on the only committed day.

### P2 — Signed-trade-flow → crypto-hourly-settlement taker (hold to settlement = single fee; join to `crypto_hourly` settled results which DO cover 08-03) → **KILL**
Only **4 distinct crypto tickers** traded on 08-03 (KXBTC/KXETH hourly) ≪ the L41 n≥10-unit floor —
no adequately-powered block-bootstrap possible. Compounded by the S8/S10 wall: crypto binaries track
public spot (S8 ρ=0.9997) and pin near close (S10), so realized aggressor flow on them carries no
private information the mid hasn't already integrated. Dies on adequacy (4 ≪ 10) before the
information wall even binds.

### P3 — Signed-trade-flow → hold-to-settlement taker on SPORTS (the exit-book-free variant of S79) → **KILL / FOLD into S79**
The producer's first kill fact (a) — "no settlement coverage of the trade day" — was itself
**REFUTED** by the verifier and is the failed re-check documented in Unit 1 above:
`q51_settlement_cache` resolves 9 of the traded games, so P3 IS joinable to settlement on current
tape. P3 nonetheless earns **no slot**, on two surviving grounds: (b) it is a **literal duplicate of
S79's own registered "cleaner hold-to-settlement single-fee variant"** — not a genuinely-new
mechanism; and (c) even standing alone the joinable population is **9 distinct games, one short of the
L41 ≥10-game floor** — an honest `below_min_units` (not measurable yet), so it stays
`collect-and-revisit`, which S79 already occupies. Registering P3 would double-book S79's slot.

**Round result: 0/3 registered.** This is the anti-treadmill discipline: the two cleanest
kalshi_trades lanes were claimed the last two nights (S78 08-05, S79 08-06); every remaining lane on
this one-day surface is either DOA (`is_block_trade` empty), below the unit floor (4 crypto tickers),
or a data-gated duplicate of S79. Registering a third `collect-and-revisit` on the same surface would
be exactly the padding the retro anti-treadmill note (open PR #208) warns against. Consumed
S80/S81 already (08-06); next free candidate id = **S82**.

**The binding constraint remains the DATA SURFACE, not idea capacity** — specifically *multi-day*
`kalshi_trades` aimed at book-covered tickers plus a settlement harvest covering the trade day (the
Q51-m3 / Q47 `orderbook_delta` write-path, both Ryan-gated). Until that lands, the kalshi_trades
surface's testable-now edges are exhausted.

## Unit 3 — probe-prep: no-op

Nothing time-gated unblocks within ~72h that is not already prepped. **Q51 milestone-3** gates
2026-08-10 (~72h out); it is already pre-flighted (`scripts/q51_m3_preflight.py` + 20 tests, L284)
and its firing-hazard — the milestone command overwriting the milestone-2 pin cache — was found and
repaired on 08-05 (frozen `settlement-m2-2026-08-04.json` snapshot; repair verified 42/42 green
against a simulated 08-10 re-pull). Verified execute-ready by FILE SHAPE (L25), not path existence.

## Housekeeping

- **Stranded branches:** 220 `tape/hourly-*` + 10 `tape/burst-*` = **230** (~+4 vs 08-06's 226;
  full sweep = research-loop's job).
- **Burst triggers named for deletion** (event dates weeks past, harmless but recurring):
  `kalshi-burst-cpi-0714`, `-wcsemi1-0714`, `-wcsemi2-0715`, `-wcfinal-0719`, `-fomc-0729`.
  Deletion is a Ryan/account action (cloud sessions cannot delete these; they live in the claude.ai
  routines surface, not this session's MCP trigger list).
- **PR backlog NOT re-flagged** (anti-tune-out, per prior nights): #271/#208/#125 (retro leave-open),
  #191/#166/#165 (draft infra) are all still Ryan-review-only with no new information since prior
  nights — re-flagging trained the channel to be ignored once already.
- **Step 9 (paper):** `SHADOW_REGISTRY={s14_ladder_underwriting}` (dead ✗, infra-only) — docs-only
  run, no tape appended, ledger byte-identical to 08-06: `paper: 0 open, 1657 settled, realized P&L
  $+27.76` — **dead-strategy shadow, paper-infra validation only, NOT edge evidence.**

## Bookkeeping

- `kb/strategies/00-index.md` — **no** status flipped, no new row (0 registered; prose-note
  precedent). Still 0 proven edges.
- `LOOP-QUEUE.md` — one Q21 "ROUND COMPLETE (#25)" status line + one "Log of runs" line.
- `kb/00-LOG.md` — one dated entry (newest at top).
- **GitHub issue #310** — the failed re-check on the 08-06 S79 settlement data-gate (Priority:high
  phone note). S79 row left un-edited for a two-agent/Ryan correction.
- Two-agent rule: Unit-1 verifiers CONFIRMED the four 08-06 findings' numbers (no flip); the one
  failed re-check went to an issue, not a self-edit; Unit-2 registered nothing, so the registration
  gate was not reached. Gates green before commit; research/docs-only → self-merge (squash).
