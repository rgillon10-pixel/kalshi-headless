# Q21 idea-generation round — 2026-07-20 (kalshi-edge-hunter, nightly)

**Trigger:** eligible (TODO/unclaimed/unblocked/**gate-open**) research items = **0**, verified by
FILE SHAPE (L25), not path existence. The 2026-07-20 morning research-loop run already re-scanned
Q0–Q46 and found all operative statuses DONE/DEAD/BLOCKED/GATED/RESERVED; this edge-hunter run
re-confirmed the near-gate items independently:

- Q43 (perp/binary consistency) — gate `_perp_days_available() >= 7`; `tape/perp_tape/` holds
  **4 canonical `.jsonl` forward days** (07-17..07-20, line counts 511/238/102/17), opens ~07-23.
  Probe already built (`scripts/q43_perp_binary_consistency_probe.py`, this-morning's run).
- Q36 (weather revival) — gated ~07-22 naive / ~07-23+ clean; `tape/weather_books/` 4 canonical
  days (07-16..07-19 + 07-20 partial) but **design-blocked** on an intraday-KNYC actual the daily
  `weather_actuals` feed (2/40/20 lines/day) does not carry. Probe already exists
  (`scripts/q36_kxtempnych_settlement_basis_probe.py`).
- Q37 gated ~Aug-05; Q19 WC-final/FOMC burst legs have no captured tape; Q32/Q33/Q35-build/Q42-part3
  credential/auth-blocked.

**Bar unchanged:** still **0 proven edges** (block-bootstrapped 95% CI > 0 at `real_ask` net of fees).
This is the **6th round in ~8 days** (07-13/14/15/16/18/19), all registering **0** — the binding
constraint remains generation surface, not cadence: **no new tape surface has landed since the 07-18
round**, and the graveyard now forecloses taker-into-overround (S1/S5/S7), maker-fee-swamp
(S6/S13/S23), unprovable-queue / no-fill-model (S19/S21), fair/depth timing gap (S21/S43-clv),
cross-venue two-fee (S34), universe_sweep no-strike-fields (S41), and perp-outside-discipline (S42).
Next free number after the 07-19 round consumed S41/S42 was **S43**. 3 candidates proposed, each
attacked by an independent `verifier` over the committed tape BEFORE registration (two-agent rule at
the idea stage); **register only survivors, never pad to quota**.

---

## S43 — Cross-venue econ-release DIRECTIONAL convergence (single-leg laggard, ONE fee)

**Mechanism / counterparty.** On a scheduled macro print (CPI/GDP/payrolls), both Kalshi
(`tape/econ_prints/`, KXCPI/KXCPICORE/KXCPIYOY/KXGDP/KXPAYROLLS `real_ask` ladders, `close_time`
carried) and Polymarket (`tape/polymarket_cpi_pairs/`) reprice. If one venue lags, trade the
**laggard** leg directionally toward the leader's post-print level — a SINGLE-leg convergence trade
paying ONE venue's fee. Counterparty: retail on the slow venue not yet updated to the released figure.
**Data:** already-collected `econ_prints` + `polymarket_cpi_pairs` (real released figure = `broker_truth`).
**Gate:** ≥N shared release events; cross-correlate repricing; directional entry at laggard `real_ask`
after the leader moves clears a block-bootstrap CI>0 net of one fee. **Kill:** venues reprice together,
or too few releases to bootstrap.
**Survives its nearest dead cousin:** S34 (two-legged arb, pays BOTH fees) — one fee, not two. S9 (WC
lead-lag dead by hourly cadence coarser than a minutes-long match) — a macro print digests over
30–60+min, comparable to the capture cadence.

## S44 — universe_sweep logical-COMPLEMENT coherence arb

**Mechanism / counterparty.** Within one `capture_id` (simultaneous ~20k-market census), find two
`event_ticker`s whose YES outcomes are logical complements such that YES_ask(A)+YES_ask(complement) <
$1.00 net of both per-contract fees with BOTH legs fillable (`yes_ask_size ≥ 1`). Counterparty: a
maker's stale/crossed cross-market quote. **Data:** `tape/universe_sweep/` (`real_ask`, shared
`capture_id`). **Gate:** ≥1 complement pair below $1 net fees, both legs fillable. **Kill:** none.
**Survives its nearest dead cousin:** S41 (bracket-arb needs the strike-ladder fields universe_sweep
lacks) — logical complements need only two tickers + a complement map, not strike fields.

## S45 — Single-series settlement-ledger-anchored rich-side maker-SELL

**Mechanism / counterparty.** Scope to ONE high-n recurring series (`tape/crypto_hourly/` BTC/ETH
ladders) joined to `tape/settlement_ledger/` `broker_truth`. Among members whose normalized ask
(`yes_ask/bracket_sum`) sits systematically ABOVE realized settlement frequency (the rich side), rest
a maker SELL; check if mean realized (premium − payout − 1¢ maker fee via `core.pricing`) clears zero
on a queue-aware fill-sim. Counterparty: retail overpaying the rich tail. **Gate:** rich-side maker
CI>0 net of fee. **Kill:** fee consumes the edge, or no fillable resting book.
**Survives its nearest dead cousin:** S23/S38 (cross-category overround swamp / fair-depth timing gap)
— a single high-n series with a direct settlement-ledger truth join.

---

## Verifier attack (two-agent rule, idea stage) — RESULTS: 3 proposed, **0 registered**

All three attacked by an independent `verifier` that re-ran the actual committed tape. **All three
KILL-AT-IDEA** — a clean sweep, same outcome as the 07-15/16/18/19 rounds. Still **0 proven edges**.
S43/S44/S45 consumed → **next free = S46**.

**S43 — KILL-AT-IDEA (data-adequacy, S9 grave).** Enumerating every `open_events` event_ticker +
`close_time` across `tape/econ_prints/dt=2026-07-05..19.jsonl`, the ONLY macro release whose settlement
moment falls inside the committed window is **June CPI** (`KXCPI-26JUN`/`KXCPICORE-26JUN`/`KXCPIYOY-26JUN`,
`close_time ≈ 2026-07-14T12:2Xz`) — and those three are the *same simultaneous BLS print*, not
independent events. Every other series releases AFTER the tape ends (`KXGDP-26JUL30` close 07-30,
`KXPAYROLLS-26JUL` close 08-07; all other CPI months are forward ladders 26AUG..26NOV). Joinable
universe = **1 release moment** → no cross-event distribution to bootstrap; intra-event ticks are one
autocorrelated digestion path, not independent draws. Also `polymarket_cpi_pairs` Kalshi leg is 100%
`price_source_tag: synthetic` (1452/1452), so the real_ask lives only in `econ_prints` — two-tape
gymnastics on top of n=1. Re-testable only when econ tape spans ≥4 distinct release moments.

**S44 — KILL-AT-IDEA (collapses into S41).** Over one census (`capture_id 20260718T003036Z`,
`tape/universe_sweep/dt=2026-07-18.jsonl`), the tightest guaranteed-exhaustive complement — the
within-market YES+NO box — across the 237 markets with both asks fillable has **min(yes_ask+no_ask) =
1.002, ZERO below $1.00**: that gap IS the overround, it never inverts even pre-fee. The candidate's
cross-ticker "sum=0.026" pairs are two *different* parlay conjunctions in one multigame event
(mutually exclusive but NOT exhaustive — both can lose, buying both collects $0), exactly the S41
all-zero/longshot artifact. Stacked kills: complements are **not identifiable** from `universe_sweep.v1`
(no partition-linking field; 84% is `KXMVESPORTSMULTIGAMEEXTENDED` combinatorial parlays); only **2.5%**
of rows (2500/100000) have `yes_ask_size ≥ 1` and only **16** events have ≥2 fillable YES legs; L96
20,000-row cap means a full MEE partition (40+ legs/event) is never guaranteed captured.

**S45 — KILL-AT-IDEA.** (1) The specified truth join is **empty**: `tape/settlement_ledger/` has a
single committed date (`dt=2026-07-17`, 5605 rows) with **0 KXBTC and 0 KXETH rows** (entirely
sports/metals) — crypto_hourly ↔ settlement_ledger key overlap = zero; the "join to settlement_ledger"
premise is refuted outright (crypto settlement truth lives only inside `crypto_hourly.previous_settlement`).
(2) Even substituting that, **no fill model is buildable**: crypto_hourly outcome records carry no
size/queue/depth field (10 keys: cap/floor_strike, no/yes_ask, no/yes_bid, price_source_tag,
strike_type, ticker, title) — the S19/S21 unprovable-queue grave + the S10 floor-pin / S14
candle-proxy no-depth problem. (3) Fee swamp confirmed: on `dt=2026-07-07` only **3.4%** (397/11835)
of bracket quotes are two-sided; modal spread 1–4¢ vs a flat **1¢ maker fee** (L30) eats 50–100%+ of
the half-spread, exactly as it killed S6/S13/S23.

## New lesson candidates (surfaced by the attacks) → ledger L113/L114/L115

- **L113** — `tape/econ_prints/` committed window contains **n=1 in-window macro release** (June CPI,
  2026-07-14); all other series settle after the tape ends. Any cross-venue *directional* econ-lag idea
  is data-adequacy-dead by n=1 until the tape spans ≥4 distinct release moments (parallels S9).
- **L114** — `universe_sweep.v1` within-market YES+NO box min = **1.002** (never <$1), and sub-$1
  cross-leg sums are non-exhaustive parlay longshots — "complement coherence" is the S41 artifact
  re-skinned; complements are unidentifiable without a partition field. Generalizes L105.
- **L115** — `tape/settlement_ledger/` (as committed, `dt=2026-07-17`) has **zero crypto rows**; crypto
  settlement truth lives only in `crypto_hourly.previous_settlement`, and `crypto_hourly` carries no
  size/depth field, so no crypto maker fill-sim is constructible. Any "join crypto_hourly to
  settlement_ledger" claim is a zero-overlap join.

## Reproduce
- `tape/econ_prints/dt=2026-07-{05..19}.jsonl` — collect `open_events.events[].{event_ticker,close_time}`;
  only June-CPI settles in-window.
- `tape/polymarket_cpi_pairs/dt=*.jsonl` — periods `{2026-07:962, 2026-06:490}`, kalshi tags `{synthetic:1452}`.
- `tape/universe_sweep/dt=2026-07-18.jsonl` — one `capture_id`; `min(yes_ask+no_ask)` over fillable rows = 1.002.
- `tape/settlement_ledger/dt=2026-07-17.jsonl` — grep KXBTC/KXETH = 0/0.
- `tape/crypto_hourly/dt=2026-07-07.jsonl` — outcome keys (no size); two-sided fraction 3.4%.
