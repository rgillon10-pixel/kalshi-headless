# Q52 — the per-day-file push wedge: measured, gated, and guarded

`2026-08-11` · research loop, protocol v3 · **verdict class: TOOLING + REPOSITORY-HEALTH
MEASUREMENT — no strategy claim, no bootstrap CI, no registry flip.** Two-agent rule **N/A**
by the Q33/Q44/Q45/Q46/L287/L288/L290/L291/L295/L308/L313 precedent (collector-guard and
invariant work, not a verdict). Still 0 proven edges.

Queue item: **Q52** — its own current Status line (2026-08-09, phase-2 backfill) ended with an
explicitly deferred sub-item: *"a day-file-size guard belongs in the script itself before the
next phase, flagged for the next run, not built here."* This run built it, and found that the
exposure is materially larger than the one script.

## 1. The mechanism

GitHub rejects a push at its pre-receive hook if **any** blob in **any** commit being pushed
exceeds **100,000,000 bytes** (decimal, not MiB). This repo commits its tape, tape day-files
are append-only, so every day-file grows monotonically toward that ceiling and never shrinks.
Three properties turn that into a *wedge* rather than a nuisance:

1. the rejection is per-**push**, not per-file — one oversized blob blocks every unrelated
   bookkeeping/findings change riding in the same push;
2. once the blob is in a commit, the branch is permanently unpushable short of a history
   rewrite — which is exactly the max-priority incident LOOP-QUEUE step 0a exists to catch;
3. the hourly collector falls back to a `tape/hourly-*` branch when its push fails, and step
   0b recovers those by **union-appending** the missing lines into `main`'s day-files —
   recreating the same oversized file. A wedged day-file strands tape in a way the standing
   recovery procedure cannot repair.

It has already bitten once. On 2026-08-09 the Q52 phase-2 trade-print backfill measured
`tape/kalshi_trades/dt=2026-07-07.jsonl` at **109,151,185 bytes**, had its push rejected
outright, and dropped one whole game (`KXWCGAME-26JUL07ARGEGY`, 35,144 lines) by hand before
it could commit. Nothing in the repo was watching for the next one.

## 2. Measured exposure (committed tree at `b06f36e`, 2026-08-11)

`python3 scripts/push_size_limit_audit.py` → `reports/push_size_limit_audit.json`.
All figures are **file byte sizes** — no price is involved, so no `price_source_tag` applies
to §2; the tape those files hold is separately tagged at capture time and is untouched here.

| tracked file | bytes | headroom to the 100,000,000 block | append paths |
|---|---|---|---|
| `tape/universe_sweep/dt=2026-07-22.jsonl` | 90,470,557 | 9,529,443 | collector, step0b_sweep |
| `tape/universe_sweep/dt=2026-07-18.jsonl` | 88,177,721 | 11,822,279 | collector, step0b_sweep |
| `tape/kalshi_trades/dt=2026-07-07.jsonl` | 88,069,420 | 11,930,580 | q52_backfill, step0b_sweep |
| `tape/universe_sweep/dt=2026-07-21.jsonl` | 72,537,877 | 27,462,123 | collector, step0b_sweep |
| `tape/universe_sweep/dt=2026-07-20.jsonl` | 54,386,963 | 45,613,037 | collector, step0b_sweep |
| `tape/universe_sweep/dt=2026-07-17.jsonl` | 53,104,187 | 46,895,813 | collector, step0b_sweep |
| `tape/universe_sweep/dt=2026-08-07.jsonl` | 52,776,365 | 47,223,635 | collector, step0b_sweep |

14,507 tracked files / 2.044 GB total. **7 files** at or over GitHub's documented 50,000,000-byte
warn threshold, **0** at or over this repo's new 95,000,000-byte gate, **0** over the hard block.

Two readings the table makes precise:

* **`universe_sweep` is the larger standing exposure, and it is not the family anyone was
  watching.** It holds the three largest files in the repo, it is actively written (last day
  2026-08-11), and its recent days still run 17–53 MB — so a single busy day at ~2x the
  2026-07-22 level crosses the block on a file nobody has to touch deliberately. It is also
  **absent from `scripts/tape_gap_monitor.py::FAMILY_CONFIG`**, the same unregistered-family
  shape as L123/L126/L139. That is why the audit derives "actively written" by MEASURING each
  family's newest committed day rather than reading the registry: a registry-driven check
  would have reported the biggest exposure in the repo as having no collector append path at
  all. (Registering `universe_sweep` in `FAMILY_CONFIG` is a separate, unclaimed unit of work —
  named here, deliberately not done in this milestone.)
* **`kalshi_trades/dt=2026-07-07.jsonl` is effectively closed to the Q52 backfill.**
  See §4.

## 3. What was built

1. **`core/push_limits.py`** — the single sanctioned site for the thresholds
   (`GITHUB_MAX_FILE_BYTES = 100_000_000`, `PUSH_SIZE_GATE_BYTES = 95_000_000`,
   `PUSH_SIZE_WARN_BYTES = 50_000_000`), the same posture as `core/pricing.py` for fee rates:
   hand-rolling the number elsewhere is the bug. The gate sits 5,000,000 below the host block
   deliberately, so a run that trips it still has room to land the repair commit.
2. **`scripts/invariants.py::push_size_gate_failure`** — **GATING**. Unlike most checks in that
   file (which are advisories), this one flips the exit code, because the failure is cheap and
   unambiguous to detect, strictly *worse* if the run proceeds (every further append moves the
   file past the point of no return), and repairable by the same cloud run that trips it.
   Tracked-scoped: an untracked mid-write collector file cannot wedge a push. It degrades to a
   no-op where `git` is unavailable — a gating check may never invent a violation for an
   environment reason. Paired with a **non-gating** warn-band advisory at 50,000,000 that
   deliberately excludes anything the gate already owns (no double-reporting one file as both).
   The `scripts/invariants.py` copy of the three constants is a mirror (that file keeps zero
   import-time dependency on the package, as with `VALID_SOURCE_TAGS`); a test pins the mirror
   equal to `core/push_limits.py`, so drift is a test failure, not a second source of truth.
3. **`scripts/push_size_limit_audit.py`** — read-only, offline measurement tool producing the
   table above plus per-family day profiles and, for each near-limit file, **which named append
   path targets it** (collector / step-0b sweep / Q52 backfill).
4. **`scripts/q52_q54_trades_backfill_phase1.py`** — the guard Q52 asked for. The pre-existing
   `--cap-mb` is a **family-total budget**; the new `--day-file-cap-bytes` is a **per-file
   push-wedge guard**, and the 2026-08-09 incident is exactly the case where the first is
   satisfied and the second is violated. It is:
   * **preventive** — before starting a game, project each target `dt=<day>.jsonl` and skip
     the game if the projection breaches. A skip does **not** stop the pass (the ordering is
     league round-robin, so the blocked day's games are interleaved with reachable ones);
     every skip is counted and named in `skipped_day_file_cap`.
   * **pessimistic before it is informed** — with no measurement yet, it uses
     `BOOTSTRAP_BYTES_PER_TICKER_DAY = 25,000,000`, deliberately above the heaviest ticker-day
     measured on committed tape (16,645,764). After a game lands it switches to the **max**
     realized bytes-per-ticker-day of the pass, never the mean: one heavy game is the case the
     guard exists to stop.
   * **post-checked against measured bytes** — a projection can be wrong, and being wrong in
     the unsafe direction *is* the 2026-08-09 failure. If a day-file is over the ceiling after
     a game lands, the pass stops and **names the whole game to drop** (whole-game atomicity,
     L315) instead of leaving it to be discovered at `git push`.
   * **non-destructive** — it never deletes, truncates or reorders tape. The remediation is
     reported, never performed; a test pins that no file shrinks.

## 4. The consequence for Q52's next phase (this is a planning result, not a verdict)

Re-derive with `python3 scripts/q52_q54_trades_backfill_phase1.py --dry-run --json -`
(offline, no network; `day_file_guard_preview`).

The remaining planned population is **328 games / 1,430 ticker-days**. **169 of those 328
games (51.5%) touch `dt=2026-07-07`** — the file already at 88,069,420 bytes with 11,930,580
of headroom. Sensitivity across estimator choices, all against the same 95,000,000 gate:

| bytes-per-ticker-day estimate | source | games skipped | blocked day |
|---|---|---|---|
| 25,000,000 | guard bootstrap | 169 / 328 | 2026-07-07 |
| 16,645,764 | realized **max** on that day | 169 / 328 | 2026-07-07 |
| 9,422,469 | realized **p90** | 169 / 328 | 2026-07-07 |
| 2,516,269 | realized **mean** | 40 / 328 | 2026-07-07 |
| 570,619 | realized **median** | 0 / 328 | — |

(The realized figures come from the committed 145,892-line `dt=2026-07-07.jsonl` itself: 35
tickers, 88,069,420 bytes.)

The honest read: **that day-file has room for one or two median-weight games and none of the
heavy ones**, and any estimator at or above the realized p90 refuses every game touching it.
So the effective reachable population for a phase-3 backfill is **159 games, not 328**, unless
`kalshi_trades` shards its 2026-07-07 writes into a new file. This is a much sharper statement
of the "per-cell quota strategy" the 2026-08-09 status asked for than a byte-budget: the binding
constraint is not the total budget, it is one calendar day that half the population lives on.

**No backfill was run this milestone** — the guard is built and measured; executing phase 3 is
Q52's own next unit of work and needs the sharding decision above made first.

## 5. What this does NOT claim

* No P&L, no fill rate, no CI, no edge, no registry change. S78 is unmoved and stays where it
  was; the trade tape this guards is evidence *toward* a binding test, not the test.
* The 100,000,000-byte figure is GitHub's documented limit, cited, not measured here. What IS
  measured here is every tracked file's size on the committed tree and the guard's effect on
  the Q52 selection.
* A clean gate today is not a promise about tomorrow: `universe_sweep`'s next busy day is the
  most likely next trip, and the gate exists precisely so that trip is a red test rather than
  a rejected push.

## Artifacts

`core/push_limits.py` · `scripts/push_size_limit_audit.py` ·
`scripts/invariants.py` (`push_size_gate_failure`, `push_size_warn_warning`) ·
`scripts/q52_q54_trades_backfill_phase1.py` (`day_file_sizes`, `days_of`,
`project_day_file_bytes`, `guard_preview`, `execute(day_file_cap_bytes=...)`) ·
`tests/test_push_size_limit_audit.py` · `tests/test_q52_q54_trades_backfill_phase1.py` ·
`reports/push_size_limit_audit.json`
