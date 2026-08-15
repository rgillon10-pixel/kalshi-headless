"""Unit + real-tape acceptance tests for `scripts/settlement_source_recall_audit.py`.

Real-tape assertions are DIRECTIONS and FLOORS, never frozen counts (L320/L191): the tape is
append-only and still growing, so a test that memorised today's number would fail tomorrow for
no reason and would teach a future run to loosen it.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import settlement_source_recall_audit as A  # noqa: E402


def _write(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


class TestEventUnit:
    def test_strips_the_final_leaf_segment(self):
        assert A.event_unit("KXWCGAME-26JUL02SUIDZA-SUI") == "KXWCGAME-26JUL02SUIDZA"

    def test_a_ticker_with_no_leaf_is_returned_unchanged(self):
        assert A.event_unit("SOLO") == "SOLO"


class TestClassification:
    def _scan(self, **kw):
        base = dict(n_binary_labeled_tickers=0, n_schema_only_result_nodes=0,
                    n_terminal_status_nodes=0)
        base.update(kw)
        return base

    def test_declared_wins_over_everything(self):
        assert A.classify("crypto_hourly", self._scan(n_binary_labeled_tickers=9),
                          ["crypto_hourly"]) == "declared"

    def test_populated_undeclared_family_is_the_gap_class(self):
        assert A.classify("sports_history", self._scan(n_binary_labeled_tickers=1),
                          ["crypto_hourly"]) == "undeclared_populated"

    def test_field_present_but_never_populated_is_schema_only(self):
        assert A.classify("sports_pairs", self._scan(n_schema_only_result_nodes=5),
                          []) == "undeclared_schema_only"

    def test_no_evidence_at_all(self):
        assert A.classify("orderbook_depth", self._scan(), []) == "no_outcome_field"


class TestScanFamily:
    def test_counts_lines_even_for_lines_the_prefilter_skips(self, tmp_path):
        """n_lines must be a TRUE line count — the prefilter is a decode saver, never a
        denominator shrinker."""
        d = tmp_path / "fam"
        _write(str(d / "dt=2026-01-01.jsonl"), [
            {"ticker": "A-B-C", "yes_bid": 1},          # prefilter skips
            {"ticker": "A-B-D", "result": "yes"},       # decoded
        ])
        sc = A.scan_family("fam", str(d))
        assert sc["n_lines"] == 2 and sc["n_decoded"] == 1
        assert sc["n_binary_labeled_tickers"] == 1

    def test_malformed_line_is_counted_not_crashed_on(self, tmp_path):
        d = tmp_path / "fam"
        os.makedirs(d)
        with open(d / "x.jsonl", "w") as fh:
            fh.write('{"ticker": "A-B-C", "result": "yes"}\n')
            fh.write('{"ticker": broken "result"}\n')
        sc = A.scan_family("fam", str(d))
        assert sc["n_malformed"] == 1 and sc["n_binary_labeled_tickers"] == 1

    def test_a_ticker_labeled_both_ways_is_reported_as_a_conflict_not_silently_picked(self, tmp_path):
        d = tmp_path / "fam"
        _write(str(d / "a.jsonl"), [{"ticker": "A-B-C", "result": "yes"},
                                    {"ticker": "A-B-C", "result": "no"}])
        sc = A.scan_family("fam", str(d))
        assert sc["n_conflicting_tickers"] == 1
        assert sc["n_binary_labeled_tickers"] == 1     # still counted as a labeled ticker
        assert "A-B-C" not in sc["_labels"]            # but never usable as a label

    def test_whole_document_json_files_are_one_record(self, tmp_path):
        d = tmp_path / "fam"
        os.makedirs(d)
        with open(d / "cache.json", "w") as fh:
            json.dump({"KXBTC-26JUL1012-B53250": {"result": "no"}}, fh)
        sc = A.scan_family("fam", str(d))
        assert sc["n_binary_labeled_tickers"] == 1


class TestAuditOnASyntheticTree:
    def _tree(self, tmp_path):
        root = tmp_path / "tape"
        _write(str(root / "settlement_ledger" / "dt=2026-01-01.jsonl"),
               [{"ticker": "KXGAME-D1-AAA", "result": "yes"}])
        _write(str(root / "sports_history" / "dt=2026-01-01.jsonl"),
               [{"outcomes": [{"ticker": "KXGAME-D2-BBB", "result": "no"},
                              {"ticker": "KXGAME-D1-AAA", "result": "yes"}]}])
        _write(str(root / "orderbook_depth" / "dt=2026-01-01.jsonl"),
               [{"ticker": "KXGAME-D2-BBB"}, {"ticker": "KXGAME-D2-CCC"}])
        return root

    def test_verdict_names_the_gap_and_the_yield_splits_overlap_from_net_new(self, tmp_path, monkeypatch):
        root = self._tree(tmp_path)
        monkeypatch.chdir(tmp_path)
        rep = A.audit("tape")
        assert rep["verdict"] == "REGISTRY-RECALL-GAP"
        assert "sports_history" in rep["registry_gap"]["undeclared_populated"]
        y = rep["yield"]["sports_history"]
        assert y["n_labeled_tickers"] == 2
        assert y["n_resolver_overlap"] == 1 and y["n_agree_on_overlap"] == 1
        assert y["n_net_new"] == 1

    def test_a_disagreeing_source_is_reported_as_a_defect_not_a_discovery(self, tmp_path, monkeypatch):
        root = self._tree(tmp_path)
        _write(str(root / "sports_history" / "dt=2026-01-02.jsonl"),
               [{"outcomes": [{"ticker": "KXGAME-D1-AAA", "result": "no"}]}])
        monkeypatch.chdir(tmp_path)
        rep = A.audit("tape")
        # AAA now carries yes AND no in the undeclared family -> conflict, never a label
        assert rep["family_scan"]["sports_history"]["n_conflicting_tickers"] == 1

    def test_net_new_that_touches_no_depth_leg_is_worth_zero_and_says_so(self, tmp_path, monkeypatch):
        root = tmp_path / "tape"
        _write(str(root / "sports_history" / "a.jsonl"),
               [{"ticker": "KXGAME-ZZ-QQQ", "result": "yes"}])
        _write(str(root / "orderbook_depth" / "a.jsonl"), [{"ticker": "KXOTHER-YY-RRR"}])
        monkeypatch.chdir(tmp_path)
        rep = A.audit("tape")
        d = rep["depth_incremental"]
        assert d["n_net_new_labels_offered"] == 1
        assert d["n_net_new_landing_on_depth_legs"] == 0
        assert d["n_depth_units_newly_fully_labeled"] == 0

    def test_a_derived_artefact_family_is_reported_but_never_offered_as_a_label_source(self, tmp_path, monkeypatch):
        root = tmp_path / "tape"
        _write(str(root / "sports_clv_s7" / "trades.jsonl"),
               [{"ticker": "KXGAME-D9-ZZZ", "result": "yes"}])
        _write(str(root / "orderbook_depth" / "a.jsonl"), [{"ticker": "KXGAME-D9-ZZZ"}])
        monkeypatch.chdir(tmp_path)
        rep = A.audit("tape")
        assert rep["yield"]["sports_clv_s7"]["derived_artefact"] is True
        assert rep["depth_incremental"]["n_net_new_labels_offered"] == 0

    def test_partially_labeled_unit_never_counts_as_newly_full(self, tmp_path, monkeypatch):
        root = tmp_path / "tape"
        _write(str(root / "sports_history" / "a.jsonl"),
               [{"ticker": "KXGAME-D2-BBB", "result": "yes"}])
        _write(str(root / "orderbook_depth" / "a.jsonl"),
               [{"ticker": "KXGAME-D2-BBB"}, {"ticker": "KXGAME-D2-CCC"}])
        monkeypatch.chdir(tmp_path)
        rep = A.audit("tape")
        assert rep["depth_incremental"]["n_net_new_landing_on_depth_legs"] == 1
        assert rep["depth_incremental"]["n_depth_units_newly_fully_labeled"] == 0


class TestDisciplineIsStructural:
    def test_report_carries_no_pnl_ci_bootstrap_or_kelly_key(self, tmp_path, monkeypatch):
        root = tmp_path / "tape"
        _write(str(root / "sports_history" / "a.jsonl"), [{"ticker": "A-B-C", "result": "yes"}])
        monkeypatch.chdir(tmp_path)
        blob = json.dumps(A.audit("tape")).lower()
        for banned in ("pnl", "ci95", "bootstrap", "kelly", "edge_after_fee"):
            assert banned not in blob, banned

    def test_verdict_caveat_forbids_quoting_net_new_without_the_incremental_block(self, tmp_path, monkeypatch):
        root = tmp_path / "tape"
        _write(str(root / "sports_history" / "a.jsonl"), [{"ticker": "A-B-C", "result": "yes"}])
        monkeypatch.chdir(tmp_path)
        cav = A.audit("tape")["verdict_caveat"]
        assert "recall limit" in cav and "depth_incremental" in cav

    def test_module_makes_no_network_call(self):
        src = open(A.__file__).read()
        for banned in ("requests", "urllib", "httpx", "socket", "aiohttp"):
            assert banned not in src, banned


@pytest.mark.skipif(not os.path.isdir("tape/orderbook_depth"), reason="needs committed tape")
class TestRealTapeAcceptance:
    """Directions and floors only — never a frozen count."""

    @pytest.fixture(scope="class")
    @classmethod
    def rep(cls):
        return A.audit("tape")

    def test_the_declared_registry_is_reported_in_full(self, rep):
        from core.settlement_sources import declared_source_names
        assert set(rep["registry_gap"]["declared"]) == set(declared_source_names())

    def test_the_recall_gap_is_real_on_the_committed_tree(self, rep):
        """Non-vacuity: if this ever stops firing because the families got DECLARED, the
        assertion below tells the next run exactly why."""
        gap = rep["registry_gap"]["undeclared_populated"]
        from core.settlement_sources import declared_source_names
        declared = set(declared_source_names())
        assert "sports_history" in gap or "sports_history" in declared

    def test_sports_pairs_is_schema_only_the_largest_sports_family_never_observes_a_result(self, rep):
        sc = rep["family_scan"]["sports_pairs"]
        assert sc["n_binary_labeled_tickers"] == 0
        assert sc["n_schema_only_result_nodes"] >= 30000

    def test_universe_sweep_observes_closed_markets_but_never_a_settled_one(self, rep):
        sc = rep["family_scan"]["universe_sweep"]
        assert sc["n_closed_not_settled_nodes"] >= 1000
        assert sc["n_terminal_status_nodes"] == 0
        assert sc["n_binary_labeled_tickers"] == 0

    def test_no_malformed_lines_anywhere_in_the_committed_tree(self, rep):
        assert sum(v["n_malformed"] for v in rep["family_scan"].values()) == 0

    def test_where_an_undeclared_source_overlaps_broker_truth_it_agrees(self, rep):
        """A source that disagrees with the declared registry is a DEFECT, not a discovery."""
        for fam, y in rep["yield"].items():
            if y["n_resolver_overlap"]:
                assert y["n_disagree_on_overlap"] == 0, fam

    def test_the_net_new_labels_buy_almost_nothing_on_either_fill_substrate(self, rep):
        """The finding's headline, pinned as a DIRECTION: the recall gap is real and its cash
        value on the substrates a probe can score is a rounding error. Floors, not equalities."""
        d, sp = rep["depth_incremental"], rep["sports_pairs_incremental"]
        assert d["n_net_new_labels_offered"] >= 100
        assert d["n_net_new_landing_on_depth_legs"] * 20 < d["n_net_new_labels_offered"]
        assert d["n_depth_units_newly_fully_labeled"] * 100 < d["n_depth_units"]
        assert sp["n_net_new_landing_on_price_legs"] * 100 < sp["n_price_legs"]
