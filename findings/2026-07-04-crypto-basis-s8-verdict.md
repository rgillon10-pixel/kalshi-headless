# S8 — crypto-hourly settlement basis: ρ-guard resolved, verdict DEAD

`2026-07-04` · LOOP-QUEUE.md Q5 (continuation) · **verdict: DEAD (ρ-guard kill, same mechanism
as S1/S5's weather NWS-vs-WU dead-on-arrival)**

## Recap

2026-07-03's first cut (`findings/2026-07-03-crypto-basis-s8-q5.md`) could not run the ρ-guard
as intended: `crypto_hourly`'s paired `spot` field is whatever Coinbase/Kraken printed when the
hourly pass happened to run, a mean **29 minutes** after the settlement instant it's meant to
pair with (VPS `:23`/cloud `:53` cadence vs settlement on the hour). Over 29 minutes, ordinary
BTC drift alone can move price $100+, fully confounding "does BRRNY/BRTI genuinely diverge from
spot" with "spot moved since settlement." The fix (fetch Coinbase's historical `/candles`
endpoint at the exact settlement-instant minute bucket) was attempted but blocked by that
session's egress. Today's egress check (`curl` to Kalshi, Coinbase spot, and Coinbase
`/candles`) all returned 200 — unblocked.

## What changed this run

`scripts/s8_basis_probe.py` gained a `--historical-spot` mode: for each of the 18 unique
settled hours per symbol accumulated in `tape/crypto_hourly/`, it fetches Coinbase's 1-minute
candle for the exact bucket containing the settlement boundary instant (Kalshi's hourly grid
always lands on a UTC minute — confirmed empirically, the requested bucket's own start epoch
matched the target exactly in all 36 fetches, zero gaps) and uses that candle's `open` price
instead of the lagged live snapshot. Lag drops from a mean 1652-1655s to **exactly 0s** for
every hour. Fetched candles are cached (`synthetic`-tagged, raw-bytes sha256) to
`tape/crypto_hourly_historical_spot/` so a rerun doesn't re-hit the endpoint.

Also fixed a latent unit bug while in this code: `frac_hours_gap_over_half_band` used a fixed
$100 band width for both symbols, but ETH's ladder steps $20 (confirmed live from the tape's
own `floor_strike` spacing), not $100 — BTC's constant silently applied to ETH understated how
often its gap crossed half a *true* band. Now keyed per-symbol
(`BAND_WIDTH_DOLLARS_BY_SYMBOL = {"BTC": 100, "ETH": 20}`).

## Result — the corrected ρ-guard

| symbol | n hours | ρ (level), live-lagged spot | ρ (level), **historical spot** | mean gap, historical | max |gap|, historical | frac > half-band, historical |
|---|---|---|---|---|---|---|
| BTC | 18 | 0.963 | **0.9997** | +$16.43 (+2.6bps) | $38.93 | **0.00%** |
| ETH | 18 | 0.947 | **0.9998** | +$0.38 (+2.2bps) | $0.94 | **0.00%** |

Fixing the lag confound moves ρ from the "close but not conclusive" 0.95-0.96 range straight
into the same territory as the weather precedent that killed S5 (NWS vs WU, ρ=0.99999) — two
readings of essentially the same thing. More decisive than ρ alone: **the max observed gap
never once crosses half a bracket width for either symbol**, across all 18 hours each (BTC's
worst case $38.93 vs a $50 half-band; ETH's worst case $0.94 vs a $10 half-band). That is
exactly the guard's own kill criterion — "if spot-vs-settle move together with no meaningful
residual, the feed-mismatch thesis dies cheap" — triggering.

One nuance worth recording honestly: BTC's gap is small but **not centered on zero** — 17 of
18 hours positive, mean +$16.43. That looks like a real, small, structural premium of the CF
Benchmarks settlement index over instantaneous Coinbase spot (plausible: BRRNY blends several
venues via TWAP; Coinbase alone can sit at a persistent small discount to that blend). It is a
genuine finding, but at ~$16 on a $100-wide bracket it is an order of magnitude too small to
ever have flipped which bracket a naive spot-watching trader would expect to settle, in this
sample. ETH shows the same directional pattern at a scale (+$0.38 on a $20 band) that is
noise-indistinguishable from tick rounding.

## Verdict

**S8: DEAD.** The ρ-guard was Q5's own designated cheap-kill gate, and it now kills cleanly
once the lag confound is removed — no bootstrap needed to reach this, matching the project's
own precedent for guard-stage kills (S5's weather ρ-guard). Caveat stated plainly: n=18 hours
per symbol is thin (this is a first-cut kill, not a large-sample proof of absence), and the
small positive BTC bias is worth a footnote for anyone revisiting crypto strategies later, but
it does not clear even the *artifact* noise floor let alone the overround, so there is no case
for continued Q5/S8 data collection. `kb/strategies/00-index.md` S8 row updated to `dead ✗`.

## What's resolved from the prior open item

Q5's remaining "rerun the moment egress reopens" instruction is now done; nothing further is
outstanding for S8. Q7 (S10 reachability-decay probe) is unaffected — it's a different
hypothesis over the same tape and stays `BLOCKED(needs ≥7 days of Q2 tape)`.
