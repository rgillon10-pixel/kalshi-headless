# 2026-07-31 — `econ_prints`/`anomalies` unexplained hour-09 passes: root cause found

Idle-run policy (c) (LOOP-QUEUE.md v3). A full Q0-Q48 rescan (this run, independently) again
found 0 eligible TODO/IN-PROGRESS items, and every open `UNENFORCED` lesson row's buildable
half is already built (L145/L213 are Ryan policy calls; L221/L222's remaining halves change a
live collector's write path or duplicate the in-flight `daily_leg_due()` catch-up-gate work in
open PR #165 — out of this run's lane either way; L227's remaining half is explicitly not
statically assertable). Instead of a fifth read-only tool addition to `tape_gap_monitor.py` in
the same vein as the last several idle runs, this run chased down a specific open question the
immediately preceding run (PR #251, `kb/00-LOG.md` 2026-07-31 ~07:3x UTC) surfaced but did not
resolve: L222's own row calls `econ_prints`/`anomalies` "roughly 65%" and "21.8%" unexplained by
registered-caller co-occurrence, respectively, without saying what actually produced those
passes. Two-agent verdict rule N/A — this is a data-quality/provenance investigation, not a
registry flip, bootstrap CI, or kill decision (same posture as the perp_tape/settlement_ledger/
polymarket_macro_pairs/econ_prints/polymarket_pairs audit precedents).

## The question

`scripts/tape_gap_monitor.py::caller_explicability()` flags a tape pass as "unexplained" when
no registered caller's (`hourly_pass`/`burst_capture`) OTHER sibling legs were written within a
900s tolerance window. Both `tape/econ_prints/` and `tape/anomalies/` are gated to fire only
when `ts.hour == 9` UTC inside `collection/hourly_pass.py` (`ANOMALY_SWEEP_UTC_HOUR = 9`,
`ECON_PRINTS_UTC_HOUR = 9`). Live re-derivation today (after the 2026-07-31 `polymarket_pairs`
audit's `BURST_CAPTURE_CO_WRITTEN_FAMILIES` fix re-credited 5 econ_prints passes to
`burst_capture`):

- `econ_prints`: **52/369 unexplained (14.09%)**, not L222's quoted 57 — that number is now
  stale, superseded by this run's own PR #251 fix, not a new finding.
- `anomalies`: **53/243 unexplained (21.79%)**, unchanged from L222's figure (no burst-family
  co-writes anomalies).
- Both concentrate on `dt=2026-07-20` (14), `dt=2026-07-21` (20), `dt=2026-07-23` (18); the two
  gated legs' unexplained passes coincide on the same days because they share the same
  `ts.hour == 9` gate.

Nobody had asked what *produces* these passes. Grepping the tree, the only code paths that ever
call `collection/econ_prints.py` or `scripts/anomaly_sweep.py` are `hourly_pass.run()` (gated to
hour 9) and `burst_capture.py` — nothing else invokes them programmatically. So either an
unknown scheduler is double-firing, or something is invoking these collectors directly outside
the normal caller set.

## What actually happened

A `tape-auditor` subagent (read-only) diffed the `captured_at` sets each commit under
`git log -- tape/econ_prints/ tape/anomalies/` introduced, cross-referenced against the commit
messages of PRs that touched these two collectors or ran gate checks around hour 09 UTC.
**All 105 unexplained passes (52 + 53) attribute to eight specific commits, all authored by
autonomous agent sessions, none by the VPS collector:**

| commit | UTC time | econ | anom | commit message excerpt |
|---|---|---|---|---|
| `81f3ae11ae` | 2026-07-13 09:48 | – | 1 | `build(Q22): S14 wired as first-ever paper shadow strategy` |
| `add12b5259` | 2026-07-13 09:21 | (part of the 07-13 total) | | `tape: 09Z anomaly sweep + econ_prints capture (live, this run's invariants pass)` |
| `a02ad3ebf2` | 2026-07-13 09:50 | (part of the 07-13 total) | | `tape: final 09Z anomaly/econ_prints capture from this run's last gate check` |
| `e54bbb0015` | 2026-07-20 09:27 | 4 | 4 | `tape: incidental daily-cadence capture, anomalies + econ_prints (2026-07-20)` |
| `94db504378` | 2026-07-20 09:45 | 10 | 10 | `idle-run: Q37 weather summer maker-NO probe-prep` (body: "incidental anomalies/econ_prints capture") |
| `3a6053d6e0` | 2026-07-21 09:39 | 20 | 20 | `tape: hourly pass 2026-07-21T09:23:31Z (hour-9 leg, anomalies+econ_prints)` |
| `3f0a91f3e5` | 2026-07-23 09:40 | 16 | 16 | `tape: hourly pass 2026-07-23T09:37Z (anomalies, econ_prints)` |
| `5799ace36e` | 2026-07-23 09:42 | 2 | 2 | `tape: hourly pass 2026-07-23T09:4x Z (anomalies, econ_prints) delta` |

All eight commit hashes and their author dates/messages were independently re-verified against
this session's own `git log -1` (not taken on the subagent's report alone) — every one exists,
touches the expected files, and its message narrates exactly the mechanism below.

**Root cause: `ts.hour == N` is a rate gate, not an idempotence gate (L221's own framing,
confirmed empirically).** Multiple commit messages narrate the mechanism directly —
`add12b5259`: "Two `invariants.py --full` runs this session ... each triggered the 09-UTC-hour
anomaly_sweep + econ_prints sub-passes as a side effect"; `3a6053d6e0`: "Landed in the
research-loop container's shared working tree during the concurrent hourly-collector's hour==9
pass." Whenever an autonomous session runs `hourly_pass.run()` live — a routine smoke-test
step this repo's own history shows repeatedly (e.g. Q38's build PR ran `weather_actuals --limit
2` against real endpoints and committed the resulting lines directly) — or reruns a gate check
that has the same side effect, and that happens to land during UTC hour 9, the two hour-gated
legs fire again, appending genuine-but-redundant captures that share no timing signature with a
real concurrent `hourly_pass`/`burst_capture` invocation's other legs. This is not a rogue
third scheduler: the minute-of-hour distribution of all 105 passes is a single continuous
09:17-09:45 smear (econ_prints modal 09:32-09:35) with no `:2x`/`:5x` VPS-vs-cloud bimodality
(the L117/Q44 signature is absent) — consistent with one in-process caller per commit, not two
competing cron schedulers.

## Honest limits

- This is git-commit attribution (which commit's diff first introduced a line), not runtime
  process attribution — it proves which session's tree state the line entered on, not which
  exact line of code executed it. The commit messages' own first-person narration is corroborating
  evidence, not independent proof.
- `3a6053d6e0`'s own message describes a *concurrent* real `hourly_pass` invocation whose other
  legs landed elsewhere — so 2026-07-21's 40 passes are consistent with a genuine second
  invocation racing the committing session's own capture, not purely a session side-effect.
  Both mechanisms may be operating; this audit does not have the evidence to fully separate them.
- L222's row cites a 2026-07-14 finding of a 0.153s inter-pass gap (proving ≥2 concurrent
  invocations that day) — 2026-07-14 has **zero** unexplained passes in the current census
  (it was the CPI burst day, fully explicable by `burst_capture` co-occurrence). That earlier
  finding and this one are about different days and do not contradict each other, but neither
  fully explains the other.
- The investigating subagent's local clone was a shallow clone truncated at 50 commits; this
  session's clone is full (791 commits, verified via `git rev-list --count HEAD`), and the
  commit hashes above were independently re-verified against this session's own history, not
  the subagent's truncated one. Flagged as a real hazard for any future run reasoning about
  commit-level provenance from a fresh shallow clone.

## What this does and doesn't close

This is a **post-hoc forensic attribution**, not a new machine-checkable enforcement — it does
not flip L222's `test` marker (no new invariant/test was built this run) and does not close
L221 (the actual fix — a once-per-day dedup key replacing the bare hour-equality gate — remains
UNENFORCED, and substantially overlaps the `daily_leg_due()` catch-up-gate design already
proposed in open PR #165; building a second, competing implementation in this run would create
avoidable merge conflict with Ryan's own pending review, so it is deliberately not attempted
here). What it does close: L222's own stated limit ("this check can prove a pass inexplicable
but never certify one legitimate") no longer needs to stay purely hypothetical for these 105
passes — they are now attributed, not mysterious. L222's enforcement cell is updated with the
corrected 52 (not 57) count and this session's attribution, per the L152 own-row-update rule
(lesson text unchanged, only the enforcement cell moves).

## Gates

`pytest -o addopts='' -q` (fresh full run, taken after this diff's last edit): **2,414 passed,
0 failed, exit 0** (2185.93s / 0:36:25). `python scripts/invariants.py --full`: exit 0, all
green (docs/findings-only diff, unaffected). No network calls beyond the read-only `git
log`/`git show` archaeology above; no orders, no credentials.
