# S9 lead-lag first cut — Kalshi ↔ Polymarket World Cup round markets

`LOOP-QUEUE.md` Q8 · 2026-07-05 (research loop) · read-only, descriptive — **NOT a verdict**

## What this is

Q8 built `collection/polymarket_pairs.py` (2026-07-04) and wired it into `hourly_pass.py`
(2026-07-05T00:14Z), pairing Kalshi's `KXWCROUND` "team to reach round" markets with
Polymarket's structurally identical events at real book prices on both sides (`real_ask`,
no de-vig needed — same Yes/No question on both venues). Q8's own remaining-work note said:
"let repeated hourly snapshots accumulate, then run the lead-lag cross-correlation once
enough history exists." This run's `scripts/s9_leadlag_probe.py` is that first cut, over
whatever had accumulated by 2026-07-05T19:xxZ (~19h of continuous hourly-ish collection,
37 distinct captures, 48 distinct markets, 40 with ≥10 captures).

## S9's actual thesis, and why this cut can't test it yet

S9 (registry): Kalshi and Polymarket price the same question but sit on different rails
(USD/KYC vs USDC/Polygon) that keep arbitrage from instantly enforcing parity — so a real
information shock (a team advancing or being eliminated) should reprice one venue visibly
before the other. That is the decision-relevant test.

`market_membership_changes()` — the honest proxy for "did a round-transition happen inside
the collected window" — found exactly **one** change record, and it is a startup artifact,
not an in-window event: 8 markets present in the very first (pre-hourly-wiring) smoke-test
capture at 2026-07-04T15:15:54Z were gone by the first capture of *continuous* hourly
collection at 2026-07-05T00:11:30Z. Nothing has opened or closed since. **Zero real
round-transition shocks have landed inside the continuously-collected window.** Every price
tick observed so far is ordinary book noise (bid/ask wobble on markets whose underlying
question hasn't resolved yet), not the information event S9 needs to test.

## What was measured instead (pooled panel cross-correlation, descriptive only)

Pooled every consecutive-capture (Δkalshi_yes_ask, Δpolymarket_best_ask) pair across the 40
markets with ≥10 captures — the classic price-discovery lead-lag panel test, run honestly
even though the underlying moves are noise rather than shocks:

| stat | value | n |
|---|---|---|
| contemporaneous ρ (same capture) | **+0.293** | 1,440 steps |
| kalshi-leads-polymarket ρ (kalshi Δt vs poly Δt+1) | +0.044 | 1,400 steps |
| polymarket-leads-kalshi ρ (poly Δt vs kalshi Δt+1) | −0.007 | 1,400 steps |
| tick-size-or-larger (≥1¢) moves, either venue | 220 | — |

Reading this honestly: most of whatever co-movement exists shows up **within the same
capture interval**, not across it — consistent with both venues reacting to something
external (live match odds moving, e.g.) roughly together rather than one leading the other
by a full ~30–60min collection interval. The weak +0.044 kalshi-leads-polymarket figure and
the near-zero reverse figure are not distinguishable from noise at this n and are explicitly
**not** claimed as a lead-lag finding — no CI was computed, and none should be trusted this
early; this is a noise-floor characterization, not a test of the thesis.

## Remaining for a real S9 test

Nothing more to build — `collection/polymarket_pairs.py` + `s9_leadlag_probe.py` already do
everything the thesis needs. What's missing is **an actual round-transition event inside the
collected window**: the next time a KXWCROUND team is eliminated or advances while hourly
collection is running, re-run this script and look specifically at that market's few captures
around the transition (which venue's book moved first). World Cup ends 2026-07-19 — there
should be several such events before then (quarterfinals/semifinals/final are all still
ahead). Until one lands in the tape, S9 stays `data-collecting`, not `dead` or `proven`.
