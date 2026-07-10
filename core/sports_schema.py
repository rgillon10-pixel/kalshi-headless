"""Locked GAME-PAIR-MANIFEST schema (sports_pairs.v0) — the Q1 sibling of
core/manifest_schema.py's CaptureManifest, for sports moneyline capture.

One manifest line = one capture of one Kalshi event (a mutually-exclusive set of
outcome markets for a single game, e.g. home/away/tie) at one instant. Same bitemporal
discipline as the weather capture manifest (core/manifest_schema.py): `event_time` is
what the data describes (the game), `captured_at`/`as_of` is when we first received
these exact bytes. Kept as a SEPARATE schema rather than overloading CaptureManifest,
because a sports event is keyed by (event_ticker), not (city, contract-day) — forcing
it into the weather shape would mean lying about what `city` means.

The `signature` is tamper-EVIDENCE (a self-hash), not tamper-proof — same caveat as
core/manifest_schema.py.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from core.canonical import canonical_json, sha256_hex
from core.timeutil import _parse_iso

SPORTS_SCHEMA_VERSION = "sports_pairs.v0"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SIG = re.compile(r"^sha256:[0-9a-f]{64}$")

# odds_leg_status: whether a matched sportsbook de-vig was attempted/available this pass.
VALID_ODDS_LEG_STATUS = frozenset({"ok", "blocked_no_key", "no_match", "fetch_error"})


@dataclass
class GamePairManifest:
    """One capture-manifest line for one Kalshi sports event. Construct, then
    `signed()` to stamp the self-hash signature."""

    capture_id: str
    venue: str
    sport_series: str            # e.g. "KXWCGAME"
    event_ticker: str            # e.g. "KXWCGAME-26JUL11ARGSUI"
    event_title: str
    event_time: str              # ISO datetime — what the data describes (game close_time)
    as_of: str                   # ISO datetime — observability boundary (D3 partition key)
    captured_at: str             # ISO datetime — wall-clock receipt of these exact bytes
    source_endpoint: str
    raw_sha256: str              # content hash over every raw outcome-market payload captured
    n_outcomes: int
    expected_outcomes: int
    bracket_sum: float           # sum of real yes_ask across the outcome set (Hard Rule #3 site)
    overround: float             # bracket_sum - 1.0
    price_source_tag: str = "real_ask"     # the Kalshi leg is always a live BBO
    odds_leg_status: str = "blocked_no_key"
    outcomes: List[str] = field(default_factory=list)   # outcome market tickers captured
    completeness_ok: bool = False
    warmup: bool = True
    schema_version: str = SPORTS_SCHEMA_VERSION
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
    "sport_series": str,
    "event_ticker": str,
    "event_title": str,
    "event_time": str,
    "as_of": str,
    "captured_at": str,
    "source_endpoint": str,
    "raw_sha256": str,
    "n_outcomes": int,
    "expected_outcomes": int,
    "bracket_sum": float,
    "overround": float,
    "price_source_tag": str,
    "odds_leg_status": str,
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
            pass  # int is an acceptable float (e.g. bracket_sum == 1)
        elif not isinstance(val, typ):
            errs.append(f"{name}: expected {typ.__name__}, got {type(val).__name__}")
    if errs:
        return errs

    if record["schema_version"] != SPORTS_SCHEMA_VERSION:
        errs.append(f"schema_version: expected {SPORTS_SCHEMA_VERSION!r}, "
                    f"got {record['schema_version']!r}")

    for name in ("capture_id", "venue", "sport_series", "event_ticker", "source_endpoint"):
        if not record[name].strip():
            errs.append(f"{name}: must be non-empty")

    for name in ("event_time", "as_of", "captured_at"):
        try:
            _parse_iso(record[name])
        except (ValueError, TypeError):
            errs.append(f"{name}: not parseable ISO-8601: {record[name]!r}")

    if not _HEX64.match(record["raw_sha256"]):
        errs.append(f"raw_sha256: not a 64-char lowercase hex sha256")

    if record["price_source_tag"] != "real_ask":
        errs.append("price_source_tag: the Kalshi leg must be tagged real_ask "
                     "(a live BBO), never a lower-trust tag")
    if record["odds_leg_status"] not in VALID_ODDS_LEG_STATUS:
        errs.append(f"odds_leg_status: {record['odds_leg_status']!r} not in "
                    f"{sorted(VALID_ODDS_LEG_STATUS)}")

    outcomes = record["outcomes"]
    if not all(isinstance(o, str) and o.strip() for o in outcomes):
        errs.append("outcomes: every entry must be a non-empty string")

    for name in ("n_outcomes", "expected_outcomes"):
        if record[name] < 0:
            errs.append(f"{name}: must be >= 0")
    # A capture of fewer than 2 outcomes cannot price a bracket (no pair to compare) —
    # the same "an empty capture is not a capture" discipline as CaptureManifest.
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
