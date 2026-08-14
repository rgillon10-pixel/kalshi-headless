# L323's own recorded residual was live in the tree: a triage ratchet's allowlist was also its escape hatch

`2026-08-14` · research loop, protocol v3, **IDLE RUN, idle-run policy (a)** (queue drained,
Q0–Q56 re-verified: 0 eligible TODO/IN-PROGRESS) · **no verdict-class output** — no bootstrap CI,
no P&L, no registry status flip, no kill. `kb/strategies/00-index.md` untouched.

## The question, framed to be falsifiable

L323's enforcement cell (2026-08-09, extended 2026-08-11) closed its measurement and triage
halves and recorded one residual as an honest limit:

> "the trigger is a family reference or a shared-loader import, so a future module consuming
> prints only through some OTHER triaged helper inherits its disposition without being asked —
> the same residual L319 records as terminal."

**Binding question:** is that residual hypothetical, or does the real tree already contain a
module that consumes `tape/kalshi_trades/` prints, depends on the order of exact-timestamp ties,
and is invisible to `inv_trade_print_tiebreak_triage`? A single such module falsifies "terminal".

## Answer: one module, and it was a lesson row's own measurement half

`scripts/q54_minority_exclusivity_audit.py` — the script that publishes **L321's** headline
minority-unit counts — was invisible to both existing triggers. It names no `kalshi_trades`
path and does not import `q51_maker_fillsim`. It imports the SEALED Q54/S79 probe and reaches
prints through it:

`P.load_all_prints` → `P.eligible_tickers` → `P.entry_candidates` → `P.first_agreeing_print`

`first_agreeing_print` **selects one print** per decision instant, and the selected print's
`yes_price` sets `entry_price` *and* decides the probe's price-band admission — so the order of
exact-timestamp ties is load-bearing by construction, not merely formally. The audit was
therefore publishing L321's numbers on an undeclared, incidental file-order tie-break: the
measurement half of one lesson row silently exposed to the hazard named by another.

## The exposure, measured (not assumed)

`python3 scripts/q54_minority_exclusivity_audit.py --sensitivity` (new this run; re-runnable,
read-only, no network, outcome paths sealed, `price_source_tag: broker_truth`):

| quantity | value |
|---|---|
| eligible sports prints in the population | 213,431 |
| prints inside an exact-timestamp `(ticker, created_time)` tie | 103,441 (**48.47%**) |
| tie groups / groups disagreeing on `yes_price` | 25,777 / 7,998 |
| entry rows (baseline, file order) | 221 (214 scoreable) |
| **entry rows filling a DIFFERENT `trade_id` under a REVERSED tie order** | **61 / 221 (27.6%)** |
| **entry rows getting a different `entry_price`** | **20 / 221 (9.0%)** |
| same two counts under an explicit `trade_id` key | 61 / 20 (identical) |

And the headline the audit exists to publish, under all three orderings (`file`, `reversed`,
`trade_id`):

| field | file | reversed | trade_id |
|---|---|---|---|
| entry candidates (all / scoreable) | 221 / 214 | 221 / 214 | 221 / 214 |
| bootstrap units (games) | 45 | 45 | 45 |
| units per side TOUCHING | `{no: 6, yes: 45}` | same | same |
| units per side EXCLUSIVE | `{no: 0, yes: 39}` | same | same |
| mixed units | 6 | 6 | 6 |
| gate as coded (touching) / L321's rule (exclusive) | OPEN / SHUT | same | same |

**Reading.** L321's published numbers are **order-robust on this population, non-vacuously** —
the perturbation demonstrably reached 27.6% of the fill identities and 9.0% of the entry prices
before the headline refused to move (the L249/L250 discipline: an "invariant" claim from a
perturbation that changed nothing is no evidence at all). This is a dated fact about an
append-only, still-backfilling family, **not** a proof: the CLI re-measures it rather than a
test memorising it (L320).

## What was built

1. **The transitive trigger** (`scripts/invariants.py`, GATING, in `STATIC_INVARIANTS`).
   `_trade_print_consumer_stems` / `_trade_print_transitive_import_re` derive the trigger set
   **from `TRADE_PRINT_TIEBREAK_TRIAGE` itself** — every entry whose disposition is not `N/A`
   becomes an import that obliges the importer to declare its own tie-break. Adding a triage
   entry therefore *widens* the net; the direct-only version made the allowlist an escape hatch
   (new lesson **L351**). Real-tree scan: exactly **1** module was invisible; it is now triaged,
   and deleting its entry puts it straight back in the failure list (non-vacuity pinned by a
   test). Honest limits carried in the rule's banner and regression-tested as deliberate misses:
   one hop through a *consumer* only (a chain through a genuine `N/A` module stays dark by
   design), lexical line-scoped import matching, stem-not-path matching.
2. **The measurement** (`scripts/q54_minority_exclusivity_audit.py`, the unsealed measurement
   half): `reorder_ties` (three explicit orderings; unknown mode raises rather than falling back
   to file order, so a typo cannot report "no sensitivity" from a comparison that never ran),
   `build_report(..., tie_break=...)` defaulting to today's behaviour so every prior number is
   unchanged, `perturbation_reach`, `tie_break_sensitivity`, and `--tie-break` / `--sensitivity`.
   **The SEALED probe is not edited** (L311): the re-ordering happens in-process on the loaded
   print series, inside the audit's existing `sealed_outcome_paths` context.
3. **Tests**: 11 new in `tests/test_invariants.py`, 12 new in
   `tests/test_q54_minority_exclusivity_audit.py`.

## What is still owed (unchanged)

L323's **original** repair half stays genuinely `UNENFORCED`: an explicit `trade_id` tie-break
inside `scripts/q51_maker_fillsim.py::load_prints` (the shared loader four modules consume) and
inside the sealed probe. That edit changes *which print a closed verdict filled against*, so it
is verdict-class and owes its own milestone under the two-agent rule — not a silent edit here.
Q54 closing DEAD on 2026-08-09 removes the seal-timing objection L323 recorded, so the milestone
is now schedulable; it is not done in this run.

## Provenance / limits

Single-agent: no `Task`/subagent tool exists in this harness (the L287/L288/L290/L291 precedent),
so the numbers above are one agent's measurement. They are **not verdict-class** (no CI, no P&L,
no registry flip), and every one of them is reproduced by re-running the two commands named
above over committed tape. Every price in the population carries `price_source_tag:
broker_truth` (executed prints), never `synthetic`.

Reproduce:

```
python3 scripts/q54_minority_exclusivity_audit.py --sensitivity
python3 scripts/invariants.py --full
```
