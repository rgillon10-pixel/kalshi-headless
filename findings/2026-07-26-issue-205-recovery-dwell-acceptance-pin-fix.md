# Issue #205 fix: `test_recovery_dwell_advisory` acceptance pin loosened (main RED → green)

**Date:** 2026-07-26 (research loop)
**Class:** gate repair, no strategy claim, no registry change. Two-agent verdict rule N/A
(no bootstrap CI, no kill decision, no registry status flip — same posture as L106/L107/
L112/L116/L156/L163's non-gating tooling fixes).

## What was broken

`main` (HEAD `9d8f4ce`, PR #204) was RED on
`tests/test_recovery_dwell_advisory.py::test_acceptance_exactly_one_real_finding_is_recovery_class`,
tracked by issue #205 (opened by the prior nightly `kalshi-edge-hunter` run's adversarial
review). The test pinned the real `findings/` corpus's recovery-class set to a frozen
single-element list, `== ["2026-07-22-vps-collector-recovered-post-pr151.md"]`. PR #203
(merged ~04:0xZ, same night) legitimately added a second recovery-class finding —
`findings/2026-07-26-stranded-tape-recovery-hourly20260725T2157Z.md` — whose headline
correctly matches both `_RECOVERY_TERM_RE` and `_RECOVERY_SUBJECT_RE`. `invariants.py --full`
correctly reports both as a non-gating L157 advisory; only the test's frozen-list acceptance
pin was stale.

## Fix applied (issue #205's option 1 — test-only, not the Ryan-review invariants-matcher option)

Renamed the test to `test_acceptance_recovery_class_findings_are_a_small_headline_scoped_subset`
and replaced the exact-list pin with:
- a membership assertion that the known-defective 2026-07-22 finding is always present (the
  true positive L157 exists because of), and
- a precision-ratio assertion — `0 < len(recovery_class) <= len(body_hits) // 2` — pinning the
  scoping claim the test's own docstring makes (headline-scoped recovery-class findings stay a
  small minority of findings whose body merely mentions "recover") without freezing membership,
  so the next legitimate recovery-class finding (e.g. a future stranded-tape recovery) does not
  re-break this test the way PR #203's did.

Live corpus at fix time: `recovery_class` = 2 (`2026-07-22-vps-collector-recovered-post-pr151.md`,
`2026-07-26-stranded-tape-recovery-hourly20260725T2157Z.md`), `body_hits` = 20, 90 total findings
(`find findings/*.md` + the two matcher regexes from `scripts/invariants.py`, run live this
session). 2 <= 20 // 2 = 10 — ratio holds.

Issue #205's option 2 (refining `scripts/invariants.py`'s matcher to distinguish
collector-recovery from one-shot tape-recovery for L157-dwell-advisory purposes) is a design
call flagged in the issue as Ryan-review — not touched here.

## Gates

- `pytest -q`: **1990 collected** (`--collect-only -q` summed across 86 files, taken after this
  commit's last edit per the L163 fresh-gate-line rule), **2 failed** — both
  `tests/test_q42_funding_estimate_path_inference.py` (real-tape-drift: `n_windows` pinned at 42
  now measures 44 as more forward `perp_tape` has landed; `p11` pinned at 0.205±0.02 now measures
  0.22715). Confirmed **byte-identical on base `main`** via `git stash` (this diff touches only
  `tests/test_recovery_dwell_advisory.py`). The recovery-dwell test itself: 0 failed.
- `python scripts/invariants.py --full`: exit 0, same pre-existing non-gating advisory classes
  (VPS collector leg 84.9h silent, worsening, Ryan-side; 36 raw-`fromisoformat` sites; etc.) —
  the L157 recovery advisory itself still fires (correctly, by design) on both findings.

## Step 0a/0/0b (this run)

- 0a: `origin/main` HEAD `9d8f4ce` (PR #204); `kb/00-LOG.md` newest entry and newest committed
  tape both 2026-07-26 — no rewind.
- 0: open PRs #191/#166/#165/#125 unchanged since the prior run, none claim eligible work.
- 0b: newest remote `tape/hourly-*`/`tape/burst-*` branch is still `tape/hourly-20260726T0356Z`
  (already recovered by PR #204, ~2h before this run) — nothing new to sweep.

## Step 9 (paper sub-pass)

`SHADOW_REGISTRY = {s14_ladder_underwriting}` (`dead ✗` per Q34 — paper-infra validation only,
NOT edge evidence). `paper_pass.py` idempotent this run (0 newly processed — no new tape since
the last pass), ledger unchanged **+$19.56** (`broker_truth`, 1059 settled, 0 open). Still
**0 proven edges**.
