"""Offline tests for `scripts/q56_s81_rederive.py` — the independent second implementation of
the Q56 / S81 headline numbers (the sanctioned no-verifier redundancy fallback).

A redundancy re-derivation is only worth anything if ITS OWN primitives are right, so these
tests attack exactly the pieces it re-implements from scratch: the hand-rolled ISO-8601
parser (checked against `core.timeutil.parse_iso_utc` on REAL committed timestamps — if the
two silently disagreed, the reported agreement would be worthless), the funding baseline
re-derived from L318's text, the round-up-to-cent taker-fee formula, the regime-run blocker
and the block bootstrap.

Offline: no network, no writes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.pricing import TAKER_FEE_RATE, fee_per_contract  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402
from scripts import q56_s81_rederive as R  # noqa: E402

CRYPTO_DAY = REPO / "tape" / "crypto_hourly" / "dt=2026-07-22.jsonl"
_real_tape = pytest.mark.skipif(not CRYPTO_DAY.exists(),
                                reason="committed crypto_hourly day file not present")


# --------------------------------------------------------------------------- #
# the hand-rolled primitives
# --------------------------------------------------------------------------- #
def test_iso_epoch_matches_known_instants():
    assert R.iso_epoch("1970-01-01T00:00:00Z") == 0
    assert R.iso_epoch("2026-08-10T00:00:00Z") == 1786320000
    assert R.iso_epoch("2026-08-10T00:00:00+00:00") == 1786320000


def test_iso_epoch_handles_arbitrary_fractional_precision():
    base = R.iso_epoch("2026-07-22T12:00:00Z")
    assert R.iso_epoch("2026-07-22T12:00:00.5Z") == pytest.approx(base + 0.5)
    assert R.iso_epoch("2026-07-22T12:00:00.295146Z") == pytest.approx(base + 0.295146)


def test_iso_epoch_orders_leap_year_and_month_boundaries_correctly():
    assert R.iso_epoch("2024-02-29T00:00:00Z") - R.iso_epoch("2024-02-28T00:00:00Z") == 86400
    assert R.iso_epoch("2026-03-01T00:00:00Z") - R.iso_epoch("2026-02-28T00:00:00Z") == 86400


@_real_tape
def test_iso_epoch_agrees_with_core_timeutil_on_real_committed_timestamps():
    seen = 0
    with open(CRYPTO_DAY) as fh:
        for line in fh:            # small file (the L327 cadence collapse) — read it all
            rec = json.loads(line)
            for ts in (rec.get("captured_at"), (rec.get("current") or {}).get("close_time")):
                if not ts:
                    continue
                assert R.iso_epoch(ts) == pytest.approx(parse_iso_utc(ts).timestamp(), abs=1e-6)
                seen += 1
    assert seen > 20, "expected a meaningful sample of real timestamps"


def test_the_baseline_is_rederived_from_l318s_text_not_imported():
    """0.01% per 8 hours, hourly — the number L318 states in words."""
    assert R.BASELINE == pytest.approx(1.25e-05)
    src = (REPO / "scripts" / "q56_s81_rederive.py").read_text()
    assert "HL_BASELINE_HOURLY_RATE" not in src


def test_taker_fee_reimplementation_matches_core_pricing_across_the_price_grid():
    for i in range(1, 100):
        p = i / 100.0
        assert R.fee(p) == pytest.approx(fee_per_contract(p, TAKER_FEE_RATE))


def test_regime_labels_split_at_the_baseline_and_at_zero():
    assert R.label_of(R.BASELINE) == "pin"
    assert R.label_of(R.BASELINE / 2) == "sub_baseline"
    assert R.label_of(-1e-9) == "negative"
    assert R.label_of(R.BASELINE * 2) == "above_baseline"


def test_runs_break_on_a_label_change_and_on_a_missing_hour():
    hours = {("BTC", 100): R.BASELINE, ("BTC", 101): R.BASELINE,      # one pin run
             ("BTC", 102): 0.0,                                        # label change
             ("BTC", 104): 0.0}                                        # hour 103 missing
    runs = R.runs_of(hours)
    ids = [runs[("BTC", h)][0] for h in (100, 101, 102, 104)]
    assert ids[0] == ids[1]
    assert len({ids[0], ids[2], ids[3]}) == 3


def test_boot_returns_a_bracketing_ci_on_a_degenerate_population():
    lo, hi = R.boot({f"U{i}": [0.1] for i in range(20)}, n_boot=200, seed=1)
    assert lo == pytest.approx(0.1) and hi == pytest.approx(0.1)


def test_boot_pools_within_unequally_sized_units_not_across_rows():
    lo, hi = R.boot({"A": [1.0] * 9, "B": [-1.0]}, n_boot=200, seed=1)
    assert lo <= 0.8 <= hi


# --------------------------------------------------------------------------- #
# independence
# --------------------------------------------------------------------------- #
def test_rederive_shares_no_code_with_the_probe_it_checks():
    src = (REPO / "scripts" / "q56_s81_rederive.py").read_text()
    body = src.split('"""', 2)[2]
    assert "q56_s81_funding_regime_settlement_probe" not in body
    assert "from scripts" not in body, (
        "the re-derivation must not import the module it is meant to check")
    for banned in ("core.io", "core.bootstrap", "core.settlement_sources", "core.settlement",
                   "core.timeutil", "hl_funding_tape_quality"):
        assert f"from {banned}" not in src and f"import {banned}" not in src
    # the ONE sanctioned shared symbol: the fee coefficient (invariants forbid a local literal)
    assert "from core.pricing import TAKER_FEE_RATE" in src


def test_rederive_uses_a_different_bootstrap_seed_than_the_probe():
    """An independent DRAW is the point; sharing seed 42 would fake agreement."""
    assert R.SEED != 42


def test_rederive_has_no_network_or_order_surface():
    src = (REPO / "scripts" / "q56_s81_rederive.py").read_text()
    # assembled from fragments so this file does not itself trip
    # `invariants.py::order_endpoints_confined`, which scans test files too.
    for token in ("requests", "urllib", "create" + "_order", "api" + "_key", "KALSHI" + "_"):
        assert token not in src
