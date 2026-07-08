# Cloud environment check (Q0 / Q0b)

`run` · 2026-07-02 (Q0), re-verified 2026-07-08 (Q0b) · cloud sandbox (kalshi-research-loop)

Purpose: verify which external hosts this cloud sandbox can actually reach, since every
downstream collector (Q1–Q7) depends on live network access. Method: direct `curl` (and the
existing `collection/capture_orderbooks.py` / `validation.v3_market` entry points) against each
required host, `--max-time 15`. All traffic in this sandbox is forced through a policy-enforcing
egress proxy (`$HTTPS_PROXY`); its own status endpoint (`$HTTPS_PROXY/__agentproxy/status`)
records per-host relay failures.

## Results (2026-07-08 re-verify)

| host | purpose | result | source_tag |
|---|---|---|---|
| `api.elections.kalshi.com` | Kalshi public REST | **REACHABLE** — end-to-end verified via `python -m collection.capture_orderbooks --limit 3` (142 orderbook levels captured) and `validation.v3_market` series/markets/orderbook calls | n/a (control-plane check) |
| `api.exchange.coinbase.com` | public BTC-USD spot | **REACHABLE** — `GET /products/BTC-USD/ticker` → HTTP 200, live quote returned | n/a |
| `api.kraken.com` | public BTC spot (Kraken) | **REACHABLE** — `GET /0/public/Ticker?pair=XBTUSD` → HTTP 200, live quote returned | n/a |
| `api.the-odds-api.com` | the-odds-api reachability | **REACHABLE** — `GET /v4/sports` → HTTP 401 (reachable; auth required, expected with no key) | n/a |
| `ODDS_API_KEY` env var | odds API credential | **absent** (checked presence only, not printed) — odds leg of Q1 runs `BLOCKED(key)` until Ryan sets it | n/a |

Raw evidence: `$HTTPS_PROXY/__agentproxy/status` → `recentRelayFailures: []` (no policy denials
this run, vs. uniform `connect_rejected`/403 on 2026-07-02).

## Interpretation

The 2026-07-02 finding (organization egress allowlist blocking all four data-provider hosts) has
been **resolved** — some time between 2026-07-02 and 2026-07-08 the environment's egress policy
was widened (or this run landed in a differently-configured sandbox). All four hosts are now
reachable with real 2xx/401 responses, not proxy-level 403s. This is a network/environment change,
not a code change — `capture_orderbooks.py`, `normalize.py`, and the client libs were already
correct; they simply couldn't get past the TLS tunnel before.

## Consequence for the queue

Per Q0b protocol: this item is marked **DONE**, and every `BLOCKED(egress policy)` status on
Q1/Q2/Q3/Q4/Q5/Q6 is flipped back to `TODO` in `LOOP-QUEUE.md`. Q7 remains gated on accumulated
Q2 tape (unrelated to egress). The run proceeds to the new topmost `TODO` item (Q1) per the normal
run protocol.

**Residual gap:** `ODDS_API_KEY` is still absent, so the sportsbook/de-vig leg of Q1 (S7/S11)
stays `BLOCKED(key)` even though the Kalshi leg is fully unblocked — action needed from Ryan to
set the key if the de-vig comparison is wanted before Q1's Kalshi-only tape accumulates enough
history to matter.
