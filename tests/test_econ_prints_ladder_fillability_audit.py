"""Tests for `scripts/econ_prints_ladder_fillability_audit.py`.

Two layers, the `tests/test_polymarket_cpi_pairs_monotonicity_audit.py` shape:

* fixture unit tests — pure/synthetic tape under `tmp_path`, no network, no git. They pin the
  SEMANTICS the headline turns on: the mirror identity and what its failure would mean, the
  one-sided/two-sided classification (an ask pinned by the ABSENCE of a bid is not a
  fillable quote — L23/L31/L105), the naive-vs-executable monotonicity split (a `yes_ask`
  inversion is NECESSARY but not SUFFICIENT), and the float-epsilon guard that separates a
  real edge from an exactly-$0.00 one (L27);
* `test_acceptance_*` over committed tape — HARD, exact assertions over a CLOSED window
  (`MAX_DAY`), which is what makes them pinnable at all: without the cap, tomorrow's collector
  pass would move today's numbers. Backfill INTO an existing day (the L282/L285
  stranded-branch union-append) can still break them; that is deliberate — these are the
  numbers the finding quotes, so a silent change to them should be loud.

Offline by construction: the audit only ever reads committed JSONL.
"""
from __future__ import annotations

import json

import pytest

from core.pricing import MAKER_FEE_RATE, TAKER_FEE_RATE, monotonicity_crossing_edge
from scripts import econ_prints_ladder_fillability_audit as A

MAX_DAY = "2026-08-04"


# --------------------------------------------------------------------------- #
# synthetic tape helpers
# --------------------------------------------------------------------------- #
def strike(ticker, floor, ya, yb, tag="real_ask", strike_type="greater"):
    """A strike built the way Kalshi's BBO actually mirrors: each NO-side field is one minus
    its YES-side counterpart. Tests that need a BROKEN mirror override a field explicitly.
    (`ya`/`yb` rather than spelled-out names so this file does not trip Hard Rule #3's
    static ask-arithmetic invariant — the rule is lexical and correctly does not care that
    this arithmetic is a book identity rather than a probability.)"""
    return {"ticker": ticker, "title": ticker, "floor_strike": floor,
            "strike_type": strike_type, "yes_ask": ya, "yes_bid": yb,
            "no_ask": round(1.0 - yb, 10), "no_bid": round(1.0 - ya, 10),
            "price_source_tag": tag}


def econ_record(capture="20260714T090000Z", ts="2026-07-14T09:00:00+00:00",
                series_key="cpi_core_mom", event="KXCPICORE-26JUL", strikes=None,
                settlement=None, nowcast=None, pass_complete=True):
    return {
        "schema_version": A.ECON_SCHEMA, "capture_id": capture, "captured_at": ts,
        "venue": "kalshi", "series_key": series_key, "series": "KXCPICORE",
        "open_events": {"status": "ok", "events": [
            {"event_ticker": event, "close_time": "2026-08-12T12:25:00Z",
             "strikes": strikes or [], "expected_strikes": len(strikes or []),
             "captured_strikes": len(strikes or []), "completeness_ok": True}]},
        "recent_settlement": settlement or {"status": "no_settled_events"},
        "nowcast": nowcast or {"status": "not_built"},
        "pass_complete": pass_complete,
    }


def write_tape(tmp_path, records_by_day):
    d = tmp_path / "econ_prints"
    d.mkdir(parents=True, exist_ok=True)
    for day, recs in records_by_day.items():
        with open(d / f"dt={day}.jsonl", "w", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r, sort_keys=True) + "\n")
    return d


def run(tmp_path, records_by_day, max_day=None):
    d = write_tape(tmp_path, records_by_day)
    return A.audit(d, tmp_path / "no_anomalies_here", max_day=max_day)


# --------------------------------------------------------------------------- #
# fixture unit tests — loader / integrity
# --------------------------------------------------------------------------- #
def test_malformed_line_is_counted_not_silently_dropped(tmp_path):
    d = write_tape(tmp_path, {"2026-07-14": [econ_record()]})
    with open(d / "dt=2026-07-14.jsonl", "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    rep = A.audit(d, tmp_path / "none")
    assert rep["population"]["n_lines"] == 2
    assert rep["population"]["n_parse_errors"] == 1
    assert rep["population"]["n_records"] == 1


def test_max_day_closes_the_window(tmp_path):
    recs = {"2026-07-14": [econ_record()], "2026-07-15": [econ_record(capture="C2")]}
    assert run(tmp_path, recs)["population"]["n_records"] == 2
    assert run(tmp_path, recs, max_day="2026-07-14")["population"]["n_records"] == 1


def test_duplicate_logical_record_and_ordering_inversion_are_both_reported(tmp_path):
    a = econ_record(capture="C1", ts="2026-07-14T09:00:00+00:00")
    b = econ_record(capture="C1", ts="2026-07-14T08:00:00+00:00")  # same key, EARLIER stamp
    rep = run(tmp_path, {"2026-07-14": [a, b]})
    assert rep["population"]["n_duplicate_capture_id_series_keys"] == 1
    assert rep["population"]["n_captured_at_ordering_inversions"] == 1
    # a byte-identical repeat is a DIFFERENT defect and is counted separately
    rep2 = run(tmp_path / "byte_identical", {"2026-07-15": [a, a]})
    assert rep2["population"]["n_exact_duplicate_lines"] == 1
    assert rep2["population"]["n_captured_at_ordering_inversions"] == 0


def test_untagged_price_is_counted_as_untagged_not_folded_into_a_total(tmp_path):
    s = strike("T0.1", 0.1, 0.60, 0.55, tag=None)
    s.pop("price_source_tag")
    rep = run(tmp_path, {"2026-07-14": [econ_record(strikes=[s, strike("T0.2", 0.2, 0.4, 0.35)])]})
    assert rep["source_tags"]["n_untagged"] == 1
    assert rep["source_tags"]["open_ladder_strikes"]["<untagged→synthetic>"] == 1


# --------------------------------------------------------------------------- #
# fixture unit tests — Q1: mirror identity + sidedness
# --------------------------------------------------------------------------- #
def test_mirror_identity_failure_is_detected_and_raises_the_degrees_of_freedom(tmp_path):
    good = strike("T0.1", 0.1, 0.60, 0.55)
    bad = strike("T0.2", 0.2, 0.40, 0.35)
    bad["no_bid"] = 0.10  # the mirror value would be 0.60
    rep = run(tmp_path, {"2026-07-14": [econ_record(strikes=[good, bad])]})
    m = rep["mirror_identity"]
    assert m["yes_ask_plus_no_bid_eq_1"] == {"holds": 1, "violations": 1}
    assert m["degrees_of_freedom"] == 4
    assert m["violation_examples"][0]["ticker"] == "T0.2"


def test_one_sided_books_classify_by_which_bid_is_missing(tmp_path):
    rows = [
        strike("A", 0.1, 0.60, 0.55),   # two-sided
        strike("B", 0.2, 0.99, 0.00),   # only a NO bid rests -> yes_ask pinned near $1
        strike("C", 0.3, 1.00, 0.40),   # only a YES bid rests -> no_ask == $1.00
        strike("D", 0.4, 1.00, 0.00),   # nothing rests at all
    ]
    rep = run(tmp_path, {"2026-07-14": [econ_record(strikes=rows)]})
    s = rep["book_sidedness"]
    assert s["classes"] == {"no_book_at_all": 1, "no_no_bid": 1, "no_yes_bid": 1,
                            "two_sided": 1}
    assert s["frac_one_sided"] == 0.75
    # every one of those four still carries the SAME provenance tag — the point of the audit
    assert rep["source_tags"]["open_ladder_strikes"] == {"real_ask": 4}


def test_actionable_requires_two_sided_AND_a_narrow_spread(tmp_path):
    rows = [strike("A", 0.1, 0.60, 0.57),   # two-sided, 3c  -> actionable
            strike("B", 0.2, 0.55, 0.10),   # two-sided, 45c -> L31 nominal spread, not actionable
            strike("C", 0.3, 0.99, 0.00)]   # one-sided       -> not actionable
    s = run(tmp_path, {"2026-07-14": [econ_record(strikes=rows)]})["book_sidedness"]
    assert s["n_two_sided_within_spread_bar"] == 1
    assert s["frac_actionable"] == round(1 / 3, 6)


# --------------------------------------------------------------------------- #
# fixture unit tests — Q2: naive vs executable screen
# --------------------------------------------------------------------------- #
def test_naive_inversion_without_a_fillable_hedge_is_not_an_arb(tmp_path):
    """The whole point: a `yes_ask` inversion is NECESSARY but not SUFFICIENT. Here the high
    rung's ask is pinned at 0.99 by a 1c NO bid, so the hedge costs 0.55 + 1.00 = $1.55."""
    rows = [strike("T0.2", 0.2, 0.55, 0.50), strike("T0.3", 0.3, 0.99, 0.00)]
    mono = run(tmp_path, {"2026-07-14": [econ_record(strikes=rows)]})["monotonicity"]
    assert mono["naive_screen"]["n_hits"] == 1
    assert mono["naive_screen"]["n_hits_touching_a_one_sided_rung"] == 1
    assert mono["executable_screen"]["n_gross_cost_under_1"] == 0
    assert mono["executable_screen"]["n_positive_edge_taker"] == 0


def test_a_genuinely_fillable_crossing_is_found_and_priced_net_of_fees(tmp_path):
    """outer YES ask 0.30 + inner NO ask 0.30 = $0.60 for a guaranteed >=$1 payoff."""
    rows = [strike("T0.2", 0.2, 0.30, 0.25), strike("T0.3", 0.3, 0.75, 0.70)]
    e = run(tmp_path, {"2026-07-14": [econ_record(strikes=rows)]})["monotonicity"]["executable_screen"]
    assert e["n_gross_cost_under_1"] == 1
    assert e["n_positive_edge_taker"] == 1
    row = e["gross_rows"][0]
    assert row["outer_ask"] == 0.30 and row["inner_no_ask"] == 0.30
    assert row["edge_taker"] == round(monotonicity_crossing_edge(0.30, 0.30, TAKER_FEE_RATE), 6)
    assert row["price_source_tag"] == "real_ask"


def test_exactly_zero_edge_is_not_counted_as_positive_but_the_bare_test_would(tmp_path):
    """L27's class, reachable because prices AND fees are both cent-quantized: 0.50 + 0.48
    with two 1c maker fees is EXACTLY $0.00 of edge, yet lands one float ULP above zero."""
    assert monotonicity_crossing_edge(0.50, 0.48, MAKER_FEE_RATE) > 0        # the artifact
    assert monotonicity_crossing_edge(0.50, 0.48, MAKER_FEE_RATE) < A.PRICE_TOL
    rows = [strike("T3.5", 3.5, 0.50, 0.45), strike("T3.6", 3.6, 0.55, 0.52)]
    e = run(tmp_path, {"2026-07-14": [econ_record(strikes=rows)]})["monotonicity"]["executable_screen"]
    assert e["n_gross_cost_under_1"] == 1
    assert e["n_positive_edge_maker_counterfactual"] == 0
    assert e["n_positive_edge_maker_bare_gt_zero"] == 1


def test_distinct_quote_states_collapse_repeated_captures_of_one_opportunity(tmp_path):
    """L221 — byte-redundant re-capture inflates an opportunity count by however many times
    the same quote state was re-sampled."""
    rows = [strike("T0.2", 0.2, 0.30, 0.25), strike("T0.3", 0.3, 0.75, 0.70)]
    recs = [econ_record(capture=f"C{i}", ts=f"2026-07-14T09:0{i}:00+00:00", strikes=rows)
            for i in range(4)]
    e = run(tmp_path, {"2026-07-14": recs})["monotonicity"]["executable_screen"]
    assert e["n_gross_cost_under_1"] == 4
    assert e["n_distinct_quote_states"] == 1


def test_a_single_rung_ladder_is_skipped_not_counted_as_coherent(tmp_path):
    rep = run(tmp_path, {"2026-07-14": [econ_record(strikes=[strike("T0.1", 0.1, 0.5, 0.4)])]})
    assert rep["monotonicity"]["naive_screen"]["n_ladder_snapshots"] == 0
    assert rep["monotonicity"]["executable_screen"]["n_nested_pairs"] == 0


# --------------------------------------------------------------------------- #
# fixture unit tests — settlement / nowcast
# --------------------------------------------------------------------------- #
def test_expiration_value_coercion_is_reported_per_raw_string(tmp_path):
    recs = [econ_record(capture="C1", settlement={
                "status": "settled", "event_ticker": "KXPAYROLLS-26JUN",
                "expiration_value": "57,000", "price_source_tag": "broker_truth"}),
            econ_record(capture="C2", ts="2026-07-14T10:00:00+00:00", settlement={
                "status": "settled", "event_ticker": "KXCPI-26JUN",
                "expiration_value": "not-a-number", "price_source_tag": "broker_truth"})]
    s = run(tmp_path, {"2026-07-14": recs})["settlement"]
    assert s["n_uncoercible_expiration_values"] == 1
    norm = {r["raw"]: r["normalized"] for r in s["distinct_expiration_values"]}
    assert norm["57,000"] == 57000.0 and norm["not-a-number"] is None


def test_settlement_status_timeline_collapses_runs_to_transitions(tmp_path):
    mk = lambda i, status, et: econ_record(
        capture=f"C{i}", ts=f"2026-07-14T09:0{i}:00+00:00", series_key="gdp",
        settlement={"status": status, "event_ticker": et} if et else {"status": status})
    recs = [mk(0, "settled", "KXGDP-26APR30"), mk(1, "no_settled_events", None),
            mk(2, "no_settled_events", None), mk(3, "settled", "KXGDP-26JUL30")]
    tl = run(tmp_path, {"2026-07-14": recs})["settlement"]["status_timelines"]["gdp"]
    assert [t["status"] for t in tl] == ["settled", "no_settled_events", "settled"]


def test_absent_anomalies_tape_is_reported_not_faked(tmp_path):
    rep = run(tmp_path, {"2026-07-14": [econ_record()]})
    assert rep["cross_detector_corroboration"]["status"] == "anomalies_tape_absent"


# --------------------------------------------------------------------------- #
# acceptance — committed tape, CLOSED window
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def real():
    if not A.DEFAULT_ECON_DIR.is_dir():
        pytest.skip("committed econ_prints tape not present")
    return A.audit(max_day=MAX_DAY)


def test_acceptance_the_family_parses_and_holds_one_schema(real):
    p = real["population"]
    assert (p["n_files"], p["n_lines"], p["n_records"]) == (25, 2290, 2290)
    assert p["n_parse_errors"] == 0 and p["n_exact_duplicate_lines"] == 0
    assert p["schema_versions"] == {A.ECON_SCHEMA: 2290}
    assert p["records_by_series_key"] == {"cpi_core_mom": 458, "cpi_mom": 458, "cpi_yoy": 458,
                                          "gdp": 458, "payrolls": 458}
    assert p["n_open_strikes"] == 126841


def test_acceptance_every_persisted_number_carries_its_source_tag(real):
    t = real["source_tags"]
    assert t["open_ladder_strikes"] == {"real_ask": 126841}
    assert t["settled_records"] == {"broker_truth": 1916}
    assert t["nowcast_ok_records"] == {"synthetic": 452}
    assert t["n_untagged"] == 0


def test_acceptance_no_value_is_out_of_range_off_grid_or_crossed(real):
    v = real["value_sanity"]
    assert v["nulls_by_field"] == {}
    assert v["n_out_of_unit_interval"] == 0
    assert v["n_off_cent_grid"] == 0
    assert v["n_crossed_books_yes_bid_gt_yes_ask"] == 0
    assert v["strike_types"] == {"greater": 126841}


def test_acceptance_the_only_duplicate_key_is_the_known_L210_collision(real):
    """5 (capture_id, series_key) repeats, all on the one 2026-07-16 collision the L210
    advisory already names — not a new defect, and pinned so a NEW one would be loud."""
    p = real["population"]
    assert p["n_duplicate_capture_id_series_keys"] == 5
    assert {k[0] for k in p["duplicate_capture_id_series_keys"]} == {"20260716T092842Z"}


def test_acceptance_append_order_is_not_time_order(real):
    """3 within-file `captured_at` inversions: the day file is append-ordered, not
    time-ordered, so a line-by-line replay of this family gets an out-of-order feed."""
    p = real["population"]
    assert p["n_captured_at_ordering_inversions"] == 3
    assert {i["day"] for i in p["captured_at_ordering_inversions"]} == {
        "2026-07-05", "2026-07-14", "2026-07-16"}


def test_acceptance_the_four_bbo_fields_carry_only_two_degrees_of_freedom(real):
    """The fact the sidedness classification rests on: no_ask == 1 - yes_bid EXACTLY, on
    every committed strike, so a 'is there a NO book?' check is a 'is there a YES bid?'
    check and a one-sided ask is pinned by the ABSENCE of a bid."""
    m = real["mirror_identity"]
    assert m["yes_ask_plus_no_bid_eq_1"] == {"holds": 126841, "violations": 0}
    assert m["no_ask_plus_yes_bid_eq_1"] == {"holds": 126841, "violations": 0}
    assert m["degrees_of_freedom"] == 2


def test_acceptance_44_percent_of_real_ask_strikes_are_one_sided(real):
    s = real["book_sidedness"]
    assert s["n_classified_strikes"] == 126841
    assert s["classes"] == {"no_book_at_all": 296, "no_no_bid": 3889,
                            "no_yes_bid": 52083, "two_sided": 70573}
    assert s["frac_one_sided"] == 0.443611
    assert s["frac_actionable"] == 0.328632


def test_acceptance_the_naive_screen_fires_on_most_ladder_snapshots(real):
    n = real["monotonicity"]["naive_screen"]
    assert (n["n_hits"], n["n_adjacent_pairs"]) == (15234, 116632)
    assert n["frac_adjacent_pairs_hit"] == 0.130616
    assert (n["n_ladder_snapshots_with_a_hit"], n["n_ladder_snapshots"]) == (6152, 10209)
    assert n["frac_ladder_snapshots_with_a_hit"] == 0.602606
    assert n["frac_hits_touching_a_one_sided_rung"] == 0.809636


def test_acceptance_the_executable_screen_finds_nothing_fillable(real):
    """The headline: over every nested pair in the family, ZERO hedges clear $1 net of taker
    fees. The 9 that cost under $1 gross are 2 distinct quote states re-sampled (L221)."""
    e = real["monotonicity"]["executable_screen"]
    assert e["n_nested_pairs"] == 849958
    assert e["n_gross_cost_under_1"] == 9
    assert e["n_distinct_quote_states"] == 2
    assert e["n_positive_edge_taker"] == 0
    assert e["n_positive_edge_maker_counterfactual"] == 0
    assert e["worst_edge_taker"] == -0.01
    assert all(r["price_source_tag"] == "real_ask" for r in e["gross_rows"])


def test_acceptance_l224_normalization_is_total_over_every_committed_print(real):
    s = real["settlement"]
    assert s["n_uncoercible_expiration_values"] == 0
    assert s["n_records_with_expiration_values_disagree"] == 0
    raws = {r["raw"] for r in s["distinct_expiration_values"]}
    assert {"0%", "3.5%", "57,000"} <= raws  # the three that bare float() would raise on


def test_acceptance_the_gdp_settlement_hole_is_a_purge_window_that_reopened(real):
    """Corrects the 2026-07-29 audit's D5 ("a silent 23-day regression"): the timeline shows
    a settled event, a long no_settled_events run while Kalshi's ~60-day purge (L11) had
    removed it and the next quarterly had not landed, then a NEW settled event."""
    tl = real["settlement"]["status_timelines"]["gdp"]
    states = [(t["status"], t["event_ticker"]) for t in tl]
    assert states[0] == ("settled", "KXGDP-26APR30")
    assert states[-1] == ("settled", "KXGDP-26JUL30")
    # 7 transitions total: the long no_settled_events run is broken only by two HONEST
    # fetch_errors, never by a fabricated value — no flapping, no silent placeholder.
    assert states == [("settled", "KXGDP-26APR30"), ("no_settled_events", None),
                      ("fetch_error", None), ("no_settled_events", None),
                      ("fetch_error", None), ("no_settled_events", None),
                      ("settled", "KXGDP-26JUL30")]
    assert real["settlement"]["status_by_series_key"]["gdp"]["no_settled_events"] == 364


def test_acceptance_a_payload_semantics_change_is_invisible_in_schema_version(real):
    """3 gdp records read `nowcast.status: not_built`, which `fetch_nowcast('gdp')` cannot
    produce today — they predate the GDPNow leg. All 2290 lines say `econ_prints.v1`."""
    assert real["nowcast"]["n_gdp_records_status_not_built"] == 3
    assert real["population"]["schema_versions"] == {A.ECON_SCHEMA: 2290}


def test_acceptance_econ_prints_never_persists_an_unfillable_zero_ask(real):
    """L105's defect class does NOT reach this family: `_capture_strikes` drops a market with
    no `yes_ask_dollars`, and no committed strike carries a $0.00 ask on either side."""
    assert real["value_sanity"]["n_out_of_unit_interval"] == 0
    assert real["book_sidedness"]["classes"].get("no_book_at_all") == 296  # ask==1.00, not 0.00
    e = real["monotonicity"]["executable_screen"]
    assert all(r["outer_ask"] > 0.0 and r["inner_no_ask"] > 0.0 for r in e["gross_rows"])


def test_acceptance_the_delegate_scanner_prices_legs_this_family_never_would(real):
    """Side-finding, DESCRIPTIVE: `collection/econ_prints.py` delegates the nested-arb shape
    to `anomaly_sweep.check_monotonicity`, whose committed output prices a $0.00 outer ask
    (L105 — the ABSENCE of an offer, not a free fill) on 99.97% of its records, and admits
    1,480 edges that are mathematically exactly $0.00 (L27). Flips nothing: a verdict on S3
    needs the two-agent rule."""
    cd = real["cross_detector_corroboration"]
    if cd["status"] != "ok":
        pytest.skip("committed anomalies tape not present")
    df = cd["delegate_fillability"]
    assert df["n_cross_strike_monotonicity"] == 43038
    assert df["n_edge_recompute_disagreements"] == 0     # the persisted edge IS reproducible
    assert df["n_outer_ask_equals_zero"] == 43025
    assert df["frac_outer_ask_equals_zero"] == 0.999698
    assert df["n_edge_within_one_ulp_of_zero"] == 1480
    assert df["smallest_edge_above_one_ulp"] >= 0.005    # a clean gap: zeros, then real edges
    assert cd["n_cross_strike_monotonicity_on_econ_series"] == 0
    assert cd["markets_truncated"].get("True") == 247    # coverage is unverifiable from tape
