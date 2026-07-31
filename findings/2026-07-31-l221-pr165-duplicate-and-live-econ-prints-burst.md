# 2026-07-31 ~22:2xZ — L221's fix duplicates open PR #165; a live-caught econ_prints burst

**Two-agent rule:** N/A. No registry change, no bootstrap CI, no P&L, no kill decision.
This is a process finding (claim-check discipline) and a data-quality observation.

## 1. L221 is already fixed, in an open PR this repo has been walking past for 8 days

`kb/lessons/00-lessons.md` L221 names a defect in `collection/hourly_pass.py`: the
`if ts.hour == ECON_PRINTS_UTC_HOUR:` gate is a rate gate, not an idempotence gate — it
re-fires unboundedly inside its hour (measured 54.4% byte-redundant re-capture,
`findings/2026-07-29-econ-prints-tape-audit.md` D2) and never fires again if the routine
misses its hour entirely (5 fully-lost calendar days, D3).

This run's `invariants._stale_unenforced_scan()` query found L221 as the sole genuinely
open (not `DISPOSES:`-superseded) `**UNENFORCED**` lesson row. Before building anything,
the immediately preceding same-day run's `kb/00-LOG.md` entry (`~09:2x UTC`) was re-read;
it says:

> L221's candidate (a once-per-day dedup key replacing `hourly_pass.py`'s bare
> `ts.hour == N` gate) substantially overlaps the unmerged, open, Ryan-review-only PR
> #165's `daily_leg_due()` catch-up-gate design — building a second, competing
> implementation risked real merge conflict with Ryan's own pending review, so this run
> did not attempt it.

That entry names the risk but does not quote PR #165's content. This run built the fix
anyway (`_leg_captured_today()`/`_daily_leg_due()`, wired to the `econ_prints` gate only,
15 new tests, full suite green: 2457 passed / 0 failed / 2221.08s, `invariants --full`
green) and only THEN fetched PR #165 in full before committing — the step that should have
happened first.

**PR #165** (`worktree-data-stream-hardening`, created 2026-07-23, draft, title
"Data-stream hardening: daily-leg catch-up gates, scheduled gap monitor, DATA-MAP") adds:

```python
def daily_leg_due(ts: datetime, scheduled_hour: int, family: str,
                  tape_root: Optional[Path] = None) -> bool:
    """True when a once-per-UTC-day leg should run this pass: on its scheduled hour, or
    within the catch-up window after it while today's `tape/<family>/dt=<today>.jsonl`
    is still absent."""
```

wired at the exact five gate sites this repo has: `anomalies`, `econ_prints`,
`polymarket_cpi_pairs`, `weather_actuals`, `settlement_ledger` — a strict superset of the
one leg (`econ_prints`) this run's independent version covered — with a bounded
`DAILY_CATCHUP_HOURS = 6` window (this run's version had none), its own 71-test suite in
`test_hourly_pass.py`, plus a `DATA-MAP.md` generator (`scripts/gen_data_map.py`) and a VPS
ops-script change scheduling `tape_gap_monitor.py` daily. PR #165's own body states it is
"the root-cause fix for L123/L124" — the exact lesson-row family L221 belongs to.

**Verdict: not an overlap, a duplicate.** This run's code was reverted before commit
(`git checkout -- collection/hourly_pass.py tests/test_hourly_pass.py`; `git diff` on both
files is empty against `origin/main`). Nothing from this attempt ships.

**Why the title didn't help.** "Data-stream hardening... DATA-MAP" gives no lexical hint
that the PR resolves L221 or fixes the hour-equality-gate defect — only the PR body says
so. Claim-check (LOOP-QUEUE.md step 0) as practiced by prior runs reads PR titles, not
diffs or bodies, when triaging the standing 5-PR backlog (#208/#191/#166/#165/#125) as
"stale, Ryan-review-only, none claims work" — true for 4 of the 5, false for #165 the
moment a queue/lesson item's own candidate matches its content. New lesson: **L246**
(`kb/lessons/00-lessons.md`).

**Flagged for Ryan, not acted on here:** PR #165 has been open, green (per its own PR
description — "all green locally"), and directly answering an open lesson row for 8 days.
Whether to merge it (even in draft state) is a decision this run's lane does not make
unilaterally — draft + "Ryan-review-only" is itself the signal a research-loop run
respects, per the same convention ~15 prior runs have followed for this exact PR.

## 2. A live-caught instance of the econ_prints "unknown caller" pattern

While reverting the code above, `git status` showed `tape/econ_prints/dt=2026-07-31.jsonl`
had grown by 420 lines in the working tree during this session — data this session's own
tool calls did not write (verified: every pytest suite run this session is fully offline
per `tests/test_hourly_pass.py`/`tests/test_econ_prints.py`'s own docstrings and injected
fakes/`tmp_path` tape dirs; `grep -rl "econ_prints.run" tests/ scripts/` outside those two
files returns nothing).

Integrity checked before treating it as real, not assumed:

- 425/425 lines (5 pre-existing + 420 new) parse as valid JSON.
- 425/425 unique `(capture_id, series_key)` pairs — 0 duplicates.
- `git diff --stat` shows pure insertions, 0 deletions — a clean append.

Breakdown by `capture_id`:

- **1** legitimate pass, `20260731T100535Z` (hour 10, one hour past
  `ECON_PRINTS_UTC_HOUR=9` — itself a minor observation, not chased further this run).
- **84** additional passes, `20260731T213625Z` through `20260731T214914Z` — a continuous
  ~13-minute window, 5 lines each (exactly `econ_prints.run()`'s own per-pass shape),
  inter-pass gaps of 3-12 seconds.

**No other tape family shows any activity in this window** — `git status` lists only this
one file as touched for the whole session. This rules out a genuine
`collection.hourly_pass.run()` invocation as the source (that entry point always writes
`sports_pairs`/`crypto_hourly`/etc. alongside `econ_prints`); whatever produced these 84
calls invoked `collection.econ_prints.run()` (or an equally narrow entry point) directly.

This extends the same-day `~09:2x UTC` run's finding
(`findings/2026-07-31-econ-prints-anomalies-unexplained-passes-provenance.md`) — "agent-
session side effects, not a rogue scheduler" — with the first LIVE-caught episode (by its
footprint, during the same session as the investigation) rather than a post-hoc
commit-diff reconstruction, and narrows the mechanism: single-family, tight-loop,
`econ_prints`-only invocation, not a competing `hourly_pass` scheduler.

The tape itself is committed as real, honest, `real_ask`-tagged (where applicable) data —
this run's idle-run policy (c) data-quality-deep-dive unit of work.

## Gates

No `.py` file differs from `origin/main` in this run's final diff (`collection/hourly_pass.py`
and `tests/test_hourly_pass.py` were built, tested green, then reverted). `python3
scripts/invariants.py --full` re-run fresh against this run's final tree: exit 0, all
green, only pre-existing non-gating advisory classes. `origin/main`'s own last gate (PR
#255): pytest exit 0 / 2442 collected / 0 failed; `invariants --full` exit 0 — unchanged by
this run since no code moved.
