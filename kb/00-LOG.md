# Running Log — kalshi.headless KB

Append-only. Newest at top. Each entry: `## YYYY-MM-DD HH:MM ET — title`,
then what happened, what it means, and links to the note/script it produced.
Dead ends stay. This is the journey; `git` is the diff.

---

## 2026-07-10 05:11 UTC — Q3 hourly collector entry point built + first live pass

Topmost eligible queue item: **Q3** was `BLOCKED(needs Q1 + Q2 built)`, and both landed this
session's prior two runs — dependency resolved, flipped to `TODO`, and it's topmost, so this
run built it: `collection/hourly_pass.py`, the single command the hourly Haiku collector
routine runs.

One pass = one `collection.sports_pairs.run()` + one `collection.crypto_hourly.run()`; during
the 09 UTC hour it also runs `scripts/anomaly_sweep.py` as a subprocess if that file exists
(Q6 isn't built yet, so today every hour is a no-op there — checked fresh every run, so Q6
needs zero additional wiring once it lands). Discipline carried over from both collectors: a
hard exception in either sub-pass degrades to an honest `{"ok": False, "error": ...}` entry
rather than crashing the whole hourly pass or silently dropping the other collector's result;
`completeness_ok` is `False` if either sub-pass raised, either sub-pass logged a
series-enumeration error, or (09 UTC only) the anomaly sweep exists and failed — never faked
`True`. Prints the exact digest line Q3 specified: `<n> markets, <m> lines, completeness
<ok/FAIL>`.

10 new unit tests (`tests/test_hourly_pass.py`), sub-passes stubbed via injected callables
(no network): count aggregation, independent-failure isolation (a sports exception doesn't
zero out crypto's real counts and vice versa), series-errors-without-an-exception still
failing completeness, the 09-UTC-only anomaly-sweep gate (both the call-happens/doesn't-happen
cases and a failing sweep failing completeness), the default runner treating "script doesn't
exist yet" as `True` (not a failure), the digest line's exact format, and `main()`'s exit code
tracking `completeness_ok`.

**Live pass** (real network, no injected fixtures): **1311 markets, 455 lines, completeness
ok** — sports leg 453 events / 1048 outcome markets (odds leg still `blocked_no_key`, unchanged
from Q1), crypto leg 2/2 symbols captured with `spot={ok:2}` and `settle={ok:2}`. Tape appended
to the existing `tape/sports_pairs/` and `tape/crypto_hourly/` stores (same manifests those
collectors already write — `hourly_pass` adds no new tape shape, just orchestration). Gates:
**105 tests green** (95 existing + 10 new), `invariants --full` green.

**Next:** Q4 (S7 historical CLV backtest) and Q5 (S8 first cut) remain the two `TODO`-eligible
research milestones; Q6 (anomaly sweep) is now load-bearing for Q3's completeness signal
whenever it lands, not just a standalone probe. Collector-side plumbing (Q1/Q2/Q3) is done;
the queue's center of gravity moves to actually testing S7/S8 for edge.

---

## 2026-07-10 00:22 UTC — Q2 crypto-hourly settlement collector built + first live pass

Topmost eligible queue item after Q1: **Q2**, the crypto-hourly settlement-basis collector
(serves S8/S10). Built:

- `core/crypto_schema.py` — `CryptoHourlyManifest`, the Q2 sibling of `core/sports_schema.py`'s
  `GamePairManifest`: one line pairs THREE legs for one symbol's current hourly bracket —
  the Kalshi ladder (`real_ask`), a live public spot reference (`synthetic`), and the previous
  hour's Kalshi-reported settlement value (`broker_truth`) — so S8's ρ-guard (spot-vs-settle
  correlation) is computable from tape alone, with no second pass ever needed.
- `collection/crypto_hourly.py` — per symbol (BTC via `KXBTC`, ETH via `KXETH`): discovers the
  CURRENT hourly range-ladder by picking the open event whose `(close_time - open_time)` is
  closest to exactly 3600s (Kalshi keeps a much-longer ~7-day "range" event alive under the
  SAME series_ticker simultaneously — duration, not the ticker string, is what actually
  distinguishes them; verified live on both KXBTC and KXETH); snapshots every outcome market's
  real yes_ask BBO; fetches live spot (Coinbase primary, Kraken fallback on failure); locates
  the settled event whose `close_time` equals the current event's `open_time` and reads off
  Kalshi's own `expiration_value`. Any leg failure degrades to an honest status code
  (`spot_status`/`settle_status`) rather than poisoning the Kalshi leg, which is captured
  unconditionally — same discipline as `sports_pairs.py`'s odds leg.
- Added `Kalshi.markets(series_ticker, status, limit)` to `validation/v3_market.py` (generalizes
  the existing `open_markets`, which now delegates to it) so the settlement leg can query
  `status="settled"` through the same throttled/paginated client, no new HTTP code path.
- 14 new unit tests (`tests/test_crypto_hourly.py`): duration-based hourly-vs-standing-range
  event selection (including the "nothing currently straddles now" fallback), degenerate/
  single-outcome/series-error handling, spot-fetch-failure and settle-not-found/fetch-error
  degradation (each independently, confirming the Kalshi leg is never poisoned), the
  provenance/forged-hash check mirroring `sports_pairs`'s, and two adversarial schema checks
  for the new "`ok` status implies the trusted tag" consistency rules.

**Live pass** (no injected fixtures): **BTC 188 outcomes / ETH 75 outcomes** captured in one
pass, `spot_status={ok:2}`, `settle_status={ok:2}` — both legs resolved live on the first try
(Coinbase spot, Kalshi `expiration_value` for the hour that had just closed). Tape →
`tape/crypto_hourly/`.

**Honest finding, not interpreted here (Q5's job):** the naive `bracket_sum` summed across the
FULL discovered ladder is **not** comparable to weather's ~10¢ overround — live BTC bracket_sum
was **3.99** (188 outcomes, overround +2.99), ETH **2.22** (75 outcomes, overround +1.22).
Inspecting the outcomes: most of the 188/75-market ladder is far out-of-the-money brackets
sitting at the exchange's $0.01 floor tick (illiquid, effectively unfillable at size), and their
one-cent asks summed across dozens of dead brackets dominate the total — a thin-tail-liquidity
artifact, not a real structural cost comparable to the weather bracket's near-the-money
overround. Nothing is discarded (the full ladder is captured honestly), but Q5's S8 first cut
will need to restrict to brackets near the money (e.g. within a few strikes of live spot) to get
a bracket_sum that means the same thing weather's did. Gates: **85 tests green** (71 existing +
14 new), `invariants --full` green.

**Next:** Q4 (S7 historical CLV backtest) and Q5 (S8 first cut from free candlesticks — now
armed with 2 days-in-progress of paired crypto tape once cron accumulates it) are both
`TODO`-eligible; Q5 should apply the near-the-money bracket filter found here before trusting
any overround number. S8 moved `idea → data-collecting` in `kb/strategies/00-index.md`.

---

## 2026-07-09 20:18 UTC — Egress unblocked (Q0b); Q1 sports paired-odds collector built + first live pass

Q0b's self-healing re-check (protocol: cheap re-test while any item sits `BLOCKED(egress...)`)
found all four Q0 hosts now reachable — `curl --max-time 15` got Kalshi REST 200, Coinbase 200,
Kraken 200, and the-odds-api 401 (reachable, just no key). Confirmed end-to-end with
`python -m collection.capture_orderbooks --limit 3` (3 markets, 159 levels, real tape written).
The org egress allowlist was evidently widened sometime between 2026-07-02 and today — not
observable from inside the sandbox, just confirmed fixed. Flipped Q1–Q6 back to `TODO` in
`LOOP-QUEUE.md`; refreshed `tape/cloud-env-check.md`.

With egress open, moved to the new topmost eligible item: **Q1**, the sports paired-odds
collector — time-sensitive, since the 2026 World Cup final round runs through Jul 19. Built:

- `core/sports_schema.py` — `GamePairManifest`, the Q1 sibling of `core/manifest_schema.py`'s
  weather `CaptureManifest`: same bitemporal/content-hash/self-signed discipline, keyed by
  `event_ticker` instead of `(city, contract-day)` since a sports event isn't a city ladder.
- `core/odds.py` — American-odds → de-vigged fair probability. Reuses
  `core.pricing.bracket_sum`/`normalized_ask` for the overround-removal division (same "divide
  by the group sum" operation as Kalshi's own Hard Rule #3 math, just applied to sportsbook
  implied probabilities), so that arithmetic still lives in one place.
- `collection/sports_pairs.py` — discovers every Sports-category series whose ticker ends in
  `GAME` (empirically the per-event moneyline/winner suffix — `KXWCGAME`, `KXNBAGAME`,
  `KXMLBGAME`, ... 186 series found live), World-Cup/soccer sorted first; groups each series'
  open markets by the API's own `event_ticker` (cross-checked against a ticker-parse, mismatches
  recorded not hidden); captures real yes/no BBO for every outcome in a >=2-way bracket
  (`price_source_tag=real_ask`); attempts a matched-Pinnacle de-vig leg if `ODDS_API_KEY` is set
  (`synthetic`), else honestly records `odds_leg_status="blocked_no_key"` per Q1's documented
  fallback — the Kalshi leg is captured regardless.
- 18 new unit tests (`tests/test_odds_devig.py`, `tests/test_sports_pairs.py`): American-odds
  math, multiplicative de-vig on 2-way and 3-way brackets, ticker parse/reconcile, World-Cup
  priority ordering, degenerate/series-error handling, odds-leg name matching (caught a real bug:
  Kalshi labels a soccer draw "Tie", the-odds-api calls it "Draw" — added a synonym normalizer),
  and the provenance/forged-hash check mirroring `capture_orderbooks`'s.

**Live pass** (no `ODDS_API_KEY` in this environment): **469 events / 1079 outcome markets**
captured at `real_ask` in ~47s. 4 `KXWCGAME` (World Cup) events captured — `bracket_sum` 1.01–1.02
(1–2¢ overround), noticeably tighter than the ~10¢ weather-bracket overround that killed
pt1/S1/S5. Across all 469 events, mean `bracket_sum` 1.34 (min 0.98, max 2.73) — wide dispersion
expected from thin/off-season leagues with stale asks; not interpreted here, that's Q4's job.
Tape → `tape/sports_pairs/`. `S7` (Kalshi moneyline vs Pinnacle CLV) moved `idea → data-collecting`
in `kb/strategies/00-index.md`. Gates: 71 tests green (53 existing + 18 new), `invariants --full`
green (two docstring false-positives on the `yes_ask`/`no_ask` regex — literal `yes_ask/no_ask`
prose tripped Hard Rule #3's arithmetic detector; reworded, not a real violation).

**Next:** Q2 (crypto-hourly collector) is now the topmost `TODO` item. Separately: S7's actual CLV
backtest (Q4) is still gated on `ODDS_API_KEY` — the odds leg is built and unit-tested but has
never made a live request; re-run Q1 once a key exists to confirm the live matching/de-vig path.

---

## 2026-07-02 22:43 UTC — Q0 cloud environment check: all external hosts BLOCKED by egress policy

Ran the cloud-sandbox reachability check the queue calls for before any of Q1–Q7 can move: Kalshi
public REST (`python -m collection.capture_orderbooks --limit 3`), Coinbase + Kraken public spot,
and `api.the-odds-api.com` (plus a presence-only check for `ODDS_API_KEY`, absent). **All 4 hosts
failed identically** — the sandbox's egress proxy answered every CONNECT with a 403 (`gateway
answered 403 to CONNECT (policy denial or upstream failure)`), and its `noProxy` allowlist covers
only package registries + `anthropic.com`, no data provider. Per the proxy runbook this is an
organization policy denial, not a transient fault — not to be retried or routed around. Full
evidence and interpretation in `tape/cloud-env-check.md`.

**Consequence:** every downstream collector needs one of these hosts, so Q1, Q2, Q3, Q4, Q5, Q6 are
now `BLOCKED(egress policy)` in `LOOP-QUEUE.md` — this is essentially the entire active queue. Q0
itself is the only item this run's cloud sandbox could actually complete; nothing here indicates a
bug in `capture_orderbooks.py`/`normalize.py` (never got past the TLS tunnel). **This needs Ryan**:
either widen this environment's egress allowlist to include a Kalshi host, a public crypto spot
host, and an odds API host, or run the collectors from a pool that already has broader network
access — no cloud run can change its own policy. Gates: 53 tests green, `invariants --full` green
(no code changed, so nothing new to gate — recorded for protocol compliance).

**Next:** once egress is widened, Q1 (sports pairs collector, time-sensitive — World Cup ends Jul
19) is the immediate next milestone.

---

## 2026-06-18 19:41 ET — S2 FOMC×ZQ free-data first cut: structure validated (n=1), worth the CME spend

Free-data, single-meeting first cut of S2 on the just-resolved June 2026 FOMC — Kalshi PUBLIC historical
candlesticks (`yes_ask` BBO) × free Yahoo ZQ. `scripts/fomc_zq_basis_s2.py`, `findings/2026-06-18-fomc-zq-s2.md`.
**n=1 STRUCTURE check, NOT an edge.**

- **FOMC bracket overround = mean +3.35¢** (3–4¢) vs the **~10¢** weather overround that killed pt1/S1/S5 →
  **~3× cleaner; the prob-to-prob structural thesis HOLDS** — the reason S2 is the post-weather pivot.
- June was **LOW-INFORMATION**: both venues priced a near-certain hold (Kalshi P(hold) 0.942–0.962, ZQ
  0.931–0.977); net-of-fee basis mean **−1.39¢/contract**, 5/163 periods positive → no tradeable gap on THIS
  event (expected for a consensus hold; one event can't yield a CI).
- **Verdict: structure worth the CME spend.** Full version needs intraday ZQ ticks (daily close too coarse —
  ZQ P(hold) swung 0.931→0.977 on a single 1-tick move; the `N_post` divisor amplifies it) + many **contested**
  meetings + block-bootstrap CI (block=meeting) + Kalshi L2 depth + frozen-pre-position risk modeling. GATED on
  Ryan (CME data sourcing).
- Honesty: `yes_ask.close` tagged `real_ask` (BBO-at-candle-close caveat — overstates fillable size); ZQ-prob
  `synthetic`. Prior-contested-meeting pull deferred (2025 tickers use a different target-range scheme +
  rate-limits), not faked. **53 tests green, invariants --full green.** Tape/DB untouched.

---

## 2026-06-18 19:40 ET — 3 new cross-venue basis candidates drafted (S7/S8/S9) via /first-principles

Ideation pass through the **cross-venue basis lens** (Kalshi vs a different venue pricing the same/
correlated resolution). Goes BEYOND S2 (FOMC×ZQ prob-to-prob). All three grounded in live
settlement-spec + data-access research (Perplexity, 2026-06-18; CF Benchmarks RTI, Polymarket CLOB
docs, Kalshi historical candlestick REST). None is in the dead ledger.

- **S7 — KXBTC vs Polymarket crypto: settlement-index + sampling mismatch.** Kalshi KXBTC/KXETH
  hourly brackets settle on **CF Benchmarks RTI = 60s average of a multi-exchange index**;
  Polymarket crypto settles on a **single-exchange (Binance) 1-min candle / last print**. Same
  nominal hour, different fixing → the two venues' implied "price lands in bracket X" can disagree
  whenever Binance basis vs the multi-exchange index, or a sub-minute spike, moves the single print
  off the 60s mean. Mechanism: settlement mismatch, NOT a probability claim. Both real-price histories
  are FREE/public (Kalshi `/historical/market_candlesticks` yes-OHLC; Polymarket CLOB
  `/prices-history` + Gamma resolved outcome). Overround note: crypto-hourly binaries are 2-outcome
  (low overround) BUT Kalshi crypto taker fee is the fat 7%-class — must clear that.
- **S8 — Kalshi single-game sports vs Pinnacle sharp closing line (directional on the laggard).**
  Documented: Kalshi order-book sports prices LAG Pinnacle's vig-removed line by minutes after a
  discrete info shock (injury/scratch/steam); practitioner reports 2–3pp gaps before catch-up;
  election-market analog measured 12–18 min lag. Mechanism: sharp dealer (Pinnacle) reprices
  instantly; Kalshi only moves when a taker crosses the book → exploitable catch-up window. Trade
  the laggard (Kalshi) directionally toward the devigged Pinnacle number. Real ask = Kalshi BBO
  (candlestick yes_ask OHLC + live book); reference = Pinnacle/odds-API devig. Overround: liquid
  marquee games show 1–3¢ spreads — thin enough that a 2–3pp lag can clear it.
- **S9 — Kalshi vs Polymarket same-event PRICE-DISCOVERY lead-lag (timing, not static level).**
  "Who Wins and Who Loses" (SSRN) + LOOP-violation paper: **Polymarket leads Kalshi in price
  discovery** (24/7 crypto crowd, zero maker fee) on the SAME politics/macro yes/no event; the
  static level-wedge has compressed to 1–2% and is NOT cleanly unidirectional, so the edge is the
  *timing* — fade Kalshi toward Polymarket's already-moved price after a discrete shock, not a
  standing level arb. Mechanism: segmented user bases + USDC/USD rail friction keep arbitrage from
  enforcing instant parity. Both prices FREE (Kalshi candlestick + Polymarket CLOB). Overround:
  Kalshi politics binaries are richer (sum 110–140% multi-outcome); the lead-lag must clear Kalshi's
  taker fee + spread on the 2-outcome legs.

These graduate to the registry as **S7/S8/S9 (idea)**. Binding tests are all no-capital replays on
free public history. Returned via the workflow's StructuredOutput; full rationale in the council/
first-principles brief to follow before any data-collection spend.

---

## 2026-06-18 15:03 ET — S5 weather rehab TESTED → DEAD. Weather family is dead at real asks.

**The decisive result.** With Ryan's go-ahead, ran the S5 weather-rehab real-ask paper test —
the question that decides the project's direction. Verdict: **the weather family is DEAD at real
asks, even with proper EMOS calibration.** (`scripts/weather_rehab_s5.py`,
`findings/2026-06-18-weather-rehab-s5.md`, per-trade dump `reports/weather_rehab_s5_full.json`.)

- **EMOS works — but it's necessary, not sufficient.** Leave-one-day-out EMOS calibration cut
  pooled CRPS **2.366 → 2.180 (−7.86%)**, fixing the underdispersion exactly as the literature
  (Gneiting 2005) predicts. The better probability is real.
- **The dollar edge is not.** 641 trades (3-model ensemble: GFS+ECMWF-IFS025+ICON; GEM single-runs
  not archived for the window so honestly dropped → member_count=3; no `ncep_gefs025`). Mean net
  **−$0.02789/trade**, 95% moving-block-bootstrap CI **[−$0.06297, +$0.00788]** (n_boot=10k, 21
  contract-day blocks). **Lower bound does NOT clear zero.** Killed by the same **~9.8¢ mean
  overround** that ate pt1 and S1. A better probability cannot beat a ~10¢ structural tax here.
- **Adversarial checks (the discipline that matters):** edge-bar sweep — raising the conviction bar
  to 0.10/0.15 made P&L *worse* (CI fully below zero), the opposite of a real edge; independent
  fill/cost sign audit — 0 mismatches (no repeat of S1's near-miss); anti-leak — used the Open-Meteo
  **Single Runs API pinned to (D−1) 00Z** (a genuine ~24h-ahead leak-free forecast), NOT the
  historical-forecast archive (which stitches lead≈0 ≈ actuals and would leak — venues.yaml warns);
  0 leak-guard drops. Prices `real_ask`, all 6 provenance fields persisted per trade.
- Caveats (honest): short 22-day spring window, EMOS data-thin, decision time near market open,
  L1-only fills (haircut modeled not measured).

**PROJECT DIRECTION CHANGE:** weather is no longer "on probation" — it is **proven dead at real
asks**. The 3 weather angles tried (raw ensemble pt1, longshot-fade S1, EMOS-calibrated S5) are all
dead to the overround. **Pivot to non-weather: S2 (FOMC×ZQ basis — structurally NO bracket
overround), S3 (cross-strike staleness), S6 (market-making — earn the spread instead of paying it).**

Verified: **53 tests green, `invariants --full` + `--db` green**, recovered tape read-only. S5
committed to `main`. Only S2 (FOMC×ZQ) remains on the queue — GATED on CME data sourcing (Ryan).

---

## 2026-06-18 12:53 ET — S1 longshot-fade FALSIFIED · EMOS reproduced · forecast tape live

Three parallel probes ran on top of the S0 substrate (autonomous `/loop`, 3 subagents). Merged
tree verified: **53 tests green, `invariants --full` green**, recovered tape DB untouched (read-only).

- **S1 longshot-fade → DEAD (real asks).** n=990 reconstructed-`real_ask` KXHIGH brackets from the
  24GB recovered tape. The favorite-longshot bias *exists* (longshots <0.20 realize fewer wins than
  priced, gaps −1.4¢..−7.0¢; favorites >0.65 underpriced) but is single-digit cents, **swamped by a
  +9.84¢ mean overround**. Maker-NO-on-longshot net P&L **+$0.00448/trade, 95% block-bootstrap CI
  [−$0.00486, +$0.01333]** — lower bound does NOT clear zero; sweep 0.05→0.25 uniformly null, deepest
  longshots negative. **A whole bias-chasing family falsified**, as the dossier predicted. Probe:
  `scripts/longshot_fade_probe.py`; writeup: `findings/2026-06-18-longshot-fade-s1.md`. **Near-miss:**
  the first run cleared zero on a cost-model sign bug (maker entry booked as a 2¢ *improvement* not a
  *cost* — the exact pt1 prime-directive failure mode); caught + fixed. **Candidate invariant filed:**
  a cost haircut must never move the entry in the trader's favor. (Tape caveat: T-24h lands near market
  open; L1-only, fill-prob haircut modeled not measured; single 22-day spring window.)
- **EMOS reproduced (#5).** `scripts/emos_demo.py` (stdlib-only, deterministic) fits a 1-param-spread
  EMOS Gaussian by minimizing closed-form Gaussian CRPS: **CRPS 1.663 (raw ensemble) → 0.717 (EMOS),
  −56.9%**, bracket P(74≤Tmax<78)=0.761. Flipped `kb/quant-finance/01-weather-forecasting-alpha.md`
  from `cited` → `reproduced`. (Calibrated post-processing beats the raw underdispersed ensemble — the
  precondition for any S5 weather-rehab attempt.)
- **Forecast tape now exists (#3).** `collection/forecast_collector.py` (+10 offline tests) — single
  read-only Open-Meteo pass per city × {gfs_seamless, ecmwf_ifs025, icon_seamless, gem_global} (NO
  `ncep_gefs025`, Hard Rule #1, with a runtime guard), append-only JSONL with ms `fetch_ts` + raw
  sha256 + `source_tag=synthetic`, honest completeness. Live smoke (NYC, 2026-06-18): 89.6/89.2/90.1/
  86.3°F across models. The previously-zero most-reused missing input is no longer zero.
  **Scheduling still GATED** (laptop-cron HOLD).

**Loop end-state:** all 4 unblocked Next items done (S0 substrate, S1, EMOS, forecast collector). **Two
items remain GATED on Ryan:** #2 cron forward capture (Kalshi creds + the laptop-cron HOLD decision)
and #4-S2 FOMC×ZQ (CME data sourcing). Nothing committed to git (Ryan's call).

---

## 2026-06-18 12:38 ET — S0 real-ask substrate built + Hard-Rule invariants (43 tests green)

**Built the project's first implementation — the substrate every future edge is scored on
(dossier #1, the canonical first build).** Autonomous `/loop` run against the 5-item Next queue.

- **Lifted verbatim from `kalshi.1` @ `fd37ae2`** (byte-identical, all 16 files diff-checked,
  recorded in `../PROVENANCE.md`): `core/{canonical,io,manifest_schema,timeutil,schema}.py`,
  `collection/{normalize,capture_orderbooks}.py`, `validation/{v1_actuals,v3_market,_http}.py`,
  4 config YAMLs, 3 tests + ticker fixture. Mirroring kalshi.1's layout meant **zero import edits**.
  - `normalize.py` derives the REAL taker ask `best_yes_ask = round(1 − best_no_bid, 4)` (Kalshi
    posts bids-only; the ask is the opposite side's complement). This is the price H1 trades on.
  - `capture_orderbooks.py` = forward, read-only, bitemporal depth capture Kalshi does NOT archive
    (the only moat that compounds with calendar time). Honest completeness: a dropped market lowers
    `n_markets < expected` so a truncated pass can't pass as complete (survivorship guard).
  - `v1_actuals.py` = 3-source settlement gate (CLI vs METAR vs GHCN) — the corrupted-actuals catch.
- **Authored fresh for THIS project's rules** (kalshi.1 has no equivalent — its invariants are
  arb-bot-v2's, scoped to a different layout):
  - `scripts/invariants.py` — the **6 Hard Rules** as static (regex) + DB (sqlite) assertions, plus
    `--pre-edit-hook` mode. Structure adapted from `arb-bot-v2/scripts/v3_invariants.py`, retargeted.
    DB invariants are **schema-discovering** (the project's DB schema isn't frozen) — they introspect
    tables, so Rule #4 (no pnl without a `price_source_tag`) fires on whatever backtest table appears.
  - `core/source_tag.py` — the trust=FALSE default in code: **untagged number ⇒ `synthetic`**; only
    `real_ask`/`broker_truth` are `is_fillable`; `require_fillable()` blocks synthetic/midpoint from
    any fill/P&L decision (prime directive #1).
  - `core/pricing.py` — THE sanctioned `yes_ask/bracket_sum` site (Hard Rule #3); `overround()` makes
    the ~5¢ pt1 killer a first-class, persisted number.
  - `core/stats.py` — `safe_pstdev` with the n≥4 guard (Hard Rule #2).
- **Verified:** `pytest -q` → **43 passed**; `invariants.py --full` → **all green**. The dossier's #1
  binding assertion is now a test: `best_yes_ask == round(1 − best_no_bid, 4)`, ask stamped `real_ask`.
- **Not wired (left for approval):** the PreToolUse hook (would block edits = harness change); live
  capture/actuals paths (need Kalshi creds + network — only offline/injected paths are tested).

**Next (this loop):** `scripts/emos_demo.py` repro (#5) → Open-Meteo collector script (#3) →
longshot-fade offline calibration on the recovered tape (#4-S1). **GATED on Ryan:** cron the forward
capture (#2 — needs creds + conflicts with the kalshi.1 laptop-cron HOLD) and FOMC×ZQ (#4-S2 — needs
CME data sourcing).

---

## 2026-06-18 01:10 ET — Codebase mine landed; KB foundations built

**Workflow result (27 agents, 22 candidates, all adversarially verified at real asks):**
- Verdict tally: **0 proven edges · 4 dead · 6 infra-only · 12 needs-data.**
- Honest bottom line: **no clean dollar edge is proven at real fillable asks anywhere.** The
  only real-money test (KXHIGH weather ensemble, n=49) lost −$0.14/trade; pt1 −9.6%, killed by
  ~3–5¢ bracket overround. Directional signal is real; dollar edge is not.
- Cheapest path forward: build the **real-ask substrate** (S0: tape capture + 3-source actuals
  gate + bid-only ask primitive + invariant engine), start **archiving forward orderbook tape**
  (un-backfillable; the only moat that compounds), and run two near-free probes — **longshot-fade
  calibration (S1)** and **FOMC×ZQ basis (S2)**. Zero weather-model capital until a real-ask CI clears zero.
- Full dossier → `../findings/2026-06-18-codebase-money-map.md`. Candidates registered → `strategies/00-index.md`.

**KB built this session:**
- `kalshi-api/`: overview, **auth & signing** (RSA-PSS/SHA-256, verified), REST+WebSocket map,
  **fees & breakeven** (`reproduced` via `scripts/fee_breakeven.py` — 2¢/contract at 0.50 → need +2¢ edge).
- Runnable repros: `scripts/kalshi_sign.py` (local signature verifies OK), `scripts/fee_breakeven.py` (ran).
- `quant-finance/`: 7-theme overview + deep weather-alpha note; citations triaged (caught a
  fabricated arXiv id + several wrong venues — see `_sources/quant-finance-sources.md`).
- `glossary.md`, both `_sources/` provenance files.

**Dead-end ledger (do not re-mine):** raw KXHIGH ensemble as deployed, Kelly-modifier tilt, LIP
rebate harvest, settle-time T-3h pin, K1' "hedge" framing, NWS/WU settle-source basis. (Details in dossier.)

**Next:**
1. Build S0 substrate (lift kalshi.1 `normalize.py`/`v1_actuals.py`/`capture_orderbooks.py` + invariants).
2. Cron forward Kalshi orderbook capture at a pinned decision time TODAY.
3. Start an Open-Meteo forecast collector (zero forecast tape exists anywhere — most-reused missing input).
4. Run S1 (longshot-fade) and S2 (FOMC×ZQ one-meeting) — near-free, no capital, decide weather's fate.
5. Reproduce: write `scripts/emos_demo.py` so the weather-alpha note can claim `reproduced`.

---

## 2026-06-18 00:35 ET — KB seeded; codebase-mining workflow launched

- Created `kalshi.headless` as the canonical Tier-2 Kalshi project. Inherited the
  prime directive, trust=FALSE defaults, and 6 hard rules from `arb-bot` (see
  `../CLAUDE.md`).
- Stood up this KB with the Karpathy-method charter (`README.md`): first
  principles, runnable repros, append-only log, cold-reader legibility.
- Kicked off a dynamic workflow to mine the four existing Kalshi codebases
  (`arb-bot`, `arb-bot-v2`, `kalshi.1`, `kalshi.ibkr`) for money-making
  opportunities and adversarially verify each against the "real fillable asks"
  bar. Output lands in `../findings/`.
- Began two foundational KB tracks in parallel:
  - `kalshi-api/` — how Kalshi actually works (auth, market structure, fees,
    rate limits, data).
  - `quant-finance/` — peer-reviewed literature relevant to prediction-market
    edges (calibration, favorite-longshot bias, market microstructure, Kelly).

**Next:** integrate workflow findings into `strategies/` candidates; reproduce
the top-1 fee/pricing claim with a runnable script.
