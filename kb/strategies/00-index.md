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
| **S6** | Inventory-aware market-making (maker rebate of spread) | QF Theme 3 | idea | — | A-S quotes; spread income > adverse-selection cost |
| **S7** | Kalshi WC/NBA-tail moneyline vs DraftKings no-vig closing line (CLV harvest) | FP→PR · cross-venue segmentation | **dead ✗** | med | TESTED n=80 games/237 outcomes: mean edge_after_fee −0.0235, 95% block-bootstrap-by-game CI [−0.0245,−0.0225] ⊄ >0 → falsified (taker side) |
| **S8** | Crypto-hourly settlement basis (CF BRRNY vs public spot) | FP→PR · settlement mismatch | **dead ✗** | med | TESTED n=18 hrs/symbol: ρ-guard (historical-spot, lag=0s) BTC 0.9997/ETH 0.9998, max gap never crosses half a band (0.00% both) → dies cheap, same as S5's NWS/WU |
| **S9** | Kalshi↔Polymarket same-question lead-lag (laggard leg) | FP→PR · cross-venue info lag | **dead ✗** | low | RESOLVED 2026-07-06: n=8 ticker-steps across 2 real round transitions, both venues repriced together every time (mean \|Δk−Δp\| 2.2¢) — collection cadence (hourly-min, platform trigger constraint) is coarser than the event itself; data-adequacy DEAD, not a CI falsification. Parity sub-question survives under S17. |
| **S10** | Crypto-hourly reachability decay (stale far-bracket pricing) | FP→PR · time-decay microstructure | idea | low | T-5/2 reachability vs ask > overround+fee; clear artifact floor; bootstrap by hour; CI>0 |
| **S11** | Sharp-anchored maker quoting on illiquid binaries | FP→PR · liquidity + Pinnacle filter | idea | low | fill-sim: rest only EV+-vs-Pinnacle side; captured spread > adverse-sel + maker fee; CI>0 |
| **S12** | Econ-print nowcast overlay (CPI/NFP/GDP brackets, maker-preferred) | 2026-07-04 gen pass · QF Themes 1+5 × econ category | **data-collecting** | med | ≥20 releases forward-collected real-ask ladders; paper taker AND maker-at-bid where \|nowcast−implied\| > overround share+fee; block-bootstrap by release; CI>0 |
| **S13** | S7-maker — bid side of the proven sports rich-ask | 2026-07-04 gen pass · S7c verdict inversion × maker lens | **dead ✗** | med | TESTED n=80 games/223 filled outcomes (94.1% fill rate): mean edge_after_fee +0.00009, 95% block-bootstrap-by-game CI [−0.00021,+0.00039] — straddles zero → null result. The maker fee alone (~1¢ at mid-range bid prices) consumes essentially the whole assumed 1¢ bid-under-fair margin. |
| **S14** | Ladder overround underwriting (short the complete bracket set) | 2026-07-04 gen pass · overround inversion × QF Theme 3 | idea | low | L2-tape fill-sim: E[overround × P(complete fill)] − E[loss on partial sets @ real asks] > 0, CI over ≥30 event-days |
| **S15** | Cross-event logical-implication scanner (A⇒B ⇒ P(A)≤P(B)) | 2026-07-04 gen pass · S3 extension × QF Theme 6 | **data-collecting** | 0.30 | `scripts/anomaly_sweep.py` (Q11, 2026-07-05) 3rd check + `config/implication_pairs.yaml` (hand-audited `kxwcround_progression` family); runs in existing daily 09 UTC slot; live-validated against real KXWCROUND markets (38 pairs/40 open markets, 0 hits — expected); kill if 0 fee-clearing hits in 60 days |
| **S16** | FedWatch-anchored shock fade on KXFED | 2026-07-04 gen pass · QF Theme 7 × S2 adjacency | idea | low | enter only \|Kalshi−FedWatch\| > spread+fee around releases; paper exit on convergence/T+24h; bootstrap by shock; CI>0; kill if Kalshi leads ZQ |
| **S17** | Kalshi↔Polymarket recurring-macro parity (S9 infra past Jul 19) | 2026-07-04 gen pass · S9 generalization × cross-venue | **data-collecting** | low | retarget matcher to Fed/CPI questions; ≥5 live-book pairs/month both venues; lead-lag xcorr + laggard paper fills @ real asks; CI>0 |
| **S18** | Single-poll overreaction fade (Congress-control markets) | 2026-07-04 gen pass · QF Theme 7 × elections category | idea | low | paper fade @ real ask when single-poll jump >3¢ while polling average moved <1¢-eq; exit reversion/T+72h; bootstrap by poll event; CI>0 before 2026-11 |

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
- **S10 (low).** Crypto-hourly reachability decay — far range-brackets stay priced above their
  remaining-time reachability as the hour elapses; retail under-updates the tails. Distinct from S3
  (conditional time-decay, not static monotonicity). Must clear the artifact noise floor + chunky longshot fee.
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
