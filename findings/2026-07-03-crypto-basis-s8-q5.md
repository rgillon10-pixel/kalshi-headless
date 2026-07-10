# S8 — crypto-hourly settlement basis: ρ-guard + overround-composition first cut

`2026-07-03` · LOOP-QUEUE.md Q5 · first cut — **inconclusive on the core hypothesis
(confounded by measurement lag), but resolves the standing +$9.27 overround flag**

## What Q5 asked

Same trick as S2's FOMC first cut: check public candlesticks/spot vs Kalshi's own
settlement, ρ-guard first — if spot and settle move together with no meaningful residual,
the feed-mismatch thesis dies cheap (the weather precedent: NWS vs WU, ρ=0.99999, dead on
arrival, two sensors reporting the same physical reading). Only if the guard survives does a
final-minutes basis-vs-overround comparison, block-bootstrapped by hour, make sense. Also
outstanding: Q2's flag that BTC's hourly bracket shows a **+$9.27 overround**, 1-2 orders of
magnitude fatter than weather/sports, un-investigated as to whether it's real mispricing or
an artifact of ~180 deep-out-of-the-money bands sitting at Kalshi's 1c minimum ask.

`scripts/s8_basis_probe.py` (read-only over `tape/crypto_hourly/*.jsonl`, no network).

## Result 1 — the ρ-guard, and why it can't be trusted alone here

Across the 13 unique settled hours each for BTC and ETH accumulated since Q2 shipped:

| symbol | n hours | ρ (settle vs spot, levels) | mean gap | mean lag |
|---|---|---|---|---|
| BTC | 13 | 0.976 | −$12.74 (−2.1bps) | 1737s (~29min) |
| ETH | 13 | 0.952 | −$1.99 (−11.4bps) | 1742s (~29min) |

Neither is close to the weather precedent's 0.99999. But a level correlation is close to a
foregone conclusion here regardless of whether a real feed mismatch exists: BTC/ETH spot and
settle both track the same intraday trend over a few hours, so ρ→1 is expected on levels
alone (unlike two co-located temperature sensors, there's no reason two price series
following the same asset would fail to correlate). **This number, on its own, is not a valid
kill/no-kill signal for S8** — it's included for continuity with the queue's own framing, not
as the decision basis.

**The real problem: a large, un-plannable confound.** `previous_settlement.expiration_value`
is the exact index value at the hour boundary, but `crypto_hourly`'s `spot` field is whatever
Coinbase/Kraken printed whenever that hour's pass happened to run — mean **29 minutes** after
the boundary (VPS `:23`/cloud `:53` cadence vs settlement on the hour). Over 29 minutes,
ordinary BTC volatility alone can move price well past $100 — enough to fully explain the
observed `max_abs_gap=$150.41` and the `84.6%` of hours with `|gap| > $50` (half a bracket
width) without any feed mismatch at all. **This first cut cannot distinguish "BRRNY
genuinely diverges from spot at settlement" from "spot moved in the 29 minutes since
settlement."** The queue's own phrasing — "public candlesticks... vs public spot **history**"
— was pointing at fetching a historical minute-candle right at the settlement instant
(Coinbase's public `/candles` endpoint, free, no key, `granularity=60`), not reusing the
already-lagged live snapshot already in tape. That fetch was attempted and is the correct
next step, but **this session's egress is currently blocked to every external host tried**
(Kalshi, Coinbase — confirmed via repeated `403` on the CONNECT tunnel, not a code bug); it
could not be run today. ETH's much smaller gap/lag ratio (never crosses half a band) hints
the BTC number may be mostly volatility, not mismatch, but that's a hint, not a test.

**Verdict: inconclusive, not dead.** Unlike S1/S5, this isn't a case where the CI failed to
clear zero — no valid CI exists yet, because the input isn't the right one. **S8 stays
`data-collecting`.** Next real step: rerun `s8_basis_probe.py` with a `--historical-spot`
mode that pulls the Coinbase 1-minute candle at each settlement's `close_time` (lag ≤60s)
the moment egress allows it, then decide the ρ-guard for real.

## Result 2 — the +$9.27 overround flag, resolved (partially)

Composition of the bracket overround across all successfully-captured `current` books:

| symbol | n passes | mean overround | floor-pinned outcomes/pass | share of **overround** from floor | share from near-the-money |
|---|---|---|---|---|---|
| BTC | 19 | +$5.00 | 169.6 / 188 | 33.9% | 66.1% |
| ETH | 18 | +$1.21 | 68.9 / ~100 | 56.9% | 43.1% |

(Mean overround over the accumulated window is lower than the single +$9.27/+$1.23 pass Q2
originally flagged — that was one early snapshot, not the running average; both are real
`real_ask` numbers, not synthetic.)

A deep-out-of-the-money band pinned at Kalshi's 1c minimum ask has a true probability near
zero, so its whole 1c counts as overround (a coherent market would price it near $0, not
$0.01) — that's the "artifact" half of the original flag. **It's real, but it's not the
dominant story for BTC**: only about a third of BTC's overround comes from the ~170 floor-
pinned tail bands; **two-thirds comes from the ~18 near-the-money bands actually being
traded**, i.e. genuine bid-ask spread economics, not a tick-size artifact. ETH splits closer
to even (57%/43%) — its ladder has roughly a third as many outcomes, so floor-pinned bands
are a proportionally bigger share of the book. Either way: **the overround is not simply an
artifact to be waved away** — a majority-to-plurality of it sits on the bands S8's actual
basis trade would touch, so it remains the right benchmark to compare a real settlement-time
basis against once one can be measured cleanly.

## Bottom line

Q5's cheap-kill gate did not trigger a DEAD verdict, but it also did not validate S8 — the
available tape can't yet answer the question it was built to answer, because of a lag this
first cut surfaced (not one anyone had noticed before: `crypto_hourly`'s spot capture is ~29
minutes off the settlement instant it's meant to pair with). That's a real, actionable
finding in its own right: any future crypto-basis work needs spot sampled **at** the
settlement boundary, not at whenever the next hourly pass happens to run. The overround
question is resolved well enough to move on: it's mostly real near-the-money spread, not a
floor-tick artifact, so it's a legitimate cost benchmark for S8's eventual basis test.

**S8 status: stays `data-collecting`.** Blocked on either (a) this environment's egress
reopening to Coinbase's historical-candle endpoint, or (b) a `crypto_hourly.py` change that
captures spot within seconds of the hour boundary instead of at next-pass time.
