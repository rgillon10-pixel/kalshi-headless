# Cloud environment check (Q0)

`run` · 2026-07-02 · cloud sandbox (kalshi-research-loop)

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

---

## Re-verify · 2026-07-09 · cloud sandbox (kalshi-research-loop, Q0b)

Per Q0b's protocol (cheap re-check while any item is `BLOCKED(egress ...)`), re-ran the same 4
`curl --max-time 15` probes plus a live GET against each host's actual public endpoint (not just
the bare root, to rule out a false-positive from a proxy default page).

| host | probe | result |
|---|---|---|
| `api.elections.kalshi.com` | `GET /trade-api/v2/markets?limit=2` | **200**, real market JSON |
| `api.exchange.coinbase.com` | `GET /products/BTC-USD/ticker` | **200**, real BTC-USD ticker |
| `api.kraken.com` | `GET /0/public/Ticker?pair=XBTUSD` | **200**, real BTC ticker |
| `api.the-odds-api.com` | `GET /v4/sports` (no key) | **200**, structured `MISSING_KEY` error (a real app-level response, not a proxy block) |
| `ODDS_API_KEY` env var | presence check | still **absent** |

`$HTTPS_PROXY/__agentproxy/status` → `recentRelayFailures: []` (empty — no denials this run,
vs. the four identical 403s on 2026-07-02). This is a genuine unblock, not a fluke: every host
returned real application-layer data, not a proxy error page.

**Consequence:** Q0b marked DONE; Q2/Q4/Q5/Q6 flipped from `BLOCKED(egress policy)` back to
`TODO` in `LOOP-QUEUE.md`; Q3 now reads `BLOCKED(needs Q2)` (Q1 no longer blocks it — see below).
Q1 (sports pairs collector) was built and run live this same session: `collection/sports_pairs.py`
captured 489 open moneyline games (4 World Cup) in one pass, 489/489 complete, every leg tagged
`real_ask`. `ODDS_API_KEY` is still unset, so the odds/de-vig leg is `BLOCKED(key)` per Q1's own
spec (the Kalshi leg is captured regardless — never let the free half wait on the paid half).

No action needed from Ryan on egress. `ODDS_API_KEY` remains a nice-to-have for S7/S11's sharp-line
leg, not a blocker for any queue item.
