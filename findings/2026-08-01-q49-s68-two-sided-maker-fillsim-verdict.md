# Q49 / S68 — Two-sided both-bid overround-capture maker fill-sim: DEAD (edge) — **PROVISIONAL**

`2026-08-01` · LOOP-QUEUE.md **Q49** · registry **S68** · probe
`scripts/q49_two_sided_maker_fillsim.py` · tests `tests/test_q49_two_sided_maker_fillsim.py`
(44, offline synthetic fixtures — no network, no orders, no auth) · **verifier: NOT RUN —
the research-loop harness for this run exposed no subagent-dispatch tool, so the two-agent
verdict rule is UNSATISFIED. The verdict is recorded PROVISIONAL and the S68 registry row is
NOT flipped.** · every price below carries its source tag.

## Status of this document

Per protocol v3's two-agent verdict rule, a registry flip is never one agent's word alone. This
run could not dispatch an independent `verifier`. What was done instead, and what it is *not*
worth: the headline cell was re-derived a second time by **independent code written from the
tape up** (`/tmp` scratch, not committed) that does not import a single function from the probe
— it reproduced the counts, the fill rates, the both-fill net, the per-attempt mean and the
adverse-selection rates **to the digit** (only the bootstrap CI bound moved in the 4th decimal,
from dict-ordering in the resample draw). That rules out a transcription or indexing bug. It
does **not** substitute for an adversarial second agent, because the same author chose the
population, the fill model and the gates in both passes. **S68 therefore stays at `idea` in
`kb/strategies/00-index.md` until a verifier confirms.**

## The question and the binding gate

S68 was registered at `idea` stage on 2026-08-01 (Q21 round #19) as the first idea-stage
survivor since S34. Mechanism: on a 2-outcome game moneyline book whose two-sided spread is at
least 2× the flat maker fee, rest **BOTH** a YES bid and a NO bid; if both fill you own both
sides for `yes_bid + no_bid` < \$1 and exactly one side settles \$1. The idea-stage arithmetic
(mean yes-spread 7.31¢, `yes_bid+no_bid` mean 0.927 and < \$1 for 100% of 205 events) gives
**+7.31¢ gross / +5.31¢ net** of the 2¢ two-sided maker fee.

The registration was explicit that this is **not an edge — a deterministic gross overround with
a defined binding test**, and that the entire edge lives in the unmodeled fill question. Q49 is
that test. Falsifiable question: **does the both-bid overround survive a queue-aware
both-sides-fill simulation with adverse selection modeled rather than assumed away?**

## The structural fact that reframes the whole probe

**If both legs fill, adverse selection cannot touch the P&L.** You hold one YES and one NO on
the same binary market; exactly one settles \$1 *regardless of the outcome*. The both-fill P&L
is arithmetically deterministic:

    1 − yes_bid − no_bid − fee(yes_bid) − fee(no_bid)

So conditioning the verdict on "both filled" would reproduce the idea-stage number by
construction and prove nothing (Q49 gate 3 / L5). Adverse selection enters in exactly one place:
the attempts where **only one leg fills**, which is a naked directional position, not the capture
(Q49 gate 2). The deployable unit of account is therefore the **per-attempt** P&L over the four
exhaustive cases — both fill / YES only / NO only / neither — and that is this probe's binding
metric. The both-fill-conditioned cut is reported as the item's literal secondary, and it
behaves exactly as the arithmetic demands.

## Method

Read-only, **fully offline** over committed tape (both legs are committed, so a verifier re-runs
with no credentials and no cache refresh):

- **Settlement** — `tape/settlement_ledger/` (`broker_truth`), 10,605 settled tickers, binary
  `yes`/`no` results only (L52: a `scalar` result is never coerced into a two-outcome
  settlement). Settlement **gates the payout, never a fill** (L50/G1).
- **Book** — `tape/orderbook_depth/` `yes_bids` / `no_bids` price-time-priority ladders
  (`real_bid`). Both resting bids live on the **same** binary market's book — the YES bid on
  `yes_bids`, the NO bid on `no_bids`. On a binary book `yes_ask ≡ 1 − best_no_bid`, so the
  yes-spread **is** the both-bid overround: the gate and the payoff are the same quantity by
  construction, not by luck.
- **Population** — settled series ending in `GAME`, excluding the `KXMVE*` multi-game /
  cross-category families (the L31 nominal-wing artifact). Entry requires a genuinely two-sided
  snapshot (`yes_bid>0 & no_bid>0`) with yes-spread ≥ 2¢ **and at least one later pre-close
  snapshot** — an entry with nothing after it cannot be simulated at all.
- **Fill (L39-free, never a candle print)** — `queue_ahead` = resting size at price ≥ ours on
  that ladder at entry; fills accumulate the tape's own observed **queue departures** at levels
  ≥ our price across consecutive snapshots (the L48 turnover proxy). Cancels ahead count as
  advancing us and new bids jumping ahead are ignored — deliberately **generous**, so a
  below-floor fill rate is a robust dead-thin OUT, never a fill guarantee.
- **Fees** — one flat maker fee **per filled leg**, from `core.pricing.fee_per_contract` at
  `MAKER_FEE_RATE` (L18/L30, never hand-rolled). Two legs, two fees, 2¢ total.
- **Sanctioned helpers** — ISO parsing via `core.timeutil.parse_iso_utc` and the binary/scalar
  settlement decision via `core.settlement.is_binary_result` / `normalize_result`. The first draft of
  this probe used a raw `datetime.fromisoformat` and `scripts/invariants.py --full` went RED on
  `no_raw_datetime_fromisoformat` (L136/L150) — the gate catching exactly the bug class it exists for.
  Every headline number below is byte-identical before and after that fix.
- **Bootstrap** — block-bootstrap by **GAME-SERIES** (L6/L41: strikes and games inside one
  series are correlated draws), routed through `bootstrap_verdict_admissible` **and**
  `clears_tick_magnitude`. A by-GAME bootstrap is reported as a secondary.

### Two explicit fill models (Q49 gate 3 — adverse selection modeled, not assumed away)

| model | fill condition | role |
|---|---|---|
| **A** `queue_only` | departures clear the queue ahead of us | optimistic upper bound; **blind to price movement** |
| **B** `queue_price_through` | A, **and** the touch on that side later prints strictly *below* our resting price | **BINDING** — the book actually repriced down through our level, i.e. we were lifted by flow moving against the side we bought |

On top of both, adverse selection is **measured, not assumed**: P(the side we own settles
against us \| that side filled alone) is compared against the population base rate.

## Result — the binding cell

Entry policy `late` (the latest qualifying snapshot, which reproduces the idea-stage regime:
mean yes-spread 4.09¢, mean `yes_bid+no_bid` **0.9591**, **< \$1 for 100.0%** of attempts), gate
`min_spread = 0.02` (S68's own), model **B**. Population **564 attempts / 18 game series /
316 games** — clears the L41 ≥10-series floor.

| cut | mean | 95% CI | n_units | admissible | clears tick |
|---|---|---|---|---|---|
| **PER-ATTEMPT (deployable, binding)** | **−\$0.0923** | **[−0.1311, −0.0423]** | 18 series | yes | **no** |
| both-fill-conditioned (item's literal secondary) | +\$0.0115 | [+0.0043, +0.0365] | 17 series | yes | no |
| per-attempt, by GAME (secondary unit) | −\$0.0923 | — | 316 games | — | — |

**The per-attempt CI sits entirely below zero.** This is a falsification, not a straddle.
17 of 18 series have a negative mean; the single positive series is `KXWCGAME` with n=2.

Prices: fills `real_bid`, settlement `broker_truth`.

### Where the money goes

| outcome | n | share | mean P&L |
|---|---|---|---|
| both legs fill | 123 | 21.81% | **+\$0.0115** (gross overround +3.15¢ − 2¢ fees) |
| YES leg only | 126 | 22.34% | −\$0.2094 |
| NO leg only | 121 | 21.45% | −\$0.2240 |
| neither fills | 194 | 34.40% | \$0.0000 |

The both-fill leg pays exactly what the idea-stage arithmetic promised. It is simply **swamped**:
247 single-leg fills at ≈−21¢ against 123 both-fills at +1.15¢. You cannot condition on both
filling, and the 44% of attempts that half-fill are the ones that decide the strategy.

### The adverse selection, measured

| quantity | value | population base rate | ratio |
|---|---|---|---|
| P(settles YES \| **YES leg only** filled, n=126) | **0.127** | 0.418 | **0.30×** |
| P(settles NO \| **NO leg only** filled, n=121) | **0.248** | 0.582 | **0.43×** |

This is textbook adverse selection and it is severe: the leg that fills alone settles in our
favour **two to three times less often** than the base rate. The mechanism S68's own registration
named — *"the side that fills is disproportionately the side about to lose"* — is confirmed
empirically on real book tape, not assumed.

Median `queue_ahead` at entry: **500 contracts (YES side) / 707 (NO side)** — squarely consistent
with Q24's median-485-ahead binding-risk finding on the same tape family.

### The entry-policy confound (stated, because it moves the headline)

`late` entry is the cell that reproduces the idea-stage *price* regime, but it also truncates the
observation window: **median 3 post-entry snapshots (mean 11.3, p10 = 1)** versus **median 65
(mean 64.0)** under `first`. With a handful of snapshots left before the close, the book makes
essentially one more move, whichever way it goes fills exactly one of our two bids, and that leg
is by construction the losing one. Part of the −\$0.0923 is therefore *short-horizon* structure,
not adverse selection alone — a verifier should attack this number on exactly that ground.

So the two cells are reported as **co-binding**, not headline-plus-footnote:

| cell | window (median post-entry snapshots) | per-attempt mean | 95% CI | verdict |
|---|---|---|---|---|
| `first` + model B — the fairer implementation of "rest both and leave them" | 65 | +\$0.0011 | [−0.0533, +0.0797] | **no edge** (straddles zero) |
| `late` + model B — the idea-stage price regime | 3 | −\$0.0923 | [−0.1311, −0.0423] | **falsified** (fully below zero) |

The economics of the short window are real, not an artifact — resting into a close genuinely
means eating the last move — but the *magnitude* at `late` should not be quoted as the clean
measure of adverse selection. **The claim that survives both readings, and that the verdict rests
on, is the weaker and more defensible one: no cell produces an admissible CI > 0 that clears the
tick-magnitude gate.**

### The non-circularity check (this matters)

Model B's fill condition is *definitionally* correlated with adverse price movement, so a
skeptic is right to ask whether the kill is baked in. It is not. **Model A is blind to price
movement entirely** — it fills on queue departures alone, with no reference to which way the
book went — and it still fails:

| entry | model | per-attempt mean | 95% CI | admissible | clears tick | verdict |
|---|---|---|---|---|---|---|
| late | A `queue_only` | +\$0.0083 | [−0.0014, +0.0277] | yes | **no** | DEAD |
| late | B `queue_price_through` | −\$0.0923 | **[−0.1311, −0.0423]** | yes | no | **DEAD** |
| first | A `queue_only` | +\$0.1617 | [+0.0721, +0.3108] | **no** (`no_opposing_unit`) | yes | DEAD (L41 degenerate) |
| first | B `queue_price_through` | +\$0.0011 | [−0.0533, +0.0797] | yes | no | DEAD |

Four cells, four failures, by three different routes: a CI fully below zero (the binding cell),
a CI straddling zero (both `first`-entry cells and the price-movement-blind `late` cell), and an
**L41-degenerate** bootstrap where all 18 series resolve the same way (`first`+A, whose apparent
+16¢ is exactly the artifact `bootstrap_verdict_admissible` exists to catch — 98.0% both-fill
under a proxy that lets a cancelled queue count as a fill).

### Wide-spread sensitivity — a bigger overround does not rescue it

Restricting to progressively wider books raises the gross capture *and* the adverse selection
together:

| min spread | n | series | both-fill rate | both-fill net | per-attempt mean (model B) | 95% CI |
|---|---|---|---|---|---|---|
| 2¢ (S68's gate) | 564 | 18 | 21.81% | +\$0.0115 | −\$0.0923 | [−0.1311, −0.0423] |
| 5¢ | 371 | 17 | 29.65% | +\$0.0550 | −\$0.0533 | [−0.0776, −0.0293] |
| 7.31¢ (idea-stage mean) | 248 | 14 | 25.81% | +\$0.1133 | −\$0.0357 | [−0.0817, +0.0043] |

The both-fill capture grows almost 10× (1.15¢ → 11.33¢) and the per-attempt result stays
negative throughout, only losing significance at the narrowest population (n=248, 14 series) —
because wider spreads mean a more mispriced book, which means more one-sided flow, which means
more half-fills.

## It dies on the EDGE, not on adequacy (L53)

The both-fill rate is **21.81%** — roughly **48× the S19 0.45% queue-aware fill floor**, and in
the same "fills fine, loses money" class as S14's 27.18%. The population is 564 attempts across
18 game series and 316 games, well clear of every structural floor. Q49's `fill rate below the
S19 floor` and `population below the 10-series floor` kill conditions **did not fire**. The one
that fired is `per-attempt block-boot CI ≤ 0`, plus `fails clears_tick_magnitude`. This is a
genuine falsification of the mechanism, not a data-adequacy dodge — the same distinction the S14
verdict drew.

## Honest reconstruction note on the idea-stage numbers

The idea-stage figures (**205** tickers / **16** series / mean yes-spread **7.31¢** / mean
`yes_bid+no_bid` **0.927**) did **not** reproduce exactly under any snapshot-selection rule tried
here. Nearest reconstructions bracket them:

| selection rule | n | series | mean spread | mean `yb+nb` |
|---|---|---|---|---|
| last pre-close snapshot | 179 | 15 | 0.0711 | 0.9289 |
| last pre-close *two-sided* snapshot | 232 | 16 | 0.0669 | 0.9331 |
| *(idea-stage, as recorded)* | *205* | *16* | *0.0731* | *0.927* |

This probe defines its own explicit, documented population (564/18) rather than inheriting an
unreproducible one — it is larger because it accepts any qualifying entry with a post-entry
observation rather than a single snapshot per ticker. **The load-bearing qualitative claims all
reproduce**: `yes_bid + no_bid < $1` for **100.0%** of the population, mean spread in the
4–7¢ band, and 15–18 game series ≥ the L41 floor. The 205/16/7.31¢ triple should be treated as
approximate provenance, not as a citable statistic.

## Limitations (stated, not hidden)

1. **No independent verifier.** The dispositive limitation. See "Status of this document".
2. **The fill model is generous in both directions of the argument.** Cancels ahead of us count
   as advancing us and queue-jumpers are free — this *inflates* fills, which biases toward
   SURVIVE, and the probe still kills. Conversely it is a turnover proxy, so it rules a cell
   OUT, never IN (L48).
3. **No order management.** A live maker would cancel the surviving leg once the first fills.
   That is a policy this ex-post sim cannot evaluate (the cancel decision needs an intra-snapshot
   decision rule the hourly-ish depth cadence cannot resolve) and it is the one steelman left
   standing — but it is a *different strategy*, not the S68 mechanism, and it would forfeit the
   deterministic capture that is S68's entire claim.
4. **Depth cadence.** Snapshots are hourly-scale, so intra-hour round trips through our level are
   invisible; the queue proxy absorbs them as departures.
5. **Entry-policy / window-length confound.** See the section above — the `late` cell's magnitude is
   partly short-horizon structure. The verdict is stated so that it does not depend on that cell's
   magnitude.

## Verdict

**S68 → DEAD (edge), PROVISIONAL pending verifier.** The deterministic both-bid overround is
real, reproduces on committed tape, and pays exactly what the arithmetic promises when both legs
fill (+\$0.0115 net at the 2¢ gate). It is not reachable as a strategy: you cannot condition on
both legs filling, 44% of attempts half-fill, and the half-fills are adversely selected by a
factor of 2–3× against the base rate. **The verdict rests on the weakest sufficient claim — of
the four cells run (2 entry policies × 2 fill models), NONE produces a `bootstrap_verdict_admissible`
CI > 0 that clears `clears_tick_magnitude`.** The fairer full-life cell (`first` + model B, median
65 post-entry snapshots) is a wash: **+\$0.0011, 95% CI [−0.0533, +0.0797]**, n=564 over 18 series.
The idea-stage-regime cell (`late` + model B) is outright falsified: **−\$0.0923, 95% CI
[−0.1311, −0.0423]**, fully below zero, admissible, failing the tick gate — with the honest caveat
that its 3-snapshot median window contributes to the magnitude. Prices `real_bid` + `broker_truth`. The S68 registration's own
presumptive outcome — *KILL on adverse selection, the L5 maker fill-wall that took S6/S13/S14/S23*
— is what the tape says. Same short-the-spread maker factor family as S6/S13/S19/S23
(Hard-Rule-#6 ρ cap, not diversification).

**Still 0 proven edges.**

## Reproduce

    python scripts/q49_two_sided_maker_fillsim.py --entry-policy late          # binding cell
    python scripts/q49_two_sided_maker_fillsim.py                              # first-entry cut
    python scripts/q49_two_sided_maker_fillsim.py --entry-policy late --min-spread 0.0731
    python -m pytest tests/test_q49_two_sided_maker_fillsim.py -q              # 44 offline tests
