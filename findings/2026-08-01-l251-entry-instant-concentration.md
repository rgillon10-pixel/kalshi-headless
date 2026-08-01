# L251 → test: entry-instant concentration, and the artifact Q49's caveat under-scoped

**2026-08-01, research loop IDLE RUN (policy (a): convert an UNENFORCED lesson into a
test/invariant).** No numbered queue item was eligible — Q0–Q49 carry no TODO/IN-PROGRESS
status as their newest status line, and the one item beyond that range (Q50) is **claimed**
by an unmerged in-flight branch (`idle-run-a-q50-s68-gate-ladder`, pushed 2026-08-01T14:14Z),
which also already claims lesson IDs `L253`/`L254`.

**No verdict, no CI, no registry change.** Q49/S68's `DEAD-by-fee` verdict
(`findings/2026-08-01-q49-s68-bothside-maker-fillsim-verdict.md`, verifier-CONFIRMED) is
untouched and `kb/strategies/00-index.md` is not edited by this run. Still **0 proven edges**.

## What L251 said, and what was actually buildable

L251 (filed 2026-08-01 by Q49's verifier pass) named two candidates and judged the whole row
"not statically assertable ... likely terminal as protocol/discoverability". That judgment is
**half right, and the half that is wrong is the useful half**:

- The **entry RULE** — "prefer *first snapshot with ttc≤H* over *earliest capture, then
  filter*" — genuinely cannot be scanned. A static checker cannot read a probe's population
  construction and tell which of the two it implements. This stays **protocol**.
- The **resulting timestamp DISTRIBUTION**, however, is a plain statistic over a list the
  probe already has in hand. Nothing prevented computing it; it simply had not been written.
  This is now **test**.

## Built

`core.bootstrap.entry_instant_concentration(instants, *, unit_labels=None, flag_share=...)`
+ `core.bootstrap.TAPE_START_CONCENTRATION_SHARE = 0.5`. It reports, for any labeled
population: `n_distinct_instants`, `top_instant` / `top_instant_count` /
`max_instant_share`, `entries_per_distinct_instant`, and — when handed the **same unit the
caller will block-bootstrap on** (L6) — `n_units`, `n_units_on_top_instant`,
`unit_share_on_top_instant`, `n_unit_instant_pairs`.

The load-bearing output is **`n_units == n_units_on_top_instant`**: when every bootstrap
block draws from one capture instant, the unit count is not evidence of independence, it is
a costume. That is precisely how Q49's "20 candidates, 5 game-series, 14 games" read as
breadth.

Deliberate design limits, stated in the docstring rather than discovered later:

- It is a **descriptor, not a verdict**. It cannot tell a tape-start artifact from a genuine
  cluster — an event-window study around one release instant *should* concentrate.
- The 0.5 flag is **blunt and documented**, not derived; the threshold actually used is
  echoed back in every result dict so a write-up cannot quietly re-interpret a flag under a
  different bar than the one that produced it.
- Empty input returns `no_signal=True`, never a clean bill (the repo's
  no_signal-vs-False discipline).
- A `unit_labels` length mismatch raises rather than silently misaligning two sequences
  (same posture as `bracket_by_movement`).
- Top-instant ties break by `str()` order, so a quoted `top_instant` reproduces
  byte-identically across runs and across mixed `str`/`datetime` inputs.

Charter half: `.claude/agents/edge-prober.md:123` now carries an L251-citing house-style
bullet naming the failure mode and mandating that the descriptor be printed beside every
labeled cut's `n`.

## The measurement — Q49's contamination was never confined to the primary cut (→ L257)

Recomputed from committed tape by re-running Q49's own loaders
(`scripts/q49_s68_bothside_maker_fillsim.py::load_settlements` /
`::load_preclose_snapshots` / `::build_trades` / `::cut_trades`, unmodified) and feeding
each cut's `entry_captured_at` list to the new descriptor, with `series_of(ticker)` — Q49's
own bootstrap unit — as `unit_labels`:

| cut | n | distinct instants | top-instant share | units | units on top instant | flagged |
|---|---|---|---|---|---|---|
| `fillable_entry` (PRIMARY) | 20 | **1** | **100.0%** | 5 | **5** | yes |
| `nearclose_le_24h` | 20 | **1** | **100.0%** | 5 | **5** | yes |
| `spread_le_10c` | 284 | 12 | **54.9%** | 17 | 12 | yes |
| `unrestricted` | 445 | 23 | **47.2%** | 18 | 12 | no |

**The top instant of all four cuts is the same one:
`2026-07-07T01:23:57.700581+00:00`** — the `orderbook_depth` tape's first full capture pass
(704 tickers in that single pass; independently confirmed by a direct `captured_at` census
over `tape/orderbook_depth/dt=2026-07-07.jsonl`, which holds 29,155 records across 46
distinct instants and whose first two passes are `00:57:50.299698Z` with 6 tickers and
`01:23:57.700581Z` with 704).

Q49's verifier caveat #1 named only the primary cut. The entry rule that caused the pile-up
was shared by **every** cut, so the artifact was too: even the widest "445 candidates / 18
series" population is nearly half one snapshot of the market. A caveat gets written about
the number in the headline; the defect lives in the probe.

**Honest counterweight, recorded rather than omitted:** `unrestricted`'s 47.2% sits *below*
the descriptor's 0.5 flag and is reported as not-flagged. The flag is not a rubber stamp,
and a share alone does not settle whether a cluster is an artifact.

None of this changes Q49's verdict. The finding's own alternative-rule population
(the verifier's "first snapshot with ttc≤24h": 176 candidates / 17 series / 131 games) was
already DEAD, and the kill rested on the fee identity plus the strategy-level bootstrap, not
on the contaminated cuts.

## Provenance / tags

No price is asserted in this document. The frozen fixture stores **capture timestamps and
ticker-derived series labels only**; the underlying probe's prices are `real_bid` (entry) and
`broker_truth` (settlement), unchanged from Q49. Nothing here is a P&L number, so Hard Rule
#4 has nothing to tag.

## Why the exact numbers live in a fixture, not in a live-tree assertion

`tape/orderbook_depth/` grows every hour, so the Q49 populations move. Pinning these counts
against the live tree is exactly the failure L191/L192 record (a gate bound to a growing
population, or to a document the gate exists to change). The exact figures are therefore
frozen at `tests/fixtures/q49_entry_instants_2026-08-01.json` (measured at commit `ae1445c`,
2026-08-01T15:40Z, command recorded inside the file), and the ONE live-tape assertion is
deliberately **monotone**: the earliest `captured_at` in `dt=2026-07-07.jsonl` can only move
*earlier* if a future stranded-tape sweep union-appends older lines, so the test asserts
`<=`, never `==`.

## A hazard hit and reverted in this run (recorded in L251's own enforcement cell)

Drafting L251's new enforcement cell, the phrase "…should add `DISPOSES: L251` if it
concurs" **silently closed the row**: per L190 the disposition marker is parsed out of the
enforcement column, so a prose mention of it in that column is indistinguishable from an
actual disposition. The census went `30 disposed / 7 open` → `31 disposed / 6 open` with no
adjudication having occurred. Caught by re-running the census immediately after the edit,
reworded, and re-verified back to `30 / 7`. The lesson L190 already states ("a prose mention
of an ID NEVER suppresses") holds for the *lesson-text* column only — in the enforcement
column, prose and marker are the same bytes.

## Not verifier-adjudicated

No independent `verifier` could be dispatched in this run's context (the Task tool was not
available to the session). Per the two-agent verdict rule this run therefore produced **no
verdict-class output**: no registry flip, no bootstrap CI, no kill. The numbers above are
recorded as re-runnable measurements pinned by tests, and L251 is deliberately **left on the
open UNENFORCED queue** without a disposition marker so that a future verifier round adjudicates
it rather than the author adjudicating their own work.

## Gates

`python3 -m pytest -o addopts='' -q` and `python3 scripts/invariants.py --full` — see the
`kb/00-LOG.md` entry for this run for the counts, taken after the last code change (L162).
