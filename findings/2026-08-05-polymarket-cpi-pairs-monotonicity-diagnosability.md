# `polymarket_cpi_pairs`: the violation flag is honest, the derived metric is not contained — and `econ_prints` diagnoses 206/206 of it

**Date:** 2026-08-05 · **Author:** research loop, IDLE RUN, idle-run policy (c) (data-quality
deep-dive on one tape family; main-context build — no `Task`/subagent tool is available in this
environment, as recorded on Q19/Q49/Q50/Q51) · **Verdict class:** **DATA-QUALITY** — no edge
claim, no P&L, no bootstrap CI, no registry change, no `kb/strategies/00-index.md` edit, no
collector write-path change. Two-agent rule **N/A** (nothing verdict-class here) and not
satisfiable; the headline numbers were re-derived from tape by an independently written loader
and predicate rather than read off the collector's own flag, which per L279 is a weaker
guarantee than a second agent.

**Artifacts:** `scripts/polymarket_cpi_pairs_monotonicity_audit.py` ·
`tests/test_polymarket_cpi_pairs_monotonicity_audit.py` (37 tests) ·
`reports/polymarket_cpi_pairs_monotonicity_audit.json` · lesson **L286** (renumbered
L284 -> L285 -> L286 across two rebases: a concurrent Q51 milestone-3 pre-flight run pushed
to `main` first and claimed L284, then a concurrent repo-wide duplicate-tape-line census run
pushed and claimed L285).

**Window:** all committed `tape/polymarket_cpi_pairs/` (23 day-files, `dt=2026-07-06`..`08-04`)
joined against all committed `tape/econ_prints/` over the same closed window (`--max-day
2026-08-04`, so the numbers below describe a window a later collector pass cannot move).

## Why this family

`tape/polymarket_cpi_pairs/` is among the least-examined live tape families in the repo. Two
checks, run here rather than taken on trust (the "7 ledger mentions" figure that motivated this
run came from a live tape-auditor survey in this session, not from a committed artifact, and
did not reproduce under a plain grep — so it is not quoted): it appears in **21** distinct
`kb/00-LOG.md` entries against 52 for `econ_prints`, 103 for `polymarket_macro_pairs` and 115
for `sports_pairs`; and of the two probes that reference it, **both deliberately exclude it** —
`scripts/s17_leadlag_probe.py` touches it only through `count_cpi_tape()`, a provenance-only
line count ("deliberately NOT correlated or pooled"), and `scripts/q31_cross_venue_arb_probe.py`
excludes the family outright. **No committed consumer reads `prob_gap` or `derived_prob` from
this family at all**, so what follows is a LATENT defect, not a realized error in any published
number. Its Kalshi leg is synthetic by construction:
`collection/polymarket_pairs.py::price_cpi_bucket_from_kalshi` differences Kalshi's cumulative
"exceed T" `yes_ask` ladder into a Polymarket-shaped bucket probability (an `exact` bucket is
`yes_ask[T-step] - yes_ask[T]`). When the ladder is locally inverted, that difference goes
negative.

## Finding 1 — the DETECTION half is honest (n=1,764)

The collector never clips and never hides: it returns the out-of-range value and sets
`monotonicity_violation: True`. Re-derived independently from `derived_prob` alone (own loader,
own predicate, the collector's own `1e-9` tolerance so the two verdicts are comparable on
identical terms):

| persisted flag | independently recomputed | n |
|---|---|---|
| False | False | 1,558 |
| True | True | **206** |
| False | True (a flag that stopped tracking its value) | **0** |
| True | False | **0** |

**206 / 1,764 = 11.68%** violating, all of them `exact` buckets (the only kind whose transform
can go negative), `derived_prob` ranging down to **-0.89** (`synthetic`). Zero disagreements in
either direction. Distribution across events: KXCPICORE-26JUL 119, KXCPIYOY-26JUN 56,
KXCPI-26JUN 19, KXCPIYOY-26JUL 7, KXCPI-26JUL 5.

## Finding 2 — the METRIC half is not contained

`prob_gap` = `kalshi.derived_prob` (`synthetic`) − `polymarket.best_ask` (`real_ask`) is
computed and persisted on **206/206** of the flagged-invalid records, and carries **no flag of
its own**. The flag protects only a consumer who already knows to read it.

- **2 records** carry `|prob_gap| > 1.0` — arithmetically impossible for a difference of two
  probabilities. Both are `KXCPICORE-26JUL` `exact` 0.5 with `derived_prob = -0.89`:
  `prob_gap = -1.67` (2026-07-06T15:18:43Z, Polymarket ask 0.78 `real_ask`) and
  `prob_gap = -1.73` (2026-07-07T09:26:58Z, ask 0.84 `real_ask`).
- Dispersion of `|prob_gap|`: violating cohort mean **0.5371** / median 0.8930 (n=206); clean
  cohort mean **0.1992** / median 0.0600 (n=1,558); all-in mean **0.2387**. The 11.68%
  violating cohort supplies **26.3%** of the total `|prob_gap|` mass, and **16.5%** of the
  headline mean is excess over the clean cohort — i.e. a naive "average CPI-pair
  cross-venue disagreement" number computed off this family is inflated by roughly a sixth,
  entirely by records the collector itself already knows are invalid.

`prob_gap` is a synthetic-minus-real_ask difference; per CLAUDE.md's trust default an untagged
number is `synthetic`, so it is `synthetic` and can never be a fill price either way. The
defect here is not a mispriced trade, it is a metric that reads as valid to any consumer that
does not join back to the flag.

## Finding 3 — the join: `econ_prints` diagnoses 206/206, exactly (the load-bearing new fact)

The record persists the THRESHOLDS it differenced (`kalshi_inputs = {exceed_le, exceed_ge}`)
but not the two `yes_ask` legs, so from this family's own tape a violating record cannot be
diagnosed — which rung inverted, by how much, stale quote or genuinely crossed ladder.
`tape/econ_prints/` (`econ_prints.v1`) carries the same `KXCPI*` events' full **`real_ask`**
ladder (`floor_strike`, `yes_ask`, `yes_bid`, per-rung `price_source_tag`).

Joined on `kalshi.event_ticker` + the record's own `kalshi_inputs` strikes, nearest capture in
time, with the freshness ladder reported beside the coverage fraction (L283):

| cohort | n | joined | median join age | ≤0.05h | ≤1h | ≤6h | exact reconstruction |
|---|---|---|---|---|---|---|---|
| violating | 206 | **206 (100%)** | **0.00129 h (4.6 s)** | 205 | 205 | 206 | **206 (100%)** |
| clean | 1,558 | 1,558 (100%) | 0.00123 h | 1,537 | 1,537 | 1,558 | 1,552 (99.6%) |
| all | 1,764 | 1,764 (100%) | 0.00124 h | 1,742 | 1,742 | 1,764 | 1,758 (99.7%) |

"Exact reconstruction" = re-applying the collector's own differencing transform to the
`econ_prints` `real_ask` ladder reproduces the persisted `synthetic` `derived_prob` to within
1e-9. All **6** misses in the clean cohort belong to the single 2026-07-06 pass whose nearest
`econ_prints` capture is **5.91 h** away (max drift 0.04); **on every join fresher than one
hour the max reconstruction error is 0.0**. The two families are captured in the same hourly
pass, seconds apart, which is why the join is essentially free.

What the join then buys, on the 206 violating records:

- **206/206** inversions reproduce in the `real_ask` ladder — the defect is Kalshi-side quote
  data, not a bug in the differencing transform.
- **196/206** inverting high rungs have **no resting `yes_bid` at all** (median ask-minus-bid
  **0.97**; 113 wide ≥0.50, 93 tight). The dominant single pattern is
  `yes_ask[0.4]=0.08, yes_ask[0.5]=0.97` (108 of 206) — a **nominal one-sided quote near $1**
  on an out-of-the-money rung, not a two-sided crossed market. The remaining tight cases
  (e.g. `0.01` vs `0.03/0.04`, 55 records) are one-to-three-cent inversions on deep wings.

**So the family is repairable in place, not lost.** Every violating record already committed
can be retro-diagnosed from a sibling tape at zero re-capture cost. What is NOT recoverable
in-family is the reading itself: a consumer of `polymarket_cpi_pairs` alone still gets a
flagged-invalid `derived_prob` and an unflagged `prob_gap` derived from it.

## Finding 4 — the 07-22 drop-off is UNDER-SAMPLING, not a healed ladder

Violations run 07-06..07-21 (176 of them on 07-14, the sanctioned CPI burst — 101 capture
passes that day), then **zero** for 07-22..08-01, then 1 on 08-02. The tape alone reads as
"something got fixed". Measured from the other side of the join (L280 — coverage measured from
one side is not coverage), it did not: applying the same inversion test to every `econ_prints`
observation of the very rung pairs this family pairs, on the very same days,

| day | pairs passes | pairs records | pairs violations | econ rung-pair obs | econ inverted | econ inverted rate |
|---|---|---|---|---|---|---|
| 2026-07-14 | 101 | 1,062 | 176 | 1,462 | 212 | 0.145 |
| 2026-07-21 | 1 | 24 | 1 | 399 | 21 | 0.053 |
| 2026-07-22 | 2 | 48 | 0 | 114 | 0 | 0.000 |
| **2026-07-29** | **1** | 24 | **0** | 437 | **22** | 0.050 |
| 2026-07-30 | 1 | 24 | 0 | 19 | 0 | 0.000 |
| **2026-07-31** | **1** | 24 | **0** | 1,615 | **14** | 0.009 |
| 2026-08-02 | 1 | 24 | 1 | 19 | 1 | 0.053 |

On **2026-07-29 and 2026-07-31** the pairs family recorded zero violations from its single
daily pass while the same rungs were observably inverted in `econ_prints` 22 and 14 times.
The Polymarket bucket ladder did not narrow (all five `exact` buckets 0.1..0.5 are present on
every one of the 23 days), so the drop-off is this family's **own capture cadence** — one pass
a day against an intermittently-inverted ladder — not evidence of improved quote quality. A
zero-violation day is an unsampled day. (Same shape as L283: a hole that looks like breadth is
cadence.)

## Two clean bills, recorded for completeness

- **Strike spacing (L7).** The collector hardcodes a 0.1 CPI step. Read off the data with
  `core.pricing.infer_strike_spacing` over each ladder's own strikes, the inferred spacing is
  **0.1 on all 6,769 committed `KXCPI*` ladders** (KXCPICORE 2,407 / KXCPI 2,407 / KXCPIYOY
  1,955). The assumption is sound here — but it is checked, not assumed.
- **Source tags.** 1,764/1,764 Kalshi legs `synthetic`, 1,764/1,764 Polymarket legs
  `real_ask`, 1,764/1,764 `econ_prints` rungs used in the join `real_ask`. Nothing untagged.
  Parse health: 23 files, 1,764 lines, **0** bad-JSON, **0** foreign-schema lines.

## What this does and does not say

It says: the collector's honesty is real and test-pinned; the containment is not; and the
repair does not need new collection, because the raw legs already sit in `econ_prints` seconds
away. It does **not** say anything about tradability — `prob_gap` is a `synthetic`-vs-`real_ask`
difference on two different venues' books, no CI was computed, nothing here is an edge claim,
and no strategy status changes.

**Two follow-ups, both Ryan-lane (collector write path — deliberately NOT attempted by this
run, the L213/L221/L222/L282 posture):** (1) stop persisting `prob_gap` on a record whose own
`monotonicity_violation` is True (write `null`, the L86 honest-None shape), and/or (2) persist
the two raw `yes_ask` legs alongside `kalshi_inputs` so the family is self-diagnosing without a
cross-family join. Neither is a data-loss repair — Finding 3 shows the history is recoverable
either way — so both are cheap and non-urgent.

## Reproduce

```
python3 scripts/polymarket_cpi_pairs_monotonicity_audit.py --max-day 2026-08-04
python3 -m pytest tests/test_polymarket_cpi_pairs_monotonicity_audit.py -q
```
