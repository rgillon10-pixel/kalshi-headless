#!/usr/bin/env python3
"""Minimal Kalshi request signer — runnable proof for kb/kalshi-api/01-auth-and-signing.md

Verified scheme (docs.kalshi.com/getting_started/api_keys):
  message = f"{timestamp_ms}{METHOD}{path_without_query}"
  signature = base64( RSA-PSS / SHA-256 / MGF1(SHA-256) / salt=DIGEST_LENGTH )
  headers: KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP, KALSHI-ACCESS-SIGNATURE

This script does NOT hit the network. It generates a throwaway RSA key, signs a
sample request, and verifies the signature locally — proving the construction is
correct independent of any vendor SDK. Swap in your real private key + Key ID to
produce real headers.

Requires: cryptography  (pip install cryptography)
"""
import base64
import time
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def sign_message(private_key, message: str) -> str:
    """RSA-PSS / SHA-256, salt = digest length, base64 output."""
    sig = private_key.sign(
        message.encode("utf-8"),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(sig).decode("ascii")


def build_headers(private_key, key_id: str, method: str, full_path: str) -> dict:
    """full_path may include a query string; we strip it before signing (verified gotcha)."""
    path_no_query = urlsplit(full_path).path
    ts_ms = str(int(time.time() * 1000))
    message = f"{ts_ms}{method.upper()}{path_no_query}"
    signature = sign_message(private_key, message)
    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-TIMESTAMP": ts_ms,
        "KALSHI-ACCESS-SIGNATURE": signature,
        # the string we actually signed, for debugging only:
        "_signed_message": message,
    }


def _self_test():
    # throwaway key — stands in for your downloaded RSA_PRIVATE_KEY
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    method = "GET"
    full_path = "/trade-api/v2/portfolio/orders?limit=5"   # query MUST be stripped
    headers = build_headers(private_key, key_id="demo-key-id", method=method,
                            full_path=full_path)

    signed = headers["_signed_message"]
    print("signed message :", signed)
    assert "?" not in signed, "query string leaked into signature!"
    assert signed.endswith("/trade-api/v2/portfolio/orders")

    # verify locally that the signature is valid for the message
    raw = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
    public_key.verify(
        raw, signed.encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    print("signature verifies locally: OK")
    print("headers:")
    for k, v in headers.items():
        if k == "_signed_message":
            continue
        print(f"  {k}: {v[:48]}{'...' if len(v) > 48 else ''}")


if __name__ == "__main__":
    _self_test()
