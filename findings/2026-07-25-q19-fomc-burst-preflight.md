# Q19 FOMC burst-capture pre-flight (2026-07-25, research loop, idle-run policy b)

## CORRECTION (same-day follow-up, independent verifier review after the first commit merged)

An independent `verifier` pass on the original version of this finding (merged as part of
PR #200) caught two factual errors and one design flaw in the chunked-commit recipe below.
Fixed in this revision, nothing hidden:

1. **"captured 144 snapshots" was mis-cited.** The original text attributed this number to
   `kb/00-LOG.md`'s 2026-07-14 entry, which does NOT contain it (that entry says the opposite in
   kind — "produced NO tape anywhere ... the session apparently did not even reach its own
   fallback-branch-push step" — no snapshot count). The 144 figure is real and traceable to a
   different source: the live `kalshi-burst-wcfinal-0719`/`kalshi-burst-fomc-0729` trigger
   prompts' own "MANDATORY PUSH VERIFICATION" text (read directly via `list_triggers` earlier in
   this session), which states it was "added 2026-07-15 after the semi-1 burst captured 144
   snapshots, claimed 'committed', and the data never reached the remote." Corrected below to
   cite that source, not `kb/00-LOG.md`.
2. **Denominator was wrong.** "2 of 3 prior burst-capture windows fired but committed no data"
   (quoting PR #195's own framing) refers to the THREE **World-Cup-family** one-shots
   (`wcsemi1-0714`, `wcsemi2-0715`, `wcfinal-0719`) — 2 of those 3 lost their data (semi1, final),
   1 succeeded (semi2). It does NOT include `kalshi-burst-cpi-0714`, which also fired and
   succeeded (`tape/burst-20260714T120659Z`, per `kb/00-LOG.md`'s 2026-07-14 entry). Counting all
   FOUR one-shots that have fired to date (cpi, wcsemi1, wcsemi2, wcfinal — `fomc-0729` has not
   fired yet): **2 of 4 (50%) lost their data**, not "2 of 3."
3. **Seam-risk design flaw in the chunked recipe.** The original uniform 6×14-tick chunk plan
   places its first chunk boundary at approximately 17:59:30Z-18:01:00Z — squarely straddling the
   FOMC statement's 18:00:00Z release instant, the single highest-information moment in the whole
   window. L57 (the June-CPI burst finding) already established that an entire burst's lead-lag
   signal can live in ONE release-instant capture; a chunk seam (the commit+push+verify pause
   between chunks) landing there risks losing exactly the tick that matters most — the opposite of
   what this recipe is supposed to protect. Fixed below: a hand-verified, non-uniform first chunk
   sized so the release instant falls safely inside it, not on its boundary.

`scripts/burst_chunk_plan.py`'s `chunk_seconds` field also had an off-by-one (it reported
`ticks_per_chunk * interval_seconds`, the ticks' *nominal* combined window, not
`(ticks_per_chunk - 1) * interval_seconds`, the actual wall-clock span from a chunk's first tick
to its last — the quantity that matters for seam planning, since the first tick of a fresh
invocation fires immediately with no wait). Fixed in the same commit as this correction, with a
regression test.

---

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

- **`kalshi-burst-cpi-0714`** (2026-07-14 12:05→13:45Z): fired, succeeded —
  `tape/burst-20260714T120659Z` carries real captures (`kb/00-LOG.md` 2026-07-14 entry).
- **`kalshi-burst-wcsemi1-0714`** (2026-07-14 20:10→22:30Z): fired, never committed —
  `kb/00-LOG.md`'s 2026-07-14 entry states plainly "produced NO tape anywhere ... no commit ...
  no fallback branch ... the session apparently did not even reach its own fallback-branch-push
  step" (it does not give a snapshot count or a definitive root cause). The "144 snapshots
  captured, claimed 'committed', lost when the sandbox died" characterization comes from a
  DIFFERENT source: the live burst-trigger prompts' own "MANDATORY PUSH VERIFICATION" text
  (`kalshi-burst-wcfinal-0719`/`kalshi-burst-fomc-0729`, read via `list_triggers`), which itself
  is a later (2026-07-15) restatement, not a first-hand log of the failure as it happened.
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

Net: 2 of the 4 one-shots fired so far lost their data (`wcsemi1`, `wcfinal`); a fix targeting
the sandbox-death failure mode (applied after the first loss) did not prevent the SECOND. FOMC
is the fifth one-shot and by far the highest-stakes window — S17's kill/live decision is gated
on it (`LOOP-QUEUE.md` Q19).

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

## A third gap the chunked fix itself introduces (caught by verifier review, fixed here)

Chunking trades "lose the whole window" for "lose at most one chunk" — but a NAIVE
uniform-size chunk plan can place a chunk SEAM (the commit+push+verify pause between two
invocations) directly on top of the single most information-dense instant in the window. For
FOMC that instant is the 18:00:00Z statement release. A uniform 20-minute/14-tick chunk plan
starting at 17:40:00Z puts its first seam at approximately 17:59:30Z-18:01:00Z — exactly
straddling the release. L57 (`findings/2026-07-14-s17-burst-cpi-q19.md`) already found that the
ENTIRE lead-lag signal in the June-CPI burst lived in ONE release-instant capture (removing it
collapsed rho from 0.902/0.777 to 0.196/0.037); a seam-induced gap at 18:00:00Z on FOMC risks
losing exactly the tick the whole exercise exists to protect. **Rule: no chunk boundary may fall
within one capture interval of a one-shot's decisive release instant.** The recommended recipe
in `ops/burst_capture_chunked.md` is a hand-verified, non-uniform sequence built around this
constraint (first chunk sized to fully contain 18:00:00Z with margin, not to seam at it).

Two smaller gaps, also fixed in the recipe: (a) each chunk's own `python -m
collection.burst_capture` invocation returns exit code 1 whenever any family's completeness
check fails within that chunk (a real possibility — crypto/sports feeds do have gaps) — this is
EXPECTED and must not be read as "the chunk failed, stop"; the trigger prompt must say so
explicitly. (b) commit+push+`git ls-remote` verification takes real wall-clock time (not
instantaneous) across 6 chunks — the recipe should not assume the tick sequence alone accounts
for the full ~125 minutes; some margin is absorbed by per-chunk overhead, which is fine (the
window's own `--until` deadline still caps the total, per `run_burst`'s "honest zero-tick exit"
behavior once the deadline passes) but should be stated rather than silently assumed away.

## What this run built (no verdict, no registry change, no P&L claim)

- `scripts/burst_chunk_plan.py` (+18 offline tests, `tests/test_burst_chunk_plan.py`) — pure
  arithmetic computing a `--max-ticks` chunk sequence for a UNIFORM chunk size over a given
  window/interval, so the runbook's numbers are a reproducible command output, not hand
  arithmetic. Reports `chunk_seconds` as the actual first-tick-to-last-tick span within a chunk
  (`(ticks_per_chunk - 1) * interval_seconds` — corrected in this revision; the original version
  over-counted by one interval, reporting the ticks' nominal combined window instead). The tool
  does NOT protect a decisive release instant from landing on a seam — it computes a uniform
  plan only; for a one-shot with a single high-value release moment (FOMC's 18:00:00Z statement),
  the seam-risk section above requires a manually-verified non-uniform first chunk, which is what
  `ops/burst_capture_chunked.md`'s actual recommended recipe uses (NOT this tool's raw uniform
  output — see the runbook for why).
- `ops/burst_capture_chunked.md` — the recipe: run `collection.burst_capture --max-ticks N` per
  chunk, commit+push+verify after EACH chunk (reusing the existing mandatory-push-verification
  step, now applied per-chunk instead of once), and report how many of N chunks actually landed
  in the final message and phone note (rather than a bare pass/fail that would have hidden
  exactly what happened on 07-14 and 07-19). Includes the literal recommended replacement text
  for `kalshi-burst-fomc-0729`'s step 3 — a hand-verified, seam-safe, non-uniform chunk sequence
  (see the seam-risk section above), not the tool's raw uniform output.
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
L152/L156/L157/L160/L161/L163 precedent. An independent `verifier` DID review this finding
before the correction round above — not as a two-agent-rule requirement (none applies), but
because Ryan will act on it before a one-shot, unrepeatable event. It caught the two citation
errors and the seam-risk design flaw documented above; all three are fixed in this revision.

## Lessons

Two candidates surfaced by the verifier's review, recorded here for a future idle run to
formalize (not built this round — see `kb/lessons/00-lessons.md` L164/L165):
- Chunking a one-shot capture window to bound data loss introduces blind seams at chunk
  boundaries; a uniform chunk plan can place a seam on top of the single most decisive instant
  in the window (L57's CPI single-tick-carries-everything finding generalizes here).
- An unsourced count in a "documented facts, not new claims" section is synthetic by CLAUDE.md's
  trust-default rule, whether or not it happens to be independently true — every count needs
  line-level provenance, and "matches my memory of an earlier read" is not a citation.

## Gates

- `pytest -q`: green (18 new tests in the original commit + more in this correction — see the
  correction commit's own message for the exact post-edit count, per the L162/L163
  fresh-gate-line rule).
- `python scripts/invariants.py --full`: exit 0, same pre-existing non-gating advisory classes
  as `main` before this run.
