# Quant-finance literature — map & prioritized edges

`cited` · 2026-06-18 · built from a deep-research survey, citations triaged (trust=FALSE)

The question this KB answers: **where in the academic record is there a real, fee-robust
edge on a binary event market like Kalshi?** Seven themes below. Each links to a deeper
note where one exists. Confidence tags: `[classic]` canonical & verified, `[plausible]`
likely real but venue/year unverified, `[dubious]` flagged — do not quote without checking.
The dubious flags come from an explicit citation-hygiene pass (see `_sources`).

## The three fee-robust edges (priority order)

Ranked by how well they survive Kalshi's ~3–7¢ fee+overround bar (`../kalshi-api/03-fees-and-breakeven.md`):

1. **Calibrated weather post-processing** (Theme 5) → `01-weather-forecasting-alpha.md`.
   Informational edge from EMOS/BMA-calibrated ensemble distributions vs. participants
   reading public forecasts by rule of thumb. **Most aligned with these markets.**
2. **Inventory-aware market-making** (Theme 3) → `03-microstructure-and-kelly.md`.
   Earn the spread instead of paying it (maker fee is 4× cheaper). Liquidity premium in
   thin retail books, minus adverse selection.
3. **No-arbitrage / monotonicity scanning** (Theme 6) → `02-no-arbitrage-scanning.md`.
   Near-riskless when genuine: bracket additivity, threshold monotonicity, YES/NO
   complementarity. Rare and small, but mechanical.

Everything else is a supplement or a trap. Size all of it with **fractional Kelly** (Theme 4).

## Theme 1 — Efficiency & calibration

- Wolfers & Zitzewitz (2004), *J. Economic Perspectives* 18(2), "Prediction Markets" `[classic]` —
  prices ≈ well-calibrated probabilities, beat polls; deviations mainly at extremes.
  → treat the Kalshi price as a strong prior, not something to fade blindly.
- Berg, Nelson & Rietz (2008), *Int. J. Forecasting* `[plausible]` — accuracy rises with
  volume & trader diversity; thin markets less efficient → hunt mispricing in low-volume contracts.
- **Edge:** overlay a domain model on **thin / long-dated / extreme** contracts where depth is low.
- **Caveat:** miscalibration in *liquid* markets is small — often smaller than commissions. Dies after fees.

## Theme 2 — Favorite–longshot bias

- Ali (1977), *J. Political Economy* 85(4) `[classic]`; Thaler & Ziemba (1988), *JEP* 2(2) `[classic]` —
  bettors overbet longshots / underbet favorites; extreme-longshot loss can exceed 40%/$.
- Snowberg & Wolfers (2010), NBER WP 15923 `[classic]` — driven by *misperception of small
  probabilities*, not risk-love.
- (Griffith 1949 is real but the survey mis-cited its venue `[dubious]`.)
- **Edge:** fade overpriced longshot YES (<~5¢) when an independent model says the event is rare.
- **Caveat:** rarely flips to +EV after fees (only reduces loss); brutal tail risk — one hit
  erases many wins; attenuated on modern exchanges vs. parimutuel.

## Theme 3 — Microstructure & market-making

- Avellaneda & Stoikov (2008), *Quantitative Finance* 8(3) `[classic]` — optimal quotes =
  inventory-skewed band around a reservation price; spread ↑ with vol/risk-aversion, ↓ with
  order-arrival intensity.
- Cartea, Jaimungal & Penalva (2015), *Algorithmic and High-Frequency Trading*, CUP `[classic]`.
- Cont, Kukanov & Stoikov (2014), *J. Financial Econometrics* 12(1) `[classic, title mis-stated in survey]` —
  order-flow/book imbalance predicts short-horizon moves; small, decays.
- **Edge:** post two-sided A-S-calibrated, inventory-aware, vol-scaled quotes; capture the
  liquidity premium in thin retail-heavy books.
- **Caveat:** severe adverse selection around news & near resolution; competition compresses spreads. Not passive.

## Theme 4 — Optimal bet sizing (Kelly)

- Kelly (1956), *Bell System Tech. J.* 35 `[classic]`; Breiman (1961), 4th Berkeley Symp. `[classic]` —
  growth-optimal fraction f* ∝ (p − π) for a binary contract.
- MacLean, Thorp & Ziemba (2011), *The Kelly Capital Growth Investment Criterion*, World Scientific `[classic]` —
  fractional Kelly (α≈0.25–0.5) slashes drawdown/ruin for modest growth loss under uncertainty.
- **Edge:** size ∝ fractional gap (fair − market), at 25–50% of full Kelly, adjusted for cross-contract correlation.
- **Caveat:** Kelly is brutally sensitive to estimation error and the independence assumption —
  correlated weather contracts + overestimated p → catastrophic overbet even when directionally right.
  (This is why the project's hard rule #6 sets regime-conditional ρ, never static 0.4.)

## Theme 5 — Weather forecasting as alpha  ← **highest value for these markets**

- Gneiting, Raftery, Westveld & Goldman (2005), *Monthly Weather Review* 133, "EMOS / min-CRPS" `[classic]`.
- Raftery, Gneiting, Balabdaoui & Polakowski (2005), *MWR* 133, "BMA to calibrate ensembles" `[classic]`.
- Gneiting & Raftery (2007), *JASA* 102, "Strictly Proper Scoring Rules" `[classic]` — minimize CRPS ⇒ best full-distribution forecast.
- Alaton, Djehiche & Stillberger (2002), *Applied Mathematical Finance* 9, weather-derivative pricing (OU temp model) `[classic]`.
- **Edge:** EMOS/BMA-calibrated predictive distribution → integrate above each contract
  threshold for P(event) → trade the gap vs. Kalshi-implied. A genuine *informational* edge.
- **Caveat:** raw ensemble member-fractions are **underdispersed** — must post-process; sophisticated
  players (energy desks) likely already do this in liquid/short-horizon contracts; tail data is sparse.
  → details + the post-processing recipe in `01-weather-forecasting-alpha.md`.

## Theme 6 — Statistical arbitrage / no-arbitrage bounds

- Hausch & Ziemba (mid-1980s), *Management Science* `[classic]` — known cross-odds permit
  positive-payoff portfolios regardless of outcome.
- Carr & Madan (~2001) static replication / convexity constraints `[plausible]` — binary prices
  must be monotone in thresholds and additive across exhaustive partitions.
- Levitt (2004), *Economic Journal* 114 `[classic]` — bookmakers shade lines toward popular sides.
- **Edge:** automated scanner enforcing additivity / monotonicity / YES-NO complementarity across
  related Kalshi contracts; execute small portfolios when violations exceed fees. → `02-no-arbitrage-scanning.md`.
- **Caveat:** true arbs are rare, small, fleeting, capacity-limited; apparent violations often hide
  contract-definition/settlement differences — read the contract before assuming free money.

## Theme 7 — Behavioral mispricing

- De Bondt & Thaler (1985), *J. Finance* 40(3) `[classic]`; Barberis, Shleifer & Vishny (1998), *JFE* 49 `[classic]`;
  Tetlock (2007), *J. Finance* 62(3) `[classic]` — overreaction/sentiment → partial reversal.
- **Edge:** when price jumps on salient/emotional news *not* matched by a fundamental change
  (vs. your calibrated model), fade it expecting partial mean-reversion.
- **Caveat:** weaker and less persistent in prediction markets (fixed endpoint, transparent payoff)
  than in equities; sentiment vs. genuine info is hard to separate ex ante. Layered supplement only.

## Citation hygiene (trust=FALSE)

The source survey leaned on several **non-peer-reviewed or fabricated** references (a personal
blog, a YouTube video, an arXiv ID encoding year *2056*). Those were discarded. Venue/year for
`[plausible]`/`[dubious]`-tagged works must be verified against the primary source before any
of them is cited in a strategy dossier or used to justify capital. See `_sources/quant-finance-sources.md`.
