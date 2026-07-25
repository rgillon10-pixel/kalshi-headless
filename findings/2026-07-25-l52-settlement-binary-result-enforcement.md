# L52 enforcement: shared binary-settlement helper + hand-rolled-comparison advisory

**2026-07-25, research loop, idle-run policy (a).**

## The gap

L52 (`kb/lessons/00-lessons.md`, 2026-07-14) records that Kalshi sports settlement results are
**not always binary**: Q26's live pull of `fetch_kalshi_settled` over **458 settled markets in 7
sports series returned 8 with `result:"scalar"`** (~1.7%), not `result ∈ {"yes","no"}`
(`findings/2026-07-14-ofi-depth-imbalance-s22-verdict.md`,
`scripts/q26_ofi_depth_imbalance_probe.py`). An unfiltered join silently injects those rows into a
yes/no hit-rate or P&L — typically booking each one as the losing side, because `result == "yes"`
is False for `"scalar"` just as it is for `"no"`. The failure is silent by construction: nothing
about a non-binary row looks wrong downstream, it just shifts the denominator and the sign.

L52's own enforcement column named what was missing: *"no shared settlement-join helper yet exists
to anchor a 'scalar-filter required' rule to."*

## The L106 reconciliation — why L52 was re-opened, and what was NOT overruled

This is the load-bearing section of this document. **L106 (2026-07-19) explicitly closed L52:**

> (iii) L52/L92's remaining "escalate to a static invariant" thread was inspected and found a FALSE
> START — `result == "yes"/"no"` is read WITHOUT an adjacent scalar guard in 9 legacy/verdicted
> scripts (`weather_rehab_s5.py`, `sports_clv_s7.py`, `longshot_fade_probe.py`,
> `q24_sports_longshot_maker_fillsim.py`, `q26_ofi_depth_imbalance_probe.py`,
> `q27_favorite_underpricing_fillsim.py`, `q28_s24_nearclose_fade_probe.py`,
> `q29_settlement_lag_probe.py`, `q30_draw_aversion_maker_probe.py`), so a gating scanner would
> false-gate frozen historical code and an allowlist of all of them is the L30/L19 dishonest-theater
> anti-pattern — L52 is honestly terminal (test-pinned at L92), SKIPPED, recorded so the next idle
> run does not re-attempt it.

**L106's reasoning was correct and is NOT overturned by this run.** Its objection is scoped
precisely to a **GATING** scanner, and every word of it still holds: a check that flips the exit
code on those sites would break the build over frozen, verdicted historical probes, and an
allowlist enumerating them all would be enforcement theater.

What shipped here is the **NON-gating advisory** form — the pattern established by
L109/L118/L126/L144/L150/L152/L156/L157/L160/L161. It needs no allowlist and it cannot false-gate:
the legacy sites are reported honestly to stderr and `python scripts/invariants.py --full` still
exits 0. The thing L106 rejected was not built; the thing L106 did not consider was. L106 also
predates the existence of any read-side helper to point offenders at, which is the other half of
why a re-open is honest rather than a re-attempt: the advisory's remediation text
(`core.settlement.filter_binary_settlements` / `binary_outcome`) did not exist on 2026-07-19.

A future run reading L106 should read this section before concluding L52 is closed *or* open: the
gating form remains closed-by-L106; the helper + advisory form is what this run delivered.

## The L92 nuance: write path vs read path

L92 (2026-07-17) claimed `collection/settlement_ledger.py` closed L52's shared-helper gap. Verified
against the file this run, the precise situation is:

- that module carries its own **private, local** `BINARY_RESULTS = ("yes", "no")` (~line 86);
- its scalar filter is **inline inside** `run()` (~lines 249-257) and `migrate_caches()` (~lines
  381-385), counting `n_scalar_dropped`.

So it centralized the **WRITE path** — what gets ingested into tape. It is genuinely the single
ingestion filter L92 says it is. But a downstream probe joining settlement data **cannot import a
classifier from it**: there is no exported predicate, only a private tuple and two inline `if`
blocks. `core/settlement.py` is the **READ path** helper that did not exist. L92's row is not
edited (append-only ledger); this is a scoping clarification, not a correction.

A consequence worth recording plainly: `tape/settlement_ledger/` is **100% binary — 10,605/10,605
rows across 2 files, `{no: 8235, yes: 2370}`, 0 non-binary** (command under `## Reproduce`,
measured 2026-07-25) precisely **BECAUSE** the collector pre-filters scalars upstream. A downstream
reader who samples that tape and concludes "Kalshi settlement is always binary" is generalizing a
**collector artifact** to the API, where the observed rate is 8/458. The acceptance test therefore
asserts `kept_fraction == 1.0` as *"the pre-filter still holds"*, never as *"the world is clean"*.

## What this run built

### Layer 1 — the shared read-side helper: `core/settlement.py`

Public API: `BINARY_RESULTS`, `VALID_BINARY_RESULTS`, `KNOWN_NON_BINARY_RESULTS`, `MISSING_SENTINEL`,
`normalize_result`, `is_binary_result`, `binary_outcome`, `require_binary_result`, the frozen
dataclass `BinaryFilterReport` (`total`/`kept`/`dropped`/`dropped_by_result`/`kept_fraction`/
`summary()`), `filter_binary_settlements(rows, *, result_key="result")`, and
`filter_binary_results_map(results)`.

Design decisions that carry the lesson:

- **Strict ALLOW-list.** `is_binary_result` tests `normalize_result(x) in VALID_BINARY_RESULTS`; it
  never tests absence from `KNOWN_NON_BINARY_RESULTS`. An unknown future result value is therefore
  non-binary **by default** — L52's bug with a new string in it cannot recur. `KNOWN_NON_BINARY_RESULTS`
  (`{"scalar"}`) is documentation only and is never consulted by the classifier.
- **`binary_outcome` returns `None`, never a fabricated `0`,** for a non-binary value. Returning 0
  is exactly the silent mis-booking L52 describes.
- **`dropped_by_result` keys the RAW un-normalized value** on purpose — diagnostic fidelity: you
  want to see what the venue actually sent, not its normalized form. Absent/`None` is counted under
  `MISSING_SENTINEL`; absent is not binary.
- **`"void"` was deliberately NOT invented.** `grep -rn '"void"' kb/ collection/ scripts/ tape/`
  returns 0 hits as of 2026-07-25, so adding it would be speculating about the venue. The allow-list
  design means we do not need to guess: any label we have not seen is non-binary already.

### Layer 2 — the non-gating advisory: `scripts/invariants.py`

`_handrolled_binary_result_sites()` / `handrolled_binary_result_warning()`, wired into `main()`'s
whole-tree (`--full`/default) branch **only** — never `--pre-edit-hook`, never `--db` — inside an
`except BaseException` wrapper, stderr-only, and **never appended to the gating `failures` list**.
Adds `import ast` and `HANDROLLED_BINARY_RESULT_EXEMPT = ("core/settlement.py",)` (a whole-file
exemption of the sanctioned helper itself).

Detection: a line carrying an `==`/`!=` against a `'yes'`/`'no'` string literal (either operand
order) **AND** a settlement token (`result`/`results`/`settle*`/`outcome`) on the **same line**. A
file is exempted wholesale if it contains a `"scalar"` literal, an explicit `in`/`not in` over a
2-element yes/no collection, or any reference to `core.settlement`'s names. Docstring lines are
excluded via an `ast` pass (Module/Class/Function leading `Expr(Constant str)` spans); comment lines
and everything under `tests/` are skipped.

## Live result on the real tree (2026-07-25)

The advisory reports **6 sites** and `python scripts/invariants.py --full` still exits **0**:

```
scripts/s14_ladder_fillsim.py:119
scripts/s19_wing_fade_fillsim.py:142
scripts/seed5_funding_prior_probe.py:180
scripts/weather_rehab_s5.py:508
scripts/weather_rehab_s5.py:610
scripts/weather_rehab_s5.py:616
```

The first three are all the same MECE-ladder shape,
`winners = [k for k, v in results.items() if v == "yes"]`.

**These 6 scripts were deliberately NOT edited.** They are frozen, verdicted historical probes;
changing them would alter recorded results. That is precisely why this check is advisory rather
than gating — and precisely the situation L106 identified.

Precision evidence, both directions:

- Ten sibling probe scripts (`longshot_fade_probe.py`, `q24_*`, `q26_*`, `q27_*`, `q28_*`, `q29_*`,
  `q30_*`, `q37_*`, `s10_reachability_probe.py`, `sports_clv_s7.py`) are correctly **suppressed** as
  guarded.
- `execution/fill_models.py` lines 90, 180 and 350 compare a `side` against a `"yes"`/`"no"` literal
  — an **ORDER SIDE**, not a settlement result — and are correctly **not** matched, pinned by
  `test_acceptance_order_side_comparisons_are_not_reported`. Reproduce the count with
  `grep -n '"yes"\|"no"' execution/fill_models.py` (grepping only `"yes"` undercounts: line 350 is
  `order.side != "no"`). Same for `scripts/weather_rehab_s5.py:723` (`t["side"] == "yes"`).

## Test coverage

- `tests/test_settlement_binary_filter.py` — **61 passed**. Includes
  `test_regression_l52_unfiltered_hit_rate_differs_from_filtered` (a named regression test showing
  an unfiltered yes/no hit-rate **numerically differs** from the filtered one — the lesson is pinned
  by arithmetic, not by prose) and the HARD acceptance test
  `test_acceptance_1_l52_real_settlement_ledger_tape_is_all_binary` over the real committed
  `tape/settlement_ledger/*.jsonl`.
- `tests/test_settlement_result_advisory.py` — **64 passed**: 8 constructed positives, 17
  constructed negatives, 4 regression-pinned blind-spot **misses**, robustness cases including an
  unparseable file, 7 `test_acceptance_*` real-tree cases, and 7 exit-code / non-gating / offline
  pins.

Per L155, the constructed-positive and blind-spot corpora are the point: widening the rule later
must delete a pinned-miss entry **on purpose**, never by accident.

## Limitations and known blind spots

Both are stated in the advisory's own warning text and regression-pinned as misses:

1. **Settlement token on an earlier line than the comparison.**
   `scripts/probe_ladder_coherence.py:140` (`if res == "yes":`) is a **genuine unguarded settlement
   read** that this line-scoped rule does **not** report — the settlement token sits on a preceding
   line. Recorded as a known miss rather than papered over.
2. **File-level guard granularity.** A single `"scalar"` literal, yes/no membership test, or
   `core.settlement` reference **anywhere** in a file exempts **every other** hand-rolled comparison
   in that file. Ten scripts are suppressed this way; each suppression is a whole-file judgment, not
   a per-site one.

Non-comparison forms (`result.startswith(...)`, `match`/`case`, membership over a dynamically built
collection) are also not detected.

**A 6-site count is PRECISION evidence, not RECALL** (L155). It answers "does this rule fire only on
real hand-rolled settlement comparisons?" — it says nothing about how many such comparisons exist
that the rule cannot see. Recall is bounded only by the constructed-positive corpus, and the two
blind spots above are the measured holes in it.

Closing blind spot (1) needs a scope-aware dataflow pass, not a wider regex; widening the line
window would immediately pick up order-side comparisons and destroy the precision case.

## Reproduce

Real-tape settlement-result census (per L162, the command ships with the count):

```
python - <<'EOF'
import json, glob, collections
c = collections.Counter(); n = 0
files = sorted(glob.glob('tape/settlement_ledger/*.jsonl'))
for f in files:
    for line in open(f):
        line = line.strip()
        if not line: continue
        n += 1; c[json.loads(line).get('result')] += 1
print(len(files), n, dict(c))
EOF
```

→ `2 10605 {'no': 8235, 'yes': 2370}` (files `dt=2026-07-17.jsonl`, `dt=2026-07-22.jsonl`; zero
non-binary), measured 2026-07-25.

Tests:

```
python -m pytest -q tests/test_settlement_binary_filter.py tests/test_settlement_result_advisory.py
```

→ `125 passed` (61 + 64), measured 2026-07-25.

Advisory + gate:

```
python scripts/invariants.py --full; echo "EXIT=$?"
```

→ the 6-site advisory on stderr, `invariants: all green`, `EXIT=0`, measured 2026-07-25.

## Gates

`python scripts/invariants.py --full` → exit 0 (re-taken this run). Full `pytest -q` was run green
by the build half of this milestone; stated as a floor rather than re-quoted here per L162 — the
numbers verified directly in this pass are the two files above (**125 collected, 0 failures**) and
the invariants exit code.

## Scope

No strategy claim, no P&L, no bootstrap CI, **no registry change** — this is non-gating
infrastructure. The two-agent verifier rule does not apply, per the
L109/L118/L126/L144/L150/L152/L156/L157/L160/L161 precedent.
