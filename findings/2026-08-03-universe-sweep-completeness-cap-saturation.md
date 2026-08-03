# `universe_sweep`'s completeness_ok signal is structurally saturated — the VPS pager fires on a known fact, not a new failure

**Date:** 2026-08-03 · **Author:** research loop, idle-run policy (c) (data-quality deep-dive, tape-auditor subagent + main-context build) · **Verdict class:** data-quality / operational, no strategy claim, no registry change, two-agent rule N/A (a tooling advisory, same posture as L156/L185/L208's non-gating checks — not a CI or kill decision)

## Summary

`tape/universe_sweep/`'s breadth-sweep collector (`collection/universe_sweep.py`, wired into
`collection/hourly_pass.py` at UTC hours {0, 6, 12, 18}) harvests under a hard row cap:
`MAX_CALLS = 20` pages of `PAGE_LIMIT = 1000` = **20,000 rows/pass**
(`collection/universe_sweep.py:74-75`). Every one of the **35** committed captures
(`dt=2026-07-17` through `dt=2026-08-03`) sits at **exactly** 20,000 lines — the pagination
cursor never exhausts, because the real open-market universe is well above the cap (the
module's own comment, "the whole open universe is ~10k markets", is stale; this run measured
the cursor active at >20k on every real pass).

`collection/universe_sweep.py:224` computes `completeness_ok = cursor_exhausted and
n_parse_errors == 0` — honest "partial coverage" accounting for a single pass. But
`collection/hourly_pass.py:587` folds that leg's `completeness_ok` into the WHOLE PASS's
completeness via an AND (`completeness_ok = completeness_ok and bool(r.get("completeness_ok",
False))`), and `collection/hourly_pass.py:635` returns exit code 1 whenever the pass-level flag
is False. `ops/vps/kalshi-headless-hourly.sh:86-87` fires a `Priority: high` phone notification
to Ryan on that nonzero exit. The consequence: **every hourly pass that reaches its
`universe_sweep` leg exits 1 and pages Ryan at high priority, for a fact that has been true on
100% of real passes since the collector landed** — indistinguishable, in both the exit code and
the notification text, from a genuine new outage.

Measured blast radius (last 14 days, hour attributed via `crypto_hourly.captured_at` as a
same-pass proxy — an observation, not a precise per-leg count): **33 of 91 passes (36.3%)** ran
at one of the four `universe_sweep` gate hours; on `dt=2026-08-02`, 3 of 6 passes (50%) were
structurally guaranteed to page. The fraction is elevated by the VPS-death cadence collapse
(L269: ~273.9h outage) shrinking total passes/day from ~48 to 4-7, making the 4 fixed gate hours
a much larger share of everything that still runs.

## Precedent, and what was new

The bounded-cap SHAPE itself is known: L96 (2026-07-18) measured the cursor exceeding 80k;
L125 measured the ~97% `KXMVE*` junk composition; `kb/00-LOG.md:8955-8959` (2026-07-17)
flagged the IDENTICAL "`completeness_ok=False` is the expected steady state" property for
`settlement_ledger` and explicitly left open whether `hourly_pass` should fold that leg's
result into the pass-level AND as-is — a design call never revisited when Q46 landed
`universe_sweep` with the same property at 4x the firing frequency. What was NOT previously
recorded anywhere (checked `kb/lessons/00-lessons.md` for `notify|alarm|pass_rc` —
only L134/L139/L156, all about wiring an alarm to a clock, none about a wired alarm stuck ON):
the ALARM-FATIGUE consequence — that a permanently-saturated leg's completeness flag, ANDed
into a pager trigger, makes a real new failure at the same gate hour indistinguishable from
the standing condition.

## What this run built (cloud-buildable measurement half only)

A non-gating advisory, mirroring the L185/L208 tape-shape-check pattern exactly:

- `scripts/tape_gap_monitor.py::COMPLETENESS_CAP_FAMILIES` — config dict, two entries:
  `universe_sweep` (cap 20,000) and `settlement_ledger` (cap 5,000, the sibling shape).
  `COMPLETENESS_CAP_SATURATION_ALERT_FRACTION = 0.90` — only flag a family whose measured
  at-cap fraction clears 90%, so an occasionally-capped family (a capacity/adequacy question,
  L185's territory) is not conflated with a structurally-saturated one.
- `scripts/tape_gap_monitor.py::completeness_cap_saturation(tape_root, family)` — groups every
  committed line by `capture_id`, counts rows per capture, and reports `n_at_cap`/`n_captures`/
  `fraction_at_cap`/`saturated`. Returns `None` for an unregistered family or a sample below
  `min_captures_for_verdict=3` (an adequacy floor, never a guess either way).
- `scripts/invariants.py::_completeness_cap_saturation_issues()` +
  `completeness_cap_saturation_warning()`, wired into `main()`'s `--full` advisory block,
  `except BaseException`-wrapped like every sibling stanza (the L156 DEFECT-1 posture: neither
  the detector nor the formatter raising, nor a non-str formatter return, can reach the exit
  code).
- 17 new tests: 9 in `tests/test_tape_gap_monitor.py` (unregistered family, below-adequacy-floor,
  all-at-cap flagged, below-threshold NOT flagged, capture_id-less rows skipped honestly, plus
  2 HARD real-tape acceptance tests), 8 in `tests/test_invariants.py` (issues/warning
  unit shapes, never-gates-exit-code, wired-to-stderr, raise-cannot-flip-exit-code, plus 2 HARD
  real-tape acceptance tests: `universe_sweep` IS flagged, `settlement_ledger` is NOT).

Reproducible: `python3 -c "import sys; sys.path.insert(0,'scripts'); from pathlib import Path;
import tape_gap_monitor as T; print(T.completeness_cap_saturation(Path('tape'),
'universe_sweep')); print(T.completeness_cap_saturation(Path('tape'), 'settlement_ledger'))"` →
`{'family': 'universe_sweep', 'cap': 20000, 'n_captures': 35, 'n_at_cap': 35,
'fraction_at_cap': 1.0, 'saturated': True}` / `{'family': 'settlement_ledger', 'cap': 5000,
'n_captures': 4, 'n_at_cap': 1, 'fraction_at_cap': 0.25, 'saturated': False}` — the asymmetry
between the two families sharing the identical cap SHAPE is the self-check that this measures
the structural rate honestly, not a hard-coded assumption.

## What this run did NOT do (Ryan/VPS-gated repair half)

Two possible fixes exist, both design calls, neither built or attempted here:

1. Raise `MAX_CALLS` (or add pagination beyond the current 20-page bound) so the cursor
   actually exhausts — a collector-lane change with cost/quota implications only Ryan can
   weigh.
2. Change `hourly_pass.py`'s fold-in so a KNOWN-saturated leg (per this advisory) is reported
   on its own axis instead of ANDed into the pager-triggering `completeness_ok` — the exact
   2026-07-17 open question for `settlement_ledger`, now measurably also true for
   `universe_sweep`.

Neither is a cloud-run decision: both touch collector/pager semantics that the Stop rules and
this project's "Ryan reviews the alarm design" discipline reserve for him. The lesson (L270)
records both candidates verbatim so neither needs re-deriving.

## Gates

`pytest -o addopts='' -q` → 2779 passed, 0 failed (was 2762 before this diff — 17 new tests, 0
regressions). `python3 scripts/invariants.py --full` → exit 0, all green; the new L270 advisory
fires and correctly names `universe_sweep` only (not `settlement_ledger`), alongside every
pre-existing advisory, unchanged.
