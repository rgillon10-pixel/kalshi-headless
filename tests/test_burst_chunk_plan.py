"""scripts.burst_chunk_plan — offline unit tests. Pure arithmetic, no network/tape/clock."""
from __future__ import annotations

import math

import pytest

from scripts.burst_chunk_plan import (
    ChunkPlan,
    chunk_max_ticks_sequence,
    chunk_max_ticks_sequence_protecting,
    chunk_max_ticks_sequence_protecting_multi,
    chunk_plan,
    first_chunk_ticks_protecting_instant,
    main,
    seam_offsets_seconds,
    seam_violations,
    ticks_per_chunk,
    window_minutes,
)


# --------------------------------------------------------------------------- #
# ticks_per_chunk
# --------------------------------------------------------------------------- #
def test_ticks_per_chunk_exact_division():
    assert ticks_per_chunk(chunk_minutes=20, interval_seconds=120) == 10  # 1200s/120s


def test_ticks_per_chunk_rounds_up_never_undershoots():
    # 20min=1200s at 90s interval -> 13.33 ticks; must round UP to 14 so the chunk
    # is never SHORTER than requested (an undershoot would just be a slightly-short
    # chunk with an extra chunk at the end; rounding down would silently under-cover).
    assert ticks_per_chunk(chunk_minutes=20, interval_seconds=90) == 14
    assert 14 * 90 >= 20 * 60


def test_ticks_per_chunk_floors_at_one():
    assert ticks_per_chunk(chunk_minutes=0.01, interval_seconds=90) == 1


@pytest.mark.parametrize("chunk_minutes,interval_seconds", [(0, 90), (-5, 90), (20, 0), (20, -1)])
def test_ticks_per_chunk_rejects_nonpositive(chunk_minutes, interval_seconds):
    with pytest.raises(ValueError):
        ticks_per_chunk(chunk_minutes, interval_seconds)


# --------------------------------------------------------------------------- #
# chunk_plan / chunk_max_ticks_sequence — the core invariant: the sequence must
# cover the FULL window with no gap, no chunk of a wrong size.
# --------------------------------------------------------------------------- #
def test_chunk_plan_exact_division_no_remainder():
    # 60 minutes at 120s interval = 30 ticks total; 20min chunks = 10 ticks/chunk -> 3 chunks, no remainder.
    plan = chunk_plan(total_minutes=60, chunk_minutes=20, interval_seconds=120)
    assert plan.total_ticks == 30
    assert plan.ticks_per_chunk == 10
    assert plan.n_chunks == 3
    assert plan.last_chunk_ticks == 10
    assert chunk_max_ticks_sequence(plan) == [10, 10, 10]


def test_chunk_plan_chunk_seconds_is_first_to_last_tick_span_not_nominal_window():
    # 10 ticks @ 120s interval: first tick fires at t=0 (no wait), last at t=9*120=1080s.
    # chunk_seconds must be (n-1)*interval = 1080, NOT n*interval = 1200 (the pre-correction bug
    # this test regression-pins: an independent verifier caught the finding's chunk-duration
    # claim overstating the actual first-to-last-tick span by one interval).
    plan = chunk_plan(total_minutes=60, chunk_minutes=20, interval_seconds=120)
    assert plan.ticks_per_chunk == 10
    assert plan.chunk_seconds == pytest.approx(1080.0)
    assert plan.chunk_seconds == pytest.approx((plan.ticks_per_chunk - 1) * 120)


def test_chunk_plan_chunk_seconds_never_negative_for_single_tick_chunk():
    plan = chunk_plan(total_minutes=1, chunk_minutes=20, interval_seconds=90)
    assert plan.ticks_per_chunk >= 1
    assert plan.chunk_seconds >= 0.0


def test_chunk_plan_sequence_sums_to_total_ticks():
    # a battery of realistic (window, chunk, interval) triples, none evenly divisible.
    cases = [
        (125, 20, 90),   # FOMC: 17:40->19:45 = 125min @ 90s
        (155, 20, 120),  # WC final: 20:10->22:45 = 155min @ 120s
        (100, 15, 60),
        (37, 10, 45),
    ]
    for total_minutes, chunk_minutes, interval_seconds in cases:
        plan = chunk_plan(total_minutes, chunk_minutes, interval_seconds)
        seq = chunk_max_ticks_sequence(plan)
        assert sum(seq) == plan.total_ticks, (total_minutes, chunk_minutes, interval_seconds)
        assert len(seq) == plan.n_chunks
        # every chunk except the last is exactly ticks_per_chunk; the last is <= that.
        assert all(t == plan.ticks_per_chunk for t in seq[:-1])
        assert 0 < seq[-1] <= plan.ticks_per_chunk


def test_chunk_plan_last_chunk_never_zero_or_negative():
    # a case engineered to land exactly on a chunk boundary (no dangling remainder chunk).
    plan = chunk_plan(total_minutes=40, chunk_minutes=20, interval_seconds=60)
    assert plan.last_chunk_ticks > 0
    assert plan.n_chunks == 2


def test_chunk_plan_single_chunk_when_window_shorter_than_chunk_size():
    plan = chunk_plan(total_minutes=10, chunk_minutes=20, interval_seconds=90)
    assert plan.n_chunks == 1
    assert chunk_max_ticks_sequence(plan) == [plan.total_ticks]


@pytest.mark.parametrize("total_minutes", [0, -1])
def test_chunk_plan_rejects_nonpositive_window(total_minutes):
    with pytest.raises(ValueError):
        chunk_plan(total_minutes, chunk_minutes=20, interval_seconds=90)


# --------------------------------------------------------------------------- #
# window_minutes — ISO8601 parsing, mirrors collection.burst_capture._parse_until
# --------------------------------------------------------------------------- #
def test_window_minutes_basic():
    assert window_minutes("2026-07-29T17:40:00Z", "2026-07-29T19:45:00Z") == pytest.approx(125.0)


def test_window_minutes_accepts_offset_form():
    assert window_minutes("2026-07-14T20:10:00+00:00", "2026-07-14T22:30:00+00:00") == pytest.approx(140.0)


def test_window_minutes_rejects_non_positive_span():
    with pytest.raises(ValueError):
        window_minutes("2026-07-29T19:45:00Z", "2026-07-29T17:40:00Z")
    with pytest.raises(ValueError):
        window_minutes("2026-07-29T17:40:00Z", "2026-07-29T17:40:00Z")


# --------------------------------------------------------------------------- #
# the ACTUAL FOMC plan this module exists to produce (real values, not a fixture) —
# regression-pins the exact recipe the ops runbook quotes.
# --------------------------------------------------------------------------- #
def test_fomc_window_plan_matches_the_recommended_recipe():
    minutes = window_minutes("2026-07-29T17:40:00Z", "2026-07-29T19:45:00Z")
    assert minutes == pytest.approx(125.0)
    plan = chunk_plan(minutes, chunk_minutes=20, interval_seconds=90)
    assert plan.total_ticks == 84       # ceil(125*60/90)
    assert plan.ticks_per_chunk == 14   # ceil(20*60/90)
    assert plan.n_chunks == 6
    assert chunk_max_ticks_sequence(plan) == [14, 14, 14, 14, 14, 14]
    assert sum(chunk_max_ticks_sequence(plan)) == 84


# --------------------------------------------------------------------------- #
# CLI smoke test — exercises main() end-to-end (argparse + print), no mocking needed
# since the module does no I/O beyond stdout.
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# FOMC seam-safety — regression-pins both halves of the verifier-caught design flaw: the naive
# uniform plan DOES seam near the 18:00:00Z release instant, and the hand-verified non-uniform
# recipe in ops/burst_capture_chunked.md does NOT (18:00:00Z lands inside its first chunk with
# margin, not on a boundary). Tick k fires at start + k*interval; a chunk of N ticks spans
# indices 0..N-1, i.e. from t=0 to t=(N-1)*interval.
# --------------------------------------------------------------------------- #
def _tick_time_seconds(tick_index: int, interval_seconds: int) -> float:
    return tick_index * interval_seconds


def test_naive_uniform_fomc_plan_seams_near_the_release_instant():
    # naive: chunk_minutes=20 -> ticks_per_chunk=14 (this module's own default recipe).
    plan = chunk_plan(total_minutes=125, chunk_minutes=20, interval_seconds=90)
    assert chunk_max_ticks_sequence(plan)[0] == 14
    first_chunk_last_tick_s = _tick_time_seconds(14 - 1, 90)  # last tick INSIDE chunk 1
    second_chunk_first_tick_s = _tick_time_seconds(14, 90)     # first tick of chunk 2 (post-seam)
    release_s = 20 * 60  # 18:00:00Z is 20 minutes into a 17:40:00Z start
    # the seam (seconds between these two ticks) brackets the release instant +/- one interval:
    assert first_chunk_last_tick_s <= release_s <= second_chunk_first_tick_s + 90


def test_hand_verified_seam_safe_fomc_recipe_keeps_release_inside_first_chunk():
    # the recipe actually recommended in ops/burst_capture_chunked.md: [16, 14, 14, 14, 14, 12].
    seam_safe_sequence = [16, 14, 14, 14, 14, 12]
    assert sum(seam_safe_sequence) == 84  # still covers the full FOMC window, per test above
    first_chunk_ticks = seam_safe_sequence[0]
    first_chunk_last_tick_s = _tick_time_seconds(first_chunk_ticks - 1, 90)
    release_s = 20 * 60
    # release instant must fall STRICTLY inside chunk 1 (not within one interval of its edge).
    assert 90 < release_s < first_chunk_last_tick_s - 90


# --------------------------------------------------------------------------- #
# L164 enforcement: first_chunk_ticks_protecting_instant / chunk_max_ticks_sequence_protecting
# replace the hand-verification above with a computed, tested equivalent.
# --------------------------------------------------------------------------- #
def test_first_chunk_ticks_protecting_instant_reproduces_the_hand_verified_fomc_first_chunk():
    # FOMC: interval=90s, ticks_per_chunk=14 (chunk_minutes=20), release at +20min=1200s.
    # Hand-verified recipe used 16 ticks for chunk 1 -- this must match exactly.
    n = first_chunk_ticks_protecting_instant(
        protect_offset_seconds=1200.0, ticks_per_chunk_=14, interval_seconds=90, total_ticks=84
    )
    assert n == 16


def test_first_chunk_ticks_protecting_instant_never_shrinks_below_ticks_per_chunk():
    # protect instant early enough that no growth is needed -- must not shrink chunk 1.
    n = first_chunk_ticks_protecting_instant(
        protect_offset_seconds=200.0, ticks_per_chunk_=14, interval_seconds=90, total_ticks=84
    )
    assert n == 14


def test_first_chunk_ticks_protecting_instant_caps_at_total_ticks():
    # protect instant very late in a short window -- chunk 1 may absorb the whole window,
    # never grow past it.
    n = first_chunk_ticks_protecting_instant(
        protect_offset_seconds=5000.0, ticks_per_chunk_=14, interval_seconds=90, total_ticks=20
    )
    assert n == 20


@pytest.mark.parametrize("margin_seconds", [0.0, 45.0, 90.0, 180.0])
def test_first_chunk_ticks_protecting_instant_honors_custom_margin(margin_seconds):
    n = first_chunk_ticks_protecting_instant(
        protect_offset_seconds=1200.0, ticks_per_chunk_=14, interval_seconds=90,
        total_ticks=84, margin_seconds=margin_seconds,
    )
    last_tick_s = (n - 1) * 90
    assert last_tick_s > 1200.0 + margin_seconds


def test_first_chunk_ticks_protecting_instant_rejects_instant_too_close_to_window_start():
    with pytest.raises(ValueError):
        first_chunk_ticks_protecting_instant(
            protect_offset_seconds=30.0, ticks_per_chunk_=14, interval_seconds=90, total_ticks=84
        )
    # exactly at the margin boundary is also rejected (strict >, not >=)
    with pytest.raises(ValueError):
        first_chunk_ticks_protecting_instant(
            protect_offset_seconds=90.0, ticks_per_chunk_=14, interval_seconds=90, total_ticks=84
        )


def test_chunk_max_ticks_sequence_protecting_reproduces_the_hand_verified_fomc_recipe():
    # the exact recipe ops/burst_capture_chunked.md recommends, now computed rather than
    # hand-derived: [16, 14, 14, 14, 14, 12].
    seq = chunk_max_ticks_sequence_protecting(
        total_minutes=125, chunk_minutes=20, interval_seconds=90, protect_offset_minutes=20.0
    )
    assert seq == [16, 14, 14, 14, 14, 12]
    assert sum(seq) == 84


def test_chunk_max_ticks_sequence_protecting_sums_to_total_ticks_across_cases():
    cases = [
        (125, 20, 90, 20.0),   # FOMC
        (155, 20, 120, 25.0),  # WC-final-shaped: release near start
        (100, 15, 60, 40.0),   # release inside a LATER naive chunk
        (37, 10, 45, 5.0),
    ]
    for total_minutes, chunk_minutes, interval_seconds, protect_offset_minutes in cases:
        seq = chunk_max_ticks_sequence_protecting(
            total_minutes, chunk_minutes, interval_seconds, protect_offset_minutes
        )
        total_ticks = max(1, math.ceil((total_minutes * 60.0) / interval_seconds))
        assert sum(seq) == total_ticks, (total_minutes, chunk_minutes, interval_seconds)
        # every chunk after the first is exactly ticks_per_chunk except a shorter last one.
        tpc = ticks_per_chunk(chunk_minutes, interval_seconds)
        assert all(t == tpc for t in seq[1:-1])
        assert 0 < seq[-1] <= tpc


def test_chunk_max_ticks_sequence_protecting_release_lands_strictly_inside_chunk_one():
    seq = chunk_max_ticks_sequence_protecting(
        total_minutes=125, chunk_minutes=20, interval_seconds=90, protect_offset_minutes=20.0
    )
    first_chunk_last_tick_s = (seq[0] - 1) * 90
    release_s = 20 * 60
    assert 90 < release_s < first_chunk_last_tick_s - 90  # same margin the hand-verified test checks


def test_chunk_max_ticks_sequence_protecting_rejects_instant_at_or_past_window_end():
    with pytest.raises(ValueError):
        chunk_max_ticks_sequence_protecting(
            total_minutes=60, chunk_minutes=20, interval_seconds=90, protect_offset_minutes=60.0
        )
    with pytest.raises(ValueError):
        chunk_max_ticks_sequence_protecting(
            total_minutes=60, chunk_minutes=20, interval_seconds=90, protect_offset_minutes=75.0
        )


def test_protect_cli_flag_reproduces_the_hand_verified_fomc_recipe(capsys):
    rc = main([
        "--start", "2026-07-29T17:40:00Z",
        "--until", "2026-07-29T19:45:00Z",
        "--interval", "90",
        "--chunk-minutes", "20",
        "--protect", "2026-07-29T18:00:00Z",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[16, 14, 14, 14, 14, 12]" in out
    assert "total_ticks=84" in out


def test_protect_cli_flag_omitted_keeps_prior_uniform_behavior_unchanged(capsys):
    rc = main([
        "--start", "2026-07-29T17:40:00Z",
        "--until", "2026-07-29T19:45:00Z",
        "--interval", "90",
        "--chunk-minutes", "20",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[14, 14, 14, 14, 14, 14]" in out


def test_main_smoke(capsys):
    rc = main([
        "--start", "2026-07-29T17:40:00Z",
        "--until", "2026-07-29T19:45:00Z",
        "--interval", "90",
        "--chunk-minutes", "20",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "total_ticks=84" in out
    assert "n_chunks=6" in out
    assert "[14, 14, 14, 14, 14, 14]" in out


# --------------------------------------------------------------------------- #
# L164's remaining half (2026-08-14): seam_offsets_seconds / seam_violations —
# the MECHANICAL form of the check ops/burst_capture_chunked.md used to mandate
# be done by hand for every future one-shot.
# --------------------------------------------------------------------------- #
def test_seam_offsets_are_the_adjacent_tick_pair_not_a_single_boundary():
    # [3, 3] @ 60s: chunk 1 covers ticks 0,1,2 (t=0,60,120); chunk 2 covers ticks 3,4,5.
    # The at-risk gap is the PAUSE between tick 2 (120s) and tick 3 (180s).
    assert seam_offsets_seconds([3, 3], interval_seconds=60) == [(120.0, 180.0)]


def test_seam_offsets_one_per_internal_boundary_window_end_is_not_a_seam():
    seams = seam_offsets_seconds([16, 14, 14, 14, 14, 12], interval_seconds=90)
    assert len(seams) == 5  # 6 chunks -> 5 internal seams; the window end is not one
    assert seams[0] == (1350.0, 1440.0)  # (16-1)*90, 16*90
    assert all(end - start == 90.0 for start, end in seams)  # each seam is exactly one interval wide


def test_seam_offsets_single_chunk_has_no_seam():
    assert seam_offsets_seconds([84], interval_seconds=90) == []


@pytest.mark.parametrize("seq,interval", [([14, 0], 90), ([-1, 14], 90), ([14, 14], 0)])
def test_seam_offsets_rejects_degenerate_input(seq, interval):
    with pytest.raises(ValueError):
        seam_offsets_seconds(seq, interval)


def test_seam_violations_empty_when_instant_clears_every_seam():
    assert seam_violations([16, 14, 14, 14, 14, 12], 90, [20 * 60.0]) == []


def test_seam_violations_catches_an_instant_INSIDE_a_seam_with_gap_zero():
    # the naive uniform FOMC plan: seam 1 spans 1170s-1260s (17:59:30Z-18:01:00Z from a
    # 17:40:00Z start) and the 18:00:00Z statement sits at 1200s, INSIDE it. This is the
    # exact hand observation that produced L164, now reproduced mechanically.
    violations = seam_violations([14, 14, 14, 14, 14, 14], 90, [20 * 60.0])
    assert len(violations) == 1
    v = violations[0]
    assert (v.chunk_index, v.seam_start_seconds, v.seam_end_seconds) == (1, 1170.0, 1260.0)
    assert v.gap_seconds == 0.0
    assert v.margin_seconds == 90.0


def test_seam_violations_is_TWO_SIDED_an_instant_just_after_a_seam_is_caught():
    # The single-instant grower only ever pushes a seam LATER, so it implicitly assumes the
    # instant precedes the seam. An instant landing just AFTER a seam is equally unprotected.
    seams = seam_offsets_seconds([10, 10], interval_seconds=60)
    seam_end = seams[0][1]  # 600.0
    just_after = seam_end + 30.0
    assert seam_violations([10, 10], 60, [just_after]) != []
    clear_after = seam_end + 61.0
    assert seam_violations([10, 10], 60, [clear_after]) == []


def test_seam_violations_margin_override_is_honoured_in_both_directions():
    seq, interval = [10, 10], 60
    instant = seam_offsets_seconds(seq, interval)[0][1] + 90.0  # 690s, 90s clear of the seam end
    assert seam_violations(seq, interval, [instant], margin_seconds=60.0) == []
    assert seam_violations(seq, interval, [instant], margin_seconds=120.0) != []


def test_seam_violations_reports_every_offending_pair_not_just_the_first():
    # two instants, each parked on a different seam of the same plan
    seams = seam_offsets_seconds([10, 10, 10], interval_seconds=60)
    instants = [seams[0][0], seams[1][0]]
    violations = seam_violations([10, 10, 10], 60, instants)
    assert len(violations) == 2
    assert sorted(v.chunk_index for v in violations) == [1, 2]


def test_seam_violations_rejects_negative_margin():
    with pytest.raises(ValueError):
        seam_violations([10, 10], 60, [300.0], margin_seconds=-1.0)


# --------------------------------------------------------------------------- #
# The committed FOMC recipe, checked against the SECOND decisive instant L164's
# own text names (the presser ~30min after the statement) — the case the
# 2026-07-26 build explicitly left to a hand check.
# --------------------------------------------------------------------------- #
def test_committed_fomc_recipe_is_seam_safe_for_BOTH_statement_and_presser():
    # window 17:40:00Z -> 19:45:00Z @ 90s; statement 18:00:00Z (t+1200s),
    # presser 18:30:00Z (t+3000s, the standard statement+30min Fed schedule).
    seq = [16, 14, 14, 14, 14, 12]
    assert seam_violations(seq, 90, [1200.0, 3000.0]) == []


def test_committed_fomc_recipe_puts_the_presser_strictly_inside_chunk_three():
    seams = seam_offsets_seconds([16, 14, 14, 14, 14, 12], interval_seconds=90)
    presser = 3000.0
    assert seams[1][1] < presser < seams[2][0]  # after seam 2 ends, before seam 3 starts
    assert min(presser - seams[1][1], seams[2][0] - presser) > 90.0


def test_multi_reproduces_the_hand_verified_fomc_recipe_for_both_instants():
    seq = chunk_max_ticks_sequence_protecting_multi(
        total_minutes=125, chunk_minutes=20, interval_seconds=90,
        protect_offsets_minutes=[20.0, 50.0],
    )
    assert seq == [16, 14, 14, 14, 14, 12]
    assert sum(seq) == 84


def test_multi_agrees_with_the_single_instant_function_when_the_instant_is_in_chunk_one():
    single = chunk_max_ticks_sequence_protecting(
        total_minutes=125, chunk_minutes=20, interval_seconds=90, protect_offset_minutes=20.0
    )
    multi = chunk_max_ticks_sequence_protecting_multi(
        total_minutes=125, chunk_minutes=20, interval_seconds=90, protect_offsets_minutes=[20.0]
    )
    assert single == multi == [16, 14, 14, 14, 14, 12]


def test_multi_does_not_inflate_chunk_one_for_a_LATER_instant_unlike_the_single_form():
    # measured defect the generalization exposed: the single-instant form grows CHUNK 1 no
    # matter where the instant sits, inflating the worst-case loss the chunking exists to bound.
    kwargs = dict(total_minutes=100, chunk_minutes=15, interval_seconds=60)
    single = chunk_max_ticks_sequence_protecting(protect_offset_minutes=40.0, **kwargs)
    multi = chunk_max_ticks_sequence_protecting_multi(protect_offsets_minutes=[40.0], **kwargs)
    assert single == [43, 15, 15, 15, 12] and max(single) == 43
    assert multi == [15, 15, 15, 15, 15, 15, 10] and max(multi) == 15
    assert sum(single) == sum(multi) == 100
    # both are seam-safe; the multi form is safe at 1/3 the worst-case loss
    assert seam_violations(single, 60, [2400.0]) == []
    assert seam_violations(multi, 60, [2400.0]) == []


def test_multi_output_is_always_seam_safe_and_covers_the_window_across_a_grid():
    cases = [
        (125, 20, 90, [20.0]),
        (125, 20, 90, [20.0, 50.0]),
        (155, 20, 120, [25.0, 60.0, 100.0]),
        (100, 15, 60, [40.0]),
        (100, 15, 60, [14.9, 30.1, 45.0]),
        (37, 10, 45, [5.0, 20.0]),
        (60, 5, 30, [10.0, 11.0, 12.0]),
    ]
    for total_minutes, chunk_minutes, interval_seconds, protects in cases:
        seq = chunk_max_ticks_sequence_protecting_multi(
            total_minutes, chunk_minutes, interval_seconds, protects
        )
        total_ticks = max(1, math.ceil((total_minutes * 60.0) / interval_seconds))
        assert sum(seq) == total_ticks, (total_minutes, protects)
        assert all(t > 0 for t in seq)
        assert seam_violations(seq, interval_seconds, [p * 60.0 for p in protects]) == [], (
            total_minutes, protects
        )


def test_multi_grows_only_the_violated_chunk_others_keep_the_requested_size():
    # instant at 40min lands in naive chunk 3 (@15min chunks); chunks 1-2 must stay at tpc.
    seq = chunk_max_ticks_sequence_protecting_multi(
        total_minutes=100, chunk_minutes=15, interval_seconds=60, protect_offsets_minutes=[46.0]
    )
    tpc = ticks_per_chunk(15, 60)
    assert seq[0] == tpc and seq[1] == tpc
    assert seam_violations(seq, 60, [46 * 60.0]) == []


def test_multi_densely_packed_instants_collapse_toward_one_chunk_honestly():
    # every candidate seam blocked -> the only seam-safe plan is one chunk. Correct, and the
    # caller should SEE the resulting loss exposure rather than have it approximated away.
    protects = [float(m) for m in range(2, 30)]
    seq = chunk_max_ticks_sequence_protecting_multi(
        total_minutes=30, chunk_minutes=5, interval_seconds=60, protect_offsets_minutes=protects
    )
    assert seq == [30]
    assert seam_offsets_seconds(seq, 60) == []


def test_multi_dedupes_and_sorts_its_protected_instants():
    a = chunk_max_ticks_sequence_protecting_multi(125, 20, 90, [50.0, 20.0, 20.0])
    b = chunk_max_ticks_sequence_protecting_multi(125, 20, 90, [20.0, 50.0])
    assert a == b


@pytest.mark.parametrize("protects", [[60.0], [20.0, 75.0], [0.5], [20.0, 1.0]])
def test_multi_rejects_instants_outside_the_protectable_window(protects):
    with pytest.raises(ValueError):
        chunk_max_ticks_sequence_protecting_multi(
            total_minutes=60, chunk_minutes=20, interval_seconds=90, protect_offsets_minutes=protects
        )


# --------------------------------------------------------------------------- #
# CLI: repeatable --protect, --verify-sequence, and the generator's self-check
# --------------------------------------------------------------------------- #
def test_cli_single_protect_output_is_unchanged_and_now_carries_a_seam_check(capsys):
    rc = main([
        "--start", "2026-07-29T17:40:00Z", "--until", "2026-07-29T19:45:00Z",
        "--interval", "90", "--chunk-minutes", "20", "--protect", "2026-07-29T18:00:00Z",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "max_ticks_sequence=[16, 14, 14, 14, 14, 12]  (chunk 1 grown" in out
    assert "seam_check=PASS" in out


def test_cli_protect_is_repeatable_for_statement_plus_presser(capsys):
    rc = main([
        "--start", "2026-07-29T17:40:00Z", "--until", "2026-07-29T19:45:00Z",
        "--interval", "90", "--chunk-minutes", "20",
        "--protect", "2026-07-29T18:00:00Z", "--protect", "2026-07-29T18:30:00Z",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "[16, 14, 14, 14, 14, 12]" in out
    assert "protect_offsets=[20.00min, 50.00min]" in out
    assert "seam_check=PASS (margin=90s, 0 violations)" in out


def test_cli_verify_sequence_passes_the_committed_fomc_recipe(capsys):
    rc = main([
        "--start", "2026-07-29T17:40:00Z", "--until", "2026-07-29T19:45:00Z", "--interval", "90",
        "--verify-sequence", "16,14,14,14,14,12",
        "--protect", "2026-07-29T18:00:00Z", "--protect", "2026-07-29T18:30:00Z",
    ])
    assert rc == 0
    assert "seam_check=PASS" in capsys.readouterr().out


def test_cli_verify_sequence_fails_the_naive_uniform_plan_with_exit_2(capsys):
    rc = main([
        "--start", "2026-07-29T17:40:00Z", "--until", "2026-07-29T19:45:00Z", "--interval", "90",
        "--verify-sequence", "[14, 14, 14, 14, 14, 14]", "--protect", "2026-07-29T18:00:00Z",
    ])
    out = capsys.readouterr().out
    assert rc == 2  # non-zero: a runbook/CI caller can gate on this
    assert "seam_check=FAIL (margin=90s, 1 violations)" in out
    assert "seam after chunk 1 [1170s, 1260s]" in out


def test_cli_verify_sequence_without_protect_is_an_error():
    with pytest.raises(SystemExit):
        main([
            "--start", "2026-07-29T17:40:00Z", "--until", "2026-07-29T19:45:00Z",
            "--interval", "90", "--verify-sequence", "14,14",
        ])


def test_cli_no_protect_path_prints_no_seam_check_and_stays_byte_compatible(capsys):
    rc = main([
        "--start", "2026-07-29T17:40:00Z", "--until", "2026-07-29T19:45:00Z",
        "--interval", "90", "--chunk-minutes", "20",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "[14, 14, 14, 14, 14, 14]" in out
    assert "seam_check" not in out  # unprotected callers see exactly what they saw before
