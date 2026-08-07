"""Offline tests for scripts/sports_pairs_close_proximity_audit.py (idle-run policy (c)
data-quality deep-dive on `tape/sports_pairs/`).

No network anywhere. Two classes of test:

* pure-function tests over hand-built records, which pin each DETECTOR by feeding it a
  synthetic defect (L191's shape) AND a synthetic clean case -- a detector that has only
  ever seen healthy input is untested. The load-bearing ones are the availability
  correction (a game whose kickoff is beyond the tape end must be EXCLUDED, not scored as
  a huge gap) and the provable-dropout rule (a covering pass must exist and must cover the
  game's OWN series before the game may be called dropped);
* `test_acceptance_*` tests over committed tape. `tape/sports_pairs/` is actively collected
  every hourly pass, so acceptance assertions are DIRECTIONAL (bounds and invariants, not
  equalities) per the `q51_trade_tape_quality` / `crypto_hourly_settlement_audit` precedent
  -- an acceptance test a future hourly pass or stranded-branch sweep would break is a test
  that would be deleted.
"""
from __future__ import annotations

import json

import pytest

from scripts import sports_pairs_close_proximity_audit as A


# --------------------------------------------------------------------------- #
# fixture builders
# --------------------------------------------------------------------------- #
def _rec(event_ticker, captured_at, game_start, series="KXTESTGAME", capture_id=None,
         schema=A.V2, game_date=None, odds_status="blocked_key", n_out=2):
    r = {
        "schema_version": schema,
        "capture_id": capture_id or captured_at.replace("-", "").replace(":", "")[:15] + "Z",
        "captured_at": captured_at,
        "series": series,
        "event_ticker": event_ticker,
        "game_date": game_date or (game_start or captured_at)[:10],
        "completeness_ok": True,
        "odds_leg": {"status": odds_status},
        "outcomes": [{"ticker": f"{event_ticker}-{i}", "yes_ask": 0.5,
                      "price_source_tag": "real_ask"} for i in range(n_out)],
    }
    if game_start is not None:
        r["game_start"] = game_start
    return r


def _closing_pass(at, series="KXTESTGAME", capture_id="ZZ"):
    """A later pass on the same series, so the game under test is NOT right-censored by the
    tape's end. Its own game is far in the future and is itself excluded by the correction."""
    return _rec("FILLER", at, "2099-01-01T00:00:00Z", series=series, capture_id=capture_id)


def _write_day(tmp_path, day, lines):
    d = tmp_path / "sports_pairs"
    d.mkdir(exist_ok=True)
    (d / f"dt={day}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    return d


# --------------------------------------------------------------------------- #
# loading / L25 file-shape gating
# --------------------------------------------------------------------------- #
def test_load_reads_only_canonical_day_files_and_reports_the_rest(tmp_path):
    d = _write_day(tmp_path, "2026-08-01", [_rec("E1", "2026-08-01T00:00:00Z", "2026-08-01T02:00:00Z")])
    (d / "dt=2026-07-09").mkdir()
    (d / "_manifest.jsonl").write_text("{}\n", encoding="utf-8")
    recs, diag = A.load_records(d)
    assert len(recs) == 1
    assert diag["n_day_files"] == 1
    assert set(diag["non_canonical_entries"]) == {"dt=2026-07-09/", "_manifest.jsonl"}


def test_load_drops_byte_identical_duplicate_lines_and_counts_them_per_day_file(tmp_path):
    r = _rec("E1", "2026-08-01T00:00:00Z", "2026-08-01T02:00:00Z")
    d = _write_day(tmp_path, "2026-08-01", [r, r, r])
    recs, diag = A.load_records(d)
    assert len(recs) == 1
    assert diag["n_duplicate_lines_dropped"] == 2
    assert diag["duplicate_lines_by_day_file"] == {"dt=2026-08-01.jsonl": 2}


def test_load_counts_json_invalid_without_aborting(tmp_path):
    d = _write_day(tmp_path, "2026-08-01", [_rec("E1", "2026-08-01T00:00:00Z", "2026-08-01T02:00:00Z")])
    with open(d / "dt=2026-08-01.jsonl", "a", encoding="utf-8") as f:
        f.write("{not json\n")
    recs, diag = A.load_records(d)
    assert len(recs) == 1 and diag["n_json_invalid"] == 1


# --------------------------------------------------------------------------- #
# availability correction -- the L302 class
# --------------------------------------------------------------------------- #
def test_availability_correction_excludes_a_game_whose_kickoff_is_past_the_tape_end():
    recs = [
        _rec("PAST", "2026-08-01T00:00:00Z", "2026-08-01T02:00:00Z"),
        _rec("PAST", "2026-08-01T01:00:00Z", "2026-08-01T02:00:00Z"),
        # kickoff four days after the last capture: its terminal gap is a tape-end artifact
        _rec("FUTURE", "2026-08-01T01:00:00Z", "2026-08-05T12:00:00Z"),
        _rec("PAST", "2026-08-01T03:00:00Z", "2026-08-01T02:00:00Z"),
    ]
    reached, window = A.reached_games(A.game_index(recs))
    assert set(reached) == {"PAST"}
    assert window["n_all"] == 2 and window["n_reached"] == 1
    assert window["n_excluded_kickoff_outside_window"] == 1


def test_uncorrected_pooling_would_have_inflated_the_median_gap():
    """The correction must actually MOVE the number -- otherwise it is decoration."""
    recs = [
        _rec("PAST", "2026-08-01T01:30:00Z", "2026-08-01T02:00:00Z"),
        _rec("FUTURE", "2026-08-01T01:30:00Z", "2026-08-09T02:00:00Z"),
        _rec("PAST", "2026-08-01T04:00:00Z", "2026-08-01T02:00:00Z"),
    ]
    games = A.game_index(recs)
    reached, _ = A.reached_games(games)
    corrected = A.close_proximity(reached)["terminal_gap_min_percentiles"]["p50"]
    uncorrected = A.close_proximity(games)["terminal_gap_min_percentiles"]["p50"]
    assert corrected == 30.0
    assert uncorrected > corrected


# --------------------------------------------------------------------------- #
# close_proximity
# --------------------------------------------------------------------------- #
def test_terminal_gap_uses_the_last_pre_kickoff_capture_not_the_last_capture():
    recs = [
        _rec("E1", "2026-08-01T00:00:00Z", "2026-08-01T02:00:00Z"),
        _rec("E1", "2026-08-01T01:30:00Z", "2026-08-01T02:00:00Z"),
        _rec("E1", "2026-08-01T03:00:00Z", "2026-08-01T02:00:00Z"),  # in-game, must not count
    ]
    reached, _ = A.reached_games(A.game_index(recs))
    cp = A.close_proximity(reached)
    assert cp["terminal_gap_min_percentiles"]["p50"] == 30.0
    assert cp["n_games_with_post_kickoff_capture"] == 1


def test_proximity_buckets_are_cumulative_and_monotone():
    recs = [_rec(f"E{i}", "2026-08-01T00:00:00Z", f"2026-08-01T0{i}:00:00Z") for i in (1, 2, 3)]
    recs.append(_closing_pass("2026-08-01T09:00:00Z"))
    reached, _ = A.reached_games(A.game_index(recs))
    b = A.close_proximity(reached)["proximity_buckets"]
    ns = [b[f"le_{t}_min"]["n"] for t in A.PROXIMITY_THRESHOLDS_MIN]
    assert ns == sorted(ns)


def test_a_game_with_only_post_kickoff_captures_is_counted_not_silently_dropped():
    recs = [_rec("E1", "2026-08-01T03:00:00Z", "2026-08-01T02:00:00Z"),
            _rec("E2", "2026-08-01T01:00:00Z", "2026-08-01T02:00:00Z")]
    reached, _ = A.reached_games(A.game_index(recs))
    cp = A.close_proximity(reached)
    assert cp["n_games_no_pre_kickoff_capture"] == 1
    assert cp["n_games_scored"] == 1


# --------------------------------------------------------------------------- #
# cadence null
# --------------------------------------------------------------------------- #
def test_cadence_null_is_not_rejected_when_every_game_is_captured_on_every_pass():
    """Dense uniform capture right up to kickoff: observed near-close availability should
    match the null, so `null_rejected` must be False. This is the detector's clean case."""
    recs = []
    for h in range(0, 12):
        for i in (1, 2):
            recs.append(_rec(f"E{i}", f"2026-08-01T{h:02d}:00:00Z", "2026-08-01T12:00:00Z",
                             capture_id=f"C{h:02d}"))
    recs.append(_closing_pass("2026-08-01T13:00:00Z"))
    reached, _ = A.reached_games(A.game_index(recs))
    cn = A.cadence_null(reached, A.pass_index(recs))
    assert cn["n_games_scored"] == 2
    assert cn["null_rejected"] is False


def test_cadence_null_is_rejected_when_games_vanish_long_before_kickoff():
    recs = []
    for h in range(0, 12):
        recs.append(_rec("KEEP", f"2026-08-01T{h:02d}:00:00Z", "2026-08-01T12:00:00Z",
                         capture_id=f"C{h:02d}"))
        if h <= 5:  # the other game disappears at 05:00, six hours before kickoff
            recs.append(_rec("GONE", f"2026-08-01T{h:02d}:00:00Z", "2026-08-01T12:00:00Z",
                             capture_id=f"C{h:02d}"))
    recs.append(_closing_pass("2026-08-01T13:00:00Z"))
    reached, _ = A.reached_games(A.game_index(recs))
    cn = A.cadence_null(reached, A.pass_index(recs))
    assert cn["shortfall_ratio"] is not None and cn["shortfall_ratio"] > 1.0


def test_cadence_null_refuses_a_game_with_too_few_local_passes():
    recs = [_rec("E1", "2026-08-01T11:00:00Z", "2026-08-01T12:00:00Z"),
            _closing_pass("2026-08-01T13:00:00Z")]
    reached, _ = A.reached_games(A.game_index(recs))
    assert A.cadence_null(reached, A.pass_index(recs))["n_games_scored"] == 0


# --------------------------------------------------------------------------- #
# provable pre-kickoff dropout
# --------------------------------------------------------------------------- #
def test_dropout_requires_a_covering_pass_and_names_it():
    recs = [
        _rec("GONE", "2026-08-01T00:00:00Z", "2026-08-01T03:00:00Z", capture_id="P1"),
        _rec("STAY", "2026-08-01T00:00:00Z", "2026-08-01T03:00:00Z", capture_id="P1"),
        _rec("STAY", "2026-08-01T02:00:00Z", "2026-08-01T03:00:00Z", capture_id="P2"),
        _closing_pass("2026-08-01T04:00:00Z", capture_id="P3"),
    ]
    reached, _ = A.reached_games(A.game_index(recs))
    dr = A.pre_kickoff_dropout(reached, A.pass_index(recs))
    assert dr["n_provably_dropped_pre_kickoff"] == 1
    assert dr["n_cadence_limited_only"] == 1
    ex = [e for e in dr["examples"] if e["event_ticker"] == "GONE"][0]
    assert ex["first_missed_pass"] == "P2"
    assert ex["drop_lead_lower_bound_min"] == 60.0


def test_a_pass_that_did_not_cover_the_series_never_proves_a_drop():
    """A pass that failed to fetch this game's OWN series is evidence of nothing -- counting
    it would manufacture dropouts out of series-level fetch errors."""
    recs = [
        _rec("GONE", "2026-08-01T00:00:00Z", "2026-08-01T03:00:00Z", series="KXA", capture_id="P1"),
        _rec("OTHER", "2026-08-01T00:00:00Z", "2026-08-01T03:00:00Z", series="KXB", capture_id="P1"),
        _rec("OTHER", "2026-08-01T02:00:00Z", "2026-08-01T03:00:00Z", series="KXB", capture_id="P2"),
        _closing_pass("2026-08-01T04:00:00Z", series="KXB", capture_id="P3"),
    ]
    reached, _ = A.reached_games(A.game_index(recs))
    dr = A.pre_kickoff_dropout(reached, A.pass_index(recs))
    assert dr["n_provably_dropped_pre_kickoff"] == 0


def test_a_pass_after_kickoff_never_proves_a_pre_kickoff_drop():
    recs = [
        _rec("E1", "2026-08-01T00:00:00Z", "2026-08-01T03:00:00Z", capture_id="P1"),
        _rec("E2", "2026-08-01T00:00:00Z", "2026-08-01T09:00:00Z", capture_id="P1"),
        _rec("E2", "2026-08-01T04:00:00Z", "2026-08-01T09:00:00Z", capture_id="P2"),
        _closing_pass("2026-08-01T10:00:00Z", capture_id="P3"),
    ]
    reached, _ = A.reached_games(A.game_index(recs))
    dr = A.pre_kickoff_dropout(reached, A.pass_index(recs))
    assert dr["n_provably_dropped_pre_kickoff"] == 0


# --------------------------------------------------------------------------- #
# field hazards
# --------------------------------------------------------------------------- #
def test_v1_records_are_counted_as_structurally_unanswerable_not_as_zero_gap():
    recs = [_rec("E1", "2026-08-01T00:00:00Z", None, schema="sports_pairs.v1"),
            _rec("E2", "2026-08-01T00:00:00Z", "2026-08-01T02:00:00Z")]
    fh = A.field_hazards(recs)
    assert fh["frac_records_without_game_start"] == 0.5
    assert A.game_index(recs).keys() == {"E2"}


def test_game_date_vs_utc_kickoff_offset_is_measured_with_its_hour_profile():
    recs = [_rec("E1", "2026-08-01T20:00:00Z", "2026-08-02T01:00:00Z", game_date="2026-08-01"),
            _rec("E2", "2026-08-01T10:00:00Z", "2026-08-01T18:00:00Z", game_date="2026-08-01")]
    fh = A.field_hazards(recs)
    assert fh["n_game_date_disagrees_with_utc_kickoff_date"] == 1
    assert fh["game_date_minus_game_start_utc_date_days"] == {"0": 1, "1": 1}
    assert fh["utc_hour_of_disagreeing_kickoffs"] == {"1": 1}


def test_untagged_outcome_prices_are_reported_as_untagged_never_assumed_real():
    r = _rec("E1", "2026-08-01T00:00:00Z", "2026-08-01T02:00:00Z")
    del r["outcomes"][0]["price_source_tag"]
    fh = A.field_hazards([r])
    assert fh["price_source_tags"]["<untagged>"] == 1


def test_capture_cadence_reports_missing_calendar_days():
    recs = [_rec("E1", "2026-08-01T00:00:00Z", "2026-08-01T02:00:00Z", capture_id="P1"),
            _rec("E1", "2026-08-03T00:00:00Z", "2026-08-03T02:00:00Z", capture_id="P2")]
    assert A.capture_cadence(recs)["missing_calendar_days"] == ["2026-08-02"]


# --------------------------------------------------------------------------- #
# acceptance -- committed tape, DIRECTIONAL only
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def real_report():
    if not A.TAPE_DIR.exists() or not A.canonical_day_files(A.TAPE_DIR):
        pytest.skip("tape/sports_pairs/ not present")
    return A.build_report(A.TAPE_DIR)


def test_acceptance_availability_correction_never_grows_the_population(real_report):
    w = real_report["availability_window"]
    assert 0 < w["n_reached"] <= w["n_all"]
    assert w["n_excluded_kickoff_outside_window"] == w["n_all"] - w["n_reached"]


def test_acceptance_every_committed_outcome_price_is_real_ask(real_report):
    assert set(real_report["field_hazards"]["price_source_tags"]) == {"real_ask"}


def test_acceptance_no_json_invalid_lines_on_committed_tape(real_report):
    assert real_report["load"]["n_json_invalid"] == 0


def test_acceptance_dropout_and_cadence_only_partition_the_scored_population(real_report):
    dr = real_report["pre_kickoff_dropout"]
    assert dr["n_provably_dropped_pre_kickoff"] + dr["n_cadence_limited_only"] == dr["n_games_scored"]


def test_acceptance_near_close_substrate_is_a_minority_of_the_family(real_report):
    """The finding this module exists to record: a near-close (<=60 min) observation is the
    EXCEPTION on this tape, not the rule. Directional bound, not the point estimate."""
    cp = real_report["close_proximity"]
    assert cp["proximity_buckets"][f"le_{A.NEAR_CLOSE_MIN}_min"]["frac"] < 0.5
    assert cp["terminal_gap_min_percentiles"]["p50"] > A.NEAR_CLOSE_MIN


def test_acceptance_the_cadence_null_is_rejected_on_committed_tape(real_report):
    cn = real_report["cadence_null"]
    assert cn["n_games_scored"] > 0
    assert cn["null_rejected"] is True
    assert cn["shortfall_ratio"] > 2.0
