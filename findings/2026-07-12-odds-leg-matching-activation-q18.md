# Q18 — Odds-leg matching activation (S11's anchor)

**Date:** 2026-07-12 (research loop, protocol v3)
**Status:** code landed; live activation confirmation pending the next keyed VPS pass.

## Diagnosis

`ODDS_API_KEY` went live on the VPS 2026-07-10. Since then every VPS pass with the key
present has written `odds_leg.status="unmatched"` — 7,476 records over 2026-07-11/12 — while
every cloud pass (key absent by design) correctly wrote `"blocked_key"`.

Read `collection/sports_pairs.py` directly: the matching layer was never implemented on
`main`. `fetch_the_odds_api_soccer()` existed but was **never called** from `run()`; the
`odds_leg` field was a hardcoded literal —

```python
"odds_leg": {"status": "blocked_key"} if not odds_api_key else {"status": "unmatched"},
```

So the 7,476 `"unmatched"` records do not represent 7,476 failed match *attempts* — no
odds-api HTTP call was ever made. The status was fabricated the moment a key was present.
Two consequences: (1) the-odds-api quota was **not** actually being burned (no calls fired),
contrary to Q18's initial "quota burn" framing; (2) the tape has been silently useless for
S11 since key day, because `"unmatched"` reads as "we tried and found nothing" when the
honest status was "not attempted."

PR #4 (`worktree-q1-odds-leg`, opened 2026-07-03, 9 days stale) already built the missing
matching layer against that day's `main` but never landed — the branch has since diverged by
~10,000 file-changes' worth of unrelated history, making a direct merge impractical. Its
actual code (`collection/odds_api.py`, the `sports_pairs.py` integration diff, and its test
suite) was reviewed and is sound: kickoff-primary matching with a team-name fallback, honest
per-game statuses, and built-in quota discipline. Ported it onto current `main` by hand
(git-diffed the two relevant files against the stale branch, applied cleanly with no
conflicts — `validation/v3_market.py`'s PR #4 diff was **not** ported, since current `main`
has since grown methods, `events()`/`candlesticks()`, that PR #4's stale diff would have
deleted).

## What landed

- **`collection/odds_api.py`** (new): `enrich_records()` — Kalshi game → the-odds-api event
  matching keyed primarily on kickoff time (`game_start`/`occurrence_datetime` vs
  `commence_time`, ±3h window), confirmed by team-name similarity (`team_match_score`:
  accent-fold, club-suffix strip, containment/initials credit). Honest per-game statuses
  (never a silent drop): `matched` / `blocked_key` / `unmapped_series` / `not_selected` /
  `sport_not_active` / `fetch_error` / `quota_floor` / `no_match` / `ambiguous` /
  `no_bookmaker`. Sharp-first bookmaker order (Pinnacle preferred, first-available
  fallback, recorded either way). De-vig via `devig_multiplicative` (moved from
  `sports_pairs.py`, same math) — every matched fair-prob is tagged `synthetic`; the
  Kalshi `real_ask` legs remain the only fillable prices on the record.
- **Quota discipline** (already built into the ported module, no changes needed): the
  quota-free `/v4/sports` catalogue call runtime-verifies each sport is active before
  spending a credit; `DEFAULT_SPORTS` scopes calls to S7's targets (World Cup + NFL + NBA);
  `ODDS_API_QUOTA_FLOOR` (default 50) degrades the remaining sports in a pass to
  `quota_floor` rather than burning the key to zero; `x-requests-remaining` /
  `x-requests-used` persisted into the pass summary every call.
- **`sports_pairs.py` schema → v2**: `game_start` (from `occurrence_datetime`) and each
  outcome's `outcome_name` (parsed from `yes_sub_title`, e.g. `"Reg Time: Portugal"` →
  `"Portugal"`) are now persisted on every record, keyless or not — so a keyless capture
  stays replayable against the-odds-api later, per the same discipline S7a used for
  settled-market backfills.
- 26 new/changed unit tests (`tests/test_odds_api.py` new, `tests/test_sports_pairs.py`
  extended) — fully offline, stub HTTP, no network. 630 tests green total,
  `python scripts/invariants.py --full` green.

## Live smoke (keyless, real Kalshi data, this run's cloud sandbox — no key present by
design)

`python -c "collection.sports_pairs.run(...)"` against a temp tape dir (not committed —
code-only change): **114/114 candidate moneyline games captured complete**, `schema_version`
correctly `sports_pairs.v2`, every record's `game_start` and each outcome's `outcome_name`
populated from live fields (e.g. `KXAFLGAME-26JUL160530SKSGEE`: `game_start
"2026-07-16T12:30:00Z"`, outcomes `"Geelong Cats"` / `"St Kilda Saints"`), `odds_leg` honestly
`{"status": "blocked_key"}` (no key in this sandbox — correct, cloud runs never get the key
by design). Confirms the v2 schema change is live-data-correct without needing the key to be
present here.

## What is NOT yet confirmed

This sandbox has no `ODDS_API_KEY` (cloud runs never get it, per Stop rules) — so the actual
event-matching-against-real-odds-api-events path (`enrich_records()` against a live
the-odds-api response) is only unit-tested here, not live-smoked. **Success condition
(unchanged from Q18's own spec):** the next keyed VPS hourly pass writes ≥1
`odds_leg.status="matched"` record. That is the signal a future run should look for in
`tape/sports_pairs/` before flipping S11's registry status.

## Registry

**Not flipped this run.** `kb/strategies/00-index.md` S11 stays `idea` — per Q18's own
success criterion, S11 only flips to `data-collecting` once matched pairs actually flow
from a live keyed pass. Flip that on the run that first confirms `odds_leg.status="matched"`
in committed VPS tape.

## PR #4

Superseded — its actual matching code was ported cleanly (see above); its stale branch
(diverged ~10,000 files from current `main`) is not mergeable and was left closed with a
comment pointing at this landing, per Q18 milestone (4).
