"""Offline tests for scripts/q51_m3_preflight.py (Q51 milestone-3 data-adequacy pre-flight).

No network. Two tiers:

  * UNIT tests over hand-built synthetic fixtures — interval counting, the
    cumulative-by-close-day roll-up, the L41 floor verdict, the "closed but fewer than 2
    snapshots contributes nothing" case, and empty/garbage settlement input.
  * HARD `test_acceptance_*` cases over the committed, frozen `dt=2026-08-03` slice.

WHICH ACCEPTANCE ASSERTIONS ARE EXACT AND WHY
---------------------------------------------
EXACT: everything sourced from `tape/q51_settlement_cache/settlement-m2-2026-08-04.json`
(a hand-frozen snapshot of a completed pull — nothing writes to it) and from the
`trade_id`-deduped `tape/kalshi_trades/dt=2026-08-03.jsonl` (a past day).

DIRECTIONAL BOUNDS: everything sourced from `tape/orderbook_depth/dt=2026-08-03.jsonl`,
i.e. the interval counts and therefore the projected unit/leg counts. That day file is a
PAST day but it is NOT closed to growth: a later stranded-branch sweep (LOOP-QUEUE step 0b)
can legitimately union-append snapshots the cloud collector stranded, which would raise
snapshot counts and hence interval counts. Per L280's enforcement precedent, an acceptance
test that a legitimate tape sweep would break is a test that gets deleted — so the
book-side numbers are asserted as `>=` with the observed 2026-08-05 values, plus the
sign-of-the-conclusion assertions (the 08-10 firing clears the L41 floor; the queue's
"~57 units" is the terminal row, not the 08-10 row) which more tape can only strengthen.

This module asserts NO mean, NO CI and NO P&L: the pre-flight computes none.
"""
from __future__ import annotations

import json

from scripts import q51_m3_preflight as P
from scripts import q51_maker_fillsim as M


# --------------------------------------------------------------------------- #
# unit tests on synthetic fixtures
# --------------------------------------------------------------------------- #
def _snaps(**kw):
    """ticker -> list of n placeholder snapshots (only the length matters here)."""
    return {t: [{"ts": float(i)} for i in range(n)] for t, n in kw.items()}


def test_interval_counts_is_consecutive_pairs_not_snapshot_count():
    snaps = _snaps(A=5, B=2, C=1, D=0)
    ivs = P.interval_counts(["A", "B", "C", "D"], snaps)
    assert ivs == {"A": 4, "B": 1, "C": 0, "D": 0}


def test_interval_counts_handles_a_ticker_absent_from_the_depth_tape():
    assert P.interval_counts(["MISSING"], {}) == {"MISSING": 0}


def test_close_day_extracts_the_utc_calendar_day():
    assert P.close_day({"close_time": "2026-08-09T23:59:59Z"}) == "2026-08-09"
    assert P.close_day({"close_time": ""}) is None
    assert P.close_day({}) is None
    assert P.close_day(None) is None


def test_cumulative_roll_up_is_monotone_and_counts_games_not_outcomes():
    # two outcome legs of ONE game must collapse to ONE bootstrap unit (L6)
    universe = ["KXG-26AUG05AB-A", "KXG-26AUG05AB-B", "KXH-26AUG07CD-C"]
    snaps = _snaps(**{"KXG-26AUG05AB-A": 3, "KXG-26AUG05AB-B": 3, "KXH-26AUG07CD-C": 2})
    ivs = P.interval_counts(universe, snaps)
    settlement = {
        "KXG-26AUG05AB-A": {"close_time": "2026-08-05T00:00:00Z"},
        "KXG-26AUG05AB-B": {"close_time": "2026-08-05T00:00:00Z"},
        "KXH-26AUG07CD-C": {"close_time": "2026-08-07T00:00:00Z"},
    }
    table = P.cumulative_by_close_day(universe, ivs, settlement)
    assert [r["close_day"] for r in table] == ["2026-08-05", "2026-08-07"]
    assert table[0]["markets_closed"] == 2 and table[0]["game_units"] == 1
    assert table[0]["intervals"] == 4 and table[0]["legs"] == 8
    assert table[1]["markets_closed"] == 3 and table[1]["game_units"] == 2
    # cumulative => never decreasing
    for a, b in zip(table[:-1], table[1:]):
        assert b["markets_closed"] >= a["markets_closed"]
        assert b["game_units"] >= a["game_units"]
        assert b["legs"] >= a["legs"]


def test_a_closed_market_with_fewer_than_two_snapshots_contributes_nothing():
    universe = ["KXG-26AUG05AB-A", "KXG-26AUG05ZZ-Z"]
    snaps = _snaps(**{"KXG-26AUG05AB-A": 3, "KXG-26AUG05ZZ-Z": 1})
    ivs = P.interval_counts(universe, snaps)
    settlement = {t: {"close_time": "2026-08-05T00:00:00Z"} for t in universe}
    row = P.cumulative_by_close_day(universe, ivs, settlement)[0]
    assert row["markets_closed"] == 2      # it IS closed
    assert row["with_intervals"] == 1      # ...and still buys nothing
    assert row["game_units"] == 1


def test_l41_floor_verdict_fires_at_exactly_ten_units():
    def table_for(n):
        universe = [f"KXG-26AUG05G{i}-A" for i in range(n)]
        snaps = _snaps(**{t: 2 for t in universe})
        ivs = P.interval_counts(universe, snaps)
        settlement = {t: {"close_time": "2026-08-05T00:00:00Z"} for t in universe}
        return P.cumulative_by_close_day(universe, ivs, settlement)[0]

    assert P.L41_MIN_UNITS == 10
    assert table_for(9)["clears_l41_floor"] is False
    assert table_for(10)["clears_l41_floor"] is True


def test_empty_and_garbage_settlement_input_yield_an_empty_table_not_a_crash():
    universe = ["KXG-26AUG05AB-A"]
    ivs = {"KXG-26AUG05AB-A": 3}
    assert P.cumulative_by_close_day(universe, ivs, {}) == []
    assert P.cumulative_by_close_day(universe, ivs, {"KXG-26AUG05AB-A": {}}) == []
    assert P.cumulative_by_close_day(universe, ivs,
                                     {"KXG-26AUG05AB-A": {"close_time": "nope"}}) == []


def test_conservative_projection_drops_same_day_closes():
    universe = ["KXG-26AUG09AB-A", "KXH-26AUG10CD-C"]
    snaps = _snaps(**{"KXG-26AUG09AB-A": 3, "KXH-26AUG10CD-C": 3})
    ivs = P.interval_counts(universe, snaps)
    settlement = {
        "KXG-26AUG09AB-A": {"close_time": "2026-08-09T12:00:00Z"},
        "KXH-26AUG10CD-C": {"close_time": "2026-08-10T12:00:00Z"},
    }
    table = P.cumulative_by_close_day(universe, ivs, settlement)
    proj = P.fire_date_projections(table, ["2026-08-10"])["2026-08-10"]
    assert proj["optimistic_includes_same_day_closes"]["game_units"] == 2
    assert proj["conservative_one_day_settlement_lag"]["game_units"] == 1


def test_synthetic_cache_marks_its_own_results_synthetic_and_only_fills_closed_markets():
    universe = ["KXG-26AUG05AB-A", "KXH-26AUG20CD-C"]
    ivs = {t: 2 for t in universe}
    settlement = {
        "KXG-26AUG05AB-A": {"close_time": "2026-08-05T00:00:00Z", "result": "", "status": "active"},
        "KXH-26AUG20CD-C": {"close_time": "2026-08-20T00:00:00Z", "result": "", "status": "active"},
    }
    synth = P.synthetic_post_repull_cache(settlement, universe, ivs, "2026-08-10")
    assert synth["KXG-26AUG05AB-A"]["result"] in ("yes", "no")
    assert synth["KXG-26AUG05AB-A"]["status"] == "finalized"
    # a market that has NOT closed by the fire date is left exactly as it was
    assert synth["KXH-26AUG20CD-C"]["result"] == ""
    assert synth["KXH-26AUG20CD-C"]["status"] == "active"


def test_an_already_settled_result_is_never_overwritten_by_the_synthetic_placeholder():
    universe = ["KXG-26AUG03AB-A"]
    settlement = {"KXG-26AUG03AB-A": {"close_time": "2026-08-03T00:00:00Z",
                                      "result": "no", "status": "finalized"}}
    synth = P.synthetic_post_repull_cache(settlement, universe, {"KXG-26AUG03AB-A": 2},
                                          "2026-08-10")
    assert synth["KXG-26AUG03AB-A"]["result"] == "no"


def test_the_preflight_reports_no_pnl_or_ci_key_anywhere():
    """This is an adequacy instrument. A mean/CI/pnl key appearing in its report would mean
    a verdict-class number leaked out of a PROJECTION — including out of the synthetic-
    settlement hazard run, whose outcomes are invented."""
    rep = P.run(with_hazard=False)

    def keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield str(k).lower()
                yield from keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys(v)

    forbidden = ("mean", "ci95", "pnl", "p_and_l", "bootstrap", "edge", "profit")
    leaked = [k for k in set(keys(rep)) for tok in forbidden if tok in k]
    assert not leaked, f"pre-flight leaked a verdict-class key: {sorted(set(leaked))}"


# --------------------------------------------------------------------------- #
# HARD acceptance tests over the committed slice
# --------------------------------------------------------------------------- #
def test_acceptance_sampled_sports_universe_is_the_probes_own_sixty_markets():
    """EXACT on the settlement side (frozen snapshot), and the depth-derived universe is
    pinned by the probe's own deterministic stride reconstruction."""
    universe, _snaps = P.sports_universe()
    assert len(universe) == 60
    cache = M.load_settlement_cache(P.FROZEN_M2_CACHE)
    assert set(universe) == set(cache)


def test_acceptance_three_of_the_sixty_can_never_contribute_a_bootstrap_unit():
    """DIRECTIONAL: a stranded-branch sweep could append snapshots for dt=2026-08-03 and
    rescue one of these, so the assertion is an upper bound on the dead count, not '== 3'."""
    universe, snaps = P.sports_universe()
    ivs = P.interval_counts(universe, snaps)
    dead = [t for t in universe if ivs[t] == 0]
    assert len(dead) <= 3, f"more markets are interval-dead than the pre-flight recorded: {dead}"
    assert sum(ivs.values()) >= 165


def test_acceptance_the_2026_08_10_firing_clears_the_l41_floor_by_a_wide_margin():
    """The whole point of the pre-flight: the time-gated firing is worth firing.

    DIRECTIONAL (`>=`) on the book side — more snapshots can only add units. The
    conservative column allows a full day of settlement lag by excluding markets that close
    ON the firing day."""
    rep = P.run(with_hazard=False)
    proj = rep["fire_date_projections"]["2026-08-10"]
    opt = proj["optimistic_includes_same_day_closes"]
    con = proj["conservative_one_day_settlement_lag"]
    assert opt["game_units"] >= 44 and opt["legs"] >= 256
    assert con["game_units"] >= 41 and con["legs"] >= 238
    assert proj["clears_l41_floor_even_conservatively"] is True
    assert con["game_units"] >= 4 * P.L41_MIN_UNITS


def test_acceptance_the_queue_s_57_units_is_the_terminal_row_not_the_08_10_row():
    """LOOP-QUEUE's milestone-3 spec predicts '~57 game units / ~330 legs'. That is the
    close-day 2026-08-23 row. Firing on 08-10 buys materially less — the pre-flight exists
    to make that difference a number instead of a word.

    `cache_path=P.FROZEN_M2_CACHE` is load-bearing (L325): `P.run()` defaults to the LIVE
    settlement cache, which milestone 3's own `--build-cache` command overwrote on 2026-08-10
    with the venue's ACTUAL finalize times. Under that cache 48 of 60 markets' `close_time`
    moves EARLIER and the close-day table collapses from 11 rows to 8, so this test — which
    pins what the PRE-FIRING projection said — must name the input the projection was measured
    on. That is L284/L191's rule (pin to a slice that cannot grow) applied one artifact over."""
    rep = P.run(with_hazard=False, cache_path=P.FROZEN_M2_CACHE)
    table = rep["cumulative_by_close_day"]
    terminal = table[-1]
    assert terminal["close_day"] == "2026-08-23"
    assert terminal["game_units"] >= 57 and terminal["legs"] >= 330
    row_0810 = [r for r in table if r["close_day"] == "2026-08-10"][0]
    assert row_0810["game_units"] < terminal["game_units"]


def test_acceptance_the_cumulative_table_is_monotone_on_real_tape():
    """FROZEN input (L325) — see the note on the terminal-row test above."""
    rep = P.run(with_hazard=False, cache_path=P.FROZEN_M2_CACHE)
    table = rep["cumulative_by_close_day"]
    assert len(table) >= 11
    for a, b in zip(table[:-1], table[1:]):
        assert b["close_day"] > a["close_day"]
        assert b["markets_closed"] >= a["markets_closed"]
        assert b["game_units"] >= a["game_units"]
        assert b["legs"] >= a["legs"]


def test_acceptance_the_frozen_m2_cache_still_holds_the_unsettled_majority():
    """EXACT: the frozen snapshot is a completed pull of a past instant and nothing writes
    to it. 49 `active` markets ARE milestone 2's binding constraint."""
    cache = M.load_settlement_cache(P.FROZEN_M2_CACHE)
    assert len(cache) == 60
    assert sum(1 for v in cache.values() if v.get("status") == "active") == 49


def test_acceptance_the_milestone_3_repull_moves_every_pinned_milestone_2_number():
    """The firing hazard, demonstrated on real tape against a SYNTHETIC post-re-pull cache.

    Only POPULATION counts are read off the synthetic run — its settlement results are
    invented, so no outcome-dependent number from it may be quoted, and none is computed.
    DIRECTIONAL on the 'after' column (more depth tape raises it); EXACT on the 'before'
    column, which comes from the frozen snapshot.

    NOTE the explicit `before_cache_path=P.FROZEN_M2_CACHE`. Defaulting it to the LIVE cache
    would make THIS test a copy of the bug it documents: on 2026-08-10 the live file becomes
    the post-re-pull state, `before` would equal `after`, and the assertion would fail for a
    reason that has nothing to do with the property under test."""
    universe, snaps = P.sports_universe()
    ivs = P.interval_counts(universe, snaps)
    settlement = M.load_settlement_cache(P.FROZEN_M2_CACHE)
    h = P.hazard_report(universe, ivs, settlement, fire_date="2026-08-10", n_boot=20,
                        before_cache_path=P.FROZEN_M2_CACHE)
    assert h["before_cache_is_the_frozen_m2_snapshot"] is True
    assert h["hazard_confirmed"] is True
    assert h["price_source_tag_of_the_after_column"] == "synthetic"
    before, after = h["before_committed_cache"], h["after_synthetic_post_repull_cache"]
    assert before == {"n_units_games": 7, "n_intervals": 20, "n_covered_intervals": 17,
                      "drops_unsettled": 145, "n_fills": 26}
    assert after["n_units_games"] >= 44
    assert after["n_intervals"] >= 128
    assert after["drops_unsettled"] < before["drops_unsettled"]
    assert set(h["pinned_quantities_that_move"]) == {
        "n_units_games", "n_intervals", "n_covered_intervals", "drops_unsettled", "n_fills"}
    assert h["repair"]["frozen_snapshot_present"] is True


def test_acceptance_the_frozen_snapshot_repair_is_in_place():
    """The repair itself: the immutable snapshot exists and the live cache is untouched."""
    assert P.FROZEN_M2_CACHE.exists()
    live = json.loads(M.CACHE_PATH.read_text(encoding="utf-8"))
    frozen = json.loads(P.FROZEN_M2_CACHE.read_text(encoding="utf-8"))
    assert frozen["pulled_at"].startswith("2026-08-04T")
    assert frozen["price_source_tag"] == "broker_truth"
    assert set(frozen["markets"]) == set(live["markets"])


def test_hazard_report_before_column_defaults_to_the_live_cache_but_is_overridable():
    """The default is right for an on-demand diagnostic (after the re-pull the hazard is
    genuinely gone, so `hazard_confirmed` SHOULD go False); the override is what makes a
    test stable across that same event. Asserted on the signature, not by running it."""
    import inspect
    sig = inspect.signature(P.hazard_report)
    assert sig.parameters["before_cache_path"].default is None


# --------------------------------------------------------------------------- #
# L325 — the milestone-3 firing hazard that L284's repair did NOT cover
# --------------------------------------------------------------------------- #
def test_acceptance_live_cache_still_produces_a_well_formed_table_after_the_m3_repull():
    """SHAPE ONLY, on the LIVE cache — deliberately not pinned to values.

    L284 froze the settlement cache and repointed `tests/test_q51_maker_fillsim.py`'s three
    milestone-2 pins at the snapshot, but left the two value-pinning cases in THIS module
    reading the live cache; on 2026-08-10 the firing turned them red. The repair repoints
    those at the frozen snapshot. This case exists so the live path is still structurally
    checked rather than silently abandoned — the same division of labour L284 chose."""
    rep = P.run(with_hazard=False)
    table = rep["cumulative_by_close_day"]
    assert table, "live cache produced no close-day rows at all"
    for a, b in zip(table[:-1], table[1:]):
        assert b["close_day"] > a["close_day"]
        assert b["markets_closed"] >= a["markets_closed"]
        assert b["game_units"] >= a["game_units"]
        assert b["legs"] >= a["legs"]
    assert rep["population"]["sports_game_markets_in_sample"] == 60


def test_acceptance_the_m3_repull_moved_close_time_earlier_never_later():
    """WHY the table collapsed, measured rather than asserted.

    Kalshi's `close_time` on a FINALIZED market is the actual finalize instant, not the
    scheduled close the milestone-2 cache recorded while the game was still `active`. So the
    re-pull can only move a market EARLIER into scope, never later — which is why the 08-10
    firing scored MORE units (51) than the pre-flight's close-day projection (44), the
    opposite direction from the settlement-lag reduction the pre-flight warned about."""
    m2 = M.load_settlement_cache(P.FROZEN_M2_CACHE)
    m3_path = P.REPO_ROOT / "tape" / "q51_settlement_cache" / "settlement-m3-2026-08-10.json"
    if not m3_path.exists():          # tolerate a checkout without the m3 snapshot
        return
    m3 = M.load_settlement_cache(m3_path)
    assert set(m2) == set(m3)
    later = [t for t in m3 if (m3[t].get("close_time") or "") > (m2[t].get("close_time") or "")]
    assert later == [], f"close_time moved LATER for {later}"
    earlier = [t for t in m3 if (m3[t].get("close_time") or "") < (m2[t].get("close_time") or "")]
    assert len(earlier) >= 40
