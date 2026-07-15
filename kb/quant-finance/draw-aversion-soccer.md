# Draw-aversion in soccer betting — primary sources for the underprice-the-draw maker angle

`cited` · 2026-07-15 · QF Theme 2 (behavioral/sentiment bias) · standing-literature half of Q30/S29 · trust=FALSE

**The bias, stated for a draw-YES buyer.** In three-way (home / draw / away) football
(soccer) betting markets there is a documented **draw-aversion / team-sentiment** distortion:
bettors dislike backing the draw — there is no team to root for, no loyalty or fandom attached
to a tie — and so they **overbet the two named teams and underbet the draw**. This is an
**outcome-TYPE** bias (it attaches to *the kind of outcome*, "a tie," which sits at a
mid-probability of roughly **0.25–0.33** implied) rather than the **price-LEVEL** gradient of
the favorite–longshot bias (which attaches to how *unlikely* a runner is). A participant who
can **rest a bid on the draw (`-TIE`) leg** is therefore on the correct side of a distinct,
non-price-level distortion. This note distills the primary sources at the confidence they can
be verified from first principles, marks every uncertain specific as `approx`, and ties each to
Q30/S29 and to this project's OWN fee-floor findings on why edge-at-quote is not edge-at-fill.

Every empirical claim below is tagged with its source. Literature magnitudes are the paper's;
any project number carries its `real_ask` / `synthetic` / `broker_truth` provenance.

---

## 1. Forrest & Simmons — sentiment / loyalty in football betting markets

**(1) Citation.** David Forrest & Robert Simmons, work on **sentiment and loyalty in
(association) football betting markets** — the strand showing that bettor *affection* for
teams distorts prices (e.g. "Sentiment in the Betting Market on Spanish Football," *Applied
Economics*, `approx` 2008; and related Forrest–Simmons football-forecasting papers). Treat the
exact title / year / venue as `approx` — the load-bearing, verifiable content is the direction
of the finding, not a precise citation string.

**(2) Market / sample.** European club football fixed-odds and forecasting markets (Spanish and
English league fixtures across multiple seasons in the relevant papers). Fixed-odds bookmaker
prices on the three-way match-result market.

**(3) Headline magnitude.** Direction only (magnitude `approx`): where a large, well-supported
club is involved, **sentiment money flows to the supported team**, so the *team* legs are bid up
and the residual — the **draw** — is left relatively cheap. The papers frame this as loyalty
distorting demand, not as a clean cents-per-contract draw discount; do not quote a specific draw
underprice figure from this source.

**(4) Mechanism it argues.** Bettors derive **consumption / fan utility** from backing a team
they support, and will accept a worse price to do so. Demand is therefore not purely
belief-driven; it is skewed toward the two named teams. The draw, which no one *supports*,
receives structurally less of this sentiment-driven demand and can be underbid relative to its
true probability.

**(5) Relevance to Q30/S29.** Supplies the *why* for the specific leg S29 rests on: the draw is
the outcome nobody roots for, so it is the natural home of any residual underpricing left by
sentiment flow. Establishes the bias is demand-side and behavioral (an outcome-type distortion),
which is exactly why L54's closure of the *price-level* favorite/longshot maker lens does not
foreclose it.

---

## 2. Constantinou & Fenton — inefficiency and the draw in football gambling markets

**(1) Citation.** Anthony C. Constantinou & Norman E. Fenton, work on **inefficiencies in
football gambling markets and the difficulty of forecasting the draw** — e.g. "Profiting from an
Inefficient Association Football Gambling Market: Prediction, Risk and Uncertainty Using
Bayesian Networks," *Knowledge-Based Systems*, `approx` 2013; and their related "pi-rating" /
draw-forecasting papers. Exact title / year / venue marked `approx`; the verifiable content is
that they (a) build models that beat market odds on some football markets and (b) single out the
**draw** as the systematically hardest and most-mispriced outcome.

**(2) Market / sample.** English and European league match-result markets, several seasons of
fixtures, evaluated against published bookmaker odds with an explicit betting-simulation P&L.

**(3) Headline magnitude.** Direction only (magnitude `approx`): they report model-vs-market
edges on football markets and identify the **draw** as the leg where market prices are least
efficient — consistent with a draw that is mispriced relative to a well-calibrated model. Treat
any specific ROI figure as `approx` and do not port it to Kalshi.

**(4) Mechanism it argues.** The draw is intrinsically hard to forecast (it is not "a team
winning," it is the *absence* of a decisive result), and market prices reflect both that
difficulty and the demand-side skew toward the two teams — so the draw leg is where residual
inefficiency concentrates.

**(5) Relevance to Q30/S29.** Independent corroboration, from a modelling/efficiency angle
rather than a sentiment angle, that **the draw specifically** is the mispriced leg. Together with
source 1 (why: sentiment) this gives S29 both a behavioral cause and an empirical
"it-lands-on-the-draw" confirmation. Neither source, however, measures the effect on a modern
**exchange** or nets it of exchange frictions — see source 3 and the caveat.

---

## 3. Franck, Verbeek & Nüesch (2010) — the exchange-attenuation cross-reference

**(1) Citation.** Egon Franck, Erwin Verbeek & Stephan Nüesch, "Prediction Accuracy of Different
Market Structures — Bookmakers versus a Betting Exchange," *International Journal of Forecasting*
26(3), 2010, pp. 448–459. Already distilled in `kb/quant-finance/favorite-longshot-bias.md`
(source 3 there); cross-referenced here, not re-derived.

**(2) Market / sample.** European club **football (soccer)** match-result markets — the same
three-way product family as S29 — matching **Betfair exchange** prices against major bookmakers'
fixed odds on the same fixtures.

**(3) Headline magnitude.** Direction (accuracy delta `approx`): exchange prices are the more
accurate probability forecasts, yet a structural bias **persists in both** structures — it is
**attenuated on the exchange, not eliminated**, because informed money can *rest offers* there
instead of paying a bookmaker's vig.

**(4) Mechanism it argues.** Exchange structure lets informed traders **post** rather than
**take**, so their information is impounded into the resting book; the residual bias is what
survives that competitive resting.

**(5) Relevance to Q30/S29.** The load-bearing caveat by analogy: whatever draw-underpricing
sources 1–2 document in *bookmaker* markets should be **present but THINNER** on an
exchange-structured venue like Kalshi. S29 must therefore budget for a **thin edge-at-quote** and
let the fill-sim decide whether it survives frictions — the same expectation the favorite–longshot
note carries for Q24.

---

## Synthesis — what the literature predicts for a Kalshi maker resting the draw bid

The sources agree on direction: **the draw leg of a three-way football market is systematically
underbet** because sentiment/loyalty demand flows to the two named teams (source 1) and the draw
is the least-efficiently-priced outcome (source 2); and on an **exchange** any such structural
bias is **attenuated, not eliminated** (source 3). For a Kalshi maker that predicts a **small,
positive edge-at-quote** from resting a bid to buy the underpriced draw-YES (the `-TIE` leg).

**The load-bearing caveat — the literature measures edge-at-QUOTE, not fill rate or fee drag.**
Every magnitude above is a return-per-dollar-*matched* (or model-vs-market) figure. It says
nothing about (a) what fraction of resting draw bids actually **fill** — and the fill you get is
adversely selected, since informed sellers dump the draw exactly when a goal makes a decisive
result likely (the catastrophic no-draw leg that Q30 gate-2 forces into the P&L) — and (b)
Kalshi's **flat $0.01/contract maker fee at every interior price** (`L30`, `synthetic`/structural:
`fee_per_contract` is a flat 1¢ for all `0<P<1` because `0.0175·max[P(1−P)]·100 = 0.4375` always
ceils to 1¢). That 1¢ floor is the bar any realized draw edge must clear, and it is what killed
**S6** (spread-capture: fee exceeds the modal 1–2¢ spread's capturable half), **S13** (S7-maker
bid side: fee ate the whole assumed ~1¢ bid-under-fair margin, CI straddled zero), and **S19**
(wing-fade, 0.45% fill rate). A modest (~1–3%) draw underpricing may be **entirely consumed** by
one flat cent of fee plus sub-100% fills plus adverse selection.

**Relevance to S29/Q30, precisely scoped.** This note supplies the **WHY** (draw aversion /
team sentiment) and the **exchange-attenuation caveat** (budget for a thin edge). It does NOT
establish a Kalshi-specific magnitude and it does NOT gate the probe — it is the
standing-literature half of the milestone. Whether the draw leg is underpriced *at real Kalshi
`-TIE` bids* by more than the flat 1¢ maker fee survives at a realistic fill rate net of the
no-draw adverse-selection leg is an empirical question only the queue-aware fill-sim (Q30) can
decide, exactly as the fill-sim decided S13/S6/S19/S23.

## Citation hygiene (trust=FALSE)

The Forrest–Simmons and Constantinou–Fenton strands and the Franck–Verbeek–Nüesch (2010) paper
are real, peer-reviewed venues verified from first-principles knowledge. Where an exact
figure, year, or venue was uncertain it is marked `approx` or stated as direction only, rather
than fabricated — in particular the precise titles/years of sources 1 and 2 and any specific
draw-underprice or ROI magnitude are left as `approx`; consult the primary source before any of
these figures is used to size capital. This note is distinct from
`kb/quant-finance/favorite-longshot-bias.md`: that note covers a **price-level** gradient
(favorites vs longshots); this one covers an **outcome-type** bias (aversion to the draw), and
the two are separately actionable maker lenses. The project's own numbers (L30 flat-1¢ fee floor;
the S13/S6/S19/S23 fee-death verdicts) carry their tags and are re-runnable.
