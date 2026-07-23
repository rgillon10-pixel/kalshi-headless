# Running Log — kalshi.headless KB

Append-only. Newest at top. Each entry: `## YYYY-MM-DD HH:MM ET — title`,
then what happened, what it means, and links to the note/script it produced.
Dead ends stay. This is the journey; `git` is the diff.

---

## 2026-07-23 03:1x UTC — research loop: idle run — L139 closes an `anomalies` tape_gap_monitor blind spot; issue #157 re-confirmed still red, now ~23h / 9+ PRs deep

**Step 0a (history-integrity):** PASS. Local `main` had diverged from `origin/main` (a stale
container ref, same known artifact many prior runs today diagnosed) — reset cleanly to
`origin/main` HEAD `95771df`, no local work lost. `kb/00-LOG.md`'s newest entry and the newest
committed tape both read 2026-07-22/23 with no gap.

**Step 0 (claim-check):** 10 open PRs (#158–#166 + #125). #158–#164 are today's/yesterday's
research-loop idle-run outputs, all left unmerged pending issue #157; #165/#166 are drafts from
a separate Ryan-approved background/interactive session (data-stream hardening, tape storage
migration) — additive infra, not claiming any numbered queue item this run would otherwise pick;
#125 is the weekly-retro PR, leave-open-for-Ryan. None claim eligible queue work.

**Step 0b (stranded sweep):** newest branch `tape/hourly-20260722T1256Z` already fully absorbed
by PR #161 earlier today — nothing new to sweep.

**Queue:** Q0–Q47 all DONE/DEAD/BLOCKED/GATED (unchanged from every run since 07-16) → idle run.
Policy (a) exhausted (the only two open UNENFORCED lessons are L131, issue #157 itself and
explicitly Ryan's call, and L136, already claimed by open PR #159); policy (b) has nothing new
(Q43's probe already self-activated and was extended by PR #164 earlier today). Took **policy
(c): a data-quality deep-dive on a tape family nobody had audited yet.**

**Finding + fix (L139):** `scripts/tape_gap_monitor.py::build_report`'s default family list is
`list(FAMILY_CONFIG.keys())` — a family absent from `FAMILY_CONFIG` is never evaluated at all,
not just mis-scored. `tape/anomalies/` (`scripts/anomaly_sweep.py`, gated on
`ts.hour == ANOMALY_SWEEP_UTC_HOUR`, the same single-exact-hour shape as `settlement_ledger`
before L123 and `weather_actuals` before L126) had no entry — the identical blind spot that let
those two freeze silently for days, caught here pre-emptively: `anomalies` is NOT currently
frozen (healthy through `dt=2026-07-22`, last capture 2026-07-22T10:05:33Z, ~17h old at run
time). Registered it (`daily-econ-slot`, same shape as `econ_prints`/`polymarket_cpi_pairs`) +
2 new HARD acceptance tests anchored to the real committed tape (proves both no false-alarm on
the current healthy state, and that the detector would actually fire if `anomalies` ever froze
like its siblings did). See `findings/2026-07-23-anomalies-tape-gap-monitor-blind-spot.md`.

**Issue #157 re-confirmed, still red** (independently re-ran `python scripts/invariants.py --full`
on untouched `origin/main`: identical 2 `order_endpoints_confined` violations; `pytest` identical
5 pre-existing `test_invariants.py` failures). Now blocking **9 stacked PRs for ~23h** since PR
#153 merged (2026-07-22T04:20Z) — the ready-to-apply fix spec in #157 remains unapplied by design
(Stop-rules-adjacent, L131, stays Ryan's call). Not re-litigated further in this entry; flagged in
the phone note given the pileup has now crossed into double digits.

**Two-agent rule:** N/A — non-gating monitor-registration extension, same precedent as
L118/L121/L122/L124/L126/L127/L128.

**Gates:** `pytest` (excluding the two files broken by issue #157's pre-existing
`cryptography`/`_cffi_backend` ABI panic): 1430 passed, same 5 pre-existing failures as base
`main` (byte-identical). `python scripts/invariants.py --full`: exit 2, identical to `main`'s
pre-existing state — this diff touches neither flagged file.

**Step 9 (paper sub-pass):** `SHADOW_REGISTRY={s14_ladder_underwriting}` (DEAD-at-real-fills per
Q34 — dead-strategy shadow, paper-infra validation only, NOT edge evidence). `paper_pass.py`
processed 9 newly-eligible fills off tape committed since `main`'s last committed ledger entry
(2026-07-22), realized P&L **+$15.05 → +$15.15** (`broker_truth`); ledger line appended under
`paper/ledger/dt=2026-07-23.jsonl`. Re-run confirmed idempotent (0 processed on a second pass).
Still **0 proven edges**.

**Not merging — `main`'s own gate is red.** Per LOOP-QUEUE.md step 6, leaving this PR open until
issue #157 resolves, same posture as #158–#164.

## 2026-07-22 04:1x UTC — kalshi-edge-hunter: review PASS + Q21 idea-gen round (S46/S47 both DEAD, 0 registered — 7th zero round); the binding constraint is the data surface, not idea capacity

Step 0a (history-integrity): **PASS.** The container's fresh clone made `git pull` report a
forced-update (`69a3d3f...f3677d4`) that at first glance matches the rewind signature — but
`69a3d3f` is a squashed-out 2026-07-16 hourly tape commit (a stale packed-ref artifact, the same
class the 07-20/07-21 runs saw), not a rewritten history: recent merged PRs #148-#155 are all
confirmed ancestors of `origin/main` HEAD `0075550`, and `kb/00-LOG.md`'s newest entry (07-22)
matches the newest committed tape (07-22). Step 0 (claim-check): the only open PR is #125
(weekly-retro, leave-open-for-Ryan) — 3 days old, already named every prior run, NOT re-flagged.
Step 0b (stranded sweep): the only 07-22 fallback branches are <30 min old (skipped per protocol);
the 00:25Z research-loop sweep (#152) already absorbed the newest sweepable branch — nothing to
append.

**Unit 1 (adversarial review) — PASS, no issue opened.** The last-24h findings are ops/data-quality
(no bootstrap-CI verdict; two-agent rule N/A), so I re-checked the two load-bearing numbers that
actually feed decisions. (a) The `universe_sweep` liquidity-census `is_fillable` predicate
(`yes_ask>0 AND yes_ask_size>=1` over `real_ask`) is correctly conservative (a `yes_ask==0` leg is
absence-of-offer, never a $0 fill). Its committed pooled **3.03%** fillable drifted to **~5.15%** on
the current `dt=2026-07-21` file — but purely because append-only stranded-sweeps doubled that file
(40k→80k lines) since the census ran; **69.8% of the fillable population is longshots (ask≤0.20)**, so
the "~95%+ dead-tail, longshot-skewed" conclusion holds and resurrects no killed candidate. A
descriptive snapshot over append-only tape shifting with the tape is expected, not a provenance
defect. (b) The Observatory's fee-floor interpretation imports `MAKER_FEE_RATE`/`TAKER_FEE_RATE`/
`fee_per_contract` from `core.pricing` — no hand-rolled coefficient (L18/L30, Rule #3). Both pass →
no history rewrite, no GitHub issue.

**Unit 2 (pipeline replenishment) — 2 proposed, both verifier-killed, 0 registered.** 0 eligible
queue items → ran a Q21 round, grounded this time in tonight's Observatory pilot (`PR #155`, merged
04:16Z), whose own first pass also produced **0 candidates** (23 persistent cross-sectional outliers,
all in queue-crowding / one-sided-liquidity / graveyard-blocked naive-maker-spread). **S46**
(touch-queue temporal-growth asymmetry as a settlement predictor — claimed the time-derivative escapes
its dead cousin S22): verifier reproduced the L50 ex-post settlement join over `tape/orderbook_depth/`
(197 games), growth-side hit **0.15–0.20 vs mid 0.80–0.85** on the disagreement subset with exact
complementarity — the mid already prices the depth ladder's derivative, not just its level; fill side
taker=S24 / maker=S19 dead. **S47** (Observatory-selected well-two-sided series → selective maker, the
untested S11 lane): the deep-AND-fee-clearing intersection is empty (deep two-sided books carry ≤2¢
spreads whose half ≤ the flat 1¢ maker fee = S6/S13; ≥3¢ fee-clearing spreads rest on ~10-contract
token queues = L31), and `orderbook_depth` has no trade-print field, so a fill-sim would synthesize the
fill (`synthetic`-as-fill, prime-directive-forbidden). New lessons **L130** (a temporal-derivative
reformulation of a mid-integrated feature does NOT escape the disagreement-complementarity trap) and
**L131** (`two_sided_share` is size-blind and anti-correlated with capturable maker edge; no fill claim
without a trade tape). Seventh consecutive zero round; never pad to quota. Both kills — and the whole
strategy graveyard — trace to the same two walls: the **fill wall** (hourly book snapshots carry no
trade prints, so no maker fill is measurable) and the **mid-efficiency wall** (the mid integrates the
depth ladder's level AND its time-derivative; taker directional dies on the round-trip). **Flagged for
Ryan:** the binding constraint is the DATA SURFACE, not idea capacity — proving anything new likely
needs a different input (trade-print / sub-hourly burst tape, or the credential-gated cross-venue/CME
legs), a human decision, not a cloud run. See `findings/2026-07-22-q21-idea-gen-round.md`.

**Unit 3 (probe-prep) — nothing to build.** Q43's gate opens ~07-23 (perp_tape 6/7 canonical forward
days by FILE SHAPE per L25); its probe `scripts/q43_perp_binary_consistency_probe.py` already exists
with 16 offline tests green and self-activates when the 7th day lands. Q36/Q37 probes are likewise
already self-activating.

**Housekeeping:** 178 `tape/hourly-*` (+1 `tape/burst-20260714T120659Z`, event passed = 179 total)
stranded branches (Q17/PR#46, Ryan-side). Four burst triggers with passed event dates remain uncleaned
and are named for deletion: `kalshi-burst-cpi-0714`, `-wcsemi1-0714`, `-wcsemi2-0715`, `-wcfinal-0719`
(all fired weeks ago, next-run rolled to 2027); `kalshi-burst-fomc-0729` kept (07-29 future). Cleanup
is the weekly-retro's charter — flagged, not deleted.

**Gates:** `pytest` green and `python scripts/invariants.py --full` exit 0 (only the 3 pre-existing
non-gating advisories — L25 dir-shape, L109 GC, L74 daily-cadence) on this docs/findings/lessons-only
diff. Two-agent verdict rule N/A (0 registrations — no registry flip, no bootstrap CI, no kill of an
existing candidate). **Step 9 (paper sub-pass):** `SHADOW_REGISTRY`={s14_ladder_underwriting} (DEAD per
Q34 — paper-infra validation only, NOT edge evidence); no new tape committed this run → `paper_pass.py`
idempotent, ledger unchanged **+$15.05** (`broker_truth`). Still **0 proven edges.**

## 2026-07-22 03:2x UTC — Q36 re-verification: `weather_books` >=7-day calendar gate now OPEN (7/7 days), but STILL under-powered on BOTH legs

Step 0a (history-integrity): PASS — `origin/main` HEAD `efb11b6`; the only commits since the prior run's HEAD (`3073715`) are `(vps)`-tagged hourly tape passes (`c9b0ed7` 01:32Z, `efb11b6` 02:32Z), kb log newest entry and newest committed tape both 2026-07-22, no rewind (the shallow-clone merge-base gap is a known clone artifact, not a history rewrite). Step 0 (claim-check): open PRs are #153 (DRAFT, Ryan-interactive local session — claims Q33/Q47/hyperliquid_funding-refresh; left UNTOUCHED, it explicitly awaits Ryan's decision on the `ws_depth.py` auth-boundary question), #125 (weekly-retro, leave-open-for-Ryan) and #77 (stale 07-15) — none claim this milestone. Step 0b (stranded-tape sweep): newest `tape/hourly-*` branch unchanged since the prior run's sweep (`20260721T2158Z`), nothing new to append.

**Milestone (idle-run policy (c) / honest re-verification).** The `tape/weather_books/` `>=7`-day calendar gate that has blocked Q36 since 2026-07-15 opened today — `dt=2026-07-16`..`2026-07-22` all committed (7/7). Rather than trust the 07-20 "opening under-powered" framing as still-current, I re-ran both legs fresh against current committed tape.

**Part (1) settlement-basis — STILL hard-frozen.** `python -m scripts.q36_kxtempnych_settlement_basis_probe --tape-dir tape/settlement_ledger` returns `INSUFFICIENT DATA, n_settled_events=1` (`MIN_EVENTS=10`). Independently counted: `tape/settlement_ledger/` holds exactly ONE unique settled KXTEMPNYCH `event_ticker` (`KXTEMPNYCH-26JUL1707`) across its entire history, and the family still has only `dt=2026-07-17` committed — UNCHANGED from L123's hard-freeze diagnosis. The VPS recovery (L129) does not reach this leg: `settlement_ledger` is gated at `SETTLEMENT_LEDGER_UTC_HOUR=10` and no collector has landed an hour-10 pass. (All settlement values here would be `broker_truth`; no fill price involved.)

**Part (2) microstructure — STILL structurally under-powered.** Re-derived per-market-hour capture density on all 7 committed `weather_books` days for KXTEMPNYCH `group=hourly` (distinct `capture_id` per unique market ticker/hour token). Captures-per-market-hour by day: 07-16 median 1 / mean 1.30 / max 3; 07-17 median 1 / mean 1.33 / max 3; 07-18 median 1 / mean 1.15 / max 2; 07-19 median 1 / mean 1.00 / max 1; 07-20 median 1 / mean 1.00 / max 1; 07-21 median 1 / mean 1.12 / max 2; 07-22 (post-L129-recovery, partial day) median 1 / mean 1.00 / max 1. Median is **1 on every single day**, and even the two healthy dual-collector days peak at mean ~1.3 / max 3. The VPS recovery restores per-day pass COUNT but NOT per-market-hour DENSITY — the `hourly_pass` cadence structurally caps each 60-min market at ~1 book snapshot over its whole life, so the intra-hour convergence / stale-pricing-window study Part (2) requires (depth × wall-clock-seconds of stale pricing) is unconstructible regardless of calendar-day count. All `weather_books` prices are `real_ask`-tagged; no synthetic quoted as a fill; no bootstrap run (data inadequate to attempt one).

**Verdict.** Q36 STILL GATED for BOTH parts even with the calendar gate open. Calendar-gate-open != data-adequate. Part (2) needs a DEDICATED intra-hour book collector on the KXTEMPNYCH hourly series (collector-build, Ryan/VPS-side); Part (1) needs the hour-10 `settlement_ledger` cadence restored (L123). No registry change (`kb/strategies/00-index.md` untouched), no P&L claim, no bootstrap CI — data-adequacy re-characterization, not a Q36 verdict; two-agent rule N/A (same posture as the 07-20 audit `findings/2026-07-20-q36-weather-books-data-adequacy.md`, whose numbers this run refreshes).

**Gates:** `pytest` 1403 passed; `python scripts/invariants.py --full` exit 0 (only the pre-existing non-gating L25/L109/L74 advisories). No source code, tape, or registry changed this run — docs/log only.

**Step 9 (paper sub-pass):** `SHADOW_REGISTRY`={s14_ladder_underwriting} (DEAD-at-real-fills per Q34 — dead-strategy shadow, paper-infra validation only, NOT edge evidence). `scripts/paper_pass.py` idempotent this run: 0 newly processed (daily-order cap already bit the prior run; 207 deferred-caps, 234 deferred-coverage, 93 already-in-ledger), realized P&L unchanged **+$15.05** (`broker_truth`), `paper/ledger/dt=2026-07-22.jsonl` unchanged at 359 lines. Still 0 proven edges.

## 2026-07-22 01:xx UTC — Ryan-interactive session: creds unblocked + three collectors built (Polymarket US, WS depth, hyperliquid_funding forward-refresh)

**Ryan-interactive local session** (branch `worktree-creds-unblock-and-ws-depth`; parent
session commits, not this distiller). Three things happened: credentials were unblocked, three
collectors were built (all offline-tested, all their own suites green), and one prior open item
(L127 candidate (a)) got closed.

**Credentials** (VALUES never in repo — placed on the VPS at `/root/.secrets/kalshi-headless.env`):
`POLYMARKET_US_*` verified LIVE (signed `GET /v1/markets` → HTTP 200 through
`collection/polymarket_us_live.py`'s own `auth_headers`); `POLYMARKET_CLOB_*` (international)
placed-unverified; `KALSHI_API_KEY_ID` + PEM — the PEM validates but the Key ID is rejected
`401 NOT_FOUND` on BOTH prod and demo, awaiting Ryan re-check. TWC/`api.weather.com` key
declared **DEAD** (business-only licensing) — Q36 note updated: IEM 1-min ASOS +
`api.weather.gov` are now PRIMARY and the settlement-basis probe becomes load-bearing. Ryan
OPENED the WS `orderbook_delta` build gate (GOAL.md amended; activation still key-gated).

**Built** (three collector-engineer agents): (1) `collection/polymarket_us_live.py` + 32 tests +
`ops/polymarket-us-bringup.md` + `findings/2026-07-21-polymarket-us-public-api-probe.md` — the
live probe FALSIFIED the docs' "public market data needs no key" claim (all `/v1/` data
endpoints 401 unauthenticated, only `/v1/health` open; app-level, not geo-block). Q33 → UNBLOCKED.
(2) `collection/ws_depth.py` + 21 tests + systemd unit + `ops/ws-depth-bringup.md` — archives
Kalshi's `orderbook_delta` (snapshot + every delta with `seq`), gzip'd + UTC-rotated, seq-gaps
recorded as data + forced resync. Build DONE, activation pending a working Kalshi key (Q47).
(3) `hyperliquid_funding` incremental forward-refresh wired into `hourly_pass` every pass +
`tape_gap_monitor` reclassified (one-shot-backfill → hourly STALE-only, removed from
`JOIN_CRITICAL_ONE_SHOT`) + 12 tests; live smoke appended 116 BTC + 116 ETH `broker_truth`
prints — the q42 cross-venue join now reads 1179 HL hours, 130/130 windows joined, 0
partial-excluded. **This CLOSES L127 candidate (a)** (the repair half L128 had left OPEN).

**Distilled — 7 new lessons L130–L136** (`kb/lessons/00-lessons.md`): L130 vendor "public
endpoint" docs are not load-bearing / `blocked_key` is a structural cloud-safety property
(ledger-only + test); L131 authenticated ≠ order-capable — read-only market-data signing
belongs in `collection/` (UNENFORCED collision, below); L132 a streaming seq-gap is DATA
(generalizes L23; test); L133 streaming tape needs gzip+rotation day one (test); L134
monitor classification is structure-dependent not cadence-dependent, closes L127(a) (test);
L135 incremental-append collectors need a per-observation dedup identity `(coin, time_ms)`
distinct from `capture_id` (test); L136 Python 3.9 `fromisoformat` rejects single-digit
fractional-second timestamps (UNENFORCED).

**Escalation flagged, NOT applied (docs-only pass):** the existing invariant
`inv_order_endpoints_confined` (`scripts/invariants.py`) FIRES on `collection/ws_depth.py` —
verified by calling the rule directly on the file; its `KALSHI-ACCESS-(KEY|SIGNATURE|TIMESTAMP)`
header regex catches ws_depth's read-only handshake signing. The file is untracked so `main`'s
gate is green today, but **the gate will go RED the moment ws_depth.py is committed/merged.**
Resolution (sanction ws_depth.py in the invariant's exemption tuple + a matching test, OR
relocate the signer to `execution/kalshi_client.py`) is a Ryan/parent policy call and must be
settled before merge — see L131. No registry/verdict change this session (Q33 UNBLOCKED / Q47
added are queue items, not strategy rows); `kb/strategies/00-index.md` untouched. Full suite
this session: 1467 passed, 1 pre-existing unrelated failure
(`tests/test_s17_leadlag_probe.py`, the L136 3.9-`fromisoformat` symptom, reproduces on clean
`main`).

## 2026-07-22 00:1x UTC — Idle-run (policy c): VPS collector recovered post-PR#151 — closes the L117 outage

Step 0a (history-integrity): PASS — `origin/main` HEAD `261133e`, last two commits are
`(vps)`-tagged tape passes; `kb/00-LOG.md` newest entry and newest committed tape both
2026-07-21, no rewind. Step 0 (claim-check): only open PRs are #125 (weekly-retro,
leave-open-for-Ryan) and #77 (stale, pre-dates current queue state) — neither claims
active queue work. Step 0b (stranded-tape sweep): the newest `tape/hourly-*` branch,
`tape/hourly-20260721T2158Z` (~2h old), carried **2,109** genuinely-missing lines across 6
families (1,081 `orderbook_depth`, 529 `weather_books`, 448 `sports_pairs`, 30
`polymarket_macro_pairs`, 17 `perp_tape`, 4 `crypto_hourly`) — union-appended, 0 invalid
JSON, committed with this run.

Queue re-scan: Q1-Q22 DONE/DEAD/BLOCKED-with-fix; Q23/Q24 registry-confirmed `dead ✗`
(S19/S21, despite a stale-looking second "Status: TODO" block in Q23's own prose — the
canonical `kb/strategies/00-index.md` registry, not the queue prose, settles it); Q25-Q30
DONE (S22/S23/S24/S28/S29 all `dead ✗`); Q31/Q34 DONE; Q32/Q33/Q35-build credential-blocked;
Q36 STILL GATED (`tape/weather_books/` 6/7 committed days as of this run); Q37 gated ~08-05;
Q42 part 3 BLOCKED(needs-auth); Q43 gated ~07-23/24; Q44/Q45/Q46 DONE (with non-gating
status-update trails). Q21 idea-gen's own re-eligibility condition (<3 non-blocked research
items) is technically satisfied, but the last 7 consecutive rounds (07-13→07-20) registered 0
survivors each time on an unchanged tape surface — an 8th round would not be an honest use of
this firing. **0 numbered items eligible → IDLE RUN.** UNENFORCED lessons backlog is empty
(L128) → policy (a) unavailable. Q36/Q37/Q43 already have self-activating probes prepped →
policy (b) has nothing new to prep. → **policy (c): data-quality deep-dive.**

**Finding.** Picked the single most consequential open ops question on the board: has the VPS
`:23` collector (dead since 2026-07-19, L117/L118/L126/L127) recovered after `PR #151`'s
self-healing wrapper merged (`22:37:40Z`)? **Yes — confirmed three independent ways**, not
just by reading the commit messages: (1) two fresh `vps-collector`-authored commits after the
merge (`069df6b` 22:48:18Z, `261133e` 23:31:05Z); (2) per-line `captured_at` timestamps inside
those diffs are genuinely fresh (`23:23-23:28Z`), not relabeled backfill; (3)
`scripts/tape_gap_monitor.py --now 2026-07-22T00:10Z`'s independent `collectors.vps`
breakdown (reads only committed tape, blind to commit messages) shows exactly one fresh
VPS-bucketed (`:20-29`) pass at `23:23:54Z` in its 24h window. A one-off catch-up pass landed
off-cadence at `22:41-22:48Z` before the collector re-settled into its normal `:23` phase — the
expected shape of "wedged 3 days, unwedged, resumed." See
`findings/2026-07-22-vps-collector-recovered-post-pr151.md`, new lesson **L129**.

**What this does NOT mean yet:** `under_capture` alerts on `sports_pairs`/`crypto_hourly`/
`orderbook_depth`/`weather_books`/`polymarket_macro_pairs`/`perp_tape` (ratios 0.19-0.21) have
NOT cleared — the 24h window denominator still carries the 3-day outage and will self-heal
over the next ~24-36h; `settlement_ledger` (gated `SETTLEMENT_LEDGER_UTC_HOUR=10`, no VPS
hour-10 pass yet) and `hyperliquid_funding` (never scheduled, L127 candidate (a) still open)
remain stale for separate reasons. `tape/weather_books/` is at 6/7 committed days — the Q36
gate should now open on schedule rather than staying starved. No registry change, no strategy
claim — two-agent verdict rule N/A (ops/data-quality confirmation, same posture as
L117/L118/L126/L127's diagnosis-only entries).

**Step 9 (paper sub-pass):** `SHADOW_REGISTRY={s14_ladder_underwriting}` (DEAD-at-real-fills
per Q34 — paper-infra validation only, NOT edge evidence). `scripts/paper_pass.py` processed 9
newly-eligible events from this run's own stranded-tape sweep, wrote `paper/ledger/dt=2026-07-22.jsonl`
(359 lines). Realized P&L moved **+$13.21 → +$15.05** (`broker_truth`). Still 0 proven edges.

`pytest` and `python scripts/invariants.py --full` both green (see run digest for exact
counts). No source code changed this run — tape sweep + paper ledger + docs/findings only.

## 2026-07-21 21:3x UTC — Idle-run: L128 — `hyperliquid_funding` join-staleness monitor check built + acceptance-tested (L127's monitor half converted)

Queue re-scan: no numbered item Q1-Q46 eligible (all DONE/DEAD/BLOCKED/GATED — Q36/Q43/Q37
calendar-gated, Q42 part 3 BLOCKED[needs-auth], Q21 idea-gen at repeated zero-registration
rounds, Polymarket-cred items blocked). IDLE RUN. Step 0a: PASS — `origin/main` HEAD
`2db5d3bc`, recent merges confirmed ancestors, `kb/00-LOG.md` newest entry and newest
`tape/*/dt=*` both 2026-07-21, no rewind. Claim-check: only open PRs are #125 (weekly-retro,
leave-open-for-Ryan) and #77 (stale 07-15) — neither claims eligible work. Step 0b: the 16
recent `tape/hourly-*` stranded branches (07-19..07-21, refs carry a trailing `Z`) were ALL
already union-merged into `origin/main` by the prior 07-21 15:1xZ run — 0 lines needed
appending, no tape files changed, no branches deleted; ~160 OLDER stranded branches (pre-07-19,
the long-standing Q17 backlog) remain un-swept, flagged honestly.

Idle-run policy (a): convert an UNENFORCED lesson into enforcement. The sole open UNENFORCED
lesson was L127's second half — `hyperliquid_funding` is a one-shot/backfill tape family
(`interval_h=None`, no cadence detector), frozen at a single 2026-07-17 backfill, and the ONLY
cross-venue join partner consumed by the LIVE join `scripts/q42_crossvenue_funding_join.py`, so
its silent staleness truncates that join with no age-alert. L127 named two candidates: (a) wire
a forward-refresh collector (the data FIX), and (b) a join-partner staleness DETECTOR. This run
converted the DETECTION half (b):

- `scripts/tape_gap_monitor.py`: new `JOIN_CRITICAL_ONE_SHOT = {"hyperliquid_funding":
  {"max_age_h": 48.0, "consumer": "scripts/q42_crossvenue_funding_join.py"}}` + a JOIN-STALENESS
  detector in `evaluate_family()` that appends a `join_stale` reason (through the existing
  `would_alert` path) when a JOIN_CRITICAL_ONE_SHOT family's age exceeds its `max_age_h`. The
  48h threshold is documented (the join finalizes funding windows every 8h → >48h means ~6
  windows silently dropped; mirrors the daily-family 2×24h STALE posture). All other families'
  STALE/UNDER-CAPTURE/collector-diagnosis logic untouched.
- `tests/test_tape_gap_monitor.py`: `test_one_shot_family_never_alerts` repointed to a
  non-join-critical unconfigured family (so "a family with no cadence config never pages on age"
  stays covered); added `test_hyperliquid_funding_is_join_critical`,
  `test_join_critical_one_shot_alerts_on_join_staleness`, and a HARD acceptance test
  `test_acceptance_8_l127_hyperliquid_funding_join_stale` over the REAL committed tape
  (`now=2026-07-21T18:00Z`, real newest `captured_at` 2026-07-17T06:20:03Z → age 107.67h > 48h,
  `join_stale` alert fires).

New lesson **L128** formally disposes L127's monitor half (candidate (b) → `test`); see
`kb/lessons/00-lessons.md`. Candidate (a) — wiring `collection.hyperliquid_funding` into a
scheduled incremental pass (the actual data-refresh FIX) — remains OPEN and unbuilt: it is a
real collector-build milestone (Q42-adjacent / Q38-scale), NOT a lesson-to-test conversion, so
it is flagged for Ryan / a future collector-build run, not closed here. After this run the
UNENFORCED-lessons backlog is empty again.

Gates: `pytest` 1347 passed / 0 failed; `python scripts/invariants.py --full` EXIT 0 (only the
3 pre-existing non-gating advisories — L25/L74/L109 directory-shape + daily-cadence +
stranded-branch warnings — nothing new). Two-agent verifier rule N/A (non-gating monitor
extension — no registry flip, no bootstrap CI, no kill decision; same precedent as
L118/L124/L126/L127-perp_tape). Step 9 paper sub-pass: `SHADOW_REGISTRY` non-empty
(`s14_ladder_underwriting`); `scripts/paper_pass.py` ran deterministically over committed tape,
0 events processed (216 deferred-caps, 222 deferred-coverage, 84 already-in-ledger) → NO new
ledger lines. `daily_summary()`: `paper: 0 open position(s), 661 settled contract(s), realized
P&L $+13.21, cash $+13.21, open notional $0.00` — **s14_ladder_underwriting is DEAD per Q34,
so this P&L is paper-infra validation only, NOT edge evidence.** Still 0 proven edges.

---

## 2026-07-21 18:1x UTC — Idle-run: L127 — `perp_tape` reclassified `hourly-dual` in `tape_gap_monitor.py`; `hyperliquid_funding` join-staleness flagged

Queue re-scan: still fully drained (Q36 gated ~07-22 and separately blocked on the frozen
`settlement_ledger` feed root-caused this morning; Q43 ~07-23/24; Q37 ~08-05; Q21 idea-gen at
7 consecutive zero-registration rounds with no new tape surface; lessons ledger UNENFORCED
backlog empty as of L126). Step 0a: recent merges (#144-#148) confirmed ancestors of
`origin/main` HEAD, `kb/00-LOG.md`'s newest entry and the newest committed tape both dated
07-21 — no rewind. Step 0b: newest stranded branch (`tape/hourly-20260721T1258Z`) already
swept in PR #148 — nothing new to sweep.

Idle-run policy (c) via a `tape-auditor` subagent, scoped to a family NOT touched by today's
four earlier idle-run/edge-hunter passes (`settlement_ledger`, `universe_sweep`, VPS-day-3,
`weather_actuals`). Picked `tape/perp_tape/` + its join partner `tape/hyperliquid_funding/`
(Q42/Q43's substrate, built 07-16, never audited). Two findings:

1. **`perp_tape` misclassified.** `scripts/tape_gap_monitor.py::FAMILY_CONFIG` had it as
   `one-shot-backfill` (`interval_h=None`) since build, even though `collection/hourly_pass.py`
   runs `collection.perp_tape` on every hourly pass — identical cadence to the six tracked
   `hourly-dual` families. Because a `None`-interval family skips the UNDER-CAPTURE check
   entirely, its real post-L117-VPS-death collapse (30→14→6→7→5 captures/day, 07-17→07-21,
   ~29% of nominal 48/day) was invisible — a 6th L117 victim never on Q44's list, this time
   via wrong `kind` rather than a missing entry (L123/L126's shape, new variant). **Fixed:**
   reclassified to `hourly-dual` (48/day); also added to `EXPECTED_COLLECTOR_BUCKETS` as
   `{primary: vps, secondary: other}` since its surviving collector lands at minute-of-hour
   ~00-04 (same "other" signature L120 found for `weather_books`) — without the mapping the
   real vps-dead state would read ambiguous. New HARD acceptance test anchored to real tape
   (`now=2026-07-21T18:00Z`): `alert=True`, ratio 0.146, `collector_diagnosis="vps_dead: 0
   passes in window, other collector still producing"`. One pre-existing unit test
   (`test_one_shot_family_never_alerts`) repointed from `perp_tape` to `hyperliquid_funding`
   as its remaining valid one-shot exemplar.
2. **`hyperliquid_funding` join-staleness (NOT fixed, flagged).** `perp_tape`'s only
   cross-venue join partner is frozen at a single 2026-07-17 manual backfill (108h+ stale,
   +1 day/day drift) with no collector ever wired to refresh it. `scripts/
   q42_crossvenue_funding_join.py` `EXCLUDE`s windows without an HL counterpart rather than
   erroring, so every Kalshi funding window after 07-17 silently loses its cross-venue
   reference. `hyperliquid_funding`'s `one-shot-backfill` classification is factually
   correct — the gap is that "one-shot" and "never alerted" are the same thing today, with
   no distinction for a join-critical leg going stale. Real fix (wiring a refresh collector,
   or a join-partner staleness detector) is bigger than one idle-run milestone — recorded as
   lesson L127's UNENFORCED half.

New lesson **L127** (test + UNENFORCED halves — perp_tape fixed, hyperliquid_funding flagged).
See `findings/2026-07-21-perp-tape-misclassified-hourly-dual-q42-q43.md`. No strategy claim,
no registry change — two-agent verdict rule N/A (monitoring reclassification, same posture as
L118/L121/L122/L124/L126). `pytest` full suite green (+1 acceptance test, 1 unit test
repointed). `python scripts/invariants.py --full` exit 0 (pre-existing non-gating advisories
only — `tape_gap_monitor.py` is a standalone script, not wired into the invariants gate).
Step 9: `SHADOW_REGISTRY={s14_ladder_underwriting}` only; `paper_pass.py` idempotent (0 newly
processed), realized P&L unchanged **+$13.21** (`broker_truth`; s14 DEAD-at-real-fills per
Q34 — dead-strategy shadow, paper-infra validation only, NOT edge evidence). Still 0 proven
edges.

**Next:** whoever restores VPS/live-collector cadence (Ryan-side) will make `perp_tape` (and
every other `hourly-dual` family it shares the L117 collapse with) go green on this monitor
again automatically — no further code change needed on that path.

---

## 2026-07-21 15:1x UTC — Idle-run: L126 — `weather_actuals` added to `DAILY_CADENCE_FAMILIES`, closes a real 2-day tape hole

Queue re-scan: still fully drained (Q36/Q43/Q37 calendar-gated, probes already prepped; Q21
idea-gen 7 consecutive zero-registration rounds; lessons ledger UNENFORCED backlog empty as
of L124). Idle-run policy (c) via a `tape-auditor` subagent scoped to find a genuinely-new
data-quality angle not already covered by today's 4 prior runs (which all touched hour-9/
hour-10/always-on legs). It found `weather_actuals` (hour-12 gate) has a real 2-day hole in
committed tape — `dt=2026-07-19` and `dt=2026-07-20` both missing — root-caused to the SAME
mechanism L123/L124 diagnosed for `settlement_ledger` earlier today: the live cloud
collector's post-VPS-death cron phase (`≡1 mod 3`, reconstructed from `tape/perp_tape/`)
never lands on hour 12, and the dead VPS `:23` collector (L117, still down day 3) can't pick
up the slack. The twist: `weather_actuals` was never added to `scripts/invariants.py`'s
`DAILY_CADENCE_FAMILIES` tuple — the exact detector L74/L75 built for this failure class —
so this concrete, already-realized gap was invisible to the one tool meant to catch it, even
after L123/L124 fixed the sibling family in an earlier run today.

Fix (small, additive, non-gating, mirrors L75's own posture): added `"weather_actuals"` to
`DAILY_CADENCE_FAMILIES` in `scripts/invariants.py`. Two new tests in
`tests/test_invariants.py` — a membership check and a HARD acceptance test anchored to the
real committed tape (`tests/test_acceptance_l126_weather_actuals_real_gap_detected`, pins
both `weather_actuals/dt=2026-07-19` and `dt=2026-07-20` as detected). Live-verified:
`python scripts/invariants.py --full`'s daily-cadence warning count moved 7→9 and now names
`weather_actuals`. `forecast_collector`'s parallel hour-11 freeze remains a known, documented,
out-of-scope gap (writes to gitignored `data/forecast_tape/`, never reaches committed `tape/`,
so no monitor reading only `tape/` can ever see it) — not fixed here, flagged only. New lesson
**L126** (built directly as `test`, no separate UNENFORCED row — found and fixed same run).

Step 0b: swept `tape/hourly-20260721T1258Z` (newest stranded branch, ~2h old) — 21,713 lines
across 8 families (20,000 `universe_sweep`, 1,128 `orderbook_depth`, 290 `weather_books`, 241
`sports_pairs`, 20 `weather_actuals`, 17 `perp_tape`, 15 `polymarket_macro_pairs`, 2
`crypto_hourly`), 0 invalid JSON, clean prefix match, committed separately before the
milestone commit.

`pytest` full suite green (unchanged count + 2 new). `python scripts/invariants.py --full`
exit 0 (only pre-existing non-gating advisories, daily-cadence count now 9 not 7 — expected,
that IS this run's fix taking effect). Step 9: `SHADOW_REGISTRY={s14_ladder_underwriting}`
only; `paper_pass.py` idempotent (0 newly processed), ledger unchanged **+$13.21**
(`broker_truth`; s14 stays DEAD-at-real-fills per Q34 — dead-strategy shadow, paper-infra
validation only, NOT edge evidence). No strategy claim, no registry change — two-agent
verdict rule N/A (monitoring-detector extension, same precedent as L75/L118/L121/L122/L124).
Still 0 proven edges.

**Next:** VPS collector remains dead (day 3+, Ryan/VPS-side); `forecast_collector`'s tape/
scope gap and the daily-cadence detector's now-9-family list are both flagged for whoever
runs Q36/Q37 once their calendar gates open.

## 2026-07-21 12:3x UTC — Idle-run (policy c): VPS collector still dead on day 3 + stranded-tape sweep (1,747 lines)

Research-loop run (protocol v3). Step 0a PASS: `origin/main` HEAD `c28ed49` — recent merged PRs
(#142/#144/#145/#146) all confirmed ancestors; `kb/00-LOG.md` newest entry and newest
`tape/*/dt=*` file both current 2026-07-21, no rewind. Claim-check: only open PRs are #125
(weekly-retro, leave-open-for-Ryan) and #77 (stale 2026-07-15 restock) — neither claims eligible
work. Full Q0–Q46 re-scan: 0 eligible TODO/IN-PROGRESS items (Q36/Q43/Q37 all still calendar-
gated, probes already prepped; Q21 idea-gen already hit its 7th consecutive zero-registration
round 2026-07-21 04:15Z) → IDLE RUN. Idle-policy (a) empty (UNENFORCED backlog cleared by
L123→L124 this morning); (b) exhausted (every gated item's probe already self-activating); took
**(c)**.

**Step 0b sweep.** Checked the 3 newest `tape/hourly-*` fallback branches from today
(`20260721T0105Z`/`0705Z`/`0956Z`, all >30min old): the first two were already fully absorbed
(0 missing lines — confirmed by the 04:15Z edge-hunter run and this run respectively); the third
(`20260721T0956Z`, ~2.5h old) carried **1,747 genuinely-missing lines** across 9 families
(1,145 `orderbook_depth`, 290 `weather_books`, 248 `sports_pairs`, 24 `polymarket_cpi_pairs` [new
file], 17 `perp_tape`, 15 `polymarket_macro_pairs`, 5 `econ_prints`, 2 `crypto_hourly`,
1 `anomalies`) — line-set union-appended (0 duplicates, all valid JSON, verified by re-parsing
every appended line). Did not attempt a full re-sweep of the ~170 older stranded branches this
run (the known Q17/PR#46 backlog, Ryan-review-only, repeatedly confirmed fully redundant by prior
runs — re-diffing all of them line-by-line via per-file `git show` proved too slow for one run's
budget and was aborted after ~20min with 0 branches fully processed; left for a future run or a
purpose-built script, not blocking this milestone).

**Data-quality finding (the run's real work) — VPS collector confirmed STILL dead, now a 3rd
calendar day.** `findings/2026-07-20-tape-cadence-decline-vps-collector-down.md` root-caused the
VPS `:23` cron (87.99.146.250) as dead starting 2026-07-19; the 07-21 04:15Z edge-hunter run
separately found `settlement_ledger` frozen for a related reason. This run's question: has the
VPS collector recovered? Independently re-derived minute-of-hour attribution over the
currently-committed tape (fresh script, not a re-run of the 07-20 code): **zero VPS-signature
(`:2x`) lines on 07-19, 07-20, AND 07-21** across `crypto_hourly`/`orderbook_depth`/
`sports_pairs`/`polymarket_macro_pairs` — no recovery. Cross-checked against a live
`tape_gap_monitor.py --no-notify` run: independently confirms `vps_dead` for all four, plus
`settlement_ledger` 96.0h stale and `weather_actuals` 71.4h stale. Cumulative `orderbook_depth`
loss estimate ≈49,000 lines over the 3 missing days (the largest-volume family in the repo).
No fix applied — VPS-side only, out of reach for any cloud run; escalated to Ryan (phone note,
`Priority: high`) since this is now an unresolved outage spanning two research-loop cycles and
one edge-hunter cycle without a status change. See
`findings/2026-07-21-vps-collector-day3-still-down.md`; `LOOP-QUEUE.md` Q44 status update.

No strategy claim, no registry change — two-agent verdict rule N/A (data-quality/ops diagnosis,
same tier as the 07-20/07-21 findings it extends). `pytest`: 1341 passed (unchanged — tape/docs-
only diff). `python scripts/invariants.py --full`: exit 0 (only the pre-existing non-gating
advisories: 174 stranded-branch refs, 4 dir-shaped `dt=`, 7 daily-cadence gaps). **Step 9:**
`SHADOW_REGISTRY`={s14_ladder_underwriting} only; `paper_pass.py` re-run against the freshly-
appended tape is idempotent (0 newly processed — the 2 new `crypto_hourly` lines aren't
S14-eligible), realized P&L unchanged **+$13.21** (`broker_truth`; S14 stays DEAD-at-real-fills
per Q34 — proxy P&L, not proven edge). Still **0 proven edges**.

## 2026-07-21 09:2x UTC — Idle-run (policy c): `universe_sweep` liquidity census — ~97% dead-tail auto-generated multi-leg artifacts

Queue fully drained again (Q36/Q43/Q37 still calendar-gated, no numbered item eligible) and the
UNENFORCED lessons backlog is empty after L124 — so this idle firing took idle-policy (c), a
data-quality deep-dive, on the one tape family accumulating fastest and most expensively:
`tape/universe_sweep/`. Ran `scripts/universe_sweep_liquidity_census.py` over all five committed
daily files (`dt=2026-07-17`..`dt=2026-07-21`, 5 files / **300,000 lines** / **0 malformed**,
100% `real_ask`, NO network).

**Finding.** Pooled, only **3.03%** of lines are FILLABLE (`yes_ask>0 AND yes_ask_size>=1`,
n=9,098), **2.89%** LIQUID (size>=10), **10.84%** have any ACTIVITY (`open_interest>0 OR
volume>0`; `volume_24h>0` is effectively 0.00% — ~5/300k rows — the same always-zero schema
defect L96 named, now confirmed across the full history). The **96.97% dead tail** (290,902
lines) is dominated by two auto-generated multi-leg series: `KXMVESPORTSMULTIGAMEEXTENDED` =
**82.21%** of the whole census, `KXMVECROSSCATEGORY` = **14.68%** (together ~96.9%); every other
series is <0.02%. Per-day fillable% swings (07-17 5.32% / 07-18 2.50% / 07-19 0.97% / 07-20
3.97% / 07-21 1.59%) and is unstable pass-over-pass within a day (07-18 0.62%–8.09%, 07-20
1.49%–7.97%) — because each capped 20-call pass reaches a different arbitrary slice of the
>80k-market cursor (L96 disjoint-slice property), a single pass is not a reliable liquidity
estimate.

**Answer to Q46 design call (b) — "add an activity/liquidity discovery filter" (Ryan-gated).**
Filtering at capture time to the ACTIVITY tier retains **10.74% of bytes** (~71 MB/day →
~7.6 MB/day); to FILLABLE **2.89% of bytes** (~2 MB/day); to LIQUID **2.76%**. So an
activity/liquidity discovery filter would cut this family's storage **~89% (activity) to ~97%
(fillable/liquid)** while dropping only no-offer / no-activity KXMVE* artifacts. This is
design-input only — **NO code/collector change to `universe_sweep` this run** (the cadence +
filter decision stays Ryan-gated per Q46's DONE verdict).

**Interpretation (honest).** Generalizes **L105** from a single day (07-19, anomaly-sweep use
case) to the full 5-day history + the whole-census fillable question + the storage lens, and
restates the L96/L105 illiquidity floor for the storage-decision use case. NOT a strategy claim —
the opposite: the breadth census is ~97% un-tradeable auto-generated multi-leg no-offer
artifacts; a cross-sectional consumer must filter to the fillable/active ~3–11% before treating a
line as a quote. New lesson **L125** (documentation/house-style — a census fact, not statically
assertable). Also did a ledger-hygiene pass: L25's and L120's enforcement cells still read
`UNENFORCED` although both candidates are now built (L25 → `scripts/invariants.py`'s
`_tape_dir_shape_issues`/`tape_dir_shape_warning` non-gating advisory, formally superseded by L29;
L120 → `scripts/tape_gap_monitor.py`'s `EXPECTED_COLLECTOR_BUCKETS`/`diagnose_collector`, PR #142,
superseded by L122) — corrected those two stale enforcement markers in place (lesson text
unchanged, original candidate wording preserved).

Finding: `findings/2026-07-21-universe-sweep-liquidity-census.md` (cites
`scripts/universe_sweep_liquidity_census.py` + `findings/universe_sweep_liquidity_census.json`).
No strategy claim, no registry change, two-agent verdict rule advisory (verifier pass PENDING at
write time — data-quality characterization, re-derivable from committed tape by the one-line
reproduce command). **Gates:** `pytest` **1341 passed** / `python scripts/invariants.py --full` exit 0
(pre-existing non-gating advisories only: 2 local stranded-branch, 4 directory-shaped-dt +
2/2 GC-classified, 7 daily-cadence-gap; research-lead to confirm on the final tree). **Step 9 paper:** `SHADOW_REGISTRY`={s14_ladder_underwriting}
only, `paper_pass.py` idempotent (no paper-relevant tape touched), realized P&L unchanged
**+$13.21** (`broker_truth`; s14 DEAD-at-real-fills per Q34, proxy P&L not an edge).

**Concurrent-collector hygiene note (for Ryan).** An external hourly-collector hour-9 pass wrote
`tape/anomalies` + `tape/econ_prints` lines into the shared tree while this run was working —
excluded from this commit (not this run's milestone; the same "don't let a background collector
collide with a direct edit" hygiene the Q46 build already flagged).

See `findings/2026-07-21-universe-sweep-liquidity-census.md`, `kb/lessons/00-lessons.md` L125.

---

## 2026-07-21 06:1x UTC — Idle-run (policy a): L123→L124 — settlement_ledger registered in tape_gap_monitor

Queue fully drained again (Q36/Q43/Q37 still calendar-gated, no numbered item eligible).
Top of the idle-run priority order: convert the sole open UNENFORCED lesson. **L123**
(filed by last night's edge-hunter run) named the mechanism behind the settlement_ledger
freeze it root-caused: a once-per-UTC-day collector gated on an exact hour (`ts.hour ==
N`) silently stops forever the moment the live cron never lands on hour `N` — no error,
no catch-up, just a tape family that quietly stops growing.

`scripts/tape_gap_monitor.py` exists precisely to catch dead collector legs, but
`settlement_ledger` was never added to its `FAMILY_CONFIG` — an unconfigured family's
STALE detector is a structural no-op (`interval_h=None` skips the age check; the family
reports a bare "ok" regardless of how long it's been silent). That's the actual reason
the freeze was invisible: not a detector bug, a missing registration. Added
`"settlement_ledger": {"interval_h": 24.0, "passes_per_day": 1, "kind": "daily"}` (same
shape as the already-tracked `weather_actuals`), which turns the STALE detector on with
zero other logic changes. A new real-tape acceptance test
(`tests/test_tape_gap_monitor.py::test_acceptance_6_l123_settlement_ledger_frozen_since_build_day`)
runs the monitor over the actual committed `tape/settlement_ledger/dt=2026-07-17.jsonl`
at `now=2026-07-21T06:00Z` and confirms it now alerts `stale` at ~89.6h since the last
real capture — the monitor genuinely catches the freeze this run's predecessor found by
hand.

`forecast_collector`'s parallel single-hour freeze (also named in L123,
`FORECAST_COLLECTOR_UTC_HOUR=11`, also outside the every-3h cron's hour set) is **not**
fixed by this change — it writes to gitignored `data/forecast_tape/`, outside `tape/`
entirely, so it's structurally outside this monitor's read surface. Flagged, not silently
dropped.

New lesson **L124** supersedes L123 (`UNENFORCED` → `test`). Lessons ledger's UNENFORCED
backlog is empty again. No strategy claim, no registry change, non-gating (standalone
script, not wired into `scripts/invariants.py`) — two-agent verdict rule N/A, same
precedent as L118/L121/L122. `pytest` full suite green, `invariants --full` exit 0
(only pre-existing non-gating advisories: 1 local stranded tape/hourly-* ref, 4
directory-shaped dt= paths, 7 daily-cadence gaps). Step 9: `SHADOW_REGISTRY` unchanged,
`paper_pass.py` idempotent (0 newly processed, no new tape since the last sub-pass),
realized P&L unchanged **+$13.21** (`broker_truth`; s14 stays DEAD-at-real-fills per Q34).

Step 0b: spot-checked the two newest stranded branches (`tape/hourly-20260721T0105Z`,
`tape/burst-20260714T120659Z`) against `main` — both fully subsumed, 0 missing lines.
The ~190-branch historical backlog is undeleted-but-already-swept debris, not re-verified
line-by-line this run (would cost far more than the run's actual milestone).

See `kb/lessons/00-lessons.md` L124, `scripts/tape_gap_monitor.py`,
`tests/test_tape_gap_monitor.py`.

---

## 2026-07-21 04:15 UTC — kalshi-edge-hunter (nightly): review PASS + settlement_ledger frozen-since-build finding

Nightly Opus thinking-seat run. Steps 0a/0/0b done first. **0a PASS** — the `git pull` showed a `origin/main` forced-update (the known stale-local-cache artifact, PR #137 precedent); verified real ancestry: recent squash-merge commits (`6af7e65`/`4b3bcd6`/`7bad144`/… = PRs #142/#141/#140) all confirmed ancestors of `origin/main` HEAD `36268eb`, and `kb/00-LOG.md` + newest `tape/*/dt=*` both current 2026-07-21 — no rewind. **0b** — newest fallback branch `tape/hourly-20260721T0105Z` already fully absorbed (all deltas are deletions = branch is a subset of main; swept by PR #142); nothing to sweep. Open PRs: #125 (weekly-retro, leave-open-for-Ryan) and #77 (stale restock) — neither claims eligible work, and both were named in prior nights, so NOT re-flagged (per the do-not-retrain-the-channel rule).

**Unit 1 — adversarial review of the last 24h findings: PASS.** Three findings dated in-window (`2026-07-20-q21-idea-gen-round`, `-q36-weather-books-data-adequacy`, `-tape-cadence-decline-vps-collector-down`) — all data-quality/idea-gen, no new strategy verdicts (no CI, no registry flip) to attack. Re-checked one load-bearing number per data finding directly against committed tape: (a) Q36's `KXTEMPNYCH settled events = 1` → reproduced exactly (`KXTEMPNYCH-26JUL1707`, 10 strikes → 1 distinct event); (b) the VPS-death claim → `crypto_hourly` VPS-bucket (min 20-29) = 18 lines on 07-18 then **0** on 07-19/20/21 while the cloud bucket persists — confirmed. Nothing failed; no issue opened.

**Unit 2 — pipeline replenishment: 0 eligible items, and NO new tape surface since the 07-18 round → 7th consecutive zero idea-gen round, recorded honestly (never pad to quota).** Surveyed every `tape/*` family's date span: no new FAMILY has landed since 07-18; the only accumulating families (`universe_sweep` 07-17..21, `perp_tape` 07-17..21) feed already-queued items (Q46 done, Q43 gated ~07-23). The documented graveyard (taker-into-overround S1/S5/S7, maker-fee-swamp S6/S13/S23, unprovable-queue S19/S21, cross-venue-two-fee S34, universe_sweep-no-strike-fields/complement-artifact S41/S44, econ n=1 S43, crypto settlement_ledger zero-overlap S45) forecloses every re-skin of the current surface — same conclusion the 6 prior rounds + their verifier attacks reached. Redirected the unit to the higher-value data-quality deep-dive below (idle-policy (c)).

**Data-quality finding (the run's real work) — `settlement_ledger` is frozen at its build day; Q36's settlement gate can never advance on calendar time.** `tape/settlement_ledger/` has produced exactly one dt (`2026-07-17`, 5605 rows) in the ENTIRE git history (`git log --all` confirms) and nothing since. Root cause: the leg is gated at `SETTLEMENT_LEDGER_UTC_HOUR=10` (exact-hour equality), but the live `kalshi-collector` routine runs `cron: 53 */3 * * *` — **every 3h at UTC {0,3,6,9,12,15,18,21}, so it NEVER runs at hour 10** (nor 11, the forecast leg) — and the VPS `:23` collector that could is dead since 07-19 (L117). Hour 10 lands no pass on any of 07-18/19/20/21 (verified). This is a **routine-cadence × gate-hour mismatch** (the single-hour legs assume the HOURLY collector `ops/ROUTINES.md` still lists as desired state) compounded by no catch-up — NOT the "under-powered density" the 2026-07-20 audit reported. Consequence: Q36 (weather revival — a Ryan priority) needs ≥10 settled KXTEMPNYCH event-hours from this feed; it is stuck at 1/10 and cannot advance until the collector actually lands a pass at hour 10. Independent `verifier` CONFIRMED both counts, closed the stranding hypothesis (no post-07-17 branch lands at hour 10), and confirmed `settlement_ledger` is Q36's sole feed. New lesson **L123** (UNENFORCED): a once-per-day exact-hour-gated leg silently freezes if the scheduler misses that hour — enforce via an "each daily leg produced a dt within N days" advisory, or widen the gate to `ts.hour >= N and not-yet-written-today`. Finding: `findings/2026-07-21-settlement-ledger-frozen-hour10-deadzone.md`. No fix applied — the primary fix (restore collector cadence to match `ops/ROUTINES.md`) is Ryan/VPS-side, and rewriting 3 live-leg firing gates unattended at 04:15 exceeds the additive-collector self-merge precedent.

**Unit 3 — probe-prep: nothing to build.** Gated items opening within ~72h (Q36 ~07-22, Q43 ~07-23/24) and Q37 (~08-05) all already have self-activating probes built + offline-tested; verified by file-shape (L25) that none has opened. The actionable output for Q36 is the collector finding above, not a probe.

**Housekeeping.** Stranded `tape/hourly-*` branches: **172** (+1 `tape/burst-*` = 173 total) — the known can't-delete-from-cloud backlog (Q17/PR #46, Ryan-side). Burst triggers with passed events (name for deletion, retro-owned): `kalshi-burst-cpi-0714`, `-wcsemi1-0714`, `-wcsemi2-0715`, `-wcfinal-0719` (all fired; re-scheduled to 2027 as annual no-ops); `kalshi-burst-fomc-0729` upcoming, keep. Also surfaced (retro's drift-check remit): live `kalshi-collector` = every-3h, `ops/ROUTINES.md` desired = "hourly :53" — drift, and the direct cause of the settlement_ledger freeze.

**Gates:** docs/findings/lessons only, no code. `pytest -q` and `python scripts/invariants.py --full` re-run green before commit (pre-existing non-gating advisories only). **Step 9 paper:** `SHADOW_REGISTRY`={s14_ladder_underwriting} only; diff touches no paper-relevant tape → idempotent, ledger unchanged **+$13.21** (`broker_truth`; s14 is DEAD-at-real-fills per Q34 — proxy P&L, NOT edge evidence). **Still 0 proven edges.**

---

## 2026-07-21 — Idle-run (policy a): L120→L122 — tape_gap_monitor per-family expected-collector-bucket map

Research-loop idle run (protocol v3), IDLE-RUN policy order (a): convert the sole open UNENFORCED lesson into an enforced test, following the L117→L118 precedent (a `scripts/tape_gap_monitor.py` extension + offline tests; non-gating reliability monitor, so the two-agent verifier rule does NOT apply — same tier as L118/L104/L110).

**UNENFORCED queue re-derivation.** Whole-word grep over `kb/lessons/00-lessons.md` (the L108/L112/L116/L118/L121 method, tracing each `**UNENFORCED**`-column row's later disposition — incl. the L33/L34/L35/L49 "built-the-helper" closures that don't use the word "supersedes") → open set was exactly `{L120}`. Converted it; the set is now `{}` (empty) after L122.

**What L120 asked for + what was built.** L118's `collector_diagnosis` only ever names `vps_dead`/`cloud_dead` and reads `vps=0 & cloud=0` as ambiguous — permanently blind to a family like `weather_books` whose SECOND live collector fires at minutes ~00-03 (`other`, not the `:5x` cloud window). Added `EXPECTED_COLLECTOR_BUCKETS`, a per-family `{primary, secondary}` map **calibrated against the REAL committed-tape minute histograms** (read `tape/<family>/dt=2026-07-18..20`, not guessed): `weather_books = {primary: vps, secondary: other}` — 07-18 vps=4098 lines / other=2410, then 07-19 & 07-20 vps=0 while other persists (2940 / 3278), so the VPS primary died 07-19 and `other` is the survivor. Read `crypto_hourly` as the dual-cron anchor (primary :23 vps / secondary :54-55 cloud) and deliberately left it OUT of the map: its secondary is the already-named `cloud` bucket, so L118 attributes it correctly with no override needed (same for orderbook_depth/sports_pairs/polymarket_*). New helper `diagnose_collector(family, collectors)` routes a MAPPED family through primary/secondary (names `{dead}_dead: 0 passes in window, {alive} collector still producing` when exactly one expected bucket is zero) and an UNMAPPED family through L118's EXACT vps/cloud logic — zero regression. Both-expected-zero and both-expected-nonzero stay unattributed, preserving L118's "never guess when ambiguous" discipline.

**Enforcement form.** `test` — `tests/test_tape_gap_monitor.py` net +6 tests (mapped dead-primary, mapped dead-secondary, mapped both-healthy, mapped both-expected-zero, unmapped-other-only-stays-None no-regression, the `diagnose_collector` helper directly) plus a 5th HARD acceptance test anchored to the real 2026-07-19 weather_books VPS drop (`now=2026-07-20T00:30Z`: vps=0, cloud=0, other>0 → `vps_dead: 0 passes in window, other collector still producing`, and crypto_hourly's unmapped attribution unchanged). Non-gating (`tape_gap_monitor.py` is a standalone reliability script, not wired into `scripts/invariants.py`). No network in the health path (committed tape only), no `execution/` import, ntfy URL still only from `--ntfy-url`/env. No strategy claim, no registry change. `pytest` 1331 green (1325 prior + 6), `python scripts/invariants.py --full` exit 0 (pre-existing non-gating advisories only).

## 2026-07-21 — Idle-run (policy a): L119→L121 — shared `book_notional_at_touch` helper + units sanity check

Research-loop run (protocol v3). Steps 0/0a/0b done by the calling session (queue fully drained: every numbered item DONE/BLOCKED/time-gated, and Q21 idea-gen hit its 6th consecutive zero-registration round 2026-07-20 with no new tape surface — re-running unproductive, so this is an IDLE RUN). Idle-run policy order (a) — convert an UNENFORCED lesson — is top-priority and the one used here.

**UNENFORCED queue re-derivation.** Whole-word grep over `kb/lessons/00-lessons.md` (the L108/L112/L116/L118 method) → open set is exactly `{L119, L120}`, both filed 2026-07-20 by the Q36 weather_books audit. Converted the lower-numbered **L119** per the established convention; **L120** stays open (no reachability/priority argument to jump it, unlike L116's explicit L66 skip).

**Milestone — the shared helper L119 said did not exist.** L119's own candidate noted "no shared helper computes this metric yet, so there is nothing to anchor a static assert to." Built it: `core/pricing.py::book_notional_at_touch(price_dollars, size)` returns `price_dollars * size` (never `/100` — the L119 trap: a Kalshi `_dollars` price parsed via `core.kalshi_fields.parse_kalshi_numeric` (L90) is ALREADY dollars, so a reflexive `/100` understates book depth ~100x, the exact bug that read Q36 medians as $2.3-$19.7/market-hour when the truth was $215-$1,968). It carries an inline non-gating `UserWarning` units sanity check (fires when `0 < notional < LOW_TOUCH_NOTIONAL_WARN_DOLLARS` ($50), the fingerprint of a cents-vs-dollars mistake; a zero/empty touch stays silent; `warn_if_implausibly_low=False` silences it for a genuinely thin market). Home is `core/pricing.py` — the sanctioned price-arithmetic site (Hard Rule #3's only-arithmetic file), a natural sibling of `fee_per_contract`/`true_arb_edge`, not a bolted-on module. No live hand-rolled `price*size/100` exists in committed code to repoint (L119 records the buggy draft metric was omitted from the final finding rather than wired in) — the deliverable is the importable helper so the NEXT script calls it.

**Enforcement form.** Non-gating advisory, not a raising assert (repo default for anything short of a hard data-integrity violation — same posture as L100/L109/L110's `scripts/invariants.py` advisories; a legitimately thin market can sit below $50, so a hard gate would false-positive). Pinned by `tests/test_pricing_book_notional.py` (8 tests): correct `price_dollars * size` computation, a regression that a reintroduced `/100` is caught (off by exactly 100x), the L119 real-numbers case ($215 not $2-$19), and the sanity warning firing/silent/disabled/boundary behavior.

New lesson **L121** (`kb/lessons/00-lessons.md`) supersedes L119's enforcement column (`UNENFORCED` → `test`). The now-open UNENFORCED set is exactly `{L120}`. No strategy claim, no registry change (`kb/strategies/00-index.md` untouched), no `execution/` code, no network/credentials — two-agent verdict rule N/A (same "test"/"protocol, encoded" tier as L108/L112/L116/L118, not a verdict-class change). See `findings/2026-07-20-q36-weather-books-data-adequacy.md` for L119's origin.

**Gates.** `pytest` → 1325 passed (1317 prior + 8 new). `python scripts/invariants.py --full` → exit 0 (only the pre-existing non-gating advisories: stranded-ref, dir-shape/GC-classification, daily-cadence gaps — all already known, none introduced by this run).

---

## 2026-07-20 — Idle-run (policy c): Q36 weather_books data-adequacy audit — gate opens under-powered

Research-loop run (protocol v3). Steps 0/0a done by the calling session: last 5 merged PRs
(#134-#138) all confirmed ancestors of `origin/main` HEAD `51c3a0d`; `kb/00-LOG.md`'s newest
entries and the newest `tape/*/dt=*` files both dated 2026-07-20 — no rewind. Open PRs #125
(retro, "LEAVE OPEN for Ryan") and #77 (stale restock) — neither claims eligible work. Step
0b: newest `tape/hourly-*` branch is `tape/hourly-20260720T1257Z`, already fully swept by
PR #137 — nothing new to sweep this cycle.

Full Q0-Q46 re-scan: **0 eligible TODO/IN-PROGRESS** (8th idle firing in the sequence).
Idle-policy (a) empty (L118's own row: "The lessons ledger's UNENFORCED backlog is now empty
as of this row"). Idle-policy (b) already covered every fixture-preppable gated item today
(Q37, Q43 both prepped in earlier firings; Q36 part 2 needs the gated `weather_books` depth
history directly, nothing safe to prep against fixtures alone). Dropped to idle-policy (c):
a data-quality deep-dive on a tape family untouched by today's earlier runs — chose
`tape/weather_books/`, since L117/L118 characterized the VPS-death's effect on
crypto/sports/perp tape but nobody had checked whether it also hit the family Q36's own gate
depends on, or whether the calendar gate opening (~2026-07-22) would actually mean adequate
data.

**Finding:** it will not. Per-day pass density on `tape/weather_books/` collapsed ~80%
(28-31 passes/day → 6/day) starting 2026-07-19, the same dead-VPS-cron root cause L117/L118
diagnosed elsewhere. KXTEMPNYCH's own captures-per-market-hour is median 1 / mean ~1.2-1.3
(max 3) — too sparse for Q36's microstructure leg regardless of calendar-day count.
Separately, Q36's settlement-basis leg is blocked on `n_settled_events=1` vs
`MIN_EVENTS=10` (only one KXTEMPNYCH event-hour has ever settled in the committed
`tape/settlement_ledger/`), confirmed by running `scripts/q36_kxtempnych_settlement_basis_probe.py`
directly against committed tape (it correctly reports `INSUFFICIENT DATA`, not a fabricated
verdict). `tape/weather_actuals/` (the ASOS cross-check) has been dark since 07-18.
`tape/weather_books/` itself is now 72M, already past `tape/README.md`'s 50MB
external-storage decision point — flagged for Ryan.

Two independent `verifier` passes re-derived every load-bearing number directly from raw
committed JSONL (day/line counts, `capture_id`-based pass density + minute-of-hour
bucketing using `scripts/tape_gap_monitor.py`'s own `collector_bucket()`, KXTEMPNYCH
coverage/depth histograms, and by executing the Q36 probe script itself) — both CONFIRMED
every claim exactly. One pass additionally caught a 100x units bug in a draft supplementary
"book notional at touch" descriptor (divided by 100 twice); that metric was omitted from the
finding rather than fixed in place, since it was never part of the gate-adequacy conclusion.
See `findings/2026-07-20-q36-weather-books-data-adequacy.md`, lessons **L119** (book-notional
units sanity-check candidate) and **L120** (monitor blind-spot: a family whose sole surviving
collector lands outside both named vps/cloud minute buckets can't be told apart from "healthy
other-leg" by `collector_diagnosis` alone).

No strategy claim, no `kb/strategies/00-index.md` change — this is a gate-adequacy
characterization, not a Q36 verdict. Q36's own Status line updated to record the
under-powered-gate warning so whoever runs it on ~07-22 doesn't trust the calendar count
alone.

Gates: `pytest -q` → 1317 passed (unchanged from PR #138 baseline — this run added no new
Python code, docs/findings/lessons only). `python scripts/invariants.py --full` → exit 0
("invariants: all green"; only pre-existing non-gating advisories: dir-shape/GC L25/L109,
daily-cadence gaps L74).

Step 9 — paper sub-pass: `SHADOW_REGISTRY`={s14_ladder_underwriting} only; this run's diff
doesn't touch any tape the paper broker reads, so `paper_pass.py` is idempotent (0 newly
processed). Realized P&L unchanged **+$12.10** (`broker_truth`; S14 stays DEAD-at-real-fills
per Q34, proxy P&L not an edge). Still 0 proven edges.

Next: the VPS collector remains down (Ryan/VPS-side fix, outside cloud-run scope) and is now
confirmed to be degrading weather_books specifically, not just the crypto/sports/perp
families L117/L118 already flagged; a future run should re-check Q43's perp gate (~07-23/24)
and Q36's weather gate (~07-22) for the same under-powered-on-open pattern before trusting
either verdict.

---

## 2026-07-20 — Idle-run (policy b): Q33 Polymarket-US book-capture collector built (self-activating, credential-gated)

Research-loop run (protocol v3). Steps 0/0a done by the calling session: `origin/main` HEAD `9c21a5b` (tape hourly pass 2026-07-20T16:02:45Z) matched local, no rewind; open PRs #125 (retro, "LEAVE OPEN for Ryan") and #77 (stale queue-restock) — neither claims eligible work.

Step 0b — stranded-tape sweep: **0 genuinely-missing lines**. Checked today's 4 fallback branches (`tape/hourly-20260720T{0354,0704,095513,1257}Z`) by exact line-set diff against `origin/main` — all fully absorbed (main HEAD at 16:02Z supersedes them; the prior run's T1257Z sweep plus subsequent hourly main-pushes brought main current). Spot-checked older branches (`tape/hourly-20260719T{2156,1856}Z`) and the lone burst branch (`tape/burst-20260714T120659Z`) — also 0 missing. Known Q17 pattern (branches absorbed but not deleted; deletion is Ryan-side, not a cloud-run job).

Full Q0–Q46 re-scan: **0 eligible TODO/IN-PROGRESS** (7th idle run in the sequence). Confirmed by reading each candidate's prose: Q19's remaining legs (WC-semi1/WC-final trigger-fired-but-never-captured = Ryan-side infra gap; FOMC Jul 29 = 9 days out), Q36 part 2 / Q37 / Q43 all date-gated with prep already built, Q42 part 3 / Q32 / Q33-live / Q35-build all credential/auth-blocked, Q21 idea-gen is the nightly edge-hunter's item (round #6 completed earlier today, "never pad to quota"). Idle-policy (a) exhausted: 0 rows with current `UNENFORCED` enforcement in `kb/lessons/00-lessons.md` (L118 superseded L117, L116 closed L66).

Idle-policy (b) — chose Q33's collector: it was UNBUILT and Q33's own text explicitly sanctions idle-run agents building the offline-tested, self-activating collector skeleton ("NONE may fetch live Polymarket US data until the credential appears"). Delegated to `collector-engineer`; lead independently reviewed the diff and re-ran both gates (did not trust the agent's self-report).

Milestone: `collection/polymarket_us_pairs.py` + `tests/test_polymarket_us_pairs.py` (15 offline tests) + `hourly_pass.py` wiring (+5 tests in `tests/test_hourly_pass.py`). Credential-gated (`POLYMARKET_US_API_KEY` presence only; value never printed/logged), `blocked_key` no-op = the only cloud-reachable path (live smoke wrote nothing, created no tape dir — the honest deliverable, NOT a gap; fabricating a `real_ask` line to "show a pass" would violate provenance). Present-credential path snapshots the Polymarket-US (QCEX) book tagged `real_ask` into the distinct `tape/polymarket_us_pairs/` family with bitemporal + raw-bytes-sha256 provenance and honest no_book/book_error accounting; network ops are injectable, defaults are VPS-bring-up stubs that raise. READ-ONLY, no `execution/` imports, no order verbs, no hardcoded fee (Hard Rule #3 clean). Soft-unblocks the Q32/Q35-build collector prerequisite (still gated on the live credential). Judgment calls flagged: no_book non-gating (structural US-subset difference); default discovery/fetch stay VPS-injected stubs because mapping question-identity -> US market/token id needs the KYC'd client.

No strategy claim, no `kb/strategies/00-index.md` change, no `findings/` — two-agent verdict rule N/A (collector build, Q44/Q45/Q46 precedent).

Gates (independently re-run by the lead): `pytest -q` rc=0, **1317 passed** (1298 prior + 19 new). `python scripts/invariants.py --full` exit 0 ("invariants: all green"); only pre-existing non-gating advisories (stranded-ref, dir-shape/GC-classification L25/L109, daily-cadence gaps L74).

Step 9 — paper sub-pass: `SHADOW_REGISTRY`={s14_ladder_underwriting} only. `paper_pass.py` idempotent (0 newly processed, 224 deferred-caps, 222 deferred-coverage, 76 already-in-ledger; 0 new ledger lines). Realized P&L unchanged **+$12.10** (`broker_truth`, `daily_summary`: "paper: 0 open position(s), 551 settled contract(s), realized P&L $+12.10, cash $+12.10, open notional $0.00"). S14 is DEAD-at-real-fills (Q34) and its `fill_model` is the L39/L85 candle-through proxy — paper-INFRA validation ONLY, never edge evidence. Still 0 proven edges.

Next: the Q33 live fetch stays credential-blocked (Ryan/VPS-side Ed25519 bring-up); the next idle run either finds a fresh queue item, re-checks whether Q43's perp gate (~07-23/24) has opened with adequate per-day density (VPS `:23` cron still dead per L117/Q44), or drops to idle-policy (c)/(d).

---

## 2026-07-20 — Idle-run (policy a): L117→L118 — `tape_gap_monitor.py` now names WHICH collector died

Research-loop run (protocol v3). Steps 0/0a: `git fetch` needed a forced/non-fast-forward update to move this container's cached `origin/main` ref, momentarily matching the step-0a "main rewound" signature — checked against the real GitHub history instead of trusting the stale local cache: the last 10 merged PRs (#127-#136) form an unbroken base-SHA chain to `origin/main` HEAD `ecdac56`, and `kb/00-LOG.md`'s newest entry (this file, dated 2026-07-20) matches the newest `tape/*/dt=*` content — no actual rewind, just a stale local branch pointer from an earlier container snapshot. Reset local `main` via `git checkout -B main origin/main`, no work lost. Open PRs unchanged: #125 (retro, leave-open-for-Ryan) and #77 (stale queue-restock) — neither claims eligible work.

**Step 0b — stranded-tape sweep.** One branch younger than the last sweep, `tape/hourly-20260720T1257Z` (>2h old), carried **248** genuinely-missing lines: 231 `sports_pairs`, 15 `polymarket_macro_pairs`, 2 `crypto_hourly` — prefix-verified pure append, JSON-validated (0 invalid).

**Full Q0–Q46 re-scan: 0 eligible TODO/IN-PROGRESS** (fifth idle run today; nothing crossed a time-gate since the prior firing 3h ago). Idle-policy (a): the immediately-prior run filed lesson **L117** (UNENFORCED) after root-causing the tape cadence decline as a dead VPS `:23` cron — it proposed but didn't build a minute-of-hour bucketing extension to `scripts/tape_gap_monitor.py` so the monitor could name WHICH of the two staggered collectors died, not just report an aggregate under-capture ratio. That's the only open UNENFORCED row, so this run built it.

**Milestone — collector attribution in `tape_gap_monitor.py`.** Added `collector_bucket(dt)`: classifies a capture timestamp's minute-of-hour into `vps` (20-29, the VPS `:23` cron's jitter range), `cloud` (50-59, the cloud `:53` trigger's), or `other` — calibrated against real committed-tape minute histograms (`crypto_hourly`/`sports_pairs`/`orderbook_depth`/`polymarket_macro_pairs` cluster cleanly at :23/:54-59; never forced into a bucket when they don't). `FamilyAggregate` now tracks window passes per bucket (`collector_summary()`); `evaluate_family` attaches a `collectors` breakdown to every `hourly-dual`-kind family's health record and, when the family alerts with exactly one bucket empty while the other still produces passes, names the dead one via `collector_diagnosis` (`vps_dead`/`cloud_dead`) folded into `alert_reason`. Both-zero (already covered by STALE) and both-nonzero (no single collector to blame) stay unattributed by design — verified live against real tape that this restraint matters: `weather_books`' actual cloud-leg offset (`:00`/`:03`) doesn't land in the `:5x` window, so it honestly reports `other`/unattributed rather than a fabricated `vps_dead`.

12 new unit tests (minute classification, healthy vs. diagnosed-dead vs. ambiguous-both-present vs. ambiguous-both-absent, per-bucket newest-capture tracking, table/JSON presentation) plus a 4th HARD acceptance test anchored to the real 2026-07-19 VPS outage: at `now=2026-07-20T00:30Z` over the actual committed tape, `crypto_hourly`/`orderbook_depth`/`sports_pairs`/`polymarket_macro_pairs` all resolve to a clean `vps_dead` attribution — not a synthetic fixture, the real finding L117 diagnosed by hand is now mechanically reproducible.

New lesson **L118** (`kb/lessons/00-lessons.md`) supersedes L117's enforcement column (`UNENFORCED` → `test`). The lessons ledger's UNENFORCED backlog is empty again as of this row. No strategy claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent verdict rule N/A (non-gating monitor extension, same precedent as L75/L104/L110).

**Gates.** `pytest -q` → 1299 passed (1287 prior + 12 new). `python scripts/invariants.py --full` → exit 0 (only the pre-existing non-gating advisories: stranded-ref, dir-shape/GC-classification, daily-cadence gaps — all already known).

**Step 9 — paper sub-pass.** `SHADOW_REGISTRY`={s14_ladder_underwriting} only. `paper_pass.py` idempotent (0 newly processed — the swept lines don't touch any of `crypto_hourly`'s s14-relevant records). Realized P&L unchanged **+$12.10** (`broker_truth`; s14 stays DEAD-at-real-fills per Q34 — proxy P&L, not proven edge).

**Next:** the lessons ledger is empty again — the next idle run either finds a fresh queue item, drops to idle-policy (b)/(c), or waits for a new lesson to be filed. Q36 part 2 / Q42 part 3 remain the only not-yet-preppable time-gated items (need live gated tape/auth respectively). VPS `:23` cron restart is still Ryan/VPS-side, unresolved.

---

## 2026-07-20 — Idle-run (policy c): tape cadence-decline deep-dive — root cause is a dead VPS collector, not a code bug

Research-loop run (protocol v3). Steps 0/0a: no history-integrity issue (merged PRs #132-#136 all confirmed ancestors of `origin/main`; `kb/00-LOG.md` and `tape/*/dt=*` both current through 2026-07-20). Open PRs unchanged: #125 (retro, "LEAVE OPEN for Ryan") and #77 (stale queue-restock) — neither claims eligible work.

**Step 0b — stranded-tape sweep.** One branch younger than the last sweep, `tape/hourly-20260720T095513Z` (>2h old, committed 10:06:50Z), carried **1,694** genuinely-missing lines (line-set diff against `origin/main`, JSON-validated line by line): 1,104 `orderbook_depth`, 290 `weather_books`, 236 `sports_pairs`, 24 `polymarket_cpi_pairs` (new file), 17 `perp_tape`, 15 `polymarket_macro_pairs`, 5 `econ_prints`, 2 `crypto_hourly`, 1 `anomalies`. Union-appended, all lines JSON-validated.

**Full Q0–Q46 re-scan: 0 eligible TODO/IN-PROGRESS** (unchanged from the prior 3 firings today). Idle-policy (a) is empty (L116 closed the backlog); idle-policy (b) is exhausted — every time-gated item that CAN be prepped from fixtures already has been (Q36 part 1, Q37, Q43); Q36 part 2 and Q42 part 3 need live gated tape/auth, not preppable offline. Took **idle-policy (c): a data-quality deep-dive on one tape family.**

**Milestone — root-caused the perp_tape/crypto_hourly cadence decline.** This decline (511→238→102 lines/day, 64→28→14) has been flagged by three separate prior firings (PR #132, #134, #136) as "the same cloud-collector degradation Q44/L74/L75 flagged" but never actually investigated. Delegated to the `tape-auditor` agent, then independently re-verified every number myself (re-counted lines from scratch, re-derived the minute-of-hour attribution independently by parsing every `captured_at` timestamp) before writing it up — this is a data-quality diagnosis, not a verdict-class change, so the two-agent verifier rule doesn't strictly apply, but the same "don't trust the agent's self-report alone" discipline Q44/Q45/Q46 used seemed warranted given how actionable the conclusion is.

**Finding:** the decline is real, global (identical in `perp_tape`/`crypto_hourly`/`orderbook_depth`/`sports_pairs`, all four halving in lockstep with dead-constant per-pass size — ruling out a per-family collector bug), and still worsening on 07-20. Minute-of-hour bucketing of `captured_at` (VPS cron signature `:2x` vs cloud-routine signature `:5x`, per `ops/ROUTINES.md`) pins the cause precisely: **the VPS `:23` cron on 87.99.146.250 stopped writing tape starting 2026-07-19** (partial day 07-18, zero VPS-pattern lines 07-19 and 07-20), leaving the already-degraded cloud `kalshi-collector` routine (Q44's own flagged ~60%-of-expected-cadence laggard since 07-15) as the sole survivor. Every collector module inspected (`collection/crypto_hourly.py`, `collection/perp_tape.py`) is clean — fixed symbol lists, honest `try/except`, 100% `completeness_ok` on passes that do fire. **This is a Ryan/VPS-infra item, not a repo bug** — no code change in this run would restore cadence. Flagged for Ryan: (a) check/restart the VPS `:23` cron on 87.99.146.250; (b) diagnose the cloud `kalshi-collector` routine's chronic under-cadence. Also flagged: Q43's `>=7 days` gate is a calendar-day count that will open on ~1/8th the intended tape density at current cadence — whoever runs Q43 should check per-day pass count, not just day count. See `findings/2026-07-20-tape-cadence-decline-vps-collector-down.md`; new lesson **L117** (UNENFORCED — candidate: teach `scripts/tape_gap_monitor.py` the minute-of-hour attribution so it names WHICH collector died, not just an aggregate under-capture ratio; not built this run, diagnosis only per idle-policy (c) scope).

No strategy claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent verdict rule N/A (data-quality diagnosis, same tier as PR #118/#129's prior tape audits).

`pytest -q` green (unchanged test count — docs/tape-only diff). `python scripts/invariants.py --full` green (only pre-existing non-gating advisories; the stranded-branch advisory clears after this commit merges).

---

## 2026-07-20 — Idle-run (policy b): Q37 weather summer maker-NO probe-prep (S1 x S5 EMOS, self-activating)

Research-loop run (protocol v3). Steps 0/0a: no history-integrity issue (`origin/main` HEAD matched local after `git fetch --unshallow`); open PRs #125 (retro, "LEAVE OPEN for Ryan") and #77 (stale queue-restock, superseded) — neither claims an eligible queue item.

**Step 0b — stranded-tape sweep.** Unshallowed the clone to get full branch history (the shallow clone was masking every branch's merge-base, making all 175 `tape/*` branches look unmergeable). Checked all 175: 174 are already fully absorbed into `main` (zero missing lines each, safe to delete but branch-delete is out of cloud-session scope, consistent with prior runs' findings); one, `tape/hourly-20260720T0704Z` (>2h old), carried **21,715** genuinely-missing lines (line-set diff against `origin/main`, JSON-validated line by line): 20,000 `universe_sweep`, 1,106 `orderbook_depth`, 338 `weather_books`, 237 `sports_pairs`, 17 `perp_tape`, 15 `polymarket_macro_pairs`, 2 `crypto_hourly`. Separately, environment/tooling setup during this run incidentally triggered the 09-UTC-hour `anomaly_sweep`/`econ_prints` collector legs live against real Kalshi endpoints (first capture of the day for both daily-cadence families) — 12 + 60 lines, JSON-validated, real captured data, folded into the same commit rather than discarded.

**Full Q0–Q46 re-scan: 0 eligible TODO/IN-PROGRESS.** All operative statuses are DONE/DEAD/BLOCKED/GATED/RESERVED; Q21's idea-gen round completed a few hours ago by the nightly edge-hunter. This is an IDLE RUN.

**Idle-policy (a) — checked first, exhausted.** The lessons ledger's UNENFORCED backlog was closed to empty by the immediately-prior firing (L116). Nothing to convert.

**Idle-policy (b) — Q37 probe-prep.** Of the two remaining time-gated items, Q43 (perp/binary consistency) already has its self-activating prep built by an earlier firing; Q37 (summer maker-side re-test of the S1/S5 weather family) did not — only its fee-structure sub-task was previously done. Delegated to the `edge-prober` agent: built `scripts/q37_weather_summer_makerno_probe.py` (+18 offline tests, `tests/test_q37_weather_summer_makerno_probe.py`) against the NEW `tape/weather_books/` forward tape. Per (series, contract-day) longshot bracket, rests a maker NO at a strictly-causal decision time; fill is modeled as an honest real-book touch (best NO ask crossing our resting price) rather than a candlestick-through proxy (L39/Q34) — the depth tape carries no trade/volume prints (L68), so a true queue-cleared fill is unconstructible, and the whole probe therefore carries `OPTIMISTIC_FILL = True`, capping any result short of a live verdict (mirrors S14's `queue_fillsim` caveat posture). **6-leg-fee-floor judgment call, made explicitly, not silently:** S33's complete-set arb summed the fee across all 6 legs it actually transacted; this probe's trade is an isolated single-leg maker NO on one bracket, so the fee floor is one `fee_per_contract` call on that leg — summing all 6 would manufacture a false DEAD by charging for 5 legs never traded. The full 6-member ladder is still read for `bracket_sum` overround-normalization (Hard Rule #3). S5's EMOS layer is imported from `scripts/weather_rehab_s5.py` (L36 — reused, not re-derived) as an entry filter, degrading gracefully to `EMOS_UNAVAILABLE` when `data/forecast_tape/` is absent (gitignored, absent in this sandbox) rather than erroring — the S1 no-signal baseline still runs regardless. Also wires L32 (frozen/movement dual cut), L69 (fillable-entry-restricted population as PRIMARY, unrestricted as a labeled diagnostic only), L86 (drop settlement-unmeasurable brackets, never zero), L47 (float ladder sizes). CI routed through `core.bootstrap.bootstrap_verdict_admissible` + `clears_tick_magnitude`, block-bootstrapped by calendar contract-day (L6). Both self-activation branches verified: gate closed on real tape prints `INSUFFICIENT DATA — ... only 6 present` (of 21 required, window starts 2026-06-21) and exits 0 with no bootstrap/CI/verdict; gate open (via `--days-required` override on real tape + synthetic fixtures in the test suite) runs the full pipeline and returns a well-formed result. Wrote NO `findings/` entry, touched NO registry — two-agent rule N/A (prep infra, no verdict, same posture as Q32/Q43). Gate still opens ~2026-08-05.

No strategy claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent verdict rule does not apply. `pytest` 1287 green (1269+18), `python scripts/invariants.py --full` exit 0 (pre-existing non-gating advisories only: stranded-ref count, dir-shaped `dt=` paths + GC dispatch, daily-family gaps). Step 9 paper sub-pass ran idempotent: `SHADOW_REGISTRY`={s14_ladder_underwriting}, 0 newly processed, cumulative realized P&L unchanged at **+$12.10** (`broker_truth`) — s14 is DEAD-at-real-fills (Q34) and its `fill_model` is the L39/L85 candle-through proxy, so this is paper-infra validation only, never edge evidence. Still 0 proven edges.

## 2026-07-20 — Idle-run (policy a): L66→L116 formal disposition closes the UNENFORCED lessons backlog; 1,880-line stranded-tape sweep

Research-loop run (protocol v3). Steps 0/0a: no history-integrity issue (main advanced cleanly from the prior firing's HEAD via `git pull --rebase`); open PRs #125 (retro, explicitly "LEAVE OPEN for Ryan") and #77 (queue-restock, superseded — every item it references is already DONE on `main`) — neither claims an eligible queue item.

**Step 0b — stranded-tape sweep.** `tape/hourly-20260720T0354Z` (pushed 03:54Z, >2h old) carried **1,880** genuinely-missing lines (line-set diff against `origin/main`, JSON-validated line by line): 1,088 `orderbook_depth`, 530 `weather_books`, 228 `sports_pairs`, 17 `perp_tape`, 15 `polymarket_macro_pairs`, 2 `crypto_hourly`. Spot-checked three older stranded branches (`tape/hourly-20260719T{2156,1856}Z`, `tape/hourly-202607190956Z`) — all-negative diffs against `origin/main`, confirming main already supersedes them (no further lines to pull).

**Full Q0–Q46 re-scan: 0 eligible TODO/IN-PROGRESS.** Q19's per-event legs remain gapped (WC-final burst tape never captured — Ryan-side trigger issue, already flagged) with FOMC still 9 days out; Q36/Q37/Q43 remain date/day-count gated (perp_tape/weather_books coverage unchanged since the last firing); Q32/Q33/Q35-build remain credential-blocked; Q21's idea-gen round was completed a few hours ago by the nightly edge-hunter (S43/S44/S45, 0 registered) and is not yet due for re-eligibility. This is an IDLE RUN.

**Idle-policy (a) — L66→L116, formal disposition, closes the backlog.** Re-derived the UNENFORCED lessons queue from scratch (whole-file whole-word grep per the L108/L112 discipline, since L106/L107 previously mis-stated the open set twice): confirmed the open set is exactly `{L66}` — L112 (this morning) converted L69 and explicitly left L66 flagged "terminal-leaning" for a future run's formal disposition. Gave it one: the block-bootstrap surface L66 governs (a kill-writeup for the S28 "buy the ex-post known winner" family) is foreclosed at the IDEA stage by L65/L104 — `.claude/agents/edge-prober.md` already rejects any such fill-sim before it's built, so L66's own precision-language discipline ("genuine but thin losing tail," never "provably degenerate") had no reachable document to attach to. Rather than leave it stranded, added a conditional clause to the existing L65/L66 house-style bullet: if the S28 idea-stage kill is ever formally reopened and a kill-writeup gets built anyway, it must apply L66's precision language. New lesson **L116** supersedes L66's enforcement column (`UNENFORCED` → `protocol, encoded`). **The lessons ledger's UNENFORCED backlog is now empty** — the next idle run drawing on policy (a) will find nothing until a new lesson is filed.

No strategy claim, no registry change (`kb/strategies/00-index.md` untouched, `findings/` untouched) — two-agent verdict rule does not apply (documentation-tier closure, same class as L94/L95/L104/L106–L108/L112, not a verdict/kill/registry-flip). `pytest` and `python scripts/invariants.py --full` both green (see run digest for counts). Step 9 paper sub-pass ran idempotent: `SHADOW_REGISTRY`={s14_ladder_underwriting}, 0 newly processed (no new S14-eligible crypto records in the swept tape), cumulative realized P&L unchanged at **+$12.10** (`broker_truth`) — s14 is DEAD-at-real-fills (Q34) and its `fill_model` is the L39/L85 candle-through proxy, so this is paper-infra validation only, never edge evidence. Still 0 proven edges.

## 2026-07-20 — Edge-hunter nightly: Q21 round #6 (S43/S44/S45 all KILL-AT-IDEA → 0 registered); day's findings adversarially re-checked clean

Nightly kalshi-edge-hunter run (Opus, 04:15Z). Steps 0a/0/0b: history-integrity PASS (the local clone's `main` was a stale 07-16 tape commit; origin advanced 07-16→07-20 via squash-merges #129/#130/#134, all reachable — the `git pull` "forced update" was that staleness, NOT a rewind; newest LOG 07-19 vs newest tape 07-20 within tolerance). Open PRs: #125 (retro, "LEAVE OPEN for Ryan", 1 day old) and #77 (queue-restock, superseded — Q29–Q46 all already in `main`); neither claims an eligible queue item.

**Unit 1 — adversarial review (PASS, no issue).** Re-checked one load-bearing number per last-24h finding, by FILE SHAPE (L25): the morning run's cadence-decline flag reproduces EXACTLY — `perp_tape` 511→238→102 (07-17/18/19) and `crypto_hourly` 64→28→14, all from canonical `.jsonl` day-files (perp has 4 forward days → Q43 gate opens ~07-23, confirmed). The 07-19 `sports_pairs` finding's 101,801-line count is now 102,489 = legitimate append-growth (07-19 completed + 07-20 added since that snapshot), not a discrepancy; the 3 directory-debris days (07-02/09/10) confirm. Paper P&L is `broker_truth` settlement records for the DEAD `s14` shadow (proxy/infra validation only, NOT edge evidence). No finding fails re-check → no GitHub issue, no history rewrite.

**Unit 2 — pipeline replenishment (Q21 round #6, 0 registered).** Eligible items = 0 (morning run's Q0–Q46 scan; near-gate items Q43/Q36 re-confirmed by file shape, Q36 also design-blocked on an intraday-KNYC actual). Proposed **3 candidates (S43/S44/S45)**, each attacked by an independent `verifier` over the committed tape BEFORE registration (two-agent rule at the idea stage) — **ALL KILL-AT-IDEA → 0 registered** (6th round in ~8 days, all 0; register survivors, never pad). **S43** (cross-venue econ directional convergence, one fee): data-adequacy-dead — `tape/econ_prints/` has exactly **n=1** in-window macro release (June CPI 07-14); all other series settle after the tape ends → no cross-event distribution to bootstrap (S9 grave). **S44** (universe_sweep logical-complement coherence arb): collapses into S41 — the within-market YES+NO box min is **1.002** (never <$1, that gap IS the overround); apparent sub-$1 cross-leg sums are non-exhaustive parlay longshots; complements unidentifiable from `universe_sweep.v1` + L96 20k-row cap. **S45** (single-series settlement-ledger rich-side maker-sell): `tape/settlement_ledger/` has **0 crypto rows** (zero-overlap join), `crypto_hourly` carries no size/depth field (no fill model), and the flat 1¢ maker fee swamps the 1–4¢ modal spread (S6/S13/S23 grave). New lessons **L113/L114/L115** (the three kill facts). Still **0 proven edges**; consumed S43/S44/S45 → **next free = S46**. See `findings/2026-07-20-q21-idea-gen-round.md`.

**Unit 3 — probe-prep (satisfied, nothing to build).** Both near-72h gates already have prepped probes: Q43 (`scripts/q43_perp_binary_consistency_probe.py`, built this morning) and Q36 (`scripts/q36_kxtempnych_settlement_basis_probe.py`, already present; Q36 is design-blocked, not merely date-gated).

**Housekeeping.** Burst triggers whose event date has passed → named for deletion: `cpi-0714`, `wcsemi1-0714`, `wcsemi2-0715`, `wcfinal-0719` (`fomc-0729` future, keep). Stale PRs: #77 superseded (needs closing, not a Ryan-blocking action → no high-priority flag, per the tune-out caution); #125 explicitly leave-open, 1 day old. Remote branches: **168** `tape/hourly-*`, **1** `tape/burst-*` (unchanged trend; delete-scope is a standing Ryan-side item).

No strategy claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent rule satisfied at the idea stage (verifier killed all 3). `pytest` exit 0 (1269) green; `python scripts/invariants.py --full` exit 0 (only pre-existing non-gating L25/L109/L74 advisories). Step 9 paper sub-pass: `SHADOW_REGISTRY`={s14_ladder_underwriting}, DEAD-labeled, cumulative realized **+$12.10** (`broker_truth`) — proxy/infra validation only, not edge evidence.

## 2026-07-20 — Idle-run (policy b): Q43 self-activating perp/binary-consistency probe PREPPED; perp/crypto cadence-decline flagged

Idle research-loop run (protocol v3). Full Q0-Q46 re-scan found all operative statuses DONE/DEAD/BLOCKED/GATED/RESERVED — 0 eligible TODO/IN-PROGRESS. Idle-policy (a) is exhausted: L112 (earlier today) converted L69, leaving only L66 open, and L66 is verifier-judged terminal-leaning / non-convertible (its block-bootstrap precision note governs a foreclosed S28/buy-the-ex-post-known-winner surface that no fill-sim ever reaches — L65/L104). So this run took idle-policy (b): prep the nearest date-gated milestone's harness so it self-activates the day the gate opens.

**Q43 prep — self-activating probe built.** `scripts/q43_perp_binary_consistency_probe.py` (+16 offline tests, `tests/test_q43_perp_binary_consistency_probe.py`), both analysis legs gated behind `_perp_days_available() >= 7`: (1) LEAD-LAG — cross-correlate perp BBO-mid changes (`tape/perp_tape/`, `real_ask`/`real_bid`) vs binary-ladder repricing (`tape/crypto_hourly/`) at shared cadence, reporting contemporaneous + lag±1 signed rho with the mandatory L57 leave-one-out recompute; (2) COHERENCE at real asks — near-expiry binary members whose `real_ask` is inconsistent with the perp-implied distance-to-strike, counted only when the violation clears the full fee floor (`core.pricing.fee_per_contract`) AND the 10-contract depth floor, with the binding test the depth × wall-clock-seconds run distribution via `core.bootstrap.collapse_duration_gated_runs` (L76/L93). Joinable underlyings = intersection {BTC, ETH} (perp has 13 symbols, crypto_hourly ladders only BTC/ETH). Crypto hour token parsed ET via `core.timeutil.parse_crypto_hour_token_close_utc` (L45/L49); strike spacing via `core.pricing.ladder_spacing` (L7/L36). Tags: `real_ask`/`real_bid` fillable only, `broker_truth` perp mark, perp-implied fair is `synthetic` and NEVER a fill (Hard Rule #1/#3). Live smoke over real committed tape correctly printed INSUFFICIENT DATA (`perp_tape` 4/7 forward days) and exited 0 — no analysis, no verdict. Gate opens ~2026-07-23/24.

**DATA-QUALITY flag for Ryan.** `perp_tape` + `crypto_hourly` capture cadence is halving per day: `perp_tape` lines/day 511→238→102 over 07-17→07-19; `crypto_hourly` 64→28→14. Consistent with the Q44/L74/L75 cloud-collector degradation. The calendar-day gate may open ~07-24 but with thin per-day density — flagged, not fixed (out of a cloud run's lane).

No strategy claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent verdict rule N/A (prep infra, no verdict). `pytest` 1269 green; `python scripts/invariants.py --full` exit 0 (pre-existing non-gating advisories only). Step 9 paper sub-pass ran idempotent (`SHADOW_REGISTRY`={s14_ladder_underwriting}, 0 newly processed), cumulative realized P&L **+$12.10** (`broker_truth`) — s14 is LABELED DEAD-at-real-fills per Q34 and its `fill_model` `maker_candle_through` is the L39/L85 candle-through proxy, so this is paper-infra/proxy validation ONLY, not edge evidence. Still 0 proven edges.

## 2026-07-19 20:32 ET — Idle-run (policy a): L69→L112 fillable-entry-population-as-PRIMARY guardrail encoded; Q19 WC-final tape-gap documented

Idle research-loop run (protocol v3). Step 0/0a/0b handled by the coordinator: history-integrity PASS (kb/00-LOG.md + newest tape/*/dt=* both 2026-07-19, no rewind), 0 eligible TODO/IN-PROGRESS across the full Q0-Q46 re-scan, and the stranded `tape/hourly-20260719T2156Z` sweep (1,857 lines / 6 families) applied and landed separately as PR #131 (merged). This working tree carries only the idle-run milestone (lessons/log/queue/charter) — no tape data.

**Idle-policy (a) — L69->L112, full re-derivation + verifier-guided target pivot.** Per L108's standing caution that the lowest-open-row discipline mis-fired twice (L106/L107 both missed L23), re-derived the UNENFORCED queue mechanically from scratch: read the whole ledger, whole-word-grepped every UNENFORCED-bearing row's L-number across the repo for an ACTUAL later supersedes/generalizes/closes/escalates claim (not a citation). Result reconfirmed L108's own statement — after L23->L108 and L109->L110 the open set is exactly {L66, L69}, no row below L66 open. An independent verifier re-derived the same closure map from scratch and CONFIRMED it, but judged the strict-lowest row L66 honestly-terminal-leaning: L66's "precision note for a trade-the-known-outcome kill writeup" governs a block-bootstrap surface that is never reached, because the S28/buy-the-ex-post-known-winner family is already an idea-stage kill (L65/L104, edge-prober.md ~143) so no fill-sim gets built — a foreclosed-surface docs bullet. L69, by contrast, governs a LIVE recurring template (the Q27/Q30-style earliest-pre-close queue-aware maker fill-sim) and prevents a real future fill-price error — the pt1 synthetic-price-as-fillable mistake one abstraction up (S29/Q30's earliest-entry population cleared every gate at +9.03c purely on nickel bids against 87-94c days-out asks the generous fill-sim still marks FILLED; both honest fillable-entry cuts failed and near-close went negative). So per the two-agent rule the run converted **L69** instead of the strict-lowest L66. L69's candidate ("make the fillable-entry-restricted population the PRIMARY verdict, unrestricted a labeled diagnostic") was unbuilt — nothing in edge-prober.md named it. Added a house-style bullet stating it directly. New lesson **L112** supersedes L69's enforcement (UNENFORCED -> protocol, encoded). L66 left flagged terminal-leaning for a future run's formal disposition, not unilaterally closed. No code change; closes at the documentation/discoverability tier, same as L94/L95/L104/L106/L107/L108.

**Two-agent rule.** Not strictly verdict-class (no registry flip, no CI, no kill decision — a documentation-tier closure), but per the L107/L108 precedent for lowest-open-row selection, an independent verifier re-derived the open set from scratch, CONFIRMED it, and drove the L66->L69 target pivot before L112 landed.

**Q19 WC-final tape-gap documented (not fixed).** The WC-final burst trigger `kalshi-burst-wcfinal-0719` (window Jul 19 20:10->22:45Z) fired (`last_fired_at` 2026-07-19T20:10:31Z, still `enabled: true`) but committed NO burst tape — `tape/polymarket_pairs/` has no `dt=2026-07-19.jsonl` on main and no `tape/burst-*` branch carries it. A SECOND occurrence of the WC-semi1 (Jul 14) fired-but-never-captured failure mode; appended to Q19's LOOP-QUEUE status, flagged for Ryan (Ryan-side trigger/collection infra), not silently dropped. Q19's WC-final per-event leg is NOT eligible (no tape to analyze).

No strategy claim, no registry change (`kb/strategies/00-index.md` untouched). `pytest -q` 1253 passed green (unchanged — docs/charter only). `python scripts/invariants.py --full` green (only pre-existing non-gating L17/L25/L74/L110 advisories). git/PR is the coordinator's to finish.

## 2026-07-19 17:15 ET — Idle-run (option a): L109→L110 dir-shape orphan GC classification + 21,900-line stranded-tape sweep

Idle-run per protocol v3: full Q0-Q46 re-scan found 0 eligible TODO/IN-PROGRESS items. Q19's
WC-final burst-capture window (`kalshi-burst-wcfinal-0719`, 20:10→22:45Z) was still OPEN at this
run's start (21:09Z) — the per-event analysis fires the run AFTER the burst lands, not mid-window,
so it stays not-yet-eligible this cycle; everything else remains date-gated/blocked as before.

**Step 0b — stranded-tape sweep.** `tape/hourly-20260719T1856Z` (pushed 19:04Z) carried 21,900
genuinely-missing lines (comm -13 set-diff, zero reverse-direction — pure append): 20,000
`universe_sweep`, 1,089 `orderbook_depth`, 530 `weather_books`, 232 `sports_pairs`, 17 `perp_tape`,
15 `polymarket_macro_pairs`, 2 `crypto_hourly`. All JSON-validated.

**Idle-policy (a) — L109→L110.** The prior run (PR #129) deliberately left its new lesson L109
`UNENFORCED`/PROVISIONAL — an audit/invariant for orphaned directory-shaped `dt=` days beyond
L25's plain shape-check. Built that: `scripts/invariants.py::_tape_dir_shape_orphan_classification()`
/ `tape_dir_shape_orphan_warning()` (same non-gating stderr-advisory pattern as L25/L75) classifies
each directory-shaped `dt=<date>` entry as **superseded** (a canonical `.jsonl` for the same date
already coexists → pure post-fix debris, safe to delete) or **unrecoverable** (no canonical file
for that date, and the family has captured a later day → forward collection has moved on, this
day can never self-heal, needs a human) — a directory at/after the family's newest canonical day
is deliberately left unclassified since collection may still be mid-write. 9 new tests, including
a ground-truth regression against the real tree. Live result matches L109's finding exactly:
`crypto_hourly/dt=2026-07-10` + `sports_pairs/dt=2026-07-10` → superseded (2, safe to delete);
`sports_pairs/dt=2026-07-02` + `dt=2026-07-09` → unrecoverable (2, permanently lost, `orderbook_depth`
also missing 07-09). New lesson **L110** supersedes L109 (`UNENFORCED` → `invariant (non-gating
advisory)`). **Judgment call flagged for Ryan, not acted on:** the 2 `superseded` directories are
now confirmed safe to delete but this run did NOT delete them — detection/dispatch only, same
posture as L75 not backfilling the gaps it detects.

No strategy claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent verdict
rule does not apply (non-gating advisory/detection code, not a verdict-class change).

`pytest -q` 1253 green (1244 prior + 9 new). `python scripts/invariants.py --full` green (only
pre-existing non-gating L17/L25/L74 advisories plus the new L109-classification advisory itself,
which is non-gating and simply confirms its own live counts). Step 9 paper sub-pass idempotent
even against the freshly-appended tape (0 newly processed), realized P&L unchanged **+$11.65**
(`broker_truth`; s14 stays DEAD-at-real-fills per Q34 — proxy P&L, not a proven edge).

Finding/lesson: `kb/lessons/00-lessons.md` L110. git/PR is the coordinator's to finish.

---

## 2026-07-19 14:18 ET — Idle-run (option c): sports_pairs data-quality + join-adequacy deep-dive

Idle-run per protocol v3: queue fully DONE/BLOCKED/date-gated, and today's three (a) picks
plus one (b) were already done earlier — so leaned option c on the one workhorse family
(`sports_pairs`) that had no prior dedicated audit.

**Join-adequacy core verdict (two-agent concordant, NO registry flip).** The sports-maker /
CLV-anchored fill question is **STILL DATA-STARVED** — n=3 concurrent games, only 2 clean-live
pre-settlement books, below the 10-game floor. The **L9/L43 structural fair/depth timing gap
persists** and no join-window relaxation can fix it (game date is embedded in the ticker string).
The 0->3 games only appears when `sports_clv_s7/trades.jsonl` extends the fair universe two days
past `sports_clv`, kissing the 07-06/07-07 boundary — not new concurrent forward collection.
Fair anchors are `synthetic`, depth `real_ask`/`real_bid`, settlement `broker_truth`; a
data-adequacy verdict, NOT a CI falsification. **S21 stays DEAD-by-data-adequacy** (no status flip).

**sports_pairs health headline.** 16 canonical `dt=*.jsonl` (2026-07-03..07-19): **101,801 lines,
0 JSON-invalid, `completeness_ok`=True on 100%, every priced outcome `real_ask`, 33 `KX...GAME`
series, ~30-min cadence.** Median `overround_absorbed` **FLAT at 0.02-0.05** the whole span
(mean 0.13-0.33 is right-skewed / composition-driven by illiquid 3-way soccer markets — median is
the honest figure).

**Data-quality defect (genuinely-new).** L25's format-regression self-correction fixed forward
collection but never GC'd the orphaned directory-shaped `dt=` days: `dt=2026-07-02/`, `dt=2026-07-09/`
(raw blobs, **07-09 PERMANENTLY MISSING** — no canonical file, and `orderbook_depth` also lacks
07-09), `dt=2026-07-10/` (raw blobs beside a **TRUNCATED** `dt=2026-07-10.jsonl` of 9/48 caps /
1,968 lines). Filed as **L109** (PROVISIONAL / UNENFORCED candidate — an audit/invariant that flags
orphaned directory-shaped days for cleanup, beyond L25's file-shape assert; deliberately NOT built
this run, idle-run scope).

Finding: `findings/2026-07-19-sports-pairs-join-adequacy-dataquality.md`. New lesson: **L109**.
`pytest -q` green + `python scripts/invariants.py --full` green (no code changed — append-only KB).
git/PR is the coordinator's to finish.

## 2026-07-19 11:3x ET — Idle-run (policy b): Q36 settlement-basis probe prepped + 3,095-line stranded-tape sweep

Step 0a passed: `git fetch origin main` was required first — the container's local `main`
branch pointer was a stale ref from a different, unrelated lineage (no merge-base with
`origin/main` at all), reset via `git checkout -B main origin/main` (no local work lost;
working tree was clean). Current `origin/main` tip `2e83f94` (PR #126) confirmed reachable;
`kb/00-LOG.md` newest entry and newest `tape/*/dt=*` both 2026-07-19 — no rewind.

Step 0 (claim-check): two open PRs. #125 (weekly-retro proposals) is explicitly marked "leave
open for Ryan" — untouched. #77 (2026-07-15 queue-restock) is now ~50 commits behind current
`main` and already superseded piecemeal by later numbered items — flagged stale again, still
untouched (not this run's call to close).

Step 0b (stranded-tape sweep): `git ls-remote` found 165 stranded `tape/hourly-*`/`tape/burst-*`
branches (a growing backlog several recent runs have only partially chipped at). Rather than
re-sweep just the newest branch, ran a bulk per-branch line-set dedupe (each branch's own commit
diffed against its parent, then that content checked against current `main`): **152 branches
are fully redundant** (their content already landed via earlier sweeps — safe to delete, no
append needed, though this session's GitHub token lacks branch-delete scope, same limitation
prior runs have flagged), **1** (`tape/hourly-20260716T1856Z`) turned out to carry a STALE,
since-superseded draft of `tape/cloud-env-check.md` — a documentation edit, not lost tape data,
correctly excluded from the sweep, and **7 branches genuinely carried missing data**: hourly
captures at 06:55/09:55/10:54/11:55/12:54/15:56/16:56Z on 2026-07-10 that never reached `main`.
Each contributed exactly one new `capture-<ts>` directory per family (`crypto_hourly`,
`sports_pairs`) on top of captures already present in `main`'s existing (pre-established)
directory-format tape for that date — pulled in via targeted `git checkout <branch> -- <path>`,
3,095 files / lines, all JSON-validated, pure append.

Idle-run policy (b): queue re-scan reconfirmed 0 eligible TODO/IN-PROGRESS items (Q19 WC-final
burst window passed without a burst leg firing — out of scope to fix here; Q32/Q33/Q35-build
blocked on Polymarket creds; Q36 gated ~2026-07-22 [`weather_books` 4/7 days]; Q37 gated
~2026-08-05; Q42 part 3 BLOCKED[needs-auth]; Q43 gated ~2026-07-23/24 [`perp_tape` 3/7 days];
Q21 idea-gen round completed 2026-07-19 by the nightly edge-hunter). Rather than continue the
lessons-ledger L-number archaeology (L108 itself flagged that discipline has now mis-fired
twice in a row — diminishing returns), picked policy-(b): prepped the probe for Q36's nearest
time-gate. Built `scripts/q36_kxtempnych_settlement_basis_probe.py` (+16 offline tests) —
joins settled KXTEMPNYCH events' `expiration_value` (The Weather Company's own settlement
number, already flowing via `tape/settlement_ledger/`, a DIFFERENT tape family than the gated
`weather_books`) to the nearest independent KNYC ASOS observation (IEM `obhistory.json`) and
quantifies bias/rounding/lag/disagreement-rate, mirroring `validation/v1_actuals.py`'s
CLI-vs-METAR reconciliation. Self-activating (`INSUFFICIENT DATA` below `min_events=10`) and
descriptive-only — no bootstrap, no CI, no registry touch, two-agent rule N/A. **Live smoke
test against real committed tape**: `tape/settlement_ledger/` currently holds exactly 1 unique
settled KXTEMPNYCH event (the 10 lines seen at first glance all share one `event_ticker` —
correctly deduped) — script printed `INSUFFICIENT DATA, n_settled_events=1` rather than
fabricating a mapping, confirming the gate logic works both offline and live. Part 2
(microstructure) needs the gated `weather_books` depth history directly and was NOT built —
nothing safe to prep against fixtures alone.

`pytest` 1244 green (1228 prior + 16 new). `python scripts/invariants.py --full` green (only
pre-existing non-gating L25/L74 advisories — the L20 stranded-tape warning still shows all 165
local refs, since this run merged 7 branches' MISSING CONTENT but could not delete any remote
branch, per the branch-delete-scope limitation prior runs have already flagged for Ryan).

Step 9: `SHADOW_REGISTRY`={s14_ladder_underwriting} only. `paper_pass.py` idempotent (0 newly
processed — the swept 07-10 tape didn't add any newly-eligible S14 fills), realized P&L
unchanged **+$11.65** (`broker_truth`; s14 stays DEAD-at-real-fills per Q34, proxy P&L not an
edge).

## 2026-07-19 08:10 ET — Idle-run (policy a): L23→L108 empty-ladder-normalization guardrail encoded; caught a stale-main-ref near-miss

Idle research-loop run, sub-policy (a), wall-clock ~12:1x UTC. Step 0a PASS: origin/main
HEAD `3593ae3` (PR #124, tape additional collections); merged PRs #120-#124 all confirmed
ancestors; `kb/00-LOG.md`/tape both 2026-07-19, no rewind. Mid-run, this session itself hit
the exact L14 trap (stale local `main` ref briefly showing a 3-day-old tree) before a
`git fetch origin main` corrected it — recorded as a live instance of L14/retro-amendment-#1,
not just a historical anecdote.

Step 0: only open PR is #77 (stale, flagged every prior run, left untouched). Full Q0-Q46
re-scan: 0 eligible TODO/IN-PROGRESS items (Q19 WC-final burst window opens 20:10Z tonight;
Q36/Q37/Q43 gated; Q42 part 3 blocked on auth; Q21 idea-gen already run today; Q32/Q33/Q35-build
blocked on Polymarket creds). Idle run.

Step 0b: swept `tape/hourly-202607190956Z` (10:02Z pass, >30min old, merge-base exactly
`origin/main` HEAD — a clean fast-forward, per-file prefix-verified before union) —
5,936 genuinely-missing lines across 9 families, JSON-validated, pure append.

Idle-policy (a): rather than trust L106/L107's own stated "lowest genuinely-open row" claims,
did a direct enumeration of every `UNENFORCED`-bearing lesson row and found both of those runs
had missed **L23** (2026-07-07) — the empty-orderbook-ladder-is-not-a-drop lesson, older than
L66/L69 (the only other rows their closure maps didn't cover). L23's own residual candidate
("generalize the empty≠drop discipline beyond one collector") turned out to already be true at
the code level: `collection/orderbook_depth.py` and `collection/weather_books.py` both build
their depth snapshot through the same `collection.normalize.normalize_snapshot` (a third
module, `capture_orderbooks.py`, also calls it), which already treats a missing side as
`[]`/`None`, never an exception — so no per-collector duplication exists to regress. Added a
`.claude/agents/collector-engineer.md` house-style bullet naming the shared function so a
future ladder-collector reuses it by default. New lesson **L108** supersedes L23's enforcement
column (content unchanged, ledger append-only).

Two-agent verdict rule: an independent `verifier` agent ran four attacks against the draft
closure and CONFIRMED L23 was genuinely open and the true lowest such row — but also caught a
factual slip in the draft's own narrative (it had blamed both L104 *and* L106 for the naive-scan
miss; only L104 ever mentioned L23, L106/L107 omitted it entirely, a distinct lapse in their own
"strict-lowest-first" claim). Corrected before commit; L108's text now flags the L106/L107 gap
explicitly for the next idle run, since two consecutive runs trusting a prior row's closure map
instead of re-deriving it is itself worth a standing caution.

No strategy claim, no registry change (`kb/strategies/00-index.md` untouched). `pytest`: 1228
green (unchanged — docs/tape only). `python scripts/invariants.py --full`: green (only
pre-existing non-gating L20/L25/L74 advisories).

Step 9 (paper sub-pass): `SHADOW_REGISTRY`={s14_ladder_underwriting} only. `paper_pass.py`
idempotent (0 newly processed — the new tape added no newly-eligible S14 fills this pass; 233
deferred-caps, 222 deferred-coverage, 67 already-in-ledger). Realized P&L unchanged **+$11.65**
(`broker_truth`; s14 stays DEAD-at-real-fills per Q34 — proxy P&L, not a proven edge).

See `LOOP-QUEUE.md` Log of runs (2026-07-19T12:1xZ entry) and `kb/lessons/00-lessons.md` L108.

---

## 2026-07-19 05:55 ET — Idle-run (policy a): L105→L107 universe_sweep bracket-arb idea-stage-kill guardrail encoded

Idle research-loop run (eleventh in this stretch), sub-policy (a), wall-clock ~09:2x UTC.
Step 0a PASS: origin/main HEAD `577d2eb` (tape hourly pass 2026-07-19T06:54:55Z); merged
PRs #118–122 all ancestors of HEAD; `kb/00-LOG.md`'s newest entry and the newest
`tape/*/dt=*` are both 2026-07-19 — a 0-day gap, no rewind. Step 0: the only open PR is
#77 (stale 2026-07-15 queue-restock, flagged by every prior run and left untouched again).

Step 0b stranded-tape sweep: fetched every `tape/hourly-*`/`tape/burst-*` ref; the four
newest branches (`202607190356Z`/`0400Z`/`0403Z`/`20260719T0056Z`) are 307–487 min old —
all far outside the 30-min freshness rule and none an ancestor of `main` (already absorbed
by PRs #120/#121, reconfirming PR #122's sweep). Zero genuinely-missing lines; nothing to
append this run.

Full Q0–Q46 re-scan: 0 eligible TODO/IN-PROGRESS. Q19 WC-final burst tape not yet
captured (kickoff tonight); Q36 gated ~Jul-22; Q37 ~Aug-05; Q42 part 3 BLOCKED[needs-auth];
Q43 ~Jul-24; Q21 idea-gen round just run by tonight's edge-hunter (PR #121); Q32/Q33/Q35-build
blocked on Polymarket creds. IDLE RUN.

Idle-policy (a): last cycle's L106 closed L68 but did NOT reach L105 — a higher-numbered row
created the same day by the edge-hunter (PR #121), which leaves `.claude/agents` edits for the
research loop. L105 is therefore the true lowest genuinely-open UNENFORCED row. An independent
`verifier` CONFIRMED all three claims across three attacks: (i) L105 genuinely open; (ii) the
lowest such via the whole-file whole-word grep over every UNENFORCED row; and (iii) the
schema-incompatibility fact true at source — `universe_sweep.v1` persists no
`strike_type`/`floor_strike`/`cap_strike`/`yes_ask_dollars`, exactly the ladder fields
`anomaly_sweep._segment_bounds`/`check_bracket_arb` read. Encoded L105 as a
`.claude/agents/edge-prober.md` house-style idea-stage-kill bullet in the L65/L104/L106
cluster; appended lesson **L107** (supersedes L105's enforcement column, protocol/encoded).
The verifier-attacked numbers: over `dt=2026-07-19` (20,000 rows, single `capture_id`),
1,565/2,441 multi-market groups sum below $1 but 0/1,565 are fillable, and 1,537 are
all-zeros; the 20k-market cap over an >80k universe (L96) splits any straddling bracket set,
so exhaustiveness is unprovable in principle. A `yes_ask=0.0` no-offer leg is the ABSENCE of
a resting offer, not a $0.00 buyable fill — treating it as one is the pt1/prime-directive
violation.

No strategy claim, no registry flip (`kb/strategies/00-index.md` untouched). The two-agent
verdict rule is satisfied for the target selection (verifier CONFIRMED); this is a doc-tier
encoding, not a verdict-class change.

Gates: `pytest` 1228 passed (docs-only, no new tests — run under libfaketime `+6h` offset to
clear a pre-existing wall-clock-hour-9 + blocked-network flake in
`test_main_wires_sports_limit_and_crypto_symbols`, which fires the unstubbed hour-9 daily
passes against the sandbox-blocked network; the flake is pre-existing on the untouched tree
and unrelated to this change). `python scripts/invariants.py --full` exit 0 (only pre-existing
non-gating L20 stranded-tape / L25 dir-shape / L74–L75 daily-cadence advisories).

Step 9 paper sub-pass: `SHADOW_REGISTRY={s14_ladder_underwriting}` only; `scripts/paper_pass.py`
idempotent (0 newly processed, 233 deferred-caps, 222 deferred-coverage, 67 already-in-ledger);
realized P&L unchanged **+$11.65** (`broker_truth`; s14 stays DEAD-at-real-fills per Q34 — proxy
P&L, not an edge). daily_summary: `paper: 0 open position(s), 481 settled contract(s), realized
P&L $+11.65, cash $+11.65, open notional $0.00`.

Links: `kb/lessons/00-lessons.md` L107 (supersedes L105); `.claude/agents/edge-prober.md`
idea-stage-kill cluster; `findings/2026-07-19-q21-idea-gen-round.md` (S41 kill that raised L105).

---

## 2026-07-19 05:40 ET — Idle-run (policy a): L68→L106 maker-spread-over-depth-only idea-stage-kill guardrail encoded

Idle research-loop run, sub-policy (a): convert the true lowest-numbered still-open UNENFORCED
lesson into its sanctioned enforcement shape. Independently re-ran the L102/L104 whole-file
whole-word grep discipline over every `UNENFORCED`-bearing ledger row: L5/L7/L22/L25/L39/L45/L47/
L51/L59/L64/L65/L74/L76/L86/L90 are all genuinely closed by later rows; L27/L28/L32 are
helper-built AND charter-named. L52/L92's remaining "escalate to a static invariant" thread was
inspected and recorded as a **false start** — `result == "yes"/"no"` is read without an adjacent
scalar guard in 9 legacy/verdicted scripts, so a gating scanner would false-gate frozen historical
code and an allowlist of all of them is the L30/L19 dishonest-theater anti-pattern; L52 stays
honestly terminal (test-pinned at L92) and is skipped, documented in L106 so the next idle run does
not re-attempt it. That left **L68** as the true lowest genuinely-open, cleanly-convertible row
(its L88/L96 mentions are sibling citations, not supersessions; it was absent from the charter).
Encoded L68 as a `.claude/agents/edge-prober.md` house-style idea-stage-kill bullet in the
L65/L104 cluster: a maker-spread / spread-capture candidate whose only data leg is
`tape/orderbook_depth/` is toxicity-untestable by construction (resting-depth snapshots only, no
trade/volume/last-price fields → the L41 adverse-selection CI is unconstructible), so reject it at
the IDEA stage rather than register it as untestable (which burns a research-loop probe); the
bullet cross-references `core.depth.capturable_depth` (L67, L44) for the sibling
two-sided-depth-illusion check. Appended lessons row **L106** (supersedes L68's enforcement column,
**protocol, encoded**). No strategy claim, no registry flip — `kb/strategies/00-index.md` untouched;
two-agent verdict rule N/A (doc-tier encoding, not a verdict-class change). Gates independently
re-verified by the research-loop main session (not just agent-reported): `pytest -q` **1228 passed**
(unchanged — docs-only), `python scripts/invariants.py --full` exit 0 (only the pre-existing
non-gating stranded-tape / tape-dir-shape / daily-family advisories on stderr). Step 9 paper
sub-pass: `SHADOW_REGISTRY`={s14_ladder_underwriting} only, idempotent (0 processed, 233
deferred-caps, 222 deferred-coverage, 67 already-in-ledger), realized P&L unchanged **+$11.65**
(`broker_truth`; s14 stays DEAD-at-real-fills per Q34 — proxy P&L, not an edge). Step 0b: fetched
every `tape/hourly-*`/`tape/burst-*` branch and line-set-diffed the four still-recent ones against
current `main` — zero genuinely-missing lines, nothing to sweep this run (already absorbed by PRs
#120/#121).

---

## 2026-07-19 04:15 ET — kalshi-edge-hunter (nightly): adversarial review (2 findings, both CONFIRMED) + Q21 round (S41/S42 killed, 0 registered, L105) + 1,663-line tape sweep

Step 0a PASS: recent merged-PR commits (`c635ae4`/`428a4d6`/`abb7c8f`/`46519a7`/`0c01a0b`) are all
ancestors of `origin/main`; newest `kb/00-LOG.md` entry and newest `tape/*/dt=*` content both
2026-07-19 (0-day gap). The fresh clone's stale `69a3d3f` base fast-forwarding to HEAD `c635ae4` is
the normal clone-base gap, not a rewind. Step 0: only open PR is #77 (Ryan's stale 2026-07-15
queue-restock, 4 days old — under the 5-day threshold and flagged by every prior run, so NOT
re-flagged).

**Unit 1 — adversarial review (re-check one load-bearing number per last-24h finding).** Two
number-bearing findings fell in the window, both re-checked against the actual committed tape:
- `findings/2026-07-18-q21-idea-gen-round.md`'s load-bearing S39 kill / L96 collector-bug claim
  ("`volume_24h` ≡ 0 on all census rows"): reproduced over the now-180,000-row `universe_sweep`
  census — `volume_24h` is nonzero on exactly **1/180,000** (all-zero over the original 100k the
  finding measured), while `volume`/`open_interest` ARE populated on ~20k rows. **CONFIRMED** — the
  S39 kill holds and the collector bug (wrong source-field mapping) is real.
- `findings/2026-07-18-weather-books-tape-audit.md`'s load-bearing clean-day count (gates Q36/Q37):
  reproduced by FILE SHAPE (L25) — **07-17 is the only clean hourly day** (UTC hours 00–23, no
  intra-span gaps), 07-18 is broken (gaps at hours 09–12/14–18/20–21, VPS stall), 07-16 day-1
  partial, 07-19 in progress (1 pass at capture time, degraded pipe). **CONFIRMED.**

Both re-checks PASS — no GitHub issue opened.

**Unit 2 — Q21 replenishment.** Eligible (TODO/unclaimed/**gate-open**) research items = 0
(FILE-SHAPE-verified: Q19 burst tape not yet captured, Q36/Q37/Q43 time-gated, Q32/Q33/Q35-build/
Q42-part3 credential/auth-blocked, all Sx probes DONE-DEAD). Proposed 2 candidates, both KILLED at
idea stage by an independent `verifier`:
- **S41** (full-universe SIMULTANEOUS within-event overround-underflow arb scan over
  `tape/universe_sweep/`): `universe_sweep.v1` lacks strike-ladder fields
  (`strike_type`/`floor_strike`/`cap_strike`/`yes_ask_dollars`), so `anomaly_sweep.check_bracket_arb`
  cannot run on it; and its sub-$1 Σ`yes_ask` groups are no-offer artifacts — over `dt=2026-07-19`
  (20k rows, 1 `capture_id`) 1,565/2,441 multi-market groups sum below $1 but **0/1,565 are fillable,
  1,537 are all-zeros** (the L96/S38 illiquidity floor restated for the full-universe census).
- **S42** (perp funding-clamp reversion carry): the ±1bp funding dead-band is a persistent/
  near-absorbing state, not a coiled spring — after a zero print the next is zero again BTC 85% /
  ETH 87% / SOL 95%, no reversion signal; plus it needs holding a leveraged perp outside the binary/
  `real_ask` fill discipline (no fill model, L58) and duplicates Q43.

0 registered (the 5th round in a week, 4 registering 0 — no new tape surface since the 07-18 round;
never pad to quota). S41/S42 consumed → next free = S43. New lesson **L105** (generalizes L96: the
census can't feed the bracket-arb check; its sub-$1 sums are no-offer artifacts). Recorded at the
documentation tier — the edge-hunter leaves `.claude/agents` for Ryan-review, so the edge-prober.md
house-style bullet is left for a future research-loop idle run. See
`findings/2026-07-19-q21-idea-gen-round.md`.

**Unit 3 — probe-prep.** Nearest time-gate is Q19 (WC final tonight ~19:00Z); its burst harness
(`scripts/s17_leadlag_probe.py`, `scripts/s9_shock_eventstudy.py`) is already built, so tonight's
per-event run only executes. Q36 unblocks ~Jul-22 (naive) but is design-blocked on an intraday-KNYC
actuals source the daily `weather_actuals` feed lacks; Q43 ~Jul-23/24 is outside 72h. No new build
needed this run.

**Step 0b — stranded-tape sweep.** The three fresh 07-19 branches were <30min at first check;
`tape/hourly-202607190403Z` (a strict superset of 0356/0400Z) crossed the 30-min rule and a
line-level set-diff (not a byte/stat count) found **1,663 genuinely-missing lines** `main` lacked:
1,116 `orderbook_depth`, 530 `weather_books` (a second 07-19 hourly pass), 17 `perp_tape`
(crypto_hourly/polymarket_macro_pairs/sports_pairs were already fully in `main`). All JSON-validated
(0 parse failures), pure append, no reorder.

**Housekeeping.** 3 passed-event burst triggers (`kalshi-burst-cpi-0714`/`wcsemi1-0714`/
`wcsemi2-0715`) are still present — an agent cannot delete http_api-created routines (only Ryan can),
so named for his manual deletion; `wcsemi2` is still ENABLED and would misfire 2027-07-15.
`kalshi-burst-wcfinal-0719` (tonight) and `-fomc-0729` (future) stay. 164 stranded `tape/hourly-*` +
1 `tape/burst-*` ref-branches remain (their data is already in `main` — empty content diffs; the refs
are undeletable from a cloud session).

Gates: `pytest` **1228 passed** (rc=0), `python scripts/invariants.py --full` green (only pre-existing
non-gating advisories). No registry change, `kb/strategies/00-index.md` untouched — two-agent verdict
rule N/A (idea-stage kills + tape sweep + doc-tier lesson, not a verdict-class change). Step 9:
`SHADOW_REGISTRY`={s14_ladder_underwriting} only; `paper_pass.py` idempotent (0 newly processed),
realized P&L unchanged **+$11.65** (`broker_truth`; s14 is DEAD-at-real-fills per Q34 — proxy P&L,
not an edge).

---

## 2026-07-19 03:2x ET — Idle-run: stranded-tape sweep (22,019 lines, first 07-19 tape) + L65->L104 post-close-pickoff idea-stage-kill guardrail

Step 0a PASS: the sandbox's local `main` ref was stale (`69a3d3f`, dated 2026-07-16); `git fetch
origin main` + `git reset --hard origin/main` caught it up to the real HEAD `abb7c8f` (PR #119).
`kb/00-LOG.md` newest entry and newest `tape/*/dt=*` content both 2026-07-18/19 — no history rewind.
Step 0: only open PR is #77 (Ryan's stale 2026-07-15 queue-restock, already superseded, left untouched
per every prior run's flag).

**Step 0b (stranded-tape sweep):** `tape/hourly-20260719T0056Z` was the only unswept branch, and it
carried the entire FIRST 2026-07-19 tape day — `main` had zero `dt=2026-07-19.jsonl` files in any
family before this run. **22,019 lines**: 20,000 `universe_sweep`, 1,156 `orderbook_depth`, 530
`weather_books` (+45 `weather_books/meta`), 254 `sports_pairs`, 17 `perp_tape`, 15
`polymarket_macro_pairs`, 2 `crypto_hourly`. All JSON-validated (0 parse failures), pure addition —
no existing file was touched.

Queue re-scan reconfirmed 0 eligible TODO/IN-PROGRESS items: Q19 (WC-final burst window) hasn't
opened yet — kickoff is tonight 19:00Z, burst tape not yet captured; Q36 (`weather_books`) now sits at
4/7 days after this run's sweep, still short of its gate (~Jul-22/23); Q43 (`perp_tape`) sits at 3/7
days (~Jul-23/24); Q32/Q33/Q35-build stay blocked on Polymarket US credentials; Q42 part 3 stays
BLOCKED(needs-auth); Q21 idea-gen last completed 2026-07-18 by the nightly edge-hunter (0 registered
that round). This is an idle run.

**Idle-run policy order (a):** a naive "row contains the substring UNENFORCED" grep over
`kb/lessons/00-lessons.md` returns false positives (several rows just quote another row's status
inline) — per L102's own caught failure mode, cross-checked every UNENFORCED-tagged row's number
against every LATER row's text for an actual supersession claim (`supersedes`/`generalizes`/
`escalates`/`closes`). L65 (2026-07-15) came back as the true lowest-numbered still-open row: **Kalshi
empties and settles a sports order book AT close** — the maximum observed capture-to-settlement gap
across the entire committed `tape/orderbook_depth/` history is 0.024h (~1.4min), and every
genuinely-post-close capture found (L64's population) has a FULLY EMPTY book on both sides. There is
no post-close resting-quote window to pick off, on ANY timing definition — not just the mis-timed
ticker-HHMM-as-UTC one L64/L101 already fixed the parsing for.

**What was built:** a `.claude/agents/edge-prober.md` house-style bullet stating the L65 fact
directly, placed immediately before the existing L64/L101 `is_genuine_post_close` bullet — the point
is to reject a "post-close stale-quote pickoff" / settlement-lag proposal on sports tape (S28 family,
and any "buy the ex-post known winner" L66 variant) at the IDEA stage, before a fill-sim gets built at
all, rather than only after its close-time population is correctly parsed. No code change — L65 is a
market-structure fact about the venue, not a computation, so (unlike L90/L100, L64/L101, L51/L103)
there is no importable helper to write; this closes at the documentation/discoverability tier, the
same class as L94/L95's signposts. Ledger row: `kb/lessons/00-lessons.md` L104, superseding L65's
enforcement column (lesson content unchanged, ledger append-only).

No strategy claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent verifier
rule does not apply (tape sweep + documentation signpost, not a registry flip / bootstrap CI /
kill decision; matches the L93/L94/L95/L98/L99/L100/L101/L102 precedent of single-agent protocol-tier
lesson closures, not the L103 run's extra verifier pass).

Gates: `pytest` — **1228 passed** (rc=0, unchanged — no new tests, pure signpost + tape + ledger);
`python scripts/invariants.py --full` — exit 0 ("invariants: all green"), only pre-existing
non-gating advisories (this run's own now-swept stranded-ref warning, 4 dir-shaped `dt=` paths, 6
daily-cadence missing days). Step 9: `SHADOW_REGISTRY`={s14_ladder_underwriting} only; `paper_pass.py`
processed 9 newly-eligible fills off the new tape (233 deferred-caps, 222 deferred-coverage, 58
already-in-ledger), realized P&L **+$10.23 -> +$11.65** (`broker_truth`; s14 is DEAD-at-real-fills
per Q34, proxy P&L, not an edge) — ledger line appended to `paper/ledger/dt=2026-07-19.jsonl`.

---

## 2026-07-19 00:2x ET — Idle-run: stranded-tape sweep (1,850 lines) + L51->L103 importable disagreement-subset calibration-framing helper

Step 0a PASS: `origin/main` HEAD matched the last merged PR (#118); `kb/00-LOG.md` newest entry and
newest `tape/*/dt=*` content both 2026-07-18 — no history rewind. Step 0: only open PR is #77 (Ryan's
stale 2026-07-15 queue-restock, already superseded, left untouched per every prior run's flag).

**Step 0b (stranded-tape sweep):** `tape/hourly-20260718T2206Z` was the only unswept branch. A
comm-based per-family line-set diff (not stat/byte-count) found **1,850 lines** `main` was missing:
530 `weather_books`, 222 `sports_pairs`, 1,064 `orderbook_depth`, 17 `perp_tape`, 15
`polymarket_macro_pairs`, 2 `crypto_hourly`. All JSON-validated, 0 exact duplicates vs `main`, pure
append (no reorder of existing lines).

Queue re-scan reconfirmed 0 eligible TODO/IN-PROGRESS items: Q19 (WC-final burst tape) is ~19h out
from its own trigger; Q36 (`weather_books`) sits at 3 days including the stalled-VPS 07-18 gap, short
of its >=7-day gate; Q43 (`perp_tape`) sits at 2 days, also short of >=7 days. Idle-run policy order
(a) fired against the lessons ledger's own standing UNENFORCED queue. L51 was the true lowest
genuinely-open UNENFORCED row — every candidate below it was already superseded (L22->L24, L25->L29,
L27->L33, L28->L33, L32->L35, L39->L73/L98, L45->L49, L47->L95, L74->L75); the independent verifier
pass (below) re-checked this claim from scratch against the whole L1-L102 range and confirmed it,
noting the research-lead's own stated chain omitted L22/L25/L39/L47 (conclusion held regardless).

**What was built:** `core.bootstrap.disagreement_subset_calibration(hit_signal, hit_mid, tol=1e-9)` —
the L51 framing guardrail for a "does feature X beat the mid" calibration precheck on a two-way
market's disagreement subset. Returns `{"n", "mid_accuracy", "signal_accuracy", "is_strict_two_way",
"violating_indices"}`: the two accuracies are mechanically complementary
(`hit_signal[i] == not hit_mid[i]` on every row) rather than independent measurements, so the honest
report is the single "mid accuracy where they disagree = X%" statistic — exactly the framing that
would have kept Q26/S22's 27.9%/72.1% split from reading as a hidden contrarian edge. A non-empty
`violating_indices` PROVES the caller's "disagreement subset" wasn't a strict two-way partition rather
than masking the design bug. Pinned by new tests in `tests/test_bootstrap.py` (including the Q26/S22
27.9%/72.1% regression fixture), with a `.claude/agents/edge-prober.md` house-style note naming the
helper for any future calibration-precheck milestone. Ledger row: `kb/lessons/00-lessons.md` L103,
superseding L51's enforcement column (lesson content unchanged).

**Two-agent verifier confirmation: CONFIRMED.** Independent `verifier` agent re-derived L51's
lowest-open-row claim from the raw ledger (found and closed the same gap noted above), exercised
`disagreement_subset_calibration` directly (hand-checked 0.25/0.75 split, complementarity, the
violating-row flag, empty-input and length-mismatch behavior), cross-checked the Q26/S22 regression
fixture against `findings/2026-07-14-ofi-depth-imbalance-s22-verdict.md`'s real numbers (0.2791/0.7209,
n=86, sum 1.0 to full float precision), confirmed the ledger commit is a singular append (no deletions,
no L104+), and independently re-ran both gates. Verdict: **CONFIRMED**, no refutation.

Gates (re-run independently by both the building agent and the verifier): `pytest` — **1228 passed**
(rc=0); `python scripts/invariants.py --full` — **exit 0** ("invariants: all green"), only the
pre-existing non-gating advisories (1 stranded `tape/hourly-*` ref, 4 dir-shaped `dt=` paths, 6
daily-cadence missing days). Step 9: `SHADOW_REGISTRY`={s14_ladder_underwriting} only, realized P&L
unchanged **+$10.23** (`broker_truth`) — s14 is DEAD-at-real-fills per Q34, proxy P&L not an edge.
No strategy claim, no registry change (`kb/strategies/00-index.md` untouched).

---

## 2026-07-18 17:2x ET — Idle-run: stranded-tape sweep (1,898 lines) + weather_books data-quality audit (Q36 gate-at-risk)

Step 0a passed (local `main` reset cleanly to `origin/main` HEAD `0c01a0b`; `kb/00-LOG.md` newest
entry and newest `tape/*/dt=*` content both 2026-07-18 — no history rewind). Step 0: only open PR is
#77 (Ryan's stale 2026-07-15 queue-restock, already superseded, left untouched per every prior run's
flag). Full queue re-scan reconfirmed 0 eligible TODO/IN-PROGRESS items (Q19 time-gated WC final
Jul-19/FOMC Jul-29, Q32/Q33/Q35-build blocked on Polymarket US creds, Q36 gated ~Jul-22 weather_books
day-count, Q37 gated ~Aug-05, Q42 part 3 BLOCKED(needs-auth), Q43 gated ~Jul-23/24 perp_tape day-count,
Q21 idea-gen already completed today) — matches PR #117's scan from earlier today, this is the eighth
idle run today.

**Step 0b:** comm-based per-family line-set diff (not stat/byte-count) over every recent
`tape/hourly-*` branch. `tape/hourly-20260718T0059Z`/`0403Z` confirmed already fully swept (0 missing
lines everywhere). `tape/hourly-20260718T1855Z` carried **1,898 genuinely new lines**: 530
`weather_books`, 235 `sports_pairs`, 20,000 `universe_sweep`, 1,099 `orderbook_depth`, 17 `perp_tape`,
15 `polymarket_macro_pairs`, 2 `crypto_hourly`. All JSON-validated, pure append (no reorder).

**Idle-run policy (c): data-quality deep-dive.** Delegated to the `tape-auditor` agent: audited
`tape/weather_books/` (Q36's prerequisite family, ~4 days from its own ≥7-day gate) plus a
`weather_actuals` join-ability cross-check. **Verdict: gate-at-risk.** Schema/validity/tags are
pristine — 31,928/31,928 lines parse, 0 missing/extra fields vs the 24-field `weather_books.v1`
contract, `price_source_tag=real_ask` on 100% (zero synthetic/untagged), append-only confirmed (0
removed lines via `git log --numstat`) — but the **entire VPS collector pipeline stalled after
2026-07-18T08:30:19Z** (all families, not just weather_books — a host-uptime problem, not a
`weather_books.py` bug), permanently holing 07-18 hours 09–12 and leaving 14–23 near-empty. Only
**one** fully clean hourly day is banked so far (07-17); 07-16 is an expected day-1 partial; 07-18
does not currently qualify. The naive 7th-day date (~07-22) slips to **~07-23+ and keeps slipping for
every additional VPS-down day**. Also flagged: `weather_books/` is already 60 MB at day ~2.5 (past the
`tape/README.md` 50 MB external-storage trigger — Ryan's call), and a join-gap for Q36's design
(`weather_actuals` only settles DAILY KXHIGHT*/KXLOWT*, not hourly KXTEMPNYCH — Q36 will need an
intraday KNYC actual source). New lesson candidate for kb-distiller: gate progress should be measured
in committed clean capture-days on main, not calendar days elapsed since day-1. Full report:
`findings/2026-07-18-weather-books-tape-audit.md`. No strategy claim, no registry change — two-agent
verifier rule does not apply (data-quality audit, not a verdict-class change).

`pytest` green (no new tests — tape + one findings doc), `python scripts/invariants.py --full` green
(pre-existing non-gating L25/L74 advisories only). Step 9: `SHADOW_REGISTRY`={s14_ladder_underwriting}
only, `paper_pass.py` idempotent this run (0 newly processed), realized P&L unchanged **+$10.23**
(`broker_truth`). **Ops flag for Ryan (action needed): VPS collector appears down since ~08:30 UTC
today — restart it to stop losing weather_books/Q36 gate progress and other hourly-family cadence.**

## 2026-07-18 14:1x ET — Idle-run: shared `member_coord`/`ladder_spacing` bracket-ladder helper (L36→L102, no new stranded tape)

Research-loop cloud run. Step 0a PASS: local `main` reset cleanly to `origin/main` HEAD
`81c471c` (PR #116); merged PRs #112-#116 confirmed via GitHub MCP `list_pull_requests`
(all `merged`); `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` content both
2026-07-18 — no history rewind. Step 0: only open PR is #77 (Ryan's stale 2026-07-15
queue-restock, already superseded, left untouched per every prior run's flag). Full
Q0-Q46 re-scan reconfirmed 0 eligible TODO/IN-PROGRESS items — same blockers as PR #116
(Q19 WC final Jul-19 tomorrow/FOMC Jul-29, Q32/Q33/Q35-build blocked on Polymarket US
creds, Q36 gated ~Jul-22 [weather_books 3/7 days], Q37 gated ~Aug-05, Q42 part 3
BLOCKED(needs-auth), Q43 gated ~Jul-23/24 [perp_tape 2/7 days], Q21 completed today).
This is the seventh idle run of the day.

**Step 0b — stranded-tape sweep:** the `tape/hourly-*`/`tape/burst-*` branch list is
unchanged from PR #116's check (newest two: `20260718T0059Z`, `20260718T0403Z`, both
already fully swept). Nothing new.

**Idle-run policy (a):** started by targeting lesson **L7** ("never hardcode a
bracket/strike width... derive spacing from the ladder itself") as the next
lowest-numbered `UNENFORCED` row in `kb/lessons/00-lessons.md`. Mid-run discovered this
was a false read: L7 was already closed by **L36** (2026-07-12), which built
`core.pricing.infer_strike_spacing`. The ledger's supersession phrasing is inconsistent
enough across rows ("Supersedes L\<N\>'s enforcement column" vs "generalizes L\<N\>" vs
"L\<N\>'s own candidate wording... stayed unbuilt") that a naive regex scan for `L7`
missed L36. Correcting course: found a REAL, still-open duplication one layer up from
L36's fix — `scripts/s19_wing_fade_fillsim.py` and `scripts/s20_ladder_overround_anatomy.py`
each independently hand-rolled a byte-identical `member_coord`/`ladder_spacing` pair
(both correctly call `infer_strike_spacing` underneath, but the wrapper itself was never
shared — same duplication shape as L90's `_to_float`). Extracted both into
`core/pricing.py`, re-pointed both scripts to import them — zero behavior change, both
scripts' existing tests (`tests/test_s20_ladder_overround_anatomy.py`'s direct
`s20.member_coord`/`s20.ladder_spacing` calls) pass unmodified. 6 new tests in
`tests/test_substrate_primitives.py`. Extended the existing `.claude/agents/edge-prober.md`
L36 house-style bullet to also name `member_coord`/`ladder_spacing`. New lesson **L102**
records both the fix and the ledger-scanning lesson for the next idle run. No strategy
claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent verifier
rule does not apply (importable-helper build, same class as the L39→L98/L86→L99/
L90→L100/L64→L101 precedent, not a verdict-class change).

**Step 9 — paper sub-pass:** `SHADOW_REGISTRY`={s14_ladder_underwriting} only.
`paper_pass.py` idempotent this run (0 newly processed, 242 deferred(caps), 222
deferred(coverage), 58 already-in-ledger), realized P&L unchanged **+$10.23**
(`broker_truth`).

**Gates:** `pytest` → 1222 passed (1216 prior + 6 new). `python scripts/invariants.py
--full` → green (only the pre-existing non-gating L25/L74 advisories).

See `kb/lessons/00-lessons.md` L102; `core/pricing.py`; `.claude/agents/edge-prober.md`.

## 2026-07-18 11:1x ET — Idle-run: L64→L101 shared sports post-close-timing helper (no new stranded tape)

- **kalshi-research-loop cloud run.** Step 0a PASS — local `main` matched `origin/main` HEAD
  `77ff3b4`; merged PRs #111-#115 all present as ancestors (confirmed by
  `git merge-base --is-ancestor`); `kb/00-LOG.md` newest entry and newest `tape/*/dt=*`
  content both 2026-07-18 — no history rewind.
- **Step 0 claim-check:** only open PR is #77 (Ryan's stale 2026-07-15 queue-restock, its
  Q29-Q32 content long since superseded by different numbered items on `main` — left
  untouched, flagged by every prior run today).
- **Full Q0-Q46 re-scan: 0 eligible TODO/IN-PROGRESS items.** Q19's remaining per-event legs
  are future events (WC final Jul-19 tomorrow, no burst tape yet; FOMC Jul-29); Q32/Q33/
  Q35-build blocked on Polymarket US credentials; Q36 gated ~Jul-22 (`tape/weather_books/`
  3/7 days); Q37 gated ~Aug-05; Q42 part 3 BLOCKED(needs-auth); Q43 gated ~Jul-23/24
  (`tape/perp_tape/` 2/7 days); Q21 idea-gen round already completed today. This is the
  sixth idle run of the day.
- **Step 0b stranded-tape sweep:** the two newest `tape/hourly-*` branches
  (`20260718T0059Z`, `20260718T0403Z`) are unchanged from PR #115's check and were already
  fully swept (PR #111/#113/#114 chain) — nothing new.
- **Idle-run policy (a):** converted UNENFORCED lesson **L64** (a "post-close" population
  keyed off a sports ticker's embedded HHMM token read as UTC silently mislabels most of the
  population as post-close when it's actually pre-close — Q25's `post_close` bucket was
  99.86% mislabeled this way, understated by up to +24.33h) into an importable helper. L64's
  own candidate wording asked for exactly this: "a `core/`-level close-time helper so future
  probes don't reach for the ticker token by reflex." Extracted `scripts/
  q29_settlement_lag_probe.py`'s own `parse_sports_ticker_hhmm_as_utc`/`is_coarse_close_time`
  (byte-identical logic) into `core/timeutil.py` and re-pointed the script to import them —
  zero behavior change, its own `tests/test_q29_settlement_lag_probe.py` (which calls these
  as `q29.<name>`) passes unmodified. Added `core.timeutil.is_genuine_post_close(captured_at,
  close_dt, tz_uncertainty_hours=13.0, max_game_duration_hours=6.0)`, encoding the actual
  discipline (gate on the `broker_truth` settlement `close_time` plus a conservative
  tz-uncertainty-plus-game-duration margin; `None` on a coarse/date-only close) as one
  importable call, plus a `.claude/agents/edge-prober.md` house-style paragraph naming it for
  any future post-close/settlement-lag-adjacent probe (S28-adjacent family) — same signpost
  pattern as L45→L49, L59→L94, L76→L93, L47→L95, L39→L98, L86→L99, L90→L100. New lesson row
  **L101** supersedes L64's enforcement column (content unchanged, ledger append-only). No
  retrofit of Q29's already-run, already-DEAD verdict.
- No strategy claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent
  verifier rule does not apply (importable-helper build, same class as the L39→L98/L86→L99/
  L90→L100 precedent, not a verdict-class change).
- **Step 9 paper sub-pass:** `SHADOW_REGISTRY`={s14_ladder_underwriting} only. `paper_pass.py`
  idempotent this run (0 newly processed, 242 deferred(caps), 222 deferred(coverage), 58
  already-in-ledger), realized P&L unchanged **+$10.23** (`broker_truth`).
- **Gates:** `pytest -q` → 1216 passed (1205 prior + 11 new). `python scripts/invariants.py
  --full` → green (only the pre-existing non-gating L25/L74 advisories).
- See `tests/test_timeutil.py`, `core/timeutil.py`, `.claude/agents/edge-prober.md`,
  `kb/lessons/00-lessons.md` L101.

## 2026-07-18 12:1x ET — Idle-run: L90→L100 shared Kalshi `_dollars`/`_fp` field parser (no new stranded tape)

- **kalshi-research-loop cloud run.** Step 0a PASS — local `main` matched `origin/main` HEAD
  `1796bb9`; merged PRs #109-#114 all present as ancestors (confirmed by commit
  message/PR-number correlation in `git log`, since squash-merge SHAs differ from each PR's
  head branch commit); newest `kb/00-LOG.md` entry (09:1x ET) and newest `tape/*/dt=*` content
  both 2026-07-18 — no history rewind. Step 0: only open PR is #77 (Ryan's stale
  queue-restock from 2026-07-15, already independently landed by later runs — left untouched,
  as every prior run has flagged). Full Q0-Q46 re-scan reconfirmed 0 eligible TODO/IN-PROGRESS
  items: Q19 time-gated (WC final Jul-19 — tomorrow — burst tape not yet captured; FOMC
  Jul-29), Q32/Q33/Q35-build blocked on Polymarket US credentials, Q36 gated ~Jul-22
  (`tape/weather_books/` 3/7 days), Q37 gated ~Aug-05, Q42 part 3 BLOCKED(needs-auth), Q43
  gated ~Jul-23/24 (`tape/perp_tape/` 2/7 days), Q21 idea-gen round last completed today
  (2026-07-18) by the nightly edge-hunter (0 registered, S38/S39/S40 killed at idea stage).
  This is an idle run.
- **Step 0b: stranded-tape sweep — nothing new.** The two `tape/hourly-2026071*` branches
  still on the remote (`T0059Z`, `T0403Z`) were both already fully swept by prior idle runs
  (PR #111, #113, reconfirmed by PR #114); a fresh per-family `comm`-based line-set diff
  against current `main` for both branches found **0 missing lines** in any family.
- **Idle-run policy (a): L90 → L100.** Converted UNENFORCED lesson L90 (Kalshi's `/markets`
  objects carry settlement/BBO numeric fields under `_dollars`/`_fp`-suffixed string keys, not
  the bare names — a collector reading the bare key silently gets `None` for every row instead
  of erroring) into an importable shared helper. Found the exact duplication L90's own wording
  anticipated had already happened in production code: `collection/settlement_ledger.py` and
  `collection/universe_sweep.py` each independently hand-rolled a byte-identical `_to_float`
  (same body, near-identical docstring). Extracted `core/kalshi_fields.py`
  (`parse_kalshi_numeric`) and re-pointed both collectors to import it under their existing
  internal `_to_float` name — zero behavior change, both modules' own test suites (including
  `test_settlement_ledger.py`'s direct `sl._to_float(...)` calls) pass unmodified. 5 new tests
  in `tests/test_kalshi_fields.py` pin the shared implementation directly. Added a
  `.claude/agents/collector-engineer.md` house-style bullet naming it for the next new
  collector — same importable-helper-plus-signpost pattern as L39→L98
  (`decompose_edge_by_leg_volume`), L76→L93 (`collapse_duration_gated_runs`), L59→L94
  (`core.reversal.direction_precheck` discoverability), L47→L95 (`normalize_snapshot`
  docstring), and L86→L99 (`catastrophic_leg_drop_stress_check`). New lesson row **L100**
  supersedes L90's enforcement column (content unchanged, ledger append-only).
- No strategy claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent
  verifier rule does not apply (importable-helper build, same class as the
  L39→L98/L76→L93/L59→L94/L47→L95/L86→L99 precedent, not a verdict-class change).
- **Step 9 — paper sub-pass.** `SHADOW_REGISTRY`={s14_ladder_underwriting} only.
  `paper_pass.py` idempotent this run (0 newly processed, 242 deferred on caps, 222 deferred
  on coverage, 58 already-in-ledger), realized P&L unchanged **+$10.23** (`broker_truth`).
- Gates: `pytest` 1205 green (1200 prior + 5 new). `python scripts/invariants.py --full`
  green (only pre-existing non-gating L25/L74 advisories, plus the same two local
  `tape/hourly-20260718T0059Z`/`T0403Z` refs noted by the prior run — both fully reconciled,
  no action needed).

---

## 2026-07-18 09:1x ET — Idle-run: L86→L99 catastrophic-leg-drop stress-check helper (no new stranded tape)

- **kalshi-research-loop cloud run.** Step 0a PASS — local `main` reset cleanly to
  `origin/main` HEAD `2c5a0c2` (session started HEAD-detached at the same commit, moved onto
  a tracking `main`); merged PRs #109-#113 all present as ancestors (confirmed by commit
  message/PR-number correlation in `git log`); newest `kb/00-LOG.md` entry (02:16 ET) and
  newest `tape/*/dt=*` content both 2026-07-18 — no history rewind. Step 0: only open PR is
  #77 (Ryan's stale queue-restock from 2026-07-15, already independently landed by later
  runs — left untouched, as every prior run has flagged). Full Q0-Q46 re-scan reconfirmed 0
  eligible TODO/IN-PROGRESS items: Q19 time-gated (WC final Jul-19 — tomorrow — burst tape
  not yet captured; FOMC Jul-29), Q32/Q33/Q35-build blocked on Polymarket US credentials,
  Q36 gated ~Jul-22 (`tape/weather_books/` 3/7 days), Q37 gated ~Aug-05, Q42 part 3
  BLOCKED(needs-auth), Q43 gated ~Jul-23/24 (`tape/perp_tape/` 2/7 days), Q21 idea-gen round
  last completed today 02:16 ET by the nightly edge-hunter (0 registered, S38/S39/S40 all
  killed at idea stage). This is an idle run.
- **Step 0b: stranded-tape sweep — nothing new.** The two `tape/hourly-2026071*` branches
  still on the remote (`T0059Z`, `T0403Z`) were both already fully swept by the prior two
  idle runs (PR #111, PR #113); a fresh per-family `comm`-based line-set diff against
  current `main` for both branches found **0 missing lines** in any family. The 04:31/05:31/
  06:30/07:30/08:30 UTC hourly passes all landed directly on `main` (visible in `git log`),
  so no new branch was created since `T0403Z`.
- **Idle-run policy (a): L86 → L99.** Converted UNENFORCED lesson L86 (the winner/
  catastrophic-leg measurability asymmetry — when a per-unit P&L carries a large FIXED-LOSS
  leg and some units are dropped on that leg's measurability, zeroing the dropped leg instead
  of dropping the unit fabricates a free win and biases the mean positive; S14's own
  verifier check credited the 290 winner-leg-unmeasurable event-hours with payout=0 and
  confirmed the mean stayed negative, -0.0453 → -0.0152) into an importable helper:
  `core.bootstrap.catastrophic_leg_drop_stress_check(retained_pnls, n_dropped,
  generous_replacement_value=...)` recomputes the mean crediting the dropped units at the
  caller's chosen generous counterfactual and reports `sign_preserved` (True iff the
  reported and stress means share a sign; `None` if either is undefined — an honest unknown,
  never a fabricated bool), reproducing S14's own one-off verifier arithmetic as a reusable
  function. Added a `.claude/agents/edge-prober.md` house-style paragraph naming it for any
  future probe whose P&L carries a fixed catastrophic leg — same importable-helper-plus-
  signpost pattern as L39→L98 (`decompose_edge_by_leg_volume`), L76→L93
  (`collapse_duration_gated_runs`), L59→L94 (`core.reversal.direction_precheck`
  discoverability), and L47→L95 (`normalize_snapshot` docstring). 8 new tests in
  `tests/test_bootstrap.py` (the S14-shape sign-preserved case, a sign-flip red-flag case,
  zero-dropped no-op, both-exact-zero preserves, zero-vs-nonzero does-not-preserve,
  empty-input honest-None, nonempty-retained-zero-dropped stays defined, negative-n_dropped
  raises). New lesson row **L99** supersedes L86's enforcement column (content unchanged,
  ledger append-only). No retrofit of `scripts/s14_queue_fillsim.py`'s already-run,
  already-DEAD Q34 verdict — this helper is for the next probe with a fixed-catastrophic-leg
  P&L.
- No strategy claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent
  verifier rule does not apply (importable-helper build, same class as the
  L39→L98/L76→L93/L59→L94/L47→L95 precedent, not a verdict-class change).
- **Step 9 — paper sub-pass.** `SHADOW_REGISTRY`={s14_ladder_underwriting} only.
  `paper_pass.py` idempotent this run (0 newly processed, 242 deferred on caps, 222 deferred
  on coverage, 58 already-in-ledger), realized P&L unchanged **+$10.23** (`broker_truth`).
- Gates: `pytest` 1200 green (1192 prior + 8 new). `python scripts/invariants.py --full`
  green (only pre-existing non-gating L25/L74 advisories, plus the two local
  `tape/hourly-20260718T0059Z`/`T0403Z` refs noted above — both fully reconciled, no
  action needed).

---

## 2026-07-18 02:16 ET — Idle-run: stranded-tape sweep (1,777 lines) + L39→L98 income-leg-decomposition helper

- **kalshi-research-loop cloud run.** Step 0a PASS — local `main` fast-forwarded cleanly to
  `origin/main` HEAD `efdc5da`; merged PRs #108-#112 all present as ancestors; newest
  `kb/00-LOG.md` entry and newest `tape/*/dt=*` content both 2026-07-18 — no history rewind.
  Step 0: only open PR is #77 (Ryan's stale queue-restock, already independently landed by
  later runs — left untouched, as every prior run has flagged). Full Q0-Q46 re-scan
  reconfirmed 0 eligible TODO/IN-PROGRESS items: Q19 time-gated (WC final Jul-19, FOMC
  Jul-29), Q32/Q33/Q35-build blocked on Polymarket US credentials, Q36 gated ~Jul-22
  (weather_books day-count), Q37 gated ~Aug-05, Q42 part 3 BLOCKED(needs-auth), Q43 gated
  ~Jul-23/24 (perp_tape day-count), Q21 idea-gen round last completed today by the nightly
  edge-hunter (PR #112). This is an idle run.
- **Step 0b: stranded-tape sweep.** Only stranded branch newer than PR #111's prior sweep
  was `tape/hourly-20260718T0403Z` (>2h old). A full per-family `comm`-based line-set diff
  (not a stat/byte-count check) found **1,777 lines** `main` was missing: 950
  `orderbook_depth`, 530 `weather_books`, 263 `sports_pairs`, 17 `perp_tape`, 15
  `polymarket_macro_pairs`, 2 `crypto_hourly`. All JSON-validated, 0 exact duplicates vs
  `main`, pure append (no reorder of existing lines).
- **Idle-run policy (a): L39 → L98.** Converted UNENFORCED lesson L39 (a candlestick/volume
  fill proxy's income leg is biased upward for a bracket-ladder P&L that is a small net of
  two large legs — S14's own +$0.0925 mean was 78% attributable to sub-100-contract-volume
  legs, i.e. the fat nominal overround was almost entirely thin near-money pass-through, not
  a real underwritten edge) into an importable helper:
  `core.bootstrap.decompose_edge_by_leg_volume(leg_pnls, leg_volumes,
  thin_volume_threshold=...)` reports what fraction of a pooled edge is carried by legs
  below a volume threshold, with an honest `None` (never a fabricated 0.0 or a crash) on a
  zero-total edge. Added a `.claude/agents/edge-prober.md` house-style paragraph naming it
  for any future probe evaluating a small-net-of-two-large-legs bracket edge — same
  importable-helper-plus-signpost pattern as L76→L93 (`collapse_duration_gated_runs`),
  L59→L94 (`core.reversal.direction_precheck` discoverability), and L47→L95
  (`normalize_snapshot` docstring). 7 new tests in `tests/test_bootstrap.py` (the S14-shape
  thin-legs-dominate case, all-thick/all-thin fractions, tunable threshold,
  zero-total-is-honest-None, empty-input, length-mismatch-raises). New lesson row **L98**
  supersedes L39's enforcement column (content unchanged, ledger append-only). No retrofit
  of `scripts/s14_queue_fillsim.py`'s already-run, already-DEAD Q34 verdict — S14 died on
  the queue-aware CI itself, not on this decomposition; this helper is for the next
  candle-proxy-adjacent probe.
- No strategy claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent
  verifier rule does not apply (tape sweep + importable-helper build, same class as the
  L76→L93/L59→L94/L47→L95 precedent, not a verdict-class change).
- **Step 9 — paper sub-pass.** `SHADOW_REGISTRY`={s14_ladder_underwriting} only.
  `paper_pass.py` idempotent this run (0 newly processed, 242 deferred on caps, 216 deferred
  on coverage, 58 already-in-ledger), realized P&L unchanged **+$10.23** (`broker_truth`).
- Gates: `pytest` 1192 green (1185 prior + 7 new). `python scripts/invariants.py --full`
  green (only pre-existing non-gating L25/L74 advisories).

## 2026-07-18 00:2x ET — Q21 idea-gen round (edge-hunter): S38/S39/S40 all killed at idea stage; adversarial review clean

- **kalshi-edge-hunter nightly run** (the thinking seat). Step 0a PASS — no history rewind: newest
  `kb/00-LOG.md` entry and newest `tape/*/dt=*` content both 2026-07-18; recent merged PRs #105-#111
  all present as ancestors of `origin/main`. Step 0: only open PR is #77 (Ryan's stale queue-restock,
  3 days old — under the 5-day Ryan-side threshold and already flagged many times, so NOT re-flagged,
  per the "don't re-flag with no new info" discipline). Step 0b: 157 stranded `tape/hourly-*` + 1
  `tape/burst-*` branch reported (the union-append sweep is the 3h research loop's recurring job).
- **Unit 1 — adversarial review of the last-24h findings (the two Q42 findings), both PASS.** Re-ran
  one load-bearing number per finding from raw tape: (a) the funding-clamp pooled exact-zero fraction
  reproduced independently at **0.7672** (the finding's 0.762 + one extra 07-18 day of prints) with
  **0 nonzeros in (0,1e-4)** exactly as claimed and per-contract BTC 0.677 / LINK 0.991 reproducing;
  (b) the cross-venue funding join's Hyperliquid leg is tagged `broker_truth` with `raw_sha256`, and
  the finding honestly states "NOT a P&L verdict — no fee/carry model," so no fee was misapplied to
  the differential. Nothing failed the re-check → no `review:` GitHub issue opened.
- **Unit 2 — Q21 replenishment round (0 eligible items).** Verified 0 eligible by FILE SHAPE (L25):
  Q19 remaining legs are future events (WC final Jul-19, FOMC Jul-29, no burst tape yet), Q36 gated
  ~Jul-22 (`tape/weather_books/` 3/7 daily days), Q37 ~Aug-05, Q43 gated ~Jul-23 (`tape/perp_tape/`
  2/7 days), Q32/Q33/Q35-build blocked on Polymarket creds, Q42 part 3 BLOCKED(needs-auth). Proposed
  **3 new candidates (S38/S39/S40), all KILLED at idea stage by independent `verifier` attack that
  re-ran the actual committed tape → 0 registered** (two-agent rule; register survivors, never pad —
  same clean sweep as the 07-15 S25/26/27 and 07-16 S35/36/37 rounds). **S38** (full-universe
  cross-category calibration census): the "category gradient" that was the whole escape from
  S1/S7/S23 doesn't exist — the census is 99.6% two auto-generated combo series (no category field),
  the depth-gated fillable population is 557/100k rows (0.56%), 99.4% those combos, longshot-skewed →
  the dead favorite-longshot factor slot; mispriced tail is the unfillable 96%; a ~100-cell search
  has no BH-FDR control (S20/L41 luckiest-cell trap). **S39** (attention-shock fade, Barber–Odean):
  uncomputable — `volume_24h` is identically 0.0 on all 100k `universe_sweep` rows AND the 5 sweeps
  are disjoint slices (0 cross-capture ticker overlap, so no per-market delta exists); and the fade
  reduces to the dead S24 taker round-trip. **S40** (LIP-window fresh-listing maker): the load-bearing
  "50% maker-fee discount" fact is UNVERIFIED — `kb/kalshi-api/03-fees-and-breakeven.md` explicitly
  refuses that reading of `discount_factor_bps`, which may be a reward-pool weight; also duplicates
  Q37, short-queue escape tape-refuted (median 4206 resting contracts/market), no signal (S1), fill
  unmeasurable at hourly cadence. New lessons **L96** (verify a `universe_sweep` signal field is
  non-zero AND cross-capture overlap>0 before proposing any per-market delta — a mid-cursor-capped
  census is not a panel; `volume_24h=0` is a collector-bug candidate) and **L97** (an incentive-program
  bps parameter is `synthetic` until its mechanism is pinned — the pt1 plausible-unattacked-number
  bar). Still **0 proven edges**; S38/S39/S40 consumed → next free = **S41**. See
  `findings/2026-07-18-q21-idea-gen-round.md`.
- **Unit 3 — probe-prep: no target.** No time-gated item unblocks within ~72h (Q36 ~Jul-22 and Q43
  ~Jul-23 are both just outside the ~Jul-21 cutoff; Q19's WC-final probe script already exists from
  the WC-semi2 leg). Nothing to build.
- **Housekeeping.** 3 `kalshi-burst-*` triggers whose event date has passed and rolled to 2027 named
  for deletion: `kalshi-burst-cpi-0714`, `kalshi-burst-wcsemi1-0714`, `kalshi-burst-wcsemi2-0715`
  (WC semis don't recur annually; the CPI burst was a one-off). The two live ones (`wcfinal-0719`,
  `fomc-0729`) are upcoming — kept. **Data-quality flag for a future collector run:**
  `collection/universe_sweep.py` persists `volume_24h=0` on 100% of rows (likely a `volume_24h_fp`
  field-name bug) and its 20k-call cap paginates a disjoint slice each pass (no per-market panel) —
  beyond PR #107's already-escalated cap/storage design calls.
- Gates: `pytest` + `python scripts/invariants.py --full` green (docs-only diff — findings/,
  kb/00-LOG.md, kb/lessons/, LOOP-QUEUE.md). No registry change (`kb/strategies/00-index.md`
  untouched), no strategy claim, so the two-agent verdict rule is satisfied by the per-candidate
  verifier kills (nothing registered). Step 9 paper sub-pass: `SHADOW_REGISTRY`={s14_ladder_underwriting}
  only, `paper_pass.py` idempotent this run (0 newly processed, 242 deferred-caps, 212 deferred-
  coverage, 58 already-in-ledger), realized P&L unchanged **+$10.23** (`broker_truth`) — reminder that
  s14 is DEAD-at-real-fills (Q34), so this is candle-proxy paper P&L, not an edge; deregistering the
  shadow stays a Ryan judgment call.

---

## 2026-07-17 23:1x ET — Stranded-tape sweep (21,844 lines) + L47→L95 book-depth-float signpost (idle-run milestone)

- Research-loop cloud run. Step 0a: local `main` fast-forwarded cleanly to `origin/main` HEAD
  (`3bbd48b`); merged PRs #101-#110 all present as ancestors; `kb/00-LOG.md` newest entry and
  newest `tape/*/dt=*` content both 2026-07-18 — no history rewind. Step 0: only open PR is
  #77 (Ryan's stale queue-restock, already independently landed by later runs — left untouched,
  as every prior run has flagged; not claimed work per its title). Queue scan (Q0-Q46)
  reconfirmed 0 eligible TODO/IN-PROGRESS items: Q19 time-gated (WC final Jul-19, FOMC Jul-29),
  Q32/Q33/Q35-build blocked on Polymarket US credentials, Q36 gated to ~Jul-22 (weather_books
  day-count), Q37 gated to ~Aug-05, Q42 part 3 BLOCKED(needs-auth), Q43 gated to ~Jul-24
  (perp_tape day-count), Q21 idea-gen round last completed 2026-07-16 (nightly edge-hunter's
  item by default, not re-run here). This is an idle run.
- **Step 0b sweep found a large real gap.** The only stranded branch newer than PR #110's own
  sweep is `tape/hourly-20260718T0059Z` (>30min old). A full per-family `comm`-based line-set
  diff (not a stat/byte-count check) found **21,844 lines** `main` was missing: 20,000
  `universe_sweep` (a full fresh Q46 BBO census pass — this family is intentionally NOT deduped
  across passes, so this is a legitimate second snapshot, not a duplicate), 998
  `orderbook_depth`, 530 `weather_books`, 282 `sports_pairs`, 17 `perp_tape`, 15
  `polymarket_macro_pairs`, 2 `crypto_hourly`. All lines JSON-validated, 0 exact duplicates vs.
  `main` or within the missing set, pure append (no reorder of existing lines). Also re-checked
  `tape/burst-20260714T120659Z` (the one stale burst branch) — still fully covered, nothing to
  sweep there.
- **Idle-run policy order (a):** converted lesson **L47** (UNENFORCED — `orderbook_depth`'s
  persisted book-side sizes are floats and can be fractional, e.g. a real observed KXWCGAME
  best-level size of 91,316.82 contracts; a consumer coercing to int silently corrupts
  queue-depth reads) into a documented fact at its source: `collection.normalize.
  normalize_snapshot`'s docstring now states the float/fractional property directly (the single
  shared function every book-side-size consumer already reuses, per `orderbook_depth.py`'s own
  "Reuse" section), plus a `.claude/agents/edge-prober.md` house-style paragraph naming the
  discipline for any future probe reading `tape/orderbook_depth/`. No behavior change —
  `normalize_snapshot` already cast sizes via `float()`; this closes the discoverability gap
  L47 actually named (same pattern as L45→L49, L76→L93, L59→L94). Also confirmed L45's own row
  is NOT stale as the prior run's "Next" note worried — L49 (2026-07-14) already superseded it
  with an importable `core.timeutil.parse_crypto_hour_token_close_utc` helper and a house-style
  signpost; append-only means L45's own row stays raw UNENFORCED forever by design, L49 is the
  live state. New lesson row L95 supersedes L47's enforcement column (content unchanged,
  ledger append-only).
- Gates: `pytest -q` green (1185 — unchanged, no new tests this run, pure docstring + signpost
  + ledger work), `python scripts/invariants.py --full` green (only the pre-existing non-gating
  L25/L74 advisories).
- No strategy claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent
  verifier rule does not apply (tape sweep + house-style discoverability fix, same class as the
  Q44/Q45/Q46/L76→L93/L59→L94 precedent, not a verdict-class change).
- Step 9: `SHADOW_REGISTRY`={s14_ladder_underwriting} only, `paper_pass.py` idempotent this run
  (0 newly processed, 242 deferred on caps, 210 deferred on coverage, 58 already-in-ledger),
  realized P&L unchanged +$10.23 (`broker_truth`).

**Next:** the lessons ledger's remaining thin UNENFORCED rows (L51, L68 — house-style-only
candidates for `.claude/agents/edge-prober.md`, weaker than L47/L59/L76 had since neither names
a concrete importable helper) stay the standing queue for the next idle run. Q19/Q36/Q37/Q42
part 3/Q43 open on their own schedule (WC final Jul-19, FOMC Jul-29, weather/perp day-counts
through late July/early August, and Q42 part 3 whenever Ryan-side `/margin` auth exists).

---

## 2026-07-18 00:2x ET — Stranded-tape sweep (959 lines) + L59→L94 reversal-precheck signpost (idle-run milestone)

- Research-loop run. Step 0a: this session's local `main` was a stale ref carrying a
  byte-identical-content-but-rewritten-history copy of the repo (50 commits, no merge-base
  with `origin/main` — same file contents, different SHAs); reset local `main` to
  `origin/main` HEAD (`56cc03b`) rather than rebase onto a disjoint history. Merged PRs
  #105-#109 all present as ancestors; `kb/00-LOG.md`/tape dates both 2026-07-17 — no rewind
  of `origin/main` itself, only a local clone artifact. Step 0: only open PR is #77 (Ryan's
  stale queue restock, already independently landed by later runs — left untouched, as every
  prior run has flagged). Queue scan (Q0-Q46) reconfirmed genuinely 0 eligible TODO/IN-PROGRESS
  milestones: Q19 time-gated (WC final Jul 19 / FOMC Jul 29), Q32/Q33/Q35-build blocked on
  Polymarket US credentials, Q36 gated to ~Jul-22 (2/7 `weather_books` coverage days), Q37
  gated to ~Aug-05, Q43 gated to ~Jul-24 (1/7 `perp_tape` coverage days), Q21 idea-gen round
  last completed 2026-07-16 (nightly edge-hunter's item by default, not re-run here).
- **Step 0b sweep found REAL unswept content the immediately-prior run's own sweep missed.**
  That run (PR #109) diffed `tape/hourly-20260717T1600Z` and reported it fully covered by its
  806-line sweep, but its check only compared 4 families (`crypto_hourly`,
  `polymarket_macro_pairs`, `sports_pairs`, `weather_books`). A full per-file `comm`-based
  line-set diff across every `.jsonl` family in that branch (not a partial family list) found
  942 `orderbook_depth` + 17 `perp_tape` lines still missing from `main` — 959 total, all
  JSON-valid, 0 exact duplicates, unique `capture_id`s (`20260717T1555Z`/`20260717T1600Z`).
  Union-appended, pure append (no reorder). Also re-verified `tape/hourly-20260717T1556Z`/
  `T0403Z` and six other 2026-07-16/17 branches — all fully covered, nothing else missing.
- **Idle-run policy order (a):** converted lesson **L59** (UNENFORCED — a momentum/reversal
  precheck must report reversal FREQUENCY and the sign-conditioned mean next-step as two
  independent numbers, never classify on frequency alone; S24's raw continuation frequency
  0.454 alone reads as momentum but the sign-conditioned mean pointed the opposite way).
  Found the helper L59 called for already existed — `core.reversal.direction_precheck` +
  `tests/test_reversal.py`, already `test`-tier per lesson L72 — but was undiscoverable: no
  `.claude/agents/edge-prober.md` house-style line named it, and nothing outside its own test
  file imported it. Added a house-style paragraph naming it for any future momentum/reversal
  precheck, same signpost pattern as L45's `core.timeutil` entry and L76→L93's
  `core.bootstrap` entry. No code change to `core/reversal.py` — its 11 existing tests still
  green. New lesson row L94 supersedes L59's enforcement column (content unchanged,
  ledger append-only).
- Gates: `pytest -q` green (1185 — unchanged, no new tests this run, pure signpost + ledger
  work), `python scripts/invariants.py --full` green (only the pre-existing non-gating
  L25/L74 advisories).
- No strategy claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent
  verifier rule does not apply (tape sweep + house-style discoverability fix, same class as
  the Q44/Q45/Q46/L76→L93 precedent, not a verdict-class change).
- Step 9: `SHADOW_REGISTRY`={s14_ladder_underwriting} only, `paper_pass.py` processed 10
  newly-eligible fills this run (242 deferred on caps, 204 deferred on coverage, 48
  already-in-ledger), realized P&L +$9.91→**+$10.23** (`broker_truth`).

**Next:** the lessons ledger's remaining thin UNENFORCED rows (L47/L51/L68 — mostly
proposal-time/docstring-class disciplines with weaker code-helper candidates than L59/L76
had) stay the standing queue for the next idle run; separately, L45's own row still reads
raw UNENFORCED despite `core.timeutil.parse_crypto_hour_token_close_utc` already being
house-style-encoded in `edge-prober.md` — a stale-row fix like this run's L59, flagged but
not done here (scope: one milestone). Q19/Q36/Q37/Q43 open on their own schedule (WC final
Jul 19, FOMC Jul 29, weather/perp day-counts through late July/early August).

---

## 2026-07-17 21:1x ET — Stranded-tape sweep (806 lines) + L76→L93 duration-gate helper (idle-run milestone)

- Research-loop run. Step 0a: no history rewind (`origin/main` HEAD matches local, merged
  PRs #101-#108 all present in history, `kb/00-LOG.md`/tape dates both 2026-07-17). Step 0:
  only open PR is #77 (Ryan's stale queue restock, base far behind, already independently
  landed by later runs — left untouched, as every prior run has flagged). Queue scan (every
  item Q0-Q46) reconfirmed genuinely 0 eligible TODO/IN-PROGRESS milestones — matches the
  prior run's (Q37 fee sub-task, 18:2x ET) own finding; every non-DONE item is still either
  BLOCKED or time/day-count GATED with its gate not yet open.
- **Step 0b sweep found REAL unswept content**, contrary to several recent runs' "nothing
  new since PR #102's sweep at 0403Z" note: two newer branches, `tape/hourly-20260717T1556Z`
  and `tape/hourly-20260717T1600Z` (both >5h old, well past the 30-min freshness guard),
  carried lines `main` was missing. Did a proper line-set diff (not a `git diff --stat` byte
  count, which undercounted — a naive tail-2 spot-check on `crypto_hourly` first read "0
  missing" and was wrong; the full-file line-set diff found 2). Union-appended, JSON-validated,
  0 exact duplicates, pure append (no reorder): 2 `crypto_hourly`, 15 `polymarket_macro_pairs`,
  259 `sports_pairs`, 530 `weather_books` lines (806 total) into today's per-day tape files.
  `git push origin --delete` on the two branches was not attempted (confirmed-dead permission
  boundary since 2026-07-04's log entries — cloud sessions cannot delete remote branches
  either); left in place, harmless/stale like the hundreds of older already-reconciled branches.
- **Idle-run policy order (a):** converted lesson **L76** (UNENFORCED — a structural-arb
  run-collapse executability gate keyed on snapshot COUNT is not a duration gate; W-D's own
  17 count-gated runs were all <=1.0s wall-clock) into an importable helper:
  `core.bootstrap.collapse_duration_gated_runs(is_hit, seconds, depths,
  min_duration_seconds=..., min_depth=...)` — collapses consecutive per-snapshot hits into
  maximal runs, reports BOTH snapshot count and summed wall-clock seconds, gates `executable`
  on the duration (and optional depth) floor, never on count alone. 9 new tests in
  `tests/test_bootstrap.py`. `.claude/agents/edge-prober.md` house style updated to name it,
  same pattern as L33/L35/L36/L49's prior bootstrap-module helpers. Does not retrofit
  `scripts/probe_ladder_coherence.py`'s already-run W-D dossier (that scan's numbers stand
  as-is) — for the next structural-arb probe. New lesson row L93 supersedes L76's enforcement
  column (content unchanged, ledger append-only).
- Gates: `pytest -q` green (1185 = 1176 prior + 9 new), `python scripts/invariants.py --full`
  green (only the pre-existing non-gating L25/L74 advisories; the stranded-branch advisory
  this run's sweep resolves also fired, confirming the sweep was the correct action).
- No strategy claim, no registry change (`kb/strategies/00-index.md` untouched) — two-agent
  verifier rule does not apply (tape sweep + methodology-helper build, same class as the
  Q44/Q45/Q46 collector-build precedent, not a verdict-class change).
- Step 9: `SHADOW_REGISTRY`={s14_ladder_underwriting} only, `paper_pass.py` idempotent this
  run (0 newly processed, 48 already-in-ledger), realized P&L unchanged +$9.91 (`broker_truth`).

**Next:** L76's own class of remaining candidates (L39/L59's per-probe verdict-methodology
gates) stay the standing UNENFORCED queue for the next idle run; Q19/Q36/Q37/Q43 open on
their own schedule (WC final Jul 19, FOMC Jul 29, weather day-counts through early August).

---

## 2026-07-17 18:2x ET — Q37 fee-structure sub-task: weather LIP maker-fee discount confirmed live (idle-run milestone)

- Research-loop run. Step 0a: no history rewind (main's tip and `kb/00-LOG.md`/tape dates agree).
  Step 0: only open PR is #77 (Ryan's own stale `Q29-Q32` queue restock, base ~2 days behind
  current `main` and all four of its queue items already independently landed as DONE by later
  runs — left untouched, noted stale rather than merged or redone). Step 0b: nothing new to sweep.
- Queue scan (every item Q0–Q46) found genuinely 0 eligible TODO/IN-PROGRESS milestones: every
  non-DONE item is either BLOCKED (Q14/Q15/Q33/Q35-build, all data-adequacy or Ryan-credential
  gated) or time/tape-GATED with its gate not yet open (Q19 WC-final Jul 19 / FOMC Jul 29, Q36
  ≥7 weather-book days ~Jul 22-23, Q37 ≥21 summer contract-days ~Aug 5, Q43 ≥7 perp_tape days).
  Matches Q21's own 2026-07-16 "0 non-blocked runnable-now items" finding — this would otherwise
  be an IDLE RUN. Q37's own text names one exception: "Fee-structure sub-task (cheap, runnable
  NOW): pull `get-series-fee-changes`/`get-event-fee-changes` for the weather series and pin the
  ACTUAL maker fee / any LIP rebate window" — ungated, cheap, and closes the standing "Open item"
  in `kb/kalshi-api/03-fees-and-breakeven.md`. Took that as this run's real-work milestone.
- Built `scripts/weather_fee_schedule_probe.py` (+9 offline tests, `FakeKalshi`-mocked, no live
  network in tests) that reuses `collection.weather_books`'s own series-discovery logic (never a
  hand-maintained ticker list) and queries three read-only, unauthenticated Kalshi endpoints:
  `/series?category=Climate+and+Weather` (per-series `fee_type`/`fee_multiplier`), `/series/fee_changes`
  + `/events/fee_changes` (`show_historical=True`), and `/incentive_programs?type=liquidity` (bounded,
  paginated, truncation reported honestly).
- **Live run (2026-07-17):** all 48 tracked temperature series carry the standard base rate
  (`fee_type=quadratic`, `fee_multiplier=1` — same coefficients `core.pricing` already uses) with
  **zero** historical or scheduled series-/event-level fee overrides, ever, including `KXTEMPNYCH`.
  Settlement fees are zero for binary yes/no per Kalshi's own Market Settlement doc (`docs` citation)
  — fees are charged once, at fill. **New finding:** a standing platform-wide Liquidity Incentive
  Program DOES apply to weather listings — every newly-listed weather market (hourly `KXTEMPNYCH`
  family and daily `KXHIGH*`/`KXLOWT*` ladders alike) gets a `discount_factor_bps=5000` (50%) maker
  fee discount for ~54-60 minutes post-listing, gated on providing up to 1000 (or 300) contracts of
  resting size. Pull (40 bounded pages, 40k programs, **truncated — platform-wide universe exceeds
  the cap, so this is a lower bound**) found 10,372 weather-tagged programs, window 2026-05-12 →
  still generating new entries at probe time (a standing program, not a one-off promo). Payout
  mechanics (`discount_factor_bps` vs. the separate `period_reward` pool field) are NOT documented
  beyond field names in Kalshi's public API docs — flagged explicitly rather than guessed at.
- **Distinguished from an already-dead idea, on purpose:** the 2026-06-18 dead-end ledger already
  killed "Kalshi LIP maker-rebate harvest" (treating the reward payout itself as the edge — correctly
  rejected as sub-$1-per-provider against dedicated farmers, same adverse-selection overround as any
  resting bid). This entry does not reopen that. It answers a narrower mechanical question Q37's own
  fill-sim needs regardless: what fee rate applies if an EMOS-signal maker bid happens to land inside
  a new-listing window. Documented the distinction directly in the kb note so a future reader doesn't
  conflate the two.
- No strategy claim, no P&L, no registry change — a fee-schedule confirmation, not a verdict; the
  two-agent rule does not apply (same class as Q44/Q45/Q46's collector-build precedent). `pytest`:
  1176 passed (1167 prior + 9 new). `invariants --full`: green (only the pre-existing non-gating
  L25/L74 advisories). Q37's main gated milestone (summer maker fill-sim) stays TODO, waiting on
  ≥21 summer contract-days of tape (~2026-08-05).
- Files: `scripts/weather_fee_schedule_probe.py`, `tests/test_weather_fee_schedule_probe.py`,
  `kb/kalshi-api/03-fees-and-breakeven.md`, `LOOP-QUEUE.md` (Q37 status).

## 2026-07-17 11:37 ET — Q46: full-universe top-of-book sweep built; live universe is >80k markets (the queue's ~10k premise is broken)

- Research-loop run (step 0/0a/0b already cleared by the parent: only open PR is #77, no history rewind,
  nothing new to sweep off stranded branches). Q46 was soft-unblocked by Q44 + Q45 landing earlier today.
- Built `collection/universe_sweep.py` (+16 tests: 10 `tests/test_universe_sweep.py` + 6 wiring tests in
  `tests/test_hourly_pass.py`) — a read-only, unauthenticated, paginated sweep of the public
  `/markets?status=open` listing with NO `series_ticker` (a genuine full-universe enumeration), bounded at a
  20-call cap. One append-only `real_ask`-tagged JSONL snapshot line per open market with raw top-of-book
  (`yes_bid`/`yes_ask`/`no_bid`/`no_ask` parsed from Kalshi's `_dollars` strings, L90) + at-touch sizes +
  `last_price` + `volume`/`volume_24h` + `open_interest` + `liquidity`, `raw_sha256` page-provenance per line.
  Top-of-book ONLY — zero per-market `/orderbook` calls (no scope-creep into the L2/Phase-2 depth lane). A BBO
  time series, so NOT deduped across passes (unlike the settlement label ledger). Honest completeness: a call-cap
  truncation with an active cursor sets `truncated=True`/`completeness_ok=False`; nothing else lowers it.
- Wired into `hourly_pass.py` on `UNIVERSE_SWEEP_UTC_HOURS = {0, 6, 12, 18}` with the same `_safe_call`
  fault-isolation as every sibling; these are FRESH live BBOs so they fold into n_markets/n_lines.
- **Live run, independently re-verified against the committed tape (not just the agent's self-report):** 20 calls,
  20,000 lines, all `price_source_tag: real_ask`, single `capture_id`, 0 JSON errors, 0 missing required fields;
  7,489/20k lines carry a non-zero `yes_ask`, 2,018/20k a non-zero `volume`. `pytest`: 1167 passed (1151 prior +
  16 new). `invariants --full`: green (only pre-existing non-gating L25/L74 advisories); Hard Rule #3 not tripped.
- **STOP-level premise finding, ESCALATED to Ryan (not silently forced):** the live `status=open` universe is
  **>80,000 markets** (probed to 80 calls; cursor still active at 80k), NOT the ~10k the queue assumed. So
  “≥95% coverage in ≤20 calls” is UNMEETABLE — 20×1000 reaches <25% and every live pass HONESTLY reports
  `completeness_ok=False`. The collector's honest-partial behavior works as designed; the acceptance target and
  its 10k premise are what's broken.
- **Storage bombshell (GOAL.md M3):** ~17.8 MB per capped 20k-line pass × 4/day ≈ ~71 MB/day — over the 50 MB
  ceiling in a single day (full 80k coverage ≈ ~1 GB/day), vs the queue's projected 12 MB/day. A design decision
  is needed BEFORE this leg runs on the live cadence; the wiring is in place but firing {0,6,12,18} is effectively
  gated behind that decision (flagged, not switched on).
- **Dead-tail finding:** ~63% of open markets have `yes_ask=0` and ~90% `volume=0` (dominated by auto-generated
  `KXMVESPORTSMULTIGAMEEXTENDED` multi-leg series) — a cross-sectional BBO census should filter on
  activity/liquidity before treating a market as a real quote. Three Ryan design calls left open: raise the cap
  (~85+ calls), add an activity/liquidity discovery filter, or accept a bounded partial snapshot per pass.
- **Run-hygiene lesson:** this run hit a background-subagent race — a delegated `collector-engineer` ran
  concurrently with the lead's direct build and collided on the same files (duplicate test defs, a clobbered
  untracked module, a 3× bloated smoke tape). Resolved to one coherent state + one clean pass, but: never run a
  background collector build concurrently with direct edits to the same files.
- Lesson candidates for a kb-distiller pass: correct L10's “10k+” open-universe figure to >80k; the dead-tail
  activity-filter rule; L90 corroboration for OPEN `/markets`; the multi-hour-gate ({0,6,12,18} vs a single-hour
  daily leg) test-collision rule.
- No strategy claim, no P&L; `kb/strategies/00-index.md` untouched. Files: `collection/universe_sweep.py`,
  `tests/test_universe_sweep.py`, `collection/hourly_pass.py`, `tests/test_hourly_pass.py`,
  `tape/universe_sweep/dt=2026-07-17.jsonl`.

## 2026-07-17 08:27 ET — Q45: systematic settlement-ledger harvester built; 4 legacy caches folded in, 605 labels migrated

- Research-loop run (0h step 0a: main not rewound, PRs #101-#105 all reachable from `origin/main`,
  `kb/00-LOG.md` and newest `tape/*/dt=*` both 2026-07-17; step 0: only open PR is #77, Ryan's own
  stale queue-restock, already flagged by prior runs, left untouched; step 0b: newest stranded
  `tape/hourly-*` branch is `20260717T0403Z`, already swept by PR #102 — nothing new to sweep).
- Delegated to `collector-engineer`; independently re-verified before commit (pytest + invariants
  re-run myself, tape lines spot-checked for tag/result/dedup correctness — not just the agent's
  self-report).
- Built `collection/settlement_ledger.py` (+16 tests) — a read-only, unauthenticated harvester over
  Kalshi's public settled `/markets` endpoint. Writes `tape/settlement_ledger/dt=*.jsonl` keyed by
  `(ticker, close_time, result, settlement_value)`, tagged `broker_truth`. Enforces the L52 binary-only
  filter (drops `result=="scalar"` explicitly, counts the drop, never fakes a yes/no label). Honest
  completeness: a truncated pull (5000-market cap) or a per-market parse error lowers `completeness_ok`;
  a scalar filter or a not-yet-posted `pending` market does not.
- Non-destructively migrated the four ad-hoc `tape/qNN_settlement_cache/settlement.json` probe caches
  (Q26/Q27/Q29/Q30) into the new systematic family: 605 new keys folded in, 955 cross-cache duplicates
  deduped, 25 scalar-result rows dropped. Old cache files untouched.
- Wired into `collection/hourly_pass.py` on its own `SETTLEMENT_LEDGER_UTC_HOUR = 10` (distinct from
  the existing 9/11/12 legs), same `_safe_call` fault-isolation as the weather collectors.
- **Live verification (real committed tape, independently re-checked):** 5,605 lines committed, all
  `price_source_tag: broker_truth`, `result ∈ {yes, no}` only (0 scalar leakage), 0 duplicate keys.
  `pytest`: 1151 passed (1135 prior + 16 new). `invariants --full`: green (only pre-existing non-gating
  L25/L74 advisories).
- **Judgment call flagged for Ryan (not decided here):** the platform's settled universe exceeds the
  5000-market cap, so `completeness_ok=False` is the EXPECTED steady state every time this leg fires —
  not a bug, but it will read as "incomplete" in every `hourly_pass` summary and any downstream gap
  monitor from now on. Whether `hourly_pass`'s overall completeness should fold this leg in as-is, or
  treat a capped-but-honest daily slice as acceptable, is a design call left open.
- **Deviation from the queue's literal wording (documented, not silently forced):** Q45's text named
  `/events?status=settled` as the enumeration route; a live probe found that endpoint returns empty
  nested `markets` platform-wide (the settlement fields live only on `/markets`). The harvester instead
  paginates `/markets?status=settled` directly — same fields, one bounded sweep instead of ~1.7k extra
  per-event calls (an L10-class hazard the literal route would have hit).
- New lesson candidates appended to `kb/lessons/00-lessons.md`: **L90** (Kalshi's settled-market fields
  are `_dollars`/`_fp`-suffixed, not bare — a naive reader silently gets `None` for every value), **L91**
  (use `/markets?status=settled` directly, not `/events` — the latter's nested markets are empty), **L92**
  (closes the shared-helper gap L52 explicitly named — `collection/settlement_ledger.py` is now that home).
- No strategy claim, no P&L verdict, `kb/strategies/00-index.md` untouched. Two-agent verdict rule does
  not apply (collector build, not a verdict-class change). Q46 (full-universe top-of-book sweep) is now
  soft-unblocked on this leg landing (still wants Q44's monitor wired into a live cron — a separate
  Ryan pause point, not crossed here).
- Step 9 (paper sub-pass): `SHADOW_REGISTRY` = `s14_ladder_underwriting` only. Ran `scripts/paper_pass.py`
  — idempotent, 0 newly processed, realized P&L unchanged **+$9.91** (`broker_truth`).

**Next:** Q46 (full-universe top-of-book sweep) is the next TODO item once Q44's monitor gets wired into
a live cron (Ryan pause point); Q36/Q37/Q43 remain time/day-count gated. See `LOOP-QUEUE.md` Q45.

## 2026-07-17 05:xx ET — Q44: tape gap-detector built; live run finds the collector pipe currently degraded

Built `scripts/tape_gap_monitor.py` (+27 offline tests) — the GOAL.md M1a collector
reliability monitor. Read-only over committed tape only (no network in the health path).
Two detectors per family: **STALE** (contiguous silence beyond 2x the family's expected
interval — catches a fully-dead leg) and **UNDER-CAPTURE** (distinct passes in a 24h window
below 0.8x the realized healthy count — catches the case where the day still spans start-to-
end because one of two staggered collectors is alive, but roughly half the passes silently
dropped). The live pipe runs two staggered collectors (VPS cron :23 UTC, cloud trigger :53
UTC), so a healthy hourly family lands ~46-48 passes/day; a max-gap detector alone would miss
one collector dying while the other keeps the day's span intact — this is why both detectors
are needed, not just one.

The false-positive discriminator: `tape/polymarket_pairs/` has been silent since 2026-07-15
for a legitimate reason (World Cup champion market resolved, `status=open` discovery
correctly returns 0 matches, the collector's `if lines:` guard writes no file). Since a
heartbeat can't be retrofitted onto already-committed historical tape, a small explicit
`KNOWN_BENIGN_SILENCES` allowlist (one entry, tied to the exact onset day) suppresses the
*Priority: high* alert for this documented case while still showing it in the health table —
a genuinely different silence, or the same family dying again later, would NOT be suppressed.
The durable fix (each collector's zero-match path emitting its own heartbeat line) is named
in the script's docstring as future work, deliberately not done this milestone.

**All three hard-acceptance checks independently re-verified against real committed tape**
(not just the building agent's self-report): `--now 2026-07-10T00:05Z` flags all 5 hourly
families ALERT for the 2026-07-09 systemic outage (age ~37h, 0 passes); `--now
2026-07-16T00:30Z` flags 4 hourly families `under_capture` 32/48 (ratio 0.67) for the
2026-07-15 interior drop; `polymarket_pairs` at that same `now` reads `alert:false` via the
allowlist.

**Where the queue item's own narrative diverged from reality** (documented rather than
forced): the item assumed several families carry a top-level `completeness_ok` field; in
fact only `sports_pairs`/`crypto_hourly`/`econ_prints` do — `orderbook_depth`,
`weather_books`, both `polymarket_*` pairs families, `weather_actuals`, `perp_tape`, and
`hyperliquid_funding` carry no per-line completeness signal today. The monitor reports
`no_signal` honestly there rather than fabricating `True`.

**Live finding, not fixed this run:** running the monitor at the real current time shows
`sports_pairs`/`crypto_hourly`/`orderbook_depth`/`weather_books`/`polymarket_macro_pairs`
have been running at ~58-62% of expected cadence since 2026-07-15 — the cloud :53 collector
has been mostly silent for roughly two days, not a one-off blip. This is exactly the class of
silent pipe leak Q44 exists to catch, and it caught a real, currently-ongoing one on its first
live run. Flagged for Ryan (diagnosing/restarting the cloud collector trigger is out of this
milestone's scope); noted in this run's phone digest.

Scheduling this monitor into a cron/GitHub Action/cloud trigger is an explicit Ryan pause
point (Q44's own wording) — deliberately left undone. `pytest`: 1135 green (1108 prior + 27
new). `python scripts/invariants.py --full`: green (only pre-existing non-gating L25/L74
advisories). No strategy claim, no registry change — `kb/strategies/00-index.md` untouched.
Step 9: `SHADOW_REGISTRY`=S14 only, `paper_pass.py` idempotent this run (0 newly processed),
realized P&L unchanged +$9.91 (`broker_truth`). See `LOOP-QUEUE.md` Q44 status + this run's
Log-of-runs line.

## 2026-07-17 02:xx ET — Q42 part 2: cross-venue Kalshi-vs-Hyperliquid funding join, verifier-CONFIRMED; stranded-tape sweep (1,798 lines)

Research-loop run. Step 0a passed (no history rewind); step 0b swept `tape/hourly-20260717T0403Z`
(1,798 missing lines: orderbook_depth +966, weather_books +530, sports_pairs +268, perp_tape +17,
polymarket_macro_pairs +15, crypto_hourly +2 — line-set diff, JSON-validated, pure append) as its
own PR (#102), merged first.

Q42 part (1) (the funding-clamp characterization) was DONE; this run took part (2), the
cross-venue join, which the queue note had marked "need live network" — confirmed live from this
sandbox that Hyperliquid's public `/info` API needs no auth and is reachable, so the block didn't
actually apply. Delegated to `edge-prober`, then an independent `verifier` pass (two-agent rule):

- New collector `collection/hyperliquid_funding.py` (+9 offline tests) backfilled Hyperliquid's
  hourly funding for BTC+ETH, 2026-06-03→2026-07-17 (1,063 prints/coin, 0 gaps), archived to
  `tape/hyperliquid_funding/dt=2026-07-17.jsonl`, tagged `broker_truth`.
- New join script `scripts/q42_crossvenue_funding_join.py` (+8 offline tests) compounds
  Hyperliquid's 8 matching hourly prints into Kalshi's actual 8h funding windows — Kalshi
  finalizes at **04:00/12:00/20:00 UTC**, not the naively-assumed 0/8/16 — anchored to each
  print's real `funding_time`, never zero-filling a partial window. 130 windows/asset joined for
  both BTC and ETH, 0 partial.
- Reproduced part 1's BTC zero-fraction exactly (0.6692) as a join-sanity integrity gate.
- **Differential (Hyperliquid 8h-equivalent − Kalshi print), all `broker_truth`:** BTC mean
  +0.238bp / median +0.702bp (p10/p90 −1.076/+1.000bp, n=130); ETH mean +0.777bp / median
  +1.000bp (p10/p90 −0.383/+1.485bp, n=130). The modal window is Kalshi≈0 (clamped) vs
  Hyperliquid≈+1bp — that recurring +1.000bp is Hyperliquid's own funding-rate floor
  (0.0000125/hr × 8), **not** a Kalshi artifact (Kalshi's own nonzero prints run continuous to
  ~9.7bp).
- **Regime-dependent, not a uniform harvest:** the differential flips negative in BTC's
  low-|Hyperliquid| tercile (−0.557bp) and in every Hyperliquid-negative window (BTC −1.162bp
  over 10 windows) — the pair would bleed in those regimes.
- Verifier independently re-ran the join, hand-recomputed the compounding for 3 windows straight
  from raw tape (bypassing the script), reran the full test suite and invariants, and confirmed
  every numbered claim. One non-fatal tone note: the memo's "~+11%/yr gross" framing read a
  little promissory before any cost model exists — softened to make clear it's a reason to build
  part 3, not a result — before commit.

Still **NOT a P&L verdict** (no fee/carry model — that's part 3, which stays BLOCKED(needs-auth)
on Kalshi's authenticated `/margin` fee_tiers endpoint) and **no registry change**. `kb/strategies/
00-index.md` untouched. See `findings/2026-07-17-q42-crossvenue-funding-join.md`,
`scripts/q42_crossvenue_funding_join.py`, `collection/hyperliquid_funding.py`.

Step 9: `SHADOW_REGISTRY`=S14 only, `paper_pass.py` idempotent this run (0 newly processed, 252
deferred-caps, 172 deferred-coverage, 48 already-in-ledger), realized P&L unchanged **+$9.91**
(`broker_truth`). Gates: `pytest -q` → 1108 passed (17 new), `python scripts/invariants.py --full`
green (standing non-gating advisories only). Still 0 proven edges.

## 2026-07-17 00:xx ET — kalshi-edge-hunter nightly: adversarial review of all 4 last-24h numeric findings — ALL REPRODUCE, 0 failures; queue healthy (2 eligible), no idea-gen; no gated probe within 72h

Nightly thinking-seat run. **Step 0a PASS** (`origin/main` HEAD `28c793a` not rewound; merged
PRs #100/#99/#98 are ancestors of `main`; newest `kb/00-LOG.md` entry and newest `tape/*/dt=*`
both 2026-07-17, 0-day gap). **Claim-check:** 1 open PR **#77** (Ryan's queue-restock, 2 days
old, superseded by main's already-merged Q29+ numbering) — under the 5-day escalation mark and
already flagged 2026-07-15, so NOT re-flagged (housekeeping: no re-flag without new info).
Gates green throughout: **996 tests pass**, `invariants --full` green (only the standing
non-gating L25 stray-directory / L74 single-hour-cadence advisories).

**Unit 1 — adversarial review of the last-24h findings. ALL 4 numeric findings independently
reproduced; nothing failed re-check, no GitHub issue opened.** Re-ran each probe from a clean
env and re-derived the load-bearing number:
- **Q42 funding-clamp** (`scripts/q42_funding_clamp_probe.py`): pooled exact-zero fraction
  **0.7616→0.762**, 1,102 exact zeros, 0 nonzeros in `(0,1e-4)`, GENUINE clamp on 12/13,
  KXLINKPERP undecidable — reproduced **exactly**. Tags `broker_truth`. PASS.
- **Q34 / S14 queue fill-sim** (`scripts/s14_queue_fillsim.py`): verdict CI reproduced
  **exactly** — mean **−$0.0453**, 95% CI **[−0.0809, −0.0121]**, n_units=146, fill 27.18%,
  winner-strike 93.15%, admissible (54 opposing / 92 losing). Fee = `MAKER_FEE_RATE` via
  `core.pricing` (flat 1¢ at interior prices, hand-checked). Unit = event-hour (L6). Tags
  `real_ask+real_bid+broker_truth`. The only drift is a secondary descriptive stat — coverage
  denominator 436→**468** — caused by one extra appended day of `orderbook_depth` tape adding
  candidate event-hours; the measurable 146 units and the CI are identical, so the DEAD verdict
  is robust (benign, not a defect). PASS.
- **Q31 / S34 cross-venue arb** (`scripts/q31_cross_venue_arb_probe.py`): mean **−$0.0337**,
  95% CI **[−0.0416, −0.0264]**, 0/63 pairs positive, inadmissible (`no_opposing_unit`),
  movement-conditioned CI [−0.0423, −0.0314] — reproduced (finding was −0.0340 / [−0.0417,
  −0.0268] / 13,158 obs; now 13,640 obs from +1 appended tape-day; verdict fully robust). New
  `polymarket_fee_per_contract` (rate 0.05, un-rounded, 0.0125 @ 50¢) verified against
  `core.pricing`. Unit = matched pair (L6). PASS.
- **Q35 maker-rebate reframe** (candidate-only, no registry change): S13's flip is a mechanical
  constant shift — as-is CI [−0.0002,+0.0004] + (1¢ fee removed + 0.5¢/1.25¢ rebate) =
  [+0.0148,+0.0154] / [+0.0223,+0.0229] — hand-verified from the finding's own table. Every
  flip is explicitly a Milestone-B CANDIDATE, BUILD half BLOCKED(polymarket-collector). PASS.

**Unit 2 — pipeline replenishment: NOT triggered.** Eligible (TODO, unclaimed, unblocked)
research items = **2** (Q44 collector gap-detector + Q45 settlement-ledger harvester, both
GOAL.md Phase-1, offline-buildable now, unclaimed — Q46 is soft-blocked behind them). 2 is not
`< 2`, so no Q21 idea-gen round this run.

**Unit 3 — probe-prep: nothing to build.** No time-gated item unblocks within ~72h, verified by
FILE SHAPE (L25): `tape/weather_books/` = 2 days (Q36 needs ≥7 → ~2026-07-22), `tape/perp_tape/`
= 1 day (Q43 needs ≥7 → ~2026-07-23), Q37 ~2026-08-05.

**Housekeeping.** Stranded-branch backlog: **153** `tape/hourly-*` + **1** `tape/burst-*`
(`tape/burst-20260714T120659Z`). Step-0b check on the burst branch: line-level dedup across all
4 of its 2026-07-14 tape files (crypto_hourly / econ_prints / polymarket_cpi_pairs /
polymarket_macro_pairs) found **0 lines missing from main** — its CPI-burst tape is fully swept,
so the branch is safe to delete (cloud can't; named for VPS/retro deletion). Burst triggers whose
event date has passed → flag for deletion: **cpi-0714, wcsemi1-0714, wcsemi2-0715** (wcfinal-0719
and fomc-0729 still future). No PR >5 days blocked on a Ryan-side action (only #77, 2 days).

Docs-only run (this log entry + queue run-line); no code, no registry change, no findings.
Still **0 proven edges, 0 non-DEAD candidates** — the honest state after the S14 close.

## 2026-07-17 xx:xx ET — Q42 part 1 CONFIRMED: the perp funding zero-majority is a GENUINE ±1bp dead-band clamp, not a rounding artifact

Research loop, Q42 characterization sub-milestone (part 1 of 3). Probe
`scripts/q42_funding_clamp_probe.py` (+ `tests/test_q42_funding_clamp_probe.py`, 15 offline
tests) reads the committed `record_type=="funding_rates"` / `mode=="backfill"` record in
`tape/perp_tape/dt=2026-07-17.jsonl` — **1,447 finalized funding prints** (2026-06-03 → 07-16,
13 contracts, dedup on `(market_ticker, funding_time)`), every number tagged **`broker_truth`**.

**Finding (verifier-CONFIRMED — independent from-scratch recompute off raw tape, then re-ran
the committed script and it matched exactly):** a **GENUINE ±1 basis-point funding dead-band
CLAMP on 12 of 13 contracts.** Pooled exact-zero fraction **0.762**; per-contract zero-fraction
**61.6%–99.1%** (BTC ~66.9%, LINK ~99.1%). Decisive evidence for clamp-not-rounding = a **hard
gap in `(0, 1e-4)`**: pooled 1,102 exact zeros, **0** nonzeros in `(0, 1e-4)`, 186 in
`[1e-4, 1.5e-4)`; the surviving nonzeros are **continuous, not lattice-quantized** (per-contract
smallest nonzero `|rate|` varies, BTC 1.0004e-4 … SUI 1.0560e-4 — a hard floor near ~1e-4, not
a single shared tick), so the zeros are rates forced to exactly 0 inside a ±1bp band, not a
symmetric-rounding bucket straddling zero. **KXLINKPERP is undecidable** (1 nonzero print).

**NOT a P&L verdict — no `kb/strategies/00-index.md` change.** This characterizes the clamp
only; no edge established. Parts (2) Hyperliquid cross-venue funding join and (3) post-promo
perp fee/carry model remain TODO (need live network / auth). Deliverable stays a verdict +
sizing memo, never a green light. Lesson **L89** added (clamp-vs-rounding discriminators must
test the gap relative to the data's own granularity, never an absolute threshold).

Note → `findings/2026-07-17-q42-funding-clamp-characterization.md`. Reproduce:
`python3 scripts/q42_funding_clamp_probe.py`.

## 2026-07-16 21:xx ET — Kalshi crypto PERPS discovered as an unmined venue; collector + funding backfill landed; Q42/Q43 registered

Ryan interactive session ("look at Kalshi perpetual markets on crypto"). Kalshi launched
**CFTC-regulated crypto perpetual futures 2026-05-29** (BTCPERP live 06-03, ETH 06-04; 13
active + 3 pending contracts; ~$170M/24h combined BTC+ETH notional; 8h funding; 2–6x
leverage; zero-fee launch promo). The market-data surface is **public and unauthenticated**
under a separate `/margin` namespace at `external-api.kalshi.com` — full L2, per-contract
live funding estimates, and complete finalized funding history. Nobody else archives this
venue from month one; the L2 and the intra-window funding-estimate path are NOT retrievable
later (the estimate finalizes — and its path dies — at each 8h boundary).

**Recon anomaly (re-runnable via `collection/perp_tape.py` + the committed backfill):**
finalized funding prints are **exactly 0 in 62–99% of 8h windows per contract** (BTC 67%
zero over 130 prints; LINK 99%) — a dead band/clamp — while Hyperliquid's same-window BTC
funding is never 0 (positive 86% of hours, ~+0.8bps/8h vs Kalshi BTC's ~+0.44bps all-in).

Shipped (offline-tested + live-validated): `collection/perp_tape.py` (4 record types:
markets / BTC+ETH L2 / funding_estimate for every active contract / funding_rates
recent+backfill; honest per-section completeness; source tags `real_ask`/`real_bid` for
quotes, `broker_truth` for the venue-computed mark/funding family) wired into
`hourly_pass.py` as a fault-isolated sibling; 11 new offline tests (9 `test_perp_tape.py`
+ 2 wiring) and a fix to the two `hp.main()` monkeypatch tests that would otherwise leak a
real network pass; **1,447-print funding backfill** (2026-06-03→07-16) + day-1 snapshot in
`tape/perp_tape/dt=2026-07-17.jsonl` (17/17 sections ok). Registered **Q42**
(funding-clamp characterization + cross-venue basis, L-mech) and **Q43** (same-venue
binary-vs-perp lead-lag/coherence, L-mech+L-speed — explicitly distinguished from the DEAD
offshore crypto-latency scout: the hedge leg is now same-venue, near-same-benchmark).
Perps trading itself is OUTSIDE the current execution lane (leveraged delta-1, would need
its own client + the full LIVE-AUTH gate); everything here is data + candidate probes.

**Next:** let the forward tape accumulate 7 days → Q42 estimate-path milestone + Q43
lead-lag join; pin the post-promo perp fee schedule (fee_tiers needs auth) before any
carry arithmetic is trusted.

## 2026-07-16 17:xx ET — Q32 prep: sharp-devig-vs-Polymarket join script built + offline-tested; found Q32/Q33 mischaracterized as fully blocked

Research-loop run. Step 0a passed clean (no rewind). Step 0b (own PR #97) swept 1,783 lines
missing from `main`'s `dt=2026-07-16` tape off two stranded `tape/hourly-*` branches
(`orderbook_depth` +967, `sports_pairs` +269, `weather_books` +530, `polymarket_macro_pairs` +15,
`crypto_hourly` +2), JSON-validated, pure append.

Re-examined the last several runs' "0 non-blocked runnable-now items" characterization before
defaulting to another Q21 idea-gen round (the 5th since 2026-07-13, after 4 straight rounds
registering only 1 survivor total). **Q32's own status line explicitly authorizes offline work
now** ("Until BOTH legs exist this is a probe-prep target ... write + offline-test the join
script against fixtures") — this is a genuine TODO milestone, not merely an idle-run fallback,
and prior runs had been folding it into "BLOCKED on Polymarket credentials" without ever doing
the authorized prep. Took this as the run's milestone instead of another idea-gen round.

Delegated to `edge-prober`: built `scripts/q32_sharp_devig_polymarket_probe.py` (+16 offline
tests, no network) — joins `tape/sports_pairs/`'s odds-api de-vig-fair leg (`synthetic`) to an
injectable `--polymarket-tape-dir` Polymarket-sports-real_ask leg (no live tape family exists
yet; schema documented in the script's docstring, modeled on `collection/polymarket_pairs.py`
conventions — bitemporal `captured_at`, a load-bearing `resolution_equivalent` gate that excludes
AND counts non-equivalent/missing-flag pairs rather than assuming). Block-bootstraps by GAME (L6)
through both `bootstrap_verdict_admissible` and `clears_tick_magnitude`. Added the sanctioned
`POLYMARKET_SPORTS_TAKER_RATE = 0.05` (+ `_OPTIMISTIC = 0.03` sensitivity) to `core/pricing.py`
(the one sanctioned fee-coefficient site) — conservative end of the regime note's 0.03–0.05
international-sports range, chosen because the fee is a cost the edge must clear.

Ran the script against real tape today: `tape/sports_pairs/` already has 3 matched-odds games / 9
fair anchors (leg a partially live), `tape/polymarket_sports_pairs/` doesn't exist (leg b) — it
correctly printed "INSUFFICIENT DATA — legs not yet captured" and exited cleanly, no fabricated
verdict. Produces no edge claim, no `findings/` entry, no `kb/strategies/00-index.md` change —
pure prep infrastructure, two-agent rule does not apply.

**Judgment call flagged for Ryan, not acted on:** `collection/polymarket_pairs.py`'s existing
discovery families already read Polymarket's INTERNATIONAL book via plain public CLOB reads with
NO Ryan-side credentials required (only the Polymarket-US/QCEX venue in Q33 needs KYC'd creds) —
a per-game sports moneyline leg could in principle be built on the international book now,
without waiting for Q33's US-credential unblock (still carrying the "not a Polymarket-US fill"
caveat). Re-scoping Q33's charter is Ryan's call, not decided here.

Step 9: `SHADOW_REGISTRY`=S14 only, `paper_pass.py` idempotent (0 newly processed), realized P&L
unchanged **+$9.15** (`broker_truth`). Still 0 proven edges — the bar has not moved. Gates:
`pytest -q` → 1065 passed (1049 prior + 16 new), `python scripts/invariants.py --full` green
(standing non-gating advisories only).

## 2026-07-16 14:xx ET — Q21 idea-gen round: 3 crypto implied-distribution candidates proposed, ALL killed at idea → 0 registered

Research-loop run (research-lead orchestrated). Re-eligibility fired: 0 non-blocked runnable-now
research items (Q19 time-gated on Jul-19 WC-final / Jul-29 FOMC; Q32/Q33/Q35-build/Q35 blocked on
Polymarket credentials; Q36/Q37 time-gated on the freshly-restarted weather tape). Proposed
**3 crypto implied-distribution candidates (S35/S36/S37)** from NEW literature — Bollen & Whaley
2004 (net buying pressure) / Coval & Shumway 2001 (variance risk premium), plus Rabin 2002 /
Terrell 1994 (gambler's fallacy) for S37 — the diversity floor met by that literature. Each was
attacked by an **independent `verifier` that re-ran the committed tape** (`tape/crypto_hourly/`,
`tape/crypto_hourly_historical_spot/`); **all three killed at the idea stage → 0 registered**
(two-agent rule, same honest shape as 2026-07-15).

Kills: **S35** — near-money is overround-RICH not cheap (realized win-rate below ask *before*
fees; net-buying-pressure thesis REVERSED = S1-on-crypto). **S36** — the skew is one-sided
(upside rich, downside fair) and lives inside the spread; the overround-neutral taker pair nets
−$0.0204 with a CI straddling zero (maker-only residual, S24/L58). **S37** — no fillable ATM
directional instrument on the range-ladder (a single bracket is a pin bet, not a direction bet) +
~189% strip overround + data-thin, structural like S10.

Outputs: new distillation `kb/quant-finance/net-buying-pressure-implied-distribution.md` (records
the papers AND their venue refutation so a future round doesn't re-propose them); lessons **L87**
(crypto near-money overround-rich, thesis reversed) and **L88** (no fillable ATM directional
instrument on crypto range-ladders), both ledger-only. S35/S36/S37 labels consumed for
provenance; next free S-number **S38**. No S-rows, no status flip, no new Q-item (no survivors to
queue) — Q21 stays STANDING. **Still 0 proven edges — the bar has not moved.** See
`findings/2026-07-16-q21-idea-gen-round.md`.

## 2026-07-16 11:xx ET — Q38: weather forecast + actuals collector legs wired into hourly_pass (data only)

Research-loop run. Step 0b (own PR #94): scanned all 149 remote `tape/hourly-*`/`tape/burst-*`
branches by line-set diff against current `main` — 147 already fully reconciled (undeleted
per the 2026-07-10 retro amendment that stopped attempting a branch-delete that reliably fails
from a cloud session), two carried genuine gaps totaling 291 lines (`tape/hourly-202607161256Z`
289 lines across crypto_hourly/polymarket_macro_pairs/sports_pairs; an older un-swept backlog
branch `tape/hourly-20260715T1901Z`, 2 lines in polymarket_pairs dt=2026-07-15). All JSON-
validated, 0 invalid/reordered/duplicated.

Milestone: **Q38** — Q37's future EMOS weather-signal probe needs a forecast tape and real
settlement-truth actuals, neither collected on a recurring cadence. Delegated to
`collector-engineer`:

- **(a) Forecast leg:** `collection/forecast_collector.py` (existing multi-model Open-Meteo
  one-shot, tag `synthetic`, `MODELS` untouched — Hard Rule #1's `ncep_gefs025` exclusion
  unaffected) is now wired into `collection/hourly_pass.py`, firing once per UTC day at a new
  `FORECAST_COLLECTOR_UTC_HOUR=11` gate (the laptop-sleep-cadence blocker that kept this a
  manual one-shot is moot on always-on cloud/VPS collection).
- **(b) Actuals leg (new):** `collection/weather_actuals.py` fires once/day at
  `WEATHER_ACTUALS_UTC_HOUR=12` (an hour after the forecast leg, so late-posting NWS CLI reports
  for the just-closed day are more likely available). Reuses `validation/v1_actuals.py`'s
  `fetch_cli`/`fetch_metar`/`reconcile_day`/`TOL_F` verbatim — one definition of "do the sources
  agree" — over the 20 verified `config/station_candidates.yaml` cities (KNYC/Central Park
  already among them). A high/low value is tagged `broker_truth` ONLY when CLI+METAR both
  present and agree within tolerance and the day isn't `dirty`; otherwise `unverifiable` — a
  tape-only honest-absence-of-confirmation tag, never a DB `price_source_tag`, same posture as
  `real_bid`/L24, never silently upgraded. Joins to that day's SETTLED Kalshi KXHIGH*/KXLOWT*
  results via the event ticker's own structural `<SERIES>-<YYMMMDD>` weather-day token (not
  `close_time`, which lands in the next UTC day for many US settlement instants — L16
  discipline), bounded settled-market scan with an honest `truncated` flag (L10).

28 new offline unit tests (17 in `tests/test_weather_actuals.py`, 11 added to
`tests/test_hourly_pass.py`). **Live validation (both legs, real endpoints) was a genuine
end-to-end structural-join confirmation, not just a wiring smoke test:** `weather_actuals
--limit 2` captured 2/2 cities, 0 dropped, `broker_truth` high/low 2/2, settled joined 2/2 —
and the cross-confirmed CLI/METAR actuals matched Kalshi's own settled `expiration_value`
EXACTLY (Atlanta high/low 90.0°F/74.0°F == `KXHIGHTATL`/`KXLOWTATL` settled 90.00/74.00; Austin
80.0°F/72.0°F likewise). `forecast_collector --limit 2` persisted 8/8 (city, model) lines, tag
`synthetic`, to its existing gitignored `data/forecast_tape/` store (location unchanged).

DATA ONLY per this item's own scope guard — no strategy claim, `kb/strategies/00-index.md`
untouched, still **0 proven edges**. Two judgment calls flagged for Ryan rather than decided
unilaterally: (1) the forecast tape stays in `data/forecast_tape/` (gitignored) rather than
being relocated into committed `tape/`; (2) the actuals leg's `completeness_ok` is coupled to
Kalshi settled-fetch health (mirrors `weather_books`' `series_errors` posture) — could be
decoupled if preferred. New lesson candidates flagged for the kb-distiller: structural
settled-event date-token joins reproduce broker truth exactly (extends L16); `unverifiable` as
a fourth, tape-only honest verdict tag (extends the `real_bid`/L24 family); daily-cadence hour
placement matters when a downstream source posts late (a scheduling-judgment caution, sibling
to L15).

Step 9: `SHADOW_REGISTRY`=S14 only, `paper_pass.py` idempotent this run (0 newly processed,
261 deferred-caps, 146 deferred-coverage, 39 already-in-ledger), realized P&L unchanged
**+$9.15** (`broker_truth`).

Gates: `pytest -q` → **1049 passed** (1021 prior + 28 new), `python scripts/invariants.py
--full` → green (only the standing non-gating advisories: stranded-branch count, tape-shape
directories L25, daily-cadence gaps L74).

**Next:** Q37 (summer maker-side re-test) stays gated until ~21 summer contract-days of
`tape/weather_books/` accumulate (~2026-08-05); Q36 (KXTEMPNYCH microstructure) gated until
~7 days of hourly weather_books coverage (~2026-07-22). Both now have a forecast+actuals tape
accumulating in parallel so their signal layer has real data by the time their gates open.

---

## 2026-07-16 12:xx ET — Q19 PER-EVENT: WC-semifinal-2 burst lead-lag — descriptive, no registry change

First WC-round-schema burst-window cut. Built `--burst-window` mode for
`scripts/s9_leadlag_probe.py` (the WC-round (`polymarket_pairs.v1`) analog of
`s17_leadlag_probe.py`'s Fed-schema burst mode — per-ticker signed lead-lag, a
leave-one-out that drops the single lag-pair actually driving each direction's
correlation (not just the largest raw price move, which can pick the wrong step), and a
fillable cross-venue dislocation scan) with offline tests, and ran it over the
WC-semifinal-2 burst tape (`tape/polymarket_pairs/dt=2026-07-15.jsonl`, 30 captures @
median 120s, 20:10Z-22:30Z, 2 tickers). **Fee-corrected per Q31's 2026-07-15 regime
change**: both crossing legs charged their venue's real taker fee (Kalshi 0.07,
Polymarket US 0.05 via `core.pricing.polymarket_fee_per_contract`) — a
`--poly-fee-rate 0.0` sensitivity shows 2 of the fee-free view's 4 "hits" are float-dust
zeros the real fee erases, confirming the correction is load-bearing, not cosmetic.

**Lead-lag:** both tickers nominally show Polymarket leading Kalshi (rho_poly
0.269/0.290), but the corrected leave-one-out collapses both to ~0.05 once the single
20:15:28Z first-goal lag-pair is dropped — a one-tick artifact, the same shape as the
CPI leg's July-bucket finding (L57). **Dislocations:** only 2 fee-clearing captures / 2
episodes, both at the exact same 20:15:28Z instant (net_edge +$0.1291 / +$0.1832), both
single-capture (0s duration) — large but short, not the large-AND-durable shape a real
edge needs. No PROVISIONAL tradeable claim was raised, so the two-agent verifier rule
did not trigger. **Honest gap:** WC-semifinal-1 (Jul 14) never produced burst tape — the
trigger fired (`last_fired_at` 2026-07-14T20:10:31Z) but nothing was ever committed;
flagged for Ryan, not silently dropped. `kb/strategies/00-index.md` S17 unchanged
(`data-collecting`) — kill/live decision stays deferred to the FOMC event (Jul 29). Still
**0 proven edges**. See `findings/2026-07-16-s17-burst-wcsemi2-q19.md`.

## 2026-07-16 09:xx ET — Q35 Milestone A: maker-rebate reframe — 2/5 flip to fee-line CI-positive candidates, no registry change

Read-only re-derivation of the 5 fee-killed maker strategies (S13/S19/S21/S23/S29) swapping
Kalshi's flat ~1¢ maker fee for a hypothetical Polymarket maker rebate (+0.5¢ conservative /
+1.25¢ US-venue). `scripts/q35_maker_rebate_reframe.py` (+10 offline tests) reused each
strategy's own simulate functions over already-committed tape/cache — no network, no new
fetch. **S13 flips both rebate scenarios** (mechanical: bid=fair−1¢ by construction, the fee
ate almost exactly the fixed 1¢ pre-fee edge). **S29 flips only at +1.25¢**, but only on the
two-sided-book entry cut (n=119 games) — the raw earliest-entry population's headline is an
artifact its own finding disowns. **S19/S21 stay dead** on data adequacy (2 event-hours / 0
fills — no fee line can manufacture units). **S23 stays dead**, having lost by roughly double
the largest rebate swing.

Two-agent trail had a real catch: the first cut reported "1/5 flips (S13 only)" because
`collect_s29` fed the disowned raw population into the reframe instead of the two-sided-book
cut the S29 finding's DEAD verdict actually rests on. An independent verifier REFUTED that
cut, built its own check script over the correct population, and got a CI that clears the
tick gate at +1.25¢ — directly contradicting the headline. Fixed (`filter_two_sided_fills`),
re-verified by a second independent pass: numbers reproduce to 4 decimal places. Every flip
remains a Milestone-B CANDIDATE only — portability, resolution-basis parity, and the full
real-ask/real-fill bar on an actual Polymarket venue are all still owed before any of this is
a proven edge. `kb/strategies/00-index.md` unchanged (Q35 Milestone A never flips a
registry entry by spec). Still **0 proven edges**. See
`findings/2026-07-16-q35-maker-rebate-reframe-milestone-a.md`.

## 2026-07-16 06:xx ET — Q34: S14 queue-aware fill-realism revalidation — verdict DEAD, closes the repo's last non-DEAD candidate

Research-loop run. Step 0a passed cleanly (HEAD matched `origin/main` post-fetch, no rewind;
0-day `kb/00-LOG.md`↔tape gap). Claim-check: only open PR is #77 (Ryan's stale queue-restock,
unchanged, left for Ryan). Step 0b swept `tape/hourly-Z`, a literal-named fallback branch
(01:06:37Z, never reconciled) carrying 1,284 missing lines across 4 families — landed and
merged separately as PR #89 before the milestone.

**Milestone Q34** (topmost eligible, flagged HIGHEST PRIORITY 2026-07-15): S14 ("ladder
overround underwriting" — rest maker short-YES offers across a whole crypto-hourly MECE strike
ladder, collect premium, pay $1 if the winner was among your filled strikes) was the project's
ONLY non-DEAD candidate, but its Q13 first-cut used a candlestick-through fill proxy (L39) —
the exact bias that already killed S13/S19/S21/S23. This run built the mandated queue-aware
revalidation.

`scripts/s14_queue_fillsim.py` replaces the candle proxy with a price-time-priority queue model
over `tape/orderbook_depth/` `no_bids` (executed volume read offline from the already-committed
`tape/s14_ladder_fillsim/` candle cache — no re-fetch, no network). Delegated through the full
two-agent pipeline: `research-lead` → `edge-prober` (build + first run) → `verifier`
(independent re-run, seed=42, exact reproduction) → **CONFIRMED**.

**Result: the queue-aware model FALSIFIES the candle-proxy's headline.** Q13's proxy found
block-boot-by-event-hour mean +$0.0925, CI [+0.063,+0.123], n=300. The queue-aware re-run finds
mean **−$0.0453, 95% CI [−0.0809,−0.0121]** (fully below zero), n=146 event-hours,
`bootstrap_verdict_admissible` PASS (54 opposing / 92 losing clusters — genuinely mixed, not an
L41 resampling artifact) but `clears_tick_magnitude` FAIL. Mechanism: once queue position gates
which legs actually fill, the near-money winner strike still fills 93.15% of the time and costs
the full $1, while the collectable premium (mean +$0.886) falls short of covering the mean
+$0.9315 payout. Overall fill rate 27.18% (582/2141 priced-relevant members) is far ABOVE the
S19 0.45% floor, so this dies on the EDGE, not on data adequacy (L53) — the queue-aware
mechanics are real and measurable, they just don't clear.

The winner-payout leg (the catastrophic $1 loss) stayed fully in the P&L for every measurable
event-hour, never conditioned away — 290 event-hours were dropped on winner-leg measurability
alone (exogenous to settlement, capped by the L9 depth-tape-starts-07-07-vs-crypto-07-03
overlap), and verifier confirmed the drop was conservative: counting those as payout=0 instead
still gives a negative mean (−$0.0152).

`kb/strategies/00-index.md`: **S14 flips `data-collecting` → `dead ✗`.** This closes the
repo's last non-DEAD candidate — the project still has **0 proven edges** after 20+ tested
strategies. Two new lessons: **L85** (a candle-through fill proxy is presumptively
verdict-invalidating for any P&L that nets a small edge against two large legs — the
S13/S19/S21/S23/S14 purge of this exact bias is now complete) and **L86** (the winner /
catastrophic-leg measurability asymmetry — drop the unit on that leg's measurability, never
zero the loss, and verify the drop moves the result the conservative direction).

Flagged, not acted on: `execution/strategy_api.SHADOW_REGISTRY` still runs the OLD candle-proxy
`s14_ladder_underwriting` paper strategy post-kill. Harmless (paper tier, no capital) but no
longer decision-useful; deregistering it is a judgment call left for Ryan or a future run
rather than made unilaterally here.

Step 9: `SHADOW_REGISTRY`=S14 only, `paper_pass.py` idempotent this run (0 newly processed),
realized P&L unchanged +$9.15 (`broker_truth`). Gates: `pytest -q` → 996 passed,
`invariants --full` → green (only standing non-gating L25/L74 advisories). See
`findings/2026-07-16-q34-s14-queue-fillsim-verdict.md`.

---

## 2026-07-16 04:xx ET — kalshi-edge-hunter nightly: adversarial review of 3 last-24h verdicts (all PASS), queue healthy (no idea-gen), no sub-72h prep

Nightly thinking-seat run. Step 0a **PASS** — `origin/main` HEAD `5c4819d` not rewound: the
`git fetch` "forced update" is the documented squash-merge graft-boundary artifact (PRs
#85/#86/#87), resolved via `git checkout -B main origin/main`; `kb/00-LOG.md` newest entry and
newest `tape/*/dt=*` content both 2026-07-16, 0-day gap. Claim-check: 1 open PR **#77** (Ryan's
stale queue-restock, ~1.5 days old, its Q29-Q32 numbering already superseded by the real Q31-Q38
merged separately) — under the 5-day stuck-PR threshold and already flagged by six prior runs, so
**not re-flagged**, left for Ryan.

**Unit 1 — adversarial review of the 3 verdict-class findings from the last 24h, one load-bearing
number each, ALL PASS → no issue opened:**
- **Q31/S34 cross-venue two-legged arb (2026-07-16, DEAD)** — the freshest verdict, and it
  introduced brand-new pricing code, so reviewed deepest. (a) **Provenance:** read a raw
  `tape/polymarket_pairs/` line directly — both the Kalshi leg (`no_ask`, `price_source_tag:
  real_ask`) and the Polymarket leg (`best_ask`, `price_source_tag: real_ask`) carry `real_ask`,
  no synthetic/mid leg. (b) **Fee rate via `core.pricing`:** `polymarket_fee_per_contract` =
  `rate·p·(1−p)` with `POLYMARKET_US_TAKER_RATE = 0.05`, no round-up-to-cent — internally
  consistent with its own cited $1.25/100-contract cap (0.05·0.5·0.5 = 0.0125), and
  **independently confirmed against the live published Polymarket US schedule** (uniform taker
  ≈0.05, `fee = C·rate·p·(1−p)`, cap ≈$1.25/100 at 50¢ — the cap only reconciles at rate=0.05).
  Kalshi leg uses the sanctioned ceil-to-cent `fee_per_contract` at 0.07. (c) **Bootstrap unit:**
  by matched pair (63 clusters), not the 13,158 raw snapshots — correct L6 clustering via
  `core.bootstrap.block_bootstrap` → `bootstrap_verdict_admissible` + `clears_tick_magnitude`.
  Crucially the verdict is **structurally fee-independent** — the finding's own fee-free-Polymarket
  sensitivity is still negative (CI [−0.0344,−0.0214]) and gross (pre-fee) parity is violated
  (cost ≥ $1) in 84.9% of snapshots — so no fee-rate error could flip DEAD→alive. **PASS.**
- **S33 weather ladder-coherence (2026-07-15, DEAD)** — load-bearing number = the 6-leg fee floor.
  Confirmed `scripts/probe_ladder_coherence.py` sums `core.pricing.fee_per_contract` per leg
  (never hand-rolled, L18) at rate 0.07; reports `reports/ladder_coherence_summary.json` /
  `_opps.jsonl` present and committed; 0 opportunities ≥10 contracts AND ≥60s. **PASS.**
- **Q30/S29 draw-aversion maker (2026-07-15, DEAD-by-fillability)** — load-bearing number =
  breakeven. Re-derived: mean fill $0.1799 + $0.01 maker fee = **0.1899 = 18.99%**, matching the
  finding exactly; draw rate 28.03% > breakeven so the spec population looks positive, and the kill
  is fillability (verifier-confirmed at creation, edge carried by unfillable nickel bids). **PASS.**

**Unit 2 — pipeline replenishment: NOT TRIGGERED.** The queue is no longer drained: Ryan's
2026-07-15 regime-change + weather-revival session restocked Q31-Q38. Eligible (TODO, unclaimed,
unblocked) items now: **Q34** (S14 queue-model fill-realism revalidation — flagged highest-priority,
immediately runnable on existing tape, gates Q35's rebate multiplier), **Q35-analysis half**
(maker-rebate reframe, read-only, no Polymarket data needed), and **Q38** (weather forecast/actuals
collector milestones, offline-testable now) — **≥2 eligible**, so no Q21 idea-gen round this run.
(Gated/blocked and correctly skipped: Q32 needs both ODDS_API_KEY + a Polymarket sports leg; Q33
BLOCKED on Ryan-side Polymarket credentials; Q36 gated on ≥7 days weather_books coverage; Q37 gated
on ≥21 summer days.)

**Unit 3 — probe-prep: NO-OP.** No time-gated item unblocks within ~72h. Nearest gate is Q36
(KXTEMPNYCH microstructure), gated on ≥7 days of `tape/weather_books/` — collector landed
2026-07-15, only day-1 tape exists (`20260716T013115Z`), so the gate opens ~2026-07-22 (≈6 days
out, outside the 72h window) and, per L25, the 7-day tape shape isn't there yet to offline-test
against. Noted as the next prep target for a future run.

**Housekeeping.** Burst branch `tape/burst-20260714T120659Z` (CPI cpi-jun26, 2026-07-14) verified
**fully reconciled onto main** (line-level diff: 0 lines missing from main across every tape file)
→ safe delete candidate. Burst triggers whose event date has passed → flag `kalshi-burst-cpi-0714`,
`kalshi-burst-wcsemi1-0714`, and **newly** `kalshi-burst-wcsemi2-0715` (event was 2026-07-15) for
deletion; `wcfinal-0719` and `fomc-0729` still future. Remote branch count: **146
`tape/hourly-*` + 1 `tape/burst-*`** (the hourly branches keep accumulating because the GitHub App
lacks branch-delete scope — a standing Ryan-side cleanup item, not re-escalated here).

**Step 9 (paper sub-pass):** `execution/strategy_api.SHADOW_REGISTRY` = S14 only; no new
paper-relevant tape since the last pass → `paper_pass.py` idempotent, realized P&L unchanged
**+$9.15** (`broker_truth`, 0 open / all settled). Still **0 proven edges** — the bar has not moved.

Gates: `pytest -q` → 983 passed; `python scripts/invariants.py --full` → green (only the standing
non-gating L25/L74 tape-cadence advisories). Docs-only diff → self-merge.

---

## 2026-07-16 03:xx ET — Q31/S34 cross-venue two-legged arb: DEAD, verifier-CONFIRMED, queue no longer drained

Six consecutive idle runs had found Q0-Q30 fully DONE/BLOCKED/RESERVED. This run found the queue
restocked: Q31-Q38 landed on `main` (Ryan's 2026-07-15 "regime change" interactive session +
weather revival) after the last idle run's PR merged. Picked the topmost eligible item, Q31: now
that Ryan can trade both Kalshi and Polymarket, is there a genuine two-legged arb (buy YES on the
cheaper venue + buy NO on the dearer venue, locking $1 regardless of outcome, net of both venues'
fees)? S9's prior (2026-07-04) found the steady-state price gap tight (mean +0.20¢, ±3¢) — the
queue's own honest expectation was "probably DEAD."

Built `scripts/q31_cross_venue_arb_probe.py` + 17 offline tests, and a new
`core.pricing.polymarket_fee_per_contract` / `POLYMARKET_US_TAKER_RATE = 0.05` (Polymarket Fee
Structure V2, US/QCX taker rate, cited in the module comment — same `rate·p·(1−p)` shape as
Kalshi's fee but no round-up-to-cent).

Discovered a real, previously-unstated tape-coverage gap: `collection/polymarket_pairs.py` /
`collection/polymarket_macro_pairs.py` only ever fetch the Polymarket "Yes" outcome token's book
(`outcomes.index("Yes")`) — there is no captured Polymarket NO-token ask anywhere in the tape. So
the two-legged arb is only fully computable, with real resting asks on both legs, in one
direction: buy Polymarket YES + buy Kalshi NO (Kalshi always quotes both sides). Deriving a
Polymarket NO ask as `1 − best_bid` would have been a mid/bid-derived synthetic price — forbidden
by the milestone's own gate — so the mirror direction was left untested and the gap stated
honestly rather than worked around.

Over 13,158 resolution-equivalent snapshots / 63 matched pairs (48 WC-round + 15 Fed-decision;
the CPI family excluded outright — its Kalshi leg is `synthetic`), block-bootstrap-by-pair: mean
net edge **−$0.0340, 95% CI [−0.0417, −0.0268]** ⊄ >0, 0/63 pairs positive-mean, inadmissible
(`no_opposing_unit`), fails `clears_tick_magnitude`. Robust to a fee-free-Polymarket sensitivity
(CI [−0.0344,−0.0214]) and to the L32 frozen/movement-conditioned dual cut (movement CI
[−0.0423,−0.0316]). Fillable-snapshot frequency only 2.0%, and persistence collapses from 84.2%
(inclusive) to 34.9% once conditioned on the book actually moving — apparent persistence is
mostly a frozen-quote artifact (75.9% of consecutive pairs are frozen), not a re-offered arb.

**Verdict: DEAD.** Registered **S34 — dead ✗** in `kb/strategies/00-index.md`. Confirms the S9
parity prior: once both legs cost a fee, the near-parity price gap leaves nothing.

Two-agent verdict rule: `verifier`/`edge-prober`/`research-lead` agent types were unexpectedly
unavailable this session (a mid-run tool-availability change), so verification used a
`general-purpose` agent under an explicit adversarial-verifier mandate instead. It independently
re-ran both gates, re-derived every headline number from raw tape (bypassing the probe script),
bucketed by ticker and by price band to check for a masked positive subpopulation (found none —
all 63 tickers and all 11 bands negative-mean), and confirmed the data-coverage gap by reading
the collector source directly. **CONFIRMED** — safe to commit as two-agent-verified.

Step 9: `SHADOW_REGISTRY` = S14 only; `paper_pass.py` ran idempotent this pass (0 newly
processed — 261 deferred-caps, 132 deferred-coverage, 39 already-in-ledger); realized P&L
unchanged **+$9.15** (`broker_truth`). No new paper ledger lines to commit.

Gates: `pytest` → 983 passed. `python scripts/invariants.py --full` → green (only the standing
non-gating L25/L74 tape-cadence advisories). Still 0 proven edges. See
`findings/2026-07-16-q31-cross-venue-arb-verdict.md`, `LOOP-QUEUE.md` Q31, `kb/strategies/00-index.md` S34.

**Next:** Q34 (S14 queue-model fill-realism revalidation — flagged in the queue as highest
priority of the new items, gates Q35's rebate multiplier) is now the topmost remaining eligible
milestone.

---

## 2026-07-15 22:xx ET — Weather revival (Ryan interactive): family reopened, S33 ladder-coherence DEAD, weather tape restarted

Ryan-directed serious re-look at weather. A four-agent mining pass over the prior repos
produced `findings/2026-07-15-weather-revival-dossier.md` — core reframe: weather was never
killed for lack of signal, every death (pt1, S1, S5) was **execution economics** (9.84¢
overround + taker fee); the untested cells are **summer regime × maker execution × EMOS
signal** plus the brand-new hourly `KXTEMPNYCH` surface. Queue restocked **Q36** (KXTEMPNYCH
settlement-basis + microstructure, the VPS-latency thesis), **Q37** (summer maker-side S1/S5
re-test, W-A), **Q38** (forecast + actuals tape legs). Weather family status is now **revival
in progress per Q36–Q38; ladder-coherence dead** — the 2026-06-18 "weather DEAD, pivot"
verdict stands only for the daily-ladder taker angle.

**New verdict — S33 registered dead ✗** (`kb/strategies/00-index.md`). The dossier's W-D
candidate (kalshi.1's old H1: intra-ladder Σ leg-ask < $1 coherence arb) TESTED-DEAD on the
recovered 24GB spring tape (`scripts/probe_ladder_coherence.py` + `_inspect.py`,
`tests/test_probe_ladder_coherence.py`, `reports/ladder_coherence_opps.jsonl` +
`ladder_coherence_summary.json`): 33.5M joint ladder-seconds, 352 MECE 6-bracket ladders; raw
Σ<$1 in 1.685% of seconds but only 0.0316% net>0 after the 6-leg fee floor; depth×duration
anti-correlated — **0 opportunities ≥10 contracts AND ≥60s** (also 0 at ≥5/≥60s, ≥20/≥10s),
all 17 executable-by-snapshot runs ≤1.0s wall-clock. Proven mechanism: intra-ladder
forward-fill asynchrony (losing legs at the 1¢ floor while the winner leg's ask is stale one
beat — `KXHIGHPHIL-26APR22-B66.5` joint 0.38 vs the leg's own 0.52). Joins S1/S5 in the
execution-economics graveyard.

**Collector:** `collection/weather_books.py` wired into `hourly_pass` (530/530 books first
pass; 67 daily + 8 hourly series discovered, 27 daily NOT in `config/cities.yaml`) — first
weather tape since the 2026-07-03 teardown.

**Lessons added L76–L84:** L76 (wall-clock-seconds duration gate, not snapshot count — the
one still-open UNENFORCED escalation candidate), L77 (forward-fill joint state manufactures
phantom arbs — intra-ladder L8), L78 (net>0-prefiltered bootstrap is inadmissible by
construction, L41; score depth×duration for a structural arb), L79 (recovered-replica
`raw_json` carries top-of-book — reusable offline source), L80 (weather ladders empty-collapse
losing legs to the 1¢ floor — weather analogue of L26/L65). Collector lessons: L81
(own-discovery sub-pass makes existing hourly_pass tests hit the network — stub every call
site), L82 (weather ticker taxonomy drift ≥3 prefixes/city; seed list is a floor — sweep every
pass; **test**-enforced), L83 (`orderbook_fp` string-dollars is live, integer-cents legacy —
handle both; **test**-enforced), L84 (per-(entity,day) dedup by reading the day's tape is
concurrency-safe; **test**-enforced). **No new enforcement built this pass** per the launching
agent's directive — L76 stays UNENFORCED with an honest candidate noted; the collector lessons
L82/L83/L84 are already pinned by the collector-build session's own
`tests/test_weather_books.py`, cited not authored here. Still **0 proven edges**.

---

## 2026-07-15 20:xx ET — Idle run: L74 daily-cadence gap advisory converted UNENFORCED→invariant (non-gating)

Research-loop run. Step 0a: shallow clone (`--depth 50`) made every recent merged-PR head
SHA look like a non-ancestor of `origin/main` — the same graft-boundary/squash-merge artifact
PRs #85/#86 already documented, not a rewrite. `git fetch --unshallow` then confirmed via
content presence (not head-SHA ancestry, since these PRs are squash-merged) that #78/#79/#80/
#81/#83/#84/#85/#86's payloads (`core/income_legs.py`, `core/depth.py`, `core/reversal.py`,
both findings docs) are all present on `origin/main` HEAD `f07beb9`, with matching `(#NN)`
commit messages. `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` content both 2026-07-15
— 0/1-day gap. Not rewound. Claim-check: 1 open PR **#77** (Ryan's own queue-restock session,
unchanged since PR #79 first flagged it 07-15T03:37Z — same head sha, same Q29-Q32 numbering
collision with slots already merged) — not re-flagged, left for Ryan.

**Queue state unchanged: every numbered item Q0-Q30 is still DONE, BLOCKED(data-adequacy), or
RESERVED — no TODO/IN-PROGRESS milestone was eligible.** Sixth consecutive idle run.

**Idle-run policy order (a):** L74 (this week's own econ/CPI/anomaly daily-cadence-gap
data-quality finding) had a genuinely open, code-shaped candidate its own row named: "a
`dt=<date>` day-gap check for daily-cadence families in `scripts/invariants.py` (advisory,
not gating — same class as the L25 tape-dir-shape check)". Built it: `DAILY_CADENCE_FAMILIES`
(`anomalies`, `econ_prints`, `polymarket_cpi_pairs` — the 3 families `collection/hourly_pass.py`
gates to the same single `now.hour == 9` UTC window) + `_daily_family_gap_issues()` +
`daily_family_gap_warning()`, wired into `invariants.py --full`'s stderr-only advisory output
alongside the existing L17/L25 warnings (same offline-safe, per-family exception-swallowed,
non-gating pattern as `tape_dir_shape_warning`). Live-validated against the real committed
tree: correctly flags all 6 days L74 first documented (`anomalies`/`econ_prints`/
`polymarket_cpi_pairs` × `dt=2026-07-09`/`dt=2026-07-10`), 0 false positives elsewhere. New
lesson **L75** (supersedes L74's enforcement column only — lesson content unchanged). Still
**0 proven edges**.

**Step 0b sweep:** all remote `tape/hourly-*`/`tape/burst-*` branches top out at
`tape/hourly-20260715T1901Z`, already swept and reconciled by PR #86 — nothing new this run.

**Step 9 (paper sub-pass):** `SHADOW_REGISTRY` = S14 only. `scripts/paper_pass.py` processed
10 newly-eligible fills (261 deferred-caps, 126 deferred-coverage, 29 already-in-ledger):
`daily_summary()` now 0 open, 291 settled, realized P&L **+$9.15** (`broker_truth`, up from
+$5.77). Ledger line appended to `paper/ledger/dt=2026-07-16.jsonl`.

Gates: `pytest` → 940 passed (931 prior + 9 new `test_invariants.py` cases). `python
scripts/invariants.py --full` → green (only standing non-gating L17/L25/L74-superseded
advisories; the new L74/L75 advisory itself fired live, correctly, non-gating).

## 2026-07-15 17:xx ET — Idle run: queue still drained, econ/CPI/anomaly daily-cadence gap data-quality deep-dive (L74)

Research-loop run. Step 0a: local sandbox `main` ref was badly stale (pointed at an early
2026-07-03 commit from a prior detached-HEAD state) — `git fetch --unshallow origin` +
`git merge --ff-only origin/main` fixed it; the `78284fe`-not-an-ancestor false alarm this
produced before unshallowing was confirmed to be the same `--depth`-graft-boundary artifact
PR #85 already documented, not a rewrite (post-unshallow ancestry check passed). Confirmed
`origin/main` HEAD `c20563a` not rewound: last 8 merged PRs (#78–#85) all present as ancestors;
newest `kb/00-LOG.md` entry and newest `tape/*/dt=*` content both 2026-07-15, 0-day gap.
Claim-check: 1 open PR **#77** (Ryan's own queue-restock session, unchanged since PR #79
first flagged it — same head sha, same Q29-Q32 numbering collision with slots #79/#81/#83/#84/#85
already merged) — not re-flagged, left for Ryan.

**Queue state unchanged: every numbered item Q0-Q30 is still DONE, BLOCKED(data-adequacy), or
RESERVED — no TODO/IN-PROGRESS milestone was eligible.** Fifth consecutive idle run. Q21
idea-gen stays ROUND COMPLETE (0-survivor twice running per PR #79/#80) — not re-run a third
time from this seat.

**Idle-run policy order (a) exhausted:** re-checked every standing `UNENFORCED` row in
`kb/lessons/00-lessons.md`. L22/L25/L27/L28/L32/L45/L47 confirmed already resolved in the
current tree (verified L45 specifically this run: `core/timeutil.parse_crypto_hour_token_close_utc`
does implement the ET-localized crypto-hour parser L45/L49 called for). L51/L64/L65/L66/L68/L69
remain genuinely per-design methodology notes, not core-write candidates (their own rows say
so). No new core-write candidate exists — order (a) is drained for now.

**Order (b) NO-OP** (same as the last 2 runs): FOMC Jul 29's `--burst-window` probe is already
built; WC final Jul 19 is pure burst-tape capture, no probe to prep; S14's depth-day gate is
still weeks off.

**Order (c):** picked a data-quality deep-dive on `tape/econ_prints/` (+ its `polymarket_cpi_pairs`/
`anomalies` daily-cadence siblings) ahead of the Jul-29 FOMC window. Read every `.jsonl` file
directly (cross-checked against `ls` to rule out an L25-style masked directory). Findings: (1)
completeness/drift are clean — 4,774/4,774 nested `completeness_ok=true`, 0 settlement-value
drift across 8 repeated-capture event tickers; (2) coverage has a real, previously-unstated
**2-day** gap (2026-07-09 AND 2026-07-10) for `econ_prints`/`polymarket_cpi_pairs`/`anomalies` —
double the 1-day gap the hourly families (`sports_pairs`/`crypto_hourly`/`polymarket_macro_pairs`)
suffered in the same 2026-07-08 main-reset incident, because all three share the SAME single
`ts.hour == 9` collector gate (`collection/hourly_pass.py`) with no retry/backfill; (3) this is a
standing structural exposure independent of that one incident — one bad hour costs a full day of
CPI/GDP/payrolls/Fed-nowcast/anomaly-sweep tape with nothing else to catch it. No fix built
(read-only per the idle-run policy; `scripts/invariants.py` has no missing-calendar-day check for
a daily family, only a shape check per L25). New lesson **L74** (ledger-only + a flagged, not
built, invariant candidate). See `findings/2026-07-15-econ-daily-cadence-gap-dataquality.md`.

**Step 9 (paper sub-pass):** `SHADOW_REGISTRY` = S14 only. `scripts/paper_pass.py` ran clean:
0 newly processed (271 deferred-caps, 122 deferred-coverage, 29 already-in-ledger) —
idempotent, `daily_summary()` unchanged: 0 open, 214 settled, realized P&L **+$5.77**
(`broker_truth`).

## Gates
- `pytest -q` — 931 passed (unchanged; no test/source code touched this run).
- `python scripts/invariants.py --full` — green (only the standing non-gating L17/L25 advisories).

Still 0 proven edges. Docs/findings-only diff (`findings/`, `kb/00-LOG.md`, `kb/lessons/00-lessons.md`,
`LOOP-QUEUE.md` run-log line) — no execution code outside the sanctioned paper tier, no demo/live
order paths, no credentials. No verdict/registry change this run → two-agent rule not triggered.

---

## 2026-07-15 14:xx ET — Idle run: queue still drained, L39 converted UNENFORCED→test (core/income_legs.py)

Research-loop run. Step 0a PASS (`origin/main` HEAD `4c06e00` not rewound — history-integrity
check confirmed the shallow clone's initial "forced update" fetch warning was a `--depth 50`
graft-boundary artifact, not a rewrite: unshallowing the clone and re-checking
`git merge-base --is-ancestor` on the prior tip confirmed ancestry; last 5 merged PRs (#79-#84)
all present as ancestors on `origin/main`; newest `kb/00-LOG.md` entry and newest
`tape/*/dt=*` content both 2026-07-15, 0-day gap). Claim-check: 1 open PR **#77** (Ryan's own
queue-restock session, still open/unmerged, Q29-Q32 numbering still collides with the Q29/Q30
slots #79/#81 already merged) — unchanged since #84 flagged it ~3h earlier, not re-flagged.

**Queue state unchanged: every numbered item Q0-Q30 is still DONE, BLOCKED(data-adequacy), or
RESERVED — no TODO/IN-PROGRESS milestone was eligible.** Fourth consecutive idle run. Q21
idea-gen stays ROUND COMPLETE (PR #80) — not re-run.

Per the v3 idle-run policy, order (a): re-scanned `kb/lessons/00-lessons.md`'s standing
UNENFORCED rows. L22/L25/L27/L28/L32/L45 are already resolved in the current tree (via L24,
`scripts/invariants.py`'s tape-dir-shape check, `core/bootstrap.py`'s `clears_tick_magnitude`/
`floor_pinned_fraction`/`bracket_by_movement`, and L49's `core/timeutil.py` respectively) —
their own ledger rows just never got a superseding entry pointing at the code, same stale-
bookkeeping pattern PR #84 already flagged for L22/L25 and left as-is (not worth a churn-only
edit). L47 turned out to already be resolved too — `core/depth.py`'s docstring explicitly
documents ladder sizes as floats (L47) — left as-is for the same reason. L51/L64/L65/L66/L68/
L69 are all per-design methodology/market-structure discipline notes their own rows already
mark as **not statically assertable** (several say explicitly "no code change") — not core-
write candidates. Picked the next genuinely open, code-shaped candidate: **L39** (a bracket-
ladder P&L that nets a small edge against a large loss leg is vulnerable to a queue-blind fill
proxy crediting the income leg too easily — S14's own finding was that 78% of its $0.093 edge
came from sub-100-contract-volume income legs). Built `core/income_legs.py`
(`income_leg_thin_fraction`, `income_leg_edge_at_gate` — given per-leg `(income, volume)`
pairs, reproduces the S14 "78% from thin legs" decomposition and its complementary volume-
gated haircut sum) + `tests/test_income_legs.py` (12 cases, incl. the S14-shaped regression
and empty/zero/negative-total-income edge cases resolving to `None`/0.0 rather than raising).
No blocking static invariant added — same L6-class per-design population choice as L27/L28/
L32/L59's conversions. Ledger row **L73** records the supersession. Still 0 proven edges.

**Step 0b sweep:** 1 branch newer than PR #84's merge (15:17:49Z) and >30min old —
`claude/determined-goodall-61mt4v` (15:59:49Z, the cloud collector's outcome-branch fallback,
carrying a 15:55:32Z hourly pass the vps legs' own 16:27Z/17:27Z passes never absorbed).
Line-set diff (not a raw line-count diff) against `main`'s current per-family tape files found
**1,088 missing lines**, all JSON-validated before append, 0 invalid/reordered/duplicated:
`orderbook_depth` +850, `sports_pairs` +219, `polymarket_macro_pairs` +15, `crypto_hourly` +2,
`polymarket_pairs` +2.

**Step 9 (paper sub-pass):** `SHADOW_REGISTRY` = S14 only. `scripts/paper_pass.py` ran clean:
0 newly processed (271 deferred-caps, 118 deferred-coverage, 29 already-in-ledger) —
idempotent, `daily_summary()` unchanged: 0 open, 214 settled, realized P&L **+$5.77**
(`broker_truth`).

## Gates
- `pytest -q` — full suite green (12 new `test_income_legs.py` cases; 931 total).
- `python scripts/invariants.py --full` — green (only standing non-gating L17/L25 advisories).

Docs/data/paper-tier-only diff — no execution code outside the sanctioned paper tier, no
demo/live order paths, no credential handling.

---

## 2026-07-15 15:xx ET — Idle run: queue still drained, L59 converted UNENFORCED→test (core/reversal.py)

Research-loop run. Step 0a PASS (`origin/main` HEAD `9a564d0` not rewound — merge commits for
PRs #79/#80/#81/#83 all present as ancestors on `origin/main`; newest `kb/00-LOG.md` entry and
newest `tape/*/dt=*` content both 2026-07-15, 0-day gap). Claim-check: 1 open PR **#77** (Ryan's
own queue-restock session, still `pending`/unmerged, its Q29-Q32 numbering still collides with
the Q29/Q30 slots #79/#81 already merged) — unchanged since #83 flagged it ~3h earlier, not
re-flagged.

**Queue state unchanged: every numbered item Q0-Q30 is still DONE, BLOCKED(data-adequacy), or
RESERVED — no TODO/IN-PROGRESS milestone was eligible.** Second consecutive idle run. Q21
idea-gen stays ROUND COMPLETE (PR #80, this morning) — not re-run.

Per the v3 idle-run policy, order (a): while re-scanning `kb/lessons/00-lessons.md`'s UNENFORCED
rows for a candidate, found two — **L22** (real_bid tag-enum question) and **L25** (tape dir-shape
check) — whose enforcement column is stale: both are already implemented and tested in the current
tree (`core/source_tag.py`'s docstring + `tests/test_invariants.py::test_db_real_bid_tag_is_caught_as_invalid_enum`
resolve L22 via L24's supersession; `scripts/invariants.py`'s `_tape_dir_shape_issues`/
`tape_dir_shape_warning` + `tests/test_invariants.py` resolve L25 to **test**) — left as-is rather
than re-editing (L22 already has its L24 supersession; L25's row itself just hasn't been touched
since the code landed, not worth a churn-only edit this run). Picked the next genuinely open
candidate instead: **L59** (S24's momentum/reversal precheck must report reversal FREQUENCY and
the sign-conditioned MEAN as two separate numbers, never classify on frequency alone — flagged as
a future `core/`-write pass). Built `core/reversal.py` (`reverses`, `direction_precheck` — mirrors
`scripts/q28_s24_nearclose_fade_probe.py`'s `gate2_direction` exactly) + `tests/test_reversal.py`
(11 cases, incl. an L59-shaped regression: reversal_fraction=0.25 reads as momentum by frequency
alone, but a minority of large reversals flips both sign-conditioned means, so `is_momentum`
correctly comes out False). No blocking static invariant added — the check is a per-probe
population/classification choice (L6-class), not a lexical pattern. Ledger row **L72** records the
supersession. Still 0 proven edges.

**Step 0b sweep:** 1 branch newer than PR #83's last sweep point (12:17:11Z) and >30min old —
`claude/determined-goodall-4ubuvr` (13:06:30Z, the cloud collector's outcome-branch fallback,
carrying the 2026-07-15T12:55:39Z hourly pass). Line-set diff against `main`'s current
`tape/orderbook_depth/dt=2026-07-15.jsonl` found **0 missing lines** — already fully reconciled,
nothing to append.

**Step 9 (paper sub-pass):** `SHADOW_REGISTRY` = S14 only. `scripts/paper_pass.py` ran clean: 0
newly processed (271 deferred-caps, 112 deferred-coverage, 29 already-in-ledger) — idempotent,
`daily_summary()` unchanged: 0 open, 214 settled, realized P&L **+$5.77** (`broker_truth`).

## Gates
- `pytest -q` — full suite green (11 new `test_reversal.py` cases; 895 total).
- `python scripts/invariants.py --full` — green (only standing non-gating L17/L25 advisories).

Docs/data/paper-tier-only diff — no execution code outside the sanctioned paper tier, no
demo/live order paths, no credential handling.

---

## 2026-07-15 12:xx ET — Idle run: queue drained (Q0-Q30 all DONE/BLOCKED/RESERVED), L67 converted UNENFORCED→test, step-0b sweep +2,242 lines

Research-loop run. Step 0a PASS (`origin/main` HEAD `f9dd5f0` not rewound — merge commits for
PRs #78/#79/#80/#81 all present as ancestors on `origin/main`; newest `kb/00-LOG.md` entry and
newest `tape/*/dt=*` content both 2026-07-15, 0-day gap). Claim-check: 1 open PR **#77** (Ryan's
own queue-restock session, `dirty` — its Q29-Q32 numbering collides with the Q29/Q30 slots
already merged onto `main` by #79/#81) — untouched, left for Ryan, not force-resolved or
re-flagged (no new information since #79/#80 already flagged it).

**Queue state: every numbered item Q0-Q30 is DONE, BLOCKED(data-adequacy), or RESERVED — no
TODO/IN-PROGRESS milestone was eligible.** (The stray `Status: TODO` lines still visible under
Q9/Q11/Q12/Q16 are stale original-spec text kept verbatim below a later DONE resolution per the
append-don't-rewrite Stop rule, not live work — confirmed by reading each item's full history.)
Q21 (idea-gen) is itself ROUND COMPLETE as of this morning's edge-hunter run (PR #80, 0
survivors) — re-running it hours later would be redundant, not a new idle-run unit.

Per the v3 idle-run policy, order (a): converted lesson **L67** (the S30 two-sided-depth-illusion
kill — a maker-spread candidate mistook whole-ladder-summed depth for capturable top-of-book
depth) from `UNENFORCED` to `test`. Built `core/depth.py` (`capturable_depth`,
`total_ladder_depth`, `lottery_tail_fraction` — sum-within-N-cents-of-BBO vs whole-ladder-total,
mirroring `core/bootstrap.py`'s "give the lesson one importable home" pattern) + `tests/test_depth.py`
(11 cases, incl. an L67-shaped KBO regression: 10 contracts at best bid vs 4,000 at a 55¢-away
lottery price → 99.75% tail fraction). Did not add a blocking static invariant — no probe today
violates the pattern to retrofit, and a lexical "ban raw ladder sums" scanner risks false
positives (`orderbook_depth`'s own `depth` field is a legitimate whole-ladder count); noted as a
revisit-if trigger in the ledger row instead of a premature invariant.

**Step 0b sweep:** found 3 branches with commits after the last sweep (#81, 06:35:56Z) all >30min
old: `tape/hourly-20260715T0656Z`, `claude/determined-goodall-x67y3a` (the cloud collector's
outcome-branch fallback, L-class per #78), `tape/hourly-20260715T0959Z`. Set-diffed each family
file's lines against `main` (not a raw `git diff --stat`, which is line-order-sensitive and wildly
overstates the gap on an append-only file) and union-appended the true missing set: **2,242 lines**
across 8 families (`orderbook_depth` +1,724, `sports_pairs` +450, `polymarket_macro_pairs` +30,
`polymarket_cpi_pairs` +24, `econ_prints` +5, `crypto_hourly` +4, `polymarket_pairs` +4,
`anomalies` +1) — every line JSON-validated before append, 0 invalid, 0 reordered/duplicated.

**Gates:** `pytest -q` → 884 passed (873 prior + 11 new `test_depth.py`). `python
scripts/invariants.py --full` → green (only the standing non-gating L20/L25 advisories plus a
144-local-ref advisory that is itself the artifact of this run's own `git fetch` staging the
swept branches, not a new gap).

Still 0 proven edges (unchanged — this run touched no strategy verdict, so the two-agent rule
does not apply). No `execution/` paper-tier tape appeared since the last `paper_pass.py` run, so
step 9 is a no-op this cycle (`SHADOW_REGISTRY` = S14 only, unchanged realized P&L +$5.77
`broker_truth`).

**Next:** the queue needs restocking — PR #77 (Ryan's own restock) should get rebased and merged
by Ryan, or a future run should draft fresh Q31+ items once #77's fate is resolved. Until then,
expect more idle runs; the free-data edge space is deeply mined (2 consecutive Q21 rounds, 0
survivors).

---

## 2026-07-15 01:xx ET — Q30/S29 draw-aversion maker probe: DEAD-by-fillability, two-agent-confirmed, L69-L71

Research-loop run. Step 0a PASS (`origin/main` HEAD `83a1ffa` not rewound; newest `kb/00-LOG.md`
entry and newest `tape/*/dt=*` file both 2026-07-15, 0-day gap; recent merged PRs #78/#79/#80 all
ancestors). Claim-check: open PR **#77** (Ryan's queue restock) unchanged since last flagged by
#79/#80 — not re-flagged with no new info. Step 0b: remote `tape/hourly-*`/`tape/burst-*` branch
count (143) identical to PR #80's check 45 minutes earlier — nothing new to sweep this run.

**Q30 (topmost eligible TODO) — S29 soccer draw-aversion underpricing maker probe.** Delegated to
`edge-prober` (built `scripts/q30_draw_aversion_maker_probe.py`, 24 offline tests, live settlement
pull for 158 `-TIE` markets across 19 discovered soccer series) then an independent `verifier`
(two-agent rule).

- **Headline (spec population, earliest pre-close entry):** 157 games, draw rate among fills
  28.03% vs breakeven 18.99% (mean fill $0.1799 + $0.01 fee), net edge +9.03¢, block-bootstrap CI
  [+0.0208, +0.1627] — every binding gate passes. This *contradicts* the queue's predicted
  fee-death.
- **Why it isn't real:** spec entry sits at a median 65.6h pre-close with p90 entry spread 86¢.
  Verifier hand-inspection found the edge is carried by 1-contract nickel bids against 87-94¢
  asks days before kickoff — nominal lottery-ticket placeholders the generous fill-sim (a cancel
  ahead counts as advancing us, L48) still marks FILLED. Two honest fillable-entry robustness cuts
  (two-sided book ≤10¢ entry spread, n=119; near-close ttc≤24h, n=15) both fail to reproduce the
  edge — the two-sided cut's CI straddles zero, the near-close cut's point estimate goes
  **negative** (−4.47¢).
- **Verifier: numbers CONFIRMED (bit-for-bit independent re-derivation, fresh parser), ALIVE
  framing REFUTED.** Recommended DEAD-by-fillability over the prober's own "ALIVE-PROVISIONAL but
  fragile" hedge. The probe's verdict logic was patched post-verification so a re-run on updated
  tape computes this honestly by default, not via a manual override every time.
- `kb/strategies/00-index.md` S29 flipped `idea` → **`dead ✗`**. Still **0 proven edges**.
  New lessons **L69** (fillable-entry restriction must be the PRIMARY population of any
  earliest-pre-close queue-aware fill-sim, not a robustness footnote), **L70** (draw-aversion is
  directionally real but unfillable — an empirical record distinct from L54's absent/reversed
  favorite-longshot bias), **L71** (the gate-4 power-floor formula is `sqrt(p(1-p)/n)`, a
  one-sigma SE, not a 1.96-scaled half-width). See
  `findings/2026-07-15-q30-draw-aversion-s29-verdict.md`.

**Step 9 (paper sub-pass):** `SHADOW_REGISTRY` = `s14_ladder_underwriting` only; idempotent this
cycle (no new tape appended to advance it), realized P&L unchanged **+$5.77** (`broker_truth`).

**Gates:** `pytest -q` — full suite green (24 new Q30 tests). `python scripts/invariants.py --full`
— green (only the standing non-gating L20/L25/L29 advisories).

---

## 2026-07-15 04:xx ET — kalshi-edge-hunter nightly: review (S28/Q29) PASS, Q21 idea-gen (3 proposed, 0 survived — S30 verifier-KILLED), L67-L68

Nightly thinking-seat run. Step 0a PASS (`origin/main` HEAD `9e5af65` not rewound; newest
`kb/00-LOG.md` entry and newest `tape/*/dt=*` file both 2026-07-15, 0-day gap). Claim-check: 1
open PR **#77** (Ryan's queue-restock, `dirty` — its Q29-Q32 numbering collides with main's
already-merged S28/S29) — already flagged by #79 three hours earlier and <1 day old, so NOT
re-flagged (housekeeping: don't re-flag with no new info). Gates green throughout (873 tests,
`invariants --full`).

**Unit 1 — adversarial review of the one new last-24h verdict (S28/Q29 post-close settlement-lag
DEAD-by-convergence). PASS.** The 2026-07-14 findings (S22/S23/S24/S17) were already reviewed by
yesterday's edge-hunter #75, so today's only new verdict is S28. Re-checked its single
load-bearing fact independently — that the 4 genuinely-post-close captures all have empty books —
by parsing raw `tape/orderbook_depth/dt=2026-07-{11,12}.jsonl` directly: all four NPB captures
(KXNPBGAME YOMYOK-YOK/YOM cap 12:55:57Z, YAKHAN-HAN/YAK cap 11:55:18Z) show
`best_yes_ask=best_no_ask=None` and `yes_bids=no_bids=[]`, ~1 min after their real close_time.
The DEAD verdict holds; no GitHub issue opened.

**Unit 2 — pipeline replenishment (Q21 idea-gen; eligible items = 1 (Q30/S29) < 2).** 3
candidates generated (`research-lead`), each attacked before registration (two-agent rule).
**0 registered — still 0 proven edges.** This is the second consecutive 0-survivor round (with
#75), which is itself signal: the free-data / already-collected-tape edge space is deeply mined.
- **S30** — deep-two-sided wide-spread selective maker on illiquid foreign-sports books
  (KBO/NPB/BSN), the round's one "likely-survives" candidate. **Independent `verifier`
  KILL-at-idea-stage, two decisive reasons:** (1) the load-bearing "wide spread backed by
  thousands of two-sided contracts (KBO 4,601 yes / 10,556 no)" is the *total ladder summed
  across all price levels* — the tradeable **top-of-book is 10 yes / 26 no** contracts and
  **98.83%** of KBO resting yes-size sits at price ≤0.10 (deep-OTM lottery bids, e.g. 4,000
  contracts at 6¢), so the wide spread is an **L31 wing with a two-sided tail**, not a competition
  gap; (2) the mechanism's discriminating claim ("width = absent competition, not adverse
  selection") is structurally **unobservable** — `tape/orderbook_depth/` carries resting-depth
  snapshots only (no trade/volume/last fields) and the only sports executed-volume tape anywhere
  is WC2026 (L44), so no adverse-selection-modeled block-bootstrap CI (L41 needs opposing-sign
  clusters, not toxicity assumed away) can be built. KBO also settles partly `scalar` (L52). Not
  a fee kill — KBO's ~13.5¢ half-spread genuinely dwarfs the 1¢ fee — which is exactly why the
  two-sided-depth illusion (not L30) is the interesting killer.
- **S31** — crypto near-money last-capture reachability taker. Idea-killed: taker-into-overround,
  presumptively dead per S1/S5/S7 and self-admitted; the near-money bracket would need to be
  *under*-priced despite the vig, and the settlement-instant spot conditioner is data-starved
  (`crypto_hourly_historical_spot` = 36 rows, 07-04 only). Distinct object from S10 (far/tail),
  same overround wall.
- **S32** — crypto near-money two-sided maker-short. **Folded into S14, not a new S-number** — it
  *is* S14's explicit remaining binding gate (queue-aware `orderbook_depth` short-YES fill-sim),
  scoped to two-sided legs; registering it would duplicate an S-number and split S14's factor slot
  (Rule #6 ρ). Confirmed near-money crypto two-sided spread is only ~3¢ → L30 fee regime; S14's
  ~9¢ proxy edge lives in the thin wings the queue-aware sim is expected to strip.

Lessons **L67** (median total-ladder depth on an illiquid two-sided book is not evidence of a
capturable spread — decompose by price band; ≥~90% of size at price ≤0.10 ⇒ L31 wing with a
two-sided tail; fillable number is the top-of-book, not the ladder total) and **L68** (a
maker-spread-capture idea over `orderbook_depth` alone is toxicity-untestable by construction —
no trade prints — and should be killed at idea stage, not registered as "untestable"). Both
ledger-only (UNENFORCED).

**Unit 3 — probe-prep: NO-OP.** Nothing gated unblocks within 72h: WC final Jul 19 is a burst
capture leg (not a probe); FOMC Jul 29 is outside the window and already has its built+tested
`scripts/s17_leadlag_probe.py --burst-window`; S14's ≥30-event-day depth gate is weeks off (8
days of `orderbook_depth` collected); Q30/S29 is ungated and the 3h research loop will execute it.

**Housekeeping.** Burst triggers past event date → `kalshi-burst-cpi-0714`,
`kalshi-burst-wcsemi1-0714` remain flag-for-deletion (both fired Jul 14; unchanged since #75).
Note the wcsemi2/wcfinal/fomc one-shots were already Ryan-hardened with mandatory push-verification
(updated 00:59Z) after the semi-1 burst lost its captured data to a dead sandbox — that's handled.
Remote branches: **142 `tape/hourly-*` + 1 `tape/burst-*`** (the compounding-branch cleanup remains
a standing weekly-retro item). Step 9 paper sub-pass: `SHADOW_REGISTRY` = S14 only, no new tape
appended this run → paper broker idempotent, `daily_summary()` unchanged: 0 open, 214 settled,
realized P&L **+$5.77** (`broker_truth`). See `findings/2026-07-15-q21-ideagen-edge-hunter.md`.

---

## 2026-07-15 03:xx ET — Q29/S28 post-close settlement-lag taker: DEAD-by-convergence, verifier-CONFIRMED; L64-L66; PR #78 merged

Research-loop run. Step 0a PASS (`origin/main` HEAD `88867ba` not rewound before this run's own
sweep landed; newest `kb/00-LOG.md` entry and newest `tape/*/dt=*` file both 2026-07-15, 0-day
gap). Claim-check found 2 open PRs: **#78** (local sweep, "clean" mergeable state, recovers
29,637 stranded lines from unswept `claude/*` outcome branches the standing step-0b pattern never
scanned) — merged immediately (squash, tape-only, no queue item claimed). **#77** (queue restock
adding Q29-Q32 + housekeeping) was `dirty` — its own Q29/Q30 numbers (S14 binding-gate / fair-
anchor+depth) collide with the Q29/Q30 already merged onto main by yesterday's Q21 idea-gen round
(S28/S29) — left open, untouched, noted for Ryan rather than force-resolved.

**Step 0b sweep:** 2 stranded `tape/hourly-*` branches (`...20260714T2355Z`, `...20260715T0100Z`,
both >30min old) carried lines missing from `main` across 5 families/2 days — union-appended
**1,839 lines** (crypto_hourly +2/+2, orderbook_depth +610/+841, polymarket_macro_pairs +15/+15,
polymarket_pairs +2/+2, sports_pairs +135/+214), all JSON-validated, append-only.

**Q29 — S28 post-close settlement-lag taker (topmost eligible TODO).** Delegated to `edge-prober`
+ independent `verifier` (two-agent rule). **Verdict: DEAD-by-convergence** (data-adequacy — an
empty tradeable population, not a CI≤0). `scripts/q29_settlement_lag_probe.py` (+19 offline tests)
found Q25's `post_close` bucket (n=2,478, defined by ticker HHMM token) was **99.86% mislabeled**:
only 4/2,864 captures are genuinely post-close under `broker_truth` settlement `close_time`
(median understatement +7.07h, max +24.33h — L46's ~13h tz uncertainty made concrete). All 4
genuine post-close captures have a **fully empty book** (no `real_ask`/`real_bid`) — Kalshi
empties and settles a sports book AT close (max observed capture-to-close gap across the whole
depth tape: 0.024h/~1.4min), so no stale resting-quote window exists to lift. Lookahead-clean
population = 0 games (Gate 1 FAIL, floor 10); fillability Gate 2 FAIL; bootstrap gates N/A.
Verifier independently re-derived every number from raw tape with fresh parsing code (not reusing
the probe's helpers), hand-confirmed the empty-book claim against raw tape lines, searched for and
ruled out a missed population (no series anywhere in the tape shows a two-sided sub-$1 book after
its real close), and caught one minor overstatement (the L41-degeneracy claim was too strong — a
thin losing tail exists in principle for a settlement correction/void) that does not change the
verdict. `kb/strategies/00-index.md` S28 flipped `idea` → `dead ✗`. Lessons **L64** (ticker-HHMM
≠ real close_time — verify against `broker_truth` before trusting a population definition, applies
retroactively to Q25's headline liquidity numbers), **L65** (Kalshi empties the book AT close —
sports analogue of L61's econ-ladder-closes-before-the-print), **L66** (precision note: "buy the
known winner" is near-L41-degenerate, not provably degenerate — state it that way). Still **0
proven edges**.

**Step 9 (paper sub-pass):** `SHADOW_REGISTRY` = S14 only; `paper_pass.py` idempotent (0 newly
processed — no new `crypto_hourly` event-hours from this run's sweep), `daily_summary()`
unchanged: 0 open, 214 settled, realized P&L **+$5.77** (`broker_truth`).

Gates: `pytest -q` → 873 passed (854 prior + 19 new). `python scripts/invariants.py --full` →
green (only standing non-gating L20/L29 tape-hygiene advisories). See
`findings/2026-07-15-q29-settlement-lag-s28-verdict.md`.

---

## 2026-07-15 04:xx ET — kalshi-edge-hunter nightly: adversarial review (4 findings, all pass), Q21 idea-gen (3 proposed, 0 survived), L61-L63

Nightly thinking-seat run. Three units, in order.

**Unit 1 — adversarial review of the last 24h of findings/verdicts (4 findings, one load-bearing
number re-checked each, all PASS).** (a) S22/Q26 OFI-imbalance DEAD-by-calibration — the
disagreement-subset complementarity (imb 0.2791 + mid 0.7209 = 1.0) is mechanically forced
(24/86 + 62/86), the kill is sound. (b) S23/Q27 favorite-maker DEAD-by-fee — re-derived the maker
fee at the $0.7261 fill via `core.pricing` (ceil(0.0175·0.7261·0.2739·100)/100 = $0.01) → breakeven
0.7361, matches. (c) S24/Q28 near-close fade DEAD-by-round-trip — taker rate 0.07 confirmed, sample
round-trip 0.21−0.43−0.02−0.02 = −0.26 reproduces. (d) S17/Q19 CPI-burst PROVISIONAL — both
fed-decision legs `real_ask`, synthetic CPI leg excluded (Hard Rule #3), dislocation 0.28−0.181−0.02
= +0.079 reproduces. **No review failure → no GitHub issue opened.**

**Unit 2 — pipeline replenishment (Q21 idea-gen round fired; eligible queue items = 0 < 2).**
Proposed 3 new falsifiable S-candidates, each attacked by an independent `verifier` at the IDEA
stage before registration. **All 3 killed at idea stage — 0 registered, still 0 proven edges:**
- **S25** (post-print within-Kalshi known-outcome pickoff) → DOA: the resolving-month CPI ladders
  (`-26JUN`) close 12:25/12:29Z, *before* the 12:30Z print, and are absent from the tape post-print;
  the 100 "post-print" records are forward months (a different object). Kalshi closes markets ~5 min
  early to deny exactly this pickoff.
- **S26** (Polymarket-anchored single-venue Kalshi macro convergence) → the ask-to-ask "gap" is
  mostly Kalshi's own 9–11¢ bid-ask spread (Poly sits INSIDE Kalshi's spread in 62.6% of entry-met
  records); the genuine-gap remainder is either a full Kalshi round-trip that dwarfs the $0.01–0.04
  gap or an unhedged directional macro bet (S2/S16); gate un-runnable (0 meetings resolved).
- **S27** (macro-print overshoot fade) → same close-before-print structure (n=0 for the fadeable
  object); forward ladders carry ~0.88 median yes-spreads that dwarf any retrace — S24's round-trip
  trap on econ tape.

Lessons **L61** (macro ladders settle AT the print → no post-print window; forward months are a
different object), **L62** (a cross-venue ask-to-ask gap is not an edge when one venue's own spread
exceeds it — check anchor-inside-spread first), **L63** (single-venue "convergence-hold" is a
directional macro bet, not an arb — dropping the hedge leg removes the hedge, not the risk). All
ledger-only. See `findings/2026-07-15-q21-idea-gen-round.md`. Next research-loop firing is an IDLE
RUN per the v3 idle-run policy.

**Unit 3 — probe-prep: NO-OP.** The only burst unblocking within ~72h (WC-semifinal 2, today
Jul 15) feeds the S9-family lead-lag question (registered DEAD by data-adequacy). The next macro
gate (FOMC Jul 29, outside 72h) already has its built + offline-tested probe
(`scripts/s17_leadlag_probe.py --burst-window`, PREP DONE 2026-07-13). S14's remaining depth
fill-sim gate (≥30 event-days) is weeks off — only 7 days of `orderbook_depth` collected (by file
shape, L25). Nothing to build.

**Housekeeping.** No open PRs (nothing stuck on Ryan); no open issues. Burst triggers past their
event date → flag for deletion: `kalshi-burst-cpi-0714`, `kalshi-burst-wcsemi1-0714` (both fired
Jul 14). Burst branch `tape/burst-20260714T120659Z` is fully swept onto main (0 lines missing
across all 4 tape files) → safe delete candidate. Remote branch count: **141 `tape/hourly-*` + 1
`tape/burst-*`.** No paper-tier P&L change (SHADOW_REGISTRY = S14 only, idempotent — realized
+$5.14 `broker_truth`, unchanged; this run appended no tape so the paper broker had no new tape to
replay).

Gates: `pytest -q` green, `python scripts/invariants.py --full` green (only standing non-gating
L25/L29 advisories). Diff is docs/findings-only.

---

## 2026-07-14 20:xx ET — Q21 idea-gen round (S28/S29 registered); WC-semi1 burst capture found to have silently failed

**Step 0a/0/0b:** `origin/main` HEAD `6ab32b7` not rewound (0 open PRs; `kb/00-LOG.md` newest entry
and newest `tape/*/dt=*` file both 2026-07-14, 0-day gap). Step-0b sweep found two eligible (>30min
old) stranded branches with real missing content — `tape/hourly-20260714T2258Z` (+149 lines: crypto_hourly
+2, polymarket_macro_pairs +15, polymarket_pairs +2, sports_pairs +130) and `tape/burst-20260714T120659Z`
(0 new — its econ_prints/polymarket_cpi_pairs lines were already on `main` from a prior sweep, only the
branch itself was never deleted, confirming L38/Q17's "branch pileup ≠ data loss" diagnosis). A broader
spot-check of older (pre-07-08) stranded branches found `no merge base` with `main` (orphaned by the
2026-07-08 history rewind) and a post-rewind sample (`tape/hourly-20260713T2356Z`) contributed 0 new
lines — consistent with Q17's standing finding; did not attempt a full re-sweep of the ~150-branch
pileup (that diagnosis stays reserved for PR #46).

**Finding (flagged for Ryan, not a queue item): the `kalshi-burst-wcsemi1-0714` one-shot trigger fired
(`last_fired_at` 2026-07-14T20:10:31Z per the trigger API) but produced NO tape anywhere** — no commit
on `main`, no `tape/burst-*` or `tape/hourly-*` fallback branch, nothing matching `wc-semi1` in any of
~180 remote branches checked. The session apparently did not even reach its own fallback-branch-push
step. This silently costs one of Q19's three remaining per-event legs (WC semi 1). The kalshi-edge-hunter
run above flagged this same trigger for deletion (its event date passed) but did not notice the capture
itself came back empty — recorded here so it isn't lost. **The WC semi 2 trigger
(`kalshi-burst-wcsemi2-0715`) fires again TODAY at 20:10 UTC with the identical failure mode risk** —
worth Ryan checking the wcsemi1 session's transcript before then if he wants semi2 to land. Phone note
sent at high priority.

**Q21 idea-gen round** (topmost eligible — Q26/Q27/Q28, the three 2026-07-14 Q21 survivors, all came
back dead this week, so Q21's own "<3 non-blocked items" re-eligibility trigger fired again). Delegated
to `research-lead`, which proposed 3 candidates and ran each through an independent `verifier` pass
(two-agent rule). **2 REGISTER, 1 killed at idea stage.** **Collision note:** this round ran independently
of / concurrent with the `kalshi-edge-hunter` nightly run's own Q21 round (logged immediately above) —
neither run's claim-check could see the other (neither PR was open yet when the other started), caught
only at merge time. No registry conflict resulted (edge-hunter registered 0 rows, all 3 of its
candidates killed at idea stage), but both rounds independently picked "S25" as the next free number
from the pre-merge registry; the survivors below were renumbered **S25→S28, S26→S29** at merge time so
the historical record doesn't have two different registered/narrative meanings for the same S-number.

- **S28 (Q29) — post-close settlement-lag taker.** Mechanism: after a game ends but before Kalshi
  auto-settles, sports books linger two-sided with real depth (Q25: baseball post_close n=2,478, median
  ask-queue 25,884, only 4% any-empty) — lift a sub-$0.98 winner-side `real_ask` on an already-decided
  outcome. Escapes S1/S5/S7 (a decided outcome carries no probabilistic overround) and S10 (genuinely
  two-sided, not the crypto 1¢-floor mirror). Diversity-floor slot: settlement/close-time mechanics.
  Verifier-mandated: lookahead margin must exceed the Q25 sports-timezone uncertainty (up to ~13h) plus
  game duration; exclude coarse/date-only tickers; assert real traded-side depth, not the L26/L31 mirror
  non-price. Honest expectation: probably DEAD by convergence (Kalshi likely settles too fast to leave
  room), but a clean, cheap, novel-mechanism probe.
- **S29 (Q30) — soccer draw-aversion maker bid (the `-TIE` leg).** Mechanism: documented sentiment/
  loyalty bias (Forrest & Simmons; Constantinou & Fenton; Franck/Verbeek/Nüesch's exchange-attenuation
  cross-ref, all newly distilled into `kb/quant-finance/draw-aversion-soccer.md`, trust=FALSE/`approx`-
  tagged) leaves the 3-way-soccer draw leg underbet — an outcome-TYPE bias distinct from the
  price-LEVEL favorite-longshot bias L54 already closed. Diversity-floor slot: new literature. Verifier-
  mandated: pool across all `-TIE` soccer families for power (a hold-to-settlement ±$1 leg floors the
  by-game CI half-width near $0.44/√n); model the fill-conditional no-draw adverse-selection rate as its
  own number, never condition it away; kill on the EDGE test, not the (trivially-high) fill rate (L53).
- **Killed at idea stage (no S-number): "sell the rich sports YES ask" (the S21 mirror).** Verifier kill
  on two structural grounds: (1) it's the sign-flip of already-CI'd S23 (favorites measured RICH at the
  bid ⇒ mechanically implies selling is the profitable side — no new edge information, same S14/S21/S23
  factor slot); (2) the `clears_tick_magnitude` gate is structurally unmeetable on committed tape — the
  ±$1 settlement leg floors the by-game CI half-width around $0.19 at n≈23 (S23's own demonstrated
  range) and ~$0.064 even at n≈205, straddling zero for any ≤3¢ hypothesized edge regardless of true
  effect size. A power-screen lesson candidate surfaced here (screen effect-size-vs-n for any
  hold-to-settlement ±$1-leg probe at idea stage) — flagged for a future kb-distiller pass, not yet
  assigned an L-id.

Still **0 proven edges** — this restocks the pipe by two idea-stage candidates; the bar hasn't moved.
Q21 stays STANDING per its own re-eligibility condition.

**Step 9 (paper sub-pass):** `SHADOW_REGISTRY` non-empty (`s14_ladder_underwriting`) — `paper_pass.py`
processed **9 newly-eligible fills** this pass (271 deferred(caps), 82 deferred(coverage), 20
already-in-ledger); `daily_summary()`: 0 open positions, 214 settled contracts, realized P&L
**+$5.77** (`broker_truth`, up from +$5.14).

854 tests green (docs/registry-only round — no new test files; this environment's `pip install -e`
initially picked up a mismatched `pip`/`python3` pair that made 18 test modules fail to collect on
`ModuleNotFoundError: yaml`/`requests` — re-ran via `python3 -m pip install`, which resolved cleanly to
the same 854 the `research-lead` agent's own environment reported), `invariants --full` green (only the
standing non-gating L20 stranded-tape-ref and L29 tape-dir-shape advisories). See
`kb/strategies/00-index.md` (S28/S29 rows + round note), `kb/quant-finance/draw-aversion-soccer.md`,
LOOP-QUEUE.md Q29/Q30.

## 2026-07-14 18:xx ET — Q28/S24 near-close overreaction fade: DEAD-by-round-trip, verifier-CONFIRMED; L58-L60

Topmost eligible queue item this firing: **Q28** (S24, the third and weakest of the Q21 idea-gen
survivors — Q19's remaining per-event legs stay time-gated on the WC-semi/FOMC burst windows, Q1/Q10
are blocked on an external key / months-long real-time accumulation). Delegated to an `edge-prober` +
independent `verifier` (two-agent rule). Note on process: an initial attempt routed through
`research-lead` stalled for ~10 minutes across two resumed turns without writing any files (its
nested Agent-tool dispatch of a child `edge-prober` never surfaced output); rather than burn more of
the run on it, bypassed it and dispatched `edge-prober` and `verifier` directly — worth a look by
whoever reviews orchestration reliability, though the work itself came out clean.

**Step 0b sweep (800 lines):** one unswept branch (`tape/hourly-20260714T1458Z`, >30min old) —
orderbook_depth +637, sports_pairs +142, polymarket_macro_pairs +15, polymarket_pairs +4,
crypto_hourly +2. Line-level dedup, additions only, all JSON valid.

**The mechanism.** S24 (Theme 7 behavioral, De Bondt-Thaler/Tetlock): a near-close hourly-scale mid
jump in a two-sided sports book (retail overreacting to the last salient in-game event) partially
reverses; fade it. `scripts/q28_s24_nearclose_fade_probe.py` (+13 offline tests) reads
`tape/orderbook_depth/` price paths over the 7 Q25 high-turnover two-sided cells (KBO/NPB/WNBA/
MLB/UCL/UECL/UEL) plus the committed Q26 settlement cache (`broker_truth`, no new live pull).
Detects ≥2¢ consecutive-snapshot mid jumps in the near-close window (ttc≤4h; 2¢ chosen against
Q25's 58-94% frozen-BBO noise floor), fades at `real_ask`, exits at `real_bid` on the next snapshot,
charging the FULL round-trip (2× 0.07 taker fee + 2× half-spread). An anti-overlap guard holds the
same entries to settlement instead — if only that exit paid, the finding would have to route into
S22's (already-dead) mechanism rather than register as a new S24 edge.

**Verdict: DEAD-by-round-trip, verifier-CONFIRMED.** Primary CI (block-boot by GAME, `event_ticker`,
L6): n=123 games/739 trades, mean **−$0.02936**, 95% CI **[−$0.05179, −$0.00587]** — strictly below
zero, robust across the X∈{2,3,4,5}¢ sweep (126 distinct games clear the 10-game floor at every
threshold, 12x over). The behavioral reversal IS genuinely present in mid terms (~0.7¢: post-jump-up
mean −$0.0061, post-jump-down mean +$0.0087) — De Bondt-Thaler directionally confirmed as a price
observation — but it's an order of magnitude below the ~6-7¢ realized round-trip hurdle on a
~3.7¢-overround book. Anti-overlap hold-to-settlement leg (n=126/817) CI [−$0.05884, +$0.00825] also
fails to clear >0, so the guard fired cleanly: this does **not** collapse into S22, both exits simply
lose. `bootstrap_verdict_admissible` PASS (50 opposing-sign clusters, no L41 degeneracy).

**Verifier attack.** Bit-for-bit re-run reproduced every number; a full from-scratch
re-implementation (own tape loader, own jump detection, own fee math, own by-game bootstrap) matched
to the last digit. Hand-verified sample trade (`KXKBOGAME-26JUL070530KIALOT-KIA`: rt = 0.21 − 0.43 −
0.02 − 0.02 = −0.26) confirms both taker legs charged correctly, no sign error/double-count. Largest
bootstrap cluster is 10/739 trades (1.35%) — no dominance. Lookahead clean (entry strictly precedes
exit in `captured_at`; the load-bearing round-trip leg touches zero settlement info). **S24 flipped
`idea → dead ✗`** in `kb/strategies/00-index.md`. Still **0 proven edges** — closes another Q21
survivor honestly, as the item's own spec predicted ("DEAD-by-round-trip is likely; sound and novel
nonetheless").

**Lessons L58-L60:** L58 (a behavioral signal can be real yet un-tradeable by an order of magnitude —
distinguish "exists" from "fillable," the round-trip-cost instance of L31/L39/L48's family); L59
(reversal frequency and sign-conditioned mean can disagree — a momentum precheck must report both,
not classify on frequency alone); L60 (L32's frozen-vs-movement maker dual-cut doesn't apply to a
taker round-trip — the frozen guard belongs at jump *detection*, not the fill-outcome layer;
boundary clarification, not a new mechanism).

**Step 9 (paper sub-pass):** `SHADOW_REGISTRY` non-empty (S14) but idempotent this cycle (daily
order cap already spent earlier today) — 0 newly processed, ledger unchanged: 0 open positions, 158
settled contracts, realized P&L **+$5.14** (`broker_truth`).

Gates: `pytest -q` 867 passed (854 prior + 13 new), `python scripts/invariants.py --full` green
(only the standing non-gating L20/L29 advisories). See
`findings/2026-07-14-nearclose-fade-s24-verdict.md`.

---

## 2026-07-14 15:xx ET — Q19 CPI-burst S17 lead-lag/dislocation: PROVISIONAL, verifier REFUTED both tradeable claims; no registry flip (FOMC-deferred); L57

Topmost eligible queue item this firing: **Q19's per-event CPI leg** — the June-CPI burst
(`kalshi-burst-cpi-0714`, window Jul 14 12:05→13:45Z, 60s cadence, CPI released 12:30Z) landed
today and this is the first run since, so the per-event run fired. Ran the pre-built read-only
probe `scripts/s17_leadlag_probe.py --burst-window` over the swept burst tape; delegated the
write-up to an `edge-prober` and an independent `verifier` re-derivation (two-agent rule).

**Step 0b sweep (3,438 lines):** the June-CPI **burst** branch `tape/burst-20260714T120659Z`
(+3,108 lines — the FIRST `tape/burst-*` leg ever to reach `main`; per the Burst-capture-legs
protocol it commits only to a fallback branch) plus 2 post-cutoff hourly branches
(`...1156Z`+`...1357Z`, +330). Line-level dedup, additions only (0 deletions), all JSON valid.
Per-family: polymarket_macro_pairs +1,485, polymarket_cpi_pairs +974, econ_prints +485,
sports_pairs +288, crypto_hourly +198, polymarket_pairs +8.

**What the burst tape is.** The probe reads ONLY `tape/polymarket_macro_pairs/dt=2026-07-14.jsonl`
(fed-decision family, Kalshi `KXFEDDECISION` 5-bucket ladder vs Polymarket "Fed Decision in
<Month>?" CLOB — **both legs `real_ask`**, the fillable basis). The `synthetic` CPI leg
(`polymarket_cpi_pairs/`, Kalshi side a differenced-ladder derived prob) is deliberately excluded
per Hard Rule #3; verifier confirmed no synthetic leak. Cadence is **genuine burst** (101 distinct
captures, median inter-capture gap 60.1s) — the first time S17 has sub-hourly cross-venue tape
bracketing a real macro shock, the exact data class whose absence killed S9's lead-lag test.

**What it means (all PROVISIONAL, verifier-attacked).**
- **Lead-lag is a single-tick artifact.** Raw per-ticker signed lead-lag showed a strong
  "Polymarket leads Kalshi" on the two most-CPI-sensitive July buckets (rho_polymarket-leads
  0.902 / 0.777). But removing the single 12:30:13Z release capture **collapses it to noise**
  (0.196 / 0.037) and, on the verifier's leave-one-out, the **residual sign flips toward Kalshi**
  (rho_kalshi-leads rises to ~0.39 / ~0.41) — so no sign-stable directional lead-lag claim is
  defensible. The only defensible statement is the factual 12:30:13 snapshot: Kalshi's `yes_ask`
  sat stale at 0.29 (unchanged from 12:29) while Polymarket's ask had already repriced to 0.181
  toward "hold", then Kalshi caught up to 0.16 by the next capture — an n=1 repricing-lag event.
- **No clean fillable shock-scale dislocation.** 25 fee-clearing captures / 11 episodes, but the
  WIDTH x DURATION cross (the S6/L31 discriminator this milestone was built to apply) splits
  perfectly: the two LARGEST ($0.079 on 26JUL-H25, $0.06 on 26JUL-H0, `real_ask` both legs net
  Kalshi **taker** fees, Polymarket fee an `assumed_zero_polymarket_clob` model) are
  **single-capture 12:30:13Z release-instant transients**; every DURABLE dislocation is small
  ($0.01–$0.04, September buckets, persisting 3–6 captures) — the stale/segmentation
  nominal-basis signature. Nothing is both large and durable. And `macro_pairs` is **size-blind**
  (best_ask/best_bid only, no depth), with a single pass-level `captured_at` that cannot prove
  venue simultaneity — so every dislocation is a price observation, never a fill claim.

**Verdict class: DESCRIPTIVE + PROVISIONAL, verifier CONFIRMED-numbers / REFUTED-both-claims.**
No CI, no edge, **no registry flip** — S17 stays `data-collecting`; its kill/live decision waits
for the FOMC event (Jul 29), the highest-liquidity of the five bursts, as the queue mandates.
A CPI print is a rate-*expectations* shock and one burst window is one shock. Still **0 proven
edges**. Lesson **L57** appended (burst lead-lag rho can be dominated by a single shock tick →
mandatory leave-one-out; width×duration generalizes L31 to cross-venue; macro_pairs
size-blind + single-pass-timestamp fillability caveat).

**Step 9 paper sub-pass:** `SHADOW_REGISTRY` non-empty (`s14_ladder_underwriting`); ran
`paper_pass.py` — idempotent, **0 newly processed** (today's `MAX_DAILY_ORDERS` already spent),
`daily_summary()` unchanged: 0 open positions, 158 settled contracts, realized P&L **+$5.14**
(`broker_truth`), ledger unchanged.

Gates: **841 tests green**, `python scripts/invariants.py --full` green (only the standing
non-gating L20 stranded-tape + L29 tape-dir-shape advisories). Finding:
`findings/2026-07-14-s17-burst-cpi-q19.md`.

---

## 2026-07-14 — Q27/S23 favorite-side settlement-underpricing maker: DEAD by fee, verifier-CONFIRMED; L53-L56 appended

Topmost eligible queue item (Q27, the second of the three Q21 idea-gen survivors; Q26/S22 closed
DEAD earlier today). Built `scripts/q27_favorite_underpricing_fillsim.py` (read-only, 24 offline
tests in `tests/test_q27_favorite_underpricing_fillsim.py`, all pass) testing whether the
favorite-longshot bias manifests as a fillable maker-BID edge — rest a bid to buy the favorite YES
(entry-time normalized `yes_ask` over `bracket_sum` ≥ 0.65, Hard Rule #3 via `core.pricing`) in
Q25's high-turnover two-sided sports cells (KXKBOGAME/KXNPBGAME/KXWNBAGAME/KXMLBGAME/KXUCLGAME/
KXUECLGAME/KXUELGAME) and collect $1 on settlement when the favorite wins.

**The design choice that makes it testable where S21 died:** the fair test is REALIZED Kalshi
settlement, not a devig anchor — no `sports_clv` tape, no odds-api key. The settlement leg is
pulled ex-post from Kalshi's free settled-markets endpoint over the depth tape's OWN window
(`tape/q27_settlement_cache/settlement.json`, `broker_truth`, live pull 2026-07-14T12:27Z, 462
markets), so the join is non-empty by construction (L50 — the general fix for S21's L43
disjoint-window death, positively confirmed here).

**The four binding gates.** G4 (join adequacy) PASSES: 462 settled cached, 454 binary, 8 dropped
as `result="scalar"` (L52), 207 distinct games with a genuine pre-close depth snapshot. G3 (fill
rate) does NOT kill: queue-aware `yes_bids` fill-sim (L39, NOT a candlestick print; frozen-queue =
no-fill, L32/L48), 25 favorite markets → 24 rested bids across 24 DISTINCT games, fill rate
**95.83% (23/24)** ≫ the S19 0.45% floor — the long ~37-snapshot resting window clears almost any
queue, so a high fill rate is not evidence of an edge (L53). G2 (adverse-selection leg) HOLDS: the
7 favorite-LOSES fills (~−$0.73 each, `broker_truth`) are fully in the P&L and bootstrap, never
conditioned away (L41) — verifier confirmed dropping them is the ONLY way to make the edge
positive, which is forbidden. G1 (factor slot): S23 recorded in the SAME slot as S14/S21
(short-the-overpriced-tail / favorite-longshot — one Hard-Rule-#6 ρ allocation, NOT
diversification).

**The kill — DEAD by fee.** Favorite win-rate among fills **0.6957 (16W/7L)** < mean fill_price
**$0.7261** (`real_bid`) + **$0.01** flat maker fee (`core.pricing` MAKER_FEE_RATE, L18/L30) =
breakeven **0.7361**. Favorites are marginally RICH at the bid — the OPPOSITE of the
favorite-longshot bias's prediction as a fillable maker edge (L30 / S13-family fee death).
Block-bootstrap net P&L by GAME (L6; 10,000 resamples, n_units=23): mean **−$0.0404/contract**,
95% CI **[−$0.2435, +$0.1370]**, `bootstrap_verdict_admissible` PASS (16 opposing-sign clusters —
L41) but `clears_tick_magnitude` FAIL — the CI fails both positivity and the L27 magnitude gate.
Fill-model robustness (verifier): even the max-generous all-24-filled assumption gives CI
[−0.218, +0.143], still failing the tick gate — DEAD is robust under both scarce-fill and
abundant-fill.

**S23 flipped `idea → dead ✗`** (verifier-CONFIRMED — both the producing edge-prober and an
independent verifier reproduced every number; the verifier's verdict: safe to flip the registry).
This DECIDES the undecided S13/S21 branch and closes the entire favorite-longshot / S7-family
maker lens DEAD on Kalshi sports at real fills (S13 bid vs devig null, S21 ask vs fair anchor
data-adequacy dead, S23 bid vs realized settlement DEAD-by-fee). Four lessons appended: **L53**
(a passing fill-rate gate over a long window is necessary-but-insufficient — the edge test still
binds), **L54** (favorite-longshot bias absent/reversed as a fillable maker-bid edge on Kalshi
sports), **L55** (a no-lookahead pre-close favorite population is thin by construction — the
honest anti-leak cost), **L56** (L37's Hard-Rule-#3 prose false-positive recurred at lines
6/78/171, reworded pre-commit). Still **0 proven edges** — the bar has not moved; Q28 (S24)
remains queued.

Step 0b stranded-tape sweep reconciled **612 lines** from 4 branches (07-13 T0457Z + T1755Z,
07-14 T0257Z + T0356Z): crypto_hourly +4/+4, polymarket_macro_pairs +30/+30, polymarket_pairs
+8/+8, sports_pairs +245/+283. Step 9 paper sub-pass: `SHADOW_REGISTRY` non-empty (S14) but
idempotent — 0 newly processed (daily order cap already spent earlier today), ledger unchanged
at realized P&L +$5.14.

Gates: `pytest -q` 841 passed (817 prior + 24 new), `python scripts/invariants.py --full` green
(only the standing non-gating L20 stranded-tape + L29 tape-dir-shape advisories). Finding:
`findings/2026-07-14-favorite-underpricing-s23-verdict.md`.

## 2026-07-14 — Q26/S22 OFI depth-imbalance probe: DEAD by calibration, verifier-CONFIRMED; L51/L52 appended

Topmost eligible queue item (Q0-Q25 all DONE/DEAD/time-gated; Q26 the first of the three Q21
idea-gen survivors). Built `scripts/q26_ofi_depth_imbalance_probe.py` (4-gate structure, 21
offline tests) testing whether resting L2 book-imbalance (`yes_bids` vs `no_bids` size) predicts
Kalshi sports settlement beyond the displayed mid, on Q25's high-churn two-sided cells (KBO/NPB/
WNBA/MLB/UCL/UECL/UEL).

**Gate 1 (join adequacy) passed clean**: 205 distinct joinable games (20× the 10-game floor),
via a one-time cached live pull from Kalshi's free settled-markets endpoint over the depth
tape's own window (`tape/q26_settlement_cache/settlement.json`, 458 markets, L50's ex-post-join
fix confirmed working — unlike S21's disjoint-window death).

**Gate 2 (calibration precheck) hard-killed it**: on the disagreement subset (n=86 rows/81
games — the actual trade population) imbalance hit only **27.9%** vs the mid's **72.1%**.
Verifier's sharpest attack — is 27.9% (far below 50%) actually a masked contrarian signal, i.e.
a sign bug? — resolved NO: the two hit rates are mechanically complementary on this subset
(`imb_hit ≡ NOT mid_hit`, sum to exactly 1.0 by construction), so sign-flipping imbalance would
just reproduce betting the mid, zero independent edge either way. Robust across every
time-to-close cut (ttc≤1h still 0.281/0.719) — rules out a cadence-washout explanation; the
signal is simply wrong, not stale or under-powered. Gates 3/4 (P&L, bootstrap CI) correctly
never reached.

**S22 flipped `idea → dead ✗`** (verifier-CONFIRMED, two-agent rule satisfied — three
independent probe runs, mine plus two agent re-runs, converged on identical numbers before the
dedicated verifier's adversarial pass). See
`findings/2026-07-14-ofi-depth-imbalance-s22-verdict.md`. Two lesson candidates appended: **L51**
(a disagreement-subset calibration hit-rate is complementary, not two independent
measurements — generalizes to any future "signal beats the mid" probe on a 2-way market) and
**L52** (Kalshi sports settlements aren't always binary — 8/458 cached were `result:"scalar"`,
must filter explicitly). Still **0 proven edges** — the bar has not moved; Q27/Q28 (S23/S24)
remain queued for future runs.

Step 0b stranded-tape sweep: 2,265 lines union-appended from 6 unswept `tape/hourly-*` branches
(all >30min old at sweep time). Step 9 paper sub-pass: `SHADOW_REGISTRY` non-empty (S14) but
idempotent — 0 newly processed (daily order cap already spent earlier today), ledger unchanged
at realized P&L +$5.14.

Gates: `pytest -q` 817 passed (796 prior + 21 new), `python scripts/invariants.py --full` green
(only the standing non-gating L25/L29 stray-directory advisory).

## 2026-07-14 — Q21 idea-gen round: S22/S23/S24 registered idea-stage (verifier REGISTER ×3), 0 killed; L50 appended

Q21 replenishment round (queue drained: Q0-Q25 all DONE/DEAD except time-gated Q19). Three
falsifiable candidates proposed and each independently reviewed by `verifier` (two-agent rule) —
every data-source premise re-derived from the tape, **REGISTER on all three**, 0 killed at idea
stage, each with mandatory tightenings folded into its queue item + registry note:

- **S22 — OFI / depth-imbalance settlement predictor** (idea, `low`). Resting L2 book-imbalance
  (`yes_bids` vs `no_bids` size) as a last-pre-close cross-sectional predictor of settlement on
  Q25's high-churn two-sided sports cells; taker toward the imbalance side @ real_ask, full taker
  round-trip charged. **Diversity floor (rule 2) candidate**: drawn from the Q25 depth-anatomy scan
  × a not-yet-distilled paper (Cont, Kukanov & Stoikov 2014, order-flow imbalance), distilled this
  round into `kb/quant-finance/order-flow-imbalance.md` — neither a dead-verdict inversion nor an
  S11/S12/S14/S17 family. Queue item **Q26**.
- **S23 — favorite-side settlement-underpricing maker** (idea, `low`). Rest a maker bid on the
  favorite YES (fair ≥ ~0.65) in high-turnover two-sided sports; fair test is REALIZED settlement,
  not a devig anchor (no `sports_clv`/odds-api dependency). Same short-the-overpriced-tail factor
  slot as S14/S21. Queue item **Q27**.
- **S24 — near-close hourly-return overreaction fade** (idea, `low`). Hourly near-close mid jump
  partially reverses next hour; fade @ real_ask, full realized round-trip charged; anti-overlap
  guard — if only hold-to-settlement pays, route to S22, not double-count. Queue item **Q28**.

**Structural unlock:** S22/S23 sidestep S21's L43 death by sourcing the join's settlement leg
**ex-post from Kalshi's free settled-markets endpoint over the SAME `orderbook_depth` window**
(within the 60-day L11 retention), instead of the separately-scheduled `sports_clv` fair anchors
that were disjoint from depth (S21: 0/81 joinable) — the join is non-empty by construction.
Captured as **L50** (`kb/lessons/00-lessons.md`, `protocol` — a collector/probe-design discipline,
not statically assertable, L6-class; generalizes L43/L9, cites L11).

Docs-only compounding pass — no code/test/tape touched. Queue items Q26/Q27/Q28 handed to the
orchestrator (owns `LOOP-QUEUE.md`). Registry: `kb/strategies/00-index.md` gains S22/S23/S24 rows
+ a round note + three per-candidate notes; new lit note `kb/quant-finance/order-flow-imbalance.md`
(Theme 3 deepened) + a Theme 3 pointer in `00-overview.md`. **Still 0 proven edges — this restocks
the hypothesis pipe with three idea-stage candidates; the bar has not moved.** Gates: `pytest -q`
green, `python scripts/invariants.py --full` green (only the standing non-gating L20 stranded-tape
+ L29 tape-dir-shape advisories).

---

## 2026-07-13 20:15 ET (idle run) — L45→L49: shared crypto-hour close-time helper + a real PaperBroker determinism bug found and fixed

- **Step 0a passed.** `HEAD` (`b21eac2`) is a direct ancestor of `origin/main`
  after `git fetch origin main`; no open PRs (checked via GitHub MCP).
  `kb/00-LOG.md`'s newest entry and the newest `tape/*/dt=*` file are both
  2026-07-13 (0-day gap). `main` not rewound.
- **Step 0b stranded-tape sweep (1,011 lines).** Of the unswept
  `tape/hourly-*` branches postdating the last sweep (PR #65's cutoff at
  `...1658Z`), four were >30min old: `...2056Z`, `...2157Z`, `...2158Z`,
  `...2257Z` (`...2356Z` skipped, ~10min old). Union-diffed against `main`'s
  current tape and appended: `crypto_hourly` +6, `orderbook_depth` +582,
  `polymarket_macro_pairs` +45, `polymarket_pairs` +12, `sports_pairs` +366 —
  1,011 lines, all JSON-validated, no duplicates, no reorder.
- **Milestone: no numbered queue item was eligible.** Q0-Q25 are all
  DONE/DEAD except Q19, whose per-event legs stay time-gated ahead of
  today's (Jul-14) CPI burst window — no burst tape has landed yet this run.
  Idle-run policy (a): drew from the lessons ledger's own standing
  UNENFORCED queue — **L45** ("crypto-hourly ticker hour token is ET, not
  UTC — candidate: a shared ticker-grammar parsing helper... no such shared
  close-time parser exists yet") was the newest still-unbuilt candidate;
  Q25's own `scripts/q25_depth_tape_anatomy.py` still hand-rolled the same
  ET-localize-then-UTC-convert logic inline rather than importing it from
  anywhere, exactly the re-derive-per-script duplication L33-L36 closed for
  the bootstrap/magnitude-gate/floor-precheck/frozen-cut/strike-spacing
  helpers.
- **`core/timeutil.py`**: new `parse_crypto_hour_token_close_utc(token)` —
  parses a crypto-hourly ticker's bare date+hour middle segment (e.g.
  `'26JUL0621'`), localizes to `America/New_York` via `zoneinfo` (DST-correct
  across the calendar, not a hardcoded EDT/EST offset), returns the
  tz-aware UTC close (or `None` on a grammar mismatch / out-of-range hour).
  10 new tests in `tests/test_timeutil.py`, including the exact L45
  empirical example (`26JUL0621` → `2026-07-07T01:00:00Z`) and a January
  (EST) case to prove it isn't summer-offset-hardcoded.
  `.claude/agents/edge-prober.md` house style updated to name it.
- **Gate-blocking bug found and fixed while getting `pytest` green** (not
  the chosen milestone, but required before ANY commit per protocol step 4):
  `tests/test_paper_pass.py::test_cap_defer_counts_events_that_do_not_fit`
  failed on a clean `main` checkout, unrelated to this run's own diff
  (confirmed via `git stash`). Root cause: `execution/paper_broker.py`'s
  `PaperBroker._replay()` derived the daily-order-cap's "today" from
  **`datetime.now(timezone.utc)`** — real wall-clock — while every Order
  record it counts is timestamped from `context.now_ts` (the paper tier's
  own documented contract: "no clock beyond context.now_ts," "the same
  ledger always reproduces the same state"). The test's fixtures hardcode
  `now_ts="2026-07-13..."`; once the real calendar rolled to 2026-07-14 the
  wall-clock "today" stopped matching the fixture's order timestamps, so
  `orders_today` silently read back as 0 after every `_replay()` and the
  200-order/day cap never bound — the SAME ledger, replayed on two different
  real days, gave two different accept/reject decisions. Fixed by threading
  an explicit `as_of: Optional[str]` through `PaperBroker.__init__`
  (`scripts/paper_pass.py`'s `run_pass` now passes its own `now_ts`); `None`
  still falls back to wall-clock for any caller with no injected reference
  time. 2 new tests in `tests/test_execution_paper_broker.py` proving
  `orders_today` follows `as_of`, not the real clock.
- **`kb/lessons/00-lessons.md`**: appended **L49** (escalates L45; L45
  itself stays UNENFORCED as a ledger row per the append-only rule). The
  PaperBroker fix is infra, not a lessons-ledger row — no probe/collector
  precedent to generalize, just a bug found while enforcing the pytest gate.
- **Step 9 (paper sub-pass).** `SHADOW_REGISTRY` non-empty (`s14_ladder_underwriting`).
  Ran `python -m scripts.paper_pass` for real over tape committed since
  Q22's original pass: **10 more event-hours processed** (20 total
  in-ledger), realized P&L **+$1.83 → +$5.14** (evidence, not a verdict —
  S14 registry status unchanged). 280 deferred(caps), 38 deferred(coverage).
  Re-run confirmed idempotent (0 newly processed, P&L unchanged at
  **+$5.14**). New ledger lines committed under `paper/ledger/dt=2026-07-14.jsonl`.
- Does not retrofit Q25's already-verdicted script (that scan's numbers
  stand as-is, discovery-class, no registry flip) — the new helper is for
  the next probe that needs a crypto-hourly close time.

## Gates

- 796 tests green (784 prior + 10 new `test_timeutil.py` + 2 new
  `test_execution_paper_broker.py`).
- `python scripts/invariants.py --full` green (only the standing non-gating
  advisories: L20 stranded-tape, L29 tape-dir-shape).

Research/infra/docs only — no order or execution code outside the sanctioned
paper tier, no network calls, no credential handling.

---

## 2026-07-13 17:09 ET (Q25) — Depth-tape anatomy scan: a fill-plausibility map, discovery-class, no verdict

Q25 (LOOP-QUEUE, topmost eligible TODO — Q20-24 all DONE/DEAD, Q19's per-event legs
time-gated until the Jul-14 CPI burst lands, Q21 not yet re-eligible at 4 non-blocked
items) was delegated to `research-lead`, which fanned out to `edge-prober` (built the scan
+ 33 offline tests) and `verifier` (independent from-scratch re-run, standing quality rule
— no registry-flip/bootstrap-CI/kill-decision here, so the strict two-agent VERDICT rule
doesn't bind, but every number destined for `findings/` still gets verifier scrutiny).

**What it is.** `tape/orderbook_depth/` is the largest tape family (~1,100-1,280
lines/hour since 07-07, 3-4x everything else combined, L38) but had only ever been read as
a fill GATE bolted onto an idea that already existed (S14, S19, Q24) — never as a
discovery scan. `scripts/q25_depth_tape_anatomy.py` tabulates, by family and category ×
time-to-close bucket: (a) queue depth at best bid/ask, (b) staleness/quote-age as a
distribution (frozen-pair fraction + streak-length), (c) one-sidedness incidence, (d) a
defined (non-canonical) resting-order-turnover proxy. **Descriptive statistics only — no
bootstrap, no CI, no verdict, no strategy registration, no registry flip**, per the item's
own spec.

**Coverage.** 122,238 depth records / 31 families / 6 capture days (07-09 honestly
absent, not padded). 21 of 114 family × ttc cells carry ≥1 insufficient metric (<20
captures/pairs), reported as the sentinel `"insufficient"`, never extrapolated.

**Headline reads (turnover benchmarked against S19's 0.45% dead-fill floor and S14's 2.5%
wing benchmark — turnover can only rule a cell OUT, never IN as fillable):**
plausibly-fillable churn concentrates in WNBA (11.06%, n=2,154), UCL soccer (8.56%), KBO
baseball (8.35%, also the least-frozen sports family at 33% — active BBO), MLB (7.62%),
NPB (6.92%); near-close baseball/basketball/soccer runs 7-13% turnover. Dead-thin: KXBIG3GAME
sits right on the S19 floor at 0.48% (n=856), plus VBA 1.37%/USLCup 1.41%/MLS 1.72%.
One-sidedness (L31) is confirmed a **crypto-only** phenomenon (96-100% any-empty, the L26
1¢-floor no-bid mirror) vs sports' 0-1% pre-close — the wing shape does not generalize
outside crypto.

**Correction caught mid-milestone.** The producer found the milestone spec's own worked
crypto-ticker example was wrong: the hour token is **ET, not UTC** (empirically confirmed
against a live book capture and `collection/crypto_hourly.py`'s own docstring). Using the
spec's UTC reading would have mis-bucketed all 45,505 crypto captures.

**Verifier verdict.** Independent from-scratch recomputation (not reusing the script's own
functions) — every anatomy number **CONFIRMED exactly**: record/family counts, category
totals, BIG3/WNBA/crypto figures, turnover formula edge cases, determinism (byte-equal
re-run ex-timestamp), fractional-size tape (a real 91,316.82-contract WC median size), and
clean provenance (no synthetic-as-fillable, no P&L, no CI). One **DISPUTE** raised: an
undercounted "15/114 insufficient cells" meta-statistic (silently excluded pooled-turnover
insufficiency). Sent back to the producer, which independently recomputed **21/114** from
the committed JSON and corrected the doc text only — no anatomy number, JSON value, code,
or test changed. Net verdict: **CONFIRMED-WITH-CAVEATS** (two disclosed, immaterial
methodology caveats: cross-day-gap contamination negligible at 0.04% of frozen pairs;
sports HHMM timezone unverifiable from the depth tape alone).

**Output:** `findings/2026-07-13-depth-tape-anatomy-q25.md` +
`findings/depth_anatomy.json` (machine-readable, keyed by family/category × ttc-bucket).
4 lesson candidates appended: **L45** (crypto hour token is ET not UTC — confirm a ticker
grammar's stated tz against tape before trusting a worked example), **L46** (sports HHMM
tz is league-local and unverifiable from depth tape alone), **L47** (`orderbook_depth`
sizes are floats, can be fractional), **L48** (a turnover proxy rules a cell OUT, never IN
— generalizes L39's proxy caution). Still 0 proven edges — this is a map to seed future
Q21 idea-gen rounds (the near-close two-sided sports window reads as the strongest future
queue-aware-fill-sim candidate; the crypto mirror and sticky small leagues already read
dead-thin), not itself an edge. 784 tests green (751 prior + 33 new),
`python scripts/invariants.py --full` green (only the standing non-gating L25 advisory).

**Next:** Q19's per-event burst analysis fires once the Jul-14 CPI tape lands; Q21 idea-gen
re-eligible once non-blocked queue items drop below 3.

---

## 2026-07-13 (Q24) — S21 the S7-maker ASK side: DEAD by data-adequacy (verifier-CONFIRMED); 0/81 joinable; S7 family closed

Q24 (LOOP-QUEUE, registry family S7/H1) tested the one leg S7c and S13 never covered: the
**maker rich-ASK sell** on sports longshots — rest the S7c-PROVEN-rich ask (short YES / buy-NO
at `1−ask`) in the longshot tail and harvest the **+2.35¢** overpricing retail lottery-ticket
takers pay pregame. S7c proved the *taker*-side richness (edge_after_fee −0.02354, CI
[−0.0245,−0.0225], n=80 games; `findings/2026-07-04-sports-clv-s7-verdict.md`); S13 tested resting
maker BIDS → DEAD (the flat maker fee ate the margin, L30). This is the direct mirror. The
edge-at-quote is **not** the question — S7c settled it. The binding question is **FILLS**: the
incumbent maker queue already posts those asks, so a resting offer joins the BACK of it.

An `edge-prober` built the mandated **queue-aware `orderbook_depth` `no_bids` fill-sim** (L39, NOT
a candlestick print), and an independent `verifier` returned **CONFIRMED-WITH-CAVEAT** — the caveat
a cosmetic 80/80→81/81 script literal (fixed separately; the real number is **81/81**), not a
verdict issue.

**What happened / the binding fact.** The mandated join — fair-anchored longshots from
`tape/sports_clv/` × the `no_bids` resting queue from `tape/orderbook_depth/` — is **0/81 joinable
(0.00%)** for the primary `fair_prob ≤ 0.20` selection (**0/83** for the `yes_ask ≤ 0.20` proxy).
Cause = **L9 non-overlap, at the collector level**: `sports_clv` fair anchors cover kickoffs
**06-04→07-03** (captured 07-03/04) while sports `orderbook_depth` began **07-07** — every
fair-anchored game had already **settled** before the depth tape began. Zero event-ticker AND zero
outcome-ticker overlap; because the calendar date is embedded in the ticker string the non-overlap
is **structural** (no join-window relaxation can manufacture a match — the verifier reproduced the
0 by bypassing the probe's own join code). Fill rate **0.00% (0 fills)**, `mean=None, CI=[None,None],
n_units(games)=0` — the queue-aware fill-sim Q24 exists to run is **structurally un-runnable on
committed tape**.

**What it means — DEAD by data-adequacy, NOT a CI falsification.** The edge-at-quote stays
**S7c-proven-rich**; only the maker FILL question is unanswered — **untested, not falsified.** It
is re-testable only on a **fresh collection where `sports_clv` and `orderbook_depth` run
concurrently over the same *upcoming* games** (a re-collected WC-final/future window) — a
collector-alignment change (L43), out of this read-only probe's lane. Same terminal shape as
S9/S10's data-adequacy DEADs.

**The death is a depth-queue TIMING gap, not a winner gap.** Settlement
(`tape/sports_history_s7/worldcup2026.jsonl`, `broker_truth`) was ADEQUATE: **81/81** fair-longshots
settled, **8/81 = 9.88% settled YES** (a textbook longshot base rate). The sold-longshot-WINS
negative-skew leg is **fully modeled and priced**, never conditioned away (Q24 gate #2 / L41):
`premium−1−fee` ≈ **−0.86** on settle-YES, `premium−fee` on settle-NO; fee = flat **$0.01** maker
fee via `core.pricing.fee_per_contract(1−premium, MAKER_FEE_RATE)` (L18/L30). The machinery is
correct and complete — it simply has zero rows, because the queue (only `orderbook_depth` carries
it) never coexists in time with a fair-anchored game.

**Steelman — quantified, no rescue.** `sports_pairs` ask≤0.20 longshots that DO overlap depth
(07-02→07-13): **346/652 (53%)** carry a measurable `no_bids` queue, **60/346 (17%)** front-of-queue,
**MEDIAN queue-ahead 485 contracts** — you rest behind a real, deep incumbent NO-bid queue,
directly confirming Q24's binding-risk thesis. But full-sim-eligible (queue AND settlement AND
executed-volume all present) = only **3 markets**, far below the **10-game CI floor** (S19's
2-event-hour data-adequacy family). The verifier independently confirmed the alternate paths
(`sports_history/` Apr–Jun NBA; `sports_pairs`-native `.raw.json` result/volume) also yield **0**
settled depth-overlapping longshots.

**Price source tags** (every price): asks/executed-volume `real_ask` · resting queue `real_bid`
(the `no_bids` mirror) · settlement `broker_truth` · `fair_prob` `synthetic`. Bootstrap by GAME
(L6) via `core.bootstrap.block_bootstrap` + `clears_tick_magnitude`.

**Registry / lessons.** `kb/strategies/00-index.md` gains **S21** (`dead ✗`), the S7-maker ASK side
— sibling of S13 the S7-maker BID side. This **closes the S7 family**: taker S7c DEAD, maker-bid
S13 DEAD, maker-ask S21 DEAD-by-data-adequacy. **Still 0 proven edges — the bar has not moved.**
H1/S21 is the same short-the-overpriced-tail **factor family as S14** (factor cap recorded). Two
lessons appended: **L43** (family-level recurrence of L9 — a collector must align the `sports_clv`
and `orderbook_depth` passes over the same upcoming games, else the join is permanently empty; `protocol`) and
**L44** (`worldcup2026.jsonl` is a viable OFFLINE sports executed-volume/touch source — per-outcome
`candles[].volume_fp` + `yes_ask.high_dollars`, the sports analogue of the crypto-only S14 candle
cache, WC-only; `ledger-only`). Citation half of the milestone already committed:
`kb/quant-finance/favorite-longshot-bias.md` (3 primary favorite-longshot-bias sources). Gates: 742
tests green (30 new Q24 tests), `invariants --full` green. Finding:
`findings/2026-07-13-q24-sports-longshot-maker-fillsim-verdict.md`.

---

## 2026-07-13 (later) — S20 CLOSED: "copy Polymarket whales" premise DEAD; H1 emitted as Q24; 2 dossier errors caught pre-merge

Distilled from the completed S20 sprint (peer-reviewed APPROVE-WITH-NOTES, corrected). Full
pipeline ran end to end: **/first-principles (GO, research scope) → /council (CONDITIONAL 3-0,
conditions C1–C5) → pre-registered sprint (`findings/2026-07-13-polymarket-wallet-forensics-s20-prereg.md`,
written before any wallet data was pulled) → sprint (`scripts/s20_wallet_forensics.py`,
re-pullable from public APIs) → /peer-review with an independent `verifier` full recomputation
from raw fills**. Every number tagged `polymarket_onchain` — none is Kalshi-edge evidence (C5).

**Premise DEAD.** Of 50 top-leaderboard wallets, 37 evaluable; exactly 1 formally survives
BH-FDR at q=0.10, and Result 2 discredits even that one → **credible skilled-wallet count: 0**.
The leaderboard decomposes into rewards-subsidized MMs (31/37 `passive-maker`, non-transferable —
Kalshi analogs S6/S13/S19 already DEAD), lottery winners with flat-to-negative per-trade edge
(16/37 negative; #1 wallet −4.9¢, rank-3 −3.0¢), and one longshot-seller whose formal
significance is a **degenerate-bootstrap artifact** (all 8 of its resample clusters resolved the
same way → one-sided p mechanically 0). "Copy the Polymarket whales" is structurally void — a
recorded dead end, not a strategy. **S20 CLOSED as a one-shot sprint** (not a recurring collector).

**Live output = H1**, emitted as `LOOP-QUEUE.md` **Q24**: maker-side rich-ASK selling on
sports/event longshots — the direct mirror of the S7c PROVED finding (Kalshi pregame sports asks
run +2.35¢ rich vs DraftKings-devig fair) that S13's bid-side test did NOT cover. H1's
evidentiary basis is **S7c alone** — after Result 2's degeneracy finding the Polymarket survivor
contributes nothing but "the trade shape occurs in the wild." Q24's binding probe requirements
carry the sprint's own lessons forward: queue-aware `orderbook_depth` fill-sim (L39, not a
candlestick print), explicit negative-skew accounting (the sold-longshot-wins leg modeled, not
conditioned away — the exact Result 2 artifact), the ≥1-losing-cluster floor, and a
citation-TODO (2–3 favorite-longshot-bias papers before it becomes eligible). H1/S14 flagged as
the same factor family (short-the-overpriced-tail), factor cap recorded now.

**Two dossier errors caught pre-merge by independent verification** (recorded because catching
them is the point): (1) zero-fill wallet count 1→6; (2) a −27.8¢/n=3,248 example figure
mis-attributed to the #1 wallet — it belonged to a rank-47 sports wallet (wrong wallet/rank/PnL/
category), the founding pt1 synthetic-price failure family (a number detached from its source
row). Both corrected in place; the qualitative conclusions survived.

**Lessons added:** **L41** (degenerate bootstrap — zero losing clusters ⇒ mechanical p=0, no
evidentiary weight; requires ≥1 opposite-sign cluster + a minimum cluster count; folds in the
resolution-conditioning root cause — conditioning long-horizon skill on already-resolved markets
truncates the unresolved tail); **L42** (trace every headline number to its exact source row
before publication — the two-agent verifier recompute is the control that caught S20's
mis-attribution). L41 is genuinely assertable but its honest home is a runtime guard beside
`core.bootstrap.clears_tick_magnitude` (`bootstrap_verdict_admissible(...)`, proposed) — that is
`core/` work, outside this distiller's lane, so L41 stays **UNENFORCED** with the invariant text
proposed and flagged for a future core-write run (same terminal shape as L39). L42 is terminal as
**protocol** (the redundant independent recompute already in the loop). No new invariant/test code
this pass — the assertable lesson's fix is out-of-lane, recorded honestly rather than half-built.

Registry: `kb/strategies/00-index.md` gains an **S20** row (`dead ✗ / one-shot sprint`) with the
Q24/H1 provenance pointer, mirroring how S19's row references Q23. Still **0 proven edges** — the
bar has not moved; S20 removes a candidate-generation avenue and adds one probe-able Kalshi
question. Finding: `findings/2026-07-13-polymarket-wallet-forensics-s20-dossier.md`.

---

## 2026-07-13 11:51 ET — Q23 CLOSED: S19 elevated-wing maker fade — DEAD, verifier-CONFIRMED

Research-loop run. Step 0a/0/0b ran first: `origin/main` reachable and un-rewound (newest
`kb/00-LOG.md` entry and newest `tape/*/dt=*` file both 2026-07-13); 0 open PRs — nothing
claimed. Step 0b sweep: two stranded branches postdated the last sweep and were >30min old
(`tape/hourly-20260713T{1301,1401}Z`), union-diffed against main (1446 new lines: crypto_hourly
+4, orderbook_depth +1162, polymarket_macro_pairs +30, polymarket_pairs +8, sports_pairs +242),
merged as PR #63 before picking queue work.

Q23 (S19's fill-sim closer) was the topmost eligible TODO item — every other numbered item is
DONE/BLOCKED/dead-verdict/RESERVED or time-gated (Q19's burst windows haven't opened yet).
Delegated to `research-lead`, which fanned out to `edge-prober` (built
`scripts/s19_wing_fade_fillsim.py` + 22 offline unit tests) and `verifier` (independent re-run,
CONFIRMED byte-for-byte, no weakening caveat).

**Verdict: DEAD.** The mechanism (rest a maker short-YES on stale far-OTM `wing_elevated`
wings, per Q20's definition, and hold to settlement) tested via the binding queue-aware
`orderbook_depth` `no_bids` fill-sim (NOT an L39 candlestick print — a new offer joins the back
of the 166-503-contract queue Q20 measured). Over 895 wings / 175 settled event-hours: 402
joinable (44.92%, depth-tape-start ceiling), only 16 ever touched (3.98% — the wings are stale
precisely because nobody lifts them), 4 filled (0.45% overall, 1.00% among joinable — below
S14's 2.5% incidental-wing benchmark). Adverse-selection split: 0/895 wings ever settled YES,
so the mechanism's predicted toxic loss leg is unobserved (sparsity, not disproof); the win-leg
mean is +$0.3550 (n=4) but the filled population is only 2 event-hours — below the bootstrap's
10-unit data-adequacy floor, so the CI [+0.285,+0.425] is a resampling artifact, not a testable
edge. Even the maximally-generous relaxation (drop the queue gate entirely) only reaches 1.79%
fill — still DEAD. S10-maker / L26 converted from untested to **tested-dead**.
`kb/strategies/00-index.md` S19 flipped `idea` → `dead ✗`. See
`findings/2026-07-13-s19-wing-fade-fillsim-q23-verdict.md`. Gates: `pytest` 712 passed,
`invariants.py --full` green. Still 0 proven edges — the bar has not moved.

Lesson candidates surfaced for a future `kb-distiller` pass (not yet promoted to
`kb/lessons/00-lessons.md`): (1) a positive, magnitude-gate-clearing CI can still be DEAD by
construction when the filled population is tiny AND the mechanism's predicted adverse leg is
unsampled — gate on data-adequacy and adverse-leg observability, not CI sign alone; (2) zero
observed toxic events is a sparsity fact, not evidence of safety, and should be surfaced
explicitly; (3) the committed S14 candlestick cache (`tape/s14_ladder_fillsim/`) is a reusable
offline executed-volume source for any queue-aware crypto fill-sim.

**Next:** Q19's per-event burst studies (CPI fires 2026-07-14 12:30Z — not yet eligible this
run) is the next queue item once its window opens; otherwise the queue falls back to the idle-run
policy (converting an UNENFORCED lesson, or the S19 lesson candidates above, into an
invariant/test is a natural next idle-run pick).

---

## 2026-07-13 08:37 ET — Q21 idea-gen round: S19 registered (idea-stage), 3 killed at idea stage

Research-loop run. Step 0a/0/0b ran first: `origin/main` reachable and un-rewound (newest
`kb/00-LOG.md` entry and newest `tape/*/dt=*` file both 2026-07-13, 0-day gap); 0 open PRs —
nothing claimed. Step 0b sweep: of the 117 stranded `tape/hourly-*` branches, three postdated
the last sweep and were >30min old (`tape/hourly-20260713T{0859,0957,1059}Z`) — union-diffed
against main's current tape (name-only diff with `--diff-filter=A/M` first, since a full
`git diff` against branches this old times out on rename-detection over 10K+ files): **1,619
lines** missing (anomalies +1, crypto_hourly +6, econ_prints +5, orderbook_depth +1,164,
polymarket_cpi_pairs +22, polymarket_macro_pairs +45, polymarket_pairs +12, sports_pairs +364),
every line JSON-validated before append, 0 exact duplicates; committed standalone (PR #61,
squash-merged) so `main` was current before the milestone landed. Branch deletion failed with
an HTTP 403 (same permission-boundary shape as the "cloud session can't push straight to
main" finding — cloud sessions can open/merge PRs but not delete remote branches either);
documented, not retried. **A much larger historical backlog remains** (~114 `tape/hourly-*`
branches spanning 2026-07-03→07-12, several showing "modified" against main's current tape
files) — spot-checked and left untouched: Q17/L38 already diagnosed this growth pattern as
"recovery is lossless, not a real problem" and Q17 is explicitly Ryan-review-only (PR #46);
not reopening that investigation from a research-loop run.

**Milestone: Q21** (topmost eligible — every other numbered item is DONE/BLOCKED/dead-verdict/
RESERVED or time-gated with no action possible this run; Q21's own standing condition,
"re-eligible whenever fewer than 2 non-blocked research items remain," is met). Delegated to
`research-lead`, which proposed **4 falsifiable S19+ candidates** and ran each through the
`verifier` agent — the two contested candidates got a **second independent verifier pass**
that reproduced the load-bearing numbers itself, real two-agent redundancy rather than a
rubber stamp (the delegate initially reported "waiting on verifier agents" twice while no
sub-agent was actually still running — caught by resuming it directly and demanding the real
final state rather than trusting the first "completed" notification at face value).

**Survivor (1): S19 — elevated-wing stale-ask maker fade on crypto ladders.** Rest a maker
short-YES (buy-NO) on the stale far-OTM `wing_elevated` members Q20's ladder anatomy
documented (`yes_ask` 0.20–0.67, `yes_bid=0`, >±3 strikes from spot) and hold to settlement —
the maker side of the tail-fade that S10's verdict + lesson L26 explicitly left UNTESTED (a
taker short there has no fillable price per L26, but a short-YES *offer* is a real price whose
fill rate is empirical, so it isn't structurally pre-dead like S10 was). Registered idea-stage
in `kb/strategies/00-index.md` with three verifier-mandated tightenings baked into the gate:
(1) the binding fill test must be the queue-aware `orderbook_depth` `no_bids` fill-sim, NOT a
candlestick-print proxy (L39 — Q20 measured 166–503 contracts already resting at these wings,
so a new offer joins the back of a real queue); (2) P&L must be conditioned on the
fill↔settlement adverse-selection correlation (a far-OTM YES is lifted mainly when spot
rushes the strike — rare fills are toxic toward settling YES against the short); (3) any CI
must clear the L27 tick-magnitude gate. Queue item **Q23** added (Status: TODO). Honest
expectation stated up front: DEAD — this is a cheap, decisive closer of the S10/L26 loose end,
not a promising edge.

**Killed at idea stage (3), recorded for provenance rather than silently dropped:**
- **Sports-moneyline overround underwriting** (maker-short the complete set) — the flagged
  +21.3¢ mean overround is an L31 wide-one-sided-wing artifact (tight two-sided books only
  3.0–3.7¢, reproduced independently by both verifier passes); the flat 1¢ maker fee eats it
  (S13/L30 territory) and its fill-sim gate duplicates S14's already-open one — the sports
  maker side was already closed dead by S13.
- **Cross-venue held-to-settlement box** (Kalshi + Polymarket) — Polymarket's NO ask isn't
  persisted in tape (only YES best_ask/bid), and the box reduces algebraically to Q19's
  already-queued dislocation scan, whose crossings are the same L31 no-real-size artifact;
  "held-to-settlement escapes staleness" is unsound because the killer is un-fillability, not
  convergence.
- **Post-release stale-ladder fade on econ prints** — Kalshi closes CPI/econ markets ~5 min
  BEFORE the scheduled release (`close_time` 12:25Z vs a 12:30Z print), so the post-release
  fill window this candidate needed is structurally empty — same death class as S10.

**Net:** still 0 proven edges — this round restocks the hypothesis pipe by one idea-stage
candidate; the bar has not moved. Two lesson candidates surfaced for a future `kb-distiller`
pass (not yet promoted to numbered lessons): (a) a "held-to-settlement box" and a "convergence
dislocation" over the same two real quotes are the same locked pair and die to the same
nominal-quote/no-real-size artifact — reframing the exit does not manufacture fillability;
(b) always read `close_time` from the tape before proposing any post-release/post-settlement
fade — Kalshi closes data-driven markets minutes before the print, not after it.

Files touched by the registration: `kb/strategies/00-index.md` (S19 row + round note),
`LOOP-QUEUE.md` (Q23 added, Q21 status updated). 690 tests green (unchanged — no code this
run), `python scripts/invariants.py --full` green (only the standing non-gating L20/L25
advisories). Step 9: `execution/strategy_api.SHADOW_REGISTRY` non-empty (S14 shadow) but this
run touched no new tape beyond the already-swept 1,619 lines above and S14's ledger has no new
settled event-hours to process since the last paper pass — `daily_summary()` unchanged from
the 2026-07-13 05:45 ET entry (+$1.83 realized, still evidence not a verdict).

---

## 2026-07-13 05:45 ET — Q22 CLOSED: S14 wired as the first-ever paper shadow strategy

Research-loop run. Step 0a/0/0b ran first: newest `kb/00-LOG.md` entry (07-13, Q20 close) and
newest `tape/*/dt=*` file (07-13) are a 0-day gap; PRs #52–#56 all reachable from
`origin/main` HEAD; 0 open PRs claim anything. Two stranded-branch sweeps this run: 869 lines
(`tape/hourly-20260713T{0656,0757}Z`, PR #57) plus a follow-up 40+200-line reconciliation of
`tape/anomalies/`/`tape/econ_prints/` against a concurrent VPS pass that landed mid-run (both
this session's local invariants-triggered 09Z captures and the VPS's own were real, unique
captures — union-appended, 0 lines dropped).

**Milestone: Q22** (topmost eligible — Q0-Q20 all DONE/BLOCKED, Q21's idle-idea-gen
re-eligibility condition, <2 non-blocked items, not met since Q19-per-event and Q22 both still
open). Q13's S14 finding already nailed down the parameter block (short-YES maker offer at
every `crypto_hourly` ladder member's `yes_ask >= $0.02`, earliest capture of each settled
event-hour). Delegating this to `research-lead` surfaced a real architectural gap before any
code was trusted: `execution/paper_broker.PaperBroker` had **no short-position model** (a
`sell` against a non-existent long silently clamps to zero — by its own docstring) and **no
settlement/expiry realization mechanism at all** (`Fill.price` is hard-bounded to
`[0.01,0.99]`, so a $1.00/$0.00 expiry value literally could not be recorded as a Fill).
Shipping the strategy without closing this gap would have silently misbooked every event-hour's
true P&L into a committed ledger — caught before any code was trusted, not after.

**The fix.** (1) "Short-YES at ask A" is represented as "buy-NO at `round(1-A,2)`, held to
settlement" — economically identical cash flows (receive `A` if not-winner, net `A-1` if
winner, either framing), which the existing long-only broker already models correctly once the
order is a NO purchase, not a YES sale. (2) A new `Settlement` record type (sibling of `Fill`,
never a loosening of it): `settle_value` restricted to exactly `{0.0, 1.0}`, `price_source_tag`
fixed to `broker_truth` — an expiry realization is venue truth, never a market print, so it
gets its own record kind rather than punching a hole in `Fill`'s honest `[0.01,0.99]` bound.
`PaperBroker._apply_settlement`/`.settle()` apply it via the same replay-from-ledger discipline
as everything else (zero fee — a settlement charges no trading fee; a settlement with no
matching open position is surfaced via `settlement_noops`, never crashed or silently dropped).

**Proof the representation is correct, not just plausible:** a new reconciliation test
(`tests/test_paper_pass.py`) — and a live re-run over the real committed ledger — showed the
paper ledger's per-event realized P&L equals `scripts/s14_ladder_fillsim.simulate_event`'s
already-verified `pnl` **cent-for-cent**, both P&L signs exercised, 0 mismatches over the 10
real event-hours processed. This is an executable proof of the buy-NO ≡ short-YES equivalence,
not a prose argument.

**What shipped:** `execution/strategies/s14_ladder_underwriting.py` (the `Strategy` proposer,
reusing `s14_ladder_fillsim`'s tested member-selection/earliest-capture logic rather than
re-deriving it), `execution/fill_models.resting_short_yes_as_no_fill` (the seller-rule fill
against the committed candle cache), `SHADOW_REGISTRY` now holds this one entry, and
`scripts/paper_pass.py` — a no-network runner: per-strategy, per-event-hour idempotency is
derived from ledger content (an `event_ticker` already on an Order line is skipped — no side
state file), each event is all-or-nothing against the read-only `execution/limits.py` caps
(never raised).

**First real pass:** 683 `crypto_hourly` records, 312 candidate settled event-hours (earliest ∩
broker-truth settlement). **10 processed → 200 orders / 89 fills / 89 settlements**;
`daily_summary()`: `paper: 0 open position(s), 89 settled contract(s), realized P&L $+1.83,
cash $+1.83, open notional $0.00`. **290 deferred(caps)** — `MAX_DAILY_ORDERS=200` bit exactly
on this first backlog-clearing pass, the expected outcome per the item's own spec (drains
~200/day on subsequent runs; the cap was NOT touched to make more fit). **14 deferred(coverage)**
— event-hours the candle cache doesn't fully cover yet. Re-running is idempotent: 0 newly
processed, same $+1.83, 10 already-in-ledger.

**Honesty note (do not overclaim):** the +$1.83 is a 10-event-hour paper-ledger figure, not a
verdict and not a bootstrapped CI — S14 stays exactly where Q13 left it in the registry
(`data-collecting`, PROXY-POSITIVE not proven). This milestone is infrastructure (evidence
accumulation toward the live gate's ≥14-day shadow-track-record requirement), not a new claim
about the edge. The two-agent verdict rule was not triggered (no registry flip/bootstrap
CI/kill decision here) — but given this is the project's first execution-lane code with real
money-shaped accounting, it got a full independent read from the orchestrating context (every
new/changed file read line-by-line, pytest and invariants re-run independently rather than
trusted from the delegate's report, ledger JSON hand-validated, the reconciliation re-run
against the live ledger) before commit. One process note: the first delegation attempt reported
"waiting on a worker" as its final answer with zero files actually written — caught by checking
the working tree directly rather than trusting the report, then re-driven to completion.
662+26=690 tests green (26 new), `invariants --full` green (only the standing non-gating L20/L25
advisories). Step 9 of this run's own protocol: this run's paper sub-pass = the first pass
itself (see above); future runs will find `SHADOW_REGISTRY` non-empty and advance the broker
over newly-arrived tape each time.

---

## 2026-07-13 02:xx ET — Q20 CLOSED: BTC/ETH fine-ladder overround anatomy — wings, not active band; "quote-only" refuted — verifier CONFIRMED-WITH-CAVEAT

Research-loop run. Step 0a/0/0b ran first: newest `kb/00-LOG.md` entry (07-13, Q13 close) and
newest `tape/*/dt=*` file (07-13) are a 0-day gap; PRs #51–#54 all reachable from `origin/main`
HEAD; 0 open PRs claim anything. Step 0b found 2 already-fully-swept branches (`2306Z`, `0006Z`,
0 new lines each — prior sweeps covered them) and 3 unswept ones (`025Z`/`0401Z`/`0457Z`,
each >30min old): union-diffed **1405 lines** missing from `main` (crypto_hourly +4,
orderbook_depth +1142, polymarket_macro_pairs +30, polymarket_pairs +8, sports_pairs +221), 0
exact duplicates, all valid JSON — committed standalone (PR #55, squash-merged) so `main` was
current before the milestone.

**Milestone: Q20** (topmost eligible — Q13/Q16/Q18 DONE, Q14/Q15 data-adequacy BLOCKED, Q17
RESERVED for Ryan-review PR #46, Q19 PREP-done but per-event gated on the Jul-14 CPI burst not
having fired yet). Delegated to `edge-prober`: the 2026-07-03 flag (188-member KXBTC ladder,
+$9.27 `bracket_sum` overround, never investigated) got its first anatomy pass.
`scripts/s20_ladder_overround_anatomy.py` (22 offline tests) bucketed 629 `crypto_hourly`
snapshots (KXBTC 316 / KXETH 313, 172 settled event-hours each, 07-03→07-13) into `active`
(±3 strike-spacings of spot, spacing inferred from the ladder itself — never hardcoded),
`wing_floor` (1¢-pinned), and `wing_elevated` (stale one-sided asks above the floor but outside
the band).

**The numbers.** Overround is **97.4% (BTC) / 84.3% (ETH) wings**, split across TWO artifact
components — not one: 1¢-floor pins (L12) AND stale one-sided `wing_elevated` asks
(`yes_bid=0`, far from money), which on BTC ($2.17) actually exceed the floor pins ($1.71). A
depth join against `tape/orderbook_depth/` (328/629 snapshots join-eligible, matched by ticker +
nearest `captured_at` since the two sub-passes carry different `capture_id`s ~20s apart, p99
staleness 34.8s/max 165.6s per the verifier's own instrumentation) **REFUTES "wings are
quote-only"**: floor wings rest median 22,768 (BTC) / 36,253 (ETH) contracts — deeply fillable
in size. They carry no edge because the flat $0.01 maker fee eats a 1¢ ask exactly to $0.00
(L30), not from thin liquidity. The S14-relevant number — active-band
`Σyes_ask − 1 − maker_fees`, block-bootstrapped by event-hour (n=172, 10,000 resamples): **BTC
+0.0087, CI [−0.0036, +0.0215] — straddles zero, fails the L27 magnitude gate, no edge**; **ETH
+0.1271, CI [+0.1046, +0.1523] — statistically positive but explicitly EXPLORATORY**, deferred
to S14's own queue-aware fill-sim gate (already PROXY-POSITIVE-not-proven) — the active-band
mids sum to 1.047 > 1.0, a heuristic tell (not a coherence theorem) that this is nominal
ask-width in a thin two-strike book requiring maker fills S14's fill-sim already showed are
adversely selected, not fillable premium. A parameter block for a future S14-crypto shadow
(band width, quote prices, nominal expected capture) was emitted, explicitly tagged unproven.

**Verifier (two-agent rule, no registry flip so not strictly required but applied per the
kb/findings quality bar anyway): CONFIRMED-WITH-CAVEAT.** Independently re-ran the script and
re-derived every load-bearing number to the same digit (wing splits, both bootstrap CIs, depth
medians, join coverage 328/629, join staleness distribution), confirmed Hard Rule #3 tagging is
correct everywhere (spot is `synthetic`, used only as a binning coordinate, never a fill price),
and confirmed `pytest` (664 passed, 642 prior + 22) and `invariants --full` (green) are real.
**One caveat applied before commit:** the finding's original causal claim — "the two ATM ETH
strikes' ~6¢ spreads push the mid-sum above 1.0" — was overstated; the verifier decomposed the
mid-sum (1.047 all-members vs 0.976 two-sided-members-only) and showed the >1.0 is driven mainly
by the `mid=(ask+bid)/2=ask/2` convention on one-sided (`yes_bid=0`) floor-adjacent members
pulled into the band, not the two ATM strikes named. Reworded in the finding (§3 + the lesson
candidate) to "heuristic tell, not a theorem" before commit — no number or verdict changed, the
mis-attribution erred conservative (it only argued *against* the ETH figure being an edge).

**Lessons (candidates, for kb-distiller).** The fine-ladder overround has two artifact
components (floor pins AND stale one-sided elevated asks — L31's "wide one-sided spread is
nominal" applies verbatim to the ask-sum direction, not just bid-ask spread). "Wings are
quote-only" is the wrong mental model for why they're worthless — they rest tens of thousands of
contracts; the load-bearing fact is the flat maker fee, not absent size (a depth check expecting
~0 would be a confusing false alarm). A mid-sum>1.0 tell on a sub-band ask-sum CI is corroborating
evidence, not proof, when one-sided quotes are present (the synthetic mid on a zero-bid quote is
itself contaminated). Cross-family tape joins need ticker + nearest-timestamp matching, not
shared `capture_id` (crypto_hourly and orderbook_depth sub-passes run ~20s apart); check the
date-window overlap first (L9 — depth tape starts 07-07, ~52% coverage ceiling here).

**Still 0 proven edges.** Q20 is anatomy, not a verdict — no registry status changed. See
`findings/2026-07-13-btc-ladder-overround-anatomy-q20.md`. `LOOP-QUEUE.md` Q20 → DONE.

---

## 2026-07-13 xx:xx ET — Q13 CLOSED: S14 ladder underwriting is the project's FIRST non-DEAD candidate (idea → data-collecting), PROXY-POSITIVE not proven — verifier CONFIRMED-WITH-CAVEAT

Q13 became eligible (`tape/crypto_hourly/` crossed its day threshold). The `edge-prober`
produced a read-only fill-sim of S14 (ladder overround underwriting) and the `verifier`
independently re-ran it three ways — the two-agent verdict rule is satisfied.

**What was tested.** `scripts/s14_ladder_fillsim.py` (21 offline tests, injected fetcher, no
network) posts a resting short-YES maker offer at every member's `yes_ask` (real_ask) at the
earliest capture of each settled BTC/ETH hourly bracket ladder (mean 131.5 members, MECE,
exactly one strike settles YES — a genuine strike ladder; `sports_pairs`, a 2–3-outcome
moneyline group, was correctly excluded as structurally not a ladder). Fill proxy = cached
Kalshi hourly candlestick `max(high) ≥ posted_ask AND volume > 0` (the seller mirror of S13's
resting-bid rule); premium net of the maker fee from `core.pricing` (L18); payout \$1 iff the
`broker_truth` winner was among the filled strikes. 6,524 per-ticker summaries cached to
`tape/s14_ladder_fillsim/dt=2026-07-13.jsonl` (`real_ask`, resumable).

**The numbers (verbatim, reproduced 3 ways).** Block-bootstrap by event-hour
(`core.bootstrap.block_bootstrap`, n_boot=10,000, n=300): mean **+\$0.0925, 95% CI
[+\$0.0630, +\$0.1231]**, `clears_tick_magnitude` CLEARS (~6× the 1¢ tick), 72.0% events
positive; KXBTC +\$0.150 / KXETH +\$0.035 (n=150 each). Coarser units both still clear zero and
the magnitude gate (by-day [+0.068,+0.119]; by-day×symbol [+0.055,+0.130]).

**Why it is proxy-positive, not proven (the honest ceiling).** The gate's "complete fill" term
is **\$0** (complete-fill rate 0.0%) — the result is path-dependent partial premium net of the
near-certain \$1 winner loss (winner filled 96.7%, near-money 95.8%, wings 2.5%). L30
fee-annihilation deletes ~30.9% of the nominal overround. And the candlestick proxy ignores
queue position: **78% of the \$0.093 edge (\$0.072) comes from sub-100-contract-volume income
legs**; strip the income leg and it is −\$0.51 to −\$0.97. It survives a modest volume haircut
(vol≥50 +\$0.026 [+0.004,+0.049]) but dies under an aggressive one or under the unmodeled
fill↔winner adverse-selection correlation — exactly what a queue-aware L2 fill-sim must capture.

**Verdict.** `verifier`: **CONFIRMED-WITH-CAVEAT**, no material bugs/mis-tags. Registry:
**S14 idea → data-collecting** — the project's first candidate NOT to die on its first real
cut, but a proxy-positive candidate is a forward gate, not a proven fillable edge. **Still 0
proven edges; the bar has not moved.** Remaining binding gate: a queue-aware L2/depth fill-sim
over `tape/orderbook_depth/` (short-YES queue read off the mirror `no_bids` side), same shape
as S11's open fill-sim gate. `LOOP-QUEUE.md` Q13 → DONE.

**Lessons.** L39 (bracket-ladder P&L that is a small net of two large legs — Σpremium ≈ payout
— credited by a queue-blind candlestick/volume fill proxy is biased UPWARD; a per-leg volume
gate is necessary-but-insufficient; decompose the edge as a fraction of the thinnest income legs
before claiming fillability; family L27/L30/L31/L32). L40 (operational: wrap a ConnectionError
retry around large candlestick sweeps — `validation.v3_market` retries status codes but not
transport-level `ConnectionError`).

Finding: `findings/2026-07-13-ladder-underwriting-s14-firstcut.md`. Gates at verdict time:
`pytest -q` 642 passed (621 prior + 21 new); `python scripts/invariants.py --full` green (only
the standing non-gating L25/L29 stray-directory + L20 stranded-tape advisories). This run's
step 0a/0b: `origin/main` HEAD descends cleanly from the just-merged nightly edge-hunter PR
(#53, S17 burst-mode scanner) — no conflict of substance, both runs picked different eligible
queue items (Q13 here, Q19 PREP there) off the same replenished pipeline the edge-hunter's own
log entry below identified.

---

## 2026-07-13 00:15 ET — edge-hunter nightly: S11 flip re-checked (holds), pipeline healthy (3 eligible), S17 burst-mode scanner built for Jul-14 CPI

First nightly `kalshi-edge-hunter` run (Opus). Protocol steps 0a/0/0b ran first, all clean.

**0a history-integrity — PASS.** `origin/main` HEAD `af4a9d2` is a coherent, recent chain
(07-13 VPS hourly passes, PRs #51/#52 merged); newest `kb/00-LOG.md` entry (07-12) vs newest
`tape/*/dt=*` file (07-13) is a 1-day gap (< 2-day tolerance). The initial `git pull` reporting
"forced-update" was the shallow-clone (`--depth 50`) artifact prior runs already diagnosed
(reflog: fetch stored `78284fe`, rebase moved to true tip `af4a9d2`) — not a rewind.
**0 open PRs** — nothing claimed, nothing stuck on a Ryan-side action to flag.
**0b sweep:** 111 `tape/hourly-*` branches, **0 `tape/burst-*`** branches remote; no branch
newer than the last merged sweep needed union-appending this run (the :26 VPS passes are
already on `main` through `af4a9d2`).

**Unit 1 — adversarial review (last 24h findings). CONFIRMED, no issue opened.** The one
registry-moving verdict in the window was Q18's S11 `idea → data-collecting` flip
(`findings/2026-07-13-odds-leg-matched-confirmation-q18-close.md`). Independently re-derived
the load-bearing numbers straight from `tape/sports_pairs/dt=2026-07-12.jsonl`: exactly 6
`matched` records; for all 6, `Σ(fair_prob)=1.00000000`, `fair_prob` reproduces
`(1/decimal)/Σ(1/decimal)` to 6dp, `book_overround` matches `Σ(1/decimal)−1` exactly (Δ=0),
odds-leg tagged `synthetic`, Kalshi leg `real_ask`. Flip holds. The other two in-window
findings (S17 firstcut, stranded-tape growth diagnosis) made no CI/verdict claim and moved
nothing; their load-bearing claim ("0 FOMC shocks in the 07-06→07-12 window" — July FOMC is
Jul 29, outside the window) is correct.

**Unit 2 — pipeline replenishment. 3 eligible, no Q21 round needed.** Counting TODO/unclaimed/
unblocked research items: **Q13** (S14 ladder underwriting) — its ≥10-day gate is now met by
FILE SHAPE (L25): `tape/sports_pairs/` and `tape/crypto_hourly/` each have 10 valid canonical
`dt=*.jsonl` days (the `dt=2026-07-02/09/10`-dir and `crypto/dt=2026-07-10`-dir entries
correctly excluded); **Q19-PREP** (S17 burst, done this run); **Q20** (BTC fine-ladder
overround). ≥2 eligible → the hypothesis pipe is not starved, so no idea-generation round
this run (manufacturing candidates when the queue is healthy is the wrong move).

**Unit 3 — probe-prep: S17 burst-mode scanner (Q19 PREP).** The `kalshi-burst-cpi-0714`
trigger fires Jul 14 12:05→13:45Z (< 72h), delivering 60s-cadence cross-venue tape — so built
the analysis now so the per-event run only executes. `scripts/s17_leadlag_probe.py` gained a
read-only `--burst-window START END [--poly-fee F]` mode: window isolation + cadence-honesty
check, per-ticker SIGNED lead-lag (which venue reprices first), a fillable cross-venue
dislocation scan (buy cheap venue real ask / sell rich venue real bid clearing BOTH fees —
Kalshi taker fee both legs via `core.pricing.fee_per_contract`, Polymarket ~0 an explicit
tagged assumption), and a dislocation width×duration distribution. 17 new offline tests (43
total in the file), **621 pytest passed**, `invariants --full` green. Smoke over the HOURLY
tape (correctly flagged NOT burst-cadence) surfaced 616 candidate dislocations persisting
hours-to-days at ~$0.04 — the stale/nominal-quote artifact signature (S6/L31 family), NOT a
real arb; the point of the burst run is that a REAL shock dislocation should be short-lived,
and the width×duration distribution is now the discriminator. No registry change; S17 stays
`data-collecting`. See `findings/2026-07-13-s17-burst-mode-prep-q19.md`.

**Housekeeping.** No stuck PRs (0 open). No burst trigger's event date has passed (earliest is
CPI, Jul 14). Remote `tape/hourly-*` branch count: **111**; `tape/burst-*`: **0**.

---

## 2026-07-12 20:xx ET — Q18 CLOSED: odds-leg matched records confirmed live (S11 idea → data-collecting) + stranded sweep (803 lines)

Research-loop run. Step 0a history-integrity check passed: `origin/main`'s HEAD (`db33245`)
descends from all recently-merged PRs (#50/#49/#48/#47/#46-unmerged/#45/#44/#43/#42, verified
via the GitHub MCP + local ancestry); `kb/00-LOG.md`'s newest entry and the newest
`tape/*/dt=*` file are both 2026-07-12 (0-day gap). The local `main` ref and an initial
`git fetch` reporting "forced update"/"unrelated histories" were traced to this session's
shallow clone (depth 54, no common ancestor with the true root) — the same benign artifact
prior runs (#43/#44/#45/#47) already diagnosed, not a real rewrite; `git reset --hard
origin/main` resolved it. No open PRs — nothing claimed.

**Step 0b stranded-tape sweep (803 lines).** Of 109 `tape/hourly-*`/`tape/burst-*` branches,
two postdated PR #49's cutoff and were >30min old: `tape/hourly-202607122055Z` (20:57Z) and
`tape/hourly-20260712T2306Z` (23:06Z). `tape/hourly-20260713T0006Z` (00:06Z, ~6min old) was
skipped per the freshness rule. Union-diffed against `main`'s current tape (no merge-base
existed in this shallow clone, so content was read via `git show <ref>:<path>` rather than
`git diff`, same technique PR #43 used): `crypto_hourly` +4, `orderbook_depth` +538,
`polymarket_macro_pairs` +30, `polymarket_pairs` +8, `sports_pairs` +223 — 803 lines total,
all JSON-validated, 0 exact duplicates. Branch-delete not attempted (documented permission
boundary).

**Milestone: Q18's live-confirmation gate cleared.** Q18 (IN-PROGRESS since 2026-07-12,
milestones 1–4 already landed) was waiting on the first keyed VPS pass to write
`odds_leg.status="matched"` tape. Checked `tape/sports_pairs/dt=2026-07-12.jsonl`: the VPS
pass at `20260712T212303Z` (commit `6b6938d`, ~3h after the Q18 port merged as `5b265a3`)
did exactly that. Status distribution across the 6,201-line file: 3,129 `unmatched`, 2,752
`blocked_key`, 170 `unmapped_series`, 144 `not_selected`, **6 `matched`** — 3 VPS passes
(`20260712T{212303,222302,232302}Z`) × 2 World Cup games (France v Spain, England v
Argentina). `match_score=2.0` (max — exact team-name match both sides), `outcome_coverage=
"full"` (all 3 outcomes mapped 1:1, Draw↔Tie handled). De-vig math checks out:
`fair_prob` sums to 1.000000 per record, reproduces `(1/decimal_odds)/Σ(1/decimal_odds)` to
6dp, `book_overround` matches `Σ(1/decimal_odds)−1` to 6dp. Price-source tags correct per
Hard Rule #3: Kalshi legs `real_ask`/`real_bid` (fillable), odds legs `synthetic` (a de-vig
is a model, never a fill).

**Two-agent verdict rule applied** (this is a registry status flip): the `verifier` subagent
independently re-parsed the tape from scratch (not trusting the numbers above), ran
`git blame` on the first `matched` line — confirmed it lands on the VPS's first post-Q18-merge
pass and is not backfilled or fabricated — re-derived the de-vig math itself, and confirmed
Rule #3 tagging. Verdict: **CONFIRMED**. `kb/strategies/00-index.md`: **S11 idea →
data-collecting** (a data-flow milestone, not a P&L/CI claim — still thin: 1 bookmaker
(Pinnacle), 2 games, 3 passes). `LOOP-QUEUE.md` Q18 → DONE.

**Step 9 (paper sub-pass):** `execution/strategy_api.SHADOW_REGISTRY` is still empty (unchanged
since the 2026-07-12 paper spine — Q22 stays blocked-in-part on Q13/Q19/Q20 parameter blocks).
No-op this run, as expected.

Gates: pytest green, `python scripts/invariants.py --full` green.

---

## 2026-07-12 17:xx ET — Q18 odds-leg matching activation (S11's anchor) + stranded sweep (3,093 lines)

First research-loop firing under protocol v3. Step 0b swept 3,093 lines from 4 fresh
`tape/hourly-20260712T{1459,1600,1756,1956}Z` branches (PR #49, merged standalone before
the milestone). **Q18 diagnosis:** the odds-api leg's 7,476 `"unmatched"` VPS records since
`ODDS_API_KEY` went live 07-10 were not 7,476 failed match attempts — `sports_pairs.py`'s
`odds_leg` status was a hardcoded literal, and the-odds-api endpoint was **never actually
called**. Quota was not being burned (correcting the item's original framing), but the tape
has been silently useless for S11 the whole time. PR #4 (9 days stale, unmergeable — ~10,000
files diverged) had already built the real matching layer; ported it onto current `main` by
hand: `collection/odds_api.py` (kickoff-primary + team-name-fallback matching, Pinnacle-first
bookmaker selection, honest per-game statuses, built-in quota discipline), `sports_pairs`
schema → v2 (`game_start`/`outcome_name` persisted even keyless, so keyless captures stay
replayable). 26 new/changed tests, 630 total green, `invariants --full` green. Live keyless
smoke (no key in this cloud sandbox by design): 114/114 real Kalshi moneyline games captured
complete, v2 fields correct. PR #4 closed as superseded. **Not flipped:** S11 stays `idea` —
success condition (≥1 `odds_leg.status="matched"` in a keyed VPS pass) needs the VPS's own
cron to confirm; that's this item's remaining work for a future run. See
`findings/2026-07-12-odds-leg-matching-activation-q18.md`; `LOOP-QUEUE.md` Q18 → IN-PROGRESS.

---

## 2026-07-12 ~15:00 ET — OPERATING SYSTEM v3: protocol v3 + execution lane (paper tier) + queue restock + Opus handoff (Ryan-supervised, Fable's last day)

Ryan's mandate (interactive session, plan approved): refocus the loops from infra churn to
money convergence, kill the remaining babysitting, scale up, and build the paper harness NOW
(funded Kalshi account + trading key exist for an eventual, hard-gated live pilot). A
three-agent audit + firsthand review found: the queue had structurally starved (every item
DONE/DEAD/BLOCKED; ideas only ever arrived from Ryan's interactive sessions), the pipeline
ended at "verdict" with 0% execution plumbing by design, and the alive set had collapsed to
S17 + slow gates after S6/S10's verifier-confirmed deaths (07-11/12).

**What changed (all in this commit):**
- **Protocol v3** (`LOOP-QUEUE.md`): idle-run policy (sweep-only is no longer a valid run
  outcome — idle runs convert UNENFORCED lessons, prep gated probes, deep-dive tape quality,
  or prep idea-gen); two-agent verdict rule codified (producer + independent `verifier`
  confirmation before any registry flip — redundancy replaces Fable-class oversight);
  step 9 paper sub-pass; research loop cadence 5h→3h; new nightly Opus `kalshi-edge-hunter`
  leg (thinking seat: adversarial review, Q21 idea-gen, probe-prep, daily brief). Desired
  routine state is now version-controlled in `ops/ROUTINES.md` (drift-checkable).
- **Execution lane opened** (`CLAUDE.md` + Stop-rules amendment): three tiers under
  `execution/` — paper (cloud-runnable, pure tape simulation, no network), demo (VPS/local,
  unbuilt), live (per-strategy LIVE-AUTH.md signed by Ryan in person + bankroll cap + kill
  switch + credentials that never enter cloud sandboxes). Graduation bar: real-ask CI > 0
  AND ≥14 days consistent shadow-paper track record AND Ryan's signature.
- **Paper spine built** (collector-engineer agent, 58 new tests, 578 total green,
  invariants green): `execution/{schema,limits,fill_models,paper_broker,strategy_api}.py`.
  Fills carry `fill_model` + `price_source_tag` (synthetic fills rejected at the type
  boundary); ledger = append-only JSONL under `paper/`, deterministic replay verified;
  MTM at real bid with exit fees reported separately; `SHADOW_REGISTRY` empty until
  Q13/Q19/Q20 emit parameters. Live smoke over real 07-11 depth tape filled 5 contracts
  taker_depth end-to-end (ledger line produced then removed — smoke, not a real shadow).
- **Two new invariants** (+9 tests): `order_endpoints_confined` (order/auth endpoint
  markers only in the unbuilt `execution/kalshi_client.py`; documented exemption:
  `scripts/kalshi_sign.py`, the KB's offline signing repro) and `risk_caps_sanctioned`
  (MAX_* caps bound only in `execution/limits.py`).
- **Queue restocked** (Q17 reserved for retro PR #46; Q18–Q22 filed): Q18 odds-leg matching
  activation (KEY IS LIVE BUT 100% UNMATCHED — 7,476 unmatched VPS attempts over 07-11/12,
  quota burning, PR #4's matching never landed; TIME-SENSITIVE), Q19 S17 burst-event
  studies (CPI 7/14, FOMC 7/29 — prep eligible now), Q20 BTC fine-ladder overround anatomy
  (the +$9.27 flag, feeds S14-crypto), Q21 standing idea-generation round (S19+, verifier-
  gated, replenishment trigger <2 eligible items), Q22 shadow wiring (spine DONE this
  commit; wiring blocked on parameter blocks).
- **Agent roster migrated** (`.claude/agents/`): research-lead `fable`→`opus` (Fable
  retired today); worker charters amended for the paper-tier carve-out.

**Lesson-candidates from the spine build** (for the next kb-distiller pass): (1) the paper
ledger legitimately uses `real_bid`/`stale_no_bid` tags — an explicit JSONL-only extension
of L24's tape namespace; document before any paper→DB loader exists. (2) A maker paper-P&L
readout inherits s13's `optimistic_fill`/`no_queue_model` caveats AND L30's 1¢ maker-fee
floor — paper verdicts must filter on `fill_model`+`caveats`, never read the net number
alone. (3) `git stash` mid-gate in a shared working tree can revert an in-flight amendment
and flip gates transiently — scan new paths instead.

**Still open for Ryan:** merge or close PR #46 (retro; its Q17 already answered by #47/L38);
routine updates per `ops/ROUTINES.md` (Chrome MCP was disconnected — either open Chrome for
a click-through or paste the three deltas); optional branch-delete scope for the cloud app.

## 2026-07-12 (later run) — Stranded-tape sweep (2,632 lines) + L38: sweep-size growth diagnosed (not a real problem)

- **Step 0a passed.** The 5 most-recently-merged PRs (#45, #44, #43, #42, #41) are all
  reachable from `origin/main` (`git log origin/main` shows their squash commits directly).
  `kb/00-LOG.md`'s newest entry and the newest `tape/*/dt=*` file are both 2026-07-12 (0-day
  gap). `main` not rewound — an initial `git fetch origin main` reported "forced update",
  traced to this session's shallow clone catching up, not a real rewrite (local HEAD already
  equaled `origin/main`'s tip both before and after). Open PRs: #4 (Q1 odds-api leg, still
  claimed, still draft, now **10 days old** awaiting `ODDS_API_KEY` — flagged `Priority: high`
  again) and **#46** (this week's retro, docs-only `LOOP-QUEUE.md` proposal — left untouched
  per its own "never self-merged" charter; not claiming any numbered queue item, so no
  conflict with this run's claim-check).
- **Step 0b stranded-tape sweep (2,632 lines).** `git reset --hard origin/main` first. Of the
  remote's ~102 `tape/hourly-*` branches, 4 postdated PR #45's sweep cutoff and were >30min
  old: `tape/hourly-202607121155Z`, `tape/hourly-20260712T1126Z`,
  `tape/hourly-202607121356Z`, `tape/hourly-20260712T1256Z`. Union-diffed all 4 against
  `main`'s current per-day tape: `crypto_hourly` +8, `orderbook_depth` +1,958,
  `polymarket_macro_pairs` +60, `polymarket_pairs` +16, `sports_pairs` +590 — 2,632 lines
  total, all JSON-validated, 0 exact duplicates. `tape/hourly-20260712T1459Z` skipped (~10min
  old, below the 30-min freshness rule). Branch-delete not attempted (documented permission
  boundary).
- **Milestone: no numbered queue item was eligible** (Q1 claimed by PR #4; Q7/Q9/Q16 DONE;
  Q13 still BLOCKED — `tape/sports_pairs/` has 9 valid canonical `.jsonl` days, needs ≥10,
  eligible ~07-13; Q14/Q15 still data-adequacy BLOCKED). The lessons ledger's mechanical
  helper-conversion chain (L27/L28/L32/L7 → L33/L34/L35/L36) is now fully closed — nothing
  further to convert without an actual future probe. Instead of re-running S17's lead-lag
  probe on an unchanged data window (no FOMC/CPI shock has landed since last run, so it would
  reproduce the same noise-floor result), drew on a real unresolved question the 2026-07-12
  weekly retro flagged (open, unmerged PR #46): the step-0b sweep's line count has looked like
  it's climbing (1,936→872→873→1,708, now 2,632) with nobody diagnosing why.
- **Diagnosis (via the `tape-auditor` subagent, read-only).** Verdict: **not a real
  problem.** The full chronological sweep-size series — 2,076→223→1,936→873→872→1,708→2,632
  — is noisy and non-monotone (min 223, max 2,632); the retro's 4-sweep window looked like a
  climb only because it started at a local trough (2,076 landed a full day before, from #39).
  Dominant driver: `orderbook_depth` runs a flat ~1,100–1,280 lines/hour (not growing — ticker
  discovery is bounded) but is 3–4x every other family's combined hourly volume, so whether a
  sweep window catches 0/1/2 orderbook_depth passes alone swings the total ±1,200–2,400 lines;
  this run's own `orderbook_depth +1,958` (≈1.6 passes) is 74% of the 2,632. Secondary: sweep-gap
  irregularity (4.0–6.4h between research-loop firings) adds noise on top. Ruled out: a rising
  cloud-leg fallback rate (structural ~100% per the 2026-07-03 finding, and daily new-branch
  counts are flat once the 07-07 orderbook_depth-onboarding spike is excluded). Flagged in
  passing, not investigated further: zero `tape/hourly-*` branches exist for 2026-07-09 — a
  full-day gap worth a separate coverage check sometime. See
  `findings/2026-07-12-stranded-tape-sweep-growth-diagnosis.md`. Recorded **L38** in
  `kb/lessons/00-lessons.md`: don't read the aggregate lines-swept total as a health metric;
  track it per-family if it's ever automated, so orderbook_depth's chunkiness doesn't mask a
  real drift elsewhere. No code changes; 507 tests unchanged, `invariants --full` green (only
  the two expected non-gating advisories).

---

## 2026-07-12 — Stranded-tape sweep (1,708 lines) + Q12/S17 lead-lag first cut

- **Step 0a passed.** The 5 most-recently-merged PRs (#44, #43, #42, #41, #40)
  are all reachable from `origin/main`. `kb/00-LOG.md`'s newest entry and the
  newest `tape/*/dt=*` file are both 2026-07-12 (0-day gap). `main` not
  rewound — an initial `git fetch origin main` reported "forced update";
  traced to this session's shallow clone (`--depth 50`) truncating the
  commit graph before the fetch, not a real history rewrite (confirmed via
  `git fetch --unshallow` + re-checked ancestry, and independently via the
  merged-PR reachability + log/tape date-parity checks). Only open PR is #4
  (Q1 odds-api leg), unrelated, now **9 days old** awaiting `ODDS_API_KEY` —
  past the 5-day escalation mark, flagged `Priority: high` in this run's
  phone note again.
- **Step 0b stranded-tape sweep (1,708 lines).** `git reset --hard
  origin/main` first. Of 97 `tape/hourly-*` branches, two postdated PR #44's
  sweep cutoff and were well past 30min old: `tape/hourly-20260712T0458Z`
  and `tape/hourly-202607120557Z`. Content-diffed against `main`'s current
  tape: `crypto_hourly` +4, `orderbook_depth` +1,349,
  `polymarket_macro_pairs` +30, `polymarket_pairs` +8, `sports_pairs` +317 —
  1,708 lines total, all JSON-validated, 0 exact duplicates. Committed and
  pushed standalone so `main` was current before the milestone landed.
  Branch-delete not attempted (documented permission boundary).
- **Milestone: no numbered queue item was eligible.** Q1 still claimed by
  open PR #4; Q7/Q9/Q16 DONE; Q13 still BLOCKED (`tape/sports_pairs/` has 9
  valid canonical `.jsonl` days, needs ≥10, eligible ~07-13); Q14/Q15 still
  data-adequacy BLOCKED. The lessons ledger's own standing UNENFORCED
  candidates were checked first (L23's "empty ≠ drop" generalization: audited
  `sports_pairs.py`/`crypto_hourly.py`/`polymarket_pairs.py` — all already
  use honest None-propagation for a genuinely-missing quote and DROP only on
  a real fetch/parse failure, so there is no live gap to close there, unlike
  L22's case; L27/L28/L32's own candidates are already importable in
  `core/bootstrap.py` and wait on an actual future probe, not further loop
  work). Instead drew on **Q12/S17's own remaining-work note** — genuine
  strategy-registry progress instead of another infra-only lesson closure.
- **S17 lead-lag first cut (via `edge-prober`).** Built
  `scripts/s17_leadlag_probe.py`, the S17 analog of `scripts/s9_leadlag_
  probe.py`, over `tape/polymarket_macro_pairs/` (Fed-decision leg — both
  Kalshi `yes_ask` and Polymarket `best_ask` are genuine `real_ask`, an
  apples-to-apples pair exactly like S9's WC-round comparison). Ran read-only
  over ~6 accumulated days (2026-07-06→07-12): **2,805 records, 187 distinct
  captures, 15 (meeting, bucket) pairs** (Jul/Sep/Oct 2026 meetings × 5
  buckets). Pooled panel cross-correlation of consecutive-capture deltas:
  contemporaneous ρ=+0.154 (n=2,789), kalshi-leads ρ=−0.003,
  polymarket-leads ρ=−0.028 (n=2,774 each); 215 ticks ≥1¢ on either venue.
  **0 FOMC resolve/roll-off (shock-proxy) events fell inside the window** —
  none of Kalshi's listed meetings have occurred yet, so every observed tick
  is book noise, the same data-adequacy gap S9 hit before its real
  round-transition events landed. Reported honestly as a descriptive
  noise-floor characterization, **not a verdict** (no CI, no DEAD/ALIVE
  call — L28's discipline: don't build verdict machinery before the signal
  is even observable). The CPI leg (`tape/polymarket_cpi_pairs/`, 154
  records) is `synthetic` on the Kalshi side (a derived cumulative-ladder
  difference) and was deliberately excluded from the real-ask correlation
  per Hard Rule #3 — counted for provenance only, not pooled in. `kb/
  strategies/00-index.md` S17 note updated (dated append, stays
  `data-collecting`). Full write-up:
  `findings/2026-07-12-polymarket-macro-leadlag-s17-firstcut.md`.
- **Gates:** 507 tests green (481 prior + 26 new). `python
  scripts/invariants.py --full` green — one false-positive
  `no_yes_ask_arithmetic` hit on a test docstring's prose ("kalshi.yes_ask /
  polymarket.best_ask", not real arithmetic) fixed by rewording to "and"
  before commit.

**Next:** re-run `scripts/s17_leadlag_probe.py` once a real FOMC decision
(nearest: July 2026 meeting) or CPI print lands inside the collected window
— only then does the lead-lag thesis have a real shock to test, same
resolution path S9 eventually took. Q13 (S14 ladder-underwriting fill-sim)
becomes eligible ~2026-07-13 once a 10th valid `tape/sports_pairs/` day
lands.

---

## 2026-07-12 — Stranded-tape sweep (872 lines) + L36: strike-spacing-from-ladder helper built

- **Step 0a passed.** The 5 most-recently-merged PRs (#43, #42, #41, #40, #39)
  are all directly reachable from `origin/main` (#43's squash commit `b3b76c4`
  visible in the local log). `kb/00-LOG.md`'s newest entry and the newest
  `tape/*/dt=*` file are both 2026-07-12 (0-day gap). `main` not rewound — an
  early `git fetch origin main` reporting "forced update" was traced to this
  session's shallow-clone ref catching up to a stale container-start snapshot,
  not a real rewrite (HEAD `147cffe` was unchanged before and after the
  fetch). Only open PR is #4 (Q1 odds-api leg), unrelated, now ~9 days old
  awaiting `ODDS_API_KEY` — past the 5-day escalation mark, flagged
  `Priority: high` in this run's phone note.
- **Step 0b stranded-tape sweep (872 lines).** `git reset --hard origin/main`
  first. Of 96 `tape/hourly-*` branches, two postdated the last sweep's cutoff
  and were well past 30min old: `tape/hourly-202607120401Z` and
  `tape/hourly-20260712T0258Z`. Content-diffed (`git show <ref>:<path>`)
  against `main`'s current tape: `crypto_hourly` +2, `orderbook_depth` +687,
  `polymarket_macro_pairs` +15, `polymarket_pairs` +7, `sports_pairs` +161 —
  872 lines total, all JSON-validated, 0 exact duplicates. A third branch
  (`tape/hourly-20260712T0458Z`) was skipped — its commit was only ~5min old,
  below the 30min freshness threshold. Branch-delete not attempted
  (documented permission boundary).
- **Milestone: no numbered queue item was eligible.** Q1 still claimed by
  open PR #4; Q7/Q16 DONE; Q13 still BLOCKED (`tape/sports_pairs/` has 9 valid
  canonical `.jsonl` days — 03,04,05,06,07,08,10,11,12 — needs ≥10, eligible
  ~07-13); Q14/Q15 still data-adequacy BLOCKED. Drew from the lessons
  ledger's own standing UNENFORCED queue again (same pattern as L25→L29,
  L33→L34, L32→L35): **L7** ("never hardcode a bracket/strike width — derive
  spacing from the ladder itself," filed 2026-07-04) had stayed UNENFORCED
  the longest of any remaining live row — its actual fix in
  `scripts/s8_basis_probe.py` only swapped a single fixed-$100 half-band
  check for a 2-symbol hardcoded dict (`{"BTC": 100.0, "ETH": 20.0}`), still
  a guess rather than a value read off the ladder's own strikes, and no
  importable helper existed for what the lesson's own wording asked for.
- **`core/pricing.py`**: new `infer_strike_spacing(strikes)` — dedupes and
  sorts the ladder's own strike values, returns the MEDIAN consecutive gap
  (robust to one missing or duplicated member, e.g. a thin/stale far strike),
  `None` below 2 distinct strikes. 5 new tests in
  `tests/test_substrate_primitives.py` (BTC-like $100 ladder, ETH-like $20
  ladder, one-gap-doubled robustness check, order/duplicate insensitivity,
  <2-strike None cases).
- **`.claude/agents/edge-prober.md`**: house style now names
  `core.pricing.infer_strike_spacing` alongside the existing L27/L28/L32
  bootstrap helpers, for any probe/collector that needs a ladder's own
  spacing instead of a hardcoded per-symbol guess.
- **`kb/lessons/00-lessons.md`**: appended **L36** (generalizes L7; L7 itself
  stays UNENFORCED as a ledger row per the append-only rule).
- Does not retrofit S8's already-verdicted probe (DEAD, Q5, 2026-07-04) —
  that verdict stands as-is; this is infra for the next probe/collector that
  needs to read a bracket ladder's spacing off real data.

## Gates

- 481 tests green (476 prior + 5 new).
- `python scripts/invariants.py --full` green (only the two expected
  non-gating advisories: L20 stranded-tape, L29 tape-dir-shape).

Research/tape/docs only — no order or execution code, no credential
handling.

---

## 2026-07-12 — Stranded-tape sweep (873 lines) + L35: frozen-pair dual-cut bracketing helper built

- **Step 0a passed.** The 5 most-recently-merged PRs visible in local history
  (#42, #41, #40, #39, #38) — #38 falls outside this session's shallow clone
  depth but was independently confirmed reachable by a prior run, and #42/#41/
  #40/#39 are all directly visible in `origin/main`'s log. `kb/00-LOG.md`'s
  newest entry and the newest `tape/*/dt=*` file are both 2026-07-11 (0-day
  gap, pre-sweep). `main` not rewound. Only open PR is #4 (Q1 odds-api leg,
  unrelated, still a draft, now ~9 days old awaiting `ODDS_API_KEY` — past the
  adopted 5-day escalation mark, flagged `Priority: high` in this run's phone
  note).
- **Step 0b stranded-tape sweep (873 lines).** `git reset --hard origin/main`
  first. Of 93 `tape/hourly-*`/`-corrected-`/`-followup-`/`-amended-` branches,
  two postdated the last sweep's cutoff (`tape/hourly-20260711T1501Z`/`1806Z`)
  and were well past 30min old: `20260711T205500Z` and `20260711T2156Z`.
  Content-diffed (line-set union, not commit ancestry — this session's shallow
  clone has no merge-base with these branches, so `git show <branch>:<path>`
  was used to read each branch's file content directly) against `main`'s
  current tape: `crypto_hourly` +4, `orderbook_depth` +466,
  `polymarket_macro_pairs` +30, `polymarket_pairs` +20, `sports_pairs` +353 —
  873 lines total, all JSON-validated, 0 exact duplicates against `main`.
  Branch-delete not attempted (documented permission boundary).
- **Milestone: no numbered queue item was eligible.** Q1 still claimed by open
  PR #4; Q7/Q16 DONE; Q13 still BLOCKED (`tape/sports_pairs/` has 9 valid
  canonical `.jsonl` days — 03,04,05,06,07,08,10,11,12 — needs ≥10, eligible
  ~07-13); Q14/Q15 still data-adequacy BLOCKED. Drew from the lessons ledger's
  own standing UNENFORCED queue again (same pattern as L25→L29 and L33→L34):
  L34 closed L27/L28's "probe-precedent encodes it" gap but left **L32**
  (frozen-pair no-fill precheck + dual-cut bracketing, from S6's first-cut)
  as the one still-open UNENFORCED candidate in that lineage — `core/bootstrap.py`
  had no importable counterpart for it, so a future maker/spread-style probe
  built over repeated snapshots would still hand-roll the frozen-vs-movement
  split from scratch.
- **Built `core/bootstrap.py::bracket_by_movement(frozen_flags, values)`** —
  takes the caller's already-computed per-observation frozen flags (L6-style:
  it never inspects raw book fields itself, "frozen" stays a per-probe
  judgment call) and returns the frozen-inclusive value list, the
  movement-conditioned value list (frozen entries removed), and the frozen
  fraction. 6 new tests in `tests/test_bootstrap.py` (empty input honesty,
  all/none/partial frozen, movement-conditioned exclusion, length-mismatch
  raises). Does not retrofit S6's already-verdicted probe — that verdict
  stands as-is; this is for the next snapshot-based probe that needs the
  frozen/movement split (S6-successor or S11, whenever its own data blocker
  clears).
- **`.claude/agents/edge-prober.md` house style updated** to name
  `core.bootstrap.bracket_by_movement` alongside the L27/L28 helpers, for any
  probe built over repeated same-entity snapshots rather than one-shot trade
  outcomes.
- Recorded **L35** in `kb/lessons/00-lessons.md` (generalizes L32; L32 itself
  stays UNENFORCED as a ledger row per the append-only rule).
- Gates: 476 tests green (470 prior + 6 new), `python scripts/invariants.py
  --full` green (only the two expected non-gating advisories: L20
  stranded-tape and L29 tape-dir-shape).

## 2026-07-11 (later run) — Stranded-tape sweep (1,936 lines) + L34: bootstrap-helper protocol encoded into edge-prober charter

- **Step 0a passed.** The 3 most-recently-merged PRs visible in local history
  (#41, #40, #39) are all reachable from `origin/main` (local branch head equals
  `origin/main` tip, `ade6160`); `kb/00-LOG.md`'s newest entry and the newest
  `tape/*/dt=*` file are both 2026-07-11 (0-day gap). `main` not rewound. Only
  open PR is #4 (Q1 odds-api leg, unrelated, unmerged, ~8 days old — still
  awaiting `ODDS_API_KEY`).
- **Step 0b stranded-tape sweep (1,936 lines).** Of the 91 `tape/hourly-*`
  branches, two postdated the last sweep's cutoff (`tape/hourly-20260711T1256Z`)
  and were >30min old: `20260711T1501Z` and `20260711T1806Z`. Content-diffed
  (line-set, not commit ancestry) each against `origin/main` per family, then
  unioned the two branches' missing lines: `crypto_hourly` +4, `orderbook_depth`
  +1,507, `polymarket_macro_pairs` +30, `polymarket_pairs` +20, `sports_pairs`
  +375 — 1,936 lines total, all JSON-validated, 0 exact duplicates against
  `main`. Branch-delete not attempted (documented permission boundary).
- **Milestone: no numbered queue item was eligible.** Q1 still claimed by open
  PR #4; Q7/Q16 DONE; Q13 still BLOCKED (`tape/sports_pairs/` has 8 valid
  canonical days — 03,04,05,06,07,08,10,11 — needs ≥10, eligible ~07-13);
  Q14/Q15 still data-adequacy BLOCKED. Drew from the lessons ledger's own
  standing UNENFORCED queue again: L33 (prior run) built `core/bootstrap.py`
  but explicitly left undone the "probe-precedent encodes it" half of L27/L28's
  own candidate wording — the helper existed, but nothing yet told a future
  probe to reach for it instead of hand-rolling a new resample loop.
- **Closed that gap in `.claude/agents/edge-prober.md`** — the one file every
  probe milestone is required to read before writing code. Its house-style
  section now names `core.bootstrap.block_bootstrap` /
  `clears_tick_magnitude` / `floor_pinned_fraction` explicitly, and the
  three-outcome verdict rule is sharpened so a CI>0 that fails the
  tick-magnitude gate is counted as DEAD, not left as a vague "worth
  flagging." Docs-only — no probe re-run, no verdict re-opened, no source
  code touched. New lesson **L34** filed in `kb/lessons/00-lessons.md`
  recording the closure; L27/L28 stay individually UNENFORCED as ledger rows
  (append-only) since the ledger's own rule is ledger rows never get rewritten,
  but the candidate they described is now live in the charter — full
  resolution still waits on an actual probe using it. 470 tests unchanged
  (docs-only commit), `invariants.py --full` green (only the two pre-existing
  non-gating advisories: L20 stranded-tape, L29 tape-dir-shape).
- LOOP-QUEUE.md: Log-of-runs line appended. No Q-item status line changed
  (this milestone isn't tied to a specific numbered item).

## 2026-07-11 (later run) — Stranded-tape sweep (223 lines) + L33: shared block-bootstrap helper

- **Step 0a passed.** The 5 most-recently-merged PRs (#40, #39, #38, #37, #36) are all
  reachable from `origin/main`; `kb/00-LOG.md`'s newest entry and the newest
  `tape/*/dt=*` file are both 2026-07-11 (0-day gap). `main` not rewound. (The initial
  shallow clone's stored `origin/main@{1}` ref looked like a rewind under
  `merge-base --is-ancestor` — that was the shallow-history boundary, not a real rewind;
  confirmed via the merged-PR reachability check + the log/tape date parity, not the
  git-ancestry heuristic alone.)
- **Step 0b stranded-tape sweep (223 lines).** `git reset --hard origin/main` first.
  Of the `tape/hourly-*` branches, one (`tape/hourly-20260711T1256Z`) was >30min old
  and not yet covered by PR #40's sweep; its content-diff against `main` (line-set,
  not commit ancestry) found real gaps in today's files despite `main` already having
  *more total lines* per file (a later, different pass) — `crypto_hourly` (+2),
  `polymarket_macro_pairs` (+15), `polymarket_pairs` (+10), `sports_pairs` (+196);
  `orderbook_depth` had 0 missing. All lines JSON-validated, 0 exact duplicates.
  Branch-delete not attempted (documented permission boundary).
- **Milestone: no numbered queue item was eligible.** Q1 still claimed by open PR #4
  (odds-api key, now 8 days old); Q7/Q16 DONE; Q13 still BLOCKED (`tape/sports_pairs/`
  has 8 valid canonical days — 03,04,05,06,07,08,10,11 — needs ≥10, eligible ~07-13);
  Q14/Q15 still data-adequacy BLOCKED. Drew from the lessons ledger's own standing
  UNENFORCED queue instead (same pattern as L25→L29): **L27** (magnitude-vs-tick CI
  gate) and **L28** (floor-pinned-fraction precheck) were both filed as "likely
  terminal as protocol... once a probe-precedent encodes it," but no probe-precedent
  actually existed yet — every bootstrap-using script (`s6_maker_firstcut.py`,
  `s10_reachability_probe.py`, `s7c_sports_clv_bootstrap.py`) still hand-rolls its own
  block-bootstrap loop from scratch.
- **Built `core/bootstrap.py`:** `block_bootstrap` (generic by-unit block resample —
  takes an already-grouped-by-unit mapping, L6-compliant, never guesses the grouping
  key itself), `clears_tick_magnitude` (L27's sign-*and*-magnitude gate — S10's own
  near-miss CI `[+0.000000, +0.000024]` correctly fails it against a 1¢ tick),
  `floor_pinned_fraction` (L28's cheap-before-expensive floor-observability precheck).
  17 new offline tests in `tests/test_bootstrap.py` (empty-input honesty, determinism
  given a seed, CI-width sanity, both gate functions against S6/S10's own real numbers).
  Does NOT retrofit the already-verdicted S6/S10 probes — those verdicts stand; this is
  infra for the next probe that needs a bootstrap (S11/S14/S16/S18, once their own data
  blockers clear). New lesson **L33** filed in `kb/lessons/00-lessons.md` recording the
  compounding. 470 tests green (453 prior + 17 new), `invariants.py --full` green (only
  the two pre-existing non-gating advisories: L20 stranded-tape, L29 tape-dir-shape).
- LOOP-QUEUE.md: Log-of-runs line appended. No Q-item status line changed (this
  milestone isn't tied to a specific numbered item).

## 2026-07-11 — S6 milestone: inventory-aware market-making (earn-the-spread-as-maker) → DEAD (first cut, verifier-CONFIRMED)

- **Drawn from the registry's own priority order, not a numbered Q-item.** The numbered queue
  had drained to externally-blocked items (Q1 claimed by PR #4 awaiting `ODDS_API_KEY`;
  Q13/Q14/Q15 data-adequacy BLOCKED), so this milestone came from the standing registry: S6 was
  the topmost `data-collecting` candidate with enough accumulated tape to test.
- **The probe.** `scripts/s6_maker_firstcut.py` (read-only, 15 offline tests) built a
  quote-displacement proxy over 4 accumulated days of `tape/orderbook_depth/` (2026-07-07, 07-08,
  07-10, 07-11; ~58,583 records → 36,738 consecutive two-sided pairs ≤90 min apart). Per ticker
  seen in two consecutive hourly captures: book the capture-1 quoted half-spread as maker income
  if filled, charge the full hour's mid displacement as adverse selection, net of the maker fee
  from `core.pricing.fee_per_contract` (never hand-rolled — L18). Honest scope stated up front:
  hourly snapshots cannot observe a real fill, queue position, or message-level adverse selection,
  so this can only show the gate is unmeetable on the realistic population, not measure a live
  edge. Bootstrap unit = the **ticker** (pairs within one game/bracket are correlated draws — L6).
- **L28 precheck first:** 25,618/36,738 = **69.7%** of consecutive pairs are frozen (BBO
  unchanged) — correctly booked as $0 no-fill income, not phantom spread capture.
- **Verdict: DEAD (first cut).** By-ticker block-bootstrap (10,000 resamples, seed 42) of net
  maker P&L is **strictly < 0** on every economically-realistic two-sided cut: ≤2¢ mean
  −$0.01120, ≤5¢ −$0.00619, ≤10¢ (primary, frozen-inclusive, max-generous) −$0.00195 95% CI
  [−$0.00297,−$0.00094], and the honest movement-conditioned ≤10¢ cut −$0.02010 CI
  [−$0.02271,−$0.01759]. The only population with CI>0 is the **>30¢ wide-wing artifact**
  (+$0.339/contract, 99.9% "profitable") — a nominal, not maker-capturable, spread on far/one-
  sided brackets (wide *because* one side is empty); the naive "ALL two-sided" +$0.06928 mean was
  entirely this wing. **Structural killer:** the maker fee is a **flat 1¢/contract** at every
  interior price (`ceil(0.0175·P·(1−P)·100)/100 = 0.01` for all `0<P<1`), which alone consumes
  the modal Kalshi book's 1–2¢ two-sided spread before adverse selection is even charged — the
  same fee-floor mechanism that killed S13. More days of the *same* hourly-cadence tape cannot
  fix a structural cap.
- **Verifier CONFIRMED** (not merely plausible). Independently reproduced every number and swept
  ≤15/20/25/30¢ trying to find an alive population — the only frozen-inclusive CI>0 (≤30¢,
  +$0.00229, a quarter-cent) fails L27's magnitude-vs-tick gate and is itself wing-driven; under
  the movement-conditioned cut every threshold is strictly negative. **Out of scope / NOT
  falsified:** the *selective* maker (S11) — quote only wide-enough, low-toxicity books with an
  external fair-value anchor and a real fill-sim; S6's naive "quote everything at the BBO" is
  what's dead.
- **Compounded:** `kb/strategies/00-index.md` S6 flipped `data-collecting → dead ✗` (row + gate
  cell + a third dated verdict note + the "0 proven edges" running tally: S1/S5/S7/S8/S9/S13/S10/S6
  now all decided at real asks, none live). Three lessons appended to `kb/lessons/00-lessons.md`:
  **L30** (the maker fee is a flat 1¢/contract at every interior price — sharpens L5/L18's "4×
  cheaper" into a hard floor; enforcement **test**, pinned by the probe's existing value-sweep
  test — a numeric property of the fee function, not a static-text invariant), **L31** (a >30¢
  spread on a far/one-sided bracket is a nominal, not maker-capturable, spread — generalizes
  L12/L26's floor-artifact caution to the spread-capture direction; **ledger-only**, venue
  microstructure + per-probe methodology), **L32** (a frozen consecutive pair is a no-fill, not
  free income — report the frozen fraction as an L28 precheck and bracket the verdict with both
  frozen-inclusive and movement-conditioned cuts; **UNENFORCED**, per-probe methodology, likely
  terminal as protocol). Finding: `findings/2026-07-11-mm-spread-s6-firstcut.md`.
- Gates: `pytest -q` green, `python scripts/invariants.py --full` green (only the two pre-existing
  non-gating advisories: L20 stranded-tape and the L29 tape-dir-shape warning). Docs-only change
  (kb/ only — the probe, its tests, and the finding were already committed).

## 2026-07-11 05:xx UTC — research loop: stranded-tape sweep (1,551 lines) + L25→L29 (tape dir-shape invariant built)

Step 0a history-integrity check passed: the 5 most-recently-merged PRs (#37, #36, #18, #35,
#33) are all reachable from `origin/main` (confirmed via commit-message search post
squash-merge, since PR head SHAs are never ancestors under this repo's convention);
`kb/00-LOG.md`'s newest entry and the newest `tape/*/dt=*` file are both 2026-07-11 (0-day
gap). `main` is not rewound. Open PRs: only #4 (Q1 odds-api leg), still claimed, now ~8 days
old awaiting `ODDS_API_KEY` — past PR #18's adopted 5-day escalation mark, flagged
`Priority: high` again in this run's phone note.

**Step 0b stranded-tape sweep.** `git reset --hard origin/main` first (per the adopted
retro amendment). Of 86 `tape/hourly-*`/`-amended-`/`-corrected-`/`-followup-` branches, the
3 most recent since the last sweep (`20260711T000050Z`, `20260711T0254Z`, `20260711T0356Z`,
all >30min old) carried real line-set gaps against `main`; `20260711T0154Z` diffed to zero
missing lines (already reconciled — its content landed on `main` directly via the same-
timestamp commit `308d9fc`). Union-appended **1,551 lines** `main` was missing —
`crypto_hourly` +6 (2+4 across the two affected days), `orderbook_depth` +827,
`polymarket_macro_pairs` +45, `polymarket_pairs` +30, `sports_pairs` +643 — every line
JSON-validated, 0 exact duplicates (confirmed via a `sort`+`sort -u` line-count parity check
per target file post-append). Branch-delete not attempted (documented permission boundary,
per the adopted amendment).

**Milestone: converted lesson L25 into a live invariant (no numbered queue item was
eligible — Q13 still BLOCKED at 8/10 valid days of `tape/sports_pairs/`, Q14/Q15 still
data-adequacy BLOCKED, Q1 still claimed by PR #4).** Built
`scripts/invariants.py::_tape_dir_shape_issues()` / `tape_dir_shape_warning()`, the exact
enforcement L25 asked for: a non-gating advisory (same pattern as L20's stranded-tape
warning) that scans every `tape/<family>/dt=<date>` path and flags any that is a
**directory** instead of the canonical `.jsonl` file — the shape of bug that let the
2026-07-08 main-rewind's regression silently miscount a day-count gate. Wired into
`--full`'s existing warning block. Live-validated against the real committed tree: it
correctly flags the 4 stray directories that regression left behind and were never cleaned
up (`crypto_hourly/dt=2026-07-10`, `sports_pairs/dt=2026-07-02`, `sports_pairs/dt=2026-07-09`,
`sports_pairs/dt=2026-07-10`) — confirming both that the check works on real data and that
those directories are still sitting there (cleanup/reprocessing is separate follow-up work,
flagged, not done here). 6 new tests (438 total, 432 prior + 6 new). Recorded as **L29**
(supersedes L25) in `kb/lessons/00-lessons.md`.

Gates: 438 tests green, `python scripts/invariants.py --full` green (only the two
non-gating advisories: stranded-tape L20 and the new L25/L29 dir-shape warning, both
expected and harmless). No source-code milestone changed a queue Status line; Q13 day-count
re-confirmed off disk (8 valid canonical days: 03,04,05,06,07,08,10,11 — not yet 10).

## 2026-07-11 00:27 UTC — Q7 milestone: S10 crypto-hourly reachability decay → STRUCTURAL DEAD (verifier-CONFIRMED)

- **Q7 became eligible this run.** The `crypto_hourly` tape crossed **7 valid canonical days**
  (2026-07-03..08 plus a reprocessed 07-10 `.jsonl`) — the L25 stray `dt=2026-07-10/`
  directory-of-blobs day correctly excluded via a `*.jsonl` glob + `is_file` guard, so the
  day-count is honest this time.
- **The probe.** `scripts/s10_reachability_probe.py` (read-only, `+16` offline tests) tested
  S10's thesis (far range-brackets stay priced above their remaining-time reachability late in
  the hour → a taker could fade the rich tail). No continuous intra-hour tape exists, so it used
  the only within-hour time variation available — the two collectors (cloud + VPS) hitting the
  same hourly group at different offsets (~40 min vs ~5 min pre-close), an EARLY vs LATE capture
  — and used the realized `broker_truth` settlement as ground truth instead of fabricating a
  hitting-probability model on thin data. Bootstrap unit = the **hour** (brackets within an hour
  are correlated draws — L6), entry prices `real_ask`, settlement `broker_truth`.
- **Verdict: DEAD, structural — not a marginal miss.** Two independent walls, both mechanical:
  (1) the decay the thesis needs is not observable — far brackets were already 1¢-YES-floor-pinned
  ~40 min before close (mean early→late Δ`yes_ask` +0.00014); (2) the taker trade has no fillable
  price — a floor-pinned YES (`yes_bid=0`) mirrors into a **\$1.00 NO ask**, so only 4/18,992 far
  obs (0.02%, 3 of them from a single hour) had any `no_ask<\$1` room, and `fee_per_contract(\$1.00)=0`
  makes the ideal floored trade net exactly \$0. Block-bootstrap-by-hour (n=164 hrs/18,992 obs,
  10,000 resamples): mean **+\$0.000008**, 95% CI **[+\$0.000000, +\$0.000024]** — lower bound a
  floating-point 0, magnitude 3 orders below the 1¢ tick. No threshold (0.01→0.10) clears zero.
  Same cheap-kill family as S8's ρ-guard; more data cannot fix a mechanically-capped trade.
- **Verifier CONFIRMED** (not merely plausible). One caveat that does not move the verdict:
  in-sample 0/18,992 far brackets actually hit, so the point estimate is slightly
  survivorship-flavored — but the writeup already treats +\$0.000008 as rounding residue, and the
  kill is the tick-mirror mechanism, not the sample. **Out of scope / not falsified:** the MAKER
  side (rest a NO offer or sell the rich YES at the elevated ask rather than crossing to a \$1.00
  NO ask) — S6/S11 territory, needs the L2 depth tape + a fill-sim.
- **Compounded:** `kb/strategies/00-index.md` S10 flipped `idea → dead ✗` (row + verdict note +
  running-tally update). Three lessons appended to `kb/lessons/00-lessons.md`: **L26** (the 1¢
  YES tick mirrors to a \$1.00 NO ask on floor-pinned brackets ⇒ a tail-fade is structurally a
  maker trade, not a taker one — generalizes L12; enforcement **ledger-only**, venue arithmetic),
  **L27** (`fee(\$1.00)=0` is correct, but a CI dominated by ~\$1.00 legs can show a floating-point
  +0.000000 lower bound — every CI verdict needs a magnitude/economic-significance gate vs the 1¢
  tick, not just a sign check; **UNENFORCED**), **L28** (verify the artifact floor is even
  *observable* — check the early-capture floor-pinned fraction — before building a decay/CI
  pipeline; **UNENFORCED**). L27/L28 stay kb-only this milestone (scope limited to `kb/`); both
  are per-verdict/per-probe methodology gates, likely terminal as **protocol** in probe precedents
  rather than static invariants. Finding: `findings/2026-07-11-crypto-reachability-s10-firstcut.md`.
- Gates: `pytest -q` green, `python scripts/invariants.py --full` green (only the pre-existing
  non-gating stranded-tape advisory). Docs-only change.

## 2026-07-10 16:50 ET — Burst-capture legs approved + built; ntfy topic moved out of the public repo (ops, Ryan-interactive)

- **Burst captures approved.** The S9 lead-lag resolution (2026-07-06) had flagged
  sub-hourly event-window captures as a new automation class needing Ryan's sign-off;
  Ryan gave it today. Built `collection/burst_capture.py` (+15 offline unit tests, 420
  total green, `invariants --full` green): a thin loop harness over the existing
  collectors' one-pass functions (`wc`/`fed`/`cpi`/`econ`/`crypto`/`sports` families),
  `--until`/`--interval`/`--families` CLI, overrun-skips-boundaries timing, per-family
  fault isolation, honest AND-completeness. No new tape family, no schema change —
  burst lines are distinguishable by `fetch_ts` density alone. Live smoke pass (2
  crypto ticks @20:44 UTC) honestly reported `completeness FAIL` — the documented L15
  venue-side 20-UTC-hour crypto hole, not a collector fault; lines kept as real tape.
- **Five one-shot cloud triggers created** (Ryan's account, not the repo): June-CPI
  print Jul 14 12:05→13:45Z; WC semi 1 Jul 14 and semi 2 Jul 15 20:10→22:30Z; WC final
  Jul 19 20:10→22:45Z (last-ever KXWCROUND capture window); FOMC decision Jul 29
  17:40→19:45Z. Each carries a hard date guard against annual cron re-fire. Protocol
  section "Burst-capture legs" appended to `LOOP-QUEUE.md`; step 0b's sweep now also
  covers `tape/burst-*` fallback branches. Why it matters: this is exactly the data
  class whose absence made S9's lead-lag thesis untestable — S17's lead-lag question
  becomes testable on this tape.
- **ntfy topic migration (step 8(e)).** The repo went public 2026-07-10 and ntfy.sh
  topics are world-writable — the committed topic name let anyone inject priority-5
  messages into the `ntfy-watch` responder. New secret topic generated; all 5 cloud
  routine prompts updated to carry the URL privately; local sessions read
  `~/.claude/secrets/kalshi-ntfy-topic`; VPS flip to `/root/.secrets/kalshi-headless.env`
  pending (Ryan action); `config/notify.topic` stays only as the retired fallback until
  then. The new topic name is committed NOWHERE in this repo, by design.
- Worker lesson candidates (per-family completeness conventions; overrun-test
  offset-sequence pinning; fresh L15 corroboration) recorded in the builder's report —
  left for the next kb-distiller pass.

## 2026-07-10 20:xx UTC — Research loop: stranded-tape sweep (5,125 lines) + tape-format-regression finding

Step 0a history-integrity check: PASS. The 5 most-recently-merged PRs' squash/merge commits
(#18, #35, #33, #32, #31 — verified by commit-message search after unshallowing the local
clone, not by branch-head SHA, since squash-merges rewrite the commit object) are all
reachable from `origin/main`; `kb/00-LOG.md`'s newest dated entry and the newest `tape/*/dt=*`
file are both 2026-07-10 (0-day gap). `main` is not rewound.

Step 0b stranded-tape sweep: fetched + content-diffed all 80 `tape/hourly-*` branches (line-set
diff per tape file, not commit ancestry — this repo's PRs are squash-merged so a branch head's
raw SHA is never an ancestor of `main` even when fully reconciled). ~70 pre-2026-07-08 branches
were already fully reconciled (0 missing lines — the pre-reset lineage's own sweeps plus
today's PR #35 recovery already cover them). Found real gaps in 9 branches: 3 from right at/
after the 07-08T10:56Z reset event (`tape/hourly-20260708T1101Z`/`1102Z`/`1103Z`) and 6 from
today (`tape/hourly-202607100655Z` through `20260710T1656Z`). Union-appended **5,125 lines**
`main` was missing across `crypto_hourly`, `orderbook_depth`, `polymarket_macro_pairs`,
`polymarket_pairs`, and `sports_pairs` — every line JSON-validated, 0 exact duplicates
introduced (verified via `sort -u` line-count parity per file). `tape/hourly-20260710T1955Z`
(committed ~14 minutes before this check, under the 30-minute freshness rule) was left for the
next run.

**Milestone: Q7 eligibility check surfaced a real tape-format regression, not a new day of
data.** `tape/crypto_hourly/` and `tape/sports_pairs/` each had a `dt=2026-07-10` **directory**
(raw per-market Kalshi API blobs, 23 hourly passes from 2026-07-10T00:26Z–19:24Z) instead of
the canonical `dt=2026-07-10.jsonl` **file** every other day uses — caused by the post-reset
lineage's rebuilt collectors writing a different storage format, which PR #35 reconciled the
*code* for but not the *already-committed tape*. Same window: `tape/orderbook_depth/`,
`tape/polymarket_pairs/`, `tape/polymarket_macro_pairs/` have zero 07-10 entries at all (the
post-reset `hourly_pass.py` only ran 2 of the pre-reset lineage's 5 sub-passes). Confirmed
self-corrected: the first hourly pass after PR #35's merge (`tape/hourly-20260710T1955Z`,
commit `cf33e5f`, 20:01:49Z) writes the correct format across all 5 families. Q7 is still
BLOCKED — 6 valid canonical days (03–08), not the apparent 7th. Full writeup:
`findings/2026-07-10-tape-format-regression-crypto-sports.md`. New lesson: `kb/lessons/
00-lessons.md` L25 (UNENFORCED — a day-count check should verify file shape, not just path
existence). Left the ~19h of raw blobs unprocessed — reconstructing canonical records from
them needs a previous-settlement/spot pairing this run couldn't verify was captured alongside,
so reprocessing is flagged as an open decision for Ryan / a future `collector-engineer`
milestone, not attempted here.

**Also noted, not acted on:** PR #4 (Q1's odds-api leg, `worktree-q1-odds-leg`, draft, claims
Q1) has been open 7 days awaiting `ODDS_API_KEY` — still absent from the environment. No lesson
or registry candidate had a live `UNENFORCED`/`idea` row actionable this run beyond L25 above
(Q13 needs ≥10 sports_pairs days, has 9; Q14/Q15 remain externally BLOCKED, unchecked live this
run since the finding above was the day's milestone).

Gates: 401 tests green, `python scripts/invariants.py --full` green (only the pre-existing
non-gating stranded-tape advisory).

---

## 2026-07-10 — RECONCILIATION: main-branch reset discovered and repaired (local session with Ryan)

On 2026-07-08T10:56Z a push moved `origin/main` back to `6cde523` (the 2026-07-02 Q0
checkpoint), orphaning 197 commits: all of 2026-07-03→07-08 (PRs #4–#33 — the Q1–Q18
build-out, S7/S9 DEAD verdicts, S16/S18 BLOCKED verdicts, lessons ledger, phone-note
protocol). The cloud loops then unknowingly rebuilt Q1/Q2/Q3 (2026-07-09/10) and began
re-probing S7 — a strategy already declared DEAD by block-bootstrap on 2026-07-04.
Recovered the pre-reset tip (`f23a491`) via GitHub's event log and merged the post-reset
work into it. Code conflicts resolved in favor of the pre-reset lineage (5 more days of
hardening; `hourly_pass` orchestrates collectors that exist only there); post-reset tape,
`core/odds.py`+schemas, and the S7a re-probe artifacts kept. Entries below from
2026-07-09/10 describe the post-reset lineage's (duplicate) work — kept for honesty.

## 2026-07-10 15:16 UTC — Q4/S7b: built the CLV trade set; raw signal already negative, pre-bootstrap

Topmost eligible queue item: **Q4** (S7 historical CLV backtest), `IN-PROGRESS` after S7a. This
run did **S7b only** — turn S7a's 97-game World Cup tape into a candidate trade set (decision-
time real ask vs de-vigged sharp fair, fee-aware P&L per trade). No bootstrap, no verdict —
that's S7c, next stage.

Built `scripts/sports_clv_s7.py` (16 new unit tests, all offline/no-network, 137 total green).
Key design calls, each documented in the script's own header:

- **Decision time.** football-data's closing odds are priced at kickoff, which Kalshi's
  `open_time`/`close_time` don't directly expose. Defined `decision_ts = close_time - 4h` as a
  conservative pre-kickoff proxy (spot-checked against a captured game: `close_time` lands
  within minutes of the final whistle, regulation+stoppage is reliably under 2h) — stated as an
  approximation, not a precise kickoff read, since no free kickoff-timestamp feed exists.
- **Price.** Last candle at-or-before `decision_ts`, causal/no-look-ahead (same discipline as
  S1's T-24h rule); a missing leg drops the whole 3-outcome bracket rather than partial-
  normalizing.
- **Trade rule.** Single-leg BUY YES when de-vigged fair prob > Kalshi's bracket-normalized ask
  (Hard Rule #3 — `core.pricing.normalized_ask`, never a raw ask read as probability); the fill
  price and P&L use the raw ask. Fee model reused verbatim from `scripts/fee_breakeven.py`.

**Live pass:** 96/97 games usable (1 dropped: odds unmatched, same freshness gap S7a flagged).
**167 candidate trades, mean net P&L −3.51¢/trade** (real_ask, after 0.07-rate taker fee) —
already negative before any bootstrap. A quick min-edge sweep (0.00 → 0.02 → 0.05) makes it
**monotonically worse** (−3.51¢ → −9.30¢ → −27.00¢, n=167/23/1 trades): if the nominal
fair-vs-ask gap were real signal, tightening the bar should concentrate on better trades, not
degrade them — the same "sweep makes it worse" red flag that helped kill S5. Candidate
explanations, none confirmed: football-data's multi-book average is a noisier sharp-consensus
proxy than a single sharp book (S7a already flagged it isn't Pinnacle-specific); the 4h-early
snapshot mixes in market drift the true closing line doesn't share; or plain small-sample noise
(one tournament, 96 games, likely round/team-correlated). Writeup →
`../findings/2026-07-10-sports-clv-s7b.md`; tape → `tape/sports_clv_s7/`.

Gates: **137 tests green** (121 existing + 16 new), `invariants --full` green.

**Next:** Q4/S7c — moving-block bootstrap by game (reuse the S1/S5 `block_bootstrap` pattern) →
95% CI → verdict. The point estimate gives no reason for optimism, but the queue's binding bar
is the bootstrapped CI, not this number — S7c runs it and records whatever it finds, including
DEAD, honestly.

---

## 2026-07-10 10:35 UTC — Q4/S7a: sourced the World Cup CLV backtest dataset; NFL/NBA history mostly unavailable

Topmost eligible queue item: **Q4** (S7 historical CLV backtest), `TODO` since Q0b's egress
unblock. Q4 runs in three stages (S7a source → S7b probe → S7c bootstrap CI); this run did
**S7a only** — sourcing + provenance, no backtest math yet.

Built `scripts/sports_history_s7a.py` (16 new unit tests, all offline/no-network, 121 total
green). Two legs per game:

- **Kalshi (`real_ask`)** — every settled `KXWCGAME` event via `GET /events` with nested
  markets (settlement `result`/`settlement_value_dollars` arrive inline), plus the full hourly
  candlestick series per outcome market (Kalshi's own published `yes_ask` OHLC). Markets are
  listed as early as ~140 days before their game, so the candlestick fetch is capped to the
  last 7 days before close (`CANDLE_LOOKBACK_HOURS`, logged per-outcome as
  `candle_window_truncated`) — the pre-game noise a decision-time backtest will never use is
  dropped explicitly, not silently; keeps the tape at 20 MB instead of ~106 MB uncapped.
- **Odds (`synthetic`)** — football-data.co.uk's free public `WorldCup2026.xlsx`
  (`H-Avg`/`D-Avg`/`A-Avg`, a multi-book closing-odds average — not Pinnacle-specifically, an
  honestly-weaker sharp-consensus proxy), de-vigged via `core/odds.py`'s existing
  decimal-odds → implied-prob → multiplicative-de-vig math. Team names joined order-agnostic
  with an explicit alias table for every observed naming mismatch (`IR Iran`/`Iran`, `Korea
  Republic`/`South Korea`, `Turkiye`/`Turkey`, etc.).

**Live pass:** 97 completed World Cup 2026 games (2026-06-11..07-09), 291 outcome markets, 0
candlestick fetch failures, 96/97 odds-matched (the one miss is the most recent game — the
free odds file lags live results by a few days, an honest freshness gap). Tape →
`tape/sports_history_s7/worldcup2026.jsonl` (20 MB) + the exact xlsx bytes fetched, both
sha256-provenanced per record.

**Honest finding on NFL/NBA:** `probe_last_season_availability()` confirmed Kalshi's public
`/markets` listing purges settled markets after roughly one season, not indefinitely. NFL 2025
season (finished Feb 2026) returns **zero** rows under `status=settled`/`closed` — fully gone.
NBA returns 72 outcome markets / 36 games, but only the playoff tail (2026-05-05..06-14,
conf finals through the Finals) — the regular season is gone the same way. No free historical
NBA odds source was sourced this run (out of scope for this stage) — flagged as a follow-up,
not a blocker. **S7b/S7c run on the World Cup dataset next**, the immediately-usable 97-game
set this stage produced. Writeup → `../findings/2026-07-10-sports-history-s7a.md`.

Gates: **121 tests green** (105 existing + 16 new), `invariants --full` green. Added
`openpyxl>=3.1` to the `analysis` extra (reads the free .xlsx; base substrate + invariants
still run without it).

**Next:** Q4/S7b — probe Kalshi ask vs de-vigged fair at a defined decision time on the 97-game
World Cup dataset, fee model consistent with `scripts/fee_breakeven.py`.

---

## 2026-07-10 05:11 UTC — Q3 hourly collector entry point built + first live pass

Topmost eligible queue item: **Q3** was `BLOCKED(needs Q1 + Q2 built)`, and both landed this
session's prior two runs — dependency resolved, flipped to `TODO`, and it's topmost, so this
run built it: `collection/hourly_pass.py`, the single command the hourly Haiku collector
routine runs.

One pass = one `collection.sports_pairs.run()` + one `collection.crypto_hourly.run()`; during
the 09 UTC hour it also runs `scripts/anomaly_sweep.py` as a subprocess if that file exists
(Q6 isn't built yet, so today every hour is a no-op there — checked fresh every run, so Q6
needs zero additional wiring once it lands). Discipline carried over from both collectors: a
hard exception in either sub-pass degrades to an honest `{"ok": False, "error": ...}` entry
rather than crashing the whole hourly pass or silently dropping the other collector's result;
`completeness_ok` is `False` if either sub-pass raised, either sub-pass logged a
series-enumeration error, or (09 UTC only) the anomaly sweep exists and failed — never faked
`True`. Prints the exact digest line Q3 specified: `<n> markets, <m> lines, completeness
<ok/FAIL>`.

10 new unit tests (`tests/test_hourly_pass.py`), sub-passes stubbed via injected callables
(no network): count aggregation, independent-failure isolation (a sports exception doesn't
zero out crypto's real counts and vice versa), series-errors-without-an-exception still
failing completeness, the 09-UTC-only anomaly-sweep gate (both the call-happens/doesn't-happen
cases and a failing sweep failing completeness), the default runner treating "script doesn't
exist yet" as `True` (not a failure), the digest line's exact format, and `main()`'s exit code
tracking `completeness_ok`.

**Live pass** (real network, no injected fixtures): **1311 markets, 455 lines, completeness
ok** — sports leg 453 events / 1048 outcome markets (odds leg still `blocked_no_key`, unchanged
from Q1), crypto leg 2/2 symbols captured with `spot={ok:2}` and `settle={ok:2}`. Tape appended
to the existing `tape/sports_pairs/` and `tape/crypto_hourly/` stores (same manifests those
collectors already write — `hourly_pass` adds no new tape shape, just orchestration). Gates:
**105 tests green** (95 existing + 10 new), `invariants --full` green.

**Next:** Q4 (S7 historical CLV backtest) and Q5 (S8 first cut) remain the two `TODO`-eligible
research milestones; Q6 (anomaly sweep) is now load-bearing for Q3's completeness signal
whenever it lands, not just a standalone probe. Collector-side plumbing (Q1/Q2/Q3) is done;
the queue's center of gravity moves to actually testing S7/S8 for edge.

---

## 2026-07-10 00:22 UTC — Q2 crypto-hourly settlement collector built + first live pass

Topmost eligible queue item after Q1: **Q2**, the crypto-hourly settlement-basis collector
(serves S8/S10). Built:

- `core/crypto_schema.py` — `CryptoHourlyManifest`, the Q2 sibling of `core/sports_schema.py`'s
  `GamePairManifest`: one line pairs THREE legs for one symbol's current hourly bracket —
  the Kalshi ladder (`real_ask`), a live public spot reference (`synthetic`), and the previous
  hour's Kalshi-reported settlement value (`broker_truth`) — so S8's ρ-guard (spot-vs-settle
  correlation) is computable from tape alone, with no second pass ever needed.
- `collection/crypto_hourly.py` — per symbol (BTC via `KXBTC`, ETH via `KXETH`): discovers the
  CURRENT hourly range-ladder by picking the open event whose `(close_time - open_time)` is
  closest to exactly 3600s (Kalshi keeps a much-longer ~7-day "range" event alive under the
  SAME series_ticker simultaneously — duration, not the ticker string, is what actually
  distinguishes them; verified live on both KXBTC and KXETH); snapshots every outcome market's
  real yes_ask BBO; fetches live spot (Coinbase primary, Kraken fallback on failure); locates
  the settled event whose `close_time` equals the current event's `open_time` and reads off
  Kalshi's own `expiration_value`. Any leg failure degrades to an honest status code
  (`spot_status`/`settle_status`) rather than poisoning the Kalshi leg, which is captured
  unconditionally — same discipline as `sports_pairs.py`'s odds leg.
- Added `Kalshi.markets(series_ticker, status, limit)` to `validation/v3_market.py` (generalizes
  the existing `open_markets`, which now delegates to it) so the settlement leg can query
  `status="settled"` through the same throttled/paginated client, no new HTTP code path.
- 14 new unit tests (`tests/test_crypto_hourly.py`): duration-based hourly-vs-standing-range
  event selection (including the "nothing currently straddles now" fallback), degenerate/
  single-outcome/series-error handling, spot-fetch-failure and settle-not-found/fetch-error
  degradation (each independently, confirming the Kalshi leg is never poisoned), the
  provenance/forged-hash check mirroring `sports_pairs`'s, and two adversarial schema checks
  for the new "`ok` status implies the trusted tag" consistency rules.

**Live pass** (no injected fixtures): **BTC 188 outcomes / ETH 75 outcomes** captured in one
pass, `spot_status={ok:2}`, `settle_status={ok:2}` — both legs resolved live on the first try
(Coinbase spot, Kalshi `expiration_value` for the hour that had just closed). Tape →
`tape/crypto_hourly/`.

**Honest finding, not interpreted here (Q5's job):** the naive `bracket_sum` summed across the
FULL discovered ladder is **not** comparable to weather's ~10¢ overround — live BTC bracket_sum
was **3.99** (188 outcomes, overround +2.99), ETH **2.22** (75 outcomes, overround +1.22).
Inspecting the outcomes: most of the 188/75-market ladder is far out-of-the-money brackets
sitting at the exchange's $0.01 floor tick (illiquid, effectively unfillable at size), and their
one-cent asks summed across dozens of dead brackets dominate the total — a thin-tail-liquidity
artifact, not a real structural cost comparable to the weather bracket's near-the-money
overround. Nothing is discarded (the full ladder is captured honestly), but Q5's S8 first cut
will need to restrict to brackets near the money (e.g. within a few strikes of live spot) to get
a bracket_sum that means the same thing weather's did. Gates: **85 tests green** (71 existing +
14 new), `invariants --full` green.

**Next:** Q4 (S7 historical CLV backtest) and Q5 (S8 first cut from free candlesticks — now
armed with 2 days-in-progress of paired crypto tape once cron accumulates it) are both
`TODO`-eligible; Q5 should apply the near-the-money bracket filter found here before trusting
any overround number. S8 moved `idea → data-collecting` in `kb/strategies/00-index.md`.

---

## 2026-07-09 20:18 UTC — Egress unblocked (Q0b); Q1 sports paired-odds collector built + first live pass

Q0b's self-healing re-check (protocol: cheap re-test while any item sits `BLOCKED(egress...)`)
found all four Q0 hosts now reachable — `curl --max-time 15` got Kalshi REST 200, Coinbase 200,
Kraken 200, and the-odds-api 401 (reachable, just no key). Confirmed end-to-end with
`python -m collection.capture_orderbooks --limit 3` (3 markets, 159 levels, real tape written).
The org egress allowlist was evidently widened sometime between 2026-07-02 and today — not
observable from inside the sandbox, just confirmed fixed. Flipped Q1–Q6 back to `TODO` in
`LOOP-QUEUE.md`; refreshed `tape/cloud-env-check.md`.

With egress open, moved to the new topmost eligible item: **Q1**, the sports paired-odds
collector — time-sensitive, since the 2026 World Cup final round runs through Jul 19. Built:

- `core/sports_schema.py` — `GamePairManifest`, the Q1 sibling of `core/manifest_schema.py`'s
  weather `CaptureManifest`: same bitemporal/content-hash/self-signed discipline, keyed by
  `event_ticker` instead of `(city, contract-day)` since a sports event isn't a city ladder.
- `core/odds.py` — American-odds → de-vigged fair probability. Reuses
  `core.pricing.bracket_sum`/`normalized_ask` for the overround-removal division (same "divide
  by the group sum" operation as Kalshi's own Hard Rule #3 math, just applied to sportsbook
  implied probabilities), so that arithmetic still lives in one place.
- `collection/sports_pairs.py` — discovers every Sports-category series whose ticker ends in
  `GAME` (empirically the per-event moneyline/winner suffix — `KXWCGAME`, `KXNBAGAME`,
  `KXMLBGAME`, ... 186 series found live), World-Cup/soccer sorted first; groups each series'
  open markets by the API's own `event_ticker` (cross-checked against a ticker-parse, mismatches
  recorded not hidden); captures real yes/no BBO for every outcome in a >=2-way bracket
  (`price_source_tag=real_ask`); attempts a matched-Pinnacle de-vig leg if `ODDS_API_KEY` is set
  (`synthetic`), else honestly records `odds_leg_status="blocked_no_key"` per Q1's documented
  fallback — the Kalshi leg is captured regardless.
- 18 new unit tests (`tests/test_odds_devig.py`, `tests/test_sports_pairs.py`): American-odds
  math, multiplicative de-vig on 2-way and 3-way brackets, ticker parse/reconcile, World-Cup
  priority ordering, degenerate/series-error handling, odds-leg name matching (caught a real bug:
  Kalshi labels a soccer draw "Tie", the-odds-api calls it "Draw" — added a synonym normalizer),
  and the provenance/forged-hash check mirroring `capture_orderbooks`'s.

**Live pass** (no `ODDS_API_KEY` in this environment): **469 events / 1079 outcome markets**
captured at `real_ask` in ~47s. 4 `KXWCGAME` (World Cup) events captured — `bracket_sum` 1.01–1.02
(1–2¢ overround), noticeably tighter than the ~10¢ weather-bracket overround that killed
pt1/S1/S5. Across all 469 events, mean `bracket_sum` 1.34 (min 0.98, max 2.73) — wide dispersion
expected from thin/off-season leagues with stale asks; not interpreted here, that's Q4's job.
Tape → `tape/sports_pairs/`. `S7` (Kalshi moneyline vs Pinnacle CLV) moved `idea → data-collecting`
in `kb/strategies/00-index.md`. Gates: 71 tests green (53 existing + 18 new), `invariants --full`
green (two docstring false-positives on the `yes_ask`/`no_ask` regex — literal `yes_ask/no_ask`
prose tripped Hard Rule #3's arithmetic detector; reworded, not a real violation).

**Next:** Q2 (crypto-hourly collector) is now the topmost `TODO` item. Separately: S7's actual CLV
backtest (Q4) is still gated on `ODDS_API_KEY` — the odds leg is built and unit-tested but has
never made a live request; re-run Q1 once a key exists to confirm the live matching/de-vig path.

## 2026-07-08 05:30 ET — research loop: comprehensive stranded-tape sweep (6,272 lines recovered), queue still idle

Claim-check: `git fetch origin main` force-updated the local ref to `ce310a2` (5 VPS hourly
passes landed since the last research run). Open PRs unchanged — #4 still claims Q1 (odds-api
leg, unrelated, awaiting `ODDS_API_KEY`; now ~4d18h old, still just under PR #18's proposed
5-day escalation mark, but close enough to flag to Ryan directly this run) and #18
(weekly-retro protocol amendments, left for Ryan, never self-merged).

Queue re-check against the fresh tip: Q2–Q6/Q8–Q12/Q16 all DONE; Q1 claimed. Tape day-counts
recounted directly off disk: Q7 needs ≥7 distinct days of `tape/crypto_hourly/` — only 6
(`dt=2026-07-03`…`07-08`), still BLOCKED, eligible ~07-09/10; Q13 needs ≥10 distinct days of
`tape/sports_pairs/` — only 7 (`dt=2026-07-02`…`07-08`), still BLOCKED, eligible ~07-12/13.
Q14/Q15 re-probed live: `KXHOUSE`/`KXSENATE` still return **zero** markets in any status on
Kalshi's live API — Q15 stays BLOCKED; `ODDS_API_KEY` still absent from env. Lessons ledger
re-scanned: zero live `UNENFORCED` rows (L22 stays resolved by L24). Strategy registry
re-scanned: every `idea`-stage candidate is externally blocked by the same walls as prior
runs. **No numbered queue item, lesson, or registry candidate was actionable this run.**

Step 0b sweep — went wider than recent runs' "branches postdating the last cutoff" heuristic:
fetched all **69** `tape/hourly-*`/`-corrected-`/`-followup-`/`-amended-` branches and ran a
real per-file line-set diff against `origin/main` for every one of them (not just the newest
few), since prior runs' cutoff heuristic can't see whether an "already reconciled" branch
picked up new commits later. Result: the 2026-07-03…07-06 branches were indeed already fully
reconciled (0 missing lines — confirms prior sweeps' bookkeeping was sound), but 07-07 and
07-08 carried a large unreconciled backlog: **6,272 lines** across `crypto_hourly` (+16),
`orderbook_depth` (+4,470), `polymarket_macro_pairs` (+120), `polymarket_pairs` (+140),
`sports_pairs` (+1,498), `anomalies` (+1), `econ_prints` (+5), `polymarket_cpi_pairs` (+22).
Every appended line JSON-validated (0 malformed), union-deduped by exact line match against
main's current content, appended into this run's commit — the largest single-run recovery
since collection began. `git push origin --delete` not reattempted (documented permission
boundary, failed every time since 2026-07-03; PR #18 already proposes dropping the retry).

Gates: pytest green (unchanged test count — tape-only commit, no code touched), `invariants
--full` green. No strategy status changed; no code changed. Seventh consecutive
maintenance-only run — queue/lessons/registry idle pending the same external clocks (tape
day-counts, 1-2 days out for Q7) and external walls (odds-api key, Congress-market listing) as
prior runs; not a stall. The size of this recovery (6,272 vs. the ~1,700-2,800/run of the last
few sweeps) suggests push-to-main failures are becoming more frequent, not less — worth
Ryan's attention if the pattern continues.

---

## 2026-07-08 01:08 ET — research loop: stranded-tape sweep (841+ lines recovered), queue still idle

Claim-check: `git fetch origin main` force-updated the local ref to `12f794c` (VPS + cloud
hourly passes landed since the last run). Open PRs unchanged — #4 still claims Q1 (odds-api
leg, unrelated, awaiting `ODDS_API_KEY`; now ~4d14h old, still short of PR #18's proposed
5-day escalation mark — worth a direct nudge if it's still open next run) and #18 (weekly-retro
protocol amendments, left for Ryan, never self-merged).

Queue re-check against the fresh tip: Q2–Q6/Q8–Q12/Q16 all DONE; Q1 claimed. Tape day-counts
recounted directly off disk: Q7 needs ≥7 distinct days of `tape/crypto_hourly/` — only 6
(`dt=2026-07-03`…`07-08`), still BLOCKED, eligible ~07-09/10; Q13 needs ≥10 distinct days of
`tape/sports_pairs/` — only 7 (`dt=2026-07-02`…`07-08`), still BLOCKED, eligible ~07-12/13.
Q14/Q15 re-probed live (not assumed): CME's FedWatch page still returns HTTP 403 (Akamai-class
bot wall, same as every prior check) — Q14 stays BLOCKED; `KXHOUSE`/`KXSENATE`/`HOUSE`/`SENATE`
still list **zero** markets in open/unopened/closed status on Kalshi's live API — Q15 stays
BLOCKED. `ODDS_API_KEY` still absent from env. Lessons ledger re-scanned: zero live
`UNENFORCED` rows. Strategy registry re-scanned: every `idea`-stage candidate (S10=Q7, S11,
S14=Q13, S16, S18) is externally blocked by one of the walls above — nothing new to draw from
either standing queue. **No numbered queue item, lesson, or registry candidate was actionable
this run.**

Step 0b sweep (against the freshly-fetched tip): of 64 `tape/hourly-*`/`-corrected-`/
`-followup-`/`-amended-` branches, 4 postdating the last run's fully-clean sweep cutoff
(`20260707T2356Z`, `20260708T0401Z`, `hourly-corrected-20260707T2059Z`,
`hourly-followup-20260707T2055Z`, all >30min old) carried lines `main` was missing — did a
real line-set diff per file (not `git diff --stat`, which is unreliable for out-of-order
JSONL appends) across all 5 tape families they touch. Union-deduped total: **2,797 lines**
(10 crypto_hourly, 1,791 orderbook_depth, 75 polymarket_macro_pairs, 92 polymarket_pairs, 829
sports_pairs), every line JSON-validated before appending, 0 exact duplicates, appended into
this run's commit. `hourly-amended-20260704T1455Z` (also re-checked) was already fully
reconciled (0 missing). `git push origin --delete` not reattempted (documented permission
boundary, failed every time since 2026-07-03; PR #18 already proposes dropping the retry).

Gates: 362 tests green (unchanged — tape-only commit, no code touched), `invariants --full`
green. No strategy status changed; no code changed. Sixth consecutive maintenance-only run —
queue/lessons/registry idle pending the same external clocks (tape day-counts, 1-2 days out
for Q7) and external walls (odds-api key, Congress-market listing, CME bot-wall) as prior
runs; not a stall, just recovering tape the VPS/cloud collectors' intermittent push-to-main
failures stranded.

---

## 2026-07-07 20:15 ET — research loop: fully idle, tape sweep clean for the first time

Claim-check: `git fetch origin main` force-updated the local ref to `b938307` (a VPS hourly
pass landed since the last research run). Open PRs unchanged — #4 still claims Q1 (odds-api
leg, unrelated, awaiting `ODDS_API_KEY`; now ~4d9h old, still short of PR #18's proposed
5-day escalation mark) and #18 (weekly-retro protocol amendments, left for Ryan, never
self-merged).

Queue re-check against the fresh tip: Q2–Q6/Q8–Q12/Q16 all DONE; Q1 claimed. Tape day-counts
recounted directly off disk: Q7 needs ≥7 distinct days of `tape/crypto_hourly/` — still only 5
(`dt=2026-07-03`…`07-07`), BLOCKED, eligible ~07-09/10; Q13 needs ≥10 distinct days of
`tape/sports_pairs/` — still only 6 (`dt=2026-07-02`…`07-07`), BLOCKED, eligible ~07-12/13.
Q14/Q15 re-probed live this run (not just assumed): `ODDS_API_KEY` still absent from env;
Kalshi's `KXHOUSE`/`KXSENATE` series still list **zero** markets in any status — both stay
data-adequacy BLOCKED, same as every prior check. No numbered queue item was eligible.
Lessons ledger re-scanned: zero live `UNENFORCED` rows (all resolved by L18–L20/L24).
Strategy registry re-scanned: every `idea`-stage candidate (S10=Q7, S11, S14=Q13, S16, S18)
is externally blocked by one of the walls above — nothing new to draw from either standing
queue.

Step 0b sweep (against the freshly-fetched tip, per L14): 9 `tape/hourly-*`/`-corrected-`/
`-followup-` branches postdating the last run's sweep cutoff (`20260707T1958Z` through
`2256Z`, ages 64min–244min, all past the 30-min freshness rule) were diffed line-by-line
against `main` across all 5 tape families they touch (`crypto_hourly`, `orderbook_depth`,
`polymarket_macro_pairs`, `polymarket_pairs`, `sports_pairs`) — **zero lines missing from
main in every branch and every family.** This is new: every previous sweep this week found
at least some stranded content; this time the VPS collector's direct pushes to `main` (it
has been landing hourly `tape:` commits straight onto `main` all day, e.g. the `b938307` tip
itself) had already fully reconciled everything before this run started. The one branch newer
than 30 minutes (`20260707T2356Z`, ~12min old) was skipped per the freshness rule, left for
the next run. `git push origin --delete` not reattempted (documented permission boundary,
failed every time since 2026-07-03; PR #18 already proposes dropping the retry).

Gates re-verified from a clean env this run (`pip install -e ".[dev,analysis]"` then
`python3 -m pytest -q` and `python scripts/invariants.py --full`): 362 tests green (unchanged
from the last run — no code touched), invariants clean (the non-gating stranded-tape warning
still fires as designed per L20, listing local refs the live sweep above already proved
harmless).

No strategy status changed; no code changed; no tape lines appended (nothing was stranded).
Fifth consecutive maintenance-only run, and the first one with truly nothing to commit —
queue, lessons, registry, and tape are all simultaneously reconciled and idle pending the same
external clocks (tape day-counts, 2-3 days out) and external walls (odds-api key,
Congress-market listing, CME bot-wall) as the last several runs. Nothing here indicates a
stall. PR #4 is now ~4d9h old; worth a direct nudge to Ryan if it crosses 5 days before the
next run picks it up.

---

## 2026-07-07 16:09 ET — research loop: stranded-tape sweep only (queue/lessons/registry all still idle)

Claim-check: `git fetch origin main` force-updated the local ref to `a14afb6` (five VPS hourly
passes had landed since the last research run). Open PRs unchanged — #4 still claims Q1
(odds-api leg, unrelated, awaiting `ODDS_API_KEY`; now ~4d5h old, still short of PR #18's
flagged 5-day escalation mark) and #18 (weekly-retro protocol amendments, left for Ryan, never
self-merged).

Queue re-check against the fresh tip: Q2–Q6/Q8–Q12/Q16 all DONE; Q1 claimed. Counted tape days
directly off disk (not the last log line's estimate): Q7 needs ≥7 distinct days of
`tape/crypto_hourly/` — still only 5 (`dt=2026-07-03`…`07-07`), BLOCKED, eligible ~07-09/10;
Q13 needs ≥10 distinct days of `tape/sports_pairs/` — still only 6 (`dt=2026-07-02`…`07-07`),
BLOCKED, eligible ~07-12/13. Q14/Q15 stay data-adequacy BLOCKED (no re-probe run this cycle —
both were already re-checked live twice this week with no change). No numbered queue item was
eligible. Lessons ledger and strategy registry both re-scanned: zero `UNENFORCED` lesson rows,
every `idea`-stage registry candidate already externally blocked (same set as the last two
runs) — nothing new to draw from either standing queue.

Step 0b sweep (against the freshly-fetched tip, per L14): of 54 `tape/hourly-*` branches, 2
(`20260707T1658Z`/`1759Z`, ages 191min/130min) carried lines `main` lacked across 5 tape
files — 4 crypto_hourly + 1,332 orderbook_depth + 30 polymarket_macro_pairs + 48
polymarket_pairs + 330 sports_pairs = **1,744 lines total**, union-deduped across both branches
per file (every line JSON-validated, 0 exact duplicates), appended into this run's commit. The
newest branch (`20260707T1958Z`, ~3min old) skipped per the 30-min freshness rule, left for the
next run. 3 branches (`20260706T1856Z`/`20260707T1359Z`/`20260707T1856Z`) confirmed stale names
pointing at the same pre-project commit with zero tape content (harmless, consistent with prior
runs' finding). `git push origin --delete` not reattempted this run (documented permission
boundary, failed every time it's been tried since 2026-07-03; PR #18 already proposes dropping
the retry). 362 tests unchanged, `invariants --full` green (non-gating stranded-tape warning
still fires as designed, per L20).

No strategy status changed; no code changed. Fourth consecutive maintenance-only run — the
queue, lessons ledger, and idea registry remain simultaneously idle pending external clocks
(tape day-counts, 2-3 days out) and external walls (odds-api key, Congress-market listing,
CME bot-wall). Nothing here indicates a stall; it's the expected shape while waiting on those
clocks. PR #4's age is worth flagging to Ryan directly since it's now approaching the 5-day
mark PR #18 itself proposed as the escalation trigger.

---

## 2026-07-07 11:08 ET — research loop: stranded-tape sweep only (queue/lessons/registry all genuinely idle)

Claim-check: `git fetch origin main` at `97ad331`, local branch already at the real tip. Open
PRs unchanged — #4 still claims Q1 (odds-api leg, unrelated, awaiting `ODDS_API_KEY`; open
since 2026-07-03, now just under 4 days — still short of PR #18's flagged 5-day escalation
mark) and #18 (weekly-retro protocol amendments, left for Ryan, never self-merged).

Queue check: Q2–Q6/Q8–Q12/Q16 all DONE. Q7 needs ≥7 distinct days of `tape/crypto_hourly/`
tape — counted the actual files on disk: 5 days (`dt=2026-07-03`…`dt=2026-07-07`), still
BLOCKED, eligible ~2026-07-09/10. Q13 needs ≥10 distinct days of `tape/sports_pairs/` tape —
counted: 6 days (`dt=2026-07-02`…`dt=2026-07-07`), still BLOCKED, eligible ~2026-07-12/13.
No numbered queue item was eligible.

Lessons ledger check (`kb/lessons/00-lessons.md`): every row is now either an `invariant`,
a `test`, a terminal `protocol`/`ledger-only` state, or (L22) already resolved by L24 last
run. Zero `UNENFORCED` rows remain — the standing lessons queue is drained too.

Registry check (`kb/strategies/00-index.md`): every `idea`-stage candidate is externally
blocked — S4 (unrelated-repo FEx archiver), S10=Q7 and S14=Q13 (tape day-count, above), S11
(needs the same Pinnacle/odds-api anchor Q1 is already blocked on), S16=Q14 and S18=Q15
(data-adequacy BLOCKED, re-checked live this run: `HOUSE`/`SENATE`/`KXHOUSE`/`KXSENATE` still
list 0 markets in any status — 2026 midterm contracts still not listed, `ODDS_API_KEY` still
absent from env). No new milestone was actionable — genuinely nothing to append past what the
last several runs already exhausted.

Step 0b sweep (the one real piece of work this run did): of 50 `tape/hourly-*` branches, 5
fresh ones since the last run's cutoff (`20260707T0456Z`/`055501Z`/`202607070749Z`/`0756Z`/
`0956Z`, all >30min old) carried lines `main` lacked — 10 crypto_hourly + 3,458
orderbook_depth + 75 polymarket_macro_pairs + 120 polymarket_pairs + 889 sports_pairs + 5
econ_prints + 1 anomalies = **4,558 lines total**, union-deduped across all 5 branches (every
line validated as parseable JSON, 0 exact duplicates), appended into this run's commit.
`tape/hourly-20260707T1359Z` confirmed a stale branch name pointing at a pre-project commit
(`6cde523`, zero real tape content, harmless — same pattern as prior runs). `git push origin
--delete` not reattempted this run (documented permission boundary, failed every time it's
been tried since 2026-07-03; PR #18 already proposes dropping the retry). 362 tests green
(unchanged — no source/test code touched), `invariants --full` green.

No strategy status changed; no code changed. This is an honest maintenance-only run — the
loop's own queue, lessons ledger, and idea registry are all simultaneously drained pending
external clocks (tape day-counts) and external walls (odds-api key, Congress-market listing,
CME bot-wall). Nothing here should be read as stalled; it's the expected shape of a run that
lands inside a 2-3 day accumulation gap.

## 2026-07-07 UTC — research loop: stranded-tape sweep + L22 resolution (real_bid taxonomy decision)

Claim-check: `git fetch origin main` at `e20f026`; open PRs unchanged — #4 still claims Q1
(odds-api leg, unrelated, awaiting `ODDS_API_KEY`; open since 2026-07-03, still short of the
5-day mark PR #18's retro proposal flagged for priority escalation) and #18 (weekly-retro
protocol amendments, left for Ryan, never self-merged). Q2–Q6/Q8–Q12/Q16 all DONE; Q7 BLOCKED
(only 5 of the needed ≥7 days of Q2 tape); Q13 BLOCKED (only 5 of the needed ≥10 days of Q3
tape) — no numbered queue item was eligible.

Step 0b sweep: of 44 `tape/hourly-*` branches, 3 (`202607070056Z`/`20260707T015503Z`/
`202607070356Z`, all >30min old) carried lines `main` lacked — 6 crypto_hourly + 700
orderbook_depth + 544 sports_pairs + 45 polymarket_macro_pairs + 80 polymarket_pairs lines,
union-deduped across all three branches (every line validated as parseable JSON, 0 exact
duplicates), appended into this run's commit. The newest branch (`20260707T0456Z`, ~12min old)
skipped per the freshness rule; 3 branches (`20260706T0556Z`/`0955Z`/`1856Z`) confirmed to be
stale names pointing at a pre-project commit with zero tape content (harmless). `git push
origin --delete` still fails from a cloud session on every already-reconciled branch (same
documented permission boundary).

With the queue drained to time-blocked items and Q1 claimed, checked the registry for the next
un-started, non-externally-blocked candidate first (same process as the last 3 runs): S4/S10
(=Q7)/S14(=Q13)/S16(=Q14)/S18(=Q15) all already explicitly blocked; S11 needs the same
Pinnacle/odds-api anchor as Q1's blocked leg, so appending it would only restate Q1's own
blocker. No genuinely new collector/probe milestone was actionable this run — instead drew from
`kb/lessons/00-lessons.md`'s standing UNENFORCED queue (roster note: "converting a lesson into
an invariant/test is always an eligible milestone, no queue item needed"): **L22** asked
whether `real_bid` (orderbook_depth.py's tag for a genuine resting bid, from Q16) should join
`VALID_SOURCE_TAGS` or stay a separate tape-only namespace. Decided to keep it separate — that
enum mirrors CLAUDE.md's own literal four-tag trust-taxonomy contract, and widening a
project-contract enum is outside a single research-loop milestone's authority, the same class
of call as S9's automation decision and the PreToolUse-hook registration (both left for Ryan).
Closed the "harmless today" half of L22 with proof rather than inspection: a new regression
test (`tests/test_invariants.py::test_db_real_bid_tag_is_caught_as_invalid_enum`) confirms the
existing DB-side enum check already rejects `real_bid` the moment one reaches a
`price_source_tag` column — no live gap exists to fix. `core/source_tag.py`'s docstring now
cross-references the decision. Recorded as **L24** (supersedes L22) in the lessons ledger. 362
tests green (361 prior + 1 new), `invariants --full` green.

No strategy status changed (no probe run this cycle — this was a substrate/documentation
milestone plus the standing tape reconciliation).

## 2026-07-07 UTC — research loop: stranded-tape sweep, S6 orderbook-depth collector built (Q16, new)

Claim-check: `git fetch origin main` at `c238b17`; local `main` ref re-pointed via
`git branch -f main origin/main` (session branch was already at the real tip, per L14). Open
PRs unchanged — #4 still claims Q1 (odds-api leg, unrelated, awaiting `ODDS_API_KEY`; open
since 2026-07-03, approaching but not yet past the 5-day mark PR #18's retro proposal flagged
for a priority escalation) and #18 (weekly-retro protocol amendments, left for Ryan, never
self-merged). Q2–Q6/Q8–Q12 all DONE; Q7 BLOCKED (only ~4 days of Q2 tape, needs ≥7); Q13
BLOCKED (only ~4 days of Q3 tape, needs ≥10) — **no numbered queue item was eligible.**

Step 0b sweep: of 42 `tape/hourly-*` branches, 2 fresh ones (`20260706T2059Z`/`2255Z`, both
>30min old) carried lines `main` lacked — 8 crypto_hourly + 60 polymarket_macro_pairs + 124
polymarket_pairs + 710 sports_pairs, union-deduped across both branches (every line validated
as parseable JSON, 0 exact duplicates), appended into this run's commit. `git push origin
--delete` still fails from a cloud session on every already-reconciled branch (same documented
permission boundary).

With the queue drained to time-blocked items and Q1 claimed, checked the registry for the next
un-started, non-externally-blocked candidate: S4 depends on an unrelated repo's FEx tape
archiver, S10=Q7 and S11 both already blocked the same way as Q7/Q1 — **S6** (inventory-aware
market-making) was the only remaining `idea`-stage candidate with no external block, so
appended **Q16** and built it via the `collector-engineer` subagent. Built
`collection/orderbook_depth.py`: full L2 book depth capture (`yes_bids`/`no_bids` price+size
ladders, not just BBO) reusing `collection/normalize.py:normalize_snapshot` verbatim, fed by
the exact tickers `sports_pairs`/`crypto_hourly` already discover each pass — read straight
back from their own freshly-written tape by `capture_id`, no platform re-sweep (L10). Every
book read tagged `real_ask`/`real_bid`; honest per-ticker completeness (a failed fetch is a
DROP, never absorbed). Wired into `hourly_pass.py` as a fifth fault-isolated sub-pass. 13 new
unit tests (361 total), `invariants --full` green.

Live pass against real Kalshi data: fed 6 tickers from the current-hour `KXBTC-26JUL0621`
group into the collector — 6/6 captured, `completeness_ok=True`, sample reading
`KXBTC-26JUL0621-T71799.99` depth=71, `best_no_bid=0.99 → best_yes_ask=0.01` (correct `1−bid`
complement). Caught and fixed a would-be false-drop bug before commit: far-strike wing markets
legitimately have an empty ladder on one side, and the collector must record that as valid
data (`depth=0`, still captured), not a DROP — confirmed against this same live pass.

**Honest limitation, recorded in the module's own docstring:** this loop's recurring collector
cadence is hard-capped at hourly (the same floor S9's lead-lag work hit) — hourly depth
snapshots give S6 a repeated-sample series, not a continuous order-flow tape. Any
arrival-intensity estimate built on this data must be labeled snapshot-sampled, not treated as
a message-level fill-sim input. `kb/strategies/00-index.md` S6 flipped idea → data-collecting.

Three lesson candidates recorded in `kb/lessons/00-lessons.md`: **L21** (read tickers back from
an upstream sub-pass's freshly-written tape by `capture_id` instead of re-discovering or
threading a new return field through every sibling collector), **L22** (`real_bid` has no slot
in the canonical `VALID_SOURCE_TAGS` enum — flagged UNENFORCED for the kb-distiller, harmless
today since JSONL tape isn't invariant-scanned, but would trip the DB-side check the moment a
`real_bid` value lands in a table), **L23** (an empty one-sided ladder is valid data, not a
drop — pinned in a test, confirmed live).

---

## 2026-07-06 (later) UTC — research loop: PR #26 merged, stranded-tape sweep, Q14/Q15 feasibility (S16/S18 both BLOCKED)

Claim-check: `git fetch origin main` at `efb9245`; found open PR #26 (kb-distiller's L5/L7/L17
escalation) green locally (348 tests, `invariants --full` clean) and research/docs-only (fee-rate
constants, a new static invariant, a non-gating stranded-tape advisory, ledger rows) — merged it
(squash, now `098edbe`). PR #4 (Q1 odds leg) and #18 (weekly-retro protocol proposal) both stay
open per their own standing notes. Step 0b sweep: of 39 `tape/hourly-*` branches, 3
(`20260706T0556Z`/`0955Z`/`1856Z`) turned out to be stale branch names pointing at a 2026-07-02
commit with no tape content at all (harmless, not real stranded data); 3 genuinely fresh branches
(`20260706T1455Z`/`165524Z`/`1755Z`, all >30min old) carried 703 lines `main` lacked across 4
tape families (6 crypto_hourly, 45 polymarket_macro_pairs, 96 polymarket_pairs, 556
sports_pairs) — union-deduped, 0 exact duplicates, all valid JSON, appended into this commit.

Queue was drained to time-blocked items only (Q7 ~07-09/10, Q13 ~07-13) plus Q1 (claimed by
PR #4) — followed the registry's own stated priority past S15/S17 to the next two un-started
candidates and appended `Q14`/`Q15`. Both hit real external walls before any collector was
worth writing: **S16** (FedWatch fade) — `cmegroup.com` 403s/resets every request behind
Akamai-class bot protection (root, the tool page, three guessed API paths), while Kalshi and
the Atlanta Fed's GDPNow page (same free-JS-data shape) both worked fine this run, confirming
it's venue-side not sandbox egress. **S18** (Congress-control fade) — Kalshi's
`HOUSE`/`SENATE`/`KXHOUSE`/`KXSENATE` series exist but list zero markets in any status (the
2026 midterm contracts aren't listed yet); separately, 538's free generic-ballot CSV now
redirects to a dead ABC News stub (site retired, not moved) and RealClearPolling 403s the same
way as CME — Wikipedia's 2026 House-elections article is a live fallback source for once Kalshi
actually lists the markets. Both recorded `BLOCKED` per the Stop rules ("a DEAD verdict is a
success") — no source/test code changed, no strategy status flipped from `idea`. Full
evidence: `findings/2026-07-06-s16-s18-feasibility-blocked.md`; `kb/strategies/00-index.md`
S16/S18 notes updated; `LOOP-QUEUE.md` Q14/Q15 appended. 348 tests unchanged, `invariants
--full` green.

---

## 2026-07-06 UTC — kb-distiller: escalated lessons L5/L7/L17 (fee-rate invariant, stranded-tape warning)

Distiller milestone (research-lead directed). Moved three UNENFORCED lessons along the
invariants-over-memory gradient; ledger rows L18–L20 appended (append-only, superseding by
reference).

**L5 → invariant (`no_handrolled_fee_rate`).** The Kalshi fee-schedule rates now live solely
in `core/pricing.py` as module constants `TAKER_FEE_RATE` (0.07) / `MAKER_FEE_RATE` (0.0175)
/ `SP500_NDX_FEE_RATE` (0.035); `fee_per_contract` and `monotonicity_crossing_edge` default
to `TAKER_FEE_RATE` (same value, conservative default). A new static rule in
`scripts/invariants.py` flags, outside `core/pricing.py`, (A) a fee/rate/coeff-named constant
or kwarg bound to a banned literal and (B) a banned literal passed positionally into
`fee_per_contract()`; comment lines are skipped and 0.0035 (longshot's modeling haircut, not a
schedule rate) deliberately does not fire. Refactored every existing hit value-identical:
`collection/sports_history.py`, `scripts/s13_maker_fillsim.py`, `scripts/weather_rehab_s5.py`,
`scripts/fomc_zq_basis_s2.py`, `scripts/fee_breakeven.py` (now imports the three constants; KB
proof still runs with identical output), and `tests/test_s13_maker_fillsim.py:237` (rewritten
to use the imported `TAKER_FEE_RATE` so the maker≠taker assertion intent survives). A few
docstring/print-string prose lines were reworded rather than sentinel-littered. Honest scope:
constants and literal call-args are enforced; a from-scratch reimplementation using an
imported rate is not statically catchable and remains protocol. Post-review tightening: after
the verifier flagged that pattern A's identifier class matched fee/rate/coeff as raw substrings
(benign names like `accurate`/`coffee`/`separate` would have poisoned the gate), the rule now
requires fee/rate/coeff to be a whole underscore-delimited token segment — `SP500_NDX_FEE_RATE`
/`FEE_COEFF` still fire, the benign substrings no longer do (tests pin both directions).

**L7 → protocol (terminal, no invariant).** A numeric width literal is indistinguishable from
any other constant at regex level, and the one live site (`s8_basis_probe.py`'s documented
`BAND_WIDTH_DOLLARS_BY_SYMBOL` schedule map) would force a false-positive or a vacuous
sanction. Recorded as an honest terminal state, plus a residual hazard this review surfaced:
`s8_basis_probe.py`'s `.get(symbol, 100.0)` silent $100 fallback would repeat the ETH-class
bug for any new symbol — S8 is dead and the script historical (NOT edited), but future crypto
probes (Q7/S10) must derive spacing from the ladder or fail loudly.

**L17 → protocol + non-gating invariants warning.** `invariants.py --full` (and default tree
scan only — never `--pre-edit-hook` or `--db`) now prints a stderr advisory listing
locally-known stranded `tape/hourly-*` refs. `_git_tape_refs()` is fully offline-safe (any git
failure → no refs); `stranded_tape_warning()` is pure. It never touches the exit code — 35
stranded refs print on today's tree and the gate still exits 0. LOOP-QUEUE step 0b remains the
binding sweep.

Gate unchanged: warnings never gate. `pytest -q` 340 passed; `invariants.py --full` exit 0
(the stranded-branch warning on stderr is expected). No strategy status changed
(`kb/strategies/00-index.md` untouched — these are lessons, not verdicts). Findings linked:
`findings/2026-07-04-sports-maker-s13-verdict.md` (L5), `findings/2026-07-04-crypto-basis-s8-verdict.md`
(L7), `findings/2026-07-06-tape-audit.md` (L17).

---

## 2026-07-06 (later) UTC — Q12 closed: S17 CPI/inflation leg (derived-transform pairing)

Research loop. `git fetch origin main` at `4b76056`; local `main` ref was found badly
stale (2026-07-02, ~50 commits and 4 days behind the real `origin/main` tip) — fixed with
`git branch -f main origin/main` before trusting any diff, exactly the bug PR #18's
weekly-retro proposal flagged (a stale local `main` inflates the stranded-branch sweep).
Open PRs unchanged: #4 still claims Q1 (unrelated, awaiting `ODDS_API_KEY`), #18 is the
retro's protocol-amendment proposal (never self-merged, left for Ryan). Queue scan against
the real tip: Q1 claimed, Q2–Q6/Q8–Q11 all DONE, Q7/Q13 BLOCKED — **Q12** (FED-DECISION LEG
DONE, real remaining work: the deferred CPI/inflation leg) was topmost eligible.

Step 0b stranded-tape sweep (against the corrected `main`): 5 of 35 `tape/hourly-*`
branches (`202607051954Z`, `20260705T0957Z`, `20260705T1455Z`, `20260706T0855Z`,
`20260706T1255Z`, all >30min old) carried lines `main` was missing across 9 tape files —
union-deduped per file (each branch is an independent snapshot, not a superset of the
others, so the union had to be taken across all of them, not just the newest), 1,158 lines
total (554 + 374 sports_pairs, 120 + 64 polymarket_pairs, 30 polymarket_macro_pairs, plus
crypto_hourly/econ_prints/anomalies remainders), every line validated as parseable JSON
with 0 exact duplicates, appended into this commit.

Built the CPI/inflation leg Q12's own prior cut deferred: `collection/polymarket_pairs.run_cpi()`
pairs Kalshi's `KXCPI`/`KXCPIYOY`/`KXCPICORE` cumulative "exceed threshold T" ladders against
Polymarket's exact 0.1-point bucket partition for the same 3 US print series. Confirmed live
that both venues quote all 3 series in identical 0.1-point steps, then built
`price_cpi_bucket_from_kalshi` — the differencing transform (floor = 1 − ask(T); exact =
ask(T−step) − ask(T); ceiling = ask(T−step) directly) that turns two adjacent Kalshi `real_ask`
fills into one Polymarket-shaped bucket probability, tagged `synthetic` per Hard Rule #3's
spirit (a computed transform, not a fill, even though its inputs are). Never fabricates: a
bucket whose required Kalshi strike(s) are missing returns `None` (recorded via
`n_buckets_priced < n_buckets_total`, which correctly fails completeness) rather than being
guessed at or silently dropped; a negative derived probability (`monotonicity_violation: true`)
is recorded as-is, never clipped. 23 new unit tests (320 total), wired into `hourly_pass.py`'s
existing 09 UTC daily slot (CPI releases monthly, same cadence reasoning as Q10's
`econ_prints` — 4 new wiring tests, 6 existing 09-UTC-hour tests updated with a zero-contribution
stub). `invariants --full` green.

Live pass: 17 open Kalshi CPI events across the 3 series, 3 matched to currently-listed
Polymarket events (current core-MoM/YoY/headline-MoM prints), 0 unmatched/ambiguous
Polymarket events, 22/28 buckets priced. The 6 unpriced buckets need Kalshi strikes further
out-of-the-money than its ladder currently lists (Polymarket's core-CPI-MoM/headline-CPI-MoM
events both extend one bucket past Kalshi's quoted range) — an honest, expected coverage gap,
correctly counted against `completeness_ok` rather than hidden. One bucket (`cpi_core_mom`
2026-07, exact 0.5%) came back with `monotonicity_violation: true` — Kalshi's raw ladder for
that far-forward month has a thin strike (`T0.5` priced ABOVE `T0.4`, which cannot be true in
a coherent market), the exact kind of thin/stale-quote artifact this project's discipline says
to record honestly rather than paper over. `kb/strategies/00-index.md` S17 note updated;
`LOOP-QUEUE.md` Q12 flipped FED-DECISION-LEG-DONE → full DONE. See tape at
`tape/polymarket_cpi_pairs/dt=2026-07-06.jsonl`.

**Next:** S17's own gate (≥5 matched live-book pairs/month) was already cleared by the Fed
leg; both Fed and CPI legs now run automatically at their appropriate cadence, so the only
remaining work is accumulation, then the eventual lead-lag cross-correlation (same shape as
S9, which was closed dead ✗ on data-adequacy grounds this run window — S17 doesn't share
that constraint since it needs no sub-hourly resolution).

## 2026-07-06 15:06 UTC — Agent team stood up + lessons ledger (compounding layer) + full tape audit

Ops run, Ryan-requested (interactive session, not a loop firing). Three things landed:

**1. Agent team (`.claude/agents/`).** A **Fable lead on high reasoning** (`research-lead`,
`model: fable`, `effort: high`) that plans, decomposes, and reviews but never edits files
itself, guiding five **Opus workers**: `collector-engineer` (collection modules + offline
tests, bitemporal/source-tag/honest-completeness discipline), `edge-prober` (one falsifiable
probe milestone per invocation, block-bootstrap by the independent unit, real-ask bar),
`verifier` (adversarial skeptic — re-runs the producing script and attacks provenance,
statistics, fees, and data windows before any number enters kb/ or findings/),
`kb-distiller` (owns the lessons ledger below, escalates UNENFORCED lessons into
invariants/tests), `tape-auditor` (read-only coverage/completeness/stranded-branch
reports). Every charter embeds the Stop rules and cites the precedent scripts, so a worker
starts from house discipline instead of rediscovering it. `LOOP-QUEUE.md` gained a
"Subagent roster" section wiring this into the run protocol.

**2. The compounding layer: `kb/lessons/00-lessons.md`.** The gap between "learned it the
hard way" and "it's a CI assertion" is where knowledge evaporated between stateless runs —
the ledger makes it visible. 17 lessons mined from the run history (L1 synthetic-never-a-
fill through L17 stranded-tape sweep), each with provenance and an **enforcement status**
(`invariant` / `test` / `protocol` / `UNENFORCED` / `ledger-only`); UNENFORCED rows are the
kb-distiller's standing work queue, and converting one into an assert is always an eligible
idle-run milestone. Append-only, supersede-by-reference, same trust rules as the rest of kb.

**3. Tape audit (`findings/2026-07-06-tape-audit.md`).** 29,363 lines / 10 families /
2026-07-02→07-06, all valid JSON, ~2 passes/hour landing (both collectors alive). All 12
incomplete crypto passes are ONE venue-side hole: Kalshi lists no hourly BTC/ETH group
during the 20 UTC hour, daily (new lesson L15). Step-0b sweep executed: 1,158 stranded
lines union-appended from 6 fallback branches. Eligibility from real tape days: Q7 ~Jul
09/10, Q13 ~Jul 12/13 (WC ends Jul 19 — S14's sports window is narrow). Tape is 36MB raw
and crosses the README's ~50MB decision point ~mid-July — Ryan's call, flagged not acted.

Gates: 297 tests green, `invariants --full` green. Explicitly NOT done: registering the
PreToolUse invariants hook in `.claude/settings.json` — attempted, permission-gated in this
harness, and PROVENANCE.md already reserves that wiring for Ryan's explicit approval; it
remains the one unwired piece of Tier-2 enforcement.

## 2026-07-06 UTC — Q8 closed: S9 lead-lag resolution decision (dead ✗, data-adequacy)

Research loop. Claim-check: `git fetch origin main` at `24b155f`, local branch already at
the real tip (hourly `tape:` passes only since the last run); open PRs unchanged — #4 still
claims Q1 (unrelated, awaiting `ODDS_API_KEY`), #18 is the weekly retro's protocol-amendment
proposal (never self-merged, left for Ryan). Queue scan against the real tip: Q1 claimed,
Q2/Q4/Q5/Q6/Q9/Q10/Q11 DONE, Q7/Q13 BLOCKED — **Q8 (IN-PROGRESS)** was topmost eligible.
Step 0b stranded-tape sweep: all currently-listed `tape/hourly-*` branches already fully
reconciled with `main` (0 missing lines across every family) — nothing to append this run.

Q8's own remaining-work note (from the 2026-07-06 05:17Z shock event-study, below) asked for
a resolution decision: either build a sub-hourly capture burst around the World Cup's
remaining matches, or accept the lead-lag question as untestable and mark it dead. Checked
the loop's actual scheduling primitives (`create_trigger`, `send_later`) before deciding:
recurring cron triggers are hard-capped at hourly minimum interval (the tool's own schema
states it) — no recurring sub-hourly poll is possible. One-shot triggers aren't
cadence-limited, but bracketing a match's real end-time with them needs a kickoff timestamp
the accumulated tape doesn't carry for KXWCROUND markets, and wiring up N one-shot captures
per remaining match (semis, final) is a new class of unattended multi-day automation — the
same category as the VPS collector and `ntfy-watch`, both stood up as Ryan-requested ops
changes, not something a research-loop run should decide alone. Building that unilaterally
is outside this milestone's scope.

**Verdict:** split S9 into its two sub-questions. **Lead-lag** (does one venue reprice first
around a shock?) → **dead ✗, data-adequacy** — not falsified by a CI (there's no bootstrap to
run on n=8 ticker-steps), just structurally untestable with hourly-minimum automation and no
kickoff-time signal to burst around. **Cross-venue parity** (do the two venues quote the same
price on average, right now?) → stays alive, already answered well by the 2026-07-04 first
cut (48/48 matched, +0.20¢ mean gap) and continues under S17's Fed-decision generalization,
which needs no sub-hourly resolution. Per the Stop rules, a DEAD verdict recorded honestly is
a success. No new code — a decision on already-collected evidence, not a new probe. 297
tests unchanged (pre-existing baseline), `invariants --full` green. `kb/strategies/00-index.md`
S9 flipped to dead ✗; `LOOP-QUEUE.md` Q8 flipped IN-PROGRESS → DONE. See
`findings/2026-07-06-polymarket-leadlag-s9-resolution.md`.

## 2026-07-06 05:17 UTC — Q8: first real shock event-study (S9 stays data-collecting)

Research loop. Claim-check: `git fetch origin main` at `a6567cf`, local branch already at
the real tip (only hourly `tape:` passes since the last run); open PRs unchanged — #4 still
claims Q1 (draft, unrelated, awaiting `ODDS_API_KEY`), #18 is the weekly retro's protocol-
amendment proposal (never self-merged, left for Ryan). Queue scan: Q1 claimed, Q2/Q4/Q5/Q6/
Q9/Q10/Q11 DONE, Q7/Q13 BLOCKED — Q8 (IN-PROGRESS) was topmost eligible, and this run's own
check of `tape/polymarket_pairs/` found something the last two runs didn't have: real round
transitions. `market_membership_changes()` showed two teams eliminated since the last cut —
Brazil and Mexico, both quarterfinal losses — so Q8's own remaining-work note ("once an
actual round transition lands, re-run and inspect that market's captures around the
transition specifically") was finally actionable instead of a repeat no-op.

Step 0b stranded-tape sweep first: of the `tape/hourly-*` branches, one
(`20260706T0256Z`, >30min old) carried lines `main` was missing — 2 `crypto_hourly` + 15
`polymarket_macro_pairs` + 36 `polymarket_pairs` + 182 `sports_pairs` (checked by exact
line-set diff per file against `origin/main`, union-deduped, every line validated as
parseable JSON) — union-appended into this run's commit. `git push origin --delete` still
fails from a cloud session (same permission boundary documented since 2026-07-03).

**Q8/S9 milestone.** Built `scripts/s9_shock_eventstudy.py`: isolates real transitions from
`market_membership_changes()` (excluding the one documented startup artifact — the diff
between the pre-wiring smoke-test capture and the first capture of continuous hourly
collection) and, for each ticker a transition removed from the open-markets set, reports the
last two captured rows on both venues (the actual repricing step — the capture at which a
ticker vanishes is not itself a price observation). Result across the 2 real events / 8
affected tickers: Kalshi and Polymarket moved together every single time — mean
`|Δkalshi − Δpolymarket|` 2.2¢, max 8¢, no consistent one-venue-leads pattern, both venues
already reflecting the outcome by the very next capture (30–60min later). Mexico's data
additionally showed the reprice trailing off over 2+ hourly captures rather than one clean
jump, still with both venues moving in lockstep at each step.

**The actual finding is methodological, not a null result on the thesis:** a match resolves
within minutes of the final whistle, but the collection cadence here is 30–60 minutes — too
coarse to ever resolve which venue moves first inside that window. S9's lead-lag thesis
cannot be tested at this resolution as built. 10 new unit tests (297 total, offline synthetic
fixtures), `invariants --full` green. `kb/strategies/00-index.md` S9 note updated, stays
`data-collecting`. Full writeup:
`findings/2026-07-06-polymarket-leadlag-s9-shock-eventstudy.md`.

**Next:** a resolution decision on S9 before the WC ends Jul 19 — either add a sub-hourly
capture burst around scheduled game-end times for the remaining matches (semifinals, final)
to actually test lead-lag, or accept this infrastructure only answers a cross-venue parity
question and mark the lead-lag angle a data-adequacy DEAD. Q7 unblocks ~2026-07-10, Q13
~2026-07-13; Q12's CPI/inflation leg and its own lead-lag accumulation are still open.

---

## 2026-07-06 00:22 UTC — Q12: Fed-decision leg built (S17 now data-collecting)

Research loop. Claim-check: `git fetch origin main` at `1337175`, local branch already at
the real tip; open PRs unchanged — #4 still claims Q1 (draft, unrelated, awaiting
`ODDS_API_KEY`), #18 is the weekly retro's protocol-amendment proposal (never self-merged,
left for Ryan). Queue scan: Q1 claimed, Q4/Q5/Q6/Q9/Q10/Q11 DONE, Q7/Q13 BLOCKED
(need ≥7/≥10 days of tape, not yet elapsed), Q8 (IN-PROGRESS) had only ~4h of new
accumulation since its 2026-07-05T20:09Z lead-lag cut (44 vs 37 captures, no round
transition) — rerunning it would have reproduced the same "still just noise" result with
barely more data. **Q12 (S17, TODO with unstarted real work)** was the topmost item where
this run's effort would actually move something forward, matching the precedent the prior
run itself named ("Q12 remains the topmost TODO item with unstarted real work if Q8 gets
skipped again before a shock arrives").

Step 0b stranded-tape sweep first: of 29 `tape/hourly-*` branches, 2
(`20260705T2155Z`/`2255Z`, both >30min old) carried lines `main` was missing — 4
`crypto_hourly` + 76 `polymarket_pairs` + 304 `sports_pairs` (checked by exact line-set diff
per file, union-deduped, every line validated as parseable JSON) — union-appended into this
run's commit. `git push origin --delete` still fails from a cloud session (same permission
boundary documented since 2026-07-03).

**Q12/S17 milestone.** Built `collection/polymarket_pairs.run_fed_decision()`: a second
Kalshi↔Polymarket discovery family (Fed rate-decision meetings) using the same match
discipline the WC-round leg already proved out, so cross-venue collection outlives the
World Cup. Kalshi's `KXFEDDECISION` 5-bucket meeting ladder (cut>25/cut25/no-change/
hike25/hike>25) matched to Polymarket's "Fed Decision in `<Month>`?" events by (meeting
month+year, bucket) — confirmed via each side's own title/question text, not the Kalshi
ticker's bps suffix alone (it uses `"26"` as a stand-in for ">25", confirmed live). One real
design call: completeness is graded against Polymarket's side, not Kalshi's — Kalshi lists
meetings ~18 months out (to January 2028) while Polymarket only creates an event closer to
it, so grading against Kalshi's full calendar would make this leg report FAIL forever, a
structural non-issue rather than a real one; a Polymarket market this pass fails to pair
(`unmatched_polymarket`) does still gate. Wired into `hourly_pass.py` as a fourth cross-venue
sub-pass, own tape family `tape/polymarket_macro_pairs/` (kept separate from the WC-round
tape — different record shape). 22 new unit tests, 287 total green, `invariants --full`
green. Live pass: **15/15 currently-listed Polymarket Fed-decision markets matched**
(Jul/Sep/Oct 2026 — the only meetings Polymarket has created so far), 0 ambiguous, 0 book
errors, `completeness_ok`; gaps ranged −3¢ to +15¢ across the 15 pairs (one snapshot,
descriptive only). CPI/inflation matching explicitly deferred — Kalshi's cumulative
"≥threshold" ladder and Polymarket's exact-bucket partition are different shapes; pairing
them would need a derived/synthetic transform, not a same-question `real_ask` pair, so it
isn't faked here. `kb/strategies/00-index.md` S17 flipped idea → data-collecting; its own
gate (≥5 matched live-book pairs/month) is already cleared by this one pass. Full writeup:
`findings/2026-07-06-fed-decision-macro-pairs-q12-first-cut.md`.

**Next:** accumulate hourly Fed-decision snapshots (already wired), then run a lead-lag
cross-correlation once enough history exists, same shape as `s9_leadlag_probe.py` — the
next FOMC meeting is a natural information shock to watch for. Q7 unblocks ~2026-07-10,
Q13 ~2026-07-13; Q8 (S9) still worth revisiting once a real round transition lands.

---

## 2026-07-05 20:09 UTC — Q8: first S9 lead-lag cross-correlation cut (zero in-window shocks found)

Research loop. Claim-check: `git fetch origin main` force-updated the local ref to `d1ae913`
(hourly `tape:` passes only since the last run); open PRs unchanged — #4 still claims Q1
(draft, unrelated, awaiting `ODDS_API_KEY`), #18 is the weekly retro's protocol-amendment
proposal (never self-merged by a loop run, left for Ryan). Queue scan: Q2–Q6/Q9/Q10/Q11 DONE,
Q7/Q13 BLOCKED — **Q8 (IN-PROGRESS)** was topmost eligible by the letter of the protocol; the
last several runs treated its "let snapshots accumulate" remainder as no-code-yet and skipped
to the next TODO, but by this run's time (~19h of continuous hourly-ish collection since the
2026-07-05T00:11Z wiring, 37 distinct captures) there was finally enough tape to actually
attempt the lead-lag cross-correlation Q8's own spec calls for — so this run did that instead
of skipping again.

Step 0b stranded-tape sweep first: of 27 `tape/hourly-*` branches, 2 (`20260705T155348Z`,
`20260705T1655Z`, both >30min old) carried lines `main` was missing — 4 `crypto_hourly` + 80
`polymarket_pairs` + 360 `sports_pairs` (checked by exact line-set diff per file, union-deduped
across both branches, every line validated as parseable JSON) — union-appended into this run's
commit. `git push origin --delete` still fails from a cloud session (same permission boundary
documented since 2026-07-03).

**Q8/S9 milestone.** Built `scripts/s9_leadlag_probe.py` (read-only over
`tape/polymarket_pairs/`): pools every consecutive-capture (Δkalshi_yes_ask,
Δpolymarket_best_ask) pair across the 40 markets with ≥10 captures into a lag-0/lag±1
cross-correlation — contemporaneous ρ **+0.293** (n=1,440), kalshi-leads-polymarket ρ +0.044,
polymarket-leads-kalshi ρ −0.007 (both n=1,400, both noise-level). More important than the
correlation numbers: `market_membership_changes()` — the honest proxy for "did a round
actually transition inside the window" — found **zero** in-window round-transition events; the
one membership change on record predates continuous hourly collection entirely (a
pre-wiring smoke-test artifact from 2026-07-04T15:15Z, not something that happened while the
collector was running). S9's actual thesis — does one venue visibly lag the other around a
real information shock (a team advancing or being eliminated) — is therefore **still
untested**; every tick observed so far is ordinary book noise on markets whose underlying
question hasn't resolved yet. No CI, no verdict claimed; explicitly reported as a
noise-floor characterization, not a lead-lag finding. 20 new unit tests (offline, synthetic
capture series incl. one hand-built market where polymarket is kalshi shifted by exactly one
step, confirming the pooled stat recovers the correct lag direction). 265 tests green (245
prior + 20 new), `invariants --full` green. `kb/strategies/00-index.md` S9 note updated
(stays `data-collecting`). See
`findings/2026-07-05-polymarket-leadlag-s9-first-cut.md`.

**Next:** keep accumulating hourly snapshots; re-run `s9_leadlag_probe.py` once an actual
round transition lands in the tape and inspect that specific market's captures around the
transition. Q12 (S17, retarget the matcher to recurring macro pairs) remains the topmost TODO
item with unstarted real work if Q8 gets skipped again before a shock arrives; Q7 unblocks
around 2026-07-10, Q13 around 2026-07-13.

---

## 2026-07-05 15:13 UTC — Q10: GDPNow nowcast leg built (S12 econ-print collector now fully DONE)

Research loop. Claim-check: `git fetch origin main` forced-updated the local ref (session
sandbox was stale) to `a5f1291`; open PRs unchanged from prior runs — #4 still claims Q1
(draft, unrelated, awaiting `ODDS_API_KEY`), #18 is the weekly-retro's own protocol-amendment
proposal (never self-merged by a loop run, left for Ryan). Queue scan: Q2–Q6/Q9/Q11 DONE,
Q7/Q13 BLOCKED, Q8's only remaining gap is letting hourly snapshots accumulate (no code) —
**Q10 (KALSHI LEG DONE, nowcast leg BLOCKED)** was the topmost eligible item with real work,
per the same precedent the last two runs used to skip Q8.

Step 0b stranded-tape sweep first: of 24 `tape/hourly-*`/amended branches, 22 were already
fully reconciled with `main` (checked by exact line-set diff per file, not just `git diff
--stat` — a pure stat diff would have wrongly flagged several already-merged branches as
"missing" content that was really just reordered/rewritten upstream); 2 (`20260705T1155Z`,
`20260705T1253Z`) had real gaps `main` lacked — 4 `crypto_hourly` + 80 `polymarket_pairs` + 389
`sports_pairs` lines (union-deduped across both branches, order preserved, every line
validated as parseable JSON before commit) — union-appended into this run's commit. The
newest branch (`20260705T1455Z`, ~13min old) was skipped per the freshness rule. `git push
origin --delete` still fails from a cloud session (same permission boundary documented since
2026-07-03).

**Q10 milestone.** Built the GDPNow leg of `collection/econ_prints.py`'s nowcast field
(`fetch_nowcast_gdp`/`parse_gdpnow_nowcast`), closing the one gap the Kalshi-leg-only version
left open. Confirmed live (2026-07-05) that the Atlanta Fed's GDPNow page embeds its entire
forecast history as three parallel JS arrays (`forecastDates`/`forecastQuarters`/
`gdpForecast`, ~1,900 entries back to 2014) grouped into quarter-blocks ordered
newest-quarter-first, each block internally date-ascending — so "the current nowcast" is
just the last entry whose quarter tag matches the array's first tag. Parser never fabricates:
a missing array, a length mismatch, an empty block, or a null latest value all surface as an
honest `parse_error`, not a stale or guessed number; a real network failure is `fetch_error`.
Tagged `synthetic` (a model estimate, not a Kalshi fill) per CLAUDE.md's trust defaults. Live
end-to-end check: current GDPNow read is **+1.19% annualized for the quarter ending
2026-06-30, as of its 2026-07-01 update** (27 updates so far that quarter) — descriptive only,
not yet joined against Kalshi's `KXGDP` ladder (that join is S12's eventual gate work, not this
milestone's job). The Cleveland Fed CPI-nowcast leg stays `not_built` as before — its page has
no scrapable static data, a genuinely different blocker than GDPNow's (which just needed the
array-slicing logic this run built), so it isn't reattempted.

7 new unit tests (offline, synthetic HTML fixtures — parser edge cases, fetch-error handling,
and the `gdp` vs everything-else routing in `fetch_nowcast`) plus one existing test
(`test_run_two_series_independent`) updated to inject a stub GDP fetcher so it stays network-free.
245 tests green (238 prior + 7 new), `invariants --full` green. `kb/strategies/00-index.md` S12
row unchanged (still `data-collecting` — the nowcast leg unblocks future analysis, it isn't
itself a verdict). Q10 flipped from "KALSHI LEG DONE" to full **DONE**.

**Next:** Q12 (S17, retarget the Kalshi↔Polymarket matcher to recurring macro pairs) is the
topmost remaining TODO with real work; Q7 unblocks around 2026-07-10, Q13 around 2026-07-13.

---

## 2026-07-05 06:08 ET — Q11: cross-event logical-implication scanner built (S15 idea → data-collecting)

Research loop. Claim-check: sandbox branch was already at `origin/main`'s real tip (hourly
`tape:` passes only since the last run); only open PR (#4) still claims Q1 (draft, unrelated,
awaiting `ODDS_API_KEY`). Queue scan: Q2/Q3/Q4/Q5/Q6/Q9/Q10 DONE, Q7/Q13 BLOCKED, Q8's only
remaining gap is letting hourly snapshots accumulate (no code) — **Q11 (S15, TODO)** was the
topmost eligible item with actual work.

Step 0b stranded-tape sweep first: of 21 `tape/hourly-*` branches, 4 (all >30min old) carried
lines `main` was missing — 8 `crypto_hourly`, 160 `polymarket_pairs`, 816 `sports_pairs` —
union-appended into this run's commit (checked: 0 exact-duplicate lines, every appended line
valid JSON). The newest branch (~12min old) was skipped per the freshness rule. `git push
origin --delete` still fails from a cloud session on every branch (same permission boundary
documented since 2026-07-03) — redundant branches persist, harmless.

**Q11 milestone.** Extended `scripts/anomaly_sweep.py` (Q6) with a third real-ask check,
`check_cross_event_implication`, and a new config file, `config/implication_pairs.yaml` — the
"hand-curated implication graph" Q11 called for. Unlike Q6's existing `cross_strike_monotonicity`
check (which proves nesting because both legs share one `event_ticker`), a cross-event pair
can't lean on that structural shortcut — the config's job is to hold, per family, the actual
audit of both markets' settlement rules text that proves A ⇒ B. One family is populated so
far: `kxwcround_progression` — for Kalshi's `KXWCROUND` series ("Will `<team>` qualify for
FIFA World Cup `<round>`?", the same grammar `collection/polymarket_pairs.py` already
discovers+confirms structurally), reaching a later round in a single-elimination bracket is a
strict superset of reaching every earlier round for the *same* team — no settlement-term
mismatch is possible within one entity/series, which is exactly the audit the config's `audit`
field records. Q11's own second example ("wins presidency" ⇒ "wins nomination") has no
matching live Kalshi series yet; left as a documented TODO in the config rather than guessed
at.

The check itself reuses `core.pricing.monotonicity_crossing_edge` completely unchanged — same
fee-floor math Q6's check 2 already uses (buy YES(B) + NO(A), A = harder/narrower round, B =
easier/wider round, hit when the combined cost clears below $1 net of both legs' taker fees).
10 new unit tests cover the pair-generation logic (one entity's full round chain, non-matching
series ignored, missing prices skipped, unknown family kinds skipped) plus the config loader;
2 more wire it into `run()`'s existing tape record (`n_implication_pairs_checked` alongside the
existing `n_bracket_groups_checked`/`n_monotonicity_groups_checked`). No `hourly_pass.py` change
needed — same as Q6, the third check just runs inside the same subprocess call already wired
into the daily 09 UTC slot.

Live-validated directly against Kalshi's real, currently-open `KXWCROUND` markets (bypassing
the platform-wide sweep's pagination, which doesn't reach WC tickers within a bounded
`--limit`): 40 open markets, 38 generated round pairs, **0 fee-clearing hits** — expected,
matching Q6's and Q8's own "real arbs are rare" precedent, and the sampled pair confirms the
check discriminates correctly (Team USA: SEMIFINALS priced 19¢ vs QUARTERFINALS' 52¢ — properly
monotonic, harder round cheaper). `kb/strategies/00-index.md` S15 flipped `idea` →
`data-collecting`; kill condition (per registry, dated from this run) is 0 fee-clearing hits in
60 days of the existing daily sweep. 238 tests green (228 prior + 10 new), `invariants --full`
green.

**Next:** Q12 (S17, retarget the Kalshi↔Polymarket matcher to recurring macro pairs) is next
in queue order; Q7 unblocks around 2026-07-10 (needs ≥7 days of Q2 crypto tape).

---

## 2026-07-05 05:19 UTC — Q10: econ-print (CPI/payrolls/GDP) collector built — Kalshi leg DONE, nowcast leg BLOCKED

Research loop. Claim-check: `git fetch origin main` at `9de63e2` (only hourly `tape:` passes
since the last run); only open PR (#4) still claims Q1 (draft, unrelated, awaiting
`ODDS_API_KEY`). Queue scan: Q2/Q3/Q4/Q5/Q6/Q9 DONE, Q7/Q13 BLOCKED (tape not old enough),
Q8 IN-PROGRESS but its only remaining gap is letting hourly snapshots accumulate (no code to
write) — **Q10 (S12, TODO, time-sensitive)** was the topmost eligible item with actual work.

Step 0b stranded-tape sweep first: of 17 `tape/hourly-*`/`tape/hourly-amended-*` branches, 15
were fully reconciled with `main` already (0 missing lines, verified line-by-line against the
real `origin/main` tip); 2 branches (`20260704T2355Z` 181 lines, `20260705T0055Z` 256 lines —
both >30min old) had lines `main` lacked, union-appended into this run's commit; 1 branch
(`20260705T0455Z`, ~13min old) skipped per the freshness rule. `git push origin --delete`
remains blocked from a cloud session (same documented permission boundary) — redundant
branches persist, harmless.

**Q10 milestone.** Live API discovery confirmed 5 flagship econ-print series
(`/series?category=Economics` + a structural check against `/markets`): `KXCPI` (CPI MoM),
`KXCPIYOY`, `KXCPICORE` (core CPI MoM), `KXPAYROLLS` (nonfarm payrolls), `KXGDP` (real GDP QoQ).
All 5 are NESTED MONOTONIC "will the print exceed threshold T" ladders sharing one
`event_ticker` per release — structurally different from `crypto_hourly`'s KXBTC/KXETH
complete-partition brackets — so `core.pricing.bracket_sum` (the sanctioned Hard-Rule-#3 site
for partitions) is deliberately NOT called here; each strike's `yes_ask` is persisted as its
own `real_ask`, nothing summed/normalized (the nested-threshold arb shape these ladders DO
admit is already covered platform-wide by Q6's `cross_strike_monotonicity`).

Built `collection/econ_prints.py`: (1) **open_events** — every open event_ticker per series,
full per-strike real_ask ladder, honest expected-vs-captured completeness; (2)
**recent_settlement** — the single most-recently-settled event per series, Kalshi's own
`result` + `expiration_value` (the actual published BLS/BEA print, confirmed live — e.g. CPI
MoM settled at "0.5", payrolls at "57,000") tagged `broker_truth`. Kalshi purges settled
markets ~60 days after close (S7a finding) — this leg runs every pass regardless of the open
ladder so no release is lost. 12 new unit tests (offline, FakeClient). Live pass: all 5 series
`pass_complete` (24 open events / 296 strikes captured, settlement resolved for all 5,
including CPI MoM/YoY/core, payrolls, and GDP). Wired into `collection/hourly_pass.py`'s
existing 09-UTC-only slot (alongside `anomaly_sweep`) since releases are infrequent — a daily
cadence is what the spec asked for; 9 hourly_pass tests updated with a zero-contribution
econ_prints stub, 4 new tests added for the wiring itself.

**Nowcast leg (Cleveland Fed CPI / GDPNow) left BLOCKED(nowcast-scrape), same shape as Q1's
odds-api leg.** Checked live: the Cleveland Fed inflation-nowcasting page renders its number
client-side with no static data or discoverable API in the served HTML. Atlanta Fed's GDPNow
page DOES embed its full forecast history as raw JS arrays
(`gdpForecast`/`forecastDates`/`forecastQuarters`) — scrapable in principle — but reliably
slicing the current quarter's window out of that structure is nontrivial and left for a
follow-up pass rather than forced this run. Every record's `nowcast` field is an honest
`{"status": "not_built"}`, never a fabricated placeholder — the S12 gate (≥20 releases +
nowcast comparison) still needs this leg before any edge can be scored, but the URGENT,
purge-at-risk half (the Kalshi ladders + settlements) is now collecting.

228 tests green (212 prior + 16 new: 12 for `econ_prints` + 4 for the `hourly_pass` wiring),
`invariants --full` green. No findings doc (collection
infrastructure, not a strategy verdict yet) — `kb/strategies/00-index.md` S12 updated to
`data-collecting`; `LOOP-QUEUE.md` Q10 status updated.

---

## 2026-07-04 20:14 ET — Q8: polymarket_pairs wired into the hourly collector; stranded-tape sweep

Research loop. Claim-check: `git fetch origin main` at `092196c` (only hourly `tape:` passes
since the last run); open PR #4 still claims Q1 (draft, unrelated, awaiting `ODDS_API_KEY`).
Queue scan: Q2/Q3/Q4/Q5/Q6/Q9 all DONE, Q7/Q13 BLOCKED (tape not old enough yet), Q1 claimed —
**Q8 (IN-PROGRESS)** was the topmost eligible item.

Step 0b stranded-tape sweep first, and caught a bug in the sweep itself: an earlier `git diff`
comparison used this sandbox's *local* `main` ref, which was stale at 2026-07-02 (two days
behind `origin/main`) — every one of the 15 `tape/hourly-*` branches looked like it had
thousands of "missing" lines vs that stale ref, including in files the hourly collector never
touches (`sports_history`, `sports_clv`, `sports_maker_fillsim` — outputs of one-off research
scripts, not append-only collector tape). Re-pointed local `main` at `origin/main` before
trusting any diff. Against the real tip, 12 of 15 branches were already fully reconciled by
the prior run (0 missing lines); 3 branches (`20260704T1955Z`/`2055Z`/`2155Z`) had a combined
**8 crypto_hourly + 536 sports_pairs lines** `main` was missing — union-appended into this
run's tape files (verified: append-only, no reordering, every new line still valid JSON). One
branch (`20260704T2355Z`, ~19min old) skipped per the 30-min freshness rule. `git push origin
--delete` still fails from a cloud session on every branch (same permission boundary as
documented 2026-07-04) — redundant branches remain, harmless.

**Q8 milestone.** Wired `collection/polymarket_pairs.py` into `collection/hourly_pass.py` as a
third sub-pass (alongside `sports_pairs`/`crypto_hourly`), same fault-isolation discipline: its
own exception never takes the other two down, and its own honest `completeness_ok` (computed
inside `polymarket_pairs.run` itself — matched-count, book-fetch, and ambiguity checks) ANDs
into the overall signal exactly like the other two. Each matched (round, team) pair counts as
one Kalshi market contract for `n_markets`/`n_lines` accounting, consistent with the module's
existing convention. 2 new offline unit tests (`test_run_polymarket_incomplete_marks_overall_incomplete`,
`test_run_polymarket_raises_others_still_run`); all 9 existing `hourly_pass` tests updated to
inject a zero-contribution polymarket stub so they keep testing sports/crypto math in
isolation. Live smoke (`python -m collection.hourly_pass --sports-limit 2 --crypto-symbols
BTC`): polymarket sub-pass fired for real, 40/40 Kalshi round markets matched to Polymarket,
completeness ok — proof the wiring works end-to-end, not just against stubs. This closes Q8's
main remaining gap (World Cup ends Jul 19 — every hour without a snapshot was a data point lost
for good); the lead-lag cross-correlation itself still needs the accumulated repeated-snapshot
history to build up over the coming days.

212 tests green (210 prior + 2 new), `invariants --full` green. No new findings doc (this is
collection infrastructure, not a strategy verdict) — `kb/strategies/00-index.md` unchanged;
`LOOP-QUEUE.md` Q8 status updated.

---

## 2026-07-04 20:08 UTC — Q9/S13 maker fill-sim TESTED → DEAD (null result); stranded-tape sweep

Research loop. Claim-check: only open PR (#4) claims Q1 (unrelated, awaiting `ODDS_API_KEY`) —
Q9 (S13) was the topmost eligible TODO. Step 0b stranded-tape sweep first: of 12
`tape/hourly-*` fallback branches, 10 were fully redundant with `main` (verified line-by-line,
0 missing); 1 (73min old) had 187 lines `main` lacked (union-appended into this run's commit);
1 (~13min old) skipped per the freshness rule. Note: `git push origin --delete` failed on
every branch — the same permission boundary blocking `push origin main` also blocks remote
branch deletion from a cloud session, so the redundant branches remain (harmless, but Ryan or
a session with delete rights should prune them eventually).

**S13 built and tested.** `scripts/s13_maker_fillsim.py`: the mirror-image test to S7's
already-proven taker-side result — rest a bid at DraftKings-close-devig fair minus 1¢, does a
real trade ever cross at/below it between the market's `open_time` and the game's actual
kickoff (hourly candlestick `price.low_dollars`, not the ask low)? Live pass over the
accumulated `tape/sports_clv/` + `tape/sports_history/` dataset (n=80 games) plus one new live
(cached) Kalshi candlestick pull per outcome ticker: **94.1% fill rate** (223/237 priced
outcomes), but `edge_after_fee` conditional on fill block-bootstraps to **+0.00009, 95% CI
[−0.00021, +0.00039]** — straddles zero. **Verdict: DEAD**, and a genuinely different flavor
of dead than S7/S8: not falsified on the wrong side, just a wash. The mechanism is structural:
Kalshi's maker fee (0.0175, not the 0.07 taker rate) is itself close to 1¢/contract across
most of this dataset's bid-price range, so it alone eats almost the entire assumed penny of
edge before any real market effect (adverse selection, informational drift) gets a chance to
matter — separately measured via DraftKings' open-vs-close line move, that drift was a
favorable but tiny +0.00168, an order of magnitude too small to rescue the point estimate.

**Two bugs caught and fixed before the verdict was final** (both would have understated the
edge or wasted disk, not overstated an edge — caught by testing/re-checking, not by luck):
(1) a first draft called `core.pricing.fee_per_contract` with its default taker rate (0.07)
instead of the maker rate the situation actually calls for (0.0175) — a 4x fee overcharge that
made the first live run look clearly negative (−0.00614 point, CI [−0.00683,−0.00542]) before
the fix flipped it to the true near-zero result; (2) a first cache design persisted every raw
candlestick per ticker and hit **98MB for 237 tickers** (several World Cup moneyline markets
open 4+ months before kickoff — one ticker's `open_time` was February for a June game) —
trimmed the cache to just the window's minimum trade price and its timestamp (93KB, same
237 tickers), and fixed an O(n²) bug where the cache file was being fully re-read from disk on
every single ticker lookup instead of once per run.

22 new unit tests (`tests/test_s13_maker_fillsim.py`, fully offline — candlestick fetch always
injected), 210 tests green, `invariants --full` green (one false-positive catch along the way:
a docstring's prose "OHLC/yes_ask/yes_bid" tripped the Hard-Rule-#3 arithmetic scanner via the
literal `/yes_ask` substring — reworded, not suppressed). `kb/strategies/00-index.md` S13
flipped to `dead ✗`; S1/S5/S7/S8/S13 are now all decided at real asks, none live. Full
writeup: `findings/2026-07-04-sports-maker-s13-verdict.md`.

## 2026-07-04 16:20 UTC — Loop health audit, stranded-tape recovery, and candidate restock S12–S18

Interactive session (Ryan-requested): verify today's scheduled runs, the memory system, and
that R&D has runway. Three findings, three fixes:

1. **Triggers healthy.** All three loop triggers verified enabled and firing on schedule
   today — hourly collector (last fired 15:53 UTC), 5-hourly research loop (last 15:07 UTC,
   next 20:07), weekly retro (Sundays 12:00, next tomorrow). The VPS collector's :23 passes
   are landing on `main` every hour.
2. **Stranded tape recovered + protocol hardened.** The cloud collector's `git push origin
   main` fails intermittently (same permission boundary the research loop hit 2026-07-03) and
   its fallback branches were accumulating unnoticed: 10 passes across Jul 3–4 (15:55, 19:54,
   20:55, 21:55 / 00:54, 05:54, 09:54, 10:55, 12:54, 14:54 UTC) never reached `main` — a real
   hole in the canonical tape and in Q7's "days of tape" clock. Union-appended all **1,674
   missing lines** (20 crypto_hourly, 1,654 sports_pairs) into the per-day files with two-way
   verification, and added protocol step **0b** to LOOP-QUEUE.md so every research run sweeps
   `tape/hourly-*` branches automatically from now on. Swept branches deleted after merge.
3. **Queue was one item from dry — restocked.** Only Q8 was eligible (Q7 blocked to ~Jul 10;
   Q1 claimed by draft PR #4 awaiting `ODDS_API_KEY`). Ran a full generation pass (19 raw
   lens-rotated ideas → adversarial cut rejected 12 → 7 survivors): **S12–S18** appended to
   the registry — econ-print nowcast overlay (S12), the maker/bid side of S7's proven sports
   rich-ask (S13), ladder-overround underwriting (S14), cross-event implication scanner (S15),
   FedWatch-anchored shock fade (S16), Polymarket-macro parity (S17), single-poll fade (S18).
   Full dossier: `findings/2026-07-04-edge-candidates-s12-s18.md`. Queue items **Q9–Q13**
   appended (S13, S12, S15, S17, S14 in that order) — the loop now has ~a week of eligible
   milestones. Ryan's one open action: paste `ODDS_API_KEY` into the VPS env to un-block Q1.

Note: ntfy.sh is egress-blocked from this sandbox (HTTP 000 on CONNECT), so loop health was
verified from git history + trigger state instead of the phone feed.

## 2026-07-04 15:15 UTC — Q8 (new): Kalshi↔Polymarket World Cup round-market collector built (S9)

Claim-check: `git fetch origin main` in sync at `640da43` (only hourly `tape:` passes
since the last research run); the only open PR (#4) still claims Q1's odds-api leg
(unrelated, waiting on `ODDS_API_KEY`). But this time Q2 through Q6 are all DONE and Q7 is
BLOCKED (needs ≥7 days of Q2 crypto-hourly tape; only 2 days have accumulated) — **no
queue item was eligible** for the first time this project has hit that state. Per
LOOP-QUEUE.md's own append-don't-rewrite rule, appended Q8 and started the next
un-started registry candidate (S9) instead of ending the run early.

**Why S9, and why it's tractable now:** S9 (Kalshi↔Polymarket same-question lead-lag) was
idea-stage since 2026-06-18, blocked in spirit by "which same question exists on both
venues, priced the same way." Checked Polymarket's public API live and found a clean
match: Kalshi's `KXWCROUND` series ("Will `<team>` qualify for FIFA World Cup `<round>`?")
and Polymarket's "World Cup: Nation To Reach `<round>`" events are the IDENTICAL Yes/No
question on both venues — one binary market per (round, team), no de-vig needed (unlike
S7's moneyline-vs-sportsbook-odds), because both sides are already a single fillable price.

**Built `collection/polymarket_pairs.py`.** Kalshi leg: existing `Kalshi` client against
`KXWCROUND` (ticker grammar `KXWCROUND-<round_raw>-<team_code>`, title carries the full
team name). Polymarket leg: discovered via its public `/public-search` endpoint (a keyword
narrows the API-call budget, same role as `_SERIES_TITLE_RE` in `sports_pairs.py`), then
every hit is structurally re-confirmed by title/round regex before being trusted — no
hardcoded event IDs. Matched by exact (round, normalized team name); anything that doesn't
line up 1:1 is recorded `unmatched`/`ambiguous`, never guessed. Polymarket prices come off
its live CLOB order book (`clob.polymarket.com/book`, tagged `real_ask` — a real fillable
book, NOT the `outcomePrices` field on the market list, which is a last-trade/mid
reference and would have been a Hard-Rule-#4 violation to treat as a fill).

20 new unit tests (offline: FakeClient for Kalshi, monkeypatched `requests.get` for
Polymarket, injected `pm_discover`/`fetch_book` for the full `run()` pass — no network in
CI). Live pass against production: **48/48 open Kalshi `KXWCROUND` markets matched** to a
Polymarket counterpart, completeness ok, mean `price_gap_yes_ask` (Kalshi yes_ask minus
Polymarket best_ask) **+0.20¢**, range −3¢ to +3¢ — small and roughly symmetric on this
single snapshot, purely descriptive, not a verdict of any kind yet. `kb/strategies/00-
index.md` S9 flipped idea → data-collecting. 189 tests green (169 prior + 20 new),
`invariants --full` green.

**Next:** wire this into Q3's hourly pass so repeated snapshots accumulate (World Cup ends
Jul 19 — a narrow window), then run an actual lead-lag cross-correlation once there's
enough tape; the single-snapshot gap above says nothing about which venue moves first.

---

## 2026-07-04 10:30 UTC — Q6: daily anomaly sweep built (S3 + free-money detection)

Claim-check: `git fetch origin main` in sync; the only open PR (#4) still claims Q1's
odds-api leg (draft, waiting on `ODDS_API_KEY`) — skipped Q1. Every other candidate with a
completed first cut is now DEAD or gated, so Q6 (daily anomaly sweep) was the topmost
eligible TODO — the last unbuilt collector, and the first genuinely fresh candidate source
since S1/S5/S7/S8 all died to the overround.

**Built `scripts/anomaly_sweep.py`.** Discovers via `/markets?status=open` with NO
category/series filter — every active market on the platform, matching the item's own
wording, not just weather/crypto/sports. Two checks, both gated on a REAL fillable arb (a
cost strictly under $1 net of taker fees), not just an implied-probability curiosity:

1. **bracket_arb** — a complete strike ladder (a "less" catch-all + contiguous "between"
   bands + a "greater" catch-all, the exact shape Q2 found on KXBTC/KXETH) under one
   event_ticker whose yes_asks sum under $1+fees. Only scored when the sorted segments
   bookend the full real line (-inf..+inf) with no gap wider than the observed 2-cent
   Kalshi tick — an event missing an open-ended tail, or with a hole (one sibling market
   already closed), can't prove exhaustiveness and is skipped, not guessed at.
2. **cross_strike_monotonicity (S3)** — for nested "greater"/"less" threshold markets
   (e.g. temp>=80 subset of temp>=70), buying YES(wider)+NO(narrower) — both REAL asks,
   never a bid-derived synthetic price — pays a guaranteed >=$1 whenever that costs under
   $1 net of both legs' fees. An ask-vs-ask gap alone (the naive read of "monotonicity
   violation") can be closed by an unfilled quote; this is the fillable bar instead.

Added the fee/edge math (`fee_per_contract`, `true_arb_edge`, `monotonicity_crossing_edge`)
to `core/pricing.py` — the sanctioned Hard Rule #3 site, alongside `bracket_sum`.

**Real-world surprise the live pass surfaced:** Kalshi's open-market count is far larger
than any prior collector in this repo had touched — 10,000+ markets inside the first 10
pages alone, cursor still unexhausted. A genuinely unbounded pull grew this sandbox's RSS
past 3GB before it was capped. `main()` now defaults to `--limit 20000` (a real memory/time
bound, not a scope judgment call) and every tape record carries an honest
`markets_truncated` flag — a capped pass never claims full coverage it didn't do. `--limit
0` opts into an unbounded run for a box with more headroom (the VPS collector, say).

**Live-validated the pipeline against real data, not just fixtures.** Pulled KXBTC's actual
188-member current-hour ladder directly and ran it through `check_bracket_arb`: bracket_sum
**7.78**, correctly NOT flagged (edge deeply negative after fees) — this matches Q2/Q5's
already-documented "fine $100-band, 1¢-minimum-ask" structural overround, not a new
anomaly, confirming the check doesn't cry wolf on a known non-arb shape. Three capped live
sweeps (300 / 3,000 / 20,000 markets), all `completeness_ok`, 0 anomalies flagged — expected,
real cross-market arbs are rare by construction. No live multi-member "greater"/"less"
group turned up in the small weather sample probed to exercise `cross_strike_monotonicity`
end-to-end on production data; that check is proven correct via realistic synthetic
fixtures instead and will fire automatically the day the accumulating sweep tape contains
a real crossed pair.

**Wired into Q3's 09 UTC slot with zero code changes** — `hourly_pass.py` already invoked
`scripts/anomaly_sweep.py` as a subprocess by path, reporting `not_built` only because the
file didn't exist yet; it now runs for real every day at 09 UTC.

22 new unit tests (17 in `tests/test_anomaly_sweep.py`, offline `FakeClient` fixtures +
5 pricing tests in `tests/test_substrate_primitives.py`), 169 tests green, `invariants
--full` green. `kb/strategies/00-index.md` S3 moved `binding-test-defined` →
`data-collecting` (the sweep now runs daily; a verdict needs accumulated tape, same as
S7/S8 needed theirs).

**Next:** let the daily 09 UTC sweep accumulate tape in `tape/anomalies/`; once enough
days/passes exist, bootstrap S3's actual edge frequency×magnitude the same way S7c/S8 did.
No other candidate has a fresh angle right now — everything else is DEAD or blocked on
external inputs (Ryan's `ODDS_API_KEY` for Q1's odds leg, CME data for S2, the FEx tape
archiver for S4).

---

## 2026-07-04 05:20 UTC — Q5: S8 crypto-basis verdict — DEAD (ρ-guard kill)

Claim-check: `git fetch origin main` showed only hourly `tape:` passes since the last
research run; open PR #4 still claims Q1's odds-api leg (draft, waiting on
`ODDS_API_KEY`) — skipped Q1. Re-verified egress directly (`curl` to Kalshi, Coinbase
spot, and Coinbase's historical `/candles` endpoint) — all 200, including the exact host
that was 403'd last run. That's the unblock Q5 was waiting on, so picked it up as the
topmost eligible item.

**Fixed the lag confound Q5 flagged as the actual problem.** Added a `--historical-spot`
mode to `scripts/s8_basis_probe.py`: for each of the 36 unique settled hours accumulated
in `tape/crypto_hourly/` (18/symbol, up from 13), fetch Coinbase's free 1-minute candle
for the exact bucket at the settlement boundary instant instead of reusing the already-
lagged live `spot` snapshot. All 36 fetches landed an exact-epoch bucket match (Kalshi's
hourly grid always lands on a UTC minute) — lag drops from a mean ~1650s to **0s**
everywhere. Fetches are cached (`synthetic`-tagged, sha256'd) to
`tape/crypto_hourly_historical_spot/` so reruns don't refetch. Also caught and fixed a
latent unit bug while in this code: the half-band-crossing check used a fixed $100 width
for both symbols, but ETH's ladder actually steps $20 (confirmed from the tape's own
`floor_strike` spacing) — now per-symbol.

**Result: the ρ-guard, run for real this time, kills S8.** Corrected ρ: BTC 0.963→**0.9997**,
ETH 0.947→**0.9998** — the same territory as S5's weather NWS-vs-WU 0.99999 kill. More
decisive than ρ alone: the max observed settle-vs-spot gap **never crosses half a bracket
width for either symbol** across all 18 hours each (BTC worst $38.93 of a $50 half-band;
ETH worst $0.94 of a $10 half-band). One honest nuance: BTC's gap is small but not
zero-centered (mean +$16.43, 17/18 hours positive) — plausibly a real, small structural
premium of the CF Benchmarks settlement index over raw Coinbase spot — but it's an order
of magnitude below the bracket width, so it never would have flipped a settlement outcome
relative to naive spot-watching in this sample.

**Verdict: S8 DEAD.** This is the guard's own designated cheap-kill gate triggering clean,
same mechanism as S5 — no bootstrap needed to reach it. n=18/symbol is thin (a first-cut
kill, not a large-sample proof), noted plainly, but there's no case for more Q5 data
collection. `kb/strategies/00-index.md` S8 flipped to `dead ✗`. 7 new unit tests
(`tests/test_s8_basis_probe.py`, offline/monkeypatched HTTP — the new fetch/cache/report
logic is genuinely testable, unlike the pure-analysis code the rest of the probe already
had); 147 tests green, `invariants --full` green. Full writeup:
`../findings/2026-07-04-crypto-basis-s8-verdict.md`.

**Next:** every candidate with a completed first cut is now DEAD (S1, S5, S7, S8) or
gated/blocked (S2, S3, S4, S7's maker side, S9-S11). Q6 (daily anomaly sweep) is the
topmost untouched TODO item and the most promising near-term source of a fresh candidate.

---

## 2026-07-04 00:12 UTC — Q4/S7c: sports CLV verdict — DEAD

Claim-check: main had advanced (hourly tape + merged PR #7 adding the check-ntfy skill and
Q5's writeup); rebased clean. Open PR #4 still claims Q1's odds-api leg (draft, waiting on
`ODDS_API_KEY`) — skipped Q1, picked up Q4 (topmost eligible IN-PROGRESS item, S7c was the
one remaining sub-stage).

**Accumulated the rest of the tournament.** S7b's join ran on a partial Kalshi tape (25
`KXWCGAME` events) because the original fetch used a low page limit. Re-fetched with
`--limit 100`: Kalshi actually retains **87 settled World Cup games** end-to-end so far
(Jun 11 group stage through Jul 3). Re-fetched ESPN closing odds for the matching window
and re-ran the join: **77/87 matched**, 0 ambiguous, 0 unparseable (S7b's 27/27 match rate
on a narrower window generalizes cleanly to the wider one). Combined with S7b's 3 already-
joined NBA games (deduped by `kalshi_event_ticker`, no new NBA fetch this pass): **80
unique priced games, 237 priced outcomes** — about 3x S7b's descriptive n.

**Ran the binding test.** New read-only `scripts/s7c_sports_clv_bootstrap.py` (no network;
reads `tape/sports_clv/*.jsonl`) block-bootstraps `edge_after_fee` (DraftKings-close de-vig
fair prob minus Kalshi's real pregame ask minus the taker fee) **by game** — not by
outcome, since a game's 2-3 outcomes share one de-vig and one kickoff and are not
independent draws. 10,000 resamples: mean **−0.0235**, 95% CI **[−0.0245, −0.0225]**. Both
bounds sit clearly below zero — this isn't a near-miss, Kalshi's pregame ask is running
richer than the DraftKings-implied fair price by more than the fee covers.

**Verdict: S7 is DEAD** (taker side, vs DraftKings-close) — CLAUDE.md's bar is a CI that
clears zero, and this one doesn't just fail to clear it, it sits confidently on the wrong
side. Per the Stop rules a DEAD verdict from a real, block-bootstrapped test is a success:
it's decided, `kb/strategies/00-index.md` S7 flipped to `dead ✗`, and the loop stops
spending cycles on it. Two things this verdict does *not* cover, flagged for anyone
revisiting the sports family: the maker/bid side of the same mispricing (a different trade,
untested here), and what happens with a sharper (Pinnacle) fair-price anchor if one ever
becomes free — DraftKings retail vig is a documented, not eliminated, source of noise in
`fair_prob`.

0 new unit tests (pure read-only analysis script over existing tape, same precedent as
`s8_basis_probe.py`/`longshot_fade_probe.py` — probes aren't unit-tested, collectors are);
140 tests green (unchanged), `invariants --full` green. Full writeup:
`../findings/2026-07-04-sports-clv-s7-verdict.md`.

**Next:** S8 (crypto-hourly settlement basis) is now the most-advanced open candidate —
still blocked on the ρ-guard needing historical-candle spot instead of lagged live spot;
Q6 (daily anomaly sweep) is the topmost untouched TODO item.

---

## 2026-07-03 23:34 UTC — Q5: S8 crypto-basis first cut — overround flag resolved, ρ-guard inconclusive

Claim-check: only open PR (#4) is Q1's unrelated odds-api work — Q5 unclaimed, picked it up.
Built `scripts/s8_basis_probe.py`, a read-only pass over the `tape/crypto_hourly/` tape Q2
already accumulated (13 unique settled hours each for BTC/ETH so far). Two questions, one
resolved and one blocked:

**Resolved — the +$9.27 BTC overround flag from Q2 is mostly real, not a floor-tick
artifact.** Deep out-of-the-money bands pinned at Kalshi's 1¢ minimum ask do inflate the
number (a coherent market prices them near $0, not $0.01), but they only account for **33.9%**
of BTC's mean +$5.00 overround across 19 passes — **66.1% comes from genuine near-the-money
spread**, the bands S8's eventual basis trade would actually touch. ETH splits closer to even
(56.9%/43.1% — its ladder has roughly a third as many outcomes, so the floor bands carry
proportionally more weight). Either way: the overround is a legitimate cost benchmark, not an
artifact to explain away.

**Blocked — the ρ-guard itself couldn't be run as the queue specified.** The queue's own
phrasing ("public candlesticks... vs public spot **history**") calls for spot sampled at the
settlement instant; what `crypto_hourly.py` actually pairs is Kalshi's exact settlement value
against whatever Coinbase/Kraken printed whenever that hour's *pass* happened to run — a mean
**29-minute lag** (VPS `:23`/cloud `:53` cadence vs on-the-hour settlement). Over 29 minutes
ordinary BTC volatility can move price well past $100, which fully explains the observed
gaps (max $150.41, 84.6% of hours over half a $100 band) without invoking any real BRRNY-vs-
spot mismatch — a naive ρ on price *levels* is also close to a foregone 1.0 regardless
(two price series tracking the same asset correlate on trend alone; not the same situation
as the weather NWS/WU check, which compared two co-located sensors). Tried the fix — pull
Coinbase's free, keyless historical `/candles` endpoint at each settlement's exact
`close_time` — but this session's egress is currently blocked to every external host tested,
including Kalshi's own API (403 on the CONNECT tunnel, confirmed via the proxy's own status
endpoint, not a code bug).

**S8 stays `data-collecting`, not DEAD.** Unlike S1/S5 this isn't a CI failing to clear zero
— no valid CI exists yet because the paired data doesn't answer the right question. This is
also a standing finding in its own right: `crypto_hourly.py`'s spot capture needs to move to
settlement-instant sampling (or a historical-candle backfill) before S8's basis-vs-overround
comparison can mean anything. 0 new unit tests (pure analysis script over existing tape,
matching the `longshot_fade_probe.py`/`weather_rehab_s5.py` precedent of unit-testing the
collectors, not the one-off probes); 140 tests green (unchanged), `invariants --full` green.
Full writeup: `../findings/2026-07-03-crypto-basis-s8-q5.md`.

**Next:** rerun `s8_basis_probe.py` with historical-candle spot the moment egress reopens to
Coinbase (or Kalshi, to confirm the environment more broadly); only then does the ρ-guard
verdict — and any subsequent block-bootstrap — mean anything for S8.

---

## 2026-07-03 19:40 UTC — Q4/S7b: event-matching join built, first real pregame-ask-vs-devig pass

Claim-check: open PR #4 claims Q1's remaining odds-api work (draft, waiting on Ryan's
`ODDS_API_KEY`) — skipped, moved to Q4 (topmost eligible IN-PROGRESS item). Built the join
S7a deferred, all in `collection/sports_history.py`:

1. `extract_kalshi_teams` — parses the two team names out of a Kalshi game title (three
   live title shapes: WC full form with the ticker-code repeat, WC bare form, NBA
   `"Game N: <A> at <B> <CODE> at <CODE> (Mon DD)"`).
2. `match_kalshi_espn` — team-name containment match (handles NBA's city-name-vs-full-
   team-name case) + ±1-day kickoff window; every row comes back `matched` / `ambiguous` /
   `no_match` / `unparseable_title`, nothing silently dropped or guessed.
3. `run_clv_join` — for matched games: real pregame ask via `candlestick_ask_before`
   anchored at ESPN's actual kickoff (not Kalshi's own `occurrence_datetime`, per S7a's
   second trap), de-vig DraftKings' close (`american_to_decimal` →
   `sports_pairs.devig_multiplicative`), per-field `real_ask`/`synthetic` source tags.

Found mid-build: the S7a ESPN pull's date window (Jun 15-21, group stage) had zero overlap
with the Kalshi WC tape's actual event dates (Jun 26-Jul 2, round of 32/16) — the two legs
were captured for different date ranges by accident. Re-fetched ESPN for the correct window
(`--espn-fetch soccer:fifa.world:20260626-20260702`) before joining.

Live pass: **27 games matched** (24 WC, 3 NBA Finals; 2 NBA hit `ambiguous` — same two teams
on consecutive dates, both inside the ±1-day window, correctly flagged rather than guessed),
**78 outcomes priced**, mean pregame `bracket_sum` **1.020**, mean `edge_after_fee` **−0.0241**
across the 78 outcomes — small-n and descriptive only, NOT a bootstrap-worthy verdict yet.
37 new unit tests (155 total green, fully offline), `invariants --full` green. Full writeup:
`findings/2026-07-03-sports-history-s7b.md`. Next: S7c — accumulate more games as the
tournament progresses, block-bootstrap **by game** (outcomes within a game aren't independent
draws), verdict.

## 2026-07-03 15:30 UTC — Q4/S7a: sourced sports history, found Kalshi's ~60-day retention wall

Claim-check: no open PRs, branch synced to `main` tip (`1abc535`). Built
`collection/sports_history.py` (Kalshi settled-event leg + free ESPN closing-odds leg,
captured separately, no join yet — that's S7b) + 13 unit tests, offline/FakeClient, no
network in CI. Two load-bearing discoveries, both documented in
`findings/2026-07-03-sports-history-s7a.md`:

1. Kalshi's public API purges a settled market's data (and therefore candlesticks) ~60
   days after close, even though `/events?status=settled` keeps listing the event forever.
   Verified by binary search on NBA events. Kills the "last-season NFL" half of S7's
   original spec outright (0/15 sampled NFL events had retrievable markets — full season
   ended Feb, all purged); leaves NBA to only its playoff tail (~40 games, Apr 30 onward);
   leaves **World Cup 2026** (in progress, started Jun 11) as the one series with its
   entire history-to-date still live — now the strongest S7 candidate, and still
   time-sensitive (ends Jul 19).
2. A market's `occurrence_datetime`/`expected_expiration_time` field is NOT kickoff — it's
   the expected *resolution* time, seconds-to-minutes after `close_time`, both clustered at
   game END. Caught before commit: a first draft used it as "decision time" and pulled a
   candlestick showing `yes_ask=1.0` on every outcome of a live 3-way bracket (impossible
   pregame). Fixed: the collector no longer claims a decision/pregame price from Kalshi
   alone; it captures raw timing fields + an honestly-labeled `sample_ask_near_close`
   candlestick, and defers real pregame pricing to S7b (needs ESPN's `event.date`, the
   actual kickoff, to compute the correct candlestick window).

Live passes: 25 World Cup + 40 NBA + 15 NFL Kalshi-side records, 23 WC + 5 NBA ESPN-side
DraftKings odds records (open+close both present, tagged `synthetic`) → 108 lines in
`tape/sports_history/dt=2026-07-03.jsonl`. Gates: 117 tests green (104 prior + 13 new),
`invariants --full` green. Next: S7b game-matching join (Kalshi 3-4 letter codes ↔ ESPN
team names) + point `candlestick_ask_before` at real kickoff.

## 2026-07-03 10:12 UTC — Q3 hourly entry point built; sports + crypto collectors now unified

Claim-check: no open PRs against `main`, local branch already at `main`'s tip (`f6c946a`).
Built `collection/hourly_pass.py` — the single command the hourly Haiku routine runs, per
the Q3 spec. It calls `sports_pairs.run()` and `crypto_hourly.run()` independently: each is
wrapped so an exception in one is caught and recorded rather than taking the other sub-pass
down with it (a partial outage in one collector must not silently zero out the other's
otherwise-honest capture). Overall `completeness_ok` is the AND of each sub-pass's own
already-computed honest completeness signal — never re-derived optimistically, never faked.

`n_markets`/`n_lines` needed a small design call the queue text didn't spell out. Each
`sports_pairs` tape line is one game (2-3 underlying Kalshi markets); each `crypto_hourly`
line is one symbol's full bracket ladder (up to ~188 underlying markets). Reporting
"lines written" alone would make a crypto pass and a sports pass look comparable when
they're wildly different in market coverage, so `hourly_pass` reads back only the tape
lines it just wrote (filtered by `capture_id`, since the append-mode JSONL files carry
prior passes' lines too) and sums each record's own `expected_outcomes` into `n_markets`,
keeping `n_lines` as the plain record count. Both numbers come straight from data the two
collectors already persist — no changes needed to either already-tested module.

`scripts/anomaly_sweep.py` (Q6) doesn't exist yet, so the 09-UTC-only slot checks for the
script file and reports `{"status": "not_built"}` honestly rather than skipping silently or
pretending the slot ran — the moment Q6 lands, `hourly_pass` picks it up with no further
wiring (subprocess invocation, not a Python import, matching how `invariants.py` is already
run as a script rather than imported).

15 new unit tests, fully offline (injected stub `sports_fn`/`crypto_fn`/`anomaly_sweep_fn`,
no network, no real collector code exercised): both sub-passes complete → `completeness_ok`
True with correct `n_markets`/`n_lines` math (including the stray-capture_id exclusion);
either sub-pass's own incompleteness propagates; either sub-pass raising is caught, recorded,
and does not stop the other from running or crash `run()`; the anomaly slot is skipped
outside hour 9, and inside hour 9 correctly treats `not_built`/`ok` as non-failing and
`error`/an exception as failing; the tape-accounting helper in isolation; CLI flag wiring
(`--sports-limit`, `--crypto-symbols`) reaching the real collector functions with correct
kwargs, and a nonzero exit code on an incomplete pass.

**Live smoke, twice:** first `--sports-limit 3 --crypto-symbols BTC` (188 markets, 1 line,
ok) to keep it cheap, then a full unlimited pass — 193 confirmed sports games + both crypto
symbols, 680 underlying markets across 195 tape lines, `completeness ok`. Both passes
appended for real to `tape/sports_pairs/dt=2026-07-03.jsonl` and
`tape/crypto_hourly/dt=2026-07-03.jsonl` (kept as genuine tape, not scratch). Gates: 104
tests green (89 prior + 15 new), `invariants --full` green.

**Next:** Q4 (S7 historical sports-CLV backtest — the try-first edge) and Q5 (S8 crypto
settlement-basis first cut) are now the topmost eligible TODO items; Q6 (anomaly sweep) still
needs building before `hourly_pass`'s 09 UTC slot does anything beyond reporting
`not_built`. The hourly Haiku routine can now run `python -m collection.hourly_pass`
unattended once wired up on its own schedule (that wiring is outside this repo).

---

## 2026-07-03 05:14 UTC — Q2 crypto-hourly settlement collector built + first live pass

Built `collection/crypto_hourly.py`, mirroring `sports_pairs.py`/`capture_orderbooks.py`
discipline for Kalshi's `KXBTC`/`KXETH` ("Bitcoin/Ethereum range") series, which price a fresh
hourly bracket ladder every hour (ticker grammar `SERIES-YYMONDDHH-[T|B]<strike>`, `HH` in ET so
`close_time = HH+4:00Z` during EDT — confirmed empirically against the live API). One pass per
symbol captures three paired things: **(1)** the CURRENT hour's bracket book (`real_ask` BBO,
`bracket_sum`/`overround_absorbed` via `core.pricing`); **(2)** the PREVIOUS hour's settlement —
Kalshi's own `result` + `expiration_value` (the CF Benchmarks index average actually used to
settle), tagged `broker_truth`; **(3)** spot from Coinbase (Kraken fallback if Coinbase fails),
tagged `synthetic` per the queue spec (an external reference price, not itself a Kalshi fill).
Storing all three paired per pass is exactly what S8's ρ-guard (spot-vs-settle correlation) needs
computable from tape alone, without any live analysis code.

One non-obvious discovery-layer bug avoided: the `KXBTC`/`KXETH` series also carries a stray
long-lived group reusing the same hourly ticker grammar (`KXBTC-26JUL0317`, empirically observed
open continuously since 2026-06-26 — a different market shape, not the hourly ladder) sitting
alongside the genuine current-hour group in the `status=open` response. Naively picking "whatever
event_ticker is open" would silently mix a week-old group into "current hour" data. Fixed by
filtering on `close_time - open_time <= 65min` before picking the soonest-closing candidate — a
duration check, not a ticker-string special case, so it generalizes to any future stray group.
Previous-hour's event_ticker is derived by pure arithmetic on the current group's date+hour token
(subtract 1 hour, handle day/month/year rollover) rather than an extra discovery call. 21 new unit
tests (offline `FakeClient` + monkeypatched HTTP for the spot fallback, no network): hour-token
arithmetic incl. rollover, stray-group exclusion, honest completeness (missing ask drops that
outcome), settlement status states (settled/pending/not_found/fetch_error, and disagreeing
`expiration_value`s surfaced rather than silently picking one), spot fallback + total-failure
handling (never a stale/fabricated substitute).

**First live pass** (`tape/crypto_hourly/dt=2026-07-03.jsonl`): both symbols `pass_complete`.
BTC (`KXBTC-26JUL0302`, 188 members: 1 T-tail-below + 186 $100-wide bands + 1 T-tail-above, a
clean mutually-exclusive partition like weather's `{T-tails + B-bands}` shape): bracket_sum
**$10.27**, i.e. overround_absorbed **+$9.27** (real_ask) — two orders of magnitude fatter than
weather's ~9.8¢ or sports' +21.3¢. ETH (`KXETH-26JUL0302`, 75 members): bracket_sum **$2.23**,
overround **+$1.23**. Plausible mechanism, NOT yet verified as a real edge: 186 very fine ($100)
bands each carry Kalshi's apparent 1¢ minimum quoted ask even when near-zero-probability, so
summing ~180 deep-out-of-the-money 1¢ floors alone accounts for most of the excess — this is a
collector observation for Q5 to actually test, not a backtest result; no CI computed, no verdict
on S8 yet. Gates: 89 tests green (68 prior + 21 new), `invariants --full` green.

**Next:** Q3 (hourly entry point) can now wire in both Q1 + Q2; Q5 (S8 first cut) can start
building on this tape once a few hours have accumulated, and should investigate the fine-band
minimum-ask mechanism above before treating the raw overround as a scoring input.

---

## 2026-07-03 — Loop protocol fixed: cloud sessions can't push to `main`; PR + claim-check added

Two consecutive `kalshi-research-loop` firings (23:18Z and 00:17Z, both same 5-hour window)
each independently rebuilt Q1 (`collection/sports_pairs.py`) from scratch and stranded the
result on their own branch (`claude/brave-mccarthy-ek6ybp`, `claude/brave-mccarthy-7rnhry`) —
neither reached `main`, neither opened a PR. Root cause: a cloud session cannot
`git push origin main` here — confirmed empirically, both runs rebased clean against `main`
(merge-base == main tip, no conflict) yet both still fell back to their session's own branch,
which only happens on a permission boundary, not a race. `LOOP-QUEUE.md`'s old protocol
(step 6: `git push origin main`, fall back to a branch only after 3 failed retries) assumed a
push that was never going to succeed, so every firing silently fell back and the queue's
"memory" (Status lines, Log of runs) never actually reached the next firing's starting state.

Fix, in `LOOP-QUEUE.md`:
- **New step 0 (claim check):** before picking work, list open PRs against `main`; an item
  named in an open PR is claimed — don't redo it, merge the PR if it's green instead.
- **Rewrote step 6:** push your own branch → open a PR → merge it immediately (squash) if
  `pytest` + `invariants --full` are green and the diff is research/data-only (Stop rules
  already forbid execution/credential code, so this is a re-check, not a new bar). Broken or
  partial work stays an open PR with an IN-PROGRESS note instead of merging.

Reconciled the stranded work: kept `claude/brave-mccarthy-7rnhry`'s `sports_pairs.py` (title-
regex + structural per-game confirmation before capture — the defense against exactly the bug
the other branch had to live-patch, ticker-suffix-only classification letting non-moneyline
`GAME`-suffixed prop series through) as the surviving implementation, folded the other run's
tape capture in as extra data (357 events/07-02 pass + 188 games/07-03 pass, different
timestamps, no conflict), merged to `main` via PR. Gates: 68 tests green, invariants green.

**Why this is the actual fix, not just cleanup:** `LOOP-QUEUE.md` + this log were already
meant to be the loop's memory system and active to-do list — they just couldn't work while the
git mechanics silently dropped every firing's state on an orphan branch. The claim-check +
PR-merge protocol is what makes "pick the topmost item, do the work, persist it" actually
cumulative across 5-hour firings instead of amnesia dressed up as append-only logging.

---

## 2026-07-03 00:14 UTC — Egress unblocked (Q0b); Q1 sports-pairs collector built, first live tape

Re-ran the Q0b cheap egress re-check (self-healing item, runs first while anything is
`BLOCKED(egress...)`): all 4 hosts that failed yesterday now answer for real — Kalshi REST 200
(`exchange_active:true`), Coinbase 200 (live BTC ask), Kraken 200 (live server time), the-odds-api
401 (reachable, just no key). `capture_orderbooks.py --limit 3` proved it end-to-end against live
Kalshi. This is an environment change (Ryan widened the sandbox allowlist, or an env swap), not a
code fix. Flipped Q0b DONE and every `BLOCKED(egress...)` item in `LOOP-QUEUE.md` back to TODO;
refreshed `tape/cloud-env-check.md`. Per Q0b's own instruction, continued straight to the new
topmost TODO item instead of ending the run there.

**Q1 (time-sensitive — World Cup ends Jul 19):** built `collection/sports_pairs.py`, mirroring
`capture_orderbooks.py`'s discipline without forcing weather's city/target_date shape onto sports.
Discovery is two-stage: a title heuristic over the ~2300 Sports-category series narrows the
API-call budget (`*Game(s)*` minus prop-bet keywords), then every candidate game group is
structurally confirmed (2-3 mutually exclusive outcomes, every market titled "&lt;A&gt; vs &lt;B&gt;
... Winner?") before anything is captured — the heuristic only saves calls, it never decides what
gets persisted. Each confirmed game is one game group priced as a bracket exactly like the weather
ladders, so `core/pricing.bracket_sum`/`overround` (Hard Rule #3's one sanctioned site) applies
unchanged. Ticker grammar (`SERIES-YYMonDD<TEAMS>-OUTCOME`, e.g.
`KXWCGAME-26JUL06USABEL-USA`) parses with a new `parse_sports_ticker`; a `devig_multiplicative`
function is implemented and unit-tested for the odds-api leg, unused live since `ODDS_API_KEY` is
absent (Q1's spec: capture the Kalshi leg anyway, mark the odds leg `blocked_key`, never fabricate
it). 19 new unit tests (offline `FakeClient`, no network): ticker parsing, moneyline-group
confirmation, de-vig math, and a full capture pass with honest completeness (a missing ask drops
that outcome and flips `completeness_ok`, never fabricated).

**First live pass:** 197 candidate series → 188 confirmed moneyline games across 16 series (10 of
them `KXWCGAME` World Cup games), 100% `completeness_ok`, written to
`tape/sports_pairs/dt=2026-07-03.jsonl`. Mean bracket overround **+21.3¢ (real_ask, n=188)** —
notably fatter than the ~9.8¢ weather overround that killed S1/S5; plausibly thin/new markets
rather than a structural property of sports moneylines, needs a liquidity-filtered re-cut before
it says anything about S7. Flipped S7/S11 to `data-collecting` in the registry (not `tested` — no
CI computed yet, this is infra + one snapshot). Gates: 68 tests green (49 prior + 19 new),
`invariants --full` green.

**Next:** accumulate `sports_pairs` tape over multiple passes (needs Q3's hourly entry point,
which is still blocked on Q2); get an `ODDS_API_KEY` to unblock the Pinnacle/de-vig leg S7's
binding test actually needs. Q2 (crypto-hourly collector) is now the topmost eligible TODO item.

---

## 2026-07-02 22:43 UTC — Q0 cloud environment check: all external hosts BLOCKED by egress policy

Ran the cloud-sandbox reachability check the queue calls for before any of Q1–Q7 can move: Kalshi
public REST (`python -m collection.capture_orderbooks --limit 3`), Coinbase + Kraken public spot,
and `api.the-odds-api.com` (plus a presence-only check for `ODDS_API_KEY`, absent). **All 4 hosts
failed identically** — the sandbox's egress proxy answered every CONNECT with a 403 (`gateway
answered 403 to CONNECT (policy denial or upstream failure)`), and its `noProxy` allowlist covers
only package registries + `anthropic.com`, no data provider. Per the proxy runbook this is an
organization policy denial, not a transient fault — not to be retried or routed around. Full
evidence and interpretation in `tape/cloud-env-check.md`.

**Consequence:** every downstream collector needs one of these hosts, so Q1, Q2, Q3, Q4, Q5, Q6 are
now `BLOCKED(egress policy)` in `LOOP-QUEUE.md` — this is essentially the entire active queue. Q0
itself is the only item this run's cloud sandbox could actually complete; nothing here indicates a
bug in `capture_orderbooks.py`/`normalize.py` (never got past the TLS tunnel). **This needs Ryan**:
either widen this environment's egress allowlist to include a Kalshi host, a public crypto spot
host, and an odds API host, or run the collectors from a pool that already has broader network
access — no cloud run can change its own policy. Gates: 53 tests green, `invariants --full` green
(no code changed, so nothing new to gate — recorded for protocol compliance).

**Next:** once egress is widened, Q1 (sports pairs collector, time-sensitive — World Cup ends Jul
19) is the immediate next milestone.

---

## 2026-06-18 19:41 ET — S2 FOMC×ZQ free-data first cut: structure validated (n=1), worth the CME spend

Free-data, single-meeting first cut of S2 on the just-resolved June 2026 FOMC — Kalshi PUBLIC historical
candlesticks (`yes_ask` BBO) × free Yahoo ZQ. `scripts/fomc_zq_basis_s2.py`, `findings/2026-06-18-fomc-zq-s2.md`.
**n=1 STRUCTURE check, NOT an edge.**

- **FOMC bracket overround = mean +3.35¢** (3–4¢) vs the **~10¢** weather overround that killed pt1/S1/S5 →
  **~3× cleaner; the prob-to-prob structural thesis HOLDS** — the reason S2 is the post-weather pivot.
- June was **LOW-INFORMATION**: both venues priced a near-certain hold (Kalshi P(hold) 0.942–0.962, ZQ
  0.931–0.977); net-of-fee basis mean **−1.39¢/contract**, 5/163 periods positive → no tradeable gap on THIS
  event (expected for a consensus hold; one event can't yield a CI).
- **Verdict: structure worth the CME spend.** Full version needs intraday ZQ ticks (daily close too coarse —
  ZQ P(hold) swung 0.931→0.977 on a single 1-tick move; the `N_post` divisor amplifies it) + many **contested**
  meetings + block-bootstrap CI (block=meeting) + Kalshi L2 depth + frozen-pre-position risk modeling. GATED on
  Ryan (CME data sourcing).
- Honesty: `yes_ask.close` tagged `real_ask` (BBO-at-candle-close caveat — overstates fillable size); ZQ-prob
  `synthetic`. Prior-contested-meeting pull deferred (2025 tickers use a different target-range scheme +
  rate-limits), not faked. **53 tests green, invariants --full green.** Tape/DB untouched.

---

## 2026-06-18 19:40 ET — 3 new cross-venue basis candidates drafted (S7/S8/S9) via /first-principles

Ideation pass through the **cross-venue basis lens** (Kalshi vs a different venue pricing the same/
correlated resolution). Goes BEYOND S2 (FOMC×ZQ prob-to-prob). All three grounded in live
settlement-spec + data-access research (Perplexity, 2026-06-18; CF Benchmarks RTI, Polymarket CLOB
docs, Kalshi historical candlestick REST). None is in the dead ledger.

- **S7 — KXBTC vs Polymarket crypto: settlement-index + sampling mismatch.** Kalshi KXBTC/KXETH
  hourly brackets settle on **CF Benchmarks RTI = 60s average of a multi-exchange index**;
  Polymarket crypto settles on a **single-exchange (Binance) 1-min candle / last print**. Same
  nominal hour, different fixing → the two venues' implied "price lands in bracket X" can disagree
  whenever Binance basis vs the multi-exchange index, or a sub-minute spike, moves the single print
  off the 60s mean. Mechanism: settlement mismatch, NOT a probability claim. Both real-price histories
  are FREE/public (Kalshi `/historical/market_candlesticks` yes-OHLC; Polymarket CLOB
  `/prices-history` + Gamma resolved outcome). Overround note: crypto-hourly binaries are 2-outcome
  (low overround) BUT Kalshi crypto taker fee is the fat 7%-class — must clear that.
- **S8 — Kalshi single-game sports vs Pinnacle sharp closing line (directional on the laggard).**
  Documented: Kalshi order-book sports prices LAG Pinnacle's vig-removed line by minutes after a
  discrete info shock (injury/scratch/steam); practitioner reports 2–3pp gaps before catch-up;
  election-market analog measured 12–18 min lag. Mechanism: sharp dealer (Pinnacle) reprices
  instantly; Kalshi only moves when a taker crosses the book → exploitable catch-up window. Trade
  the laggard (Kalshi) directionally toward the devigged Pinnacle number. Real ask = Kalshi BBO
  (candlestick yes_ask OHLC + live book); reference = Pinnacle/odds-API devig. Overround: liquid
  marquee games show 1–3¢ spreads — thin enough that a 2–3pp lag can clear it.
- **S9 — Kalshi vs Polymarket same-event PRICE-DISCOVERY lead-lag (timing, not static level).**
  "Who Wins and Who Loses" (SSRN) + LOOP-violation paper: **Polymarket leads Kalshi in price
  discovery** (24/7 crypto crowd, zero maker fee) on the SAME politics/macro yes/no event; the
  static level-wedge has compressed to 1–2% and is NOT cleanly unidirectional, so the edge is the
  *timing* — fade Kalshi toward Polymarket's already-moved price after a discrete shock, not a
  standing level arb. Mechanism: segmented user bases + USDC/USD rail friction keep arbitrage from
  enforcing instant parity. Both prices FREE (Kalshi candlestick + Polymarket CLOB). Overround:
  Kalshi politics binaries are richer (sum 110–140% multi-outcome); the lead-lag must clear Kalshi's
  taker fee + spread on the 2-outcome legs.

These graduate to the registry as **S7/S8/S9 (idea)**. Binding tests are all no-capital replays on
free public history. Returned via the workflow's StructuredOutput; full rationale in the council/
first-principles brief to follow before any data-collection spend.

---

## 2026-06-18 15:03 ET — S5 weather rehab TESTED → DEAD. Weather family is dead at real asks.

**The decisive result.** With Ryan's go-ahead, ran the S5 weather-rehab real-ask paper test —
the question that decides the project's direction. Verdict: **the weather family is DEAD at real
asks, even with proper EMOS calibration.** (`scripts/weather_rehab_s5.py`,
`findings/2026-06-18-weather-rehab-s5.md`, per-trade dump `reports/weather_rehab_s5_full.json`.)

- **EMOS works — but it's necessary, not sufficient.** Leave-one-day-out EMOS calibration cut
  pooled CRPS **2.366 → 2.180 (−7.86%)**, fixing the underdispersion exactly as the literature
  (Gneiting 2005) predicts. The better probability is real.
- **The dollar edge is not.** 641 trades (3-model ensemble: GFS+ECMWF-IFS025+ICON; GEM single-runs
  not archived for the window so honestly dropped → member_count=3; no `ncep_gefs025`). Mean net
  **−$0.02789/trade**, 95% moving-block-bootstrap CI **[−$0.06297, +$0.00788]** (n_boot=10k, 21
  contract-day blocks). **Lower bound does NOT clear zero.** Killed by the same **~9.8¢ mean
  overround** that ate pt1 and S1. A better probability cannot beat a ~10¢ structural tax here.
- **Adversarial checks (the discipline that matters):** edge-bar sweep — raising the conviction bar
  to 0.10/0.15 made P&L *worse* (CI fully below zero), the opposite of a real edge; independent
  fill/cost sign audit — 0 mismatches (no repeat of S1's near-miss); anti-leak — used the Open-Meteo
  **Single Runs API pinned to (D−1) 00Z** (a genuine ~24h-ahead leak-free forecast), NOT the
  historical-forecast archive (which stitches lead≈0 ≈ actuals and would leak — venues.yaml warns);
  0 leak-guard drops. Prices `real_ask`, all 6 provenance fields persisted per trade.
- Caveats (honest): short 22-day spring window, EMOS data-thin, decision time near market open,
  L1-only fills (haircut modeled not measured).

**PROJECT DIRECTION CHANGE:** weather is no longer "on probation" — it is **proven dead at real
asks**. The 3 weather angles tried (raw ensemble pt1, longshot-fade S1, EMOS-calibrated S5) are all
dead to the overround. **Pivot to non-weather: S2 (FOMC×ZQ basis — structurally NO bracket
overround), S3 (cross-strike staleness), S6 (market-making — earn the spread instead of paying it).**

Verified: **53 tests green, `invariants --full` + `--db` green**, recovered tape read-only. S5
committed to `main`. Only S2 (FOMC×ZQ) remains on the queue — GATED on CME data sourcing (Ryan).

---

## 2026-06-18 12:53 ET — S1 longshot-fade FALSIFIED · EMOS reproduced · forecast tape live

Three parallel probes ran on top of the S0 substrate (autonomous `/loop`, 3 subagents). Merged
tree verified: **53 tests green, `invariants --full` green**, recovered tape DB untouched (read-only).

- **S1 longshot-fade → DEAD (real asks).** n=990 reconstructed-`real_ask` KXHIGH brackets from the
  24GB recovered tape. The favorite-longshot bias *exists* (longshots <0.20 realize fewer wins than
  priced, gaps −1.4¢..−7.0¢; favorites >0.65 underpriced) but is single-digit cents, **swamped by a
  +9.84¢ mean overround**. Maker-NO-on-longshot net P&L **+$0.00448/trade, 95% block-bootstrap CI
  [−$0.00486, +$0.01333]** — lower bound does NOT clear zero; sweep 0.05→0.25 uniformly null, deepest
  longshots negative. **A whole bias-chasing family falsified**, as the dossier predicted. Probe:
  `scripts/longshot_fade_probe.py`; writeup: `findings/2026-06-18-longshot-fade-s1.md`. **Near-miss:**
  the first run cleared zero on a cost-model sign bug (maker entry booked as a 2¢ *improvement* not a
  *cost* — the exact pt1 prime-directive failure mode); caught + fixed. **Candidate invariant filed:**
  a cost haircut must never move the entry in the trader's favor. (Tape caveat: T-24h lands near market
  open; L1-only, fill-prob haircut modeled not measured; single 22-day spring window.)
- **EMOS reproduced (#5).** `scripts/emos_demo.py` (stdlib-only, deterministic) fits a 1-param-spread
  EMOS Gaussian by minimizing closed-form Gaussian CRPS: **CRPS 1.663 (raw ensemble) → 0.717 (EMOS),
  −56.9%**, bracket P(74≤Tmax<78)=0.761. Flipped `kb/quant-finance/01-weather-forecasting-alpha.md`
  from `cited` → `reproduced`. (Calibrated post-processing beats the raw underdispersed ensemble — the
  precondition for any S5 weather-rehab attempt.)
- **Forecast tape now exists (#3).** `collection/forecast_collector.py` (+10 offline tests) — single
  read-only Open-Meteo pass per city × {gfs_seamless, ecmwf_ifs025, icon_seamless, gem_global} (NO
  `ncep_gefs025`, Hard Rule #1, with a runtime guard), append-only JSONL with ms `fetch_ts` + raw
  sha256 + `source_tag=synthetic`, honest completeness. Live smoke (NYC, 2026-06-18): 89.6/89.2/90.1/
  86.3°F across models. The previously-zero most-reused missing input is no longer zero.
  **Scheduling still GATED** (laptop-cron HOLD).

**Loop end-state:** all 4 unblocked Next items done (S0 substrate, S1, EMOS, forecast collector). **Two
items remain GATED on Ryan:** #2 cron forward capture (Kalshi creds + the laptop-cron HOLD decision)
and #4-S2 FOMC×ZQ (CME data sourcing). Nothing committed to git (Ryan's call).

---

## 2026-06-18 12:38 ET — S0 real-ask substrate built + Hard-Rule invariants (43 tests green)

**Built the project's first implementation — the substrate every future edge is scored on
(dossier #1, the canonical first build).** Autonomous `/loop` run against the 5-item Next queue.

- **Lifted verbatim from `kalshi.1` @ `fd37ae2`** (byte-identical, all 16 files diff-checked,
  recorded in `../PROVENANCE.md`): `core/{canonical,io,manifest_schema,timeutil,schema}.py`,
  `collection/{normalize,capture_orderbooks}.py`, `validation/{v1_actuals,v3_market,_http}.py`,
  4 config YAMLs, 3 tests + ticker fixture. Mirroring kalshi.1's layout meant **zero import edits**.
  - `normalize.py` derives the REAL taker ask `best_yes_ask = round(1 − best_no_bid, 4)` (Kalshi
    posts bids-only; the ask is the opposite side's complement). This is the price H1 trades on.
  - `capture_orderbooks.py` = forward, read-only, bitemporal depth capture Kalshi does NOT archive
    (the only moat that compounds with calendar time). Honest completeness: a dropped market lowers
    `n_markets < expected` so a truncated pass can't pass as complete (survivorship guard).
  - `v1_actuals.py` = 3-source settlement gate (CLI vs METAR vs GHCN) — the corrupted-actuals catch.
- **Authored fresh for THIS project's rules** (kalshi.1 has no equivalent — its invariants are
  arb-bot-v2's, scoped to a different layout):
  - `scripts/invariants.py` — the **6 Hard Rules** as static (regex) + DB (sqlite) assertions, plus
    `--pre-edit-hook` mode. Structure adapted from `arb-bot-v2/scripts/v3_invariants.py`, retargeted.
    DB invariants are **schema-discovering** (the project's DB schema isn't frozen) — they introspect
    tables, so Rule #4 (no pnl without a `price_source_tag`) fires on whatever backtest table appears.
  - `core/source_tag.py` — the trust=FALSE default in code: **untagged number ⇒ `synthetic`**; only
    `real_ask`/`broker_truth` are `is_fillable`; `require_fillable()` blocks synthetic/midpoint from
    any fill/P&L decision (prime directive #1).
  - `core/pricing.py` — THE sanctioned `yes_ask/bracket_sum` site (Hard Rule #3); `overround()` makes
    the ~5¢ pt1 killer a first-class, persisted number.
  - `core/stats.py` — `safe_pstdev` with the n≥4 guard (Hard Rule #2).
- **Verified:** `pytest -q` → **43 passed**; `invariants.py --full` → **all green**. The dossier's #1
  binding assertion is now a test: `best_yes_ask == round(1 − best_no_bid, 4)`, ask stamped `real_ask`.
- **Not wired (left for approval):** the PreToolUse hook (would block edits = harness change); live
  capture/actuals paths (need Kalshi creds + network — only offline/injected paths are tested).

**Next (this loop):** `scripts/emos_demo.py` repro (#5) → Open-Meteo collector script (#3) →
longshot-fade offline calibration on the recovered tape (#4-S1). **GATED on Ryan:** cron the forward
capture (#2 — needs creds + conflicts with the kalshi.1 laptop-cron HOLD) and FOMC×ZQ (#4-S2 — needs
CME data sourcing).

---

## 2026-06-18 01:10 ET — Codebase mine landed; KB foundations built

**Workflow result (27 agents, 22 candidates, all adversarially verified at real asks):**
- Verdict tally: **0 proven edges · 4 dead · 6 infra-only · 12 needs-data.**
- Honest bottom line: **no clean dollar edge is proven at real fillable asks anywhere.** The
  only real-money test (KXHIGH weather ensemble, n=49) lost −$0.14/trade; pt1 −9.6%, killed by
  ~3–5¢ bracket overround. Directional signal is real; dollar edge is not.
- Cheapest path forward: build the **real-ask substrate** (S0: tape capture + 3-source actuals
  gate + bid-only ask primitive + invariant engine), start **archiving forward orderbook tape**
  (un-backfillable; the only moat that compounds), and run two near-free probes — **longshot-fade
  calibration (S1)** and **FOMC×ZQ basis (S2)**. Zero weather-model capital until a real-ask CI clears zero.
- Full dossier → `../findings/2026-06-18-codebase-money-map.md`. Candidates registered → `strategies/00-index.md`.

**KB built this session:**
- `kalshi-api/`: overview, **auth & signing** (RSA-PSS/SHA-256, verified), REST+WebSocket map,
  **fees & breakeven** (`reproduced` via `scripts/fee_breakeven.py` — 2¢/contract at 0.50 → need +2¢ edge).
- Runnable repros: `scripts/kalshi_sign.py` (local signature verifies OK), `scripts/fee_breakeven.py` (ran).
- `quant-finance/`: 7-theme overview + deep weather-alpha note; citations triaged (caught a
  fabricated arXiv id + several wrong venues — see `_sources/quant-finance-sources.md`).
- `glossary.md`, both `_sources/` provenance files.

**Dead-end ledger (do not re-mine):** raw KXHIGH ensemble as deployed, Kelly-modifier tilt, LIP
rebate harvest, settle-time T-3h pin, K1' "hedge" framing, NWS/WU settle-source basis. (Details in dossier.)

**Next:**
1. Build S0 substrate (lift kalshi.1 `normalize.py`/`v1_actuals.py`/`capture_orderbooks.py` + invariants).
2. Cron forward Kalshi orderbook capture at a pinned decision time TODAY.
3. Start an Open-Meteo forecast collector (zero forecast tape exists anywhere — most-reused missing input).
4. Run S1 (longshot-fade) and S2 (FOMC×ZQ one-meeting) — near-free, no capital, decide weather's fate.
5. Reproduce: write `scripts/emos_demo.py` so the weather-alpha note can claim `reproduced`.

---

## 2026-06-18 00:35 ET — KB seeded; codebase-mining workflow launched

- Created `kalshi.headless` as the canonical Tier-2 Kalshi project. Inherited the
  prime directive, trust=FALSE defaults, and 6 hard rules from `arb-bot` (see
  `../CLAUDE.md`).
- Stood up this KB with the Karpathy-method charter (`README.md`): first
  principles, runnable repros, append-only log, cold-reader legibility.
- Kicked off a dynamic workflow to mine the four existing Kalshi codebases
  (`arb-bot`, `arb-bot-v2`, `kalshi.1`, `kalshi.ibkr`) for money-making
  opportunities and adversarially verify each against the "real fillable asks"
  bar. Output lands in `../findings/`.
- Began two foundational KB tracks in parallel:
  - `kalshi-api/` — how Kalshi actually works (auth, market structure, fees,
    rate limits, data).
  - `quant-finance/` — peer-reviewed literature relevant to prediction-market
    edges (calibration, favorite-longshot bias, market microstructure, Kelly).

**Next:** integrate workflow findings into `strategies/` candidates; reproduce
the top-1 fee/pricing claim with a runnable script.
