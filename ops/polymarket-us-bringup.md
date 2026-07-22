# Polymarket US book-capture — VPS bring-up (Q33)

Read-only, credential-gated capture of the Polymarket **US** (QCEX) order book for the
internationally-matched questions the `polymarket_pairs` collector already pairs on. Closes the
"not a Polymarket-US fill" provenance caveat on Q31/Q32 for the lines it writes. Tape family:
`tape/polymarket_us_pairs/dt=YYYY-MM-DD.jsonl`, one line per matched market, US book tagged
`real_ask`.

## What activates when

The leg is a hard **no-op** unless `POLYMARKET_US_API_KEY` is present in the environment. On a
cloud sandbox / CI (credential absent) `run()` returns `{"status":"blocked_key"}`, makes **zero
network calls, writes zero files** — this is the correct steady state everywhere except the
credentialed VPS/local box. It self-activates the moment the credential lands; no code change
needed.

- Entry point: `python -m collection.polymarket_us_live`
  (thin wiring over `collection/polymarket_us_pairs.py`, which owns the credential gate, tape
  write, provenance stamps, and honest no_book/book_error accounting).
- Skeleton-only (no live default): `python -m collection.polymarket_us_pairs` — same gate,
  but its network callables are VPS-bring-up stubs that raise if reached.

## Why credentials are required even for "public" data (live probe 2026-07-21)

The docs claim market-data/events are public, but the live API returns
`401 Missing required API key headers` on **every** `/v1/...` data endpoint from a
no-credential machine (`/v1/health` is the only open path). Full evidence:
`findings/2026-07-21-polymarket-us-public-api-probe.md`. So every read is an Ed25519-signed
GET; there is no unauthenticated public mode. That is why the leg stays gated on
`POLYMARKET_US_API_KEY` and the cloud-run no-op guarantee is structural.

## Env vars to set (VPS only)

| Var | Meaning | Used for |
|---|---|---|
| `POLYMARKET_US_API_KEY` | Key ID from polymarket.us/developer | `X-PM-Access-Key` header **and** the presence signal that arms the leg |
| `POLYMARKET_US_SECRET_KEY` | base64 Ed25519 secret (shown once at key creation) | signing every request (`X-PM-Signature`); never logged/printed |

Both are needed to sign. Getting keys: install the Polymarket US app, complete KYC, then
polymarket.us/developer → create key (copy the secret immediately — shown once).

### Where they live

Root-only secrets file on the Hetzner VPS: **`/root/.secrets/kalshi-headless.env`**
(mode `600`, `root:root`), alongside the existing `ODDS_API_KEY` / IBKR slots. Example lines:

```
POLYMARKET_US_API_KEY=<key-id>
POLYMARKET_US_SECRET_KEY=<base64-secret>
```

The hourly runner sources that file before invoking the collector. Never commit these; never
place them in a cloud sandbox (a cloud run must only ever see `blocked_key`). The repo carries
no credentials and no `.env`.

## What it does once armed

1. **Discovery** — reuses `polymarket_pairs` matching (WC-round + Fed-decision families) to get
   the internationally-matched question set, lists Polymarket US markets via signed
   `GET /v1/markets` (paginated, capped at `MAX_US_MARKETS=8000` with an honest truncation
   marker, L10), and attaches each question's US market/slug by **structural** token
   confirmation (round+team, or meeting+bucket tokens present in the US market's own text) —
   1:1 only, never guessed. A question with no US match is kept and recorded as `no_book`.
2. **Fetch** — signed `GET /v1/markets/{slug}/book` per matched market; best bid/ask + depth
   parsed from `marketData.bids`/`marketData.offers`, tagged `real_ask`.
3. **Honest accounting** — empty/one-sided book = data (L23), not a drop; `404` or no US market
   = `no_book` (structural, does NOT gate); a genuine HTTP/JSON failure = `book_error` (gates
   `completeness_ok`). Bitemporal `captured_at` + raw-bytes `sha256` on every line.

## Verify after setting creds (VPS)

```
python -m collection.polymarket_us_live      # expect status=ok, an n_captured line, tape written
```
Confirm `X-PM-Timestamp` clock skew < 30s vs Polymarket server time (the signature window).
First real run also confirms the live US market/book **title grammar** the structural matcher
assumes (unverifiable from a no-credential box, where the endpoint 401s) — sanity-check
`n_no_book` vs `n_captured` to catch a title-shape mismatch.

## Not built here (out of scope / forbidden to autonomous work)

Order placement, cancellation, quotes, the authenticated WebSocket, and
`execution/kalshi_client.py`-class order paths. The Ed25519 `auth_headers` signer in
`collection/polymarket_us_live.py` is provided read-only for market data and as a vetted signer
for the later Ryan-supervised WS/trading bring-up — it issues only `GET`s here.
