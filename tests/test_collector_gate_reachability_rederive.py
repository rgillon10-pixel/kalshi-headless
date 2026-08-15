"""scripts/collector_gate_reachability_rederive.py — the REDUNDANCY leg for the 2026-08-15
gate-hour reachability finding.

No `Task`/subagent tool exists in this harness, so no independent `verifier` was dispatchable
(the L287/L288/L290/L291/L295/L308/L313/L325 precedent). The sanctioned fallback is a second
implementation sharing NO code with the primary, and these tests are its receipts:

  1. the hand-rolled ISO parser agrees with `core.timeutil.parse_iso_utc` on REAL committed
     timestamps (otherwise "two implementations agree" would just be one shared parser),
  2. the two implementations agree, on the real frozen slice, on every load-bearing count,
  3. the redundancy leg is honest about what it is (never called verification).

All offline, read-only. No network.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from core.timeutil import parse_iso_utc

ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


red = _load("gate_rederive", "scripts/collector_gate_reachability_rederive.py")
tgm = _load("tgm_for_rederive", "scripts/tape_gap_monitor.py")

FROZEN_FIRST, FROZEN_LAST = "dt=2026-07-26", "dt=2026-08-14"


# ── (1) the hand-rolled parser is not secretly the shared one ────────────────
def test_own_iso_parser_matches_core_timeutil_on_real_committed_timestamps():
    path = ROOT / "tape" / "sports_pairs"
    if not path.is_dir():
        pytest.skip("committed tape/sports_pairs/ not present")
    day = sorted(p for p in path.glob("dt=*.jsonl"))[-1]
    seen = 0
    with open(day, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            ca = rec.get("captured_at")
            if not isinstance(ca, str):
                continue
            assert red.iso_to_utc(ca) == parse_iso_utc(ca), ca
            seen += 1
            if seen >= 500:
                break
    assert seen > 0


@pytest.mark.parametrize("s,ok", [
    ("2026-08-14T09:54:48+00:00", True),
    ("2026-08-14T09:54:48.123456+00:00", True),
    ("2026-08-14T09:54:48Z", True),
    ("2026-08-14T09:54:48", True),
    ("not-a-date", False),
    ("", False),
    (None, False),
    (12345, False),
])
def test_own_iso_parser_refuses_rather_than_guesses(s, ok):
    out = red.iso_to_utc(s)
    assert (out is not None) is ok


def test_own_iso_parser_normalises_a_non_utc_offset():
    assert red.iso_to_utc("2026-08-14T11:54:48+02:00") == parse_iso_utc("2026-08-14T09:54:48+00:00")


# ── (2) the two implementations agree on the real frozen slice ───────────────
@pytest.fixture(scope="module")
def _both():
    tape = ROOT / "tape"
    if not (tape / "sports_pairs").is_dir():
        pytest.skip("committed tape/sports_pairs/ not present")
    r = red.rederive(tape, FROZEN_FIRST, FROZEN_LAST)
    frozen = r["frozen_window"]["days"]
    prim = {fam: tgm.gate_hour_reachability(tape, 10, days=frozen,
                                            witness_families=(fam,))
            for fam in ("sports_pairs", "crypto_hourly", "perp_tape")}
    return r, prim, frozen, tape


def test_two_independent_implementations_agree_on_the_pass_start_census(_both):
    r, prim, _frozen, _tape = _both
    for fam in ("sports_pairs", "crypto_hourly", "perp_tape"):
        assert r["witnesses"][fam]["n_pass_instants"] == prim[fam]["n_pass_instants"], fam
        assert r["witnesses"][fam]["observed_hours"] == prim[fam]["observed_hours"], fam


def test_two_independent_implementations_agree_on_every_gate_verdict(_both):
    r, _prim, frozen, tape = _both
    for const, got in r["per_gate"].items():
        p = tgm.gate_hour_reachability(tape, got["gate_hour_utc"], days=frozen, family=const)
        assert (p["verdict"] == "REACHABLE") == got["reachable"], const
        assert p["n_at_gate_hour"] == got["n_at_gate_hour"], const


def test_the_late_leg_counter_example_reproduces_independently(_both):
    """The witness-ordering trap, re-derived: the SAME frozen passes give 0 hits at 10Z off
    the first leg and >0 off `perp_tape` (leg #7, which stamps into the next clock hour)."""
    r, _prim, _frozen, _tape = _both
    assert r["witnesses"]["sports_pairs"]["observed_hours"].get("10", 0) == 0
    assert int(r["witnesses"]["perp_tape"]["observed_hours"].get("10", 0)) > 0


def test_settlement_ledger_freeze_facts_reproduce(_both):
    r, _prim, _frozen, _tape = _both
    sl = r["settlement_ledger"]
    assert sl["n_days"] == 2
    assert sl["days"] == ["dt=2026-07-17", "dt=2026-07-22"]
    assert sl["lines_per_day"] == {"dt=2026-07-17": 5605, "dt=2026-07-22": 5000}
    assert sl["n_lines"] == 10605
    # Directional so ordinary tape growth only ever makes the freeze LONGER (L341).
    assert sl["days_since_last_capture"] is not None and sl["days_since_last_capture"] >= 24


# ── (3) honesty about what a redundancy leg is ───────────────────────────────
def test_the_redundancy_leg_never_calls_itself_verification(_both):
    r, _prim, _frozen, _tape = _both
    note = r["note"]
    assert "REDUNDANCY, not verification" in note
    assert "cannot catch an error both implementations share" in note
    src = (ROOT / "scripts" / "collector_gate_reachability_rederive.py").read_text(encoding="utf-8")
    assert "tape_gap_monitor" not in src.split('"""', 2)[2], \
        "the redundancy leg must not import the implementation it is checking"
