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
| **S22** | OFI / depth-imbalance settlement predictor (high-churn two-sided sports books) | 2026-07-14 Q21 gen · Q25 depth anatomy × QF Theme 3 (Cont-Kukanov-Stoikov OFI, newly distilled) | idea | low | last-pre-close L2 book-imbalance predicts settlement beyond mid; taker toward imbalance side @ real_ask; block-boot by GAME; L41-admissible (≥10 games, ≥1 opposing cluster) + L27 magnitude vs taker round-trip; kill if imbalance adds nothing over mid / edge<cost / cadence washout / CI fails either gate |
| **S23** | Favorite-side settlement-underpricing maker (favorite-longshot bias, no devig anchor) | 2026-07-14 Q21 gen · Theme 2 favorite bias × Q25 high-churn cells · S13/S21 adjacency | idea | low | rest maker bid on favorite YES (fair≥~0.65) in high-turnover two-sided sports; net = settlement − fill − 1¢ maker fee; queue-aware yes_bids fill-sim (L39); block-boot by GAME; L41 + L27; same factor slot as S14/S21; kill if win-rate ≤ fill+fee / fill ≤ S19 0.45% floor / CI fails either gate |
| **S24** | Near-close hourly-return overreaction fade (two-sided sports books) | 2026-07-14 Q21 gen · Theme 7 behavioral × Q25 high-churn cells | idea | low | hourly near-close mid jump ≥X¢ partially reverses next hour; fade @ real_ask, full round-trip charged; block-boot by GAME; L41 + L27; anti-overlap: if only hold-to-settlement pays, route to S22 not double-count; kill if momentum / reversal < round-trip / cadence too coarse / CI fails either gate |

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

**S6 → DATA-COLLECTING (2026-07-07, Q16).** With the queue drained to time-blocked items
(Q7/Q13) and Q1 claimed by an open PR, S6 was the only remaining `idea`-stage candidate not
blocked by external data (S4/S10/S11/S14 all already blocked). `collection/orderbook_depth.py`
now captures full L2 book depth (`yes_bids`/`no_bids` price+size ladders, not just BBO) for the
tickers `sports_pairs`/`crypto_hourly` already discover each pass — reusing
`normalize.py:normalize_snapshot` and the tickers read straight back from those collectors'
own freshly-written tape (no platform re-sweep). Every book read is tagged `real_ask`/`real_bid`
(a live order book is a genuine fillable quote). Wired into `hourly_pass.py` as a fifth
sub-pass; live-validated against 6 real current-hour KXBTC tickers, all captured,
`completeness_ok=True`. **Honest limitation:** this loop's recurring collector cadence is
hard-capped at hourly (the same floor S9's lead-lag work hit) — hourly depth snapshots give a
repeated-sample series, not a continuous order-flow tape, so any arrival-intensity estimate
built on this data is snapshot-sampled and must be labeled as such, not treated as a true
message-level fill-sim input. Remaining for S6: accumulate depth snapshots, then attempt a
first-cut arrival-intensity/adverse-selection estimate honestly scoped to what an hourly
sample can support.

**S6 → DEAD (first cut, 2026-07-11, Q-drained draw — verifier-CONFIRMED).** With the numbered
queue drained to externally-blocked items, S6 was taken from the registry's own priority order.
`scripts/s6_maker_firstcut.py` (read-only, 15 offline tests) built a quote-displacement proxy
over 4 accumulated days of `tape/orderbook_depth/` (58,583 records → 36,738 consecutive two-
sided pairs ≤90 min apart): for a ticker seen in two hourly captures, book the quoted half-
spread as maker income if filled and charge the full hour's mid move as adverse selection,
net of the maker fee from `core.pricing.fee_per_contract` (never hand-rolled, L18). Honest
scope stated up front — hourly snapshots cannot observe a real fill, queue position, or
message-level adverse selection, so this proves the gate cannot be met on the realistic
population, it does not measure a live maker edge. Bootstrap unit = the **ticker** (pairs
within one game are correlated draws, L6). **L28 precheck first:** 25,618/36,738 = **69.7%**
of consecutive pairs are frozen (BBO unchanged) — correctly a no-fill booking $0, not phantom
spread capture. **Verdict: DEAD.** By-ticker block-bootstrap (10,000 resamples) of net P&L is
**strictly < 0** on every economically-realistic two-sided cut: ≤2¢ mean −$0.01120, ≤5¢
−$0.00619, ≤10¢ (primary, frozen-inclusive, max-generous) −$0.00195 CI [−$0.00297,−$0.00094],
and the honest movement-conditioned ≤10¢ cut −$0.02010 CI [−$0.02271,−$0.01759]. The only
population with CI>0 is the **>30¢ wide-wing artifact** (+$0.339/contract, 99.9% "profitable")
— a nominal, not maker-capturable, spread on far/one-sided brackets that is wide *because* one
side is empty; the naive "ALL two-sided" +$0.06928 mean was entirely this wing. Verifier
independently reproduced every number and swept ≤15/20/25/30¢ trying to resurrect it — the
only frozen-inclusive CI>0 (≤30¢, +$0.00229, a quarter-cent) fails L27's magnitude-vs-tick gate
and is itself wing-driven; under the movement-conditioned cut every threshold is strictly
negative. **Structural killer:** the maker fee is a **flat 1¢/contract** at every interior
price (L30), which alone consumes the modal Kalshi book's 1–2¢ two-sided spread before adverse
selection is charged — the same fee-floor mechanism that killed S13. More days of the *same*
hourly-cadence tape cannot fix a structural cap. **Untested / NOT falsified here:** the
*selective* maker (S11) — quote only wide-enough, low-toxicity books with an external
fair-value anchor and a real fill-sim; S6's naive "quote everything at the BBO" is what's dead.
Lessons L30 (flat 1¢ maker fee), L31 (wide-wing = nominal not capturable spread), L32 (frozen
pair = no-fill; bracket the verdict with frozen-inclusive + movement-conditioned cuts). Full
writeup: `../../findings/2026-07-11-mm-spread-s6-firstcut.md`.

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
- **S10 (low). → DEAD ✗ (2026-07-11, see verdict note below).** Crypto-hourly reachability decay — far range-brackets stay priced above their
  remaining-time reachability as the hour elapses; retail under-updates the tails. Distinct from S3
  (conditional time-decay, not static monotonicity). Must clear the artifact noise floor + chunky longshot fee.
  The artifact floor turned out to be unclearable because there is nothing beneath it (verdict note below).
- **S11 (low).** Sharp-anchored maker quoting on illiquid binaries — earn the wide spread (maker fee 4×
  cheaper), quote only the side Pinnacle calls EV+ to filter adverse selection. Distinct from S6 (no
  external truth anchor). Needs the forward L2 tape for fill-intensity.

**S8 → data-collecting (2026-07-03).** Q2 built `collection/crypto_hourly.py` — per pass, per
symbol (BTC/ETH), pairs the current hour's `real_ask` bracket book with the previous hour's
`broker_truth` settlement (Kalshi's own `result` + `expiration_value`, the CF Benchmarks index
average it actually settles on) and a `synthetic` Coinbase/Kraken spot read, exactly the (settle,
spot) pairing the ρ-guard needs. First live pass: both symbols captured complete; BTC's 188-member
ladder (1 T-tail + 186 $100-wide bands + 1 T-tail, a clean partition like weather's) priced a
**+$9.27** real_ask bracket overround, ETH +$1.23 — one to two orders of magnitude fatter than
weather/sports, plausibly an artifact of ~180 deep-out-of-the-money bands each near Kalshi's 1¢
min-ask floor rather than real probability mass. Un-investigated — Q5 (S8's first cut) needs to
check this before the ρ-guard or basis calc can mean anything; noted here so it isn't silently
assumed away.

**S9 → data-collecting (2026-07-04, Q8).** No unclaimed queue item was eligible this run
(Q1 claimed by open PR #4 awaiting `ODDS_API_KEY`; Q2-Q6 done; Q7 blocked on ≥7 days of
Q2 tape) — appended Q8 and started the next un-started candidate. Found a clean same-
question pair with **no de-vig needed** (unlike S7): Kalshi's `KXWCROUND` series ("Will
`<team>` qualify for FIFA World Cup `<round>`?") and Polymarket's "World Cup: Nation To
Reach `<round>`" events are the identical Yes/No question on both venues, one market per
(round, team). Built `collection/polymarket_pairs.py`: Polymarket events discovered via
its public `/public-search` endpoint (keyword-narrowed, then structurally confirmed by
title regex — no hardcoded event IDs), Kalshi leg via the existing `Kalshi` client,
matched by exact (round, normalized-team-name) with honest unmatched/ambiguous
accounting. Polymarket prices come off its live CLOB order book (`real_ask`, not the
`outcomePrices` last-trade reference) via `clob.polymarket.com/book`. 20 new unit tests,
live pass: **48/48 Kalshi round markets matched**, completeness ok, mean
`price_gap_yes_ask` (Kalshi yes_ask − Polymarket best_ask) **+0.20¢**, range −3¢/+3¢ —
small and roughly symmetric on this single snapshot, descriptive only, not a verdict.
World Cup ends Jul 19 — the round ladder (quarterfinals→semifinals→final) only has a few
weeks of life; next step is accumulating repeated passes (wire into the hourly collector)
to get enough snapshots for an actual lead-lag cross-correlation.

**S9 → first cross-correlation cut (2026-07-05, Q8 continued) — stays data-collecting.**
`scripts/s9_leadlag_probe.py` (read-only over accumulated `tape/polymarket_pairs/`, 37
captures/48 markets/40 with ≥10 captures) pooled every consecutive-capture price-change pair
into a lag-0/lag±1 cross-correlation: contemporaneous ρ +0.293 (n=1,440), kalshi-leads-poly
ρ +0.044, poly-leads-kalshi ρ −0.007 (both n=1,400, both noise-level). More importantly:
`market_membership_changes()` — the honest proxy for "did a round actually transition inside
the window" — found **zero** in-window round-transition events (the one change on record
predates continuous hourly collection, a startup artifact). S9's actual thesis (does one
venue visibly lag the other around a real information shock) is therefore still untested —
every observed tick so far is book noise, not a shock. No CI, no verdict; stays
`data-collecting` until an actual elimination/advance lands in the tape (several should occur
before the WC ends Jul 19). See `findings/2026-07-05-polymarket-leadlag-s9-first-cut.md`.

**S9 → first real shock event-study (2026-07-06, Q8 continued) — stays data-collecting.**
Two real round transitions have now landed: Brazil and Mexico both eliminated (quarterfinal
losses). New `scripts/s9_shock_eventstudy.py` isolates real transitions from
`market_membership_changes()` and reports each affected ticker's last two captured rows (the
actual repricing step) on both venues. Result across n=8 ticker-steps: Kalshi and Polymarket
moved together every time — mean `|Δkalshi − Δpolymarket|` = 2.2¢, max 8¢, no consistent
one-venue-leads pattern, both venues already reflecting the outcome by the very next capture
(30–60min later). **The actual finding is methodological, not a null result on the thesis
itself:** collection cadence (hourly-ish) is coarser than the event (a match resolves within
minutes) — S9's lead-lag thesis cannot be tested at this resolution without either sub-hourly
captures around scheduled game-end times or accepting this infra only answers a cross-venue
parity question, not lead-lag. Stays `data-collecting`; flagged for a resolution decision
before the WC ends Jul 19 (only a handful of transitions remain). See
`findings/2026-07-06-polymarket-leadlag-s9-shock-eventstudy.md`.

**S9 → resolution decision (2026-07-06, Q8 closed): lead-lag flips dead ✗ (data-adequacy),
parity sub-question survives under S17.** Checked this loop's actual scheduling primitives
before deciding: recurring cron triggers are hard-capped at hourly minimum interval (the
tool's own schema states it), ruling out a sub-hourly recurring poll. One-shot triggers
aren't cadence-limited, but placing them around a match's real end-time needs a kickoff
timestamp the accumulated `tape/polymarket_pairs/` doesn't carry (round/team/price only) and
neither collector currently resolves for KXWCROUND markets — and wiring up N one-shot
captures per remaining match is a new class of unattended multi-day automation, the same
category as the VPS collector and `ntfy-watch`, both of which were Ryan-requested ops
changes rather than something a research-loop run decided alone. Building that
infrastructure unilaterally is outside a single milestone's scope. Per the Stop rules, a
DEAD verdict recorded honestly is a success: the **lead-lag** sub-thesis (does one venue
reprice first around a shock?) is dead by data-adequacy — not falsified by a CI, just
untestable with hourly-minimum automation and no kickoff-time signal to burst around. The
**cross-venue parity** sub-thesis (do the two venues quote the same price on average right
now?) is a different, already-useful question the existing infra answers fine (48/48 matched,
+0.20¢ mean gap, 2026-07-04 first cut) and continues under S17's Fed-decision generalization,
which doesn't need sub-hourly resolution. No new code this run — a decision on already-
collected evidence. See `findings/2026-07-06-polymarket-leadlag-s9-resolution.md`.

**S8 → Q5 first cut (2026-07-03): overround flag resolved, ρ-guard inconclusive (stays
data-collecting).** `scripts/s8_basis_probe.py` (read-only over accumulated
`tape/crypto_hourly/`) found the earlier +$9.27 flag is **mostly real, not a floor-tick
artifact**: only 33.9% of BTC's mean overround (+$5.00 across 19 passes) comes from the
~170 deep-OTM 1¢-floor bands; 66.1% comes from genuine near-the-money spread (ETH splits
57%/43%, floor-heavier since its ladder has fewer outcomes). The ρ-guard itself could not
be run as specified: `crypto_hourly`'s paired `spot` read lags each settlement by a mean
**29 minutes** (VPS `:23`/cloud `:53` cadence vs settlement on the hour) — enough ordinary
BTC drift in that window to fully explain the observed gaps (max $150.41, 84.6% of hours
over half a $100 band) without any real BRRNY-vs-spot mismatch. A correct guard needs spot
sampled **at** the settlement instant (Coinbase's free historical `/candles` endpoint,
`granularity=60`) — attempted this run, blocked by this session's egress (403 on every
external host tried, including Kalshi itself). **S8 stays `data-collecting`, not DEAD**:
unlike S1/S5 this isn't a CI failing to clear zero, it's that the available data can't yet
answer the question. Full writeup: `../../findings/2026-07-03-crypto-basis-s8-q5.md`.

**S8 → DEAD (2026-07-04, ρ-guard kill).** Egress reopened; `s8_basis_probe.py --historical-spot`
fetched Coinbase's free `/candles` endpoint at the exact settlement-instant minute bucket for
all 36 accumulated settled hours (18/symbol), fixing the 29-minute lag confound (lag now 0s
every hour, zero gaps). Corrected ρ jumps from 0.963/0.947 (lagged) to **0.9997/0.9998**
(BTC/ETH) — the same territory as S5's NWS-vs-WU 0.99999 kill — and, more decisively, the max
observed settle-vs-spot gap **never once crosses half a bracket width** for either symbol
(BTC worst case $38.93 of a $50 half-band; ETH $0.94 of a $10 half-band; also fixed a latent
bug where the half-band check used a fixed $100 width for both symbols instead of ETH's actual
$20 strike spacing). BTC shows a small, real, non-zero-centered basis (mean +$16.43, 17/18
hours positive — CF Benchmarks likely runs a hair above raw Coinbase spot) but it's an order of
magnitude below the bracket width, so it never would have flipped a settlement outcome relative
to naive spot-watching in this sample. **Verdict: DEAD**, same cheap-kill mechanism as S1/S5,
no bootstrap needed since the guard itself fails to show a meaningful residual. n=18/symbol is
thin — noted as a first-cut kill, not a large-sample proof — but clears no further bar for
continued collection. Full writeup: `../../findings/2026-07-04-crypto-basis-s8-verdict.md`.

**S10 → DEAD (2026-07-11, Q7 — structural, verifier-CONFIRMED).** Q7 became eligible this run
(the `crypto_hourly` tape crossed 7 valid canonical days: 2026-07-03..08, 10 — the 07-10 entry
being the reprocessed `.jsonl`, the L25 stray-directory day excluded). `scripts/s10_reachability_probe.py`
(read-only, 16 offline tests) used the two-collector offset (cloud + VPS hitting the same hourly
group ~40 min vs ~5 min pre-close) as its only within-hour time variation, and the realized
`broker_truth` settlement as ground truth rather than a fabricated hitting-probability model.
**The decay the thesis needs is not observable**: far brackets (market's own `yes_ask` ≤ 0.01 at
the EARLY capture) were already 1¢-floor-pinned ~40 min before close (mean early→late Δ`yes_ask`
+0.00014). **And the taker trade the thesis requires has no fillable price**: a floor-pinned YES
(`yes_bid=0`) mirrors into a \$1.00 NO ask, so buying NO pays a full dollar to win a dollar back;
only 4/18,992 far obs (0.02%, 3 from one hour) had any `no_ask<\$1` room, and `fee_per_contract(\$1.00)=0`
so the ideal floored trade nets exactly \$0. Block-bootstrap-by-hour (n=164 hrs/18,992 obs, 10,000
resamples): mean **+\$0.000008**, 95% CI **[+\$0.000000, +\$0.000024]** — lower bound a floating-point
0, magnitude 3 orders of magnitude below the 1¢ tick, i.e. rounding residue, not an edge. No
threshold (0.01→0.10) clears zero — relaxing "far" only pulls in reachable brackets that sometimes
hit, flipping the mean negative. **Verdict: STRUCTURAL / data-adequacy DEAD** — the 1¢-tick-mirrors-
to-\$1.00-NO-ask mechanism caps the trade mechanically, so more data cannot fix it (same cheap-kill
family as S8's ρ-guard). Verifier's one caveat (doesn't move the verdict): in-sample 0/18,992 far
brackets actually hit, so the point estimate is slightly survivorship-flavored — but the writeup
already treats it as rounding residue, and the kill is the mechanism, not the sample.
**Untested / out of scope** (NOT falsified here): the **maker** side — resting a NO offer or selling
the rich YES at the elevated ask instead of crossing to the \$1.00 NO ask — which is S6/S11
territory and needs the L2 depth tape + a fill-sim. Lessons L26 (tick-mirror ⇒ tail-fade is a
maker trade, generalizes L12), L27 (magnitude gate must accompany the CI-sign check), L28 (verify
the floor is observable before building a decay/CI pipeline). Full writeup:
`../../findings/2026-07-11-crypto-reachability-s10-firstcut.md`.

**S7/S11 → data-collecting (2026-07-03).** Cloud egress unblocked mid-run (Q0b); built
`collection/sports_pairs.py` (Q1) — discovers Kalshi sports moneyline series by title heuristic,
confirms each game group structurally (2-3 outcomes, every market titled "&lt;A&gt; vs &lt;B&gt; ...
Winner?") before capture, then persists real-ask BBO + `bracket_sum`/`overround_absorbed` per game
to `tape/sports_pairs/`. First live pass: 188 confirmed moneyline games across 16 series (10 of them
`KXWCGAME` World Cup), all `completeness_ok`, mean bracket overround **+21.3¢** (real_ask, n=188) —
notably fatter than the weather ~9.8¢ that killed S1/S5, consistent with these being thinner/newer
markets; needs a liquidity-filtered re-cut before it says anything about S7's edge. The Pinnacle/
odds-api leg stays `blocked_key` (`ODDS_API_KEY` absent) — de-vig math (`devig_multiplicative`) is
implemented and unit-tested, but event matching against Kalshi tickers is not built yet. Next: let
the hourly collector (Q3, still blocked on Q2) accumulate tape, then get an `ODDS_API_KEY` to
unblock the sharp-line leg S7 actually needs.

**S7 → Q4/S7a (2026-07-03): spec revised by a hard retention finding.** `collection/sports_history.py`
sourced both legs of the *historical* backtest S7 needs (distinct from Q1's live `sports_pairs.py`
tape). Discovery that reshapes S7's scope: Kalshi's public API purges a settled market's data
~60 days after close — `/events?status=settled` lists forever, `/markets`/candlesticks don't. **NFL
is dead as a data source** (0/15 sampled 2025-season events retrievable — full season is >60 days
old). **NBA** only its playoff tail survives (~40 games, Apr 30 onward; regular season gone).
**World Cup 2026** (in progress since Jun 11) is fully retained end-to-end — now S7's primary
dataset, and still time-boxed to Jul 19. Odds source is **DraftKings via ESPN's public summary API**
(`pickcenter[].moneyline.{open,close}`, free, genuinely closing-line-labeled), not Pinnacle — no free
Pinnacle API exists; documented as a real fidelity downgrade from the original spec, not silently
substituted. A second trap was caught pre-commit: `occurrence_datetime` is the market's *resolution*
time, not kickoff (candlesticks pulled against it showed post-settlement $1.00 prices) — fixed by not
claiming a decision price from Kalshi alone; S7b must join ESPN's real kickoff timestamp first. Full
writeup: `findings/2026-07-03-sports-history-s7a.md`.

**S7 → Q4/S7b (2026-07-03): join built, first real pregame-ask-vs-devig numbers.**
`match_kalshi_espn` (team-name containment + ±1-day kickoff window) + `run_clv_join` (real
pregame ask anchored at ESPN's actual kickoff, de-vig DraftKings' close) landed in
`collection/sports_history.py`. Caught mid-build: S7a's ESPN pull covered WC group-stage
dates (Jun 15-21) while the Kalshi WC tape's actual events were round-of-32/16 (Jun 26-Jul
2) — zero date overlap between the two legs as originally captured; re-fetched ESPN for the
right window before joining. Live pass: **27 games matched** (24 WC + 3 NBA), **78 outcomes
priced**, mean pregame `bracket_sum` **1.020**, mean `edge_after_fee` **−0.0241** — small-n,
descriptive only, **not a verdict**. S7c (block-bootstrap by game, 95% CI) is still open;
status stays `data-collecting` until then. Full writeup:
`findings/2026-07-03-sports-history-s7b.md`.

**S7 → Q4/S7c (2026-07-04): verdict — DEAD.** Re-fetched Kalshi settled `KXWCGAME` (87
events, full tournament to date) + ESPN closing odds for the matching window, re-ran the
join: 77/87 matched, 0 ambiguous. Combined with S7b's 3 NBA games (deduped by event ticker):
**80 unique games, 237 priced outcomes** — roughly 3x S7b's n. New read-only
`scripts/s7c_sports_clv_bootstrap.py` block-bootstraps `edge_after_fee` by **game** (not
outcome — outcomes within a game are correlated draws), 10,000 resamples: mean **−0.0235**,
95% CI **[−0.0245, −0.0225]**. Both bounds sit well below zero, not just failing to clear
it — Kalshi's real pregame ask runs richer than DraftKings' de-vigged fair price by more
than the taker fee covers. **S7 (taker side, vs DraftKings-close) is DEAD** — a real-ask
block-bootstrap failing to clear zero is a successful, decided result per the Stop rules,
not a reason to keep collecting. Untested and NOT covered by this verdict: the bid/maker
side of the same mispricing (a different trade), and a sharper (Pinnacle-anchored) fair
price should one ever become free. Full writeup:
`findings/2026-07-04-sports-clv-s7-verdict.md`.

## New candidates S12–S18 (2026-07-04 · interactive generation pass)

Second post-weather idea set, generated the same way as S7–S11 (19 raw lens-rotated ideas →
adversarial rejection of 12 → 7 survivors), seeded from the S7/S8 verdicts and the untouched
market categories (econ prints, elections, cross-event structure, the maker side). Full
dossier with mechanisms, both data legs named, kill conditions in cents, and the
not-a-dead-idea-repeat argument for each: `findings/2026-07-04-edge-candidates-s12-s18.md`.
Priority by (proven-mispricing proximity × data readiness): ~~S13~~ → S12 → S14 → S15 → S16 →
S17 → S18 (S13 now decided, see below). S12/S14/S15/S17 have queue items (Q10–Q13 in
`LOOP-QUEUE.md`); S16/S18 stay registry-only until the queue drains to them.

**S13 → DEAD (2026-07-04, Q9).** `scripts/s13_maker_fillsim.py` papered the maker/bid side S7's
own verdict flagged as untested: rest a bid at DK-close-devig fair − 1¢, fill = a real trade
crossing at/below it (hourly candlestick `price.low_dollars`, `open_time` → kickoff), 94.1%
fill rate (223/237 priced outcomes) but `edge_after_fee` conditional on fill is **+0.00009,
95% block-bootstrap-by-game CI [−0.00021, +0.00039]** — a genuine null, not a falsification on
the wrong side like S7. Mechanism: Kalshi's 0.0175 maker fee is itself ~1¢/contract for most
of this dataset's bid-price range, which consumes essentially the entire assumed 1¢
bid-under-fair margin regardless of any real adverse selection (which, separately measured via
DK's open-vs-close line move, was a favorable but tiny +0.00168 — nowhere near enough to
rescue the edge). A first draft of this script used the wrong fee rate (taker 0.07 instead of
maker 0.0175, a 4× overcharge) and a naive full-candle cache that hit 98MB for 237 tickers —
both caught and fixed before this verdict. Full writeup:
`findings/2026-07-04-sports-maker-s13-verdict.md`.

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

**Update 2026-06-18:** S0 is **built**; **S1 and S5 are dead** at real asks; **weather is decided —
DEAD** (all three angles swamped by the ~10¢ overround). The project **pivoted to non-weather**: S2's
free-data first cut **validated the structural thesis** (FOMC bracket overround +3.4¢, 3× cleaner than
weather) — its full multi-meeting test is GATED on CME ticks. The non-weather candidate set is now
**S7–S11** (above), with **S7 (sports CLV vs Pinnacle) as try-first** — lowest overround, all data free,
deep history, single-leg. No capital moves until a real-ask CI clears zero — **nothing has yet** (still
0 proven edges; the substrate scores every candidate honestly).

**Update 2026-07-04:** **S7 is now dead ✗** too — taker-side WC/NBA moneyline vs DraftKings-close CLV,
block-bootstrapped by game (n=80 games/237 outcomes), 95% CI **[−0.0245,−0.0225]**, well clear of zero
on the wrong side. That's S1/S5/S7 all falsified at real asks; S8 remains the most promising open
candidate (data-collecting, ρ-guard blocked on egress to a historical-candle spot feed) with S9-S11
still at `idea`. Still 0 proven edges — the bar has not moved, only the candidate list has shrunk.

**Update 2026-07-04 (later):** S8's ρ-guard ran and killed it (see its row/notes) — S1/S5/S7/S8
all falsified at real asks. Candidate list restocked the same day: **S12–S18 seeded** (section
above) with Q9–Q13 queued, so the loop has ~a week of eligible milestones again. Still 0 proven
edges; the restock widens the search, it does not lower the bar.

**Update 2026-07-04 (even later):** **S13 (the S7-maker follow-up) is dead ✗ on its first
test** — a genuine null (CI straddles zero), not a falsification on the wrong side like S7;
Kalshi's own maker fee eats almost the whole assumed 1¢ edge before any real market effect
gets a chance to matter. S1/S5/S7/S8/S13 now all decided at real asks — none of them live. S9
remains the only `data-collecting` candidate; S6/S10-S12/S14-S18 still at `idea`.

**Update 2026-07-06 (Q12):** **S17 flipped idea → data-collecting.** `collection/polymarket_pairs.py`
gained a second discovery family, `run_fed_decision()`, retargeting the S9 matcher discipline at
Fed rate-decision meetings (Kalshi's `KXFEDDECISION` 5-bucket ladder vs Polymarket's "Fed Decision
in `<Month>`?" events — same partition on both venues, matched by meeting month/year + bucket, never
the Kalshi ticker's bps suffix alone). Wired into `hourly_pass.py` as a fourth cross-venue sub-pass
so collection outlives the World Cup. Live pass: **15/15 currently-listed Polymarket Fed-decision
markets matched** (Jul/Sep/Oct 2026 meetings — the only ones Polymarket has created so far;
Kalshi's own forward calendar runs to Jan 2028, all correctly recorded as `unmatched_kalshi` and
explicitly NOT gating completeness, since that gap is normal forward-calendar noise, not a data
problem), 0 ambiguous, 0 book errors, `completeness_ok`. One-snapshot gaps ranged −3¢ to +15¢
(descriptive only, not a verdict). CPI/inflation matching is explicitly deferred: Kalshi prices a
cumulative "≥ threshold" ladder while Polymarket prices an exact bucket — pairing those needs a
derived/synthetic transform, not a same-question real_ask pair, so it isn't faked here. S17's own
gate (≥5 matched live-book pairs/month) is already cleared by this one pass; remaining work is
accumulation + the eventual lead-lag cross-correlation, same shape as S9.

**Update 2026-07-06 (Q12 CPI follow-up):** built the deferred CPI/inflation leg,
`run_cpi()` — a third discovery family pairing Kalshi's `KXCPI`/`KXCPIYOY`/`KXCPICORE`
cumulative "exceed T" ladders against Polymarket's exact 0.1-point bucket partition for
the same 3 US print series. Not a same-question `real_ask` pair like the WC-round/Fed
families: `price_cpi_bucket_from_kalshi` derives each Polymarket bucket's probability by
differencing two adjacent Kalshi asks, tagged `synthetic` per Hard Rule #3's spirit even
though both inputs are genuine `real_ask` fills — this is exactly the transform the prior
cut deferred rather than fake. 23 new unit tests, wired into `hourly_pass.py`'s existing
09 UTC daily slot (CPI releases monthly — no need for hourly cadence). Live pass: 17 open
Kalshi CPI events, 3 matched Polymarket events (current core-MoM/YoY/headline-MoM prints),
22/28 buckets priced — the other 6 need Kalshi strikes beyond what its ladder currently
lists (a real, honestly-recorded coverage gap, not a bug) — 0 unmatched/ambiguous
Polymarket events, one bucket's derived probability came back negative
(`monotonicity_violation: true`, a thin/stale Kalshi strike, recorded not clipped). S17's
own gate was already cleared by the Fed leg; this closes the item's only documented
remaining-work gap besides accumulation.

**Update 2026-07-11 (Q7): S10 flipped idea → dead ✗.** Crypto-hourly reachability decay — a
verifier-CONFIRMED structural DEAD (not a marginal CI miss): far brackets are 1¢-floor-pinned
before any decay window opens, and the 1¢ YES tick mirrors to a \$1.00 NO ask, so the taker fade
has no fillable positive-EV price at all. S1/S5/S7/S8/S9/S13/S10 now all decided at real asks —
none live; still **0 proven edges**, the bar has not moved. S10's maker side stays open under
S6/S11 (a different trade, not falsified here). See its verdict note above.

**Update 2026-07-11 (S6): market-making flipped data-collecting → dead ✗ (first cut).** Drawn
from the registry's own priority order after the numbered queue drained (no Q-item). Inventory-
aware maker / earn-the-spread — verifier-CONFIRMED DEAD on the realistic population: the flat 1¢
maker fee (L30) exceeds the modal Kalshi book's 1–2¢ capturable spread, so a by-ticker block-
bootstrap of net maker P&L is strictly < 0 on every economically-real two-sided cut (the naive
+$0.069 "edge" was a >30¢ wing artifact). Same fee-floor family as S13. S1/S5/S7/S8/S9/S13/S10/S6
now all decided at real asks — none live; still **0 proven edges**, the bar has not moved. The
*selective* maker (S11, sharp-anchored, quotes only wide-enough low-toxicity books) is a distinct
un-falsified trade. See S6's verdict note above.

**Update 2026-07-06 (Q14/Q15, S16 + S18 feasibility): both stay `idea`, both hit real
data-adequacy walls.** With the queue drained to time-blocked items, followed the registry's
own stated priority past S15/S17 to the next two un-started candidates. **S16** (FedWatch
fade): `cmegroup.com` is behind Akamai-class bot protection — every path tried (root, the
FedWatch tool page, three guessed widget/API endpoints) 403'd or reset the connection with a
real browser UA over HTTP/1.1, while Kalshi and the Atlanta Fed's GDPNow page (a structurally
similar free-JS-data target) both worked fine this same run, so the block is venue-side, not
sandbox egress. **S18** (Congress-control fade): Kalshi's `HOUSE`/`SENATE`/`KXHOUSE`/`KXSENATE`
series exist but list **zero markets in any status** — the 2026 midterm control contracts
aren't listed yet, so there's no Kalshi print to build against; separately, the classic free
generic-ballot polling feeds are gone (538's CSV redirects to a dead ABC News stub, not just
moved; RealClearPolling 403s the same way as CME) — Wikipedia's 2026 House-elections article
is a live fallback source for whenever Kalshi actually lists the markets. Neither is a CI
falsification — both are honest `BLOCKED` verdicts per the Stop rules, recorded so a future
run doesn't re-spend a milestone on the same dead ends. See
`findings/2026-07-06-s16-s18-feasibility-blocked.md`.

**Update 2026-07-12 (Q12, S17 lead-lag first cut): stays `data-collecting`, no shock yet.**
Built `scripts/s17_leadlag_probe.py` (the S17 analog of `s9_leadlag_probe.py`) and ran it
read-only over ~6 days of `tape/polymarket_macro_pairs/` (2026-07-06→07-12): **2,805 records,
187 distinct captures, 15 (meeting,bucket) pairs** (Jul/Sep/Oct 2026 × 5 buckets, all with
186–187 captures; 1 record dropped for `book_fetch_ok=false`). Pooled panel cross-correlation
of consecutive-capture Δ (both sides `real_ask`, apples-to-apples like S9): **contemporaneous
ρ=+0.154** (n=2,789), **kalshi-leads ρ=−0.003**, **polymarket-leads ρ=−0.028** (n=2,774 each),
215 ≥1¢ moves (max 9¢ either venue). **FOMC resolve/roll-off (shock proxy) events in window:
0** — Kalshi's listed meetings are Jul/Sep/Oct 2026 and none has occurred inside the window,
so every tick so far is book noise, not an information shock. This is a **noise-floor
characterization, NOT a lead-lag verdict** (no CI, no DEAD/ALIVE call — dishonest with zero
shocks, per L28's "verify the signal is observable before building verdict machinery"). The
CPI leg (`tape/polymarket_cpi_pairs/`, 154 records) is `synthetic` on the Kalshi side and
deliberately **excluded** from the real-ask correlation (Hard Rule #3), counted for
provenance only. Same status as S9's first cut: re-run when a real FOMC decision lands inside
the collected window (July 2026 meeting is nearest). See
`findings/2026-07-12-polymarket-macro-leadlag-s17-firstcut.md`.

**Update 2026-07-13 (Q13): S14 flips idea → data-collecting — the project's FIRST non-DEAD
candidate, but PROXY-POSITIVE, not proven (verifier CONFIRMED-WITH-CAVEAT).** Q13 became
eligible (`tape/crypto_hourly/` crossed the day threshold). `scripts/s14_ladder_fillsim.py`
(read-only, 21 offline tests, injected fetcher — no network) posts a resting short-YES maker
offer at every member's `yes_ask` (real_ask) at the earliest capture of each settled BTC/ETH
hourly ladder (mean **131.5 members**, MECE, exactly one strike settles YES — a genuine strike
ladder; `sports_pairs` was correctly excluded as a 2–3-outcome moneyline, structurally not a
ladder). Fill proxy = the cached Kalshi hourly candlestick `max(high) ≥ posted_ask AND
volume > 0` (the seller mirror of S13's resting-bid rule); premium net of the maker fee from
`core.pricing` (L18); payout \$1 iff the `broker_truth` winner was among filled strikes.
Block-bootstrap by event-hour (`core.bootstrap.block_bootstrap`, n_boot=10,000, **n=300**):
mean **+\$0.0925, 95% CI [+\$0.0630, +\$0.1231]**, **`clears_tick_magnitude` CLEARS** (~6× the
1¢ tick), 72.0% events positive; by series KXBTC +\$0.150 / KXETH +\$0.035; coarser units
(by-day [+0.068,+0.119], by-day×symbol [+0.055,+0.130]) both still clear zero and the magnitude
gate. **Three caveats cap the verdict to proxy-positive, not proven:** (1) the "underwrite the
whole ladder" gate term is **\$0** — complete-fill rate 0.0%, so the result is path-dependent
partial premium net of the near-certain \$1 winner loss (winner filled 96.7%, near-money 95.8%,
wings 2.5%); (2) L30 fee-annihilation deletes ~30.9% of the nominal overround (1¢-floor asks net
\$0 after the flat 1¢ maker fee) by construction; (3) the candlestick proxy ignores queue
position — **78% of the \$0.093 edge (\$0.072) comes from sub-100-contract-volume income legs**;
strip the income leg and it is −\$0.51 to −\$0.97. It survives a modest haircut (vol≥50 still
+\$0.026 [+0.004,+0.049], filled legs carry median 1,047 contracts) but dies under an aggressive
one or under the unmodeled fill↔winner adverse-selection correlation. **Remaining binding gate:
a queue-aware L2/depth fill-sim** (over `tape/orderbook_depth/`, short-YES queue read off the
mirror `no_bids` side, 6 days crypto-covered) — same open-fill-sim shape as S11's gate.
**Still 0 proven edges** — S14 is the first candidate NOT to die on its first real cut, but a
proxy-positive candidate is a forward gate, not a proven fillable edge; the bar has not moved.
Lessons L39 (small-net-of-two-large-legs candlestick fill proxy is biased UP; per-leg volume
gate necessary-but-insufficient; decompose the edge as a fraction of the thinnest income legs
before claiming fillability). Full writeup:
`findings/2026-07-13-ladder-underwriting-s14-firstcut.md`.

**Update 2026-07-13 (Q21 idea-gen round): one survivor registered — S19; three candidates killed at idea stage.** The Q21 replenishment round proposed 4 falsifiable candidates; the `verifier` agent (adversarial, two-agent rule) reviewed each against its nearest dead cousin before registration. **S19 — elevated-wing stale-ask maker fade (SURVIVED, idea):** rest a maker short-YES on the stale far-OTM `wing_elevated` members Q20 documented (`findings/2026-07-13-btc-ladder-overround-anatomy-q20.md`; yes_ask 0.20–0.67 with yes_bid=0) and hold to settlement — the maker side of the tail-fade that S10's verdict + L26 explicitly left UNTESTED (a taker short there has no fillable price per L26, but a short-YES *offer* at 0.40 is a real price whose fill rate/toxicity is empirical, so it is not structurally pre-dead like S10). Registered with three mandatory tightenings the verifier required: (1) the binding fill gate is the **queue-aware `orderbook_depth` `no_bids` fill-sim, not the candlestick-print proxy** — Q20 showed 166–503 contracts already rest at these wings, so a new offer joins the back of that queue and an L39 candle-print would overstate the fill; (2) P&L must be **conditioned on the fill↔settlement adverse-selection correlation** (a far-OTM YES is lifted mainly when spot rushes the strike — the rare fills are toxic toward settling YES against the short); (3) an L27 magnitude gate on any CI, labeled a cheap L26-closer, expected DEAD, not a promising edge. Queue item Q23. **Three killed at idea stage** (recorded here for provenance so a future round doesn't re-spend a milestone): a **sports-moneyline overround-underwriting** maker-short (KILLED — the +21.3¢ mean overround is an L31 wide-one-sided-wing artifact: median 5¢, tight two-sided games only 3.7¢, which the flat 1¢ maker fee eats — S13/L30 territory — and a thinner-legged duplicate of S14's already-open queue gate; both verifier passes reproduced the 3.7¢ tight-two-sided number); a **cross-venue held-to-settlement box** Kalshi+Polymarket (KILLED — Polymarket's NO ask isn't persisted in tape, only the YES best_ask/bid, and the box reduces algebraically to Q19's already-queued dislocation scan whose crossings are the L31 no-real-size artifact; "held-to-settlement escapes staleness" is unsound because the killer is un-fillability, not convergence); and a **post-release stale-ladder fade** on econ prints (KILLED — Kalshi closes its CPI/econ markets ~5 min BEFORE the scheduled release, `close_time` 12:25Z vs the 12:30Z print, so the post-release fill window is structurally empty, same death class as S10). Still 0 proven edges — this restocks the hypothesis pipe with one idea-stage candidate; the bar has not moved. Lesson candidates for a future distiller pass: (a) a "held-to-settlement box" and a "convergence dislocation" over the same two real quotes are the same locked pair and die to the same nominal-quote / no-real-size artifact — reframing the exit does not manufacture fillability; (b) before proposing any post-release / post-settlement fade on a Kalshi event market, read `close_time` from the tape first — Kalshi closes data-driven markets minutes before the scheduled release (L28-family: verify the window is observable before building the probe).

**Update 2026-07-13 (S20 sprint): premise DEAD, S20 CLOSED as a one-shot; H1 emitted as Q24.**
S20 is a research sprint (mine top-PnL Polymarket wallets for transferable strategy shapes), not
a tradeable Kalshi strategy — registered `dead ✗` for the record, the same way a dead idea-stage
candidate stays recorded. Full pipeline: /first-principles (GO) → /council (CONDITIONAL 3-0,
conditions C1–C5 honored) → a pre-registration written before any wallet data was pulled
(`findings/2026-07-13-polymarket-wallet-forensics-s20-prereg.md`) → the sprint
(`scripts/s20_wallet_forensics.py`, re-pullable from public APIs) → peer review with an
independent `verifier` full recomputation from raw fills. Of 50 leaderboard wallets, 37 evaluable;
exactly **1 formally survives BH-FDR at q=0.10 and Result 2 discredits it** → **0 credible skilled
wallets**. The survivor's significance is a **degenerate bootstrap** (all 8 of its resample
clusters resolved the same direction, so the one-sided p is mechanically 0 — L41) atop a
resolution-conditioning bias that truncates the unresolved catastrophic tail. The rest of the
leaderboard is rewards-subsidized MMs (31/37 `passive-maker`, whose Kalshi analogs S6/S13/S19 are
already DEAD) and lottery winners with flat-to-negative per-trade edge (16/37 negative). **"Copy
the Polymarket whales" is structurally void** — closed with data so no future loop re-chases it.
**Live output = H1**, filed as `LOOP-QUEUE.md` **Q24** (mirroring how S19's registration filed
Q23): maker-side rich-ASK selling on sports/event longshots — the direct mirror of the S7c PROVED
rich-ask finding that S13's bid-side test never covered; **its evidentiary basis is S7c alone**
(the Polymarket survivor contributes nothing after the degeneracy finding). Q24's binding probe
requirements: queue-aware `orderbook_depth` fill-sim (L39), explicit negative-skew accounting (the
sold-longshot-wins leg modeled, not conditioned away — the exact Result 2 artifact), the
≥1-losing-cluster floor (L41), and a favorite-longshot-bias citation TODO before it becomes
eligible. H1/S14 are the same short-the-overpriced-tail factor family — factor cap recorded. Two
first-draft dossier errors were caught pre-merge by the independent verifier (zero-fill count 1→6;
a −27.8¢/n=3,248 example mis-attributed to the #1 wallet, actually a rank-47 sports wallet — the
pt1 provenance-detachment failure, L42). All numbers tagged `polymarket_onchain`, zero Kalshi-edge
evidence. Lessons L41 (degenerate bootstrap) / L42 (trace-to-source-row). Still 0 proven edges —
S20 removes a candidate-generation avenue and adds one probe-able Kalshi question; the bar has not
moved. See `findings/2026-07-13-polymarket-wallet-forensics-s20-dossier.md`.

**Update 2026-07-13 (Q24): S21 registered dead ✗ — the S7-maker ASK side, DEAD by data-adequacy
(verifier-CONFIRMED).** S21 is the direct mirror S7c/S13 never covered: rest the S7c-PROVEN-rich
ask on sports longshots (short YES / buy-NO at `1−ask`) and harvest the +2.35¢ overpricing retail
takers pay pregame. The edge-at-quote is not in dispute — S7c proved it; the binding question is
FILLS (you join the BACK of the incumbent maker queue). An edge-prober built a queue-aware
`orderbook_depth` `no_bids` fill-sim (L39, NOT a candlestick print) and an independent verifier
returned CONFIRMED-WITH-CAVEAT (the caveat a cosmetic 80/80→81/81 script literal, fixed
separately — the real number is **81/81**). **The mandated join is 0/81 joinable (0.00%)** at
`fair_prob ≤ 0.20` (0/83 for the `yes_ask ≤ 0.20` proxy): `sports_clv` fair anchors cover kickoffs
≤07-03 while sports `orderbook_depth` began ≥07-07, so every fair-anchored game had already
settled before the depth tape began — zero event- AND outcome-ticker overlap, and because the
calendar date is embedded in the ticker string the non-overlap is structural (the verifier
reproduced 0 by bypassing the probe's own join code). This is **L9 recurring at the collector
level** (L43): two datasets a probe needs were collected in disjoint windows, so the join is
permanently empty. Fill rate 0.00%, no testable CI (n_units=0), L27 n/a, L41 admissibility
correctly False on the empty population. **The death is a depth-queue TIMING gap, not a winner
gap:** settlement (`tape/sports_history_s7/worldcup2026.jsonl`, `broker_truth`, L44) was ADEQUATE
(81/81 settled, 8/81=9.88% YES) and the sold-longshot-WINS negative-skew leg is fully modeled
(`premium−1−fee`≈−0.86 settle-YES; flat $0.01 maker fee via `core.pricing`, L18/L30) — never
conditioned away (Q24 gate #2 / L41). **Steelman (no rescue):** `sports_pairs` ask≤0.20 longshots
that DO overlap depth → 346/652 (53%) carry a queue, MEDIAN queue-ahead **485 contracts** (you
rest behind a real incumbent — confirms Q24's binding-risk thesis), but full-sim-eligible = only
**3 markets** << the 10-game floor (S19's 2-event-hour data-adequacy family); verifier confirmed
`sports_history/` NBA and `sports_pairs`-native result/volume paths also yield 0. Prices tagged
`real_ask` (asks/volume) · `real_bid` (queue) · `broker_truth` (settlement) · `synthetic`
(fair_prob); bootstrap by GAME (L6). **Verdict: DEAD by data-adequacy — NOT a CI falsification.**
The edge-at-quote stays S7c-proven-rich; only the maker FILL question is unanswered, and it is
untested/unmeasurable on current tape, NOT falsified — re-testable only on a fresh collection where
`sports_clv` and `orderbook_depth` run concurrently over the same *upcoming* games (a re-collected
WC-final/future window). Same short-the-overpriced-tail factor family as S14 (factor cap recorded).
This closes the S7 family (taker S7c DEAD, maker-bid S13 DEAD, maker-ask S21 DEAD-by-data-adequacy).
Same terminal shape as S9/S10's data-adequacy DEADs — **still 0 proven edges; the bar has not
moved.** Lessons L43 (collector-alignment recurrence of L9) / L44 (`worldcup2026.jsonl` offline
sports executed-volume source). See `findings/2026-07-13-q24-sports-longshot-maker-fillsim-verdict.md`
and `kb/quant-finance/favorite-longshot-bias.md`.

**Update 2026-07-14 (Q21 idea-gen round): three survivors registered — S22, S23, S24; zero killed at idea stage.** The Q21 replenishment round (queue drained: Q0-Q25 DONE/DEAD except time-gated Q19) proposed three falsifiable candidates; an independent `verifier` pass (two-agent rule) re-derived every data-source premise from the tape and returned **REGISTER on all three**, each with mandatory tightenings folded into its queue item and note below. The round's structural unlock, verifier-confirmed against `collection/sports_history.py::fetch_kalshi_settled`: **S21 died by L43/L9 (disjoint collector windows — `sports_clv` fair anchors kicked off ≤07-03, `orderbook_depth` began ≥07-07, join 0/81), but S22/S23 replace the fair-anchor leg with realized settlement pulled ex-post from Kalshi's free settled-markets endpoint over the SAME depth-window games (within the 60-day L11 retention), so the disjoint-window death does not transfer** — the join is non-empty by construction. Diversity floor (rule 2) satisfied by **S22**, drawn from the Q25 depth-anatomy scan + a not-yet-distilled paper (Cont, Kukanov & Stoikov 2014, order-flow imbalance — distilled this round into `kb/quant-finance/order-flow-imbalance.md`), neither a dead-verdict inversion nor an S11/S12/S14/S17 family. Still 0 proven edges — this restocks the hypothesis pipe with three idea-stage candidates; the bar has not moved. Queue items Q26/Q27/Q28. Lesson candidate L50 (settlement-leg-over-own-window as the L43 fix).

**S22 — OFI / depth-imbalance settlement predictor (idea, 2026-07-14).** Mechanism: resting L2 book-imbalance (size on the `yes_bids` ladder vs the `no_bids` ladder) carries information that leads the mid and predicts the settlement outcome; the losing counterparty is retail who trade the displayed BBO/mid without reading depth. Tested on exactly the two-sided, low-frozen, high-turnover sports cells Q25 flagged (KBO 8.35%/33%-frozen, NPB 6.92%/29%, WNBA 11.06%, MLB 7.62%, UCL 8.56%) where fills are plausible and books are two-sided (any-empty 0-1%) — NOT the stale one-sided crypto wings. Data (already-collected / free): `tape/orderbook_depth/` for the imbalance signal; settlement from Kalshi's free settled-markets endpoint (`fetch_kalshi_settled`, L11 retention) over the same games, or the tape's own post_close convergence. Survives its dead cousins: vs S9 (lead-lag DEAD by cadence) — S9 died because a minutes-scale cross-venue event resolved between hourly snapshots, whereas S22 makes a single last-pre-close cross-sectional prediction of an hours-scale win-probability, so hourly cadence is not disqualifying; vs S6/S19 — this is a taker directional trade, NOT spread capture (no flat-1¢-fee-vs-spread death) and NOT a stale wing (these cells churn 7-11%); vs S21 — settlement over the depth window is non-empty (no L43 disjoint-window death). Verifier-mandated tightenings (do NOT weaken): (1) verify settlement-join non-emptiness (≥10 games each with a genuine pre-close `ttc>0` last snapshot AND a retrieved `result`) BEFORE any CI, pulling the settled API while the 07-14 cohort is still retained; (2) the L28-style calibration precheck (imbalance beats mid at all) is a hard gate, not a footnote; (3) the fillable object is a taker lift at `best_yes_ask`/`best_no_ask`, fee at the taker 0.07 rate (`core.pricing`) — the edge must clear the full taker round-trip; (4) block-bootstrap by GAME (L6), route the CI through `core.bootstrap.bootstrap_verdict_admissible` (≥10 units, ≥1 opposing-sign cluster) AND `clears_tick_magnitude` (L27/L41) — a CI failing either is not-a-verdict. Honest expectation: uncertain — a genuinely novel signal that could well be washed out by hourly cadence; the calibration precheck decides cheaply. Queue item Q26.

**S23 — Favorite-side settlement-underpricing maker (idea, 2026-07-14).** Mechanism: the favorite-longshot bias (`kb/quant-finance/favorite-longshot-bias.md`) leaves favorites underbet; rest a maker BID to buy the favorite YES (fair ≥ ~0.65) in Q25's high-turnover two-sided sports cells and collect $1 on settlement when the favorite wins; the losing counterparty is retail longshot-lovers who overbet the underdog and leave the favorite cheap. Key design choice — the fair test is REALIZED SETTLEMENT, not a devig anchor, so it needs NO `sports_clv` tape and NO odds-api key. Data (already-collected / free): `tape/orderbook_depth/` (`yes_bids` queue for the fill-sim) + Kalshi free settled endpoint (outcome). Survives its dead cousins: vs S13 (maker bid at devig-fair−1¢, POOLED across outcomes → null, fee ate the pooled margin) — isolates the favorite side where Theme 2 predicts the largest underpricing and tests against realized settlement; vs S21 (rest the rich longshot ASK → DEAD by data-adequacy, `sports_clv` anchors settled before depth, L43) — S21 was never DECIDED (0/81 joinable, not a CI falsification), and S23 drops the `sports_clv` dependency (settlement overlaps the depth window), so it is a testable instance of an undecided question, on a genuinely different resting side (favorite `yes_bids` bid vs longshot `no_bids`-mirror offer); vs overround (S1/S7) — it is a maker, never pays the ask. Verifier-mandated tightenings: (1) record it in the SAME factor slot as S14/S21 (short-the-overpriced-tail / favorite-longshot — one Hard-Rule-#6 ρ allocation, not diversification); (2) model the fill↔settlement adverse-selection correlation — a resting favorite-bid fills disproportionately when an informed seller dumps the favorite (about to lose), so the catastrophic favorite-loses leg MUST be in the P&L, never conditioned away (L41, Q24 gate-2); (3) queue-aware `orderbook_depth` fill-sim, NOT a candlestick print (L39 — S13's 94.1% candle-fill was the biased proxy; the queue reality is S19 0.45% / Q24 median 485-ahead), kill if fill rate ≤ the S19 0.45% floor; (4) settlement-join non-empty (≥10 games) before CI, flat 1¢ maker fee (`core.pricing`, L30), bootstrap by GAME through `bootstrap_verdict_admissible` + `clears_tick_magnitude`. Honest expectation: probably DEAD (the bias is attenuated on modern exchanges and rarely clears fees — Theme 2 caveat), but sound and testable, and closes an undecided branch of the S13/S21 family. Queue item Q27.

**S24 — Near-close hourly-return overreaction fade (idea, 2026-07-14).** Mechanism (Theme 7 behavioral, De Bondt-Thaler/Tetlock): an hourly-scale near-close mid jump in a two-sided sports book (retail overreacting to the last salient in-game event) partially reverses over the next hour; fade the jump; the losing counterparty is the overreacting retail flow. Distinct from S18 (elections/polls, idea-stage) — a different category and horizon. Data (already-collected): `tape/orderbook_depth/` price paths in the Q25 high-turnover cells. Survives its dead cousin: vs S9 (cadence) — it tests a DIFFERENT object, within-market hour-to-hour return autocorrelation (do jumps continue or revert?), which the hourly tape genuinely can answer; the honest downgrade to "hour-to-hour reversal only" (a same-hour jump-and-revert is invisible at hourly cadence) is a weaker-but-testable claim that clears the idea-stage bar. Verifier-mandated tightenings — the first is load-bearing for distinctness: (1) the exit MUST be explicitly specified and the CI MUST charge the full realized round-trip (both taker legs: 2× 0.07 fee + 2× half-spread ≈ a 6-8¢ hurdle on a ~3.7¢-overround two-sided book) — AND if the only profitable exit turns out to be hold-to-settlement, S24 collapses into S22's mechanism (a directional settlement bet keyed on a recent jump) and MUST be routed to S22's slot, not double-counted; (2) the ≥X¢ jump threshold must clear the frozen-BBO/bid-ask-bounce noise floor (Q25: 58-94% frozen — a jump must be a real mid move, not a one-tick flicker); (3) bootstrap by distinct GAME (L6), ≥10 games — verify the jump population reaches the floor (Q25's sub-hour buckets are mostly `insufficient`); (4) momentum-vs-reversal is a sign question so the opposing-sign cluster (L41) is NOT guaranteed — assert `bootstrap_verdict_admissible` admissible and `clears_tick_magnitude`. Honest expectation: the weakest of the three; DEAD-by-round-trip is a likely outcome, but it's a sound, novel, testable behavioral question. Queue item Q28.
