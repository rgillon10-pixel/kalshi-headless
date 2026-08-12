# L320 — a frozen population pin used as a live pass/fail gate: repair, ratchet, and the
# false alarm that healed itself

*2026-08-12 · research loop, IDLE RUN, idle-run policy (a) (UNENFORCED lesson → invariant/test)
· read-only over committed tape + one non-weakening code repair · NOT verdict-class: no
bootstrap CI, no P&L, no registry flip, no kill decision.*

## 0. Why this run took L320

The queue is drained. Every item Q0–Q56 reads DONE / BLOCKED(Ryan-or-credential) / gated /
data-inadequate at its CURRENT status line — independently re-derived this run, and consistent
with `kalshi-edge-hunter`'s round-#28 rescan earlier the same day (0 eligible). Under the v3
idle-run policy that makes option (a) binding: convert an UNENFORCED lesson into an
invariant/test.

The ledger's own scanner (`scripts/invariants.py::_stale_unenforced_scan`) reports **338 rows,
42 marked UNENFORCED, 33 formally disposed, 9 open**: L213, L221, L222, L282, L319, L320, L321,
L323, L338. Of those:

| row | why not taken |
|---|---|
| L213 | remaining half is a Ryan-account trigger-prompt change (out of lane) |
| L221 / L222 | collector cadence — Ryan/VPS write path |
| L282 | a historical tape incident, already recorded as a non-gating note |
| L319 / L321 / L323 | already converted by earlier runs; what remains is each row's terminal, by-admission-unbuildable residual |
| L338 | prose/semantic judgment by its own text; nothing machine-checkable |
| **L320** | **taken** |

L321 was converted by the immediately-preceding run (PR #358); this run deliberately picked a
different row and a different enforcement SHAPE (see §3).

L320's cell carried a caveat — *"Not fixed this run — Q42's own scripts are frozen against
pinned real-tape gate tests (L191) that a dedicated Q42 milestone should update deliberately"*.
That was checked before acting, and it does not bind for this constant: **no test anywhere in
the repo references `PART1_BTC_ZERO_FRACTION` or `within_tolerance_of_part1_btc`**
(`tests/test_q42_crossvenue_funding_join.py` is wholly synthetic/offline, 10 tests, none
touching the pin). The L191 freeze the row feared protects other Q42 assertions, not this one.

## 1. The lesson, restated

`scripts/q42_crossvenue_funding_join.py` carried

```python
PART1_BTC_ZERO_FRACTION = 0.669
JOIN_SANITY_TOLERANCE   = 0.05
...
sanity["within_tolerance_of_part1_btc"] = (
    abs(kalshi_zero_frac - PART1_BTC_ZERO_FRACTION) <= JOIN_SANITY_TOLERANCE)
```

`kalshi_zero_frac` is derived fresh from committed tape on every run, and the tape grows with
every collector pass. The constant does not. So the boolean drifts for a reason that has
nothing to do with what it claims to test (did the join lose or duplicate windows?).

## 2. The new fact: the false alarm SELF-HEALED (new lesson L343)

L320 measured the check reading `False` on 2026-08-09. This run re-measured it *before* writing
any repair — and it now reads `True`:

| date | windows joined / asset | joined BTC zero-fraction | \|Δ\| vs pin 0.669 | boolean |
|---|---|---|---|---|
| 2026-08-09 | 198 | 0.7222 | 0.0532 | **False** |
| 2026-08-12 | 210 | 0.7048 | 0.0358 | **True** |

Same script. Same constant. No edit in between (`git log` shows
`scripts/q42_crossvenue_funding_join.py` untouched since before the L320 audit, exactly as that
audit's "what was not changed" section states). Reproduce with
`python3 scripts/q42_crossvenue_funding_join.py`.

Two consequences, and they are the substance of this finding:

1. **A verdict decided by the reader's run date carries no information.** Neither the `False`
   nor the `True` says anything about join integrity. This is the L27/L165/L323 family in a
   fresh costume: reproducible is not the same as principled.
2. **The obvious repair would have been wrong.** Re-pinning the constant to the fresher reading
   (0.7222, or 0.7048) trades a false alarm today for a false all-clear later, because the drift
   is **non-monotone** — it went out of band and came back. Only removing the frozen number from
   the decision path fixes it.

Corollary for the loop, recorded as **L343**: when an audit hands you a red check, *re-measure
it before writing the repair*. An alarm that has since cleared on its own is the strongest
available evidence that it was never a gate.

## 3. What was built

### (1) Targeted repair — non-weakening, additive

`scripts/q42_crossvenue_funding_join.py`:

* `PART1_BTC_ZERO_FRACTION = 0.669` **kept verbatim** so the drift stays measurable, now
  documented at its definition as a HISTORICAL PIN with an explicit "not a live gate" sentence.
* Both legacy report keys — `expected_part1_btc`, `within_tolerance_of_part1_btc` — **retained
  byte-identical in value** (append-only report shape; nothing deleted, nothing relaxed).
* New `historical_pin_drift(current, pin, tolerance)` →
  `join_sanity.part1_btc_historical_pin` = `{pin, current, drift, abs_drift, tolerance,
  beyond_tolerance, is_live_gate: False, note}`. The record states *in itself* that it is not a
  gate, so `beyond_tolerance: true` cannot be misread as a defect. A `None` population returns
  `None` rather than a fabricated comparison.
* The printed line is relabelled:
  `part1-BTC HISTORICAL PIN 0.669 (NOT a gate, L320): drift=+0.0358 (within tol 0.05) —
  population growth, not a join defect`.
* **The live join gate is untouched**: `joined_matches_full_population` re-derives its bound
  from the CURRENT population on every run, and passes (True for both BTC and ETH today).

### (2) Ratchet — `scripts/invariants.py::inv_frozen_population_pin_declared` (GATING)

Any module under `scripts/` | `core/` | `collection/` | `execution/` that compares a
freshly-derived value against a module-level numeric constant inside `abs(x - CONST) <op> TOL`
must declare that constant in a module-level `HISTORICAL_POPULATION_PINS` mapping **in the same
file**. Fails closed.

The declaration is deliberately **site-local**, not a central registry — a different shape from
L319's `COLLECTOR_SELF_TAPE_READ_TRIAGE`, L321's `MINORITY_SIDE_GATE_TRIAGE` and L323's
`TRADE_PRINT_TIEBREAK_TRIAGE`. The reason: "is this constant frozen against an older
population?" is answerable only where the constant is defined, and a central list of pins would
itself go stale the moment a file moved.

Real-tree scan: **exactly 1 site** in the whole repo carries the shape — the Q42 pin — and it
now declares itself, so the rule is green at 0 failures today and red for the next one.

**Honest limits (banner + a test pins them; L155 — a 0-issue report is PRECISION, never
recall):**

* the trigger is ONE AST shape, `abs(<expr> − NAME)` / `abs(NAME − <expr>)` with NAME a
  module-level int/float. A frozen pin compared with a bare `<`/`>`, through a helper function,
  via a dict lookup, or assembled at runtime is **invisible**;
* declaring a constant records a disposition; it never asserts the disposition is the right one
  (the L319/L321/L323 residual, restated);
* `scripts/invariants.py` is `_file_excluded` from every static invariant, so the rule cannot
  see its own definition site.

### (3) Tests — 18 new

`tests/test_q42_crossvenue_funding_join.py` (+6): drift sign in both directions; the strict `>`
tolerance boundary (exactly-at-tolerance is *not* beyond it); `None` population fabricates
nothing; the report carries the drift record **and** the retained legacy keys; the declaration
and the constant stay in sync; and a **real-tape acceptance test written growth-safe** — it pins
`n_windows_joined >= 198` (a floor) plus structural properties (live gate green, `is_live_gate:
False`, `current != pin`), never an equality on a growing population. That test is written the
way it is *because of the lesson it enforces*: pinning either dated reading would have made the
test itself the next stale constant.

`tests/test_invariants.py` (+12): real-tree-clean acceptance; the Q42 origin site carrying both
halves; fires-on-undeclared; silent-once-declared; dict/tuple/list/set declaration forms; a
DIFFERENT declared name not disarming the rule; local-variable, string-constant and
non-subtraction negatives; directory scoping; file exclusions; garbage input; STATIC_INVARIANTS
registration; and a banner-honesty pin (the rule's own source must state its limits).

## 4. What this is NOT

No bootstrap CI, no P&L, no fill model, no price claim of any kind. Q42's own verdict is
unchanged (still H1 UNDECIDABLE, still data-gated), `kb/strategies/00-index.md` is untouched,
and the repo still has **0 proven edges**. This is a correctness/tooling milestone: the
two-agent verdict rule does not gate this class (L104/L110/L118/L126/L127/L137/L287 precedent),
and no `Task`/subagent tool exists in this harness in any case — stated, not glossed. The
redundancy that was available was used: the two dated readings were reproduced independently by
`scripts/hl_funding_tape_quality.py::build_report` (08-09, per L320's own citation) and by
`scripts/q42_crossvenue_funding_join.py` (08-12, this run).

## 5. Re-run

```
python3 scripts/q42_crossvenue_funding_join.py            # prints the drift record
python3 -m pytest tests/test_q42_crossvenue_funding_join.py -q
python3 -m pytest tests/test_invariants.py -q -k frozen_pin
python3 scripts/invariants.py --full                      # the gating ratchet
```
