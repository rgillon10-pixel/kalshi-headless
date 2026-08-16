# Q57 / S82 — game-level signed-taker-flow FADE taker: NOT MEASURABLE on committed tape

**Date:** 2026-08-16 · **Queue item:** Q57 · **Strategy:** S82 (Q21 round #32 survivor)
**Verdict class:** DATA-ADEQUACY (sign-variation degeneracy) — **presumptive KILL**
**Status: PROVISIONAL.** No `verifier` subagent exists in this harness (no `Task` tool; the
L287/L288/L290/L291/L295/L308/L313/L325 precedent, and Q57's own text: *"run it PROVISIONAL if
no `verifier` subagent is available in the executing harness"*). Per the run protocol's
two-agent rule a PROVISIONAL verdict **may not flip the registry**, and it has not:
`kb/strategies/00-index.md` S82 stays `idea`, with a dated note.

**No CI was computed. No settlement result VALUE was read.** The probe refused structurally,
which is the intended behaviour — see §3.

Still **0 proven edges.**

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
