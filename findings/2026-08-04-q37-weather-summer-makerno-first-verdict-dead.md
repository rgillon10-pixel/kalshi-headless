# Q37 — Weather summer maker-NO fade — first live verdict: DEAD (verifier-CONFIRMED)

**Date:** 2026-08-04 (research loop). **Verdict:** DEAD. **Two-agent rule:** producer (this run) +
independent `verifier` agent, CONFIRMED. **Registry:** no strategy graduates; S1/S5 stay `dead ✗`.

## Background

Q37 (`LOOP-QUEUE.md`, added 2026-07-15) asked whether the one untested cell of the weather matrix —
**summer regime × MAKER execution (fee 0.0175 vs taker 0.07) × EMOS-calibrated entry signal** — could
revive S1's longshot-fade thesis after every prior weather angle (S1, S5, pt1) died to the ~9.8¢
taker-side overround. The probe (`scripts/q37_weather_summer_makerno_probe.py`, built 2026-07-20) was
gated on ≥21 summer contract-days of `tape/weather_books/` coverage and has printed `INSUFFICIENT
DATA` on every run since. The gate opened today at exactly 21/21 (`scripts/q37_bootstrap_unit_preflight.py`
independently confirmed 15 usable bootstrap units, clearing the L41 admissibility floor of 10) — this
is the probe's **first-ever live execution**.

## The trade

Per `(series, contract-day)` daily temperature ladder, at strictly-causal decision time
`T = close_time − 24h`: on every LONGSHOT bracket (implied prob < 0.20, via `bracket_sum`-normalized
`real_ask`), rest a MAKER NO at the best real `no_bid`, hold to settlement. Fill is a real book-touch
(`OPTIMISTIC_FILL = True` — no trade tape exists to prove queue clearance, so this can never graduate
to a live verdict regardless of sign; see Stop rules). Net edge = payout − entry_no_price − maker fee.

## Result (live, `tape/weather_books/` committed tape, `real_bid` entry / `broker_truth` settlement)

```
summer contract-days: 21/21 (2026-07-15 .. 2026-08-04, gate open)
groups=840  longshot trades=2914  skips={incomplete_book: 101}  EMOS available=False

PRIMARY (fillable-entry, S1 no-signal), movement-conditioned cut:
    mean = −$0.05670   95% CI = [−$0.09598, −$0.03023]
    n_units (contract-days) = 15   n_obs (filled trades) = 531
    admissible=True   clears_tick_magnitude=False (CI does not need it — already DEAD)

fill rate: 25.49% (both optimistic and movement-conditioned — L32 degenerate, touched∧frozen=0)
GATE-DAY vs BOOTSTRAP-UNIT: 21 gate days -> 15 units (deficit 6: incomplete_book 1, zero_fill 1,
  settlement_lag 4) — clears MIN_CI_UNITS=10 floor
```

**VERDICT: DEAD** — the primary movement-conditioned CI is strictly negative, not merely
non-positive. This is the expected weather death (execution economics), now measured for the
summer/maker cell specifically.

## Verifier confirmation (independent re-run, `verifier` agent, 2026-08-04)

Re-ran the probe on a clean tree at the same commit — every number reproduced exactly (mean, CI
bounds to 5 decimals, n_units, n_obs, gate/deficit breakdown, degeneracy counts). Checked and PASSED:
price provenance (`real_bid` entry via the collector's raw book side, never a midpoint; `broker_truth`
settlement), fee sourcing (`core.pricing.MAKER_FEE_RATE`, single-leg, never hand-rolled), bootstrap
unit (calendar contract-day, `core.bootstrap.block_bootstrap`), both admissibility gates
(`bootstrap_verdict_admissible`, `clears_tick_magnitude`) read from `core/bootstrap.py`, and the L32
dual-cut degeneracy claim (`touched ∧ frozen = 0` verified structurally: `no_ask − no_bid = yes_spread
≥ 0` by collector construction, and empirically 0 crossed books in 41,441 two-sided snapshots).

**Is the DEAD an artifact?** No — it decomposes to an exact identity, not a residue. Mean entry price
0.89981, mean fee 0.01000 → break-even hit rate = 1 − p − fee = 9.02%. Realized hit rate on the 531
FILLED trades = 14.69%. `0.09019 − 0.14689 = −0.05670`, matching the reported mean to 5 decimals. The
mechanism is textbook adverse selection: getting filled requires the market to move *toward* the
longshot (no_ask falling to our resting no_bid), which is exactly the condition correlated with the
longshot actually happening. Unfilled measurable trades hit at 0.88%; filled trades hit at 14.69%.

**Robustness checks run by the verifier, all held sign:**
- Zero-fee counterfactual: mean −$0.0467, CI [−$0.08598, −$0.02023] — fee is not what kills it.
- Leave-one-day-out (15 folds): CI upper bound stays negative in all 15 (worst fold hi = −0.02603).
- L86 stress (credit every unmeasurable dropped row as a win): mean −$0.0306 — sign preserved.
- L249 sign-boundedness check: `one_sided_support=False`, `verdict_bearing=True` (453 positive units /
  78 negative) — admissibility here is genuine, not a gate artifact (unlike Q49/S68).
- L251 entry-instant concentration: 33 distinct entry instants, max share 7.7% — not a tape-start
  artifact.
- Settlement integrity: all 664 settled events carry exactly 6 bracket results with exactly one
  `yes` — no partial-settlement bias.
- Full-book-coverage stratum (touch window within 2h of close, n_units=11/n_obs=307): mean −$0.05029,
  CI [−$0.10874, −$0.00934] — still strictly negative under a tighter coverage requirement.

## Two non-blocking findings worth recording

1. **The maker-fee premise Q37 was built to test is largely void at longshot prices, independent of
   this verdict's sign.** Kalshi's fee floor is `ceil(rate·p·(1−p)·100)/100` — a whole-cent round-up.
   At the ~$0.90 no-price these longshot NO trades transact at, **both the maker (0.0175) and taker
   (0.07) rate round up to the same $0.01** on 443/531 (83.4%) of filled trades. Mean fee: maker
   $0.01000 vs taker $0.01166 — the entire maker/taker distinction is worth ~0.17¢ against a 5.67¢
   loss. Filed as lesson **L277**: pre-screen any "maker re-test" of an existing longshot-priced
   strategy with a direct `fee_per_contract(p, MAKER) vs fee_per_contract(p, TAKER)` comparison before
   queueing it — at extreme prices (p ≳ 0.86 or ≲ 0.14) it is not a fee experiment at all.
2. **The L69 near-close OR-branch (`ttc ≤ 24h`) is dead code at this probe's `DECISION_LEAD_HOURS=24`**
   — `ttc ≥ 24.01h` always holds by construction (0/2914 rows qualify via that branch), so the primary
   population is the spread-test branch alone. Does not affect the verdict (the branch can only add
   rows and added none); noted so a future reader doesn't assume both L69 conditions are live here.
   The 21 gate days also all fall in 2026-07-15..08-04 (three weeks of mid-summer), not the full
   `SUMMER_START..SUMMER_END` astronomical window — this is a mid-July/early-August verdict, not a
   94-day-season one.

## Consequence

Q37's Status line in `LOOP-QUEUE.md` flips to `DONE — DEAD, verifier-CONFIRMED`. `kb/strategies/00-index.md`
S1's row gets an addendum noting the summer/maker re-test result. No registry graduation — `OPTIMISTIC_FILL`
would have blocked one regardless of sign. **S1/S5/S7/S8/S9/S10/S13/S16 (implicitly)/weather-family are
now decided at real asks across EVERY tested regime × execution-side combination this project has run.**
Still **0 proven edges**.

## Reproduce

```
python scripts/q37_weather_summer_makerno_probe.py
python scripts/q37_bootstrap_unit_preflight.py
```

Both read `tape/weather_books/` only (committed, no network). Prices: `real_bid` (entry, resting NO
bid) / `real_ask` (touch detection) / `broker_truth` (settlement). No synthetic price in the P&L path.
