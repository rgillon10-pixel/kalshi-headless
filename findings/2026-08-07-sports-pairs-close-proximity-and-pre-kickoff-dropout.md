# sports_pairs close-proximity + pre-kickoff dropout (idle-run policy (c), 2026-08-07)

**Status: data-quality / data-adequacy only. No CI, no P&L, no registry flip, no kill.**
Nothing here re-opens or re-closes any strategy: S7/S11/S13/S22/S23/S24/S28/S29 keep the
verdicts they already carry, and S79 stays `collect-and-revisit` (Q54). **Two-agent rule is
N/A** — this run produces no verdict-class claim (no bootstrap CI destined for `kb/`, no
registry status flip, no kill decision). The harness exposed no `Task`/subagent tool, so no
independent `verifier` was dispatchable in any case; the same main-context-build precedent as
L287/L288/L290/L291 and Q53 milestone 3. In place of a second agent, every headline number
below was **re-derived a second time by a throwaway stdlib-only parser** (own ISO parser, own
line-dedup, zero imports from `core/` or `scripts/`) and matched bit-for-bit — that is a
producer-side robustness check, not a verifier verdict, and it is labelled as such.

All prices touched here are `real_ask` (379,664/379,664 tagged outcomes, 0 untagged). No price
is quoted as a fill.

## Why this family, why now

`tape/sports_pairs/` is the repo's **largest** tape family — 35 canonical `dt=*.jsonl`
day-files, 147,264 lines, 682 passes, 2026-07-03 → 2026-08-07 — and the substrate under every
sports strategy this project has run. Its only dedicated finding,
`findings/2026-07-19-sports-pairs-join-adequacy-dataquality.md`, measured a **different**
question (can a `synthetic` fair anchor be joined to a real resting book?) over the family's
first 16 days and its `sports_pairs.v1` schema. Recent idle-run(c) passes went to
`crypto_hourly` (08-06), `econ_prints` (08-05), `polymarket_cpi_pairs` (08-05),
`kalshi_trades` (08-04), `weather_books` (08-04), `orderbook_depth` (08-04) — the biggest
family has not had a look in 19 days, and in that window its schema changed.

The `sports_pairs.v2` schema (first record `2026-07-12T21:23:03.072875Z`) added `game_start`
(Kalshi's `occurrence_datetime`). **Only with that field does this question become answerable
at all:**

> How close to its own kickoff does this tape actually observe a game?

Every near-close sports entry rule — "taker the book in the last hour", "rest a maker quote
into kickoff", S79's hold-to-settlement lane — is silently conditioned on the answer, and
**L251** is the standing warning that an entry rule which looks temporal can in fact be
selecting on a collector artifact.

Built `scripts/sports_pairs_close_proximity_audit.py` (read-only, fully offline; imports the
standard library + `core.timeutil.parse_iso_utc` only — no bare `fromisoformat`, L136/L162
lane) + `tests/test_sports_pairs_close_proximity_audit.py` (**24 tests**: 18 pure-function
against hand-built fixtures, including a clean case AND a synthetic-defect case for each
detector per L191, plus 6 real-tape acceptance tests written as **directional bounds** — the
family is actively collected, and an acceptance pin a future hourly pass would break is a pin
that gets deleted). Report: `reports/sports_pairs_close_proximity_audit.json`.

## 0. The availability correction, applied before any headline (L302 class)

2,273 distinct v2 games publish a `game_start`. **637 of them have a kickoff AFTER the tape's
last pass** (`2026-08-07T12:55:00.209755Z`) — Kalshi lists games days ahead, so the family is
full of markets for games that have not happened. Their terminal observation gap is bounded by
the tape's end date, not by the collector, and pooling them measures when we stopped
collecting.

| statistic | uncorrected (n=2,267) | availability-corrected (n=1,636) |
|---|---|---|
| median terminal pre-kickoff gap | **216.1 min** | **155.7 min** |
| p75 | 1,467.5 min | 245.9 min |
| p90 | 4,745.0 min | 399.6 min |

The correction moves the headline by 39% and the tail by 6-12x. Scored population =
games whose kickoff falls inside `[first v2 capture, last family pass]`; that condition also
guarantees at least one pass ran **at or after** kickoff, which is exactly when the terminal
gap is uncensored. All 1,636 have ≥1 pre-kickoff capture (0 with none); 63 also have a
post-kickoff capture.

## 1. FINDING — a near-close observation is the exception on this tape, not the rule

Availability-corrected, 1,636 games, `real_ask` throughout:

| window before kickoff | games with any observation in it | share |
|---|---|---|
| ≤ 5 min | 4 | 0.24% |
| ≤ 15 min | 32 | 1.96% |
| ≤ 30 min | 52 | 3.18% |
| **≤ 60 min** | **163** | **9.96%** |
| ≤ 120 min | 610 | 37.29% |
| ≤ 180 min | 889 | 54.34% |
| ≤ 360 min | 1,379 | 84.29% |

Median terminal gap **155.7 min**; p5 is 37.0 min, so even the best-observed twentieth of
games is not seen inside half an hour of kickoff.

**What this bounds.** A sports strategy whose entry rule is "within 60 minutes of kickoff" has
**at most 163 game-units** of substrate on this family — above L41's n≥10 floor, so the lane is
not dead, but it is **10% of the tape**, and it collapses per series (the L6 bootstrap unit is
the game, and any series-conditioned variant re-splits this number):

| series | games reached | median gap | ≤60 min |
|---|---|---|---|
| `KXMLBGAME` | 292 | 100.4 min | 66 |
| `KXUECLGAME` | 154 | 261.1 min | **0** |
| `KXNPBGAME` | 103 | 185.2 min | 21 |
| `KXKBOGAME` | 95 | 185.9 min | 22 |
| `KXUCLGAME` | 52 | 140.5 min | 1 |
| `KXMLSGAME` | 51 | 95.7 min | 3 |
| `KXARGPREMDIVGAME` | 45 | 185.6 min | **0** |

At ≤30 min the whole-family population is 52 games; European club football contributes
essentially nothing at any near-close horizon.

## 2. FINDING — collector cadence does NOT explain it (the null is rejected, 4.09x)

The obvious explanation is "the collector is only 3-hourly now." Stated as a falsifiable null:
if a game were captured on **every** family pass until kickoff, its terminal gap would be
~U(0, C) for C the family's own local cadence, and near-close availability would be
mean(min(1, 60/C)).

Scored on the 1,151 games with ≥3 family passes in their 12 h pre-kickoff window (local
cadence p25/p50/p75 = 60.0 / 179.8 / 180.6 min):

- **predicted P(gap ≤ 60 min) under the null = 0.5190**
- **observed = 0.1268**
- **shortfall = 4.09x → null REJECTED**

The internal consistency check says the null's *shape* is right and only its *support* is
wrong: among the 48.57% of games whose gap is within one cadence interval, mean(gap/C) =
**0.5001** against the U(0,1) reference of 0.500 — textbook. But the full distribution has
median gap/C = **1.029**, p90 = 2.194, max = 32.2: the typical game's last observation is more
than a *whole extra pass* earlier than "captured until kickoff" would give.

## 3. FINDING — 28.55% of games are PROVABLY dropped before their own kickoff

The non-inferential version. A game is called dropped only when at least one family pass that
**did capture the game's own `series`** ran strictly between the game's last observation and
its kickoff, and that pass does not contain the game. This names the passes rather than
arguing from a distribution, and the same-series condition is what stops a series-level fetch
error from manufacturing dropouts.

- **467 / 1,636 = 28.55% provably dropped pre-kickoff**; 1,169 (71.45%) are cadence-limited
  only (no covering pass exists, so nothing is proven either way).
- Missed passes per dropped game: median 1, p90 2, **max 14**.
- Drop lead (kickoff − first missed pass), a **LOWER BOUND** — the true drop instant lies
  between the last observation and the first missed pass, and the tape cannot resolve it finer
  than its own cadence: p25 5.8 / **median 15.9** / p75 37.0 / p90 53.0 min.
- Worked example from the report: `KXAFLGAME-26JUL160530SKSGEE`, kickoff
  `2026-07-16T12:30:00Z`, last captured `11:23:02Z`, and pass `20260716T122302Z` — 7.0 min
  before kickoff — captured `KXAFLGAME` without it.

**Mechanism, located in code but deliberately not over-attributed.**
`collection/sports_pairs.py::_fetch_open_markets_raw` queries `/markets` with
`status: "open"` **only**, and `discover_groups` keeps a group only if
`is_moneyline_group` holds (2-3 markets, every title matching the `... Winner?` form). Either
gate can drop a game, and this tape cannot separate them — a record persists no market
`status` and no `close_time`, so the family cannot answer its own dropout question. That is
the same shape as **L222** (`econ_prints` could not answer its provenance question because the
record carried no `mode` field); a `status`/`close_time` passthrough is the collector-lane fix,
and it is **not built here** (write-path; L221/L222 lane).

What IS excluded by measurement: the hollow-book explanation. `run()` appends a record for
every confirmed group **unconditionally** — a game with no live asks would still be written
with `captured_outcomes: 0` — and empirically `completeness_ok` is `True` on **147,036 /
147,036** records, split only 61,444 × (2 of 2) and 85,592 × (3 of 3). Absence from a pass is a
listing-level fact, never a pricing-level one.

**Why this matters beyond data hygiene.** If the drop is Kalshi-side (the moneyline book leaves
`status=open` before the ball is thrown), then the *last hour before kickoff is partly not
tradeable at all*, and a near-close entry rule is not merely under-sampled — it is partly
unfillable, which is a prime-directive question, not a collection question. If it is
collector-side (`is_moneyline_group` losing a group whose titles or member count changed near
close), then the tape understates a real fillable window. **This finding does not decide
between them** and no strategy should be priced off either reading until a collector-lane
`status`/`close_time` passthrough settles it.

## 4. Secondary hazards found in passing

1. **`game_date` is not the UTC kickoff date on 44.85% of v2 records** (38,804 / 86,520). The
   offset takes exactly two values — 0 days (47,716) and **+1 day** (38,804) — and every
   disagreeing record has a UTC kickoff hour in 00-06 (peak 02Z, n=10,880). `game_date` is
   parsed out of the **ticker** by `parse_sports_ticker`; `game_start` is Kalshi's UTC
   `occurrence_datetime`. So `game_date` is a local/US-evening calendar date. Any probe that
   buckets or joins on `game_date` as if it were the UTC kickoff day **mis-dates nearly half
   the family by a full day** — a live join hazard against any UTC-keyed settlement ledger.
2. **41.16% of the family (60,516 `sports_pairs.v1` records) carries no `game_start` at all**,
   so §1-§3 are *structurally unanswerable* on the tape before 2026-07-12T21:23Z. Reported as a
   denominator, not hidden in a total (L296's reading rule).
3. **The sharp-odds anchor is still effectively absent**: `odds_leg.status` over 147,036
   records is `blocked_key` 104,457 / `unmapped_series` 17,848 / `not_selected` 15,753 /
   `unmatched` 8,738 / **`matched` 240 (0.163%)**. S7/S11's de-vigged signal leg remains
   credential-gated in fact, not just on paper.
4. **Cadence decayed ~8x**: peak 49 passes/day (2026-07-06, ~29 min) → recent-7-day mean 5.86
   passes/day (~246 min). Cause is already diagnosed elsewhere and is NOT re-derived here
   (`findings/2026-07-25-vps-collector-second-death-and-cloud-slot-attrition.md`,
   `findings/2026-08-03-vps-collector-true-outage-273h-burst-contamination-blind-spot.md`).
   Consequence for §1: near-close substrate accrues far more slowly now than it did in July.
5. **One missing calendar day** — `2026-07-09` has no canonical `dt=*.jsonl`; its data sits in
   the non-canonical directory `dt=2026-07-09/`, alongside `dt=2026-07-02/` and
   `dt=2026-07-10/`. The L25 format-regression debris already named in the 2026-07-19 audit;
   unchanged, re-reported so the 35-day-file denominator is honest.
6. **228 byte-identical duplicate lines**, all in `dt=2026-07-28.jsonl`, all one pass
   (`20260728T065420Z`) landed twice. **Already recorded** —
   `findings/2026-08-05-duplicate-tape-line-census-l282-attribution-falsified.md` (L285) lists
   this exact row, and it is the same 2026-07-28 double-landing incident L282 diagnosed for
   `orderbook_depth`. Not re-attributed here. They are deduplicated before scoring and move no
   number in this finding: the independent stdlib re-derivation, which dedupes independently,
   returned 1,636 / 155.7 min / 163 / 467 identically.

## Reproduce

```
python3 scripts/sports_pairs_close_proximity_audit.py
python3 -m pytest tests/test_sports_pairs_close_proximity_audit.py -q
```

Report written to `reports/sports_pairs_close_proximity_audit.json`.
