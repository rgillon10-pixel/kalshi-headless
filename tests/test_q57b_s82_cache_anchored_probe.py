"""Tests for the Q57(b) / S82 cache-anchored flow-fade probe.

Two tiers, deliberately separated:

  * LOGIC tier — synthetic fixtures, exact assertions. Everything the module itself owns
    (the union anchor and its precedence, the multivalue pick, the minority floor, the L51
    restatement, the concentration/calibration checks) is pinned here.
  * REAL-TAPE tier — asserts DIRECTIONS, FLOORS and INVARIANTS only, never an exact value
    (L320/L191: a test that pins a tape-derived number turns every future collector pass
    into a red build and teaches the next run to edit the test instead of the finding).

The one exception is the pre-registration digest, which is pinned exactly ON PURPOSE: that
test failing is the intended alarm that someone edited a sealed constant after scoring.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.pricing import MAKER_FEE_RATE, TAKER_FEE_RATE  # noqa: E402
from scripts import q57_s82_flow_fade_probe as P  # noqa: E402
from scripts import q57b_s82_cache_anchored_probe as Q  # noqa: E402

# The digest of the sealed spec at the moment it was run. Changing any pre-registered
# constant changes this and fails here — that is the alarm, not a bug.
SEALED_SHA256 = "eaab11238127ebedb5df61b41427d9ac7881272a7bd7a3a18cb3cc76e63ac595"


# --------------------------------------------------------------------------- #
# the seal
# --------------------------------------------------------------------------- #
def test_preregistration_hash_is_sealed():
    assert Q.PREREG_SHA256 == SEALED_SHA256
    assert Q.preregistration_sha256() == SEALED_SHA256


def test_preregistration_cites_the_commit_that_pre_committed_its_constants():
    """Path (b)'s constants are quoted from LOOP-QUEUE.md as committed BEFORE this probe.
    Without the citation the seal is just a hash of a choice made in the same session."""
    assert Q.PREREGISTRATION["prereg_source_commit"] == Q.PREREG_SOURCE_COMMIT
    assert "LOOP-QUEUE.md" in str(Q.PREREGISTRATION["prereg_source"])
    assert Q.PREREGISTRATION["reopen_path"] == "b"


def test_the_three_path_b_constants_are_what_the_queue_text_named():
    assert Q.PREREGISTRATION["flow_window_minutes"] == 15
    assert Q.PREREGISTRATION["max_entry_lag_minutes"] == 240
    assert "q51_settlement_cache" in str(Q.PREREGISTRATION["close_anchor"])


def test_minority_floor_is_the_real_default_two_not_one():
    """The first probe used 1 — an undisclosed relaxation of
    `sign_variation_admissible`'s actual default. Path (b) exists partly to fix that."""
    import inspect

    from core.bootstrap import sign_variation_admissible

    assert Q.MIN_MINORITY_UNITS == 2
    assert Q.PREREGISTRATION["min_exclusive_minority_units"] == 2
    lib_default = inspect.signature(
        sign_variation_admissible).parameters["min_exclusive_minority_units"].default
    assert Q.MIN_MINORITY_UNITS == lib_default, (
        "the probe's floor must BE the library default, not a coincidentally equal literal")
    assert Q.MIN_MINORITY_UNITS > P.MIN_MINORITY_UNITS


def test_fee_is_the_taker_rate_imported_not_spelled():
    """L5: an S13 draft charged maker fills the taker rate — a 4x overcharge. S82 CROSSES
    the spread, so taker is correct; the mirror error would UNDERcharge and manufacture
    an edge."""
    assert Q.FEE_RATE == TAKER_FEE_RATE
    assert Q.FEE_RATE != MAKER_FEE_RATE
    assert Q.PREREGISTRATION["fee_side"] == "taker"
    assert Q.PREREGISTRATION["fee_legs"] == 1


# --------------------------------------------------------------------------- #
# the union anchor — the only loader this module owns
# --------------------------------------------------------------------------- #
def _write_cache(tmp_path: Path, blobs):
    d = tmp_path / "cache"
    d.mkdir()
    for i, markets in enumerate(blobs):
        (d / f"settlement-{i}.json").write_text(json.dumps(
            {"day": "2026-08-01", "markets": markets, "price_source_tag": "broker_truth"}))
    return d


def test_cache_loader_picks_earliest_by_default_and_latest_on_request(tmp_path):
    d = _write_cache(tmp_path, [
        {"KXA-26AUG01XY-X": {"close_time": "2026-08-01T12:00:00Z", "result": "yes"}},
        {"KXA-26AUG01XY-X": {"close_time": "2026-08-01T10:00:00Z", "result": "yes"}},
    ])
    tickers = frozenset({"KXA-26AUG01XY-X"})
    early, census = Q.load_cache_close_times(tickers, d)
    late, _ = Q.load_cache_close_times(tickers, d, pick="latest")
    assert late["KXA-26AUG01XY-X"] - early["KXA-26AUG01XY-X"] == pytest.approx(7200.0)
    assert census["n_with_multiple_close_times"] == 1
    assert census["max_distinct_close_times"] == 2


def test_cache_loader_reports_mutation_rather_than_silently_collapsing_it(tmp_path):
    """L360/L361: Kalshi rewrites close_time EARLIER at settlement. A loader that just
    takes min() and says nothing hides the exposure."""
    d = _write_cache(tmp_path, [
        {"A-X": {"close_time": "2026-08-01T12:00:00Z"}, "B-Y": {"close_time": "2026-08-01T12:00:00Z"}},
        {"A-X": {"close_time": "2026-08-01T09:00:00Z"}, "B-Y": {"close_time": "2026-08-01T12:00:00Z"}},
    ])
    _, census = Q.load_cache_close_times(frozenset({"A-X", "B-Y"}), d)
    assert census["n_tickers_in_cache_and_traded"] == 2
    assert census["n_with_multiple_close_times"] == 1


def test_cache_loader_rejects_an_unknown_pick():
    with pytest.raises(ValueError):
        Q.load_cache_close_times(frozenset(), pick="median")


def test_cache_loader_ignores_tickers_outside_the_requested_set(tmp_path):
    d = _write_cache(tmp_path, [{"WANTED-X": {"close_time": "2026-08-01T12:00:00Z"},
                                 "UNWANTED-Y": {"close_time": "2026-08-01T12:00:00Z"}}])
    out, _ = Q.load_cache_close_times(frozenset({"WANTED-X"}), d)
    assert set(out) == {"WANTED-X"}


def test_union_anchor_gives_the_ledger_precedence(tmp_path, monkeypatch):
    """Precedence is pre-registered so the widening is strictly ADDITIVE: no unit the
    ledger already anchored may silently move to a cache-derived instant."""
    d = _write_cache(tmp_path, [{"SHARED-X": {"close_time": "2026-08-01T09:00:00Z"},
                                 "CACHEONLY-Y": {"close_time": "2026-08-01T11:00:00Z"}}])
    monkeypatch.setattr(P, "load_close_times",
                        lambda tickers, tape_dir=None: ({"SHARED-X": 1000.0}, 1))
    merged, prov = Q.union_close_times(frozenset({"SHARED-X", "CACHEONLY-Y"}), cache_dir=d)
    assert merged["SHARED-X"] == 1000.0          # ledger won
    assert "CACHEONLY-Y" in merged               # cache widened
    assert prov["n_added_by_cache"] == 1
    assert prov["n_in_both"] == 1
    assert prov["precedence"] == "settlement_ledger"


def test_union_anchor_is_a_superset_of_the_ledger_only_anchor(tmp_path, monkeypatch):
    d = _write_cache(tmp_path, [{"C-1": {"close_time": "2026-08-01T09:00:00Z"}}])
    monkeypatch.setattr(P, "load_close_times",
                        lambda tickers, tape_dir=None: ({"L-1": 5.0, "L-2": 6.0}, 1))
    merged, _ = Q.union_close_times(frozenset({"C-1", "L-1", "L-2"}), cache_dir=d)
    assert {"L-1", "L-2"}.issubset(set(merged))


# --------------------------------------------------------------------------- #
# Q57 gate (3) — the L51 restatement
# --------------------------------------------------------------------------- #
def test_l51_is_not_voided_and_admits_the_window_axis_inverted():
    d = Q.l51_differentiation([])
    assert d["voided"] is False
    assert d["entry_price_surfaces_disjoint"] is True
    assert d["window_ratio"] == pytest.approx(15.0 / 30.0)
    assert d["window_ratio"] < 1.0, "at 15 min the window is NARROWER than S79's 30"
    assert "HALF" in d["window_axis_note"]
    assert "disjoint_entry_price_family" in d["surviving_differentiation_axes"]


def test_l51_void_condition_is_reachable_if_the_price_family_ever_matched(monkeypatch):
    """A gate that can never fire is not a gate. Both branches must be reachable (L249)."""
    monkeypatch.setattr(P, "S82_ENTRY_PRICE_FAMILY", P.S79_ENTRY_PRICE_FAMILY)
    assert Q.l51_differentiation([])["entry_price_surfaces_disjoint"] is False


# --------------------------------------------------------------------------- #
# population report
# --------------------------------------------------------------------------- #
def _row(game, ticker, side, ask=0.5, instant="2026-08-01T00:00:00Z"):
    return {"game": game, "ticker": ticker, "fade_side": side, "entry_ask": ask,
            "entry_captured_at": instant, "overround": 0.02}


def test_population_report_floors_are_explicit_kwargs_not_module_globals():
    """Rebinding another module's global to change a gate is the defect class
    `q57_s82_rederive.py` caught last round."""
    rows = [_row(f"G{i}", f"T{i}", "no") for i in range(11)]
    rows.append(_row("G11", "T11", "yes"))
    settled = frozenset(r["ticker"] for r in rows)
    strict = Q.population_report(rows, settled, min_minority=2)
    loose = Q.population_report(rows, settled, min_minority=1)
    assert strict["admissible"] is False      # only 1 exclusive-minority unit
    assert loose["admissible"] is True
    assert strict["min_exclusive_minority_units"] == 2


def test_population_report_enforces_the_l41_unit_floor():
    rows = [_row(f"G{i}", f"T{i}", "no") for i in range(5)]
    rows += [_row("Ga", "Ta", "yes"), _row("Gb", "Tb", "yes")]
    pop = Q.population_report(rows, frozenset(r["ticker"] for r in rows))
    assert pop["meets_unit_floor"] is False
    assert pop["admissible"] is False


def test_population_report_only_counts_settled_tickers():
    rows = [_row("G1", "T1", "no"), _row("G2", "T2", "yes")]
    pop = Q.population_report(rows, frozenset({"T1"}))
    assert pop["n_entries_all"] == 2
    assert pop["n_entries_scoreable"] == 1


def test_population_report_tags_its_price_source():
    pop = Q.population_report([_row("G1", "T1", "no")], frozenset({"T1"}))
    assert pop["price_source_tag"] == "real_ask"


# --------------------------------------------------------------------------- #
# the concentration / calibration checks
# --------------------------------------------------------------------------- #
def _s(game, ask, won, rho=0.5):
    pnl = (1.0 if won else 0.0) - ask - 0.0
    return {"game": game, "entry_ask": ask, "fade_won": won, "fee": 0.0,
            "pnl": pnl, "rho": rho}


def test_jackknife_flags_a_mean_carried_by_one_unit():
    scored = [_s(f"G{i}", 0.5, False) for i in range(9)] + [_s("BIG", 0.02, True)]
    cc = Q.concentration_and_calibration(scored, n_boot=200)
    jk = cc["jackknife"]
    assert jk["worst_leave_one_out"]["dropped_unit"] == "BIG"
    assert jk["max_single_unit_mean_contribution"] > 0


def test_calibration_null_counts_excess_wins_not_dollars():
    scored = [_s(f"G{i}", 0.5, i < 6) for i in range(10)]
    cal = Q.concentration_and_calibration(scored, n_boot=200)["calibration_null"]
    assert cal["observed_fade_wins"] == 6
    assert cal["expected_fade_wins_if_asks_calibrated"] == pytest.approx(5.0)
    assert cal["excess_wins"] == pytest.approx(1.0)
    assert cal["price_source_tag"] == "real_ask"


def test_price_ordering_detects_a_perfect_price_separation():
    scored = [_s("A", 0.9, True), _s("B", 0.8, True), _s("C", 0.1, False), _s("D", 0.2, False)]
    po = Q.concentration_and_calibration(scored, n_boot=200)["price_ordering"]
    assert po["perfectly_price_ordered"] is True
    assert po["win_ask_min"] > po["lose_ask_max"]


def test_price_ordering_is_false_when_prices_interleave():
    scored = [_s("A", 0.9, True), _s("B", 0.1, True), _s("C", 0.8, False), _s("D", 0.2, False)]
    po = Q.concentration_and_calibration(scored, n_boot=200)["price_ordering"]
    assert po["perfectly_price_ordered"] is False


def test_concentration_check_is_empty_safe():
    assert Q.concentration_and_calibration([])["n_units"] == 0


# --------------------------------------------------------------------------- #
# REAL-TAPE tier — directions, floors and invariants ONLY (L320/L191)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def report():
    return Q.run()


def test_real_tape_never_quotes_a_synthetic_price(report):
    """Hard Rule #1 / the pt1 wall: a synthetic price is never a fill."""
    assert report["price_provenance"]["price_source_tag"] == "real_ask"
    assert report["price_provenance"]["synthetic_prices_used"] is False
    for s in report.get("scored", []):
        assert s["price_source_tag"] == "real_ask"


def test_real_tape_every_scored_entry_carries_a_price_and_a_tag(report):
    for s in report.get("scored", []):
        assert s["entry_ask"] is not None
        assert 0.02 <= s["entry_ask"] <= 0.98
        assert s["price_source_tag"] == "real_ask"


def test_real_tape_l51_gate_ran_before_any_outcome_and_did_not_void(report):
    assert report["l51_differentiation"]["voided"] is False


def test_real_tape_population_clears_the_floors_it_claims_to_clear(report):
    pop = report["population"]
    if pop["admissible"]:
        assert pop["n_game_units"] >= Q.MIN_UNITS
        cen = pop["sign_variation"]["census"]
        assert cen["minority_side_units_exclusive"] >= Q.MIN_MINORITY_UNITS


def test_real_tape_verdict_is_one_of_the_declared_classes(report):
    assert report["verdict"] in {"ALIVE", "DEAD", "INSUFFICIENT DATA", "VOID"}


def test_real_tape_alive_requires_a_ci_strictly_above_zero(report):
    """The bar itself, asserted rather than trusted: nothing may be called ALIVE whose
    bootstrapped lower bound is not strictly positive AND tick-material."""
    if report["verdict"] == "ALIVE":
        assert report["bootstrap"]["ci95"][0] > 0.0
        assert report["clears_tick_magnitude"] is True


def test_real_tape_anchor_widening_is_additive(report):
    prov = report["anchor_provenance"]
    assert prov["n_union"] >= prov["n_from_settlement_ledger"]
    assert prov["precedence"] == "settlement_ledger"


def test_real_tape_anchor_multivalue_choice_does_not_drive_the_result(report):
    """If `earliest` vs `latest` moved the verdict, the undetermined choice would be
    load-bearing and the result would not be reportable."""
    rows = {r["anchor"]: r for r in report.get("robustness_anchors", [])}
    if "prereg_union_earliest" in rows and "union_latest_close_time" in rows:
        a, b = rows["prereg_union_earliest"], rows["union_latest_close_time"]
        if a["ci95"] and b["ci95"]:
            assert (a["ci95"][0] > 0) == (b["ci95"][0] > 0)


def test_real_tape_bootstrap_unit_is_the_game(report):
    """L6: block-bootstrap by the independent unit, never by outcome/leg."""
    if report.get("bootstrap"):
        assert report["bootstrap"]["n_units"] == report["population"]["n_game_units"]
        assert report["preregistration"]["unit"] == "game"
