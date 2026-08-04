# Q51 milestone 2 — the sports maker family, re-tested against REAL executed prints

`research loop` · 2026-08-04 · **DATA-INADEQUATE (not a kill, not an edge), PROVISIONAL** ·
no registry flip

## Verdict (one line)

The maker fill question is now genuinely measurable — every one of 26 simulated fills traces
to a `broker_truth` executed print, and interval coverage on the scoreable population is
**85%** — but the resulting bootstrap rests on **7 games**, below the L41 floor of 10, and
its 95% CI **straddles zero**. The family is therefore **not re-opened and not re-killed**:
the answer is *"not measured yet"*, and the constraint has moved a third time — from trade
data (milestone 1's answer) to book resolution (milestone 1's revised answer) to
**settlement recency**.

**Headline object** — rest at the observed touch, hold to settlement, all intervals,
`price_source_tag: real_bid` on the rest price, `broker_truth` on the fill evidence:

| | |
|---|---|
| mean | **+$0.0445** / contract |
| 95% CI (block bootstrap by GAME, n_boot 10,000, seed 42) | **[−$0.0212, +$0.1202]** |
| n_units (games) | **7** — below `MIN_UNITS = 10` |
| losing clusters | **4 / 7** (the S20 ≥1 requirement is satisfied) |
| legs / filled | 40 / 26 → **fill rate 65.0%** |
| interval coverage | **17 / 20 = 85.0%** |
| L41 admissibility | **False**, reason `['below_min_units']` only |
| L27 tick-magnitude gate | **False** (CI lower bound is negative) |
| `sign_bounded_objective` | `verdict_bearing: True`, `inadmissibility_is_definitional: False` |
| maker fee | 0.0175 (`core.pricing.MAKER_FEE_RATE`), never the 0.07 taker rate (L5) |

That last row is the load-bearing nuance. Per L249's discriminator the inadmissibility here
is **not definitional** — the object has 15 positive and 11 negative observations spanning
−$0.56 to +$0.55 across 7 units, so it genuinely *could* have disagreed with itself. This
is an honest "not enough data", repairable by more data under the same design, not a gate
that arithmetically bounds its own sign (the Q49/S68 failure mode).

## The first result was that milestone 1 read the tape backwards

Milestone 1's collector docstring and finding both define `taker_book_side` as *"the side of
the BOOK the taker crossed into"*, and derive from that: *"a resting maker order fills
exactly when a taker crosses into its side"*. Building the fill predicate on that sentence
and then checking it against the book falsified it.

Restricting to prints landing within 15 minutes of their reference snapshot (so the quote is
not up to three hours stale):

| `taker_book_side` | n (≤15 min) | at/above best ASK | at/below best BID | strictly inside |
|---|---|---|---|---|
| `bid` | 151 | **86.8%** | 9.9% | 3.3% |
| `ask` | 30 | 0.0% | **83.3%** | 16.7% |

A `bid`-tagged print executes *at or above the offer*. It is a **buy**. So the field names
the side the taker's **own order** sat on, not the side it crossed: a taker holding a bid
lifts the ask. The corroborating decay is the part that makes this a measurement rather than
an anecdote — the `bid`→ask agreement falls 86.8% → 84.6% → 70.4% as the join window widens
from ≤15 min to ≤60 min to any age, which is what a real relationship does when you add
staleness and what a spurious one does not.

Two weaker corroborations: the three side fields are perfectly collinear on this tape
(`bid`/`yes`/`yes` 31,831; `ask`/`no`/`no` 7,867), so `taker_side` reads identically; and
under the corrected orientation the 80/20 split says retail overwhelmingly **buys**, the
standard prediction-market pattern, where milestone 1's reading implied 80% of taker flow
**sells**.

**This was load-bearing, not a naming quibble.** The identical tape, read the milestone-1
way, gives a **27.5%** fill rate and a mean of **−$0.066**; read correctly, **65.0%** and
**+$0.045**. Both are inadmissible, so no recorded verdict was ever wrong — but the sign of
the point estimate flips, and a run that had not checked would have published the wrong one.
No captured record changed: the collector stores the field verbatim from the API and never
derived it, so the correction is confined to interpretation. `collection/kalshi_trades.py`'s
docstring is corrected in place with a dated note and the milestone-1 finding is annotated
(appended, not rewritten).

## What was actually built and measured

`scripts/q51_maker_fillsim.py`. Read-only; fully offline in analysis mode. **Mechanism:** at
book snapshot `t_i`, rest a maker order at the observed touch — `best_yes_bid` (a YES bid)
and, as an independent second leg, `best_no_bid` (a NO bid). Ask whether a taker crossed into
that side at or through that price before `t_{i+1}`. Hold any fill to settlement.

- **Fills come from prints, not from a proxy.** This is the first fill-sim in this repo whose
  fills are neither a queue-departure proxy (L48/L250) nor an `OPTIMISTIC_FILL=True`
  assumption. The predicate reads a `broker_truth` print or returns `False`; a synthesised
  fill cannot occur by construction. 26/26 fills carry a `trade_id`.
- **Both sides always scored.** YES-bid and NO-bid legs are each scored on every interval and
  each can lose; the sold side's losses are modelled, never conditioned away. The two legs are
  deliberately **not** paired into a both-bid capture object — that object is sign-bounded by
  its own spread gate (L249, Q49/S68) and this probe does not build it.
- **Two coverage branches, headline is the conservative one.** `all_intervals` (headline)
  scores a zero-print interval as a **no-fill**, which is legitimate only because milestone
  1's capture was ticker-scoped over the whole UTC day with the cursor exhausted
  (`completeness_ok=True`, `at_cap=False`), so a zero on a sampled ticker is a *measured*
  zero. It dilutes the mean toward zero and makes the bar harder. `covered_intervals`
  (sensitivity, conditions on activity) gives fill rate 76.5%, mean +$0.0524, CI
  [−$0.0250, +$0.1361], 6 units — also inadmissible.
- **Population.** Milestone 1's 200-ticker stride sample is reconstructed deterministically
  from the depth tape's own insertion order and **checked**: all 42 tickers carrying prints
  must fall inside it or the run aborts rather than analyse the wrong denominator. Restricted
  to sports `*GAME` series (60 markets, 60 games), `KXMVE*` excluded (L31).
- **Settlement** is the one network path: an unauthenticated public `GET /markets/{ticker}`
  for 60 tickers, cached to `tape/q51_settlement_cache/settlement.json` (`broker_truth`) so
  every re-run and every check is offline. Non-binary results are filtered through
  `core.settlement` (L52), never hand-compared.

Side legs, both inadmissible and both straddling zero, reported for completeness: YES-bid
only — 20 legs, fill rate 45.0%, mean −$0.0015, CI [−$0.2048, +$0.1859]; NO-bid only — 20
legs, fill rate 85.0%, mean +$0.0905, CI [−$0.1528, +$0.3252]. The **fill-rate asymmetry
(45% vs 85%) is the one robust observation in this run** and it follows directly from the
corrected orientation: taker flow is 80% buying, so an offer gets lifted far more often than
a bid gets hit. Any future maker strategy on this population should expect to be filled
mostly on the side it is selling.

## Why n=7: the constraint moved to settlement recency

Of the day's **165** sports intervals, **145 (87.9%) are dropped because the market has not
settled** — 49 of the 60 sampled sports markets are for games scheduled 2026-08-04 through
2026-08-09, still `active` when the settlement cache was pulled on 2026-08-04. Only 10
markets were `finalized`; 3 more tickers had a single snapshot and contribute no interval.
**Zero** intervals were lost to a missing settlement record, a non-binary result, a one-sided
book, or a post-close entry.

This is the cleanest possible statement of the remaining gap, and the fix requires **no new
collection**: re-pulling the same 60 tickers' settlement once those games have been played
converts 145 dropped intervals into scoreable ones over tape that is **already committed**,
taking the bootstrap to roughly 57 game units and ~330 legs. That is milestone 3, and it is
a one-command re-pull, not a data-collection campaign.

## Binding gates — how each was satisfied

| Gate | Status |
|---|---|
| Every fill traces to a `broker_truth` print | 26/26, `all_fills_traced: true`; predicate cannot synthesise |
| 3-hour interval resolution is a CEILING | No queue-position or time-to-fill number is computed anywhere; the report's key set is asserted free of them by test |
| Interval coverage reported alongside any fill rate | 85.0% (17/20) reported on both branches |
| Block-bootstrap by GAME, never by outcome | `unit_values` groups on the event key (L6) |
| Maker fee 0.0175, not 0.07 | `core.pricing.MAKER_FEE_RATE`, regression-tested against the taker rate (L5) |
| Sold-side losses modelled | Both legs scored on every interval; 4 of 7 clusters lose |
| ≥1 losing cluster or the claim is void (S20) | 4 losing clusters of 7 |
| L27 tick-magnitude gate | Applied; fails (lower bound negative) |

**Kill conditions from the queue spec:** the CI does not clear zero and the magnitude gate
fails, which under the spec reads as a kill — but the same spec kills on *"interval coverage
so low the fill rate is data-inadequate"*, and the L41 gate fires first on `below_min_units`.
A CI that is inadmissible is **not a verdict** (that is the whole point of the gate), so this
run records **DATA-INADEQUATE** and explicitly declines to convert a 7-unit straddle into a
kill. S13/S23/S29 keep the status they already had; nothing is revived.

## Two-agent status: PROVISIONAL

No `verifier` subagent was dispatchable in this run's environment (no `Task` tool in
context — the same constraint recorded on Q19, Q49, Q50 and on Q51 milestone 1 itself). The
sanctioned fallback was used: `scripts/q51_maker_fillsim_rederive.py`, a second independent
code path with its own reader, its own Decimal round-up fee arithmetic (vs the probe's
`math.ceil`), its own game grouping, its own bootstrap and a different seed (20260804),
reading **only** `reports/q51_maker_fillsim_rows.jsonl` and never importing the probe. It
reproduces 40/40 rows with **0 P&L mismatches, 0 untraced fills, 0 price-tag violations**,
mean +$0.04450, 7 units, 4 opposing, CI [−$0.0212, +$0.1181], `admissible: false`,
`clears_tick: false`.

That is a redundancy check, **not** a verifier, and it is honest about its limit: it could
not have caught the orientation error on its own — only the tape did. **The verdict stays
PROVISIONAL, flips no row in `kb/strategies/00-index.md`, and revives no strategy.**

## Honest limits

- One day, one 200-ticker stride sample, one book family, 7 scoreable games. Nothing here
  generalises to the venue.
- Resting at the touch is one arbitrary quote choice among many; no offset ladder was swept,
  because 7 units cannot support one.
- The headline branch's zero-print-is-a-no-fill rule inherits milestone 1's per-ticker
  completeness claim. If that claim is wrong for any sampled ticker, the headline is
  optimistic about no-fills and pessimistic about the mean; the `covered_intervals` branch,
  which makes no such assumption, is reported alongside and reaches the same verdict.
- **Not measurable and not claimed:** queue position, time to fill, sub-interval adverse
  selection, partial fills, and the size that sat ahead of a hypothetical resting order. The
  ~3-hour book cadence is a hard ceiling on all of them.

## Next

1. **Milestone 3** — re-pull `tape/q51_settlement_cache/settlement.json` once the 2026-08-04
   → 08-09 games have been played, and re-run `scripts/q51_maker_fillsim.py` unchanged over
   the already-committed tape. Expected ~57 game units / ~330 legs — the first
   admissible-by-construction run of this design, over data we already hold.
2. Only then consider extending the trade tape to further days, and only aimed at ticker
   populations whose book tape already exists (never venue-wide — ~1e6 prints/day).
3. **Ryan action, unchanged from milestone 1:** Q47's WS `orderbook_delta` stream remains the
   single highest-value unblock — it is what would lift the 3-hour ceiling and make queue
   position and time-to-fill measurable at all.
