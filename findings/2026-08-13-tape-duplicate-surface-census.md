# The tape duplicate-capture surface, fully mapped — and the third class was never measured

2026-08-13 · research loop, IDLE RUN, idle-run policy (c) (data-quality deep-dive, widened
from one family to the whole duplicate surface) · main context, read-only over committed
tape, offline. **No strategy claim, no P&L, no fee model, no bootstrap CI, no registry
change** — two-agent rule N/A (data-quality characterization + a detector build, not a
verdict; same posture as L104/L110/L118/L126/L127/L137/L287/L318).

## Why this, why now

Full Q0–Q56 rescan at current-status (10th consecutive idle-adjacent run; this morning's
`kalshi-edge-hunter` round #29 independently found 0 eligible and registered 0). Idle-run
policy (a) re-derived with the ledger's own scanner rather than trusted: 9 open `UNENFORCED`
rows (`L213`/`L221`/`L222`/`L282`/`L319`/`L320`/`L321`/`L323`/`L338`), each either Ryan/VPS
write-path-gated, a workflow-level repair, or "not statically assertable" by its own cell
text — empty for a cloud research run, same as the previous two firings. Policy (b) has no
target (no unopened calendar gate). Policy (c) taken.

The family-by-family audits are getting thin (most families now have one), so this run
audited a *surface* instead: **duplicate captures**, the defect class three separate lessons
have already recorded on this repo's tape (L281, L282→L285, L210→L218). The question was
simply: *is the surface fully covered, or is there a class no detector can see?*

## The three incumbent detectors and their blind spots

| detector | lesson | finds | cannot see |
|---|---|---|---|
| `invariants._tape_duplicate_line_issues` | L285 (corrects L282) | BYTE-IDENTICAL lines, repo-wide | anything whose payload differs at all — its own docstring says so |
| `tape_gap_monitor.duplicate_capture_id_collisions` | L218 (disposes L210) | same logical item under one `capture_id` at >1 `captured_at` | anything stamped at ONE instant (it is candidate-gated on `n_distinct_captured_at > 1`) |
| `invariants._orderbook_depth_duplicate_capture_issues` | L282 (corrects L84) | repeated `(capture_id, ticker)` | every family except `orderbook_depth` |

The uncovered class falls exactly between the first two: **same `capture_id`, same
`captured_at`, same logical row identity, DIFFERENT payload** — one pass emitting one item
twice with two different answers. It is the most damaging of the three: two contradictory
truths stamped identically, so no consumer can pick between them, and any per-row statistic
(population size, a bootstrap unit's weight) is silently inflated. It had never been measured.

## Census (2026-08-13, all committed tape)

Scope: **429 files, 2,024,482 rows**, of which **2,003,675 rows in 19 capture families**
(families carrying `capture_id`); the other 7 families are derived caches / one-shot
historical pulls with no pass identity.

1. **Byte-identical class (L285's lane) — reproduced exactly.** An independent by-hand census
   this run found **1,358** duplicate rows, all on `dt=2026-07-28`, split
   `orderbook_depth 1,093 · sports_pairs 228 · perp_tape 17 · polymarket_macro_pairs 16 ·
   crypto_hourly 2 · hyperliquid_funding 2` — digit-for-digit L285's six-family incident
   (commit `10681abe` re-appending that morning's pass). **0 rows on any other day.**
2. **`capture_id`-collision class (L218's lane) — reproduced exactly.** **7** collided item
   groups across **3** families: `perp_tape` `20260717T010032Z` (a `--backfill-funding`
   one-shot vs the scheduled pass, differing in `mode`/`n_prints`/`start_ts`), `econ_prints`
   `20260716T092842Z` (all 5 series written twice, 414 ms apart), `anomalies`
   `20260714T091958Z` (two summary rows 84 ms apart). Root cause re-confirmed at source:
   `capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")` at 21 mint sites across 16 `collection/` modules — one-second resolution,
   no process or random component, so two invocations starting in the same second are
   indistinguishable by design.
3. **Within-instant class (the seam) — first measurement: `0` instances, repo-wide.**

So the duplicate-capture surface is now fully mapped and fully accounted for: every duplicate
row on committed tape belongs to one of two known, documented incidents, and the previously
unmeasured third class does not occur.

## The load-bearing methodological finding: the obvious key reuse is UNSOUND

The first attempt at (3) reused `tape_gap_monitor.ITEM_IDENTITY_FIELDS` — the coarse
"most-specific-field-wins" tuple L218 already uses. That key is **sound for L218's question
and unsound for this one.** L218 additionally requires two distinct `captured_at`, and *that*
requirement is what makes a coarse key safe there: a repeated coarse key across two instants
implies a re-walk. Drop it and the same key false-positives catastrophically — it reported
**97 files**, including **145,855 "extra rows"** in a single `kalshi_trades` day, because
every executed print of a ticker inside one pass shares `('ticker', ...)`. The real identity
of a `kalshi_trades` row is `trade_id`. Two further false-positive shapes appeared in the same
pass: `polymarket_cpi_pairs` (many buckets per `series`) and `sports_history` (**137** false
pairs, because the family mixes `sports_history_kalshi.v1`, keyed on `event_ticker`, with
`sports_history_espn.v1`, which has none — every ESPN row collapsed onto `event_ticker=None`).

**A within-pass row identity is a per-family semantic judgment, and a guessed key is worse
than no check.** That is why the enforcement below is a fail-closed declaration ratchet, not
a bare assert — the same shape as L319's self-tape-read triage and L323's tie-break triage.

## What was built (this run)

- `scripts/invariants.py::TAPE_ROW_IDENTITY_KEYS` — 19 declared families, each with the
  fields that identify ONE row inside ONE pass (`()` is a real declaration meaning "one row
  per pass", e.g. `anomalies`), plus `NON_CAPTURE_TAPE_FAMILIES` — 7 derived/cache families
  with the reason each is not capture tape.
- `scripts/invariants.py::_tape_row_identity_declaration_issues` /
  `tape_row_identity_declaration_failure` — **GATING**, wired into `--full`. A tape family
  carrying `capture_id` that appears in neither table fails the gate: a new collector cannot
  land its family until someone writes down what one of its rows means. Live-fired against
  the real tree (removing `universe_sweep`'s declaration in-process yields exactly
  `['universe_sweep']`).
- `scripts/invariants.py::_tape_within_instant_duplicate_issues` /
  `tape_within_instant_duplicate_warning` — the seam census, **non-gating** (a duplicate
  already on append-only tape cannot be un-committed; gating on a historical fact would halt
  the loop forever — the L218/L285 posture), `except BaseException`-wrapped per L156 DEFECT-1.
  It deliberately reports NEITHER adjacent class, so each defect keeps exactly one owner.
  The within-pass-sequence exemption (`capture_seq`/`capture_mono_ns`/`round_index`) is
  imported from `tape_gap_monitor`, never re-declared (L100), and applies structurally, so a
  future burst collector inherits it with no edit.
- **21 tests** in `tests/test_invariants.py`, including: the class firing; both adjacent
  classes staying silent; the coarse-key false positive reproduced and then prevented by the
  declared key; the empty-key semantics; the structural burst exemption; malformed/identity-
  less rows skipped rather than merged; and two HARD real-tree acceptance tests (every real
  capture family is declared; the two tables are disjoint and non-empty).

## Honest limits

- The declaration **gate** samples the first 200 lines per file (stated in-code). A family
  whose only `capture_id`-bearing rows sit deeper than that in *every* file would be missed by
  the gate; the advisory's full parse is the backstop.
- A 0-issue census is evidence about *this* class only — the L155 precision-vs-recall
  discipline that L285's own docstring states, now stated for its successor too.
- The census costs ~36 s cold over the current tape. Measured end-to-end: `--full` ran
  **3m17s before** this change and **3m14s after** — i.e. within noise, because the extra
  full-tape read is absorbed by the OS page cache on a warm run. Treat ~36 s as the honest
  cold-cache cost; it scales linearly with tape and will need revisiting if `--full` becomes
  a bottleneck.
- Nothing here is edge evidence. It is EV-protection: the class it closes is one of the few
  that can inflate a bootstrap population without leaving any other trace.
