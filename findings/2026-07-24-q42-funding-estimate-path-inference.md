# Q42 (part-1 residual) — is the finalized funding print a clamp of Kalshi's published `funding_estimate` path? **UNDECIDABLE at current tape density**

`2026-07-24` · LOOP-QUEUE.md **Q42**, part-1 residual (the clamp-FORMULA inference) ·
script `scripts/q42_funding_estimate_path_inference.py` ·
tests `tests/test_q42_funding_estimate_path_inference.py` (87 at publication, **88** after the
2026-07-27 frozen-slice gate repair; offline; synthetic fixtures plus
4 read-only tape pins) · read-only over committed tape, **no network**.

> Corrected **twice**, by two independent verifiers. Read the round-1 correction immediately
> below and the **round-2** correction at the end of this file before quoting any number.

> **NOT a P&L verdict. NO registry change.** `kb/strategies/00-index.md` untouched. There is
> no fill price, no fee math, and no bootstrap CI anywhere in this milestone. Every funding
> number below (forward estimate AND finalized print alike) is tagged **`broker_truth`**:
> venue-computed, and **never** a fillable price.

---

## Correction (2026-07-24, post-verifier — round 1)

**The first pass of this note claimed "H1 is FALSIFIED at current tape density." That claim
was wrong and is withdrawn.** An independent `verifier` agent refuted it the same day.

What the verifier reproduced EXACTLY (so the loader and the arithmetic are not at issue): all
eight integrity-gate cells (299 / 1746 / 286 / 13 / 22 / 130 / 42 / 28), the five-`g`
separation table bit-for-bit, the overlap band `[1.0194343677e-04, 1.3015897238e-04]` with its
5-zero / 9-nonzero split, the 244/240/4 class-wide counterexample block, the **NAIVE
(pseudo-replicated — see item 3 below; never quote it alone)** Fisher p = 5.299656e-10, the
identity-fit table, and the density block. It also confirmed the probe
fell into none of the schema traps (`record_type` filter, nested `prints[]`, L137 both-mode
read, `funding_rate_estimate` field name, 13 no-print groups excluded rather than imputed, no
raw `fromisoformat`).

**What it broke was the inference, in four places:**

1. **The overlap is a capture-STALENESS artifact, not evidence of nondeterminism.** The
   `g_last` gap is *monotone in path density* and turns POSITIVE (a hard gap) on the dense
   subsets. The first pass measured the staleness confound in the identity leg
   (`r(|resid|, lead) = +0.367`) and then failed to propagate it into the threshold leg —
   which is exactly where it bites.
2. **The stated data-adequacy argument was logically false.** The first pass wrote: *"More
   data can add windows to a gap; it cannot remove observations that already sit inside one."*
   That is false for a statistic of a **sampled path**: denser capture does not merely add
   windows, it **recomputes `g_last` on the windows already in the band** — a 2-sample window
   whose last estimate landed 4.95h before close gets a *different* `g_last` under denser
   capture. That sentence was load-bearing for the FALSIFIED verdict; it is deleted and
   inverted below.
3. **The Fisher p was pseudo-replicated (L6).** 286 windows are 13 tickers x 22 funding_times,
   not 286 independent observations.
4. **The KXETHPERP/KXZECPERP "near-controlled pair" did not show what was claimed**, and
   `mis_1bp = 10/42` was headlined as if it bore on H1 when H1 is existentially quantified
   over θ.

**Corrected verdict: H1 is UNDECIDABLE at current tape density.** This tape cannot decide it
in either direction. The density-independent result (Result 1) is unaffected and is now the
headline.

Recording the correction rather than quietly rewriting the file is the point: the first pass's
error was a *reasoning* error on top of arithmetic the verifier confirmed line by line, which
is precisely the class of error a second agent exists to catch.

---

## The question

Q42 part 1 (`findings/2026-07-17-q42-funding-clamp-characterization.md`) established a
**genuine ±1 basis-point (1e-4) dead-band clamp** on Kalshi's finalized 8h perp funding
prints. The open thread was the **formula**:

> **H1** — **there exists** a summary statistic `g(estimate_path)` and a threshold θ such that
> `finalized == 0` **iff** `|g| < θ`, and on the non-clamped branch `finalized ≈ g` (identity).

Note the existential quantifier over θ. Accuracy at part 1's *borrowed* ±1bp constant
(`mis_1bp`) tests **"does part 1's untuned constant transfer to the estimate path"** — a
different and weaker question. H1's own quantity is the **hard-gap** test. The first pass
conflated the two; this revision keeps them apart.

Candidate `g`'s tested (all read only Kalshi's own published forward estimates):

| id | `g` |
|---|---|
| (a) | `g_last` — LAST estimate strictly before `funding_time` |
| (b) | `g_mean` — simple unweighted mean of the path |
| (c) | `g_twap` — time-weighted mean, piecewise-constant forward-fill |
| (d) | `g_maxabs` — the estimate with the largest `|.|` on the path |
| (e) | `g_last_nonzero` — LAST NONZERO estimate (labeled diagnostic) |

---

## Data + the schema trap this probe exists to avoid

`tape/perp_tape/dt=*.jsonl` multiplexes a family on `record_type`:

- **`funding_estimate`** — a FLAT per-ticker row. The rate field is **`funding_rate_estimate`**
  (NOT `funding_estimate`, NOT `funding_rate`). Keyed `(ticker, next_funding_time)`.
- **`funding_rates`** — a **NESTED ENVELOPE** (`mode` ∈ {`backfill`, `recent`}, `n_prints`,
  `prints[]`). The per-print fields live **inside `prints[]`**. A naive TOP-LEVEL join
  **silently returns ~zero rows instead of erroring**. `naive_toplevel_print_index()`
  reproduces the trap on purpose and a regression test pins it at **0**.
- Per **L137**, BOTH `mode` values are read and deduped on `(market_ticker, funding_time)`:
  **99 envelopes = 1 `backfill` + 98 `recent`**, 5,230 prints read → **1,746 after dedupe**.
- Other `record_type`s are filtered out (L96-class conflation guard). All ISO timestamps go
  through `core.timeutil.parse_iso_utc`; **zero** raw `fromisoformat` call sites (L136/L138).

## Integrity gate — reproduced EXACTLY (all `broker_truth`), and independently by the verifier

| quantity | observed | pre-measured | |
|---|---|---|---|
| estimate-path groups `(ticker, next_funding_time)` | **299** | 299 | OK |
| finalized prints deduped, both modes | **1746** | 1746 | OK |
| **joined windows** | **286** | 286 | OK |
| distinct tickers | **13** | 13 | OK |
| distinct funding_times | **22** | 22 | OK |
| joined with ≥3 estimate samples | **130** | 130 | OK |
| discriminating (≥1 NONZERO estimate) | **42** | 42 | OK |
| …of which finalized == 0 | **28** | 28 | OK |

Excluded and counted, never imputed: 13 estimate groups with no finalized print; 0 prints with
a `None` rate; 0 estimate samples at/after close.

---

## Result 1 (THE HEADLINE — density-independent, survives the correction untouched) — **the published estimate is itself ±1bp clamped**

Before any `g` can be tested, the regressor has to be checked. It carries the *same* dead band
part 1 found on the finalized prints:

| quantity (`broker_truth`) | value |
|---|---|
| estimate samples | **1,274** |
| exactly zero | **1,191** (fraction **0.9348509**) |
| nonzero | **83** |
| min `\|nonzero estimate\|` | **1.0026436e-04** |
| nonzeros inside the open interval `(0, 1e-4)` | **0** |

Same decisive shape as part 1 (L89's discriminator): a **hard gap** just above zero, nonzeros
continuous rather than lattice-quantized. **Kalshi clamps the forward estimate it publishes,
not just the finalized print.**

This is the one result that owes nothing to capture density — it is a property of the 1,274
sampled values themselves, not of how they are grouped into paths. Its consequence is the
strongest statement this milestone can make: **the regressor is PRE-CLAMPED, so sub-band
information is destroyed at the source**, and no `g` computed from the published path can ever
recover the pre-clamp quantity the settlement formula presumably acts on. The FORMULA question
may therefore be **structurally unanswerable from the `funding_estimate` endpoint at ANY
capture density** — a stronger and more durable caution than anything the threshold leg found.

## Result 2 — the density stratification that overturns the first pass's verdict

Rule: predict `finalized == 0` iff `|g| < θ`. **Hard gap** =
`max(|g| | fin=0) < min(|g| | fin≠0)`, i.e. *some* θ classifies every window correctly — that
is H1's quantity. The pooled discriminating population (n = 42) has **no** hard gap for any
`g`. Re-running the identical test on progressively DENSER subsets (`density_stratified_
separation()`, now a first-class output of the script):

**`g_last`, discriminating population, re-derived here — matches the verifier cell-for-cell:**

| filter | n | fin=0 | fin≠0 | median samples | median lead (h) | mis_1bp | gap | **hard gap?** | exact p |
|---|---|---|---|---|---|---|---|---|---|
| `n>=1` (as first published) | 42 | 28 | 14 | 3.0 | 0.98 | 10 | −1.3016e-04 | NO | — |
| `n>=2` | 40 | 28 | 12 | 3.0 | 0.98 | 10 | −1.3016e-04 | NO | — |
| `n>=3` | 22 | 17 | 5 | 7.5 | 0.53 | 4 | −2.7473e-05 | NO | — |
| `n>=4` | 18 | 15 | 3 | 8.5 | 0.52 | 3 | **−2.8168e-07** | NO | — |
| `n>=5` | 18 | 15 | 3 | 8.5 | 0.52 | 3 | −2.8168e-07 | NO | — |
| `n>=8` | 11 | 10 | 1 | 12.0 | 0.53 | 2 | **+2.0479e-05** | **YES** | **0.0909** |
| `lead<=0.75h` | 14 | 12 | 2 | 11.0 | 0.50 | 2 | **+1.0256e-05** | **YES** | **0.0110** |
| `lead<=1h` | 24 | 17 | 7 | 7.0 | 0.54 | 2 | −1.0307e-06 | NO | — |
| `lead<=2h` | 28 | 19 | 9 | 5.0 | 0.70 | 3 | −2.8216e-05 | NO | — |

Every cell I re-derived agrees with the verifier's; **no cell differs**. (The verifier reported
five of these nine rows; `n>=2`, `n>=5`, `lead<=1h`, `lead<=2h` are additional rows this script
now emits, and they interpolate the same monotone trend.)

The gap rises monotonically along the nested chain — **which is automatic for nested subsets
and carries no information** — and crosses zero at `n>=8`; **a hard gap on a random 11-of-42
subset occurs 20% of the time, so the crossing is not itself evidence.**

> **Why the monotonicity flag is a tautology (round-2 correction).**
> `gap(S) = min{|g| : fin≠0} − max{|g| : fin=0}`. For nested `S' ⊂ S` the min over the smaller
> set can only rise and the max can only fall, so `gap(S') >= gap(S)` **unconditionally, for
> any data whatsoever**. The `min_samples` strata are exactly a nested chain, so
> `gap_is_monotone_in_density → True` is guaranteed by construction. (Verifier check: 2000/2000
> random nested chains of matched cardinality 42→40→22→18→18→11 were monotone. A test now pins
> this as a tautology so it cannot be re-read as a finding, and the script's docstring — which
> asserted the opposite in round 1 — is fixed.) Note also that
> `pooled_overlap_is_density_confounded = bool(hard) and bool(mono)` therefore reduces to
> `bool(hard)`; the `and mono` conjunct is **inert** and is documented as such in the script.
>
> **The statistic that does carry information — matched-size random-subset baseline**
> (`random_subset_hard_gap_rate()`, 20,000 seeded draws each, seed 20260724, re-derived here):
>
> | draw | P(hard gap) | vs. the dense cut |
> |---|---|---|
> | random **11**-of-42 (matches `n>=8`) | **0.2056** (4,113/20,000; 97 single-class draws) | `n>=8`'s hard gap is unremarkable |
> | random **14**-of-42 (matches `lead<=0.75h`) | **0.1042** (2,084/20,000; 15 single-class draws) | ditto |
>
> Neither dense cut's hard gap beats an arbitrary same-size cut. Cross-seed spread over
> {20260724, 1, 7, 42}: 0.2014–0.2063 and 0.0990–0.1066.

**What actually carries the density argument is measurement validity, not these strata**: a
`g_last` computed from an estimate published **4.95h before close** (population median lead
1.47h, max 4.99h of an 8h window) is simply **not a measurement of "the last estimate before
`funding_time`."** That is a validity objection, not an inference — and it is what makes the
UNDECIDABLE verdict hold regardless of how the strata come out.

Descriptive detail — the 10 `g_last` misclassifications at the 1bp band:

| ticker | funding_time | n_samples | last-sample lead (h) | `g_last` | finalized |
|---|---|---|---|---|---|
| KXETHPERP | 2026-07-17T20 | 11 | 0.54 | −1.004158e-04 | 0.0 |
| KXETHPERP | 2026-07-24T12 | **2** | **4.95** | −1.002644e-04 | 0.0 |
| KXLINKPERP | 2026-07-24T12 | **2** | **4.95** | +1.027505e-04 | 0.0 |
| KXLTCPERP | 2026-07-21T12 | 3 | 1.99 | −1.301590e-04 | 0.0 |
| KXLTCPERP | 2026-07-22T12 | 12 | 0.50 | −1.029741e-04 | 0.0 |
| KXNEARPERP | 2026-07-19T04 | **2** | **2.99** | −1.157074e-04 | 0.0 |
| KXNEARPERP | 2026-07-21T04 | **2** | **2.98** | 0.0 | −2.082260e-04 |
| KXSUIPERP | 2026-07-24T12 | **2** | **4.95** | −1.020924e-04 | 0.0 |
| KXZECPERP | 2026-07-18T12 | 7 | 2.52 | −1.003919e-04 | 0.0 |
| KXZECPERP | 2026-07-21T04 | **2** | **2.98** | 0.0 | −1.372422e-04 |

**Failures-vs-successes: one half of this contrast is supported and one half is not.** Round 1
headlined both as if both were (`failure_density_permutation()`, 200,000 draws, seed 20260724,
add-one, re-derived here):

| axis | failures (n=10) | successes (n=32) | mean difference | permutation p (one-sided / two-sided) | verdict |
|---|---|---|---|---|---|
| last-sample **lead** (h) | mean **2.935**, median 2.98 | mean **1.341**, median 0.94 | **+1.594 h** staler | **0.00112** / **0.00112** | **SUPPORTED** |
| path **sample count** | mean 4.50, median **2.0** (6 of 10 have exactly 2) | mean 5.41, median 3.0 | −0.906 samples | **0.2851** / **0.5572** | **NOT supported** |

So the failures are genuinely **staler**; they are **not** significantly **sparser**. The
"median 2.0 samples" figure is a descriptive cut only and must not be quoted beside the lead
figure as if it were a second supported result. (The verifier's independently computed
p = 0.0012 / 0.283 agree with mine to Monte-Carlo resolution.) Both **reverse-direction**
failures (last estimate exactly 0, print nonzero) are n=2, lead=2.98h — i.e. the "path was
zero" is really "we stopped looking three hours early." The same applies to Result 2 of the
first pass (the class-wide falsifier): all four all-zero-path-but-nonzero-print counterexamples
are **1- or 2-sample** windows (max samples on any counterexample: **2**; counterexamples with
≥3 samples: **0**), so the script now prints them under an explicit `DENSITY-CONFOUNDED` banner
and `counterexamples_all_sparse = True`.

**Honest counter-note — the dense subsets do NOT establish H1 either.** A hard gap on a stratum
with `k` nonzero-finalized windows out of `n` has exact one-sided permutation
p = `1 / C(n, k)`:

- `n>=8`: n = 11, k = **1** → p = **0.0909**. One nonzero window separates nothing; vacuous.
- `lead<=0.75h`: n = 14, k = 2, and those 2 are the top 2 of 14 → p = **0.0110**. More
  interesting, but n = 14 with 2 events, and it is **one of several post-hoc cuts** chosen
  after seeing the data.

**Multiplicity, stated numerically (round-2 correction — round 1 said this in words but never
gave the count or the corrected value).** The script declares
`MIN_SAMPLE_STRATA = (1, 2, 3, 4, 5, 8)` and `MAX_LEAD_STRATA_HOURS = (0.75, 1.0, 2.0)`:
**9 cuts searched** (`N_POSTHOC_CUTS_SEARCHED = 9`, now emitted per-row as
`exact_p_bonferroni_9_cuts`). Bonferroni over 9:

| cut | raw exact p | × 9 | significant at 0.05? |
|---|---|---|---|
| `lead<=0.75h` | 0.010989 | **0.0989** | **no** |
| `n>=8` | 0.090909 | **0.818** | **no** |

And **9 is a floor, not the true family size**: the specific values `8` and `0.75` were
themselves chosen after seeing the data, so the effective number of comparisons is larger than
9 and the corrected p's above are optimistic. This **strengthens** the conclusion — these p's
exist only to show H1 **cannot be confirmed** here.

So: the pooled overlap cannot falsify H1 (it is a staleness/validity artifact), and the dense
strata cannot confirm it (too few nonzero-finalized windows; post-hoc cuts that do not beat a
same-size random subset; nothing surviving multiplicity). That is the definition of
**undecidable on this tape**.

**Leave-one-out PASSES on the published population** (`leave_one_out_gap_scan()`, shipped in
the script as of round 2 and tape-pinned in the tests): over **67 drops = 7 discriminating
tickers + 18 discriminating funding_times + 42 individual windows**, **not one** restores a
hard gap for `g_last`. The most favourable single drop (`funding_time = 2026-07-21T04:00:00Z`)
still leaves gap = **−2.8216e-05**, versus a pooled **−1.3016e-04**. The pooled result is not
driven by a few rows — it is driven by **density stratification**, which is why an influence
check alone would never have caught it.

> The drop families are over the **discriminating** population's own distinct keys: only **7**
> of the 13 joined tickers and **18** of the 22 joined funding_times contribute a
> discriminating window at all. (Round 1 of this note wrote the decomposition as "13 + 22 +
> 42", which sums to 77, not 67 — see the round-2 correction section.)

## Result 3 — per-`g` θ, misclassification, and the hard-gap test (pooled)

`mis_tuned` uses the **in-sample optimal** θ (an upper bound on accuracy — fit on the same rows
it is scored on); `mis_1bp` uses part 1's **untuned** ±1e-4 dead band. **Reframed per the
correction:** `mis_1bp` measures whether **part 1's borrowed constant transfers to the estimate
path**. It is *not* a test of H1, which quantifies existentially over θ.

**Discriminating population (n = 42; 28 finalized-zero / 14 finalized-nonzero):**

| `g` | θ (tuned) | mis_tuned | rate | mis_1bp | max\|g\| \| fin=0 | min\|g\| \| fin≠0 | gap | hard gap? |
|---|---|---|---|---|---|---|---|---|
| `g_last` | 1.012e-04 | **7** | 0.167 | 10 | 1.302e-04 | 0.000e+00 | −1.302e-04 | **NO** |
| `g_mean` | 6.327e-05 | 10 | 0.238 | 10 | 1.402e-04 | 4.658e-05 | −9.365e-05 | **NO** |
| `g_twap` | 1.105e-04 | 11 | 0.262 | 13 | 2.408e-04 | 2.928e-05 | −2.116e-04 | **NO** |
| `g_maxabs` | 1.174e-04 | 14 | 0.333 | 28 | 2.970e-04 | 1.191e-04 | −1.779e-04 | **NO** |
| `g_last_nonzero` | 1.221e-04 | 13 | 0.310 | 28 | 2.805e-04 | 1.019e-04 | −1.785e-04 | **NO** |

**Full joined population (n = 286; 268 / 18):** `g_last` mis_tuned 11 (rate 0.038) / mis_1bp
14; `g_mean` 14 / 14; `g_twap` 15 / 17; `g_maxabs` 18 / 32; `g_last_nonzero` 17 / 32 — **no
hard gap** anywhere.

Pooled overlap detail for `g_last`:

- `|g_last|` where `finalized == 0`: 20 exact zeros + 8 nonzeros spanning **1.0026e-04 … 1.3016e-04**
- `|g_last|` where `finalized ≠ 0`: 2 exact zeros + 12 nonzeros spanning **1.0194e-04 … 2.3059e-04**
- inside the overlap band `[1.0194343677e-04, 1.3015897238e-04]`: **5** finalized-zero and **9**
  finalized-nonzero windows.

These numbers are correct (verifier-reproduced). What they do **not** support is the pooled
falsification — see Result 2.

**The KXETHPERP/KXZECPERP pair, corrected framing.** The pair is real (identical last
`computed_time` `19:27:50.880798Z` — a venue batch stamp shared across 13 tickers), same
funding_time, same 11-sample path length, same 0.54h lead:

| ticker | funding_time | last estimate | \|g_last\| | finalized |
|---|---|---|---|---|
| KXETHPERP | 2026-07-17T20:00:00Z | −1.0042e-04 | 1.0042e-04 | **0.0** |
| KXZECPERP | 2026-07-17T20:00:00Z | −1.2345e-04 | 1.2345e-04 | −1.2664e-04 |

The first pass called this the strongest evidence for falsification. **It is not.** The two
`|g_last|` values are in the **correct threshold order** (1.0042e-04 < 1.2345e-04), so any
θ ≈ 1.1e-04 classifies **both perfectly**. The pair refutes **part 1's untuned 1bp constant**
on the estimate path; it says nothing against H1, which only needs *some* θ. That distinction
is now enforced in the script's own report text.

`g_maxabs` remains the worst candidate (28/42 wrong at the untuned band). `g_last`'s tuned
θ = 1.011796e-04 buys its entire improvement (10 → 7) by shaving three borderline observations
in `[1e-04, θ)` — a textbook in-sample tuning artifact on n = 42, not a discovered venue
constant.

## Result 4 — identity fit on the non-clamped branch (`finalized ≠ 0`)

Discriminating population, n = 14:

| `g` | pearson r | MAE | median AE | mean signed | MAE / median\|fin\| | sign agree | r(\|resid\|, lead h) |
|---|---|---|---|---|---|---|---|
| `g_last` | 0.7203 | 3.627e-05 | 1.504e-05 | −2.964e-05 | 0.298 | 0.857 | **+0.367** |
| `g_mean` | 0.7723 | 4.922e-05 | 3.508e-05 | −4.505e-05 | 0.404 | 1.000 | +0.198 |
| `g_twap` | 0.7452 | 5.337e-05 | 4.637e-05 | −4.797e-05 | 0.438 | 1.000 | +0.079 |
| `g_maxabs` | 0.9278 | 2.158e-05 | 1.504e-05 | +2.593e-06 | 0.177 | 1.000 | +0.061 |
| `g_last_nonzero` | **0.9422** | 1.973e-05 | 1.504e-05 | −7.736e-06 | 0.162 | 1.000 | +0.335 |

Strong but non-identity on this tape: the best correlations (0.93–0.94) come from
`g_maxabs`/`g_last_nonzero`, exactly the two `g`'s worst at the threshold leg; even the best
MAE is ~16% of the typical finalized magnitude; `g_mean`/`g_twap` carry a systematic
−4.5e-05/−4.8e-05 shrink-toward-zero bias (what averaging an already-clamped path does).
`r(|residual|, lead)` is **positive for every `g`** — the miss grows with staleness. **This is
the confound the first pass measured here and then failed to carry into the threshold leg.**
On n = 14 these are descriptive; no p-value is attached.

## Result 5 — the independence null is rejected, but the naive p was inflated ~5 orders (L6)

| | finalized ≠ 0 | finalized == 0 |
|---|---|---|
| path has ≥1 nonzero estimate | 14 | 28 |
| path all-zero | 4 | 240 |

- `P(finalized ≠ 0 | path has a nonzero)` = **0.3333**; `P(finalized ≠ 0 | path all-zero)` = **0.0164**
- **NAIVE** two-sided Fisher exact **p = 5.2997e-10** — **pseudo-replicated**: it treats 286
  windows as independent when they are **13 tickers x 22 funding_times**. *Never quote this
  number alone.*
- **Cluster-robust permutation, labels permuted WITHIN TICKER** (200,000 draws, seed 20260724,
  add-one estimator, MC floor 5.0e-06): **p = 4.0e-05** one-sided (7 exceedances). Across
  seeds {1, 7, 42, 2026} the estimate ranges **2.5e-05 … 4.5e-05** — the verifier's
  independently computed **~2.5e-05** sits inside that Monte-Carlo spread, so the two agree to
  within resolution. **Round-2 caveat: that 4-seed spread slightly UNDERSTATES the true
  Monte-Carlo uncertainty.** With ~7 exceedances the Poisson SE on the count alone is √7 ≈ 2.65,
  giving roughly **2.2e-05 … 5.3e-05** for a ±1 SE band — wider than the observed seed spread.
  Read the p as "order 1e-05, direction robust," never as a 2-digit quantity.
- **Cluster-robust permutation, labels permuted WITHIN FUNDING_TIME**: **p = 5.0e-06** (0
  exceedances in 200,000 — at the MC floor, i.e. `< 5e-06`; verifier: `< 5e-05`).

**Direction survives clustering; the magnitude does not.** The association is also
**concentrated**, not uniform — per-ticker 2x2s (`a` = path-nonzero & print-nonzero,
`b` = path-nonzero & print-zero):

| ticker | n | a | b | c | d | discriminating | Fisher p |
|---|---|---|---|---|---|---|---|
| KXZECPERP | 22 | 6 | 5 | 0 | 11 | 11 | **0.0124** |
| KXSUIPERP | 22 | 3 | 5 | 0 | 14 | 8 | **0.0364** |
| KXHYPEPERP | 22 | 1 | 0 | 0 | 21 | 1 | **0.0455** (degenerate: one discriminating window) |
| KXNEARPERP | 22 | 3 | 7 | 1 | 11 | 10 | 0.293 |
| KXLTCPERP | 22 | 1 | 4 | 0 | 17 | 5 | 0.227 |
| KXETHPERP | 22 | 0 | 5 | 1 | 16 | 5 | 1.0 |
| KXLINKPERP | 22 | 0 | 2 | 1 | 19 | 2 | 1.0 |
| (6 others: BCH, BTC, DOGE, KSHIB, SOL, XRP) | 22 each | 0 | 0 | 0–1 | 21–22 | 0 | 1.0 |

**10 of 13 tickers are individually non-significant at 0.05.** The first verifier named
ZEC / SUI / NEAR as the carriers; I get ZEC / SUI / **HYPE** below 0.05 with NEAR at p = 0.293.
The second verifier adjudicated this table as **correct** (NEAR does not survive at p = 0.293).
**Real carriers: 2** — ZEC (0.0124) and SUI (0.0364). HYPE's 0.0455 is exactly 1/22 from a
single degenerate window (a=1, b=0, c=0, d=21) and is **not** a carrier; anywhere this note
previously said "~3 of 13 tickers" it now says **2 of 13**.

**Multiplicity here too:** these 13 per-ticker Fisher p's carry **no correction**. Bonferroni
over 13 leaves ZEC at 0.0124 × 13 = **0.16** and SUI at 0.0364 × 13 = **0.47** — i.e. the
per-ticker table locates *where* the pooled association lives, it does not independently
establish any single ticker.

So the estimate path is genuinely **informative** about the finalized print (~20x odds lift),
clustered in a handful of contracts. It is not shown to be **deterministic**, and it is not
shown *not* to be.

---

## Verdict on H1

**UNDECIDABLE at current tape density.** This tape cannot decide H1 in either direction:

- The pooled "no hard gap" result — the first pass's grounds for FALSIFIED — **inverts to a
  hard gap** once 2-sample / multi-hour-stale windows are dropped, and, more fundamentally, a
  `g_last` read off an estimate published up to 4.99h before close **is not a measurement of
  "the last estimate before `funding_time`"** at all. That **measurement-validity** objection
  (not the strata trend, which is a tautology on nested subsets) is what makes the pooled
  overlap unable to falsify H1.
- The dense strata that *do* show a hard gap are **too small, too post-hoc, and not rare
  enough to confirm H1**: exact p = 0.0909 (`n>=8`, one nonzero-finalized window) and 0.0110
  (`lead<=0.75h`, n = 14 with 2 events); Bonferroni over the **9 searched cuts** gives 0.818
  and 0.0989 respectively — neither significant at 0.05, and 9 is a floor since the values
  `8` and `0.75` were themselves picked after seeing the data. A hard gap on a *random*
  11-of-42 subset occurs **20%** of the time (14-of-42: **10%**), so neither dense cut beats an
  arbitrary same-size cut.

## What this tape CAN and CANNOT say

**CAN (density-independent or robust):**

1. **The published forward estimate is itself ±1bp clamped** (1,274 samples, 93.4851% exactly
   zero, min `|nonzero|` 1.0026436e-04, **0** nonzeros in `(0, 1e-4)`). The regressor is
   **pre-clamped**.
2. **Part 1's untuned ±1bp constant does NOT transfer to the estimate path**: at that constant
   `g_last` is wrong 10/42 on the pooled discriminating population (and the KXETH/KXZEC pair is
   a clean demonstration — both windows sit above 1e-4 with opposite outcomes). This is a
   statement about the *borrowed constant*, not about H1.
3. **The path/print association is real but clustered**: cluster-robust within-ticker
   permutation p ≈ **4.0e-05** (seed-spread 2.5e-05 … 4.5e-05, and see the Poisson-SE note in
   the round-2 correction — that spread understates the true MC uncertainty),
   within-funding_time p ≤ **5.0e-06**, carried by **2 of 13** tickers (ZEC p = 0.0124, SUI
   p = 0.0364; HYPE's 0.0455 is exactly 1/22 from a single degenerate window and is not a
   carrier). Those 13 per-ticker Fisher p's carry **no multiplicity correction** (ZEC
   0.0124 × 13 = 0.16). The naive Fisher 5.30e-10 overstates the pooled association by
   roughly five orders of magnitude (L6).
4. **The pooled result is not an outlier artifact**: leave-one-out over **67 drops (7
   discriminating tickers + 18 discriminating funding_times + 42 windows)** never restores a
   hard gap; the max gap over all drops is **−2.8216e-05**, still negative.

**CANNOT:**

- **Decide H1.** No statement about whether some `(g, θ)` reproduces the venue's clamp is
  supportable from this tape — neither positive nor negative.
- **Rank the `g`'s.** At a median of 2 samples per window, a 2-point "path" has no shape and
  `g_twap` degenerates toward `g_last`.

**Why the first pass's adequacy argument was wrong, stated plainly:** it asserted that more
data can only *add* windows to a gap, never remove observations already inside it. False for a
statistic of a **sampled path** — denser capture **recomputes `g_last` on the very windows in
the band**. The failures' last sample is on average **1.594 h staler** than the successes'
(permutation p = 0.00112, supported); their `g_last` is whatever the venue happened to publish
3–5 hours before close, and it would be a *different number* under denser capture. The band is
not a fixed set of observations; it is an artifact of where we stopped looking. (Six of the ten
have exactly 2 samples, but the sample-count difference is **not** significant, p = 0.285 — the
staleness axis is the supported one.)

**Reopen condition (concrete):** a per-window estimate path with **a sample inside the final
~5 minutes before `funding_time`** AND **≥8 samples across the window** (≈ the family's healthy
~30/day capture rate, sustained). Current tape: 07-17: 30 · 07-18: 15 · 07-19: 6 · 07-20: 7 ·
07-21: 9 · 07-22: 25 · 07-23: 3 · 07-24: 3 captures/day — **5 of 8 days below the 10/day
advisory floor**, median **2.0** samples per joined window, median last-sample lead **1.47h**
(max 4.99h) of an 8h window.

**Caveat on the reopen condition:** Result 1 means even that may not suffice. If the venue
publishes a **clamped** estimate, the pre-clamp quantity the settlement formula acts on is
never observable from this endpoint, and the FORMULA question may be **structurally**
unanswerable from `funding_estimate` at any density. A future run should treat "get denser
tape" as necessary-but-possibly-insufficient, and consider whether any *other* endpoint exposes
an unclamped forward rate before spending the capture budget.

## Limits

- **No P&L claim, no registry change, no bootstrap CI.** Nothing here is fillable. A funding
  number is `broker_truth`; treating it as a price would be the pt1 mistake.
- The tuned-θ column is an in-sample upper bound, explicitly *not* a discovered venue constant.
- The cluster-robust p is Monte-Carlo (seeded, reproducible); its floor is `1/(n_perm+1)` and
  its cross-seed spread is reported rather than hidden — but with ~7 exceedances the Poisson SE
  alone spans ≈2.2e-05 … 5.3e-05, wider than that spread, so the p is an order of magnitude,
  not a 2-digit number.
- The density strata are **post-hoc** cuts over a **9-cut searched family** (a floor: the values
  `8` and `0.75` were chosen after seeing the data). They are reported as a diagnostic, never as
  a fitted result, and no p read off them survives Bonferroni. The gap-monotonicity flag across
  them is a **tautology** (nested subsets) and carries no information; the matched-size
  random-subset baseline is the statistic that does.
- Q42's carry thesis is untouched. Part 3 remains **BLOCKED(needs-auth)**.

## Reproduce

```
python3 scripts/q42_funding_estimate_path_inference.py
python3 scripts/q42_funding_estimate_path_inference.py --json-out /tmp/q42pathinf.json
python3 scripts/q42_funding_estimate_path_inference.py --n-perm 20000 --seed 7   # faster / seed sweep
python3 scripts/q42_funding_estimate_path_inference.py --n-subset-draws 2000     # faster baseline
```

Reads `tape/perp_tape/dt=*.jsonl` (committed), offline, no network. Runtime ~8s including
4 x 200,000 permutation draws and 2 x 20,000 random-subset draws. The integrity-gate block
prints first; if any cell mismatches, the run says so and the inference below it must not be
read as this milestone.

> **Provenance note (added 2026-07-27, gate repair — a POPULATION change, not a correction
> to any number above).** Every number in this file was computed over the **eight** day-files
> committed on 2026-07-24: `dt=2026-07-17.jsonl` … `dt=2026-07-24.jsonl`, **1,667 records**
> (see *Artifacts* below). `perp_tape` is a **live, still-growing** family and has since
> gained `dt=2026-07-25/26/27`, so the default `--tape` glob above **no longer selects this
> milestone's population**: it now reads 11 day-files / 1,803 records and yields 364 joined
> windows and **58** discriminating windows instead of 286 / **42**, with the leave-one-out
> decomposition at 89 = 8 + 23 + 58 (not 67 = 7 + 18 + 42) and the random-subset baselines at
> p11 = 0.3655 / p14 = 0.2390 (not 0.2056 / 0.1042). The old day-files were verified
> **byte-identical** between the finding commit `cebe691` and 2026-07-27 `HEAD` (blob-by-blob),
> as was `scripts/q42_funding_estimate_path_inference.py` — the drift is pure tape growth, and
> every number here still reproduces **EXACTLY** on the frozen eight-day slice. To re-run it,
> either pass a slice-restricted `--tape` pattern or run the tape pins, which now hold the
> slice as an explicit constant (`_FROZEN_TAPE_SLICE_DAYS`):
>
> ```
> python -m pytest -q tests/test_q42_funding_estimate_path_inference.py -k tape
> ```
>
> The integrity gate is the thing that catches this: on the full glob it reports MISMATCH and
> tells you not to read the inference as this milestone — exactly as designed.

## Artifacts

- `scripts/q42_funding_estimate_path_inference.py` — emits the density-stratified separation
  table (now with a Bonferroni column over the 9 searched cuts), the gap-monotonicity summary
  **labelled as a tautology**, the matched-size **random-subset baseline**, the **67-drop
  leave-one-out scan**, the misclassification/density contrast **with separate permutation
  p's for lead and sample count**, the exact hard-gap permutation p, and BOTH the naive and
  cluster-robust independence p-values.
- `tests/test_q42_funding_estimate_path_inference.py` (87 tests at publication, **88** after
  the 2026-07-27 gate repair; 24 in the `=== correction ===` block, 19 in the
  `=== correction round 2 ===` block, of which **5** are read-only tape pins for the
  leave-one-out and random-subset numbers quoted above — 4 originals plus the new
  frozen-slice population ratchet)
- tape read: `tape/perp_tape/dt=2026-07-17.jsonl` … `dt=2026-07-24.jsonl` (1,667 records) —
  now pinned as `_FROZEN_TAPE_SLICE_DAYS` in the test module, not an open-ended `dt=*` glob
  (see the *Provenance note* under **Reproduce**)

---

## Correction (2026-07-24, post-verifier **round 2**)

A **second independent `verifier`** re-read the corrected note and returned
**CONFIRMED-WITH-CAVEAT**: the verdict (**H1 UNDECIDABLE**; **Result 1** as the
density-independent headline) **SURVIVES and is reinforced**. The integrity gate and Result 1
were re-confirmed to the digit. Five things below it did not survive, and are fixed above
rather than quietly rewritten:

1. **Arithmetic error in the leave-one-out decomposition (MANDATORY).** The note said "67 drops
   (13 tickers + 22 funding_times + 42 windows)". 13 + 22 + 42 = **77**. The total 67 is right;
   the decomposition was wrong. Re-derived from the tape: the *discriminating* population spans
   **7 tickers** and **18 funding_times** (not the full join's 13 / 22), so
   **7 + 18 + 42 = 67**. Fixed at both sites, and pinned by
   `test_tape_leave_one_out_67_drops_decomposes_as_7_18_42`.
2. **The leave-one-out claim was not re-runnable from the shipped artifact (MANDATORY).** The
   number was true — the verifier reproduced it independently — but it existed only in a
   throwaway session, violating CLAUDE.md's trust default ("no claim enters `kb/` without a
   re-runnable script"). `leave_one_out_gap_scan()` now ships in the script, performs all 67
   drops, and prints max/min gap plus the count of drops that restore a hard gap. Re-derived:
   **0 drops restore a hard gap**, max gap over all drops **−2.8216e-05**
   (argmax: drop `funding_time = 2026-07-21T04:00:00Z`), pooled gap **−1.3016e-04**. Tape-pinned
   by `test_tape_no_leave_one_out_drop_restores_a_hard_gap` and
   `test_tape_leave_one_out_max_gap_is_still_negative`.
3. **The gap-monotonicity flag is a TAUTOLOGY.** `gap(S) = min{|g| : fin≠0} − max{|g| : fin=0}`
   can only rise on a nested subset, so `gap_is_monotone_in_density → True` is guaranteed by
   construction for the nested `min_samples` chain and carries **zero information**. The
   script's docstring asserted the **opposite** ("a nested chain of subsets, so a monotone trend
   there is meaningful") — that is now fixed and pinned as a tautology
   (`test_gap_monotonicity_is_a_tautology_on_any_nested_chain`), and
   `pooled_overlap_is_density_confounded = bool(hard) and bool(mono)` is documented as reducing
   to `bool(hard)` (the `and mono` conjunct is inert). The replacement statistic that *does*
   carry information — matched-size random subsets, re-derived seeded — gives
   **P(hard gap | random 11-of-42) = 0.2056** and **P(random 14-of-42) = 0.1042**, so neither
   dense cut beats an arbitrary same-size cut. What survives is the **measurement-validity**
   argument, which the verifier explicitly endorsed as what makes the verdict hold: a `g_last`
   computed from an estimate published 4.95h before close (median lead 1.47h, max 4.99h of an
   8h window) is simply **not a measurement of "the last estimate before `funding_time`."**
   Separately, round 1 blurred a **supported** claim with an **unsupported** one: the
   failures-vs-successes contrast is real on **lead** (+1.594 h staler, permutation
   p = **0.00112**, 200k draws) but **not** on **sample count** (−0.906 samples, p = **0.285**
   one-sided / 0.557 two-sided). The "median 2.0 samples (6 of 10 have exactly 2)" line was
   headlined beside the lead figure as if both were supported; the two are now reported
   separately with their own p's, and the script says which half is supported.
4. **Per-ticker carrier count was over-counted.** "~3 of 13 tickers" → **2 of 13** (ZEC 0.01238,
   SUI 0.03636). HYPE's 0.04545 is exactly 1/22 from a single degenerate window
   (a=1, b=0, c=0, d=21) and is not a real carrier. The verifier adjudicated the per-ticker
   table itself as **correct** against the first verifier's summary (NEAR does not survive,
   p = 0.293), so only the phrasing changed. Added: the 13 per-ticker Fisher p's carry **no
   multiplicity correction** (ZEC 0.0124 × 13 = 0.16).
5. **Post-hoc multiplicity was described in words but never counted.** The declared strata are
   `MIN_SAMPLE_STRATA = (1,2,3,4,5,8)` + `MAX_LEAD_STRATA_HOURS = (0.75,1.0,2.0)` = **9 cuts
   searched**. Bonferroni over 9: `lead<=0.75h` 0.010989 × 9 = **0.0989**; `n>=8` 0.090909 × 9 =
   **0.818** — **neither significant at 0.05**. The effective family is **larger** than 9,
   because the specific values `8` and `0.75` were themselves chosen after seeing the data. This
   **strengthens** the verdict: those p's are used only to argue H1 **cannot be confirmed** here.

Also corrected in place: the naive Fisher p = 5.299656e-10 in the reproduced-items list is now
tagged **NAIVE/pseudo-replicated** where it appears, not six lines later; and the 4-seed
cluster-p spread (2.5e-05 … 4.5e-05) is noted to **understate** the true Monte-Carlo
uncertainty (with ~7 exceedances the Poisson SE alone gives ≈2.2e-05 … 5.3e-05).

**The verdict sentence is unchanged: H1 is UNDECIDABLE at current tape density.** Two rounds of
independent review moved every supporting number and left the verdict where it was — which is
the case for keeping the error log in the file instead of rewriting history.
