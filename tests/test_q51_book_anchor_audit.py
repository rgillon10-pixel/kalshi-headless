"""Tests for `scripts/q51_book_anchor_audit.py`.

Two layers, as on `tests/test_q51_trade_tape_quality.py`:

* fixture unit tests — pure, no tape, they pin the SEMANTICS of the two anchor criteria and
  of the panel verdict, including the boundary cases the headline numbers turn on;
* `test_acceptance_*` over committed tape — `tape/kalshi_trades/dt=2026-08-03.jsonl` is a
  frozen past day (the collector dedupes on `trade_id`, so it cannot legitimately change),
  which is why the CONTROL can be pinned exactly. The book side is NOT frozen, so every
  book-derived acceptance assertion is a DIRECTIONAL BOUND, never an equality.
"""
from __future__ import annotations

import json

import pytest

from scripts import q51_book_anchor_audit as A
from scripts.q51_maker_fillsim import MIN_UNITS


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def pr(*ts):
    return [{"ts": float(t)} for t in ts]


MIN = 60.0


# --------------------------------------------------------------------------- #
# anchor criteria
# --------------------------------------------------------------------------- #
def test_bracket_requires_two_observations_prior_requires_one():
    """THE criterion difference, isolated. One observation before the print is worthless to
    L280's bracket rule and sufficient for a fill-sim's resting price."""
    prints = {"T": pr(100 * MIN)}
    snaps = {"T": [90 * MIN]}
    assert A.anchor_coverage(prints, snaps, A.BRACKET)["n_usable"] == 0
    assert A.anchor_coverage(prints, snaps, A.BRACKET)["n_ticker_under_two_observations"] == 1
    assert A.anchor_coverage(prints, snaps, A.PRIOR)["n_usable"] == 1


def test_bracket_rejects_prints_after_the_last_observation():
    prints = {"T": pr(300 * MIN)}
    snaps = {"T": [10 * MIN, 20 * MIN]}
    r = A.anchor_coverage(prints, snaps, A.BRACKET)
    assert r["n_usable"] == 0 and r["n_after_last_observation"] == 1


def test_prior_accepts_prints_after_the_last_observation_but_ages_them():
    """The relaxed criterion's entire cost: it admits arbitrarily stale anchors, so the age
    must travel with the count."""
    prints = {"T": pr(300 * MIN)}
    snaps = {"T": [10 * MIN, 20 * MIN]}
    r = A.anchor_coverage(prints, snaps, A.PRIOR)
    assert r["n_usable"] == 1
    assert r["median_anchor_age_min"] == pytest.approx(280.0)
    assert r["freshness_ladder"]["within_15min"]["n"] == 0


def test_never_observed_ticker_is_its_own_bucket_not_a_silent_drop():
    r = A.anchor_coverage({"T": pr(5 * MIN)}, {}, A.PRIOR)
    assert r["n_ticker_never_observed"] == 1
    assert r["buckets_partition_the_tape"] is True


def test_print_before_every_observation_is_its_own_bucket():
    r = A.anchor_coverage({"T": pr(1 * MIN)}, {"T": [5 * MIN, 9 * MIN]}, A.PRIOR)
    assert r["n_before_first_observation"] == 1 and r["n_usable"] == 0


def test_buckets_partition_the_tape_under_both_criteria():
    prints = {"A": pr(1 * MIN, 50 * MIN, 900 * MIN), "B": pr(7 * MIN), "C": pr(3 * MIN)}
    snaps = {"A": [10 * MIN, 60 * MIN], "B": [1 * MIN]}
    for c in (A.BRACKET, A.PRIOR):
        r = A.anchor_coverage(prints, snaps, c)
        assert r["buckets_partition_the_tape"] is True
        assert r["n_prints"] == 5


def test_prior_is_never_stricter_than_bracket():
    """A property, not an example: PRIOR relaxes BRACKET's two extra conditions, so its
    usable count dominates. If this ever inverts, the criteria are mis-implemented."""
    prints = {"A": pr(1 * MIN, 50 * MIN, 900 * MIN), "B": pr(7 * MIN), "C": pr(3 * MIN)}
    snaps = {"A": [10 * MIN, 60 * MIN], "B": [1 * MIN]}
    assert (A.anchor_coverage(prints, snaps, A.PRIOR)["n_usable"]
            >= A.anchor_coverage(prints, snaps, A.BRACKET)["n_usable"])


def test_freshness_ladder_is_monotone_in_the_rung():
    prints = {"A": pr(20 * MIN, 70 * MIN, 200 * MIN, 800 * MIN)}
    snaps = {"A": [0.0, 19 * MIN, 60 * MIN, 100 * MIN, 700 * MIN]}
    lad = A.anchor_coverage(prints, snaps, A.PRIOR)["freshness_ladder"]
    ns = [lad[f"within_{int(r)}min"]["n"] for r in A.FRESHNESS_RUNGS]
    assert ns == sorted(ns)


def test_ages_are_none_when_nothing_is_usable():
    r = A.anchor_coverage({"T": pr(5 * MIN)}, {}, A.BRACKET)
    assert r["median_anchor_age_min"] is None and r["p90_anchor_age_min"] is None


def test_unknown_criterion_raises_rather_than_guessing():
    with pytest.raises(ValueError):
        A.anchor_coverage({}, {}, "whatever")


# --------------------------------------------------------------------------- #
# panel profile
# --------------------------------------------------------------------------- #
def _write_sweep(tmp_path, day, rows):
    p = tmp_path / f"dt={day}.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return tmp_path


def _row(tk, cap, ts, tag="real_ask"):
    return {"ticker": tk, "capture_id": cap, "captured_at": ts, "price_source_tag": tag}


def test_rotating_census_is_not_a_panel():
    """The structural verdict: disjoint ticker slices per capture => modal ticker observed
    once => the family can never supply a second look at anything."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        root = _write_sweep(Path(td), "2026-01-01", [
            _row("A", "c1", "2026-01-01T00:00:00+00:00"),
            _row("B", "c1", "2026-01-01T00:00:00+00:00"),
            _row("C", "c2", "2026-01-01T06:00:00+00:00"),
            _row("D", "c2", "2026-01-01T06:00:00+00:00"),
        ])
        r = A.sweep_panel_profile(["2026-01-01"], tape_root=root)
    assert r["is_panel"] is False
    assert r["frac_tickers_observed_once"] == 1.0
    assert r["max_observations_per_ticker"] == 1
    assert r["n_tickers_ever_revisited"] == 0


def test_a_repeating_sweep_is_a_panel():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        root = _write_sweep(Path(td), "2026-01-01", [
            _row("A", "c1", "2026-01-01T00:00:00+00:00"),
            _row("B", "c1", "2026-01-01T00:00:00+00:00"),
            _row("A", "c2", "2026-01-01T06:00:00+00:00"),
            _row("B", "c2", "2026-01-01T06:00:00+00:00"),
        ])
        r = A.sweep_panel_profile(["2026-01-01"], tape_root=root)
    assert r["is_panel"] is True and r["n_tickers_ever_revisited"] == 2


def test_panel_profile_reports_untagged_prices_as_untagged():
    """CLAUDE.md trust default: a missing tag is never quietly treated as a real price."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        root = _write_sweep(Path(td), "2026-01-01",
                            [{"ticker": "A", "capture_id": "c1",
                              "captured_at": "2026-01-01T00:00:00+00:00"}])
        r = A.sweep_panel_profile(["2026-01-01"], tape_root=root)
    assert r["price_source_tag_census"] == {"__untagged__": 1}


def test_panel_profile_flags_captures_at_the_row_cap():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        root = _write_sweep(Path(td), "2026-01-01",
                            [_row(f"T{i}", "c1", "2026-01-01T00:00:00+00:00")
                             for i in range(3)])
        r = A.sweep_panel_profile(["2026-01-01"], tape_root=root)
    assert r["per_day"]["2026-01-01"]["all_captures_at_cap"] is False
    assert r["frac_captures_at_row_cap"] == 0.0


def test_panel_profile_on_absent_days_is_honest_not_a_guess():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        r = A.sweep_panel_profile(["2026-01-01"], tape_root=Path(td))
    assert r["is_panel"] is None and r["n_lines"] == 0


def test_load_sweep_sorts_and_skips_unusable_lines():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        root = _write_sweep(Path(td), "2026-01-01", [
            _row("A", "c2", "2026-01-01T06:00:00+00:00"),
            _row("A", "c1", "2026-01-01T00:00:00+00:00"),
            {"ticker": "A", "capture_id": "c3", "captured_at": "not-a-time"},
            {"capture_id": "c4", "captured_at": "2026-01-01T09:00:00+00:00"},
        ])
        s = A.load_sweep(["2026-01-01"], tape_root=root)
    assert list(s) == ["A"] and s["A"] == sorted(s["A"]) and len(s["A"]) == 2


def test_union_snaps_merges_and_sorts():
    u = A.union_snaps({"A": [3.0, 1.0]}, {"A": [2.0], "B": [9.0]})
    assert u["A"] == [1.0, 2.0, 3.0] and u["B"] == [9.0]


# --------------------------------------------------------------------------- #
# coverage weighting + resample units
# --------------------------------------------------------------------------- #
def test_ticker_coverage_is_print_weighted_not_just_ticker_counted():
    """A family covering only the QUIET tickers must not look half-good."""
    prints = {"LOUD": pr(*range(100)), "QUIET": pr(1.0)}
    f = A.ticker_coverage(prints, {"fam": {"QUIET": [0.0]}})["families"]["fam"]
    assert f["frac_print_tickers_covered"] == 0.5
    assert f["frac_prints_on_covered_tickers"] < 0.02


def test_resample_units_are_games_not_tickers():
    """L6: two outcomes of one game are one unit, never two."""
    prints = {"KXG-26AUG03AAABBB-AAA": pr(10 * MIN),
              "KXG-26AUG03AAABBB-BBB": pr(10 * MIN)}
    snaps = {t: [9 * MIN] for t in prints}
    r = A.fresh_anchor_unit_profile(prints, snaps)
    assert r["n_fresh_anchored_prints"] == 2 and r["n_resample_units"] == 1


def test_resample_units_respect_the_freshness_bound():
    prints = {"KXG-26AUG03AAABBB-AAA": pr(100 * MIN)}
    snaps = {"KXG-26AUG03AAABBB-AAA": [80 * MIN]}
    assert A.fresh_anchor_unit_profile(prints, snaps, 15.0)["n_resample_units"] == 0
    assert A.fresh_anchor_unit_profile(prints, snaps, 60.0)["n_resample_units"] == 1


def test_unit_floor_boundary_matches_the_repo_floor():
    prints = {f"KXG-26AUG03G{i}-A": pr(10 * MIN) for i in range(MIN_UNITS)}
    snaps = {t: [9 * MIN] for t in prints}
    r = A.fresh_anchor_unit_profile(prints, snaps)
    assert r["min_units_floor"] == MIN_UNITS and r["clears_unit_floor"] is True
    one_short = dict(list(prints.items())[:-1])
    assert A.fresh_anchor_unit_profile(
        one_short, snaps)["clears_unit_floor"] is False


# --------------------------------------------------------------------------- #
# acceptance — committed tape
# --------------------------------------------------------------------------- #
DAY = "2026-08-03"


@pytest.fixture(scope="module")
def real():
    prints = A.load_prints(DAY)
    return prints, A.load_depth_ts([DAY])


def test_acceptance_the_l280_control_reproduces_exactly(real):
    """If this drifts, every other number in this module is void — L280's 10.1% is the only
    published figure the two implementations share."""
    prints, depth = real
    r = A.anchor_coverage(prints, depth, A.BRACKET)
    assert r["n_prints"] == 39698
    assert r["frac_usable"] == pytest.approx(0.101, abs=0.001)
    assert r["buckets_partition_the_tape"] is True


def test_acceptance_orderbook_depth_covers_every_print_ticker(real):
    """THE re-scoping: the print-side hole is NOT a breadth hole. The depth family already
    holds every ticker that printed; what it lacks is a second, timely look."""
    prints, depth = real
    c = A.ticker_coverage(prints, {"depth": depth})["families"]["depth"]
    assert c["frac_print_tickers_covered"] == 1.0
    assert c["frac_prints_on_covered_tickers"] == 1.0


def test_acceptance_universe_sweep_covers_none_of_the_print_tickers(real):
    """The obvious breadth fix, measured and dead: 652 MB of full-universe top-of-book
    contributes zero anchors to the print tape."""
    prints, _ = real
    sweep = A.load_sweep(A.adjacent_days(DAY))
    assert sweep, "universe_sweep tape is present"
    c = A.ticker_coverage(prints, {"sweep": sweep})["families"]["sweep"]
    assert c["n_print_tickers_covered"] == 0


def test_acceptance_universe_sweep_is_not_a_panel():
    """Structural, and the reason the previous test can never improve: the sweep rotates a
    cap-bound slice and (almost) never looks at the same market twice."""
    r = A.sweep_panel_profile(["2026-08-02", "2026-08-03"])
    assert r["is_panel"] is False
    assert r["max_observations_per_ticker"] == 1
    assert r["per_day"]["2026-08-03"]["all_captures_at_cap"] is True


def test_acceptance_relaxing_the_criterion_buys_coverage_but_not_freshness(real):
    """The honest reading of the 10.1% -> 99.85% jump: nearly every print has SOME prior
    quote, and almost none has a fresh one. Directional bounds — the book side is live."""
    prints, depth = real
    p = A.anchor_coverage(prints, depth, A.PRIOR)
    assert p["frac_usable"] > 0.90
    assert p["freshness_ladder"]["within_15min"]["frac"] < 0.05
    assert p["median_anchor_age_min"] > 60.0


def test_acceptance_the_fresh_anchored_population_clears_the_unit_floor(real):
    """The constructive half: even at a 15-minute anchor bound the committed tape yields
    more resample units than the repo's own floor, so a fresh-quote fill-sim is not
    ruled out by adequacy on this day."""
    prints, depth = real
    r = A.fresh_anchor_unit_profile(prints, depth, 15.0)
    assert r["clears_unit_floor"] is True
    assert r["n_resample_units"] >= MIN_UNITS
