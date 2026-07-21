"""Offline, fixture-based tests for scripts/universe_sweep_liquidity_census.py.

Deterministic tiny synthetic JSONL in a tmp dir — no network, no real tape. Covers:
  * a fillable line counted as fillable,
  * a yes_ask==0 no-offer line EXCLUDED from fillable (L105),
  * a size=0.5 fractional line handled as float and BELOW the >=1 fillable floor (L47),
  * a liquid vs illiquid split at the 10-contract floor,
  * dead-tail series ranking + single-series dominance,
  * a size stored as float 91316.82 is NOT int-truncated (L47).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.universe_sweep_liquidity_census import (  # noqa: E402
    census, is_fillable, is_liquid, _as_float, series_prefix,
)


def _rec(**kw):
    base = {
        "schema_version": "universe_sweep.v1",
        "capture_id": "20260101T000000Z",
        "series": "KXTEST",
        "ticker": "KXTEST-A-B",
        "yes_ask": 0.0, "yes_ask_size": 0.0,
        "volume_24h": 0.0, "open_interest": 0.0, "volume": 0.0,
        "price_source_tag": "real_ask",
    }
    base.update(kw)
    return base


def _write(tmp_path, day, recs):
    fp = tmp_path / f"dt={day}.jsonl"
    with open(fp, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    return fp


def test_fillable_line_counted():
    assert is_fillable(_rec(yes_ask=0.45, yes_ask_size=5.0)) is True


def test_zero_ask_no_offer_excluded():
    # yes_ask == 0.0 is a NO-OFFER artifact, never a $0.00 fill (L105).
    assert is_fillable(_rec(yes_ask=0.0, yes_ask_size=1000.0)) is False


def test_fractional_size_below_fillable_floor():
    # 0.5 contracts < 1.0 -> not fillable; and must be read as float, not int-truncated to 0.
    assert _as_float("0.5") == 0.5
    assert is_fillable(_rec(yes_ask=0.30, yes_ask_size=0.5)) is False


def test_liquid_vs_illiquid_split():
    assert is_liquid(_rec(yes_ask=0.5, yes_ask_size=10.0)) is True
    assert is_liquid(_rec(yes_ask=0.5, yes_ask_size=9.99)) is False
    # a fillable-but-illiquid line: size between 1 and 10
    r = _rec(yes_ask=0.5, yes_ask_size=4.0)
    assert is_fillable(r) is True and is_liquid(r) is False


def test_large_float_size_not_truncated():
    # L47: a real observed best-level size was 91,316.82 contracts.
    v = _as_float(91316.82)
    assert v == 91316.82 and isinstance(v, float)
    assert is_fillable(_rec(yes_ask=0.5, yes_ask_size=91316.82)) is True
    assert is_liquid(_rec(yes_ask=0.5, yes_ask_size=91316.82)) is True


def test_series_prefix_fallback():
    assert series_prefix({"series": "KXFOO"}) == "KXFOO"
    assert series_prefix({"series": None, "ticker": "KXBAR-X-Y"}) == "KXBAR"


def test_census_end_to_end(tmp_path):
    recs = [
        _rec(yes_ask=0.45, yes_ask_size=50.0, volume_24h=100.0),  # fillable + liquid + active
        _rec(yes_ask=0.30, yes_ask_size=4.0),                     # fillable, illiquid
        _rec(yes_ask=0.30, yes_ask_size=0.5),                     # not fillable (frac size)
        _rec(series="KXDEAD", ticker="KXDEAD-1-2"),               # dead no-offer
        _rec(series="KXDEAD", ticker="KXDEAD-3-4"),               # dead no-offer
        _rec(series="KXDEAD", ticker="KXDEAD-5-6"),               # dead no-offer
    ]
    _write(tmp_path, "2026-01-01", recs)
    rep = census(tmp_path)

    assert rep["n_lines"] == 6
    assert rep["n_malformed"] == 0
    # 2 of 6 fillable
    assert rep["pooled"]["fillable"]["n"] == 2
    assert rep["pooled"]["fillable"]["frac_lines"] == round(2 / 6, 6)
    # 1 of 6 liquid
    assert rep["pooled"]["liquid"]["n"] == 1
    # activity: 1 line with volume_24h>0
    assert rep["pooled"]["activity"]["n_any"] == 1
    # dead tail = 4 (0.5 fractional + 3 KXDEAD); KXDEAD dominates with 3
    assert rep["dead_tail"]["n_dead"] == 4
    top = rep["dead_tail"]["top_series"]
    assert top[0]["series"] == "KXDEAD" and top[0]["n_dead"] == 3
    dom = rep["dead_tail"]["most_dominant_series"]
    assert dom["series"] == "KXDEAD"
    assert dom["frac_of_census"] == round(3 / 6, 6)


def test_malformed_line_counted_not_dropped(tmp_path):
    fp = tmp_path / "dt=2026-01-02.jsonl"
    with open(fp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(_rec(yes_ask=0.5, yes_ask_size=20.0)) + "\n")
        fh.write("{not valid json\n")
        fh.write("\n")  # blank line ignored, not malformed
    rep = census(tmp_path)
    assert rep["n_lines"] == 1
    assert rep["n_malformed"] == 1


def test_pass_stability_per_capture(tmp_path):
    day = "2026-01-03"
    recs = [
        _rec(capture_id="P1", yes_ask=0.5, yes_ask_size=20.0),  # fillable
        _rec(capture_id="P1", yes_ask=0.0, yes_ask_size=0.0),   # dead
        _rec(capture_id="P2", yes_ask=0.5, yes_ask_size=20.0),  # fillable
        _rec(capture_id="P2", yes_ask=0.5, yes_ask_size=20.0),  # fillable
    ]
    _write(tmp_path, day, recs)
    rep = census(tmp_path)
    st = rep["pass_stability"][day]
    assert st["n_passes"] == 2
    assert st["fillable_frac_min"] == 0.5   # P1: 1/2
    assert st["fillable_frac_max"] == 1.0   # P2: 2/2
