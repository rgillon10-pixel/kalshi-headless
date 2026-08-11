"""Offline tests for `scripts/q56_s81_settlement_backfill.py` (Q56 / S81 settlement backfill).

Four jobs:

  1. the SELECTION RULE is exhaustive and outcome-blind — the property that makes a backfill
     incapable of biasing a sealed probe's population;
  2. HONEST COMPLETENESS — a failed fetch lowers completeness and leaves the ticker absent;
     it is never written as a null result and a partial pull never reports as a whole one;
  3. IDEMPOTENT / ADDITIVE merge — a re-run never truncates, and a stored binary result is
     never downgraded by a later weaker read;
  4. VERBATIM caching (L52) + `broker_truth` provenance + the artifact being readable by the
     real `core.settlement_sources` registry through its declared family.

Every test is offline: the fetcher is injected, so no test in this module can touch a network,
a credential or an order path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.settlement_sources import (  # noqa: E402
    CACHE_MARKETS_MAP,
    MARKET_RESULT,
    SETTLEMENT_SOURCES,
    declared_source_names,
    iter_source_results,
    resolve_market_results,
)
from scripts import q56_s81_settlement_backfill as B  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _market(result="no", status="finalized", ticker="KXBTC-T-B1"):
    return {"result": result, "status": status, "close_time": "2026-07-05T16:00:00Z",
            "event_ticker": ticker.rsplit("-", 1)[0], "volume": 123, "yes_ask": 44}


def _fetcher(table, fail=()):
    calls = []

    def fetch(ticker):
        calls.append(ticker)
        if ticker in fail:
            raise ConnectionError("boom")
        return table[ticker]

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


# --------------------------------------------------------------------------- #
# 1. the selection rule
# --------------------------------------------------------------------------- #
class TestSelectionRule:
    def test_the_rule_is_declared_in_the_module_and_written_into_the_artifact(self, tmp_path):
        assert "EXHAUSTIVE" in B.SELECTION_RULE and "outcome-blind" in B.SELECTION_RULE
        payload = B.backfill(["A"], _fetcher({"A": _market()}), tmp_path / "s.json")
        assert payload["selection_rule"] == B.SELECTION_RULE

    def test_every_requested_ticker_is_attempted_in_sorted_order(self, tmp_path):
        table = {t: _market() for t in ("C", "A", "B")}
        fetch = _fetcher(table)
        B.backfill(["C", "A", "B"], fetch, tmp_path / "s.json")
        assert fetch.calls == ["A", "B", "C"]

    def test_a_fetched_result_can_never_shorten_the_attempt_list(self, tmp_path):
        """No early stop may depend on what came back — the whole point of the rule."""
        table = {"A": _market(result="yes"), "B": _market(result="scalar"),
                 "C": _market(result="", status="active")}
        fetch = _fetcher(table)
        B.backfill(["A", "B", "C"], fetch, tmp_path / "s.json")
        assert fetch.calls == ["A", "B", "C"]

    def test_the_cap_truncates_the_sorted_prefix_and_says_so(self, tmp_path):
        table = {t: _market() for t in ("A", "B", "C")}
        fetch = _fetcher(table)
        payload = B.backfill(["A", "B", "C"], fetch, tmp_path / "s.json", max_tickers=2)
        assert fetch.calls == ["A", "B"]
        assert payload["completeness"]["cap_bound"] is True
        assert payload["completeness"]["n_requested"] == 3
        assert payload["completeness"]["n_attempted"] == 2

    def test_uncapped_runs_report_cap_bound_false(self, tmp_path):
        payload = B.backfill(["A"], _fetcher({"A": _market()}), tmp_path / "s.json")
        assert payload["completeness"]["cap_bound"] is False

    def test_selection_is_computed_from_the_sealed_probes_outcome_blind_path_only(self):
        """`unjoinable_leg_tickers` may reach the probe's candidate/membership functions and
        nothing that reads a settlement direction."""
        src = (REPO / "scripts" / "q56_s81_settlement_backfill.py").read_text()
        for banned in ("outcome_map", "score_rows", "verdict_block", "binary_outcome"):
            assert f"PROBE.{banned}" not in src, banned


# --------------------------------------------------------------------------- #
# 2. honest completeness
# --------------------------------------------------------------------------- #
class TestCompleteness:
    def test_a_failed_fetch_lowers_completeness_and_writes_no_row(self, tmp_path):
        table = {"A": _market(), "B": _market()}
        payload = B.backfill(["A", "B"], _fetcher(table, fail={"B"}), tmp_path / "s.json")
        comp = payload["completeness"]
        assert comp["n_fetched"] == 1 and comp["n_failed"] == 1
        assert comp["completeness"] == 0.5
        assert comp["errors"] == {"ConnectionError": 1}
        assert "B" not in payload["markets"]          # absent, NOT a null-result row
        assert payload["markets"]["A"]["result"] == "no"

    def test_a_total_failure_is_reported_as_zero_not_as_success(self, tmp_path):
        payload = B.backfill(["A"], _fetcher({"A": _market()}, fail={"A"}),
                             tmp_path / "s.json")
        assert payload["completeness"]["completeness"] == 0.0
        assert payload["markets"] == {}

    def test_a_non_mapping_response_is_an_error_not_a_row(self, tmp_path):
        payload = B.backfill(["A"], lambda t: None, tmp_path / "s.json")
        assert payload["completeness"]["errors"] == {"NonMappingResponse": 1}
        assert payload["markets"] == {}

    def test_classification_counts_binary_scalar_and_listed_separately(self, tmp_path):
        table = {"A": _market(result="yes"), "B": _market(result="scalar"),
                 "C": _market(result="", status="active")}
        payload = B.backfill(["A", "B", "C"], _fetcher(table), tmp_path / "s.json")
        comp = payload["completeness"]
        assert (comp["n_binary"], comp["n_non_binary"], comp["n_listed_unsettled"]) == (1, 1, 1)


# --------------------------------------------------------------------------- #
# 3. idempotent / additive
# --------------------------------------------------------------------------- #
class TestMerge:
    def test_rerunning_is_idempotent(self, tmp_path):
        path = tmp_path / "s.json"
        table = {"A": _market()}
        first = B.backfill(["A"], _fetcher(table), path)
        second = B.backfill(["A"], _fetcher(table), path)
        assert first["markets"] == second["markets"]
        assert second["completeness"]["n_markets_before"] == 1

    def test_a_second_pull_adds_rather_than_truncates(self, tmp_path):
        path = tmp_path / "s.json"
        B.backfill(["A"], _fetcher({"A": _market()}), path)
        payload = B.backfill(["B"], _fetcher({"B": _market(result="yes")}), path)
        assert set(payload["markets"]) == {"A", "B"}

    def test_a_stored_binary_result_is_never_downgraded(self, tmp_path):
        path = tmp_path / "s.json"
        B.backfill(["A"], _fetcher({"A": _market(result="yes")}), path)
        payload = B.backfill(["A"], _fetcher({"A": _market(result="", status="active")}), path)
        assert payload["markets"]["A"]["result"] == "yes"
        assert payload["markets"]["A"]["status"] == "finalized"

    def test_an_unsettled_row_is_upgraded_when_the_result_lands(self, tmp_path):
        path = tmp_path / "s.json"
        B.backfill(["A"], _fetcher({"A": _market(result="", status="active")}), path)
        payload = B.backfill(["A"], _fetcher({"A": _market(result="no")}), path)
        assert payload["markets"]["A"]["result"] == "no"

    def test_a_corrupt_existing_artifact_is_not_fatal(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text("{not json")
        payload = B.backfill(["A"], _fetcher({"A": _market()}), path)
        assert payload["markets"]["A"]["result"] == "no"


# --------------------------------------------------------------------------- #
# 4. verbatim caching, provenance, registry readability
# --------------------------------------------------------------------------- #
class TestArtifact:
    def test_results_are_kept_verbatim_including_scalar(self, tmp_path):
        payload = B.backfill(["A"], _fetcher({"A": _market(result="scalar")}),
                             tmp_path / "s.json")
        assert payload["markets"]["A"]["result"] == "scalar"

    def test_only_the_declared_fields_are_persisted(self, tmp_path):
        payload = B.backfill(["A"], _fetcher({"A": _market()}), tmp_path / "s.json")
        assert set(payload["markets"]["A"]) == set(B.KEPT_FIELDS)

    def test_the_artifact_is_broker_truth(self, tmp_path):
        payload = B.backfill(["A"], _fetcher({"A": _market()}), tmp_path / "s.json")
        assert payload["price_source_tag"] == "broker_truth"
        assert payload["schema_version"] == B.SCHEMA_VERSION

    def test_the_registry_declares_this_family_with_the_reader_kind_it_writes(self):
        assert "q56_settlement_cache" in declared_source_names()
        src = next(s for s in SETTLEMENT_SOURCES if s.name == "q56_settlement_cache")
        assert src.kind == CACHE_MARKETS_MAP
        assert src.resolves == MARKET_RESULT
        assert src.declared_tag == "broker_truth"
        assert src.reader_field is None

    def test_the_real_registry_reads_an_artifact_written_by_this_module(self, tmp_path):
        root = tmp_path / "tape"
        out = root / "q56_settlement_cache" / "settlement-s81-2026-08-11.json"
        B.backfill(["KXBTC-X-B1", "KXBTC-X-B2"],
                   _fetcher({"KXBTC-X-B1": _market(result="yes"),
                             "KXBTC-X-B2": _market(result="scalar")}), out)
        rep = resolve_market_results(["KXBTC-X-B1", "KXBTC-X-B2"], root=str(root))
        assert rep.n_resolved == 1
        assert rep.per_source_hits["q56_settlement_cache"] == 1
        assert "KXBTC-X-B2" in rep.non_binary          # scalar is NOT a settlement (L52)
        assert rep.resolved["KXBTC-X-B1"].price_source_tag == "broker_truth"

    def test_the_default_cache_path_lands_in_the_declared_family_dir(self):
        path = B.default_cache_path("2026-08-11")
        assert path.parent.name == "q56_settlement_cache"
        assert path.name == "settlement-s81-2026-08-11.json"
        src = next(s for s in SETTLEMENT_SOURCES if s.name == "q56_settlement_cache")
        import fnmatch
        assert fnmatch.fnmatch(f"q56_settlement_cache/{path.name}", src.path_glob)


# --------------------------------------------------------------------------- #
# 5. no network / no credential path in the module's import surface
# --------------------------------------------------------------------------- #
def test_module_has_no_credential_or_order_surface():
    """Checked on the AST (what the module IMPORTS and CALLS), not on prose: the docstring
    is allowed to SAY `execution/`, the code is not allowed to REACH it."""
    import ast

    tree = ast.parse((REPO / "scripts" / "q56_s81_settlement_backfill.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(m.split(".")[0] == "execution" for m in imported), imported
    assert not any("kalshi_sign" in m or "auth" in m for m in imported), imported
    called = {node.func.attr for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    for verb in ("post", "put", "delete", "patch"):
        assert verb not in called, verb
    # the one client method reached is the throttled read-only GET
    assert "get" in called


def test_dry_run_makes_no_network_call(monkeypatch, capsys):
    monkeypatch.setattr(B, "make_public_fetcher",
                        lambda *a, **k: pytest.fail("dry run must not fetch"))
    monkeypatch.setattr(B, "unjoinable_leg_tickers",
                        lambda *a, **k: (["A"], {"n_distinct_leg_tickers": 2,
                                                 "n_already_settled": 1,
                                                 "unjoinable_entry_rows_by_cell": {}}))
    assert B.main(["--dry-run"]) == 0
    assert "no network call made" in capsys.readouterr().out
