# The print-side anchor hole is a CADENCE hole, not a breadth hole — and `universe_sweep` is a rotating census, not a panel

**Date:** 2026-08-05 · **Author:** research loop, IDLE RUN, idle-run policy (c) (data-quality
deep-dive; main-context build — no `Task`/subagent tool is available in this environment, as
recorded on Q19/Q49/Q50 and all three prior Q51 milestones) · **Verdict class:**
**DATA-ADEQUACY** — no edge claim, no P&L, no bootstrap CI, no registry change. Two-agent rule
**N/A** (nothing verdict-class here) and not satisfiable; the headline numbers were instead
re-derived through a second, independently written code path before being recorded, which
L279 correctly warns is a weaker guarantee than a second agent (it cannot catch a shared
misreading of a field).

## Why this run existed

L280 (2026-08-04) measured the print-side dual of the Q51 join and got **10.1%**: of the
39,698 executed prints in the frozen `dt=2026-08-03` slice, only one in ten sits inside an
`orderbook_depth` interval we can price against. It named the defect BOOK-side. It left two
questions open, and the answers change what the repo should build next:

1. Is there a **breadth fix** already sitting in committed tape? `tape/universe_sweep/` is
   652 MB / 17 days of full-universe top-of-book *with* `yes_bid_size`/`yes_ask_size`. If it
   covers the tickers `orderbook_depth` misses, the hole closes for free.
2. How much of the 10.1% is the **criterion** rather than the tape? L280's rule is a BRACKET
   (>=2 snapshots, print inside `[first, last]`). A resting-maker fill-sim needs something
   strictly weaker: a PRIOR quote to rest against, then prints after it.

## Control

`scripts/q51_book_anchor_audit.py` reproduces L280's figure exactly before reporting anything
else — **0.101 vs published 0.101**, buckets partitioning the 39,698-print tape. Pinned by
`tests/test_q51_book_anchor_audit.py::test_acceptance_the_l280_control_reproduces_exactly`.
Had it not reproduced, the discrepancy would have been the finding.

## Finding 1 — `universe_sweep` cannot anchor anything, structurally

| measure | value |
|---|---|
| lines across all 17 committed days | 760,000 |
| distinct tickers | 723,235 |
| tickers observed **exactly once, ever** | 686,470 (**94.92%**) |
| max observations of any ticker, ever | **2** |
| captures at the 20,000-row cap | **38 / 38 (100%)** |
| `price_source_tag` census | `real_ask`: 760,000 (100% tagged) |
| **`is_panel`** | **False** |

Every capture is cap-bound (`MAX_CALLS=20 × PAGE_LIMIT=1000`), and the truncated slice
*rotates*: on `dt=2026-08-03` the two captures wrote 20,000 rows each and produced 40,000
**distinct** tickers — zero overlap. The consequence nobody had measured is not about the
pager: **a family whose modal market is seen once can never yield a price change, an interval,
or an anchor-then-print join.** 94.92% of the largest tape family in the repo is analytically
inert for any time-series question.

Concretely, against the print tape: `universe_sweep` covers **0 of 42** print tickers and
**0 of 39,698** prints, under every criterion, on the print day and its neighbours. The
breadth fix is dead — measured, not assumed.

This is a distinct fact from `findings/2026-08-03-universe-sweep-completeness-cap-saturation.md`,
which measured the same cap and correctly diagnosed its *operational* consequence (a
permanently-saturated `completeness_ok` wired into a high-priority pager). What that finding
did not ask is what the cap does to the **data**: it converts a "full-universe sweep" into a
rotating census.

## Finding 2 — relaxing the criterion buys coverage, not freshness

Print-weighted, over the same 39,698 prints (book side is live tape, so these are directional
bounds, not frozen equalities):

| anchor family | BRACKET (L280) | PRIOR (fill-sim's rule) | median anchor age | p90 |
|---|---|---|---|---|
| `orderbook_depth`, same day | **0.101** (control) | **0.9350** | 123.6 min | — |
| `orderbook_depth`, ±1 day | 0.1719 | **0.9985** | 128.6 min | 365.8 min |
| `universe_sweep`, ±1 day | 0.0000 | 0.0000 | — | — |
| union of both, ±1 day | 0.1719 | 0.9985 | 128.6 min | 365.8 min |

Read alone, "10.1% → 99.85%" would look like the hole was an artifact of a strict rule. It is
not. The freshness ladder under the *relaxed* criterion:

| anchor younger than | prints | fraction |
|---|---|---|
| 15 min | 791 | **1.99%** |
| 60 min | 3,281 | 8.26% |
| 180 min | 26,687 | 67.23% |
| 720 min | 39,637 | 99.85% |

So nearly every print has *some* prior quote and almost none has a *fresh* one. L280's
strict-criterion 15-minute figure was 0.46%; the weakest defensible criterion, using every
book family the repo owns plus adjacent days, moves that to 1.99%. **The two criteria agree
once you require a quote you would actually rest against.** The ~10x headline gap is a
criterion artifact; the ~2% fresh-anchor ceiling is the tape.

## Finding 3 — the constructive half: the fresh-anchored population clears the unit floor

Adequacy is decided by resample UNITS, not fractions. Units are GAMES (L6), derived via the
shared `game_of`, floor `MIN_UNITS = 10` (L41):

| anchor bound | prints | resample units (games) | clears floor |
|---|---|---|---|
| <= 15 min | 791 | **21** | yes (2.1x) |
| <= 60 min | 3,281 | **27** | yes |
| <= 180 min | 24,173 | **32** | yes |

All 21 units at the 15-minute bound are sports GAME markets (KXMLBGAME ×6, KXLEAGUESCUPGAME
×4, plus 11 single-game series). Prints per unit are heavily skewed (328 / 157 / 102 / 56 /
47 / 36 / 15 / 14 / 10 / 4 / 4 / 3 / …), so 21 is a unit count, not an effective sample size.

Note what does **not** move these rows: same-day, ±1 day and the union of both give the
*identical* 791 prints / 21 units. Adding a day of tape and 652 MB of sweep contributes zero
fresh anchors. **Only cadence moves this number.**

## What this means for the program (stated as an upper bound, not a verdict)

Q51 milestone 2's sports maker re-test returned **DATA-INADEQUATE at n=7 units**
(`findings/2026-08-04-q51-maker-fillsim-milestone2.md`, PROVISIONAL). This run measures an
**upper bound of 21 fresh-anchored sports-game units on the same single committed day** —
2.1x the L41 floor and 3x what milestone 2 realised. A fresh anchor is *necessary but not
sufficient* for milestone 2's population (it also needs settlement and its rest-window logic),
so this does **not** refute the n=7 result and flips nothing. What it does say is that
milestone 2's shortfall is more likely a property of its **sampling rule** (stride-13 over the
first 200 depth tickers, 3h/9h rest windows) than of the tape, and that is a cheap, read-only
thing to check on already-committed tape — i.e. **before** the 2026-08-10 time gate, not after.

The other implication is negative and firm: the binding constraint on the whole WALL-B
fill-sim program is `orderbook_depth`'s **revisit interval**. It is not coverage
(`orderbook_depth` already holds 42/42 print tickers and 39,698/39,698 prints), not breadth
(`universe_sweep` contributes zero and structurally always will), and not history (±1 day adds
nothing fresh). The only lever that moves it is more frequent looks at markets already being
captured — which is precisely what Q47's `orderbook_delta` WS daemon delivers, and Q47 remains
BUILD DONE / ACTIVATION PENDING, Ryan-gated on a working key. This run puts a print-weighted
number behind that gate: at present cadence, 98.01% of executed volume cannot be priced
against a quote younger than 15 minutes.

## Limits, honestly

* One print day (`dt=2026-08-03`). It is frozen and `trade_id`-deduped, so the print side
  cannot drift; the book side can, hence directional bounds on every book-derived assertion.
* `universe_sweep`'s panel profile covers 17 committed days; the two days with internal
  repeats (`dt=2026-07-22`, `dt=2026-08-01`) are included and are why `max_observations_per_ticker`
  is 2 rather than 1.
* "Fresh anchor" is a necessary condition for a priceable fill, never a sufficient one. No
  fill, no fill rate and no P&L is claimed anywhere in this run.
* No independent `verifier` agent was dispatchable; the numbers were re-derived through a
  separate implementation, which per L279 does not protect against a shared misreading.

## Reproduce

```
python3 scripts/q51_book_anchor_audit.py      # ~10 s, offline -> reports/q51_book_anchor_audit.json
python3 -m pytest tests/test_q51_book_anchor_audit.py -q    # 27 tests
```
