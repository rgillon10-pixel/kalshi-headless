# `tape/orderbook_depth/` hollow crypto ladders: a fetch-after-close failure mode `completeness_ok` can't see (2026-07-26)

Idle-run milestone (policy c — a data-quality deep-dive on one tape family, one finding). The
queue (Q0-Q48) is fully drained/blocked, the lessons ledger's `UNENFORCED` backlog is empty
(L167), and both known time-gated probes (Q19 FOMC, Q37 weather) are already prepped, so this
run's real-work unit is a fresh content-level audit of `tape/orderbook_depth/` — the single
largest tape family by volume (Q46: ~83% of the repo's 1.1GB tape footprint) and one of the
two families fed by both the (now-dead, per Q44/L156) VPS `:23` cron and the cloud `:53` cron.

**Two-agent provenance.** A `tape-auditor` subagent found the phenomenon below; an
independent `verifier` subagent re-derived every number directly from the raw committed
`.jsonl` files and REFUTED several of the auditor's causal claims while confirming the core
mechanism and surfacing two further failure modes the auditor missed. The numbers below are
the verifier-corrected set, reproduced exactly by the committed script
`scripts/orderbook_depth_hollow_ladder_audit.py` (see its HARD acceptance tests in
`tests/test_orderbook_depth_hollow_ladder_audit.py`).

**Numbers below are FROZEN at `dt<=2026-07-25`** (the last fully-closed day at audit time),
not "as of whenever this file is read." A live hourly pass landed mid-session while this
finding was being written, growing `dt=2026-07-26.jsonl` from 976 to 1,464 crypto records —
proof, inside this very run, of why the committed tests below freeze to a day that can never
grow again rather than pinning exact counts against a still-accumulating day file.

## The finding

`tape/orderbook_depth/` can write a record that is present, well-formed JSON, tagged
`price_source_tags: {"asks":"real_ask","bids":"real_bid"}` — and completely **hollow**:
`yes_bids=[]`, `no_bids=[]`, all four best-price fields `null`, `depth=0`. This is not a
malformed line, a schema violation, or a fetch error `completeness_ok` (computed in
`collection/orderbook_depth.py`, never persisted onto the tape line itself) would catch — it
is a 200-OK response for a ticker whose market had **already closed** by the time the fetch
reached it, or was fetched close enough to expiry that the book had already emptied.

**Scale (18 committed day-files, `dt=2026-07-07`..`dt=2026-07-25`, `dt=2026-07-09` absent;
339,947 lines total, 0 malformed, one uniform 14-key schema shape throughout, 0 duplicate
`(capture_id, ticker)` pairs, 0 crossed two-sided books):**

- **15,238 records (4.48%) are hollow.** 15,175 (99.6%) are crypto (`KXBTC`/`KXETH`); only 63
  are non-crypto (sports/other families stay at ~0-0.5% hollow every day — these are almost
  certainly ordinary settled/thin-wing books, not this mechanism).
- Crypto's own hollow rate is not a spring-to-summer drift story — it was already 1.6% on the
  very first committed day (07-07) and has been present throughout, worsening sharply once the
  VPS leg (the only leg that has ever produced clean crypto depth — see below) started dying:
  07-23 and 07-25 committed **zero usable crypto ladders all day** (976/976 and 488/488 hollow
  respectively) despite writing non-empty files. (07-26, still accumulating at audit time, was
  already running 52-78% hollow across two reads taken minutes apart within this same session
  — descriptive only, deliberately excluded from every pinned number above and from the tests.)

## The mechanism: runway-to-close, not collector identity

Bucketing every crypto record by its own runway to its ticker's close time (parsed from the
ticker's embedded date+hour token via `core.timeutil.parse_crypto_hour_token_close_utc`):

| runway to close | records | hollow | rate |
|---|---|---|---|
| post-close (fetched at/after the ticker's own close) | 789 | 789 | **100.0%** |
| 0-5 min | 51,501 | 14,385 | **27.9%** |
| 5-15 min | 1,578 | 0 | 0.0% |
| 15-30 min | 488 | 0 | 0.0% |
| 30-45 min | 64,274 | 1 | 0.0% |
| 45-60 min | 526 | 0 | 0.0% |

Hollow rate is a function of **how close the fetch lands to the ticker's own expiry**, not of
which collector leg produced it. The same table split by collector leg (via the project's own
`scripts/tape_gap_monitor.py::collector_bucket`, not a hand-rolled minute rule — the auditor's
first pass hand-rolled this split and silently dropped clean off-slot records from the
denominator, inflating the cloud leg's apparent rate) is DESCRIPTIVE, not causal, and is
included here specifically to warn against over-reading it:

| leg (by `collector_bucket`) | records | hollow | rate |
|---|---|---|---|
| vps (minutes 20-29, ~37 min runway) | 64,274 | 1 | 0.002% |
| cloud (minutes 50-59, ~0-5 min runway) | 53,079 | 14,385 | 27.1% |
| other (ad-hoc/off-schedule minutes) | 1,803 | 789 | 43.8% |

Leg and runway are collinear under the current cron schedule (the VPS slot happens to have
long runway; the cloud slot happens to have short runway), so this table alone cannot
distinguish "the cloud leg is worse" from "the cloud leg's slot has less runway." The
verifier's discriminating case: an off-schedule cloud-hour capture at minute :41
(`20260721T224112Z`, ~18.8 min runway) is **488/488 clean** — a cloud-leg capture with enough
runway is fine. **Do not read "restore the cloud leg's slot count" as a fix for this — a
restored `:53`-only cadence with today's pass size reproduces the defect exactly.**

Counter-intuitive corollary: the dead VPS `:23` leg has been the **only** leg that ever
produced clean crypto depth (1 hollow record in 64,274, an isolated deep-OTM ETH strike, not a
truncation — see below). Fixing the VPS collector alone does not fix this family; the cloud
leg's pass now appears to take longer than its runway allows against the current (grown)
ticker universe.

## Two further mechanisms, distinct from in-flight overrun

1. **Fetch-after-close from a stale discovered universe.** 789 records (all in the "other"
   bucket above) were fetched from a ticker list built *before* the hour rolled over, so the
   fetch targets an already-closed contract from the start — not a pass that ran out of time
   mid-flight. Example: capture `20260723T005605Z` fetched 488 `KXBTC`/`KXETH` records for
   markets whose `close_time` (per `tape/crypto_hourly/dt=2026-07-23.jsonl`) is
   `2026-07-23T01:00:00Z` — the capture's own `captured_at` stamp of `00:56:05Z` claims to
   precede close by ~4 minutes, but every one of its 488 crypto records is hollow.

2. **`captured_at` is a pass-START stamp, not a per-record fetch time.** Every record in a
   given `capture_id` shares one identical `captured_at` (verified: 1 distinct value per
   capture across all 425 captures in the family). A multi-minute pass therefore backdates its
   later fetches by up to the whole pass duration. The capture above is the proof: its records
   claim `00:56:05Z`, but they were provably fetched at or after `01:00:00Z` (their own
   ticker's close), i.e. **>=235 seconds after their recorded timestamp.** Any event-time or
   nearest-timestamp join against this family (e.g. to `tape/crypto_hourly/`) is silently off
   by up to a full pass duration — far more than the ~17-second `crypto_hourly`-vs-
   `orderbook_depth` lag a naive join would worry about.

## Fetch-order contiguity (the truncation signature) — mostly holds, two named exceptions

Within a capture, does the fetch order (file line order) show hollow records as a strict
suffix — first hollow, then hollow through the end? **42 of 42** crypto-only partially-empty
captures were checked; **2 violate** the suffix rule:

- `20260711T052352Z` — a single hollow record at crypto-fetch-index 226/263
  (`KXETH-26JUL1102-B1800`), with 36 non-hollow crypto records after it.
- `20260714T125521Z` — hollow at indices 228-229 (`KXETH-26JUL1409-B1840`/`B1860`), 33
  non-hollow after.

Both exceptions are **deep-OTM ETH strikes** — kb/lessons **L23**: a genuinely empty resting
book on a far-wing bracket is legitimate market shape, not a capture failure. "Hollow implies
truncation" is not universally true; these two are the counterexample, correctly distinguished
from the 40 genuine truncation-signature captures. (All-record variant, including non-crypto
tickers: 77 partially-empty captures, 16 violations — same pattern, more non-crypto wing
exceptions.)

## Joinability warning

`(capture_id, ticker)` never matches across `orderbook_depth` and `crypto_hourly` — each
collector mints its own independent `capture_id`. A nearest-`captured_at` join on ticker alone
is unsafe for two reasons: (1) the pass-start-stamp defect above means the recorded time can
trail the real fetch time by minutes, and (2) `crypto_hourly` is fetched earlier in the same
pass than `orderbook_depth`, so pairing a live pre-close `crypto_hourly` BBO with a hollow
post-close `orderbook_depth` ladder manufactures a phantom "tight two-sided quote, zero resting
depth" signal — exactly the shape a naive liquidity/market-making probe would misread as an
opportunity. **Any future probe joining these two families must drop `depth==0` crypto
records before computing a liquidity statistic, and must not trust `orderbook_depth`'s
`captured_at` as a precise fetch time.**

## One historical footnote, not a new lesson

Commit `d845dfb` on `dt=2026-07-22.jsonl` shows `34202 additions / 31422 deletions` in
`git log --numstat` — at first glance a rewrite. A full line-set diff shows **0 lines lost**;
it was a stranded-branch recovery (step 0b) that reordered the file's lines rather than
strictly appending. Content is intact; flagged here only because LOOP-QUEUE.md step 0b's own
stated discipline is "never rewrite or reorder existing lines" and this is a real, if harmless,
departure from it. Not actionable now (rewriting merged git history is out of scope and
riskier than the issue it would fix) — noted for future stranded-tape-sweep tooling to
preserve line order, not just content.

## What's built, what isn't

**Built:** `scripts/orderbook_depth_hollow_ladder_audit.py` (the reproducer; every number
above comes from running it, both `load_records` and `run_audit` accept an optional
`max_day` freeze) + `tests/test_orderbook_depth_hollow_ladder_audit.py` (offline unit tests +
2 HARD acceptance tests frozen at `dt<=2026-07-25`). A non-gating advisory,
`scripts/invariants.py::hollow_crypto_ladder_warning` (+
`tests/test_hollow_crypto_ladder_advisory.py`, its own HARD test frozen the same way), now
surfaces any recent day where >=50% of `tape/orderbook_depth/`'s crypto records are hollow —
live (unfrozen) it currently fires for `dt=2026-07-23` (100%), `dt=2026-07-24` (86.1%),
`dt=2026-07-25` (100%), and `dt=2026-07-26` (52.0% as of this run's last tape pull, still
accumulating). Advisory only; does not affect the gate's exit code.

**Not built (repair spec, Ryan-gated collector lane, same posture as every other
`collection/`-touching finding this loop produces):**
1. Stamp a per-record fetch timestamp alongside the pass-level `captured_at`.
2. Order the ticker list deadline-first — crypto hourlies have a hard expiry; sports/weather
   do not — so crypto should be fetched at the head of a pass, not wherever it currently falls.
3. Have the collector's `run()` detect a ticker whose close time has already passed at actual
   fetch time and count it as a drop (lower `completeness_ok`) rather than a clean capture.

No strategy claim, no P&L, no registry change. No new `price_source_tag`; every line audited
here already carries its own collector's tag. Two-agent rule N/A for the write-up itself (a
data-quality finding, not a bootstrap CI/kill decision) — but the underlying numbers DID go
through the standing two-agent process (tape-auditor find → independent verifier re-derivation
→ this corrected write-up), consistent with house practice for anything landing in `findings/`.

## Lessons

New rows **L168** and **L169** in `kb/lessons/00-lessons.md` (both `UNENFORCED` — the repair
above is a collector change, Ryan-gated; the leg-collinearity discipline is
protocol/methodology, not a static assert).
