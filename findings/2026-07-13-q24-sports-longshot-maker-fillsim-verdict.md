# Q24 / S21 — sports-longshot maker-ASK fill-sim verdict: DEAD by data-adequacy

`2026-07-13` · LOOP-QUEUE.md Q24 · registry family S7/H1 · verifier CONFIRMED-WITH-CAVEAT
(the caveat was a cosmetic 80/80→81/81 script literal, fixed separately — the real number is
**81/81**) · every price below carries its source tag

## The question (H1, the untested S7c mirror)

S7c PROVED the *taker* side of Kalshi sports moneyline: the real pregame ask runs **+2.35¢
rich** vs a DraftKings-devig fair price (n=80 games/237 outcomes, block-bootstrap-by-game
edge_after_fee mean −0.02354, 95% CI [−0.0245,−0.0225]; `findings/2026-07-04-sports-clv-s7-verdict.md`).
S13 then tested resting maker **BIDS at fair−1¢** → DEAD (the flat maker fee ate the assumed
1¢ margin; `findings/2026-07-04-sports-maker-s13-verdict.md`, L30). The one leg neither test
covered is the **direct mirror**: rest the rich ASK itself — short YES / buy-NO at `1−ask` —
concentrated in the longshot tail where S7c's richness is largest, and harvest the overpricing
paid by retail lottery-ticket takers who cross the spread pregame.

The edge-at-quote is not in question here — S7c proved it. **The binding question Q24 exists to
answer is FILLS:** the incumbent maker queue already posts those asks, so a new resting offer
joins the BACK of that queue (S19 died at a 0.45% fill rate; that floor was expected to apply).
The mandated instrument is therefore a **queue-aware `orderbook_depth` fill-sim** (L39 — never a
candlestick print), reading the resting-offer queue off the mirror `no_bids` side, with the
sold-longshot-WINS negative-skew leg modeled explicitly (never conditioned away — the exact L41
degeneracy S20 surfaced).

## Verdict: DEAD by data-adequacy (verifier-CONFIRMED)

**NOT a CI falsification.** The queue-aware fill-sim that Q24 exists to run is **structurally
un-runnable on the committed tape** — the two datasets it must join were collected in
non-overlapping windows, so the population is empty before any bootstrap can begin.

### The binding fact: 0/81 joinable (0.00%)

The mandated join is `tape/sports_clv/` (fair-anchored longshots — the S7c pipeline's
`fair_prob`/`pregame_ask` per outcome) × the `no_bids` resting queue from
`tape/orderbook_depth/`. Result:

- **0/81 joinable (0.00%)** for the primary `fair_prob ≤ 0.20` longshot selection.
- **0/83 joinable** for the `yes_ask ≤ 0.20` proxy selection (asks tagged `real_ask`).
- **Zero event-ticker overlap AND zero outcome-ticker overlap.** The verifier reproduced the 0
  independently by bypassing the probe's own join code — the calendar date is embedded in the
  Kalshi ticker string, so overlap is **structurally impossible**; no join-window relaxation can
  manufacture a match.

### Cause — L9 non-overlap, at the collector level

`sports_clv` fair anchors cover games with kickoffs **06-04 → 07-03** (captured 07-03/04), while
sports `orderbook_depth` began **07-07**. Every fair-anchored game had already **settled** before
the depth tape started. This is L9 ("verify two datasets' date windows actually overlap before
joining") recurring one level up: not a probe-time join bug, but two collectors — `sports_clv`
(via `sports_history`) and `orderbook_depth` — run over **disjoint game windows**, so the join is
forever (permanently) empty regardless of any probe-time care. See L43 below.

### No testable CI

- Fill rate **0.00% (0 fills)** → `mean=None, 95% CI=[None,None], n_units(games)=0`.
- L27 magnitude gate **n/a** (no estimate to gate).
- L41 admissibility correctly **False** on the empty population — no positive-edge claim exists,
  so no suppressed ALIVE, no degenerate-bootstrap artifact.

## The death is a depth-queue timing gap, NOT a winner gap

Critically, the *settlement* side was fully adequate — the death is purely the fill-queue timing
gap, not a missing-winners problem:

- Settlement source `tape/sports_history_s7/worldcup2026.jsonl` (`broker_truth`): **81/81
  fair-longshots settled**, **8/81 = 9.88% settled YES**. A textbook longshot base rate; the
  winners are present and priced.
- The sold-longshot-WINS negative-skew leg is **fully modeled and priced**, never conditioned
  away (Q24 gate #2 / L41 satisfied): `premium − 1 − fee` ≈ **−0.86** on a settle-YES outcome
  (the toxic leg), `premium − fee` on settle-NO.
- Fee = flat **$0.01** maker fee via `core.pricing.fee_per_contract(1−premium, MAKER_FEE_RATE)`
  (L18/L30) — never hand-rolled, never the taker rate.

So the machinery is correct and complete; it simply has zero rows to run on, because the queue
(the one thing only `orderbook_depth` carries) never coexists in time with a fair-anchored game.

## Steelman — quantified, no rescue exists

To make sure the DEAD is honest and not an artifact of one selection, the depth-overlapping
population was examined directly:

- **`sports_pairs` ask≤0.20 longshots** (07-02 → 07-13, which DO overlap the depth tape):
  **346/652 (53%)** have a measurable resting `no_bids` queue; **60/346 (17%)** would rest
  front-of-queue; **MEDIAN queue-ahead = 485 contracts** (asks `real_ask`, queue `real_bid`). You
  rest behind a real, deep incumbent NO-bid queue — this directly **confirms Q24's binding-risk
  thesis** that fills, not edge, are the killer here.
- But **full-sim-eligible** markets (queue AND settlement AND executed-volume all present at once)
  = only **3 markets**, far below the **10-game CI floor** (the same data-adequacy floor that
  killed S19's 2-event-hour filled population).
- The verifier independently confirmed the alternate rescue paths are also empty: `sports_history/`
  (Apr–Jun NBA) and the `sports_pairs`-native `.raw.json` result/volume fields both yield **0
  settled depth-overlapping longshots**. **No rescue.**

## Price source tags (every price, per Rule #3 / trust=FALSE)

| quantity | source tag |
|---|---|
| pregame / longshot asks | `real_ask` |
| resting `no_bids` queue (mirror) | `real_bid` |
| settlement (win/loss) | `broker_truth` |
| `fair_prob` (DraftKings-devig anchor) | `synthetic` |
| executed volume (worldcup candles) | `real_ask` |

Bootstrap unit = **GAME** (L6), via `core.bootstrap.block_bootstrap` + `clears_tick_magnitude`
(unused this pass only because n_units=0).

## What would make this testable (honest terminal state)

The edge-at-quote stays **S7c-proven-rich**; only the FILL question is unanswered — **untested,
NOT falsified.** The one thing that would make Q24's actual probe runnable is a **fresh
collection where `sports_clv` and `orderbook_depth` run concurrently over the same *upcoming*
games** — e.g. a re-collected WC-final / future-window pass where the fair-anchor pipeline and the
L2 depth capture both fire on games that have not yet settled. That is a collector-alignment
change (L43), outside this read-only probe's lane. Until such tape exists, the maker-fill question
is genuinely unmeasurable, and per the Stop rules a DEAD verdict recorded honestly is a success,
not a failure.

## Factor-family cap (S14)

H1/S21 is the same factor family as **S14** — short-the-overpriced-tail, negative skew. If both
ever graduate they share **one factor allocation**; record this in any graduation memo. (Recorded
now per the Q24 spec's factor-cap note.)

## Registry / queue updates

- `kb/strategies/00-index.md`: **S21** registered `dead ✗` (the S7-maker ASK side, sibling of
  S13's bid side) — TESTED 2026-07-13, Q24, verifier-CONFIRMED; DEAD by data-adequacy.
- `LOOP-QUEUE.md` Q24: `TODO` → **DONE (2026-07-13) — VERDICT DEAD by data-adequacy
  (verifier-CONFIRMED)**.
- Citation half of the milestone (already committed): `kb/quant-finance/favorite-longshot-bias.md`
  (3 primary favorite-longshot-bias sources, S7c + L30 tie-ins, S14 factor cap).

## Gates

- `python3 -m pytest` = **742 passed** (30 new Q24 tests, `tests/test_q24_sports_longshot_maker_fillsim.py`).
- `python3 scripts/invariants.py --full` = all green.

## Artifacts

- Probe: `scripts/q24_sports_longshot_maker_fillsim.py` (read-only, queue-aware fill-sim).
- Tests: `tests/test_q24_sports_longshot_maker_fillsim.py`.
- Citation note: `kb/quant-finance/favorite-longshot-bias.md`.
- Provenance color (NOT evidence): `findings/2026-07-13-polymarket-wallet-forensics-s20-dossier.md`
  (S20's Polymarket sprint found the same trade shape in the wild; its wallet stat was degenerate,
  L41 — the evidentiary basis for Q24 is S7c alone).
</content>
</invoke>
