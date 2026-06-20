# Strategy candidates — registry

`drafted` · 2026-06-18 · seeded from `findings/2026-06-18-codebase-money-map.md` + `../quant-finance/`

Each candidate is a **falsifiable hypothesis with a binding test**, not a vibe. A candidate
may only graduate (gain capital) after a bootstrapped CI **strictly > 0 at real fillable asks**
(prime directive). Status: `idea` → `binding-test-defined` → `data-collecting` → `tested` →
`live` / `dead`. Confidence is the workflow's verifier confidence.

| id | name | source | status | conf | gate (binding test, abbreviated) |
|---|---|---|---|---|---|
| **S0** | Real-ask substrate (tape + actuals gate + ask primitive) | kalshi.1 + invariants | **built ✅** | 0.9 | substrate, not an edge — enables all scoring (53 tests green, invariants live) |
| **S1** | Longshot-fade real-ask calibration (weather) | arb-bot-v2 tape · QF Theme 2 | **dead ✗** | 0.45 | TESTED n=990 real-ask brackets: net P&L CI [−$0.005,+$0.013] ⊄ >0 → falsified |
| **S2** | FOMC × ZQ single-meeting basis | kalshi.ibkr · QF Theme 6 | **first-cut done · gated** | 0.40 | June'26 free-data cut: bracket overround **+3.4¢ (3× cleaner than weather)** → structure HOLDS; full multi-meeting test gated on CME ticks |
| **S3** | K3 cross-strike monotonicity staleness | kalshi.ibkr · QF Theme 6 | binding-test-defined | 0.30 | 1h calibrate; signal must clear artifact noise floor |
| **S4** | FEx wing-strike fat-tail mispricing | arb-bot H1 · QF Theme 5 | blocked-on-data | 0.25 | quoted tail mass < empirical by > overround+fee |
| **S5** | Weather rehab (EMOS-calibrated × honest fill × real asks) | combo · QF Theme 5 | **dead ✗** | — | TESTED n=641: EMOS CRPS −7.9% but net P&L CI [−$0.063,+$0.008] ⊄ >0 → weather family dead |
| **S6** | Inventory-aware market-making (maker rebate of spread) | QF Theme 3 | idea | — | A-S quotes; spread income > adverse-selection cost |
| **S7** | Kalshi NFL/NBA moneyline vs Pinnacle no-vig line (CLV harvest) | FP→PR · cross-venue segmentation | **idea · try 1st** | med | season backtest: Kalshi ask vs devig Pinnacle fair − overround − fee; block-bootstrap by game; CI>0 |
| **S8** | Crypto-hourly settlement basis (CF BRRNY 60s index vs public spot) | FP→PR · settlement mismatch | idea | med | final-minutes BRRNY-vs-spot gap > overround; bootstrap by hour; CI>0 + feeds genuinely differ (ρ guard) |
| **S9** | Kalshi↔Polymarket same-question lead-lag (laggard leg) | FP→PR · cross-venue info lag | idea | low | forward-poll matched binaries; cross-correlate lead-lag; paper laggard fill; CI>0 |
| **S10** | Crypto-hourly reachability decay (stale far-bracket pricing) | FP→PR · time-decay microstructure | idea | low | T-5/2 reachability vs ask > overround+fee; clear artifact floor; bootstrap by hour; CI>0 |
| **S11** | Sharp-anchored maker quoting on illiquid binaries | FP→PR · liquidity + Pinnacle filter | idea | low | fill-sim: rest only EV+-vs-Pinnacle side; captured spread > adverse-sel + maker fee; CI>0 |

## New candidates S7–S11 (2026-06-18, via /first-principles → /peer-review, 21 agents)

15 candidates generated across 5 first-principles lenses; the adversarial peer-review flagged **all 15** (max-skeptic
bar — every one is an unproven hypothesis); synthesis distilled the 5 most-defensible with kill conditions. Full
dossiers: `../../reports/new-ideas-2026-06-18.html`. All share one design rule — **attack the overround that killed
weather** (clear it on a low-overround 2-outcome family, or earn/sidestep it). **Try S7 first** (lowest overround,
all data free today with deep history, best-documented mechanism, single-leg zero-capital test); **S8** second (24/7
crypto cadence → bootstrappable n in days). NB: the basis-lens draft logged at 19:40 used preliminary S7/S8/S9 ids —
the synthesis numbering above supersedes it.

## Notes on each

**S0 — substrate. → BUILT (2026-06-18).** The machine that lets every other candidate be scored
*honestly*. Lifted byte-identical from `kalshi.1@fd37ae2`: `normalize.py` (real taker ask),
`v1_actuals.py` (3-source gate), `capture_orderbooks.py` (bitemporal forward tape), `v3_market.py`.
Authored fresh for this project: `scripts/invariants.py` (6 Hard Rules, static+DB), `core/pricing.py`
(sanctioned `yes_ask/bracket_sum` site), `core/source_tag.py` (trust=FALSE default), `core/stats.py`
(safe_pstdev n≥4). **53 tests green; `invariants --full` green.** Provenance: `../../PROVENANCE.md`.
S1 was scored on top of it (above) — the substrate works. **Still GATED:** cron forward capture
(needs Kalshi creds + conflicts with the kalshi.1 laptop-cron HOLD) — see `project-status.md`.
→ `findings/2026-06-18-codebase-money-map.md` #1.

**S1 — longshot fade. → DEAD (tested 2026-06-18, real asks).** The bias *exists* and points the
textbook way — longshots (<0.20) realize fewer wins than priced (gaps −1.4¢ to −7.0¢), favorites
(>0.65) underpriced — but the mispricing is only single-digit cents and is swamped by a mean
**+9.84¢ overround** absorbed at the real ask. Net maker-NO-on-longshot P&L = **+$0.00448/trade,
95% block-bootstrap CI [−$0.00486, +$0.01333]** (n=990 reconstructed-real-ask brackets, 654
longshot trades, 21 contract-day blocks); the threshold sweep 0.05→0.25 is uniformly null and the
deepest longshots (<0.05) are negative. Lower CI bound does **not** clear zero → the whole
bias-chasing family is falsified on this sample, exactly as the dossier predicted. Prices are
`real_ask` (exchange BBO), not synthetic. Probe: `scripts/longshot_fade_probe.py`; full writeup:
`findings/2026-06-18-longshot-fade-s1.md`. **Near-miss recorded:** the first run cleared zero on a
cost-model sign bug (maker entry booked as a 2¢ improvement, not a cost) — the exact prime-directive
failure mode; caught and corrected. Candidate invariant filed: a cost haircut must never move the
entry in the trader's favor.

**S2 — FOMC × ZQ basis.** The structurally cleanest candidate: prob-to-prob, **no weather
overround** (Theme 6 no-arbitrage). But it's a directional pre-position (Kalshi halts before
settlement), unbounded per-event downside, ~8 events/year. Replay one meeting at real asks first.

**S3 — cross-strike monotonicity.** Theme 6 again: P(≥80°F) ≥ P(≥85°F) must hold; staleness can
violate it briefly. Cheapest Kalshi-only probe. Taker-by-construction → ~8¢ round-trip floor binds.

**S4 — FEx fat tails.** Theme 5 tail mispricing across venues. Blocked until the FEx tape archiver
(#24) is fixed — unrunnable, do not start until tape persists.

**S5 — weather rehab. → DEAD (tested 2026-06-18, real asks).** The question that decided the
project's direction, now answered. **EMOS calibration works** (leave-one-day-out pooled CRPS
2.366→2.180, −7.9% — fixes the underdispersion exactly as the literature predicts) **but it is
necessary, not sufficient.** 641 trades on real captured asks: net **−$0.02789/trade**, 95%
moving-block-bootstrap CI **[−$0.06297, +$0.00788]** — lower bound does NOT clear zero. Killed by the
same **~9.8¢ overround** that ate pt1 and S1. Adversarially checked: edge-bar sweep makes it *worse*
(real edges get better with conviction, not worse); fill/cost sign audit clean; anti-leak via
Open-Meteo Single-Runs pinned to D−1 00Z (0 leak drops). Probe: `scripts/weather_rehab_s5.py`;
writeup: `findings/2026-06-18-weather-rehab-s5.md`. **All three weather angles (raw ensemble pt1,
longshot-fade S1, EMOS-calibrated S5) are now dead to the overround. Pivot to non-weather: S2/S3/S6.**

**S6 — market-making.** Theme 3 (Avellaneda-Stoikov). Earn the spread instead of paying it; maker
fee is 4× cheaper (`../kalshi-api/03-fees-and-breakeven.md`). The structural long-term play if a
forecast edge never materializes — but adverse selection in thin books is the killer. Idea-stage;
needs the forward tape (S0) to even estimate order-arrival intensity.

## The one rule that orders all of this

**Update 2026-06-18:** S0 is **built**; **S1 and S5 are dead** at real asks; **weather is decided —
DEAD** (all three angles swamped by the ~10¢ overround). The project now **pivots to non-weather
microstructure/basis**: **S2** (FOMC×ZQ basis — structurally no bracket overround; GATED on CME data
sourcing), then **S3** (cross-strike staleness, Kalshi-only) / **S6** (market-making — earn the spread
instead of paying it). No capital moves until a real-ask CI clears zero — **nothing has yet** (still
0 proven edges; but the substrate now scores every future candidate honestly).
