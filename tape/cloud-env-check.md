# Cloud environment check (Q0 / Q0b)

`run` · 2026-07-02, re-verified 2026-07-09 · cloud sandbox (kalshi-research-loop)

## 2026-07-09 re-verify (Q0b) — UNBLOCKED

Per LOOP-QUEUE.md Q0b, re-tested the same four hosts with plain `curl --max-time 15` before
touching anything else this run. All four are now reachable — this cloud sandbox's egress
allowlist was widened since 2026-07-02 (no code changed on our end; nothing below indicates
`capture_orderbooks.py`/`sports_pairs.py` were ever broken, only that the tunnel now opens).

| host | result |
|---|---|
| `api.elections.kalshi.com` | **200** — `/exchange/status` returned real JSON (`exchange_active: true`) |
| `api.exchange.coinbase.com` | **200** — `/products/BTC-USD/ticker` returned a real quote |
| `api.kraken.com` | **200** — `/0/public/Ticker` returned a real quote |
| `api.the-odds-api.com` | **401** `MISSING_KEY` — host reachable, request reached the odds-api server itself (not a proxy block); `ODDS_API_KEY` still absent from env |

Action taken this run: flipped every `BLOCKED(egress policy)` queue item back to TODO (see
LOOP-QUEUE.md), then proceeded to Q1 (now unblocked) and shipped `collection/sports_pairs.py`
with a first live capture pass (500 events, 42 series, all `real_ask`, all complete).

---

## 2026-07-02 original check (superseded above — kept for history)

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
