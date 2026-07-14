# Q27 / S23 — Favorite-side settlement-underpricing maker verdict: DEAD by fee

`2026-07-14` · LOOP-QUEUE.md Q27 · registry S23 · verifier CONFIRMED (independent from-scratch
re-run, every number reproduced, fill-model robustness swept) · two-agent rule satisfied ·
every price below carries its source tag

## The question

The favorite-longshot bias (`kb/quant-finance/favorite-longshot-bias.md`) says bettors overbet
longshots and underbet favorites, leaving favorites cheap. S23 asks the direct fillable-maker
version on Kalshi: rest a maker BID to buy the favorite YES (entry-time normalized
`yes_ask` over `bracket_sum` ≥ 0.65, Hard Rule #3 via `core.pricing`) in Q25's high-turnover
two-sided sports cells, and collect $1 on settlement when the favorite wins. If the bias is real
and fillable, favorite win-rate among fills should exceed the fill price plus the maker fee.

**The design choice that makes S23 testable where S21 died.** S21 (the maker rich-ASK longshot
sell) needed `tape/sports_clv/` fair anchors joined to `tape/orderbook_depth/`, and those two
collectors ran over disjoint game windows → 0/81 joinable, DEAD by data-adequacy (L43). S23's
fair test is **REALIZED Kalshi settlement**, not a devig anchor — no `sports_clv` tape, no
odds-api key. The settlement leg is pulled ex-post from Kalshi's free settled-markets endpoint
over the depth tape's OWN window (within the ~60-day L11 retention), so the join is non-empty by
construction (L50 — the general fix for the S21-class disjoint-join death).

Data: `tape/orderbook_depth/` for the `yes_bids` resting queue + Kalshi's free settled-markets
endpoint (`collection/sports_history.py::fetch_kalshi_settled`), pulled once and cached at
`tape/q27_settlement_cache/settlement.json` (462 settled markets, `broker_truth`, live pull
2026-07-14T12:27Z) across the Q25 high-turnover two-sided cells (KXKBOGAME, KXNPBGAME,
KXWNBAGAME, KXMLBGAME, KXUCLGAME, KXUECLGAME, KXUELGAME).

## Verdict: DEAD by fee (verifier-CONFIRMED)

Both the producing edge-prober and an independent verifier reproduced every number below. The
verifier's verdict: CONFIRMED — safe to flip the S23 registry to DEAD.

### The four binding gates and how each resolved

**G4 (settlement-join adequacy) PASSES.** 462 settled markets cached; 454 binary; 8 dropped as
`result="scalar"` (L52 — a binary probe must filter `result ∈ {yes,no}` explicitly, never assume
settled ⇒ binary). 207 distinct games carry a genuine pre-close depth snapshot. Well clear of the
10-game floor.

**G3 (fill rate) does NOT kill.** Fill = a queue-aware `yes_bids` fill-sim (L39, NOT a candlestick
print), frozen-queue = no-fill (L32/L48). The favorite funnel: 25 favorite markets → 1 with no
restable bid → **24 rested favorite bids across 24 DISTINCT games** (verifier confirmed 24 distinct
`event_ticker`s, no double-counting). Fill rate **95.83% (23/24)** — far above the S19 0.45% dead
floor. The resting windows are long (median ~37 hourly pre-close snapshots per game), so a
cumulative-departures model clears almost any queue: a high fill rate here is a property of the
long window, NOT evidence of an edge (L53). The strategy therefore must live or die on the EDGE,
not on fill adequacy.

**G2 (adverse-selection leg included) HOLDS.** The 7 favorite-LOSES fills (each ~−$0.73,
settlement `broker_truth`) are FULLY in the P&L and the bootstrap, never conditioned away (L41).
The verifier confirmed that dropping them is the ONLY way to make the edge positive — and that is
forbidden.

**G1 (factor slot) recorded.** S23 sits in the SAME factor slot as S14/S21 —
short-the-overpriced-tail / favorite-longshot — one Hard-Rule-#6 ρ allocation, NOT diversification.

### The edge — why it dies

Favorite win-rate among fills **0.6957 (16 wins / 7 losses)** < mean fill_price **$0.7261**
(source_tag `real_bid`) + **$0.01** flat maker fee (`core.pricing` MAKER_FEE_RATE, L18/L30) =
breakeven win-rate **0.7361**. Favorites are marginally RICH at the bid — the OPPOSITE of what the
favorite-longshot bias predicts as a fillable maker edge. This is a DEAD-by-fee outcome
(L30 / the S13 fee-floor family): the flat 1¢ maker fee plus the fill price already exceeds the
realized win-rate.

### The bootstrap

Block-bootstrap net P&L BY GAME (L6; 10,000 resamples): mean **−$0.0404/contract**, 95% CI
**[−$0.2435, +$0.1370]**, n_units = 23 games (the 1 no-fill game has no P&L observation).
`bootstrap_verdict_admissible` PASSED (23 units ≥ 10, 16 opposing-sign clusters — L41).
`clears_tick_magnitude` FAILED (lower bound −0.2435 far below the +0.01 tick). The CI fails BOTH
positivity and the L27 magnitude gate.

### Fill-model robustness

Even the maximally-generous "all 24 filled" assumption gives CI **[−0.218, +0.143]**, still
failing the tick gate. DEAD is robust under both the scarce-fill and the abundant-fill assumption.

### Source tags

Fill price `real_bid`; settlement `broker_truth`; normalized fair derived from `real_ask`. No
synthetic number is quoted as a fill.

## Registry

S23 flips `idea → dead ✗` in `kb/strategies/00-index.md`. Still **0 proven edges** — the bar has
not moved. This is a testable instance of the undecided S13/S21 branch now DECIDED: the
favorite-longshot bias does not manifest as a fillable maker-bid edge on Kalshi two-sided sports;
combined with S13 (bid vs devig, null) and S21 (ask vs fair anchor, data-adequacy dead), the whole
favorite-longshot / S7-family maker lens is closed DEAD on Kalshi sports at real fills.

## Lesson candidates

- **L53** — a queue-aware fill-sim's fill-rate KILL gate (S19 0.45% floor, G3) does NOT bind over
  a long resting window: a cumulative-departures model clears almost any queue across ~37 hourly
  snapshots (S23 fill rate 95.83%), so a high fill rate is NOT evidence of an edge — the strategy
  must still die or live on the EDGE (win-rate vs fill_price+fee). Complements L39/L48.
- **L54** — favorite-longshot bias does NOT manifest as a fillable maker-BID edge on Kalshi
  two-sided sports (win-rate 0.6957 < breakeven 0.7361, favorites marginally RICH at the bid); with
  S13/S21 this closes the favorite-longshot / S7-family maker lens DEAD at real fills.
- **L55** — an entry-time favorite filter with NO settlement lookahead is thin by construction
  (24 rested markets from 207 joinable games); a thin-but-honest population that still clears the
  ≥10-game floor is the correct anti-lookahead trade.
- **L56** — L37 (Hard-Rule-#3 scanner false-positives on prose writing "yes_ask/bracket_sum" with
  a slash) RECURRED in this script (lines 6/78/171), again fixed by rewording the separator to
  "over"/"and". Prose convention, not a code bug.

## Gates

`pytest -q`: 841 passed (817 prior + 24 new in `tests/test_q27_favorite_underpricing_fillsim.py`).
`python scripts/invariants.py --full`: green (only the standing non-gating L20 stranded-tape +
L29 tape-dir-shape advisories). No execution code outside the sanctioned paper tier; no network
calls beyond the one documented, cached, re-runnable settlement pull; no credentials.

## Files

- `scripts/q27_favorite_underpricing_fillsim.py` — the probe (read-only, 24 offline tests,
  queue-aware `yes_bids` fill-sim, offline-first against the cache).
- `tests/test_q27_favorite_underpricing_fillsim.py` — 24 offline unit tests.
- `tape/q27_settlement_cache/settlement.json` — cached settlement snapshot (`broker_truth`,
  re-runnable offline by any future verifier without a fresh network call).
