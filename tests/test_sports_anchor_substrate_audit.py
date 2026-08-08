"""Offline tests for scripts/sports_anchor_substrate_audit.py.

No network anywhere. Two classes of test:

* pure-function tests over hand-built tape fixtures, which pin the DETECTORS themselves —
  each one is proven to FIRE on a planted defect, because a detector that has only ever seen
  a healthy input is untested (L191's shape, and L155's precision-vs-recall rule);
* `test_acceptance_*` tests over committed tape, run through the module's own `--max-day`
  CLOSED window (2026-08-07). Tape is append-only, so a later collector pass or a
  stranded-branch sweep can only ADD rows on a LATER day; pinning the cutoff is what makes
  these equalities safe to assert (L286's closed-window rule). Numbers that a same-day sweep
  could still legitimately move are asserted DIRECTIONALLY (>=), never as equalities.
"""
from __future__ import annotations

import json

import pytest

from core.io import REPO_ROOT
from scripts import sports_anchor_substrate_audit as A


WINDOW = A.DEFAULT_MAX_DAY  # 2026-08-07 — the closed window every acceptance number is from


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _write(root, family, day, rows):
    d = root / "tape" / family
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"dt={day}.jsonl"
    with open(p, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def _pair(status, ticker="KXMLBGAME-26JUL22ABC", series="KXMLBGAME", **leg):
    leg = dict(leg)
    leg["status"] = status
    return {"event_ticker": ticker, "series": series, "odds_leg": leg}


# --------------------------------------------------------------------------- #
# 1. backfill lane — the out-of-vocabulary tag detector
# --------------------------------------------------------------------------- #
def test_out_of_vocabulary_tag_is_reported_and_degrades_to_synthetic(tmp_path):
    """A record can LOOK tagged and still be untrusted. `mixed` is not one of the four
    sanctioned tags, so CLAUDE.md's trust default makes it `synthetic`."""
    _write(tmp_path, "sports_clv", "2026-07-03",
           [{"price_source_tag": "mixed", "captured_at": "2026-07-03T20:00:00+00:00"}])
    rep = A.backfill_lane(root=tmp_path, max_day="2026-07-04")
    oov = rep["sports_clv"]["out_of_vocabulary_tags"]
    assert "price_source_tag=mixed" in oov
    assert oov["price_source_tag=mixed"]["degrades_to"] == "synthetic"


def test_a_sanctioned_tag_is_not_flagged_out_of_vocabulary(tmp_path):
    _write(tmp_path, "sports_clv", "2026-07-03",
           [{"price_source_tag": "real_ask", "captured_at": "2026-07-03T20:00:00+00:00"}])
    rep = A.backfill_lane(root=tmp_path, max_day="2026-07-04")
    assert rep["sports_clv"]["out_of_vocabulary_tags"] == {}
    assert rep["sports_clv"]["record_source_tags"] == {"price_source_tag=real_ask": 1}


def test_backfill_lane_respects_the_max_day_cutoff(tmp_path):
    _write(tmp_path, "sports_clv", "2026-07-03", [{"price_source_tag": "real_ask"}])
    _write(tmp_path, "sports_clv", "2026-07-09", [{"price_source_tag": "real_ask"}])
    assert A.backfill_lane(root=tmp_path, max_day="2026-07-04")["sports_clv"]["n_records"] == 1
    assert A.backfill_lane(root=tmp_path, max_day="2026-07-31")["sports_clv"]["n_records"] == 2


def test_a_missing_family_is_reported_absent_not_healthy(tmp_path):
    """An absent directory must never read as a clean family (L86: an honest None)."""
    rep = A.backfill_lane(root=tmp_path, max_day=WINDOW)
    assert rep["sports_clv"]["exists"] is False
    assert rep["sports_clv"]["n_records"] == 0


def test_unparseable_line_does_not_crash_or_inflate_the_count(tmp_path):
    d = tmp_path / "tape" / "sports_clv"
    d.mkdir(parents=True)
    (d / "dt=2026-07-03.jsonl").write_text('{"price_source_tag": "real_ask"}\nnot json\n\n')
    assert A.backfill_lane(root=tmp_path, max_day=WINDOW)["sports_clv"]["n_records"] == 1


# --------------------------------------------------------------------------- #
# 2. write-path liveness — AST, not lexical
# --------------------------------------------------------------------------- #
def test_liveness_is_ast_based_a_docstring_mention_is_not_a_call_site(tmp_path):
    """L228's precedent: a line-regex draft of a similar check flagged only string
    literals. A module named ONLY in `hourly_pass`'s docstring must not read as scheduled."""
    hp = tmp_path / "collection"
    hp.mkdir(parents=True)
    (hp / "hourly_pass.py").write_text(
        '"""Also mentions collection.sports_history in prose."""\n'
        "from collection import sports_pairs\n"
    )
    rep = A.write_path_liveness(root=tmp_path)
    assert rep["write_path_liveness" if False else "families"]["sports_clv"]["verdict"] == \
        "one_shot_no_scheduled_caller"
    assert rep["families"]["sports_pairs"]["verdict"] == "scheduled"


def test_liveness_sees_a_real_import(tmp_path):
    hp = tmp_path / "collection"
    hp.mkdir(parents=True)
    (hp / "hourly_pass.py").write_text("from collection import sports_history, sports_pairs\n")
    rep = A.write_path_liveness(root=tmp_path)
    assert rep["families"]["sports_clv"]["imported_by_hourly_pass"] is True
    assert rep["families"]["sports_clv"]["verdict"] == "scheduled"


def test_a_scripts_writer_can_never_be_scheduled_by_hourly_pass(tmp_path):
    """`hourly_pass` imports from `collection`; a `scripts/` writer is out of reach by
    construction, so the verdict must not depend on what happens to be imported."""
    hp = tmp_path / "collection"
    hp.mkdir(parents=True)
    (hp / "hourly_pass.py").write_text("from collection import sports_clv_s7\n")
    rep = A.write_path_liveness(root=tmp_path)
    assert rep["families"]["sports_clv_s7"]["importable_by_hourly_pass"] is False
    assert rep["families"]["sports_clv_s7"]["verdict"] == "one_shot_no_scheduled_caller"


# --------------------------------------------------------------------------- #
# 3. live lane — status census and the trailing-outage run
# --------------------------------------------------------------------------- #
def test_trailing_all_blocked_run_counts_only_the_TRAILING_days(tmp_path):
    """A blocked day in the MIDDLE of history is not an ongoing outage. The run must be
    anchored at the newest day and stop at the first day that produced anything else."""
    _write(tmp_path, "sports_pairs", "2026-07-01", [_pair("blocked_key")])
    _write(tmp_path, "sports_pairs", "2026-07-02", [_pair("matched", bookmaker="pinnacle")])
    _write(tmp_path, "sports_pairs", "2026-07-03", [_pair("blocked_key")])
    _write(tmp_path, "sports_pairs", "2026-07-04", [_pair("blocked_key")])
    rep = A.live_lane(root=tmp_path, max_day="2026-07-31")
    assert rep["n_consecutive_trailing_all_blocked_days"] == 2
    assert rep["trailing_all_blocked_days"] == ["2026-07-03", "2026-07-04"]


def test_a_day_with_one_non_blocked_row_is_not_an_all_blocked_day(tmp_path):
    _write(tmp_path, "sports_pairs", "2026-07-04",
           [_pair("blocked_key"), _pair("unmatched")])
    rep = A.live_lane(root=tmp_path, max_day="2026-07-31")
    assert rep["n_consecutive_trailing_all_blocked_days"] == 0


def test_anchor_events_are_distinct_events_not_rows(tmp_path):
    """240 anchor ROWS over 4 EVENTS is the whole point — a row count would overstate the
    re-test population ~60x."""
    _write(tmp_path, "sports_pairs", "2026-07-12",
           [_pair("matched", "KXWCGAME-A", bookmaker="pinnacle"),
            _pair("matched", "KXWCGAME-A", bookmaker="pinnacle"),
            _pair("matched", "KXWCGAME-B", bookmaker="pinnacle")])
    rep = A.live_lane(root=tmp_path, max_day="2026-07-31")
    assert rep["status_totals"]["matched"] == 3
    assert rep["n_anchor_events"] == 2
    assert rep["last_anchor_day"] == "2026-07-12"


def test_missing_odds_leg_is_its_own_status_not_silently_dropped(tmp_path):
    _write(tmp_path, "sports_pairs", "2026-07-04", [{"event_ticker": "X", "series": "Y"}])
    rep = A.live_lane(root=tmp_path, max_day="2026-07-31")
    assert rep["status_totals"]["<missing>"] == 1


# --------------------------------------------------------------------------- #
# 4. starvation diagnosis — the causes must stay separable
# --------------------------------------------------------------------------- #
def test_odds_api_constants_are_read_by_ast_not_imported():
    """The audit must not need `requests` installed to run (its contract is committed bytes
    only), and a rename of either literal must fail loudly rather than move a headline."""
    default_sports, by_series = A.odds_api_constants()
    assert default_sports == ("soccer_fifa_world_cup", "americanfootball_nfl",
                              "basketball_nba")
    assert by_series["KXMLBGAME"] == "baseball_mlb"


def test_odds_api_constants_raises_if_a_literal_is_renamed(tmp_path):
    d = tmp_path / "collection"
    d.mkdir(parents=True)
    (d / "odds_api.py").write_text('DEFAULT_SPORTS = ("a",)\n')
    with pytest.raises(RuntimeError, match="SPORT_KEY_BY_SERIES"):
        A.odds_api_constants(root=tmp_path)


def test_selector_forfeiture_is_measured_only_on_keyed_days_after_the_last_anchor(tmp_path):
    """On a blocked_key day the selector is MOOT — attributing the outage to it there
    would misdiagnose a missing credential as a config choice."""
    _write(tmp_path, "sports_pairs", "2026-07-12",
           [_pair("matched", "KXWCGAME-A", series="KXWCGAME", bookmaker="pinnacle")])
    _write(tmp_path, "sports_pairs", "2026-07-20", [_pair("blocked_key")])
    _write(tmp_path, "sports_pairs", "2026-07-22",
           [_pair("not_selected", "KXMLBGAME-1"), _pair("not_selected", "KXMLBGAME-2")])
    rep = A.starvation_diagnosis(root=tmp_path, max_day="2026-07-31")
    assert rep["last_anchor_day"] == "2026-07-12"
    assert rep["post_anchor_keyed_days"] == ["2026-07-22"]
    f = rep["selector_forfeiture"]["2026-07-22"]
    assert f["n_events_not_selected"] == 2
    assert f["n_rows_not_selected"] == 2
    assert f["n_rows_whose_series_is_in_default_sports"] == 0


def test_a_selected_sport_that_is_present_is_counted(tmp_path):
    """The 0 in `n_rows_whose_series_is_in_default_sports` is load-bearing: it says NO
    selected sport had a Kalshi game at all. A planted selected-sport row must move it."""
    _write(tmp_path, "sports_pairs", "2026-07-12",
           [_pair("matched", "KXWCGAME-A", series="KXWCGAME", bookmaker="pinnacle")])
    _write(tmp_path, "sports_pairs", "2026-07-22",
           [_pair("not_selected", "KXMLBGAME-1"),
            _pair("unmatched", "KXNBAGAME-1", series="KXNBAGAME")])
    rep = A.starvation_diagnosis(root=tmp_path, max_day="2026-07-31")
    assert rep["selector_forfeiture"]["2026-07-22"]["n_rows_whose_series_is_in_default_sports"] == 1


def test_every_not_selected_series_reports_the_sport_key_it_was_refused_for(tmp_path):
    """`not_selected` means the series IS mapped — the report must name the sport_key so a
    reader cannot confuse it with `unmapped_series`."""
    _write(tmp_path, "sports_pairs", "2026-07-12",
           [_pair("matched", "KXWCGAME-A", series="KXWCGAME", bookmaker="pinnacle")])
    _write(tmp_path, "sports_pairs", "2026-07-22", [_pair("not_selected", "KXMLBGAME-1")])
    ns = A.starvation_diagnosis(root=tmp_path,
                                max_day="2026-07-31")["selector_forfeiture"]["2026-07-22"]
    assert ns["not_selected_by_series"]["KXMLBGAME"]["sport_key"] == "baseball_mlb"


# --------------------------------------------------------------------------- #
# 5. re-test population — BOTH gates
# --------------------------------------------------------------------------- #
def test_retest_population_requires_both_depth_and_settlement(tmp_path):
    """Reporting either gate alone overstates the population; only the intersection is a
    scoreable unit."""
    _write(tmp_path, "sports_pairs", "2026-07-12",
           [_pair("matched", "KXWCGAME-A", bookmaker="pinnacle"),
            _pair("matched", "KXWCGAME-B", bookmaker="pinnacle")])
    _write(tmp_path, "orderbook_depth", "2026-07-12",
           [{"ticker": "KXWCGAME-A-ESP"}, {"ticker": "KXWCGAME-B-FRA"}])
    _write(tmp_path, "settlement_ledger", "2026-07-13",
           [{"ticker": "KXWCGAME-A-ESP", "result": "yes"}])
    rep = A.retest_population(root=tmp_path, max_day="2026-07-31")
    assert rep["n_anchor_events"] == 2
    assert rep["n_joinable_to_depth"] == 2
    assert rep["n_with_settlement"] == 1
    assert rep["n_passing_both_gates"] == 1
    assert rep["events_passing_both_gates"] == ["KXWCGAME-A"]
    assert rep["clears_l41_floor"] is False


def test_l41_floor_flag_flips_when_the_population_is_large_enough(tmp_path):
    rows, depth, settle = [], [], []
    for i in range(12):
        ev = f"KXWCGAME-{i:02d}"
        rows.append(_pair("matched", ev, bookmaker="pinnacle"))
        depth.append({"ticker": f"{ev}-ESP"})
        settle.append({"ticker": f"{ev}-ESP", "result": "yes"})
    _write(tmp_path, "sports_pairs", "2026-07-12", rows)
    _write(tmp_path, "orderbook_depth", "2026-07-12", depth)
    _write(tmp_path, "settlement_ledger", "2026-07-13", settle)
    rep = A.retest_population(root=tmp_path, max_day="2026-07-31")
    assert rep["n_passing_both_gates"] == 12
    assert rep["clears_l41_floor"] is True


def test_event_prefix_strips_only_the_outcome_token():
    assert A._event_prefix("KXWCGAME-26JUL14FRAESP-ESP") == "KXWCGAME-26JUL14FRAESP"
    assert A._event_prefix("NOHYPHEN") == "NOHYPHEN"
    assert A._event_prefix("") == ""


def test_clv_depth_overlap_finds_a_planted_overlap(tmp_path):
    """The real answer is 0; a detector that can only ever return 0 proves nothing (L155)."""
    _write(tmp_path, "sports_clv", "2026-07-03",
           [{"kalshi_event_ticker": "KXWCGAME-X", "outcomes": []}])
    _write(tmp_path, "orderbook_depth", "2026-07-08", [{"ticker": "KXWCGAME-X-ESP"}])
    rep = A.clv_depth_overlap(root=tmp_path, max_day="2026-07-31")
    assert rep["n_overlap"] == 1 and rep["overlap"] == ["KXWCGAME-X"]


# --------------------------------------------------------------------------- #
# acceptance — real committed tape, closed window
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def rep():
    return A.build_report(root=REPO_ROOT, max_day=WINDOW)


def test_acceptance_every_backfill_family_is_a_one_shot_with_no_scheduled_caller(rep):
    fams = rep["write_path_liveness"]["families"]
    for f in A.BACKFILL_FAMILIES:
        assert fams[f]["verdict"] == "one_shot_no_scheduled_caller", f
    assert fams["sports_pairs"]["verdict"] == "scheduled"


def test_acceptance_no_backfill_family_can_alert_on_staleness(rep):
    mc = rep["monitor_coverage"]
    assert mc["n_unmonitored_backfill_families"] == 5
    for f in A.BACKFILL_FAMILIES:
        assert mc["families"][f]["in_family_config"] is False, f
    # the live family IS monitored — which is exactly why the sub-field hole is invisible
    assert mc["families"]["sports_pairs"]["in_family_config"] is True
    assert mc["monitors_the_odds_leg_subfield"] is False


def test_acceptance_sports_clv_is_frozen_before_the_depth_tape_begins(rep):
    s = rep["clv_anchor_span"]
    assert s["n_records"] == 104
    assert s["n_distinct_events"] == 80
    assert s["n_outcome_rows"] == 309
    assert s["kickoff_max"] == "2026-07-03T22:00Z"
    # `tape/orderbook_depth/` begins 2026-07-07 -> the join is empty by construction (L43/L9)
    assert rep["clv_depth_overlap"]["n_clv_events"] == 80
    assert rep["clv_depth_overlap"]["n_overlap"] == 0


def test_acceptance_s21_longshot_denominators_are_reproduced(rep):
    """The S21 registry row quotes 81 (`fair_prob<=0.20`) and 83 (the `yes_ask<=0.20`
    proxy). The proxy reproduces EXACTLY; the fair-prob cut re-derives to 80, a 1-market
    discrepancy this audit did not resolve. Pinned as-measured so the gap stays visible
    rather than being quietly rounded to the registry's number (L155/L183)."""
    s = rep["clv_anchor_span"]
    assert s["n_markets_yes_ask_le_020"] == 83
    assert s["n_markets_fair_prob_le_020"] == 80


def test_acceptance_the_clv_record_tag_is_out_of_vocabulary_on_every_record(rep):
    oov = rep["backfill_lane"]["sports_clv"]["out_of_vocabulary_tags"]
    assert oov["price_source_tag=mixed"]["n"] == 104
    assert oov["price_source_tag=mixed"]["degrades_to"] == "synthetic"


def test_acceptance_live_anchor_lifetime_yield_is_four_events(rep):
    ll = rep["live_lane"]
    assert ll["status_totals"]["matched"] == 240
    assert ll["n_anchor_events"] == 4
    assert ll["anchor_events"] == ["KXWCGAME-26JUL14FRAESP", "KXWCGAME-26JUL15ENGARG",
                                   "KXWCGAME-26JUL18FRAENG", "KXWCGAME-26JUL19ESPARG"]
    assert ll["last_anchor_day"] == "2026-07-18"
    assert ll["anchor_days"] == ["2026-07-12", "2026-07-13", "2026-07-14", "2026-07-15",
                                 "2026-07-16", "2026-07-17", "2026-07-18"]
    # every anchor is Pinnacle, and the de-vigged fair prob is honestly `synthetic`
    assert set(ll["anchor_bookmakers"]) == {"pinnacle"}
    assert set(ll["anchor_price_source_tags"]) == {"synthetic"}


def test_acceptance_live_lane_denominator_and_outage_run(rep):
    ll = rep["live_lane"]
    # a same-day stranded sweep can only ADD rows on 2026-08-07, so assert directionally
    assert ll["n_records"] >= 148463
    assert ll["n_days"] == 35
    assert ll["n_distinct_events"] >= 2836
    assert ll["status_totals"]["blocked_key"] >= 105884
    assert ll["n_consecutive_trailing_all_blocked_days"] == 16
    assert ll["trailing_all_blocked_days"][0] == "2026-07-23"
    assert ll["trailing_all_blocked_days"][-1] == "2026-08-07"


def test_acceptance_the_selector_forfeits_in_season_mapped_games(rep):
    sd = rep["starvation_diagnosis"]
    assert sd["default_sports"] == ["soccer_fifa_world_cup", "americanfootball_nfl",
                                    "basketball_nba"]
    assert sd["n_mapped_series"] == 16
    assert sd["n_mapped_series_reachable_by_default"] == 3
    assert sd["post_anchor_keyed_days"] == ["2026-07-21", "2026-07-22"]
    f = sd["selector_forfeiture"]["2026-07-22"]
    assert f["n_events_not_selected"] == 133
    assert f["n_rows_not_selected"] == 2031
    # the load-bearing zero: not one row of a SELECTED sport existed to spend a credit on
    assert f["n_rows_whose_series_is_in_default_sports"] == 0
    assert sd["selector_forfeiture"]["2026-07-21"][
        "n_rows_whose_series_is_in_default_sports"] == 0
    assert f["not_selected_by_series"]["KXMLBGAME"]["sport_key"] == "baseball_mlb"


def test_acceptance_retest_population_is_one_unit_far_below_the_l41_floor(rep):
    rp = rep["retest_population"]
    assert rp["n_anchor_events"] == 4
    # the L43/L9 blocker that killed S21 is GONE for these four: all four have depth tape
    assert rp["n_joinable_to_depth"] == 4
    for ev, d in rp["per_event"].items():
        assert d["n_depth_days"] >= 4, ev
    # but only one carries an ex-post settlement anywhere on committed tape
    assert rp["n_with_settlement"] == 1
    assert rp["n_passing_both_gates"] == 1
    assert rp["events_passing_both_gates"] == ["KXWCGAME-26JUL14FRAESP"]
    assert rp["clears_l41_floor"] is False
