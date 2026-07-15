# Idea seeds — 8 angles for future Q21 rounds / edge-hunter nights

`seed list` · 2026-07-14 · Ryan-approved local session · referenced from Q21's spec

These are **inputs to idea-generation, not registrations.** Every candidate built from a
seed still passes the full Q21 verifier gate (mechanism / data source / kill condition /
why-it-survives-its-nearest-dead-cousin, two-agent rule). A seed may be killed at idea
stage like anything else — being on this list confers zero evidentiary status. One seed
(L2 depth-imbalance) was independently generated and registered as S22 by the
2026-07-14T03Z Q21 round before this file landed; it is omitted here.

Ordering is rough prior-value, best first.

## Inside Kalshi data (runnable mostly on committed tape)

### 1. Cross-horizon term-structure consistency (hourly vs daily vs weekly ladders)
Same underlier (BTC/ETH, indices) listed at multiple horizons must nest: the daily
distribution is (approximately) the convolution of its hourlies; a weekly bounds its
dailies. Monotonicity/nesting violations across HORIZONS are the time-axis sibling of
S3/S15's strike-axis checks — same true-arb character, unexplored axis. Data: extend the
discovery sweep to capture daily/weekly crypto ladders alongside `crypto_hourly` (the
collector already discovers series; the join is by underlier + window). Nearest dead
cousin: none — S3/S15 are alive-collecting, and this widens the same scanner. Honest
expectation: hits are rare (like S3's 0-so-far), but each is a genuine fee-clearing arb;
cheap to add to the existing daily 09 UTC sweep.

### 2. Platform-wide implication-graph scanner (S15 generalized past 1 family)
S15 currently checks one hand-audited family (`kxwcround_progression`). Auto-derive
implication constraints across ALL series from settlement-source + strike math: KXFED
target-rate vs KXFEDDECISION cut/hold/hike, nested thresholds within a series, event→
outcome chains. Every violation that clears fees at real asks is a true arb. Data:
existing hourly discovery tape. Nearest dead cousin: none dead — this is scale-out of a
data-collecting candidate. Risk to respect: auto-derived implications can be WRONG
(settlement-rule nuance) — a derived pair enters the sweep only after a structural
confirmation step, mirroring how `polymarket_pairs` confirms matches. Expectation: the
scanner's value is breadth × rarity; the derivation library is the real deliverable.

### 3. Listing-age anatomy: are books systematically mispriced in their first hours?
New markets before MMs arrive: is overround widest / skew most biased at listing, and how
fast does it decay? Data: discovery sweeps already timestamp first-seen per ticker —
overround-by-age curve is derivable from committed tape today. This is discovery-class
(Q25-style, no registry flip) that could seed a "trade the first N hours" candidate only
if the anatomy shows structure. Nearest dead cousin: S19/S21 (stale-quote fades died on
fill rates) — any tradeable version MUST lead with the queue-aware fill question, not the
quote-level mispricing. Expectation: anatomy cheap and informative either way.

### 4. S6-at-burst-resolution re-cut (the maker question, on sub-hourly tape)
S6's DEAD verdict was scoped to hourly-snapshot cadence; its charter explicitly left the
maker question open at burst resolution. The Jul 14 CPI + WC and Jul 29 FOMC bursts
(60–120s cadence) are the only sub-hourly tape the project will have until Q31's VPS leg
lands. Pre-build the re-cut so it runs the day burst tape commits: spread-capture vs
displacement at 1–2 min horizons, frozen-pair dual-cut bracketing (L35), flat-1¢-fee floor
(L30) stated up front. Nearest dead cousin: S6 itself — survives only if sub-hourly
displacement is materially smaller than hourly displacement; the flat fee floor may kill
it regardless (say so fast). Expectation: probably still fee-dead; worth one prepped probe
because the tape is already being bought (with burst triggers) either way.

## Outside data sources (all free/cheap, all read-only)

### 5. Perp-funding / basis prior for crypto hourly ladders
Free exchange APIs (Binance/Bybit funding, perp-spot basis) as a directional prior for
within-hour drift: does elevated funding predict settle-side skew the ladder ignores?
Joins onto existing `tape/crypto_hourly/` by hour; historical funding is free and deep, so
a backtest is runnable NOW without new collection. Nearest dead cousins: S8 (basis-as-
settlement-mismatch died on ρ≈1 — this is a DIFFERENT object, a return-direction prior,
not a settlement-feed gap) and S10 (reachability — this predicts the active band, not the
pinned wings). Expectation: crypto hourly direction is close to a martingale; the prior
must clear the taker round-trip on the active band — L27 will decide cheaply.

### 6. Polymarket flow-as-signal at burst resolution (S20 infra, inverted)
S20 killed copy-the-whales; its pipeline (`polymarket_onchain` fills) survives. Different
hypothesis: AGGREGATE flow imbalance on S17-matched pairs as a leading indicator for the
Kalshi leg at sub-hourly resolution. Needs burst-cadence tape on both venues (Jul 14/29
windows; Q31 later). Nearest dead cousin: S9 lead-lag died by CADENCE, explicitly not by
falsification — this is the same question asked at the resolution S9's postmortem said it
requires. Expectation: unknown; the burst windows make it testable for the first time.

### 7. Nowcast-leg retry for S12 (Cleveland Fed alternate route + Truflation)
S12's Cleveland-Fed CPI nowcast leg is `not_built` (page scrape found no static data).
Two retries: (a) Cleveland Fed publishes downloadable nowcast files (xlsx/csv) linked off
the page — fetch the artifact, not the DOM; (b) Truflation's free daily index as an
INDEPENDENT prior — methodology ≠ BLS, so it is a directional prior with an honest
`synthetic` tag, never a settlement predictor. Nearest dead cousin: none — S12 is alive
and collecting its Kalshi leg daily; this completes its other half before the ~20-release
gate matures (~Sep). Expectation: mechanical; value realized only when releases accumulate.

### 8. Team-news shock fade (stale thin books after lineup/injury news)
News hits sharp books minutes before thin Kalshi sports books reprice. Free legs: ESPN
API (already used for kickoffs/odds) + rotowire-class RSS timestamps. The trade is taking
stale Kalshi quotes immediately post-news — S11's adverse-selection filter, inverted.
HARD prerequisite: concurrent fair-anchor + depth tape (Q30) — without it this is
S21's L43 death repeated, and S19's 0.45% fill floor is the null hypothesis. Expectation:
fill-rate-dead is likely; only worth a probe once Q30's Milestone B tape exists, so this
seed is explicitly GATED on Q30.

## Non-seeds (named so nobody re-derives them)

- **Weather anything** — family proven dead 3 ways; do-not-re-mine ledger applies.
- **Copy-Polymarket-whales** — S20 closed the premise (0 credible skilled wallets).
- **Attention/Google-Trends proxies** — no mechanism tying attention to a *fillable*
  mispricing survived first-principles; revisit only with a concrete counterparty story.
