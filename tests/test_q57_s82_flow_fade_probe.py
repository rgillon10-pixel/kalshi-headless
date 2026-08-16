"""Offline tests for the Q57 / S82 signed-taker-flow FADE probe.

House style (L201/L207): hard assertions over hand-built fixtures, no network, no reliance on
the live tape except in the two deliberately STRUCTURAL tests at the bottom (this tape grows
daily, so a value-pinned real-tape test would become the next stale constant — L191).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import q57_s82_flow_fade_probe as P


# ── the seal ──────────────────────────────────────────────────────────────────
def test_preregistration_hash_is_sealed():
    """Any edit to a spec constant must break loudly — tuning cannot be a quiet diff."""
    assert P.PREREG_SHA256 == P.preregistration_sha256(P.PREREGISTRATION)
    assert P.PREREG_SHA256 == "dd80f5973c39a0f4e99afcce8a83eb97c51070d046ad5a893bab1c559fa1c92c"


def test_preregistration_carries_every_binding_constant():
    for k in ("flow_window_minutes", "min_abs_rho", "min_window_count",
              "max_entry_lag_minutes", "entry_price_band", "min_units",
              "min_exclusive_minority_units", "direction", "fee_legs", "fee_side"):
        assert k in P.PREREGISTRATION, k
    assert P.PREREGISTRATION["direction"] == "FADE"
    assert P.PREREGISTRATION["fee_legs"] == 1
    assert P.PREREGISTRATION["fee_side"] == "taker"


def test_fee_rate_is_the_taker_rate_from_core_pricing():
    from core.pricing import TAKER_FEE_RATE
    assert P.FEE_RATE == TAKER_FEE_RATE


# ── the join key (Q57's named gotcha) ─────────────────────────────────────────
def test_game_id_strips_the_outcome_suffix_not_the_event_ticker():
    assert P.game_id_of("KXKBOGAME-26JUL070530KIALOT-KIA") == "KXKBOGAME-26JUL070530KIALOT"
    assert P.game_id_of("KXUCLGAME-26JUL07ARARFC-TIE") == "KXUCLGAME-26JUL07ARARFC"


# ── signal orientation + window ──────────────────────────────────────────────
def _pr(ts, side, count, book_side=None):
    return {"ts": float(ts), "side": side, "count": float(count),
            "book_side": book_side or (P.TAKER_BUYS if side == "yes" else P.TAKER_SELLS)}


def test_window_flow_signs_yes_positive_and_no_negative():
    rows = [_pr(0, "yes", 10), _pr(10, "no", 4)]
    net, tot, n = P.window_flow(rows, 100.0, window_s=1000.0)
    assert (net, tot, n) == (6.0, 14.0, 2)


def test_window_flow_is_half_open_and_excludes_the_future():
    rows = [_pr(0, "yes", 5), _pr(50, "yes", 7), _pr(150, "yes", 99)]
    net, tot, n = P.window_flow(rows, 100.0, window_s=100.0)
    assert n == 1 and net == 7.0        # ts=0 is at the open boundary, ts=150 is after entry
    assert tot == 7.0


def test_window_flow_keeps_fractional_counts():
    """L47: a fractional `count` is valid venue data; int-coercion silently drops it."""
    net, tot, _ = P.window_flow([_pr(5, "yes", 10.93)], 10.0, window_s=100.0)
    assert net == pytest.approx(10.93) and tot == pytest.approx(10.93)


def test_flow_orientation_audit_reports_non_collinear_tape():
    prints = {"A": [_pr(0, "yes", 1, book_side=P.TAKER_SELLS)]}   # decoupled fields
    a = P.flow_orientation_audit(prints)
    assert a["collinear"] is False and a["n_orientation_agreeing"] == 0


# ── entry construction ───────────────────────────────────────────────────────
def _fixture(rho_side="yes", yes_ask=0.40, no_ask=0.60, lag_s=60.0, count=1000.0):
    tk = "KXTESTGAME-26JUL01AAABBB-AAA"
    prints = {tk: [_pr(900.0, rho_side, count)]}
    depth = {tk: [{"ts": 1000.0, "captured_at": "2026-07-01T00:16:40+00:00",
                   "best_yes_ask": yes_ask, "best_no_ask": no_ask}]}
    closes = {tk: 1000.0 + lag_s}
    return prints, depth, closes


def test_fade_takes_the_side_opposite_the_flow():
    rows, _ = P.entry_candidates(*_fixture(rho_side="yes"))
    assert len(rows) == 1 and rows[0]["fade_side"] == "no" and rows[0]["entry_ask"] == 0.60
    rows, _ = P.entry_candidates(*_fixture(rho_side="no"))
    assert len(rows) == 1 and rows[0]["fade_side"] == "yes" and rows[0]["entry_ask"] == 0.40


def test_entry_price_is_tagged_real_ask_and_carries_the_overround():
    rows, _ = P.entry_candidates(*_fixture(yes_ask=0.44, no_ask=0.60))
    assert rows[0]["price_source_tag"] == "real_ask"
    assert rows[0]["overround"] == pytest.approx(0.04)


def test_stale_entry_snapshot_is_dropped():
    _, drops = P.entry_candidates(*_fixture(lag_s=P.MAX_ENTRY_LAG_S + 1.0))
    assert drops["entry_snapshot_too_stale"] == 1


def test_thin_window_is_dropped_below_the_count_floor():
    _, drops = P.entry_candidates(*_fixture(count=P.MIN_WINDOW_COUNT - 1.0))
    assert drops["window_count_below_floor"] == 1


def test_absent_fade_side_ask_is_a_drop_not_a_reconstructed_price():
    """A one-sided book (L23) must never be completed from the opposite side's bid."""
    _, drops = P.entry_candidates(*_fixture(rho_side="yes", no_ask=None))
    assert drops["fade_side_ask_absent"] == 1


def test_floor_pinned_ask_is_outside_the_price_band():
    _, drops = P.entry_candidates(*_fixture(rho_side="no", yes_ask=0.01))
    assert drops["entry_ask_outside_price_band"] == 1


def test_non_extreme_flow_is_dropped():
    tk = "KXTESTGAME-26JUL01AAABBB-AAA"
    prints = {tk: [_pr(900.0, "yes", 550.0), _pr(901.0, "no", 500.0)]}   # rho = 0.0476
    depth = {tk: [{"ts": 1000.0, "captured_at": "x", "best_yes_ask": 0.4, "best_no_ask": 0.6}]}
    _, drops = P.entry_candidates(prints, depth, {tk: 1010.0})
    assert drops["flow_not_extreme"] == 1


def test_collapse_to_games_takes_one_entry_per_game_by_max_abs_rho():
    rows = [{"game": "G", "ticker": "G-A", "rho": 0.30},
            {"game": "G", "ticker": "G-B", "rho": -0.80},
            {"game": "H", "ticker": "H-A", "rho": 0.50}]
    out = P.collapse_to_games(rows)
    assert {r["game"] for r in out} == {"G", "H"}
    assert next(r for r in out if r["game"] == "G")["ticker"] == "G-B"


def test_collapse_tie_breaks_on_the_lexicographically_smaller_ticker():
    rows = [{"game": "G", "ticker": "G-B", "rho": 1.0},
            {"game": "G", "ticker": "G-A", "rho": -1.0}]
    assert P.collapse_to_games(rows)[0]["ticker"] == "G-A"


# ── the sweep defect the rederive caught ─────────────────────────────────────
def test_sweep_constants_are_threaded_not_read_from_globals():
    """A module global that is ALSO another function's default argument is bound at def-time.

    `scripts/q57_s82_rederive.py` caught the earlier version rebinding `FLOW_WINDOW_S` and
    sweeping nothing on that axis (4 sign-variation-passing cells reported as 0). This pins
    that a caller-supplied window actually changes the answer."""
    tk = "KXTESTGAME-26JUL01AAABBB-AAA"
    prints = {tk: [_pr(0.0, "yes", 10000.0), _pr(990.0, "no", 2000.0)]}
    depth = {tk: [{"ts": 1000.0, "captured_at": "x", "best_yes_ask": 0.4, "best_no_ask": 0.6}]}
    closes = {tk: 1010.0}
    wide, _ = P.entry_candidates(prints, depth, closes, window_s=5000.0)
    narrow, _ = P.entry_candidates(prints, depth, closes, window_s=100.0)
    assert wide and narrow
    assert wide[0]["fade_side"] == "no"       # net +8000 over the wide window
    assert narrow[0]["fade_side"] == "yes"    # only the -2000 print is inside the narrow one


# ── scoring ──────────────────────────────────────────────────────────────────
def test_score_charges_exactly_one_taker_fee_and_pays_one_dollar_on_a_win():
    from core.pricing import TAKER_FEE_RATE, fee_per_contract
    row = {"game": "G", "ticker": "G-A", "fade_side": "no", "entry_ask": 0.60}
    s = P.score_rows([row], {"G-A": 0})[0]
    assert s["fade_won"] is True
    assert s["fee"] == fee_per_contract(0.60, TAKER_FEE_RATE)
    assert s["pnl"] == pytest.approx(1.0 - 0.60 - s["fee"])
    lose = P.score_rows([row], {"G-A": 1})[0]
    assert lose["fade_won"] is False
    assert lose["pnl"] == pytest.approx(-0.60 - lose["fee"])


def test_score_drops_unresolved_tickers_rather_than_booking_a_loss():
    """L52: an unknown result is not a loss."""
    row = {"game": "G", "ticker": "G-A", "fade_side": "no", "entry_ask": 0.60}
    assert P.score_rows([row], {}) == []


# ── gates ────────────────────────────────────────────────────────────────────
def test_population_report_fails_the_sign_variation_gate_when_single_sided():
    rows = [{"game": f"G{i}", "ticker": f"G{i}-A", "fade_side": "no",
             "entry_captured_at": f"t{i}", "overround": 0.02} for i in range(12)]
    rep = P.population_report(rows, frozenset(r["ticker"] for r in rows))
    assert rep["meets_unit_floor"] is True
    assert rep["admissible"] is False
    assert "single_sided" in rep["sign_variation"]["reasons"]


def test_population_report_admissible_with_one_exclusive_minority_unit():
    rows = [{"game": f"G{i}", "ticker": f"G{i}-A",
             "fade_side": "yes" if i == 0 else "no",
             "entry_captured_at": f"t{i}", "overround": 0.02} for i in range(12)]
    rep = P.population_report(rows, frozenset(r["ticker"] for r in rows))
    assert rep["admissible"] is True
    assert rep["sign_variation"]["census"]["minority_side_units_exclusive"] == 1


def test_population_report_fails_below_the_l41_unit_floor():
    rows = [{"game": f"G{i}", "ticker": f"G{i}-A",
             "fade_side": "yes" if i == 0 else "no",
             "entry_captured_at": f"t{i}", "overround": 0.02} for i in range(9)]
    rep = P.population_report(rows, frozenset(r["ticker"] for r in rows))
    assert rep["meets_unit_floor"] is False and rep["admissible"] is False


def test_l51_differentiation_does_not_void_on_disjoint_price_surfaces():
    d = P.l51_differentiation([])
    assert d["voided"] is False
    assert d["entry_price_surfaces_disjoint"] is True
    assert d["s82_direction"] == "FADE" and d["s79_direction"] == "FOLLOW"
    assert d["window_ratio"] == 4.0


def test_l51_differentiation_is_outcome_blind():
    blob = json.dumps(P.l51_differentiation([])).lower()
    for token in ("pnl", "ci95", "settled", "won", "result"):
        assert token not in blob, token


# ── real-tape STRUCTURAL tests (no pinned values — this tape grows daily, L191) ──
def test_committed_report_is_present_and_structurally_complete():
    path = Path(P.REPORT_PATH)
    assert path.exists(), "run scripts/q57_s82_flow_fade_probe.py"
    rep = json.loads(path.read_text())
    for k in ("preregistration_sha256", "l51_differentiation", "population",
              "sign_variation_sensitivity", "minority_arm_fillability",
              "close_time_cross_family_audit", "verdict"):
        assert k in rep, k
    assert rep["preregistration_sha256"] == P.PREREG_SHA256


def test_an_inadmissible_report_never_carries_a_ci_or_a_pnl():
    """The structural refusal: no CI may be quoted on a population that failed a gate."""
    rep = json.loads(Path(P.REPORT_PATH).read_text())
    if not rep.get("population", {}).get("admissible", False):
        assert "bootstrap" not in rep
        assert "scored" not in rep
        assert rep["verdict"] in ("INSUFFICIENT DATA", "VOID")
