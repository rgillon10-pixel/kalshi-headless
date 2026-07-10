# Tape audit — what has actually been collected (2026-07-06)

`ops run (Ryan-requested, interactive)` · audited at 2026-07-06T15:06Z, post stranded-branch
sweep · re-runnable: the per-family summary below is reproducible with a ~30-line
read-only pass over `tape/**/*.jsonl` (JSON-parse every line, count days / capture IDs /
completeness flags); the stranded-branch check is `git ls-remote --heads origin
'refs/heads/tape/hourly-*'` + per-file line-set diff vs `origin/main`.

## Headline

**29,363 tape lines across 10 families, 2026-07-02 → 2026-07-06, every line valid JSON,
zero unexplained completeness failures.** Both collectors (VPS :23, cloud :53) are firing —
25–29 passes per family landed on 07-06 alone by 15:06Z (~2/hour, matching the two-collector
cadence). This audit also swept **1,158 stranded lines** from `tape/hourly-*` fallback
branches into the canonical files (protocol step 0b; one branch skipped, 11.6 min old).

## Per family (post-sweep)

| family | days | range | lines | passes | incomplete | serves |
|---|---|---|---|---|---|---|
| sports_pairs | 5 | 07-02..07-06 | 25,162 | 140 | 0 | S11/S14 (S7/S13 dead) |
| polymarket_pairs | 3 | 07-04..07-06 | 2,768 | 74 | 0 | S17 parity (S9 dead) |
| polymarket_macro_pairs | 1 | 07-06 | 435 | 29 | 0 | S17 (Fed-decision leg) |
| crypto_hourly | 4 | 07-03..07-06 | 281 | 142 | 12 (all explained, see below) | S10/S14 |
| sports_history | 2 | 07-03..07-04 | 308 | 8 | 0 | S7 verdict inputs (closed) |
| sports_maker_fillsim | 1 | 07-04 | 237 | 1 | 0 | S13 verdict inputs (closed) |
| sports_clv | 2 | 07-03..07-04 | 104 | 2 | 0 | S7 verdict inputs (closed) |
| crypto_hourly_historical_spot | 1 | 07-04 | 36 | 1 | 0 | S8 verdict inputs (closed) |
| econ_prints | 2 | 07-05..07-06 | 25 | 5 | 0 | S12 (needs ≥20 releases — months) |
| anomalies | 3 | 07-04..07-06 | 7 | 7 | 0 anomalies found | S3/S15 (kill clock: 60 days from 07-04/07-05) |

## The 12 incomplete crypto passes are one venue-side hole, not a bug

Every single `pass_complete: false` line (12/12, spanning 07-03→07-05, both collectors
independently) is a 20:2x or 20:5x UTC capture with status `no_hourly_group_found` for both
BTC and ETH — **Kalshi lists no hourly crypto group during the 20 UTC hour**, daily.
Expect exactly 2 incomplete passes/day; probes over this tape must treat that hour as
structurally missing. Recorded as **L15** in `kb/lessons/00-lessons.md`. (No 07-06
occurrence yet at audit time — the 20 UTC hour hadn't arrived.)

## Blocked-item eligibility (from actual tape days, not calendar hope)

- **Q7 / S10** (needs ≥7 days of crypto_hourly): 4 distinct days as of 07-06 →
  eligible ~**2026-07-09/10** if collection continues uninterrupted.
- **Q13 / S14** (needs ≥10 days of Q3 hourly tape): sports_pairs has 5 days →
  eligible ~**2026-07-12/13**. World Cup ends Jul 19 — S14's sports leg has a real but
  narrow post-eligibility window; the crypto leg has no deadline.
- **S12** (needs ≥20 releases): 2 days of econ_prints ladders; monthly/quarterly prints
  mean this stays months out by design. Purge risk (L11) is why it collects anyway.

## Stranded-tape sweep executed in this run

30 `tape/hourly-*` branches listed remotely; line-set diff vs `origin/main` found 6
branches holding lines main lacked → union-appended **1,158 lines** (554+374 sports_pairs,
120+64 polymarket_pairs, 30 polymarket_macro_pairs, 6+4 crypto_hourly, 5 econ_prints,
1 anomalies), every appended line JSON-validated, zero exact duplicates introduced.
`tape/hourly-20260706T1455Z` skipped (11.6 min old, 30-min freshness rule). Branch
deletion still blocked from cloud sessions (documented permission boundary) — swept
branches remain listed but fully reconciled. One malformed branch name exists
(`tape/hourly-` with empty timestamp suffix, from a collector push where the timestamp
variable was evidently empty); contents reconciled, only Ryan can delete it.

## Size trajectory (tape/README.md's ~50 MB decision point)

`tape/` is **36 MB raw** (git pack: 6.6 MiB — JSONL compresses ~5x). sports_pairs grows
~5 MB/day at current cadence; raw size crosses the README's ~50 MB threshold around
**mid-July**. If the threshold means pack size, months remain. Either way this is Ryan's
call per the README ("a deliberate decision for Ryan, not a silent change by a loop run") —
flagged, not acted on. Note: sports_pairs volume drops naturally after Jul 19 (World Cup
ends); the right moment to decide is when post-WC steady-state volume is visible.

## Flags

1. **20 UTC crypto hole** — venue-side, now ledgered (L15). No action.
2. **Tape size** — decision point approaching mid-July (above). Ryan's call.
3. **Malformed branch `tape/hourly-`** — harmless, undeletable from cloud; Ryan can
   `git push origin --delete tape/hourly-` when convenient, along with the ~29 already-
   reconciled stale `tape/hourly-*` branches.
4. **`polymarket_pairs` day-count** — first file is dt=2026-07-04 but continuous hourly
   collection started 2026-07-05T00:11Z; day counts for eligibility math should use
   passes-per-day, not file existence.
