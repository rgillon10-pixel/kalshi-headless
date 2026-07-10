# S7a — historical sourcing for the sports-CLV backtest

`2026-07-03` · LOOP-QUEUE.md Q4/S7a · sourcing stage only, no join/probe/verdict yet

## What this stage did

Sourced (and proved live, not just planned) the two legs S7's binding test needs:

1. **Kalshi historical leg** — `collection/sports_history.py::fetch_kalshi_settled`.
   Settled-event discovery via `GET /events?series_ticker=X&status=settled`
   (paginates cleanly, no auth) + per-event market retrieval + one candlestick pull per
   outcome market for provenance.
2. **Free closing-odds leg** — `collection/sports_history.py::fetch_espn_closing_odds`.
   ESPN's public `site.api.espn.com/.../summary?event=<id>` exposes a `pickcenter[0]`
   entry with **DraftKings** `moneyline.{home,away,draw}.{open,close}.odds` — a free,
   reachable, genuinely-closing-line source (ESPN itself labels the two legs `open`/
   `close`, this isn't an inference on our part).

Both legs captured live to `tape/sports_history/dt=2026-07-03.jsonl` (108 lines: 25
World Cup + 40 NBA + 15 NFL Kalshi-side event records, 23 WC + 5 NBA ESPN-side odds
records). 117 unit tests green (13 new, offline/FakeClient/monkeypatched — no network in
CI), `invariants --full` green.

## Finding 1 (load-bearing): Kalshi purges settled markets after ~60 days

`/events?status=settled` lists an event **forever**, but the individual market objects
(`GET /markets?event_ticker=...`, and therefore candlesticks, which need a live market to
resolve) are removed from the public API roughly **60 days** after the market closes.
Verified empirically by binary search on NBA events sorted newest-first:

| event | close date | markets still retrievable? |
|---|---|---|
| `KXNBAGAME-26JUN13NYKSAS` | 2026-06-13 | yes |
| `KXNBAGAME-26APR30BOSPHI` | 2026-04-30 | yes |
| `KXNBAGAME-26APR24BOSPHI` | 2026-04-24 | **no** |
| `KXNBAGAME-26APR03UTAHOU` … | earlier | no |

Consequence for S7's original spec ("last-season NFL/NBA"):

- **NFL**: last settled game was ~2026-02 (Super Bowl); **100% purged** (0/15 sampled
  events had retrievable markets). A full last-season NFL backtest via Kalshi's public
  API is **not possible** — there is no historical ask to pair against ESPN's odds.
  Not a blocker on S7 as a whole (see below), but it does kill the NFL half of the
  original spec outright; recorded here rather than silently reattempted next run.
- **NBA**: only the **playoff tail** survives — roughly `2026-04-30` onward (~40 most
  recent settled events, all retrievable). The regular season (Oct 2025-Apr 2026) is
  gone. Usable n is small (~40 games: 2 rounds + Finals) but real.
- **World Cup 2026** (started ~2026-06-11, still running): the **entire tournament to
  date** is inside the retention window — 25/25 sampled events fully retrievable. This is
  now the strongest candidate dataset for S7, not NFL as originally assumed — and it's
  time-sensitive (tournament ends Jul 19, per Q1's note).

`fetch_kalshi_settled` never drops a purged event silently — it emits the event row with
`retention_available: false` and empty `outcomes`, so a downstream count of "games
available" is always honest, not silently undercounted.

## Finding 2 (load-bearing): `occurrence_datetime` is NOT kickoff

A first draft of this collector used the market's `occurrence_datetime` /
`expected_expiration_time` field as "decision time" (intending: pull the last pregame
candlestick before it). Caught before commit: a live pull showed `yes_ask = 1.0` on
*every* outcome of a Switzerland-vs-Algeria market — impossible pregame (a 3-way bracket
summing to 1.0 total instead of the expected ~1.02-1.10 overround). Root cause: on both a
sampled NBA and World Cup market, `close_time` sits **20 seconds to 18 minutes *before***
`occurrence_datetime` — both fields cluster at game **end**, not game start. Kalshi's
market object carries no kickoff field at all.

Fix: `sports_history.py` no longer claims a decision/pregame price from Kalshi alone. It
captures the raw timing fields (`open_time`, `close_time`, `occurrence_datetime`) plus one
honestly-labeled `sample_ask_near_close` candlestick (proves the candlestick pipeline
resolves a real, non-degenerate ask — e.g. 0.71/0.22/0.09 on the corrected SUI-DZA pull —
but is explicitly *not* a CLV/decision price). True pregame pricing requires the actual
kickoff timestamp, which only ESPN's `event.date` field carries.

## What's still open (S7b, next run)

1. **Game matching**: Kalshi event (`SUI` vs `DZA`, 3-4 letter codes) ↔ ESPN event (full
   country/team names) — needs a code→name table (World Cup: FIFA country codes; NBA:
   standard team abbreviations, likely already close to Kalshi's codes).
2. Once matched, use ESPN's `event.date` (real kickoff) to pull the correct **pregame**
   Kalshi candlestick (`candlestick_ask_before(..., kickoff_ts, lookback_hours=~2)`) —
   the function already exists and is unit-tested, it just hasn't been pointed at a real
   kickoff timestamp yet.
3. Then: Kalshi ask vs de-vig(DraftKings close) fair, fee model from
   `scripts/fee_breakeven.py`, block-bootstrap by game (S7c).

## Honest limitations to carry forward

- The odds source is **DraftKings via ESPN**, not Pinnacle. S7's spec preferred Pinnacle
  (sharp, lower vig) — Pinnacle has no free public API, so this is a real fidelity
  downgrade, not a full substitute. If a paid odds-api key materializes later (Q1 already
  built devig against decimal odds), re-run with Pinnacle and compare.
- ESPN's odds coverage is retail-book and can be sparse for lower-profile games; every
  event with no `pickcenter` entry is recorded with `moneyline: null`, never dropped.
- "DraftKings closing line" ≠ "true market-clearing closing line" — it's one book's close,
  a reasonable but imperfect fair-price anchor.
