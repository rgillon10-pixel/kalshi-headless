# `anomalies` was a `tape_gap_monitor.py` blind spot (L139)

**Date:** 2026-07-23 · **Run:** cloud research-loop, idle-run (policy c: data-quality deep-dive)
**Status:** fix built + tested, no strategy claim, no registry change

## What this is

Zero eligible queue items this run (Q0–Q47 all DONE/DEAD/BLOCKED/GATED, matching every run
since 2026-07-16) → idle run. `main`'s own `python scripts/invariants.py --full` gate is still
red (issue #157, independently re-confirmed this run — see Gates below), so idle-run policy (a)
(convert an UNENFORCED lesson) is exhausted: the only two open UNENFORCED rows are L131 (issue
#157 itself — explicitly Ryan's call, not touched) and L136 (already claimed by open PR #159,
not redone). Policy (b) (probe-prep for the next time-gated item) has nothing new: Q43's probe
already self-activated and was extended by PR #164 earlier today. So this run took policy (c): a
data-quality deep-dive on a tape family nobody has audited yet.

## Finding

`scripts/tape_gap_monitor.py::build_report`'s default family list is
`list(FAMILY_CONFIG.keys())` — a family with no entry in `FAMILY_CONFIG` is not just
mis-scored, it is **never evaluated at all**. `tape/anomalies/` (written by
`scripts/anomaly_sweep.py`, run as a subprocess from `collection/hourly_pass.py` only when
`ts.hour == ANOMALY_SWEEP_UTC_HOUR` (9) — the exact same single-exact-UTC-hour gate shape as
`settlement_ledger` before L123 and `weather_actuals` before L126) had no `FAMILY_CONFIG` entry.
Both L123 and L126 found real multi-day freezes in exactly this failure shape (an exact-hour
collector gate the live cron never lands on, invisible because the monitor never watched the
family) — `anomalies` was exposed to the identical risk and nobody had checked.

**Not currently frozen** (unlike L123/L126's finds): real committed tape shows a healthy daily
cadence through `dt=2026-07-22` (last real `captured_at` 2026-07-22T10:05:33Z, ~17h old at run
time — well under the 48h STALE threshold). This is a pre-emptive close of a blind spot, not a
reactive fix for an already-realized gap.

## Fix

Registered `"anomalies": {"interval_h": 24.0, "passes_per_day": 1, "kind": "daily-econ-slot"}`
in `scripts/tape_gap_monitor.py::FAMILY_CONFIG` (same shape as `econ_prints`/
`polymarket_cpi_pairs`, its sibling single-exact-hour daily slots). Two new HARD acceptance
tests anchored to the real committed tape (`tests/test_tape_gap_monitor.py`):
- `test_acceptance_9_l139_anomalies_was_a_monitoring_blind_spot` — proves the family is now
  visible in the report and does not false-alarm on its actual healthy state.
- `test_acceptance_10_l139_anomalies_would_be_caught_if_it_ever_froze` — evaluated at a `now`
  past the real last capture + 48h, proves the registration is load-bearing (the detector
  actually pages), not cosmetic.

New lesson **L139** in `kb/lessons/00-lessons.md`.

## Two-agent verdict rule

N/A — non-gating monitor-registration extension, same precedent as L118/L121/L122/L124/L126/L127/L128
(no registry flip, no bootstrap CI, no kill decision).

## Gates

- `pytest tests/test_tape_gap_monitor.py`: 54/54 green (2 new).
- Full suite excluding the two files broken by the pre-existing `cryptography`/`_cffi_backend`
  ABI panic (issue #157, tracked separately): **1430 passed**, same 5 pre-existing
  `test_invariants.py` failures as base `main` (identical failure set — this diff touches
  neither `tests/test_invariants.py` nor either of the two files issue #157 flags).
- `python scripts/invariants.py --full`: exit 2, identical 2 violations to `main`'s pre-existing
  state (issue #157) — unrelated to and untouched by this diff.

## Not merging yet — `main`'s own gate is red

Per `LOOP-QUEUE.md` step 6, this PR stays open until issue #157 resolves, joining the now
double-digit stack of PRs blocked behind it (#158–#166 plus this one) since PR #153 merged
2026-07-22T04:20Z (~23h ago at run time). This diff is green in isolation and touches none of
the files #157 flags.
