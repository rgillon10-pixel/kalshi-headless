# S7a — historical sourcing for the sports-CLV backtest (Q4, stage 1 of 3)

`2026-07-10` · Q4/S7a · status: **sourced (World Cup) / partial (NBA) / blocked (NFL)**

S7's binding test (CLV harvest: Kalshi moneyline ask vs a de-vigged sharp closing line,
block-bootstrapped by game) needs a season of decision-time real-ask history matched to a
free historical closing-odds source. This stage sources that data and documents its
provenance; it does **not** run the backtest math (S7b/S7c, later queue items).

## What was built

`scripts/sports_history_s7a.py` (16 new unit tests, all offline/no-network) pulls, per
completed World Cup 2026 game:

1. **Kalshi leg (`real_ask`)** — every settled `KXWCGAME` event via `GET /events`
   (`status=settled`, nested markets included — settlement `result`/`settlement_value_dollars`
   arrive inline, no extra call), plus the FULL hourly candlestick series
   (`GET /series/{s}/markets/{t}/candlesticks`) for each outcome market, Kalshi's own
   published `yes_ask` OHLC — the same complement-of-best-NO-bid taker price as every
   other `real_ask` site in this repo. Capped to the last 7 days before close (documented
   `CANDLE_LOOKBACK_HOURS`, logged per-outcome as `candle_window_truncated`) — markets are
   listed as early as ~140 days before their game, and a decision-time backtest (S7b) will
   only ever need the pre-game window, so the far-earlier noise is dropped, not silently.
2. **Odds leg (`synthetic`)** — football-data.co.uk's free, public `WorldCup2026.xlsx`
   (`H-Avg`/`D-Avg`/`A-Avg`: closing decimal odds averaged across their tracked bookmaker
   panel), de-vigged via `core.odds` (decimal → implied prob → multiplicative de-vig,
   same overround-removal math as `core.pricing`). This is a multi-book average, **not**
   Pinnacle specifically (Q1's preferred single sharp book) — a reasonable but weaker
   sharp-consensus proxy, noted honestly rather than mislabeled.
3. Team names are joined order-agnostically (frozenset of two normalized slugs) with an
   explicit alias table (`TEAM_NAME_ALIASES`) for every observed Kalshi/football-data
   naming mismatch (`IR Iran`/`Iran`, `Korea Republic`/`South Korea`, `Turkiye`/`Turkey`,
   `Czechia`/`Czech Republic`, `Congo DR`/`D.R. Congo`, `Bosnia and Herzegovina`/
   `Bosnia & Herzegovina`).

Every record carries `kalshi_raw_sha256` (over the full event+outcome+candlestick payload)
and `odds_raw_sha256` (over the exact xlsx bytes fetched, saved alongside the JSONL) —
provenance is re-verifiable byte-for-byte, not just structurally valid.

## Live pass results

- **97 completed World Cup games** (2026-06-11 .. 2026-07-09), 291 outcome markets, 0
  candlestick fetch failures. Tape → `tape/sports_history_s7/worldcup2026.jsonl` (20 MB) +
  `worldcup2026-odds-source-<run_id>.xlsx` (163 KB, the exact bytes de-vigged).
- **96/97 odds-matched.** The one miss is the most recent game in the dataset (France vs
  Morocco, Jul 9 semifinal) — football-data.co.uk's public file lags live results by a few
  days, an honest source-freshness gap, not a matching bug.
- De-vig sanity-checked: every matched game's `fair_home + fair_draw + fair_away == 1.0`
  (multiplicative normalization is exact by construction; spot-checked, not just asserted
  in the unit tests).

## What did NOT (fully) work: last-season NFL/NBA

`probe_last_season_availability()` (re-runnable, logged in every run's summary) checked
Kalshi's public `/markets` listing directly against `KXNFLGAME`/`KXNBAGAME`:

- **NFL: fully blocked.** `status=settled`/`status=closed` return zero rows. Unfiltered
  `/markets?series_ticker=KXNFLGAME` returns only 66 markets, all with `close_time` in
  2026-08/09 (next season's not-yet-played games) — the 2025 season that finished in
  February 2026 (~5 months ago) has fully aged out of the listing endpoint. Without a
  market ticker, candlesticks can't even be requested (404 on an unknown ticker). This is
  a genuine Kalshi data-retention wall, not a code bug.
- **NBA: partial.** `status=settled` returns 72 outcome markets / **36 games**, but only
  the *tail of the playoffs* — 2026-05-05 through 2026-06-14 (conference finals through
  the Finals, OKC/SAS/NYK). The regular season (Oct 2025–Apr 2026) is gone the same way
  NFL's full season is. So a real, candlestick-fetchable 36-game NBA dataset exists — but
  this run did **not** source a matched free historical NBA odds provider for it (out of
  scope for this stage; football-data.co.uk is soccer-only). Flagged as the natural next
  sourcing target, not solved here.

**Conclusion for the queue:** a full NFL/NBA regular-season backtest needs a different
historical source entirely (a paid Kalshi archive product, if one exists, or a third-party
historical odds+results feed) — that's a new, separate queue item, not a blocker on S7b/c.
**S7b/S7c should run on the 97-game World Cup dataset first** — it is real, complete,
provenance-tagged, and immediately usable. The 36-game NBA playoff window is a documented
opportunity for a follow-up stage once an odds source for it is found.

## Reproducing

```
pip install -e ".[dev,analysis]"       # openpyxl added this run (analysis extra)
python -m pytest tests/test_sports_history_s7a.py -q
python -m scripts.sports_history_s7a   # live pass, appends tape/sports_history_s7/
```
