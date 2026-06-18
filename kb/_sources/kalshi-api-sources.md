# Captured sources — Kalshi API (for auditability)

Trust = FALSE: claims in `kb/kalshi-api/` trace to these. Verified 2026-06-18.
If the web changes, these are what the notes were built on.

## Official docs (docs.kalshi.com)

- Doc index (machine-readable): https://docs.kalshi.com/llms.txt
- API keys / signing: https://docs.kalshi.com/getting_started/api_keys
- Environments (base URLs): https://docs.kalshi.com/getting_started/api_environments
- Demo env: https://docs.kalshi.com/getting_started/demo_env
- First request / auth quickstart: https://docs.kalshi.com/getting_started/making_your_first_request ·
  https://docs.kalshi.com/getting_started/quick_start_authenticated_requests
- Market-data quickstart: https://docs.kalshi.com/getting_started/quick_start_market_data
- Create-order quickstart: https://docs.kalshi.com/getting_started/quick_start_create_order
- Rate limits: https://docs.kalshi.com/getting_started/rate_limits
- Fee rounding: https://docs.kalshi.com/getting_started/fee_rounding
- Fee schedule PDF: https://kalshi.com/docs/kalshi-fee-schedule.pdf
- WebSockets overview: https://docs.kalshi.com/websockets
- Orderbook channel: https://docs.kalshi.com/websockets/orderbook-updates
- API reference (markets/events/orders/portfolio): https://docs.kalshi.com/api-reference/...
- OpenAPI / AsyncAPI specs (authoritative for exact schemas):
  https://docs.kalshi.com/openapi.yaml · https://docs.kalshi.com/asyncapi.yaml
- FIX auth: https://docs.kalshi.com/fix/authentication

## Verified facts pinned

- Auth: RSA-PSS / SHA-256 / MGF1(SHA-256) / salt=DIGEST_LENGTH; sign
  `ts_ms + METHOD + path(no query)`; base64; headers KALSHI-ACCESS-KEY /
  -TIMESTAMP / -SIGNATURE. (api_keys page)
- Prod REST `https://external-api.kalshi.com/trade-api/v2`; demo
  `https://external-api.demo.kalshi.co/trade-api/v2`. WS prod
  `wss://external-api-ws.kalshi.com/trade-api/ws/v2`. (api_environments)
- Fee: `roundup(rate·C·P·(1−P))`, taker 0.07 / maker 0.0175 / index 0.035. (fee PDF)
- Rate limits: token bucket, ~10 tokens/req, Basic 200 read / 100 write tokens/s … up to
  Prestige 6000/8000. (rate_limits)
- Orderbook channel `orderbook_delta`: `orderbook_snapshot` + `orderbook_delta` messages,
  `seq` for gap detection, `yes_dollars_fp`/`no_dollars_fp`, resync via `get_snapshot`. (orderbook-updates)

## Not yet confirmed (do not treat as fact)

- WebSocket `subscribe` envelope field names → confirm in `asyncapi.yaml`.
- Literal REST paths for cancel-order / settlements / batch ops → confirm in `openapi.yaml`.
- Per-tier WS connection/message limits.
- Whether fees are entry-only and any weather-series-specific discount.
