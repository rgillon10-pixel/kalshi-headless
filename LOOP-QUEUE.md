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
Status: DONE (2026-07-09) — all 4 hosts now REACHABLE (Kalshi REST, Coinbase, Kraken,
the-odds-api); confirmed live via `collection.sports_pairs` (168 series, 442 events).
See `tape/cloud-env-check.md`. Every `BLOCKED(egress policy)` status below flipped to
TODO/updated this run.
Cheap check, run FIRST while any item is `BLOCKED(egress...)`: re-test the four Q0 hosts
(`curl --max-time 15` each; do not retry a 403 beyond once per host). If ALL still blocked:
leave every status untouched, append one log line, and END THE RUN immediately with digest
`Done: egress still blocked; awaiting environment network change` — do not burn the session
on anything else. If hosts are NOW reachable: set this item DONE, flip every
`BLOCKED(egress ...)` status back to TODO, refresh `tape/cloud-env-check.md`, log the
unblock, then proceed to the topmost TODO item as normal.

### Q1 — Build sports paired-odds collector (serves S7/S11) — TIME-SENSITIVE: World Cup ends Jul 19
Status: DONE (2026-07-09, Kalshi leg) — `collection/sports_pairs.py` built + live-verified: one
pass discovers Kalshi moneyline ("Game"-scope) series two-stage (ticker.endswith("GAME") cheap
filter -> `/series/{ticker}` detail confirms `product_metadata.scope=="Game"`, empirically
derived against live API 2026-07-09), groups open markets by `event_ticker`, snapshots yes/no
BBO (tag `real_ask`) -> JSONL under `tape/sports_pairs/dt=<day>/pass-<id>.jsonl`, World Cup
(`KXWCGAME`) sorted first. Live pass: 168 confirmed series, 442 events, 100% complete brackets.
`bracket_sum`/`overround_absorbed` computed via `core.pricing` (Hard Rule #3 sanctioned site).
`core/oddsmath.py` (American/decimal conversion + multiplicative de-vig, tag `synthetic`) built
+ unit-tested but NOT wired to a live odds fetch — `ODDS_API_KEY` is absent in this environment
(confirmed again this run), so the odds leg honestly records `odds_leg: "BLOCKED(key)"` per
pass; the matching/pairing implementation against the-odds-api's actual response shape is
deferred until a key exists to verify against (CLAUDE.md: derive from live shapes, don't guess).
19 new tests (`tests/test_sports_pairs.py`, `tests/test_oddsmath.py`), all green; `invariants
--full` green. **Follow-up (not blocking):** live pass observed `overround_absorbed` ranging
from **-0.02 to +1.73** across sports — the negative value on at least one bracket is a
bracket-sum-below-$1 anomaly worth a look under Q6 (anomaly sweep) once that exists; not
investigated this run (out of scope for a collector-build milestone).

### Q2 — Build crypto-hourly settlement collector (serves S8/S10)
Status: TODO (egress unblocked 2026-07-09, see Q0b — was BLOCKED(egress policy))
`collection/crypto_hourly.py`: one pass = snapshot the CURRENT hour's BTC/ETH hourly bracket
books (tag `real_ask`) + spot from ≥1 public exchange endpoint (tag `synthetic`), AND fetch
settlement results for the PREVIOUS hour's markets → paired JSONL under `tape/crypto_hourly/`.
Store both spot and settle so the S8 ρ-guard (spot-vs-settle correlation) is computable from
tape alone.

### Q3 — Hourly entry point for the collector routine
Status: BLOCKED(needs Q2 — Q1 is now DONE, egress unblocked, see Q0b)
`collection/hourly_pass.py`: the single command the hourly Haiku routine runs — one
sports-pairs pass + one crypto-hourly pass; during the 09 UTC hour also run
`scripts/anomaly_sweep.py` if it exists. Prints the one-line summary the collector digest
needs (`<n> markets, <m> lines, completeness <ok/FAIL>`). Must be safe to run unattended
every hour; a partial failure lowers completeness, it never fakes success.

### Q4 — S7 historical backtest (sports CLV vs de-vigged sharp line) — the try-first edge
Status: TODO (egress unblocked 2026-07-09, see Q0b — was BLOCKED(egress policy); S7a still
needs a historical odds source — `ODDS_API_KEY` remains absent, re-check each run)
One stage per run:
**S7a** — source last-season NFL/NBA (+ any completed 2026 World Cup) Kalshi market history
via public candlesticks + a free historical closing-odds source; document provenance in the
finding. **S7b** — probe `scripts/sports_clv_s7.py`: Kalshi ask vs de-vig fair at decision
time, fee model consistent with `scripts/fee_breakeven.py`. **S7c** — block-bootstrap by game
→ 95% CI, verdict, `findings/<date>-sports-clv-s7.md`, update registry + this file.

### Q5 — S8 first cut from free candlesticks (crypto settlement basis)
Status: TODO (egress unblocked 2026-07-09, see Q0b — was BLOCKED(egress policy))
Same trick as S2's first cut: public candlesticks on crypto-hourly markets vs public spot
history. FIRST the ρ-guard — if spot-vs-settle ρ≈1 the feed-mismatch thesis dies cheap →
mark S8 DEAD in the registry and here. Only if the guard passes: final-minutes basis vs
overround at real asks, block-bootstrap by hour.

### Q6 — Daily anomaly sweep (serves S3 + free-money detection)
Status: TODO (egress unblocked 2026-07-09, see Q0b — was BLOCKED(egress policy)). Note: Q1's
first live pass already surfaced 2 candidate bracket_sum<$1 events in sports moneylines
(`KXLMBGAME-26JUL082100ALGDOR` bracket_sum 0.99, `KXUECLGAME-26JUL09EURSHK` bracket_sum 0.98) —
worth an explicit fee-floor check when this item is picked up.
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
- 2026-07-09T00:23Z · Q0b+Q1 · egress re-verify: all 4 hosts now REACHABLE (allowlist was widened since 07-02) → flipped Q2/Q4/Q5/Q6 back to TODO, Q3 now BLOCKED(needs Q2) only; built+shipped `collection/sports_pairs.py` (Kalshi leg), live pass 168 series/442 events/100% complete, World Cup first, odds leg honestly BLOCKED(key) (`ODDS_API_KEY` still absent); `core/oddsmath.py` de-vig math built+tested but not wired (no key to verify shape against); 19 new tests + invariants green.
