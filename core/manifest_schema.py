"""Locked CAPTURE-MANIFEST schema (m1.v0) + a self-hash integrity stamp.

A capture manifest is one line summarizing one capture of public data for one city /
one contract-day: what was fetched, when *we* first received it, and content hashes
that pin the exact bytes. Milestone 1 criterion 4 ("the manifest validates against the
locked census schema") is satisfied here.

NOT the spec-census ledger. D2/D6 describe a *different* append-only ledger — the
hash-chained record of evaluated hypothesis *specs* (one row per forking-path test),
which gates the fitter (C4) and feeds log(M). That ledger is built later (Phase 2) and
must stay separate so Claude stays out of the accounting trust path. This file is only
the data-capture manifest; do not overload it with spec/fit accounting.

Bitemporal contract (D3): `event_time` = what the data describes; `as_of`/`captured_at`
= when we first received these exact bytes. The forward partition is on `as_of`, never
`event_time`. Every Milestone-1 record is `warmup=True` (C7): pre-temporal-contract
capture is excluded from every holdout and can never be scored as forward evidence.

The `signature` is tamper-EVIDENCE, not tamper-proof (D5, honest): a self-hash of the
record. Hardware-signing of protected paths is Phase 4 — this does not pretend otherwise.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from core.canonical import canonical_json, sha256_hex
from core.timeutil import _parse_iso

MANIFEST_SCHEMA_VERSION = "m1.v0"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SIG = re.compile(r"^sha256:[0-9a-f]{64}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class CaptureManifest:
    """One capture-manifest line. Construct, then `signed()` to stamp the signature."""

    capture_id: str
    venue: str
    city: str
    target_date: str            # ISO date (YYYY-MM-DD) — the contract-day
    event_time: str             # ISO datetime — what the data describes
    as_of: str                  # ISO datetime — observability boundary (partition key, D3)
    captured_at: str            # ISO datetime — wall-clock receipt of these exact bytes
    source_endpoint: str        # API base/path family the bytes came from
    raw_sha256: str             # content hash committing to every raw file captured
    normalized_sha256: str      # content hash of the canonical normalized payload
    n_markets: int
    expected_markets: int
    n_with_book: int
    total_levels: int
    series: List[str] = field(default_factory=list)
    completeness_ok: bool = False
    warmup: bool = True
    schema_version: str = MANIFEST_SCHEMA_VERSION
    signature: str = ""         # "sha256:<hex>" self-hash; set by signed()/sign()

    def signed(self) -> Dict[str, Any]:
        """Return this manifest as a dict with a fresh self-hash signature."""
        return sign(asdict(self))


def _signing_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """The record minus its own signature — what the self-hash is computed over."""
    return {k: v for k, v in record.items() if k != "signature"}


def sign(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of `record` with `signature` = sha256: of its canonical content."""
    out = dict(record)
    out["signature"] = "sha256:" + sha256_hex(canonical_json(_signing_payload(out)))
    return out


def verify_signature(record: Dict[str, Any]) -> bool:
    """True iff `record['signature']` matches a fresh self-hash of the record."""
    sig = record.get("signature")
    if not isinstance(sig, str) or not _SIG.match(sig):
        return False
    expected = "sha256:" + sha256_hex(canonical_json(_signing_payload(record)))
    return sig == expected


# Required (field name -> python type) for structural validation.
_REQUIRED: Dict[str, type] = {
    "schema_version": str,
    "capture_id": str,
    "venue": str,
    "city": str,
    "target_date": str,
    "event_time": str,
    "as_of": str,
    "captured_at": str,
    "source_endpoint": str,
    "raw_sha256": str,
    "normalized_sha256": str,
    "n_markets": int,
    "expected_markets": int,
    "n_with_book": int,
    "total_levels": int,
    "series": list,
    "completeness_ok": bool,
    "warmup": bool,
    "signature": str,
}

_COUNT_FIELDS = ("n_markets", "expected_markets", "n_with_book", "total_levels")


def validate(record: Dict[str, Any]) -> List[str]:
    """Return a list of human-readable errors; empty list == valid manifest.

    Checks presence + types, field formats (hex hashes, ISO times, signature shape),
    cross-field consistency (completeness_ok, count sanity), the schema-version pin,
    the warmup invariant (C7), and that the self-hash signature is internally consistent.
    """
    errs: List[str] = []
    if not isinstance(record, dict):
        return ["record is not a dict"]

    # presence + types
    for name, typ in _REQUIRED.items():
        if name not in record:
            errs.append(f"missing field: {name}")
            continue
        val = record[name]
        # bool is a subclass of int — guard the count/int fields against True/False.
        if typ is int and isinstance(val, bool):
            errs.append(f"{name}: expected int, got bool")
        elif not isinstance(val, typ):
            errs.append(f"{name}: expected {typ.__name__}, got {type(val).__name__}")
    if errs:
        return errs  # don't dereference fields that failed type checks

    # schema version pin
    if record["schema_version"] != MANIFEST_SCHEMA_VERSION:
        errs.append(f"schema_version: expected {MANIFEST_SCHEMA_VERSION!r}, "
                    f"got {record['schema_version']!r}")

    # non-empty identity strings
    for name in ("capture_id", "venue", "city", "source_endpoint"):
        if not record[name].strip():
            errs.append(f"{name}: must be non-empty")

    # series: non-empty list of non-empty strings
    series = record["series"]
    if not series:
        errs.append("series: must be a non-empty list")
    elif not all(isinstance(s, str) and s.strip() for s in series):
        errs.append("series: every entry must be a non-empty string")

    # date / datetime formats
    if not _ISO_DATE.match(record["target_date"]):
        errs.append(f"target_date: not ISO YYYY-MM-DD: {record['target_date']!r}")
    for name in ("event_time", "as_of", "captured_at"):
        try:
            _parse_iso(record[name])
        except (ValueError, TypeError):
            errs.append(f"{name}: not parseable ISO-8601: {record[name]!r}")

    # content hashes
    for name in ("raw_sha256", "normalized_sha256"):
        if not _HEX64.match(record[name]):
            errs.append(f"{name}: not a 64-char lowercase hex sha256")

    # count sanity
    for name in _COUNT_FIELDS:
        if record[name] < 0:
            errs.append(f"{name}: must be >= 0")
    # A capture of NOTHING is not a complete capture — it is the survivorship /
    # corrupted-actuals failure mode (D3: "scoring only the days capture succeeded
    # = survivorship = the corrupted-actuals mode reborn"). An empty manifest must
    # NEVER validate as a complete, ok capture, regardless of completeness_ok.
    if record["expected_markets"] <= 0:
        errs.append("expected_markets must be >= 1 (an empty capture is not a capture)")
    if record["n_markets"] <= 0:
        errs.append("n_markets must be >= 1 (a capture with zero markets is degenerate)")
    if record["n_with_book"] > record["n_markets"]:
        errs.append("n_with_book cannot exceed n_markets")
    if record["n_markets"] > record["expected_markets"]:
        errs.append("n_markets cannot exceed expected_markets")
    # n_with_book and total_levels must agree on emptiness (a book-less capture has
    # zero levels; any depth implies at least one book with depth).
    if (record["n_with_book"] == 0) != (record["total_levels"] == 0):
        errs.append("n_with_book and total_levels disagree on emptiness")

    # completeness must be consistent with the counts (D3: completeness, not just liveness)
    if record["completeness_ok"] != (record["n_markets"] == record["expected_markets"]):
        errs.append("completeness_ok inconsistent with n_markets == expected_markets")

    # warmup invariant (C7): every Milestone-1 record is warm-up
    if record["warmup"] is not True:
        errs.append("warmup must be True for Milestone-1 capture (C7)")

    # signature shape + internal consistency (tamper-evidence)
    if not _SIG.match(record["signature"]):
        errs.append("signature: must match 'sha256:<64 hex>'")
    elif not verify_signature(record):
        errs.append("signature: self-hash does not match record content")

    return errs
