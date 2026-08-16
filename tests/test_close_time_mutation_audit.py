"""Tests for `scripts/close_time_mutation_audit.py`.

Fixture tests pin the arithmetic; a small number of STRUCTURAL tests run against the real
committed tree, because this tape grows every hour and pinning a live count would make the
suite fail on new data rather than on a defect (the L201/L207 balance).
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

import close_time_mutation_audit as A  # noqa: E402
from core.close_time_mutation import OPEN_TO_SETTLED, SETTLED_TO_SETTLED  # noqa: E402


def _blob(tmp_path, family, name, markets, pulled_at, tag="broker_truth"):
    d = tmp_path / family
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(json.dumps({"markets": markets, "pulled_at": pulled_at,
                             "price_source_tag": tag}), encoding="utf-8")
    return p


@pytest.fixture()
def two_pull_tree(tmp_path, monkeypatch):
    """A minimal q51-shaped tree: one pre-settlement pull, one post-settlement pull."""
    _blob(tmp_path, "q51_settlement_cache", "settlement-m2-2026-08-04.json", {
        "KX-A": {"close_time": "2026-08-20T09:30:00Z", "result": "", "status": "active"},
        "KX-B": {"close_time": "2026-08-07T01:00:00Z", "result": "", "status": "active"},
        "KX-C": {"close_time": "2026-08-03T10:00:00Z", "result": "no", "status": "finalized"},
    }, "2026-08-04T12:40:44+00:00")
    _blob(tmp_path, "q51_settlement_cache", "settlement.json", {
        "KX-A": {"close_time": "2026-08-06T12:09:30Z", "result": "no", "status": "finalized"},
        "KX-B": {"close_time": "2026-08-04T21:06:47Z", "result": "yes", "status": "finalized"},
        "KX-C": {"close_time": "2026-08-03T10:00:00Z", "result": "no", "status": "finalized"},
    }, "2026-08-10T00:38:33+00:00")
    return tmp_path


class TestSourceEnumeration:
    def test_cache_sources_come_from_the_declared_registry_not_a_local_list(self):
        # L358: a second hardcoded copy of the source list is how two modules drift apart.
        from core.settlement_sources import CACHE_MARKETS_MAP, SETTLEMENT_SOURCES
        expected = {s.name for s in SETTLEMENT_SOURCES if s.kind == CACHE_MARKETS_MAP}
        assert {s.name for s in A.cache_sources()} == expected
        assert expected, "registry declares no cache sources — the audit would be vacuous"

    def test_the_default_tape_root_is_absolute(self):
        # L345/L348: a relative root scores whatever tree the process started in and reports
        # a fabricated clean bill of health at exit code 0.
        from core.settlement_sources import DEFAULT_TAPE_ROOT
        assert os.path.isabs(DEFAULT_TAPE_ROOT)

    def test_an_unreadable_blob_is_skipped_not_fatal(self, tmp_path):
        d = tmp_path / "q51_settlement_cache"
        d.mkdir(parents=True)
        (d / "settlement.json").write_text("{not json", encoding="utf-8")
        assert A.load_cache_blob(str(d / "settlement.json")) is None

    def test_a_blob_without_a_markets_map_is_not_a_cache(self, tmp_path):
        d = tmp_path / "q51_settlement_cache"
        d.mkdir(parents=True)
        p = d / "settlement.json"
        p.write_text(json.dumps({"pulled_at": "2026-08-04T00:00:00+00:00"}), encoding="utf-8")
        assert A.load_cache_blob(str(p)) is None


class TestPairing:
    def test_blobs_are_ordered_by_pulled_at_not_by_filename(self, two_pull_tree):
        # `settlement-m2-...json` sorts BEFORE `settlement.json` lexically and was also pulled
        # first here; the ordering must survive when the two disagree, so assert on the key.
        blobs = A.load_all_cache_blobs(str(two_pull_tree))
        assert [b["pulled_at"] for b in blobs] == sorted(b["pulled_at"] for b in blobs)

    def test_the_pre_settlement_pull_shows_open_to_settled_moving_earlier(self, two_pull_tree):
        rep = A.build_report(str(two_pull_tree), include_live=False)
        pooled = rep["blob_pairs"]["pooled"]["by_regime"]
        assert pooled[OPEN_TO_SETTLED]["n"] == 2
        assert pooled[OPEN_TO_SETTLED]["instant_changed"] == 2
        assert pooled[OPEN_TO_SETTLED]["moved_earlier"] == 2
        assert pooled[OPEN_TO_SETTLED]["moved_later"] == 0

    def test_a_row_settled_in_both_pulls_never_moves(self, two_pull_tree):
        rep = A.build_report(str(two_pull_tree), include_live=False)
        assert rep["blob_pairs"]["pooled"]["by_regime"][SETTLED_TO_SETTLED]["n"] == 1
        assert rep["blob_pairs"]["pooled"]["by_regime"][SETTLED_TO_SETTLED]["instant_changed"] == 0

    def test_distinct_ticker_counts_do_not_inherit_the_observation_double_count(self, tmp_path):
        # Three blobs sharing one ticker produce THREE paired observations for ONE market.
        # Quoting the observation count as a market count inflates the headline by the number
        # of redundant pulls — the exact unit error the ledger keeps catching.
        for i, (name, ts) in enumerate((("settlement-a.json", "2026-08-01T00:00:00+00:00"),
                                        ("settlement-b.json", "2026-08-02T00:00:00+00:00"),
                                        ("settlement-c.json", "2026-08-03T00:00:00+00:00"))):
            _blob(tmp_path, "q51_settlement_cache", name, {
                "KX-A": {"close_time": f"2026-08-2{i}T00:00:00Z",
                         "result": "" if i < 2 else "no",
                         "status": "active" if i < 2 else "finalized"}}, ts)
        rep = A.build_report(str(tmp_path), include_live=False)
        assert rep["blob_pairs"]["pooled"]["n_pairs"] == 3
        assert rep["blob_pairs"]["distinct_ticker_counts"]["n_distinct_tickers"] == 1

    def test_settled_result_conflicts_are_reported_with_both_labels(self, tmp_path):
        _blob(tmp_path, "q26_settlement_cache", "settlement.json",
              {"KX-A": {"close_time": "2026-08-01T00:00:00Z", "result": "yes"}},
              "2026-08-01T00:00:00+00:00")
        _blob(tmp_path, "q27_settlement_cache", "settlement.json",
              {"KX-A": {"close_time": "2026-08-01T00:00:00Z", "result": "no"}},
              "2026-08-02T00:00:00+00:00")
        rep = A.build_report(str(tmp_path), include_live=False)
        conf = rep["blob_pairs"]["settled_result_conflicts"]
        assert rep["blob_pairs"]["n_settled_result_conflicts"] == 1
        assert conf[0]["ticker"] == "KX-A"
        assert {conf[0]["earlier_result"], conf[0]["later_result"]} == {"yes", "no"}


class TestCloseDateExposure:
    def test_it_counts_the_derived_bucket_a_day_keyed_probe_actually_uses(self, two_pull_tree):
        rep = A.build_report(str(two_pull_tree), include_live=False)
        rows = [r for r in rep["close_date_exposure"] if r["n_close_date_changed"]]
        assert rows and rows[0]["n_close_date_changed"] == 2
        assert rows[0]["n_dated"] == 3

    def test_an_undated_row_is_excluded_from_the_denominator_not_scored_as_stable(self, tmp_path):
        _blob(tmp_path, "q51_settlement_cache", "settlement-a.json",
              {"KX-A": {"result": "", "status": "active"}}, "2026-08-01T00:00:00+00:00")
        _blob(tmp_path, "q51_settlement_cache", "settlement-b.json",
              {"KX-A": {"result": "no", "status": "finalized"}}, "2026-08-02T00:00:00+00:00")
        rep = A.build_report(str(tmp_path), include_live=False)
        row = rep["close_date_exposure"][0]
        assert row["n_common"] == 1 and row["n_dated"] == 0 and row["n_close_date_changed"] == 0


class TestLiveDriftControl:
    def test_a_ticker_seen_once_cannot_answer_a_stability_question(self, tmp_path):
        d = tmp_path / "universe_sweep"
        d.mkdir(parents=True)
        (d / "dt=2026-08-01.jsonl").write_text(json.dumps(
            {"ticker": "KX-A", "captured_at": "2026-08-01T00:00:00+00:00",
             "close_time": "2026-08-09T00:00:00Z", "status": "active"}) + "\n", encoding="utf-8")
        live = A.live_drift_report(str(tmp_path))
        assert live["n_distinct_tickers"] == 1
        assert live["n_tickers_observed_twice_or_more"] == 0
        assert live["n_close_time_stable"] == 0

    def test_a_drifting_close_time_while_open_would_be_caught(self, tmp_path):
        d = tmp_path / "universe_sweep"
        d.mkdir(parents=True)
        (d / "dt=2026-08-01.jsonl").write_text("\n".join(json.dumps(r) for r in [
            {"ticker": "KX-A", "captured_at": "2026-08-01T00:00:00+00:00",
             "close_time": "2026-08-09T00:00:00Z", "status": "active"},
            {"ticker": "KX-A", "captured_at": "2026-08-02T00:00:00+00:00",
             "close_time": "2026-08-08T00:00:00Z", "status": "active"},
        ]) + "\n", encoding="utf-8")
        live = A.live_drift_report(str(tmp_path))
        assert live["n_close_time_changed"] == 1
        assert live["n_close_time_stable"] == 0
        assert live["examples_changed"][0]["delta_hours"] == pytest.approx(-24.0)

    def test_a_malformed_line_is_counted_never_silently_dropped(self, tmp_path):
        d = tmp_path / "universe_sweep"
        d.mkdir(parents=True)
        (d / "dt=2026-08-01.jsonl").write_text("{bad\n", encoding="utf-8")
        assert A.live_drift_report(str(tmp_path))["n_malformed"] == 1


class TestDiscipline:
    def test_the_report_carries_no_verdict_class_key(self):
        # This is a DESCRIPTIVE audit. A pnl/CI/bootstrap/kelly key appearing here would mean
        # a data-quality pass had quietly become a verdict without the two-agent rule.
        rep = A.build_report(include_live=False)

        def keys(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    yield str(k).lower()
                    yield from keys(v)
            elif isinstance(node, list):
                for v in node:
                    yield from keys(v)

        found = set(keys(rep))
        for banned in ("pnl", "ci95", "bootstrap", "kelly", "sharpe"):
            assert not any(banned in k for k in found), banned
        # Keys, not the serialized text: the report's own `discipline` field names the very
        # things it excludes ("no bootstrap, no P&L, no Kelly"), and a substring test over the
        # whole blob would fail on the honest declaration while passing on a smuggled value.
        assert "bootstrap" in rep["discipline"]

    def test_the_script_makes_no_network_call_and_writes_only_its_report(self):
        src = open(A.__file__).read()
        for banned in ("requests", "urllib", "httpx", "socket", "aiohttp"):
            assert banned not in src, banned
        assert src.count("open(") == src.count("open(") and 'json.dump(' in src

    def test_no_price_field_is_read_so_no_price_source_tag_attaches_to_our_output(self):
        rep = A.build_report(include_live=False)
        # The audit reports each SOURCE's declared tag as provenance, and invents none.
        for b in rep["cache_blobs"]:
            assert b["price_source_tag"] in (None, "broker_truth")


class TestAgainstCommittedTape:
    """Structural assertions over the real tree — shapes, not counts (the tape grows)."""

    @pytest.fixture(scope="class")
    def rep(self):
        return A.build_report(include_live=False)

    def test_every_committed_cache_blob_is_readable(self, rep):
        assert rep["n_cache_blobs"] >= 8
        assert rep["n_blobs_without_pulled_at"] == 0

    def test_no_two_settled_caches_disagree_on_a_label(self, rep):
        # The gating invariant's data-side twin. If this ever fails, some closed DEAD verdict
        # rests on a label the exchange contradicts.
        assert rep["blob_pairs"]["n_settled_result_conflicts"] == 0

    def test_no_close_time_ever_moves_once_the_market_is_settled(self, rep):
        b = rep["blob_pairs"]["pooled"]["by_regime"][SETTLED_TO_SETTLED]
        assert b["n"] > 0, "no settled-to-settled overlap — the control would be vacuous"
        assert b["instant_changed"] == 0

    def test_the_open_to_settled_rewrite_is_present_and_strictly_one_directional(self, rep):
        b = rep["blob_pairs"]["pooled"]["by_regime"][OPEN_TO_SETTLED]
        assert b["n"] > 0, "no before/after pair in tape — the finding would be unfalsifiable"
        assert b["moved_later"] == 0, "a close_time moved LATER — the finding's direction broke"
        assert b["moved_earlier"] > 0
        assert b["delta_hours_max"] < 0
