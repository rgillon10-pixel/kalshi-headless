# Q21 idea-gen round #24 + nightly adversarial review — 2026-08-06 (kalshi-edge-hunter, Opus)

**One line:** the last-24h findings survive an independent re-check (3/3 verifiers CONFIRMED,
no issue opened); Q21 round #24 proposes 3 candidates on the new `tape/kalshi_trades/` flow
surface and registers **1** (**S79**, aggressor-flow continuation taker) as `collect-and-revisit`,
folding **S80/S81** into S78. Still **0 proven edges**.

## Context / protocol

- Steps **0a/0/0b** clean. Step 0a: `git pull --rebase` reported a forced-update on `origin/main`
  (`cc5e985…28a5d26`) — the same shallow-clone signature PR #294 documented — but after
  `git fetch --deepen=200` the old clone SHA `cc5e985` **IS an ancestor** of HEAD `28a5d26`, so
  **no rewind, 0a PASS**; newest `kb/00-LOG.md` entry and newest `tape/*/dt=*` both 2026-08-05
  (gap 0). Step 0 claim-check: 6 open PRs (#300 crypto-hourly research-loop idle-run, created
  03:12Z today; #271/#208/#125 retro leave-open; #191/#166/#165 draft infra) — none claims an
  eligible queue item; #300 is the research loop's own in-flight idle-run, not edge-hunter work.
  Step 0b: **216** `tape/hourly-*` + **10** `tape/burst-*` = **226** stranded branches (full sweep
  is the research-loop's job, not duplicated here).
- **Queue eligibility: 0 eligible TODO/unclaimed/unblocked items** (Q48 burst/data-gated, Q49/Q50
  DONE, Q51 milestone-3 time-gated to 2026-08-10, Q52/S78 data-gated). 0 < 2 → Q21 round fires
  (Unit 2). Unit 3 (probe-prep) is a no-op: nothing unblocks within ~72h (Q51-m3 gates 08-10, ~96h
  out, and is already pre-flighted per L284).

## Unit 1 — adversarial review of the last-24h findings: **CLEAN**

Three independent `verifier` agents each re-derived ONE load-bearing number per finding from
committed tape (trust=FALSE, read-only). All three returned **CONFIRMED**; no re-check failed →
**no GitHub issue opened**.

| finding (merged) | load-bearing number re-checked | verdict |
|---|---|---|
| S78 registration (`findings/2026-08-05-q21-idea-gen-round.md`, the only registry-moving finding) | markout measurability: 39,327/39,698 = **99.1%** prints have a later same-ticker print ≤30 min (97.6% ≤5 min); **42/42** trade tickers join `orderbook_depth`; maker fee is `core.pricing.MAKER_FEE_RATE`=0.0175 (not hand-rolled); registration is `collect-and-revisit`, **no CI smuggled** | CONFIRMED (two counts exact, third to rounding) |
| econ_prints fillability (L287, PR #299) | executable nested-arb screen (`core.pricing.monotonicity_crossing_edge`, TAKER_FEE_RATE=0.07) fires **0** times net of fees over 849,958 pairs; best pair −$0.02 net; BBO mirror `yes_ask+no_bid==1` holds 126,841/126,841; all `real_ask` | CONFIRMED (independent re-implementation agrees to the digit) |
| Q51 book-anchor (L283, PR #295) | bootstrap unit = **21 distinct GAME units** / 791 prints at the 15-min anchor bound via `game_of`/L6 (2.1× the L41 floor of 10); registry NOT flipped; DATA-ADEQUACY only | CONFIRMED (histogram reproduced; series→13, ticker→21, game→21) |

One **non-load-bearing prose nit** noted only (no issue, verdict robust): the econ finding says the
best pair is "−$0.02 net of two 1¢ taker fees," but each leg's taker fee is actually $0.02 (total
$0.04); the −$0.02 net is correct and the "0 executable arb" conclusion is unchanged. Left as
history (the finding is on merged `main`; we do not rewrite history).

## Unit 2 — Q21 idea-gen round #24

**Honest framing:** no genuinely new tape family appeared in the last 24h. The one live surface is
`tape/kalshi_trades/` (executed prints w/ `taker_book_side`), first minable in round #23 yesterday,
where **S78** already claimed its cleanest lane (cell-toxicity-filtered selective maker). So this
round proposes candidates that attack *different* mechanisms on that flow surface and lets the
verifier fold/kill the ones that collapse into S78 or hit a graveyard wall. A producer proposed 3;
an independent `verifier` attacked every one BEFORE registration (two-agent rule). **1 survived.**

### S79 — aggressor-flow CONTINUATION taker on signed trade-flow → **REGISTER (collect-and-revisit)**
- **Mechanism:** signed aggressor flow (`taker_book_side`, the executed-print aggressor direction)
  predicts short-horizon continuation before quotes catch up; a taker follows the flow.
  Counterparty: slow liquidity providers run over by informed flow.
- **Load-bearing fact (producer + verifier both derived it on committed tape):** `taker_book_side`
  is present and non-degenerate on `tape/kalshi_trades/dt=2026-08-03.jsonl` — **bid 31,831 / ask
  7,867** (80/20, not a constant) — a *signed TRADE-flow* field genuinely distinct from S22's DEPTH
  imbalance (dead: the displayed mid already integrates the depth ladder; a realized aggressor print
  is different information) and *opposite-sign* to S24's near-close FADE. All **42/42** trade tickers
  join the concurrent `orderbook_depth` so a fillable entry ask/spread exists.
- **Nearest wall = OVERROUND/TAKER (S1/S5/S7/S24):** round-trip ≈ 2×`TAKER_FEE_RATE`(0.07) + spread
  ≈ 14%+, and S24 measured these very sports mid-moves as mean-REVERTING (0.454 continuation
  frequency). **Presumptive outcome is KILL**; registered only because the signed-flow *conditioning
  variable* is untested and the surface is one sports-heavy day — the S55/S78 precedent (a directional
  taker bet on an unmeasured transient, not an algebraic fee-identity kill).
- **Gate (Q54), tightenings:** pre-register horizon+entry BEFORE returns; block-boot by GAME (L6),
  n_units ≥ 10 (L41), L27 tick gate, net of taker fee via `core.pricing`; entry = aggressor print
  price (`broker_truth`), never midpoint/synthetic (pt1 wall); CI > 0. **The fillable EXIT is the
  binding data-gate** — 08-03 `orderbook_depth` has only 4 capture timestamps all day, so a
  seconds-to-minutes taker exit can't be priced (S9 cadence wall); the cleaner hold-to-settlement
  single-fee variant needs `settlement_ledger` close_times covering the trade day (07-07→07-22 only
  today). **Kill:** net return ≤ round-trip taker cost / population < 10-game floor / no fillable-exit
  surface. Data-gated on multi-day `kalshi_trades` + a trade-cadence book (Ryan-gated write-path
  L221/L222 or Q47 `orderbook_delta`).

### S80 — large-print informed-follow MAKER → **FOLD into S78**
Its gate is verbatim "large-print-conditioned realized markout > maker fee 0.0175, block-boot by
GAME, n≥10, CI>0" — that IS S78's gate; print SIZE is one feature of S78's mandated pre-registered
toxicity score (S78 tightening #1 literally permits "a continuous toxicity score"). A
parameterization inside S78, not a new mechanism. No new slot.

### S81 — post-release spread-capture MAKER on the econ-print cohort → **FOLD into S78 + blocked**
Same toxicity/markout FOLD boundary (and overlaps S12's econ-maker lane). Independently blocked from
REGISTER: **its measurement surface does not exist** — `tape/kalshi_trades/dt=2026-08-03.jsonl`
contains **0** econ tickers (20 distinct series, all sports [KXNWSLGAME/KXMLBGAME/KXNPBGAME/…] or
crypto [KXBTC/KXETH]; no KXCPI*/KXNFP*/KXGDP*/KXFED*/KXPCE*), so post-release econ markout cannot be
computed on committed tape today. Its own kill condition fires. New lesson **L292** captures the
general rule (name a `kalshi_trades`-anchored candidate's target-ticker presence at proposal time).

**Round result: 1/3 registered (S79). 2 folded into S78.** This is the anti-treadmill discipline
working — a genuinely new falsifiable hypothesis on a new surface earns a slot; two re-skins of the
already-claimed toxicity lane do not.

## Unit 3 — probe-prep: no-op

Nothing time-gated unblocks within ~72h. Q51 milestone-3 gates 2026-08-10 (~96h out) and is already
pre-flighted (`scripts/q51_m3_preflight.py`, L284). Verified by FILE SHAPE (L25), not path existence.

## Housekeeping

- **Stranded branches:** 216 `tape/hourly-*` + 10 `tape/burst-*` = **226** (full sweep = research
  loop's job).
- **Burst triggers named for deletion** (event dates weeks past, now recurring erroneously into
  2027): `kalshi-burst-cpi-0714`, `-wcsemi1-0714`, `-wcsemi2-0715`, `-wcfinal-0719`, `-fomc-0729`.
  Harmless until 2027; deletion is a Ryan/account action.
- **PR backlog NOT re-flagged** (anti-tune-out): #271/#208/#125 (retro leave-open), #191/#166/#165
  (draft infra) are all still Ryan-review-only with no new information since prior nights.
- **Step 9 (paper):** `SHADOW_REGISTRY={s14_ladder_underwriting}` (dead ✗, infra-only) — idempotent
  this run (docs-only, no tape appended): `paper: 0 open, 1657 settled, realized P&L $+27.76`,
  no new ledger lines.

## Bookkeeping

- `kb/strategies/00-index.md` — new **S79** row (`collect-and-revisit`); no existing status flipped;
  still 0 proven edges.
- `LOOP-QUEUE.md` — new **Q54** item + one "Log of runs" line.
- `kb/lessons/00-lessons.md` — new lesson **L292**.
- `kb/00-LOG.md` — one dated entry (newest at top).
- Two-agent rule: Unit 1 verifiers CONFIRMED existing numbers; Unit 2 S79 is idea-stage
  `collect-and-revisit` (no CI, no `live` flip) with producer + independent verifier both endorsing
  REGISTER. Gates green before commit; research/docs-only → self-merge (squash).
