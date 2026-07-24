"""Offline tests for scripts/tape_timestamp_parseability_audit.py (L136/L138 census).

Fixture-only, no network, no real-tape scan. Pins the 3.9-hazard classifier AND
the load-bearing claim that core.timeutil.parse_iso_utc parses every hazardous
shape (bare-Z, short fraction, 9-digit nanosecond) to a tz-aware UTC datetime.
"""
import importlib.util
import json
import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location(
    "tape_ts_audit", os.path.join(_ROOT, "scripts", "tape_timestamp_parseability_audit.py")
)
audit_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit_mod)

from core.timeutil import parse_iso_utc


# --- classifier -----------------------------------------------------------

def test_clean_offset_and_frac_are_not_hazardous():
    for v in ("2026-07-24T00:55:28+00:00",
              "2026-07-24T00:55:28.123456+00:00",  # 6-digit frac + offset
              "2026-07-24T00:55:28.123+00:00"):     # 3-digit frac + offset
        haz, reason = audit_mod.classify(v)
        assert haz is False, v
        assert reason == "clean", v


def test_bare_z_is_hazardous():
    haz, reason = audit_mod.classify("2026-07-24T00:55:28Z")
    assert haz is True
    assert reason == "bare_z"


def test_short_fraction_z_is_hazardous_even_though_3_11_accepts_it():
    # The literal L136 shape. On 3.11 raw fromisoformat WOULD accept it; the
    # census must classify it hazardous via the digit-count rule, not by parsing.
    from datetime import datetime
    assert datetime.fromisoformat("2026-06-28T01:18:29.71Z".replace("Z", "+00:00"))
    haz, reason = audit_mod.classify("2026-06-28T01:18:29.71Z")
    assert haz is True
    assert "short_frac" in reason and "bare_z" in reason


def test_nanosecond_fraction_is_hazardous_overlen():
    haz, reason = audit_mod.classify("2026-07-24T00:55:28.475160531Z")  # 9 digits
    assert haz is True
    assert "overlen_frac" in reason


def test_secondsless_bare_z_is_hazardous():
    haz, reason = audit_mod.classify("2026-06-28T02:00Z")
    assert haz is True
    assert reason == "bare_z"


def test_non_timestamp_string_returns_none():
    for v in ("hello", "KXBTC-26JUL0621-B71750", "72.0", "yes", ""):
        assert audit_mod.classify(v) is None


# --- wrapper is the complete fix (load-bearing) ---------------------------

@pytest.mark.parametrize("v", [
    "2026-07-24T00:55:28Z",
    "2026-06-28T01:18:29.71Z",
    "2026-07-24T00:55:28.475160531Z",  # 9-digit nanosecond
    "2026-07-24T00:55:28.123456+00:00",
])
def test_parse_iso_utc_parses_every_hazardous_shape(v):
    r = parse_iso_utc(v)
    assert r is not None and r.tzinfo is not None
    assert r.utcoffset().total_seconds() == 0  # tz-aware UTC


# --- end-to-end over a fixture dir ----------------------------------------

def _write_fixture(tmp_path):
    fam = tmp_path / "famA"
    fam.mkdir()
    rows = [
        {"captured_at": "2026-07-24T00:55:28+00:00", "note": "clean"},
        {"captured_at": "2026-07-24T00:55:28.123456+00:00"},
        {"captured_at": "2026-07-24T00:55:28Z"},                 # bare_z
        {"captured_at": "2026-06-28T01:18:29.71Z"},              # short_frac + z
        {"exchange_time": "2026-07-24T00:55:28.475160531Z"},     # nanosecond + z
        {"ticker": "KXBTC-26JUL0621-B71750", "size": "12.5"},    # no ts field
    ]
    p = fam / "dt=2026-07-24.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return str(tmp_path)


def test_audit_end_to_end_urgent(tmp_path):
    rep = audit_mod.audit(_write_fixture(tmp_path))
    # 6 clean-eligible ts values: 2 clean + 3 hazardous + (the nanosecond).
    assert rep["total_ts_values"] == 5   # KX ticker + "12.5" are not ISO ts
    assert rep["hazardous"] == 3
    assert rep["unparseable"] == 0
    assert rep["parse_iso_utc_failures"] == 0
    assert rep["reason_breakdown"].get("bare_z", 0) == 3
    assert rep["reason_breakdown"].get("overlen_frac", 0) == 1
    assert rep["reason_breakdown"].get("short_frac", 0) == 1
    assert rep["verdict"] == "URGENT"


def test_audit_all_clean_is_benign(tmp_path):
    fam = tmp_path / "famB"
    fam.mkdir()
    (fam / "dt=2026-07-24.jsonl").write_text(
        json.dumps({"captured_at": "2026-07-24T00:55:28+00:00"}) + "\n"
    )
    rep = audit_mod.audit(str(tmp_path))
    assert rep["hazardous"] == 0
    assert rep["verdict"] == "BENIGN"
