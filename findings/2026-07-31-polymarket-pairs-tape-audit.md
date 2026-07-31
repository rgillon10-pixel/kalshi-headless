# 2026-07-31 — `tape/polymarket_pairs/` data-quality audit (first dedicated pass)

Idle-run policy (c) (LOOP-QUEUE.md v3): no queue item (Q0-Q48) was eligible this run — a full
Q0-Q48 rescan was already independently confirmed 0 TODO/IN-PROGRESS by two runs earlier
tonight (the 2026-07-31 ~03:2x UTC L222 idle run and the ~04:1x UTC edge-hunter nightly), and
every open UNENFORCED lesson row (L145/L213/L221/L222/L227) has its buildable half already
built, with the remainder genuinely Ryan-only or not statically assertable. So this run picked
policy (c): a dedicated data-quality deep-dive on `tape/polymarket_pairs/` — the World Cup
Kalshi<->Polymarket paired tape, the collector `S9`/`S17` and the 2026-07-15 "Polymarket is
now a TRADEABLE venue" regime change both depend on. No dedicated audit of this family existed
before today (weather_books, hyperliquid_funding, perp_tape, settlement_ledger,
polymarket_macro_pairs, and econ_prints all already have one). Produced by a `tape-auditor`
subagent; every number below was independently reproduced from the committed bytes and the
repo's own `scripts/tape_gap_monitor.py`, not taken on faith. Two-agent verdict rule N/A — this
is a data-quality audit plus a tool-correctness fix, not a registry flip/strategy CI/kill
decision (same posture as the perp_tape/settlement_ledger/polymarket_macro_pairs/econ_prints
audit precedents).

## Coverage

`tape/polymarket_pairs/` — 11 day-files, `dt=2026-07-04` … `dt=2026-07-15`, 424 distinct
passes (`capture_id`s), 6,369 lines, 2.9 MB. Per-day lines/passes: 04: 48/1 · 05: 1944/49 ·
06: 1604/50 · 07: 1128/49 · 08: 368/23 · 10: 102/9 · 11: 490/49 · 12: 213/45 · 13: 188/47 ·
14: 170/45 · 15: 114/57.

Two gaps, both already-known, neither new:
- **`dt=2026-07-09` absent** — the repo-wide 57h outage (`2026-07-08T11:00:16Z` →
  `2026-07-10T19:55:04Z`) that also blacked out `crypto_hourly`/`sports_pairs`/
  `polymarket_macro_pairs`/`orderbook_depth` that day. Not a `polymarket_pairs`-specific
  defect.
- **Silence since `2026-07-15T21:11:28Z` (369h to this audit)** — already classified
  `known_benign_silence` by `scripts/tape_gap_monitor.py`: the World Cup champion market
  resolved, and `collection/polymarket_pairs.py:354`'s `run()` writes nothing at all on a
  zero-match pass (`if lines:`). Its sibling `run_fed_decision` got the always-write-a-summary
  fix in the 2026-07-28 `polymarket_macro_pairs` audit (L212); `run()` did not, so "World Cup
  is over" and "collector silently broke" remain indistinguishable from tape alone. Pre-existing
  and already flagged — not a new finding, restated here because it's this family's instance of
  the same gap.

## Drift

Clean. 0 malformed lines out of 6,369 (100% valid JSON). Exactly one schema
(`polymarket_pairs.v1`) and one key-set across all 11 days — no silent schema evolution. 100%
of records (6,369/6,369) carry `real_ask` on both the Kalshi and Polymarket legs — 0
`synthetic`, 0 `midpoint`, 0 untagged (CLAUDE.md's default-FALSE trust rule holds). Only 3
`book_fetch_ok: false` rows (2 on 07-07, 1 on 07-15) and 16 null `price_gap_yes_ask` — 5 of
those nulls are on 07-15 and are the resolved final's genuinely-empty Polymarket ask side, a
real venue signature, not a defect. Append-only confirmed via
`git log --numstat -- tape/polymarket_pairs/`: **6,369 additions, 0 deletions, across the
family's history** — the entire family reached `main` in one 2026-07-27 stranded-tape-recovery
commit (`ac8a758`), consistent with `polymarket_pairs` predating the per-hour incremental
collector cadence other families show.

## Join-ability

Match key is (round, normalized team name), exact 1:1
(`collection/polymarket_pairs.py:245-268`) — every line that reaches committed tape is by
construction a matched pair; the `unmatched`/`ambiguous` counts live only in `run()`'s
in-process summary dict, which is never persisted (the same L212-class hole `run_fed_decision`
had before its 07-28 fix). So a matched/ambiguous/unmatched **rate** is not recomputable from
committed tape today — stated honestly rather than guessed. What tape does show: 16 distinct
teams across 3 rounds (final 2,976 rows / semifinals 2,223 / quarterfinals 1,170).

## The one real finding: the 14/424 caller-explicability anomaly, resolved

Last night's new `scripts/tape_gap_monitor.py::caller_explicability()` (built 2026-07-31,
L222) flagged `polymarket_pairs` at **14/424 (3.3%) unexplained passes** — the highest of any
ungated leg (`sports_pairs` 1/638, `crypto_hourly` 1/766, `polymarket_macro_pairs` 1/644,
`polymarket_cpi_pairs` 1/127, all ≤0.4%), though far below the two gated legs
(`econ_prints` 15.4%, `anomalies` 21.8%). Nobody had looked into *why* before this audit.

**Root cause, fully identified.** All 14 unexplained passes sit on `dt=2026-07-15`,
`20:39:28Z`→`21:05:28Z`, spaced exactly 120s apart with an identical sub-second `captured_at`
offset (`.5934xx`). They are the interior of a contiguous 30-tick, 2-minute-cadence run from
`20:11:28Z` to `21:11:28Z` (one boundary skipped at `21:07:28Z`, consistent with
`burst_capture`'s documented skip-on-overrun behavior) — the `kalshi-burst-wcsemi2-0715`
one-shot trigger (`ops/burst_capture_chunked.md:15`;
`findings/2026-07-16-s17-burst-wcsemi2-q19.md:16,55`, "median ~120s"). Content confirms it:
Argentina's `yes_ask` moves 0.26 → 1.00 across exactly those 14 rows as the semifinal resolves.

**Two compounding causes, both in the tool, not the tape:**
1. `scripts/tape_gap_monitor.py`'s `BURST_CAPTURE_CO_WRITTEN_FAMILIES` (before this fix) was a
   hand-maintained 3-family tuple (`polymarket_macro_pairs`, `crypto_hourly`, `econ_prints`) —
   the set a multi-family FOMC burst happened to co-write (L227) — that silently omitted
   `polymarket_pairs`, `polymarket_cpi_pairs`, and `sports_pairs`, even though
   `collection/burst_capture.py::FAMILY_REGISTRY` has always driven all six via `wc`/`fed`/
   `cpi`/`econ`/`crypto`/`sports`. So `burst_capture` was never even a **registered caller** of
   `polymarket_pairs` — the report's `registered_callers` field read `["hourly_pass"]` only,
   which is factually wrong against the repo.
2. Even a fully corrected registry does **not** clear these 14: `caller_explicability`
   self-excludes the audited family from its own witness list, and `kalshi-burst-wcsemi2-0715`
   ran `--families wc` alone — none of `crypto_hourly`/`econ_prints`/`polymarket_macro_pairs`/
   `polymarket_cpi_pairs`/`sports_pairs` wrote a single pass in the 20:39-21:05Z window
   (confirmed directly against their tape). A single-family burst round leaves **no sibling leg
   to witness by construction**, no matter how complete the registry is — a structural blind
   spot of the co-occurrence method itself, not a registry gap.

**Verdict: DEAD (tool blind spot, not a data hole).** `tape/polymarket_pairs/` has no defect
here — every one of the 14 rows is a real, correctly-captured observation from a known, sanctioned
burst trigger. The anomaly was entirely in how the analysis tool classified its own provenance.

## Fix applied this run (`scripts/tape_gap_monitor.py`, `tests/test_tape_gap_monitor.py`)

1. **Registry correctness.** `BURST_CAPTURE_CO_WRITTEN_FAMILIES` is now *derived* from a new
   explicit `BURST_CAPTURE_KEY_TO_TAPE_FAMILY` map (`wc`→`polymarket_pairs`,
   `fed`→`polymarket_macro_pairs`, `cpi`→`polymarket_cpi_pairs`, `econ`→`econ_prints`,
   `crypto`→`crypto_hourly`, `sports`→`sports_pairs`) instead of a hand-picked subset.
   `burst_capture` is now correctly registered (and a correct witness) for all six families it
   can actually write. A new drift-detector test,
   `test_burst_capture_key_to_tape_family_matches_registry`, asserts this map's keys equal
   `collection.burst_capture.VALID_FAMILIES` — it fails loudly if burst_capture ever adds or
   renames a family without this map being updated, closing the exact silent-omission mode that
   caused this finding.
2. **Documented, tested limit — deliberately NOT "fixed away".** The single-family arity blind
   spot is real and structural: the registry fix makes `burst_capture` a correctly-registered
   caller of `polymarket_pairs`, but the 14 rows on `dt=2026-07-15` still verdict
   `UNEXPLAINED_PASSES` after the fix (verified live — see below). The `caller_explicability`
   docstring and its returned `coverage_note` now both state this caveat, so it travels with
   any future quoted number. A new HARD real-tape acceptance test,
   `test_acceptance_14_l222_polymarket_pairs_wcsemi2_burst_is_registered_but_still_arity_blind`
   (FROZEN to `dt=2026-07-15`, L191), pins BOTH facts at once: `burst_capture` now appears in
   `registered_callers` and explains the OTHER 43 passes that day, while these 14 remain
   unexplained AND form a regular 120s cadence (the burst signature) rather than noise — so a
   future change can't silently paper over the blind spot by fabricating a witness.

Verified live before/after:
```
# before: registered_callers=["hourly_pass"], n_unexplained=14
# after:  registered_callers=["burst_capture","hourly_pass"], n_unexplained=14 (unchanged, as designed)
python3 scripts/tape_gap_monitor.py --caller-explicability polymarket_pairs --explicability-days dt=2026-07-15 --no-notify
```

## Lesson candidates (for kb-distiller)

- "Co-occurrence explicability has an arity floor: a caller invoked with a SINGLE family
  produces zero witnesses and is inexplicable by construction. Before treating
  `n_unexplained > 0` as a provenance incident, check whether the unexplained passes form a
  regular fixed-interval train with a constant sub-second offset (a burst signature) rather
  than assuming co-occurrence is exhaustive."
- "A caller-family registry hand-maintained in an audit tool drifts silently from the caller's
  own registry (here: `collection/burst_capture.py::FAMILY_REGISTRY`). Derive it, and pin the
  correspondence with a test that fails on drift, rather than re-deriving it by hand each time
  a new family is added."

## Not acted on this run (Ryan-side / out of a research run's lane)

- `collection/polymarket_pairs.py:354`'s `run()` still lacks the L212 always-write-a-summary
  fix its sibling `run_fed_decision` received on 2026-07-28 — this changes a LIVE collector's
  write path, same posture as L221/L222's deferred halves, out of a research run's lane.
- Persisting `unmatched`/`ambiguous` match counts to tape (so join-ability rates become
  recomputable) is the same class of write-path change.

## Gates

`pytest` — full suite green (see run digest for the exact count, taken fresh at commit time
per L162). `python scripts/invariants.py --full` — exit 0, only pre-existing non-gating
advisories (unchanged by this diff's content beyond the L152 stale-candidate note, which this
finding does not touch). Diff: `scripts/tape_gap_monitor.py` (registry fix + docstring/
coverage_note caveat), `tests/test_tape_gap_monitor.py` (+4 tests), this finding.
