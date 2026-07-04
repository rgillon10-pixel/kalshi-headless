# New edge candidates S12–S18 — raw generation → adversarial cut → synthesis

`drafted` · 2026-07-04 · idea-generation pass (no execution code, no capital recommendation)

Inputs: `kb/strategies/00-index.md` (S0–S11 state as of 2026-07-04), `kb/quant-finance/00-overview.md`
(7 themes), the dead-end ledger (weather family pt1/S1/S5, S7-taker, S8, Kelly-tilt, LIP, pin,
settle-source basis). Method mirrors the 2026-06-18 pass: force lens variety → reject harshly →
synthesize only what survives. Everything below is a falsifiable hypothesis with a real-ask gate;
nothing here is a claim of edge.

Fee bar used throughout: taker `roundup(0.07·C·P·(1−P))` ≈ 2¢/contract at P=0.5 (1¢ maker at
0.0175; S&P/Nasdaq taker 0.035). Overround priors from our own tape: ~9.8¢/ladder weather,
+21.3¢ sports moneylines (n=188), +$5–9 crypto ladders (mostly real, 34–43% floor artifact),
+3.4¢ FOMC, ~2–4¢ liquid 2-outcome sports.

---

## 1. Raw candidates (19, lens-rotated)

Format: **mechanism** / why it might clear fees+overround / what kills it.

1. **[T1/T5 × econ] CPI-bracket nowcast overlay.** Cleveland Fed's daily inflation nowcast
   (free, published, strong documented MoM accuracy) vs Kalshi CPI bracket ladder; trade the
   gap, maker-preferred. / A genuinely superior public model most retail doesn't consult;
   maker fee ~1¢; recurring monthly. / Print-day overround exceeds the model gap; rates pros
   already anchor the book.
2. **[T1 × politics] Long-dated political extreme-longshot fade** (perpetual 2–4¢ novelty
   contracts). / Longshot bias is worst at extremes. / S1's lesson: fading only *reduces* loss
   after fees; one tail hit erases months — same family, new category, same math.
3. **[T2] Extreme-favorite buying** where the fee →1¢ as P→1 (fee ∝ P(1−P)). / Cheapest fee
   zone on the exchange + documented favorite underpricing. / The last 2–3¢ of ask *is* the
   overround, concentrated; no independent anchor says 97¢ is "really" 99¢.
4. **[T3 maker × sports] S7-maker: rest bids at DraftKings-devig fair − fee** on the exact
   mispricing S7c proved (asks run +2.35¢ rich, CI [−2.45,−2.25] vs fair). / The mispricing is
   *proven at real asks*; the bid side is explicitly untested; maker fee 4× cheaper. / Adverse
   selection: you fill mainly when the true price moved through you first.
5. **[T3 maker × structure] Ladder overround underwriting** — rest short-YES across a complete
   bracket ladder at Σ(asks) > $1 + fees; a complete fill is a locked profit of the overround
   (exactly one strike pays $1). / Converts the #1 documented killer (+10–21¢/ladder we
   measured) from a cost into revenue; per-leg loss bounded at (1−price). / Partial fills:
   the leg that fills fastest is the one informed flow likes — incomplete sets are naked
   informed-side shorts.
6. **[T3] Two-sided A-S market-making on index dailies.** / Half taker rate on S&P/Nasdaq. /
   Duplicate of claimed S6 — rejected on duplication, not merit.
7. **[T4] Kelly-regime overlay as a standalone candidate.** / — / By the project's own framing
   Kelly is an overlay on a proven edge, never an edge; also adjacent to the dead Kelly-tilt.
8. **[T5 × econ] NFP bracket overlay** vs claims/ADP-based nowcast. / Same shape as #1. /
   Weaker public model than Cleveland Fed CPI — folded into #1 as one "econ-print family."
9. **[T5 × entertainment] Awards markets vs precursor-award model** (guild results predict
   Oscars with known reliability). / Thin books = miscalibration per Theme 1. / ~1 ceremony
   cluster/yr, fat overround, and the precursor signal is maximally public — priced.
10. **[T5 × earnings] Company earnings beat/miss vs whisper numbers or options-implied.** /
    Untouched category. / No free fair-value leg: whisper data paywalled, options imply the
    *move*, not beat direction — disqualified on the "real data for both legs" rule.
11. **[T6] Cross-event logical-implication scanner:** if event A ⇒ event B then P(A) ≤ P(B)
    across *distinct markets* (win final ⇒ reach final; presidency ⇒ nomination; shutdown ≥10
    days ⇒ shutdown occurs); buy YES(B)+NO(A) when the real-ask violation clears fees. /
    Mechanical, near-riskless when genuine; a curated implication graph is exactly what S3's
    within-ladder sweep does NOT cover. / Same as S3's risk: zero fee-clearing hits ever.
12. **[T6] YES/NO complementarity scan.** / — / Already inside S3's daily sweep — duplicate.
13. **[T6 cross-instrument] SPX 0DTE options-implied distribution vs KXINX range ladder.** /
    The listed-options book is the sharpest free-ish anchor in existence. / Professional MMs
    (e.g. Susquehanna) already quote Kalshi index markets off live SPX options; free chains
    are 15-min delayed — bringing a delayed knife to a colocated gunfight.
14. **[T7 × macro] FedWatch-anchored shock fade on KXFED:** when a macro headline jumps the
    Kalshi fed-funds book beyond where CME FedWatch (free, ZQ-derived) moved, fade toward
    FedWatch and exit on convergence. / Prob-vs-prob (no ladder overround), 2–3-outcome events,
    free anchor, several shocks/month; distinct from S2 (convergence round-trip, not
    hold-to-settlement basis, no CME tick data needed). / Kalshi *leads* ZQ instead of lagging,
    or the gap is persistently smaller than spread + fee.
15. **[T7 × elections] Single-poll overreaction fade** on Congress-control markets: fade
    jumps > x¢ that occur on one poll's release while the polling *average* barely moves. /
    Most liquid untouched category (tight spreads, low overround); dozens of poll releases
    before Nov 2026; round-trips exit on reversion so trades aren't all correlated to one
    settlement day. / Info vs noise is hard ex ante; Theme 7 is documented to be weak in
    prediction markets; runway ends Nov 2026.
16. **[T7 × entertainment] Box-office / news-jump fade.** / — / Thinnest books, fattest
    overround, no independent anchor — worst of every world.
17. **[cross-venue] Generalize S9's Kalshi↔Polymarket matcher to recurring macro questions**
    (Fed decision, CPI ranges) that exist on both venues monthly, forever. / S9's collector is
    already built and validated (48/48 WC matches); the WC window dies Jul 19 — this preserves
    the lead-lag thesis on a question family with unlimited runway. / Polymarket macro books
    too thin to quote a real ask, or lead-lag xcorr flat.
18. **[recurring by-date] Deadline theta on "X by date Y" contracts** — retail under-updates
    as time passes eventless. / Hazard-rate model vs price path. / Mechanism-identical to
    claimed S10 (reachability decay) — duplicate; revisit as an S10 generalization only if
    S10 tests positive.
19. **[econ × maker] Pre-release liquidity provision on CPI morning** with the nowcast as the
    quote anchor. / Spreads widen into the print — earn them with an informational anchor. /
    Not independent — this is #1's execution mode; folded into S12's design.

## 2. Adversarial rejections (one line each)

- **#2 political longshot fade — REJECT.** S1 established fading longshots only trims the loss
  after fees; category change doesn't change the arithmetic, and tail risk is worse on
  novelty contracts with no base-rate model.
- **#3 extreme-favorite buying — REJECT.** No anchor distinguishes a cheap 97¢ from a fair
  97¢; the residual spread is exactly where ladder overround concentrates; unbounded
  adverse-selection near settlement (pin-adjacent, and pin is in the dead ledger).
- **#6 index A-S MM — REJECT (duplication).** This is S6 verbatim; anything learned belongs on
  S6's card.
- **#7 Kelly standalone — REJECT (category error).** Overlay, not an edge; Kelly-tilt already
  dead.
- **#9 awards — REJECT.** ~Annual frequency fails the sample-size bar on its own; add thin
  books, fat overround, fully public precursor signal.
- **#10 earnings — REJECT (data).** No free, honest fair-value leg exists; disqualified, not
  discounted.
- **#12 complementarity — REJECT (duplication).** Already in S3's sweep.
- **#13 SPX options vs KXINX — REJECT.** The one Kalshi category with professional MMs
  anchoring to the exact instrument we'd anchor to, with better (undelayed) data; a 15-min
  delayed chain is negative edge.
- **#16 entertainment fade — REJECT.** No anchor + worst overround + thinnest books.
- **#18 deadline theta — REJECT (duplication).** S10's mechanism with a longer clock; don't
  fork an untested idea.
- **#8, #19 — MERGED** into #1 (S12) as the econ-print family and its maker execution mode.

Survivors: #1(+8+19), #4, #5, #11, #14, #17, #15 → seven candidates, S12–S18.

## 3. Synthesis — registry-ready rows

| id | name | source | status | conf | gate (binding test, abbreviated) |
|---|---|---|---|---|---|
| S12 | Econ-print nowcast overlay (CPI/NFP/GDP brackets, maker-preferred) | QF Themes 1+5 × untouched econ category | idea | med | ≥20 releases of forward-collected real-ask ladders; paper trades (taker AND maker-at-bid) where \|nowcast − implied\| > overround share + fee; block-bootstrap by release; net P&L/trade 95% CI > 0 at real asks |
| S13 | S7-maker — bid side of the proven sports rich-ask | S7c verdict inversion × maker lens | idea | med | fill-sim resting bids at DK-devig fair − 1¢ over S7 dataset + forward tape (fills inferred from candlestick trade-through); (fill-rate × edge_after_fee), adverse-selection-conditioned, block-bootstrap by game, 95% CI > 0 |
| S14 | Ladder overround underwriting (short the complete bracket set) | overround inversion × QF Theme 3 | idea | low | L2-tape fill-sim of complete-ladder short-YES resting at BBO asks: E[overround captured × P(complete fill)] − E[loss on partial sets marked at real asks] > 0, 95% CI over ≥30 event-days |
| S15 | Cross-event logical-implication scanner (A⇒B ⇒ P(A)≤P(B)) | S3 extension × QF Theme 6 | idea | low | daily sweep over a curated implication graph; hit = YES(B)_ask + NO(A)_ask ≤ $1 − fees at one snapshot with fillable size; kill if 0 fee-clearing hits in 60 days (S3's own verdict path) |
| S16 | FedWatch-anchored shock fade on KXFED | QF Theme 7 × S2 adjacency (free-data convergence, not basis) | idea | low | snapshot KXFED real asks + FedWatch around scheduled releases; enter only when \|gap\| > spread + fee; paper exit on convergence or T+24h; bootstrap by shock event; CI > 0 — kill if Kalshi systematically leads ZQ |
| S17 | Kalshi↔Polymarket recurring-macro parity (S9 infra past Jul 19) | S9 collector generalization × cross-venue | idea | low | retarget `polymarket_pairs.py` to Fed/CPI questions; require ≥5 matched pairs/month with live books both venues; lead-lag xcorr + laggard-leg paper fills at real asks, CI > 0; kill if PM macro books can't quote a real ask |
| S18 | Single-poll overreaction fade (Congress-control markets) | QF Theme 7 × untouched elections category | idea | low | log poll releases + polling-average deltas vs Kalshi control-market prints; paper fade at real ask when jump > 3¢ and average moved < 1¢; exit reversion/T+72h; bootstrap by poll event; CI > 0 before 2026-11 |

**S12 — Econ-print nowcast overlay.** The mechanism is Theme 5's *shape* — a better model of a
real-world process than the retail prices in — transplanted off weather onto a process with a
demonstrably strong free public model: the Cleveland Fed's daily inflation nowcast (CPI leg),
FRBNY/GDPNow (GDP leg), against Kalshi's KXCPI/payrolls/GDP bracket ladders read as `real_ask`
via the existing S0 substrate. Kill condition in cents: if the release-day ladder overround
absorbed per trade exceeds the model-vs-implied gap net of fees — concretely, if the
block-bootstrap-by-release 95% CI of net P&L/trade fails to clear $0.00 at real asks after ≥20
releases — the family dies exactly as weather did. It is NOT a weather repeat because the claim
being tested is different: weather died with the *model proven better* (EMOS CRPS −7.9%) but the
overround unbeatable at ~9.8¢; here the prior is that macro ladders are structurally cleaner
(S2's FOMC first cut measured +3.4¢, 3× cleaner) and the maker-at-bid mode (fee ~1¢, entering
inside the overround rather than paying it) is tested side-by-side from day one. Kalshi's 60-day
settled-data purge (S7a finding) means collection must start forward now; ~4 prints/month gives
a bootstrappable n in ~5–6 months.

**S13 — S7-maker.** S7c is the project's only *proven, signed, tight* mispricing: Kalshi
pregame asks run +2.35¢ (CI ±0.10¢) rich versus DraftKings' de-vigged close, at real asks,
n=80 games. The taker who pays that ask loses — decided. S13 tests the only untested trade in
that finding: resting a bid at devig-fair − 1¢ so that a fill happens at a price the sharp
anchor calls cheap, paying maker fee (≈1¢ at mid-prob) instead of taker. Both legs are already
built and free: `collection/sports_pairs.py` real-ask tape + ESPN/DraftKings closing lines; the
new work is a fill model (candlestick low/high trade-through against the hypothetical bid) with
adverse selection measured honestly — edge conditioned *on being filled*, not unconditional.
Kill condition: fill-rate × conditional edge_after_fee bootstrapped by game has a 95% CI ≤ 0 —
i.e., if you only get filled when DK-fair has already moved through your bid by more than the
2.35¢ cushion. Not a dead-idea repeat by construction: the dead S7 verdict explicitly scopes
itself to the taker side and names this trade as open.

**S14 — Ladder overround underwriting.** Every falsified candidate (pt1, S1, S5, S7-taker)
died to the same line item: 9.8–21.3¢ of measured real-ask overround per ladder that takers
pay and *someone collects*. S14 tests being the collector: rest short-YES across every strike
of a complete, exhaustive ladder at prices summing to > $1 + total fees + margin; exactly one
strike settles at $1, so a complete fill locks in the excess regardless of outcome, with per-leg
loss bounded at (1 − sale price). Both legs are internal: the S0 forward L2 tape (fill-intensity
estimation) and Kalshi candlestick volume (did takers actually lift at these levels). Kill
condition in dollars: if E[overround captured | complete] × P(complete fill within horizon)
minus E[mark-to-real-ask loss on incomplete sets] has a 95% CI ≤ 0 over ≥30 event-days — the
expected failure mode being that the winning strike's short fills eagerly while the wings never
do. It is NOT a repeat of S6/S11 (inventory MM / sharp-anchored quoting around a fair value):
S14 needs no fair-value estimate at all — its profit is the *structural* ladder excess, and its
only open question is fill completion vs adverse selection, which the tape can answer without
any model.

**S15 — Cross-event logical-implication scanner.** Theme 6, extended one axis beyond S3:
S3 sweeps monotonicity *within* a single ladder; S15 curates implication pairs *across distinct
markets* — "team wins final" ⇒ "team reaches final" (the KXWCROUND family literally lists both),
"candidate wins presidency" ⇒ "candidate wins nomination", "shutdown lasts ≥10 days" ⇒
"shutdown occurs" — and flags when YES(consequent) + NO(antecedent) can be bought at real asks
for under $1 − fees, a locked payoff. Both legs are the same free Kalshi book via the existing
client; the incremental build is a hand-audited implication graph (the audit matters: apparent
implications with mismatched settlement terms are the classic Theme 6 trap, so each pair's
rules text must be read before it enters the graph). Kill condition: zero fee-clearing hits
(≥$0.01 locked after both taker fees, at fillable size) in 60 days of daily sweeps — the same
frequency×magnitude verdict path S3 is on. Not a duplicate of S3 because S3's sweep is
structural-within-ladder and cannot see cross-event pairs; not previously falsified because no
prior candidate scanned across event families at all.

**S16 — FedWatch-anchored shock fade.** Theme 7 with the one thing Theme 7 usually lacks: a
free, sharp, continuously updated fundamental anchor. CME's FedWatch tool publishes ZQ-implied
meeting probabilities at no cost; Kalshi's KXFED markets are 2–4-outcome (near-zero ladder
overround — S2 measured +3.4¢) and are moved intraday by retail reacting to CPI prints,
Fedspeak, and headlines. The hypothesis: Kalshi overshoots the ZQ-implied move on salient
shocks and converges back within hours–days; the trade is a fade toward FedWatch entered at
real ask only when the gap exceeds spread + fee, exited on convergence — a round-trip, which is
what makes it distinct from S2 (a hold-to-settlement basis pre-position with unbounded
event-day downside, gated on paid CME tick data; S16 needs only free FedWatch snapshots and
bounded holding periods). Kill conditions: the post-shock gap is persistently < ~3¢ (spread +
taker fee on a mid-prob contract), or the sign test shows Kalshi *leading* ZQ rather than
lagging — either one ends it. Several scheduled shocks/month means a bootstrappable n inside
a quarter.

**S17 — Kalshi↔Polymarket recurring-macro parity.** S9's collector
(`collection/polymarket_pairs.py`) is built, validated (48/48 World Cup matches, real CLOB asks
both venues), and dies with the tournament on Jul 19. S17 retargets the identical machinery at
question families that recur monthly forever: Fed decision markets and CPI/inflation ranges,
which both venues list as structurally identical binaries (same matching discipline as S9 —
exact question equivalence with honest unmatched accounting, no "correlated proxy" pairs). The
mechanism is unchanged — KYC/rail segmentation keeps casual arbitrage from enforcing parity, so
the laggard venue can be traded toward the leader after a shared shock. Kill conditions:
Polymarket's macro books are too thin to quote a real fillable ask on ≥5 pairs/month, the
lead-lag cross-correlation is flat, or laggard-leg paper fills at real asks bootstrap to CI ≤ 0.
Not a duplicate of S9: same infrastructure, but a different market family whose value is
precisely that it *outlives* S9's window — and if S9's WC data shows a lead-lag signal before
Jul 19, S17 is the only way that finding compounds.

**S18 — Single-poll overreaction fade.** Elections are Kalshi's most liquid category and the
project has never touched them; liquidity means tight spreads and low overround — the fee bar
here is the lowest available for a Theme 7 idea. The mechanism is operationalized to dodge the
"sentiment vs information" trap: fade only price jumps > 3¢ on Congress-control markets that
coincide with a *single* poll release while the free polling averages (RCP / Silver Bulletin)
moved < 1¢-equivalent — i.e., the market moved on salience, not on the aggregate. Both legs
free: Kalshi book via existing client, poll releases + averages scraped from public trackers.
Exits on reversion or T+72h keep round-trips independent-ish rather than all correlated to one
November settlement. Kill conditions: bootstrap-by-poll-event CI ≤ 0, fewer than ~30 qualifying
events materialize before 2026-11 (sample-size death), or jumps qualifying under the filter
average < spread + fee. Not a repeat: no prior candidate touched elections, and unlike the dead
weather/sports takers this pays taker fees on a 1–2¢-spread book, not into a 10–21¢ ladder
overround.

## Priority note (not a capital recommendation)

Ordered by (proven-mispricing proximity × data readiness): **S13** first (the mispricing is
already proven at real asks; only the fill model is new), **S12** second (strongest free anchor,
recurring forever, but collection must start now due to the 60-day purge), **S14** third
(internal data only, reframes the documented killer), then S15 (cheap S3 add-on), S16, S17,
S18. All seven stay `idea` until each gate's collector/probe exists; per the working agreement,
building any collector is a separate approved task.
