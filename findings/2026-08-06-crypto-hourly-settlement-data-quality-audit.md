# crypto_hourly data-quality deep-dive (idle-run policy (c), 2026-08-06)

**Status: data-quality only. No CI, no P&L, no registry flip.** S8/S10/S14 keep the DEAD
verdicts they already carry (Q5/Q7/Q34); nothing here reopens them. Two-agent rule N/A
(no verdict-class claim). Step 0b (stranded-branch sweep) ran first this session and
recovered 5,718 genuinely-missing lines across 7 tape families from 3 stranded branches —
see the "Step 0b" section below; this audit runs over the post-recovery tape.

## Why this family, why now

`tape/crypto_hourly/` is Q2's original collector (2026-07-03). It fed three now-DEAD
strategies (S8, S10, and S14's crypto-ladder leg) and Q20's overround anatomy (DONE), so no
strategy is currently alive on it — but the collector still runs every hourly pass, and
recent idle-run(c) data-quality passes covered `orderbook_depth` (L282), `weather_books`
meta (L281), `kalshi_trades` (L280) and `polymarket_cpi_pairs` (L286) without ever giving
`crypto_hourly` itself a dedicated look (it only appeared as a passenger in the 2026-08-05
repo-wide duplicate census, L285). A latent defect in its settlement payload would silently
corrupt any future revival attempt or cross-family join, so this is worth checking even
with no live strategy on it (CLAUDE.md: "collect data where others aren't").

Built `scripts/crypto_hourly_settlement_audit.py` (read-only, fully offline, imports nothing
but the standard library + `core.settlement`) + `tests/test_crypto_hourly_settlement_audit.py`
(16 tests: 12 pure-function against hand-built fixtures incl. two that feed a synthetic
zero-winner / multi-winner settlement to prove the detector actually detects — L191 shape —
plus 4 real-tape acceptance tests with directional bounds, since the family is actively
collected and a future hourly pass must not break the suite).

## 1. Settlement integrity — clean

The full committed history (33 day-files, 2026-07-03 → 2026-08-05, 1,599 lines) carries
1,483 `previous_settlement.status == "settled"` records. The MECE bracket-ladder invariant —
**exactly one member has `result == "yes"`** — holds on **1,483/1,483 (100%)**, checked
through `core.settlement.filter_binary_results_map` (the codebase's sanctioned binary-result
guard, L52/L155) rather than a bare `== "yes"` comparison.

The remaining 116 `previous_settlement` records are **not** malformed settlements — they are
three distinct, correctly-labeled non-settled states, verified against
`collection/crypto_hourly.py::fetch_settlement`/`run()`:

| status | count | meaning |
|---|---|---|
| `pending` | 34 | not every market in the event had posted a `result` yet at capture time |
| `no_current_group` | 76 | no active hourly bracket group found (see §3) — there is no ticker to derive a "previous hour" from |
| `not_found` | 6 | the derived previous-hour event ticker returned no markets at all |

None of these three carry a `results` key at all (confirmed against source), so an event-level
reader that only trusts `status == "settled"` — which is what all three real consumers
(`s14_ladder_fillsim.py`, `s19_wing_fade_fillsim.py`, `seed5_funding_prior_probe.py`) already
do via an `if not et or not results: continue` guard, independently re-read this run — can
never misinterpret a not-yet-settled event as "every bracket lost." An earlier pass at this
analysis (this run, self-caught before publication) conflated "key absent" with "key present
and empty," which would have wrongly reported 116 corrupted `broker_truth` records; re-running
through the `status` field resolved it to the clean result above. Recorded as **L289** (a
methodology note for future family audits, not a code defect — see kb/lessons; renumbered
from L287 on rebase, as PR #299 landed concurrently and claimed L287/L288 first).

## 2. Capture cadence — collapsed, consistent with the already-diagnosed collector outage

Passes/day (one pass = one BTC line + one ETH line, same `capture_id`):

- Peak: **143 passes** on 2026-07-14 (the CPI burst-capture day; excluded from the "normal"
  baseline below).
- Steady mid-July baseline: **46–50 passes/day** (07-04 through 07-13, minus the 07-14 burst).
- Most recent 7 committed day-files (07-30 → 08-05): **5.6 passes/day mean** — an ~88% drop
  from the mid-July baseline.

This is **not a new root cause** — it is this family's own number for the already-documented
VPS-death + cloud-slot-attrition outage (`findings/2026-07-25-vps-collector-second-death-and-cloud-slot-attrition.md`,
`findings/2026-08-03-vps-collector-true-outage-273h-burst-contamination-blind-spot.md`, and
`scripts/invariants.py`'s own COLLECTOR HEALTH ADVISORY, which reports the `vps` leg silent
343.1h as of this run). No new diagnosis is claimed; this is a confirmation that the outage's
effect is visible in `crypto_hourly` specifically, at the same order of magnitude as every
other family already measured.

## 3. Discovery-gap profile — a closed July episode, not a live risk

`current` (the hourly bracket-group discovery step) failed on 76/1,599 passes (4.75%),
72 of them the genuine "no hourly group exists right now" case (`no_hourly_group_found`,
split evenly 38 BTC / 38 ETH) and 4 transient network/proxy errors. Every occurrence falls
between 2026-07-03 and 2026-07-30 — **zero recurrences in the 6+ days of tape since**, so
this reads as a closed historical episode rather than an ongoing defect. No fix proposed;
recorded for the record so a future audit doesn't have to re-derive it.

## Step 0b — stranded-branch sweep (this run)

`scripts/tape_branch_sweep.py` (no `--limit`, full fetch) triaged all 231 remote `tape/*`
branches: 25 fully line-verified contained, 190 contained via the capture_id-level check
(bulk-family size guard), 54 malformed-name (ordered by commit date, not name), and **16**
carrying content genuinely absent from `HEAD` — 13 of those are the known L247 unappendable
class (git conflict markers / the non-JSONL `tape/cloud-env-check.md` doc; correctly left
alone) and **3 carried real, appendable tape**:

| branch | family : missing | recovered |
|---|---|---|
| `tape/hourly-20260805T1305Z` | `crypto_hourly` (2), `polymarket_macro_pairs` (21), `sports_pairs` (614) | line-level union-append |
| `tape/hourly-20260805T1615Z` | `orderbook_depth` (1 capture_id = 2,000 lines), `weather_books` (1 capture_id = 531 lines) | capture_id-level extraction |
| `tape/hourly-20260805T2210Z` | `hyperliquid_funding` (2), `perp_tape` (17), `orderbook_depth` (1 capture_id = 2,000 lines), `weather_books` (1 capture_id = 531 lines) | line/capture_id extraction |

**5,718 lines recovered** across 7 files, all validated as parseable JSON and confirmed
zero-overlap / zero-duplicate against `HEAD` and against each other before appending
(the two `orderbook_depth`/`weather_books` capture_id gaps come from two *different* missing
passes, verified disjoint). Post-append every touched file re-checked: line count == distinct
line count (no duplicates introduced), 0 JSON parse errors. Branches are left undeleted per
the 2026-07-10 retro amendment (cloud sessions cannot delete remote branches — a documented
permission boundary, not re-attempted here).

## Honest limits

- The MECE-invariant check reads only what the collector already writes; it cannot detect an
  upstream Kalshi API defect that would make a genuinely wrong single "yes" look clean.
- Cadence and discovery-gap numbers are point-in-time as of this run's tape; both will move
  as more tape lands (the acceptance tests use directional bounds for exactly this reason).
- No new fix is proposed for the cadence collapse — it is Ryan/VPS-gated per every prior
  finding on the same outage; this run adds one more family's confirming number, not a new
  lever.
