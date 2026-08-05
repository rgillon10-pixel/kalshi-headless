"""Tests for `scripts/polymarket_cpi_pairs_monotonicity_audit.py`.

Two layers, the `tests/test_q51_book_anchor_audit.py` shape:

* fixture unit tests — pure / synthetic tape under `tmp_path`, no network, no git. They pin
  the SEMANTICS the headline turns on: the independent re-derivation of the violation flag
  (so a collector flag that ever stops tracking its own value is CAUGHT, not inherited), the
  `|prob_gap| > 1` impossibility test, and both the joinable and non-joinable branches of the
  `econ_prints` join;
* `test_acceptance_*` over committed tape — HARD, exact assertions over a CLOSED window
  (`MAX_DAY`), which is what makes them pinnable at all: without the cap, tomorrow's collector
  pass would move today's numbers. Backfill INTO an existing day (the L282 stranded-branch
  union-append) can still break them; that is deliberate — these are the numbers a finding
  quotes, so a silent change to them should be loud.
"""
from __future__ import annotations

import json

import pytest

from scripts import polymarket_cpi_pairs_monotonicity_audit as A

MAX_DAY = "2026-08-04"


# --------------------------------------------------------------------------- #
# synthetic tape helpers
# --------------------------------------------------------------------------- #
def pair_record(day="2026-07-14", ts="2026-07-14T09:00:00+00:00", ticker="KXCPICORE-26JUL",
                kind="exact", value=0.5, derived=0.2, flag=False, gap=0.1,
                lo=0.4, hi=0.5, ask=0.1, capture="C1", kalshi_tag="synthetic",
                poly_tag="real_ask"):
    rec = {
        "schema_version": A.PAIR_SCHEMA, "capture_id": capture, "captured_at": ts,
        "family": "cpi", "series": "cpi_core_mom", "period": "2026-07",
        "bucket_kind": kind, "bucket_value": value,
        "kalshi": {"event_ticker": ticker, "derived_prob": derived,
                   "kalshi_inputs": {"exceed_le": lo, "exceed_ge": hi},
                   "monotonicity_violation": flag, "price_source_tag": kalshi_tag},
        "polymarket": {"event_id": "1", "market_id": "2", "best_bid": 0.01, "best_ask": ask,
                       "book_fetch_ok": True, "price_source_tag": poly_tag},
        "prob_gap": gap,
    }
    if kalshi_tag is None:
        rec["kalshi"].pop("price_source_tag")
    if poly_tag is None:
        rec["polymarket"].pop("price_source_tag")
    return day, rec


def econ_record(day="2026-07-14", ts="2026-07-14T09:00:03+00:00", ticker="KXCPICORE-26JUL",
                rungs=((0.4, 0.08, 0.0), (0.5, 0.97, 0.0)), tag="real_ask"):
    return day, {
        "schema_version": A.ECON_SCHEMA, "capture_id": "E1", "captured_at": ts,
        "open_events": {"events": [{
            "event_ticker": ticker, "completeness_ok": True,
            "strikes": [{"floor_strike": fs, "yes_ask": ya, "yes_bid": yb,
                         "strike_type": "greater", "ticker": f"{ticker}-T{fs}",
                         "price_source_tag": tag} for fs, ya, yb in rungs],
        }]},
    }


def write_tape(root, name, rows):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    by_day = {}
    for day, rec in rows:
        by_day.setdefault(day, []).append(rec)
    for day, recs in by_day.items():
        (d / f"dt={day}.jsonl").write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in recs), encoding="utf-8")
    return d


def fake_git(args, cwd=None):
    if "rev-parse" in args:
        return "deadbeef"
    return ""


# --------------------------------------------------------------------------- #
# the independent re-derivation of the flag
# --------------------------------------------------------------------------- #
def test_unit_interval_boundaries_are_not_violations():
    assert A.is_out_of_unit_interval(0.0) is False
    assert A.is_out_of_unit_interval(1.0) is False
    assert A.is_out_of_unit_interval(0.5) is False


def test_a_negative_derived_probability_is_a_violation():
    assert A.is_out_of_unit_interval(-0.89) is True
    assert A.is_out_of_unit_interval(1.4) is True


def test_float_noise_inside_the_collectors_own_tolerance_is_not_a_violation():
    """The tolerance is copied from the collector so the two verdicts are comparable on
    identical terms — a tighter bar here would manufacture disagreements."""
    assert A.is_out_of_unit_interval(-1e-12) is False
    assert A.is_out_of_unit_interval(-1e-6) is True


def test_a_missing_probability_is_none_not_false():
    """Honest None, never a guessed clean bill (L86)."""
    assert A.is_out_of_unit_interval(None) is None
    assert A.is_out_of_unit_interval("0.5") is None


def test_classify_clean_record_agrees_with_its_flag():
    _, rec = pair_record(derived=0.2, flag=False, gap=0.1)
    info = A.classify_record(rec)
    assert info["flag_persisted"] is False and info["flag_recomputed"] is False
    assert info["flags_agree"] is True
    assert info["gap_impossible"] is False


def test_classify_violating_record_agrees_with_its_flag():
    _, rec = pair_record(derived=-0.89, flag=True, gap=-0.5)
    info = A.classify_record(rec)
    assert info["flag_persisted"] is True and info["flag_recomputed"] is True
    assert info["flags_agree"] is True
    assert info["abs_prob_gap"] == pytest.approx(0.5)


def test_classify_catches_a_flag_that_stopped_tracking_its_own_value():
    """The planted defect this audit exists to be able to detect: a negative derived_prob
    carrying `monotonicity_violation: False`. If the real tape ever shows this, the honesty
    half of the finding is void."""
    _, rec = pair_record(derived=-0.4, flag=False, gap=-0.5)
    info = A.classify_record(rec)
    assert info["flag_persisted"] is False and info["flag_recomputed"] is True
    assert info["flags_agree"] is False


def test_an_impossible_gap_is_flagged_and_a_boundary_gap_is_not():
    assert A.classify_record(pair_record(gap=-1.73)[1])["gap_impossible"] is True
    assert A.classify_record(pair_record(gap=-1.0)[1])["gap_impossible"] is False
    assert A.classify_record(pair_record(gap=1.0000001)[1])["gap_impossible"] is True


def test_a_missing_gap_is_not_an_impossible_gap():
    day, rec = pair_record()
    rec["prob_gap"] = None
    info = A.classify_record(rec)
    assert info["gap_persisted"] is False and info["gap_impossible"] is False
    assert info["abs_prob_gap"] is None


def test_an_untagged_price_defaults_to_synthetic():
    """CLAUDE.md trust default — an absent tag is never read as clean."""
    _, rec = pair_record(kalshi_tag=None, poly_tag=None)
    info = A.classify_record(rec)
    assert info["kalshi_price_source_tag"] == "synthetic"
    assert info["polymarket_price_source_tag"] == "synthetic"


def test_gap_cohort_stats_on_an_empty_cohort_is_null_not_zero():
    st = A.gap_cohort_stats([])
    assert st["n"] == 0 and st["mean_abs_gap"] is None and st["median_abs_gap"] is None


# --------------------------------------------------------------------------- #
# the transform, re-applied to a real_ask ladder
# --------------------------------------------------------------------------- #
def test_needed_strikes_per_bucket_kind():
    assert A.needed_strikes(A.classify_record(pair_record(kind="exact")[1])) == [0.4, 0.5]
    assert A.needed_strikes(A.classify_record(pair_record(kind="floor")[1])) == [0.5]
    assert A.needed_strikes(A.classify_record(pair_record(kind="ceiling")[1])) == [0.4]


def test_needed_strikes_is_none_when_the_kind_is_unknown_or_an_input_is_missing():
    assert A.needed_strikes(A.classify_record(pair_record(kind="weird")[1])) is None
    assert A.needed_strikes(A.classify_record(pair_record(kind="exact", lo=None)[1])) is None


def test_reconstruct_prob_mirrors_the_collectors_three_transforms():
    asks = {0.4: 0.08, 0.5: 0.97}
    assert A.reconstruct_prob("exact", asks, 0.4, 0.5) == pytest.approx(-0.89)
    assert A.reconstruct_prob("floor", asks, None, 0.5) == pytest.approx(0.03)
    assert A.reconstruct_prob("ceiling", asks, 0.4, None) == pytest.approx(0.08)


def test_reconstruct_prob_returns_none_when_a_rung_is_absent_or_unpriced():
    assert A.reconstruct_prob("exact", {0.4: 0.08}, 0.4, 0.5) is None
    assert A.reconstruct_prob("exact", {0.4: 0.08, 0.5: None}, 0.4, 0.5) is None
    assert A.reconstruct_prob("weird", {0.4: 0.08, 0.5: 0.97}, 0.4, 0.5) is None


# --------------------------------------------------------------------------- #
# the join, both branches
# --------------------------------------------------------------------------- #
def test_a_joinable_violating_record_is_fully_diagnosed(tmp_path):
    write_tape(tmp_path, "econ", [econ_record()])
    ladders = A.load_econ_ladders(tmp_path / "econ")
    info = A.classify_record(pair_record(derived=-0.89, flag=True, gap=-1.67)[1])
    info["_ts"] = A._parse_ts(info["captured_at"])
    j = A.join_to_econ_ladder(info, ladders)
    assert j["joined"] is True
    assert j["reconstruction_exact"] is True and j["reconstruction_abs_diff"] == 0.0
    assert j["inversion_reproduced"] is True
    assert j["ask_lo"] == 0.08 and j["ask_hi"] == 0.97
    assert j["high_rung_one_sided"] is True and j["high_rung_spread"] == pytest.approx(0.97)
    assert j["rung_tags"] == ["real_ask"]
    assert j["age_hours"] == pytest.approx(3.0 / 3600.0, abs=1e-6)


def test_a_record_whose_event_never_appears_in_econ_prints_is_not_joinable(tmp_path):
    write_tape(tmp_path, "econ", [econ_record(ticker="KXCPI-26AUG")])
    ladders = A.load_econ_ladders(tmp_path / "econ")
    info = A.classify_record(pair_record(ticker="KXCPICORE-26JUL")[1])
    info["_ts"] = A._parse_ts(info["captured_at"])
    j = A.join_to_econ_ladder(info, ladders)
    assert j["joined"] is False and j["reason"] == "no_econ_capture_for_event"


def test_a_record_whose_rung_is_unpriced_in_every_capture_is_not_joinable(tmp_path):
    write_tape(tmp_path, "econ", [econ_record(rungs=((0.4, 0.08, 0.0), (0.5, None, 0.0)))])
    ladders = A.load_econ_ladders(tmp_path / "econ")
    info = A.classify_record(pair_record()[1])
    info["_ts"] = A._parse_ts(info["captured_at"])
    j = A.join_to_econ_ladder(info, ladders)
    assert j["joined"] is False and j["reason"] == "needed_rungs_absent_or_unpriced"


def test_the_join_picks_the_nearest_priced_capture_not_the_first(tmp_path):
    write_tape(tmp_path, "econ", [
        econ_record(ts="2026-07-14T03:00:00+00:00", rungs=((0.4, 0.5, 0.1), (0.5, 0.2, 0.1))),
        econ_record(ts="2026-07-14T08:59:00+00:00"),
    ])
    ladders = A.load_econ_ladders(tmp_path / "econ")
    info = A.classify_record(pair_record(derived=-0.89, flag=True)[1])
    info["_ts"] = A._parse_ts(info["captured_at"])
    j = A.join_to_econ_ladder(info, ladders)
    assert j["ask_hi"] == 0.97 and j["age_hours"] == pytest.approx(1.0 / 60.0, abs=1e-6)


def test_freshness_ladder_reports_coverage_and_age_together(tmp_path):
    """L283 — a join fraction quoted without its age ladder is not a measurement."""
    blk = A.join_freshness_ladder([0.001, 0.5, 5.0, None], 4, bounds=(0.25, 1.0, 6.0))
    assert blk["n_joined"] == 3 and blk["frac_joined"] == pytest.approx(0.75)
    assert blk["freshness_ladder"]["within_0.25h"]["n"] == 1
    assert blk["freshness_ladder"]["within_1.0h"]["n"] == 2
    assert blk["freshness_ladder"]["within_6.0h"]["n"] == 3


# --------------------------------------------------------------------------- #
# the other side of the join (L280)
# --------------------------------------------------------------------------- #
def test_a_day_with_zero_flags_can_still_have_an_inverted_ladder(tmp_path):
    """The under-sampling shape: one pairs pass sees a healthy ladder, another econ capture
    the same day sees the inversion. Absence of flags is not absence of defect."""
    write_tape(tmp_path, "econ", [
        econ_record(day="2026-07-29", ts="2026-07-29T09:00:03+00:00",
                    rungs=((0.4, 0.11, 0.0), (0.5, 0.09, 0.0))),
        econ_record(day="2026-07-29", ts="2026-07-29T15:00:00+00:00",
                    rungs=((0.4, 0.04, 0.0), (0.5, 0.05, 0.0))),
    ])
    ladders = A.load_econ_ladders(tmp_path / "econ")
    day, rec = pair_record(day="2026-07-29", ts="2026-07-29T09:00:00+00:00",
                           derived=0.02, flag=False, gap=-0.08)
    rec["_day"] = day
    rows = A.shadow_inversion_by_day([rec], ladders)
    assert rows["2026-07-29"]["n_econ_rung_pair_observations"] == 2
    assert rows["2026-07-29"]["n_econ_inverted"] == 1


def test_shadow_scan_only_counts_rung_pairs_this_family_actually_pairs():
    """It must not credit itself with inversions on rungs the pairs collector never touched."""
    rows = A.shadow_inversion_by_day([], {"KXCPICORE-26JUL": []})
    assert rows == {}


# --------------------------------------------------------------------------- #
# end-to-end over synthetic tape
# --------------------------------------------------------------------------- #
def test_audit_end_to_end_over_synthetic_tape(tmp_path):
    pairs = write_tape(tmp_path, "pairs", [
        pair_record(derived=0.2, flag=False, gap=0.1),
        pair_record(derived=-0.89, flag=True, gap=-1.67, capture="C1"),
        pair_record(day="2026-07-15", ts="2026-07-15T09:00:00+00:00", derived=0.3,
                    flag=False, gap=0.2, capture="C2"),
    ])
    econ = write_tape(tmp_path, "econ", [
        econ_record(),
        econ_record(day="2026-07-15", ts="2026-07-15T09:00:03+00:00",
                    rungs=((0.4, 0.05, 0.01), (0.5, 0.06, 0.01))),
    ])
    rep = A.audit(pairs, econ, run_git=fake_git)

    assert rep["population"]["n_pair_records"] == 3
    v = rep["violation_detection"]
    assert v["n_violations_persisted"] == 1 and v["n_violations_recomputed"] == 1
    assert v["flag_is_honest"] is True and v["n_flag_disagreements"] == 0
    g = rep["prob_gap_containment"]
    assert g["n_violating_records_with_a_persisted_prob_gap"] == 1
    assert g["n_impossible_abs_gap_gt_1"] == 1
    assert g["impossible_records"][0]["econ_prints_diagnosis"]["ask_at_exceed_ge"] == 0.97
    assert rep["econ_prints_join"]["violating_cohort"]["frac_joined"] == 1.0
    assert rep["temporal"]["by_day"]["2026-07-15"]["n_econ_inverted"] == 1
    assert rep["temporal"]["days_with_zero_flags_but_a_nonzero_econ_inversion_rate"] \
        == ["2026-07-15"]
    assert rep["source_tags"]["kalshi_leg"] == {"synthetic": 3}
    assert "DESCRIPTIVE" in rep["scope"]


def test_audit_is_empty_but_does_not_crash_on_an_absent_tape_dir(tmp_path):
    rep = A.audit(tmp_path / "nope", tmp_path / "also-nope", run_git=fake_git)
    assert rep["population"]["n_pair_records"] == 0
    assert rep["violation_detection"]["frac_violating"] is None
    assert rep["prob_gap_containment"]["all_records"]["mean_abs_gap"] is None


def test_a_broken_git_runner_never_poisons_the_report(tmp_path):
    def boom(args, cwd=None):
        raise RuntimeError("no git here")
    rep = A.audit(tmp_path / "nope", tmp_path / "nope", run_git=boom)
    assert rep["git_ref"] is None and rep["uncommitted_tape_paths"] is None


def test_max_day_closes_the_window(tmp_path):
    pairs = write_tape(tmp_path, "pairs", [
        pair_record(day="2026-07-14"),
        pair_record(day="2026-07-15", ts="2026-07-15T09:00:00+00:00"),
    ])
    econ = write_tape(tmp_path, "econ", [econ_record()])
    assert A.audit(pairs, econ, run_git=fake_git,
                   max_day="2026-07-14")["population"]["n_pair_records"] == 1
    assert A.audit(pairs, econ, run_git=fake_git)["population"]["n_pair_records"] == 2


def test_unparseable_and_foreign_lines_are_counted_not_dropped(tmp_path):
    d = tmp_path / "pairs"
    d.mkdir()
    (d / "dt=2026-07-14.jsonl").write_text(
        json.dumps(pair_record()[1], sort_keys=True) + "\n"
        + "{not json\n"
        + json.dumps({"schema_version": "something_else.v1"}) + "\n", encoding="utf-8")
    _, meta = A.load_pair_records(d)
    assert meta["n_lines"] == 3 and meta["n_bad_json"] == 1 and meta["n_other_schema"] == 1


# --------------------------------------------------------------------------- #
# acceptance — committed tape, closed window
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def real():
    if not A.DEFAULT_PAIRS_DIR.is_dir() or not A.DEFAULT_ECON_DIR.is_dir():
        pytest.skip("committed tape not present")
    return A.audit(max_day=MAX_DAY, run_git=fake_git)


def test_acceptance_the_violating_cohort_reproduces_exactly(real):
    """The number every other claim in the finding rests on. Independently re-derived here
    (own loader, own predicate) rather than read off the collector's flag alone."""
    assert real["population"]["n_pair_records"] == 1764
    assert real["violation_detection"]["n_violations_persisted"] == 206
    assert real["violation_detection"]["n_violations_recomputed"] == 206
    assert real["violation_detection"]["frac_violating"] == pytest.approx(0.1168, abs=1e-4)


def test_acceptance_the_detection_half_is_honest(real):
    """Every violating record's own flag agrees with an independent re-derivation, in BOTH
    directions — 1558 clean / 206 flagged, zero disagreements."""
    v = real["violation_detection"]
    assert v["flag_is_honest"] is True and v["n_flag_disagreements"] == 0
    assert v["cooccurrence_persisted_vs_recomputed"] == {
        "persisted=False,recomputed=False": 1558,
        "persisted=True,recomputed=True": 206,
    }
    assert v["n_by_bucket_kind"] == {"exact": 206}


def test_acceptance_the_metric_half_is_not_contained(real):
    """...and every one of those 206 flagged-invalid records still carries a `prob_gap`
    computed from the invalid value, two of them arithmetically impossible."""
    g = real["prob_gap_containment"]
    assert g["n_violating_records_with_a_persisted_prob_gap"] == 206
    assert g["frac_of_violations_carrying_a_gap"] == 1.0
    assert g["n_impossible_abs_gap_gt_1"] == 2
    assert g["all_records"]["max_abs_gap"] == pytest.approx(1.73)
    assert {round(r["prob_gap"], 2) for r in g["impossible_records"]} == {-1.67, -1.73}


def test_acceptance_the_violating_cohort_inflates_the_headline_dispersion(real):
    g = real["prob_gap_containment"]
    assert g["violating_cohort"]["mean_abs_gap"] == pytest.approx(0.5371, abs=1e-4)
    assert g["clean_cohort"]["mean_abs_gap"] == pytest.approx(0.1992, abs=1e-4)
    assert g["all_records"]["mean_abs_gap"] == pytest.approx(0.2387, abs=1e-4)
    assert g["frac_of_headline_mean_that_is_excess_over_clean_cohort"] == \
        pytest.approx(0.1653, abs=1e-4)


def test_acceptance_econ_prints_diagnoses_every_violating_record(real):
    """THE load-bearing new fact: the raw legs the pairs schema drops are recoverable, at a
    median join age of ~4.6 seconds, reproducing the persisted synthetic value exactly."""
    j = real["econ_prints_join"]["violating_cohort"]
    assert j["n_total"] == 206 and j["n_joined"] == 206
    assert j["frac_joined"] == 1.0
    assert j["median_age_hours"] < 0.01
    assert j["freshness_ladder"]["within_0.05h"]["n"] == 205
    assert j["reconstruction"]["n_exact_to_1e_9"] == 206
    assert j["reconstruction"]["frac_exact"] == 1.0


def test_acceptance_every_reconstruction_miss_is_a_stale_join_not_a_failed_one(real):
    """Family-wide the reconstruction is exact on 1758/1764; all 6 misses sit on the one
    2026-07-06 pass whose nearest econ capture is ~5.9h away. On every join fresher than an
    hour the transform reproduces the persisted value bit for bit."""
    r = real["econ_prints_join"]["all_records"]["reconstruction"]
    assert r["n_exact_to_1e_9"] == 1758
    assert r["max_abs_diff"] == pytest.approx(0.04)
    assert r["max_abs_diff_on_joins_within_1h"] == 0.0


def test_acceptance_the_inversion_is_a_one_sided_quote_not_a_crossed_market(real):
    """What the join buys beyond joinability: 196/206 inverting rungs have NO resting bid at
    all, median ask-minus-bid 0.97 — a nominal quote, not a two-sided crossed book."""
    a = real["econ_prints_join"]["inversion_anatomy"]
    assert a["inversion_reproduced_in_real_ask_ladder"] == 206
    assert a["high_rung_one_sided_no_bid"] == 196
    assert a["median_high_rung_spread"] == pytest.approx(0.97)


def test_acceptance_the_zero_violation_days_are_under_sampled_not_healed(real):
    """The temporal half: violations stop after 2026-07-21, but the same rungs are still
    observably inverted in econ_prints on 07-29 and 07-31 — the flag count is bounded by the
    pairs family's own one-pass-a-day cadence (L280 both-sides, L283 cadence-not-breadth)."""
    t = real["temporal"]
    assert t["by_day"]["2026-07-14"]["n_violations"] == 176
    assert t["by_day"]["2026-07-22"]["n_violations"] == 0
    assert t["days_with_zero_flags_but_a_nonzero_econ_inversion_rate"] == \
        ["2026-07-29", "2026-07-31"]
    assert t["by_day"]["2026-07-29"]["n_econ_inverted"] == 22
    assert t["by_day"]["2026-07-31"]["n_econ_inverted"] == 14
    assert t["by_day"]["2026-07-29"]["n_capture_passes"] == 1


def test_acceptance_every_price_in_the_join_carries_its_source_tag(real):
    """Trust default held end to end: the derived leg is `synthetic`, both priced legs are
    `real_ask`, and nothing in the join is untagged."""
    tags = real["source_tags"]
    assert tags["kalshi_leg"] == {"synthetic": 1764}
    assert tags["polymarket_leg"] == {"real_ask": 1764}
    assert tags["econ_prints_rungs_used_in_join"] == {"real_ask": 1764}


def test_acceptance_the_collectors_assumed_step_matches_every_ladders_own_spacing(real):
    """L7 — the 0.1 CPI step is hardcoded in the collector; read off the data it is also 0.1
    on every committed KXCPI* ladder, so that assumption is (here) sound rather than assumed."""
    s = real["ladder_spacing_check"]
    assert s["collector_assumed_step"] == 0.1
    for series, seen in s["inferred_spacing_by_series"].items():
        assert list(seen) == ["0.1"], series
