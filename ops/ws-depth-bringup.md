# WS-depth collector — bring-up

Stand up the Kalshi WebSocket `orderbook_delta` capture daemon
(`collection/ws_depth.py`) on the VPS. This is the project's biggest data-surface
expansion: continuous L2 book deltas instead of the hourly REST snapshot
(`collection/orderbook_depth.py`), feeding the L-speed / L-mech / L-flow structural
lanes (prime directive #2 — collect data where others aren't).

**Read-only.** The daemon signs an authenticated WS handshake (public book data still
needs the RSA-signed upgrade) and subscribes to `orderbook_delta` ONLY. It defines no
order verb and imports nothing from `execution/`. See the CONTRACT NUANCE banner at the
top of `collection/ws_depth.py`. It is a collector, so it lives in `collection/`.

The daemon is **key-gated and self-activating**: with no key it logs
`{"status":"blocked_key"}` and exits 0 (writes nothing). It only starts capturing once a
Kalshi API key + a ticker list are in place. Do NOT `enable` the unit before then, or
`Restart=always` will hot-loop on the blocked_key exit.

---

## 1. Generate a Kalshi API key (RSA keypair)

Kalshi auth is RSA request-signing, not a bearer token (see
`kb/kalshi-api/01-auth-and-signing.md`).

1. Kalshi account → **Settings → API Keys → Create API Key**.
2. Kalshi stores your public key and returns a **Key ID** + an **RSA private key** (PEM,
   `-----BEGIN RSA PRIVATE KEY-----`). The **private key is shown once** — save it now.
3. A demo key against the demo host is fine for a first smoke; production tape needs a
   production key. The same keypair works for REST + WS + FIX.

> No credentials are committed. The repo gitignores `*.key` / `*.pem` / `.env`. A cloud
> agent can never obtain a key — `BLOCKED(key)` is the honest state there.

## 2. Drop the key on the VPS

```sh
# private key file — mode 600, outside the repo checkout
scp kalshi-prod.pem root@87.99.146.250:/root/.secrets/kalshi-headless-wsdepth.pem
ssh root@87.99.146.250 'chmod 600 /root/.secrets/kalshi-headless-wsdepth.pem'
```

Append to `/root/.secrets/kalshi-headless.env` (the same env file the hourly runner
sources):

```sh
KALSHI_API_KEY_ID=your-key-id-uuid
KALSHI_PRIVATE_KEY_PATH=/root/.secrets/kalshi-headless-wsdepth.pem
# optional overrides:
# KALSHI_WS_BASE=wss://api.elections.kalshi.com/trade-api/ws/v2   # demo host differs
# WS_DEPTH_COMPRESS=none      # write plain .jsonl instead of .jsonl.gz (bring-up debugging)
# WS_DEPTH_TICKERS=KX-A,KX-B  # inline override of the committed ticker file
```

## 3. Runtime dependencies (VPS venv)

The daemon lazily imports two libs NOT in the minimal core deps (so the test venv and
plain module import stay light). Install them into the VPS venv once:

```sh
ssh root@87.99.146.250 '/root/kalshi-headless/.venv/bin/pip install cryptography websocket-client'
```

- `cryptography` — RSA-PSS/SHA-256 handshake signing.
- `websocket-client` (import name `websocket`) — the blocking WS client
  (`websocket.create_connection`).

> These belong in a `pyproject.toml [project.optional-dependencies] wsdepth = [...]`
> extra; adding that is out of this change's file-scope — track it separately.

## 4. Pick the tickers to capture

Edit `config/ws_depth_tickers.txt` (committed) — one full Kalshi **market** ticker per
line, `#` comments, blanks ignored. A market only earns a continuous subscription if a
human lists it here (the set is capped at 200 with an honest `truncated` flag — lesson
L10). Pick the ~most-active markets, where order-flow structure has signal:

```sh
# candidates from the volume leaderboard (values are *_fp STRINGS — see core.kalshi_fields):
curl -s 'https://api.elections.kalshi.com/trade-api/v2/markets?status=open&limit=1000' \
  | python3 -c 'import sys,json; ms=json.load(sys.stdin)["markets"]; \
      ms.sort(key=lambda m: float(m.get("volume_fp","0") or 0), reverse=True); \
      print("\n".join(m["ticker"] for m in ms[:40]))'
```

Paste the ones you want into `config/ws_depth_tickers.txt`, commit, and pull on the VPS.
Or set `WS_DEPTH_TICKERS=...` in the env file to override without a commit.

## 5. Install + enable the unit

```sh
ssh root@87.99.146.250 '
  git -C /root/kalshi-headless pull -q --ff-only
  install -m755 /root/kalshi-headless/ops/vps/kalshi-headless-wsdepth.sh /root/bin/kalshi-headless-wsdepth.sh
  install -m644 /root/kalshi-headless/ops/vps/kalshi-headless-wsdepth.service /etc/systemd/system/kalshi-headless-wsdepth.service
  systemctl daemon-reload
'
```

Smoke it in the foreground first (bounded run, no enable):

```sh
ssh root@87.99.146.250 'cd /root/kalshi-headless && \
  set -a; . /root/.secrets/kalshi-headless.env; set +a && \
  .venv/bin/python -m collection.ws_depth --max-messages 50'
# expect: [ws_depth] {"status":"start",...} then book lines, then {"status":"stopped",...}
# no key? expect exactly: [ws_depth] {"status":"blocked_key",...}
```

Then enable for real:

```sh
ssh root@87.99.146.250 'systemctl enable --now kalshi-headless-wsdepth'
```

## 6. Verify tape flows

```sh
ssh root@87.99.146.250 '
  systemctl status kalshi-headless-wsdepth --no-pager | head -20
  ls -la /root/kalshi-headless/tape/ws_depth/
  zcat /root/kalshi-headless/tape/ws_depth/dt=$(date -u +%F).jsonl.gz | head -3
  zcat /root/kalshi-headless/tape/ws_depth/dt=$(date -u +%F).jsonl.gz | wc -l
'
```

You should see `ws_depth.session.v1` (session_open), `ws_depth.v1` book lines
(`orderbook_snapshot` / `orderbook_delta`, tagged `price_source_tag: real_ask`), and —
when the feed drops a seq — explicit `ws_depth.gap.v1` lines. A gap is DATA (honest
accounting), not a failure; the daemon reconnects to re-anchor the chain.

**Tape → git:** the daemon only writes files. The existing hourly runner
(`ops/vps/kalshi-headless-hourly.sh`) does `git add tape/`, which globs all families, so
`tape/ws_depth/dt=*.jsonl.gz` rides to git on the next hourly commit — **no extra wiring**.

**Storage:** `orderbook_delta` is high-rate. Files are written **gzipped** by default
(`dt=YYYY-MM-DD.jsonl.gz`, ~5-10x smaller than raw JSONL) to stay under GOAL.md's ~50MB/day
ceiling. Rough math: ~50 active tickers × a busy day of deltas ≈ hundreds of MB raw →
tens of MB gzipped. Watch the first few days:

```sh
ssh root@87.99.146.250 'du -sh /root/kalshi-headless/tape/ws_depth/dt=$(date -u +%F).jsonl.gz'
```

If a day file trends past ~50MB gzipped, trim `config/ws_depth_tickers.txt` to the highest-
signal markets. Files rotate automatically at UTC midnight.

## 7. Kill switch

```sh
ssh root@87.99.146.250 'systemctl stop kalshi-headless-wsdepth'      # SIGTERM: daemon flushes + closes the current file
ssh root@87.99.146.250 'systemctl disable kalshi-headless-wsdepth'   # don't restart on boot
```

To pause capture without touching the unit, remove the key lines from
`/root/.secrets/kalshi-headless.env` and restart — the daemon reverts to `blocked_key`.
