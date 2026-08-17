# L362 converted: the sensitivity-grid edge check — and the lesson's own proposed rule is refuted

**Date:** 2026-08-17 · **Run:** kalshi-research-loop, protocol v3, **IDLE RUN, idle-run policy (a)**
(convert an `UNENFORCED` lesson into an invariant/test) · **Class: TOOLING + MEASUREMENT.**

**Nothing here is verdict-class.** No registry flip, no bootstrap CI, no P&L, no kill decision;
**still 0 proven edges.** No price is read anywhere in this work:
`price_provenance = {prices_quoted: false, price_source_tag: null}`.

**Two-agent rule: NOT SATISFIABLE in this harness** — no `Task`/subagent tool exists here (the
L287/L288/L290/L291/L295/L308/L313/L325/L349/Q57b precedent), so no independent `verifier` could be
dispatched. The rule does not bind this milestone class anyway (lesson→test conversion: no CI, no
registry flip, no kill — the L104/L110/L118/L126/L127/L137 precedent), and the redundancy fallback
below stands in for it. Every number in §2 is machine-computed by a committed, re-runnable script.

## 0. Why this item

The queue is drained: Q0–Q56 are DONE / CLOSED / gated at their newest-dated Status line, and Q57's
path (b) closed the same morning with path (a) data-gated on a ~1-in-45 arrival. Under policy (a),
`stale_unenforced_recall_report()` showed **13** genuinely-open `UNENFORCED` rows — the 10 long-triaged
Ryan-lane ones plus **three untouched rows added 2026-08-16 by the Q57 verifier round: L362, L363,
L364**. L362 was picked because it is the only one of the three whose subject matter is structured
data already in the tree (grids and sealed spec dicts), so it can be enforced precisely rather than
by prose-lint.

## 1. What was built

| file | role |
|---|---|
| `core/sensitivity.py` (new) | the arithmetic. `axis_spacing()` classifies an axis (arithmetic / geometric / irregular / singleton); `out_of_grid_probes()` returns the value ONE STEP PAST each edge in the axis's own spacing, or an honest reason (`irregular_spacing`, `at_natural_bound`, `singleton_axis`); `axis_edge_status()` / `grid_edge_report()` / `structural_claim_admissible()` record where the seal sits and whether each edge was actually probed. |
| `scripts/invariants.py` (extended) | the repo-wide inventory. `_sensitivity_grid_declarations()` (AST) reads three declaration shapes; `_sensitivity_grid_edge_issues()` flags a sealed value sitting AT an edge; `sensitivity_grid_edge_warning()` is wired **NON-GATING** into `--full` (stderr only, wrapped so neither the scanner nor the formatter can reach the exit code — the L156 DEFECT-1 lesson). |
| `scripts/sensitivity_grid_edge_report.py` (new) | the re-runnable artifact: `--json` / `--write` → `reports/l362_sensitivity_grid_edges.json`. Composition only — AST-pinned to define neither the detector nor the arithmetic (L36/L102 twin discipline). |
| `tests/test_sensitivity_grid_edges.py` (new) | **57 tests** in four tiers: arithmetic, scanner shapes, scanner BLIND SPOTS pinned as deliberate misses, and real-tree acceptance as directions/floors (L320/L191) with the single exact pin that IS the lesson. |

**The pin that is the lesson.** `out_of_grid_probes((30, 60, 120, 240, 480))["low"] == 15.0`. Q57's
window axis is geometric with ratio 2; one step below its own low edge is 15 minutes — **the exact
value at which the verifier, by hand, found the "structural" sign-variation degeneracy dissolve.**
The tool derives it from the seal as committed, before any cell is run.

## 2. What the live tree says (`reports/l362_sensitivity_grid_edges.json`, regenerable)

**13** readable grid axes across **6** modules; **5** paired to a sealed value; **1** seats its seal
at an edge; **0** modules record a single executed out-of-grid cell.

1. **L362's own candidate rule is refuted.** The row proposed "require the pre-registered value not
   be the min/max of any swept axis." Measured: **all four** of Q57's axes are INTERIOR
   (`flow_window_minutes` 120 inside (30,60,120,240,480); `min_abs_rho` 0.20 inside (0.05…0.40);
   `min_window_count` 100 inside (0,100,1000); `max_entry_lag_minutes` 60 inside (30,60,240,4320)).
   The proposed rule **passes the very run it was written for.** The enforceable content of L362 is
   the out-of-grid PROBE, not the seal's position (new **L371**).
2. **The one edge-seated seal is mechanism-excluded, not a defect.**
   `scripts/q28_s24_nearclose_fade_probe.py::X_SWEEP` runs (0.02, 0.03, 0.04, 0.05) with
   `X_PRIMARY = 0.02` at the low edge; one arithmetic step below is 0.01 — and that module's own
   docstring excludes it by mechanism ("PRIMARY X = 2¢, clearly beyond a one-tick flicker"). The
   honest remedy is a DECLARED natural bound, which `out_of_grid_probes(..., bounds=)` supports;
   it is not a cell anyone should run. Recorded as an issue by the advisory precisely so the bound
   gets declared rather than assumed.
3. **The most recent structural-class claim still owes 7 of its 8 edges.** Cross-module coverage of
   Q57's grid by the Q57b census — the only out-of-grid probing this repo has ever done — is
   **1 / 8**: past the `flow_window_minutes` low edge (down to 15, which is how the value got
   measured at all) and past **0** high edges on any axis. `structural_claim_admissible = False`.
4. **Mechanical extension covers under a third of the tree.** **9 of 13** axes are irregularly spaced,
   so the tool refuses to name a step (`(30,60,240,4320)`, `(0,100,1000)`, `(0.01,0.02,0.03,0.05)`).
   That refusal is the honest answer, and it makes the cheap half load-bearing: an axis whose edge
   already sits on its physical floor is settled with no probe at all (new **L372**).

**Construction defect caught by this suite before commit** (recorded, not laundered): the natural-bound
check must run BEFORE the spacing refusal. The first draft returned `irregular_spacing` for
`min_window_count = (0, 100, 250)` with `bounds=(0.0, None)` — an axis literally sitting on its own
floor was reported as a permanently unmet obligation. Fixed, with 4 regression tests
(`TestNaturalBoundPrecedence`).

## 3. Redundancy (in place of the unavailable second agent)

- The `15.0` headline is derived twice by different routes: the library's geometric extension, and a
  hand check on the committed literal (480/240 = 240/120 = 120/60 = 60/30 = 2 → 30/2 = 15).
- The scanner's recall is stated, not implied: five known blind spots (symbolic axis values, an
  expression-valued seal, a grid built inside a function, a <2-element sequence, a comprehension) are
  pinned as deliberate MISSES, so a 0-issue report is evidence of PRECISION only, never of RECALL
  (L155). The advisory text carries that sentence verbatim.
- The committed JSON is pinned to a fresh run on its stable aggregates, so it cannot drift into a
  hand-edited number.

## 4. What this does NOT do

- It does not run any out-of-grid cell for any strategy. Probing past the edge on Q57 would mean
  re-running a sealed probe; that is Q57's own path, not this milestone's, and Q57 is closed on (b).
- It does not make an interior seal safe. Every real-tree test asserts the opposite.
- It says nothing about whether an out-of-grid cell is MECHANISM-FAITHFUL — Q57b's own 180-minute
  entry-lag cells cleared every population floor while abandoning the mechanism. Probing past the
  edge is necessary for a structural claim, never sufficient for an alive one.

## 5. Owed next

`L363` (a written reopen condition must be evaluated against current tape before it is filed) and
`L364` (an untaken outcome-blind alternative must have its population SHAPE measured, not predicted
away) remain the two open `UNENFORCED` rows from the same verifier round — both are document-level
conventions over `findings/`, enforceable only as prose-lint with a real false-positive budget, and
neither was attempted here. Open `UNENFORCED` rows: **13 → 12**.

## 6. Inherited red gate found and repaired (not this run's breakage — reproduced at pristine HEAD)

The full-suite gate came back **4,594 passed / 1 failed**, and the failure was not this run's:
`tests/test_hl_funding_tape_quality.py::test_real_tape_degenerate_window_share_is_material_and_a_point_mass`
asserts `both_degenerate_fraction > 0.25`, and BTC now reads **exactly 56/224 = 0.25**. Checked out
`HEAD` (`6254b92`) into a throwaway worktree with none of this run's edits present: **it fails there
too.** `main`'s gate was already red when this run began — the 04:11Z hourly pass appended perp
windows, the numerator stayed at its own pinned floor of 56, and the ratio decayed onto the boundary.
This run touched neither `tape/hyperliquid_funding/` nor `tape/perp_tape/`.

Repaired in place, in the repo's own idiom (**L263** — a quality ratio falls when you add good data,
so the absolute numerator is the claim; **L320/L191** — pin directions and floors, never a knife-edge
on a round number): the numerator floor is unchanged and now fails first, and the ratio carries a
non-strict `>= 0.20` with the measured value in the failure message. The materiality claim the test
exists to make is untouched. Recorded as **L373**; a repo-wide `assert <ratio> > <round literal>` lint
is buildable and is named there as the obvious next policy-(a) unit.
