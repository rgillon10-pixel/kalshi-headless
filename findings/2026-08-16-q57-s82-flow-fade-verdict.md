# Q57 / S82 — game-level signed-taker-flow FADE taker: population-inadequate at the sealed spec (corrected — see §8)

**Date:** 2026-08-16 · **Queue item:** Q57 · **Strategy:** S82 (Q21 round #32 survivor)
**Verdict class:** DATA-ADEQUACY — **`below_min_units`, one game short at the sealed spec's tightest
mechanism-faithful window. NOT a structural/definitional impossibility — see §8, the independent
verifier REFUTED that escalation.**
**Status: PROVISIONAL — an independent `verifier` DID run (§8) and REFUTED the original "structurally
unfillable" framing while CONFIRMING the narrow single-sided-population claim under the exact
pre-registered spec. Per the two-agent rule this correction still may not flip the registry itself, and
it has not: `kb/strategies/00-index.md` S82 stays `idea`.** The presumptive-KILL recommendation
originally in §6 below is **WITHDRAWN** — see §8 before drawing any conclusion from §§1-7 alone.

**No CI was computed in either round. No settlement result VALUE was read.** The original probe refused
structurally at the population gate (§3) under the sealed spec; §8 shows that refusal does not generalize
past a single pre-registered constant.

Still **0 proven edges.**

---
**§§1-7 below are the original PROVISIONAL writeup, left unchanged as the historical record. Read §8
first — it corrects §§3/4c/6's central claim.**
---

---

## 1. The question, and the binding test

Over each settled sports GAME, aggregate net `count`-weighted taker-signed volume from
`tape/kalshi_trades/` over a pre-close window; when net flow is extreme toward one side, TAKE
THE OPPOSITE side at `real_ask` from `tape/orderbook_depth/` and HOLD to `broker_truth`
settlement. **Binding test:** a block-bootstrap-by-GAME 95% CI strictly > 0 net of ONE taker
fee (0.07, `core.pricing.fee_per_contract`) that also clears the L27 tick-magnitude gate, on a
population of ≥10 independent games (L41) carrying ≥1 opposing-sign unit (L312/L321, Q57 gate 2).

Reproduce:
```
python3 scripts/q57_s82_flow_fade_probe.py     # -> reports/q57_s82_flow_fade.json
python3 scripts/q57_s82_rederive.py            # independent second implementation, exit 0
```

## 2. The pre-registration (sealed before any outcome was read)

`PREREG_SHA256 = dd80f5973c39a0f4e99afcce8a83eb97c51070d046ad5a893bab1c559fa1c92c`, pinned by
`tests/test_q57_s82_flow_fade_probe.py::test_preregistration_hash_is_sealed`.

| field | value | chosen from |
|---|---|---|
| unit | GAME (L6) | one directional bet per event; never the outcome leg |
| close anchor | `settlement_ledger.close_time` (`broker_truth`) | the venue's own recorded close |
| entry instant | last `orderbook_depth` snapshot at/before close | Q57 gate 1's "nearest in-window snapshot" |
| max entry lag | 60 min | the depth collector's own hourly cadence |
| flow window | 120 min, ENDING at the entry instant | the final-approach / in-play stretch; 4x S79's 30 min |
| signal | `rho = net_signed_count / total_count` | scale-free, so "extreme" means the same on a 33- and a 3.5M-contract market |
| game ticker | argmax \|rho\|, ties → min(ticker) | one bet per game, no complementary-leg double count |
| gates | \|rho\| ≥ 0.20, window count ≥ 100 | a 60/40 split is the weakest "extreme"; rho=1.0 on 33 contracts is no flow |
| direction | **FADE** | S82's mechanism |
| entry price | `best_no_ask` if rho>0 else `best_yes_ask`, tag `real_ask` | Hard Rule #1 / the pt1 wall |
| price band | [0.02, 0.98] | L27/L249 |
| cost | ONE taker fee at entry | hold-to-settlement has no exit leg |

**Q57 gate (3) — the L51 differentiation, proven outcome-blind BEFORE scoring**
(`l51_differentiation()`, `voided = False`): the window is 4x wider (120 vs 30 min), the
decision rule is one close-anchored instant per game vs S79's hourly UTC grid, the signal is a
scale-free ratio vs S79's absolute contract threshold, and — decisively — **the entry price
surfaces are disjoint families**: S82 fills at `orderbook_depth`/`real_ask`, S79 at
`kalshi_trades`/`broker_truth` print prices. No entry price is shared, so the two populations
cannot be sign-negations of one another. The mechanisms stay complementary in SIGN; the
measurements are not the same measurement.

## 3. The result: the conditioning variable is CONSTANT, so there is nothing to measure

Substrate (re-derived from committed tape, independently twice): 213,488 prints / 87 traded
`*GAME` tickers / 72 games; 49 tickers carry a `settlement_ledger` close_time; 81/87 tickers
resolve to a binary settlement across all ten declared sources (L300 — `settlement_ledger` 49,
`q51_settlement_cache` 32).

Pre-registered cell:

| | |
|---|---|
| ticker candidates | 13 |
| GAME entries (after collapse) | **11** |
| scoreable (settled) game units | **11** — clears the L41 floor of 10 |
| entry sides | **{no: 11, yes: 0}** |
| exclusive minority units | **0** (floor 1) |
| mean overround absorbed | **+0.0222** (9 of 11 units two-sided) |
| entry-instant concentration | 10 distinct instants, max share 0.18 — NOT a tape-start artifact (L251) |
| **verdict** | **POPULATION-INADEQUATE — sign-variation gate (L312/L321) fails: `single_sided`** |

Every admissible unit fades to NO. A CI on that population would be a measurement of
"buy NO on late sports moneylines", not a test of signed flow — a directional bet wearing a
conditioning variable as a disguise. This is S79's own documented hole, now confirmed to
survive the flip to the FADE side.

### 3a. It is not an artifact of the pre-registered constants

`sign_variation_sensitivity()` sweeps all four constants over a declared 240-cell grid
(window ∈ {30,60,120,240,480} min · |rho| ∈ {0.05,0.10,0.20,0.40} · count floor ∈ {0,100,1000}
· max lag ∈ {30,60,240,4320} min). **Outcome-blind — it reports population SHAPE only, never a
return, so it costs no multiplicity and cannot tune the spec toward a result.**

* **178 / 240** cells meet the ≥10-game-unit floor.
* **4 / 178** also clear the sign-variation gate.
* The **maximum exclusive-minority-unit count anywhere in the grid is 1.**

All 4 passing cells share the same two extreme relaxations — `max_entry_lag = 4320 min`
(a book up to **3 days** stale, which is not a pre-close price at all) **and** `count floor = 0`
(so "extreme flow" can mean 33 contracts). Both abandon the mechanism. And each yields exactly
ONE minority unit, which is L321's own exhibit of a block that can never appear alone in any
resample.

### 3b. WHY the minority arm is empty — two separate walls, not one

`minority_arm_fillability()`, no gates applied, 45 ticker-level observations:

* **FREQUENCY.** Only **3 / 45 (6.67%)** have negative net flow at all. Root cause is L279's
  venue-wide retail-buy asymmetry, re-measured here: **151,937 yes-buy vs 61,494 no-buy prints
  (71.2% yes)**, and **68.3% yes** count-weighted. More days of the same tape do not remove a
  structural property of retail flow.
* **FILLABILITY — the one that actually binds.** Of those 3 negative-flow cases, **0** have a
  fillable in-band YES ask: **1 has no `best_yes_ask` at all** (one-sided book, L23) and
  **2 are pinned at the 1¢ tick floor** (L26/L249 — a floor-pinned price is a lottery ticket,
  not evidence, and is outside the pre-registered band).

These are the same event: by the time the crowd is net-SELLING yes into the close, the yes ask
has already collapsed to the floor or vanished. **The fade-to-YES arm is not merely rare — it
is structurally unfillable.** That is a stronger obstruction than a small sample: no quantity of
additional tape of this shape opens it.

## 4. Two defects found and fixed, and one blind spot disclosed

**(a) A sweep that swept nothing** — caught by `scripts/q57_s82_rederive.py`, not by a test.
The first version of `sign_variation_sensitivity` rebound module globals, but `window_flow`'s
window was ALSO spelled as a **default argument**, which Python binds at `def`-time. The flow
window therefore never varied: the sweep reported **0** sign-variation-passing cells where the
truth is **4**, and `max_minority = 0` where the truth is **1**. Fixed by threading all four
constants explicitly as keyword arguments; pinned by
`test_sweep_constants_are_threaded_not_read_from_globals`. *This is exactly the class of error
the two-agent rule exists to catch, and here the redundancy — not the author — caught it.*

**(b) The probe's own close_time-mutation check has a structural blind spot.**
`substrate.close_time_mutation_observed` reads `false`, but only because both committed
`settlement_ledger` day-files are POST-settlement, so the family can never disagree with
itself. `close_time_cross_family_audit()` looks at `tape/q51_settlement_cache/`, which holds
the same tickers captured at different moments: **48 of 60 tickers carry more than one distinct
`close_time`**, e.g. `KXAFLGAME-26AUG060530NMKBUL-BUL` moving `2026-08-20T09:30:00Z` →
`2026-08-06T12:09:30Z` — **14 days earlier**, a textbook L360/L361 exhibit.

**Consequence, declared not hidden:** S82's entry anchor is a post-settlement `close_time`, so
its ex-ante knowability is **UNVERIFIED**. A *positive* result from this probe would owe that
check before graduation. The *negative* result is unaffected — a look-ahead anchor can only
flatter the strategy.

**(c) Not taken, on purpose.** `tape/q51_settlement_cache/` also carries `close_time` and would
expand the anchored population beyond the 49 `settlement_ledger` tickers. Adding a source after
seeing the population is tuning, so the pre-registered spec was left alone. Given 93.3%
positive flow and the fillability wall, a larger population is very unlikely to change the
sign-variation verdict, but that is a prediction, not a measurement.

## 5. Independent re-derivation (the no-verifier redundancy fallback)

`scripts/q57_s82_rederive.py` re-derives every headline from the committed tape sharing nothing
with the probe — its own JSONL/JSON readers, its own ISO→epoch parser written by string slicing
and integer day arithmetic (no `datetime`, no `core.timeutil`), its own settled-set reader
(direct off `settlement_ledger` + `q51_settlement_cache`, not `core.settlement_sources`), its
own sports filter, game-key split, window/flow/collapse loop, and per-side census. Independence
is pinned by an AST check in `tests/test_q57_s82_rederive.py`.

All 16 compared headlines agree **EXACTLY** (no bootstrap-noise tolerance was needed or granted,
because no bootstrap was run): 13 ticker candidates · 11 game entries · 11 scoreable units ·
`{no: 11}` · 240/178/4 sensitivity cells · max minority 1 · 3 negative-flow cases split
1 absent / 2 floor-pinned / 0 in-band · 49 tickers with close_time · 72 traded games.

**This is a second implementation, not a second agent.** The verdict remains PROVISIONAL.

## 6. Verdict, kill mapping, and the reopen condition

Q57's kill list reads: *"real-ask CI ≤ 0 / straddles zero / fails the magnitude gate / L51
collapses it into S79 / population below the 10-game floor."* None of those fired literally —
the population CLEARS the 10-game floor and L51 does NOT collapse it. What fired is Q57's
**binding gate (2)**, the ≥1-opposing-sign-unit requirement, and it fired structurally rather
than marginally.

**S82 is NOT MEASURABLE as a signed-flow strategy on the committed tape**, and the obstruction
is a property of the venue's flow and book shape, not of the sample size. Recommended
disposition once a second agent confirms: **`idea` → `dead ✗` (not-measurable / degenerate
conditioning variable)**, closing the signed-flow-taker family alongside S79 and S22. Same
short-the-crowded-side factor slot as S13/S23/S79/S80 (Hard Rule #6 ρ cap).

**Reopen condition (precise, so a future run does not re-run this by accident):** a tape in
which net-NEGATIVE game-level taker flow coexists with a **live, in-band (`0.02 ≤ ask ≤ 0.98`)
YES ask** on at least 2 independent games. Neither more days of the current hourly
`orderbook_depth` cadence nor more `kalshi_trades` days of the current shape produce that —
it needs a venue/book regime where informed selling happens while the yes side is still quoted.

## 7. Provenance

* Prices: entry `real_ask` (`tape/orderbook_depth/`, `price_source_tags.asks == "real_ask"`,
  filtered on that field — a snapshot that does not call its own asks real is never read).
  Prints and settlements `broker_truth`. **No `midpoint` or `synthetic` value is read anywhere
  in this probe, and no P&L number is quoted in this document.**
* Fees: `core.pricing.TAKER_FEE_RATE` / `fee_per_contract` only — no hand-rolled rate (L5/L30).
* Bootstrap unit: GAME (L6); floor 10 (L41); Kish n (L322), tick-magnitude (L27) and
  sign-variation (L312/L321) gates wired but not reached, because the population gate fires first.
* Flow orientation: `flow_orientation_audit()` MEASURES rather than assumes L279's reading —
  `taker_book_side`/`taker_outcome_side` are perfectly collinear on committed tape
  (`bid|yes` 151,937 · `ask|no` 61,494, `collinear = True`), so both readings of the sign agree.
* Files: `scripts/q57_s82_flow_fade_probe.py`, `scripts/q57_s82_rederive.py`,
  `tests/test_q57_s82_flow_fade_probe.py`, `tests/test_q57_s82_rederive.py`,
  `reports/q57_s82_flow_fade.json`, `scripts/invariants.py` (two triage declarations added).

## 8. Verifier round (independent adversarial review, 2026-08-16) — REFUTED the escalation, CONFIRMED the narrow claim

An independent `verifier` subagent was dispatched by the calling research-loop session after the run above
(the run above ran in a harness with no `Task`/nested-agent tool, so it could not dispatch one itself and
correctly committed as PROVISIONAL per Q57's own sanctioned fallback).

**What re-ran and matched, independently (not just by re-executing the committed scripts):** a from-scratch
reader sharing no code with either `q57_s82_flow_fade_probe.py` or `q57_s82_rederive.py` reproduced EXACTLY:
213,488 total trade rows / 213,431 `*GAME` prints / 87 GAME tickers / 72 games; yes-print share 0.7119 raw,
0.6830 count-weighted; 49 ledger `close_time` tickers; 81/87 settled binary; the same 11 pre-registered
units, every one with rho > 0 (all fade to NO); same asks, same lags, 10 distinct entry instants / max share
0.1818; the §3b fillability split exactly (neg=3, pos=42, `{floor: 2, absent: 1}`, in-band 0). Both new test
files (39 tests) pass and are non-vacuous (the prereg-hash test pins the literal SHA and breaks on any
spec-constant edit; the AST test really forbids the rederive script from importing shared code).
`invariants.py --full` exit 0. Regenerating `reports/q57_s82_flow_fade.json` from a clean checkout is
byte-identical to the committed copy. **The narrow claim is CONFIRMED to the digit.**

**What broke:** §3b's own stated wall — *"the fade-to-YES arm is not merely rare — it is structurally
unfillable … no quantity of additional tape of this shape opens it"* — and §6's escalation of that to *"the
obstruction is a property of the venue's flow and book shape, not of the sample size."* Both are false on the
tape already committed.

**Minimal repro.** Change exactly ONE pre-registered constant — flow window 120 → 15 min — holding the
ledger `close_time` anchor, the last-snapshot-before-close entry rule, `|rho| >= 0.20`, count floor 100, max
lag 60 min, and the `[0.02, 0.98]` band all fixed at their pre-registered values:

```
KXKBOGAME-26JUL070530KIWKTW-KIW   ledger close_time 2026-07-07T11:59:58Z
  entry snapshot 2026-07-07T11:55:53Z   lag 4.08 min
  best_yes_ask 0.06  (a real 6c offer, not floor-pinned)
  15-min window: rho = -0.2313   -> FADE = YES
  120-min window: rho = +0.5759  -> FADE = NO
```

A second case exists in the same pass (`KXNPBGAME-26JUL070500HANYOM-YOM`, rho -0.0972, best_yes_ask 0.92,
lag 18.8 min). Both are fully mechanism-faithful, in-band, `real_ask`-fillable fade-to-YES entries on
settled games — exactly the reopen condition §6 wrote down (negative flow coexisting with a live in-band
YES ask on ≥2 independent games), already satisfied on the committed tape, not a hypothetical future one.
Re-running §3b's own no-gates fillability census at 15 min instead of 120 min on the identical ledger anchor
gives **10 negative-flow observations, 2 with a fillable in-band YES ask** — not "0 of 3." The zero in §3b
is a property of the 120-minute window, not of the book.

**Consequences:**

1. **§6's reopen condition is already tripped**, on the tape already in hand. A tripwire that is already
   tripped cannot prevent an accidental re-run — it should be checked against current tape before being
   filed, not written down as a future-only condition.
2. **A genuinely two-sided, floor-clearing population exists on this tape.** Anchoring on
   `tape/q51_settlement_cache/` (§4c's road explicitly not taken) instead of `settlement_ledger`, max lag
   240 min, window 15 min, same `|rho| >= 0.20`/count-floor-100/band → **12 GAME units, {no: 10, yes: 2},
   2 EXCLUSIVE-minority units on 2 distinct games** (`…KIWKTW-KIW` 0.06, `KXNWSLGAME-26AUG02DENBOS-TIE`
   0.22). That clears L41's 10-unit floor, the probe's own gate-2 floor of 1, AND
   `core.bootstrap.sign_variation_admissible`'s real default of `min_exclusive_minority_units=2` — with no
   3-day-stale book and no zero volume floor. At the full pre-registered 120-min window with the same cache
   anchor and lag 240: 14 units {no: 13, yes: 1}.
3. **§4c's prediction is falsified by measurement, not merely unmeasured.** *"Given 93.3% positive flow and
   the fillability wall, a larger population is very unlikely to change the sign-variation verdict"* —
   expanding the anchor from 49 to 87 tickers does change it. Where an alternative is outcome-blind (a
   close-time anchor choice is not a result value) and cheap, it should be measured, not predicted away.
4. **§3a's "not an artifact of the pre-registered constants" is true only inside the declared grid.** The
   grid's window axis bottoms at 30 min next to a pre-registered 120. Below 30 min (15 min), with the
   ledger anchor and lag ≤ 60, the population is **9 units {no: 8, yes: 1}** — two-sided but ONE game short
   of the L41 floor. That is `below_min_units` ("not measured yet"), categorically different from
   "definitionally impossible." (The grid's own claim does hold where it applies: across ledger+cache
   anchors × windows 2–1440 min × count floors 0–5000 at lag ≤ 60, zero cells reach 10 units with a
   minority unit at `min_abs_rho >= 0.20` — the escape hatch is the lag, not the rho gate.)

**Smaller defects, worth fixing regardless of the headline:**

- **Citation error.** §3a's *"each yields exactly ONE minority unit, which is L321's own exhibit of a block
  that can never appear alone in any resample"* cites the wrong lesson. The floor-of-2 rule is **L312
  sub-lesson (b)** (a minority arm concentrated in a single game cannot be block-bootstrapped at all); L321
  is about EXCLUSIVE-vs-TOUCHING counting. The conclusion (1 is too few) is right, for L312's reason — an
  EXCLUSIVE single minority block *can* appear alone in a with-replacement resample.
- **Undisclosed floor relaxation.** `core.bootstrap.sign_variation_admissible`'s default is
  `min_exclusive_minority_units=2`; the probe passes 1. This faithfully implements Q57's own gate-2 wording
  (checked against `origin/main:LOOP-QUEUE.md` — the prereg is not self-authored), but it is below L312's
  established floor. Harmless in the original run (0 < 1 < 2), but should be stated as using the weaker of
  the two available floors.
- **Cosmetic.** §3's "213,488 prints / 87 traded `*GAME` tickers" conflates the whole-tape row count with
  the GAME subset (213,431); the probe's own JSON report has it right.
- **Unremarked population shape.** 8 of the 11 pre-registered units are `-TIE` legs — `argmax|rho|`
  systematically selects the 3-way soccer draw market. The population reads closer to "sell the draw" than
  to "buy NO on a moneyline." This strengthens the degeneracy reading but was not stated.

**Disposition.** The narrow fact — the pre-registered S82 cell yields 11 single-sided units and cannot
produce a valid two-sided sign-variation test — is CONFIRMED to the digit. The KILL rested on escalating
that to "structurally unfillable, no more tape helps," and that escalation is REFUTED by the committed tape
at the pre-registered anchor. **Q57 stays PROVISIONAL and OPEN. S82 must NOT be flipped `idea -> dead ✗` on
a not-measurable rationale — the honest class is `below_min_units` under the sealed spec, one game short at
a 15-min window, not a definitional obstruction.** (To be explicit about the limit of this correction too:
the two-sided population in point 2 above required THREE simultaneous spec changes found by searching for
two-sidedness, so it is not itself licence to score S82 there — it is only evidence that the impossibility
claim is false. A proper retest needs its own fresh pre-registration.)

**New lesson candidates** (filed in `kb/lessons/00-lessons.md` as L362-L364, UNENFORCED):
- A sensitivity grid that only *brackets* the pre-registered value cannot distinguish "structural" from
  "an artifact of this constant" — a structural claim requires perturbing each constant past the edge of
  the declared grid, one at a time.
- A written reopen condition must be executed against the CURRENT tape before it is filed — an untested
  tripwire that is already tripped is worse than none.
- Declaring an untaken, outcome-blind, cheap-to-measure alternative as "unlikely to matter" converts a
  measurable fact into an unmeasured guess; where it costs no multiplicity, measure it.
