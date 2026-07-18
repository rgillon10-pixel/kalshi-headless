# Q21 idea-generation round — 2026-07-18 (kalshi-edge-hunter, nightly)

**Trigger:** re-eligibility fired again — eligible (TODO/unclaimed/unblocked/gate-open) research
items = **0**. Q19 remaining legs are future events (WC final Jul-19, FOMC Jul-29, no burst tape
yet); Q36 gated (`tape/weather_books/` 3/7 daily days — opens ~Jul-22 by FILE SHAPE, L25);
Q37 gated (~Aug-05); Q43 gated (`tape/perp_tape/` 2/7 days — opens ~Jul-23); Q32/Q33/Q35-build
blocked on Polymarket credentials; Q42 part 3 BLOCKED(needs-auth). Matches the last three
research-loop runs' own "0 eligible" findings (PRs #109/110/111).

**Bar unchanged:** still **0 proven edges** (block-bootstrapped 95% CI > 0 at `real_ask` net of
fees). A round restocks the hypothesis pipe; it does not move the bar. Next free number **S38**.
Target 3–5 defensible candidates; every proposal attacked by an independent `verifier` BEFORE
registration (two-agent rule at the idea stage); register only survivors. Diversity floor: ≥1
proposal from new literature or non-QF-theme mechanics.

**New surfaces this round can use that prior rounds could not:**
- **Q46 `tape/universe_sweep/`** (landed 2026-07-17): a full-universe top-of-book census, 4×/day,
  ~20k `real_ask` lines/pass, one line per open market, carrying `yes_ask`/`no_ask` +
  `yes_ask_size`/`yes_bid_size` (touch depth) + `volume`/`volume_24h`/`open_interest`, grouped by
  `event_ticker`, **all legs of one pass sharing a single `capture_id`** (a genuinely simultaneous
  cross-section — unlike the forward-filled ladder tape that produced S33's asynchrony artifact).
- **Q45 `tape/settlement_ledger/`** (landed 2026-07-17): systematic `broker_truth` terminal labels
  (`result`/`settlement_value`/terminal `volume`/`open_interest`), binary-only (L52), keyed for
  joining entry-BBO snapshots to realized outcomes (GOAL.md M4 join-test, ~2026-08-20).
- **Q37 fee finding** (2026-07-17): a *confirmed-live* standing Kalshi Liquidity Incentive Program —
  every newly-listed weather market gets a **50% maker-fee discount** (`discount_factor_bps=5000`)
  for ~54–60 min post-listing, gated on ≤1000 resting contracts. A real Kalshi (in-execution-surface)
  fee lever, distinct from Q35's Polymarket-credential-blocked rebate.

---

## S38 — Full-universe cross-category calibration census (favorite–longshot gradient)

**Mechanism / counterparty.** The favorite–longshot bias (Snowberg & Wolfers 2010) has been tested
on Kalshi only *one category at a time* — S1/S5 (weather), S7/S23 (sports) — and every single-category
test died (taker swamped by overround, or maker fills unrealizable). None has ever measured the bias
*across all categories at once*. Kalshi lists >80k open markets (Q46); sharp market-making capital is
concentrated in a handful of liquid flagships, so the **counterparty on obscure/auto-listed categories
is retail with no sharp offset**, and that is precisely where a longshot-overpricing (or favorite-
underpricing) cell large enough to clear the real-ask fee floor could survive. The novel object is the
**category × liquidity gradient**, not a pooled mean.

**Data (already-collected / free).** `tape/universe_sweep/` entry BBO (`real_ask`, with `yes_ask_size`
touch depth) joined to `tape/settlement_ledger/` realized `result` (`broker_truth`). Both on the
monitored pipe, accumulating now.

**Falsifiable gate.** For each (category, `yes_ask`-decile) cell: realized-win-rate − (`yes_ask` +
`core.pricing.fee_per_contract`); block-bootstrap by settlement-day (L6); require a cell whose 95% CI
> 0 AND passes `bootstrap_verdict_admissible` (L41) AND `clears_tick_magnitude` (L27) AND has ≥10
contracts of `yes_ask_size` at entry (fillability). **Kill:** no cell clears the fee floor with depth
→ the S1/S7 death generalizes platform-wide and the whole favorite–longshot factor is retired for
Kalshi (a clean, valuable platform-scale kill).

**Why it survives its nearest dead cousin.** S1/S7/S23 each tested a *single* category and never had
a cross-category census or a per-line touch-depth field to gate fillability; this is the first test
that can locate *where* (if anywhere) the mispricing is fattest rather than assuming the weather/sports
death transfers. **Presumptive-dead caveat honored:** it pays taker into overround, so the base rate is
DEAD (S1/S5/S7) — the defensible reason to run it anyway is (a) it is a cheap read-only heavy-tail
*search* over 80k markets, not a pooled-mean bet, and (b) the depth gate (`yes_ask_size`, new in Q46)
is the honest fillability guard the single-category takes lacked. **GATED** on ≥~14 days of joined
`universe_sweep`×`settlement_ledger` tape (GOAL.md M4). Diversity: census/breadth-derived, not a
dead-verdict inversion.

---

## S39 — Attention-shock overpricing fade (Barber & Odean 2008 net-buying-pressure) — NEW LITERATURE

**Mechanism / counterparty.** Barber & Odean (2008), *"All That Glitters"*: individual investors are
net **buyers** of attention-grabbing assets, transiently pushing prices above fair. On Kalshi a market
with a sudden `volume_24h` surge is receiving an attention shock; retail net-buys the YES, lifting
`yes_ask` above the realized-frequency-implied fair. **Counterparty: attention-driven retail chasers**;
they lose because the attention decays and the price mean-reverts toward the settlement-implied level.

**Data (already-collected / free).** `tape/universe_sweep/` `volume_24h` + BBO across consecutive 6h
sweeps to detect surges; `tape/settlement_ledger/` for the realized outcome.

**Falsifiable gate.** Flag markets with a `volume_24h` jump > X·σ (X∈{2,3}) between consecutive sweeps;
compute realized settlement vs the surged-side entry `yes_ask` net of fee; block-bootstrap by
surge-event (L6); require CI > 0, `bootstrap_verdict_admissible` (L41), `clears_tick_magnitude` (L27),
and ≥10-contract touch depth. **Kill:** surged-side realized win-rate ≥ `yes_ask` − fee (no overpricing)
/ fillable population below the 10-event floor / the fade loses more than the round-trip (the S24 trap).

**Why it survives its nearest dead cousin.** S24 (dead) tested a *near-close hourly-return* reversion
(De Bondt–Thaler, a **price** signal, sports-only) and died because the ~0.7¢ reversal was an order of
magnitude below the ~6–7¢ round-trip. S39 is a **volume/attention** signal (Barber–Odean), a different
mechanism, on the **whole universe** (not near-close, not sports-only) — the trigger and population do
not overlap S24. New literature distilled into `kb/quant-finance/attention-driven-buying.md` as part of
this round (diversity floor). **Presumptive-dead caveat honored:** if run as a taker fade it is
overround-dead, so the gate requires the overpricing to exceed the *full* round-trip (or a cited maker
fill model, S13 precedent). Diversity: new literature not yet in `kb/quant-finance/`.

---

## S40 — LIP-window fresh-listing maker (half-fee + short-queue selection) — Kalshi-only

**Mechanism / counterparty.** Q37 confirmed live a standing Kalshi LIP: every newly-listed weather
market carries a **50% maker-fee discount** for its first ~54–60 min, gated on ≤1000 resting contracts.
Rest maker offers **only inside that fresh-listing window**: the book is new, so the competing resting
**queue is short** (a maker actually reaches the front and fills) *and* the maker fee is halved. This
attacks the two mechanisms that killed every prior Kalshi maker (S6/S13/S21/S23): the flat-fee-exceeds-
spread death (halved here) and the deep-queue-no-fill death (short fresh queue here). **Counterparty:
early retail takers who cross the thin fresh book** before sharp liquidity arrives.

**Data (already-collected / free).** `tape/weather_books/` (accumulating; Q36/Q37 gate) — listing
timestamps + first-hour book evolution; Q37's confirmed fee schedule. Kalshi-only, so it is in the
project's execution surface (unlike Q35's Polymarket-blocked rebate half).

**Falsifiable gate.** Identify fresh-listing windows from the tape; run a **queue-aware** fill-sim
(L39 — NOT candle-through) using the short fresh-listing queue; net of the **LIP-discounted** maker fee
applied at the sanctioned `core.pricing` site (never hand-rolled, L18/L30); block-bootstrap by
market-hour (L6); `bootstrap_verdict_admissible` (L41) + `clears_tick_magnitude` (L27). **Kill:** the
fresh-listing queue is still too deep to fill (the S21 median-485-ahead death persists) / the half-fee
still exceeds the captured spread (S6/S13 fee-floor death survives the discount) / no weather signal
(S1/S5).

**Why it survives its nearest dead cousin.** S6/S13/S23 makers died on flat-1¢-fee > spread *and* deep
queues; S40 is the first candidate to attack **both** at once — the LIP **half-fee** (0.5×) and
**fresh-listing queue selection** (short queue → real fills, vs S21's 485-deep). It exploits a
confirmed-live Kalshi structural fact (Q37) and stays Kalshi-only. Relationship to Q37 (the general
summer weather-maker re-test): S40 is the *specific* LIP-window + short-queue selection mechanism and
can share Q37's fill-sim scaffolding; it is not the general re-test. **GATED** on `weather_books`
accumulation.

---

## Verifier attack (two-agent rule, idea stage) — RESULTS: 3 proposed, **0 registered**

Each candidate was attacked by an independent `verifier` agent that re-ran the actual committed
tape (not just the proposal's data claims). **All three KILL-AT-IDEA.** A clean idea-stage sweep,
same outcome as the 2026-07-15 (S25/26/27) and 2026-07-16 (S35/36/37) rounds — register only what
survives, never pad to quota. Still **0 proven edges**. Numbers S38/S39/S40 are consumed (killed
numbers are not reused, per the 07-16 round's "next free = S38" precedent) → **next free = S41**.

**S38 — KILL-AT-IDEA.** The "cross-category gradient" that was the whole escape from S1/S7/S23
does not exist in the tape: the `universe_sweep` census is **99.6% two auto-generated combo series**
(`KXMVESPORTSMULTIGAMEEXTENDED` 83.6% + `KXMVECROSSCATEGORY` 16.0%), there is no `category` field,
and after the proposal's own depth gate (`yes_ask_size≥10 ∧ volume>0 ∧ 0<yes_ask<1`) the fillable
population is **557/100,000 rows (0.56%), 99.4% of them those same combo series**, longshot-skewed
(341/557 in decile 0, ~10 rows across favorite deciles 7–9). So it reduces to favorite-longshot on
the combo tail — the same Hard-Rule-#6 factor slot as the dead S1/S7/S21/S23, not a new object. The
mispriced tail is the unfillable 96% (`yes_ask_size==0` on 96.2%, `volume==0` on 88.5%); where depth
exists it is the liquid combo core that is not mispriced (the S21/Q46 structural point, not a timing
gate). Also: a ~100-cell category×decile search with only per-cell L41/L27 gates and no BH-FDR
control is the S20/L41 luckiest-cell trap.

**S39 — KILL-AT-IDEA.** The surge signal is uncomputable on the committed tape: **`volume_24h` is
identically 0.0 on all 100,000 records** (the collector maps it from `volume_24h_fp`; `volume`/
`open_interest` are populated, so the field mapping is the suspect), and the five 20k-line census
passes have **zero cross-capture ticker overlap** (each pass paginates a disjoint slice because the
20k call-cap truncates mid-cursor over an >80k universe), so no market is ever re-observed and no
consecutive-sweep delta of ANY field exists. Separately, swapping the trigger (volume vs price)
leaves the fill economics identical to the dead S24 round-trip (taker entry, overround absorbed,
binary settle), and Barber–Odean equity net-buying is bps-scale, not the >7¢ needed to clear a
Kalshi round-trip. `kb/quant-finance/attention-driven-buying.md` was NOT distilled (candidate died
first).

**S40 — KILL-AT-IDEA.** The load-bearing fact is unverified: `kb/kalshi-api/03-fees-and-breakeven.md`
(the source S40 cites) explicitly REFUSES the "5000 bps → 50% off my fill's fee" inference —
`discount_factor_bps` vs the separate `period_reward` pool are undocumented beyond field names, and
a Liquidity Incentive Program is structurally a reward *pool*, so the parameter is at least as likely
a reward weight as a fee discount. Building a strategy on it treats a plausible-unattacked number as
fillable (the pt1 failure mode). It also duplicates Q37 (whose own queue entry already owns the
"is the LIP window exploitable" sub-question, same tape gate, same fill-sim). The short-queue escape
is tape-refuted: `tape/weather_books/dt=2026-07-17.jsonl` shows a **median 4206 resting contracts/
market**, 1619/1920 markets already >1000; where the touch queue is short it is short because that
side has no flow (no taker crosses → no maker fill). No forecast signal (S1's maker-NO base rate is
+$0.00448/trade, CI lower bound −$0.005, already dead), and a queue-aware fill is unmeasurable at the
~31-snapshots/day (~hourly) cadence — the S6/S21 data-adequacy death. **Correction flag:** the
"confirmed-live 50% maker-fee discount" phrasing in this doc (and any repeat) overstates the source,
which flags the mechanic as unpinned.

## Data-quality byproducts (for a future research run / Ryan — NOT a strategy claim)

The verifier re-runs surfaced two concrete `collection/universe_sweep.py` (Q46/PR #107) issues beyond
the >80k-universe/storage design calls PR #107 already escalated:
1. **`volume_24h` is persisted as 0.0 on every census line** — likely a wrong source-field name
   (`volume_24h_fp`). A downstream consumer would silently read no 24h-activity signal at all.
2. **The 20k-call-cap census paginates a disjoint slice each pass** (0 ticker overlap across all 5
   committed passes), so `universe_sweep` is a set of one-shot cross-sections, NOT a per-market time
   series — any consecutive-sweep delta strategy is structurally impossible, and even entry-BBO→
   settlement joins get only the trickle of tickers that recur by luck. This compounds PR #107's
   already-flagged "cadence gated behind the storage decision." Recording here so the next probe over
   `universe_sweep` does not assume a per-market panel that isn't there.

