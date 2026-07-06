"""collection.hourly_pass — sub-pass wiring, honest completeness aggregation, n_markets/
n_lines accounting from freshly-written tape, and the 09-UTC-only anomaly-sweep/econ-prints
slots. Fully offline: sports_fn/crypto_fn/polymarket_fn/anomaly_sweep_fn/econ_prints_fn are
injected stubs, no network."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from collection import hourly_pass as hp


def _write_tape(tmp_path: Path, name: str, records: list) -> str:
    path = tmp_path / name
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return str(path)


def _sports_summary(tmp_path, capture_id="cap1", n_games=2, n_complete=2, per_game_outcomes=3):
    records = [
        {"capture_id": capture_id, "expected_outcomes": per_game_outcomes}
        for _ in range(n_games)
    ]
    # a stray line from an earlier pass, must not be double-counted
    records.append({"capture_id": "some-other-pass", "expected_outcomes": 999})
    path = _write_tape(tmp_path, "sports.jsonl", records)
    return {
        "capture_id": capture_id, "n_candidate_series": 10,
        "n_games": n_games, "n_complete": n_complete, "path": path,
    }


def _crypto_summary(tmp_path, capture_id="cap2", n_symbols=2, n_complete=2, per_symbol_outcomes=188):
    records = [
        {"capture_id": capture_id, "current": {"expected_outcomes": per_symbol_outcomes}}
        for _ in range(n_symbols)
    ]
    records.append({"capture_id": "some-other-pass", "current": {"expected_outcomes": 999}})
    path = _write_tape(tmp_path, "crypto.jsonl", records)
    return {"capture_id": capture_id, "n_symbols": n_symbols, "n_complete": n_complete, "path": path}


# a zero-contribution stub: keeps existing n_lines/n_markets math untouched in tests that
# aren't exercising the polymarket sub-pass itself
_EMPTY_POLYMARKET = {"n_matched": 0, "n_kalshi_markets": 0, "completeness_ok": True}

# same role as _EMPTY_POLYMARKET, for the Q12 Fed-decision macro-pairs sub-pass
_EMPTY_POLYMARKET_MACRO = {"n_matched": 0, "n_kalshi_markets": 0, "completeness_ok": True}


def _polymarket_summary(n_matched=3, n_kalshi_markets=3, completeness_ok=True):
    return {
        "n_matched": n_matched, "n_kalshi_markets": n_kalshi_markets,
        "completeness_ok": completeness_ok,
    }


NOT_ANOMALY_HOUR = 5
ANOMALY_HOUR = hp.ANOMALY_SWEEP_UTC_HOUR

# a zero-contribution stub for the 09-UTC-only econ_prints slot, used by every test that
# fires at ANOMALY_HOUR but isn't exercising econ_prints itself
_NOT_BUILT_ECON = {"status": "not_built"}


def _ts(hour):
    return datetime(2026, 7, 3, hour, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# happy path: both sub-passes complete, outside the anomaly-sweep hour
# --------------------------------------------------------------------------- #
def test_run_all_complete_outside_anomaly_hour(tmp_path):
    sports = _sports_summary(tmp_path, n_games=2, n_complete=2, per_game_outcomes=3)
    crypto = _crypto_summary(tmp_path, n_symbols=2, n_complete=2, per_symbol_outcomes=188)

    summary = hp.run(
        sports_fn=lambda: sports, crypto_fn=lambda: crypto,
        polymarket_fn=lambda: _EMPTY_POLYMARKET,
                      polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO, now=_ts(NOT_ANOMALY_HOUR))

    assert summary["completeness_ok"] is True
    assert summary["n_lines"] == 2 + 2
    assert summary["n_markets"] == 2 * 3 + 2 * 188
    assert summary["anomaly_sweep"] is None


def test_run_prints_expected_digest_line(tmp_path, capsys):
    sports = _sports_summary(tmp_path, n_games=1, n_complete=1, per_game_outcomes=2)
    crypto = _crypto_summary(tmp_path, n_symbols=1, n_complete=1, per_symbol_outcomes=10)

    hp.run(sports_fn=lambda: sports, crypto_fn=lambda: crypto,
           polymarket_fn=lambda: _EMPTY_POLYMARKET,
                      polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO, now=_ts(NOT_ANOMALY_HOUR))

    out = capsys.readouterr().out
    assert "[hourly_pass] 12 markets, 2 lines, completeness ok" in out


# --------------------------------------------------------------------------- #
# honest completeness: a sub-pass's own incompleteness propagates
# --------------------------------------------------------------------------- #
def test_run_sports_incomplete_marks_overall_incomplete(tmp_path):
    sports = _sports_summary(tmp_path, n_games=5, n_complete=3)
    crypto = _crypto_summary(tmp_path, n_symbols=2, n_complete=2)

    summary = hp.run(
        sports_fn=lambda: sports, crypto_fn=lambda: crypto,
        polymarket_fn=lambda: _EMPTY_POLYMARKET,
                      polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO, now=_ts(NOT_ANOMALY_HOUR))

    assert summary["completeness_ok"] is False


def test_run_crypto_incomplete_marks_overall_incomplete(tmp_path):
    sports = _sports_summary(tmp_path, n_games=2, n_complete=2)
    crypto = _crypto_summary(tmp_path, n_symbols=2, n_complete=1)

    summary = hp.run(
        sports_fn=lambda: sports, crypto_fn=lambda: crypto,
        polymarket_fn=lambda: _EMPTY_POLYMARKET,
                      polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO, now=_ts(NOT_ANOMALY_HOUR))

    assert summary["completeness_ok"] is False


def test_run_polymarket_incomplete_marks_overall_incomplete(tmp_path):
    sports = _sports_summary(tmp_path, n_games=2, n_complete=2)
    crypto = _crypto_summary(tmp_path, n_symbols=2, n_complete=2)
    polymarket = _polymarket_summary(n_matched=2, n_kalshi_markets=3, completeness_ok=False)

    summary = hp.run(
        sports_fn=lambda: sports, crypto_fn=lambda: crypto,
        polymarket_fn=lambda: polymarket,
        polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO, now=_ts(NOT_ANOMALY_HOUR))

    assert summary["completeness_ok"] is False
    assert summary["n_lines"] == 2 + 2 + 2
    assert summary["n_markets"] == 2 * 3 + 2 * 188 + 2


# --------------------------------------------------------------------------- #
# fault isolation: one sub-pass raising never kills the other or the whole run
# --------------------------------------------------------------------------- #
def test_run_sports_raises_crypto_still_runs(tmp_path):
    crypto = _crypto_summary(tmp_path, n_symbols=2, n_complete=2, per_symbol_outcomes=10)

    def _boom():
        raise RuntimeError("simulated sports_pairs failure")

    summary = hp.run(sports_fn=_boom, crypto_fn=lambda: crypto,
                      polymarket_fn=lambda: _EMPTY_POLYMARKET,
                      polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO, now=_ts(NOT_ANOMALY_HOUR))

    assert summary["completeness_ok"] is False
    assert summary["sports_pairs"]["status"] == "error"
    assert "simulated sports_pairs failure" in summary["sports_pairs"]["error"]
    assert summary["crypto_hourly"]["status"] == "ok"
    assert summary["n_markets"] == 2 * 10
    assert summary["n_lines"] == 2


def test_run_crypto_raises_sports_still_runs(tmp_path):
    sports = _sports_summary(tmp_path, n_games=1, n_complete=1, per_game_outcomes=3)

    def _boom():
        raise RuntimeError("simulated crypto_hourly failure")

    summary = hp.run(sports_fn=lambda: sports, crypto_fn=_boom,
                      polymarket_fn=lambda: _EMPTY_POLYMARKET,
                      polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO, now=_ts(NOT_ANOMALY_HOUR))

    assert summary["completeness_ok"] is False
    assert summary["crypto_hourly"]["status"] == "error"
    assert summary["sports_pairs"]["status"] == "ok"
    assert summary["n_markets"] == 3
    assert summary["n_lines"] == 1


def test_run_polymarket_raises_others_still_run(tmp_path):
    sports = _sports_summary(tmp_path, n_games=1, n_complete=1, per_game_outcomes=3)
    crypto = _crypto_summary(tmp_path, n_symbols=1, n_complete=1, per_symbol_outcomes=10)

    def _boom():
        raise RuntimeError("simulated polymarket_pairs failure")

    summary = hp.run(sports_fn=lambda: sports, crypto_fn=lambda: crypto,
                      polymarket_fn=_boom,
                      polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO, now=_ts(NOT_ANOMALY_HOUR))

    assert summary["completeness_ok"] is False
    assert summary["polymarket_pairs"]["status"] == "error"
    assert "simulated polymarket_pairs failure" in summary["polymarket_pairs"]["error"]
    assert summary["sports_pairs"]["status"] == "ok"
    assert summary["crypto_hourly"]["status"] == "ok"
    assert summary["n_markets"] == 3 + 10
    assert summary["n_lines"] == 1 + 1


# --------------------------------------------------------------------------- #
# anomaly sweep: only during the 09 UTC hour, never fakes success
# --------------------------------------------------------------------------- #
def test_anomaly_sweep_not_invoked_outside_09_utc(tmp_path):
    sports = _sports_summary(tmp_path)
    crypto = _crypto_summary(tmp_path)
    calls = []

    def _sweep():
        calls.append(1)
        return {"status": "ok"}

    summary = hp.run(sports_fn=lambda: sports, crypto_fn=lambda: crypto,
                     polymarket_fn=lambda: _EMPTY_POLYMARKET,
                     polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO,
                     anomaly_sweep_fn=_sweep, now=_ts(NOT_ANOMALY_HOUR))

    assert calls == []
    assert summary["anomaly_sweep"] is None


def test_anomaly_sweep_not_built_does_not_fail_completeness(tmp_path):
    sports = _sports_summary(tmp_path)
    crypto = _crypto_summary(tmp_path)

    summary = hp.run(sports_fn=lambda: sports, crypto_fn=lambda: crypto,
                     polymarket_fn=lambda: _EMPTY_POLYMARKET,
                     polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO,
                     anomaly_sweep_fn=lambda: {"status": "not_built"},
                     econ_prints_fn=lambda: _NOT_BUILT_ECON, now=_ts(ANOMALY_HOUR))

    assert summary["completeness_ok"] is True
    assert summary["anomaly_sweep"]["result"]["status"] == "not_built"


def test_anomaly_sweep_error_marks_incomplete(tmp_path):
    sports = _sports_summary(tmp_path)
    crypto = _crypto_summary(tmp_path)

    summary = hp.run(sports_fn=lambda: sports, crypto_fn=lambda: crypto,
                     polymarket_fn=lambda: _EMPTY_POLYMARKET,
                     polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO,
                     anomaly_sweep_fn=lambda: {"status": "error", "returncode": 1},
                     econ_prints_fn=lambda: _NOT_BUILT_ECON, now=_ts(ANOMALY_HOUR))

    assert summary["completeness_ok"] is False


def test_anomaly_sweep_raising_marks_incomplete_not_crash(tmp_path):
    sports = _sports_summary(tmp_path)
    crypto = _crypto_summary(tmp_path)

    def _boom():
        raise RuntimeError("simulated anomaly sweep crash")

    summary = hp.run(sports_fn=lambda: sports, crypto_fn=lambda: crypto,
                     polymarket_fn=lambda: _EMPTY_POLYMARKET,
                     polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO,
                     anomaly_sweep_fn=_boom, econ_prints_fn=lambda: _NOT_BUILT_ECON,
                     now=_ts(ANOMALY_HOUR))

    assert summary["completeness_ok"] is False
    assert summary["anomaly_sweep"]["status"] == "error"


def test_anomaly_sweep_script_absent_reports_not_built(tmp_path, monkeypatch):
    monkeypatch.setattr(hp, "ANOMALY_SWEEP_SCRIPT", tmp_path / "does-not-exist.py")
    assert hp._run_anomaly_sweep_subprocess() == {"status": "not_built"}


# --------------------------------------------------------------------------- #
# econ_prints: only during the 09 UTC hour, never fakes success
# --------------------------------------------------------------------------- #
def test_econ_prints_not_invoked_outside_09_utc(tmp_path):
    sports = _sports_summary(tmp_path)
    crypto = _crypto_summary(tmp_path)
    calls = []

    def _econ():
        calls.append(1)
        return {"n_series": 1, "n_complete": 1}

    summary = hp.run(sports_fn=lambda: sports, crypto_fn=lambda: crypto,
                     polymarket_fn=lambda: _EMPTY_POLYMARKET,
                     polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO,
                     anomaly_sweep_fn=lambda: {"status": "not_built"},
                     econ_prints_fn=_econ, now=_ts(NOT_ANOMALY_HOUR))

    assert calls == []
    assert summary["econ_prints"] is None


def test_econ_prints_all_complete_does_not_fail_completeness(tmp_path):
    sports = _sports_summary(tmp_path)
    crypto = _crypto_summary(tmp_path)

    summary = hp.run(sports_fn=lambda: sports, crypto_fn=lambda: crypto,
                     polymarket_fn=lambda: _EMPTY_POLYMARKET,
                     polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO,
                     anomaly_sweep_fn=lambda: {"status": "not_built"},
                     econ_prints_fn=lambda: {"n_series": 5, "n_complete": 5},
                     now=_ts(ANOMALY_HOUR))

    assert summary["completeness_ok"] is True
    assert summary["econ_prints"]["result"] == {"n_series": 5, "n_complete": 5}


def test_econ_prints_partial_marks_incomplete(tmp_path):
    sports = _sports_summary(tmp_path)
    crypto = _crypto_summary(tmp_path)

    summary = hp.run(sports_fn=lambda: sports, crypto_fn=lambda: crypto,
                     polymarket_fn=lambda: _EMPTY_POLYMARKET,
                     polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO,
                     anomaly_sweep_fn=lambda: {"status": "not_built"},
                     econ_prints_fn=lambda: {"n_series": 5, "n_complete": 3},
                     now=_ts(ANOMALY_HOUR))

    assert summary["completeness_ok"] is False


def test_econ_prints_raising_marks_incomplete_not_crash(tmp_path):
    sports = _sports_summary(tmp_path)
    crypto = _crypto_summary(tmp_path)

    def _boom():
        raise RuntimeError("simulated econ_prints crash")

    summary = hp.run(sports_fn=lambda: sports, crypto_fn=lambda: crypto,
                     polymarket_fn=lambda: _EMPTY_POLYMARKET,
                     polymarket_macro_fn=lambda: _EMPTY_POLYMARKET_MACRO,
                     anomaly_sweep_fn=lambda: {"status": "not_built"},
                     econ_prints_fn=_boom, now=_ts(ANOMALY_HOUR))

    assert summary["completeness_ok"] is False
    assert summary["econ_prints"]["status"] == "error"


# --------------------------------------------------------------------------- #
# n_markets accounting helper, in isolation
# --------------------------------------------------------------------------- #
def test_sum_expected_markets_from_tape_filters_by_capture_id(tmp_path):
    path = _write_tape(tmp_path, "mixed.jsonl", [
        {"capture_id": "keep", "expected_outcomes": 3},
        {"capture_id": "keep", "expected_outcomes": 2},
        {"capture_id": "drop", "expected_outcomes": 100},
    ])
    total = hp._sum_expected_markets_from_tape(path, "keep", hp._sports_expected_outcomes)
    assert total == 5


def test_sum_expected_markets_from_tape_no_path_returns_zero():
    assert hp._sum_expected_markets_from_tape(None, "cap1", hp._sports_expected_outcomes) == 0


# --------------------------------------------------------------------------- #
# CLI wiring: --sports-limit / --crypto-symbols reach the real collectors
# --------------------------------------------------------------------------- #
def test_main_wires_sports_limit_and_crypto_symbols(monkeypatch, tmp_path):
    calls = {}

    def fake_sports_run(limit=None, odds_api_key=None, **kwargs):
        calls["sports"] = {"limit": limit, "odds_api_key": odds_api_key}
        return {"capture_id": "c", "n_candidate_series": 0, "n_games": 0, "n_complete": 0}

    def fake_crypto_run(symbols=None, **kwargs):
        calls["crypto"] = {"symbols": symbols}
        return {"capture_id": "c", "n_symbols": 0, "n_complete": 0}

    def fake_polymarket_run(**kwargs):
        return dict(_EMPTY_POLYMARKET)

    def fake_polymarket_macro_run(**kwargs):
        return dict(_EMPTY_POLYMARKET_MACRO)

    monkeypatch.setattr(hp.sports_pairs, "run", fake_sports_run)
    monkeypatch.setattr(hp.crypto_hourly, "run", fake_crypto_run)
    monkeypatch.setattr(hp.polymarket_pairs, "run", fake_polymarket_run)
    monkeypatch.setattr(hp.polymarket_pairs, "run_fed_decision", fake_polymarket_macro_run)

    rc = hp.main(["--sports-limit", "3", "--crypto-symbols", "BTC"])

    assert rc == 0
    assert calls["sports"]["limit"] == 3
    assert calls["crypto"]["symbols"] == {"BTC": "KXBTC"}


def test_main_returns_nonzero_on_incomplete_pass(monkeypatch, tmp_path):
    def fake_sports_run(**kwargs):
        return {"capture_id": "c", "n_candidate_series": 0, "n_games": 5, "n_complete": 2}

    def fake_crypto_run(**kwargs):
        return {"capture_id": "c", "n_symbols": 0, "n_complete": 0}

    def fake_polymarket_run(**kwargs):
        return dict(_EMPTY_POLYMARKET)

    def fake_polymarket_macro_run(**kwargs):
        return dict(_EMPTY_POLYMARKET_MACRO)

    monkeypatch.setattr(hp.sports_pairs, "run", fake_sports_run)
    monkeypatch.setattr(hp.crypto_hourly, "run", fake_crypto_run)
    monkeypatch.setattr(hp.polymarket_pairs, "run", fake_polymarket_run)
    monkeypatch.setattr(hp.polymarket_pairs, "run_fed_decision", fake_polymarket_macro_run)

    assert hp.main([]) == 1
