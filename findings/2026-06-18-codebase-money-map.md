# Codebase money-map — what could make money across the Kalshi repos

**Date:** 2026-06-18 · **Method:** dynamic workflow `kalshi-money-map` (27 agents, 22
candidates surveyed + adversarially verified at the real-fillable-ask bar, then synthesized).
**Verdict tally:** 0 proven edges · 4 dead · 6 infra-only · 12 needs-data.
Run artifact: workflow `wf_53c67e24-46a`. Every candidate was cross-checked against the
prime directive (real asks, not synthetic prices).

## The honest bottom line

> **No clean dollar edge is proven at real fillable asks anywhere across the four
> codebases.** Every positive headline is synthetic or midpoint. The only thing ever
> filled with real money — the KXHIGH weather ensemble (live n=49) — printed **−$0.14/trade**
> and lost pt1 ~9.6%, killed by a structural ~3–5¢ bracket **overround** (consistent with
> `kb/kalshi-api/03-fees-and-breakeven.md`). The directional *signal* is real (SIG fails to
> correct a cold bias; r=−0.152, p=2e-5); the *dollar* edge is not, because overround eats it.

The cheapest honest path to a first real-ask number is **not a new model**. It is:
1. **Lift the real-ask + actuals-gate infra** from `kalshi.1` and the invariant engine from `arb-bot(-v2)`.
2. **Start archiving forward orderbook tape** Kalshi never keeps (the only moat that compounds with calendar time).
3. **Run two near-free, no-capital probes:** the FOMC×ZQ single-meeting basis replay and the longshot-fade real-ask calibration on already-recovered tape.

**Fund infra + data capture + those two probes. Fund zero weather-model capital until a bootstrapped real-ask CI clears zero.**

## Codebase one-liners

| repo | what it is | proven edges | candidates |
|---|---|---|---|
| `arb-bot` | Most-developed pt2 weather-arb bot; built, dry-run-clean, **PRE-LIVE with a unanimous NO-GO** (no edge at real asks). | "3" (all synthetic) | 7 |
| `arb-bot-v2` | Disciplined Tier-2 edge-rediscovery harness; Phase-0 built, **Phase-1 backtest aborted Day-1**. Zero scored trades. | 0 | 5 |
| `kalshi.1` | Execution-free Phase-0 research harness: 3-source actuals validation + **forward full-depth orderbook capture**. No strategy code by design. | 0 | 5 |
| `kalshi.ibkr` | KB+scaffold for a Kalshi+IBKR multi-edge effort (FOMC×ZQ basis, cross-strike latency, etc.). Zero captured data, nothing tested at real prices. | 0 | 5 |

## Ranked opportunities (only what a skeptic would still fund)

### #1 — Real-ask substrate: forward tape + 3-source actuals gate + bid-only ask primitive  `[kalshi.1]`
*verdict: infra_only-but-fund · conf 0.9 · effort low-med · enabling*
The substrate every future edge is scored against. `normalize.py` derives the REAL taker
ask (`yes_ask = 1 − best_no_bid`), `v1_actuals.py` gates corrupted settlement data (the
failure that sank a prior project), `capture_orderbooks.py` archives intraday depth Kalshi
does **not** archive and nobody can backfill. A captured 2026-06-06 snapshot already makes
the ~5.2¢ mean overround (the pt1 killer) directly visible instead of silently absorbed.
**Binding test:** cron capture at one pinned decision time (e.g. 16:00 ET prior-day) for
30–60 days, join to settled actuals, confirm Kalshi truly cannot backfill intraday depth
(one docs/API check). Assert `best_yes_ask == round(1 − best_no_bid, 4)` and stamp every
ask `real_ask`.
**Next step:** lift `normalize.py` + source-tag wrapper + `v1_actuals.py` + `capture_orderbooks.py`
into `kalshi.headless` verbatim; wire the source-tag invariant; cron the capture **today**.

### #2 — Longshot-fade real-ask calibration on Kalshi weather brackets  `[arb-bot-v2 recovered tape]`
*verdict: needs_data · conf 0.45 · effort med · modest-at-best, plausibly zero*
Three independent peer-reviewed methodologies point the same way: Kalshi weather longshots
overpriced, favorites underpriced, concentrating in the final 48h (ties to
`kb/quant-finance/00-overview.md` Theme 2). Data largely exists on the 24GB recovered tape
(1,056 settled brackets). **Binding test:** replay deltas → reconstruct `yes_ask/no_ask` per
KXHIGH bracket at T-24h → normalize by `bracket_sum` → bin by 5¢ → regress realized win-rate
vs implied prob → net P&L of a maker-side NO-on-longshot rule **after** 2¢ spread + maker fee
+ a fill-probability haircut. **Pass only if bootstrap CI strictly > 0.** Expect it to straddle
or sit below zero — but it is near-free and falsifies a whole bias-chasing family if it fails.

### #3 — FOMC × CME ZQ cross-venue basis — single-meeting replay  `[kalshi.ibkr]`
*verdict: needs_data · conf 0.4 · effort med · modest (capped ~8 events/yr)*
Clean prob-to-prob arithmetic (FEDS 2026-010 month-average identity) with **no per-bracket
weather overround** — the exact structural killer that ate pt1 is absent (ties to Theme 6).
Honest caveat: it is **not a hedge** but a frozen directional pre-position (Kalshi halts
1:55pm, settles 2:05pm) with unbounded per-event downside, ~8 events/year (capital idle 95%
of the calendar). **Binding test:** pull ONE in-range FOMC; for T-60..T-10 pre-halt compute
basis using REAL Kalshi `yes_ask/no_ask` (not midpoint) minus ZQ-implied p_hold, subtract
taker fee + commission + 1 ZQ tick slippage, mark to 2:05pm settlement. If net ≤ 0¢, dead.
Screen the EFFR look-ahead leak flagged in peer review.

### #4 — K3 cross-strike monotonicity staleness — 1h calibration run  `[kalshi.ibkr]`
*verdict: needs_data · conf 0.3 · effort low · marginal-to-modest*
Cheapest Kalshi-only, single-venue, ~$680-sufficient probe. The pilot instrument is built
and unit-tested (WS book reconstruction, seq reconciliation, self-inversion logging) but has
never been pointed at the world. **Binding test:** `--discover-only`, then a 1h KXBTC
`--calibrate` to capture the artifact-floor null (NTP-skew p95, reconciliation transients).
If calibration noise swamps plausible MM lag, K3 dies for ~$0. **First verify** the public WS
exposes per-strike L1 ask deltas at all (not mids-only) — if mids-only it dies on contact.
Taker-by-construction, so the ~8¢ round-trip floor is binding; likely a fast, cheap kill.

### #5 — FEx wing-strike fat-tail mispricing — VPS tape probe  `[arb-bot H1]`
*verdict: needs_data · conf 0.25 · effort high · modest-if-real*
Plausible: ForecastEx settles on Weather Underground (5-min MA of 1-min ASOS, smooths spikes)
while IBGI presumably quotes Gaussian-on-NBM, and temp tails are genuinely fat (GPD ξ>0)
against a retail crowd with a low $0.01 fee. **Hard blocker:** the FEx tape was silently never
persisted (archiver bug #24) and FEx execution code doesn't exist in `arb-bot`. **Unrunnable
until the tape exists** — gate everything behind tape persistence.

## Combos (stronger assembled than alone)

- **Canonical real-ask substrate** = `kalshi.1 normalize.py` (real taker-ask) × `v1_actuals.py`
  (3-source actuals gate) × `capture_orderbooks.py` (un-backfillable forward tape) ×
  `pt2/v3_invariants.py` (10-hard-rule contamination guard) × `pricing.py` (the only sanctioned
  `yes_ask/bracket_sum` site) × the recovered 24GB tape (1,056 settled brackets). Build this
  **once** in `kalshi.headless` and every candidate gets scored honestly on top of it. **This is
  the project's first build.**
- **Rehabilitate weather, honestly** = the real directional signal (n=49, WR 61.9%) × `kalshi.ibkr`
  `fills.py` no-mid adverse-fill discipline (short@bid/long@ask) × forward tape × the summer-2026
  paper sample (test seasonal mean-reversion vs regime-shift on the subset where synthetic edge
  was strongest, +$0.165). A **$0-capital paper test**. If the forward summer real-ask CI still
  straddles zero, the entire weather family is dead and the project pivots to non-weather.

## Data to start collecting TODAY (edges live in data nobody else keeps)

1. **Forward full-depth Kalshi orderbook** at a pinned decision time (e.g. 16:00 ET prior-day),
   cron'd 15–30min, all weather-city ladders. Un-backfillable; the only moat that compounds with
   calendar time. Stamp every derived ask `real_ask`. (`capture_orderbooks.py`, honest completeness.)
2. **FEx (ForecastEx) L1 bid/ask tape** — fix archiver #24 FIRST (it has persisted nothing since
   May 1, invalidating every recent FEx claim). Without it, all cross-venue/FEx candidates are unrunnable.
3. **Per-(city,date) paired NWS-CLI vs actual Weather-Underground readings** (not free-tier ASOS,
   which == NCEI) — required to honestly price any Kalshi-NWS vs FEx-WU cross-source thesis.
4. **Open-Meteo single-run forecast tape** with ms-precision `fetch_ts` at each new `model_run_init_ts`,
   per city/model. There is **zero forecast tape anywhere** — blocks the latency edge, the settle-time
   pin, and any forward ensemble-vs-market study. Most-reused missing input.
5. **CME ZQ tick + Kalshi KXFEDDECISION orderbook** around every FOMC (Databento free $125 credit +
   Predexon free tier). ~8 events/year — every meeting missed is unrecoverable.
6. **3-source reconciled daily actuals** (NWS CLI / IEM METAR / NCEI GHCN) rolling via `v1_actuals.py` —
   keeps the settlement-label gate green so no future backtest is an actuals bug masquerading as edge.

## Dead — do not re-mine (recorded so we never pay to relearn)

- **KXHIGH 4-model ensemble as deployed.** Real-money n=49 = −$0.14/trade; pt1 −9.6%. Paper real-ask
  −$0.021 [−0.082,+0.041] vs synthetic +$0.074 [+0.044,+0.104] — non-overlapping CIs. NO-side breakeven
  needs WR≥65% vs observed 61.9%; ~5.4¢ overround absorbs the gap. *Only* the forward-summer paper variant is open.
- **Model-divergence Kelly modifier (1.12×).** A positive scalar can't create sign; it amplifies a
  confirmed-negative base. Evidence is in-sample, 6 cities, no OOS, no multiple-comparison correction.
- **Kalshi LIP maker-rebate harvest.** Never built; mischaracterized (LIP rewards resting at BBO, not a
  flipped taker); sub-$1 payouts vs dedicated farmers; inherits the adverse-selection overround. Negative-carry lottery.
- **arb-bot-v2 settle-time microstructure pin (T-3h).** Unbuildable as framed: the ensemble-implied leg
  needs a forecast tape that is zero rows; delta rows dropped depth. Survives only as a descriptive timing probe.
- **K1' as a dual-venue "hedge."** Category error — restates a flaw the repo already flags. The K1 *edge*
  is alive (ranked #3); only the "hedge" label is dead. Size as a directional micro-position, never a basis lock.
- **arb-bot-v2 NWS/WU basis as a settle-source edge.** The +0.77F prior was unsourced; same-station data shows
  ASOS==NCEI to ρ=0.99999. A sub-1F bias is under the overround. Station-geography artifact, not methodology edge.

## How this feeds the project

The ranked + combos list seeds `kb/strategies/` (each becomes a falsifiable candidate with a
binding test). The "data to collect" list is the immediate build queue. The "dead" list is a
permanent do-not-re-mine ledger. The substrate combo (#1) is the project's first implementation
task. See `kb/strategies/00-index.md`.
