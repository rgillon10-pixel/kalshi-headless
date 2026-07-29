# 2026-07-29 — `tape/econ_prints/` data-quality audit (second dedicated pass)

Idle-run policy (c) (LOOP-QUEUE.md v3): a dedicated data-quality deep-dive on `econ_prints`
(feeds Q10/S12's CPI/payrolls/GDP nowcast leg). Idle-run policy (a) was exhausted this run —
the only open `UNENFORCED` lessons (L145/L208/L213/L214) have each been explicitly skipped by
5+ consecutive prior idle runs as out-of-scope or "needs more design work"; re-treading them
would add nothing. Policy (b) was already satisfied (Q48/S55's FOMC probe hardened, Q37's
weather probe prepped). Produced by a `tape-auditor` subagent; the two most consequential
numeric claims (the hour-09 pass-count contradiction and the 0.153s inter-pass gap) were
independently re-derived in the main context before this write-up, both reproduced exactly.
Two-agent verdict rule N/A: data-quality audit, not a registry flip/bootstrap CI/kill decision
(same posture as the perp_tape/hyperliquid_funding/polymarket_macro_pairs precedents).

**Correction to the subagent's framing:** this is NOT the family's first audit. A 2026-07-15
pass (`findings/2026-07-15-econ-daily-cadence-gap-dataquality.md`) already found the
2026-07-09/10 blackout and flagged the single-hour `ts.hour == 9` gate as a structural
exposure (no retry/backfill). That earlier note did not build a check; a later
`_daily_family_gap_issues()` day-gap advisory now covers the presence question. This run digs
one level deeper — into *why* the gate produces both over- and under-collection — and finds
four new, independently confirmed defects the 07-15 pass didn't reach.

## Coverage

19 day-files, `dt=2026-07-05`…`dt=2026-07-28`, **1,720 lines** (`wc -l` confirmed), 24 MB.
344 lines/series × 5 series. **Missing calendar days: 2026-07-09, 07-10, 07-24, 07-25, 07-27**
(5/24; `_daily_family_gap_issues()` reports these exactly, non-gating). No file for today yet
(last capture `2026-07-28T10:03:56Z`, 23.2h old at audit time — under the 24h staleness floor).

Passes/day is wildly non-uniform: 1–137, median 4, mean 29.9/day over 07-13→07-23 collapsing
to 0.4/day over 07-24→07-28 (3 of the last 6 days empty, the other 2 carry exactly 1 pass
each). The family is trending toward silent death, not just gap-prone.

## Validity — clean

0/1,720 malformed lines, 0 conflict markers, 0 torn lines, 0 schema drift (all
`econ_prints.v1`, identical top-level/nested/strike shapes). Trust tags fully clean per
CLAUDE.md's default-FALSE rule: `real_ask` on 93,585/93,585 strikes, `broker_truth` on
1,380/1,380 settled records, `synthetic` on 340/340 GDPNow nowcasts — 0 untagged, 0
`midpoint`. 0 nulls on required fields, 0 prices outside (0,1], 0 crossed books. Append-only
holds (`git log --numstat` on all 3 touching commits: 0 deletion lines). Completeness is
persisted and recomputable from tape (`pass_complete: true` 1,720/1,720, nested
`completeness_ok: true` 7,609/7,609) — the opposite posture from `polymarket_macro_pairs`
pre-L212.

## New defects

**D1 (material — the flagship finding).** Roughly **65% of the family's 344 passes (≈220)
come from an invocation path that does not exist anywhere in this repo.** `econ_prints.run()`
has exactly two callers: `hourly_pass.py` (gated `ts.hour == 9`) and `burst_capture.py`
(30s floor, no anomaly family). Neither explains the tape. Independently reproduced in the
main context: on 2026-07-23, `econ_prints` recorded 90 lines (18 passes) all in hour 09, while
`sports_pairs`/`crypto_hourly`/`orderbook_depth` — legs #1/#2 and a sibling of the same
`hourly_pass` run — recorded **zero** captures in hours 09 or 10 that day (direct per-line
`captured_at` hour census over the real committed files). 18 econ passes cannot have reached
leg 10 of `hourly_pass` without leg 1/2 ever firing. Same shape on 07-16 (29 econ passes vs 3
hourly passes) and 07-20 (23 vs 1). Burst accounts for 07-14's 99 passes (matches
`polymarket_cpi_pairs`' 101 that day) but nothing else. The records carry no invocation-
provenance field (no `mode`/`source`, unlike `perp_tape`'s `mode`, which is exactly what let
L210/L218 root-cause that family's collision) — so the tape itself cannot answer the question.

**D2 (material — the mechanism, and root cause of D1's collision and the 07-16 duplicate).**
`if ts.hour == 9:` (`collection/hourly_pass.py:500`) is a rate gate, not an idempotence gate:
unbounded passes inside the hour, zero outside it. Directly proven concurrent, not just
suspicious: consecutive pass-start gaps on 07-14 include **0.153s** (`20260714T092017Z` →
`20260714T092018Z`, independently reproduced in the main context from the raw `capture_id`/
`captured_at` values) — impossible for one sequential process given `validation/v3_market.py`'s
per-client rate-limit floor (~1.8s of enforced sleep per pass). At least two `econ_prints`
processes run concurrently against the 09-hour gate. Consequence, quantified: **1,720 lines
collapse to 785 distinct payloads once `capture_id`/`captured_at` are excluded — 54.4% of the
family is byte-redundant re-capture** of a monthly-cadence payload (`payrolls` 88% redundant,
`gdp` 72%, `cpi_core_mom` 52%). This is also the birthday-problem mechanism behind the L210/L218
07-16 collision (5 lines, 414ms apart) — confirmed the ONE occurrence in the family's full
history, not a recurring pattern on its own, but a symptom of an unbounded-concurrency gate
that will produce more collisions given a wider gap.

**D3 (the flip side of D2).** The same single-hour gate starves the family when a pass dies
early or misses the hour: 07-24/07-27 never reached hour 09 at all (other-hour captures exist:
`{00,03,06,15,18}` / `{03,06,12,15,21}`); 07-25 reached hour 09 (sports/crypto/macro all fired)
but the pass died after leg 4 — no tape for any of legs 5-10 that day. Because the econ leg
lands ~40min after pass start (structurally near-last), it is the first thing a truncated pass
loses. Stranded-branch check: swept every `tape/*` branch named for the 5 missing days plus the
two branches newer than the last recovery — **0 econ_prints lines exist anywhere that `main`
lacks.** The days are genuinely lost, not merely unswept.

**D4 (correctness-relevant).** `expiration_value` (the family's only `broker_truth` field) is
unnormalized free text whose format changed *within* the same series between events:
`KXCPICORE-26MAY` → `'0.2'`, `KXCPICORE-26JUN` → `'0%'`; `KXPAYROLLS-26JUN` → `'57,000'`
(thousands separator). `float(expiration_value)` raises on 3 of 8 committed settled prints.
Mitigating: value/`n_markets` agreement across every repeat capture is 100% (0 drift) — the
tag is right, the value's type discipline isn't.

**D5.** The `gdp` leg reported one real settlement (`KXGDP-26APR30`, 2026-07-05) then
`no_settled_events` on all 340 subsequent lines (07-06→07-28) while `pass_complete: true` held
throughout — a silent 23-day regression indistinguishable from "never had data" by any
persisted field.

**D6 (benign, recorded for completeness).** GDPNow nowcast staleness is real but honest: 6
distinct values across 344 gdp lines, age up to 9 days, 1 honest `fetch_error`, 0
`parse_error` in 24 days — the scraper hasn't silently broken.

**D7.** Zero analytical consumers exist for this family today (`grep` over `analysis/`,
`scripts/`, `execution/`, `core/`, `validation/` finds only the two monitors). S12 is still
`data-collecting`, gated on ≥20 releases (months of real time) per Q10's own spec — expected,
not a defect, but worth naming: 24 MB / 24 days currently serves no probe.

## What monitoring would and wouldn't have caught

`tape_gap_monitor.py`'s UNDER-CAPTURE detector is a structural no-op for this family's
`kind: "daily-econ-slot"` (`expected_in_window: null`) — a 1-pass day and a 137-pass day are
indistinguishable to it. The 24h staleness clock and the non-gating interior-day gap list are
the only things that would have surfaced D3's holes, and only if a run happens to check while
the gap is still interior (a trailing gap, like today's, is invisible to the interior-only
check — same blind spot already ledgered for weather_actuals/settlement_ledger).

## Lesson candidates → kb-distiller

1. An hour-equality collector gate (`if ts.hour == N`) is a rate gate, not an idempotence gate
   — it admits unbounded passes inside the hour (D2: 54.4% byte-redundant, plus the L210/L218
   collision) and zero outside it (D3: 5 fully-lost days), from the same line of code. The fix
   shape is a once-per-day *key* ("has `dt=<today>` already got a pass?"), not an hour predicate.
2. A tape family whose observed firing pattern contradicts its only in-repo caller cannot be
   root-caused without invocation provenance on the record itself (D1: 65% of passes
   unattributable here; contrast `perp_tape`'s `mode` field, which made the equivalent L210
   question a one-line answer).
3. A `no_settled_events`/`not_built` status that counts toward `pass_complete` converts a
   regression into silence — the honest-status vocabulary needs to distinguish "never had this"
   from "used to have this and no longer does" (D5), since the discriminator (prior tape for the
   same key) is already sitting in the committed history.
4. A venue's `broker_truth` scalar is a string until proven otherwise, and its format can
   change between two events of the *same* series (D4) — normalize (and persist both raw and
   normalized) at capture time.

Files: `collection/econ_prints.py`; `collection/hourly_pass.py:196,500`;
`collection/burst_capture.py:58,98`; `scripts/tape_gap_monitor.py:231`;
`tape/econ_prints/dt=2026-07-16.jsonl` (lines 61-70, the L210/L218 collision).
