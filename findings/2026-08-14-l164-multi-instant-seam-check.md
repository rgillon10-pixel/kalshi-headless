# L164's remaining half: multi-instant burst seam protection + a mechanical check

`2026-08-14` · research loop, IDLE RUN, idle-run policy (a) (`UNENFORCED` lesson → test) ·
**no registry flip, no bootstrap CI, no P&L, no kill decision**

**Verdict class: TOOLING + DESCRIPTIVE.** This run persists **no price of any kind**, so no
`price_source_tag` applies and nothing here is verdict-class. It is pure scheduling arithmetic over
one-shot burst-capture windows.

**Two-agent status: REDUNDANCY ONLY, NOT VERIFIER-CONFIRMED.** No `Task`/subagent tool exists in
this harness (`No such tool available: Task` — the L287/L288/L290/L291/L295/L308/L313/L325/L349
precedent), so no independent `verifier` was dispatchable. The sanctioned redundancy fallback ran
instead (`scripts/l164_seam_rederive.py`, below) and is reported as redundancy, never as
verification: it is a second implementation by the same author, which catches representation and
off-by-one errors but cannot catch a shared misconception. Because nothing verdict-class was
produced, nothing needed the two-agent rule and nothing was flipped.

## 1. What was open

**L164** (2026-07-25) recorded that chunking a one-shot burst window to bound sandbox-death data
loss introduces its own failure mode: the commit+push+verify pause between two chunks can land on
the single most decisive instant in the window. A verifier caught exactly that in the FOMC plan
(the uniform `[14]*6` seam straddled the 18:00:00Z statement), and it was fixed BY HAND with
`[16, 14, 14, 14, 14, 12]`.

A 2026-07-26 follow-up built `--protect` for **one** instant. L164's enforcement cell named two
things it deliberately left out, and both were still open on 2026-08-14:

- **more than one protected instant** — "e.g. an FOMC presser Q&A window as well as the statement
  itself";
- the fact that a plan could be **generated** but never **checked**. `ops/burst_capture_chunked.md`
  still instructed every future one-shot to "MANUALLY check whether any chunk boundary in that
  sequence falls within one `--interval` of any of them ... **the tool will not do it for you**".

## 2. What was built

`scripts/burst_chunk_plan.py` (additive — no existing function's behavior changed):

- `seam_offsets_seconds(seq, interval)` — each INTERNAL seam as the `(last tick of chunk k, first
  tick of chunk k+1)` elapsed-second pair. The pair, not a single boundary, is the honest object:
  the whole span between the two adjacent ticks is at risk.
- `seam_violations(seq, interval, instants, margin)` — L164's rule made mechanical, and **two-sided**:
  an instant is safe iff its distance to *every* seam interval exceeds the margin, on either side.
  (The single-instant grower only ever pushes a seam LATER, so it implicitly assumed the instant
  precedes the seam; an instant landing just AFTER a seam was equally unprotected and unreported.)
- `chunk_max_ticks_sequence_protecting_multi(...)` — N protected instants, growing **only** the
  chunk whose own trailing seam is violated.
- CLI: `--protect` is now repeatable; `--verify-sequence` checks an already-written sequence and
  **exits 2** on a violation; every protect-mode run self-checks its own emitted plan through the
  separate checker path.

`scripts/l164_seam_rederive.py` — the redundancy re-derivation. It imports nothing from
`burst_chunk_plan` (pinned on the AST, not on prose) and works on a deliberately different
representation: absolute `datetime` ticks materialized per chunk invocation, seams read off the
materialized tick lists rather than from a cumulative-index formula, and its own string-slicing ISO
parser (pinned equal to `core.timeutil.parse_iso_utc` on real timestamps including leap/century
days) instead of the shared helper.

## 3. Measured result 1 — the committed FOMC recipe is seam-safe for the instant it was never checked against

The hand-verified `[16, 14, 14, 14, 14, 12]`, window `2026-07-29T17:40:00Z → 19:45:00Z` @ 90 s,
against BOTH the 18:00:00Z statement and the 18:30:00Z presser (the standard statement + 30 min Fed
schedule — the second instant L164's own text names):

| instant | offset | lands in | nearest seam | margin | safe @ 90 s |
|---|---|---|---|---|---|
| statement 18:00:00Z | t+1200 s | chunk 1 | after chunk 1 (18:02:30Z–18:04:00Z) | **150 s** | yes |
| presser 18:30:00Z | t+3000 s | chunk 3 | after chunk 2 (18:23:30Z–18:25:00Z) | **300 s** | yes |

`seam_violations(...) == []` and the independent re-derivation returns `all_safe: true`, agreeing
on every seam position to the second. **The hand recipe holds for the second instant too** — that
was luck, not design (nothing in the 2026-07-26 build checked it), and it is now regression-pinned
rather than left to be rediscovered.

The new multi-instant generator, given both instants, **independently reproduces the same
`[16, 14, 14, 14, 14, 12]`** — a generator/checker/hand-derivation triple agreement.

## 4. Measured result 2 — the naive uniform plan's defect, reproduced mechanically and sharpened

Both implementations put the naive `[14]*6` first seam at **17:59:30Z–18:01:00Z**, reproducing the
2026-07-25 verifier's hand observation exactly. The re-derivation adds a sharper statement of the
same fact: under that plan the statement instant's `containing_chunk` is **`None`** — **no chunk
captures 18:00:00Z at all**, it falls inside the dead pause. L57 established an entire burst's
signal can live in one release-instant capture.

## 5. Measured result 3 — a real defect the generalization exposed in the shipped single-instant form

`chunk_max_ticks_sequence_protecting()` grows **chunk 1** no matter where the instant sits, so an
instant in a later chunk inflates chunk 1 to reach it — inflating the very worst-case loss the
chunking exists to bound. Measured on this module's own committed test cases (all four sequences
are seam-safe and cover the identical window; the difference is purely the exposure):

| case (total/chunk/interval, protect) | single-instant seq | max chunk | multi-instant seq | max chunk |
|---|---|---|---|---|
| FOMC 125/20/90 @ 20 min | `[16,14,14,14,14,12]` | 16 (24.0 min) | `[16,14,14,14,14,12]` | 16 (24.0 min) |
| WC-final-shaped 155/20/120 @ 25 min | `[15,10,10,10,10,10,10,3]` | 15 (30.0 min) | `[10,10,10,10,10,10,10,8]` | **10 (20.0 min)** |
| later-chunk 100/15/60 @ 40 min | `[43,15,15,15,12]` | **43 (43.0 min)** | `[15,15,15,15,15,15,10]` | **15 (15.0 min)** |
| short 37/10/45 @ 5 min | `[14,14,14,8]` | 14 (10.5 min) | `[14,14,14,8]` | 14 (10.5 min) |

In the third case a caller asking for 15-minute chunks silently got a **43-minute** first chunk —
2.9× the requested worst-case loss, from a tool whose entire purpose is bounding that loss. The
single-instant function is **NOT changed** (the FOMC recipe is regression-pinned to it, and the two
agree whenever the instant falls inside chunk 1); it is documented as superseded for general use.

## 6. What is still not automated (stated, not papered over)

**Deciding which instants are decisive for a given event remains human judgment.** The tool protects
the instants it is given and cannot know one was forgotten. That half of L164 stays `UNENFORCED`
and is genuinely not assertable, the same terminal posture as L6/L27/L28.

Also idealized and stated in both modules: the zero-overhead seam model. A real seam additionally
carries the commit+push+verify wall-clock pause, which only WIDENS the gap — every margin above is
therefore an upper bound on safety and a lower bound on risk.

## 7. Why this matters beyond tooling

S17's next burst leg is BLOCKED by the Q19 verifier's standing condition: the window must be
**contiguous across the release instant**, or the honest verdict is `kill-on-untestability` rather
than a kill on sub-tick evidence (`findings/2026-07-29-s17-burst-fomc-q19.md`). The 2026-07-29 FOMC
burst failed that condition with a 720.000196 s seam sitting on 18:00:00Z. This run does not open
that gate — the gate is a live-capture question — but it removes the hand-verification step that
stood between a future burst plan and a provable contiguity claim, and makes the claim checkable
after the fact from the sequence alone.

## 8. Artifacts

- `scripts/burst_chunk_plan.py` (additive), `tests/test_burst_chunk_plan.py` (+31 tests, 36 → 67)
- `scripts/l164_seam_rederive.py`, `tests/test_l164_seam_rederive.py` (+21 tests)
- `reports/l164_seam_check.json` (both checks + the inflation table, re-runnable)
- `ops/burst_capture_chunked.md` ("Applying this pattern to future one-shots" rewritten)
- `kb/lessons/00-lessons.md` (L164 enforcement cell moves per the L152 own-row-update rule; new L350)

Re-run:

```
python3 scripts/burst_chunk_plan.py --start 2026-07-29T17:40:00Z --until 2026-07-29T19:45:00Z \
  --interval 90 --chunk-minutes 20 --protect 2026-07-29T18:00:00Z --protect 2026-07-29T18:30:00Z
python3 scripts/l164_seam_rederive.py --start 2026-07-29T17:40:00Z --interval 90 \
  --sequence 16,14,14,14,14,12 --protect 2026-07-29T18:00:00Z --protect 2026-07-29T18:30:00Z
```
