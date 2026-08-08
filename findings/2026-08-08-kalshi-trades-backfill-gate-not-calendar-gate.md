# The S78/S79 data gate is an UN-RUN BACKFILL, not a calendar wait

*2026-08-08 · research loop, IDLE RUN under LOOP-QUEUE step 3, idle-run policy (c)
(data-quality deep-dive on one tape family: `tape/kalshi_trades/`) · main-context build,
no `Task`/subagent tool in this harness (the L287/L288/L290/L291/L295/L308 precedent)*

**Class: DATA-ADEQUACY ONLY.** No bootstrap, no CI, no P&L, no fill rate, no edge claim, no
registry flip. S78 and S79 keep the exact status they had (`collect-and-revisit`, idea-stage);
what changes is the *description of what their gate is made of*. Still 0 proven edges.

---

## The question

Two queue items park the only two live strategy candidates behind a data gate:

| item | strategy | gate as written |
|---|---|---|
| Q52 | S78 toxicity-filtered selective maker | "needs more `tape/kalshi_trades/` days" |
| Q54 | S79 aggressor-flow continuation taker | `below_min_units` — 9 distinct settled games, below the L41 floor of 10 (corrected 2026-08-07) |

Both read as **calendar** gates: wait, and units accrue. Falsifiable question:

> Is that true — or is the population already sitting in committed tape, waiting on a pull
> nobody has run?

Binding test (data-adequacy verdict, no CI): counting only committed tape and the *nine*
declared settlement families, how many distinct **settled sports games** (S79's resample
unit, L6) already have book tape good enough to form an interval? If that count clears the
L41 floor of 10 with material margin, the gate is un-run work, not a wait.

## Method

`scripts/kalshi_trades_backfill_population_audit.py` (new, read-only, fully offline, 9.7s
over the whole committed tape) + `tests/test_kalshi_trades_backfill_population_audit.py`
(23 tests, 5 of them HARD acceptance tests on real committed tape). The funnel imports the
fill-sim's own predicates (`scripts/q51_maker_fillsim.is_sports_game_market` / `game_of`,
and its `len(snapshots) < 2` interval rule) rather than re-guessing them, and resolves
settlement through `core.settlement_sources.resolve_market_results` — all nine families, the
L300/Q54 correction that one-family reads are how this exact gate was mis-stated before.

## Result 1 — there is no scheduled writer, so waiting adds exactly zero days

`kalshi_trades` appears in neither `collection/hourly_pass.py` nor
`collection/burst_capture.py`, nor in `.github/` or `ops/`. This is not a defect: Q51
milestone 1 made that call deliberately on the L221/L222 write-path lane. But the
consequence had never been drawn — **the only writer is a manual `python -m
collection.kalshi_trades` invocation, so "revisit when more days land" describes an event
that cannot occur.** Pinned by
`test_acceptance_kalshi_trades_has_no_scheduled_writer_in_this_repo`, which is deliberately
an *exact* assertion: if someone ever wires the collector in, that test fails and this
finding's framing must be revisited. That is the intended alarm.

Committed trade tape today: **1 day (`dt=2026-08-03`), 39,698 lines, 42 distinct tickers,
0 duplicate `trade_id`s, 39,698/39,698 `broker_truth`** — reproducing Q51-m1's published
39,698 prints / 42 traded tickers exactly.

## Result 2 — the joinable population already in committed tape is 338 game units

Union over the 31 committed `tape/orderbook_depth/` days (`dt=2026-07-07` … `dt=2026-08-07`):

| funnel stage | count |
|---|---|
| distinct tickers in book tape | 107,033 |
| … with ≥2 snapshots on some day (one interval is formable) | 45,495 |
| … that are sports-game markets (S79's population) | 6,837 tickers / **2,575 games** |
| … whose outcome a committed settlement family already resolves (`broker_truth`) | 611 tickers / **338 games** |

**338 distinct settled sports games = 33.8x the L41 floor of 10**, versus the 9 units Q54
measured on 2026-08-07. The 9 was not wrong; it was the population of the *one* trade day
that happens to be captured. The 338 needs no new market to be played and no day to pass —
only the print leg to be pulled.

Settlement provenance (`broker_truth`, per-source first hits over the eligible set):
`crypto_hourly` 35,052 · `settlement_ledger` 601 · `q51_settlement_cache` 10 · all other
declared families 0. The sports units come from `settlement_ledger` + the Q51 cache.

Per-day settled-sports-game counts are **lumpy, and reported that way rather than averaged**:
169 (07-07), 189 (07-08), 158 (07-10), 163 (07-11), 110 (07-12), 34 (07-13), 28 (07-14),
3 (07-15), then a long stretch of 0-3 through 07-30, 8 (07-31), 10 (08-01), 10 (08-02),
7 (08-03), and **0 for 08-04 … 08-07**. A zero day means *nobody cached those markets*, not
that they did not settle — settlement is itself fetched by an unauthenticated public
`GET /markets/{ticker}` (`q51_maker_fillsim.build_settlement_cache`). So **both** missing
legs are pulls, not waits.

## Result 3 — the historical print endpoint really does serve long-settled markets (measured)

The whole finding rests on one assumption Q51-m1 stated but never tested against a *settled*
market: does `/markets/trades` still return prints for a market that closed weeks ago? Three
read-only, unauthenticated calls (public market data; no credentials, no order path; nothing
committed to tape from this probe):

| ticker | day window | prints returned | calls |
|---|---|---|---|
| `KXBRASILEIROBGAME-26JUL07ATHFER-TIE` | 2026-07-07 | **392** (first `created_time` 2026-07-07T23:59:56Z) | 1 |
| `KXALLSVENSKANGAME-26JUL11MJAAIK-TIE` | 2026-07-08 | 2 | 1 |
| `KXARGNACBGAME-26JUL25CHISMT-SMT` | 2026-07-22 | 0 | 1 |

`price_source_tag = broker_truth` (executed prints). **32-day-old settled markets still serve
their full print history** — the assumption is now measured, not assumed. The third row is
the honest counterweight: a market can simply have had no trades in a day window.

## The haircut, labelled as the projection it is

Ticker-level print incidence was measured once — 42/200 = **21.0%** of sampled book tickers
had ≥1 print on 2026-08-03 (a whole-universe stride-13 sample, *not* a sports-only rate).
Applying it: 338 × 0.210 ≈ **71 units, 7.1x the floor**. This is `price_source_tag: synthetic`
and the audit's own report flags it `is_projection: true` with its basis attached. It is a
crude bound in both directions — a game survives if *any* of its tickers printed, so a
ticker-rate applied to game units understates; and sports moneylines likely trade more than
the average listed market, so 21.0% is probably pessimistic here. The point is the order of
magnitude: **even a harsh haircut leaves the floor cleared several times over.**

## Redundancy (the sanctioned stand-in when no `verifier` is dispatchable)

No `Task` tool exists in this harness, so no independent `verifier` agent could be
dispatched. Following the L221/L308 precedent, the headline was re-derived by a **second,
independently written code path** that imports nothing from the audit module or from
`q51_maker_fillsim`: its own ticker grammar, its own eligibility pass, and its own direct
readers over the raw settlement files (ledger JSONL, the five `*_settlement_cache` blobs, and
the three embedded families). It reproduces **45,495 eligible / 6,837 sports tickers / 2,575
eligible games / 611 settled sports tickers / 338 settled games**, and the two game *sets* are
**set-equal (symmetric difference 0)**. This is a redundancy check, **not** a verifier
confirmation: it cannot catch an error both paths share (e.g. if the `-`-suffix ticker
grammar mis-splits some series into games). The count is therefore recorded **PROVISIONAL**
and flips nothing.

## Honest limits

1. **Potential, not realized joins.** 338 is the population a backfill *could* unlock; not a
   single print for those games has been captured. The realized number will be lower.
2. **Book cadence still binds fill realism.** Median inter-snapshot interval on the traded
   day was 180.3 min (Q51-m1) — a resting quote can only be pinned to a ~3h grid, so
   queue position, time-to-fill and sub-3h adverse selection stay unmeasurable (L283, WALL-B's
   surviving half). More units do not repair that; only Q47's WS depth stream would.
3. **Settlement lumpiness is structural**, not sampling noise — it tracks which probes cached
   which markets. The 08-04..08-07 zeros are cache absence.
4. **The 21.0% haircut is borrowed from a different population** (whole-universe, one day).
5. Two acceptance tests assert *bounds* (`>=`), not equalities, on every tape-sourced number,
   because a legitimate step-0b sweep may union-append lines (L280).

## What a bounded backfill would cost (proposal, NOT executed this run)

Sizing from the one committed day: 23,993,603 bytes / 39,698 lines ≈ **604 bytes/print**, and
39,698 prints across 42 traded tickers ≈ 945 prints/traded ticker. Backfilling all 611 settled
sports tickers unbounded could therefore reach ~350MB — unacceptable next to a `tape/` that is
already 378MB for `orderbook_depth` alone. A bounded phase 1 instead:

* target only the **611 settled sports tickers**, `min_ts`/`max_ts` scoped to each ticker's own
  book-snapshot span on its eligible day (not the whole day), with the collector's existing
  `--max-calls` cap and its `trade_id` dedup;
* start with the **07-07 … 07-14 window**, which holds the bulk of the 338 units;
* measure realized bytes after the first ~50 tickers and stop if the extrapolation exceeds a
  declared cap (suggest 25-50MB for phase 1);
* only then decide whether S78/S79 warrant the rest.

This is a collector milestone, not a probe: it does not test an edge, and the probe that
would consume it must still clear the real-ask bar afterwards.

## Reproduce

```
python3 scripts/kalshi_trades_backfill_population_audit.py           # -> reports/kalshi_trades_backfill_population.json
python3 -m pytest tests/test_kalshi_trades_backfill_population_audit.py -q
```
