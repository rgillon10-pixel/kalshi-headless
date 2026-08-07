# Two enforcement gaps closed: settlement-source completeness (L300) and post-recovery containment (L301)

`2026-08-07` · research loop, protocol v3 · **IDLE RUN, idle-run policy (a)** (queue drained;
every item Q0–Q55 reads DONE / BLOCKED / RESERVED / time-gated / data-gated at its current
Status line — Q51 milestone 3 is time-gated to 2026-08-10)

**Verdict class: TOOLING + a factual CORRECTION.** No registry status flip, no bootstrap CI,
no P&L, no kill decision. `kb/strategies/00-index.md`'s status column is untouched; S79 stays
`collect-and-revisit`. Still **0 proven edges**.

---

## 1. The S79 data-gate was wrong about which wall it was standing at (L300)

The 2026-08-06 S79 registration recorded its blocker as *"no settlement coverage of the trade
day — `tape/settlement_ledger/` covers 07-07→07-22 only"*. The 2026-08-07 edge-hunter round #25
caught that as false and filed **GitHub issue #310** (Priority:high) rather than rewriting
history. This run re-derived it a **third** time, independently, before writing any code:

```
python3 scripts/settlement_coverage_audit.py --tickers-from tape/kalshi_trades/dt=2026-08-03.jsonl
42 requested / 9 resolved / 0 non-binary / 33 unresolved; hits: q51_settlement_cache=9
  settlement_ledger        files=2    hits=0     ledger_rows
  q26_settlement_cache     files=1    hits=0     cache_markets_map
  q27_settlement_cache     files=1    hits=0     cache_markets_map
  q29_settlement_cache     files=1    hits=0     cache_markets_map
  q30_settlement_cache     files=1    hits=0     cache_markets_map
  q51_settlement_cache     files=2    hits=9     cache_markets_map
  crypto_hourly            files=35   hits=0     record_results
  weather_actuals          files=9    hits=0     event_list_results
  econ_prints              files=25   hits=0     record_results
```

* 42 distinct tickers traded on `dt=2026-08-03`; **38** are listed in
  `tape/q51_settlement_cache/settlement.json` (`broker_truth`, `day: "2026-08-03"`, 60 markets,
  10 `finalized` / 49 `active` / 1 `closed`); **9** carry a binary `result`, spanning **9
  distinct `event_ticker`s** — the bootstrap unit for a sports probe is the GAME (L6).
* `tape/settlement_ledger/` contributes **0** (its two day-files hold 10,605 rows, none of them
  an 08-03 ticker).
* The remaining **4** traded tickers (`KXBTC-26AUG0221-B63650`, `KXBTC-26AUG0300-B62550`,
  `KXBTC-26AUG0312-B63950`, `KXETH-26AUG0300-B1842`) are listed by **no** settlement family —
  checked against every `crypto_hourly.previous_settlement.results` map on committed tape.

**What changes:** S79's settlement blocker is `below_min_units` — **9 games < the L41 floor of
10** — a one-game data wait, not a missing collector. **What does not change:** the exit-book
half of the gate (08-03 `orderbook_depth` has 4 captures all day = the S9 cadence wall), the
multi-day `kalshi_trades` requirement, the presumptive KILL prior on the taker/overround wall,
and S79's status. A wrong reason is not a harmless imprecision: it points the next run at a
collector build instead of at one more day of tape.

### The general defect, and the enforcement

Nine settlement-bearing surfaces exist; a `grep settlement_ledger` finds one of them, and a
directory-name scan finds six. Three are **embedded** in another family's record schema and are
structurally invisible to any name-based search:

| family | where the results live |
|---|---|
| `crypto_hourly` | `previous_settlement.results` (the prior hour's settled ladder) |
| `weather_actuals` | `settled_markets.events[].results` |
| `econ_prints` | `recent_settlement.results` |

`core/settlement_sources.py` is now the ONE registry. `resolve_market_results(tickers)` scans
all nine and returns per-source attribution, with three outcome classes kept separate on
purpose: `resolved` (a binary result, via `core.settlement.is_binary_result` — L52, a
`"scalar"` is never scored as a loss), `non_binary`, and `listed_unsettled` (Kalshi still lists
it `active` — **listed is not settled**, and conflating them would be the same lie pointing the
other way). `scripts/settlement_coverage_audit.py` is the read-only CLI
(`reports/settlement_coverage_audit.json`).

**Published recall limit (L155/L189).** `undeclared_settlement_dirs()` can only catch a NEW
settlement-*named* directory (how five of the nine arrived). A tenth family embedding results
in another schema is undetectable by name, and
`tests/test_settlement_sources.py::TestUndeclaredDirDetector::test_it_cannot_see_an_embedded_family_and_that_limit_is_the_point`
constructs exactly that case and proves the blind spot instead of asserting the prose. A
0-issue report is precision evidence, never recall.

---

## 2. A "recovered stranded branch" was only partly recovered (L301)

Step 0b this run found three branches carrying tape `main` did not have — including one that a
**merged PR had already claimed**:

| branch | lines recovered | families |
|---|---|---|
| `tape/hourly-20260806T0657Z` | 643 | crypto_hourly 2, polymarket_macro_pairs 21, sports_pairs 620 |
| `tape/hourly-20260806T0726Z` | 438 | hyperliquid_funding 2, perp_tape 17, weather_books 419 |
| `tape/hourly-20260807T0115Z` | 23,270 | **universe_sweep 20,000** (whole day-file absent from main), orderbook_depth 2,000, sports_pairs 637, weather_books 543 + meta 48, polymarket_macro_pairs 21, perp_tape 17, crypto_hourly 2, hyperliquid_funding 2 |
| **total** | **24,351** | |

PR #305 (2026-08-06) was titled *"recover hourly-20260806T0726Z stranded lines"* and recovered
that branch's two bulk families (`orderbook_depth` 1,748 + `universe_sweep` 20,000). The same
branch still carried six other capture_ids — `20260806T065616Z`, `065625Z`, `065433Z`,
`072313Z`, `072308Z`, `072315Z`, 1,081 lines — verified absent from every
`tape/*/dt=2026-08-06.jsonl` on `main` before appending (0 grep hits for all six). Nothing
re-triaged the branch after that append, so nothing could notice; the next sweep read the PR
title as a recovery. Same family as **L216** one step later in the workflow: there the CHECK was
incomplete, here the RECOVERY was.

**Enforcement:** `scripts/tape_branch_sweep.py --assert-contained BRANCH[,BRANCH...]` re-triages
only the named branches against `--base-ref` and exits 2 unless every one is contained with zero
missing lines and zero missing capture_ids. Unfetched commits, size-guard-skipped files, and
names the remote does not have all FAIL — an unverifiable claim is not a verified one. Run both
ways this run:

```
$ python3 scripts/tape_branch_sweep.py --assert-contained \
      tape/hourly-20260806T0657Z,tape/hourly-20260806T0726Z,hourly-20260807T0115Z
post-recovery containment check (L301):
  CONTAINED    tape/hourly-20260806T0657Z (capture_id-level only)
  CONTAINED    tape/hourly-20260806T0726Z (capture_id-level only)
  CONTAINED    tape/hourly-20260807T0115Z (capture_id-level only)
  VERDICT: all named branches contained                                    # exit 0

$ python3 scripts/tape_branch_sweep.py --assert-contained \
      tape/hourly-20260806T0726Z --base-ref origin/main
  STILL MISSING tape/hourly-20260806T0726Z: 1081 line(s), 0 capture_id(s)
  VERDICT: NOT recovered - do not claim recovery                            # exit 2
```

### Corollary, recorded rather than quietly fixed

Recovering the 0115Z pass created a **new L281-class duplicate**:
`tape/weather_books/meta/dt=2026-08-07.jsonl` now carries 96 rows — two full 48-key captures
(`20260807T010616Z`, the stranded pass, and `20260807T040557Z`, the one that landed), 5 keys
differing in content. This is not a collector regression: `_existing_meta_series` is
write-once-per-DAY, so whichever pass runs first owns the meta, and recovering the day's *first*
pass necessarily produces two. Both are real captures with distinct `capture_id`s and are
**kept** — dropping real tape to quiet a warning is the wrong trade. `2026-08-07` is added to
`scripts/invariants.py::WEATHER_BOOKS_META_DUP_ALLOWLIST` (second entry, after 2026-07-27) so
future runs read it as a known fact, and the L281 real-tape acceptance test was amended in the
same commit to expect exactly this one extra day and to fail on a third.

### The recovery also falsified a claim nobody could have checked (L302)

The recovered `crypto_hourly` capture `20260806T065616Z` carries
`current.status == "no_hourly_group_found"` on **both BTC and ETH** (`pass_complete: false`).
The 2026-08-06 data-quality audit had concluded that this discovery-gap episode was "a closed
July episode, zero August recurrence" — a claim that was already false when written, because
the tape documenting the August failure had itself been stranded on a push-fallback branch.
Post-recovery the profile reads **78 gaps / 74 `no_hourly_group_found` / `last_gap_day`
2026-08-06** (was 76 / 72 / 2026-07-30).

The bias is not random: a collector host sick enough to fail discovery is the same host likely
to fail its push, so the missing observations are exactly the ones that would have refuted the
claim. **L302**: any "no recurrence since X" statement computed over committed tape is
conditioned on the pass having pushed, and must either follow a sweep that proves no stranded
branch carries the family (now mechanizable via `--assert-contained`) or state the conditioning
out loud. The 08-06 finding carries a dated CORRECTION section rather than an edit, and its
acceptance pin was renamed to state the fact:
`tests/test_crypto_hourly_settlement_audit.py::test_acceptance_real_tape_discovery_gaps_recurred_in_august_L302`.
The discovery mechanism is worth noting: that pin went red **on real tape, by itself**, the
moment the stranded pass landed — the finding was produced by the gate, not by a hunch.

---

## 3. What was built

| artifact | what it is |
|---|---|
| `core/settlement_sources.py` | the 9-source registry + `resolve_market_results` + `undeclared_settlement_dirs` |
| `scripts/settlement_coverage_audit.py` | read-only CLI → `reports/settlement_coverage_audit.json` |
| `scripts/tape_branch_sweep.py` | `--assert-contained` post-recovery self-check (exit 2 on failure) |
| `scripts/invariants.py` | `WEATHER_BOOKS_META_DUP_ALLOWLIST` += `2026-08-07`, with the reason in-line |
| `tests/test_settlement_sources.py` | 35 tests incl. the real-tape S79 acceptance class |
| `tests/test_settlement_coverage_audit.py` | 10 tests |
| `tests/test_tape_branch_sweep.py` | +12 tests (`TestAssertContainedPostRecoveryCheck`) |
| `tests/test_invariants.py` | +2 L301 tests, 1 amended L281 acceptance pin |
| `tests/test_crypto_hourly_settlement_audit.py` | acceptance pin renamed + re-pinned to the August recurrence (L302) |
| `findings/2026-08-06-crypto-hourly-settlement-data-quality-audit.md` | dated CORRECTION section (append-only, original claim not rewritten) |

**Two-agent rule.** Neither half is verdict-class (tooling + a factual correction of a
non-verdict claim; nothing flipped in either direction). No `Task`/subagent tool exists in this
harness, so no independent `verifier` was dispatchable — the L287/L288/L290/L291/L295 precedent.
Every load-bearing number here was computed on a code path independent of the one that first
reported it, and the settlement figure now has three independent derivations behind it.

**Provenance.** Every settlement value quoted is `broker_truth` (an exchange-reported settled
result). No price, no P&L, no fill is claimed anywhere in this finding.
