# Cloud environment check (Q0)

`run` · 2026-07-02, refreshed 2026-07-09 (Q0b unblock) · cloud sandbox (kalshi-research-loop)

## UPDATE 2026-07-09 (Q0b): egress unblocked

Re-tested the same four hosts with `curl --max-time 15`, per Q0b's protocol:

| host | result |
|---|---|
| `api.elections.kalshi.com` (`GET /trade-api/v2/markets?limit=1`) | **200**, valid JSON market page |
| `api.exchange.coinbase.com` (`GET /products/BTC-USD/ticker`) | **200**, valid JSON ticker (BTC ≈ $63,190) |
| `api.kraken.com` (`GET /0/public/Ticker?pair=XBTUSD`) | **200** |
| `api.the-odds-api.com` (`GET /v4/sports`) | **401** (reachable — auth error, not a network block) |
| `ODDS_API_KEY` env var | still **absent** (checked presence only, not printed) |

End-to-end confirmed via `python -m collection.capture_orderbooks --limit 3`: captured 3 live
Kalshi markets / 159 orderbook levels to `data/processed/orderbooks/` (`real_ask` tape, not
synthetic). The org egress allowlist was evidently widened between 2026-07-02 and 2026-07-09 —
not something observable from inside the sandbox, just confirmed fixed.

**Consequence:** Q1–Q6's `BLOCKED(egress policy ...)` statuses (original findings below) are
stale and are flipped back to `TODO` in `LOOP-QUEUE.md` this run. The odds-api leg of Q1
(sportsbook de-vig prices) stays gated on `ODDS_API_KEY` being absent — per Q1's own fallback
clause ("no key → capture the Kalshi leg anyway and note the odds leg as `BLOCKED(key)`") — that
sub-piece alone stays blocked; it does not block the rest of the queue.

## Original 2026-07-02 findings (superseded by the above; kept for history)

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
