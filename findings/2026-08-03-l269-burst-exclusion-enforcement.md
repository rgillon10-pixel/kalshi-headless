# L269 enforced: declared burst-window captures can no longer stand in for a scheduled collector pass

`2026-08-03` · research loop, **IDLE RUN, idle-run policy (a)** (UNENFORCED lesson → test)
· producer: main context · **verdict class: TOOLING / MEASUREMENT — no registry flip, no
bootstrap CI, no kill decision, no P&L claim, no price asserted**

## The defect (L269, diagnosed earlier the same day, not re-derived here)

`scripts/invariants.py::_collector_leg_last_seen` took the MAX `captured_at` across ALL
`hourly-dual` families, bucketed by minute-of-hour, with **no burst-window exclusion**. A
declared burst trigger deliberately re-fires the collectors every 60-120 s inside its window,
and those passes carry whatever minute-of-hour they land on. One
`kalshi-burst-fomc-0729` pass (window 17:40-19:45 Z) landed at `:29` — inside the `vps` bucket
(minutes 20-29) — for `crypto_hourly` and `polymarket_macro_pairs`, both named in that
trigger's own `burst_keys`. The aggregate MAX then read that burst pass as a live VPS pass.

Prior diagnosis and evidence:
`findings/2026-08-03-vps-collector-true-outage-273h-burst-contamination-blind-spot.md`
(research loop, ~03:2x Z, idle-run policy (c)), which named the fix but deliberately did not
build it. This run builds exactly the candidate that row named — no redesign.

Same blind-spot class **L213** already closed for `slot_cadence_by_time_of_day`; this function
never got the equivalent exclusion.

## What landed

`scripts/invariants.py`

* `_family_burst_windows(tgm, family)` — reads the padded declared windows from
  `scripts/tape_gap_monitor.py::_burst_windows_for_family`, i.e. the ONE existing home of
  `BURST_TRIGGER_WINDOWS` + `BURST_WINDOW_PAD_S` (900 s). No second copy of the table. Returns
  `None` — a *distinct* "table unavailable", never an empty list — when the helper is missing
  or raises.
* `_collector_leg_last_seen(..., exclude_burst_windows: bool = True, stats: dict | None = None)`
  — skips a capture that falls inside a padded declared window **for that family**. Per-family,
  never global wall-clock: the identical instant in a family no trigger covers still counts.
  `exclude_burst_windows=False` reproduces the pre-L269 reading exactly (so the defect stays
  demonstrable, per L251's "keep the old cut runnable" discipline).
* Degradation is **toward the old behaviour, never toward silence**: if the window table can't
  be read, that family is counted without the exclusion and the family is named in
  `stats["burst_table_unavailable"]`. A blanked advisory is how an outage goes unnoticed.
* `_dead_collector_leg_diagnosis(..., exclude_burst_windows=True)` threads it through and
  publishes `n_burst_excluded`, `burst_excluded_by_family`, `burst_table_unavailable`,
  `scan_oldest_day` in its facts dict.
* `dead_collector_leg_warning` gains two optional provenance lines (rendered only when the keys
  are present, so a pre-L269-shaped diag still renders unchanged). The advisory stays
  **NON-GATING** — it is written to stderr and never appended to `failures`; the existing
  `test_advisory_is_non_gating` still pins that.

## Measured effect (committed tape, this tree, `now = 2026-08-03T12:45:00Z`)

Live scan (`max_day=None`, production `DEAD_LEG_LOOKBACK_DAYS = 10`):

| leg | exclusion OFF (pre-L269) | exclusion ON (this build) |
|---|---|---|
| `vps` | `2026-07-29T18:29:45.808389Z` — **114.3 h** | `2026-07-15T19:23:54.847425Z` — **449.4 h** |
| `cloud` | `2026-08-03T06:56:06.724517Z` — 5.8 h | `2026-08-03T06:56:06.724517Z` — 5.8 h (unchanged) |
| `other` | `2026-08-03T07:01:57.192747Z` — 5.7 h | unchanged |

Excluded: **82 captures** — `crypto_hourly` 24, `polymarket_pairs` 35,
`polymarket_macro_pairs` 23. Only `vps` moves; no other leg's reading changes.

Pinned historical slice (`max_day=2026-08-01`, the shape the new acceptance test asserts):

* OFF → `vps` = `2026-07-29T18:29:45.808389Z` (114.3 h) — the contaminated FOMC-burst reading.
* ON  → `vps` = `2026-07-22T17:29:49.498223Z` (283.3 h) — **reproduces the prior finding's
  honest value to the second**, independently of that finding's code path.

`invariants.py --full` exit code is **unchanged (0)**; the advisory was and remains non-gating.

**Honest caveat on the live `--full` run.** The collector-health advisory did NOT print during this
run's gate pass, and that is pre-existing behaviour unrelated to L269: `_dead_collector_leg_diagnosis`
requires a SURVIVOR (some leg capturing within `DEAD_LEG_ALIVE_HOURS = 6`) before it will name a dead
leg, and at gate time the newest cloud capture (`2026-08-03T06:56:06Z`) was ~7.1h old, so the
"one leg silent but nothing is producing right now either" branch correctly stayed quiet rather than
mis-attributing a possible whole-pipe outage. The numbers above are therefore stated at the FUNCTION
level (`_collector_leg_last_seen` / `_dead_collector_leg_diagnosis` with an injected `now`), which is
also exactly what the new tests pin — not scraped from a `--full` stderr block that happened not to
fire. Quoting the rendered advisory when it did not render would have been an L165-class citation
error.

## Secondary finding (new, and the reason the live number is 449.4 h and not 283.3 h)

`DEAD_LEG_LOOKBACK_DAYS = 10` bounds the scan to the newest **10 day-FILES per family**, which
is a **ragged** horizon, not 10 calendar days. Families that write a file most days reach back
~10 days; a sparse family (`polymarket_pairs`) reaches back much further. On today's tree that
means:

* the dense families' `2026-07-22T17:29:49Z` vps capture has fallen OUT of their own 10-file
  window, while
* a sparse family's genuine `2026-07-15T19:23:54Z` vps capture is still IN its window,

so the post-exclusion MAX is `07-15`, i.e. the reported last-capture date can be **OLDER than
the leg's true last capture** and the silence figure correspondingly **over**-stated (449.4 h
reported vs 283.3 h true). Both readings are far worse than the 114.3 h the pre-fix code
published, so the direction of the fix is not in question — but the exact date is not a
measurement. The advisory now says so in the "horizon caveat" line rather than leaving a
reader to assume the date is exact. Recorded as **L271**.

This is deliberately NOT repaired here (widening the horizon changes the bounded-I/O contract
that `DEAD_LEG_LOOKBACK_DAYS`'s own comment defends, and the honest fix — a per-family
CALENDAR-day horizon — is a cost/design call, not a mid-loop patch). The candidate is recorded
verbatim in L271 so it needs no re-deriving.

## Tests (all offline; `tests/test_dead_collector_leg_advisory.py`)

* `test_burst_window_capture_is_excluded_for_a_burst_covered_family` — the defect itself, and
  that `exclude_burst_windows=False` still reproduces it.
* `test_same_instant_counts_for_a_family_no_declared_trigger_covers` — per-family, not
  wall-clock. This is the assertion that stops the fix from over-reaching.
* `test_burst_pad_boundary_is_respected` — 17:24 Z outside / 17:26 Z inside the 900 s-padded
  17:25-20:00 window.
* `test_exclusion_is_reported_not_silent` — an invisible exclusion is indistinguishable from
  missing data (L263's "quote the numerator" discipline).
* `test_missing_burst_table_degrades_to_old_behaviour_not_to_nothing` +
  `test_family_burst_windows_returns_none_when_the_helper_raises` — degradation direction.
* `test_burst_windows_table_has_exactly_one_home` — no second copy of `BURST_TRIGGER_WINDOWS` /
  `BURST_WINDOW_PAD_S` in `invariants.py` (same discipline as the existing
  `test_leg_signatures_come_from_tape_gap_monitor`).
* `test_warning_renders_for_a_diag_without_the_l269_keys` / `test_warning_names_the_exclusion_when_present`.
* `test_acceptance_real_tape_burst_exclusion_moves_the_vps_reading` — HARD acceptance over the
  REAL committed tape, pinned at `max_day=2026-08-01` + no `datetime.now()` call (L140
  anti-time-bomb), asserting OFF starts `2026-07-29T18:29:45`, ON starts `2026-07-22T17:29:49`,
  `on < off` ("the fix must make the outage look LONGER, never shorter"), and `cloud` untouched.

## Two-agent rule

**N/A by milestone class, and stated rather than assumed.** No registry status flip, no
bootstrap CI destined for `kb/`, no kill decision — this is a tooling/measurement change over
committed tape. The `Agent`/`Task` tool was UNAVAILABLE in this session, so no independent
`verifier` was dispatchable; the milestone was deliberately chosen non-verdict-class for that
reason (same posture as the 2026-08-01 ~04:xx and ~22:5x runs). Redundancy instead comes from
an independent code path: the `283.3 h` / `2026-07-22T17:29:49Z` figure was derived here by
new code and matches the prior run's hand-derivation exactly, and the pre-fix reading remains
runnable via `exclude_burst_windows=False` so the delta is reproducible by anyone.

## What this does NOT claim

No edge, no price, no fill, no P&L. Still **0 proven edges**. `kb/strategies/00-index.md` is
untouched. The VPS collector remains dead and un-restartable from a cloud run (L117/L129) —
this run only makes the advisory tell the truth about how dead it is.

## Gates (fresh, after the last code change — L162)

* `python -m pytest -q` — **2,789 passed / 0 failed / 0 skipped, exit 0** (was 2,779 before this diff, +10 new; count taken AFTER the last code change, L162).
* `python scripts/invariants.py --full` — exit 0, `invariants: all green` (15 standing non-gating advisories, unchanged in kind; the L152 advisory now reads `n_open_unenforced=3` [L213/L221/L222] and mixed-tier [L168/L270/**L271**] — L269 correctly gone).
