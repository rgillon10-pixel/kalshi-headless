# Running Log — kalshi.headless KB

Append-only. Newest at top. Each entry: `## YYYY-MM-DD HH:MM ET — title`,
then what happened, what it means, and links to the note/script it produced.
Dead ends stay. This is the journey; `git` is the diff.

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
