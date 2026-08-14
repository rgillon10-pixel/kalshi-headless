# Chunked burst-capture recipe (added 2026-07-25 — Q19 FOMC pre-flight)

**Correction (same-day follow-up, independent verifier review):** the original version of this
runbook mis-cited the "144 snapshots" figure to `kb/00-LOG.md` (it isn't there — the real source
is below), miscounted "2 of 3" fired one-shots (it's 2 of 4), and recommended a UNIFORM chunk
plan whose seam lands on top of the FOMC release instant itself. All three fixed here; see
`findings/2026-07-25-q19-fomc-burst-preflight.md`'s correction section for the full account.

## The problem this fixes

Every burst trigger today (`ops/ROUTINES.md` "Burst-capture legs") runs ONE continuous
`python -m collection.burst_capture --until <end> --interval I --families F` for the whole
event window (up to ~155 minutes) and commits tape to git exactly ONCE, after the script exits
on its own. 2 of the 4 one-shots fired so far produced ZERO committed tape despite
`last_fired_at` confirming they ran (`kalshi-burst-cpi-0714` and `kalshi-burst-wcsemi2-0715`
both fired and succeeded — this hits about half the one-shots that have run, not all of them):

- `kalshi-burst-wcsemi1-0714` (2026-07-14) — `kb/00-LOG.md`'s 2026-07-14 entry states plainly
  it "produced NO tape anywhere ... no commit ... no fallback branch ... the session apparently
  did not even reach its own fallback-branch-push step" (no snapshot count, no definitive root
  cause given there). The "144 snapshots captured, claimed 'committed', lost when the sandbox
  died" characterization is from a DIFFERENT, later (2026-07-15) source: the live burst-trigger
  prompts' own "MANDATORY PUSH VERIFICATION" text (`kalshi-burst-wcfinal-0719`/`-fomc-0729`,
  read via `list_triggers`).
- `kalshi-burst-wcfinal-0719` (2026-07-19) — lost data too, even though a 2026-07-15
  Ryan-applied fix had already added mandatory push-verification to every remaining one-shot
  (`kalshi-burst-wcsemi2-0715`/`-wcfinal-0719`/`-fomc-0729`). `LOOP-QUEUE.md` Q19's 2026-07-19
  status line records the trigger fired (`last_fired_at` set) but no `tape/polymarket_pairs/
  dt=2026-07-19.jsonl` and no `tape/burst-*` branch ever carried it.

The push-verification fix hardens the LAST step (confirm the commit is visible on some remote
ref); it does nothing for a run that never reaches that step at all. The structural gap: each
underlying collector `run()` call (`collection.polymarket_pairs`, `collection.crypto_hourly`,
etc.) writes its own tape line to local disk on every tick — the data isn't silently
uncaptured, it's captured-then-orphaned in a sandbox that gets torn down before the single
end-of-window commit ever runs (or, alternatively, before the window's start if the triggered
session spins up late — both failure modes currently look identical from the outside: zero
committed tape, no error). See `findings/2026-07-25-q19-fomc-burst-preflight.md` for the full
write-up; both explanations are stated there as hypotheses, not confirmed root cause — there is
no direct evidence (e.g. a captured stderr) distinguishing them, only the documented facts above.

## The fix: chunk the window, commit after every chunk

`collection.burst_capture` already supports `--max-ticks` — no source change is needed. Instead
of one ~125-160min invocation + one commit, run several ~20-minute chunks, each its own
`--max-ticks`-capped invocation immediately followed by the SAME commit/push/verify steps the
one-shot prompt already has. Worst case, a chunk's own sandbox dies: every PRIOR chunk is
already safely on the remote, and only the in-flight chunk (≤20 min of ticks) is at risk instead
of the whole window.

Use `scripts/burst_chunk_plan.py` to compute a UNIFORM chunk sequence — do not hand-compute it
(an arithmetic slip here is exactly the class of bug this repo's lessons ledger keeps catching
elsewhere, e.g. L162). Example, the FOMC window's naive uniform plan:

```
$ python3 scripts/burst_chunk_plan.py --start 2026-07-29T17:40:00Z --until 2026-07-29T19:45:00Z \
    --interval 90 --chunk-minutes 20
total_ticks=84 interval=90s chunk~19.5min n_chunks=6
max_ticks_sequence=[14, 14, 14, 14, 14, 14]
```

**This naive uniform output must NOT be used as-is for FOMC.** Its first chunk boundary (the
seam between chunk 1 and chunk 2) falls at approximately 17:59:30Z-18:01:00Z — straddling the
18:00:00Z statement release, the single highest-information instant in the window. L57 found
the entire June-CPI burst's lead-lag signal lived in ONE release-instant capture; a seam there
risks losing exactly the tick this whole recipe exists to protect. `scripts/burst_chunk_plan.py`
computes a uniform plan only — it does not know about a decisive release instant and will not
warn you (see its module docstring). **The recommended recipe below hand-adjusts the first
chunk so the release instant falls safely inside it, verified by
`tests/test_burst_chunk_plan.py::test_hand_verified_seam_safe_fomc_recipe_keeps_release_inside_first_chunk`.**

## Recommended trigger-prompt replacement (FOMC, `kalshi-burst-fomc-0729`)

This is a RECOMMENDATION, not applied by this run. Per the 2026-07-15 precedent (`kb/00-LOG.md`'s
2026-07-15 04:xx entry: "already Ryan-hardened ... that's handled"), editing a live one-shot
trigger's prompt is Ryan's call, not an autonomous cloud run's — the account-level
`update_trigger` tool was deliberately not invoked here. Ryan (or a Ryan-supervised session) can
apply this via `update_trigger` on `trig_01L9RysFtWUUjj3BgQmNKw7g` any time before 2026-07-29
17:40Z.

Replace step 3 of the existing prompt (`Run: python -m collection.burst_capture --until ...`)
with:

```
3. Use this seam-safe chunk sequence (do NOT regenerate it with scripts/burst_chunk_plan.py's
   PLAIN default --chunk-minutes 20 with no --protect — that produces a uniform plan whose first
   seam lands on the 18:00:00Z release instant; see ops/burst_capture_chunked.md). As of L164
   (2026-07-26) it is reproducible by machine, not just by hand:
   python scripts/burst_chunk_plan.py --start 2026-07-29T17:40:00Z --until 2026-07-29T19:45:00Z
     --interval 90 --chunk-minutes 20 --protect 2026-07-29T18:00:00Z
   max_ticks_sequence = [16, 14, 14, 14, 14, 12]  (6 chunks, sums to the window's 84 ticks;
   chunk 1's extra 2 ticks push its boundary to ~18:02:30Z, safely past the release with margin).
   For EACH value N in that sequence, in order:
   a. Run: python -m collection.burst_capture --until 2026-07-29T19:45:00Z --interval 90
      --families fed,econ,crypto --max-ticks N
      (the SAME --until every time; the script self-limits to N ticks or the deadline,
      whichever comes first, and exits 0 with 0 ticks harmlessly once the deadline has passed —
      if that happens, stop the loop, do not run remaining chunks). This command's own exit code
      is 1 whenever any family's completeness check failed during this chunk's ticks — that is
      EXPECTED and not a reason to stop; only a process crash / no output at all means the chunk
      itself was lost.
   b. Commit ONLY new/changed files under tape/, message 'tape: burst fomc-jul29 chunk <k>/6
      <UTC ISO timestamp>'. git pull --rebase origin main, then git push origin main; on
      rejection retry rebase+push up to 3 times; if still failing, push to branch
      tape/burst-<YYYYMMDDTHHMM>Z (the research loop's stranded-tape sweep recovers those).
   c. MANDATORY PUSH VERIFICATION per chunk (same rule as before, now applied 6 times instead
      of once): run git ls-remote origin and confirm this chunk's commit SHA is reachable from
      SOME remote ref. If not, retry under a fresh branch name; if STILL not visible, note
      'chunk <k>/6 PUSH FAILED' and continue to the next chunk anyway (a lost chunk should never
      block the remaining ones from still trying to land).
   d. If `date -u` is already past 2026-07-29T19:45:00Z, stop the loop early (the window is
      over) rather than running a chunk with 0 useful ticks.
```

Step 6 (final message) and step 7 (phone note) should report how many of the 6 chunks landed
successfully, not just an overall pass/fail — e.g. "5/6 chunks committed, chunk 4 lost (sandbox
restart), data for that ~20min segment missing" is exactly the information a bare "burst
failed" summary would have hidden on 07-14 and 07-19. Six commit+push+verify round-trips also
take real wall-clock time out of the ~125-minute window (not accounted for by the tick sequence
alone) — this is fine, `--until` still bounds the total, but don't assume the chunks alone fill
the window with zero overhead.

## Applying this pattern to future one-shots

Any new burst trigger (a future FOMC meeting, a new World-Cup-style event) should use this same
chunked recipe from the start rather than the single-continuous-run template. Compute the sequence
with `scripts/burst_chunk_plan.py`, passing `--protect` ONCE PER decisive instant the event has
(a scheduled statement, a print time, a kickoff, a presser Q&A):

```
$ python3 scripts/burst_chunk_plan.py --start 2026-07-29T17:40:00Z --until 2026-07-29T19:45:00Z \
    --interval 90 --chunk-minutes 20 \
    --protect 2026-07-29T18:00:00Z --protect 2026-07-29T18:30:00Z
total_ticks=84 interval=90s n_chunks=6 protect_offsets=[20.00min, 50.00min]
max_ticks_sequence=[16, 14, 14, 14, 14, 12]  (only the chunks whose own seam was violated grew, L164)
seam_check=PASS (margin=90s, 0 violations)
```

**Update (2026-08-14 — L164's remaining half is now built; this section previously said "the tool
will not do it for you").** Three things changed and one did not:

1. `--protect` is REPEATABLE. An event with a statement AND a presser no longer needs a hand check
   for the second instant.
2. Only the chunk whose OWN seam is violated grows. The 2026-07-26 single-instant form grew chunk 1
   regardless of where the instant fell, which inflates the worst-case loss the chunking exists to
   bound (measured: a 43-tick first chunk where 15 was asked for). The two agree exactly whenever
   the instant falls inside chunk 1 — the FOMC recipe above is unchanged either way.
3. An ALREADY-WRITTEN sequence (e.g. one already pasted into a live trigger prompt) can now be
   CHECKED rather than regenerated, and exits non-zero on a violation, so a runbook step or a CI
   caller can gate on it:

```
$ python3 scripts/burst_chunk_plan.py --start 2026-07-29T17:40:00Z --until 2026-07-29T19:45:00Z \
    --interval 90 --verify-sequence 14,14,14,14,14,14 --protect 2026-07-29T18:00:00Z
seam_check=FAIL (margin=90s, 1 violations)
  instant t+1200s vs seam after chunk 1 [1170s, 1260s] -- gap 0s <= margin 90s
$ echo $?
2
```

4. What did NOT change, and cannot be automated: **deciding WHICH instants are decisive for a given
   event is still human judgment.** The tool protects the instants you give it and has no way to
   know you forgot one. Naming them remains a pre-flight step for every new one-shot.

Pinned by `tests/test_burst_chunk_plan.py` (`::test_committed_fomc_recipe_is_seam_safe_for_BOTH_statement_and_presser`,
`::test_cli_verify_sequence_fails_the_naive_uniform_plan_with_exit_2`) and independently
re-derived on a separate implementation by `scripts/l164_seam_rederive.py`
(`tests/test_l164_seam_rederive.py`). See `findings/2026-08-14-l164-multi-instant-seam-check.md`
and lesson L164/L350 in `kb/lessons/00-lessons.md`.
