# Q29 / S28 — Post-close settlement-lag taker on decided sports outcomes — VERDICT

Date: 2026-07-15
Probe: `scripts/q29_settlement_lag_probe.py` (read-only over `tape/orderbook_depth/`)
Tests: `tests/test_q29_settlement_lag_probe.py` (19 offline tests, no network)
Settlement cache (fresh, committed): `tape/q29_settlement_cache/settlement.json`
(507 settled markets, all `retention_available: true`; `broker_truth`)

## Verdict: **DEAD-by-convergence** (also below the lookahead-clean adequacy floor)

The post-close settlement-lag taker is **structurally non-existent at real fills**. There is
**zero** fillable winner-side ask in **any** genuinely post-close capture across the entire
committed depth window. The mechanism's premise — a decided game whose market lingers with a
sub-$1 winner-side ask resting to be lifted — does not occur: Kalshi **empties and settles the
book at close**. Every gate that could keep it alive fails, and the CI gate never even applies
(the tradeable population is empty).

This confirms the LOOP-QUEUE honest expectation ("probably DEAD by convergence — Kalshi
auto-settles fast"). A clean kill.

## The load-bearing finding: Q25's "post_close depth" was a timezone confound (lookahead gate 1)

Q25 reported baseball `post_close` n=2,478, median ask-queue 25,884 — the number that motivated
this probe. That bucket was derived from the **sports ticker's HHMM token read as UTC**, which
L46 flagged as tz-ambiguous (league-local, unverifiable, up to ~13h off). Against the **reliable
settlement `close_time`** (`broker_truth` UTC, which for sports clusters at game END per S7a):

| post-close classifier | captures labelled post-close |
|---|---|
| ticker-HHMM-as-UTC (Q25's method) | **2,864** |
| settlement `close_time` (reliable) | **4** |
| of the 2,864 ticker-"post-close", actually PRE-close | **2,860** (99.86%) |

Per-market offset `settlement_close − ticker_HHMM_as_UTC`: median **+7.07h**, max **+24.3h**,
n=296 — i.e. the ticker HHMM understates the real close by ~7h median, exactly the L46 tz
uncertainty. Q25's "post_close" two-sided depth (median queue 25,884, 16% turnover) was the
**in-game live book mislabeled**, not a real post-decision trading window. Using the ex-post
winner over that mislabeled window would have been direct lookahead — this is precisely why
gate 1 is load-bearing.

## The genuinely-post-close population (settlement-anchored)

Three nested windows, source-tagged (`real_ask` entry / `real_bid` backing depth /
`broker_truth` settlement), over 499 settled-joined yes/no markets (224 games) in
`tape/orderbook_depth/dt=2026-07-{07,08,10,11,12,13,14,15}.jsonl`:

| window | captures | games | fillable winner asks | mirror/empty |
|---|---|---|---|---|
| all settled-joined (mostly PRE-close, in-game) | 30,428 | 224 | 30,015 | 413 |
| **post-close (settlement close_time)** | **4** | **2** | **0** | **4** |
| lookahead-clean (≥19h margin = 13h tz + 6h game) | 0 | 0 | 0 | 0 |

The "all settled-joined" row's 30,015 fillable asks (winner_ask median $0.58, edge-net-fee
median +$0.40) is the **lookahead trap**: those are in-game live-book captures where the winner
is known only ex-post. They are NOT post-close and NOT tradeable on public information. The
tradeable window — genuinely post-close — has **4 captures across 2 games, all with empty books**.

All 4 post-close captures (both NPB games), verbatim from the tape:

```
KXNPBGAME-26JUL110500YOMYOK-YOK  result=no   cap=2026-07-11T12:55:57Z  close=2026-07-11T12:54:32Z
KXNPBGAME-26JUL110500YOMYOK-YOM  result=yes  cap=2026-07-11T12:55:57Z  close=2026-07-11T12:54:32Z
KXNPBGAME-26JUL120500YAKHAN-HAN  result=yes  cap=2026-07-12T11:55:18Z  close=2026-07-12T11:54:36Z
KXNPBGAME-26JUL120500YAKHAN-YAK  result=no   cap=2026-07-12T11:55:18Z  close=2026-07-12T11:54:36Z
   all four:  best_yes_bid=None best_yes_ask=None best_no_bid=None best_no_ask=None
              yes_bids=[]  no_bids=[]
```

Captured ~1.4 min and ~0.7 min after the real close, the books are **already fully emptied** —
not even a $1.00 mirror, just no resting orders on either side. There is no winner-side ask to
lift. (These are the only post-close captures at all because the depth collector only snapshots
tickers the sibling sports collector still discovers; once a game closes the ticker drops out,
so a post-close snapshot is a rare timing edge — and when it lands, the book is gone.)

## Gate results (verifier-mandated; none weakened)

- **Gate 1 — LOOKAHEAD: FAIL (population below floor).** Lookahead-clean fillable population = 0
  games at the conservative 19h margin (13h L46 tz uncertainty + 6h max game duration); even the
  lookahead-suspect margin=0 post-close fillable window = 0 games. Below the 10-game floor.
  Date-only/coarse-close (23:59 clamp) exclusion implemented (`is_coarse_close_time`); 0 excluded
  here (all close_times were hour-resolved).
- **Gate 2 — FILLABILITY vs mirror: FAIL.** 0 fillable winner-side asks; all 4 post-close
  captures are empty-book / mirror non-prices (L26/L31). Fillability requires a genuine
  `real_ask` with `0 < ask < 1` AND resting `real_bid` size on the backing ladder (Kalshi posts
  bids-only, so a YES ask is backed by the NO-bid ladder). None qualify.
- **Gate 3 — EXCLUSIONS: applied.** `result ∈ {yes,no}` (drops 8 scalar, L52) AND
  `retention_available` (fresh q29 cache; 0 excluded — all 507 markets retained, within L11).
- **Gate 4 — bootstrap (admissible ≥10 games + opposing cluster, L41; clears_tick_magnitude vs
  taker fee, L27): N/A.** The fillable trade population is empty; no by-GAME CI can be formed.
  This is a **data-adequacy DEAD**, not a CI computed and found ≤ 0.

**price_source_tag on the (non-existent) trade:** entry `real_ask`, backing depth `real_bid`,
settlement value `broker_truth`. No synthetic price was ever treated as fillable (CLAUDE.md L1).

## Hand-verifiable sample math

1. **Fee/edge sanity (used by the probe, would apply IF a fill existed).** A hypothetical
   winner-side lift at `real_ask` $0.90: taker fee `= ceil(0.07·0.90·0.10·100)/100 =
   ceil(0.63)/100 = $0.01`; edge `= settlement($1) − 0.90 − 0.01 = $0.09`. At $0.99 the room is
   gone: fee `= ceil(0.07·0.99·0.01·100)/100 = ceil(0.0693)/100 = $0.01`, edge `= 1 − 0.99 −
   0.01 = $0.00`. (Pinned in `test_settlement_lag_edge_*`.) On the REAL post-close tape
   `winner_ask` is `None` (empty book) for all 4 captures, so no such trade is constructible.

2. **The tz confound, one game.** `KXNPBGAME-26JUL110500YOMYOK`: ticker HHMM `0500` read as UTC
   ⇒ "close" 05:00Z; real settlement `close_time` 12:54:32Z ⇒ offset +7.9h. A capture at 12:55Z
   looks ~8h "post-close" by the ticker (Q25's method) but is only ~1 min past the real close —
   and at that 1-min mark the book is already empty. Multiply this across the window: 2,860 of
   2,864 ticker-"post-close" captures are actually pre-close.

3. **L41 degeneracy note (why even a fillable version would struggle).** Buying the ex-post
   winner always pays $1, so the by-GAME edge population is **all-positive by construction** — it
   can never contain an opposing-sign cluster, making a positive CI mechanically inadmissible
   under L41 (`bootstrap_verdict_admissible`). The probe's synthetic ALIVE test only reaches
   ALIVE-PROVISIONAL by injecting an artificial adverse-fill game. Moot on the real tape (empty
   fillable population), but recorded: the settlement-lag edge is L41-degenerate in principle,
   not just empty in practice.

## Reproduce

```
# offline (verifier mode) — reads the committed q29 cache + committed depth tape:
python scripts/q29_settlement_lag_probe.py
# refresh the settlement cache from Kalshi's free settled endpoint (network), then analyze:
python scripts/q29_settlement_lag_probe.py --refresh-cache
pytest -q tests/test_q29_settlement_lag_probe.py
```

## Lesson candidates (for the kb-distiller)

- **A "post-close/settlement-lag" sports probe must anchor post-close on the settlement
  `close_time` (broker_truth UTC), NEVER on the ticker HHMM token.** Q25's `post_close` n=2,478
  was a tz-confound: 2,860/2,864 (99.86%) of ticker-HHMM-as-UTC "post_close" captures are
  actually PRE-close under the reliable close_time (median offset +7.07h, max +24.3h — the L46
  ~13h tz uncertainty made concrete). Using the ex-post winner over that mislabeled window is
  direct lookahead. This is the settlement-mechanics instance of L46, and it retroactively
  reframes Q25's headline post_close liquidity as the in-game live book mislabeled.
- **Kalshi empties and settles a sports book AT close — there is no post-close resting-quote
  window to pick off.** Across the whole committed depth window only 4 genuinely-post-close
  captures exist (2 games, timing edge-cases ~1 min after close), and all 4 have fully empty
  books (both BBO sides None, ladders []) — not even a $1.00 mirror. The settlement-lag /
  stale-quote-pickoff thesis on Kalshi sports is structurally DOA, the sports analogue of L61's
  "econ ladders close before the print." Closes the S28 slot.
- **The settlement-lag edge is L41-degenerate by construction:** buying the ex-post winner
  always pays $1, so the by-GAME edge population can never contain an opposing-sign cluster, and
  any positive CI is mechanically inadmissible under `bootstrap_verdict_admissible`. Even a
  counterfactual fillable version would fail gate 4 without a genuine adverse-fill population —
  a useful boundary note on where L41's opposing-cluster requirement bites (any "trade the
  known winner" construction, not just S20's resolution-conditioning).
```
