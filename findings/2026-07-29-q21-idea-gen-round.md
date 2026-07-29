# Q21 idea-gen round — 2026-07-29 (kalshi-edge-hunter → independent verifier, two-agent rule)

**3 surveyed, 1 executed to a numeric kill, 0 registered.** Consumes S57/S58/S59 for provenance
→ next free **S60**. Still **0 proven edges.** The 16th consecutive zero-registration round (last
genuine round was 2026-07-26; the 07-27 edge-hunter reasoned-skipped to close the time-critical L180
FOMC gate instead).

## Why the round fired

Re-eligibility trigger met: a full Q0–Q48 rescan (this run's steps 0/0a/0b + the last week of
research-loop firings, all logged) finds **0 eligible TODO/IN-PROGRESS** items — every item is DONE,
credential/auth-BLOCKED (Q32/Q33/Q35-build/Q42-pt3/Q47), calendar-gated-not-open (Q19/Q48/S55 FOMC
burst opens **today 2026-07-29 17:40–19:45 UTC**, Q37 ~08-05), or gate-open-but-density-inadequate
(Q36 both legs, Q43). Fewer than 2 eligible → Q21 standing replenishment condition satisfied.

This round deliberately did **not** pad to quota with three shallow re-treads (which is what the last
several dry rounds became, per the retro's anti-treadmill note in open PR #208). Instead it executed
**one** genuinely-new, cheaply-falsifiable candidate — S57 — through the full producer + independent
`verifier` two-agent gate, and documents two more (S58/S59) as surveyed-and-foreclosed at the idea
stage. Quality over quota; 0 registered is a valid honest outcome.

## S57 — Complete-set underpricing arb (the INVERSE of the dead taker-into-overround wall) → KILL / hollow-book false positive

**Mechanism.** S1/S5/S7 are all dead because you cannot *take* into a bracket ladder whose YES asks
sum to *more* than \$1 (the overround). S57 asks the complementary, un-foreclosed question: is any MECE
ladder ever *under*-round enough that buying **every** YES leg costs **less** than the guaranteed \$1
payout, net of fees — a genuine riskless arb (the one shape that beats, rather than pays, the
overround)? The check is exactly `core.pricing.true_arb_edge(bracket_sum, total_fees) > 0` — the same
math as **Q6**'s "bracket sums vs \$1 + fees", but asked as a directed *buy-side* strategy rather than
a passive anomaly sweep. Counterparty: a maker who has left the *whole* ladder mispriced low; they
lose the locked spread. Data: already-collected `tape/crypto_hourly/` (all `real_ask`), plus a
cross-family look at `weather_books`. Gate: ≥1 event-hour with edge>0 where **every** leg carries a
real, buyable, sized offer. Kill condition: 0 such event-hours, or every positive-edge hit is a
hollow book.

**Kill (producer census, verifier-CONFIRMED independently — the verifier re-derived every number from
`core.pricing` + raw tape with its own script and extended the census to a second family).** Over
**1,397** real crypto_hourly ladders (1,467 capture-lines minus **70 empty-ladder captures** — the
documented ~20:00Z crypto venue hole, whose 0 outcomes give a spurious `true_arb_edge`=+\$1.00 and are
correctly excluded), **exactly 1** shows a positive `true_arb_edge` (`KXETH-26JUL1410`, capture
`20260714T130028Z`, bracket_sum 0.22, apparent edge +\$0.56) — and it is a **hollow-book artifact**,
not an arb: of its 75 legs only **22 carry a real offer** (`yes_ask > 0`, all at the 1-cent floor),
and the verifier's key catch is that **all 22 offered legs are deep-OTM tails guaranteed to settle NO
(ETH spot ≈\$1856; the 22 strikes sit at 1030–1250 and 2250–2490), while the near-spot bracket that
will actually settle YES has NO offer at all.** The other **53 legs have `yes_ask == 0` — no offer, so
they cannot be bought**. You physically cannot assemble the complete set, and the 22 you *can* buy are
the ones certain to lose. The "+\$0.56" is fictional liquidity. Every other event-hour is over-round
(bracket_sum ≥ 1 + fees), i.e. the S1/S5/S7 wall.

**The kill generalizes across families (verifier Task 3).** Reconstructing `weather_books` ladders
(9,752 snapshots — this family *does* carry `depth`/`yes_bids`/`best_yes_ask`), **1,097 show
edge > 0 but ZERO have every leg carrying a real offer.** The top case (`KXHIGHAUS-26JUL15`, apparent
edge +\$0.90) is a stale post-settlement book: 6 legs captured, five 1-cent asks on losing tails, the
winning bracket unbuyable — the identical hollow/incomplete-capture artifact. So the false-positive is
not a crypto quirk; it is what `true_arb_edge > 0` *means* on any MECE ladder that isn't fully offered.

Two compounding reasons the kill is structural, not a data-window artifact:
1. **`bracket_sum < 1` is itself the fingerprint of a hollow book on a genuinely-MECE ladder.** A
   complete N-member mutually-exclusive ladder that is fully quoted has bracket_sum ≥ 1 (+ overround)
   by construction. A sum well below 1 means most legs have no live YES offer — exactly the L168/L169
   hollow-crypto-ladder failure mode (a 200-OK fetch of an at/after-close ticker returns an empty
   book still tagged `real_ask`). `completeness_ok == True` does **not** rescue it: that flag means
   the *capture* got all the ticker rows, not that the *book* has offers.
2. **crypto_hourly carries no `yes_ask_size` field at all** (confirmed — same gap S53 hit), so even
   the 22 offered legs on the one hit have unverifiable depth. The complete-set arb needs every leg
   simultaneously fillable at size; the tape cannot even in principle establish that here.

Price provenance (verifier-confirmed): the yes_ask values are all tagged `real_ask`, and a
`yes_ask == 0.0` is a real *absence* of an offer, not a \$0 fill; fee via
`core.pricing.fee_per_contract` at the correct taker rate **0.07** (the 1-cent per-contract floor
applied). `spot.price_source_tag` is `synthetic`, but spot is not an input to `true_arb_edge`, so it
does not taint the census. So the kill is a genuine data-adequacy / fill-wall death, not a provenance
error — the same terminal shape as L168/L169, now shown to also manufacture a **false-positive
`true_arb_edge`** if a census trusts `bracket_sum` without an all-legs-offered guard.

**Transferable lesson (corollary of L168, not a new ID — verifier's recommendation).**
`completeness_ok` and `member_count == captured_outcomes` certify brackets *captured in the snapshot*,
NOT brackets with a *live buyable YES offer* (KXETH-26JUL1410 has `completeness_ok=True`,
`member_count == captured_outcomes == expected_outcomes == 75`, and is still hollow). Any complete-set
/ `true_arb_edge` census must additionally require every leg `yes_ask > 0` **and** a real ask-size
before treating `bracket_sum` as the cost of the set; on crypto_hourly (no `yes_ask_size` field) even
the offered legs' depth is unverifiable, so a positive `true_arb_edge` there can never clear the
fillable-arb bar. Recorded as the S57 corollary under **L168** (deferred to `kb-distiller`), not a new
lesson number.

## S58 — FOMC-instant cross-asset dislocation maker-fade → DEFER (Q19/S17 domain, not a new slot)

Rest a maker on an over-extended crypto-ladder wing in the seconds after the 18:00Z Fed statement and
collect the reversion. Surveyed and **not registered**: this is already Q19/S17's burst lead-lag /
dislocation territory, which is registered and **burst-gated to today's FOMC tape** (arriving in ~13h)
— proposing it as S58 would duplicate a live queued item, not open a new one. It also inherits the
S53/L131 fill-wall (crypto_hourly has no size; maker fills unverifiable without a fill model) and the
S13 assumed-maker-fill bar. Correct move is to let Q48/S55 execute against today's burst tape, not to
mint a parallel slot.

## S59 — Post-anomaly mean-reversion taker (tape/anomalies/) → KILL at idea stage (lookahead + fill-wall)

Use `tape/anomalies/` detector flags as entry triggers, taker into the reverting side. Foreclosed at
the idea stage: (a) the anomaly tape is a *post-hoc* detector census — an entry conditioned on it is
lookahead unless the flag is available strictly before the fillable quote, which the tape does not
establish; (b) the reverting instrument is the same crypto/ladder surface with no trade-print and no
size (L131 fill-wall, L130 mid-efficiency wall) that killed S46/S47; (c) a taker exit re-pays the
0.07 fee twice, and the anomaly-sized dislocations are inside that round-trip on the observed rows.
No committed tape can price it without a fill model it doesn't have (S13). Not sent to a full verifier
re-run — the foreclosure is by already-enforced lessons, not a new number.

## Registry / provenance

NO registry table change (idea-stage round, prose-note precedent — same as the 07-24/07-25/07-26
rounds). Consumed **S57/S58/S59** → next free **S60**. S57's kill is an idea-stage two-agent gate
(producer census + independent verifier), not a verdict-class registry flip. The `true_arb_edge`
hollow-book false-positive guard is deferred to `kb-distiller` as an **L168 corollary** (not a new
lesson ID, per the verifier's recommendation). Still **0 proven edges** — the binding constraint remains the DATA SURFACE (the first-ever FOMC decision burst,
captured today, is the genuine next unlock via S55/Q48), not idea capacity.
