# Q49 / S68 — two-sided both-bid overround-capture maker: verdict DEAD-by-fee

**2026-08-01, research loop.** Verdict: **DEAD** (headline label `DEAD-by-fee`), verifier-**CONFIRMED**
after an independent full re-derivation, adversarial entry-rule sweep, and a fee-identity proof. Still
**0 proven edges**.

## Mechanism tested

On 2-outcome game moneyline books whose two-sided spread is ≥ the sum of the two flat maker fees, rest
BOTH a YES bid and a NO bid; if both fill you own both sides for `yes_bid + no_bid` < $1 and exactly one
side pays $1 at settlement — a deterministic gross capture equal to the entry yes-spread. The idea-stage
registration (`findings/2026-08-01-q21-idea-gen-round.md`) measured this gross overround (mean 7.31¢
over 205 wide-spread tickers / 16 series) and flagged the whole open question as the fill model /
adverse-selection question — the same L5 wall that killed S6/S13/S14/S23.

## What was built

`scripts/q49_s68_bothside_maker_fillsim.py` (+ `tests/test_q49_s68_bothside_maker_fillsim.py`, 53
offline unit tests) — a queue-aware BOTH-sides-fill maker sim over `tape/orderbook_depth/`
`yes_bids`/`no_bids` price-time-priority ladders (L39-free, no candle/volume proxy), joined ex-post to
`tape/settlement_ledger/` (`broker_truth`). Two independent fill models are reported: `touch` (departures
at our own price level, only while at the touch — the primary, price-priority-correct rule) and
`turnover` (the generous Q27/S19 departures-at-any-level rule, reported as a labeled diagnostic; it
**saturates** on this multi-day-hold population — 98% "fill rate" — because book migration away from a
stale price counts as queue advancement under that rule, which is why `touch` is primary). Fees are
`core.pricing.fee_per_contract` at `MAKER_FEE_RATE` (never hand-rolled). Block-bootstrap groups by
GAME-SERIES (ticker prefix, e.g. `KXKBOGAME`), per the Q49 spec's L6/L41 discipline.

## Headline result (fill_model=`touch`, cut=`fillable_entry`: entry spread ≤ 10c AND ttc ≤ 24h)

- 20 rested both-bid candidates, 5 game-series, 14 games.
- Fills: both=11, yes_only=6, no_only=3, neither=0 → both-fill rate 55.0% (≫ S19's 0.45% floor).
- P&L symmetry proven in code (not assumed): `max|pnl(settles YES) − pnl(settles NO)| = 0.0` over every
  candidate.
- Realized double-fill overround, net of BOTH maker fees: mean **exactly $0.0000** on 11/11 observations
  (every one sub-tick — 0/11 clears the $0.01 tick). Block-bootstrap by game-series: mean $0.0000, 95% CI
  `[$0.0000, $0.0000]`, n_units=5 (below the 10-series adequacy floor), L41-inadmissible
  (`below_min_units`, `no_opposing_unit`).
- Strategy-level diagnostic (every rested pair — double fill = capture, single-side fill = the
  directional position left holding, neither = 0): mean +0.0095, 95% CI `[−0.2422, +0.0853]` — straddles
  zero.
- Every other population/fill-model combination reported by the script (spread≤10c, nearclose≤24h,
  unrestricted; both fill models) also dies — DEAD-by-CI (L41-inadmissible) or DEAD-by-adequacy. None
  clears both admissibility and the tick-magnitude gate.

## The structural finding (why this is a fee wall, not a data-adequacy gap)

On a binary book, `best_yes_ask = round(1 − best_no_bid, 4)` by construction
(`collection/normalize.py:35` — Kalshi posts only bids per outcome). This makes the entry yes-spread
**identically equal to** the both-bid gross capture (`1 − yes_bid − no_bid`), not merely correlated with
it. So the entry gate "spread ≥ two fees" **guarantees by construction** that every double-fill's gross
capture is ≥ the two fees — net P&L can never be negative under this design, and at the realistic
near-close population the gate mostly admits books sitting almost exactly on that boundary, so net rounds
to zero. This also means the L41-inadmissible verdict on the wider cuts (spread≤10c, unrestricted) carries
**no evidentiary weight about the strategy** — a gate that arithmetically guarantees non-negative P&L can
never produce an opposing-sign bootstrap cluster, so "DEAD-by-CI (L41)" there is a definitional artifact
of the gate, not new information. The two non-degenerate objects that actually kill this candidate are (1)
the per-observation sub-tick magnitude decomposition (11/11 sub-tick at the primary cut) and (2) the
strategy-level bootstrap, which is genuinely admissible and straddles/goes negative.

## Verifier's independent contribution

The `verifier` agent re-ran everything from a fresh shell (pytest, invariants, the probe script twice
with a JSON diff — byte-identical modulo timestamp, confirming full determinism), brute-force-checked all
445 wide-spread candidates for the fee identity (0 violations, `min net = $0.0000` exactly, 0 candidates
net-negative), and confirmed 0 of 53 series prefixes in the depth tape start with `KXMVE` (the S68
exclusion binds vacuously on this tape — moot, not violated).

It then built and ran an **independent alternative entry rule** — "first snapshot with ttc ≤ H" (a
genuine at-T-minus-H rule, not earliest-then-filter) — at four horizons (24h/10c-spread, 24h, 6h, 2h) and
re-ran the full sim. Every one is DEAD: three straddle zero on the (admissible) strategy-level CI, and the
6-hour cut goes **negative** (mean −$0.0562, CI `[−$0.1459, +$0.0046]`). This is materially stronger
evidence than the producer's single-cut result, because it rules out the specific entry-timing choice as
the source of the null.

**Verdict: CONFIRMED.**

## Two disclosure caveats the verifier raised (neither changes the verdict)

1. **The primary `fillable_entry` population is a tape-start artifact, not a temporally-spread
   near-close sample.** All 20 candidates share ONE `entry_captured_at`
   (`2026-07-07T01:23:57.700581Z` — the depth tape's first-ever capture pass, which happens to fall
   within 24h of several games' close). "5 game-series, 14 games" implies more breadth than a single
   capture instant carries. The verifier's alternative "first snapshot with ttc≤24h" population (176
   candidates / 17 series / 131 games, spanning the full tape) is the more defensible near-close test,
   and it is also DEAD (strategy-level CI `[−0.0242, +0.0623]`, straddles zero).
2. **The "gross capture is measured, not assumed equal to the spread" framing in the script's docstring
   and one unit test overstates what was checked** — given the collector's `best_yes_ask = 1 −
   best_no_bid` identity, the two quantities are definitionally equal on any real snapshot; the test's
   synthetic counterexample input is unproducible by the collector. This does not weaken the verdict (it
   makes `net ≥ 0` exact rather than approximate) but the prose should say "identical by construction,"
   not "measured."

## Binding gates checked

`real_bid` for all fill prices and queue depth; `broker_truth` for settlement. Block-bootstrap by
GAME-SERIES (L6/L41). `clears_tick_magnitude` (L27) applied. Fee source `core.pricing.fee_per_contract`
at `MAKER_FEE_RATE` (L18/L30) only. `scripts/invariants.py::no_yes_ask_arithmetic` initially flagged a
false positive on a comment string in the test file (fixed by rewording, not by weakening the check) —
`invariants: all green` after the fix.

## Gates (fresh, post-fix)

`python3 -m pytest -q` → 2547 collected, 2547 passed, 0 failed (producer and verifier, independently, both
runs). `python3 scripts/invariants.py --full` → all green (14 pre-existing non-gating advisories).

## Lesson candidates (for kb-distiller)

1. A verdict ladder whose ALIVE branch is structurally unreachable (because the entry gate arithmetically
   guarantees the sign of the object being bootstrapped) is not a real test — a probe of this shape must
   report its kill on a non-degenerate object (per-observation magnitude decomposition, or a
   strategy-level P&L that includes the unhedged single-side legs), never quote the gate-guaranteed
   L41-inadmissible cuts as evidence.
2. The Q27/S19 "turnover" fill proxy saturates on multi-day-hold populations (98% fill rate here, vs 42%
   under the price-priority-correct `touch` rule) because book migration away from a stale resting price
   counts as queue advancement under that rule. L48's "a turnover proxy rules a population OUT, never IN"
   needs the explicit corollary: a HIGH fill rate under the turnover proxy is not itself a fill result.
3. L69 sibling: an "earliest pre-close snapshot, then filter ttc≤H" primary cut silently selects on tape
   start date for any tape family still young — for a freshly-started collector this can degenerate to a
   single capture instant. The honest near-close rule is "first snapshot with ttc≤H" (a genuine
   at-T-minus-H entry), not "earliest capture, then filtered."
4. A wide-spread gate defined as "spread ≥ sum of the round-trip fees" selects, at its tightest/most
   realistic population, books sitting almost exactly on the zero-profit boundary — any "collect the
   spread" design needs the gate set at fees-plus-a-target-tick, with the resulting population re-run, or
   it structurally captures the fee wall rather than an edge.

## Price source tags

fills: `real_bid`; queue depth: `real_bid`; settlement: `broker_truth`.

See `scripts/q49_s68_bothside_maker_fillsim.py`, `tests/test_q49_s68_bothside_maker_fillsim.py`,
`kb/strategies/00-index.md` S68 row, `findings/2026-08-01-q21-idea-gen-round.md` (idea-stage
registration).
