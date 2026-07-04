# S13 — maker (bid) side of the proven sports rich-ask: verdict DEAD

`2026-07-04` · LOOP-QUEUE.md Q9 · **verdict: DEAD (edge ≈ 0, 95% CI straddles zero)**

## Recap

S7c proved the TAKER side is DEAD: buying Kalshi's pregame ask on World Cup/NBA moneylines
runs +2.35¢ rich vs DraftKings-devig fair (95% block-bootstrap-by-game CI [-0.0245, -0.0225],
n=80 games/237 outcomes; `findings/2026-07-04-sports-clv-s7-verdict.md`). A rich ask is the
mirror-image setup for a MAKER: instead of paying the rich ask, rest a bid below fair and let
someone else cross the spread into you. S13 (`kb/strategies/00-index.md`) asks whether that
side clears zero.

## What was built

`scripts/s13_maker_fillsim.py`, read-only paper fill-sim, no order code:

- **Bid** = `fair_prob` (DraftKings-close devig, S7c's already-proven fair anchor) − 1¢,
  clamped to Kalshi's [0.01, 0.99] tradeable range.
- **Fill** = does the market ever *trade* at or below the bid between the outcome market's
  `open_time` and the game's real kickoff (ESPN's kickoff — not Kalshi's `close_time`, which
  is resolution time; same trap `sports_history.py` already documents)? Read off hourly
  candlestick `price.low_dollars` (the realized trade low, not the ask low — an ask sitting
  above the bid never needs to "trade through" anything).
- **Adverse-selection check** (read literally from Q9's own spec — "compare fair-at-fill vs
  fair-at-entry"): the resting bid can only be informed, at the moment it's placed, by
  whatever line existed then — DraftKings' OPENING moneyline (already in
  `tape/sports_history/`'s ESPN leg, no new pull needed), not the closing line the bid price
  itself uses. `fair_entry` = devig(DK open); `fair_fill` = devig(DK close) = the same
  `fair_prob` already in `sports_clv_join.v1`. This is a proxy — we know a fill occurred
  somewhere in the window, not the instant — stated plainly, not smoothed over.
- Live data: `tape/sports_clv/` (S7b/S7c's matched-game join) + `tape/sports_history/`
  (each ticker's `open_time`, DraftKings' raw open+close moneyline) + one NEW live pull per
  outcome ticker — hourly candlesticks, `open_time` → kickoff — cached to
  `tape/sports_maker_fillsim/` (237 tickers, 93KB; a first draft cached full raw candles and
  hit **98MB for the same 237 tickers**, since some World Cup markets open 4+ months before
  kickoff — trimmed the cache to just the window's minimum trade price + its timestamp, the
  only fields a fill decision needs).
- Fee: **0.0175 (maker)**, not the 0.07 taker rate `core.pricing.fee_per_contract` defaults
  to — caught before the verdict was final; a first pass silently used the taker default and
  overcharged every simulated fill 4×, showing a spuriously-more-negative edge.
- Bootstrap: block-bootstrap by GAME (not outcome), 10,000 resamples, mirroring S7c.

22 new unit tests (`tests/test_s13_maker_fillsim.py`), fully offline (candlestick fetch always
injected). 210 tests green, `invariants --full` green.

## Result

| metric | point | 95% CI | n |
|---|---|---|---|
| fill rate | 94.1% (223/237) | [91.1%, 96.7%] | 80 games |
| `edge_after_fee` \| filled | **+0.00009** | **[−0.00021, +0.00039]** | 80 games / 223 filled outcomes |

**Fill rate is very high (94%)** — but this is largely a function of the window, not a
market property worth celebrating: several World Cup moneyline markets open **months** before
kickoff (one ticker's `open_time` was 2026-02-04 for a 2026-06-14 game), so a bid resting the
whole window has a lot of time to get run over even by ordinary price wander. Reported
honestly as a caveat, not smoothed into the headline number.

**`edge_after_fee` is a wash, not a loss or a win — 95% CI straddles zero.** The reason is
structural, not noisy: bid = fair − 1¢ makes the *entry* edge before fees a fixed 1¢ by
construction; Kalshi's maker fee is `ceil(0.0175 · p · (1−p) · 100)/100`, which is itself
~1¢ per contract for any bid price in the broad middle of the range (peaking at 1.09¢ at
p=0.50) and only shrinks meaningfully out past roughly p<0.13 or p>0.87. So for most of this
dataset's bid prices, **the maker fee alone consumes essentially the whole assumed penny of
edge** — before any consideration of whether the DK-close fair anchor was even right. The
adverse-selection check adds a small, favorable nudge (mean `fair_close − fair_open` =
**+0.00168** over filled outcomes — the line moved slightly toward these bids' side between
entry and kickoff, on average) but it's an order of magnitude too small to move a
near-zero point estimate anywhere.

**Verdict: DEAD.** Not "falsified on the wrong side" like S7's taker verdict — a genuine
null result, CI centered on zero. The 1¢ bid-under-fair convention this design (and the
registry's own spec) picked is barely wide enough to clear Kalshi's own maker fee, let alone
any real edge.

## What would revive this (not built — out of scope for this verdict)

- **Wider bid discount.** Since the fee is what's eating the edge, not adverse selection,
  resting further under fair (2-3¢) would mechanically clear the fee with room to spare —
  at the cost of a lower, untested fill rate. That trade-off is the natural next probe if
  this strategy family gets revisited.
- **A narrower, more realistic resting window** (e.g. last 24-72h before kickoff, not
  `open_time`) — would very likely show a materially lower fill rate than 94%; worth knowing
  before assuming this fill-rate number generalizes to a live quoting strategy.

`kb/strategies/00-index.md` S13 flipped to `dead ✗`.
