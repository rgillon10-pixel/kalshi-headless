# Q52 / S78 train/holdout split feasibility — Q52's stated blocker holds, and two real bugs got caught on the way

2026-08-13 · research loop, idle-run policy (c), main context (offline, read-only) + `research-lead`
(idea/scoping) + two `verifier` rounds. No strategy claim, no P&L, no fee model, no bootstrap CI, no
registry change — two-agent rule does not strictly bind this class of output (data-quality /
feasibility characterization, not a verdict; same posture as the Q44/Q54 status-update precedent),
but a `verifier` pass was run anyway, twice, because the first draft's *interpretation* (not its
arithmetic) turned out to be wrong.

## Why this milestone, why now

Full Q0–Q56 rescan (file-shape, current status line per item) found 0 eligible TODO/IN-PROGRESS
items — the 10th+ consecutive idle-adjacent run per `kb/00-LOG.md`'s own running count, independently
re-confirmed by `kalshi-edge-hunter`'s round #29 the same day. Idle-run policy (a) (convert an
UNENFORCED lesson) was re-verified empty — all 9 open rows are Ryan/VPS-gated or not statically
assertable, cross-checked against the actual tree rather than trusted from a prior run's summary.
Policy (b) (prep the next time-gated queue item) surfaced a real, unprepped target — **Q52/S78 has no
probe script at all**, unlike every other gated item — but building the full sealed pre-registered
probe (mirroring the Q54/S79 architecture) needs the `Task` subagent tool for a `verifier` dispatch
mid-build, which was unavailable to the `research-lead` seat that scoped it. Falling back to policy
(c): before that probe can be *written*, someone has to establish whether a chronological train/
holdout split of the S78 population is even *feasible* — nobody had measured it.

## What was measured

`scripts/q52_s78_split_feasibility_audit.py` (read-only, offline, +26 tests in
`tests/test_q52_s78_split_feasibility_audit.py`): for every `tape/kalshi_trades/dt=*.jsonl` day, take
distinct sports-`GAME`-series tickers (excludes `KXMVE*`, L31) with ≥2 same-day `orderbook_depth`
snapshots and a binary settlement result (via `core.settlement_sources.resolve_market_results` — the
one sanctioned resolver, never a single family, L300). Report every chronological split's unit counts,
series overlap between train/holdout, book-capture cadence, and per-ticker snapshot-gap distribution.
Settlement is used **only as a label class** (does this game have a result at all), never by
direction — the same outcome-blind discipline the S78/S79 sealed probes hold, since any markout or
fill number belongs to S78's own future probe, not to a feasibility audit that runs before it.

## The corrected headline

**A chronological split at the natural 3-week gap (train = 2026-07-07/08/10/11/12, holdout =
2026-08-03) gives 34 train units / 29 holdout units / 0 overlap.** Read undivided, that clears the
repo's L41 n≥10 floor with room to spare. **But Q52's own status line qualifies its claim with "≤4
cells"** — and at 4 cells, 34/4 ≈ 8.5 train and 29/4 ≈ 7.25 holdout units per cell, both below the L41
floor. **Q52's stated blocker holds once its own qualifier is honored — this audit does not overturn
it.** (The first draft of this script dropped that qualifier and claimed to falsify Q52; an adversarial
`verifier` pass caught it before it was committed — see "How this got here" below.)

Two structural walls sit underneath that arithmetic, independent of the exact split point:

1. **Series non-transfer.** Only 4 of 18 train-window series and 4 of 14 holdout-window series
   overlap (`KXMLBGAME`, `KXNPBGAME`, `KXUCLGAME`, `KXUSLGAME`), covering 8 of 34 train units and 10
   of 29 holdout units. A series-keyed toxicity cell would be largely untestable out-of-sample; any
   future S78 cell design should be series-agnostic.
2. **A real book-cadence step, but the July trade-day comparison is contaminated by a selection
   artifact.** `orderbook_depth`'s own capture-instant count (over the WHOLE day file, unaffected by
   the trade-tape selection below) steps from **25 distinct capture instants on 2026-07-22 to 3 on
   2026-07-23** — a real, sharp collapse, consistent with the already-documented VPS-collector-death
   lesson chain (L117/L127/L177/L213/L304), not a new discovery. But the pre-boundary days are not
   uniformly dense either (07-19 = 6, 07-20 = 7) — "tens vs ones" overstates it; what's load-bearing
   is the step itself, not a clean two-level contrast.

## The caveat this audit exists to surface: the July trade tape is not a clean day-sample

`tape/kalshi_trades/dt=2026-07-*.jsonl` are **a ticker-scoped BACKFILL of one specific 34-game list**
(`reports/q52_q54_trades_backfill_phase1_phase2.json::execution.coverage_is_ticker_scoped = true`,
its own `coverage_note`: *"day-files are a ticker-scoped backfill of the listed games only, NOT
complete venue days; join against `manifest`, never against a whole dt= file assumed complete"*), while
`2026-08-03` is a genuinely complete, live `public_markets_trades` sweep. The 34 July-side settled
units in this audit are **exactly** the manifest's 34 backfilled games — set-identical, verified by
the round-2 verifier independently. So the July-side unit and series counts reflect which games the
backfill's round-robin selection and 50MB byte cap happened to reach, not a random sample of what
traded those days. The script surfaces this structurally (`backfill_scope_caveat`, read live from the
manifest, never asserted in prose) rather than hiding it in a docstring a future reader might skip.

**What survives this caveat:** the `orderbook_depth` cadence numbers, because that collector runs
independently of the trade backfill and the script counts every row in the day file, not just rows
for backfilled tickers.

## How this got here — an honest two-round verifier trail

**Round 1: REFUTED.** Every raw count in the first draft reproduced independently to the digit (a
from-scratch re-implementation using regex JSONL scanning and a direct settlement read, bypassing
`core.settlement_sources` entirely, gave 34/29/0, the same 4 shared series, the same cadence numbers,
the same gap percentiles to 4 decimals) — but the *interpretation* was wrong on four counts: (1) it
dropped Q52's own "≤4-cell" qualifier and called a true statement false; (2) it asserted the
starved-era gap distribution was "cleanly unimodal" from 4 percentiles alone, when a histogram shows
it's actually multi-modal (clusters near ~180/360/540/900 minutes); (3) `resolve_market_results`'s
default `root="tape"` is **relative** — the script anchored every other path via an absolute `REPO`
constant but left this one relative, so running it from any other working directory silently returned
"0 resolved" / n_train=0 / n_holdout=0 at exit code 0, no warning, the opposite headline; (4) it never
surfaced the backfill-scope caveat above.

**Fixes applied:** added `per_cell_split` (reports both the undivided split and Q52's own ≤4-cell
arithmetic, and the module `purpose` string now explicitly disclaims falsifying Q52); replaced the
unimodality claim with a `gap_histogram_30min_bins` field, computed rather than asserted; changed the
default settlement root to an absolute `os.path.join(REPO, "tape")`; added `backfill_scope_caveat`,
read live from the manifest.

**Round 2: CONFIRMED-WITH-CORRECTIONS.** All four round-1 breaks verified genuinely closed (including
a live `cd /tmp && python3 .../q52_s78_split_feasibility_audit.py` byte-identical to the repo-root run
— the exact regression Break 3 was about). Two new prose-accuracy defects were found: (NEW-1) the
corrected docstring said "see `book_cadence_by_era` in the output" for the era-boundary step, but that
block is keyed by trade day and has a 3-week hole straddling the boundary itself — it could not show
what was claimed, recreating round 1's own failure mode one layer up; (NEW-2) "tens of captures/day
pre-07-23 vs single digits after" is contradicted by the script's own data (2026-07-10 = 9, a single
digit, pre-boundary). Plus three minor nits: the histogram's overflow bin was labeled with a
misleading finite upper edge (`"[960,990)"` for a 5000-minute gap); `main()`'s
`json.dumps(sort_keys=True)` was silently re-sorting the histogram's dict keys lexicographically,
discarding the numeric order the function built; and a stray unused `best_split` computation plus a
wrong return-type annotation.

**Fixes applied:** added `depth_capture_id_counts_around_boundary()` / `era_boundary_evidence`, which
scans every `orderbook_depth` day file near the boundary regardless of whether it had a trade — the
docstring's boundary claim is now checkable against a real emitted field (25 → 3 on 07-22 → 07-23,
confirmed above); corrected the "tens vs single digits" line to state the actual, less clean pattern;
changed `gap_histogram_30min_bins` to return an ordered list of `[bin, count]` pairs (survives
`sort_keys`) with an explicit `"[960,+inf)"` overflow label; removed the dead code; fixed the type
annotation. 26/26 tests green after both correction passes.

## Lesson candidates (for kb-distiller / the lessons ledger)

- **L345** — `core.settlement_sources.resolve_market_results` defaults `root="tape"` (a **relative**
  path). Any script that anchors its other paths via an absolute repo-root constant but leaves this
  one on the default silently returns a **0-resolved report at exit code 0** from any other working
  directory — indistinguishable from a genuine data gate, with no error. Any caller mixing absolute
  and default-relative paths should pass an absolute `root=` explicitly; a repo-wide grep for
  `resolve_market_results(` call sites without an explicit `root=` is a candidate invariant.
- **L346** — A finding that corrects a prior claim must quote that claim's own qualifiers before
  contradicting it (here: dropping Q52's "≤4-cell" qualifier turned a true statement into a false
  one) — and a docstring citation of "see X in the output" is itself a checkable claim: grep the
  named field for the evidence before shipping, or the citation recreates the same failure the
  correction was written to fix, one layer up.

## Reproduce

```
python3 scripts/q52_s78_split_feasibility_audit.py
python3 -m pytest -q tests/test_q52_s78_split_feasibility_audit.py
```

Gates: see the Log-of-runs line for the fresh post-commit `pytest` / `invariants --full` counts (L162).
