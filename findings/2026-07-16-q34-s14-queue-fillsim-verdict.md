# Q34 / S14 — Ladder overround underwriting, queue-aware revalidation: DEAD (edge)

`2026-07-16` · LOOP-QUEUE.md **Q34** · registry **S14** · probe
`scripts/s14_queue_fillsim.py` · tests `tests/test_s14_queue_fillsim.py` (13,
offline synthetic fixtures — no network, no orders, no auth) · **verifier: CONFIRMED**
(independent re-run reproduced every number) · two-agent verdict rule satisfied —
registry flip authorized · every price below carries its source tag.

## The question and the binding gate

S14 was the repo's **only** positive-proxy edge. The first cut (2026-07-13, Q13,
`findings/2026-07-13-ladder-underwriting-s14-firstcut.md`) sold a resting short-YES maker
offer at every strike of a complete MECE crypto-hourly bracket ladder, collected the
overround, paid \$1 on the one strike that settles YES. Under an **upward-biased candlestick
fill proxy** (`max(price.high) >= posted_ask AND volume > 0` — the price merely *printed*, not
that a resting offer behind the whole book was reached) it cleared the gate: block-boot by
event-hour mean **+\$0.0925, 95% CI [+0.063, +0.123]**, n=300. It was recorded honestly as
**PROXY-POSITIVE, not proven** — the verifier's explicit call was "promising-but-proxy-dependent"
and the registry stayed at **0 proven edges**. The one remaining binding gate:

> A **queue-aware L2/depth fill-sim** (`tape/orderbook_depth/`, short-YES queue read off the
> mirror `no_bids` side) modeling queue position + the fill↔winner correlation, CI > 0 at real
> asks over ≥30 event-days.

Q34 is that gate. Falsifiable question: **does the +\$0.0925 headline survive when a
price-time-priority queue replaces the candle-through proxy?** Kill condition: block-boot CI
does not clear zero, or fill adequacy collapses.

## The contrast in one line: +\$0.0925 → −\$0.0453

`scripts/s14_queue_fillsim.py` replaces the L39 candle-through proxy with a real
**price-time-priority queue model**. A new resting short-YES offer joins the BACK of the
`orderbook_depth` `no_bids` queue (the short-YES side mirrors to `no_bids`, because the depth
tape stores the `best_yes_ask` *price* but not the yes_ask *size* ladder — the same read S19/S21
used). It is filled only if the executed volume over the hold clears the queue ahead of it.
Executed volume and the touched-price series come from the **already-committed S14 candle cache**,
read offline — never re-fetched. This is exactly the fill↔winner-correlation-aware model the
first cut said it could not build. The headline inverts:

| fill model | mean P&L/contract | 95% CI | n_units |
|---|---|---|---|
| candle-through proxy (Q13, L39) | **+\$0.0925** | [+0.063, +0.123] | 300 |
| price-time-priority queue (Q34) | **−\$0.0453** | **[−0.0809, −0.0121]** | 146 |

The +\$0.0925 was an **L39 income-leg artifact**. The candle proxy credited premium on income
legs that merely printed; the queue model shows those legs sit behind a queue that the hold's
executed volume does not clear, while the near-money winner leg — heavily traded — fills
regardless and costs the full \$1.

## Verdict: DEAD (edge), verifier-CONFIRMED

Block-bootstrap net P&L **by event-hour** (`core.bootstrap`, unit = event-hour, L6; n_boot =
10000, seed 42):

- mean **−\$0.0453/contract**, 95% CI **[−0.0809, −0.0121]** — the entire interval is below zero.
- n_units = **146** event-hours, n_obs = 146.
- `bootstrap_verdict_admissible` = **True**: n_opposing_units = **54** (54 profitable / 92 losing
  event-hours), well above the min-10-units floor. This is a **genuinely mixed** population, not
  an L41 degenerate-bootstrap artifact — both signs are sampled.
- `clears_tick_magnitude` = **False**: the lower bound −0.0121 is inside the +\$0.01 tick, so even
  the sign-positive tail (there is none — the whole CI is negative) would not clear the L27
  magnitude gate.

Both gates that matter point the same way: the CI is strictly negative AND fails the tick gate.

## Why it dies — the leg decomposition

On the measurable population the leg arithmetic is unambiguous (mean per measurable event-hour):

- bracket_sum **4.056**, overround **3.056** (the fat nominal "edge" the thesis chases),
- premium collected **+\$0.8862**,
- winner payout (the \$1 loss on the strike that settles YES) **+\$0.9315**.

The collectable premium (+0.886) cannot cover the winner loss (+0.931). Once queue position gates
the income legs, you no longer collect the whole overround — you collect the fraction of premium
whose legs' queues actually clear — but you still eat the near-certain \$1 on the winner, which
fills **93.15%** of the time (136/146). The overround is nominal; the loss is real.

## Honest gate results

**Fill adequacy — dies on EDGE, not on adequacy (L53).** Overall fill rate **27.18%** (582/2141
priced-relevant members) — two orders of magnitude ABOVE the S19 0.45% dead-floor. Winner-strike
fill rate **93.15%** (136/146). The long resting window (earliest-capture → close) is precisely
what makes fill rate high (L53: a cumulative-departures model clears almost any queue over a long
window), so the high fill rate is NOT evidence of edge — it is the mechanism of death: the income
legs that DON'T fill are the ones you needed, and the winner that DOES fill is the one that costs
you.

**Coverage (with the L9 caveat).** Event-hour winner-leg coverage **0.3349** (146/436
simulatable event-hours); member-level join **1.0000** (2141/2141 within the overlap window). The
cap on winner-leg coverage is the L9 non-overlap: `orderbook_depth` tape starts 2026-07-07 while
`crypto_hourly` starts 2026-07-03, so only the overlap window joins — that mechanically caps
simulatable event-hours at ~1/3. This is a coverage limit, not a bias: within the overlap every
member joins.

## The winner-leg measurability asymmetry (the discipline this verdict turns on)

**290 event-hours were DROPPED** for winner-unmeasurability — the winner strike's fill could not
be resolved from the offline queue+candle data. They were dropped **strictly on measurability,
which is exogenous to settlement**, and were **never counted with payout = 0**.

This matters because the net P&L contains a leg that is a large fixed loss (the winner's \$1
payout). The S19-family "unmeasurable → no-fill / no-payout" discipline is **not symmetric** when
applied to a loss leg: zeroing an unmeasurable loss fabricates a free win and biases the result
POSITIVE. The correct handling is to drop the whole event-hour on that leg's measurability, and
then to **verify the drop moves the result in the conservative direction**.

The verifier ran two adversarial counterfactuals:

1. **Counting the 290 dropped event-hours as payout = 0** (i.e. as if the winner never filled)
   moves the mean from −0.0453 to **−0.0152** — still negative. The drop is therefore the
   conservative direction: including the dropped hours the generous way still does not resurrect
   the edge, confirming the drop is honest and not a thumb on the scale.
2. The 92 losing / 54 profitable event-hour split (admissibility) was reproduced independently,
   confirming the negative mean is a genuine mixed-population result, not a degenerate resample.

## Source tags and fee handling

All prices carry `real_ask+real_bid+broker_truth`: strike asks are `real_ask`; the resting queue
is the `real_bid` mirror `no_bids` size ladder; executed volume is drawn from the S14 candle cache
(itself `real_ask`-tagged trade prints); settlement is `broker_truth` (Kalshi's own `result`). No
synthetic number is ever quoted as a fill. Fees are the flat \$0.01 maker fee via
`core.pricing.fee_per_contract` at `MAKER_FEE_RATE` (L30, never hand-rolled, L18). Bootstrap via
the sanctioned `core.bootstrap` helpers, unit = event-hour (L6).

## Two-agent verdict trail

- **edge-prober** built `scripts/s14_queue_fillsim.py` + `tests/test_s14_queue_fillsim.py` (13
  offline synthetic-fixture tests) and produced the −\$0.0453 result.
- **verifier** independently re-ran the probe, reproduced the bootstrap mean/CI, the
  admissibility split (54 opposing), the fill rates, the coverage fractions, and executed the two
  adversarial counterfactuals above (the payout=0 stress → −0.0152; the mixed-population check).
  Verdict: **CONFIRM — DEAD (edge)**. Registry flip authorized.

## What this closes

S14 was the repo's last non-DEAD candidate. Its death completes the **proxy → queue-aware purge**:
S13, S19, S21, S23, and now S14 all died once the candle-through fill proxy (L39) was replaced
with a price-time-priority queue model. Every candle-proxy "edge" in this repo to date has been an
L39 income-leg artifact. **The running tally is now 0 proven edges, and 0 non-DEAD candidates.**
A clean DEAD, recorded cleanly, is the success here.

## Gates

`pytest -q`: 996 passed (includes the 13 new `tests/test_s14_queue_fillsim.py`).
`python scripts/invariants.py --full`: green (only the standing non-gating advisories). No
execution code outside the sanctioned paper tier; no network calls (offline against the committed
cache + depth tape); no credentials.

## Files

- `scripts/s14_queue_fillsim.py` — the queue-aware probe (read-only, price-time-priority queue
  over `orderbook_depth` `no_bids`, executed vol from the S14 candle cache read offline).
- `tests/test_s14_queue_fillsim.py` — 13 offline synthetic-fixture tests.
- Canonical numbers live in this finding; the probe emits a scratch JSON summary alongside its
  run, but this document is the source of record.
- Prior context: `findings/2026-07-13-ladder-underwriting-s14-firstcut.md` (the proxy-positive
  first cut this revalidation falsifies).

## Lessons

New rows **L85** (the proxy→queue-aware purge is complete; treat a candle-through fill proxy as
presumptively verdict-invalidating for any P&L that is a small net of two large legs) and **L86**
(the winner/catastrophic-leg measurability asymmetry: drop the unit on the loss leg's
measurability, never zero the loss, and verify the drop is the conservative direction) appended to
`kb/lessons/00-lessons.md`.
