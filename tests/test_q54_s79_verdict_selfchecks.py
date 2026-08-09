"""Offline tests for `scripts/q54_s79_verdict_selfchecks.py` (Q54 / S79 verdict self-checks).

The self-check script exists to attack the probe's own DEAD-by-CI reading, so the failure
mode that matters most here is a VACUOUS check: one that returns `ok=True` because it can
never say anything else. Every check therefore gets a test that makes it FIRE on a fixture
built to break it, alongside the passing case.

Real-tape assertions follow the marking convention of
`tests/test_q54_s79_flow_continuation_probe.py` and
`tests/test_settlement_sources.py::TestAcceptanceRealTapeS79DataGate`: skipped when the tape
is absent, and written as FLOORS / structural relations, never as pinned live-population
equalities (L320).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import q54_s79_flow_continuation_probe as Q  # noqa: E402
from scripts import q54_s79_verdict_selfchecks as S  # noqa: E402

LIVE_TRADE_DAY = REPO / "tape" / "kalshi_trades" / "dt=2026-08-03.jsonl"
_real_tape = pytest.mark.skipif(not LIVE_TRADE_DAY.exists(),
                                reason="committed trade tape day not present")


# --------------------------------------------------------------------------- #
# A. sign-boundedness (L249)
# --------------------------------------------------------------------------- #
def test_sign_bounded_check_flags_a_definitionally_one_sided_object():
    """The Q49/S68 shape: an entry gate that bounds the sign. A DEAD (or inadmissible)
    reading on such an object is an artifact of the gate, not evidence."""
    uv = {f"G{i}": [0.01 * (i + 1)] for i in range(4)}   # every observation > 0
    out = S.check_sign_bounded(uv)
    assert out["sign_bounded_objective"]["one_sided_support"] is True
    assert out["sign_bounded_objective"]["verdict_bearing"] is False
    assert out["verdict_is_artifact_of_a_bounded_object"] is True


def test_sign_bounded_check_passes_an_object_that_could_have_disagreed():
    uv = {f"G{i}": [0.5 if i % 2 else -0.5] for i in range(12)}
    out = S.check_sign_bounded(uv)
    sbo = out["sign_bounded_objective"]
    assert sbo["one_sided_support"] is False
    assert sbo["verdict_bearing"] is True
    assert sbo["n_positive"] > 0 and sbo["n_negative"] > 0
    assert out["verdict_is_artifact_of_a_bounded_object"] is False
    assert out["admissibility"]["admissible"] is True


# --------------------------------------------------------------------------- #
# B. unit integrity (L6)
# --------------------------------------------------------------------------- #
def _scored(ticker, unit, pnl=0.1, entry=0.5, won=True, tid="t"):
    from core.pricing import TAKER_FEE_RATE, fee_per_contract
    fee = fee_per_contract(entry, TAKER_FEE_RATE)
    return {"ticker": ticker, "unit": unit, "side": Q.SIDE_YES, "entry_price": entry,
            "entry_trade_id": tid, "entry_ts": 0.0, "decision_ts": 0.0,
            "price_source_tag": "broker_truth", "won": won, "fee": fee,
            "pnl": (1.0 if won else 0.0) - entry - fee}


def _ledger_root(tmp_path, rows):
    """A `settlement_ledger`-shaped jsonl source (carries the venue's own `event_ticker`)."""
    root = tmp_path / "tape"
    d = root / "settlement_ledger"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "dt=2026-08-03.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return str(root)


def _ledger_row(ticker, event_ticker, result="yes"):
    return {"ticker": ticker, "event_ticker": event_ticker, "result": result,
            "price_source_tag": "broker_truth", "close_time": "2026-08-03T00:00:00Z",
            "schema_version": "settlement_ledger.v1"}


def test_unit_integrity_agrees_with_the_venue_event_ticker(tmp_path):
    root = _ledger_root(tmp_path, [_ledger_row("KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03AB"),
                                   _ledger_row("KXAGAME-26AUG03AB-B", "KXAGAME-26AUG03AB")])
    scored = [_scored("KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03AB"),
              _scored("KXAGAME-26AUG03AB-B", "KXAGAME-26AUG03AB")]
    out = S.check_unit_integrity(scored, root=root)
    assert out["ok"] is True
    assert out["n_units"] == 1 and out["n_scored_tickers"] == 2
    # both outcome legs of one game collapse into ONE bootstrap unit (L6)
    assert out["n_units_carrying_both_outcome_legs"] == 1


def test_unit_integrity_fires_when_a_unit_key_is_itself_a_market_ticker(tmp_path):
    """The L6 failure: an outcome leg voting as its own bootstrap unit."""
    root = _ledger_root(tmp_path, [_ledger_row("KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03AB")])
    scored = [_scored("KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03AB-A")]
    out = S.check_unit_integrity(scored, root=root)
    assert out["ok"] is False
    assert out["unit_key_that_is_itself_a_market_ticker"] == ["KXAGAME-26AUG03AB-A"]


def test_unit_integrity_fires_on_a_venue_event_ticker_mismatch(tmp_path):
    """A ticker grammar the string split mis-reads: the venue's own event field disagrees."""
    root = _ledger_root(tmp_path, [_ledger_row("KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03ZZ")])
    out = S.check_unit_integrity([_scored("KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03AB")],
                                root=root)
    assert out["ok"] is False
    assert out["unit_vs_venue_event_ticker_mismatches"] == ["KXAGAME-26AUG03AB-A"]


def test_venue_event_tickers_reads_the_json_cache_shape(tmp_path):
    root = tmp_path / "tape"
    d = root / "q51_settlement_cache"
    d.mkdir(parents=True, exist_ok=True)
    (d / "settlement.json").write_text(json.dumps({
        "schema_version": "q51_settlement_cache.v1", "price_source_tag": "broker_truth",
        "day": "2026-08-03",
        "markets": {"KXAGAME-26AUG03AB-A": {"result": "yes", "status": "finalized",
                                            "close_time": None,
                                            "event_ticker": "KXAGAME-26AUG03AB"}}}),
        encoding="utf-8")
    ev = S.venue_event_tickers(["KXAGAME-26AUG03AB-A"], root=str(root))
    assert ev == {"KXAGAME-26AUG03AB-A": "KXAGAME-26AUG03AB"}


# --------------------------------------------------------------------------- #
# C. fee (L5/L18/L30)
# --------------------------------------------------------------------------- #
def test_fee_check_passes_correctly_charged_rows_and_shows_its_arithmetic():
    from core.pricing import TAKER_FEE_RATE, fee_per_contract
    scored = [_scored("T1", "G1", entry=0.27), _scored("T2", "G2", entry=0.50)]
    out = S.check_fee(scored)
    assert out["ok"] is True
    assert out["n_rows_with_a_wrong_fee"] == 0
    assert out["n_rows_violating_the_single_leg_identity"] == 0
    hand = out["hand_derivation"]
    assert hand["imported_TAKER_FEE_RATE"] == TAKER_FEE_RATE
    assert hand["agrees"] is True
    assert hand["fee_per_contract_from_core_pricing"] == pytest.approx(
        fee_per_contract(hand["entry_price"], TAKER_FEE_RATE))


def test_fee_check_fires_on_a_maker_rate_charge():
    """The L5 bug, mirrored: charging the wrong schedule must be caught, not averaged over."""
    from core.pricing import MAKER_FEE_RATE, fee_per_contract
    row = _scored("T1", "G1", entry=0.50)
    row["fee"] = fee_per_contract(0.50, MAKER_FEE_RATE)
    row["pnl"] = 1.0 - 0.50 - row["fee"]
    out = S.check_fee([row])
    assert out["ok"] is False
    assert out["n_rows_with_a_wrong_fee"] == 1


def test_fee_check_fires_when_a_second_fee_leg_is_charged():
    row = _scored("T1", "G1", entry=0.50)
    row["pnl"] -= row["fee"]          # a round trip smuggled into a hold-to-settlement probe
    out = S.check_fee([row])
    assert out["ok"] is False
    assert out["n_rows_violating_the_single_leg_identity"] == 1


# --------------------------------------------------------------------------- #
# D. price provenance
# --------------------------------------------------------------------------- #
def test_forbidden_price_tag_scan_is_not_vacuous():
    assert S.forbidden_price_tags_in({"a": {"price_source_tag": "midpoint"}}) == ["midpoint"]
    assert S.forbidden_price_tags_in({"a": [{"price_source_tag": "synthetic"}]}) == ["synthetic"]
    assert S.forbidden_price_tags_in({"a": {"price_source_tag": "broker_truth"}}) == []


def _trade_tape(tmp_path, recs):
    d = tmp_path / "trades"
    d.mkdir(exist_ok=True)
    with open(d / "dt=2026-08-03.jsonl", "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    return d


def _raw(ticker, tid, yes_price=0.5, tag="broker_truth"):
    return {"ticker": ticker, "created_time": "2026-08-03T00:00:00Z", "yes_price": yes_price,
            "no_price": round(1.0 - yes_price, 2), "taker_book_side": Q.TAKER_BUYS,
            "count": 100.0, "trade_id": tid, "price_source_tag": tag,
            "schema_version": "kalshi_trades.v1"}


def test_price_provenance_passes_when_every_entry_is_a_real_print(tmp_path):
    tape = _trade_tape(tmp_path, [_raw("KXAGAME-26AUG03AB-A", "tid-1", 0.5)])
    root = _ledger_root(tmp_path, [_ledger_row("KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03AB")])
    scored = [_scored("KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03AB", entry=0.5, tid="tid-1")]
    out = S.check_price_provenance(scored, {"price_source_tag": "broker_truth"},
                                   tape_dir=tape, root=root)
    assert out["ok"] is True
    assert out["entry_price_source_tags_on_the_raw_tape"] == ["broker_truth"]
    assert out["settlement_price_source_tags"] == ["broker_truth"]


def test_price_provenance_fires_on_an_entry_with_no_matching_executed_print(tmp_path):
    tape = _trade_tape(tmp_path, [_raw("KXAGAME-26AUG03AB-A", "tid-1", 0.5)])
    root = _ledger_root(tmp_path, [_ledger_row("KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03AB")])
    scored = [_scored("KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03AB", tid="not-on-the-tape")]
    out = S.check_price_provenance(scored, {}, tape_dir=tape, root=root)
    assert out["ok"] is False
    assert out["n_entry_prints_not_found_on_the_trade_tape"] == 1


def test_price_provenance_fires_when_the_entry_price_is_not_the_print_price(tmp_path):
    tape = _trade_tape(tmp_path, [_raw("KXAGAME-26AUG03AB-A", "tid-1", 0.5)])
    root = _ledger_root(tmp_path, [_ledger_row("KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03AB")])
    scored = [_scored("KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03AB", entry=0.42, tid="tid-1")]
    out = S.check_price_provenance(scored, {}, tape_dir=tape, root=root)
    assert out["ok"] is False
    assert out["n_entry_prices_disagreeing_with_the_tape_print"] == 1


def test_price_provenance_fires_on_a_forbidden_tag_in_the_probe_report(tmp_path):
    tape = _trade_tape(tmp_path, [_raw("KXAGAME-26AUG03AB-A", "tid-1", 0.5)])
    root = _ledger_root(tmp_path, [_ledger_row("KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03AB")])
    scored = [_scored("KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03AB", entry=0.5, tid="tid-1")]
    out = S.check_price_provenance(scored, {"price_source_tag": "real_ask"},
                                   tape_dir=tape, root=root)
    assert out["ok"] is False
    assert out["forbidden_price_tags_in_probe_report"] == ["real_ask"]


# --------------------------------------------------------------------------- #
# E. population description — descriptive, never a second verdict
# --------------------------------------------------------------------------- #
def test_population_description_is_descriptive_only():
    """No mean, no CI, no per-slice statistic may appear: a second scoring arm shipped beside
    a DEAD reading would add verdict surface without adding evidence (L41)."""
    built = {"scored": [_scored("T1", "G1"), _scored("T2", "G2")],
             "rows": [{"ticker": "T1"}, {"ticker": "T2"}],
             "pop": {"n_entry_candidates_settled": 2}}
    out = S.describe_population(built)
    assert out["n_scored"] == 2 and out["n_units"] == 2
    keys = json.dumps(out).lower()
    for token in ("\"mean", "ci95", "pnl", "bootstrap"):
        assert token not in keys


# --------------------------------------------------------------------------- #
# committed tape — floors and structural relations only (L320)
# --------------------------------------------------------------------------- #
@_real_tape
class TestAcceptanceRealTapeSelfChecks:
    @pytest.fixture(scope="class")
    def rep(self):
        return S.run()

    def test_every_self_check_passes_on_the_committed_tape(self, rep):
        assert rep["all_checks_ok"] is True

    def test_the_bootstrapped_object_is_not_sign_bounded(self, rep):
        """L249: the DEAD verdict rests on an object that COULD have come back positive."""
        sbo = rep["checks"]["A_sign_boundedness"]["sign_bounded_objective"]
        assert sbo["one_sided_support"] is False
        assert sbo["verdict_bearing"] is True
        assert sbo["inadmissibility_is_definitional"] is False
        assert sbo["n_positive"] > 0 and sbo["n_negative"] > 0
        assert rep["checks"]["A_sign_boundedness"]["admissibility"]["n_opposing_units"] >= 1

    def test_the_unit_is_the_game_on_the_real_population(self, rep):
        b = rep["checks"]["B_unit_integrity"]
        assert b["ok"] is True
        assert b["unit_vs_venue_event_ticker_mismatches"] == []
        # more scored tickers than units => at least one game's legs are pooled, not split
        assert b["n_scored_tickers"] >= b["n_units"]
        assert b["n_units_carrying_both_outcome_legs"] >= 1

    def test_exactly_one_taker_fee_leg_is_charged_on_the_real_population(self, rep):
        from core.pricing import TAKER_FEE_RATE
        f = rep["checks"]["C_fee"]
        assert f["fee_rate_used"] == TAKER_FEE_RATE
        assert f["fee_legs_pre_registered"] == 1
        assert f["n_rows_with_a_wrong_fee"] == 0
        assert f["n_rows_violating_the_single_leg_identity"] == 0

    def test_every_price_in_the_pnl_path_is_broker_truth(self, rep):
        d = rep["checks"]["D_price_provenance"]
        assert d["entry_price_source_tags_on_the_raw_tape"] == ["broker_truth"]
        assert d["settlement_price_source_tags"] == ["broker_truth"]
        assert d["n_entry_prints_not_found_on_the_trade_tape"] == 0
        assert d["forbidden_price_tags_in_probe_report"] == []

    def test_population_floors_hold(self, rep):
        e = rep["checks"]["E_population"]
        assert e["n_units"] >= 24
        assert e["minority_side_units"] >= 2
        assert e["n_scored"] >= 133
        assert e["n_entry_days"] >= 6

    def test_the_entry_population_is_not_one_instant(self, rep):
        """L251 descriptor: 24 units drawn from a single moment would not be 24 blocks."""
        c = rep["checks"]["E_population"]["entry_instant_concentration"]
        assert c["n_distinct_instants"] > 1
        assert c["single_instant"] is False
        assert c["n_units_on_top_instant"] < c["n_units"]

    def test_main_runs_without_writing(self, capsys):
        assert S.main(["--no-write"]) == 0
        assert "Q54 / S79" in capsys.readouterr().out
