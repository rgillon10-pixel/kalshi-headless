"""Tests for `scripts/depth_label_substrate_rederive.py` — the redundancy half of the
2026-08-15 depth-substrate census (no `Task`/verifier subagent exists in this harness).

The point of a redundancy script is that it shares nothing with the thing it checks, so the
first test pins exactly that: it must not import the census module, `core.settlement_sources`,
or any repo helper (AST-level, the L338/`l338_rederive` precedent)."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "scripts" / "depth_label_substrate_rederive.py"


def _load():
    spec = importlib.util.spec_from_file_location("_dls_rederive", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


red = _load()


def test_rederive_shares_no_code_with_the_census_or_the_repo_helpers():
    tree = ast.parse(SRC.read_text())
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            imported.add(n.module.split(".")[0])
    assert "core" not in imported
    assert not any(i.startswith("depth_label_substrate") for i in imported)
    assert imported <= {"__future__", "argparse", "json", "os", "glob", "typing"}


def test_raw_ticker_extraction_matches_a_full_parse():
    line = json.dumps({"best_yes_ask": 0.4, "ticker": "KXBTC-26AUG0101-B1", "depth": 50})
    assert red._ticker_of_raw(line) == json.loads(line)["ticker"]


def test_raw_ticker_extraction_abstains_on_a_line_without_the_field():
    assert red._ticker_of_raw('{"depth":50}') == ""
    assert red._ticker_of_raw("garbage") == ""


def test_median_matches_the_two_parity_cases():
    assert red.median([3, 1, 2]) == 2.0
    assert red.median([4, 1, 2, 3]) == 2.5
    assert red.median([]) is None


def test_klass_partitions_like_the_census_does():
    assert red.klass("KXETH-1-B1") == "crypto"
    assert red.klass("KXMLBGAME-1-NYY") == "sports"
    assert red.klass("KXTEMPNYCH-1-B1") == "other"


def _tape(tmp_path):
    (tmp_path / "orderbook_depth").mkdir(parents=True)
    (tmp_path / "orderbook_depth" / "dt=2026-08-01.jsonl").write_text(
        "".join(json.dumps({"ticker": t, "captured_at": "2026-08-01T00:00:00Z"}) + "\n"
                for t in ["KXBTC-26AUG0101-B1", "KXBTC-26AUG0101-B1", "KXBTC-26AUG0101-B2"]))
    (tmp_path / "crypto_hourly").mkdir()
    (tmp_path / "crypto_hourly" / "dt=2026-08-01.jsonl").write_text(json.dumps(
        {"previous_settlement": {"status": "settled",
                                 "results": {"KXBTC-26AUG0101-B1": "yes",
                                             "KXBTC-26AUG0101-B2": "no"}}}) + "\n")
    return str(tmp_path)


def test_rederive_recomputes_the_conditioned_ready_only_block(tmp_path):
    """The corrected headline (verifier round 3, 2026-08-15) must be reproduced by the
    redundancy implementation too, or the correction has only one witness."""
    c = red.rederive(_tape(tmp_path))["by_class"]["crypto"]
    assert c["n_ready_legs"] == 2
    assert c["ready_median_snapshots_per_leg"] == 1.5
    assert c["n_units_every_leg_ge_2"] == 0      # leg B2 has a single snapshot
    assert c["n_units_all_legs_single"] == 0     # ... and B1 has two, so the unit is MIXED


def test_rederive_reads_the_embedded_source_the_naive_union_misses(tmp_path):
    out = red.rederive(_tape(tmp_path))
    assert out["n_tickers"] == 2 and out["n_snapshots"] == 3
    assert out["n_resolved_total"] == 2
    assert out["n_resolved_naive_union"] == 0
    c = out["by_class"]["crypto"]
    assert c["n_units"] == 1 and c["n_probe_ready"] == 1
    assert c["median_snapshots_per_leg"] == 1.5


def test_compare_reports_a_disagreement_field_by_field(tmp_path):
    mine = red.rederive(_tape(tmp_path))
    fake = {"population": {"n_tickers": 99, "n_snapshots": mine["n_snapshots"]},
            "label_coverage": {"n_resolved_total": mine["n_resolved_total"],
                               "n_resolved_naive_union_only": mine["n_resolved_naive_union"],
                               "by_class": {c: {"n_tickers": v["n_tickers"],
                                                "n_resolved": v["n_resolved"]}
                                            for c, v in mine["by_class"].items()}},
            "unit_readiness": {c: {"n_units": v["n_units"], "n_probe_ready": v["n_probe_ready"],
                                   "n_distinct_ready_days": v["n_distinct_ready_days"]}
                               for c, v in mine["by_class"].items()},
            "fill_observability": {c: {"median_snapshots_per_leg": v["median_snapshots_per_leg"],
                                       "frac_legs_with_ge_2_snapshots":
                                           v["frac_legs_with_ge_2_snapshots"]}
                                   for c, v in mine["by_class"].items()},
            "fill_observability_ready_only": {
                c: {"median_snapshots_per_leg": v["ready_median_snapshots_per_leg"],
                    "frac_legs_with_ge_2_snapshots": v["ready_frac_legs_with_ge_2_snapshots"],
                    "n_ready_legs": v["n_ready_legs"],
                    "n_units_every_leg_ge_2": v["n_units_every_leg_ge_2"],
                    "n_distinct_days_every_leg_ge_2": v["n_distinct_days_every_leg_ge_2"],
                    "n_units_all_legs_single": v["n_units_all_legs_single"]}
                for c, v in mine["by_class"].items()}}
    diffs = red.compare(mine, fake)
    assert len(diffs) == 1 and diffs[0].startswith("n_tickers:")


def test_compare_is_silent_when_everything_agrees(tmp_path):
    mine = red.rederive(_tape(tmp_path))
    good = {"population": {"n_tickers": mine["n_tickers"], "n_snapshots": mine["n_snapshots"]},
            "label_coverage": {"n_resolved_total": mine["n_resolved_total"],
                               "n_resolved_naive_union_only": mine["n_resolved_naive_union"],
                               "by_class": {c: {"n_tickers": v["n_tickers"],
                                                "n_resolved": v["n_resolved"]}
                                            for c, v in mine["by_class"].items()}},
            "unit_readiness": {c: {"n_units": v["n_units"], "n_probe_ready": v["n_probe_ready"],
                                   "n_distinct_ready_days": v["n_distinct_ready_days"]}
                               for c, v in mine["by_class"].items()},
            "fill_observability": {c: {"median_snapshots_per_leg": v["median_snapshots_per_leg"],
                                       "frac_legs_with_ge_2_snapshots":
                                           v["frac_legs_with_ge_2_snapshots"]}
                                   for c, v in mine["by_class"].items()},
            "fill_observability_ready_only": {
                c: {"median_snapshots_per_leg": v["ready_median_snapshots_per_leg"],
                    "frac_legs_with_ge_2_snapshots": v["ready_frac_legs_with_ge_2_snapshots"],
                    "n_ready_legs": v["n_ready_legs"],
                    "n_units_every_leg_ge_2": v["n_units_every_leg_ge_2"],
                    "n_distinct_days_every_leg_ge_2": v["n_distinct_days_every_leg_ge_2"],
                    "n_units_all_legs_single": v["n_units_all_legs_single"]}
                for c, v in mine["by_class"].items()}}
    assert red.compare(mine, good) == []
