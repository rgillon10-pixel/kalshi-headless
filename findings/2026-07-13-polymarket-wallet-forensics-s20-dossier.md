# S20 — Polymarket wallet forensics: dossier (HYPOTHESES ONLY, zero Kalshi evidence)

`2026-07-13` · prereg: `findings/2026-07-13-polymarket-wallet-forensics-s20-prereg.md`
(written before any wallet data was pulled) · script: `scripts/s20_wallet_forensics.py`
· raw data: `data/s20_wallet_forensics/` (gitignored; fully re-pullable from public APIs)
· every number below: **`polymarket_onchain`** — none is evidence of Kalshi edge (C5)
· council: CONDITIONAL 3-0 → C1–C5 all honored · status: **PEER-REVIEWED — APPROVE
WITH NOTES (as corrected); S20 CLOSED, premise DEAD, H1/H2 stand**

## Question

Do Polymarket's top-PnL wallets show statistically persistent per-trade skill, and do the
skilled wallets' patterns suggest ≤3 falsifiable Kalshi strategy candidates?

## Data & honest accounting

- Selection: top 50 wallets, public leaderboard, 30d PnL window (captured 2026-07-13,
  `captured_at=1783964116`).
- Fills: 134,843 across 50 wallets (`data-api /trades`, takerOnly=false ∪ true;
  maker = set-difference on fill key). **35/50 wallets hit the API's ~3,500-fill history
  cap** — their reachable history is recent-only. **6 wallets returned 0 fills**
  (unevaluable; folded into the insufficient-n bucket — first draft said "1", corrected
  at verification). 493 collection calls, 0 errors.
- Resolution join: 5,332 unique conditionIds sampled (cluster-sample cap 250
  markets/wallet, seed 20260713, uniform → mean-e_i estimator unbiased;
  `data/s20_wallet_forensics/resolve_sampling.json` logs per-wallet truncation):
  1,432 via gamma, 3,890 via CLOB `/markets/{cid}` (the 5-min updown family lives only
  there), **10 unjoinable** (recorded, excluded). 4,167 calls, 0 errors.
- Evaluation modes (pre-registered): 22 wallets `pre-window` (trades older than the
  selection window — clean split), 15 `within-window-split` (first-half-by-time
  fallback, flagged), 13 `insufficient-n` (<100 evaluable fills).

## Result 1 — the skill filter confirms (mostly) the null

Of **37 evaluated** wallets, exactly **1 formally survives** Benjamini–Hochberg FDR at
q=0.10 (and Result 2 discredits it — credible survivors: **0**). 16 of 37 have a
**negative** mean per-trade edge despite top-50 PnL. The leaderboard leaders themselves
(all verifier-recomputed, correctly attributed): **#1** `0x3a8aa345…` ($382,750 30d PnL,
5-min crypto-updown grinder) — pre-window mean edge **−4.9¢/trade**, p=0.909, n=310;
**rank 3** `0x2c335066…` ($198k) — **−3.0¢**, p=0.984 (within-window-split); extreme
case `0x8c80d213…` (rank 47, sports) — **−27.8¢**, p=0.94, n=3,248. Rank is size ×
recent variance, the textbook lottery-winner signature the council predicted.
*(Correction note: the first draft attributed the −27.8¢/n=3,248 figure to the #1 wallet
— wrong wallet, rank, PnL, and category; caught by independent verification. The
qualitative conclusion — top-ranked wallets show flat-to-negative per-trade edge —
survives with the corrected numbers.)*

Taxonomy (labels per pre-registered thresholds): **31/37 wallets are
`passive-maker/spread-capture`** (maker share ≥50%). The leaderboard's PnL engine is
market-making at scale — spread + size (+ liquidity-rewards subsidy), not directional
skill. Kalshi analogs of generic MM are already TESTED-DEAD here at our fee/latency
(S13: maker fee eats the 1¢ margin; S19: wing-maker fill-rate floor).

## Result 2 — the single FDR survivor, and why we distrust our own metric on it

`afkpnlucl` (0x55eca…8c7d): mean e = **+6.6¢/trade**, boot CI90 [+1.3¢, +9.3¢], n=174 —
but every one of those 174 evaluation fills is a **maker SELL of a longshot "Will X win
the 2026 World Cup?" YES token at median 10.6¢**, across only **8 market clusters**
(Portugal 95, Mexico 27, South Korea 22, …).

**Degenerate significance (verifier finding, stronger than the first draft's self-flag):
all 8 evaluation clusters resolved to 0 — every longshot this wallet sold LOST.** With
no losing cluster, the by-market cluster bootstrap cannot produce a single resample ≤ 0,
so p is **structurally 0.0** regardless of the wallet's true edge — the "significance"
is a mechanical artifact, not a skill test. Root cause: the evaluation set conditions on
markets RESOLVED during the sample; in long-horizon winner ladders, early resolutions
are disproportionately longshot eliminations, and the catastrophic leg (a sold longshot
that goes on to win, −89¢ at this median) is structurally absent. The wallet's
unresolved in-window book (Spain 549, England 425, France 235 — still alive) is exactly
the unpriced tail. **This wallet's formal FDR survival carries no evidentiary weight**;
credible skilled-wallet count for the sprint is ZERO. 8 clusters is also below any
comfortable bootstrap floor (cf. S19's data-adequacy lesson). Lesson candidate: a
positive-edge claim requires **≥1 losing cluster** in the resample unit, else p=0 is
mechanical and must be rejected.

## Emitted hypotheses (C5: ≤3, counterparty + falsifiable probe named)

**H1 — Maker-side longshot-ask selling on sports/event markets (the S7c mirror nobody
tested).** S7c PROVED (our tape, real asks) that Kalshi pregame sports asks run
**+2.35¢ rich** vs DraftKings-devig fair (n=80 games, CI [−0.0245,−0.0225] for the
taker). S13 tested resting *bids at fair−1¢* — DEAD (fee ate margin). But the direct
mirror of S7c — **resting the rich ASK itself** (selling YES / making on the NO side at
the S7c-measured rich prices, concentrated in the longshot tail where richness is
largest) — is untested. **H1's evidentiary basis is S7c alone**; the Polymarket
survivor contributes nothing after Result 2's degeneracy finding (at most it shows the
trade shape occurs in the wild). Counterparty: retail lottery-ticket buyers crossing
the spread pregame — but the binding *competitor* is the incumbent maker queue already
posting those rich asks (S7c's richness is being harvested by whoever posts it; we'd be
joining that queue, which is why fill rate, not edge-at-quote, is where this dies —
cf. S19). Probe: queue-aware fill-sim (L39 — `orderbook_depth` tape, never candlestick
prints) on the ask side of `sports_clv` games, maker fee 0.0175, block-bootstrap by
game, **explicit negative-skew accounting: the sold-longshot-wins leg modeled, not
conditioned away** (the exact artifact in Result 2), and the ≥1-losing-cluster floor
enforced. Kill: CI straddles zero, or fill rate below S19's floor. Factor-overlap note:
H1 and S14 are the same family (short-the-overpriced-tail, collect premium, wear
negative skew) — if both ever graduate they share a factor cap, recorded now.
Citation TODO before H1 becomes a Q-item: cite 2–3 primary favorite-longshot-bias
papers into `kb/` (the sprint itself has zero academic citations — flagged at review).

**H2 — Exclusionary (negative) finding: "copy the Polymarket whales" is structurally
void.** The top of the leaderboard decomposes into (a) rewards-subsidized MMs
(31/37 — non-transferable; Kalshi analogs S6-hourly/S13/S19 already DEAD), (b) lottery
winners with flat-to-negative per-trade edge (16/37 negative; #1 wallet −4.9¢, rank-3
−3.0¢), and (c) one longshot-seller whose formal significance is a degenerate-bootstrap
artifact (Result 2). Caveat on the 15 `within-window-split` wallets: their p-values are
structurally optimistic (first-half trades contributed to the PnL that selected them) —
none may be cited as near-significant skill. Value: this closes the premise with data,
so no future loop re-chases it. One-regime caveat: a single July-2026, World-Cup-heavy
snapshot; the 31/37 MM mix may be seasonal, the exclusionary conclusion is not (it
rests on mechanism, not mix). Recorded as a lesson candidate, not a strategy.

**No third hypothesis.** Nothing else in the data earns one (prereg allows ≤3; honesty
over quota). Note: S14 (ladder overround underwriting, our first non-DEAD candidate) is
*qualitatively* the same trade shape as the survivor's — short the overpriced tail,
collect premium, wear negative skew — which is mild convergent comfort for S14's
direction, and changes nothing about S14's binding gate (queue-aware fill-sim, CI>0).

## C4 compliance & premise verdict

One sprint, no filter loosening, no threshold retuning. Formal FDR survivors: 1;
**credible survivors after the degeneracy audit: 0** — so per the prereg's C4 spirit,
the premise "top-earner mining yields new transferable strategies" is **DEAD**. The
sprint's live output is H1 (a probe-able Kalshi question whose evidence is our own S7c
finding, not Polymarket) and H2 (a recorded dead end). Verdict on S20 as a *continuing
strategy family*: **CLOSE** — one-shot sprint, not a recurring collector.

## Peer review (2026-07-13)

Two-pass review completed same day. Skeptic flags: #2 (8-cluster survivor = LOW
confidence by definition), #3 (within-window-split optimism), #6 (single regime),
#8 (maker-queue competition folded into H1), #11 (H1/S14 factor overlap), #13 (zero
academic citations — TODO before H1 Q-item). Validator (independent `verifier` agent,
full recomputation from raw fills, scratch script `recompute.py`): 8/10 claims
CONFIRMED; 2 REFUTED and corrected in place (zero-fill wallet count 1→6; the −27.8¢
example mis-attributed to the #1 wallet — the founding pt1 failure mode, caught);
plus the degenerate-p finding (all 8 survivor clusters won → p mechanically 0),
incorporated into Result 2. **Verdict: APPROVE WITH NOTES (as corrected)** —
hypotheses-only status affirmed, S20 CLOSED, H1 eligible to become a Q-item with the
citation TODO and the ≥1-losing-cluster floor as binding probe requirements.
