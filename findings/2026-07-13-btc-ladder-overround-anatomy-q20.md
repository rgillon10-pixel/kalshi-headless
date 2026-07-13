# BTC/ETH fine-ladder overround anatomy (Q20) — where the +$X overround lives

`2026-07-13` · LOOP-QUEUE.md **Q20** (feeds S14's crypto leg) · script
`scripts/s20_ladder_overround_anatomy.py` · tests `tests/test_s20_ladder_overround_anatomy.py`
(22, offline/synthetic) · **read-only, no network, no orders** · **NOT a P&L verdict, NOT a
registry flip** (Q20: "No registry flip without the two-agent rule") · **verifier:
CONFIRMED-WITH-CAVEAT** (all numbers reproduced exactly independently; one causal wording on the
ETH mid-sum tell corrected per verifier decomposition — see §3 and the lesson candidates)

## Question

Q2 (2026-07-03) flagged a 188-member KXBTC hourly ladder whose `bracket_sum` overround was
**+$9.27** at `real_ask` prices (Σ of all members' `yes_ask`, minus $1.00) and never
investigated it. Leading hypothesis (S10 DEAD, lesson L12): the fat apparent overround is an
**artifact of the ~180 far strikes pinned at Kalshi's 1¢ minimum ask** — a floor, not
maker-capturable premium. This decomposes the overround by strike distance from spot, joins L2
depth to test the "wings are quote-only" claim, and emits the S14-crypto parameter block.

Method (all in `scripts/s20_ladder_overround_anatomy.py`):
- **Buckets** per member: `active` (within ±3 strike-spacings of spot) vs `wing_floor`
  (`yes_ask ≤ 1¢`) vs `wing_elevated` (ask above the floor but outside the band). Spacing is
  read off the ladder's own `between` floor strikes (`core.pricing.infer_strike_spacing`, L7 —
  never a hardcoded width; BTC infers $100, ETH $20).
- **Spot** = the top-level `spot.price` leg, tag **`synthetic`** (Coinbase). Used ONLY as a
  binning coordinate, never as a fill price; its `exchange_time` is <1 s from `captured_at`, so
  no L8 lag confound in the binning.
- **Depth join** (`tape/orderbook_depth/`): a Kalshi YES offer at price `p` is the mirror of a
  NO bid at `1−p` (`best_no_bid == 1 − best_yes_ask`), so the size resting AT a member's
  `yes_ask` is the **top of its `no_bids` ladder** (tag `real_bid`). Matched by ticker +
  nearest `captured_at` (the depth sub-pass runs ~20 s after the crypto sub-pass with a
  *different* `capture_id`). Depth tape starts 2026-07-07 vs crypto 2026-07-03, so the join
  covers only the overlapping window (L9): 328/629 snapshots are join-eligible → ~47% member
  match rate, drawn from that window.
- **Fees**: `core.pricing.fee_per_contract` at `MAKER_FEE_RATE` (L5/L18/L30 — flat $0.01 at
  every interior price). **Bootstrap by EVENT-HOUR** (L6) via `core.bootstrap.block_bootstrap`,
  10,000 resamples, + the L27 magnitude gate.

Corpus: **629 snapshots** (KXBTC 316 / KXETH 313), 172 settled event-hours each, 07-03→07-13.

## 1. The overround is 84–97% WINGS, not the active band

Mean Σ`yes_ask` per bucket (all `real_ask`), per snapshot:

| series | mean bracket_sum | overround | active (≈6 mem) | wing_floor (1¢) | wing_elevated | **% of overround in wings** |
|---|---|---|---|---|---|---|
| **KXBTC** | 4.950 | **+3.950** | 1.069 (6 mem) | 1.710 (171 mem) | 2.170 (11 mem) | **97.4%** |
| **KXETH** | 2.051 | **+1.051** | 1.185 (6 mem) | 0.677 (67.7 mem) | 0.189 (1.3 mem) | **84.3%** |

The active band (±3 brackets) sums to ~$1.0–1.2 — i.e. a **coherent near-money book carrying
~all the probability mass and essentially none of the excess**. The fat overround is split
between (a) ~170 BTC / ~68 ETH members mechanically pinned at the 1¢ floor, and (b) a handful
of **`wing_elevated`** members — stale one-sided asks (0.20–0.67 with `yes_bid = 0`) far from
money, the L31 "wide spread on a one-sided far bracket is nominal, not capturable" artifact in
the **ask** direction. On BTC the elevated wings ($2.17) actually exceed the floor wings ($1.71):
the +$9.27-class overround is as much stale-quote inflation as it is floor-pinning.

## 2. Depth join REFUTES "wings are quote-only (depth ≈ 0)"

Ask-side resting size (contracts) = top of the mirror `no_bids` ladder, `real_bid`:

| series | active median | wing_floor median | wing_elevated median | frac with depth>0 |
|---|---|---|---|---|
| **KXBTC** | 401 | **22,768** | 166 | 97–98% |
| **KXETH** | 160 | **36,253** | 503 | 92–98% |

The 1¢-floor wings are **not** empty quotes — they rest **tens of thousands of contracts** at
the floor (e.g. one KXBTC wing 11 brackets OTM: a 46,967-contract NO-bid-at-0.99 = a
46,967-contract offer to sell YES at 1¢). So the naive "quote-only / no size" framing is
**refuted**: the wings are deeply *fillable in size*. The reason they carry no capturable edge
is **not** absence of liquidity — it is L30/L12: a 1¢ ask nets `0.01 − fee($0.01) = $0.00`
after the flat maker fee, so a wall of floor size is worth exactly $0 to underwrite. Depth is
present and non-trivial in the active band too (median 160–401 contracts, 92–97% depth>0), so
the active-band figures below are not depth-starved.

## 3. S14-relevant number — active band `Σyes_ask − 1 − maker_fees`

Restricting to the active band, block-bootstrapped BY EVENT-HOUR (n=172 event-hours each):

| series | mean Σ(active asks) | mean Σ(active mids) | **Σasks − 1 − fees** (95% CI) | L27 magnitude gate |
|---|---|---|---|---|
| **KXBTC** | 1.069 | 0.970 | **+0.0087** [−0.0036, +0.0215] | **does NOT clear** |
| **KXETH** | 1.185 | 1.047 | **+0.1271** [+0.1046, +0.1523] | clears |

- **BTC**: the active-band balance **straddles zero and fails the magnitude gate** → no edge.
  The near-money book is coherent (Σmid 0.970 ≈ prob mass); the ~1¢ half-spread it carries is
  eaten by the flat 6×$0.01 maker fees.
- **ETH: the +0.127 CI is strictly positive but is NOT an edge and NOT a verdict** — it is the
  **nominal ask-width of a wide, thin 2-strike near-money book, not a fillable P&L.** Tell:
  the active-band **mids** sum to **1.047 > 1.0** (verifier decomposition: 0.976 restricted to
  two-sided members only — the >1.0 is driven mainly by one-sided (`yes_bid=0`) floor-adjacent
  members, where the `mid=(ask+bid)/2=ask/2` convention mechanically overstates a near-zero fair
  value, not primarily by the two wide ATM strikes' spreads, which alone sum below 1.0). It is a
  **heuristic tell that this synthetic-mid convention is contaminated by one-sided quotes here,
  not a coherence-theorem violation** — treat it as corroborating evidence, not proof. Collecting
  `Σasks` requires a **maker to be lifted at those elevated asks on every active member**, which
  is precisely the queue-position question **S14's fill-sim
  already showed the winner strike fills (you pay the $1) while the income legs only partially
  fill** — S14 first cut (2026-07-13) landed **PROXY-POSITIVE, not proven** (+$0.0925 CI
  [+0.063, +0.123], but 0.0% complete-fill and 78% of the edge from sub-100-volume legs the
  queue-blind proxy over-credits, L39). This Q20 number is the *nominal upper bound* on that
  same overround, one band closer to money; it is labeled **EXPLORATORY** and defers to S14's
  binding queue-aware gate.

Depth-weighting note (as Q20 requested): the active-band SIGN cannot be rescued/flipped by
depth-weighting — every active member rests fillable size (median 160–401 contracts), so the
undepth-weighted figures above are the honest ones. The binding constraint on realized capture
is **queue position and the fill↔winner correlation**, not available depth — and that is S14's
fill-sim, not an overround-anatomy question.

## Parameter block — future S14-crypto shadow (`execution/`, EXPLORATORY, unproven)

For Q22's paper harness, IF/when S14's queue-aware fill-sim clears its gate. Numbers below are
`real_ask` nominal caps, NOT proven capture.

```yaml
s14_crypto_shadow:
  universe: [KXBTC, KXETH]            # crypto_hourly MECE hourly bracket ladders
  band_width_steps: 3                 # active band = within ±3 strike-spacings of spot
  strike_spacing: infer_from_ladder   # core.pricing.infer_strike_spacing (L7); BTC≈$100 ETH≈$20
  spot_reference: crypto_hourly.spot.price   # tag=synthetic — binning ONLY, never a fill price
  side: maker_short_yes               # rest a short-YES offer at each active member's yes_ask
  quote_price: member.yes_ask         # real_ask; queue read off the MIRROR no_bids side (L2)
  fee: MAKER_FEE_RATE                 # flat $0.01/contract interior (L30) — 6×~$0.01 per band
  entry: earliest_capture_per_hour    # maximize horizon to close
  wings_excluded: true                # 1¢-floor + stale one-sided asks net $0 (L30) / non-fillable (L31)
  expected_overround_capture_per_event_hour:      # NOMINAL, unproven, per-event-hour
    KXBTC: {sum_asks_minus_1_minus_fees: +0.009, ci95: [-0.004, +0.021], verdict: no_edge_fails_magnitude_gate}
    KXETH: {sum_asks_minus_1_minus_fees: +0.127, ci95: [+0.105, +0.152], caveat: nominal_wide_book_requires_S14_fill_sim}
    half_spread_net_of_fee:           # ask-over-mid capturable premium, net of flat fee
      KXBTC: {mean: +0.039, ci95: [+0.033, +0.045]}
      KXETH: {mean: +0.080, ci95: [+0.062, +0.099]}
  binding_gate_before_live: queue_aware_L2_fill_sim  # S14's remaining gate; CI>0 @ real asks over ≥30 event-days
  kill_condition: realized_capture <= 0 after queue/adverse-selection modeling
```

## Verdict / reading

**ANATOMY, not a verdict.** The +$9.27-class overround is **97.4% (BTC) / 84.3% (ETH) wings** —
1¢-floor pins plus stale one-sided elevated asks — not active-band premium. The wings are
**deeply fillable in size** (median 22.8k / 36.3k contracts at the floor), so "quote-only" is
the wrong reason they're worthless; the right reason is the **flat 1¢ maker fee annihilating a
1¢ ask** (L30/L12). The active band carries the only non-floor overround: **BTC ~0 (CI straddles
zero, fails the L27 gate)**; **ETH +0.127 nominal but incoherent (mids sum >1) and fill-dependent
— EXPLORATORY, deferred to S14's queue-aware fill-sim** (already PROXY-POSITIVE-not-proven).
No registry status changed (Q20 two-agent rule).

## Provenance / tags

- asks: `real_ask` (crypto_hourly `current.outcomes[].yes_ask`); settlement not used here.
- depth: `real_bid` (mirror `no_bids` top; `tape/orderbook_depth/`).
- spot binning coordinate: `synthetic` (Coinbase `spot.price`) — never a fill price.
- gates at write time: `pytest -q` **664 passed** (was 642; +22 offline S20 tests);
  `python scripts/invariants.py --full` **all green** (non-gating L20/L29 advisories only).

## Lesson candidates (for kb-distiller)

- **The fine-ladder overround has TWO artifact components, not one.** L12 named the 1¢-floor
  pins; on BTC the **stale one-sided `wing_elevated` asks** (0.20–0.67 with `yes_bid=0`, far
  from money) actually contribute *more* overround than the floor pins ($2.17 vs $1.71). Any
  "capturable overround" claim must exclude BOTH — the elevated wings are the L31 wide-one-sided
  artifact in the ask direction (L31 was framed for the bid-ask spread; it applies verbatim to
  the ask-sum overround).
- **"Wings are quote-only (depth≈0)" is the WRONG mental model — and stating it wrong hides the
  real reason.** The 1¢-floor wings rest *tens of thousands* of contracts (mirror `no_bids` at
  0.99). They're worthless to underwrite because of the **flat 1¢ maker fee** (L30), not absence
  of size. A depth check that expected ~0 and found 22.8k would be a confusing false alarm; the
  fee-floor is the load-bearing fact.
- **A strictly-positive block-bootstrap CI on `Σ(sub-band asks) − 1 − fees` is NOT an edge when
  the sub-band's MIDS already sum to >1.0 — but treat that as a heuristic tell, not a coherence
  theorem.** ETH's active-band mids summing to 1.047 is corroborating evidence the "overround" is
  nominal ask-width, not fillable premium — verifier decomposition shows the >1.0 is driven mainly
  by the `mid=(ask+bid)/2=ask/2` convention on one-sided (`yes_bid=0`) floor-adjacent members
  pulled into the band, NOT by the two ATM strikes' spreads (restricted to two-sided members only,
  the mid-sum is 0.976, i.e. < 1.0). A mid-sum-vs-1.0 precheck is still useful (same family as
  L27's magnitude gate and L39's queue-blind-proxy caution) but must be read alongside a one-sided-
  member share, since a synthetic mid on a zero-bid quote is itself contaminated (`mid=ask/2`),
  not a fair-value estimate.
- **Cross-family tape join key gotcha:** `crypto_hourly` and `orderbook_depth` share tickers but
  NOT `capture_id` (separate sub-passes ~20 s apart) — join by ticker + nearest `captured_at`,
  and check the date-window overlap first (L9; depth starts 07-07, crypto 07-03 → ~52% ceiling
  on join coverage).
