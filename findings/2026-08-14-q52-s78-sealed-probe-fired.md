# Q52 / S78 — the sealed toxicity-filtered maker probe was FIRED. Verdict: DEAD (PROVISIONAL)

`2026-08-14` · research loop, protocol v3 · queue item **Q52** · candidate **S78**
**Verdict class. Two-agent rule NOT satisfied — this result is `PROVISIONAL` and the
registry is NOT flipped.** See §6.

---

## 0. What this run did

On 2026-08-13 a research-loop firing built `scripts/q52_s78_toxicity_filtered_maker_probe.py`
under idle-run policy (b), sealed it at `PREREG_SHA256
1c2e422876ce44f5f8217dc98b4a7d8a43c9fcca04b1d8ddd1e8d3ff5bb218c2`, measured that its data
gate had opened (`gate_reasons: []`, `admissible: true`), and then **deliberately did not run
the scoring half** — that half is verdict-class, no `Task`/subagent tool existed in that
harness, and banking an unverifiable CI was judged worse than leaving a sealed probe unfired.
Its closing sentence: *"Next run with a `verifier` available fires it with no flags and no
edit."*

This run fired it. Exactly as specified: **no flags, no edit.** `git diff HEAD` on the probe
file is empty and the seal hash recomputed at import time still equals the one recorded in
`LOOP-QUEUE.md` on 08-13. The committed `tape/kalshi_trades/` day set is unchanged (6 days:
`dt=2026-07-07/07-08/07-10/07-11/07-12/08-03`), so the population the probe scored is the
population it was sealed against.

Q52 was the topmost eligible queue item: Q0–Q56 were re-derived at each item's CURRENT status
(reading each section in full — Q4/Q9/Q11/Q12/Q16/Q23/Q27 keep a stale `TODO` BELOW their real
DONE verdict, Q24/Q53 keep theirs ABOVE) and every other item is DONE / BLOCKED(Ryan-or-
credential) / density-gated / data-inadequate.

---

## 1. The verdict

**DEAD.** The pre-registered headline branch is `all_candidates` (an unfilled candidate scores
an honest $0.00, never dropped):

| branch | n_units (games) | n_obs | mean / contract | 95% block-bootstrap CI | clears 1 tick |
|---|---|---|---|---|---|
| **`all_candidates` (headline, pre-registered)** | **34** | **362** | **+$0.0034807** | **[−$0.0086686, +$0.0145783]** | **no** |
| `conditional_on_fill` (secondary) | 13 | 21 | +$0.060000 | [−$0.1552941, +$0.2396667] | no |

`n_boot=10000`, `seed=42`, block bootstrap **by GAME** (L6). The CI straddles zero, so the
pre-registered `verdict_rule` returns **DEAD**. It would have failed the L27 economic-
significance gate anyway (`clears_tick_magnitude: false` — the lower bound is nowhere near
one cent).

**Price source tags** (CLAUDE.md trust defaults — this is a P&L number, so it carries them):

| quantity | tag |
|---|---|
| resting maker price | `real_bid` (the snapshot's own touch bid, read off the committed ladder — never a midpoint, never synthetic) |
| fill evidence | `broker_truth` (an executed `tape/kalshi_trades/` print that consumes our queue) |
| toxicity signal (markout) | `broker_truth` (print vs later print) |
| settlement | `broker_truth` (`core.settlement_sources`, 9 declared families) |
| fee | maker rate via `core.pricing.fee_per_contract` (L5 — no hand-rolled rate) |

`network_calls: 0`. Nothing here is a synthetic price and no synthetic price was filled.

---

## 2. This is an ADMISSIBLE dead, not a data-adequacy dodge

Every pre-registered adequacy gate PASSED before scoring was reachable:

- `n_units = 34` games vs the L41 floor of **10** — 3.4x.
- `sign_variation_admissible`: minority side `yes`, **5 EXCLUSIVE** minority units vs the L321
  floor of 2 (the exclusive count, not the touching count — this is the first probe in the
  repo built against L321 from the start rather than retrofitted). 29 `no` / 28 `yes` touching
  units, 23 mixed.
- `bootstrap_verdict_admissible`: 7 opposing units, `admissible: true`.
- Kish effective n **26.57** on 34 units (design effect 1.28) — the block structure is not
  concentrated in one game.
- `gate_reasons: []`.

So the population was adequate to answer the question, and the answer is that the edge is not
there. That is a real kill, not "come back with more tape".

---

## 3. Where the edge went: the signal is measured per PRINT, the P&L is earned per CANDIDATE

The train-window filter looked strong. TRAIN = `07-07/07-08/07-10`, markout net of the maker
fee, 30-minute horizon:

| cell | n TRAIN prints | mean markout | net of maker fee | admitted? |
|---|---|---|---|---|
| `cheap/tight` | 52,738 | +$0.068608 | **+$0.058608** | **ADMITTED** |
| `rich/wide` | 2,422 | +$0.067143 | **+$0.057143** | **ADMITTED** |
| `cheap/wide` | 2,717 | −$0.044192 | −$0.054192 | refused |
| `rich/tight` | 62,560 | −$0.061594 | −$0.071594 | refused |

Two of four pre-declared cells clear the admission rule by ~5.8¢/contract — an enormous
apparent margin over a 1¢ maker fee. Yet the holdout realized P&L is +0.35¢ with a CI through
zero. The gap is **denominator substitution**:

```
52,738 TRAIN prints  ->  434 holdout candidates  ->  362 scoreable  ->  21 fills (5.80%)
```

- The markout that defines the filter is a property of prints that **actually executed**. Our
  candidate is a quote we **rest** — and the queue-aware fill model (imported wholesale from
  the S80 probe, L100; never `OPTIMISTIC_FILL`, never a queue-departure proxy, L39/L48/L250)
  fills only **5.80%** of them. 94.2% of the headline population is therefore an honest $0.00,
  and the headline is a mean dominated by zeros.
- Conditional on being filled the mean is +6.0¢ — nominally attractive — but 21 fills spread
  over 13 games gives a CI of ±20¢. Conditioning on the fill is conditioning on the taker's
  decision to cross us, which is exactly the adverse selection the strategy claims to filter.

The mechanism failure is therefore **not** "the toxicity signal is noise". It is that a maker
cannot convert a print-population statistic into a fill-population return at this book cadence:
where the filter says rest, we are almost never filled; where we are filled, the sample is too
small to distinguish from noise. This is the same wall S19 (0.45% fill), S13, S23, S79 and the
S80 mirror all hit, reached from a new direction.

Holdout settlement coverage (`broker_truth`): 40 tickers requested → **34 binary**
(`q51_settlement_cache` 32, `settlement_ledger` 2) → 5 non-binary, 1 listed-but-unsettled,
6 unresolved. No settlement family was absent from disk.

---

## 4. Honest caveats (these bound the kill, they do not rescue it)

1. **The headline mean is POSITIVE** (+0.35¢). This is a "not proven" kill, not a
   "demonstrably loses money" kill. Re-firing on a much larger holdout is the only thing that
   could move it, and see (2).
2. **Population provenance (L315).** The five July `tape/kalshi_trades/` day-files are a
   TICKER-SCOPED BACKFILL of one 34-game manifest
   (`reports/q52_q54_trades_backfill_phase1_phase2.json`, `coverage_is_ticker_scoped=true`),
   while `dt=2026-08-03` is a complete live sweep. The holdout therefore mixes a backfill-
   selected slice with one full day; the unit and series counts on the July side are a property
   of that selection, not a random day-sample.
3. **Book cadence.** `orderbook_depth`'s capture density steps from 25 distinct capture
   instants on 2026-07-22 to 3 on 2026-07-23 (the L117/L127/L177/L213/L304 VPS-collector-death
   chain). Sub-3h queue position remains unmeasurable (L283); the 240-minute interval/staleness
   caps in the seal are the honest accommodation of that, and they are also why 434 candidates
   is a small number for 40 games.
4. **No sensitivity grid was run, deliberately.** The seal forbids one (mandate (1)'s
   luckiest-cell rule). A future run wanting one must re-pre-register and re-pin
   `PREREG_SHA256` in the open.

---

## 5. Redundancy leg (reported as redundancy, NEVER as verification)

No `Task`/subagent tool exists in this harness, so the sanctioned second-implementation
fallback ran (the L287/L288/L290/L291/L295/L308/L313/L325 precedent chain).

`scripts/q52_s78_population_rederive.py` (built 08-13, from-scratch, shares no code with the
probe) re-ran unchanged and reproduced the outcome-blind half exactly: admitted cells
`['cheap/tight', 'rich/wide']`, 21 train / 40 holdout / 11 straddling games, 362/434
candidates, 21 fills, 34 units, 5 exclusive-minority units.

**New this run:** `scripts/q52_s78_scoring_rederive.py` (+44 offline tests) re-derives the half
the outcome-blind leg deliberately refused to touch — settlement DIRECTION, per-candidate P&L,
and the bootstrap. It does not import the probe (AST-pinned by a test), reads settlement
straight at the committed cache/ledger files with its own restated first-hit precedence walk,
restates the payout/fee arithmetic, and resamples with a **hand-rolled 64-bit LCG** rather than
`random.Random`, so the CI is a genuinely independent Monte-Carlo estimate rather than a replay
of the same stream.

| quantity | sealed probe | independent re-derivation | agreement |
|---|---|---|---|
| n scored | 362 | 362 | exact |
| n filled | 21 | 21 | exact |
| n units | 34 | 34 | exact |
| `all_candidates` mean | +0.0034806630 | +0.0034806630 | **exact** |
| `all_candidates` CI | [−0.0086686, +0.0145783] | [−0.0084469, +0.0146635] | within MC error; both straddle 0 |
| `conditional_on_fill` mean | +0.0600000 | +0.0600000 | **exact** |
| `conditional_on_fill` CI | [−0.1552941, +0.2396667] | [−0.1490909, +0.2425806] | within MC error; both straddle 0 |
| verdict | DEAD | DEAD | agree |

The re-derivation also reports **0 settlement-direction conflicts** across the declared source
families for these tickers, so the first-hit precedence walk is not hiding a disagreement that
could flip a P&L sign.

Two independent implementations agreeing is evidence a number is not a typo. **It is not the
two-agent verdict rule.**

---

## 6. Why this is PROVISIONAL, and what it blocks

`LOOP-QUEUE.md` step 5: a verdict-class change (registry status flip, bootstrap CI destined for
`kb/`/`findings/`, kill decision) requires the producer AND an independent `verifier` re-run
that CONFIRMS before commit; without it the result *"may only be committed as `PROVISIONAL` and
must not flip the registry."*

**This harness exposes no `Task`/subagent tool** — the `research-lead` seat was launched with
Read/Grep/Glob/Bash and the GitHub MCP tools only, despite its charter naming five worker
agents. That is the same defect recorded at L287/L288/L290/L291/L295/L308/L313/L325 and flagged
for Ryan on 2026-08-13 as a regression from the 08-07 "Task restored" note. It is now the sole
thing standing between this repo and a closed verdict on its only open candidate.

Therefore:

- **S78 stays `collect-and-revisit` in `kb/strategies/00-index.md`.** No flip. A note recording
  that a PROVISIONAL DEAD CI is on the table is appended to its row; the status cell is
  untouched.
- The owed independent verification is filed as **Q57**, in the shape Q50 used for the previous
  PROVISIONAL-result-on-the-table case.
- The repo remains at **0 proven edges**.

## 7. Reproduce

```
python3 scripts/q52_s78_toxicity_filtered_maker_probe.py        # ~1m50s, writes reports/q52_s78_toxicity_filtered_maker.json
python3 scripts/q52_s78_population_rederive.py                  # ~1m00s, outcome-blind redundancy
python3 scripts/q52_s78_scoring_rederive.py                     # ~1m10s, writes reports/q52_s78_scoring_rederive.json
```

All three are read-only, offline, credential-free, and import nothing from `execution/`.
