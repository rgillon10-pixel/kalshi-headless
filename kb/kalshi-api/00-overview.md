# Kalshi API — overview & market structure

`cited` · last verified 2026-06-18 against docs.kalshi.com

Kalshi is a CFTC-regulated US event-contract exchange. This note is the substrate
every strategy in this repo runs on: what a contract *is*, what the API exposes,
and where the money math starts. Sources captured in `../_sources/kalshi-api-sources.md`.

## The contract (first principles)

- A market is a **binary contract** that settles **YES = $1.00 (100¢)** or **NO = $0.00**.
- Price is quoted in **whole cents, 1–99¢**. A price of `P` cents ≈ the market's
  implied probability of YES (before fees/overround — see `03-fees-and-breakeven.md`).
- `YES price + NO price = 100¢` for a single market by construction. You can be long
  YES or long NO; selling YES ≡ buying NO.
- Markets are grouped: **series → event → market**. A weather *event* (e.g. "NYC high
  temp on 2026-06-18") contains many *markets* = mutually-exclusive **brackets/strikes**
  (`<=70`, `71–72`, `73–74`, …). The bracket prices across an exhaustive partition
  should sum to ~100¢; the excess over 100¢ is the **overround** the market maker keeps.
  (This additivity is itself a tradable constraint — see `../quant-finance/` no-arb note.)

## Environments (verified)

| | REST base | WebSocket base |
|---|---|---|
| **Production** | `https://external-api.kalshi.com/trade-api/v2` | `wss://external-api-ws.kalshi.com/trade-api/ws/v2` |
| **Demo/sandbox** | `https://external-api.demo.kalshi.co/trade-api/v2` | `wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2` |

Note the TLD flip: production is `.com`, demo is `.co`. Same auth scheme on both.
Develop and integration-test against **demo** with a demo-issued API key; demo has
separate balances and key pairs.

## What the API gives you

- **Market data (REST):** list/get markets, events, series; per-market orderbook;
  candlesticks; public trades. See `02-rest-and-websocket.md`.
- **Real-time (WebSocket):** orderbook deltas, ticker, public trades, your orders,
  your fills, your positions, market/event lifecycle. This is how you keep a live book.
- **Trading (REST):** create / amend / cancel orders (limit & market), batch variants,
  order-group (OCO-style) operations, queue position.
- **Portfolio (REST):** balance, positions, fills, settlements, deposits/withdrawals,
  subaccounts.
- **FIX:** a FIX gateway exists for higher-end users (same RSA key pair; API key ID =
  `SenderCompID`). Out of scope until latency matters.

## Why this matters for the edge

Three structural facts drive every strategy decision here:

1. **Fees are a per-trade tax of ~1–2¢/contract** (round-up-to-cent). On a $1 contract
   that is 100–200 bps. Any edge thinner than the fee is fictional. → `03-fees-and-breakeven.md`.
2. **Overround stacks on top of fees.** The bracket-sum excess (historically 3–5¢ in
   arb-bot's data) is paid on entry at the ask. `yes_ask` is *not* a probability.
3. **You can both make and take.** Maker fills cut the fee rate from 0.07 → 0.0175 (4×)
   and can capture spread — but invite adverse selection. The maker/taker choice is a
   first-class strategy parameter, not an afterthought.

## Open items (verify before relying)

- Exact REST path strings for cancel-order, get-fills, get-settlements (docs name the
  endpoints; literal paths not all confirmed from the public index — pull from
  `openapi.yaml` and pin them in `02-rest-and-websocket.md`).
- The canonical WebSocket `subscribe` envelope (field names) — confirm against
  `asyncapi.yaml`. Channel `orderbook_delta` and its snapshot/delta shape ARE confirmed
  (see `02-rest-and-websocket.md`).
