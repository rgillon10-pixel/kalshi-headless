"""Offline tests for the Q57 / S82 independent re-derivation.

This file's whole value is that the re-derivation shares no code with the probe. The tests
therefore pin (a) the hand-written ISO->epoch parser against the stdlib on real tape shapes,
and (b) the structural independence itself, so a future refactor cannot quietly make the
"second implementation" import the first and stop being a check.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import q57_s82_rederive as R


@pytest.mark.parametrize("ts", [
    "2026-07-07T23:59:56.902633Z",
    "2026-07-07T00:57:50.299698+00:00",
    "2026-08-16T12:00:00Z",
    "2026-01-01T00:00:00Z",
    "2026-02-28T23:59:59Z",
    "2024-02-29T12:34:56Z",          # leap day
    "2026-12-31T23:59:59.5Z",        # short fraction (L150's shape)
    "1970-01-01T00:00:00Z",
])
def test_handrolled_epoch_matches_the_sanctioned_parser(ts):
    """Compared against `core.timeutil.parse_iso_utc`, the repo's one sanctioned ISO parser
    (L136/L150) — not against the stdlib directly, which Python 3.9 (the declared floor)
    rejects on the bare-`Z` and short-fraction shapes that are 38.27% of committed tape."""
    from core.timeutil import parse_iso_utc
    assert R.epoch(ts) == pytest.approx(parse_iso_utc(ts).timestamp(), abs=1e-6)


def test_epoch_rejects_a_non_utc_offset_rather_than_mis_parsing():
    with pytest.raises(ValueError):
        R.epoch("2026-07-07T12:00:00-04:00")


def test_is_game_matches_the_sports_moneyline_family_and_excludes_kxmve():
    assert R.is_game("KXMLBGAME-26JUL061915NYMATL-ATL")
    assert not R.is_game("KXMVESPORTSMULTIGAMEEXTENDED-S2026-0A6")
    assert not R.is_game("KXBTC-26JUL0621-T71799.99")


def test_rederive_imports_nothing_from_the_probe_or_from_core():
    """The independence IS the check. If this file ever imports the probe or core, the
    'second implementation' has become an echo and stops being redundancy.

    Checked over the AST (imports) plus a source scan with docstrings stripped, so the
    module's own prose about what it does NOT import cannot satisfy or trip the check."""
    import ast
    tree = ast.parse(Path(R.__file__).read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert "core" not in mods
    assert not any(m.startswith("q57") or m == "scripts" for m in mods)
    assert "datetime" not in mods

    for node in ast.walk(tree):   # strip every docstring, then scan what is left
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                first.value.value = ""
    code = ast.unparse(tree)
    for banned in ("fromisoformat", "q57_s82_flow_fade_probe", "core.timeutil"):
        assert banned not in code, banned


def test_probe_and_rederive_agree_on_the_committed_tape():
    """The two-agent substitute, executed: exit 0 means every headline matched exactly."""
    assert R.main() == 0
