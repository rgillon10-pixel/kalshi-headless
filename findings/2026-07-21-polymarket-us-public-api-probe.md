# Polymarket US public-API probe — 2026-07-21

**Question (Q33 live bring-up):** does the Polymarket US (`api.polymarket.us`) public
market-data / events surface respond to read-only requests **without credentials** from this
machine? The official docs (docs.polymarket.us/api-reference/authentication) claim: *"Public
endpoints like market data and events don't need one."* This note records what the live API
actually did.

## What I probed (read-only GETs, no auth headers)

Machine: local dev box (network allowed here). Tool: `curl`. All requests plain
`GET https://api.polymarket.us<path>`, no `X-PM-*` headers.

| path | HTTP | body |
|---|---|---|
| `/` | 401 | `Missing required API key headers` |
| `/v1/health` | **200** | `{"status":"ok"}` |
| `/v1/markets` | 401 | `Missing required API key headers` |
| `/v1/markets?limit=2` | 401 | `Missing required API key headers` |
| `/v1/events` | 401 | `Missing required API key headers` |
| `/v1/events?limit=2` | 401 | `Missing required API key headers` |
| `/v1/search?q=trump` | 401 | `Missing required API key headers` |
| `/v1/series` | 401 | `Missing required API key headers` |
| `/v1/sports` | 401 | `Missing required API key headers` |
| `/v1/markets/{slug}/book` (documented public) | 401* | `Missing required API key headers` |
| `/v1/markets/{slug}/bbo` (documented public) | 401* | `Missing required API key headers` |

\* every `/v1/...` data path returns the identical 401; `/v1/health` is the *only*
unauthenticated endpoint that answers.

Response headers on the 401 (from `/v1/markets`):
```
HTTP/2 401
content-type: text/plain; charset=utf-8   content-length: 33
x-pm-server-latency: 0                     x-pm-trace-id: 03a34d9b...
server: cloudflare                         cf-ray: a1ef0307c8e41497-ORD
```
The `cf-ray: ...-ORD` edge (Chicago/O'Hare, a US PoP) and the presence of
`x-pm-trace-id` / `x-pm-server-latency` mean the request reached Polymarket's own gateway and
was rejected **by the application**, not geo-blocked at the CDN edge. The rejection reason is
uniform and explicit: **`Missing required API key headers`**.

## Key result (the honest finding)

**Contrary to the published docs, the live Polymarket US API rejects unauthenticated requests
to every market-data and events endpoint with `401 Missing required API key headers`.** There
is **no working public read-only mode from this machine** as of 2026-07-21. `/v1/health` is
the sole open endpoint (and it carries no market data). Every data path — `markets`, `events`,
`search`, `series`, `sports`, `markets/{slug}/book`, `markets/{slug}/bbo` — requires the three
`X-PM-*` auth headers, and `X-PM-Signature` is an **Ed25519 signature over
`f"{timestamp}{method}{path}"` using the account secret** (auth doc + `/v1/portfolio/...`
example). So even "public" data requires a KYC'd Key ID **and** its Ed25519 secret to sign.

**Design consequence:** there is no `POLYMARKET_US_PUBLIC=1` unauthenticated mode to build —
it would 401. The collector therefore stays fully credential-gated on `POLYMARKET_US_API_KEY`
(Key ID presence) exactly as the existing skeleton is, and the live default fetch/discover
**sign every GET** with Ed25519 using `POLYMARKET_US_API_KEY` (Key ID) +
`POLYMARKET_US_SECRET_KEY` (base64 secret). This keeps the cloud-run no-op guarantee trivially
intact: a cloud sandbox has no credential, so `run()` returns `blocked_key` before any network
call. The `blocked_key` line for this leg is therefore not a limitation to fix — it is the
*correct* state everywhere except the credentialed VPS/local box.

## Endpoint shapes discovered (from docs.polymarket.us/llms-full.txt + oapi schema JSON)

Base REST: `https://api.polymarket.us`, gateway `https://gateway.polymarket.us`, v1 paths.
Market-data endpoints that the live default will use once signed:

- **`GET /v1/markets`** — list markets. Query params: `limit`, `offset` (pagination),
  `active`, `closed`, `archived`, `slug[]`, `id[]`, `orderBy`, `orderDirection`,
  `volumeNumMin/Max`, `startDateMin/Max`. Response: `{"markets":[Market,...]}`.
  `Market` fields of interest: `id`, `slug`, `question`, `title`, `outcomes` (JSON string),
  `outcomePrices` (JSON string, reference not book), `bestBidQuote`/`bestAskQuote` (Amount),
  `active`, `closed`, `endDate`, `category`, `volume`.
- **`GET /v1/markets/{slug}/book`** — live order book. Response:
  `{"marketData":{"marketSlug":str,"bids":[BookEntry],"offers":[BookEntry],"state":MarketState,"stats":{...},"transactTime":str}}`
  where `BookEntry = {"px": Amount, "qty": str}` and
  `Amount = {"value": decimal-string, "currency": str}`. **`bids`/`offers` are the ladder;
  `offers` is the ask side.** An empty or one-sided book is a normal thin/far-from-strike
  shape (L23) — a `book` with `bids:[]` or `offers:[]` is *data*, not a fetch failure.
- **`GET /v1/markets/{slug}/bbo`** — lightweight best bid/offer: `marketData.bestBid`,
  `marketData.bestAsk` (Amount), `bidDepth`, `askDepth`, `currentPx`, `lastTradePx`.
- `GET /v1/events`, `/v1/events/slug/{slug}`, `/v1/search?q=` — event/market discovery.
- `MarketState` enum: `MARKET_STATE_OPEN`, `_PREOPEN`, `_SUSPENDED`, `_EXPIRED`,
  `_TERMINATED`, `_HALTED`, `_MATCH_AND_CLOSE_AUCTION`.

A live US order book is a genuine fillable quote → `price_source_tag: "real_ask"`
(consistent with the international `polymarket_pairs` CLOB-book leg). `outcomePrices` /
`currentPx` / `lastTradePx` are last/mid references and are NOT treated as fillable.

## Auth mechanics (recorded for the later WS/trading bring-up — no order verbs built)

Three headers on every authenticated request:
`X-PM-Access-Key` = Key ID; `X-PM-Timestamp` = ms epoch (must be within **30s** of server
time); `X-PM-Signature` = `base64(Ed25519.sign(secret, f"{timestamp}{method}{path}"))`.
Secret loaded via `ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(SECRET)[:32])`.
Keys are minted at polymarket.us/developer after app KYC; the secret is shown once. There is
also an official `polymarket-us` Python SDK — **deliberately not taken as a dependency**; we
implement the thin signed GETs with the repo's `requests` pattern (mirrors
`collection/polymarket_pairs.py`).

## Reproduce
```
curl -s -w '\n[%{http_code}]\n' https://api.polymarket.us/v1/markets
curl -s https://api.polymarket.us/v1/health          # the one open endpoint
curl -s https://docs.polymarket.us/llms-full.txt      # full endpoint map
curl -s https://docs.polymarket.us/api-reference/oapi-schemas/markets-schema.json
```
