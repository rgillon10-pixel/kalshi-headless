"""Offline unit tests for q48_s55_fomc_lag_probe (Q48 / S55 prep infrastructure).

Q48 is BURST-GATED on `kalshi-burst-fomc-0729` committing tape across the 2026-07-29T18:00Z
FOMC statement. The probe is built + offline-tested now (idle-run policy (b), mirroring
q43/q37/q36/q32) so it fires the day the gate opens. NO NETWORK anywhere: every fixture is
synthetic, written into `tmp_path` as `dt=*.jsonl` day-files in the real
`polymarket_macro_pairs.v1` shape.

Mandated coverage:
  (a) zero-burst tape                       -> INSUFFICIENT DATA, no CI emitted
  (b) covering burst + persistent dislocation -> positive gap-net-of-fee, kill_condition_met
      False, and STILL descriptive-only at n_bursts=1
  (c) covering burst, Kalshi reprices next capture -> kill_condition_met True
  (d) n_bursts >= MIN_BURSTS_FOR_CI          -> bootstrap runs, resampling unit is the BURST
  (e) fee comes from core.pricing at the TAKER rate (fixture value + no literal rate in source)
  (f) bracket_sum / normalized-ask path (Hard Rule #3)
  (g) malformed / missing-leg records are skipped honestly and COUNTED
Plus the post-first-cut hardening: the one-tick `MIN_ENTRY_EDGE` gate (a sub-tick candidate is
COUNTED, never fired), the stale window BASELINED against each unit's own pre-release gap (a
standing overround is not a release-caused lag) with an UNMEASURABLE baseline reported as None,
the magnitude-qualified companion to the magnitude-blind first-move statistic, advisory burst
CADENCE qualification, and the two empty-population guards (zero units -> kill_condition_met
None, not a vacuous True; zero priced observations -> INSUFFICIENT DATA, never ANALYSIS).

L180 closure (2026-07-27) adds the two numerical-adequacy properties of the BASELINE itself:
a THIN pre-release baseline (1 <= n_pre < MIN_PRE_CAPTURES_FOR_BASELINE) is unmeasurable-class
(None) and can never create a persistent-stale-window count, and the excess-over-baseline tick
test is TIGHTENED from `>= 1 tick` to `> 1 tick` (an exactly-one-tick excess is scored to the
kill side). NOTE, because the first version of this file said otherwise: the unit that
tightening drops (`2026-10|cut_25`, 2026-07-14 CPI dry-run) was NOT float dust — its excess is
exactly one tick in exact arithmetic with 5.0 ulps of float margin, and under the documented
`>= 1 tick` rule the answer was and remains 4.

Verifier round 3 (2026-07-27) adds the third property, which the FLOOR itself created: an
n-adequacy floor relocates vacuity rather than removing it, so `no_persistent_stale_window` /
`kill_condition_met` are None whenever ZERO units carry a measurable baseline — a hard kill may
never be fired from a population in which nothing was measurable.
"""
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.pricing import TAKER_FEE_RATE, fee_per_contract, normalized_ask
from scripts.q48_s55_fomc_lag_probe import (
    BURST_CADENCE_MIN_DURATION_S,
    BURST_CADENCE_MIN_PASSES,
    BURST_MAX_INTERVAL_S,
    DEPTH_UNMEASURABLE,
    MIN_BURSTS_FOR_CI,
    MIN_ENTRY_EDGE,
    MIN_PASSES_PER_BURST_WINDOW,
    MIN_PRE_CAPTURES_FOR_BASELINE,
    STALE_WINDOW_EXCESS_EPSILON,
    STALE_WINDOW_MIN_EXCESS_DOLLARS,
    analyze_unit,
    build_observations,
    covering_release,
    covers_release,
    detect_burst_windows,
    entry_edge,
    entry_edge_candidate,
    front_meeting_key,
    gap_net_fee,
    kill_condition,
    human_one_liner,
    ladder_sums,
    load_family_records,
    max_pass_density_per_hour,
    parse_releases,
    pass_times,
    provenance_string,
    run_probe,
)

UTC = timezone.utc
BUCKETS = ("cut_50plus", "cut_25", "no_change", "hike_25", "hike_50plus")
MEETING = "2026-07"
RELEASE = "2026-07-29T18:00:00Z"
RELEASE_DT = datetime(2026, 7, 29, 18, 0, 0, tzinfo=UTC)

_TICKER = {"cut_50plus": "C26", "cut_25": "C25", "no_change": "H0",
           "hike_25": "H25", "hike_50plus": "H26"}


# --------------------------------------------------------------------------- #
# fixture builders
# --------------------------------------------------------------------------- #
def _record(when, bucket, k_yes, k_no, pm_ask, pm_bid, *, meeting=MEETING,
            family="fed_decision", book_ok=True, tag="real_ask"):
    cid = when.strftime("%Y%m%dT%H%M%SZ")
    return {
        "schema_version": "polymarket_macro_pairs.v1",
        "capture_id": cid,
        "captured_at": when.isoformat(),
        "family": family,
        "meeting": meeting,
        "bucket": bucket,
        "kalshi": {
            "ticker": f"KXFEDDECISION-26JUL-{_TICKER.get(bucket, 'X')}",
            "yes_ask": k_yes, "yes_bid": max(0.0, k_yes - 0.01),
            "no_ask": k_no, "no_bid": max(0.0, k_no - 0.01),
            "price_source_tag": tag,
        },
        "polymarket": {
            "event_id": "287395", "market_id": "1654957",
            "best_bid": pm_bid, "best_ask": pm_ask,
            "book_fetch_ok": book_ok, "price_source_tag": tag,
        },
        "price_gap_yes_ask": (k_yes - pm_ask) if (k_yes is not None and pm_ask is not None)
        else None,
    }


def _pass(when, kalshi_yes_by_bucket, poly_ask_by_bucket, **kw):
    """One full 5-bucket pass. NO price is derived from the YES price by the probe; the NO ask
    is supplied explicitly so the fixture is a genuine two-sided book."""
    out = []
    for b in BUCKETS:
        ky = kalshi_yes_by_bucket[b]
        pa = poly_ask_by_bucket[b]
        out.append(_record(when, b, ky, round(1.0 - ky + 0.02, 4), pa,
                           round(max(0.0, pa - 0.005), 4), **kw))
    return out


def _write(tape_dir: Path, records):
    tape_dir.mkdir(parents=True, exist_ok=True)
    by_day = {}
    for r in records:
        by_day.setdefault(r["captured_at"][:10], []).append(r)
    for day, rows in by_day.items():
        with (tape_dir / f"dt={day}.jsonl").open("a") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")


FLAT_K = {"cut_50plus": 0.05, "cut_25": 0.30, "no_change": 0.55,
          "hike_25": 0.08, "hike_50plus": 0.04}
FLAT_P = {"cut_50plus": 0.04, "cut_25": 0.29, "no_change": 0.54,
          "hike_25": 0.07, "hike_50plus": 0.03}


def _sparse_tape(tape_dir: Path, n_passes=6):
    """Recurring-cadence (12h apart) passes only — no burst window anywhere."""
    recs = []
    t = datetime(2026, 7, 20, 6, 0, tzinfo=UTC)
    for i in range(n_passes):
        recs.extend(_pass(t + timedelta(hours=12 * i), FLAT_K, FLAT_P))
    _write(tape_dir, recs)


def _burst_tape(tape_dir: Path, *, release=RELEASE_DT, post_kalshi_by_step=None,
                post_poly=None, n_pre=MIN_PRE_CAPTURES_FOR_BASELINE, cadence_s=90,
                day_offset_days=0):
    """A covering burst window: `n_pre` passes at 90s cadence before the release and
    len(post_kalshi_by_step) passes after it.

    `n_pre` defaults to `MIN_PRE_CAPTURES_FOR_BASELINE` so the DEFAULT fixture has an ADEQUATE
    stale-window baseline (L180) and its `has_persistent_stale_window` is a real True/False.
    Tests that want the thin-baseline path pass `n_pre` below the floor explicitly — never by
    accident, which is exactly how the defect shipped."""
    recs = []
    for i in range(n_pre, 0, -1):
        recs.extend(_pass(release - timedelta(seconds=cadence_s * i) +
                          timedelta(days=day_offset_days), FLAT_K, FLAT_P))
    for step, k_map in enumerate(post_kalshi_by_step, start=1):
        p_map = post_poly[step - 1] if post_poly else FLAT_P
        recs.extend(_pass(release + timedelta(seconds=cadence_s * step) +
                          timedelta(days=day_offset_days), k_map, p_map))
    _write(tape_dir, recs)


# --------------------------------------------------------------------------- #
# burst-window detection primitives
# --------------------------------------------------------------------------- #
def test_detect_burst_windows_splits_on_interval():
    base = datetime(2026, 7, 29, 17, 50, tzinfo=UTC)
    times = {
        "a": base,
        "b": base + timedelta(seconds=90),
        "c": base + timedelta(seconds=180),
        "far": base + timedelta(hours=6),                     # isolated -> not a window
        "d": base + timedelta(hours=12),
        "e": base + timedelta(hours=12, seconds=120),
    }
    windows = detect_burst_windows(times)
    assert [w["n_passes"] for w in windows] == [3, 2]
    assert windows[0]["capture_ids"] == ["a", "b", "c"]
    assert windows[0]["median_gap_s"] == 90.0
    # a single isolated pass is never a burst window
    assert all(w["n_passes"] >= MIN_PASSES_PER_BURST_WINDOW for w in windows)


def test_covers_release_requires_strictly_both_sides():
    times = {"a": RELEASE_DT - timedelta(seconds=90), "b": RELEASE_DT - timedelta(seconds=30)}
    w = detect_burst_windows(times)[0]
    assert covers_release(w, times, RELEASE_DT) is False
    times2 = dict(times, c=RELEASE_DT + timedelta(seconds=60))
    w2 = detect_burst_windows(times2)[0]
    assert covers_release(w2, times2, RELEASE_DT) is True
    # a pass exactly AT the release is not "strictly after"
    times3 = {"a": RELEASE_DT - timedelta(seconds=60), "b": RELEASE_DT}
    w3 = detect_burst_windows(times3)[0]
    assert covers_release(w3, times3, RELEASE_DT) is False


def test_max_pass_density_per_hour():
    base = datetime(2026, 7, 29, 17, 0, tzinfo=UTC)
    times = {str(i): base + timedelta(seconds=90 * i) for i in range(10)}
    times["late"] = base + timedelta(hours=9)
    assert max_pass_density_per_hour(times) == 10
    assert max_pass_density_per_hour({"only": base}) == 1
    assert max_pass_density_per_hour({}) == 0


def test_front_meeting_key_derived_from_release_not_hardcoded():
    assert front_meeting_key(RELEASE_DT) == "2026-07"
    assert front_meeting_key(datetime(2026, 9, 17, 18, 0, tzinfo=UTC)) == "2026-09"


def test_parse_releases_accepts_one_or_many_sorted():
    assert parse_releases(RELEASE) == [RELEASE_DT]
    got = parse_releases("2026-10-28T18:00:00Z, 2026-07-29T18:00:00Z")
    assert got == sorted(got) and len(got) == 2 and got[0] == RELEASE_DT


def test_covering_release_attributes_a_window_to_exactly_one_instant():
    r1 = RELEASE_DT
    r2 = RELEASE_DT + timedelta(seconds=180)
    times = {"a": r1 - timedelta(seconds=90), "b": r1 + timedelta(seconds=90),
             "c": r2 + timedelta(seconds=90)}
    w = detect_burst_windows(times)[0]
    assert w["n_passes"] == 3
    # the window straddles BOTH instants; it is attributed to the earlier one only, so a single
    # burst can never be counted twice in the bootstrap unit set (L6)
    assert covers_release(w, times, r1) and covers_release(w, times, r2)
    assert covering_release(w, times, [r1, r2]) == r1


# --------------------------------------------------------------------------- #
# (a) zero-burst tape -> INSUFFICIENT DATA, no CI emitted
# --------------------------------------------------------------------------- #
def test_zero_burst_tape_is_insufficient_data(tmp_path):
    _sparse_tape(tmp_path / "tape")
    rep = run_probe(tmp_path / "tape", release_ts=RELEASE)
    assert rep["status"] == "INSUFFICIENT DATA"
    assert rep["n_burst_windows"] == 0
    assert rep["n_covering_burst_windows"] == 0
    assert rep["n_fed_records"] == 30
    assert rep["n_passes"] == 6
    assert rep["max_pass_density_per_hour"] == 1
    assert rep["verdict"] is None
    # No edge/CI claim of any kind may appear.
    for banned in ("bootstrap", "bursts", "kill_condition", "clears_tick_magnitude",
                   "bootstrap_verdict_admissible", "n_bursts", "n_fired_trades"):
        assert banned not in rep
    # The baseline IS still reported (it needs no burst).
    assert rep["baseline"]["all_meetings"]["raw_gap"]["n"] == 30
    assert rep["rerun_command"].startswith("python3 scripts/q48_s55_fomc_lag_probe.py --baseline")


def test_empty_tape_dir_is_insufficient_data_not_a_crash(tmp_path):
    rep = run_probe(tmp_path / "nothing-here", release_ts=RELEASE)
    assert rep["status"] == "INSUFFICIENT DATA"
    assert rep["n_fed_records"] == 0 and rep["n_passes"] == 0
    assert "bootstrap" not in rep


def test_dt_directory_is_counted_by_file_shape_not_path_existence(tmp_path):
    """L25: a `dt=<date>` entry that is a DIRECTORY is counted and skipped, never read as a day."""
    tape = tmp_path / "tape"
    _sparse_tape(tape)          # 6 passes at 12h spacing -> 3 calendar day-files
    (tape / "dt=2026-07-25").mkdir()
    rep = run_probe(tape, release_ts=RELEASE)
    assert rep["load_skips"]["n_nonfile_dt_entries"] == 1
    assert rep["load_skips"]["n_day_files"] == 3


# --------------------------------------------------------------------------- #
# (b) covering burst WITH a persistent post-release dislocation
# --------------------------------------------------------------------------- #
def _stale_kalshi_tape(tmp_path):
    """Kalshi's book is FROZEN at its pre-release prices for 6 post-release captures while
    Polymarket jumps hard toward `cut_25` — the textbook S55 stale-quote shape."""
    shocked_poly = {"cut_50plus": 0.02, "cut_25": 0.80, "no_change": 0.12,
                    "hike_25": 0.03, "hike_50plus": 0.02}
    tape = tmp_path / "tape"
    _burst_tape(tape,
                post_kalshi_by_step=[FLAT_K] * 6,
                post_poly=[shocked_poly] * 6)
    return tape


def test_persistent_dislocation_is_descriptive_only_at_one_burst(tmp_path):
    rep = run_probe(_stale_kalshi_tape(tmp_path), release_ts=RELEASE)
    assert rep["status"] == "ANALYSIS"
    assert rep["n_bursts"] == 1
    assert rep["n_covering_burst_windows"] == 1
    # descriptive-only, NO bootstrap CI
    assert rep["verdict"] == f"DESCRIPTIVE ONLY (n_bursts=1 < MIN_BURSTS_FOR_CI={MIN_BURSTS_FOR_CI})"
    assert rep["bootstrap"] is None
    assert "clears_tick_magnitude" not in rep
    assert "bootstrap_verdict_admissible" not in rep

    unit = rep["bursts"][0]["units"][f"{MEETING}|cut_25"]
    assert unit["n_post_captures"] == 6
    assert unit["max_abs_gap_net_fee"] > 0                     # a genuine >fee dislocation
    assert unit["captures_until_first_kalshi_move"] is None    # Kalshi never moved
    assert unit["stale_window_seconds"] >= 60.0
    assert unit["has_persistent_stale_window"] is True
    assert unit["n_fired_trades"] > 0
    assert set(unit["fired_directions"]) == {"BUY_YES"}        # Kalshi too cheap vs the signal

    kc = rep["kill_condition"]
    assert kc["kill_condition_met"] is False
    assert kc["n_units_with_persistent_stale_window"] >= 1
    assert kc["no_persistent_stale_window"] is False


def test_post_release_trajectory_is_time_stamped_relative_to_the_release(tmp_path):
    rep = run_probe(_stale_kalshi_tape(tmp_path), release_ts=RELEASE)
    traj = rep["bursts"][0]["units"][f"{MEETING}|cut_25"]["trajectory"]
    assert [p["seconds_after_release"] for p in traj] == [90.0 * i for i in range(1, 7)]
    assert all(p["seconds_after_release"] > 0 for p in traj)
    for p in traj:
        assert p["gap_net_fee"] == abs(p["raw_gap"]) - fee_per_contract(p["kalshi_yes_price"])


def test_depth_unmeasurable_travels_with_every_report(tmp_path):
    rep = run_probe(_stale_kalshi_tape(tmp_path), release_ts=RELEASE)
    assert rep["depth_unmeasurable"] is True and DEPTH_UNMEASURABLE is True
    assert "size-blind" in rep["depth_note"]


# --------------------------------------------------------------------------- #
# (c) covering burst where Kalshi reprices on the very next capture
# --------------------------------------------------------------------------- #
def test_immediate_reprice_sets_kill_condition_met(tmp_path):
    """Kalshi matches Polymarket's new level on the FIRST post-release capture -> no stale
    window at all -> Q48's kill condition is met (single-leg lag thesis DEAD-by-measurement)."""
    shocked_poly = {"cut_50plus": 0.02, "cut_25": 0.80, "no_change": 0.12,
                    "hike_25": 0.03, "hike_50plus": 0.02}
    shocked_kalshi = {b: round(v + 0.002, 4) for b, v in shocked_poly.items()}
    tape = tmp_path / "tape"
    _burst_tape(tape, post_kalshi_by_step=[shocked_kalshi] * 4,
                post_poly=[shocked_poly] * 4)
    rep = run_probe(tape, release_ts=RELEASE)
    assert rep["status"] == "ANALYSIS"
    kc = rep["kill_condition"]
    assert kc["median_captures_until_first_kalshi_move"] == 1
    assert kc["reprices_within_one_capture"] is True
    assert kc["no_persistent_stale_window"] is True
    assert kc["kill_condition_met"] is True
    for unit in rep["bursts"][0]["units"].values():
        assert unit["captures_until_first_kalshi_move"] == 1
        assert unit["has_persistent_stale_window"] is False


# --------------------------------------------------------------------------- #
# (d) n_bursts >= MIN_BURSTS_FOR_CI -> bootstrap runs, unit is the BURST
# --------------------------------------------------------------------------- #
def test_non_covering_bursts_never_enter_the_bootstrap(tmp_path):
    """Three burst windows exist but only ONE straddles the release -> n_bursts is 1 and the
    probe stays descriptive-only. A burst that does not cover the release cannot measure a
    reprice lag and must not pad the unit count."""
    shocked_poly = {"cut_50plus": 0.02, "cut_25": 0.80, "no_change": 0.12,
                    "hike_25": 0.03, "hike_50plus": 0.02}
    tape = tmp_path / "tape"
    for i in range(MIN_BURSTS_FOR_CI):
        _burst_tape(tape, release=RELEASE_DT + timedelta(days=30 * i),
                    post_kalshi_by_step=[FLAT_K] * 4, post_poly=[shocked_poly] * 4)
    rep = run_probe(tape, release_ts=RELEASE)
    assert rep["n_burst_windows"] == MIN_BURSTS_FOR_CI
    assert rep["n_covering_burst_windows"] == 1
    assert rep["n_bursts"] == 1
    assert rep["bootstrap"] is None
    assert rep["verdict"].startswith("DESCRIPTIVE ONLY")


def test_bootstrap_unit_is_the_burst_not_the_capture(tmp_path):
    """THREE accumulated FOMC meetings (three release instants, each straddled by its own
    burst window) -> the bootstrap runs and its n_units is the BURST count, NOT the
    capture/bucket/observation count (L6). Only one maximal burst run can straddle a given
    instant, so this is the only physically reachable shape of the n>=3 path."""
    shocked_poly = {"cut_50plus": 0.02, "cut_25": 0.80, "no_change": 0.12,
                    "hike_25": 0.03, "hike_50plus": 0.02}
    tape = tmp_path / "tape"
    releases = [RELEASE_DT + timedelta(days=49 * k) for k in range(MIN_BURSTS_FOR_CI)]
    for rel in releases:
        _burst_tape(tape, release=rel, post_kalshi_by_step=[FLAT_K] * 4,
                    post_poly=[shocked_poly] * 4)
    rep = run_probe(tape, release_ts=",".join(r.isoformat().replace("+00:00", "Z")
                                              for r in releases))
    assert rep["n_burst_windows"] == MIN_BURSTS_FOR_CI
    assert rep["n_covering_burst_windows"] == MIN_BURSTS_FOR_CI
    assert rep["n_bursts"] >= MIN_BURSTS_FOR_CI
    assert sorted(rep["front_meetings"]) == sorted({f"{r.year:04d}-{r.month:02d}"
                                                    for r in releases})
    boot = rep["bootstrap"]
    assert boot is not None
    assert rep["bootstrap_unit"] == "burst window (one FOMC release)"
    # THE assertion: resampling unit count == burst count, not observation count
    assert boot["n_units"] == rep["n_bursts"]
    assert boot["n_obs"] == rep["n_fired_trades"] > boot["n_units"]
    assert boot["n_boot"] == 10000
    assert len(boot["ci95"]) == 2
    # both binding gates are reported beside the CI
    assert "bootstrap_verdict_admissible" in rep
    assert rep["bootstrap_verdict_admissible"]["n_units"] == rep["n_bursts"]
    # MIN_BURSTS_FOR_CI (3) is far below L41's default min_units (10) -> honestly inadmissible
    assert rep["bootstrap_verdict_admissible"]["admissible"] is False
    assert "below_min_units" in rep["bootstrap_verdict_admissible"]["reasons"]
    assert isinstance(rep["clears_tick_magnitude"], bool)
    assert rep["verdict"].startswith("BOOTSTRAPPED")


# --------------------------------------------------------------------------- #
# (e) the fee is core.pricing's TAKER fee, and no rate literal lives in the module
# --------------------------------------------------------------------------- #
def test_gap_net_fee_uses_core_pricing_taker_fee():
    obs = {"raw_gap": 0.10, "kalshi_yes_price": 0.40}
    expected = 0.10 - fee_per_contract(0.40)
    assert abs(gap_net_fee(obs) - expected) < 1e-12
    # pinned fixture value at the TAKER rate: ceil(0.07*0.4*0.6*100)/100 = 0.02
    assert fee_per_contract(0.40) == 0.02
    assert TAKER_FEE_RATE == 0.07
    # a maker-rate fee would be 4x cheaper; assert we are NOT charging it
    assert gap_net_fee(obs) < 0.10 - 0.01


def test_entry_edge_charges_exactly_one_kalshi_taker_fee():
    obs = {"normalized_gap": -0.20, "kalshi_yes_price": 0.30, "kalshi_no_price": 0.72,
           "poly_ask_signal": 0.55, "poly_bid_signal": 0.54}
    got = entry_edge(obs)
    assert got["direction"] == "BUY_YES"
    assert abs(got["edge"] - (0.54 - 0.30 - fee_per_contract(0.30))) < 1e-12
    assert got["fee"] == fee_per_contract(0.30)

    obs_no = {"normalized_gap": +0.20, "kalshi_yes_price": 0.60, "kalshi_no_price": 0.20,
              "poly_ask_signal": 0.30, "poly_bid_signal": 0.29}
    got_no = entry_edge(obs_no)
    assert got_no["direction"] == "BUY_NO"
    assert abs(got_no["edge"] - ((1.0 - 0.30) - 0.20 - fee_per_contract(0.20))) < 1e-12


def test_entry_edge_requires_normalized_direction_agreement():
    # raw edge is positive but the NORMALIZED gap disagrees -> no trade (Hard Rule #3 gate)
    obs = {"normalized_gap": +0.20, "kalshi_yes_price": 0.30, "kalshi_no_price": 0.95,
           "poly_ask_signal": 0.55, "poly_bid_signal": 0.54}
    assert entry_edge(obs) is None
    # normalization unmeasurable -> excluded, never assumed tradeable
    assert entry_edge(dict(obs, normalized_gap=None)) is None


def test_module_source_contains_no_handrolled_fee_rate_literal():
    src = Path(__file__).resolve().parents[1] / "scripts" / "q48_s55_fomc_lag_probe.py"
    text = src.read_text()
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    assert not re.search(r"0?\.(?:07|0175|035)\b", code), "no Kalshi fee-rate literal in source"
    assert "fee_per_contract" in text and "TAKER_FEE_RATE" in text


# --------------------------------------------------------------------------- #
# (f) bracket_sum / normalized-ask path (Hard Rule #3)
# --------------------------------------------------------------------------- #
def test_ladder_sums_and_normalized_gap(tmp_path):
    when = datetime(2026, 7, 29, 17, 58, tzinfo=UTC)
    recs = _pass(when, FLAT_K, FLAT_P)
    sums = ladder_sums(recs)
    key = (MEETING, when.strftime("%Y%m%dT%H%M%SZ"))
    assert abs(sums[key]["kalshi_bracket_sum"] - sum(FLAT_K.values())) < 1e-12
    assert abs(sums[key]["polymarket_bracket_sum"] - sum(FLAT_P.values())) < 1e-12
    assert sums[key]["n_kalshi_buckets"] == 5 and sums[key]["n_polymarket_buckets"] == 5

    times, _ = pass_times(recs)
    obs, _ = build_observations(recs, times, sums)
    row = [o for o in obs if o["bucket"] == "no_change"][0]
    expect = (normalized_ask(FLAT_K["no_change"], sum(FLAT_K.values()))
              - normalized_ask(FLAT_P["no_change"], sum(FLAT_P.values())))
    assert abs(row["normalized_gap"] - expect) < 1e-12
    assert abs(row["raw_gap"] - (FLAT_K["no_change"] - FLAT_P["no_change"])) < 1e-12
    # the two are genuinely different numbers -> reporting both is not redundant
    assert abs(row["normalized_gap"] - row["raw_gap"]) > 1e-6


def test_incomplete_ladder_yields_no_normalized_gap():
    """A pass missing one Polymarket bucket cannot normalize that leg — the members present
    are NOT re-summed as if the ladder were complete (that would fabricate a probability)."""
    when = datetime(2026, 7, 29, 17, 58, tzinfo=UTC)
    recs = _pass(when, FLAT_K, FLAT_P)
    recs[0]["polymarket"]["best_ask"] = None
    sums = ladder_sums(recs)
    key = (MEETING, when.strftime("%Y%m%dT%H%M%SZ"))
    assert sums[key]["kalshi_bracket_sum"] is not None
    assert sums[key]["polymarket_bracket_sum"] is None
    times, _ = pass_times(recs)
    obs, _ = build_observations(recs, times, sums)
    assert all(o["normalized_gap"] is None for o in obs)
    assert all(o["raw_gap"] is not None for o in obs)


def test_normalized_gap_mechanical_identity_is_flagged(tmp_path):
    _sparse_tape(tmp_path / "tape")
    rep = run_probe(tmp_path / "tape", release_ts=RELEASE)
    note = rep["baseline"]["normalized_gap_note"]
    assert "MECHANICAL IDENTITY" in note
    # and the identity itself holds on a complete ladder: normalized gaps sum to ~0 per pass
    assert abs(rep["baseline"]["all_meetings"]["normalized_gap"]["mean"]) < 1e-12


# --------------------------------------------------------------------------- #
# (g) malformed / missing-leg records are skipped honestly and COUNTED
# --------------------------------------------------------------------------- #
def test_malformed_and_missing_leg_records_are_counted_not_dropped(tmp_path):
    tape = tmp_path / "tape"
    tape.mkdir()
    when = datetime(2026, 7, 20, 6, 0, tzinfo=UTC)
    good = _pass(when, FLAT_K, FLAT_P)
    later = _pass(when + timedelta(hours=12), FLAT_K, FLAT_P)
    later[0]["polymarket"]["book_fetch_ok"] = False
    later[1]["kalshi"]["yes_ask"] = None
    later[2]["polymarket"]["best_bid"] = None
    later[3]["kalshi"]["price_source_tag"] = "synthetic"
    lines = [json.dumps(r) for r in good + later]
    lines.append("{not json at all")
    lines.append(json.dumps(_record(when, "cut_25", 0.1, 0.9, 0.1, 0.09, family="cpi")))
    (tape / "dt=2026-07-20.jsonl").write_text("\n".join(lines) + "\n")

    records, skips = load_family_records(tape)
    assert skips["n_bad_json"] == 1
    assert skips["n_other_family"] == 1
    assert len(records) == 10

    rep = run_probe(tape, release_ts=RELEASE)
    o = rep["observation_skips"]
    assert o["n_book_fetch_failed"] == 1
    assert o["n_missing_kalshi_leg"] == 1
    assert o["n_missing_polymarket_leg"] == 1
    assert o["n_non_real_ask_tag"] == 1
    assert rep["n_observations"] == 10 - 4
    assert rep["load_skips"]["n_bad_json"] == 1
    assert rep["load_skips"]["n_other_family"] == 1


def test_record_without_parseable_timestamp_is_counted(tmp_path):
    tape = tmp_path / "tape"
    tape.mkdir()
    rec = _record(datetime(2026, 7, 20, 6, 0, tzinfo=UTC), "cut_25", 0.1, 0.9, 0.1, 0.09)
    rec["captured_at"] = "not-a-timestamp"
    rec["capture_id"] = "also-not-a-timestamp"
    (tape / "dt=2026-07-20.jsonl").write_text(json.dumps(rec) + "\n")
    rep = run_probe(tape, release_ts=RELEASE)
    assert rep["load_skips"]["n_records_without_capture_time"] == 1
    assert rep["n_passes"] == 0
    assert rep["status"] == "INSUFFICIENT DATA"


# --------------------------------------------------------------------------- #
# kill_condition aggregation + CLI shape
# --------------------------------------------------------------------------- #
def test_kill_condition_needs_both_components():
    fast_no_stale = [{"units": {"u": {"has_persistent_stale_window": False,
                                      "captures_until_first_kalshi_move": 1,
                                      "has_pre_release_observation": True}}}]
    assert kill_condition(fast_no_stale)["kill_condition_met"] is True
    slow = [{"units": {"u": {"has_persistent_stale_window": False,
                             "captures_until_first_kalshi_move": 4,
                             "has_pre_release_observation": True}}}]
    assert kill_condition(slow)["kill_condition_met"] is False
    stale = [{"units": {"u": {"has_persistent_stale_window": True,
                              "captures_until_first_kalshi_move": 1,
                              "has_pre_release_observation": True}}}]
    assert kill_condition(stale)["kill_condition_met"] is False
    # a unit that never repriced is counted separately, never silently treated as "moved"
    never = [{"units": {"u": {"has_persistent_stale_window": False,
                              "captures_until_first_kalshi_move": None,
                              "has_pre_release_observation": True}}}]
    kc = kill_condition(never)
    assert kc["n_units_never_repriced_in_window"] == 1
    assert kc["median_captures_until_first_kalshi_move"] is None
    assert kc["kill_condition_met"] is False


def test_cli_json_and_baseline_modes_exit_zero(tmp_path, capsys):
    from scripts.q48_s55_fomc_lag_probe import main
    _sparse_tape(tmp_path / "tape")
    assert main(["--tape-dir", str(tmp_path / "tape"), "--release-ts", RELEASE, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "INSUFFICIENT DATA"

    assert main(["--tape-dir", str(tmp_path / "tape"), "--release-ts", RELEASE,
                 "--baseline"]) == 0
    out = capsys.readouterr().out
    assert "baseline" in out and "[q48/s55]" in out
    assert "burst_windows" not in json.loads(out[:out.rindex("}") + 1])


def test_burst_max_interval_constant_is_named_not_inline():
    assert BURST_MAX_INTERVAL_S == 300.0
    assert MIN_PASSES_PER_BURST_WINDOW == 2
    assert MIN_BURSTS_FOR_CI == 3


# --------------------------------------------------------------------------- #
# hardening added after the first cut (sub-tick gate, baselined stale window,
# magnitude-qualified first move, cadence qualification, empty-population guards)
# --------------------------------------------------------------------------- #
def test_subtick_candidate_is_counted_not_fired():
    """A directionally-agreeing candidate below one tick is float residue, not a fill: it must
    NOT enter the bootstrap population, and it must be COUNTED rather than vanish."""
    # edge = 0.54 - 0.53 - fee(0.53) = 0.01 - 0.01 = 0.0 -> sub-tick
    obs = {"normalized_gap": -0.20, "kalshi_yes_price": 0.53, "kalshi_no_price": 0.90,
           "poly_ask_signal": 0.55, "poly_bid_signal": 0.54}
    cand = entry_edge_candidate(obs)
    assert cand is None or cand["edge"] < MIN_ENTRY_EDGE
    assert entry_edge(obs) is None
    assert MIN_ENTRY_EDGE == 0.01


def test_subtick_candidates_are_reported_by_run_probe(tmp_path):
    """Kalshi sits exactly one fee below the Polymarket bid on every bucket -> every candidate
    is sub-tick -> zero fired trades but a non-zero dropped count."""
    tape = tmp_path / "tape"
    poly = {b: round(v + 0.02, 4) for b, v in FLAT_K.items()}
    _burst_tape(tape, post_kalshi_by_step=[FLAT_K] * 3, post_poly=[poly] * 3)
    rep = run_probe(tape, release_ts=RELEASE)
    assert rep["status"] == "ANALYSIS"
    assert rep["min_entry_edge"] == MIN_ENTRY_EDGE
    assert rep["n_fired_trades"] + rep["n_subtick_candidates_dropped"] > 0
    assert "MIN_ENTRY_EDGE" in rep["subtick_note"]


def test_stale_window_is_baselined_against_the_units_own_pre_release_gap():
    """A unit that ALREADY carried a >fee cross-venue gap before the release has not been
    dislocated BY the release: the absolute flag fires, the baselined one does not."""
    base = datetime(2026, 7, 29, 17, 50, tzinfo=UTC)

    def row(when, k_yes=0.30, pm=0.50):
        return {"captured_at": when, "kalshi_yes_price": k_yes, "kalshi_no_price": 0.72,
                "poly_ask_signal": pm, "poly_bid_signal": pm - 0.005,
                "raw_gap": k_yes - pm, "normalized_gap": -0.2}

    # an ADEQUATE baseline (>= MIN_PRE_CAPTURES_FOR_BASELINE, L180), so the flag under test is a
    # genuine False rather than the unmeasurable-class None a thin baseline would produce
    pre = [row(base + timedelta(seconds=90 * i)) for i in range(MIN_PRE_CAPTURES_FOR_BASELINE)]
    post = [row(RELEASE_DT + timedelta(seconds=90 * i)) for i in range(1, 5)]
    unit = analyze_unit(pre, post, RELEASE_DT)
    assert unit["has_persistent_stale_window_absolute_unbaselined"] is True
    assert unit["pre_release_frac_gap_net_fee_positive"] == 1.0
    assert unit["excess_frac_gap_net_fee_positive"] == 0.0
    assert unit["has_persistent_stale_window"] is False       # standing overround, not a lag


def test_stale_window_baseline_unmeasurable_is_none_never_false():
    post = [{"captured_at": RELEASE_DT + timedelta(seconds=90 * i),
             "kalshi_yes_price": 0.30, "kalshi_no_price": 0.72,
             "poly_ask_signal": 0.80, "poly_bid_signal": 0.79,
             "raw_gap": -0.50, "normalized_gap": -0.2} for i in range(1, 4)]
    unit = analyze_unit([], post, RELEASE_DT)
    assert unit["stale_window_baseline_measurable"] is False
    assert unit["has_persistent_stale_window"] is None
    assert unit["has_persistent_stale_window_absolute_unbaselined"] is True
    assert unit["captures_until_first_kalshi_move"] is None


def test_first_move_is_magnitude_blind_and_has_a_qualified_companion():
    """A 1c Kalshi tick against a 10c Polymarket shock scores first_move=1 — which must NOT be
    read as 'Kalshi caught up'. The half-move companion stays None."""
    pre = [{"captured_at": RELEASE_DT - timedelta(seconds=60), "kalshi_yes_price": 0.30,
            "kalshi_no_price": 0.72, "poly_ask_signal": 0.30, "poly_bid_signal": 0.295,
            "raw_gap": 0.0, "normalized_gap": 0.0}]
    post = [{"captured_at": RELEASE_DT + timedelta(seconds=90 * i), "kalshi_yes_price": 0.31,
             "kalshi_no_price": 0.71, "poly_ask_signal": 0.40, "poly_bid_signal": 0.395,
             "raw_gap": -0.09, "normalized_gap": -0.09} for i in range(1, 4)]
    unit = analyze_unit(pre, post, RELEASE_DT)
    assert unit["captures_until_first_kalshi_move"] == 1
    assert unit["captures_until_kalshi_closed_half_of_polymarket_move"] is None
    assert abs(unit["polymarket_max_abs_move_vs_pre"] - 0.10) < 1e-12
    # and it DOES fire once Kalshi closes >= half the move
    post2 = [dict(p, kalshi_yes_price=0.36) for p in post]
    unit2 = analyze_unit(pre, post2, RELEASE_DT)
    assert unit2["captures_until_kalshi_closed_half_of_polymarket_move"] == 1


def test_cadence_qualification_separates_a_real_burst_from_a_recurring_pair():
    base = datetime(2026, 7, 29, 17, 0, tzinfo=UTC)
    pair = {"p0": base, "p1": base + timedelta(seconds=120)}
    assert detect_burst_windows(pair)[0]["cadence_qualified"] is False
    real = {f"b{i}": base + timedelta(days=1, seconds=90 * i) for i in range(12)}
    w = detect_burst_windows(real)[0]
    assert w["n_passes"] >= BURST_CADENCE_MIN_PASSES
    assert w["duration_s"] >= BURST_CADENCE_MIN_DURATION_S
    assert w["cadence_qualified"] is True


def test_run_probe_reports_the_cadence_qualified_split(tmp_path):
    _sparse_tape(tmp_path / "tape")
    tape = tmp_path / "tape"
    # add one 2-pass recurring coincidence (a pair 200s apart) -> detected but NOT qualified
    t = datetime(2026, 7, 24, 6, 0, tzinfo=UTC)
    _write(tape, _pass(t, FLAT_K, FLAT_P) + _pass(t + timedelta(seconds=200), FLAT_K, FLAT_P))
    rep = run_probe(tape, release_ts=RELEASE)
    assert rep["n_burst_windows"] == 1
    assert rep["n_burst_windows_cadence_qualified"] == 0
    assert rep["n_burst_windows_marginal"] == 1
    assert "Never write `n_burst_windows` into a log" in rep["burst_cadence_note"]


def test_kill_condition_on_zero_units_is_none_not_a_vacuous_true():
    kc = kill_condition([])
    assert kc["n_units"] == 0
    assert kc["no_persistent_stale_window"] is None
    assert kc["kill_condition_met"] is None


def test_covering_window_with_zero_priced_observations_is_insufficient_data(tmp_path):
    """A covering burst whose every leg is tagged `midpoint` leaves ZERO observations; the probe
    must NOT reach ANALYSIS and emit a vacuous 'no persistent stale window'."""
    tape = tmp_path / "tape"
    _burst_tape(tape, post_kalshi_by_step=[FLAT_K] * 3)
    for day_file in tape.glob("dt=*.jsonl"):
        rows = [json.loads(ln) for ln in day_file.read_text().splitlines() if ln.strip()]
        for r in rows:
            r["kalshi"]["price_source_tag"] = "midpoint"
        day_file.write_text("".join(json.dumps(r) + "\n" for r in rows))
    rep = run_probe(tape, release_ts=RELEASE)
    assert rep["n_covering_burst_windows"] == 1
    assert rep["n_observations"] == 0
    assert rep["status"] == "INSUFFICIENT DATA"
    assert "ZERO priced observations" in rep["reason"]
    assert rep["verdict"] is None
    assert "kill_condition" not in rep and "bootstrap" not in rep


def test_bootstrap_object_carries_its_own_statistic_label(tmp_path):
    shocked_poly = {"cut_50plus": 0.02, "cut_25": 0.80, "no_change": 0.12,
                    "hike_25": 0.03, "hike_50plus": 0.02}
    tape = tmp_path / "tape"
    releases = [RELEASE_DT + timedelta(days=49 * k) for k in range(MIN_BURSTS_FOR_CI)]
    for rel in releases:
        _burst_tape(tape, release=rel, post_kalshi_by_step=[FLAT_K] * 4,
                    post_poly=[shocked_poly] * 4)
    rep = run_probe(tape, release_ts=",".join(r.isoformat().replace("+00:00", "Z")
                                              for r in releases))
    assert "NOT settled P&L" in rep["bootstrap"]["bootstrap_statistic"]
    assert "real_ask" in rep["bootstrap"]["bootstrap_statistic"]
    assert rep["bootstrap_cadence_warning"] is not None    # 4-pass windows are not burst cadence


# --------------------------------------------------------------------------- #
# (C) the human one-liner's provenance bracket is DATA-DERIVED, never hardcoded
# --------------------------------------------------------------------------- #
def test_one_liner_provenance_is_rendered_from_the_observed_tags(tmp_path):
    """The one-liner is the line most likely to be pasted into `kb/00-LOG.md`, so it must never
    assert `real_ask` from a string literal: with zero surviving observations it has to say so
    (CLAUDE.md's untagged->synthetic default, re-opened on the copy-paste surface)."""
    tape = tmp_path / "tape"
    _sparse_tape(tape)

    # (i) a real all-`real_ask` tape -> the bracket names BOTH legs' observed tags
    rep = run_probe(tape, release_ts=RELEASE)
    assert rep["price_source_tags_observed"] == [{"kalshi": "real_ask", "polymarket": "real_ask"}]
    assert provenance_string(rep) == "[kalshi=real_ask/polymarket=real_ask]"
    assert provenance_string(rep) in human_one_liner(rep)

    # (ii) an unknown family -> zero records, zero observations, EMPTY tag list
    empty = run_probe(tape, release_ts=RELEASE, family="nope")
    assert empty["n_observations"] == 0
    assert empty["price_source_tags_observed"] == []
    assert provenance_string(empty) == "[no priced observations]"
    line = human_one_liner(empty)
    assert "[no priced observations]" in line and "real_ask" not in line

    # (iii) a tape whose legs are all `midpoint` also never renders as real_ask
    for day_file in tape.glob("dt=*.jsonl"):
        rows = [json.loads(ln) for ln in day_file.read_text().splitlines() if ln.strip()]
        for r in rows:
            r["polymarket"]["price_source_tag"] = "midpoint"
        day_file.write_text("".join(json.dumps(r) + "\n" for r in rows))
    mid = run_probe(tape, release_ts=RELEASE)
    assert mid["n_observations"] == 0
    assert "real_ask" not in human_one_liner(mid)

    # the literal that used to be hardcoded is gone from the RENDERING CODE (it survives only
    # as the retracted example inside `provenance_string`'s docstring)
    import inspect

    import scripts.q48_s55_fomc_lag_probe as mod
    assert "[real_ask both legs]" not in inspect.getsource(mod.human_one_liner)
    assert "provenance_string(rep)" in inspect.getsource(mod.human_one_liner)


# --------------------------------------------------------------------------- #
# (D-ii) the docstring's cadence figures + the retracted "by construction" claim
# --------------------------------------------------------------------------- #
def test_docstring_states_the_corrected_cadence_and_retracts_the_false_claims():
    """L165: the corrected numbers must live in the probe itself, and the two FALSE claims must
    be gone — not softened. Tape truth (2026-07-26, `tape/polymarket_macro_pairs/`): 600 passes
    / 20.65 days = 29.05 passes/day, median inter-pass gap 1,856.3s."""
    import scripts.q48_s55_fomc_lag_probe as mod
    # whitespace-normalized: the claims are line-wrapped in the source
    doc = " ".join(mod.__doc__.split())
    src = (Path(__file__).resolve().parents[1] / "scripts"
           / "q48_s55_fomc_lag_probe.py").read_text()

    # (ii) the recurring-cadence figure, and the wrong one retired everywhere in the file
    assert "29.05 passes/day" in doc and "1,856.3s" in doc
    assert "9.44/day" in doc and "10,777.7s" in doc
    # the wrong figure survives ONLY as an explicitly-labelled retraction, nowhere as a claim
    assert src.count("captures/day") == 1, "the '~2 captures/day' figure was wrong by 5-15x"
    assert 'earlier "~2 captures/day" in this' in src

    # (i) the "n_bursts>=3 necessarily means >=3 FOMC statements, by construction" claim is gone
    assert "necessarily means" not in src
    assert "never reach the CI path, by construction" not in src
    assert "ADVISORY on an operator-supplied instant list" in doc
    assert "bootstrap_verdict_admissible.admissible = False" in doc
    # and the tick-magnitude gate is NOT credited as a guard against a fabricated list: under
    # the MIN_ENTRY_EDGE gate the same attack shape clears it
    assert "tick-magnitude gate is therefore NOT a reliable guard" in doc
    assert "fabricated instants" in doc
    assert "cadence_qualified" in " ".join(mod.parse_releases.__doc__.split())
    assert "WHAT THIS DOES *NOT* GUARANTEE" in " ".join(mod.parse_releases.__doc__.split())

    # H: the one field that must never be quoted is named explicitly
    assert "`baseline.*.normalized_gap.mean`" in doc


def test_fabricated_release_list_reaches_the_ci_path_but_is_flagged_not_burst_cadence(tmp_path):
    """The verifier's attack, offline: N fabricated instants, each dropped between the two
    passes of an ordinary RECURRING-cadence pair, reach `BOOTSTRAPPED (n_bursts=N)` because
    nothing validates that an instant is a real release. The probe must not pretend otherwise —
    it must say ZERO covering windows are burst cadence, emit the warning, and fail the two
    gates that are the actual guard."""
    tape = tmp_path / "tape"
    starts = [datetime(2026, 7, 20, 6, 0, tzinfo=UTC) + timedelta(hours=12 * i)
              for i in range(MIN_BURSTS_FOR_CI)]
    shocked_poly = {"cut_50plus": 0.02, "cut_25": 0.80, "no_change": 0.12,
                    "hike_25": 0.03, "hike_50plus": 0.02}
    for t in starts:                      # a 2-pass pair 200s apart == "recurring cadence"
        _write(tape, _pass(t, FLAT_K, FLAT_P)
               + _pass(t + timedelta(seconds=200), FLAT_K, shocked_poly))
    fabricated = ",".join((t + timedelta(seconds=100)).isoformat().replace("+00:00", "Z")
                          for t in starts)
    rep = run_probe(tape, release_ts=fabricated)

    assert rep["n_bursts"] == MIN_BURSTS_FOR_CI
    assert rep["verdict"].startswith("BOOTSTRAPPED")          # honestly reported, not hidden
    # ...but every one of those "bursts" is a recurring-cadence pair, and the report says so
    assert rep["n_burst_windows"] == MIN_BURSTS_FOR_CI
    assert rep["n_burst_windows_cadence_qualified"] == 0
    assert rep["n_covering_burst_windows_cadence_qualified"] == 0
    assert rep["bootstrap_cadence_warning"] is not None
    assert "fabricated instants" in rep["bootstrap_cadence_warning"]
    assert "NOT burst cadence" in rep["bootstrap_cadence_warning"]
    # and the gate that actually guarded the real attack's output still fails
    assert rep["bootstrap_verdict_admissible"]["admissible"] is False
    assert isinstance(rep["clears_tick_magnitude"], bool)
    assert "bootstrap_statistic" in rep["bootstrap"]


# --------------------------------------------------------------------------- #
# (L180-1) the BASELINE's own n-adequacy guard: a thin pre-period is not a baseline
# --------------------------------------------------------------------------- #
def _perm_overround_rows(release, *, n_pre, tight_last_pre):
    """L180's reproduction fixture, verbatim in shape: an identical PERMANENT 6c cross-venue
    overround before and after the release, except that the LAST pre-release capture is
    momentarily tight. With a thick pre-period that lone tight capture is one draw among many;
    with n_pre=1 it IS the entire baseline."""
    def row(when, k, p):
        return {"captured_at": when, "kalshi_yes_price": k, "kalshi_no_price": 1 - k,
                "poly_ask_signal": p, "poly_bid_signal": p - 0.01,
                "raw_gap": k - p, "normalized_gap": k - p}

    post = [row(release + timedelta(seconds=60 * i), 0.50, 0.44) for i in range(1, 25)]
    pre = [row(release - timedelta(seconds=60 * (n_pre - i)), 0.50, 0.44)
           for i in range(n_pre - 1)]
    pre.append(row(release - timedelta(seconds=60), 0.50, 0.50 if tight_last_pre else 0.44))
    return pre, post


def test_thin_pre_release_baseline_is_none_never_a_persistent_true():
    """L180: differencing against a pre-event period does not remove vacuity if the pre-period
    can be n=1. Identical permanent overround, identical post-release rows: at n_pre=1 the
    pre-release fraction is confined to {0,1} and the pre-release max is a single draw, so ONE
    momentarily-tight pre-capture used to flip a standing overround into a 'release-caused
    dislocation' (the old code returned True here). It must now be the unmeasurable-class None —
    never True (which would credit the lag thesis), never False (which would assert the opposite
    on the same inadequate evidence)."""
    release = datetime(2026, 7, 14, 12, 30, tzinfo=UTC)
    pre1, post = _perm_overround_rows(release, n_pre=1, tight_last_pre=True)
    thick, _ = _perm_overround_rows(release, n_pre=23, tight_last_pre=True)

    thin_unit = analyze_unit(pre1, post, release)
    thick_unit = analyze_unit(thick, post, release)

    assert thin_unit["n_pre_captures"] == 1
    assert thin_unit["thin_baseline"] is True
    assert thin_unit["stale_window_baseline_measurable"] is True      # rows exist...
    assert thin_unit["stale_window_baseline_adequate"] is False       # ...but are not enough
    assert thin_unit["has_persistent_stale_window"] is None
    # the absolute (unbaselined) statistic is untouched — the fix removes a CLAIM, not a number
    assert thin_unit["has_persistent_stale_window_absolute_unbaselined"] is True

    assert thick_unit["n_pre_captures"] == 23
    assert thick_unit["thin_baseline"] is False
    assert thick_unit["stale_window_baseline_adequate"] is True
    assert thick_unit["has_persistent_stale_window"] is False         # standing overround
    assert thin_unit["min_pre_captures_for_baseline"] == MIN_PRE_CAPTURES_FOR_BASELINE


def test_thin_baseline_boundary_is_exactly_min_pre_captures_for_baseline():
    """One capture below the floor is thin; the floor itself is adequate. Pins the comparison
    direction so the constant cannot drift into an off-by-one."""
    release = datetime(2026, 7, 14, 12, 30, tzinfo=UTC)
    below, post = _perm_overround_rows(release, n_pre=MIN_PRE_CAPTURES_FOR_BASELINE - 1,
                                       tight_last_pre=True)
    at, _ = _perm_overround_rows(release, n_pre=MIN_PRE_CAPTURES_FOR_BASELINE,
                                 tight_last_pre=True)
    assert analyze_unit(below, post, release)["thin_baseline"] is True
    assert analyze_unit(below, post, release)["has_persistent_stale_window"] is None
    assert analyze_unit(at, post, release)["thin_baseline"] is False
    assert analyze_unit(at, post, release)["has_persistent_stale_window"] is False
    assert MIN_PRE_CAPTURES_FOR_BASELINE > 1     # the whole point: n=1 is not a baseline


def test_thin_baseline_can_never_create_a_persistent_stale_window_count():
    """The invariant that must hold no matter how the flag is represented: a thin baseline
    cannot CONTRIBUTE to `n_units_with_persistent_stale_window`. The two None causes (thin vs
    zero-pre-capture) are counted separately and PARTITION the None flags — no double count, and
    the pre-existing `n_units_stale_window_baseline_unmeasurable` keeps its original meaning."""
    units = {
        "thin": {"has_persistent_stale_window": None, "thin_baseline": True,
                 "captures_until_first_kalshi_move": 1, "has_pre_release_observation": True},
        "absent": {"has_persistent_stale_window": None, "thin_baseline": False,
                   "captures_until_first_kalshi_move": 1, "has_pre_release_observation": False},
        "real": {"has_persistent_stale_window": True, "thin_baseline": False,
                 "captures_until_first_kalshi_move": 1, "has_pre_release_observation": True},
    }
    kc = kill_condition([{"units": units}])
    assert kc["n_units"] == 3
    assert kc["n_units_with_persistent_stale_window"] == 1            # only the real one
    assert kc["n_units_with_thin_stale_window_baseline"] == 1
    assert kc["n_units_stale_window_baseline_unmeasurable"] == 1
    assert (kc["n_units_with_thin_stale_window_baseline"]
            + kc["n_units_stale_window_baseline_unmeasurable"]
            + kc["n_units_with_persistent_stale_window"]) <= kc["n_units"]
    assert kc["min_pre_captures_for_baseline"] == MIN_PRE_CAPTURES_FOR_BASELINE
    assert "thin" in kc["stale_window_note"].lower()
    # the partition this test exists to protect, restated against the measurable count
    assert kc["n_units_with_measurable_stale_window_baseline"] == 1

    # and with EVERY unit thin, the persistent count is 0 — but that 0 is NOT evidence of an
    # absence: see `test_all_units_unmeasurable_makes_the_kill_none_not_a_vacuous_true`.
    all_thin = kill_condition([{"units": {"a": units["thin"], "b": dict(units["thin"])}}])
    assert all_thin["n_units_with_persistent_stale_window"] == 0
    assert all_thin["n_units_with_thin_stale_window_baseline"] == 2
    assert all_thin["no_persistent_stale_window"] is None


def test_all_units_unmeasurable_makes_the_kill_none_not_a_vacuous_true():
    """DEFECT 3 — an n-adequacy FLOOR does not remove vacuity, it RELOCATES it.

    Raising `MIN_PRE_CAPTURES_FOR_BASELINE` from 1 to 5 moved units out of the measurable set
    (into the None class). If the kill still gated on `n_units`, a population in which EVERY
    unit is None would satisfy `n_persistent == 0` and fire a hard "S55 is dead" from zero
    measurable evidence. That is live at the 90s burst cadence: a window opening < 7.5 min
    before the 18:00Z statement leaves every unit below the floor. So the guard must be the
    count of MEASURABLE units, not the count of units — the same convention `kill_condition`
    already applies at `n_units == 0`."""
    thin = {"has_persistent_stale_window": None, "thin_baseline": True,
            "captures_until_first_kalshi_move": 1, "has_pre_release_observation": True}
    absent = {"has_persistent_stale_window": None, "thin_baseline": False,
              "captures_until_first_kalshi_move": 1, "has_pre_release_observation": False}

    all_thin = kill_condition([{"units": {"a": thin, "b": dict(thin)}}])
    assert all_thin["n_units"] == 2
    assert all_thin["n_units_with_measurable_stale_window_baseline"] == 0
    assert all_thin["reprices_within_one_capture"] is True     # the OTHER component still fires
    assert all_thin["no_persistent_stale_window"] is None
    assert all_thin["kill_condition_met"] is None

    # the zero-pre-capture None class behaves identically, and so does a mix of the two
    all_absent = kill_condition([{"units": {"a": absent, "b": dict(absent)}}])
    assert all_absent["no_persistent_stale_window"] is None
    assert all_absent["kill_condition_met"] is None
    mixed_none = kill_condition([{"units": {"a": thin, "b": absent}}])
    assert mixed_none["n_units_with_measurable_stale_window_baseline"] == 0
    assert mixed_none["kill_condition_met"] is None

    # ...and ONE measurable unit is enough to make the statement again — the guard is not a
    # blanket disabling of the kill
    measurable = {"has_persistent_stale_window": False, "thin_baseline": False,
                  "captures_until_first_kalshi_move": 1, "has_pre_release_observation": True}
    revived = kill_condition([{"units": {"a": thin, "b": dict(thin), "c": measurable}}])
    assert revived["n_units_with_measurable_stale_window_baseline"] == 1
    assert revived["no_persistent_stale_window"] is True
    assert revived["kill_condition_met"] is True


def test_all_thin_baseline_run_reports_no_kill_verdict_end_to_end(tmp_path):
    """The Defect-3 guard on the REPORT surface, not just on the aggregator: a whole burst whose
    every unit has a 1-capture baseline reaches ANALYSIS but must not print a kill."""
    shocked_poly = {"cut_50plus": 0.02, "cut_25": 0.80, "no_change": 0.12,
                    "hike_25": 0.03, "hike_50plus": 0.02}
    tape = tmp_path / "tape"
    _burst_tape(tape, n_pre=1, post_kalshi_by_step=[FLAT_K] * 6, post_poly=[shocked_poly] * 6)
    kc = run_probe(tape, release_ts=RELEASE)["kill_condition"]
    assert kc["n_units"] == 5
    assert kc["n_units_with_thin_stale_window_baseline"] == 5
    assert kc["n_units_with_measurable_stale_window_baseline"] == 0
    assert kc["no_persistent_stale_window"] is None
    assert kc["kill_condition_met"] is None


def test_dry_run_headline_units_stay_measurable_under_the_defect_3_guard():
    """The guard must not touch the 2026-07-14 CPI dry-run: all 15 units carry n_pre=23, so the
    measurable count equals the unit count and the headline is unchanged."""
    units = {f"u{i}": {"has_persistent_stale_window": i < 3, "thin_baseline": False,
                       "captures_until_first_kalshi_move": 1,
                       "has_pre_release_observation": True} for i in range(15)}
    kc = kill_condition([{"units": units}])
    assert kc["n_units"] == 15
    assert kc["n_units_with_measurable_stale_window_baseline"] == 15
    assert kc["n_units_with_persistent_stale_window"] == 3
    assert kc["no_persistent_stale_window"] is False
    assert kc["kill_condition_met"] is False


def test_run_probe_surfaces_the_thin_baseline_count_in_the_report_header(tmp_path):
    """The fact has to be visible on the report surface, not just inside a unit dict: a run whose
    every unit has a 1-capture baseline must say so in the header block, in the kill-condition
    block, and in the one-liner that gets pasted into a log."""
    shocked_poly = {"cut_50plus": 0.02, "cut_25": 0.80, "no_change": 0.12,
                    "hike_25": 0.03, "hike_50plus": 0.02}
    tape = tmp_path / "tape"
    _burst_tape(tape, n_pre=1, post_kalshi_by_step=[FLAT_K] * 6, post_poly=[shocked_poly] * 6)
    rep = run_probe(tape, release_ts=RELEASE)

    assert rep["status"] == "ANALYSIS"
    assert rep["min_pre_captures_for_baseline"] == MIN_PRE_CAPTURES_FOR_BASELINE
    assert rep["stale_window_excess_epsilon"] == STALE_WINDOW_EXCESS_EPSILON
    kc = rep["kill_condition"]
    assert kc["n_units"] == 5
    assert kc["n_units_with_thin_stale_window_baseline"] == 5
    assert kc["n_units_with_persistent_stale_window"] == 0
    # the ABSOLUTE statistic still sees the dislocation — nothing was hidden, only un-claimed
    assert kc["n_units_with_persistent_stale_window_absolute_unbaselined"] >= 1
    assert all(u["thin_baseline"] is True for u in rep["bursts"][0]["units"].values())
    assert "thin baseline=5" in human_one_liner(rep)

    # the SAME tape with an adequate baseline does produce the claim -> the guard is not a no-op
    tape2 = tmp_path / "tape2"
    _burst_tape(tape2, n_pre=MIN_PRE_CAPTURES_FOR_BASELINE,
                post_kalshi_by_step=[FLAT_K] * 6, post_poly=[shocked_poly] * 6)
    rep2 = run_probe(tape2, release_ts=RELEASE)
    assert rep2["kill_condition"]["n_units_with_thin_stale_window_baseline"] == 0
    assert rep2["kill_condition"]["n_units_with_persistent_stale_window"] >= 1


# --------------------------------------------------------------------------- #
# (L180-2) the excess-over-baseline tick test needs an explicit epsilon
# --------------------------------------------------------------------------- #
def _excess_unit(release, pre_prices, post_prices):
    """A unit whose pre/post gap_net_fee values are chosen off the 1c grid so the excess lands
    on a named float. `*_prices` are (kalshi_yes, polymarket_ask) pairs."""
    def rows(start, prices, n):
        k, p = prices
        return [{"captured_at": start + timedelta(seconds=90 * i), "kalshi_yes_price": k,
                 "kalshi_no_price": round(1 - k, 4), "poly_ask_signal": p,
                 "poly_bid_signal": max(0.0, p - 0.005), "raw_gap": k - p,
                 "normalized_gap": -0.2} for i in range(n)]

    pre = rows(release - timedelta(seconds=90 * MIN_PRE_CAPTURES_FOR_BASELINE), pre_prices,
               MIN_PRE_CAPTURES_FOR_BASELINE)
    post = rows(release + timedelta(seconds=90), post_prices, 3)
    return analyze_unit(pre, post, release)


def test_stale_window_excess_tick_test_has_an_explicit_epsilon():
    """L180 closure, on the 1c grid: `excess_max` comes out at 0.010000000000000009 — the EXACT
    value the real `2026-10|cut_25` unit carried on the 2026-07-14 CPI dry-run — and this code
    drops it. IT IS NOT FLOAT DUST. The justification this file previously carried (an "ulp
    accident": "one ulp the other way and the same tape reports a different headline") was an
    INHERITED, never-re-measured claim — L177's citation-chain failure applied to a
    float-fragility claim. Measured: the excess is EXACTLY one tick in exact arithmetic
    (`Decimal('0.01') - Decimal('0.00')`), it carries 5.0 ulps of float margin over 0.01, and it
    still clears one tick with the pre-release max forced to exactly 0.0 (2.0 ulps to spare).
    What drops it is a deliberate threshold TIGHTENING from `>= 1 tick` to `> 1 tick` — the
    epsilon moves the boundary case, it does not de-dust anything. See
    `test_the_dropped_unit_is_exactly_one_tick_not_float_dust`."""
    release = RELEASE_DT
    boundary = _excess_unit(release, (0.01, 0.01), (0.06, 0.07))
    # the float form is the documented one
    assert repr(boundary["excess_max_abs_gap_net_fee"]) == "0.010000000000000009"
    # the documented ">= 1 tick" rule passed on this value, and was RIGHT to under that rule
    assert boundary["excess_max_abs_gap_net_fee"] > STALE_WINDOW_MIN_EXCESS_DOLLARS
    assert boundary["has_persistent_stale_window_absolute_unbaselined"] is True
    assert boundary["stale_window_baseline_adequate"] is True
    # ...and the tightened "> 1 tick" rule scores it to the kill side
    assert boundary["has_persistent_stale_window"] is False

    # a genuinely large excess (8c over the baseline) still clears -> the epsilon is not a
    # blanket kill of the statistic
    real = _excess_unit(release, (0.01, 0.01), (0.06, 0.15))
    assert real["excess_max_abs_gap_net_fee"] > STALE_WINDOW_MIN_EXCESS_DOLLARS
    assert real["has_persistent_stale_window"] is True


def test_stale_window_excess_epsilon_is_named_sub_tick_and_kill_biased():
    """The epsilon must be a NAMED constant (the `MIN_ENTRY_EDGE` pattern, L176/L179), orders of
    magnitude below one tick so it can never filter an economically real excess, and orders above
    the ~1e-17 residues this arithmetic produces. Its direction is documented and deliberate: an
    excess of EXACTLY one tick does not clear, which biases toward the KILL."""
    assert 0 < STALE_WINDOW_EXCESS_EPSILON < STALE_WINDOW_MIN_EXCESS_DOLLARS / 1e6
    assert STALE_WINDOW_EXCESS_EPSILON > 1e-15
    src = (Path(__file__).resolve().parents[1] / "scripts"
           / "q48_s55_fomc_lag_probe.py").read_text()
    assert "STALE_WINDOW_MIN_EXCESS_DOLLARS = PRICE_TICK" in src        # threshold unchanged
    assert "excess_max >= STALE_WINDOW_MIN_EXCESS_DOLLARS\n" not in src  # the bare `>=` is gone
    assert "biases toward the KILL" in src or "biases toward the kill" in src

    # the exact-one-tick boundary resolves to the kill side, deterministically (not by ulp)
    exact = _excess_unit(RELEASE_DT, (0.01, 0.02), (0.02, 0.04))
    assert exact["excess_max_abs_gap_net_fee"] == STALE_WINDOW_MIN_EXCESS_DOLLARS
    assert exact["has_persistent_stale_window"] is False


def test_the_dropped_unit_is_exactly_one_tick_not_float_dust():
    """The "ulp accident" justification was FALSE, and a claim about float fragility is itself a
    MEASUREMENT — it must be re-derived at every hop, not inherited (L177 extended).

    Reconstructed from the real `2026-10|cut_25` prices of the 2026-07-14 CPI dry-run
    (pre: kalshi 0.11 / poly 0.12; post-max: kalshi 0.11 / poly 0.09). In EXACT arithmetic the
    pre-release max is |0.01| - fee(0.11) = 0.00, the post-release max is |0.02| - fee(0.11) =
    0.01, and the excess is `Decimal('0.01') - Decimal('0.00')` = exactly ONE TICK. In float it
    carries 5.0 ulps of margin over 0.01, and even with the pre-release max forced to exactly 0.0
    it still clears one tick with 2.0 ulps to spare. So it was never one ulp from the boundary:
    it is dropped by the deliberate `>= 1 tick` -> `> 1 tick` TIGHTENING, not by de-dusting."""
    unit = _excess_unit(RELEASE_DT, (0.11, 0.12), (0.11, 0.09))

    # (1) the float forms, reproduced exactly from the real prices
    assert repr(unit["pre_release_max_abs_gap_net_fee"]) == "-5.204170427930421e-18"
    assert repr(unit["max_abs_gap_net_fee"]) == "0.010000000000000004"
    assert repr(unit["excess_max_abs_gap_net_fee"]) == "0.010000000000000009"

    # (2) the EXACT arithmetic behind those floats — one tick, not dust
    assert fee_per_contract(0.11) == 0.01
    exact_pre = Decimal("0.01") - Decimal("0.01")          # |0.11-0.12| - fee(0.11)
    exact_post = Decimal("0.02") - Decimal("0.01")         # |0.11-0.09| - fee(0.11)
    assert exact_pre == Decimal("0.00")
    assert exact_post == Decimal("0.01")
    assert exact_post - exact_pre == Decimal(str(STALE_WINDOW_MIN_EXCESS_DOLLARS))

    # (3) the float margin is 5 ulps, and 2 ulps even with pre_max pinned to exactly 0.0 —
    #     i.e. the outcome under the documented ">= 1 tick" rule is robust, not ulp-decided
    ulp = math.ulp(STALE_WINDOW_MIN_EXCESS_DOLLARS)
    margin = (unit["excess_max_abs_gap_net_fee"] - STALE_WINDOW_MIN_EXCESS_DOLLARS) / ulp
    assert round(margin, 2) == 5.0
    assert unit["max_abs_gap_net_fee"] - 0.0 >= STALE_WINDOW_MIN_EXCESS_DOLLARS
    assert round((unit["max_abs_gap_net_fee"] - STALE_WINDOW_MIN_EXCESS_DOLLARS) / ulp, 2) == 2.0

    # (4) and the tightened rule — not a de-duster — is what drops it
    assert unit["stale_window_baseline_adequate"] is True
    assert unit["has_persistent_stale_window_absolute_unbaselined"] is True
    assert unit["has_persistent_stale_window"] is False

    # (5) the retracted claim is GONE from the probe, not merely softened
    src = (Path(__file__).resolve().parents[1] / "scripts"
           / "q48_s55_fomc_lag_probe.py").read_text()
    assert "one ulp the other way" not in src
    assert "so float dust cannot clear it" not in src
    assert "gave 4 by ulp" not in src
    # ...and the corrected statement is present, with the strict-vs-tolerant counterfactual kept
    assert "DELIBERATE TIGHTENING" in src or "deliberate tightening" in src
    assert "one full tick in exact arithmetic" in src
    assert "= 3" in src and "gives 4" in src


def test_report_surface_states_the_effective_strictly_greater_than_one_tick_rule():
    """DEFECT 2B: `stale_window_note` is the ONLY statement of the rule a JSON-report reader
    sees. It must not advertise `>= 1 tick` while the code enforces `> 1 tick`."""
    kc = kill_condition([{"units": {"u": {"has_persistent_stale_window": False,
                                          "thin_baseline": False,
                                          "captures_until_first_kalshi_move": 1,
                                          "has_pre_release_observation": True}}}])
    note = kc["stale_window_note"]
    assert "STRICTLY MORE THAN ONE TICK" in note
    assert "EXACTLY one tick is scored to the KILL side" in note
    assert "> 1 tick" in note
    assert "by >= 1 tick" not in note          # the superseded wording is gone
    assert "float dust cannot clear it" not in note
    # the published strict-vs-tolerant counterfactual survives on the report surface
    assert "3 units (this code) and 4" in note

    doc = " ".join(__import__("scripts.q48_s55_fomc_lag_probe", fromlist=["x"]).__doc__.split())
    assert "an excess of EXACTLY one tick does NOT clear" in doc
    assert "by at least `STALE_WINDOW_MIN_EXCESS_DOLLARS`" not in doc
