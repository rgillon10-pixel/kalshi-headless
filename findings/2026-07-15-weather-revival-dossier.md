# Weather revival dossier — full mining of prior repos (2026-07-15)

**Trigger:** Ryan directed a serious re-look at weather. This dossier synthesizes a
four-agent mining pass over `arb-bot` (pt2), `arb-bot-v2`, `kalshi.1`, `kalshi.ibkr`,
plus this repo's own S1/S5 verdicts, and a live API check of today's weather surface.

**Provenance:** every claim below cites the source file in the originating repo.
Numbers inherited from old repos keep their original price-source caveats.

---

## 1. Why weather "died" — the honest ledger

Weather was never killed for lack of signal. Every attempt found real signal;
every attempt died on **execution economics at taker prices**:

| Attempt | Signal | Dollar verdict | Price basis | Window |
|---|---|---|---|---|
| pt1 live (kalshi-bot, Apr 2026) | WR 61.9% live (n=49) | **−$0.14/trade, −9.6% bankroll** | real fills | Apr 14–18, live |
| pt1 walk-forward | +$0.138/trade CI [+0.131,+0.145] (n=14,860) | fictional forward | **synthetic raw_prob** | 2020–2026 |
| S1 longshot-fade (this repo) | bias real, −1.4¢..−7¢ on longshots | +$0.00448/trade CI [−$0.005, +$0.013] ⊅ >0 | real_ask, **maker-NO** | 22d spring, 8 cities |
| S5 EMOS rehab (this repo) | CRPS −7.86% (calibration works) | −$0.028/trade CI [−$0.063, +$0.008] ⊅ >0 | real_ask, taker | 22d spring, 8 cities |
| v2 NWS×WU basis | none — prior was unsourced | ABORT day 1 | n/a | n/a |

Killers, quantified:
- **Bracket overround ≈ 9.84¢ mean (median 10¢)** across the 6-bracket ladder at real asks
  (`kalshi.headless/findings/2026-06-18-weather-rehab-s5.md`).
- **Taker fee** `ceil(0.07·p·(1−p)·n)` — ~2¢ at mid-prices, 20% of premium on 5¢ longshots
  (`kb/kalshi-api/03-fees-and-breakeven.md`).
- pt1 mechanism: NO bets average ~$0.65 ask → breakeven WR ≥65%; live WR 61.9%
  (`arb-bot/data/audits/golive_2026-05-05/03_edge.md`).

**What the DEAD verdict did NOT test** (stated in the findings themselves):
1. **Summer/high-convective regime** — the QF literature note expects edge to concentrate
   there; all real-ask tests ran on a 22-day **spring** tape (2026-04-16→05-07).
2. **Maker-side economics beyond S1's single variant** — maker fee 0.0175 (4× cheaper),
   earns the spread instead of paying the overround. S1's maker-NO CI lower bound was
   −$0.005 — a near-miss, on spring data, with no forecast input.
3. **The new hourly market surface** (see §3) — likely postdates all prior work.
4. Kalshi **Liquidity Incentive Program maker-rebate windows** (arb-bot
   `data/research/pricing_microstructure_2026-04-29.md` H2, never run).

## 2. Surviving assets (verified on disk 2026-07-15)

**Tape (the moat):**
- `arb-bot-v2/data/tape_replica/orderbook_archive_recovered.db` — **24 GB**, 103.0M
  orderbook events (Kalshi 101.8M / ForecastEx 1.3M), 2,112 settlements, 22 trading
  days 2026-04-16→2026-05-07, 8 cities, full L2. VERIFIED present.
  Caveats: `settlements.settled_at` is cron-time not close-time (DIRTY);
  arb-bot's VPS twin had `size_total` NULL — depth reconstructed from deltas.
- The VPS weather tape (32G, Apr 16→Jul 3) was **deleted** in the 2026-07-03 teardown
  (`LOOP-QUEUE.md:1370`). Forward collection stopped that day. Nothing collects weather now.

**Research corpus:** `arb-bot/data/backtest_cache.db` (230 MB) —
`historical_forecasts` 227,725 rows (2020-10→2026-04, 20 cities, 5 models, GEFS-free);
`daily_weather_actuals` 46,160 rows (2020→2026-04, high+low, NCEI + IEM-CLI calendar-day);
`historical_candles` 994,155 rows of real Kalshi bid/ask closes (2022→2026);
`historical_markets` 35,082 settled markets. Plus
`arb-bot-v2/data/external/paired_2025/` — full-year-2025 ASOS×NCEI paired calibration.

**Code (clean, carried forward or portable):**
- Station truth: `arb-bot/shared/config/cities.py` (20-city TRIPLE map: NCEI USW /
  Kalshi CLI ICAO / ForecastEx-WU station; Houston 14% mismatch unresolved — re-verify),
  and this repo's `config/cities.yaml` + `validation/resolve_stations.py`.
- Forecasts: `arb-bot-v2/shared/weather/ensemble.py` (4 free ensemble models, n≥4 guard,
  slugs verified live 2026-05-11), `arb-bot/dev/backtest/open_meteo_single_runs.py`
  (issued-at-aware, 6 deterministic models), this repo's `collection/forecast_collector.py`.
- Actuals: this repo's `validation/v1_actuals.py` (3-source CLI/METAR/GHCN reconciler,
  all 20 cities ≥98.9% clean over 92 days), `arb-bot-v2/dev/data/{asos,ncei}_client.py`.
- Books: this repo's `collection/capture_orderbooks.py` (full-depth weather capture,
  derived asks = 1−opposite_bid, bitemporal manifest) — **not wired into hourly_pass**.
- Economics: this repo's `core/execution.py` (exact quadratic fee, top-level haircut,
  FILL_CAVEAT stamping); `arb-bot/dev/audit/settlement_cross_check.py` (canonical
  settlement rule parser).

## 3. The 2026-07-15 live surface (fresh API check)

- 288 Climate-and-Weather series exist. Daily-high ladders alive with real depth
  (KXHIGHNY 26JUL15: 500+ contracts bid at 92¢ on T97, ~$40k resting at 99¢).
- **Daily highs settle on the NWS Climatological Report (Daily)** for the settlement
  station (e.g. Central Park), and the market **stays open until 04:59Z (12:59am ET)** —
  hours after the day's max is physically locked in. Kalshi's own rules warn about
  preliminary-data rounding nuances (CLI = max of 5-min running mean rounded to °F;
  METAR hourly ~:52 — `arb-bot-v2/kb/research/L5_ibkr.md` #14).
- **NEW: hourly temperature series `KXTEMPNYCH`** — one market per hour, opens ~60 min
  before the reading, settles on **The Weather Company value for coordinates KNYC**
  (e.g. "temperature at Central Park Jul 15 11 PM EDT as reported by TWC"). Sub-degree
  thresholds (T80.99 etc.). A 1-hour nowcast market settled by a queryable commercial
  API. Not covered by any prior repo's work. Liquidity unmeasured — first question.
- Note: public `/markets` endpoint no longer returns price/volume fields unauthenticated;
  orderbook endpoint still serves full depth.

## 4. Edge candidates, ranked (all must clear the real-ask CI gate)

**W-A. Summer maker-side re-test of the S1/S5 family.** The single closest-to-alive
number in the whole history is S1's maker-NO +$0.0045/trade with CI lower −$0.005, on
spring tape with no forecast input. Rerun on summer tape (collect now — it is mid-July),
maker-side, with the EMOS-calibrated ensemble from S5 as the signal. Levers stacking in
its favor: summer regime concentration + maker fee 0.0175 + earning the spread + LIP
rebate windows (H2). Needs: fresh weather L2 tape (gone — must re-collect) + forecast tape.

**W-B. KXTEMPNYCH hourly nowcast (the VPS-latency play).** Structure: 60-minute markets
on a value observable in near-real-time (KNYC ASOS 5-min obs vs TWC settlement value).
If the book lags the observation stream even by minutes, a VPS bot reacting to each
5-min METAR/mesonet update has a structural speed edge nobody prices. Prereqs:
(1) settlement-basis study — how does the TWC KNYC value map to ASOS 5-min obs
(rounding, smoothing, lag)? (2) liquidity audit of the hourly books. This is the
cleanest expression of "VPS able to place trades fast."

**W-C. Daily-high late-session convergence.** Market open until 12:59am ET; the high is
locked by early evening; settlement risk is only CLI-vs-intraday-obs rounding. Measure
on tape: when does each bracket converge to 0/100, who supplies liquidity in the
18:00–01:00 window, and is there systematic mispricing vs the obs-implied outcome in the
last hours (kalshi.1's unbuilt H3; arb-bot's `intraday_update_probe.py` found repricing
"spread across full session" — i.e. the market may be slow). Fast obs ingestion on the
VPS is the execution edge; the METAR≠CLI rounding trap is the risk to quantify
(kalshi.1's 3-source reconciler measures exactly this).

**W-D. Ladder coherence (kalshi.1 H1). TESTED-DEAD 2026-07-15** — probed same-day on
the 24GB recovered spring tape (`scripts/probe_ladder_coherence.py`, artifacts in
`reports/ladder_coherence_*`). Raw Σask<$1 states exist (1.7% of 33.5M ladder-seconds)
but ~98% die to the 6-leg fee floor and the remainder are forward-fill artifacts:
depth×duration are anti-correlated — 0 opportunities ≥10 contracts AND ≥60s (or even
≥5 contracts/≥60s, ≥20/≥10s). All "executable" runs persisted ≤1.0s. Verified mechanism:
losing legs collapse to the 1¢ floor in sub-second bursts while the winner leg's ask is
stale one beat — the Σ<$1 was never simultaneously true. Joins S1/S5 in the
execution-economics graveyard.

**W-E. Station-geography basis (CHI only).** v2's rescope: same-station NWS-vs-WU
methodology basis is dead (μ −0.0025°F, ρ 0.99999); only KORD-vs-KMDW spatial basis
survives, gated on a pre-registered intraday-σ threshold (μ/σ < 0.5 → shelf). Needs
ForecastEx access via IBKR. Park unless FEx re-enters scope.

**Anti-candidates (do not revisit):** settle-source methodology basis (v2 ABORT);
DEN station basis (σ 3.15 vs μ 0.52, F.1-final); dying-hour edge (BH-FDR negative,
29 cells); raw-ensemble taker entry (three funerals: pt1, S5, golive NO-GO).

## 5. What blocks everything: data

No weather data is being collected anywhere as of 2026-07-03. Immediate plan (§6 of
this dossier is executed as Q-items / local work):

1. **Weather L2 tape back on** — wire `capture_orderbooks.py` families
   (KXHIGH*/KXLOWT* 20 cities) + the KXTEMPNYCH hourly series into the collection
   cadence. Hourly baseline; finer cadence (≤5 min) for W-B/W-C windows needs the VPS.
2. **Forecast tape back on** — `forecast_collector.py` multi-model daily pulls
   (the scheduling HOLD was laptop-sleep-driven; VPS cron solves it — Ryan approval
   needed for deploy).
3. **Actuals tape** — continuous IEM ASOS 5-min + CLI capture for the 20 stations +
   KNYC, and a TWC-settlement-basis probe for W-B.
4. **Validation before trust** — rerun `v1_actuals.py` 3-source reconciliation over the
   new window; extend to TWC-vs-ASOS for the hourly market. No number enters kb/
   without its source tag.

Fee-structure open item from `kb/kalshi-api/03-fees-and-breakeven.md` (still unresolved):
confirm weather-series maker fee / LIP rebate schedule from live `get-series-fee-changes`
before any W-A sizing.
