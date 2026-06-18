# Kalshi API — REST endpoints & WebSocket feed

`cited` · verified 2026-06-18 (paths marked ✓ confirmed, ~ inferred — confirm ~ from `openapi.yaml`)

Paths are relative to the base `…/trade-api/v2`. Sign the full path incl. `/trade-api/v2`,
strip the query (see `01-auth-and-signing.md`).

## REST — market data (public, no auth needed for reads)

| Purpose | Method & path |
|---|---|
| List markets | `GET /markets` ✓ (filters: `series_ticker`, `event_ticker`, `status`, `limit`≤1000, `cursor`) |
| Get one market | `GET /markets/{ticker}` ✓ |
| Orderbook | `GET /markets/{ticker}/orderbook` ✓ (`depth` param) |
| Multi orderbook | `GET /markets/orderbooks` (batch) ~ |
| Candlesticks | `GET /series/{series}/markets/{ticker}/candlesticks` ~ |
| Public trades | `GET /markets/trades` ~ |
| Events / series | `GET /events`, `GET /events/{event_ticker}`, `GET /series`, `GET /series/{series}` ✓ |

## REST — trading & portfolio (auth required)

| Purpose | Method & path |
|---|---|
| Balance | `GET /portfolio/balance` ✓ |
| Positions | `GET /portfolio/positions` ✓ |
| Create order | `POST /portfolio/orders` ✓ |
| Get / list orders | `GET /portfolio/orders`, `GET /portfolio/orders/{order_id}` ✓ |
| Amend / decrease | `POST /portfolio/orders/{id}/amend`, `/decrease` (v2 variants exist) ~ |
| Cancel order | `DELETE /portfolio/orders/{order_id}` ~ (confirm) |
| Batch create/cancel | `POST /portfolio/orders/batched`, `DELETE /portfolio/orders/batched` ~ |
| Fills | `GET /portfolio/fills` ✓ (historical fills endpoint exists) |
| Settlements | `GET /portfolio/settlements` ~ |

**Order params (create):** `ticker`, `action` (`buy`/`sell`), `side` (`yes`/`no`),
`type` (`limit`/`market`), `count`, `yes_price`/`no_price` (cents, for limit),
`client_order_id` (idempotency key — always set it), plus optional `expiration_ts`,
`post_only`, time-in-force. **Use `client_order_id`** so retries don't double-fill.

## Rate limits (verified — token bucket)

Limits are a **token bucket per second**, default **~10 tokens per request**. Tiers:

| Tier | Read tokens/s | Write tokens/s | ≈ read req/s | ≈ write req/s |
|---|---|---|---|---|
| Basic | 200 | 100 | ~20 | ~10 |
| Advanced | 300 | 300 | ~30 | ~30 |
| Expert | 600 | 600 | ~60 | ~60 |
| Premier | 1,000 | 1,000 | ~100 | ~100 |
| Paragon | 2,000 | 2,000 | ~200 | ~200 |
| Prime | 4,000 | 4,000 | ~400 | ~400 |
| Prestige | 6,000 | 8,000 | ~600 | ~800 |

Writes = order placement/amend/cancel, order groups, RFQ quote flow, block-trade accepts.
Buckets refill continuously and allow a burst up to ~2× the per-second budget. **Design
the bot to live comfortably inside Basic** (≤10 writes/s) — don't assume a high tier.

## WebSocket — keeping a live book

Connect to the `wss://…-ws…/trade-api/ws/v2` base, authenticate with the same RSA
headers on the handshake. Then subscribe to channels. The reliable order-book channel
is **`orderbook_delta`** (snapshot + deltas):

- **`orderbook_snapshot`** (first message): full book.
  `seq` (int), `market_ticker`, `market_id` (UUID), `yes_dollars_fp[]` and
  `no_dollars_fp[]` as `[price_in_dollars, contract_count_fp]` arrays.
- **`orderbook_delta`** (incremental): `seq`, `market_ticker`, `price_dollars`,
  `delta_fp` (fixed-point contract change), `side` (`yes`/`no`), `ts_ms`.
  `client_order_id`/`subaccount` present only when *your* order caused the change.
- **Sequencing:** `seq` increments per message per subscription. **If you see a gap,
  you have missed data — discard the book and resync** (re-request a snapshot via the
  `get_snapshot` action). Never trade off a book with an unverified `seq` chain.

Other channels (from the docs index, confirm payloads in `asyncapi.yaml`): market ticker,
public trades, user orders, user fills, market positions, order-group updates,
market/event lifecycle. **For execution you mainly need:** `orderbook_delta` (the book),
user `fill`s (your executions), and `market_lifecycle` (don't trade a market that just closed).

The exact `subscribe` envelope field names are not pinned from the public index — confirm
against `asyncapi.yaml` before coding the client.

## Data-capture implication (prime directive #2)

The `orderbook_delta` tape — full L2 with timestamps — is the moat. **Archive every
delta with its `seq` and `ts_ms` from day 1.** arb-bot's pt1 failure traced partly to
having only 40s of tape. The book history is the dataset nobody else keeps; persist it
raw with a `price_source_tag = real_ask` on the touched levels.
