# S17 lead-lag first cut — Kalshi ↔ Polymarket recurring-macro (Fed-decision) markets

`LOOP-QUEUE.md` Q12 · 2026-07-12 (research loop) · read-only, descriptive — **NOT a verdict**

## What this is

Q12 gave `collection/polymarket_pairs.py` a second discovery family, `run_fed_decision()`
(2026-07-06), and wired it into the hourly pass — pairing Kalshi's `KXFEDDECISION` 5-bucket
ladder against Polymarket's "Fed Decision in `<Month>`?" events at real book prices on both
sides (`kalshi.yes_ask` and `polymarket.best_ask`, both tagged `real_ask`, a genuine CLOB
book on the Polymarket side; same-question, no de-vig needed). Q12's own remaining-work note
said: "accumulate hourly snapshots, then the eventual lead-lag cross-correlation once enough
history exists, same shape as S9." This run's `scripts/s17_leadlag_probe.py` is that first
cut, the direct S17 analog of `scripts/s9_leadlag_probe.py`, over what had accumulated by
2026-07-12 (~6 days, 2026-07-06 → 2026-07-12, 187 distinct captures).

Both sides being genuine `real_ask` is what makes this leg an apples-to-apples S9 analog.
The CPI leg (`tape/polymarket_cpi_pairs/`) is **deliberately excluded** from the pooled
correlation: its Kalshi side is `kalshi.derived_prob`, a `synthetic` cumulative-ladder
difference, NOT a fillable price (CLAUDE.md Hard Rule #3 / prime directive #1). Pooling it in
would mix a synthetic derived value with a real fill price — the exact mistake the prime
directive forbids. The probe counts it for provenance only (154 records, `synthetic`,
`pooled=false`) and correlates none of it.

## S17's actual thesis, and why this cut can't test it yet

S17 (registry): Kalshi and Polymarket price the same recurring-macro question but sit on
different rails (USD/KYC vs USDC/Polygon) that keep arbitrage from instantly enforcing
parity — so a real information shock (an FOMC decision resolving a meeting, a fresh dot-plot
or CPI surprise repricing the odds) should reprice one venue visibly before the other. That
is the decision-relevant test.

`market_membership_changes()` — the honest proxy for "did a meeting resolve or roll off the
board inside the collected window" — found **zero** changes. This is expected and stated
plainly: Kalshi's listed Fed meetings are Jul / Sep / Oct 2026 and **none has occurred**
inside the 2026-07-06 → 2026-07-12 window. No FOMC decision has landed, so no market has
resolved or rolled off while continuous collection was running. **Zero real information
shocks have landed inside the window.** Every price tick observed so far is ordinary book
noise (bid/ask wobble on markets whose underlying meeting hasn't happened yet), not the
information event S17 needs to test.

## What was measured instead (pooled panel cross-correlation, descriptive only)

Pooled every consecutive-capture (Δ`kalshi.yes_ask`, Δ`polymarket.best_ask`) pair across all
15 (meeting, bucket) pairs (3 meetings × 5 buckets; all 15 have ≥10 captures, 186–187 each)
— the classic price-discovery lead-lag panel test, run honestly even though the underlying
moves are noise rather than shocks. 1 of 2,805 records had `book_fetch_ok=false` and was
dropped (no real ask observed).

| stat | value | n |
|---|---|---|
| contemporaneous ρ (same capture) | **+0.154** | 2,789 steps |
| kalshi-leads-polymarket ρ (kalshi Δt vs poly Δt+1) | −0.003 | 2,774 steps |
| polymarket-leads-kalshi ρ (poly Δt vs kalshi Δt+1) | −0.028 | 2,774 steps |
| tick-size-or-larger (≥1¢) moves, either venue | 215 | (123 kalshi, 116 poly; max \|Δ\| 9¢ each) |
| FOMC resolve/roll-off (shock proxy) events in window | **0** | — |

Reading this honestly: whatever weak co-movement exists shows up **within the same capture
interval** (+0.154 contemporaneous), not across it — consistent with both venues drifting on
the same slow macro backdrop roughly together rather than one leading the other by a full
collection interval. Both lag figures are within noise of zero (and slightly negative), so
neither venue leads at this cadence on book-noise moves. No CI was computed and none should
be trusted this early: this is a **noise-floor characterization, not a lead-lag verdict**.

## Remaining for a real S17 test

Nothing more to build — `run_fed_decision()` + `s17_leadlag_probe.py` already do everything
the thesis needs. What's missing is **an actual information shock inside the collected
window**: the next FOMC decision (the July 2026 meeting is the nearest) resolving a meeting's
buckets while hourly collection runs. When one lands, re-run this script and look at that
meeting's few captures around the decision — which venue's book moved first. Until then S17
stays `data-collecting`, not `dead` or `proven`.

## Reproduce

```
PYTHONPATH=. python scripts/s17_leadlag_probe.py --cpi-note
pytest tests/test_s17_leadlag_probe.py -q
```
