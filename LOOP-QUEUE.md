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

1. Read `CLAUDE.md`, this file, `kb/strategies/00-index.md`.
2. Env: `pip install -e ".[dev,analysis]"` (venv optional in a throwaway sandbox).
3. Pick the TOPMOST item whose status is TODO or IN-PROGRESS (skip DONE / BLOCKED / DEAD).
   Do ONE milestone (~one focused stage). If the item blocks mid-run, set its status to
   `BLOCKED(<reason>)` and move to the next eligible item.
4. Gates before ANY commit: `pytest` green AND `python scripts/invariants.py --full` green.
5. Bookkeeping: update the item's Status line in this file; append one dated entry to
   `kb/00-LOG.md` (match its existing format); findings → `findings/`; strategy status
   changes → `kb/strategies/00-index.md`; append one line to "Log of runs" below.
6. Git: `git pull --rebase origin main` → commit (message conventions from history:
   `build:` / `probe(Sx):` / `tape:` / `docs:`) → `git push origin main`. If push is still
   rejected after 3 rebase+retry cycles, push to `cloud/run-<YYYYMMDDTHH>Z` and say so.
7. Final message must be EXACTLY this shape — it is Ryan's phone digest:

   ```
   RUN DIGEST
   - Done: <one line>
   - Found: <key numbers; any price carries its price_source_tag>
   - Next: <one line>
   - Repo: <short sha> → <branch>
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
Status: DONE (2026-07-02) — all 4 hosts BLOCKED by org egress policy; see `tape/cloud-env-check.md`
Verify from the cloud sandbox and record results in `tape/cloud-env-check.md`:
(a) Kalshi public REST via `python -m collection.capture_orderbooks --limit 3`;
(b) public crypto spot (Coinbase `GET https://api.exchange.coinbase.com/products/BTC-USD/ticker`
and/or Kraken equivalent);
(c) whether `ODDS_API_KEY` exists in env (do NOT print it) and the-odds-api reachability.
Any blocked host → mark the dependent queue items `BLOCKED(<host>)`.

### Q0b — Egress re-verify (self-healing; stays TODO until it succeeds)
Status: DONE (2026-07-09) — all 4 hosts now REACHABLE (Kalshi REST 200, Coinbase 200,
Kraken 200, the-odds-api 401 MISSING_KEY = reachable, no key). Egress allowlist was
widened since the 2026-07-02 check. See `tape/cloud-env-check.md` for full re-verify.
Every `BLOCKED(egress ...)` status below flipped to TODO (Q1 additionally completed its
build this same run — see its Status line).
Cheap check, run FIRST while any item is `BLOCKED(egress...)`: re-test the four Q0 hosts
(`curl --max-time 15` each; do not retry a 403 beyond once per host). If ALL still blocked:
leave every status untouched, append one log line, and END THE RUN immediately with digest
`Done: egress still blocked; awaiting environment network change` — do not burn the session
on anything else. If hosts are NOW reachable: set this item DONE, flip every
`BLOCKED(egress ...)` status back to TODO, refresh `tape/cloud-env-check.md`, log the
unblock, then proceed to the topmost TODO item as normal.

### Q1 — Build sports paired-odds collector (serves S7/S11) — TIME-SENSITIVE: World Cup ends Jul 19
Status: DONE (2026-07-09) — `collection/sports_pairs.py` built + 18 unit tests green
(ticker parsing, de-vig math, offline FakeClient run(), completeness-on-failure). Live
full pass: 211 moneyline events across 186/186 discovered "GAME" series, `completeness_ok:
true`, World-Cup/soccer prioritized first. Every leg tagged `real_ask` (yes_ask/no_ask
BBO straight off the live book); `bracket_sum`/`overround` routed through
`core.pricing` only (Hard Rule #3). Odds leg: `ODDS_API_KEY` still absent (a credential,
not egress — see `tape/cloud-env-check.md`) → every event honestly records
`{"odds":{"status":"BLOCKED(key)"}}` rather than fabricating a devig. Data lands in
`tape/sports_pairs/`. Remaining for a future run: schedule this hourly (Q3), and once
Ryan supplies `ODDS_API_KEY` out-of-band, wire the live sharp-odds fetch + devig persist.
`collection/sports_pairs.py`, mirroring `collection/capture_orderbooks.py` discipline
(bitemporal `fetch_ts`, raw-bytes sha256, honest expected-vs-captured completeness). One pass =
for every open Kalshi sports moneyline market (soccer/World Cup first, then anything listed):
snapshot yes/no BBO (tag `real_ask`) → JSONL under `tape/sports_pairs/`. If `ODDS_API_KEY` is
present, also fetch matched sportsbook odds (Pinnacle preferred), store raw + de-vigged fair
prob per outcome (tag `synthetic` — a de-vig is a model, not a fill). No key → capture the
Kalshi leg anyway and note the odds leg as BLOCKED(key). Unit tests for ticker parsing and
de-vig math.

### Q2 — Build crypto-hourly settlement collector (serves S8/S10)
Status: TODO (unblocked 2026-07-09 — Q0b confirmed Kalshi REST + Coinbase + Kraken all reachable)
`collection/crypto_hourly.py`: one pass = snapshot the CURRENT hour's BTC/ETH hourly bracket
books (tag `real_ask`) + spot from ≥1 public exchange endpoint (tag `synthetic`), AND fetch
settlement results for the PREVIOUS hour's markets → paired JSONL under `tape/crypto_hourly/`.
Store both spot and settle so the S8 ρ-guard (spot-vs-settle correlation) is computable from
tape alone.

### Q3 — Hourly entry point for the collector routine
Status: BLOCKED(needs Q2 — Q1 done 2026-07-09, Q2 still TODO)
`collection/hourly_pass.py`: the single command the hourly Haiku routine runs — one
sports-pairs pass + one crypto-hourly pass; during the 09 UTC hour also run
`scripts/anomaly_sweep.py` if it exists. Prints the one-line summary the collector digest
needs (`<n> markets, <m> lines, completeness <ok/FAIL>`). Must be safe to run unattended
every hour; a partial failure lowers completeness, it never fakes success.

### Q4 — S7 historical backtest (sports CLV vs de-vigged sharp line) — the try-first edge
Status: TODO (unblocked 2026-07-09 — Kalshi REST + the-odds-api host both reachable; a
historical odds source for S7a still needs sourcing/provenance work, not egress)
One stage per run:
**S7a** — source last-season NFL/NBA (+ any completed 2026 World Cup) Kalshi market history
via public candlesticks + a free historical closing-odds source; document provenance in the
finding. **S7b** — probe `scripts/sports_clv_s7.py`: Kalshi ask vs de-vig fair at decision
time, fee model consistent with `scripts/fee_breakeven.py`. **S7c** — block-bootstrap by game
→ 95% CI, verdict, `findings/<date>-sports-clv-s7.md`, update registry + this file.

### Q5 — S8 first cut from free candlesticks (crypto settlement basis)
Status: TODO (unblocked 2026-07-09 — Kalshi REST + public spot hosts reachable)
Same trick as S2's first cut: public candlesticks on crypto-hourly markets vs public spot
history. FIRST the ρ-guard — if spot-vs-settle ρ≈1 the feed-mismatch thesis dies cheap →
mark S8 DEAD in the registry and here. Only if the guard passes: final-minutes basis vs
overround at real asks, block-bootstrap by hour.

### Q6 — Daily anomaly sweep (serves S3 + free-money detection)
Status: TODO (unblocked 2026-07-09 — live Kalshi market snapshots reachable)
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
- 2026-07-09T10:13Z · Q0b then Q1 · egress unblocked (all 4 hosts reachable, ODDS_API_KEY still absent) → flipped Q2/Q4/Q5/Q6 to TODO; built + tested `collection/sports_pairs.py` (18 tests green) and ran a live full pass: 211 moneyline events / 186 series, completeness_ok, World-Cup-first, real_ask-tagged, odds leg honestly BLOCKED(key). Q1 marked DONE.
