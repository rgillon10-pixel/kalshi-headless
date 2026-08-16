# `settlement_ledger` has been structurally unable to fire since 2026-07-22 — its gate hour is not on the collector's realized grid

**Run:** kalshi-research-loop, 2026-08-15, **IDLE RUN** (idle-run policy (c): data-quality
deep-dive on one tape family producing one finding, with the (a)-class enforcement attached).
**Class:** data-quality / tooling. **NOT verdict-class** — no registry flip, no bootstrap CI,
no P&L, no kill decision, no price quoted anywhere in this document. Still **0 proven edges**.
**Two-agent status: CONFIRMED (2026-08-16, kalshi-edge-hunter — see §8).** The producing
research-loop run had no `Task`/subagent tool and committed PROVISIONAL with the sanctioned
redundancy fallback (§6). The next night's edge-hunter DID carry an independent `Agent`-tool
`verifier`, which re-derived every §2/§3 number from scratch on an independent code path and
returned CONFIRMED — the two-agent pass this finding explicitly owed is now closed.

## 0. Why this run went here

The queue is drained: every item Q0–Q56 reads DONE / DEAD / BLOCKED / RESERVED / credential- or
burst-gated at its **newest-dated** `Status:` line (the topmost-line reading rule is not uniform —
Q24 and Q53 append newest at the BOTTOM and both are closed; Q54 says so explicitly in its own
status). That makes this an IDLE RUN. Policy (a) was checked first and is genuinely thin:
`scripts/invariants.py::stale_unenforced_recall_report()` reports 10 open `**UNENFORCED**` rows
plus 4 mixed-tier, and per-row triage puts every one of them in "collector write-path, Ryan-lane"
(L168, L213, L221, L222, L270, L282, L286) or "declares itself unmechanizable" (L27, L28, L32,
L318, L338, L346) or "already has its buildable half built" (L319, L320, L321, L323, L288).

Policy (c) then pointed straight at the thing the nightly thinking seat had just measured.
`findings/2026-08-14-q21-round30-idea-gen.md` killed all 3 of that round's candidates on
adequacy and named the binding constraint: `tape/universe_sweep/` — the largest, freshest,
most-diversified tape we hold — has a broker-truth-settleable footprint of **one snapshot-day /
209 events / 3 series**, "not because of the sweep but because the broad settlement family
(`settlement_ledger`, Q45) stopped producing after 07-22." It named the symptom. This run found
the cause, and the cause is one integer in one line of the collector.

## 1. The defect

`collection/hourly_pass.py`:

```
SETTLEMENT_LEDGER_UTC_HOUR = 10
...
    if ts.hour == SETTLEMENT_LEDGER_UTC_HOUR:
        settlement = _safe_call(sl_fn)
```

`ts` is the pass START instant (`ts = now if now is not None else datetime.now(timezone.utc)`,
first line of `run()`). The live `kalshi-collector` starts its passes at **~:54 past the hour on
a 3-hourly grid**, so `ts.hour` is never 10 — and the leg is not slow, or erroring, or
rate-limited. It simply never executes.

## 2. The measurement (read-only, committed tape, frozen slice)

Realized pass-START hours are not readable from this repo — the schedule lives in Ryan's cloud
trigger and the VPS crontab — so they are **measured** from the pass instants of an ungated leg.
Frozen slice `dt=2026-07-26 .. dt=2026-08-14` (20 committed day-files, past days only, L191):

| witness leg | position in `hourly_pass.run()` | pass-starts | at 10Z | at 09Z | at 12Z |
|---|---|---|---|---|---|
| `sports_pairs` | leg #1 (ungated, runs first) | **103** | **0** | 13 | 12 |
| `crypto_hourly` | leg #2 (ungated) | 127 | **0** | 13 | 12 |
| `perp_tape` | leg #7 (ungated, minutes later) | 74 | **11** | 1 | 0 |

Rule-of-three upper bound on the per-pass probability of a 10Z start, given 0/103: **≤ 0.029**.

The corroborator's larger count is worth reading carefully: `crypto_hourly` shows 127 pass
instants against `sports_pairs`'s 103 on the identical slice, because `collection/burst_capture.py`
can also write it (family `crypto`). Those extra passes could only ADD hours — and 10Z is still
**0** — so the second witness strengthens the conclusion rather than diluting it. That is the
same one-directional bias the check documents in general: a witness written by a
non-`hourly_pass` caller can never manufacture an UNREACHABLE verdict, only suppress one.

**The witness choice is load-bearing, not cosmetic.** A pass that starts at 09:54Z reaches leg #7
at ~10:04Z, so `perp_tape`'s instants sit one clock hour later and cluster on
{1,4,7,10,13,16,19,22} — reading reachability off a late leg **inverts the verdict** and would
have concluded "10Z fires 11 times, the gate is fine." That inversion is pinned as a test
(`tests/test_tape_gap_monitor.py::test_acceptance_a_late_leg_witness_would_invert_the_verdict_on_the_real_tree`)
and re-derived independently (§6).

**The era caveat is stated, not hidden.** Over ALL committed history `sports_pairs` has 716
pass-starts with **25 at 10Z** — the collector ran ~20 pass-hours/day through 2026-07-22 and ~4/day
after. A whole-history reading therefore answers a question about a schedule that no longer runs.
Every verdict carries `window_sensitivity` beside it; for 10Z it reads: 14d UNREACHABLE (0/67),
21d UNREACHABLE (0/105), 28d REACHABLE (1/171), all-history REACHABLE (25/716). The flip between
21 and 28 days IS the era boundary, reported rather than smoothed away.

## 3. The consequence, and the control that proves it is the hour

`tape/settlement_ledger/` holds exactly **2 day-files: `dt=2026-07-17` (5,605 lines) and
`dt=2026-07-22` (5,000 lines) — 10,605 lines total**, and nothing since. As of the newest
committed tape day (2026-08-15) that is **24 calendar days frozen**. Both surviving captures
land in the dense era (their own capture stamps are 12Z and 10Z), i.e. the family last grew on a
day when 10Z was still reachable.

The control matters more than the symptom: three sibling legs gated at **09Z**
(`anomalies`, `econ_prints`, `polymarket_cpi_pairs`) and one at **12Z** (`weather_actuals`) are
on the realized grid and kept producing through 2026-08-13 / 2026-08-12. The collector is not
dead — it is alive and simply never in hour 10. A missing-day check cannot tell those two
situations apart, which is exactly why this class stayed invisible for 24 days.

Downstream cost, cited not re-derived (round #30's `verifier` did the 1,003,235-ticker
resolution; this run only sanity-checks the bound — a settlement family holding 2 day-files
cannot join more than 2 days): `universe_sweep` spans 26 committed days and ~20k markets/pass,
and its broker-truth-settleable footprint is **373 tickers → 209 events → 3 series, all on the
single day `dt=2026-07-22`**, which is the `settlement_ledger` freeze date. Q21 round #30's
three candidates (S82/S83/S84) all died on adequacy against that footprint.

## 4. This was predicted, and the predicted repair already exists

**L123 (2026-07-21)** named this exact mechanism a month ago — "`collection/hourly_pass.py` gates
`settlement_ledger` at `SETTLEMENT_LEDGER_UTC_HOUR=10` ... the live `kalshi-collector` routine
runs `cron: 53 */3 * * *` ... and so NEVER runs at hour 10 or 11". Its candidate (a) (detection:
register the family in `tape_gap_monitor`'s STALE check, L124; the structural registration
meta-guard, L144) was built. Its **candidate (b) — widening the gate — was explicitly ruled
Ryan/VPS-side** ("changing live-leg firing gates unattended exceeds the additive-collector
self-merge precedent"), and **L221/L246** record that the fix is ALREADY WRITTEN: open draft
**PR #165**'s `daily_leg_due()`, wired at all five gate sites with a bounded
`DAILY_CATCHUP_HOURS=6` window and 71 tests, pending Ryan's review — and that a second
implementation was written and reverted before commit rather than duplicated.

**This run therefore did NOT touch `collection/hourly_pass.py`.** No gate change, no constant
change, no third `daily_leg_due()`. What was missing was never the fix; it was a mechanical way
to see that the gate is unreachable and to keep saying so until someone clears it.

## 5. What was built (detection only)

1. `scripts/tape_gap_monitor.py::gate_hour_reachability(...)` — five distinct verdicts, never a
   boolean: `REACHABLE` / `UNREACHABLE` / `INSUFFICIENT_EVIDENCE` (below a 20-pass evidence
   floor) / `WITNESS_DISAGREEMENT` (two witnesses disagree — reported, never resolved by picking
   a favourite) / `NO_WITNESS_TAPE`. Reuses `pass_instants()` rather than re-reading tape, and
   every report carries `coverage_note`, `window_sensitivity` and `full_history_observed_hours`.
   Residual bias is stated and one-directional: a witness written by some caller other than
   `hourly_pass` can only ADD hours, so the check **under-reports** — it cannot manufacture an
   alarm. CLI: `python3 scripts/tape_gap_monitor.py --gate-reachability 10`.
2. `scripts/invariants.py::_gate_hour_unreachable_issues` / `gate_hour_unreachable_warning`
   (+ `_exempt_gate_hour_unreachable_notes`), wired into `--full` as a **non-gating** stderr
   advisory (same posture as L74/L117/L144/L221: a condition only Ryan can clear must not halt
   the research loop). Gate hours are read via the existing `_single_hour_leg_gate_hours()`, so
   the number is never re-declared and cannot desync from the collector. On today's tree it
   fires on exactly one family, `settlement_ledger`, and reports the exempt
   `FORECAST_COLLECTOR_UTC_HOUR = 11Z` leg beside it (also off-grid; it writes gitignored
   `data/forecast_tape/`, so it is labelled exempt rather than silently dropped — dropping it is
   how L123's forecast half stayed invisible).
3. `scripts/collector_gate_reachability_audit.py` → `reports/collector_gate_reachability.json`
   (the per-leg table, `collector_gate_reachability.v1`).
4. `scripts/collector_gate_reachability_rederive.py` — the redundancy leg (§6).
5. Tests: 18 in `tests/test_tape_gap_monitor.py`, 9 in `tests/test_invariants.py`, 15 in
   `tests/test_collector_gate_reachability_rederive.py`, 6 in
   `tests/test_collector_gate_reachability_audit.py`. Real-tree acceptance tests run on the
   FROZEN past-day slice so ordinary tape growth cannot move them; if one goes red the world
   changed (the collector started firing at 10Z, or stopped at 09Z/12Z) and this finding is
   genuinely superseded — the intended loud signal, not a flake (L341).

## 6. Redundancy, NOT verification

`scripts/collector_gate_reachability_rederive.py` shares no code with the primary: its own
`json.loads` line reader (vs the primary's streaming regex scan), its own ISO-8601 parser by
string slicing (pinned against `core.timeutil.parse_iso_utc` on 500 real committed timestamps,
so the agreement is not two implementations sharing one parser), its own earliest-per-`capture_id`
fold, its own day-window selection, its own histogram, its own gate-constant regex.

It reproduces **every** load-bearing number exactly: 103 / 127 / 74 pass-starts, 0 / 0 / 11 at
10Z, 13 at 09Z, 12 at 12Z, the identical full hour histograms, all five gate verdicts, and
`settlement_ledger` = 2 days / 5,605 + 5,000 = 10,605 lines / last day 2026-07-22 / 24 days
frozen. It cannot catch an error both implementations share and is not claimed to. **An
independent `verifier` pass is still owed before any of this is treated as confirmed.**

## 7. Disposition and the ask

- **Nothing in the registry moves.** `kb/strategies/00-index.md` untouched; no strategy status,
  no CI, no P&L, no kill. Q45's own verdict is unchanged (still DONE); this appends a
  data-quality status line, not a new verdict.
- **The ask for Ryan, sharpened from round #30's:** it is no longer "someone should fix a
  settlement collector." It is **"merge or reject open PR #165"** — the one-line consequence of
  leaving it open is that the project's largest tape family has been un-backtestable for
  settlement-direction edges for 24 days and counting, and the loop is (correctly) forbidden
  from fixing it itself. A one-off `python -m collection.settlement_ledger` run from the VPS
  should also unfreeze the tape immediately and independently of the PR — and if that run
  FAILS, that failure is itself the next diagnosis, because an unreachable gate hides every
  other defect behind it: a leg that never executes cannot be observed erroring.
- **Owed next:** ~~an independent `verifier` pass over §2/§3 before this leaves PROVISIONAL.~~
  **DONE — see §8.**

## 8. Independent verifier confirmation (2026-08-16, kalshi-edge-hunter, Unit-1 adversarial review)

The nightly edge-hunter's adversarial-review unit dispatched an independent `Agent`-tool
`verifier` (a different session/model instance from the producer) tasked to REFUTE §1–§4. It
re-implemented the reachability histogram from raw tape on its own path — its own `json.loads`
line reader, its own string-slice ISO-hour parser, its own earliest-per-`capture_id` fold — not
by running this finding's scripts. **Verdict: CONFIRMED.** Every load-bearing number reproduces
exactly:

- **§1 mechanism** — `SETTLEMENT_LEDGER_UTC_HOUR = 10` (L150), gated `if ts.hour == …` (L561)
  where `ts` is the pass-START instant (L365). Reads exactly as claimed.
- **§2 histograms** (frozen slice dt=2026-07-26..2026-08-14): `sports_pairs` 103 / **0**@10Z /
  13@09Z / 12@12Z; `crypto_hourly` 127 / **0**@10Z / 13 / 12; `perp_tape` (late leg) 74 /
  **11**@10Z. Independently identical. The load-bearing inversion holds (early-leg witness 0/103;
  late-leg witness would spuriously read 11@10Z and flip the verdict).
- **§3 consequence** — `settlement_ledger` = exactly 2 files, 5,605 + 5,000 = 10,605 lines, frozen
  since dt=2026-07-22, 24 calendar days behind the newest committed tape day dt=2026-08-15.
- **§4 control** — 09Z/12Z sibling legs alive into August, settlement_ledger frozen. Verifier
  caveat (strengthens, not weakens): those siblings actually have files through **dt=2026-08-15**
  (weather_actuals through 08-12), fresher than the conservative 08-13/08-12 stated above — so
  "the collector is alive, only hour 10 is dead" is if anything understated here.

No price/fee/bootstrap issues apply (this finding quotes none; the verifier confirmed no registry
flip and no price anywhere). The Ryan-side ask in §7 (merge or reject open PR #165 — the written
`daily_leg_due()` fix) is unchanged and now independently corroborated; it was already surfaced
to the phone feed on 2026-08-15, so it is NOT re-flagged today (no new decision, only confirmation).
