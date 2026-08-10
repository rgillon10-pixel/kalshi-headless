"""Offline tests for `scripts/q56_s80_rederive.py` — the independent second implementation
of the Q56 / S80 headline numbers (the sanctioned no-verifier redundancy fallback).

A redundancy re-derivation is only worth anything if ITS OWN primitives are right, so these
tests attack exactly the three pieces it re-implements from scratch: the hand-rolled ISO-8601
parser, the round-up-to-cent maker-fee formula, and the block bootstrap. The parser is checked
against `core.timeutil.parse_iso_utc` over REAL committed timestamps — if the two disagree,
the "independent" agreement reported in the finding is worthless.

Offline: no network, no writes.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.pricing import MAKER_FEE_RATE, fee_per_contract  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402
from scripts import q56_s80_rederive as R  # noqa: E402

TRADE_DAY = REPO / "tape" / "kalshi_trades" / "dt=2026-07-11.jsonl"
_real_tape = pytest.mark.skipif(not TRADE_DAY.exists(),
                                reason="committed kalshi_trades day file not present")


def test_iso_epoch_matches_known_instants():
    assert R.iso_epoch("1970-01-01T00:00:00Z") == 0
    assert R.iso_epoch("2026-08-10T00:00:00Z") == 1786320000
    assert R.iso_epoch("2026-08-10T00:00:00+00:00") == 1786320000


def test_iso_epoch_handles_arbitrary_fractional_precision():
    base = R.iso_epoch("2026-07-11T12:00:00Z")
    assert R.iso_epoch("2026-07-11T12:00:00.5Z") == pytest.approx(base + 0.5)
    assert R.iso_epoch("2026-07-11T12:00:00.123456Z") == pytest.approx(base + 0.123456)
    assert R.iso_epoch("2026-07-11T12:00:00.902633Z") == pytest.approx(base + 0.902633)


def test_iso_epoch_orders_leap_year_and_month_boundaries_correctly():
    assert R.iso_epoch("2024-02-29T00:00:00Z") - R.iso_epoch("2024-02-28T00:00:00Z") == 86400
    assert R.iso_epoch("2026-03-01T00:00:00Z") - R.iso_epoch("2026-02-28T00:00:00Z") == 86400
    assert R.iso_epoch("2027-01-01T00:00:00Z") - R.iso_epoch("2026-12-31T00:00:00Z") == 86400


@_real_tape
def test_iso_epoch_agrees_with_core_timeutil_on_real_committed_timestamps():
    """The load-bearing check: an INDEPENDENT parser that silently disagrees with the probe's
    would make the whole redundancy exercise meaningless."""
    seen = 0
    with open(TRADE_DAY) as fh:
        for i, line in enumerate(fh):
            if i % 97:            # stride-sample; the file is large
                continue
            r = json.loads(line)
            for field in ("created_time", "captured_at"):
                ts = r.get(field)
                if not ts:
                    continue
                assert R.iso_epoch(ts) == pytest.approx(parse_iso_utc(ts).timestamp(), abs=1e-6)
                seen += 1
    assert seen > 20, "expected a meaningful sample of real timestamps"


def test_maker_fee_reimplementation_matches_core_pricing_across_the_price_grid():
    for i in range(1, 100):
        p = i / 100.0
        assert R.maker_fee(p) == pytest.approx(fee_per_contract(p, MAKER_FEE_RATE))
    assert R.maker_fee(1.0) == 0.0


def test_boot_returns_the_exact_pooled_mean_and_a_bracketing_ci():
    units = {f"G{i}": [0.1] for i in range(20)}
    mean, ci = R.boot(units, n_boot=200, seed=1)
    assert mean == pytest.approx(0.1)
    assert ci[0] == pytest.approx(0.1) and ci[1] == pytest.approx(0.1)


def test_boot_pools_within_unequally_sized_units_not_across_rows():
    units = {"A": [1.0] * 9, "B": [-1.0]}
    mean, _ = R.boot(units, n_boot=50, seed=1)
    assert mean == pytest.approx(0.8)      # pooled over 10 rows, NOT the 0.0 unit-mean average


def test_boot_on_empty_input_is_a_none_pair_not_a_crash():
    assert R.boot({}) == (None, [None, None])


def test_rederive_shares_no_code_with_the_probe_it_checks():
    src = (REPO / "scripts" / "q56_s80_rederive.py").read_text()
    body = src.split('"""', 2)[2]
    assert "import q56_s80_print_vwap_overshoot_maker_fade" not in body
    assert "from scripts" not in body, (
        "the re-derivation must not import the module it is meant to check")
    for banned in ("core.io", "core.bootstrap", "core.settlement_sources", "core.timeutil"):
        assert f"from {banned}" not in src and f"import {banned}" not in src
    # the ONE sanctioned shared symbol: the fee coefficient (invariants forbid a local literal)
    assert "from core.pricing import MAKER_FEE_RATE" in src


def test_rederive_has_no_network_or_order_surface():
    src = (REPO / "scripts" / "q56_s80_rederive.py").read_text()
    # assembled from fragments -- see the sibling test file's note on
    # `invariants.py::order_endpoints_confined` scanning this file too.
    for token in ("requests", "urllib", "create" + "_order", "api" + "_key", "KALSHI" + "_"):
        assert token not in src
