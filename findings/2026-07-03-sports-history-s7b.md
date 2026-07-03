# S7b — event matching + real pregame ask vs de-vigged DraftKings close

`2026-07-03` · LOOP-QUEUE.md Q4/S7b · join stage — descriptive only, no CI/verdict yet (S7c)

## What this stage did

Built the join S7a deferred: match a Kalshi settled game to its ESPN closing-odds
counterpart, use ESPN's real kickoff timestamp to pull the correct **pregame** Kalshi
candlestick (not the near-close sample S7a captured), de-vig DraftKings' closing moneyline,
and compute a raw per-outcome edge. All in `collection/sports_history.py`:

1. **`extract_kalshi_teams`** — parses the two team names out of a Kalshi game title. Three
   title shapes are live in the tape (World Cup full form with the ticker-code repeat,
   World Cup bare form, NBA `"Game N: <A> at <B> <CODE> at <CODE> (Mon DD)"`); all three
   strip cleanly to `(team_a, team_b)` in ticker team-code order.
2. **`match_kalshi_espn`** — for each Kalshi event, finds ESPN candidates where BOTH team
   names containment-match (handles NBA's city-name-vs-full-team-name case: "San Antonio"
   ⊂ "San Antonio Spurs") within a ±1-day kickoff window (Kalshi's date token and ESPN's UTC
   kickoff can disagree by a day across timezones). Every input row gets an output row —
   `matched` / `ambiguous` / `no_match` / `unparseable_title`, nothing silently dropped.
3. **`run_clv_join`** — for each `matched` game: maps each Kalshi outcome ticker's 3-letter
   code to home/away/draw via the event ticker's team-code split, pulls a real pregame
   `candlestick_ask_before` per outcome anchored at ESPN's kickoff (6h lookback), de-vigs
   DraftKings' close (`american_to_decimal` → `sports_pairs.devig_multiplicative`), and
   persists a paired record per game with independent per-field `price_source_tag`s
   (`real_ask` on the pregame ask, `synthetic` on the de-vigged fair prob — never blended
   into one tag).

37 new unit tests, fully offline (FakeClient + injected fixtures, no network), covering the
title-parsing edge cases, the ambiguous/no-match/date-window-reject paths, and a full
`run_clv_join` pass. 155 tests green project-wide, `invariants --full` green.

## Live pass

The existing S7a ESPN tape only covered World Cup group-stage dates (Jun 15–21) while the
Kalshi WC events actually captured were round-of-32/16 (Jun 26–Jul 2) — no date overlap at
all. Fetched a fresh, correctly-dated ESPN pull (`--espn-fetch soccer:fifa.world:20260626-
20260702`) before joining:

- **27 games matched** (24 WC, 3 NBA Finals — the NBA ESPN tape only covers that series' 5
  games; 2 NBA games hit `ambiguous` because the same two teams played on consecutive dates
  and both fell inside the ±1-day window — correctly flagged, not guessed).
- **78 outcomes priced** (both a real pregame ask and a de-vigged fair prob present).
- Mean pregame `bracket_sum` **1.020** (vs. the ~1.21 seen on Q1's live BBO snapshot —
  expected: these are majority-liquid marquee games at candlestick-close-to-kickoff, not the
  full thin-market mix Q1 sampled).
- Mean `edge_raw` (fair − ask) **−0.0068**, mean `edge_after_fee` **−0.0241** across the 78
  priced outcomes — small-n, descriptive only. `edge_after_fee` uses the taker fee formula
  from `scripts/fee_breakeven.py` (duplicated as a 2-line pure function in
  `sports_history.py` rather than importing across the scripts/collection package boundary).

**This is not a verdict.** n=78 outcomes / 27 games is far short of a block-bootstrap sample,
DraftKings-close is a retail-book anchor (not Pinnacle, per S7a's documented downgrade), and
no filtering for stale/thin markets has been applied. It only shows the join pipeline works
end-to-end at real prices with honest source tags — S7c still owns the bootstrap + verdict.

## Persisted data

`tape/sports_clv/dt=2026-07-03.jsonl` — one line per matched game: `kalshi_event_ticker`,
`espn_event_id`, `kickoff_ts`, `bracket_sum`, `overround_absorbed`, and per outcome:
`pregame_ask` (`real_ask`), `fair_prob` (`synthetic`), `edge_raw`, `fee_per_contract`,
`edge_after_fee`. Top-level `price_source_tag: "mixed"` — a composite record; the per-field
tags are what's load-bearing (CLAUDE.md trust defaults).

## What's still open (S7c, next run)

1. Accumulate more games — re-run the join as more World Cup rounds settle (tournament ends
   Jul 19) and as NBA's ESPN coverage is widened past the Finals-only slice already tape'd.
2. Block-bootstrap by game (not by outcome — outcomes within one game aren't independent
   draws) → 95% CI on `edge_after_fee`.
3. Verdict + `findings/<date>-sports-clv-s7.md` update; flip S7's registry status accordingly.

## Honest limitations carried forward from S7a (unchanged)

- Odds source is DraftKings via ESPN, not Pinnacle (no free Pinnacle API).
- ESPN's `/summary` odds coverage can be sparse for lower-profile games — the ambiguous/
  no-match counts above already reflect that (NFL had zero ESPN coverage fetched this run,
  consistent with NFL being dead for the Kalshi leg per S7a).
- The ±1-day match window is a deliberate safety valve, not a guarantee — it produced 2
  honest `ambiguous` flags this run rather than a wrong silent pick.
