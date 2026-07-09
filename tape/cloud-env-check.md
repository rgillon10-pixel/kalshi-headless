# Cloud environment check (Q0 / Q0b)

`run` · 2026-07-02 (Q0, initial) · 2026-07-09 (Q0b, re-verify — UNBLOCKED)
cloud sandbox (kalshi-research-loop)

Purpose: verify which external hosts this cloud sandbox can actually reach, since every
downstream collector (Q1–Q7) depends on live network access. Method: direct `curl` (and
the existing `collection/capture_orderbooks.py` / `collection/sports_pairs.py` entry
points) against each required host, `--max-time 15`.

## Results — 2026-07-09 re-verify (Q0b)

| host | purpose | result | source_tag |
|---|---|---|---|
| `api.elections.kalshi.com` | Kalshi public REST | **REACHABLE** — `GET /exchange/status` → 200, `exchange_active: true` | n/a |
| `api.exchange.coinbase.com` | public BTC-USD spot | **REACHABLE** — `GET /products/BTC-USD/ticker` → 200 | n/a |
| `api.kraken.com` | public BTC spot (Kraken) | **REACHABLE** — `GET /0/public/Ticker?pair=XBTUSD` → 200 | n/a |
| `api.the-odds-api.com` | the-odds-api reachability | **REACHABLE** — `GET /v4/sports` → 401 `MISSING_KEY` (host + API reachable; no key configured, see below) | n/a |
| `ODDS_API_KEY` env var | odds API credential | **absent** (checked presence only, not printed) | n/a |

End-to-end confirmation: `python -m collection.sports_pairs --limit-series 3` and a full
unbounded pass both completed live against `api.elections.kalshi.com` — 211 moneyline
events captured across 186/186 discovered series, `completeness_ok: true`. See
`tape/sports_pairs/`.

## Interpretation

The org egress allowlist that blocked all four hosts on 2026-07-02 (proxy CONNECT → 403,
policy denial per `/root/.ccr/README.md`) has been **widened** as of this run — every host
now completes a real TLS handshake and returns a genuine application response (200/401,
never a proxy 403). This is a environment/policy change on Ryan's side, not a code change
here.

`api.the-odds-api.com` is reachable but `ODDS_API_KEY` is still absent from the
environment — a **credential**, not a network gap. Per CLAUDE.md/Stop rules, a cloud run
never touches credentials, so this cannot be resolved from here; the sports collector
(`collection/sports_pairs.py`) captures the Kalshi leg unconditionally and honestly marks
the odds leg `{"status": "BLOCKED(key)"}` per event rather than fabricating a devigged
price without one.

## Consequence for the queue

Q0b (LOOP-QUEUE.md) is DONE; every `BLOCKED(egress policy ...)` status is flipped back to
TODO (Q2, Q4, Q5, Q6) or resolved this run (Q1 — see its Status line). Q3 still needs Q2;
Q7 still needs ≥7 days of Q2 tape. No further action needed from Ryan on egress. The
odds-leg gap (Q1/Q4) needs `ODDS_API_KEY` supplied out-of-band whenever Ryan chooses to.

---

## 2026-07-02 original check (superseded above; kept for the record)

All 4 hosts were **BLOCKED** — proxy CONNECT → 403 (`{"kind":"connect_rejected", "detail":
"gateway answered 403 to CONNECT (policy denial or upstream failure)"}` for each). Q1–Q6
were marked `BLOCKED(egress policy)` pending Ryan widening the sandbox allowlist. That
widening has now happened (see 2026-07-09 section above).
