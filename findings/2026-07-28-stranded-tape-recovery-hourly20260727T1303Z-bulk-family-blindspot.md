# Stranded-tape recovery (`tape/hourly-20260727T1303Z`, 21,303 lines) + `tape_branch_sweep.py` bulk-family blind spot (2026-07-28)

Step 0b milestone: three consecutive prior runs (PRs #217, #218/#219, #220) recorded
"`tape/hourly-20260727T1303Z` already recovered by PR #217 — nothing new to sweep," each
trusting `scripts/tape_branch_sweep.py`'s report at face value. This run re-verified that
branch directly, by hand, against `HEAD` rather than re-trusting the prior claim — and found
it was wrong.

## The blind spot

`tape_branch_sweep.py`'s per-file line-set containment check applies a `--max-file-bytes`
size guard (default 2,000,000 bytes) that **skips** any file above that size, reporting the
branch as "no problem found but NOT FULLY VERIFIED" rather than flagging a gap. The module's
own docstring says this "excludes this repo's bulk families by construction" —
`orderbook_depth`, `universe_sweep`, `sports_pairs`. That line is accurate on its face, but its
practical effect is a standing coverage hole: any stranded line in exactly those three families
is **structurally invisible** to the sweep tool, every run, forever, unless someone checks by
hand. Three runs in a row (07-27T21:1x, 07-28T00:1x, 07-28T03:2x) read "no branch newer than
`tape/hourly-20260727T1303Z`" and "13 missing-lines hits, all previously-triaged false
positives" as a clean bill of health for that branch — none of them noticed the size-guard
skip meant `orderbook_depth`/`universe_sweep` were never actually checked on it.

## What was actually stranded

Direct capture_id-level comparison of `tape/hourly-20260727T1303Z` (commit `0e9870b`,
2026-07-27T13:11:49Z, an `hourly_pass` run that fell back off `main`) against `HEAD`'s current
per-day tape files found three genuinely missing captures, none present anywhere in `HEAD`'s
tape tree:

| family | capture_id | lines | evidence |
|---|---|---|---|
| `weather_books` | `20260727T130038Z` | 302 | `HEAD`'s `dt=2026-07-27.jsonl` had captures at 04:00/07:00/16:00/22:00 only — 13:00 absent |
| `orderbook_depth` | `20260727T125540Z` | 1,001 | `HEAD` had 03:55/06:55/15:55/21:55 captures only — 12:55 absent |
| `universe_sweep` | `20260727T130302Z` | 20,000 | `HEAD` had exactly ONE capture (07:03) for the whole day — 13:03 absent entirely |

Total: **21,303 lines**, all valid JSON (verified via `json.loads` on every extracted line),
all `dt=2026-07-27`. The branch's other five touched files
(`crypto_hourly`, `hyperliquid_funding`, `perp_tape`, `polymarket_macro_pairs`,
`sports_pairs`, `weather_actuals`) were independently verified fully contained in `HEAD`
(raw line-set diff, 0 missing) — those are correctly not part of this recovery.

Union-appended to each family's `dt=2026-07-27.jsonl` (pure append — pre-recovery content is
an exact prefix of post-recovery content; post-append dedup check confirms 0 duplicate lines
in any of the three files). The branch is not deleted here — step 0b defers deletion until
the PR carrying these lines merges, per protocol.

## Why this matters beyond one branch

The same three families (`orderbook_depth`, `universe_sweep`, `sports_pairs`) are exactly the
ones large enough to trip the 2MB size guard on almost every `tape/hourly-*` branch, which
means **every prior sweep's "fully contained + verified" and "nothing new to sweep" claims for
these three families were never actually checked** — the tool's own report format
distinguishes "fully contained + verified" from "no problem found but NOT FULLY VERIFIED," but
prior runs' prose (including this run's own predecessors) collapsed that distinction when
summarizing the sweep result. New lesson **L216** (below) records this; the honest fix is
either a cheaper per-family check that doesn't require reading the whole file (e.g. capture_id
set comparison via a lighter parse, or raising the size guard for a bounded per-branch budget)
or an explicit standing exception: bulk-family branches always get the manual capture_id
check this run just did, never trusted to the tool's default guard alone.

## Gates

`python3 -m pytest -q`: **2,162 collected, 0 failed** (fresh `--collect-only -q` count, taken
after this diff's last edit — pure tape append, no source touched).
`python3 scripts/invariants.py --full`: exit 0, `invariants: all green` — same pre-existing
non-gating advisory classes as PR #220 (dir-shaped days, GC-dispatch, daily-cadence gaps,
hollow crypto ladders, capped-pagination coverage ceiling, raw-`fromisoformat` backlog,
recovery-dwell, unguarded-settlement; VPS collector-dead advisory duration increased as
expected). No new advisory class introduced by this diff.

No strategy claim, no registry change, no bootstrap CI/P&L — pure data recovery plus a
tooling-blind-spot finding, same posture as the 07-23/07-25/07-26/07-27 stranded-tape
recoveries. Two-agent verdict rule N/A (not a verdict-class change).

## Addendum (2026-07-28, research loop, idle-run policy (a): L216 → enforced)

Built the fix L216 proposed as its own candidate (option (a), "a cheaper per-family check ...
avoiding the need to load the whole file"): `scripts/tape_branch_sweep.py` gains
`BULK_CAPTURE_ID_FAMILIES` + `capture_ids_in_blob()`. Every line within one of these families'
captures is minted atomically by a single collector pass and shares one `capture_id` (this
run's own table above is the direct evidence — one row per capture, not per line), so
comparing the small set of DISTINCT `capture_id` values between a branch and `HEAD` is a
structurally-sound, cheap proxy for containment, without materializing a 20MB file into a
frozenset of full line strings. `per_file_containment()` now takes this path for an oversized
file under a bulk family IF the branch side yields >=1 real `capture_id` — an oversized bulk
file with none (malformed content, or a family whose schema genuinely lacks the field) still
falls back to the honest "skipped, no signal" behavior rather than reading zero-matched as
zero-missing. The result is surfaced as its own `BranchTriage.capture_id_checked_files`
field/`capture_id_only` property and its own report bucket — never silently folded into
"every line checked", since it is a genuinely coarser (though real) guarantee.

**Verified directly against the real recovery branch this addendum's own parent commit
already merged:** re-running `triage_branch()` on `tape/hourly-20260727T1303Z` (sha `0e9870b`)
against the current `HEAD` now reports `contained=True`, `fully_verified=True`,
`capture_id_only=True`, with `orderbook_depth/dt=2026-07-27.jsonl` and
`weather_books/dt=2026-07-27.jsonl` both showing 0 missing capture_ids — a genuine,
independent confirmation that this run's own recovery above was complete, rather than a
second unverified "no problem found" skip.

**Scope note — `weather_books` added as a fourth bulk family, not just the three L216 named.**
L216's own text (and the docstring it was quoting) named `orderbook_depth`/`universe_sweep`/
`sports_pairs` as of the 2026-07-25 measurement. Verifying this fix against the real
`tape/hourly-20260727T1303Z` branch found its `weather_books/dt=2026-07-27.jsonl` is
2,303,754 bytes — itself over the 2MB guard — and `HEAD`'s own `dt=2026-07-24/26/27`
`weather_books` day-files measured today at 2.75MB/2.23MB/4.48MB respectively (all carrying a
`capture_id` field). This is in fact the SAME family whose 302-line capture was recovered
above, in this very finding's own table — the size-guard blind spot always covered it too;
L216's prose just didn't name it. Added rather than left as a fresh, undocumented instance of
the exact gap this fix exists to close.

**Tests:** `tests/test_tape_branch_sweep.py` gains `TestCaptureIdsInBlob` (extraction, missing
path, malformed/fieldless lines skipped not crashed) and `TestBulkCaptureIdCheck`
(contained-via-capture_id, missing-capture_id, `triage_branch`-level `capture_id_only`
semantics, cache reuse) — 12 new tests, all against a real temporary git repo (this module's
existing testing discipline), plus a `format_report` case pinning the new report bucket and
wording. All pre-existing tests in the file are unchanged in behavior: the two extant
size-guard tests use `sports_pairs` content with no `capture_id` field, so they exercise the
"no signal, fall back to skip" branch exactly as before.

No strategy claim, no registry change, no bootstrap CI/P&L — a tooling fix with test coverage,
same posture as the L156/L168/L172/L211/L215 precedents. Two-agent verdict rule N/A (not a
verdict-class change; disposition per L188's grammar, see `kb/lessons/00-lessons.md` L217).
