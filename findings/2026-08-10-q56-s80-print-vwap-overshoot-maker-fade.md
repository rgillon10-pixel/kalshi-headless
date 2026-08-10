# Q56 / S80 — print-VWAP-overshoot contrarian maker fade: DEAD by CI, on an ADEQUATE population

**Date:** 2026-08-10 · **Run:** research loop (protocol v3), Q56 S80 milestone
**Verdict class:** **CI FALSIFICATION** — not a data-adequacy refusal. The fillable
population clears the L41 floor by 2.7x, so the strategy was genuinely measured and it lost.
**Status of this record:** **CONFIRMED-WITH-CORRECTIONS** (2026-08-10, later the same run) —
the producing sub-context had no `Task`/subagent tool (the L287/L288/L290/L291/L295/L308/L313/L325
precedent) and ran the sanctioned no-verifier redundancy fallback instead
(`scripts/q56_s80_rederive.py`, a from-scratch second implementation sharing no code with the
probe, reproducing every headline number). The orchestrating research-loop session then
dispatched an independent `verifier` agent, which built a THIRD from-scratch implementation
(own parser, own settlement reader, own bootstrap RNG), reproduced every population/K1/K3 number
to the digit, stress-tested for look-ahead / game-grouping / fee-direction / sign errors and
found none, and inverted the fill orientation entirely as an adversarial check (still DEAD on
both branches) — **CONFIRMED-WITH-CORRECTIONS**: the DEAD verdict stands, and four wording/
arithmetic errors it caught are fixed in place below (a 100.1%→101.3% arithmetic slip, a
settlement-count table that summed to 92 against 87, a "65 of 76 games" population that does
not exist in this tape, and an overclaim that K1 directly refutes the registered CHASE
mechanism when it is algebraically a static per-ticker price-level cut with no chase term in
it — DEAD by K3's CI either way). Two-agent rule: **SATISFIED**. **The S80 registry STATUS
COLUMN IS NOW FLIPPED to `dead ✗`** in `kb/strategies/00-index.md` — this is a verdict-class
change and the two-agent CONFIRM above is what authorizes it.
**Still 0 proven edges.**

---

## 1. What was tested, and what pre-registered it

S80's registry row (written 2026-08-10 by the Q21 round-#26 idea-gen pass, after its own
independent verifier attack, i.e. **before this probe existed**) fixes the direction:

> late in a Kalshi sports moneyline, retail chases the leading side, pushing executed prints
> above settlement-fair; a MAKER resting on the **TRAILING** side is filled by the chase at an
> overshoot → +EV iff overshoot > maker fee.

That external pre-registration is the honesty guarantee on the DIRECTION. The **free
parameters** (the trailing window, the print minima, the trigger threshold) were chosen at
build time by this run's author, so all of them are swept and the entire 12-cell grid is
reported below — the verdict does not depend on the chosen cell.

**Probe:** `scripts/q56_s80_print_vwap_overshoot_maker_fade.py`
**Report:** `reports/q56_s80_print_vwap_overshoot_maker_fade.json` (+ `.md` summary)
**Independent re-derivation:** `scripts/q56_s80_rederive.py` →
`reports/q56_s80_rederive.json`
**Tests:** `tests/test_q56_s80_print_vwap_overshoot_maker_fade.py` (43),
`tests/test_q56_s80_rederive.py` (10)
**Reads only committed tape.** Zero network calls, zero credentials, zero orders of any
kind (not even paper). `tape/kalshi_trades/` (6 day-files) × `tape/orderbook_depth/`
(34 day-files) × settlement via `core.settlement_sources`.

### The recipe, exactly

| step | rule | price_source_tag |
|---|---|---|
| signal | per-ticker print VWAP over prints STRICTLY before the snapshot: `chase = recent_vwap(last 30 min) − anchor_vwap(everything earlier)`, ≥5 anchor / ≥3 recent prints | `broker_truth` |
| trigger | `abs(chase) ≥ $0.02` (2 ticks; the Kalshi maker fee is a FLAT $0.01 across the interior range, L18/L30 — a trigger inside the fee cannot pay for itself) | — |
| leg | REGISTERED direction: rest on the TRAILING side. `chase > 0` → NO bid at `best_no_bid`; `chase < 0` → YES bid at `best_yes_bid` | `real_bid` |
| queue | price-time priority: `queue_ahead` = resting size at price ≥ our bid on our OWN ladder at the snapshot | `real_bid` |
| fill | cumulative consuming EXECUTED-PRINT volume in `(t_i, t_{i+1}]` must STRICTLY exceed `queue_ahead`. NO-bid consumed by `taker_book_side == "bid"` (a BUYER lifting the mirrored offer) at `yes_price ≥ 1 − q`; YES-bid consumed by `taker_book_side == "ask"` (a SELLER hitting the bid) at `yes_price ≤ p`. Q51-m2 CORRECTED orientation | `broker_truth` |
| P&L | `payout − fill_price − fee_per_contract(fill_price, MAKER_FEE_RATE)`; held to settlement, losing leg fully priced, never conditioned away | `real_bid` + `broker_truth` |
| bootstrap | block by **GAME** (`event_ticker`), never by outcome (L6). `n_boot=10000`, `seed=42` | — |

Fee: **maker 0.0175** via `core.pricing.MAKER_FEE_RATE` only (L5 — the 4x taker overcharge
that sank an S13 draft). `TAKER_FEE_RATE` does not appear in the probe at all; a test pins that.

---

## 2. The result

### Gate K1 — is the overshoot bigger than the maker fee? **NO. It is the WRONG SIGN.**

Per-ticker full-sample print VWAP minus its `broker_truth` settlement value, aligned to the
registered fade direction, block-bootstrapped by GAME (**81 tickers / 66 games**):

| quantity | value | tag |
|---|---|---|
| fade-aligned gross overshoot, mean | **−$0.15922** | `broker_truth` |
| 95% CI (block-boot by game) | **[−$0.22531, −$0.08180]** | `broker_truth` |
| maker fee per contract | $0.01 (flat) | `core.pricing` |
| K1 passes? | **NO** — the point estimate is not merely inside the fee, it is negative and ~16x the fee in the WRONG direction | |

The decomposition is the whole story:

| chased side (own VWAP) | n tickers | mean VWAP | realized settle rate | mean overshoot (VWAP − settle) |
|---|---|---|---|---|
| YES, i.e. the **leading** side (VWAP ≥ 0.50) | 30 | 0.6638 | **0.8333** | **−0.16949** |
| NO, i.e. the **trailing** side (VWAP < 0.50) | 51 | 0.2512 | **0.0980** | **+0.15318** |

The leading side's prints sit **BELOW** what it turned out to be worth, and the trailing
side's sit **ABOVE**. That is textbook favourite-longshot bias
(`kb/quant-finance/favorite-longshot-bias.md`). **Correction (verifier, 2026-08-10):** K1 is
algebraically a **static per-ticker price-level cut** — `chased_side` is set by the ticker's
own full-sample VWAP level (`>= 0.5`), and the CHASE signal itself never enters
`overshoot_rows` — so K1 is not a direct test of the registered chase direction, and "exact
opposite of the premise" overclaims what it computes. What K1 legitimately shows is that
resting on the trailing (sub-50c) side buys a systematically overpriced longshot, which is the
same conclusion the registered strategy needs to be false to work, but the falsification of the
CHASE mechanism specifically rests on gate K3 below (the actual queue-aware fill-sim on the
registered trailing-side leg), not on K1.

### Gate K2 — adequacy. **PASSES.** This is not a data-adequacy death.

| quantity | value |
|---|---|
| tape | 213,431 `broker_truth` prints / 87 traded sports market tickers / 72 games / 6 trade-days |
| settlement | 81 resolved binary / 6 unresolved (of which 5 are `scalar`, non-binary, dropped per L52, and 1 is listed-but-unsettled) — all `broker_truth`; **correction (verifier): the earlier "81+5+6" phrasing double-counted the scalar tickers, which are a subset of the 6 unresolved, not a third bucket** |
| intervals seen | 2,607 · signal computable 364 · triggered 180 · one-sided touch dropped 59 |
| **candidates** | **121** over **31 games** |
| **fills** | **84** (fill rate **69.42%**) over **27 games** — 2.7x the L41 floor of 10 |
| fills traceable to a `broker_truth` `trade_id` | **84 / 84 (100%)** |
| median `queue_ahead` at entry | 662.45 contracts |
| median fill price | **$0.27** (`real_bid`) |

The fill rate is two orders of magnitude above S19's 0.45% dead-thin floor. **This family
dies on the EDGE, not on adequacy or fillability** (the S14/L53 distinction).

### Gate K3 — the CI. **DEAD, fully below zero on the headline cell.**

| branch | n games | n legs | mean | 95% CI | admissible (L41) | clears tick (L27) | verdict |
|---|---|---|---|---|---|---|---|
| **`all_candidates` (headline)** | **31** (informative **27**, L326) | 121 | **−$0.09727** | **[−$0.18770, −$0.01229]** | True | False | **DEAD-negative-CI** |
| `conditional_on_fill` | 27 | 84 | **−$0.14012** | **[−$0.26919, −$0.01143]** | True | False | DEAD-negative-CI |

Kish effective n (L322) on the headline branch: **20.95** of 31 nominal units
(design effect 1.48) — still 2.1x the floor, so the adequacy margin survives the honest
correction.

**Kill conditions fired: `K1_overshoot_within_maker_fee`, `K3_headline_ci_not_positive`.
`K2` did NOT fire. Verdict: DEAD.**

### Parameter sensitivity — 12/12 cells negative

Every cell of the author-chosen free parameters (`all_candidates` branch):

| window (min) | θ | n cand | fills | fill rate | games | mean | 95% CI | verdict |
|---|---|---|---|---|---|---|---|---|
| 15 | 0.01 | 163 | 98 | 0.601 | 30 | −0.05791 | [−0.1366, +0.0077] | straddles 0 |
| 15 | 0.02 | 123 | 87 | 0.707 | 30 | −0.08130 | [−0.1747, +0.0010] | straddles 0 |
| 15 | 0.03 | 103 | 74 | 0.718 | 30 | −0.07408 | [−0.1690, +0.0118] | straddles 0 |
| 15 | 0.05 | 88 | 64 | 0.727 | 27 | −0.06409 | [−0.1651, +0.0283] | straddles 0 |
| **30** | **0.02** | **121** | **84** | **0.694** | **31** | **−0.09727** | **[−0.1877, −0.0123]** | **negative CI** |
| 30 | 0.01 | 176 | 102 | 0.580 | 34 | −0.06420 | [−0.1395, +0.0013] | straddles 0 |
| 30 | 0.03 | 104 | 74 | 0.712 | 31 | −0.11952 | [−0.2150, −0.0327] | negative CI |
| 30 | 0.05 | 79 | 60 | 0.759 | 27 | −0.09215 | [−0.1922, −0.0034] | negative CI |
| 60 | 0.01 | 192 | 103 | 0.536 | 34 | −0.05130 | [−0.1142, +0.0118] | straddles 0 |
| 60 | 0.02 | 110 | 77 | 0.700 | 33 | −0.05664 | [−0.1546, +0.0399] | straddles 0 |
| 60 | 0.03 | 95 | 69 | 0.726 | 30 | −0.08453 | [−0.1909, +0.0176] | straddles 0 |
| 60 | 0.05 | 71 | 53 | 0.746 | 25 | −0.08014 | [−0.1903, +0.0266] | straddles 0 |

**Honest framing of the default cell.** The chosen headline cell (30 min / $0.02) is one of
only 3 of 12 whose CI is entirely below zero; the other 9 straddle zero from below. Both
defaults were fixed on principled grounds *before* the grid was computed — 30 min because it
matches the measured book cadence (§4), $0.02 because it is the first threshold strictly
above the flat $0.01 maker fee — but the DEAD verdict does not lean on that choice: **the
point estimate is negative in 12/12 cells**, and K1 (a full-sample statistic with no window or
threshold in it at all) fails on its own, decisively.

---

## 3. The mirror leg — and why the sign-flip does NOT rescue it (DESCRIPTIVE ONLY)

The obvious next thought — "the sign is backwards, so rest on the CHASED side instead" — is a
**post-hoc direction and is not a verdict** (L41's family of selection artifacts). It is
computed and reported so nobody has to guess, and it kills the idea rather than resurrecting it:

| mirror branch (rest on the CHASED side) | n games | mean | 95% CI | verdict |
|---|---|---|---|---|
| `all_candidates` | 31 | −$0.00669 | [−$0.08000, +$0.06330] | DEAD-straddles-zero |
| `conditional_on_fill` | 29 | −$0.01095 | [−$0.13956, +$0.10014] | DEAD-straddles-zero |

### The adverse-selection identity (the load-bearing new fact)

On the mirror leg's **74 filled contracts**, decomposed per contract:

| quantity | value | tag |
|---|---|---|
| static gross at the ticker's own print VWAP | **+$0.07508** | `broker_truth` |
| realized gross at our actual resting price | **−$0.00095** | `real_bid` |
| **adverse-selection cost** | **+$0.07603** | |
| realized NET after the flat maker fee | **−$0.01095** | |

Read it carefully: a resting bid is **strictly cheaper** than the average print, so under
*random* fills the realized gross must **exceed** the static gross. It does not. The flow gave
us the fills that hurt, and **101.3% of a +7.5¢ static edge disappeared into which contracts
actually filled** (0.07602780845007773 / 0.07508186250413179; correction, verifier: the
originally-quoted 100.1% was an arithmetic slip) — before the fee was charged at all. The same decomposition on the
registered leg reads static −$0.16038 → realized −$0.13012 (adverse-selection cost
**−$0.03026**, i.e. genuinely favourable price improvement), which confirms the machinery is
not simply biased against makers: the registered leg loses because its **mechanism is
wrong-signed**, the mirror leg loses because of **adverse selection**. Two different deaths,
one probe.

This is the same identity S1's Q37 summer-maker re-test found in weather
(break-even hit rate 9.02% vs realized-on-fills 14.69%) and S23 found in sports favourites,
now measured directly against executed prints rather than a queue-departure proxy.

---

## 4. Book-cadence reconciliation — the L283 scope question, resolved

The Q56 spec owed a reconciliation: the round-#26 verifier measured **~29 min** intra-ticker
`orderbook_depth` cadence on TRADED sports tickers, while the graveyard has been quoting
**~3h** as a blanket maker-fill blocker. Measured here on committed tape:

| population | n tickers | snapshots/ticker (median) | pooled gap p25 | **pooled gap median** | pooled gap p75 | pooled gap p90 |
|---|---|---|---|---|---|---|
| all depth tickers | 108,668 | **1** | 31.09 min | 31.99 min | 179.36 min | 360.14 min |
| traded tickers | 87 | 28 | 28.72 min | 31.33 min | 179.54 min | 360.39 min |
| traded sports GAME tickers | 87 | 28 | **28.72 min** | **31.33 min** | **179.54 min** | 360.39 min |

**Both figures are correct statistics of the SAME distribution.** The intra-ticker revisit
interval is **bimodal**: a ~31-minute lower mode (revisits *within* a collector burst) and a
~180-minute upper mode (the gap *between* bursts), with a ~360-minute tail. "~29 min" is
essentially the p25 (28.72); "~3h" is essentially the p75 (179.5). Neither is "the cadence"
and neither refutes the other — **there is no scalar cadence to quote**.

What this settles for S80's design: the ~3h figure is **not** a blanket blocker on traded
sports tickers (median 28 snapshots per ticker, ~6–12 usable pre-settlement intervals per
game — the round-#26 verifier's claim survives), and indeed the fill-sim above got 121
candidates and 84 fills out of it. But the flip side is equally real: a quarter of intervals
are ≥3h wide, and a maker leg resting across one of those is exposed for three hours to a
book we cannot see. That is a *ceiling on resolution*, not an emptiness — the honest reading.

**Second, separate fact, same table:** across ALL 108,668 depth tickers the median is **1
snapshot ever**, so `orderbook_depth` is L283-shaped (a census, not a panel) *in aggregate* —
but the traded-sports subset is a genuine panel (28 snapshots median, 87/87 tickers with a
book). L283's warning applies to the family; it does not apply to this probe's population,
and the difference is measurable rather than assumed.

---

## 5. Two-agent status and independent re-derivation

No `Task`/subagent tool was exposed to the producing sub-context, so no independent `verifier`
agent could be dispatched there. Under the sanctioned fallback, `scripts/q56_s80_rederive.py` re-derives the
headline from scratch: its own JSONL readers, its own hand-rolled ISO-8601 → epoch parser
(string slicing + Hinnant's days-from-civil, no `datetime.fromisoformat`, no `core.timeutil`),
its own settlement reader straight off `tape/settlement_ledger/` + `tape/q51_settlement_cache/`
(not `core.settlement_sources`), its own round-up-to-cent fee formula, its own signal/queue/fill
loop, its own block bootstrap over its own RNG. Only `MAKER_FEE_RATE` is imported, because
`scripts/invariants.py::no_handrolled_fee_rate` forbids any module but `core/pricing.py` from
spelling a schedule rate.

| number | probe | independent re-derivation | agreement |
|---|---|---|---|
| prints / tickers / games | 213,431 / 87 / 72 | 213,431 / 87 / 72 | exact |
| settled binary tickers | 81 | 81 | exact |
| K1 mean | −0.15922 | −0.1592186397431818 | exact |
| K1 CI | [−0.22531, −0.08180] | [−0.22659, −0.08195] | bootstrap noise (independent draw) |
| leading-side overshoot / n | −0.16948863869403363 / 30 | −0.16948863869403363 / 30 | exact |
| trailing-side overshoot / n | +0.1531774638897395 / 51 | +0.1531774638897395 / 51 | exact |
| candidates / fills / fill rate | 121 / 84 / 0.694215 | 121 / 84 / 0.694215 | exact |
| games with candidate / with fill | 31 / 27 | 31 / 27 | exact |
| `all_candidates` mean, CI | −0.0972727272727273, [−0.18769841, −0.01228571] | −0.0972727272727273, [−0.18769841, −0.01228571] | **bit-identical** |
| `conditional_on_fill` mean, CI | −0.14011905, [−0.26918919, −0.01142857] | −0.14011905, [−0.26918919, −0.01142857] | **bit-identical** |

The independent parser is itself pinned against `core.timeutil.parse_iso_utc` on real
committed timestamps (`tests/test_q56_s80_rederive.py`), so the agreement is not two
implementations sharing one bug.

**That redundancy pass alone was NOT the two-agent verdict rule.** The orchestrating
research-loop session separately dispatched an independent `verifier` agent (it had the
`Task`/subagent tool where the producing sub-context did not), which built a THIRD from-scratch
implementation (own JSONL readers, own Hinnant days-from-civil ISO parser, settlement read
directly off `tape/settlement_ledger/` + `tape/q51_settlement_cache/`, its own bootstrap with an
independent seed/RNG stream and 20,000 draws) and reproduced every headline number to the digit:
prints/tickers/games, the full funnel, K1's mean and decomposition, both K3 branches' means, and
all 12 grid cells' n/fills/means. It additionally: checked `event_ticker_of()`'s
derived-game-id parsing against the venue's own `event_ticker` field on 10,785 ticker/event
pairs (0 mismatches — no block-bootstrap off-by-one); ran `sign_bounded_objective` (L249) on
both K3 objects and confirmed the negative CI is not a gate artifact (two-sided support,
`one_sided_support=False` on both); and inverted the `taker_book_side` fill-orientation
convention entirely as an adversarial check — still DEAD-negative-CI on both branches under the
inversion. **Verdict: CONFIRMED-WITH-CORRECTIONS** (see the corrections folded into §2 and §6
above and the status line at the top of this document). Two-agent rule: **SATISFIED.**

---

## 6. What is and is not claimed

**Claimed.** On 6 days of committed sports print tape joined to committed book depth, the
registered S80 trade — rest a maker bid on the trailing side of a print-VWAP chase, fill
queue-aware off executed prints, hold to settlement — has a block-bootstrapped-by-game 95% CI
entirely **below** zero at `real_bid` net the maker fee, on a population 2.7x the L41 floor.
Its motivating overshoot has the opposite sign to the one registered.

**Not claimed.** (a) That the *mirror* direction is dead by CI — it straddles zero, which is a
null, and it is post-hoc besides. (b) That maker-side sports fading is dead in general: this
is one signal, one window family, 6 trade-days, 27 filled games, and the trade tape is a
backfill sample rather than the platform. (c) That the fill model is exact — it is
generous in ignoring order cancellations ahead of us and conservative in assuming we join the
back of the touch queue; it does not model partial fills or size.

**Caveats a verifier should attack first.**
1. **Ticker-selection provenance.** The 87 tickers come from the Q52/Q54 phase-1/phase-2
   backfill, which sampled rather than enumerated. If that sample is correlated with
   settlement (e.g. skewed to markets that settled early), the K1 decomposition inherits the
   skew. The CI verdict does not depend on K1, but the *explanation* does.
2. **51 trailing vs 30 leading tickers.** **Correction (verifier): the original "65 of 76
   games" cited a population that does not exist in this tape — no cut here has 76 games.**
   The correct figures: 61 of the 72 traded games contribute only ONE traded outcome market
   over the full traded population, or 55 of 66 games over K1's own settled 81-ticker
   population (distribution: 55 games × 1 ticker, 7 × 2, 4 × 3). Either way the leading/
   trailing split is mostly a *per-market price-level* cut, not a within-game comparison;
   regression effects on the 81-ticker sample deserve scrutiny.
3. **Interval width.** ~25% of scored intervals are ≥3h wide (§4). A tighter book would
   change which fills occur, though not obviously in the strategy's favour.
4. **A mutable artifact sits inside the settlement join (L325).** `core.settlement_sources`
   resolves this population from `settlement_ledger` (49 tickers) + `q51_settlement_cache`
   (32) — and that cache's glob is `q51_settlement_cache/settlement*.json`, which includes
   the **mutable** `settlement.json` alongside the frozen `settlement-m2-2026-08-04.json` /
   `settlement-m3-2026-08-10.json` snapshots. A future Q51 `--build-cache` run overwrites the
   mutable file, so ~40% of this probe's settlement inputs are not frozen. Nothing here
   depends on a single ticker, and the independent re-derivation read the same directory by a
   different path and agreed exactly — but a re-run months from now may not reproduce these
   numbers byte-for-byte, and that is a property of the cache, not of the probe.
5. **Population definition.** `is_game_series` (series token ends in `GAME`) is a suffix test,
   not an allow-list, so a newly backfilled league is never silently dropped. It excludes
   exactly 4 of the 91 tickers in `tape/kalshi_trades/` — `KXBTC-26AUG0312-B63950`,
   `KXETH-26AUG0300-B1842`, `KXBTC-26AUG0221-B63650`, `KXBTC-26AUG0300-B62550` — which are
   crypto-hourly brackets, not sports moneylines, and are outside S80's registered scope.

---

## 7. Files

- `scripts/q56_s80_print_vwap_overshoot_maker_fade.py` — the probe (offline, read-only)
- `scripts/q56_s80_rederive.py` — independent second implementation
- `tests/test_q56_s80_print_vwap_overshoot_maker_fade.py` — 43 offline tests
- `tests/test_q56_s80_rederive.py` — 10 offline tests
- `reports/q56_s80_print_vwap_overshoot_maker_fade.json` / `.md`
- `reports/q56_s80_rederive.json`
