# Stale UNENFORCED queue audit + tape-pinned gate repair (2026-07-27 idle run)

`created 2026-07-27` · `corrected 2026-07-27 after an independent verifier round REFUTED several
of its numbers` · research loop, IDLE RUN, policy (a) · producer + independent `verifier` round

> **Read this first.** An independent `verifier` round **REFUTED** three published numbers and one
> central conclusion of the first draft of this file. Every affected figure below has been
> corrected in place and the refutation is written out in full in
> [§ Verifier round](#verifier-round--what-was-refuted). The short version:
> the gate line `2136 passed, 0 failed` was **false** (the suite was `2 failed, 2134 passed` at
> that instant); `tests/test_stale_unenforced_advisory.py` was **48** tests, not 49, and is **65**
> now; "reaches 7 of 21" is **fixture-measured only**; and Unit 1's conclusion that the
> `**UNENFORCED**` work queue was **empty is FALSIFIED** — it was never empty. Corrected lessons:
> **L193**-**L200**.

Two units of work in one idle run:

1. **Unit 1** — the lessons ledger's self-declared standing work queue (its `**UNENFORCED**`
   rows) was audited row-by-row. **21 of the 21 rows the census could see were stale.** L152's own
   follow-up detector, whose entire job is finding exactly that, reported **0 issues** on it.
   The census itself was later shown to be short by two rows (see § Verifier round).
2. **Unit 2** — `main`'s binding pytest gate was RED (pre-existing, 2 failures). Root cause:
   a tape-pinned acceptance test globbing `dt=*` over a **live, still-growing** tape family.
   No code changed anywhere; three routine days of capture moved the population.

Neither unit produces a price, a P&L, a bootstrap CI, or a registry change.
`kb/strategies/00-index.md` is unchanged — still **0 proven edges**.

---

## Unit 1 — the `**UNENFORCED**` queue audit (21 rows disposed; the queue was NOT emptied)

### Measurement

The ledger's header (line 9) states: *"`UNENFORCED` rows are the kb-distiller's standing work
queue."* An independent `verifier` parsed every table row and classified every row whose
enforcement column starts `**UNENFORCED**`, with file:line evidence per row.

```bash
# row census (measured 2026-07-27, repo root)
python3 -c "import sys;sys.path.insert(0,'scripts');import invariants as I;r=I._parse_lesson_rows();u=[x for x in r if x[2].startswith('**UNENFORCED**')];print(len(r),len(u),[x[0] for x in u])"
```

→ **185 rows parsed · 21 marked `**UNENFORCED**` · 21 of 21 classified already-BUILT stale
markers · 0 genuinely open · 0 terminal-as-protocol-unbuilt.**

**That census is WRONG and the command above is the buggy one** (kept verbatim because it is the
artifact being corrected). It used a naive `|` split and a strict `startswith("**UNENFORCED**")`
literal, and both defects independently hid `L145`. Corrected live census, after the parser and
marker-shape remediation (measured 2026-07-27, repo root):

```bash
python3 -c "import sys;sys.path.insert(0,'scripts');import invariants as I;r=I._parse_lesson_rows();d=I._lesson_disposed_ids(r);u=[x[0] for x in r if x[2].lstrip().startswith('**UNENFORCED')];print(len(r),len(u),[x for x in u if x not in d])"
```

→ **190 rows · 23 carrying an `UNENFORCED` marker · 21 disposed by L188 · exactly 2 genuinely
OPEN: `L145` and `L192`.** (This file's own lesson rows L193-L200 have since moved those figures;
per L161 every count here carries its command and its measurement time.)

Idle-policy (a), as scoped ("convert an open UNENFORCED lesson into enforcement"), had no target
among the 21 audited rows — every one was already built. It did have targets the census could not
see: `L145`, whose resolution is a policy call reserved for Ryan, and (after the fact) `L192`.

### The detector that should have caught this reported nothing

```bash
python3 scripts/invariants.py --full   # BEFORE this run's fix
```

`scripts/invariants.py::_stale_unenforced_candidate_issues()` — built as L152's own follow-up —
extracted **0 candidate tokens from those 21 rows and reported 0 issues**, printing nothing at
all. A 100%-stale queue and a clean queue produced byte-identical output.

### The 21 rows and their audited terminal disposition

(These 21 dispositions and their file:line evidence **stand** — the verifier round did not disturb
them. What it disturbed is the claim that these 21 were the whole queue. One evidence line was
corrected: **L76**, see § Verifier round.)

| id | terminal tier | evidence |
|---|---|---|
| L22 | test | `core/source_tag.py:17-27` documents the deliberate decision NOT to add `real_bid`; `tests/test_invariants.py::test_db_real_bid_tag_is_caught_as_invalid_enum`. The row's "kb-distiller to decide" is DECIDED. |
| L27 | test | `core/bootstrap.py:122 clears_tick_magnitude()`; `tests/test_bootstrap.py:75-97`; `.claude/agents/edge-prober.md:34` |
| L28 | test | `core/bootstrap.py:138 floor_pinned_fraction()`; `tests/test_bootstrap.py:102-120`; `edge-prober.md:38` |
| L32 | test | `core/bootstrap.py:155 bracket_by_movement()` (returns `frac_frozen` :177 AND both cuts); `edge-prober.md:47`; adopter `scripts/q37_weather_summer_makerno_probe.py:36` |
| L39 | test | `core/bootstrap.py:241 decompose_edge_by_leg_volume()` + `core/income_legs.py:23,37` (12 tests); `edge-prober.md:99` |
| L45 | test | `core/timeutil.py:105 parse_crypto_hour_token_close_utc()`; `tests/test_timeutil.py:19-66` |
| L51 | test | `core/bootstrap.py:281 disagreement_subset_calibration()`; `tests/test_bootstrap.py:451-507`; `edge-prober.md:211` |
| L59 | test | `core/reversal.py:30 direction_precheck()`; `tests/test_reversal.py` (11 tests). **RESIDUAL:** zero callers outside its own test, and no `L59` mention in any `.claude/agents/*.md` — a future momentum probe can still hand-roll a frequency-only classification without tripping anything. |
| L64 | test | `core/timeutil.py:125/147/160`; `tests/test_timeutil.py:74-82`; `edge-prober.md:139` |
| L65 | protocol | `edge-prober.md:148-160` (verbatim idea-stage kill incl. the 0.024h / empty-book numbers) |
| L66 | protocol | `edge-prober.md:161-168` |
| L68 | protocol | `edge-prober.md:169-176` |
| L69 | protocol | `edge-prober.md:109-121` |
| L76 | test | `core/bootstrap.py:187 collapse_duration_gated_runs()`; `tests/test_bootstrap.py:171-207`; adopter `scripts/q43_perp_binary_consistency_probe.py:73` |
| L86 | test | `core/bootstrap.py:344 catastrophic_leg_drop_stress_check()`; `tests/test_bootstrap.py:304-366` |
| L105 | protocol | `edge-prober.md:188-196` |
| L117 | test/invariant | `scripts/tape_gap_monitor.py:448 collector_bucket()` + `:460 diagnose_collector()`; `tests/test_tape_gap_monitor.py:280-290`; surfaced non-gating at `scripts/invariants.py:2286`. Already superseded in substance by L118. |
| L119 | test | `core/pricing.py:186 book_notional_at_touch()` with `LOW_TOUCH_NOTIONAL_WARN_DOLLARS=50.0`; `tests/test_pricing_book_notional.py` (8 tests) |
| L162 | protocol | Candidate (b) — which the row itself calls the cheaper and probably correct form — is built at both named sites: `LOOP-QUEUE.md:72-77` (step-4 fresh-gate-line rule) and `.claude/agents/kb-distiller.md:26-30`. Candidate (a) deliberately NOT built (would require running the full suite inside `invariants.py`, a regression of that file's offline/fast contract). |
| L164 | test | `scripts/burst_chunk_plan.py:115/149/216` (`--protect`); `tests/test_burst_chunk_plan.py:235-241` pins the hand-verified FOMC recipe `[16,14,14,14,14,12]`; `ops/burst_capture_chunked.md:89-91`. CLI re-run reproduces it byte-identically. |
| L165 | protocol | `.claude/agents/verifier.md:36-41` and `edge-prober.md:227-231` |

### The fix (built this run, in `scripts/invariants.py` + `tests/`)

Three new candidate matchers, **enforcement-column-only**, plus a machine-readable close marker
and a **published recall figure** in the warning text itself.

**FIXTURE-MEASURED**, against the frozen fixture of the 21 rows
(`tests/fixtures/lessons_unenforced_21_2026-07-27.md`, byte-identical copies), measured
2026-07-27:

**reaches 7 of 21 rows, 8 hits — `func=0, path_symbol=1 (L76), script_flag=1 (L164),
agent_charter=5 (L28, L32, L51, L105, L165)`.**

**This figure is fixture-scoped and is NOT a property of the live ledger.** On the live ledger the
same detector reads, today: `0 flagged · extraction reached 0 of 2 open UNENFORCED rows · 21
formally disposed via `DISPOSES:``. Quoting the 7-of-21 as a live recall would be exactly the
error L155/L189 warn about, one level further out.

The 14 rows not reached are enumerated as a named constant in the tests and are **deliberate
blind spots**: prose candidates naming no artifact; L22 names only a constant plus a bare path;
L117 names a script but no CLI flag; L162 names non-`.py` files; L39 mentions the charter without
backticking its path; L65/L66/L68 are idea-stage writeup rules with no artifact to find.

A **measured precision cost** is published alongside: of the 164 non-`UNENFORCED` rows, **22**
name a charter that does not cite their own ID, so the `agent_charter` matcher misses them.

New tests: `tests/test_stale_unenforced_advisory.py` — **48** at that point (the first draft of
this file, and L189's enforcement column, said 49; that was wrong), **65** after the remediation
(48 + 17). `tests/test_invariants.py` collects **193**. Measured 2026-07-27:
`python3 -m pytest -o addopts="" -q --collect-only tests/test_stale_unenforced_advisory.py`
→ `65 tests collected`; adding `tests/test_invariants.py` → `258 tests collected`.

### The close marker

The advisory is suppressed per-row only by one canonical, case-sensitive marker in the
**enforcement column** (5th pipe column):

```
DISPOSES: L22, L27, L28
```

Grammar documented and test-pinned at `scripts/invariants.py::_lesson_disposed_ids`: `L<digits>`
tokens separated by commas and/or spaces, terminating at the first non-separator token (a `.`
ends the list). A prose mention of an ID **never** suppresses. Written this run as **L188**.

---

## Verifier round — what was REFUTED

<a id="verifier-round--what-was-refuted"></a>

An independent `verifier` re-derived Unit 1's claims against the live tree. Four of them did not
survive. A remediation pass then changed the code; this section records both halves.

### 1. REFUTED — "the `**UNENFORCED**` work queue is empty" (L188's conclusion)

It was never empty. **Two independent defects hid the same row.**

**Defect A — the row parser.** `_parse_lesson_rows` split rows on a naive `|`, so any row whose
prose contains a pipe had its enforcement column shifted: **14 of 190 rows misparsed — L25, L37,
L62, L89, L109, L145, L147, L161, L173, L177, L179, L180, L183, L184.** The trap: the obvious
repair "take the second-to-last cell" (`cols[-2]`) **agrees with the correct answer on 13 of those
14** and fails only on **L147**, whose embedded pipe sits inside the enforcement cell itself. Only
a delimiter-aware splitter — `\|` is a literal, and a `|` inside a backtick code span is a literal
— is right for 190/190.

**Defect B — the marker literal.** Even correctly parsed, the membership test
`startswith("**UNENFORCED**")` missed **L145**, whose real cell reads
`**UNENFORCED — UNRESOLVED COLLISION, flagged to parent/Ryan (NOT touched this docs-only pass).**`
— the em dash and qualifier sit **inside** the bold span, so the closing `**` never lands where
the literal expects it. A detector must match the marker's SHAPE, not one spelling.

**True measured state of the ledger (2026-07-27, after remediation, before this run's L193-L200):
190 rows · 23 carrying an UNENFORCED marker · 21 disposed by L188 · exactly 2 genuinely OPEN —
`L145` (the `collection/ws_depth.py` vs `inv_order_endpoints_confined` policy collision, flagged
to Ryan) and `L192` (this run's own row).** L188's 21-row audit stands; its closure claim does
not, and `L145` was never audited into the 21. Recorded as **L193** (correction), **L194**
(parser), **L195** (marker shape), **L196** (two invisibilities, one row).

### 2. REFUTED — the L76 evidence line

The detector's L76 hit was **the right verdict cited to the wrong artifact**. It matched
`tests/test_probe_ladder_coherence.py::test_runs_single_deep_snapshot_fails_duration_gate`, whose
NAME says "duration gate" but whose BODY asserts a snapshot COUNT (`MIN_SNAPS=2`) — the exact
mechanism L76's own text says is **not** a duration gate. L76 genuinely IS stale, but for an
unrelated reason: **L93** later built `core.bootstrap.collapse_duration_gated_runs`.

This is **L165** (a citation is not a verification) **recurring inside the fix for L152** — the
tool built to stop stale statuses was about to certify one on a string coincidence. The
remediation reworded every emitted evidence string to claim only that *the cell NAMES an artifact
that EXISTS in the tree — a NAME match, never proof the enforcement is built*, pinned per matcher
in `tests/test_stale_unenforced_advisory.py`, with L76 written into the docstring as the worked
hazard example. Recorded as **L197**.

### 3. REFUTED — the gate line and the test count

`2136 passed, 0 failed` was published as the post-edit gate; at that instant the suite was
**`2 failed, 2134 passed`**. `tests/test_stale_unenforced_advisory.py` was published as **49**
tests; it was **48**. Both corrected above and in **L199** (L189's row is not edited — append-only).
**L199's own figures then went stale in turn** when the run's FINAL code fix landed (§ *Final fix*
below): the suite is **2159**, not the 2155 L199 published, and that file collects **69** tests,
not 65. Corrected here in place and filed as **L206**; L199's row is not edited either.
**TRUE final gate, taken after the last edit of the run:**

```
python -m pytest -o addopts="" -q      -> 2159 passed in 1152.67s (0:19:12), 0 failed
python scripts/invariants.py --full    -> exit 0, "invariants: all green"
git status --porcelain -- tape/ paper/ -> (empty)
```

### 4. Corrected scope — "reaches 7 of 21"

Valid **only** against the frozen fixture, measured 2026-07-27. The live ledger reads
`0 flagged · extraction reached 0 of 2 open UNENFORCED rows · 21 formally disposed`. Labelled
fixture-measured everywhere in this file; recorded in **L199**.

### Also: `n_disposed = 0` was not a measurement

The `DISPOSES:` grammar shipped with zero pre-existing matches, which was read as "no row has ever
been closed". The ledger already had a supersession convention in prose — **L107 enumerates the
whole closure map** (L22→L24, L27/L28→L33+L34, L32→L35, L39→L73/L98, L45→L49, L51→L103,
L59→L72/L94, L64→L101, L65→L104, L68→L106, L76→L93, L86→L99, plus L66→L116, L69→L112, L105→L107,
L117→L118, L119→L121, L162→L163, L164→L166, L165→L167) — and **L163/L166/L167 each already state
the backlog is empty**. A supersession grammar that matches zero existing rows is a claim about
the future, not a measurement: publish its coverage of the convention already in use before adding
a new one. Recorded as **L198**.

### Disclosed relaxation

During remediation, one HARD real-tree assertion in `tests/test_invariants.py` was **narrowed**:
`assert _stale_unenforced_candidate_issues() == []` → a per-matcher assertion → structural
arithmetic (`test_stale_unenforced_candidate_warning_never_gates_exit_code` now asserts absence of
effect only, with the TEXT contract moved onto the frozen fixture in
`test_stale_unenforced_advisory_text_on_the_frozen_fixture`). It is honestly commented in the file
and it is the correct response to **L192** — but it IS a relaxation of an existing assertion and
is named as one here rather than left to a reader of the diff.

### Flagged, not fixed

- `scripts/gen_problems_dashboard.py::cells` holds a **second, independent copy** of the
  lessons-row parser that handles `\|` but not code-span pipes, so it still mis-buckets
  **3 of 190 rows — L89, L161, L173** — in the HTML dashboard. (That file also hardcodes
  `REPO = find_repo("/Users/ryan.gillon/...")` and raises `SystemExit` on any other checkout, so
  it cannot run in a cloud sandbox at all.) Two copies of one parsing job with two different bugs.
- `tests/test_invariants.py::test_raw_datetime_fromisoformat_warning_never_gates_exit_code` (L138)
  still asserts advisory TEXT on the real tree; its dependency is the repo's own source snapshot
  rather than a live ledger or growing tape, so it was deliberately left — flagged, not silently
  kept.
- The `DISPOSES:` grammar is documented in `scripts/invariants.py` and test-pinned, but **not** in
  `.claude/agents/kb-distiller.md` — the agent expected to use the marker is not told it exists.
  No file under `.claude/` was touched by this pass, by instruction; recorded for Ryan.

All three are the queue entry **L200**.

---

## Unit 2 — `main`'s pytest gate was RED from tape GROWTH, not code

### Baseline

`main` HEAD `ad6b95e`: **2087 collected, 2085 passed, 2 FAILED** —
`tests/test_q42_funding_estimate_path_inference.py::test_tape_leave_one_out_67_drops_decomposes_as_7_18_42`
and `::test_tape_random_same_size_subsets_reproduce_the_dense_cuts_hard_gap`. The previous run
(PR #215, `kb/00-LOG.md` 2026-07-27 ~17:0xZ) recorded these honestly as "known pre-existing
real-tape-drift failures" and left them red.

### Root cause, established by BLOB comparison (not mtime)

```bash
# all 8 day-files: blob hash at the pinning commit vs HEAD
for d in 17 18 19 20 21 22 23 24; do
  git rev-parse cebe691:tape/perp_tape/dt=2026-07-$d.jsonl
  git rev-parse HEAD:tape/perp_tape/dt=2026-07-$d.jsonl
done
git rev-parse cebe691:scripts/q42_funding_estimate_path_inference.py
git rev-parse HEAD:scripts/q42_funding_estimate_path_inference.py
```

All 8 files `tape/perp_tape/dt=2026-07-17..24.jsonl` are **byte-identical** between commit
`cebe691` (where the pins were written) and HEAD, and the probe script is byte-identical too.
`ac8a758`'s 1,798 recovered stranded lines touched **only** `dt=2026-07-27.jsonl` in this family
— the "the stranded-line union-append mutated old day-files" hypothesis is **FALSIFIED** for
`perp_tape`.

The four `@_real_tape` pins globbed `tape/perp_tape/dt=*.jsonl` — an **open-ended glob over a
live, still-growing family** — so three routine days of capture (07-25/26/27) moved the
population with **zero code change anywhere**.

### Frozen slice (dt=2026-07-17..24) vs today's full `dt=*` glob

| statistic | frozen slice (as pinned) | today's full glob |
|---|---|---|
| records | 1667 | 1803 |
| n_estimate_groups | 299 | 377 |
| n_joined_windows | 286 | 364 |
| n_discriminating | 42 | 58 |
| LOO n_tickers_dropped | 7 | 8 |
| LOO n_funding_times_dropped | 18 | 23 |
| LOO n_drops | 67 | 89 |
| p_hard_gap(11) | 0.2057 | 0.3655 |
| p_hard_gap(14) | 0.1042 | 0.2390 |

At 20,000 draws the binomial se at p≈0.2 is ≈0.0029, so **0.2057 → 0.3655 is ≈55 se** — a
population change, not Monte-Carlo noise.

### The repair

**No pin was moved and no tolerance was widened.** The fix made the population explicit
(`_FROZEN_TAPE_SLICE_DAYS`) and added a ratchet test
`test_frozen_tape_slice_is_intact_and_its_population_is_unchanged`, which fires if a future
stranded-line recovery ever union-appends into one of those 8 closed day-files.

**Two of the four pins were passing BY LUCK** —
`..._no_leave_one_out_drop_restores_a_hard_gap` and `..._leave_one_out_max_gap_is_still_negative`
— their extreme-order statistics happened not to move. A green tape pin over an open glob is
therefore **not** evidence that the population is stable.

A tree-wide audit found these four were the **only** pinned-statistic-over-open-ended-live-glob
tests. Other real-tape tests are already frozen
(`tests/test_dead_collector_leg_advisory.py::_SLICE_MAX_DAY`,
`tests/test_orderbook_depth_hollow_ladder_audit.py::_FROZEN_MAX_DAY`) or assert properties/ratios
rather than statistics.

### Finding-side correction

`findings/2026-07-24-q42-funding-estimate-path-inference.md`'s numbers all still reproduce
**exactly** from the frozen slice. Its *Artifacts* footer named the slice correctly, but its
*Reproduce* section said `dt=*` — so the published repro command had stopped reproducing the
published numbers. Corrected in place by another agent this run.

**Q42's own verdict is UNCHANGED: H1 still UNDECIDABLE, no CI, no registry change.** This unit
is test hygiene only.

---

## Gates

**Baseline** for the run, on `main` HEAD `ad6b95e`: **2087 collected, 2085 passed, 2 failed**.

**Mid-run (WRONG, retained for the record).** The first draft of this file published
`2136 passed, 0 failed` as the post-edit gate. That number was **false when written**: the suite
was **`2 failed, 2134 passed`** at that instant. Writing **L188** (the disposition row) drove
`n_open_unenforced` to 0, the advisory correctly went silent, and the two tests that asserted it
FIRES on the real tree
(`tests/test_stale_unenforced_advisory.py::test_advisory_is_non_gating_on_the_real_tree`,
`tests/test_invariants.py::test_stale_unenforced_candidate_warning_never_gates_exit_code`) went
red — 0 other regressions. That is **L192**'s lesson: an acceptance test that asserts a
LIVE-DOCUMENT advisory fires binds the gate to that document's mutable content. The remediation
pass has since applied the split (absence-of-effect on the real tree, TEXT on the frozen fixture),
so today's green no longer depends on the queue being non-empty.

**TRUE final gate, taken after the LAST edit of the run:**

```
python -m pytest -o addopts="" -q      -> 2159 passed in 1152.67s (0:19:12), 0 failed  (EXIT 0)
python scripts/invariants.py --full    -> exit 0, "invariants: all green"
git status --porcelain -- tape/ paper/ -> (empty)
```

`invariants --full` carries pre-existing non-gating advisories only, plus the stale-marker
advisory reporting `Extraction reached 0 of 2 open UNENFORCED row(s) (21 formally disposed via
`DISPOSES:`)` at that time.

## Paper sub-pass (protocol step 9)

`SHADOW_REGISTRY` non-empty (1 entry, `s14_ladder_underwriting`, `dead ✗` — paper-infra
validation, NOT edge evidence). `python3 scripts/paper_pass.py` over committed tape:
**0 processed, 154 deferred(caps), 266 deferred(coverage), 146 already-in-ledger**.
`daily_summary()`: `paper: 0 open position(s), 1132 settled contract(s), realized P&L $+20.06,
cash $+20.06, open notional $0.00`. No new ledger lines (idempotent re-run — the day's
`MAX_DAILY_ORDERS` budget was already spent by the earlier run today); `git status` shows nothing
under `paper/`.

## Final fix — the binding gate had become a hostage of lesson PROSE

The L152 repair described above shipped, inside `tests/test_stale_unenforced_advisory.py`, a test
that asserted **against the LIVE ledger** that a named set of rows contains pipe characters and
that *no other row does*. That is an assertion about **prose**. It went red twice in one day and
forced a kb-distiller to **reword its own lesson text** to get the gate green — the gate editing
the knowledge it exists to protect. This is the same shape as **L192** and **L200** item (2),
recurring inside the fix for **L152**.

**What changed.** Every content-enumerating assertion was moved onto a second frozen fixture,
`tests/fixtures/lessons_pipe_split_2026-07-27.md` — **49** rows, byte-identical copies: all **14**
misparsing rows **plus** a **35**-row representative sample of correctly-parsing rows (every
immediate neighbour of a misparsing row, the **L188** `DISPOSES:` row, a 1-in-20 spaced sample
across the ledger, and the first and last rows). Freezing only the failures would have proved "the
naive rule breaks these" while dropping the anti-tautology half, "and it agrees everywhere else"
(**L202**).

This fixture is **deliberately NEVER identity-checked against the live ledger.** Such a check would
re-couple the binding gate to live prose and recreate the exact defect being fixed, one level up.
It is a snapshot of a moment, not a mirror; it is expected to diverge from `kb/lessons/00-lessons.md`
as the ledger grows, and that divergence is correct.

**The live-tree coverage is now purely STRUCTURAL** —
`::test_live_ledger_is_wholly_parsed_and_never_truncated`: nothing dropped, split lossless, every
enforcement cell starts at the head of the 5th cell and runs to end-of-row, `n_rows >= 190`. The
identical contract is re-run over the frozen fixture
(`::test_frozen_pipe_fixture_satisfies_the_same_structural_contract`), which is what shows the live
check is a real constraint and not a vacuous one that only ever sees well-behaved rows (**L204**).

**Proven, not argued.** Five rows covering every pipe shape — backslash-escaped, code-span,
escaped inside the enforcement cell, bare unescaped, and a `DISPOSES:`-carrying mixed row — were
appended to a **scratch copy** of the ledger. The new structural check stays green on all five;
the retired enumeration test fails on all five.

**Two further findings from the same fix.** (a) The structural contract was first written with
`len(fields) == 7`, which would have reddened on a bare unescaped pipe — a shape
`_parse_lesson_rows` handles correctly *by design*. A guard stricter than the parser it guards
re-creates the defect one abstraction down; the adopted floor is the parser's OWN admission
threshold, `>= 6` (**L203**). (b) Four `::test_name` node ids in that file are cited as enforcement
evidence by ledger row TEXT, and the agent that owns `tests/` may not edit `kb/` — so a rename made
in the test lane creates a dangling citation nobody in that lane can repair. Grep `kb/`,
`findings/` and `LOOP-QUEUE.md` before renaming a test (**L205**, filed `UNENFORCED`).

**Residual, recorded and not fixed.** `tests/test_invariants.py:748`
(`::test_stale_unenforced_candidate_real_tree_func_matcher_is_clean`) still asserts
`by_matcher["func"] == 0` on the live tree, so a future genuinely-open `**UNENFORCED**` row whose
enforcement column backticks a function-with-parens name that already exists in the tree would red
the gate. That is a **different** coupling — to the tree's symbol table, not to the document's
prose — and materially narrower, but it is the same family. Verified green against all five
mutation rows. Filed as **L207**, `UNENFORCED`.

## Lessons filed

**L188** (formal disposition of all 21 rows, carrying the `DISPOSES:` marker), **L189** (a
detector reporting 0 issues must publish its RECALL), **L190** (a queue only a machine can close
needs a machine-readable close marker, and precision requirements have publishable recall costs),
**L191** (a tape-pinned acceptance test must name the exact `dt=` day-slice its number was
measured over), **L192** (an acceptance test asserting a live-document advisory FIRES binds the
gate to that document's content — filed `UNENFORCED`; described at the time as "the queue's one
genuinely-open row", which **L193** retracts: it was one of two).

Filed after the verifier round: **L193** (formal correction of L188 — the 21-row audit stands, the
"queue is empty" conclusion is falsified, true open queue = `L145` + `L192`), **L194** (a markdown
ledger row is not `str.split("|")`; `cols[-2]` is the seductive wrong fix), **L195** (match the
marker's SHAPE, not one spelling), **L196** (two independent invisibilities can hide the same row
twice — verify the extraction path before quoting the count), **L197** (emitted evidence must
claim only what the matcher showed; L76 as the worked counterexample), **L198** (a supersession
grammar matching zero existing rows is a claim about the future), **L199** (correction of the gate
line, the 49-tests figure and the scope of "7 of 21"), **L200** (the three flagged-not-fixed items,
tier `UNENFORCED`). See `kb/lessons/00-lessons.md`.

Filed after the run's final code fix (§ *Final fix*): **L201** (`test`, a regression test may pin a
live document's STRUCTURE, never its ENUMERATION), **L202** (`test`, freeze the negative population
too), **L203** (`test`, never assert stricter than the parser you guard), **L204** (`test`,
parameterise a live-tree assertion body on its path so "would a future append red this?" is
executable), **L205** (`UNENFORCED`, grep for `::test_` citations before renaming a test),
**L206** (`protocol`, the suite count is **2159** and the file collects **69** — correcting L199's
2155/65), **L207** (`UNENFORCED`, the live-tree `func` matcher residual).

**The open `**UNENFORCED**` queue is NOT empty:** `L145`, `L192`, `L200`, `L205`, `L207`.

## Two-agent verdict rule

No registry status flip, no bootstrap CI, no kill decision — so the rule is N/A by its own terms.
The ledger-disposition and recall claims are nevertheless kb-destined, so they were produced by
one agent and put through an **independent `verifier` round — which REFUTED several of them**
(§ Verifier round). The corrected state, not the original claim, is what is recorded here and in
the ledger. The 7-of-21 recall figure is **fixture-scoped**, not a live-ledger property.
`kb/strategies/00-index.md` is unchanged: **0 proven edges**.
