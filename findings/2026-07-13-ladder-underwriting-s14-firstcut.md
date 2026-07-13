# S14 — Ladder overround underwriting: crypto-hourly first cut → PROXY-POSITIVE (not proven)

`2026-07-13` · S14 (kb/strategies/00-index.md row 26) · probe `scripts/s14_ladder_fillsim.py` ·
tests `tests/test_s14_ladder_fillsim.py` (21, offline, injected fetcher — no network) ·
per-ticker fill summaries cached to `tape/s14_ladder_fillsim/dt=2026-07-13.jsonl`
(6,524 rows, `price_source_tag:"real_ask"`, resumable) · **verifier: CONFIRMED-WITH-CAVEAT**

## Verdict up front (do not inflate)

S14 is the **first non-DEAD candidate in the project**, but it is **NOT a proven fillable
edge**. It is **proxy-positive** under an upward-biased candlestick fill proxy and must be read
at exactly that ceiling. The verifier's decisive call (its answer to a three-way
alive/dead/proxy-dependent question) was **(b): promising-but-proxy-dependent — move
`idea → data-collecting` with a queue-aware follow-up gate, do NOT call it a proven/live/alive
edge.** The project's running tally is unchanged: **still 0 proven edges.** S14 has not moved
that bar; it has earned a real forward gate.

## Hypothesis (S14)

Sell (short YES / rest a maker offer) at every strike of a complete MECE bracket ladder and
collect the ladder's overround. Because exactly one strike settles YES, the underwriter pays
out \$1 once and keeps the premium on every filled strike. Binding gate (registry text):
`E[overround × P(complete fill)] − E[loss on partial sets @ real asks] > 0`, 95% CI over
≥30 event-days.

## Scoping decision: crypto_hourly, NOT sports_pairs

S14 needs a genuine **strike ladder** — a MECE partition of many strikes where exactly one
settles YES. `tape/crypto_hourly/` BTC/ETH hourly bracket ladders are exactly that: **mean
131.5 members**, MECE, exactly one strike settles YES. `sports_pairs` is explicitly **not** a
ladder — a moneyline group has only 2–3 outcomes, structurally a binary/ternary, not a strike
ladder to underwrite. The Q13 item named both tape families; only crypto_hourly carries the
ladder structure the thesis is about. Documented so a future reader doesn't re-add sports.

## Method + fill proxy (and its limitation, stated up front)

At the **earliest** capture of each settled event-hour, post a resting **short-YES maker
offer** at every member's `yes_ask` (real_ask). Fill over `[capture_time, close_time]` is
determined by the cached Kalshi hourly candlestick:
**`max(price.high_dollars) >= posted_ask AND total_volume > 0`** — the seller mirror of s13's
resting-bid `low <= bid` rule. On a fill, premium = `ask − fee_per_contract(ask, MAKER_FEE_RATE)`
(fee from `core.pricing`, never hand-rolled, L18); payout = \$1 iff the realized winner
(`previous_settlement.results[k]=="yes"`, broker_truth) was among the filled strikes. Per-event
P&L = `Σ premium(filled) − payout`.

Egress to Kalshi candlesticks was reachable; **6,524 per-ticker summaries** cached to
`tape/s14_ladder_fillsim/dt=2026-07-13.jsonl` (resumable). Fetches are bounded to members with
`yes_ask >= 0.02` plus the realized winner — 1¢-floor wing asks net exactly \$0 either way after
the flat \$0.01 maker fee (L30), so fetching them buys nothing.

**The limitation that caps the verdict:** the candlestick fill ignores **queue position**. A
`high >= ask` bar only proves the price *printed*, not that a resting offer *ahead of the whole
book* would have been filled. This biases the **income leg** upward. It does not bias the
**winner-\$1 loss leg**, which is robust (heavy volume sweeps the offer; see below).

## Primary gate (block-bootstrap by event-hour)

`core.bootstrap.block_bootstrap`, n_boot=10,000, unit = **event-hour** (L6):

- mean **+\$0.0925**, 95% CI **[+\$0.0630, +\$0.1231]**, **n=300 settled event-hours**
- **`clears_tick_magnitude` CLEARS** (lower bound ~6× the 1¢ tick — passes L27's magnitude gate,
  not just the sign check)
- **72.0% of events positive** (216/300)
- by series: **KXBTC +\$0.150** (n=150), **KXETH +\$0.035** (n=150)

## Coarser bootstrap units (verifier robustness check)

The event-hour CI is not an independence artifact — coarser units still clear zero and the
magnitude gate:

- by-day (10 units): [+0.068, +0.119]
- by-day × symbol (20 units): [+0.055, +0.130]

## Gate decomposition — the "underwrite the whole ladder" term is ZERO

Against the registry's own gate text, `E[overround × P(complete fill)] ≈ 3.16 × 0.00 = \$0`:
the **complete-fill rate is 0.0%** (0/12 in the full-ladder sample). The dream term — collect
the whole ladder's overround because the entire set fills — contributes **nothing**. The entire
result is **path-dependent partial pass-through premium net of the winner-\$1 loss**:
`E[P&L | partial] = +\$0.0925`, n_partial = 300. Whatever S14 is, it is **not** "underwrite the
complete overround"; it is "collect premium on the strikes that fill and eat the one \$1 loss."

## Adverse-selection profile (the answer to Q13's core question)

Full-ladder sample (n=12 event-hours, every member fetched):

- winner strike fill: **100%**
- near-money fill: **95.8%** (69/72)
- wing fill: **2.5%** (55/2172)
- complete-fill: **0.0%** (0/12)
- winner-filled over the full n=300: **96.7%** (290/300)

Confirms the thesis's own worry verbatim: **the winning strike fills eagerly (you always eat
the \$1), the wings never fill (you rarely collect their premium).** The edge is not the fat
nominal overround; it is the near-money premium net of the near-certain \$1 loss.

## Structural fee annihilation (L30)

mean bracket_sum 4.16, overround 3.16, members 131.5; **30.9% of bracket_sum is 1¢-floor asks
that net exactly \$0 after the flat \$0.01 maker fee** (L30: `fee_per_contract(P, MAKER_FEE_RATE)
= 0.01` at every interior price). A third of the headline "overround premium" is uncollectable
by construction — the same fee floor that killed S6/S13, here quietly deleting a third of the
nominal edge before any fill question.

## The caveat that caps the verdict — queue / asymmetric optimism

The candlestick proxy ignores queue position: the winner-\$1 loss is robust (heavy volume sweeps
the offer, 96.7% filled) but the **income leg is thin-print optimistic**. Volume-gate
sensitivity (require non-winner fills to carry volume ≥ X; winner kept robust):

| gate | mean P&L | 95% CI |
|---|---|---|
| vol0 (primary) | +0.0925 | [+0.063, +0.123] |
| vol5 | +0.0575 | — |
| vol10 | +0.0467 | — |
| vol50 | +0.0261 | [+0.004, +0.049] |
| vol100 | +0.0206 | [−0.001, +0.043] |

**\$0.072 of the \$0.093 edge (78%) comes from sub-100-contract-volume income legs.** Strip the
income leg entirely and the strategy is **−\$0.51 to −\$0.97** (you are left holding the \$1
loss). Counterweight — why it is not dead: the filled income legs carry **heavy volume**
(median 1,047 contracts, p90 10,183), so the edge survives a *modest* haircut (vol≥50 still
+0.026 [+0.004, +0.049]). It dies only under an **aggressive** haircut, or under the unmodeled
**adverse-selection correlation** between which income strikes fill and which strike wins —
exactly what a queue-aware L2 fill-sim must capture and this candlestick proxy cannot.

## Follow-up gate substrate exists

`tape/orderbook_depth/` (6 days, crypto covered — 11,046 KXBTC/KXETH lines on 07-12) carries
`no_bids`/`yes_bids` size ladders. Note for the queue-aware fill-sim: the short-YES resting
queue must be read off the **mirror `no_bids`** side, because the depth tape stores the
`best_yes_ask` *price* but not the yes_ask *size* ladder.

## Verifier (independent re-run): CONFIRMED-WITH-CAVEAT

The verifier reproduced the headline three independent ways (event-hour, by-day, by-day×symbol
bootstraps), found no material bugs or mis-tags, and made the (b) proxy-dependent call above.
One labeling nuance only (headline unaffected): the producer's "winner-only, no income"
strip-out (−0.5078) keeps the winner's *own* premium; a strict no-income strip is −0.9667 —
same direction, headline untouched.

## Honest verdict

**PROXY-POSITIVE, not proven.** Under an upward-biased candlestick fill proxy, S14 clears the CI
and magnitude gates at the primary and both coarser bootstrap units, and survives a modest
volume haircut — enough to be the project's first non-DEAD candidate and to earn a forward gate,
**not** enough to be a proven, fillable, real-ask edge. The registry stays at **0 proven edges**.
S14 flips **`idea → data-collecting`**; the remaining binding step is a **queue-aware L2/depth
fill-sim** (over `tape/orderbook_depth/`, reading the short-YES queue off the mirror `no_bids`
side) that models queue position and the fill↔winner correlation this proxy cannot — before any
real-ask graduation claim.

## Provenance (re-runnable)

- probe: `scripts/s14_ladder_fillsim.py`
- tests: `tests/test_s14_ladder_fillsim.py` (21, offline, injected fetcher, no network)
- cache: `tape/s14_ladder_fillsim/dt=2026-07-13.jsonl` (6,524 summaries, `real_ask`, resumable)
- gates at time of verdict (post-rebase onto concurrently-merged PR #53): `pytest -q` 642
  passed (621 prior + 21 new); `python scripts/invariants.py --full` green (only standing
  non-gating L25/L29 stray-directory + L20 stranded-tape advisories)
