# Q50 / S68 — the fees-plus-N-ticks gate re-derivation (L252) — **PROVISIONAL**

**2026-08-01, research loop (idle run, policy (a): UNENFORCED lesson → executed re-derivation + tests).**

> **PROVISIONAL — SINGLE-AGENT. NO VERIFIER CONFIRMATION.** No `verifier` dispatch was available in
> this run's context (the `Task` tool was not enabled), so the two-agent verdict rule could NOT be
> satisfied. Per LOOP-QUEUE.md step 5 this is therefore committed as PROVISIONAL and **flips
> nothing**: `kb/strategies/00-index.md` S68 stays `dead ✗`, unchanged. Every number below is
> re-runnable from one command and is owed an independent re-derivation — see **Q50** in the queue.

**Bottom line: S68 is NOT rescued by a tighter gate.** The apparent CI>0 cells are a
**days-out fillability artifact** — the S29 signature — and are additionally bounded by an
adverse-selection term that this tape structurally cannot measure. Still **0 proven edges**.

## Why this run existed

Q49 killed S68 (`findings/2026-08-01-q49-s68-bothside-maker-fillsim-verdict.md`, verifier-CONFIRMED,
headline `DEAD-by-fee`). That verdict stands, but it left two follow-ups owed, filed the same day as
UNENFORCED lessons:

* **L252** — Q49's gate was `yes-spread >= fee(yes_bid) + fee(no_bid)`. On a mirrored binary book
  (`best_yes_ask == 1 - best_no_bid` by collector construction) that is IDENTICAL to
  "gross capture >= the two fees", so it admits books sitting *on* the zero-profit boundary; all 11
  of Q49's double fills netted between $0.0000 and one cent. L252's candidate enforcement: set the
  gate at **fees-plus-N-ticks** and **re-derive the population size and economics** before treating
  a fee-boundary result as informative. *That re-derivation had not been done.*
* **L251** — Q49's primary cut used "earliest pre-close snapshot, then filter ttc<=24h", which on a
  young tape selects on TAPE START DATE: all 20 candidates shared ONE `entry_captured_at`. The honest
  rule is "**first snapshot with ttc<=H**".

## What was built

`scripts/q50_s68_gate_ladder.py` (+ `tests/test_q50_s68_gate_ladder.py`, 30 offline tests). Every
simulation primitive (queue accounting, both fill models, both P&L branches, tape loading) is
**imported from the Q49 module**, not re-implemented — Q49's code is already verifier-CONFIRMED and a
second copy would be a second thing to get wrong. What is new is only (a) the entry rule, (b) the
gate, and (c) the adverse-selection instrumentation Q49's own spec asked for and no probe in this
repo has ever charged.

    python3 scripts/q50_s68_gate_ladder.py --n-boot 10000     # direct CLI form verified (L232)

**The bootstrapped object is the strategy-level P&L** (L249): a double fill books the realized net
capture, a single-side fill books the **unhedged directional position actually left on the book**
marked to `broker_truth` settlement, a no-fill books 0. The double-fill-only P&L is **sign-bounded by
construction** under this gate and is reported as a diagnostic that carries no evidentiary weight —
quoting it as a verdict is precisely the L249 error. Fill model `touch` is primary (L250). Bootstrap
unit = GAME-SERIES (L6/L41), 10,000 resamples, through `bootstrap_verdict_admissible` +
`clears_tick_magnitude`.

Join: 368,466 depth lines / 95,413 depth tickers → **605** settled tickers with a pre-close two-sided
depth snapshot (L9/L43 window overlap is the binding constraint, as in every prior probe on this tape).

## The ladder (strategy-level, `touch`, 35 cells)

| H (entry) | N=0 | N=1 | N=2 | N=3 | N=5 |
|---|---|---|---|---|---|
| **6h** | **−0.0562** [−0.1459,+0.0046] · 14 ser | −0.0060 · 4 ser | +0.0200 · 1 ser | +0.0717 · 1 ser | empty |
| **12h** | **−0.0397** [−0.0913,+0.0125] · 15 ser | +0.0587 · 6 ser | +0.0339 · 3 ser | +0.0385 · 2 ser | +0.0914 · 1 ser |
| **18h** | +0.0308 [−0.0382,+0.0855] · 14 ser | +0.0300 [−0.0274,+0.1288] · 11 ser | +0.0371 · 7 ser | +0.0397 · 5 ser | −0.0072 · 3 ser |
| **24h** | +0.0244 [−0.0242,+0.0623] · 17 ser | **+0.0695 [+0.0235,+0.1473] · 13 ser — ALIVE** | +0.0579 [−0.0000,+0.1410] · 11 ser | +0.0664 · 7 ser | +0.0602 · 5 ser |
| **36h** | +0.0307 [−0.0105,+0.0859] · 17 ser | +0.0400 [−0.0212,+0.1074] · 15 ser | +0.0506 [−0.0078,+0.1149] · 12 ser | +0.0436 · 9 ser | +0.0547 · 9 ser |
| **48h** | **+0.0487 [+0.0134,+0.1047] · 17 ser — ALIVE** | **+0.0673 [+0.0233,+0.1313] · 17 ser — ALIVE** | **+0.0782 · 13 ser — ALIVE** | **+0.0759 · 11 ser — ALIVE** | +0.0951 · 9 ser |
| **72h** | **+0.0768 · 17 ser — ALIVE** | **+0.0952 · 17 ser — ALIVE** | **+0.1038 · 12 ser — ALIVE** | **+0.1156 · 11 ser — ALIVE** | **+0.1512 · 10 ser — ALIVE** |

Cells with fewer than 10 series units are DEAD-by-adequacy regardless of their CI (L41) and their
point estimates are shown for completeness only. 10 of 35 cells clear.

**L252's actual question is answered: yes, a genuinely wider-spread population exists.** At H=24/N=1
it is 100 candidates / 13 series / 81 games across **47 distinct entry instants** — so this is NOT
Q49's L251 tape-start artifact (Q49's own anchor over the identical tape: 445 candidates on 23
instants, but its headline cut collapsed to 1). Population decays smoothly with N (H=24: 176 → 100 →
82 → 64 → 55), so the gate is doing what it should.

## Why this is an artifact and not an edge — three independent reasons

**1. The result is monotone in the entry horizon, and inverts in the only fillable window.**
Every one of the 10 ALIVE cells sits at H >= 24h; nine of them at H >= 48h. The two genuinely
near-close windows — the only ones where a resting maker order is a realistic object — are
**negative** at the adequately-powered N=0 cut: H=6h **−0.0562** (14 series), H=12h **−0.0397**
(15 series). An "edge" that grows the further you enter from close and flips negative as you approach
it is the **S29 DEAD-by-fillability signature**, verbatim: nominal bids on days-out, effectively
one-sided books that a generous fill-sim still "fills" (L31/L48). S29 died on exactly this pattern on
exactly this tape family.

**2. The verdict is decided by a term this tape cannot measure.** Break-even adverse-selection charge
per filled leg on the ALIVE cells: **0.5c to 4.0c** (H=24/N=1: **2.0c**; H=48/N=0: **0.5c**). Kalshi's
maker fee is a flat 1c, so the whole result lives inside a band of one-to-four fees. Q49's own binding
spec required "an explicit adverse-selection model"; neither Q49 nor Q50 has one, because
`tape/orderbook_depth/` carries **no trade or volume field** (L68/L106) — the `touch` rule cannot tell
a CANCEL at our price from a TRADE against us.

**3. The direct markout measurement is blind by construction — and must not be read as reassurance.**
Marking each simulated fill to the book's own later mid gives a *positive, non-decaying* markout
(H=24/N=1: k=0 **+0.0543**, k=1 +0.0562, k=5 +0.0610, k=10 +0.0618), i.e. no adverse selection at all.
That is the expected output of a **blind instrument**, not evidence of its absence: a fill proxy that
cannot observe trade direction cannot exhibit adverse selection. The +5.4c at k=0 is approximately the
half-spread of these wide books — a restatement of "we bought at the bid", not a measured informational
cost. **This is the single most important caveat in this document.**

## Attacks that did NOT kill it (recorded so they are not re-run)

* **Leave-one-series-out (L57)** on H=24/N=1: all 13 drops keep the CI strictly > 0.
* **Dropping longshot single-side fills** (fill price <= $0.30): mean +0.0525, CI [+0.0131,+0.1410] —
  still clears. The result is not solely a longshot lottery, though the top-5 contributors are all
  unhedged `yes_only` legs on `-TIE`/longshot bids (+0.72 to +0.93 each).
* **Price-offset placebo**: resting 2c below the entry best bid collapses leg fill rates from
  53%/44% to 2%/9%, so the `touch` model is genuinely price-sensitive and not a generic churn
  detector. This is a point *in favour* of the fill model's discrimination and is recorded as such.

## Composition of the H=24/N=1 headline (why the mechanism attribution fails)

Fills: both 27 · yes_only 26 · no_only 17 · neither 30 (both-fill rate 27.0%).
Contribution to the +0.0695 mean: double fills +0.0347 (50%), no_only +0.0180, yes_only +0.0168 —
so **half the "edge" is unhedged directional exposure**, which is not the S68 both-bid capture
mechanism at all. Distribution: median **$0.0000**, 48 positive / 30 zero / 22 negative, p10 −0.31,
p90 +0.62 — a lottery shape whose mean is tail-driven. Filled single legs "pick winners"
(filled-YES wins 34.6% vs 27.2c paid; filled-NO wins 70.6% vs 59.0c paid), which is the arithmetic
consequence of both bids sitting below fair on an over-round book under an outcome-independent fill
rule — not a demonstrated edge.

## Verdict

**S68 remains `dead ✗` (no status change).** What changes is the *scope* of Q49's headline: its
`DEAD-by-fee` label is now known to be **gate-scoped** — true at the fee-boundary gate Q49 tested, and
it does not, on its own, extend to the wider-gate population. That wider population is not an edge
either: it is **DEAD-by-fillability** on the same evidence pattern that killed S29, and what remains
after that is **UNRESOLVABLE on current tape** (data-adequacy), pending a trade-bearing feed. The
`orderbook_delta` WebSocket daemon (Q47, BUILD DONE / ACTIVATION PENDING, Ryan-gated on a working key)
is exactly the tape that would settle it.

Verdict class: **DEAD-by-fillability + data-adequacy residue. NOT a CI falsification, NOT a
resurrection.** PROVISIONAL pending verifier.

## Gates

Taken after the last code edit, immediately before commit (L162).

* `python -m pytest -q` -> **2577 tests, 2577 passed, 0 failed**. This suite emits no trailing summary
  line, so the count is a progress-character census over the completed 100% run (2577 `.`, zero
  `F`/`E`/`x`/`s`), independently re-confirmed by a second full run that also reached 100% with no
  failure character. 30 of those tests are new (`tests/test_q50_s68_gate_ladder.py`).
* `python scripts/invariants.py --full` -> exit 0, `invariants: all green` (14 pre-existing non-gating
  advisories).

**One gate defect this probe introduced and fixed in-run:** the first draft compared
`result == "yes"` with no binary-result guard in the file, which turned L52's *non-gating* advisory
into a **red** acceptance test (`tests/test_settlement_result_advisory.py::test_acceptance_every_reported_site_is_real`
failed on the pre-fix tree). Fixed properly — by routing the settlement read through
`core.settlement.require_binary_result` — not by suppressing the advisory. A Kalshi settlement is not
always binary ('scalar' exists, Q26), so an unguarded comparison would silently book a scalar row as
the losing side.

## Price source tags

fills `real_bid` · queue depth `real_bid` · book mid (markout) `real_bid` · settlement `broker_truth`.
No synthetic price is used as a fill anywhere in this probe.

## Artifacts

`scripts/q50_s68_gate_ladder.py` · `tests/test_q50_s68_gate_ladder.py` ·
`reports/q50_s68_gate_ladder_summary.json` (35 cells, all diagnostics) ·
`reports/q50_s68_gate_ladder_rows.jsonl` (4,727 per-candidate rows).
