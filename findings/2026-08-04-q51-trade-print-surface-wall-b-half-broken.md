# Q51 — a public executed-trade tape now exists; WALL-B is HALF broken

`research loop` · 2026-08-04 · **data-adequacy measurement, PROVISIONAL** · no registry flip,
no P&L, no CI

## Verdict (one line)

Kalshi's **public, unauthenticated** `GET /markets/trades` supplies the executed-print surface
that eight dead candidates were killed for lacking, and it **backfills** to before our oldest
book tape — but the binding constraint does not disappear, it **moves to the book side**:
`tape/orderbook_depth/`'s ~3-hour snapshot cadence pins a resting quote only to a 3-hour grid,
so interval-level fill *existence* becomes measurable while queue position and time-to-fill
stay unmeasurable.

**PROVISIONAL.** No independent `verifier` agent was dispatchable in this run's environment
(no agent-dispatch tool was available), so per LOOP-QUEUE.md's two-agent rule this finding is
recorded as PROVISIONAL: it flips no registry status, revives no dead strategy, and every
number below is reproducible from the committed scripts named against committed tape.

## Why this was worth building

Eight candidates — S6, S13, S19, S21, S23, S29, S68, and the S73 idea-stage kill — died on one
recurring sentence: *"`orderbook_depth` has no trade-print field, so a rested maker fill is
unmeasurable"* (lessons L68/L131). The 2026-08-02 and 2026-08-03 Q21 rounds both closed with
the same standing conclusion — *"until that or a comparable trade-print surface lands, further
idea-gen rounds will keep returning zero"* — and 22 consecutive idea-gen rounds have registered
one candidate in total. Meanwhile `kb/kalshi-api/02-rest-and-websocket.md` has listed
`GET /markets/trades` as public market data since 2026-06-18, marked `~` (inferred), and no
collector was ever pointed at it.

The load-bearing field is `taker_book_side` ∈ {bid, ask}: the side of the BOOK the taker
crossed into. A resting maker order fills exactly when a taker crosses into its side at or
through its price, so this field is the direct observable for the question every fill-sim in
this repo has had to synthesise (prime-directive-forbidden as a fill price) or assume away
(`OPTIMISTIC_FILL=True`).

## What was built

- `collection/kalshi_trades.py` — read-only, unauthenticated, append-only trade-print
  collector. Ticker-scoped and/or window-scoped (`min_ts`/`max_ts`), cursor-paginated with a
  per-query call cap, `at_cap` reported on its own axis (L270), deduped by immutable
  `trade_id` so re-running a window appends zero bytes (the L221 byte-redundant-recapture
  shape avoided by construction). Every line `price_source_tag: "broker_truth"` — an executed
  trade is a venue-reported completed transaction, the same epistemic class as Kalshi's own
  settlement `result`; the enum in `core/source_tag.py` is NOT widened. Prices verbatim, no
  normalization (Hard Rule #3). **Deliberately NOT wired into `hourly_pass.py`** — adding a leg
  mutates a live collector's write path, which L221/L222 place outside a research run's lane.
  34 offline tests (`tests/test_kalshi_trades.py`).
- `scripts/q51_trade_print_joinability.py` — the re-runnable adequacy probe. 16 offline tests
  (`tests/test_q51_trade_print_joinability.py`).
- `tape/kalshi_trades/dt=2026-08-03.jsonl` — first capture, 39,698 prints, 23 MB.

Day partitioning is by the print's **own** `created_time`, not the capture day (unlike the
snapshot families), so one backfill pass legitimately writes several past day-files and the
join key is book-day × trade-day.

## Live measurements (2026-08-04)

**Endpoint reachability and history depth.** Public, no auth. Window probes returned prints
for 2026-07-03 and 2026-06-20; 2026-05-01, 2026-01-15 and 2025-08-04 returned zero. History
therefore reaches at least 2026-06-20, which **predates this repo's oldest book tape**
(`tape/sports_pairs/dt=2026-07-03`) — the fill question is retro-testable on already-committed
tape rather than only after N more forward days.

**Venue-wide density (the reason pulls must be ticker-scoped).** A single 10-minute
platform-wide window (2026-07-28T18:00–18:10Z) paged past 6,000 prints with the cursor still
active — order 1e6 prints/day venue-wide, i.e. ~600 MB/day if captured naively. A venue-wide
daily backfill is **not** viable; the collector must be aimed at the ticker population whose
book we already hold.

**First capture (reproduce: `python -m collection.kalshi_trades` with the stride sample, then
`python3 scripts/q51_trade_print_joinability.py --day 2026-08-03`).** Population = the 2,713
distinct tickers in `tape/orderbook_depth/dt=2026-08-03.jsonl`; deterministic stride-13 sample
of 200; window = the full UTC day.

| measure | value |
|---|---|
| prints pulled / written / duplicate | 39,698 / 39,698 / 0 |
| API calls · cursor exhausted · parse errors | 236 · yes (`truncated=False`, `at_cap=False`) · 0 |
| `completeness_ok` | **True** |
| tickers with ≥1 print | **42 / 200 = 21.0%** |
| `taker_book_side` split | bid 31,831 · ask 7,867 |
| book snapshots per ticker (all 200) | mean 1.82, median 1, max 4 |
| **interval coverage, all 200** | 67 / 165 intervals = **40.6%** |
| **interval coverage, traded tickers only (42)** | 67 / 103 = **65.0%** |
| inter-snapshot interval, traded tickers | median **180.3 min**, min 179.9, max 539.8 |
| print price inside preceding snapshot's [bid, ask] | 2,648 / 4,011 = **66.0%** |

Concentration is extreme and sports-dominated: the top ticker alone carries 10,156 prints, and
19 of the 20 traded series are sports (`KXLEAGUESCUPGAME`, `KXMLBGAME`, `KXUELGAME`, …) with a
single crypto series (`KXETH`) present. 79% of sampled book tickers are quoted-but-untraded —
the S48-shape population that has repeatedly flattered breadth counts.

## What this does and does not unlock

**Now measurable.** *Interval-level fill existence*: "given a resting order at the quote
observed at book snapshot `t_i`, did a taker cross into that side at or through that price
before `t_{i+1}`?" On traded tickers that question has an answer 65.0% of the time. This is
enough for a coarse maker fill-sim of the S13/S23/S29 shape, block-bootstrapped by game.

**Still NOT measurable.** Queue position, time-to-fill, and sub-3h adverse selection. The
66.0% price-consistency figure is the honest tell: a third of prints execute **outside** the
[bid, ask] of a snapshot up to three hours stale, so the resting quote cannot be pinned at
print time. This is a property of the BOOK cadence, not a defect in the trade tape — and it is
the reason the claim here is "half broken", not "broken".

**The constraint has moved.** Before this run the missing input was trade data; after it, the
missing input is book *resolution*. That re-prices **Q47** (the Kalshi WS `orderbook_delta`
daemon — built, activation gated on a working key from Ryan): a live book stream plus this
trade tape together close WALL-B completely, where either alone does not.

## Honest limits

- One day, one 200-ticker stride sample, one book family. The 21.0% / 65.0% / 66.0% figures
  are that slice's, not the venue's.
- `interval_coverage` abstains (`None`) rather than scoring 0 for a ticker with fewer than two
  book snapshots — 143 of the 200 sampled tickers have exactly one snapshot on the day and
  contribute no interval at all. That abstention is why the all-200 figure (40.6%) and the
  traded-only figure (65.0%) differ, and both are reported.
- `taker_book_side` tells us which book side was crossed; it does not tell us *how much* size
  sat ahead of a hypothetical resting order. Nothing here converts a fill *existence* result
  into a fill *probability* for a specific queue slot.
- No strategy is revived, no status flipped, no CI computed. This is an input, not an edge.

## Next

1. Q51 milestone 2 — coarse interval-level maker fill-sim re-test of the sports maker family
   over this tape (block bootstrap by game, maker fee 0.0175, `broker_truth` prints joined to
   `real_bid`/`real_ask` book quotes).
2. Backfill more days/tickers, aimed at the populations whose book tape already exists.
3. **Ryan action:** Q47's WS book stream is now the single highest-value unblock.

---

## CORRECTION appended 2026-08-04 (Q51 milestone 2, same day) — the `taker_book_side`
## orientation above is INVERTED

*Annotated, not rewritten (the L191/L236 discipline: a finding is an append-only record of
what a run concluded, and the correction is worth more next to the error than in place of
it). Nothing else in this finding changes — every count, coverage figure and adequacy
verdict above stands.*

This finding states, twice, that `taker_book_side` is *"the side of the BOOK the taker
crossed into"* and that *"a resting maker order fills exactly when a taker crosses into its
side"*. Milestone 2 tested that against the two committed tapes and it does not hold. The
field names the side of the book the **taker's own order sat on**: a taker carrying a BID
is a BUYER and LIFTS a resting offer; a taker carrying an ASK is a SELLER and HITS a
resting bid.

Evidence (`scripts/q51_maker_fillsim.py`, pinned by
`tests/test_q51_maker_fillsim.py::test_acceptance_taker_book_side_orientation_*`),
restricted to prints landing within 15 minutes of their reference book snapshot so the
quote is not up to three hours stale:

| `taker_book_side` | n (≤15 min) | at/above best ASK | at/below best BID |
|---|---|---|---|
| `bid` | 151 | **86.8%** | 9.9% |
| `ask` | 30 | 0.0% | **83.3%** |

and the effect decays monotonically as the join window widens — `bid` prints sit at/above
the ask 86.8% → 84.6% → 70.4% at ≤15 min / ≤60 min / any age — which is what a real
relationship does under a widening join window and what an artifact does not.

Two corroborations, neither of them independent evidence but both consistent: the three
side fields are perfectly collinear on this tape (`bid`/`yes`/`yes` 31,831 rows,
`ask`/`no`/`no` 7,867 rows), so `taker_side` reads the same way; and under the corrected
orientation the 80/20 split says retail overwhelmingly **buys**, the standard
prediction-market pattern, where the original reading would have claimed 80% of taker flow
**sells**.

**Blast radius.** Zero on the data — `collection/kalshi_trades.py` stores the field
verbatim from the API and never derived it, so no captured record changed and no re-capture
is needed. The damage was confined to interpretation, and it was load-bearing: read the
milestone-1 way, milestone 2's fill-sim reported a 27.5% fill rate and a mean of −$0.066;
read correctly, the same tape gives 65.0% and +$0.045. The collector docstring is corrected
in place with a dated note. See `findings/2026-08-04-q51-maker-fillsim-milestone2.md`.
