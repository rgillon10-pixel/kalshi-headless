"""Tests for scripts/l338_rederive.py — REDUNDANCY, not verification.

The point of this module is that it shares no code with the audit it re-derives, so these
tests pin (a) that its hand-rolled ISO parser really equals `core.timeutil.parse_iso_utc`
on real committed timestamps, (b) that its independence is structural (it does not import
the audit), and (c) that both implementations land on the same numbers on real tape.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.l338_rederive as R  # noqa: E402
import scripts.l338_trend_claim_scope_audit as A  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402


@pytest.mark.parametrize("stamp", [
    "2026-08-03T00:00:00Z",
    "2026-08-03T23:59:59.999999Z",
    "2026-08-03T12:34:56.789+00:00",
    "2026-01-01T00:00:00Z",
    "2026-12-31T23:00:00Z",
    "2024-02-29T06:07:08Z",      # leap day
    "2024-03-01T00:00:00Z",      # the day after a leap day
    "2100-03-01T00:00:00Z",      # a century year that is NOT a leap year
    "2000-03-01T00:00:00Z",      # a century year that IS a leap year
    "1970-01-01T00:00:00Z",      # the epoch itself
])
def test_hand_rolled_iso_parser_matches_core_timeutil(stamp):
    assert R.epoch_seconds(stamp) == pytest.approx(parse_iso_utc(stamp).timestamp(), abs=1e-6)


def test_parser_handles_a_short_fractional_second():
    assert R.epoch_seconds("2026-08-03T00:00:04.7Z") == pytest.approx(
        parse_iso_utc("2026-08-03T00:00:04.7Z").timestamp(), abs=1e-6)


def test_the_rederivation_does_not_import_the_module_it_rederives():
    """Structural independence — the whole value of the fallback rests on it."""
    tree = ast.parse(Path(R.__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any("l338_trend_claim_scope_audit" in m for m in imported)


def test_trend_helpers_reject_an_unmeasurable_cell():
    res = {"grid": {"probe_sports_sample": {"bracketed": [{"rate": 0.9}, {"rate": None}],
                                            "last_preceding": [{"rate": 0.1}, {"rate": 0.2}]},
                    "full_depth_day": {"bracketed": [{"rate": 0.9}, {"rate": None}],
                                       "last_preceding": [{"rate": 0.1}, {"rate": 0.2}]}}}
    assert R.join_rule_flips_direction(res) is False
    assert R.population_moves_nothing(res) is True


_HAVE = (A.DEPTH_TAPE / f"dt={A.DAY}.jsonl").exists() and \
        (A.TRADES_TAPE / f"dt={A.DAY}.jsonl").exists()
_real = pytest.mark.skipif(not _HAVE, reason="committed 2026-08-03 tape not present")


@pytest.fixture(scope="module")
def both():
    if not _HAVE:
        pytest.skip("committed 2026-08-03 tape not present")
    return A.build_report(), R.rederive()


@_real
def test_acceptance_the_two_implementations_agree_on_every_bid_side_cell(both):
    report, red = both
    for pop in ("probe_sports_sample", "full_depth_day"):
        for rule in ("bracketed", "last_preceding"):
            a = report["grid"][pop][rule][A.TAKER_BUYS]["cells"]
            b = red["grid"][pop][rule]
            assert [c["n_admitted_prints"] for c in a] == [c["n"] for c in b]
            for ca, cb in zip(a, b):
                assert ca["agreement_rate"] == pytest.approx(cb["rate"], abs=1e-12)


@_real
def test_acceptance_the_rederivation_reaches_the_same_two_conclusions(both):
    report, red = both
    assert R.population_moves_nothing(red) is True
    assert R.join_rule_flips_direction(red) is True
    assert report["attribution"]["driver"] == "join_rule"


@_real
def test_acceptance_main_runs(capsys):
    assert R.main([]) == 0
    assert "join rule flips direction: True" in capsys.readouterr().out
