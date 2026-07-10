# S7b — CLV trade-set construction (Q4, stage 2 of 3)

`2026-07-10` · Q4/S7b · status: **trade set built; raw signal negative, not yet bootstrapped**

S7a sourced 97 completed World Cup 2026 games (real_ask candlesticks + de-vigged
football-data.co.uk closing odds). This stage turns that tape into a candidate trade
set — a decision-time real ask per outcome, compared against the sharp de-vigged fair
probability, fee-aware net P&L per trade — and reports the raw (un-bootstrapped) signal.
No CI, no verdict: that's S7c, next stage.

## What was built

`scripts/sports_clv_s7.py` (16 new unit tests, all offline, all green):

1. **Decision-time definition.** football-data's H/D/A-Avg odds are the CLOSING line
   (right at kickoff). We don't have an exact kickoff timestamp, so we approximate:
   `decision_ts = close_time - 4h`. Spot-checked against a captured game (France vs
   Morocco) — `close_time` lands within minutes of the final whistle, and regulation +
   stoppage is reliably under 2h, so a 4h offset is comfortably pre-kickoff (before
   lineups/team news at ~T-1h). **Stated limitation:** this snapshot sits earlier than
   the true closing instant, so it isn't an apples-to-apples CLV comparison — a real
   kickoff feed would tighten it; none is free today.
2. **Price selection.** The last candle (by `end_period_ts`) at or before `decision_ts`
   — causal, no look-ahead, same discipline as S1's T-24h rule. Missing a candle at
   decision time for any of the 3 legs drops the whole game (a 2-of-3 bracket_sum would
   mis-normalize the overround) rather than substituting a stale or missing price.
3. **Trade rule.** Single-leg BUY YES only. Compare the de-vigged sharp fair prob
   against Kalshi's own `core.pricing.normalized_ask` (Hard Rule #3 — never a raw ask).
   `fair_prob > normalized_ask` and clearing `--min-edge` (default 0.0, i.e. any nominal
   edge) makes a leg a candidate trade; the ACTUAL fill price and P&L use the raw
   `raw_yes_ask`, never the normalized probability. Fee model reused verbatim from
   `scripts/fee_breakeven.fee_per_contract` (taker rate 0.07).
4. Every trade persists `raw_yes_ask`, `bracket_sum`, `overround_absorbed`,
   `member_count` (=3), `models_json`, `price_source_tag_kalshi=real_ask`,
   `price_source_tag_odds=synthetic` (CLAUDE.md per-trade schema).

## Live pass — raw signal (NOT bootstrapped)

96/97 games usable (1 dropped: odds unmatched, same France-Morocco freshness gap S7a
flagged). **167 candidate trades across 96 games**, `--min-edge 0.0`:

| metric | value |
|---|---|
| mean nominal edge (pre-fee, fair − normalized_ask) | **+1.07¢** |
| mean gross P&L (realized, before fee) | **−1.90¢** |
| mean net P&L (realized, after fee) | **−3.51¢** |
| mean bracket overround absorbed | **+2.27¢** |

**The realized sign is already negative before bootstrapping**, and a quick min-edge
sweep makes it worse, not better — the same "sweep makes it worse" pattern that helped
kill S5:

| `--min-edge` | n trades | n games | mean net P&L |
|---|---|---|---|
| 0.00 | 167 | 96 | −3.51¢ |
| 0.02 | 23 | 18 | −9.30¢ |
| 0.05 | 1 | 1 | −27.00¢ |

If the nominal edge (fair − normalized_ask) were real signal, tightening the bar should
concentrate on higher-quality trades and improve the realized mean; instead it degrades
monotonically. Candidate reads, none confirmed yet: (a) football-data's multi-book
average (not Pinnacle-specific, as S7a already flagged) is a noisier sharp-consensus
proxy than a single sharp book, so its "edge" over Kalshi is partly de-vig estimation
error rather than real mispricing; (b) the 4h-early decision snapshot mixes in market
drift the closing line doesn't share; (c) genuine small-sample noise at n=167/96 games
— a single tournament, likely correlated by team/round. **This is exactly why S7c's
job is a block-bootstrap by game, not this point estimate** — but the point estimate
gives S7c no reason for optimism.

## What did NOT change

No verdict yet. `S7` stays `data-collecting` in the registry. S7c runs the moving-block
bootstrap by game (reusing the `block_bootstrap` pattern from S1/S5), reports the 95%
CI, and — per the queue's binding-test bar — a CI that doesn't strictly clear zero
means DEAD, recorded honestly.

## Reproducing

```
python -m pytest tests/test_sports_clv_s7.py -q
python -m scripts.sports_clv_s7                    # full pass, tape/sports_clv_s7/
python -m scripts.sports_clv_s7 --min-edge 0.02     # sensitivity check
```
