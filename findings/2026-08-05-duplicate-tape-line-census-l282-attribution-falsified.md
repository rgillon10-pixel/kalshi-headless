# The 2026-07-28 duplicate is SIX families wide and the step-0b sweep did not cause it — L282's attribution falsified

`research loop` · 2026-08-05 · **IDLE RUN, idle-run policy (c)** · tooling + lesson-correction
+ descriptive tape facts: no P&L, no bootstrap CI, no registry flip, nothing verdict-class.
Two-agent verifier rule is **N/A** by class (L145/L152/L205/L210/L223/L281/L282 precedent);
no `Task` tool was available in this harness, so no subagent was dispatchable regardless —
stated, not hidden.

## Verdict (one line)

A repo-wide exact-line census of **all 1,476,500 committed tape lines across 342 day-files** finds byte-identical
duplicate lines on **exactly one calendar day** — `dt=2026-07-28` — in **six families**
totalling **1,358 lines**, and traces every one of them to **one ordinary hourly-pass commit,
`10681abe`**. **L282's attribution is wrong on both counts:** the incident is not confined to
`orderbook_depth` (1,093 lines was 80% of it, not all of it), and the step-0b stranded-branch
sweep it blames (`c4ed31ab`, PR #223) left the tape **duplicate-free**.

Reproduce (offline, read-only, ~5s):
`python3 -c "from scripts import invariants as inv; import json;
print(json.dumps(inv._tape_duplicate_line_issues(), indent=2))"`.
Pinned by 16 new tests in `tests/test_invariants.py`, including a HARD real-tape acceptance
test that reds the moment a seventh family or a second day appears.

## 1. The census

Exact-line (byte-identical) duplicate census over every `tape/**/*.jsonl`:

| family | day-file | lines | duplicate lines | duplicated `capture_id` |
|---|---|---|---|---|
| `orderbook_depth` | `dt=2026-07-28` | 6,484 | **1,093** | `20260728T065616Z` |
| `sports_pairs` | `dt=2026-07-28` | 1,562 | **228** | `20260728T065420Z` |
| `perp_tape` | `dt=2026-07-28` | 102 | **17** | `20260728T070408Z` |
| `polymarket_macro_pairs` | `dt=2026-07-28` | 112 | **16** | `20260728T065605Z` |
| `crypto_hourly` | `dt=2026-07-28` | 14 | **2** | `20260728T065559Z` |
| `hyperliquid_funding` | `dt=2026-07-28` | 12 | **2** | `20260728T070413Z` |
| **total** | | | **1,358** | one pass, six legs |

Everything else in committed tape is clean: **0 duplicate lines on any other day, in any other
family**, including the 8 days of tape appended since. Each family's duplicates come from
**exactly one** `capture_id`, and all six of those ids belong to **the same collection pass**
(`20260728T065635Z`, whose legs stamped 06:54Z–07:04Z). This is one pass landing twice, not
scattered per-row repeats.

## 2. What actually happened (commit-by-commit)

| commit | UTC | what it did to the six day-files | duplicates after |
|---|---|---|---|
| `dd29b3a3` / `8130bffa` | 06:57 / 07:07 | the `20260728T065635Z` morning pass lands on `main`, split across two commits (the second literally titled "(continued)") | **0** |
| `c4ed31ab` (**PR #223**, step-0b sweep) | 08:07 | recovers branch `tape/hourly-20260728T1004Z` — **1,691 lines across 10 files**, incl. 1,093 `orderbook_depth` rows carrying `capture_id=20260728T095630Z`, a **different, genuinely-absent** capture | **0** |
| `10681abe` "tape: hourly pass 2026-07-28T13:08:00Z" | 13:09 | appends, in all six families, a **verbatim re-append of the whole morning pass** followed by the new 12:5xZ/13:0xZ rows | **1,358** |

`10681abe`'s parent **is** `c4ed31ab`, so every line it duplicated was already in its own
parent commit. The appended region's block structure is identical in all six families, e.g.:

* `orderbook_depth`: `[DUP 20260728T065616Z ×1093][NEW 20260728T125552Z ×1084]`
* `sports_pairs`: `[DUP 20260728T065420Z ×228][NEW 20260728T125421Z ×224][NEW 20260728T130509Z ×223]`
* `perp_tape`: `[DUP 20260728T070408Z ×17][NEW 20260728T130357Z ×17]`

## 3. Why L282's attribution is falsified, tested directly

L282 states: *"commit `8130bff` … introduced the pass fresh … and commit `c4ed31a` … independently
reintroduced the SAME 1,093 rows from a branch that had forked before `8130bff` landed — the
stranded-branch-sweep's own line-level containment check correctly (by its own contract) saw
1,093 'new' lines that were in fact already on `main`."*

Measured, three independent ways:

1. **The sweep's own output is duplicate-free.** At `c4ed31ab` the census returns **0**
   duplicate lines in every one of the six files.
2. **The sweep's rows are a different capture.** Its 1,093 `orderbook_depth` rows carry
   `capture_id=20260728T095630Z`; the duplicated rows carry `20260728T065616Z`. They are not
   the same content.
3. **Today's containment check agrees with the sweep.** Re-running the current
   `scripts/tape_branch_sweep.py::per_file_containment("origin/tape/hourly-20260728T1004Z",
   base_ref="8016b8ac")` — the sweep commit's own parent — returns **1,691 missing lines across
   10 files, 0 size-guard-skipped**, which is *exactly* what `c4ed31ab` committed (numstat:
   1+2+5+2+1093+17+24+16+228+303 = 1,691). The check did not mis-fire; it was right.

The branch `tape/hourly-20260728T1004Z` is still on `origin`, so (3) is re-runnable today.

Consequence for the L170→L281→L282 arc: **L170 and L281 stand** (both are genuine
branch-local-dedup findings, and L281's `weather_books/meta` duplicates differ in content, a
class this byte-identical census cannot see and does not claim to). What does **not** stand is
L282's promotion of the pattern to *"a structural property of the step-0b stranded-branch-sweep
workflow itself"*. The sweep was the one actor in this incident that behaved correctly.

## 4. The mechanism that fits the evidence

The 13:09Z tree = `main`'s file (2,186 lines) ++ a **stale local copy of the morning pass**
(1,093) ++ the new pass (1,084), in that order, in all six families simultaneously. That is the
signature of a **union-style conflict resolution applied during `git pull --rebase`**: the
LOOP-QUEUE step-0b "keep both sides, append" convention is correct for a *stranded branch*
(disjoint content by construction) and **wrong as a pull-conflict resolution**, where the local
side's overlap with upstream has, by definition, already been merged.

What rules out the simpler story: a plain rebase *replay* of a carried-forward local commit
would have produced its own commit, and the graph has none — `10681abe`'s parent is
`c4ed31ab` directly. What cannot be proven from the object graph: which runner/agent resolved
it, since the collector's local state is long gone. That is stated as a limit, not guessed at —
the same discipline L221/L222 impose on pass attribution.

**Live-risk read, honest:** the specific route is *plausibly* closed (cloud runs now push to
`tape/hourly-*` branches rather than to `main`), but the shape that produced it is still in
active use — `main` still carries multi-commit carried-forward passes as recently as
2026-08-02 (`… [continued]`, `… [final]`), and `ops/vps/kalshi-headless-hourly.sh` still opens
each pass with `git pull --rebase -q origin main` over a tree that may hold an unpushed tape
commit. Eight subsequent days are clean, which is evidence of rarity, not of repair.

## 5. What was built

`scripts/invariants.py`: `TAPE_DUP_LINE_ALLOWLIST` + `_tape_duplicate_line_issues()` +
`tape_duplicate_line_warning()`, wired **non-gating** into `--full`'s stderr advisory stanza,
`BaseException`-wrapped (L156 DEFECT-1). Family-agnostic by design — the defect lives in the
commit path, not in any collector — which also makes it the cheapest superset of the two
existing per-family duplicate advisories. Lines are compared by 16-byte digest so the 760k-line
`universe_sweep` files cost bounded memory; whole-tape runtime ~5s.

`ORDERBOOK_DEPTH_DUP_ALLOWLIST` / `WEATHER_BOOKS_META_DUP_ALLOWLIST` are deliberately left in
place: the first is now redundant in coverage but its `(capture_id, ticker)` framing is the
finer-grained one, and the second detects the content-differing class this census cannot.

**Scope limit, stated up front (L155):** this detects **byte-identical** repeats only. A
0-issue report is precision evidence about exact re-appends and is **never** a clean bill of
health for logical-key duplication (L281's class). A file whose name carries no `dt=` date can
never be allowlisted — conservative toward flagging.

## Gates

`pytest` and `python scripts/invariants.py --full` both re-run after the last edit; numbers in
`kb/00-LOG.md`'s entry for this run.
