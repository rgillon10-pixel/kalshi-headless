# 2026-07-20 — Q36 data-adequacy audit: `tape/weather_books/` gate opens under-powered

**Type:** data-quality characterization only. NO strategy claim, NO bootstrap CI, NO
registry change. Two-agent rule applied because this determines whether a queue gate is
trustworthy — two independent `verifier` passes (see below) re-derived every number from
raw committed JSONL and CONFIRMED all of them.

## Context

Q36 (`LOOP-QUEUE.md`) is GATED on `>=7` distinct days of `tape/weather_books/` coverage,
expected to open ~2026-07-22. Today's idle run (research-loop, policy-c data-quality
deep-dive) checked whether the gate opening on schedule will also mean the underlying data
is adequate to run Q36's two probe legs — same question the Q43 perp-gate density warning
already raised for a different family (L117-adjacent).

## Numbers (independently re-derived twice; both passes CONFIRMED)

- `tape/weather_books/` holds exactly **5** daily files as of this run:
  `dt=2026-07-16` (12,758 lines) / `-17` (13,722) / `-18` (6,508) / `-19` (2,940) /
  `-20` (2,748, partial day). Total **38,676** lines, 0 JSON-parse failures, 100%
  `price_source_tag=real_ask`. `du -sh tape/weather_books/` = **72M** — already over
  `tape/README.md`'s 50MB external-storage decision point, a separate flag for Ryan.
- **Pass-density collapse, same VPS-death root cause as L117/L118 but worse here.**
  Bucketing each day's distinct `capture_id` by `captured_at` minute-of-hour using
  `scripts/tape_gap_monitor.py`'s own `collector_bucket()` ranges (vps=20-29, cloud=50-59,
  else other): 07-16=28 passes (23 vps / 1 cloud / 4 other), 07-17=31 (24/1/6),
  07-18=14 (9/0/5), 07-19=**6 (0/0/6)**, 07-20=**6 (0/0/6)**. The VPS-bucket leg — which
  carried ~75-80% of weather_books' passes at peak — goes to exactly zero on 07-19/07-20,
  the same VPS `:23` cron death L117/L118 diagnosed for crypto/sports/perp tape. The
  surviving leg lands at minutes ~00-03 (cloud collector), which is why `tape_gap_monitor`'s
  current attribution logic reports this family as *ambiguous* (both named buckets read
  zero) rather than `vps_dead` — a real monitor blind-spot (see lesson L119 below).
  Net effect: **~28-31 passes/day collapsed to 6/day, an ~80% density loss**, worse than the
  ~50% "halving" seen in the hourly-cadence families L117 already covered, because
  weather_books' cloud leg was only ever a minority collector (~15-20% of passes) rather
  than a co-equal one.
- **KXTEMPNYCH-specific coverage (Q36's actual target series):** 880 records, 71 distinct
  market-hours (by `close_time`) across the 5 days. Captures per market-hour: median **1**,
  mean **1.2-1.3** (both independent measurements agree within rounding), max 3; 56/71
  market-hours captured exactly once. 832/880 records carry a populated `yes_bids`/`no_bids`
  ladder (depth>0); only 48 are empty top-of-book — so this is not a liquidity problem, it's
  a **sampling-rate** problem. A single snapshot per market-hour cannot support any
  intra-hour stale-pricing/convergence measurement (Q36 milestone part 2) by construction.
- **Settlement join (Q36 milestone part 1):** `tape/settlement_ledger/` holds only one
  day-file, `dt=2026-07-17.jsonl` (5,605 rows). Exactly 10 of those rows are KXTEMPNYCH, and
  all 10 are strikes of a single event, `KXTEMPNYCH-26JUL1707`. Running
  `scripts/q36_kxtempnych_settlement_basis_probe.py`'s own `load_settled_events`/`run`
  directly against committed tape reproduces this: `n_settled_events=1` against
  `MIN_EVENTS=10` — the script correctly and honestly reports `INSUFFICIENT DATA`, not a
  fabricated single-point mapping (confirms the gate logic on the live-reality side, same
  posture as the 2026-07-19 run's smoke test). The 10/10 strike-ticker join to
  `weather_books` is structurally clean (0 unmatched) — the join itself works; there simply
  isn't enough settled history yet, and `settlement_ledger` is not accumulating daily files
  for weather the way `weather_books` is, so more `weather_books` days alone does not fix
  this leg.
- **`tape/weather_actuals/` (the ASOS cross-check for the settlement-basis leg) has gone
  dark since 2026-07-18:** only `dt=2026-07-16` (2 lines), `-17` (40), `-18` (20) exist;
  `-19` and `-20` are both missing, consistent with the same collector outage.

## Verdict

The `>=7`-day calendar gate will open on schedule (~2026-07-22), but on a family whose
per-day pass density collapsed ~80% starting 07-19 due to the same dead VPS cron L117/L118
already diagnosed elsewhere, and whose target series (KXTEMPNYCH) is captured a median of
once per market-hour with only one settleable event-hour on record. **Both of Q36's probe
legs would be under-powered even after the calendar gate opens**, unless the VPS collector
is restored (Ryan/VPS-side, outside a cloud run's lane) before the gate fires:

- Part (1) settlement-basis: blocked on `n_settled_events=1 < MIN_EVENTS=10`, independent of
  the weather_books calendar gate — `settlement_ledger`'s weather coverage needs to grow,
  which the current wiring does slowly (only 1 event captured to date).
- Part (2) microstructure/stale-window: structurally unmeasurable at ~1.2-1.3
  captures/market-hour (max 3) — cannot observe intra-hour convergence from ~1 snapshot —
  and actively getting worse post-VPS-death (07-19/20/21/22 will all be cloud-only at ~6
  passes/day vs the ~28-31/day peak, so ≥3 of the eventual 7 gate-days are degraded).

No code change, no registry change, no P&L claim — `kb/strategies/00-index.md` untouched.
This closes an honest gap: nobody had checked whether Q36's gate opening would also mean
the data was adequate, the same question Q43's prep run already flagged for the perp family.

## Two-agent verification trail

Two independent `verifier` passes re-derived every number above directly from raw committed
tape (day counts, line counts, capture_id-based pass density, minute-of-hour bucketing,
KXTEMPNYCH coverage/depth histograms, and by directly executing
`scripts/q36_kxtempnych_settlement_basis_probe.py` against committed tape rather than
trusting a report). Both passes CONFIRMED every claim above exactly. One pass additionally
caught and corrected a units bug in a supplementary "book notional at touch" descriptor that
was NOT part of the load-bearing Q36-adequacy claims above (a draft metric divided by 100
twice, understating resting-book dollar depth ~100x); that metric is omitted from this
finding rather than corrected in place, since it was never part of the gate-adequacy
conclusion. See lesson L119 below for the reusable catch (book-notional units sanity check)
and L120 for the monitor blind-spot this audit surfaced.
