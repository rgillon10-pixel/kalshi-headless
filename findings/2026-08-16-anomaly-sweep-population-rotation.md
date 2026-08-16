# The anomaly sweep's 20,000-market cap is a conveyor belt, not a window: the prefix fully turns over every few minutes and is 99.4% auto-generated parlay artifacts

**Date:** 2026-08-16 · **Author:** research loop, IDLE RUN, idle-run policy (c) (data-quality
deep-dive on `tape/anomalies/` + `tape/universe_sweep/`) · **Verdict class:** DATA-ADEQUACY.
No registry status flip, no bootstrap CI, no P&L, no kill decision, no price quoted (so no
`price_source_tag` to carry — the audit's own report says so in `price_provenance`).
**PROVISIONAL:** no `Task`/subagent tool exists in this harness, so no independent `verifier`
was dispatchable; per the L287/L288/L290/L291/L295 precedent and the two-agent rule, nothing
here flips a registry status and every number below is owed an independent re-derivation.

## The question, and why it was open

`scripts/anomaly_sweep.py::_fetch_all_open_markets_raw` walks `/markets?status=open&limit=1000`
by cursor, stops at `DEFAULT_LIVE_LIMIT = 20000`, and keeps `markets[:limit]` — the FIRST
20,000 tickers in cursor order. **253 of the 254** committed `tape/anomalies/` passes report
`markets_truncated: true` at exactly `n_markets_scanned: 20000`.

S3's registry row already states the consequence honestly: *"PLATFORM coverage is unmeasurable
from tape and a rate with an unknown denominator falsifies nothing ... S3's standing kill
clause is unreachable until a pass persists its scanned event/ticker inventory (L296)."*
Q55 milestone 1 built that inventory (`scanned_tickers_sha256`) and its own status line named
the comparison it deferred:

> *"matching digests across passes would mean 247 `markets_truncated` passes never expanded
> S3's measured population beyond one ~20,000-ticker slice, a WEAKER reading than '26 days of
> coverage' currently implies; differing digests would support the stronger reading. That
> comparison itself is left for whichever run next touches S3/S15."*

This run ran that comparison. It cannot decide the question — and the question is answerable
anyway, from a proxy that has been sitting on committed tape since 2026-07-17.

Built: `scripts/anomaly_sweep_population_rotation_audit.py` (read-only, fully offline, `--json`)
+ `tests/test_anomaly_sweep_population_rotation_audit.py` (29 tests: synthetic branch coverage
+ real-tape acceptance asserted as **directions and floors only**, never frozen counts —
L320/L191) → `reports/anomaly_sweep_population_rotation_audit.json`.

## 1. The deferred digest comparison cannot decide it — and can only ever return the flattering answer

Five committed passes carry a digest (2026-08-06, 08-10, 08-11, 08-13, 08-15). All five are
**distinct**. Under Q55's stated reading that "supports the stronger reading" — 26 days of
genuinely expanding coverage.

That reading is unsafe, and the audit proves it at run time rather than asserting it.
`scanned_tickers_digest` is a sha256 over the sorted-unique ticker list, so the audit takes a
**real** committed 20,000-ticker capture, deletes exactly ONE ticker, and re-hashes:

| | |
|---|---|
| digest of the full 20,000-ticker set | `3c2f39e8be6b1c83…` |
| digest of the same set minus ONE ticker | `1e95088dedce71d9…` |
| Jaccard similarity of those two sets | **0.99995** |
| digests equal? | **no** |

Kalshi lists and delists markets continuously, so *every* pair of real passes differs by at
least one ticker. The field therefore returns "distinct" unconditionally: it is a **one-bit
identity test standing in for a set-similarity question**, and its only two possible readings
are "identical" (unreachable in practice) and "differing" (the flattering one). It cannot
distinguish 100% rotation from 99.995% overlap. The committed record cannot be repaired after
the fact either, because the ticker LIST was never kept — only its hash.

## 2. A proxy that CAN answer it — premise tested, not assumed

`collection/universe_sweep.py::fetch_open_markets` hits the **same endpoint** with the **same
params** (`status=open`, `limit=1000` pages, cursor order) and stops at
`MAX_CALLS=20 × PAGE_LIMIT=1000` = the **same 20,000 rows** — and, unlike the anomaly sweep, it
persists every scanned ticker. `tape/universe_sweep/` holds **55 captures / 26 days /
1,100,000 rows**, every capture at exactly 20,000 rows, 0 duplicate tickers within a capture.

The proxy premise is a claim, so it is tested against the anomaly tape's own independently
recorded counters:

| measurement | anomaly tape (its own counter) | universe_sweep proxy |
|---|---|---|
| distinct event groups per 20,000-row capture, median | **16,341** (n=251 at-cap passes, min 15,067 / max 18,069) | **16,397** (n=55, min 13,329 / max 17,836) |
| relative gap of medians | — | **0.34%** |
| ladder-capable group count per capture, median | 9 monotonicity group-checks (n=251) | 5 non-junk ladder-capable groups (n=55) |

Two different collectors, different processes, different gate hours (universe_sweep at UTC
{0,6,12,18}; anomaly_sweep ~09-10Z), agreeing to 0.34% on event-group density — that is
evidence the two see the same population *shape*. **Known limits, stated:** no committed record
joins a specific anomaly pass to a specific universe_sweep capture, so this is a
population-shape proxy and never a per-pass identity claim; the ladder-capable series is
additionally non-junk-filtered while the anomaly counter is not, so the proxy is expected to
read at or below it (5 vs 9), and it does.

## 3. The prefix is not frozen — it turns over COMPLETELY

| measurement (population: 55 universe_sweep captures / 26 days) | value |
|---|---|
| consecutive-capture Jaccard, median | **0.0** |
| consecutive pairs at exactly 0.0 | **52 of 54** |
| first capture vs last capture Jaccard | **0.0** |
| cumulative distinct tickers ever scanned | **1,063,235** (of 1,100,000 rows) |
| max number of captures any single ticker ever appears in | **2** |
| tickers appearing in exactly 1 capture | **1,026,470 (96.5%)** |

The "one frozen slice re-scanned 250 times" worry is **falsified**. And the two exceptions are
the sharp part: *every* repeat in the entire committed history comes from exactly **two**
capture pairs that are **76 seconds** and **194 seconds** apart —

- `2026-08-01T13:07:29 → 13:08:45` (76 s): 18,874 / 20,000 shared = **94.4%**
- `2026-07-22T07:07:55 → 07:11:09` (194 s): 17,891 / 20,000 shared = **89.5%**

Across any two captures separated by more than ~3 minutes, **zero** tickers are shared. The
prefix sheds ~5-10% of its content per minute and replaces itself entirely in roughly
20-30 minutes. **The sweep has never observed the same market twice.**

## 4. Rotation is churn, not coverage

| composition (population: 1,063,235 distinct tickers ever scanned) | value |
|---|---|
| `KXMVESPORTSMULTIGAMEEXTENDED` | 774,911 (72.88%) |
| `KXMVECROSSCATEGORY` | 282,194 (26.54%) |
| **all `KXMVE*` auto-generated multi-leg families** | **1,057,105 (99.42%)** |
| **everything else — the entire non-junk population ever reached in 26 days** | **6,130 tickers** |
| distinct series ever seen | 212 |
| junk share per capture: median / min | 99.77% / 95.76% |

L125 (2026-07-21) already measured the ~97% `KXMVE*` share as a **fillability** property over a
5-day window ("a non-fillable dead tail"). What is new here is the **population-identity** view
over 26 days: the junk is not a static dead tail sitting in the prefix, it is a *conveyor belt*
of freshly minted markets whose churn is what consumes the entire cap. Descriptive support: on
the three most recent capture days the prefix's `close_time` values cluster **2-4 days out**
(e.g. dt=2026-08-15: 17,284 rows closing 08-18, 6,148 closing 08-17), which is what a stream of
newly created near-dated parlay markets looks like.

One alternative hypothesis is worth rejecting explicitly. If the platform's open universe were
*static* of size U and the cursor merely returned an unstable ordering, two 20,000-row draws
would share about 20,000²/U tickers; observing **0** shared across 52 consecutive pairs would
require U ≳ 4×10⁸. The static-universe-with-unstable-ordering model is therefore quantitatively
implausible, and the churn reading survives. What this tape **cannot** separate is "cursor
tracks newly CREATED markets" from "cursor tracks most-recently-UPDATED markets" — both produce
the same coverage consequence, and neither is decidable from committed bytes.

## 5. The honest denominators behind "0 verified fillable arbs"

Non-junk population ever reached across all 26 days: **6,130 distinct tickers**, in **988**
distinct event groups, of which **737** carry ≥2 markets (the only groups a cross-strike
monotonicity check can evaluate at all). Per capture: median **92** non-junk tickers and median
**5** ladder-capable groups — out of 20,000 rows scanned.

0 events observed → rule-of-three 95% upper bound, per candidate unit:

| unit | n | 95% upper bound (per unit) | note |
|---|---|---|---|
| market-observation (proxy tape rows) | 1,100,000 | 2.73e-06 | most optimistic; treats each re-listing of an ephemeral market as an independent trial |
| distinct non-junk ticker ever scanned (proxy) | 6,130 | 4.89e-04 | the population a real crossing could ever have been found on |
| distinct ladder-capable event group ever scanned (proxy) | 737 | **4.07e-03** | the only evaluable unit for S3's check |
| monotonicity group-check (anomaly tape's own counter, no proxy) | 2,247 | 1.34e-03 | measured directly on `tape/anomalies/` |
| capture-day | 26 | 1.15e-01 | the unit S3's registry row currently quotes (per L221) |

**These span three orders of magnitude, and the tape cannot identify which one is correct.** A
market observed once and never again is not a repeated trial, and the repeat structure needed to
decide the question was never captured. What *is* now decided: **none of these bounds is a
statement about "the Kalshi platform."** Every one is scoped to whatever fell inside a
20,000-row cursor prefix that is ~99.4% auto-generated parlay artifacts. S3's registry row is
not overclaiming today (it quotes the capture-day unit and says the denominator is unknown);
this run replaces "unknown" with "measurable, and small."

## 6. S15's kill clause is structurally unfireable, and now we know why

Q55 milestone 2 added `kxmarmadround_progression` to `config/implication_pairs.yaml` — 560 open
`KXMARMADROUND` markets, hand-audited rules text, an offline dry-run generating 1,120 pairs —
precisely so S15's "kill if 0 fee-clearing hits in 60 days" clause could finally fire. Its first
live pass still reported `n_implication_pairs_checked: 0`, attributed at the time to cursor
truncation.

Measured here: `KXMARMADROUND` appears in **0 of 55** committed captures, **0 distinct tickers
ever**. It is not "sometimes beyond the cursor" — it is never inside the cap at all, and given
§3 it never will be while a conveyor belt of parlay markets occupies the whole prefix. Every
future pass will keep writing `n_implication_pairs_checked: 0` as an `empty_denominator`
(L296/L298), forever, for a reason no amount of waiting fixes.

## What this changes, and what it does not

**Does not change:** S3 and S15 both stay `data-collecting`. No status flip, no CI, no kill.
Q55's own milestones stay DONE. No collector was modified.

**Does change the diagnosis.** The blocking condition on S3/S15 was recorded as "the denominator
is unknown, waiting on a scanned-ticker manifest." The manifest was built, and it turns out (a)
the manifest's chosen form cannot answer the question, and (b) the question was already
answerable from a sibling family. The real blocker is neither: it is that **the cap and the
cursor order together select a population that contains almost nothing worth scanning**, and
more passes buy more of the same.

**The repair is cheap and is NOT built here** (a collector-write-path change, deliberately out
of scope for an idle run, recorded for Ryan / a future collector milestone):

1. **Targeted series fetches instead of a blind prefix.** `anomaly_sweep` already knows which
   series its checks care about (`config/implication_pairs.yaml`'s families, plus whatever S3
   ladders matter). Q55's own offline dry-run against `series_ticker=KXMARMADROUND` returned all
   560 markets and 1,120 pairs — one bounded call reaches what 55 blind 20,000-row pulls never
   did.
2. **Exclude the auto-generated families from the cap.** Filtering `KXMVE*` at the pagination
   boundary would raise the non-junk yield of a 20,000-row budget by roughly two orders of
   magnitude, from a median 92 tickers per capture to the whole non-junk universe.
3. **If the blind sweep is kept, persist the ticker LIST (or a similarity-preserving sketch —
   a MinHash / bottom-k signature), not a content hash.** A hash answers "identical?"; the
   honest-denominator question is "how much overlap?", and only the second buys anything.

## Precedent, and what is actually new

Three prior pieces of work touched this tape and are cited rather than re-discovered:

- **L96 (2026-07-18)** measured the `/markets` cursor still active past 80k — the cap is
  partial coverage, known.
- **`findings/2026-07-21-universe-sweep-liquidity-census.md` / L125** measured the ~97%
  `KXMVE*` share over a 5-day window as a **fillability** property ("a non-fillable dead tail",
  3.03% of lines fillable).
- **`findings/2026-08-03-universe-sweep-completeness-cap-saturation.md`** measured that the cap
  saturates on 100% of real passes and wired a `completeness_cap_saturation` advisory.

What none of them asked, and what this run measures: **the IDENTITY of the scanned population
across time.** "The prefix is capped" and "the prefix is mostly junk" are both compatible with a
stable 20,000-market window that accumulates coverage as markets turn over slowly. The new facts
are that (a) the prefix shares NOTHING with itself beyond ~3 minutes and no market is ever
observed twice, (b) the junk is therefore not a static dead tail but the churning stream that
consumes the whole cap, (c) the non-junk denominator behind S3/S15's kill clauses is consequently
6,130 tickers / 737 evaluable groups rather than an unknown, and (d) the manifest field built to
answer exactly this question cannot answer it. (a)-(d) are what change the S3/S15 diagnosis; the
cap and the junk share on their own never did.

## Redundancy check (in place of a verifier that this harness cannot dispatch)

No `Task`/subagent tool exists here, so the two-agent rule could not be satisfied. As the
standing fallback (the same posture as the 2026-08-15 run), every headline was re-derived on a
SEPARATE code path that never imports the audit module and — importantly — derives each
market's series from the **ticker string** instead of trusting the `series` field the collector
computed at capture time:

| claim | audit | independent re-derivation |
|---|---|---|
| captures / median consecutive Jaccard / pairs at exactly 0 | 55 / 0.0 / 52 | 55 / 0.0 / 52 |
| first-vs-last capture Jaccard | 0.0 | 0.0 |
| distinct tickers / max recurrence / seen exactly once | 1,063,235 / 2 / 1,026,470 | 1,063,235 / 2 / 1,026,470 |
| `KXMVE*` share of distinct tickers / non-junk tickers | 0.9942 / 6,130 | 0.9942 / 6,130 |
| captures containing `KXMARMADROUND` | 0 | 0 |
| non-junk event groups / ladder-capable (>=2 markets) | 988 / **737** | 1,055 / **791** |

Every number reproduces exactly except the last row, and that gap is a definitional one worth
stating rather than smoothing: the audit groups by the API's own `event_ticker` field, which is
what `scripts/anomaly_sweep.py::_group_by_event` itself groups by (`m.get("event_ticker")`), so
737 is the figure that matches the consumer. The re-derivation used a ticker-string heuristic
(ticker minus its final leaf) and got 791 — a 7.3% spread that moves no order of magnitude and
leaves the rule-of-three bound at 3.8e-03 instead of 4.07e-03. Both are quoted rather than the
more favourable one.

This is a redundancy check, not an independent verifier: it shares this run's judgment about
what to measure. The result stays PROVISIONAL and flips nothing.

## Reproduction

```
python3 scripts/anomaly_sweep_population_rotation_audit.py            # verdict + denominators
python3 scripts/anomaly_sweep_population_rotation_audit.py --json --steps
python3 -m pytest tests/test_anomaly_sweep_population_rotation_audit.py -q
```

Report: `reports/anomaly_sweep_population_rotation_audit.json`. Read-only, no network, no
credentials, no order path. Every count above re-derives from committed tape.
