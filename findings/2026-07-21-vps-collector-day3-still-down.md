# VPS collector still dead on day 3 — cadence loss now spans 07-19 through 07-21 (idle-run option c)

- **Date:** 2026-07-21 (research-loop idle-run, protocol v3 option c — data-quality deep-dive).
- **Scope:** Follow-up re-check of `findings/2026-07-20-tape-cadence-decline-vps-collector-down.md`
  (which root-caused the VPS `:23` cron on 87.99.146.250 as dead starting 2026-07-19) and
  `kb/00-LOG.md`'s 2026-07-21 04:15Z edge-hunter entry (which separately found `settlement_ledger`
  frozen for the same underlying reason). Question: is the VPS collector still down today, or did
  it recover? Answer, independently re-derived from committed tape, not assumed from either prior
  write-up: **still completely dead, now a full 3rd calendar day (07-19/07-20/07-21), zero
  VPS-signature lines on any of the three days, across every VPS-primary family.**
- **Mode:** READ-ONLY over committed tape. No collector run, no network calls, no files modified
  other than this write-up + bookkeeping. Not a strategy verdict — two-agent verifier rule N/A
  (same data-quality/ops tier as the 07-20 finding it extends).
- **Method:** re-parsed every line's `captured_at`/`fetch_ts` minute-of-hour directly from the
  currently-committed `tape/<family>/dt=*.jsonl` files (independent script, not a re-run of the
  07-20 finding's own code) and re-bucketed VPS-signature (`:20`-`:29`) vs cloud-signature
  (`:50`-`:59`) vs other, exactly as `ops/ROUTINES.md`'s documented cron minutes predict.

## Result

| family | 07-17 | 07-18 | 07-19 | 07-20 | 07-21 (partial) |
|---|---|---|---|---|---|
| `crypto_hourly` total | 64 | 28 | 14 | 16 | 6 |
| `crypto_hourly` vps | 48 | 18 | **0** | **0** | **0** |
| `perp_tape` total | 511 | 238 | 102 | 119 | 51 |
| `perp_tape` vps | 374 | 153 | **0** | **0** | **0** |
| `orderbook_depth` total | 29,435 | 15,020 | 6,655 | 7,703 | 3,447 |
| `orderbook_depth` vps | 22,710 | 9,766 | **0** | **0** | **0** |
| `sports_pairs` total | 8,521 | 3,667 | 1,682 | 1,871 | 750 |
| `sports_pairs` vps | 6,375 | 2,415 | **0** | **0** | **0** |
| `polymarket_macro_pairs` total | 480 | 210 | 105 | 120 | 45 |
| `polymarket_macro_pairs` vps | 360 | 135 | **0** | **0** | **0** |

Every VPS-primary family shows **exactly zero** `:2x`-minute lines on 07-19, 07-20, AND now
07-21 — the outage has not self-healed and nothing in this repo can fix it (VPS-side, no
code path). Cross-checked against `scripts/tape_gap_monitor.py --no-notify` run live just before
this write-up: it independently confirms `vps_dead: 0 passes in window, cloud collector still
producing` (or `other` for `weather_books`) for every affected family, and separately flags
`settlement_ledger` (96.0h stale — the L123/L124 daily-gate-hour finding, same root cause) and
`weather_actuals` (71.4h stale) as alerting.

**Cumulative loss estimate (VPS-signature lines that would have landed at the pre-outage rate,
`orderbook_depth` alone):** at the 07-17/07-18 blended VPS rate (~16,200 lines/day), 3 missing
days ≈ **~49,000 lines** of L2 depth tape not captured — the single largest-volume family in the
whole repo, and the one Q16/S6/S13/S19/S21/S23's fill-sim work all depend on.

## Why this is worth a fresh finding, not just a repeat of 07-20's

The 07-20 finding and the 07-21 04:15Z edge-hunter note both already named the outage; this run's
purpose was narrowly to check **has it been fixed yet**, since two full research-loop cycles and
one edge-hunter cycle have now passed without a status change. It has not. Escalating a *known,
unresolved, still-open* infra outage on day 3 — rather than letting it go stale in the log as
"already reported" — is the point of this check: cost is compounding (cadence loss + the
downstream `settlement_ledger`/Q36 freeze), and only Ryan can act on it (VPS access).

## What this does NOT do

No collector-side or gate-hour code change (per the 07-21 04:15Z finding's own judgment: rewriting
a live firing gate unattended exceeds the additive-collector self-merge precedent). No registry
change, no strategy claim. `pytest`/`invariants --full` re-run green (this run touches no source,
only tape-derived read paths already covered by existing tests).

## Recommendation for Ryan (unchanged from 07-20, now higher urgency)

Restart the `:23` UTC cron on the VPS (`87.99.146.250`) — that is the only fix; nothing autonomous
can reach it. Until then, `crypto_hourly`/`orderbook_depth`/`sports_pairs`/`polymarket_macro_pairs`
run at roughly half their designed cadence (cloud `:53` only) and `weather_books` similarly loses
its VPS leg; `settlement_ledger` and its Q36 dependency stay frozen regardless (separate gate-hour
issue, already logged).
