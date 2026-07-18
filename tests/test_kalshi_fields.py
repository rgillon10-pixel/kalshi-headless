"""core.kalshi_fields — shared `_dollars` / `_fp` numeric field parser (lesson L90/L100).

Before this module, `collection/settlement_ledger.py` and `collection/universe_sweep.py`
each hand-rolled a byte-identical `_to_float` helper. This pins the shared implementation's
behavior directly; the two collectors now import it (see their own test files for the
per-module regression coverage, unchanged by this refactor).
"""
from __future__ import annotations

from core.kalshi_fields import parse_kalshi_numeric


def test_parses_valid_numeric_strings():
    assert parse_kalshi_numeric("1.0000") == 1.0
    assert parse_kalshi_numeric("12.50") == 12.5
    assert parse_kalshi_numeric("0") == 0.0


def test_none_and_blank_are_honest_none_never_fabricated_zero():
    assert parse_kalshi_numeric(None) is None
    assert parse_kalshi_numeric("") is None
    assert parse_kalshi_numeric("   ") is None


def test_unparseable_string_is_none():
    assert parse_kalshi_numeric("garbage") is None


def test_passthrough_for_already_numeric_values():
    assert parse_kalshi_numeric(3) == 3.0
    assert parse_kalshi_numeric(3.5) == 3.5


def test_strips_surrounding_whitespace():
    assert parse_kalshi_numeric("  4.25  ") == 4.25
