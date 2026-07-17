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

## Weather-series fee schedule (confirmed 2026-07-17, LOOP-QUEUE.md Q37 sub-task)

`broker_truth` (live Kalshi API, read-only) unless noted `docs`. Reproduce with
`python scripts/weather_fee_schedule_probe.py` (offline-tested in
`tests/test_weather_fee_schedule_probe.py`).

1. **Settlement fees are zero for binary yes/no contracts** (`docs`, Kalshi's Market
   Settlement doc: "Settlement fees are zero for simple yes/no determinations but may apply
   for sub-cent scalar settlement"). All weather series here are binary — fees are charged
   once, at fill, never again at resolution. Confirms the existing assumption in this file.
2. **No series-level or event-level fee override on any weather series.** Live-checked all
   48 temperature series the collector's own discovery (`collection.weather_books`)
   currently tracks (config `high_series`/`low_series` union the "Climate and Weather"
   category's hourly-directional title sweep): every one carries the STANDARD base rate
   (`fee_type: "quadratic"`, `fee_multiplier: 1` — the same coefficients `core.pricing`
   already uses, no special weather discount). `/series/fee_changes` and
   `/events/fee_changes` (both `show_historical=True`) return an empty array for every
   series checked, including `KXTEMPNYCH` — zero historical or scheduled overrides, ever.
3. **A standing platform-wide Liquidity Incentive Program (LIP) DOES apply to weather
   series** — this is the open item's "maker rebate" answer, and it is real. Every newly
   listed weather market (both the `KXTEMPNYCH`-family hourly-directional series and the
   daily `KXHIGH*`/`KXLOWT*` ladders) gets a `type: "liquidity"`,
   `incentive_description: "new_event"` program: `discount_factor_bps: 5000` (a 50%
   discount factor) for a window of ~54–60 minutes right after listing (a handful of
   outliers ran longer, up to ~11h — not yet explained), gated on providing up to
   `target_size_fp` 1000 (or 300 on some markets) contracts of resting size. Live pull
   (2026-07-17, 40 bounded pages / 40,000 programs, **truncated — the platform-wide
   incentive universe exceeds the pull cap, so this is a lower bound, not a full census**):
   10,372 weather-tagged programs across 25 series, window observed 2026-05-12 → ongoing
   (still generating new entries at probe time — this reads as a standing program, not a
   one-off promo). **Not fully understood, flagged rather than guessed at:** the exact
   payout mechanics — how `discount_factor_bps` (a fee discount) and `period_reward`
   (a separate "total reward for the period in centi-cents" field) combine, and what
   qualifies a specific order for the discount vs. the reward — are not in Kalshi's public
   API docs beyond field names. Before Q37 sizes off this, pin the mechanism (support
   ticket or empirical fee-paid-on-a-real-fill check) rather than assuming a specific
   formula.

**Bottom line for Q37:** the base maker fee (0.0175) is the right assumption for a
between-listing-windows resting bid, but a resting bid placed within the first ~hour of a
NEW weather market's life may be discounted ~50% by this LIP — a real, currently-live lever
this file didn't previously account for. Whether that window is exploitable (does it
overlap with when Q37's EMOS-filtered entries actually fire?) is untested — a new
sub-question for Q37's own milestone, not answered here.

**Not a re-open of the killed "LIP maker-rebate harvest" idea.** `kb/00-LOG.md`'s dead-end
ledger (2026-06-18) and `findings/2026-06-18-codebase-money-map.md` already killed a
DIFFERENT proposal at idea stage — treating the LIP reward payout itself as the edge
("harvest the rebate"), correctly rejected as sub-$1-per-provider against dedicated farmers
plus the same adverse-selection overround as any resting bid. This entry does not revive
that idea. It answers a narrower, purely mechanical question Q37 needs regardless: what fee
rate applies to a Q37 EMOS-signal maker bid if it happens to land inside a new-listing
window. The `period_reward` totals above are the PROGRAM's pool, not a per-provider payout
estimate — do not conflate the two.
