"""Tests for the INDEPENDENT re-derivation of the close_time-mutation audit.

Two jobs: pin that the re-derivation really is independent (a redundancy pass that imports the
thing it checks proves nothing), and pin the reconciliation it produced on committed tape.
"""
from __future__ import annotations

import ast
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

import close_time_mutation_audit as A  # noqa: E402
import close_time_mutation_rederive as R  # noqa: E402


def _imports(module) -> set:
    tree = ast.parse(open(module.__file__).read())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            out.add(node.module or "")
    return out


class TestIndependence:
    def test_imports_neither_the_audit_nor_the_shared_primitives_nor_the_registry(self):
        imported = _imports(R)
        for banned in ("core.close_time_mutation", "core.settlement_sources",
                       "core.result_evidence", "close_time_mutation_audit"):
            assert banned not in imported, banned

    def test_the_only_permitted_project_import_is_the_mandated_iso_parser(self):
        # L136/L150 GATE every new raw `datetime.fromisoformat` site, so a private parser here
        # would be independence bought with a known Python-3.9 crash. This pins that the
        # exception stays exactly one module wide and does not grow into shared logic.
        project = {m for m in _imports(R) if m.split(".")[0] in ("core", "collection",
                                                                "execution", "scripts")}
        assert project == {"core.timeutil"}

    def test_it_publishes_the_limit_that_shared_parser_creates(self):
        doc = R.__doc__ or ""
        assert "HONEST LIMIT" in doc or "one published limit" in doc

    def test_it_finds_cache_files_by_glob_not_by_the_declared_registry(self):
        # A registry omission must not be able to hide a file from BOTH implementations.
        src = open(R.__file__).read()
        assert "settlement*.json" in src
        assert "SETTLEMENT_SOURCES" not in src

    def test_it_makes_no_network_call(self):
        src = open(R.__file__).read()
        for banned in ("requests", "urllib", "httpx", "socket", "aiohttp"):
            assert banned not in src, banned

    def test_its_tape_root_is_absolute(self):
        assert os.path.isabs(R.TAPE_ROOT)

    def test_it_answers_live_stability_without_reading_captured_at(self):
        # The audit orders each ticker's observations and compares first to last. This counts
        # distinct (ticker, close_time) pairs and needs no ordering at all, so a clock defect
        # cannot produce the same answer twice.
        src = ast.parse(open(R.__file__).read())
        fn = next(n for n in ast.walk(src)
                  if isinstance(n, ast.FunctionDef) and n.name == "rederive_live")
        assert "captured_at" not in ast.unparse(fn)


class TestPositionalAttribution:
    def test_a_field_is_attributed_to_the_nearest_preceding_ticker_key(self, tmp_path):
        p = tmp_path / "settlement.json"
        p.write_text(json.dumps({"markets": {
            "KX-AAA-1": {"close_time": "2026-08-01T00:00:00Z", "result": "yes"},
            "KX-BBB-2": {"close_time": "2026-08-02T00:00:00Z", "result": "no"},
        }}), encoding="utf-8")
        scan = R.scan_cache_file(str(p))
        assert scan["KX-AAA-1"]["result"] == "yes"
        assert scan["KX-BBB-2"]["close_time"] == "2026-08-02T00:00:00Z"

    def test_settled_matches_the_audits_rule_including_closed_being_unsettled(self):
        assert R._settled({"result": "no"}) is True
        assert R._settled({"result": "", "status": "finalized"}) is True
        assert R._settled({"result": "", "status": "closed"}) is False
        assert R._settled({"result": "", "status": "active"}) is False


class TestReconciliation:
    """Every headline number, both implementations, on the real committed tree."""

    @pytest.fixture(scope="module")
    def pair(self):
        return A.build_report(include_live=False), R.rederive_caches()

    def test_both_enumerate_the_same_number_of_cache_files(self, pair):
        audit, red = pair
        assert audit["n_cache_blobs"] == red["n_cache_files"]

    def test_paired_observation_counts_agree(self, pair):
        audit, red = pair
        assert audit["blob_pairs"]["pooled"]["n_pairs"] == red["n_paired_observations"]

    def test_every_regime_observation_count_agrees(self, pair):
        audit, red = pair
        for regime, n in red["regime_observation_counts"].items():
            assert audit["blob_pairs"]["pooled"]["by_regime"][regime]["n"] == n, regime

    def test_distinct_ticker_counts_agree(self, pair):
        audit, red = pair
        dc = audit["blob_pairs"]["distinct_ticker_counts"]
        assert dc["n_distinct_tickers"] == red["n_distinct_tickers_across_pairs"]
        assert dc["n_distinct_instant_changed"] == red["n_distinct_close_time_changed"]
        assert dc["n_distinct_date_changed"] == red["n_distinct_close_date_changed"]
        assert dc["n_distinct_open_to_settled"] == red["n_distinct_open_to_settled"]

    def test_the_direction_is_one_sided_in_both(self, pair):
        audit, red = pair
        assert red["n_observations_moved_later"] == 0
        assert red["n_observations_moved_earlier"] > 0
        pooled = audit["blob_pairs"]["pooled"]["by_regime"]
        assert sum(b["moved_later"] for b in pooled.values()) == 0
        assert sum(b["moved_earlier"] for b in pooled.values()) == \
            red["n_observations_moved_earlier"]

    def test_both_find_zero_settled_label_conflicts(self, pair):
        audit, red = pair
        assert audit["blob_pairs"]["n_settled_result_conflicts"] == 0
        assert red["n_settled_result_conflicts"] == 0
