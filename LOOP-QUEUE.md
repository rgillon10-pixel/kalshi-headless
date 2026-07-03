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

## Stop rules (non-negotiable)

- NEVER write order/execution code, never touch credentials, never place a trade. Capital
  requires an in-person sign-off from Ryan that no cloud run can obtain — by design.
- An edge is "proven" ONLY by a block-bootstrapped 95% CI strictly > 0 at `real_ask` prices
  net of fees. A DEAD verdict is a success — record it honestly and move on.
- Never relax an invariant, never delete or reorder queue items; append, don't rewrite.
- Timebox: if a milestone isn't converging, commit honest partial state with an
  IN-PROGRESS note rather than forcing a result.

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
Status: TODO (2026-07-03) — egress unblocked (Q0b)
One stage per run:
**S7a** — source last-season NFL/NBA (+ any completed 2026 World Cup) Kalshi market history
via public candlesticks + a free historical closing-odds source; document provenance in the
finding. **S7b** — probe `scripts/sports_clv_s7.py`: Kalshi ask vs de-vig fair at decision
time, fee model consistent with `scripts/fee_breakeven.py`. **S7c** — block-bootstrap by game
→ 95% CI, verdict, `findings/<date>-sports-clv-s7.md`, update registry + this file.

### Q5 — S8 first cut from free candlesticks (crypto settlement basis)
Status: TODO (2026-07-03) — egress unblocked (Q0b)
Same trick as S2's first cut: public candlesticks on crypto-hourly markets vs public spot
history. FIRST the ρ-guard — if spot-vs-settle ρ≈1 the feed-mismatch thesis dies cheap →
mark S8 DEAD in the registry and here. Only if the guard passes: final-minutes basis vs
overround at real asks, block-bootstrap by hour.

### Q6 — Daily anomaly sweep (serves S3 + free-money detection)
Status: TODO (2026-07-03) — egress unblocked (Q0b)
`scripts/anomaly_sweep.py`: one pass over all active markets — bracket sums vs $1 + fees
(true arb), cross-strike monotonicity violations (S3). Flag ONLY violations clearing the fee
floor. Append `tape/anomalies/`. Wire into Q3's 09 UTC slot when both exist.

### Q7 — S10 reachability-decay probe from accumulated crypto tape
Status: BLOCKED(needs ≥7 days of Q2 tape)
T−5/T−2 far-bracket ask vs remaining-time reachability; must clear the artifact noise floor
+ the chunky longshot fee.

## Log of runs

(append one line per run: `<UTC ts> · <item> · <one-line outcome>`)

- 2026-07-02T22:43Z · Q0 · all 4 required hosts (Kalshi REST, Coinbase, Kraken, the-odds-api) BLOCKED by org egress policy (proxy CONNECT→403); Q1–Q6 marked BLOCKED(egress policy) pending Ryan widening the sandbox allowlist.
- 2026-07-03T00:08Z · Q0b · egress now open on all 4 hosts (Kalshi 200, Coinbase 200, Kraken 200, the-odds-api 401=reachable); `capture_orderbooks.py --limit 3` proved live. Q0b DONE, Q1/Q2/Q4/Q5/Q6 flipped BLOCKED(egress)→TODO; ODDS_API_KEY still absent (Q1 odds leg stays BLOCKED(key)). Proceeding to Q1 (time-sensitive, World Cup) per Q0b's own continue-instruction.
- 2026-07-03T00:14Z · Q1 · built `collection/sports_pairs.py` (discover→confirm→capture, real_ask BBO + bracket_sum/overround via core.pricing) + 19 unit tests; live pass captured 188 confirmed moneyline games (16 series incl. 10 World Cup) to `tape/sports_pairs/dt=2026-07-03.jsonl`, all complete, mean overround +21.3¢ real_ask. Odds-api leg stays BLOCKED(key); de-vig math implemented+tested but unused live.
- 2026-07-03T (reconciliation, out-of-band) · protocol fix + Q1 dedup · root cause found: cloud sessions cannot `git push origin main` (permission boundary, not a rebase race — both prior runs rebased clean, merge-base==main tip, yet both still fell back to their own branch). Two consecutive firings (`claude/brave-mccarthy-ek6ybp` 23:18Z, `claude/brave-mccarthy-7rnhry` 00:17Z) independently rebuilt Q1 from scratch as a result, each stranded on its own branch, no PR opened either time. Reconciled onto one branch: kept 7rnhry's collector (structural title-regex confirmation, not ticker-suffix alone), folded in ek6ybp's tape capture, merged to `main` via PR. Rewrote protocol steps 0/6: claim-check open PRs before picking work, push-branch+PR+auto-merge-if-green instead of push-to-main-with-branch-fallback — this is the actual fix, not just this run's cleanup.
- 2026-07-03T05:14Z · Q2 · claim-check: no open PRs, `main` in sync. Built `collection/crypto_hourly.py` (current-hour bracket book real_ask + previous-hour broker_truth settlement via pure hour-token arithmetic + Coinbase/Kraken-fallback synthetic spot) + 21 unit tests; live pass captured BTC+ETH both `pass_complete` to `tape/crypto_hourly/dt=2026-07-03.jsonl`. Excluded a stray long-lived same-grammar group via a close-open duration filter (would otherwise have silently mixed a week-old group into "current hour"). Notable: BTC bracket overround +$9.27 real_ask (188-member fine-band ladder) — flagged un-investigated for Q5, not a verdict. Q3 flipped BLOCKED→TODO (both its dependencies now built). Gates: 89 tests green, invariants green.
- 2026-07-03T10:12Z · Q3 · claim-check: no open PRs, `main` in sync at f6c946a. Built `collection/hourly_pass.py` — the hourly routine's single entry point: calls `sports_pairs.run()` + `crypto_hourly.run()` independently (one raising never kills the other), ANDs their own honest `completeness_ok` signals, sums `n_markets`/`n_lines` by reading back only the tape lines this pass just wrote (filtered by `capture_id`, so prior passes' lines in the same append-mode file aren't double-counted), and runs `scripts/anomaly_sweep.py` as a subprocess only during the 09 UTC hour (reports `not_built` honestly since Q6 doesn't exist yet — never silently skipped without a trace). 15 new unit tests (offline, injected stub sub-passes, no network): completeness AND-ing, fault isolation on either sub-pass raising, the 09-UTC-only anomaly slot (not-built/ok/error/raises), the tape-accounting helper, and CLI flag wiring. Live smoke: `--sports-limit 3 --crypto-symbols BTC` (188 markets, 1 line) then a full unlimited pass (193 sports games + 2 crypto symbols = 680 markets, 195 lines, completeness ok) — both appended to today's tape. Gates: 104 tests green (89 prior + 15 new), `invariants --full` green.
- 2026-07-03T15:25Z · ops (local, Ryan-approved) · VPS collector live: Hetzner box cleared of the dead weather apparatus (archiver services disabled, weather crons commented, 32G of weather-only tape/caches deleted after a sampled 123M-row audit found 100% KXHIGH/KXLOWT/UH* series — zero sports/crypto overlap with S7–S11), `kalshi-headless` cloned at `/root/kalshi-headless` with a write deploy key, hourly cron at :23 UTC (offset from cloud collector's :53), first live pass 645 markets / 178 lines / completeness ok pushed as 36c7f4e. Odds-api key slot prepared on the VPS (see Q1 note). Stale `tape/hourly-*` branches pruned (contents verified on main).
