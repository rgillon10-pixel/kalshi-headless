"""Determinism + content-hashing primitives — the single definition for the harness.

Every byte the harness commits or content-addresses passes through here, so
"byte-identical on re-run" (Milestone 1 criterion 1) and content-addressing (D3
bitemporal store) have exactly one meaning. These are pure functions of their input:
no wall-clock, no randomness, no environment reads.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no insignificant whitespace, ASCII-escaped.

    Two structurally-equal objects always serialize to the identical string, so the
    sha256 of the result is a stable content id. Floats serialize via Python's
    round-trip repr (stable within an interpreter); round numeric values upstream
    (the normalizer does) so the committed bytes don't depend on float formatting.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(data: Any) -> str:
    """SHA-256 hex digest of bytes/str (str is UTF-8 encoded). Hashes are lowercase."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    elif not isinstance(data, (bytes, bytearray)):
        raise TypeError(f"sha256_hex expects bytes or str, got {type(data).__name__}")
    return hashlib.sha256(data).hexdigest()
