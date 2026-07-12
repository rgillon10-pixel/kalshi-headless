# Running Log — kalshi.headless KB

Append-only. Newest at top. Each entry: `## YYYY-MM-DD HH:MM ET — title`,
then what happened, what it means, and links to the note/script it produced.
Dead ends stay. This is the journey; `git` is the diff.

---

## 2026-07-12 — Stranded-tape sweep (1,708 lines) + Q12/S17 lead-lag first cut

- **Step 0a passed.** The 5 most-recently-merged PRs (#44, #43, #42, #41, #40)
  are all reachable from `origin/main`. `kb/00-LOG.md`'s newest entry and the
  newest `tape/*/dt=*` file are both 2026-07-12 (0-day gap). `main` not
  rewound — an initial `git fetch origin main` reported "forced update";
  traced to this session's shallow clone (`--depth 50`) truncating the
  commit graph before the fetch, not a real history rewrite (confirmed via
  `git fetch --unshallow` + re-checked ancestry, and independently via the
  merged-PR reachability + log/tape date-parity checks). Only open PR is #4
  (Q1 odds-api leg), unrelated, now **9 days old** awaiting `ODDS_API_KEY` —
  past the 5-day escalation mark, flagged `Priority: high` in this run's
  phone note again.
- **Step 0b stranded-tape sweep (1,708 lines).** `git reset --hard
  origin/main` first. Of 97 `tape/hourly-*` branches, two postdated PR #44's
  sweep cutoff and were well past 30min old: `tape/hourly-20260712T0458Z`
  and `tape/hourly-202607120557Z`. Content-diffed against `main`'s current
  tape: `crypto_hourly` +4, `orderbook_depth` +1,349,
  `polymarket_macro_pairs` +30, `polymarket_pairs` +8, `sports_pairs` +317 —
  1,708 lines total, all JSON-validated, 0 exact duplicates. Committed and
  pushed standalone so `main` was current before the milestone landed.
  Branch-delete not attempted (documented permission boundary).
- **Milestone: no numbered queue item was eligible.** Q1 still claimed by
  open PR #4; Q7/Q9/Q16 DONE; Q13 still BLOCKED (`tape/sports_pairs/` has 9
  valid canonical `.jsonl` days, needs ≥10, eligible ~07-13); Q14/Q15 still
  data-adequacy BLOCKED. The lessons ledger's own standing UNENFORCED
  candidates were checked first (L23's "empty ≠ drop" generalization: audited
  `sports_pairs.py`/`crypto_hourly.py`/`polymarket_pairs.py` — all already
  use honest None-propagation for a genuinely-missing quote and DROP only on
  a real fetch/parse failure, so there is no live gap to close there, unlike
  L22's case; L27/L28/L32's own candidates are already importable in
  `core/bootstrap.py` and wait on an actual future probe, not further loop
  work). Instead drew on **Q12/S17's own remaining-work note** — genuine
  strategy-registry progress instead of another infra-only lesson closure.
- **S17 lead-lag first cut (via `edge-prober`).** Built
  `scripts/s17_leadlag_probe.py`, the S17 analog of `scripts/s9_leadlag_
  probe.py`, over `tape/polymarket_macro_pairs/` (Fed-decision leg — both
  Kalshi `yes_ask` and Polymarket `best_ask` are genuine `real_ask`, an
  apples-to-apples pair exactly like S9's WC-round comparison). Ran read-only
  over ~6 accumulated days (2026-07-06→07-12): **2,805 records, 187 distinct
  captures, 15 (meeting, bucket) pairs** (Jul/Sep/Oct 2026 meetings × 5
  buckets). Pooled panel cross-correlation of consecutive-capture deltas:
  contemporaneous ρ=+0.154 (n=2,789), kalshi-leads ρ=−0.003,
  polymarket-leads ρ=−0.028 (n=2,774 each); 215 ticks ≥1¢ on either venue.
  **0 FOMC resolve/roll-off (shock-proxy) events fell inside the window** —
  none of Kalshi's listed meetings have occurred yet, so every observed tick
  is book noise, the same data-adequacy gap S9 hit before its real
  round-transition events landed. Reported honestly as a descriptive
  noise-floor characterization, **not a verdict** (no CI, no DEAD/ALIVE
  call — L28's discipline: don't build verdict machinery before the signal
  is even observable). The CPI leg (`tape/polymarket_cpi_pairs/`, 154
  records) is `synthetic` on the Kalshi side (a derived cumulative-ladder
  difference) and was deliberately excluded from the real-ask correlation
  per Hard Rule #3 — counted for provenance only, not pooled in. `kb/
  strategies/00-index.md` S17 note updated (dated append, stays
  `data-collecting`). Full write-up:
  `findings/2026-07-12-polymarket-macro-leadlag-s17-firstcut.md`.
- **Gates:** 507 tests green (481 prior + 26 new). `python
  scripts/invariants.py --full` green — one false-positive
  `no_yes_ask_arithmetic` hit on a test docstring's prose ("kalshi.yes_ask /
  polymarket.best_ask", not real arithmetic) fixed by rewording to "and"
  before commit.

**Next:** re-run `scripts/s17_leadlag_probe.py` once a real FOMC decision
(nearest: July 2026 meeting) or CPI print lands inside the collected window
— only then does the lead-lag thesis have a real shock to test, same
resolution path S9 eventually took. Q13 (S14 ladder-underwriting fill-sim)
becomes eligible ~2026-07-13 once a 10th valid `tape/sports_pairs/` day
lands.

---

## 2026-07-12 — Stranded-tape sweep (872 lines) + L36: strike-spacing-from-ladder helper built

- **Step 0a passed.** The 5 most-recently-merged PRs (#43, #42, #41, #40, #39)
  are all directly reachable from `origin/main` (#43's squash commit `b3b76c4`
  visible in the local log). `kb/00-LOG.md`'s newest entry and the newest
  `tape/*/dt=*` file are both 2026-07-12 (0-day gap). `main` not rewound — an
  early `git fetch origin main` reporting "forced update" was traced to this
  session's shallow-clone ref catching up to a stale container-start snapshot,
  not a real rewrite (HEAD `147cffe` was unchanged before and after the
  fetch). Only open PR is #4 (Q1 odds-api leg), unrelated, now ~9 days old
  awaiting `ODDS_API_KEY` — past the 5-day escalation mark, flagged
  `Priority: high` in this run's phone note.
- **Step 0b stranded-tape sweep (872 lines).** `git reset --hard origin/main`
  first. Of 96 `tape/hourly-*` branches, two postdated the last sweep's cutoff
  and were well past 30min old: `tape/hourly-202607120401Z` and
  `tape/hourly-20260712T0258Z`. Content-diffed (`git show <ref>:<path>`)
  against `main`'s current tape: `crypto_hourly` +2, `orderbook_depth` +687,
  `polymarket_macro_pairs` +15, `polymarket_pairs` +7, `sports_pairs` +161 —
  872 lines total, all JSON-validated, 0 exact duplicates. A third branch
  (`tape/hourly-20260712T0458Z`) was skipped — its commit was only ~5min old,
  below the 30min freshness threshold. Branch-delete not attempted
  (documented permission boundary).
- **Milestone: no numbered queue item was eligible.** Q1 still claimed by
  open PR #4; Q7/Q16 DONE; Q13 still BLOCKED (`tape/sports_pairs/` has 9 valid
  canonical `.jsonl` days — 03,04,05,06,07,08,10,11,12 — needs ≥10, eligible
  ~07-13); Q14/Q15 still data-adequacy BLOCKED. Drew from the lessons
  ledger's own standing UNENFORCED queue again (same pattern as L25→L29,
  L33→L34, L32→L35): **L7** ("never hardcode a bracket/strike width — derive
  spacing from the ladder itself," filed 2026-07-04) had stayed UNENFORCED
  the longest of any remaining live row — its actual fix in
  `scripts/s8_basis_probe.py` only swapped a single fixed-$100 half-band
  check for a 2-symbol hardcoded dict (`{"BTC": 100.0, "ETH": 20.0}`), still
  a guess rather than a value read off the ladder's own strikes, and no
  importable helper existed for what the lesson's own wording asked for.
- **`core/pricing.py`**: new `infer_strike_spacing(strikes)` — dedupes and
  sorts the ladder's own strike values, returns the MEDIAN consecutive gap
  (robust to one missing or duplicated member, e.g. a thin/stale far strike),
  `None` below 2 distinct strikes. 5 new tests in
  `tests/test_substrate_primitives.py` (BTC-like $100 ladder, ETH-like $20
  ladder, one-gap-doubled robustness check, order/duplicate insensitivity,
  <2-strike None cases).
- **`.claude/agents/edge-prober.md`**: house style now names
  `core.pricing.infer_strike_spacing` alongside the existing L27/L28/L32
  bootstrap helpers, for any probe/collector that needs a ladder's own
  spacing instead of a hardcoded per-symbol guess.
- **`kb/lessons/00-lessons.md`**: appended **L36** (generalizes L7; L7 itself
  stays UNENFORCED as a ledger row per the append-only rule).
- Does not retrofit S8's already-verdicted probe (DEAD, Q5, 2026-07-04) —
  that verdict stands as-is; this is infra for the next probe/collector that
  needs to read a bracket ladder's spacing off real data.

## Gates

- 481 tests green (476 prior + 5 new).
- `python scripts/invariants.py --full` green (only the two expected
  non-gating advisories: L20 stranded-tape, L29 tape-dir-shape).

Research/tape/docs only — no order or execution code, no credential
handling.

---

## 2026-07-12 — Stranded-tape sweep (873 lines) + L35: frozen-pair dual-cut bracketing helper built

- **Step 0a passed.** The 5 most-recently-merged PRs visible in local history
  (#42, #41, #40, #39, #38) — #38 falls outside this session's shallow clone
  depth but was independently confirmed reachable by a prior run, and #42/#41/
  #40/#39 are all directly visible in `origin/main`'s log. `kb/00-LOG.md`'s
  newest entry and the newest `tape/*/dt=*` file are both 2026-07-11 (0-day
  gap, pre-sweep). `main` not rewound. Only open PR is #4 (Q1 odds-api leg,
  unrelated, still a draft, now ~9 days old awaiting `ODDS_API_KEY` — past the
  adopted 5-day escalation mark, flagged `Priority: high` in this run's phone
  note).
- **Step 0b stranded-tape sweep (873 lines).** `git reset --hard origin/main`
  first. Of 93 `tape/hourly-*`/`-corrected-`/`-followup-`/`-amended-` branches,
  two postdated the last sweep's cutoff (`tape/hourly-20260711T1501Z`/`1806Z`)
  and were well past 30min old: `20260711T205500Z` and `20260711T2156Z`.
  Content-diffed (line-set union, not commit ancestry — this session's shallow
  clone has no merge-base with these branches, so `git show <branch>:<path>`
  was used to read each branch's file content directly) against `main`'s
  current tape: `crypto_hourly` +4, `orderbook_depth` +466,
  `polymarket_macro_pairs` +30, `polymarket_pairs` +20, `sports_pairs` +353 —
  873 lines total, all JSON-validated, 0 exact duplicates against `main`.
  Branch-delete not attempted (documented permission boundary).
- **Milestone: no numbered queue item was eligible.** Q1 still claimed by open
  PR #4; Q7/Q16 DONE; Q13 still BLOCKED (`tape/sports_pairs/` has 9 valid
  canonical `.jsonl` days — 03,04,05,06,07,08,10,11,12 — needs ≥10, eligible
  ~07-13); Q14/Q15 still data-adequacy BLOCKED. Drew from the lessons ledger's
  own standing UNENFORCED queue again (same pattern as L25→L29 and L33→L34):
  L34 closed L27/L28's "probe-precedent encodes it" gap but left **L32**
  (frozen-pair no-fill precheck + dual-cut bracketing, from S6's first-cut)
  as the one still-open UNENFORCED candidate in that lineage — `core/bootstrap.py`
  had no importable counterpart for it, so a future maker/spread-style probe
  built over repeated snapshots would still hand-roll the frozen-vs-movement
  split from scratch.
- **Built `core/bootstrap.py::bracket_by_movement(frozen_flags, values)`** —
  takes the caller's already-computed per-observation frozen flags (L6-style:
  it never inspects raw book fields itself, "frozen" stays a per-probe
  judgment call) and returns the frozen-inclusive value list, the
  movement-conditioned value list (frozen entries removed), and the frozen
  fraction. 6 new tests in `tests/test_bootstrap.py` (empty input honesty,
  all/none/partial frozen, movement-conditioned exclusion, length-mismatch
  raises). Does not retrofit S6's already-verdicted probe — that verdict
  stands as-is; this is for the next snapshot-based probe that needs the
  frozen/movement split (S6-successor or S11, whenever its own data blocker
  clears).
- **`.claude/agents/edge-prober.md` house style updated** to name
  `core.bootstrap.bracket_by_movement` alongside the L27/L28 helpers, for any
  probe built over repeated same-entity snapshots rather than one-shot trade
  outcomes.
- Recorded **L35** in `kb/lessons/00-lessons.md` (generalizes L32; L32 itself
  stays UNENFORCED as a ledger row per the append-only rule).
- Gates: 476 tests green (470 prior + 6 new), `python scripts/invariants.py
  --full` green (only the two expected non-gating advisories: L20
  stranded-tape and L29 tape-dir-shape).

## 2026-07-11 (later run) — Stranded-tape sweep (1,936 lines) + L34: bootstrap-helper protocol encoded into edge-prober charter

- **Step 0a passed.** The 3 most-recently-merged PRs visible in local history
  (#41, #40, #39) are all reachable from `origin/main` (local branch head equals
  `origin/main` tip, `ade6160`); `kb/00-LOG.md`'s newest entry and the newest
  `tape/*/dt=*` file are both 2026-07-11 (0-day gap). `main` not rewound. Only
  open PR is #4 (Q1 odds-api leg, unrelated, unmerged, ~8 days old — still
  awaiting `ODDS_API_KEY`).
- **Step 0b stranded-tape sweep (1,936 lines).** Of the 91 `tape/hourly-*`
  branches, two postdated the last sweep's cutoff (`tape/hourly-20260711T1256Z`)
  and were >30min old: `20260711T1501Z` and `20260711T1806Z`. Content-diffed
  (line-set, not commit ancestry) each against `origin/main` per family, then
  unioned the two branches' missing lines: `crypto_hourly` +4, `orderbook_depth`
  +1,507, `polymarket_macro_pairs` +30, `polymarket_pairs` +20, `sports_pairs`
  +375 — 1,936 lines total, all JSON-validated, 0 exact duplicates against
  `main`. Branch-delete not attempted (documented permission boundary).
- **Milestone: no numbered queue item was eligible.** Q1 still claimed by open
  PR #4; Q7/Q16 DONE; Q13 still BLOCKED (`tape/sports_pairs/` has 8 valid
  canonical days — 03,04,05,06,07,08,10,11 — needs ≥10, eligible ~07-13);
  Q14/Q15 still data-adequacy BLOCKED. Drew from the lessons ledger's own
  standing UNENFORCED queue again: L33 (prior run) built `core/bootstrap.py`
  but explicitly left undone the "probe-precedent encodes it" half of L27/L28's
  own candidate wording — the helper existed, but nothing yet told a future
  probe to reach for it instead of hand-rolling a new resample loop.
- **Closed that gap in `.claude/agents/edge-prober.md`** — the one file every
  probe milestone is required to read before writing code. Its house-style
  section now names `core.bootstrap.block_bootstrap` /
  `clears_tick_magnitude` / `floor_pinned_fraction` explicitly, and the
  three-outcome verdict rule is sharpened so a CI>0 that fails the
  tick-magnitude gate is counted as DEAD, not left as a vague "worth
  flagging." Docs-only — no probe re-run, no verdict re-opened, no source
  code touched. New lesson **L34** filed in `kb/lessons/00-lessons.md`
  recording the closure; L27/L28 stay individually UNENFORCED as ledger rows
  (append-only) since the ledger's own rule is ledger rows never get rewritten,
  but the candidate they described is now live in the charter — full
  resolution still waits on an actual probe using it. 470 tests unchanged
  (docs-only commit), `invariants.py --full` green (only the two pre-existing
  non-gating advisories: L20 stranded-tape, L29 tape-dir-shape).
- LOOP-QUEUE.md: Log-of-runs line appended. No Q-item status line changed
  (this milestone isn't tied to a specific numbered item).

## 2026-07-11 (later run) — Stranded-tape sweep (223 lines) + L33: shared block-bootstrap helper

- **Step 0a passed.** The 5 most-recently-merged PRs (#40, #39, #38, #37, #36) are all
  reachable from `origin/main`; `kb/00-LOG.md`'s newest entry and the newest
  `tape/*/dt=*` file are both 2026-07-11 (0-day gap). `main` not rewound. (The initial
  shallow clone's stored `origin/main@{1}` ref looked like a rewind under
  `merge-base --is-ancestor` — that was the shallow-history boundary, not a real rewind;
  confirmed via the merged-PR reachability check + the log/tape date parity, not the
  git-ancestry heuristic alone.)
- **Step 0b stranded-tape sweep (223 lines).** `git reset --hard origin/main` first.
  Of the `tape/hourly-*` branches, one (`tape/hourly-20260711T1256Z`) was >30min old
  and not yet covered by PR #40's sweep; its content-diff against `main` (line-set,
  not commit ancestry) found real gaps in today's files despite `main` already having
  *more total lines* per file (a later, different pass) — `crypto_hourly` (+2),
  `polymarket_macro_pairs` (+15), `polymarket_pairs` (+10), `sports_pairs` (+196);
  `orderbook_depth` had 0 missing. All lines JSON-validated, 0 exact duplicates.
  Branch-delete not attempted (documented permission boundary).
- **Milestone: no numbered queue item was eligible.** Q1 still claimed by open PR #4
  (odds-api key, now 8 days old); Q7/Q16 DONE; Q13 still BLOCKED (`tape/sports_pairs/`
  has 8 valid canonical days — 03,04,05,06,07,08,10,11 — needs ≥10, eligible ~07-13);
  Q14/Q15 still data-adequacy BLOCKED. Drew from the lessons ledger's own standing
  UNENFORCED queue instead (same pattern as L25→L29): **L27** (magnitude-vs-tick CI
  gate) and **L28** (floor-pinned-fraction precheck) were both filed as "likely
  terminal as protocol... once a probe-precedent encodes it," but no probe-precedent
  actually existed yet — every bootstrap-using script (`s6_maker_firstcut.py`,
  `s10_reachability_probe.py`, `s7c_sports_clv_bootstrap.py`) still hand-rolls its own
  block-bootstrap loop from scratch.
- **Built `core/bootstrap.py`:** `block_bootstrap` (generic by-unit block resample —
  takes an already-grouped-by-unit mapping, L6-compliant, never guesses the grouping
  key itself), `clears_tick_magnitude` (L27's sign-*and*-magnitude gate — S10's own
  near-miss CI `[+0.000000, +0.000024]` correctly fails it against a 1¢ tick),
  `floor_pinned_fraction` (L28's cheap-before-expensive floor-observability precheck).
  17 new offline tests in `tests/test_bootstrap.py` (empty-input honesty, determinism
  given a seed, CI-width sanity, both gate functions against S6/S10's own real numbers).
  Does NOT retrofit the already-verdicted S6/S10 probes — those verdicts stand; this is
  infra for the next probe that needs a bootstrap (S11/S14/S16/S18, once their own data
  blockers clear). New lesson **L33** filed in `kb/lessons/00-lessons.md` recording the
  compounding. 470 tests green (453 prior + 17 new), `invariants.py --full` green (only
  the two pre-existing non-gating advisories: L20 stranded-tape, L29 tape-dir-shape).
- LOOP-QUEUE.md: Log-of-runs line appended. No Q-item status line changed (this
  milestone isn't tied to a specific numbered item).

## 2026-07-11 — S6 milestone: inventory-aware market-making (earn-the-spread-as-maker) → DEAD (first cut, verifier-CONFIRMED)

- **Drawn from the registry's own priority order, not a numbered Q-item.** The numbered queue
  had drained to externally-blocked items (Q1 claimed by PR #4 awaiting `ODDS_API_KEY`;
  Q13/Q14/Q15 data-adequacy BLOCKED), so this milestone came from the standing registry: S6 was
  the topmost `data-collecting` candidate with enough accumulated tape to test.
- **The probe.** `scripts/s6_maker_firstcut.py` (read-only, 15 offline tests) built a
  quote-displacement proxy over 4 accumulated days of `tape/orderbook_depth/` (2026-07-07, 07-08,
  07-10, 07-11; ~58,583 records → 36,738 consecutive two-sided pairs ≤90 min apart). Per ticker
  seen in two consecutive hourly captures: book the capture-1 quoted half-spread as maker income
  if filled, charge the full hour's mid displacement as adverse selection, net of the maker fee
  from `core.pricing.fee_per_contract` (never hand-rolled — L18). Honest scope stated up front:
  hourly snapshots cannot observe a real fill, queue position, or message-level adverse selection,
  so this can only show the gate is unmeetable on the realistic population, not measure a live
  edge. Bootstrap unit = the **ticker** (pairs within one game/bracket are correlated draws — L6).
- **L28 precheck first:** 25,618/36,738 = **69.7%** of consecutive pairs are frozen (BBO
  unchanged) — correctly booked as $0 no-fill income, not phantom spread capture.
- **Verdict: DEAD (first cut).** By-ticker block-bootstrap (10,000 resamples, seed 42) of net
  maker P&L is **strictly < 0** on every economically-realistic two-sided cut: ≤2¢ mean
  −$0.01120, ≤5¢ −$0.00619, ≤10¢ (primary, frozen-inclusive, max-generous) −$0.00195 95% CI
  [−$0.00297,−$0.00094], and the honest movement-conditioned ≤10¢ cut −$0.02010 CI
  [−$0.02271,−$0.01759]. The only population with CI>0 is the **>30¢ wide-wing artifact**
  (+$0.339/contract, 99.9% "profitable") — a nominal, not maker-capturable, spread on far/one-
  sided brackets (wide *because* one side is empty); the naive "ALL two-sided" +$0.06928 mean was
  entirely this wing. **Structural killer:** the maker fee is a **flat 1¢/contract** at every
  interior price (`ceil(0.0175·P·(1−P)·100)/100 = 0.01` for all `0<P<1`), which alone consumes
  the modal Kalshi book's 1–2¢ two-sided spread before adverse selection is even charged — the
  same fee-floor mechanism that killed S13. More days of the *same* hourly-cadence tape cannot
  fix a structural cap.
- **Verifier CONFIRMED** (not merely plausible). Independently reproduced every number and swept
  ≤15/20/25/30¢ trying to find an alive population — the only frozen-inclusive CI>0 (≤30¢,
  +$0.00229, a quarter-cent) fails L27's magnitude-vs-tick gate and is itself wing-driven; under
  the movement-conditioned cut every threshold is strictly negative. **Out of scope / NOT
  falsified:** the *selective* maker (S11) — quote only wide-enough, low-toxicity books with an
  external fair-value anchor and a real fill-sim; S6's naive "quote everything at the BBO" is
  what's dead.
- **Compounded:** `kb/strategies/00-index.md` S6 flipped `data-collecting → dead ✗` (row + gate
  cell + a third dated verdict note + the "0 proven edges" running tally: S1/S5/S7/S8/S9/S13/S10/S6
  now all decided at real asks, none live). Three lessons appended to `kb/lessons/00-lessons.md`:
  **L30** (the maker fee is a flat 1¢/contract at every interior price — sharpens L5/L18's "4×
  cheaper" into a hard floor; enforcement **test**, pinned by the probe's existing value-sweep
  test — a numeric property of the fee function, not a static-text invariant), **L31** (a >30¢
  spread on a far/one-sided bracket is a nominal, not maker-capturable, spread — generalizes
  L12/L26's floor-artifact caution to the spread-capture direction; **ledger-only**, venue
  microstructure + per-probe methodology), **L32** (a frozen consecutive pair is a no-fill, not
  free income — report the frozen fraction as an L28 precheck and bracket the verdict with both
  frozen-inclusive and movement-conditioned cuts; **UNENFORCED**, per-probe methodology, likely
  terminal as protocol). Finding: `findings/2026-07-11-mm-spread-s6-firstcut.md`.
- Gates: `pytest -q` green, `python scripts/invariants.py --full` green (only the two pre-existing
  non-gating advisories: L20 stranded-tape and the L29 tape-dir-shape warning). Docs-only change
  (kb/ only — the probe, its tests, and the finding were already committed).

## 2026-07-11 05:xx UTC — research loop: stranded-tape sweep (1,551 lines) + L25→L29 (tape dir-shape invariant built)

Step 0a history-integrity check passed: the 5 most-recently-merged PRs (#37, #36, #18, #35,
#33) are all reachable from `origin/main` (confirmed via commit-message search post
squash-merge, since PR head SHAs are never ancestors under this repo's convention);
`kb/00-LOG.md`'s newest entry and the newest `tape/*/dt=*` file are both 2026-07-11 (0-day
gap). `main` is not rewound. Open PRs: only #4 (Q1 odds-api leg), still claimed, now ~8 days
old awaiting `ODDS_API_KEY` — past PR #18's adopted 5-day escalation mark, flagged
`Priority: high` again in this run's phone note.

**Step 0b stranded-tape sweep.** `git reset --hard origin/main` first (per the adopted
retro amendment). Of 86 `tape/hourly-*`/`-amended-`/`-corrected-`/`-followup-` branches, the
3 most recent since the last sweep (`20260711T000050Z`, `20260711T0254Z`, `20260711T0356Z`,
all >30min old) carried real line-set gaps against `main`; `20260711T0154Z` diffed to zero
missing lines (already reconciled — its content landed on `main` directly via the same-
timestamp commit `308d9fc`). Union-appended **1,551 lines** `main` was missing —
`crypto_hourly` +6 (2+4 across the two affected days), `orderbook_depth` +827,
`polymarket_macro_pairs` +45, `polymarket_pairs` +30, `sports_pairs` +643 — every line
JSON-validated, 0 exact duplicates (confirmed via a `sort`+`sort -u` line-count parity check
per target file post-append). Branch-delete not attempted (documented permission boundary,
per the adopted amendment).

**Milestone: converted lesson L25 into a live invariant (no numbered queue item was
eligible — Q13 still BLOCKED at 8/10 valid days of `tape/sports_pairs/`, Q14/Q15 still
data-adequacy BLOCKED, Q1 still claimed by PR #4).** Built
`scripts/invariants.py::_tape_dir_shape_issues()` / `tape_dir_shape_warning()`, the exact
enforcement L25 asked for: a non-gating advisory (same pattern as L20's stranded-tape
warning) that scans every `tape/<family>/dt=<date>` path and flags any that is a
**directory** instead of the canonical `.jsonl` file — the shape of bug that let the
2026-07-08 main-rewind's regression silently miscount a day-count gate. Wired into
`--full`'s existing warning block. Live-validated against the real committed tree: it
correctly flags the 4 stray directories that regression left behind and were never cleaned
up (`crypto_hourly/dt=2026-07-10`, `sports_pairs/dt=2026-07-02`, `sports_pairs/dt=2026-07-09`,
`sports_pairs/dt=2026-07-10`) — confirming both that the check works on real data and that
those directories are still sitting there (cleanup/reprocessing is separate follow-up work,
flagged, not done here). 6 new tests (438 total, 432 prior + 6 new). Recorded as **L29**
(supersedes L25) in `kb/lessons/00-lessons.md`.

Gates: 438 tests green, `python scripts/invariants.py --full` green (only the two
non-gating advisories: stranded-tape L20 and the new L25/L29 dir-shape warning, both
expected and harmless). No source-code milestone changed a queue Status line; Q13 day-count
re-confirmed off disk (8 valid canonical days: 03,04,05,06,07,08,10,11 — not yet 10).

## 2026-07-11 00:27 UTC — Q7 milestone: S10 crypto-hourly reachability decay → STRUCTURAL DEAD (verifier-CONFIRMED)

- **Q7 became eligible this run.** The `crypto_hourly` tape crossed **7 valid canonical days**
  (2026-07-03..08 plus a reprocessed 07-10 `.jsonl`) — the L25 stray `dt=2026-07-10/`
  directory-of-blobs day correctly excluded via a `*.jsonl` glob + `is_file` guard, so the
  day-count is honest this time.
- **The probe.** `scripts/s10_reachability_probe.py` (read-only, `+16` offline tests) tested
  S10's thesis (far range-brackets stay priced above their remaining-time reachability late in
  the hour → a taker could fade the rich tail). No continuous intra-hour tape exists, so it used
  the only within-hour time variation available — the two collectors (cloud + VPS) hitting the
  same hourly group at different offsets (~40 min vs ~5 min pre-close), an EARLY vs LATE capture
  — and used the realized `broker_truth` settlement as ground truth instead of fabricating a
  hitting-probability model on thin data. Bootstrap unit = the **hour** (brackets within an hour
  are correlated draws — L6), entry prices `real_ask`, settlement `broker_truth`.
- **Verdict: DEAD, structural — not a marginal miss.** Two independent walls, both mechanical:
  (1) the decay the thesis needs is not observable — far brackets were already 1¢-YES-floor-pinned
  ~40 min before close (mean early→late Δ`yes_ask` +0.00014); (2) the taker trade has no fillable
  price — a floor-pinned YES (`yes_bid=0`) mirrors into a **\$1.00 NO ask**, so only 4/18,992 far
  obs (0.02%, 3 of them from a single hour) had any `no_ask<\$1` room, and `fee_per_contract(\$1.00)=0`
  makes the ideal floored trade net exactly \$0. Block-bootstrap-by-hour (n=164 hrs/18,992 obs,
  10,000 resamples): mean **+\$0.000008**, 95% CI **[+\$0.000000, +\$0.000024]** — lower bound a
  floating-point 0, magnitude 3 orders below the 1¢ tick. No threshold (0.01→0.10) clears zero.
  Same cheap-kill family as S8's ρ-guard; more data cannot fix a mechanically-capped trade.
- **Verifier CONFIRMED** (not merely plausible). One caveat that does not move the verdict:
  in-sample 0/18,992 far brackets actually hit, so the point estimate is slightly
  survivorship-flavored — but the writeup already treats +\$0.000008 as rounding residue, and the
  kill is the tick-mirror mechanism, not the sample. **Out of scope / not falsified:** the MAKER
  side (rest a NO offer or sell the rich YES at the elevated ask rather than crossing to a \$1.00
  NO ask) — S6/S11 territory, needs the L2 depth tape + a fill-sim.
- **Compounded:** `kb/strategies/00-index.md` S10 flipped `idea → dead ✗` (row + verdict note +
  running-tally update). Three lessons appended to `kb/lessons/00-lessons.md`: **L26** (the 1¢
  YES tick mirrors to a \$1.00 NO ask on floor-pinned brackets ⇒ a tail-fade is structurally a
  maker trade, not a taker one — generalizes L12; enforcement **ledger-only**, venue arithmetic),
  **L27** (`fee(\$1.00)=0` is correct, but a CI dominated by ~\$1.00 legs can show a floating-point
  +0.000000 lower bound — every CI verdict needs a magnitude/economic-significance gate vs the 1¢
  tick, not just a sign check; **UNENFORCED**), **L28** (verify the artifact floor is even
  *observable* — check the early-capture floor-pinned fraction — before building a decay/CI
  pipeline; **UNENFORCED**). L27/L28 stay kb-only this milestone (scope limited to `kb/`); both
  are per-verdict/per-probe methodology gates, likely terminal as **protocol** in probe precedents
  rather than static invariants. Finding: `findings/2026-07-11-crypto-reachability-s10-firstcut.md`.
- Gates: `pytest -q` green, `python scripts/invariants.py --full` green (only the pre-existing
  non-gating stranded-tape advisory). Docs-only change.

## 2026-07-10 16:50 ET — Burst-capture legs approved + built; ntfy topic moved out of the public repo (ops, Ryan-interactive)

- **Burst captures approved.** The S9 lead-lag resolution (2026-07-06) had flagged
  sub-hourly event-window captures as a new automation class needing Ryan's sign-off;
  Ryan gave it today. Built `collection/burst_capture.py` (+15 offline unit tests, 420
  total green, `invariants --full` green): a thin loop harness over the existing
  collectors' one-pass functions (`wc`/`fed`/`cpi`/`econ`/`crypto`/`sports` families),
  `--until`/`--interval`/`--families` CLI, overrun-skips-boundaries timing, per-family
  fault isolation, honest AND-completeness. No new tape family, no schema change —
  burst lines are distinguishable by `fetch_ts` density alone. Live smoke pass (2
  crypto ticks @20:44 UTC) honestly reported `completeness FAIL` — the documented L15
  venue-side 20-UTC-hour crypto hole, not a collector fault; lines kept as real tape.
- **Five one-shot cloud triggers created** (Ryan's account, not the repo): June-CPI
  print Jul 14 12:05→13:45Z; WC semi 1 Jul 14 and semi 2 Jul 15 20:10→22:30Z; WC final
  Jul 19 20:10→22:45Z (last-ever KXWCROUND capture window); FOMC decision Jul 29
  17:40→19:45Z. Each carries a hard date guard against annual cron re-fire. Protocol
  section "Burst-capture legs" appended to `LOOP-QUEUE.md`; step 0b's sweep now also
  covers `tape/burst-*` fallback branches. Why it matters: this is exactly the data
  class whose absence made S9's lead-lag thesis untestable — S17's lead-lag question
  becomes testable on this tape.
- **ntfy topic migration (step 8(e)).** The repo went public 2026-07-10 and ntfy.sh
  topics are world-writable — the committed topic name let anyone inject priority-5
  messages into the `ntfy-watch` responder. New secret topic generated; all 5 cloud
  routine prompts updated to carry the URL privately; local sessions read
  `~/.claude/secrets/kalshi-ntfy-topic`; VPS flip to `/root/.secrets/kalshi-headless.env`
  pending (Ryan action); `config/notify.topic` stays only as the retired fallback until
  then. The new topic name is committed NOWHERE in this repo, by design.
- Worker lesson candidates (per-family completeness conventions; overrun-test
  offset-sequence pinning; fresh L15 corroboration) recorded in the builder's report —
  left for the next kb-distiller pass.

## 2026-07-10 20:xx UTC — Research loop: stranded-tape sweep (5,125 lines) + tape-format-regression finding

Step 0a history-integrity check: PASS. The 5 most-recently-merged PRs' squash/merge commits
(#18, #35, #33, #32, #31 — verified by commit-message search after unshallowing the local
clone, not by branch-head SHA, since squash-merges rewrite the commit object) are all
reachable from `origin/main`; `kb/00-LOG.md`'s newest dated entry and the newest `tape/*/dt=*`
file are both 2026-07-10 (0-day gap). `main` is not rewound.

Step 0b stranded-tape sweep: fetched + content-diffed all 80 `tape/hourly-*` branches (line-set
diff per tape file, not commit ancestry — this repo's PRs are squash-merged so a branch head's
raw SHA is never an ancestor of `main` even when fully reconciled). ~70 pre-2026-07-08 branches
were already fully reconciled (0 missing lines — the pre-reset lineage's own sweeps plus
today's PR #35 recovery already cover them). Found real gaps in 9 branches: 3 from right at/
after the 07-08T10:56Z reset event (`tape/hourly-20260708T1101Z`/`1102Z`/`1103Z`) and 6 from
today (`tape/hourly-202607100655Z` through `20260710T1656Z`). Union-appended **5,125 lines**
`main` was missing across `crypto_hourly`, `orderbook_depth`, `polymarket_macro_pairs`,
`polymarket_pairs`, and `sports_pairs` — every line JSON-validated, 0 exact duplicates
introduced (verified via `sort -u` line-count parity per file). `tape/hourly-20260710T1955Z`
(committed ~14 minutes before this check, under the 30-minute freshness rule) was left for the
next run.

**Milestone: Q7 eligibility check surfaced a real tape-format regression, not a new day of
data.** `tape/crypto_hourly/` and `tape/sports_pairs/` each had a `dt=2026-07-10` **directory**
(raw per-market Kalshi API blobs, 23 hourly passes from 2026-07-10T00:26Z–19:24Z) instead of
the canonical `dt=2026-07-10.jsonl` **file** every other day uses — caused by the post-reset
lineage's rebuilt collectors writing a different storage format, which PR #35 reconciled the
*code* for but not the *already-committed tape*. Same window: `tape/orderbook_depth/`,
`tape/polymarket_pairs/`, `tape/polymarket_macro_pairs/` have zero 07-10 entries at all (the
post-reset `hourly_pass.py` only ran 2 of the pre-reset lineage's 5 sub-passes). Confirmed
self-corrected: the first hourly pass after PR #35's merge (`tape/hourly-20260710T1955Z`,
commit `cf33e5f`, 20:01:49Z) writes the correct format across all 5 families. Q7 is still
BLOCKED — 6 valid canonical days (03–08), not the apparent 7th. Full writeup:
`findings/2026-07-10-tape-format-regression-crypto-sports.md`. New lesson: `kb/lessons/
00-lessons.md` L25 (UNENFORCED — a day-count check should verify file shape, not just path
existence). Left the ~19h of raw blobs unprocessed — reconstructing canonical records from
them needs a previous-settlement/spot pairing this run couldn't verify was captured alongside,
so reprocessing is flagged as an open decision for Ryan / a future `collector-engineer`
milestone, not attempted here.

**Also noted, not acted on:** PR #4 (Q1's odds-api leg, `worktree-q1-odds-leg`, draft, claims
Q1) has been open 7 days awaiting `ODDS_API_KEY` — still absent from the environment. No lesson
or registry candidate had a live `UNENFORCED`/`idea` row actionable this run beyond L25 above
(Q13 needs ≥10 sports_pairs days, has 9; Q14/Q15 remain externally BLOCKED, unchecked live this
run since the finding above was the day's milestone).

Gates: 401 tests green, `python scripts/invariants.py --full` green (only the pre-existing
non-gating stranded-tape advisory).

---

## 2026-07-10 — RECONCILIATION: main-branch reset discovered and repaired (local session with Ryan)

On 2026-07-08T10:56Z a push moved `origin/main` back to `6cde523` (the 2026-07-02 Q0
checkpoint), orphaning 197 commits: all of 2026-07-03→07-08 (PRs #4–#33 — the Q1–Q18
build-out, S7/S9 DEAD verdicts, S16/S18 BLOCKED verdicts, lessons ledger, phone-note
protocol). The cloud loops then unknowingly rebuilt Q1/Q2/Q3 (2026-07-09/10) and began
re-probing S7 — a strategy already declared DEAD by block-bootstrap on 2026-07-04.
Recovered the pre-reset tip (`f23a491`) via GitHub's event log and merged the post-reset
work into it. Code conflicts resolved in favor of the pre-reset lineage (5 more days of
hardening; `hourly_pass` orchestrates collectors that exist only there); post-reset tape,
`core/odds.py`+schemas, and the S7a re-probe artifacts kept. Entries below from
2026-07-09/10 describe the post-reset lineage's (duplicate) work — kept for honesty.

## 2026-07-10 15:16 UTC — Q4/S7b: built the CLV trade set; raw signal already negative, pre-bootstrap

Topmost eligible queue item: **Q4** (S7 historical CLV backtest), `IN-PROGRESS` after S7a. This
run did **S7b only** — turn S7a's 97-game World Cup tape into a candidate trade set (decision-
time real ask vs de-vigged sharp fair, fee-aware P&L per trade). No bootstrap, no verdict —
that's S7c, next stage.

Built `scripts/sports_clv_s7.py` (16 new unit tests, all offline/no-network, 137 total green).
Key design calls, each documented in the script's own header:

- **Decision time.** football-data's closing odds are priced at kickoff, which Kalshi's
  `open_time`/`close_time` don't directly expose. Defined `decision_ts = close_time - 4h` as a
  conservative pre-kickoff proxy (spot-checked against a captured game: `close_time` lands
  within minutes of the final whistle, regulation+stoppage is reliably under 2h) — stated as an
  approximation, not a precise kickoff read, since no free kickoff-timestamp feed exists.
- **Price.** Last candle at-or-before `decision_ts`, causal/no-look-ahead (same discipline as
  S1's T-24h rule); a missing leg drops the whole 3-outcome bracket rather than partial-
  normalizing.
- **Trade rule.** Single-leg BUY YES when de-vigged fair prob > Kalshi's bracket-normalized ask
  (Hard Rule #3 — `core.pricing.normalized_ask`, never a raw ask read as probability); the fill
  price and P&L use the raw ask. Fee model reused verbatim from `scripts/fee_breakeven.py`.

**Live pass:** 96/97 games usable (1 dropped: odds unmatched, same freshness gap S7a flagged).
**167 candidate trades, mean net P&L −3.51¢/trade** (real_ask, after 0.07-rate taker fee) —
already negative before any bootstrap. A quick min-edge sweep (0.00 → 0.02 → 0.05) makes it
**monotonically worse** (−3.51¢ → −9.30¢ → −27.00¢, n=167/23/1 trades): if the nominal
fair-vs-ask gap were real signal, tightening the bar should concentrate on better trades, not
degrade them — the same "sweep makes it worse" red flag that helped kill S5. Candidate
explanations, none confirmed: football-data's multi-book average is a noisier sharp-consensus
proxy than a single sharp book (S7a already flagged it isn't Pinnacle-specific); the 4h-early
snapshot mixes in market drift the true closing line doesn't share; or plain small-sample noise
(one tournament, 96 games, likely round/team-correlated). Writeup →
`../findings/2026-07-10-sports-clv-s7b.md`; tape → `tape/sports_clv_s7/`.

Gates: **137 tests green** (121 existing + 16 new), `invariants --full` green.

**Next:** Q4/S7c — moving-block bootstrap by game (reuse the S1/S5 `block_bootstrap` pattern) →
95% CI → verdict. The point estimate gives no reason for optimism, but the queue's binding bar
is the bootstrapped CI, not this number — S7c runs it and records whatever it finds, including
DEAD, honestly.

---

## 2026-07-10 10:35 UTC — Q4/S7a: sourced the World Cup CLV backtest dataset; NFL/NBA history mostly unavailable

Topmost eligible queue item: **Q4** (S7 historical CLV backtest), `TODO` since Q0b's egress
unblock. Q4 runs in three stages (S7a source → S7b probe → S7c bootstrap CI); this run did
**S7a only** — sourcing + provenance, no backtest math yet.

Built `scripts/sports_history_s7a.py` (16 new unit tests, all offline/no-network, 121 total
green). Two legs per game:

- **Kalshi (`real_ask`)** — every settled `KXWCGAME` event via `GET /events` with nested
  markets (settlement `result`/`settlement_value_dollars` arrive inline), plus the full hourly
  candlestick series per outcome market (Kalshi's own published `yes_ask` OHLC). Markets are
  listed as early as ~140 days before their game, so the candlestick fetch is capped to the
  last 7 days before close (`CANDLE_LOOKBACK_HOURS`, logged per-outcome as
  `candle_window_truncated`) — the pre-game noise a decision-time backtest will never use is
  dropped explicitly, not silently; keeps the tape at 20 MB instead of ~106 MB uncapped.
- **Odds (`synthetic`)** — football-data.co.uk's free public `WorldCup2026.xlsx`
  (`H-Avg`/`D-Avg`/`A-Avg`, a multi-book closing-odds average — not Pinnacle-specifically, an
  honestly-weaker sharp-consensus proxy), de-vigged via `core/odds.py`'s existing
  decimal-odds → implied-prob → multiplicative-de-vig math. Team names joined order-agnostic
  with an explicit alias table for every observed naming mismatch (`IR Iran`/`Iran`, `Korea
  Republic`/`South Korea`, `Turkiye`/`Turkey`, etc.).

**Live pass:** 97 completed World Cup 2026 games (2026-06-11..07-09), 291 outcome markets, 0
candlestick fetch failures, 96/97 odds-matched (the one miss is the most recent game — the
free odds file lags live results by a few days, an honest freshness gap). Tape →
`tape/sports_history_s7/worldcup2026.jsonl` (20 MB) + the exact xlsx bytes fetched, both
sha256-provenanced per record.

**Honest finding on NFL/NBA:** `probe_last_season_availability()` confirmed Kalshi's public
`/markets` listing purges settled markets after roughly one season, not indefinitely. NFL 2025
season (finished Feb 2026) returns **zero** rows under `status=settled`/`closed` — fully gone.
NBA returns 72 outcome markets / 36 games, but only the playoff tail (2026-05-05..06-14,
conf finals through the Finals) — the regular season is gone the same way. No free historical
NBA odds source was sourced this run (out of scope for this stage) — flagged as a follow-up,
not a blocker. **S7b/S7c run on the World Cup dataset next**, the immediately-usable 97-game
set this stage produced. Writeup → `../findings/2026-07-10-sports-history-s7a.md`.

Gates: **121 tests green** (105 existing + 16 new), `invariants --full` green. Added
`openpyxl>=3.1` to the `analysis` extra (reads the free .xlsx; base substrate + invariants
still run without it).

**Next:** Q4/S7b — probe Kalshi ask vs de-vigged fair at a defined decision time on the 97-game
World Cup dataset, fee model consistent with `scripts/fee_breakeven.py`.

---

## 2026-07-10 05:11 UTC — Q3 hourly collector entry point built + first live pass

Topmost eligible queue item: **Q3** was `BLOCKED(needs Q1 + Q2 built)`, and both landed this
session's prior two runs — dependency resolved, flipped to `TODO`, and it's topmost, so this
run built it: `collection/hourly_pass.py`, the single command the hourly Haiku collector
routine runs.

One pass = one `collection.sports_pairs.run()` + one `collection.crypto_hourly.run()`; during
the 09 UTC hour it also runs `scripts/anomaly_sweep.py` as a subprocess if that file exists
(Q6 isn't built yet, so today every hour is a no-op there — checked fresh every run, so Q6
needs zero additional wiring once it lands). Discipline carried over from both collectors: a
hard exception in either sub-pass degrades to an honest `{"ok": False, "error": ...}` entry
rather than crashing the whole hourly pass or silently dropping the other collector's result;
`completeness_ok` is `False` if either sub-pass raised, either sub-pass logged a
series-enumeration error, or (09 UTC only) the anomaly sweep exists and failed — never faked
`True`. Prints the exact digest line Q3 specified: `<n> markets, <m> lines, completeness
<ok/FAIL>`.

10 new unit tests (`tests/test_hourly_pass.py`), sub-passes stubbed via injected callables
(no network): count aggregation, independent-failure isolation (a sports exception doesn't
zero out crypto's real counts and vice versa), series-errors-without-an-exception still
failing completeness, the 09-UTC-only anomaly-sweep gate (both the call-happens/doesn't-happen
cases and a failing sweep failing completeness), the default runner treating "script doesn't
exist yet" as `True` (not a failure), the digest line's exact format, and `main()`'s exit code
tracking `completeness_ok`.

**Live pass** (real network, no injected fixtures): **1311 markets, 455 lines, completeness
ok** — sports leg 453 events / 1048 outcome markets (odds leg still `blocked_no_key`, unchanged
from Q1), crypto leg 2/2 symbols captured with `spot={ok:2}` and `settle={ok:2}`. Tape appended
to the existing `tape/sports_pairs/` and `tape/crypto_hourly/` stores (same manifests those
collectors already write — `hourly_pass` adds no new tape shape, just orchestration). Gates:
**105 tests green** (95 existing + 10 new), `invariants --full` green.

**Next:** Q4 (S7 historical CLV backtest) and Q5 (S8 first cut) remain the two `TODO`-eligible
research milestones; Q6 (anomaly sweep) is now load-bearing for Q3's completeness signal
whenever it lands, not just a standalone probe. Collector-side plumbing (Q1/Q2/Q3) is done;
the queue's center of gravity moves to actually testing S7/S8 for edge.

---

## 2026-07-10 00:22 UTC — Q2 crypto-hourly settlement collector built + first live pass

Topmost eligible queue item after Q1: **Q2**, the crypto-hourly settlement-basis collector
(serves S8/S10). Built:

- `core/crypto_schema.py` — `CryptoHourlyManifest`, the Q2 sibling of `core/sports_schema.py`'s
  `GamePairManifest`: one line pairs THREE legs for one symbol's current hourly bracket —
  the Kalshi ladder (`real_ask`), a live public spot reference (`synthetic`), and the previous
  hour's Kalshi-reported settlement value (`broker_truth`) — so S8's ρ-guard (spot-vs-settle
  correlation) is computable from tape alone, with no second pass ever needed.
- `collection/crypto_hourly.py` — per symbol (BTC via `KXBTC`, ETH via `KXETH`): discovers the
  CURRENT hourly range-ladder by picking the open event whose `(close_time - open_time)` is
  closest to exactly 3600s (Kalshi keeps a much-longer ~7-day "range" event alive under the
  SAME series_ticker simultaneously — duration, not the ticker string, is what actually
  distinguishes them; verified live on both KXBTC and KXETH); snapshots every outcome market's
  real yes_ask BBO; fetches live spot (Coinbase primary, Kraken fallback on failure); locates
  the settled event whose `close_time` equals the current event's `open_time` and reads off
  Kalshi's own `expiration_value`. Any leg failure degrades to an honest status code
  (`spot_status`/`settle_status`) rather than poisoning the Kalshi leg, which is captured
  unconditionally — same discipline as `sports_pairs.py`'s odds leg.
- Added `Kalshi.markets(series_ticker, status, limit)` to `validation/v3_market.py` (generalizes
  the existing `open_markets`, which now delegates to it) so the settlement leg can query
  `status="settled"` through the same throttled/paginated client, no new HTTP code path.
- 14 new unit tests (`tests/test_crypto_hourly.py`): duration-based hourly-vs-standing-range
  event selection (including the "nothing currently straddles now" fallback), degenerate/
  single-outcome/series-error handling, spot-fetch-failure and settle-not-found/fetch-error
  degradation (each independently, confirming the Kalshi leg is never poisoned), the
  provenance/forged-hash check mirroring `sports_pairs`'s, and two adversarial schema checks
  for the new "`ok` status implies the trusted tag" consistency rules.

**Live pass** (no injected fixtures): **BTC 188 outcomes / ETH 75 outcomes** captured in one
pass, `spot_status={ok:2}`, `settle_status={ok:2}` — both legs resolved live on the first try
(Coinbase spot, Kalshi `expiration_value` for the hour that had just closed). Tape →
`tape/crypto_hourly/`.

**Honest finding, not interpreted here (Q5's job):** the naive `bracket_sum` summed across the
FULL discovered ladder is **not** comparable to weather's ~10¢ overround — live BTC bracket_sum
was **3.99** (188 outcomes, overround +2.99), ETH **2.22** (75 outcomes, overround +1.22).
Inspecting the outcomes: most of the 188/75-market ladder is far out-of-the-money brackets
sitting at the exchange's $0.01 floor tick (illiquid, effectively unfillable at size), and their
one-cent asks summed across dozens of dead brackets dominate the total — a thin-tail-liquidity
artifact, not a real structural cost comparable to the weather bracket's near-the-money
overround. Nothing is discarded (the full ladder is captured honestly), but Q5's S8 first cut
will need to restrict to brackets near the money (e.g. within a few strikes of live spot) to get
a bracket_sum that means the same thing weather's did. Gates: **85 tests green** (71 existing +
14 new), `invariants --full` green.

**Next:** Q4 (S7 historical CLV backtest) and Q5 (S8 first cut from free candlesticks — now
armed with 2 days-in-progress of paired crypto tape once cron accumulates it) are both
`TODO`-eligible; Q5 should apply the near-the-money bracket filter found here before trusting
any overround number. S8 moved `idea → data-collecting` in `kb/strategies/00-index.md`.

---

## 2026-07-09 20:18 UTC — Egress unblocked (Q0b); Q1 sports paired-odds collector built + first live pass

Q0b's self-healing re-check (protocol: cheap re-test while any item sits `BLOCKED(egress...)`)
found all four Q0 hosts now reachable — `curl --max-time 15` got Kalshi REST 200, Coinbase 200,
Kraken 200, and the-odds-api 401 (reachable, just no key). Confirmed end-to-end with
`python -m collection.capture_orderbooks --limit 3` (3 markets, 159 levels, real tape written).
The org egress allowlist was evidently widened sometime between 2026-07-02 and today — not
observable from inside the sandbox, just confirmed fixed. Flipped Q1–Q6 back to `TODO` in
`LOOP-QUEUE.md`; refreshed `tape/cloud-env-check.md`.

With egress open, moved to the new topmost eligible item: **Q1**, the sports paired-odds
collector — time-sensitive, since the 2026 World Cup final round runs through Jul 19. Built:

- `core/sports_schema.py` — `GamePairManifest`, the Q1 sibling of `core/manifest_schema.py`'s
  weather `CaptureManifest`: same bitemporal/content-hash/self-signed discipline, keyed by
  `event_ticker` instead of `(city, contract-day)` since a sports event isn't a city ladder.
- `core/odds.py` — American-odds → de-vigged fair probability. Reuses
  `core.pricing.bracket_sum`/`normalized_ask` for the overround-removal division (same "divide
  by the group sum" operation as Kalshi's own Hard Rule #3 math, just applied to sportsbook
  implied probabilities), so that arithmetic still lives in one place.
- `collection/sports_pairs.py` — discovers every Sports-category series whose ticker ends in
  `GAME` (empirically the per-event moneyline/winner suffix — `KXWCGAME`, `KXNBAGAME`,
  `KXMLBGAME`, ... 186 series found live), World-Cup/soccer sorted first; groups each series'
  open markets by the API's own `event_ticker` (cross-checked against a ticker-parse, mismatches
  recorded not hidden); captures real yes/no BBO for every outcome in a >=2-way bracket
  (`price_source_tag=real_ask`); attempts a matched-Pinnacle de-vig leg if `ODDS_API_KEY` is set
  (`synthetic`), else honestly records `odds_leg_status="blocked_no_key"` per Q1's documented
  fallback — the Kalshi leg is captured regardless.
- 18 new unit tests (`tests/test_odds_devig.py`, `tests/test_sports_pairs.py`): American-odds
  math, multiplicative de-vig on 2-way and 3-way brackets, ticker parse/reconcile, World-Cup
  priority ordering, degenerate/series-error handling, odds-leg name matching (caught a real bug:
  Kalshi labels a soccer draw "Tie", the-odds-api calls it "Draw" — added a synonym normalizer),
  and the provenance/forged-hash check mirroring `capture_orderbooks`'s.

**Live pass** (no `ODDS_API_KEY` in this environment): **469 events / 1079 outcome markets**
captured at `real_ask` in ~47s. 4 `KXWCGAME` (World Cup) events captured — `bracket_sum` 1.01–1.02
(1–2¢ overround), noticeably tighter than the ~10¢ weather-bracket overround that killed
pt1/S1/S5. Across all 469 events, mean `bracket_sum` 1.34 (min 0.98, max 2.73) — wide dispersion
expected from thin/off-season leagues with stale asks; not interpreted here, that's Q4's job.
Tape → `tape/sports_pairs/`. `S7` (Kalshi moneyline vs Pinnacle CLV) moved `idea → data-collecting`
in `kb/strategies/00-index.md`. Gates: 71 tests green (53 existing + 18 new), `invariants --full`
green (two docstring false-positives on the `yes_ask`/`no_ask` regex — literal `yes_ask/no_ask`
prose tripped Hard Rule #3's arithmetic detector; reworded, not a real violation).

**Next:** Q2 (crypto-hourly collector) is now the topmost `TODO` item. Separately: S7's actual CLV
backtest (Q4) is still gated on `ODDS_API_KEY` — the odds leg is built and unit-tested but has
never made a live request; re-run Q1 once a key exists to confirm the live matching/de-vig path.

## 2026-07-08 05:30 ET — research loop: comprehensive stranded-tape sweep (6,272 lines recovered), queue still idle

Claim-check: `git fetch origin main` force-updated the local ref to `ce310a2` (5 VPS hourly
passes landed since the last research run). Open PRs unchanged — #4 still claims Q1 (odds-api
leg, unrelated, awaiting `ODDS_API_KEY`; now ~4d18h old, still just under PR #18's proposed
5-day escalation mark, but close enough to flag to Ryan directly this run) and #18
(weekly-retro protocol amendments, left for Ryan, never self-merged).

Queue re-check against the fresh tip: Q2–Q6/Q8–Q12/Q16 all DONE; Q1 claimed. Tape day-counts
recounted directly off disk: Q7 needs ≥7 distinct days of `tape/crypto_hourly/` — only 6
(`dt=2026-07-03`…`07-08`), still BLOCKED, eligible ~07-09/10; Q13 needs ≥10 distinct days of
`tape/sports_pairs/` — only 7 (`dt=2026-07-02`…`07-08`), still BLOCKED, eligible ~07-12/13.
Q14/Q15 re-probed live: `KXHOUSE`/`KXSENATE` still return **zero** markets in any status on
Kalshi's live API — Q15 stays BLOCKED; `ODDS_API_KEY` still absent from env. Lessons ledger
re-scanned: zero live `UNENFORCED` rows (L22 stays resolved by L24). Strategy registry
re-scanned: every `idea`-stage candidate is externally blocked by the same walls as prior
runs. **No numbered queue item, lesson, or registry candidate was actionable this run.**

Step 0b sweep — went wider than recent runs' "branches postdating the last cutoff" heuristic:
fetched all **69** `tape/hourly-*`/`-corrected-`/`-followup-`/`-amended-` branches and ran a
real per-file line-set diff against `origin/main` for every one of them (not just the newest
few), since prior runs' cutoff heuristic can't see whether an "already reconciled" branch
picked up new commits later. Result: the 2026-07-03…07-06 branches were indeed already fully
reconciled (0 missing lines — confirms prior sweeps' bookkeeping was sound), but 07-07 and
07-08 carried a large unreconciled backlog: **6,272 lines** across `crypto_hourly` (+16),
`orderbook_depth` (+4,470), `polymarket_macro_pairs` (+120), `polymarket_pairs` (+140),
`sports_pairs` (+1,498), `anomalies` (+1), `econ_prints` (+5), `polymarket_cpi_pairs` (+22).
Every appended line JSON-validated (0 malformed), union-deduped by exact line match against
main's current content, appended into this run's commit — the largest single-run recovery
since collection began. `git push origin --delete` not reattempted (documented permission
boundary, failed every time since 2026-07-03; PR #18 already proposes dropping the retry).

Gates: pytest green (unchanged test count — tape-only commit, no code touched), `invariants
--full` green. No strategy status changed; no code changed. Seventh consecutive
maintenance-only run — queue/lessons/registry idle pending the same external clocks (tape
day-counts, 1-2 days out for Q7) and external walls (odds-api key, Congress-market listing) as
prior runs; not a stall. The size of this recovery (6,272 vs. the ~1,700-2,800/run of the last
few sweeps) suggests push-to-main failures are becoming more frequent, not less — worth
Ryan's attention if the pattern continues.

---

## 2026-07-08 01:08 ET — research loop: stranded-tape sweep (841+ lines recovered), queue still idle

Claim-check: `git fetch origin main` force-updated the local ref to `12f794c` (VPS + cloud
hourly passes landed since the last run). Open PRs unchanged — #4 still claims Q1 (odds-api
leg, unrelated, awaiting `ODDS_API_KEY`; now ~4d14h old, still short of PR #18's proposed
5-day escalation mark — worth a direct nudge if it's still open next run) and #18 (weekly-retro
protocol amendments, left for Ryan, never self-merged).

Queue re-check against the fresh tip: Q2–Q6/Q8–Q12/Q16 all DONE; Q1 claimed. Tape day-counts
recounted directly off disk: Q7 needs ≥7 distinct days of `tape/crypto_hourly/` — only 6
(`dt=2026-07-03`…`07-08`), still BLOCKED, eligible ~07-09/10; Q13 needs ≥10 distinct days of
`tape/sports_pairs/` — only 7 (`dt=2026-07-02`…`07-08`), still BLOCKED, eligible ~07-12/13.
Q14/Q15 re-probed live (not assumed): CME's FedWatch page still returns HTTP 403 (Akamai-class
bot wall, same as every prior check) — Q14 stays BLOCKED; `KXHOUSE`/`KXSENATE`/`HOUSE`/`SENATE`
still list **zero** markets in open/unopened/closed status on Kalshi's live API — Q15 stays
BLOCKED. `ODDS_API_KEY` still absent from env. Lessons ledger re-scanned: zero live
`UNENFORCED` rows. Strategy registry re-scanned: every `idea`-stage candidate (S10=Q7, S11,
S14=Q13, S16, S18) is externally blocked by one of the walls above — nothing new to draw from
either standing queue. **No numbered queue item, lesson, or registry candidate was actionable
this run.**

Step 0b sweep (against the freshly-fetched tip): of 64 `tape/hourly-*`/`-corrected-`/
`-followup-`/`-amended-` branches, 4 postdating the last run's fully-clean sweep cutoff
(`20260707T2356Z`, `20260708T0401Z`, `hourly-corrected-20260707T2059Z`,
`hourly-followup-20260707T2055Z`, all >30min old) carried lines `main` was missing — did a
real line-set diff per file (not `git diff --stat`, which is unreliable for out-of-order
JSONL appends) across all 5 tape families they touch. Union-deduped total: **2,797 lines**
(10 crypto_hourly, 1,791 orderbook_depth, 75 polymarket_macro_pairs, 92 polymarket_pairs, 829
sports_pairs), every line JSON-validated before appending, 0 exact duplicates, appended into
this run's commit. `hourly-amended-20260704T1455Z` (also re-checked) was already fully
reconciled (0 missing). `git push origin --delete` not reattempted (documented permission
boundary, failed every time since 2026-07-03; PR #18 already proposes dropping the retry).

Gates: 362 tests green (unchanged — tape-only commit, no code touched), `invariants --full`
green. No strategy status changed; no code changed. Sixth consecutive maintenance-only run —
queue/lessons/registry idle pending the same external clocks (tape day-counts, 1-2 days out
for Q7) and external walls (odds-api key, Congress-market listing, CME bot-wall) as prior
runs; not a stall, just recovering tape the VPS/cloud collectors' intermittent push-to-main
failures stranded.

---

## 2026-07-07 20:15 ET — research loop: fully idle, tape sweep clean for the first time

Claim-check: `git fetch origin main` force-updated the local ref to `b938307` (a VPS hourly
pass landed since the last research run). Open PRs unchanged — #4 still claims Q1 (odds-api
leg, unrelated, awaiting `ODDS_API_KEY`; now ~4d9h old, still short of PR #18's proposed
5-day escalation mark) and #18 (weekly-retro protocol amendments, left for Ryan, never
self-merged).

Queue re-check against the fresh tip: Q2–Q6/Q8–Q12/Q16 all DONE; Q1 claimed. Tape day-counts
recounted directly off disk: Q7 needs ≥7 distinct days of `tape/crypto_hourly/` — still only 5
(`dt=2026-07-03`…`07-07`), BLOCKED, eligible ~07-09/10; Q13 needs ≥10 distinct days of
`tape/sports_pairs/` — still only 6 (`dt=2026-07-02`…`07-07`), BLOCKED, eligible ~07-12/13.
Q14/Q15 re-probed live this run (not just assumed): `ODDS_API_KEY` still absent from env;
Kalshi's `KXHOUSE`/`KXSENATE` series still list **zero** markets in any status — both stay
data-adequacy BLOCKED, same as every prior check. No numbered queue item was eligible.
Lessons ledger re-scanned: zero live `UNENFORCED` rows (all resolved by L18–L20/L24).
Strategy registry re-scanned: every `idea`-stage candidate (S10=Q7, S11, S14=Q13, S16, S18)
is externally blocked by one of the walls above — nothing new to draw from either standing
queue.

Step 0b sweep (against the freshly-fetched tip, per L14): 9 `tape/hourly-*`/`-corrected-`/
`-followup-` branches postdating the last run's sweep cutoff (`20260707T1958Z` through
`2256Z`, ages 64min–244min, all past the 30-min freshness rule) were diffed line-by-line
against `main` across all 5 tape families they touch (`crypto_hourly`, `orderbook_depth`,
`polymarket_macro_pairs`, `polymarket_pairs`, `sports_pairs`) — **zero lines missing from
main in every branch and every family.** This is new: every previous sweep this week found
at least some stranded content; this time the VPS collector's direct pushes to `main` (it
has been landing hourly `tape:` commits straight onto `main` all day, e.g. the `b938307` tip
itself) had already fully reconciled everything before this run started. The one branch newer
than 30 minutes (`20260707T2356Z`, ~12min old) was skipped per the freshness rule, left for
the next run. `git push origin --delete` not reattempted (documented permission boundary,
failed every time since 2026-07-03; PR #18 already proposes dropping the retry).

Gates re-verified from a clean env this run (`pip install -e ".[dev,analysis]"` then
`python3 -m pytest -q` and `python scripts/invariants.py --full`): 362 tests green (unchanged
from the last run — no code touched), invariants clean (the non-gating stranded-tape warning
still fires as designed per L20, listing local refs the live sweep above already proved
harmless).

No strategy status changed; no code changed; no tape lines appended (nothing was stranded).
Fifth consecutive maintenance-only run, and the first one with truly nothing to commit —
queue, lessons, registry, and tape are all simultaneously reconciled and idle pending the same
external clocks (tape day-counts, 2-3 days out) and external walls (odds-api key,
Congress-market listing, CME bot-wall) as the last several runs. Nothing here indicates a
stall. PR #4 is now ~4d9h old; worth a direct nudge to Ryan if it crosses 5 days before the
next run picks it up.

---

## 2026-07-07 16:09 ET — research loop: stranded-tape sweep only (queue/lessons/registry all still idle)

Claim-check: `git fetch origin main` force-updated the local ref to `a14afb6` (five VPS hourly
passes had landed since the last research run). Open PRs unchanged — #4 still claims Q1
(odds-api leg, unrelated, awaiting `ODDS_API_KEY`; now ~4d5h old, still short of PR #18's
flagged 5-day escalation mark) and #18 (weekly-retro protocol amendments, left for Ryan, never
self-merged).

Queue re-check against the fresh tip: Q2–Q6/Q8–Q12/Q16 all DONE; Q1 claimed. Counted tape days
directly off disk (not the last log line's estimate): Q7 needs ≥7 distinct days of
`tape/crypto_hourly/` — still only 5 (`dt=2026-07-03`…`07-07`), BLOCKED, eligible ~07-09/10;
Q13 needs ≥10 distinct days of `tape/sports_pairs/` — still only 6 (`dt=2026-07-02`…`07-07`),
BLOCKED, eligible ~07-12/13. Q14/Q15 stay data-adequacy BLOCKED (no re-probe run this cycle —
both were already re-checked live twice this week with no change). No numbered queue item was
eligible. Lessons ledger and strategy registry both re-scanned: zero `UNENFORCED` lesson rows,
every `idea`-stage registry candidate already externally blocked (same set as the last two
runs) — nothing new to draw from either standing queue.

Step 0b sweep (against the freshly-fetched tip, per L14): of 54 `tape/hourly-*` branches, 2
(`20260707T1658Z`/`1759Z`, ages 191min/130min) carried lines `main` lacked across 5 tape
files — 4 crypto_hourly + 1,332 orderbook_depth + 30 polymarket_macro_pairs + 48
polymarket_pairs + 330 sports_pairs = **1,744 lines total**, union-deduped across both branches
per file (every line JSON-validated, 0 exact duplicates), appended into this run's commit. The
newest branch (`20260707T1958Z`, ~3min old) skipped per the 30-min freshness rule, left for the
next run. 3 branches (`20260706T1856Z`/`20260707T1359Z`/`20260707T1856Z`) confirmed stale names
pointing at the same pre-project commit with zero tape content (harmless, consistent with prior
runs' finding). `git push origin --delete` not reattempted this run (documented permission
boundary, failed every time it's been tried since 2026-07-03; PR #18 already proposes dropping
the retry). 362 tests unchanged, `invariants --full` green (non-gating stranded-tape warning
still fires as designed, per L20).

No strategy status changed; no code changed. Fourth consecutive maintenance-only run — the
queue, lessons ledger, and idea registry remain simultaneously idle pending external clocks
(tape day-counts, 2-3 days out) and external walls (odds-api key, Congress-market listing,
CME bot-wall). Nothing here indicates a stall; it's the expected shape while waiting on those
clocks. PR #4's age is worth flagging to Ryan directly since it's now approaching the 5-day
mark PR #18 itself proposed as the escalation trigger.

---

## 2026-07-07 11:08 ET — research loop: stranded-tape sweep only (queue/lessons/registry all genuinely idle)

Claim-check: `git fetch origin main` at `97ad331`, local branch already at the real tip. Open
PRs unchanged — #4 still claims Q1 (odds-api leg, unrelated, awaiting `ODDS_API_KEY`; open
since 2026-07-03, now just under 4 days — still short of PR #18's flagged 5-day escalation
mark) and #18 (weekly-retro protocol amendments, left for Ryan, never self-merged).

Queue check: Q2–Q6/Q8–Q12/Q16 all DONE. Q7 needs ≥7 distinct days of `tape/crypto_hourly/`
tape — counted the actual files on disk: 5 days (`dt=2026-07-03`…`dt=2026-07-07`), still
BLOCKED, eligible ~2026-07-09/10. Q13 needs ≥10 distinct days of `tape/sports_pairs/` tape —
counted: 6 days (`dt=2026-07-02`…`dt=2026-07-07`), still BLOCKED, eligible ~2026-07-12/13.
No numbered queue item was eligible.

Lessons ledger check (`kb/lessons/00-lessons.md`): every row is now either an `invariant`,
a `test`, a terminal `protocol`/`ledger-only` state, or (L22) already resolved by L24 last
run. Zero `UNENFORCED` rows remain — the standing lessons queue is drained too.

Registry check (`kb/strategies/00-index.md`): every `idea`-stage candidate is externally
blocked — S4 (unrelated-repo FEx archiver), S10=Q7 and S14=Q13 (tape day-count, above), S11
(needs the same Pinnacle/odds-api anchor Q1 is already blocked on), S16=Q14 and S18=Q15
(data-adequacy BLOCKED, re-checked live this run: `HOUSE`/`SENATE`/`KXHOUSE`/`KXSENATE` still
list 0 markets in any status — 2026 midterm contracts still not listed, `ODDS_API_KEY` still
absent from env). No new milestone was actionable — genuinely nothing to append past what the
last several runs already exhausted.

Step 0b sweep (the one real piece of work this run did): of 50 `tape/hourly-*` branches, 5
fresh ones since the last run's cutoff (`20260707T0456Z`/`055501Z`/`202607070749Z`/`0756Z`/
`0956Z`, all >30min old) carried lines `main` lacked — 10 crypto_hourly + 3,458
orderbook_depth + 75 polymarket_macro_pairs + 120 polymarket_pairs + 889 sports_pairs + 5
econ_prints + 1 anomalies = **4,558 lines total**, union-deduped across all 5 branches (every
line validated as parseable JSON, 0 exact duplicates), appended into this run's commit.
`tape/hourly-20260707T1359Z` confirmed a stale branch name pointing at a pre-project commit
(`6cde523`, zero real tape content, harmless — same pattern as prior runs). `git push origin
--delete` not reattempted this run (documented permission boundary, failed every time it's
been tried since 2026-07-03; PR #18 already proposes dropping the retry). 362 tests green
(unchanged — no source/test code touched), `invariants --full` green.

No strategy status changed; no code changed. This is an honest maintenance-only run — the
loop's own queue, lessons ledger, and idea registry are all simultaneously drained pending
external clocks (tape day-counts) and external walls (odds-api key, Congress-market listing,
CME bot-wall). Nothing here should be read as stalled; it's the expected shape of a run that
lands inside a 2-3 day accumulation gap.

## 2026-07-07 UTC — research loop: stranded-tape sweep + L22 resolution (real_bid taxonomy decision)

Claim-check: `git fetch origin main` at `e20f026`; open PRs unchanged — #4 still claims Q1
(odds-api leg, unrelated, awaiting `ODDS_API_KEY`; open since 2026-07-03, still short of the
5-day mark PR #18's retro proposal flagged for priority escalation) and #18 (weekly-retro
protocol amendments, left for Ryan, never self-merged). Q2–Q6/Q8–Q12/Q16 all DONE; Q7 BLOCKED
(only 5 of the needed ≥7 days of Q2 tape); Q13 BLOCKED (only 5 of the needed ≥10 days of Q3
tape) — no numbered queue item was eligible.

Step 0b sweep: of 44 `tape/hourly-*` branches, 3 (`202607070056Z`/`20260707T015503Z`/
`202607070356Z`, all >30min old) carried lines `main` lacked — 6 crypto_hourly + 700
orderbook_depth + 544 sports_pairs + 45 polymarket_macro_pairs + 80 polymarket_pairs lines,
union-deduped across all three branches (every line validated as parseable JSON, 0 exact
duplicates), appended into this run's commit. The newest branch (`20260707T0456Z`, ~12min old)
skipped per the freshness rule; 3 branches (`20260706T0556Z`/`0955Z`/`1856Z`) confirmed to be
stale names pointing at a pre-project commit with zero tape content (harmless). `git push
origin --delete` still fails from a cloud session on every already-reconciled branch (same
documented permission boundary).

With the queue drained to time-blocked items and Q1 claimed, checked the registry for the next
un-started, non-externally-blocked candidate first (same process as the last 3 runs): S4/S10
(=Q7)/S14(=Q13)/S16(=Q14)/S18(=Q15) all already explicitly blocked; S11 needs the same
Pinnacle/odds-api anchor as Q1's blocked leg, so appending it would only restate Q1's own
blocker. No genuinely new collector/probe milestone was actionable this run — instead drew from
`kb/lessons/00-lessons.md`'s standing UNENFORCED queue (roster note: "converting a lesson into
an invariant/test is always an eligible milestone, no queue item needed"): **L22** asked
whether `real_bid` (orderbook_depth.py's tag for a genuine resting bid, from Q16) should join
`VALID_SOURCE_TAGS` or stay a separate tape-only namespace. Decided to keep it separate — that
enum mirrors CLAUDE.md's own literal four-tag trust-taxonomy contract, and widening a
project-contract enum is outside a single research-loop milestone's authority, the same class
of call as S9's automation decision and the PreToolUse-hook registration (both left for Ryan).
Closed the "harmless today" half of L22 with proof rather than inspection: a new regression
test (`tests/test_invariants.py::test_db_real_bid_tag_is_caught_as_invalid_enum`) confirms the
existing DB-side enum check already rejects `real_bid` the moment one reaches a
`price_source_tag` column — no live gap exists to fix. `core/source_tag.py`'s docstring now
cross-references the decision. Recorded as **L24** (supersedes L22) in the lessons ledger. 362
tests green (361 prior + 1 new), `invariants --full` green.

No strategy status changed (no probe run this cycle — this was a substrate/documentation
milestone plus the standing tape reconciliation).

## 2026-07-07 UTC — research loop: stranded-tape sweep, S6 orderbook-depth collector built (Q16, new)

Claim-check: `git fetch origin main` at `c238b17`; local `main` ref re-pointed via
`git branch -f main origin/main` (session branch was already at the real tip, per L14). Open
PRs unchanged — #4 still claims Q1 (odds-api leg, unrelated, awaiting `ODDS_API_KEY`; open
since 2026-07-03, approaching but not yet past the 5-day mark PR #18's retro proposal flagged
for a priority escalation) and #18 (weekly-retro protocol amendments, left for Ryan, never
self-merged). Q2–Q6/Q8–Q12 all DONE; Q7 BLOCKED (only ~4 days of Q2 tape, needs ≥7); Q13
BLOCKED (only ~4 days of Q3 tape, needs ≥10) — **no numbered queue item was eligible.**

Step 0b sweep: of 42 `tape/hourly-*` branches, 2 fresh ones (`20260706T2059Z`/`2255Z`, both
>30min old) carried lines `main` lacked — 8 crypto_hourly + 60 polymarket_macro_pairs + 124
polymarket_pairs + 710 sports_pairs, union-deduped across both branches (every line validated
as parseable JSON, 0 exact duplicates), appended into this run's commit. `git push origin
--delete` still fails from a cloud session on every already-reconciled branch (same documented
permission boundary).

With the queue drained to time-blocked items and Q1 claimed, checked the registry for the next
un-started, non-externally-blocked candidate: S4 depends on an unrelated repo's FEx tape
archiver, S10=Q7 and S11 both already blocked the same way as Q7/Q1 — **S6** (inventory-aware
market-making) was the only remaining `idea`-stage candidate with no external block, so
appended **Q16** and built it via the `collector-engineer` subagent. Built
`collection/orderbook_depth.py`: full L2 book depth capture (`yes_bids`/`no_bids` price+size
ladders, not just BBO) reusing `collection/normalize.py:normalize_snapshot` verbatim, fed by
the exact tickers `sports_pairs`/`crypto_hourly` already discover each pass — read straight
back from their own freshly-written tape by `capture_id`, no platform re-sweep (L10). Every
book read tagged `real_ask`/`real_bid`; honest per-ticker completeness (a failed fetch is a
DROP, never absorbed). Wired into `hourly_pass.py` as a fifth fault-isolated sub-pass. 13 new
unit tests (361 total), `invariants --full` green.

Live pass against real Kalshi data: fed 6 tickers from the current-hour `KXBTC-26JUL0621`
group into the collector — 6/6 captured, `completeness_ok=True`, sample reading
`KXBTC-26JUL0621-T71799.99` depth=71, `best_no_bid=0.99 → best_yes_ask=0.01` (correct `1−bid`
complement). Caught and fixed a would-be false-drop bug before commit: far-strike wing markets
legitimately have an empty ladder on one side, and the collector must record that as valid
data (`depth=0`, still captured), not a DROP — confirmed against this same live pass.

**Honest limitation, recorded in the module's own docstring:** this loop's recurring collector
cadence is hard-capped at hourly (the same floor S9's lead-lag work hit) — hourly depth
snapshots give S6 a repeated-sample series, not a continuous order-flow tape. Any
arrival-intensity estimate built on this data must be labeled snapshot-sampled, not treated as
a message-level fill-sim input. `kb/strategies/00-index.md` S6 flipped idea → data-collecting.

Three lesson candidates recorded in `kb/lessons/00-lessons.md`: **L21** (read tickers back from
an upstream sub-pass's freshly-written tape by `capture_id` instead of re-discovering or
threading a new return field through every sibling collector), **L22** (`real_bid` has no slot
in the canonical `VALID_SOURCE_TAGS` enum — flagged UNENFORCED for the kb-distiller, harmless
today since JSONL tape isn't invariant-scanned, but would trip the DB-side check the moment a
`real_bid` value lands in a table), **L23** (an empty one-sided ladder is valid data, not a
drop — pinned in a test, confirmed live).

---

## 2026-07-06 (later) UTC — research loop: PR #26 merged, stranded-tape sweep, Q14/Q15 feasibility (S16/S18 both BLOCKED)

Claim-check: `git fetch origin main` at `efb9245`; found open PR #26 (kb-distiller's L5/L7/L17
escalation) green locally (348 tests, `invariants --full` clean) and research/docs-only (fee-rate
constants, a new static invariant, a non-gating stranded-tape advisory, ledger rows) — merged it
(squash, now `098edbe`). PR #4 (Q1 odds leg) and #18 (weekly-retro protocol proposal) both stay
open per their own standing notes. Step 0b sweep: of 39 `tape/hourly-*` branches, 3
(`20260706T0556Z`/`0955Z`/`1856Z`) turned out to be stale branch names pointing at a 2026-07-02
commit with no tape content at all (harmless, not real stranded data); 3 genuinely fresh branches
(`20260706T1455Z`/`165524Z`/`1755Z`, all >30min old) carried 703 lines `main` lacked across 4
tape families (6 crypto_hourly, 45 polymarket_macro_pairs, 96 polymarket_pairs, 556
sports_pairs) — union-deduped, 0 exact duplicates, all valid JSON, appended into this commit.

Queue was drained to time-blocked items only (Q7 ~07-09/10, Q13 ~07-13) plus Q1 (claimed by
PR #4) — followed the registry's own stated priority past S15/S17 to the next two un-started
candidates and appended `Q14`/`Q15`. Both hit real external walls before any collector was
worth writing: **S16** (FedWatch fade) — `cmegroup.com` 403s/resets every request behind
Akamai-class bot protection (root, the tool page, three guessed API paths), while Kalshi and
the Atlanta Fed's GDPNow page (same free-JS-data shape) both worked fine this run, confirming
it's venue-side not sandbox egress. **S18** (Congress-control fade) — Kalshi's
`HOUSE`/`SENATE`/`KXHOUSE`/`KXSENATE` series exist but list zero markets in any status (the
2026 midterm contracts aren't listed yet); separately, 538's free generic-ballot CSV now
redirects to a dead ABC News stub (site retired, not moved) and RealClearPolling 403s the same
way as CME — Wikipedia's 2026 House-elections article is a live fallback source for once Kalshi
actually lists the markets. Both recorded `BLOCKED` per the Stop rules ("a DEAD verdict is a
success") — no source/test code changed, no strategy status flipped from `idea`. Full
evidence: `findings/2026-07-06-s16-s18-feasibility-blocked.md`; `kb/strategies/00-index.md`
S16/S18 notes updated; `LOOP-QUEUE.md` Q14/Q15 appended. 348 tests unchanged, `invariants
--full` green.

---

## 2026-07-06 UTC — kb-distiller: escalated lessons L5/L7/L17 (fee-rate invariant, stranded-tape warning)

Distiller milestone (research-lead directed). Moved three UNENFORCED lessons along the
invariants-over-memory gradient; ledger rows L18–L20 appended (append-only, superseding by
reference).

**L5 → invariant (`no_handrolled_fee_rate`).** The Kalshi fee-schedule rates now live solely
in `core/pricing.py` as module constants `TAKER_FEE_RATE` (0.07) / `MAKER_FEE_RATE` (0.0175)
/ `SP500_NDX_FEE_RATE` (0.035); `fee_per_contract` and `monotonicity_crossing_edge` default
to `TAKER_FEE_RATE` (same value, conservative default). A new static rule in
`scripts/invariants.py` flags, outside `core/pricing.py`, (A) a fee/rate/coeff-named constant
or kwarg bound to a banned literal and (B) a banned literal passed positionally into
`fee_per_contract()`; comment lines are skipped and 0.0035 (longshot's modeling haircut, not a
schedule rate) deliberately does not fire. Refactored every existing hit value-identical:
`collection/sports_history.py`, `scripts/s13_maker_fillsim.py`, `scripts/weather_rehab_s5.py`,
`scripts/fomc_zq_basis_s2.py`, `scripts/fee_breakeven.py` (now imports the three constants; KB
proof still runs with identical output), and `tests/test_s13_maker_fillsim.py:237` (rewritten
to use the imported `TAKER_FEE_RATE` so the maker≠taker assertion intent survives). A few
docstring/print-string prose lines were reworded rather than sentinel-littered. Honest scope:
constants and literal call-args are enforced; a from-scratch reimplementation using an
imported rate is not statically catchable and remains protocol. Post-review tightening: after
the verifier flagged that pattern A's identifier class matched fee/rate/coeff as raw substrings
(benign names like `accurate`/`coffee`/`separate` would have poisoned the gate), the rule now
requires fee/rate/coeff to be a whole underscore-delimited token segment — `SP500_NDX_FEE_RATE`
/`FEE_COEFF` still fire, the benign substrings no longer do (tests pin both directions).

**L7 → protocol (terminal, no invariant).** A numeric width literal is indistinguishable from
any other constant at regex level, and the one live site (`s8_basis_probe.py`'s documented
`BAND_WIDTH_DOLLARS_BY_SYMBOL` schedule map) would force a false-positive or a vacuous
sanction. Recorded as an honest terminal state, plus a residual hazard this review surfaced:
`s8_basis_probe.py`'s `.get(symbol, 100.0)` silent $100 fallback would repeat the ETH-class
bug for any new symbol — S8 is dead and the script historical (NOT edited), but future crypto
probes (Q7/S10) must derive spacing from the ladder or fail loudly.

**L17 → protocol + non-gating invariants warning.** `invariants.py --full` (and default tree
scan only — never `--pre-edit-hook` or `--db`) now prints a stderr advisory listing
locally-known stranded `tape/hourly-*` refs. `_git_tape_refs()` is fully offline-safe (any git
failure → no refs); `stranded_tape_warning()` is pure. It never touches the exit code — 35
stranded refs print on today's tree and the gate still exits 0. LOOP-QUEUE step 0b remains the
binding sweep.

Gate unchanged: warnings never gate. `pytest -q` 340 passed; `invariants.py --full` exit 0
(the stranded-branch warning on stderr is expected). No strategy status changed
(`kb/strategies/00-index.md` untouched — these are lessons, not verdicts). Findings linked:
`findings/2026-07-04-sports-maker-s13-verdict.md` (L5), `findings/2026-07-04-crypto-basis-s8-verdict.md`
(L7), `findings/2026-07-06-tape-audit.md` (L17).

---

## 2026-07-06 (later) UTC — Q12 closed: S17 CPI/inflation leg (derived-transform pairing)

Research loop. `git fetch origin main` at `4b76056`; local `main` ref was found badly
stale (2026-07-02, ~50 commits and 4 days behind the real `origin/main` tip) — fixed with
`git branch -f main origin/main` before trusting any diff, exactly the bug PR #18's
weekly-retro proposal flagged (a stale local `main` inflates the stranded-branch sweep).
Open PRs unchanged: #4 still claims Q1 (unrelated, awaiting `ODDS_API_KEY`), #18 is the
retro's protocol-amendment proposal (never self-merged, left for Ryan). Queue scan against
the real tip: Q1 claimed, Q2–Q6/Q8–Q11 all DONE, Q7/Q13 BLOCKED — **Q12** (FED-DECISION LEG
DONE, real remaining work: the deferred CPI/inflation leg) was topmost eligible.

Step 0b stranded-tape sweep (against the corrected `main`): 5 of 35 `tape/hourly-*`
branches (`202607051954Z`, `20260705T0957Z`, `20260705T1455Z`, `20260706T0855Z`,
`20260706T1255Z`, all >30min old) carried lines `main` was missing across 9 tape files —
union-deduped per file (each branch is an independent snapshot, not a superset of the
others, so the union had to be taken across all of them, not just the newest), 1,158 lines
total (554 + 374 sports_pairs, 120 + 64 polymarket_pairs, 30 polymarket_macro_pairs, plus
crypto_hourly/econ_prints/anomalies remainders), every line validated as parseable JSON
with 0 exact duplicates, appended into this commit.

Built the CPI/inflation leg Q12's own prior cut deferred: `collection/polymarket_pairs.run_cpi()`
pairs Kalshi's `KXCPI`/`KXCPIYOY`/`KXCPICORE` cumulative "exceed threshold T" ladders against
Polymarket's exact 0.1-point bucket partition for the same 3 US print series. Confirmed live
that both venues quote all 3 series in identical 0.1-point steps, then built
`price_cpi_bucket_from_kalshi` — the differencing transform (floor = 1 − ask(T); exact =
ask(T−step) − ask(T); ceiling = ask(T−step) directly) that turns two adjacent Kalshi `real_ask`
fills into one Polymarket-shaped bucket probability, tagged `synthetic` per Hard Rule #3's
spirit (a computed transform, not a fill, even though its inputs are). Never fabricates: a
bucket whose required Kalshi strike(s) are missing returns `None` (recorded via
`n_buckets_priced < n_buckets_total`, which correctly fails completeness) rather than being
guessed at or silently dropped; a negative derived probability (`monotonicity_violation: true`)
is recorded as-is, never clipped. 23 new unit tests (320 total), wired into `hourly_pass.py`'s
existing 09 UTC daily slot (CPI releases monthly, same cadence reasoning as Q10's
`econ_prints` — 4 new wiring tests, 6 existing 09-UTC-hour tests updated with a zero-contribution
stub). `invariants --full` green.

Live pass: 17 open Kalshi CPI events across the 3 series, 3 matched to currently-listed
Polymarket events (current core-MoM/YoY/headline-MoM prints), 0 unmatched/ambiguous
Polymarket events, 22/28 buckets priced. The 6 unpriced buckets need Kalshi strikes further
out-of-the-money than its ladder currently lists (Polymarket's core-CPI-MoM/headline-CPI-MoM
events both extend one bucket past Kalshi's quoted range) — an honest, expected coverage gap,
correctly counted against `completeness_ok` rather than hidden. One bucket (`cpi_core_mom`
2026-07, exact 0.5%) came back with `monotonicity_violation: true` — Kalshi's raw ladder for
that far-forward month has a thin strike (`T0.5` priced ABOVE `T0.4`, which cannot be true in
a coherent market), the exact kind of thin/stale-quote artifact this project's discipline says
to record honestly rather than paper over. `kb/strategies/00-index.md` S17 note updated;
`LOOP-QUEUE.md` Q12 flipped FED-DECISION-LEG-DONE → full DONE. See tape at
`tape/polymarket_cpi_pairs/dt=2026-07-06.jsonl`.

**Next:** S17's own gate (≥5 matched live-book pairs/month) was already cleared by the Fed
leg; both Fed and CPI legs now run automatically at their appropriate cadence, so the only
remaining work is accumulation, then the eventual lead-lag cross-correlation (same shape as
S9, which was closed dead ✗ on data-adequacy grounds this run window — S17 doesn't share
that constraint since it needs no sub-hourly resolution).

## 2026-07-06 15:06 UTC — Agent team stood up + lessons ledger (compounding layer) + full tape audit

Ops run, Ryan-requested (interactive session, not a loop firing). Three things landed:

**1. Agent team (`.claude/agents/`).** A **Fable lead on high reasoning** (`research-lead`,
`model: fable`, `effort: high`) that plans, decomposes, and reviews but never edits files
itself, guiding five **Opus workers**: `collector-engineer` (collection modules + offline
tests, bitemporal/source-tag/honest-completeness discipline), `edge-prober` (one falsifiable
probe milestone per invocation, block-bootstrap by the independent unit, real-ask bar),
`verifier` (adversarial skeptic — re-runs the producing script and attacks provenance,
statistics, fees, and data windows before any number enters kb/ or findings/),
`kb-distiller` (owns the lessons ledger below, escalates UNENFORCED lessons into
invariants/tests), `tape-auditor` (read-only coverage/completeness/stranded-branch
reports). Every charter embeds the Stop rules and cites the precedent scripts, so a worker
starts from house discipline instead of rediscovering it. `LOOP-QUEUE.md` gained a
"Subagent roster" section wiring this into the run protocol.

**2. The compounding layer: `kb/lessons/00-lessons.md`.** The gap between "learned it the
hard way" and "it's a CI assertion" is where knowledge evaporated between stateless runs —
the ledger makes it visible. 17 lessons mined from the run history (L1 synthetic-never-a-
fill through L17 stranded-tape sweep), each with provenance and an **enforcement status**
(`invariant` / `test` / `protocol` / `UNENFORCED` / `ledger-only`); UNENFORCED rows are the
kb-distiller's standing work queue, and converting one into an assert is always an eligible
idle-run milestone. Append-only, supersede-by-reference, same trust rules as the rest of kb.

**3. Tape audit (`findings/2026-07-06-tape-audit.md`).** 29,363 lines / 10 families /
2026-07-02→07-06, all valid JSON, ~2 passes/hour landing (both collectors alive). All 12
incomplete crypto passes are ONE venue-side hole: Kalshi lists no hourly BTC/ETH group
during the 20 UTC hour, daily (new lesson L15). Step-0b sweep executed: 1,158 stranded
lines union-appended from 6 fallback branches. Eligibility from real tape days: Q7 ~Jul
09/10, Q13 ~Jul 12/13 (WC ends Jul 19 — S14's sports window is narrow). Tape is 36MB raw
and crosses the README's ~50MB decision point ~mid-July — Ryan's call, flagged not acted.

Gates: 297 tests green, `invariants --full` green. Explicitly NOT done: registering the
PreToolUse invariants hook in `.claude/settings.json` — attempted, permission-gated in this
harness, and PROVENANCE.md already reserves that wiring for Ryan's explicit approval; it
remains the one unwired piece of Tier-2 enforcement.

## 2026-07-06 UTC — Q8 closed: S9 lead-lag resolution decision (dead ✗, data-adequacy)

Research loop. Claim-check: `git fetch origin main` at `24b155f`, local branch already at
the real tip (hourly `tape:` passes only since the last run); open PRs unchanged — #4 still
claims Q1 (unrelated, awaiting `ODDS_API_KEY`), #18 is the weekly retro's protocol-amendment
proposal (never self-merged, left for Ryan). Queue scan against the real tip: Q1 claimed,
Q2/Q4/Q5/Q6/Q9/Q10/Q11 DONE, Q7/Q13 BLOCKED — **Q8 (IN-PROGRESS)** was topmost eligible.
Step 0b stranded-tape sweep: all currently-listed `tape/hourly-*` branches already fully
reconciled with `main` (0 missing lines across every family) — nothing to append this run.

Q8's own remaining-work note (from the 2026-07-06 05:17Z shock event-study, below) asked for
a resolution decision: either build a sub-hourly capture burst around the World Cup's
remaining matches, or accept the lead-lag question as untestable and mark it dead. Checked
the loop's actual scheduling primitives (`create_trigger`, `send_later`) before deciding:
recurring cron triggers are hard-capped at hourly minimum interval (the tool's own schema
states it) — no recurring sub-hourly poll is possible. One-shot triggers aren't
cadence-limited, but bracketing a match's real end-time with them needs a kickoff timestamp
the accumulated tape doesn't carry for KXWCROUND markets, and wiring up N one-shot captures
per remaining match (semis, final) is a new class of unattended multi-day automation — the
same category as the VPS collector and `ntfy-watch`, both stood up as Ryan-requested ops
changes, not something a research-loop run should decide alone. Building that unilaterally
is outside this milestone's scope.

**Verdict:** split S9 into its two sub-questions. **Lead-lag** (does one venue reprice first
around a shock?) → **dead ✗, data-adequacy** — not falsified by a CI (there's no bootstrap to
run on n=8 ticker-steps), just structurally untestable with hourly-minimum automation and no
kickoff-time signal to burst around. **Cross-venue parity** (do the two venues quote the same
price on average, right now?) → stays alive, already answered well by the 2026-07-04 first
cut (48/48 matched, +0.20¢ mean gap) and continues under S17's Fed-decision generalization,
which needs no sub-hourly resolution. Per the Stop rules, a DEAD verdict recorded honestly is
a success. No new code — a decision on already-collected evidence, not a new probe. 297
tests unchanged (pre-existing baseline), `invariants --full` green. `kb/strategies/00-index.md`
S9 flipped to dead ✗; `LOOP-QUEUE.md` Q8 flipped IN-PROGRESS → DONE. See
`findings/2026-07-06-polymarket-leadlag-s9-resolution.md`.

## 2026-07-06 05:17 UTC — Q8: first real shock event-study (S9 stays data-collecting)

Research loop. Claim-check: `git fetch origin main` at `a6567cf`, local branch already at
the real tip (only hourly `tape:` passes since the last run); open PRs unchanged — #4 still
claims Q1 (draft, unrelated, awaiting `ODDS_API_KEY`), #18 is the weekly retro's protocol-
amendment proposal (never self-merged, left for Ryan). Queue scan: Q1 claimed, Q2/Q4/Q5/Q6/
Q9/Q10/Q11 DONE, Q7/Q13 BLOCKED — Q8 (IN-PROGRESS) was topmost eligible, and this run's own
check of `tape/polymarket_pairs/` found something the last two runs didn't have: real round
transitions. `market_membership_changes()` showed two teams eliminated since the last cut —
Brazil and Mexico, both quarterfinal losses — so Q8's own remaining-work note ("once an
actual round transition lands, re-run and inspect that market's captures around the
transition specifically") was finally actionable instead of a repeat no-op.

Step 0b stranded-tape sweep first: of the `tape/hourly-*` branches, one
(`20260706T0256Z`, >30min old) carried lines `main` was missing — 2 `crypto_hourly` + 15
`polymarket_macro_pairs` + 36 `polymarket_pairs` + 182 `sports_pairs` (checked by exact
line-set diff per file against `origin/main`, union-deduped, every line validated as
parseable JSON) — union-appended into this run's commit. `git push origin --delete` still
fails from a cloud session (same permission boundary documented since 2026-07-03).

**Q8/S9 milestone.** Built `scripts/s9_shock_eventstudy.py`: isolates real transitions from
`market_membership_changes()` (excluding the one documented startup artifact — the diff
between the pre-wiring smoke-test capture and the first capture of continuous hourly
collection) and, for each ticker a transition removed from the open-markets set, reports the
last two captured rows on both venues (the actual repricing step — the capture at which a
ticker vanishes is not itself a price observation). Result across the 2 real events / 8
affected tickers: Kalshi and Polymarket moved together every single time — mean
`|Δkalshi − Δpolymarket|` 2.2¢, max 8¢, no consistent one-venue-leads pattern, both venues
already reflecting the outcome by the very next capture (30–60min later). Mexico's data
additionally showed the reprice trailing off over 2+ hourly captures rather than one clean
jump, still with both venues moving in lockstep at each step.

**The actual finding is methodological, not a null result on the thesis:** a match resolves
within minutes of the final whistle, but the collection cadence here is 30–60 minutes — too
coarse to ever resolve which venue moves first inside that window. S9's lead-lag thesis
cannot be tested at this resolution as built. 10 new unit tests (297 total, offline synthetic
fixtures), `invariants --full` green. `kb/strategies/00-index.md` S9 note updated, stays
`data-collecting`. Full writeup:
`findings/2026-07-06-polymarket-leadlag-s9-shock-eventstudy.md`.

**Next:** a resolution decision on S9 before the WC ends Jul 19 — either add a sub-hourly
capture burst around scheduled game-end times for the remaining matches (semifinals, final)
to actually test lead-lag, or accept this infrastructure only answers a cross-venue parity
question and mark the lead-lag angle a data-adequacy DEAD. Q7 unblocks ~2026-07-10, Q13
~2026-07-13; Q12's CPI/inflation leg and its own lead-lag accumulation are still open.

---

## 2026-07-06 00:22 UTC — Q12: Fed-decision leg built (S17 now data-collecting)

Research loop. Claim-check: `git fetch origin main` at `1337175`, local branch already at
the real tip; open PRs unchanged — #4 still claims Q1 (draft, unrelated, awaiting
`ODDS_API_KEY`), #18 is the weekly retro's protocol-amendment proposal (never self-merged,
left for Ryan). Queue scan: Q1 claimed, Q4/Q5/Q6/Q9/Q10/Q11 DONE, Q7/Q13 BLOCKED
(need ≥7/≥10 days of tape, not yet elapsed), Q8 (IN-PROGRESS) had only ~4h of new
accumulation since its 2026-07-05T20:09Z lead-lag cut (44 vs 37 captures, no round
transition) — rerunning it would have reproduced the same "still just noise" result with
barely more data. **Q12 (S17, TODO with unstarted real work)** was the topmost item where
this run's effort would actually move something forward, matching the precedent the prior
run itself named ("Q12 remains the topmost TODO item with unstarted real work if Q8 gets
skipped again before a shock arrives").

Step 0b stranded-tape sweep first: of 29 `tape/hourly-*` branches, 2
(`20260705T2155Z`/`2255Z`, both >30min old) carried lines `main` was missing — 4
`crypto_hourly` + 76 `polymarket_pairs` + 304 `sports_pairs` (checked by exact line-set diff
per file, union-deduped, every line validated as parseable JSON) — union-appended into this
run's commit. `git push origin --delete` still fails from a cloud session (same permission
boundary documented since 2026-07-03).

**Q12/S17 milestone.** Built `collection/polymarket_pairs.run_fed_decision()`: a second
Kalshi↔Polymarket discovery family (Fed rate-decision meetings) using the same match
discipline the WC-round leg already proved out, so cross-venue collection outlives the
World Cup. Kalshi's `KXFEDDECISION` 5-bucket meeting ladder (cut>25/cut25/no-change/
hike25/hike>25) matched to Polymarket's "Fed Decision in `<Month>`?" events by (meeting
month+year, bucket) — confirmed via each side's own title/question text, not the Kalshi
ticker's bps suffix alone (it uses `"26"` as a stand-in for ">25", confirmed live). One real
design call: completeness is graded against Polymarket's side, not Kalshi's — Kalshi lists
meetings ~18 months out (to January 2028) while Polymarket only creates an event closer to
it, so grading against Kalshi's full calendar would make this leg report FAIL forever, a
structural non-issue rather than a real one; a Polymarket market this pass fails to pair
(`unmatched_polymarket`) does still gate. Wired into `hourly_pass.py` as a fourth cross-venue
sub-pass, own tape family `tape/polymarket_macro_pairs/` (kept separate from the WC-round
tape — different record shape). 22 new unit tests, 287 total green, `invariants --full`
green. Live pass: **15/15 currently-listed Polymarket Fed-decision markets matched**
(Jul/Sep/Oct 2026 — the only meetings Polymarket has created so far), 0 ambiguous, 0 book
errors, `completeness_ok`; gaps ranged −3¢ to +15¢ across the 15 pairs (one snapshot,
descriptive only). CPI/inflation matching explicitly deferred — Kalshi's cumulative
"≥threshold" ladder and Polymarket's exact-bucket partition are different shapes; pairing
them would need a derived/synthetic transform, not a same-question `real_ask` pair, so it
isn't faked here. `kb/strategies/00-index.md` S17 flipped idea → data-collecting; its own
gate (≥5 matched live-book pairs/month) is already cleared by this one pass. Full writeup:
`findings/2026-07-06-fed-decision-macro-pairs-q12-first-cut.md`.

**Next:** accumulate hourly Fed-decision snapshots (already wired), then run a lead-lag
cross-correlation once enough history exists, same shape as `s9_leadlag_probe.py` — the
next FOMC meeting is a natural information shock to watch for. Q7 unblocks ~2026-07-10,
Q13 ~2026-07-13; Q8 (S9) still worth revisiting once a real round transition lands.

---

## 2026-07-05 20:09 UTC — Q8: first S9 lead-lag cross-correlation cut (zero in-window shocks found)

Research loop. Claim-check: `git fetch origin main` force-updated the local ref to `d1ae913`
(hourly `tape:` passes only since the last run); open PRs unchanged — #4 still claims Q1
(draft, unrelated, awaiting `ODDS_API_KEY`), #18 is the weekly retro's protocol-amendment
proposal (never self-merged by a loop run, left for Ryan). Queue scan: Q2–Q6/Q9/Q10/Q11 DONE,
Q7/Q13 BLOCKED — **Q8 (IN-PROGRESS)** was topmost eligible by the letter of the protocol; the
last several runs treated its "let snapshots accumulate" remainder as no-code-yet and skipped
to the next TODO, but by this run's time (~19h of continuous hourly-ish collection since the
2026-07-05T00:11Z wiring, 37 distinct captures) there was finally enough tape to actually
attempt the lead-lag cross-correlation Q8's own spec calls for — so this run did that instead
of skipping again.

Step 0b stranded-tape sweep first: of 27 `tape/hourly-*` branches, 2 (`20260705T155348Z`,
`20260705T1655Z`, both >30min old) carried lines `main` was missing — 4 `crypto_hourly` + 80
`polymarket_pairs` + 360 `sports_pairs` (checked by exact line-set diff per file, union-deduped
across both branches, every line validated as parseable JSON) — union-appended into this run's
commit. `git push origin --delete` still fails from a cloud session (same permission boundary
documented since 2026-07-03).

**Q8/S9 milestone.** Built `scripts/s9_leadlag_probe.py` (read-only over
`tape/polymarket_pairs/`): pools every consecutive-capture (Δkalshi_yes_ask,
Δpolymarket_best_ask) pair across the 40 markets with ≥10 captures into a lag-0/lag±1
cross-correlation — contemporaneous ρ **+0.293** (n=1,440), kalshi-leads-polymarket ρ +0.044,
polymarket-leads-kalshi ρ −0.007 (both n=1,400, both noise-level). More important than the
correlation numbers: `market_membership_changes()` — the honest proxy for "did a round
actually transition inside the window" — found **zero** in-window round-transition events; the
one membership change on record predates continuous hourly collection entirely (a
pre-wiring smoke-test artifact from 2026-07-04T15:15Z, not something that happened while the
collector was running). S9's actual thesis — does one venue visibly lag the other around a
real information shock (a team advancing or being eliminated) — is therefore **still
untested**; every tick observed so far is ordinary book noise on markets whose underlying
question hasn't resolved yet. No CI, no verdict claimed; explicitly reported as a
noise-floor characterization, not a lead-lag finding. 20 new unit tests (offline, synthetic
capture series incl. one hand-built market where polymarket is kalshi shifted by exactly one
step, confirming the pooled stat recovers the correct lag direction). 265 tests green (245
prior + 20 new), `invariants --full` green. `kb/strategies/00-index.md` S9 note updated
(stays `data-collecting`). See
`findings/2026-07-05-polymarket-leadlag-s9-first-cut.md`.

**Next:** keep accumulating hourly snapshots; re-run `s9_leadlag_probe.py` once an actual
round transition lands in the tape and inspect that specific market's captures around the
transition. Q12 (S17, retarget the matcher to recurring macro pairs) remains the topmost TODO
item with unstarted real work if Q8 gets skipped again before a shock arrives; Q7 unblocks
around 2026-07-10, Q13 around 2026-07-13.

---

## 2026-07-05 15:13 UTC — Q10: GDPNow nowcast leg built (S12 econ-print collector now fully DONE)

Research loop. Claim-check: `git fetch origin main` forced-updated the local ref (session
sandbox was stale) to `a5f1291`; open PRs unchanged from prior runs — #4 still claims Q1
(draft, unrelated, awaiting `ODDS_API_KEY`), #18 is the weekly-retro's own protocol-amendment
proposal (never self-merged by a loop run, left for Ryan). Queue scan: Q2–Q6/Q9/Q11 DONE,
Q7/Q13 BLOCKED, Q8's only remaining gap is letting hourly snapshots accumulate (no code) —
**Q10 (KALSHI LEG DONE, nowcast leg BLOCKED)** was the topmost eligible item with real work,
per the same precedent the last two runs used to skip Q8.

Step 0b stranded-tape sweep first: of 24 `tape/hourly-*`/amended branches, 22 were already
fully reconciled with `main` (checked by exact line-set diff per file, not just `git diff
--stat` — a pure stat diff would have wrongly flagged several already-merged branches as
"missing" content that was really just reordered/rewritten upstream); 2 (`20260705T1155Z`,
`20260705T1253Z`) had real gaps `main` lacked — 4 `crypto_hourly` + 80 `polymarket_pairs` + 389
`sports_pairs` lines (union-deduped across both branches, order preserved, every line
validated as parseable JSON before commit) — union-appended into this run's commit. The
newest branch (`20260705T1455Z`, ~13min old) was skipped per the freshness rule. `git push
origin --delete` still fails from a cloud session (same permission boundary documented since
2026-07-03).

**Q10 milestone.** Built the GDPNow leg of `collection/econ_prints.py`'s nowcast field
(`fetch_nowcast_gdp`/`parse_gdpnow_nowcast`), closing the one gap the Kalshi-leg-only version
left open. Confirmed live (2026-07-05) that the Atlanta Fed's GDPNow page embeds its entire
forecast history as three parallel JS arrays (`forecastDates`/`forecastQuarters`/
`gdpForecast`, ~1,900 entries back to 2014) grouped into quarter-blocks ordered
newest-quarter-first, each block internally date-ascending — so "the current nowcast" is
just the last entry whose quarter tag matches the array's first tag. Parser never fabricates:
a missing array, a length mismatch, an empty block, or a null latest value all surface as an
honest `parse_error`, not a stale or guessed number; a real network failure is `fetch_error`.
Tagged `synthetic` (a model estimate, not a Kalshi fill) per CLAUDE.md's trust defaults. Live
end-to-end check: current GDPNow read is **+1.19% annualized for the quarter ending
2026-06-30, as of its 2026-07-01 update** (27 updates so far that quarter) — descriptive only,
not yet joined against Kalshi's `KXGDP` ladder (that join is S12's eventual gate work, not this
milestone's job). The Cleveland Fed CPI-nowcast leg stays `not_built` as before — its page has
no scrapable static data, a genuinely different blocker than GDPNow's (which just needed the
array-slicing logic this run built), so it isn't reattempted.

7 new unit tests (offline, synthetic HTML fixtures — parser edge cases, fetch-error handling,
and the `gdp` vs everything-else routing in `fetch_nowcast`) plus one existing test
(`test_run_two_series_independent`) updated to inject a stub GDP fetcher so it stays network-free.
245 tests green (238 prior + 7 new), `invariants --full` green. `kb/strategies/00-index.md` S12
row unchanged (still `data-collecting` — the nowcast leg unblocks future analysis, it isn't
itself a verdict). Q10 flipped from "KALSHI LEG DONE" to full **DONE**.

**Next:** Q12 (S17, retarget the Kalshi↔Polymarket matcher to recurring macro pairs) is the
topmost remaining TODO with real work; Q7 unblocks around 2026-07-10, Q13 around 2026-07-13.

---

## 2026-07-05 06:08 ET — Q11: cross-event logical-implication scanner built (S15 idea → data-collecting)

Research loop. Claim-check: sandbox branch was already at `origin/main`'s real tip (hourly
`tape:` passes only since the last run); only open PR (#4) still claims Q1 (draft, unrelated,
awaiting `ODDS_API_KEY`). Queue scan: Q2/Q3/Q4/Q5/Q6/Q9/Q10 DONE, Q7/Q13 BLOCKED, Q8's only
remaining gap is letting hourly snapshots accumulate (no code) — **Q11 (S15, TODO)** was the
topmost eligible item with actual work.

Step 0b stranded-tape sweep first: of 21 `tape/hourly-*` branches, 4 (all >30min old) carried
lines `main` was missing — 8 `crypto_hourly`, 160 `polymarket_pairs`, 816 `sports_pairs` —
union-appended into this run's commit (checked: 0 exact-duplicate lines, every appended line
valid JSON). The newest branch (~12min old) was skipped per the freshness rule. `git push
origin --delete` still fails from a cloud session on every branch (same permission boundary
documented since 2026-07-03) — redundant branches persist, harmless.

**Q11 milestone.** Extended `scripts/anomaly_sweep.py` (Q6) with a third real-ask check,
`check_cross_event_implication`, and a new config file, `config/implication_pairs.yaml` — the
"hand-curated implication graph" Q11 called for. Unlike Q6's existing `cross_strike_monotonicity`
check (which proves nesting because both legs share one `event_ticker`), a cross-event pair
can't lean on that structural shortcut — the config's job is to hold, per family, the actual
audit of both markets' settlement rules text that proves A ⇒ B. One family is populated so
far: `kxwcround_progression` — for Kalshi's `KXWCROUND` series ("Will `<team>` qualify for
FIFA World Cup `<round>`?", the same grammar `collection/polymarket_pairs.py` already
discovers+confirms structurally), reaching a later round in a single-elimination bracket is a
strict superset of reaching every earlier round for the *same* team — no settlement-term
mismatch is possible within one entity/series, which is exactly the audit the config's `audit`
field records. Q11's own second example ("wins presidency" ⇒ "wins nomination") has no
matching live Kalshi series yet; left as a documented TODO in the config rather than guessed
at.

The check itself reuses `core.pricing.monotonicity_crossing_edge` completely unchanged — same
fee-floor math Q6's check 2 already uses (buy YES(B) + NO(A), A = harder/narrower round, B =
easier/wider round, hit when the combined cost clears below $1 net of both legs' taker fees).
10 new unit tests cover the pair-generation logic (one entity's full round chain, non-matching
series ignored, missing prices skipped, unknown family kinds skipped) plus the config loader;
2 more wire it into `run()`'s existing tape record (`n_implication_pairs_checked` alongside the
existing `n_bracket_groups_checked`/`n_monotonicity_groups_checked`). No `hourly_pass.py` change
needed — same as Q6, the third check just runs inside the same subprocess call already wired
into the daily 09 UTC slot.

Live-validated directly against Kalshi's real, currently-open `KXWCROUND` markets (bypassing
the platform-wide sweep's pagination, which doesn't reach WC tickers within a bounded
`--limit`): 40 open markets, 38 generated round pairs, **0 fee-clearing hits** — expected,
matching Q6's and Q8's own "real arbs are rare" precedent, and the sampled pair confirms the
check discriminates correctly (Team USA: SEMIFINALS priced 19¢ vs QUARTERFINALS' 52¢ — properly
monotonic, harder round cheaper). `kb/strategies/00-index.md` S15 flipped `idea` →
`data-collecting`; kill condition (per registry, dated from this run) is 0 fee-clearing hits in
60 days of the existing daily sweep. 238 tests green (228 prior + 10 new), `invariants --full`
green.

**Next:** Q12 (S17, retarget the Kalshi↔Polymarket matcher to recurring macro pairs) is next
in queue order; Q7 unblocks around 2026-07-10 (needs ≥7 days of Q2 crypto tape).

---

## 2026-07-05 05:19 UTC — Q10: econ-print (CPI/payrolls/GDP) collector built — Kalshi leg DONE, nowcast leg BLOCKED

Research loop. Claim-check: `git fetch origin main` at `9de63e2` (only hourly `tape:` passes
since the last run); only open PR (#4) still claims Q1 (draft, unrelated, awaiting
`ODDS_API_KEY`). Queue scan: Q2/Q3/Q4/Q5/Q6/Q9 DONE, Q7/Q13 BLOCKED (tape not old enough),
Q8 IN-PROGRESS but its only remaining gap is letting hourly snapshots accumulate (no code to
write) — **Q10 (S12, TODO, time-sensitive)** was the topmost eligible item with actual work.

Step 0b stranded-tape sweep first: of 17 `tape/hourly-*`/`tape/hourly-amended-*` branches, 15
were fully reconciled with `main` already (0 missing lines, verified line-by-line against the
real `origin/main` tip); 2 branches (`20260704T2355Z` 181 lines, `20260705T0055Z` 256 lines —
both >30min old) had lines `main` lacked, union-appended into this run's commit; 1 branch
(`20260705T0455Z`, ~13min old) skipped per the freshness rule. `git push origin --delete`
remains blocked from a cloud session (same documented permission boundary) — redundant
branches persist, harmless.

**Q10 milestone.** Live API discovery confirmed 5 flagship econ-print series
(`/series?category=Economics` + a structural check against `/markets`): `KXCPI` (CPI MoM),
`KXCPIYOY`, `KXCPICORE` (core CPI MoM), `KXPAYROLLS` (nonfarm payrolls), `KXGDP` (real GDP QoQ).
All 5 are NESTED MONOTONIC "will the print exceed threshold T" ladders sharing one
`event_ticker` per release — structurally different from `crypto_hourly`'s KXBTC/KXETH
complete-partition brackets — so `core.pricing.bracket_sum` (the sanctioned Hard-Rule-#3 site
for partitions) is deliberately NOT called here; each strike's `yes_ask` is persisted as its
own `real_ask`, nothing summed/normalized (the nested-threshold arb shape these ladders DO
admit is already covered platform-wide by Q6's `cross_strike_monotonicity`).

Built `collection/econ_prints.py`: (1) **open_events** — every open event_ticker per series,
full per-strike real_ask ladder, honest expected-vs-captured completeness; (2)
**recent_settlement** — the single most-recently-settled event per series, Kalshi's own
`result` + `expiration_value` (the actual published BLS/BEA print, confirmed live — e.g. CPI
MoM settled at "0.5", payrolls at "57,000") tagged `broker_truth`. Kalshi purges settled
markets ~60 days after close (S7a finding) — this leg runs every pass regardless of the open
ladder so no release is lost. 12 new unit tests (offline, FakeClient). Live pass: all 5 series
`pass_complete` (24 open events / 296 strikes captured, settlement resolved for all 5,
including CPI MoM/YoY/core, payrolls, and GDP). Wired into `collection/hourly_pass.py`'s
existing 09-UTC-only slot (alongside `anomaly_sweep`) since releases are infrequent — a daily
cadence is what the spec asked for; 9 hourly_pass tests updated with a zero-contribution
econ_prints stub, 4 new tests added for the wiring itself.

**Nowcast leg (Cleveland Fed CPI / GDPNow) left BLOCKED(nowcast-scrape), same shape as Q1's
odds-api leg.** Checked live: the Cleveland Fed inflation-nowcasting page renders its number
client-side with no static data or discoverable API in the served HTML. Atlanta Fed's GDPNow
page DOES embed its full forecast history as raw JS arrays
(`gdpForecast`/`forecastDates`/`forecastQuarters`) — scrapable in principle — but reliably
slicing the current quarter's window out of that structure is nontrivial and left for a
follow-up pass rather than forced this run. Every record's `nowcast` field is an honest
`{"status": "not_built"}`, never a fabricated placeholder — the S12 gate (≥20 releases +
nowcast comparison) still needs this leg before any edge can be scored, but the URGENT,
purge-at-risk half (the Kalshi ladders + settlements) is now collecting.

228 tests green (212 prior + 16 new: 12 for `econ_prints` + 4 for the `hourly_pass` wiring),
`invariants --full` green. No findings doc (collection
infrastructure, not a strategy verdict yet) — `kb/strategies/00-index.md` S12 updated to
`data-collecting`; `LOOP-QUEUE.md` Q10 status updated.

---

## 2026-07-04 20:14 ET — Q8: polymarket_pairs wired into the hourly collector; stranded-tape sweep

Research loop. Claim-check: `git fetch origin main` at `092196c` (only hourly `tape:` passes
since the last run); open PR #4 still claims Q1 (draft, unrelated, awaiting `ODDS_API_KEY`).
Queue scan: Q2/Q3/Q4/Q5/Q6/Q9 all DONE, Q7/Q13 BLOCKED (tape not old enough yet), Q1 claimed —
**Q8 (IN-PROGRESS)** was the topmost eligible item.

Step 0b stranded-tape sweep first, and caught a bug in the sweep itself: an earlier `git diff`
comparison used this sandbox's *local* `main` ref, which was stale at 2026-07-02 (two days
behind `origin/main`) — every one of the 15 `tape/hourly-*` branches looked like it had
thousands of "missing" lines vs that stale ref, including in files the hourly collector never
touches (`sports_history`, `sports_clv`, `sports_maker_fillsim` — outputs of one-off research
scripts, not append-only collector tape). Re-pointed local `main` at `origin/main` before
trusting any diff. Against the real tip, 12 of 15 branches were already fully reconciled by
the prior run (0 missing lines); 3 branches (`20260704T1955Z`/`2055Z`/`2155Z`) had a combined
**8 crypto_hourly + 536 sports_pairs lines** `main` was missing — union-appended into this
run's tape files (verified: append-only, no reordering, every new line still valid JSON). One
branch (`20260704T2355Z`, ~19min old) skipped per the 30-min freshness rule. `git push origin
--delete` still fails from a cloud session on every branch (same permission boundary as
documented 2026-07-04) — redundant branches remain, harmless.

**Q8 milestone.** Wired `collection/polymarket_pairs.py` into `collection/hourly_pass.py` as a
third sub-pass (alongside `sports_pairs`/`crypto_hourly`), same fault-isolation discipline: its
own exception never takes the other two down, and its own honest `completeness_ok` (computed
inside `polymarket_pairs.run` itself — matched-count, book-fetch, and ambiguity checks) ANDs
into the overall signal exactly like the other two. Each matched (round, team) pair counts as
one Kalshi market contract for `n_markets`/`n_lines` accounting, consistent with the module's
existing convention. 2 new offline unit tests (`test_run_polymarket_incomplete_marks_overall_incomplete`,
`test_run_polymarket_raises_others_still_run`); all 9 existing `hourly_pass` tests updated to
inject a zero-contribution polymarket stub so they keep testing sports/crypto math in
isolation. Live smoke (`python -m collection.hourly_pass --sports-limit 2 --crypto-symbols
BTC`): polymarket sub-pass fired for real, 40/40 Kalshi round markets matched to Polymarket,
completeness ok — proof the wiring works end-to-end, not just against stubs. This closes Q8's
main remaining gap (World Cup ends Jul 19 — every hour without a snapshot was a data point lost
for good); the lead-lag cross-correlation itself still needs the accumulated repeated-snapshot
history to build up over the coming days.

212 tests green (210 prior + 2 new), `invariants --full` green. No new findings doc (this is
collection infrastructure, not a strategy verdict) — `kb/strategies/00-index.md` unchanged;
`LOOP-QUEUE.md` Q8 status updated.

---

## 2026-07-04 20:08 UTC — Q9/S13 maker fill-sim TESTED → DEAD (null result); stranded-tape sweep

Research loop. Claim-check: only open PR (#4) claims Q1 (unrelated, awaiting `ODDS_API_KEY`) —
Q9 (S13) was the topmost eligible TODO. Step 0b stranded-tape sweep first: of 12
`tape/hourly-*` fallback branches, 10 were fully redundant with `main` (verified line-by-line,
0 missing); 1 (73min old) had 187 lines `main` lacked (union-appended into this run's commit);
1 (~13min old) skipped per the freshness rule. Note: `git push origin --delete` failed on
every branch — the same permission boundary blocking `push origin main` also blocks remote
branch deletion from a cloud session, so the redundant branches remain (harmless, but Ryan or
a session with delete rights should prune them eventually).

**S13 built and tested.** `scripts/s13_maker_fillsim.py`: the mirror-image test to S7's
already-proven taker-side result — rest a bid at DraftKings-close-devig fair minus 1¢, does a
real trade ever cross at/below it between the market's `open_time` and the game's actual
kickoff (hourly candlestick `price.low_dollars`, not the ask low)? Live pass over the
accumulated `tape/sports_clv/` + `tape/sports_history/` dataset (n=80 games) plus one new live
(cached) Kalshi candlestick pull per outcome ticker: **94.1% fill rate** (223/237 priced
outcomes), but `edge_after_fee` conditional on fill block-bootstraps to **+0.00009, 95% CI
[−0.00021, +0.00039]** — straddles zero. **Verdict: DEAD**, and a genuinely different flavor
of dead than S7/S8: not falsified on the wrong side, just a wash. The mechanism is structural:
Kalshi's maker fee (0.0175, not the 0.07 taker rate) is itself close to 1¢/contract across
most of this dataset's bid-price range, so it alone eats almost the entire assumed penny of
edge before any real market effect (adverse selection, informational drift) gets a chance to
matter — separately measured via DraftKings' open-vs-close line move, that drift was a
favorable but tiny +0.00168, an order of magnitude too small to rescue the point estimate.

**Two bugs caught and fixed before the verdict was final** (both would have understated the
edge or wasted disk, not overstated an edge — caught by testing/re-checking, not by luck):
(1) a first draft called `core.pricing.fee_per_contract` with its default taker rate (0.07)
instead of the maker rate the situation actually calls for (0.0175) — a 4x fee overcharge that
made the first live run look clearly negative (−0.00614 point, CI [−0.00683,−0.00542]) before
the fix flipped it to the true near-zero result; (2) a first cache design persisted every raw
candlestick per ticker and hit **98MB for 237 tickers** (several World Cup moneyline markets
open 4+ months before kickoff — one ticker's `open_time` was February for a June game) —
trimmed the cache to just the window's minimum trade price and its timestamp (93KB, same
237 tickers), and fixed an O(n²) bug where the cache file was being fully re-read from disk on
every single ticker lookup instead of once per run.

22 new unit tests (`tests/test_s13_maker_fillsim.py`, fully offline — candlestick fetch always
injected), 210 tests green, `invariants --full` green (one false-positive catch along the way:
a docstring's prose "OHLC/yes_ask/yes_bid" tripped the Hard-Rule-#3 arithmetic scanner via the
literal `/yes_ask` substring — reworded, not suppressed). `kb/strategies/00-index.md` S13
flipped to `dead ✗`; S1/S5/S7/S8/S13 are now all decided at real asks, none live. Full
writeup: `findings/2026-07-04-sports-maker-s13-verdict.md`.

## 2026-07-04 16:20 UTC — Loop health audit, stranded-tape recovery, and candidate restock S12–S18

Interactive session (Ryan-requested): verify today's scheduled runs, the memory system, and
that R&D has runway. Three findings, three fixes:

1. **Triggers healthy.** All three loop triggers verified enabled and firing on schedule
   today — hourly collector (last fired 15:53 UTC), 5-hourly research loop (last 15:07 UTC,
   next 20:07), weekly retro (Sundays 12:00, next tomorrow). The VPS collector's :23 passes
   are landing on `main` every hour.
2. **Stranded tape recovered + protocol hardened.** The cloud collector's `git push origin
   main` fails intermittently (same permission boundary the research loop hit 2026-07-03) and
   its fallback branches were accumulating unnoticed: 10 passes across Jul 3–4 (15:55, 19:54,
   20:55, 21:55 / 00:54, 05:54, 09:54, 10:55, 12:54, 14:54 UTC) never reached `main` — a real
   hole in the canonical tape and in Q7's "days of tape" clock. Union-appended all **1,674
   missing lines** (20 crypto_hourly, 1,654 sports_pairs) into the per-day files with two-way
   verification, and added protocol step **0b** to LOOP-QUEUE.md so every research run sweeps
   `tape/hourly-*` branches automatically from now on. Swept branches deleted after merge.
3. **Queue was one item from dry — restocked.** Only Q8 was eligible (Q7 blocked to ~Jul 10;
   Q1 claimed by draft PR #4 awaiting `ODDS_API_KEY`). Ran a full generation pass (19 raw
   lens-rotated ideas → adversarial cut rejected 12 → 7 survivors): **S12–S18** appended to
   the registry — econ-print nowcast overlay (S12), the maker/bid side of S7's proven sports
   rich-ask (S13), ladder-overround underwriting (S14), cross-event implication scanner (S15),
   FedWatch-anchored shock fade (S16), Polymarket-macro parity (S17), single-poll fade (S18).
   Full dossier: `findings/2026-07-04-edge-candidates-s12-s18.md`. Queue items **Q9–Q13**
   appended (S13, S12, S15, S17, S14 in that order) — the loop now has ~a week of eligible
   milestones. Ryan's one open action: paste `ODDS_API_KEY` into the VPS env to un-block Q1.

Note: ntfy.sh is egress-blocked from this sandbox (HTTP 000 on CONNECT), so loop health was
verified from git history + trigger state instead of the phone feed.

## 2026-07-04 15:15 UTC — Q8 (new): Kalshi↔Polymarket World Cup round-market collector built (S9)

Claim-check: `git fetch origin main` in sync at `640da43` (only hourly `tape:` passes
since the last research run); the only open PR (#4) still claims Q1's odds-api leg
(unrelated, waiting on `ODDS_API_KEY`). But this time Q2 through Q6 are all DONE and Q7 is
BLOCKED (needs ≥7 days of Q2 crypto-hourly tape; only 2 days have accumulated) — **no
queue item was eligible** for the first time this project has hit that state. Per
LOOP-QUEUE.md's own append-don't-rewrite rule, appended Q8 and started the next
un-started registry candidate (S9) instead of ending the run early.

**Why S9, and why it's tractable now:** S9 (Kalshi↔Polymarket same-question lead-lag) was
idea-stage since 2026-06-18, blocked in spirit by "which same question exists on both
venues, priced the same way." Checked Polymarket's public API live and found a clean
match: Kalshi's `KXWCROUND` series ("Will `<team>` qualify for FIFA World Cup `<round>`?")
and Polymarket's "World Cup: Nation To Reach `<round>`" events are the IDENTICAL Yes/No
question on both venues — one binary market per (round, team), no de-vig needed (unlike
S7's moneyline-vs-sportsbook-odds), because both sides are already a single fillable price.

**Built `collection/polymarket_pairs.py`.** Kalshi leg: existing `Kalshi` client against
`KXWCROUND` (ticker grammar `KXWCROUND-<round_raw>-<team_code>`, title carries the full
team name). Polymarket leg: discovered via its public `/public-search` endpoint (a keyword
narrows the API-call budget, same role as `_SERIES_TITLE_RE` in `sports_pairs.py`), then
every hit is structurally re-confirmed by title/round regex before being trusted — no
hardcoded event IDs. Matched by exact (round, normalized team name); anything that doesn't
line up 1:1 is recorded `unmatched`/`ambiguous`, never guessed. Polymarket prices come off
its live CLOB order book (`clob.polymarket.com/book`, tagged `real_ask` — a real fillable
book, NOT the `outcomePrices` field on the market list, which is a last-trade/mid
reference and would have been a Hard-Rule-#4 violation to treat as a fill).

20 new unit tests (offline: FakeClient for Kalshi, monkeypatched `requests.get` for
Polymarket, injected `pm_discover`/`fetch_book` for the full `run()` pass — no network in
CI). Live pass against production: **48/48 open Kalshi `KXWCROUND` markets matched** to a
Polymarket counterpart, completeness ok, mean `price_gap_yes_ask` (Kalshi yes_ask minus
Polymarket best_ask) **+0.20¢**, range −3¢ to +3¢ — small and roughly symmetric on this
single snapshot, purely descriptive, not a verdict of any kind yet. `kb/strategies/00-
index.md` S9 flipped idea → data-collecting. 189 tests green (169 prior + 20 new),
`invariants --full` green.

**Next:** wire this into Q3's hourly pass so repeated snapshots accumulate (World Cup ends
Jul 19 — a narrow window), then run an actual lead-lag cross-correlation once there's
enough tape; the single-snapshot gap above says nothing about which venue moves first.

---

## 2026-07-04 10:30 UTC — Q6: daily anomaly sweep built (S3 + free-money detection)

Claim-check: `git fetch origin main` in sync; the only open PR (#4) still claims Q1's
odds-api leg (draft, waiting on `ODDS_API_KEY`) — skipped Q1. Every other candidate with a
completed first cut is now DEAD or gated, so Q6 (daily anomaly sweep) was the topmost
eligible TODO — the last unbuilt collector, and the first genuinely fresh candidate source
since S1/S5/S7/S8 all died to the overround.

**Built `scripts/anomaly_sweep.py`.** Discovers via `/markets?status=open` with NO
category/series filter — every active market on the platform, matching the item's own
wording, not just weather/crypto/sports. Two checks, both gated on a REAL fillable arb (a
cost strictly under $1 net of taker fees), not just an implied-probability curiosity:

1. **bracket_arb** — a complete strike ladder (a "less" catch-all + contiguous "between"
   bands + a "greater" catch-all, the exact shape Q2 found on KXBTC/KXETH) under one
   event_ticker whose yes_asks sum under $1+fees. Only scored when the sorted segments
   bookend the full real line (-inf..+inf) with no gap wider than the observed 2-cent
   Kalshi tick — an event missing an open-ended tail, or with a hole (one sibling market
   already closed), can't prove exhaustiveness and is skipped, not guessed at.
2. **cross_strike_monotonicity (S3)** — for nested "greater"/"less" threshold markets
   (e.g. temp>=80 subset of temp>=70), buying YES(wider)+NO(narrower) — both REAL asks,
   never a bid-derived synthetic price — pays a guaranteed >=$1 whenever that costs under
   $1 net of both legs' fees. An ask-vs-ask gap alone (the naive read of "monotonicity
   violation") can be closed by an unfilled quote; this is the fillable bar instead.

Added the fee/edge math (`fee_per_contract`, `true_arb_edge`, `monotonicity_crossing_edge`)
to `core/pricing.py` — the sanctioned Hard Rule #3 site, alongside `bracket_sum`.

**Real-world surprise the live pass surfaced:** Kalshi's open-market count is far larger
than any prior collector in this repo had touched — 10,000+ markets inside the first 10
pages alone, cursor still unexhausted. A genuinely unbounded pull grew this sandbox's RSS
past 3GB before it was capped. `main()` now defaults to `--limit 20000` (a real memory/time
bound, not a scope judgment call) and every tape record carries an honest
`markets_truncated` flag — a capped pass never claims full coverage it didn't do. `--limit
0` opts into an unbounded run for a box with more headroom (the VPS collector, say).

**Live-validated the pipeline against real data, not just fixtures.** Pulled KXBTC's actual
188-member current-hour ladder directly and ran it through `check_bracket_arb`: bracket_sum
**7.78**, correctly NOT flagged (edge deeply negative after fees) — this matches Q2/Q5's
already-documented "fine $100-band, 1¢-minimum-ask" structural overround, not a new
anomaly, confirming the check doesn't cry wolf on a known non-arb shape. Three capped live
sweeps (300 / 3,000 / 20,000 markets), all `completeness_ok`, 0 anomalies flagged — expected,
real cross-market arbs are rare by construction. No live multi-member "greater"/"less"
group turned up in the small weather sample probed to exercise `cross_strike_monotonicity`
end-to-end on production data; that check is proven correct via realistic synthetic
fixtures instead and will fire automatically the day the accumulating sweep tape contains
a real crossed pair.

**Wired into Q3's 09 UTC slot with zero code changes** — `hourly_pass.py` already invoked
`scripts/anomaly_sweep.py` as a subprocess by path, reporting `not_built` only because the
file didn't exist yet; it now runs for real every day at 09 UTC.

22 new unit tests (17 in `tests/test_anomaly_sweep.py`, offline `FakeClient` fixtures +
5 pricing tests in `tests/test_substrate_primitives.py`), 169 tests green, `invariants
--full` green. `kb/strategies/00-index.md` S3 moved `binding-test-defined` →
`data-collecting` (the sweep now runs daily; a verdict needs accumulated tape, same as
S7/S8 needed theirs).

**Next:** let the daily 09 UTC sweep accumulate tape in `tape/anomalies/`; once enough
days/passes exist, bootstrap S3's actual edge frequency×magnitude the same way S7c/S8 did.
No other candidate has a fresh angle right now — everything else is DEAD or blocked on
external inputs (Ryan's `ODDS_API_KEY` for Q1's odds leg, CME data for S2, the FEx tape
archiver for S4).

---

## 2026-07-04 05:20 UTC — Q5: S8 crypto-basis verdict — DEAD (ρ-guard kill)

Claim-check: `git fetch origin main` showed only hourly `tape:` passes since the last
research run; open PR #4 still claims Q1's odds-api leg (draft, waiting on
`ODDS_API_KEY`) — skipped Q1. Re-verified egress directly (`curl` to Kalshi, Coinbase
spot, and Coinbase's historical `/candles` endpoint) — all 200, including the exact host
that was 403'd last run. That's the unblock Q5 was waiting on, so picked it up as the
topmost eligible item.

**Fixed the lag confound Q5 flagged as the actual problem.** Added a `--historical-spot`
mode to `scripts/s8_basis_probe.py`: for each of the 36 unique settled hours accumulated
in `tape/crypto_hourly/` (18/symbol, up from 13), fetch Coinbase's free 1-minute candle
for the exact bucket at the settlement boundary instant instead of reusing the already-
lagged live `spot` snapshot. All 36 fetches landed an exact-epoch bucket match (Kalshi's
hourly grid always lands on a UTC minute) — lag drops from a mean ~1650s to **0s**
everywhere. Fetches are cached (`synthetic`-tagged, sha256'd) to
`tape/crypto_hourly_historical_spot/` so reruns don't refetch. Also caught and fixed a
latent unit bug while in this code: the half-band-crossing check used a fixed $100 width
for both symbols, but ETH's ladder actually steps $20 (confirmed from the tape's own
`floor_strike` spacing) — now per-symbol.

**Result: the ρ-guard, run for real this time, kills S8.** Corrected ρ: BTC 0.963→**0.9997**,
ETH 0.947→**0.9998** — the same territory as S5's weather NWS-vs-WU 0.99999 kill. More
decisive than ρ alone: the max observed settle-vs-spot gap **never crosses half a bracket
width for either symbol** across all 18 hours each (BTC worst $38.93 of a $50 half-band;
ETH worst $0.94 of a $10 half-band). One honest nuance: BTC's gap is small but not
zero-centered (mean +$16.43, 17/18 hours positive) — plausibly a real, small structural
premium of the CF Benchmarks settlement index over raw Coinbase spot — but it's an order
of magnitude below the bracket width, so it never would have flipped a settlement outcome
relative to naive spot-watching in this sample.

**Verdict: S8 DEAD.** This is the guard's own designated cheap-kill gate triggering clean,
same mechanism as S5 — no bootstrap needed to reach it. n=18/symbol is thin (a first-cut
kill, not a large-sample proof), noted plainly, but there's no case for more Q5 data
collection. `kb/strategies/00-index.md` S8 flipped to `dead ✗`. 7 new unit tests
(`tests/test_s8_basis_probe.py`, offline/monkeypatched HTTP — the new fetch/cache/report
logic is genuinely testable, unlike the pure-analysis code the rest of the probe already
had); 147 tests green, `invariants --full` green. Full writeup:
`../findings/2026-07-04-crypto-basis-s8-verdict.md`.

**Next:** every candidate with a completed first cut is now DEAD (S1, S5, S7, S8) or
gated/blocked (S2, S3, S4, S7's maker side, S9-S11). Q6 (daily anomaly sweep) is the
topmost untouched TODO item and the most promising near-term source of a fresh candidate.

---

## 2026-07-04 00:12 UTC — Q4/S7c: sports CLV verdict — DEAD

Claim-check: main had advanced (hourly tape + merged PR #7 adding the check-ntfy skill and
Q5's writeup); rebased clean. Open PR #4 still claims Q1's odds-api leg (draft, waiting on
`ODDS_API_KEY`) — skipped Q1, picked up Q4 (topmost eligible IN-PROGRESS item, S7c was the
one remaining sub-stage).

**Accumulated the rest of the tournament.** S7b's join ran on a partial Kalshi tape (25
`KXWCGAME` events) because the original fetch used a low page limit. Re-fetched with
`--limit 100`: Kalshi actually retains **87 settled World Cup games** end-to-end so far
(Jun 11 group stage through Jul 3). Re-fetched ESPN closing odds for the matching window
and re-ran the join: **77/87 matched**, 0 ambiguous, 0 unparseable (S7b's 27/27 match rate
on a narrower window generalizes cleanly to the wider one). Combined with S7b's 3 already-
joined NBA games (deduped by `kalshi_event_ticker`, no new NBA fetch this pass): **80
unique priced games, 237 priced outcomes** — about 3x S7b's descriptive n.

**Ran the binding test.** New read-only `scripts/s7c_sports_clv_bootstrap.py` (no network;
reads `tape/sports_clv/*.jsonl`) block-bootstraps `edge_after_fee` (DraftKings-close de-vig
fair prob minus Kalshi's real pregame ask minus the taker fee) **by game** — not by
outcome, since a game's 2-3 outcomes share one de-vig and one kickoff and are not
independent draws. 10,000 resamples: mean **−0.0235**, 95% CI **[−0.0245, −0.0225]**. Both
bounds sit clearly below zero — this isn't a near-miss, Kalshi's pregame ask is running
richer than the DraftKings-implied fair price by more than the fee covers.

**Verdict: S7 is DEAD** (taker side, vs DraftKings-close) — CLAUDE.md's bar is a CI that
clears zero, and this one doesn't just fail to clear it, it sits confidently on the wrong
side. Per the Stop rules a DEAD verdict from a real, block-bootstrapped test is a success:
it's decided, `kb/strategies/00-index.md` S7 flipped to `dead ✗`, and the loop stops
spending cycles on it. Two things this verdict does *not* cover, flagged for anyone
revisiting the sports family: the maker/bid side of the same mispricing (a different trade,
untested here), and what happens with a sharper (Pinnacle) fair-price anchor if one ever
becomes free — DraftKings retail vig is a documented, not eliminated, source of noise in
`fair_prob`.

0 new unit tests (pure read-only analysis script over existing tape, same precedent as
`s8_basis_probe.py`/`longshot_fade_probe.py` — probes aren't unit-tested, collectors are);
140 tests green (unchanged), `invariants --full` green. Full writeup:
`../findings/2026-07-04-sports-clv-s7-verdict.md`.

**Next:** S8 (crypto-hourly settlement basis) is now the most-advanced open candidate —
still blocked on the ρ-guard needing historical-candle spot instead of lagged live spot;
Q6 (daily anomaly sweep) is the topmost untouched TODO item.

---

## 2026-07-03 23:34 UTC — Q5: S8 crypto-basis first cut — overround flag resolved, ρ-guard inconclusive

Claim-check: only open PR (#4) is Q1's unrelated odds-api work — Q5 unclaimed, picked it up.
Built `scripts/s8_basis_probe.py`, a read-only pass over the `tape/crypto_hourly/` tape Q2
already accumulated (13 unique settled hours each for BTC/ETH so far). Two questions, one
resolved and one blocked:

**Resolved — the +$9.27 BTC overround flag from Q2 is mostly real, not a floor-tick
artifact.** Deep out-of-the-money bands pinned at Kalshi's 1¢ minimum ask do inflate the
number (a coherent market prices them near $0, not $0.01), but they only account for **33.9%**
of BTC's mean +$5.00 overround across 19 passes — **66.1% comes from genuine near-the-money
spread**, the bands S8's eventual basis trade would actually touch. ETH splits closer to even
(56.9%/43.1% — its ladder has roughly a third as many outcomes, so the floor bands carry
proportionally more weight). Either way: the overround is a legitimate cost benchmark, not an
artifact to explain away.

**Blocked — the ρ-guard itself couldn't be run as the queue specified.** The queue's own
phrasing ("public candlesticks... vs public spot **history**") calls for spot sampled at the
settlement instant; what `crypto_hourly.py` actually pairs is Kalshi's exact settlement value
against whatever Coinbase/Kraken printed whenever that hour's *pass* happened to run — a mean
**29-minute lag** (VPS `:23`/cloud `:53` cadence vs on-the-hour settlement). Over 29 minutes
ordinary BTC volatility can move price well past $100, which fully explains the observed
gaps (max $150.41, 84.6% of hours over half a $100 band) without invoking any real BRRNY-vs-
spot mismatch — a naive ρ on price *levels* is also close to a foregone 1.0 regardless
(two price series tracking the same asset correlate on trend alone; not the same situation
as the weather NWS/WU check, which compared two co-located sensors). Tried the fix — pull
Coinbase's free, keyless historical `/candles` endpoint at each settlement's exact
`close_time` — but this session's egress is currently blocked to every external host tested,
including Kalshi's own API (403 on the CONNECT tunnel, confirmed via the proxy's own status
endpoint, not a code bug).

**S8 stays `data-collecting`, not DEAD.** Unlike S1/S5 this isn't a CI failing to clear zero
— no valid CI exists yet because the paired data doesn't answer the right question. This is
also a standing finding in its own right: `crypto_hourly.py`'s spot capture needs to move to
settlement-instant sampling (or a historical-candle backfill) before S8's basis-vs-overround
comparison can mean anything. 0 new unit tests (pure analysis script over existing tape,
matching the `longshot_fade_probe.py`/`weather_rehab_s5.py` precedent of unit-testing the
collectors, not the one-off probes); 140 tests green (unchanged), `invariants --full` green.
Full writeup: `../findings/2026-07-03-crypto-basis-s8-q5.md`.

**Next:** rerun `s8_basis_probe.py` with historical-candle spot the moment egress reopens to
Coinbase (or Kalshi, to confirm the environment more broadly); only then does the ρ-guard
verdict — and any subsequent block-bootstrap — mean anything for S8.

---

## 2026-07-03 19:40 UTC — Q4/S7b: event-matching join built, first real pregame-ask-vs-devig pass

Claim-check: open PR #4 claims Q1's remaining odds-api work (draft, waiting on Ryan's
`ODDS_API_KEY`) — skipped, moved to Q4 (topmost eligible IN-PROGRESS item). Built the join
S7a deferred, all in `collection/sports_history.py`:

1. `extract_kalshi_teams` — parses the two team names out of a Kalshi game title (three
   live title shapes: WC full form with the ticker-code repeat, WC bare form, NBA
   `"Game N: <A> at <B> <CODE> at <CODE> (Mon DD)"`).
2. `match_kalshi_espn` — team-name containment match (handles NBA's city-name-vs-full-
   team-name case) + ±1-day kickoff window; every row comes back `matched` / `ambiguous` /
   `no_match` / `unparseable_title`, nothing silently dropped or guessed.
3. `run_clv_join` — for matched games: real pregame ask via `candlestick_ask_before`
   anchored at ESPN's actual kickoff (not Kalshi's own `occurrence_datetime`, per S7a's
   second trap), de-vig DraftKings' close (`american_to_decimal` →
   `sports_pairs.devig_multiplicative`), per-field `real_ask`/`synthetic` source tags.

Found mid-build: the S7a ESPN pull's date window (Jun 15-21, group stage) had zero overlap
with the Kalshi WC tape's actual event dates (Jun 26-Jul 2, round of 32/16) — the two legs
were captured for different date ranges by accident. Re-fetched ESPN for the correct window
(`--espn-fetch soccer:fifa.world:20260626-20260702`) before joining.

Live pass: **27 games matched** (24 WC, 3 NBA Finals; 2 NBA hit `ambiguous` — same two teams
on consecutive dates, both inside the ±1-day window, correctly flagged rather than guessed),
**78 outcomes priced**, mean pregame `bracket_sum` **1.020**, mean `edge_after_fee` **−0.0241**
across the 78 outcomes — small-n and descriptive only, NOT a bootstrap-worthy verdict yet.
37 new unit tests (155 total green, fully offline), `invariants --full` green. Full writeup:
`findings/2026-07-03-sports-history-s7b.md`. Next: S7c — accumulate more games as the
tournament progresses, block-bootstrap **by game** (outcomes within a game aren't independent
draws), verdict.

## 2026-07-03 15:30 UTC — Q4/S7a: sourced sports history, found Kalshi's ~60-day retention wall

Claim-check: no open PRs, branch synced to `main` tip (`1abc535`). Built
`collection/sports_history.py` (Kalshi settled-event leg + free ESPN closing-odds leg,
captured separately, no join yet — that's S7b) + 13 unit tests, offline/FakeClient, no
network in CI. Two load-bearing discoveries, both documented in
`findings/2026-07-03-sports-history-s7a.md`:

1. Kalshi's public API purges a settled market's data (and therefore candlesticks) ~60
   days after close, even though `/events?status=settled` keeps listing the event forever.
   Verified by binary search on NBA events. Kills the "last-season NFL" half of S7's
   original spec outright (0/15 sampled NFL events had retrievable markets — full season
   ended Feb, all purged); leaves NBA to only its playoff tail (~40 games, Apr 30 onward);
   leaves **World Cup 2026** (in progress, started Jun 11) as the one series with its
   entire history-to-date still live — now the strongest S7 candidate, and still
   time-sensitive (ends Jul 19).
2. A market's `occurrence_datetime`/`expected_expiration_time` field is NOT kickoff — it's
   the expected *resolution* time, seconds-to-minutes after `close_time`, both clustered at
   game END. Caught before commit: a first draft used it as "decision time" and pulled a
   candlestick showing `yes_ask=1.0` on every outcome of a live 3-way bracket (impossible
   pregame). Fixed: the collector no longer claims a decision/pregame price from Kalshi
   alone; it captures raw timing fields + an honestly-labeled `sample_ask_near_close`
   candlestick, and defers real pregame pricing to S7b (needs ESPN's `event.date`, the
   actual kickoff, to compute the correct candlestick window).

Live passes: 25 World Cup + 40 NBA + 15 NFL Kalshi-side records, 23 WC + 5 NBA ESPN-side
DraftKings odds records (open+close both present, tagged `synthetic`) → 108 lines in
`tape/sports_history/dt=2026-07-03.jsonl`. Gates: 117 tests green (104 prior + 13 new),
`invariants --full` green. Next: S7b game-matching join (Kalshi 3-4 letter codes ↔ ESPN
team names) + point `candlestick_ask_before` at real kickoff.

## 2026-07-03 10:12 UTC — Q3 hourly entry point built; sports + crypto collectors now unified

Claim-check: no open PRs against `main`, local branch already at `main`'s tip (`f6c946a`).
Built `collection/hourly_pass.py` — the single command the hourly Haiku routine runs, per
the Q3 spec. It calls `sports_pairs.run()` and `crypto_hourly.run()` independently: each is
wrapped so an exception in one is caught and recorded rather than taking the other sub-pass
down with it (a partial outage in one collector must not silently zero out the other's
otherwise-honest capture). Overall `completeness_ok` is the AND of each sub-pass's own
already-computed honest completeness signal — never re-derived optimistically, never faked.

`n_markets`/`n_lines` needed a small design call the queue text didn't spell out. Each
`sports_pairs` tape line is one game (2-3 underlying Kalshi markets); each `crypto_hourly`
line is one symbol's full bracket ladder (up to ~188 underlying markets). Reporting
"lines written" alone would make a crypto pass and a sports pass look comparable when
they're wildly different in market coverage, so `hourly_pass` reads back only the tape
lines it just wrote (filtered by `capture_id`, since the append-mode JSONL files carry
prior passes' lines too) and sums each record's own `expected_outcomes` into `n_markets`,
keeping `n_lines` as the plain record count. Both numbers come straight from data the two
collectors already persist — no changes needed to either already-tested module.

`scripts/anomaly_sweep.py` (Q6) doesn't exist yet, so the 09-UTC-only slot checks for the
script file and reports `{"status": "not_built"}` honestly rather than skipping silently or
pretending the slot ran — the moment Q6 lands, `hourly_pass` picks it up with no further
wiring (subprocess invocation, not a Python import, matching how `invariants.py` is already
run as a script rather than imported).

15 new unit tests, fully offline (injected stub `sports_fn`/`crypto_fn`/`anomaly_sweep_fn`,
no network, no real collector code exercised): both sub-passes complete → `completeness_ok`
True with correct `n_markets`/`n_lines` math (including the stray-capture_id exclusion);
either sub-pass's own incompleteness propagates; either sub-pass raising is caught, recorded,
and does not stop the other from running or crash `run()`; the anomaly slot is skipped
outside hour 9, and inside hour 9 correctly treats `not_built`/`ok` as non-failing and
`error`/an exception as failing; the tape-accounting helper in isolation; CLI flag wiring
(`--sports-limit`, `--crypto-symbols`) reaching the real collector functions with correct
kwargs, and a nonzero exit code on an incomplete pass.

**Live smoke, twice:** first `--sports-limit 3 --crypto-symbols BTC` (188 markets, 1 line,
ok) to keep it cheap, then a full unlimited pass — 193 confirmed sports games + both crypto
symbols, 680 underlying markets across 195 tape lines, `completeness ok`. Both passes
appended for real to `tape/sports_pairs/dt=2026-07-03.jsonl` and
`tape/crypto_hourly/dt=2026-07-03.jsonl` (kept as genuine tape, not scratch). Gates: 104
tests green (89 prior + 15 new), `invariants --full` green.

**Next:** Q4 (S7 historical sports-CLV backtest — the try-first edge) and Q5 (S8 crypto
settlement-basis first cut) are now the topmost eligible TODO items; Q6 (anomaly sweep) still
needs building before `hourly_pass`'s 09 UTC slot does anything beyond reporting
`not_built`. The hourly Haiku routine can now run `python -m collection.hourly_pass`
unattended once wired up on its own schedule (that wiring is outside this repo).

---

## 2026-07-03 05:14 UTC — Q2 crypto-hourly settlement collector built + first live pass

Built `collection/crypto_hourly.py`, mirroring `sports_pairs.py`/`capture_orderbooks.py`
discipline for Kalshi's `KXBTC`/`KXETH` ("Bitcoin/Ethereum range") series, which price a fresh
hourly bracket ladder every hour (ticker grammar `SERIES-YYMONDDHH-[T|B]<strike>`, `HH` in ET so
`close_time = HH+4:00Z` during EDT — confirmed empirically against the live API). One pass per
symbol captures three paired things: **(1)** the CURRENT hour's bracket book (`real_ask` BBO,
`bracket_sum`/`overround_absorbed` via `core.pricing`); **(2)** the PREVIOUS hour's settlement —
Kalshi's own `result` + `expiration_value` (the CF Benchmarks index average actually used to
settle), tagged `broker_truth`; **(3)** spot from Coinbase (Kraken fallback if Coinbase fails),
tagged `synthetic` per the queue spec (an external reference price, not itself a Kalshi fill).
Storing all three paired per pass is exactly what S8's ρ-guard (spot-vs-settle correlation) needs
computable from tape alone, without any live analysis code.

One non-obvious discovery-layer bug avoided: the `KXBTC`/`KXETH` series also carries a stray
long-lived group reusing the same hourly ticker grammar (`KXBTC-26JUL0317`, empirically observed
open continuously since 2026-06-26 — a different market shape, not the hourly ladder) sitting
alongside the genuine current-hour group in the `status=open` response. Naively picking "whatever
event_ticker is open" would silently mix a week-old group into "current hour" data. Fixed by
filtering on `close_time - open_time <= 65min` before picking the soonest-closing candidate — a
duration check, not a ticker-string special case, so it generalizes to any future stray group.
Previous-hour's event_ticker is derived by pure arithmetic on the current group's date+hour token
(subtract 1 hour, handle day/month/year rollover) rather than an extra discovery call. 21 new unit
tests (offline `FakeClient` + monkeypatched HTTP for the spot fallback, no network): hour-token
arithmetic incl. rollover, stray-group exclusion, honest completeness (missing ask drops that
outcome), settlement status states (settled/pending/not_found/fetch_error, and disagreeing
`expiration_value`s surfaced rather than silently picking one), spot fallback + total-failure
handling (never a stale/fabricated substitute).

**First live pass** (`tape/crypto_hourly/dt=2026-07-03.jsonl`): both symbols `pass_complete`.
BTC (`KXBTC-26JUL0302`, 188 members: 1 T-tail-below + 186 $100-wide bands + 1 T-tail-above, a
clean mutually-exclusive partition like weather's `{T-tails + B-bands}` shape): bracket_sum
**$10.27**, i.e. overround_absorbed **+$9.27** (real_ask) — two orders of magnitude fatter than
weather's ~9.8¢ or sports' +21.3¢. ETH (`KXETH-26JUL0302`, 75 members): bracket_sum **$2.23**,
overround **+$1.23**. Plausible mechanism, NOT yet verified as a real edge: 186 very fine ($100)
bands each carry Kalshi's apparent 1¢ minimum quoted ask even when near-zero-probability, so
summing ~180 deep-out-of-the-money 1¢ floors alone accounts for most of the excess — this is a
collector observation for Q5 to actually test, not a backtest result; no CI computed, no verdict
on S8 yet. Gates: 89 tests green (68 prior + 21 new), `invariants --full` green.

**Next:** Q3 (hourly entry point) can now wire in both Q1 + Q2; Q5 (S8 first cut) can start
building on this tape once a few hours have accumulated, and should investigate the fine-band
minimum-ask mechanism above before treating the raw overround as a scoring input.

---

## 2026-07-03 — Loop protocol fixed: cloud sessions can't push to `main`; PR + claim-check added

Two consecutive `kalshi-research-loop` firings (23:18Z and 00:17Z, both same 5-hour window)
each independently rebuilt Q1 (`collection/sports_pairs.py`) from scratch and stranded the
result on their own branch (`claude/brave-mccarthy-ek6ybp`, `claude/brave-mccarthy-7rnhry`) —
neither reached `main`, neither opened a PR. Root cause: a cloud session cannot
`git push origin main` here — confirmed empirically, both runs rebased clean against `main`
(merge-base == main tip, no conflict) yet both still fell back to their session's own branch,
which only happens on a permission boundary, not a race. `LOOP-QUEUE.md`'s old protocol
(step 6: `git push origin main`, fall back to a branch only after 3 failed retries) assumed a
push that was never going to succeed, so every firing silently fell back and the queue's
"memory" (Status lines, Log of runs) never actually reached the next firing's starting state.

Fix, in `LOOP-QUEUE.md`:
- **New step 0 (claim check):** before picking work, list open PRs against `main`; an item
  named in an open PR is claimed — don't redo it, merge the PR if it's green instead.
- **Rewrote step 6:** push your own branch → open a PR → merge it immediately (squash) if
  `pytest` + `invariants --full` are green and the diff is research/data-only (Stop rules
  already forbid execution/credential code, so this is a re-check, not a new bar). Broken or
  partial work stays an open PR with an IN-PROGRESS note instead of merging.

Reconciled the stranded work: kept `claude/brave-mccarthy-7rnhry`'s `sports_pairs.py` (title-
regex + structural per-game confirmation before capture — the defense against exactly the bug
the other branch had to live-patch, ticker-suffix-only classification letting non-moneyline
`GAME`-suffixed prop series through) as the surviving implementation, folded the other run's
tape capture in as extra data (357 events/07-02 pass + 188 games/07-03 pass, different
timestamps, no conflict), merged to `main` via PR. Gates: 68 tests green, invariants green.

**Why this is the actual fix, not just cleanup:** `LOOP-QUEUE.md` + this log were already
meant to be the loop's memory system and active to-do list — they just couldn't work while the
git mechanics silently dropped every firing's state on an orphan branch. The claim-check +
PR-merge protocol is what makes "pick the topmost item, do the work, persist it" actually
cumulative across 5-hour firings instead of amnesia dressed up as append-only logging.

---

## 2026-07-03 00:14 UTC — Egress unblocked (Q0b); Q1 sports-pairs collector built, first live tape

Re-ran the Q0b cheap egress re-check (self-healing item, runs first while anything is
`BLOCKED(egress...)`): all 4 hosts that failed yesterday now answer for real — Kalshi REST 200
(`exchange_active:true`), Coinbase 200 (live BTC ask), Kraken 200 (live server time), the-odds-api
401 (reachable, just no key). `capture_orderbooks.py --limit 3` proved it end-to-end against live
Kalshi. This is an environment change (Ryan widened the sandbox allowlist, or an env swap), not a
code fix. Flipped Q0b DONE and every `BLOCKED(egress...)` item in `LOOP-QUEUE.md` back to TODO;
refreshed `tape/cloud-env-check.md`. Per Q0b's own instruction, continued straight to the new
topmost TODO item instead of ending the run there.

**Q1 (time-sensitive — World Cup ends Jul 19):** built `collection/sports_pairs.py`, mirroring
`capture_orderbooks.py`'s discipline without forcing weather's city/target_date shape onto sports.
Discovery is two-stage: a title heuristic over the ~2300 Sports-category series narrows the
API-call budget (`*Game(s)*` minus prop-bet keywords), then every candidate game group is
structurally confirmed (2-3 mutually exclusive outcomes, every market titled "&lt;A&gt; vs &lt;B&gt;
... Winner?") before anything is captured — the heuristic only saves calls, it never decides what
gets persisted. Each confirmed game is one game group priced as a bracket exactly like the weather
ladders, so `core/pricing.bracket_sum`/`overround` (Hard Rule #3's one sanctioned site) applies
unchanged. Ticker grammar (`SERIES-YYMonDD<TEAMS>-OUTCOME`, e.g.
`KXWCGAME-26JUL06USABEL-USA`) parses with a new `parse_sports_ticker`; a `devig_multiplicative`
function is implemented and unit-tested for the odds-api leg, unused live since `ODDS_API_KEY` is
absent (Q1's spec: capture the Kalshi leg anyway, mark the odds leg `blocked_key`, never fabricate
it). 19 new unit tests (offline `FakeClient`, no network): ticker parsing, moneyline-group
confirmation, de-vig math, and a full capture pass with honest completeness (a missing ask drops
that outcome and flips `completeness_ok`, never fabricated).

**First live pass:** 197 candidate series → 188 confirmed moneyline games across 16 series (10 of
them `KXWCGAME` World Cup games), 100% `completeness_ok`, written to
`tape/sports_pairs/dt=2026-07-03.jsonl`. Mean bracket overround **+21.3¢ (real_ask, n=188)** —
notably fatter than the ~9.8¢ weather overround that killed S1/S5; plausibly thin/new markets
rather than a structural property of sports moneylines, needs a liquidity-filtered re-cut before
it says anything about S7. Flipped S7/S11 to `data-collecting` in the registry (not `tested` — no
CI computed yet, this is infra + one snapshot). Gates: 68 tests green (49 prior + 19 new),
`invariants --full` green.

**Next:** accumulate `sports_pairs` tape over multiple passes (needs Q3's hourly entry point,
which is still blocked on Q2); get an `ODDS_API_KEY` to unblock the Pinnacle/de-vig leg S7's
binding test actually needs. Q2 (crypto-hourly collector) is now the topmost eligible TODO item.

---

## 2026-07-02 22:43 UTC — Q0 cloud environment check: all external hosts BLOCKED by egress policy

Ran the cloud-sandbox reachability check the queue calls for before any of Q1–Q7 can move: Kalshi
public REST (`python -m collection.capture_orderbooks --limit 3`), Coinbase + Kraken public spot,
and `api.the-odds-api.com` (plus a presence-only check for `ODDS_API_KEY`, absent). **All 4 hosts
failed identically** — the sandbox's egress proxy answered every CONNECT with a 403 (`gateway
answered 403 to CONNECT (policy denial or upstream failure)`), and its `noProxy` allowlist covers
only package registries + `anthropic.com`, no data provider. Per the proxy runbook this is an
organization policy denial, not a transient fault — not to be retried or routed around. Full
evidence and interpretation in `tape/cloud-env-check.md`.

**Consequence:** every downstream collector needs one of these hosts, so Q1, Q2, Q3, Q4, Q5, Q6 are
now `BLOCKED(egress policy)` in `LOOP-QUEUE.md` — this is essentially the entire active queue. Q0
itself is the only item this run's cloud sandbox could actually complete; nothing here indicates a
bug in `capture_orderbooks.py`/`normalize.py` (never got past the TLS tunnel). **This needs Ryan**:
either widen this environment's egress allowlist to include a Kalshi host, a public crypto spot
host, and an odds API host, or run the collectors from a pool that already has broader network
access — no cloud run can change its own policy. Gates: 53 tests green, `invariants --full` green
(no code changed, so nothing new to gate — recorded for protocol compliance).

**Next:** once egress is widened, Q1 (sports pairs collector, time-sensitive — World Cup ends Jul
19) is the immediate next milestone.

---

## 2026-06-18 19:41 ET — S2 FOMC×ZQ free-data first cut: structure validated (n=1), worth the CME spend

Free-data, single-meeting first cut of S2 on the just-resolved June 2026 FOMC — Kalshi PUBLIC historical
candlesticks (`yes_ask` BBO) × free Yahoo ZQ. `scripts/fomc_zq_basis_s2.py`, `findings/2026-06-18-fomc-zq-s2.md`.
**n=1 STRUCTURE check, NOT an edge.**

- **FOMC bracket overround = mean +3.35¢** (3–4¢) vs the **~10¢** weather overround that killed pt1/S1/S5 →
  **~3× cleaner; the prob-to-prob structural thesis HOLDS** — the reason S2 is the post-weather pivot.
- June was **LOW-INFORMATION**: both venues priced a near-certain hold (Kalshi P(hold) 0.942–0.962, ZQ
  0.931–0.977); net-of-fee basis mean **−1.39¢/contract**, 5/163 periods positive → no tradeable gap on THIS
  event (expected for a consensus hold; one event can't yield a CI).
- **Verdict: structure worth the CME spend.** Full version needs intraday ZQ ticks (daily close too coarse —
  ZQ P(hold) swung 0.931→0.977 on a single 1-tick move; the `N_post` divisor amplifies it) + many **contested**
  meetings + block-bootstrap CI (block=meeting) + Kalshi L2 depth + frozen-pre-position risk modeling. GATED on
  Ryan (CME data sourcing).
- Honesty: `yes_ask.close` tagged `real_ask` (BBO-at-candle-close caveat — overstates fillable size); ZQ-prob
  `synthetic`. Prior-contested-meeting pull deferred (2025 tickers use a different target-range scheme +
  rate-limits), not faked. **53 tests green, invariants --full green.** Tape/DB untouched.

---

## 2026-06-18 19:40 ET — 3 new cross-venue basis candidates drafted (S7/S8/S9) via /first-principles

Ideation pass through the **cross-venue basis lens** (Kalshi vs a different venue pricing the same/
correlated resolution). Goes BEYOND S2 (FOMC×ZQ prob-to-prob). All three grounded in live
settlement-spec + data-access research (Perplexity, 2026-06-18; CF Benchmarks RTI, Polymarket CLOB
docs, Kalshi historical candlestick REST). None is in the dead ledger.

- **S7 — KXBTC vs Polymarket crypto: settlement-index + sampling mismatch.** Kalshi KXBTC/KXETH
  hourly brackets settle on **CF Benchmarks RTI = 60s average of a multi-exchange index**;
  Polymarket crypto settles on a **single-exchange (Binance) 1-min candle / last print**. Same
  nominal hour, different fixing → the two venues' implied "price lands in bracket X" can disagree
  whenever Binance basis vs the multi-exchange index, or a sub-minute spike, moves the single print
  off the 60s mean. Mechanism: settlement mismatch, NOT a probability claim. Both real-price histories
  are FREE/public (Kalshi `/historical/market_candlesticks` yes-OHLC; Polymarket CLOB
  `/prices-history` + Gamma resolved outcome). Overround note: crypto-hourly binaries are 2-outcome
  (low overround) BUT Kalshi crypto taker fee is the fat 7%-class — must clear that.
- **S8 — Kalshi single-game sports vs Pinnacle sharp closing line (directional on the laggard).**
  Documented: Kalshi order-book sports prices LAG Pinnacle's vig-removed line by minutes after a
  discrete info shock (injury/scratch/steam); practitioner reports 2–3pp gaps before catch-up;
  election-market analog measured 12–18 min lag. Mechanism: sharp dealer (Pinnacle) reprices
  instantly; Kalshi only moves when a taker crosses the book → exploitable catch-up window. Trade
  the laggard (Kalshi) directionally toward the devigged Pinnacle number. Real ask = Kalshi BBO
  (candlestick yes_ask OHLC + live book); reference = Pinnacle/odds-API devig. Overround: liquid
  marquee games show 1–3¢ spreads — thin enough that a 2–3pp lag can clear it.
- **S9 — Kalshi vs Polymarket same-event PRICE-DISCOVERY lead-lag (timing, not static level).**
  "Who Wins and Who Loses" (SSRN) + LOOP-violation paper: **Polymarket leads Kalshi in price
  discovery** (24/7 crypto crowd, zero maker fee) on the SAME politics/macro yes/no event; the
  static level-wedge has compressed to 1–2% and is NOT cleanly unidirectional, so the edge is the
  *timing* — fade Kalshi toward Polymarket's already-moved price after a discrete shock, not a
  standing level arb. Mechanism: segmented user bases + USDC/USD rail friction keep arbitrage from
  enforcing instant parity. Both prices FREE (Kalshi candlestick + Polymarket CLOB). Overround:
  Kalshi politics binaries are richer (sum 110–140% multi-outcome); the lead-lag must clear Kalshi's
  taker fee + spread on the 2-outcome legs.

These graduate to the registry as **S7/S8/S9 (idea)**. Binding tests are all no-capital replays on
free public history. Returned via the workflow's StructuredOutput; full rationale in the council/
first-principles brief to follow before any data-collection spend.

---

## 2026-06-18 15:03 ET — S5 weather rehab TESTED → DEAD. Weather family is dead at real asks.

**The decisive result.** With Ryan's go-ahead, ran the S5 weather-rehab real-ask paper test —
the question that decides the project's direction. Verdict: **the weather family is DEAD at real
asks, even with proper EMOS calibration.** (`scripts/weather_rehab_s5.py`,
`findings/2026-06-18-weather-rehab-s5.md`, per-trade dump `reports/weather_rehab_s5_full.json`.)

- **EMOS works — but it's necessary, not sufficient.** Leave-one-day-out EMOS calibration cut
  pooled CRPS **2.366 → 2.180 (−7.86%)**, fixing the underdispersion exactly as the literature
  (Gneiting 2005) predicts. The better probability is real.
- **The dollar edge is not.** 641 trades (3-model ensemble: GFS+ECMWF-IFS025+ICON; GEM single-runs
  not archived for the window so honestly dropped → member_count=3; no `ncep_gefs025`). Mean net
  **−$0.02789/trade**, 95% moving-block-bootstrap CI **[−$0.06297, +$0.00788]** (n_boot=10k, 21
  contract-day blocks). **Lower bound does NOT clear zero.** Killed by the same **~9.8¢ mean
  overround** that ate pt1 and S1. A better probability cannot beat a ~10¢ structural tax here.
- **Adversarial checks (the discipline that matters):** edge-bar sweep — raising the conviction bar
  to 0.10/0.15 made P&L *worse* (CI fully below zero), the opposite of a real edge; independent
  fill/cost sign audit — 0 mismatches (no repeat of S1's near-miss); anti-leak — used the Open-Meteo
  **Single Runs API pinned to (D−1) 00Z** (a genuine ~24h-ahead leak-free forecast), NOT the
  historical-forecast archive (which stitches lead≈0 ≈ actuals and would leak — venues.yaml warns);
  0 leak-guard drops. Prices `real_ask`, all 6 provenance fields persisted per trade.
- Caveats (honest): short 22-day spring window, EMOS data-thin, decision time near market open,
  L1-only fills (haircut modeled not measured).

**PROJECT DIRECTION CHANGE:** weather is no longer "on probation" — it is **proven dead at real
asks**. The 3 weather angles tried (raw ensemble pt1, longshot-fade S1, EMOS-calibrated S5) are all
dead to the overround. **Pivot to non-weather: S2 (FOMC×ZQ basis — structurally NO bracket
overround), S3 (cross-strike staleness), S6 (market-making — earn the spread instead of paying it).**

Verified: **53 tests green, `invariants --full` + `--db` green**, recovered tape read-only. S5
committed to `main`. Only S2 (FOMC×ZQ) remains on the queue — GATED on CME data sourcing (Ryan).

---

## 2026-06-18 12:53 ET — S1 longshot-fade FALSIFIED · EMOS reproduced · forecast tape live

Three parallel probes ran on top of the S0 substrate (autonomous `/loop`, 3 subagents). Merged
tree verified: **53 tests green, `invariants --full` green**, recovered tape DB untouched (read-only).

- **S1 longshot-fade → DEAD (real asks).** n=990 reconstructed-`real_ask` KXHIGH brackets from the
  24GB recovered tape. The favorite-longshot bias *exists* (longshots <0.20 realize fewer wins than
  priced, gaps −1.4¢..−7.0¢; favorites >0.65 underpriced) but is single-digit cents, **swamped by a
  +9.84¢ mean overround**. Maker-NO-on-longshot net P&L **+$0.00448/trade, 95% block-bootstrap CI
  [−$0.00486, +$0.01333]** — lower bound does NOT clear zero; sweep 0.05→0.25 uniformly null, deepest
  longshots negative. **A whole bias-chasing family falsified**, as the dossier predicted. Probe:
  `scripts/longshot_fade_probe.py`; writeup: `findings/2026-06-18-longshot-fade-s1.md`. **Near-miss:**
  the first run cleared zero on a cost-model sign bug (maker entry booked as a 2¢ *improvement* not a
  *cost* — the exact pt1 prime-directive failure mode); caught + fixed. **Candidate invariant filed:**
  a cost haircut must never move the entry in the trader's favor. (Tape caveat: T-24h lands near market
  open; L1-only, fill-prob haircut modeled not measured; single 22-day spring window.)
- **EMOS reproduced (#5).** `scripts/emos_demo.py` (stdlib-only, deterministic) fits a 1-param-spread
  EMOS Gaussian by minimizing closed-form Gaussian CRPS: **CRPS 1.663 (raw ensemble) → 0.717 (EMOS),
  −56.9%**, bracket P(74≤Tmax<78)=0.761. Flipped `kb/quant-finance/01-weather-forecasting-alpha.md`
  from `cited` → `reproduced`. (Calibrated post-processing beats the raw underdispersed ensemble — the
  precondition for any S5 weather-rehab attempt.)
- **Forecast tape now exists (#3).** `collection/forecast_collector.py` (+10 offline tests) — single
  read-only Open-Meteo pass per city × {gfs_seamless, ecmwf_ifs025, icon_seamless, gem_global} (NO
  `ncep_gefs025`, Hard Rule #1, with a runtime guard), append-only JSONL with ms `fetch_ts` + raw
  sha256 + `source_tag=synthetic`, honest completeness. Live smoke (NYC, 2026-06-18): 89.6/89.2/90.1/
  86.3°F across models. The previously-zero most-reused missing input is no longer zero.
  **Scheduling still GATED** (laptop-cron HOLD).

**Loop end-state:** all 4 unblocked Next items done (S0 substrate, S1, EMOS, forecast collector). **Two
items remain GATED on Ryan:** #2 cron forward capture (Kalshi creds + the laptop-cron HOLD decision)
and #4-S2 FOMC×ZQ (CME data sourcing). Nothing committed to git (Ryan's call).

---

## 2026-06-18 12:38 ET — S0 real-ask substrate built + Hard-Rule invariants (43 tests green)

**Built the project's first implementation — the substrate every future edge is scored on
(dossier #1, the canonical first build).** Autonomous `/loop` run against the 5-item Next queue.

- **Lifted verbatim from `kalshi.1` @ `fd37ae2`** (byte-identical, all 16 files diff-checked,
  recorded in `../PROVENANCE.md`): `core/{canonical,io,manifest_schema,timeutil,schema}.py`,
  `collection/{normalize,capture_orderbooks}.py`, `validation/{v1_actuals,v3_market,_http}.py`,
  4 config YAMLs, 3 tests + ticker fixture. Mirroring kalshi.1's layout meant **zero import edits**.
  - `normalize.py` derives the REAL taker ask `best_yes_ask = round(1 − best_no_bid, 4)` (Kalshi
    posts bids-only; the ask is the opposite side's complement). This is the price H1 trades on.
  - `capture_orderbooks.py` = forward, read-only, bitemporal depth capture Kalshi does NOT archive
    (the only moat that compounds with calendar time). Honest completeness: a dropped market lowers
    `n_markets < expected` so a truncated pass can't pass as complete (survivorship guard).
  - `v1_actuals.py` = 3-source settlement gate (CLI vs METAR vs GHCN) — the corrupted-actuals catch.
- **Authored fresh for THIS project's rules** (kalshi.1 has no equivalent — its invariants are
  arb-bot-v2's, scoped to a different layout):
  - `scripts/invariants.py` — the **6 Hard Rules** as static (regex) + DB (sqlite) assertions, plus
    `--pre-edit-hook` mode. Structure adapted from `arb-bot-v2/scripts/v3_invariants.py`, retargeted.
    DB invariants are **schema-discovering** (the project's DB schema isn't frozen) — they introspect
    tables, so Rule #4 (no pnl without a `price_source_tag`) fires on whatever backtest table appears.
  - `core/source_tag.py` — the trust=FALSE default in code: **untagged number ⇒ `synthetic`**; only
    `real_ask`/`broker_truth` are `is_fillable`; `require_fillable()` blocks synthetic/midpoint from
    any fill/P&L decision (prime directive #1).
  - `core/pricing.py` — THE sanctioned `yes_ask/bracket_sum` site (Hard Rule #3); `overround()` makes
    the ~5¢ pt1 killer a first-class, persisted number.
  - `core/stats.py` — `safe_pstdev` with the n≥4 guard (Hard Rule #2).
- **Verified:** `pytest -q` → **43 passed**; `invariants.py --full` → **all green**. The dossier's #1
  binding assertion is now a test: `best_yes_ask == round(1 − best_no_bid, 4)`, ask stamped `real_ask`.
- **Not wired (left for approval):** the PreToolUse hook (would block edits = harness change); live
  capture/actuals paths (need Kalshi creds + network — only offline/injected paths are tested).

**Next (this loop):** `scripts/emos_demo.py` repro (#5) → Open-Meteo collector script (#3) →
longshot-fade offline calibration on the recovered tape (#4-S1). **GATED on Ryan:** cron the forward
capture (#2 — needs creds + conflicts with the kalshi.1 laptop-cron HOLD) and FOMC×ZQ (#4-S2 — needs
CME data sourcing).

---

## 2026-06-18 01:10 ET — Codebase mine landed; KB foundations built

**Workflow result (27 agents, 22 candidates, all adversarially verified at real asks):**
- Verdict tally: **0 proven edges · 4 dead · 6 infra-only · 12 needs-data.**
- Honest bottom line: **no clean dollar edge is proven at real fillable asks anywhere.** The
  only real-money test (KXHIGH weather ensemble, n=49) lost −$0.14/trade; pt1 −9.6%, killed by
  ~3–5¢ bracket overround. Directional signal is real; dollar edge is not.
- Cheapest path forward: build the **real-ask substrate** (S0: tape capture + 3-source actuals
  gate + bid-only ask primitive + invariant engine), start **archiving forward orderbook tape**
  (un-backfillable; the only moat that compounds), and run two near-free probes — **longshot-fade
  calibration (S1)** and **FOMC×ZQ basis (S2)**. Zero weather-model capital until a real-ask CI clears zero.
- Full dossier → `../findings/2026-06-18-codebase-money-map.md`. Candidates registered → `strategies/00-index.md`.

**KB built this session:**
- `kalshi-api/`: overview, **auth & signing** (RSA-PSS/SHA-256, verified), REST+WebSocket map,
  **fees & breakeven** (`reproduced` via `scripts/fee_breakeven.py` — 2¢/contract at 0.50 → need +2¢ edge).
- Runnable repros: `scripts/kalshi_sign.py` (local signature verifies OK), `scripts/fee_breakeven.py` (ran).
- `quant-finance/`: 7-theme overview + deep weather-alpha note; citations triaged (caught a
  fabricated arXiv id + several wrong venues — see `_sources/quant-finance-sources.md`).
- `glossary.md`, both `_sources/` provenance files.

**Dead-end ledger (do not re-mine):** raw KXHIGH ensemble as deployed, Kelly-modifier tilt, LIP
rebate harvest, settle-time T-3h pin, K1' "hedge" framing, NWS/WU settle-source basis. (Details in dossier.)

**Next:**
1. Build S0 substrate (lift kalshi.1 `normalize.py`/`v1_actuals.py`/`capture_orderbooks.py` + invariants).
2. Cron forward Kalshi orderbook capture at a pinned decision time TODAY.
3. Start an Open-Meteo forecast collector (zero forecast tape exists anywhere — most-reused missing input).
4. Run S1 (longshot-fade) and S2 (FOMC×ZQ one-meeting) — near-free, no capital, decide weather's fate.
5. Reproduce: write `scripts/emos_demo.py` so the weather-alpha note can claim `reproduced`.

---

## 2026-06-18 00:35 ET — KB seeded; codebase-mining workflow launched

- Created `kalshi.headless` as the canonical Tier-2 Kalshi project. Inherited the
  prime directive, trust=FALSE defaults, and 6 hard rules from `arb-bot` (see
  `../CLAUDE.md`).
- Stood up this KB with the Karpathy-method charter (`README.md`): first
  principles, runnable repros, append-only log, cold-reader legibility.
- Kicked off a dynamic workflow to mine the four existing Kalshi codebases
  (`arb-bot`, `arb-bot-v2`, `kalshi.1`, `kalshi.ibkr`) for money-making
  opportunities and adversarially verify each against the "real fillable asks"
  bar. Output lands in `../findings/`.
- Began two foundational KB tracks in parallel:
  - `kalshi-api/` — how Kalshi actually works (auth, market structure, fees,
    rate limits, data).
  - `quant-finance/` — peer-reviewed literature relevant to prediction-market
    edges (calibration, favorite-longshot bias, market microstructure, Kelly).

**Next:** integrate workflow findings into `strategies/` candidates; reproduce
the top-1 fee/pricing claim with a runnable script.
