"""The Hard-Rule invariant engine fires on violations, exempts the sanctioned sites, and
finds the real tree clean. These are adversarial fixtures by design (this file is on the
engine's EXCLUDE_FILES list so its own banned-pattern strings don't self-trip)."""
from __future__ import annotations

import importlib.util
import pathlib
import sqlite3

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_engine():
    spec = importlib.util.spec_from_file_location("inv_engine", ROOT / "scripts" / "invariants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inv = _load_engine()

# A path that is NOT any sanctioned site or excluded file — a generic runtime module.
GENERIC = ROOT / "some_runtime_module.py"

VIOLATIONS = {
    "no_gefs": 'MODELS = ["gfs_seamless", "ncep_gefs025"]',
    "no_bare_pstdev": "spread = pstdev(members)",
    "no_pstdev_import": "from statistics import pstdev",
    "no_yes_ask_arithmetic": "p = yes_ask / bracket_sum",
    "no_static_rho_point_four": "rho = 0.4",
    "no_http_server": "from fastapi import FastAPI",
}


@pytest.mark.parametrize("rule,snippet", list(VIOLATIONS.items()))
def test_each_rule_fires_on_a_violation(rule, snippet):
    failures = inv.scan_text(GENERIC, snippet)
    assert any(f"[{rule}]" in f for f in failures), f"{rule} did not fire on: {snippet!r}\n{failures}"


def test_clean_text_passes():
    assert inv.scan_text(GENERIC, "x = 1 + 2\nreturn x\n") == []


def test_pstdev_exempt_in_sanctioned_stats_site():
    # core/stats.py is the one home allowed to call pstdev (behind safe_pstdev's n>=4 guard)
    assert inv.scan_text(ROOT / "core" / "stats.py", "v = pstdev(values)") == []


def test_yes_ask_arithmetic_exempt_in_sanctioned_pricing_site():
    # core/pricing.py is the one home allowed to do yes_ask/bracket_sum arithmetic
    assert inv.scan_text(ROOT / "core" / "pricing.py", "p = yes_ask / bracket_sum") == []


def test_sentinel_line_is_skipped():
    line = "MODELS = ['ncep_gefs025']  # inv-pattern-def"
    assert inv.scan_text(GENERIC, line) == []


def test_real_tree_is_green():
    assert inv.scan_tree() == [], "the committed tree must satisfy every Hard Rule"


# ─── DB invariants ────────────────────────────────────────────────────────────

def _db(tmp_path, name, ddl, rows_sql=()):
    p = tmp_path / name
    con = sqlite3.connect(p)
    con.executescript(ddl)
    for stmt in rows_sql:
        con.execute(stmt)
    con.commit()
    con.close()
    return p


def test_db_clean_backtest_passes(tmp_path):
    db = _db(
        tmp_path, "clean.db",
        "CREATE TABLE backtest (pnl REAL, price_source_tag TEXT, fair_probability REAL);",
        ["INSERT INTO backtest VALUES (0.12, 'real_ask', 0.61)",
         "INSERT INTO backtest VALUES (-0.05, 'synthetic', 0.40)"],
    )
    assert inv.scan_db(db) == []


def test_db_pnl_with_null_tag_is_caught(tmp_path):
    db = _db(
        tmp_path, "nulltag.db",
        "CREATE TABLE backtest (pnl REAL, price_source_tag TEXT);",
        ["INSERT INTO backtest VALUES (0.30, NULL)"],
    )
    fails = inv.scan_db(db)
    assert any("pnl_requires_tag" in f for f in fails), fails


def test_db_pnl_without_tag_column_is_caught(tmp_path):
    db = _db(
        tmp_path, "notagcol.db",
        "CREATE TABLE backtest (pnl REAL, note TEXT);",
        ["INSERT INTO backtest VALUES (0.30, 'x')"],
    )
    fails = inv.scan_db(db)
    assert any("no price_source_tag column" in f for f in fails), fails


def test_db_invalid_enum_value_is_caught(tmp_path):
    db = _db(
        tmp_path, "badenum.db",
        "CREATE TABLE signals (price_source_tag TEXT);",
        ["INSERT INTO signals VALUES ('guess')"],
    )
    fails = inv.scan_db(db)
    assert any("price_source_tag" in f for f in fails), fails


def test_db_probability_out_of_range_is_caught(tmp_path):
    db = _db(
        tmp_path, "prob.db",
        "CREATE TABLE signals (fair_probability REAL);",
        ["INSERT INTO signals VALUES (1.4)"],
    )
    fails = inv.scan_db(db)
    assert any("probability_in_range" in f for f in fails), fails
