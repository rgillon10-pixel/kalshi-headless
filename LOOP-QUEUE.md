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

### Q7 — S10 reachability-decay probe from accumulated crypto tape
Status: BLOCKED(needs ≥7 days of Q2 tape)
T−5/T−2 far-bracket ask vs remaining-time reachability; must clear the artifact noise floor
+ the chunky longshot fee.

### Q8 — Build Kalshi↔Polymarket World Cup round-market collector (serves S9) — new, 2026-07-04
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
