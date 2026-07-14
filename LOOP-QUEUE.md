# LOOP-QUEUE — standing work queue for autonomous cloud runs

`protocol v3` · created 2026-07-02 (v1) · v3 2026-07-12 (Fable handoff, Ryan-approved
interactive session) · owner: Ryan Gillon

This file is the coordination bus for the cloud loop system:

- **kalshi-research-loop** (every 3 h since 2026-07-12; was 5 h, Sonnet 5): executes ONE
  milestone from the queue below.
- **kalshi-edge-hunter** (nightly ~04:15 UTC, Opus — added 2026-07-12): the thinking seat.
  Idea generation (Q21-class), adversarial review of the day's findings, probe-prep for
  upcoming gates, and the daily plain-English brief (incl. paper P&L once shadows exist).
  It may add queue items and findings; it NEVER flips a verdict without the two-agent rule.
- **kalshi-collector** (hourly, Haiku): runs `python -m collection.hourly_pass` if it exists;
  nothing else, ever.

**Standing approval.** For a cloud run, executing the topmost eligible queue item under this
protocol IS the approved plan — do not wait for interactive approval (CLAUDE.md's plan-first
rule is satisfied by this file). Everything else in CLAUDE.md binds unchanged, especially:
research + data collection + the sanctioned **paper tier** of `execution/` ONLY (see the
2026-07-12 Stop-rules amendment — demo/live tiers are NOT cloud-runnable), the real-ask bar,
source tags on every persisted price, invariants green before commit.

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
   research run: `git ls-remote --heads origin 'refs/heads/tape/hourly-*' 'refs/heads/tape/burst-*'`
   (`burst-*` added 2026-07-10 — the burst legs below use the same fallback mechanism); for each such
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
   **(v3, 2026-07-12) Idle-run policy:** if NO item is eligible, the run is an IDLE RUN and
   must still produce one unit of real work, chosen in this order: (a) convert an UNENFORCED
   lesson from `kb/lessons/00-lessons.md` into an invariant/test; (b) write + offline-test
   the probe script for the NEXT time-gated queue item so it fires the day its gate opens;
   (c) a data-quality deep-dive on one tape family (gaps, drift, join-ability — one finding);
   (d) idea-gen prep for Q21 (observations memo from accumulated tape, no registration).
   The step-0b sweep still runs, but "sweep only" is no longer a valid run outcome.
4. Gates before ANY commit: `pytest` green AND `python scripts/invariants.py --full` green.
5. Bookkeeping: update the item's Status line in this file; append one dated entry to
   `kb/00-LOG.md` (match its existing format); findings → `findings/`; strategy status
   changes → `kb/strategies/00-index.md`; append one line to "Log of runs" below.
   **(v3, 2026-07-12) Two-agent verdict rule (codifies what the S10/S6 verdicts already
   practiced):** any verdict-class change — a registry status flip, a bootstrap CI destined
   for `kb/`/`findings/`, a kill decision — requires TWO agents: the producer (edge-prober
   or main context) AND an independent `verifier` re-run that CONFIRMS before commit. A
   verdict without verifier confirmation may only be committed as `PROVISIONAL` and must not
   flip the registry. (Fable's oversight is gone; redundancy replaces it.)
6. Git: commit (message conventions from history: `build:` / `probe(Sx):` / `tape:` /
   `docs:`) on your own branch, push it, then open a PR against `main` (`gh`/GitHub MCP —
   do NOT attempt `git push origin main`, it will not succeed from a cloud session). If gates
   (step 4) are green and the diff is research/data/paper-tier-only — no execution code
   outside `execution/`'s sanctioned paper tier (2026-07-12 Stop-rules amendment), no
   demo/live order paths, no credential handling (Stop rules forbid these, so this is a
   re-check, not a new bar) — **merge the PR immediately** (squash) so `main` is current for the next firing. If
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

8. Phone note (all legs — research loop, cloud collector, VPS collector, weekly retro, burst
   legs; added 2026-07-03). Best-effort, never blocks a run: POST one plain-English summary a
   non-programmer understands (no jargon, SHAs, or ticker codes) to the leg's ntfy URL
   (supplied privately per the 2026-07-10 topic migration in (e) below; formerly the URL in
   `config/notify.topic`) via `curl -s -m 10 -H 'Title: <leg name>' -d '<text>'`. Hourly
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
   **(e) Topic migration (2026-07-10, Ryan-approved public-repo hardening):** the ntfy topic
   is no longer stored in this repo. The repo went public on 2026-07-10 and ntfy.sh topics
   are world-readable AND world-writable — a committed topic name lets anyone inject
   priority-5 messages that the `ntfy-watch` responder would investigate. Each cloud leg's
   routine prompt now carries the URL directly (private to Ryan's account); the VPS leg reads
   `NTFY_TOPIC_URL` from `/root/.secrets/kalshi-headless.env`; Ryan's local sessions read
   `~/.claude/secrets/kalshi-ntfy-topic`. `config/notify.topic` holds only the OLD, retired
   topic as a temporary fallback until the VPS is flipped, after which it gets deleted —
   nothing reads it for action anymore (`ntfy-watch` polls the new topic only). NEVER commit
   the new topic name to any file in this repo, any PR, or any run's final message.

9. **Paper sub-pass (v3, 2026-07-12).** If `execution/strategy_api.SHADOW_REGISTRY` is
   non-empty: advance `execution/paper_broker.PaperBroker` over tape appended since the
   ledger's last entry (deterministic replay — same tape, same ledger, same state), append
   the resulting ledger lines under `paper/` in your commit, and include the broker's
   one-line `daily_summary()` in the run digest and the phone note. An empty registry makes
   this step a silent no-op. Paper results are evidence, not verdicts: a shadow's track
   record feeds the live-gate criteria (Stop rules amendment) but never flips a registry
   status by itself.

## Stop rules (non-negotiable)

- NEVER touch credentials, never place a trade. Capital requires an in-person sign-off from
  Ryan that no cloud run can obtain — by design.
  **Amendment (2026-07-12, Ryan-approved interactive session — the paper-harness decision):**
  "never write order/execution code" is replaced by a three-tier lane under `execution/`:
  - **paper** — pure simulation over committed tape; no order ever leaves the process; no
    network calls. Cloud runs MAY build, extend, and run it. Every paper fill carries
    `fill_model` + `price_source_tag` (a fill against a `synthetic` price is forbidden);
    the ledger is append-only JSONL under `paper/`, committed like tape.
  - **demo** — Kalshi demo-API orders. VPS/local only; NOT cloud-runnable. Not built yet.
  - **live** — real orders. Requires ALL of: (1) block-bootstrapped real-ask CI > 0,
    (2) ≥14 days of shadow-paper track record consistent with the backtest, (3) a
    per-strategy `LIVE-AUTH.md` signed by Ryan in person, (4) a bankroll cap + kill switch
    from `execution/limits.py` (the single sanctioned caps site), (5) credentials that exist
    ONLY on the VPS/local — cloud sandboxes never receive them. Authenticated/order
    endpoints may exist ONLY in `execution/kalshi_client.py` (unbuilt until graduation is
    near). Live trading therefore stays structurally impossible for autonomous cloud runs.
- An edge is "proven" ONLY by a block-bootstrapped 95% CI strictly > 0 at `real_ask` prices
  net of fees. A DEAD verdict is a success — record it honestly and move on.
- Never relax an invariant, never delete or reorder queue items; append, don't rewrite.
- Timebox: if a milestone isn't converging, commit honest partial state with an
  IN-PROGRESS note rather than forcing a result.

## Subagent roster (added 2026-07-06, ops — Ryan-requested)

`.claude/agents/` now defines a project agent team: an **Opus lead on high reasoning**
(`research-lead` — plans, decomposes, reviews; never edits files itself; was Fable-class
until Fable's retirement 2026-07-12) guiding five
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

## Burst-capture legs (added 2026-07-10 — Ryan-approved, interactive session)

The S9 lead-lag resolution (`findings/2026-07-06-polymarket-leadlag-s9-resolution.md`)
identified sub-hourly event-window captures as a new automation class that needed Ryan's
sign-off; that sign-off was given 2026-07-10. Five ONE-SHOT cloud triggers now exist
(created via the trigger API — they live in Ryan's account, not this file):

| trigger | event | window (UTC) | families / interval |
|---|---|---|---|
| `kalshi-burst-cpi-0714` | June CPI print (12:30Z release) | Jul 14 12:05→13:45 | econ,cpi,fed,crypto @60s |
| `kalshi-burst-wcsemi1-0714` | WC semifinal 1 (19:00Z kickoff) | Jul 14 20:10→22:30 | wc @120s |
| `kalshi-burst-wcsemi2-0715` | WC semifinal 2 (19:00Z kickoff) | Jul 15 20:10→22:30 | wc @120s |
| `kalshi-burst-wcfinal-0719` | WC FINAL (19:00Z kickoff) | Jul 19 20:10→22:45 | wc @120s |
| `kalshi-burst-fomc-0729` | FOMC decision (18:00Z statement) | Jul 29 17:40→19:45 | fed,econ,crypto @90s |

Each runs `python -m collection.burst_capture --until <end> --interval <s> --families <list>`
— a thin loop over the existing collectors' one-pass functions (no new tape family, no schema
change; burst lines are distinguishable downstream purely by `fetch_ts` density), commits
tape ONLY (`tape: burst <slug> <ts>`, fallback branch `tape/burst-*`, swept by step 0b),
posts a step-8 phone note, and carries a hard date guard so the cron's annual re-fire is a
no-op. Burst runs obey every Stop rule: they collect, they never analyze, never trade. The
point: this is exactly the data class whose absence killed S9's lead-lag test — S17's
lead-lag question (who reprices first around a macro shock, Kalshi or Polymarket?) becomes
testable on this tape. After each event the trigger should be disabled/deleted (weekly retro
or Ryan); a fired one-shot left enabled is harmless but untidy.

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
Status: DONE (2026-07-11) — **verdict DEAD (structural).** `tape/crypto_hourly/` crossed 7
valid canonical `dt=<date>.jsonl` days (03,04,05,06,07,08,10 — confirmed by file, not path,
per L25) this run, unblocking the item. Built `scripts/s10_reachability_probe.py` (16 new
unit tests, 432 total green): joined each hourly group's early/late `real_ask` captures
(multi-capture groups from overlapping cloud+VPS collector legs) against the next-hour pass's
`broker_truth` settlement. Found: far out-of-the-money brackets are already pinned at the 1¢
YES-ask floor at the EARLY capture (~30–48min pre-close) — no decay window exists to measure.
The mirrored NO-ask sits at $1.00 on those brackets (`yes_bid=0`), and
`core.pricing.fee_per_contract(1.00)==0` is genuinely correct — so the taker fade this gate
asked about has no fillable positive-EV price at all (0.02% of 18,992 far observations had
any room, 3 of those 4 from a single hour). Block-bootstrap by HOUR (10,000 resamples, seed
42, n=164 hours): mean +$0.000008, 95% CI **[+$0.000000, +$0.000024]** — three orders below
the 1¢ tick, unfillable rounding residue, not an edge. Adversarially verified (CONFIRMED, not
just plausible) by the `verifier` agent — re-ran the script independently, checked the
settlement join, the fee math, the cluster-bootstrap correctness, and the far-bracket
threshold sweep (no threshold clears zero; relaxing it goes negative). `kb/strategies/
00-index.md` S10 flipped idea → dead ✗. See `findings/2026-07-11-crypto-reachability-s10-firstcut.md`.
**Untested, out of scope for this verdict:** the maker side (rest a NO offer / sell the rich
YES instead of crossing at the $1.00 NO ask) is a different trade, S6/S11 territory, needs L2
depth + fill-sim.
Original spec below, unchanged.
Status (history): BLOCKED(needs ≥7 days of Q2 tape)
**Note (2026-07-10):** `tape/crypto_hourly/` shows a `dt=2026-07-10` path that looks like a
7th day but is a **directory** of raw unreadable blobs (a tape-format regression from the
2026-07-08 main-rewind's rebuilt collectors, self-corrected but not yet backfilled — see
`findings/2026-07-10-tape-format-regression-crypto-sports.md`), not a usable day of tape.
Still only 6 valid canonical `dt=<date>.jsonl` days (03–08). Day-count checks for this item
MUST confirm the `dt=<date>` entry is a file, not just that the path exists (kb/lessons L25).
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
Status: DONE (2026-07-06); **lead-lag first cut added 2026-07-12** — no numbered queue item
was eligible this run (Q1 claimed by open PR #4; Q7/Q9/Q16 DONE; Q13 BLOCKED — 9 of ≥10 valid
`tape/sports_pairs/` days, eligible ~07-13; Q14/Q15 data-adequacy BLOCKED), so this run drew on
Q12/S17's own "remaining work" note (accumulate snapshots, then a lead-lag cross-correlation
once enough history exists, same shape as S9) via the `edge-prober` subagent. Built
`scripts/s17_leadlag_probe.py` (S9's `s9_leadlag_probe.py` pattern, adapted to the
`polymarket_macro_pairs` Fed-decision schema — both sides `real_ask`) and ran it read-only over
~6 days of tape (2026-07-06→07-12): 2,805 records / 187 captures / 15 (meeting,bucket) pairs.
Pooled panel cross-correlation of consecutive-capture deltas: contemporaneous ρ=+0.154
(n=2,789), kalshi-leads ρ=−0.003, polymarket-leads ρ=−0.028 (n=2,774 each); 215 ≥1¢ moves;
**0 FOMC resolve/roll-off (shock-proxy) events in window** — no real meeting has occurred
inside the collected window yet, so every tick observed is book noise, same data-adequacy gap
S9 hit before its own eventual resolution. Reported as a descriptive noise-floor
characterization, explicitly NOT a verdict (no CI, no DEAD/ALIVE call). The CPI leg
(`tape/polymarket_cpi_pairs/`) is `synthetic` on the Kalshi side (a derived cumulative-ladder
difference, not a fillable price) and was deliberately excluded from the real-ask correlation
per Hard Rule #3 — counted for provenance only. `kb/strategies/00-index.md` S17 note updated
(dated append, stays `data-collecting`). See
`findings/2026-07-12-polymarket-macro-leadlag-s17-firstcut.md`. 507 tests green (481 prior +
26 new), `invariants --full` green. Remaining: re-run once a real FOMC decision (nearest: July
2026 meeting) or CPI print lands inside the collected window.
Status (history): DONE (2026-07-06, later run) — **CPI/inflation leg built**, closing the only
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
Status: DONE (2026-07-13) — S14 idea → data-collecting, proxy-CI +\$0.093 [+0.063,+0.123] n=300 event-hours (candlestick fill-proxy over `tape/crypto_hourly/` BTC/ETH ladders), verifier CONFIRMED-WITH-CAVEAT — PROXY-POSITIVE not proven (complete-fill term \$0; 78% of edge from sub-100-vol income legs); needs a queue-aware L2/depth fill-sim before any real-ask graduation. Still 0 proven edges. See `findings/2026-07-13-ladder-underwriting-s14-firstcut.md`.
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
Status: DONE (2026-07-11, later run) — **S6 first-cut verdict: DEAD**, verifier-CONFIRMED.
No numbered queue item was eligible this run (Q13 still BLOCKED — needs ≥10 days of
`tape/sports_pairs/`, eligible ~2026-07-13; Q14/Q15 still data-adequacy BLOCKED; Q1 claimed by
open PR #4) — drew on S6's own "remaining work" note below via the `edge-prober` subagent.
Built `scripts/s6_maker_firstcut.py` (15 new tests, 453 total) over 4 accumulated days of
`tape/orderbook_depth/` (~58K records): an L28-style precheck first (69.7% of consecutive
same-ticker snapshot pairs are frozen — no fill, correctly booked as $0, not phantom spread
income), then a by-ticker block bootstrap (10,000 resamples) of net maker P&L across
fillability-filtered spread populations. Every economically realistic cut (tight ≤10¢ spreads,
both frozen-inclusive and movement-conditioned) came back strictly negative (e.g. primary
≤10¢ frozen-inclusive: mean −$0.00195, 95% CI [−$0.00297, −$0.00094]). The naive "ALL
two-sided" population looked alive (+$0.069) but is a wide (>30¢) one-sided wing-bracket
artifact, not a real edge. Structural kill: Kalshi's maker fee is a FLAT $0.01/contract at
every interior price (`ceil(0.0175·P(1−P)·100)/100 = 0.01 ∀ 0<P<1`, since max `P(1−P)=0.25`),
consuming the modal 1–2¢ two-sided spread before adverse selection is even charged — the same
fee-floor mechanism that killed S13. Adversarially reviewed and **CONFIRMED** by the `verifier`
subagent: independently reproduced every number exactly, swept additional thresholds
(≤15/20/25/30¢) trying to find an alive population, confirmed the only CI>0 cut (≤30¢
frozen-inclusive, +$0.00229) fails lesson L27's magnitude-vs-tick gate and is itself a wing
artifact — under the honest movement-conditioned cut every threshold tested is strictly
negative. More days of the SAME hourly-cadence tape will not resurrect this (structural, not
sample-size). `kb-distiller` subagent compounded: `kb/strategies/00-index.md` S6 flipped
`data-collecting → dead ✗`; 3 lessons appended (L30 flat-maker-fee, L31 wing-spread artifact,
L32 frozen-pair-no-fill). See `findings/2026-07-11-mm-spread-s6-firstcut.md`. 453 tests green,
`invariants --full` green. **Untested/out of scope:** S11 (sharp-anchored maker quoting) is a
distinct hypothesis (external EV+ filter, not a bare spread-capture) and is NOT falsified by
this verdict — remains the un-falsified S6-adjacent successor, but needs a free real-time
sharp-odds anchor this run doesn't have (same key gap as Q1).
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

### Q17 — (number reserved) stranded-sweep-growth diagnosis, filed by weekly retro PR #46
Status: RESERVED for PR #46 (open, Ryan-review-only per the retro charter). The question it
files was independently answered the same day by `findings/2026-07-12-stranded-tape-sweep-
growth-diagnosis.md` + lesson L38 ("not a real problem" — growth tracks collector volume,
recovery is lossless). When Ryan merges #46, flip its Q17 to DONE citing that finding; if he
closes #46 instead, this placeholder stands as the tombstone. Do not start work on it.

### Q18 — Odds-leg matching activation (S11's anchor) — TIME-SENSITIVE: quota burn + WC ends Jul 19
Status: DONE (2026-07-13, research loop) — **live confirmation landed, verifier-CONFIRMED.**
The first keyed VPS pass after the Q18 port (`20260712T212303Z`, commit `6b6938d`, ~3h after
the `5b265a3` merge) wrote `odds_leg.status="matched"` records: **6 matched lines** across 3
VPS passes (`20260712T{212303,222302,232302}Z`) × 2 World Cup games (France v Spain, England v
Argentina) — `match_score=2.0` (max), `outcome_coverage="full"`, de-vig `fair_prob` sums to
1.000000 and reproduces `(1/decimal_odds)/Σ(1/decimal_odds)` to 6dp, `book_overround` matches
`Σ(1/decimal_odds)−1` to 6dp, Kalshi legs correctly tagged `real_ask`/`real_bid`, odds legs
correctly tagged `synthetic` (Hard Rule #3 respected). `git blame` confirms this is the FIRST
appearance of `status="matched"` anywhere in the tape — not backfilled. Independently
re-derived and confirmed by the `verifier` subagent (two-agent rule satisfied) before this
flip. `kb/strategies/00-index.md` **S11: idea → data-collecting** (data-flow milestone only —
no P&L/CI claim; still thin, 1 bookmaker/2 games/3 passes). See the verifier's full report in
this run's `kb/00-LOG.md` entry. Q18 CLOSED.
Status (history): IN-PROGRESS (2026-07-12, research loop) — **milestones (1)-(4) landed; live
confirmation pending.** Diagnosis: the matching layer was never a "burns quota and fails" —
it was a hardcoded literal (`{"status": "unmatched"}` whenever a key was present), so the
odds-api HTTP endpoint was **never actually called**; the 7,476 `"unmatched"` VPS records
since key-day represent zero attempted matches, not zero successful ones (quota was NOT
being burned, contrary to this item's original framing). Ported PR #4's already-built
matching layer (`collection/odds_api.py`: kickoff-primary + team-name-fallback matching,
Pinnacle-first bookmaker selection, honest per-game statuses, built-in quota discipline —
`ODDS_API_QUOTA_FLOOR`/`DEFAULT_SPORTS` scoping/quota-header persistence) onto current
`main` by hand (PR #4's branch had diverged ~10,000 files and wasn't mergeable; its
`validation/v3_market.py` diff was deliberately NOT ported — main has since grown methods
that stale diff would have deleted). `sports_pairs` schema → v2: `game_start` +
per-outcome `outcome_name` now persisted even keyless. 26 new/changed tests, 630 total
green, `invariants --full` green. Live keyless smoke (no `ODDS_API_KEY` in this cloud
sandbox, by design): 114/114 real Kalshi moneyline games captured complete with v2 fields
populated correctly (tape not committed — code-only change). PR #4 commented + closed as
superseded. **Not yet confirmed:** the actual match-against-real-odds-api-events path is
unit-tested only (no key here to live-smoke it) — success condition unchanged: the next
keyed VPS pass must write ≥1 `odds_leg.status="matched"` record. S11 stays `idea` in the
registry; flips to `data-collecting` only on the run that confirms a matched record in
committed VPS tape. See `findings/2026-07-12-odds-leg-matching-activation-q18.md`.
Status (history): TODO (added 2026-07-12, Ryan-approved v3 restock)
The `ODDS_API_KEY` went live on the VPS 2026-07-10, but the odds leg has produced **zero
matched records** since: 2026-07-11/12 tape shows 7,476 `odds_leg.status="unmatched"` (VPS
passes, key present) + 5,958 `"blocked_key"` (cloud passes, key absent by design — expected).
The event-matching built in PR #4 (kickoff-primary matching, `collection/odds_api.py`) never
reached main; main's matcher matches nothing while burning free-tier quota (500 req/month,
hourly VPS passes). Milestone: (1) diagnose WHY every VPS attempt is unmatched (read a raw
odds_leg record + the matcher in `collection/sports_pairs.py`; likely the matching layer is
a stub or key-presence gates a codepath that never joins); (2) port PR #4's kickoff-primary
matching (or build equivalent) onto CURRENT main with offline fixture tests; (3) add quota
discipline: ≤1 odds-api call per pass via the batched sports endpoint, skip when no
soccer/major-league Kalshi market is live, record `quota_remaining` from response headers
into the tape line; (4) after landing, comment on + close PR #4 as superseded. Success =
next VPS pass writes ≥1 `odds_leg.status="matched"` record with de-vigged `synthetic` fair
+ raw odds, or an honest finding explaining why zero matches is structurally correct (e.g.
the-odds-api soccer coverage vs Kalshi's current sports set). S11 flips to data-collecting
only when matched pairs flow.

### Q19 — S17 burst-event studies (lead-lag + dislocation scan) — TIME-SENSITIVE: CPI Jul 14, FOMC Jul 29
Status: PREP DONE (2026-07-13, edge-hunter) — per-event runs remain TODO (fire as each burst
tape lands). Built `scripts/s17_leadlag_probe.py --burst-window START END [--poly-fee F]`
(read-only, additive): window isolation + cadence-honesty check, per-ticker SIGNED lead-lag,
fillable cross-venue dislocation scan (buy cheap-venue real ask / sell rich-venue real bid net
of BOTH fees — Kalshi taker both legs via `core.pricing.fee_per_contract`, Polymarket ~0 an
explicit tagged assumption `--poly-fee`), and a dislocation width×duration distribution. 17 new
offline tests (43 total), 621 pytest green, `invariants --full` green. Smoke over hourly tape
(flagged NOT burst-cadence) surfaced 616 candidate dislocations persisting hours-to-days (~$0.04)
— the stale/nominal-quote artifact signature (S6/L31), NOT an arb; a REAL shock dislocation
should be short-lived, and width×duration is the discriminator the burst run applies. See
`findings/2026-07-13-s17-burst-mode-prep-q19.md`. **PER-EVENT (still TODO):** run `--burst-window`
on each event's tape the run after it lands → `findings/<date>-s17-burst-<event>.md`, two-agent
rule on any tradeable claim; S17 kill/live decision AFTER the FOMC event.
Status (history): TODO (added 2026-07-12, Ryan-approved v3 restock; PREP eligible immediately,
per-event analysis fires as each burst tape lands)
The five one-shot burst triggers (see "Burst-capture legs") deliver 60–90s-cadence cross-venue
tape around June-CPI (Jul 14 12:30Z), WC semis (Jul 14/15), WC final (Jul 19), FOMC (Jul 29).
This is exactly the data class whose absence killed S9's lead-lag test, and S17's first cut
(`findings/2026-07-12-polymarket-macro-leadlag-s17-firstcut.md`) was descriptive-only because
no shock fell inside the hourly window. Milestone(s), one per run: **PREP (eligible now):**
extend `scripts/s17_leadlag_probe.py` with a burst-mode entry point (`--burst-window <start>
<end>`) that isolates high-`fetch_ts`-density segments, aligns Kalshi vs Polymarket capture
pairs at 60–120s resolution, and computes (a) who reprices first (signed lead-lag by venue,
per ticker), (b) fillable dislocation scan: moments where buying the cheap venue's `real_ask`
and selling the rich venue's `real_bid` clears BOTH venues' fees (use each venue's real fee
schedule; Polymarket fee ≈ 0 but document the assumption with a source tag), (c) dislocation
width × duration distribution. Offline tests on synthetic burst fixtures. **PER-EVENT (fires
the run after each burst lands):** run it on that event's tape → one finding per event
(`findings/<date>-s17-burst-<event>.md`), two-agent verdict rule if any tradeable claim is
made. S17's kill/live decision comes AFTER the FOMC event (the highest-liquidity shock of
the five).

### Q20 — BTC fine-ladder overround anatomy (feeds S14's crypto leg)
Status: DONE (2026-07-13, research loop) — **anatomy only, no registry flip** (per this item's
own spec), verifier CONFIRMED-WITH-CAVEAT. `scripts/s20_ladder_overround_anatomy.py` (22 offline
tests) decomposed the overround over 629 crypto_hourly snapshots (KXBTC 316/KXETH 313, 172
settled event-hours each): **97.4% (BTC) / 84.3% (ETH) of the overround sits in wings**, split
between 1¢-floor pins AND stale one-sided `wing_elevated` asks (on BTC the latter, $2.17,
actually exceeds the floor pins, $1.71 — a second artifact component L12 didn't name). Depth
join (`tape/orderbook_depth/`, 328/629 snapshots join-eligible) **REFUTES "wings are quote-only"**
— floor wings rest median 22,768 (BTC) / 36,253 (ETH) contracts; they carry no edge because the
flat $0.01 maker fee eats a 1¢ ask (L30), not from lack of size. Active-band
`Σyes_ask − 1 − maker_fees`, block-bootstrapped by event-hour (n=172, 10k resamples): **BTC
+0.0087 CI [−0.0036, +0.0215] — fails the magnitude gate, no edge**; **ETH +0.1271 CI
[+0.1046, +0.1523] — statistically positive but EXPLORATORY**, deferred to S14's existing
queue-aware fill-sim gate (the active-band mids themselves sum >1.0, a heuristic tell — not a
theorem — that this is nominal ask-width in a thin book, per the verifier's decomposition). S14
parameter block emitted (band width, quote prices, nominal expected capture), tagged unproven.
Verifier re-derived every load-bearing number independently (exact match) and instrumented the
join staleness (p99 34.8s, max 165.6s — sound); one causal wording (ETH mid-sum attribution) was
corrected per the verifier's caveat before commit. See
`findings/2026-07-13-btc-ladder-overround-anatomy-q20.md`. 664 tests green (642 prior + 22),
`invariants --full` green.

### Q21 — Idea-generation round: S19+ candidates (standing replenishment item)
Status: ROUND COMPLETE (2026-07-14, research loop) — re-eligibility trigger fired (queue drained
to 0-1 non-blocked research items: Q19's per-event legs are time-gated on the Jul-14 CPI burst
tape, everything else DONE/DEAD/BLOCKED/RESERVED). Delegated to `research-lead`, which proposed
**3 falsifiable candidates and ran each through independent `verifier` review** (two-agent rule) —
**REGISTER on all 3, 0 killed at idea stage** (proposed only what was judged defensible rather
than padding to quota). Survivors: **S22** (OFI/depth-imbalance settlement predictor on Q25's
high-churn two-sided sports cells — satisfies the diversity floor: drawn from the Q25 depth-anatomy
scan + a newly-distilled paper, Cont/Kukanov/Stoikov 2014, `kb/quant-finance/order-flow-imbalance.md`
— neither a dead-verdict inversion nor an S11/S12/S14/S17 family), **S23** (favorite-side
settlement-underpricing maker, favorite-longshot bias with NO devig/odds-api dependency — the
design choice that sidesteps S21's L43 join-emptiness death), **S24** (near-close hourly-return
overreaction fade, weakest of the three, explicit anti-overlap guard vs S22). Queue items
**Q26/Q27/Q28** added below. New lesson **L50** (settlement-leg-sourced-over-the-depth-tape's-own-
window as the general fix for S21-style disjoint-join deaths). Still 0 proven edges — this restocks
the hypothesis pipe by three idea-stage candidates, the bar hasn't moved. Item stays STANDING per
its own re-eligibility condition below (do not treat "complete" as permanently done).
Status (history): ROUND COMPLETE (2026-07-13, research loop) — delegated to `research-lead`, which
proposed 4 falsifiable candidates and ran each through the `verifier` agent (two independent
verifier passes on the two contested ones — real two-agent redundancy, not a rubber stamp).
**1 survivor registered: S19** (elevated-wing stale-ask maker fade on crypto ladders — the
S10-maker/L26 direction Q20's ladder anatomy fed directly into), queue item **Q23** added,
Status: TODO. **3 killed at idea stage** (sports-moneyline overround underwriting — L31
wing-artifact, S13/L30 flat-fee death, duplicate of S14's gate; a cross-venue held-to-settlement
box — Polymarket NO-ask not in tape, reduces to Q19's already-queued dislocation scan and its
L31 artifact; a post-release econ-ladder fade — Kalshi closes CPI/econ markets ~5min BEFORE the
print, structurally empty fill window), recorded with reasons in the `kb/strategies/00-index.md`
S19 note rather than silently dropped. Still 0 proven edges — this restocks the hypothesis pipe
by one idea-stage candidate, the bar hasn't moved. Item stays STANDING per its own
re-eligibility condition below (do not treat "complete" as permanently done).
Status (history): TODO (added 2026-07-12, Ryan-approved v3 restock — STANDING: re-eligible whenever
fewer than 2 non-blocked research items remain in this queue)

**Spec amendment (2026-07-13, Ryan-approved local session — from that session's pipeline
audit of the run logs):** (1) **Re-eligibility trigger raised to "fewer than 3 non-blocked
research items"** — at 3h cadence the loop drained a 6-item restock in 18 hours; waiting
for <2 guarantees idle runs before the next round lands. (2) **A round's target is 3–5
registered survivors, not 1** — the 07-13 round registered a single candidate whose own
honest expectation was DEAD (a closer; fine, but closers don't restock the pipe). If the
verifier honestly kills down to fewer, register what survives and say so — never pad to
quota. (3) **Diversity floor: every round must include ≥1 proposal NOT derived from (a) a
dead-verdict inversion or (b) the existing QF themes** — drawn instead from depth-tape
anomaly/anatomy scans (Q25), settlement/close-time mechanics, or literature not yet in
`kb/quant-finance/` (a new-literature candidate cites its paper and distills it into `kb/`
as part of the round). Rationale: every currently-alive candidate came from interactive
gen passes; the loop's own input distribution hasn't widened since 2026-07-04 — the audit
found generation quality, not cadence or verification, is the binding constraint.
(4) **L41 gate mandatory in every proposal's probe spec:** any bootstrap verdict must pass
`core.bootstrap.bootstrap_verdict_admissible` (≥1 opposing-sign cluster, ≥10 units)
alongside the L27 magnitude gate — a CI failing either is not-a-verdict by construction.

The alive set has collapsed to S17 + slow gates (S6 and S10 died 2026-07-11/12; S2 gated on
CME data, S12 on ~20 releases, S3/S15 on 60-day sweeps). The machine must replenish its own
hypothesis pipe. One round = propose 3–5 NEW falsifiable candidates (S19+), each with: (a) a
named mechanism (who is the counterparty and why do they lose), (b) a data source that is
already-collected tape or free, (c) a falsifiable gate + kill condition, (d) an explicit
"why this survives what killed its nearest dead cousin" paragraph — anything paying taker
into overround-heavy books is presumptively dead (S1/S5/S7 precedent); anything needing
sub-hourly resolution must cite burst-class tape (S9 precedent); anything assuming maker
fills are free must cite a fill model (S13 precedent). Sources to mine: dead-strategy
postmortems in `findings/`, the lessons ledger, anomaly-sweep tape, the S10 finding's
"maker side untested" note, cross-venue gap distributions. The `verifier` agent reviews
every proposal BEFORE registration (two-agent rule applies to the candidate set); survivors
get registered in `kb/strategies/00-index.md` + a queue item here. The nightly edge-hunter
leg owns this item by default; a research run may take it when eligible.

### Q22 — Paper-harness shadow wiring (after the 2026-07-12 spine)
Status: DONE (2026-07-13, research loop) — **first-ever shadow strategy wired and run.**
Q13's S14 parameter block (short-YES maker offer at every `crypto_hourly` ladder member's
`yes_ask >= $0.02`, earliest capture of each settled event-hour) is now `execution/strategies/
s14_ladder_underwriting.py`, registered in `SHADOW_REGISTRY`. Found and closed a real
architectural gap first: `PaperBroker` had no short-position model AND no settlement/expiry
realization mechanism (`Fill.price` is hard-bounded to `[0.01,0.99]`, so a $1.00/$0.00 expiry
value could not even be recorded). Fixed via (a) representing "short-YES at ask A" as
"buy-NO at `round(1-A,2)`, held to settlement" — economically identical cash flows, proven
cent-for-cent by an executable reconciliation test against the already-verified
`s14_ladder_fillsim.simulate_event`; (b) a new `Settlement` record type (sibling of `Fill`,
`settle_value` restricted to exactly `{0.0,1.0}`, tag fixed to `broker_truth`) so `Fill`'s
honesty bound was never loosened. New `scripts/paper_pass.py` (no network) drives the
registry over committed tape; per-event idempotency is derived from ledger content (no side
state file). First real pass over `tape/crypto_hourly/` + the committed `tape/
s14_ladder_fillsim/` candle cache: **10 event-hours processed → 200 orders / 89 fills / 89
settlements**, `daily_summary()`: `paper: 0 open position(s), 89 settled contract(s), realized
P&L $+1.83, cash $+1.83, open notional $0.00`. **290 deferred(caps)** — `MAX_DAILY_ORDERS=200`
bit exactly as expected on this first backlog-clearing pass (drains ~200/day on subsequent
runs, caps were NOT raised); **14 deferred(coverage)** (candle cache doesn't cover every
member yet). Re-run confirmed idempotent (0 newly processed, same $+1.83). **This is evidence
accumulation, not a verdict** — S14 stays `data-collecting`/PROXY-POSITIVE in the registry,
unchanged by this milestone; the $+1.83 is a 10-event slice, not a CI. 26 new tests (690 total
green), `invariants --full` green. Two-agent rule not triggered (no registry flip/bootstrap
CI/kill decision — this is infrastructure), but reviewed independently by the orchestrating
context (full code read, own pytest/invariants run, ledger JSON validated, reconciliation
re-verified) before commit, after an initial delegation stalled without producing files and
had to be re-driven.
Original spec below, unchanged.
Status (history): TODO (added 2026-07-12, Ryan-approved v3 restock; BLOCKED-in-part until Q13/Q19/Q20
emit parameter blocks)
The paper tier spine (`execution/` — schema, fill models, paper broker, strategy API, limits;
built 2026-07-12 in the Ryan-supervised session) ships with an EMPTY shadow registry.
Milestone: when Q13 (S14 ladder underwriting), Q19 (S17 dislocations), or Q20 (S14-crypto
band) produces a parameter block, implement that strategy against
`execution/strategy_api.Strategy`, register it in `SHADOW_REGISTRY`, and wire the paper
sub-pass (protocol step 9) so every research run advances the broker over new tape and the
digest carries a paper-P&L line. Shadow track records are the graduation evidence the live
gate requires (≥14 days consistent with backtest). Paper fills obey every honesty rule:
`fill_model` + `price_source_tag` on every fill, no synthetic fills, caps from
`execution/limits.py`.

### Q23 — S19 elevated-wing stale-ask maker fade (the S10-maker / L26 untested direction)
Status: DONE (2026-07-13, research loop) — **verdict DEAD, verifier-CONFIRMED.**
`scripts/s19_wing_fade_fillsim.py` (+22 unit tests, offline/synthetic) ran the binding
queue-aware `orderbook_depth` `no_bids` fill-sim (not an L39 candlestick print) over 895
`wing_elevated` members / 175 settled event-hours: 0.45% fill rate overall (4 fills, 1.00%
among 402 joinable) — below S14's 2.5% incidental-wing benchmark and the near-zero-fill
kill floor; the filled population is only 2 event-hours, below the bootstrap's
data-adequacy floor, so the +$0.355 win-leg CI [+0.285,+0.425] is a resampling artifact,
not a testable edge (0/895 wings ever settled YES — the mechanism's predicted toxic leg is
unsampled, not disproven). S10-maker / L26 converted from untested to tested-dead.
`kb/strategies/00-index.md` S19 flipped `idea` → `dead ✗`. See
`findings/2026-07-13-s19-wing-fade-fillsim-q23-verdict.md`. Still 0 proven edges.
Status: TODO (added 2026-07-13, Q21 idea-gen round — verifier-reviewed survivor, two-agent rule)
S10 died as a TAKER trade (a floor-pinned far tail's 1¢ YES mirrors to a $1.00 NO ask — no
fillable price, L26); its verdict and L26 explicitly leave the MAKER side untested. Q20's
ladder anatomy (`findings/2026-07-13-btc-ladder-overround-anatomy-q20.md`) then documented
`wing_elevated` members — stale one-sided YES asks (0.20–0.67 with `yes_bid=0`, >±3 strikes
from spot) that almost surely settle NO. **Mechanism:** rest a maker short-YES (buy-NO at
`1−ask`) on those stale elevated wings and hold to settlement; the losing counterparty is
whoever lifts the stale far-OTM ask (a lottery-chasing taker). **Data (already collected):**
`tape/crypto_hourly/` (real_ask ladders + `broker_truth` settlement) for wing identification
and outcome, `tape/orderbook_depth/` (the mirror `no_bids` side) for the fill question —
verifier confirmed the depth tape covers these tickers. **Milestone (one probe, read-only):**
build the fill-sim and block-bootstrap by event-hour (`core.bootstrap`, L6), net of the flat
1¢ maker fee (`core.pricing`, L30). **Binding gate (verifier-mandated, do NOT weaken):**
(1) the fill test MUST be the **queue-aware `orderbook_depth` `no_bids` sim, NOT a candlestick
print** — a new offer joins the back of the 166–503-contract queue Q20 measured at these
wings, so an L39 candle-print would overstate your fill; (2) P&L MUST be **conditioned on the
fill↔settlement adverse-selection correlation** — a far-OTM YES is lifted mainly when spot
rushes the strike, so the rare fills are toxic toward settling YES against the short; (3) any
CI must clear the **L27 tick-magnitude gate**, not just sign. **Kill:** 0%-fill null (the
wings are stale precisely because nobody lifts them — S14's incidental wing fill rate was
2.5%) OR net CI ≤ 0 / fails the magnitude gate. **Honest expectation: DEAD** — this is a
cheap, decisive closer of the S10-maker / L26 loose end (a clean no-fill or CI≤0 result
formally converts "untested" to "tested-dead"), not a promising edge; the two-agent verdict
rule applies to any kill/CI. Registered this round; three sibling proposals (sports-moneyline
overround underwriting, a cross-venue held-to-settlement box, a post-release econ-ladder fade)
were killed at idea stage by the verifier — see the S19 note in `kb/strategies/00-index.md`.

### Q24 — H1: maker-side rich-ASK selling on sports longshots (the untested S7c mirror)
Status: TODO (added 2026-07-13, local Ryan-approved session — S20 wallet-forensics dossier,
peer-reviewed APPROVE WITH NOTES + independent verifier recomputation; the probe's own
verdict still requires the two-agent rule as usual)
Status: DONE (2026-07-13) — VERDICT DEAD by data-adequacy (verifier-CONFIRMED). The mandated
join (fair-anchored longshots from `tape/sports_clv/` × the `no_bids` depth queue from
`tape/orderbook_depth/`) is 0/81 joinable (0.00%, 0/83 for the yes_ask≤0.20 proxy) — L9
non-overlap: fair anchors cover kickoffs ≤07-03 while sports depth began ≥07-07, every
fair-anchored game had settled before the depth tape began (date embedded in ticker ⇒ zero
overlap is structural, verifier reproduced by bypassing the join code). Fill rate 0.00%, no
testable CI (n_units=0) — the queue-aware fill-sim Q24 exists to run is structurally
un-runnable on committed tape. NOT a CI falsification: the edge-at-quote stays S7c-proven-rich,
only the maker FILL question is untested/unmeasurable (re-testable only on concurrently-collected
fair-anchor+depth tape). Settlement was ADEQUATE (81/81 settled, 8/81=9.88% YES) and the
sold-longshot-WINS negative-skew leg fully modeled; steelman median queue-ahead 485 contracts,
only 3 full-sim-eligible markets << the 10-game floor. S21 registered dead ✗. Citation note
`kb/quant-finance/favorite-longshot-bias.md` distilled. See
`findings/2026-07-13-q24-sports-longshot-maker-fillsim-verdict.md`.
S7c PROVED the taker side: Kalshi pregame sports asks run **+2.35¢ rich** vs
DraftKings-devig fair (n=80 games/237 outcomes, block-bootstrap-by-game CI
[−0.0245,−0.0225]; `findings/2026-07-04-sports-clv-s7-verdict.md`) — do NOT re-run S7c.
S13 then tested resting maker **BIDS at fair−1¢** → DEAD (the 0.0175 maker fee ate the
margin; `findings/2026-07-04-sports-maker-s13-verdict.md`). The direct mirror is still
untested: **rest the rich ASK itself** (short YES / buy-NO at `1−ask`), concentrated in
the longshot tail where S7c's richness is largest. **Mechanism:** collect the measured
overpricing from retail lottery-ticket takers who cross the spread pregame. **The binding
risk is not edge, it's fills:** the incumbent maker queue already posts those asks — we
join the BACK of it (S19 died at 0.45% fill rate; that floor applies). Provenance color
(NOT evidence): S20's Polymarket sprint found the same trade shape in the wild
(`findings/2026-07-13-polymarket-wallet-forensics-s20-dossier.md`); its wallet stat was
degenerate — the evidentiary basis for Q24 is S7c alone. **Data (already collected):**
`tape/sports_clv/` (matched-game fair anchors) + `tape/orderbook_depth/` (S6's L2 capture
covers the sports_pairs tickers — the YES-ask/`no_bids` queue for the fill question).
**Milestone (one probe, read-only):** queue-aware fill-sim of resting at the observed ask
(and ask−1¢ variant) on longshot outcomes (fair ≤ ~0.20), open→kickoff window, maker fee
0.0175, block-bootstrap by game. **Binding gates (do NOT weaken):** (1) queue-aware
`orderbook_depth` sim, NEVER a candlestick print (L39); (2) the sold-longshot-WINS leg
must be modeled, not conditioned away — and per S20's lesson, any positive-edge claim
requires **≥1 losing cluster** in the resample unit, else p=0 is mechanical and the claim
is void; (3) L27 tick-magnitude gate on any CI; (4) adverse-selection: longshot asks get
lifted when news moves toward the longshot — condition fills on subsequent line movement
where the tape allows. **Factor cap note:** same family as S14 (short-the-overpriced-tail,
negative skew) — if both ever graduate they share one factor allocation; record this in
any graduation memo. **Citation TODO (peer-review flag #13):** distill 2–3 primary
favorite-longshot-bias papers into `kb/` as part of this milestone. **Kill:** fill rate at
or below the S19-class floor, net CI ≤ 0, magnitude-gate fail, or zero losing clusters in
the filled sample (data-inadequacy → report honestly, no verdict flip without the
two-agent rule). **Honest expectation:** the edge-at-quote is real (S7c); survival hinges
entirely on fill rate and adverse selection — a clean no-fill result converts this to
tested-dead and closes the S7 family for good.

### Q25 — Depth-tape anatomy scan: fill-plausibility map across ALL captured families
Status: DONE (2026-07-13, research loop) — **discovery-class scan complete, verifier
CONFIRMED-WITH-CAVEATS, no registry flip** (per this item's own spec). `scripts/
q25_depth_tape_anatomy.py` (33 offline tests) tabulated `tape/orderbook_depth/`
(**122,238 records / 31 families / 6 days**, 07-09 honestly absent) by family and
category × time-to-close bucket: queue depth, staleness/streak distribution,
one-sidedness, and a defined (non-canonical) resting-order turnover proxy read against
the S19 0.45%/S14 2.5% fill-rate anchors (turnover can rule a cell OUT, never IN). 21/114
cells insufficient (<20 captures/pairs), reported honestly, never extrapolated.
**Plausibly-fillable churn** (≫2.5%, next idea-gen round should look here first): WNBA
11.06% (n=2,154), UCL soccer 8.56%, KBO baseball 8.35% (least-frozen sports family, 33%),
MLB 7.62%, NPB 6.92%; near-close baseball/basketball/soccer runs 7–13%. **Dead-thin**
(at/near the S19 floor): KXBIG3GAME 0.48% (n=856), VBA 1.37%, USLCup 1.41%, MLS 1.72%.
One-sidedness (L31) confirmed **crypto-only** (96–100% any-empty vs 0–1% sports pre-close)
— the L26 1¢-floor no-bid mirror, not a general wing shape. Verifier independently
recomputed every number from scratch (record/family counts, BIG3/WNBA/crypto figures,
turnover formula edge cases, determinism) — **CONFIRMED**; raised one dispute (an
undercounted "15/114 insufficient" meta-stat), producer independently recomputed 21/114
from the JSON and corrected the doc text only (no number/code/test changed) —
**CONFIRMED-WITH-CAVEATS** net (two disclosed methodology caveats: cross-day-gap
contamination negligible at 0.04% of frozen pairs; sports HHMM tz unverifiable from
tape). Corrected the milestone spec's own worked example in the process: **crypto's hour
token is ET, not UTC** (confirmed against tape + `collection/crypto_hourly.py`'s own
docstring). 4 lesson candidates appended (L45–L48) — see `kb/lessons/00-lessons.md`.
Output: `findings/2026-07-13-depth-tape-anatomy-q25.md` +
`findings/depth_anatomy.json`. 784 tests green (751 prior + 33 new), `invariants --full`
green (only the standing non-gating L25 stray-directory advisory). Still 0 proven edges —
this is a map to seed future Q21 rounds, not itself an edge.
Status (history): TODO (added 2026-07-13, Ryan-approved local session — recommendation #1 of that
session's pipeline audit; discovery-class, no registry flip, Q20-precedent)
`tape/orderbook_depth/` is the largest tape family (~1,100–1,280 lines/hour since 07-07,
3–4× everything else combined, L38) yet it has only ever been read as a fill GATE after an
idea existed (S14's queue-aware sim, S19, now Q24) — never as a discovery scan. Q20 proved
the anatomy-scan method generates candidates (it produced S19 and S14's tradeable-parameter
block). **Milestone (one read-only scan, anatomy only — descriptive stats, no bootstrap, no
verdict, no strategy registration):** across every family the depth tape covers (sports,
crypto ladders, and whatever else `orderbook_depth.py` has captured), tabulate by
category × time-to-close bucket: (a) queue depth at best bid/ask (the 166–503-contract
queues Q20 measured on crypto wings — where are they thin?), (b) quote age / staleness
(consecutive-capture BBO-unchanged streaks — L32's frozen-pair notion as a *distribution*,
not a flag), (c) one-sidedness incidence (L31's `yes_bid=0` wing shape outside crypto),
(d) observed resting-order turnover — the direct input to fill plausibility, THE quantity
that killed S19 (0.45%) and gates S14 (2.5% benchmark) and Q24, measured BEFORE the next
idea is proposed instead of discovered after it dies. **Output:** a findings/ anatomy doc +
a machine-readable `findings/depth_anatomy.json` keyed by (family, category,
time-to-close bucket) → {median queue depth, staleness distribution, turnover rate,
one-sided incidence}, so every future Q21 round and probe spec can cite fill plausibility
from data instead of assuming it. Every number carries its capture-count denominator
(honest-accounting: cells with <20 captures are reported as `insufficient`, never
extrapolated). **This item feeds the Q21 diversity floor** — its output cells are an idea
source, not ideas themselves. Kill/limits: read-only; if the depth tape turns out to cover
too few families for a cross-category cut, report that coverage fact honestly (it is
itself the answer) rather than padding with BBO-only tape.

### Q26 — S22: OFI / depth-imbalance settlement predictor on high-churn two-sided sports books
Status: DONE (2026-07-14, research loop) — **verdict DEAD by calibration, verifier-CONFIRMED.**
Gate 1 (join adequacy) passed clean: 205 distinct joinable games (20× the 10-game floor), via a
cached live pull from Kalshi's free settled-markets endpoint over the depth tape's own window
(`tape/q26_settlement_cache/settlement.json`, 458 markets — L50's ex-post-join fix confirmed
working, unlike S21's disjoint-window death). Gate 2 (calibration precheck) hard-killed it: on
the disagreement subset (n=86 rows/81 games, the actual trade population) imbalance hit only
27.9% vs the mid's 72.1%. The verifier's sharpest attack — is 27.9% (far below 50%) a masked
sign-flipped contrarian signal? — resolved NO: `imb_hit`/`mid_hit` are mechanically
complementary on this subset (sum to exactly 1.0 by construction, both directional and
opposite by the subset's own definition), so flipping the sign would just reproduce betting
the mid, zero independent edge either way; robust across every time-to-close cut (ttc≤1h still
0.281/0.719), ruling out a cadence-washout explanation. Gates 3/4 (P&L, bootstrap CI) correctly
never reached — the calibration precheck decided cheaply, exactly as the item's own honest
expectation anticipated. `kb/strategies/00-index.md` S22 flipped `idea → dead ✗`. Two lessons
appended: L51 (disagreement-subset calibration hit-rates are complementary, not two
independent measurements — a general caution for any future "signal beats the mid" probe on a
2-way market) and L52 (Kalshi sports settlements aren't always binary — 8/458 cached were
`result:"scalar"`, must filter explicitly). See
`findings/2026-07-14-ofi-depth-imbalance-s22-verdict.md`. 21 new unit tests, `pytest` 817
green, `invariants --full` green. Still 0 proven edges; Q27/Q28 (S23/S24) remain queued.
Original spec below, unchanged.
Status (history): TODO (added 2026-07-14, Q21 idea-gen round — verifier-reviewed survivor, two-agent rule; diversity-floor candidate)
Mechanism: resting L2 book-imbalance (size on the yes_bids ladder vs the no_bids ladder) carries
information that leads the mid and predicts the settlement outcome; the losing counterparty is retail
who trade the displayed BBO/mid without reading depth. Tested ONLY on the two-sided, low-frozen,
high-turnover sports cells Q25 flagged (KBO 8.35%/33%-frozen, NPB 6.92%/29%, WNBA 11.06%, MLB 7.62%,
UCL 8.56%) — not the one-sided crypto wings. Literature: Cont, Kukanov & Stoikov 2014 (OFI), distilled
this round into `kb/quant-finance/order-flow-imbalance.md`. Data (already-collected / free):
`tape/orderbook_depth/` for the imbalance signal; settlement from Kalshi's free settled-markets endpoint
(`collection/sports_history.py::fetch_kalshi_settled`, within the ~60-day L11 retention) over the SAME
games, or the tape's own post_close convergence. Milestone (one read-only probe): at each game's last
pre-close (ttc>0) depth snapshot form the imbalance signal; when it disagrees with the mid, take the
imbalance-favored side at real_ask (best_yes_ask/best_no_ask); realized P&L = settlement − ask − taker
fee (`core.pricing`, 0.07); block-bootstrap by GAME (L6). Binding gates (verifier-mandated, do NOT weaken):
(1) VERIFY settlement-join non-emptiness — ≥10 distinct games each with a genuine pre-close last snapshot
AND a retrieved result — BEFORE any CI (pull the settled API while the 07-14 cohort is still retained,
purge ~09-12); (2) the L28-style calibration precheck (imbalance beats mid at predicting settlement) is a
HARD gate, not a footnote — stop if the signal adds nothing over the mid; (3) fillable object is a TAKER
lift, fee at the 0.07 taker rate; (4) route any CI through `core.bootstrap.bootstrap_verdict_admissible`
(≥10 units, ≥1 opposing-sign cluster) AND `clears_tick_magnitude` (L41/L27) vs the taker round-trip. Kill:
imbalance adds no predictive content beyond mid / predicted edge < round-trip cost / hourly cadence washes
the signal to noise (S9-family data-adequacy → honest DEAD-by-cadence) / CI fails either gate. Honest
expectation: uncertain — genuinely novel; the calibration precheck decides cheaply.

### Q27 — S23: Favorite-side settlement-underpricing maker on high-churn sports (favorite-longshot bias)
Status: DONE (2026-07-14) — S23 DEAD-by-fee, verifier-CONFIRMED. Queue-aware yes_bids fill-sim + ex-post Kalshi settlement (L50), 24 distinct games (G4 pass), fill 95.83% ≫ S19 floor (G3 no-kill), favorite win-rate 0.6957 < breakeven 0.7361 (fill_price real_bid + 1¢ maker fee) → favorites RICH at bid, bias absent/reversed. Block-boot by GAME n=23: mean −$0.0404, CI [−0.2435,+0.1370], admissible PASS / tick-magnitude FAIL. Same factor slot as S14/S21. Kill = win-rate ≤ fill+fee (L30/S13-family). See findings/2026-07-14-favorite-underpricing-s23-verdict.md.
Status: TODO (added 2026-07-14, Q21 idea-gen round — verifier-reviewed survivor, two-agent rule)
Mechanism: favorite-longshot bias (`kb/quant-finance/favorite-longshot-bias.md`) leaves favorites underbet;
rest a maker BID to buy the favorite YES (fair ≥ ~0.65) in Q25's high-turnover two-sided sports cells and
collect $1 on settlement when the favorite wins; the losing counterparty is retail longshot-lovers who
overbet the underdog and leave the favorite cheap. Key design choice — the fair test is REALIZED SETTLEMENT,
not a devig anchor, so it needs NO sports_clv tape and NO odds-api key (this is the exact dependency whose
absence killed S21). Data (already-collected / free): `tape/orderbook_depth/` (yes_bids queue for the
fill-sim) + Kalshi free settled endpoint (`fetch_kalshi_settled`) for the outcome, same games, within L11
retention. Milestone (one read-only probe): queue-aware yes_bids fill-sim (L39, NOT a candlestick print),
net = settlement − fill_price − flat 1¢ maker fee (`core.pricing`, L30), block-bootstrap by GAME. Binding
gates (verifier-mandated, do NOT weaken): (1) record in the SAME factor slot as S14/S21 (short-the-
overpriced-tail / favorite-longshot — one Hard-Rule-#6 ρ allocation, not diversification); (2) MODEL the
fill↔settlement adverse-selection correlation — a resting favorite-bid fills disproportionately when an
informed seller dumps the favorite about to lose, so the catastrophic favorite-loses leg MUST be in the
P&L, never conditioned away (L41 / Q24 gate-2); (3) queue-aware fill-sim, kill if fill rate ≤ the S19 0.45%
floor (Q24 measured median 485 contracts ahead); (4) verify settlement-join non-empty (≥10 games) before
CI; route through `bootstrap_verdict_admissible` + `clears_tick_magnitude`. Kill: favorite win-rate ≤
fill_price + 1¢ maker fee (bias too small / L30 fee-death, S13-family) / fill rate at-or-below S19 floor /
CI fails either gate. Honest expectation: probably DEAD (attenuated modern-exchange bias rarely clears fees),
but sound, testable, and closes an undecided branch of the S13/S21 family.

### Q28 — S24: Near-close hourly-return overreaction fade on two-sided sports books
Status: TODO (added 2026-07-14, Q21 idea-gen round — verifier-reviewed survivor, two-agent rule; weakest of the three)
Mechanism (Theme 7 behavioral, De Bondt-Thaler/Tetlock): an hourly-scale near-close mid jump in a two-sided
sports book (retail overreacting to the last salient in-game event) partially reverses over the next hour;
fade the jump. Losing counterparty = the overreacting retail flow. Distinct from S18 (elections/polls,
idea-stage) — different category and horizon. Data (already-collected): `tape/orderbook_depth/` price paths
in the Q25 high-turnover cells. Milestone (one read-only probe): identify consecutive-snapshot mid jumps
≥ X¢ in the near-close window; enter a fade at real_ask against the jump; measure the next-snapshot
reversal; block-bootstrap by distinct GAME (L6). Binding gates (verifier-mandated, do NOT weaken) — the
first is load-bearing for distinctness: (1) the EXIT must be explicitly specified and the CI must charge
the FULL realized round-trip (both taker legs: 2× 0.07 fee + 2× half-spread ≈ a 6-8¢ hurdle on a ~3.7¢-
overround two-sided book) — AND if the only profitable exit is hold-to-settlement, S24 collapses into S22's
mechanism (a directional settlement bet keyed on a recent jump) and MUST be routed to S22's slot, NOT
double-counted; (2) the ≥X¢ jump threshold must clear the frozen-BBO/bid-ask-bounce noise floor (Q25:
58-94% frozen — a real mid move, not a one-tick flicker); (3) bootstrap by distinct GAME, ≥10 games —
verify the jump population reaches the floor (Q25's sub-hour buckets are mostly insufficient); (4)
momentum-vs-reversal is a sign question so the opposing-sign cluster (L41) is NOT guaranteed — assert
`bootstrap_verdict_admissible` admissible and `clears_tick_magnitude`. Kill: jumps continue (momentum, not
reversal) / reversal < round-trip cost / hourly cadence too coarse (S9-family) / CI fails either gate.
Honest expectation: DEAD-by-round-trip is likely; sound and novel nonetheless.

## Retro amendments — proposed 2026-07-05, ADOPTED 2026-07-10 (PR #18 merged)

Drafted by the weekly retro run from that week's "Log of runs". **Adopted** — Ryan merged
PR #18 on 2026-07-10T19:55:32Z, so all 3 items below are now binding protocol, not proposals.
This run (2026-07-11) already followed #1 (mandatory `git reset --hard origin/main` before
the step 0b diff) and #2 (no more `git push origin --delete` retries) and applied #3 (PR #4
is 8 days old, flagged `Priority: high` in this run's phone note). Nothing here relaxed an
invariant or a Stop rule, deleted or reordered a queue item, or touched source code.

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
- 2026-07-10T20:2xZ (research loop) · step 0a PASS + stranded-tape sweep (5,125 lines) + tape-format-regression finding, Q7 still BLOCKED · Step 0a history-integrity check passed (5 most-recent merged PRs' squash commits all reachable from `origin/main`, verified by message search post-unshallow since PR head SHAs aren't ancestors under squash-merge; kb-log/tape date gap 0 days). Open PR #4 still claims Q1 (unrelated, now 7 days old awaiting `ODDS_API_KEY`, past PR #18's proposed 5-day escalation mark — flagged Priority:high this run). Step 0b sweep: fetched + content-diffed all 80 `tape/hourly-*` branches; ~70 pre-07-08 branches already fully reconciled; found and union-appended **5,125 lines** from 9 branches with real gaps (3 from the 07-08T10:56Z reset window, 6 from today) across crypto_hourly/orderbook_depth/polymarket_macro_pairs/polymarket_pairs/sports_pairs — 0 malformed, 0 exact dupes; `20260710T1955Z` skipped (freshness rule). Checking Q7's day-count surfaced a real bug: `tape/crypto_hourly/dt=2026-07-10` and `tape/sports_pairs/dt=2026-07-10` were **directories** of unreadable raw blobs (23 hourly passes, 00:26Z–19:24Z), not the canonical `.jsonl` file — a leftover from the post-reset lineage's rebuilt collectors that PR #35 reconciled the code for but not the already-committed tape; `orderbook_depth`/`polymarket_pairs`/`polymarket_macro_pairs` have zero 07-10 entries at all (post-reset `hourly_pass.py` only ran 2 of 5 sub-passes). Confirmed self-corrected (first pass after PR #35's merge writes the correct format, still stranded on `tape/hourly-20260710T1955Z` pending next sweep). Q7 stays BLOCKED — 6 valid days, not 7. Added `kb/lessons/00-lessons.md` L25 (UNENFORCED). No code changed; docs/tape only. 401 tests green, `invariants --full` green. See `findings/2026-07-10-tape-format-regression-crypto-sports.md`.
- 2026-07-10T00:22Z · Q2 · built `collection/crypto_hourly.py` + `core/crypto_schema.py` (14 new tests, all green, 85 total); live pass captured BTC (188 outcomes) + ETH (75 outcomes) hourly ladders paired with spot (Coinbase, synthetic) + prior-hour settlement (Kalshi expiration_value, broker_truth), spot/settle both `ok`; found naive full-ladder bracket_sum is inflated by far-OTM $0.01-floor brackets (BTC overround +2.99, ETH +1.22) — not comparable to weather's ~10¢ without a near-the-money filter, flagged for Q5 → S8 data-collecting.
- 2026-07-10T05:11Z · Q3 · Q1+Q2 dependency resolved so Q3 flipped BLOCKED→TODO and ran topmost; built `collection/hourly_pass.py` (10 new tests, all green, 105 total) orchestrating sports_pairs + crypto_hourly + conditional 09-UTC anomaly sweep, honest completeness_ok never faked True; live pass 1311 markets/455 lines completeness ok. Collector plumbing (Q1/Q2/Q3) complete; queue center of gravity moves to Q4/Q5 edge-testing.
- 2026-07-10T10:35Z · Q4(S7a) · built `scripts/sports_history_s7a.py` (16 new tests, all green, 121 total); live pass sourced 97 completed World Cup 2026 games / 291 outcome markets at real_ask candlesticks, matched 96/97 to football-data.co.uk's free closing-odds average (synthetic, de-vigged); confirmed last-season NFL fully unavailable from Kalshi's public API (settled markets purged after ~1 season) and NBA only partially available (36 playoff games, no odds leg yet) — documented, not a blocker. Q4 IN-PROGRESS, next stage runs S7b (Kalshi ask vs de-vig fair) on the World Cup dataset.
- 2026-07-10T15:16Z · Q4(S7b) · built `scripts/sports_clv_s7.py` (16 new tests, all green, 137 total); live pass over S7a's 97-game tape: 96 usable games, 167 candidate trades (decision_ts = close_time−4h, buy-YES when de-vigged fair > Kalshi bracket-normalized ask), mean net P&L −3.51¢/trade at real_ask after fee — negative point estimate, and a min-edge sweep (0.00/0.02/0.05 → −3.51¢/−9.30¢/−27.00¢) makes it monotonically worse, mirroring the S5 red flag. Not yet a verdict (no bootstrap run). Q4 IN-PROGRESS, next stage S7c runs the block-bootstrap by game → 95% CI → verdict.
- 2026-07-10T (local, Ryan) · RECONCILIATION · discovered main was rewound to 6cde523 on 2026-07-08T10:56Z (197 commits orphaned: 07-03→07-08 incl. PRs #4–#33); recovered pre-reset tip f23a491 via GitHub event log, merged post-reset 07-09/10 work into it (code conflicts → pre-reset lineage; post-reset tape/findings/core.odds kept). The five 07-09/10 lines above describe the post-reset lineage's duplicate rebuild — S7 stays DEAD per the 07-04 bootstrap verdict, independently corroborated by their S7b point estimate.
- 2026-07-11T00:xxZ (research loop) · step 0a PASS + stranded-tape sweep (1,070 lines) + Q7(S10) DONE, verdict DEAD · Step 0a: 5 most-recently-merged PRs (#36,#18,#35,#33,#32) all reachable from `origin/main` (verified via commit-message search, squash-merge convention); `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` file both 2026-07-10, 0-day gap. `main` not rewound. Open PRs: only #4 (Q1 odds-api leg, still claimed, now 8 days old awaiting `ODDS_API_KEY` — past the now-merged PR #18 retro amendment's 5-day escalation mark, flagged `Priority: high` in this run's phone note). Step 0b sweep: `git reset --hard origin/main` done first (per PR #18's now-merged amendment #1); 3 remaining `tape/hourly-*` branches (`20260710T1955Z`/`2058Z`/`2200Z`, all pointing at the same commit `cf33e5f` — the first hourly pass after PR #35's merge, left unswept by PR #36 because it was <30min old at the time) carried 1,070 lines `main` was missing (crypto_hourly +2, orderbook_depth +822, polymarket_macro_pairs +15, polymarket_pairs +13, sports_pairs +218), union-appended, 0 exact duplicates, all valid JSON; `tape/hourly-20260711T000050Z` skipped (freshness rule); branch-delete not attempted (per PR #18's now-merged amendment #2, documented permission boundary). This sweep pushed `tape/crypto_hourly/` to **7 valid canonical days** (03,04,05,06,07,08,10), unblocking **Q7**. Built `scripts/s10_reachability_probe.py` (16 new tests, 432 total) via the `edge-prober` subagent: joined early/late `real_ask` captures per hourly group against `broker_truth` settlement — far brackets are already pinned at the 1¢ YES floor before the early capture (no decay window), the mirrored $1.00 NO-ask is structurally unfillable-positive-EV (`fee_per_contract(1.00)==0`, only 4/18,992 far obs had any room), block-bootstrap by hour (10,000 resamples, n=164): mean +$0.000008, 95% CI [+$0.000000, +$0.000024] — 3 orders below the 1¢ tick. **Verdict: DEAD (structural)**, adversarially CONFIRMED by the `verifier` subagent (independent re-run, settlement-join/fee-math/cluster-bootstrap/threshold-sweep all checked, no bug found). `kb-distiller` subagent compounded S10 → dead ✗ in the registry plus 3 lesson candidates. See `findings/2026-07-11-crypto-reachability-s10-firstcut.md`. 432 tests green, `invariants --full` green.
- 2026-07-11T05:xxZ (research loop) · step 0a PASS + stranded-tape sweep (1,551 lines) + L25→L29 tape dir-shape invariant built · Step 0a: 5 most-recently-merged PRs (#37,#36,#18,#35,#33) all reachable from `origin/main` (commit-message search post squash-merge); `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` file both 2026-07-11, 0-day gap. `main` not rewound. Open PRs: only #4 (Q1 odds-api leg, still claimed, ~8 days old awaiting `ODDS_API_KEY`, past the adopted 5-day escalation mark — flagged `Priority: high` again). Step 0b sweep (`git reset --hard origin/main` first): of 86 branches, 3 recent ones (`20260711T000050Z`/`0254Z`/`0356Z`, all >30min old) carried real gaps — `20260711T0154Z` diffed to zero missing (already landed on `main` via commit `308d9fc`). Union-appended **1,551 lines** (crypto_hourly +6, orderbook_depth +827, polymarket_macro_pairs +45, polymarket_pairs +30, sports_pairs +643), 0 exact duplicates, all valid JSON; branch-delete not attempted (documented permission boundary). No numbered queue item eligible (Q13 still BLOCKED — 8 of ≥10 valid `tape/sports_pairs/` days; Q14/Q15 still data-adequacy BLOCKED; Q1 claimed by PR #4) — drew from the lessons ledger's standing UNENFORCED queue instead. Converted **L25** into a live check: `scripts/invariants.py`'s new `_tape_dir_shape_issues()`/`tape_dir_shape_warning()` (non-gating advisory, same pattern as L20) flags any `tape/<family>/dt=<date>` path that is a directory instead of the canonical `.jsonl` file — live-validated against the real tree, correctly catches the 4 stray directories the 2026-07-08 regression left uncleaned (`crypto_hourly/dt=2026-07-10`, `sports_pairs/dt=2026-07-02`/`07-09`/`07-10`; cleanup itself flagged as separate follow-up, not done here). 6 new tests (438 total). Recorded **L29** (supersedes L25) in `kb/lessons/00-lessons.md`. 438 tests green, `invariants --full` green (only the two expected non-gating advisories).
- 2026-07-11T10:xxZ (research loop) · step 0a PASS + stranded-tape sweep (2,076 lines, PR #39 merged) + Q16(S6) milestone: first-cut verdict DEAD, verifier-CONFIRMED · Step 0a: 5 most-recently-merged PRs (#38,#37,#36,#18,#35) all reachable from `origin/main` (verified in local shallow log); `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` file both 2026-07-11, 0-day gap. `main` not rewound. Open PRs: only #4 (Q1 odds-api leg, still claimed, ~8 days old awaiting `ODDS_API_KEY` — flagged `Priority: high` again). Step 0b sweep (`git reset --hard origin/main` first): of 88 branches, 2 recent ones (`20260711T0656Z`/`0756Z`, both >30min old, distinct non-overlapping commits) carried a union of **2,076 lines** `main` was missing (crypto_hourly +4, orderbook_depth +1,606, polymarket_macro_pairs +30, polymarket_pairs +20, sports_pairs +416), 0 exact duplicates, all valid JSON — merged as standalone PR #39 (squash) so `main` was current before the milestone landed. No numbered queue item eligible (Q13 still BLOCKED — needs ≥10 days `tape/sports_pairs/`, eligible ~07-13; Q14/Q15 data-adequacy BLOCKED; Q1 claimed by PR #4) — drew on Q16/S6's own documented remaining-work note (build a first-cut arrival-intensity/adverse-selection estimate) via the `edge-prober` subagent. Built `scripts/s6_maker_firstcut.py` (15 new tests, 453 total) over 4 days of accumulated `tape/orderbook_depth/` (~58K records): L28 precheck first (69.7% of consecutive same-ticker pairs frozen — no fill, booked $0), then a by-ticker block bootstrap (10,000 resamples) of net maker P&L across fillability-filtered spread populations — every economically realistic cut came back strictly negative (primary ≤10¢ frozen-inclusive: mean −$0.00195, 95% CI [−$0.00297,−$0.00094]); the naive "alive" +$0.069 population was a >30¢ one-sided wing-bracket artifact. Structural kill: Kalshi's maker fee is a flat $0.01/contract at every interior price, consuming the modal 1–2¢ two-sided spread before adverse selection — same mechanism as S13's death. Adversarially **CONFIRMED** by the `verifier` subagent: exact reproduction, additional threshold sweep (≤15/20/25/30¢) found no economically-meaningful alive population (the lone CI>0 cut clears only a quarter-cent, failing L27's tick-magnitude gate, and is itself wing-driven). `kb-distiller` subagent compounded: `kb/strategies/00-index.md` S6 → `dead ✗`; lessons L30 (flat maker fee, test-enforced), L31 (wing-spread artifact, ledger-only), L32 (frozen-pair-no-fill precheck, UNENFORCED) appended. See `findings/2026-07-11-mm-spread-s6-firstcut.md`. 453 tests green, `invariants --full` green. S11 (sharp-anchored maker quoting) remains un-falsified — needs a free real-time sharp-odds anchor this run doesn't have.
- 2026-07-11T15:xxZ (research loop) · step 0a PASS + stranded-tape sweep (223 lines) + L33: shared block-bootstrap helper built · Step 0a: 5 most-recently-merged PRs (#40,#39,#38,#37,#36) all reachable from `origin/main`; `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` file both 2026-07-11, 0-day gap. `main` not rewound (the shallow clone's stored `origin/main@{1}` ref failing `merge-base --is-ancestor` was the shallow-history boundary, not evidence of a rewind — confirmed via the merged-PR reachability check + log/tape date parity instead of trusting that heuristic alone). Open PRs: only #4 (Q1 odds-api leg, still claimed, now 8 days old awaiting `ODDS_API_KEY`, flagged `Priority: high` again). Step 0b sweep (`git reset --hard origin/main` first): of the branches, `tape/hourly-20260711T1256Z` (>30min old, uncovered by PR #40's sweep) carried **223 lines** `main` was missing despite already having more total lines per file from a later pass (crypto_hourly +2, polymarket_macro_pairs +15, polymarket_pairs +10, sports_pairs +196; orderbook_depth 0 missing), 0 exact duplicates, all valid JSON; branch-delete not attempted (documented permission boundary). No numbered queue item eligible (Q1 claimed by PR #4; Q7/Q16 DONE; Q13 still BLOCKED — 8 of ≥10 valid `tape/sports_pairs/` days, eligible ~07-13; Q14/Q15 data-adequacy BLOCKED) — drew from the lessons ledger's standing UNENFORCED queue instead: L27/L28 were both filed as "likely terminal as protocol... once a probe-precedent encodes it," but no such precedent existed — every bootstrap-using script still hand-rolls its own loop. Built `core/bootstrap.py` (`block_bootstrap` generic by-unit resample, `clears_tick_magnitude` L27's gate, `floor_pinned_fraction` L28's precheck) + 17 new offline tests in `tests/test_bootstrap.py`. Does not retrofit S6/S10's already-verdicted probes. Recorded **L33** in `kb/lessons/00-lessons.md`. 470 tests green (453 prior + 17 new), `invariants --full` green (only the two expected non-gating advisories).
- 2026-07-11T (later run, research loop) · step 0a PASS + stranded-tape sweep (1,936 lines) + L34: bootstrap-helper protocol encoded into edge-prober charter · Step 0a: local branch head equals `origin/main` tip (`ade6160`); 3 most-recently-merged PRs visible (#41,#40,#39) all reachable; `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` file both 2026-07-11, 0-day gap. `main` not rewound. Open PRs: only #4 (Q1 odds-api leg, still claimed, ~8 days old awaiting `ODDS_API_KEY`). Step 0b sweep: of 91 `tape/hourly-*` branches, 2 postdating the last sweep's cutoff (`20260711T1501Z`/`1806Z`, both >30min old) carried a union of **1,936 lines** `main` was missing (crypto_hourly +4, orderbook_depth +1,507, polymarket_macro_pairs +30, polymarket_pairs +20, sports_pairs +375), 0 exact duplicates, all valid JSON; branch-delete not attempted (documented permission boundary). No numbered queue item eligible (same state as the prior run this cycle: Q1 claimed, Q7/Q16 DONE, Q13 BLOCKED — still 8 of ≥10 valid `tape/sports_pairs/` days, eligible ~07-13, Q14/Q15 data-adequacy BLOCKED) — drew from the lessons ledger's standing UNENFORCED queue again: L33 built `core/bootstrap.py` but left the "probe-precedent encodes it" half of L27/L28's own wording undone — nothing yet told a future probe to use the new helper instead of hand-rolling again. Closed the gap in `.claude/agents/edge-prober.md` (the file every probe milestone reads before writing code): house style now names `block_bootstrap`/`clears_tick_magnitude`/`floor_pinned_fraction` explicitly and folds the tick-magnitude gate into the three-outcome verdict rule (CI>0 that fails the magnitude gate = DEAD, not just "worth flagging"). Docs-only, no source code touched. Recorded **L34** in `kb/lessons/00-lessons.md` (L27/L28 stay individually UNENFORCED as ledger rows per the append-only rule — full resolution still waits on an actual probe using the helper). 470 tests unchanged, `invariants --full` green (only the two expected non-gating advisories).
- 2026-07-12T00:xxZ (research loop) · step 0a PASS + stranded-tape sweep (873 lines) + L35: frozen-pair dual-cut bracketing helper built · Step 0a: 5 most-recently-merged PRs (#42,#41,#40,#39,#38) reachable from `origin/main` (#38 confirmed by a prior run — outside this session's shallow-clone depth, not evidence of a rewind; #42/#41/#40/#39 directly visible); `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` file both 2026-07-11, 0-day gap pre-sweep. `main` not rewound. Open PRs: only #4 (Q1 odds-api leg, still claimed, still draft, now ~9 days old awaiting `ODDS_API_KEY` — flagged `Priority: high` again). Step 0b sweep (`git reset --hard origin/main` first): of 93 `tape/hourly-*` branches, 2 postdating the last sweep's cutoff (`20260711T1501Z`/`1806Z`) — `20260711T205500Z` and `20260711T2156Z`, both well past 30min old — carried a union of **873 lines** `main` was missing (crypto_hourly +4, orderbook_depth +466, polymarket_macro_pairs +30, polymarket_pairs +20, sports_pairs +353; this session's shallow clone had no merge-base with these branches, so line content was read via `git show <branch>:<path>` rather than `git diff`), 0 exact duplicates, all valid JSON; branch-delete not attempted (documented permission boundary). No numbered queue item eligible (Q1 claimed, Q7/Q16 DONE, Q13 BLOCKED — 9 of ≥10 valid `tape/sports_pairs/` days, eligible ~07-13, Q14/Q15 data-adequacy BLOCKED) — drew from the lessons ledger's standing UNENFORCED queue again: L34 closed L27/L28's charter gap but left **L32** (frozen-pair no-fill precheck + dual-cut bracketing, from S6) as the one still-open UNENFORCED candidate in that lineage, with no importable counterpart in `core/bootstrap.py`. Built `core.bootstrap.bracket_by_movement(frozen_flags, values)` — takes the caller's own per-observation frozen flags (L6-style, never guesses what "frozen" means) and returns the frozen-inclusive list, movement-conditioned list, and frozen fraction; 6 new tests. Updated `.claude/agents/edge-prober.md` house style to name it alongside the L27/L28 helpers for any snapshot-based probe. Recorded **L35** in `kb/lessons/00-lessons.md` (generalizes L32; L32 stays UNENFORCED as a ledger row per the append-only rule). 476 tests green (470 prior + 6 new), `invariants --full` green (only the two expected non-gating advisories).
- 2026-07-12T05:xxZ (research loop) · step 0a PASS + stranded-tape sweep (872 lines) + L36: strike-spacing-from-ladder helper built · Step 0a: 5 most-recently-merged PRs (#43,#42,#41,#40,#39) all reachable from `origin/main` (#43's squash commit `b3b76c4` directly visible in the local log); `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` file both 2026-07-12, 0-day gap. `main` not rewound (an initial `git fetch origin main` reporting "forced update" was the local shallow-clone ref catching up to a stale snapshot from container start, not a real rewrite — confirmed HEAD `147cffe` unchanged before/after). Open PRs: only #4 (Q1 odds-api leg, still claimed, still draft, now ~9 days old awaiting `ODDS_API_KEY` — flagged `Priority: high` again). Step 0b sweep (`git reset --hard origin/main` first): of 96 `tape/hourly-*` branches, 2 postdating the last sweep's cutoff and >30min old (`202607120401Z`, `20260712T0258Z`) carried a union of **872 lines** `main` was missing (crypto_hourly +2, orderbook_depth +687, polymarket_macro_pairs +15, polymarket_pairs +7, sports_pairs +161), 0 exact duplicates, all valid JSON; `20260712T0458Z` skipped (commit 5min old, below the freshness threshold); branch-delete not attempted (documented permission boundary). No numbered queue item eligible (Q1 claimed, Q7/Q16 DONE, Q13 BLOCKED — still 9 of ≥10 valid `tape/sports_pairs/` days, eligible ~07-13, Q14/Q15 data-adequacy BLOCKED) — drew from the lessons ledger's standing UNENFORCED queue again: L7 ("derive bracket/strike spacing from the ladder itself") had stayed UNENFORCED since 2026-07-04 — its actual fix in `scripts/s8_basis_probe.py` only swapped a fixed-$100 width for a 2-symbol hardcoded dict, still a guess rather than a ladder-derived value, and no importable helper existed for what the lesson actually asked for. Built `core.pricing.infer_strike_spacing(strikes)`: dedupes/sorts the ladder's own strikes, returns the median consecutive gap (robust to one missing/duplicated member), `None` below 2 distinct strikes; 5 new tests in `tests/test_substrate_primitives.py`. Updated `.claude/agents/edge-prober.md` house style to name it. Does not retrofit S8's already-verdicted DEAD probe (Q5) — that verdict stands as-is. Recorded **L36** in `kb/lessons/00-lessons.md` (generalizes L7; L7 stays UNENFORCED as a ledger row per the append-only rule). 481 tests green (476 prior + 5 new), `invariants --full` green (only the two expected non-gating advisories).
- 2026-07-12T11:xxZ (research loop) · step 0a PASS + stranded-tape sweep (1,708 lines) + Q12/S17 lead-lag first cut · Step 0a: 5 most-recently-merged PRs (#44,#43,#42,#41,#40) all reachable from `origin/main` (a fresh `git fetch origin main` reported "forced update" — traced to this session's shallow-clone (`--depth 50`) truncating the graph, confirmed a false positive via `git fetch --unshallow` + re-checked ancestry, not a real rewrite); `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` file both 2026-07-12, 0-day gap. `main` not rewound. Open PRs: only #4 (Q1 odds-api leg, still claimed, still draft, now **9 days old** awaiting `ODDS_API_KEY` — past the 5-day escalation mark, flagged `Priority: high` in this run's phone note, same as the last several runs). Step 0b sweep (`git reset --hard origin/main` first): of 97 `tape/hourly-*` branches, 2 postdating PR #44's sweep cutoff and well past 30min old (`20260712T0458Z`, `202607120557Z`) carried a union of **1,708 lines** `main` was missing (crypto_hourly +4, orderbook_depth +1,349, polymarket_macro_pairs +30, polymarket_pairs +8, sports_pairs +317), 0 exact duplicates, all valid JSON; committed standalone (PR, squash-merged) so `main` was current before the milestone landed. No numbered queue item eligible (Q1 claimed, Q7/Q9/Q16 DONE, Q13 BLOCKED — still 9 of ≥10 valid `tape/sports_pairs/` days, eligible ~07-13, Q14/Q15 data-adequacy BLOCKED); the lessons ledger's own standing UNENFORCED rows (L23, L27/L28/L32-style) were all already resolved-as-far-as-possible or blocked on a future probe, so this run instead drew on **Q12/S17's own remaining-work note** (accumulate snapshots, then a lead-lag cross-correlation, same shape as S9) via the `edge-prober` subagent — genuine strategy-registry progress rather than another infra-only lesson closure. See the Q12 entry above for the full write-up. 507 tests green (481 prior + 26 new), `invariants --full` green (one false-positive `no_yes_ask_arithmetic` hit on a docstring's "kalshi.yes_ask / polymarket.best_ask" prose — not real arithmetic — fixed by rewording to "and" before commit).
- 2026-07-12T15:xxZ (research loop, later run) · step 0a PASS + stranded-tape sweep (2,632 lines) + L38 sweep-size diagnosis · Step 0a: 5 most-recently-merged PRs (#45,#44,#43,#42,#41) all reachable from `origin/main`; `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` file both 2026-07-12, 0-day gap. `main` not rewound (local HEAD already equaled `origin/main` tip before and after a "forced update" fetch message — shallow-clone artifact). Open PRs: #4 (Q1 odds-api leg, still claimed, now **10 days old** awaiting `ODDS_API_KEY`, flagged `Priority: high` again) and #46 (this week's retro — docs-only `LOOP-QUEUE.md` proposal, left untouched per its own never-self-merge charter; claims no numbered queue item). Step 0b sweep (`git reset --hard origin/main` first): of ~102 `tape/hourly-*` branches, 4 postdating PR #45's cutoff and >30min old (`202607121155Z`, `20260712T1126Z`, `202607121356Z`, `20260712T1256Z`) carried a union of **2,632 lines** `main` was missing (crypto_hourly +8, orderbook_depth +1,958, polymarket_macro_pairs +60, polymarket_pairs +16, sports_pairs +590), 0 exact duplicates, all valid JSON; `20260712T1459Z` skipped (~10min old). No numbered queue item eligible (Q1 claimed, Q7/Q9/Q16 DONE, Q13 BLOCKED — still 9 of ≥10 valid `tape/sports_pairs/` days, eligible ~07-13, Q14/Q15 data-adequacy BLOCKED); the lessons ledger's mechanical helper-conversion chain (L27/L28/L32/L7→L33/L34/L35/L36) is now fully closed, and re-running S17's lead-lag probe would just reproduce last run's same no-shock-in-window result — so this run instead diagnosed a real question the 2026-07-12 weekly retro (open PR #46) flagged: is the sweep's line count actually climbing (1,936→872→873→1,708→2,632)? Via the `tape-auditor` subagent (read-only): **verdict NOT a real problem** — the fuller chronological series (2,076→223→1,936→873→872→1,708→2,632) is noisy/non-monotone, not climbing; `orderbook_depth`'s flat-but-large ~1,100–1,280 lines/hour footprint (3–4x every other family combined) means whichever sweep window catches 0/1/2 of its passes alone swings the total ±1,200–2,400 lines, no rising cloud-leg fallback rate, no unbounded ticker growth. Flagged in passing (not chased further): zero `tape/hourly-*` branches exist for 2026-07-09, a full-day gap worth a future coverage check. See `findings/2026-07-12-stranded-tape-sweep-growth-diagnosis.md`; **L38** recorded in `kb/lessons/00-lessons.md`. No code changes; 507 tests unchanged, `invariants --full` green (only the two expected non-gating advisories).
- 2026-07-12T~19:30Z (ops, Ryan-approved interactive — Fable handoff) · OPERATING SYSTEM v3 · protocol v3 (idle-run policy, two-agent verdict rule codified, step-9 paper sub-pass, research cadence 5h→3h, nightly Opus edge-hunter leg specced in ops/ROUTINES.md), execution lane opened (Stop-rules amendment; paper spine execution/{schema,limits,fill_models,paper_broker,strategy_api}.py, 58 new tests), 2 new invariants (order_endpoints_confined, risk_caps_sanctioned), queue restocked Q18–Q22 (Q17 reserved for retro PR #46), agent roster fable→opus. 578 tests + invariants --full green. See kb/00-LOG.md 2026-07-12 OS v3 entry.
- 2026-07-12T21:xxZ (research loop, protocol v3 first firing) · step 0a PASS + stranded-tape sweep (3,093 lines, PR #49 merged) + Q18 odds-leg matching activation · Step 0a: `git fetch origin main` initially reported "forced update" (traced to this session's shallow clone catching up — local HEAD already equaled `origin/main`'s tip both before/after, same false-positive shape as several prior runs); `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` file both 2026-07-12, 0-day gap, `main` not rewound. Only open PR was #4 (Q1 odds-api leg, now ~9 days old, claimed Q1's remaining work) — closed this run as superseded (see below). Step 0b sweep (`git reset --hard origin/main` first): of the 4 `tape/hourly-20260712T{1459,1600,1756,1956}Z` branches (all >30min old; `202607122055Z` skipped at ~13min old), union-diffed against main's current tape: **3,093 lines** missing (crypto_hourly +8, orderbook_depth +2,466, polymarket_macro_pairs +60, polymarket_pairs +16, sports_pairs +543), 0 exact duplicates, all valid JSON — committed standalone (PR #49, squash-merged) so `main` was current before the milestone landed. **Milestone: Q18** (topmost eligible — Q1 not actionable without the key, Q13 still BLOCKED ~9/10 days, Q14/Q15 data-adequacy BLOCKED). Diagnosed the "zero matched records since key-day" report: the odds-api matching layer was a hardcoded literal, never actually calling the-odds-api — so quota was NOT being burned (contrary to the item's original framing) but the tape has been silently useless for S11 since 07-10. Ported PR #4's already-built matching layer (`collection/odds_api.py`: kickoff-primary + team-name-fallback matching, Pinnacle-first bookmaker order, honest per-game statuses, built-in quota discipline) onto current `main` by hand (PR #4's own branch had diverged ~10,000 files and wasn't mergeable). `sports_pairs` schema → v2 (`game_start` + `outcome_name` persisted even keyless). 26 new/changed tests, 630 total green, `invariants --full` green. Live keyless smoke (no key in this cloud sandbox by design): 114/114 real Kalshi games captured complete, v2 fields correct (tape not committed, code-only PR). PR #4 commented + closed as superseded. Not flipped: S11 stays `idea` in the registry — the actual match-against-real-odds-api-events path needs a keyed VPS pass to confirm; that confirmation is this item's remaining work. See `findings/2026-07-12-odds-leg-matching-activation-q18.md`.
- 2026-07-13T00:xxZ (research loop) · step 0a PASS + stranded-tape sweep (803 lines) + Q18 CLOSED: odds-leg matched records confirmed, S11 idea→data-collecting (verifier-CONFIRMED) · Step 0a: `origin/main`'s HEAD (`db33245`) descends from all recently-merged PRs (#50/#49/#48/#47/#45/#44/#43/#42, checked via GitHub MCP + local ancestry; #46 stays unmerged, untouched per its own charter); `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` file both 2026-07-12, 0-day gap. `main` not rewound — the local `main` ref plus an initial `git fetch` "forced update"/"unrelated histories" were the same benign shallow-clone artifact prior runs (#43/#44/#45/#47) already diagnosed (no common ancestor within this session's shallow depth); `git reset --hard origin/main` resolved it. No open PRs — nothing claimed. Step 0b sweep (of 109 `tape/hourly-*`/`tape/burst-*` branches, 2 postdating PR #49's cutoff and >30min old — `tape/hourly-202607122055Z` (20:57Z), `tape/hourly-20260712T2306Z` (23:06Z); `tape/hourly-20260713T0006Z` (00:06Z, ~6min old) skipped per freshness rule): union-diffed via `git show <ref>:<path>` (no merge-base in this shallow clone) against main's current tape — **803 lines** missing (crypto_hourly +4, orderbook_depth +538, polymarket_macro_pairs +30, polymarket_pairs +8, sports_pairs +223), 0 exact duplicates, all valid JSON; branch-delete not attempted (documented permission boundary). **Milestone: Q18's live-confirmation gate** (topmost eligible — Q13 still BLOCKED at 9/10 valid `tape/sports_pairs/` days due to the 07-09 collection gap, Q14/Q15 data-adequacy BLOCKED). Checked `tape/sports_pairs/dt=2026-07-12.jsonl`: the first keyed VPS pass after Q18's port (`20260712T212303Z`, commit `6b6938d`, ~3h post-merge) wrote `odds_leg.status="matched"` — **6 matched records**, 3 VPS passes × 2 World Cup games, `match_score=2.0`/`outcome_coverage="full"`, de-vig `fair_prob`/`book_overround` math reproduced exactly, Rule #3 tags correct (`real_ask`/`real_bid` Kalshi legs, `synthetic` odds leg). Two-agent rule applied (registry flip): `verifier` subagent independently re-parsed the tape, ran `git blame` to confirm the match is genuinely new (not backfilled) and re-derived the de-vig math — **CONFIRMED**. `kb/strategies/00-index.md` **S11: idea → data-collecting** (data-flow milestone only, still thin — 1 bookmaker/2 games/3 passes, no P&L/CI claim). `LOOP-QUEUE.md` Q18 → DONE. Step 9: `execution/strategy_api.SHADOW_REGISTRY` still empty — no-op. pytest green, `invariants --full` green.
- 2026-07-13T03:xxZ (research loop) · step 0a PASS + stranded-tape sweep (655 lines, PR #52 merged) + Q13(S14) DONE: ladder-underwriting first cut, PROXY-POSITIVE not proven (verifier CONFIRMED-WITH-CAVEAT) · Step 0a: `origin/main` HEAD (`cc7e67a`) descends from all recently-merged PRs (#51/#50/#49/#48/#47/#46/#45/#44/#43, checked via GitHub MCP + local ancestry); `kb/00-LOG.md` newest entry (2026-07-12) and newest `tape/*/dt=*` file (2026-07-13) within the 2-day gap tolerance. `main` not rewound. No open PRs — nothing claimed. Step 0b sweep: of the `tape/hourly-*` branches, `tape/hourly-20260713T0006Z` (00:06:44Z) was >30min old at check time — union-diffed against main's current tape: **655 lines** missing (crypto_hourly +2, orderbook_depth +532, polymarket_macro_pairs +15, polymarket_pairs +4, sports_pairs +102), 0 exact duplicates, all valid JSON; `tape/hourly-20260713T025Z` (02:57:27Z, ~12min old) skipped per freshness rule; committed standalone (PR #52, squash-merged) so `main` was current before the milestone landed. **Milestone: Q13** — newly eligible this run (`tape/sports_pairs/` crossed 10 valid canonical days: 03,04,05,06,07,08,10,11,12,13; 07-09 remains a real gap day). Delegated to `research-lead`, which re-scoped the spec honestly: `sports_pairs` moneyline groups (2-3 outcomes) are not a genuine strike ladder, so the fill-sim ran over `tape/crypto_hourly/`'s BTC/ETH hourly bracket ladders instead (mean 131.5 members, MECE, exactly one strike settles YES) via new `scripts/s14_ladder_fillsim.py` (21 offline tests, injected fetcher). Method: post a resting short-YES maker offer at every member's `yes_ask` at the earliest capture of each settled event-hour; fill proxy = cached Kalshi candlestick `max(high) >= posted_ask AND volume > 0` (seller mirror of S13's resting-bid rule); payout $1 iff the `broker_truth` winner was among filled strikes. Block-bootstrap by event-hour (n_boot=10,000, n=300): mean **+$0.0925, 95% CI [+$0.0630, +$0.1231]**, clears the tick-magnitude gate, robust under coarser blocking units (by-day, by-day×symbol). Adversarially reviewed by the `verifier` subagent (three independent reproductions, all to the cent): verdict **CONFIRMED-WITH-CAVEAT** — the "complete fill" gate term is $0 (0.0% complete-fill rate; the result is path-dependent partial premium net of the near-certain $1 winner loss), and the candlestick proxy is queue-blind and biased upward (78% of the edge traces to sub-100-contract-volume income legs; survives a modest vol≥50 haircut at +$0.026 [+0.004,+0.049] but the fill↔winner adverse-selection correlation is unmodeled). `kb/strategies/00-index.md` **S14: idea → data-collecting** (the project's first non-DEAD candidate, explicitly NOT a proven edge — still 0 proven edges overall; remaining binding gate is a queue-aware L2/depth fill-sim over `tape/orderbook_depth/`). Lessons **L39** (queue-blind candlestick proxy biases the income leg up; decompose by income-leg volume before any fillability claim) + **L40** appended. See `findings/2026-07-13-ladder-underwriting-s14-firstcut.md`. 642 tests green (621 prior — including the concurrently-merged nightly edge-hunter PR #53's 17 new S17 burst-mode tests — + 21 new), `invariants --full` green (only the two expected non-gating advisories). Rebased onto PR #53 (S17 burst-mode scanner, Q19 PREP) after it merged concurrently mid-run; both runs picked different eligible queue items off the same replenished pipeline, no duplicate work. Step 9: `execution/strategy_api.SHADOW_REGISTRY` still empty — no-op.
- 2026-07-13T06:xxZ (research loop) · claim-check + stranded sweep (1405 lines, PR #55 merged) + Q20 CLOSED (anatomy only, no registry flip) · overround decomposition: 97.4%(BTC)/84.3%(ETH) in wings, depth join refutes "quote-only", active-band BTC no-edge/ETH exploratory; verifier CONFIRMED-WITH-CAVEAT. See kb/00-LOG.md.
- 2026-07-13T09:xxZ (research loop) · claim-check + stranded sweeps (869 lines PR #57 + 240-line reconciliation PR #58) + Q22 CLOSED: S14 wired as first-ever paper shadow strategy · found+fixed a real PaperBroker gap (no short model, no settlement/expiry mechanism — `Fill.price` can't hold $0/$1) before trusting any strategy code: short-YES represented as buy-NO held to settlement (cent-for-cent reconciled against `s14_ladder_fillsim`), new `Settlement` record type (sibling of `Fill`, never loosens it). First paper pass: 10 event-hours processed, 200 orders/89 fills/89 settlements, realized P&L **+$1.83** (evidence, not a verdict — S14 registry status unchanged). 290 deferred(caps) as expected, cap not raised. 690 tests green, invariants green. See kb/00-LOG.md.
- 2026-07-13T12:xxZ (research loop) · claim-check + stranded sweep (1,619 lines, PR #61 merged) + Q21 idea-gen round: S19 registered (idea, verifier two-agent-confirmed), 3 killed at idea stage, Q23 added · S19 = elevated-wing stale-ask maker fade on crypto ladders (the S10-maker/L26 untested direction), binding gate = queue-aware `orderbook_depth` fill-sim + adverse-selection conditioning + L27 magnitude gate, honest expectation DEAD. Killed: sports overround-underwriting (L31 wing artifact, S13/L30 fee death), cross-venue held-to-settlement box (Polymarket NO-ask not in tape, reduces to Q19's already-queued scan), post-release econ-ladder fade (Kalshi closes CPI/econ markets ~5min before the print — empty fill window). Still 0 proven edges. Step 9: SHADOW_REGISTRY non-empty but idempotent re-run confirmed 0 newly processed, P&L unchanged at +$1.83. 690 tests green, invariants green. Branch deletion 403'd (documented, not retried). See kb/00-LOG.md.
- 2026-07-13T15:xxZ (research loop) · claim-check + stranded sweep (1,446 lines, PR #63 merged) + Q23 CLOSED: S19 verdict DEAD, verifier-CONFIRMED · queue-aware `orderbook_depth` `no_bids` fill-sim (not an L39 candle print) over 895 `wing_elevated` members/175 event-hours: 0.45% fill rate (4/895, 1.00% among 402 joinable) — below S14's 2.5% benchmark and the near-zero floor; filled population only 2 event-hours (< 10-unit data-adequacy floor) so the +$0.355 win-leg CI [+0.285,+0.425] is a resampling artifact, not an edge (0/895 wings ever settled YES — the predicted toxic leg unsampled, not disproven). S10-maker/L26 now tested-dead. `kb/strategies/00-index.md` S19 flipped idea→dead ✗. Still 0 proven edges. Step 9: paper pass idempotent, 0 new processed, P&L unchanged at +$1.83. 712 tests green, invariants green. See kb/00-LOG.md.
- 2026-07-13T18:xxZ (research loop) · claim-check + Q24 CLOSED: S21 registered dead ✗ (DEAD by data-adequacy), verifier-CONFIRMED · maker-side rich-ASK selling on sports longshots (H1, the S7c-mirror maker-sell S13's bid-side test never covered). Queue-aware `orderbook_depth` `no_bids` fill-sim (L39, not a candlestick print) delegated to an edge-prober, independently verified CONFIRMED-WITH-CAVEAT (caveat = a cosmetic 80/80→81/81 script literal fixed separately; the real number is 81/81). **The mandated join is 0/81 joinable (0.00%)** at `fair_prob ≤ 0.20` (0/83 for the `yes_ask ≤ 0.20` proxy): `sports_clv` fair anchors cover kickoffs ≤07-03 while sports `orderbook_depth` began ≥07-07 — every fair-anchored game had settled before the depth tape began (L9 non-overlap; the calendar date is embedded in the ticker so zero event/outcome overlap is structural, verifier reproduced 0 by bypassing the probe's join code). Fill rate 0.00%, no testable CI (n_units=0) → **DEAD by data-adequacy, NOT a CI falsification** — the edge-at-quote stays S7c-proven-rich (+2.35¢), only the maker FILL question is untested/unmeasurable on current tape (re-testable only on concurrently-collected fair-anchor+depth tape). Settlement ADEQUATE (81/81 settled, 8/81=9.88% YES); the sold-longshot-WINS negative-skew leg fully modeled (`premium−1−fee`≈−0.86 settle-YES, flat $0.01 maker fee via `core.pricing`, L18/L30). Steelman: 346/652 (53%) of depth-overlapping ask≤0.20 longshots carry a queue, MEDIAN queue-ahead 485 contracts (confirms the binding-risk thesis), but full-sim-eligible = only 3 markets << the 10-game floor; alternate paths verifier-confirmed 0. Prices tagged `real_ask`/`real_bid`/`broker_truth`/`synthetic`; bootstrap by GAME (L6). `kb/strategies/00-index.md` S21 registered dead ✗ (closes the S7 family: taker S7c / maker-bid S13 / maker-ask S21 all DEAD); still 0 proven edges. Citation note `kb/quant-finance/favorite-longshot-bias.md` distilled (3 favorite-longshot-bias sources, S14 factor cap). Lessons L43 (collector-alignment recurrence of L9) + L44 (`worldcup2026.jsonl` offline sports executed-volume source) appended. 742 tests green (30 new Q24 tests), `invariants --full` green. See `findings/2026-07-13-q24-sports-longshot-maker-fillsim-verdict.md`.
- 2026-07-13T21:xxZ (research loop) · claim-check (no open PRs; step 0b sweep skipped, only unswept branch `tape/hourly-20260713T2056Z` <30min old) + Q25 CLOSED: depth-tape anatomy scan, discovery-class, verifier CONFIRMED-WITH-CAVEATS · Step 0a: `origin/main` HEAD (`70416b0`) descends from all recently-merged PRs (#66/#65/#64/#63/#62, checked via GitHub MCP + local ancestry); `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` file both 2026-07-13, 0-day gap. `main` not rewound. `tape/orderbook_depth/` (largest tape family, 3-4x everything else combined, L38) read as a discovery scan for the first time via `scripts/q25_depth_tape_anatomy.py` (33 offline tests): 122,238 records/31 families/6 days (07-09 honestly absent) tabulated by family and category×time-to-close bucket — queue depth, staleness/streak distribution, one-sidedness, and a defined resting-order-turnover proxy benchmarked against S19's 0.45% dead floor and S14's 2.5% wing benchmark (turnover rules a cell OUT, never IN). Plausibly-fillable churn: WNBA 11.06%, UCL soccer 8.56%, KBO baseball 8.35% (also least-frozen, 33%), MLB 7.62%, NPB 6.92% — near-close sports runs 7-13%. Dead-thin: KXBIG3GAME 0.48% (on the S19 line), VBA/USLCup/MLS all <2%. One-sidedness (L31) confirmed crypto-only (96-100% vs sports' 0-1% pre-close). Corrected the milestone spec's own worked example mid-run: crypto's ticker hour token is ET, not UTC (confirmed against tape + `collection/crypto_hourly.py`'s docstring) — a UTC reading would have mis-bucketed all 45,505 crypto captures. Verifier independently recomputed every number from scratch — CONFIRMED; one dispute (an undercounted 15/114 vs correct 21/114 insufficient-cells meta-stat) resolved by the producer recomputing from the committed JSON and correcting doc text only (no number/code/test touched) — net CONFIRMED-WITH-CAVEATS (two disclosed, immaterial caveats). 4 lessons appended (L45 crypto-hour-is-ET, L46 sports-tz-unverifiable, L47 fractional depth sizes, L48 turnover-rules-out-never-in). Still 0 proven edges — a map to seed future Q21 rounds. 784 tests green (751 prior + 33 new), `invariants --full` green. See `findings/2026-07-13-depth-tape-anatomy-q25.md`, `findings/depth_anatomy.json`, `kb/00-LOG.md`.
- 2026-07-14T00:xxZ (research loop) · claim-check (no open PRs) + stranded sweep (1,011 lines) + idle run: L45→L49 shared crypto-hour close-time helper + PaperBroker determinism bug found/fixed · Q0-Q25 all DONE/DEAD, Q19 per-event legs still time-gated ahead of today's CPI burst window — idle-run policy (a): built `core/timeutil.parse_crypto_hour_token_close_utc` (ET-localized, DST-correct) so Q25's inline hand-rolled logic has an importable home for the next probe (10 new tests, edge-prober house style updated), appended lesson L49. While driving `pytest` green (protocol step 4, not the chosen milestone) found `execution/paper_broker.py`'s daily-order cap read real wall-clock instead of the paper tier's own `context.now_ts` contract — the same ledger replayed on two different real days gave two different cap decisions, breaking `test_paper_pass.py`'s cap test the moment the real calendar rolled to 07-14. Fixed by threading `as_of` through `PaperBroker`/`paper_pass.run_pass` (2 new tests). Step 9: real paper pass over new tape, 10 more event-hours processed (20 total), P&L +$1.83→+$5.14, idempotent re-run confirmed. 796 tests green, invariants green. See kb/00-LOG.md.
- 2026-07-14T03:xxZ (research loop) · claim-check (no open PRs; `git fetch origin main` clean, `origin/main` HEAD `cbbb5f5` not rewound — `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` file both 2026-07-14, 0-day gap) + stranded-tape sweep (1,531 lines: 2 branches postdating the last sweep's `...2257Z` cutoff — `tape/hourly-20260713T2356Z` + `tape/hourly-20260714T0202Z`, both >30min old — union-appended orderbook_depth +1223, sports_pairs +266, polymarket_macro_pairs +30, polymarket_pairs +8, crypto_hourly +4; newest branch `...0257Z` skipped, ~12min old) + **Q21 idea-gen round** (queue drained to 0-1 non-blocked research items — Q19's per-event legs still time-gated ahead of the Jul-14 CPI burst window — Q21's STANDING re-eligibility trigger fired). Delegated to `research-lead`: 3 candidates proposed, each independently `verifier`-reviewed (two-agent rule) — **REGISTER ×3, 0 killed at idea stage**. **S22** (OFI/depth-imbalance settlement predictor on Q25's high-churn two-sided sports cells — diversity-floor candidate, drawn from Q25's anatomy scan + a newly-distilled paper, Cont/Kukanov/Stoikov 2014 OFI, `kb/quant-finance/order-flow-imbalance.md`), **S23** (favorite-side settlement-underpricing maker, favorite-longshot bias with NO devig/odds-api dependency — sidesteps S21's L43 join-emptiness death by sourcing settlement ex-post over the depth tape's own window), **S24** (near-close hourly-return overreaction fade, weakest of the three, explicit anti-overlap guard vs S22). Queue items Q26/Q27/Q28 added. New lesson L50 (settlement-leg-over-own-window as the general S21-style disjoint-join fix). Still 0 proven edges — restocks the hypothesis pipe by three idea-stage candidates, the bar hasn't moved. Step 9: `SHADOW_REGISTRY` non-empty (`s14_ladder_underwriting`) — ran `paper_pass.py`, 0 newly processed this pass (280 deferred(caps) — today's `MAX_DAILY_ORDERS` already spent by the 00:15Z pass, 44 deferred(coverage), 20 already-in-ledger); `daily_summary()` unchanged: 0 open positions, 158 settled contracts, realized P&L +$5.14, cash +$5.14. Docs-only Q21 round (no code/test/tape touched by it); combined with the tape sweep, 796 tests green (unchanged), `invariants --full` green (only standing non-gating L20/L29 advisories). See `kb/00-LOG.md`.
- 2026-07-14T09:xxZ (research loop) · claim-check (no open PRs; `origin/main` HEAD `f35da31` not rewound — last 5 merged PRs all ancestors, `kb/00-LOG.md` newest entry and newest `tape/*/dt=*` file both 2026-07-14, 0-day gap) + stranded-tape sweep (2,265 lines: 6 branches >30min old — `...0202Z`/`...0257Z`/`...0356Z`/`...0659Z`/`...0755Z` (07-14) + `...2356Z` (07-13) — union-appended orderbook_depth +1926, sports_pairs +297, polymarket_macro_pairs +30, polymarket_pairs +8, crypto_hourly +4) + **Q26/S22 probe** (topmost eligible TODO, first of the three Q21 survivors). Delegated to `research-lead` → `edge-prober` → `verifier` (two-agent rule); built `scripts/q26_ofi_depth_imbalance_probe.py` (4-gate structure, 21 offline tests) testing whether L2 book-imbalance predicts settlement beyond the mid on Q25's high-churn two-sided sports cells. **Gate 1 (join adequacy) passed clean**: 205 joinable games (20× the 10-game floor) via a cached live settled-markets pull over the depth tape's own window (L50's fix confirmed working). **Gate 2 (calibration precheck) hard-killed it**: on the disagreement subset (n=86/81 games) imbalance hit 27.9% vs the mid's 72.1%; verifier confirmed this is genuine (the two rates are mechanically complementary on this subset, not a masked sign-flip contrarian edge) and robust across every time-to-close cut. Gates 3/4 never reached. **S22 flipped `idea → dead ✗`**, verifier-CONFIRMED. Two lessons appended: L51 (disagreement-subset calibration hit-rates are complementary, not independent) and L52 (Kalshi sports settlements aren't always binary — 8/458 were `result:"scalar"`). Still 0 proven edges. Step 9: `SHADOW_REGISTRY` non-empty (S14) but idempotent — 0 newly processed (daily cap already spent earlier today), P&L unchanged at +$5.14. 817 tests green (796 prior + 21 new), `invariants --full` green. See `findings/2026-07-14-ofi-depth-imbalance-s22-verdict.md`, `kb/00-LOG.md`.
- 2026-07-14T12:xxZ (research loop) · claim-check + step-0b sweep (612 lines, 4 branches: 07-13 T0457Z + T1755Z, 07-14 T0257Z + T0356Z — crypto_hourly +4/+4, polymarket_macro_pairs +30/+30, polymarket_pairs +8/+8, sports_pairs +245/+283) + **Q27/S23 DEAD-by-fee, verifier-CONFIRMED** (registry idea → dead ✗). Second of the three Q21 survivors: favorite-side settlement-underpricing maker, favorite-longshot bias with NO devig/odds-api dependency — `scripts/q27_favorite_underpricing_fillsim.py` (read-only, 24 offline tests) queue-aware `yes_bids` fill-sim (L39) over `tape/orderbook_depth/` joined to ex-post Kalshi settlement (L50, `tape/q27_settlement_cache/settlement.json` `broker_truth`). G4 join adequate (24 distinct games ≥10 floor), G3 fill 95.83% ≫ S19 0.45% floor (dies on the EDGE, not fill/adequacy — L53), G2 catastrophic favorite-loses leg fully modeled (L41). Kill: favorite win-rate **0.6957 (16W/7L)** < breakeven **0.7361** (mean fill $0.7261 `real_bid` + 1¢ maker fee, L30) → favorites RICH at the bid, bias absent/reversed (L54). Block-boot by GAME n=23: mean −$0.0404, 95% CI [−0.2435,+0.1370], admissible PASS (16 opposing clusters) / tick-magnitude FAIL; even max-generous all-24-filled fails the tick gate. Same factor slot as S14/S21 — closes the favorite-longshot / S7-family maker lens DEAD (S13/S21/S23). L53/L54/L55/L56 appended. Still 0 proven edges. Step 9: paper pass idempotent, 0 newly processed, P&L unchanged +$5.14. 841 tests green (817 prior + 24 new), `invariants --full` green. See `findings/2026-07-14-favorite-underpricing-s23-verdict.md`, `kb/00-LOG.md`.
