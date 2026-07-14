# Order-flow imbalance — primary sources for the depth-imbalance settlement-predictor angle

`cited` · 2026-07-14 · QF Theme 3 deepened · standing-literature half of Q26/S22 · trust=FALSE

**The signal, stated for a cross-sectional predictor.** In a limit-order book the *net of
bid-side vs ask-side size changes* — **order-flow imbalance (OFI)** — is a strong, largely
linear predictor of the short-horizon price move: when resting bid depth grows relative to ask
depth, price tends to move up next, and vice versa. A participant who can *read the resting
depth* (not just the displayed BBO/mid) is on the correct side of that gradient. This note
distills the primary source for OFI, ties in the queue/book-imbalance and market-making
backdrop already in `00-overview.md` Theme 3, and — critically — carries forward the literature's
own load-bearing caveat: the effect is real but **small and decays fast** (seconds-to-minutes
in equities), which is exactly S22's central risk.

Every empirical claim below is tagged with its source. Literature magnitudes are the paper's;
any project number carries its `real_ask` / `real_bid` / `synthetic` / `broker_truth`
provenance.

---

## 1. Cont, Kukanov & Stoikov (2014) — order-flow imbalance as the linear price-impact driver

**(1) Citation.** Rama Cont, Arseniy Kukanov & Sasha Stoikov, "The Price Impact of Order Book
Events," *Journal of Financial Econometrics* 12(1), 2014, pp. 47–88. `[classic]` (The survey
in `00-overview.md` mis-stated its title; this is the correct one, verified from
first-principles knowledge.)

**(2) Market / sample.** U.S. equities — TAQ/ITCH-style message data on liquid large-cap
stocks, aggregating limit-order **book events** (arrivals, cancellations, market orders) at the
best bid and ask over short (sub-minute to minute) horizons. A message-level microstructure
study, not a daily-bar study.

**(3) Headline magnitude.** OFI — defined as the **net change in bid-side minus ask-side depth
at the best quotes** over an interval — explains short-horizon price changes with a **high
linear R²** (a single OFI regressor captures most of the contemporaneous move), and it
**largely subsumes trade imbalance** (signed trade volume): once OFI is in the regression, the
trade-based measure adds little. Treat the exact R² as `approx` (it varies by stock/interval);
the load-bearing result is the *direction and dominance* — book-event imbalance is the better
linear predictor. Crucially, the effect is **small in absolute terms per event and decays over
seconds-to-minutes** — it is an intraday microstructure signal, not a multi-hour one.

**(4) Mechanism it argues.** Price impact is driven by the **net order flow into the book**, not
by trades alone: a cancellation on the ask thins the offered side exactly as a bid arrival
thickens the demand side, and both push price the same way. Modeling the book's *net size
change* rather than only executed trades gives a cleaner, more stable linear price-impact
coefficient. This is the supply/demand-at-the-quote channel underneath the Avellaneda-Stoikov
reservation-price picture.

**(5) Relevance to Q26/S22.** Establishes that resting-depth imbalance genuinely leads price —
the theoretical warrant for reading `tape/orderbook_depth/`'s `yes_bids` vs `no_bids` ladders as
a predictor rather than noise. But it also supplies S22's **central risk in the same breath**:
the equity signal decays in seconds-to-minutes, whereas Kalshi depth is captured only hourly and
S22 must predict an hours-scale settlement — so the whole question is whether *any* predictive
content survives the horizon mismatch (the S9-family cadence-washout risk).

---

## 2. Backdrop — queue/book imbalance and the market-making frame (already in Theme 3)

**Cont & de Larrard — the queue/book-imbalance line.** The queueing-model tradition (Rama Cont
& Adrien de Larrard, "Price Dynamics in a Markovian Limit Order Market," *SIAM J. Financial
Mathematics* 4(1), 2013, `[classic]`) shows that the **imbalance between best-bid and best-ask
queue sizes** predicts the direction of the *next* price move under a Markovian book model — a
static-snapshot analog of source 1's flow measure (you can read imbalance off one book snapshot,
not only off event increments). This matters for S22 because Kalshi's hourly capture gives
**snapshots**, not the message stream source 1 used — so the queue-imbalance (level) reading is
the honest analog of what the tape can actually support, not the flow (increment) reading.

**Avellaneda & Stoikov (2008) — the microstructure backdrop.** OFI/queue-imbalance is the
"which way does price go next" companion to the A-S reservation-price/optimal-quote frame
already summarized in `00-overview.md` Theme 3: imbalance tells you the drift, A-S tells you how
to quote around it. S22 is the *taker-directional* read of that drift (predict settlement, lift
the imbalance side), not the maker/quoting read (which is S6/S11/S23 territory).

---

## Synthesis — what the literature predicts for S22

The sources agree on direction: resting book/queue imbalance is a **genuine, largely-linear
predictor** of the next short-horizon price move (source 1), readable off a snapshot under a
queueing model (source 2), and it dominates trade-based measures. For S22 that predicts a
**real cross-sectional signal**: the pre-close `yes_bids`-vs-`no_bids` imbalance should carry
information about the settlement outcome beyond what the mid already prices.

**The load-bearing caveat — horizon mismatch, not existence.** Every magnitude above is an
**equity intraday, seconds-to-minutes** figure, and the effect is small and **decays fast**.
Kalshi depth is captured **hourly** (`collection/orderbook_depth.py`, the same cadence floor
that killed S9's lead-lag and shaped Q25), and S22 must predict an **hours-scale** win
probability out to settlement. The whole edge therefore hinges on whether ANY of the fast-
decaying predictive content survives at hours-scale — which is **exactly S22's L28-style
calibration precheck** (does imbalance beat the mid at all, cheaply, before any CI machinery).
If it does not, S22 is a cheap cadence-washout DEAD in the S9 family; if it does, it is a
genuinely novel signal on the high-churn two-sided sports cells Q25 mapped. The literature
cannot answer the horizon question — only the precheck on real tape can.

## Citation hygiene (trust=FALSE)

Source 1 (Cont, Kukanov & Stoikov 2014) and source 2 (Cont & de Larrard 2013; Avellaneda &
Stoikov 2008) are real, peer-reviewed venues verified from first-principles knowledge; the
survey's mis-statement of source 1's title is corrected here. Where a magnitude (the OFI R²,
the exact decay horizon) was not certain it is marked `approx` or stated as direction only,
rather than fabricated — consult the primary source before any figure is used to size capital.
The project's own numbers (Q25 turnover/frozen cells, `orderbook_depth` sizes) carry their
`real_ask`/`real_bid` tags and are re-runnable.

## See also

- `00-overview.md` Theme 3 (microstructure & market-making) — the map entry this note deepens.
- `kb/strategies/00-index.md` **S22** — the OFI / depth-imbalance settlement predictor this note
  is the standing-literature half of (Q26).
- `favorite-longshot-bias.md` — the sibling Theme 2 deep note (S23's standing literature).
