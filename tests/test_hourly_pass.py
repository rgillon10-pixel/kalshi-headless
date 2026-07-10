"""Hourly collector entry point (Q3) — combines sports_pairs + crypto_hourly (+ the
09 UTC anomaly sweep, if scripts/anomaly_sweep.py exists), never fakes success.

sports_pairs.run / crypto_hourly.run are stubbed via injected callables so this
exercises hourly_pass's own aggregation/degradation logic offline (no network).
"""
from __future__ import annotations

from datetime import datetime, timezone

from collection import hourly_pass as hp

NOON_UTC = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
NINE_UTC = datetime(2026, 7, 10, 9, 30, 0, tzinfo=timezone.utc)


def _sports_ok(n_events=3, total_outcomes=7, n_series_errors=0):
    return lambda: {"n_events": n_events, "total_outcomes": total_outcomes,
                    "n_series_errors": n_series_errors}


def _crypto_ok(n_captured=2, total_outcomes=250, n_series_errors=0):
    return lambda: {"n_captured": n_captured, "total_outcomes": total_outcomes,
                    "n_series_errors": n_series_errors}


def _raising(label):
    def _fn():
        raise RuntimeError(f"simulated {label} failure")
    return _fn


# --------------------------------------------------------------------------- #
# happy path — both sub-passes clean, not the anomaly-sweep hour
# --------------------------------------------------------------------------- #
def test_complete_pass_aggregates_counts_and_reports_ok():
    summary = hp.run(sports_fn=_sports_ok(), crypto_fn=_crypto_ok(), now=NOON_UTC)
    assert summary["n_markets"] == 7 + 250
    assert summary["n_lines"] == 3 + 2
    assert summary["completeness_ok"] is True
    assert summary["ran_anomaly_sweep"] is False


# --------------------------------------------------------------------------- #
# never fakes success: a hard sub-pass exception degrades honestly
# --------------------------------------------------------------------------- #
def test_sports_pass_exception_recorded_not_fatal_to_crypto():
    summary = hp.run(sports_fn=_raising("sports"), crypto_fn=_crypto_ok(), now=NOON_UTC)
    assert summary["sports"]["ok"] is False
    assert "simulated sports failure" in summary["sports"]["error"]
    assert summary["crypto"]["ok"] is True
    assert summary["completeness_ok"] is False
    # crypto's real counts still contribute — a partial failure still reports what
    # actually happened, it doesn't zero out the pass that succeeded.
    assert summary["n_markets"] == 250


def test_crypto_pass_exception_recorded_not_fatal_to_sports():
    summary = hp.run(sports_fn=_sports_ok(), crypto_fn=_raising("crypto"), now=NOON_UTC)
    assert summary["crypto"]["ok"] is False
    assert summary["sports"]["ok"] is True
    assert summary["completeness_ok"] is False


def test_series_errors_inside_a_clean_pass_still_fail_completeness():
    summary = hp.run(sports_fn=_sports_ok(n_series_errors=1), crypto_fn=_crypto_ok(),
                     now=NOON_UTC)
    assert summary["sports"]["ok"] is True   # no exception...
    assert summary["completeness_ok"] is False   # ...but coverage was incomplete


# --------------------------------------------------------------------------- #
# 09 UTC anomaly sweep gate
# --------------------------------------------------------------------------- #
def test_anomaly_sweep_run_only_during_09_utc_hour():
    calls = []
    summary = hp.run(sports_fn=_sports_ok(), crypto_fn=_crypto_ok(),
                     anomaly_runner=lambda: calls.append(1) or True, now=NOON_UTC)
    assert calls == []
    assert summary["ran_anomaly_sweep"] is False
    assert summary["completeness_ok"] is True

    summary = hp.run(sports_fn=_sports_ok(), crypto_fn=_crypto_ok(),
                     anomaly_runner=lambda: calls.append(1) or True, now=NINE_UTC)
    assert calls == [1]
    assert summary["ran_anomaly_sweep"] is True
    assert summary["completeness_ok"] is True


def test_anomaly_sweep_failure_during_09_utc_hour_fails_completeness():
    summary = hp.run(sports_fn=_sports_ok(), crypto_fn=_crypto_ok(),
                     anomaly_runner=lambda: False, now=NINE_UTC)
    assert summary["anomaly_sweep_ok"] is False
    assert summary["completeness_ok"] is False


def test_default_anomaly_runner_is_ok_when_script_does_not_exist_yet():
    # scripts/anomaly_sweep.py is Q6, not yet built — its absence must not fail Q3.
    assert not hp.ANOMALY_SWEEP_SCRIPT.exists()
    assert hp._default_anomaly_runner() is True


# --------------------------------------------------------------------------- #
# one-line digest format the hourly Haiku routine's own summary line relies on
# --------------------------------------------------------------------------- #
def test_print_summary_line_format(capsys):
    hp.run(sports_fn=_sports_ok(n_events=3, total_outcomes=7),
          crypto_fn=_crypto_ok(n_captured=2, total_outcomes=250), now=NOON_UTC)
    out = capsys.readouterr().out
    assert "257 markets, 5 lines, completeness ok" in out


def test_print_summary_line_reports_fail():
    summary = hp.run(sports_fn=_raising("sports"), crypto_fn=_crypto_ok(), now=NOON_UTC)
    assert summary["completeness_ok"] is False


def test_main_exit_code_reflects_completeness(monkeypatch):
    monkeypatch.setattr(hp, "run", lambda: {"completeness_ok": True})
    assert hp.main([]) == 0
    monkeypatch.setattr(hp, "run", lambda: {"completeness_ok": False})
    assert hp.main([]) == 1
