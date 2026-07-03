# Cloud environment check (Q0)

`run` · 2026-07-02 · cloud sandbox (kalshi-research-loop)
`updated 2026-07-03 (Q0b)` — egress now unblocked, see final section.

Purpose: verify which external hosts this cloud sandbox can actually reach, since every
downstream collector (Q1–Q7) depends on live network access. Method: direct `curl` (and the
existing `collection/capture_orderbooks.py` entry point) against each required host, `--max-time
15`. All traffic in this sandbox is forced through a policy-enforcing egress proxy
(`$HTTPS_PROXY`); its own status endpoint (`$HTTPS_PROXY/__agentproxy/status`) records
per-host relay failures.

## Results

| host | purpose | result | source_tag |
|---|---|---|---|
| `api.elections.kalshi.com` | Kalshi public REST (`capture_orderbooks.py --limit 3`) | **BLOCKED** — proxy CONNECT → 403 | n/a |
| `api.exchange.coinbase.com` | public BTC-USD spot | **BLOCKED** — proxy CONNECT → 403 | n/a |
| `api.kraken.com` | public BTC spot (Kraken) | **BLOCKED** — proxy CONNECT → 403 | n/a |
| `api.the-odds-api.com` | the-odds-api reachability | **BLOCKED** — proxy CONNECT → 403 | n/a |
| `ODDS_API_KEY` env var | odds API credential | **absent** (checked presence only, not printed) | n/a |

Raw evidence (`$HTTPS_PROXY/__agentproxy/status` → `recentRelayFailures`, all same shape):
```
{"kind":"connect_rejected","detail":"gateway answered 403 to CONNECT (policy denial or upstream failure)","host":"<host>:443"}
```
`api.elections.kalshi.com` failure reproduced end-to-end via
`python -m collection.capture_orderbooks --limit 3` (same proxy 403, full traceback in run log).

## Interpretation

This is an **organization egress allowlist**, not a transient outage: the proxy's `noProxy`
allowlist covers only package registries (`pypi.org`, `registry.npmjs.org`, …) and
`anthropic.com` — no data-provider host is reachable from this particular cloud sandbox. Per
the proxy runbook (`/root/.ccr/README.md`), a 403 from the gateway is a policy denial and must
**not** be retried or routed around.

This is a sandbox/environment property, not a code bug — nothing here indicates
`capture_orderbooks.py`, `normalize.py`, or the client libs are broken; they never got past the
TLS tunnel.

## Consequence for the queue

Every downstream collector needs one of these hosts, so per protocol they are marked
`BLOCKED(egress policy)` in `LOOP-QUEUE.md` (see Status lines): Q1, Q2, Q3, Q4 (S7a candlesticks +
historical odds source), Q5 (S8 candlesticks), Q6 (anomaly sweep needs live market snapshots).
Q7 was already `BLOCKED(needs ≥7 days of Q2 tape)` and now additionally depends on Q2's egress
fix.

**Action needed from Ryan (not resolvable by a cloud run):** either (a) add
`api.elections.kalshi.com`, the crypto spot host(s), and `api.the-odds-api.com` to this
environment's egress allowlist, or (b) run the collectors from an environment/pool that already
has broader egress. No cloud loop run can change its own network policy.

## Re-verify (Q0b) — 2026-07-03T00:08Z — UNBLOCKED

Ryan (or an environment change) widened the sandbox's egress allowlist between the 07-02 run and
this one. Re-ran the identical `curl --max-time 15` probes plus the real collector entry point:

| host | purpose | result | source_tag |
|---|---|---|---|
| `api.elections.kalshi.com` | Kalshi public REST | **OK — HTTP 200**, real body (`exchange_active:true`, `trading_active:true`) | n/a |
| `api.exchange.coinbase.com` | public BTC-USD spot | **OK — HTTP 200**, live ask/bid (`~$61,365`) | n/a |
| `api.kraken.com` | public BTC spot (Kraken) | **OK — HTTP 200**, live server time | n/a |
| `api.the-odds-api.com` | the-odds-api reachability | **OK — HTTP 401** (reachable; rejected for missing key, not a network block) | n/a |
| `ODDS_API_KEY` env var | odds API credential | still **absent** | n/a |

End-to-end proof: `python -m collection.capture_orderbooks --limit 3` succeeded against live
Kalshi — `1 (city,day) groups, 1 complete, 3 markets, 119 levels` written to
`data/processed/orderbooks/dt=2026-07-03/`.

**Consequence:** Q0b is DONE. Every `BLOCKED(egress policy ...)` status in `LOOP-QUEUE.md`
(Q1–Q6; Q7 stays blocked on tape accumulation) flips back to TODO. `ODDS_API_KEY` is still
missing, so the-odds-api leg of Q1 stays `BLOCKED(key)` specifically — Kalshi-only capture in Q1
can proceed.
