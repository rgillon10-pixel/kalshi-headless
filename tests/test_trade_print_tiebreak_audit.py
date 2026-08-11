"""Offline tests for scripts/trade_print_tiebreak_audit.py (L323 — trade-print tie-breaks).

No network anywhere. Two classes of test:

* pure-function tests over hand-built tape, which pin the DETECTORS themselves — a healthy
  input must never be the only input a detector has seen (L191's shape). The most important
  of these is `test_concordance_excludes_tied_prints_*`: the estimator this file measures was
  BUILT with a bias (including tied prints made a purely random `trade_id` read 0.412 instead
  of 0.500, because a tie-ordered sort makes each group's last member a max-of-k draw), and
  that regression is pinned here so the artifact cannot come back.
* `test_acceptance_*` tests over the real committed `tape/kalshi_trades/`. These are written
  GROWTH-SAFE: the tape is append-only and still being backfilled, so counts are asserted as
  FLOORS (`>=`) and rates as bands, never as frozen equalities (L320's lesson — a hardcoded
  constant against a growing population turns honest growth into a false alarm).
  The one exception is `totally_orders_every_tie`, asserted as a live property on purpose: if
  a future backfill ever introduces a duplicate `trade_id`, L323's proposed repair key stops
  existing and a red test is the correct way to find that out.
"""
from __future__ import annotations

import json

import pytest

from scripts import trade_print_tiebreak_audit as T


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _rec(**kw):
    row = {
        "ticker": "KXMLBGAME-26AUG03X-A",
        "created_time": "2026-08-03T12:00:00.000000Z",
        "trade_id": "id-1",
        "yes_price": 0.60,
        "price_source_tag": "broker_truth",
    }
    row.update(kw)
    return row


def _write(tmp_path, day, recs, raw_extra=()):
    d = tmp_path / "kalshi_trades"
    d.mkdir(exist_ok=True)
    p = d / f"dt={day}.jsonl"
    with open(p, "a", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
        for line in raw_extra:
            fh.write(line + "\n")
    return d


def _prints(tmp_path, recs, day="2026-08-03", **kw):
    d = _write(tmp_path, day, recs, **kw)
    return list(T.iter_prints(T.day_paths(d)))


# --------------------------------------------------------------------------- #
# iter_prints / day_paths
# --------------------------------------------------------------------------- #
def test_day_paths_are_sorted_and_filterable(tmp_path):
    d = _write(tmp_path, "2026-08-03", [_rec()])
    _write(tmp_path, "2026-08-01", [_rec()])
    assert [p.stem for p in T.day_paths(d)] == ["dt=2026-08-01", "dt=2026-08-03"]
    assert [p.stem for p in T.day_paths(d, ["dt=2026-08-01"])] == ["dt=2026-08-01"]
    assert [p.stem for p in T.day_paths(d, ["dt=2026-08-01.jsonl"])] == ["dt=2026-08-01"]
    assert T.day_paths(tmp_path / "nope") == []


def test_iter_prints_drops_non_broker_truth_by_default(tmp_path):
    rows = _prints(tmp_path, [_rec(trade_id="a"),
                              _rec(trade_id="b", price_source_tag="synthetic")])
    assert [r[2] for r in rows] == ["a"]


def test_iter_prints_can_admit_every_tag(tmp_path):
    d = _write(tmp_path, "2026-08-03",
               [_rec(trade_id="a"), _rec(trade_id="b", price_source_tag="midpoint")])
    rows = list(T.iter_prints(T.day_paths(d), admitted_tag=None))
    assert sorted(r[2] for r in rows) == ["a", "b"]


def test_iter_prints_survives_garbage_lines(tmp_path):
    rows = _prints(tmp_path, [_rec(trade_id="a")],
                   raw_extra=("", "   ", "{not json", "[1,2,3]", '"a string"'))
    assert [r[2] for r in rows] == ["a"]


def test_iter_prints_skips_records_missing_ticker_or_time(tmp_path):
    rows = _prints(tmp_path, [_rec(trade_id="a"),
                              _rec(trade_id="b", ticker=None),
                              _rec(trade_id="c", created_time=None)])
    assert [r[2] for r in rows] == ["a"]


def test_iter_prints_skips_an_unparseable_timestamp_without_crashing(tmp_path):
    rows = _prints(tmp_path, [_rec(trade_id="a"),
                              _rec(trade_id="b", created_time="not-a-timestamp")])
    assert [r[2] for r in rows] == ["a"]


def test_ties_are_keyed_on_the_PARSED_instant_not_the_raw_string(tmp_path):
    # The committed tape strips trailing zeros, so one instant can render at 1-6 fractional
    # digits. A string key would call these two prints DISTINCT and silently under-count the
    # tie; keying on the parsed instant (via core.timeutil.parse_iso_utc, not the stdlib
    # fromisoformat that rejects ragged precision on older Pythons — L136/L138) groups them.
    rows = _prints(tmp_path, [
        _rec(trade_id="a", created_time="2026-08-03T12:00:00.5Z", yes_price=0.60),
        _rec(trade_id="b", created_time="2026-08-03T12:00:00.500000Z", yes_price=0.64),
    ])
    assert rows[0][1] == rows[1][1]
    c = T.tie_census(rows)
    assert c["n_distinct_keys"] == 1
    assert c["n_groups_tied"] == 1
    assert c["n_groups_price_differing"] == 1


def test_ordering_is_by_instant_not_lexical(tmp_path):
    # Lexically ".5Z" sorts AFTER ".500001Z" ('Z' > '0'); chronologically it comes first. The concordance
    # walk must use the instant, or it would score a correctly time-ordered id as discordant.
    rows = _seq(tmp_path, [("2026-08-03T12:00:00.5Z", "id-1"),
                           ("2026-08-03T12:00:00.500001Z", "id-2")])
    c = T.chronological_concordance(rows)
    assert c["n_strictly_increasing_pairs"] == 1
    assert c["rate"] == 1.0


def test_iter_prints_preserves_file_order(tmp_path):
    # File order is the artifact under study — the loader must not quietly sort it away.
    rows = _prints(tmp_path, [_rec(trade_id="z"), _rec(trade_id="a"), _rec(trade_id="m")])
    assert [r[2] for r in rows] == ["z", "a", "m"]


# --------------------------------------------------------------------------- #
# tie_census
# --------------------------------------------------------------------------- #
def test_census_clean_tape_has_no_ties(tmp_path):
    rows = _prints(tmp_path, [_rec(trade_id="a", created_time="2026-08-03T12:00:00Z"),
                              _rec(trade_id="b", created_time="2026-08-03T12:00:01Z")])
    c = T.tie_census(rows)
    assert c["n_prints"] == 2
    assert c["n_distinct_keys"] == 2
    assert c["n_groups_tied"] == 0
    assert c["n_prints_in_ties"] == 0
    assert c["frac_prints_in_ties"] == 0.0
    assert c["max_group_size"] == 1
    assert c["price_spread_cents"]["n"] == 0
    assert c["price_spread_cents"]["p50"] is None


def test_census_counts_a_same_price_tie_as_a_tie_but_not_as_price_differing(tmp_path):
    rows = _prints(tmp_path, [_rec(trade_id="a"), _rec(trade_id="b")])
    c = T.tie_census(rows)
    assert c["n_groups_tied"] == 1
    assert c["n_prints_in_ties"] == 2
    assert c["frac_prints_in_ties"] == 1.0
    assert c["n_groups_price_differing"] == 0


def test_census_flags_a_price_differing_tie_and_measures_its_spread(tmp_path):
    rows = _prints(tmp_path, [_rec(trade_id="a", yes_price=0.60),
                              _rec(trade_id="b", yes_price=0.63)])
    c = T.tie_census(rows)
    assert c["n_groups_price_differing"] == 1
    assert c["n_prints_in_price_differing_groups"] == 2
    assert c["price_spread_cents"]["min"] == pytest.approx(3.0)
    assert c["price_spread_cents"]["max"] == pytest.approx(3.0)


def test_census_does_not_tie_across_tickers_or_across_times(tmp_path):
    rows = _prints(tmp_path, [
        _rec(trade_id="a", ticker="T1", created_time="2026-08-03T12:00:00Z"),
        _rec(trade_id="b", ticker="T2", created_time="2026-08-03T12:00:00Z"),
        _rec(trade_id="c", ticker="T1", created_time="2026-08-03T12:00:01Z"),
    ])
    c = T.tie_census(rows)
    assert c["n_groups_tied"] == 0
    assert c["n_distinct_keys"] == 3


def test_census_reports_max_group_size_and_ignores_missing_prices(tmp_path):
    rows = _prints(tmp_path, [_rec(trade_id=f"i{i}") for i in range(5)]
                   + [_rec(trade_id="x", yes_price=None)])
    c = T.tie_census(rows)
    assert c["max_group_size"] == 6
    # a single known price + one missing price is NOT a price disagreement
    assert c["n_groups_price_differing"] == 0


def test_census_on_empty_input_is_not_a_crash_and_reports_none_fraction():
    c = T.tie_census([])
    assert c["n_prints"] == 0
    assert c["n_groups_tied"] == 0
    assert c["frac_prints_in_ties"] is None


# --------------------------------------------------------------------------- #
# tiebreak_key_adequacy
# --------------------------------------------------------------------------- #
def test_adequacy_is_true_when_trade_ids_are_present_and_distinct(tmp_path):
    rows = _prints(tmp_path, [_rec(trade_id="a"), _rec(trade_id="b")])
    a = T.tiebreak_key_adequacy(rows)
    assert a["totally_orders_every_tie"] is True
    assert a["n_missing_or_empty"] == 0
    assert a["n_globally_duplicated_ids"] == 0
    assert a["n_tied_groups_not_totally_ordered"] == 0
    assert a["verdict"].startswith("ADEQUATE")


def test_adequacy_is_false_when_a_tied_group_repeats_an_id(tmp_path):
    rows = _prints(tmp_path, [_rec(trade_id="dup"), _rec(trade_id="dup")])
    a = T.tiebreak_key_adequacy(rows)
    assert a["n_tied_groups_not_totally_ordered"] == 1
    assert a["totally_orders_every_tie"] is False
    assert a["verdict"].startswith("INADEQUATE")


def test_adequacy_is_false_when_an_id_is_missing(tmp_path):
    rows = _prints(tmp_path, [_rec(trade_id="a"), _rec(trade_id="")])
    a = T.tiebreak_key_adequacy(rows)
    assert a["n_missing_or_empty"] == 1
    assert a["totally_orders_every_tie"] is False


def test_adequacy_separates_global_duplication_from_within_tie_duplication(tmp_path):
    # Same id on two prints at DIFFERENT timestamps: a tape-integrity smell worth surfacing,
    # but it does not stop the key from totally ordering every tie group.
    rows = _prints(tmp_path, [
        _rec(trade_id="dup", created_time="2026-08-03T12:00:00Z"),
        _rec(trade_id="dup", created_time="2026-08-03T12:00:01Z"),
    ])
    a = T.tiebreak_key_adequacy(rows)
    assert a["n_globally_duplicated_ids"] == 1
    assert a["n_tied_groups_not_totally_ordered"] == 0
    assert a["totally_orders_every_tie"] is True


# --------------------------------------------------------------------------- #
# chronological_concordance  (incl. the estimator-bias regression)
# --------------------------------------------------------------------------- #
def _seq(tmp_path, pairs, ticker="T1"):
    return _prints(tmp_path, [_rec(trade_id=tid, ticker=ticker, created_time=ct)
                              for ct, tid in pairs])


def test_concordance_detects_a_time_ordered_id(tmp_path):
    rows = _seq(tmp_path, [(f"2026-08-03T12:00:0{i}Z", f"id-{i}") for i in range(6)])
    c = T.chronological_concordance(rows)
    assert c["n_strictly_increasing_pairs"] == 5
    assert c["rate"] == 1.0
    assert c["interpretation"].startswith("TIME-ORDERED")


def test_concordance_detects_a_reverse_ordered_id(tmp_path):
    rows = _seq(tmp_path, [(f"2026-08-03T12:00:0{i}Z", f"id-{9 - i}") for i in range(6)])
    c = T.chronological_concordance(rows)
    assert c["rate"] == 0.0
    assert c["interpretation"].startswith("REVERSE-ORDERED")


def test_concordance_calls_a_half_and_half_id_random(tmp_path):
    rows = _seq(tmp_path, [("2026-08-03T12:00:00Z", "id-1"),
                           ("2026-08-03T12:00:01Z", "id-2"),   # concordant
                           ("2026-08-03T12:00:02Z", "id-0"),   # discordant
                           ("2026-08-03T12:00:03Z", "id-5")])  # concordant
    c = T.chronological_concordance(rows)
    assert c["n_strictly_increasing_pairs"] == 3
    assert c["interpretation"].startswith("PARTIAL") or c["rate"] == pytest.approx(2 / 3)


def test_concordance_excludes_tied_prints_regression_on_the_max_of_k_bias(tmp_path):
    # THE regression test for this module's own build defect. Two singletons whose ids are
    # concordant, plus a tie group whose largest id would (if admitted) be compared against
    # the following singleton and lose. Admitting ties would read 1/2; singleton-only reads
    # 1/1. Same tape, two different answers — one of them manufactured by the estimator.
    rows = _seq(tmp_path, [
        ("2026-08-03T12:00:00Z", "id-1"),
        ("2026-08-03T12:00:01Z", "id-8"),   # tie member (with the next row)
        ("2026-08-03T12:00:01Z", "id-9"),   # tie member, the max-of-k draw
        ("2026-08-03T12:00:02Z", "id-2"),
    ])
    c = T.chronological_concordance(rows)
    assert c["n_strictly_increasing_pairs"] == 1     # 12:00:00 -> 12:00:02 only
    assert c["rate"] == 1.0
    assert "singleton" in c["pairs_source"]


def test_concordance_does_not_pair_across_tickers(tmp_path):
    rows = _prints(tmp_path, [
        _rec(trade_id="id-9", ticker="T1", created_time="2026-08-03T12:00:00Z"),
        _rec(trade_id="id-1", ticker="T2", created_time="2026-08-03T12:00:01Z"),
    ])
    c = T.chronological_concordance(rows)
    assert c["n_strictly_increasing_pairs"] == 0
    assert c["rate"] is None
    assert c["interpretation"].startswith("UNDETERMINED")


# --------------------------------------------------------------------------- #
# build_report / CLI
# --------------------------------------------------------------------------- #
def test_build_report_shape_and_coverage_note(tmp_path):
    d = _write(tmp_path, "2026-08-03", [_rec(trade_id="a", yes_price=0.60),
                                        _rec(trade_id="b", yes_price=0.61)])
    rep = T.build_report(d)
    assert rep["lesson"] == "L323"
    assert rep["n_days"] == 1 and rep["days"] == ["dt=2026-08-03"]
    assert rep["admitted_price_source_tag"] == "broker_truth"
    for k in ("tie_census", "tiebreak_key_adequacy", "chronological_concordance"):
        assert isinstance(rep[k], dict)
    note = rep["coverage_note"]
    assert "UPPER bound" in note and "not the true execution sequence" in note


def test_build_report_on_a_missing_family_is_an_honest_zero(tmp_path):
    rep = T.build_report(tmp_path / "absent")
    assert rep["n_days"] == 0
    assert rep["tie_census"]["n_prints"] == 0
    assert rep["tiebreak_key_adequacy"]["totally_orders_every_tie"] is True
    # An empty tape must not be readable as a measured clean bill: the count is right there.
    assert rep["tiebreak_key_adequacy"]["n_prints"] == 0


def test_main_writes_json_and_returns_zero(tmp_path):
    d = _write(tmp_path, "2026-08-03", [_rec(trade_id="a")])
    out = tmp_path / "rep.json"
    rc = T.main(["--tape-dir", str(d), "--json", str(out)])
    assert rc == 0
    rep = json.loads(out.read_text())
    assert rep["tie_census"]["n_prints"] == 1


# --------------------------------------------------------------------------- #
# acceptance — real committed tape (growth-safe)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def real_report():
    if not T.day_paths():
        pytest.skip("tape/kalshi_trades/ not present in this checkout")
    return T.build_report()


def test_acceptance_l323_real_tape_reproduces_the_tie_exposure(real_report):
    # HARD acceptance on the real tape, asserted as FLOORS because the family is append-only
    # and still being backfilled (L320: a frozen constant against a growing population turns
    # honest growth into a false alarm). Measured 2026-08-11: 213,488 admitted prints,
    # 25,781 tie groups, 103,449 prints in ties (48.46%), 7,999 price-differing groups,
    # max group 303, spread p50 1c / p90 4c / max 61c.
    c = real_report["tie_census"]
    assert c["n_prints"] >= 213_488
    assert c["n_groups_tied"] >= 25_781
    assert c["n_prints_in_ties"] >= 103_449
    assert c["n_groups_price_differing"] >= 7_999
    assert c["max_group_size"] >= 303
    assert c["frac_prints_in_ties"] >= 0.30
    assert c["price_spread_cents"]["max"] >= 1.0


def test_acceptance_l323_trade_id_is_an_adequate_explicit_tiebreak_key(real_report):
    # L323's own row left this open ("`trade_id`, IF monotonic within a capture"). Measured:
    # present on every admitted print, zero global collisions, and it totally orders every
    # tie group — so the repair key EXISTS. Asserted live, not pinned: if a future backfill
    # breaks it, the repair L323 proposes stops being available and this must go red.
    a = real_report["tiebreak_key_adequacy"]
    assert a["n_missing_or_empty"] == 0
    assert a["n_globally_duplicated_ids"] == 0
    assert a["n_tied_groups_not_totally_ordered"] == 0
    assert a["totally_orders_every_tie"] is True
    assert a["n_distinct"] == a["n_prints"]


def test_acceptance_l323_trade_id_is_not_chronological(real_report):
    # The other half of the same finding, and the reason the repair must be described as
    # "declared and reproducible" rather than "correct": concordance with clock order is
    # 0.500282 over 109,950 untied pairs — indistinguishable from a coin flip.
    c = real_report["chronological_concordance"]
    assert c["n_strictly_increasing_pairs"] >= 100_000
    assert 0.45 <= c["rate"] <= 0.55
    assert c["interpretation"].startswith("RANDOM")
