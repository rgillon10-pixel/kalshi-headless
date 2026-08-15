"""scripts/collector_gate_reachability_audit.py — the per-leg gate-hour reachability table
(L123's third half) and the committed `reports/collector_gate_reachability.json` artifact.

Read-only, offline. The audit REPORTS; it never repairs — widening a live `if ts.hour == N`
gate is Ryan/VPS-side (L123 candidate (b)) and the once-per-day key already exists in open
PR #165 (L221/L246). One test pins that the script cannot quietly become a repair.

L341: no test here builds a path to the live `reports/collector_gate_reachability.json` the
script regenerates — the write path is exercised against fixture tape into `tmp_path`, and the
real-tape numbers are pinned on a FROZEN day slice in tests/test_tape_gap_monitor.py instead.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "collector_gate_reachability_audit.py"


def _load():
    spec = importlib.util.spec_from_file_location("gate_audit", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


aud = _load()


def _grid_tape(tape_root, family, days, hours, minute=54):
    fam = tape_root / family
    fam.mkdir(parents=True, exist_ok=True)
    for day in days:
        with open(fam / f"dt={day}.jsonl", "a", encoding="utf-8") as f:
            for h in hours:
                f.write(json.dumps({"capture_id": f"{day}T{h:02d}{minute:02d}",
                                    "captured_at": f"{day}T{h:02d}:{minute:02d}:00+00:00"}) + "\n")


def test_build_report_reads_gate_hours_from_the_collector_never_redeclares_them(tmp_path):
    days = [f"2026-08-{d:02d}" for d in range(1, 11)]
    _grid_tape(tmp_path, "sports_pairs", days, (0, 3, 6, 9, 12, 15, 18, 21))
    rep = aud.build_report(tape_root=tmp_path)
    assert rep["schema_version"] == "collector_gate_reachability.v1"
    # the hours come from collection/hourly_pass.py itself
    assert rep["gate_hours"]["settlement_ledger"] == 10
    assert rep["gate_hours"]["anomalies"] == 9
    assert rep["legs"]["settlement_ledger"]["verdict"] == "UNREACHABLE"
    assert rep["legs"]["anomalies"]["verdict"] == "REACHABLE"
    assert rep["unreachable_families"] == ["settlement_ledger"]
    assert rep["n_unreachable"] == 1 and rep["n_legs"] >= 4


def test_build_report_reports_the_exempt_leg_with_its_reason(tmp_path):
    days = [f"2026-08-{d:02d}" for d in range(1, 11)]
    _grid_tape(tmp_path, "sports_pairs", days, (0, 3, 6, 9, 12, 15, 18, 21))
    rep = aud.build_report(tape_root=tmp_path)
    ex = rep["exempt_legs"]["FORECAST_COLLECTOR_UTC_HOUR"]
    assert ex["gate_hour_utc"] == 11 and ex["verdict"] == "UNREACHABLE"
    assert "gitignored" in ex["exempt_reason"]
    # exempt legs are NOT counted as defects of the committed tape tree
    assert "FORECAST_COLLECTOR_UTC_HOUR" not in rep["unreachable_families"]


def test_build_report_accepts_a_frozen_day_slice(tmp_path):
    days = [f"2026-08-{d:02d}" for d in range(1, 11)]
    _grid_tape(tmp_path, "sports_pairs", days, (0, 3, 6, 9, 12, 15, 18, 21))
    _grid_tape(tmp_path, "sports_pairs", ["2026-08-20"], (10,))
    rep = aud.build_report(tape_root=tmp_path, days=[f"dt={d}" for d in days])
    assert rep["frozen_days"] == [f"dt={d}" for d in days]
    assert rep["legs"]["settlement_ledger"]["verdict"] == "UNREACHABLE"


def test_the_documented_cli_form_actually_runs(tmp_path):
    """L232: a script whose docstring cites a direct CLI form must have that form work."""
    proc = subprocess.run([sys.executable, str(SCRIPT), "--tape-root", str(tmp_path),
                           "--no-write"], capture_output=True, text=True, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "settlement_ledger" in proc.stdout


def test_the_audit_is_detection_only_and_says_so(tmp_path):
    days = [f"2026-08-{d:02d}" for d in range(1, 11)]
    _grid_tape(tmp_path, "sports_pairs", days, (0, 3, 6, 9, 12, 15, 18, 21))
    rep = aud.build_report(tape_root=tmp_path)
    disp = rep["repair_disposition"]
    assert "DETECTION ONLY" in disp and "PR #165" in disp
    src = SCRIPT.read_text(encoding="utf-8")
    # it must never write to the collector it audits
    assert "hourly_pass.py" in src            # it READS the constants
    assert "write_text" in src                # ... and writes only its own report
    body = src.split('"""', 2)[2]
    for banned in ("_UTC_HOUR =", "requests", "urllib.request", "execution"):
        assert banned not in body, banned


def test_cli_writes_a_wellformed_report_to_an_explicit_path(tmp_path):
    """The write path, exercised on fixture tape into tmp_path — never against the live
    committed artifact (L341: a test that pins a report some script regenerates goes red on
    correct data the next time the script runs)."""
    tape = tmp_path / "tape"
    days = [f"2026-08-{d:02d}" for d in range(1, 11)]
    _grid_tape(tape, "sports_pairs", days, (0, 3, 6, 9, 12, 15, 18, 21))
    out = tmp_path / "out" / "gate.json"
    assert aud.main(["--tape-root", str(tape), "--out", str(out)]) == 0
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["schema_version"] == "collector_gate_reachability.v1"
    assert rep["unreachable_families"] == ["settlement_ledger"]
    assert rep["legs"]["settlement_ledger"]["n_at_gate_hour"] == 0
    assert "DETECTION ONLY" in rep["repair_disposition"]
    # the coverage note travels WITH the number, never separated from it
    assert "perp_tape" in rep["legs"]["settlement_ledger"]["coverage_note"]
