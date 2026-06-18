# Kalshi API — authentication & request signing

`cited` · verified 2026-06-18 against docs.kalshi.com/getting_started/api_keys

This is the "API key" the project focus rests on. Kalshi REST + WebSocket auth is an
**RSA key-pair request-signing** scheme (not a bearer token, not email/password). Get
this wrong and nothing else works.

## The key pair

- In your Kalshi account profile you **generate an API key**. Kalshi stores your
  **public key** and returns a **Key ID** + an **RSA private key** (PEM, `RSA PRIVATE KEY`).
- The **private key is shown once** — store it securely (this repo gitignores `*.key`,
  `*.pem`, `.env`). Losing it means re-issuing.
- Create-key with your *own* public key is gated to higher usage tiers; the default
  generate-key flow works for everyone.
- The **same key pair** is reused for REST, WebSocket, and FIX.

## The signature (exact, verified)

For every request you compute a signature and send three headers:

| Header | Value |
|---|---|
| `KALSHI-ACCESS-KEY` | your Key ID |
| `KALSHI-ACCESS-TIMESTAMP` | current time in **milliseconds** (string) |
| `KALSHI-ACCESS-SIGNATURE` | base64( RSA-PSS sign ) of the message below |

**Message that gets signed** = concatenation, no separators, in this exact order:

```
<timestamp_ms> + <HTTP_METHOD> + <request_path_without_query>
```

Example string: `1234567890000GET/trade-api/v2/portfolio/balance`

**Algorithm (verified):** RSA-PSS, hash **SHA-256**, MGF1(SHA-256),
**salt length = digest length (32 bytes)**. Output base64-encoded.

**Critical gotcha:** sign the **path only, strip the query string**. For
`/trade-api/v2/portfolio/orders?limit=5` you sign `/trade-api/v2/portfolio/orders`.
Signing the query string is the #1 silent 401.

The timestamp also can't be too stale — sign and send promptly; resign per request.

## WebSocket auth

Same scheme. Sign with `GET` and the WS path (`/trade-api/ws/v2`) and pass the three
headers on the upgrade handshake. Host changes to the `wss://…-ws…` base.

## Runnable reference

`../scripts/kalshi_sign.py` is a minimal, self-contained signer (generates a throwaway
key, signs a sample request, and verifies the signature locally). It is the
"what I cannot create I do not understand" check for this note — run it before trusting
any client library's signing.

## Caveat / trust tag

Verified against the public docs page, not against a live 200 response (no key issued in
this session). Marked `cited`, not `reproduced`, until a real demo request returns 200.
First real task: issue a **demo** key, hit `GET /trade-api/v2/portfolio/balance`, confirm
200, then upgrade this note to `reproduced`.
