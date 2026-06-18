# S1 — Longshot-fade real-ask calibration on Kalshi KXHIGH brackets

**Date:** 2026-06-18 · **Dossier opportunity:** #2 (`findings/2026-06-18-codebase-money-map.md`)
**Script:** `scripts/longshot_fade_probe.py` (read-only, re-runnable)
**Data:** `arb-bot-v2/data/tape_replica/orderbook_archive_recovered.db` (opened `mode=ro`; tape
unmodified — mtime stayed 2026-05-09, no WAL/SHM created).
**Prices:** RECONSTRUCTED REAL asks, `price_source_tag = "real_ask"` — **not synthetic, not midpoint.**

---

## VERDICT (the honest bottom line)

> **NO EDGE. Null result.** Fading Kalshi KXHIGH daily-temperature longshots, priced and
> filled at real book asks, does **not** produce a dollar edge once a realistic maker spread,
> fee, and fill-probability haircut are charged. The 95% bootstrap CI on net per-trade P&L
> **straddles zero at every longshot threshold tested (0.05 → 0.25)**. The lower bound never
> strictly clears zero. This falsifies the longshot-fade family on this sample, exactly as the
> dossier anticipated ("Expect it to straddle or sit below zero").

Headline (longshot = implied prob < 0.20, the dossier's framing):

| metric | value |
|---|---|
| net mean expected P&L / trade | **+$0.00448** |
| 95% block-bootstrap CI | **[−$0.00486, +$0.01333]** |
| lower bound clears zero? | **NO** |
| longshot trades (n) | 654 |
| bootstrap blocks (contract-days) | 21 |

**Threshold sensitivity — robustly null (and *negative* at the deepest longshots):**

| longshot_max | n_trades | mean net P&L/trade | 95% CI | clears 0? |
|---|---|---|---|---|
| 0.05 | 334 | **−$0.00331** | [−$0.00903, +$0.00155] | no |
| 0.10 | 476 | −$0.00260 | [−$0.01283, +$0.00647] | no |
| 0.15 | 577 | +$0.00070 | [−$0.00914, +$0.00983] | no |
| 0.20 | 654 | +$0.00448 | [−$0.00486, +$0.01333] | no |
| 0.25 | 737 | −$0.00035 | [−$0.00971, +$0.00896] | no |

The deepest longshots (<0.05), where the favorite-longshot bias should be *strongest*, are the
ones with a **negative** mean — the opposite of an edge. There is no threshold at which a
skeptic could honestly graduate this.

---

## n — completeness (honest drops)

- **(city, contract-day) groups:** 176 total → **165 usable** · 11 dropped (incomplete book at T-24h).
- **Brackets priced (trade rows):** 990 of 1,056 settled brackets.
  - 51 brackets dropped: no `ticker`-event book at/before T-24h.
  - 0 dropped for ask≥1.0 (no NO liquidity); 0 dropped crossed/malformed.
- A group is dropped **whole** if any of its 6 brackets lacks a book at T, so every priced
  group is a complete 6-way partition (bracket_sum is a valid divisor). This is why drops are
  reported at both bracket and group granularity.

---

## Calibration table — win-rate vs implied prob (5¢ bins, full sample, n=990)

`gap = realized_win_rate − mean_implied_prob`. Negative gap in the low bins = longshot
overpriced (the bias we fade); positive gap in the high bins = favorite underpriced.

| implied-prob bin | n | mean implied | realized win-rate | gap |
|---|---|---|---|---|
| [0.00,0.05) | 334 | 0.0264 | 0.0120 | −0.0144 |
| [0.05,0.10) | 142 | 0.0710 | 0.0563 | −0.0147 |
| [0.10,0.15) | 101 | 0.1231 | 0.0792 | −0.0439 |
| [0.15,0.20) | 77 | 0.1737 | 0.1039 | −0.0698 |
| [0.20,0.25) | 83 | 0.2241 | 0.3012 | +0.0771 |
| [0.25,0.30) | 58 | 0.2734 | 0.2414 | −0.0320 |
| [0.30,0.35) | 47 | 0.3209 | 0.3617 | +0.0408 |
| [0.35,0.40) | 46 | 0.3745 | 0.4130 | +0.0385 |
| [0.40,0.45) | 27 | 0.4204 | 0.5185 | +0.0981 |
| [0.45,0.50) | 26 | 0.4696 | 0.5000 | +0.0304 |
| [0.50,0.55) | 21 | 0.5237 | 0.6190 | +0.0954 |
| [0.55,0.60) | 8 | 0.5748 | 0.5000 | −0.0748 |
| [0.60,0.65) | 6 | 0.6147 | 0.6667 | +0.0520 |
| [0.65,0.70) | 3 | 0.6798 | 1.0000 | +0.3202 |
| [0.70,0.75) | 4 | 0.7243 | 1.0000 | +0.2757 |
| [0.75,0.80) | 3 | 0.7823 | 1.0000 | +0.2177 |
| [0.80,0.85) | 1 | 0.8113 | 1.0000 | +0.1887 |
| [0.85,0.90) | 3 | 0.8597 | 1.0000 | +0.1403 |

**Reading the curve:** the directional bias *is* present and points the textbook way —
longshots (<0.20) realize fewer wins than priced (gaps −1.4¢ to −7.0¢), favorites realize
more (the >0.65 bins all settle 100% yes). **But the longshot mispricing is small (single
digits of a cent) and the favorite tail is thin (n=1–6 per bin).** A few cents of calibration
gap is not enough to survive a 2¢ maker spread + the fill-probability haircut — which is
precisely what the P&L bootstrap shows. The signal exists; the dollar edge does not. This is
the same shape as the dead KXHIGH ensemble: a real directional signal that the structural
~5–10¢ overround eats.

---

## Method (the binding test, as run)

**Source & why `real_ask`.** The tape has no book snapshot — only `delta` events
(`size_delta` only, `size_total` always NULL) that assume an initial snapshot we don't have
(early deltas are negative for never-added levels), so integrating deltas is unreliable.
Instead we use the self-contained `ticker`-event BBO, which carries Kalshi's published
`yes_ask_dollars` = the complement of the best NO bid (Kalshi posts bids only;
`collection/normalize.py`). That published ask is the real, fillable taker price → stamped
`real_ask`. We require `yes_ask < 1.0` (else best_no_bid = 0, no fillable NO liquidity) and
drop crossed books.

**T-24h decision time (exact definition):**
`close_T(group)` = latest `ticker`-event ts across the group's 6 brackets (the empirical close;
lands at ~midnight-local of the day after the observation day — ~04:59 UTC ET / 05:59 CT /
06:59 MT / 09:00 PT). **`T = close_T − 24h`.** For each bracket we read the most recent
`ticker` BBO **at or before T** (strictly causal, no look-ahead). The contract-day is parsed
from the **ticker** (`KXHIGH<CODE>-YYMMMDD`), never from `settlements.settled_at` (that is the
shared cron run-time, not the settlement instant).

**Pricing (Hard Rule #3).** Per (city, day) group: `bracket_sum = Σ yes_ask` over all 6
brackets; each implied prob via `core.pricing.normalized_ask(yes_ask, bracket_sum)` (the only
sanctioned ask→prob site). Persisted `overround = bracket_sum − 1.0`. The 6 brackets are a
verified clean partition (2 T-tails + 4 B-bands; exactly one settles `yes` on all 176 groups),
so normalized probs sum to 1.0.

**Overround actually absorbed at T-24h (real asks):** mean **+0.0984**, median +0.10, range
[−0.07, +0.30]. This ~10¢ structural cost — visible *because* we price off real asks, not a
synthetic — is the same family of cost (3–10¢) that killed pt1.

**Cost model for the maker NO-on-longshot rule (assumptions stated explicitly):**
- Rule: for each bracket with implied prob < threshold, BUY the NO outcome as a maker (fade
  the longshot YES).
- **Spread = 2¢ (`HAIRCUT_SPREAD`)**, applied in the HONEST direction: effective entry =
  `no_bid + 0.02` (a resting maker who actually gets filled in a thin longshot must improve
  *up* toward the ask → pays *more*, never less). *(Sign discipline note below.)*
- **Maker fee = $0.0035/contract** (`MAKER_FEE`) — conservative; Kalshi's true maker fee is ~0,
  so this is deliberately pessimistic to avoid claiming a fee-free edge.
- **Fill probability = 0.50 (`FILL_PROB`)** — a resting maker is not guaranteed a fill;
  longshots are thin and you often miss the fill you most want. We book *expected* net P&L =
  `FILL_PROB × (payoff − entry − fee)`, the honest EV for a non-always-executable strategy.

**Bootstrap.** Moving-block by contract-day (block = a calendar contract-day, all city-day
groups + all their trades on that date), 10,000 resamples, 95% percentile CI. Blocking by day
prevents double-counting the within-day correlation (one weather realization drives all 6
brackets of a group, and same-date city-days share regimes).

---

## Per-trade provenance (the persisted fields, real examples)

Every trade row carries: `raw_yes_ask`, `no_bid`, `bracket_sum`, `overround_absorbed`,
`member_count`, `implied_prob`, `result`, `price_source_tag="real_ask"`, plus decision/book
timestamps. Four real rows from the full run:

| ticker | decision_T (UTC) | book_ts (UTC) | raw_yes_ask | no_bid | bracket_sum | overround | member_count | implied | result | entry_no | net_pnl | exp_net | tag |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| KXHIGHPHIL-26APR17-B84.5 | 05:13:17 | 05:13:06 | 0.14 | 0.86 | 1.08 | 0.08 | 6 | 0.1296 | no | 0.88 | +0.1165 | +0.0583 | real_ask |
| KXHIGHPHIL-26APR17-B86.5 | 05:13:17 | 05:12:53 | 0.03 | 0.97 | 1.08 | 0.08 | 6 | 0.0278 | no | 0.99 | +0.0065 | +0.0033 | real_ask |
| KXHIGHPHIL-26APR17-T80 | 05:13:17 | 05:13:11 | 0.18 | 0.82 | 1.08 | 0.08 | 6 | 0.1667 | no | 0.84 | +0.1565 | +0.0783 | real_ask |
| KXHIGHPHIL-26APR17-T87 | 05:13:17 | 05:13:15 | 0.03 | 0.97 | 1.08 | 0.08 | 6 | 0.0278 | no | 0.99 | +0.0065 | +0.0033 | real_ask |

(Full per-trade rows + drop stats dump via `--json-out`.)

---

## Sign-discipline note (a near-miss false positive, recorded as a lesson)

The **first** run reported a positive CI [+$0.0151, +$0.0333] that "cleared zero." That was a
**cost-model sign bug**: the entry was booked at `no_bid − 0.02` (a 2¢ price *improvement*),
which literally paid the trader to take the trade and inflated P&L by ~2¢/trade. A spread is a
*cost*: it must *raise* the entry price (`no_bid + 0.02`). With the sign corrected the CI
collapses to straddle zero. Recorded here because it is exactly the prime-directive failure
mode — a positive headline that is an artifact, not an edge. The corrected sign is in the
script and is the only result reported above. (Worth a future invariant: a maker "cost"
haircut must never move the entry price in the trader's favor.)

---

## Tape limitations hit (honest)

1. **T-24h ≈ market open, not deep history.** The archiver subscribed to each daily KXHIGH
   market at a fixed ~04:00 UTC and captured only that market's single trading day, so the
   tape window is ~25–29h. T−24h therefore lands within seconds of tape-open (see book_ts vs
   decision_T above) — we are reading the *opening* book, not a settled mid-life book 24h out.
   The dossier's "24h before close" is satisfiable but only at the earliest available quote.
2. **No snapshot → ask comes from `ticker` BBO, not from delta integration.** Defensible (the
   exchange's own published ask) but it is L1 only; we cannot reconstruct depth at T-24h from
   this tape, so the fill-probability haircut is a modeled assumption, not measured queue depth.
3. **Single 22-day window (2026-04-16 .. 2026-05-07), 8 cities, spring season.** 21 bootstrap
   blocks is thin; one season. Even if a future, larger forward tape nudged the mean positive,
   this sample cannot support it.

## What this closes

A null at real asks, robust across thresholds, on 990 real-ask-priced brackets. Combined with
the dead KXHIGH ensemble, it is strong evidence that the KXHIGH bracket *directional* signal is
real but the *dollar* edge is absent because the ~10¢ overround dominates the few-cent
calibration gap. **Do not fund longshot-fade capital.** If anything in this family is revisited,
it must be on a forward tape with measured depth (to replace the modeled fill haircut) and must
clear zero *strictly* — which it does not here.
