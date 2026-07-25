# VPS collector's SECOND death (61.7h silent, unnoticed) + cloud-leg slot attrition to 5/8

**Date:** 2026-07-25 (research loop, IDLE RUN under LOOP-QUEUE.md v3 idle-run policy (c) —
tape data-quality deep-dive — which escalated into policy-(a)-style enforcement: a new
non-gating advisory in `scripts/invariants.py` + tests)
**Status:** descriptive/ops finding. **NO strategy claim, NO registry change, NO bootstrap CI,
NO price and NO P&L claim in this run** — so `kb/strategies/00-index.md` is deliberately
untouched and the real-ask CI bar (CLAUDE.md prime directive #1) is not implicated here.
The project still has **0 proven edges**.
**Two-agent trail:** producer (`tape-auditor`) → independent `verifier`. Round 1 **REFUTED**
three sub-claims (a fabricated commit hash, a broken repro command, and five mislabeled
percentage baselines) and **downgraded two framings**; all corrections are folded in below.
Final verdict on the outage claim: **CONFIRMED (post-correction)**.
The only P&L number anywhere in this run is the standing paper ledger's **$+18.15**, tag
`broker_truth` (see "Paper sub-pass").

## Headline

The VPS `:23` collector leg — declared **RECOVERED** three days ago (L129 /
`findings/2026-07-22-vps-collector-recovered-post-pr151.md`) — **died a second time** and has
been silent for **61.7h** with nobody noticing, while the surviving cloud `:53` leg
**independently degraded** from 8-of-8 to **5-of-8** scheduled passes/day. Three queue items
(Q36, Q42, Q43) are data-gated by exactly this. Nothing is stranded: the VPS is dead, not
merely failing to push.

## Evidence (all independently re-derived by the verifier against committed tape)

### 1. The VPS leg's last breath

Last capture written by the VPS leg anywhere in committed tape:

```
captured_at = 2026-07-22T17:29:49.498223+00:00     (in tape/weather_books/dt=2026-07-22.jsonl)
```

Silence = **61.7h** as of `2026-07-25T07:12Z`. There are **ZERO** hourly-dual-family lines in
the `:20-29` minute bucket anywhere after that timestamp.

**The attribution method that IS sound:** per-line `captured_at` **minute-of-hour bucketing**
(vps = minutes 20-29, cloud = minutes 50-59) **restricted to `kind=="hourly-dual"` families**,
per `scripts/tape_gap_monitor.py`'s `COLLECTOR_MINUTE_BUCKETS` (L118's calibration). Both
restrictions matter — see §4 for why the family restriction is load-bearing.

### 2. RECURRENCE — and the dwell window nobody stated

L129 declared this leg RECOVERED at **2026-07-21T22:41Z**. The recovery dwelled only:

- **18.8h** measured from L129's declared recovery moment (`22:41Z`), or
- **18.1h** measured from the first `:23`-cadence pass (`2026-07-21T23:23:01Z`).

**State the anchor whenever you quote this.** An earlier draft of this finding said "17h";
that figure silently dropped the `2026-07-21T23:23:01Z` pass — which is the very pass L129
cited as its recovery evidence. **Do not use 17h.** Either 18.1h or 18.8h, with its anchor
named.

A point observation ("it produced a pass, therefore it recovered") cannot distinguish a fixed
collector from a collector that will die again within a day. It died again within a day.

### 3. NOTHING IS STRANDED — the VPS is dead, not merely unable to push

The verifier fetched **all 487 remote heads**. No `vps-collector` commit exists after
`2026-07-22T17:32:20Z` on **any** ref. And:

```
origin/tape/hourly-202607250406Z:tape  ==  HEAD:tape
tree hash 23b44416b723b76fca0b130feba53f719d2b5676
```

So the failure mode is *not* the familiar push-fallback-to-`tape/hourly-*` branch (step-0b's
whole reason to exist). The process is gone.

**Step-0b stranded-tape sweep, plain observation:** this run's sweep found **ZERO missing
lines**. The only branch newer than the last-swept `tape/hourly-20260724T1857Z` is
`tape/hourly-202607250406Z`, whose `tape/` tree is byte-identical to main's (hash above).

### 4. The cloud leg degraded independently — this is a second, separate failure

Expected slots `{00,03,06,09,12,15,18,21}` UTC (`53 */3 * * *`). Realized:

| dt | passes realized | note |
|---|---|---|
| 2026-07-20 | **8/8** | healthy |
| 2026-07-21 | **7/8** | |
| 2026-07-22 | **6/8** | last healthy-ish day; the volume baseline below |
| 2026-07-23 | **5/8** | `orderbook_depth` **3/8**, `weather_books` **1/8** |
| 2026-07-24 | **5/8** | `orderbook_depth` **3/8** |

Per-family volume collapse, **07-24 vs the 07-22 baseline** (label the days explicitly — an
earlier draft mislabeled these as "07-23/07-24"):

| family | 07-24 vs 07-22 |
|---|---|
| `orderbook_depth` | **-88.9%** |
| `weather_books` | **-86.6%** |
| `sports_pairs` | **-82.0%** |
| `perp_tape` | **-88.0%** |
| `crypto_hourly` | **-80.0%** |

For **07-23 vs 07-22** the figures differ and must not be conflated: `weather_books`
**-94.9%** (worse than 07-24), `orderbook_depth` **-88.7%**, `sports_pairs` **-78.9%**.

**The 09-UTC econ artifact (why the family restriction in §1 is load-bearing).** The
`econ_prints`/`anomalies` legs land at **09:20-09:29** (e.g. `econ_prints` dt=2026-07-19 at
09:20 and 09:21; dt=2026-07-21 at 09:23/09:24/09:28/09:29 — an earlier draft narrowed this to
09:25-09:29), which falls inside the VPS `:20-29`
bucket and forges a "VPS is alive" reading in any **raw** `:20-29` count. It was present
through the *entire* first outage (07-19T09, 07-20T09, 07-21T09) and again on 07-23T09.
Restricting liveness counts to `kind=="hourly-dual"` families removes it. Note that
`scripts/tape_gap_monitor.py`'s own raw counts still carry this artifact.

### 5. DETECTION EXISTED BUT WAS NEVER INVOKED

`scripts/tape_gap_monitor.py` right now names `collector_diagnosis = "vps_dead"` on **six**
families (`sports_pairs`, `crypto_hourly`, `orderbook_depth`, `weather_books`,
`polymarket_macro_pairs`, `perp_tape`; **10 families alerting in total**) and ends with:

```
[tape_gap_monitor] alerts present but no NTFY_TOPIC_URL / --ntfy-url supplied — ntfy POST skipped (no-op)
```

**Framing correction (verifier-imposed, use this wording).** Do NOT write "the detector worked
for 61h and paged nobody." The verifier grepped the whole repo: the monitor has **no scheduled
caller at all** — no cron, no workflow, no `collection/` call site. The true statement is:

> The monitor would have named `vps_dead` at any moment in the 61h window; **nothing schedules
> it**, and its only escalation path is a documented no-op when `NTFY_TOPIC_URL` is unset.

A detector with no scheduled caller is not enforcement. That is the lesson (L156) and it is
what this run's code milestone fixes: detection is now attached to the one command every run
is required to run and read.

## Downstream gate costs (all re-run live by the verifier)

**Q36 part (1)** — `python3 scripts/q36_kxtempnych_settlement_basis_probe.py`:

```json
{"status": "INSUFFICIENT DATA", "n_settled_events": 2, "min_events": 10}
```

Exactly **2** distinct settled KXTEMPNYCH event-hours: `KXTEMPNYCH-26JUL1707` (dt=2026-07-17)
and `KXTEMPNYCH-26JUL2205` (dt=2026-07-22). This is an **ADVANCE** from the previously-recorded
`n=1` — prior Q36 status blocks assert that `settlement_ledger` held exactly one settled event
across its whole git history, and **that assertion is now stale**; this run's new Q36 Status
line corrects it. Still gated at **2/10**.

**The causal link (verified).** All 5,000 lines of `tape/settlement_ledger/dt=2026-07-22.jsonl`
carry a single `captured_at = 2026-07-22T10:31:41.942809+00:00` — UTC hour **10**, matching the
`SETTLEMENT_LEDGER_UTC_HOUR = 10` gate in `collection/hourly_pass.py` (gate ~line 561, constant
~line 150, pass-start `ts` ~line 365). The cloud cron starts passes at `:53` of hours
`{0,3,6,9,12,15,18,21}`, so `ts.hour` is **never** 10 — **the VPS is the only writer this family
can ever have.** Its second death re-freezes the feed.

> **Do NOT cite a commit hash for this file.** An earlier draft cited `01c74de`, which the
> verifier proved touches no `settlement_ledger` path at all; and the "which commit added it"
> answer varies by ref set because `main` squash-merges. Cite the `captured_at` **hour** — that
> is durable.

**Q43** — `python3 scripts/q43_perp_binary_consistency_probe.py`, capture density/day vs its own
advisory floor of 10: `dt=2026-07-23` = **3**, `dt=2026-07-24` = **3**, `dt=2026-07-25` = **1**.
THIN DAYS now **6 of 9** (was 3 of 6 on 07-23). Density-gated, and **worse** than when last
measured.

**Q42** — the cross-venue funding join legs (`perp_tape`, `hyperliquid_funding`) sit on the same
starved pipe: 3 / 3 / 1 captures on 07-23 / 07-24 / 07-25, versus 25 and 17 on 07-22.

## What shipped this run (code, by a collector-engineer; described here, not authored here)

- **A NON-GATING "dead collector-leg advisory" in `scripts/invariants.py`.** Computed from
  committed tape only — no network, no git, no commit-author strings. It **imports** the leg
  minute-signatures and family config from `scripts/tape_gap_monitor.py` rather than duplicating
  them. Named thresholds: `DEAD_LEG_SILENCE_HOURS = 24.0`, `DEAD_LEG_ALIVE_HOURS = 6.0`,
  `DEAD_LEG_LOOKBACK_DAYS = 10`. It fires only on the "one of two staggered collectors died"
  signature (a leg silent >= 24h while another produced within 6h); it reports **AMBIGUOUS** and
  never guesses a name when both scheduled legs are silent (the L118/L120 attribution
  discipline); and it prints to **stderr without ever touching the exit code**.
  **Rationale for non-gating:** a dead VPS cron is severe AND physically un-fixable from a cloud
  sandbox; gating would convert one silent failure into an indefinite loop halt.
- **`tests/test_dead_collector_leg_advisory.py`** (21 tests),
  including a real-tape acceptance test made **time-bomb-proof** (lesson L140) by freezing BOTH
  axes: an injected `_SLICE_NOW = 2026-07-24T20:00Z` **and** an input cap at
  `max_day = 2026-07-24`. The verifier attacked this specifically against a true 1.2 GB copy of
  tape and confirmed it survives a fabricated FULL VPS recovery on `dt=2026-07-25` and
  `dt=2026-07-26`, and a far-future `dt=2027-06-01`.
- **Honest caveats, recorded so a future reader is not misled:**
  1. The test **departs from L140's LETTER** (it hardcodes a calendar `now`) while satisfying its
     **INTENT** by freezing the input slice instead. Stating this plainly so nobody reads it as
     an L140 violation.
  2. **One narrow vector survives:** a retro-APPEND of a `:20-29`-minute line into an
     already-closed `dt <= 2026-07-24` file would flip it. L140's own prescribed fix would not
     cover that either.
- The advisory's live output on current tape names the vps leg, its last-seen timestamp, the
  **61.4h** silence at advisory runtime, and that cloud/other are still alive.

## Gates

- `python -m pytest -q` → exit **0**, **1750 collected, 0 failures** (verifier independently
  re-ran AFTER the final code change; an earlier draft of this line quoted a mid-edit 1743).
- `python scripts/invariants.py --full` → exit **0**, unchanged from baseline.
- Worth recording: the **GitHub-issue-#157 cryptography/pyo3 baseline failures**
  (`tests/test_invariants.py`, `tests/test_ws_depth.py`, `tests/test_polymarket_us_live.py`)
  **did NOT reproduce in this sandbox** — those 236 tests all passed and `cryptography` imports
  at **41.0.7**. This run's baseline-failure set is **EMPTY**.

## Paper sub-pass (LOOP-QUEUE step 9)

`execution/strategy_api.SHADOW_REGISTRY` is non-empty (`{s14_ladder_underwriting}`), so the
sub-pass ran. `python scripts/paper_pass.py`: **0 newly-eligible events processed** (178
deferred on caps, 264 deferred on coverage, 122 already in the ledger) → **no new ledger lines
appended**. Standing state: realized P&L **$+18.15** — **`real_bid` fills settled at
`broker_truth`**, not a single-tag number. Counted over `paper/ledger/dt=*.jsonl`: **984** lines
tagged `price_source_tag="real_bid"` (the fills) and **984** tagged `broker_truth` (the
settlements), plus 2,595 order lines with no price tag. **No synthetic price is involved** — no
prime-directive break — but the tag must be stated accurately per CLAUDE.md's trust defaults.
984 settled contracts, 0 open positions, open notional $0.00. Honestly: **S14 is `dead ✗` at real
fills per Q34** — this is paper-infrastructure validation, not edge.

## Lessons filed

- **L156** — a detector with no scheduled caller is not enforcement (**enforced by this run**).
- **L157** — a "RECOVERED" declaration needs a stated dwell window (**UNENFORCED**).
- **L158** — commit-author archaeology is unsound on a squash-merge repo (**enforced by
  construction**).
- **L159** — the 09-UTC econ slot is a permanent false `:2x` signal (**enforced by
  construction**, with the `tape_gap_monitor.py` raw-count caveat flagged).
- **L160** — tree-hash equality is the cheap authoritative stranded-tape containment test;
  `git merge-base --is-ancestor` must never be used for it (**UNENFORCED**).
- **L161** — malformed tape-branch names are a recurring defect and a data-loss risk in step-0b
  (**UNENFORCED**). Census re-derived post-review: **44 of 192** remote `tape/*` branches fail
  `^tape/hourly-[0-9]{8}T[0-9]{4}Z$` (2026-07-25 ~08:5xZ); the row ships its counting command
  because the count drifts as branches accumulate.
- **L162** — a gate result quoted mid-edit is stale by the time the run lands (this finding's own
  gate line first said 1743/14 before the final tree said 1750/21); re-take the gate after the
  last change or write it as a floor, and inline the command behind any count-bearing lesson row
  (**UNENFORCED**).

## Ryan-side action needed

1. **Restart the VPS collector** (`:23` leg) — second death, 61.7h and counting; it is the only
   possible writer for `tape/settlement_ledger/` (Q36 part 1) and half the cadence for five
   other families.
2. **Investigate the cloud cron's dropped slots** — 8/8 → 5/8 over five days, with
   `orderbook_depth` at 3/8 on both 07-23 and 07-24.

**Notification-pipe gap (flagged per LOOP-QUEUE step 8(c)):** **no ntfy topic URL was supplied
to this session**, so step 8's mandatory phone note could not be posted — and 8(b) requires
`Priority: high` for exactly the kind of item listed above. The retired topic in
`config/notify.topic` was deliberately not used (nothing reads it). The weekly retro should see
this.

## Reproduce

```
# NOTE: run WITHOUT --no-notify. The "ntfy POST skipped (no-op)" line quoted in §5 sits behind
# the `if not args.no_notify:` branch (scripts/tape_gap_monitor.py ~L890, message ~L833), so
# --no-notify suppresses exactly the line this finding quotes. With no NTFY_TOPIC_URL set, the
# command below prints that line, exits 0, and makes NO network call.
python3 scripts/tape_gap_monitor.py --now 2026-07-25T07:12:00Z
python3 scripts/q36_kxtempnych_settlement_basis_probe.py
python3 scripts/q43_perp_binary_consistency_probe.py
python3 scripts/invariants.py --full          # advisory prints to stderr, exit code unchanged
python -m pytest -q tests/test_dead_collector_leg_advisory.py

# stranded-tape containment, the CORRECT test (never merge-base --is-ancestor):
git rev-parse origin/tape/hourly-202607250406Z:tape
git rev-parse HEAD:tape

# the settlement_ledger causal link (cite the hour, never a commit hash):
grep -o '"captured_at": *"[^"]*"' tape/settlement_ledger/dt=2026-07-22.jsonl | sort -u
```
