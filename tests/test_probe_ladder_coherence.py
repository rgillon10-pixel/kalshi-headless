"""Offline unit tests for the pure math in scripts/probe_ladder_coherence.py (W-D probe).

No DB, no network — pins the ladder-key parse, the (a)/(b) arb algebra, the derived-price
identities, and the run-collapse duration/depth logic. The read-only tape scan itself
follows the analysis-script precedent (no live-DB test), but every price primitive it uses
is pinned here.
"""
import importlib.util
import os

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "scripts", "probe_ladder_coherence.py")
_spec = importlib.util.spec_from_file_location("probe_ladder_coherence", _PATH)
plc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plc)

from core.pricing import fee_per_contract  # noqa: E402


def test_ladder_key_strips_final_bracket_segment():
    assert plc.ladder_key("KXHIGHTBOS-26APR17-B65.5") == "KXHIGHTBOS-26APR17"
    assert plc.ladder_key("KXHIGHTBOS-26APR17-T65") == "KXHIGHTBOS-26APR17"
    assert plc.ladder_key("KXLOWTLAX-26APR17-B50.5") == "KXLOWTLAX-26APR17"
    # bracket labels use '.', never '-', so a single rsplit is unambiguous
    assert plc.ladder_key("KXLOWTCHI-26APR16-T56") == "KXLOWTCHI-26APR16"


def test_to_float_handles_empty_and_none():
    assert plc._to_float("0.6100") == 0.61
    assert plc._to_float(None) is None
    assert plc._to_float("") is None
    assert plc._to_float("garbage") is None
    assert plc._to_float("0.0000") == 0.0


def test_yes_ladder_arb_no_arb_with_overround():
    # a normal 6-bracket ladder with ~7c overround: sum_ask 1.07 => net strongly negative
    asks = [0.69, 0.13, 0.11, 0.07, 0.04, 0.03]
    r = plc.yes_ladder_arb(asks)
    assert abs(r["sum_ask"] - 1.07) < 1e-9
    assert r["net"] < 0  # no arb: pay > $1 for a $1 payout, plus fees


def test_yes_ladder_arb_positive_only_when_deep_under_a_dollar():
    # sum_ask 0.90 => raw underpricing, but 6 legs of >=1c fee (~6-8c) still matter
    asks = [0.50, 0.12, 0.10, 0.08, 0.06, 0.04]
    r = plc.yes_ladder_arb(asks)
    assert abs(r["sum_ask"] - 0.90) < 1e-9
    # fees are the sum of per-leg fee_per_contract at the taker rate
    expected_fees = sum(fee_per_contract(a) for a in asks)
    assert abs(r["fees"] - expected_fees) < 1e-12
    assert abs(r["net"] - (1.0 - 0.90 - expected_fees)) < 1e-12
    assert r["net"] > 0  # deep enough under $1 to clear the fee floor here


def test_no_ladder_arb_algebra_matches_yesbid_identity():
    # net_b should equal sum(yes_bid) - 1 - fees_b exactly
    yes_bids = [0.67, 0.12, 0.09, 0.06, 0.03, 0.02]
    n = 6
    r = plc.no_ladder_arb(yes_bids, n)
    no_asks = [1.0 - b for b in yes_bids]
    expected_fees = sum(fee_per_contract(a) for a in no_asks)
    assert abs(r["fees"] - expected_fees) < 1e-12
    assert abs(r["net"] - (sum(yes_bids) - 1.0 - expected_fees)) < 1e-12
    # this ladder's yes bids sum to 0.99 < 1 => selling the ladder loses => no arb
    assert r["net"] < 0


def test_no_ladder_arb_positive_when_bids_sum_above_one():
    yes_bids = [0.70, 0.20, 0.18, 0.10, 0.08, 0.05]  # sum 1.31
    r = plc.no_ladder_arb(yes_bids, 6)
    assert sum(yes_bids) > 1.0
    assert r["net"] > 0


def test_runs_collapse_consecutive_and_flag_executable():
    # class 'a': three consecutive net>0 snaps with depth>=10 => one executable run
    per_snap = [
        {"ts": "t0", "dt_s": 60.0, "a_net": 0.02, "a_min_depth": 50.0},
        {"ts": "t1", "dt_s": 60.0, "a_net": 0.03, "a_min_depth": 12.0},
        {"ts": "t2", "dt_s": 60.0, "a_net": 0.01, "a_min_depth": 40.0},
        {"ts": "t3", "dt_s": 60.0, "a_net": -0.01, "a_min_depth": 40.0},  # breaks run
        {"ts": "t4", "dt_s": 0.0, "a_net": 0.05, "a_min_depth": 3.0},     # thin, 1 snap
    ]
    runs = plc._runs(per_snap, "a")
    assert len(runs) == 2
    r0, r1 = runs
    assert r0["snaps"] == 3 and r0["min_depth"] == 12.0
    assert r0["entry_net"] == 0.02 and r0["peak_net"] == 0.03
    assert r0["executable"] is True
    # second run: single snapshot, depth 3 => fails BOTH duration and depth gates
    assert r1["snaps"] == 1 and r1["executable"] is False


def test_runs_single_deep_snapshot_fails_duration_gate():
    # deep depth but only 1 consecutive snapshot => not executable (MIN_SNAPS=2)
    per_snap = [{"ts": "t0", "dt_s": 10.0, "a_net": 0.10, "a_min_depth": 9999.0},
                {"ts": "t1", "dt_s": 0.0, "a_net": -0.05, "a_min_depth": 10.0}]
    runs = plc._runs(per_snap, "a")
    assert len(runs) == 1 and runs[0]["executable"] is False


def test_leg_prices_marks_absent_bid_side_unexecutable():
    members = ["m1", "m2"]
    state = {
        "m1": {"yes_ask": 0.10, "yes_ask_size": 20.0, "yes_bid": 0.09, "yes_bid_size": 5.0},
        # m2 has no resting yes bid (price 0) => NO leg unfillable (L26 mirror)
        "m2": {"yes_ask": 0.90, "yes_ask_size": 30.0, "yes_bid": 0.0, "yes_bid_size": 0.0},
    }
    ya, yas, yb, ybs, ask_ok, bid_ok = plc._leg_prices(state, members)
    assert ask_ok is True     # both asks fillable
    assert bid_ok is False    # m2 bid absent
