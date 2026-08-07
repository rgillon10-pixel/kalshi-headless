"""Offline tests for scripts/settlement_coverage_audit.py (L300)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.settlement_coverage_audit import (build_report, main, tickers_from_jsonl)


@pytest.fixture()
def tiny_tape(tmp_path):
    root = tmp_path / "tape"
    (root / "q51_settlement_cache").mkdir(parents=True)
    (root / "q51_settlement_cache/settlement.json").write_text(json.dumps(
        {"day": "2026-08-03", "price_source_tag": "broker_truth",
         "markets": {"AAA-X": {"status": "finalized", "result": "yes"},
                     "BBB-Y": {"status": "active", "result": ""}}}))
    trades = tmp_path / "trades.jsonl"
    trades.write_text("\n".join([
        json.dumps({"ticker": "AAA-X"}),
        json.dumps({"ticker": "AAA-X"}),      # duplicate -> one distinct ticker
        json.dumps({"ticker": "BBB-Y"}),
        json.dumps({"ticker": "CCC-Z"}),
        "{malformed",
        "",
    ]) + "\n")
    return root, trades


class TestTickerExtraction:
    def test_distinct_sorted_and_malformed_skipped(self, tiny_tape):
        _root, trades = tiny_tape
        assert tickers_from_jsonl(str(trades)) == ["AAA-X", "BBB-Y", "CCC-Z"]

    def test_alternate_field_name(self, tmp_path):
        p = tmp_path / "x.jsonl"
        p.write_text(json.dumps({"event_ticker": "E1"}) + "\n")
        assert tickers_from_jsonl(str(p), "event_ticker") == ["E1"]


class TestReport:
    def test_report_names_every_source_even_the_absent_ones(self, tiny_tape):
        root, _ = tiny_tape
        rep = build_report(["AAA-X", "BBB-Y", "CCC-Z"], root=str(root))
        names = [s["name"] for s in rep["sources"]]
        assert "settlement_ledger" in names and "q51_settlement_cache" in names
        absent = [s for s in rep["sources"] if s["name"] == "settlement_ledger"][0]
        assert absent["n_files_present"] == 0 and absent["hits"] == 0

    def test_hits_are_attributed_to_the_family_that_answered(self, tiny_tape):
        root, _ = tiny_tape
        rep = build_report(["AAA-X", "BBB-Y", "CCC-Z"], root=str(root))
        assert rep["n_resolved"] == 1
        assert rep["per_source_hits"]["q51_settlement_cache"] == 1
        assert rep["n_listed_unsettled"] == 1          # BBB-Y is listed, not settled
        assert rep["unresolved"] == ["BBB-Y", "CCC-Z"]

    def test_report_carries_the_recall_limit(self, tiny_tape):
        root, _ = tiny_tape
        rep = build_report(["AAA-X"], root=str(root))
        assert "precision evidence, never recall" in rep["recall_note"]
        assert rep["embedded_result_families"]


class TestCli:
    def test_cli_writes_json_and_prints_the_summary(self, tiny_tape, tmp_path, capsys):
        root, trades = tiny_tape
        out = tmp_path / "rep.json"
        rc = main(["--tickers-from", str(trades), "--tape-root", str(root),
                   "--out", str(out)])
        assert rc == 0
        printed = capsys.readouterr().out
        assert "3 requested / 1 resolved" in printed
        assert "q51_settlement_cache" in printed
        assert json.loads(out.read_text())["n_resolved"] == 1

    def test_cli_no_write_leaves_no_file(self, tiny_tape, tmp_path, capsys):
        root, trades = tiny_tape
        out = tmp_path / "nope.json"
        assert main(["--tickers-from", str(trades), "--tape-root", str(root),
                     "--out", str(out), "--no-write"]) == 0
        assert not out.exists()

    def test_cli_accepts_explicit_tickers(self, tiny_tape, tmp_path, capsys):
        root, _ = tiny_tape
        assert main(["--tickers", "AAA-X", "--tape-root", str(root),
                     "--no-write"]) == 0
        assert "1 requested / 1 resolved" in capsys.readouterr().out

    def test_cli_requires_a_ticker_source(self, capsys):
        with pytest.raises(SystemExit):
            main(["--no-write"])

    def test_cli_flags_an_undeclared_settlement_dir(self, tiny_tape, tmp_path, capsys):
        root, trades = tiny_tape
        (root / "q99_settlement_cache").mkdir()
        main(["--tickers-from", str(trades), "--tape-root", str(root), "--no-write"])
        assert "UNDECLARED settlement-named dirs: q99_settlement_cache" in \
            capsys.readouterr().out
