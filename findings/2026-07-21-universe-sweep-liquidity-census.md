# 2026-07-21 — `tape/universe_sweep/` liquidity census: ~97% dead-tail auto-generated multi-leg artifacts

**Type:** data-quality / adequacy characterization only. NO strategy claim, NO bootstrap CI,
NO P&L, NO registry change (`kb/strategies/00-index.md` untouched). This is an IDLE-RUN
(LOOP-QUEUE idle-policy (c)) deep-dive that answers the design-input half of Q46's Ryan-gated
call (b) — "add an activity/liquidity discovery filter" — with concrete numbers, and generalizes
lesson L105 from a single day to the full committed history. It is NOT evidence any tradeable
edge exists in `universe_sweep`; the opposite — the breadth census is overwhelmingly
un-tradeable auto-generated multi-leg no-offer artifacts.

## Falsifiable question

Over the full committed `tape/universe_sweep/` history, what fraction of captured lines is a
**real, fillable quote** (a market a taker could actually buy at a non-zero size), and would a
capture-time activity/liquidity discovery filter (Q46 design call (b)) materially shrink the
family's storage without dropping anything a cross-sectional consumer would treat as a quote?

## Method

`python scripts/universe_sweep_liquidity_census.py` — a read-only, NO-network pass over the five
committed daily files `tape/universe_sweep/dt=2026-07-17.jsonl` … `dt=2026-07-21.jsonl`
(5 files / **300,000 lines** / **0 malformed**; every field carries `price_source_tag=real_ask`).
Three tiers, defined in the script and echoed in `findings/universe_sweep_liquidity_census.json`:

- **FILLABLE** — `yes_ask > 0.0 AND yes_ask_size >= 1.0` (a non-zero offer with at least one
  contract of size behind it; a `yes_ask=0.0` no-offer leg is NOT a $0.00 buyable fill — treating
  it as one is the pt1 / prime-directive violation, L1/L105).
- **LIQUID** — `yes_ask > 0.0 AND yes_ask_size >= 10.0`.
- **ACTIVITY** — `volume_24h > 0 OR open_interest > 0 OR volume > 0`.

Pooled and per-day fractions are reported by both line-count and by bytes (the storage lens).

## Numbers (all reproduced-exact; two independent reproductions agree)

Pooled over all 300,000 lines:

- **FILLABLE = 3.03%** (9,098 lines).
- **LIQUID = 2.89%** (8,662 lines).
- **ACTIVITY = 10.84%** (32,519 lines) — carried entirely by `open_interest` (10.83%) and
  `volume` (10.84%).
- **`volume_24h > 0` = 0.00%** — pooled fraction `1.7e-05` (~5 of 300,000 lines nonzero), i.e.
  effectively always-zero across the ENTIRE family. This is the same schema-quality defect L96
  named (`volume_24h` persisted 0.0 despite `volume`/`open_interest` being populated — a probable
  `volume_24h_fp` source-field-name bug in `collection/universe_sweep.py`); confirmed here to
  persist across all five committed days, not just the one L96 checked. **Flagged as a
  schema-quality note, not fixed** (collector code is outside this run's lane).

### Dead tail — two auto-generated multi-leg series dominate

- **DEAD TAIL (not fillable) = 96.97%** of the census (290,902 lines).
- `KXMVESPORTSMULTIGAMEEXTENDED` = **82.21%** of the WHOLE census (n_dead=246,619 of 253,202
  in-census rows for that series).
- `KXMVECROSSCATEGORY` = **14.68%** (n_dead=44,045).
- Together those two `KXMVE*` series are **~96.9%** of the entire census. Every other series is
  **<0.02%** each (the next-largest, `KXSILVERH`, is 0.014%).

### Per-day fillable% and pass-level instability

Per-day fillable fraction: 07-17 = **5.32%**, 07-18 = **2.50%**, 07-19 = **0.97%**,
07-20 = **3.97%**, 07-21 = **1.59%**.

Pass-over-pass, the fillable fraction is NOT stable within a day: 07-18 ranges **0.62%–8.09%**
across its 5 capped passes; 07-20 ranges **1.49%–7.97%** across its 3 passes. Because each pass is
a bounded 20-call (≤20,000-line) slice that reaches a *different* arbitrary chunk of the >80k-market
cursor (the L96 disjoint-slice property), the fillable fraction swings with which markets a pass
happens to reach — **a single pass is not a reliable liquidity estimate** of the family.

### Storage-decision table (answers Q46 design call (b))

Kept-fraction of the family if the collector had filtered to each tier **at capture time**
(from `storage_decision` in the JSON; the headline day-rate uses Q46's own ~71 MB/day figure —
4 capped passes/day × ~17.8 MB/pass):

| tier | definition | keep % of bytes | keep % of lines | ~MB/day retained |
|---|---|---|---|---|
| (none — current) | all open markets | 100% | 100% | ~71 MB/day |
| ACTIVITY | `volume_24h>0 OR open_interest>0 OR volume>0` | **10.74%** | 10.84% | ~7.6 MB/day |
| FILLABLE | `yes_ask>0 AND yes_ask_size>=1` | **2.89%** | 3.03% | ~2.0 MB/day |
| LIQUID | `yes_ask>0 AND yes_ask_size>=10` | **2.76%** | 2.89% | ~2.0 MB/day |

So an activity/liquidity discovery filter would cut this family's storage **~89% (activity tier)
to ~97% (fillable/liquid tier)** while dropping only no-offer / no-activity artifacts — the
KXMVE* auto-generated multi-leg tail that no cross-sectional consumer should treat as a quote
anyway. This is design-input for Ryan's gated call (b); **no collector/code change to
`universe_sweep` was made this run — the cadence + filter decision stays Ryan-gated** (Q46).

## Interpretation (keep honest)

This **generalizes L105** (edge-hunter, 2026-07-19) — which found ~98% of sub-$1 groups were
all-zero no-offer artifacts on a SINGLE day (`dt=2026-07-19`, the anomaly-sweep use case) — to
the FULL 5-day history and to the whole-census *fillable* question, and adds the storage lens.
It **restates the L96 / L105 illiquidity floor** for the storage-decision use case: a
cross-sectional consumer MUST filter to the fillable/active ~3–11% before treating any line as a
real quote. It is emphatically **not** a claim that a tradeable edge exists in `universe_sweep`:
the census is ~97% un-tradeable auto-generated multi-leg no-offer artifacts, and a crossable /
fillable complete-set book never appears in the breadth tape. This finding is data-quality and
adequacy, not a verdict.

## Reproduce

```
python scripts/universe_sweep_liquidity_census.py
```

Writes `findings/universe_sweep_liquidity_census.json` (schema `universe_sweep_liquidity_census.v1`).
Read-only, no network, no credentials; every input line is `real_ask`-tagged committed tape.

## Verification trail

Two independent reproductions agree **exactly**: the census script
`scripts/universe_sweep_liquidity_census.py` AND the research-lead's own throwaway count of the
fillable / dead-tail / KXMVE*-share numbers over the same five committed files. A `verifier` pass
CONFIRMED (independent re-count, does not import the census script, reproduced all 6 headline
numbers exactly); this is a data-quality characterization, not a
strategy verdict, so the two-agent verdict rule is advisory rather than gating here — the numbers
are re-derivable from committed tape by the one-line reproduce command above. See lesson **L125**
(this run) and **L105** (the single-day precursor it generalizes).
