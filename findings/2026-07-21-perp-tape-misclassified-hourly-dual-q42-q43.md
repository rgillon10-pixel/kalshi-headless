# perp_tape misclassified as one-shot-backfill in tape_gap_monitor (L127)

**Date:** 2026-07-21 (idle-run, policy c: data-quality deep-dive → immediate fix)
**Status:** data-quality / monitoring finding, NOT a strategy verdict. No registry change.
Two-agent verdict rule N/A (monitoring-only reclassification, same posture as L118/L121/
L122/L124/L126).

## What was checked

`tape/perp_tape/` (Kalshi CFTC-regulated crypto perps, built 2026-07-16 for Q42/Q43) and its
only cross-venue join partner `tape/hyperliquid_funding/`, audited by a `tape-auditor`
subagent for coverage, cadence, and join-ability — a family not covered by today's three
earlier idle-run/edge-hunter passes (`settlement_ledger`, `universe_sweep`,
VPS-collector-day-3, `weather_actuals`).

## Finding 1 — perp_tape genuinely hourly, misfiled as one-shot (FIXED this run)

`scripts/tape_gap_monitor.py::FAMILY_CONFIG` classified `perp_tape` as
`{"interval_h": None, "passes_per_day": None, "kind": "one-shot-backfill"}` since its build.
But `collection/hourly_pass.py` runs `collection.perp_tape`'s pass on **every**
`hourly_pass()` invocation, unconditionally — identical cadence to the already-tracked
`sports_pairs`/`crypto_hourly`/`orderbook_depth`/`weather_books`/`polymarket_pairs`/
`polymarket_macro_pairs` (`hourly-dual`, 48/day). Because an `interval_h=None` family never
runs the UNDER-CAPTURE ratio check, `perp_tape`'s real post-L117-VPS-death collapse was
structurally invisible:

| date | distinct captures |
|---|---|
| 07-17 | 30 |
| 07-18 | 14 |
| 07-19 | 6 |
| 07-20 | 7 |
| 07-21 (partial, through hr 13) | 5 |

~29% of nominal cadence on the two full post-outage days — the same L117 VPS-cron death
already diagnosed for 5 other families (Q44), `perp_tape` is simply a 6th victim that was
never on the list because it was never a tracked cadence family in the first place.

**Fix:** reclassified `perp_tape` to `{"interval_h": 1.0, "passes_per_day": 48, "kind":
"hourly-dual"}`. Its surviving collector's captures land at minute-of-hour ~00-04 — neither
the `vps` (:20-29) nor `cloud` (:50-59) bucket, the same "other" signature L120 found for
`weather_books`' secondary leg — so `perp_tape` was also added to `EXPECTED_COLLECTOR_BUCKETS`
as `{"primary": "vps", "secondary": "other"}`, giving an unambiguous `vps_dead` diagnosis
instead of the ambiguous `vps=0 & cloud=0` an unmapped family would report.

**Verified against real committed tape** (`tests/test_tape_gap_monitor.py::
test_acceptance_7_l127_perp_tape_reclassified_hourly_dual`, `now=2026-07-21T18:00Z`):
`alert=True`, capture ratio 0.146 (< 0.8 floor), `collector_diagnosis="vps_dead: 0 passes in
window, other collector still producing"`.

## Finding 2 — hyperliquid_funding join-partner staleness (NOT fixed, flagged)

`tape/hyperliquid_funding/` is `perp_tape`'s only cross-venue join partner
(`scripts/q42_crossvenue_funding_join.py`, feeds Q42/Q43). It holds exactly one file
(`dt=2026-07-17.jsonl`, a single manual backfill capture, BTC+ETH, funding_time range
2026-06-03→2026-07-17T06:00Z) and no collector has ever been wired to refresh it — it is
now 108h+ (4.5 days) stale and drifting +1 day/day as `perp_tape` keeps accumulating forward.
The join script `EXCLUDE`s any window without an HL counterpart rather than erroring, so
every Kalshi funding window after 07-17 silently loses its cross-venue reference — no crash,
no warning, just a shrinking effective join window. `hyperliquid_funding`'s
`one-shot-backfill` classification is factually correct (no collector, no cadence
expectation) — the gap is that "one-shot" and "never alerted" are currently the same thing in
`tape_gap_monitor.py`, which doesn't distinguish a harmless one-shot from a join-critical one
silently going stale.

**Not fixed this run** — the real fix is either (a) wiring `collection.hyperliquid_funding`
into `hourly_pass.py`/a daily pass with an incremental `startTime`, a genuine collector-build
milestone (Q38-scale scope), or (b) a new join-partner staleness detector in
`tape_gap_monitor.py`, a monitor design decision — both bigger than one idle-run milestone.
Recorded as lesson L127's UNENFORCED half; a candidate for a future idle-run policy (b)-style
build or a new queue item.

## Gates

`pytest` full suite green (+1 new acceptance test, 1 existing unit test repointed from
`perp_tape` to `hyperliquid_funding` as its one-shot exemplar since `perp_tape` no longer
belongs to that class). `python scripts/invariants.py --full` exit 0 (pre-existing non-gating
advisories only; `tape_gap_monitor.py` is a standalone reliability script, not wired into
`invariants.py`'s gate — same posture as L118/L121/L122/L124).

Step 9: `SHADOW_REGISTRY={s14_ladder_underwriting}` only; `paper_pass.py` idempotent (0 newly
processed), realized P&L unchanged **+$13.21** (`broker_truth`; s14 is DEAD-at-real-fills per
Q34 — dead-strategy shadow, paper-infra validation only, NOT edge evidence). Still 0 proven
edges.
