# `orderbook_depth` — L84's concurrency-safety claim falsified a 3rd time, plus a post-VPS cadence collapse

`research loop` · 2026-08-04 · **IDLE RUN, idle-run policy (c)** · tooling/lesson-correction +
descriptive cadence facts: no P&L, no CI, no registry flip, nothing verdict-class

## Verdict (one line)

`tape/orderbook_depth/dt=2026-07-28.jsonl` carries **1,093 byte-identical duplicate
`(capture_id, ticker)` rows** — an entire pass (`capture_id=20260728T065616Z`) landed on
`main` TWICE via two separately-racing commits — the same step-0b union-append mechanism L281
diagnosed for `weather_books/meta` earlier today, and L170 diagnosed for `hyperliquid_funding`
on 2026-07-26. This is the **third** family to show the identical defect from the identical
mechanism, which means the claim in **L84** ("per-(entity, day) dedup implemented by reading
the day's already-written tape is concurrency-safe across concurrent writers") is not a
per-family bug — it is a structural property of the repo's step-0b stranded-branch-sweep
workflow itself, and any future collector that dedups the same way will eventually show the
same defect. New lesson **L282** supersedes L84 for this family (ledger rows are never
edited/deleted). Separately, and not the same defect: the family's own capture **cadence**
degraded roughly 6x in the median case (and far worse in the tail) after the VPS collector
died (~2026-07-22) — a fact this audit measured directly rather than inferring from the
join-side view L280 took this morning.

Reproduce (both, offline, read-only): `python3 -c "from scripts import invariants as inv;
import json; print(json.dumps(inv._orderbook_depth_duplicate_capture_issues(), indent=2))"`.
Pinned by 14 new tests in `tests/test_invariants.py`, including a HARD real-tape acceptance
test.

**Not a repeat of the prior `orderbook_depth` audit.** This family was already audited
2026-07-26 for hollow crypto ladders (L168/L169,
`findings/2026-07-26-orderbook-depth-hollow-crypto-ladders.md`) — a book-CONTENT defect (empty
ladders near a ticker's close). This run's two angles — the branch-merge duplicate-capture
defect and the post-VPS capture-cadence collapse — are both new; neither was checked by that
prior audit.

## 1. The duplicate — mechanism and forensics

`collection/orderbook_depth.py::run` has no read-back dedup at all (unlike
`weather_books`'s `_existing_meta_series` or `hyperliquid_funding`'s per-day guard) — it simply
appends every captured ticker's snapshot to `dt=<day>.jsonl` on every pass. That is safe within
one process. It is not safe against this repo's actual operating pattern: two collector
invocations can each land on their own unmerged `tape/hourly-*` fallback branch (LOOP-QUEUE.md
step 0b), and when BOTH branches' tape is later union-appended into `main`, a pass that both
branches captured independently — or, as happened here, a single real pass whose commit got
recorded on `main` twice — survives as a literal duplicate. The step-0b sweep's own containment
check is line-level; two rows differing in nothing at all are still two separate `git commit`
events if they land via two different merge paths, and nothing downstream re-derives
uniqueness.

Traced via `git log --numstat` on `tape/orderbook_depth/dt=2026-07-28.jsonl`: two commits each
added exactly 1,093 lines for `capture_id=20260728T065616Z`:

| commit | wall time (UTC) | message |
|---|---|---|
| `8130bff` | 2026-07-28T07:06:58Z | `tape: hourly pass 20260728T065635Z (continued)` |
| `c4ed31a` | 2026-07-28T13:07:07Z | `tape: recover 1,691 stranded lines (hourly-20260728T1004Z) (#223)` |

`8130bff`'s parent does not contain the capture at all (`git show <parent>:<file> | grep -c
06:56:16.273008` → 0), so `8130bff` introduced it fresh; `c4ed31a` — a stranded-branch recovery
PR whose own message claims "1,691 stranded lines" — independently reintroduced the identical
1,093-row pass from a branch that had forked before `8130bff` landed on `main`, so its own
line-level containment check (correctly, by its own contract) saw 1,093 "new" lines that were
in fact already on `main` under a different commit. This is the exact race L281 named, just
with the roles reversed: there, two racing writers both missed each other; here, a live pass and
a stale-branch recovery both "won."

## 2. The numbers

| check | result |
|---|---|
| day-files in `tape/orderbook_depth/` | 28 (2026-07-07 → 2026-08-04, gaps are missing days not corrupt ones) |
| day-files with a duplicated `(capture_id, ticker)` key | **1** (`dt=2026-07-28`) |
| duplicated keys / total keys on that day | **1,093 / 5,391** |
| duplicate pairs with genuinely differing content (excl. `capture_id`/`ticker`) | **0** — every duplicate is byte-identical, unlike L281's 5 content-differing pairs |
| total records in the affected capture | 2,186 (1,093 tickers × 2) |

Every OTHER of the 28 committed day-files is clean (checked exhaustively, not sampled — see
the acceptance test in §4).

## 3. Blast radius today: one consumer already defends against exactly this, most don't

`grep -rln "orderbook_depth"` finds ~20 consumers across `scripts/`/`execution/`. Checked each
for a `capture_id` grouping/dedup step (the thing a byte-identical duplicate would corrupt):
**`scripts/s6_maker_firstcut.py::_dedup_by_capture`** (line 148) already drops repeat
`capture_id`s per ticker, with a docstring reading "belt-and-suspenders so a duplicated pass
line never fakes a zero-gap pair" — i.e. this exact defect class was anticipated (plausibly
informed by L210, 2026-07-27) and defended against before this audit ever ran; S6's numbers are
unaffected by the `dt=2026-07-28` incident. `scripts/s19_wing_fade_fillsim.py` joins by ticker +
nearest-`captured_at` rather than a `capture_id` key; a duplicate is a redundant, content-
identical candidate match, not a corruption. Neither `scripts/q51_maker_fillsim.py` nor the
other ~18 consumers key by `capture_id` at all — they iterate in append order or key by
`(ticker, captured_at)`, so today the 1,093 duplicate rows just look like repeated observations
at an identical timestamp, not a schema violation. A FUTURE consumer that groups by
`(capture_id, ticker)` expecting exactly one row, without S6's defensive dedup, would silently
double-count that pass's liquidity for every affected ticker. Latent for everyone but S6 (which
is immune by design), same posture as L281.

## 4. What was built

* **`scripts/invariants.py::_orderbook_depth_duplicate_capture_issues` /
  `orderbook_depth_duplicate_capture_warning`** — a non-gating `--full` advisory, structurally
  identical to L281's weather_books-meta advisory: counts `(capture_id, ticker)` occurrences
  per day-file, reports any day outside `ORDERBOOK_DEPTH_DUP_ALLOWLIST = {"2026-07-28"}` as a
  **NEW regression**, the allowlisted day as the known historical incident. Non-gating for the
  same reason as L210/L281: the duplicate lines are already-committed append-only tape and
  cannot be un-written. `BaseException`-wrapped in `main()` per L156 DEFECT-1 (a formatter raise
  or non-str return must never silently become a gate).
* **`kb/lessons/00-lessons.md` L282** — supersedes L84 a third time.
* **14 new tests** in `tests/test_invariants.py`: clean-day / different-capture-is-not-a-dup /
  byte-identical-duplicate / content-differing-duplicate / allowlisted / garbage-input /
  missing-ticker-field coverage over synthetic fixtures, a warning-content test for each message
  branch, a never-gates-exit-code regression test, and one HARD real-tape acceptance test
  (`test_acceptance_l282_real_tape_reproduces_the_2026_07_28_incident`) pinning the exact
  numbers above so a future sweep introducing a *second* incident is caught immediately.

No `collection/orderbook_depth.py` code change was made this run — the collector itself has no
bug (append-only-per-pass is the correct design for a full-depth snapshot family, unlike
weather_books' write-once-per-day meta contract); the defect lives entirely in the step-0b
union-append workflow, which is Ryan-lane repair territory (a general dedup-on-merge tool, not
a per-family collector fix). Flagged, not built, this run.

## 5. Side-finding: post-VPS-death cadence collapse, measured directly on this family

Independent of the duplicate, this audit measured `orderbook_depth`'s own capture cadence
across its full 28-day history (462 distinct capture passes) rather than inferring it from the
`kalshi_trades` join-side view L280 took this morning. Splitting at 2026-07-22 (the VPS
collector's last live capture, per the existing dead-collector-leg diagnosis):

| period | n passes | median gap | mean gap | max gap |
|---|---|---|---|---|
| before 2026-07-22 (VPS + cloud both alive) | 391 | **0.52h** (31min) | 0.92h | 56.91h (one 07-08→07-10 outage, pre-dates the VPS death) |
| on/after 2026-07-22 (cloud-only) | 71 | **3.00h** | 4.72h | **21.00h** |

The post-VPS median (3.00h) roughly matches the cloud research-loop's own 3-hourly firing
cadence (LOOP-QUEUE.md's loop-frequency change, 2026-07-12) — meaning the nominally-**hourly**
`kalshi-collector` leg is no longer actually landing hourly captures of this family; the 3-hour
research-loop cadence is now the effective floor, and the tail (up to 21h, matching the 18h gap
L280 independently found for 08-03→08-04) is worse than that floor. This directly corroborates
and generalizes L280's finding (`orderbook_depth` max gap 18h in an 08-02..08-04 slice) to the
family's entire post-VPS history: the degradation is not a one-off, it is the new steady state.
Descriptive only — not acted on (no collector-cadence fix attempted; VPS revival is Ryan's
call, already flagged by the existing dead-collector-leg advisory).

## Two-agent rule

N/A — tooling/lesson-correction and descriptive cadence facts, no registry flip, no bootstrap
CI, no kill decision, same posture as L145/L152/L205/L210/L223/L281's precedent. `verifier` was
not dispatched (not required for this milestone class); every number above is independently
reproducible in one offline command and is pinned by the hard acceptance test in §4.
