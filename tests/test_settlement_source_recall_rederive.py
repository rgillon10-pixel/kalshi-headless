"""Tests for the independent re-derivation of the settlement-source recall audit.

Two jobs: pin that the re-derivation really is independent (a redundancy pass that imports the
thing it is checking proves nothing), and pin the reconciliation it produced — including the
two bugs the disagreement exposed IN THE RE-DERIVATION, which is what a redundancy pass is for.
"""
from __future__ import annotations

import ast
import json
import os
import sys

import pytest

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, _SCRIPTS)

import settlement_source_recall_audit as A  # noqa: E402
import settlement_source_recall_rederive as R  # noqa: E402


class TestIndependence:
    def test_imports_neither_the_audit_nor_the_shared_detector_nor_the_resolver(self):
        tree = ast.parse(open(R.__file__).read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        for banned in ("core.result_evidence", "core.settlement_sources", "core.settlement",
                       "settlement_source_recall_audit"):
            assert banned not in imported, banned

    def test_makes_no_network_call(self):
        src = open(R.__file__).read()
        for banned in ("requests", "urllib", "httpx", "socket", "aiohttp"):
            assert banned not in src, banned

    def test_it_declares_itself_redundancy_not_verification(self):
        doc = R.__doc__ or ""
        assert "REDUNDANCY, NOT VERIFICATION" in doc


class TestAttributionRule:
    def test_attributes_a_result_to_the_nearest_ticker_in_EITHER_direction(self):
        """The bug this test exists for: these files are written with `sort_keys=True`, so
        `result` lands BEFORE `ticker` in the same object while a ticker-keyed map puts the
        key first. A nearest-PRECEDING rule attributed every label to its neighbour and
        under-counted `sports_history` 341 -> 214."""
        blob = json.dumps({"outcomes": [
            {"result": "yes", "ticker": "AAA-BBB-CCC"},
            {"result": "no", "ticker": "AAA-BBB-DDD"}]}, sort_keys=True).encode()
        assert R._labels_in_blob(blob) == {"AAA-BBB-CCC": "yes", "AAA-BBB-DDD": "no"}

    def test_reads_market_ticker_as_well_as_ticker(self):
        """The second bug: `tape/sports_history_s7/` names the field `market_ticker`, and a
        reader that only knew `ticker` scored the whole family as 0 labels."""
        blob = json.dumps({"market_ticker": "AAA-BBB-CCC", "result": "yes"}, sort_keys=True).encode()
        assert R._labels_in_blob(blob) == {"AAA-BBB-CCC": "yes"}

    def test_a_ticker_keyed_map_attributes_by_its_key(self):
        blob = json.dumps({"KXBTC-26JUL1012-B53250": {"result": "no"}}).encode()
        assert R._labels_in_blob(blob) == {"KXBTC-26JUL1012-B53250": "no"}

    def test_empty_and_scalar_results_are_not_labels(self):
        blob = json.dumps({"outcomes": [{"result": "", "ticker": "AAA-BBB-CCC"},
                                        {"result": "scalar", "ticker": "AAA-BBB-DDD"}]}).encode()
        assert R._labels_in_blob(blob) == {}

    def test_a_ticker_labeled_both_ways_is_dropped_not_last_write_wins(self):
        blob = (b'{"ticker":"AAA-BBB-CCC","result":"yes"}'
                b'{"ticker":"AAA-BBB-CCC","result":"no"}')
        assert R._labels_in_blob(blob) == {}


@pytest.mark.skipif(not os.path.isdir("tape/orderbook_depth"), reason="needs committed tape")
class TestReconciliationOnRealTape:
    """Directions and identities, never frozen counts."""

    @pytest.fixture(scope="class")
    @classmethod
    def pair(cls):
        return A.audit("tape"), R.rederive("tape")

    def test_line_counts_agree_family_by_family(self, pair):
        audit, rede = pair
        for fam, sc in audit["family_scan"].items():
            assert sc["n_lines"] == rede["per_family"][fam]["n_lines"], fam

    def test_labeled_ticker_counts_agree_on_every_family_outside_the_published_limit(self, pair):
        """Excluded BY NAME, never by loosening the assertion: the positional reader's own
        published limit is ticker-KEYED MAPS with small objects."""
        audit, rede = pair
        known = set(R.known_disagreement_families())
        for fam, sc in audit["family_scan"].items():
            if fam in known:
                continue
            assert (sc["n_binary_labeled_tickers"]
                    == rede["per_family"][fam]["n_binary_labeled_tickers"]), fam

    def test_the_published_limit_is_small_and_confined_to_declared_cache_maps(self, pair):
        """A limit is only honest if its size is measured. Every family it touches is a
        DECLARED source the audit reads through the sanctioned resolver anyway, so it cannot
        reach the headline."""
        audit, rede = pair
        from core.settlement_sources import declared_source_names
        declared = set(declared_source_names())
        for fam in R.known_disagreement_families():
            a = audit["family_scan"][fam]["n_binary_labeled_tickers"]
            b = rede["per_family"][fam]["n_binary_labeled_tickers"]
            assert fam in declared, fam
            assert abs(a - b) <= max(3, a // 100), (fam, a, b)

    def test_the_schema_only_family_agrees_on_its_empty_result_count(self, pair):
        audit, rede = pair
        assert (audit["family_scan"]["sports_pairs"]["n_schema_only_result_nodes"]
                == rede["per_family"]["sports_pairs"]["n_empty_result_nodes"])

    def test_universe_sweep_closed_count_agrees_and_neither_sees_a_settled_market(self, pair):
        audit, rede = pair
        assert (audit["family_scan"]["universe_sweep"]["n_closed_not_settled_nodes"]
                == rede["per_family"]["universe_sweep"]["n_closed_status_nodes"])
        assert rede["per_family"]["universe_sweep"]["n_terminal_status_nodes"] == 0

    def test_the_two_substrate_intersections_reconcile_exactly(self, pair):
        """The re-derivation counts ALL candidate labels; the audit counts only NET-NEW ones.
        The difference must be exactly the candidates the declared resolver already resolves,
        on both substrates — otherwise one of the two is enumerating a different population."""
        audit, rede = pair
        already = rede["candidate_labels"] - audit["depth_incremental"]["n_net_new_labels_offered"]
        assert (rede["candidates_landing_on_depth_legs"]
                - audit["depth_incremental"]["n_net_new_landing_on_depth_legs"]) == already
        assert (rede["candidates_landing_on_price_legs"]
                - audit["sports_pairs_incremental"]["n_net_new_landing_on_price_legs"]) == already

    def test_both_enumerate_the_same_leg_populations(self, pair):
        audit, rede = pair
        assert audit["depth_incremental"]["n_depth_legs"] == rede["n_depth_legs"]
        assert audit["sports_pairs_incremental"]["n_price_legs"] == rede["n_price_legs"]
