# 2026-07-27 — `tape/perp_tape/` data-quality audit

Idle-run policy (c) (LOOP-QUEUE.md v3): a dedicated data-quality deep-dive on `perp_tape`,
the collector feeding Q42 (funding-clamp characterization, monitoring-only) and Q43
(same-venue crypto binary-vs-perp consistency, STILL GATED on density). No dedicated audit
of this family existed before today (prior audits: general tape 07-06, econ_prints 07-15,
weather_books 07-18, sports_pairs 07-19, timestamp-parseability 07-24, hyperliquid_funding
07-26, settlement_ledger 07-27). Produced by a `tape-auditor` subagent, numbers independently
spot-checked by the lead against the real committed tape before this write-up (line counts
per day, the sentinel value's presence, the q43 probe's guard code) — all reproduced exactly.
Two-agent verdict rule N/A: this is a data-quality audit, not a registry status flip, a
bootstrapped CI, or a kill decision (same posture as the hyperliquid_funding/settlement_ledger
audit precedents).

## Coverage

`tape/perp_tape/` — 11 day-files, `dt=2026-07-17` … `dt=2026-07-27`, no missing calendar
days. **1,837 lines** total (re-counted directly: `wc -l tape/perp_tape/dt=*.jsonl` sums to
1837, matching the per-day breakdown below exactly), 3.1 MB. **108 capture passes**, every
one with byte-identical shape (1 `markets` / 2 `orderbook` / 13 `funding_estimate` / 1
`funding_rates` section) plus one one-shot `mode=backfill` record on 07-17. Zero
`fetch_error` sections across all 1,837 lines.

| day | lines | passes | | day | lines | passes |
|---|---|---|---|---|---|---|
| 07-17 | 511 | 30 | | 07-23 | 51 | 3 |
| 07-18 | 255 | 15 | | 07-24 | 51 | 3 |
| 07-19 | 102 | 6 | | 07-25 | 17 | 1 |
| 07-20 | 119 | 7 | | 07-26 | 85 | 5 |
| 07-21 | 153 | 9 | | 07-27 | 68 | 4 (incl. 17 lines this run's own stranded-tape recovery landed) |
| 07-22 | 425 | 25 | | | | |

Median inter-pass gap 1.00h, mean 2.36h, max 20.98h (07-25T04:04:53Z → 07-26T01:03:35Z).

## Schema/field integrity — clean

100% JSON-valid (1,837/1,837, independently re-verified line-by-line). 0 empty lines, 0
byte-identical duplicate lines. Null rate 0.0% across all `markets.contracts` rows,
`funding_estimate` records, and deduped funding prints. Source tags: 0 MISSING, 0
unsanctioned — every tag site is `real_ask`/`real_bid`/`broker_truth`. Exact-zero rates on
bid/ask/last/OI/volume resolve exactly to the known-inactive rows (`KXDOTPERP`/
`KXHBARPERP`/`KXXLMPERP`, still inactive in 108/108 passes — not silent zeros). Append-only
confirmed (every commit touching this family is pure-addition). 0 crossed/locked BBO.

## New defects (this run)

**PERP-F1 (material).** Of 33 8-hour funding windows spanning 07-17T00Z→07-27, **4 have zero
capture passes** (`2026-07-23T08Z`, `07-24T08Z`, `07-25T08Z`, `07-25T16Z`) and 8 more have
exactly 1 sample — 12/33 (36%) path-inadequate. `collection/perp_tape.py` destroys the
premium path at each funding boundary with no re-fetch, so these 4 windows are permanently
unrecoverable. Structurally invisible to `scripts/q42_funding_estimate_path_inference.py`:
its `min/median/max_samples_per_window` are computed over windows built *from observed
estimates* (line ~1167), so a zero-sample window can never enter that statistic — the
reported "median 2.0 samples/window" is a survivorship number, not a coverage number.

**PERP-F2 (latent, correctness-relevant).** A single pass (`2026-07-23T07:00:31.621036Z`)
carries `ask = 922337203685477.6` on 5 contracts (`KXBCHPERP`, `KXKSHIBPERP`, `KXLINKPERP`,
`KXSOLPERP`, `KXSUIPERP`) — confirmed by direct grep: `9223372036854775807 / 1e4`, an int64-max
sentinel leaking through `_f()`'s bare numeric coercion with no magnitude guard. Not BTC/ETH,
so Q43 is not poisoned today, but `scripts/q43_perp_binary_consistency_probe.py:208`'s guard
(`if bid <= 0.0 or ask <= 0.0: continue`, confirmed by direct read) only screens zero/negative
placeholders — a BTC/ETH sentinel would produce `mid ≈ 4.6e14`, silently wrecking the
lead-lag correlation instead of being dropped.

**PERP-F3 (minor).** `capture_id` collides across a one-shot backfill and a regular pass that
land in the same wall-clock second (`20260717T010032Z` maps to two distinct `captured_at`
values). This explains a pre-existing, previously-unreconciled discrepancy: the 07-23
edge-hunter LOOP-QUEUE entry counted 30 passes for 07-17 while
`findings/2026-07-23-q43-capture-density-advisory.md` counted 31 — `capture_id` alone is not
a safe join/dedupe key; use `(capture_id, record_type, mode)` or `captured_at`.

**PERP-F4 (near-miss, flagged not yet a defect).** The collector's `RECENT_FUNDING_WINDOW_S`
(24h) has only 3.02h of headroom over the observed max inter-pass gap (20.98h). Any gap past
24h would silently drop finalized funding prints with no automatic recovery (the
`--backfill-funding` flag exists but nothing schedules it). Given the collector's two
documented outages this window, this is a live risk.

**PERP-F5 (known, unchanged).** Density collapse: mean captures/day fell from 13.6 (first 5
days) to 3.2 (last 5 days), −76.5%. Ryan-side collector-health issue, already tracked by
existing VPS-dead advisories — recorded here as the reason Q43's gate is not opening, not as
a new defect.

**PERP-F6 (hygiene, already resolved by this run).** `origin/tape/hourly-20260727T1303Z`
carried 17 genuinely-stranded `perp_tape` lines (one full pass, `captured_at
2026-07-27T13:00:31.314323Z`), 5.3h+ old at detection — past the 30-minute freshness rule.
Recovered as part of this run's step-0b sweep (see kb/00-LOG.md entry); the day-11 row above
already reflects the recovered count.

## Q42 — funding-clamp leg is healthy

1,863 unique `(ticker, funding_time)` finalized prints over 162 distinct 8h boundaries,
2026-06-03T20:00Z … 2026-07-27T12:00Z, zero interior holes on any of the 13 tickers (the
101-162 range across tickers is listing-date variation, not gaps). Clamp confirmed stable on
~8x the prior recon data: 79.1% exact-zero overall, per-ticker range 69.4%–95.1%, inside the
62–99% recon band. This leg took no density damage — only the funding_estimate premium-path
leg (PERP-F1) did.

## Q43 — gate verdict: not closer, further away

Day-count gate (`>= 7`) open since 07-23, now reads 11 — but density against the probe's own
`MIN_CAPTURES_PER_DAY_ADVISORY = 10` is 8/11 days thin. Trailing-7-day captures/day:
`[9, 25, 3, 3, 1, 5, 4]` — 6/7 thin. The 07-26/07-27 uptick (5, 4) is noise around a degraded
floor, not a recovery — both remain under half the advisory threshold. Usable Q43 join
material (108 BTC + 108 ETH BBO rows, `contract_size` present 108/108, implied underlying in
sane ranges) exists but only 13 passes landed across the 4 most recent days versus 30 on
07-17 alone. **Verdict: Q43 remains STILL GATED — the binding constraint is upstream
collector health (Ryan-side), not tape quality.** No registry change.

## Lesson candidates → kb-distiller

1. A per-window density statistic computed only over windows that produced ≥1 observation is
   a survivorship statistic — the honest denominator is the expected window grid, not the
   observed one (PERP-F1).
2. Faithful numeric coercion is not validation: preserving a venue's int64-max no-quote
   sentinel produces a value that clears every null check and every `> 0` guard (PERP-F2).
3. A second-granularity `capture_id` is not a unique key when a one-shot backfill can share a
   wall-clock second with a scheduled pass (PERP-F3).
