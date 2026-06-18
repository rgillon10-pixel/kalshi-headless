# Glossary

Precise definitions of every term this KB uses. A cold reader should be able to read any
note with only this open.

- **Binary contract** — a market settling YES=$1.00 (100¢) or NO=$0.00. Price in 1–99¢.
- **Bracket / strike** — one mutually-exclusive outcome within an event (e.g. the `73–74°F`
  high-temp bracket). The brackets of one event form an exhaustive partition.
- **bracket_sum** — the sum of YES asks across an event's brackets. By no-arbitrage it should be
  ~100¢; the excess is the overround. Normalize: `implied_prob = yes_ask / bracket_sum`.
- **Overround (vig)** — the amount the bracket asks sum *above* 100¢; the market maker's margin,
  paid silently when you lift the ask. ~3–5¢ in arb-bot's weather data — the pt1 killer.
- **yes_ask / no_ask** — the price you actually pay to *take* (buy) YES / NO. The **only** price
  that counts for proving an edge. `yes_ask ≈ 1 − best_no_bid`.
- **Real ask** — a `yes_ask/no_ask` that came from an actual orderbook (fillable). Opposite of
  **synthetic** (a model probability) or **midpoint** (between bid and ask, not fillable).
- **price_source_tag** — provenance stamp required on every persisted price:
  `real_ask` / `midpoint` / `synthetic` / `broker_truth`. Untagged ⇒ assumed `synthetic`.
- **Maker / Taker** — maker posts a resting limit order (adds liquidity, fee rate 0.0175); taker
  lifts an existing order (removes liquidity, fee rate 0.07). Maker fee is 4× cheaper.
- **Fee** — `roundup_to_cent(rate · C · P · (1−P))`, per trade. ~1–2¢/contract at mid prices.
- **CRPS** — Continuous Ranked Probability Score; a strictly proper scoring rule for a full
  predictive distribution. Minimizing it ⇒ the profit-optimal probability for threshold contracts.
- **EMOS / BMA** — Ensemble Model Output Statistics / Bayesian Model Averaging: post-processing
  methods that turn an underdispersed raw ensemble into a calibrated predictive distribution.
- **Underdispersion** — raw ensembles are systematically overconfident (too-narrow spread);
  the reason you can't read probabilities off raw member fractions.
- **Favorite–longshot bias** — bettors overprice longshots and underprice favorites.
- **Kelly fraction** — growth-optimal bet size ∝ (fair − market) / odds. Use **fractional Kelly**
  (25–50%) under estimation error; this project uses **regime-conditional ρ** (hard rule #6).
- **Bootstrapped CI** — confidence interval on a backtest statistic from resampling trades. The
  graduation gate: an edge must show a CI **strictly > 0 at real asks**.
- **Binding test** — the single cheapest experiment that would prove or kill a candidate.
- **orderbook_delta** — the Kalshi WebSocket channel giving a snapshot + incremental book updates,
  with a `seq` number for gap detection.
- **KXHIGH** — the Kalshi daily high-temperature market series the repos trade.
- **FEx / ForecastEx** — Interactive Brokers' event-contract venue; settles on Weather Underground.
- **pt1 / pt2** — the prior live attempt (pt1, lost 9.6%) and the soak rebuild (pt2).
- **Maturity tags** — `stub → drafted → cited → reproduced → battle-tested` (see `README.md`).
