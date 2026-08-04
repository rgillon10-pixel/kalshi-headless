# `weather_books` meta sidecar — L84's concurrency-safety claim is falsified on committed tape

`research loop` · 2026-08-04 · **IDLE RUN, idle-run policy (c)** · tooling/lesson-correction
verdict only: no P&L, no CI, no registry flip, nothing verdict-class

## Verdict (one line)

`tape/weather_books/meta/dt=2026-07-27.jsonl` violates its own write-once-per-`(series,
group)`-per-day contract — **47 of its 48 keys are duplicated**, and **5 of those 47 pairs
differ in content** (`rules_primary`/`sample_ticker`), not just in `capture_id`/`captured_at`.
Every other of the 19 committed day-files is exactly 1:1. Lesson **L84** ("per-(entity, day)
dedup implemented by reading the day's already-written tape is concurrency-safe across
concurrent writers") is false as a repo-wide claim — it holds only within one working tree —
and its cited test (`tests/test_weather_books.py::test_meta_written_once_per_series_day`)
passes green while the real committed tape violates the property it claims to protect. New
lesson **L281** supersedes L84 per the ledger's own rule (never edit/delete a row).

Reproduce: `python3 -c "from scripts import invariants as inv; import json;
print(json.dumps(inv._weather_books_meta_duplicate_issues(), indent=2))"` (offline, read-only).
Pinned by 16 new tests in `tests/test_invariants.py`, including a HARD real-tape acceptance
test.

## 1. The mechanism

`collection/weather_books.py::_existing_meta_series` dedups a day's meta write by reading the
day's already-written file back and skipping any `series` already present
(`collection/weather_books.py:262-275`). That is correct and sufficient **for a single
process on a single working tree**. It is not correct across this repo's actual operating
pattern: two collector passes can each run on their own unmerged `tape/hourly-*` fallback
branch (LOOP-QUEUE.md step 0b's standing mechanism — the hourly collector's push to `main`
falls back to a per-run branch when it can't push directly). Each branch-local process reads
back a file that does not yet contain the sibling branch's write, sees no conflict, and both
write a meta record for the same `(series, day)`. The step-0b sweep later union-appends both
branches' tape into `main` — and its containment check is **line-level**: because the two rows
carry different `capture_id`/`captured_at` (and, in 5 cases, different `rules_primary`/
`sample_ticker`), they are not the same line, so the sweep correctly (by its own contract)
keeps both. The duplicate is invisible to every check in the pipeline: `_existing_meta_series`
only ever sees one branch at a time, and the sweep only ever compares line sets.

Traced by `git log -S'20260727T040036Z' -- tape/weather_books/meta/` and the same for
`20260727T070032Z`: both blocks entered `main` in a single commit, `a7ee98b` (2026-07-31,
"idle-run(a): L221's MEASUREMENT half UNENFORCED -> test" — an unrelated milestone; the
duplicate rode in as tape recovered by that run's step-0b sweep), and that commit is the
file's entire history.

## 2. The numbers

| check | result |
|---|---|
| day-files in `tape/weather_books/meta/` | 19 (2026-07-16 → 2026-08-04) |
| day-files with a duplicated `(series, group)` key | **1** (`dt=2026-07-27`) |
| duplicated keys / total keys on that day | **47 / 48** |
| duplicate pairs with genuinely differing content (excl. `capture_id`/`captured_at`) | **5** (all `KXTEMP*H` hourly-directional series) |
| duplicate pairs byte-identical modulo capture metadata | 42 |
| the two colliding `capture_id`s on 2026-07-27 | `20260727T040036Z` (47 rows), `20260727T070032Z` (47 rows), plus one late single-row pass at `20260727T220039Z` (a genuinely new series that day, not part of the duplicate) |

Example of a content-differing pair (`KXTEMPAUSH`):

```
capture_id=20260727T070032Z  sample_ticker=KXTEMPAUSH-26JUL2704-T82.99
  rules_primary: "...Jul 27, 2026 4 AM EDT ... above 82.99°..."
capture_id=20260727T040036Z  sample_ticker=KXTEMPAUSH-26JUL2701-T83.99
  rules_primary: "...Jul 27, 2026 1 AM EDT ... above 83.99°..."
```

Both rows are individually honest (verbatim from a real market, never guessed) — the defect is
that a consumer keying meta by `series` for that day gets a value that depends on which row it
happens to read, not a stable per-day fact.

## 3. Blast radius today: nil, but the test that should have caught it didn't

`grep -rn` finds zero production consumers of `tape/weather_books/meta/` — only
`tests/test_weather_books.py:303`. So the duplicate is currently latent; nothing downstream is
silently corrupted. But that single-process test is exactly the gap: it pins the write-once
behavior under one collector invocation and therefore cannot see the cross-branch failure mode
that actually produced the real defect. This is the same shape L170 (2026-07-26) found in
`hyperliquid_funding.py` and explicitly flagged as worth re-checking elsewhere — confirmed here
in a second family.

## 4. What was built

* **`scripts/invariants.py::_weather_books_meta_duplicate_issues` /
  `weather_books_meta_duplicate_warning`** — a non-gating `--full` advisory. For every
  `tape/weather_books/meta/dt=*.jsonl`, counts `(series, group)` occurrences; a day outside
  `WEATHER_BOOKS_META_DUP_ALLOWLIST = {"2026-07-27"}` with any duplicate is reported as a
  **NEW regression**; the allowlisted day is reported as the known historical incident. Kept
  non-gating for the same reason L210's colliding-`capture_id` advisory is non-gating: the
  historical duplicate lines are already committed, append-only tape and cannot be un-written,
  so gating on them would fail every future `--full` run over an already-known, already-record
  fact. `BaseException`-wrapped in `main()` like every sibling advisory (L156 DEFECT-1: a
  formatter raise or non-str return must never silently become a gate).
* **`collection/weather_books.py` docstring** corrected in place with a dated note (L279
  precedent: annotate, don't rewrite) — states the working-tree-local scope of the dedup
  guarantee and which meta fields are true series-level constants
  (`settlement_sources`/`title`/`fee_type`, 0 variation across 19 days save one deliberate
  `frequency` reclassification, see §5) versus per-pass samples
  (`rules_primary`/`sample_ticker`/`contract_url`).
* **`kb/lessons/00-lessons.md` L281** — supersedes L84 per the ledger's own rule (rows are
  never edited or deleted).
* **16 new tests** in `tests/test_invariants.py`: clean-day / different-group-is-not-a-dup /
  byte-identical-duplicate / content-differing-duplicate / allowlisted / garbage-input /
  missing-series-field coverage over synthetic fixtures, a warning-content test for each of the
  new-regression and known-incident message branches, a never-gates-exit-code regression test,
  and one HARD real-tape acceptance test (`test_acceptance_l281_real_tape_reproduces_the_2026_07_27_incident`)
  pinning the exact numbers above so a future sweep introducing a *second* incident is caught
  immediately rather than silently absorbed into "well dt=2026-07-27 is already known-dirty."

## 5. Side-finding, not a defect: the `frequency` reclassification

While auditing per-field stability, all 5 hourly-directional series (`KXTEMPNYCH`,
`KXTEMPAUSH`, `KXTEMPCHIH`, `KXTEMPDCH`, `KXTEMPLAXH`) flipped `frequency` from `"one_off"` to
`"hourly"` between `dt=2026-07-23` and `dt=2026-07-24`, simultaneously, with `title` and
`settlement_sources` unchanged — a genuine, dated, venue-side reclassification our own tape
happened to capture, relevant background for Q36. Not acted on further this run.

## Two-agent rule

N/A — tooling/lesson-correction, no registry flip, no bootstrap CI, no kill decision, same
posture as L145/L152/L205/L210/L223's precedent. `verifier` was not dispatched (not required
for this milestone class); the real-tape numbers were instead independently re-derivable
in one command and are pinned by the hard acceptance test above.
