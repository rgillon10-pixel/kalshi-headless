# `kalshi_trades` data-quality deep-dive — the tape is clean, the join is not

`research loop` · 2026-08-04 · **IDLE RUN, idle-run policy (c)** · data-quality verdict only:
no P&L, no CI, no registry flip, nothing verdict-class

## Verdict (one line)

`tape/kalshi_trades/dt=2026-08-03.jsonl` is **internally flawless** — 39,698 lines, 39,698
distinct `trade_id`s, zero parse errors, zero broken `yes_price + no_price = 1` identities,
zero sub-tick prices, zero non-positive sizes, zero `trade_day` disagreements with
`created_time`, zero captures dated before the trade they describe, all 24 UTC hours present,
one schema version, one `price_source_tag` (`broker_truth`), one `capture_id` — but only
**10.1%** of its prints can be priced against a bracketing `orderbook_depth` interval, and
**82.7%** land *after the last book snapshot that ticker ever got*. Milestone 1 measured this
join from the book side and got a healthy-looking 65%; measured from the print side it is
**one tenth** of that. Both numbers are correct; they answer different questions, and the
print-side one is the ceiling on how much of the new tape is usable evidence.

Reproduce: `python3 scripts/q51_trade_tape_quality.py` (offline, read-only) →
`reports/q51_trade_tape_quality.json`. Pinned by `tests/test_q51_trade_tape_quality.py`.

## 1. The tape itself: clean, with two fields that are easy to misread

| check | result |
|---|---|
| lines / distinct `trade_id` / duplicates | 39,698 / 39,698 / **0** |
| parse errors | **0** |
| `yes_price + no_price != 1` | **0** |
| sub-tick (non 1c-grid) prices | **0** |
| non-positive `count` | **0** |
| `trade_day` != UTC day of `created_time` | **0** |
| `captured_at` earlier than `created_time` | **0** |
| UTC hours covered | **24 / 24** (no day-boundary truncation) |
| distinct tickers / schema / tag / capture_id | 42 / 1 / 1 (`broker_truth`) / 1 |
| side triples `(taker_book_side, taker_outcome_side, taker_side)` | `bid|yes|yes` 31,831 · `ask|no|no` 7,867 — perfectly collinear, as L279 recorded |

Two fields do **not** mean what their names suggest:

* **`event_ticker` is structurally null on every one of the 39,698 lines.** This is not a
  collector bug: `GET /markets/trades` has no such field. Verified 2026-08-04 with one
  read-only, unauthenticated public GET — the payload carries exactly
  `{count_fp, created_time, is_block_trade, no_price_dollars, taker_book_side,
  taker_outcome_side, taker_side, ticker, trade_id, yes_price_dollars}`. Consequence: the
  **block-bootstrap unit (the game/event, L6) cannot be read off this tape** and must be
  derived from the ticker string. `scripts/q51_maker_fillsim.py::game_of` does exactly that,
  and this audit validates it against the venue's own `event_ticker` from
  `tape/q51_settlement_cache/`: **60 checked, 0 mismatches**. The derived unit is sound —
  but it was never checked before today, and a silent divergence would have invalidated every
  block bootstrap built on this family.
* **`raw_sha256` is a per-QUERY digest, not a per-line content hash** — 42 distinct values
  across 39,698 lines, max multiplicity 10,156 (one per ticker pull). It groups lines by the
  pull that produced them; it cannot verify a line, and it is not reproducible downstream
  (the page sequence it hashes is ephemeral). Useful as provenance grouping, misleading as
  integrity.

**57.45% of executed prints are fractional-size** (p01 = 0.26 contracts, p10 = 1.64,
p50 = 17.94, p90 = 132, max = 17,442). Any fill-sim that silently assumes integer contracts
is modelling a different venue.

## 2. The finding: print-side join coverage is ~10%, and the defect is book-side

Of the 39,698 prints (buckets partition the tape exactly — nothing is silently dropped):

| bucket | same-day books (what the fill-sim reads) | + adjacent days (best case) |
|---|---|---|
| inside a bracketing book span | 4,011 = **10.1%** | 6,825 = **17.2%** |
| **after that ticker's last snapshot** | 17,629 = **44.4%** | 32,812 = **82.7%** |
| before its first snapshot | 97 | 4 |
| ticker has < 2 snapshots that day | 17,961 | 57 |
| reference quote fresher than 15 min | 181 = **0.46%** | 189 = **0.48%** |
| median age of the preceding quote | **149.7 min** | 156.1 min |

The worst dropouts are exactly the highest-volume markets:
`KXNWSLGAME-26AUG02DENBOS-TIE` — 10,156 prints, 6 snapshots, **10,120 prints after the last
one**; `KXMLBGAME-26AUG032005LADCHC-LAD` — 7,596 prints, 9 snapshots, 5,676 after the last.

**The cause is the depth collector, not the trade collector.** Across 2026-08-02..08-04 the
`orderbook_depth` family ran only **10 passes**: 08-02 06:56/09:55/15:56/18:56/21:55, 08-03
00:56/03:56/06:56/15:56, 08-04 09:56. Median gap 180 min (the nominal cadence) but **max gap
1,080 min = 18 h**, starting 2026-08-03T15:56Z, plus a 9 h hole earlier the same day. A
market that trades through an 18-hour book blackout produces perfect trade evidence about a
book we cannot quote.

This also re-scopes L279's orientation measurement honestly: its n=151/n=30 fresh-quote
prints are drawn from the **0.46%** of the tape with a quote younger than 15 minutes. The
measurement stands (it decays monotonically with staleness, as a real relationship does), but
it is a thin slice, and nothing wider is currently available.

## 3. Fill capacity — the size question every fill-sim here has ignored

The milestone-2 predicate asks *"did a qualifying print occur?"* and never asks *"was it big
enough to fill me?"*. Re-tracing all 26 committed fills against the print tape (orientation
imported wholesale from the tested predicate — this audit invents no fill and re-derives no
P&L): 26/26 traced, 0 untraceable.

| resting order size | fillable on the FIRST qualifying print | fillable on the interval's TOTAL qualifying size |
|---|---|---|
| 1 contract | **92.3%** (24/26) | **96.2%** |
| 10 | 57.7% | 92.3% |
| 100 | 15.4% | 73.1% |
| 1,000 | 0.0% | 50.0% |

First-print size p50 = 12.0 contracts; interval-total p50 = 1,113. **Milestone 2's implicit
1-contract assumption is size-safe** (only 2 of 26 fills lean on a sub-1-contract print) —
but the result does not scale: at 100 contracts only 15% of fills are supported by the print
that triggered them, and the interval-total column is an *upper* bound that assumes queue
priority over every other resting order, which this tape cannot observe. Any future capacity
claim must quote the first-print column, not the total.

Related caveat for milestone 3: 12 of milestone 2's 40 legs are **9-hour** intervals (28 are
3-hour). A "maker fill" over a 9-hour rest is a different strategy from one over 3 hours;
the interval length should be carried per row when the population grows.

## 4. Policy-(b) by-product: when Q51 milestone 3's gate actually opens

Computed offline from the committed settlement cache (`n=60` markets, pulled
2026-08-04T12:40Z, 10 already settled, 50 unsettled). Cumulative markets resolvable by close
day: **08-07 → 26 · 08-08 → 37 · 08-09 → 44 · 08-10 → 47 · 08-12 → 57 · 08-20 → 58 ·
08-23 → 60.**

The queue's spec says the gate opens "once the 2026-08-04..08-09 games have been played".
That is **incomplete**: 16 of the 60 markets close *after* 08-09, and the last two close
**2026-08-23**. Practical guidance for the next run: a re-pull on **2026-08-10** yields ~44
settled markets — already far above the L41 floor of 10 units and enough for the first
admissible-by-construction run; a second re-pull after **2026-08-24** completes the sample.
No new collection is needed either time.

## What this does NOT claim

No P&L, no CI, no fill rate is produced or revised here; milestone 2's DATA-INADEQUATE
verdict is untouched, and no row of `kb/strategies/00-index.md` moves. The audit is a
statement about tape, reproducible offline from committed bytes.

**Two-agent rule: N/A** (no verdict-class output). It is also **not satisfiable** in this
environment — no `Task`/subagent tool was available, as on Q19/Q49/Q50 and both Q51
milestones — so no independent `verifier` ran. Every number above is re-derivable by one
offline command over committed tape, which is the strongest available substitute and is not
claimed to be more.
