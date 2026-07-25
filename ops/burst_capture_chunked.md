# Chunked burst-capture recipe (added 2026-07-25 — Q19 FOMC pre-flight)

## The problem this fixes

Every burst trigger today (`ops/ROUTINES.md` "Burst-capture legs") runs ONE continuous
`python -m collection.burst_capture --until <end> --interval I --families F` for the whole
event window (up to ~155 minutes) and commits tape to git exactly ONCE, after the script exits
on its own. Two of the three fired one-shots so far produced ZERO committed tape despite
`last_fired_at` confirming they ran:

- `kalshi-burst-wcsemi1-0714` (2026-07-14) — `kb/00-LOG.md` 2026-07-14 entry pins this to the
  triggered sandbox dying mid-run, losing 144 already-captured snapshots that were never
  committed.
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

Use `scripts/burst_chunk_plan.py` to compute the exact `--max-ticks` sequence — do not
hand-compute it (an arithmetic slip here is exactly the class of bug this repo's lessons ledger
keeps catching elsewhere, e.g. L162). Example, the FOMC window:

```
$ python3 scripts/burst_chunk_plan.py --start 2026-07-29T17:40:00Z --until 2026-07-29T19:45:00Z \
    --interval 90 --chunk-minutes 20
total_ticks=84 interval=90s chunk~21.0min n_chunks=6
max_ticks_sequence=[14, 14, 14, 14, 14, 14]
```

## Recommended trigger-prompt replacement (FOMC, `kalshi-burst-fomc-0729`)

This is a RECOMMENDATION, not applied by this run. Per the 2026-07-15 precedent
(`kb/00-LOG.md` 2026-07-14 entry: "already Ryan-hardened ... that's handled"), editing a live
one-shot trigger's prompt is Ryan's call, not an autonomous cloud run's — the account-level
`update_trigger` tool was deliberately not invoked here. Ryan (or a Ryan-supervised session) can
apply this via `update_trigger` on `trig_01L9RysFtWUUjj3BgQmNKw7g` any time before 2026-07-29
17:40Z.

Replace step 3 of the existing prompt (`Run: python -m collection.burst_capture --until ...`)
with:

```
3. Compute the chunk plan (do not hand-compute): `python3 scripts/burst_chunk_plan.py --start
   2026-07-29T17:40:00Z --until 2026-07-29T19:45:00Z --interval 90 --chunk-minutes 20`
   -> max_ticks_sequence=[14, 14, 14, 14, 14, 14] (6 chunks).
   For EACH value N in that sequence, in order:
   a. Run: python -m collection.burst_capture --until 2026-07-29T19:45:00Z --interval 90
      --families fed,econ,crypto --max-ticks N
      (the SAME --until every time; the script self-limits to N ticks or the deadline,
      whichever comes first, and exits 0 with 0 ticks harmlessly once the deadline has passed —
      if that happens, stop the loop, do not run remaining chunks).
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
failed" summary would have hidden on 07-14 and 07-19.

## Applying this pattern to future one-shots

Any new burst trigger (a future FOMC meeting, a new World-Cup-style event) should use this same
chunked recipe from the start rather than the single-continuous-run template — compute its
`--max-ticks` sequence with `scripts/burst_chunk_plan.py` and follow the step-3 replacement
above, substituting that event's own `--until`/`--interval`/`--families`.
