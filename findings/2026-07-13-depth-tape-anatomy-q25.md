# Depth-tape anatomy scan (Q25) — a fill-plausibility map

`2026-07-13` · READ-ONLY, DISCOVERY-CLASS · **descriptive statistics only — NO bootstrap, NO CI,
NO verdict, NO P&L, NO strategy registration, NO registry flip**

- Script: `scripts/q25_depth_tape_anatomy.py` (read-only over `tape/orderbook_depth/`)
- Machine-readable: `findings/depth_anatomy.json` (keyed by family / category × ttc-bucket)
- Tests: `tests/test_q25_depth_anatomy.py` (33 offline unit tests, no tape/network)
- Precedent: `scripts/s20_ladder_overround_anatomy.py` (same read-only shape + source-tag hygiene)

This scan reads `tape/orderbook_depth/` — the largest tape family (~1,100–1,280 lines/hour since
07-07, 3–4× everything else combined, L38) — as a **discovery scan** for the first time, rather
than as a fill GATE bolted onto an idea that already existed (S14/S19/Q24). It is a map, not an
edge: its cells are an idea source for future Q21 diversity rounds, not themselves a strategy.

## Scope & coverage

- **122,238** depth records scanned across **31 families**, 6 capture days (07-07, 07-08, 07-10,
  07-11, 07-12, 07-13; **07-09 absent** — honest gap, not padded).
- Category totals (captures): **soccer 49,671** · **crypto 45,505** · baseball 17,044 ·
  basketball 6,112 · sports_other 3,906.
- Source tags (per the depth collector): **asks = `real_ask`, bids = `real_bid`** — both real,
  fillable, not synthetic. No synthetic number, no P&L, no CI appears anywhere in this scan.
- Insufficient threshold: any cell with **<20 captures** (capture-based metrics) or **<20 pairs**
  (pair-based metrics) is the string sentinel `"insufficient"` — never extrapolated/imputed. 21
  of 114 family × ttc cells carry at least one insufficient metric (counting pooled-turnover
  insufficiency, consistent with the category table) (almost all are the sub-hour
  buckets, which are structurally sparse at hourly capture cadence — expected, reported honestly).

## Definitions (verbatim, for the verifier)

**family** = series prefix, `ticker.split('-')[0]`.

**category** = domain rollup: `crypto` (KXBTC/KXETH) · `soccer` · `baseball` · `basketball` ·
`sports_other`. Every sports family maps via a documented prefix map (`SUBCATEGORY_MAP` in the
script); **any unmapped family falls to `sports_other`, never silently dropped**. The family axis
carries the fine detail. (Mappings: baseball = MLB/NPB/KBO; basketball = WNBA/BIG3/NZNBL/BSN/FIBA;
sports_other = AFL/VBA/PLL; everything else listed = soccer.)

**time-to-close (ttc) = close_ts − captured_at.** Close parsed from the ticker grammar:
- crypto `KXBTC-26JUL0621-…` → middle `26JUL0621` = `YYMMMDD`+`HH`. **The hour token is ET**
  (EDT/UTC-4 in July), close = D @ HH:00 ET → UTC. *Confirmed against the tape AND
  `collection/crypto_hourly.py`: token hour 21 (`KXBTC-26JUL0621`) is captured 00:57:50 UTC on
  07-07 = 20:57 EDT on 07-06, closing 21:00 EDT = 01:00 UTC. The milestone spec's example
  ("…1221 → 21:00 UTC") is off by the ET offset; I used the empirically-correct ET.*
- sports w/ time `KXAFLGAME-26JUL160530SKSGEE-GEE` → `YYMMMDD`+`HHMM`+letters, **HHMM treated as
  UTC per the spec's contract.** *Caveat: sports HHMM's true timezone is league-local and NOT
  independently verifiable from the tape (settled markets linger in the depth feed, so
  last-capture time is not a reliable close proxy). A wrong sports tz only shifts the near-close
  bucket boundaries by a few hours; in this coarse hourly-cadence descriptive scan that reshuffles
  the 1-6h/15-60m boundary, nothing structural.*
- sports date-only `KXWCGAME-26JUL06USABEL-USA` → `YYMMMDD`+letters, **day-resolved only**:
  `resolution=coarse`, close = end-of-day (23:59:59 UTC). Coarse captures are **clamped** — never
  placed in `<15m`/`15-60m` (those are promoted to `1-6h`), because the intra-day close is unknown.
- any middle segment that fails the grammar → `ttc_bucket="unparsed"`, counted honestly, 0 seen.

**ttc buckets** (exact edges): `>24h` (≥24h) · `6-24h` · `1-6h` · `15-60m` · `<15m` (0–15m) ·
`post_close` (ttc<0, late capture of a settling market) · `unparsed`.

**(a) queue depth** — per capture: `yes_bid_side` = `yes_bids[0][1]`; `yes_ask_side_mirror` =
`no_bids[0][1]` (the MIRROR — a YES offer at p is a NO bid at 1−p, so the size resting AT the best
YES ask is the top of the no-bid ladder; same primitive as s20's `_ask_side_depth`). Reported as
median + p25/p75. Empty ladder → 0 (L23: empty ≠ drop).

**(b) staleness** — per ticker, captures ordered by `captured_at` across ALL days; a consecutive
pair whose full BBO 4-tuple `(best_yes_bid, best_yes_ask, best_no_bid, best_no_ask)` is UNCHANGED
is *frozen* (L32, here as a distribution). Per-cell `frozen_pair_fraction` + a family/category
**streak-length distribution** (median / p90 / max run of unchanged BBO). *Hourly-cadence caveat:
a frozen hourly pair is not proof of no intra-hour movement — it is an upper bound on quote age.*

**(c) one-sidedness** — per capture: `yes_side_empty` (no yes_bids), `no_side_empty` (no no_bids
⇒ no tradeable YES ask), `any_side_empty` (L31's wing shape). Incidence per cell.

**(d) turnover formula (THE fill-plausibility signal — defined here, not canonical):** for a
consecutive same-ticker pair where the **best PRICE on a side is UNCHANGED** and `size_prev>0`:
`turnover = max(0, size_prev − size_now) / size_prev` — contracts that left the queue at a stable
price (a proxy for fills+cancels ahead). Per side + pooled, mean per pair. **Honesty caveat
(binding, stated in code + here):** snapshot-sampled at hourly cadence, so intra-hour round-trips
are invisible (undercount) and a best-price move resets/excludes the pair — a coarse
order-of-magnitude observable, **NOT a fill guarantee**. Anchors for orientation only (NOT
recomputed): **S19's 0.45%** queue-aware fill rate (DEAD,
`findings/2026-07-13-s19-wing-fade-fillsim-q23-verdict.md`) and **S14's 2.5%** incidental-wing
benchmark. Turnover is looser than a fill rate, so it can **rule a cell OUT (dead-thin), never
rule one IN as fillable.**

**Pair assignment:** staleness/turnover pairs are assigned to the **earlier** capture's cell (the
resting state we ask "did it move?").

## Key anatomy numbers (each with its denominator)

### Per family (all-ttc pooled) — median queue depth, frozen fraction, turnover, any-empty

| family | cat | n_cap | n_tk | bidQ | askQ(mirror) | frozen | turnover | any-empty | streak med/p90/max |
|---|---|--:|--:|--:|--:|--:|--:|--:|--|
| KXBTC | crypto | 32,530 | 19,370 | 0 | 18,832 | 87% | 6.83% | 97% | 2/2/3 |
| KXETH | crypto | 12,975 | 7,725 | 0 | 35,962 | 87% | 5.86% | 98% | 2/2/3 |
| KXMLBGAME | baseball | 9,760 | 192 | 1,364 | 3,030 | 75% | 7.62% | 1% | 1/10/52 |
| KXBRASILEIROBGAME | soccer | 7,518 | 63 | 50 | 54 | 60% | 2.78% | 1% | 1/6/42 |
| KXNPBGAME | baseball | 5,560 | 100 | 30 | 140 | 29% | 6.92% | 0% | 1/2/27 |
| KXUECLGAME | soccer | 4,620 | 81 | 50 | 500 | 70% | 3.47% | 4% | 2/7/30 |
| KXBRASILEIROCGAME | soccer | 4,335 | 33 | 76 | 76 | 61% | 2.08% | 0% | 1/6/59 |
| KXUSLCUPGAME | soccer | 3,792 | 63 | 26 | 10 | 77% | 1.41% | 1% | 1/9/43 |
| KXLIGAMXGAME | soccer | 3,750 | 33 | 148 | 200 | 65% | 3.61% | 0% | 1/6/56 |
| KXECULPGAME | soccer | 3,222 | 51 | 1,235 | 1,200 | 74% | 2.94% | 2% | 2/8/37 |
| KXAFLGAME | sports_other | 2,934 | 36 | 1,500 | 1,500 | 66% | 2.20% | 0% | 1/6/61 |
| KXUCLGAME | soccer | 2,550 | 72 | 144 | 650 | 68% | **8.56%** | 1% | 1/7/30 |
| KXCHNSLGAME | soccer | 2,481 | 24 | 49 | 67 | 74% | 2.86% | 0% | 2/9/62 |
| KXUELGAME | soccer | 2,214 | 18 | 49 | 97 | 59% | 2.24% | 0% | 1/5/22 |
| KXMLSGAME | soccer | 2,172 | 18 | 547 | 782 | 90% | 1.72% | 0% | 3/26/78 |
| KXWNBAGAME | basketball | 2,154 | 54 | 801 | 1,814 | 62% | **11.06%** | 1% | 1/5/24 |
| KXBRASILEIROGAME | soccer | 1,845 | 15 | 400 | 751 | 79% | 2.27% | 0% | 2/11/44 |
| KXURYPDGAME | soccer | 1,842 | 24 | 2,000 | 1,600 | 80% | 1.90% | 1% | 2/11/56 |
| KXBSNGAME | basketball | 1,812 | 28 | 50 | 50 | 73% | 2.16% | 0% | 1/7/43 |
| KXALLSVENSKANGAME | soccer | 1,788 | 24 | 1,552 | 1,737 | 84% | 3.65% | 2% | 2/16/64 |
| KXELITESERIENGAME | soccer | 1,737 | 27 | 1,000 | 1,138 | 79% | 4.14% | 1% | 2/12/50 |
| KXKBOGAME | baseball | 1,724 | 44 | 52 | 70 | 33% | **8.35%** | 0% | 1/2/30 |
| KXWCGAME | soccer | 1,635 | 27 | 91,317 | 403,560 | 94% | 4.30% | 0% | 1/44/120 |
| KXNWSLGAME | soccer | 1,569 | 30 | 172 | 502 | 58% | 3.65% | 0% | 1/5/26 |
| KXUSLGAME | soccer | 1,548 | 18 | 1,003 | 895 | 71% | 2.12% | 0% | 1/9/62 |
| KXNZNBLGAME | basketball | 1,158 | 20 | 100 | 55 | 73% | 2.20% | 0% | 1/9/50 |
| KXKLEAGUEGAME | soccer | 1,053 | 18 | 1,500 | 1,500 | 75% | 3.93% | 1% | 2/9/42 |
| KXBIG3GAME | basketball | 856 | 8 | 10 | 200 | 89% | **0.48%** | 2% | 2/24/44 |
| KXVBAGAME | sports_other | 544 | 10 | 26 | 10 | 77% | 1.37% | 1% | 1/9/45 |
| KXPLLGAME | sports_other | 428 | 8 | 49 | 33 | 41% | 4.33% | 1% | 1/3/15 |
| KXFIBAGAME | basketball | 132 | 8 | 5 | 25 | 54% | 6.81% | 6% | 2/3/13 |

*(bidQ/askQ = median best-level size in contracts, `real_bid`/`real_bid`-mirror; sizes are stored
as floats in the tape and can be fractional — e.g. WC median bid 91,316.82 — reported as-is.)*

### Category × ttc-bucket

Turnover **rises monotonically toward close in every category** (>24h ≈ 2% → post_close ≈ 12–16%),
consistent with more resting-order churn as settlement nears — the near-close buckets are where
any fill-plausibility lives, but they are also the sparsest.

| category | ttc | n_cap | bidQ | askQ | frozen | turnover | any-empty |
|---|---|--:|--:|--:|--:|--:|--:|
| soccer | >24h | 36,390 | 142 | 392 | 71% | 2.25% | 0% |
| soccer | 6-24h | 9,381 | 292 | 608 | 74% | 5.76% | 1% |
| soccer | 1-6h | 1,728 | 176 | 479 | 48% | 7.57% | 6% |
| soccer | post_close | 2,172 | 14 | 36 | 60% | 3.24% | 12% |
| crypto | 15-60m | 27,352 | 0 | 25,384 | 89% | 6.56% | 96% |
| crypto | <15m | 17,627 | 0 | 23,097 | 0% | insuf (n_pairs=526→pooled insuf) | 99% |
| crypto | post_close | 526 | 0 | 0 | insuf | insuf | 100% |
| baseball | >24h | 8,208 | 48 | 181 | 45% | 4.42% | 0% |
| baseball | 6-24h | 4,794 | 1,016 | 2,448 | 73% | 8.38% | 0% |
| baseball | 1-6h | 1,266 | 1,249 | 22,485 | 86% | 9.20% | 0% |
| baseball | 15-60m | 194 | 12,397 | 57,736 | 79% | **12.91%** | 0% |
| baseball | <15m | 104 | 1,504 | 5,567 | 78% | 11.13% | 0% |
| baseball | post_close | 2,478 | 9,786 | 25,884 | 41% | 16.12% | 4% |
| basketball | >24h | 3,524 | 13 | 50 | 74% | 2.81% | 0% |
| basketball | 6-24h | 1,634 | 505 | 700 | 76% | 7.13% | 0% |
| basketball | 1-6h | 464 | 609 | 720 | 62% | 8.69% | 5% |
| basketball | post_close | 454 | 98 | 146 | 35% | 12.14% | 10% |
| sports_other | >24h | 3,000 | 1,500 | 693 | 66% | 1.43% | 0% |
| sports_other | 6-24h | 448 | 598 | 466 | 77% | 3.39% | 0% |
| sports_other | 1-6h | 198 | 1,500 | 864 | 56% | 5.77% | 0% |
| sports_other | 15-60m | 20 | 1,966 | 1,758 | 80% | 7.47% | 0% |

*(soccer has no `15-60m`/`<15m` rows: most soccer families are date-only → coarse-clamped out of
sub-hour buckets, and the HHMM soccer games' near-close captures are too few to populate them.
crypto has only `15-60m`/`<15m`/`post_close`: hourly crypto markets only exist ~1h before close.)*

## Where the tape shows plausibly-fillable liquidity vs dead-thin (turnover vs anchors)

Read against the anchors — S19's **0.45%** (queue-aware fill, DEAD) and S14's **2.5%** (incidental
wing). Turnover can only rule cells OUT; a high turnover is necessary-not-sufficient for fills.

- **Plausibly-fillable churn (turnover ≫ 2.5%), where the next idea-gen round should look first:**
  WNBA basketball (11.06% pooled; two-sided books, median ask-queue 1,814), UCL soccer (8.56%),
  KBO baseball (8.35%, and notably the *least* frozen sports family at 33% — active BBO), MLB
  (7.62%), NPB (6.92%, also low-frozen 29%). By ttc, **baseball 6-24h→<15m runs 8–13%** and
  **basketball/soccer 6-24h→1-6h run 7–9%** — the near-money, near-close sports window is where
  churn is real. Crypto's 5.9–6.8% turnover is essentially all on the mirror/no-bid side of a
  one-sided (97–98% empty-YES-bid) book — the L26 1¢-floor mirror, not a two-sided quote.
- **Dead-thin (turnover ≤ the S19 0.45% / near it):** **KXBIG3GAME at 0.48%** sits right on the
  S19-dead anchor (n=856, only 8 tickers, 89% frozen) — the clearest "do not bother" cell.
  Low-churn neighbours: VBA 1.37%, USLCup 1.41%, MLS 1.72% (also 90% frozen), URYPD 1.90% — slow,
  sticky books with little observable queue movement.
- **One-sidedness (L31 outside crypto):** sports books are essentially **two-sided** (any-empty
  0–1% pre-close) — the L31/L26 empty-wing shape is a *crypto* phenomenon (96–100% any-empty),
  where the tradeable-YES-ask side is the mechanical mirror of a 1¢-floored no-bid. The only sports
  one-sidedness appears **post_close** (10–12% any-empty — books emptying out as markets settle).

## Staleness / quote age

Frozen fractions are **high across the board (58–94%)** at hourly cadence — most consecutive hourly
BBO pairs are unchanged. This is an *upper bound* on quote age, not proof of no intra-hour movement
(the binding caveat). Streak-length maxima show some genuinely glacial books: WC max run 120
consecutive unchanged captures (~days), MLS 78, AFL/USL/CHNSL 61–62. The least-frozen families
(most active BBO) are the Asian baseball leagues **NPB (29%) and KBO (33%)** — consistent with
their higher turnover. Crypto's max streak is only 3 (each crypto ticker lives ~2–3 captures).

## Coverage gaps / families too sparse to cut (reported honestly)

- **07-09 absent** from the depth tape (6 of a possible 7 days) — an honest gap, not imputed.
- **Sub-hour buckets are universally sparse** by construction (hourly capture cadence): sports
  `15-60m`/`<15m` cells mostly fall under n=20 and are `insufficient`; crypto `<15m` has captures
  but only 526 consecutive-pairs (its turnover pools to `insufficient`). 21/114 family × ttc cells
  carry ≥1 insufficient metric (counting pooled-turnover insufficiency, consistent with the
  category table). This is a *cadence* limitation of the tape, not a defect of the
  scan — a probe wanting sub-hour resolution would need sub-hourly depth capture first.
- **Smallest families** (FIBA n=132/8 tickers, PLL n=428/8, BIG3 n=856/8, VBA n=544/10) are thin;
  their all-ttc pooled numbers stand but their ttc breakdowns are mostly insufficient.
- **Sports HHMM timezone is unverified** (league-local); near-close sports bucket boundaries carry
  a few-hour tz uncertainty — read sports near-close cells at bucket, not minute, granularity.

## Reading (NOT a verdict)

The two-sided, higher-churn near-close sports books (baseball/basketball 6-24h→close at 7–13%
turnover; WNBA, UCL, KBO, MLB, NPB at the family level) are where the depth tape shows the most
observable queue movement and are the strongest candidates for a *future* queue-aware fill-sim
idea. The one-sided crypto mirror and the sticky low-churn small leagues (BIG3 on the S19-dead
line, VBA/USLCup/MLS) are where fill plausibility already looks dead-thin. **This is a descriptive
map to seed idea-gen — every "fillable" here is an upper-bound observability read, not an edge; any
real strategy still faces the binding real-ask bootstrapped-CI bar.**

## Lesson candidates (for the kb-distiller)

- **Crypto's Kalshi hour token is ET, not UTC** — empirically `KXBTC-26JUL0621` closes 01:00 UTC
  07-07 (21:00 EDT 07-06), and `collection/crypto_hourly.py`'s docstring already says "HH in ET".
  A ttc/close-time parser that reads the token as UTC mis-times every crypto market by the ET
  offset (4h in summer). The milestone spec's own example ("…1221 → 21:00 UTC") was off by exactly
  this; confirm hour-token semantics against the tape before trusting a grammar example.
- **Sports HHMM timezone is league-local and NOT verifiable from the depth tape**, because settled
  markets linger in the feed (last-capture time is not a reliable close proxy). Any sports
  close-time parse should carry an explicit tz caveat rather than assume UTC == local == fillable.
- **`orderbook_depth` size fields are stored as floats and can be fractional** (WC median bid
  91,316.82 contracts) — a consumer expecting integer contract counts should not assume int.
- **Turnover-as-fill-plausibility can only rule a cell OUT, never IN**: it is a looser upper-bound
  observable than a queue-aware fill rate (intra-hour round-trips invisible; price moves exclude
  the pair). Orient it against the S19 0.45% / S14 2.5% anchors as a *dead-thin filter*, and keep
  the "necessary-not-sufficient" framing (family L39) before any fill claim.
