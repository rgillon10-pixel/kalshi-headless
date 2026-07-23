# Q43 probe: capture-density advisory floor added ahead of the day-count gate opening

**2026-07-23, research loop, idle-run policy (b) follow-up.** Zero eligible queue items
(Q0-Q47 all DONE/DEAD/BLOCKED/GATED — Q43's own gate re-checked fresh this run: `perp_tape`
still 6/7 file-shaped days, `dt=2026-07-17`..`dt=2026-07-22`; `dt=2026-07-23` has not landed
yet at run time 00:1xZ). `main`'s own `invariants --full` gate is still red (issue #157,
byte-identical 2 `order_endpoints_confined` violations to every prior run today and
yesterday — not re-litigated here, still Ryan's call per L131).

## What this adds

`scripts/q43_perp_binary_consistency_probe.py` gated its two analysis legs purely on
`_perp_days_available() >= 7` (file-count). That mirrors exactly the trap Q36 already fell
into and had to re-diagnose (`findings/2026-07-20-q36-weather-books-data-adequacy.md`):
**calendar/day-count-gate-open does not mean data-adequate.** Q43's own queue history
(`findings/2026-07-20-tape-cadence-decline-vps-collector-down.md`, L117) already flagged that
perp_tape's per-day capture density was collapsing (30→14→6→7→5 captures/day 07-17→07-21) even
while the *day-count* kept climbing toward 7 — the exact mismatch that made Q36's first live
read misleading.

Rather than wait for the gate to flip and discover this the same way Q36 did, this run adds
an **advisory-only capture-density readout** to the Q43 probe:

- `_perp_capture_density(perp_glob)` — distinct-capture count per `dt=` day file (keyed on
  `captured_at`, falling back to `capture_id`).
- `_thin_days(density, floor=MIN_CAPTURES_PER_DAY_ADVISORY)` — flags days below the floor
  (`MIN_CAPTURES_PER_DAY_ADVISORY = 10`, chosen as roughly half the ~20-30/day healthy rate
  seen on 07-17/07-22; advisory only, never a hard gate — `PERP_DAYS_REQUIRED` stays the only
  thing that blocks the live analysis legs).
- Both fields (`capture_density_by_day`, `thin_days`) now travel on EVERY report — including
  the current `INSUFFICIENT DATA` state, so the caveat is visible before the gate even opens —
  and the `ANALYSIS`-path `note` gets an explicit CAVEAT sentence when thin days are present,
  so a future run (or the edge-hunter) can't miss it once the gate flips.

## Current reading (as of this run, 6/7 days)

```
dt=2026-07-17=31  dt=2026-07-18=15  dt=2026-07-19=6  dt=2026-07-20=7  dt=2026-07-21=9  dt=2026-07-22=23
THIN DAYS (below advisory floor of 10): dt=2026-07-19, dt=2026-07-20, dt=2026-07-21
```

Good news buried in this: the 07-22 recovery (23 captures, up from 9 on 07-21) tracks the
cloud-collector direct-push recovery independently found in PR #161/#162 — the degradation
L117/L127 flagged has NOT continued unabated. 3 of the current 6 days remain thin, but if
`dt=2026-07-23` lands at a healthy rate the eventual 7-day window will be a 4-thin/3-healthy
mix rather than uniformly starved. Whoever runs the live analysis the day the gate opens should
read `thin_days` before trusting the lead-lag/coherence counts at face value — exactly Q36's
lesson, applied pre-emptively this time instead of after the fact.

Not a verdict, no registry change, no bootstrap CI, no P&L claim. Two-agent rule N/A (probe-prep
infra, same posture as the 07-20/07-21 Q43 prep runs).

## Gates

`pytest`: full suite green (including all 18 `test_q43_perp_binary_consistency_probe.py`
cases, +3 new) except the same 5 pre-existing `test_invariants.py` failures as base `main`
(byte-identical, confirmed via stash-compare) — issue #157. Local gate verification required
working around the pre-existing `cryptography`/`_cffi_backend` collection panic on
`tests/test_polymarket_us_live.py`/`tests/test_ws_depth.py` via
`pip install --upgrade --ignore-installed cryptography cffi websocket-client` (sandbox-only,
not part of this diff — same workaround PR #162 used).
`python scripts/invariants.py --full`: exit 2, identical 2 violations to `main`'s pre-existing
state (issue #157) — this diff touches neither flagged file.
