# The sports fair-anchor substrate: two lanes, one dead by design, one dead by a quota selector

`2026-08-08` · research loop, IDLE RUN policy (c) · **DESCRIPTIVE — no registry flip, no
bootstrap CI, no kill decision** · script `scripts/sports_anchor_substrate_audit.py` ·
artifact `reports/sports_anchor_substrate_audit.json` · tests
`tests/test_sports_anchor_substrate_audit.py` (30) · closed window `--max-day 2026-08-07`

## Why this family, and what is genuinely new here

Four candidates in `kb/strategies/00-index.md` are scored against an **external bookmaker's
de-vigged fair probability** rather than against Kalshi's own price: S7 (dead), S13 (dead),
S21 (DEAD-by-data-adequacy) and **S11**, the only sports-maker lane still `data-collecting`.
That anchor has two lanes in this repo, and no audit had ever looked at them together:

| lane | directories | writer | scheduled? |
|---|---|---|---|
| **backfill** | `sports_clv`, `sports_history`, `sports_clv_s7`, `sports_history_s7`, `sports_maker_fillsim` | `collection/sports_history.py`, `scripts/sports_history_s7a.py`, `scripts/sports_clv_s7.py`, `scripts/s13_maker_fillsim.py` | **no** — 5/5 `one_shot_no_scheduled_caller` |
| **live** | the per-record `odds_leg` sub-object inside `tape/sports_pairs/` | `collection/sports_pairs.py` → `collection/odds_api.py` | **yes**, every hourly pass |

**Prior art, stated up front so this finding is not read as bigger than it is.** `L305`
(2026-08-07, one day before this audit) already published the raw `odds_leg.status` census —
`matched` 240 rows = 0.163% — as a secondary observation inside a different audit. **This
finding does not re-claim that number.** What is new is everything the row count cannot tell
you: that the 240 rows are **4 distinct games**, that they stopped on a nameable day, *which
of three independent mechanisms* stopped them, and what population a future re-test is
actually left with.

## Finding 1 — the live anchor's entire lifetime yield is 4 games, and it ended 2026-07-18

Over 35 committed day-files (2026-07-03 → 2026-08-07), 148,463 records, 2,836 distinct
`event_ticker`s:

| `odds_leg.status` | rows |
|---|---|
| `blocked_key` | 105,884 |
| `unmapped_series` | 17,848 |
| `not_selected` | 15,753 |
| `unmatched` | 8,738 |
| **`matched`** | **240** |

The 240 `matched` rows are **4 distinct events / 2,836 = 0.141%**, all `KXWCGAME`, all
bookmaker `pinnacle`, all `price_source_tag: synthetic` (correct — a de-vigged fair
probability is a model output, never a fillable price):

```
KXWCGAME-26JUL14FRAESP   KXWCGAME-26JUL15ENGARG
KXWCGAME-26JUL18FRAENG   KXWCGAME-26JUL19ESPARG
```

They occur on 7 consecutive days, **2026-07-12 → 2026-07-18**, and nowhere else. The last
`matched` record anywhere in committed tape is **2026-07-18** — 21 days before this audit.
The S11 registry note "Anchor confirmed live 2026-07-13 … 6 `matched` records (2 WC games ×
3 passes)" describes the *second day of the only week this lane ever worked*.

## Finding 2 — three independent causes, only one of which is the durable one

They must not be conflated: they have different fixes and different lifetimes.

**(a) Missing credential — `blocked_key`.** `2026-07-23 → 2026-08-07` is **16 consecutive
day-files that are 100% `blocked_key`**, with no other status present on any of them. The
collector is running fine (3,686 records on 2026-08-07); `ODDS_API_KEY` is simply absent from
the environment of every pass. This is the loudest cause and the least interesting: it is one
env var on the VPS.

**(b) Series never mapped — `unmapped_series`.** `SPORT_KEY_BY_SERIES` holds 16 Kalshi
series. On 2026-07-22 alone, 3,920 rows / 230 events fell outside it (`KXUECLGAME`,
`KXMLSGAME`, `KXSCOCUPGAME`, `KXARGPREMDIVGAME`, …). A catalogue gap, cheap to widen.

**(c) The durable one — the `DEFAULT_SPORTS` quota selector.**

```python
# collection/odds_api.py
DEFAULT_SPORTS = ("soccer_fifa_world_cup", "americanfootball_nfl", "basketball_nba")
```

Only **3 of the 16 mapped series** are reachable without setting `ODDS_API_SPORTS`. Its three
entries are the World Cup (ended **2026-07-19**), the NFL (season opens September) and the NBA
(season opens October) — **all three are out of season on 2026-08-08**. Two committed day-files
prove the consequence, and they are the only two fully-keyed days that exist *after* the last
anchor, which is exactly the window where the selector is the binding constraint rather than a
moot one:

| day | events refused `not_selected` | rows refused | rows whose series IS in `DEFAULT_SPORTS` |
|---|---|---|---|
| 2026-07-21 | 105 | 206 | **0** |
| 2026-07-22 | **133** | **2,031** | **0** |

Every one of those series is already in `SPORT_KEY_BY_SERIES` and in season — `KXMLBGAME` 687
rows (`baseball_mlb`), `KXKBOGAME` 320, `KXNPBGAME` 305, `KXBRASILEIROBGAME` 203, `KXAFLGAME`
162, `KXCHNSLGAME` 140, `KXWNBAGAME` 108, `KXUCLGAME` 54, `KXALLSVENSKANGAME` 52. The
right-hand zero is the load-bearing number: **not one row of a selected sport existed on either
day**, so the selector conserved an API quota it never got the chance to spend while refusing
133 games it could have priced.

**The consequence that matters operationally:** restoring `ODDS_API_KEY` tomorrow would still
yield **0 matched games**, because (c) survives (a). The two causes are stacked, and the tape
shows (c) alone is sufficient to keep the lane at zero. This is not a proposal to widen the
selector — the collector's own comment budgets "24 hourly passes/day × 1 credit × 1 in-season
sport … fits a 500/month key", so `ODDS_API_SPORTS=all` over 16 series is ~384 credits/day and
would blow the quota inside two days. The honest fix is *select the sports that are actually in
season*, which is a live-config decision on Ryan's VPS, not a cloud-runnable code change.

## Finding 3 — the re-test population is 1 unit against a floor of 10

S21's registry row says it is "re-testable only on concurrently-collected fair-anchor + depth
tape". **That specific blocker is gone for these four games** — and this is the one genuinely
good news in this audit:

| event | depth-captured days | settlement surface |
|---|---|---|
| `KXWCGAME-26JUL14FRAESP` | 5 (07-10 → 07-14) | `settlement_ledger/dt=2026-07-17`, `q30_settlement_cache` |
| `KXWCGAME-26JUL15ENGARG` | 4 (07-12 → 07-15) | **none** |
| `KXWCGAME-26JUL18FRAENG` | 4 (07-15 → 07-18) | **none** |
| `KXWCGAME-26JUL19ESPARG` | 5 (07-15 → 07-19) | **none** |

**4/4 join `tape/orderbook_depth/` on 4–5 distinct pre-kickoff days each.** The L43/L9
non-overlap that killed S21 does not apply to them. But only **1/4** carries an ex-post
settlement on any of the nine committed settlement surfaces (L300), so the population that
passes *both* gates is **1 game** — against L41's 10-unit block-bootstrap floor. S21/S13 remain
untestable, and the binding reason has moved: it is no longer a timing gap between two tapes, it
is that the anchor lane has produced **4 games in its entire history and 0 in 21 days**.

**Backfill-lane control, independently re-derived.** `tape/sports_clv/` holds 104 records / 80
distinct events / 309 outcome rows, kickoffs **2026-06-04T00:30Z → 2026-07-03T22:00Z**, last
capture 2026-07-04T00:12:27Z (**35 days stale**). Against 3,203 distinct depth events the
overlap is **0/80** — S21's zero reproduces. The S21 row's `yes_ask ≤ 0.20` proxy denominator
reproduces **exactly (83)**; its `fair_prob ≤ 0.20` denominator re-derives to **80**, not the 81
the row quotes. That 1-market discrepancy is recorded as-measured rather than rounded to the
registry's number; it does not touch the headline zero, and this audit did not resolve it.

## Finding 4 — a green family-level monitor over a 100%-dead sub-field

`sports_pairs` **is** registered in `scripts/tape_gap_monitor.py::FAMILY_CONFIG`, and it passes
every check it has: it wrote 3,686 records on 2026-08-07, its cadence is normal, it is not
stale. Meanwhile the join-critical `odds_leg` sub-object inside it has been 100% degraded for 16
straight days. **No monitor in this repo reads `odds_leg`**, and no cadence or staleness check
can see it, because a sub-field's health is not a property of the file's timestamps.

The backfill lane fails the other way: **0 of its 5 directories** appear in `FAMILY_CONFIG` at
all, so the monitor makes no claim about them and cannot alert on 35 days of silence. Per L155
that is a coverage limit of the monitor, never evidence the families are healthy.

## Two-agent rule

**Not engaged, and here is why explicitly rather than by omission.** Every claim above is
DESCRIPTIVE — a count, a span, a join cardinality, a config literal. There is no registry
status flip, no bootstrapped CI, and no kill decision, so LOOP-QUEUE.md's two-agent verdict
rule does not bind. Separately: **no `Task`/subagent tool was exposed in this harness**, so no
independent `verifier` was dispatchable (the L287/L288/L290/L291/L295 precedent) — which is
also why this run deliberately confined itself to work the rule does not gate. Nothing in
`kb/strategies/00-index.md` is flipped; the S11 row gains a DESCRIPTIVE note only.

## Honest limits

- Whether an odds-API credit was actually *spent* on 07-21/07-22 is **not measurable from
  committed tape** — the tape records the refusal, not the HTTP call. The claim made here is
  only that no selected sport had a Kalshi game to match.
- Settlement coverage is tested by raw-substring membership across every committed
  `*settlement*` path. That over-counts if anything; a 1/4 result is therefore an **upper**
  bound on settlement availability, which makes Finding 3's conclusion conservative.
- The `unmatched` bucket (8,738 rows) is a *fifth* failure mode — key present, sport selected
  and fetched, but no bookmaker event matched the Kalshi game. It is not decomposed here;
  during the anchor week it coexisted with successful matches, so it is a matcher-quality
  question rather than a lane-outage question, and it is left for a future pass.
- All numbers are from the closed window `--max-day 2026-08-07` and include the 1,199
  `sports_pairs` lines this same run recovered from two stranded branches, so they are
  slightly larger than L305's same-family denominators taken one day earlier.
