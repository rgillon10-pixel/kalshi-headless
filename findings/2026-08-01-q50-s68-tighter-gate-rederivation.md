# Q50 / S68 — the fees-plus-N-ticks gate re-derivation (L252) — **VERIFIER-CONFIRMED**

**2026-08-01, research loop (idle run, policy (a): UNENFORCED lesson → executed re-derivation + tests).**
**Amended 2026-08-01 (same day) after an independent verifier pass — see "Verifier pass" below.**

> **STATUS: VERIFIER-CONFIRMED. The PROVISIONAL label is withdrawn.** An independent verifier
> re-ran the script and re-derived every headline number, and returned **CONFIRMED**: S68 stays
> `dead ✗` and nothing flips. The verifier additionally found a **STRONGER kill** than the three
> grounds this document originally gave (a zero-information "mid-as-truth" control and a
> flatten-at-cross exit treatment — both below), and found two **provenance defects** in what had
> been committed, now fixed:
>
> 1. the three "attacks that did NOT kill it" existed **only as prose**, with no code, no CLI flag
>    and no artifact behind them — a violation of this repo's own trust default ("no claim without
>    a re-runnable script"). They are now real code (run by default; `--robustness-only` runs them
>    alone in ~11s, `--no-robustness` skips them) writing
>    `reports/q50_s68_gate_ladder_robustness.json`, with 12 new offline tests (42 in the file, was 30);
> 2. the longshot-drop CI was quoted at an **undisclosed `n_boot=4000`** while the headline used
>    10,000. Every robustness number is now computed at the headline's `n_boot=10000` and **echoes
>    the `n_boot` it used** in the printed report, in the JSON, and below.

**Bottom line: S68 is NOT rescued by a tighter gate.** The apparent CI>0 cells are an artifact:
they die outright under a flatten-at-cross exit and are reproduced by a zero-information control
(both verifier attacks, below), they exist only at entry horizons where the wide-spread population
lives and the near-close cells are negative, and they are bounded by an adverse-selection term this
tape structurally cannot measure. Still **0 proven edges**.

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

`scripts/q50_s68_gate_ladder.py` (+ `tests/test_q50_s68_gate_ladder.py`, 30 offline tests at first commit, **42 after the post-verifier robustness fix**). Every
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
it is not a shape an edge has. This document originally read it as the **S29 DEAD-by-fillability
signature** (nominal bids on
days-out, effectively one-sided books that a generous fill-sim still "fills", L31/L48). **The
verifier confirmed the PATTERN and corrected the MECHANISM** — see "Verifier pass" below and the
amended L254: the ALIVE cell's median entry ttc is 23.7h with an actually-traded-looking book, and
the real driver is a spread regime (median entry spread $0.020 = 2 ticks near close vs $0.060-$0.090
at 9 of the 10 ALIVE cells (the tenth, H=72/N=5, is wider still at $0.290)), i.e. the wide-spread population this ladder hunts does not exist near close.
The horizon dependence is real either way (matched-ticker control), but the near-close end is a
data-adequacy residue, not a proven fill failure.

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

## Attacks that did NOT kill it (recorded so they are not re-run) — NOW CODE-BACKED

**Provenance note.** These three were prose-only in the first cut of this document. They are now
re-runnable code — `leave_one_series_out`, `drop_longshot_single_side`, `price_offset_placebo`,
driven by `run_robustness` in `scripts/q50_s68_gate_ladder.py` — which run **by default** and write
`reports/q50_s68_gate_ladder_robustness.json`. Reproduce in ~11s with:

    python3 scripts/q50_s68_gate_ladder.py --robustness-only

**All three are computed at `n_boot=10000`, the same as the headline**, and each result dict/print
line carries its own `n_boot` (the earlier +0.0525 CI had been computed at an undisclosed
`n_boot=4000`; the corrected 10,000-resample CI is below). Headline cell for all three:
H=24h / N=1 tick, 100 candidates / 13 series / 81 games, `touch`, mean +0.0695 CI [+0.0235,+0.1473].

* **Leave-one-series-out (L57)** on H=24/N=1, `n_boot=10000`: **13/13 drops keep the CI lower bound
  strictly > 0**, and 13/13 also clear the L27 one-tick gate. Worst drop is KXWNBAGAME
  (CI [+0.0147,+0.1151]); the largest unit (KXNPBGAME, n=30) leaves CI [+0.0166,+0.1766]. No single
  series carries the cell.
* **Dropping longshot single-side fills** (unhedged leg priced <= $0.30), `n_boot=10000`: 19/100
  candidates dropped (units dropped whole, never zeroed — L86), leaving mean **+0.0525**, CI
  **[+0.0134,+0.1358]**, 13 series / n=81. *(The originally published CI [+0.0131,+0.1410] was the
  `n_boot=4000` value; [+0.0134,+0.1358] is the correct 10,000-resample number.)* The result is not
  solely a longshot lottery, though the top-5 contributors are all unhedged `yes_only` legs on
  `-TIE`/longshot bids (+0.72 to +0.93 each).
* **Price-offset placebo** (rest 2c below the entry best bid, same admitted population, gate
  unchanged): leg fill rates collapse **yes 53% -> 2%, no 44% -> 9%, both 27% -> 1%**, so the
  `touch` model is genuinely price-sensitive and not a generic churn detector. This is a point *in
  favour of the fill model's discrimination* — a statement about the instrument, not about the
  strategy — and is recorded as such.

None of the three is evidence FOR an edge. The two attacks that DO kill the cell are the verifier's,
below.

## Verifier pass (2026-08-01, independent) — CONFIRMED, and the kill is stronger

The verifier re-ran the script, reproduced the ladder, re-derived the three robustness numbers by
hand (all three confirmed true), and returned **CONFIRMED: S68 stays `dead ✗`, nothing flips.** It
then produced two attacks this document had not run, both of which kill the ALIVE cells outright:

1. **Zero-information "mid-as-truth" control (new lesson L255).** Replace the `broker_truth`
   settlement payout of every unhedged single-side leg with the book's own contemporaneous mid — so
   the leg carries no directional information at all — and re-bootstrap. The CI comes back the
   **same shape and sign as the real verdict**. A positive result reproduced by a zero-information
   control is an arithmetic restatement of `half-spread x fill-rate − fees` on a wide-spread
   population (true by construction of the entry gate), not a claim that the fills pick winners.
2. **Flatten-at-cross exit treatment (new lesson L256).** This probe's strategy-level object marks
   an orphan single-side leg to settlement, which is the most generous possible treatment — a free
   directional lottery ticket no maker would knowingly keep. Closing the orphan instead by buying
   the other side at its ask costs, on a mirrored binary book where the two prices sum to exactly
   $1, precisely both fees (`pnl = −(fee_entry + fee_exit)`). Under that treatment **all 10 ALIVE
   cells die — every CI straddles zero.** The whole apparent edge lived in the unhedged legs'
   settlement lottery, consistent with this document's own composition analysis (half the H=24/N=1
   mean is unhedged single-side exposure).

**Mechanism correction (L254 amended).** The verifier confirmed the monotone-in-H pattern is real —
a matched-ticker control on the 70 tickers / 14 series present at BOTH H=12 and H=72 still flips,
CI [−0.1137,−0.0054] -> +0.0151 — but rejected this document's original *"S29-style nominal
one-sided books days-out"* attribution. The ALIVE cell's median entry ttc is **23.7h** (not
days-out) and its queue/depth numbers look like an actually-traded book. The real driver is a
**spread regime**: median entry spread is **$0.020 (2 ticks, exactly the Q49 fee boundary)** at the
near-close H=6/N=0 and H=12/N=0 cells versus **$0.060-$0.090 (6-9 ticks)** at 9 of the 10 ALIVE cells (the tenth, H=72/N=5, is wider still at $0.290)
(the ladder now prints per-cell `median_entry_spread`, and it is persisted in the summary JSON).
**The wide-spread population this ladder exists to find does not exist near close** — H=6/N=1
admits 25 candidates across 4 series, below the L41 10-series floor. So the near-close end is a
data-adequacy residue, not a demonstration that the same books fail to fill.

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
either: it is **DEAD** — outright under the verifier's flatten-at-cross exit treatment (all 10
ALIVE cells' CIs straddle zero) and content-free under the mid-as-truth control — and what remains
after that is **UNRESOLVABLE on current tape** (data-adequacy), pending a trade-bearing feed. The
`orderbook_delta` WebSocket daemon (Q47, BUILD DONE / ACTIVATION PENDING, Ryan-gated on a working key)
is exactly the tape that would settle it.

Verdict class: **DEAD (flatten-at-cross CI straddles zero on every ALIVE cell) + data-adequacy
residue at the near-close end. NOT a resurrection.** **VERIFIER-CONFIRMED 2026-08-01** — the
PROVISIONAL label is withdrawn and the registry is unchanged (`dead ✗`, as it already was).

## Gates

**First commit (2026-08-01, PROVISIONAL cut).** Taken after the last code edit, immediately before
commit (L162).

* `python -m pytest -q` -> **2577 tests, 2577 passed, 0 failed**. This suite emits no trailing summary
  line, so the count is a progress-character census over the completed 100% run (2577 `.`, zero
  `F`/`E`/`x`/`s`), independently re-confirmed by a second full run that also reached 100% with no
  failure character. 30 of those tests are new (`tests/test_q50_s68_gate_ladder.py`).
* `python scripts/invariants.py --full` -> exit 0, `invariants: all green` (14 pre-existing non-gating
  advisories).

**Second commit (2026-08-01, post-verifier provenance fix).** Re-taken after the last edit of this
pass (L162).

* `python -m pytest -q` -> **2589 tests collected, all passed, 0 failed** (`--collect-only` census =
  2589; the run reaches 100% with zero `F`/`E`/`x`/`s` progress characters and exits 0; the suite
  still emits no trailing summary line). +12 vs. the first commit, all in
  `tests/test_q50_s68_gate_ladder.py`, which now holds **42**.
* `python scripts/invariants.py --full` -> exit 0, `invariants: all green` (14 pre-existing
  non-gating advisories, unchanged).

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
`reports/q50_s68_gate_ladder_summary.json` (35 cells, all diagnostics, now incl. per-cell
`median_entry_spread` / `median_ttc_hours_entry`) · `reports/q50_s68_gate_ladder_rows.jsonl`
(4,727 per-candidate rows) · `reports/q50_s68_gate_ladder_robustness.json` (**new** — the three
attacks, every number tagged with its `n_boot`).
