# Q42 — Kalshi crypto-perps funding-clamp characterization + cross-venue funding basis (first cut)

- **Date:** 2026-07-17
- **Probe:** `scripts/q42_funding_clamp_probe.py` (read-only over `tape/perp_tape/dt=2026-07-17.jsonl`;
  HL funding cached to `tape/q42_hl_funding_cache/`, `--offline` re-runs from tape+cache)
- **Tests:** `tests/test_q42_funding_clamp_probe.py` (9 offline unit tests, no network)
- **Headline JSON:** `findings/2026-07-17-q42-funding-clamp-firstcut.json`
- **Lane:** L-mech research-grade characterization. **This is NOT a green light.** The
  short leg (Hyperliquid perp) is OUTSIDE this project's sanctioned execution surface
  (`execution/` is Kalshi-only). The deliverable is a verdict + sizing memo per the Q42 spec.

## One-line verdict

**Register: PARKED-pending-execution-surface + ≥7d-forward-tape.** The anomaly is REAL and
fully characterized — the Kalshi funding clamp is a genuine documented formula dead-band
(not a display/API artifact), and the long-Kalshi/short-Hyperliquid differential is reliably
positive gross (**+0.751 bps/8h, block-bootstrap 95% CI [+0.628, +0.872] bps, admissible,
cleanly separated from zero, n=1,447 windows / 44 UTC-day clusters**). It is **parked, not
falsified**, on two decisive blockers: **(a)** the short-HL leg is **outside this project's
execution surface** (Kalshi-only per CLAUDE.md) — never a green light regardless of carry;
and **(b)** the **crash tail is un-boundable from day-1 marks** — the HL 4%/hr (= 32%/8h)
vs Kalshi 2%/8h funding-cap asymmetry plus mark-vs-mark basis is DEAD-by-data-adequacy until
≥7 days of forward perp tape (both marks aligned) exist. All three Q42-named mechanism-kills
answered **NO**; the ~1 bp materiality bar is a distant third, contestable consideration
(the net-generous CI is cleanly above zero — it merely fails a strict 1 bp bar, not "noise").

## Source tags (trust discipline)

- Kalshi finalized funding prints, marks, settlement/reference prices: `broker_truth` (as tagged in tape).
- Kalshi contract BBO (bid/ask): `real_ask` / `real_bid` (as tagged in tape).
- Hyperliquid published hourly funding: `broker_truth`, `venue=hyperliquid`. This means
  **HL's own realized/settled funding — a truth of THAT venue**, not a Kalshi truth, and
  HL is outside our execution surface. Cached rows carry both `price_source_tag` and
  `venue` so the provenance is never ambiguous. (Chosen over the seed5 `synthetic`/OKX
  convention because these are *realized* settled values, not a constructed prior; the
  `venue` qualifier keeps the offshore/out-of-surface fact explicit.)

## Documented mechanism (web-verified this session; underpins the kill-2 answer)

- **Kalshi perp funding** = TWAP of 1-min premium candles (480/8h) of perp-mark vs CF
  Benchmarks spot; **interest component = 0%**; clamped to **±2%/8h**; and a **documented
  zero threshold: |rate| < 0.01% (= 1 bp/8h) is set to exactly 0**. Settles 04:00/12:00/20:00
  UTC. This zero threshold IS the clamp/dead-band.
- **Hyperliquid funding** (hourly, charged 1/8 each hour) = premium + clamp(interest − premium,
  −0.05%, +0.05%), interest = **+0.01%/8h** (= 1.25e-5/hr), funding clamp **±4%/HOUR**.
  Positive funding: longs pay shorts. HL's +1 bp/8h interest term is the structural floor
  of the calm-regime carry — an L-rent-like venue subsidy, **not a mispricing**.

## Window alignment rule (stated explicitly)

Kalshi settles an 8h window at time T ∈ {04,12,20} UTC, accruing over [T−8h, T]. HL charges
hourly. The probe sums HL hourly rates with top-of-hour timestamp t in **[T−8h, T)** — the 8
hourly charges inside the window. A window with < 8 HL prints is dropped (never silently
treated as a complete sum). The ±1h boundary choice is immaterial: hourly rates are ~1e-5
and autocorrelated. 1,447/1,447 windows joined cleanly (all 13 active Kalshi perps are
listed on HL, including kSHIB).

---

## (a) Clamp characterization

Per-contract finalized-print zero fractions (`broker_truth`), 2026-06-03 → 2026-07-16:

| contract | n | zero-frac | nonzero (pos/neg) | min\|nonzero\| |
|---|---|---|---|---|
| KXBTCPERP | 130 | 0.669 | 43 (42/1) | 1.000e-4 |
| KXETHPERP | 130 | 0.792 | 27 (4/23) | 1.003e-4 |
| KXXRPPERP | 130 | 0.623 | 49 (28/21) | 1.003e-4 |
| KXSOLPERP | 130 | 0.938 | 8 (1/7) | 1.090e-4 |
| KXKSHIBPERP | 112 | 0.616 | 43 (0/43) | 1.012e-4 |
| KXHYPEPERP | 115 | 0.670 | 38 (9/29) | 1.001e-4 |
| KXLINKPERP | 114 | **0.991** | 1 (0/1) | 1.446e-4 |
| KXDOGEPERP | 112 | 0.920 | 9 (0/9) | 1.023e-4 |
| KXLTCPERP | 112 | 0.714 | 32 (0/32) | 1.007e-4 |
| KXSUIPERP | 112 | 0.696 | 34 (0/34) | 1.056e-4 |
| KXBCHPERP | 112 | 0.679 | 36 (0/36) | 1.056e-4 |
| KXNEARPERP | 69 | 0.855 | 10 (0/10) | 1.030e-4 |
| KXZECPERP | 69 | 0.783 | 15 (0/15) | 1.068e-4 |

Recon (62–99%, BTC ~67%, LINK ~99%) is **confirmed**. Note the nonzero prints skew
**negative** (longs receive on Kalshi) on most alt contracts.

**Dead-band width inference: threshold ≈ 1e-4 (1 bp/8h).** Smallest surviving |nonzero|
print across the whole complex = **1.0004e-4**; **0 of 345 nonzero prints fall below 1e-4**.

**Formula dead-band vs display rounding — evidence supports FORMULA DEAD-BAND.** If the
zeros were display-rounding a continuous underlying to a 1e-4 grid, the surviving nonzeros
would themselves be quantized to 1e-4 multiples (grid residual ≈ 0). They are **not**: the
grid-residual mean is **0.222** (near the 0.25 of a uniform continuous distribution), i.e.
the nonzeros are continuous *above* a hard floor at 1e-4 with nothing in the (0, 1e-4)
interval. That is the signature of a **threshold clamp applied to a continuous quantity**
(the documented ±0.01% zero band), not display rounding. How to distinguish definitively
with future data: join the forward `funding_estimate` TWAP path (intra-window, continuous)
to its finalized print — estimates that drift within (0, 1e-4) and finalize to exactly 0
confirm the dead-band. The estimate leg is destroyed at each 8h boundary, so this needs the
≥7-day forward tape (Q42 milestone-3 proper, gated).

**Zeros are temporally CLUSTERED (calm periods), not uniform.** BTC consecutive-zero-run
mean = **5.80** vs the iid-Bernoulli expectation of **3.02** at the same marginal zero rate
(max run 30 = ~10 days of continuous clamping). Per-UTC-day pooled zero-fraction mean 0.736,
stdev 0.166. The clamp releases in bursts, consistent with premium excursions crossing the
±1 bp band during active regimes.

**`funding_rate_estimate` @ 01:00Z dead-band consistency (descriptive, single snapshot —
not over-read):** all 13 live estimates = 0.0 at 01:00:31Z, 1h into the 20:00→04:00 window,
next funding 04:00Z. `max_abs = 0.0`, `consistent_with_dead_band = True`. A single mid-window
snapshot is weakly consistent with the dead band (TWAP-so-far within ±1 bp displays 0) but
cannot by itself distinguish dead-band from an always-0 estimate field — the forward tape does.

## (b) Cross-venue join + regime

**Differential sign derivation (long-Kalshi / short-HL):** positive funding ⇒ longs pay
shorts on both venues. Long Kalshi *pays* the Kalshi print (cashflow −Kalshi). Short HL
*receives* the HL sum (cashflow +HL). **Collected differential = HL_8h_sum − Kalshi_print.**

**Where the +0.751 bps/8h comes from — explicit 3-way decomposition** (pooled means over
the 1,447 joined windows):

> **differential +0.751 = HL net funding (+0.513) − Kalshi print (−0.238)**
> = HL net funding **+0.513** *(HL interest +1.0 bps eroded ~−0.49 by systematically
>   negative HL premium)* **+** Kalshi-richness **+0.238** *(Kalshi funding averages
>   −0.238 bps — longs on Kalshi systematically RECEIVE — so subtracting it ADDS to the
>   collectable)*.

So the carry is **not** "essentially the HL interest subsidy": only ~two-thirds (**+0.513**)
comes from the HL leg (and that is itself the +1 bp interest floor net of a persistent
negative premium, not a clean +1 bp), and **~one-third (+0.238 bps, ~32%)** comes from the
**Kalshi leg's own negative-funding richness** (longs are paid to hold Kalshi perps on
average). Both legs contribute; the Kalshi contribution is the more interesting half because
it is a Kalshi-native structural feature, not an offshore subsidy.

**Naive abs(HL) tercile is MISLEADING — use the SIGNED decomposition.** Bucketing by
|HL_8h| makes the "spike" bucket a mix of positive pumps and negative crashes and falsely
reads a kill (its mean went −0.16 bps). The correct kill-3 check is by **signed** HL_8h
deciles (p10 = −0.61 bps, p90 = +1.00 bps; baseline Kalshi nonzero-fraction 0.238).

**Tie-detection caveat (verifier-mandated relabel):** p90 lands exactly ON the +1.0 bps
HL-interest-floor **mass point** (611 windows print exactly +1.0 bps), so the "≥p90" bucket
holds **n=661 = 46% of the sample** — ~4.6× the expected decile count. It is therefore NOT a
rare positive-spike tail: it is the **modal interest-floor regime** (HL pinned at its +1 bp/8h
interest term with premium ≈ 0). This *strengthens* the substantive finding — the harvestable
+1.17 bps state is the market's normal state, not an excursion — but any percentile-threshold
regime label must be checked against its bucket count before being called a "spike."

| signed regime | n | differential mean | HL mean | Kalshi mean | Kalshi nonzero-frac |
|---|---|---|---|---|---|
| **+1bp interest-floor regime** (≥p90; modal, 46% — p90 sits on the mass point) | 661 | **+1.165 bps** | +1.044 | −0.121 | **0.159** (clamp STAYS SHUT) |
| HL middle 80% | 641 | +0.665 bps | +0.419 | −0.247 | 0.267 |
| HL NEGATIVE tail (≤p10) | 145 | **−0.759 bps** | −1.494 | −0.735 | **0.476** (clamp RELEASES) |

Reading: when HL funding sits at or above its interest floor (the harvestable side — the
**modal** state), the Kalshi clamp **stays shut** (nonzero only 15.9%, below the 23.8%
baseline) and the pair collects **+1.17 bps** — the asymmetry the thesis wants is **present**,
not killed. When HL goes **negative** (crash), the clamp **releases** (47.6%) and Kalshi
*also* prints negative (−0.74 bps), so the long-Kalshi leg **cushions** part of the short-HL
payment (net differential −0.76 bps rather than −1.49). **Kill-3 does NOT fire.**

## (c) Honest carry model (bounded) + cost stack

Kalshi half-spreads from the day-1 contract BBO (`real_ask`/`real_bid`): BTC 1.1 bps,
tight across the complex. HL half-spread not in tape — proxied conservatively at 1.5 bps
(HL maker tier) and flagged.

**Cost stack (base case, post-promo real schedules):**
- Kalshi taker **12 bps** / maker 5 bps (base tier — the zero-fee launch promo is upside,
  NOT durable economics, per the spec).
- Hyperliquid taker **4.5 bps** / maker 1.5 bps (VIP0 base).
- Round-trip (both legs, entry+exit) = 2·12 + 2·4.5 + 2·(Kalshi half-spread) + 2·(HL half-spread)
  ≈ **33–38 bps** depending on asset.
- Capital/margin drag: capital = notional·(1/lev_Kalshi + 1/lev_HL); at a conservative
  **3× effective leverage both legs**, capital ≈ 0.67× notional; idle collateral yield
  assumed 0 (flagged — real forgone risk-free ~4%/yr further nets down ROC).

**Per-asset gross carry** (fraction of notional; annualized at 1,095 windows/yr):

- Pooled gross **+0.75 bps/8h ≈ +8.2%/yr on notional**; gross ROC at 3× ≈ **4–21%/yr**
  across assets (BTC 3.9%, ETH 12.8%, the high-funding alts ZEC 21%, NEAR 21%, SUI 18%).
- **Break-even holding horizon** (round-trip cost / gross-per-window): **9.5–53.5 days,
  median 14.2 days** just to recoup a single entry+exit. Perps never expire, so a
  buy-and-hold amortizes the round-trip toward zero — but that is exactly what re-exposes
  the position to the crash tail (below).
- **Fee-death:** under the worst-case *rebalance-every-window* assumption, a Kalshi taker
  fee of just **0.38 bps/8h** zeroes the pooled net — i.e. any active rebalancing at the
  real 12 bps schedule is instantly, massively negative. The carry only exists as
  buy-and-hold.

**Tail asymmetry (HL 4%/hr cap vs Kalshi 2%/8h cap), quantified:** **20.2%** of joined
windows have a negative HL 8h-sum (short leg pays); the worst single-window differentials
were **−9.35, −7.83, −7.33 bps**. Structurally, a sustained crash can pay up to **4%/hr =
32%/8h** on the short-HL leg while the long-Kalshi leg is capped at receiving **2%/8h** — an
uncorrected short-crash exposure that at 3× leverage carries **liquidation risk** and can
erase a year of the ~8%/yr carry in a single stress episode. **Day-1 marks cannot bound the
persistent mark-vs-mark basis** (Kalshi CF Benchmarks vs HL oracle) — this is the largest
un-quantified risk and is DEAD-by-data-adequacy on the risk side until ≥7 days of forward
perp tape (both marks, aligned) exist.

## (d) Verdict — block-bootstrap by UTC day (L6 unit = UTC day; L41 admissibility; materiality floor)

The L27 tick-magnitude gate (1¢ contract tick) does not map to a funding *rate*, so per the
edge-prober charter we substitute an **explicit economic-materiality floor = 1 bp/8h** (the
Kalshi dead-band width itself: a per-window differential smaller than the venue's own zero
threshold is not economically distinguishable from clamp residue). Dual-cut cost bracketing
(L32-style): net-generous = gross − round-trip amortized over the full sample; net-conservative
= gross − a full round-trip every window.

| cut | mean (bps/8h) | 95% CI (bps) | n_units | n_obs | admissible | clears 1bp floor | outcome |
|---|---|---|---|---|---|---|---|
| gross | +0.751 | [+0.628, +0.872] | 44 | 1,447 | yes | **no** | **DEAD** |
| net_generous (buy-and-hold) | +0.724 | [+0.600, +0.845] | 44 | 1,447 | yes | **no** | **DEAD** |
| net_conservative (rebalance) | −38.74 | [−38.88, −38.59] | 44 | 1,447 | **no** | no | **DEAD-inadmissible** |

The CI is strictly **> 0** under the gross and buy-and-hold cuts and admissible (44 day-clusters,
opposing-sign clusters present) — **cleanly separated from zero**, not an L41 degenerate or a
sign-only artifact. The table's per-cut "DEAD" outcomes are the mechanical gate outputs against
the declared **1 bp/8h materiality floor**, which the CI (upper bound +0.845) does not clear.
That floor is a *contestable* bar for a cross-venue differential (it was motivated by Kalshi's
own dead-band width, but the differential is a real HL-interest-plus-Kalshi-richness quantity,
not clamp residue) — so the floor alone would be a weak kill. **The decisive blockers are
structural, per the PARKED register above:** (i) the short-HL leg is outside this project's
execution surface; (ii) the short-crash tail (HL 4%/hr vs Kalshi 2%/8h cap) plus mark-vs-mark
basis is un-boundable from day-1 marks — DEAD-by-data-adequacy until ≥7 days of forward tape.
The net_conservative (rebalance-every-window) cut is retained only as a **fee-sensitivity
illustration** — no one rebalances a non-expiring perp carry every 8h, so it is not an
independent kill of the buy-and-hold interpretation; it shows how fast the 12 bps taker
schedule destroys any *active* variant (0.38 bps/8h of taker fee zeroes the pooled net).

### Q42 kill-criteria checklist

| # | kill criterion | fires? | evidence |
|---|---|---|---|
| 1 | differential after fees+drag below transaction/basis cost in ALL regimes | **NO** (buy-and-hold) / YES (rebalance) | positive in calm/mid/HL-positive-spike; below cost only in the HL-negative crash tail. Dead in all regimes ONLY under rebalance-every-window. The tradeable death is via the binding-bar gates, not this. |
| 2 | clamp is a display/API artifact, not a formula property | **NO** | 0/345 nonzeros below 1e-4; grid-residual 0.222 (continuous, not gridded); documented ±0.01% zero threshold; estimate=0 consistent. The clamp is a **real formula dead-band**. |
| 3 | clamp releases exactly when offshore spikes (no asymmetry to harvest) | **NO** | on the HL-**positive** (harvestable) side the clamp STAYS SHUT (nonzero 0.159 < 0.238 baseline) and the differential is **+1.17 bps**; the clamp only releases in the HL-**negative** tail, where it *cushions* the loss. |

**None of the Q42 mechanism-kills fire — the anomaly is real.** The honest outcome is the
register at the top: not "alive," not "the anomaly is fake," but **PARKED** — "the anomaly is
real, characterized, gross-positive with an admissible CI, and not a tradeable edge *for this
project today*" (execution surface + un-bounded tail), with named unblock conditions rather
than a terminal verdict.

## Adversarial verification (2026-07-17, two-agent rule)

A separate verifier agent attacked this memo in both directions (fake-positive and false-kill)
before it was finalized: every headline number reproduced byte-for-byte from the committed
tape + cache via `--offline`; the differential sign convention was independently re-derived
from the raw records (HL hourly prints confirmed hourly, summed once — no double-scaling);
window alignment perturbation did not move the result; the read window is pinned (hardcoded
tape file + cache-derived HL window), so the quoted CIs re-derive from committed inputs. The
verifier's mandated revisions are incorporated above: register DEAD → **PARKED** (this is not
a falsification; nothing tradeable-today is being discarded), the explicit 3-way carry
decomposition (~⅓ of the collectable is the Kalshi leg's own negative-funding richness), and
the "≥p90 spike" bucket relabeled as the modal (46%) interest-floor regime with the
mass-point tie noted.

## What ≥7 days of forward `perp_tape` would add (Q42 milestone-3 proper, gated)

1. **Formula confirmation:** forward `funding_estimate` TWAP paths joined to their finalized
   prints — the definitive dead-band-vs-rounding test the single 01:00Z snapshot cannot do.
2. **Basis risk sizing:** aligned Kalshi-mark vs HL-mark time series to bound the mark-vs-mark
   divergence — the single largest un-quantified risk, currently DEAD-by-data-adequacy.
3. **Live clamp-release dynamics** around a real premium excursion (not just finalized prints).

## Reproduce

```
python scripts/q42_funding_clamp_probe.py            # fetch HL + analyze (populates cache)
python scripts/q42_funding_clamp_probe.py --offline  # tape + cache only, deterministic
python -m pytest tests/test_q42_funding_clamp_probe.py -q
```

Numbers above are from the `--offline` run (seed 42, 10,000 resamples); the headline JSON
next to this memo carries the full machine-readable result.
