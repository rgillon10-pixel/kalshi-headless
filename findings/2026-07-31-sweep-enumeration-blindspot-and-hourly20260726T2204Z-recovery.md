# Stranded-tape sweep: L217's family allowlist left 57.8% of branches unverified — closed, plus a 1,271-line recovery

**Date:** 2026-07-31 · **Run:** research loop, IDLE RUN, idle-run policy (a) (`UNENFORCED` → test)
**Verdict class:** TOOLING + DATA-RECOVERY. **No registry flip, no bootstrap CI, no kill decision** —
the two-agent verdict rule is N/A by construction (same posture as L156/L168/L172/L211/L215/L217).

## 1. What was measured

`python3 scripts/tape_branch_sweep.py` (LOOP-QUEUE.md step 0b), full unfiltered pass over all
**218** remote `tape/*` heads, run twice on the same `HEAD` (`6618cf3`) — once before this run's
code change and once after.

### Before

```
218 branch(es) checked against HEAD
  30 fully contained + verified
  48 contained via capture_id-level check only (L216)
 126 no problem found but NOT FULLY VERIFIED (>=1 file skipped by the size guard, no signal at all)
  14 carry line(s) or capture_id(s) genuinely MISSING from HEAD
```

**126 of 218 branches (57.8%) had no containment check of any kind.** Every one of them was
blocked by the same thing: `scripts/tape_branch_sweep.py::per_file_containment` gated its
capture_id-set fallback on a hard-coded allowlist,

```python
family = rel_file.split("/", 1)[0]
if family in BULK_CAPTURE_ID_FAMILIES:   # {orderbook_depth, universe_sweep, sports_pairs, weather_books}
```

and the oversized files actually blocking those 126 branches were in families that are not on it:

| family blocking the skip | branches affected |
|---|---|
| `crypto_hourly` (dt=2026-07-04/05/06/07/11/12/13/14/29) | 121 |
| `econ_prints` (dt=2026-07-13/14) | 5 |
| `anomalies` (dt=2026-07-21) | 1 |

All three carry `capture_id` and answer the check perfectly well. Verified live **before** touching
the gate, by calling `capture_ids_in_blob` directly:

| file | branch ids | HEAD ids | missing |
|---|---|---|---|
| `tape/crypto_hourly/dt=2026-07-14.jsonl` (8,376,187 B on `tape/burst-20260714T120659Z`) | 116 | 143 | **0** |
| `tape/econ_prints/dt=2026-07-14.jsonl` (9,830,255 B, same branch) | 137 | 137 | **0** |
| `tape/anomalies/dt=2026-07-21.jsonl` (2,108,558 B on `tape/20260721-hour9-stray-capture`) | 20 | 21 | **0** |

So the exclusion was purely nominal: the families were skipped for not being on a list, not for
lacking the field the check needs. This is L216's defect reproduced one layer up inside L216's own
fix — see `kb/lessons/00-lessons.md` **L245**.

## 2. The change

`per_file_containment` no longer consults any family list. The capture_id-set check is **attempted
on every oversized file**, and the blob's own content decides whether it applies: a branch-side
extraction yielding zero capture_ids still falls back to the honest size-guard skip (the exact
"no signal is never a clean bill of health" semantics L217 already relied on — that is what makes
the derivation safe to universalize). `BULK_CAPTURE_ID_FAMILIES` survives only as an observational
record of families measured above `DEFAULT_MAX_FILE_BYTES` (it is cited by name in L217 and in
`findings/2026-07-28-stranded-tape-recovery-hourly20260727T1303Z-bulk-family-blindspot.md`, so it
must stay importable and factually current); it was extended to the 7 now-measured families and is
read by nothing.

Four new tests in `tests/test_tape_branch_sweep.py::TestBulkCaptureIdCheck` pin the behaviour. The
load-bearing one is `::test_constant_is_not_consulted_by_the_containment_gate`, which parses the
module with `ast` and asserts there is **no `ast.Load` of `BULK_CAPTURE_ID_FAMILIES` anywhere** —
pinning the absence of the read is the only assertion that stops the enumeration coming back a
third time. `::test_capture_id_check_fires_for_family_absent_from_constant` builds a real temp git
repo with a `tape/brand_new_family/` day-file and asserts it is capture_id-checked, not skipped;
`::test_oversized_file_without_capture_id_still_skips_honestly` asserts the no-signal fallback
survived the widening.

### After (same 218 branches, same HEAD)

```
218 branch(es) checked against HEAD
  30 fully contained + verified
 174 contained via capture_id-level check only (L216)
   0 no problem found but NOT FULLY VERIFIED
  14 carry line(s) or capture_id(s) genuinely MISSING from HEAD
```

Unverified **126 → 0**. Wall-clock for the full 218-branch sweep: **5m09s**.

**The genuinely-missing count did not move (14 → 14).** That is the honest headline: the newly
visible 126 branches were all clean. This closed a blind spot; it did not uncover new loss. The
hole had to be *measured* rather than assumed empty, and the measurement came back empty.

## 3. Triage of the 14 genuinely-missing branches

Each hit was inspected directly (bytes shown, not asserted).

**(a) 8 branches × `tape/cloud-env-check.md`, 2 lines each** — `hourly-202607100655Z`,
`hourly-20260710T0955Z/T1054Z/T1155Z/T1254Z/T1556Z/T1656Z`, `hourly-20260716T1856Z`.
**FALSE POSITIVE, unchanged verdict.** `diff` of branch vs HEAD shows HEAD is strictly the richer
document: the branch's two "missing" lines are a condensed provenance header
(`` `run` · 2026-07-02, refreshed 2026-07-09 (Q0b unblock) ``) and an un-suffixed heading, both
superseded on `main` by a 3-line provenance block and a longer heading, with HEAD additionally
carrying a whole 22-line `## Re-verify (Q0b) — 2026-07-03T00:08Z — UNBLOCKED` section the branch
lacks. A prose documentation rewrite, not append-only tape. **Left untouched.**

**(b) 5 branches × `tape/anomalies/dt=2026-07-18.jsonl` (3) + `tape/econ_prints/dt=2026-07-18.jsonl`
(3)** — `hourly-20260722T0357Z/T0403Z/T1256Z`, `hourly-20260723T0359Z/T0715Z`.
**FALSE POSITIVE, unchanged verdict, re-confirmed by direct inspection this run rather than
inherited from prior triage.** The three "missing" lines in each file are literally:

```
'<<<<<<< HEAD'
'======='
'>>>>>>> 58145d7 (tape: hourly pass 2026-07-18T09:30:28Z (vps))'
```

i.e. the L142 git conflict-marker corruption, already repaired on `main`. Recovering them would
re-inject the corruption. **Left untouched.**

**(c) `tape/hourly-20260726T2204Z` (`ad9e7a36a8ec`) — GENUINE, recovered.** Two whole captures
absent from `main`:

| file | capture_id | lines recovered | of those already byte-present in HEAD |
|---|---|---|---|
| `tape/orderbook_depth/dt=2026-07-26.jsonl` | `20260726T215542Z` | **729** | 0 |
| `tape/weather_books/dt=2026-07-26.jsonl` | `20260726T220100Z` | **542** | 0 |

**1,271 lines total** of real L2 depth tape (`price_source_tag` on these families is the collector's
own `real_ask`/book fields; nothing here is a fill or a P&L claim). Note the provenance: a
2026-07-27 run already recovered 134 *non-bulk* lines from this same branch, but on that date both
of these files were size-guard-skipped outright — the capture-level loss only became visible once
the capture_id path existed. Union-appended at EOF, original bytes preserved.

Post-append verification, all three checks green on both files: (i) **pure append** — the
pre-existing content is a byte-exact prefix of the new file (`new[:len(old)] == old`, so no line was
rewritten or reordered); (ii) **every appended line parses as JSON** and carries the expected
`capture_id`; (iii) **0 duplicate lines** in the resulting file.

## 4. What this does NOT claim

- No edge, no CI, no P&L, no registry change. Still **0 proven edges**.
- The capture_id check remains coarser than a line-level proof (a matched `capture_id` does not
  prove every byte of that capture is identical) — L217's deliberate, documented trade, unchanged.
- The 174 capture_id-verified branches are verified *at capture granularity*, and the report keeps
  that visibly distinct from the 30 line-level-verified ones. Neither number licenses deleting a
  branch on its own.
