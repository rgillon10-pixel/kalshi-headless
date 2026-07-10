"""Locked CRYPTO-HOURLY-MANIFEST schema (crypto_hourly.v0) — the Q2 sibling of
core/sports_schema.py's GamePairManifest, for BTC/ETH hourly range-bracket capture.

One manifest line = one capture of one symbol's CURRENT hourly Kalshi bracket (the whole
mutually-exclusive/exhaustive range ladder for that hour, e.g. KXBTC-26JUL0921's ~188
threshold/band outcome markets — same overround-bearing shape as the weather ladder),
PAIRED with two reference legs so S8's ρ-guard (spot-vs-settle correlation) is computable
from tape alone, with no second pass needed:

  - the live public spot price for the same symbol (tag `synthetic` — not a Kalshi fill)
  - the PREVIOUS hour's settlement result: Kalshi's own `expiration_value` for the hour
    that just closed (tag `broker_truth` — the exchange's own reported settlement fact,
    not a model and not a fill either, per core/source_tag.py's tag semantics)

Kept as a SEPARATE schema rather than overloading GamePairManifest or CaptureManifest,
because this shape pairs THREE distinct provenance lines (current book / spot / prior
settle) in one record, none of which is "an event with >=2 outcome markets" alone.

The `signature` is tamper-EVIDENCE (a self-hash), not tamper-proof — same caveat as
core/manifest_schema.py and core/sports_schema.py.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from core.canonical import canonical_json, sha256_hex
from core.timeutil import _parse_iso

CRYPTO_SCHEMA_VERSION = "crypto_hourly.v0"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SIG = re.compile(r"^sha256:[0-9a-f]{64}$")

# spot_status: whether the public spot fetch for this pass succeeded.
VALID_SPOT_STATUS = frozenset({"ok", "fetch_error", "blocked"})
# settle_status: whether the previous hour's settlement could be located this pass.
VALID_SETTLE_STATUS = frozenset({"ok", "not_found", "fetch_error"})


@dataclass
class CryptoHourlyManifest:
    """One capture-manifest line for one symbol's current hourly bracket + paired
    spot/settle reference legs. Construct, then `signed()` to stamp the self-hash."""

    capture_id: str
    venue: str
    symbol: str                  # "BTC" / "ETH"
    series_ticker: str            # "KXBTC" / "KXETH"
    event_ticker: str             # the CURRENT hourly event's ticker
    event_time: str               # ISO datetime — the hour's open_time (what the data describes)
    close_time: str               # ISO datetime — the hour's close_time
    as_of: str                    # ISO datetime — observability boundary (D3 partition key)
    captured_at: str              # ISO datetime — wall-clock receipt of these exact bytes
    source_endpoint: str
    raw_sha256: str               # content hash over every raw outcome-market payload captured
    n_outcomes: int
    expected_outcomes: int
    bracket_sum: float            # sum of real yes_ask across the hourly ladder (Hard Rule #3 site)
    overround: float              # bracket_sum - 1.0
    price_source_tag: str = "real_ask"       # the Kalshi ladder leg is always a live BBO
    spot_price: float = 0.0
    spot_exchange: str = ""
    spot_status: str = "blocked"
    spot_source_tag: str = "synthetic"       # a reference price, never a fill (Q2)
    prev_event_ticker: str = ""
    prev_close_time: str = ""
    settle_value: float = 0.0
    settle_status: str = "not_found"
    settle_source_tag: str = "broker_truth"  # Kalshi's own reported settlement fact
    outcomes: List[str] = field(default_factory=list)   # outcome market tickers captured
    completeness_ok: bool = False
    warmup: bool = True
    schema_version: str = CRYPTO_SCHEMA_VERSION
    signature: str = ""

    def signed(self) -> Dict[str, Any]:
        return sign(asdict(self))


def _signing_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in record.items() if k != "signature"}


def sign(record: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(record)
    out["signature"] = "sha256:" + sha256_hex(canonical_json(_signing_payload(out)))
    return out


def verify_signature(record: Dict[str, Any]) -> bool:
    sig = record.get("signature")
    if not isinstance(sig, str) or not _SIG.match(sig):
        return False
    expected = "sha256:" + sha256_hex(canonical_json(_signing_payload(record)))
    return sig == expected


_REQUIRED: Dict[str, type] = {
    "schema_version": str,
    "capture_id": str,
    "venue": str,
    "symbol": str,
    "series_ticker": str,
    "event_ticker": str,
    "event_time": str,
    "close_time": str,
    "as_of": str,
    "captured_at": str,
    "source_endpoint": str,
    "raw_sha256": str,
    "n_outcomes": int,
    "expected_outcomes": int,
    "bracket_sum": float,
    "overround": float,
    "price_source_tag": str,
    "spot_price": float,
    "spot_exchange": str,
    "spot_status": str,
    "spot_source_tag": str,
    "prev_event_ticker": str,
    "prev_close_time": str,
    "settle_value": float,
    "settle_status": str,
    "settle_source_tag": str,
    "outcomes": list,
    "completeness_ok": bool,
    "warmup": bool,
    "signature": str,
}


def validate(record: Dict[str, Any]) -> List[str]:
    """Return a list of human-readable errors; empty list == valid manifest."""
    errs: List[str] = []
    if not isinstance(record, dict):
        return ["record is not a dict"]

    for name, typ in _REQUIRED.items():
        if name not in record:
            errs.append(f"missing field: {name}")
            continue
        val = record[name]
        if typ is int and isinstance(val, bool):
            errs.append(f"{name}: expected int, got bool")
        elif typ is float and isinstance(val, bool):
            errs.append(f"{name}: expected float, got bool")
        elif typ is float and isinstance(val, int):
            pass  # int is an acceptable float
        elif not isinstance(val, typ):
            errs.append(f"{name}: expected {typ.__name__}, got {type(val).__name__}")
    if errs:
        return errs

    if record["schema_version"] != CRYPTO_SCHEMA_VERSION:
        errs.append(f"schema_version: expected {CRYPTO_SCHEMA_VERSION!r}, "
                    f"got {record['schema_version']!r}")

    for name in ("capture_id", "venue", "symbol", "series_ticker", "event_ticker",
                 "source_endpoint"):
        if not record[name].strip():
            errs.append(f"{name}: must be non-empty")

    for name in ("event_time", "close_time", "as_of", "captured_at"):
        try:
            _parse_iso(record[name])
        except (ValueError, TypeError):
            errs.append(f"{name}: not parseable ISO-8601: {record[name]!r}")

    if not _HEX64.match(record["raw_sha256"]):
        errs.append("raw_sha256: not a 64-char lowercase hex sha256")

    if record["price_source_tag"] != "real_ask":
        errs.append("price_source_tag: the Kalshi ladder leg must be tagged real_ask "
                     "(a live BBO), never a lower-trust tag")
    if record["spot_status"] not in VALID_SPOT_STATUS:
        errs.append(f"spot_status: {record['spot_status']!r} not in {sorted(VALID_SPOT_STATUS)}")
    if record["spot_status"] == "ok" and record["spot_source_tag"] != "synthetic":
        errs.append("spot_source_tag: a public spot reference is never a fill — must be "
                     "'synthetic' whenever spot_status is 'ok'")
    if record["settle_status"] not in VALID_SETTLE_STATUS:
        errs.append(f"settle_status: {record['settle_status']!r} not in "
                    f"{sorted(VALID_SETTLE_STATUS)}")
    if record["settle_status"] == "ok" and record["settle_source_tag"] != "broker_truth":
        errs.append("settle_source_tag: a located Kalshi settlement value must be tagged "
                     "'broker_truth' whenever settle_status is 'ok'")

    outcomes = record["outcomes"]
    if not all(isinstance(o, str) and o.strip() for o in outcomes):
        errs.append("outcomes: every entry must be a non-empty string")

    for name in ("n_outcomes", "expected_outcomes"):
        if record[name] < 0:
            errs.append(f"{name}: must be >= 0")
    # A capture of fewer than 2 outcomes cannot price a bracket (no pair to compare) —
    # the same "an empty capture is not a capture" discipline as GamePairManifest.
    if record["n_outcomes"] < 2:
        errs.append("n_outcomes must be >= 2 (a single-leg capture cannot price a bracket)")
    if len(outcomes) != record["n_outcomes"]:
        errs.append("outcomes length must equal n_outcomes")
    if record["n_outcomes"] > record["expected_outcomes"]:
        errs.append("n_outcomes cannot exceed expected_outcomes")
    if record["completeness_ok"] != (record["n_outcomes"] == record["expected_outcomes"]):
        errs.append("completeness_ok inconsistent with n_outcomes == expected_outcomes")

    if record["warmup"] is not True:
        errs.append("warmup must be True for this collector's first phase (no live-scoring yet)")

    if not _SIG.match(record["signature"]):
        errs.append("signature: must match 'sha256:<64 hex>'")
    elif not verify_signature(record):
        errs.append("signature: self-hash does not match record content")

    return errs
