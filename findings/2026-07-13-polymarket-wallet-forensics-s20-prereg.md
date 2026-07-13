# S20 pre-registration — Polymarket wallet forensics (written BEFORE any wallet data was pulled)

Date: 2026-07-13 · Status: PRE-REGISTERED · Capital: $0 (read-only research sprint)
Pipeline: /first-principles (GO, research scope) → /council (CONDITIONAL 3-0) → this prereg → sprint → /peer-review

Council conditions this document satisfies: **C1** (skill metric pre-registered), **C3**
(pattern taxonomy pre-registered). C2 (hour-1 feasibility gate), C4 (timebox/stop), C5
(tagging + counterparty naming) are binding run rules recorded here for the audit trail.

## Question

Among top Polymarket wallets by leaderboard PnL, does a non-empty subset show
statistically persistent per-trade skill — and do the skilled wallets' behavior patterns
suggest ≤3 falsifiable Kalshi strategy candidates?

## Selection vs. evaluation split (kills selection-on-test-variable)

- **Selection**: top ~50 wallets from the public leaderboard, most recent ~30d PnL window.
- **Evaluation**: per-trade skill computed ONLY on trades **outside** the selection window
  (older trades, target lookback ≈ days 31–180) in markets that have since RESOLVED.
  If the API cannot serve pre-window history at usable depth, the fallback is a
  within-window temporal split (select implicitly on full-window PnL, evaluate on
  first-half trades only) — weaker, and must be flagged as such in the dossier.

## C1 — skill metric (fixed now, not tunable after seeing data)

- Universe per wallet: fills in binary markets with known resolution; require **n ≥ 100**
  evaluation trades, else wallet is `insufficient-n` (descriptive only, never "skilled").
- Per-trade edge: `e_i = sign · (outcome − price)` where outcome ∈ {0,1} is the resolved
  value of the token bought/sold, price is the fill price, sign = +1 for buys, −1 for
  sells. This is entry-price-vs-resolution improvement (CLV analog).
- Statistic: **unweighted mean** of `e_i` (primary; size-weighted reported descriptively).
- Uncertainty: cluster bootstrap **by market** (fills in one market are correlated),
  10,000 resamples, one-sided p-value under H0: mean edge ≤ 0.
- Multiplicity: **Benjamini–Hochberg FDR at q = 0.10** across ALL wallets evaluated
  (denominator = wallets evaluated, not wallets surviving n-filter).
- "Positive PnL across ≥3 categories" is DESCRIPTIVE ONLY — never the skill test (council
  C1: categories share regime in any 90d window).

## C3 — pattern taxonomy (fixed now; wallets are assigned, patterns are not invented)

1. **news-reaction taker** — clusters of taker fills shortly after public information
   events; short time-to-resolution positions entered mid-life.
2. **longshot/favorite harvester** — systematic selling at <15¢ or buying at >85¢
   across many markets (harvesting the favorite-longshot bias).
3. **resolution-endgame sniper** — buys at 90–99¢ concentrated in the final hours/days
   before resolution (earning the last cents on near-certainties).
4. **cross-market structural arb** — offsetting/complementary positions across related
   markets or outcomes (incl. negative-risk style constructions).
5. **passive maker / spread capture** — high two-sided fill activity, short holding,
   fills on both YES/NO sides of the same markets. (Likely rewards-subsidized →
   presumptively NON-transferable; classified to be excluded, not copied.)
6. **event-drift position trader** — early accumulation, held to resolution,
   category-concentrated.
7. **unclassified** — recorded honestly; not shoehorned into 1–6.

## C2 — hour-1 feasibility gate (STOP conditions)

STOP and report infeasible if the public API cannot provide, per wallet: fill-level
records with price, size, side, timestamp, market identifier; joinable market resolution
outcomes; and maker/taker attribution **or** a defensible proxy for it (e.g., on-chain
OrderFilled maker/taker roles, or classification-by-behavior with the limitation stated
in the dossier and echoed at peer-review).

## C4 — timebox & stop

One sprint. If zero wallets survive FDR: record a DEAD-style verdict for S20's premise;
NO filter loosening, NO threshold retuning, no second look.

## C5 — output contract

Every number tagged `polymarket_onchain`. Output is ≤3 HYPOTHESES; each must name its
Kalshi counterparty and a falsifiable probe criterion (probe on our tape, block-bootstrap
CI at real asks) before it can become a Q-item. Nothing here is evidence of Kalshi edge.
Wallet PnL is never treated as our fillable P&L (the synthetic-price lesson, new costume).
