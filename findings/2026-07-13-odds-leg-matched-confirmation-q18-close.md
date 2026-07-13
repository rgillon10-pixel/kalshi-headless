# Q18 close: odds-leg matched records confirmed live (S11 anchor)

**Date:** 2026-07-13 · **Run:** research loop (cloud) · **Verdict class:** data-flow milestone
(no P&L/CI claim) · **Two-agent rule:** applied, `verifier` subagent CONFIRMED.

## Claim

Q18's stated success condition ("the next keyed VPS pass must write ≥1
`odds_leg.status="matched"` record" in committed tape) has been met. `S11` (sharp-anchored
maker quoting on illiquid binaries) flips registry status `idea` → `data-collecting`.

## Evidence

`tape/sports_pairs/dt=2026-07-12.jsonl` (6,201 lines) status distribution:

| status | count |
|---|---|
| unmatched | 3,129 |
| blocked_key | 2,752 |
| unmapped_series | 170 |
| not_selected | 144 |
| **matched** | **6** |

The 6 `matched` lines span 3 VPS capture passes — `20260712T212303Z`, `20260712T222302Z`,
`20260712T232302Z` — each covering 2 World Cup moneyline games:

- `KXWCGAME-26JUL14FRAESP` (France vs Spain)
- `KXWCGAME-26JUL15ENGARG` (England vs Argentina)

Both matches are clean: `match_score=2.0` (maximum — exact team-name match both sides per
`collection/odds_api.py`'s `_pair_score`), `outcome_coverage="full"` (all 3 outcomes,
including Draw↔Tie, mapped 1:1). Bookmaker: `pinnacle` (preferred, per `DEFAULT_SPORTS`
config).

**Provenance.** `git blame` on `tape/sports_pairs/dt=2026-07-12.jsonl` shows the first
`matched` line lands on commit `6b6938d` ("tape: hourly pass 2026-07-12T21:26:13Z (vps)") —
the first VPS pass after Q18's port merged as `5b265a3`. No `matched` status exists earlier
in this file or in any other `dt=2026-07-1*` file. Not backfilled.

**De-vig math (re-derived independently by the `verifier` subagent, not just read off the
record).** For all 6 records: `Σ(fair_prob) == 1.000000`; `fair_prob_i` reproduces
`(1/decimal_odds_i) / Σ_j(1/decimal_odds_j)` to 6 decimal places; `book_overround` matches
`Σ(1/decimal_odds) − 1` to 6 decimal places (e.g. FRAESP 0.032948, ENGARG 0.032691/0.032662
across the 3 passes — Pinnacle's line moved slightly pass to pass, expected).

**Price-source-tag discipline (Hard Rule #3).** Kalshi legs (`yes_ask`/`yes_bid`/`no_ask`/
`no_bid`) tagged `real_ask` (fillable). The odds-api leg's `fair_prob` tagged `synthetic` (a
de-vig is a model, never a fill price). No violation.

## What this is not

Not a strategy verdict. Not a P&L claim. Not a CI bound. This is confirmation that the
odds-api matching pipeline built in Q18 (`collection/odds_api.py`, ported from the stale
PR #4 onto current `main` on 2026-07-12) actually produces matched Kalshi↔sportsbook pairs
end to end against live data — the anchor S11's eventual fill-sim needs. The dataset is
still thin: 1 bookmaker (Pinnacle), 2 games, 3 hourly passes. S11 stays a long way from a
binding test.

## Verification

Independently re-run by the `verifier` subagent: re-parsed the tape from scratch, confirmed
the count/provenance via `git blame`, re-derived the de-vig math, checked Rule #3 tagging,
and reviewed `collection/odds_api.py`'s status enum to confirm `matched` requires a clean
full-coverage pair (not a fallback/ambiguous state). Verdict: **CONFIRMED**.

## Registry / queue changes

- `kb/strategies/00-index.md`: S11 `idea` → `data-collecting`.
- `LOOP-QUEUE.md`: Q18 `IN-PROGRESS` → `DONE`.
