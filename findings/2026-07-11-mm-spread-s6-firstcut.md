# S6 — Inventory-aware market-making: hourly-snapshot first cut → DEAD (first cut)

`2026-07-11` · S6 (kb/strategies/00-index.md row 18) · probe `scripts/s6_maker_firstcut.py` ·
tests `tests/test_s6_maker_firstcut.py` (15, offline) · read-only over
`tape/orderbook_depth/dt=*.jsonl` (4 accumulated days: 2026-07-07, 07-08, 07-10, 07-11;
07-09 missing per an already-resolved main incident — untouched)

## Hypothesis (S6)

Resting a maker quote at the best bid/ask earns the half-spread; net of adverse selection and
the 4×-cheaper maker fee that income is positive (Avellaneda-Stoikov: earn the spread instead
of paying it). Binding gate: spread income > adverse-selection cost + maker fee; block-
bootstrapped 95% CI **strictly > 0** at real fillable prices.

## What an hourly-snapshot proxy can and cannot support (stated up front)

`tape/orderbook_depth/` is **hourly L2 snapshots, not message-level order flow**. So this cut:

- **cannot** observe a real fill, a real fill probability, queue position, or true message-
  resolution adverse selection; and (unlike S10) **uses no settlement** — this is a pure
  quote-displacement proxy, not a realized-P&L-vs-`broker_truth` cut.
- **can** observe, for a ticker seen in two consecutive hourly captures: the quoted half-spread
  at capture-1 (notional maker income if filled) and how far the mid moved to capture-2
  (notional adverse selection — a resting quote is picked off on exactly the side the market
  moves toward).

Proxy round-leg P&L, entirely in YES-price space (the NO-side spread is identical, the NO mid
is one minus the YES mid — one space suffices), all prices carrying the tape's own tags
(`real_ask` = yes_ask, `real_bid` = yes_bid):

```
half_spread = (yes_ask_1 - yes_bid_1) / 2            # income if filled as maker  [real_ask/real_bid]
dmid        = mid_2 - mid_1                          # ~1h market displacement
fill_price  = yes_ask_1 if dmid>0 else yes_bid_1     # the adverse side you'd be filled on
maker_fee   = fee_per_contract(fill_price, MAKER_FEE_RATE)   # core.pricing — never hand-rolled (L18)
net         = half_spread - |dmid| - maker_fee
```

This is the Glosten-Milgrom intuition (if the mid rises by `dmid`, a buyer lifts your resting
ask at `mid_1 + half_spread` and your mark-to-fair leg is `half_spread - dmid`). It is
**optimistic** in assuming you always capture the full half-spread and **conservative** in
charging the whole hour's move as adverse; neither is a true fill population, so both a
frozen-inclusive and a movement-conditioned cut are reported to bracket the honest range.

Bootstrap unit = **the ticker** (the instrument you rest a quote on): consecutive pairs within
one game/bracket are correlated draws (a frozen game held for 5 hours = 4 near-identical pairs),
so resampling tickers — not pairs — avoids pseudo-replication (lesson L6 / S7c "by game").
Pairs are restricted to `<= 90 min` gaps (99.4% of pairs; excludes overnight/multi-day stale
comparisons of long-lived game tickers). One-sided books (empty ladder → `None` best) are a
valid market shape, not a capture failure (lesson L23), but have no two-sided spread to quote,
so they are skipped.

## L28 cheap precheck FIRST — is there even a signal?

58,583 depth records → **36,738 consecutive two-sided pairs** (≤90 min gap).

- **Frozen BBO (bid AND ask identical between the two captures): 25,618 / 36,738 = 69.7%.**
- Any mid movement: 29.1%.

So ~70% of consecutive pairs are frozen — high, but **not** a vast-majority-frozen dead end:
~30% show real movement, enough to test. Crucially, a **frozen pair represents no fill** — a
resting quote just sits there earning nothing — so booking its nominal half-spread as riskless
income (`dmid=0` → `net = half_spread − fee`) is the naive error the movement-conditioned cut
removes.

## Two artifacts the probe refuses to launder into an edge

**(1) The maker fee is a FLAT $0.01/contract at every interior price.** Kalshi's fee is
`ceil(rate·P·(1−P)·100)/100`; `MAKER_FEE_RATE · max P(1−P) = 0.0175·0.25 = 0.004375`, whose
`·100 = 0.4375` always ceils to 1 → **$0.01**. Verified across `p ∈ [0.01,0.99]`: the only
distinct value is `0.01`. So a maker must net **more than a full cent** of half-spread-minus-
adverse just to break even — a 1¢-spread book (half-spread 0.5¢, the modal case) mathematically
cannot. This sharpens L5/L18: the maker fee is not merely "4× cheaper", it is a **flat 1¢ floor**
a sub-2¢ spread can never clear.

**(2) The apparent edge is entirely a wide-wing artifact (L12/L26 floor-artifact family).**
Spread-bucket decomposition of `net` (real_ask+real_bid):

| population | n_tickers | n_pairs | frac net>0 | mean_net | 95% CI (by-ticker boot) |
|---|---|---|---|---|---|
| ALL two-sided (naive; frozen booked as free spread) | 1,050 | 36,738 | 60.6% | **+$0.06928** | [+$0.06067, +$0.07807] |
| WIDE WING >30¢ (**unfillable artifact — not a maker edge**) | 313 | 7,307 | 99.9% | **+$0.33912** | [+$0.32853, +$0.34923] |

The "positive edge" is the wing: far/one-sided brackets quote a huge nominal spread (e.g. a
0.03 bid against a 0.89 ask → a 43¢ half-spread) **precisely because there is no two-sided
interest**. That spread is not maker-capturable; a frozen wing has `dmid≈0`, so the `|dmid|`
proxy spuriously books the entire unfillable half-spread as riskless profit. This is the exact
"stretch a descriptive cut into a verdict" trap the charter forbids — the mean is dominated by
prices nobody would fill you at.

## Realistic maker population — the actual gate

Restricting to **genuinely-tight two-sided books** (where a maker quote could realistically be
crossed for its spread), the sign flips and stays flipped across every cap
(all by-ticker block bootstrap, 10,000 resamples, seed 42, `real_ask+real_bid`):

| population | n_tickers | n_pairs | frac net>0 | mean_net | 95% CI |
|---|---|---|---|---|---|
| tight ≤ 2¢ | 670 | 15,272 | 12.0% | **−$0.01120** | [−$0.01211, −$0.01034] |
| tight ≤ 5¢ | 849 | 23,200 | 38.8% | **−$0.00619** | [−$0.00703, −$0.00538] |
| tight ≤ 10¢ (**primary**, frozen-inclusive, max-generous income) | 901 | 27,713 | 48.1% | **−$0.00195** | [−$0.00297, −$0.00094] |
| tight ≤ 10¢ **AND mid moved** (honest adverse-selection test) | 875 | 6,960 | 39.3% | **−$0.02010** | [−$0.02271, −$0.01759] |

Both ends of the honest range are **strictly negative**: even the frozen-inclusive cut (maximally
generous — counts unrealized spread on frozen books as free income) has a 95% CI entirely below
zero, and conditioning on actual movement (the only population where a fill plausibly occurred
and adverse selection is real) drives it more negative still. The flat 1¢ maker fee plus the
adverse move exceeds the capturable half-spread on every realistic two-sided book.

## Verdict: DEAD (first cut)

The binding bar (block-bootstrapped 95% CI **strictly > 0** at real fillable prices net of the
maker fee) is not met on any economically-realistic maker population — the CI is **strictly < 0**
across the ≤2¢/≤5¢/≤10¢ sweep and under the movement-conditioned adverse-selection test. The
only population with CI>0 is the **wide-wing artifact** (>30¢ nominal spreads on far/one-sided
brackets), whose "edge" is an unfillable quoted spread, not a maker opportunity — declaring it
alive would repeat the L12/L26 floor-artifact and L27 magnitude-gate errors.

Mechanism, in one line: **the maker fee is a flat 1¢/contract, and the modal genuinely-two-sided
Kalshi book quotes a 1–2¢ spread (0.5–1¢ half-spread), so the fee alone consumes the entire
capturable half-spread before any adverse selection is even charged.** Same family as S13's
verdict (the maker fee ate the assumed 1¢ bid-under-fair margin) — here the same fee floor
kills the spread-capture thesis directly.

This is a **structural first-cut DEAD, honestly scoped to what an hourly sample supports**: it
is a quote-displacement proxy, not a fill-level measurement, so it cannot *prove* a maker edge
alive — but it can and does show that on the realistic population the spread does not clear the
flat fee, which is dispositive for the gate as posed. More days of the *same* hourly tape would
not change this: the killer is the flat 1¢ fee vs the modal 1–2¢ spread, a structural fact, not
a sample-size one.

## What a fuller cut would need (not pursued — structure, not sample, is the wall)

- **Message-level trade tape** (a burst/continuous-capture leg) to measure *real* fill
  probability and realized (not full-hour) adverse selection — the hourly `|dmid|` charges the
  whole hour's move, which no real fill horizon incurs. But it cannot rescue a 0.5–1¢ half-
  spread from a flat 1¢ fee on the modal book; it would only refine the *magnitude* of an
  already-negative realistic population.
- **A liquidity/adverse-selection filter that quotes only wide-enough, low-toxicity books** —
  which is precisely S11 (sharp-anchored maker quoting on illiquid binaries): quote only the
  Pinnacle-EV+ side to escape adverse selection, and only where the spread genuinely exceeds the
  1¢ fee floor. S6's naive "quote everything at the BBO" is dead; S11's *selective* maker is a
  distinct, un-falsified trade that would need the same L2 depth tape plus an external fair-value
  anchor and a real fill-sim.

## Lesson candidates (for kb-distiller)

- **L-cand A:** Kalshi's **maker fee is a flat $0.01/contract at every interior price** (not
  price-scaled): `ceil(0.0175·P·(1−P)·100)/100 = 0.01` for all `0<P<1` because the maximum of
  `P(1−P)` is 0.25. Consequence: a maker must net **> 1¢** of half-spread-minus-adverse to break
  even, so the modal 1–2¢-spread book (0.5–1¢ half-spread) is structurally unprofitable before
  adverse selection is even counted. Sharpens L5/L18 ("4× cheaper") into a hard floor. (Verified
  in `tests/test_s6_maker_firstcut.py::test_maker_fee_is_flat_one_cent_at_every_interior_price`.)
- **L-cand B:** A **wide bid-ask on a Kalshi far/one-sided bracket is a nominal, not
  maker-capturable, spread** — it is wide *because* there is no two-sided interest. A naive
  maker-spread P&L that books the half-spread as income lets these unfillable wings dominate the
  mean (>30¢ wings: +$0.34/contract, vs −$0.002 on realistic ≤10¢ books). Generalizes L12/L26's
  floor-artifact caution to the *spread-capture* direction: cap the spread / exclude the wing
  before any maker-edge verdict, exactly as L28 says to check observability first.
- **L-cand C:** For a maker-spread proxy over **hourly snapshots**, a *frozen* consecutive pair
  (BBO unchanged) is **no fill**, so it must not book its nominal half-spread as free income;
  report the frozen fraction (here 69.7%) as an L28 precheck and bracket the verdict with both a
  frozen-inclusive and a movement-conditioned cut — both came out strictly negative here, which
  is what makes the DEAD robust rather than an artifact of the fill assumption.
