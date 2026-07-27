# `tape/settlement_ledger/` data-quality audit — 2026-07-27

Research-loop idle run, policy (c) — a data-quality deep-dive on one tape family. Queue
(Q0-Q48) fully saturated as of today's earlier nightly edge-hunter run (PR #213); no
`UNENFORCED` lesson remained to convert (policy a unavailable, L180 closed this morning);
both known time-gated probes (Q19 FOMC, Q37 weather) already fully prepped (policy b
unavailable). `tape/settlement_ledger/` (Q45, GOAL.md Phase-1 M1b) has never had its own
dedicated audit the way `orderbook_depth` (L168/L169) and `hyperliquid_funding` (L170/L171)
did, despite being the y-label source multiple probes (Q21's S52 candidate) have joined
against. Audit performed by a `tape-auditor` subagent; the load-bearing numbers below were
independently re-derived in the main context before this writeup (producer-side sanity
check — not a full `verifier` pass, since nothing here is a strategy verdict or registry
flip; same posture as the hyperliquid_funding audit, L170's row).

Baseline: 2 committed files, 10,605 lines, `dt=2026-07-17` (5,605) + `dt=2026-07-22`
(5,000). 4 `capture_id`s: 1 migration (605, from the 4 legacy `qNN_settlement_cache` dirs)
+ 3 live harvests (800 / 4,200 / 5,000).

## F1 (real, high blast radius) — the daily live harvest covers a ~3-hour window, not a day

`collection/settlement_ledger.py` paginates `/markets?status=settled` newest-first with
`MAX_SETTLED_MARKETS=5000` and no `min_close_ts`/`max_close_ts` parameter (`fetch_settled_
markets`, lines 150-174). Independently re-derived per-`capture_id` `close_time` spans from
the live committed tape:

```
capture_id          n     close_time window                      span    n/hour
20260717T122243Z   800   2026-07-17T11:00:00Z .. 12:15:21Z       1.26h    ~635
20260717T122302Z  4200   2026-07-17T08:15:00Z .. 12:04:41Z       3.83h   ~1097
20260722T103141Z  5000   2026-07-22T07:15:00Z .. 10:30:05Z       3.25h   ~1538
```

Kalshi settles on the order of 1,100-1,540 markets/hour in these windows, i.e. roughly
26,000-37,000/day. The leg fires once per UTC day (`SETTLEMENT_LEDGER_UTC_HOUR = 10`,
`hourly_pass.py`), so even a pass that never hits the 5,000-row cap (the 800- and 4,200-row
passes did not) only reaches back a few hours before the API's own newest-first pagination
runs out — the cursor cannot be steered to an earlier window, and a later day's pass starts
the clock over from "now" again. Net effect over the whole committed history
(2026-07-17..07-27): the 3 live captures collectively span **~7.1 of the possible 240
hours (~3.0%)** of that 10-day window, and the two live-day files (07-17, 07-22) do not
overlap in `close_time` at all (`intersect = 0` on the dedup key `(ticker, close_time,
result, settlement_value)` and on bare ticker).

**Consequence:** any probe treating this ledger as "Kalshi's settlements for day X" is
silently working from ≤13.5% of that day's true settlement population, non-randomly biased
toward whatever few hours preceded the 10:00 UTC cron fire. Growing the ledger's row count
over more days will not fix this — see F3 below.

## F2 — `completeness_ok` is pinned `False` on essentially every real pass, by design

`completeness_ok = (not truncated) and (n_parse_errors == 0)` (line 282); a truncated pull
(cap hit) sets it `False` and folds into the hourly-pass-wide flag `hourly_pass.py` reads
(lines 561-567). This was already flagged as an accepted, undecided judgment call in Q45's
own original DONE note ("`completeness_ok=False` is the EXPECTED steady state every time
this leg fires, not a bug") — this audit does not re-open that call, it just confirms the
flag still carries near-zero signal for this family (it fires FAIL on the capped pass and
would fire FAIL even on the two sub-cap passes if either legitimately ran dry mid-window,
since `truncated` only tracks the cap, not "did I actually reach yesterday"). No action
taken; flagged for whoever eventually revisits Q45's judgment call.

## F3 — 97.6% of the live ledger is two auto-generated multivariate-parlay series

```
live rows n=10,000
  KXMVESPORTSMULTIGAMEEXTENDED  7,881
  KXMVECROSSCATEGORY            1,876   -> 9,757 = 97.6%
  KXSILVERH 57 / KXGOLDH 40 / KXWTIH 40 / KXTEMP{DC,LAX,AUS,CHI,NYC}H 20 ea
  KXITFMATCH 4 / KXITFWDOUBLES 2         -> 243 = 2.4%   (12 distinct series total)
```

Of the 9,757 MVE rows, 7,922 (81%) have `volume==0`, `open_interest==0`, and
`is_provisional: true`. Only 1,987/10,000 live rows (19.9%) ever traded. Line-count alone
(10,605) overstates tradable-label content by roughly 40x.

## F4 — the Q21/S52 5.7% join rate is entirely the 605 migrated legacy rows, not the harvester

`findings/2026-07-25-q21-idea-gen-round.md` (S52) reported 605/10,605 settlement-ledger
rows joinable against a pre-close real-ask book, 100% sports. Migration provenance breaks
down exactly as q26 450 + q30 106 + q29 45 + q27 4 = 605, all from the four legacy
`qNN_settlement_cache` probe caches folded into this family at Q45's build (Q45's own DONE
note). **Zero of the 10,000 live-harvested rows are joinable.** The mechanism is F1 (narrow
few-hour close-time windows) compounded by F3 (97.6% auto-generated parlay series no
orderbook collector tracks), not a generic L9/L43 disjoint-window property of the family in
general — and it means the historical join-rate finding is not going to improve as this
ledger accumulates more days under its current pagination shape.

## F5 — one observed hour-10 firing produced zero output (cause unrecoverable from tape)

`origin/tape/hourly-20260725T1003Z` (the one hour-10 branch found across all 43 committed
`tape/hourly-*`/`burst-*` branches at audit time) touches `crypto_hourly`,
`polymarket_macro_pairs`, `sports_pairs` — no `tape/settlement_ledger/dt=2026-07-25.jsonl`.
`ops/vps/kalshi-headless-hourly.sh` keeps only the one-line `[hourly_pass]` summary, so
whether this leg raised or genuinely returned zero new rows that day cannot be reconstructed
after the fact. This refines (does not replace) L123/L144's "cron never lands on hour 10"
diagnosis — the cron DID land on 2026-07-25, and the leg still produced nothing. Not
actionable from a cloud run without richer per-leg logging; noted for whoever next touches
`hourly_pass.py`'s logging.

## F6 (minor, descriptive) — `is_provisional` rows are dedup-indistinguishable from final ones

7,922/10,000 live rows carry `is_provisional: true`, tagged `broker_truth` identically to
final settlements, and `is_provisional` is not part of the dedup key (`ticker, close_time,
result, settlement_value`). A later revision that changes `result` would append a second,
contradictory row for the same ticker with no consumer-visible ordering rule; one that
doesn't change `result` is silently absorbed as a duplicate. Not realized today (0 duplicate
tickers in the committed tape) — descriptive only.

## Dedup blast radius (same question L170 asked of `hyperliquid_funding`)

`_load_existing_keys` globs the LOCAL working tree only (branch-local, same shape as L170).
Currently harmless: the leg fires at most once/day and the observed windows never overlap;
two hour-10 passes on two unmerged branches in the same UTC day would collide with no
downstream guard, same latent risk class as L170.

## What is genuinely clean

- 10,605/10,605 lines parse as valid JSON, 0 malformed.
- `price_source_tag == "broker_truth"` on 10,605/10,605 rows — nothing untagged, nothing
  `synthetic`.
- L52 binary-result discipline holds: `result` is `{no: 8,235, yes: 2,370}` only — 0
  `scalar`/pending/other leaked through. This family needs no additional binary filter.
- Zero null rates on `ticker`/`event_ticker`/`series`/`title`/`close_time`/`settlement_ts`/
  `result`/`settlement_value`/`volume`/`open_interest`/`raw_sha256`. `expiration_value` is
  97.6% null but that is exactly the MVE-series rows and is structural (Q36's KXTEMPNYCH
  probe depends on it for its own series and gets it).
- `result` × `settlement_value` consistency: `{(no,0.0):7,884, (yes,1.0):2,116}`, zero
  contradictions. `settlement_ts < close_time`: 0 violations. `captured_at < close_time`: 0
  violations.
- Append-only history confirmed (`git log --numstat` shows pure insertions, one commit,
  never rewritten). No stranded `settlement_ledger` tape on any of the 43 remote `tape/*`
  branches at audit time (every branch carrying a `dt=2026-07-17` file matches `main`
  exactly).

## Reproduction

```bash
python3 -c "
import json, glob, collections
R=[json.loads(l) for f in sorted(glob.glob('tape/settlement_ledger/dt=*.jsonl'))
   for l in open(f) if l.strip()]
by_cap = collections.defaultdict(list)
for r in R: by_cap[r['capture_id']].append(r)
for cid, rows in sorted(by_cap.items()):
    cts = [r['close_time'] for r in rows]
    print(cid, len(rows), min(cts), max(cts), rows[0].get('source'))
"
```

## Classification / disposition

No strategy claim, no P&L, no registry change — `kb/strategies/00-index.md` untouched.
Two-agent verdict rule N/A (data-quality audit, not a verdict-class change — same posture as
the hyperliquid_funding audit precedent). F1+F2 filed as new lesson **L185** (`UNENFORCED`
— the coverage-ceiling shape generalizes beyond this one collector: any capped, newest-
first-paginated pull with no time-window parameter has a coverage ceiling set by
`cap / event_rate`, independent of how often the leg runs, and that ceiling must be
reconciled against the observed per-hour event rate rather than chosen as a bare memory
guardrail). F3/F4/F6/dedup are descriptive, recorded here for future citation. F5 needs one
future instrumented hour-10 run to characterize before it can become a lesson row; not
actionable today.
