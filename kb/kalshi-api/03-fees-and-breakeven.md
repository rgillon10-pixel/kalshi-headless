# Kalshi fees & breakeven — the tax that kills thin edges

`reproduced` · formula from Kalshi fee schedule; numbers reproduced by `../scripts/fee_breakeven.py` (2026-06-18)

This is the most important number in the whole project. Every "edge" must clear this bar.

## The formula (verified)

Per **trade** (charged on entry), fee in dollars:

```
fee = roundup_to_next_cent( rate · C · P · (1 − P) )
```

- `C` = contracts, `P` = price in **dollars** (50¢ → 0.50).
- `rate = 0.07` standard **taker**; `rate = 0.0175` **maker**; `rate = 0.035` for
  S&P 500 / Nasdaq-100 products.
- Round-up is on the **whole order**, to the next whole cent.

## Reproduced numbers (taker, per single contract)

From `../scripts/fee_breakeven.py` (run it yourself — `python3 scripts/fee_breakeven.py`):

| price | fee/ct | breakeven P(YES) | edge needed |
|------:|------:|----------------:|-----------:|
| 0.05 | 1.0¢ | 0.060 | +1.0¢ |
| 0.20 | 2.0¢ | 0.220 | +2.0¢ |
| 0.50 | 2.0¢ | 0.520 | +2.0¢ |
| 0.80 | 2.0¢ | 0.820 | +2.0¢ |
| 0.95 | 1.0¢ | 0.960 | +1.0¢ |

Maker at 0.50 → **1.0¢** (half the taker fee). The round-up makes the fee *chunky*: on a
single contract at mid-prices you pay ~2¢ regardless, because `0.07·0.5·0.5 = 0.0175 → 2¢`.

## Why this is the prime-directive bar

A YES buy at 50¢ is only EV-positive if **true P(YES) ≥ ~0.52** (taker). A model that is
"right" by 1¢ of probability is a **guaranteed loser** after fees. And fees are not the
whole tax:

```
total entry cost ≈ quoted_ask  +  fee(≈1–2¢)  +  overround_share(≈3–5¢ across a bracket set)
```

The **overround** is the amount by which the bracket asks sum above 100¢ — you pay it
silently when you lift the ask. arb-bot's pt1 post-mortem: the directional signal was real
(live n=49, ~61.9% win rate) but the **dollar** edge evaporated because synthetic model
prices ignored fee + overround. That is hard-rule #3 (`yes_ask` is not a probability;
normalize `yes_ask / bracket_sum`) and the whole reason `price_source_tag` exists.

## Practical consequences for strategy design

1. **Minimum required edge ≈ fee + overround ≈ 3–7¢** of true vs. fillable probability.
   If a backtest's edge is smaller than this *at real asks*, it is not an edge.
2. **Maker > taker when you can wait.** 4× lower fee + you earn (not pay) the spread.
   Market-making / passive limit orders are structurally favored — at the cost of
   adverse selection and fill uncertainty.
3. **Mid/extreme asymmetry.** Fee is largest (relative to nothing) near 0.5 in absolute
   cents but the round-up means cheap longshots (5¢) pay a *huge* relative fee (1¢ on 5¢
   = 20%). Longshot strategies are the most fee-fragile.
4. **Always persist `fee_paid` and `overround_absorbed` per trade.** A P&L number without
   them is synthetic (hard rule #4).

## Open item

Confirm whether Kalshi still charges fees only on entry (not settlement) and whether any
maker-rebate or volume-tier discount applies to weather series specifically. Pull the live
`get-series-fee-changes` / `get-event-fee-changes` endpoints before sizing.
