# 2026-07-12 — Stranded-tape sweep size: diagnosed, verdict NOT a real problem

**Status: read-only diagnosis, no code/collector changes.**

## The question

The 2026-07-12 weekly retro (open PR #46, unmerged, awaiting Ryan) flagged that the
research-loop's step-0b stranded-tape sweep recovers a growing number of lines run over run —
1,936 → 872 → 873 → 1,708, and this run's own sweep just recovered 2,632 — with nobody
diagnosing why. Proposed (as draft Q17 in that PR) a read-only investigation. This run drew on
the same underlying question independently (no numbered queue item was eligible: Q1 claimed by
PR #4, Q7/Q9/Q16 DONE, Q13 still BLOCKED until ~07-13, Q14/Q15 data-adequacy BLOCKED, and the
lessons ledger's mechanical helper-conversion chain — L27/L28/L32/L7 → L33/L34/L35/L36 — is now
fully closed). PR #46 itself is left untouched, per its own charter ("never self-merged").

## Method

Dispatched the `tape-auditor` subagent (read-only by charter) to: correlate `tape/hourly-*`
branch timestamps against `main`'s own `tape: hourly pass ... (vps)` commit log; estimate
per-family lines-per-hour over the last week; and check whether the growth tracks elapsed time
since the last sweep or a genuinely rising fallback/discovery rate.

## Verdict: NOT a real problem

The four-sweep window quoted in the retro (1,936→872→873→1,708) is a real subsequence but
reads as a trend only because it starts at a local trough. The full chronological series is
noisy and non-monotone: **2,076 (#39) → 223 (#41) → 1,936 (#42) → 873 (#43) → 872 (#44) →
1,708 (#45) → 2,632 (this run)** — min 223, max 2,632, no slope. 2,076 landed a full day before
the quoted "climb" even starts.

**Dominant driver: `orderbook_depth`'s large, discrete, but flat per-hour footprint.**
`orderbook_depth` runs ~1,100–1,280 lines/hour and is NOT growing (07-07: 1,018/hr, 07-08:
1,281, 07-10: 1,100, 07-11: 1,282, 07-12: 1,167 — ticker discovery is bounded). Every other
family is small (crypto_hourly single digits/hr, polymarket legs tens/hr, sports_pairs
~270–370/hr). Because one orderbook_depth pass alone is ~1,200 lines while a sweep window can
catch 0, 1, or 2 such passes depending on exactly when it lands, the total swings by
±1,200–2,400 lines purely from which side of an hourly boundary the sweep happens to fall on.
This run's `orderbook_depth +1,958` (≈1.6 passes) is 74% of the total 2,632 — that single
family's chunkiness *is* the volatility, not a regression.

**Secondary: sweep-gap irregularity.** Gaps between research-loop firings vary 4.0–6.4h (the
#44→#45 gap was 6.4h, correlating with #45's larger 1,708-line sweep), adding noise on top of
the orderbook_depth effect, but it isn't the main axis.

**Ruled out: a rising per-hour fallback rate.** The cloud-leg's push-to-branch fallback is
structural (~100%, per the 2026-07-03 finding — a permission boundary, not a race) and stays
that way; daily new-branch counts are roughly flat once the 07-07 orderbook_depth-onboarding
spike is excluded (07-04: 11, 05: 14, 06: 11, 07: 22, 08: 9, 09: 0, 10: 10, 11: 11, 12: 9 so
far). No creeping failure rate, no unbounded ticker-discovery growth.

## Flagged in passing (separate from the diagnosed question, not investigated further here)

Zero `tape/hourly-*` branches exist for 2026-07-09 — a full-day gap in cloud-leg fallback
branches that day. Could be a day the cloud leg didn't fire, or branches from that day were
pruned by an earlier (pre-2026-07-10 retro-adopted) cleanup attempt. Worth a coverage check by
whoever next has a spare cycle; unrelated to the sweep-size question this run answered.

## Recommendation

Nothing to fix in the collector or the sweep protocol — the mechanism is fully explained by
`orderbook_depth`'s inherent chunkiness plus normal cadence variance. The one process change
worth making: stop reading the raw total-lines-swept number as a health metric on its own (it
will keep swinging ±1,200+ purely on orderbook_depth timing); if a real regression needs
watching for, track it **per family** so orderbook_depth's noise doesn't mask a genuine
drift in one of the smaller families.
