# Q21 idea-generation round — 2026-07-22 (kalshi-edge-hunter, nightly Opus)

**Outcome: 2 candidates proposed (S46, S47), BOTH killed at idea stage by independent
`verifier` attack → 0 registered.** Seventh consecutive zero-registration round. Both kills
are decisive and tape-backed (the verifier re-ran real joins, not hand-waving), and both trace
to the SAME two structural walls the entire strategy graveyard shares. Never pad to quota — the
honest output of a saturated surface is a well-attacked zero.

New this round vs. the six prior zero rounds: tonight's Observatory pilot (`PR #155`, merged
04:16Z) is now live as a bottom-up candidate feeder, so this round was grounded in its first
pass (`reports/observatory/run-2026-07-22.md`) rather than the unchanged top-down tape survey.
**The Observatory's own first pass also produced 0 candidates** (23 persistent cross-sectional
outliers, all in `queue-crowding` / `liquidity-structure` / graveyard-blocked
`naive-maker-spread`). Two independent "short of things to test" signals now agree.

---

## S46 — Touch-queue temporal-growth asymmetry as a settlement predictor (DEAD)

- **Mechanism proposed:** in `tape/orderbook_depth/`, compute the CHANGE in size-at-touch
  between consecutive hourly captures per side; when one side's touch-queue grows materially
  while the mid stays fixed, treat it as informed accumulation not yet repriced, and bet the
  growth side predicts settlement better than the contemporaneous mid.
- **Claimed distinction from its dead cousin S22** (OFI/depth-imbalance, dead 2026-07-14): S22
  used the *static level* of depth imbalance, already integrated into the displayed mid. S46
  proposed the *time-derivative* (queue growth with the mid held fixed) as a feature S22 never
  tested.
- **Verifier verdict: DEAD — collapses into S22.** Read 15 `orderbook_depth` files (301,561
  records, 2,765 sports `GAME-` tickers, 192,816 consecutive capture-pairs;
  `price_source_tags={asks:real_ask, bids:real_bid}`, not synthetic) joined to
  `tape/q26_settlement_cache/settlement.json` (the L50 ex-post window, 450 yes/no markets).
  - The signal IS computable (not the L32/S6 total-freeze problem): the exact S46 signal
    (mid fixed + asymmetric touch-queue growth >20%) fires in 8.7% = 16,839 pairs.
  - But on the **197-game** settlement join, the growth-side hit-rate on the disagreement
    subset is **0.15–0.20 vs the mid's 0.80–0.85** across four charitable constructions, with
    exact arithmetic complementarity (`growth_hit ≡ NOT mid_hit`) — the identical trap that
    killed S22. Tightening to strong (>50%) growth makes it *worse* (0.154), a spoof/noise
    signature, not stronger signal. The mid already integrates the depth ladder's derivative,
    not just its level.
  - Fill side independently dead: the only trade is a taker cross at 3.0¢ median / 13.3¢ mean
    spread (S24 round-trip death) or a maker post into S19/S21 fill deaths. No edge to pay
    either cost.

## S47 — Observatory-selected adequately-two-sided series → selective maker (DEAD)

- **Mechanism proposed:** the Observatory flags persistently ONE-SIDED series; the tradeable
  inverse is persistently WELL two-sided series with spread > 2× the maker fee — the S11
  "selective maker" lane, a book where a resting order can actually fill and the half-spread
  can exceed the flat 1¢ maker fee.
- **Claimed distinction from S6/S13/S19/S21/S23:** use the Observatory's cross-sectional screen
  to pre-select the adequately-two-sided, wide-enough population up front rather than quoting
  everything (S6) or a pre-chosen tail (S19/S21/S23).
- **Verifier verdict: DEAD — two binding reasons.** Read `analysis/observatory/features.py`
  (289 lines), `core/pricing.py` (`MAKER_FEE_RATE=0.0175`), all 15 Observatory day-aggregates,
  and 15 `orderbook_depth` files (301,561 lines / 10,427 two-sided touch snapshots).
  - **(A) The fee-positive spread region is exactly where the book is token-thin** (L30 + L31 =
    S6/S13 restated). Where the book is genuinely deep and two-sided (spread ≤2¢, median touch
    queue ~540 contracts), the capturable half-spread (≤1¢) ≤ the flat 1¢ maker fee. Where the
    spread clears the fee (≥3¢, up to ≥10¢), the touch queue collapses to ~10 contracts — a
    nominal L31 wing, not a capturable two-sided spread. The intersection S47 needs (deep AND
    fee-clearing) is empty.
  - **(B) The fill is not measurable.** `orderbook_depth` has no `volume`/`trade`/`last_price`
    field — only ~hourly book snapshots. A "queue-aware fill-sim" over it would synthesize
    fills from an assumption = a `synthetic` number used as a fill price, the pt1 −9.6% failure
    mode, forbidden by the prime directive and already fatal to S6/S21.
  - **Notable correction to the framing:** median `two_sided_share` across 423 series-days is
    **1.0** (89.8% ≥0.5) — the books are mostly two-sided; the one-sided KXBTC/KXETH outliers
    are the minority. But `two_sided_share` is size-blind (a 1-contract quote each side counts
    "two-sided"), so it is anti-correlated with capturable maker edge, not a proxy for it.

---

## The two walls (why this round, and the whole graveyard, dies)

1. **Fill wall.** Hourly `orderbook_depth` snapshots carry no trade-print tape, so no maker
   fill is *observable*. Every maker candidate (S6/S13/S19/S21/S23/S47) either fills at a rate
   we cannot measure or would require inventing the fill. Proving a maker edge needs either
   trade-level / sub-hourly capture, or live shadow-paper fills — not more hourly snapshots.
2. **Mid-efficiency wall.** The displayed mid already prices the depth ladder's level (S22) AND
   its time-derivative (S46), so no depth-derived directional signal beats the mid on the
   disagreement subset. And taker directional into the wide overround dies on round-trip cost
   (S1/S5/S7/S24/S34).

**The binding constraint is the data surface, not idea capacity.** The current tape
(hourly-cadence book snapshots, no trade prints, a ~95%-dead-tail longshot-skewed universe)
structurally cannot prove a fillable edge for the maker, taker, or depth-signal families. New
proof likely requires a different data input — trade-print / sub-hourly burst tape (the Q19
lane), or the credential-gated cross-venue / CME legs (S2/Q32/Q33) — a decision for Ryan, not
a cloud run.

## Lessons filed
- **L130** — a temporal-derivative reformulation of a feature already integrated into the mid
  does NOT escape the disagreement-subset complementarity trap; gate any "it's the derivative,
  not the level" proposal on the disagreement-subset hit-rate (must beat 0.5) before build.
- **L131** — `two_sided_share` (size-blind) is anti-correlated with capturable maker edge on
  this tape; a maker screen must gate on touch SIZE at the fee-clearing spread, and cannot
  claim a fill without a trade-print tape.

Consumed S46/S47 → **next free = S48.** Still **0 proven edges.**
