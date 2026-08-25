# 24/7 Market Monitor

Always-on, **observation-only** monitoring of scoped Kalshi markets, running on the VPS
(Hetzner, `root@87.99.146.250`) inside the kalshi-headless runtime. It records every book
change and trade on the watched markets, keeps quiet periods measurable, and feeds the
analytics/anomaly layers. It never places, modifies, or cancels an order — there is no
order-capable code outside `execution/kalshi_client.py`, and this system imports nothing
from `execution/`.

## Architecture (Layer 1 — live)

```
config/monitor.yaml            the single control surface (scope, thresholds+ranges, cadences)
        │
        ▼  hourly cron (:08)
collection/monitor_scope.py    /series + per-series /markets → tape/monitor_markets/
        │                      regenerates config/ws_depth_tickers.txt (cap 200, by volume)
        ▼  restart only when the set changed
collection/ws_depth.py         systemd daemon: WS orderbook_delta + trade channels
        │                      → tape/ws_depth/dt=*.jsonl.gz  (VPS-local, gitignored)
        │                      • every book delta with seq (gaps detected → resync)
        │                      • every public trade print (broker_truth)
        │                      • snapshot60 line per market per 60s (quiet periods measurable)
        ▼  cron every 15 min
scripts/monitor_ingest.py      idempotent fold → data/monitor.db (SQLite, WAL, gitignored)
                               tables: markets, book_events, snapshots, trades, gaps,
                               settlements (labels from collection/settlement_ledger.py)
```

Alerting is **ntfy** (`NTFY_TOPIC_URL` in `/root/.secrets/kalshi-headless.env`): `low` =
silent feed entry, `high` = buzz. No Telegram anywhere.

## How to add (or remove) a market family

Edit `config/monitor.yaml` → `scope:` — one line:

```yaml
scope:
  series_prefixes: [KXHIGH, KXLOW, KXNEWTHING]   # series ticker prefix
  categories: [Mentions]                          # or a whole Kalshi series category
  series_tickers: [KXONEOFF]                      # or one explicit series
```

The next hourly scope pass picks it up, rewrites the ws_depth subscription list, and
restarts the daemon only if the subscribed set actually changed. Nothing else to touch.
The WS subscription is capped at 200 tickers (memory bound, lesson L10); when scope
exceeds the cap, the highest-24h-volume markets win and `n_dropped_by_cap` says how many
lost out (honest truncation, in every scope summary line).

## Reading the data

```bash
ssh root@87.99.146.250
cd /root/kalshi-headless
sqlite3 data/monitor.db 'SELECT market_ticker, mid, spread, captured_at
                         FROM snapshots ORDER BY captured_at DESC LIMIT 10'
```

Raw truth is the tape (`tape/ws_depth/dt=*.jsonl.gz`); the DB is derived and disposable —
delete it and the next ingest rebuilds it from tape. Every price row carries its
`price_source_tag` (`real_ask` book quotes, `broker_truth` trade prints/settlements).
`yes_ask`/`mid` here are top-of-book geometry, NOT probabilities (Hard Rule #3 — bracket
normalization lives in `core/pricing.py`).

## Status / stop / start

```bash
make status          # from the local clone: one-screen VPS status over SSH
# on the VPS:
systemctl status kalshi-headless-wsdepth.service
systemctl stop kalshi-headless-wsdepth.service     # safe: SIGTERM → daemon flushes tape
systemctl start kalshi-headless-wsdepth.service    # resumes with a fresh book snapshot
```

Stopping is always safe: tape is append-only JSONL, a restart re-anchors the book with a
fresh WS snapshot, and the ingest is idempotent (per-file offsets + INSERT OR IGNORE), so
nothing duplicates and nothing is silently lost — a gap in coverage shows up as a `gaps`
row / missing snapshot minutes, never as corrupted data.

Self-healing: systemd restarts the daemon on crash (`Restart=always`); a cron healthcheck
every 5 min restarts it if tape goes stale >3 min and pages ntfy `high` if the restart
didn't help; `scripts/tape_gap_monitor.py` (cron, 6h) watches every committed tape family.

## Layers 2–4

Horizon analytics, the anomaly scanner + investigations, and the nightly self-tuning loop
are the next build phases; their design contract (thresholds with declared ranges, the
append-only `reports/nightly/CHANGELOG.md`) is already fixed in `config/monitor.yaml`.
This README grows as they land.
