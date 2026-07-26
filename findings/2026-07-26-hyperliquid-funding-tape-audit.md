# `tape/hyperliquid_funding/` data-quality audit (first dedicated pass)

2026-07-26 · research loop, idle-run policy (c) · read-only tape-auditor subagent, main
context applied the one small fix that fell out of it. No strategy claim, no P&L, no
registry change — two-agent rule N/A (data-quality audit + a documentation/test fix, not a
verdict).

## Why this family, why now

`tape/hyperliquid_funding/` feeds the Q42 cross-venue funding-basis work
(`scripts/q42_crossvenue_funding_join.py`, `findings/2026-07-22-q42-crossvenue-join-recent-
mode-unfreeze.md`) but had never been the *subject* of its own audit — only consumed by
downstream join scripts. Other large families (`orderbook_depth`, `universe_sweep`,
`weather_books`/`settlement_ledger`) have each had a dedicated pass; this one hadn't.

## What was checked, and what was found

**Schema/shape — clean.** 56 lines / 2566 print rows total across 6 day-files, 100% valid
JSON, exactly two key-sets matching `collection/hyperliquid_funding.py`'s `backfill`
(14 keys, +`end_ms`) and `incremental` (13 keys) record shapes. Zero null/missing fields
across all 2566 print rows. Inner `prints[].coin` always equals the record's own `coin`.
BTC and ETH payloads are genuinely distinct (0/1282 shared `time_ms` share identical
`(funding_rate, premium)`) — no L127-style leg duplication.

**Coverage — perfect at the print level; day-files are not a coverage metric for this
family.** `dt=2026-07-18`…`dt=2026-07-21` have no committed file (the L127 VPS-freeze
window), which *looks* like a 4-day hole — but the union of every `prints[].time_ms` across
all 6 files is **1282 distinct hourly prints per coin, 2026-06-03T00:00Z → 2026-07-
26T09:00Z, 0 non-1h steps**. Because each record carries a retrospective list rather than
one point-in-time observation, the catch-up pass after the freeze (`20260722T024322Z`,
n=116) backfilled the whole gap in one page. **Any future audit of this family that counts
`dt=` files as coverage will manufacture a false gap finding** — coverage here must be
computed on the union of the embedded `time_ms` field.

**Source tag — consistent and correct.** `price_source_tag == "broker_truth"` on 56/56
lines, correctly non-fillable (these are venue-computed finalized prints, not live quotes).

**Units/UTC/mode-freshness — clean on all three previously-seen defect classes.** Checked
against L119 (dollars-vs-cents), L45 (ET-vs-UTC ticker parsing), and L137 (backfill-vs-
recent mode gap): none apply here. Kalshi 8h rates and HL's 8h-compounded hourly rates are
the same fractional units and order of magnitude; both legs are epoch-ms/UTC-ISO with no
ticker-hour parsing exposure; `collect_kalshi_prints` already reads both modes (`mode=
{"backfill","recent"}`).

**Append-only — clean.** All 11 commits touching the family are pure additions (`git show
--numstat`: `+2 -0` ×10, `+36 -0` ×1). No rewrite, reorder, or deletion anywhere in the
family's history.

## F1 — a real, low-blast-radius defect: cross-branch dedup is branch-local, not global

2 of 2566 print rows are duplicated on `(coin, time_ms)`:

```
('BTC', 1784725200052)  captured_at 20260722T130722Z  and  20260722T133011Z
('ETH', 1784725200052)  captured_at 20260722T130722Z  and  20260722T133011Z
```

`git log -S` traces the two captures to different commits that landed **out of capture
order**: `d845dfb` (2026-07-23 01:38) carries the earlier `20260722T130722Z` capture, while
`2235aa3` (2026-07-22 22:36) carries the later `20260722T133011Z` one. Root cause:
`collection/hyperliquid_funding.py::_committed_time_ms` dedups a pass's "what's already
archived" set against the *local working tree* only — which is only as complete as the last
merge. With two collectors (VPS + cloud) racing on unmerged `tape/hourly-*`/`tape/burst-*`
fallback branches (LOOP-QUEUE.md step 0b's standing state — 189 such branches on `origin` at
audit time), each can independently see "nothing new" and both archive the same print. The
module's own docstring overclaimed global idempotency ("whichever pass runs first... the
next finds nothing new... never a duplicate line") — true only once both collectors' prior
work is merged.

**Blast radius today: nil.** The only current consumer, `scripts/q42_crossvenue_funding_
join.py::collect_hl_hourly`, already dedups on `(coin, hour_index)` keep-first before use —
1282/coin, the true count, unaffected. The two duplicate rows are byte-identical, so even a
naive raw-row read wouldn't corrupt a *rate*, only a *count* (e.g. a future `n_prints`
summary).

**Fix applied this run (read-only tape families are never rewritten — this corrects the
code and its claim, not the two already-committed duplicate lines):**
1. `collection/hyperliquid_funding.py`'s docstring now states the branch-local caveat
   explicitly, with this finding's citation, instead of claiming unconditional global
   idempotency.
2. New regression test `tests/test_q42_crossvenue_funding_join.py::
   test_collect_hl_dedups_cross_branch_duplicate_records` reproduces the exact real-tape
   scenario (the same `(coin, time_ms)` print arriving in two separate `funding_history`
   records) and pins that `collect_hl_hourly` handles it correctly today.

## F2 — documentation gap: Q42's 8h window alignment is unverifiable from this tape

`join_asset` maps a Kalshi print at hour index `hT` to HL hours `hT-7 … hT`, which is only
correct if HL's `time` field is the *application* time (covering the preceding hour) rather
than the interval start. A shift sweep (−2…+2 hours) over all 158 joinable windows:

```
KXBTCPERP  shift=-2 corr=-0.0534 | -1 -0.0845 | 0 -0.1288 | +1 -0.1529 | +2 -0.1336
KXETHPERP  shift=-2 corr=+0.1384 | -1 +0.1432 | 0 +0.1481 | +1 +0.1396 | +2 +0.1290
```

The correlation curve is flat within ±0.03 across all five shifts, and `shift=0` is not the
argmax for BTC (it's among the most negative). The two legs are near-uncorrelated at this
density, so a ±1h misalignment would be completely invisible in the current tape — this is
not a defect to fix, it's a limits caveat future Q42 write-ups should carry. (Also notable,
not a problem: 158/158 Kalshi prints join with all 8 HL hours present — zero partial
windows; HL's coverage of the Kalshi leg is complete.)

## F3 — out of scope for this audit, flagged anyway

`du -sh tape` = 1.2G, ~24x the `tape/README.md` 50MB external-storage decision point
(`universe_sweep` 428M, `orderbook_depth` 318M, `sports_pairs` 227M, `weather_books` 106M,
`crypto_hourly` 67M — `hyperliquid_funding` itself is a trivial 348K). Ryan's storage
decision (tracked in PR #166, open) is well past due; not actionable from a cloud run.

## Gates

`python -m pytest tests/test_q42_crossvenue_funding_join.py tests/test_hyperliquid_funding.py -q`
→ 26 passed (1 new). Full-suite and `invariants --full` counts are in the `kb/00-LOG.md`
entry for this run (taken after this diff's last edit, per L162).
