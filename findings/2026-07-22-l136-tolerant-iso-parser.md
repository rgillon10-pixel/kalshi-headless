# L136 closed — sanctioned tolerant ISO-timestamp parser, wired into its live-symptom file

**Date:** 2026-07-22 (research loop, idle-run policy (a) — UNENFORCED lesson → test)
**Status:** infra fix, no strategy claim, no registry change. Two-agent verdict rule N/A (not a
verdict-class change — a code fix + tests, same tier as L108/L112/L116/L118/L121/L122/L124/L126).

## Background

`kb/lessons/00-lessons.md` L136 (filed by PR #153, 2026-07-22) documented a real, live test
failure: Python 3.9's `datetime.fromisoformat` rejects fractional-second precision that isn't
exactly 3 or 6 digits (e.g. Kalshi's trailing-zero-stripped `...:04.7Z`), and rejects a trailing
`Z` outright. `tests/test_s17_leadlag_probe.py` fails on clean `main` under 3.9 for exactly this
reason. L136 left the fix as an UNENFORCED candidate: "a shared tolerant timestamp parser... OR
pin a 3.11+ runtime."

## What was found

`core/timeutil.py` already had this parser — `_parse_iso`, built for `parse_kalshi_ts`'s
epoch-vs-ISO dispatch — but it was private, with no entry point for a caller parsing a
standalone ISO string directly. `scripts/s17_leadlag_probe.py` (L136's own live-symptom file)
still called `datetime.fromisoformat` raw in two places: `parse_capture_time` (line 304) and
`parse_window_bound` (line 321).

## Fix

- `core/timeutil.py`: added `parse_iso_utc(s: str) -> datetime`, a public wrapper around the
  existing `_parse_iso`. No change to the tolerant-parsing logic itself — it was already correct.
- `scripts/s17_leadlag_probe.py`: both raw `fromisoformat` call sites now route through
  `parse_iso_utc`.
- Regression tests added in `tests/test_timeutil.py` (7 cases covering `parse_iso_utc`
  directly: single-digit fraction, `Z` + short fraction, no fraction, full 6-digit microseconds,
  naive-string-assumed-UTC, non-UTC offset conversion, bad-string raises `ValueError`) and
  `tests/test_s17_leadlag_probe.py` (2 cases pinning the exact L136 malformed-input shape,
  `...04.7Z`, end-to-end through `parse_capture_time` and `parse_window_bound`).

## Verification note (sandbox runs Python 3.11, not 3.9)

This cloud sandbox runs Python 3.11.15, where `fromisoformat` already tolerates short fractions
— so the literal 3.9 failure cannot be reproduced or re-broken here as a live check. Confidence
instead comes from construction: `parse_iso_utc` normalizes the fraction to exactly 6 digits and
maps `Z`→`+00:00` **before** calling `fromisoformat`, so the string `fromisoformat` actually sees
is byte-identical regardless of Python version — the fix is version-independent by design, not by
observed behavior on this box. The new tests pin the exact malformed-input shape from the lesson,
so a future 3.9 CI run (or the VPS, which runs 3.9) exercises the identical code path.

## Scope explicitly left out

`core/timeutil.py::parse_iso_utc` and the two `s17_leadlag_probe.py` call sites are the only
call sites migrated this run. A repo-wide grep finds roughly 30 other files (`collection/*.py`,
several other `scripts/*.py`) that still call `datetime.fromisoformat` directly on raw strings —
none of them are today's L136 live symptom, and migrating all of them (plus verifying each one's
existing tests/live behavior is unaffected) is a separate, larger milestone, optionally backed by
a static invariant forbidding raw `fromisoformat` outside `core/timeutil.py`. Left as residue on
L138's enforcement row for a future idle run, not silently dropped.

## Gates

- `pytest tests/test_timeutil.py tests/test_s17_leadlag_probe.py`: all green (9 new tests).
- `pytest` full suite (excluding the two files broken by the pre-existing, unrelated
  `cryptography`/pyo3 ABI panic — see GitHub issue #157): green, byte-identical failure set to
  `main` before this change (verified via `git stash`/compare).
- `python scripts/invariants.py --full`: exit 2, but identical 2 violations to `main` before this
  change (both `inv_order_endpoints_confined` false-positives from PR #153's test files — see
  issue #157; this diff touches neither flagged file). **Not merging this PR until #157 is
  resolved**, per LOOP-QUEUE.md step 6 (a red `main` gate blocks merging even when the redness
  is pre-existing and unrelated) — same posture as PR #158 this same run-cycle.
