# Phase-1 trade-print backfill: the S79 data gate is OPEN (24 units, floor 10)

*2026-08-08 · research loop · milestone = the bounded phase-1 backfill that
`findings/2026-08-08-kalshi-trades-backfill-gate-not-calendar-gate.md` (L313) proposed and
deliberately did NOT execute · main-context build, no `Task`/subagent tool exists in this
harness (the L287/L288/L290/L291/L295/L308/L313 precedent)*

**Class: DATA-COLLECTION + DATA-ADEQUACY.** No bootstrap, no CI, no P&L, no fill rate, no
edge claim, no registry flip. S78 and S79 keep the status they had. Still 0 proven edges.
What changed is that the data their gate was waiting on now exists in committed tape.

---

## The question

L313 measured that the S78/Q52 and S79/Q54 gates are un-run backfills, not calendar waits,
and ended with a bounded proposal: pull only settled sports tickers, scoped to their own
eligible days, starting in the 07-07..07-14 window, under a declared 25-50MB cap.

> Falsifiable question: does a bounded, byte-capped pull of ALREADY-IDENTIFIED tickers move
> S79's pre-registered adequacy gate from shut to open — measured by the sealed probe's own
> outcome-blind adequacy path, not by a new hand-rolled count?

Binding test: `population_report()` in `scripts/q54_s79_flow_continuation_probe.py` must
return `admissible: true` — i.e. `n_units >= 10` (L41) **and** `minority_side_units >= 2`
(the L312 sign-variation gate) — with no outcome value ever entering scope.

## What was pulled

`scripts/q52_q54_trades_backfill_phase1.py` (new, + 20 offline tests). Selection is computed
from committed tape only; the pull itself goes through `collection.kalshi_trades.run` (its own
`trade_id` dedupe, its own append-only writer, its own honest `completeness_ok`).

| stage | count |
|---|---|
| sports-game tickers with >=2 `orderbook_depth` snapshots on a day in 07-07..07-14 | 1,240 |
| … resolved to a binary outcome by the nine declared settlement families (`broker_truth`) | 601 |
| … as (day, ticker) pull units | 1,430 |
| … rolled up to GAMES (S79's resample unit, L6) | 328 |
| **games actually pulled before the declared byte cap fired** | **17** |

Result: **89,217 new executed prints**, 24 tickers, 17 games, 5 new day-files
(`dt=2026-07-07/08/10/11/12`), **51.37 MB**, `price_source_tag: broker_truth` on 128,915 of
128,915 lines across the family. 0 duplicate `trade_id`s appended (the collector's dedupe
made the repair pass below a no-op on everything it had already held).

## The selection rule — pre-registered by being committed BEFORE the probe runs

This matters more than the byte count, so it is stated first-class rather than in a footnote:
**the backfill's selection rule is now part of S79's sampling frame.** It is outcome-blind
(no settlement *result* was read at any point — only the boolean "does a declared family
resolve this ticker"), but it is not random:

1. games ordered by **round-robin over series (league)**, sorted within each league — a plain
   `sorted()` prefix would have been one league's alphabet, and a byte-capped prefix of that
   is a single-competition sample masquerading as a cross-sport one. The realized 17 games are
   17 DIFFERENT leagues (MLB, WC, UECL, UCL, NPB, KBO, NWSL, USL, USL Cup, K-League,
   Eliteserien, Allsvenskan, Brasileiro B/C, China SL, Uruguay PD, Ecuador LP);
2. **whole games only** — a game is either fully pulled or not started, because a half-pulled
   game is a silently biased unit;
3. stop at a **declared 40MB cap**, enforced on measured on-disk bytes, checked before each
   game. It fired at game 18 with 43.9MB realized — the 3.9MB overshoot is whole-game
   atomicity on one heavy game, reported rather than hidden
   (`reports/q52_q54_trades_backfill_phase1_selection.json`).

Consequence to carry into any S79 CI: this sample is skewed toward the alphabetically-first
game of each league in the earliest days of the window, and toward games heavy enough to
survive whole-game atomicity. It is a convenience sample of a known shape, not a draw.

## The truncation the first pass found (why the cap moved 20 -> 60)

The first pass ran with `max_calls=20` per query. `KXMLBGAME-26JUL061915NYMATL` hit it on both
outcome tickers: 20,000 prints each, cursor still active, `completeness_ok=False`. Measured
true depth: **25,405 and 27,532 prints** (26 and 28 calls). So the tape held a 40,000-print
PREFIX of a 52,937-print ticker-day.

That is worse than missing data for this strategy. A `kalshi_trades` line carries no
partial-coverage marker — the truncation lives only in the pass summary, which is not tape.
A signed-flow signal joining that ticker would read a prefix of the day as the day, and the
prefix is time-ordered, so the distortion is systematic rather than noisy. The cap is now 60
(~2x the measured worst case) and a repair pass completed the game (+12,937 lines, +7.46MB,
`reports/q52_q54_trades_backfill_phase1_repair.json`, **0 games with an incomplete query**).
Total realized growth 51.37MB, inside the finding's proposed 25-50MB band only if you count
the selection pass; stated honestly, it is 51.37MB = 43.9 (selection, cap 40) + 7.5 (repair).

## A second defect the pull exposed: windows frozen on one end only (L316)

Two committed acceptance pins went red on tape that was added correctly:
`tests/test_kalshi_trades_ticker_inventory.py::test_acceptance_real_tape_reproduces_l292s_published_inventory`
and `::test_cli_runs_offline_and_emits_stable_json`. Both froze their window with
`max_day="2026-08-03"` per L140's time-bomb discipline — airtight for a family that only
accretes NEWER days. This family has no scheduled writer, so it grows by BACKFILL: every one
of `dt=2026-07-07` … `dt=2026-07-12` is OLDER than the frozen `max_day` and walked straight
into a window that had been closed on purpose. The assertions were right; the window was
wrong. Repaired by adding a symmetric `min_day` to `_family_files` / `trade_tape_inventory` /
the CLI and re-freezing the L292 pins at `min_day == max_day == M1_DAY` — **the pinned numbers
are unchanged**, only the window is now closed on both sides, plus a positive-control test
that asserts the older day leaks in WITHOUT `min_day`.

## Result — the gate is open, measured outcome-blind

Run through the sealed probe's own adequacy half (`load_all_prints` -> `eligible_tickers` ->
`settled_ticker_set` -> `entry_candidates` -> `population_report`). `outcome_map()` and
`score_rows()` were **not called**; the seal (L311) is intact and the probe file is unmodified.

| quantity | before (2026-08-08, 1 trade day) | after this backfill | floor |
|---|---|---|---|
| trade days | 1 | 6 | — |
| sports `*GAME` tickers with prints | 38 | 62 | — |
| entry candidates | 82 | 148 | — |
| … on a settled market | 67 | 133 | — |
| **bootstrap units (games)** | **8** | **24** | 10 (L41) |
| **minority-side units** | **0** | **2** | 2 (L312) |
| `gate_reasons` | `[below_min_units, no_sign_variation]` | `[]` | — |
| `admissible` | false | **true** | — |

Both halves of Q54's gate are open for the first time since S79 was registered.

## Honest limits

1. **The minority arm clears by exactly zero margin** (2 vs a floor of 2). One unit
   reclassifying shuts the gate again. The side split is 131 YES / 2 NO entries — the L279
   80/20 buy-skew is still the dominant fact about this tape, and a CI computed here will be
   overwhelmingly a statement about the majority side. S79's own BINDING MANDATE (benchmark
   decomposition against an always-majority-side arm, paired per-unit difference CI) is not
   optional at this margin; it is the whole test.
2. **No probe was run.** This milestone deliberately stops at "the gate is open". Running the
   sealed probe is verdict-class and needs the two-agent rule, which is unsatisfiable in this
   harness — the next run (or an interactive session with a dispatchable `verifier`) should do
   it, against the sampling frame committed here.
3. **Day-files are NOT complete venue days.** They are a ticker-scoped backfill of the 17
   listed games. The coverage manifest in the report names every (game, day, ticker, min_ts,
   max_ts) attempted; join against it, never against a whole `dt=` file assumed complete.
4. **Book cadence still binds S78.** 4 `orderbook_depth` captures/day, median inter-snapshot
   interval 180.3 min (Q51-m1): more prints do not repair queue position or sub-3h adverse
   selection (L283). This backfill helps the taker-side question (S79) far more than the
   maker-side one (S78).
5. **311 of the 328 identified games are still un-pulled**, and 07-13/07-14 got no coverage at
   all — the cap stopped inside 07-07..07-12. Phase 2 is a bigger byte decision, not a new
   discovery.
6. **`count` is far more often fractional on this population than on the day the S79 gate was
   designed against.** The field is the venue's own `count_fp`, stored verbatim (L47 — a
   fractional count is valid venue data and must not be int-coerced). Measured over the first
   500 lines of each day: **34.0% non-integer on `dt=2026-08-03`, 79.6% on `dt=2026-07-07`.**
   S79's `|net flow| >= 10` threshold was pre-registered against the 08-03 shape, so its
   effective selectivity on the backfilled sports population is not identical to what the seal
   was written against. Nothing here changes the spec — flagged so the probe run reads its own
   threshold with eyes open rather than discovering this after the CI.
7. **Redundancy, not verification.** The population funnel (601/328/1430) was reproduced by an
   independent ad-hoc computation before the driver existed, and the driver's own dry run
   agrees; the adequacy numbers come from the sealed probe's code, not from this run's. No
   independent `verifier` agent could be dispatched, so everything here is PROVISIONAL and
   flips nothing.

## Reproduce

```
python3 scripts/q52_q54_trades_backfill_phase1.py --dry-run --json -     # offline plan
python3 scripts/q52_q54_trades_backfill_phase1.py --cap-mb 40            # the pull (idempotent)
#   -> reports/q52_q54_trades_backfill_phase1_selection.json ; the L314 repair pass was
#      `--cap-mb 60 --max-games 17 --json reports/q52_q54_trades_backfill_phase1_repair.json`
python3 -m pytest tests/test_q52_q54_trades_backfill_phase1.py -q
python3 scripts/q54_s79_flow_continuation_probe.py                       # adequacy + (now) scoring
```
