# L171 disposition: retrospective-list family coverage in `tape_gap_monitor.py`

2026-07-26 · research loop, idle-run policy (a) · non-gating monitor extension + tests, no
strategy claim, no P&L, no registry change — two-agent rule N/A (same posture as L109/L118/
L121/L122/L124/L126/L138/L157/L160/L161/L163/L166/L167's monitor/tooling closures).

## The open lesson

L171 (`kb/lessons/00-lessons.md`, filed by the prior idle run's `tape/hyperliquid_funding/`
audit): a collector whose record carries a retrospective LIST of historical observations
(`hyperliquid_funding`'s `prints[].time_ms`) cannot be audited for coverage by `dt=` day-file
presence — `dt=2026-07-18`..`dt=2026-07-21` have no committed file (the L127 VPS-freeze
window), which reads as a 4-day hole by file-count, but the union of every `prints[].time_ms`
across the whole family has zero missing hourly steps (a catch-up pass backfilled the whole
window into one record on the catch-up day). The lesson's own candidate: teach
`tape_gap_monitor.py` a family-kind flag distinguishing "retrospective-list" from
"point-in-time" families, so a coverage read doesn't misreport the pre-catch-up window as
missing.

Re-derived the open `UNENFORCED` lesson set fresh this run (whole-word grep over
`kb/lessons/00-lessons.md`, tracing every historical row to a later `supersedes`/
`Formal disposition of` closure, per the L108/L112/L116 discipline used every prior idle
run): **L171 is the sole open row.**

## What was built

`scripts/tape_gap_monitor.py`:

- `RETROSPECTIVE_LIST_FAMILIES: Dict[str, Dict[str, Any]]` — a small, explicit,
  human-editable map (mirrors `EXPECTED_COLLECTOR_BUCKETS`'s shape) naming which families
  carry an embedded-observation-list record shape, and how to read it: the record field
  holding the list (`list_key`), the per-item epoch-ms timestamp field (`time_key`), and the
  list's own fixed grid spacing (`step_seconds`). Seeded with exactly the one family L171
  named: `hyperliquid_funding` (`prints`, `time_ms`, 3600s).
- `retrospective_coverage(tape_root, family) -> Optional[Dict]` — computes real coverage for
  a registered family as the UNION of every embedded observation timestamp across ALL
  committed `dt=*.jsonl` files (not file presence): `n_observations`, `span_start`/
  `span_end`, and `n_missing_steps` (expected fixed-step slots between the observed min/max,
  minus what was actually seen). Malformed/missing embedded timestamps are skipped, never
  fabricated into the union (mirrors `extract_completeness`'s "no signal, never a guess"
  discipline) — a non-dict list item, a missing/wrong-typed `time_key`, or a bool masquerading
  as an int (`isinstance(t, bool)` excluded explicitly, since `bool` is a subtype of `int` in
  Python) are all skipped. Returns `None` for any family not registered in
  `RETROSPECTIVE_LIST_FAMILIES` — the function makes no claim about a family it wasn't told
  carries this shape.
- `evaluate_family(..., tape_root: Optional[Path] = None)` — new optional parameter (default
  `None`, so every existing call site in this repo and its test suite is unaffected). When
  given and the family is registered, the health record gains a `retrospective_coverage` key
  with the reading above; `None` otherwise (never fabricated). Does NOT feed the STALE/
  UNDER-CAPTURE alert path — `hyperliquid_funding`'s forward-collector-cadence freeze
  detection (L127/L128, STALE at 2h) is already correct and untouched; this is purely an
  additional, correct coverage signal for the family's *historical* completeness, which file
  presence cannot represent for this record shape.
- `build_report()` now passes `tape_root` through to every family's `evaluate_family()` call,
  so the field is populated end-to-end in the monitor's normal report output.

## Verification

New tests (`tests/test_tape_gap_monitor.py`, +7, 59→collected count in the file below):
unregistered family returns `None`; empty tape returns the zero-observation shape; a
constructed fixture reproducing the EXACT L171 shape (day-file hole `dt=18`..`dt=21` absent,
catch-up record on `dt=22` backfills the gap) asserts `n_missing_steps == 0` while
independently confirming the day-file read WOULD have seen the hole (proving the function is
not a no-op relative to the naive read it replaces); a genuine-gap fixture (hours 0,1,2 then a
jump to hour 5) asserts `n_missing_steps == 2`; a malformed-items fixture (missing key, wrong
type, bool, non-dict list item) asserts only the 1 well-formed observation counts;
`evaluate_family`'s wiring is tested three ways (populated with `tape_root`, `None` without
it, `None` for an unregistered family even with `tape_root` given).

**HARD real-tape acceptance test** (`test_acceptance_11_l171_hyperliquid_funding_real_tape_
zero_missing_steps`): asserts the real committed `tape/hyperliquid_funding/` still has no
`dt=2026-07-18`..`dt=2026-07-21` files (so the test's premise — day-file presence looks like a
gap — actually holds; the assertion fails loudly with a message pointing at re-verification,
not silently, if that premise ever changes), then asserts `retrospective_coverage()` over the
real tape returns `n_missing_steps == 0` with `n_observations > 1000`. Live result this run:
**1,289 distinct hourly `time_ms` values, 0 missing steps**, up from the audit's own 1,282 (a
few hours of tape landed between the two runs — the union is int-idempotent, so this doesn't
threaten the assertion).

## Gates

`pytest -q`: **2025 collected** (`--collect-only -q` summed across 87 files, post-edit), **2
pre-existing failures** in `tests/test_q42_funding_estimate_path_inference.py` (the same
real-tape-drift class every recent run has reported — window/drop counts drift as more
forward `perp_tape`/tape lands; re-confirmed byte-identical on base `main` via `git stash`
this run). `python scripts/invariants.py --full`: exit 0, same pre-existing non-gating
advisory classes (VPS collector leg still dead, ~96.8h silent, worsening, Ryan-side; the L168/
L169 hollow-crypto-ladder advisory; the L52 unguarded-settlement advisory; the L138 raw-
`fromisoformat` advisory; the L157 recovery-dwell advisory) — this diff adds no new advisory
class.

No strategy claim, no P&L, no registry change. Two-agent rule N/A (monitor/tooling extension
converting an `UNENFORCED` lesson into `test`-tier enforcement, not a verdict-class change).
