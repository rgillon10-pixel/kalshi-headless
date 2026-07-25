# Q19 FOMC burst-capture pre-flight (2026-07-25, research loop, idle-run policy b)

## Why this run

Full queue re-scan re-confirmed 0 eligible TODO/IN-PROGRESS items (Q19 FOMC gate opens
2026-07-29, still 4 days out; Q36/Q37/Q42-pt3/Q43/Q47 remain density/calendar/credential-gated;
Q1-odds/Q32/Q33/Q35-build stay credential-blocked) and the lessons ledger's `**UNENFORCED**`
backlog is empty (L163, this morning's earlier idle run, closed the last open row) — idle-run
policy (a) is exhausted this round. The prior run (PR #195) explicitly flagged a concrete,
actionable gap for "whoever picks up" Q19's FOMC leg: *"2 of 3 prior burst-capture windows (WC
semi-1, WC final) fired but committed no data — worth a pre-flight check before Jul 29."* This
run is that pre-flight check, per idle-run policy (b) (prep for the next time-gated item).

## What was verified live

`kalshi-burst-fomc-0729` (`trig_01L9RysFtWUUjj3BgQmNKw7g`), read via `list_triggers`:
`enabled: true`, `cron_expression: "40 17 29 7 *"`, `next_run_at: 2026-07-29T17:40:00Z` — the
trigger is correctly configured and has not fired yet. Its prompt already carries the
2026-07-15 mandatory-push-verification hardening (confirmed by reading the stored `job_config`
message body directly, not assumed).

## The documented failure history (facts, from `kb/00-LOG.md`/`LOOP-QUEUE.md`, not new claims)

- **`kalshi-burst-wcsemi1-0714`** (2026-07-14 20:10→22:30Z): fired, captured 144 snapshots,
  never committed — lost to a dead sandbox mid-run (`kb/00-LOG.md` 2026-07-14 entry).
- **Fix applied 2026-07-15 (Ryan-hardened, per `kb/00-LOG.md`'s own words: "already
  Ryan-hardened ... that's handled")**: mandatory push-verification added to the three
  remaining one-shots (`wcsemi2-0715`, `wcfinal-0719`, `fomc-0729`).
- **`kalshi-burst-wcsemi2-0715`** (the very next window, same day as the fix): succeeded — real
  burst tape exists (`tape/polymarket_pairs/dt=2026-07-15.jsonl`, 30 captures), analyzed in
  `findings/2026-07-16-s17-burst-wcsemi2-q19.md`.
- **`kalshi-burst-wcfinal-0719`**: fired (`last_fired_at` set per the trigger API, `enabled:
  true`), yet **still** produced zero committed tape — no `tape/polymarket_pairs/
  dt=2026-07-19.jsonl` on `main`, no `tape/burst-*` branch carries it (`LOOP-QUEUE.md` Q19
  status, dated 2026-07-19/2026-07-20). This is AFTER the push-verification hardening, so
  whatever the push-verification step is meant to catch was not the (whole) problem here.

Net: 1 of 3 fired one-shots definitely lost its data to a mid-run sandbox death; a fix targeting
exactly that failure mode did not prevent the SECOND loss. FOMC is the fourth and by far the
highest-stakes window — S17's kill/live decision is gated on it (`LOOP-QUEUE.md` Q19).

## Two structural gaps (stated as hypotheses — no direct evidence, e.g. a captured stderr or
session log, distinguishes them; both are real properties of the CURRENT mechanism regardless
of which one actually explains `wcfinal`)

1. **Single commit gates the whole window.** `collection/burst_capture.py::run_burst` calls each
   family's existing `run()` once per tick, and — per its own module docstring — "writes NO tape
   of its own"; each `run()` call writes its own tape line to LOCAL DISK immediately. The trigger
   prompt's step 4 (git commit) only fires once, after the ENTIRE loop returns (`Let it run to
   completion — do not kill it early`). If the triggered sandbox is torn down at any point before
   that return — a timeout, a resource reclaim, a disconnect — every tick's already-written-to-
   disk data is lost with it, uncommitted. Push-verification (step 5) only helps once step 4 is
   reached; it does nothing for a run that never gets there.
2. **"Started late" and "died mid-run" currently look identical from outside.** If a triggered
   session's actual start is delayed past its scheduled cron time (documented cloud-session
   scheduling drift elsewhere in this repo, e.g. PR #195's "cloud collector's dropped 09:00/12:00
   UTC slots"), `run_burst`'s own `window_already_past` branch would correctly exit 0 with 0
   ticks and genuinely nothing to commit — a well-behaved, silent, zero-data outcome
   indistinguishable after the fact from a mid-run crash. Neither the trigger prompt nor
   `burst_capture.py` currently logs the scheduled-vs-actual start delay anywhere that would
   survive a lost sandbox.

Both gaps point at the same fix: shrink the unit of work between "capture" and "commit" from one
~125-160-minute window to several ~20-minute chunks.

## What this run built (no verdict, no registry change, no P&L claim)

- `scripts/burst_chunk_plan.py` (+18 offline tests, `tests/test_burst_chunk_plan.py`) — pure
  arithmetic computing a `--max-ticks` chunk sequence for a given window/interval/chunk-size, so
  the runbook's numbers are a reproducible command output, not hand arithmetic. Regression-pins
  the actual FOMC window: 125 minutes @ 90s interval, 20-minute chunks → 6 chunks of 14 ticks
  each (`[14, 14, 14, 14, 14, 14]`, sums to the 84-tick total).
- `ops/burst_capture_chunked.md` — the recipe: chunk the window via the tool above, run
  `collection.burst_capture --max-ticks N` per chunk, commit+push+verify after EACH chunk
  (reusing the existing mandatory-push-verification step, now applied per-chunk instead of once),
  and report how many of N chunks actually landed in the final message and phone note (rather
  than a bare pass/fail that would have hidden exactly what happened on 07-14 and 07-19). Includes
  the literal recommended replacement text for `kalshi-burst-fomc-0729`'s step 3.
- **No source change to `collection/burst_capture.py`** — it already supports `--max-ticks`
  per-invocation; the fix is entirely in HOW the trigger orchestrates repeated invocations of the
  existing, already-tested tool.

## Deliberately NOT done this run

The live `kalshi-burst-fomc-0729` trigger was **not** modified. Per the 2026-07-15 precedent —
that one-shot's own hardening was applied by Ryan, not an autonomous run — editing a live
account-level trigger's prompt is treated as Ryan's call, not a cloud research loop's, even
though the mitigation itself is fully designed, computed, and offline-tested. **Action needed
from Ryan (or a Ryan-supervised session) before 2026-07-29 17:40Z**: apply the replacement text
in `ops/burst_capture_chunked.md` via `update_trigger` on `trig_01L9RysFtWUUjj3BgQmNKw7g`, or
decide the existing single-shot recipe is an acceptable risk for this window and do nothing.

## Two-agent verdict rule

N/A — no registry flip, no bootstrap CI, no kill decision. This is ops/infra hardening plus a
diagnostic writeup of already-documented facts (the two failure hypotheses are explicitly
labeled as such, not asserted as confirmed), same posture as the L109/L118/L126/L144/L150/
L152/L156/L157/L160/L161/L163 precedent.

## Gates

- `pytest -q`: green (18 new tests, 0 failed) — see the run's final commit message for the
  exact post-edit count (L162/L163 fresh-gate-line rule).
- `python scripts/invariants.py --full`: exit 0, same pre-existing non-gating advisory classes
  as `main` before this run.
