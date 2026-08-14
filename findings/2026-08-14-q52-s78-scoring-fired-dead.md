# Q52 / S78 — sealed probe scoring fired: verdict DEAD, two-agent CONFIRMED

*2026-08-13/14 · research loop, protocol v3 · producer: main context · independent verifier:
`verifier` subagent (this harness has an `Agent` tool with a `verifier` type available — the
first research-loop firing where that has been true; prior runs on this exact next-step were
blocked on it, see `findings/2026-08-13-q52-s78-sealed-probe-and-open-gate.md`) ·
**CONFIRMED, two-agent rule satisfied.**

**Verdict.** S78 ("toxicity-filtered selective maker") is **DEAD**. Both pre-registered branches
of the sealed probe's 95% block-bootstrap-by-game CI straddle zero net of the maker fee. This is
the expected, honestly-stated-in-advance outcome (see the 2026-08-13 finding above) — a DEAD
verdict is a success per CLAUDE.md's Stop rules, not a failure of the run.

---

## 1. What fired

`scripts/q52_s78_toxicity_filtered_maker_probe.py`, sealed 2026-08-13 at
`PREREG_SHA256 = 1c2e422876ce44f5f8217dc98b4a7d8a43c9fcca04b1d8ddd1e8d3ff5bb218c2` (test-pinned,
unmodified — confirmed by both the producer and the independent verifier before and after this
firing). Fired exactly as the prior status update instructed: **no flags, no edit**
(`python3 -m scripts.q52_s78_toxicity_filtered_maker_probe --json`). `network_calls: 0`.

## 2. The numbers

Population (unchanged from the 2026-08-13 sealed-and-open-gate finding, reproduced here for
context): HOLDOUT 434 candidates → 362 scoreable → **21 fills (5.80%) over 34 bootstrap units
(games)**, exclusive-minority units 5 (L321 floor 2), settlement 34/40 binary
(`q51_settlement_cache` 32, `settlement_ledger` 2, `broker_truth`). `gate_reasons: []`,
`admissible: true`.

**`all_candidates` branch** (unfilled legs score an honest $0 — the pre-registered `verdict_label`
branch):
- n_units = 34, n_obs = 362
- mean = **+$0.003481** / contract
- 95% CI (block-bootstrap by game, n_boot=10,000, seed=42) = **[-$0.008669, +$0.014578]**
- `clears_tick_magnitude: false`
- admissible: true (n_opposing_units = 7), Kish effective n = 26.57 (design effect 1.28)

**`conditional_on_fill` branch:**
- n_units = 13, n_obs = 21
- mean = **+$0.06** / contract
- 95% CI = **[-$0.1553, +$0.2397]**
- `clears_tick_magnitude: false`
- admissible: true (n_opposing_units = 7), Kish effective n = 9.8

**Verdict: DEAD** on both branches. Prices `real_bid` (rest) / `broker_truth` (fill evidence,
settlement); no synthetic price anywhere in the chain (Hard Rule #3).

## 3. Independent verification (two-agent rule)

An independent `verifier` agent — sharing no process state with the producer — was dispatched
with the exact claim, the script path, and the tape it read. It:

1. Confirmed the seal (`PREREG_SHA256` unmodified, `git status` clean on all code) and re-ran the
   identical command from a clean shell, reproducing every number above field-for-field.
2. Verified the bootstrap is a genuine block-bootstrap by `event_ticker_of` (game) — both legs of
   a two-sided game collapse into one unit — and stress-tested with an independent
   re-implementation (different seed, n_boot=20,000: CIs unchanged in substance) and a
   deliberately-wrong pseudo-replicated-by-row contrast, which came out **narrower**, confirming
   the by-game blocking is doing its job in the conservative direction, not manufacturing a false
   DEAD.
3. Confirmed L249 sign-boundedness is a real, reachable measurement on both branches (not a gate
   artifact): 11 positive / 10 negative raw observations, 6/7 positive/negative unit means.
4. Confirmed the fee path (`MAKER_FEE_RATE` via `core.pricing`, no hand-rolled literal) with two
   hand-checked fills, and confirmed L345/L348 (anchored settlement root) and L321 (exclusive
   minority-unit gate, not a weaker check) are both correctly wired in this probe.
5. Spot-checked one settlement join directly against a raw print and confirmed the win/loss
   direction matches the scored row.

**Returned: CONFIRMED.** Two caveats carried into the registry entry, neither a refutation:
(a) the `conditional_on_fill` branch is *underpowered* (21 fills, ±$0.20 half-width) rather than
*measured-null* — the headline `all_candidates` branch is the informative one and is the branch
the pre-registered `verdict_label` actually uses; (b) the TRAIN cell admission pattern
(`cheap/tight` and `rich/wide` admitted, `rich/tight` and `cheap/wide` refused) looks like a
favorite-longshot-bias artifact of the markout definition rather than a genuine toxicity signal —
it did not survive holdout, which is exactly what holdout is for.

## 4. What this does and does not change

- `kb/strategies/00-index.md` S78 row: **flipped `collect-and-revisit` → `dead ✗`**, conf `low`
  (two-agent CONFIRMED, per the run protocol's two-agent verdict rule).
- No other candidate's status changes. S11 ("data-collecting", the parent lane) is unaffected —
  S78 was one candidate operationalization of it, now closed.
- Same short-the-toxic-side / rest-on-the-cheap-favorite factor family as S13/S23/S79/S80 — all
  now dead or straddling zero. Hard-Rule-#6's regime-conditional ρ cap applies to this family as a
  whole, not diversification credit.
- Still **0 proven edges**.

## 5. Redundancy trail preserved

The 2026-08-13 population-construction redundancy leg (`scripts/q52_s78_population_rederive.py`,
+28 tests, caught the L347/L345-adjacent cent-arithmetic classification defect) is unchanged and
still stands behind the population numbers this scoring run consumed unmodified.

See `reports/q52_s78_toxicity_filtered_maker.json`,
`findings/2026-08-13-q52-s78-sealed-probe-and-open-gate.md`, `kb/00-LOG.md` 2026-08-14.
