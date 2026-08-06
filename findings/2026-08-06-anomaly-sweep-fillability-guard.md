# The arb scanner's $0.00 legs are now refused — and what is left is not an arb either

`2026-08-06` · research loop, IDLE RUN, idle-run policy **(a)** (convert an UNENFORCED lesson
into an invariant/test) · main-context build · **verdict class: TOOLING + DESCRIPTIVE
data-quality. No registry flip, no bootstrap CI, no kill decision. Still 0 proven edges.**

## What this run converted

`kb/lessons/00-lessons.md` **L288** (2026-08-05) measured a defect and explicitly left its
repair half `UNENFORCED`: `scripts/anomaly_sweep.py::check_monotonicity` filters its legs on
`is None` only and admits on a bare `if edge > 0`, so **43,025 of the 43,038**
`cross_strike_monotonicity` anomalies this project has ever recorded price an `outer_ask ==
$0.00` leg — the ABSENCE of a resting offer — while carrying `price_source_tag: "real_ask"`.
That is the pt1 / prime-directive violation CLAUDE.md forbids, live in the repo's own scanner.

Built this run (the write-path guard L288 asked for), as ONE shared site rather than three
private copies (L36/L102 twin discipline):

- `core/pricing.py::is_fillable_ask(price)` — `MIN_FILLABLE_ASK_DOLLARS = 0.01`, Kalshi's
  minimum quotable tick. `$0.00`, `None`, NaN and unparseable inputs are refused; a
  `_dollars` string is coerced, not refused. Deliberately NOT capped above $1.00 (documented).
- `core/pricing.py::is_material_arb_edge(edge)` — replaces the bare `edge > 0` admission test.
  `ARB_EDGE_RESIDUE_FLOOR_DOLLARS = 1e-9`, the same magnitude as `core.bootstrap
  .SUB_TICK_RESIDUE_FLOOR` (L236). This is a float-residue filter, NOT L27's
  economic-significance gate (that one belongs to a verdict, not to a scanner's admission test).
- `scripts/anomaly_sweep.py` — all THREE checks (`check_bracket_arb`,
  `check_monotonicity`, `check_cross_event_implication`) now route every leg through
  `is_fillable_ask` and every edge through `is_material_arb_edge`. Refusals are **counted and
  persisted** (`n_unfillable_leg_refusals`, `n_residue_edge_refusals`, additive to
  `anomaly_sweep.v1`; every pre-existing field unchanged in shape and meaning), so
  `n_anomalies: 0` can no longer be misread as "the market was clean" when the truth is
  "every candidate leg was unquoted".

**The guard cannot cost a real arb.** A leg with no resting offer cannot be bought at any
price; refusing it removes imaginary money only. It is also **necessary, not sufficient**:
`/markets` carries no `*_ask_size` field at all, and where size IS observable
(`tape/universe_sweep/`, L96/L105) ~96% of nonzero asks still show zero size. This guard proves
the price sits on the tradeable cent grid — nothing more.

## Replay over all committed tape (frozen window `dt <= 2026-08-04`, 26 capture-days)

Re-scoring every committed `cross_strike_monotonicity` record through the new predicates
(`pytest tests/test_anomaly_sweep.py -k acceptance`, which pins each number below):

| quantity | value |
|---|---|
| recorded anomalies | **43,038** |
| persisted `edge` recomputes exactly from its own two legs | 43,038 (0 disagreements) |
| refused — leg not on the tradeable price grid (`$0.00`) | **43,025 (99.9698%)** |
| refused — edge is sub-tick float residue, after the above | 0 (all 1,480 also carry a $0.00 leg) |
| **survive both guards** | **13 records / 6 distinct ticker pairs / 7 distinct (pair, price) rows** |

The residue guard is **not** redundant even though it adds nothing on this tape: **87** of the
9,801 fully-quoted cent-grid pairs net exactly $0.00 and surface as `1.73e-17` — e.g. a $0.01
outer ask against a $0.97 inner NO ask. Without the floor the fillability guard alone would
still admit those as arbs (`tests/test_pricing_fillable_ask.py`).

## The second finding: after the $0.00 legs are gone, 100% of the remainder is a premise failure

The 13 survivors are not arbs. `check_monotonicity` assumes that markets sharing an
`event_ticker` and a `strike_type` are **nested strikes on ONE underlying** (P(≥80°) can never
exceed P(≥70°)). Kalshi also packs **multiple SUBJECTS into one event**, and the check sorts
those by `floor_strike`/`cap_strike` as if they were rungs of one ladder:

| survivor pair | what the two markets actually are |
|---|---|
| `KXATPGSPREAD-26JUL17COLVAC-VAC2` vs `-COL2` | two DIFFERENT tennis players' game-spread markets |
| `KXMLBHIT/HRR/TB-26JUL181610SDKC-KCVPASQUANTINO9-*` vs `-KCBWITT7-*` | two DIFFERENT batters' prop markets (3 pairs) |
| `KXRAIN-26JUL23-NYC` vs `-NOLA` and vs `-DEN` | three DIFFERENT CITIES' rain markets |

Corroborated independently in `tape/universe_sweep/`, which carries the market titles: e.g.
event `KXATPGSPREAD-26JUL22STRNAV` contains both *"Will Navone win at least 2.5 more games than
Struff?"* and *"Will Struff win at least 1.5 more games than Navone?"* — opposite-direction
claims under one `event_ticker`, both `greater`-typed. Buying YES(subject A) + NO(subject B) is
a **naked directional bet**, not a guaranteed ≥$1 payout.

So, over 26 committed capture-days: **43,038 recorded "anomalies" → 43,025 unbuyable legs → 13
cross-subject false positives → ZERO verified fillable arbs.** `check_bracket_arb` and
`check_cross_event_implication` have recorded zero hits of any kind over the same window
(check 3's hand-curated implication graph proves nesting by audited rules text, so it does not
share the defect).

## What this does and does not change

- **Does:** the scanner can no longer persist an imaginary edge on an unquoted leg, and every
  refusal is now counted on the record. Committed tape is untouched — it is append-only, and
  the historical records stay exactly as captured, now with a re-runnable replay that says what
  they were worth.
- **Does NOT:** flip any registry status. S3 stays `data-collecting` and S15 stays
  `data-collecting`; a kill is verdict-class and needs the two-agent rule, which this run could
  not satisfy (no independent verifier available in-session). A dated descriptive note was
  added to both rows so the stale "0 hits in 3 capped passes" reading cannot mislead the next
  run. The nesting repair is filed as **Q53**, not attempted here: a correct fix needs a
  structural subject-identity test validated against a real ladder corpus, and a ticker-suffix
  heuristic is exactly the shortcut Q1's own note warns against.

## Reproduce

```
pytest tests/test_pricing_fillable_ask.py tests/test_anomaly_sweep.py -q
pytest tests/test_anomaly_sweep.py -k acceptance -q      # the replay over committed tape
```

Provenance: every number above is computed from committed `tape/anomalies/` (`price_source_tag:
"real_ask"` as persisted by the scanner) over the closed window `dt <= 2026-08-04`; the survivor
anatomy is corroborated against `tape/universe_sweep/` market titles. No network, no orders, no
credentials.
