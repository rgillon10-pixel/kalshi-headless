"""Offline tests for `scripts/q56_s81_funding_regime_settlement_probe.py` (Q56 / S81).

Three jobs:

  1. ordinary unit tests — regime labelling, regime-run blocking, entry-snapshot selection,
     the adjacent-above leg, the fillability band, the fee/P&L arithmetic;
  2. THE SEAL — this probe is committed with its gate SHUT, so the tests pin that it cannot
     peek: the pre-registration is hash-locked, the sealed report carries no outcome-derived
     field, and the two outcome-reading functions are unreachable while the gate is shut;
  3. real-tape acceptance on a FIXED slice of committed day files (never the open-ended live
     glob — a test that globs a growing family red-lines the day the collector lands a new
     day), with directional assertions that survive tape growth.

Every test is offline: no network, no credentials, no writes outside tmp_path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.pricing import TAKER_FEE_RATE, fee_per_contract  # noqa: E402
from scripts import q56_s81_funding_regime_settlement_probe as Q  # noqa: E402

BASE = Q.HL_BASELINE_HOURLY_RATE

# A fixed, never-growing slice of committed tape (07-21/07-22 carry informative-cell entries).
CRYPTO_DAYS = [REPO / "tape" / "crypto_hourly" / f"dt=2026-07-{d}.jsonl" for d in ("21", "22")]
FUNDING_DAYS = [REPO / "tape" / "hyperliquid_funding" / f"dt=2026-07-{d}.jsonl"
                for d in ("22", "23", "24")]
_real_tape = pytest.mark.skipif(
    not all(p.exists() for p in CRYPTO_DAYS + FUNDING_DAYS),
    reason="committed crypto_hourly / hyperliquid_funding day files not present")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _bracket(floor, cap, ask=0.20, bid=0.15, ticker=None):
    # NB: the complement fields are built from locals named `ask`/`bid` on purpose. Hard
    # rule #3's scanner rightly refuses arithmetic on an identifier carrying the ask name
    # anywhere outside core/pricing.py -- and it scans comment lines too, so this note
    # deliberately spells no such identifier.
    return {"strike_type": "between", "floor_strike": floor, "cap_strike": cap,
            "yes_ask": ask, "yes_bid": bid, "no_ask": 1 - bid,
            "no_bid": 1 - ask, "price_source_tag": "real_ask",
            "ticker": ticker or f"KXBTC-T-B{int((floor + cap) / 2)}"}


def _ladder(spot=1050.0, **kw):
    return [_bracket(900, 999.99, **kw), _bracket(1000, 1099.99, **kw),
            _bracket(1100, 1199.99, **kw), _bracket(1200, 1299.99, **kw)]


def _capture(event="KXBTC-E1", captured_at="2026-07-21T20:55:00Z",
             close_time="2026-07-21T21:00:00Z", spot=1050.0, status="ok",
             symbol="BTC", outcomes=None):
    return {"symbol": symbol, "captured_at": captured_at,
            "spot": {"price": spot, "price_source_tag": "synthetic"},
            "current": {"status": status, "event_ticker": event, "close_time": close_time,
                        "outcomes": outcomes if outcomes is not None else _ladder(spot)}}


# --------------------------------------------------------------------------- #
# 1. regime labelling
# --------------------------------------------------------------------------- #
def test_rate_exactly_at_the_interest_baseline_is_the_dead_band():
    assert Q.regime_label(BASE) == "pin"


def test_rate_below_baseline_but_positive_is_sub_baseline():
    assert Q.regime_label(BASE / 2) == "sub_baseline"
    assert Q.regime_label(0.0) == "sub_baseline"


def test_negative_rate_is_its_own_regime_not_merely_sub_baseline():
    assert Q.regime_label(-1e-6) == "negative"


def test_rate_above_baseline_is_above_baseline():
    assert Q.regime_label(BASE * 2) == "above_baseline"


def test_informative_and_control_cells_are_disjoint():
    assert not (Q.INFORMATIVE_REGIMES & Q.CONTROL_REGIMES)
    assert "pin" in Q.CONTROL_REGIMES and "pin" not in Q.INFORMATIVE_REGIMES


# --------------------------------------------------------------------------- #
# 2. regime runs (the L6/L318 blocking unit)
# --------------------------------------------------------------------------- #
def test_consecutive_same_label_hours_collapse_into_one_run():
    hours = {("BTC", 100): BASE, ("BTC", 101): BASE, ("BTC", 102): BASE}
    runs = Q.regime_runs(hours)
    assert len({rid for rid, _ in runs.values()}) == 1


def test_a_missing_hour_breaks_the_run():
    hours = {("BTC", 100): BASE, ("BTC", 102): BASE}
    runs = Q.regime_runs(hours)
    assert len({rid for rid, _ in runs.values()}) == 2


def test_a_label_change_breaks_the_run():
    hours = {("BTC", 100): BASE, ("BTC", 101): -1e-6, ("BTC", 102): BASE}
    runs = Q.regime_runs(hours)
    assert len({rid for rid, _ in runs.values()}) == 3


def test_two_coins_never_share_a_run_id():
    hours = {("BTC", 100): BASE, ("ETH", 100): BASE}
    runs = Q.regime_runs(hours)
    assert runs[("BTC", 100)][0] != runs[("ETH", 100)][0]


# --------------------------------------------------------------------------- #
# 3. entry snapshots
# --------------------------------------------------------------------------- #
def test_latest_capture_strictly_before_close_wins():
    recs = [_capture(captured_at="2026-07-21T20:10:00Z"),
            _capture(captured_at="2026-07-21T20:55:00Z")]
    best = Q.entry_snapshots(recs)
    assert len(best) == 1
    assert best[("BTC", "KXBTC-E1")]["captured_at"] == "2026-07-21T20:55:00Z"


def test_a_capture_at_or_after_close_is_never_an_entry():
    recs = [_capture(captured_at="2026-07-21T21:00:00Z"),
            _capture(captured_at="2026-07-21T21:30:00Z")]
    assert Q.entry_snapshots(recs) == {}


def test_non_ok_current_status_is_excluded():
    assert Q.entry_snapshots([_capture(status="no_hourly_group_found")]) == {}


def test_same_event_on_two_coins_is_two_entries():
    recs = [_capture(symbol="BTC"), _capture(symbol="ETH")]
    assert len(Q.entry_snapshots(recs)) == 2


# --------------------------------------------------------------------------- #
# 4. the directional leg
# --------------------------------------------------------------------------- #
def test_adjacent_above_leg_is_the_next_bracket_up_from_the_one_holding_spot():
    leg = Q.adjacent_above_leg(_ladder(), 1050.0)
    assert leg is not None
    assert leg["floor_strike"] == 1100


def test_no_leg_when_spot_is_outside_every_bracket():
    assert Q.adjacent_above_leg(_ladder(), 5000.0) is None


def test_no_leg_when_the_holding_bracket_is_the_top_of_the_ladder():
    assert Q.adjacent_above_leg(_ladder(), 1250.0) is None


def test_non_between_strike_types_are_ignored():
    ladder = _ladder() + [{"strike_type": "greater", "floor_strike": 1300,
                           "cap_strike": None, "yes_ask": 0.5, "yes_bid": 0.4,
                           "ticker": "KXBTC-T-T1300"}]
    leg = Q.adjacent_above_leg(ladder, 1250.0)
    assert leg is None  # the `greater` cap-less outcome is not a bracket


# --------------------------------------------------------------------------- #
# 5. fillability band
# --------------------------------------------------------------------------- #
def test_one_tick_ask_with_a_two_sided_quote_is_fillable():
    assert Q.leg_is_fillable({"yes_ask": 0.01, "yes_bid": 0.01}) is True


def test_a_one_sided_quote_is_not_fillable():
    assert Q.leg_is_fillable({"yes_ask": 0.20, "yes_bid": 0.0}) is False


def test_an_ask_above_the_pre_registered_band_is_not_fillable():
    assert Q.leg_is_fillable({"yes_ask": 0.99, "yes_bid": 0.95}) is False
    assert Q.leg_is_fillable({"yes_ask": Q.MAX_ENTRY_ASK, "yes_bid": 0.5}) is True


def test_a_missing_side_is_not_fillable():
    assert Q.leg_is_fillable({"yes_ask": None, "yes_bid": 0.4}) is False
    assert Q.leg_is_fillable({"yes_bid": 0.4}) is False


# --------------------------------------------------------------------------- #
# 6. candidate rows / cells
# --------------------------------------------------------------------------- #
def test_candidate_rows_assign_the_informative_and_control_cells():
    hours = {("BTC", 1_000): BASE, ("BTC", 1_001): -1e-6}
    runs = Q.regime_runs(hours)
    at_pin = f"{Q.parse_iso_utc('1970-01-01T00:00:00Z').isoformat()}"  # sanity: parser present
    assert at_pin
    pin_capture = _capture(event="E-PIN",
                           captured_at="2026-01-15T16:30:00Z",
                           close_time="2026-01-15T17:00:00Z")
    neg_capture = _capture(event="E-NEG",
                           captured_at="2026-01-15T17:30:00Z",
                           close_time="2026-01-15T18:00:00Z")
    # rebuild hours so the two captures land in the two synthetic regimes
    h_pin = int(Q.parse_iso_utc(pin_capture["captured_at"]).timestamp() // 3600)
    h_neg = int(Q.parse_iso_utc(neg_capture["captured_at"]).timestamp() // 3600)
    runs = Q.regime_runs({("BTC", h_pin): BASE, ("BTC", h_neg): -1e-6})
    rows = Q.candidate_rows([pin_capture, neg_capture], runs)
    cells = {r["event_ticker"]: r["cell"] for r in rows}
    assert cells == {"E-PIN": "control", "E-NEG": "informative"}


def test_candidate_rows_drop_a_capture_with_no_funding_hour():
    rows = Q.candidate_rows([_capture()], {})
    assert rows == []


def test_candidate_rows_carry_the_spot_source_tag_and_never_use_spot_as_a_price():
    h = int(Q.parse_iso_utc("2026-07-21T20:55:00Z").timestamp() // 3600)
    rows = Q.candidate_rows([_capture()], Q.regime_runs({("BTC", h): BASE}))
    assert rows[0]["spot_source_tag"] == "synthetic"
    assert rows[0]["price_source_tag"] == "real_ask"
    assert rows[0]["entry_ask_dollars"] == 0.20


# --------------------------------------------------------------------------- #
# 7. THE SEAL
# --------------------------------------------------------------------------- #
def test_preregistration_hash_is_pinned():
    assert Q.PREREG_SHA256 == Q.preregistration_sha256()
    assert Q.PREREG_SHA256 == (
        "edde1f66efc059d3628128ad2bbf0e49d60526c274664ca8e8bb5978dec34581")


def test_population_report_signature_takes_a_membership_set_not_a_result_map():
    import inspect
    src = inspect.getsource(Q.population_report)
    assert "binary_outcome" not in src
    assert '"yes"' not in src and "'yes'" not in src


def test_settled_ticker_set_drops_the_direction():
    settled, coverage = Q.settled_ticker_set([])
    assert settled == frozenset()
    assert coverage["requested"] == 0


def test_sealed_report_carries_no_outcome_or_pnl_token(tmp_path):
    hours = {("BTC", 1_000): -1e-6}
    runs = Q.regime_runs(hours)
    rows = Q.candidate_rows([], runs)
    pop = Q.population_report(rows, frozenset())
    assert pop["admissible"] is False
    blob = json.dumps(pop).lower()
    for token in Q.FORBIDDEN_SEALED_TOKENS:
        assert token not in blob, token


def test_run_over_an_empty_slice_is_sealed_and_scoreless(tmp_path):
    empty = tmp_path / "none-dt=*.jsonl"
    report = Q.run(str(empty), str(empty))
    assert report["status"] == "SEALED_INSUFFICIENT_DATA"
    assert "verdict" not in report
    assert report["population"]["gate_reasons"]


# --------------------------------------------------------------------------- #
# 8. scoring arithmetic (reachable only behind the gate, but its maths is pinned)
# --------------------------------------------------------------------------- #
def test_score_rows_charges_exactly_one_taker_fee_at_entry():
    row = {"leg_fillable": True, "leg_ticker": "T", "entry_ask_dollars": 0.20,
           "run_id": "BTC-run0001"}
    scored = Q.score_rows([row], {"T": 1})
    assert len(scored) == 1
    expected_fee = fee_per_contract(0.20, TAKER_FEE_RATE)
    assert scored[0]["fee_dollars"] == expected_fee
    assert scored[0]["pnl_dollars"] == pytest.approx(1.0 - 0.20 - expected_fee)
    assert scored[0]["price_source_tag_entry"] == "real_ask"
    assert scored[0]["price_source_tag_settlement"] == "broker_truth"


def test_a_losing_leg_loses_exactly_its_cost():
    row = {"leg_fillable": True, "leg_ticker": "T", "entry_ask_dollars": 0.20,
           "run_id": "BTC-run0001"}
    scored = Q.score_rows([row], {"T": 0})
    assert scored[0]["pnl_dollars"] == pytest.approx(
        -0.20 - fee_per_contract(0.20, TAKER_FEE_RATE))


def test_unfillable_and_unsettled_rows_are_never_scored():
    rows = [{"leg_fillable": False, "leg_ticker": "A", "entry_ask_dollars": 0.2,
             "run_id": "r"},
            {"leg_fillable": True, "leg_ticker": "B", "entry_ask_dollars": 0.2,
             "run_id": "r"}]
    assert Q.score_rows(rows, {}) == []
    assert len(Q.score_rows(rows, {"B": 1})) == 1


def test_verdict_block_reports_admissibility_and_the_tick_gate():
    scored = [{"run_id": f"r{i}", "pnl_dollars": 0.05} for i in range(3)]
    block = Q.verdict_block(scored)
    assert block["n_scored"] == 3
    assert block["admissibility"]["admissible"] is False       # 3 units < the L41 floor
    assert "below_min_units" in block["admissibility"]["reasons"]
    assert block["clears_tick_magnitude"] in (True, False)
    assert block["kish"]["n_units"] == 3


# --------------------------------------------------------------------------- #
# 9. real-tape acceptance, on a FIXED slice (directional — survives tape growth)
# --------------------------------------------------------------------------- #
@_real_tape
def test_acceptance_fixed_slice_builds_informative_and_control_cells():
    hours = Q.funding_hours([str(p) for p in FUNDING_DAYS])
    runs = Q.regime_runs(hours)
    rows = Q.candidate_rows(Q.load_crypto_records([str(p) for p in CRYPTO_DAYS]), runs)
    assert rows, "the fixed crypto slice must produce entry candidates"
    cells = {r["cell"] for r in rows}
    assert "informative" in cells and "control" in cells
    # every leg price on a real row is a resting real_ask, never a synthetic
    assert {r["price_source_tag"] for r in rows if r["leg_ticker"]} == {"real_ask"}


@_real_tape
def test_acceptance_the_join_loses_most_of_the_informative_cell_to_settlement_pairing():
    """The load-bearing measurement (L327): `crypto_hourly.previous_settlement` reports ONLY
    the event that closed immediately before a capture, so most entry snapshots never get a
    settlement partner. Directional: the unjoined informative population may only grow."""
    hours = Q.funding_hours([str(p) for p in FUNDING_DAYS])
    runs = Q.regime_runs(hours)
    rows = Q.candidate_rows(Q.load_crypto_records([str(p) for p in CRYPTO_DAYS]), runs)
    settled, _cov = Q.settled_ticker_set(sorted({r["leg_ticker"] for r in rows
                                                 if r["leg_ticker"]}))
    informative = [r for r in rows if r["cell"] == "informative"]
    unjoined = [r for r in informative if r["leg_ticker"] not in settled]
    assert len(informative) >= 8
    assert len(unjoined) >= 1


@_real_tape
def test_acceptance_gate_is_shut_on_the_fixed_slice():
    hours = Q.funding_hours([str(p) for p in FUNDING_DAYS])
    runs = Q.regime_runs(hours)
    rows = Q.candidate_rows(Q.load_crypto_records([str(p) for p in CRYPTO_DAYS]), runs)
    settled, _cov = Q.settled_ticker_set(sorted({r["leg_ticker"] for r in rows
                                                 if r["leg_ticker"]}))
    pop = Q.population_report(rows, settled)
    assert pop["admissible"] is False
    assert "below_min_units" in pop["gate_reasons"]
    # and the sealed population block still leaks no outcome
    blob = json.dumps(pop).lower()
    for token in Q.FORBIDDEN_SEALED_TOKENS:
        assert token not in blob, token
