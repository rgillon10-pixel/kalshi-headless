# LOOP-QUEUE — standing work queue for autonomous cloud runs

`protocol v1` · created 2026-07-02 · owner: Ryan Gillon

This file is the coordination bus for the cloud loop system:

- **kalshi-research-loop** (every 5 h, Sonnet 5): executes ONE milestone from the queue below.
- **kalshi-collector** (hourly, Haiku): runs `python -m collection.hourly_pass` if it exists;
  nothing else, ever.

**Standing approval.** For a cloud run, executing the topmost eligible queue item under this
protocol IS the approved plan — do not wait for interactive approval (CLAUDE.md's plan-first
rule is satisfied by this file). Everything else in CLAUDE.md binds unchanged, especially:
research + data collection ONLY, no execution code, the real-ask bar, source tags on every
persisted price, invariants green before commit.

## Run protocol (research loop)

0a. **History-integrity check (added 2026-07-10, after main was rewound to a 6-day-old
   checkpoint on 2026-07-08 and the loops unknowingly redid a week of work).** Before ANY
   other step: `gh pr list --state merged --limit 5 --json number,mergeCommit`, then for
   each `git merge-base --is-ancestor <mergeCommit.oid> origin/main`. Also verify the
   newest `kb/00-LOG.md` entry date on `origin/main` is not older than the newest
   `tape/*/dt=*` file date by more than 2 days. If EITHER check fails, `main` has been
   rewound or rewritten: do NOT pick queue work, do NOT push anything on top of the rewound
   base. Instead: post a `Priority: max` ntfy note ("main history rewound — needs Ryan"),
   open a GitHub issue titled `main rewound — <date>` with the evidence (which merged PR is
   unreachable, current main SHA), and END THE RUN. Recovery is Ryan-supervised, never
   automatic — see kb/00-LOG.md 2026-07-10 reconciliation entry for the one prior repair.

0. **Claim check (do this before picking work — prevents duplicate runs).** A cloud session
   cannot push straight to `main` (confirmed empirically 2026-07-03: two consecutive runs
   each rebased cleanly, `git push origin main` still fell back to the session's own branch
   with zero rebase conflicts — this is a permission boundary, not a race). So "state of
   `main`" and "state of the queue" can lag behind in-flight work sitting in open PRs.
   `git fetch origin main` and list open PRs targeting `main` in this repo. For each open
   PR: if its title/body names a queue item that is still TODO/IN-PROGRESS here, that item is
   **claimed** — do not redo it. If the PR is green (checks pass) and unmodified for a while,
   merge it yourself (squash) before doing anything else, so `main` catches up; if it's stale
   or broken, note that in the digest and pick the next eligible item instead.
0b. **Stranded-tape sweep (added 2026-07-04, after 10 collector passes silently stranded).**
   The hourly collector's push to `main` fails intermittently and falls back to a
   `tape/hourly-*` branch; that tape never reaches `main` on its own. As part of every
   research run: `git ls-remote --heads origin 'refs/heads/tape/hourly-*'`; for each such
   branch, union-append any JSONL lines missing from `main`'s per-day tape files into your
   run's own commit (line-level dedupe is safe — tape is append-only JSONL with unique
   capture identity per line; never rewrite or reorder existing lines), then, only after
   your PR containing those lines has merged, delete the swept branch. Skip any branch
   whose commit is younger than 30 minutes (may still be mid-run).

1. Read `CLAUDE.md`, this file, `kb/strategies/00-index.md` — from `main` HEAD, post claim-check.
2. Env: `pip install -e ".[dev,analysis]"` (venv optional in a throwaway sandbox).
3. Pick the TOPMOST unclaimed item whose status is TODO or IN-PROGRESS (skip DONE / BLOCKED /
   DEAD / claimed-by-an-open-PR). Do ONE milestone (~one focused stage). If the item blocks
   mid-run, set its status to `BLOCKED(<reason>)` and move to the next eligible item.
4. Gates before ANY commit: `pytest` green AND `python scripts/invariants.py --full` green.
5. Bookkeeping: update the item's Status line in this file; append one dated entry to
   `kb/00-LOG.md` (match its existing format); findings → `findings/`; strategy status
   changes → `kb/strategies/00-index.md`; append one line to "Log of runs" below.
6. Git: commit (message conventions from history: `build:` / `probe(Sx):` / `tape:` /
   `docs:`) on your own branch, push it, then open a PR against `main` (`gh`/GitHub MCP —
   do NOT attempt `git push origin main`, it will not succeed from a cloud session). If gates
   (step 4) are green and the diff is research/data-only — no order/execution code, no
   credential handling (Stop rules already forbid both, so this is a re-check, not a new
   bar) — **merge the PR immediately** (squash) so `main` is current for the next firing. If
   gates are red or the milestone is only partially done, leave the PR open with an
   IN-PROGRESS note in its body and say so in the digest; do not merge broken or incomplete
   work into `main`.
7. Final message must be EXACTLY this shape — it is Ryan's phone digest:

   ```
   RUN DIGEST
   - Done: <one line>
   - Found: <key numbers; any price carries its price_source_tag>
   - Next: <one line>
   - Repo: <short sha> → <branch> (PR #<n>, merged|open)
   ```

8. Phone note (all legs — research loop, cloud collector, VPS collector, weekly retro; added
   2026-07-03). Best-effort, never blocks a run: POST one plain-English summary a
   non-programmer understands (no jargon, SHAs, or ticker codes) to the ntfy URL in
   `config/notify.topic` via `curl -s -m 10 -H 'Title: <leg name>' -d '<text>'`. Hourly
   collector notes use `-H 'Priority: low'` (silent feed); anything failed or needing Ryan's
   action uses `-H 'Priority: high'`. Ryan reads this feed on his phone via the ntfy app —
   it is the human window into the loop; write for him, not for the log.
   **Hardening (2026-07-10, after the feed went silent for 2 days without anyone noticing):**
   (a) the note is mandatory on EVERY research-loop run, including idle/maintenance runs and
   runs that end early on a guard (step 0a) or a blocked queue — silence is never a valid
   outcome; (b) any run that fails its gates, loses its push, or hits step 0a posts at
   `Priority: high` or above; (c) if the ntfy POST itself fails, say so in the run digest so
   the retro can see the notification pipe is broken; (d) the weekly retro's review MUST
   include "did phone notes flow every day this week?" as a checklist item.

## Stop rules (non-negotiable)

- NEVER write order/execution code, never touch credentials, never place a trade. Capital
  requires an in-person sign-off from Ryan that no cloud run can obtain — by design.
- An edge is "proven" ONLY by a block-bootstrapped 95% CI strictly > 0 at `real_ask` prices
  net of fees. A DEAD verdict is a success — record it honestly and move on.
- Never relax an invariant, never delete or reorder queue items; append, don't rewrite.
- Timebox: if a milestone isn't converging, commit honest partial state with an
  IN-PROGRESS note rather than forcing a result.

## Subagent roster (added 2026-07-06, ops — Ryan-requested)

`.claude/agents/` now defines a project agent team: a **Fable lead on high reasoning**
(`research-lead` — plans, decomposes, reviews; never edits files itself) guiding five
**Opus workers** — `collector-engineer` (build collectors + tests), `edge-prober` (probes/
backtests/bootstraps, one falsifiable milestone each), `verifier` (adversarial skeptic:
re-runs and attacks every number before it enters kb/ or findings/), `kb-distiller`
(compounds lessons into `kb/lessons/00-lessons.md` and escalates UNENFORCED lessons into
invariants/tests), and `tape-auditor` (read-only tape health/coverage/stranded-branch
reports). Each agent's charter carries the Stop rules and the real-ask bar; none can place
orders or touch credentials by charter, and the repo Stop rules bind regardless.

Loop usage: a research run MAY delegate its milestone through `research-lead` (which fans
out to the workers) instead of doing everything in the main context — the run protocol
above (claim-check, step-0b sweep, gates, bookkeeping, digest) binds identically either
way. Two standing quality rules regardless of who executes: (1) any number destined for
`kb/` or `findings/` passes the `verifier` bar — re-runnable, provenance-tagged,
statistically honest; (2) every run that learned something ends with a `kb-distiller`-style
ledger append, so knowledge compounds instead of evaporating between stateless runs. The
lessons ledger lives at `kb/lessons/00-lessons.md`; its UNENFORCED rows are a standing
work queue any idle run may draw from (converting a lesson into an invariant/test is
always an eligible milestone, no queue item needed).

## Queue (topmost eligible item wins)

### Q0 — Cloud environment check
Status: DONE (2026-07-02) — initial check found all 4 hosts BLOCKED by org egress policy;
superseded by Q0b (2026-07-03), which found egress reopened. See `tape/cloud-env-check.md`.
Verify from the cloud sandbox and record results in `tape/cloud-env-check.md`:
(a) Kalshi public REST via `python -m collection.capture_orderbooks --limit 3`;
(b) public crypto spot (Coinbase `GET https://api.exchange.coinbase.com/products/BTC-USD/ticker`
and/or Kraken equivalent);
(c) whether `ODDS_API_KEY` exists in env (do NOT print it) and the-odds-api reachability.
Any blocked host → mark the dependent queue items `BLOCKED(<host>)`.

### Q0b — Egress re-verify (self-healing; stays TODO until it succeeds)
Status: DONE (2026-07-03) — all 4 hosts now reachable (Kalshi 200, Coinbase 200, Kraken 200,
the-odds-api 401=reachable-no-key); `capture_orderbooks.py --limit 3` proved live end-to-end.
`ODDS_API_KEY` still absent. See `tape/cloud-env-check.md` "Re-verify (Q0b)" section.
**Note (2026-07-10 reconciliation):** the post-reset lineage independently re-verified the same unblock on 2026-07-09 (main had been rewound to the 07-02 checkpoint on 07-08; see kb/00-LOG.md reconciliation entry).
Cheap check, run FIRST while any item is `BLOCKED(egress...)`: re-test the four Q0 hosts
(`curl --max-time 15` each; do not retry a 403 beyond once per host). If ALL still blocked:
leave every status untouched, append one log line, and END THE RUN immediately with digest
`Done: egress still blocked; awaiting environment network change` — do not burn the session
on anything else. If hosts are NOW reachable: set this item DONE, flip every
`BLOCKED(egress ...)` status back to TODO, refresh `tape/cloud-env-check.md`, log the
unblock, then proceed to the topmost TODO item as normal.

### Q1 — Build sports paired-odds collector (serves S7/S11) — TIME-SENSITIVE: World Cup ends Jul 19
Status: KALSHI LEG DONE (2026-07-03) — `collection/sports_pairs.py` built + 19 unit tests green;
two independent live passes both captured (357 events/2026-07-02 pass, 188 games/2026-07-03
pass — market set shifts between passes, both kept as tape), all `completeness_ok`, mean
overround +21.3¢ real_ask. Odds-api leg still BLOCKED(key) (`ODDS_API_KEY` absent) —
`devig_multiplicative` implemented+tested, event-matching not built.
Remaining for full DONE: wire into Q3's hourly pass once Q2 exists; get an odds-api key.
**Note (ops, 2026-07-03):** a second hourly collector now runs on Ryan's Hetzner VPS (cron
:23 UTC, commits `tape: hourly pass <ts> (vps)`). The odds-api key will live in the VPS env
(`/root/.secrets/kalshi-headless.env`, root-only, never in this repo) — the moment Ryan pastes
it there, VPS passes start capturing the odds leg automatically. Cloud runs: do NOT attempt to
obtain or store the key; treat odds-leg tape appearing in `tape/sports_pairs/` as the unblock
signal.
**Note (reconciliation, 2026-07-03):** this milestone was independently built twice this run
window — two loop firings each rebuilt Q1 from scratch because neither could push straight to
`main` (see protocol step 0/6 above, fixed after this). Kept the more defensively-built
implementation (structural title-regex confirmation of each game group, not ticker-suffix
alone) and folded in the other run's tape capture as extra data. No further duplicate work
should occur now that the claim-check + PR-merge protocol is in place.
**Note (2026-07-10 reconciliation):** the post-reset lineage rebuilt this collector from scratch on 2026-07-09 (`core/sports_schema.py` + `core/odds.py` variant); the pre-reset implementation was kept at merge time (5 more days of hardening, hourly_pass integration). `core/odds.py` and its tests were retained — the S7a re-probe scripts import them.
`collection/sports_pairs.py`, mirroring `collection/capture_orderbooks.py` discipline
(bitemporal `fetch_ts`, raw-bytes sha256, honest expected-vs-captured completeness). One pass =
for every open Kalshi sports moneyline market (soccer/World Cup first, then anything listed):
snapshot yes/no BBO (tag `real_ask`) → JSONL under `tape/sports_pairs/`. If `ODDS_API_KEY` is
present, also fetch matched sportsbook odds (Pinnacle preferred), store raw + de-vigged fair
prob per outcome (tag `synthetic` — a de-vig is a model, not a fill). No key → capture the
Kalshi leg anyway and note the odds leg as BLOCKED(key). Unit tests for ticker parsing and
de-vig math.

### Q2 — Build crypto-hourly settlement collector (serves S8/S10)
Status: DONE (2026-07-03) — `collection/crypto_hourly.py` built + 21 unit tests green; one
live pass captured both BTC and ETH `pass_complete` (current-hour bracket book real_ask +
previous-hour broker_truth settlement + Coinbase synthetic spot) to
`tape/crypto_hourly/dt=2026-07-03.jsonl`. Stray long-lived same-grammar group
(`KXBTC-26JUL0317`, open since 06-26) correctly excluded from "current hour" via a duration
filter, not a ticker special-case. Notable: BTC bracket overround **+$9.27** (real_ask,
188-member ladder) — plausibly driven by ~180 fine $100 bands each near Kalshi's 1¢ min ask;
un-investigated, flagged for whoever runs Q5. See `kb/00-LOG.md` 2026-07-03 05:14 UTC entry.
`collection/crypto_hourly.py`: one pass = snapshot the CURRENT hour's BTC/ETH hourly bracket
books (tag `real_ask`) + spot from ≥1 public exchange endpoint (tag `synthetic`), AND fetch
settlement results for the PREVIOUS hour's markets → paired JSONL under `tape/crypto_hourly/`.
Store both spot and settle so the S8 ρ-guard (spot-vs-settle correlation) is computable from
tape alone.

### Q3 — Hourly entry point for the collector routine
Status: DONE (2026-07-03) — `collection/hourly_pass.py` built + 15 unit tests green; live pass
captured 193 sports games + 2 crypto symbols (680 underlying markets, 195 tape lines),
`completeness ok`. Wires the hourly Haiku routine's one command
(`python -m collection.hourly_pass`).
`collection/hourly_pass.py`: the single command the hourly Haiku routine runs — one
sports-pairs pass + one crypto-hourly pass; during the 09 UTC hour also run
`scripts/anomaly_sweep.py` if it exists. Prints the one-line summary the collector digest
needs (`<n> markets, <m> lines, completeness <ok/FAIL>`). Must be safe to run unattended
every hour; a partial failure lowers completeness, it never fakes success.

### Q4 — S7 historical backtest (sports CLV vs de-vigged sharp line) — the try-first edge
Status: DONE (2026-07-04) — **S7a DONE, S7b DONE, S7c DONE — verdict DEAD.** S7c re-fetched
Kalshi's full-to-date World Cup settled tape (87 events) + matching ESPN closing odds,
re-joined (77/87 matched, 0 ambiguous), combined with S7b's 3 NBA games (deduped) for
**80 unique games / 237 priced outcomes**. New `scripts/s7c_sports_clv_bootstrap.py`
block-bootstraps `edge_after_fee` by game, 10,000 resamples: mean **−0.0235**, 95% CI
**[−0.0245, −0.0225]** — strictly below zero, not just failing to clear it. **S7 (taker
side, Kalshi ask vs DraftKings-close de-vig) is DEAD** per the Stop rules' own bar — a
decided real-ask CI is a success, not a reason to keep collecting. See
`findings/2026-07-04-sports-clv-s7-verdict.md`; registry updated in
`kb/strategies/00-index.md`. Untested / out of scope for this verdict: the maker/bid side of
the same mispricing, and a sharper (Pinnacle) fair-price anchor should one become free.
S7a/S7b history below, unchanged.
Status: IN-PROGRESS (2026-07-03) — **S7a DONE, S7b DONE**. S7a built
`collection/sports_history.py` (Kalshi settled-event leg + free ESPN/DraftKings closing-odds
leg) + found Kalshi purges settled markets ~60 days after close (NFL 100% purged, NBA only
playoff tail, World Cup 2026 fully retained → now S7's primary dataset, time-boxed to Jul 19).
See `findings/2026-07-03-sports-history-s7a.md`. S7b added the join: `extract_kalshi_teams` +
`match_kalshi_espn` (team-name containment + ±1-day kickoff window, honest
matched/ambiguous/no_match/unparseable_title — never a silent pick) + `run_clv_join` (real
pregame ask via `candlestick_ask_before` anchored at ESPN's actual kickoff, de-vig DraftKings'
close via `sports_pairs.devig_multiplicative`, per-field `real_ask`/`synthetic` source tags).
37 new unit tests (155 total green), `invariants --full` green. Live pass (fresh ESPN pull for
the WC round-of-32/16 dates the Kalshi tape actually covers, Jun26-Jul02 — the prior S7a ESPN
pull's date window didn't overlap the Kalshi events at all): **27 games matched, 78 outcomes
priced**, mean pregame `bracket_sum` 1.020, mean `edge_after_fee` −0.0241 (real_ask vs
synthetic-devig, descriptive only — NOT a verdict, n far short of bootstrap-worthy). See
`findings/2026-07-03-sports-history-s7b.md` + `kb/strategies/00-index.md` S7 note.
Remaining: **S7c** — accumulate more games as the tournament progresses, block-bootstrap by
GAME (not by outcome — outcomes within a game aren't independent draws) → 95% CI, verdict,
`findings/<date>-sports-clv-s7.md`, update registry + this file.

### Q5 — S8 first cut from free candlesticks (crypto settlement basis)
Status: DONE (2026-07-04) — **verdict DEAD.** Egress reopened (confirmed live, including the
Coinbase `/candles` host that 403'd last run); `s8_basis_probe.py --historical-spot` fetched
the exact settlement-instant minute candle for all 36 accumulated settled hours (18/symbol),
fixing the 29-minute lag confound (lag now 0s, zero gaps). Corrected ρ: BTC 0.963→0.9997, ETH
0.947→0.9998 (weather-precedent kill territory); max settle-vs-spot gap never crosses half a
bracket width for either symbol (BTC $38.93 of $50; ETH $0.94 of $10 — also fixed a latent
bug where the half-band check used a fixed $100 width instead of ETH's actual $20 spacing).
BTC shows a small non-zero-centered basis (+$16.43 mean, plausibly real CF-Benchmarks-vs-spot
premium) but an order of magnitude below the bracket width. The ρ-guard's own cheap-kill
criterion triggers — no bootstrap needed, same mechanism as S5. `kb/strategies/00-index.md`
S8 flipped to `dead ✗`. See `findings/2026-07-04-crypto-basis-s8-verdict.md`. 2026-07-03
history (overround-composition first cut, the lag-confound diagnosis) unchanged, see
`findings/2026-07-03-crypto-basis-s8-q5.md`.

### Q6 — Daily anomaly sweep (serves S3 + free-money detection)
Status: DONE (2026-07-04) — `scripts/anomaly_sweep.py` built + 22 new unit tests (17 in
`tests/test_anomaly_sweep.py`, 5 new pricing tests in `tests/test_substrate_primitives.py`);
real-ask
fee-floor math (`fee_per_contract`, `true_arb_edge`, `monotonicity_crossing_edge`) added to
`core/pricing.py` (the sanctioned Hard-Rule-#3 site) alongside `bracket_sum`. Two checks,
both requiring a real fillable cost under $1 net of fees, not just an implied-probability
gap: (1) **bracket_arb** — a complete less+between+greater strike ladder under one
event_ticker whose yes_asks sum below $1+fees; only scored when the sorted segments
bookend the full real line with no gap past a 2-cent tolerance (the observed Kalshi tick
gap). (2) **cross_strike_monotonicity** (S3) — nested "greater"/"less" strikes where
buying YES(wider)+NO(narrower), both real asks, pays a guaranteed >=$1 for under $1+fees.
Discovery has NO series/category filter (literally every open market, per this item's own
wording) via `/markets?status=open` pagination. **Real-world surprise:** Kalshi's open-
market count runs into the tens of thousands (confirmed live: 10,000+ inside the first 10
pages alone, cursor still unexhausted; an unbounded pull grew this sandbox past 3GB RSS
before it was capped) — `main()` now defaults to `--limit 20000` and every tape record
carries an honest `markets_truncated` flag (never silently claims full coverage); `--limit
0` opts into an unbounded run for a beefier box (e.g. the VPS). Three live passes run
(300/3000/20000-market caps, all `completeness_ok`, 0 anomalies — expected, real arbs are
rare) plus a direct live probe of KXBTC's real 188-member ladder proving the pipeline fires
correctly on production data: bracket_sum 7.78 (matches Q2/Q5's already-documented "fine
$100-band, 1¢-min-ask" overround, correctly NOT flagged as an arb). No live multi-member
"greater"/"less" group was found in the small weather sample probed to exercise
`cross_strike_monotonicity` end-to-end on real data; that check is proven via realistic
unit-test fixtures instead and will fire automatically once the daily sweep tape
accumulates a case. Wired into Q3's 09 UTC slot automatically (no code change needed —
`hourly_pass.py` already ran `scripts/anomaly_sweep.py` as a subprocess whenever the file
exists). Gates: 169 tests green, `invariants --full` green.
**Note (2026-07-10 reconciliation):** unaware of this verdict (main rewound 07-08), the post-reset lineage independently re-ran S7a/S7b on 2026-07-09/10 with a DIFFERENT free odds source (football-data.co.uk closing average, 97 WC games / 167 candidate trades): mean net P&L −3.51¢/trade at real_ask after fees, monotonically worse under a min-edge sweep — an independent replication of the DEAD direction before its own bootstrap ran. Artifacts kept: `tape/sports_history_s7/`, `tape/sports_clv_s7/`, `scripts/sports_history_s7a.py`, `scripts/sports_clv_s7.py`, `findings/2026-07-10-sports-history-s7a.md`, `findings/2026-07-10-sports-clv-s7b.md`. S7 remains DEAD; do NOT run S7c again.

### Q7 — S10 reachability-decay probe from accumulated crypto tape
Status: BLOCKED(needs ≥7 days of Q2 tape)
T−5/T−2 far-bracket ask vs remaining-time reachability; must clear the artifact noise floor
+ the chunky longshot fee.

### Q8 — Build Kalshi↔Polymarket World Cup round-market collector (serves S9) — new, 2026-07-04
Status: DONE (2026-07-06) — **resolution decision: S9 lead-lag flips dead ✗ (data-adequacy),
not a CI falsification.** Checked this loop's actual scheduling tools (`create_trigger`,
`send_later`) before deciding: recurring cron triggers are hard-capped at hourly minimum
interval (ruling out a sub-hourly recurring poll); one-shot triggers aren't cadence-limited
but need a per-match kickoff timestamp the tape doesn't carry for KXWCROUND, and wiring up
N one-shot bursts per remaining match is a new class of unattended multi-day automation —
the same category as the VPS collector / `ntfy-watch`, both Ryan-requested ops changes, not
something a research-loop run should decide alone. So: lead-lag (does one venue reprice
first around a shock?) is dead by data-adequacy, per the prior run's own n=8 shock-study
evidence (both venues repriced together every time, mean gap 2.2¢, no leader). The
cross-venue parity sub-question (do the two venues quote the same price on average?) is a
different, already-answered-well question that survives under S17's Fed-decision
generalization (no sub-hourly resolution needed there). No new code — decision on already-
collected evidence. See `findings/2026-07-06-polymarket-leadlag-s9-resolution.md`;
`kb/strategies/00-index.md` S9 flipped to dead ✗. History below (Q8's build + prior cuts),
unchanged.
Status: IN-PROGRESS (2026-07-06) — **first real shock event-study** (this run): two real
round transitions landed since the last cut (Brazil and Mexico both eliminated,
quarterfinal losses). New `scripts/s9_shock_eventstudy.py` isolates real transitions from
`market_membership_changes()` (excluding the documented startup artifact) and reports each
affected ticker's last two captured rows (the actual repricing step) on both venues. Result,
n=8 ticker-steps across the 2 events: Kalshi and Polymarket moved together every time — mean
`|Δkalshi − Δpolymarket|` 2.2¢, max 8¢, no consistent one-venue-leads pattern, both venues
already reflecting the outcome by the very next capture (30–60min later). **Finding is
methodological, not a null result on the thesis:** collection cadence is coarser than the
event itself (a match resolves within minutes of the final whistle) — S9's lead-lag thesis
cannot be resolved at this cadence without sub-hourly captures bracketing scheduled game-end
times. 10 new unit tests (297 total, 287 prior + 10 new), `invariants --full` green. Remaining
for full DONE: a resolution decision before WC ends Jul 19 — either add a sub-hourly capture
burst for the remaining matches (semis/final) or accept this infra only answers cross-venue
parity, not lead-lag, and mark the lead-lag angle a data-adequacy DEAD. See
`findings/2026-07-06-polymarket-leadlag-s9-shock-eventstudy.md`.
Status: IN-PROGRESS (2026-07-05) — **first lead-lag cross-correlation cut run** (this run):
`scripts/s9_leadlag_probe.py` (read-only over `tape/polymarket_pairs/`, 37 captures/48
markets/40 with ≥10 captures) pooled consecutive-capture price changes into a lag-0/lag±1
cross-correlation (contemporaneous ρ +0.293 n=1,440; kalshi-leads-poly +0.044; poly-leads-
kalshi −0.007 n=1,400, both noise-level) — descriptive only, not a verdict. More important
finding: `market_membership_changes()` found **zero** in-window round-transition events (no
team has advanced/been eliminated since continuous hourly collection started 2026-07-05T00:11Z)
— S9's actual thesis (does one venue lag the other around a real information shock) is still
untested; every tick observed so far is book noise. 20 new unit tests (offline, synthetic
series). Remaining for full DONE: no more code needed — keep accumulating hourly snapshots
until an actual round transition lands in the tape, then re-run this script and inspect that
market's captures around the transition specifically. See
`findings/2026-07-05-polymarket-leadlag-s9-first-cut.md`.
Status: IN-PROGRESS (2026-07-05) — **wired into `hourly_pass.py`** (this run): the collector
now runs every hour alongside `sports_pairs`/`crypto_hourly` with the same fault-isolation +
honest-completeness discipline, 2 new tests (212 total), live smoke confirmed end-to-end
(40/40 matched). Only remaining gap: let repeated hourly snapshots accumulate, then run the
lead-lag cross-correlation once enough history exists (World Cup ends Jul 19).
Status: IN-PROGRESS (2026-07-04) — collector built + one live pass; needs repeated snapshots
before a lead-lag cross-correlation is possible.
**Why this item exists:** this run's claim-check found NO eligible TODO/IN-PROGRESS queue
item (Q1 claimed by open PR #4 awaiting `ODDS_API_KEY`; Q2/Q3/Q4/Q5/Q6 all DONE; Q7
BLOCKED on ≥7 days of Q2 tape, only 2 days elapsed). Per this file's own append-don't-
rewrite rule, started the next un-started registry candidate (S9) rather than idle the run.
`collection/polymarket_pairs.py` built: discovers Kalshi's `KXWCROUND` series ("Will
`<team>` qualify for FIFA World Cup `<round>`?") and Polymarket's structurally-identical
"World Cup: Nation To Reach `<round>`" events (via Polymarket's public `/public-search`,
keyword-narrowed then title-regex-confirmed — no hardcoded event IDs), matches by exact
(round, normalized team name), and pairs each Kalshi `real_ask` with Polymarket's live CLOB
best bid/ask (also `real_ask` — a real order book, not the `outcomePrices` last-trade
reference). 20 new unit tests (offline, monkeypatched HTTP + FakeClient). Live pass:
**48/48 Kalshi round markets matched**, completeness ok, mean `price_gap_yes_ask` +0.20¢
(range −3¢/+3¢) — one snapshot, descriptive only. **Remaining for full DONE:** wire into
Q3's hourly pass (World Cup ends Jul 19 — narrow window to accumulate repeated snapshots),
then a lead-lag cross-correlation once enough passes exist.

### Q9 — S13 maker-side fill-sim on the proven sports rich-ask — TIME-SENSITIVE: WC ends Jul 19
Status: DONE (2026-07-04) — **verdict DEAD (null result).** `scripts/s13_maker_fillsim.py`
built + 22 unit tests; live pass over n=80 games/223 filled outcomes (94.1% fill rate):
`edge_after_fee` conditional on fill = +0.00009, 95% block-bootstrap-by-game CI
[−0.00021, +0.00039] — straddles zero. Mechanism: Kalshi's maker fee (0.0175) is itself
~1¢/contract across most of this dataset's bid-price range, consuming essentially the whole
assumed 1¢ bid-under-fair margin regardless of adverse selection (separately measured via
DK open-vs-close line move: a favorable but tiny +0.00168, nowhere near enough to rescue the
edge). Two bugs caught before the verdict: a first draft used the taker fee rate (0.07)
instead of maker (0.0175), overcharging every fill 4×; a first cache design stored full raw
candlesticks and hit 98MB for 237 tickers (some WC moneyline markets open 4+ months before
kickoff) — fixed by caching only the window's min trade price + timestamp (93KB after the
fix). `kb/strategies/00-index.md` S13 flipped to `dead ✗`. See
`findings/2026-07-04-sports-maker-s13-verdict.md`. 210 tests green, `invariants --full` green.
Original spec below, unchanged.
Status: TODO (added 2026-07-04, from `findings/2026-07-04-edge-candidates-s12-s18.md`)
S7c proved Kalshi pregame asks run +2.35¢ rich vs DraftKings-devig fair (95% CI ±0.10¢,
n=80 games) — the taker side is DEAD, the bid side is explicitly untested. Build a read-only
fill-sim over the existing `tape/sports_history/` + `tape/sports_pairs/` data plus Kalshi
candlesticks: simulate resting a bid at devig-fair − 1¢ from capture time to kickoff; a fill
= the candlestick low trading through the bid level; measure fill rate AND `edge_after_fee`
*conditional on being filled* (adverse selection: compare fair-at-fill vs fair-at-entry,
never assume the entry edge survives the fill). Block-bootstrap by game, 95% CI. All Kalshi
prices `real_ask`, devig `synthetic`, per S7b conventions. Output
`findings/<date>-sports-maker-s13.md` + registry update. No order code — paper fill-sim only.

### Q10 — S12 econ-print collector (CPI/payrolls/GDP ladders + nowcast leg) — TIME-SENSITIVE: 60-day purge
Status: DONE (2026-07-05) — **nowcast leg built.** `collection/econ_prints.py`'s
`fetch_nowcast_gdp`/`parse_gdpnow_nowcast` scrape the Atlanta Fed GDPNow page's embedded
`forecastDates`/`forecastQuarters`/`gdpForecast` JS arrays (confirmed live: quarter-blocks
newest-first, each block date-ascending — current nowcast = last entry of the first block).
Never fabricates: missing/mismatched arrays or a null latest value are an honest
`parse_error`, a real network failure a `fetch_error`. Live check: GDPNow read **+1.19%**
annualized for the quarter ending 2026-06-30 (as of its 2026-07-01 update, 27 updates so
far), tagged `synthetic`. Cleveland Fed's CPI-nowcast leg stays `not_built` — genuinely
un-scrapable (client-side rendered, no static data), unrelated to the GDPNow gap this run
closed. 7 new unit tests (245 total), `invariants --full` green. Remaining: accumulate ≥20
releases before S12's block-bootstrap gate is attemptable (months of real time, not loop
cycles) — no more code needed, this item is otherwise complete.
Status: KALSHI LEG DONE (2026-07-05) — `collection/econ_prints.py` built + 12 unit tests green;
discovers 5 confirmed-live flagship series (`KXCPI`/`KXCPIYOY`/`KXCPICORE`/`KXPAYROLLS`/`KXGDP`,
each a nested-monotonic "exceed threshold T" ladder per release, NOT a complete partition like
`crypto_hourly`'s brackets — `core.pricing.bracket_sum` deliberately not applied here, see the
module docstring). One pass = every open event's full per-strike real_ask ladder + the single
most-recently-settled event's Kalshi-reported result/`expiration_value` (`broker_truth`). Live
pass: all 5 series `pass_complete` (24 open events / 296 strikes, settlement resolved for all
5 — e.g. CPI MoM print "0.5", payrolls "57,000"). Wired into `hourly_pass.py`'s existing 09 UTC
slot (daily cadence, as this item's own spec asked for). Odds-api-style remaining gap: the
**nowcast leg is BLOCKED(nowcast-scrape)** — Cleveland Fed's CPI nowcast page has no static or
discoverable-API number in its served HTML (client-side rendered); Atlanta Fed's GDPNow page
DOES embed its full history as raw JS arrays but reliably slicing the current quarter's window
is nontrivial, left for a follow-up pass. Every record's `nowcast` field is honestly
`{"status": "not_built"}`. `kb/strategies/00-index.md` S12 flipped idea → data-collecting.
Remaining for full DONE: build the nowcast leg (GDPNow first — it's actually scrapable, unlike
Cleveland Fed), then accumulate ≥20 releases before S12's block-bootstrap gate is even
attemptable (CPI/payrolls are monthly, GDP quarterly — this will take months of real time, not
loop cycles; each daily pass is still worth taking now per the purge risk).
Original spec (unchanged): mirroring `crypto_hourly.py` discipline: discover Kalshi's CPI /
payrolls / GDP bracket series, snapshot full real-ask ladders, pair with the Cleveland Fed
inflation nowcast (public, free — tag `synthetic`; GDPNow for the GDP leg) and, post-release,
the Kalshi settlement result (`broker_truth`). Wire into `hourly_pass.py` at a cheap cadence
(one pass per day is enough except release mornings). Kalshi purges settled markets ~60 days
after close (S7a finding) — every un-collected release is data lost forever; the S12 gate
needs ≥20 releases, so collection must start now. Unit tests offline per house style.

### Q11 — S15 cross-event implication-pair scanner (extends Q6's sweep)
Status: DONE (2026-07-05) — `scripts/anomaly_sweep.py`'s third check
(`check_cross_event_implication`) + `config/implication_pairs.yaml`, the hand-curated
implication graph (one audited family so far: `kxwcround_progression` — reaching a later
World Cup round strictly implies reaching every earlier round for the same team, audited
against the same title text `collection/polymarket_pairs.py` already confirmed structurally;
the queue item's own second example, "wins presidency ⇒ wins nomination", has no matching
live Kalshi series yet and is left as a documented TODO rather than guessed at). Reuses
`core.pricing.monotonicity_crossing_edge` (same fee-floor math as Q6's check 2) — a hit is
YES(B)_ask + NO(A)_ask ≤ $1 − both fees, A = harder/narrower round, B = easier/wider round.
Runs automatically in `anomaly_sweep.py`'s existing 09 UTC slot (no `hourly_pass.py` change
needed, same as Q6). 12 new unit tests (10 for the check + config loader, 2 wiring into
`run()`); live-validated directly against Kalshi's real 40 open KXWCROUND markets: 38
generated round pairs, 0 hits (expected — matches Q6's/Q8's own "real arbs are rare" precedent,
and directly confirms correct monotonic pricing, e.g. SEMI priced 19¢ under QUAR's 52¢ for
Team USA). Kill condition (registry): 0 fee-clearing hits in 60 days of daily sweeps — dated
from this run. Original spec below, unchanged.
Status: TODO (added 2026-07-04)
Extend `scripts/anomaly_sweep.py` with a third check: a hand-curated implication graph
(config file, each pair added ONLY after reading both markets' rules text — settlement-term
mismatch is the classic Theme-6 trap, document the audit per pair) of cross-event pairs
where A ⇒ B logically (e.g. "wins final" ⇒ "reaches final" across KXWCROUND rounds;
"wins presidency" ⇒ "wins nomination"). A hit = YES(B)_ask + NO(A)_ask ≤ $1 − both fees at
one snapshot with fillable size (`real_ask` only), i.e. a locked payoff — same fee-floor
math as `core/pricing.true_arb_edge`. Runs in the existing 09 UTC slot automatically. Kill
condition per registry: 0 fee-clearing hits in 60 days of sweeps.

### Q12 — S17 retarget Kalshi↔Polymarket matcher to recurring macro pairs
Status: DONE (2026-07-06, later run) — **CPI/inflation leg built**, closing the only
remaining-work gap the Fed-decision cut below deferred. `collection/polymarket_pairs.py`
gained a third discovery family, `run_cpi()`: pairs Kalshi's `KXCPI`/`KXCPIYOY`/`KXCPICORE`
cumulative "exceed threshold T" ladders (see `collection/econ_prints.py`) against
Polymarket's exact 0.1-point bucket partition for the same 3 US print series ("<Month>
Inflation US - Monthly/Annual", "Core CPI MoM - <Month> <Year>", confirmed live). This is
NOT a same-question `real_ask` pair like the two families below — `price_cpi_bucket_from_kalshi`
derives each Polymarket bucket's probability by differencing two adjacent Kalshi asks, so
every derived value is tagged `synthetic` per Hard Rule #3's spirit (the two inputs are
each a genuine `real_ask`, but subtracting them is a model, not a fill) — exactly the
transform the Fed-leg cut below deferred rather than fake. Written to its own tape family
(`tape/polymarket_cpi_pairs/`), wired into `hourly_pass.py`'s existing 09 UTC daily slot
(CPI prints release monthly, same cadence reasoning as Q10's econ_prints — no need for
hourly polling). 23 new unit tests (320 total), `invariants --full` green. Live pass: 17
open Kalshi CPI events discovered, 3 matched to currently-listed Polymarket events
(core-MoM/YoY/headline-MoM), 0 unmatched/ambiguous Polymarket events, 22/28 buckets
priced — the other 6 need Kalshi strikes further out than its ladder currently lists (an
honest, expected coverage gap, not a bug, and correctly counted against
`completeness_ok`); one bucket's derived probability came back negative
(`monotonicity_violation: true`, traced to a thin/stale Kalshi far-OTM strike observed live
this run) and was recorded as-is, never clipped. Remaining for S17 overall: accumulate
snapshots (both Fed and CPI legs now run automatically every needed cadence), then the
eventual lead-lag cross-correlation, same shape as S9.
Status: FED-DECISION LEG DONE (2026-07-06) — `collection/polymarket_pairs.py` gained
`run_fed_decision()`: a second discovery family matching Kalshi's `KXFEDDECISION` 5-bucket
meeting ladder ("Hike/Cut rates by 0/25/>25bps") to Polymarket's "Fed Decision in `<Month>`?"
events by (meeting month+year, bucket) — confirmed structurally via each side's own
title/question text, never the Kalshi ticker's bps suffix alone (it uses "26" as a stand-in
for ">25", a live-confirmed quirk). Wired into `hourly_pass.py` as a fourth cross-venue
sub-pass (own tape family, `tape/polymarket_macro_pairs/`, so it doesn't mix with the
structurally different WC-round records). Live pass: 15/15 currently-listed Polymarket
Fed-decision markets matched (Jul/Sep/Oct 2026 — the only meetings Polymarket has created
so far), 0 ambiguous, 0 book errors, `completeness_ok`; Kalshi's much longer forward
calendar (meetings out to Jan 2028) is recorded as `unmatched_kalshi` but deliberately does
NOT gate completeness (see module docstring — grading against Kalshi's full calendar would
make this leg report FAIL forever, a structural non-issue, not a real one). 22 new unit
tests (287 total), `invariants --full` green. S17 flipped idea → data-collecting; its own
gate (≥5 matched live-book pairs/month) already cleared by this one pass.
**Remaining for full DONE:** the CPI/inflation leg is explicitly deferred — Kalshi prices a
cumulative "≥ threshold" ladder while Polymarket prices an exact bucket, so pairing them
needs a derived/synthetic transform (differencing adjacent Kalshi thresholds), not a
same-question `real_ask` pair; faking that pairing would violate Hard Rule #3's spirit, so
it's left for a follow-up rather than done here. Also: accumulate hourly snapshots, then
run a lead-lag cross-correlation once enough history exists, same shape as S9/Q8.
Original spec below, unchanged.
Status: TODO (added 2026-07-04; do after Q8's hourly wiring so both share the pass)
`collection/polymarket_pairs.py` currently only discovers World Cup round markets, which die
Jul 19. Add a second discovery family: Fed-decision and CPI/inflation questions listed on
both venues, same exact-question matching discipline (structural title confirmation, honest
unmatched/ambiguous accounting, Polymarket CLOB book = `real_ask`, never `outcomePrices`).
Wire alongside the WC pairs in `hourly_pass.py` so cross-venue collection outlives the
tournament. S17's gate needs ≥5 matched live-book pairs/month — if Polymarket's macro books
are too thin to quote a real ask, record that honestly; it is S17's kill condition, not a
collection failure.

### Q13 — S14 ladder-underwriting fill-sim from accumulated hourly tape
Status: BLOCKED(needs ≥10 days of Q3 hourly tape; eligible ~2026-07-13)
Read-only fill-sim of S14 (sell the complete bracket ladder as maker, collect the measured
+10–21¢ overround): from `tape/sports_pairs/` + `tape/crypto_hourly/` snapshots plus
candlestick volume, estimate P(complete fill of all-strike short-YES quotes at BBO asks
within horizon H) and the mark-to-real-ask loss on partial sets. Gate per registry:
E[overround × P(complete)] − E[loss | partial] > 0, 95% CI over ≥30 event-days. The
adverse-selection question (winning strike fills eagerly, wings never do) IS the test —
report it either way.

### Q14 — S16 FedWatch-anchored shock fade on KXFED (new, 2026-07-06)
Status: BLOCKED(fedwatch-scrape) — data-adequacy, not effort. This run tried to fetch CME's
FedWatch tool (the free ZQ-implied Fed-meeting-probability anchor S16 needs) from `cmegroup.com`
via `www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html` plus three guessed
widget/API paths (`/CmeWS/exp/fedwatch/index.html`, `/services/fedwatch`,
`/CmeWS/mvc/Volume/V1/Fedwatch`). Every one returned HTTP 403 with a realistic browser
User-Agent over HTTP/1.1 (HTTP/2 resets the stream outright) — Akamai-class bot protection,
the same shape that blocked Cleveland Fed's CPI nowcast page (Q10) and RealClearPolling below;
Kalshi itself and the Atlanta Fed's GDPNow page (both confirmed reachable this run and in Q10)
prove this session's egress is fine in general, so this is venue-side, not sandbox policy. No
free static/API alternative found. See `findings/2026-07-06-s16-s18-feasibility-blocked.md`.
Leave BLOCKED; revisit only if a free FedWatch data source surfaces (a headless-browser scrape
of a bot-walled page is not a sound basis for an unattended hourly collector).

### Q15 — S18 single-poll overreaction fade on Congress-control markets (new, 2026-07-06)
Status: BLOCKED(no-live-market) — data-adequacy, not effort. Kalshi's Congress-control series
(`HOUSE`/`SENATE`/`KXHOUSE`/`KXSENATE`, all confirmed to exist via `/series/<ticker>`) currently
list **zero markets in any status** (open/unopened/closed) — the 2026 midterm control contracts
have not been created yet, so there is nothing for a collector to snapshot and no Kalshi print to
join a poll against. Secondary blocker found even for the polling leg alone: the classic free
generic-congressional-ballot feeds are gone — `projects.fivethirtyeight.com`'s polls page and CSV
both 302-redirect to a dead `abcnews.com/politics` stub (site retired/migrated, not just moved),
`natesilver.net`'s Substack redirects away from any static data endpoint, and
`realclearpolling.com` 403s the same Akamai-class way as CME above. Wikipedia's "2026 United
States House of Representatives elections" article (confirmed reachable, HTTP 200, via
`en.wikipedia.org/w/api.php?action=parse`) cites a live generic-ballot polling section and stays
a viable free source for a future build, but pairing it against a Kalshi market that doesn't
exist yet would be tape nobody can use — unlike Q10/Q12's purge-risk urgency, a FUTURE market
carries no purge deadline, so there is no reason to build the stub early. See
`findings/2026-07-06-s16-s18-feasibility-blocked.md`. Revisit once Kalshi actually lists
`HOUSE`/`SENATE` markets for the 2026 cycle (watch via a cheap periodic `/markets?series_ticker=`
check, no need for a standing collector until then).

### Q16 — S6 forward L2 order-book depth collector (market-making order-arrival data) — new, 2026-07-07
Status: DONE (2026-07-07) — `collection/orderbook_depth.py` built + 13 new unit tests (361
total green); reuses `collection/normalize.py:normalize_snapshot` verbatim and the
`capture_orderbooks.py` fetch pattern, fed by the SAME tickers `sports_pairs`/`crypto_hourly`
already discover each pass (read back from their freshly-written tape by `capture_id`, no
platform re-sweep, per lesson L10). Every record tags asks `real_ask` / bids `real_bid` and
carries the full `yes_bids`/`no_bids` ladders + honest per-ticker completeness (a failed
fetch is a DROP, never absorbed). Wired into `hourly_pass.py` as a fifth fault-isolated
sub-pass. Live pass against real Kalshi data: 6/6 current-hour KXBTC tickers captured,
`completeness_ok=True`, sample reading `KXBTC-26JUL0621-T71799.99` depth=71,
`best_no_bid=0.99 → best_yes_ask=0.01` (correct `1−bid` complement) — one-sided wing books
confirmed to be genuine Kalshi shape, not a capture gap (a would-be false-drop bug caught and
tested before commit). `invariants --full` green. **Honest limitation recorded in the
module's own docstring:** hourly cadence (this loop's recurring-cron floor, per S9's own
finding) gives S6 a repeated depth *snapshot* series, not a continuous order-flow tape —
any arrival-intensity estimate built on it must be labeled snapshot-sampled, not
message-level. `kb/strategies/00-index.md` S6 flipped idea → data-collecting. See
`kb/lessons/00-lessons.md` L21-L23 for the reusable wiring pattern, the `real_bid`
source-tag-enum gap (flagged UNENFORCED for the kb-distiller), and the one-sided-book lesson.
Original spec below, unchanged.
Status: TODO (added 2026-07-07) — with the queue drained to time-blocked items (Q7 ~07-09/10,
Q13 ~07-13) and Q1 claimed by open PR #4, followed the registry's own priority order to the
next un-started, non-externally-blocked candidate: **S6** (inventory-aware market-making) is
the only remaining `idea`-stage candidate not blocked by external data (S4 needs an unrelated
repo's FEx archiver, S10=Q7 and S11 both already blocked). S6's own gate note says it "needs
the forward tape (S0) to even estimate order-arrival intensity" — no non-weather full L2 depth
collector exists yet; `collection/capture_orderbooks.py`'s fetch+normalize logic
(`collection/normalize.py:normalize_snapshot`, pure/reusable) is weather-scoped only via its
`discover_groups`. Build a new collector that captures full L2 depth (yes_bids/no_bids price+size
ladders, not just BBO) for the tickers `sports_pairs`/`crypto_hourly` already discover each pass
(reuse their discovery, don't re-sweep the platform — L10's 10,000+-market lesson) — tag every
book read `real_ask`/`real_bid` (a live order book is fillable). Honest expected-vs-captured
completeness per ticker, same discipline as every other collector. Wire into `hourly_pass.py`
as a new sub-pass. Unit tests offline. **Scope note:** this is the collector-build stage only
(mirrors Q1/Q2's own scope) — it does NOT attempt S6's actual fill-sim/arrival-intensity
estimation yet, and it should honestly flag that hourly cadence is coarse for arrival-rate
estimation (recurring cron is hard-capped at hourly per S9/Q8's own finding) — record that
limitation rather than oversell what hourly L2 snapshots can support.

## Retro amendments — proposed 2026-07-05 (open for Ryan's review, not yet adopted)

Drafted by the weekly retro run from this week's "Log of runs" below. These are **proposals
only** — nothing in this section is authoritative until Ryan reviews and merges the PR that
carries it. Nothing here relaxes an invariant or a Stop rule, deletes or reorders a queue
item, or touches source code.

1. **Step 0b clarification — reset local `main` before diffing stranded branches.** On
   2026-07-05T05:19Z the research run found its sandbox's local `main` ref was ~2 days stale,
   which made every `tape/hourly-*` branch look like it carried far more missing lines than it
   actually did (including in files the collector never touches) — caught before it produced
   a bad commit, but only because that run happened to check. Proposed addition to step 0b:
   run `git fetch origin main && git reset --hard origin/main` (or equivalent) immediately
   before diffing any `tape/hourly-*` branch against `main`, every run, not only when a diff
   looks suspicious.

2. **Step 0b — stop retrying the branch-delete that always fails.** Every research run since
   2026-07-03 (at least 5 runs, per the log below) has attempted `git push origin --delete` on
   fully-reconciled `tape/hourly-*` branches, and every single attempt has failed with the same
   documented cloud-session permission boundary. Proposed: stop attempting the delete each run
   — it costs a tool call and a log sentence for a guaranteed no-op — and just note
   reconciled-but-undeleted branches once per run instead. Separately, flagging for Ryan: if
   the stale branches should actually get cleaned up, the cloud GitHub App/token would need
   branch-delete scope added. That's a one-time permissions change only Ryan can make; no loop
   run can fix it from inside the sandbox.

3. **New — stuck-PR escalation after 5+ days with no owner action.** PR #4 (Q1's odds-api leg)
   has been open since 2026-07-03 waiting on Ryan to paste `ODDS_API_KEY` into the environment
   — at least 6 research runs now have silently re-noted "skipped Q1, unrelated" without ever
   escalating. Proposed: if an open PR has sat more than 5 days blocked purely on a Ryan-side
   action (a key, a decision, a merge) with no new activity, that run's ntfy phone note should
   use `Priority: high` (instead of the default) and name the specific blocking action once,
   so a stuck item doesn't stay silent indefinitely.

## Log of runs

(append one line per run: `<UTC ts> · <item> · <one-line outcome>`)

- 2026-07-02T22:43Z · Q0 · all 4 required hosts (Kalshi REST, Coinbase, Kraken, the-odds-api) BLOCKED by org egress policy (proxy CONNECT→403); Q1–Q6 marked BLOCKED(egress policy) pending Ryan widening the sandbox allowlist.
- 2026-07-03T00:08Z · Q0b · egress now open on all 4 hosts (Kalshi 200, Coinbase 200, Kraken 200, the-odds-api 401=reachable); `capture_orderbooks.py --limit 3` proved live. Q0b DONE, Q1/Q2/Q4/Q5/Q6 flipped BLOCKED(egress)→TODO; ODDS_API_KEY still absent (Q1 odds leg stays BLOCKED(key)). Proceeding to Q1 (time-sensitive, World Cup) per Q0b's own continue-instruction.
- 2026-07-03T00:14Z · Q1 · built `collection/sports_pairs.py` (discover→confirm→capture, real_ask BBO + bracket_sum/overround via core.pricing) + 19 unit tests; live pass captured 188 confirmed moneyline games (16 series incl. 10 World Cup) to `tape/sports_pairs/dt=2026-07-03.jsonl`, all complete, mean overround +21.3¢ real_ask. Odds-api leg stays BLOCKED(key); de-vig math implemented+tested but unused live.
- 2026-07-03T (reconciliation, out-of-band) · protocol fix + Q1 dedup · root cause found: cloud sessions cannot `git push origin main` (permission boundary, not a rebase race — both prior runs rebased clean, merge-base==main tip, yet both still fell back to their own branch). Two consecutive firings (`claude/brave-mccarthy-ek6ybp` 23:18Z, `claude/brave-mccarthy-7rnhry` 00:17Z) independently rebuilt Q1 from scratch as a result, each stranded on its own branch, no PR opened either time. Reconciled onto one branch: kept 7rnhry's collector (structural title-regex confirmation, not ticker-suffix alone), folded in ek6ybp's tape capture, merged to `main` via PR. Rewrote protocol steps 0/6: claim-check open PRs before picking work, push-branch+PR+auto-merge-if-green instead of push-to-main-with-branch-fallback — this is the actual fix, not just this run's cleanup.
- 2026-07-03T05:14Z · Q2 · claim-check: no open PRs, `main` in sync. Built `collection/crypto_hourly.py` (current-hour bracket book real_ask + previous-hour broker_truth settlement via pure hour-token arithmetic + Coinbase/Kraken-fallback synthetic spot) + 21 unit tests; live pass captured BTC+ETH both `pass_complete` to `tape/crypto_hourly/dt=2026-07-03.jsonl`. Excluded a stray long-lived same-grammar group via a close-open duration filter (would otherwise have silently mixed a week-old group into "current hour"). Notable: BTC bracket overround +$9.27 real_ask (188-member fine-band ladder) — flagged un-investigated for Q5, not a verdict. Q3 flipped BLOCKED→TODO (both its dependencies now built). Gates: 89 tests green, invariants green.
- 2026-07-03T10:12Z · Q3 · claim-check: no open PRs, `main` in sync at f6c946a. Built `collection/hourly_pass.py` — the hourly routine's single entry point: calls `sports_pairs.run()` + `crypto_hourly.run()` independently (one raising never kills the other), ANDs their own honest `completeness_ok` signals, sums `n_markets`/`n_lines` by reading back only the tape lines this pass just wrote (filtered by `capture_id`, so prior passes' lines in the same append-mode file aren't double-counted), and runs `scripts/anomaly_sweep.py` as a subprocess only during the 09 UTC hour (reports `not_built` honestly since Q6 doesn't exist yet — never silently skipped without a trace). 15 new unit tests (offline, injected stub sub-passes, no network): completeness AND-ing, fault isolation on either sub-pass raising, the 09-UTC-only anomaly slot (not-built/ok/error/raises), the tape-accounting helper, and CLI flag wiring. Live smoke: `--sports-limit 3 --crypto-symbols BTC` (188 markets, 1 line) then a full unlimited pass (193 sports games + 2 crypto symbols = 680 markets, 195 lines, completeness ok) — both appended to today's tape. Gates: 104 tests green (89 prior + 15 new), `invariants --full` green.
- 2026-07-03T15:25Z · ops (local, Ryan-approved) · VPS collector live: Hetzner box cleared of the dead weather apparatus (archiver services disabled, weather crons commented, 32G of weather-only tape/caches deleted after a sampled 123M-row audit found 100% KXHIGH/KXLOWT/UH* series — zero sports/crypto overlap with S7–S11), `kalshi-headless` cloned at `/root/kalshi-headless` with a write deploy key, hourly cron at :23 UTC (offset from cloud collector's :53), first live pass 645 markets / 178 lines / completeness ok pushed as 36c7f4e. Odds-api key slot prepared on the VPS (see Q1 note). Stale `tape/hourly-*` branches pruned (contents verified on main).
- 2026-07-03T15:30Z · Q4/S7a · claim-check: no open PRs, branch reset onto `main` tip (1abc535, ahead of stale local branch — two hourly `tape:` passes had landed since last research run). Built `collection/sports_history.py` (Kalshi settled-event leg + free ESPN/DraftKings closing-odds leg, no join yet) + 13 unit tests. Found Kalshi purges settled-market data ~60 days after close (NFL fully purged, NBA only playoff tail survives, World Cup fully retained — reshapes S7's dataset from "last-season NFL/NBA" to "World Cup + NBA tail"); also caught and fixed a pre-commit bug where `occurrence_datetime` was mistaken for kickoff (it's actually the resolution time) and would have silently priced "decision" asks from post-settlement candles. Live pass: 25 WC + 40 NBA + 15 NFL Kalshi records, 23 WC + 5 NBA ESPN odds records, 108 lines to `tape/sports_history/dt=2026-07-03.jsonl`. Gates: 117 tests green (104 prior + 13 new), `invariants --full` green. Full writeup: `findings/2026-07-03-sports-history-s7a.md`. Next: S7b (event-matching join + point the candlestick puller at real kickoff).
- 2026-07-03T15:32Z · ops (local, Ryan-requested) · Visibility layer live: ntfy phone feed (`config/notify.topic`) wired into all four legs — VPS runner notifies directly, both cloud trigger prompts updated (kept in sync with new protocol step 8), and a new `kalshi-weekly-retro` routine (trig_0147PgZMXWWXYXpb2ZdZHqfm, Sundays 12:00 UTC) sends a plain-English week-in-review + opens a leave-open improvement PR (never self-merged).
- 2026-07-03T19:40Z · Q4/S7b · claim-check: open PR #4 claims Q1's remaining odds-api work (draft, unmerged, waiting on Ryan's `ODDS_API_KEY`) — skipped Q1, moved to Q4 (topmost eligible IN-PROGRESS item). Built the S7b join: `extract_kalshi_teams`/`match_kalshi_espn` (team-name containment + ±1-day kickoff window) + `run_clv_join` (real pregame ask anchored at ESPN's actual kickoff, de-vig DraftKings' close, per-field source tags) in `collection/sports_history.py`. Found the prior S7a ESPN pull's date window (Jun15-21) didn't overlap the Kalshi WC tape's actual dates (Jun26-Jul02) at all — re-fetched ESPN for the correct window before joining. Live pass: 27 games matched (24 WC + 3 NBA), 78 outcomes priced, mean bracket_sum 1.020, mean edge_after_fee −0.0241 (descriptive only, not a verdict — S7c still owns the bootstrap). 37 new tests (155 total), invariants green. Full writeup: `findings/2026-07-03-sports-history-s7b.md`.
- 2026-07-03T23:34Z · Q5 · claim-check: only open PR is #4 (Q1, unrelated) — Q5 unclaimed. Built `scripts/s8_basis_probe.py` (read-only over accumulated `tape/crypto_hourly/`). Resolved the Q2 overround flag: BTC's mean +$5.00 overround (19 passes) is 66.1% real near-the-money spread, only 33.9% the suspected floor-tick artifact (ETH splits 43%/57%, floor-heavier — smaller ladder). Could NOT run the ρ-guard as specified: the tape's paired `spot` lags each settlement by a mean 29 minutes (VPS `:23`/cloud `:53` cadence vs on-the-hour settlement), enough ordinary BTC drift to fully explain the observed gaps (max $150, 84.6% of hours over half a $100 band) without any real feed mismatch — tried to fix this with Coinbase's historical `/candles` endpoint (free, keyless) but this session's egress is currently blocked to every external host tested, including Kalshi itself (403 on CONNECT). Q5 left IN-PROGRESS/BLOCKED(egress), not DEAD — this is a data-adequacy gap the probe surfaced, not a CI failing to clear zero. 0 new unit tests (pure read-only analysis script over existing tape, matching `longshot_fade_probe.py`/`weather_rehab_s5.py` precedent); 140 tests green (unchanged), `invariants --full` green. Full writeup: `findings/2026-07-03-crypto-basis-s8-q5.md`.
- 2026-07-04T (research loop) · Q4/S7c · claim-check: `git fetch origin main` showed main had advanced (hourly tape passes + a merged PR #7 adding the check-ntfy skill and Q5 writeup); rebased clean. Open PR #4 still claims Q1's odds-api leg (draft, unmerged, waiting on `ODDS_API_KEY`) — skipped Q1, moved to Q4 (topmost eligible IN-PROGRESS item). Re-fetched Kalshi's `KXWCGAME` settled tape at a higher limit (87 events now retained, full tournament to date vs S7b's 25) + fresh ESPN closing odds for the matching window (20260611-20260703, 88/88 events with DraftKings odds), re-ran the join: 77/87 matched, 0 ambiguous, 0 unparseable. Combined with S7b's 3 NBA games (deduped by event ticker, kept latest capture): **80 unique games, 237 priced outcomes** — ~3x S7b's n. New read-only `scripts/s7c_sports_clv_bootstrap.py` block-bootstraps `edge_after_fee` by GAME (not outcome), 10,000 resamples: mean −0.0235, 95% CI [−0.0245, −0.0225] — strictly below zero. **S7 verdict: DEAD** (taker side vs DraftKings-close). Q4 flipped IN-PROGRESS → DONE; `kb/strategies/00-index.md` S7 row + notes updated. 0 new unit tests (read-only analysis script over existing tape, same precedent as `s8_basis_probe.py`); 140 tests green (unchanged), `invariants --full` green. Full writeup: `findings/2026-07-04-sports-clv-s7-verdict.md`.
- 2026-07-04T05:20Z · Q5 · claim-check: `git fetch origin main` showed only hourly `tape:` passes since the last research run; open PR #4 still claims Q1's odds-api leg (unrelated) — skipped Q1. Re-verified egress directly: all hosts 200, including Coinbase's `/candles` endpoint that 403'd last run — the exact unblock Q5 was waiting on. Added `--historical-spot` to `scripts/s8_basis_probe.py`: fetched Coinbase's 1-minute candle at the exact settlement-instant bucket for all 36 accumulated settled hours (18/symbol), fixing the 29-minute live-spot lag confound (lag now 0s, zero gaps, cached to `tape/crypto_hourly_historical_spot/`). Also fixed a latent bug where the half-band check used a fixed $100 width for both symbols instead of ETH's actual $20 strike spacing. Corrected ρ: BTC 0.963→0.9997, ETH 0.947→0.9998 (weather-precedent kill territory); max gap never crosses half a bracket width for either symbol (BTC $38.93/$50, ETH $0.94/$10). **S8 verdict: DEAD** — the ρ-guard's own cheap-kill criterion triggers, no bootstrap needed (BTC shows a small +$16.43 non-zero-centered basis, plausibly real but an order of magnitude below the bracket width). Q5 flipped IN-PROGRESS → DONE; `kb/strategies/00-index.md` S8 flipped to `dead ✗`. 7 new unit tests (`tests/test_s8_basis_probe.py`, offline/monkeypatched), 147 tests green, `invariants --full` green. Full writeup: `findings/2026-07-04-crypto-basis-s8-verdict.md`.
- 2026-07-04T (research loop) · Q6 · claim-check: `git fetch origin main` in sync, only open PR (#4) claims Q1 (unrelated) — Q6 was the topmost eligible TODO. Built `scripts/anomaly_sweep.py` (platform-wide `/markets?status=open` pagination, no category filter) + `core/pricing.py` additions (`fee_per_contract`, `true_arb_edge`, `monotonicity_crossing_edge` — the sanctioned Hard Rule #3 site) for two real-fillable checks: complete-ladder true arb (bracket sum vs $1+fees) and S3's cross-strike monotonicity (nested "greater"/"less" strikes, real ask/no_ask hedge). Found live that Kalshi's open-market count is far larger than assumed (10,000+ in the first 10 pages, cursor unexhausted) — an unbounded pull grew RSS past 3GB before being capped; added a `--limit 20000` default with an honest `markets_truncated` flag on every tape record. Live-validated the bracket-arb check directly against KXBTC's real 188-member ladder (bracket_sum 7.78, correctly not flagged — matches Q2/Q5's already-documented fine-band overround, not a new arb). Three capped live sweeps run (300/3000/20000 markets), all `completeness_ok`, 0 anomalies (expected). Automatically wired into Q3's 09 UTC slot (no code change — `hourly_pass.py` already invokes the script by path once it exists). 22 new unit tests (17 in `tests/test_anomaly_sweep.py` + 5 pricing tests), 169 tests green, `invariants --full` green.
- 2026-07-04T (research loop) · Q8 (new) · claim-check: `git fetch origin main` in sync at 640da43 (hourly `tape:` passes only); only open PR (#4) claims Q1 (unrelated, awaiting `ODDS_API_KEY`) — Q2-Q6 all DONE, Q7 BLOCKED (only 2 days of Q2 tape, needs ≥7) — **no eligible TODO/IN-PROGRESS item existed**. Appended Q8 and started S9 (next un-started registry candidate) rather than idle the run. Found Kalshi's `KXWCROUND` series and Polymarket's "World Cup: Nation To Reach `<round>`" events are the identical Yes/No question (one market per round×team) on both venues — no de-vig needed, unlike S7. Built `collection/polymarket_pairs.py`: Polymarket discovery via its public `/public-search` endpoint (keyword-narrowed, title-regex-confirmed, no hardcoded event IDs), matched to Kalshi by exact (round, normalized team name), Polymarket price pulled from its live CLOB order book (`real_ask`, not the `outcomePrices` reference). 20 new unit tests (offline). Live pass: 48/48 Kalshi round markets matched, completeness ok, mean `price_gap_yes_ask` +0.20¢ (range −3¢/+3¢, one snapshot, descriptive only). `kb/strategies/00-index.md` S9 flipped idea→data-collecting. 189 tests green (169 prior + 20 new), `invariants --full` green.
- 2026-07-04T16:20Z · ops (interactive, Ryan-requested) · Loop health audit + restock: all 3 triggers verified enabled and firing today (collector last 15:53Z, research 15:07Z, retro next Sun 12:00Z). Found 10 collector passes stranded on `tape/hourly-*` fallback branches (push-to-main failed intermittently) — union-appended their 1,674 missing tape lines into the canonical per-day files, added protocol step 0b (stranded-tape sweep every research run), swept branches deleted post-merge. Seeded registry S12–S18 from `findings/2026-07-04-edge-candidates-s12-s18.md` (19 raw → 7 survivors) and appended Q9–Q13 so the queue has ~a week of eligible milestones (queue was one item from dry: only Q8 eligible, Q7 blocked to ~Jul 10). ntfy feed unreachable from this sandbox (egress), verified loop health via git/GitHub instead.
- 2026-07-04T (ops, Ryan-requested) · ntfy-watch (new leg) · Ryan asked to be notified whenever an ntfy message lands so issues get fixed proactively rather than just texted. ntfy is one-way push to the phone app — nothing calls back into a session — so true instant-push isn't possible; built the closest available thing instead: an hourly trigger (`ntfy-watch`, fresh session per firing) that polls `config/notify.topic` for `priority>=4` messages, dedups against `ops/ntfy-watch-state.md` (its append-only handled-message log — this IS the memory since each firing starts cold), investigates anything new (git log / open PRs / CI / the referenced queue item), and — per Ryan's choice — attempts a real fix within the existing Stop rules (research/data-only, no credentials, gates green before commit) rather than only reporting, committing/PR'ing exactly like the research-loop protocol, then posts one follow-up phone note. Silent when nothing new is found. See `ops/ntfy-watch-state.md` for the protocol detail.
- 2026-07-04T20:08Z (research loop) · claim-check + stranded-tape sweep + Q9 · `git fetch origin main` at 6ebb2cf; only open PR (#4) claims Q1 (draft, unmerged, awaiting `ODDS_API_KEY`, unrelated) — Q2-Q6/Q8 all DONE-or-in-progress-elsewhere, Q7 BLOCKED — Q9 (S13) was the topmost eligible TODO. Step 0b sweep: 12 `tape/hourly-*` fallback branches found; 10 were fully redundant with `main` (0 missing lines, confirmed line-by-line) — attempted `git push origin --delete` on each but the same permission boundary that blocks `push origin main` also blocks remote branch deletion from a cloud session (every delete failed, branches left in place, harmless/stale); 1 branch (`20260704T1854Z`, 73min old) had 187 lines `main` was missing (2 crypto_hourly + 185 sports_pairs) — union-appended into this run's commit; 1 branch (`20260704T1955Z`, ~13min old) skipped per the 30-min-freshness rule, left for the next run. Built `scripts/s13_maker_fillsim.py` (Q9/S13): bid = DK-close-devig fair − 1¢, fill = real trade crossing at/below it (hourly candlestick `price.low_dollars`, market `open_time` → ESPN kickoff), 22 new unit tests. Live pass: 94.1% fill rate (223/237 outcomes), `edge_after_fee` conditional on fill 95% CI [−0.00021, +0.00039] — straddles zero. **S13 verdict: DEAD** (null result — Kalshi's maker fee alone consumes ~all of the assumed 1¢ margin). Caught and fixed two bugs before finalizing: wrong fee rate (taker 0.07 used instead of maker 0.0175, a 4x overcharge) and a naive cache that stored full raw candlesticks (98MB for 237 tickers, since some WC markets open 4+ months pre-kickoff) — trimmed to just the window's min trade price + timestamp (93KB). 210 tests green, `invariants --full` green. Full writeup: `findings/2026-07-04-sports-maker-s13-verdict.md`; `kb/strategies/00-index.md` S13 flipped to `dead ✗`.
- 2026-07-05T00:14Z (research loop) · claim-check + stranded-tape sweep + Q8 · `git fetch origin main` at 092196c; only open PR (#4) claims Q1 (unrelated) — Q2/Q3/Q4/Q5/Q6/Q9 DONE, Q7/Q13 BLOCKED — Q8 (IN-PROGRESS) topmost eligible. Step 0b sweep caught its own bug first: the sandbox's local `main` ref was stale (2026-07-02, two days behind `origin/main`), making every `tape/hourly-*` branch look like it had thousands of lines missing, including in files the collector never touches — re-pointed local `main` at `origin/main` before trusting any diff. Against the real tip: 12/15 branches already fully reconciled by the prior run; 3 branches (`1955Z`/`2055Z`/`2155Z`) had 8 crypto_hourly + 536 sports_pairs lines `main` lacked, union-appended; 1 branch (`2355Z`, ~19min old) skipped per freshness rule. `git push origin --delete` still fails from a cloud session on every branch (same permission boundary, harmless). Wired `collection/polymarket_pairs.py` into `collection/hourly_pass.py` as a third sub-pass alongside sports_pairs/crypto_hourly — same fault-isolation + honest-completeness-AND discipline, 2 new tests, all 9 existing hourly_pass tests updated with a zero-contribution polymarket stub. Live smoke: polymarket sub-pass fired for real, 40/40 Kalshi round markets matched, completeness ok. 212 tests green, `invariants --full` green. Q8 remaining gap is now purely "let hourly snapshots accumulate" — no more code needed before the lead-lag cross-correlation.
- 2026-07-05T05:19Z (research loop) · claim-check + stranded-tape sweep + Q10 · `git fetch origin main` at 9de63e2; only open PR (#4) claims Q1 (unrelated, still awaiting `ODDS_API_KEY`) — Q2/Q3/Q4/Q5/Q6/Q9 DONE, Q7/Q13 BLOCKED, Q8's only remaining gap is letting snapshots accumulate (no code) — **Q10 (S12, TODO)** topmost eligible item with real work. Step 0b sweep: local `main` was correctly at the real tip this time; 15/17 `tape/hourly-*` branches already fully reconciled (0 missing lines); 2 branches (`20260704T2355Z` 181 lines, `20260705T0055Z` 256 lines) union-appended into this commit; 1 branch (`20260705T0455Z`, ~13min old) skipped per freshness rule. `git push origin --delete` still blocked from a cloud session (same permission boundary). Built `collection/econ_prints.py`: live-confirmed 5 flagship series (`KXCPI`/`KXCPIYOY`/`KXCPICORE`/`KXPAYROLLS`/`KXGDP`, nested-monotonic threshold ladders — deliberately NOT run through `core.pricing.bracket_sum`, which is scoped to complete partitions) — captures every open event's full real_ask ladder + the most-recent settlement's Kalshi-published print value (`broker_truth`). 12 new unit tests. Live pass: all 5 series pass_complete (24 open events/296 strikes, 5/5 settlements resolved, e.g. CPI MoM print "0.5", payrolls "57,000"). Wired into `hourly_pass.py`'s 09 UTC slot (4 new wiring tests, 9 existing tests updated with a stub). Nowcast leg (Cleveland Fed/GDPNow) left BLOCKED(nowcast-scrape) — same shape as Q1's odds-api leg — Cleveland Fed's page has no scrapable static data, GDPNow's does but needs nontrivial follow-up work; every record's `nowcast` field is honestly `{"status":"not_built"}`. `kb/strategies/00-index.md` S12 flipped idea → data-collecting. 228 tests green (212 prior + 16 new), `invariants --full` green.
- 2026-07-05T10:08Z (research loop) · claim-check + stranded-tape sweep + Q11 · `git fetch origin main` showed the sandbox branch already at the real tip (`a5d9b4f`, hourly `tape:` passes only since the last run); only open PR (#4) still claims Q1 (draft, unrelated, awaiting `ODDS_API_KEY`) — Q2/Q3/Q4/Q5/Q6/Q9/Q10 DONE, Q7/Q13 BLOCKED, Q8's only remaining gap is accumulation (no code) — **Q11 (S15, TODO)** was the topmost eligible item with real work. Step 0b sweep: of 21 `tape/hourly-*` branches, 4 (`20260705T0455Z`/`055604Z`/`0755Z`/`0854Z`, all >30min old) had lines `main` lacked — 8 crypto_hourly + 160 polymarket_pairs + 816 sports_pairs, union-appended into this commit (verified 0 exact-duplicate lines, all valid JSON); the newest branch (`0957Z`, ~12min old) skipped per freshness rule; `git push origin --delete` still fails from a cloud session (same documented permission boundary). Extended `scripts/anomaly_sweep.py` with a third check (`check_cross_event_implication`) + new `config/implication_pairs.yaml` (hand-curated implication graph — one audited family, `kxwcround_progression`: reaching a later World Cup round strictly implies every earlier round for the same team; audit note documents the settlement-rules read, same title text `collection/polymarket_pairs.py` already confirmed structurally). Reused `core.pricing.monotonicity_crossing_edge` unchanged — same fee-floor math as Q6's check 2, just across two `event_ticker`s instead of one. 10 new unit tests + 2 `run()`-wiring tests. Live-validated directly against Kalshi's real 40 open KXWCROUND markets: 38 generated round pairs, 0 fee-clearing hits (expected, matches Q6/Q8 precedent; spot-checked one pair — Team USA SEMI priced 19¢ vs QUAR 52¢, correctly monotonic). `kb/strategies/00-index.md` S15 flipped idea → data-collecting. 238 tests green (228 prior + 10 new), `invariants --full` green.
- 2026-07-05T15:13Z (research loop) · claim-check + stranded-tape sweep + Q10 · `git fetch origin main` forced-updated local ref to `a5f1291`; open PRs unchanged — #4 still claims Q1 (unrelated, awaiting `ODDS_API_KEY`), #18 is the weekly retro's own protocol-amendment proposal (left for Ryan, never self-merged). Q2–Q6/Q9/Q11 DONE, Q7/Q13 BLOCKED, Q8's only remaining gap is accumulation (no code) — **Q10 (KALSHI LEG DONE, real work remaining)** was topmost eligible, same precedent used to skip Q8 the last two runs. Step 0b sweep (line-set diff, not `git diff --stat`, per file): 22/24 `tape/hourly-*`/amended branches already fully reconciled; 2 (`20260705T1155Z`/`1253Z`) had 4 crypto_hourly + 80 polymarket_pairs + 389 sports_pairs lines `main` lacked, union-deduped and appended (all valid JSON, 0 exact dupes); newest branch (`1455Z`, ~13min old) skipped per freshness rule; `git push origin --delete` still blocked (same permission boundary). Built the GDPNow leg of `collection/econ_prints.py`'s `nowcast` field: scrapes the Atlanta Fed's embedded `forecastDates`/`forecastQuarters`/`gdpForecast` JS arrays (confirmed live: quarter-blocks newest-first, each date-ascending — current nowcast = last entry of the first block); a missing/mismatched array or null latest value is an honest `parse_error`, never fabricated. Live check: GDPNow reads **+1.19%** annualized for the quarter ending 2026-06-30 (as of 2026-07-01, 27 updates that quarter), tagged `synthetic`. Cleveland Fed's CPI leg stays `not_built` (genuinely unscrapable, unrelated gap). 7 new unit tests (245 total, incl. fixing one existing test to inject a stub GDP fetcher so it stays network-free), `invariants --full` green. Q10 flipped KALSHI-LEG-DONE → full DONE.
- 2026-07-05T20:09Z (research loop) · claim-check + stranded-tape sweep + Q8 · `git fetch origin main` force-updated local ref to `d1ae913`; open PRs unchanged — #4 still claims Q1 (unrelated, awaiting `ODDS_API_KEY`), #18 is the weekly retro's protocol-amendment proposal (left for Ryan). Q2–Q6/Q9/Q10/Q11 DONE, Q7/Q13 BLOCKED — Q8 (IN-PROGRESS) was topmost eligible by the letter of the protocol, and by this run's time ~19h of continuous hourly collection had accumulated since the 2026-07-05T00:11Z wiring (37 captures) — enough to actually attempt the lead-lag cross-correlation Q8's spec calls for, instead of skipping again. Step 0b sweep: 2 of 27 `tape/hourly-*` branches (`155348Z`/`1655Z`, both >30min old) had lines `main` lacked — 4 crypto_hourly + 80 polymarket_pairs + 360 sports_pairs, union-deduped and appended (all valid JSON, 0 exact dupes); `git push origin --delete` still blocked (same permission boundary). Built `scripts/s9_leadlag_probe.py`: pooled panel cross-correlation over 40 markets/≥10 captures each — contemporaneous ρ +0.293 (n=1,440), kalshi-leads-poly +0.044, poly-leads-kalshi −0.007 (n=1,400, both noise-level). More important finding: `market_membership_changes()` found **zero** in-window round-transition events — no team has advanced/been eliminated since continuous collection started, so S9's actual thesis (does one venue lag the other around a real information shock) is still untested; every tick so far is book noise. 20 new unit tests, 265 tests green (245 prior + 20 new), `invariants --full` green. `kb/strategies/00-index.md` S9 note updated, stays `data-collecting`. See `findings/2026-07-05-polymarket-leadlag-s9-first-cut.md`.
- 2026-07-06T00:22Z (research loop) · claim-check + stranded-tape sweep + Q12 · `git fetch origin main` at `1337175`, local branch already at the real tip; open PRs unchanged — #4 still claims Q1 (unrelated), #18 is the weekly retro's protocol-amendment proposal (left for Ryan). Q1 claimed, Q4/Q5/Q6/Q9/Q10/Q11 DONE, Q7/Q13 BLOCKED; Q8 (IN-PROGRESS) had only ~4h of new accumulation since its own 2026-07-05T20:09Z run (44 vs 37 captures, still no round transition) — rerunning it would reproduce the same "still noise" result, so per the prior run's own note this run moved to **Q12 (S17, TODO with unstarted real work)** instead. Step 0b sweep: 2 of 29 `tape/hourly-*` branches (`20260705T2155Z`/`2255Z`, both >30min old) had lines `main` lacked — 4 crypto_hourly + 76 polymarket_pairs + 304 sports_pairs, union-deduped and appended (all valid JSON, 0 exact dupes); `git push origin --delete` still blocked (same permission boundary). Built `collection/polymarket_pairs.run_fed_decision()`: second Kalshi↔Polymarket family (Fed rate-decision meetings, `KXFEDDECISION`'s 5-bucket ladder vs Polymarket's "Fed Decision in `<Month>`?" events), matched by (meeting month+year, bucket) confirmed via each side's own title/question text — not the Kalshi ticker's bps suffix alone (it uses "26" as a stand-in for ">25", confirmed live). Judged completeness against Polymarket's side rather than Kalshi's, since Kalshi lists meetings ~18 months out (to Jan 2028) while Polymarket only creates an event closer to it — grading against Kalshi's full calendar would make this leg FAIL forever, a structural non-issue. Wired into `hourly_pass.py` as a fourth cross-venue sub-pass, own tape family `tape/polymarket_macro_pairs/`. 22 new unit tests, 287 tests green (265 prior + 22 new), `invariants --full` green. Live pass: 15/15 currently-listed Polymarket Fed-decision markets matched (Jul/Sep/Oct 2026), 0 ambiguous, 0 book errors, completeness ok; gaps −3¢ to +15¢ (one snapshot, descriptive only). CPI/inflation leg explicitly deferred (different price shape — cumulative threshold vs exact bucket — would need a derived transform, not a same-question real_ask pair). `kb/strategies/00-index.md` S17 flipped idea → data-collecting. See `findings/2026-07-06-fed-decision-macro-pairs-q12-first-cut.md`.
- 2026-07-06T05:17Z (research loop) · claim-check + stranded-tape sweep + Q8 · `git fetch origin main` at `a6567cf`, local branch already at the real tip; open PRs unchanged — #4 still claims Q1 (unrelated), #18 is the weekly retro's protocol-amendment proposal (left for Ryan). Q2/Q4/Q5/Q6/Q9/Q10/Q11 DONE, Q7/Q13 BLOCKED — Q8 (IN-PROGRESS) was topmost eligible, and this run's own check of `tape/polymarket_pairs/` found real round transitions for the first time (Brazil and Mexico both eliminated, quarterfinal losses), so Q8's own remaining-work note was finally actionable. Step 0b sweep: 1 of the `tape/hourly-*` branches (`20260706T0256Z`, >30min old) had lines `main` lacked — 2 crypto_hourly + 15 polymarket_macro_pairs + 36 polymarket_pairs + 182 sports_pairs, union-deduped and appended (all valid JSON, 0 exact dupes); `git push origin --delete` still blocked (same permission boundary). Built `scripts/s9_shock_eventstudy.py`: isolates real transitions from `market_membership_changes()` (excluding the documented startup artifact) and reports each affected ticker's last two captured rows (the actual repricing step) on both venues. Result across 2 real events / 8 ticker-steps: Kalshi and Polymarket moved together every time — mean `|Δkalshi − Δpolymarket|` 2.2¢, max 8¢, no consistent one-venue-leads pattern, both venues already reflecting the outcome by the very next capture (30–60min later). **Finding is methodological, not a null result on the thesis:** collection cadence is coarser than the event itself (a match resolves within minutes) — S9's lead-lag thesis cannot be resolved at this cadence as built. 10 new unit tests, 297 tests green (287 prior + 10 new), `invariants --full` green. `kb/strategies/00-index.md` S9 note updated, stays `data-collecting`. See `findings/2026-07-06-polymarket-leadlag-s9-shock-eventstudy.md`.
- 2026-07-06T (research loop) · claim-check + stranded-tape sweep + Q8 resolution · `git fetch origin main` at `24b155f`, local branch already at the real tip; open PRs unchanged — #4 still claims Q1 (unrelated), #18 is the weekly retro's protocol-amendment proposal (left for Ryan). Q2/Q4/Q5/Q6/Q9/Q10/Q11 DONE, Q7/Q13 BLOCKED — Q8 (IN-PROGRESS) was topmost eligible. Step 0b sweep: every currently-listed `tape/hourly-*` branch was already fully reconciled with `main` (0 missing lines) — nothing to append this run. Closed out Q8's own remaining-work note (a resolution decision on the sub-hourly-burst-vs-dead question): checked the loop's actual scheduling tools (`create_trigger`/`send_later`) — recurring cron is hard-capped at hourly minimum interval, ruling out a sub-hourly recurring poll; one-shot triggers aren't cadence-limited but need a per-match kickoff timestamp the tape doesn't carry, and building N one-shot bursts per remaining match is a new class of unattended multi-day automation this run shouldn't decide alone (same category as the VPS collector/`ntfy-watch`, both Ryan-requested). **Verdict: S9 lead-lag flips dead ✗ (data-adequacy, not a CI falsification)** — the prior run's own n=8 shock-study evidence (both venues repriced together every time) already showed the thesis untestable at this cadence; **cross-venue parity survives under S17** (already answered well, no sub-hourly resolution needed there). No new code — decision on already-collected evidence. 297 tests unchanged, `invariants --full` green. `kb/strategies/00-index.md` S9 flipped to dead ✗; Q8 flipped IN-PROGRESS → DONE. See `findings/2026-07-06-polymarket-leadlag-s9-resolution.md`.
- 2026-07-06T15:06Z (ops, Ryan-requested, interactive) · agent-team setup + tape audit + stranded sweep · Stood up `.claude/agents/`: Fable lead on high reasoning (`research-lead`) guiding five Opus workers (`collector-engineer`, `edge-prober`, `verifier`, `kb-distiller`, `tape-auditor`); added the compounding layer `kb/lessons/00-lessons.md` (17 lessons mined from run history, each with an enforcement-status column — UNENFORCED rows are the kb-distiller's standing work queue) + roster section above. Step-0b sweep: 6 of 30 `tape/hourly-*` branches held 1,158 lines main lacked (554+374 sports_pairs, 120+64 polymarket_pairs, 30 polymarket_macro_pairs, 10 crypto_hourly, 5 econ_prints, 1 anomalies), union-appended, all JSON-valid, 0 dupes; `1455Z` skipped (11.6min, freshness rule). Full tape audit → `findings/2026-07-06-tape-audit.md`: 29,363 lines/10 families/07-02→07-06, all 12 incomplete crypto passes are one venue-side hole (no hourly group in the 20 UTC hour, daily — ledgered as L15); Q7 eligible ~07-09/10, Q13 ~07-12/13; tape 36MB raw, crosses README's ~50MB decision point ~mid-July (Ryan's call, flagged). Gates: 297 tests green, `invariants --full` green. NOT done (permission-gated, consistent with PROVENANCE.md's "left for explicit approval"): registering the built-and-tested PreToolUse invariants hook in `.claude/settings.json` — needs Ryan.
- 2026-07-06T (research loop) · claim-check + stranded-tape sweep + Q12 CPI leg · `git fetch origin main` at `4b76056`; local `main` ref found badly stale (2026-07-02, ~50 commits/4 days behind the real tip) — fixed with `git branch -f main origin/main` before trusting any diff, exactly the bug PR #18's weekly-retro proposal flagged. Open PRs unchanged — #4 still claims Q1 (unrelated, awaiting `ODDS_API_KEY`), #18 is the retro's protocol-amendment proposal (left for Ryan). Q1 claimed, Q2–Q6/Q8–Q11 all DONE, Q7/Q13 BLOCKED — **Q12 (FED-DECISION LEG DONE, real remaining work: the deferred CPI/inflation leg)** was topmost eligible. Step 0b sweep (against the corrected `main`): 5 of 35 `tape/hourly-*` branches (`202607051954Z`/`20260705T0957Z`/`20260705T1455Z`/`20260706T0855Z`/`20260706T1255Z`, all >30min old) carried lines `main` was missing across 9 tape files — union-deduped per file (each branch is an independent snapshot, not a superset of the others), 1,158 lines total, every line validated as parseable JSON with 0 exact duplicates, appended into this commit; `git push origin --delete` still blocked (same permission boundary). Built `collection/polymarket_pairs.run_cpi()`: pairs Kalshi's `KXCPI`/`KXCPIYOY`/`KXCPICORE` cumulative "exceed threshold T" ladders against Polymarket's exact 0.1-point bucket partition for the same 3 US print series via a differencing transform (`price_cpi_bucket_from_kalshi`) tagged `synthetic` per Hard Rule #3's spirit — exactly the transform the prior Fed-leg cut deferred rather than fake. 23 new unit tests (320 total), wired into `hourly_pass.py`'s existing 09 UTC daily slot (CPI releases monthly, same cadence reasoning as Q10's `econ_prints`; 4 new wiring tests, 6 existing 09-UTC tests updated with a stub). `invariants --full` green. Live pass: 17 open Kalshi CPI events, 3 matched Polymarket events, 0 unmatched/ambiguous, 22/28 buckets priced (the other 6 need Kalshi strikes further out than its ladder currently lists — an honest, expected coverage gap correctly counted against completeness); one bucket flagged `monotonicity_violation: true` (a thin/stale far-forward Kalshi strike, recorded not clipped). `kb/strategies/00-index.md` S17 note updated; Q12 flipped FED-DECISION-LEG-DONE → full DONE. See `tape/polymarket_cpi_pairs/dt=2026-07-06.jsonl`.
- 2026-07-06T20:10Z (research loop) · claim-check + PR #26 merge + stranded-tape sweep + Q14/Q15 (new) · `git fetch origin main` at `efb9245`, local branch already at the real tip. Open PR #26 (kb-distiller's L5/L7/L17 escalation, research/docs-only) verified green locally (348 tests, `invariants --full` clean) and merged (squash → `098edbe`); PR #4 (Q1, unrelated) and #18 (retro proposal, left for Ryan) unchanged. Step 0b sweep: 3 of 39 `tape/hourly-*` branches (`20260706T0556Z`/`0955Z`/`1856Z`) turned out to be stale branch names pointing at a 2026-07-02 commit with zero tape content (harmless, not real strandage); 3 fresh branches (`20260706T1455Z`/`165524Z`/`1755Z`, all >30min old) carried 703 lines `main` lacked (6 crypto_hourly, 45 polymarket_macro_pairs, 96 polymarket_pairs, 556 sports_pairs), union-deduped, 0 exact dupes, all valid JSON, appended into this commit; `git push origin --delete` still blocked (same permission boundary). Queue was drained to time-blocked items (Q7 ~07-09/10, Q13 ~07-13) plus Q1 (claimed) — followed the registry's stated priority order past S15/S17 to the next two un-started candidates, appended **Q14 (S16 FedWatch fade)** and **Q15 (S18 Congress-control fade)**. Both hit real external walls before any collector was worth writing: S16 — `cmegroup.com` 403s/resets every path tried (Akamai-class bot protection) while Kalshi and the Atlanta Fed's GDPNow page (same free-JS-data shape) both worked fine this run, confirming venue-side not sandbox egress. S18 — Kalshi's `HOUSE`/`SENATE`/`KXHOUSE`/`KXSENATE` series exist but list zero markets in any status (2026 midterm contracts not yet listed); separately 538's CSV feed now redirects to a dead ABC News stub and RealClearPolling 403s like CME — Wikipedia's 2026 House-elections article is a live fallback source for once Kalshi lists real markets. Both recorded `BLOCKED` per the Stop rules (data-adequacy, not a CI falsification) — no source/test code changed. 348 tests unchanged, `invariants --full` green. See `findings/2026-07-06-s16-s18-feasibility-blocked.md`; `kb/strategies/00-index.md` S16/S18 notes updated.
- 2026-07-07T00:11Z (research loop) · claim-check + stranded-tape sweep + Q16 (new) · `git fetch origin main` at `c238b17`, local `main` re-pointed via `git branch -f main origin/main` (session branch was already at the real tip). Open PRs unchanged — #4 still claims Q1 (unrelated, awaiting `ODDS_API_KEY`), #18 is the weekly retro's protocol-amendment proposal (left for Ryan). Q2–Q6/Q8–Q12 all DONE, Q7 BLOCKED (only ~4 days of Q2 tape, needs ≥7), Q13 BLOCKED (only ~4 days of Q3 tape, needs ≥10) — **no numbered queue item was eligible this run.** Step 0b sweep: of 42 `tape/hourly-*` branches, 2 fresh ones (`20260706T2059Z`/`2255Z`, both >30min old) carried lines `main` lacked — 8 crypto_hourly + 60 polymarket_macro_pairs + 124 polymarket_pairs + 710 sports_pairs, union-deduped across both branches, all valid JSON, 0 exact duplicates, appended into this run's commit; `git push origin --delete` still blocked (same permission boundary). Checked the registry for the next un-started, non-externally-blocked candidate past the queue's own drained state: S4/S10/S11/S14 are all already blocked (unrelated-repo dependency, or the same tape/key blocks as Q7/Q13/Q1) — **S6** (inventory-aware market-making) was the only remaining `idea`-stage candidate with no external block, so appended **Q16** and built it via the `collector-engineer` subagent. Built `collection/orderbook_depth.py`: full L2 depth capture (yes_bids/no_bids ladders, `real_ask`/`real_bid` tagged) fed by the exact tickers `sports_pairs`/`crypto_hourly` already discover each pass (read back from their own freshly-written tape by `capture_id` — no platform re-sweep, honoring L10), wired into `hourly_pass.py` as a fifth fault-isolated sub-pass. 13 new unit tests (361 total), `invariants --full` green. Live pass against real Kalshi data: 6/6 current-hour KXBTC tickers captured, `completeness_ok=True`; caught and tested a would-be false-drop bug (one-sided wing books are genuine Kalshi shape, not a capture gap) before commit. Honestly documented in the module's own docstring: hourly cadence (this loop's recurring-cron floor) gives S6 a snapshot depth series, not continuous order-flow — any arrival-intensity estimate built on it must be labeled snapshot-sampled. `kb/strategies/00-index.md` S6 flipped idea → data-collecting; `kb/lessons/00-lessons.md` gained L21 (tape-readback wiring pattern for a downstream sub-pass needing an upstream sub-pass's discovered set), L22 (the source-tag enum has no `real_bid` slot — UNENFORCED, flagged for the kb-distiller), L23 (one-sided wing books are valid captures, not drops).
- 2026-07-07T05:08Z (research loop) · claim-check + stranded-tape sweep + L22 resolution · `git fetch origin main` at `e20f026`; open PRs unchanged — #4 still claims Q1 (unrelated, awaiting `ODDS_API_KEY`, still short of PR #18's flagged 5-day escalation mark), #18 is the retro's protocol-amendment proposal (left for Ryan). Q2–Q6/Q8–Q12/Q16 all DONE, Q7 BLOCKED (5 of ≥7 days of Q2 tape), Q13 BLOCKED (5 of ≥10 days of Q3 tape) — no numbered queue item eligible. Step 0b sweep: of 44 `tape/hourly-*` branches, 3 fresh-enough ones (`202607070056Z`/`20260707T015503Z`/`202607070356Z`, all >30min old) carried lines `main` lacked — 6 crypto_hourly + 700 orderbook_depth + 544 sports_pairs + 45 polymarket_macro_pairs + 80 polymarket_pairs, union-deduped across all three, all valid JSON, 0 exact duplicates, appended into this run's commit; `20260707T0456Z` skipped (~12min old, freshness rule); 3 branches confirmed stale names pointing at a pre-project commit (harmless). `git push origin --delete` still blocked (same permission boundary). Registry check found no new actionable collector/probe milestone (S4/S10=Q7/S14=Q13/S16=Q14/S18=Q15 all already blocked; S11 needs the same Pinnacle/odds-api anchor Q1 is already blocked on) — drew from `kb/lessons/00-lessons.md`'s standing UNENFORCED queue instead. Resolved **L22** (does `real_bid` join `VALID_SOURCE_TAGS`?): kept it a separate tape-only namespace — that enum mirrors CLAUDE.md's own literal 4-tag trust-taxonomy contract, and widening a project-contract enum is outside a single milestone's authority (same class as S9's automation call and the PreToolUse-hook registration, both left for Ryan). Added a regression test (`tests/test_invariants.py::test_db_real_bid_tag_is_caught_as_invalid_enum`) proving the existing DB-side enum check already rejects `real_bid` — no live gap exists. `core/source_tag.py` docstring cross-references the decision; **L24** (supersedes L22) recorded. 362 tests green (361 prior + 1 new), `invariants --full` green.
- 2026-07-07T15:08Z (research loop) · claim-check + stranded-tape sweep only (queue/lessons/registry all genuinely idle) · `git fetch origin main` at `97ad331`, local branch already at the real tip. Open PRs unchanged — #4 still claims Q1 (unrelated, awaiting `ODDS_API_KEY`, now just under 4 days old, still short of PR #18's flagged 5-day escalation mark), #18 is the retro's protocol-amendment proposal (left for Ryan). Counted tape days directly off disk rather than trusting the last log line's estimate: Q7 needs ≥7 days of `tape/crypto_hourly/` — only 5 present (`dt=07-03`…`07-07`), still BLOCKED, eligible ~07-09/10; Q13 needs ≥10 days of `tape/sports_pairs/` — only 6 present (`dt=07-02`…`07-07`), still BLOCKED, eligible ~07-12/13. Lessons ledger re-checked: zero `UNENFORCED` rows remain (all now `invariant`/`test`/terminal `protocol`/`ledger-only`, L22 resolved by L24 last run) — that standing queue is drained too. Registry re-checked with two live re-probes: `HOUSE`/`SENATE`/`KXHOUSE`/`KXSENATE` still list 0 markets in any status (S18 stays BLOCKED) and `ODDS_API_KEY` still absent from env (S11/Q1 stay blocked); every other `idea`-stage candidate was already externally blocked. **No numbered queue item, lesson, or registry candidate was actionable this run.** Step 0b sweep: of 50 `tape/hourly-*` branches, 5 fresh ones since the last run (`20260707T0456Z`/`055501Z`/`202607070749Z`/`0756Z`/`0956Z`, all >30min old) carried lines `main` lacked — 10 crypto_hourly + 3,458 orderbook_depth + 75 polymarket_macro_pairs + 120 polymarket_pairs + 889 sports_pairs + 5 econ_prints + 1 anomalies = 4,558 lines total, union-deduped across all 5 branches, all valid JSON, 0 exact duplicates, appended into this run's commit; `20260707T1359Z` confirmed a stale branch name pointing at a pre-project commit (harmless). `git push origin --delete` not reattempted (documented permission boundary, PR #18 already proposes dropping the retry). 362 tests unchanged, `invariants --full` green. Honest maintenance-only run — queue, lessons, and registry are simultaneously idle pending external clocks (tape day-counts, 2-3 days out) and external walls (odds-api key, Congress-market listing, CME bot-wall); nothing here indicates a stall.
- 2026-07-07T20:09Z (research loop) · claim-check + stranded-tape sweep only (queue/lessons/registry all still idle) · `git fetch origin main` force-updated local ref to `a14afb6` (5 VPS hourly passes landed since the last run). Open PRs unchanged — #4 still claims Q1 (unrelated, awaiting `ODDS_API_KEY`, ~4d5h old, still short of PR #18's flagged 5-day escalation mark), #18 is the retro's protocol-amendment proposal (left for Ryan). Counted tape days directly off disk: Q7 needs ≥7 days of `tape/crypto_hourly/` — still only 5 (`dt=07-03`…`07-07`), BLOCKED, eligible ~07-09/10; Q13 needs ≥10 days of `tape/sports_pairs/` — still only 6 (`dt=07-02`…`07-07`), BLOCKED, eligible ~07-12/13. Q14/Q15 unchanged (data-adequacy BLOCKED, no re-probe this cycle). Lessons ledger and registry re-scanned: zero UNENFORCED rows, every idea-stage candidate already externally blocked — same drained state as the last 3 runs. **No numbered queue item, lesson, or registry candidate was actionable this run.** Step 0b sweep: of 54 `tape/hourly-*` branches, 2 (`20260707T1658Z`/`1759Z`, ages 191min/130min) carried lines `main` lacked — 4 crypto_hourly + 1,332 orderbook_depth + 30 polymarket_macro_pairs + 48 polymarket_pairs + 330 sports_pairs = 1,744 lines total, union-deduped across both branches per file, all valid JSON, 0 exact duplicates, appended into this run's commit; `20260707T1958Z` (~3min old) skipped per freshness rule; 3 branches (`20260706T1856Z`/`20260707T1359Z`/`20260707T1856Z`) confirmed stale names pointing at the same pre-project commit, harmless. `git push origin --delete` not reattempted (same documented permission boundary). 362 tests unchanged, `invariants --full` green. Fourth consecutive maintenance-only run; nothing here indicates a stall — PR #4's age is worth flagging to Ryan directly as it nears PR #18's own 5-day escalation trigger.
- 2026-07-07T20:15Z (research loop) · claim-check + stranded-tape sweep only — fully idle, first fully-clean sweep · `git fetch origin main` force-updated local ref to `b938307`. Open PRs unchanged — #4 still claims Q1 (unrelated, awaiting `ODDS_API_KEY`, ~4d9h old, still short of PR #18's proposed 5-day escalation mark), #18 is the retro's protocol-amendment proposal (left for Ryan). Tape day-counts recounted off disk: Q7 needs ≥7 days of `tape/crypto_hourly/` — still only 5 (`dt=07-03`…`07-07`), BLOCKED, eligible ~07-09/10; Q13 needs ≥10 days of `tape/sports_pairs/` — still only 6 (`dt=07-02`…`07-07`), BLOCKED, eligible ~07-12/13. Q14/Q15 re-probed live (not assumed): `ODDS_API_KEY` still absent, `KXHOUSE`/`KXSENATE` still list 0 markets — both stay BLOCKED. Lessons ledger and registry re-scanned: zero UNENFORCED rows, every idea-stage candidate already externally blocked. **No numbered queue item, lesson, or registry candidate was actionable this run.** Step 0b sweep: 9 branches postdating the last sweep cutoff (`20260707T1958Z`→`2256Z`, all >30min old) diffed line-by-line against `main` across all 5 tape families they touch — **zero lines missing from main in any branch/family**, the first fully-reconciled sweep this week (the VPS collector has been pushing straight to `main` all day). `20260707T2356Z` (~12min old) skipped per freshness rule. `git push origin --delete` not reattempted (same documented permission boundary). Gates re-verified from a clean env: 362 tests green, `invariants --full` green. Fifth consecutive maintenance-only run, first with literally nothing to commit (no tape, no code, no status change) — queue/lessons/registry/tape all simultaneously idle pending the same external clocks and walls as prior runs; not a stall.
- 2026-07-08T01:08Z (research loop) · claim-check + stranded-tape sweep only — queue still idle, real tape recovered · `git fetch origin main` force-updated local ref to `12f794c`. Open PRs unchanged — #4 still claims Q1 (unrelated, awaiting `ODDS_API_KEY`, ~4d14h old, still short of PR #18's proposed 5-day escalation mark). Tape day-counts recounted off disk: Q7 needs ≥7 days of `tape/crypto_hourly/` — only 6 (`dt=07-03`…`07-08`), BLOCKED, eligible ~07-09/10; Q13 needs ≥10 days of `tape/sports_pairs/` — only 7 (`dt=07-02`…`07-08`), BLOCKED, eligible ~07-12/13. Q14/Q15 re-probed live: CME FedWatch still 403 (Akamai bot wall), `KXHOUSE`/`KXSENATE`/`HOUSE`/`SENATE` still list 0 markets in any status, `ODDS_API_KEY` still absent — all stay BLOCKED. Lessons ledger and registry re-scanned: zero UNENFORCED rows, every idea-stage candidate already externally blocked. **No numbered queue item, lesson, or registry candidate was actionable this run.** Step 0b sweep: of 64 `tape/hourly-*`/`-corrected-`/`-followup-`/`-amended-` branches, 4 postdating the last clean sweep (`20260707T2356Z`, `20260708T0401Z`, `hourly-corrected-20260707T2059Z`, `hourly-followup-20260707T2055Z`, all >30min old) carried lines `main` lacked — real per-file line-set diff (not `git diff --stat`, unreliable for out-of-order JSONL), union-deduped **2,797 lines** total (10 crypto_hourly, 1,791 orderbook_depth, 75 polymarket_macro_pairs, 92 polymarket_pairs, 829 sports_pairs), every line JSON-validated, 0 exact dupes, appended into this run's commit; `hourly-amended-20260704T1455Z` re-checked, already fully reconciled. `git push origin --delete` not reattempted (same documented permission boundary). Gates: 362 tests green (tape-only commit, no code touched), `invariants --full` green. Sixth consecutive maintenance-only run; not a stall — recovering stranded tape from intermittent push-to-main failures while queue/lessons/registry wait on the same external clocks/walls as prior runs.
- 2026-07-08T05:30Z (research loop) · claim-check + comprehensive stranded-tape sweep only — queue still idle · `git fetch origin main` force-updated local ref to `ce310a2` (5 VPS hourly passes since the last run). Open PRs unchanged — #4 still claims Q1 (unrelated, awaiting `ODDS_API_KEY`, ~4d18h old, just under PR #18's proposed 5-day escalation mark — flagged to Ryan directly in this run's phone note), #18 is the retro's protocol-amendment proposal (left for Ryan). Tape day-counts recounted off disk: Q7 needs ≥7 days of `tape/crypto_hourly/` — only 6 (`dt=07-03`…`07-08`), BLOCKED, eligible ~07-09/10; Q13 needs ≥10 days of `tape/sports_pairs/` — only 7 (`dt=07-02`…`07-08`), BLOCKED, eligible ~07-12/13. Q14/Q15 re-probed live: `KXHOUSE`/`KXSENATE` still list 0 markets in any status, `ODDS_API_KEY` still absent — both stay BLOCKED. Lessons ledger re-scanned: zero live UNENFORCED rows (L22 stays resolved by L24). **No numbered queue item, lesson, or registry candidate was actionable this run.** Step 0b sweep went wider than recent runs' "postdating the last cutoff" heuristic: fetched and line-diffed all **69** `tape/hourly-*`/`-corrected-`/`-followup-`/`-amended-` branches against `origin/main` (not just the newest few) — 2026-07-03…07-06 branches confirmed fully reconciled (0 missing), but 07-07/07-08 carried a large backlog: **6,272 lines** union-deduped (16 crypto_hourly, 4,470 orderbook_depth, 120 polymarket_macro_pairs, 140 polymarket_pairs, 1,498 sports_pairs, 1 anomalies, 5 econ_prints, 22 polymarket_cpi_pairs), every line JSON-validated, 0 malformed, appended into this run's commit — the largest single-run recovery since collection began. `git push origin --delete` not reattempted (same documented permission boundary). Gates: pytest green, `invariants --full` green. Seventh consecutive maintenance-only run; not a stall. Worth watching: recovery size is trending up (1.7k→2.8k→6.3k across the last 3 runs), suggesting push-to-main failures are getting more frequent, not less.
- 2026-07-09T20:09Z · Q0b · egress unblocked — all 4 hosts now reachable (Kalshi 200, Coinbase 200, Kraken 200, the-odds-api 401=reachable-no-key); Q1–Q6 flipped BLOCKED(egress)→TODO.
- 2026-07-09T20:18Z · Q1 · built `collection/sports_pairs.py` + `core/sports_schema.py` + `core/odds.py` (18 new tests, all green); live pass captured 469 events/1079 outcome markets real_ask (4 World-Cup KXWCGAME events, bracket_sum 1.01–1.02); odds leg blocked_no_key (ODDS_API_KEY absent) → S7 data-collecting.
- 2026-07-10T00:22Z · Q2 · built `collection/crypto_hourly.py` + `core/crypto_schema.py` (14 new tests, all green, 85 total); live pass captured BTC (188 outcomes) + ETH (75 outcomes) hourly ladders paired with spot (Coinbase, synthetic) + prior-hour settlement (Kalshi expiration_value, broker_truth), spot/settle both `ok`; found naive full-ladder bracket_sum is inflated by far-OTM $0.01-floor brackets (BTC overround +2.99, ETH +1.22) — not comparable to weather's ~10¢ without a near-the-money filter, flagged for Q5 → S8 data-collecting.
- 2026-07-10T05:11Z · Q3 · Q1+Q2 dependency resolved so Q3 flipped BLOCKED→TODO and ran topmost; built `collection/hourly_pass.py` (10 new tests, all green, 105 total) orchestrating sports_pairs + crypto_hourly + conditional 09-UTC anomaly sweep, honest completeness_ok never faked True; live pass 1311 markets/455 lines completeness ok. Collector plumbing (Q1/Q2/Q3) complete; queue center of gravity moves to Q4/Q5 edge-testing.
- 2026-07-10T10:35Z · Q4(S7a) · built `scripts/sports_history_s7a.py` (16 new tests, all green, 121 total); live pass sourced 97 completed World Cup 2026 games / 291 outcome markets at real_ask candlesticks, matched 96/97 to football-data.co.uk's free closing-odds average (synthetic, de-vigged); confirmed last-season NFL fully unavailable from Kalshi's public API (settled markets purged after ~1 season) and NBA only partially available (36 playoff games, no odds leg yet) — documented, not a blocker. Q4 IN-PROGRESS, next stage runs S7b (Kalshi ask vs de-vig fair) on the World Cup dataset.
- 2026-07-10T15:16Z · Q4(S7b) · built `scripts/sports_clv_s7.py` (16 new tests, all green, 137 total); live pass over S7a's 97-game tape: 96 usable games, 167 candidate trades (decision_ts = close_time−4h, buy-YES when de-vigged fair > Kalshi bracket-normalized ask), mean net P&L −3.51¢/trade at real_ask after fee — negative point estimate, and a min-edge sweep (0.00/0.02/0.05 → −3.51¢/−9.30¢/−27.00¢) makes it monotonically worse, mirroring the S5 red flag. Not yet a verdict (no bootstrap run). Q4 IN-PROGRESS, next stage S7c runs the block-bootstrap by game → 95% CI → verdict.
- 2026-07-10T (local, Ryan) · RECONCILIATION · discovered main was rewound to 6cde523 on 2026-07-08T10:56Z (197 commits orphaned: 07-03→07-08 incl. PRs #4–#33); recovered pre-reset tip f23a491 via GitHub event log, merged post-reset 07-09/10 work into it (code conflicts → pre-reset lineage; post-reset tape/findings/core.odds kept). The five 07-09/10 lines above describe the post-reset lineage's duplicate rebuild — S7 stays DEAD per the 07-04 bootstrap verdict, independently corroborated by their S7b point estimate.
