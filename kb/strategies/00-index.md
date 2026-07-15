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
| **S2** | FOMC × ZQ single-meeting basis | kalshi.ibkr · QF Theme 6 | **first-cut done · gated** | 0.40 | June'26 free-data cut: bracket overround +3.4¢ (3× cleaner than weather) → structure HOLDS; full test gated on CME ticks |
| **S3** | K3 cross-strike monotonicity staleness | kalshi.ibkr · QF Theme 6 | **data-collecting** | 0.30 | `scripts/anomaly_sweep.py` (Q6, 2026-07-04) sweeps daily @09 UTC for real fee-floor-clearing crossings; 0 so far in 3 capped live passes (expected, rare); verdict needs accumulated tape |
| **S4** | FEx wing-strike fat-tail mispricing | arb-bot H1 · QF Theme 5 | blocked-on-data | 0.25 | quoted tail mass < empirical by > overround+fee |
| **S5** | Weather rehab (EMOS-calibrated × honest fill × real asks) | combo · QF Theme 5 | **dead ✗** | — | TESTED n=641: EMOS CRPS −7.9% but net P&L CI [−$0.063,+$0.008] ⊄ >0 → weather family dead |
| **S6** | Inventory-aware market-making (maker rebate of spread) | QF Theme 3 | **dead ✗** | — | DEAD (first cut, 2026-07-11, verifier-CONFIRMED): by-ticker block-bootstrap net maker P&L strictly < 0 on every realistic two-sided book (≤10¢ frozen-inclusive mean −$0.00195 CI [−$0.00297,−$0.00094]; movement-conditioned −$0.02010 CI [−$0.02271,−$0.01759]). Structural killer: the flat 1¢ maker fee exceeds the modal 1–2¢ spread's capturable half. Naive +$0.069 "edge" was a >30¢ wing artifact. Selective-maker (S11) untested. |
| **S7** | Kalshi WC/NBA-tail moneyline vs DraftKings no-vig closing line (CLV harvest) | FP→PR · cross-venue segmentation | **dead ✗** | med | TESTED n=80 games/237 outcomes: mean edge_after_fee −0.0235, 95% block-bootstrap-by-game CI [−0.0245,−0.0225] ⊄ >0 → falsified (taker side) |
| **S8** | Crypto-hourly settlement basis (CF BRRNY vs public spot) | FP→PR · settlement mismatch | **dead ✗** | med | TESTED n=18 hrs/symbol: ρ-guard (historical-spot, lag=0s) BTC 0.9997/ETH 0.9998, max gap never crosses half a band (0.00% both) → dies cheap, same as S5's NWS/WU |
| **S9** | Kalshi↔Polymarket same-question lead-lag (laggard leg) | FP→PR · cross-venue info lag | **dead ✗** | low | RESOLVED 2026-07-06: n=8 ticker-steps across 2 real round transitions, both venues repriced together every time (mean \|Δk−Δp\| 2.2¢) — collection cadence (hourly-min, platform trigger constraint) is coarser than the event itself; data-adequacy DEAD, not a CI falsification. Parity sub-question survives under S17. |
| **S10** | Crypto-hourly reachability decay (stale far-bracket pricing) | FP→PR · time-decay microstructure | **dead ✗** | low | STRUCTURAL DEAD (2026-07-11, verifier-CONFIRMED): far brackets already 1¢-YES-floor-pinned ~40min pre-close (no decay window); the 1¢ tick mirrors to a \$1.00 NO ask (yes_bid=0) so the taker fade has no fillable price (only 4/18,992 far obs had `no_ask<\$1`, 3 from one hour). Block-bootstrap-by-hour n=164 hrs/18,992 obs: mean +\$0.000008, 95% CI [+\$0.000000,+\$0.000024] — 3 orders below the 1¢ tick (rounding residue, `fee(\$1.00)=0`). Maker side untested (S6/S11). |
| **S11** | Sharp-anchored maker quoting on illiquid binaries | FP→PR · liquidity + Pinnacle filter | **data-collecting** | low | fill-sim: rest only EV+-vs-Pinnacle side; captured spread > adverse-sel + maker fee; CI>0. Anchor confirmed live 2026-07-13 (verifier-CONFIRMED): first keyed VPS pass post-Q18 wrote 6 `odds_leg.status="matched"` records (2 WC games × 3 passes, `match_score=2.0`/`outcome_coverage="full"`, de-vig math + Rule #3 tags clean) — data now flows end to end, thin so far (1 bookmaker, 2 games); no P&L/CI claim yet. |
| **S12** | Econ-print nowcast overlay (CPI/NFP/GDP brackets, maker-preferred) | 2026-07-04 gen pass · QF Themes 1+5 × econ category | **data-collecting** | med | ≥20 releases forward-collected real-ask ladders; paper taker AND maker-at-bid where \|nowcast−implied\| > overround share+fee; block-bootstrap by release; CI>0 |
| **S13** | S7-maker — bid side of the proven sports rich-ask | 2026-07-04 gen pass · S7c verdict inversion × maker lens | **dead ✗** | med | TESTED n=80 games/223 filled outcomes (94.1% fill rate): mean edge_after_fee +0.00009, 95% block-bootstrap-by-game CI [−0.00021,+0.00039] — straddles zero → null result. The maker fee alone (~1¢ at mid-range bid prices) consumes essentially the whole assumed 1¢ bid-under-fair margin. |
| **S14** | Ladder overround underwriting (short the complete bracket set) | 2026-07-04 gen pass · overround inversion × QF Theme 3 | **data-collecting** | low | **First non-DEAD candidate — PROXY-POSITIVE, not proven** (2026-07-13, Q13, verifier CONFIRMED-WITH-CAVEAT). Candlestick fill-proxy over `tape/crypto_hourly/` BTC/ETH ladders (mean 131.5 members, MECE): block-boot by event-hour mean **+\$0.0925 CI [+0.063,+0.123]** n=300, clears the tick-magnitude gate, robust to coarser units. BUT the "complete fill" term is \$0 (0.0% complete-fill) — it's path-dependent partial premium net of the near-certain \$1 winner loss (winner filled 96.7%), and **78% of the edge is sub-100-vol income legs** the queue-blind proxy over-credits. Remaining binding gate: a **queue-aware L2/depth fill-sim** (`tape/orderbook_depth/`, short-YES queue read off the mirror `no_bids` side) modeling queue position + the fill↔winner correlation, CI>0 @ real asks over ≥30 event-days |
| **S15** | Cross-event logical-implication scanner (A⇒B ⇒ P(A)≤P(B)) | 2026-07-04 gen pass · S3 extension × QF Theme 6 | **data-collecting** | 0.30 | `scripts/anomaly_sweep.py` (Q11, 2026-07-05) 3rd check + `config/implication_pairs.yaml` (hand-audited `kxwcround_progression` family); runs in existing daily 09 UTC slot; live-validated against real KXWCROUND markets (38 pairs/40 open markets, 0 hits — expected); kill if 0 fee-clearing hits in 60 days |
| **S16** | FedWatch-anchored shock fade on KXFED | 2026-07-04 gen pass · QF Theme 7 × S2 adjacency | idea | low | enter only \|Kalshi−FedWatch\| > spread+fee around releases; paper exit on convergence/T+24h; bootstrap by shock; CI>0; kill if Kalshi leads ZQ |
| **S17** | Kalshi↔Polymarket recurring-macro parity (S9 infra past Jul 19) | 2026-07-04 gen pass · S9 generalization × cross-venue | **data-collecting** | low | Fed + CPI matchers both built (2026-07-06); ≥5 live-book pairs/month cleared; remaining: accumulate + lead-lag xcorr + laggard paper fills @ real asks; CI>0 |
| **S18** | Single-poll overreaction fade (Congress-control markets) | 2026-07-04 gen pass · QF Theme 7 × elections category | idea | low | paper fade @ real ask when single-poll jump >3¢ while polling average moved <1¢-eq; exit reversion/T+72h; bootstrap by poll event; CI>0 before 2026-11 |
| **S19** | Elevated-wing stale-ask maker fade on crypto ladders (S10-maker / L26 direction) | 2026-07-13 Q21 gen · S10-maker-untested × L26 | **dead ✗** | low | TESTED (2026-07-13, verifier-CONFIRMED): queue-aware `orderbook_depth` `no_bids` fill-sim (NOT a candlestick print, L39) over 895 `wing_elevated` members / 175 settled event-hours — 0.45% fill rate overall (4 fills, 1.00% among the 402 joinable), below S14's 2.5% incidental-wing benchmark and the near-zero-fill floor; filled population is only 2 event-hours, below the bootstrap data-adequacy floor, so the +$0.355 win-leg CI [+0.285,+0.425] is a resampling artifact, not an edge (the mechanism's predicted toxic settle-YES leg is 0/895 observed — unsampled, not disproven). S10-maker / L26 now TESTED-DEAD. See `findings/2026-07-13-s19-wing-fade-fillsim-q23-verdict.md`. |
| **S20** | Polymarket wallet forensics (mine top-PnL whales for transferable strategy shapes) | 2026-07-13 · /first-principles → /council CONDITIONAL 3-0 → prereg sprint | **dead ✗** | — | ONE-SHOT RESEARCH SPRINT, not a tradeable strategy — CLOSED, premise DEAD (2026-07-13, peer-reviewed APPROVE-WITH-NOTES). 50 top wallets, 37 evaluable, 1 formal BH-FDR survivor discredited by Result 2 (degenerate bootstrap: 8/8 clusters resolved same-way ⇒ p mechanically 0, L41) → **0 credible skilled wallets**. Decomposes into rewards-subsidized MMs (31/37, Kalshi analogs S6/S13/S19 DEAD), lottery winners (16/37 negative per-trade edge), and the degenerate survivor. "Copy the whales" structurally void. **Live output: H1 → `LOOP-QUEUE.md` Q24** (maker-side rich-ASK selling on sports longshots, the untested S7c mirror; evidentiary basis S7c alone). Lessons L41/L42. All numbers `polymarket_onchain` — zero Kalshi-edge evidence. See `findings/2026-07-13-polymarket-wallet-forensics-s20-dossier.md`. |
| **S21** | S7-maker ASK side — rest the rich longshot ask (H1, the S7c-mirror maker-sell) | 2026-07-13 · S20/H1 → Q24 · S7c verdict inversion (ASK side) × longshot tail × maker lens | **dead ✗** | low | TESTED (2026-07-13, Q24, verifier-CONFIRMED): queue-aware `orderbook_depth` `no_bids` fill-sim (NOT a candlestick print, L39) of resting the S7c-proven-rich ask on sports longshots. The mandated join (fair-anchored longshots from `tape/sports_clv/` × the depth queue from `tape/orderbook_depth/`) is **0/81 joinable (0.00%)** at `fair_prob ≤ 0.20` (0/83 for the `yes_ask ≤ 0.20` proxy) — L9 non-overlap: fair anchors cover kickoffs ≤07-03, sports depth began ≥07-07, so every fair-anchored game had settled before the depth tape began (zero event- AND outcome-ticker overlap, the calendar date is embedded in the ticker so no join-window relaxation manufactures one; verifier reproduced 0 bypassing the probe's join code). Fill rate **0.00%, no testable CI** (n_units=0). Settlement was ADEQUATE (81/81 settled, 8/81=9.88% YES) and the sold-longshot-WINS negative-skew leg is fully modeled (`premium−1−fee`≈−0.86 settle-YES; flat $0.01 maker fee via `core.pricing`, L18/L30) — the death is a depth-queue **timing** gap, not a winner gap. Steelman: `sports_pairs` ask≤0.20 longshots that DO overlap depth → 346/652 (53%) have a queue, MEDIAN queue-ahead **485 contracts** (confirms the binding-risk thesis), but full-sim-eligible = only **3 markets** << the 10-game floor; verifier confirmed alternate paths also 0. → **DEAD by data-adequacy** (NOT a CI falsification; the edge-at-quote stays S7c-proven-rich, the maker FILL question is untested/unmeasurable on current tape, re-testable only on concurrently-collected fair-anchor+depth tape — L43). Same factor family as S14 (short-the-overpriced-tail, factor cap). See `findings/2026-07-13-q24-sports-longshot-maker-fillsim-verdict.md`, `kb/quant-finance/favorite-longshot-bias.md`. |
| **S22** | OFI / depth-imbalance settlement predictor (high-churn two-sided sports books) | 2026-07-14 Q21 gen · Q25 depth anatomy × QF Theme 3 (Cont-Kukanov-Stoikov OFI, newly distilled) | **dead ✗** | low | TESTED (2026-07-14, Q26, verifier-CONFIRMED): join gate passed clean (205 joinable games, 20× the 10-game floor, L50's ex-post-settlement-join fix confirmed working) but the calibration precheck hard-killed it — on the disagreement subset (n=86 rows/81 games, the actual trade population) imbalance hit **27.9%** vs the mid's **72.1%**; because `imb_side`/`mid_side` are opposite by construction on this subset the two hit rates are exactly complementary (sum to 1.0), so this is NOT a masked contrarian signal — sign-flipping imbalance would just reproduce the mid. Robust across every ttc cut (ttc≤1h still 0.281/0.719), ruling out a cadence-washout explanation: the displayed mid already integrates whatever the depth ladder shows on these books. Gates 3/4 (P&L, bootstrap CI) correctly never reached. See `findings/2026-07-14-ofi-depth-imbalance-s22-verdict.md`. |
| **S23** | Favorite-side settlement-underpricing maker (favorite-longshot bias, no devig anchor) | 2026-07-14 Q21 gen · Theme 2 favorite bias × Q25 high-churn cells · S13/S21 adjacency | **dead ✗** | low | TESTED (2026-07-14, Q27, verifier-CONFIRMED): settlement-as-fair-test favorite maker bid (normalized ask/bracket_sum ≥0.65) queue-aware yes_bids fill-sim over tape/orderbook_depth/ joined to ex-post Kalshi settlement (L50, sidesteps S21's L43 death). Join ADEQUATE (24 distinct games ≥10 floor, fill rate 95.83% ≫ S19 0.45% floor — dies on the EDGE, not adequacy/fill). Favorite win-rate among fills 0.6957 (16W/7L) < mean fill_price $0.7261 (real_bid) + $0.01 maker fee = breakeven 0.7361 → favorites marginally RICH at the bid, favorite-longshot bias absent/reversed as a fillable maker edge. Block-boot by GAME n=23: mean −$0.0404, 95% CI [−0.2435,+0.1370], admissible PASS (16 opposing clusters) / clears_tick_magnitude FAIL. Catastrophic favorite-loses leg fully modeled (G2/L41). Same factor slot as S14/S21 (short-the-overpriced-tail / favorite-longshot). See findings/2026-07-14-favorite-underpricing-s23-verdict.md. |
| **S24** | Near-close hourly-return overreaction fade (two-sided sports books) | 2026-07-14 Q21 gen · Theme 7 behavioral × Q25 high-churn cells | **dead ✗** | low | TESTED (2026-07-14, Q28, verifier-CONFIRMED): block-boot by GAME (`event_ticker`, L6) of a real_ask-entry/real_bid-exit fade round-trip on ≥2¢ near-close mid jumps over 7 Q25 high-turnover two-sided sports cells, n=123 games/739 trades: mean **−$0.02936, 95% CI [−0.05179, −0.00587]** — strictly below zero, robust across X∈{2..5}¢. The De Bondt-Thaler reversal is real in mid terms (~0.7¢, conditional-mean sign confirms reversal despite a 0.454 continuation frequency) but an order of magnitude below the ~6-7¢ realized round-trip (2× taker fee + 2× half-spread). Anti-overlap hold-to-settlement leg (n=126/817) CI [−0.05884,+0.00825] also does not clear >0 → does **not** collapse into S22 (both exits unprofitable). Verifier: bit-for-bit re-run + from-scratch re-implementation reproduced every number; hand-verified sample trade, no fee/lookahead/cluster-degeneracy defects. See `findings/2026-07-14-nearclose-fade-s24-verdict.md`. |

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

**S2 — FOMC × ZQ basis.** The structurally cleanest candidate: prob-to-prob, **no weather
overround** (Theme 6 no-arbitrage). But it's a directional pre-position (Kalshi halts before
settlement), unbounded per-event downside, ~8 events/year. Replay one meeting at real asks first.

**S3 — cross-strike monotonicity. → DATA-COLLECTING (probe built 2026-07-04).** Theme 6 again:
P(≥80°F) ≥ P(≥85°F) must hold; staleness can violate it briefly. Taker-by-construction → ~8¢
round-trip floor binds. `scripts/anomaly_sweep.py` (Q6) now sweeps every open market platform-
wide daily at 09 UTC (wired into the hourly collector automatically) for two real-fillable
checks: a complete strike ladder's yes_asks summing under $1+fees (true arb), and nested
"greater"/"less" strikes where buying YES(wider)+NO(narrower) at real asks pays a guaranteed
≥$1 for under $1+fees (the actual fee-floor-clearing version of this candidate's hypothesis,
not just an ask-vs-ask gap). Live-validated against KXBTC's real 188-member ladder (correctly
did NOT flag the already-known fine-band overround as an arb). 0 anomalies in 3 capped live
passes so far — expected, real arbs are rare; the daily sweep needs to accumulate tape before
a frequency×magnitude verdict is possible, same path S7c/S8 took to their bootstraps.

**S4 — FEx fat tails.** Theme 5 tail mispricing across venues. Blocked until the FEx tape archiver
(#24) is fixed — unrunnable, do not start until tape persists.

## New candidates S7–S11 (2026-06-18 · /first-principles → /peer-review, 21 agents)

The post-weather pivot's first non-weather idea set. 5 first-principles generators → adversarial
peer-review (rejected all 15 raw candidates — appropriate skepticism for unproven hypotheses) →
synthesis distilled the 5 most-defensible, each with its kill condition. **All inputs are FREE today;
no idea is in the dead ledger.** Full dossiers: `../../reports/new-ideas-2026-06-18.html`.

- **S7 (try first, med).** Kalshi NFL/NBA moneyline vs Pinnacle de-vigged fair — CLV harvest on the
  lowest-overround family (2-outcome ~2–4¢). Sharps under-participate (books limit winners) → squares
  set Kalshi's price; Pinnacle's balanced book is the truth anchor. Single-leg directional, zero-capital
  season backtest on free Kalshi candlesticks + free odds. *Best risk-adjusted bet.*
- **S8 (med).** Crypto-hourly settlement basis — Kalshi settles on CF Benchmarks BRRNY (60s index avg),
  retail prices off visible spot → genuine feed mismatch (NOT the dead NWS/WU ρ=0.99999 case; first
  check is the ρ guard). 24/7 cadence → bootstrappable n in days.
- **S9 (low).** Kalshi↔Polymarket same-question lead-lag — trade the laggard leg toward the leader after
  a shared shock; segmentation (USDC/USD rail, KYC) keeps arb from enforcing parity. Forward probe (PM
  deep history paywalled).
- **S10 (low). → DEAD ✗ (2026-07-11, verdict note in `01-dead-notes.md`).** Crypto-hourly reachability decay — far range-brackets stay priced above their
  remaining-time reachability as the hour elapses; retail under-updates the tails. Distinct from S3
  (conditional time-decay, not static monotonicity). Must clear the artifact noise floor + chunky longshot fee.
  The artifact floor turned out to be unclearable because there is nothing beneath it (verdict note in `01-dead-notes.md`).
- **S11 (low).** Sharp-anchored maker quoting on illiquid binaries — earn the wide spread (maker fee 4×
  cheaper), quote only the side Pinnacle calls EV+ to filter adverse selection. Distinct from S6 (no
  external truth anchor). Needs the forward L2 tape for fill-intensity.

## New candidates S12–S18 (2026-07-04 · interactive generation pass)

Second post-weather idea set, generated the same way as S7–S11 (19 raw lens-rotated ideas →
adversarial rejection of 12 → 7 survivors), seeded from the S7/S8 verdicts and the untouched
market categories (econ prints, elections, cross-event structure, the maker side). Full
dossier with mechanisms, both data legs named, kill conditions in cents, and the
not-a-dead-idea-repeat argument for each: `findings/2026-07-04-edge-candidates-s12-s18.md`.
Priority by (proven-mispricing proximity × data readiness): ~~S13~~ → S12 → S14 → S15 → S16 →
S17 → S18 (S13 now decided — note in `01-dead-notes.md`). S12/S14/S15/S17 have queue items (Q10–Q13 in
`LOOP-QUEUE.md`); S16/S18 stay registry-only until the queue drains to them.

**S12 — DATA-COLLECTING (2026-07-05, Q10).** `collection/econ_prints.py` now captures the
Kalshi side of this candidate every day at 09 UTC: 5 flagship series (`KXCPI`/`KXCPIYOY`/
`KXCPICORE`/`KXPAYROLLS`/`KXGDP`), full open-ladder real_ask per strike plus the most-recent
settlement (Kalshi's own published print value, `broker_truth`) — 60-day purge risk means this
leg had to start now regardless of the nowcast side being ready. The nowcast leg (Cleveland Fed
CPI / GDPNow) is BLOCKED(nowcast-scrape): Cleveland Fed's page has no static/API-discoverable
number, GDPNow's does but needs nontrivial quarter-window slicing — both left for a follow-up
pass. S12's ≥20-releases gate can't be scored until that leg lands.

**Update (2026-07-05, same-day follow-up Q10 run).** The GDPNow half of the nowcast leg is
now built and live: the Atlanta Fed embeds its full forecast history as three parallel JS
arrays, sliceable to the current quarter's latest update (current read: **+1.19% annualized**
for the quarter ending 2026-06-30, `synthetic`). The Cleveland Fed CPI-nowcast leg stays
`not_built` — a genuinely separate blocker (no scrapable static data at all), not reattempted
this run. S12's gate still needs ≥20 accumulated releases (months of real time) before any
bootstrap is attemptable; still `data-collecting`.

## The one rule that orders all of this


All dated updates (2026-06-18 → 2026-07-14) live verbatim in `01-dead-notes.md` — the
one-line version: **no capital moves until a bootstrapped real-ask CI clears zero, and
none has. 0 proven edges since inception; the bar has never moved.** Everything decided
so far is decided DEAD at real asks: weather (pt1/S1/S5), the S7 family (taker S7c,
maker-bid S13, maker-ask S21), S8, S9-leadlag, S10, S6-hourly-MM, S19, the S20 whale
premise, and the 07-14 trio S22 (calibration) / S23 (fee — closes the favorite-longshot
maker lens S13/S21/S23) / S24 (round-trip). Alive: **S14** (only positive-proxy candidate;
binding gate = Q29's queue-aware L2 fill-sim), **S11** (odds leg matching live), **S17**
(CPI-burst claims verifier-REFUTED; decision deferred to FOMC Jul 29), plus slow gates
S2 (CME/IBKR — Q32), S3/S15 (60-day sweeps), S12 (~20 releases). Dead-candidate notes:
`01-dead-notes.md`. Current queue: `../../LOOP-QUEUE.md` Q29–Q32.
