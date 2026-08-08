"""Offline tests for scripts/q51_m3_fill_projection.py (Q51 milestone-3 fill projection).

No network. Two tiers:

  * UNIT tests over hand-built synthetic fixtures — leg enumeration and its three drop
    filters, the covered/uncovered split, the projection roll-up arithmetic, the marginal
    table, the compression identity, the calibration block's direction flag, and the
    orientation-is-a-parameter negative control.
  * HARD `test_acceptance_*` cases over the committed `dt=2026-08-03` slice.

WHICH ACCEPTANCE ASSERTIONS ARE EXACT AND WHY
---------------------------------------------
Following `tests/test_q51_m3_preflight.py`'s own rule. Everything sourced from
`tape/orderbook_depth/dt=2026-08-03.jsonl` is a DIRECTIONAL BOUND (`>=`): that day file is
past but not closed to growth — a legitimate LOOP-QUEUE step-0b stranded-branch sweep can
union-append snapshots, which raises interval, leg and fill counts. Per L280's enforcement
precedent, an acceptance test a legitimate tape sweep would break is a test that gets
deleted. What IS asserted exactly is the sign of every conclusion (the headline fill rate
falls below the covered-branch fill rate; the covered branch clears the L41 floor at the
08-10 firing; the redundancy cross-check disagrees on nothing), because more tape can only
be additive to those.

This module asserts NO mean, NO CI, NO P&L and NO settlement outcome: the projection
computes none, and `test_report_is_outcome_independent` pins that it never will.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import q51_m3_fill_projection as P
from scripts import q51_maker_fillsim as M


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _iso(minute: int) -> str:
    """A real RFC3339 instant. The fixtures must use parseable `captured_at` strings: the
    independent cross-check path re-derives its window from that string, not from `ts`."""
    return "2026-08-03T%02d:%02d:00Z" % (minute // 60, minute % 60)


def _snap(minute, yb=0.40, nb=0.55, ya=0.45):
    at = _iso(minute)
    return {"ts": M.parse_ts(at), "captured_at": at,
            "best_yes_bid": yb, "best_no_bid": nb, "best_yes_ask": ya}


def _print(minute, yes_price, side, trade_id="T1"):
    return {"ts": M.parse_ts(_iso(minute)), "yes_price": float(yes_price),
            "taker_book_side": side, "trade_id": trade_id, "count": 1.0}


def _write_cache(tmp_path: Path, markets: dict) -> Path:
    p = tmp_path / "settlement.json"
    p.write_text(json.dumps({"schema_version": "q51_settlement_cache.v1",
                             "price_source_tag": "broker_truth",
                             "markets": markets}), encoding="utf-8")
    P._CLOSE_TS_CACHE.clear()
    return p


def _legs(tmp_path, snaps, prints, markets, order=None):
    order = order or sorted(snaps)
    cache = _write_cache(tmp_path, markets)
    return P.enumerate_legs(cache_path=cache, depth=(order, snaps), prints=prints)


# --------------------------------------------------------------------------- #
# unit: enumeration + drop filters
# --------------------------------------------------------------------------- #
def test_two_snapshots_make_one_interval_and_two_legs(tmp_path):
    t = "KXMLBGAME-26AUG03NYABOS-NYA"
    legs = _legs(tmp_path,
                 {t: [_snap(0), _snap(10)]},
                 {},
                 {t: {"close_time": "2026-08-04T00:00:00Z"}})
    assert len(legs) == 2
    assert {x["side"] for x in legs} == {"yes_bid", "no_bid"}
    assert all(x["price_source_tag"] == "real_bid" for x in legs)
    assert all(x["filled"] is False for x in legs)


def test_single_snapshot_ticker_contributes_no_legs(tmp_path):
    t = "KXMLBGAME-26AUG03NYABOS-NYA"
    legs = _legs(tmp_path, {t: [_snap(0)]}, {},
                 {t: {"close_time": "2026-08-04T00:00:00Z"}})
    assert legs == []


def test_one_sided_book_interval_is_dropped(tmp_path):
    t = "KXMLBGAME-26AUG03NYABOS-NYA"
    legs = _legs(tmp_path,
                 {t: [_snap(0, yb=0.0), _snap(10)]},
                 {}, {t: {"close_time": "2026-08-04T00:00:00Z"}})
    assert legs == []


def test_post_close_entry_interval_is_dropped(tmp_path):
    t = "KXMLBGAME-26AUG03NYABOS-NYA"
    # close at epoch 0 -> the interval whose ENTRY snapshot is at ts=5 is post-close
    legs = _legs(tmp_path,
                 {t: [_snap(5), _snap(10)]},
                 {}, {t: {"close_time": "1970-01-01T00:00:00Z"}})
    assert legs == []


def test_non_sports_and_kxmve_tickers_are_excluded(tmp_path):
    """The population is the probe's own: the stride-13 sample FIRST, then sports `*GAME`
    with KXMVE* excluded (L31). The three named tickers are placed at sampled indices 0/13/26
    so the exclusion is what is being tested and not the stride."""
    good = "KXMLBGAME-26AUG03NYABOS-NYA"
    bad = "KXBTCD-26AUG0312-T50"
    mve = "KXMVEGAME-26AUG03NYABOS-NYA"
    order = [good] + ["KXFILLER-%02d-A" % i for i in range(12)] \
        + [bad] + ["KXFILLER-1%02d-A" % i for i in range(12)] + [mve]
    assert (order[0], order[13], order[26]) == (good, bad, mve)
    snaps = {k: [_snap(0), _snap(10)] for k in order}
    legs = _legs(tmp_path, snaps, {},
                 {k: {"close_time": "2026-08-04T00:00:00Z"} for k in order}, order=order)
    assert {x["ticker"] for x in legs} == {good}


def test_population_is_the_probes_stride_sample_not_every_ticker(tmp_path):
    """A sports market that the stride sample never selects contributes nothing — the
    denominator is milestone 1's sampled 200, not the day's 2,713 depth tickers."""
    sampled = "KXMLBGAME-26AUG03NYABOS-NYA"
    unsampled = "KXMLBGAME-26AUG03LADSFN-LAD"
    order = [sampled, unsampled]
    snaps = {k: [_snap(0), _snap(10)] for k in order}
    legs = _legs(tmp_path, snaps, {},
                 {k: {"close_time": "2026-08-04T00:00:00Z"} for k in order}, order=order)
    assert {x["ticker"] for x in legs} == {sampled}


def test_market_with_unparseable_close_time_gets_empty_close_day(tmp_path):
    t = "KXMLBGAME-26AUG03NYABOS-NYA"
    legs = _legs(tmp_path, {t: [_snap(0), _snap(10)]}, {},
                 {t: {"close_time": None}})
    assert [x["close_day"] for x in legs] == ["", ""]
    # and such a market is excluded from every dated projection row (never bucketed)
    assert P.project(legs, "2026-08-10")["n_legs" if False else "n_markets"] == 0


# --------------------------------------------------------------------------- #
# unit: fills, coverage, and the orientation parameter
# --------------------------------------------------------------------------- #
def test_yes_bid_fills_on_a_selling_taker_and_carries_broker_truth_evidence(tmp_path):
    t = "KXMLBGAME-26AUG03NYABOS-NYA"
    legs = _legs(tmp_path,
                 {t: [_snap(0, yb=0.40), _snap(10)]},
                 {t: [_print(5, 0.38, "ask", trade_id="TID-9")]},
                 {t: {"close_time": "2026-08-04T00:00:00Z"}})
    yes = [x for x in legs if x["side"] == "yes_bid"][0]
    assert yes["filled"] is True
    assert yes["fill_trade_id"] == "TID-9"
    assert yes["fill_evidence_tag"] == "broker_truth"
    assert yes["interval_covered"] is True


def test_a_fill_can_only_occur_inside_a_covered_interval(tmp_path):
    t = "KXMLBGAME-26AUG03NYABOS-NYA"
    legs = _legs(tmp_path,
                 {t: [_snap(0), _snap(10)]},
                 {t: [_print(99, 0.10, "ask")]},   # print outside the interval
                 {t: {"close_time": "2026-08-04T00:00:00Z"}})
    assert all(x["interval_covered"] is False for x in legs)
    assert all(x["filled"] is False for x in legs)


def test_independent_path_agrees_with_the_probe_on_a_fixture(tmp_path):
    t = "KXMLBGAME-26AUG03NYABOS-NYA"
    prints = {t: [_print(5, 0.38, "ask"), _print(6, 0.90, "bid")]}
    legs = _legs(tmp_path, {t: [_snap(0, yb=0.40, nb=0.05), _snap(10)]},
                 prints, {t: {"close_time": "2026-08-04T00:00:00Z"}})
    indep = P.independent_fill_decisions(legs, prints=prints)
    assert indep == [x["filled"] for x in legs]


def test_orientation_is_a_parameter_not_a_hardcoded_literal(tmp_path):
    """The L279 negative control: swapping the orientation arguments must change decisions.
    If it did not, the independent path would be reading a constant, not the field."""
    t = "KXMLBGAME-26AUG03NYABOS-NYA"
    prints = {t: [_print(5, 0.38, "ask")]}
    legs = _legs(tmp_path, {t: [_snap(0, yb=0.40, nb=0.05), _snap(10)]},
                 prints, {t: {"close_time": "2026-08-04T00:00:00Z"}})
    normal = P.independent_fill_decisions(legs, prints=prints)
    flipped = P.independent_fill_decisions(legs, prints=prints,
                                           taker_buys="ask", taker_sells="bid")
    assert normal != flipped


# --------------------------------------------------------------------------- #
# unit: projection roll-up
# --------------------------------------------------------------------------- #
def _synthetic_rows():
    return [
        {"ticker": "KXG-1-A", "game": "KXG-1", "close_day": "2026-08-04", "side": "yes_bid",
         "entry_captured_at": "e1", "next_captured_at": "n1", "rest_price": 0.4,
         "price_source_tag": "real_bid", "interval_covered": True, "filled": True,
         "fill_trade_id": "x", "fill_evidence_tag": "broker_truth"},
        {"ticker": "KXG-1-A", "game": "KXG-1", "close_day": "2026-08-04", "side": "no_bid",
         "entry_captured_at": "e1", "next_captured_at": "n1", "rest_price": 0.5,
         "price_source_tag": "real_bid", "interval_covered": True, "filled": False,
         "fill_trade_id": None, "fill_evidence_tag": None},
        {"ticker": "KXG-2-B", "game": "KXG-2", "close_day": "2026-08-10", "side": "yes_bid",
         "entry_captured_at": "e2", "next_captured_at": "n2", "rest_price": 0.4,
         "price_source_tag": "real_bid", "interval_covered": False, "filled": False,
         "fill_trade_id": None, "fill_evidence_tag": None},
        {"ticker": "KXG-2-B", "game": "KXG-2", "close_day": "2026-08-10", "side": "no_bid",
         "entry_captured_at": "e2", "next_captured_at": "n2", "rest_price": 0.5,
         "price_source_tag": "real_bid", "interval_covered": False, "filled": False,
         "fill_trade_id": None, "fill_evidence_tag": None},
    ]


def test_projection_is_cumulative_by_close_day():
    rows = _synthetic_rows()
    early = P.project(rows, "2026-08-04")
    late = P.project(rows, "2026-08-10")
    assert early["n_units_games"] == 1 and early["all_intervals"]["n_legs"] == 2
    assert late["n_units_games"] == 2 and late["all_intervals"]["n_legs"] == 4


def test_uncovered_legs_are_counted_structurally_unfillable():
    late = P.project(_synthetic_rows(), "2026-08-10")
    assert late["all_intervals"]["n_structurally_unfillable_legs"] == 2
    assert late["covered_intervals"]["n_legs"] == 2
    assert late["all_intervals"]["fill_rate"] == 0.25
    assert late["covered_intervals"]["fill_rate"] == 0.5


def test_interval_counts_are_intervals_not_halved_legs():
    """A one-sided book drops the whole interval, so legs/2 is not always the interval
    count; the projection counts distinct (ticker, entry) pairs directly."""
    late = P.project(_synthetic_rows(), "2026-08-10")
    assert late["n_scored_intervals"] == 2
    assert late["n_covered_intervals"] == 1


def test_marginal_table_reports_legs_and_fills_bought_by_waiting():
    rows = [P.project(_synthetic_rows(), d) for d in ("2026-08-04", "2026-08-10")]
    m = P.marginal_table(rows)
    assert len(m) == 1
    assert m[0]["d_legs"] == 2 and m[0]["d_fills"] == 0
    assert m[0]["marginal_fill_rate"] == 0.0


def test_compression_reports_the_identity_and_refuses_to_multiply_it():
    rows = [P.project(_synthetic_rows(), d) for d in ("2026-08-04", "2026-08-10")]
    c = P.compression(rows, "2026-08-04", "2026-08-10")
    assert c["all_intervals_compression_x"] == 2.0
    assert "explicitly_not_computed" in c
    assert "0.0" in c["identity"]


def test_compression_on_a_missing_fire_date_is_empty_not_an_error():
    rows = [P.project(_synthetic_rows(), "2026-08-04")]
    assert P.compression(rows, "2026-08-04", "1999-01-01") == {}


# --------------------------------------------------------------------------- #
# unit: calibration + drops audit
# --------------------------------------------------------------------------- #
def test_calibration_is_empty_when_the_observed_report_is_absent(tmp_path):
    rows = [P.project(_synthetic_rows(), "2026-08-04")]
    assert P.calibration_vs_milestone_2(rows, observed_report=tmp_path / "nope.json") == {}


def test_calibration_flags_mixed_when_the_upper_bound_is_violated(tmp_path):
    obs = tmp_path / "obs.json"
    obs.write_text(json.dumps({
        "intervals": {"n_intervals": 99, "n_covered_intervals": 99},
        "verdicts": {"all_intervals": {"n_legs": 99, "n_filled_legs": 99,
                                       "n_units_games": 99}}}), encoding="utf-8")
    rows = [P.project(_synthetic_rows(), "2026-08-04")]
    cal = P.calibration_vs_milestone_2(rows, observed_report=obs)
    assert cal["direction"].startswith("MIXED")


def test_drops_unit_audit_names_the_mixed_units_explicitly():
    a = P.drops_unit_audit()
    assert a["keys_counting_tickers"] == ["single_snapshot"]
    assert "unsettled" in a["keys_counting_intervals"]
    assert "UNCHANGED" in a["repair_status"]


# --------------------------------------------------------------------------- #
# acceptance: committed tape
# --------------------------------------------------------------------------- #
def _report():
    if not hasattr(_report, "_cached"):
        _report._cached = P.run()
    return _report._cached


def test_acceptance_report_is_outcome_independent():
    """The load-bearing discipline: this instrument may never become a P&L forecast."""
    blob = json.dumps(_report()).lower()
    for token in ("\"pnl\"", "\"ci95\"", "\"won\"", "\"settle_result\"",
                  "queue_position", "time_to_fill"):
        assert token not in blob, token
    assert _report()["outcome_independent"] is True


def test_acceptance_no_leg_record_carries_an_outcome_or_a_pnl():
    legs = P.enumerate_legs()
    assert legs, "committed tape produced no legs"
    for k in ("won", "pnl", "settle_result", "result"):
        assert all(k not in leg for leg in legs), k


def test_acceptance_redundancy_cross_check_disagrees_on_nothing():
    rc = _report()["redundancy_check"]
    assert rc["n_disagreements"] == 0
    assert rc["n_legs_cross_checked"] >= 330
    assert rc["is_a_verifier"] is False


def test_acceptance_0810_population_matches_the_preflight_directionally():
    row = {r["fire_date"]: r for r in _report()["projections"]}["2026-08-10"]
    assert row["n_units_games"] >= 44
    assert row["n_scored_intervals"] >= 128
    assert row["all_intervals"]["n_legs"] >= 256
    assert row["all_intervals"]["n_fills"] >= 76


def test_acceptance_headline_fill_rate_falls_below_the_covered_branch_at_0810():
    """The finding: the headline fill rate is a property of the SETTLED SUBSET, not of the
    mechanism. More tape can only add legs, so the gap can only widen."""
    row = {r["fire_date"]: r for r in _report()["projections"]}["2026-08-10"]
    assert row["all_intervals"]["fill_rate"] < row["covered_intervals"]["fill_rate"]
    assert row["all_intervals"]["fill_rate"] < 0.40
    assert row["covered_intervals"]["fill_rate"] > 0.55


def test_acceptance_covered_branch_clears_the_l41_floor_at_0810():
    row = {r["fire_date"]: r for r in _report()["projections"]}["2026-08-10"]
    assert row["covered_intervals"]["n_units_games"] >= M.MIN_UNITS


def test_acceptance_compression_multiplier_is_material():
    c = _report()["compression_m2_to_0810"]
    assert c["all_intervals_compression_x"] > 1.5
    assert c["covered_intervals_compression_x"] < c["all_intervals_compression_x"]


def test_acceptance_waiting_past_0810_buys_units_but_almost_no_fills():
    marg = {(m["from"], m["to"]): m for m in _report()["marginal"]}
    late = marg[("2026-08-12", "2026-08-23")]
    assert late["d_units_games"] >= 1
    assert late["marginal_fill_rate"] < 0.15


def test_acceptance_the_close_day_proxy_is_an_upper_bound_on_milestone_2():
    cal = _report()["calibration_vs_milestone_2"]
    assert cal["direction"] == "over-inclusive"
    assert all(v >= 0 for v in cal["delta_projected_minus_observed"].values())
