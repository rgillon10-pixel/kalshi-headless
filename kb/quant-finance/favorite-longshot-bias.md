# Favorite–longshot bias — primary sources for the maker-SELL-the-longshot angle

`cited` · 2026-07-13 · QF Theme 2 deepened · standing-literature half of Q24/H1 (peer-review flag #13) · trust=FALSE

**The bias, stated for a seller.** Across a century of betting data, **longshots are
systematically overpriced and favorites underpriced**: the expected return per dollar staked
falls monotonically as the implied probability shrinks. A market participant who can *sell*
(lay / rest the offer on) the overpriced longshot is on the correct side of that gradient.
This note distills three PRIMARY sources — the taxonomy, the discriminating large-sample
test, and the betting-EXCHANGE analog closest to Kalshi's maker/limit-order structure — then
ties each to Q24/H1 and, critically, to this project's OWN findings on why edge-at-quote is
not the same as edge-at-fill.

Every empirical claim below is tagged with its source. Literature magnitudes are the paper's;
any project number carries its `real_ask` / `synthetic` provenance.

---

## 1. Ottaviani & Sørensen (2008) — the canonical taxonomy of explanations

**(1) Citation.** Marco Ottaviani & Peter Norman Sørensen, "The Favorite-Longshot Bias: An
Overview of the Main Explanations," in *Handbook of Sports and Lottery Markets* (Donald B.
Hausch & William T. Ziemba, eds.), Handbooks in Finance series, North-Holland / Elsevier,
2008, Chapter 6, pp. 83–101.

**(2) Market / sample.** A theoretical review chapter, not a new dataset — it organizes the
explanations that the empirical literature (Ali 1977; Thaler & Ziemba 1988; and others) has
proposed for the bias observed in pari-mutuel and bookmaker odds. Cite it as the *taxonomy*
anchor, not as a source of a fresh magnitude.

**(3) Headline magnitude.** None of its own; its contribution is the classification. It takes
as its stylized fact the well-documented pattern that expected return declines steeply from
favorites to longshots (the raw pari-mutuel figures are quantified in source 2 below).

**(4) Mechanism it argues.** It partitions the candidate explanations into families:
(a) **preference-based** — bettors are *risk-loving* over the longshot's lottery-like payoff,
so they willingly accept a worse price; (b) **misperception** — bettors *overweight small
probabilities* (prospect-theory probability weighting), overpaying for unlikely events;
(c) **market-maker / informed-trader models** — a monopolist bookmaker optimally shades the
longshot line against a pool of privately-informed and heterogeneous bettors, so the bias can
be a rational *supply-side* response, not only a bettor error. The key contribution for us:
these have *different* implications for whether an exchange participant can arbitrage the
bias, and (c) in particular says some of the bias is a market-maker's deliberate margin, not
free money.

**(5) Relevance to Q24/H1.** Establishes that "longshot is overpriced" is a robust,
multiply-explained stylized fact — but also warns that under the informed-trader family the
overprice partly compensates the resting seller for **adverse selection**. That is exactly
the risk a Kalshi maker resting the rich ask must survive, and it foreshadows why edge-at-quote
overstates realized edge.

---

## 2. Snowberg & Wolfers (2010) — the large horse-race test that discriminates the mechanism

**(1) Citation.** Erik Snowberg & Justin Wolfers, "Explaining the Favorite-Long Shot Bias: Is
It Risk-Love or Misperceptions?" *Journal of Political Economy* 118(4), 2010, pp. 723–746.
(Circulated earlier as NBER Working Paper 15923, 2010.)

**(2) Market / sample.** U.S. horse racing — on the order of **millions of horse-race starts**
(the authors assemble essentially the universe of North-American races over roughly a decade;
count stated as several million starts — treat the exact figure as `approx` rather than quote
a precise number here). Win-pool pari-mutuel odds, which are set by bettor demand, so prices
reveal preferences directly.

**(3) Headline magnitude.** The classic return gradient by odds: heavy **favorites lose only a
few cents per dollar** (on the order of **≈ −5%**, `approx`), while **extreme longshots lose on
the order of −60% per dollar** (`approx`, at the ~100/1-and-out end). The exploitable bias for
a *seller* is NOT the raw −60% — most of that is the uniform pari-mutuel **track take
(~15–20%)** that a seller on an exchange never collects. The exploitable component is the
**excess** of the longshot's loss over that take, i.e. the ~50-point *spread* between the
favorite and longshot return rates. Sell the longshot side and you are capturing that spread,
minus your own venue's frictions.

**(4) Mechanism it argues.** Using the full return curve as a discriminating test, they show
the data fit **misperceptions of probability** (specifically prospect-theory-style
*overweighting of small probabilities*) markedly better than **risk-love**: a risk-love model
calibrated to the longshot end makes counterfactual predictions elsewhere (e.g. in
simultaneous state-price / options-implied data), whereas probability-weighting reproduces the
observed curve. So the bias is a *demand-side cognitive* distortion, not (mainly) a rational
risk premium.

**(5) Relevance to Q24/H1.** If the bias is a persistent cognitive overweighting of small
probabilities rather than a fair risk premium, then the resting seller of the longshot is
harvesting a genuine mispricing, not merely being paid for bearing skew — supportive of H1's
premise. Caveat carried forward: this is *pari-mutuel* magnitude; the exchange analog (source
3) is smaller.

---

## 3. Franck, Verbeek & Nüesch (2010) — the bias on a betting EXCHANGE (the Kalshi analog)

**(1) Citation.** Egon Franck, Erwin Verbeek & Stephan Nüesch, "Prediction Accuracy of
Different Market Structures — Bookmakers versus a Betting Exchange," *International Journal of
Forecasting* 26(3), 2010, pp. 448–459.

**(2) Market / sample.** European club **football (soccer)** match-result markets over several
seasons of the big leagues, matching **Betfair exchange** prices against the fixed odds of
several major traditional **bookmakers** on the same fixtures. This is the structural analog
to Kalshi: an exchange where participants **REST limit offers against each other** rather than
cross a bookmaker's built-in vig — and it is the *soccer* domain, the same product family as
S7's World Cup moneylines.

**(3) Headline magnitude.** The **exchange (Betfair) prices are the more accurate probability
forecasts** than the bookmakers' odds (statistically superior forecast accuracy on the same
games), yet a **favorite-longshot bias persists in both** structures — it is *attenuated* on
the exchange, not eliminated. (Report the direction as the load-bearing result; treat any
single accuracy delta as `approx`.) Corroborated for horse racing by **Smith, Paton &
Vaughan Williams (2006), "Market Efficiency in Person-to-Person Betting," *Economica* 73(292),
pp. 673–689**, which likewise finds the bias present but **smaller on the person-to-person
(Betfair) exchange than with bookmakers**, because informed money can rest offers there.

**(4) Mechanism it argues.** Exchange structure lets informed traders **post** rather than
**take**, so their information is impounded into the resting book instead of being taxed away
by a bookmaker's spread; the residual bias is what survives that competitive resting. This is
the supply-side/informed-trader family of source 1, observed live on an exchange.

**(5) Relevance to Q24/H1.** The single most transferable finding: on an EXCHANGE (Kalshi) the
overpricing of the longshot is **real but smaller** than the pari-mutuel/bookmaker figures in
source 2 — so H1 should budget for a *thin* edge-at-quote, and the whole question is whether it
survives Kalshi's frictions. Resting the offer (H1's design) is exactly the mechanism this
literature says lets you capture the bias without paying vig.

---

## Synthesis — what the literature predicts for a Kalshi maker resting the rich longshot ask

The three sources agree on direction: the longshot is overpriced, the effect is robust and
multiply-explained (taxonomy: risk-love / misperception / informed-market-maker — source 1),
the demand-side misperception channel dominates in the discriminating large-sample test
(source 2), and the effect **survives on a betting exchange but attenuated** (source 3). For a
Kalshi maker, that predicts a **small, positive edge-at-quote** from resting the offer on an
overpriced longshot YES — sell the rich ask instead of crossing a book's vig.

**The load-bearing caveat — the literature measures edge-at-QUOTE, not fill rate or fee drag.**
Every magnitude above is a return-per-dollar-*matched* figure. It says nothing about (a) what
fraction of your resting offers actually **fill** — the adverse-selection concern that source
1's informed-trader family predicts precisely (the longshot offer that fills is
disproportionately the one you should not have wanted), and (b) Kalshi's **flat $0.01/contract
maker fee at every interior price** (`L30`, `synthetic`/structural — `fee_per_contract` is a
flat 1¢ for all `0<P<1` because `0.0175·max[P(1−P)]·100 = 0.4375` always ceils to 1¢). That 1¢
floor is what killed **S6** (spread-capture: the fee exceeds the modal 1–2¢ spread's capturable
half) and **S13** (S7-maker bid side: the fee ate the whole assumed ~1¢ bid-under-fair margin,
CI [−0.00021,+0.00039] straddled zero), and was re-confirmed lethal for the wing-fade **S19**
(0.45% fill rate, edge unsampled). A literature edge of a *few cents at quote* can be entirely
consumed by one flat cent of fee plus a fill rate far below 100%.

**This project's own confirmation that the raw material is there.** `findings/2026-07-04-sports-clv-s7-verdict.md`
(**S7c**) is the empirical anchor for H1: buying Kalshi WC/NBA moneyline at the **real taker
ask** against a DraftKings-devigged fair probability returned mean `edge_after_fee` **−0.0235**,
95% block-bootstrap-by-game CI **[−0.0245, −0.0225]**, n=80 games / 237 outcomes. Read from the
seller's side, that tight sub-zero CI means **Kalshi's sports ask runs ≈ +2.35¢ RICHER than a
DK-devig fair price** (`pregame_ask` = `real_ask`; `fair_prob` = `synthetic`, DK multiplicative
de-vig) — the taker loses by exactly the amount a *maker selling that ask* would, in principle,
be paid. S7c explicitly flags this maker/seller inversion as the untested angle its taker join
never covered; H1/Q24 is that test. The literature (this note) supplies the *why* (favorite-
longshot bias) and the exchange caveat (attenuated); S7c supplies the *Kalshi-specific
magnitude* of the raw richness; L30 supplies the fee floor any realized edge must clear.

**Factor-family cap.** H1 (short-the-overpriced-longshot, negative-skew premium harvested by
resting the rich offer) is the **same short-the-overpriced-tail factor family as S14** (ladder
overround underwriting). They share a risk factor — a common adverse move (the longshot/tail
*hitting*) hurts both at once — so they are one factor slot for exposure/correlation purposes,
not two independent edges. Any sizing must treat them as correlated (Hard Rule #6 / regime-
conditional Kelly ρ), and a portfolio should not double-count them as diversification.

**Bottom line for H1.** The literature predicts a real but *thin* edge-at-quote for resting the
rich longshot offer on an exchange; whether it clears Kalshi's flat 1¢ maker fee *at a
realistic fill rate* is an empirical question the literature cannot answer — only a queue-aware
fill-sim on real asks can, exactly as it decided S13/S6/S19/S14. This note is the standing-
literature half of the milestone; it does not gate the probe.

## Citation hygiene (trust=FALSE)

Sources 1–3 and Smith/Paton/Vaughan Williams are real, peer-reviewed venues verified from
first-principles knowledge. Where a specific magnitude was not certain it is marked `approx` or
stated as direction only, rather than fabricated — in particular Snowberg & Wolfers' exact
sample size and the precise Franck-et-al. accuracy delta are left as `approx`; consult the
primary source before any of these figures is used to size capital. The project's own numbers
(S7c −2.35¢, L30 fee floor) carry their `real_ask`/`synthetic` tags and are re-runnable.
