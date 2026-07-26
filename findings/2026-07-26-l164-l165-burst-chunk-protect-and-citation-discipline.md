# L164/L165 enforcement — `--protect` seam guard + citation-discipline house style

Scheduled cloud research-loop run, 2026-07-26 ~00:1xZ, protocol v3, idle-run policy (a).

## Step 0a/0/0b

**PASS.** `origin/main` HEAD `1714dc6` (merged PR #201) fast-forwarded cleanly with no local
divergence. `kb/00-LOG.md`'s newest entry and the newest committed tape file are both dated
2026-07-25 — no rewind.

Step 0 claim-check: open PRs are #191 (draft, dead-shadow invariant, Ryan-review), #166/#165
(draft, Ryan-action storage-migration/data-stream-hardening infra), #125 (leave-open weekly-retro
proposals) — none claim eligible queue work; none touched by this diff.

Step 0b: ran `scripts/tape_branch_sweep.py` (built 2026-07-25, PR #196) fresh against the current
487-branch remote backlog. Zero genuinely-missing lines reported (no `MISSING`/`not fetched`
findings in the output) — the malformed-name triage section lists the same historical branches
PR #196/#197's backlog audit already accounted for, plus this week's newest `tape/hourly-*`
branches, all consistent with already-merged tape. Nothing to append this run.

## Queue re-verified saturated

Re-checked Q0–Q47 directly against their current Status blocks: every item is `DONE`, `GATED`
(calendar/density — Q19 FOMC 4 days out, Q36/Q37/Q42-pt3/Q43/Q47), or `BLOCKED` (credentials —
Q1-odds/Q32/Q33/Q35-build). The 2026-07-25 Q21 idea-gen round (13th consecutive zero-registration
round) is already filed. → **IDLE RUN.**

## The milestone (idle-run policy a)

Re-derived the open `**UNENFORCED**` lesson set in `kb/lessons/00-lessons.md` by whole-word grep
for `\*\*UNENFORCED\*\*`. L163's own row states the backlog was empty as of 2026-07-25's earlier
idle run; the two rows filed AFTER that snapshot in the same day's correction round — **L164**
(chunk-seam protection) and **L165** (citation provenance) — are the only two genuinely open rows.

### L164 — built the named candidate

L164's own text named the candidate: "teach `scripts/burst_chunk_plan.py` an optional `--protect
ISO_INSTANT` argument that adjusts the first chunk's tick count so no boundary falls within one
interval of it." Built exactly that:

- `first_chunk_ticks_protecting_instant()` — given a protected instant's offset from window
  start, returns the minimum chunk-1 tick count whose last tick lands strictly more than a margin
  (default one `--interval`, overridable via `--margin-seconds`) past the instant. Never shrinks
  below the normal `ticks_per_chunk`, never grows past the total window; raises if the instant is
  too close to (or before) window start, since there is no boundary before t=0 to move.
- `chunk_max_ticks_sequence_protecting()` — grows chunk 1 via the above, then chunks the
  remainder normally (same tail logic as the existing uniform planner).
- CLI: `--protect ISO_INSTANT` (+ `--margin-seconds` override) on `scripts/burst_chunk_plan.py`.

**Verification against the real precedent:** feeding the FOMC's own numbers back through it
(`--start 2026-07-29T17:40:00Z --until 2026-07-29T19:45:00Z --interval 90 --chunk-minutes 20
--protect 2026-07-29T18:00:00Z`) reproduces the hand-verified `[16, 14, 14, 14, 14, 12]` recipe
from `ops/burst_capture_chunked.md` **exactly** — the tool now generates what a human had to
hand-check after PR #200's verifier catch. `ops/burst_capture_chunked.md` updated to show the
reproducing command alongside the literal sequence (kept literal for direct copy-paste into the
live trigger prompt, unchanged from before — still Ryan/a Ryan-supervised session's action to
apply it, per the existing 2026-07-15 precedent this runbook already follows).

Scope kept honest, matching L164's own candidate wording — not generalized further this round:
ONE protected instant only; a second decisive moment in the same window (e.g. an FOMC presser
Q&A) still needs a hand check, exactly as L164 flagged as future, non-trivial work.

### L165 — built its own named disposition (protocol tier)

L165's own text judged this "likely terminal as **protocol**" — no static scanner can verify a
citation is accurate without re-reading the cited artifact and comparing content, which is
exactly what a `verifier` pass already does by charter. Added the reminder to both agents whose
output carries citations:

- `.claude/agents/edge-prober.md` gained a house-style bullet: grep-verify a cited artifact
  before writing a count into a "facts, not new claims" section; if the real source is a live
  tool-call result rather than a committed file, say so explicitly.
- `.claude/agents/verifier.md` gained a numbered attack step ("Attack citations, not just
  numbers") — a true number cited to the wrong source is still a REFUTED-class defect.

## Ledger disposition

New lessons **L166** (supersedes L164's enforcement column: `tool (enforced) + test`) and **L167**
(supersedes L165's enforcement column: `protocol, encoded`) appended to
`kb/lessons/00-lessons.md`. **The UNENFORCED backlog is empty again as of L167.**

## Two-agent verdict rule

N/A — tool build + lesson-conversion + agent-house-style documentation addition (no registry
flip, no bootstrap CI, no kill decision), same posture as L106/L107/L109/L116/L118/L126/L144/
L150/L152/L156/L157/L160/L161/L163.

## Gates

- `pytest -q`: exit 0, 0 failed. `pytest --collect-only -q` summed to **1990 collected** across
  all files (re-verified after this diff's last edit — 14 new tests in
  `tests/test_burst_chunk_plan.py`, no other test file touched). This sandbox's `pytest -q`
  prints only per-file progress dots with no "N passed" summary line reaching stdout/stderr (the
  same output-plumbing quirk L162/L163 documented) — a clean exit code plus the independent
  collected-count cross-check is the honest floor this run can state, per LOOP-QUEUE.md step 4's
  own rule.
- `python scripts/invariants.py --full`: exit 0 — `invariants: all green`. Same pre-existing
  non-gating advisory classes as `main` before this run (directory-shaped `dt=` paths, GC
  dispatch, daily-cadence missing days, raw-`fromisoformat` call sites, the recovery-dwell
  advisory, the L52 binary-result advisory) — no new advisory class, since this run touched no
  scanned production tape/settlement code path.

## Paper tier (step 9)

`SHADOW_REGISTRY = {s14_ladder_underwriting}` (`dead ✗` per Q34 — **paper-infra validation only,
NOT edge evidence**). `python scripts/paper_pass.py` processed 13 newly-eligible events against
tape committed since the ledger's last entry: realized P&L **+$19.56** (`broker_truth`, up from
+$18.15), 1059 settled contracts, 0 open positions. New ledger lines under
`paper/ledger/dt=2026-07-26.jsonl`.

## Separately noted, not actioned

The dead-collector-leg advisory (`scripts/invariants.py`, L156) did not fire this run's gate
output above the pre-existing set — the VPS `:23` leg's silence duration was not independently
re-measured this run (out of scope for this milestone; the last measurement, 2026-07-25, stood at
61.7h). Unblocking remains Ryan-side.

## Next

The lessons ledger's `UNENFORCED` backlog is empty again as of this row. A future idle run
drawing on policy (a) will find nothing to convert until a new lesson is filed as `UNENFORCED`;
policy (b)/(c)/(d) remain available in the meantime. The Q19 FOMC burst leg (2026-07-29 17:40Z)
still needs Ryan (or a Ryan-supervised session) to apply the chunked-commit recipe to the live
trigger `kalshi-burst-fomc-0729` before it fires — unchanged action item from PR #200/#201.
