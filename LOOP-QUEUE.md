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
   **(e — added 2026-07-14, Ryan local session; check FIRST, before (a)–(d)):** if any
   alive candidate's registry row names a binding gate with no corresponding TODO queue
   item, WRITE that queue item as this run's unit of work. (S14's queue-aware fill-sim
   gate sat unqueued through a full idle run on 2026-07-14T00Z — this clause exists so
   that never recurs.)
   The step-0b sweep still runs, but "sweep only" is no longer a valid run outcome.
4. Gates before ANY commit: `pytest` green AND `python scripts/invariants.py --full` green.
5. Bookkeeping: update the item's Status line in this file; append one dated entry to
   `kb/00-LOG.md` (match its existing format); findings → `findings/`; strategy status
   changes → `kb/strategies/00-index.md`; append one line to the run ledger at
   `ops/run-log.md` (moved 2026-07-15 — formerly the "Log of runs" section below).
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
Status: PER-EVENT CPI DONE (2026-07-14, research loop) — descriptive + PROVISIONAL, verifier
CONFIRMED (all descriptive numbers) / REFUTED (both tradeable claims); **NO registry flip** —
S17 stays `data-collecting`, kill/live decision deferred to FOMC (Jul 29) as mandated. Ran
`s17_leadlag_probe.py --burst-window 2026-07-14T12:05:00Z 2026-07-14T13:46:00Z` over the swept
June-CPI burst tape (`tape/polymarket_macro_pairs/`, 15 fed-decision `real_ask` pairs). Tape
**ADEQUATE** — the first sub-hourly cross-venue macro shock tape S17 has ever had: 101 captures
@ median 60.1s bracketing the 12:30Z CPI print. **Lead-lag:** the apparent "Polymarket leads
Kalshi" on the July buckets (rho_poly 0.902/0.777) is a SINGLE-TICK artifact — removing the one
12:30:13Z release capture collapses it to noise (0.196/0.037) and the residual sign is unstable
(flips toward Kalshi on leave-one-out) → **no defensible directional lead-lag claim**.
**Dislocations:** 25 fee-clearing captures / 11 episodes, but WIDTH x DURATION splits cleanly —
the two largest ($0.079/$0.06, `real_ask` both legs net Kalshi taker fees) are single-capture
12:30:13Z release-instant transients (size-blind — macro_pairs has no depth field; a
non-synchronous stale-Kalshi-quote artifact per the single pass-level `captured_at`), the durable
ones small ($0.01-0.04) S6/L31 stale-nominal-basis → **no clean fillable shock-scale edge**.
Lesson **L57**. See `findings/2026-07-14-s17-burst-cpi-q19.md`. Remaining PER-EVENT legs: WC
semis (Jul 14/15), WC final (Jul 19), **FOMC (Jul 29 — the S17 decision event)**.
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
Status: ROUND COMPLETE (2026-07-15, kalshi-edge-hunter) — re-eligibility trigger fired again
(eligible items = 0). Proposed **3 new candidates, ALL killed at idea stage by independent
`verifier` attack → 0 registered** (two-agent rule at the idea stage). **S25** (post-print
within-Kalshi known-outcome pickoff) DOA — the resolving-month CPI ladder closes ~5 min *before*
the print (`close_time` 12:25/12:29Z < 12:30Z release), no post-print market exists. **S26**
(Polymarket-anchored single-venue Kalshi macro convergence) — the ask-to-ask gap is mostly Kalshi's
own 9–11¢ spread (Poly inside Kalshi's bid-ask 62.6% of entry-met records); the genuine remainder
is a directional macro bet (S2/S16), gate un-runnable (0 meetings resolved). **S27** (macro-print
overshoot fade) — same close-before-print structure + forward-month ~0.88 spreads = S24's round-trip
trap on econ tape. Lessons **L61/L62/L63**. Still 0 proven edges; queue now genuinely empty → next
research firing is an IDLE RUN (v3 policy). See `findings/2026-07-15-q21-idea-gen-round.md`.
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

Seed material (added 2026-07-14, Ryan local session): `findings/2026-07-14-idea-seeds.md`
— 8 angle seeds (cross-horizon term-structure nesting, platform-wide implication graph,
listing-age anatomy, S6-at-burst-resolution re-cut, perp-funding prior, Polymarket
flow-as-signal at burst resolution, nowcast-leg retry, team-news shock fade). Future Q21
rounds and the nightly edge-hunter draw from this list FIRST before free-generating;
every registration still passes the full verifier gate — seeds are input, not approval.

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

### Q29 — S14 binding gate: queue-aware L2/depth fill-sim, first cut (POSITION = PRIORITY — deliberately inserted above Q26)
Status: TODO (added 2026-07-14, Ryan-approved local session; merged 07-15 after the S22–S24
round completed and died. Numbering is chronological, position is priority: S14 is the
project's only positive-proxy `data-collecting` candidate, and its registry-mandated binding
gate was never given a queue item. Q26–Q28 below are now DONE/DEAD, so this is the topmost
eligible item.)
The gate, verbatim from S14's registry row: a **queue-aware L2/depth fill-sim** over
`tape/orderbook_depth/` (short-YES queue read off the mirror `no_bids` side) modeling queue
position + the fill↔winner correlation, CI>0 @ real asks over ≥30 event-days.
**Pre-declared scope for this first cut:** only ~7 depth days exist, so THIS RUN CANNOT
GRADUATE S14 no matter what number comes out — its purpose is to convert the candlestick
proxy (+$0.0925 CI [+0.063,+0.123], queue-blind, biased up, 78% of edge from sub-100-vol
legs) into a queue-aware read and measure the proxy's bias direction and magnitude.
Milestone (one read-only probe): `scripts/s14_depth_fillsim.py` over the BTC/ETH crypto
families — for each event-hour ladder, model resting short-YES on every member via the
mirror `no_bids` queue (L39, NOT a candlestick print; reuse the S19/Q24 queue machinery),
keep the near-certain $1 winner leg INSIDE the P&L (never conditioned away — L41 / Q24
gate-2), fees via `core.pricing` (flat 1¢ maker, L30), block-bootstrap by EVENT-HOUR,
route through `core.bootstrap.bootstrap_verdict_admissible` + `clears_tick_magnitude`
(L41/L27). Deliverables: (1) per-leg queue-aware fill-rate distribution vs the proxy's
implied fills — name the phantom fraction; (2) the first queue-aware P&L CI; (3) a note on
whether the S14 paper shadow's PaperBroker `fill_model` assumptions diverge from the
queue-aware read (the +$5.14 ledger is evidence only under its stated fill model).
Verdict handling (two-agent rule): decisively negative + admissible → registry flip DEAD
(verifier-confirmed); income-leg fill rates collapsing toward the S19 0.45% floor → the
proxy edge is largely phantom, report honestly, S14 stays `data-collecting` with the
shadow re-based; positive → S14 stays `data-collecting` (NOT proven) and keeps
accumulating toward the ≥30-event-day graduation bar.

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
Status: DONE (2026-07-14, research loop) — **verdict DEAD by round-trip, verifier-CONFIRMED.**
`scripts/q28_s24_nearclose_fade_probe.py` (+13 offline tests) block-bootstraps a real_ask-entry/
real_bid-exit fade round-trip on ≥2¢ near-close mid jumps (7 Q25 high-turnover two-sided sports
cells): n=123 games/739 trades, mean −$0.02936, 95% CI [−0.05179,−0.00587] — strictly < 0, robust
across X∈{2..5}¢. Anti-overlap hold-to-settlement leg also fails to clear (CI straddles 0) → does
NOT collapse into S22. Independent verifier bit-for-bit reproduced every number plus a from-scratch
re-implementation; confirmed no fee/lookahead/cluster-degeneracy defects. `kb/strategies/00-index.md`
S24 flipped idea → dead ✗. Still 0 proven edges. See `findings/2026-07-14-nearclose-fade-s24-verdict.md`.
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

### Q30 — Concurrent fair-anchor + depth coverage (S11's fill leg; unlocks the S21/L43 re-test) — TIME-SENSITIVE: WC final Jul 19
Status: TODO (added 2026-07-14, Ryan-approved local session)
Why: S21 died by data-adequacy (L43/L9 — fair anchors and depth tape never covered the same
games). Since Q18 closed (07-13) the odds leg writes live `matched` fair anchors into
`tape/sports_pairs/` AND `orderbook_depth` captures the same discovered tickers — concurrency
now exists in principle but is THIN (1 bookmaker / 2 games at Q18 close). Milestone A (now,
one run): MEASURE it — count games since 07-13 with BOTH a matched `odds_leg` record and ≥1
same-ticker depth snapshot; report the joinable-game rate; then implement whatever
quota-respecting odds-api widening (sport keys / regions / bookmaker set, within the 500/mo
free tier — check remaining quota first) raises it, inside `collection/odds_api.py`'s existing
quota-discipline rules. Milestone B (gated: ≥10 concurrently-covered SETTLED games — expect
~1–2 weeks; the WC final Jul 19 is the liquidity peak, don't miss it): re-run the S21
maker-ASK fill-sim per L43 AND the S11 selective-maker fill-sim (rest ONLY the EV+-vs-devig
side), same gates as Q24 (L39 queue-aware, L41 admissible, L27 magnitude, two-agent rule).
Kill/limits: if the free tier cannot cover ≥1 sport at usable frequency, report the exact
quota math — that fact gates S11 honestly; never burn quota to fake coverage.

### Q31 — Sub-hourly VPS capture leg (the cadence-floor fix) — code now; VPS install = Ryan/local
Status: TODO (the code + offline tests are cloud-buildable; the cron INSTALL is
BLOCKED(vps-access) — Ryan or a local session with SSH does that step)
Why: three separate deaths/caveats were data-adequacy-by-cadence (S9 lead-lag, S6's
fill-sim quality scope, S24's declared washout risk). The hourly floor is a claude.ai
routine limitation, NOT a VPS limitation — a VPS cron at minutes-scale costs zero Claude
tokens and converts token spend into data quality. Milestone: build
`collection/subhourly_pass.py` — a lightweight pass capturing ONLY (1) L2 depth for
near-close two-sided high-churn sports cells (Q25 map: WNBA/UCL/KBO/MLB/NPB) within
~T−90min of close, (2) crypto ladder+depth in the final ~15 min pre-close, (3) econ ladders
inside scheduled release windows (reuse `collection/burst_capture.py` family logic where it
fits); target cadence 5 min; hard per-pass caps (family whitelist, max tickers, expected-
lines budget) so incremental tape stays bounded (~<5k lines/day); same per-day JSONL append
shape + honest completeness accounting as `hourly_pass`; offline tests. Deliverable includes
the exact crontab line (offset from the :26 hourly) + a one-paragraph install doc in `ops/`.
NOTE for Ryan: this generalizes the hand-made burst-trigger class — future CPI/NFP/game-end
windows stop needing one-shot cloud triggers at all.

### Q32 — IBKR data leg: ZQ-implied Fed path for S2-full / S16 — offline prep now; live leg = Ryan
Status: TODO (offline prep is cloud-runnable; the live connection is BLOCKED(ibkr-activation)
— credentials exist ONLY on the VPS (`/root/.secrets/ibkr.env`, IB Gateway installed).
READ-ONLY MARKET DATA, zero order-placement code anywhere — Stop rules unchanged.)
Why: S2-full (FOMC × ZQ — the structurally cleanest gated candidate, +3.4¢ overround, 3×
cleaner than weather) has been gated on CME data since 06-19, and S16 is BLOCKED on the
FedWatch bot-wall. Ryan already owns an unused IBKR basic-subscription key. ZQ futures
prices → implied meeting-path probabilities is pure arithmetic (FedWatch itself is derived
from exactly this). Milestone (offline): build `core/fed_path.py` — ZQ price → implied
average rate → per-meeting step probabilities, methodology documented, unit-tested against
published FedWatch snapshots committed as fixtures — plus a collector skeleton with a mock
feed writing `tape/zq_fed_path/`, so the day the IBKR leg goes live it starts collecting
immediately. Source tags: `broker_truth` for IBKR-delivered prices, `synthetic` for every
derived probability (Rule #3 discipline). First live target: FOMC Jul 29 (burst trigger
already scheduled — intraday ZQ around that window would give S2 its first real event).
NOTE for Ryan: activation = start IB Gateway on the VPS + a ~30-line runner; say the word
in any local session.

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

## Log of runs — MOVED to `ops/run-log.md` (2026-07-15)

The per-run ledger lives in `ops/run-log.md` now (same one-line format, append-only).
Rationale: this queue file is read in full by every research run; the ledger grows
forever and was ~40% of the file. Append your run line THERE, not here. Any run that
cloned before this change and appended a line below this header instead: the next run
moves it over during step 5 bookkeeping.
