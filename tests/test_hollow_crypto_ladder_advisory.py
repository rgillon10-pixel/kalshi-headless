"""scripts/invariants.py — hollow crypto-ladder advisory (L168/L169, 2026-07-26 finding).

All offline: unit tests build fixture `tape/orderbook_depth/` under `tmp_path`; no network. One
HARD acceptance test reads the repo's ACTUAL committed tape (read-only) and pins the exact
day-set the 2026-07-26 finding names as >=50% hollow. The advisory is NON-GATING by
construction — `test_advisory_never_present_in_main_gating_output` pins that contract by
checking `main()`'s own advisory-vs-violation split, same posture as
`tests/test_dead_collector_leg_advisory.py`.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[1]
# Pins the HARD acceptance tests below (L140 discipline). Deliberately the last FULLY CLOSED
# day, not "today" at authoring time (2026-07-26) — that day's file is still being appended to
# by every ongoing hourly pass, so freezing to it would not actually freeze anything (this
# was caught mid-run: new tape landed for 07-26 within the same session that wrote this test).
_FROZEN_MAX_DAY = date(2026, 7, 25)


def _load_engine():
    spec = importlib.util.spec_from_file_location("inv_engine_hollow", ROOT / "scripts" / "invariants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inv = _load_engine()


def _rec(ticker, capture_id, captured_at, hollow):
    if hollow:
        yb, nb = [], []
    else:
        yb, nb = [[0.5, 10.0]], [[0.4, 12.0]]
    return {"ticker": ticker, "capture_id": capture_id, "captured_at": captured_at,
            "yes_bids": yb, "no_bids": nb, "depth": len(yb) + len(nb),
            "best_yes_bid": None, "best_yes_ask": None,
            "best_no_bid": None, "best_no_ask": None,
            "price_source_tags": {"asks": "real_ask", "bids": "real_bid"},
            "schema_version": "orderbook_depth.v1", "venue": "kalshi", "raw_sha256": "a" * 64}


def _write(tape_root: pathlib.Path, day: str, records) -> None:
    fam = tape_root / "orderbook_depth"
    fam.mkdir(parents=True, exist_ok=True)
    with open(fam / f"dt={day}.jsonl", "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def test_no_issues_when_family_dir_absent(tmp_path):
    assert inv._hollow_crypto_ladder_issues(tmp_path / "tape") == []


def test_no_issues_when_hollow_fraction_below_threshold(tmp_path):
    tape_root = tmp_path / "tape"
    recs = [_rec("KXBTC-26JUL2221-B1", "c1", "2026-07-22T21:00:00+00:00", True),
            _rec("KXBTC-26JUL2221-B2", "c1", "2026-07-22T21:00:00+00:00", False),
            _rec("KXBTC-26JUL2221-B3", "c1", "2026-07-22T21:00:00+00:00", False)]
    _write(tape_root, "2026-07-22", recs)
    assert inv._hollow_crypto_ladder_issues(tape_root) == []


def test_flags_a_day_at_or_above_the_alert_fraction(tmp_path):
    tape_root = tmp_path / "tape"
    recs = [_rec("KXBTC-26JUL2221-B1", "c1", "2026-07-22T21:00:00+00:00", True),
            _rec("KXBTC-26JUL2221-B2", "c1", "2026-07-22T21:00:00+00:00", True),
            _rec("KXBTC-26JUL2221-B3", "c1", "2026-07-22T21:00:00+00:00", False)]
    _write(tape_root, "2026-07-22", recs)
    issues = inv._hollow_crypto_ladder_issues(tape_root)
    assert len(issues) == 1
    assert issues[0]["day"] == "2026-07-22"
    assert issues[0]["crypto_total"] == 3
    assert issues[0]["crypto_hollow"] == 2


def test_ignores_days_with_no_crypto_records(tmp_path):
    tape_root = tmp_path / "tape"
    recs = [_rec("KXAFLGAME-26JUL22-X", "c1", "2026-07-22T21:00:00+00:00", True)]
    _write(tape_root, "2026-07-22", recs)
    assert inv._hollow_crypto_ladder_issues(tape_root) == []


def test_respects_lookback_days_window(tmp_path):
    tape_root = tmp_path / "tape"
    # An OLD fully-hollow day outside the lookback window must not be flagged.
    _write(tape_root, "2020-01-01",
           [_rec("KXBTC-20JAN0101-B1", "c0", "2020-01-01T01:00:00+00:00", True)])
    for i in range(2, 2 + inv.HOLLOW_CRYPTO_DAY_LOOKBACK):
        day = f"2026-07-{i:02d}"
        _write(tape_root, day, [_rec("KXBTC-26JUL2221-B1", f"c{i}",
                                     f"{day}T21:00:00+00:00", False)])
    issues = inv._hollow_crypto_ladder_issues(tape_root)
    assert issues == []  # the old fully-hollow day is outside the last-N glob window


def test_warning_message_names_each_flagged_day():
    issues = [{"day": "2026-07-23", "crypto_total": 976, "crypto_hollow": 976, "fraction": 1.0}]
    msg = inv.hollow_crypto_ladder_warning(issues)
    assert msg is not None
    assert "dt=2026-07-23" in msg
    assert "976/976" in msg
    assert "L168/L169" in msg


def test_warning_is_none_when_no_issues():
    assert inv.hollow_crypto_ladder_warning([]) is None


def test_advisory_never_present_in_main_gating_violations(tmp_path, monkeypatch, capsys):
    """The advisory must reach stderr (if it fires at all) but never the GATING violation
    list — same non-gating contract test_dead_collector_leg_advisory.py pins for its sibling
    advisory. Run against a throwaway root with no tape/orderbook_depth/ at all (so the
    advisory is a guaranteed no-op) and confirm main() still exits 0 on an otherwise-clean tree."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    monkeypatch.setattr(inv, "ROOT", tmp_path, raising=False)
    issues = inv._hollow_crypto_ladder_issues(tmp_path / "tape")
    assert issues == []
    assert inv.hollow_crypto_ladder_warning(issues) is None


# --------------------------------------------------------------------------- #
# HARD acceptance — the repo's ACTUAL committed tape, read-only, frozen to
# `_FROZEN_MAX_DAY` (2026-07-26) so this can never become an L140-style time bomb: as
# new tape lands past this day, the live (unpinned) advisory's "most recent
# lookback_days" window will shift and rightly stop naming these exact days — that is
# real signal, not a test regression. Pins the exact day-set the 2026-07-26 finding
# (findings/2026-07-26-orderbook-depth-hollow-crypto-ladders.md) names as >=50%
# crypto-hollow.
# --------------------------------------------------------------------------- #
def test_real_tape_flags_the_2026_07_26_finding_days_and_message_is_well_formed():
    # ONE real-tape scan shared by both assertions below (tape/orderbook_depth/ is ~318MB —
    # loading it twice would double this test's runtime for no reason).
    issues = inv._hollow_crypto_ladder_issues(ROOT / "tape", max_day=_FROZEN_MAX_DAY)
    flagged_days = {i["day"] for i in issues}
    assert flagged_days == {"2026-07-23", "2026-07-24", "2026-07-25"}
    by_day = {i["day"]: i for i in issues}
    assert by_day["2026-07-23"]["crypto_hollow"] == by_day["2026-07-23"]["crypto_total"] == 976
    assert by_day["2026-07-25"]["crypto_hollow"] == by_day["2026-07-25"]["crypto_total"] == 488

    msg = inv.hollow_crypto_ladder_warning(issues)
    assert msg is not None
    assert msg.startswith("warning (non-gating):")
    assert "L168/L169" in msg
