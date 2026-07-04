# S7c — sports CLV verdict: DEAD

`2026-07-04` · LOOP-QUEUE.md Q4/S7c · block-bootstrap CI, binding

## The question

Does buying Kalshi's World Cup/NBA moneyline at the real pregame taker ask, against a
DraftKings-close de-vigged fair probability, clear a 95% block-bootstrapped CI strictly
above zero net of fees? S7a sourced both legs; S7b built the join and produced a small-n
descriptive number (27 games, not a verdict); this stage accumulates the rest of the
available tournament and runs the binding test.

## What changed since S7b

- Re-fetched Kalshi settled `KXWCGAME` events with a raised limit: **87 settled World Cup
  games** now retained (vs. the 25 S7b's tape happened to hold), spanning the full
  tournament to date (Jun 11 – Jul 03; group stage through the round in progress).
- Re-fetched ESPN closing odds for the matching window (`20260611-20260703`): 88 events,
  **all 88 carrying DraftKings odds**.
- Re-ran the join (`collection.sports_history join`): **77/87 matched** (10 `no_match` —
  ESPN's soccer scoreboard endpoint doesn't carry every group-stage game; not investigated
  further, doesn't bias the priced sample since match failure is a data-availability gap on
  the ESPN side, unrelated to the Kalshi price), **0 ambiguous, 0 unparseable** this pass —
  cleaner than S7b's run because the full date range now overlaps.
- Combined with S7b's 3 previously-joined NBA Finals games (not re-joined this pass — no new
  ESPN NBA fetch), deduped by `kalshi_event_ticker` (keep latest `capture_id`): **80 unique
  priced games, 237 priced outcomes** — roughly 3x S7b's n.

## The test

New script `scripts/s7c_sports_clv_bootstrap.py` (read-only, no network — reads the
accumulated `tape/sports_clv/*.jsonl`): block-bootstrap by **GAME** (blocks = all priced
outcomes of one `kalshi_event_ticker`; resampling outcomes directly would treat the 2-3
outcomes of one game as independent draws, which they are not — they share a de-vig and a
kickoff), 10,000 resamples.

```
games loaded (deduped): 80  priced (>=1 outcome): 80  priced outcomes: 237
  KXNBAGAME: 3 games
  KXWCGAME: 77 games

mean edge_after_fee (point estimate) = -0.02354
95% block-bootstrap CI (n_boot=10000) = [-0.02447, -0.02254]

VERDICT: lower CI bound does NOT clear zero -> DEAD (null result)
```

`edge_after_fee` = `fair_prob` (`synthetic` — DraftKings close, de-vigged multiplicatively)
minus `pregame_ask` (`real_ask` — Kalshi candlestick ask anchored at ESPN's real kickoff)
minus the taker fee at that ask. Both CI bounds sit at roughly **−2.3¢ to −2.4¢**: not just
failing to clear zero, but tightly centered well below it — Kalshi's pregame ask is, on
average, running *richer* than a DraftKings-implied fair price by more than the taker fee
covers. The bar (CLAUDE.md prime directive #1 / LOOP-QUEUE Stop rules): a strategy needs a
block-bootstrapped 95% CI strictly **above** zero at real asks. This one sits strictly
**below** zero.

## Verdict: DEAD

**S7 (sports CLV vs DraftKings-close, taker side) is DEAD as specified.** Per the Stop
rules, a DEAD verdict from a real-ask block-bootstrap is a success — it is decided and can
stop consuming loop cycles, not left to linger as "data-collecting."

Notes on why, and what's *not* dead:

1. **This tests the taker side only** (buy at ask). It says nothing about whether Kalshi's
   *bid* side (i.e., being the seller / fading the same mispricing) would clear a positive
   CI — that's a different trade with different fill assumptions (crossing the same spread
   from the other direction) and is not covered by this join. If S7 or a variant is revisited,
   that's the natural next angle, not a rerun of this exact test.
2. **DraftKings, not Pinnacle.** S7a/S7b already documented this downgrade — no free Pinnacle
   API exists. DraftKings carries retail-side vig beyond the multiplicative de-vig's ability
   to fully strip, which could bias `fair_prob` in either direction relative to a true sharp
   line. Directionally, though, a −2.3¢ to −2.4¢ CI this tight (n=80 games, 237 outcomes)
   is a wide enough margin that a sharper anchor closing the gap seems unlikely to flip the
   sign — but it isn't proof against it.
3. **n is still WC-heavy (77/80).** The 3 NBA games are too few to bootstrap alone
   meaningfully; this verdict is really "WC moneyline CLV taker side is dead," generalized to
   S7 broadly on the assumption WC and NBA share the same retail-mispricing mechanism (both
   are Kalshi's general sports-moneyline product, priced by the same market-maker behavior).

## Registry / queue updates

- `kb/strategies/00-index.md`: S7 status `data-collecting` → **DEAD**.
- `LOOP-QUEUE.md` Q4: `IN-PROGRESS` → **DONE** (S7a/S7b/S7c all complete; verdict DEAD).

## Persisted data

No new tape written (read-only probe over existing `tape/sports_clv/` + a re-run of the
existing `sports_history`/`sports_clv` capture, which *did* append: `tape/sports_history/dt=
2026-07-04.jsonl`, `tape/sports_clv/dt=2026-07-04.jsonl`, both schema-identical to S7a/S7b's
existing formats, same per-field source tags).
