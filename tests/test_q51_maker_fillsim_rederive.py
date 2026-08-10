"""Offline tests for scripts/q51_maker_fillsim_rederive.py.

The re-derivation is a REDUNDANCY check (own reader, own Decimal fee arithmetic, own
grouping, own bootstrap, different seed) standing in for a `verifier` subagent that was
not dispatchable. These tests pin that it is genuinely independent and that it would
actually FAIL on a corrupted row rather than rubber-stamping the probe.
"""
from __future__ import annotations

import json

import pytest

from core.pricing import MAKER_FEE_RATE, TAKER_FEE_RATE, fee_per_contract
from scripts import q51_maker_fillsim_rederive as R


def test_independent_fee_matches_core_pricing_on_every_tradeable_cent():
    """Decimal ROUND_CEILING vs core.pricing's math.ceil must agree at every price a
    Kalshi order can carry — if they ever disagree the redundancy check is worthless."""
    for cents in range(1, 100):
        p = cents / 100
        assert R.maker_fee(p) == pytest.approx(fee_per_contract(p, rate=MAKER_FEE_RATE))


def test_rederivation_uses_the_maker_rate_not_the_taker_rate_l5():
    p = 0.40
    assert R.maker_fee(p) == pytest.approx(fee_per_contract(p, rate=MAKER_FEE_RATE))
    assert R.maker_fee(p) != pytest.approx(fee_per_contract(p, rate=TAKER_FEE_RATE))


def test_uses_a_different_seed_from_the_probe():
    from scripts import q51_maker_fillsim as M
    assert R.SEED != M.SEED


def test_own_game_key_matches_the_probes_grouping_without_importing_it():
    from scripts import q51_maker_fillsim as M
    for t in ("KXMLBGAME-26AUG032005LADCHC-CHC", "KXNWSLGAME-26AUG02DENBOS-DEN", "SOLO"):
        assert R.own_game_key(t) == M.game_of(t)


def _row(**kw):
    base = {"ticker": "KXTESTGAME-26AUG03AB-A", "side": "yes_bid", "rest_price": 0.40,
            "filled": True, "fill_trade_id": "t1", "fill_price_source_tag": "broker_truth",
            "settle_result": "yes", "interval_covered": True, "price_source_tag": "real_bid"}
    base.update(kw)
    if "pnl" not in base:
        pr = base["rest_price"]
        if not base["filled"]:
            base["pnl"] = 0.0
        else:
            won = ((base["settle_result"] == "yes") if base["side"] == "yes_bid"
                   else (base["settle_result"] == "no"))
            base["pnl"] = (1.0 if won else 0.0) - pr - R.maker_fee(pr)
    return base


def _write(tmp_path, rows):
    p = tmp_path / "rows.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def test_clean_rows_produce_zero_mismatches(tmp_path):
    out = R.rederive(_write(tmp_path, [_row(), _row(side="no_bid", settle_result="no")]),
                     n_boot=100)
    assert out["pnl_mismatches"] == 0 and out["untraced_fills"] == 0
    assert out["price_tag_violations"] == 0


def test_a_corrupted_pnl_is_caught(tmp_path):
    out = R.rederive(_write(tmp_path, [_row(pnl=0.99)]), n_boot=50)
    assert out["pnl_mismatches"] == 1
    assert out["examples_of_mismatch"]


def test_a_fill_with_no_broker_truth_print_is_caught(tmp_path):
    out = R.rederive(_write(tmp_path, [_row(fill_trade_id=None)]), n_boot=50)
    assert out["untraced_fills"] == 1


def test_a_fill_tagged_other_than_broker_truth_is_caught(tmp_path):
    out = R.rederive(_write(tmp_path, [_row(fill_price_source_tag="synthetic")]), n_boot=50)
    assert out["untraced_fills"] == 1


def test_a_non_real_bid_rest_price_tag_is_caught(tmp_path):
    out = R.rederive(_write(tmp_path, [_row(price_source_tag="midpoint")]), n_boot=50)
    assert out["price_tag_violations"] == 1


def test_unfilled_row_must_carry_zero_pnl(tmp_path):
    bad = _row(filled=False, fill_trade_id=None, fill_price_source_tag=None, pnl=0.25)
    out = R.rederive(_write(tmp_path, [bad]), n_boot=50)
    assert out["pnl_mismatches"] == 1


def test_admissibility_needs_ten_units_and_one_opposing_cluster(tmp_path):
    rows = [_row(ticker=f"KXTESTGAME-26AUG03G{i}-A",
                 settle_result=("yes" if i else "no")) for i in range(12)]
    out = R.rederive(_write(tmp_path, rows), n_boot=200)
    assert out["all_intervals"]["n_units"] == 12
    assert out["all_intervals"]["n_opposing_units"] >= 1
    assert out["all_intervals"]["admissible"] is True


def test_all_same_direction_population_is_inadmissible_s20(tmp_path):
    rows = [_row(ticker=f"KXTESTGAME-26AUG03G{i}-A") for i in range(12)]
    out = R.rederive(_write(tmp_path, rows), n_boot=200)
    assert out["all_intervals"]["n_opposing_units"] == 0
    assert out["all_intervals"]["admissible"] is False


#: The FROZEN milestone-2 rows file (L325's repair, 2026-08-10). `R.rederive()` defaults to
#: the LIVE `reports/q51_maker_fillsim_rows.jsonl`, which milestone 3's own firing command
#: rewrites — 40 rows became 294 on 2026-08-10 and this acceptance case went red. Same defect
#: class as L284/L191: pin to a slice that cannot grow.
M2_ROWS = R.ROWS_PATH.parent / "q51_maker_fillsim_rows-m2-2026-08-04.jsonl"
M2_ROWS_SHA256 = "780b1a7de2970ea8187f01c8252051aa95d2fe14e5afa7bcdcd62eb83d65ca50"


def test_acceptance_frozen_m2_rows_are_the_milestone_2_output():
    """Identity pin so the frozen comparand cannot be swapped and silently re-baselined."""
    import hashlib
    assert M2_ROWS.exists(), M2_ROWS
    assert hashlib.sha256(M2_ROWS.read_bytes()).hexdigest() == M2_ROWS_SHA256


def test_acceptance_rederives_the_committed_report_rows_cleanly():
    """HARD acceptance over the FROZEN milestone-2 rows (L325 — was the live file)."""
    out = R.rederive(rows_path=M2_ROWS, n_boot=2000)
    assert out["rows"] == 40
    assert out["pnl_mismatches"] == 0
    assert out["untraced_fills"] == 0
    assert out["price_tag_violations"] == 0
    assert out["all_intervals"]["n_units"] == 7
    assert out["all_intervals"]["n_filled"] == 26
    assert out["all_intervals"]["fill_rate"] == pytest.approx(0.65)
    assert out["all_intervals"]["mean"] == pytest.approx(0.0445, abs=1e-9)
    assert out["all_intervals"]["admissible"] is False
    assert out["all_intervals"]["clears_tick"] is False
    assert out["row_level_interval_coverage"] == pytest.approx(0.85)


def test_acceptance_independent_ci_agrees_with_the_probe_within_resampling_noise():
    from scripts import q51_maker_fillsim as M
    report, _rows = M.run(n_boot=4000)
    probe = report["verdicts"]["all_intervals"]
    mine = R.rederive(n_boot=4000)["all_intervals"]
    assert mine["mean"] == pytest.approx(probe["mean"], abs=1e-9)
    assert mine["n_units"] == probe["n_units_games"]
    # both straddle zero — the CONCLUSION, not the exact bound, is what must agree
    assert mine["ci95"][0] < 0 < mine["ci95"][1]
    assert probe["ci95"][0] < 0 < probe["ci95"][1]


def test_a_non_binary_settlement_result_is_flagged_not_booked_as_a_loss_l52(tmp_path):
    out = R.rederive(_write(tmp_path, [_row(settle_result="scalar", pnl=0.0)]), n_boot=50)
    assert out["non_binary_result_fills"] == 1


def test_acceptance_no_non_binary_result_reached_a_scored_fill():
    assert R.rederive(n_boot=100)["non_binary_result_fills"] == 0


def test_acceptance_rederives_the_milestone_3_rows_cleanly():
    """The same independent re-derivation over MILESTONE 3's rows (fired 2026-08-10).

    This is the redundancy path the two-agent rule falls back to when no `verifier` subagent
    is dispatchable: an own-reader, own-fee, own-bootstrap re-derivation that never imports
    the probe. It shares the producer's premises (notably L279's `taker_book_side`
    orientation) and is therefore NOT a verification of those premises."""
    out = R.rederive(n_boot=2000)
    assert out["rows"] == 294
    assert out["pnl_mismatches"] == 0
    assert out["untraced_fills"] == 0
    assert out["price_tag_violations"] == 0
    assert out["all_intervals"]["n_units"] == 51
    assert out["all_intervals"]["n_filled"] == 64
    assert out["all_intervals"]["fill_rate"] == pytest.approx(64 / 294)
    assert out["all_intervals"]["mean"] == pytest.approx(0.010068027210884354, abs=1e-9)
    assert out["all_intervals"]["admissible"] is True
    assert out["all_intervals"]["n_opposing_units"] == 12
    assert out["all_intervals"]["clears_tick"] is False
    assert out["all_intervals"]["ci95"][0] < 0 < out["all_intervals"]["ci95"][1]
    assert out["row_level_interval_coverage"] == pytest.approx(58 / 147)
