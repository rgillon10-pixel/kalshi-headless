# L208 → enforced: expected-window-grid coverage, and a correction to its own worked example

`2026-07-30` · research loop, **IDLE RUN**, idle-run policy (a) (convert an UNENFORCED lesson
into an invariant/test) · read-only over committed tape, no network, no strategy claim, no
registry change, no P&L, no bootstrap CI.

## Why this run is an idle run

Full FILE-SHAPE rescan of Q0–Q48 (per L25 — each item's real current state verified, not its
prose): **0 eligible TODO/IN-PROGRESS items**, the same verdict the two prior runs today
(PRs #238, #240) reached independently. Re-verified live rather than trusted, on the three
items whose gates are the closest to opening:

| item | gate | live re-check this run | verdict |
|---|---|---|---|
| Q43 | `perp_tape` capture density ≥10/day | `python3 scripts/q43_perp_binary_consistency_probe.py` → 14 forward days, **11 of 14 below the 10-capture/day advisory floor** (07-29 = 1, 07-30 = 2) | still density-gated, and no better than the 07-25 reading |
| Q36 | ≥10 settled `KXTEMPNYCH` events | `python3 scripts/q36_kxtempnych_settlement_basis_probe.py` → `{"status":"INSUFFICIENT DATA","n_settled_events":2,"min_events":10}` | still frozen at n=2 (VPS-side, Ryan) |
| Q37 | ≥21 `weather_books` contract-days from 2026-06-21 | 14 day-files present | gate opens ~2026-08-05 |

Everything else is DONE / DEAD / credential-BLOCKED (Q1-odds, Q32, Q33, Q35-build, Q47) /
burst-gated (Q19, Q48) / policy-blocked (Q14, Q15, Q17). So: idle run, policy (a).

`kb/lessons/00-lessons.md` had **8** genuinely-open `UNENFORCED` rows. Of those, L145/L213 are
policy calls reserved for Ryan, L214/L221/L222 require changing live collector write paths (a
collector change, not an enforcement), and L236's own cell says its fix lives outside that
lane. **L208** is the one whose named candidate is buildable, generic, and read-only. It is
also the one already misleading a live analysis.

## What L208 says, and what was built

> *A per-window density statistic computed only over windows that produced ≥1 observation is a
> survivorship statistic, not a coverage statistic.* … *The honest denominator for any
> window-bucketed tape metric is the expected window grid (derived from the collector's own
> cadence), never the observed-windows set.*
> Candidate: *a generic "expected window grid vs observed window grid" gap check … keyed to a
> collector's own cadence instead of a fixed interval.*

Built verbatim:

* **`scripts/tape_gap_monitor.py::expected_window_grid_coverage(tape_root, family, days=None)`**
  plus the `WINDOW_GRIDDED_FAMILIES` spec table (one entry today: `perp_tape` →
  `next_funding_time`, 8h, anchor 04Z, thin ≤1 pass). It enumerates the full expected grid
  between the family's first and last observed boundary and reports, side by side, the
  **observed-only** and the **grid-filled** pass-count summaries, `n_windows_zero_capture` +
  the zero windows themselves, `n_windows_thin` (which INCLUDES the zero windows — a zero
  window is the extreme thin window), `path_inadequate_fraction`, `coverage_fraction`, and
  `survivorship_gap_median`.
* CLI: `python3 scripts/tape_gap_monitor.py --window-grid [--window-grid-days dt=…,dt=…]`.
* **`scripts/invariants.py::window_grid_coverage_warning` / `_window_grid_coverage_issues`**,
  wired into `main()`'s `--full` advisory path — **stderr only, `except BaseException`, never
  flips the exit code**. Non-gating deliberately: a missed funding window is permanently
  unrecoverable (the collector destroys the premium path at each boundary and never re-fetches),
  so gating would halt the loop forever over an unfixable past. Same posture as the
  hollow-ladder / capped-pagination / colliding-`capture_id` advisories.
* **22 new tests** — 12 in `tests/test_tape_gap_monitor.py` (incl. one HARD real-tape acceptance
  test on a **frozen** `dt=2026-07-17..27` slice, per L191 — `tape/perp_tape/` is live and
  growing, and an open-ended `dt=*` pin is exactly what red-lined the gate on 2026-07-27),
  10 `*_L208` tests in `tests/test_invariants.py`.

Refusals encoded (house style: report, never guess): an unregistered family returns `None`; a
row with an absent/unparseable boundary is skipped **and counted**, never bucketed into a
neighbour; a family with zero on-grid boundaries reports `reason="no_on_grid_window_keys"`
rather than inventing a span; a boundary **off** the configured grid is counted in
`n_offgrid_window_keys` with examples and **never snapped**.

Density unit is the distinct capture **pass** (`capture_id`) — that is what "a window with zero
capture passes" means. Known blind spot, stated rather than papered over: `capture_id` is a
second-granularity label, so an L210-class collision counts two invocations as one pass. That
biases this detector's density **low**, i.e. toward flagging — never toward a false all-clear.

## The correction (the load-bearing finding)

Building the check re-derived its own worked example, and the example does not survive.

`findings/2026-07-27-perp-tape-audit.md` **PERP-F1** reports:

> Of 33 8-hour funding windows spanning 07-17T00Z→07-27, **4 have zero capture passes**
> (`2026-07-23T08Z`, `07-24T08Z`, `07-25T08Z`, `07-25T16Z`) and 8 more have exactly 1 sample —
> 12/33 (36%) path-inadequate.

Those four instants are on a **00Z-anchored** 8h grid. Kalshi perps' funding boundaries are not.
Read off the collector's own `next_funding_time` field, **1,534 of 1,534** committed
`funding_estimate` rows in `tape/perp_tape/` sit on the **04/12/20Z** grid and **zero** on
00/08/16 (`n_offgrid_window_keys = 0` against anchor 04). PERP-F1's grid was therefore built by
binning `captured_at` into wall-clock calendar bins, not by reading the venue's own boundary.

Both readings were reproduced independently this run — first by a from-scratch scratch script,
then by the shipped detector — over the same committed tape:

| reading | span | expected | zero-pass windows | ≤1 pass |
|---|---|---|---|---|
| PERP-F1: `captured_at` in 00Z-anchored 8h bins | 07-17T00Z→07-27T16Z | 33 | **4** — `07-23T08Z`, `07-24T08Z`, `07-25T08Z`, `07-25T16Z` | 11 |
| this run: `next_funding_time` on the 04/12/20Z grid | 07-17T04Z→07-27T20Z | 33 | **3** — `07-24T04Z`, `07-25T04Z`, `07-25T20Z` | 10 (30.3%) |

(Span note: the day-file slice `dt=2026-07-17..27` enumerates **34** windows because a 07-27 capture
already points at the `07-28T04Z` boundary; that 34th window is observed, so restricting to the
audit's own `…→07-27T20Z` span gives 33 windows and the same 3 zeros. The frozen-slice acceptance
test pins the 34-window day-slice form.)

The two zero-window sets are **disjoint**: not one named instant is common to both. PERP-F1's
four bins are not funding windows at all, so its claim that *those four* funding windows are
permanently unrecoverable is wrong on the instants — while its *thesis* (real windows were lost,
and the observed-only statistic cannot see them) is confirmed, just at a different three.
`12/33 = 36%` re-derives as `10/33 = 30.3%`.

On the **full** committed tape (07-17T04Z → 07-30T12Z, live, will move): 41 expected windows,
36 observed, **5** zero-pass (`07-24T04Z`, `07-25T04Z`, `07-25T20Z`, `07-29T20Z`, `07-30T04Z`),
15 at ≤1 pass = 36.6% path-inadequate, coverage 87.8%.

Honest note on the survivorship number itself: on this tape the **median** passes/window is 2 in
both views (`survivorship_gap_median = 0.0`) — the median is robust to five holes out of 41. The
survivorship distortion shows up in the parts a median cannot see: `observed_only.min_passes = 1`
vs `grid_filled.min_passes = 0`, and in the coverage/path-inadequacy fractions that do not exist
at all in an observed-windows-only view. Claiming a moved median here would have been an
overstatement; the reported gap field is 0.0 and is left that way.

## Consequences

* `scripts/q42_funding_estimate_path_inference.py`'s `min/median/max_samples_per_window` remains
  a survivorship statistic. **Deliberately not modified** — L191 froze that probe's tape slice
  for a reason, and Q42's own verdict (H1 UNDECIDABLE) is unchanged and untouched by this run.
  The coverage number now lives next to it, computable on demand.
* No registry status moved. No strategy claim. No CI. Q42's and Q43's verdicts are unchanged.
* `findings/2026-07-27-perp-tape-audit.md` is **annotated, not rewritten** (append-only).

## Two-agent rule

**Not applicable to the milestone class** (idle-run policy (a): infra/enforcement build — no
registry flip, no bootstrap CI, no kill decision). The numeric correction to PERP-F1 is
nonetheless verdict-adjacent, and no `verifier` subagent was dispatchable in this run's harness,
so it is recorded **PROVISIONAL**: adversarially re-derived twice within one session (an
independent scratch script that reproduced *both* readings, then the shipped detector), pinned by
a test that asserts the two window sets are disjoint, and explicitly **not** used to rewrite
PERP-F1 or to move any status. A second agent should confirm before the correction is treated as
settled.

## Reproduce

```
python3 scripts/tape_gap_monitor.py --window-grid
python3 scripts/tape_gap_monitor.py --window-grid --window-grid-days \
  "dt=2026-07-17,dt=2026-07-18,dt=2026-07-19,dt=2026-07-20,dt=2026-07-21,dt=2026-07-22,\
dt=2026-07-23,dt=2026-07-24,dt=2026-07-25,dt=2026-07-26,dt=2026-07-27"
python3 -m pytest -o addopts='' -q tests/test_tape_gap_monitor.py
python3 -m pytest -o addopts='' -q tests/test_invariants.py -k L208
python3 scripts/invariants.py --full
```

Lessons: **L208** enforcement cell moved `UNENFORCED` → `test + non-gating advisory` (lesson text
unchanged, per the L152 own-row-update rule); new **L238** (width AND anchor — a mis-anchored
window grid is a confident wrong answer the width alone cannot expose).
