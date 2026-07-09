# Cloud environment check (Q0 / Q0b)

`run` · 2026-07-02 (Q0, all BLOCKED) → **2026-07-09 (Q0b, UNBLOCKED)** · cloud sandbox
(kalshi-research-loop)

Purpose: verify which external hosts this cloud sandbox can actually reach, since every
downstream collector (Q1–Q7) depends on live network access. Method: direct `curl` (and
the live collectors) against each required host, `--max-time 15`.

## Results (2026-07-09, Q0b re-verify)

| host | purpose | result | source_tag |
|---|---|---|---|
| `api.elections.kalshi.com` | Kalshi public REST | **REACHABLE** — HTTP 200, real market data (`/trade-api/v2/markets`, `/series`) | n/a |
| `api.exchange.coinbase.com` | public BTC-USD spot | **REACHABLE** — HTTP 200, live ticker (`BTC-USD ~$62,153`) | n/a |
| `api.kraken.com` | public BTC spot (Kraken) | **REACHABLE** — HTTP 200, live ticker | n/a |
| `api.the-odds-api.com` | the-odds-api reachability | **REACHABLE** — HTTP 401 `MISSING_KEY` (network path open; auth, not egress, is the gate) | n/a |
| `ODDS_API_KEY` env var | odds API credential | **absent** (checked presence only, not printed) | n/a |

All four hosts that were uniformly proxy-403-blocked on 2026-07-02 are now reachable end
to end — this cloud sandbox's egress allowlist was widened between the two checks (no
code change explains it; the 2026-07-02 evidence was a clean 403 `connect_rejected` at
the proxy, not a client bug). Confirmed with a full live collector run, not just a bare
`curl`: `python -m collection.sports_pairs` completed a real pass — 168 confirmed
moneyline series, 442 events, World Cup (`KXWCGAME`) markets present with real bid/ask
depth (e.g. France vs Morocco: yes_ask $0.62, bracket_sum 1.02).

## Interpretation

The 2026-07-02 finding (organization egress allowlist denial) is superseded. No action
item remains for Ryan on network access. `ODDS_API_KEY` is still absent — that is a
credentials gap, not a network one; the sports-pairs collector already handles it
honestly (`odds_leg: "BLOCKED(key)"`, Kalshi leg still captured).

## Consequence for the queue

Per Q0b's protocol: every `BLOCKED(egress policy)` status in `LOOP-QUEUE.md` is flipped
back to `TODO` this run (Q2, Q4, Q5, Q6; Q3 remains blocked, now on Q2 rather than
egress). Q1 was picked up as this run's milestone and is now built + live-verified —
see `LOOP-QUEUE.md` and `kb/00-LOG.md` for details.
